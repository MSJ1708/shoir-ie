"""Central tier capabilities and Copilot access policy for Shoir-IE."""

from __future__ import annotations

import re
from typing import Iterable, Optional

TIER_ORDER = [
    "Starter",
    "Mid-Tier Pro",
    "Professional",
    "Enterprise",
    "Enterprise Plus",
    "Research Pack",
]

# Shared by the public module explorer so no paid tier silently disappears from filters.
MODULE_EXPLORER_TIERS = ("All capabilities", *TIER_ORDER)

MODULE_REQUIREMENTS = {
    "AI Copilot": "Starter",
    "ShadowShift — Micro-Loss & Recovery Intelligence": "Enterprise",
    "Excel Data Cleaning & Import": "Starter",
    "Industrial Workbook": "Starter",
    "Research AI": "Research Pack",
    "Statistical Hypothesis Testing": "Research Pack",
    "Literature & Citation Matrix": "Research Pack",
    "Advanced Regression Analysis": "Research Pack",
    "Paper-to-Simulation Auto-Engine": "Research Pack",
    "Adversarial AI Peer-Review Swarm": "Research Pack",
    # These are Enterprise Plus-only modules in app.py's tier4_features menu.
    "Advanced Engineering Copilot": "Enterprise Plus",
    "Live Industrial Digital Twin": "Enterprise Plus",
    "Enterprise Security & Governance": "Enterprise Plus",
    "Predictive Maintenance Digital Twin": "Enterprise Plus",
}

COPILOT_TOOL_REQUIREMENTS = {
    "shadowshift": "Enterprise",
    "run milp": "Starter",
    "optimize the network": "Starter",
    "clean workbook": "Starter",
    "format excel": "Starter",
    "format workbook": "Starter",
    "excel cleaning": "Starter",
    "check my tier": "Starter",
    "show my account": "Starter",
    "forecast": "Enterprise",
    "monte carlo": "Enterprise",
    "sensitivity analysis": "Enterprise",
    "agentic workflow": "Enterprise",
    "routing optimization": "Mid-Tier Pro",
    "fleet routing": "Mid-Tier Pro",
    "quality analysis": "Mid-Tier Pro",
    "gage r&r": "Mid-Tier Pro",
    "process capability": "Mid-Tier Pro",
    "npv": "Mid-Tier Pro",
    "meio": "Mid-Tier Pro",
    "research ai": "Research Pack",
    "hypothesis test": "Research Pack",
    "hypothesis testing": "Research Pack",
    "anova": "Research Pack",
    "t-test": "Research Pack",
    "peer review": "Research Pack",
    "literature matrix": "Research Pack",
    "reproducible paper": "Research Pack",
    "paper-to-simulation": "Research Pack",
    # Keep conversational actions aligned with the Enterprise Plus menu.
    "advanced engineering copilot": "Enterprise Plus",
    "live industrial digital twin": "Enterprise Plus",
    "enterprise security & governance": "Enterprise Plus",
    "predictive maintenance digital twin": "Enterprise Plus",
}


def normalize_tier(value: str) -> str:
    v = str(value or "Starter").strip().lower()
    if "research" in v:
        return "Research Pack"
    if "enterprise plus" in v or "industrial enterprise" in v:
        return "Enterprise Plus"
    if "enterprise" in v:
        return "Enterprise"
    if "professional" in v:
        return "Professional"
    if "pro" in v:
        return "Mid-Tier Pro"
    return "Starter"


def tier_allows(current: str, required: str) -> bool:
    """Enforce the product menu: Research Pack inherits Enterprise, plus research.

    Research Pack is an add-on package in the app, not a grant of the
    Enterprise Plus-only tier. Keep research entitlement independent from
    the ordinary tier ladder so one package never implies another add-on.
    """
    current_tier = normalize_tier(current)
    required_tier = normalize_tier(required)

    if current_tier == "Research Pack":
        return required_tier in {
            "Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Research Pack"
        }
    if required_tier == "Research Pack":
        return current_tier == "Research Pack"

    return TIER_ORDER.index(current_tier) >= TIER_ORDER.index(required_tier)


def module_required_tier(module: str) -> Optional[str]:
    return MODULE_REQUIREMENTS.get(str(module).strip())


def available_modules(tier: str, modules: Iterable[str]) -> list[str]:
    result = []
    for module in modules:
        required = module_required_tier(str(module))
        if required is None or tier_allows(tier, required):
            result.append(str(module))
    return result


def _looks_like_action_request(prompt: str) -> bool:
    p = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
    return bool(re.search(
        r"\b(run|execute|perform|calculate|analy[sz]e|build|create|generate|export|clean|format|"
        r"compare|optimi[sz]e|fit|test|review|simulate|forecast|open|use|apply|do)\b",
        p,
    ))


def copilot_gate(prompt: str, tier: str) -> Optional[dict[str, str]]:
    p = re.sub(r"\s+", " ", str(prompt or "").strip().lower())
    if not _looks_like_action_request(p):
        return None

    # More specific phrases are evaluated first so a broad request cannot
    # accidentally bypass a package-specific capability gate.
    for phrase, required in sorted(COPILOT_TOOL_REQUIREMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in p and not tier_allows(tier, required):
            return {
                "required_tier": required,
                "current_tier": normalize_tier(tier),
                "phrase": phrase,
                "message": (
                    f"🔒 **{phrase.title()}** is outside your current package. "
                    f"Your package is **{normalize_tier(tier)}**; this capability requires "
                    f"**{required}**. I can still explain the method or help you use the "
                    f"capabilities included in your package."
                ),
            }
    return None


def copilot_capabilities(tier: str, allowed_modules: Iterable[str]) -> dict[str, object]:
    normalized = normalize_tier(tier)
    return {
        "tier": normalized,
        "modules": available_modules(normalized, allowed_modules),
        "can_research": tier_allows(normalized, "Research Pack"),
        "can_enterprise": tier_allows(normalized, "Enterprise"),
        "can_professional": tier_allows(normalized, "Professional"),
    }
