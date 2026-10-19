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
    migration = (ROOT / "supabase/migrations/20261019123300_server_side_login_rate_limits.sql").read_text(encoding="utf-8")
    edge = (ROOT / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    assert "shoir_check_login_throttle" in migration
    assert 'supabase.rpc("shoir_check_login_throttle"' in edge
