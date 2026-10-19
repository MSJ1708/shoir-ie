"""Regression tests for the hosted public-shell smoke release gate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "shoir-validation.yml"


def test_hosted_smoke_runs_after_main_pushes_and_can_be_dispatched():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "\n  workflow_dispatch:\n" in source
    assert "github.event_name == 'push'" in source
    assert "github.ref_name == 'main'" in source
    assert "github.event_name == 'workflow_dispatch'" in source


def test_hosted_smoke_still_runs_for_audit_pull_requests_and_pushes():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "github.event_name == 'pull_request'" in source
    assert "startsWith(github.head_ref, 'audit/')" in source
    assert "startsWith(github.ref_name, 'audit/')" in source


def test_hosted_smoke_documents_that_it_does_not_prove_deployed_sha():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "not proof" in source
    assert "triggering Git SHA" in source
