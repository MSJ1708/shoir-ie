"""Golden, boundary, and entitlement tests for T013/T017/T018/T019/T034/T070/T082/T084."""
from __future__ import annotations

import math

import pandas as pd
import pytest
from scipy.stats import binom

from shoir_100_tool_methods import (
    acceptance_sampling_oc, cost_variance, generate_synthetic_industrial_data,
    join_dataframes, mm1_queue, portfolio_score, process_time_series,
    profile_dataframe, require_tool_access,
)


def test_profile_counts_missing_duplicates_and_iqr_outlier_without_mutating_input():
    source = pd.DataFrame({"cycle": [1, 2, 3, 4, 100], "area": ["A", "A", None, "B", "B"]})
    before = source.copy(deep=True)
    result = profile_dataframe(source)
    assert result["row_count"] == 5
    assert result["missing_cell_count"] == 1
    assert result["duplicate_row_count"] == 0
    prof = result["columns"].set_index("column")
    assert prof.loc["cycle", "iqr_outlier_count"] == 1
    pd.testing.assert_frame_equal(source, before)


def test_join_reconciles_rows_and_blocks_unapproved_many_to_many_and_null_keys():
    left = pd.DataFrame({"machine": ["M1", "M2", "M3"], "units": [1, 2, 3]})
    right = pd.DataFrame({"machine": ["M1", "M2"], "line": ["A", "B"]})
    result = join_dataframes(left, right, ["machine"], cardinality="many_to_one")
    assert result["output_rows"] == 3
    assert result["join_status_counts"]["left_only"] == 1
    assert list(result["data"]["line"].fillna("")) == ["A", "B", ""]
    duplicated_right = pd.DataFrame({"machine": ["M1", "M1"], "line": ["A", "B"]})
    with pytest.raises(ValueError, match="violates"):
        join_dataframes(left, duplicated_right, ["machine"], cardinality="many_to_one")
    with pytest.raises(ValueError, match="many-to-many"):
        join_dataframes(left, duplicated_right, ["machine"], cardinality="many_to_many")
    with pytest.raises(ValueError, match="Null join keys"):
        join_dataframes(pd.DataFrame({"k": [None]}), pd.DataFrame({"k": [1]}), ["k"])


def test_time_series_normalizes_timezone_sorts_and_flags_gap():
    source = pd.DataFrame({
        "ts": ["2026-01-01T02:00:00+03:00", "bad", "2026-01-01T00:00:00+03:00",
               "2026-01-01T05:00:00+03:00"],
        "value": [2, 999, 0, 5],
    })
    result = process_time_series(source, "ts", ["value"], target_timezone="UTC")
    assert result["invalid_timestamp_rows"] == 1
    assert result["rows_in"] == 4 and result["rows_out"] == 3
    assert result["data"]["timestamp"].is_monotonic_increasing
    assert result["gap_count_vs_median_interval"] >= 1


def test_synthetic_data_is_reproducible_and_explicitly_synthetic():
    a = generate_synthetic_industrial_data(20, 77, "2026-01-01")
    b = generate_synthetic_industrial_data(20, 77, "2026-01-01")
    pd.testing.assert_frame_equal(a["data"], b["data"])
    assert set(a["data"]["data_status"]) == {"SYNTHETIC"}
    with pytest.raises(ValueError, match="between 1 and 10,000"):
        generate_synthetic_industrial_data(0)


def test_acceptance_sampling_oc_matches_binomial_reference_and_risk_direction():
    result = acceptance_sampling_oc(10, 1, 5, 20)
    assert result["probability_accept_at_aql"] == pytest.approx(binom.cdf(1, 10, 0.05))
    assert result["probability_accept_at_ltpd"] == pytest.approx(binom.cdf(1, 10, 0.20))
    assert result["producer_risk_at_aql"] == pytest.approx(1 - result["probability_accept_at_aql"])
    assert result["consumer_risk_at_ltpd"] == pytest.approx(result["probability_accept_at_ltpd"])
    assert result["probability_accept_at_aql"] > result["probability_accept_at_ltpd"]
    with pytest.raises(ValueError, match="AQL < LTPD"):
        acceptance_sampling_oc(10, 1, 20, 5)


def test_mm1_queue_matches_known_values_and_rejects_unstable_system():
    result = mm1_queue(4, 5, "hour")
    assert result["utilization"] == pytest.approx(0.8)
    assert result["Lq_expected_queue_length"] == pytest.approx(3.2)
    assert result["L_expected_system_length"] == pytest.approx(4.0)
    assert result["Wq_expected_wait"] == pytest.approx(0.8)
    assert result["W_expected_system_time"] == pytest.approx(1.0)
    unstable = mm1_queue(5, 5)
    assert unstable["status"] == "UNSTABLE"
    with pytest.raises(ValueError, match="greater than zero"):
        mm1_queue(0, 5)


def test_cost_variance_reconciles_components_and_marks_cost_direction():
    result = cost_variance([
        {"component": "Material", "actual": 120, "standard": 100, "plan": 110},
        {"component": "Labor", "actual": 80, "standard": 90, "plan": 85},
    ], "SAR")
    assert result["totals"]["actual_cost"] == 200
    assert result["totals"]["actual_minus_standard"] == 10
    assert result["totals"]["actual_minus_plan"] == 5
    assert list(result["components"]["standard_variance"]) == ["UNFAVORABLE", "FAVORABLE"]
    with pytest.raises(ValueError, match="currency code"):
        cost_variance([{"component": "A", "actual": 1, "standard": 1, "plan": 1}], "SAR1")


def test_portfolio_score_normalizes_weights_and_reports_limited_sensitivity():
    result = portfolio_score([
        {"name": "A", "scores": {"value": 5, "risk": 3}},
        {"name": "B", "scores": {"value": 3, "risk": 5}},
    ], {"value": 2, "risk": 1})
    weights = result["weights"]
    assert weights["normalized_weight_pct"].sum() == pytest.approx(100.0)
    assert result["scores"].iloc[0]["project"] == "A"
    assert result["scores"].iloc[0]["weighted_score_pct"] == pytest.approx(86.6666667)
    assert set(result["sensitivity"].columns) >= {"base_rank", "best_rank", "worst_rank"}
    with pytest.raises(ValueError, match="missing criterion"):
        portfolio_score([{"name": "A", "scores": {"value": 4}}], {"value": 1, "risk": 1})


@pytest.mark.parametrize("tool_id,tier,allowed", [
    ("T013", "Starter Tier", True),
    ("T017", "Starter", False),
    ("T017", "Mid-Tier Pro", True),
    ("T034", "Research Pack", True),
    ("T034", "Professional", True),
    ("T098", "Research Pack", False),
    ("T098", "Enterprise Plus Tier", True),
])
def test_tool_access_matches_six_package_contract(tool_id, tier, allowed):
    if allowed:
        assert require_tool_access(tier, tool_id, "disposable-test-user")["tool_id"] == tool_id
    else:
        with pytest.raises(PermissionError):
            require_tool_access(tier, tool_id, "disposable-test-user")


@pytest.mark.parametrize("tier,tool_id,actor", [
    ("Enterprise Plus", "T013", "guest"),
    ("Made Up Tier", "T013", "disposable-test-user"),
    ("Enterprise Plus", "T999", "disposable-test-user"),
])
def test_tool_access_fails_closed_for_guest_unknown_tier_or_id(tier, tool_id, actor):
    with pytest.raises(PermissionError):
        require_tool_access(tier, tool_id, actor)
