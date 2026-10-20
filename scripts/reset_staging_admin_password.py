#!/usr/bin/env python3
"""Reset the existing Shoir-IE administrator password in the fixed staging project.

This script never creates an account and cannot target production. It requires a
staging server key and a generated password supplied through environment
variables by a trusted local wrapper. It never prints keys, hashes, or passwords.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

STAGING_PROJECT_REF = "hfhrosthswcybccepmak"
PRODUCTION_PROJECT_REF = "gcsamrdaeraxieaagsta"
PROJECT_URL = f"https://{STAGING_PROJECT_REF}.supabase.co"
ADMIN_USERNAME = "sho"
ADMIN_ROLE = "Enterprise Admin"
PBKDF2_ITERATIONS = 200_000
REQUEST_TIMEOUT_SECONDS = 20


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_service_role_key(key: str) -> bool:
    key = key.strip()
    if key.startswith("sb_secret_"):
        return len(key) > len("sb_secret_")
    if key.startswith("sb_publishable_"):
        return False
    parts = key.split(".")
    if len(parts) != 3:
        return False
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(decoded, dict) and decoded.get("role") == "service_role"


def _request_json(key: str, method: str, query: str, payload: dict | None = None):
    url = f"{PROJECT_URL}/rest/v1/shoir_accounts?{query}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    if method == "PATCH":
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
                raise RuntimeError("Staging API returned an unexpected response format.") from None
    except HTTPError as exc:
        raise RuntimeError(f"Staging API request failed with HTTP {exc.code}. No credentials were printed.") from None
    except URLError:
        raise RuntimeError("Could not reach the fixed staging Supabase endpoint.") from None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    salt_hex = salt.hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    ).hex()
    return salt_hex + "$" + digest


def run() -> int:
    if STAGING_PROJECT_REF == PRODUCTION_PROJECT_REF:
        raise RuntimeError("Production/staging safety check failed.")

    key = os.environ.pop("SHOIR_STAGING_SERVICE_KEY", "").strip()
    password = os.environ.pop("SHOIR_STAGING_GENERATED_ADMIN_PASSWORD", "")
    if not is_service_role_key(key):
        raise ValueError("Missing or invalid staging server secret key.")
    if len(password) < 24:
        raise ValueError("Generated staging password is missing or too short.")

    print("SHOIR-IE staging administrator password reset")
    print(f"Fixed target: {PROJECT_URL}")
    print("Only the existing 'sho' admin password will be changed; the account will not be created.")

    select_before = urlencode({
        "select": "username_lc,role,tier,active",
        "username_lc": "eq.sho",
    })
    status, rows = _request_json(key, "GET", select_before)
    if status != 200 or not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError("Could not verify one existing staging administrator. No password was changed.")
    admin = rows[0]
    if (
        admin.get("username_lc") != ADMIN_USERNAME
        or admin.get("role") != ADMIN_ROLE
        or admin.get("active") is not True
    ):
        raise RuntimeError("The existing staging admin identity is not in the expected active state. No password was changed.")

    new_hash = hash_password(password)
    patch_query = urlencode({
        "username_lc": "eq.sho",
        "role": f"eq.{ADMIN_ROLE}",
        "active": "eq.true",
        "select": "username_lc,role,tier,active,password_hash",
    })
    status, updated = _request_json(
        key,
        "PATCH",
        patch_query,
        {"password_hash": new_hash, "updated_at": datetime.now(timezone.utc).isoformat()},
    )
    if status not in (200, 204) or not isinstance(updated, list) or len(updated) != 1:
        raise RuntimeError("Staging password reset could not be confirmed. Do not retry blindly.")

    row = updated[0]
    if (
        row.get("username_lc") != ADMIN_USERNAME
        or row.get("role") != ADMIN_ROLE
        or row.get("active") is not True
        or not isinstance(row.get("password_hash"), str)
        or not hmac.compare_digest(row["password_hash"], new_hash)
    ):
        raise RuntimeError("Staging password reset verification failed. Do not retry blindly.")

    print("PASS: existing staging administrator password reset and verified.")
    print("Username: sho")
    print("The new password was not printed or saved by this script.")
    print("Save it from your local clipboard into your password manager now.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"STAGING ADMIN PASSWORD RESET BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
