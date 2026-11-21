"""Unit coverage for staging-only disposable E2E account provisioning."""
import base64
import json
import os
import stat

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
    _write_private_json,
    is_publishable_key,
    is_service_role_key,
)


def _jwt(role: str, ref: str = STAGING_PROJECT_REF) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"role": role, "ref": ref}).encode()).decode().rstrip("=")
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
    assert not is_publishable_key(_jwt("anon", PRODUCTION_PROJECT_REF))
    assert not is_publishable_key(_jwt("anon", ""))

    assert is_service_role_key("sb_secret_staging_test")
    assert is_service_role_key(_jwt("service_role"))
    assert not is_service_role_key(_jwt("service_role", PRODUCTION_PROJECT_REF))
    assert not is_service_role_key("sb_publishable_staging_test")
    assert not is_service_role_key(_jwt("anon"))


def test_private_credential_writer_is_atomic_owner_only_and_exclusive(tmp_path):
    destination = tmp_path / ".staging-e2e-credentials.json"
    _write_private_json(destination, {"status": "first"}, exclusive=True)

    assert json.loads(destination.read_text(encoding="utf-8")) == {"status": "first"}
    if os.name != "nt":
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600

    with pytest.raises(FileExistsError):
        _write_private_json(destination, {"status": "must-not-overwrite"}, exclusive=True)

    assert json.loads(destination.read_text(encoding="utf-8")) == {"status": "first"}

    _write_private_json(destination, {"status": "updated"})
    assert json.loads(destination.read_text(encoding="utf-8")) == {"status": "updated"}
    assert sorted(path.name for path in tmp_path.iterdir()) == [destination.name]


def test_private_credential_writer_refuses_symlink_destination(tmp_path):
    protected = tmp_path / "protected.json"
    protected.write_text('{"status":"untouched"}', encoding="utf-8")
    destination = tmp_path / ".staging-e2e-credentials.json"
    try:
        destination.symlink_to(protected)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available to this test user.")

    with pytest.raises(OSError, match="symbolic link"):
        _write_private_json(destination, {"status": "overwritten"})

    assert protected.read_text(encoding="utf-8") == '{"status":"untouched"}'


def test_expected_fixture_has_seven_distinct_disposable_accounts_and_tiers():
    accounts = _expected_accounts()
    assert len(accounts) == 7
    assert len({a["username"].casefold() for a in accounts}) == 7
    assert all(a["username"].startswith("shoir-e2e-") for a in accounts)
    assert len({a["password"] for a in accounts}) == 7
    assert all(len(a["password"]) >= 24 for a in accounts)
    tiers = {a["secret_prefix"]: a["tier"] for a in accounts}
    assert tiers["active"] == ACTIVE_TIER
    assert tiers["second"] == ACTIVE_TIER
    assert tiers["module"] == ACTIVE_TIER
    assert tiers["starter"] == STARTER_TIER
    assert tiers["expired"] == STARTER_TIER
    assert tiers["research_module"] == RESEARCH_TIER
    assert tiers["inactive"] == STARTER_TIER
    inactive = next(a for a in accounts if a["secret_prefix"] == "inactive")
    assert inactive["username"] == "shoir-e2e-inactive"
    assert EXPIRED_AT.startswith("2000-")


def test_fixture_email_domains_are_reserved_invalid_domains():
    assert all(a["email"].endswith("@example.invalid") for a in _expected_accounts())
