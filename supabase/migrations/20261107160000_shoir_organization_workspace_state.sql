-- Shared organization workspace state with authorization-checked optimistic writes.
-- Personal shoir_workspace_states(username_lc) remains unchanged.
CREATE TABLE public.shoir_organization_workspace_states (
    workspace_key text PRIMARY KEY
        REFERENCES public.shoir_organization_workspaces(workspace_key) ON DELETE RESTRICT,
    state_json text NOT NULL
        CHECK (
            octet_length(state_json) <= 8388608
            AND jsonb_typeof(state_json::jsonb) = 'object'
        ),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_by_username_lc text NOT NULL
        REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX shoir_org_workspace_states_updated
    ON public.shoir_organization_workspace_states(updated_at DESC);

ALTER TABLE public.shoir_organization_workspace_states ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.shoir_organization_workspace_states
FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.shoir_organization_workspace_states
TO service_role;
REVOKE DELETE ON TABLE public.shoir_organization_workspace_states
FROM service_role;

CREATE OR REPLACE FUNCTION public.shoir_org_workspace_state_load(
    p_actor text,
    p_organization_id uuid,
    p_workspace_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_workspace_key text;
    v_state text;
    v_revision bigint;
    v_updated_at timestamptz;
BEGIN
    IF p_organization_id IS NULL OR p_workspace_id IS NULL
       OR v_actor IS NULL OR v_actor = '' OR length(v_actor) > 128 THEN
        RAISE EXCEPTION 'Invalid organization workspace load input.' USING ERRCODE = '22023';
    END IF;

    -- All membership/workspace mutation RPCs lock this organization FOR UPDATE.
    -- Holding a shared lock prevents removal, suspension, archive or closure from
    -- racing this authorization check and state read.
    PERFORM 1 FROM public.shoir_organizations
     WHERE organization_id = p_organization_id AND status = 'active'
     FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active organization was not found.' USING ERRCODE = '42501';
    END IF;

    SELECT workspace_key INTO v_workspace_key
      FROM public.shoir_org_resolve_workspace(
          v_actor, p_organization_id, p_workspace_id, 'read'
      );
    SELECT state_json, revision, updated_at
      INTO v_state, v_revision, v_updated_at
      FROM public.shoir_organization_workspace_states
     WHERE workspace_key = v_workspace_key;

    RETURN jsonb_build_object(
        'state_json', v_state,
        'revision', COALESCE(v_revision, 0),
        'updated_at', v_updated_at,
        'workspace_key', v_workspace_key
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_workspace_state_save(
    p_actor text,
    p_organization_id uuid,
    p_workspace_id uuid,
    p_state_json text,
    p_expected_revision bigint DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_workspace_key text;
    v_json jsonb;
    v_revision bigint;
    v_updated_at timestamptz;
BEGIN
    IF p_organization_id IS NULL OR p_workspace_id IS NULL
       OR v_actor IS NULL OR v_actor = '' OR length(v_actor) > 128
       OR p_state_json IS NULL OR octet_length(p_state_json) > 1048576
       OR (p_expected_revision IS NOT NULL AND p_expected_revision < 0) THEN
        RAISE EXCEPTION 'Invalid organization workspace save input.' USING ERRCODE = '22023';
    END IF;

    BEGIN
        v_json := p_state_json::jsonb;
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'Workspace state must be valid JSON.' USING ERRCODE = '22023';
    END;
    IF jsonb_typeof(v_json) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'Workspace state must be a JSON object.' USING ERRCODE = '22023';
    END IF;

    -- Keep authorization and the conditional upsert in one transaction. A
    -- concurrent role removal or workspace archive must wait for this write.
    PERFORM 1 FROM public.shoir_organizations
     WHERE organization_id = p_organization_id AND status = 'active'
     FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active organization was not found.' USING ERRCODE = '42501';
    END IF;

    SELECT workspace_key INTO v_workspace_key
      FROM public.shoir_org_resolve_workspace(
          v_actor, p_organization_id, p_workspace_id, 'write'
      );

    INSERT INTO public.shoir_organization_workspace_states(
        workspace_key, state_json, revision, updated_by_username_lc, updated_at
    ) VALUES (
        v_workspace_key, p_state_json, 1, v_actor, now()
    )
    ON CONFLICT (workspace_key) DO UPDATE
       SET state_json = EXCLUDED.state_json,
           revision = public.shoir_organization_workspace_states.revision + 1,
           updated_by_username_lc = EXCLUDED.updated_by_username_lc,
           updated_at = now()
     WHERE p_expected_revision IS NULL
        OR public.shoir_organization_workspace_states.revision = p_expected_revision
    RETURNING revision, updated_at INTO v_revision, v_updated_at;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Shared workspace changed since it was loaded. Reload before saving.'
            USING ERRCODE = '40001';
    END IF;

    RETURN jsonb_build_object(
        'ok', true,
        'revision', v_revision,
        'updated_at', v_updated_at,
        'workspace_key', v_workspace_key
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_org_workspace_state_load(text, uuid, uuid)
FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_workspace_state_save(text, uuid, uuid, text, bigint)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_org_workspace_state_load(text, uuid, uuid)
TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_workspace_state_save(text, uuid, uuid, text, bigint)
TO service_role;
