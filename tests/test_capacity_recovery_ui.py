"""Integration-contract tests for the capacity recovery workflow wiring."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_capacity_recovery_is_inside_the_existing_enterprise_os():
    source = (ROOT / "industrial_operating_system.py").read_text(encoding="utf-8")
    renderer = (ROOT / "shoir_capacity_recovery_ui.py").read_text(encoding="utf-8")
    assert '"🧰 Bottleneck Recovery"' in source
    assert "with tabs[10]:" in source
    assert "render_capacity_recovery_workspace(tier, username)" in source
    for contract in (
        "analyze_capacity_recovery(stations, demand_units, yield_pct)",
        "map_imported_station_data(imported_frame, mapping)",
        "save_capacity_study(",
        "list_capacity_studies(username)",
        "record_capacity_outcome(",
        "render_exports(",
        "os_capacity_loaded_study",
    ):
        assert contract in renderer


def test_capacity_recovery_import_guardrails_are_visible_in_the_ui():
    workflow = (ROOT / "shoir_capacity_recovery_ui.py").read_text(encoding="utf-8")
    assert 'type=["csv", "xlsx"]' in workflow
    assert "10 * 1024 * 1024" in workflow
    assert "len(imported_frame) > 1000" in workflow
    assert "Apply validated column mapping" in workflow
    assert "optional" in workflow.lower()
    assert "synthetic demonstration data" in workflow.lower()


def test_capacity_recovery_documentation_explains_scope_and_evidence_limits():
    docs = (ROOT / "docs" / "INDUSTRIAL_ENGINEERING_OS.md").read_text(encoding="utf-8")
    assert "Production Bottleneck & Capacity Recovery Study" in docs
    assert "not a discrete-event simulation" in docs
    assert "not independently authenticated" in docs
    assert "input/result hashes" in docs
