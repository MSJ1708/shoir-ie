"""Server-side entitlement policy for the premium Excel Intelligence module.

The default minimum is Enterprise. Operators may change it with
SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER without changing the Office add-in.
Invalid configuration fails closed to Enterprise Plus.
"""
from __future__ import annotations

import os

DEFAULT_MINIMUM_TIER = "Enterprise"
FAIL_CLOSED_TIER = "Enterprise Plus"
ALLOWED_TIERS = (
    "Starter",
    "Mid-Tier Pro",
    "Professional",
    "Enterprise",
    "Enterprise Plus",
    "Research Pack",
)
_TIER_LOOKUP = {tier.casefold(): tier for tier in ALLOWED_TIERS}
ENVIRONMENT_VARIABLE = "SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER"


def excel_intelligence_entitlement_config() -> dict[str, str | bool]:
    """Return the effective minimum tier and whether the override is valid."""
    raw = os.getenv(ENVIRONMENT_VARIABLE)
    if raw is None or not raw.strip():
        return {
            "minimum_tier": DEFAULT_MINIMUM_TIER,
            "configured_by": "default",
            "valid": True,
            "warning": "",
        }

    canonical = _TIER_LOOKUP.get(raw.strip().casefold())
    if canonical:
        return {
            "minimum_tier": canonical,
            "configured_by": ENVIRONMENT_VARIABLE,
            "valid": True,
            "warning": "",
        }

    return {
        "minimum_tier": FAIL_CLOSED_TIER,
        "configured_by": ENVIRONMENT_VARIABLE,
        "valid": False,
        "warning": (
            f"{ENVIRONMENT_VARIABLE} must be one of: "
            + ", ".join(ALLOWED_TIERS)
            + ". Access has been restricted to Enterprise Plus until corrected."
        ),
    }


def excel_intelligence_minimum_tier() -> str:
    """Return the effective server-side minimum tier."""
    return str(excel_intelligence_entitlement_config()["minimum_tier"])


def excel_intelligence_allowed(user_tier: str | None) -> bool:
    """Enforce the configured minimum tier; failures deny access."""
    try:
        from shoir_tier_capabilities import tier_allows

        return bool(tier_allows(str(user_tier or "Starter"), excel_intelligence_minimum_tier()))
    except Exception:
        return False
