from shoir_tier_capabilities import copilot_gate, module_required_tier, normalize_tier, tier_allows

def test_tier_order_and_research_are_distinct():
    assert normalize_tier("Starter Tier") == "Starter"
    assert normalize_tier("Enterprise Plus Tier") == "Enterprise Plus"
    assert normalize_tier("Research Pack") == "Research Pack"
    assert tier_allows("Starter", "Starter")
    assert tier_allows("Research Pack", "Enterprise Plus")
    assert not tier_allows("Enterprise Plus", "Research Pack")

def test_copilot_and_research_module_requirements():
    assert module_required_tier("AI Copilot") == "Starter"
    assert module_required_tier("Research AI") == "Research Pack"
    assert tier_allows("Starter", "Starter")
    assert not tier_allows("Starter", "Research Pack")
    assert not tier_allows("Enterprise", "Research Pack")

def test_copilot_blocks_package_gated_actions():
    gate = copilot_gate("run Monte Carlo simulation", "Starter Tier")
    assert gate is not None and gate["required_tier"] == "Enterprise"
    research_gate = copilot_gate("run hypothesis testing", "Enterprise Tier")
    assert research_gate is not None and research_gate["required_tier"] == "Research Pack"
    assert copilot_gate("what is ANOVA?", "Starter Tier") is None
