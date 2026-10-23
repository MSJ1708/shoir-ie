"""Tests for stable identity, fail-closed access and the 100-target tier contract."""
from shoir_100_tool_registry import (
    TOOL_TARGETS, TOOL_TIER_ORDER, TOOL_STATUSES, WORKBENCHES,
    audit_target_tool_registry, get_target_tool, list_target_tools,
    target_tool_access_decision, target_tool_execution_decision,
)

ORDINARY = ("Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus")
RESEARCH_BASE = {"Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Research Pack"}

def expected_allow(current, required):
    if current == "Research Pack":
        return required in RESEARCH_BASE
    if required == "Research Pack":
        return False
    return ORDINARY.index(current) >= ORDINARY.index(required)

def test_registry_has_100_unique_sequential_ids_and_complete_metadata():
    a = audit_target_tool_registry()
    assert a["count"] == a["unique_id_count"] == 100
    assert not a["duplicate_ids"] and not a["missing_fields"]
    assert not a["invalid_statuses"] and not a["invalid_tiers"] and not a["invalid_workbenches"]
    assert [row["tool_id"] for row in TOOL_TARGETS] == [f"T{i:03d}" for i in range(1,101)]
    assert all(row["implementation_status"] in TOOL_STATUSES for row in TOOL_TARGETS)
    assert all(row["workbench"] in WORKBENCHES for row in TOOL_TARGETS)

def test_six_package_tier_truth_table_for_every_target():
    for row in TOOL_TARGETS:
        for tier in TOOL_TIER_ORDER:
            decision = target_tool_access_decision(row["tool_id"], tier)
            assert decision["allowed"] is expected_allow(tier, row["target_minimum_tier"]), (
                row["tool_id"], tier, row["target_minimum_tier"], decision
            )

def test_research_pack_and_enterprise_plus_are_not_interchangeable():
    for row in TOOL_TARGETS:
        research = target_tool_access_decision(row["tool_id"], "Research Pack")
        plus = target_tool_access_decision(row["tool_id"], "Enterprise Plus")
        assert research["allowed"] is (row["target_minimum_tier"] != "Enterprise Plus")
        assert plus["allowed"] is (row["target_minimum_tier"] != "Research Pack")

def test_unknown_tool_and_unknown_tier_fail_closed():
    for token in ("", "T000", "T101", "random renamed tool"):
        assert target_tool_access_decision(token, "Enterprise")["allowed"] is False
    for tier in ("", "free premium", "Super Enterprise", "null"):
        assert target_tool_access_decision("T001", tier)["allowed"] is False
    assert target_tool_execution_decision("T101", "Enterprise")["executable"] is False

def test_existing_subscription_display_labels_resolve_to_exact_tiers():
    for tier in ("Starter Tier ($29)", "Starter Tier", "Mid-Tier Pro Tier ($79)",
                 "Professional Tier ($129)", "Enterprise Tier ($199)",
                 "Enterprise Plus Tier ($399)", "Research Pack (+$30)"):
        assert target_tool_access_decision("T001", tier)["allowed"] is True
    assert target_tool_access_decision("T074", "Research Pack (+$30)")["allowed"] is False
    assert target_tool_access_decision("T074", "Enterprise Plus Tier ($399)")["allowed"] is True

def test_display_label_customization_cannot_mutate_identity_or_policy():
    row = get_target_tool("T065")
    assert row is not None and row["canonical_name"] == "Facility Layout and SLP Studio"
    row["canonical_name"] = "renamed display"
    assert get_target_tool("T065")["canonical_name"] == "Facility Layout and SLP Studio"
    assert target_tool_access_decision("T065", "Starter")["allowed"] is True
    assert target_tool_access_decision("renamed display", "Starter")["allowed"] is False

def test_only_end_to_end_verified_targets_pass_execution_readiness():
    assert audit_target_tool_registry()["ready_for_execution_count"] == 0
    for row in TOOL_TARGETS:
        decision = target_tool_execution_decision(row["tool_id"], "Research Pack")
        assert decision["executable"] is False
        assert decision["allowed"] is (row["target_minimum_tier"] != "Enterprise Plus")

def test_registry_filters_and_copies_are_safe():
    assert any(r["tool_id"] == "T065" for r in list_target_tools(workbench="Optimization and facilities"))
    assert list_target_tools(status="MISSING") == []
    assert len(list_target_tools(search="Cpk")) >= 1

def test_registry_exposes_full_contract_metadata_for_every_target():
    for row in TOOL_TARGETS:
        for key in ("persistence_scope", "external_dependency", "entitlement_enforcement_points",
                    "unit_test_id", "integration_test_id", "browser_test_id",
                    "acceptance_gate_id", "evidence_state"):
            assert row.get(key), (row["tool_id"], key)
    assert get_target_tool("T066")["implementation_status"] == "IMPLEMENTED_NEEDS_VALIDATION"
    assert get_target_tool("T076")["implementation_status"] == "IMPLEMENTED_NEEDS_VALIDATION"
    assert "shoir_100_tool_engines.py" in get_target_tool("T066")["source_files"]
    assert "shoir_100_tool_engines.py" in get_target_tool("T076")["source_files"]

def test_numerical_targets_reference_their_actual_golden_fixture_tests():
    expected = {
        "T021": "test_standard_time_golden_fixture_and_allowance_conventions",
        "T023": "test_takt_time_and_capacity_golden_fixture",
        "T026": "test_oee_golden_fixture_and_loss_decomposition",
        "T032": "test_process_capability_golden_fixture_with_two_subgroups",
        "T055": "test_inventory_policy_golden_fixture_and_boundaries",
        "T066": "test_first_fit_decreasing_known_fixture_and_capacity_accounting",
        "T076": "test_process_mining_timezone_duration_and_transition_fixture",
        "T078": "test_carbon_emissions_requires_sourced_versioned_factor",
        "T081": "test_engineering_economics_npv_irr_and_payback_golden_fixture",
    }
    from shoir_100_tool_registry import get_target_tool
    for tool_id, test_name in expected.items():
        row = get_target_tool(tool_id)
        assert row is not None
        assert test_name in row["unit_test_id"]
