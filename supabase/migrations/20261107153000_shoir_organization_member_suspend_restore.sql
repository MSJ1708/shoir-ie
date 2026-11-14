-- Controlled member suspension/restoration for team organizations.
-- Existing session tokens remain valid cryptographically, but membership checks
-- deny organization access while status = 'suspended'.
CREATE OR REPLACE FUNCTION public.shoir_org_member_suspend(
    p_actor text,
    p_organization_id uuid,
    p_target_username_lc text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_target text := lower(btrim(p_target_username_lc));
    v_org_type text;
    v_actor_role text;
    v_target_role text;
    v_target_status text;
BEGIN
    IF p_organization_id IS NULL
       OR v_actor IS NULL OR v_actor = ''
       OR v_target IS NULL OR v_target = ''
       OR length(v_actor) > 128 OR length(v_target) > 128 THEN
        RAISE EXCEPTION 'Invalid organization member suspension input.' USING ERRCODE = '22023';
    END IF;

    SELECT org_type INTO v_org_type
      FROM public.shoir_organizations
     WHERE organization_id = p_organization_id
       AND status = 'active'
     FOR UPDATE;
    IF v_org_type IS DISTINCT FROM 'team' THEN
        RAISE EXCEPTION 'Active team organization was not found.' USING ERRCODE = '42501';
    END IF;

    SELECT role INTO v_actor_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id
       AND username_lc = v_actor
       AND status = 'active'
     FOR UPDATE;
    SELECT role, status
      INTO v_target_role, v_target_status
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id
       AND username_lc = v_target
     FOR UPDATE;

    IF v_actor_role IS NULL
       OR v_actor_role NOT IN ('owner','admin')
       OR v_target_role IS NULL
       OR v_target_role = 'owner'
       OR v_target_status IS DISTINCT FROM 'active'
       OR (v_target_role = 'admin' AND v_actor_role <> 'owner') THEN
        RAISE EXCEPTION 'Organization member suspension permission denied.' USING ERRCODE = '42501';
    END IF;

    UPDATE public.shoir_organization_memberships
       SET status = 'suspended',
           updated_at = now()
     WHERE organization_id = p_organization_id
       AND username_lc = v_target;

    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, subject_username_lc,
        event_type, payload_json
    ) VALUES (
        p_organization_id, v_actor, v_target,
        'organization.member_suspended',
        jsonb_build_object('previous_status', v_target_status, 'role', v_target_role)
    );

    RETURN jsonb_build_object('ok', true, 'status', 'suspended');
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_member_restore(
    p_actor text,
    p_organization_id uuid,
    p_target_username_lc text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_target text := lower(btrim(p_target_username_lc));
    v_org_type text;
    v_actor_role text;
    v_target_role text;
    v_target_status text;
    v_account_active boolean;
BEGIN
    IF p_organization_id IS NULL
       OR v_actor IS NULL OR v_actor = ''
       OR v_target IS NULL OR v_target = ''
       OR length(v_actor) > 128 OR length(v_target) > 128 THEN
        RAISE EXCEPTION 'Invalid organization member restoration input.' USING ERRCODE = '22023';
    END IF;

    SELECT org_type INTO v_org_type
      FROM public.shoir_organizations
     WHERE organization_id = p_organization_id
       AND status = 'active'
     FOR UPDATE;
    IF v_org_type IS DISTINCT FROM 'team' THEN
        RAISE EXCEPTION 'Active team organization was not found.' USING ERRCODE = '42501';
    END IF;

    SELECT role INTO v_actor_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id
       AND username_lc = v_actor
       AND status = 'active'
     FOR UPDATE;
    SELECT role, status
      INTO v_target_role, v_target_status
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id
       AND username_lc = v_target
     FOR UPDATE;

    SELECT COALESCE(active, true)
      INTO v_account_active
      FROM public.shoir_accounts
     WHERE username_lc = v_target;

    IF v_actor_role IS NULL
       OR v_actor_role NOT IN ('owner','admin')
       OR v_target_role IS NULL
       OR v_target_role = 'owner'
       OR v_target_status IS DISTINCT FROM 'suspended'
       OR (v_target_role = 'admin' AND v_actor_role <> 'owner')
       OR v_account_active IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Organization member restoration permission denied or target account inactive.' USING ERRCODE = '42501';
    END IF;

    UPDATE public.shoir_organization_memberships
       SET status = 'active',
           updated_at = now()
     WHERE organization_id = p_organization_id
       AND username_lc = v_target;

    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, subject_username_lc,
        event_type, payload_json
    ) VALUES (
        p_organization_id, v_actor, v_target,
        'organization.member_restored',
        jsonb_build_object('previous_status', v_target_status, 'role', v_target_role)
    );

    RETURN jsonb_build_object('ok', true, 'status', 'active');
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_org_member_suspend(text, uuid, text)
FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.shoir_org_member_restore(text, uuid, text)
FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_member_suspend(text, uuid, text)
TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_member_restore(text, uuid, text)
TO service_role;
