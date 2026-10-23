"""Regression tests for the canonical 100-tool library and its executable quick methods."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from industrial_platform import tier_allows as platform_tier_allows
from shoir_100_tool_registry import (
    TOOL_CATALOG,
    TOOL_BY_ID,
    VALID_IMPLEMENTATION_STATUSES,
    tool_access_allowed,
    validate_tool_catalog,
    visible_tools,
)
from shoir_100_tool_workbench import (
    ToolEntitlementError,
    ToolNotImplementedError,
    convert_quantity,
    generate_synthetic_industrial_data,
    profile_dataframe,
    run_tool_calculation,
    takt_time_capacity,
    time_study_standard_time,
    work_sampling_interval,
)
from shoir_tier_capabilities import available_modules, tier_allows


ORDINARY = ("Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus")
ALL_TIERS = (*ORDINARY, "Research Pack")
TIER_INDEX = {tier: index for index, tier in enumerate(ORDINARY)}


def _expected_access(current: str, required: str) -> bool:
    if current == "Research Pack":
        return required in {"Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Research Pack"}
    if required == "Research Pack":
        return False
    return TIER_INDEX[current] >= TIER_INDEX[required]


def test_registry_has_exactly_100_stable_unique_ids_and_valid_metadata():
    assert len(TOOL_CATALOG) == 100
    assert set(TOOL_BY_ID) == {f"T{i:03d}" for i in range(1, 101)}
    assert validate_tool_catalog() == []
    assert all(row["implementation_status"] in VALID_IMPLEMENTATION_STATUSES for row in TOOL_CATALOG)
    assert not any(row["implementation_status"] == "VERIFIED_WORKING" for row in TOOL_CATALOG)
    assert all(row["browser_test"] == "UNVERIFIED" for row in TOOL_CATALOG)


@pytest.mark.parametrize("tier", ALL_TIERS)
def test_all_100_tool_ids_match_independent_six_package_entitlement_truth_table(tier):
    for row in TOOL_CATALOG:
        actual = tool_access_allowed(tier, row["tool_id"])
        assert actual == _expected_access(tier, row["minimum_tier"]), (
            row["tool_id"], row["canonical_name"], tier, row["minimum_tier"], actual
        )


def test_research_pack_and_enterprise_plus_remain_independent_for_tool_catalog():
    research_tools = [row for row in TOOL_CATALOG if row["minimum_tier"] == "Research Pack"]
    enterprise_plus_tools = [row for row in TOOL_CATALOG if row["minimum_tier"] == "Enterprise Plus"]
    assert research_tools and enterprise_plus_tools
    assert all(tool_access_allowed("Research Pack", row["tool_id"]) for row in research_tools)
    assert all(not tool_access_allowed("Enterprise Plus", row["tool_id"]) for row in research_tools)
    assert all(not tool_access_allowed("Research Pack", row["tool_id"]) for row in enterprise_plus_tools)
    assert all(tool_access_allowed("Enterprise Plus", row["tool_id"]) for row in enterprise_plus_tools)


def test_unknown_tier_tool_id_and_display_name_fail_closed():
    assert not tool_access_allowed("Made-up Tier", "T001")
    assert not tool_access_allowed("", "T001")
    assert not tool_access_allowed("Enterprise Plus", "T999")
    assert not tool_access_allowed("Enterprise Plus", "Personalized Engineering Home")
    with pytest.raises(ToolEntitlementError):
        run_tool_calculation("Made-up Tier", "T023", {"available_time": 420, "demand_units": 240, "cycle_time": 1.5})
    with pytest.raises(ToolEntitlementError):
        run_tool_calculation("Starter", "T078", {"activity_quantity": 1, "factor": 1})


def test_both_entitlement_helpers_fail_closed_for_unknown_values():
    assert not tier_allows("unrecognized account label", "Starter")
    assert not tier_allows("Enterprise", "unrecognized requirement")
    assert available_modules("unrecognized account label", ["AI Copilot"]) == []
    assert available_modules("Enterprise Plus", ["Module Missing From Policy"]) == []
    assert not platform_tier_allows("unrecognized account label", "Starter")
    assert not platform_tier_allows("Enterprise", "unrecognized requirement")
    assert tier_allows("Research Pack ($30 add-on)", "Enterprise")
    assert not tier_allows("Enterprise Plus Tier ($399)", "Research Pack")


def test_visible_tools_preserves_locked_entries_and_reports_access_separately():
    visible = visible_tools("Starter", workbench="Enterprise, collaboration, and trust")
    assert visible
    research_or_enterprise = [item for item in visible if item["minimum_tier"] in {"Enterprise", "Enterprise Plus"}]
    assert research_or_enterprise
    assert all(item["accessible"] is False for item in research_or_enterprise)
    allowed = visible_tools("Starter", query="T013", include_locked=False)
    assert [item["tool_id"] for item in allowed] == ["T013"]


def test_profile_dataframe_counts_missing_duplicates_and_outlier_candidates_without_mutation():
    frame = pd.DataFrame({"value": [1.0, 2.0, 3.0, 100.0], "label": ["a", "b", "b", None]})
    before = frame.copy(deep=True)
    result = profile_dataframe(frame)
    assert result["status"] == "PROFILED"
    assert result["rows"] == 4
    assert result["columns"] == 2
    assert result["duplicate_rows"] == 0
    assert result["missing_cells"] == 1
    value_profile = next(row for row in result["column_profile"] if row["column"] == "value")
    assert value_profile["outlier_count_iqr"] == 1
    pd.testing.assert_frame_equal(frame, before)
    with pytest.raises(ValueError):
        profile_dataframe(pd.DataFrame())


def test_physical_unit_conversion_and_dimension_guard():
    result = convert_quantity(2, "km", "m")
    assert result["value"] == pytest.approx(2000.0)
    assert result["unit"] == "m"
    with pytest.raises(ValueError, match="Incompatible dimensions"):
        convert_quantity(1, "km", "kg")


def test_currency_conversion_requires_rate_date_and_provenance():
    with pytest.raises(ValueError, match="date and source"):
        convert_quantity(100, "SAR", "USD", exchange_rate=0.27)
    result = convert_quantity(
        100, "SAR", "USD", exchange_rate=0.27,
        rate_date="2026-10-23", rate_source="Fixture rate for test",
    )
    assert result["value"] == pytest.approx(27.0)
    assert result["rate_date"] == "2026-10-23"
    assert "user-supplied" in result["warnings"][0]


def test_synthetic_generator_is_reproducible_bounded_and_never_claims_live_data():
    first = generate_synthetic_industrial_data(rows=20, seed=123, start="2026-01-01")
    second = generate_synthetic_industrial_data(rows=20, seed=123, start="2026-01-01")
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 20
    assert set(first["data_status"]) == {"SYNTHETIC"}
    assert first["seed"].eq(123).all()
    with pytest.raises(ValueError):
        generate_synthetic_industrial_data(rows=10_001, seed=1)


def test_time_study_golden_fixture_and_invalid_observations():
    result = time_study_standard_time([10, 12, 8], performance_rating_pct=110, allowance_pct=15)
    assert result["metrics"]["mean_observed_time"] == pytest.approx(10)
    assert result["metrics"]["normal_time"] == pytest.approx(11)
    assert result["metrics"]["standard_time"] == pytest.approx(12.65)
    assert "percentage of normal time" in result["assumptions"][1]
    with pytest.raises(ValueError, match="greater than zero"):
        time_study_standard_time([10, 0, 11])
    with pytest.raises(ValueError, match="Performance rating"):
        time_study_standard_time([10], performance_rating_pct=0)


def test_work_sampling_wilson_interval_golden_fixture_and_small_sample_warning():
    result = work_sampling_interval(40, 100, 95)
    metrics = result["metrics"]
    assert metrics["estimated_percent"] == pytest.approx(40)
    assert metrics["lower_bound_percent"] == pytest.approx(30.94, abs=0.03)
    assert metrics["upper_bound_percent"] == pytest.approx(49.80, abs=0.03)
    assert not result["warnings"]
    small = work_sampling_interval(1, 5, 90)
    assert any("below 30" in warning for warning in small["warnings"])
    with pytest.raises(ValueError):
        work_sampling_interval(6, 5, 95)


def test_takt_capacity_golden_fixture_and_capacity_shortfall_warning():
    result = takt_time_capacity(420, 240, 1.5)
    metrics = result["metrics"]
    assert metrics["takt_time_per_unit"] == pytest.approx(1.75)
    assert metrics["theoretical_capacity_units_per_period"] == pytest.approx(280)
    assert metrics["implied_utilization_pct"] == pytest.approx(85.7142857)
    assert metrics["capacity_shortfall_units_per_period"] == 0
    overloaded = takt_time_capacity(60, 120, 1)
    assert overloaded["metrics"]["implied_utilization_pct"] == pytest.approx(200)
    assert overloaded["warnings"]
    with pytest.raises(ValueError):
        takt_time_capacity(0, 2, 1)


def test_only_declared_quick_engines_execute_and_no_catalog_stub_returns_fake_success():
    result = run_tool_calculation("Starter", "T021", {
        "observed_times": "10, 12, 8",
        "performance_rating_pct": 100,
        "allowance_pct": 0,
    })
    assert result["status"] == "CALCULATED"
    assert result["tool_id"] == "T021"
    with pytest.raises(ToolNotImplementedError):
        run_tool_calculation("Enterprise", "T071", {"synthetic_kpi": 1})
