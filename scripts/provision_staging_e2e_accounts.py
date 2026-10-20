#!/usr/bin/env python3
"""Provision disposable Shoir-IE E2E identities in the approved staging project.

Normal accounts are created by register_request and approved through the admin
approval action. The only direct data mutation is setting the new disposable
expired-fixture's subscription timestamp into the past. Target URL/project are
hard-pinned; the script never reads or accepts a production URL.
"""
from __future__ import annotations

import getpass
import json
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

STAGING_PROJECT_REF = "hfhrosthswcybccepmak"
PRODUCTION_PROJECT_REF = "gcsamrdaeraxieaagsta"
PROJECT_URL = f"https://{STAGING_PROJECT_REF}.supabase.co"
EDGE_URL = f"{PROJECT_URL}/functions/v1/shoir-persistence"
OUTPUT_PATH = Path(".staging-e2e-credentials.json")
REQUEST_TIMEOUT_SECONDS = 25
EXPIRED_AT = "2000-01-01T00:00:00Z"
ACTIVE_TIER = "Enterprise Plus Tier ($399)"
STARTER_TIER = "Starter Tier ($29)"
RESEARCH_TIER = "Research Pack ($30 add-on)"
PAYMENT_METHOD = "STC Pay (QR)"


def get_hidden_key(prompt: str) -> str:
    """Read a key via hidden input; type @clipboard to retrieve Windows clipboard text."""
    value = getpass.getpass(prompt).strip()
    if value.casefold() != "@clipboard":
        return value
    if sys.platform != "win32":
        raise RuntimeError("@clipboard is supported only on Windows PowerShell.")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("Could not read the Windows clipboard. Copy the key again and retry.") from None
    key = result.stdout.strip()
    if not key:
        raise RuntimeError("The Windows clipboard was empty. Copy the key again and retry.")
    print("Read key from clipboard; the key value was not displayed.")
    return key


class _NoRedirect(HTTPRedirectHandler):
    """Never forward a server key or session token through HTTP redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_publishable_key(key: str) -> bool:
    key = key.strip()
    if key.startswith("sb_publishable_"):
        return len(key) > len("sb_publishable_")
    parts = key.split(".")
    if len(parts) != 3:
        return False
    try:
        import base64
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return False
    return isinstance(claims, dict) and claims.get("role") == "anon"


def is_service_role_key(key: str) -> bool:
    key = key.strip()
    if key.startswith("sb_secret_"):
        return len(key) > len("sb_secret_")
    parts = key.split(".")
    if len(parts) != 3:
        return False
    try:
        import base64
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return False
    return isinstance(claims, dict) and claims.get("role") == "service_role"


def _read_response(req: Request) -> tuple[int, object]:
    try:
        response = build_opener(_NoRedirect()).open(req, timeout=REQUEST_TIMEOUT_SECONDS)
    except HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except URLError:
        raise RuntimeError("Could not reach the fixed staging Supabase endpoint.") from None
    else:
        status = response.status
        raw = response.read()
        response.close()
    if not raw:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        # Never display an HTML error body which might contain infrastructure detail.
        return status, None


def edge_call(publishable_key: str, action: str, payload: dict) -> tuple[int, dict]:
    body = dict(payload)
    body["action"] = action
    req = Request(
        EDGE_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "apikey": publishable_key,
            **({} if publishable_key.startswith("sb_publishable_") else {"Authorization": f"Bearer {publishable_key}"}),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    status, data = _read_response(req)
    return status, data if isinstance(data, dict) else {}


def rest_call(service_key: str, method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    if path.startswith("/") or "://" in path or ".." in path:
        raise RuntimeError("Refused an invalid staging REST path.")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": service_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # New Supabase secret keys are accepted through apikey only; legacy
    # service_role JWTs continue to use the Authorization header.
    if not service_key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {service_key}"
    if method in {"POST", "PATCH"}:
        headers["Prefer"] = "return=representation"
    req = Request(f"{PROJECT_URL}/rest/v1/{path}", data=data, headers=headers, method=method)
    return _read_response(req)


def _write_private_json(path: Path, payload: dict, *, exclusive: bool = False) -> None:
    """Atomically save credentials with owner-only permissions."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL if exclusive else os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    temp_name = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _expected_accounts() -> list[dict[str, str]]:
    specs = [
        ("active", "shoir-e2e-active", ACTIVE_TIER),
        ("second", "shoir-e2e-second", ACTIVE_TIER),
        ("starter", "shoir-e2e-starter", STARTER_TIER),
        ("expired", "shoir-e2e-expired", STARTER_TIER),
        ("module", "shoir-e2e-module", ACTIVE_TIER),
        ("research_module", "shoir-e2e-research", RESEARCH_TIER),
    ]
    result = []
    for key, username, tier in specs:
        result.append({
            "secret_prefix": key,
            "username": username,
            "password": secrets.token_urlsafe(24),
            "email": f"{username}@example.invalid",
            "tier": tier,
            "status": "NOT_STARTED",
        })
    return result


def _assert_none_exist(service_key: str, accounts: list[dict[str, str]]) -> None:
    names = [account["username"] for account in accounts]
    expr = "in.(" + ",".join(names) + ")"
    conflicts: set[str] = set()
    # Check all durable lifecycle tables, not only approved accounts. This
    # catches a stale pending request/credential left by an interrupted attempt
    # and prevents accidental reuse or duplicate submissions.
    for table in ("shoir_accounts", "shoir_pending_credentials", "shoir_subscription_requests"):
        query = urlencode({"select": "username_lc", "username_lc": expr})
        status, data = rest_call(service_key, "GET", f"{table}?{query}")
        if status != 200 or not isinstance(data, list):
            raise RuntimeError("Could not verify whether the planned staging test identities already exist.")
        conflicts.update(
            str(row.get("username_lc") or "").casefold()
            for row in data
            if isinstance(row, dict)
        )
    if conflicts:
        raise RuntimeError(
            "At least one planned E2E identity or pending request already exists. No registration was attempted; inspect the staging lifecycle state and do not retry blindly."
        )


def _set_status(document: dict, account: dict, status: str) -> None:
    for row in document["accounts"]:
        if row["username"] == account["username"]:
            row["status"] = status
            break
    _write_private_json(OUTPUT_PATH, document)


def provision() -> int:
    if STAGING_PROJECT_REF == PRODUCTION_PROJECT_REF:
        raise RuntimeError("Staging and production project references must differ.")

    resume_existing = OUTPUT_PATH.exists()
    existing_document: dict | None = None
    if resume_existing:
        # Resume only the known safe first-registration failure. Reuse the
        # credential file's original identities/passwords; never generate new
        # credentials on top of an interrupted run.
        try:
            with OUTPUT_PATH.open("r", encoding="utf-8") as stream:
                candidate = json.load(stream)
        except (OSError, json.JSONDecodeError):
            raise RuntimeError("The existing credential file cannot be read safely; do not delete or overwrite it.") from None
        if not isinstance(candidate, dict) or candidate.get("schema_version") != 1:
            raise RuntimeError("The existing credential file has an unsupported schema; no action taken.")
        if candidate.get("target_project_ref") != STAGING_PROJECT_REF:
            raise RuntimeError("The existing credential file is not pinned to this staging project; no action taken.")
        if candidate.get("overall") == "PASS" or candidate.get("finished_at_utc"):
            raise RuntimeError("The existing credential file records a completed run; do not provision duplicates.")
        candidate_accounts = candidate.get("accounts")
        expected_names = {
            "shoir-e2e-active", "shoir-e2e-second", "shoir-e2e-starter",
            "shoir-e2e-expired", "shoir-e2e-module", "shoir-e2e-research",
        }
        if not isinstance(candidate_accounts, list) or {
            str(a.get("username", "")).casefold() for a in candidate_accounts
            if isinstance(a, dict)
        } != expected_names:
            raise RuntimeError("The existing credential file does not contain exactly the six expected staging identities.")
        safe_resume_statuses = {"NOT_STARTED", "REGISTRATION_FAILED"}
        for account in candidate_accounts:
            if not isinstance(account, dict) or account.get("status") not in safe_resume_statuses or "request_id" in account:
                raise RuntimeError("The existing run may have made partial account changes. Automatic resume is blocked to prevent duplicates.")
            if not account.get("password") or not account.get("email"):
                raise RuntimeError("The existing credential file is incomplete; automatic resume is blocked.")
        existing_document = candidate

    print("Shoir-IE disposable staging E2E-account provisioner")
    if resume_existing:
        print("Recovery mode: reusing the existing private credentials file after a failed first registration.")
    else:
        print("Fresh provisioning mode: a new private credentials file will be created.")
    print(f"Fixed target: {PROJECT_URL}")
    print("Creates synthetic registration records only; it does not charge or contact a payment provider.")
    # Prefer credentials passed by the trusted local PowerShell wrapper so the
    # operator does not need to paste long values into hidden prompts.
    # Interactive fallbacks remain available for manual/local use.
    publishable_key = os.environ.pop("SHOIR_STAGING_PUBLISHABLE_KEY", "").strip()
    if not publishable_key:
        publishable_key = get_hidden_key("Staging publishable key (input hidden; type @clipboard to read clipboard): ").strip()
    if not is_publishable_key(publishable_key):
        raise ValueError("The first key was not recognized as a publishable/anon client key.")

    service_key = os.environ.pop("SHOIR_STAGING_SERVICE_KEY", "").strip()
    if not service_key:
        service_key = get_hidden_key("Staging service key (input hidden; type @clipboard to read clipboard): ").strip()
    if not is_service_role_key(service_key):
        raise ValueError("The second key was not recognized as a Supabase server secret/service_role key.")
    if secrets.compare_digest(publishable_key, service_key):
        raise ValueError("The publishable key and service key must be different.")

    admin_password = os.environ.pop("SHOIR_STAGING_ADMIN_PASSWORD", "")
    if not admin_password:
        admin_password = getpass.getpass("Staging administrator password for 'sho' (input hidden): ")
    if not admin_password:
        raise ValueError("Administrator password cannot be empty.")

    accounts = existing_document["accounts"] if existing_document is not None else _expected_accounts()
    print("This will create six disposable staging identities through registration and admin approval.")
    print("It refuses to reuse matching identities. The expired account is a synthetic test fixture.")
    confirmation_phrase = (
        f"RESUME SHOIR STAGING E2E ACCOUNTS {STAGING_PROJECT_REF}"
        if resume_existing
        else f"PROVISION SHOIR STAGING E2E ACCOUNTS {STAGING_PROJECT_REF}"
    )
    confirmation = input(f"Type {confirmation_phrase} to proceed: ").strip()
    if confirmation != confirmation_phrase:
        raise ValueError("Confirmation phrase did not match. No account was created.")

    _assert_none_exist(service_key, accounts)
    status, admin = edge_call(
        publishable_key,
        "login",
        {"username": "sho", "password": admin_password},
    )
    admin_token = str(admin.get("token") or "")
    if status != 200 or not admin_token or str(admin.get("role") or "") != "Enterprise Admin":
        raise RuntimeError("Staging administrator login failed or did not return an admin session.")

    if existing_document is not None:
        document = existing_document
        document["accounts"] = accounts
        document["last_resume_attempt_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_private_json(OUTPUT_PATH, document)
    else:
        document = {
            "schema_version": 1,
            "target_project_ref": STAGING_PROJECT_REF,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "notice": "Disposable staging credentials. Keep private. Do not commit. Never use with production.",
            "accounts": accounts,
            "github_actions_secret_map": {
                "active": ["SHOIR_E2E_ACTIVE_USERNAME", "SHOIR_E2E_ACTIVE_PASSWORD"],
                "second": ["SHOIR_E2E_SECOND_USERNAME", "SHOIR_E2E_SECOND_PASSWORD"],
                "starter": ["SHOIR_E2E_STARTER_USERNAME", "SHOIR_E2E_STARTER_PASSWORD"],
                "expired": ["SHOIR_E2E_EXPIRED_USERNAME", "SHOIR_E2E_EXPIRED_PASSWORD"],
                "module": ["SHOIR_E2E_MODULE_USERNAME", "SHOIR_E2E_MODULE_PASSWORD"],
                "research_module": ["SHOIR_E2E_RESEARCH_MODULE_USERNAME", "SHOIR_E2E_RESEARCH_MODULE_PASSWORD"],
            },
            "results": [],
        }
        _write_private_json(OUTPUT_PATH, document, exclusive=True)
    regular_tokens: list[tuple[str, str]] = []

    try:
        for account in accounts:
            register_payload = {
                "username": account["username"],
                "password": account["password"],
                "email": account["email"],
                "tier": account["tier"],
                "payment_method": PAYMENT_METHOD,
                "transaction_id": "SHOIR-E2E-NO-CHARGE-" + secrets.token_hex(12),
            }
            reg_status, reg = edge_call(publishable_key, "register_request", register_payload)
            if reg_status not in (200, 201) or not reg.get("ok") or not reg.get("request_id"):
                _set_status(document, account, "REGISTRATION_FAILED")
                raise RuntimeError(
                    f"Staging registration request failed for {account['secret_prefix']} (HTTP {reg_status}); inspect the staging admin queue before retrying."
                )
            account["request_id"] = int(reg["request_id"])
            _set_status(document, account, "REQUEST_CREATED")
            approve_status, approved = edge_call(
                publishable_key,
                "admin_approve_target_session",
                {
                    "username": "sho",
                    "token": admin_token,
                    "target_username": account["username"],
                    "request_type": "New",
                },
            )
            if approve_status != 200 or approved.get("ok") is not True:
                _set_status(document, account, "APPROVAL_FAILED")
                raise RuntimeError(
                    f"Staging approval failed for {account['secret_prefix']} (HTTP {approve_status}); do not create a duplicate. Inspect the staging request queue."
                )
            _set_status(document, account, "APPROVED")

        expired = next(account for account in accounts if account["secret_prefix"] == "expired")
        username_filter = quote(expired["username"], safe="")
        path = f"shoir_accounts?username_lc=eq.{username_filter}"
        patch_status, patched = rest_call(
            service_key,
            "PATCH",
            path,
            {"subscription_expires_at": EXPIRED_AT},
        )
        if patch_status not in (200, 204) or not isinstance(patched, list) or len(patched) != 1:
            _set_status(document, expired, "EXPIRED_FIXTURE_FAILED")
            raise RuntimeError("Could not set the expired staging fixture; inspect staging before retrying.")
        expired["status"] = "EXPIRED_FIXTURE_SET"
        _write_private_json(OUTPUT_PATH, document)

        # Validate the login/tier contract for the five active accounts and the
        # renewal-only contract for the intentionally expired account.
        for account in accounts:
            login_status, auth = edge_call(
                publishable_key,
                "login",
                {"username": account["username"], "password": account["password"]},
            )
            if account["secret_prefix"] == "expired":
                valid = (
                    login_status == 403
                    and auth.get("error") == "SUBSCRIPTION_EXPIRED"
                    and bool(auth.get("token"))
                    and auth.get("renewal_only") is True
                )
                if not valid:
                    _set_status(document, account, "EXPIRED_LOGIN_VALIDATION_FAILED")
                    raise RuntimeError("Expired-account contract failed in staging; inspect the evidence and do not retry by creating a duplicate.")
                logout_status, _ = edge_call(
                    publishable_key,
                    "logout",
                    {"username": account["username"], "token": str(auth.get("token") or "")},
                )
                if logout_status not in (200, 204):
                    raise RuntimeError("Could not revoke the expired fixture session.")
                account["status"] = "VERIFIED_EXPIRED_RENEWAL_ONLY"
            else:
                token = str(auth.get("token") or "")
                expected_tier = account["tier"]
                valid = (
                    login_status == 200
                    and bool(token)
                    and str(auth.get("username") or "").casefold() == account["username"].casefold()
                    and str(auth.get("tier") or "").strip() == expected_tier
                    and str(auth.get("role") or "") != "Enterprise Admin"
                )
                if not valid:
                    _set_status(document, account, "LOGIN_VALIDATION_FAILED")
                    raise RuntimeError(f"Staging login/tier validation failed for {account['secret_prefix']}; inspect staging before retrying.")
                regular_tokens.append((account["username"], token))
                account["status"] = "VERIFIED_ACTIVE"
            _write_private_json(OUTPUT_PATH, document)

        # The user accounts remain for the authenticated gate, but the temporary
        # verification sessions are revoked now.
        for username, token in regular_tokens:
            status, result = edge_call(publishable_key, "logout", {"username": username, "token": token})
            if status != 200 or result.get("ok") is not True:
                raise RuntimeError("A staging verification session could not be revoked.")
        status, result = edge_call(publishable_key, "logout", {"username": "sho", "token": admin_token})
        if status != 200 or result.get("ok") is not True:
            raise RuntimeError("The staging administrator verification session could not be revoked.")

        document["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        document["overall"] = "PASS"
        _write_private_json(OUTPUT_PATH, document)
        try:
            OUTPUT_PATH.chmod(0o600)
        except OSError:
            pass
        print("PASS: six staging identities were created through registration/approval and their login/expiry contracts were verified.")
        print(f"Private credentials file written: {OUTPUT_PATH.resolve()}")
        print("No password, token, key, or response body was printed.")
        print("Copy username/password values into the mapped GitHub Actions secrets, then keep or securely delete the file.")
        return 0
    finally:
        # Best-effort revocation if the process stops part-way through verification.
        for username, token in regular_tokens:
            try:
                edge_call(publishable_key, "logout", {"username": username, "token": token})
            except Exception:
                pass
        if admin_token:
            try:
                edge_call(publishable_key, "logout", {"username": "sho", "token": admin_token})
            except Exception:
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(provision())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"STAGING PROVISIONING BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
