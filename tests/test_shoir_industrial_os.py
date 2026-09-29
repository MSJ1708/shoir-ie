from pathlib import Path

import pytest
import numpy as np
import pandas as pd

from shoir_industrial_os import (
    CAPABILITY_STATES,
    WORKFLOW_STEPS,
    benchmark_snapshot,
    compare_scenarios,
    dataframe_digest,
    deep_data_quality,
    factorial_design,
    holm_adjust,
    module_manifest,
    monte_carlo_summary,
    problem_solver,
    profile_data,
    residual_diagnostics,
    schema_drift,
    uncertainty_summary,
    verification_report,
    visualization_recommendations,
)


def test_universal_lifecycle_is_complete():
    assert WORKFLOW_STEPS == (
        "DATA", "VALIDATE", "MAP", "MODEL", "RUN", "VISUALIZE",
        "COMPARE", "EXPLAIN", "DECIDE", "EXPORT", "VERIFY",
    )


def test_manifest_is_machine_readable():
    manifest = module_manifest("Capacity Optimizer")
    assert manifest["identity"] == "Capacity Optimizer"
    assert manifest["contract_version"] == "2.0"
    assert manifest["workflow"] == list(WORKFLOW_STEPS)
    assert manifest["scenario_support"] is True
    assert manifest["persistence"] is True


def test_profile_and_digest_are_deterministic():
    df = pd.DataFrame({"Asset": ["A", "B", "B"], "Qty": [10, np.nan, 12]})
    first = profile_data(df)
    second = profile_data(df)
    assert first["rows"] == 3
    assert first["missing_cells"] == 1
    assert first["duplicate_rows"] == 0
    assert first["readiness"] == second["readiness"]
    assert len(dataframe_digest(df)) == 64


def test_quality_and_schema_drift_detection():
    previous = pd.DataFrame({"Asset": ["A"], "Qty": [1]})
    current = pd.DataFrame({"Asset": ["A"], "Qty": ["1"], "Energy": [4.2]})
    quality = deep_data_quality(current)
    drift = schema_drift(current, previous)
    assert not quality.empty
    assert drift["status"] == "DRIFT"
    assert "Energy" in drift["added"]
    assert drift["dtype_changes"]


def test_visualization_recommendations_are_data_driven():
    df = pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=5),
        "Throughput": [100, 102, 101, 104, 106],
        "Defects": [3, 2, 4, 1, 2],
        "Line": ["A", "A", "B", "B", "B"],
    })
    names = {x["chart"] for x in visualization_recommendations(df)}
    assert "time_series" in names
    assert "distribution" in names
    assert "grouped_summary" in names


def test_scenario_comparison_has_delta_and_percent_change():
    result = compare_scenarios(
        {"Baseline": {"Throughput": 100, "Cost": 50}, "A": {"Throughput": 110, "Cost": 45}},
        baseline="Baseline",
    )
    row = result[(result["Scenario"] == "A") & (result["KPI"] == "Throughput")].iloc[0]
    assert row["Delta"] == 10
    assert round(row["% Change"], 4) == 10


def test_uncertainty_contains_percentiles_and_probability():
    summary = uncertainty_summary([1, 2, 3, 4, 5], threshold=3)
    assert summary["p10"] <= summary["p50"] <= summary["p90"]
    assert 0 <= summary["probability_above"]["3.0"] <= 1


def test_factorial_design_and_multiple_comparison():
    design = factorial_design({"Speed": [10, 20], "Feed": [1, 2, 3]})
    assert design.shape == (6, 2)
    adjusted = holm_adjust([0.01, 0.04, 0.20])
    assert adjusted[0] <= adjusted[1] <= adjusted[2]


def test_residual_diagnostics_and_verification():
    diag = residual_diagnostics([10, 11, 9], [9, 10, 10])
    assert diag["n"] == 3
    assert diag["mae"] > 0
    report = verification_report(pd.DataFrame({"x": [1, 2, 3]}), {"status": "Completed"})
    assert report["status"] == "PASS"


def test_problem_solver_routes_common_operational_problem():
    plan = problem_solver(
        "We have late customer orders and limited machine capacity.",
        ["Capacity Analysis", "Production Scheduling", "Optimization", "Quality"],
    )
    assert plan["goal"] == "Improve Delivery"
    assert "Capacity / Scheduling" in plan["workflow"]
    assert "constraints" in plan["required_signals"]


def test_benchmark_snapshot_is_neutral_delta():
    result = benchmark_snapshot({"Throughput": 95}, {"Throughput": 100})
    assert result.iloc[0]["Delta"] == -5
    assert result.iloc[0]["% vs benchmark"] == -5


def test_app_integrates_complete_os_surface():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "from shoir_industrial_os import render_platform_os_surface" in source
    assert "render_platform_os_surface(" in source


def test_catalog_has_explicit_maturity_states():
    assert CAPABILITY_STATES == ("Verified", "Implemented", "Foundation", "Integration-ready")

def test_monte_carlo_rejects_arbitrary_python():
    with pytest.raises(ValueError):
        monte_carlo_summary({"X": {"distribution": "normal", "mean": 1, "std": 0.1}}, "__import__('os').system('echo unsafe')", samples=100)
