#!/usr/bin/env python3
"""Recover credentials for the six existing Shoir-IE staging E2E accounts.

This fail-closed helper is pinned to the staging Supabase project. It never
creates or deletes accounts, never touches the production project, and never
prints or writes passwords, password hashes, API keys, or session tokens.

The six passwords are generated in memory, reset for the matching existing
staging rows, and synchronized to GitHub Actions secrets. If it is interrupted,
rerunning is safe: it resets those same six identities again and synchronizes
their secrets rather than attempting to provision duplicate accounts.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from typing import Any

STAGING_PROJECT_REF = "hfhrosthswcybccepmak"
PRODUCTION_PROJECT_REF = "gcsamrdaeraxieaagsta"
PROJECT_URL = f"https://{STAGING_PROJECT_REF}.supabase.co"
EDGE_URL = f"{PROJECT_URL}/functions/v1/shoir-persistence"
REPOSITORY = "MSJ1708/shoir-ie"
PBKDF2_ITERATIONS = 200_000
REQUEST_TIMEOUT_SECONDS = 20

# These identities must already exist. This script is never an account creator.
ACCOUNT_SPECS = (
    {"prefix": "active", "username": "shoir-e2e-active", "tier": "Enterprise Plus Tier ($399)", "expired": False},
    {"prefix": "second", "username": "shoir-e2e-second", "tier": "Enterprise Plus Tier ($399)", "expired": False},
    {"prefix": "starter", "username": "shoir-e2e-starter", "tier": "Starter Tier ($29)", "expired": False},
    {"prefix": "expired", "username": "shoir-e2e-expired", "tier": "Starter Tier ($29)", "expired": True},
    {"prefix": "module", "username": "shoir-e2e-module", "tier": "Enterprise Plus Tier ($399)", "expired": False},
    {"prefix": "research_module", "username": "shoir-e2e-research", "tier": "Research Pack ($30 add-on)", "expired": False},
)


class _NoRedirect(HTTPRedirectHandler):
    """Never forward credentials or session tokens through HTTP redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _jwt_claims(value: str) -> dict[str, Any]:
    parts = value.split(".")
    if len(parts) != 3:
        return {}
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def is_service_role_key(value: str) -> bool:
    key = str(value or "").strip()
    if not key or not key.isascii() or any(ord(ch) < 33 or ord(ch) > 126 for ch in key):
        return False
    if key.startswith("sb_secret_"):
        return len(key) > len("sb_secret_")
    if key.startswith("sb_publishable_"):
        return False
    claims = _jwt_claims(key)
    if claims.get("role") != "service_role":
        return False
    return not claims.get("ref") or claims.get("ref") == STAGING_PROJECT_REF


def is_publishable_key(value: str) -> bool:
    key = str(value or "").strip()
    if not key or not key.isascii() or any(ord(ch) < 33 or ord(ch) > 126 for ch in key):
        return False
    if key.startswith("sb_publishable_"):
        return len(key) > len("sb_publishable_")
    if key.startswith("sb_secret_"):
        return False
    claims = _jwt_claims(key)
    if claims.get("role") != "anon":
        return False
    return not claims.get("ref") or claims.get("ref") == STAGING_PROJECT_REF


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    salt_hex = salt.hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32
    ).hex()
    return salt_hex + "$" + digest


def verify_password_hash(stored: str, password: str) -> bool:
    if not stored or "$" not in stored or not password:
        return False
    salt_hex, expected = stored.split("$", 1)
    if len(salt_hex) != 32 or len(expected) != 64:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        bytes.fromhex(expected)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32
    ).hex()
    return hmac.compare_digest(actual, expected)


def _request_json(key: str, method: str, url: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    # New secret API keys are used through apikey only. Legacy service-role JWTs
    # also need Bearer authorization.
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    if method in {"POST", "PATCH"}:
        headers["Prefer"] = "return=representation"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with build_opener(_NoRedirect()).open(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
            if not raw:
                return response.status, None
            try:
                return response.status, json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                return response.status, None
    except HTTPError as exc:
        raw = exc.read()
        try:
            result = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeError, json.JSONDecodeError):
            result = None
        return exc.code, result
    except URLError:
        raise RuntimeError("Could not reach the fixed staging Supabase endpoint.") from None


def _rest_call(key: str, method: str, table: str, username: str, payload: dict | None = None):
    if table != "shoir_accounts" or username not in {spec["username"] for spec in ACCOUNT_SPECS}:
        raise RuntimeError("Refused a request outside the fixed E2E account allowlist.")
    query = urlencode({
        "select": "username_lc,role,tier,active,subscription_expires_at,password_hash",
        "username_lc": f"eq.{username}",
    })
    return _request_json(key, method, f"{PROJECT_URL}/rest/v1/{table}?{query}", payload)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A staging E2E account is missing its subscription expiry.")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("A staging E2E account has a timestamp without timezone information.")
    return parsed.astimezone(timezone.utc)


def validate_existing_account(row: dict[str, Any], spec: dict[str, Any], now: datetime | None = None) -> None:
    """Validate account identity/tier/state before allowing a password reset."""
    now = now or datetime.now(timezone.utc)
    if row.get("username_lc") != spec["username"]:
        raise ValueError("Staging account identity did not match the allowlisted username.")
    if row.get("role") != "User" or row.get("active") is not True:
        raise ValueError(f"{spec['prefix']} must be an active non-administrator test account.")
    if row.get("tier") != spec["tier"]:
        raise ValueError(f"{spec['prefix']} has an unexpected tier; no password was changed.")
    if not isinstance(row.get("password_hash"), str) or "$" not in row["password_hash"]:
        raise ValueError(f"{spec['prefix']} does not have a valid existing password hash.")
    expiry = _parse_timestamp(row.get("subscription_expires_at"))
    if spec["expired"]:
        if expiry > now:
            raise ValueError("The expired test account is no longer expired; no password was changed.")
    elif expiry <= now + timedelta(hours=1):
        raise ValueError(f"{spec['prefix']} must have an active subscription with more than one hour remaining.")


def _store_github_secret(name: str, value: str) -> None:
    if not name.startswith("SHOIR_E2E_"):
        raise RuntimeError("Refused to write a secret outside the Shoir-IE E2E namespace.")
    try:
        result = subprocess.run(
            ["gh", "secret", "set", name, "--repo", REPOSITORY],
            input=value,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError(f"Could not update GitHub Actions secret {name}.") from None
    if result.returncode != 0:
        raise RuntimeError(f"Could not update GitHub Actions secret {name}; check repository permissions and retry.")
    print(f"[PASS] GitHub Actions secret synchronized: {name}")


def _call_edge(publishable_key: str, action: str, payload: dict[str, Any]):
    body = dict(payload)
    body["action"] = action
    return _request_json(publishable_key, "POST", EDGE_URL, body)


def _password_secret_names(prefix: str) -> tuple[str, str]:
    mapping = {
        "active": ("SHOIR_E2E_ACTIVE_USERNAME", "SHOIR_E2E_ACTIVE_PASSWORD"),
        "second": ("SHOIR_E2E_SECOND_USERNAME", "SHOIR_E2E_SECOND_PASSWORD"),
        "starter": ("SHOIR_E2E_STARTER_USERNAME", "SHOIR_E2E_STARTER_PASSWORD"),
        "expired": ("SHOIR_E2E_EXPIRED_USERNAME", "SHOIR_E2E_EXPIRED_PASSWORD"),
        "module": ("SHOIR_E2E_MODULE_USERNAME", "SHOIR_E2E_MODULE_PASSWORD"),
        "research_module": ("SHOIR_E2E_RESEARCH_MODULE_USERNAME", "SHOIR_E2E_RESEARCH_MODULE_PASSWORD"),
    }
    return mapping[prefix]


def _logout(publishable_key: str, username: str, token: str) -> bool:
    try:
        status, result = _call_edge(publishable_key, "logout", {"username": username, "token": token})
    except Exception:
        return False
    return status == 200 and isinstance(result, dict) and result.get("ok") is True


def run_recovery() -> int:
    if STAGING_PROJECT_REF == PRODUCTION_PROJECT_REF:
        raise RuntimeError("Production/staging safety check failed.")

    service_key = os.environ.pop("SHOIR_STAGING_SERVICE_KEY", "").strip()
    publishable_key = os.environ.pop("SHOIR_STAGING_PUBLISHABLE_KEY", "").strip()
    if not is_service_role_key(service_key):
        raise ValueError("Missing/invalid server key. Use the staging service-role/secret key, never a publishable key.")
    if not is_publishable_key(publishable_key):
        raise ValueError("Missing/invalid staging publishable/anon key. Copy it directly from the staging project.")

    # Confirm the GitHub CLI is authenticated before changing any account.
    try:
        auth = subprocess.run(
            ["gh", "auth", "status", "--hostname", "github.com"],
            capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("GitHub CLI is required; install it and authenticate with gh auth login.") from None
    if auth.returncode != 0:
        raise RuntimeError("GitHub CLI authentication failed; run gh auth login and retry.")

    print("Staging E2E credential recovery")
    print(f"Fixed project: {STAGING_PROJECT_REF}")
    print("Scope: six already-existing shoir-e2e-* accounts. No account creation or deletion.")

    # Validate the publishable key against the fixed staging REST API before
    # storing it in GitHub. This prevents accidentally replacing the Actions
    # secret with an opaque sb_publishable_* key copied from another project.
    try:
        key_status, _ = _request_json(publishable_key, "GET", f"{PROJECT_URL}/rest/v1/")
    except Exception as exc:
        raise RuntimeError(f"Staging publishable-key preflight failed ({type(exc).__name__}); no passwords were changed.") from None
    if key_status != 200:
        raise RuntimeError(f"Publishable key was not accepted by the fixed staging REST API (HTTP {key_status}); no passwords were changed.")

    # Check every target row before the first write. No fallback to production.
    initial_rows: dict[str, dict[str, Any]] = {}
    now = datetime.now(timezone.utc)
    for spec in ACCOUNT_SPECS:
        status, rows = _rest_call(service_key, "GET", "shoir_accounts", spec["username"])
        if status != 200 or not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError(
                f"Could not confirm exactly one existing staging row for {spec['prefix']} (HTTP {status}); no passwords were changed."
            )
        row = rows[0]
        validate_existing_account(row, spec, now)
        initial_rows[spec["username"]] = row
        print(f"[PASS] Existing account preflight: {spec['prefix']}")

    # Confirm Edge Function reachability without touching a real account bucket.
    probe_user = "shoir-e2e-recovery-probe-" + secrets.token_hex(8)
    try:
        probe_status, probe_data = _call_edge(
            publishable_key, "login",
            {"username": probe_user, "password": "invalid-" + secrets.token_urlsafe(16)},
        )
    except Exception as exc:
        raise RuntimeError(f"Staging Edge Function preflight failed ({type(exc).__name__}); no passwords were changed.") from None
    if probe_status != 401 or not isinstance(probe_data, dict) or probe_data.get("error") != "Invalid username or password.":
        raise RuntimeError(f"Staging Edge Function preflight returned unexpected HTTP {probe_status}; no passwords were changed.")

    # Keep the publishable key in sync with the staging key just validated above.
    _store_github_secret("SHOIR_E2E_PUBLISHABLE_KEY", publishable_key)

    credentials: dict[str, dict[str, str]] = {}
    # Updating one row and immediately synchronizing its secret makes a retry
    # safe if PowerShell closes mid-run. A retry rotates the same six users only.
    for spec in ACCOUNT_SPECS:
        password = secrets.token_urlsafe(32)
        password_hash = hash_password(password)
        query = urlencode({
            "username_lc": f"eq.{spec['username']}",
            "role": "eq.User",
            "active": "eq.true",
            "select": "username_lc,role,tier,active,subscription_expires_at,password_hash",
        })
        url = f"{PROJECT_URL}/rest/v1/shoir_accounts?{query}"
        status, updated = _request_json(
            service_key, "PATCH", url,
            {"password_hash": password_hash, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        if status not in (200, 204) or not isinstance(updated, list) or len(updated) != 1:
            raise RuntimeError(
                f"Could not confirm the password reset for {spec['prefix']} (HTTP {status}). Rerun this recovery script to resynchronize; no account was created."
            )

        row = updated[0]
        if (
            row.get("username_lc") != spec["username"]
            or row.get("role") != "User"
            or row.get("active") is not True
            or row.get("tier") != spec["tier"]
            or not hmac.compare_digest(str(row.get("password_hash") or ""), password_hash)
        ):
            raise RuntimeError(
                f"Password reset verification failed for {spec['prefix']}. Rerun recovery after reviewing staging."
            )

        credentials[spec["prefix"]] = {"username": spec["username"], "password": password}
        username_secret, password_secret = _password_secret_names(spec["prefix"])
        _store_github_secret(username_secret, spec["username"])
        _store_github_secret(password_secret, password)
        print(f"[PASS] Existing staging password reset and stored for {spec['prefix']} (value hidden).")

    # Verify actual server-side login/tier/expiry behavior with the new values.
    live_tokens: list[tuple[str, str]] = []
    try:
        for spec in ACCOUNT_SPECS:
            account = credentials[spec["prefix"]]
            status, result = _call_edge(
                publishable_key, "login",
                {"username": account["username"], "password": account["password"]},
            )
            if not isinstance(result, dict):
                raise RuntimeError(f"Login verification for {spec['prefix']} returned an invalid response.")

            token = str(result.get("token") or "")
            valid_common = bool(token) and result.get("username", "").casefold() == spec["username"]
            if spec["expired"]:
                valid = (
                    status == 403 and result.get("error") == "SUBSCRIPTION_EXPIRED"
                    and result.get("renewal_only") is True and valid_common
                )
            else:
                valid = (
                    status == 200 and result.get("ok") is True and valid_common
                    and result.get("tier") == spec["tier"]
                    and result.get("role") != "Enterprise Admin"
                )
            if token:
                live_tokens.append((spec["username"], token))
            if not valid:
                raise RuntimeError(
                    f"Staging Edge login/tier/expiry verification failed for {spec['prefix']} (HTTP {status}); Actions secrets have been synchronized. Do not create duplicate accounts."
                )
            print(f"[PASS] Edge login and expected tier/expiry: {spec['prefix']}")

    finally:
        cleanup_failed = False
        for username, token in live_tokens:
            if not _logout(publishable_key, username, token):
                cleanup_failed = True
                print("[FAIL] Could not confirm revocation of one temporary E2E session.")
        if cleanup_failed:
            raise RuntimeError("A temporary staging recovery session could not be confirmed revoked.")

    print("[PASS] All six existing staging E2E accounts reset and verified.")
    print("[PASS] Matching GitHub Actions username/password secrets synchronized.")
    print("No passwords, hashes, API keys, or session tokens were printed or saved to disk.")
    print("Next: let PowerShell wait for ordinary CI, then launch a new authenticated release gate.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run_recovery())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"STAGING E2E RECOVERY BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
