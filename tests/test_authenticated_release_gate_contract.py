"""Guard the manual authenticated release workflow and prevent customer-account use."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_authenticated_gate_is_manual_with_scoped_release_pr_and_one_shot_push_opt_in():
    workflow = (ROOT / ".github/workflows/authenticated-release-gate.yml").read_text(encoding="utf-8")
    script = (ROOT / "scripts/authenticated_release_gate.py").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "pull_request:" in workflow
    assert "branches:" in workflow
    assert "github.event_name == 'pull_request'" in workflow
    assert "github.head_ref == 'docs/live-release-recheck-20261027'" in workflow
    assert "!github.event.pull_request.head.repo.fork" in workflow
    assert "push:" in workflow
    assert "staging-e2e-20261019" in workflow
    assert "[run-authenticated-gate]" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "SHOIR_E2E_VERIFY_LOGIN_THROTTLE must be set to true" in workflow
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
    assert "stable_signout_observations >= 2" in script
    assert "authenticated-logout-state.png" in script



def test_navigation_and_logout_defer_widget_state_reset_until_before_render():
    shell = (ROOT / "shoir_application_shell.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/authenticated_browser_matrix.py").read_text(encoding="utf-8")

    assert 'st.session_state[selector_key] = requested_module' in shell
    assert '_shoir_clear_global_search_before_render' in shell
    assert 'st.session_state.pop("shoir_shell_section_radio", None)' in shell
    assert '_shoir_clear_session_before_render' in app
    assert 'del st.session_state[_logout_key]' not in app
    assert 'del st.session_state[_key]' not in app
    assert 'Active module:' in browser
    assert 'data-testid="shoir-active-module"' in browser
    assert "candidate shell marker" in browser
    assert "ACTIVE_MODULE_SELECTOR" in browser
    assert 'full_page=False' in browser


def test_authenticated_sidebar_starts_expanded_and_browser_gate_expands_it_before_logout():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    matrix = (ROOT / "scripts/authenticated_module_matrix.py").read_text(encoding="utf-8")
    browser = (ROOT / "scripts/authenticated_browser_matrix.py").read_text(encoding="utf-8")
    assert 'initial_sidebar_state="expanded"' in app
    assert "def visible_logout_button(frame)" in matrix
    assert "def visible_logout_button(frame)" in browser
    assert "visible_logout_button(frame).click" in matrix
    assert "visible_logout_button(app_frame).click" in browser
    assert "open_button.scroll_into_view_if_needed" in matrix
    assert "for navigation_attempt in range(2)" in matrix
    assert "CANDIDATE_BUILD_MARKER" in matrix
    assert "candidate build preflight should have confirmed" in matrix
    assert "STAGING_BUILD_WAIT_SECONDS" not in matrix
    candidate = (ROOT / "scripts/staging_candidate_build_preflight.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/authenticated-release-gate.yml").read_text(encoding="utf-8")
    assert "SHOIR-IE SHELL VERSION: 3.2" in candidate
    assert "WAIT_SECONDS = 90" in candidate
    assert "python scripts/staging_candidate_build_preflight.py" in workflow
    assert "steps.candidate_build.conclusion == 'success'" in workflow
    assert "steps.backend_check.conclusion == 'success'" not in workflow
    assert "always()" in workflow


def test_active_module_identity_renders_before_optional_header_diagnostics_and_has_visible_text_fallback():
    shell = (ROOT / "shoir_application_shell.py").read_text(encoding="utf-8")
    shell_start = shell.index("def render_application_header(")
    shell_end = shell.index("\ndef render_module_workflow(", shell_start)
    header = shell[shell_start:shell_end]
    assert header.index('data-testid="shoir-active-module"') < header.index("_first_dataframe()")
    assert header.count('data-testid="shoir-active-module"') == 1

    for relative_path in (
        "scripts/authenticated_browser_matrix.py",
        "scripts/authenticated_module_matrix.py",
    ):
        script = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "def read_active_module_label(frame)" in script
        assert "get_by_text(re.compile" in script
        assert "ACTIVE_MODULE_SELECTOR" in script


def test_manual_release_gate_runbook_targets_the_unmerged_candidate_branch():
    docs = (ROOT / "docs/AUTHENTICATED_RELEASE_GATE.md").read_text(encoding="utf-8")
    assert "select the branch containing the release-candidate commit" in docs
    assert "select `staging-e2e-20261019` (PR #165)" in docs
    assert "choosing `main` would test the older base revision" in docs


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
    assert 'st.caption(f"SHOIR-IE SHELL VERSION: {SHELL_VERSION}")' in app
    assert "SHELL_VERSION = \"3.2\"" in (ROOT / "shoir_application_shell.py").read_text(encoding="utf-8")
    assert "if not is_staging" in browser
    assert "STAGING TEST ENVIRONMENT" in module_matrix
    assert "edge_url = " in docs
    assert "environment = \"staging\"" in docs



def test_current_supabase_publishable_key_is_not_sent_as_bearer_auth():
    script = (ROOT / "scripts/authenticated_release_gate.py").read_text(encoding="utf-8")
    assert 'publishable_key.startswith("sb_publishable_")' in script
    assert 'self.headers["Authorization"] = f"Bearer {publishable_key}"' in script
    assert '"apikey": publishable_key' in script


def test_browser_gates_locate_visible_streamlit_signin_inputs_without_label_association():
    for relative_path in (
        "scripts/authenticated_browser_matrix.py",
        "scripts/authenticated_module_matrix.py",
    ):
        script = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "input[type='text']:visible" in script
        assert "input[type='password']:visible" in script
        assert "fill_signin_credentials" in script
        assert 'get_by_label("Username", exact=True)' not in script


def test_logout_saves_workspace_before_server_session_revocation():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    logout_start = app.index('if _shell_surface == "logout":')
    logout_end = app.index("# Compatibility contract retained", logout_start)
    logout_block = app[logout_start:logout_end]
    assert logout_block.index("save_user_workspace") < logout_block.index("edge_logout")
    assert 'st.session_state["_shoir_clear_session_before_render"] = True' in logout_block
    assert "st.rerun()" in logout_block


def test_backend_authentication_failures_give_safe_actionable_diagnostics():
    backend = (ROOT / "scripts/authenticated_release_gate.py").read_text(encoding="utf-8")
    assert "HTTP 401 means the staging API rejected the credentials or account state" in backend
    assert "HTTP 429 indicates the staging login throttle is active" in backend
    assert "HTTP 503 indicates staging authentication protection is unavailable" in backend
    assert "scripts/recover_staging_e2e_credentials.py" in backend
    assert "Response details were suppressed." in backend

def test_staging_credential_recovery_reads_clipboard_without_echo_and_clears_it():
    wrapper = (ROOT / "scripts/Recover-StagingE2ECredentials.ps1").read_text(encoding="utf-8")
    assert "function Read-StagingKeyFromClipboard" in wrapper
    assert "Get-Clipboard -Raw" in wrapper
    assert "Clear-Clipboard" in wrapper
    assert "[Console]::ReadKey($true)" in wrapper
    assert "Read-Host" not in wrapper
    assert "STAGING server secret/service-role key" in wrapper
    assert "STAGING publishable/anon key" in wrapper


def test_authenticated_registration_probes_use_current_refund_policy_version():
    script = (ROOT / "scripts/authenticated_release_gate.py").read_text(encoding="utf-8")
    assert '"refund_policy_version": "2026-10-23-v2"' in script
    assert '"referral code"' in script

def test_inactive_test_account_is_required_and_restricted_to_disposable_prefix():
    workflow = (ROOT / ".github/workflows/authenticated-release-gate.yml").read_text(encoding="utf-8")
    required_line = next(line for line in workflow.splitlines() if line.strip().startswith("required=("))
    account_prefix_line = next(
        line for line in workflow.splitlines()
        if "for name in SHOIR_E2E_ACTIVE_USERNAME" in line
    )

    assert "SHOIR_E2E_INACTIVE_USERNAME" in required_line
    assert "SHOIR_E2E_INACTIVE_PASSWORD" in required_line
    assert "SHOIR_E2E_INACTIVE_USERNAME" in account_prefix_line
    assert "shoir-e2e-*" in workflow
