"""Golden, boundary, preservation and reproducibility tests for additional focused tools."""
from __future__ import annotations

import pandas as pd
import pytest

from shoir_target_engines import (
    analyze_mm1_queue,
    generate_synthetic_industrial_data,
    join_dataframes,
    plan_acceptance_sampling,
    process_time_series,
    profile_dataframe,
)


def test_data_profiler_reports_missing_duplicates_and_outliers_without_mutation():
    source = pd.DataFrame({
        "measurement": [1.0, 2.0, 3.0, 4.0, 100.0],
        "station": ["A", "A", "B", "B", "B"],
    })
    original = source.copy(deep=True)
    result = profile_dataframe(source)
    assert result["status"] == "PROFILED"
    assert result["row_count"] == 5
    assert result["column_count"] == 2
    profile = result["column_profile"].set_index("column")
    assert profile.loc["measurement", "numeric_mean"] == pytest.approx(22.0)
    assert profile.loc["measurement", "iqr_outlier_count"] == 1
    assert profile.loc["measurement", "missing_count"] == 0
    pd.testing.assert_frame_equal(source, original)
    assert result["source_unchanged"] is True


def test_data_profiler_validates_empty_and_oversized_inputs():
    with pytest.raises(ValueError, match="non-empty"):
        profile_dataframe(pd.DataFrame())
    with pytest.raises(ValueError, match="limit"):
        profile_dataframe(pd.DataFrame({"x": [1, 2]}), max_rows=1)


def test_data_join_reconciles_rows_and_unmatched_keys():
    left = pd.DataFrame({"part": ["A", "B", "C"], "quantity": [10, 20, 30]})
    right = pd.DataFrame({"sku": ["A", "A", "D"], "cost": [2.0, 2.5, 9.0]})
    result = join_dataframes(left, right, left_key="part", right_key="sku", how="left")
    assert result["status"] == "JOINED"
    assert result["result_rows"] == 4
    assert result["left_duplicate_key_rows"] == 0
    assert result["right_duplicate_key_rows"] == 2
    assert result["left_unmatched_rows"] == 2
    assert result["right_unmatched_rows"] == 1
    assert len(result["joined_data"]) == result["result_rows"]
    assert result["source_rows_preserved"] is True


def test_data_join_rejects_many_to_many_keys_and_bad_inputs():
    left = pd.DataFrame({"key": ["A", "A"], "left": [1, 2]})
    right = pd.DataFrame({"key": ["A", "A"], "right": [3, 4]})
    with pytest.raises(ValueError, match="many-to-many"):
        join_dataframes(left, right, left_key="key", right_key="key")
    with pytest.raises(ValueError, match="does not exist"):
        join_dataframes(left, right, left_key="absent", right_key="key")
    with pytest.raises(ValueError, match="Join type"):
        join_dataframes(left.drop_duplicates("key"), right, left_key="key", right_key="key", how="cross")


def test_time_series_sorts_timezone_aware_rows_and_averages_duplicates():
    frame = pd.DataFrame({
        "time": ["2026-01-01 00:02:00", "2026-01-01 00:01:00", "2026-01-01 00:01:00"],
        "output": [30, 10, 20],
    })
    result = process_time_series(
        frame, timestamp_column="time", value_columns=["output"],
        local_timezone="Asia/Riyadh", duplicate_policy="mean",
    )
    assert result["status"] == "PROCESSED"
    assert result["source_rows"] == 3
    assert result["processed_rows"] == 2
    assert result["duplicate_timestamp_rows"] == 1
    assert result["series"]["output"].tolist() == [15.0, 30.0]
    assert str(result["series"]["timestamp"].dt.tz) == "Asia/Riyadh"


def test_time_series_rejects_bad_columns_duplicate_policy_and_empty_valid_series():
    frame = pd.DataFrame({"time": ["not-a-date"], "output": [1]})
    with pytest.raises(ValueError, match="not found"):
        process_time_series(frame, timestamp_column="missing", value_columns=["output"])
    with pytest.raises(ValueError, match="Duplicate policy"):
        process_time_series(frame, timestamp_column="time", value_columns=["output"], duplicate_policy="drop")
    with pytest.raises(ValueError, match="No valid timestamped"):
        process_time_series(frame, timestamp_column="time", value_columns=["output"])


def test_time_series_resample_discloses_empty_periods():
    frame = pd.DataFrame({
        "time": ["2026-01-01 00:00:00", "2026-01-01 02:00:00"],
        "output": [5, 9],
    })
    result = process_time_series(
        frame, timestamp_column="time", value_columns=["output"],
        frequency="1h", aggregation="mean",
    )
    assert result["processed_rows"] == 3
    assert result["empty_resampled_periods"] == 1
    assert pd.isna(result["series"]["output"].iloc[1])


def test_synthetic_generator_is_reproducible_and_explicitly_labelled():
    first = generate_synthetic_industrial_data(row_count=25, seed=7)
    second = generate_synthetic_industrial_data(row_count=25, seed=7)
    pd.testing.assert_frame_equal(first["data"], second["data"])
    assert first["status"] == "SYNTHETIC"
    assert first["provenance"] == "SYNTHETIC"
    assert len(first["data"]) == 25
    assert (first["data"]["good_units"] + first["data"]["defect_units"]).equals(first["data"]["output_units"])
    assert "not sampled from a real plant" in first["method"]


def test_synthetic_generator_rejects_invalid_size_and_seed():
    with pytest.raises(ValueError, match="row count"):
        generate_synthetic_industrial_data(row_count=0)
    with pytest.raises(ValueError, match="Random seed"):
        generate_synthetic_industrial_data(row_count=3, seed=-1)


def test_acceptance_sampling_plan_meets_both_operating_characteristic_constraints():
    result = plan_acceptance_sampling(
        aql_fraction=0.01, ltpd_fraction=0.05,
        producer_risk=0.05, consumer_risk=0.10,
        max_sample_size=1500, max_acceptance_number=50,
    )
    assert result["status"] == "CALCULATED"
    assert result["probability_accept_at_aql"] >= 0.95
    assert result["probability_accept_at_ltpd"] <= 0.10
    assert result["rejection_number"] == result["acceptance_number_c"] + 1
    assert "large-lot binomial approximation" in result["warning"]


def test_acceptance_sampling_reports_limit_and_rejects_invalid_assumptions():
    limited = plan_acceptance_sampling(max_sample_size=1, max_acceptance_number=0)
    assert limited["status"] == "LIMIT_REACHED"
    assert limited["sample_size_n"] is None
    with pytest.raises(ValueError, match="AQL and LTPD"):
        plan_acceptance_sampling(aql_fraction=0.05, ltpd_fraction=0.01)
    with pytest.raises(ValueError, match="risk"):
        plan_acceptance_sampling(producer_risk=1.0)


def test_mm1_queue_matches_hand_calculated_stable_case():
    result = analyze_mm1_queue(2.0, 3.0, rate_unit="per hour")
    assert result["status"] == "STABLE"
    assert result["utilization_fraction"] == pytest.approx(2 / 3)
    assert result["mean_customers_in_system"] == pytest.approx(2.0)
    assert result["mean_customers_in_queue"] == pytest.approx(4 / 3)
    assert result["mean_time_in_system"] == pytest.approx(1.0)
    assert result["mean_waiting_time_in_queue"] == pytest.approx(2 / 3)


def test_mm1_queue_marks_unstable_without_finite_steady_state_estimates():
    result = analyze_mm1_queue(4.0, 3.0)
    assert result["status"] == "UNSTABLE"
    assert result["utilization_pct"] == pytest.approx(400 / 3)
    assert result["mean_time_in_system"] is None
    assert result["mean_customers_in_queue"] is None


@pytest.mark.parametrize("arrival,service", [(0, 2), (-1, 2), (1, 0), (1, -2)])
def test_mm1_queue_rejects_nonpositive_rates(arrival, service):
    with pytest.raises(ValueError):
        analyze_mm1_queue(arrival, service)


def test_data_profiler_reports_missing_and_duplicate_rows_without_cleaning():
    source = pd.DataFrame({"batch": ["A", "A", None, None], "count": [1.0, 1.0, 2.0, None]})
    original = source.copy(deep=True)
    result = profile_dataframe(source)
    assert result["duplicate_row_count"] == 1
    assert result["column_profile"].set_index("column").loc["count", "missing_count"] == 1
    pd.testing.assert_frame_equal(source, original)


def test_data_join_rejects_null_key_many_to_many_expansion():
    left = pd.DataFrame({"key": [None, None], "left": [1, 2]})
    right = pd.DataFrame({"key": [None, None], "right": [3, 4]})
    with pytest.raises(ValueError, match="many-to-many"):
        join_dataframes(left, right, left_key="key", right_key="key")


def test_cost_variance_reconciles_totals_and_marks_positive_variance_unfavorable():
    from shoir_target_engines import analyze_cost_variance

    frame = pd.DataFrame({
        "category": ["Labor", "Material"],
        "plan": [100.0, 200.0],
        "standard": [90.0, 220.0],
        "actual": [110.0, 190.0],
    })
    result = analyze_cost_variance(
        frame, category_column="category", plan_column="plan",
        standard_column="standard", actual_column="actual",
        currency="SAR", period="2026-Q1",
    )
    assert result["actual_cost_total"] == pytest.approx(300.0)
    assert result["actual_minus_plan"] == pytest.approx(0.0)
    assert result["actual_minus_standard"] == pytest.approx(-10.0)
    assert result["plan_variance_pct"] == pytest.approx(0.0)
    assert result["currency"] == "SAR"
    assert result["variance_table"]["Actual − Plan"].tolist() == [10.0, -10.0]


def test_cost_variance_rejects_missing_categories_negative_and_invalid_costs():
    from shoir_target_engines import analyze_cost_variance

    frame = pd.DataFrame({"category": ["Labor", "Labor"], "plan": [1, 2], "standard": [1, 2], "actual": [1, 2]})
    with pytest.raises(ValueError, match="unique"):
        analyze_cost_variance(frame, category_column="category", plan_column="plan", standard_column="standard", actual_column="actual")
    frame = pd.DataFrame({"category": ["Labor"], "plan": [1], "standard": [1], "actual": [-2]})
    with pytest.raises(ValueError, match="negative"):
        analyze_cost_variance(frame, category_column="category", plan_column="plan", standard_column="standard", actual_column="actual")
    frame = pd.DataFrame({"category": ["Labor"], "plan": [0], "standard": [0], "actual": [2]})
    result = analyze_cost_variance(frame, category_column="category", plan_column="plan", standard_column="standard", actual_column="actual")
    assert result["plan_variance_pct"] is None
    assert result["standard_variance_pct"] is None


def test_portfolio_score_respects_benefit_cost_directions_and_exposes_weights():
    from shoir_target_engines import score_engineering_portfolio

    result = score_engineering_portfolio(
        projects=[
            {"name": "A", "cost": 100, "service": 90},
            {"name": "B", "cost": 80, "service": 70},
            {"name": "C", "cost": 120, "service": 95},
        ],
        criteria=[
            {"criterion": "cost", "weight": 0.6, "direction": "cost"},
            {"criterion": "service", "weight": 0.4, "direction": "benefit"},
        ],
    )
    ranking = result["ranking"].set_index("Project")
    assert ranking.loc["B", "cost weighted contribution"] == pytest.approx(60.0)
    assert ranking.loc["C", "service weighted contribution"] == pytest.approx(40.0)
    assert ranking.iloc[0]["Weighted score (0–100)"] >= ranking.iloc[-1]["Weighted score (0–100)"]
    assert result["weight_sum"] == pytest.approx(1.0)
    assert len(result["criteria"]) == 2


def test_portfolio_score_rejects_duplicate_projects_bad_weights_and_missing_values():
    from shoir_target_engines import score_engineering_portfolio

    with pytest.raises(ValueError, match="at least two"):
        score_engineering_portfolio([{"name": "A", "cost": 1}], [{"criterion": "cost", "weight": 1, "direction": "cost"}])
    with pytest.raises(ValueError, match="unique"):
        score_engineering_portfolio([{"name": "A", "x": 1}, {"name": "A", "x": 2}], [{"criterion": "x", "weight": 1, "direction": "benefit"}])
    with pytest.raises(ValueError, match="greater than zero"):
        score_engineering_portfolio([{"name": "A", "x": 1}, {"name": "B", "x": 2}], [{"criterion": "x", "weight": 0, "direction": "benefit"}])
    with pytest.raises(ValueError, match="must supply"):
        score_engineering_portfolio([{"name": "A", "x": 1}, {"name": "B"}], [{"criterion": "x", "weight": 1, "direction": "benefit"}])


def test_safety_incident_rates_use_period_exposure_once_and_include_categories():
    from shoir_target_engines import analyze_safety_incident_trends

    incidents = [
        {"date": "2026-01-02", "category": "Near miss", "severity": "Low"},
        {"date": "2026-01-11", "category": "Injury", "severity": "Moderate"},
        {"date": "2026-02-03", "category": "Near miss", "severity": "Low"},
    ]
    result = analyze_safety_incident_trends(
        incidents,
        exposure_hours_by_period={"2026-01": 10_000, "2026-02": 20_000},
    )
    summary = result["period_summary"].set_index("Period")
    assert summary.loc["2026-01", "Incident count"] == 2
    assert summary.loc["2026-01", "Rate per 200000 exposure hours"] == pytest.approx(40.0)
    assert summary.loc["2026-02", "Rate per 200000 exposure hours"] == pytest.approx(10.0)
    assert result["incident_count_total"] == 3
    assert set(result["category_summary"]["category"]) == {"Near miss", "Injury"}


def test_safety_incident_trends_reject_bad_records_and_report_missing_denominators():
    from shoir_target_engines import analyze_safety_incident_trends

    with pytest.raises(ValueError, match="valid date"):
        analyze_safety_incident_trends([{"date": "not-date", "category": "Injury"}], exposure_hours_by_period={"2026-01": 100})
    with pytest.raises(ValueError, match="greater than zero"):
        analyze_safety_incident_trends([{"date": "2026-01-01", "category": "Injury"}], exposure_hours_by_period={"2026-01": 0})
    result = analyze_safety_incident_trends(
        [{"date": "2026-01-01", "category": "Injury"}], exposure_hours_by_period={"2026-02": 100}
    )
    january = result["period_summary"].set_index("Period").loc["2026-01"]
    assert pd.isna(january["Rate per 200000 exposure hours"])
    assert any("No exposure-hour denominator" in message for message in result["warnings"])


def test_energy_efficiency_aggregates_periods_and_compares_to_explicit_baseline():
    from shoir_target_engines import analyze_energy_efficiency

    frame = pd.DataFrame({
        "period": ["2026-01", "2026-01", "2026-02"],
        "energy": [100.0, 50.0, 120.0],
        "output": [50.0, 25.0, 100.0],
    })
    result = analyze_energy_efficiency(
        frame, period_column="period", energy_column="energy", output_column="output",
        energy_unit="kWh", output_unit="units", baseline_period="2026-01",
    )
    table = result["energy_intensity_table"].set_index("Period")
    assert result["total_energy"] == pytest.approx(270.0)
    assert table.loc["2026-01", "Energy intensity (kWh/units)"] == pytest.approx(2.0)
    assert table.loc["2026-02", "Energy intensity (kWh/units)"] == pytest.approx(1.2)
    assert table.loc["2026-02", "Change from baseline (%)"] == pytest.approx(-40.0)


def test_energy_efficiency_requires_valid_columns_values_and_baseline():
    from shoir_target_engines import analyze_energy_efficiency

    frame = pd.DataFrame({"period": ["A"], "energy": [1], "output": [0]})
    with pytest.raises(ValueError, match="greater than zero"):
        analyze_energy_efficiency(frame, period_column="period", energy_column="energy", output_column="output")
    frame["output"] = [1]
    with pytest.raises(ValueError, match="does not exist"):
        analyze_energy_efficiency(frame, period_column="period", energy_column="energy", output_column="output", baseline_period="Z")
    frame["energy"] = [-1]
    with pytest.raises(ValueError, match="negative"):
        analyze_energy_efficiency(frame, period_column="period", energy_column="energy", output_column="output")


def test_water_waste_efficiency_reports_intensities_and_balance_warning():
    from shoir_target_engines import analyze_water_waste_efficiency

    frame = pd.DataFrame({
        "period": ["2026-01", "2026-02"],
        "water_in": [100.0, 100.0],
        "discharge": [30.0, 70.0],
        "reuse": [20.0, 40.0],
        "waste": [10.0, 5.0],
        "output": [50.0, 100.0],
    })
    result = analyze_water_waste_efficiency(
        frame, period_column="period", water_input_column="water_in",
        discharge_column="discharge", reuse_column="reuse", waste_column="waste",
        output_column="output", water_unit="m3", waste_unit="kg", output_unit="units",
    )
    table = result["efficiency_table"].set_index("Period")
    assert result["water_input_total"] == pytest.approx(200.0)
    assert table.loc["2026-01", "Water balance residual"] == pytest.approx(50.0)
    assert table.loc["2026-01", "Water input intensity (m3/units)"] == pytest.approx(2.0)
    assert table.loc["2026-02", "Waste intensity (kg/units)"] == pytest.approx(0.05)
    assert any("Positive water balance residual" in warning for warning in result["warnings"])


def test_water_waste_efficiency_rejects_bad_units_columns_and_negative_flows():
    from shoir_target_engines import analyze_water_waste_efficiency

    frame = pd.DataFrame({
        "period": ["A"], "water_in": [1], "discharge": [0], "reuse": [0], "waste": [-1], "output": [1],
    })
    with pytest.raises(ValueError, match="cannot be negative"):
        analyze_water_waste_efficiency(
            frame, period_column="period", water_input_column="water_in",
            discharge_column="discharge", reuse_column="reuse", waste_column="waste",
            output_column="output",
        )

