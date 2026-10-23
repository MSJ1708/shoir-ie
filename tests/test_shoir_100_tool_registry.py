"""Regression tests for the 100-target library and strict launch-policy decisions."""
from __future__ import annotations

from shoir_100_tool_registry import TOOL_CATALOG, TOOL_STATUS_VALUES, tool_access_decision
from shoir_tier_capabilities import TIER_ORDER, tier_allows


def test_target_catalog_has_all_stable_ids_and_required_metadata():
    assert len(TOOL_CATALOG) == 100
    assert {item["tool_id"] for item in TOOL_CATALOG} == {f"T{i:03d}" for i in range(1, 101)}
    assert len({item["canonical_name"] for item in TOOL_CATALOG}) == 100
    for item in TOOL_CATALOG:
        assert item["canonical_name"].strip()
        assert item["workbench"].strip()
        assert item["target_minimum_tier"] in TIER_ORDER
        assert item["implementation_status"] in TOOL_STATUS_VALUES


def test_target_minimum_tier_is_enforced_before_related_route_navigation():
    item = next(tool for tool in TOOL_CATALOG if tool["tool_id"] == "T074")
    can_open, reason = tool_access_decision(item, "Enterprise", ["Live Industrial Digital Twin"])
    assert not can_open
    assert "requires Enterprise Plus" in reason


def test_related_route_must_be_in_existing_allowed_module_set():
    item = next(tool for tool in TOOL_CATALOG if tool["tool_id"] == "T065")
    can_open, reason = tool_access_decision(item, "Starter", [])
    assert not can_open
    assert "not available" in reason


def test_unknown_route_policy_is_not_authorized(monkeypatch):
    item = next(tool for tool in TOOL_CATALOG if tool["tool_id"] == "T065")
    monkeypatch.setattr("shoir_100_tool_registry.module_required_tier", lambda route: None)
    can_open, reason = tool_access_decision(item, "Starter", ["Facility Layout & Warehousing"])
    assert not can_open
    assert "no verified matching access policy" in reason


def test_research_pack_and_enterprise_plus_are_distinct_for_target_tools():
    research = next(tool for tool in TOOL_CATALOG if tool["tool_id"] == "T085")
    enterprise_plus = next(tool for tool in TOOL_CATALOG if tool["tool_id"] == "T074")
    assert tier_allows("Research Pack ($30 add-on)", research["target_minimum_tier"])
    assert not tier_allows("Enterprise Plus Tier ($399)", research["target_minimum_tier"])
    assert not tier_allows("Research Pack ($30 add-on)", enterprise_plus["target_minimum_tier"])
    assert not tier_allows("Enterprise Plus Tier ($399)", "Research Pack")


def test_no_target_is_declared_verified_without_end_to_end_evidence():
    # This source-audit snapshot has no authenticated acceptance artifacts attached.
    # Update this expectation only together with evidence-bearing status changes.
    assert not [item for item in TOOL_CATALOG if item["implementation_status"] == "VERIFIED_WORKING"]


def test_tool_library_is_connected_to_existing_shell_without_replacing_it():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    shell = (root / "shoir_application_shell.py").read_text(encoding="utf-8")
    assert '"TOOL_LIBRARY": "🧰 Tool Library"' in shell
    assert 'elif surface == "tool_library":' in shell
    assert "render_tool_library(username, tier, allowed_modules)" in shell
