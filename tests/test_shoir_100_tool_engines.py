"""Golden and boundary fixtures for native Shoir-IE Tool Library calculations."""
from __future__ import annotations

import math

import pytest

from shoir_100_tool_engines import (
    fit_weibull_uncensored,
    inventory_policy,
    monte_carlo_independent_sum,
    mtbf_mttr,
    work_sampling,
)


def test_work_sampling_percent_and_wilson_interval_are_consistent():
    result = work_sampling(35, 100, 0.95)
    assert result["percent"] == pytest.approx(35.0)
    assert result["proportion"] == pytest.approx(0.35)
    assert 0.25 < result["ci_lower"] < 0.35 < result["ci_upper"] < 0.45
    assert result["ci_lower"] <= result["proportion"] <= result["ci_upper"]
    assert result["method"].startswith("Wilson score interval")


@pytest.mark.parametrize(
    ("activity", "total", "confidence"),
    [(-1, 10, 0.95), (11, 10, 0.95), (1, 0, 0.95), (1.2, 10, 0.95), (1, 10, 0.92)],
)
def test_work_sampling_rejects_invalid_counts_and_confidence(activity, total, confidence):
    with pytest.raises(ValueError):
        work_sampling(activity, total, confidence)


def test_weibull_fit_returns_positive_parameters_and_descriptive_diagnostics():
    result = fit_weibull_uncensored([10, 14, 17, 22, 27, 29, 32, 37, 40, 43])
    assert result["shape"] > 0
    assert result["scale"] > 0
    assert result["median_life"] > 0
    assert 0 <= result["ks_distance_descriptive"] <= 1
    assert len(result["sorted_times"]) == len(result["fitted_cdf"]) == 10
    assert result["censoring_supported"] is False
    assert all(a <= b for a, b in zip(result["fitted_cdf"], result["fitted_cdf"][1:]))


@pytest.mark.parametrize("times", [[], [1, 2], [0, 1, 2], [1, -1, 2], [1, math.inf, 3]])
def test_weibull_fit_rejects_small_nonpositive_or_nonfinite_samples(times):
    with pytest.raises(ValueError):
        fit_weibull_uncensored(times)


def test_mtbf_and_mttr_use_operating_hours_and_each_repair_episode():
    result = mtbf_mttr(1000, 4, [1, 2, 3, 4])
    assert result["mtbf_hours"] == pytest.approx(250.0)
    assert result["mttr_hours"] == pytest.approx(2.5)
    assert result["repair_count"] == 4


@pytest.mark.parametrize(
    ("uptime", "count", "repairs"),
    [(0, 1, [1]), (100, 0, []), (100, 2, [1]), (100, 1, [-1])],
)
def test_mtbf_mttr_reject_invalid_operating_or_repair_data(uptime, count, repairs):
    with pytest.raises(ValueError):
        mtbf_mttr(uptime, count, repairs)


def test_inventory_policy_matches_hand_calculated_eoq_and_reorder_point():
    result = inventory_policy(
        annual_demand=10000,
        order_cost=25,
        annual_holding_cost_per_unit=4,
        mean_demand_per_period=100,
        std_demand_per_period=20,
        lead_time_periods=4,
        service_z=1.645,
    )
    assert result["eoq_units"] == pytest.approx(math.sqrt(125000))
    assert result["safety_stock_units"] == pytest.approx(65.8)
    assert result["expected_lead_time_demand_units"] == pytest.approx(400)
    assert result["reorder_point_units"] == pytest.approx(465.8)


@pytest.mark.parametrize(
    "args",
    [
        (0, 25, 4, 100, 20, 4, 1.645),
        (10000, 25, 0, 100, 20, 4, 1.645),
        (10000, 25, 4, 100, -1, 4, 1.645),
        (10000, 25, 4, 100, 20, 0, 1.645),
    ],
)
def test_inventory_policy_rejects_invalid_assumptions(args):
    with pytest.raises(ValueError):
        inventory_policy(*args)


def test_monte_carlo_is_seed_reproducible_and_reports_distributions():
    drivers = {
        "normal_component": {"distribution": "normal", "mean": 100.0, "sd": 15.0},
        "range_component": {"distribution": "uniform", "low": 0.0, "high": 50.0},
        "triangular_component": {"distribution": "triangular", "low": 10.0, "mode": 20.0, "high": 30.0},
    }
    first = monte_carlo_independent_sum(drivers, iterations=2000, seed=123)
    second = monte_carlo_independent_sum(drivers, iterations=2000, seed=123)
    assert first["outcomes"] == second["outcomes"]
    assert first["mean"] == pytest.approx(second["mean"])
    assert first["p05"] <= first["p50"] <= first["p95"]
    assert first["iterations"] == 2000
    assert first["seed"] == 123
    assert set(first["input_sensitivity_correlation"]) == set(drivers)


@pytest.mark.parametrize(
    ("drivers", "iterations", "seed"),
    [
        ({}, 1000, 42),
        ({"risk": {"distribution": "unknown"}}, 1000, 42),
        ({"risk": {"distribution": "uniform", "low": 10, "high": 0}}, 1000, 42),
        ({"risk": {"distribution": "triangular", "low": 1, "mode": 5, "high": 2}}, 1000, 42),
        ({"risk": {"distribution": "normal", "mean": 1, "sd": -1}}, 1000, 42),
        ({"risk": {"distribution": "normal", "mean": 1, "sd": 1}}, 99, 42),
    ],
)
def test_monte_carlo_rejects_invalid_distributions_and_run_settings(drivers, iterations, seed):
    with pytest.raises(ValueError):
        monte_carlo_independent_sum(drivers, iterations, seed)
