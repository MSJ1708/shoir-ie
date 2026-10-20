from __future__ import annotations

import base64
import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "recover_staging_e2e_credentials.py"
SPEC = importlib.util.spec_from_file_location("recover_staging_e2e_credentials", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def fake_jwt(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).decode("ascii").rstrip("=")
    return "header." + payload + ".signature"


class StagingE2ECredentialRecoveryTests(unittest.TestCase):
    def test_password_hash_matches_edge_function_format(self) -> None:
        password = "test-only-" + ("x" * 32)
        stored = recovery.hash_password(password)
        self.assertEqual(len(stored.split("$")), 2)
        self.assertEqual(len(stored.split("$")[0]), 32)
        self.assertEqual(len(stored.split("$")[1]), 64)
        self.assertTrue(recovery.verify_password_hash(stored, password))
        self.assertFalse(recovery.verify_password_hash(stored, password + "-wrong"))

    def test_recovery_targets_only_six_fixed_test_accounts(self) -> None:
        usernames = [row["username"] for row in recovery.ACCOUNT_SPECS]
        self.assertEqual(len(usernames), 6)
        self.assertEqual(len(set(usernames)), 6)
        self.assertTrue(all(name.startswith("shoir-e2e-") for name in usernames))
        self.assertNotIn("sho", usernames)
        self.assertEqual(recovery.STAGING_PROJECT_REF, "hfhrosthswcybccepmak")
        self.assertNotEqual(recovery.STAGING_PROJECT_REF, recovery.PRODUCTION_PROJECT_REF)

    def test_staging_service_role_jwt_is_accepted_but_wrong_project_is_not(self) -> None:
        valid = fake_jwt({"role": "service_role", "ref": recovery.STAGING_PROJECT_REF})
        wrong_project = fake_jwt({"role": "service_role", "ref": recovery.PRODUCTION_PROJECT_REF})
        self.assertTrue(recovery.is_service_role_key(valid))
        self.assertFalse(recovery.is_service_role_key(wrong_project))
        self.assertFalse(recovery.is_service_role_key(fake_jwt({"role": "anon", "ref": recovery.STAGING_PROJECT_REF})))
        self.assertFalse(recovery.is_service_role_key("sb_publishable_demo"))
        self.assertTrue(recovery.is_service_role_key("sb_secret_demo"))

    def test_staging_publishable_key_is_accepted_but_secret_key_is_not(self) -> None:
        valid = fake_jwt({"role": "anon", "ref": recovery.STAGING_PROJECT_REF})
        wrong_project = fake_jwt({"role": "anon", "ref": recovery.PRODUCTION_PROJECT_REF})
        self.assertTrue(recovery.is_publishable_key(valid))
        self.assertFalse(recovery.is_publishable_key(wrong_project))
        self.assertTrue(recovery.is_publishable_key("sb_publishable_demo"))
        self.assertFalse(recovery.is_publishable_key("sb_secret_demo"))
        self.assertFalse(recovery.is_publishable_key("key with whitespace"))
        self.assertFalse(recovery.is_publishable_key("bad\u200bkey"))

    def make_row(self, spec: dict, *, role: str = "User", active: bool = True,
                 tier: str | None = None, expired: bool | None = None) -> dict:
        now = datetime.now(timezone.utc)
        is_expired = spec["expired"] if expired is None else expired
        expiry = now - timedelta(days=1) if is_expired else now + timedelta(days=30)
        return {
            "username_lc": spec["username"],
            "role": role,
            "tier": tier or spec["tier"],
            "active": active,
            "subscription_expires_at": expiry.isoformat(),
            "password_hash": recovery.hash_password("prior-test-password"),
        }

    def test_expected_non_expired_accounts_pass_preflight(self) -> None:
        now = datetime.now(timezone.utc)
        for spec in recovery.ACCOUNT_SPECS:
            row = self.make_row(spec)
            recovery.validate_existing_account(row, spec, now)

    def test_preflight_refuses_wrong_role_active_state_tier_and_expiry(self) -> None:
        now = datetime.now(timezone.utc)
        active = next(spec for spec in recovery.ACCOUNT_SPECS if spec["prefix"] == "active")
        expired = next(spec for spec in recovery.ACCOUNT_SPECS if spec["prefix"] == "expired")

        for row in (
            self.make_row(active, role="Enterprise Admin"),
            self.make_row(active, active=False),
            self.make_row(active, tier="Starter Tier ($29)"),
            self.make_row(active, expired=True),
            self.make_row(expired, expired=False),
        ):
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    recovery.validate_existing_account(row, active if row["username_lc"] == active["username"] else expired, now)

    def test_preflight_requires_existing_password_hash(self) -> None:
        now = datetime.now(timezone.utc)
        spec = recovery.ACCOUNT_SPECS[0]
        row = self.make_row(spec)
        row["password_hash"] = ""
        with self.assertRaises(ValueError):
            recovery.validate_existing_account(row, spec, now)


if __name__ == "__main__":
    unittest.main()
