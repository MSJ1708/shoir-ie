#!/usr/bin/env python3
"""One-time bootstrap for the first Shoir-IE administrator in staging only.

This intentionally never accepts a target URL or project ref from input. It is
pinned to the approved staging project, uses an interactive hidden prompt for
the staging service key and password, and refuses to overwrite an existing
'sho' administrator identity. Customer/test accounts must still be created
through the regular registration and approval workflow.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import secrets
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STAGING_PROJECT_REF = "hfhrosthswcybccepmak"
PRODUCTION_PROJECT_REF = "gcsamrdaeraxieaagsta"
PROJECT_URL = f"https://{STAGING_PROJECT_REF}.supabase.co"
ADMIN_USERNAME = "sho"
ADMIN_ROLE = "Enterprise Admin"
ADMIN_TIER = "Enterprise Plus Tier ($399)"
ADMIN_EXPIRY = "2099-01-01T00:00:00Z"
PBKDF2_ITERATIONS = 200_000
REQUEST_TIMEOUT_SECONDS = 20


def hash_password(password: str, salt_hex: str | None = None) -> str:
    """Return the same salt$PBKDF2-SHA256 hash format used by shoir-persistence."""
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = salt_hex or secrets.token_bytes(16).hex()
    try:
        salt_bytes = bytes.fromhex(salt)
    except ValueError as exc:
        raise ValueError("Salt must be hexadecimal.") from exc
    if len(salt_bytes) != 16:
        raise ValueError("Salt must be exactly 16 bytes.")
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        PBKDF2_ITERATIONS,
        dklen=32,
    ).hex()
    return f"{salt}\${digest}"


def verify_password(stored_hash: str, password: str) -> bool:
    """Verify a stored hash with constant-time digest comparison."""
    try:
        salt, expected = stored_hash.split("$", 1)
        salt_bytes = bytes.fromhex(salt)
        expected_bytes = bytes.fromhex(expected)
        if len(salt_bytes) != 16 or len(expected_bytes) != 32:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt_bytes,
            PBKDF2_ITERATIONS,
            dklen=32,
        )
        return hmac.compare_digest(actual, expected_bytes)
    except (ValueError, TypeError):
        return False


def is_service_role_key(key: str) -> bool:
    """Accept a current Supabase secret key or a legacy service_role JWT only."""
    key = key.strip()
    if not key or key.startswith("sb_publishable_"):
        return False
    if key.startswith("sb_secret_"):
        return True
    parts = key.split(".")
    if len(parts) != 3:
        return False
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(decoded, dict) and decoded.get("role") == "service_role"


def _request_json(
    key: str,
    method: str,
    path: str,
    payload: dict | None = None,
) -> tuple[int, object]:
    url = f"{PROJECT_URL}/rest/v1/{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if method == "POST":
        headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
            if not body:
                return response.status, None
            try:
                return response.status, json.loads(body.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                raise RuntimeError("Staging API returned an unexpected response format.")
    except HTTPError as exc:
        # Do not print response bodies, headers, or credential-bearing requests.
        raise RuntimeError(f"Staging API request failed with HTTP {exc.code}.") from None
    except URLError:
        raise RuntimeError("Could not reach the fixed staging Supabase endpoint.") from None


def _existing_admin(key: str) -> list[dict]:
    query = urlencode(
        {"select": "username_lc,role,tier,active", "username_lc": "eq.sho"}
    )
    status, result = _request_json(key, "GET", f"shoir_accounts?{query}")
    if status != 200 or not isinstance(result, list):
        raise RuntimeError("Could not verify the staging administrator record.")
    return [row for row in result if isinstance(row, dict)]


def bootstrap() -> int:
    if STAGING_PROJECT_REF == PRODUCTION_PROJECT_REF:
        raise RuntimeError("The staging and production project references must be different.")

    print("SHOIR-IE staging administrator bootstrap")
    print(f"Fixed target: {PROJECT_URL}")
    print("This utility cannot target production and will not overwrite an existing administrator.")
    print("Use a one-time staging service key from Supabase Dashboard → Project Settings → API.")
    service_key = getpass.getpass("Staging service key (input hidden): ").strip()
    if not is_service_role_key(service_key):
        raise ValueError("The key was not recognized as a Supabase server secret/service_role key.")

    existing = _existing_admin(service_key)
    if existing:
        raise RuntimeError(
            "The staging 'sho' identity already exists. No record was changed; use the approved admin-recovery process."
        )

    password = getpass.getpass("New staging admin password (input hidden; 16+ characters): ")
    confirmation = getpass.getpass("Re-enter staging admin password (input hidden): ")
    if password != confirmation:
        raise ValueError("Password confirmation did not match.")
    if len(password) < 16:
        raise ValueError("Use a unique staging password with at least 16 characters.")
    if password.casefold() == ADMIN_USERNAME:
        raise ValueError("The password is too weak.")
    typed_confirmation = input(
        f"To confirm staging-only creation, type BOOTSTRAP SHOIR STAGING ADMIN {STAGING_PROJECT_REF}: "
    ).strip()
    expected_confirmation = f"BOOTSTRAP SHOIR STAGING ADMIN {STAGING_PROJECT_REF}"
    if typed_confirmation != expected_confirmation:
        raise ValueError("Staging confirmation phrase did not match; no record was created.")

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "username": ADMIN_USERNAME,
        "username_lc": ADMIN_USERNAME,
        "password_hash": hash_password(password),
        "role": ADMIN_ROLE,
        "tier": ADMIN_TIER,
        "subscription_expires_at": ADMIN_EXPIRY,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    # The insert ignores a duplicate instead of updating it, protecting against
    # a concurrent provisioning operation.
    status, _ = _request_json(
        service_key, "POST", "shoir_accounts?on_conflict=username_lc", row
    )
    if status not in (200, 201, 204):
        raise RuntimeError(f"Staging administrator insert returned unexpected HTTP status {status}.")

    verified = _existing_admin(service_key)
    if len(verified) != 1:
        raise RuntimeError("The staging administrator insert could not be verified.")
    admin = verified[0]
    if (
        admin.get("username_lc") != ADMIN_USERNAME
        or admin.get("role") != ADMIN_ROLE
        or admin.get("tier") != ADMIN_TIER
        or admin.get("active") is not True
    ):
        raise RuntimeError("Staging admin verification did not match expected state; do not retry blindly.")

    print("PASS: a new Enterprise Plus staging administrator was created and verified.")
    print("The password and server key were not displayed or saved by this script.")
    print("Store the staging admin password in your password manager, then use it only for staging.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(bootstrap())
    except (ValueError, RuntimeError) as exc:
        print(f"BOOTSTRAP BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
