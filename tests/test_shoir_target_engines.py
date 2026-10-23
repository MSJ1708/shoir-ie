"""Independent fixtures and boundary tests for the focused target engines."""
from __future__ import annotations

import math

import pytest
import pandas as pd

from shoir_target_engines import (
    monitor_forecast_drift,
    plan_two_sample_t_sample_size,
    solve_cutting_stock,
)


def test_cutting_stock_known_case_and_material_reconciliation():
    # Two 6-unit pieces fit on each 12-unit stock; four parts require two stocks.
    result = solve_cutting_stock(
        12,
        [{"name": "A", "length": 6, "quantity": 4}],
        kerf=0,
    )
    assert result["status"] == "OPTIMAL"
    assert result["stock_count"] == 2
    assert result["physical_length_total"] == pytest.approx(24)
    assert result["total_stock_length"] == pytest.approx(24)
    assert result["waste_length"] == pytest.approx(0)
    assert int(result["cut_plan"]["Stocks"].sum()) == 2


def test_cutting_stock_kerf_is_applied_and_reported_explicitly():
    result = solve_cutting_stock(
        10,
        [{"name": "A", "length": 5, "quantity": 2}],
        kerf=0.2,
    )
    assert result["status"] == "OPTIMAL"
    assert result["stock_count"] == 2
    assert result["kerf_allowance_total"] == pytest.approx(0.4)
    assert result["waste_length"] == pytest.approx(9.6)


def test_cutting_stock_rejects_bad_inputs_and_reports_impossible_piece():
    with pytest.raises(ValueError, match="greater than zero"):
        solve_cutting_stock(0, [{"name": "A", "length": 1, "quantity": 1}])
    with pytest.raises(ValueError, match="whole number"):
        solve_cutting_stock(10, [{"name": "A", "length": 1, "quantity": 1.5}])
    result = solve_cutting_stock(5, [{"name": "oversize", "length": 6, "quantity": 1}])
    assert result["status"] == "INFEASIBLE"
    assert result["stock_count"] is None
    assert result["issues"][0]["part"] == "oversize"


def test_forecast_drift_monitor_has_hand_calculated_error_values():
    result = monitor_forecast_drift(
        predictions=[10, 20, 30],
        actuals=[12, 18, 33],
        max_mae=2,
    )
    assert result["status"] == "DRIFT_ALERT"
    assert result["mae"] == pytest.approx(7 / 3)
    assert result["rmse"] == pytest.approx(math.sqrt(17 / 3))
    assert result["bias_actual_minus_prediction"] == pytest.approx(1)
    assert result["mape_pct_excluding_zero_actuals"] == pytest.approx(
        (2/12 + 2/18 + 3/33) / 3 * 100
    )


def test_forecast_drift_monitor_window_and_invalid_inputs():
    result = monitor_forecast_drift([1, 100, 100], [1, 105, 101], max_mae=10, window=2)
    assert result["observations"] == 2
    assert result["status"] == "WITHIN_THRESHOLD"
    with pytest.raises(ValueError, match="same number"):
        monitor_forecast_drift([1, 2], [1], max_mae=1)
    with pytest.raises(ValueError, match="[Aa]t least two"):
        monitor_forecast_drift([1], [1], max_mae=1)
    with pytest.raises(ValueError, match="negative"):
        monitor_forecast_drift([1, 2], [1, 2], max_mae=-0.5)


def test_power_planner_matches_known_balanced_t_test_reference():
    result = plan_two_sample_t_sample_size(effect_size=0.5, alpha=0.05, target_power=0.80)
    assert result["status"] == "CALCULATED"
    assert result["required_n_per_group"] == 64
    assert result["total_sample_size"] == 128
    assert result["achieved_power"] >= 0.80
    assert result["power_at_n_minus_1"] < 0.80
    assert "no multiplicity/dropout" in result["assumptions"]


def test_power_planner_handles_search_limit_and_invalid_inputs():
    result = plan_two_sample_t_sample_size(0.01, target_power=0.99, max_n_per_group=3)
    assert result["status"] == "LIMIT_REACHED"
    assert result["required_n_per_group"] is None
    with pytest.raises(ValueError, match="greater than zero"):
        plan_two_sample_t_sample_size(0)
    with pytest.raises(ValueError, match="strictly between"):
        plan_two_sample_t_sample_size(0.5, alpha=1)



def test_time_study_uses_explicit_rating_and_allowance_convention():
    from shoir_target_engines import calculate_time_study

    result = calculate_time_study(
        [1, 2, 3], performance_rating_pct=110, allowance_pct=10, time_unit="minutes"
    )
    assert result["status"] == "CALCULATED"
    assert result["observation_count"] == 3
    assert result["mean_observed_time"] == pytest.approx(2.0)
    assert result["sample_standard_deviation"] == pytest.approx(1.0)
    assert result["normal_time"] == pytest.approx(2.2)
    # 10% allowance is defined as a share of standard time, not normal time.
    assert result["standard_time"] == pytest.approx(2.2 / 0.9)
    assert len(result["observations"]) == 3
    assert "percentage of standard time" in result["method"]
    assert "Fewer than 10 observations" in result["warning"]


def test_time_study_rejects_empty_nonpositive_and_invalid_assumptions():
    from shoir_target_engines import calculate_time_study

    with pytest.raises(ValueError, match="at least one"):
        calculate_time_study([])
    with pytest.raises(ValueError, match="greater than zero"):
        calculate_time_study([1, 0, 2])
    with pytest.raises(ValueError, match="greater than zero"):
        calculate_time_study([1, 2], performance_rating_pct=0)
    with pytest.raises(ValueError, match="less than 100"):
        calculate_time_study([1, 2], allowance_pct=100)
    with pytest.raises(ValueError, match="finite number"):
        calculate_time_study([1, float("nan")])


def test_takt_capacity_calculates_capacity_gap_and_exact_boundary():
    from shoir_target_engines import calculate_takt_capacity

    result = calculate_takt_capacity(480, 120, 3, time_unit="minutes")
    assert result["status"] == "CAPACITY_MEETS_DEMAND"
    assert result["takt_time_per_unit"] == pytest.approx(4.0)
    assert result["implied_capacity_units_per_period"] == pytest.approx(160.0)
    assert result["capacity_gap_units_per_period"] == pytest.approx(40.0)
    assert result["demand_load_pct_of_implied_capacity"] == pytest.approx(75.0)

    boundary = calculate_takt_capacity(480, 120, 4, time_unit="minutes")
    assert boundary["implied_capacity_units_per_period"] == pytest.approx(120.0)
    assert boundary["capacity_gap_units_per_period"] == pytest.approx(0.0)
    assert boundary["feasible_at_stated_cycle_time"] is True

    shortfall = calculate_takt_capacity(480, 120, 5, time_unit="minutes")
    assert shortfall["status"] == "CAPACITY_BELOW_DEMAND"
    assert shortfall["capacity_gap_units_per_period"] == pytest.approx(-24.0)


def test_takt_capacity_rejects_zero_mixed_or_noninteger_denominators():
    from shoir_target_engines import calculate_takt_capacity

    with pytest.raises(ValueError, match="[Aa]vailable production time"):
        calculate_takt_capacity(0, 120, 3)
    with pytest.raises(ValueError, match="whole number"):
        calculate_takt_capacity(480, 120.5, 3)
    with pytest.raises(ValueError, match="[Cc]ycle time"):
        calculate_takt_capacity(480, 120, 0)
    with pytest.raises(ValueError, match="[Tt]ime unit"):
        calculate_takt_capacity(480, 120, 3, time_unit="")


def test_time_study_result_and_input_snapshot_roundtrip_per_user(tmp_path):
    from shoir_target_engines import calculate_time_study
    from workspace_persistence import load_user_workspace, save_user_workspace

    db_path = str(tmp_path / "focused-tool-workspace.db")
    inputs = {
        "observation_times_text": "1, 2, 3",
        "performance_rating_pct": 110.0,
        "allowance_pct_of_standard_time": 10.0,
        "time_unit": "minutes",
    }
    result = calculate_time_study([1, 2, 3], 110, 10, time_unit="minutes")
    result["_workspace_persistence"] = "SAVED_LOCAL_FALLBACK"
    workspace = {
        "shoir_tool_result_T021": result,
        "shoir_tool_inputs_T021": inputs,
        "shoir_tool_save_status_T021": "SAVED_LOCAL_FALLBACK",
    }

    assert save_user_workspace("Alice", workspace, db_path)
    alice = {}
    bob = {}
    assert load_user_workspace("Alice", alice, db_path)
    assert not load_user_workspace("Bob", bob, db_path)

    restored = alice["shoir_tool_result_T021"]
    assert restored["standard_time"] == pytest.approx(2.2 / 0.9)
    assert restored["_workspace_persistence"] == "SAVED_LOCAL_FALLBACK"
    assert isinstance(restored["observations"], pd.DataFrame)
    pd.testing.assert_frame_equal(restored["observations"], result["observations"])
    assert alice["shoir_tool_inputs_T021"] == inputs
    assert "shoir_tool_result_T021" not in bob
