"""Durable Shoir-IE account/subscription store for Streamlit Cloud.

The app's SQLite file is useful for local development but Streamlit Community
Cloud does not guarantee persistence of local files across restarts. This
module makes a managed PostgreSQL database the authoritative account store
when [database].url is configured in Streamlit secrets (or SHOIR_DATABASE_URL
is present in the environment). SQLite remains a local fallback.

Never put the database URL/password in Git.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from typing import Any, Mapping, Optional

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


def durable_backend_configured() -> bool:
    return bool(database_url()) and psycopg2 is not None


def _pg_connect():
    if not durable_backend_configured():
        raise RuntimeError("Durable PostgreSQL backend is not configured.")
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
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
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
    """Create the durable research-study table alongside account storage."""
    if not durable_backend_configured():
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
    """Persist a research protocol durably when the managed DB is configured."""
    if not durable_backend_configured():
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
                    owner=EXCLUDED.owner,
                    owner_lc=EXCLUDED.owner_lc,
                    title=EXCLUDED.title,
                    protocol_json=EXCLUDED.protocol_json,
                    updated_at=EXCLUDED.updated_at
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
        conn.commit()


def remote_research_study(study_id: str, owner: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Load one durable research protocol, optionally owner-scoped."""
    if not durable_backend_configured():
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
    if not durable_backend_configured():
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
    if not durable_backend_configured():
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
    if not durable_backend_configured():
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

def _iso(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def remote_account(username: str) -> Optional[dict[str, Any]]:
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
    ensure_remote_schema()
    with _pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM shoir_accounts ORDER BY username_lc")
            return [dict(row) for row in cur.fetchall()]


def upsert_remote_account(account: Mapping[str, Any]) -> None:
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


def insert_remote_request(request: Mapping[str, Any]) -> None:
    ensure_remote_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shoir_subscription_requests
                (username,username_lc,email,tier,request_type,payment_method,
                 transaction_id,screenshot_path,status,requested_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(request["username"]),
                    str(request.get("username_lc") or request["username"]).strip().lower(),
                    request.get("email"),
                    request.get("tier"),
                    request.get("request_type", "New"),
                    request.get("payment_method"),
                    request.get("transaction_id"),
                    request.get("screenshot_path"),
                    request.get("status", "Pending"),
                    request.get("requested_at") or dt.datetime.now(dt.timezone.utc),
                    dt.datetime.now(dt.timezone.utc),
                ),
            )
        conn.commit()


def update_remote_request_status(request_id: int, status: str) -> None:
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
    """Update the latest pending request for a user/type without requiring its local ID."""
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
    """Hydrate pending subscription requests from PostgreSQL into SQLite cache."""
    if not durable_backend_configured():
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
    with sqlite3.connect(db_path) as conn:
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
    """Hydrate local SQLite from remote accounts; never delete remote/local rows."""
    if not durable_backend_configured():
        return 0
    ensure_remote_schema()
    rows = remote_accounts()
    if not rows:
        return 0
    with sqlite3.connect(db_path) as conn:
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
    """Upload local accounts that are not already present remotely.
    Existing remote accounts are authoritative and are never overwritten by this migration.
    """
    if not durable_backend_configured():
        return 0
    ensure_remote_schema()
    existing = {row["username_lc"] for row in remote_accounts()}
    with sqlite3.connect(db_path) as conn:
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
    """Use remote PostgreSQL as authority and migrate local-only accounts once."""
    if not durable_backend_configured():
        return False
    ensure_remote_schema()
    migrate_local_accounts_to_remote(db_path)
    sync_remote_accounts_to_local(db_path)
    return True


def save_remote_workspace(username: str, state_json: str) -> bool:
    """Persist serialized Streamlit workspace state in the managed database."""
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
    """Return a user's durable workspace JSON, if available."""
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
