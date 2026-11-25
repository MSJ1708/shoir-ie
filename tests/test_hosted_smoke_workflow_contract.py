"""Contract tests for the separate staging and production hosted smoke gates."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATION_WORKFLOW = ROOT / ".github" / "workflows" / "shoir-validation.yml"
PRODUCTION_WORKFLOW = ROOT / ".github" / "workflows" / "production-public-smoke.yml"
STAGING_WORKFLOW = ROOT / ".github" / "workflows" / "staging-hosted-smoke.yml"
RUNBOOK = ROOT / "docs" / "SHOIR_IE_STAGING_BACKUP_RECOVERY_RUNBOOK.md"


def test_pull_request_validation_uses_local_browser_smoke_without_a_skipped_hosted_job():
    source = VALIDATION_WORKFLOW.read_text(encoding="utf-8")

    assert "\n  live-deployment-smoke:\n" not in source
    assert "http://127.0.0.1:8501/" in source
    assert "python scripts/live_deployment_smoke.py" in source


def test_production_public_smoke_is_restricted_to_main_and_can_be_dispatched():
    source = PRODUCTION_WORKFLOW.read_text(encoding="utf-8")

    assert "branches:\n      - main" in source
    assert "workflow_dispatch:" in source
    assert 'if [[ "$GITHUB_REF_NAME" != "main" ]]' in source
    assert "https://shoir-ie-app.streamlit.app/" in source
    assert "SHOIR_LIVE_URL" in source


def test_staging_hosted_smoke_is_opt_in_and_refuses_the_production_host():
    source = STAGING_WORKFLOW.read_text(encoding="utf-8")

    assert "branches:\n      - staging-e2e-20261019" in source
    assert '".github/staging-smoke-triggers/run.txt"' in source
    assert "name: staging-smoke" in source
    assert "vars.SHOIR_STAGING_LIVE_URL" in source
    assert "shoir-ie-app.streamlit.app" in source
    assert "Refusing to run a staging smoke against the known production Streamlit hostname." in source


def test_runbook_distinguishes_public_render_smoke_from_deployed_sha_and_authenticated_acceptance():
    source = RUNBOOK.read_text(encoding="utf-8").casefold()

    assert "not proof that the triggering git sha is deployed" in source
    assert "authenticated 96-route module matrix" in source
    assert "owner-provided disposable staging accounts" in source
