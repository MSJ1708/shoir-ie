from shoir_100_tool_registry import (
    IMPLEMENTED_TOOL_IDS, STATUS_VALUES, TOOL_CATALOG, TOOL_BY_ID,
    catalog_integrity_errors, get_tool, tool_access_allowed, tool_is_actionable,
)
from shoir_tier_capabilities import TIER_ORDER


def test_registry_contains_all_stable_ids_once():
    assert not catalog_integrity_errors()
    assert len(TOOL_CATALOG) == 100
    assert set(TOOL_BY_ID) == {f"T{i:03d}" for i in range(1, 101)}
    assert len({row["canonical_name"] for row in TOOL_CATALOG}) == 100
    assert {row["implementation_status"] for row in TOOL_CATALOG} <= set(STATUS_VALUES)


def test_all_100_tools_have_an_exhaustive_six_package_entitlement_matrix():
    for row in TOOL_CATALOG:
        for tier in TIER_ORDER:
            got = tool_access_allowed(row["tool_id"], tier)
            expected = _expected_access(tier, row["target_minimum_tier"])
            assert got is expected, (row["tool_id"], tier, row["target_minimum_tier"], got)


def _expected_access(current, required):
    if current == "Research Pack":
        return required in {"Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Research Pack"}
    if required == "Research Pack":
        return current == "Research Pack"
    levels = ["Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus"]
    if current not in levels or required not in levels:
        return False
    return levels.index(current) >= levels.index(required)


def test_unknown_or_display_alias_only_tool_fails_closed():
    assert not tool_access_allowed("T999", "Enterprise Plus")
    assert not tool_access_allowed("Engineering Tool Library", "Enterprise Plus")
    assert get_tool("t011")["canonical_name"] == "Universal Data Importer"
    # Display labels are not IDs and cannot be used to switch execution gates.
    assert not tool_is_actionable("Universal Data Importer")


def test_registry_does_not_mislabel_catalog_only_items_as_executable():
    for row in TOOL_CATALOG:
        if row["tool_id"] not in IMPLEMENTED_TOOL_IDS:
            assert not tool_is_actionable(row["tool_id"])
    assert all(tool_is_actionable(tool_id) for tool_id in IMPLEMENTED_TOOL_IDS)
    assert all(TOOL_BY_ID[tool_id]["implementation_status"] == "IMPLEMENTED_NEEDS_VALIDATION" for tool_id in IMPLEMENTED_TOOL_IDS)
