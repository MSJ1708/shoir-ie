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
    assert "viewport_width <= 600" in source


def test_tab_bar_layout_validator_catches_mobile_clipping():
    import pytest
    from scripts.live_deployment_smoke import _validate_tab_bar_layout

    good_tabs = [
        {
            "label": "Sign In",
            "left": 0, "right": 118, "clientWidth": 118, "scrollWidth": 118,
            "clientHeight": 42, "scrollHeight": 42,
            "labelLeft": 8, "labelRight": 110,
            "labelClientWidth": 102, "labelScrollWidth": 102,
            "labelClientHeight": 18, "labelScrollHeight": 18,
            "whiteSpace": "normal", "labelWhiteSpace": "normal",
        },
        {
            "label": "Get Ticket & Register",
            "left": 0, "right": 390, "clientWidth": 390, "scrollWidth": 390,
            "clientHeight": 58, "scrollHeight": 58,
            "labelLeft": 8, "labelRight": 382,
            "labelClientWidth": 374, "labelScrollWidth": 374,
            "labelClientHeight": 34, "labelScrollHeight": 34,
            "whiteSpace": "normal", "labelWhiteSpace": "normal",
        },
        {
            "label": "Explore the Modules",
            "left": 0, "right": 390, "clientWidth": 390, "scrollWidth": 390,
            "clientHeight": 58, "scrollHeight": 58,
            "labelLeft": 8, "labelRight": 382,
            "labelClientWidth": 374, "labelScrollWidth": 374,
            "labelClientHeight": 34, "labelScrollHeight": 34,
            "whiteSpace": "normal", "labelWhiteSpace": "normal",
        },
    ]
    layout = {
        "listLeft": 0, "listRight": 390,
        "clientWidth": 390, "scrollWidth": 390,
        "tabCount": 3, "tabs": good_tabs,
    }
    _validate_tab_bar_layout(layout, 390)

    horizontally_scrolling = {**layout, "scrollWidth": 520}
    with pytest.raises(AssertionError, match="horizontal scrolling"):
        _validate_tab_bar_layout(horizontally_scrolling, 390)

    clipped_label = {**layout, "tabs": [dict(tab) for tab in good_tabs]}
    clipped_label["tabs"][1]["scrollWidth"] = clipped_label["tabs"][1]["clientWidth"] + 12
    with pytest.raises(AssertionError, match="horizontally clipped"):
        _validate_tab_bar_layout(clipped_label, 390)

    vertically_clipped_label = {**layout, "tabs": [dict(tab) for tab in good_tabs]}
    vertically_clipped_label["tabs"][1]["scrollHeight"] = vertically_clipped_label["tabs"][1]["clientHeight"] + 12
    with pytest.raises(AssertionError, match="vertically clipped"):
        _validate_tab_bar_layout(vertically_clipped_label, 390)


def test_tab_bar_layout_validator_allows_desktop_whitespace_when_not_clipped():
    from scripts.live_deployment_smoke import _validate_tab_bar_layout

    tabs = [
        {
            "label": name, "left": left, "right": right,
            "clientWidth": right - left, "scrollWidth": right - left,
            "clientHeight": 44, "scrollHeight": 44,
            "labelLeft": left + 8, "labelRight": right - 8,
            "labelClientWidth": right - left - 16, "labelScrollWidth": right - left - 16,
            "labelClientHeight": 28, "labelScrollHeight": 28,
            "whiteSpace": "nowrap", "labelWhiteSpace": "nowrap",
        }
        for name, left, right in [
            ("Sign In", 0, 150),
            ("Get Ticket & Register", 150, 380),
            ("Explore the Modules", 380, 600),
        ]
    ]
    layout = {
        "listLeft": 0, "listRight": 1440,
        "clientWidth": 1440, "scrollWidth": 1440,
        "tabCount": 3, "tabs": tabs,
    }
    _validate_tab_bar_layout(layout, 1440)



def test_local_runtime_smoke_covers_all_three_release_viewports():
    smoke = (ROOT / "scripts" / "live_deployment_smoke.py").read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert '("desktop", {"width": 1440, "height": 1000})' in smoke
    assert '("tablet", {"width": 768, "height": 1024})' in smoke
    assert '("mobile", {"width": 390, "height": 844})' in smoke
    assert "artifacts/live-deployment-smoke/desktop.png" in workflow
    assert "artifacts/live-deployment-smoke/tablet.png" in workflow
    assert "artifacts/live-deployment-smoke/mobile.png" in workflow
