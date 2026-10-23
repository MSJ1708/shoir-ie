"""Regression tests for the canonical 100-tool library and its executable quick methods."""
from __future__ import annotations

import ast
import csv
import math
from pathlib import Path

import pandas as pd
import pytest

from industrial_platform import PLATFORM_CATALOG, tier_allows as platform_tier_allows
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
    oee_analysis,
    process_capability,
    mtbf_mttr_analysis,
    inventory_policy,
    carbon_emissions,
    engineering_economics,
)
from shoir_tier_capabilities import available_modules, copilot_capabilities, copilot_gate, tier_allows


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
    assert not tier_allows("Researcher", "Starter")
    assert not tier_allows("Researcher", "Research Pack")
    assert not tier_allows("Enterprise demo environment", "Starter")
    assert not platform_tier_allows("Researcher", "Research Pack")
    assert not tool_access_allowed("Researcher", "T085")
    assert copilot_gate("run OEE", "Starter") is not None
    assert copilot_gate("run MTBF analysis", "Mid-Tier Pro") is not None
    assert copilot_gate("calculate NPV", "Starter") is not None
    assert copilot_gate("calculate NPV", "Mid-Tier Pro") is None
    unknown_copilot = copilot_capabilities("Researcher", ["Core IE Tools", "Research AI"])
    assert unknown_copilot["tier"] == "Unrecognized package"
    assert unknown_copilot["modules"] == []
    assert not unknown_copilot["can_research"]
    assert not unknown_copilot["can_enterprise"]
    assert not unknown_copilot["can_professional"]


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
    duplicate_columns = pd.DataFrame([[1, 2], [3, 4]], columns=["same", "same"])
    with pytest.raises(ValueError, match="Column names must be unique"):
        profile_dataframe(duplicate_columns)


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



def test_every_declared_related_route_exists_in_the_actual_app_or_platform_catalog():
    root = Path(__file__).resolve().parents[1]
    app_tree = ast.parse((root / "app.py").read_text(encoding="utf-8"), filename="app.py")
    app_catalog = None
    for node in app_tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "MODULE_CATALOG" for target in node.targets):
            app_catalog = ast.literal_eval(node.value)
            break
    assert isinstance(app_catalog, list), "Could not parse app.py MODULE_CATALOG."
    route_names = {str(item.get("name", "")).strip() for item in app_catalog}
    route_names.update(str(item.get("name", "")).strip() for item in PLATFORM_CATALOG)
    declared = {
        row["existing_route"] for row in TOOL_CATALOG if row["existing_route"]
    }
    missing = sorted(declared - route_names)
    assert not missing, f"Tool crosswalk contains routes absent from current source catalogs: {missing}"


def test_machine_readable_matrix_has_all_ids_and_does_not_overstate_browser_evidence():
    path = Path(__file__).resolve().parents[1] / "docs" / "SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 100
    assert {row["tool_id"] for row in rows} == {f"T{i:03d}" for i in range(1, 101)}
    assert all(row["browser_test"] == "UNVERIFIED" for row in rows)
    assert not any(row["implementation_status"] == "VERIFIED_WORKING" for row in rows)
    assert all(row["remaining_gap"].strip() for row in rows)
    registry_by_id = {row["tool_id"]: row for row in TOOL_CATALOG}
    matrix_by_id = {row["tool_id"]: row for row in rows}
    for tool_id, spec in registry_by_id.items():
        matrix_row = matrix_by_id[tool_id]
        assert matrix_row["canonical_name"] == spec["canonical_name"]
        assert matrix_row["target_minimum_tier"] == spec["minimum_tier"]
        assert matrix_row["implementation_status"] == spec["implementation_status"]
        assert matrix_row["browser_test"] == "UNVERIFIED"



def test_oee_golden_fixture_and_invalid_time_boundaries():
    result = oee_analysis(
        planned_production_time=480,
        downtime=45,
        ideal_cycle_time=0.5,
        total_count=800,
        good_count=784,
    )
    metrics = result["metrics"]
    assert metrics["operating_time"] == pytest.approx(435)
    assert metrics["availability_pct"] == pytest.approx(90.625)
    assert metrics["performance_pct"] == pytest.approx((0.5 * 800 / 435) * 100)
    assert metrics["quality_pct"] == pytest.approx(98.0)
    assert metrics["oee_pct"] == pytest.approx(81.6666667, abs=0.001)
    with pytest.raises(ValueError, match="Downtime"):
        oee_analysis(100, 101, 1, 50, 49)
    with pytest.raises(ValueError, match="good output"):
        oee_analysis(100, 10, 1, 50, 51)
    with pytest.raises(ValueError, match="whole numbers"):
        oee_analysis(100, 10, 1, 50.5, 50)


def test_process_capability_hand_fixture_and_signed_measurements():
    values = [-1.0, 0.0, 1.0, 0.0, 0.0]
    result = process_capability(values, -3.0, 3.0, within_subgroup_sigma=1.0)
    metrics = result["metrics"]
    assert metrics["mean"] == pytest.approx(0.0)
    assert metrics["Cp"] == pytest.approx(1.0)
    assert metrics["Cpk"] == pytest.approx(1.0)
    assert metrics["Pp"] == pytest.approx(6 / (6 * math.sqrt(0.5)))
    assert metrics["Ppk"] == pytest.approx(metrics["Pp"])
    with pytest.raises(ValueError, match="below upper"):
        process_capability([1, 2, 3], 5, 4)
    with pytest.raises(ValueError, match="non-zero variation"):
        process_capability([5, 5, 5], 0, 10)


def test_mtbf_mttr_golden_fixture_and_failure_count_reconciliation():
    result = mtbf_mttr_analysis(1000, 5, "2, 1.5, 3, 2.5, 1")
    metrics = result["metrics"]
    assert metrics["MTBF_hours"] == pytest.approx(200)
    assert metrics["MTTR_hours"] == pytest.approx(2)
    assert metrics["inherent_availability_pct"] == pytest.approx(200 / 202 * 100)
    with pytest.raises(ValueError, match="one positive repair-duration"):
        mtbf_mttr_analysis(1000, 2, "1, 2, 3")


def test_inventory_policy_golden_fixture_and_parameter_validation():
    result = inventory_policy(12000, 50, 2, 40, 5, 5, 1.96)
    metrics = result["metrics"]
    assert metrics["EOQ_units"] == pytest.approx(math.sqrt(600000))
    assert metrics["mean_lead_time_demand_units"] == pytest.approx(200)
    assert metrics["safety_stock_units"] == pytest.approx(1.96 * 5 * math.sqrt(5))
    assert metrics["reorder_point_units"] == pytest.approx(200 + 1.96 * 5 * math.sqrt(5))
    with pytest.raises(ValueError, match="must all be positive"):
        inventory_policy(0, 50, 2, 40, 5, 5, 1.96)


def test_carbon_emissions_golden_fixture_requires_factor_provenance():
    result = carbon_emissions(1000, 0.42, "kWh", "kg CO2e", "Test factor set", "2026-10-23")
    assert result["metrics"]["total_emissions"] == pytest.approx(420)
    assert result["factor_source"] == "Test factor set"
    with pytest.raises(ValueError, match="source and date"):
        carbon_emissions(1000, 0.42, "kWh", "kg CO2e", "", "")


def test_engineering_economics_npv_and_payback_golden_fixture():
    result = engineering_economics([-1000, 300, 350, 400, 450], 8)
    metrics = result["metrics"]
    expected_npv = -1000 + 300 / 1.08 + 350 / (1.08 ** 2) + 400 / (1.08 ** 3) + 450 / (1.08 ** 4)
    assert metrics["NPV"] == pytest.approx(expected_npv)
    assert metrics["simple_payback_periods"] == pytest.approx(3 - 50 / 400)
    assert metrics["discounted_payback_periods"] is not None
    assert metrics["IRR_pct"] is not None
    irr = metrics["IRR_pct"] / 100.0
    assert sum(flow / ((1 + irr) ** period) for period, flow in enumerate(result["cash_flows"])) == pytest.approx(0.0, abs=1e-6)
    ambiguous = engineering_economics([-100, 230, -132], 8)
    assert ambiguous["metrics"]["IRR_pct"] is None
    assert any("multiple IRRs" in warning for warning in ambiguous["warnings"])
    with pytest.raises(ValueError, match="at least a period-0"):
        engineering_economics([-1000], 8)


@pytest.mark.parametrize(
    ("tier", "tool_id", "inputs"),
    [
        ("Mid-Tier Pro", "T026", {"planned_production_time": 480, "downtime": 45, "ideal_cycle_time": 0.5, "total_count": 800, "good_count": 784}),
        ("Mid-Tier Pro", "T032", {"measurements": "-1,0,1,0,0", "lower_spec_limit": -3, "upper_spec_limit": 3, "within_subgroup_sigma": 1}),
        ("Professional", "T042", {"operating_hours": 1000, "failure_count": 5, "repair_hours": "2,1,3,2,1"}),
        ("Mid-Tier Pro", "T055", {"annual_demand": 12000, "order_cost": 50, "annual_holding_cost_per_unit": 2, "daily_demand_mean": 40, "daily_demand_sigma": 5, "lead_time_days": 5, "service_factor_z": 1.96}),
        ("Mid-Tier Pro", "T078", {"activity_quantity": 100, "emission_factor": 0.4, "quantity_unit": "kWh", "emission_unit": "kg CO2e", "factor_source": "fixture", "factor_date": "2026-10-23"}),
        ("Mid-Tier Pro", "T081", {"cash_flows": "-100,50,60", "discount_rate_pct": 8}),
    ],
)
def test_added_quick_engines_dispatch_through_stable_tool_ids_and_tier_gates(tier, tool_id, inputs):
    result = run_tool_calculation(tier, tool_id, inputs)
    assert result["tool_id"] == tool_id
    assert result["status"] == "CALCULATED"
    assert result["required_tier"] == TOOL_BY_ID[tool_id]["minimum_tier"]


def test_oee_and_capability_cannot_be_run_below_declared_minimum_tier():
    with pytest.raises(ToolEntitlementError):
        run_tool_calculation("Starter", "T026", {"planned_production_time": 480, "downtime": 45, "ideal_cycle_time": 0.5, "total_count": 800, "good_count": 784})
    with pytest.raises(ToolEntitlementError):
        run_tool_calculation("Starter", "T032", {"measurements": "1,2,3", "lower_spec_limit": 0, "upper_spec_limit": 4})
