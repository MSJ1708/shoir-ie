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
