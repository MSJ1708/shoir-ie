-- Close a disposable/team organization without deleting its immutable audit trail.
-- The operation is owner-only, revokes invitations, archives workspaces and
-- removes active memberships. Historical rows remain available for retention.
CREATE OR REPLACE FUNCTION public.shoir_org_close(
    p_actor text,
    p_organization_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_owner text;
    v_revoked_invitations integer := 0;
    v_archived_workspaces integer := 0;
    v_removed_memberships integer := 0;
BEGIN
    IF p_organization_id IS NULL OR v_actor IS NULL OR v_actor = '' OR length(v_actor) > 128 THEN
        RAISE EXCEPTION 'Invalid organization close input.' USING ERRCODE = '22023';
    END IF;

    SELECT owner_username_lc
      INTO v_owner
      FROM public.shoir_organizations
     WHERE organization_id = p_organization_id
       AND org_type = 'team'
       AND status = 'active'
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active team organization was not found.' USING ERRCODE = '42501';
    END IF;
    IF v_owner IS DISTINCT FROM v_actor THEN
        RAISE EXCEPTION 'Only the current organization owner may close the organization.' USING ERRCODE = '42501';
    END IF;

    UPDATE public.shoir_organization_invitations
       SET revoked_at = now()
     WHERE organization_id = p_organization_id
       AND used_at IS NULL
       AND revoked_at IS NULL;
    GET DIAGNOSTICS v_revoked_invitations = ROW_COUNT;

    UPDATE public.shoir_organization_workspaces
       SET status = 'archived',
           updated_at = now()
     WHERE organization_id = p_organization_id
       AND status = 'active';
    GET DIAGNOSTICS v_archived_workspaces = ROW_COUNT;

    UPDATE public.shoir_organization_memberships
       SET status = 'removed',
           updated_at = now()
     WHERE organization_id = p_organization_id
       AND status = 'active';
    GET DIAGNOSTICS v_removed_memberships = ROW_COUNT;

    UPDATE public.shoir_organizations
       SET status = 'closed',
           updated_at = now()
     WHERE organization_id = p_organization_id;

    INSERT INTO public.shoir_organization_audit_events(
        organization_id,
        actor_username_lc,
        event_type,
        payload_json
    ) VALUES (
        p_organization_id,
        v_actor,
        'organization.closed',
        jsonb_build_object(
            'revoked_invitations', v_revoked_invitations,
            'archived_workspaces', v_archived_workspaces,
            'removed_memberships', v_removed_memberships
        )
    );

    RETURN jsonb_build_object(
        'ok', true,
        'status', 'closed',
        'revoked_invitations', v_revoked_invitations,
        'archived_workspaces', v_archived_workspaces,
        'removed_memberships', v_removed_memberships
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_org_close(text, uuid)
FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_close(text, uuid)
TO service_role;
