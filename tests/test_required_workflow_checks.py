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
