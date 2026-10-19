from shoir_tier_capabilities import (MODULE_REQUIREMENTS, TIER_ORDER, audit_module_entitlement_coverage, available_modules, copilot_gate, module_required_tier, normalize_tier, tier_allows)
from industrial_platform import PLATFORM_CATALOG, tier_allows as platform_tier_allows


def test_tier_order_and_research_are_distinct():
    assert normalize_tier("Starter Tier") == "Starter"
    assert normalize_tier("Enterprise Plus Tier") == "Enterprise Plus"
    assert normalize_tier("Research Pack ($30 add-on)") == "Research Pack"
    assert tier_allows("Starter", "Starter")
    assert tier_allows("Research Pack", "Enterprise")
    assert tier_allows("Research Pack", "Research Pack")
    assert not tier_allows("Research Pack", "Enterprise Plus")
    assert not tier_allows("Enterprise Plus", "Research Pack")


def test_platform_tier_gate_matches_shared_research_add_on_policy():
    # Research Pack inherits the Enterprise base but not Enterprise Plus.
    assert platform_tier_allows("Research Pack ($30 add-on)", "Enterprise")
    assert platform_tier_allows("Research Pack ($30 add-on)", "Research Pack")
    assert not platform_tier_allows("Research Pack ($30 add-on)", "Enterprise Plus")
    assert platform_tier_allows("Enterprise Plus Tier ($399)", "Enterprise Plus")
    assert not platform_tier_allows("Enterprise Plus Tier ($399)", "Research Pack")


def test_copilot_and_research_module_requirements():
    assert module_required_tier("AI Copilot") == "Starter"
    assert module_required_tier("Research AI") == "Research Pack"
    assert tier_allows("Starter", "Starter")
    assert not tier_allows("Starter", "Research Pack")
    assert not tier_allows("Enterprise", "Research Pack")




def test_research_pack_cannot_access_enterprise_plus_modules_or_copilot_actions():
    candidates = [
        "Research AI",
        "Advanced Engineering Copilot",
        "Live Industrial Digital Twin",
        "Enterprise Security & Governance",
        "Predictive Maintenance Digital Twin",
    ]
    assert available_modules("Research Pack ($30 add-on)", candidates) == ["Research AI"]
    assert available_modules("Enterprise Plus Tier ($399)", candidates) == [
        "Advanced Engineering Copilot",
        "Live Industrial Digital Twin",
        "Enterprise Security & Governance",
        "Predictive Maintenance Digital Twin",
    ]

    for phrase in (
        "open Advanced Engineering Copilot",
        "open Live Industrial Digital Twin",
        "open Enterprise Security & Governance",
        "open Predictive Maintenance Digital Twin",
    ):
        gate = copilot_gate(phrase, "Research Pack")
        assert gate is not None and gate["required_tier"] == "Enterprise Plus"


def test_copilot_blocks_package_gated_actions():
    gate = copilot_gate("run Monte Carlo simulation", "Starter Tier")
    assert gate is not None and gate["required_tier"] == "Enterprise"
    research_gate = copilot_gate("run hypothesis testing", "Enterprise Tier")
    assert research_gate is not None and research_gate["required_tier"] == "Research Pack"
    assert copilot_gate("run Monte Carlo simulation", "Research Pack") is None
    assert copilot_gate("what is ANOVA?", "Starter Tier") is None



def test_module_entitlement_audit_reports_unmapped_catalog_items():
    report = audit_module_entitlement_coverage([
        "AI Copilot",
        "Research AI",
        "Module with no explicit policy",
        "AI Copilot",
        "",
    ])

    assert report["status"] == "INCOMPLETE"
    assert report["total_modules"] == 3
    assert report["explicit_policy_count"] == 2
    assert report["unmapped_count"] == 1
    assert report["unmapped_modules"] == ["Module with no explicit policy"]
    assert report["invalid_policy_count"] == 0
    assert report["coverage_percent"] == 66.67
    assert report["policy_source"] == "MODULE_REQUIREMENTS"


def test_module_entitlement_audit_reports_empty_catalog_without_claiming_coverage():
    report = audit_module_entitlement_coverage([])

    assert report["status"] == "EMPTY"
    assert report["total_modules"] == 0
    assert report["coverage_percent"] == 0.0


def test_module_entitlement_audit_exposes_invalid_policy_tier(monkeypatch):
    monkeypatch.setitem(MODULE_REQUIREMENTS, "Audit-only invalid mapping", "Unrecognized tier")

    report = audit_module_entitlement_coverage(["Audit-only invalid mapping"])

    assert report["status"] == "INCOMPLETE"
    assert report["explicit_policy_count"] == 0
    assert report["invalid_policy_count"] == 1
    assert report["invalid_policy_modules"] == [
        {"module": "Audit-only invalid mapping", "required_tier": "Unrecognized tier"}
    ]


def test_declared_module_entitlement_tiers_are_known_tiers():
    assert set(MODULE_REQUIREMENTS.values()).issubset(set(TIER_ORDER))



def test_every_platform_catalog_entry_has_an_explicit_matching_shared_tier_policy():
    names = [str(item["name"]) for item in PLATFORM_CATALOG]
    report = audit_module_entitlement_coverage(names)

    assert report["status"] == "COMPLETE"
    assert report["total_modules"] == len(names)
    assert report["total_modules"] == len(set(names))
    assert report["unmapped_modules"] == []
    assert report["invalid_policy_modules"] == []
    assert all(
        module_required_tier(str(item["name"])) == normalize_tier(str(item["tier"]))
        for item in PLATFORM_CATALOG
    )
