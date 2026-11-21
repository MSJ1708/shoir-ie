-- Atomic dataset version registry for the session-validated Shoir-IE Edge API.
-- Immutable versions and the current pointer are written in one transaction.
CREATE OR REPLACE FUNCTION public.shoir_platform_register_dataset_version(
    p_workspace_key text, p_dataset_id text, p_name text, p_source_name text,
    p_data_hash text, p_version_fingerprint text, p_row_count bigint,
    p_column_count integer, p_schema_json jsonb, p_transformations_json jsonb,
    p_actor text, p_version_record_id text, p_head_record_id text, p_event_id text
)
RETURNS TABLE (
    dataset_id text, version integer, data_hash text, version_fingerprint text,
    version_record_id text, registered_at timestamptz, created_new_version boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_head jsonb;
    v_existing_version jsonb;
    v_current_version integer := 0;
    v_new_version integer;
    v_version_key text;
    v_version_payload jsonb;
    v_head_payload jsonb;
    v_now timestamptz := now();
    v_version_record_id text;
BEGIN
    IF p_workspace_key IS NULL OR p_workspace_key !~ '^[0-9a-f]{32}$'
       OR p_dataset_id IS NULL OR p_dataset_id !~ '^DS-[A-F0-9]{12,32}$'
       OR p_name IS NULL OR btrim(p_name) = '' OR length(p_name) > 200
       OR p_source_name IS NULL OR length(p_source_name) > 500
       OR p_data_hash IS NULL OR p_data_hash !~ '^[0-9a-f]{64}$'
       OR p_version_fingerprint IS NULL OR p_version_fingerprint !~ '^[0-9a-f]{64}$'
       OR p_row_count IS NULL OR p_row_count < 0 OR p_row_count > 100000000
       OR p_column_count IS NULL OR p_column_count < 0 OR p_column_count > 5000
       OR p_schema_json IS NULL OR jsonb_typeof(p_schema_json) <> 'object'
       OR pg_column_size(p_schema_json) > 65536
       OR p_transformations_json IS NULL OR jsonb_typeof(p_transformations_json) <> 'array'
       OR jsonb_array_length(p_transformations_json) > 50
       OR pg_column_size(p_transformations_json) > 16384
       OR p_actor IS NULL OR btrim(p_actor) = '' OR length(p_actor) > 128
       OR p_version_record_id IS NULL OR p_version_record_id !~ '^SPR-[A-F0-9]{24}$'
       OR p_head_record_id IS NULL OR p_head_record_id !~ '^SPR-[A-F0-9]{24}$'
       OR p_event_id IS NULL OR p_event_id !~ '^SPE-[A-F0-9]{24}$' THEN
        RAISE EXCEPTION 'Invalid dataset version registration input.' USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_workspace_key || '|' || p_dataset_id, 0));

    SELECT payload_json INTO v_head
      FROM public.shoir_platform_records
     WHERE workspace_key = p_workspace_key
       AND record_type = 'dataset'
       AND entity_key = p_dataset_id
     FOR UPDATE;

    IF v_head IS NOT NULL THEN
        IF v_head->>'version_fingerprint' = p_version_fingerprint THEN
            RETURN QUERY SELECT p_dataset_id,
                COALESCE((v_head->>'version')::integer, 1),
                v_head->>'data_hash', v_head->>'version_fingerprint',
                v_head->>'version_record_id',
                COALESCE((v_head->>'registered_at')::timestamptz, v_now), false;
            RETURN;
        END IF;
        v_current_version := COALESCE((v_head->>'version')::integer, 0);
    END IF;

    v_new_version := v_current_version + 1;
    v_version_key := p_dataset_id || ':v' || v_new_version::text;
    v_version_payload := jsonb_build_object(
        'dataset_id', p_dataset_id, 'version', v_new_version,
        'name', p_name, 'source_name', p_source_name, 'data_hash', p_data_hash,
        'version_fingerprint', p_version_fingerprint, 'row_count', p_row_count,
        'column_count', p_column_count, 'schema', p_schema_json,
        'transformations', p_transformations_json,
        'parent_version', CASE WHEN v_current_version > 0 THEN v_current_version ELSE NULL END,
        'created_by', lower(btrim(p_actor)), 'registered_at', v_now
    );

    INSERT INTO public.shoir_platform_records (
        record_id, workspace_key, record_type, entity_key, payload_json,
        content_hash, version, created_at, updated_at
    ) VALUES (
        p_version_record_id, p_workspace_key, 'dataset_version', v_version_key,
        v_version_payload, p_version_fingerprint, 1, v_now, v_now
    ) ON CONFLICT (workspace_key, record_type, entity_key) DO NOTHING;

    SELECT payload_json, record_id INTO v_existing_version, v_version_record_id
      FROM public.shoir_platform_records
     WHERE workspace_key = p_workspace_key
       AND record_type = 'dataset_version'
       AND entity_key = v_version_key;

    IF v_existing_version IS NULL
       OR v_existing_version->>'version_fingerprint' IS DISTINCT FROM p_version_fingerprint THEN
        RAISE EXCEPTION 'Dataset version key conflicts with different content.'
            USING ERRCODE = '23505';
    END IF;

    v_head_payload := jsonb_build_object(
        'dataset_id', p_dataset_id, 'name', p_name, 'source_name', p_source_name,
        'version', v_new_version, 'data_hash', p_data_hash,
        'version_fingerprint', p_version_fingerprint, 'row_count', p_row_count,
        'column_count', p_column_count, 'schema', p_schema_json,
        'transformations', p_transformations_json,
        'version_record_id', v_version_record_id,
        'registered_at', v_now, 'updated_at', v_now
    );

    INSERT INTO public.shoir_platform_records (
        record_id, workspace_key, record_type, entity_key, payload_json,
        content_hash, version, created_at, updated_at
    ) VALUES (
        p_head_record_id, p_workspace_key, 'dataset', p_dataset_id,
        v_head_payload, p_version_fingerprint, 1, v_now, v_now
    ) ON CONFLICT (workspace_key, record_type, entity_key)
    DO UPDATE SET payload_json = EXCLUDED.payload_json,
                  content_hash = EXCLUDED.content_hash,
                  version = public.shoir_platform_records.version + 1,
                  updated_at = EXCLUDED.updated_at;

    INSERT INTO public.shoir_platform_events (
        event_id, workspace_key, event_type, actor, entity_key, payload_json, created_at
    ) VALUES (
        p_event_id, p_workspace_key, 'dataset_version_registered',
        lower(btrim(p_actor)), p_dataset_id,
        jsonb_build_object(
            'dataset_id', p_dataset_id, 'version', v_new_version,
            'data_hash', p_data_hash, 'version_fingerprint', p_version_fingerprint,
            'version_record_id', v_version_record_id
        ), v_now
    );

    RETURN QUERY SELECT p_dataset_id, v_new_version, p_data_hash,
        p_version_fingerprint, v_version_record_id, v_now, true;
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_platform_register_dataset_version(
    text, text, text, text, text, text, bigint, integer, jsonb, jsonb, text, text, text, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_platform_register_dataset_version(
    text, text, text, text, text, text, bigint, integer, jsonb, jsonb, text, text, text, text
) TO service_role;
