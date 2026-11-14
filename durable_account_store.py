"""Durable Shoir-IE account/subscription store for Streamlit Cloud.

The app's SQLite file is useful for local development but Streamlit Community
Cloud does not guarantee persistence of local files across restarts. This
module makes a managed PostgreSQL database the authoritative account store
when [database].url is configured in Streamlit secrets (or SHOIR_DATABASE_URL
is present in the environment). SQLite remains a local fallback.

Never put the database URL/password in Git.
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import sqlite3
from shoir_sqlite import ClosingSQLiteConnection
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # pragma: no cover
    psycopg2 = None
    RealDictCursor = None

# The production defaults preserve the existing public deployment. A staging
# deployment must set [shoir].environment = "staging" and supply the staging
# Edge URL + publishable key. In staging mode, there is deliberately no
# fallback to production if configuration is missing or incorrect.
PRODUCTION_SUPABASE_EDGE_URL = "https://gcsamrdaeraxieaagsta.supabase.co/functions/v1/shoir-persistence"
PRODUCTION_SUPABASE_PROJECT_HOST = "gcsamrdaeraxieaagsta.supabase.co"
PRODUCTION_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_ccMYEvPjf1AXbx_VhewNUQ_jWPnSwEc"
STAGING_SUPABASE_EDGE_URL = "https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence"
STAGING_SUPABASE_PROJECT_HOST = "hfhrosthswcybccepmak.supabase.co"
SUPABASE_EDGE_PATH = "/functions/v1/shoir-persistence"


def _streamlit_secret(section: str, key: str) -> str:
    if st is None:
        return ""
    try:
        value = st.secrets[section][key]
        return str(value).strip() if value is not None else ""
    except Exception:
        return ""


def _validate_supabase_edge_url(value: str, expected_host: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("The configured Supabase Edge URL is invalid.") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.hostname.casefold().rstrip(".") != expected_host
        or parsed.path.rstrip("/") != SUPABASE_EDGE_PATH
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or port not in (None, 443)
    ):
        raise RuntimeError(
            "The configured Supabase Edge URL does not match the declared deployment environment."
        )
    return value.strip().rstrip("/")


def _validate_supabase_publishable_key(value: str) -> str:
    key = value.strip()
    if key.startswith("sb_publishable_") and len(key) > len("sb_publishable_"):
        return key
    if key.startswith("sb_secret_"):
        raise RuntimeError("A Supabase secret/service-role key is forbidden in the Streamlit app.")
    parts = key.split(".")
    if len(parts) == 3:
        try:
            import base64
            import json

            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        except Exception:
            claims = {}
        if isinstance(claims, dict) and claims.get("role") == "anon":
            return key
    raise RuntimeError(
        "The Streamlit app requires a Supabase publishable key (or legacy anon key), never a service-role key."
    )


def _resolve_supabase_edge_config(
    environment: str,
    configured_url: str = "",
    configured_key: str = "",
) -> tuple[str, str]:
    mode = str(environment or "").strip().casefold()
    url = str(configured_url or "").strip()
    key = str(configured_key or "").strip()
    if mode not in {"production", "staging"}:
        raise RuntimeError("SHOIR_ENVIRONMENT must be either 'production' or 'staging'.")

    if mode == "staging":
        if not url or not key:
            raise RuntimeError(
                "Staging mode requires supabase.edge_url and supabase.publishable_key; production fallback is disabled."
            )
        return (
            _validate_supabase_edge_url(url, STAGING_SUPABASE_PROJECT_HOST),
            _validate_supabase_publishable_key(key),
        )

    # Production keeps its historical fallback for backward compatibility. If
    # an explicit override is supplied, require a complete production-matched pair.
    if bool(url) != bool(key):
        raise RuntimeError("Production Supabase overrides must include both Edge URL and publishable key.")
    if url and key:
        return (
            _validate_supabase_edge_url(url, PRODUCTION_SUPABASE_PROJECT_HOST),
            _validate_supabase_publishable_key(key),
        )
    return PRODUCTION_SUPABASE_EDGE_URL, PRODUCTION_SUPABASE_PUBLISHABLE_KEY


APP_ENVIRONMENT = (
    os.getenv("SHOIR_ENVIRONMENT", "").strip()
    or _streamlit_secret("shoir", "environment")
    or "production"
).casefold()
SUPABASE_EDGE_URL, SUPABASE_PUBLISHABLE_KEY = _resolve_supabase_edge_config(
    APP_ENVIRONMENT,
    os.getenv("SHOIR_SUPABASE_EDGE_URL", "").strip()
    or _streamlit_secret("supabase", "edge_url"),
    os.getenv("SHOIR_SUPABASE_PUBLISHABLE_KEY", "").strip()
    or _streamlit_secret("supabase", "publishable_key"),
)


def _configured_direct_database_url() -> str:
    for name in ("SHOIR_DATABASE_URL", "SUPABASE_DB_URL", "DATABASE_URL"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    for section in ("database", "postgresql", "supabase"):
        value = _streamlit_secret(section, "url")
        if value:
            return value
    return ""


if APP_ENVIRONMENT == "staging" and _configured_direct_database_url():
    raise RuntimeError(
        "Direct PostgreSQL URLs are forbidden in Shoir-IE staging mode. "
        "Remove database.url/postgresql.url/supabase.url and database DSN environment variables; use the pinned staging Edge Function."
    )


def _edge_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}",
        "Content-Type": "application/json",
    }


def _edge_call(action: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    import requests
    body = dict(payload or {})
    # Shared managed records/datasets use the selected organization workspace
    # only in an explicitly configured staging environment. The Edge Function
    # independently revalidates membership and role for every request.
    shared_actions = {
        "dataset_download_url",
        "dataset_upload_create",
        "dataset_version_finalize",
        "dataset_version_register",
        "platform_record_save",
        "platform_record_list",
    }
    if APP_ENVIRONMENT == "staging" and action in shared_actions:
        try:
            organization_id = str(
                st.session_state.get("shoir_active_organization_id") or ""
            ).strip()
            organization_workspace_id = str(
                st.session_state.get("shoir_active_organization_workspace_id") or ""
            ).strip()
        except Exception:
            organization_id = ""
            organization_workspace_id = ""
        if organization_id or organization_workspace_id:
            body["organization_id"] = organization_id
            body["organization_workspace_id"] = organization_workspace_id
    body["action"] = action
    resp = requests.post(
        SUPABASE_EDGE_URL,
        json=body,
        headers=_edge_headers(),
        timeout=15,
    )
    try:
        data = resp.json()
    except Exception:
        data = {"error": resp.text[:500]}
    # Expiry is an expected authentication state, not a transport failure.
    if data.get("error") == "SUBSCRIPTION_EXPIRED":
        return data
    if resp.status_code >= 400 or data.get("error"):
        raise RuntimeError(str(data.get("error") or f"Supabase persistence request failed ({resp.status_code})"))
    return data


def edge_backend_configured() -> bool:
    return bool(SUPABASE_EDGE_URL and SUPABASE_PUBLISHABLE_KEY)

_ORGANIZATION_EDGE_ACTIONS = {
    "org_list_session",
    "org_create_session",
    "org_workspace_list_session",
    "org_member_list_session",
    "org_invitation_create_session",
    "org_invitation_accept_session",
    "org_invitation_list_session",
    "org_invitation_revoke_session",
    "org_member_role_set_session",
    "org_member_remove_session",
    "org_member_suspend_session",
    "org_member_restore_session",
    "org_owner_transfer_session",
    "org_close_session",
    "org_workspace_create_session",
    "org_workspace_archive_session",
    "org_audit_list_session",
}


def edge_organization_action(
    action: str,
    username: str,
    token: str,
    **payload: Any,
) -> dict[str, Any]:
    """Call one allow-listed, session-authenticated organization operation."""
    if action not in _ORGANIZATION_EDGE_ACTIONS:
        raise ValueError("Organization operation is not supported.")
    if str(APP_ENVIRONMENT).casefold() != "staging":
        raise RuntimeError(
            "Organization workspace actions require explicit SHOIR_ENVIRONMENT=staging configuration."
        )
    if not edge_backend_configured():
        raise RuntimeError("The staging organization persistence endpoint is not configured.")
    actor = str(username or "").strip()
    bearer = str(token or "")
    if not actor or not bearer:
        raise PermissionError("An authenticated organization session is required.")
    return _edge_call(
        action,
        {"username": actor, "token": bearer, **payload},
    )



def database_url() -> str:
    """Read the managed database URL from secrets/environment."""
    if st is not None:
        for section in ("database", "postgresql", "supabase"):
            try:
                value = st.secrets[section]["url"]
                if value:
                    return str(value)
            except Exception:
                pass
    return str(
        os.getenv("SHOIR_DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()


def postgres_backend_configured() -> bool:
    """Return whether a direct PostgreSQL connection is actually configured."""
    return bool(database_url()) and psycopg2 is not None


def durable_backend_configured() -> bool:
    """Return whether any durable backend is configured (Edge or direct PostgreSQL)."""
    return edge_backend_configured() or postgres_backend_configured()

def ephemeral_local_storage_allowed() -> bool:
    """Explicit opt-in for SQLite-only local development.
    Production/deployed instances must use managed storage by default."""
    raw = os.getenv("SHOIR_ALLOW_EPHEMERAL_LOCAL_STORAGE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if st is not None:
        try:
            value = st.secrets.get("allow_ephemeral_local_storage", False)
            return str(value).strip().lower() in {"1", "true", "yes", "on"}
        except Exception:
            pass
    return False


def _pg_connect():
    # Supabase Edge persistence does not provide a PostgreSQL DSN to this process.
    # Never let psycopg2 fall back to the machine's local Unix socket.
    if not postgres_backend_configured():
        raise RuntimeError("Direct PostgreSQL backend is not configured.")
    return psycopg2.connect(
        database_url(),
        sslmode="require",
        connect_timeout=10,
        application_name="shoir-ie",
    )


def ensure_remote_schema() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS shoir_accounts (
        username TEXT PRIMARY KEY,
        username_lc TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT,
        tier TEXT,
        email TEXT,
        created_at TIMESTAMPTZ NOT NULL,
        subscription_expires_at TIMESTAMPTZ NOT NULL,
        linkedin TEXT,
        github TEXT,
        about_me TEXT,
        affiliate_code TEXT,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_shoir_accounts_expiry
        ON shoir_accounts(subscription_expires_at);
    CREATE INDEX IF NOT EXISTS idx_shoir_accounts_email
        ON shoir_accounts(email);

    CREATE TABLE IF NOT EXISTS shoir_subscription_requests (
        id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        username_lc TEXT NOT NULL,
        email TEXT,
        tier TEXT,
        request_type TEXT NOT NULL DEFAULT 'New',
        payment_method TEXT,
        transaction_id TEXT,
        screenshot_path TEXT,
        status TEXT NOT NULL DEFAULT 'Pending',
        requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        approved_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
        terms_version TEXT,
        privacy_policy_version TEXT,
        refund_policy_version TEXT,
        cookie_policy_version TEXT,
        accepted_at TIMESTAMPTZ
    );
    ALTER TABLE shoir_subscription_requests ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE shoir_subscription_requests ADD COLUMN IF NOT EXISTS terms_version TEXT;
    ALTER TABLE shoir_subscription_requests ADD COLUMN IF NOT EXISTS privacy_policy_version TEXT;
    ALTER TABLE shoir_subscription_requests ADD COLUMN IF NOT EXISTS refund_policy_version TEXT;
    ALTER TABLE shoir_subscription_requests ADD COLUMN IF NOT EXISTS cookie_policy_version TEXT;
    ALTER TABLE shoir_subscription_requests ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;
    CREATE TABLE IF NOT EXISTS shoir_referrals (
        id BIGSERIAL PRIMARY KEY,
        referrer_username_lc TEXT NOT NULL,
        referred_username_lc TEXT NOT NULL UNIQUE,
        referral_code TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending','Qualified','Declined')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        qualified_at TIMESTAMPTZ,
        CHECK (referrer_username_lc <> referred_username_lc)
    );
    CREATE INDEX IF NOT EXISTS idx_shoir_referrals_referrer_status ON shoir_referrals(referrer_username_lc, status);
    CREATE INDEX IF NOT EXISTS idx_shoir_requests_status
        ON shoir_subscription_requests(status, requested_at DESC);
    CREATE INDEX IF NOT EXISTS idx_shoir_requests_user
        ON shoir_subscription_requests(username_lc, requested_at DESC);
    """
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()




def ensure_remote_research_schema() -> None:
    """Create research tables only when direct PostgreSQL is configured."""
    if not postgres_backend_configured():
        return
    schema = """
    CREATE TABLE IF NOT EXISTS shoir_research_studies (
        study_id TEXT PRIMARY KEY,
        research_id TEXT UNIQUE NOT NULL,
        owner TEXT NOT NULL,
        owner_lc TEXT NOT NULL,
        title TEXT NOT NULL,
        protocol_json TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_shoir_research_owner
        ON shoir_research_studies(owner_lc, updated_at DESC);
    CREATE TABLE IF NOT EXISTS shoir_research_runs (
        run_id TEXT PRIMARY KEY,
        study_id TEXT NOT NULL,
        research_id TEXT NOT NULL,
        owner TEXT NOT NULL,
        owner_lc TEXT NOT NULL,
        experiment_code TEXT NOT NULL,
        config_json TEXT NOT NULL,
        summary_json TEXT NOT NULL,
        results_csv TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_shoir_research_runs_study
        ON shoir_research_runs(owner_lc, study_id, created_at DESC);
    """
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()


def upsert_remote_research_study(study: Mapping[str, Any]) -> None:
    """Persist a research protocol when direct PostgreSQL is configured."""
    if not postgres_backend_configured():
        return
    ensure_remote_research_schema()
    import json
    now = dt.datetime.now(dt.timezone.utc)
    created = study.get("created_at") or now
    updated = study.get("updated_at") or now
    protocol = study.get("protocol") or {}
    owner = str(study.get("owner") or "").strip()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shoir_research_studies
                    (study_id,research_id,owner,owner_lc,title,protocol_json,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (study_id) DO UPDATE SET
                    research_id=EXCLUDED.research_id,
                    title=EXCLUDED.title,
                    protocol_json=EXCLUDED.protocol_json,
                    updated_at=EXCLUDED.updated_at
                WHERE shoir_research_studies.owner_lc = EXCLUDED.owner_lc
                """,
                (
                    str(study["study_id"]),
                    str(study["research_id"]),
                    owner,
                    owner.lower(),
                    str(study.get("title") or protocol.get("title") or "Research Study"),
                    json.dumps(dict(protocol), ensure_ascii=False, sort_keys=True, default=str),
                    created,
                    updated,
                ),
            )
            if cur.rowcount == 0:
                raise PermissionError("Research study not found or not owned by this user.")
        conn.commit()


def remote_research_study(study_id: str, owner: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Load one durable research protocol, optionally owner-scoped."""
    if not postgres_backend_configured():
        return None
    ensure_remote_research_schema()
    import json
    with _pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if owner:
                cur.execute(
                    "SELECT * FROM shoir_research_studies WHERE study_id=%s AND owner_lc=%s LIMIT 1",
                    (str(study_id), str(owner).strip().lower()),
                )
            else:
                cur.execute(
                    "SELECT * FROM shoir_research_studies WHERE study_id=%s LIMIT 1",
                    (str(study_id),),
                )
            row = cur.fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["protocol"] = json.loads(data.get("protocol_json") or "{}")
    except Exception:
        data["protocol"] = {}
    return data



def upsert_remote_research_run(run: Mapping[str, Any]) -> None:
    """Persist a completed research run and its CSV evidence."""
    if not postgres_backend_configured():
        return
    ensure_remote_research_schema()
    import json
    created = run.get("created_at") or dt.datetime.now(dt.timezone.utc)
    owner = str(run.get("owner") or "").strip()
    config = run.get("config") or {}
    summary = run.get("summary") or {}
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shoir_research_runs
                    (run_id,study_id,research_id,owner,owner_lc,experiment_code,
                     config_json,summary_json,results_csv,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (run_id) DO UPDATE SET
                    study_id=EXCLUDED.study_id,
                    research_id=EXCLUDED.research_id,
                    owner=EXCLUDED.owner,
                    owner_lc=EXCLUDED.owner_lc,
                    experiment_code=EXCLUDED.experiment_code,
                    config_json=EXCLUDED.config_json,
                    summary_json=EXCLUDED.summary_json,
                    results_csv=EXCLUDED.results_csv
                """,
                (
                    str(run["run_id"]),
                    str(run["study_id"]),
                    str(run["research_id"]),
                    owner,
                    owner.lower(),
                    str(run["experiment_code"]),
                    json.dumps(dict(config), ensure_ascii=False, sort_keys=True, default=str),
                    json.dumps(dict(summary), ensure_ascii=False, sort_keys=True, default=str),
                    str(run.get("results_csv") or ""),
                    created,
                ),
            )
        conn.commit()


def remote_research_runs(owner: str, study_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Return durable research runs for one owner, optionally one study."""
    if not postgres_backend_configured():
        return []
    ensure_remote_research_schema()
    import json
    with _pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if study_id:
                cur.execute(
                    """
                    SELECT * FROM shoir_research_runs
                    WHERE owner_lc=%s AND study_id=%s
                    ORDER BY created_at DESC
                    """,
                    (str(owner).strip().lower(), str(study_id)),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM shoir_research_runs
                    WHERE owner_lc=%s
                    ORDER BY created_at DESC
                    """,
                    (str(owner).strip().lower(),),
                )
            rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        for key in ("config_json","summary_json"):
            try: row[key[:-5]] = json.loads(row.get(key) or "{}")
            except Exception: row[key[:-5]] = {}
    return rows


def remote_research_studies(owner: str) -> list[dict[str, Any]]:
    """List all durable research protocols for one workspace owner."""
    if not postgres_backend_configured():
        return []
    ensure_remote_research_schema()
    import json
    with _pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM shoir_research_studies WHERE owner_lc=%s ORDER BY updated_at DESC",
                (str(owner).strip().lower(),),
            )
            rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        try:
            row["protocol"] = json.loads(row.get("protocol_json") or "{}")
        except Exception:
            row["protocol"] = {}
    return rows

def edge_login(username: str, password: str) -> dict[str, Any]:
    return _edge_call("login", {"username": username, "password": password})


def edge_logout(username: str, token: str) -> dict[str, Any]:
    """Revoke only the current server session for this account."""
    return _edge_call("logout", {"username": username, "token": token})


def edge_session_entitlement(username: str, token: str) -> dict[str, Any]:
    """Revalidate this user's live workspace session and current subscription."""
    actor = str(username or "").strip()
    session_token = str(token or "").strip()
    if not actor or not session_token:
        raise PermissionError("An authenticated workspace session is required.")
    return _edge_call(
        "session_entitlement",
        {"username": actor, "token": session_token},
    )


def edge_register_request(request: Mapping[str, Any]) -> dict[str, Any]:
    proof_path = str(request.get("screenshot_path") or "").strip()
    proof_base64 = str(request.get("proof_base64") or "").strip() or None
    proof_content_type = str(request.get("proof_content_type") or "").strip().lower() or None
    allowed_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pdf": "application/pdf",
    }

    if proof_base64 or proof_content_type:
        if not proof_base64 or proof_content_type not in set(allowed_types.values()):
            raise ValueError("Payment proof data or content type is invalid.")
        try:
            proof_bytes = base64.b64decode(proof_base64, validate=True)
        except Exception as exc:
            raise ValueError("Payment proof data is not valid base64.") from exc
        if not proof_bytes:
            raise ValueError("The payment proof file is empty.")
        if len(proof_bytes) > 512 * 1024:
            raise ValueError("Payment proofs must be 512 KiB or smaller.")
        proof_base64 = base64.b64encode(proof_bytes).decode("ascii")
    elif proof_path:
        extension = os.path.splitext(proof_path)[1].lower()
        proof_content_type = allowed_types.get(extension)
        if not proof_content_type:
            raise ValueError("Payment proofs must be PNG, JPG, JPEG or PDF files.")
        with open(proof_path, "rb") as proof_file:
            proof_bytes = proof_file.read(512 * 1024 + 1)
        if not proof_bytes:
            raise ValueError("The payment proof file is empty.")
        if len(proof_bytes) > 512 * 1024:
            raise ValueError("Payment proofs must be 512 KiB or smaller.")
        proof_base64 = base64.b64encode(proof_bytes).decode("ascii")
    else:
        # No upload is valid for registration; when either proof field is
        # supplied, both must be valid (the branch above enforces that).
        proof_base64 = None
        proof_content_type = None

    return _edge_call("register_request", {
        "username": request["username"],
        "password": request.get("password") or "",
        "email": request.get("email") or "",
        "tier": request.get("tier") or "Starter Tier ($29)",
        "payment_method": request.get("payment_method") or "",
        "transaction_id": request.get("transaction_id"),
        "proof_base64": proof_base64,
        "proof_content_type": proof_content_type,
        "referral_code": request.get("referral_code") or None,
        "terms_accepted": bool(request.get("terms_accepted", False)),
        "terms_version": request.get("terms_version"),
        "privacy_policy_version": request.get("privacy_policy_version"),
        "refund_policy_version": request.get("refund_policy_version"),
        "cookie_policy_version": request.get("cookie_policy_version"),
    })

def edge_admin_approve(username: str, token: str, request_id: int | None = None, target_username: str | None = None, request_type: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"username": username, "token": token}
    action = "admin_approve_latest_session"
    if request_id is not None:
        action = "admin_approve_session"
        payload["request_id"] = int(request_id)
    elif target_username:
        action = "admin_approve_target_session"
        payload["target_username"] = target_username
        payload["request_type"] = request_type or "New"
    return _edge_call(action, payload)


def edge_admin_decline(username: str, token: str, request_id: int) -> dict[str, Any]:
    return _edge_call("admin_decline_session", {
        "username": username, "token": token, "request_id": int(request_id)
    })


def edge_admin_list_requests(username: str, token: str) -> list[dict[str, Any]]:
    result = _edge_call("admin_list_requests_session", {"username": username, "token": token})
    return list(result.get("requests") or [])


def edge_referral_summary(username: str, token: str) -> dict[str, Any]:
    """Return the authenticated user's referral code and real attribution counts."""
    return _edge_call("referral_summary_session", {"username": username, "token": token})


def edge_renew_request(username: str, token: str, request: Mapping[str, Any]) -> dict[str, Any]:
    return _edge_call("renew_request", {
        "username": username,
        "token": token,
        "tier": request.get("tier"),
        "payment_method": request.get("payment_method") or "",
        "transaction_id": request.get("transaction_id"),
        "proof_base64": request.get("proof_base64"),
        "proof_content_type": request.get("proof_content_type"),
    })


def edge_admin_payment_proof_url(username: str, token: str, screenshot_path: str) -> dict[str, Any]:
    """Return a short-lived signed URL for a private payment proof (admin session required)."""
    return _edge_call("admin_payment_proof_url_session", {
        "username": username,
        "token": token,
        "screenshot_path": screenshot_path,
    })


def _iso(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def remote_account(username: str) -> Optional[dict[str, Any]]:
    if edge_backend_configured():
        result = _edge_call("account_exists", {"username": username})
        if result.get("exists"):
            return {"username": result.get("username") or username, "username_lc": str(username).strip().lower()}
        return None
    ensure_remote_schema()
    with _pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM shoir_accounts WHERE username_lc=%s LIMIT 1",
                (str(username).strip().lower(),),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def remote_accounts() -> list[dict[str, Any]]:
    if edge_backend_configured():
        raise RuntimeError("Bulk account listing is admin-only in Edge mode.")
    ensure_remote_schema()
    with _pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM shoir_accounts ORDER BY username_lc")
            return [dict(row) for row in cur.fetchall()]


def upsert_remote_account(account: Mapping[str, Any]) -> None:
    if edge_backend_configured():
        token = str(account.get("admin_session_token") or "")
        admin_username = str(account.get("admin_username") or "")
        request_id = account.get("request_id")
        target_username = account.get("target_username") or account.get("username")
        request_type = account.get("request_type") or "New"
        if not token or not admin_username:
            raise RuntimeError("Admin session token is required for remote account approval.")
        edge_admin_approve(
            admin_username,
            token,
            int(request_id) if request_id is not None else None,
            str(target_username) if target_username else None,
            str(request_type),
        )
        return
    ensure_remote_schema()
    now = dt.datetime.now(dt.timezone.utc)
    created = account.get("created_at") or now
    expires = account.get("subscription_expires_at")
    if not expires:
        expires = created + dt.timedelta(days=30)
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shoir_accounts
                (username,username_lc,password_hash,role,tier,email,created_at,
                 subscription_expires_at,linkedin,github,about_me,affiliate_code,active,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (username) DO UPDATE SET
                    username_lc=EXCLUDED.username_lc,
                    password_hash=EXCLUDED.password_hash,
                    role=EXCLUDED.role,
                    tier=EXCLUDED.tier,
                    email=EXCLUDED.email,
                    created_at=EXCLUDED.created_at,
                    subscription_expires_at=EXCLUDED.subscription_expires_at,
                    linkedin=EXCLUDED.linkedin,
                    github=EXCLUDED.github,
                    about_me=EXCLUDED.about_me,
                    affiliate_code=EXCLUDED.affiliate_code,
                    active=EXCLUDED.active,
                    updated_at=EXCLUDED.updated_at
                """,
                (
                    str(account["username"]),
                    str(account.get("username_lc") or account["username"]).strip().lower(),
                    str(account.get("password_hash") or account.get("password") or ""),
                    account.get("role"),
                    account.get("tier"),
                    account.get("email"),
                    created,
                    expires,
                    account.get("linkedin"),
                    account.get("github"),
                    account.get("about_me"),
                    account.get("affiliate_code"),
                    bool(account.get("active", True)),
                    now,
                ),
            )
        conn.commit()


def insert_remote_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Create a pending subscription request and report recorded consent/referral state."""
    if edge_backend_configured():
        return edge_register_request(request)
    ensure_remote_schema()
    referral_code = str(request.get("referral_code") or "").strip().upper()
    username = str(request["username"]).strip()
    username_lc = username.lower()
    terms_accepted = bool(request.get("terms_accepted", False))
    if not terms_accepted or not request.get("terms_version") or not request.get("accepted_at"):
        raise ValueError("Current beta terms must be accepted before registration.")
    referral_attributed = False
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            referrer_lc = None
            if referral_code:
                cur.execute(
                    "SELECT username_lc FROM shoir_accounts WHERE UPPER(COALESCE(affiliate_code,''))=%s AND active=TRUE LIMIT 2",
                    (referral_code,),
                )
                matches = cur.fetchall()
                if len(matches) != 1:
                    raise ValueError("Referral code was not found or is ambiguous.")
                referrer_lc = str(matches[0][0]).strip().lower()
                if referrer_lc == username_lc:
                    raise ValueError("Self-referrals are not allowed.")
                cur.execute(
                    "SELECT 1 FROM shoir_referrals WHERE referred_username_lc=%s LIMIT 1",
                    (username_lc,),
                )
                if cur.fetchone():
                    raise ValueError("This account already has referral attribution recorded.")

            cur.execute(
                """
                INSERT INTO shoir_subscription_requests
                (username,username_lc,email,tier,request_type,payment_method,
                 transaction_id,screenshot_path,status,requested_at,updated_at,
                 terms_accepted,terms_version,privacy_policy_version,
                 refund_policy_version,cookie_policy_version,accepted_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    username,
                    username_lc,
                    request.get("email"),
                    request.get("tier"),
                    request.get("request_type", "New"),
                    request.get("payment_method"),
                    request.get("transaction_id"),
                    request.get("screenshot_path"),
                    request.get("status", "Pending"),
                    request.get("requested_at") or dt.datetime.now(dt.timezone.utc),
                    dt.datetime.now(dt.timezone.utc),
                    terms_accepted,
                    request.get("terms_version"),
                    request.get("privacy_policy_version"),
                    request.get("refund_policy_version"),
                    request.get("cookie_policy_version"),
                    request.get("accepted_at") or dt.datetime.now(dt.timezone.utc),
                ),
            )
            request_id = cur.fetchone()[0]
            if referrer_lc:
                cur.execute(
                    """
                    INSERT INTO shoir_referrals
                        (referrer_username_lc,referred_username_lc,referral_code,status)
                    VALUES (%s,%s,%s,'Pending')
                    """,
                    (referrer_lc, username_lc, referral_code),
                )
                referral_attributed = True
        conn.commit()
    return {
        "ok": True,
        "request_id": request_id,
        "status": "Pending",
        "legal_acceptance_recorded": True,
        "referral_attributed": referral_attributed,
    }

def update_remote_request_status(request_id: int, status: str) -> None:
    if not postgres_backend_configured():
        return
    ensure_remote_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE shoir_subscription_requests
                SET status=%s, updated_at=NOW(), approved_at=CASE
                    WHEN %s='Approved' THEN NOW() ELSE approved_at END
                WHERE id=%s
                """,
                (status, status, int(request_id)),
            )
        conn.commit()

def update_latest_remote_request(username: str, request_type: str, status: str) -> None:
    """Update a direct-PostgreSQL pending request without requiring local ID."""
    if not postgres_backend_configured():
        return
    ensure_remote_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE shoir_subscription_requests
                SET status=%s, updated_at=NOW(), approved_at=CASE
                    WHEN %s='Approved' THEN NOW() ELSE approved_at END
                WHERE id = (
                    SELECT id FROM shoir_subscription_requests
                    WHERE username_lc=%s AND request_type=%s AND status='Pending'
                    ORDER BY requested_at DESC
                    LIMIT 1
                )
                """,
                (status, status, str(username).strip().lower(), str(request_type or "New")),
            )
        conn.commit()


def sync_remote_requests_to_local(db_path: str = "enterprise_full_workspace.db") -> int:
    """Hydrate pending requests locally when direct PostgreSQL mode is used.
    Edge mode retrieves requests only after an authenticated admin session."""
    if edge_backend_configured():
        return 0
    if not postgres_backend_configured():
        return 0
    ensure_remote_schema()
    with _pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT username,email,tier,request_type,payment_method,transaction_id,
                       screenshot_path,status,requested_at
                FROM shoir_subscription_requests
                WHERE status='Pending'
                ORDER BY requested_at ASC
                """
            )
            rows = [dict(row) for row in cur.fetchall()]
    inserted = 0
    with sqlite3.connect(db_path, factory=ClosingSQLiteConnection) as conn:
        for row in rows:
            exists = conn.execute(
                """
                SELECT 1 FROM pending_payments
                WHERE LOWER(username)=? AND COALESCE(transaction_id,'')=COALESCE(?, '')
                  AND COALESCE(request_type,'New')=?
                  AND status='Pending'
                LIMIT 1
                """,
                (
                    str(row["username"]).strip().lower(),
                    row.get("transaction_id"),
                    row.get("request_type") or "New",
                ),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO pending_payments
                (username,password,email,tier,payment_method,transaction_id,
                 screenshot_path,status,timestamp,request_type)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["username"], "", row.get("email") or "", row.get("tier") or "",
                    row.get("payment_method") or "", row.get("transaction_id"),
                    row.get("screenshot_path") or "", "Pending",
                    _iso(row.get("requested_at")) or dt.datetime.now(dt.timezone.utc).isoformat(),
                    row.get("request_type") or "New",
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def sync_remote_accounts_to_local(db_path: str = "enterprise_full_workspace.db") -> int:
    """Hydrate local SQLite from remote accounts in direct PostgreSQL mode."""
    if edge_backend_configured():
        return 0
    if not postgres_backend_configured():
        return 0
    ensure_remote_schema()
    rows = remote_accounts()
    if not rows:
        return 0
    with sqlite3.connect(db_path, factory=ClosingSQLiteConnection) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO users
                (username,password,role,tier,email,created_at,subscription_expires_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    row["username"], row["password_hash"], row.get("role"), row.get("tier"),
                    row.get("email"), _iso(row.get("created_at")),
                    _iso(row.get("subscription_expires_at")),
                ),
            )
            conn.execute(
                """
                UPDATE users
                SET password=?, role=?, tier=?, email=?, created_at=?, subscription_expires_at=?
                WHERE LOWER(username)=?
                """,
                (
                    row["password_hash"], row.get("role"), row.get("tier"), row.get("email"),
                    _iso(row.get("created_at")), _iso(row.get("subscription_expires_at")),
                    row["username"].strip().lower(),
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO enterprise_users (username) VALUES (?)",
                (row["username"],),
            )
            conn.execute(
                """
                UPDATE enterprise_users
                SET password_hash=?, role=?, tier=?, email=?, ticket_expiry=?,
                    linkedin=?, github=?, about_me=?, affiliate_code=?
                WHERE LOWER(username)=?
                """,
                (
                    row["password_hash"], row.get("role"), row.get("tier"), row.get("email"),
                    _iso(row.get("subscription_expires_at")), row.get("linkedin"),
                    row.get("github"), row.get("about_me"), row.get("affiliate_code"),
                    row["username"].strip().lower(),
                ),
            )
        conn.commit()
    return len(rows)


def migrate_local_accounts_to_remote(db_path: str = "enterprise_full_workspace.db") -> int:
    """Upload local accounts in direct PostgreSQL mode only."""
    if edge_backend_configured():
        return 0
    if not postgres_backend_configured():
        return 0
    ensure_remote_schema()
    existing = {row["username_lc"] for row in remote_accounts()}
    with sqlite3.connect(db_path, factory=ClosingSQLiteConnection) as conn:
        rows = conn.execute(
            """
            SELECT
                u.username,u.password,u.role,u.tier,u.email,u.created_at,
                u.subscription_expires_at,
                eu.linkedin,eu.github,eu.about_me,eu.affiliate_code
            FROM users u
            LEFT JOIN enterprise_users eu
              ON LOWER(eu.username)=LOWER(u.username)
            """
        ).fetchall()
    uploaded = 0
    for row in rows:
        username_lc = str(row[0]).strip().lower()
        if not username_lc or username_lc in existing:
            continue
        upsert_remote_account({
            "username": row[0],
            "username_lc": username_lc,
            "password_hash": row[1],
            "role": row[2],
            "tier": row[3],
            "email": row[4],
            "created_at": row[5],
            "subscription_expires_at": row[6],
            "linkedin": row[7],
            "github": row[8],
            "about_me": row[9],
            "affiliate_code": row[10],
        })
        uploaded += 1
    return uploaded


def sync_durable_accounts(db_path: str = "enterprise_full_workspace.db") -> bool:
    """Report durable backend readiness without touching ephemeral local SQLite."""
    if edge_backend_configured():
        return True
    if not durable_backend_configured():
        return False
    ensure_remote_schema()
    migrate_local_accounts_to_remote(db_path)
    sync_remote_accounts_to_local(db_path)
    return True



def _active_organization_workspace_context() -> Optional[dict[str, str]]:
    """Return the explicitly selected organization workspace, or None for personal state."""
    if st is None:
        return None
    raw = st.session_state.get("shoir_active_organization_workspace")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Active organization workspace context is invalid.")
    organization_id = str(raw.get("organization_id") or "").strip()
    workspace_id = str(raw.get("organization_workspace_id") or "").strip()
    if not organization_id or not workspace_id:
        raise ValueError("Both organization and workspace IDs are required for shared persistence.")
    return {
        "organization_id": organization_id,
        "organization_workspace_id": workspace_id,
    }




def validate_remote_organization_workspace_access(username: str) -> bool:
    """Revalidate the active shared workspace before each authenticated app rerun."""
    context = _active_organization_workspace_context()
    if context is None:
        return True
    if APP_ENVIRONMENT != "staging" or not edge_backend_configured() or st is None:
        raise RuntimeError("Shared workspace access cannot be validated outside the configured staging Edge Function.")
    token = str(st.session_state.get("remote_session_token") or "")
    actor = str(username or "").strip()
    if not actor or not token:
        raise PermissionError("An active Shoir-IE session is required for shared workspace access.")
    result = _edge_call(
        "workspace_access_check",
        {"username": actor, "token": token, **context},
    )
    if result.get("ok") is not True:
        raise PermissionError("Shared workspace access could not be verified.")
    return True



def save_remote_workspace(username: str, state_json: str) -> bool:
    """Persist serialized Streamlit workspace state in managed Supabase."""
    if edge_backend_configured():
        if st is None:
            return False
        token = str(st.session_state.get("remote_session_token") or "")
        if not token:
            return False
        organization_context = _active_organization_workspace_context()
        payload = {
            "username": username,
            "token": token,
            "state_json": state_json,
        }
        if organization_context is not None:
            if APP_ENVIRONMENT != "staging":
                raise RuntimeError("Shared organization persistence is restricted to the authorized staging environment.")
            revision = st.session_state.get("_workspace_org_revision", 0)
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                raise ValueError("Shared workspace revision state is invalid.")
            payload.update(organization_context)
            payload["expected_revision"] = revision
            result = _edge_call("workspace_save", payload)
            saved_revision = result.get("revision")
            if isinstance(saved_revision, bool) or not isinstance(saved_revision, int) or saved_revision < 1:
                raise RuntimeError("The shared workspace save did not return a valid revision.")
            st.session_state["_workspace_org_revision"] = saved_revision
            st.session_state["_workspace_org_updated_at"] = result.get("updated_at")
            return True
        _edge_call("workspace_save", payload)
        return True
    if st is not None and _active_organization_workspace_context() is not None:
        raise RuntimeError("Shared organization workspaces require the authenticated staging Edge Function.")
    if not durable_backend_configured():
        return False
    ensure_remote_schema()
    now = dt.datetime.now(dt.timezone.utc)
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS shoir_workspace_states (
                    username_lc TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                INSERT INTO shoir_workspace_states (username_lc,state_json,updated_at)
                VALUES (%s,%s,%s)
                ON CONFLICT (username_lc) DO UPDATE SET
                    state_json=EXCLUDED.state_json,
                    updated_at=EXCLUDED.updated_at
                """,
                (str(username).strip().lower(), state_json, now),
            )
        conn.commit()
    return True


def load_remote_workspace(username: str) -> Optional[str]:
    """Return a user's durable workspace JSON from Supabase."""
    if edge_backend_configured():
        if st is None:
            return None
        token = str(st.session_state.get("remote_session_token") or "")
        if not token:
            return None
        organization_context = _active_organization_workspace_context()
        payload = {"username": username, "token": token}
        if organization_context is not None:
            if APP_ENVIRONMENT != "staging":
                raise RuntimeError("Shared organization persistence is restricted to the authorized staging environment.")
            payload.update(organization_context)
            result = _edge_call("workspace_load", payload)
            revision = result.get("revision", 0)
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                raise RuntimeError("The shared workspace load returned an invalid revision.")
            st.session_state["_workspace_org_revision"] = revision
            st.session_state["_workspace_org_updated_at"] = result.get("updated_at")
            return result.get("state_json")
        result = _edge_call("workspace_load", payload)
        return result.get("state_json")
    if st is not None and _active_organization_workspace_context() is not None:
        raise RuntimeError("Shared organization workspaces require the authenticated staging Edge Function.")
    if not durable_backend_configured():
        return None
    ensure_remote_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS shoir_workspace_states (
                    username_lc TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "SELECT state_json FROM shoir_workspace_states WHERE username_lc=%s LIMIT 1",
                (str(username).strip().lower(),),
            )
            row = cur.fetchone()
    return row[0] if row else None


def account_is_expired(expires_at: Any, now: Optional[dt.datetime] = None) -> bool:
    if not expires_at:
        return False
    now = now or dt.datetime.now(dt.timezone.utc)
    if isinstance(expires_at, str):
        text = expires_at.replace("Z", "+00:00")
        try:
            expires_at = dt.datetime.fromisoformat(text)
        except ValueError:
            return False
    if isinstance(expires_at, dt.date) and not isinstance(expires_at, dt.datetime):
        expires_at = dt.datetime.combine(expires_at, dt.time(), tzinfo=dt.timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
    return expires_at <= now


def renewed_expiry(existing_expiry: Any, days: int = 30, now: Optional[dt.datetime] = None) -> dt.datetime:
    now = now or dt.datetime.now(dt.timezone.utc)
    if existing_expiry:
        if isinstance(existing_expiry, str):
            existing_expiry = dt.datetime.fromisoformat(existing_expiry.replace("Z", "+00:00"))
        if existing_expiry.tzinfo is None:
            existing_expiry = existing_expiry.replace(tzinfo=dt.timezone.utc)
        start = max(existing_expiry, now)
    else:
        start = now
    return start + dt.timedelta(days=int(days))

_PLATFORM_RECORD_TYPES = {
    "asset", "dataset", "dataset_version", "process", "product", "material", "calculation",
    "kpi", "scenario", "recommendation", "decision", "project", "action",
    "document", "workbook", "model", "quality", "maintenance", "energy",
    "cost", "traceability", "risk", "workflow", "artifact",
    "canonical_entity", "canonical_relationship", "canonical_event",
    "twin_asset", "twin_snapshot", "twin_scenario", "connector_health",
    "job", "knowledge_document", "monitoring_event", "report_provenance",
    "security_policy", "twin_snapshot", "connector_run", "connector_schedule",
    "collaboration_item", "monitoring_rule", "cost_baseline", "kpi_definition",
    "project_record", "work_order", "change_request", "risk_record",
    "traceability_record", "laboratory_sample", "procurement_record",
    "spare_part", "shutdown_package", "competency_record",
}
_PLATFORM_FORBIDDEN_KEY = __import__("re").compile(
    r"(?:password|passwd|token|secret|api.?key|authorization|cookie|credential|private.?key|national.?id|passport|e.?mail|phone|mobile|birth|\bdob\b|street|postal.?address|home.?address|full.?name|first.?name|last.?name|username|employee.?id|person.?id)",
    __import__("re").IGNORECASE,
)


def _validate_platform_record_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    import json
    import math

    if not isinstance(payload, Mapping):
        raise ValueError("Platform record payload must be an object.")
    value = dict(payload)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 256 * 1024:
        raise ValueError("Platform record payload exceeds the 256 KiB limit.")

    def inspect(item: Any, depth: int = 0) -> None:
        if depth > 8:
            raise ValueError("Platform record payload nesting is too deep.")
        if isinstance(item, Mapping):
            for key, child in item.items():
                if _PLATFORM_FORBIDDEN_KEY.search(str(key)):
                    raise ValueError("Credential or sensitive identifier fields are not accepted.")
                inspect(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            if len(item) > 5000:
                raise ValueError("Platform record payload contains too many items.")
            for child in item:
                inspect(child, depth + 1)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Platform record payload contains a non-finite number.")
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("Platform record payload contains an unsupported value.")

    inspect(value)
    return value


def edge_download_dataset_version(
    username: str,
    token: str,
    workspace: str,
    dataset_id: str,
    version: int | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Download a registered dataset from private storage and verify its SHA-256."""
    import hashlib
    import requests
    from urllib.parse import urlsplit

    if not str(username or "").strip() or not str(token or ""):
        raise PermissionError("An authenticated workspace session is required.")
    if str(APP_ENVIRONMENT).casefold() != "staging":
        raise RuntimeError("Managed dataset download helper is restricted to staging.")
    result = _edge_call("dataset_download_url", {
        "username": str(username).strip(),
        "token": str(token),
        "workspace": str(workspace or "default").strip(),
        "dataset_id": str(dataset_id),
        "version": version,
    })
    signed_url = str(result.get("download_url") or "")
    parsed = urlsplit(signed_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != STAGING_SUPABASE_PROJECT_HOST
        or not parsed.path.startswith("/storage/v1/object/sign/shoir-industrial-datasets/")
        or not parsed.query
    ):
        raise RuntimeError("Storage provider returned an unexpected signed download URL.")
    response = requests.get(signed_url, timeout=(10, 90))
    if response.status_code != 200:
        raise RuntimeError(
            f"Private dataset download failed ({response.status_code}): {response.text[:300]}"
        )
    content = response.content
    if not content or len(content) > 50 * 1024 * 1024:
        raise RuntimeError("Downloaded dataset is empty or exceeds the 50 MiB limit.")
    digest = hashlib.sha256(content).hexdigest()
    if digest != str(result.get("data_hash") or "").lower():
        raise RuntimeError("Downloaded dataset failed its SHA-256 integrity check.")
    return content, result


def edge_upload_and_register_dataset_version(
    username: str,
    token: str,
    workspace: str,
    dataset_id: str,
    name: str,
    source_name: str,
    file_bytes: bytes,
    data_hash: str,
    version_fingerprint: str,
    row_count: int,
    column_count: int,
    schema: Mapping[str, Any],
    transformations: Sequence[Mapping[str, Any]] = (),
    content_type: str = "text/csv",
) -> dict[str, Any]:
    """Upload a bounded dataset file to private staging storage, then server-verify and register it."""
    import hashlib
    import re
    import requests
    from urllib.parse import urlsplit

    if not str(username or "").strip() or not str(token or ""):
        raise PermissionError("An authenticated workspace session is required.")
    if str(APP_ENVIRONMENT).casefold() != "staging":
        raise RuntimeError("Private dataset upload helper is restricted to the staging environment.")
    if not isinstance(file_bytes, bytes) or not file_bytes or len(file_bytes) > 50 * 1024 * 1024:
        raise ValueError("Dataset upload must be between 1 byte and 50 MiB.")
    actual_hash = hashlib.sha256(file_bytes).hexdigest()
    if actual_hash != str(data_hash or "").lower():
        raise ValueError("Dataset bytes do not match the supplied content hash.")
    if content_type != "text/csv":
        raise ValueError("The normalized dataset artifact must be uploaded as text/csv.")
    upload = _edge_call("dataset_upload_create", {
        "username": str(username).strip(),
        "token": str(token),
        "workspace": str(workspace or "default").strip(),
        "dataset_id": str(dataset_id),
        "data_hash": actual_hash,
    })
    signed_url = str(upload.get("upload_url") or "")
    parsed = urlsplit(signed_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != STAGING_SUPABASE_PROJECT_HOST
        or not parsed.path.startswith("/storage/v1/object/upload/sign/shoir-industrial-datasets/")
        or not parsed.query
    ):
        raise RuntimeError("Storage provider returned an unexpected signed upload URL.")
    response = requests.put(
        signed_url,
        data=file_bytes,
        headers={"Content-Type": content_type, "x-upsert": "false"},
        timeout=(10, 90),
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            f"Private dataset upload failed ({response.status_code}): {response.text[:300]}"
        )
    return _edge_call("dataset_version_finalize", {
        "username": str(username).strip(),
        "token": str(token),
        "workspace": str(workspace or "default").strip(),
        "dataset_id": str(dataset_id),
        "upload_path": str(upload.get("upload_path") or ""),
        "name": str(name)[:200],
        "source_name": str(source_name)[:500],
        "data_hash": actual_hash,
        "version_fingerprint": str(version_fingerprint).lower(),
        "row_count": row_count,
        "column_count": column_count,
        "schema": dict(schema),
        "transformations": [dict(x) for x in transformations],
    })


def edge_register_dataset_version(
    username: str,
    token: str,
    workspace: str,
    dataset_id: str,
    name: str,
    source_name: str,
    data_hash: str,
    version_fingerprint: str,
    row_count: int,
    column_count: int,
    schema: Mapping[str, Any],
    transformations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Atomically register an immutable dataset version through the authenticated Edge API."""
    import re

    if not str(username or "").strip() or not str(token or ""):
        raise PermissionError("An authenticated workspace session is required.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", str(workspace or "default")):
        raise ValueError("Workspace identifier is invalid.")
    if not re.fullmatch(r"DS-[A-F0-9]{12,32}", str(dataset_id or "")):
        raise ValueError("Dataset identifier is invalid.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(data_hash or "").lower()):
        raise ValueError("Dataset content hash is invalid.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(version_fingerprint or "").lower()):
        raise ValueError("Dataset version fingerprint is invalid.")
    if isinstance(row_count, bool) or not isinstance(row_count, int) or not 0 <= row_count <= 100_000_000:
        raise ValueError("Dataset row count is invalid.")
    if isinstance(column_count, bool) or not isinstance(column_count, int) or not 0 <= column_count <= 5000:
        raise ValueError("Dataset column count is invalid.")
    if not isinstance(schema, Mapping):
        raise ValueError("Dataset schema must be an object.")
    if not isinstance(transformations, (list, tuple)) or len(transformations) > 50:
        raise ValueError("Dataset transformation history is invalid.")
    return _edge_call("dataset_version_register", {
        "username": str(username).strip(),
        "token": str(token),
        "workspace": str(workspace or "default").strip(),
        "dataset_id": str(dataset_id),
        "name": str(name)[:200],
        "source_name": str(source_name)[:500],
        "data_hash": str(data_hash).lower(),
        "version_fingerprint": str(version_fingerprint).lower(),
        "row_count": row_count,
        "column_count": column_count,
        "schema": dict(schema),
        "transformations": [dict(x) for x in transformations],
    })


def edge_save_platform_record(
    username: str,
    token: str,
    workspace: str,
    record_type: str,
    entity_key: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one validated workspace-scoped engineering record through the staging Edge API."""
    import re

    user = str(username or "").strip()
    bearer = str(token or "")
    scope = str(workspace or "default").strip()
    kind = str(record_type or "").strip().lower()
    key = str(entity_key or "").strip()
    if not user or not bearer:
        raise PermissionError("An authenticated workspace session is required.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", scope):
        raise ValueError("Workspace identifier is invalid.")
    if kind not in _PLATFORM_RECORD_TYPES:
        raise ValueError("Platform record type is not supported.")
    if not key or len(key) > 240 or any(ord(ch) < 32 or ord(ch) == 127 for ch in key):
        raise ValueError("Platform entity key is invalid.")
    safe_payload = _validate_platform_record_payload(payload)
    return _edge_call("platform_record_save", {
        "username": user,
        "token": bearer,
        "workspace": scope,
        "record_type": kind,
        "entity_key": key,
        "payload": safe_payload,
    })


def edge_list_platform_records(
    username: str,
    token: str,
    workspace: str = "default",
    record_type: str = "",
    limit: int = 100,
    entity_key: str = "",
) -> list[dict[str, Any]]:
    """List workspace records using bounded server-filtered pages."""
    import re

    user = str(username or "").strip()
    bearer = str(token or "")
    scope = str(workspace or "default").strip()
    kind = str(record_type or "").strip().lower()
    key = str(entity_key or "").strip()
    if not user or not bearer:
        raise PermissionError("An authenticated workspace session is required.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", scope):
        raise ValueError("Workspace identifier is invalid.")
    if kind and kind not in _PLATFORM_RECORD_TYPES:
        raise ValueError("Platform record type is not supported.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError("Platform record limit must be between 1 and 10,000.")
    if len(key) > 240 or any(ord(ch) < 32 or ord(ch) == 127 for ch in key):
        raise ValueError("Platform entity key is invalid.")

    records: list[dict[str, Any]] = []
    offset = 0
    while len(records) < limit:
        page_limit = min(200, limit - len(records))
        result = _edge_call("platform_record_list", {
            "username": user,
            "token": bearer,
            "workspace": scope,
            "record_type": kind,
            "entity_key": key,
            "limit": page_limit,
            "offset": offset,
        })
        page = result.get("records", [])
        if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
            raise RuntimeError("Platform persistence returned an invalid record list.")
        if len(page) > page_limit:
            raise RuntimeError("Platform persistence exceeded the requested page size.")
        records.extend(page)
        if not bool(result.get("has_more")):
            break
        next_offset = result.get("next_offset")
        if isinstance(next_offset, bool) or not isinstance(next_offset, int) or next_offset <= offset:
            raise RuntimeError("Platform persistence returned an invalid pagination cursor.")
        if not page:
            raise RuntimeError("Platform persistence reported more data after an empty page.")
        offset = next_offset
    return records
