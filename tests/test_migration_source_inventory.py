"""Fast source-integrity checks for the versioned Supabase migration set."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
EXPECTED_VERSIONS = [
    "20260925093314",
    "20260925093546",
    "20260925093748",
    "20260925094637",
    "20260925125508",
    "20260925131100",
    "20260929185528",
    "20260929190456",
    "20261018194225",
    "20261018204013",
    "20261018204217",
    "20261018204857",
    "20261019124815",
    "20261019140600",
    "20261021130000",
    "20261022110000",
    "20261025164602",
    "20261026110000",
    "20261104183132",
    "20261104184453",
    "20261104192112",
    "20261104192857",
    "20261105101231",
    "20261105111832",
    "20261107120637",
    "20261107150000",
    "20261107153000",
    "20261107160000",
]


def test_all_recorded_migration_versions_have_tracked_source_files():
    files = sorted(MIGRATIONS.glob("*.sql"))
    versions = [path.name.split("_", 1)[0] for path in files]
    assert versions == EXPECTED_VERSIONS, (
        "A versioned Supabase migration is missing, unexpected or misordered. "
        f"Expected {EXPECTED_VERSIONS}; found {versions}."
    )


def test_bootstrap_migration_does_not_embed_static_master_admin_credentials():
    source = (MIGRATIONS / "20260925093748_seed_shoir_admin_account.sql").read_text(
        encoding="utf-8"
    ).casefold()
    assert "select 1;" in source
    assert "insert into shoir_accounts" not in source
    assert "password_hash" not in source
    assert "557e828e5d76f4cf" not in source


def test_transactional_subscription_migration_is_present_and_guarded():
    source = (
        MIGRATIONS
        / "20261019140600_atomic_subscription_request_decisions.sql"
    ).read_text(encoding="utf-8")
    assert "FOR UPDATE" in source
    assert "p_decision NOT IN ('Approved', 'Declined')" in source
    assert "shoir_create_registration_request" in source
    assert "REVOKE ALL ON FUNCTION public.shoir_finalize_subscription_request" in source


def test_beta_acceptance_guard_migration_enforces_all_current_notice_versions():
    source = (MIGRATIONS / "20261022110000_enforce_beta_legal_acceptance.sql").read_text(encoding="utf-8")
    assert "BEFORE UPDATE OF status" in source
    assert "privacy_policy_version IS DISTINCT FROM" in source
    assert "refund_policy_version IS DISTINCT FROM" in source
    assert "cookie_policy_version IS DISTINCT FROM" in source
    assert "accepted_at IS NULL" in source


def test_refund_policy_v2_guard_migration_requires_current_refund_version():
    source = (MIGRATIONS / "20261025164602_20261023130000_refresh_refund_policy_acceptance_version.sql").read_text(encoding="utf-8")
    assert "refund_policy_version IS DISTINCT FROM '2026-10-23-v2'" in source
    assert "BEFORE UPDATE OF status" in source


def test_additive_referral_migration_does_not_rewrite_existing_account_identifiers():
    source = (
        MIGRATIONS / "20261026110000_safe_beta_legal_referrals.sql"
    ).read_text(encoding="utf-8").casefold()
    # Comments and safe lookup indexes may mention the existing code column.
    # The invariant is that this additive migration performs no data rewrite.
    executable_sql = "\n".join(line.split("--", 1)[0] for line in source.splitlines())
    assert "create table if not exists public.shoir_referrals" in executable_sql
    assert "update public.shoir_accounts" not in executable_sql
    assert "set affiliate_code" not in executable_sql
    assert "set updated_at" not in executable_sql
    assert "create unique index if not exists idx_shoir_accounts_affiliate_code_trimmed_unique" in executable_sql
    assert "on public.shoir_accounts (lower(btrim(affiliate_code)))" in executable_sql
    assert "where affiliate_code is not null and btrim(affiliate_code) <> ''" in executable_sql
    assert "revoke all on table public.shoir_referrals from public, anon, authenticated" in executable_sql



def test_internal_schema_rls_migration_enables_only_private_deny_by_default_tables():
    """Check executable SQL, not comments, for the intended RLS posture."""
    source = (
        MIGRATIONS
        / "20261104183132_enable_shoir_internal_rls_20261104.sql"
    ).read_text(encoding="utf-8")

    # Strip line comments before asserting on SQL commands. A comment explaining
    # that FORCE RLS is intentionally not used must not trigger a false failure.
    executable_sql = "\n".join(
        line.split("--", 1)[0] for line in source.splitlines()
    )
    normalized = re.sub(r"\s+", " ", executable_sql).casefold()

    expected_tables = {
        "artifacts",
        "twin_assets",
        "twin_snapshots",
        "twin_scenarios",
        "connector_health",
        "jobs",
        "collaboration",
        "knowledge",
        "monitoring_rules",
        "monitoring_events",
        "report_provenance",
        "security",
    }
    enabled_tables = {
        table.casefold()
        for table in re.findall(
            r"alter\s+table\s+shoir_internal\.([a-z_]+)\s+enable\s+row\s+level\s+security\s*;",
            executable_sql,
            flags=re.IGNORECASE,
        )
    }

    assert enabled_tables == expected_tables
    assert not re.search(
        r"\bforce\s+row\s+level\s+security\b",
        executable_sql,
        flags=re.IGNORECASE,
    )
    assert not re.search(r"\bcreate\s+policy\b", executable_sql, re.IGNORECASE)
    assert not re.search(r"\bgrant\b", executable_sql, re.IGNORECASE)
    assert (
        "revoke all on schema shoir_internal from public, anon, authenticated"
        in normalized
    )
    assert (
        "revoke all on all tables in schema shoir_internal from public, anon, authenticated"
        in normalized
    )



def test_staging_referral_reconciliation_migration_is_idempotent_and_non_rewriting():
    source = (
        MIGRATIONS
        / "20261105101231_safe_beta_legal_referrals_20261105.sql"
    ).read_text(encoding="utf-8").casefold()
    executable_sql = "\n".join(
        line.split("--", 1)[0] for line in source.splitlines()
    )
    assert "alter table public.shoir_subscription_requests" in executable_sql
    assert "add column if not exists terms_accepted" in executable_sql
    assert "create table if not exists public.shoir_referrals" in executable_sql
    assert (
        "create unique index if not exists idx_shoir_accounts_affiliate_code_trimmed_unique"
        in executable_sql
    )
    assert "on public.shoir_accounts (lower(btrim(affiliate_code)))" in executable_sql
    assert "update public.shoir_accounts" not in executable_sql
    assert "set affiliate_code" not in executable_sql
    assert "set updated_at" not in executable_sql
    assert (
        "revoke all on table public.shoir_referrals from public, anon, authenticated"
        in executable_sql
    )
    assert "grant select, insert, update, delete on table public.shoir_referrals to service_role" in executable_sql


def test_private_rls_advisory_migration_adds_explicit_client_deny_policies_only():
    source = (
        MIGRATIONS
        / "20261105111832_explicit_deny_policies_for_private_rls_advisories.sql"
    ).read_text(encoding="utf-8")
    executable_sql = "\n".join(
        line.split("--", 1)[0] for line in source.splitlines()
    )
    normalized = " ".join(executable_sql.casefold().split())

    expected_tables = [
        "public.shoir_referrals",
        "shoir_internal.artifacts",
        "shoir_internal.twin_assets",
        "shoir_internal.twin_snapshots",
        "shoir_internal.twin_scenarios",
        "shoir_internal.connector_health",
        "shoir_internal.jobs",
        "shoir_internal.collaboration",
        "shoir_internal.knowledge",
        "shoir_internal.monitoring_rules",
        "shoir_internal.monitoring_events",
        "shoir_internal.report_provenance",
        "shoir_internal.security",
    ]
    for table in expected_tables:
        short_name = table.split(".")[-1]
        policy_name = (
            "shoir_referrals_deny_browser_roles"
            if table == "public.shoir_referrals"
            else f"shoir_internal_{short_name}_deny_browser_roles"
        )
        policy = (
            f"create policy {policy_name} on {table} "
            "for all to anon, authenticated using (false) with check (false);"
        )
        assert policy in normalized, table

    assert normalized.count("create policy ") == 13
    assert "grant " not in normalized
    assert "force row level security" not in normalized


def test_organization_workspace_migration_is_server_only_and_preserves_legacy_keys():
    source = (
        MIGRATIONS
        / "20261107120637_shoir_organization_workspaces.sql"
    ).read_text(encoding="utf-8")
    executable_sql = "\n".join(
        line.split("--", 1)[0] for line in source.splitlines()
    )
    normalized = " ".join(executable_sql.casefold().split())
    expected_tables = {
        "shoir_organizations",
        "shoir_organization_memberships",
        "shoir_organization_invitations",
        "shoir_organization_workspaces",
        "shoir_organization_audit_events",
    }
    for table in expected_tables:
        assert f"create table public.{table}" in normalized
        assert f"alter table public.{table} enable row level security" in normalized
        assert f"public.{table}" in normalized
    assert "revoke all on table public.shoir_organizations" in normalized
    assert "from public, anon, authenticated" in normalized
    assert "to service_role" in normalized
    assert "using (false) with check (false)" in normalized
    assert "shoir_org_invitation_accept" in normalized
    assert "shoir_org_invitation_revoke" in normalized
    assert "shoir_org_workspace_archive" in normalized
    assert "shoir_org_resolve_workspace" in normalized
    assert "shoir_org_resolve_legacy_workspace" in normalized
    assert "token_hash text not null unique" in normalized
    assert "grant select, insert on table public.shoir_organization_audit_events to service_role" in normalized
    assert "grant select, insert, update, delete on table public.shoir_organization_audit_events" not in normalized
    assert "shoir_org_audit_events_immutable" in normalized
    assert "before update or delete on public.shoir_organization_audit_events" in normalized
    assert "organization audit events are append-only" in normalized
    assert "v_inv.target_username_lc <> v_actor" in normalized
    assert "used_at is null" in normalized
    # Existing account-derived keys are registered lazily; no platform records,
    # storage objects, or dataset payloads are rewritten by this migration.
    assert "update public.shoir_platform_records" not in normalized
    assert "update public.shoir_platform_events" not in normalized
    assert "update storage.objects" not in normalized
    assert "legacy_workspace_key" in normalized


def test_organization_owner_and_invitation_lifecycle_is_fail_closed():
    source = (
        MIGRATIONS
        / "20261107120637_shoir_organization_workspaces.sql"
    ).read_text(encoding="utf-8")
    executable_sql = "\n".join(
        line.split("--", 1)[0] for line in source.splitlines()
    )
    normalized = " ".join(executable_sql.casefold().split())
    assert "create unique index shoir_org_memberships_one_owner" in normalized
    assert "where role = 'owner'" in normalized
    assert "shoir_org_owner_transfer" in normalized
    assert "only the current organization owner may transfer ownership" in normalized
    assert "new owner must be an active organization member" in normalized
    assert "invitations are available only for active team organizations" in normalized
    assert "v_inv.target_username_lc <> v_actor" in normalized
    assert "v_inv.expires_at <= now()" in normalized
    assert "v_inv.used_at is not null" in normalized
    assert "v_inv.revoked_at is not null" in normalized
    assert "the organization account is inactive" in normalized
    assert "new owner must have an active enterprise subscription" in normalized
    assert "active enterprise subscription is required to create a team organization" in normalized
    assert "target active account was not found" in normalized
    assert "a pending invitation already exists for this account" in normalized
    assert "organization owner enterprise subscription is inactive or expired" in normalized
    assert "perform 1 from public.shoir_organizations" in normalized
    assert "last active organization workspace cannot be archived" in normalized
    assert "invitation is missing, expired, used or already revoked" in normalized
    assert "revoke all on function public.shoir_org_invitation_revoke(text,uuid,uuid)" in normalized
    assert "grant execute on function public.shoir_org_invitation_revoke(text,uuid,uuid) to service_role" in normalized
    assert "revoke all on function public.shoir_org_workspace_archive(text,uuid,uuid)" in normalized
    assert "grant execute on function public.shoir_org_workspace_archive(text,uuid,uuid) to service_role" in normalized
    assert "revoke all on function public.shoir_org_owner_transfer(text,uuid,text)" in normalized
    assert "grant execute on function public.shoir_org_owner_transfer(text,uuid,text) to service_role" in normalized



def test_organization_close_rpc_preserves_audit_and_removes_active_access():
    source = (
        MIGRATIONS
        / "20261107150000_shoir_organization_close.sql"
    ).read_text(encoding="utf-8")
    executable_sql = "\n".join(
        line.split("--", 1)[0] for line in source.splitlines()
    )
    normalized = " ".join(executable_sql.casefold().split())
    assert "create or replace function public.shoir_org_close" in normalized
    assert "security definer" in normalized
    assert "set search_path = ''" in normalized
    assert "only the current organization owner may close the organization" in normalized
    assert "org_type = 'team'" in normalized
    assert "status = 'closed'" in normalized
    assert "status = 'archived'" in normalized
    assert "status = 'removed'" in normalized
    assert "revoked_at = now()" in normalized
    assert "organization.closed" in normalized
    assert "public.shoir_organization_audit_events" in normalized
    assert "delete from public.shoir_organization_audit_events" not in normalized
    assert "update public.shoir_organization_audit_events" not in normalized
    assert "revoke all on function public.shoir_org_close(text, uuid) from public, anon, authenticated, service_role" in normalized
    assert "grant execute on function public.shoir_org_close(text, uuid) to service_role" in normalized


def test_organization_member_suspend_restore_is_owner_admin_scoped_and_audited():
    source = (
        MIGRATIONS
        / "20261107153000_shoir_organization_member_suspend_restore.sql"
    ).read_text(encoding="utf-8")
    executable_sql = "\n".join(
        line.split("--", 1)[0] for line in source.splitlines()
    )
    normalized = " ".join(executable_sql.casefold().split())
    assert "create or replace function public.shoir_org_member_suspend" in normalized
    assert "create or replace function public.shoir_org_member_restore" in normalized
    assert "security definer" in normalized
    assert "set search_path = ''" in normalized
    assert "v_actor_role not in ('owner','admin')" in normalized
    assert "v_target_role = 'admin' and v_actor_role <> 'owner'" in normalized
    assert "v_target_status is distinct from 'active'" in normalized
    assert "v_target_status is distinct from 'suspended'" in normalized
    assert "v_account_active is distinct from true" in normalized
    assert "organization.member_suspended" in normalized
    assert "organization.member_restored" in normalized
    assert "revoke all on function public.shoir_org_member_suspend(text, uuid, text)" in normalized
    assert "revoke all on function public.shoir_org_member_restore(text, uuid, text)" in normalized
    assert "revoke all on function public.shoir_org_member_suspend(text, uuid, text) from public, anon, authenticated, service_role" in normalized
    assert "revoke all on function public.shoir_org_member_restore(text, uuid, text) from public, anon, authenticated, service_role" in normalized
    assert "grant execute on function public.shoir_org_member_suspend(text, uuid, text) to service_role" in normalized
    assert "grant execute on function public.shoir_org_member_restore(text, uuid, text) to service_role" in normalized


def test_mutating_organization_edge_actions_require_server_session_and_scoped_membership():
    source = (
        ROOT / "supabase/functions/shoir-persistence/index.ts"
    ).read_text(encoding="utf-8")
    actions = {
        "org_create_session": "shoir_org_create",
        "org_workspace_create_session": "shoir_org_workspace_create",
        "org_workspace_archive_session": "shoir_org_workspace_archive",
        "org_invitation_create_session": "shoir_org_invitation_create",
        "org_invitation_accept_session": "shoir_org_invitation_accept",
        "org_invitation_revoke_session": "shoir_org_invitation_revoke",
        "org_member_role_set_session": "shoir_org_member_role_set",
        "org_member_remove_session": "shoir_org_member_remove",
        "org_member_suspend_session": "shoir_org_member_suspend",
        "org_member_restore_session": "shoir_org_member_restore",
        "org_owner_transfer_session": "shoir_org_owner_transfer",
        "org_close_session": "shoir_org_close",
    }
    for action, rpc in actions.items():
        marker = f'if (action === "{action}")'
        start = source.index(marker)
        following = source.find('if (action === "', start + len(marker))
        block = source[start:following if following >= 0 else len(source)]
        assert "await getSession(" in block, action
        if action == "org_create_session":
            # Creating a new organization is account-scoped, not scoped to
            # an organization that does not exist yet.
            assert "requireOrganizationTier(actor as Record<string, unknown>)" in block
        elif action == "org_invitation_accept_session":
            # An invitee is not a member until this RPC succeeds. Authenticate
            # the actor, validate the one-time token and pass only its hash;
            # requiring existing organization membership would block valid invites.
            assert '"workspace"' in block
            assert "^[0-9a-f]{64}$" in block
            assert "sha256Hex(invitationToken)" in block
            assert "p_actor: actor.username_lc" in block
        else:
            assert "organizationForActor(" in block, action
        assert f'"{rpc}"' in block, action


def test_organization_workspace_state_rpc_is_transactional_and_revision_checked():
    source = (
        MIGRATIONS
        / "20261107160000_shoir_organization_workspace_state.sql"
    ).read_text(encoding="utf-8")
    executable_sql = "\n".join(
        line.split("--", 1)[0] for line in source.splitlines()
    )
    normalized = " ".join(executable_sql.casefold().split())
    assert "create table public.shoir_organization_workspace_states" in normalized
    assert "workspace_key text primary key" in normalized
    assert "jsonb_typeof(state_json::jsonb) = 'object'" in normalized
    assert "octet_length(state_json) <= 8388608" in normalized
    assert "octet_length(p_state_json) > 8388608" in normalized
    assert "p_expected_revision bigint" in normalized
    assert "p_expected_revision is null or p_expected_revision < 0" in normalized
    assert "revision bigint not null default 1" in normalized
    assert "enable row level security" in normalized
    assert "revoke all on table public.shoir_organization_workspace_states from public, anon, authenticated, service_role" in normalized
    assert "grant select, insert, update on table public.shoir_organization_workspace_states" not in normalized
    assert "create or replace function public.shoir_org_workspace_state_load" in normalized
    assert "create or replace function public.shoir_org_workspace_state_save" in normalized
    assert "for share" in normalized
    assert "shoir_org_resolve_workspace" in normalized
    assert "if p_expected_revision = 0 then" in normalized
    assert "on conflict (workspace_key) do nothing" in normalized
    assert "update public.shoir_organization_workspace_states" in normalized
    assert "where workspace_key = v_workspace_key and revision = p_expected_revision" in normalized
    # A missing/negative expected revision must fail closed before any write.
    assert "or p_expected_revision is null or p_expected_revision < 0 then" in normalized
    assert "revision = revision + 1" in normalized
    assert "shared workspace changed since it was loaded" in normalized
    assert "using errcode = '40001'" in normalized
    assert "organization.workspace_state_saved" in normalized
    assert "workspace_id', p_workspace_id" in normalized
    assert "revision', v_revision" in normalized
    assert "state_bytes', octet_length(p_state_json)" in normalized
    assert "insert into public.shoir_organization_audit_events" in normalized
    assert "revoke all on function public.shoir_org_workspace_state_load(text, uuid, uuid)" in normalized
    assert "revoke all on function public.shoir_org_workspace_state_load(text, uuid, uuid) from public, anon, authenticated, service_role" in normalized
    assert "revoke all on function public.shoir_org_workspace_state_save(text, uuid, uuid, text, bigint)" in normalized
    assert "revoke all on function public.shoir_org_workspace_state_save(text, uuid, uuid, text, bigint) from public, anon, authenticated, service_role" in normalized
    assert "grant execute on function public.shoir_org_workspace_state_load(text, uuid, uuid) to service_role" in normalized
    assert "grant execute on function public.shoir_org_workspace_state_save(text, uuid, uuid, text, bigint) to service_role" in normalized
    assert "delete from public.shoir_organization_workspace_states" not in normalized
    assert "create index if not exists shoir_org_owner_username_fk on public.shoir_organizations(owner_username_lc)" in normalized
    assert "create index if not exists shoir_org_audit_actor_fk" in normalized
    assert "create index if not exists shoir_org_audit_subject_fk" in normalized
    assert "create index if not exists shoir_org_invitation_accepted_by_fk" in normalized
    assert "create index if not exists shoir_org_invitation_created_by_fk" in normalized
    assert "create index if not exists shoir_org_invitation_organization_fk" in normalized
    assert "create index if not exists shoir_org_membership_invited_by_fk" in normalized
    assert "create index if not exists shoir_org_workspace_created_by_fk" in normalized
    assert "create index if not exists shoir_org_workspace_state_updated_by_fk" in normalized
    assert "revoke update, delete, truncate, references, trigger on table public.shoir_organization_audit_events from service_role" in normalized


def test_shared_workspace_edge_handlers_route_only_explicit_org_context_to_shared_rpc():
    source = (
        ROOT / "supabase/functions/shoir-persistence/index.ts"
    ).read_text(encoding="utf-8")
    load_start = source.index('if (action === "workspace_load")')
    save_start = source.index('if (action === "workspace_save")')
    access_start = source.index('if (action === "workspace_access_check")')
    renewal_start = source.index('if (action === "renew_request")')
    load_block = source[load_start:save_start]
    save_block = source[save_start:access_start]
    access_block = source[access_start:renewal_start]

    for block in (load_block, save_block, access_block):
        assert "await getSession(" in block
        assert "organization_id" in block
        assert "organization_workspace_id" in block

    assert '"shoir_org_workspace_state_load"' in load_block
    assert '"shoir_org_workspace_state_save"' in save_block
    assert "await resolveManagedWorkspaceKey(" in access_block
    resolver_start = source.index("async function resolveManagedWorkspaceKey(")
    resolver_end = source.index("return key;", resolver_start) + len("return key;")
    resolver_block = source[resolver_start:resolver_end]
    assert "organizationForActor(" in resolver_block
    assert 'supabase.rpc("shoir_org_resolve_workspace"' in resolver_block
    assert "actor.username_lc" in load_block
    assert "actor.username_lc" in save_block
    assert 'error?.code === "40001"' in save_block
    assert "SHARED_WORKSPACE_REVISION_CONFLICT" in save_block
    assert "Workspace revision is required." in save_block
    assert "rawRevision === undefined || rawRevision === null" in save_block


def test_main_app_revalidates_and_clears_revoked_shared_workspace_before_loading():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    marker = 'if st.session_state.get("current_user") and st.session_state.get("authenticated"):'
    start = source.index(marker)
    end = source.index("# WORKSPACE STATUS RIBBON", start)
    block = source[start:end]
    validate = block.index("validate_remote_organization_workspace_access")
    clear = block.index("clear_loaded_workspace_state")
    drop = block.index('st.session_state.pop("shoir_active_organization_workspace", None)')
    load = block.index("load_user_workspace(")
    assert validate < clear < drop < load
    assert "_workspace_loaded_scope" in block

def test_protected_administrator_is_immutable_on_login_and_existing_sessions():
    sources = (
        ROOT / "supabase/functions/shoir-persistence/index.ts",
        ROOT / "supabase/production-backports/shoir-persistence-v9/index.ts",
    )
    for path in sources:
        source = path.read_text(encoding="utf-8")
        normalized = " ".join(source.casefold().split())
        session_start = normalized.find("async function getsession(")
        session_end = normalized.find("async function adminsession(", session_start)
        assert session_start >= 0 and session_end > session_start, path
        session_guard = normalized[session_start:session_end]
        assert "row.username_lc === \"sho\"" in session_guard, path
        assert "hascanonicalmasteradmininvariant(row)" in session_guard, path
        assert "administrator account requires manual security review" in session_guard, path
        assert '"access-control-allow-origin": "*"' not in normalized, path
        assert "const admintier = \"enterprise plus tier ($399)\"" not in normalized, path
        assert not re.search(
            r'from\("shoir_accounts"\)\s*\.update\(\{\s*tier\s*:\s*adminTier',
            source,
            flags=re.IGNORECASE,
        ), path
