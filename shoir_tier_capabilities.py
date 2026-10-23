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

__all__ = [
    "MODULE_EXPLORER_TIERS",
    "MODULE_REQUIREMENTS",
    "COPILOT_TOOL_REQUIREMENTS",
    "unique_modules",
    "normalize_tier",
    "tier_allows",
    "module_required_tier",
    "available_modules",
    "audit_module_entitlement_coverage",
    "copilot_gate",
    "copilot_capabilities",
]



def unique_modules(modules: Iterable[str]) -> list[str]:
    """Return non-empty module labels once, preserving their first-seen order."""
    seen = set()
    result = []
    for module in modules:
        label = str(module or "").strip()
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result


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
    "Autonomous Global Supply Chain & Resilient Logistics Network": "Enterprise",
    "Zero-Waste Closed-Loop Mega-Factory (Industrial Symbiosis Engine)": "Enterprise",
    "Real-Time Urban Mobility & Smart Infrastructure Grid": "Enterprise",
    "Fully Automated Emergency Response & Humanitarian Disaster Logistics System": "Enterprise",
    "L-SIMS — Local Capability & Dynamic Industrial Readiness Simulator": "Enterprise",
    "Autonomous Kinetic-Digital Twin (AKDT) for Industrial Logistics Resilience": "Enterprise Plus",
    # Mirror the minimum tiers in industrial_platform.PLATFORM_CATALOG. The
    # regression tests compare both sources to prevent silent policy drift.
    "Industrial Operating System": "Enterprise",
    "Global Project & Digital Thread": "Enterprise",
    "Engineering Validation Center": "Starter",
    "Industrial Data Model & Digital Thread": "Mid-Tier Pro",
    "Advanced Planning & Scheduling": "Professional",
    "Quality Engineering & Reliability": "Professional",
    "Capital Investment & Engineering Economics": "Professional",
    "Workforce Engineering": "Professional",
    "Industrial Sustainability & LCA": "Professional",
    "Benchmarking & Engineering Standards": "Professional",
    "Manufacturing Execution System": "Enterprise",
    "Industrial Simulation Lab": "Enterprise",
    "3D Factory Designer": "Enterprise",
    "Industrial Connectivity Hub": "Enterprise",
    "Multi-Objective Optimization": "Enterprise",
    "Robust & Resilient Optimization": "Enterprise",
    "Engineering Model Registry": "Enterprise",
    "Experiment Lab": "Enterprise",
    "Experiment Engine": "Enterprise",
    "Industrial Control Center": "Enterprise",
    "Engineering Decision Center": "Enterprise",
    "Industrial Data Platform": "Enterprise",
    "Advanced ML Demand Forecasting": "Enterprise",
    "Scenario Versioning & Comparison": "Mid-Tier Pro",
    "Team Workspaces & RBAC": "Enterprise",
    "Executive Report Center": "Enterprise",
    "Localization & Multi-Currency": "Mid-Tier Pro",
    "Production Bottleneck & Capacity Recovery Study": "Mid-Tier Pro",
    # Remaining names declared in industrial_platform.TIER_FEATURES.
    "Carbon Accounting": "Mid-Tier Pro",
    "MEIO Matrix": "Mid-Tier Pro",
    "Fleet Routing": "Mid-Tier Pro",
    "Production Planning & Control (PPC)": "Mid-Tier Pro",
    "Monte Carlo Sim": "Enterprise",
    "Sensitivity Analysis": "Enterprise",
    "Digital Twin & Discrete-Event Simulation": "Enterprise",
    # Explicit minimum tier from app.py's subscription feature registry: Starter.
    "MILP Solvers": "Starter",
    "Inventory Playback": "Starter",
    "Core IE Tools": "Starter",
    "Subscriptions": "Starter",
    "Persistence": "Starter",
    "Facility Layout & Warehousing": "Starter",
    "Enterprise Integration & Collaboration": "Starter",
    "Venture Studio": "Starter",
    # Explicit minimum tier from app.py's subscription feature registry: Mid-Tier Pro.
    "IoT Digital Twin": "Mid-Tier Pro",
    "Slotting & Gantt": "Mid-Tier Pro",
    "Warehouse Heatmap": "Mid-Tier Pro",
    "Supplier Risk Matrix": "Mid-Tier Pro",
    "Scenarios": "Mid-Tier Pro",
    "AGV Fleet Dispatcher": "Mid-Tier Pro",
    "Geospatial Network Designer": "Mid-Tier Pro",
    "Lean Manufacturing & Shop Floor Operations": "Mid-Tier Pro",
    "Quality Control, Six Sigma & Reliability": "Mid-Tier Pro",
    "Engineering Economics & Finance": "Mid-Tier Pro",
    # Explicit minimum tier from app.py's subscription feature registry: Enterprise.
    "FastAPI Gateway": "Enterprise",
    "Webhook Alerts": "Enterprise",
    "Agentic Workflows": "Enterprise",
    "Control Tower": "Enterprise",
    "Cryptographic Ledger": "Enterprise",
    "Predictive Maintenance Hub": "Enterprise",
    "Human Factors & Ergonomics (NIOSH)": "Enterprise",
    "Green IE & Sustainability": "Enterprise",
    # Explicit minimum tier from app.py's subscription feature registry: Research Pack.
    "Evidence Degradation & Decision-Readiness Lab": "Research Pack",
    "LaTeX Document Formatter": "Research Pack",
    "Live Reproducible Paper Canvas": "Research Pack",
    "Adversarial Chaos & Shock Injector": "Research Pack",
    "Adversarially Stressed Synthetic Industrial Twins": "Research Pack",
    "Automated Theory-to-Code Formalizer": "Research Pack",
    "Real-Time Quantum-Classical Hybrid Optimization Router": "Research Pack",
    "Automated Code-to-Formal-Proof Verifier": "Research Pack",
    "Decentralized Cryptographic Reproducibility Vault": "Research Pack",
    "Autonomous Parametric Surrogate Swarm": "Research Pack",
    "🔌 Edge-Connected IoT Digital Twin Bridge": "Research Pack",
    "🔌 Universal Cross-Domain Mathematical Isomorphism Engine (UCMIE)": "Research Pack",
    "🔄 Autonomous Epistemic Cross-Disciplinary Falsification Matrix (AE-FRESM)": "Research Pack",
    "Autonomous Cognitive Operations & Zero-Knowledge Mesh (ACO-ZKMS)": "Research Pack",
    "⚡ ACO-ZKMS Master Engine": "Research Pack",
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
    "autonomous global supply chain": "Enterprise",
    "closed-loop mega-factory": "Enterprise",
    "industrial symbiosis": "Enterprise",
    "urban mobility grid": "Enterprise",
    "humanitarian disaster logistics": "Enterprise",
    "local capability simulator": "Enterprise",
    "l-sims": "Enterprise",
    "industrial logistics resilience twin": "Enterprise Plus",
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


def _recognized_tier_requirement(value: str) -> Optional[str]:
    """Resolve an explicit tier label or alias; unknown policy labels stay unresolved."""
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if "research" in raw:
        return "Research Pack"
    if "enterprise plus" in raw or "industrial enterprise" in raw:
        return "Enterprise Plus"
    if "enterprise" in raw:
        return "Enterprise"
    if "professional" in raw:
        return "Professional"
    if "mid-tier pro" in raw or "mid tier pro" in raw:
        return "Mid-Tier Pro"
    if raw == "pro" or raw.startswith("pro tier"):
        return "Mid-Tier Pro"
    if "starter" in raw or raw in {"basic", "free"}:
        return "Starter"
    return None


def tier_allows(current: str, required: str) -> bool:
    """Fail closed for unknown required tiers; Research Pack is not Enterprise Plus.

    Research Pack is an add-on package: it inherits ordinary access through
    Enterprise and receives research-only features, but it never grants
    Enterprise Plus. Enterprise Plus likewise does not imply Research Pack.
    """
    current_tier = normalize_tier(current)
    required_tier = _recognized_tier_requirement(required)
    if required_tier is None:
        return False

    if current_tier == "Research Pack":
        return required_tier in {
            "Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Research Pack"
        }
    if required_tier == "Research Pack":
        return current_tier == "Research Pack"

    return TIER_ORDER.index(current_tier) >= TIER_ORDER.index(required_tier)


def module_required_tier(module: str) -> Optional[str]:
    return MODULE_REQUIREMENTS.get(str(module).strip())


def audit_module_entitlement_coverage(modules: Iterable[str]) -> dict[str, object]:
    """Audit explicit tier-policy coverage for an observed module catalogue.

    A missing policy is reported as unresolved rather than being inferred to mean
    that the module is free or secure. This is an audit helper only: it does not
    authorize access or change the existing module-availability behavior.
    """
    catalog = unique_modules(modules)
    unmapped: list[str] = []
    invalid: list[dict[str, str]] = []

    for module in catalog:
        required = module_required_tier(module)
        if required is None:
            unmapped.append(module)
        elif required not in TIER_ORDER:
            invalid.append({"module": module, "required_tier": required})

    total = len(catalog)
    explicit = total - len(unmapped) - len(invalid)
    if total == 0:
        status = "EMPTY"
    elif not unmapped and not invalid:
        status = "COMPLETE"
    else:
        status = "INCOMPLETE"

    return {
        "status": status,
        "total_modules": total,
        "explicit_policy_count": explicit,
        "unmapped_count": len(unmapped),
        "unmapped_modules": unmapped,
        "invalid_policy_count": len(invalid),
        "invalid_policy_modules": invalid,
        "coverage_percent": round((100.0 * explicit / total), 2) if total else 0.0,
        "policy_source": "MODULE_REQUIREMENTS",
    }


def available_modules(tier: str, modules: Iterable[str]) -> list[str]:
    """Return only capabilities with an explicit, recognized, permitted policy.

    Unmapped names are intentionally omitted here; callers can surface them in
    diagnostics through audit_module_entitlement_coverage(), but must not treat
    a missing policy as free access.
    """
    result = []
    for module in modules:
        required = module_required_tier(str(module))
        if required in TIER_ORDER and tier_allows(tier, required):
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
