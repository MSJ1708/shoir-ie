-- Private staging dataset file storage and metadata linkage.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'shoir-industrial-datasets',
    'shoir-industrial-datasets',
    false,
    52428800,
    ARRAY['text/csv', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    public = false,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS private_subscription_payment_proofs_only_server
    ON storage.objects;
CREATE POLICY private_subscription_payment_proofs_only_server
    ON storage.objects
    FOR ALL
    TO anon, authenticated
    USING (bucket_id <> 'subscription-payment-proofs'
           AND bucket_id <> 'shoir-industrial-datasets')
    WITH CHECK (bucket_id <> 'subscription-payment-proofs'
                AND bucket_id <> 'shoir-industrial-datasets');

CREATE OR REPLACE FUNCTION public.shoir_platform_register_dataset_version_with_storage(
    p_workspace_key text, p_dataset_id text, p_name text, p_source_name text,
    p_data_hash text, p_version_fingerprint text, p_row_count bigint,
    p_column_count integer, p_schema_json jsonb, p_transformations_json jsonb,
    p_actor text, p_version_record_id text, p_head_record_id text,
    p_event_id text, p_storage_key text
)
RETURNS TABLE (
    dataset_id text, version integer, data_hash text, version_fingerprint text,
    version_record_id text, registered_at timestamptz, created_new_version boolean
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_result record;
    v_version_key text;
BEGIN
    IF p_storage_key IS NULL
       OR p_storage_key <> p_workspace_key || '/' || p_dataset_id || '/' || p_data_hash || '.csv'
       OR length(p_storage_key) > 160
       OR p_storage_key ~ '(^/|\.\.|//|\\)' THEN
        RAISE EXCEPTION 'Dataset storage key is invalid.' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_result
    FROM public.shoir_platform_register_dataset_version(
        p_workspace_key, p_dataset_id, p_name, p_source_name,
        p_data_hash, p_version_fingerprint, p_row_count, p_column_count,
        p_schema_json, p_transformations_json, p_actor,
        p_version_record_id, p_head_record_id, p_event_id
    );

    v_version_key := p_dataset_id || ':v' || v_result.version::text;

    UPDATE public.shoir_platform_records
       SET payload_json = payload_json || jsonb_build_object('storage_key', p_storage_key),
           updated_at = now()
     WHERE workspace_key = p_workspace_key
       AND record_type = 'dataset_version'
       AND entity_key = v_version_key;

    UPDATE public.shoir_platform_records
       SET payload_json = payload_json || jsonb_build_object('storage_key', p_storage_key),
           updated_at = now()
     WHERE workspace_key = p_workspace_key
       AND record_type = 'dataset'
       AND entity_key = p_dataset_id;

    UPDATE public.shoir_platform_events
       SET payload_json = payload_json || jsonb_build_object('storage_key', p_storage_key)
     WHERE workspace_key = p_workspace_key
       AND event_type = 'dataset_version_registered'
       AND entity_key = p_dataset_id
       AND payload_json->>'version' = v_result.version::text;

    RETURN QUERY SELECT v_result.dataset_id, v_result.version, v_result.data_hash,
        v_result.version_fingerprint, v_result.version_record_id,
        v_result.registered_at, v_result.created_new_version;
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_platform_register_dataset_version_with_storage(
    text,text,text,text,text,text,bigint,integer,jsonb,jsonb,text,text,text,text,text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_platform_register_dataset_version_with_storage(
    text,text,text,text,text,text,bigint,integer,jsonb,jsonb,text,text,text,text,text
) TO service_role;
