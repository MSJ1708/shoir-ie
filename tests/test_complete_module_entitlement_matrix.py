"""Exhaustive tier-policy tests across every canonical module inventory entry."""

from __future__ import annotations

import csv
from pathlib import Path

from shoir_tier_capabilities import (
    TIER_ORDER,
    available_modules,
    module_required_tier,
    normalize_tier,
    tier_allows,
)

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "MODULE_TIER_INVENTORY.csv"
ORDINARY_TIERS = ("Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus")
ALL_TIERS = (*ORDINARY_TIERS, "Research Pack")
RESEARCH_PACK_BASE_TIERS = {"Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Research Pack"}


def load_inventory() -> list[dict[str, str]]:
    with INVENTORY.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def expected_policy_decision(current: str, required: str) -> bool:
    """Independent entitlement truth table; Research Pack is not tier six."""
    if current == "Research Pack":
        return required in RESEARCH_PACK_BASE_TIERS
    if required == "Research Pack":
        return False
    return ORDINARY_TIERS.index(current) >= ORDINARY_TIERS.index(required)


def test_every_inventory_module_has_an_explicit_matching_shared_requirement():
    rows = load_inventory()
    assert len(rows) == 97, f"Expected the current 97-name inventory; found {len(rows)}."
    names = [row["module_name"].strip() for row in rows]
    assert len(names) == len(set(names)), "The source inventory must contain unique module names."
    assert set(TIER_ORDER) == set(ALL_TIERS)

    mismatches = []
    for row in rows:
        name = row["module_name"].strip()
        declared = row["minimum_tier"].strip()
        actual = module_required_tier(name)
        if actual is None:
            mismatches.append({ "module": name, "inventory_tier": declared, "shared_policy": None })
            continue
        if normalize_tier(actual) != normalize_tier(declared):
            mismatches.append({ "module": name, "inventory_tier": declared, "shared_policy": actual })
    assert not mismatches, f"Missing or drifting module entitlement mappings: {mismatches}"


def test_every_module_decision_matches_independent_truth_table_for_every_tier():
    rows = load_inventory()
    disagreements = []
    for row in rows:
        module = row["module_name"].strip()
        required = module_required_tier(module)
        assert required is not None, f"Missing explicit requirement for {module!r}."
        required = normalize_tier(required)
        for current in ALL_TIERS:
            expected = expected_policy_decision(current, required)
            actual = tier_allows(current, required)
            visible = module in available_modules(current, [module])
            if actual != expected or visible != expected:
                disagreements.append({
                    "module": module,
                    "required": required,
                    "current": current,
                    "expected": expected,
                    "tier_allows": actual,
                    "available_modules": visible,
                })
    assert not disagreements, f"Tier decision truth table has mismatches: {disagreements}"


def test_research_pack_is_an_add_on_not_implicit_enterprise_plus():
    for required in ("Starter", "Mid-Tier Pro", "Professional", "Enterprise"):
        assert tier_allows("Research Pack", required)
    assert tier_allows("Research Pack", "Research Pack")
    assert not tier_allows("Research Pack", "Enterprise Plus")
    assert not tier_allows("Enterprise Plus", "Research Pack")
    for module in ("Research AI", "Statistical Hypothesis Testing", "Literature & Citation Matrix"):
        assert module in available_modules("Research Pack", [module])
        assert module not in available_modules("Enterprise Plus", [module])



def test_unmapped_module_and_unknown_tier_fail_closed():
    assert available_modules("Starter", ["Unmapped protected capability"]) == []
    assert not tier_allows("Unrecognized subscription label", "Starter")
    assert not tier_allows("Starter", "Unrecognized protected tier")
