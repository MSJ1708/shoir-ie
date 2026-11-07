-- Organization and shared-workspace tenancy for Shoir-IE.
-- Additive only: existing account-derived workspace keys remain valid and are
-- registered lazily as personal-workspace aliases. No customer records are
-- rewritten or moved by this migration.
CREATE TABLE public.shoir_organizations (
    organization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 2 AND 120),
    org_type text NOT NULL CHECK (org_type IN ('personal','team')),
    owner_username_lc text NOT NULL REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','closed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX shoir_organizations_one_personal_per_owner
    ON public.shoir_organizations(owner_username_lc)
    WHERE org_type = 'personal';

CREATE TABLE public.shoir_organization_memberships (
    organization_id uuid NOT NULL REFERENCES public.shoir_organizations(organization_id) ON DELETE RESTRICT,
    username_lc text NOT NULL REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    role text NOT NULL CHECK (role IN ('owner','admin','engineer','approver','viewer')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','removed')),
    invited_by_username_lc text REFERENCES public.shoir_accounts(username_lc) ON DELETE SET NULL,
    joined_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, username_lc)
);
CREATE UNIQUE INDEX shoir_org_memberships_one_owner
    ON public.shoir_organization_memberships(organization_id)
    WHERE role = 'owner';
CREATE INDEX shoir_org_memberships_user_active
    ON public.shoir_organization_memberships(username_lc, status, organization_id);

CREATE TABLE public.shoir_organization_invitations (
    invitation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES public.shoir_organizations(organization_id) ON DELETE RESTRICT,
    target_username_lc text NOT NULL CHECK (target_username_lc = lower(btrim(target_username_lc))),
    role text NOT NULL CHECK (role IN ('admin','engineer','approver','viewer')),
    token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_by_username_lc text NOT NULL REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    revoked_at timestamptz,
    accepted_by_username_lc text REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at),
    CHECK (used_at IS NULL OR revoked_at IS NULL)
);
CREATE INDEX shoir_org_invitations_pending
    ON public.shoir_organization_invitations(organization_id, target_username_lc, expires_at)
    WHERE used_at IS NULL AND revoked_at IS NULL;

CREATE TABLE public.shoir_organization_workspaces (
    workspace_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES public.shoir_organizations(organization_id) ON DELETE RESTRICT,
    display_name text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 120),
    name_key text NOT NULL CHECK (name_key = lower(btrim(name_key))),
    workspace_key text NOT NULL UNIQUE CHECK (workspace_key ~ '^[0-9a-f]{32}$'),
    legacy_workspace_key text UNIQUE CHECK (legacy_workspace_key IS NULL OR legacy_workspace_key ~ '^[0-9a-f]{32}$'),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_by_username_lc text NOT NULL REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, name_key)
);
CREATE INDEX shoir_org_workspaces_org_active
    ON public.shoir_organization_workspaces(organization_id, status, display_name);

CREATE TABLE public.shoir_organization_audit_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES public.shoir_organizations(organization_id) ON DELETE RESTRICT,
    actor_username_lc text NOT NULL REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    subject_username_lc text REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    event_type text NOT NULL CHECK (event_type ~ '^[a-z][a-z0-9_.-]{1,79}$'),
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload_json) = 'object' AND pg_column_size(payload_json) <= 16384),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX shoir_org_audit_events_org_time
    ON public.shoir_organization_audit_events(organization_id, created_at DESC);

-- Preserve every existing account as owner of a personal organization.
-- Existing SQLite/account workspace data is not rewritten; the exact old
-- account-derived key is lazily mapped to its personal workspace on first use.
INSERT INTO public.shoir_organizations (
    organization_id, display_name, org_type, owner_username_lc, status
)
SELECT gen_random_uuid(),
       left(a.username, 108) || ' Personal',
       'personal',
       a.username_lc,
       CASE WHEN COALESCE(a.active, true) THEN 'active' ELSE 'suspended' END
FROM public.shoir_accounts a
WHERE NOT EXISTS (
    SELECT 1 FROM public.shoir_organizations o
    WHERE o.org_type = 'personal' AND o.owner_username_lc = a.username_lc
);

INSERT INTO public.shoir_organization_memberships (
    organization_id, username_lc, role, status, joined_at
)
SELECT o.organization_id,
       o.owner_username_lc,
       'owner',
       o.status,
       CASE WHEN o.status = 'active' THEN now() ELSE NULL END
FROM public.shoir_organizations o
WHERE o.org_type = 'personal'
ON CONFLICT (organization_id, username_lc) DO NOTHING;

ALTER TABLE public.shoir_organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shoir_organization_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shoir_organization_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shoir_organization_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shoir_organization_audit_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.shoir_organizations,
    public.shoir_organization_memberships,
    public.shoir_organization_invitations,
    public.shoir_organization_workspaces,
    public.shoir_organization_audit_events
FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.shoir_organizations,
    public.shoir_organization_memberships,
    public.shoir_organization_invitations,
    public.shoir_organization_workspaces
TO service_role;
-- Organisation audit events are append-only for application roles. The service
-- role may read and append events, but cannot update or delete history.
GRANT SELECT, INSERT ON TABLE public.shoir_organization_audit_events
TO service_role;
REVOKE UPDATE, DELETE ON TABLE public.shoir_organization_audit_events
FROM service_role;

CREATE OR REPLACE FUNCTION public.shoir_org_audit_events_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    RAISE EXCEPTION 'Organization audit events are append-only.'
        USING ERRCODE = '55000';
    RETURN NULL;
END;
$function$;
REVOKE ALL ON FUNCTION public.shoir_org_audit_events_immutable()
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_org_audit_events_immutable()
TO service_role;

CREATE TRIGGER shoir_org_audit_events_no_update_delete
    BEFORE UPDATE OR DELETE ON public.shoir_organization_audit_events
    FOR EACH ROW
    EXECUTE FUNCTION public.shoir_org_audit_events_immutable();

CREATE POLICY shoir_organizations_deny_browser_roles
    ON public.shoir_organizations FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);
CREATE POLICY shoir_organization_memberships_deny_browser_roles
    ON public.shoir_organization_memberships FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);
CREATE POLICY shoir_organization_invitations_deny_browser_roles
    ON public.shoir_organization_invitations FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);
CREATE POLICY shoir_organization_workspaces_deny_browser_roles
    ON public.shoir_organization_workspaces FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);
CREATE POLICY shoir_organization_audit_events_deny_browser_roles
    ON public.shoir_organization_audit_events FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);

CREATE OR REPLACE FUNCTION public.shoir_org_create(
    p_actor text,
    p_display_name text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_org uuid;
    v_workspace uuid;
    v_workspace_key text;
    v_actor text := lower(btrim(p_actor));
    v_name text := btrim(p_display_name);
BEGIN
    IF v_actor IS NULL OR v_actor = '' OR length(v_actor) > 128
       OR v_name IS NULL OR length(v_name) < 2 OR length(v_name) > 120
       OR v_name ~ '[[:cntrl:]]' THEN
        RAISE EXCEPTION 'Invalid organization creation input.' USING ERRCODE = '22023';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.shoir_accounts
        WHERE username_lc = v_actor
          AND COALESCE(active, true)
          AND lower(COALESCE(tier, '')) LIKE '%enterprise%'
          AND subscription_expires_at > now()
    ) THEN
        RAISE EXCEPTION 'An active Enterprise subscription is required to create a team organization.'
            USING ERRCODE = '42501';
    END IF;
    INSERT INTO public.shoir_organizations(display_name, org_type, owner_username_lc)
    VALUES (v_name, 'team', v_actor)
    RETURNING organization_id INTO v_org;
    INSERT INTO public.shoir_organization_memberships(
        organization_id, username_lc, role, status, joined_at
    ) VALUES (v_org, v_actor, 'owner', 'active', now());
    v_workspace := gen_random_uuid();
    v_workspace_key := md5('shoir-org:' || v_org::text || ':' || v_workspace::text);
    INSERT INTO public.shoir_organization_workspaces(
        workspace_id, organization_id, display_name, name_key,
        workspace_key, created_by_username_lc
    ) VALUES (v_workspace, v_org, 'General', 'general', v_workspace_key, v_actor);
    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, event_type, payload_json
    ) VALUES (
        v_org, v_actor, 'organization.created',
        jsonb_build_object('organization_id', v_org, 'workspace_id', v_workspace)
    );
    RETURN jsonb_build_object(
        'organization_id', v_org,
        'display_name', v_name,
        'role', 'owner',
        'workspace_id', v_workspace,
        'workspace_name', 'General'
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_invitation_create(
    p_actor text, p_organization_id uuid, p_target_username_lc text,
    p_role text, p_token_hash text, p_expires_at timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_target text := lower(btrim(p_target_username_lc));
    v_role text := lower(btrim(p_role));
    v_actor_role text;
    v_org_type text;
    v_id uuid;
BEGIN
    IF p_organization_id IS NULL OR v_actor IS NULL OR v_actor = ''
       OR v_target IS NULL OR v_target = '' OR length(v_target) > 128
       OR v_target ~ '[[:space:][:cntrl:]]'
       OR v_role IS NULL OR v_role NOT IN ('admin','engineer','approver','viewer')
       OR p_token_hash IS NULL OR p_token_hash !~ '^[0-9a-f]{64}$'
       OR p_expires_at IS NULL OR p_expires_at <= now() OR p_expires_at > now() + interval '30 days' THEN
        RAISE EXCEPTION 'Invalid organization invitation input.' USING ERRCODE = '22023';
    END IF;
    SELECT org_type INTO v_org_type FROM public.shoir_organizations
    WHERE organization_id = p_organization_id AND status = 'active'
    FOR UPDATE;
    IF v_org_type IS DISTINCT FROM 'team' THEN
        RAISE EXCEPTION 'Invitations are available only for active team organizations.' USING ERRCODE = '42501';
    END IF;
    SELECT role INTO v_actor_role
    FROM public.shoir_organization_memberships
    WHERE organization_id = p_organization_id
      AND username_lc = v_actor AND status = 'active'
    FOR UPDATE;
    IF v_actor_role IS NULL OR v_actor_role NOT IN ('owner','admin')
       OR (v_role = 'admin' AND v_actor_role <> 'owner') THEN
        RAISE EXCEPTION 'Organization invitation permission denied.' USING ERRCODE = '42501';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.shoir_accounts
        WHERE username_lc = v_target AND COALESCE(active, true)
    ) THEN
        RAISE EXCEPTION 'Target active account was not found.' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.shoir_organization_memberships
        WHERE organization_id = p_organization_id AND username_lc = v_target AND status = 'active'
    ) THEN
        RAISE EXCEPTION 'Target account is already an active member.' USING ERRCODE = '23505';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.shoir_organization_invitations
        WHERE organization_id = p_organization_id
          AND target_username_lc = v_target
          AND used_at IS NULL AND revoked_at IS NULL
          AND expires_at > now()
    ) THEN
        RAISE EXCEPTION 'A pending invitation already exists for this account.'
            USING ERRCODE = '23505';
    END IF;
    INSERT INTO public.shoir_organization_invitations(
        organization_id, target_username_lc, role, token_hash,
        created_by_username_lc, expires_at
    ) VALUES (
        p_organization_id, v_target, v_role, p_token_hash, v_actor, p_expires_at
    ) RETURNING invitation_id INTO v_id;
    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, subject_username_lc, event_type, payload_json
    ) VALUES (
        p_organization_id, v_actor, v_target, 'organization.invitation_created',
        jsonb_build_object('invitation_id', v_id, 'role', v_role, 'expires_at', p_expires_at)
    );
    RETURN jsonb_build_object('invitation_id', v_id, 'expires_at', p_expires_at, 'role', v_role);
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_invitation_accept(
    p_actor text, p_token_hash text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_organization_id uuid;
    v_inv public.shoir_organization_invitations%ROWTYPE;
BEGIN
    IF v_actor IS NULL OR v_actor = '' OR length(v_actor) > 128
       OR p_token_hash IS NULL OR p_token_hash !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Invalid invitation acceptance input.' USING ERRCODE = '22023';
    END IF;

    -- Resolve the organization without locking the invitation first. All
    -- mutation paths lock organization -> invitation/membership rows, avoiding
    -- lock-order inversion with invitation revocation and membership changes.
    SELECT organization_id INTO v_organization_id
      FROM public.shoir_organization_invitations
     WHERE token_hash = p_token_hash;
    IF v_organization_id IS NULL THEN
        RAISE EXCEPTION 'Invitation is invalid, expired, used or assigned to another account.'
            USING ERRCODE = '42501';
    END IF;

    PERFORM 1
      FROM public.shoir_organizations o
      JOIN public.shoir_accounts owner
        ON owner.username_lc = o.owner_username_lc
     WHERE o.organization_id = v_organization_id
       AND o.org_type = 'team'
       AND o.status = 'active'
       AND COALESCE(owner.active, true)
       AND lower(COALESCE(owner.tier, '')) LIKE '%enterprise%'
       AND owner.subscription_expires_at > now()
     FOR UPDATE OF o, owner;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'An active Enterprise organization owner is required.'
            USING ERRCODE = '42501';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.shoir_accounts
        WHERE username_lc = v_actor AND COALESCE(active, true)
    ) THEN
        RAISE EXCEPTION 'Active account is required.' USING ERRCODE = '42501';
    END IF;

    SELECT * INTO v_inv
      FROM public.shoir_organization_invitations
     WHERE token_hash = p_token_hash
     FOR UPDATE;
    IF NOT FOUND OR v_inv.organization_id IS DISTINCT FROM v_organization_id
       OR v_inv.used_at IS NOT NULL OR v_inv.revoked_at IS NOT NULL
       OR v_inv.expires_at <= now() OR v_inv.target_username_lc <> v_actor THEN
        RAISE EXCEPTION 'Invitation is invalid, expired, used or assigned to another account.'
            USING ERRCODE = '42501';
    END IF;

    INSERT INTO public.shoir_organization_memberships(
        organization_id, username_lc, role, status,
        invited_by_username_lc, joined_at
    ) VALUES (
        v_inv.organization_id, v_actor, v_inv.role, 'active',
        v_inv.created_by_username_lc, now()
    )
    ON CONFLICT (organization_id, username_lc)
    DO UPDATE SET role = EXCLUDED.role, status = 'active',
                  invited_by_username_lc = EXCLUDED.invited_by_username_lc,
                  joined_at = now(), updated_at = now();

    UPDATE public.shoir_organization_invitations
       SET used_at = now(), accepted_by_username_lc = v_actor
     WHERE invitation_id = v_inv.invitation_id
       AND used_at IS NULL AND revoked_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invitation has already been consumed.' USING ERRCODE = '23505';
    END IF;

    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, subject_username_lc, event_type, payload_json
    ) VALUES (
        v_inv.organization_id, v_actor, v_actor, 'organization.invitation_accepted',
        jsonb_build_object('invitation_id', v_inv.invitation_id, 'role', v_inv.role)
    );
    RETURN jsonb_build_object('organization_id', v_inv.organization_id, 'role', v_inv.role);
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_member_role_set(
    p_actor text, p_organization_id uuid, p_target_username_lc text, p_role text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_target text := lower(btrim(p_target_username_lc));
    v_new_role text := lower(btrim(p_role));
    v_actor_role text;
    v_old_role text;
BEGIN
    IF p_organization_id IS NULL OR v_actor IS NULL OR v_target IS NULL
       OR v_new_role IS NULL OR v_new_role NOT IN ('admin','engineer','approver','viewer') THEN
        RAISE EXCEPTION 'Invalid organization role update input.' USING ERRCODE = '22023';
    END IF;
    PERFORM 1 FROM public.shoir_organizations
     WHERE organization_id = p_organization_id AND status = 'active'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active organization was not found.' USING ERRCODE = '42501';
    END IF;
    SELECT role INTO v_actor_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id AND username_lc = v_actor AND status = 'active'
     FOR UPDATE;
    IF v_actor_role IS NULL OR v_actor_role NOT IN ('owner','admin')
       OR (v_new_role = 'admin' AND v_actor_role <> 'owner') THEN
        RAISE EXCEPTION 'Organization role update permission denied.' USING ERRCODE = '42501';
    END IF;
    SELECT role INTO v_old_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id AND username_lc = v_target AND status = 'active'
     FOR UPDATE;
    IF v_old_role IS NULL OR v_old_role = 'owner' OR (v_old_role = 'admin' AND v_actor_role <> 'owner') THEN
        RAISE EXCEPTION 'Target membership cannot be changed by this actor.' USING ERRCODE = '42501';
    END IF;
    UPDATE public.shoir_organization_memberships
       SET role = v_new_role, updated_at = now()
     WHERE organization_id = p_organization_id AND username_lc = v_target;
    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, subject_username_lc, event_type, payload_json
    ) VALUES (
        p_organization_id, v_actor, v_target, 'organization.member_role_changed',
        jsonb_build_object('from', v_old_role, 'to', v_new_role)
    );
    RETURN jsonb_build_object('ok', true, 'role', v_new_role);
END;
$function$;


CREATE OR REPLACE FUNCTION public.shoir_org_owner_transfer(
    p_actor text, p_organization_id uuid, p_target_username_lc text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_target text := lower(btrim(p_target_username_lc));
    v_owner text;
    v_target_role text;
BEGIN
    IF p_organization_id IS NULL OR v_actor IS NULL OR v_actor = ''
       OR v_target IS NULL OR v_target = '' OR v_target = v_actor THEN
        RAISE EXCEPTION 'Invalid organization owner transfer input.' USING ERRCODE = '22023';
    END IF;
    SELECT owner_username_lc INTO v_owner
      FROM public.shoir_organizations
     WHERE organization_id = p_organization_id AND org_type = 'team' AND status = 'active'
     FOR UPDATE;
    IF v_owner IS DISTINCT FROM v_actor THEN
        RAISE EXCEPTION 'Only the current organization owner may transfer ownership.' USING ERRCODE = '42501';
    END IF;
    SELECT role INTO v_target_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id
       AND username_lc = v_target AND status = 'active'
     FOR UPDATE;
    IF NOT EXISTS (
        SELECT 1 FROM public.shoir_accounts
        WHERE username_lc = v_target
          AND COALESCE(active, true)
          AND lower(COALESCE(tier, '')) LIKE '%enterprise%'
          AND subscription_expires_at > now()
    ) THEN
        RAISE EXCEPTION 'New owner must have an active Enterprise subscription.'
            USING ERRCODE = '42501';
    END IF;
    IF v_target_role IS NULL OR v_target_role NOT IN ('admin','engineer','approver','viewer') THEN
        RAISE EXCEPTION 'The new owner must be an active organization member.' USING ERRCODE = '42501';
    END IF;
    UPDATE public.shoir_organization_memberships
       SET role = 'admin', updated_at = now()
     WHERE organization_id = p_organization_id AND username_lc = v_actor AND role = 'owner';
    UPDATE public.shoir_organization_memberships
       SET role = 'owner', updated_at = now()
     WHERE organization_id = p_organization_id AND username_lc = v_target AND status = 'active';
    UPDATE public.shoir_organizations
       SET owner_username_lc = v_target, updated_at = now()
     WHERE organization_id = p_organization_id;
    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, subject_username_lc, event_type, payload_json
    ) VALUES (
        p_organization_id, v_actor, v_target, 'organization.owner_transferred',
        jsonb_build_object('previous_owner', v_actor, 'new_owner', v_target)
    );
    RETURN jsonb_build_object('ok', true, 'previous_owner_role', 'admin', 'new_owner', v_target);
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_member_remove(
    p_actor text, p_organization_id uuid, p_target_username_lc text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_target text := lower(btrim(p_target_username_lc));
    v_actor_role text;
    v_target_role text;
BEGIN
    IF p_organization_id IS NULL OR v_actor IS NULL OR v_actor = ''
       OR v_target IS NULL OR v_target = '' THEN
        RAISE EXCEPTION 'Invalid organization member removal input.' USING ERRCODE = '22023';
    END IF;
    PERFORM 1 FROM public.shoir_organizations
     WHERE organization_id = p_organization_id AND status = 'active'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active organization was not found.' USING ERRCODE = '42501';
    END IF;
    SELECT role INTO v_actor_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id AND username_lc = v_actor AND status = 'active'
     FOR UPDATE;
    SELECT role INTO v_target_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id AND username_lc = v_target AND status = 'active'
     FOR UPDATE;
    IF v_actor_role IS NULL OR v_actor_role NOT IN ('owner','admin')
       OR v_target_role IS NULL OR v_target_role = 'owner'
       OR (v_target_role = 'admin' AND v_actor_role <> 'owner') THEN
        RAISE EXCEPTION 'Organization member removal permission denied.' USING ERRCODE = '42501';
    END IF;
    UPDATE public.shoir_organization_memberships
       SET status = 'removed', updated_at = now()
     WHERE organization_id = p_organization_id AND username_lc = v_target;
    UPDATE public.shoir_organization_invitations
       SET revoked_at = now()
     WHERE organization_id = p_organization_id AND target_username_lc = v_target
       AND used_at IS NULL AND revoked_at IS NULL;
    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, subject_username_lc, event_type
    ) VALUES (p_organization_id, v_actor, v_target, 'organization.member_removed');
    RETURN jsonb_build_object('ok', true);
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_workspace_create(
    p_actor text, p_organization_id uuid, p_display_name text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_name text := btrim(p_display_name);
    v_role text;
    v_workspace uuid;
    v_key text;
BEGIN
    IF p_organization_id IS NULL OR v_actor IS NULL OR v_name IS NULL
       OR length(v_name) < 1 OR length(v_name) > 120 OR v_name ~ '[[:cntrl:]]' THEN
        RAISE EXCEPTION 'Invalid organization workspace input.' USING ERRCODE = '22023';
    END IF;
    PERFORM 1 FROM public.shoir_organizations
     WHERE organization_id = p_organization_id AND status = 'active'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active organization was not found.' USING ERRCODE = '42501';
    END IF;
    SELECT m.role INTO v_role
      FROM public.shoir_organization_memberships m
     WHERE m.organization_id = p_organization_id
       AND m.username_lc = v_actor
       AND m.status = 'active'
     FOR UPDATE OF m;
    IF v_role IS NULL OR v_role NOT IN ('owner','admin') THEN
        RAISE EXCEPTION 'Organization workspace creation permission denied.' USING ERRCODE = '42501';
    END IF;
    v_workspace := gen_random_uuid();
    v_key := md5('shoir-org:' || p_organization_id::text || ':' || v_workspace::text);
    INSERT INTO public.shoir_organization_workspaces(
        workspace_id, organization_id, display_name, name_key,
        workspace_key, created_by_username_lc
    ) VALUES (
        v_workspace, p_organization_id, v_name, lower(v_name), v_key, v_actor
    );
    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, event_type, payload_json
    ) VALUES (
        p_organization_id, v_actor, 'organization.workspace_created',
        jsonb_build_object('workspace_id', v_workspace, 'workspace_name', v_name)
    );
    RETURN jsonb_build_object('workspace_id', v_workspace, 'workspace_name', v_name, 'workspace_key', v_key);
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_invitation_revoke(
    p_actor text, p_organization_id uuid, p_invitation_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_role text;
BEGIN
    IF p_organization_id IS NULL OR p_invitation_id IS NULL
       OR v_actor IS NULL OR v_actor = '' THEN
        RAISE EXCEPTION 'Invalid organization invitation revocation input.'
            USING ERRCODE = '22023';
    END IF;
    PERFORM 1
      FROM public.shoir_organizations
     WHERE organization_id = p_organization_id AND status = 'active'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active organization was not found.'
            USING ERRCODE = '42501';
    END IF;
    SELECT role INTO v_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id
       AND username_lc = v_actor AND status = 'active'
     FOR UPDATE;
    IF v_role IS NULL OR v_role NOT IN ('owner','admin') THEN
        RAISE EXCEPTION 'Organization invitation revocation permission denied.'
            USING ERRCODE = '42501';
    END IF;
    UPDATE public.shoir_organization_invitations
       SET revoked_at = now()
     WHERE invitation_id = p_invitation_id
       AND organization_id = p_organization_id
       AND used_at IS NULL AND revoked_at IS NULL
       AND expires_at > now();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invitation is missing, expired, used or already revoked.'
            USING ERRCODE = '42501';
    END IF;
    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, event_type, payload_json
    ) VALUES (
        p_organization_id, v_actor, 'organization.invitation_revoked',
        jsonb_build_object('invitation_id', p_invitation_id)
    );
    RETURN jsonb_build_object('ok', true, 'invitation_id', p_invitation_id);
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_workspace_archive(
    p_actor text, p_organization_id uuid, p_workspace_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_role text;
    v_name text;
    v_active_count integer;
BEGIN
    IF p_organization_id IS NULL OR p_workspace_id IS NULL
       OR v_actor IS NULL OR v_actor = '' THEN
        RAISE EXCEPTION 'Invalid organization workspace archive input.'
            USING ERRCODE = '22023';
    END IF;
    PERFORM 1 FROM public.shoir_organizations
     WHERE organization_id = p_organization_id AND status = 'active'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active organization was not found.' USING ERRCODE = '42501';
    END IF;
    SELECT role INTO v_role
      FROM public.shoir_organization_memberships
     WHERE organization_id = p_organization_id
       AND username_lc = v_actor AND status = 'active'
     FOR UPDATE;
    IF v_role IS NULL OR v_role NOT IN ('owner','admin') THEN
        RAISE EXCEPTION 'Organization workspace archive permission denied.'
            USING ERRCODE = '42501';
    END IF;
    SELECT display_name INTO v_name
      FROM public.shoir_organization_workspaces
     WHERE workspace_id = p_workspace_id
       AND organization_id = p_organization_id
       AND status = 'active'
     FOR UPDATE;
    IF v_name IS NULL THEN
        RAISE EXCEPTION 'Active organization workspace was not found.'
            USING ERRCODE = '42501';
    END IF;
    SELECT count(*) INTO v_active_count
      FROM public.shoir_organization_workspaces
     WHERE organization_id = p_organization_id AND status = 'active';
    IF v_active_count <= 1 THEN
        RAISE EXCEPTION 'The last active organization workspace cannot be archived.'
            USING ERRCODE = '23514';
    END IF;
    UPDATE public.shoir_organization_workspaces
       SET status = 'archived', updated_at = now()
     WHERE workspace_id = p_workspace_id AND organization_id = p_organization_id;
    INSERT INTO public.shoir_organization_audit_events(
        organization_id, actor_username_lc, event_type, payload_json
    ) VALUES (
        p_organization_id, v_actor, 'organization.workspace_archived',
        jsonb_build_object('workspace_id', p_workspace_id, 'workspace_name', v_name)
    );
    RETURN jsonb_build_object('ok', true, 'workspace_id', p_workspace_id);
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_resolve_workspace(
    p_actor text, p_organization_id uuid, p_workspace_id uuid, p_permission text
)
RETURNS TABLE (organization_id uuid, workspace_id uuid, workspace_key text, member_role text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_role text;
    v_key text;
BEGIN
    SELECT m.role INTO v_role
      FROM public.shoir_organization_memberships m
      JOIN public.shoir_organizations o ON o.organization_id = m.organization_id
     WHERE m.organization_id = p_organization_id
       AND m.username_lc = lower(btrim(p_actor))
       AND m.status = 'active' AND o.status = 'active';
    IF v_role IS NULL THEN
        RAISE EXCEPTION 'Organization membership is required.' USING ERRCODE = '42501';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.shoir_accounts
        WHERE username_lc = lower(btrim(p_actor)) AND COALESCE(active, true)
    ) THEN
        RAISE EXCEPTION 'The organization account is inactive.' USING ERRCODE = '42501';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.shoir_organizations o
        WHERE o.organization_id = p_organization_id
          AND o.org_type = 'team'
          AND NOT EXISTS (
              SELECT 1 FROM public.shoir_accounts owner
              WHERE owner.username_lc = o.owner_username_lc
                AND COALESCE(owner.active, true)
                AND lower(COALESCE(owner.tier, '')) LIKE '%enterprise%'
                AND owner.subscription_expires_at > now()
          )
    ) THEN
        RAISE EXCEPTION 'Organization owner Enterprise subscription is inactive or expired.'
            USING ERRCODE = '42501';
    END IF;
    IF p_permission IS NULL OR p_permission NOT IN ('read','write','approve','manage') THEN
        RAISE EXCEPTION 'Invalid workspace permission request.' USING ERRCODE = '22023';
    END IF;
    IF (p_permission = 'write' AND v_role NOT IN ('owner','admin','engineer'))
       OR (p_permission = 'approve' AND v_role NOT IN ('owner','admin','approver'))
       OR (p_permission = 'manage' AND v_role NOT IN ('owner','admin')) THEN
        RAISE EXCEPTION 'Organization role does not permit this workspace action.' USING ERRCODE = '42501';
    END IF;
    SELECT w.workspace_key INTO v_key
      FROM public.shoir_organization_workspaces w
     WHERE w.workspace_id = p_workspace_id
       AND w.organization_id = p_organization_id
       AND w.status = 'active';
    IF v_key IS NULL THEN
        RAISE EXCEPTION 'Workspace does not belong to the selected organization.' USING ERRCODE = '42501';
    END IF;
    RETURN QUERY SELECT p_organization_id, p_workspace_id, v_key, v_role;
END;
$function$;

CREATE OR REPLACE FUNCTION public.shoir_org_resolve_legacy_workspace(
    p_actor text, p_workspace_name text, p_legacy_workspace_key text
)
RETURNS TABLE (organization_id uuid, workspace_id uuid, workspace_key text, member_role text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_actor text := lower(btrim(p_actor));
    v_name text := btrim(p_workspace_name);
    v_org uuid;
    v_workspace uuid;
    v_key text;
    v_status text;
BEGIN
    IF v_actor IS NULL OR v_actor = '' OR length(v_actor) > 128
       OR v_name IS NULL OR length(v_name) < 1 OR length(v_name) > 100
       OR v_name ~ '[[:cntrl:]]'
       OR p_legacy_workspace_key IS NULL OR p_legacy_workspace_key !~ '^[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'Invalid personal workspace resolution input.' USING ERRCODE = '22023';
    END IF;
    SELECT o.organization_id, o.status INTO v_org, v_status
      FROM public.shoir_organizations o
     WHERE o.org_type = 'personal' AND o.owner_username_lc = v_actor;
    IF v_org IS NULL THEN
        RAISE EXCEPTION 'Personal organization is not provisioned.' USING ERRCODE = '42501';
    END IF;
    IF v_status <> 'active' OR NOT EXISTS (
        SELECT 1 FROM public.shoir_organization_memberships m
        WHERE m.organization_id = v_org AND m.username_lc = v_actor
          AND m.role = 'owner' AND m.status = 'active'
    ) THEN
        RAISE EXCEPTION 'Personal workspace membership is not active.' USING ERRCODE = '42501';
    END IF;
    INSERT INTO public.shoir_organization_workspaces(
        organization_id, display_name, name_key, workspace_key,
        legacy_workspace_key, created_by_username_lc
    ) VALUES (
        v_org, v_name, lower(v_name), p_legacy_workspace_key,
        p_legacy_workspace_key, v_actor
    )
    ON CONFLICT (organization_id, name_key) DO NOTHING;
    SELECT w.workspace_id, w.workspace_key INTO v_workspace, v_key
      FROM public.shoir_organization_workspaces w
     WHERE w.organization_id = v_org AND w.name_key = lower(v_name)
       AND w.status = 'active';
    IF v_workspace IS NULL OR v_key IS DISTINCT FROM p_legacy_workspace_key THEN
        RAISE EXCEPTION 'Personal workspace key mapping is inconsistent.' USING ERRCODE = '23505';
    END IF;
    RETURN QUERY SELECT v_org, v_workspace, v_key, 'owner'::text;
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_org_create(text,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_invitation_create(text,uuid,text,text,text,timestamptz) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_invitation_accept(text,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_member_role_set(text,uuid,text,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_member_remove(text,uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_owner_transfer(text,uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_workspace_create(text,uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_invitation_revoke(text,uuid,uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_workspace_archive(text,uuid,uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_resolve_workspace(text,uuid,uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.shoir_org_resolve_legacy_workspace(text,text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_org_create(text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_invitation_create(text,uuid,text,text,text,timestamptz) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_invitation_accept(text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_member_role_set(text,uuid,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_member_remove(text,uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_owner_transfer(text,uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_workspace_create(text,uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_invitation_revoke(text,uuid,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_workspace_archive(text,uuid,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_resolve_workspace(text,uuid,uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.shoir_org_resolve_legacy_workspace(text,text,text) TO service_role;
