"""Guard the manual authenticated release workflow and prevent customer-account use."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_authenticated_gate_is_manual_only_and_uses_dedicated_test_accounts():
    workflow = (ROOT / ".github/workflows/authenticated-release-gate.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts/authenticated_release_gate.py").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "shoir-e2e-*" in workflow
    assert "shoir-e2e-" in script
    assert "admin_approve_session" not in script
    assert "admin_decline_session" not in script
    assert "restore_expected" in script
    assert 'action": "logout"' in script or 'api.call("logout"' in script


def test_authenticated_browser_gate_checks_module_route_and_shell_logout():
    script = (ROOT / "scripts/authenticated_browser_matrix.py").read_text(encoding="utf-8")
    assert "Sign In to Your Workspace" in script
    assert "Excel Data Cleaning & Import" in script
    assert "sidebar_logout_returns_to_signin" in script
    assert "Lock / Logout Workspace" in script



def test_server_login_throttle_is_reviewed_and_migration_first():
    migration = (ROOT / "supabase/migrations/20261019124815_server_side_login_rate_limits.sql").read_text(encoding="utf-8")
    edge = (ROOT / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    assert "shoir_check_login_throttle" in migration
    assert 'supabase.rpc("shoir_check_login_throttle"' in edge



def test_authenticated_gate_makes_live_login_throttle_probe_opt_in():
    script = (ROOT / "scripts/authenticated_release_gate.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/authenticated-release-gate.yml").read_text(encoding="utf-8")
    assert "SHOIR_E2E_VERIFY_LOGIN_THROTTLE" in script
    assert 'observed == [401] * 8 + [429]' in script
    assert "SHOIR_E2E_VERIFY_LOGIN_THROTTLE" in workflow


def test_authenticated_gate_requires_explicit_staging_targets_and_guard():
    workflow = (ROOT / ".github/workflows/authenticated-release-gate.yml").read_text(encoding="utf-8")
    docs = (ROOT / "docs/AUTHENTICATED_RELEASE_GATE.md").read_text(encoding="utf-8")
    guard = (ROOT / "scripts/staging_e2e_guard.py").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/authenticated_browser_matrix.py").read_text(encoding="utf-8")
    module_matrix = (ROOT / "scripts/authenticated_module_matrix.py").read_text(encoding="utf-8")

    assert "SHOIR_E2E_EXPECTED_STAGING_APP_HOST" in workflow
    assert "python scripts/staging_e2e_guard.py" in workflow
    assert "hfhrosthswcybccepmak" in guard
    assert "gcsamrdaeraxieaagsta" in guard
    assert "shoir-ie-app.streamlit.app" in guard
    assert "https://shoir-ie-app.streamlit.app/" not in browser
    assert "https://shoir-ie-app.streamlit.app/" not in module_matrix
    assert "There is intentionally no default application URL" in docs


def test_staging_app_must_declare_staging_and_refuses_production_backend_fallback():
    durable = (ROOT / "durable_account_store.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/authenticated_browser_matrix.py").read_text(encoding="utf-8")
    module_matrix = (ROOT / "scripts/authenticated_module_matrix.py").read_text(encoding="utf-8")
    docs = (ROOT / "docs/AUTHENTICATED_RELEASE_GATE.md").read_text(encoding="utf-8")

    assert "hfhrosthswcybccepmak.supabase.co" in durable
    assert "production fallback is disabled" in durable
    assert "Direct PostgreSQL URLs are forbidden in Shoir-IE staging mode" in durable
    assert "STAGING TEST ENVIRONMENT" in app
    assert "if not is_staging" in browser
    assert "STAGING TEST ENVIRONMENT" in module_matrix
    assert "edge_url = " in docs
    assert "environment = \"staging\"" in docs
