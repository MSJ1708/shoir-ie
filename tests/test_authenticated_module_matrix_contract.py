"""Contract tests for fail-closed authenticated module acceptance."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "authenticated_module_matrix.py"
WORKFLOW = ROOT / ".github" / "workflows" / "authenticated-release-gate.yml"
DOCS = ROOT / "docs" / "AUTHENTICATED_RELEASE_GATE.md"


def test_matrix_is_inventory_driven_and_covers_research_separately():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'docs" / "MODULE_TIER_INVENTORY.csv' in source
    assert 'row["minimum_tier"].strip() == "Research Pack"' in source
    assert "SHOIR_E2E_MODULE_USERNAME" in source
    assert "SHOIR_E2E_RESEARCH_MODULE_USERNAME" in source
    assert "Enterprise Plus" in source
    assert "Research Pack" in source


def test_module_matrix_fails_closed_for_missing_or_broken_routes():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'report["overall"] = (' in source
    assert "passed_routes == expected" in source
    assert "report.get(\"preflight_error\")" in source
    assert "traceback (most recent call last)" in source.casefold()
    assert "main content is effectively blank" in source.casefold()
    assert "horizontal overflow" in source.casefold()


def test_authenticated_release_workflow_runs_matrix_and_requires_disposable_accounts():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "python scripts/authenticated_module_matrix.py" in workflow
    assert "SHOIR_E2E_MODULE_USERNAME" in workflow
    assert "SHOIR_E2E_RESEARCH_MODULE_USERNAME" in workflow
    assert "shoir-e2e-*" in workflow


def test_runbook_documents_matrix_scope_and_account_setup():
    docs = DOCS.read_text(encoding="utf-8")
    assert "Module-rendering matrix" in docs
    assert "SHOIR_E2E_MODULE_USERNAME" in docs
    assert "SHOIR_E2E_RESEARCH_MODULE_USERNAME" in docs
    assert "not calculation correctness" in docs.casefold()
