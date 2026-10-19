"""Unit coverage for staging-only disposable E2E account provisioning."""
import base64
import json

import pytest

from scripts.provision_staging_e2e_accounts import (
    ACTIVE_TIER,
    EXPIRED_AT,
    PROJECT_URL,
    PRODUCTION_PROJECT_REF,
    RESEARCH_TIER,
    STARTER_TIER,
    STAGING_PROJECT_REF,
    _expected_accounts,
    is_publishable_key,
    is_service_role_key,
)


def _jwt(role: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


def test_script_is_pinned_to_staging_not_production():
    assert STAGING_PROJECT_REF == "hfhrosthswcybccepmak"
    assert STAGING_PROJECT_REF != PRODUCTION_PROJECT_REF
    assert PROJECT_URL == f"https://{STAGING_PROJECT_REF}.supabase.co"


def test_client_and_server_keys_are_not_interchangeable():
    assert is_publishable_key("sb_publishable_staging_test")
    assert is_publishable_key(_jwt("anon"))
    assert not is_publishable_key("sb_secret_staging_test")
    assert not is_publishable_key(_jwt("service_role"))
    assert is_service_role_key("sb_secret_staging_test")
    assert is_service_role_key(_jwt("service_role"))
    assert not is_service_role_key("sb_publishable_staging_test")
    assert not is_service_role_key(_jwt("anon"))


def test_expected_fixture_has_six_distinct_disposable_accounts_and_tiers():
    accounts = _expected_accounts()
    assert len(accounts) == 6
    assert len({a["username"].casefold() for a in accounts}) == 6
    assert all(a["username"].startswith("shoir-e2e-") for a in accounts)
    assert len({a["password"] for a in accounts}) == 6
    assert all(len(a["password"]) >= 24 for a in accounts)
    tiers = {a["secret_prefix"]: a["tier"] for a in accounts}
    assert tiers["active"] == ACTIVE_TIER
    assert tiers["second"] == ACTIVE_TIER
    assert tiers["module"] == ACTIVE_TIER
    assert tiers["starter"] == STARTER_TIER
    assert tiers["expired"] == STARTER_TIER
    assert tiers["research_module"] == RESEARCH_TIER
    assert EXPIRED_AT.startswith("2000-")


def test_fixture_email_domains_are_reserved_invalid_domains():
    assert all(a["email"].endswith("@example.invalid") for a in _expected_accounts())
