"""Regression contracts for the optional, server-verified T098 OIDC flow."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
STORE = ROOT / "durable_account_store.py"
OIDC_HELPERS = ROOT / "shoir_oidc_auth.py"
EDGE = ROOT / "supabase" / "functions" / "shoir-persistence" / "index.ts"
OIDC = ROOT / "supabase" / "functions" / "shoir-persistence" / "oidc.ts"
AUDIT_MIGRATION = ROOT / "supabase" / "migrations" / "20261028190000_shoir_oidc_audit_events.sql"


def test_optional_streamlit_oidc_is_config_gated_and_keeps_existing_password_login():
    app = APP.read_text(encoding="utf-8")
    helpers = OIDC_HELPERS.read_text(encoding="utf-8")
    store = STORE.read_text(encoding="utf-8")
    assert 'st.login("enterprise")' in app
    assert "oidc_configuration_status(st.secrets)" in app
    assert "get_verified_streamlit_id_token(st.user)" in app
    assert "edge_oidc_login(_oidc_id_token, _oidc_display_hint)" in app
    assert 'if not _oidc_status.get("ready")' in app
    assert 'action === "login"' in EDGE.read_text(encoding="utf-8")
    assert 'return _edge_call("oidc_login", {"id_token": token, "email_hint": hint})' in store
    assert 'hint = str(email_hint or "").strip().lower()[:320]' in store
    assert '"id" not in exposed_tokens' in helpers
    assert "st.login(\"enterprise\")" in app


def test_edge_function_independently_verifies_provider_token_before_account_mapping():
    edge = EDGE.read_text(encoding="utf-8")
    oidc = OIDC.read_text(encoding="utf-8")
    start = edge.index('if (action === "oidc_login")')
    end = edge.index('if (action === "login")', start)
    action = edge[start:end]
    assert "verifyOidcIdToken(idToken, oidcConfig)" in action
    assert "findAccountByVerifiedOidcEmail(identity.email)" in action
    assert "identity.email" in action
    assert "account.active === false" in action
    assert "writeOidcAuditEvent" in action
    assert "revokeJustCreatedSession(sessionToken, usernameLc)" in action
    assert "isUniqueConstraintError(auditError)" in action
    assert "config.requireMfa && !mfaVerified" in oidc
    assert 'algorithms: ["RS256", "ES256"]' in oidc
    assert 'maxTokenAge: MAX_ID_TOKEN_AGE_SECONDS' in oidc
    # The OIDC branch must map to an existing account, not create/promote one.
    assert '.from("shoir_accounts").insert' not in action
    assert '.from("shoir_accounts").upsert' not in action


def test_audit_migration_is_server_only_and_append_only():
    migration = AUDIT_MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "REVOKE ALL ON TABLE public.shoir_security_audit_events" in migration
    assert "GRANT INSERT ON TABLE public.shoir_security_audit_events TO service_role" in migration
    assert "GRANT USAGE ON SEQUENCE public.shoir_security_audit_events_id_seq TO service_role" in migration
    assert "FROM PUBLIC, anon, authenticated, service_role" in migration
    assert "UNIQUE" in migration
    assert "id_token_sha256" in migration
    assert "GRANT SELECT" not in migration
    assert "GRANT UPDATE" not in migration
    assert "GRANT DELETE" not in migration
