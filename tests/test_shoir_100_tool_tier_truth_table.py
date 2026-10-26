"""Release-gate contract for the canonical 100 targets and six package states.

These tests evaluate execution authorization by stable target ID, independently
of card visibility, user-renamed labels, or the legacy module catalogue.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from shoir_tool_registry import (
    BASE_TIERS,
    TOOL_STATUS_VALUES,
    TOOL_TIER_ORDER,
    TOOL_TARGETS,
    get_tool,
    require_tool_access,
    tier_allows_tool,
    validate_tool_registry,
)

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv"
ORDINARY_TIERS = ("Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus")
ALL_TIERS = (*ORDINARY_TIERS, "Research Pack")
RESEARCH_INHERITED_TIERS = {
    "Starter",
    "Mid-Tier Pro",
    "Professional",
    "Enterprise",
    "Research Pack",
}


def expected_access(current: str, required: str) -> bool:
    """Independent package truth table; Research Pack is an add-on, not tier six."""
    if current == "Research Pack":
        return required in RESEARCH_INHERITED_TIERS
    if required == "Research Pack":
        return False
    return ORDINARY_TIERS.index(current) >= ORDINARY_TIERS.index(required)


def load_matrix() -> list[dict[str, str]]:
    with MATRIX.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_registry_and_matrix_account_for_exactly_t001_through_t100():
    expected_ids = [f"T{i:03d}" for i in range(1, 101)]
    ids = [row["tool_id"] for row in TOOL_TARGETS]
    matrix = load_matrix()
    matrix_ids = [row["tool_id"] for row in matrix]

    assert ids == expected_ids
    assert matrix_ids == expected_ids
    assert len(set(ids)) == 100
    assert len(set(row["canonical_name"] for row in TOOL_TARGETS)) == 100
    assert validate_tool_registry() == []
    assert set(TOOL_TIER_ORDER) == set(ALL_TIERS)
    assert set(BASE_TIERS) == set(ORDINARY_TIERS)


def test_matrix_names_tiers_and_statuses_match_the_runtime_registry():
    by_id = {row["tool_id"]: row for row in TOOL_TARGETS}
    matrix = load_matrix()
    mismatches = []
    for row in matrix:
        target = by_id.get(row["tool_id"])
        if target is None:
            mismatches.append((row["tool_id"], "missing runtime registry target"))
            continue
        for field, matrix_field in (
            ("canonical_name", "canonical_name"),
            ("target_minimum_tier", "target_minimum_tier"),
            ("implementation_status", "implementation_status"),
        ):
            if target[field] != row[matrix_field]:
                mismatches.append(
                    (row["tool_id"], field, target[field], row[matrix_field])
                )
        if row["implementation_status"] not in TOOL_STATUS_VALUES:
            mismatches.append(
                (row["tool_id"], "unknown matrix status", row["implementation_status"])
            )
    assert not mismatches, f"Registry/matrix drift: {mismatches}"


@pytest.mark.parametrize("target", TOOL_TARGETS, ids=lambda t: t["tool_id"])
def test_every_target_matches_independent_six_package_truth_table(target):
    target_id = target["tool_id"]
    required = target["target_minimum_tier"]
    for current in ALL_TIERS:
        expected = expected_access(current, required)
        assert tier_allows_tool(current, target_id) is expected, (
            target_id,
            current,
            required,
            expected,
        )
        if expected:
            assert require_tool_access(current, target_id)["tool_id"] == target_id
        else:
            with pytest.raises(PermissionError):
                require_tool_access(current, target_id)


def test_unknown_target_ids_fail_closed_at_execution_time():
    for tier in ALL_TIERS:
        assert not tier_allows_tool(tier, "T999")
        with pytest.raises(PermissionError):
            require_tool_access(tier, "T999")
    assert get_tool("T999") is None


def test_research_pack_and_enterprise_plus_are_not_interchangeable():
    research_only = [
        target["tool_id"]
        for target in TOOL_TARGETS
        if target["target_minimum_tier"] == "Research Pack"
    ]
    enterprise_plus_only = [
        target["tool_id"]
        for target in TOOL_TARGETS
        if target["target_minimum_tier"] == "Enterprise Plus"
    ]
    assert research_only, "Expected at least one Research Pack-restricted target."
    assert enterprise_plus_only, "Expected at least one Enterprise Plus-restricted target."
    for target_id in research_only:
        assert tier_allows_tool("Research Pack", target_id)
        assert not tier_allows_tool("Enterprise Plus", target_id)
    for target_id in enterprise_plus_only:
        assert tier_allows_tool("Enterprise Plus", target_id)
        assert not tier_allows_tool("Research Pack", target_id)
