import numpy as np
import pandas as pd
import pytest

from shoir_engineering_os import (
    INDUSTRY_PROFILES,
    METHOD_LIBRARY,
    PERSONA_VIEWS,
    RESOURCE_FAMILIES,
    WORKFLOW_STAGES,
    classify_industrial_problem,
    event_contract,
    method_library_frame,
    operating_system_contract,
    pareto_tradeoff_flags,
    resource_efficiency_analysis,
    scenario_tradeoff_matrix,
    verification_table,
)


def test_os_catalogs_are_present_and_nonempty():
    assert len(WORKFLOW_STAGES) == 10
    assert len(METHOD_LIBRARY) >= 75
    assert len(RESOURCE_FAMILIES) == 8
    assert INDUSTRY_PROFILES
    assert PERSONA_VIEWS
    frame = method_library_frame()
    assert {"Method", "Category", "Authority", "Coverage"} <= set(frame.columns)


def test_problem_solver_routes_to_existing_engine_families():
    plan = classify_industrial_problem(
        "Throughput fell because bottleneck downtime increased and quality defects rose.",
        "Manufacturing Execution System",
    )
    assert plan["intent"] in {"throughput", "quality", "downtime"}
    assert "Simulation" in plan["methods"] or "Bottleneck Analysis" in plan["methods"]
    assert "Engineering Decision Center" in plan["candidate_modules"]
    assert plan["workflow"] == list(WORKFLOW_STAGES)


def test_resource_analysis_is_evidence_driven():
    df = pd.DataFrame(
        {
            "Operator Hours": [8, 9],
            "Machine Utilization": [0.8, 0.9],
            "Inventory Qty": [100, 120],
            "Cycle Time": [4.0, 5.0],
            "Energy kWh": [200, 220],
            "Unit Cost": [10, 11],
        }
    )
    result, gaps = resource_efficiency_analysis(df)
    assert not result.empty
    assert float(result.loc[result["Resource Family"].eq("Energy"), "Total"].iloc[0]) == 420.0
    assert "Carbon / Waste" in gaps
    assert "People / Labor" in set(result["Resource Family"])


def test_scenario_tradeoff_is_baseline_relative_without_ranking():
    df = pd.DataFrame(
        {
            "Scenario": ["Baseline", "A", "B"],
            "Cost": [100, 90, 110],
            "Throughput": [100, 105, 120],
            "Risk": [5, 6, 4],
        }
    )
    result = scenario_tradeoff_matrix(df, "Scenario", ["Cost", "Throughput", "Risk"])
    assert list(result["Scenario"]) == ["Baseline", "A", "B"]
    assert float(result.loc[result["Scenario"].eq("A"), "Cost Δ"].iloc[0]) == -10.0
    assert float(result.loc[result["Scenario"].eq("A"), "Throughput Δ %"].iloc[0]) == 5.0


def test_pareto_flags_support_mixed_objectives():
    df = pd.DataFrame({"Cost": [100, 90, 110], "Throughput": [100, 95, 120]})
    result = pareto_tradeoff_flags(df, {"Cost": True, "Throughput": False})
    assert "Pareto" in result.columns
    assert result["Pareto"].sum() >= 1


def test_expected_vs_actual_verification_is_explicit():
    result = verification_table(
        {"Throughput": 100, "Cost": 50},
        {"Throughput": 94, "Cost": 52},
        tolerance=0.05,
    )
    assert set(result["KPI"]) == {"Throughput", "Cost"}
    assert float(result.loc[result["KPI"].eq("Throughput"), "Delta"].iloc[0]) == -6.0
    assert result.loc[result["KPI"].eq("Throughput"), "Status"].iloc[0] == "Outside tolerance"


def test_event_contract_is_whitelisted():
    event = event_contract("result_verified", "Quality", {"kpi": "Cpk", "value": 1.33})
    assert event["event"] == "result_verified"
    with pytest.raises(ValueError):
        event_contract("delete_everything", "Quality", {})


def test_operating_system_contract_does_not_claim_execution():
    frame = pd.DataFrame({"Scenario": ["Baseline"], "Value": [1.0]})
    report = operating_system_contract("Test", frame, session_state={})
    assert list(report["Stage"]) == list(WORKFLOW_STAGES)
    assert not bool(report.loc[report["Stage"].eq("Execute"), "Ready"].iloc[0])
