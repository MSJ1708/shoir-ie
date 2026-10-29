"""Guard required CI context triggers used by the protected main/staging rulesets."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "edge-function-check.yml"


def test_edge_function_required_check_is_not_path_skipped_for_main_or_staging_prs():
    source = WORKFLOW.read_text(encoding="utf-8")
    pull_request = source.split("  pull_request:", 1)[1].split("\npermissions:", 1)[0]
    assert '"main"' in pull_request
    assert '"staging-e2e-20261019"' in pull_request
    assert "paths:" not in pull_request


def test_edge_function_workflow_covers_database_migration_rehearsal_paths():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert '"supabase/migrations/**"' in source
    assert '"tests/test_migration_source_inventory.py"' in source
    assert '"tests/test_full_migration_history_postgres.py"' in source


def test_required_test_context_is_unique_across_workflows():
    workflows = (ROOT / ".github" / "workflows").glob("*.yml")
    matching = []
    for path in workflows:
        source = path.read_text(encoding="utf-8")
        if "\n  test:" in source or source.startswith("jobs:\n  test:"):
            matching.append(path.name)
    assert matching == ["shoir-validation.yml"], (
        "The protected ruleset requires the check context 'test'; it must be emitted "
        f"by exactly one workflow, found {matching}."
    )


def test_authenticated_gate_requires_inactive_denial_and_login_throttle_inputs():
    gate = (ROOT / ".github" / "workflows" / "authenticated-release-gate.yml").read_text(
        encoding="utf-8"
    )
    required = gate.split("required=(", 1)[1].split(")", 1)[0]
    for name in (
        "SHOIR_E2E_ACTIVE_EXPECTED_TIER",
        "SHOIR_E2E_INACTIVE_USERNAME",
        "SHOIR_E2E_INACTIVE_PASSWORD",
        "SHOIR_E2E_VERIFY_LOGIN_THROTTLE",
    ):
        assert name in required, f"{name} must be a mandatory release-gate input"
    assert 'SHOIR_E2E_VERIFY_LOGIN_THROTTLE,,}" != "true"' in gate
    username_checks = gate.split("for name in SHOIR_E2E_ACTIVE_USERNAME", 1)[1].split("; do", 1)[0]
    assert "SHOIR_E2E_INACTIVE_USERNAME" in username_checks
    assert 'shoir-e2e-*' in gate


def test_validation_workflow_emits_test_once_per_release_pr_head():
    source = (ROOT / ".github" / "workflows" / "shoir-validation.yml").read_text(
        encoding="utf-8"
    )
    events = source.split("jobs:", 1)[0]
    push = events.split("  push:", 1)[1].split("  pull_request:", 1)[0]
    pull_request = events.split("  pull_request:", 1)[1].split("  workflow_dispatch:", 1)[0]
    assert 'branches: ["main", "staging-e2e-20261019"]' in push
    assert 'branches: ["main", "staging-e2e-20261019"]' in pull_request
    assert "pull_request:" in events
