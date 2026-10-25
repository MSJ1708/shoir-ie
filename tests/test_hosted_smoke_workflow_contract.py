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

def test_public_tab_smoke_rejects_clipped_mobile_labels():
    source = (ROOT / "scripts" / "live_deployment_smoke.py").read_text(encoding="utf-8")

    assert "def _tab_bar_layout(" in source
    assert "def _validate_tab_bar_layout(" in source
    assert 'layout["scrollWidth"] > layout["clientWidth"] + 2' in source
    assert 'tab["scrollWidth"] > tab["clientWidth"] + 2' in source
    assert 'tab["scrollHeight"] > tab["clientHeight"] + 2' in source
    assert 'viewport_width <= 600' in source

