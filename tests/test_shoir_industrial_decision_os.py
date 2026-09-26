import pandas as pd

from shoir_industrial_decision_os import (
    CANONICAL_ENTITY_TYPES,
    benchmark_manual_record,
    canonical_thread_contract,
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
