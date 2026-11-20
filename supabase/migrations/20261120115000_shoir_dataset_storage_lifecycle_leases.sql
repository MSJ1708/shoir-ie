BEGIN;

-- Serialize dataset Storage finalization, reference registration and orphan cleanup.
-- This table is private: callers use only the server-side SECURITY DEFINER RPCs.
CREATE TABLE public.shoir_dataset_storage_lifecycle_leases (
    workspace_key text NOT NULL
        CHECK (workspace_key ~ '^[0-9a-f]{32}$'),
    dataset_id text NOT NULL
        CHECK (dataset_id ~ '^DS-[A-F0-9]{12,32}$'),
    lease_token uuid NOT NULL,
    lease_operation text NOT NULL
        CHECK (lease_operation IN ('finalize', 'register', 'sweep')),
    actor_username_lc text NOT NULL
        CHECK (length(btrim(actor_username_lc)) BETWEEN 1 AND 128),
    acquired_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (workspace_key, dataset_id),
    CHECK (expires_at > acquired_at)
);

ALTER TABLE public.shoir_dataset_storage_lifecycle_leases
    ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.shoir_dataset_storage_lifecycle_leases
    FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.shoir_dataset_storage_lease_acquire(
    p_workspace_key text,
    p_dataset_id text,
    p_lease_token uuid,
    p_lease_operation text,
    p_actor_username_lc text,
    p_lease_seconds integer
)
RETURNS TABLE (acquired boolean, expires_at timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_expires_at timestamptz;
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
        RAISE EXCEPTION 'Invalid dataset storage lifecycle lease input.'
            USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.shoir_dataset_storage_lifecycle_leases AS current_lease (
        workspace_key,
        dataset_id,
        lease_token,
        lease_operation,
        actor_username_lc,
        acquired_at,
        expires_at
    )
    VALUES (
        p_workspace_key,
        p_dataset_id,
        p_lease_token,
        p_lease_operation,
        lower(btrim(p_actor_username_lc)),
        clock_timestamp(),
        clock_timestamp() + make_interval(secs => p_lease_seconds)
    )
    ON CONFLICT (workspace_key, dataset_id)
    DO UPDATE SET
        lease_token = EXCLUDED.lease_token,
        lease_operation = EXCLUDED.lease_operation,
        actor_username_lc = EXCLUDED.actor_username_lc,
        acquired_at = EXCLUDED.acquired_at,
        expires_at = EXCLUDED.expires_at
    WHERE current_lease.expires_at <= clock_timestamp()
    RETURNING current_lease.expires_at INTO v_expires_at;

    IF FOUND THEN
        RETURN QUERY SELECT TRUE, v_expires_at;
        RETURN;
    END IF;

    SELECT current_lease.expires_at
      INTO v_expires_at
      FROM public.shoir_dataset_storage_lifecycle_leases AS current_lease
     WHERE current_lease.workspace_key = p_workspace_key
       AND current_lease.dataset_id = p_dataset_id;

    RETURN QUERY SELECT FALSE, v_expires_at;
END;
$function$;

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
    v_updated integer;
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
       AND expires_at > clock_timestamp();

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated = 1;
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_dataset_storage_lease_release(
    p_workspace_key text,
    p_dataset_id text,
    p_lease_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_deleted integer;
BEGIN
    IF p_workspace_key IS NULL
       OR p_workspace_key !~ '^[0-9a-f]{32}$'
       OR p_dataset_id IS NULL
       OR p_dataset_id !~ '^DS-[A-F0-9]{12,32}$'
       OR p_lease_token IS NULL THEN
        RAISE EXCEPTION 'Invalid dataset storage lifecycle lease release input.'
            USING ERRCODE = '22023';
    END IF;

    DELETE FROM public.shoir_dataset_storage_lifecycle_leases
     WHERE workspace_key = p_workspace_key
       AND dataset_id = p_dataset_id
       AND lease_token = p_lease_token;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted = 1;
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_dataset_storage_lease_acquire(
    text, text, uuid, text, text, integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_dataset_storage_lease_acquire(
    text, text, uuid, text, text, integer
) TO service_role;

REVOKE ALL ON FUNCTION public.shoir_dataset_storage_lease_renew(
    text, text, uuid, text, text, integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_dataset_storage_lease_renew(
    text, text, uuid, text, text, integer
) TO service_role;

REVOKE ALL ON FUNCTION public.shoir_dataset_storage_lease_release(
    text, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_dataset_storage_lease_release(
    text, text, uuid
) TO service_role;

COMMENT ON TABLE public.shoir_dataset_storage_lifecycle_leases IS
    'Private server-only fencing leases serializing dataset Storage finalization, reference registration and cleanup.';
COMMENT ON FUNCTION public.shoir_dataset_storage_lease_acquire(
    text, text, uuid, text, text, integer
) IS
    'Atomically acquire a workspace/dataset Storage lifecycle lease for finalization, reference registration or cleanup; otherwise report the active lease expiry. Only the session-validated Edge Function service role may execute.';
COMMENT ON FUNCTION public.shoir_dataset_storage_lease_renew(
    text, text, uuid, text, text, integer
) IS
    'Renew only a live lease held by the matching workspace/dataset, token, operation and actor; stale or expired lease holders cannot renew it.';
COMMENT ON FUNCTION public.shoir_dataset_storage_lease_release(
    text, text, uuid
) IS
    'Release only the matching workspace/dataset lease token; stale holders cannot release a newer lease.';

COMMIT;
