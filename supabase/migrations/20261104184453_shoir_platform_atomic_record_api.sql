-- Source for staging migration 20261104184453_shoir_platform_atomic_record_api.
-- Applied only to Supabase staging project hfhrosthswcybccepmak.
-- Atomic upsert/version/event contract for session-scoped platform records.
CREATE OR REPLACE FUNCTION public.shoir_platform_upsert_record(
    p_record_id text,
    p_workspace_key text,
    p_record_type text,
    p_entity_key text,
    p_payload jsonb,
    p_content_hash text,
    p_actor text,
    p_event_id text
)
RETURNS TABLE (record_id text, version integer, content_hash text, created_at timestamptz, updated_at timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_record_id text;
    v_version integer;
    v_content_hash text;
    v_created_at timestamptz;
    v_updated_at timestamptz;
BEGIN
    IF p_record_id IS NULL OR p_record_id !~ '^SPR-[A-F0-9]{24}$'
       OR p_workspace_key IS NULL OR p_workspace_key !~ '^[0-9a-f]{32}$'
       OR p_record_type IS NULL OR p_record_type !~ '^[a-z][a-z0-9_.-]{0,79}$'
       OR p_entity_key IS NULL OR btrim(p_entity_key) = '' OR length(p_entity_key) > 240
       OR p_payload IS NULL OR jsonb_typeof(p_payload) <> 'object' OR pg_column_size(p_payload) > 262144
       OR p_content_hash IS NULL OR p_content_hash !~ '^[0-9a-f]{64}$'
       OR p_actor IS NULL OR btrim(p_actor) = '' OR length(p_actor) > 128
       OR p_event_id IS NULL OR p_event_id !~ '^SPE-[A-F0-9]{24}$' THEN
        RAISE EXCEPTION 'Invalid platform record input.' USING ERRCODE = '22023';
    END IF;
    INSERT INTO public.shoir_platform_records AS current_record
      (record_id,workspace_key,record_type,entity_key,payload_json,content_hash,version,created_at,updated_at)
    VALUES (p_record_id,p_workspace_key,p_record_type,p_entity_key,p_payload,p_content_hash,1,now(),now())
    ON CONFLICT (workspace_key,record_type,entity_key)
    DO UPDATE SET
      payload_json=EXCLUDED.payload_json,
      content_hash=EXCLUDED.content_hash,
      version=CASE WHEN current_record.content_hash IS DISTINCT FROM EXCLUDED.content_hash THEN current_record.version+1 ELSE current_record.version END,
      updated_at=CASE WHEN current_record.content_hash IS DISTINCT FROM EXCLUDED.content_hash THEN now() ELSE current_record.updated_at END
    RETURNING current_record.record_id,current_record.version,current_record.content_hash,current_record.created_at,current_record.updated_at
    INTO v_record_id,v_version,v_content_hash,v_created_at,v_updated_at;
    INSERT INTO public.shoir_platform_events(event_id,workspace_key,event_type,actor,entity_key,payload_json,created_at)
    VALUES (p_event_id,p_workspace_key,'platform_record_saved',lower(btrim(p_actor)),p_entity_key,
      jsonb_build_object('record_id',v_record_id,'record_type',p_record_type,'entity_key',p_entity_key,'version',v_version,'content_hash',v_content_hash),now());
    RETURN QUERY SELECT v_record_id,v_version,v_content_hash,v_created_at,v_updated_at;
END;
$function$;
REVOKE ALL ON FUNCTION public.shoir_platform_upsert_record(text,text,text,text,jsonb,text,text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_platform_upsert_record(text,text,text,text,jsonb,text,text,text) TO service_role;
COMMENT ON FUNCTION public.shoir_platform_upsert_record(text,text,text,text,jsonb,text,text,text)
IS 'Session-validated Edge Function only: atomically upsert a workspace-scoped platform record, version changed content, and append an event.';
