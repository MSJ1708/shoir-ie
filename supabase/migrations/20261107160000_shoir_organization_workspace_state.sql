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

-- Cover the organization audit/member/invitation/workspace foreign keys reported
-- by the staging performance advisor. These indexes are separate from the
-- organization-leading list indexes and support account deletion checks/joins.
-- Include team owners as well as the partial personal-owner index. A partial index
-- cannot cover the complete owner foreign key when an account is referenced by
-- a team organization.
CREATE INDEX IF NOT EXISTS shoir_org_owner_username_fk
    ON public.shoir_organizations(owner_username_lc);

CREATE INDEX IF NOT EXISTS shoir_org_audit_actor_fk
    ON public.shoir_organization_audit_events(actor_username_lc);
CREATE INDEX IF NOT EXISTS shoir_org_audit_subject_fk
    ON public.shoir_organization_audit_events(subject_username_lc);
CREATE INDEX IF NOT EXISTS shoir_org_invitation_accepted_by_fk
    ON public.shoir_organization_invitations(accepted_by_username_lc);
CREATE INDEX IF NOT EXISTS shoir_org_invitation_created_by_fk
    ON public.shoir_organization_invitations(created_by_username_lc);

CREATE INDEX IF NOT EXISTS shoir_org_invitation_organization_fk
    ON public.shoir_organization_invitations(organization_id);
CREATE INDEX IF NOT EXISTS shoir_org_membership_invited_by_fk
    ON public.shoir_organization_memberships(invited_by_username_lc);
CREATE INDEX IF NOT EXISTS shoir_org_workspace_created_by_fk
    ON public.shoir_organization_workspaces(created_by_username_lc);
CREATE INDEX IF NOT EXISTS shoir_org_workspace_state_updated_by_fk
    ON public.shoir_organization_workspace_states(updated_by_username_lc);

-- Row triggers cannot stop TRUNCATE. Keep the service key limited to reading
-- and appending audit history; also remove unneeded table-level privileges.
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE public.shoir_organization_audit_events
FROM service_role;

ALTER TABLE public.shoir_organization_workspace_states ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.shoir_organization_workspace_states
FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.shoir_org_workspace_state_load(
    p_actor text,
    p_organization_id uuid,
    p_workspace_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
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
    p_expected_revision bigint
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
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
       OR p_state_json IS NULL OR octet_length(p_state_json) > 8388608
       OR p_expected_revision IS NULL OR p_expected_revision < 0 THEN
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

    -- A missing state accepts only revision 0. Existing state accepts only
    -- the exact revision loaded by the caller. Keep the two paths separate:
    -- an INSERT ... SELECT with a revision predicate would emit no source row
    -- for revisions greater than zero and could never reach ON CONFLICT.
    IF p_expected_revision = 0 THEN
        INSERT INTO public.shoir_organization_workspace_states(
            workspace_key, state_json, revision, updated_by_username_lc, updated_at
        ) VALUES (
            v_workspace_key, p_state_json, 1, v_actor, now()
        )
        ON CONFLICT (workspace_key) DO NOTHING
        RETURNING revision, updated_at INTO v_revision, v_updated_at;
    ELSE
        UPDATE public.shoir_organization_workspace_states
           SET state_json = p_state_json,
               revision = revision + 1,
               updated_by_username_lc = v_actor,
               updated_at = now()
         WHERE workspace_key = v_workspace_key
           AND revision = p_expected_revision
        RETURNING revision, updated_at INTO v_revision, v_updated_at;
    END IF;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Shared workspace changed since it was loaded. Reload before saving.'
            USING ERRCODE = '40001';
    END IF;

    INSERT INTO public.shoir_organization_audit_events(
        organization_id,
        actor_username_lc,
        event_type,
        payload_json
    ) VALUES (
        p_organization_id,
        v_actor,
        'organization.workspace_state_saved',
        jsonb_build_object(
            'workspace_id', p_workspace_id,
            'revision', v_revision,
            'state_bytes', octet_length(p_state_json)
        )
    );

    RETURN jsonb_build_object(
        'ok', true,
        'revision', v_revision,
        'updated_at', v_updated_at,
        'workspace_key', v_workspace_key
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_org_workspace_state_load(text, uuid, uuid)
FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.shoir_org_workspace_state_save(text, uuid, uuid, text, bigint)
FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_workspace_state_load(text, uuid, uuid)
TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_workspace_state_save(text, uuid, uuid, text, bigint)
TO service_role;
