import io
import zipfile

import pandas as pd

from shoir_copilot_orchestrator import (
    WORKFLOW_STEPS,
    build_graph,
    build_workflow_plan,
    classify_request,
    compare_scenarios,
    inspect_data,
    recommend_module,
    run_analysis,
)


def test_request_classification_routes_common_ie_goals():
    assert classify_request("forecast SKU demand")["intent"] == "forecast"
    assert classify_request("compare baseline to scenario B")["intent"] == "compare"
    assert classify_request("find correlations between drivers")["intent"] == "relationship"
    assert classify_request("analyze defect quality")["intent"] == "quality"
    assert classify_request("optimize routing")["intent"] == "optimization"


def test_module_router_uses_live_module_names():
    module, reason = recommend_module(
        "I need to forecast demand",
        ["Quality Engineering & Reliability", "Advanced ML Demand Forecasting"],
    )
    assert module == "Advanced ML Demand Forecasting"
    assert reason


def test_plan_is_reviewable_before_execution():
    df = pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=8), "Demand": range(10, 18)})
    plan = build_workflow_plan("forecast demand", "Advanced ML Demand Forecasting", df)
    assert plan["requires_approval"] is True
    assert [x["step"] for x in plan["steps"]] == WORKFLOW_STEPS
    assert plan["method"]["method"] == "Demand forecast"


def test_scenario_comparison_handles_scenario_column():
    df = pd.DataFrame(
        {
            "Scenario": ["Baseline", "Baseline", "Scenario B", "Scenario B"],
            "Cost": [100, 120, 90, 95],
            "Service": [95, 96, 97, 98],
        }
    )
    result, meta = compare_scenarios(df)
    assert meta["mode"] == "grouped"
    assert set(result["Scenario"]) == {"Baseline", "Scenario B"}


def test_descriptive_analysis_and_graph_are_grounded_in_data():
    df = pd.DataFrame({"Line": ["A", "B", "C"], "Throughput": [10, 20, 30], "Cost": [5, 7, 9]})
    inspection = inspect_data(df)
    method = {"method": "Descriptive engineering profile"}
    result, meta = run_analysis(df, "descriptive", method)
    assert inspection["rows"] == 3
    assert meta["type"] == "descriptive"
    assert "Measure" in result.columns
    fig = build_graph(result, meta["type"])
    assert fig is not None
    assert fig.data


def test_export_bundle_contains_auditable_artifacts():
    from shoir_copilot_orchestrator import build_export_bundle

    df = pd.DataFrame({"Line": ["A", "B"], "Throughput": [10, 20]})
    inspection = inspect_data(df)
    method = {"method": "Descriptive engineering profile"}
    result, _ = run_analysis(df, "descriptive", method)
    fig = build_graph(result)
    bundle = build_export_bundle(
        "profile this dataset",
        "Engineering Validation Center",
        "COP-TEST123",
        inspection,
        method,
        result,
        "Evidence summary",
        fig,
    )
    with zipfile.ZipFile(io.BytesIO(bundle), "r") as zf:
        names = set(zf.namelist())
        assert "request.txt" in names
        assert "inspection.json" in names
        assert "method.json" in names
        assert "results.csv" in names
        assert "explanation.md" in names
        assert "copilot_analysis.xlsx" in names
        assert "manifest.json" in names


def test_optimization_can_use_existing_solver_hook():
    df = pd.DataFrame({"Signal": ["network"], "Cost": [10], "Capacity": [100]})
    calls = {}

    def fake_validate(customers, warehouses):
        return True, "Validated"

    def fake_solver(customers_tuple, warehouses_tuple, w_cost, w_carbon):
        calls["called"] = True
        return "Optimal", 1234.0, 56.0, [
            {"Customer": "C1", "Assigned Warehouse": "W1", "Haversine Cost ($)": 12.5}
        ]

    from shoir_copilot_orchestrator import run_orchestration

    run = run_orchestration(
        "optimize my network",
        "MILP Solvers",
        df,
        context={
            "customers": [{"Customer": "C1", "lat": 1.0, "lon": 1.0, "Demand": 10}],
            "warehouses": [{"name": "W1", "lat": 1.1, "lon": 1.1, "capacity": 100, "fixed_cost": 500}],
            "milp_solver": fake_solver,
            "validate_network_inputs": fake_validate,
        },
    )
    assert calls["called"] is True
    assert run["analysis_meta"]["type"] == "milp_optimization"
    assert run["analysis_meta"]["solver_status"] == "Optimal"
    assert float(run["analysis_meta"]["total_cost"]) == 1234.0
    assert not run["result"].empty


def test_plan_can_expose_linked_knowledge_context_count():
    df = pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=8), "Demand": range(10, 18)})
    plan = build_workflow_plan("forecast demand using the SOP context", "Advanced ML Demand Forecasting", df, knowledge_documents=3)
    assert "3 linked knowledge document(s)" in plan["steps"][5]["detail"]


def test_export_bundle_carries_linked_knowledge():
    from shoir_copilot_orchestrator import build_export_bundle

    df = pd.DataFrame({"Line": ["A", "B"], "Throughput": [10, 20]})
    inspection = inspect_data(df)
    method = {"method": "Descriptive engineering profile"}
    result, _ = run_analysis(df, "descriptive", method)
    fig = build_graph(result)
    bundle = build_export_bundle(
        "use linked SOP context",
        "Engineering Validation Center",
        "COP-KNOWLEDGE",
        inspection,
        method,
        result,
        "Evidence summary",
        fig,
        "SOP: verify data units before analysis.",
    )
    with zipfile.ZipFile(io.BytesIO(bundle), "r") as zf:
        assert "knowledge_context.txt" in zf.namelist()
        assert b"verify data units" in zf.read("knowledge_context.txt")
