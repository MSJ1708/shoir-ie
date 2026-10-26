"""Contract and entitlement tests for the 100-tool target registry.

These tests verify registry completeness and tier policy. They do NOT claim the
specialist numerical engines or authenticated module routes are fully tested.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from shoir_tier_capabilities import TIER_ORDER, tier_allows
from shoir_tool_registry import (
    BASE_TIERS,
    TOOL_STATUS_VALUES,
    TOOL_TARGETS,
    get_tool,
    require_tool_access,
    tier_allows_tool,
    tool_status_counts,
    validate_tool_registry,
)

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv"
ALL_STATES = (*BASE_TIERS, "Research Pack")


def _expected(current: str, required: str) -> bool:
    # Independent truth table: Research Pack is Enterprise inheritance plus
    # its add-on features, and is intentionally not Enterprise Plus.
    if current == "Research Pack":
        return required in {"Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Research Pack"}
    if required == "Research Pack":
        return False
    return BASE_TIERS.index(current) >= BASE_TIERS.index(required)


def test_registry_has_exactly_one_record_for_each_stable_id():
    assert not validate_tool_registry()
    assert len(TOOL_TARGETS) == 100
    assert [row["tool_id"] for row in TOOL_TARGETS] == [f"T{i:03d}" for i in range(1, 101)]
    assert len({row["canonical_name"] for row in TOOL_TARGETS}) == 100


def test_all_100_tool_metadata_contracts():
    required = {
        "tool_id", "canonical_name", "aliases", "workbench", "target_minimum_tier",
        "existing_module_or_route", "source_files", "implementation_status",
        "calculation_or_action", "input_contract", "output_contract", "persistence_scope",
        "external_dependency", "entitlement_enforcement_points", "unit_test",
        "integration_test", "browser_test", "evidence_link_or_artifact",
        "remaining_gap", "owner_or_next_action",
    }
    for tool in TOOL_TARGETS:
        assert required <= set(tool), f"{tool.get('tool_id')} metadata is incomplete"
        assert tool["implementation_status"] in TOOL_STATUS_VALUES
        assert tool["target_minimum_tier"] in TIER_ORDER
        assert tool["canonical_name"].strip()
        assert tool["workbench"].strip()
        assert tool["calculation_or_action"].strip()
        assert tool["input_contract"].strip()
        assert tool["output_contract"].strip()
        assert tool["remaining_gap"].strip()


def test_matrix_covers_registry_without_duplicate_or_missing_ids():
    with MATRIX.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 100
    assert [row["tool_id"] for row in rows] == [tool["tool_id"] for tool in TOOL_TARGETS]
    assert len({row["tool_id"] for row in rows}) == 100
    assert set(rows[0]) >= {
        "tool_id", "canonical_name", "workbench", "target_minimum_tier",
        "existing_module_or_route", "source_files", "implementation_status",
        "calculation_or_action", "input_contract", "output_contract",
        "persistence_scope", "external_dependency", "entitlement_enforcement_points",
        "unit_test", "integration_test", "browser_test", "evidence_link_or_artifact",
        "remaining_gap", "owner_or_next_action",
    }
    for row, tool in zip(rows, TOOL_TARGETS):
        assert row["canonical_name"] == tool["canonical_name"]
        assert row["target_minimum_tier"] == tool["target_minimum_tier"]
        assert row["implementation_status"] == tool["implementation_status"]


@pytest.mark.parametrize("tool", TOOL_TARGETS, ids=lambda tool: tool["tool_id"])
def test_every_target_entitlement_matches_independent_six_state_truth_table(tool):
    for current in ALL_STATES:
        expected = _expected(current, tool["target_minimum_tier"])
        assert tier_allows_tool(current, tool["tool_id"]) is expected
        assert tier_allows(current, tool["target_minimum_tier"]) is expected


def test_research_pack_and_enterprise_plus_are_not_interchangeable():
    research_ids = [tool["tool_id"] for tool in TOOL_TARGETS if tool["target_minimum_tier"] == "Research Pack"]
    plus_ids = [tool["tool_id"] for tool in TOOL_TARGETS if tool["target_minimum_tier"] == "Enterprise Plus"]
    assert research_ids and plus_ids
    assert all(tier_allows_tool("Research Pack", tool_id) for tool_id in research_ids)
    assert all(not tier_allows_tool("Enterprise Plus", tool_id) for tool_id in research_ids)
    assert all(tier_allows_tool("Enterprise Plus", tool_id) for tool_id in plus_ids)
    assert all(not tier_allows_tool("Research Pack", tool_id) for tool_id in plus_ids)


def test_unknown_or_display_name_ids_fail_closed_and_cannot_authorize_by_alias():
    assert not tier_allows_tool("Enterprise Plus", "T999")
    assert not tier_allows_tool("Enterprise Plus", "Facility Layout and SLP Studio")
    with pytest.raises(PermissionError, match="Unknown Shoir-IE tool ID"):
        require_tool_access("Enterprise Plus", "Facility Layout and SLP Studio")
    with pytest.raises(PermissionError, match="requires the Research Pack"):
        require_tool_access("Enterprise Plus", "T037")
    allowed = require_tool_access("Research Pack", "T037")
    assert allowed["canonical_name"] == "Hypothesis Testing Assistant"


def test_status_summary_counts_all_targets_and_never_infers_verified_from_presence():
    counts = tool_status_counts()
    assert sum(counts.values()) == 100
    # No authenticated browser matrix or engine fixture suite has yet run for all
    # targets on this branch, so source mapping alone must not create "verified".
    assert counts["VERIFIED_WORKING"] == 0


def test_focused_workbench_tools_document_direct_gates_tests_and_transient_persistence():
    focused = {"T006", "T015", "T016", "T017", "T018", "T019", "T020", "T021", "T022", "T023", "T024", "T025", "T026", "T027", "T028", "T029", "T030", "T031", "T032", "T033", "T034", "T035", "T036", "T037", "T038", "T039", "T040", "T041", "T042", "T043", "T045", "T047", "T048", "T049", "T050", "T051", "T052", "T054", "T055", "T056", "T058", "T059", "T060", "T063", "T066", "T070", "T072", "T074", "T075", "T076", "T077", "T078", "T079", "T080", "T081", "T082", "T083", "T084", "T085", "T094", "T097", "T099"}
    for tool_id in focused:
        tool = get_tool(tool_id)
        assert tool is not None
        assert "require_tool_access" in tool["entitlement_enforcement_points"]
        assert "not yet wired" not in tool["entitlement_enforcement_points"]
        assert "workspace_persistence.py" in tool["persistence_scope"]
        assert "local SQLite fallback may be ephemeral" in tool["persistence_scope"]
        assert ("tests/test_shoir_target_engines.py::" in tool["unit_test"] or "tests/test_shoir_remaining_tool_engines.py::" in tool["unit_test"])
        assert tool["implementation_status"] == "IMPLEMENTED_NEEDS_VALIDATION"


def test_workbench_tier_gate_keeps_research_pack_separate_from_enterprise_plus():
    from industrial_platform_excellence import module_availability, tier_allows as workbench_tier_allows

    assert workbench_tier_allows("Research Pack", "Starter")
    assert workbench_tier_allows("Research Pack", "Professional")
    assert workbench_tier_allows("Research Pack", "Operations")
    assert workbench_tier_allows("Research Pack", "Enterprise")
    assert workbench_tier_allows("Research Pack", "Research")
    assert not workbench_tier_allows("Research Pack", "Enterprise Plus")
    assert not workbench_tier_allows("Enterprise Plus", "Research")
    assert workbench_tier_allows("Enterprise Plus", "Enterprise Plus")

    research_view = module_availability("Research Pack")
    plus_rows = research_view[research_view["Required Tier"] == "Enterprise Plus"]
    assert not plus_rows["Available"].any()


def test_rnle_ergonomics_target_has_real_gated_runner_and_explicit_validation_state():
    tool = get_tool("T046")
    assert tool is not None
    assert tool["canonical_name"] == "Ergonomics Assessment Toolkit"
    assert tool["implementation_status"] == "IMPLEMENTED_NEEDS_VALIDATION"
    assert "shoir_ergonomics.py" in tool["source_files"]
    assert "require_tool_access" in tool["entitlement_enforcement_points"]
    assert "tests/test_shoir_ergonomics.py::" in tool["unit_test"]
    assert not tier_allows_tool("Starter", "T046")
    assert not tier_allows_tool("Mid-Tier Pro", "T046")
    assert tier_allows_tool("Professional", "T046")
    assert "UNVERIFIED" in tool["browser_test"]

def test_external_configuration_targets_are_entitlement_gated_and_never_claim_active():
    connector = get_tool("T096")
    identity = get_tool("T098")
    assert connector is not None and connector["implementation_status"] == "EXTERNAL_CONFIGURATION_REQUIRED"
    assert identity is not None and identity["implementation_status"] == "EXTERNAL_CONFIGURATION_REQUIRED"
    for tool in (connector, identity):
        assert "require_tool_access" in tool["entitlement_enforcement_points"]
        assert "workspace_persistence.py" in tool["persistence_scope"]
        assert "local SQLite fallback may be ephemeral" in tool["persistence_scope"]
    assert tier_allows_tool("Enterprise", "T096")
    assert tier_allows_tool("Enterprise Plus", "T098")
    assert not tier_allows_tool("Enterprise", "T098")

