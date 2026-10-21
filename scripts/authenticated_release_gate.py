#!/usr/bin/env python3
"""On-demand authenticated backend release gate for dedicated disposable test accounts.

Never run this against customer or administrator accounts. The script refuses
usernames outside the shoir-e2e- prefix, does not print passwords/tokens, and
restores the active test workspace after its save/reload probe.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from staging_e2e_guard import validate_edge_from_env

REPORT_PATH = Path(os.environ.get("SHOIR_E2E_REPORT", "artifacts/authenticated-release-gate/backend-report.json"))
PREFIX = "shoir-e2e-"
TIMEOUT = 20
RESULTS: list[dict[str, Any]] = []


def record(case: str, account_class: str, passed: bool | None, detail: str) -> None:
    status = "PASS" if passed is True else "FAIL" if passed is False else "SKIP"
    RESULTS.append({
        "case": case,
        "account_class": account_class,
        "status": status,
        "detail": detail,
    })
    print(f"[{status}] {case} ({account_class}): {detail}")


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Required environment value is missing: {name}")
    return value


def validate_test_username(name: str, label: str) -> str:
    value = name.strip()
    if not value.casefold().startswith(PREFIX):
        raise ValueError(f"{label} must start with {PREFIX!r}; refusing to risk a customer/admin account.")
    return value


class EdgeAPI:
    def __init__(self, url: str, publishable_key: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": publishable_key,
            "Content-Type": "application/json",
        }
        # Supabase's current sb_publishable_* keys are not JWTs and must be
        # sent in the apikey header only. Legacy anon JWTs still need Bearer auth.
        if not publishable_key.startswith("sb_publishable_"):
            self.headers["Authorization"] = f"Bearer {publishable_key}"

    def call(self, action: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        body = dict(payload)
        body["action"] = action
        response = requests.post(self.url, json=body, headers=self.headers, timeout=TIMEOUT)
        try:
            data = response.json()
        except Exception:
            data = {}
        return response.status_code, data


def safe_call(api: EdgeAPI, case: str, account_class: str, action: str, payload: dict[str, Any]):
    try:
        status, data = api.call(action, payload)
        return status, data
    except Exception as exc:
        record(case, account_class, False, f"Edge request failed ({type(exc).__name__}); response body suppressed.")
        return None, {}


def login_failure_detail(status: int | None, data: dict[str, Any], expected: str) -> str:
    """Return actionable authentication diagnostics without exposing secrets or raw API bodies."""
    if status is None:
        return f"{expected}; the Edge request did not return a valid HTTP response."
    error = str(data.get("error") or "")
    if status == 401 and error == "Invalid username or password.":
        return (
            f"{expected}; HTTP 401 means the staging API rejected the credentials or account state. "
            "The dedicated E2E password may be out of sync with the staging account. "
            "Run scripts/recover_staging_e2e_credentials.py on the trusted workstation; "
            "do not create duplicate accounts or modify production."
        )
    if status == 429:
        return f"{expected}; HTTP 429 indicates the staging login throttle is active. Stop retries and let the window expire."
    if status == 503:
        return f"{expected}; HTTP 503 indicates staging authentication protection is unavailable. Inspect the Edge Function and login-throttle RPC."
    if status == 403 and error == "SUBSCRIPTION_EXPIRED"::
        return f"{expected}; HTTP 403 reports an expired subscription, not an active workspace session."
    if status == 200:
        return f"{expected}; HTTP 200 was returned but the session/tier metadata did not satisfy the release-gate contract."
    return f"{expected}; staging Edge API returned unexpected HTTP {status}. Response details were suppressed."


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        edge_url = validate_edge_from_env()
        key = require_env("SHOIR_E2E_PUBLISHABLE_KEY")
        # HTTP header values must be ASCII/Latin-1 encodable. Supabase
        # publishable keys and legacy anon JWTs are ASCII; reject a pasted
        # non-ASCII character or hidden formatting before making live requests.
        if not key.isascii():
            raise ValueError(
                "SHOIR_E2E_PUBLISHABLE_KEY contains non-ASCII characters; replace it with the exact "
                "staging project's publishable/anon key copied as plain text, without quotes or hidden formatting."
            )
        active_user = validate_test_username(require_env("SHOIR_E2E_ACTIVE_USERNAME"), "active account")
        active_password = require_env("SHOIR_E2E_ACTIVE_PASSWORD")
        second_user = validate_test_username(require_env("SHOIR_E2E_SECOND_USERNAME"), "second account")
        second_password = require_env("SHOIR_E2E_SECOND_PASSWORD")
        starter_user = validate_test_username(require_env("SHOIR_E2E_STARTER_USERNAME"), "starter account")
        starter_password = require_env("SHOIR_E2E_STARTER_PASSWORD")
        expired_user = validate_test_username(require_env("SHOIR_E2E_EXPIRED_USERNAME"), "expired account")
        expired_password = require_env("SHOIR_E2E_EXPIRED_PASSWORD")
        active_expected_tier = os.environ.get("SHOIR_E2E_ACTIVE_EXPECTED_TIER", "Enterprise Plus Tier ($399)").strip()
    except ValueError as exc:
        print(f"[FAIL] Preflight: {exc}", file=sys.stderr)
        return 2

    if len({active_user.casefold(), second_user.casefold(), starter_user.casefold(), expired_user.casefold()}) != 4:
        print("[FAIL] Preflight: active, second, starter and expired test accounts must be distinct.", file=sys.stderr)
        return 2

    api = EdgeAPI(edge_url, key)
    active_token = ""
    second_token = ""
    starter_token = ""
    expired_token = ""
    reload_token = ""
    original_workspace: str | None = None
    workspace_was_loaded = False
    write_started = False
    restore_expected = "{}"
    sentinel_key = "__shoir_e2e_release_probe__"
    sentinel_value = secrets.token_hex(16)

    try:
        # Active account login and entitlement are checked without exposing its username.
        status, data = safe_call(api, "active_login", "active", "login",
                                 {"username": active_user, "password": active_password})
        active_token = str(data.get("token") or "")
        record("active_login", "active",
               status == 200 and bool(active_token) and data.get("username", "").casefold() == active_user.casefold()
               and str(data.get("tier") or "").strip() == active_expected_tier
               and str(data.get("role") or "") != "Enterprise Admin",
               "Expected active non-admin session and configured tier." if (status == 200 and bool(active_token) and data.get("username", "").casefold() == active_user.casefold() and str(data.get("tier") or "").strip() == active_expected_tier and str(data.get("role") or "") != "Enterprise Admin") else login_failure_detail(status, data, "Active account login failed"))

        # Verify generic invalid-password behavior; use a random wrong value, never an actual secret.
        bad_status, bad = safe_call(api, "invalid_password", "active", "login",
                                    {"username": active_user, "password": "invalid-" + secrets.token_hex(12)})
        record("invalid_password", "active",
               bad_status == 401 and not bad.get("token") and bad.get("error") == "Invalid username or password.",
               "Invalid credentials rejected without issuing a session.")

        status2, data2 = safe_call(api, "second_login", "second", "login",
                                   {"username": second_user, "password": second_password})
        second_token = str(data2.get("token") or "")
        record("second_login", "second",
               status2 == 200 and bool(second_token) and str(data2.get("role") or "") != "Enterprise Admin",
               "Second dedicated non-admin account can authenticate." if (status2 == 200 and bool(second_token) and str(data2.get("role") or "") != "Enterprise Admin") else login_failure_detail(status2, data2, "Second account login failed"))

        status3, data3 = safe_call(api, "starter_login", "starter", "login",
                                   {"username": starter_user, "password": starter_password})
        starter_token = str(data3.get("token") or "")
        record("starter_tier", "starter",
               status3 == 200 and bool(starter_token) and "starter" in str(data3.get("tier") or "").casefold()
               and str(data3.get("role") or "") != "Enterprise Admin",
               "Starter tier is returned for the dedicated Starter test identity." if (status3 == 200 and bool(starter_token) and "starter" in str(data3.get("tier") or "").casefold() and str(data3.get("role") or "") != "Enterprise Admin") else login_failure_detail(status3, data3, "Starter account login failed"))

        # An active non-admin must not invoke administrator APIs even with a valid token.
        if active_token:
            status, admin_data = safe_call(api, "admin_action_denied", "active", "admin_list_requests_session",
                                           {"username": active_user, "token": active_token})
            record("admin_action_denied", "active",
                   status is not None and status >= 400 and bool(admin_data.get("error")),
                   "Server-side administrator API rejects a non-admin token.")

        # Workspace access is bound to the session owner, not a caller-supplied username.
        if active_token and second_token:
            status, data = safe_call(api, "cross_owner_load_denied", "active", "workspace_load",
                                     {"username": second_user, "token": active_token})
            record("cross_owner_load_denied", "active",
                   status is not None and status >= 400 and bool(data.get("error")),
                   "A valid token cannot read a different account's workspace.")
            before_status, before_data = safe_call(api, "second_workspace_before", "second", "workspace_load",
                                                   {"username": second_user, "token": second_token})
            second_before = before_data.get("state_json") if before_status == 200 else None
            save_status, save_data = safe_call(api, "cross_owner_save_denied", "active", "workspace_save",
                                               {"username": second_user, "token": active_token,
                                                "state_json": json.dumps({"forbidden": sentinel_value})})
            after_status, after_data = safe_call(api, "second_workspace_after", "second", "workspace_load",
                                                  {"username": second_user, "token": second_token})
            record("cross_owner_save_denied", "active",
                   save_status is not None and save_status >= 400 and bool(save_data.get("error"))
                   and before_status == 200 and after_status == 200
                   and before_data.get("state_json") == after_data.get("state_json") == second_before,
                   "Cross-owner save is denied and the second account's stored workspace is unchanged.")

        # Persist one temporary marker, login again with a fresh session, read it,
        # then restore the account's original serialized workspace in every exit path.
        if active_token:
            status, data = safe_call(api, "active_workspace_before", "active", "workspace_load",
                                     {"username": active_user, "token": active_token})
            workspace_was_loaded = status == 200
            original_workspace = data.get("state_json") if workspace_was_loaded else None
            if not workspace_was_loaded:
                record("workspace_load", "active", False, "Could not load the active test workspace.")
            elif original_workspace is not None and (not isinstance(original_workspace, str) or len(original_workspace) > 1_000_000):
                record("workspace_round_trip", "active", False, "Workspace is not a small string suitable for a safe test-account probe.")
            else:
                try:
                    prior_state = json.loads(original_workspace) if original_workspace else {}
                    if not isinstance(prior_state, dict):
                        raise ValueError("Workspace is not a JSON object.")
                except Exception:
                    record("workspace_round_trip", "active", False, "Workspace is not a JSON object; refusing to overwrite it.")
                else:
                    prior_state.pop(sentinel_key, None)
                    restore_expected = original_workspace if original_workspace else "{}"
                    probe_state = dict(prior_state)
                    probe_state[sentinel_key] = sentinel_value
                    status, result = safe_call(api, "workspace_save", "active", "workspace_save",
                                               {"username": active_user, "token": active_token,
                                                "state_json": json.dumps(probe_state, ensure_ascii=False)})
                    write_started = status == 200 and bool(result.get("ok"))
                    record("workspace_save", "active", write_started, "Temporary test marker write acknowledged." if write_started else "Temporary workspace write failed.")
                    if write_started:
                        fresh_status, fresh_login = safe_call(api, "fresh_login", "active", "login",
                                                              {"username": active_user, "password": active_password})
                        reload_token = str(fresh_login.get("token") or "")
                        read_status, restored = (None, {})
                        if fresh_status == 200 and reload_token:
                            read_status, restored = safe_call(api, "workspace_reload", "active", "workspace_load",
                                                              {"username": active_user, "token": reload_token})
                        state_text = restored.get("state_json") if read_status == 200 else None
                        try:
                            reloaded_state = json.loads(state_text) if state_text else {}
                        except Exception:
                            reloaded_state = {}
                        record("workspace_relogin_restore", "active",
                               fresh_status == 200 and read_status == 200 and reloaded_state.get(sentinel_key) == sentinel_value,
                               "Saved marker was visible after a new authenticated session." if reloaded_state.get(sentinel_key) == sentinel_value else "Marker did not survive a new authenticated session.")

                        if reload_token:
                            restore_status, restore_data = safe_call(api, "workspace_restore", "active", "workspace_save",
                                                                      {"username": active_user, "token": reload_token,
                                                                       "state_json": restore_expected})
                            restore_ok = restore_status == 200 and bool(restore_data.get("ok"))
                            record("workspace_restore", "active",
                                   restore_ok,
                                   "Original test workspace restored." if restore_ok else "Original workspace restoration failed; manual retry will run.")
                            write_started = not restore_ok

        # Expiry should produce only a renewal-scoped token, never workspace access.
        expired_status, expired_data = safe_call(api, "expired_login", "expired", "login",
                                                  {"username": expired_user, "password": expired_password})
        expired_token = str(expired_data.get("token") or "")
        expired_ok = expired_status == 403 and expired_data.get("error") == "SUBSCRIPTION_EXPIRED" and bool(expired_token) and expired_data.get("renewal_only") is True
        record("expired_login_renewal_only", "expired", expired_ok,
               "Expired account receives a renewal-only session, not a workspace session." if valid else login_failure_detail(status4, data4, "Expired-account renewal-only login contract failed"))
        if expired_token:
            st_load, load_data = safe_call(api, "expired_workspace_load_denied", "expired", "workspace_load",
                                           {"username": expired_user, "token": expired_token})
            st_save, save_data = safe_call(api, "expired_workspace_save_denied", "expired", "workspace_save",
                                           {"username": expired_user, "token": expired_token, "state_json": "{}"})
            st_renew, renew_data = safe_call(api, "renewal_missing_reference", "expired", "renew_request",
                                             {"username": expired_user, "token": expired_token, "transaction_id": ""})
            record("expired_workspace_load_denied", "expired", st_load is not None and st_load >= 400 and bool(load_data.get("error")),
                   "Renewal-only token cannot read workspace data.")
            record("expired_workspace_save_denied", "expired", st_save is not None and st_save >= 400 and bool(save_data.get("error")),
                   "Renewal-only token cannot write workspace data.")
            record("renewal_requires_reference", "expired",
                   st_renew == 400 and "reference" in str(renew_data.get("error") or "").casefold(),
                   "Missing transaction reference is rejected before a renewal record is created.")

        if os.environ.get("SHOIR_E2E_VERIFY_LOGIN_THROTTLE", "").strip().casefold() in {"1", "true", "yes", "on"}:
            # Use a synthetic non-account identity so the test cannot lock a real
            # user's bucket. This uses 9 attempts from the runner IP bucket and
            # should only be enabled for an intentional release-gate run.
            throttle_user = PREFIX + "throttle-" + secrets.token_hex(8)
            observed = []
            for attempt_number in range(9):
                code, payload = safe_call(
                    api, "login_throttle_probe", "synthetic", "login",
                    {"username": throttle_user, "password": "invalid-" + secrets.token_hex(16)},
                )
                observed.append(code)
                if code is None:
                    break
            record(
                "login_throttle_blocks_excess_attempts",
                "synthetic",
                observed == [401] * 8 + [429],
                "Eight synthetic attempts were rejected generically and the ninth was rate-limited."
                if observed == [401] * 8 + [429]
                else "Rate-limit responses differed from the expected 8x401 then 429 sequence.",
            )
        else:
            record(
                "login_throttle_blocks_excess_attempts",
                "synthetic",
                None,
                "Skipped: set the GitHub Actions variable SHOIR_E2E_VERIFY_LOGIN_THROTTLE=true for an intentional live limiter probe.",
            )

        inactive_user = os.environ.get("SHOIR_E2E_INACTIVE_USERNAME", "").strip()
        inactive_password = os.environ.get("SHOIR_E2E_INACTIVE_PASSWORD", "")
        if inactive_user or inactive_password:
            if not inactive_user or not inactive_password:
                record("inactive_account_denied", "inactive", False, "Both inactive-account test credentials must be configured together.")
            else:
                try:
                    inactive_user = validate_test_username(inactive_user, "inactive account")
                    status, data = safe_call(api, "inactive_account_denied", "inactive", "login",
                                             {"username": inactive_user, "password": inactive_password})
                    record("inactive_account_denied", "inactive",
                           status == 401 and not data.get("token"),
                           "Inactive account credentials do not create a server session.")
                except ValueError as exc:
                    record("inactive_account_denied", "inactive", False, str(exc))
        else:
            record("inactive_account_denied", "inactive", None, "Skipped: configure a dedicated inactive test account to verify the server guard.")

    finally:
        # Restore the original dedicated test workspace before revoking the
        # session needed to perform a retry. Never use a production/customer user.
        if write_started and workspace_was_loaded:
            restore_token = reload_token or active_token
            if restore_token:
                try:
                    status, data = api.call("workspace_save", {
                        "username": active_user,
                        "token": restore_token,
                        "state_json": restore_expected,
                    })
                    restored_ok = status == 200 and bool(data.get("ok"))
                    record("workspace_restore_retry", "active", restored_ok,
                           "Original test workspace restored on retry." if restored_ok else "Workspace restore retry failed; manual review is required.")
                    write_started = not restored_ok
                except Exception:
                    record("workspace_restore_retry", "active", False, "Workspace restore retry failed; manual review is required.")
            else:
                record("workspace_restore_retry", "active", False, "No valid test session remained to restore the workspace.")

        # Never leave probe sessions active after the test.
        for label, username, token in (
            ("active", active_user, active_token),
            ("active-fresh", active_user, reload_token),
            ("second", second_user, second_token),
            ("starter", starter_user, starter_token),
            ("expired", expired_user, expired_token),
        ):
            if token:
                try:
                    status, data = api.call("logout", {"username": username, "token": token})
                    record("session_revocation", label, status == 200 and data.get("ok") is True,
                           "Dedicated test session revoked.")
                except Exception:
                    record("session_revocation", label, False, "Could not confirm cleanup of a dedicated test session.")

    REPORT_PATH.write_text(json.dumps({
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": edge_url,
        "overall": "PASS" if all(item["status"] != "FAIL" for item in RESULTS) else "FAIL",
        "cases": RESULTS,
    }, indent=2), encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")
    return 0 if all(item["status"] != "FAIL" for item in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
