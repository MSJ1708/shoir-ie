"""Structural and package-policy tests for the 100-tool target registry."""

from shoir_100_tool_registry import (
    TOOL_CATALOG, TOOL_BY_ID, VALID_TOOL_TIERS, validate_tool_catalog,
)
from shoir_tier_capabilities import TIER_ORDER, tier_allows
from shoir_ie_basic_calculators import calculate_standard_time, calculate_work_sampling, calculate_takt_capacity


def test_registry_contains_exactly_one_row_for_each_stable_tool_id():
    assert validate_tool_catalog() == []
    assert len(TOOL_CATALOG) == 100
    assert set(TOOL_BY_ID) == {f"T{i:03d}" for i in range(1, 101)}
    assert VALID_TOOL_TIERS == set(TIER_ORDER)


def test_every_target_minimum_tier_obeys_the_six_package_truth_table():
    ordinary = ("Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus")
    all_packages = (*ordinary, "Research Pack")
    research_base = {"Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Research Pack"}
    for tool in TOOL_CATALOG:
        required = tool["target_minimum_tier"]
        for current in all_packages:
            expected = required in research_base if current == "Research Pack" else (
                False if required == "Research Pack" else ordinary.index(current) >= ordinary.index(required)
            )
            assert tier_allows(current, required) is expected, (
                tool["tool_id"], tool["canonical_name"], current, required
            )


def test_registry_does_not_claim_authenticated_modules_are_verified():
    assert all(tool["implementation_status"] != "VERIFIED_WORKING" for tool in TOOL_CATALOG)
    assert all(tool["browser_test"].startswith("UNVERIFIED") for tool in TOOL_CATALOG)


def test_t021_t023_are_wired_to_calculator_engines_and_workbench():
    expected = {
        "T021": ("Time Study and Standard Time", "calculate_standard_time"),
        "T022": ("Work Sampling Analyzer", "calculate_work_sampling"),
        "T023": ("Takt Time and Capacity Calculator", "calculate_takt_capacity"),
    }
    for tool_id, (name, function_name) in expected.items():
        tool = TOOL_BY_ID[tool_id]
        assert tool["canonical_name"] == name
        assert tool["implementation_status"] == "IMPLEMENTED_NEEDS_VALIDATION"
        assert "shoir_ie_basic_calculators.py" in tool["source_files"]
        assert "pages/Industrial_Engineering_Workbench.py" in tool["source_files"]
        engines = {
            "calculate_standard_time": calculate_standard_time,
            "calculate_work_sampling": calculate_work_sampling,
            "calculate_takt_capacity": calculate_takt_capacity,
        }
        assert callable(engines[function_name])


def test_t016_points_to_implemented_converter_and_explicit_fx_provenance():
    tool = TOOL_BY_ID["T016"]
    assert tool["implementation_status"] == "IMPLEMENTED_NEEDS_VALIDATION"
    assert "shoir_unit_converter.py" in tool["source_files"]
    assert "date" in tool["input_contract"].lower()
    assert "source" in tool["input_contract"].lower()
