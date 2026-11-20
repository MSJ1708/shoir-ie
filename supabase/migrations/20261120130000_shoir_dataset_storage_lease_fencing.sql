BEGIN;

-- Renew only a still-live lease held by the same operation/actor/token.
-- An expired or reclaimed holder cannot renew itself.
CREATE OR REPLACE FUNCTION public.shoir_dataset_storage_lease_renew(
    p_workspace_key text,
    p_dataset_id text,
    p_lease_token uuid,
    p_lease_operation text,
    p_actor_username_lc text,
    p_lease_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_renewed boolean;
BEGIN
    IF p_workspace_key IS NULL
       OR p_workspace_key !~ '^[0-9a-f]{32}$'
       OR p_dataset_id IS NULL
       OR p_dataset_id !~ '^DS-[A-F0-9]{12,32}$'
       OR p_lease_token IS NULL
       OR p_lease_operation IS NULL
       OR p_lease_operation NOT IN ('finalize', 'register', 'sweep')
       OR p_actor_username_lc IS NULL
       OR length(btrim(p_actor_username_lc)) NOT BETWEEN 1 AND 128
       OR p_lease_seconds IS NULL
       OR p_lease_seconds NOT BETWEEN 30 AND 600 THEN
        RAISE EXCEPTION 'Invalid dataset storage lifecycle lease renewal input.'
            USING ERRCODE = '22023';
    END IF;

    UPDATE public.shoir_dataset_storage_lifecycle_leases
       SET expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds)
     WHERE workspace_key = p_workspace_key
       AND dataset_id = p_dataset_id
       AND lease_token = p_lease_token
       AND lease_operation = p_lease_operation
       AND actor_username_lc = lower(btrim(p_actor_username_lc))
       AND expires_at > clock_timestamp()
    RETURNING TRUE INTO v_renewed;

    RETURN COALESCE(v_renewed, FALSE);
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_dataset_storage_lease_renew(
    text, text, uuid, text, text, integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_dataset_storage_lease_renew(
    text, text, uuid, text, text, integer
) TO service_role;

-- Lock and fence the final metadata transaction against the exact live
-- finalization lease. SELECT FOR UPDATE prevents another acquisition from
-- reclaiming the lease until this transaction commits.
CREATE OR REPLACE FUNCTION public.shoir_platform_register_dataset_version_with_storage_and_lease(
    p_workspace_key text,
    p_dataset_id text,
    p_name text,
    p_source_name text,
    p_data_hash text,
    p_version_fingerprint text,
    p_row_count bigint,
    p_column_count integer,
    p_schema_json jsonb,
    p_transformations_json jsonb,
    p_actor text,
    p_version_record_id text,
    p_head_record_id text,
    p_event_id text,
    p_storage_key text,
    p_lease_token uuid
)
RETURNS TABLE (
    dataset_id text,
    version integer,
    data_hash text,
    version_fingerprint text,
    version_record_id text,
    registered_at timestamptz,
    created_new_version boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF p_lease_token IS NULL THEN
        RAISE EXCEPTION 'Dataset finalization lease token is required.'
            USING ERRCODE = '22023';
    END IF;

    PERFORM 1
      FROM public.shoir_dataset_storage_lifecycle_leases
     WHERE workspace_key = p_workspace_key
       AND dataset_id = p_dataset_id
       AND lease_token = p_lease_token
       AND lease_operation = 'finalize'
       AND actor_username_lc = lower(btrim(p_actor))
       AND expires_at > clock_timestamp()
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Dataset finalization lease is no longer active.'
            USING ERRCODE = '55P03';
    END IF;

    RETURN QUERY
    SELECT *
      FROM public.shoir_platform_register_dataset_version_with_storage(
        p_workspace_key, p_dataset_id, p_name, p_source_name,
        p_data_hash, p_version_fingerprint, p_row_count, p_column_count,
        p_schema_json, p_transformations_json, p_actor,
        p_version_record_id, p_head_record_id, p_event_id, p_storage_key
      );
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_platform_register_dataset_version_with_storage_and_lease(
    text, text, text, text, text, text, bigint, integer, jsonb, jsonb,
    text, text, text, text, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_platform_register_dataset_version_with_storage_and_lease(
    text, text, text, text, text, text, bigint, integer, jsonb, jsonb,
    text, text, text, text, text, uuid
) TO service_role;

-- Fence generic platform-record writes that add a T020 storage_key reference.
-- The record and its append-only event are written while the lease row remains
-- locked in this transaction.
CREATE OR REPLACE FUNCTION public.shoir_platform_upsert_record_with_dataset_lease(
    p_record_id text,
    p_workspace_key text,
    p_record_type text,
    p_entity_key text,
    p_payload jsonb,
    p_content_hash text,
    p_actor text,
    p_event_id text,
    p_dataset_id text,
    p_lease_token uuid
)
RETURNS TABLE (
    record_id text,
    version integer,
    content_hash text,
    created_at timestamptz,
    updated_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_storage_key text;
BEGIN
    IF p_lease_token IS NULL
       OR p_dataset_id IS NULL
       OR p_dataset_id !~ '^DS-[A-F0-9]{12,32}$'
       OR p_payload IS NULL
       OR jsonb_typeof(p_payload) <> 'object' THEN
        RAISE EXCEPTION 'Invalid dataset reference registration input.'
            USING ERRCODE = '22023';
    END IF;

    v_storage_key := p_payload->>'storage_key';
    IF v_storage_key IS NULL OR v_storage_key !~
       ('^' || p_workspace_key || '/' || p_dataset_id ||
        '/[0-9a-f]{64}\.csv$|^tmp/' || p_workspace_key || '/' ||
        p_dataset_id || '/[0-9a-f]{32}\.csv$') THEN
        RAISE EXCEPTION 'Dataset storage reference is invalid.'
            USING ERRCODE = '22023';
    END IF;

    PERFORM 1
      FROM public.shoir_dataset_storage_lifecycle_leases
     WHERE workspace_key = p_workspace_key
       AND dataset_id = p_dataset_id
       AND lease_token = p_lease_token
       AND lease_operation = 'register'
       AND actor_username_lc = lower(btrim(p_actor))
       AND expires_at > clock_timestamp()
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Dataset reference registration lease is no longer active.'
            USING ERRCODE = '55P03';
    END IF;

    RETURN QUERY
    SELECT saved.record_id, saved.version, saved.content_hash,
           saved.created_at, saved.updated_at
      FROM public.shoir_platform_upsert_record(
        p_record_id, p_workspace_key, p_record_type, p_entity_key,
        p_payload, p_content_hash, p_actor, p_event_id
      ) AS saved;
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_platform_upsert_record_with_dataset_lease(
    text, text, text, text, jsonb, text, text, text, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_platform_upsert_record_with_dataset_lease(
    text, text, text, text, jsonb, text, text, text, text, uuid
) TO service_role;

COMMENT ON FUNCTION public.shoir_dataset_storage_lease_renew(
    text, text, uuid, text, text, integer
) IS
    'Extend only an unexpired dataset Storage lease held by the exact token, operation and actor. Expired/stale holders cannot renew.';
COMMENT ON FUNCTION public.shoir_platform_register_dataset_version_with_storage_and_lease(
    text, text, text, text, text, text, bigint, integer, jsonb, jsonb,
    text, text, text, text, text, uuid
) IS
    'Atomically fence dataset version metadata registration with a live, locked finalize lease.';
COMMENT ON FUNCTION public.shoir_platform_upsert_record_with_dataset_lease(
    text, text, text, text, jsonb, text, text, text, text, uuid
) IS
    'Atomically fence a generic platform record/event Storage reference with a live, locked register lease.';

COMMIT;
