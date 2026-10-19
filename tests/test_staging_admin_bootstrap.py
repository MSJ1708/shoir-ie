"""Regression tests for the staging-only admin bootstrap helpers."""
import base64
import json

import pytest

from scripts.bootstrap_staging_admin import (
    ADMIN_ROLE,
    ADMIN_TIER,
    PRODUCTION_PROJECT_REF,
    STAGING_PROJECT_REF,
    hash_password,
    is_service_role_key,
    verify_password,
)


def test_password_hash_matches_the_edge_function_format():
    hashed = hash_password("staging-only password for tests", salt_hex="00" * 16)
    salt, digest = hashed.split("$")
    assert salt == "00" * 16
    assert len(digest) == 64
    assert verify_password(hashed, "staging-only password for tests")
    assert not verify_password(hashed, "wrong password")


def test_password_hash_uses_random_salts():
    first = hash_password("a sufficiently long password")
    second = hash_password("a sufficiently long password")
    assert first != second
    assert verify_password(first, "a sufficiently long password")
    assert verify_password(second, "a sufficiently long password")


def test_only_service_role_or_secret_keys_are_accepted():
    def jwt(payload):
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        return f"header.{body}.signature"

    assert is_service_role_key("sb_secret_test_key")
    assert is_service_role_key(jwt({"role": "service_role"}))
    assert not is_service_role_key("sb_publishable_test_key")
    assert not is_service_role_key(jwt({"role": "anon"}))
    assert not is_service_role_key("not-a-key")


def test_staging_target_is_hard_pinned_and_distinct_from_production():
    from scripts import bootstrap_staging_admin

    assert STAGING_PROJECT_REF == "hfhrosthswcybccepmak"
    assert STAGING_PROJECT_REF != PRODUCTION_PROJECT_REF
    assert bootstrap_staging_admin.PROJECT_URL == (
        f"https://{STAGING_PROJECT_REF}.supabase.co"
    )
    assert ADMIN_ROLE == "Enterprise Admin"
    assert ADMIN_TIER == "Enterprise Plus Tier ($399)"


def test_password_hash_rejects_bad_salt():
    with pytest.raises(ValueError):
        hash_password("pw", salt_hex="abc")
