import pandas as pd

from shoir_industrial_decision_os import (
    CANONICAL_ENTITY_TYPES,
    benchmark_manual_record,
    canonical_thread_contract,
    canonical_control_tower_state,
    connector_health_evidence,
    connector_schedule_spec,
    decision_value_record,
    run_standard_benchmark_suite,
    test_connector_profile as run_connector_profile,
    visualization_contract_report,
)


def test_canonical_thread_contract_contains_operational_spine():
    contract = canonical_thread_contract()
    assert "Product" in CANONICAL_ENTITY_TYPES
    assert "Material" in CANONICAL_ENTITY_TYPES
    assert "Order" in CANONICAL_ENTITY_TYPES
    assert "Workforce" in CANONICAL_ENTITY_TYPES
    assert "Quality" in CANONICAL_ENTITY_TYPES
    assert "Maintenance" in CANONICAL_ENTITY_TYPES
    assert "Energy" in CANONICAL_ENTITY_TYPES
    assert "Cost" in CANONICAL_ENTITY_TYPES
    assert {"Scenario", "Decision", "Outcome"} <= set(CANONICAL_ENTITY_TYPES)
    assert contract["source_of_truth"].startswith("workspace digital thread")


def test_connector_adapter_rejects_unsafe_and_unknown_protocols():
    invalid_rest = run_connector_profile({
        "name": "bad",
        "system_type": "REST",
        "protocol": "REST",
        "endpoint": "not-a-url",
    })
    assert invalid_rest.status == "FAIL"

    unknown = run_connector_profile({
        "name": "bad",
        "system_type": "Unknown",
        "protocol": "TELNET",
        "endpoint": "telnet://example.invalid",
    })
    assert unknown.status == "FAIL"


def test_decision_value_record_math(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    aid = decision_value_record(
        "tester",
        "DEC-1",
        "Capacity decision",
        "Throughput",
        100.0,
        92.0,
        "units/hr",
        "Measured",
        "Post implementation observation.",
    )
    assert aid.startswith("DVL-")


def test_benchmark_record_math(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    aid = benchmark_manual_record(
        "tester",
        "Manual vs Shoir runtime",
        "Minutes",
        60.0,
        15.0,
        "min",
        True,
    )
    assert aid.startswith("ART-")


def test_standard_runtime_benchmark_returns_measurement_frame():
    result = run_standard_benchmark_suite()
    assert not result.empty
    assert {"benchmark_name", "status"}.issubset(result.columns)
    assert set(result["status"]) <= {"Measured", "Failed"}


def test_visualization_contract_audits_catalog():
    report = visualization_contract_report()
    assert not report.empty
    assert report["Visualization contract"].eq("Universal").all()
    assert report["Status"].notna().all()


def test_structural_workflow_figure_is_available_without_data():
    from shoir_industrial_decision_os import structural_workflow_figure
    fig = structural_workflow_figure("Empty Module")
    assert fig is not None
    assert len(fig.data) >= 1


def test_canonical_control_tower_state_uses_thread_entities(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(
        st,
        "session_state",
        {
            "global_thread_nodes": [
                {"node_type": "Process", "updated_at": "2026-09-26T00:00:00+00:00", "status": "Observed"},
                {"node_type": "Order", "updated_at": "2026-09-26T00:01:00+00:00", "status": "Observed"},
                {"node_type": "Quality", "updated_at": "2026-09-26T00:02:00+00:00", "status": "Observed"},
            ]
        },
    )
    state = canonical_control_tower_state()
    assert state["Production"]["records"] == 2
    assert state["Quality"]["records"] == 1
    assert state["Production"]["source"] == "Digital Thread"
    assert state["Maintenance"]["status"] == "No Data"


def test_connector_health_evidence_preserves_latency_and_detail(monkeypatch):
    captured = {}

    def fake_record(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "CONN-TEST"

    import shoir_enterprise_layer
    monkeypatch.setattr(shoir_enterprise_layer, "record_connector_health", fake_record)

    evidence = connector_health_evidence(
        "tester",
        {"name": "REST API", "system_type": "ERP", "endpoint": "https://example.com"},
        type("Result", (), {
            "status": "PASS",
            "protocol": "REST",
            "latency_ms": 12.5,
            "message": "HTTP 200",
            "rows": 4,
            "columns": 2,
        })(),
    )
    assert captured["args"][6] == "HTTP 200"
    assert captured["args"][7] == 12.5
    assert captured["kwargs"]["workspace"] == "default"
    assert evidence["Latency (ms)"] == 12.5
    assert evidence["Detail"] == "HTTP 200"


def test_connector_schedule_spec_is_explicit_about_execution_mode():
    scheduled = connector_schedule_spec({"schedule_enabled": True, "sync_interval_minutes": 15})
    assert scheduled["enabled"] is True
    assert scheduled["interval_minutes"] == 15
    assert scheduled["mode"] == "Application-triggered schedule"


def test_visualization_suite_handles_categorical_only_data():
    from shoir_live_visuals import build_visualization_suite
    frame = pd.DataFrame({"Station": ["A", "A", "B", "C", "C"]})
    suite = build_visualization_suite(frame, context="Categorical Test", max_figures=3)
    assert suite
    assert any("Category distribution" in label for label, _ in suite)


def test_visualization_suite_handles_sparse_numeric_data():
    from shoir_live_visuals import build_visualization_suite
    frame = pd.DataFrame({"KPI": [None, None, None], "Status": ["Missing", "Missing", "Missing"]})
    suite = build_visualization_suite(frame, context="Sparse Test", max_figures=3)
    assert suite
