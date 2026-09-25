import numpy as np
import pandas as pd

from shoir_engine_studio import (
    analyze_factorial,
    bootstrap_difference,
    build_factorial_design,
    effect_size,
    forecast_series,
    monte_carlo_uncertainty,
    pareto_candidates,
    robust_stochastic_scenario_analysis,
    sensitivity_screen,
    solve_lp_or_milp,
    solve_nonlinear_quadratic,
    summarize_replications,
)


def test_factorial_design_and_effect_model():
    factors = pd.DataFrame({
        "Factor": ["A", "B"],
        "Low": [0, 10],
        "High": [1, 20],
    })
    design = build_factorial_design(factors, center_points=1, replications=2, seed=7)
    assert len(design) == 10
    response = 10 + 2 * design["__code__A"] + 3 * design["__code__B"] + 1 * design["__code__A"] * design["__code__B"]
    design["Response"] = response
    effects, fitted, summary = analyze_factorial(design, "Response", ["A", "B"])
    assert len(fitted) == len(design)
    assert summary["R2"] > 0.99
    terms = dict(zip(effects["Term"], effects["Effect (2×coef)"]))
    assert abs(terms["A"] - 4.0) < 1e-8
    assert abs(terms["B"] - 6.0) < 1e-8
    assert abs(terms["A × B"] - 2.0) < 1e-8


def test_bootstrap_effect_and_reproducibility():
    a = [10, 11, 9, 12, 10, 13]
    b = [8, 9, 10, 8, 7, 9]
    first, summary1 = bootstrap_difference(a, b, iterations=1000, seed=123)
    second, summary2 = bootstrap_difference(a, b, iterations=1000, seed=123)
    pd.testing.assert_frame_equal(first, second)
    assert summary1["Observed Difference (A-B)"] > 0
    assert summary1 == summary2
    assert effect_size(a, b)["Cohen's d"] > 0


def test_monte_carlo_uncertainty_and_sensitivity():
    specs = pd.DataFrame({
        "Name": ["x", "y"],
        "Mean": [10.0, 5.0],
        "Std": [1.0, 0.5],
        "Distribution": ["Normal", "Uniform"],
        "Low": [7.0, 4.0],
        "High": [13.0, 6.0],
        "Coefficient": [2.0, -1.0],
    })
    samples, summary = monte_carlo_uncertainty(specs, simulations=1000, seed=5, intercept=3)
    assert len(samples) == 1000
    assert "Output" in samples.columns
    assert summary["P95"] >= summary["P50"]
    sens = sensitivity_screen(pd.DataFrame({"x": [1, 2, 3, 4], "y": [4, 8, 12, 16], "z": [16, 12, 8, 4]}), "y", ["x", "z"])
    assert sens.iloc[0]["Driver"] in {"x", "z"}
    assert sens["Sensitivity"].max() > 0.99


def test_replication_summary():
    df = pd.DataFrame({"Replication": [1, 2, 3, 4], "Metric": [10, 12, 11, 13]})
    grouped, overall = summarize_replications(df, "Metric")
    assert len(grouped) == 4
    assert overall["Replications"] == 4
    assert overall["CI Upper"] > overall["CI Lower"]


def test_time_aware_forecast_outputs_validation_metrics():
    df = pd.DataFrame({
        "Date": pd.date_range("2024-01-01", periods=24, freq="MS"),
        "Demand": np.linspace(100, 200, 24) + 5 * np.sin(np.arange(24)),
        "Promotion": [0, 1, 0, 0] * 6,
    })
    result, metrics = forecast_series(df, "Date", "Demand", ["Promotion"], horizon=6)
    assert len(result) == 30
    assert result["Forecast"].notna().sum() == 6
    assert "Validation RMSE" in metrics
    assert "Future Driver Assumption" in metrics


def test_lp_milp_and_nonlinear_solvers():
    variables = pd.DataFrame({
        "Variable": ["x", "y"],
        "Objective Coef": [1.0, 2.0],
        "Lower": [0.0, 0.0],
        "Upper": [20.0, 20.0],
        "Integer": [False, False],
        "Binary": [False, False],
    })
    constraints = pd.DataFrame({
        "Constraint": ["minimum"],
        "Sense": [">="],
        "RHS": [10.0],
        "x": [1.0],
        "y": [1.0],
    })
    sol, summary = solve_lp_or_milp(variables, constraints, "min", "LP")
    assert summary["Status"] == "Optimal"
    assert abs(sol.loc[sol["Variable"] == "x", "Value"].iloc[0] - 10.0) < 1e-6

    milp_vars = variables.copy()
    milp_vars["Integer"] = True
    milp_sol, milp_summary = solve_lp_or_milp(milp_vars, constraints, "min", "MILP")
    assert milp_summary["Status"] == "Optimal"
    assert abs(milp_sol["Value"].sum() - 10.0) < 1e-6

    nl_vars = pd.DataFrame({
        "Variable": ["x", "y"],
        "Linear Coef": [0.0, 0.0],
        "Quadratic Coef": [2.0, 2.0],
        "Lower": [0.0, 0.0],
        "Upper": [10.0, 10.0],
    })
    nl_sol, nl_summary = solve_nonlinear_quadratic(nl_vars, constraints, "min")
    assert nl_summary["Status"] == "Converged"
    assert abs(nl_sol["Value"].sum() - 10.0) < 1e-4


def test_pareto_and_robust_stochastic_worst_case_direction():
    candidates = pd.DataFrame({"Scenario": ["A", "B", "C"], "Cost": [100, 90, 120], "Service": [95, 97, 99]})
    pareto = pareto_candidates(candidates, {"Cost": True, "Service": False})
    assert len(pareto) == 2

    states = pd.DataFrame({
        "Decision": ["A", "A", "B", "B"],
        "State": ["Base", "Shock", "Base", "Shock"],
        "Probability": [0.8, 0.2, 0.8, 0.2],
        "Cost": [100, 200, 120, 150],
        "Service": [95, 80, 94, 90],
    })
    summary, scored = robust_stochastic_scenario_analysis(
        states, "Decision", "State", ["Cost", "Service"], {"Cost": True, "Service": False}, "Probability"
    )
    a = summary.loc[summary["Decision"] == "A"].iloc[0]
    b = summary.loc[summary["Decision"] == "B"].iloc[0]
    assert a["Worst Cost"] == 200
    assert a["Worst Service"] == 80
    assert b["Worst Cost"] == 150
    assert b["Worst Service"] == 90
    assert "Robust Composite" in scored.columns
