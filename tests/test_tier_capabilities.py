from shoir_tier_capabilities import available_modules, copilot_gate, module_required_tier, normalize_tier, tier_allows
from industrial_platform import tier_allows as platform_tier_allows


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
