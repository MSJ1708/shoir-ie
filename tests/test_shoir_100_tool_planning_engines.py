"""Hand-checkable and boundary fixtures for bounded quality/planning methods."""
from __future__ import annotations

import pytest

from shoir_100_tool_planning_engines import (
    evaluate_acceptance_sampling_plan,
    forecast_demand_series,
    plan_material_requirements,
    simulate_monte_carlo_outcome,
)


def test_acceptance_sampling_hypergeometric_risks_match_hand_checkable_fixture():
    result = evaluate_acceptance_sampling_plan(
        lot_size=100, sample_size=10, acceptance_number=0, aql_percent=1, ltpd_percent=10
    )
    metrics = result["metrics"]
    assert metrics["defectives_assumed_at_aql"] == 1
    assert metrics["probability_of_acceptance_at_aql"] == pytest.approx(0.9)
    assert metrics["producer_risk_at_aql"] == pytest.approx(0.1)
    assert metrics["defectives_assumed_at_ltpd"] == 10
    assert metrics["probability_of_acceptance_at_ltpd"] == pytest.approx(0.3305, abs=0.001)
    assert metrics["consumer_risk_at_ltpd"] == metrics["probability_of_acceptance_at_ltpd"]
    assert len(result["operating_characteristic"]) == 21
    assert all(0 <= row["probability_of_acceptance"] <= 1 for row in result["operating_characteristic"])


def test_acceptance_sampling_rejects_invalid_plan_or_risk_points():
    with pytest.raises(ValueError, match="Sample size"):
        evaluate_acceptance_sampling_plan(100, 101, 0, 1, 5)
    with pytest.raises(ValueError, match="Acceptance number"):
        evaluate_acceptance_sampling_plan(100, 10, 10, 1, 5)
    with pytest.raises(ValueError, match="AQL < LTPD"):
        evaluate_acceptance_sampling_plan(100, 10, 1, 5, 5)
    with pytest.raises(ValueError, match="whole number"):
        evaluate_acceptance_sampling_plan(100.5, 10, 1, 1, 5)


def test_forecast_comparison_uses_chronological_holdout_without_leakage():
    result = forecast_demand_series([10, 12, 14, 16, 18, 20], horizon=2, holdout_periods=2, moving_average_window=2)
    metrics = result["metrics"]
    assert metrics["naive_last_value"]["mae"] == pytest.approx(2)
    assert metrics["moving_average"]["mae"] == pytest.approx(3)
    assert metrics["selected_model_by_holdout_mae"] == "naive_last_value"
    assert [row["actual"] for row in result["backtest"]] == [18, 20]
    assert [row["naive_last_value_prediction"] for row in result["backtest"]] == [16, 18]
    assert [row["moving_average_prediction"] for row in result["backtest"]] == [15, 17]
    assert [row["selected_forecast"] for row in result["forecast"]] == [20, 20]
    assert [row["moving_average"] for row in result["forecast"]] == [19, 19.5]


def test_forecast_validation_and_zero_safe_mape():
    result = forecast_demand_series([0, 0, 1, 1, 2], horizon=1, holdout_periods=1, moving_average_window=2)
    assert result["metrics"]["naive_last_value"]["mape_percent"] is not None
    with pytest.raises(ValueError, match="cannot be negative"):
        forecast_demand_series([1, 2, -1, 4], horizon=1)
    with pytest.raises(ValueError, match="at least four"):
        forecast_demand_series([1, 2, 3], horizon=1)


def _mrp_fixture():
    return plan_material_requirements(
        bom=[
            {"parent": "PRODUCT", "component": "SUB", "quantity_per": 2},
            {"parent": "SUB", "component": "RAW", "quantity_per": 3},
        ],
        master_schedule=[{"item": "PRODUCT", "period": 4, "demand": 5}],
        horizon_periods=5,
        inventory={"PRODUCT": 0, "SUB": 0, "RAW": 0},
        lead_times={"PRODUCT": 1, "SUB": 1, "RAW": 1},
    )


def test_multilevel_mrp_explodes_components_and_offsets_lead_times():
    result = _mrp_fixture()
    plans = result["period_plans"]
    releases = result["planned_releases"]
    def at(item, period):
        return next(row for row in plans if row["item"] == item and row["period"] == period)
    assert at("PRODUCT", 4)["planned_order_receipt"] == pytest.approx(5)
    assert at("PRODUCT", 4)["planned_release_period"] == 3
    assert at("SUB", 3)["gross_requirement"] == pytest.approx(10)
    assert at("SUB", 3)["planned_release_period"] == 2
    assert at("RAW", 2)["gross_requirement"] == pytest.approx(30)
    assert at("RAW", 2)["planned_release_period"] == 1
    assert result["metrics"]["planned_order_count"] == 3
    assert {row["item"] for row in releases} == {"PRODUCT", "SUB", "RAW"}


def test_mrp_netting_uses_on_hand_and_scheduled_receipts():
    result = plan_material_requirements(
        bom=[],
        master_schedule=[{"item": "A", "period": 2, "demand": 8}],
        horizon_periods=3,
        inventory={"A": 5},
        lead_times={"A": 1},
        scheduled_receipts=[{"item": "A", "period": 2, "quantity": 2}],
    )
    row = next(r for r in result["period_plans"] if r["item"] == "A" and r["period"] == 2)
    assert row["projected_available_before_requirement"] == pytest.approx(7)
    assert row["net_requirement"] == pytest.approx(1)
    assert result["planned_releases"] == [{
        "item": "A", "release_period": 1, "receipt_period": 2,
        "quantity": 1.0, "lead_time_periods": 1,
    }]


def test_mrp_rejects_cycles_and_pre_horizon_release_instead_of_faking_plan():
    with pytest.raises(ValueError, match="cycle"):
        plan_material_requirements(
            [{"parent": "A", "component": "B", "quantity_per": 1},
             {"parent": "B", "component": "A", "quantity_per": 1}],
            [{"item": "A", "period": 2, "demand": 1}], 3,
            {"A": 0, "B": 0}, {"A": 0, "B": 0},
        )
    with pytest.raises(ValueError, match="before the planning horizon"):
        plan_material_requirements(
            [], [{"item": "A", "period": 1, "demand": 1}], 3,
            {"A": 0}, {"A": 1},
        )


def test_mrp_rejects_missing_lead_times_invalid_periods_and_negative_demand():
    with pytest.raises(ValueError, match="Lead time is missing"):
        plan_material_requirements([], [{"item": "A", "period": 2, "demand": 1}], 3, {"A": 0}, {})
    with pytest.raises(ValueError, match="Demand cannot be negative"):
        plan_material_requirements([], [{"item": "A", "period": 2, "demand": -1}], 3, {"A": 0}, {"A": 0})


def test_monte_carlo_is_reproducible_and_reports_percentiles_and_histogram():
    inputs = [
        {"name": "Demand", "distribution": "uniform", "low": 1, "high": 3, "coefficient": 2},
        {"name": "Delay", "distribution": "triangular", "low": 0, "mode": 1, "high": 4, "coefficient": -5},
    ]
    result = simulate_monte_carlo_outcome(inputs, base_outcome=100, iterations=1000, seed=17)
    again = simulate_monte_carlo_outcome(inputs, base_outcome=100, iterations=1000, seed=17)
    assert result["metrics"] == again["metrics"]
    assert result["histogram"] == again["histogram"]
    assert result["metrics"]["p05"] <= result["metrics"]["p50"] <= result["metrics"]["p95"]
    assert len(result["histogram"]) == 20
    assert sum(row["count"] for row in result["histogram"]) == 1000
    assert {row["input"] for row in result["sensitivity"]} == {"Demand", "Delay"}


def test_monte_carlo_constant_input_has_exact_outcome_and_zero_risk():
    result = simulate_monte_carlo_outcome(
        [{"name": "fixed", "distribution": "uniform", "low": 5, "high": 5, "coefficient": 2}],
        base_outcome=100, iterations=100, seed=1,
    )
    metrics = result["metrics"]
    assert metrics["mean"] == pytest.approx(110)
    assert metrics["p05"] == pytest.approx(110)
    assert metrics["p95"] == pytest.approx(110)
    assert metrics["standard_deviation"] == pytest.approx(0)
    assert metrics["probability_outcome_below_zero"] == pytest.approx(0)


def test_monte_carlo_rejects_unknown_distributions_bad_ranges_and_iteration_counts():
    with pytest.raises(ValueError, match="Unsupported distribution"):
        simulate_monte_carlo_outcome([{"name": "x", "distribution": "beta", "coefficient": 1}], 0)
    with pytest.raises(ValueError, match="cannot exceed"):
        simulate_monte_carlo_outcome([{"name": "x", "distribution": "uniform", "low": 5, "high": 1, "coefficient": 1}], 0)
    with pytest.raises(ValueError, match="cannot be negative"):
        simulate_monte_carlo_outcome([{"name": "x", "distribution": "normal", "mean": 0, "sd": -1, "coefficient": 1}], 0)
    with pytest.raises(ValueError, match="Iterations"):
        simulate_monte_carlo_outcome([{"name": "x", "distribution": "uniform", "low": 1, "high": 2, "coefficient": 1}], 0, iterations=10)


def test_planning_methods_do_not_mutate_user_inputs():
    bom=[{"parent": "P", "component": "C", "quantity_per": 2}]
    mps=[{"item": "P", "period": 2, "demand": 1}]
    original_bom=[dict(x) for x in bom]
    original_mps=[dict(x) for x in mps]
    plan_material_requirements(bom, mps, 3, {"P": 0,"C":0},{"P":0,"C":0})
    assert bom == original_bom
    assert mps == original_mps
