"""
Shoir-IE Enterprise Integration Layer.

Shared platform services for durable industrial artifacts, Digital Twin state,
connector health, jobs, collaboration, knowledge, monitoring, security-safe
file handling, reporting provenance, and data intelligence.

The layer is deliberately additive: existing Shoir-IE module engines remain
the owners of their domain calculations; this module provides the governed
cross-module infrastructure around them.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import sqlite3
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd
import requests

try:
    from durable_account_store import _pg_connect, durable_backend_configured
except Exception:  # local/unit-test safety
    _pg_connect = None
    durable_backend_configured = lambda: False


DEFAULT_DB = "enterprise_full_workspace.db"
_PRIVATE_SCHEMA = "shoir_internal"
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shoir-job")
_FUTURES: dict[str, Any] = {}
_FUTURES_LOCK = threading.Lock()

ALLOWED_UPLOAD_EXTENSIONS = {
    ".csv", ".xlsx", ".xlsm", ".json", ".txt", ".md", ".pdf", ".docx", ".pptx"
}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_ARCHIVE_BYTES = 250 * 1024 * 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def workspace_key(username: str, workspace: str = "default") -> str:
    raw = str(username or "").strip().lower() + "::" + str(workspace or "default").strip().lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _remote() -> bool:
    try:
        return bool(durable_backend_configured and durable_backend_configured() and _pg_connect)
    except Exception:
        return False


def _local_connect(db_path: Optional[str] = None):
    # Resolve DEFAULT_DB at call time so tests and local deployments can safely
    # override the enterprise store without relying on a stale default argument.
    target = str(db_path or DEFAULT_DB)
    conn = sqlite3.connect(target, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


LOCAL_DDL = [
    """CREATE TABLE IF NOT EXISTS shoir_ent_artifacts (
        artifact_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, artifact_type TEXT NOT NULL,
        name TEXT NOT NULL, payload_json TEXT NOT NULL, content_hash TEXT, owner TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_artifacts_ws
        ON shoir_ent_artifacts(workspace_id, artifact_type, updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_twin_assets (
        workspace_id TEXT NOT NULL, asset_id TEXT NOT NULL, state_json TEXT NOT NULL,
        source TEXT, updated_at TEXT NOT NULL, PRIMARY KEY(workspace_id, asset_id))""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_twin_snapshots (
        snapshot_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, scenario_name TEXT NOT NULL,
        state_json TEXT NOT NULL, created_by TEXT, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_twin_scenarios (
        scenario_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
        parent_name TEXT, parameters_json TEXT NOT NULL, notes TEXT, created_by TEXT,
        created_at TEXT NOT NULL, UNIQUE(workspace_id, name))""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_connector_health (
        connector_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
        system_type TEXT NOT NULL, protocol TEXT NOT NULL, endpoint TEXT, status TEXT NOT NULL,
        latency_ms REAL, detail TEXT, checked_at TEXT NOT NULL, checked_by TEXT, secret_ref TEXT)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_connector_runs (
        run_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, connector_id TEXT NOT NULL,
        operation TEXT NOT NULL, status TEXT NOT NULL, latency_ms REAL, detail TEXT,
        records INTEGER NOT NULL DEFAULT 0, started_at TEXT NOT NULL, finished_at TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_connector_runs_ws
        ON shoir_ent_connector_runs(workspace_id, started_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_connector_schedules (
        schedule_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, connector_id TEXT NOT NULL,
        interval_minutes INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
        next_run_at TEXT, last_run_at TEXT, last_status TEXT, updated_at TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_connector_sched_ws
        ON shoir_ent_connector_schedules(workspace_id, next_run_at)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_connector_ws
        ON shoir_ent_connector_health(workspace_id, checked_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_jobs (
        job_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, module TEXT NOT NULL,
        job_type TEXT NOT NULL, status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
        message TEXT, payload_json TEXT, result_json TEXT, attempts INTEGER NOT NULL DEFAULT 0,
        cancel_requested INTEGER NOT NULL DEFAULT 0, pause_requested INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, updated_at TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_jobs_ws
        ON shoir_ent_jobs(workspace_id, updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_collaboration (
        item_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, item_type TEXT NOT NULL,
        subject TEXT, body TEXT, actor TEXT NOT NULL, assignee TEXT, reviewer TEXT,
        status TEXT NOT NULL DEFAULT 'Open', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_collab_ws
        ON shoir_ent_collaboration(workspace_id, updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_knowledge (
        doc_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
        content TEXT NOT NULL, source_type TEXT, tags_json TEXT, sha256 TEXT NOT NULL,
        created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_knowledge_ws
        ON shoir_ent_knowledge(workspace_id, updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_monitoring_rules (
        rule_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
        metric TEXT NOT NULL, operator TEXT NOT NULL, threshold REAL NOT NULL,
        severity TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_monitoring_events (
        event_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, rule_id TEXT,
        asset_id TEXT, metric TEXT NOT NULL, value REAL NOT NULL, status TEXT NOT NULL,
        message TEXT, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_report_provenance (
        report_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, module TEXT NOT NULL,
        format TEXT NOT NULL, filename TEXT NOT NULL, source_hash TEXT,
        figure_hashes_json TEXT, artifact_ids_json TEXT, created_by TEXT,
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_security (
        workspace_id TEXT PRIMARY KEY, require_mfa INTEGER NOT NULL DEFAULT 0,
        oidc_provider TEXT, oidc_enabled INTEGER NOT NULL DEFAULT 0,
        retention_days INTEGER NOT NULL DEFAULT 365, updated_by TEXT, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_canonical_entities (
        entity_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, entity_type TEXT NOT NULL,
        name TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Observed',
        state_json TEXT NOT NULL, content_hash TEXT NOT NULL, created_by TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,entity_type,name,source))""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_canonical_entities_ws
        ON shoir_ent_canonical_entities(workspace_id,entity_type,updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_canonical_relationships (
        relationship_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
        source_entity_id TEXT NOT NULL, target_entity_id TEXT NOT NULL,
        relation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Linked',
        metadata_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(workspace_id,source_entity_id,target_entity_id,relation))""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_canonical_relationships_ws
        ON shoir_ent_canonical_relationships(workspace_id,updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_ent_canonical_events (
        event_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, event_type TEXT NOT NULL,
        entity_id TEXT, relationship_id TEXT, payload_json TEXT NOT NULL, actor TEXT,
        created_at TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_ent_canonical_events_ws
        ON shoir_ent_canonical_events(workspace_id,created_at DESC)""",
]


REMOTE_DDL = [
    """CREATE SCHEMA IF NOT EXISTS shoir_internal""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.artifacts (
        artifact_id text PRIMARY KEY, workspace_id text NOT NULL, artifact_type text NOT NULL,
        name text NOT NULL, payload_json text NOT NULL, content_hash text, owner text,
        created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_artifacts_ws
        ON shoir_internal.artifacts(workspace_id, artifact_type, updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.twin_assets (
        workspace_id text NOT NULL, asset_id text NOT NULL, state_json text NOT NULL,
        source text, updated_at timestamptz NOT NULL, PRIMARY KEY(workspace_id, asset_id))""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.twin_snapshots (
        snapshot_id text PRIMARY KEY, workspace_id text NOT NULL, scenario_name text NOT NULL,
        state_json text NOT NULL, created_by text, created_at timestamptz NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.twin_scenarios (
        scenario_id text PRIMARY KEY, workspace_id text NOT NULL, name text NOT NULL,
        parent_name text, parameters_json text NOT NULL, notes text, created_by text,
        created_at timestamptz NOT NULL, UNIQUE(workspace_id, name))""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.connector_health (
        connector_id text PRIMARY KEY, workspace_id text NOT NULL, name text NOT NULL,
        system_type text NOT NULL, protocol text NOT NULL, endpoint text, status text NOT NULL,
        latency_ms double precision, detail text, checked_at timestamptz NOT NULL, checked_by text, secret_ref text)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.connector_runs (
        run_id text PRIMARY KEY, workspace_id text NOT NULL, connector_id text NOT NULL,
        operation text NOT NULL, status text NOT NULL, latency_ms double precision,
        detail text, records integer NOT NULL DEFAULT 0, started_at timestamptz NOT NULL,
        finished_at timestamptz NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_connector_runs_ws
        ON shoir_internal.connector_runs(workspace_id, started_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.connector_schedules (
        schedule_id text PRIMARY KEY, workspace_id text NOT NULL, connector_id text NOT NULL,
        interval_minutes integer NOT NULL, enabled boolean NOT NULL DEFAULT true,
        next_run_at timestamptz, last_run_at timestamptz, last_status text, updated_at timestamptz NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_connector_sched_ws
        ON shoir_internal.connector_schedules(workspace_id, next_run_at)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_connector_ws
        ON shoir_internal.connector_health(workspace_id, checked_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.jobs (
        job_id text PRIMARY KEY, workspace_id text NOT NULL, module text NOT NULL,
        job_type text NOT NULL, status text NOT NULL, progress double precision NOT NULL DEFAULT 0,
        message text, payload_json text, result_json text, attempts integer NOT NULL DEFAULT 0,
        cancel_requested boolean NOT NULL DEFAULT false, pause_requested boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL, started_at timestamptz, finished_at timestamptz,
        updated_at timestamptz NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_jobs_ws
        ON shoir_internal.jobs(workspace_id, updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.collaboration (
        item_id text PRIMARY KEY, workspace_id text NOT NULL, item_type text NOT NULL,
        subject text, body text, actor text NOT NULL, assignee text, reviewer text,
        status text NOT NULL DEFAULT 'Open', created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_collab_ws
        ON shoir_internal.collaboration(workspace_id, updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.knowledge (
        doc_id text PRIMARY KEY, workspace_id text NOT NULL, name text NOT NULL,
        content text NOT NULL, source_type text, tags_json text, sha256 text NOT NULL,
        created_by text, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_knowledge_ws
        ON shoir_internal.knowledge(workspace_id, updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.monitoring_rules (
        rule_id text PRIMARY KEY, workspace_id text NOT NULL, name text NOT NULL,
        metric text NOT NULL, operator text NOT NULL, threshold double precision NOT NULL,
        severity text NOT NULL, enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.monitoring_events (
        event_id text PRIMARY KEY, workspace_id text NOT NULL, rule_id text,
        asset_id text, metric text NOT NULL, value double precision NOT NULL, status text NOT NULL,
        message text, created_at timestamptz NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.report_provenance (
        report_id text PRIMARY KEY, workspace_id text NOT NULL, module text NOT NULL,
        format text NOT NULL, filename text NOT NULL, source_hash text,
        figure_hashes_json text, artifact_ids_json text, created_by text,
        created_at timestamptz NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.security (
        workspace_id text PRIMARY KEY, require_mfa boolean NOT NULL DEFAULT false,
        oidc_provider text, oidc_enabled boolean NOT NULL DEFAULT false,
        retention_days integer NOT NULL DEFAULT 365, updated_by text, updated_at timestamptz NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.canonical_entities (
        entity_id text PRIMARY KEY, workspace_id text NOT NULL, entity_type text NOT NULL,
        name text NOT NULL, source text NOT NULL, status text NOT NULL DEFAULT 'Observed',
        state_json text NOT NULL, content_hash text NOT NULL, created_by text,
        created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
        UNIQUE(workspace_id,entity_type,name,source))""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_canonical_entities_ws
        ON shoir_internal.canonical_entities(workspace_id,entity_type,updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.canonical_relationships (
        relationship_id text PRIMARY KEY, workspace_id text NOT NULL,
        source_entity_id text NOT NULL, target_entity_id text NOT NULL,
        relation text NOT NULL, status text NOT NULL DEFAULT 'Linked',
        metadata_json text NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
        UNIQUE(workspace_id,source_entity_id,target_entity_id,relation))""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_canonical_relationships_ws
        ON shoir_internal.canonical_relationships(workspace_id,updated_at DESC)""",
    """CREATE TABLE IF NOT EXISTS shoir_internal.canonical_events (
        event_id text PRIMARY KEY, workspace_id text NOT NULL, event_type text NOT NULL,
        entity_id text, relationship_id text, payload_json text NOT NULL, actor text,
        created_at timestamptz NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_shoir_internal_canonical_events_ws
        ON shoir_internal.canonical_events(workspace_id,created_at DESC)""",
]


def ensure_enterprise_schema(db_path: Optional[str] = None) -> None:
    """Create the additive enterprise layer in private schema/local tables."""
    db_path = str(db_path or DEFAULT_DB)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                for sql in REMOTE_DDL:
                    cur.execute(sql)
                cur.execute("ALTER TABLE IF EXISTS shoir_internal.connector_health ADD COLUMN IF NOT EXISTS secret_ref text")
                cur.execute("REVOKE ALL ON SCHEMA shoir_internal FROM anon, authenticated")
                cur.execute("REVOKE ALL ON ALL TABLES IN SCHEMA shoir_internal FROM anon, authenticated")
            conn.commit()
        return
    with _local_connect(db_path) as conn:
        for sql in LOCAL_DDL:
            conn.execute(sql)
        try:
            conn.execute("ALTER TABLE shoir_ent_connector_health ADD COLUMN secret_ref TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def _artifact_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def record_artifact(
    username: str,
    artifact_type: str,
    name: str,
    payload: Mapping[str, Any] | Sequence[Any] | str,
    workspace: str = "default",
    artifact_id: Optional[str] = None,
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    aid = artifact_id or "ART-" + uuid.uuid4().hex[:14].upper()
    body = payload if isinstance(payload, (dict, list, tuple, str)) else {"value": payload}
    payload_json = _json(body)
    stamp = now_iso()
    content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.artifacts
                    (artifact_id,workspace_id,artifact_type,name,payload_json,content_hash,owner,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (artifact_id) DO UPDATE SET
                      payload_json=EXCLUDED.payload_json,content_hash=EXCLUDED.content_hash,
                      updated_at=EXCLUDED.updated_at""",
                    (aid, wid, artifact_type, str(name), payload_json, content_hash, username, stamp, stamp),
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_artifacts
                (artifact_id,workspace_id,artifact_type,name,payload_json,content_hash,owner,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                payload_json=excluded.payload_json,content_hash=excluded.content_hash,
                updated_at=excluded.updated_at""",
                (aid, wid, artifact_type, str(name), payload_json, content_hash, username, stamp, stamp),
            )
            conn.commit()
    return aid


_CANONICAL_PAYLOAD_LIMIT = 60000
_CANONICAL_SENSITIVE_KEYS = {
    "password", "token", "secret", "api_key", "apikey", "client_secret",
    "access_token", "refresh_token", "authorization", "otp",
}


def _canonical_safe(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if str(key).strip().lower() in _CANONICAL_SENSITIVE_KEYS:
                continue
            out[str(key)[:120]] = _canonical_safe(item, depth + 1)
            if len(out) >= 120:
                break
        return out
    if isinstance(value, pd.DataFrame):
        return {
            "__type__": "dataframe",
            "rows": int(len(value)),
            "columns": [str(x) for x in value.columns[:80]],
            "sha256": hashlib.sha256(value.to_csv(index=False).encode("utf-8")).hexdigest(),
        }
    if isinstance(value, pd.Series):
        return {"__type__": "series", "length": int(len(value))}
    if isinstance(value, (list, tuple)):
        return [_canonical_safe(x, depth + 1) for x in list(value)[:200]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value[:4000] if isinstance(value, str) else value
    if isinstance(value, np.generic):
        return _canonical_safe(value.item(), depth + 1)
    return str(value)[:4000]


def _canonical_json(payload: Any) -> tuple[str, str]:
    safe = _canonical_safe(payload)
    raw = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    if len(raw.encode("utf-8")) > _CANONICAL_PAYLOAD_LIMIT:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        safe = {"truncated": True, "sha256": digest, "preview": raw[:56000]}
        raw = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_entity_id(username: str, workspace: str, entity_type: str, name: str, source: str = "") -> str:
    wid = workspace_key(username, workspace)
    raw = f"{wid}|{str(entity_type).strip()}|{str(name).strip()}|{str(source).strip()}"
    return "CEN-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def upsert_canonical_entity(
    username: str,
    entity_type: str,
    name: str,
    source: str = "",
    state: Any = None,
    status: str = "Observed",
    workspace: str = "default",
    secret_ref: str = "",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    safe_secret_ref = str(secret_ref or "")[:300]
    eid = canonical_entity_id(username, workspace, entity_type, name, source)
    payload_json, content_hash = _canonical_json(state or {})
    stamp = now_iso()
    values = (eid, wid, str(entity_type)[:100], str(name)[:240], str(source)[:300],
              str(status)[:80] or "Observed", payload_json, content_hash, username, stamp, stamp)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.canonical_entities
                    (entity_id,workspace_id,entity_type,name,source,status,state_json,content_hash,created_by,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (entity_id) DO UPDATE SET
                      status=EXCLUDED.status,state_json=EXCLUDED.state_json,
                      content_hash=EXCLUDED.content_hash,updated_at=EXCLUDED.updated_at""",
                    values,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_canonical_entities
                (entity_id,workspace_id,entity_type,name,source,status,state_json,content_hash,created_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(entity_id) DO UPDATE SET
                  status=excluded.status,state_json=excluded.state_json,
                  content_hash=excluded.content_hash,updated_at=excluded.updated_at""",
                values,
            )
            conn.commit()
    return eid


def canonical_relationship_id(username: str, workspace: str, source_entity_id: str, target_entity_id: str, relation: str) -> str:
    wid = workspace_key(username, workspace)
    raw = f"{wid}|{source_entity_id}|{target_entity_id}|{relation}"
    return "CREL-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def upsert_canonical_relationship(
    username: str,
    source_entity_id: str,
    target_entity_id: str,
    relation: str,
    status: str = "Linked",
    metadata: Any = None,
    workspace: str = "default",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    rid = canonical_relationship_id(username, workspace, source_entity_id, target_entity_id, relation)
    metadata_json, _ = _canonical_json(metadata or {})
    stamp = now_iso()
    values = (rid, wid, str(source_entity_id), str(target_entity_id), str(relation)[:180],
              str(status)[:80] or "Linked", metadata_json, stamp, stamp)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.canonical_relationships
                    (relationship_id,workspace_id,source_entity_id,target_entity_id,relation,status,metadata_json,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (relationship_id) DO UPDATE SET
                      status=EXCLUDED.status,metadata_json=EXCLUDED.metadata_json,updated_at=EXCLUDED.updated_at""",
                    values,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_canonical_relationships
                (relationship_id,workspace_id,source_entity_id,target_entity_id,relation,status,metadata_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(relationship_id) DO UPDATE SET
                  status=excluded.status,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
                values,
            )
            conn.commit()
    return rid


def record_canonical_event(
    username: str,
    event_type: str,
    payload: Any = None,
    entity_id: str = "",
    relationship_id: str = "",
    workspace: str = "default",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    event_id = "CEVT-" + uuid.uuid4().hex[:14].upper()
    payload_json, _ = _canonical_json(payload or {})
    stamp = now_iso()
    values = (event_id, wid, str(event_type)[:120], str(entity_id or "")[:80] or None,
              str(relationship_id or "")[:80] or None, payload_json, username, stamp)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.canonical_events
                    (event_id,workspace_id,event_type,entity_id,relationship_id,payload_json,actor,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    values,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_canonical_events
                (event_id,workspace_id,event_type,entity_id,relationship_id,payload_json,actor,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                values,
            )
            conn.commit()
    return event_id


def canonical_entities_frame(username: str, workspace: str = "default", entity_type: str = "", limit: int = 2000) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.canonical_entities" if _remote() else "shoir_ent_canonical_entities"
    sql = "SELECT entity_id,workspace_id,entity_type,name,source,status,state_json,content_hash,created_by,created_at,updated_at FROM " + table
    sql += " WHERE workspace_id=" + ("%s" if _remote() else "?")
    params = [wid]
    if entity_type:
        sql += " AND entity_type=" + ("%s" if _remote() else "?")
        params.append(str(entity_type))
    sql += " ORDER BY updated_at DESC LIMIT " + str(max(1, min(5000, int(limit))))
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def canonical_relationships_frame(username: str, workspace: str = "default", limit: int = 5000) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.canonical_relationships" if _remote() else "shoir_ent_canonical_relationships"
    sql = "SELECT * FROM " + table + " WHERE workspace_id=" + ("%s" if _remote() else "?") + " ORDER BY updated_at DESC LIMIT " + str(max(1, min(10000, int(limit))))
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def canonical_events_frame(username: str, workspace: str = "default", limit: int = 5000) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.canonical_events" if _remote() else "shoir_ent_canonical_events"
    sql = "SELECT * FROM " + table + " WHERE workspace_id=" + ("%s" if _remote() else "?") + " ORDER BY created_at DESC LIMIT " + str(max(1, min(10000, int(limit))))
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def canonical_state_manifest(username: str, workspace: str = "default") -> dict[str, Any]:
    entities = canonical_entities_frame(username, workspace, limit=5000)
    relationships = canonical_relationships_frame(username, workspace, limit=10000)
    events = canonical_events_frame(username, workspace, limit=10000)
    combined = (
        entities.to_json(orient="records", date_format="iso")
        + relationships.to_json(orient="records", date_format="iso")
        + events.to_json(orient="records", date_format="iso")
    )
    return {
        "workspace_id": workspace_key(username, workspace),
        "workspace": str(workspace),
        "entity_count": int(len(entities)),
        "relationship_count": int(len(relationships)),
        "event_count": int(len(events)),
        "entity_types": entities["entity_type"].value_counts().to_dict() if not entities.empty else {},
        "last_entity_update": str(entities["updated_at"].max()) if not entities.empty else None,
        "last_event": str(events["created_at"].max()) if not events.empty else None,
        "content_hash": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
    }


def canonical_health(username: str, workspace: str = "default") -> dict[str, Any]:
    manifest = canonical_state_manifest(username, workspace)
    required = 13
    observed_types = len([x for x in manifest["entity_types"] if x in {
        "Asset","Process","Product","Material","Order","Workforce",
        "Quality","Maintenance","Energy","Cost","Scenario","Decision","Outcome",
    }])
    return {
        "status": "Healthy" if manifest["entity_count"] > 0 else "No Data",
        "coverage": round(observed_types / required * 100.0, 1),
        **manifest,
    }


def build_control_tower_health_from_canonical(username: str, workspace: str = "default") -> pd.DataFrame:
    """Build the Control Tower from the durable canonical industrial state."""
    entities = canonical_entities_frame(username, workspace, limit=5000)
    events = canonical_events_frame(username, workspace, limit=10000)
    domain_types = {
        "Production": {"Process", "KPI"},
        "Supply": {"Order", "Material"},
        "Inventory": {"Material", "Product"},
        "Quality": {"Quality"},
        "Maintenance": {"Maintenance", "Asset"},
        "Transport": {"Transport", "Route"},
        "Workforce": {"Workforce"},
        "Energy": {"Energy"},
        "Carbon": {"Carbon"},
    }
    alert_events = (
        events[events["event_type"].astype(str).str.lower().str.contains("alert|anomaly|attention|error|offline", regex=True)]
        if not events.empty else pd.DataFrame()
    )
    rows = []
    for domain, types in domain_types.items():
        subset = entities[entities["entity_type"].isin(types)] if not entities.empty else pd.DataFrame()
        records = int(len(subset))
        related_ids = set(subset["entity_id"].astype(str)) if not subset.empty else set()
        domain_events = (
            alert_events[alert_events["entity_id"].astype(str).isin(related_ids)]
            if not alert_events.empty and related_ids else pd.DataFrame()
        )
        alerts = int(len(domain_events))
        if records == 0:
            status, score = "No Data", 0.0
        elif alerts:
            status, score = "Attention", 35.0
        else:
            status, score = "Healthy", 100.0
        rows.append({
            "Area": domain,
            "Status": status,
            "Health %": score,
            "Records": records,
            "Alerts": alerts,
            "Last Update": str(subset["updated_at"].max()) if not subset.empty else "—",
            "Signal": "Canonical Digital Thread" if records else "No canonical entity mapped",
        })
    return pd.DataFrame(rows)


def list_artifacts(username: str, artifact_type: Optional[str] = None, workspace: str = "default", limit: int = 200) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.artifacts" if _remote() else "shoir_ent_artifacts"
    sql = "SELECT * FROM " + table + " WHERE workspace_id=%s" if _remote() else "SELECT * FROM " + table + " WHERE workspace_id=?"
    params: list[Any] = [wid]
    if artifact_type:
        sql += " AND artifact_type=" + ("%s" if _remote() else "?")
        params.append(artifact_type)
    sql += " ORDER BY updated_at DESC LIMIT " + str(max(1, min(1000, int(limit))))
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _save_twin_asset(username: str, asset_id: str, state: Mapping[str, Any], source: str, workspace: str) -> None:
    wid = workspace_key(username, workspace)
    stamp = now_iso()
    body = _json(state)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.twin_assets
                    (workspace_id,asset_id,state_json,source,updated_at) VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(workspace_id,asset_id) DO UPDATE SET
                    state_json=EXCLUDED.state_json,source=EXCLUDED.source,updated_at=EXCLUDED.updated_at""",
                    (wid, str(asset_id), body, source, stamp),
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_twin_assets
                (workspace_id,asset_id,state_json,source,updated_at) VALUES (?,?,?,?,?)
                ON CONFLICT(workspace_id,asset_id) DO UPDATE SET
                state_json=excluded.state_json,source=excluded.source,updated_at=excluded.updated_at""",
                (wid, str(asset_id), body, source, stamp),
            )
            conn.commit()


def save_twin_snapshot(
    username: str,
    states: pd.DataFrame | Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    source: str = "manual",
    scenario_name: str = "Live",
    workspace: str = "default",
) -> str:
    """Update live asset state and append a replayable immutable snapshot."""
    ensure_enterprise_schema()
    if isinstance(states, pd.DataFrame):
        records = states.to_dict("records")
    elif isinstance(states, Mapping):
        records = [{"Asset": k, **dict(v)} for k, v in states.items()]
    else:
        records = [dict(x) for x in states]
    normalized: list[dict[str, Any]] = []
    for row in records:
        asset = str(row.get("Asset") or row.get("asset_id") or row.get("ID") or "").strip()
        if not asset:
            continue
        normalized.append(dict(row, Asset=asset))
        _save_twin_asset(username, asset, dict(row), source, workspace)
    wid = workspace_key(username, workspace)
    sid = "TWS-" + uuid.uuid4().hex[:14].upper()
    stamp = now_iso()
    body = _json(normalized)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.twin_snapshots
                    (snapshot_id,workspace_id,scenario_name,state_json,created_by,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (sid, wid, str(scenario_name), body, username, stamp),
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_twin_snapshots
                (snapshot_id,workspace_id,scenario_name,state_json,created_by,created_at)
                VALUES (?,?,?,?,?,?)""",
                (sid, wid, str(scenario_name), body, username, stamp),
            )
            conn.commit()
    record_artifact(username, "digital_twin_snapshot", scenario_name, {"snapshot_id": sid, "states": normalized}, workspace)
    return sid


def load_twin_state(username: str, workspace: str = "default", limit: int = 500) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.twin_assets" if _remote() else "shoir_ent_twin_assets"
    sql = "SELECT asset_id,state_json,source,updated_at FROM " + table + (
        " WHERE workspace_id=%s ORDER BY updated_at DESC LIMIT " if _remote() else
        " WHERE workspace_id=? ORDER BY updated_at DESC LIMIT "
    ) + str(max(1, min(2000, int(limit))))
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        df = pd.read_sql_query(sql, conn, params=[wid])
    if df.empty:
        return df
    rows = []
    for r in df.to_dict("records"):
        try:
            payload = json.loads(r["state_json"])
        except Exception:
            payload = {"Asset": r["asset_id"], "State": r["state_json"]}
        payload = dict(payload)
        payload.setdefault("Asset", r["asset_id"])
        payload["Source"] = r["source"]
        payload["Updated At"] = r["updated_at"]
        rows.append(payload)
    return pd.DataFrame(rows)


def save_twin_scenario(
    username: str,
    name: str,
    parameters: Mapping[str, Any],
    parent_name: str = "Live",
    notes: str = "",
    workspace: str = "default",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    sid = "TWSCN-" + uuid.uuid4().hex[:12].upper()
    stamp = now_iso()
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.twin_scenarios
                    (scenario_id,workspace_id,name,parent_name,parameters_json,notes,created_by,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(workspace_id,name) DO UPDATE SET
                    parent_name=EXCLUDED.parent_name,parameters_json=EXCLUDED.parameters_json,
                    notes=EXCLUDED.notes""",
                    (sid, wid, str(name), str(parent_name), _json(parameters), str(notes), username, stamp),
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_twin_scenarios
                (scenario_id,workspace_id,name,parent_name,parameters_json,notes,created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(workspace_id,name) DO UPDATE SET
                parent_name=excluded.parent_name,parameters_json=excluded.parameters_json,notes=excluded.notes""",
                (sid, wid, str(name), str(parent_name), _json(parameters), str(notes), username, stamp),
            )
            conn.commit()
    return sid


def list_twin_scenarios(username: str, workspace: str = "default") -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.twin_scenarios" if _remote() else "shoir_ent_twin_scenarios"
    sql = "SELECT * FROM " + table + (" WHERE workspace_id=%s" if _remote() else " WHERE workspace_id=?") + " ORDER BY created_at DESC"
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def twin_what_if(df: pd.DataFrame, changes: Mapping[str, float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply explicit numeric deltas without mutating the live state."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Digital Twin what-if input must be a DataFrame.")
    baseline = df.copy(deep=True)
    scenario = df.copy(deep=True)
    audit_rows: list[dict[str, Any]] = []
    for column, delta in changes.items():
        if column not in scenario.columns:
            continue
        values = pd.to_numeric(scenario[column], errors="coerce")
        if values.notna().any():
            before = values.copy()
            scenario[column] = values + float(delta)
            audit_rows.append({
                "Column": str(column),
                "Delta": float(delta),
                "Before Mean": float(before.mean()),
                "After Mean": float(scenario[column].mean()),
            })
    return scenario, pd.DataFrame(audit_rows)


def twin_replay(username: str, scenario_name: Optional[str] = None, workspace: str = "default", limit: int = 200) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.twin_snapshots" if _remote() else "shoir_ent_twin_snapshots"
    sql = "SELECT snapshot_id,scenario_name,state_json,created_by,created_at FROM " + table + (
        " WHERE workspace_id=%s" if _remote() else " WHERE workspace_id=?"
    )
    params = [wid]
    if scenario_name:
        sql += " AND scenario_name=" + ("%s" if _remote() else "?")
        params.append(scenario_name)
    sql += " ORDER BY created_at DESC LIMIT " + str(max(1, min(2000, int(limit))))
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    return df


def _status_from_health(status: str, alerts: int = 0, records: int = 0) -> str:
    s = str(status or "").lower()
    if alerts > 0 or any(x in s for x in ("critical", "error", "offline", "failed")):
        return "Attention"
    if "warn" in s or "review" in s:
        return "Review"
    if records <= 0:
        return "No Data"
    if any(x in s for x in ("ready", "online", "connected", "healthy", "operational")):
        return "Healthy"
    return "Ready"


def build_control_tower_health(state: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    """Normalize disparate module states into one control-tower health map."""
    areas = [
        "Production", "Supply", "Inventory", "Quality", "Maintenance",
        "Transport", "Workforce", "Energy", "Carbon"
    ]
    rows = []
    for area in areas:
        item = dict(state.get(area, {}))
        records = int(item.get("records", 0) or 0)
        alerts = int(item.get("alerts", 0) or 0)
        rows.append({
            "Area": area,
            "Records": records,
            "Alerts": alerts,
            "Health": _status_from_health(str(item.get("status", "")), alerts, records),
            "KPI": item.get("kpi", "—"),
            "Last Update": item.get("last_update", "—"),
        })
    return pd.DataFrame(rows)


def redact_connector_endpoint(endpoint: str) -> str:
    """Remove embedded credentials/tokens from persisted connector endpoints."""
    value = str(endpoint or "").strip()
    if not value:
        return ""
    try:
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
        parts = urlsplit(value)
        userinfo = ""
        if parts.username:
            userinfo = parts.username
        host = parts.hostname or ""
        if parts.port:
            host += ":" + str(parts.port)
        if userinfo:
            host = userinfo + "@"+host
        blocked = {"token","access_token","api_key","apikey","key","password","passwd","secret","client_secret"}
        query = [(k, "***" if k.lower() in blocked else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        return urlunsplit((parts.scheme, host, parts.path, urlencode(query, safe="*"), ""))
    except Exception:
        return re.sub(r"(?i)(password|token|api[_-]?key|secret)=([^&\s]+)", r"\1=***", value)

def record_connector_health(
    username: str,
    name: str,
    system_type: str,
    protocol: str,
    endpoint: str,
    status: str,
    detail: str = "",
    latency_ms: Optional[float] = None,
    workspace: str = "default",
    secret_ref: str = "",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    cid = "CONN-" + hashlib.sha256((wid + "|" + name + "|" + system_type + "|" + protocol).encode()).hexdigest()[:14].upper()
    stamp = now_iso()
    safe_endpoint = redact_connector_endpoint(endpoint)
    safe_secret_ref = str(secret_ref or "")[:300]
    params = (
        cid, wid, name, system_type, protocol, safe_endpoint, status, latency_ms,
        detail, stamp, username, safe_secret_ref,
    )
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.connector_health
                    (connector_id,workspace_id,name,system_type,protocol,endpoint,status,latency_ms,detail,checked_at,checked_by,secret_ref)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(connector_id) DO UPDATE SET
                    status=EXCLUDED.status,latency_ms=EXCLUDED.latency_ms,detail=EXCLUDED.detail,
                    checked_at=EXCLUDED.checked_at,checked_by=EXCLUDED.checked_by,secret_ref=EXCLUDED.secret_ref""",
                    params,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_connector_health
                (connector_id,workspace_id,name,system_type,protocol,endpoint,status,latency_ms,detail,checked_at,checked_by,secret_ref)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(connector_id) DO UPDATE SET
                status=excluded.status,latency_ms=excluded.latency_ms,detail=excluded.detail,
                checked_at=excluded.checked_at,checked_by=excluded.checked_by,secret_ref=excluded.secret_ref""",
                params,
            )
            conn.commit()
    return cid


def connector_health_frame(username: str, workspace: str = "default") -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.connector_health" if _remote() else "shoir_ent_connector_health"
    sql = "SELECT * FROM " + table + (" WHERE workspace_id=%s" if _remote() else " WHERE workspace_id=?") + " ORDER BY checked_at DESC"
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def check_rest_connector(url: str, token: str = "", timeout: float = 8.0) -> tuple[str, float, str]:
    target = str(url or "").strip()
    if not re.match(r"^https?://", target, flags=re.I):
        return "Configuration Error", 0.0, "Endpoint must use http:// or https://."
    started = datetime.now(timezone.utc)
    try:
        headers = {"Authorization": "Bearer " + token} if token else {}
        response = requests.get(target, headers=headers, timeout=max(1.0, float(timeout)))
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        status = "Healthy" if 200 <= response.status_code < 400 else "Attention"
        return status, round(elapsed, 1), "HTTP " + str(response.status_code)
    except requests.RequestException as exc:
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        return "Offline", round(elapsed, 1), type(exc).__name__ + ": " + str(exc)[:220]


def validate_connector_profile(system_type: str, protocol: str, endpoint: str) -> dict[str, Any]:
    system = str(system_type or "").strip().upper()
    proto = str(protocol or "").strip().upper()
    ep = str(endpoint or "").strip()
    supported_systems = {"SAP", "ORACLE", "WMS", "MES", "ERP", "SQL", "REST", "MQTT", "OPC-UA"}
    supported_protocols = set(CONNECTOR_PROTOCOLS)
    errors = []
    if system not in supported_systems:
        errors.append("Unsupported system type.")
    if proto not in supported_protocols:
        errors.append("Unsupported protocol profile.")
    elif system in CONNECTOR_SYSTEM_PROTOCOLS and proto not in CONNECTOR_SYSTEM_PROTOCOLS[system]:
        errors.append(f"Protocol {proto} is not executable for system type {system} in the current adapter build.")
    if proto in {"REST", "ODATA", "HTTPS"} and ep and not re.match(r"^https?://", ep, flags=re.I):
        errors.append("HTTP-based endpoints must use http:// or https://.")
    if proto == "MQTT" and ep and not re.match(r"^(mqtt|mqtts)://", ep, flags=re.I):
        errors.append("MQTT endpoints should use mqtt:// or mqtts://.")
    if proto == "OPC-UA" and ep and not re.match(r"^opc\.tcp://", ep, flags=re.I):
        errors.append("OPC-UA endpoints should use opc.tcp://.")
    if proto in {"SQL", "JDBC"} and ep and not re.match(r"^(sqlite:///|postgres(ql)?://)", ep, flags=re.I):
        errors.append("SQL adapter currently accepts sqlite:/// or PostgreSQL DSNs.")
    return {"valid": not errors, "errors": errors, "system_type": system, "protocol": proto, "adapter": CONNECTOR_PROTOCOLS.get(proto, proto)}

CONNECTOR_SYSTEM_PROTOCOLS = {
    # These are executable transports in the current adapter build. A named
    # system is not treated as a native database driver unless the adapter
    # actually implements and tests that transport.
    "SAP": {"REST", "ODATA", "HTTPS"},
    "ORACLE": {"REST", "ODATA", "HTTPS"},
    "WMS": {"REST", "ODATA", "HTTPS"},
    "MES": {"REST", "ODATA", "HTTPS", "MQTT"},
    "ERP": {"REST", "ODATA", "HTTPS"},
    "SQL": {"SQL"},
    "REST": {"REST", "ODATA", "HTTPS"},
    "MQTT": {"MQTT"},
    "OPC-UA": {"OPC-UA"},
}


CONNECTOR_PROTOCOLS = {
    "REST": "HTTP(S) API",
    "ODATA": "OData / HTTP API",
    "HTTPS": "HTTP(S) API",
    "SQL": "Relational database",
    "JDBC": "JDBC-compatible database",
    "MQTT": "MQTT telemetry broker",
    "OPC-UA": "OPC-UA industrial endpoint",
}


def resolve_connector_secret(secret_ref: str = "") -> str:
    """Resolve credentials by reference without ever persisting the secret value."""
    ref = str(secret_ref or "").strip()
    if not ref:
        return ""
    key = ref[4:] if ref.lower().startswith("env:") else ref
    try:
        value = os.environ.get(key)
        if value:
            return value
    except Exception:
        pass
    try:
        import streamlit as st
        for section in ("connector_secrets", "secrets", "authentication"):
            try:
                section_value = st.secrets.get(section, {})
                if isinstance(section_value, Mapping) and key in section_value:
                    return str(section_value[key])
            except Exception:
                continue
        try:
            return str(st.secrets.get(key, ""))
        except Exception:
            return ""
    except Exception:
        return ""


def _record_connector_run(
    username: str,
    connector_id: str,
    operation: str,
    status: str,
    latency_ms: float,
    detail: str,
    records: int,
    started: datetime,
    finished: datetime,
    workspace: str = "default",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    run_id = "CRUN-" + uuid.uuid4().hex[:12].upper()
    values = (
        run_id, wid, connector_id, str(operation), str(status),
        float(latency_ms), str(detail)[:500], int(max(0, records)),
        started.isoformat(), finished.isoformat(),
    )
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.connector_runs
                    (run_id,workspace_id,connector_id,operation,status,latency_ms,detail,records,started_at,finished_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    values,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_connector_runs
                (run_id,workspace_id,connector_id,operation,status,latency_ms,detail,records,started_at,finished_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            conn.commit()
    return run_id


def connector_run_frame(username: str, workspace: str = "default", limit: int = 200) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.connector_runs" if _remote() else "shoir_ent_connector_runs"
    sql = (
        "SELECT * FROM " + table +
        (" WHERE workspace_id=%s" if _remote() else " WHERE workspace_id=?") +
        " ORDER BY started_at DESC LIMIT " + str(max(1, min(1000, int(limit))))
    )
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def _connector_sql_test(endpoint: str, timeout: float = 8.0) -> tuple[str, float, str, int]:
    started = datetime.now(timezone.utc)
    target = str(endpoint or "").strip()
    if target.lower().startswith("sqlite:///"):
        db_path = target[10:]
        try:
            with sqlite3.connect(db_path, timeout=max(1.0, float(timeout))) as conn:
                row = conn.execute("SELECT 1").fetchone()
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
            return "Healthy", elapsed, "SQLite connection validated.", int(bool(row))
        except sqlite3.Error as exc:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
            return "Offline", elapsed, f"{type(exc).__name__}: {str(exc)[:220]}", 0
    if target.lower().startswith(("postgresql://", "postgres://")):
        try:
            import psycopg2
            conn = psycopg2.connect(target, connect_timeout=max(1, int(timeout)))
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    row = cur.fetchone()
            finally:
                conn.close()
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
            return "Healthy", elapsed, "PostgreSQL connection validated.", int(bool(row))
        except Exception as exc:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
            return "Offline", elapsed, f"{type(exc).__name__}: {str(exc)[:220]}", 0
    elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
    return "Configuration Error", elapsed, "SQL adapter supports sqlite:/// and PostgreSQL DSNs.", 0


def _connector_mqtt_test(endpoint: str, username: str = "", password: str = "", timeout: float = 8.0) -> tuple[str, float, str, int]:
    started = datetime.now(timezone.utc)
    target = str(endpoint or "").strip()
    try:
        import paho.mqtt.client as mqtt
    except Exception:
        return "Dependency Missing", 0.0, "Install paho-mqtt to enable live MQTT adapter tests.", 0
    try:
        from urllib.parse import urlparse
        parsed = urlparse(target if "://" in target else "mqtt://" + target)
        host = parsed.hostname or ""
        port = parsed.port or (8883 if parsed.scheme == "mqtts" else 1883)
        client = mqtt.Client()
        if username:
            client.username_pw_set(username, password or None)
        client.connect(host, port, keepalive=max(5, int(timeout)))
        client.disconnect()
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        return "Healthy", elapsed, f"MQTT broker {host}:{port} accepted a connection.", 1
    except Exception as exc:
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        return "Offline", elapsed, f"{type(exc).__name__}: {str(exc)[:220]}", 0


def _connector_opcua_test(endpoint: str, timeout: float = 8.0) -> tuple[str, float, str, int]:
    started = datetime.now(timezone.utc)
    try:
        from opcua import Client
    except Exception:
        return "Dependency Missing", 0.0, "Install opcua to enable live OPC-UA adapter tests.", 0
    client = None
    try:
        client = Client(str(endpoint), timeout=max(1.0, float(timeout)))
        client.connect()
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        return "Healthy", elapsed, "OPC-UA session handshake validated.", 1
    except Exception as exc:
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        return "Offline", elapsed, f"{type(exc).__name__}: {str(exc)[:220]}", 0
    finally:
        try:
            if client is not None:
                client.disconnect()
        except Exception:
            pass


def test_connector_profile(
    username: str,
    name: str,
    system_type: str,
    protocol: str,
    endpoint: str,
    secret_ref: str = "",
    workspace: str = "default",
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Run one opt-in connector smoke test and persist the result."""
    validation = validate_connector_profile(system_type, protocol, endpoint)
    if not validation.get("valid"):
        connector_id = record_connector_health(
            username,
            name,
            system_type,
            protocol,
            endpoint,
            "Configuration Error",
            "; ".join(validation.get("errors", [])),
            0.0,
            workspace,
            secret_ref=secret_ref,
        )
        return {
            "connector_id": connector_id,
            "run_id": "",
            "status": "Configuration Error",
            "latency_ms": 0.0,
            "detail": "; ".join(validation.get("errors", [])),
            "records": 0,
        }

    secret = resolve_connector_secret(secret_ref)
    started = datetime.now(timezone.utc)
    pr = str(protocol).strip().upper()
    if pr in {"REST", "ODATA", "HTTPS"}:
        status, latency, detail = check_rest_connector(endpoint, secret, timeout)
        records = 1 if status == "Healthy" else 0
    elif pr in {"SQL", "JDBC"}:
        status, latency, detail, records = _connector_sql_test(endpoint, timeout)
    elif pr == "MQTT":
        status, latency, detail, records = _connector_mqtt_test(endpoint, username if secret else "", secret, timeout)
    elif pr == "OPC-UA":
        status, latency, detail, records = _connector_opcua_test(endpoint, timeout)
    else:
        status, latency, detail, records = "Configuration Error", 0.0, "No executable adapter is registered for this protocol.", 0

    finished = datetime.now(timezone.utc)
    connector_id = record_connector_health(
        username, name, system_type, protocol, endpoint, status, detail,
        float(latency), workspace, secret_ref=secret_ref,
    )
    run_id = _record_connector_run(
        username, connector_id, "test", status, float(latency), detail,
        int(records), started, finished, workspace,
    )
    return {
        "connector_id": connector_id,
        "run_id": run_id,
        "status": status,
        "latency_ms": round(float(latency), 1),
        "detail": detail,
        "records": int(records),
        "adapter": CONNECTOR_PROTOCOLS.get(pr, pr),
        "secret_ref_used": bool(secret_ref),
    }


def infer_canonical_schema(frame: pd.DataFrame) -> dict[str, str]:
    """Map observed source fields to canonical industrial roles without renaming data silently."""
    if not isinstance(frame, pd.DataFrame):
        return {}
    aliases = {
        "asset_id": ("asset", "asset_id", "machine", "equipment", "workcenter", "work_center", "node"),
        "product_id": ("product", "product_id", "sku", "part", "item"),
        "material_id": ("material", "material_id", "component", "raw_material"),
        "order_id": ("order", "order_id", "work_order", "sales_order", "purchase_order"),
        "operator_id": ("operator", "employee", "employee_id", "worker", "technician"),
        "process": ("process", "operation", "activity", "route"),
        "quality_metric": ("quality", "defect", "scrap", "yield", "inspection"),
        "maintenance_metric": ("maintenance", "downtime", "mtbf", "mttr", "rul", "failure"),
        "energy_metric": ("energy", "kwh", "electricity", "power"),
        "cost_metric": ("cost", "price", "opex", "capex", "expense"),
        "scenario": ("scenario", "case", "variant", "alternative"),
    }
    result = {}
    for role, terms in aliases.items():
        for column in frame.columns:
            lowered = str(column).lower().replace("-", "_").replace(" ", "_")
            if any(term in lowered for term in terms):
                result[role] = str(column)
                break
    return result


def _safe_read_sql_query(query: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(query or "").strip().lower())
    if not re.match(r"^(select|with)\b", normalized):
        return False
    if ";" in normalized.rstrip(";"):
        return False
    return not bool(re.search(r"\b(insert|update|delete|drop|alter|create|truncate|attach|detach|pragma|vacuum|grant|revoke)\b", normalized))


def fetch_connector_sample(
    username: str,
    connector_id: str,
    protocol: str,
    endpoint: str,
    secret_ref: str = "",
    query: str = "",
    workspace: str = "default",
    limit: int = 1000,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Read a bounded sample from supported REST/SQL connectors and persist it with lineage."""
    limit = max(1, min(10000, int(limit)))
    started = datetime.now(timezone.utc)
    proto = str(protocol or "").strip().upper()
    secret = resolve_connector_secret(secret_ref)
    frame = pd.DataFrame()
    detail = ""
    status = "Configuration Error"
    if proto in {"REST", "ODATA", "HTTPS"}:
        try:
            response = requests.get(str(endpoint).strip(), headers={"Authorization":"Bearer "+secret} if secret else {}, timeout=max(1.0, float(timeout)))
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                frame = pd.json_normalize(payload).head(limit)
            elif isinstance(payload, dict):
                rows = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("results")
                if isinstance(rows, list):
                    frame = pd.json_normalize(rows).head(limit)
                else:
                    frame = pd.DataFrame([payload]).head(limit)
            else:
                raise ValueError("Response body is not JSON object/array data.")
            status = "Healthy"
            detail = f"Fetched {len(frame):,} record(s) from the REST endpoint."
        except Exception as exc:
            detail = f"{type(exc).__name__}: {str(exc)[:300]}"
            status = "Offline" if isinstance(exc, requests.RequestException) else "Read Error"
    elif proto in {"SQL", "JDBC"}:
        if not _safe_read_sql_query(query):
            detail = "Only a single read-only SELECT/WITH query is allowed for connector samples."
        else:
            bounded_query = "SELECT * FROM (" + str(query).strip().rstrip(";") + f") AS shoir_sample LIMIT {limit}"
            try:
                target = str(endpoint).strip()
                if target.lower().startswith("sqlite:///"):
                    db_path = target[10:]
                    with sqlite3.connect(db_path, timeout=max(1.0, float(timeout))) as conn:
                        frame = pd.read_sql_query(bounded_query, conn)
                elif target.lower().startswith(("postgresql://", "postgres://")):
                    import psycopg2
                    conn = psycopg2.connect(target, connect_timeout=max(1, int(timeout)))
                    try:
                        frame = pd.read_sql_query(bounded_query, conn)
                    finally:
                        conn.close()
                else:
                    raise ValueError("SQL sample adapter supports sqlite:/// and PostgreSQL DSNs.")
                status = "Healthy"
                detail = f"Fetched {len(frame):,} record(s) from the SQL source."
            except Exception as exc:
                detail = f"{type(exc).__name__}: {str(exc)[:300]}"
                status = "Read Error"
    else:
        detail = "Sample reads are currently supported for REST/ODATA/HTTPS and SQL/JDBC adapters."
    finished = datetime.now(timezone.utc)
    mapping = infer_canonical_schema(frame)
    artifact_id = ""
    if status == "Healthy" and not frame.empty:
        artifact_id = persist_dataframe_artifact(username, "Industrial Connectivity Hub", "connector_sample_"+connector_id, frame, workspace, limit)
        record_artifact(username, "connector_schema_mapping", connector_id, {"connector_id":connector_id, "mapping":mapping, "columns":[str(x) for x in frame.columns], "artifact_id":artifact_id}, workspace)
    _record_connector_run(username, connector_id, "sample_read", status, (finished-started).total_seconds()*1000.0, detail, len(frame), started, finished, workspace)
    return {
        "status": status,
        "detail": detail,
        "records": int(len(frame)),
        "artifact_id": artifact_id,
        "schema_mapping": mapping,
        "frame": frame,
    }

def schedule_connector_sync(
    username: str,
    connector_id: str,
    interval_minutes: int,
    workspace: str = "default",
    enabled: bool = True,
) -> str:
    """Persist connector synchronization cadence; execution is handled by the job backend."""
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    schedule_id = "CSCH-" + uuid.uuid4().hex[:12].upper()
    interval = max(1, int(interval_minutes))
    now = datetime.now(timezone.utc)
    next_run = now + pd.Timedelta(minutes=interval) if enabled else None
    values = (
        schedule_id, wid, connector_id, interval, bool(enabled),
        next_run.isoformat() if next_run is not None else None,
        None, "Scheduled" if enabled else "Disabled", now_iso(),
    )
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.connector_schedules
                    (schedule_id,workspace_id,connector_id,interval_minutes,enabled,next_run_at,last_run_at,last_status,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    values,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_connector_schedules
                (schedule_id,workspace_id,connector_id,interval_minutes,enabled,next_run_at,last_run_at,last_status,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                values,
            )
            conn.commit()
    return schedule_id


def connector_schedule_frame(username: str, workspace: str = "default") -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.connector_schedules" if _remote() else "shoir_ent_connector_schedules"
    sql = "SELECT * FROM " + table + " WHERE workspace_id=" + ("%s" if _remote() else "?") + " ORDER BY next_run_at ASC"
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def _update_connector_schedule_after_run(
    schedule_id: str,
    username: str,
    status: str,
    workspace: str = "default",
    interval_minutes: int = 60,
) -> None:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    next_run = (datetime.now(timezone.utc) + pd.Timedelta(minutes=max(1, int(interval_minutes)))).isoformat()
    table = "shoir_internal.connector_schedules" if _remote() else "shoir_ent_connector_schedules"
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""UPDATE {table}
                    SET last_run_at=%s,last_status=%s,next_run_at=CASE WHEN enabled THEN %s::timestamptz ELSE NULL END,updated_at=%s
                    WHERE schedule_id=%s AND workspace_id=%s""",
                    (now_iso(), str(status)[:120], next_run, now_iso(), schedule_id, wid),
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """UPDATE shoir_ent_connector_schedules
                SET last_run_at=?,last_status=?,next_run_at=?,updated_at=?
                WHERE schedule_id=? AND workspace_id=?""",
                (now_iso(), str(status)[:120], next_run, now_iso(), schedule_id, wid),
            )
            conn.commit()


def run_due_connector_syncs(
    username: str,
    workspace: str = "default",
    max_attempts: int = 3,
    require_approval: bool = True,
) -> pd.DataFrame:
    """Execute due connector health checks with bounded retry and no secret persistence."""
    if require_approval:
        enforce_action_gate(username, "connector_sync", workspace, require_approval=True)
    schedules = connector_schedule_frame(username, workspace)
    if schedules.empty:
        return pd.DataFrame(columns=["Schedule ID","Connector ID","Status","Attempts","Detail"])
    now = datetime.now(timezone.utc)
    due = schedules[
        schedules["enabled"].astype(bool)
        & pd.to_datetime(schedules["next_run_at"], errors="coerce", utc=True).le(now)
    ].copy()
    results = []
    for _, row in due.iterrows():
        connector_id = str(row["connector_id"])
        health = connector_health_frame(username, workspace)
        connector = health[health["connector_id"].astype(str).eq(connector_id)] if "connector_id" in health.columns else pd.DataFrame()
        if connector.empty:
            results.append({"Schedule ID":row["schedule_id"],"Connector ID":connector_id,"Status":"Review","Attempts":0,"Detail":"Connector health record not found."})
            continue
        record = connector.iloc[0]
        attempts = 0
        status = "Offline"
        detail = "No attempt completed."
        for attempt in range(1, max(1, int(max_attempts)) + 1):
            attempts = attempt
            result = test_connector_profile(
                username,
                str(record.get("name","Connector")),
                str(record.get("system_type","REST")),
                str(record.get("protocol","REST")),
                str(record.get("endpoint","")),
                str(record.get("secret_ref","")),
                workspace,
                8.0,
            )
            status = str(result.get("status","Review"))
            detail = str(result.get("detail",""))
            if status == "Healthy":
                break
        interval = int(row.get("interval_minutes", 60) or 60)
        _update_connector_schedule_after_run(str(row["schedule_id"]), username, status, workspace, interval)
        record_canonical_event(
            username, "connector_sync",
            {"schedule_id":str(row["schedule_id"]),"connector_id":connector_id,"status":status,"attempts":attempts,"detail":detail[:300]},
            workspace=workspace,
        )
        results.append({"Schedule ID":row["schedule_id"],"Connector ID":connector_id,"Status":status,"Attempts":attempts,"Detail":detail})
    return pd.DataFrame(results, columns=["Schedule ID","Connector ID","Status","Attempts","Detail"])


def create_job_record(username: str, module: str, job_type: str, payload: Mapping[str, Any], workspace: str = "default") -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    jid = "JOB-" + uuid.uuid4().hex[:12].upper()
    stamp = now_iso()
    params = (jid, wid, str(module), str(job_type), "Queued", 0.0, "Queued", _json(payload), None, 0, False, False, stamp, None, None, stamp)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.jobs
                    (job_id,workspace_id,module,job_type,status,progress,message,payload_json,result_json,attempts,
                     cancel_requested,pause_requested,created_at,started_at,finished_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    params,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_jobs
                (job_id,workspace_id,module,job_type,status,progress,message,payload_json,result_json,attempts,
                 cancel_requested,pause_requested,created_at,started_at,finished_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                params,
            )
            conn.commit()
    return jid


def update_job_record(username: str, job_id: str, status: Optional[str] = None, progress: Optional[float] = None, message: Optional[str] = None, result: Any = None, workspace: str = "default") -> None:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    fields: list[str] = []
    values: list[Any] = []
    if status is not None:
        fields.append("status=" + ("%s" if _remote() else "?")); values.append(status)
    if progress is not None:
        fields.append("progress=" + ("%s" if _remote() else "?")); values.append(float(max(0, min(100, progress))))
    if message is not None:
        fields.append("message=" + ("%s" if _remote() else "?")); values.append(message)
    if result is not None:
        fields.append("result_json=" + ("%s" if _remote() else "?")); values.append(_json(result))
    if status == "Running":
        fields.append("started_at=COALESCE(started_at," + ("%s" if _remote() else "?") + ")"); values.append(now_iso())
    if status in {"Completed", "Failed", "Cancelled"}:
        fields.append("finished_at=" + ("%s" if _remote() else "?")); values.append(now_iso())
    fields.append("updated_at=" + ("%s" if _remote() else "?")); values.append(now_iso())
    if not fields:
        return
    values.extend([job_id, wid])
    table = "shoir_internal.jobs" if _remote() else "shoir_ent_jobs"
    where = "job_id=" + ("%s" if _remote() else "?") + " AND workspace_id=" + ("%s" if _remote() else "?")
    sql = "UPDATE " + table + " SET " + ",".join(fields) + " WHERE " + where
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        if _remote():
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()
        else:
            conn.execute(sql, values)
            conn.commit()


def _serialize_job_result(result: Any) -> Any:
    if isinstance(result, pd.DataFrame):
        return {"__type__": "dataframe", "value": result.to_json(orient="split", date_format="iso")}
    if isinstance(result, pd.Series):
        return {"__type__": "series", "value": result.to_json(date_format="iso")}
    return result


def _run_job_worker(username: str, job_id: str, task: Callable[[], Any], workspace: str) -> None:
    try:
        update_job_record(username, job_id, status="Running", progress=5, message="Worker started.", workspace=workspace)
        with _FUTURES_LOCK:
            future = _FUTURES.get(job_id)
        result = task()
        # A worker can still be completed deterministically even when cancel was
        # requested too late to interrupt a domain solver. We preserve the fact in
        # the message and expose a Cancelled state only before execution starts.
        update_job_record(
            username, job_id, status="Completed", progress=100,
            message="Worker completed." if result is not None else "Worker completed with no result.",
            result=_serialize_job_result(result), workspace=workspace
        )
    except Exception as exc:
        update_job_record(username, job_id, status="Failed", progress=100, message=type(exc).__name__ + ": " + str(exc)[:500], workspace=workspace)


def submit_background_job(username: str, module: str, job_type: str, payload: Mapping[str, Any], task: Callable[[], Any], workspace: str = "default") -> str:
    jid = create_job_record(username, module, job_type, payload, workspace)
    with _FUTURES_LOCK:
        _FUTURES[jid] = _EXECUTOR.submit(_run_job_worker, username, jid, task, workspace)
    return jid


def request_job_action(username: str, job_id: str, action: str, workspace: str = "default") -> bool:
    action = str(action).strip().lower()
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.jobs" if _remote() else "shoir_ent_jobs"
    if action not in {"cancel", "pause", "resume", "retry"}:
        return False
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        where = "job_id=" + ("%s" if _remote() else "?") + " AND workspace_id=" + ("%s" if _remote() else "?")
        if action in {"cancel", "pause"}:
            sets = "cancel_requested=" + ("%s" if _remote() else "?") + ",pause_requested=" + ("%s" if _remote() else "?") + ",updated_at=" + ("CURRENT_TIMESTAMP" if _remote() else "?")
            vals = [action == "cancel", action == "pause", job_id, wid]
            if not _remote():
                vals[2] = job_id
                vals[3] = wid
                vals[2:] = [job_id, wid]
            sql = "UPDATE " + table + " SET " + sets + " WHERE " + where
            if _remote():
                with conn.cursor() as cur: cur.execute(sql, vals)
                conn.commit()
            else:
                conn.execute(sql, [int(vals[0]), int(vals[1]), job_id, wid] if "CURRENT_TIMESTAMP" not in sql else [int(vals[0]), int(vals[1]), job_id, wid])
                conn.commit()
            return True
        if action == "resume":
            sql = "UPDATE " + table + " SET pause_requested=" + ("false" if _remote() else "0") + ",status=" + ("%s" if _remote() else "?") + ",updated_at=" + ("CURRENT_TIMESTAMP" if _remote() else "?") + " WHERE " + where
            vals = ["Running", job_id, wid] if _remote() else ["Running", now_iso(), job_id, wid]
            if _remote():
                with conn.cursor() as cur: cur.execute(sql, vals)
                conn.commit()
            else:
                conn.execute(sql, vals)
                conn.commit()
            return True
        if action == "retry":
            sql = "UPDATE " + table + " SET status=" + ("%s" if _remote() else "?") + ",progress=0,message=" + ("%s" if _remote() else "?") + ",attempts=attempts+1,cancel_requested=" + ("false" if _remote() else "0") + ",pause_requested=" + ("false" if _remote() else "0") + ",updated_at=" + ("CURRENT_TIMESTAMP" if _remote() else "?") + " WHERE " + where
            vals = ["Queued", "Retry requested", job_id, wid] if _remote() else ["Queued", "Retry requested", now_iso(), job_id, wid]
            if _remote():
                with conn.cursor() as cur: cur.execute(sql, vals)
                conn.commit()
            else:
                conn.execute(sql, vals)
                conn.commit()
            return True
    return False


def list_jobs(username: str, workspace: str = "default", limit: int = 200) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.jobs" if _remote() else "shoir_ent_jobs"
    sql = "SELECT * FROM " + table + (" WHERE workspace_id=%s" if _remote() else " WHERE workspace_id=?") + " ORDER BY updated_at DESC LIMIT " + str(max(1, min(1000, int(limit))))
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def add_collaboration_item(
    username: str,
    item_type: str,
    body: str,
    subject: str = "",
    assignee: str = "",
    reviewer: str = "",
    status: str = "Open",
    workspace: str = "default",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    iid = "COL-" + uuid.uuid4().hex[:12].upper()
    stamp = now_iso()
    params = (iid, wid, item_type, subject, body, username, assignee, reviewer, status, stamp, stamp)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.collaboration
                    (item_id,workspace_id,item_type,subject,body,actor,assignee,reviewer,status,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", params)
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_collaboration
                (item_id,workspace_id,item_type,subject,body,actor,assignee,reviewer,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", params)
            conn.commit()
    return iid


def collaboration_frame(username: str, workspace: str = "default") -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.collaboration" if _remote() else "shoir_ent_collaboration"
    sql = "SELECT * FROM " + table + (" WHERE workspace_id=%s" if _remote() else " WHERE workspace_id=?") + " ORDER BY updated_at DESC"
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def inspect_upload(filename: str, data: bytes, content_type: str = "") -> dict[str, Any]:
    """Static security scan for uploaded artifacts; never stores the raw bytes."""
    name = os.path.basename(str(filename or "")).strip()
    lower = name.lower()
    ext = os.path.splitext(lower)[1]
    reasons: list[str] = []
    if not name or name in {".", ".."}:
        reasons.append("Missing filename.")
    if any(token in str(filename) for token in ("\\x00", ".." + os.sep, "..\\", "../")):
        reasons.append("Path traversal characters detected.")
    if len(data) > MAX_UPLOAD_BYTES:
        reasons.append("File exceeds the 50 MB upload limit.")
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        reasons.append("File type is not allowed.")
    if any(part.startswith(".") and len(part) > 1 for part in name.split(".")[:-1]):
        reasons.append("Suspicious multi-extension filename.")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        reasons.append("PDF signature is invalid.")
    if ext in {".xlsx", ".xlsm", ".docx", ".pptx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                total = sum(max(0, int(i.file_size)) for i in zf.infolist())
                if total > MAX_UNPACKED_ARCHIVE_BYTES:
                    reasons.append("Archive expands beyond the configured unpacked-size limit.")
                for item in zf.infolist():
                    member = item.filename.replace("\\", "/")
                    if member.startswith("/") or "../" in member.split("/"):
                        reasons.append("Archive contains unsafe member path.")
                        break
        except zipfile.BadZipFile:
            reasons.append("Office container is not a valid ZIP package.")
    safe = not reasons
    return {
        "safe": safe,
        "filename": name,
        "content_type": content_type,
        "bytes": int(len(data)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "reasons": reasons,
    }


def upsert_security_policy(
    username: str,
    require_mfa: bool,
    oidc_provider: str = "",
    oidc_enabled: bool = False,
    retention_days: int = 365,
    workspace: str = "default",
) -> None:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    stamp = now_iso()
    vals = (wid, require_mfa, oidc_provider or None, oidc_enabled, int(max(1, retention_days)), username, stamp)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.security
                    (workspace_id,require_mfa,oidc_provider,oidc_enabled,retention_days,updated_by,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(workspace_id) DO UPDATE SET
                    require_mfa=EXCLUDED.require_mfa,oidc_provider=EXCLUDED.oidc_provider,
                    oidc_enabled=EXCLUDED.oidc_enabled,retention_days=EXCLUDED.retention_days,
                    updated_by=EXCLUDED.updated_by,updated_at=EXCLUDED.updated_at""",
                    vals,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_security
                (workspace_id,require_mfa,oidc_provider,oidc_enabled,retention_days,updated_by,updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                require_mfa=excluded.require_mfa,oidc_provider=excluded.oidc_provider,
                oidc_enabled=excluded.oidc_enabled,retention_days=excluded.retention_days,
                updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                vals,
            )
            conn.commit()


def security_access_check(username: str, action: str, workspace: str = "default", require_approval: bool = False) -> dict[str, Any]:
    """Return an explicit, non-mutating authorization decision for an operator action."""
    policy = security_policy(username, workspace)
    try:
        import streamlit as st
        role = str(st.session_state.get("current_role") or st.session_state.get("role") or "")
        mfa_verified = bool(
            st.session_state.get("mfa_verified")
            or st.session_state.get("auth_mfa_verified")
            or st.session_state.get("mfa_challenge_verified")
        )
    except Exception:
        role = ""
        mfa_verified = False
    reasons = []
    allowed = True
    try:
        current_user = str(st.session_state.get("current_user") or "")
    except Exception:
        current_user = ""
    if not role and current_user and current_user == str(username):
        role = "Owner"
    if not role:
        allowed = False
        reasons.append("No active workspace role is available.")
    if bool(policy.get("require_mfa")) and not mfa_verified:
        allowed = False
        reasons.append("Workspace policy requires MFA verification.")
    if require_approval and action in {"execute", "write", "approve", "connector_sync"}:
        try:
            approved = bool(st.session_state.get("decision_approved") or st.session_state.get("current_action_approved"))
        except Exception:
            approved = False
        if not approved:
            allowed = False
            reasons.append("Explicit human approval is required before this action.")
    return {
        "allowed": allowed,
        "action": str(action),
        "role": role,
        "workspace_id": workspace_key(username, workspace),
        "mfa_required": bool(policy.get("require_mfa")),
        "mfa_verified": mfa_verified,
        "reasons": reasons,
    }


def enforce_action_gate(
    username: str,
    action: str,
    workspace: str = "default",
    require_approval: bool = False,
) -> None:
    decision = security_access_check(username, action, workspace, require_approval=require_approval)
    if not decision.get("allowed"):
        raise PermissionError("Action blocked: " + " ".join(decision.get("reasons", [])))


def security_maturity_status(username: str, workspace: str = "default") -> pd.DataFrame:
    """Report implementation maturity without overstating provider-dependent controls."""
    policy = security_policy(username, workspace)
    try:
        import streamlit as st
        role_present = bool(st.session_state.get("current_role") or st.session_state.get("role"))
        mfa_verified = bool(st.session_state.get("mfa_verified") or st.session_state.get("auth_mfa_verified"))
    except Exception:
        role_present = False
        mfa_verified = False
    cloud = _remote()
    rows = [
        {"Control":"RBAC","State":"Verified" if role_present else "Configured","Evidence":"Active workspace role." if role_present else "Role model is present; runtime role not observed."},
        {"Control":"Workspace isolation","State":"Verified","Evidence":"Enterprise records are keyed by user + workspace."},
        {"Control":"Audit / artifacts","State":"Verified","Evidence":"Durable artifact and audit stores are available."},
        {"Control":"Cloud persistence","State":"Connected" if cloud else "Configured","Evidence":"Managed persistence configuration."},
        {"Control":"SSO / OIDC","State":"Connected" if bool(policy.get("oidc_enabled")) else "Configured","Evidence":"Provider policy flag; runtime provider enforcement is external."},
        {"Control":"MFA","State":"Connected" if bool(policy.get("require_mfa")) and mfa_verified else ("Configured" if bool(policy.get("require_mfa")) else "Not configured"),"Evidence":"Session verification is checked; secrets are never displayed."},
        {"Control":"Secure uploads","State":"Verified","Evidence":"Extension, size, archive traversal and signature checks."},
        {"Control":"Secrets","State":"Configured","Evidence":"Connector credentials use references rather than stored secret values."},
    ]
    return pd.DataFrame(rows)
def security_policy(username: str, workspace: str = "default") -> dict[str, Any]:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.security" if _remote() else "shoir_ent_security"
    sql = "SELECT * FROM " + table + (" WHERE workspace_id=%s" if _remote() else " WHERE workspace_id=?")
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        row = pd.read_sql_query(sql, conn, params=[wid])
    if row.empty:
        return {"workspace_id": wid, "require_mfa": False, "oidc_provider": "", "oidc_enabled": False, "retention_days": 365}
    return row.iloc[0].to_dict()


def add_knowledge_document(
    username: str,
    name: str,
    content: str,
    source_type: str = "text",
    tags: Sequence[str] = (),
    workspace: str = "default",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    clean = str(content or "")
    if len(clean) > 2_000_000:
        raise ValueError("Knowledge document is larger than the 2 MB text limit.")
    did = "KN-" + uuid.uuid4().hex[:12].upper()
    stamp = now_iso()
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    vals = (did, wid, str(name), clean, source_type, _json(list(tags)), digest, username, stamp, stamp)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.knowledge
                    (doc_id,workspace_id,name,content,source_type,tags_json,sha256,created_by,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_knowledge
                (doc_id,workspace_id,name,content,source_type,tags_json,sha256,created_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", vals)
            conn.commit()
    record_artifact(username, "knowledge_document", name, {"doc_id": did, "sha256": digest, "source_type": source_type}, workspace)
    return did


def search_knowledge(username: str, query: str, workspace: str = "default", limit: int = 20) -> pd.DataFrame:
    ensure_enterprise_schema()
    q = str(query or "").strip()
    if not q:
        return pd.DataFrame()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.knowledge" if _remote() else "shoir_ent_knowledge"
    if _remote():
        sql = "SELECT doc_id,name,source_type,tags_json,sha256,created_by,created_at,updated_at FROM " + table + " WHERE workspace_id=%s AND content ILIKE %s ORDER BY updated_at DESC LIMIT " + str(max(1,min(100,int(limit))))
        params = [wid, "%" + q + "%"]
    else:
        sql = "SELECT doc_id,name,source_type,tags_json,sha256,created_by,created_at,updated_at FROM " + table + " WHERE workspace_id=? AND content LIKE ? ORDER BY updated_at DESC LIMIT " + str(max(1,min(100,int(limit))))
        params = [wid, "%" + q + "%"]
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def profile_data_intelligence(df: pd.DataFrame, reference: Optional[pd.DataFrame] = None) -> dict[str, Any]:
    """Comprehensive deterministic profiling for Excel-first industrial data."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Data Intelligence expects a pandas DataFrame.")
    rows, cols = df.shape
    numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    date_like: list[str] = []
    ids: list[str] = []
    units: dict[str, str] = {}
    missing = int(df.isna().sum().sum()) if rows else 0
    duplicate_rows = int(df.duplicated().sum()) if rows else 0
    duplicate_columns = int(len(df.columns) - len(set(map(str, df.columns))))
    outliers: dict[str, int] = {}

    for column in df.columns:
        name = str(column)
        lname = name.lower()
        unit_match = re.search(r"(?:^|[ _])(?:unit|units)\s*[:=]\s*([^,]+)$|\(([^()]+)\)$", name)
        if unit_match:
            units[name] = str(unit_match.group(1) or unit_match.group(2) or "").strip()
        series = df[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            date_like.append(name)
        elif series.dtype == object:
            sample = series.dropna().astype(str).head(50)
            if len(sample) >= 5:
                parsed = pd.to_datetime(sample, errors="coerce")
                if float(parsed.notna().mean()) >= 0.8:
                    date_like.append(name)
        if rows:
            uniqueness = float(series.nunique(dropna=True)) / max(1, int(series.notna().sum()))
            if uniqueness >= 0.98 and ("id" in lname or "code" in lname or "sku" in lname or "key" in lname):
                ids.append(name)
        if pd.api.types.is_numeric_dtype(series):
            x = pd.to_numeric(series, errors="coerce").dropna()
            if len(x) >= 8:
                q1, q3 = x.quantile([0.25, 0.75]); iqr = q3 - q1
                if float(iqr) > 0:
                    mask = (x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr)
                    outliers[name] = int(mask.sum())

    missing_pct = (missing / max(1, rows * max(1, cols))) * 100
    duplicate_pct = (duplicate_rows / max(1, rows)) * 100
    outlier_cells = sum(outliers.values())
    score = max(0.0, min(100.0, 100 - min(30, missing_pct * 0.8) - min(20, duplicate_pct * 0.6) - min(20, outlier_cells / max(1, rows) * 2) - min(10, duplicate_columns * 5)))

    drift: dict[str, float] = {}
    if isinstance(reference, pd.DataFrame) and not reference.empty and not df.empty:
        shared = [c for c in df.columns if c in reference.columns and pd.api.types.is_numeric_dtype(df[c]) and pd.api.types.is_numeric_dtype(reference[c])]
        for c in shared:
            a = pd.to_numeric(reference[c], errors="coerce").dropna().to_numpy(dtype=float)
            b = pd.to_numeric(df[c], errors="coerce").dropna().to_numpy(dtype=float)
            if len(a) >= 10 and len(b) >= 10:
                edges = np.unique(np.quantile(a, np.linspace(0, 1, 11)))
                if len(edges) >= 3:
                    edges[0] = -np.inf; edges[-1] = np.inf
                    pa = np.histogram(a, bins=edges)[0].astype(float); pb = np.histogram(b, bins=edges)[0].astype(float)
                    pa = pa / max(pa.sum(), 1); pb = pb / max(pb.sum(), 1)
                    pa = np.clip(pa, 1e-6, None); pb = np.clip(pb, 1e-6, None)
                    drift[c] = float(np.sum((pb - pa) * np.log(pb / pa)))
    return {
        "rows": int(rows), "columns": int(cols), "numeric_columns": numeric,
        "date_like_columns": date_like, "id_columns": ids, "units": units,
        "missing_cells": missing, "missing_pct": round(missing_pct, 3),
        "duplicate_rows": duplicate_rows, "duplicate_row_pct": round(duplicate_pct, 3),
        "duplicate_columns": duplicate_columns, "outlier_counts": outliers,
        "drift_psi": {k: round(v, 6) for k, v in drift.items()},
        "data_quality_score": round(score, 1),
    }


def save_report_provenance(
    username: str,
    module: str,
    report_format: str,
    filename: str,
    source_hash: str = "",
    figure_hashes: Sequence[str] = (),
    artifact_ids: Sequence[str] = (),
    workspace: str = "default",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    rid = "REP-" + uuid.uuid4().hex[:12].upper()
    stamp = now_iso()
    vals = (rid, wid, str(module), str(report_format).upper(), str(filename), source_hash, _json(list(figure_hashes)), _json(list(artifact_ids)), username, stamp)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.report_provenance
                    (report_id,workspace_id,module,format,filename,source_hash,figure_hashes_json,artifact_ids_json,created_by,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_report_provenance
                (report_id,workspace_id,module,format,filename,source_hash,figure_hashes_json,artifact_ids_json,created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", vals)
            conn.commit()
    return rid


def build_research_paper_bundle(
    title: str,
    module: str,
    tables: Sequence[tuple[str, pd.DataFrame]],
    figures: Sequence[tuple[str, Any]] = (),
    provenance: Sequence[str] = (),
) -> bytes:
    """Build a reproducible LaTeX research bundle with chart images and tables."""
    safe_module = re.sub(r"[^A-Za-z0-9]+", "_", str(module)).strip("_").lower() or "module"
    buf = io.BytesIO()
    figure_names: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        latex: list[str] = [
            r"\documentclass[11pt]{article}",
            r"\usepackage[margin=1in]{geometry}",
            r"\usepackage{graphicx}",
            r"\usepackage{booktabs}",
            r"\usepackage{hyperref}",
            r"\title{" + str(title).replace("&", r"\&") + r"}",
            r"\date{" + now_iso().replace("+00:00", " UTC") + r"}",
            r"\begin{document}",
            r"\maketitle",
            r"\section*{Shoir-IE Research/Engineering Export}",
            "Module: " + str(module).replace("_", r"\_") + r"\\",
        ]
        if provenance:
            latex.append("Provenance: " + ", ".join(map(str, provenance)).replace("_", r"\_") + r"\\")
        for label, frame in tables:
            csv_name = safe_module + "_" + re.sub(r"[^A-Za-z0-9]+", "_", str(label)).strip("_").lower() + ".csv"
            data = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
            zf.writestr(csv_name, data.to_csv(index=False).encode("utf-8"))
            latex.append(r"\subsection*{" + str(label).replace("&", r"\&") + r"}")
            latex.append(r"Source table: \texttt{" + csv_name.replace("_", r"\_") + r"}\\")
            latex.append("Rows: " + str(len(data)) + r"\\")
        for idx, (label, fig) in enumerate(figures, 1):
            try:
                png = fig.to_image(format="png", width=1400, height=800, scale=2)
                fname = safe_module + "_figure_" + str(idx) + ".png"
                zf.writestr(fname, png)
                figure_names.append(fname)
                latex.extend([
                    r"\begin{figure}[htbp]",
                    r"\centering",
                    r"\includegraphics[width=0.96\linewidth]{" + fname + "}",
                    r"\caption{" + str(label).replace("&", r"\&") + r"}",
                    r"\end{figure}",
                ])
            except Exception:
                pass
        latex.extend([r"\section*{Reproducibility}", r"All data tables and successfully rendered figures are included in this bundle.", r"\end{document}"])
        zf.writestr(safe_module + "_research_paper.tex", "\n".join(latex).encode("utf-8"))
        manifest = {
            "module": module,
            "title": title,
            "generated_at": now_iso(),
            "provenance": list(provenance),
            "tables": [label for label, _ in tables],
            "figures": figure_names,
        }
        zf.writestr("provenance_manifest.json", _json(manifest).encode("utf-8"))
    return buf.getvalue()


def create_generic_audit_event(username: str, event_type: str, detail: str, workspace: str = "default") -> str:
    return record_artifact(username, "audit_event", event_type, {"detail": detail, "timestamp": now_iso()}, workspace)


def render_enterprise_integration_surface(module: str, username: str, tier: str) -> None:
    """Render shared enterprise capabilities inside the relevant existing module flow."""
    import streamlit as st
    import plotly.express as px

    workspace = str(
        st.session_state.get("shoir_workspace_name")
        or st.session_state.get("workspace")
        or st.session_state.get("active_workspace_name")
        or "default"
    )
    module = str(module)

    # Digital Twin: augment the existing twin with durable state, replay and what-if.
    if module in {"Live Industrial Digital Twin", "Digital Twin & Discrete-Event Simulation", "Predictive Maintenance Digital Twin", "Industrial Simulation Lab"}:
        st.markdown("### 🌐 Connected Digital Twin")
        twin = load_twin_state(username, workspace)
        if twin.empty:
            st.info("No live Digital Twin state is currently connected to this workspace. Import telemetry or synchronize a real source to activate the twin view.")
        t1,t2,t3,t4 = st.tabs(["Live State","What-if","Scenario Replay","Scenarios"])
        with t1:
            st.dataframe(twin, use_container_width=True, hide_index=True)
            if st.button("🔄 Synchronize current state", key="ent_twin_sync"):
                sid=save_twin_snapshot(username,twin.to_dict("records"),source="module_state",scenario_name="Live",workspace=workspace)
                st.success(f"Twin snapshot synchronized: {sid}")
        with t2:
            numeric=[c for c in twin.columns if pd.api.types.is_numeric_dtype(twin[c])]
            if numeric:
                changes={}
                cols=st.columns(min(3,max(1,len(numeric))))
                for i,c in enumerate(numeric[:6]):
                    with cols[i%len(cols)]:
                        changes[c]=st.number_input(f"Δ {c}",value=0.0,key=f"ent_twin_delta_{i}")
                if st.button("🧪 Run what-if",key="ent_twin_whatif"):
                    scenario,audit=twin_what_if(twin,changes)
                    st.dataframe(scenario,use_container_width=True,hide_index=True)
                    if not audit.empty: st.dataframe(audit,use_container_width=True,hide_index=True)
                    record_artifact(username,"digital_twin_what_if",module,{"changes":changes,"audit":audit.to_dict("records")},workspace)
        with t3:
            replay=twin_replay(username,workspace=workspace)
            st.dataframe(replay,use_container_width=True,hide_index=True)
        with t4:
            scenario_name=st.text_input("Scenario name","Capacity Shock",key="ent_twin_scenario_name")
            params=st.text_area("Scenario parameters JSON",'{"capacity_delta":-10}',key="ent_twin_scenario_params")
            if st.button("💾 Save twin scenario",key="ent_twin_save_scenario"):
                try:
                    save_twin_scenario(username,scenario_name,json.loads(params),parent_name="Live",workspace=workspace)
                    st.success("Scenario saved.")
                except Exception as exc: st.error(f"Scenario could not be saved: {exc}")
            st.dataframe(list_twin_scenarios(username,workspace),use_container_width=True,hide_index=True)

    # Control Tower: consume existing module/session state instead of duplicating it.
    if module in {"Industrial Control Center","Control Tower","Industrial Operating System"}:
        st.markdown("### 🛰️ Unified Industrial Control Tower")
        state={
            "Production":{"records":len(st.session_state.get("mes_wo_df",[])),"status":"Ready","kpi":"Production"},
            "Supply":{"records":len(st.session_state.get("customers_list",[])),"status":"Ready","kpi":"Demand nodes"},
            "Inventory":{"records":len(st.session_state.get("meio_data",[])) if isinstance(st.session_state.get("meio_data"),list) else 0,"status":"Ready","kpi":"MEIO"},
            "Quality":{"records":len(st.session_state.get("quality_df",[])) if isinstance(st.session_state.get("quality_df"),pd.DataFrame) else 0,"status":"Ready","kpi":"Quality"},
            "Maintenance":{"records":len(st.session_state.get("maint_df",[])) if isinstance(st.session_state.get("maint_df"),pd.DataFrame) else 0,"status":"Ready","kpi":"Maintenance"},
            "Transport":{"records":len(st.session_state.get("fleet_list",[])),"status":"Ready","kpi":"Fleet"},
            "Workforce":{"records":len(st.session_state.get("work_elements",[])) if isinstance(st.session_state.get("work_elements"),pd.DataFrame) else 0,"status":"Ready","kpi":"Work elements"},
            "Energy":{"records":len(st.session_state.get("energy_units",[])) if isinstance(st.session_state.get("energy_units"),pd.DataFrame) else 0,"status":"Ready","kpi":"Energy"},
            "Carbon":{"records":len(st.session_state.get("sustain_df",[])) if isinstance(st.session_state.get("sustain_df"),pd.DataFrame) else 0,"status":"Ready","kpi":"Carbon"},
        }
        health=build_control_tower_health(state)
        st.dataframe(health,use_container_width=True,hide_index=True)
        st.plotly_chart(px.bar(health,x="Area",y="Records",color="Health",title="Unified industrial health map"),use_container_width=True)

    # Connectivity: replace simulated success with explicit health state.
    if module == "Industrial Connectivity Hub":
        st.markdown("### 🔌 Connector Health & Governance")
        ch=connector_health_frame(username,workspace)
        st.dataframe(ch,use_container_width=True,hide_index=True)
        st.caption("Credentials are never persisted by this surface.")
        record_artifact(username,"connector_catalog",module,{"supported_systems":["SAP","Oracle","WMS","MES","ERP","SQL","REST","MQTT","OPC-UA"]},workspace)

    # Security: show real configuration state rather than claiming SSO/MFA is already active.
    if module == "Enterprise Security & Governance":
        st.markdown("### 🔐 Workspace Security Policy")
        policy=security_policy(username,workspace)
        st.json(policy)
        require=st.checkbox("Require MFA for this workspace",value=bool(policy.get("require_mfa")),key="ent_security_mfa")
        oidc=st.checkbox("Enable OIDC configuration",value=bool(policy.get("oidc_enabled")),key="ent_security_oidc")
        provider=st.text_input("OIDC provider identifier",value=str(policy.get("oidc_provider") or ""),key="ent_security_provider")
        if st.button("💾 Save security policy",key="ent_security_save"):
            upsert_security_policy(username,require,provider,oidc,int(policy.get("retention_days",365)),workspace)
            create_generic_audit_event(username,"security_policy_update","Enterprise security policy changed.",workspace)
            st.success("Security policy saved.")

    # Collaboration: shared comments, assignments and reviewer records.
    if module in {"Team Workspaces & RBAC","Enterprise Integration & Collaboration","Enterprise Integration","Collaboration Suite"}:
        st.markdown("### 👥 Collaboration & Review")
        c1,c2=st.columns(2)
        with c1:
            subject=st.text_input("Subject",key="ent_collab_subject")
            body=st.text_area("Comment / assignment",key="ent_collab_body")
            assignee=st.text_input("Assignee",key="ent_collab_assignee")
            reviewer=st.text_input("Reviewer",key="ent_collab_reviewer")
            if st.button("💬 Add collaboration item",key="ent_collab_add"):
                if body.strip():
                    add_collaboration_item(username,"comment",body,subject,assignee,reviewer,workspace=workspace)
                    st.success("Collaboration item saved.")
        with c2:
            st.dataframe(collaboration_frame(username,workspace),use_container_width=True,hide_index=True)

    # Knowledge layer: organizational context for Copilot and engineering modules.
    if module in {"AI Copilot","Advanced Engineering Copilot","Engineering Decision Center","Global Project & Digital Thread"}:
        st.markdown("### 📚 Engineering Knowledge Layer")
        query=st.text_input("Search SOPs, standards, manuals and engineering notes",key="ent_knowledge_query")
        if query.strip():
            st.dataframe(search_knowledge(username,query,workspace),use_container_width=True,hide_index=True)
        with st.expander("Add knowledge source"):
            name=st.text_input("Document name",key="ent_knowledge_name")
            content=st.text_area("Text / extracted content",key="ent_knowledge_content")
            tags=st.text_input("Tags",key="ent_knowledge_tags")
            if st.button("📚 Register knowledge",key="ent_knowledge_add"):
                if name.strip() and content.strip():
                    add_knowledge_document(username,name,content,"text",[x.strip() for x in tags.split(",") if x.strip()],workspace)
                    st.success("Knowledge source registered.")

    # Data intelligence is shared with Excel-first and data-platform workflows.
    if module in {"Industrial Data Platform","Engineering Validation Center","AI Copilot","Industrial Data Model & Digital Thread"}:
        df=st.session_state.get("data_platform_latest_df")
        if isinstance(df,pd.DataFrame) and not df.empty:
            st.markdown("### 🔍 Data Intelligence")
            reference=st.session_state.get("data_intelligence_reference")
            report=profile_data_intelligence(df,reference if isinstance(reference,pd.DataFrame) else None)
            a,b,c,d=st.columns(4)
            a.metric("Quality score",f'{report["data_quality_score"]:.1f}')
            b.metric("Missing cells",f'{report["missing_cells"]:,}')
            c.metric("Duplicates",f'{report["duplicate_rows"]:,}')
            d.metric("Outlier cells",f'{sum(report["outlier_counts"].values()):,}')
            st.json({"IDs":report["id_columns"],"Dates":report["date_like_columns"],"Units":report["units"],"Drift PSI":report["drift_psi"]})

    # Jobs: expose durable job history wherever long-running engineering work is managed.
    if module in {"Industrial Simulation Lab","Experiment Lab","Engineering Model Registry","Advanced Planning & Scheduling","AI Copilot"}:
        jobs=list_jobs(username,workspace)
        if not jobs.empty:
            with st.expander("🕐 Background Jobs & History",expanded=False):
                st.dataframe(jobs,use_container_width=True,hide_index=True)

    # Research Studio: preserve the existing Research Workspace and add reproducible paper packaging.
    if module in {"Experiment Lab","Statistical Hypothesis Testing","Literature & Citation Matrix","LaTeX Document Formatter"}:
        with st.expander("📝 Reproducible Research Package",expanded=False):
            st.caption("Uses the existing research protocol/run records; this adds a single provenance-aware package surface.")
            tables=[]
            for key,label in [("experiment_results","Experiment Results"),("experiment_df","Experiment Inputs"),("stats_result_df","Statistics")]:
                value=st.session_state.get(key)
                if isinstance(value,pd.DataFrame) and not value.empty: tables.append((label,value))
            if tables and st.button("📦 Build research-paper bundle",key="ent_research_bundle"):
                bundle=build_research_paper_bundle("Shoir-IE Research Export",module,tables,provenance=[str(st.session_state.get("sx_research_study_id","active-study"))])
                st.download_button("Download reproducible research bundle",bundle,"shoir_ie_research_bundle.zip","application/zip",key="ent_research_bundle_download")




_BASE_CONTROL_TOWER_HEALTH = build_control_tower_health


def build_control_tower_health(state: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    df = _BASE_CONTROL_TOWER_HEALTH(state)
    score_map = {"Healthy": 100, "Ready": 85, "Review": 65, "Attention": 35, "No Data": 0}
    df.insert(len(df.columns), "Health Score", df["Health"].map(score_map).fillna(50).astype(float))
    return df

# ---------------------------------------------------------------------------
# Enterprise Platform v2: orchestration, monitoring, evidence and integration
# ---------------------------------------------------------------------------
import inspect as _inspect
import time as _time


class JobCancelled(Exception):
    """Raised by cooperative background jobs when cancellation is requested."""


class JobContext:
    """Cooperative control channel for long-running Shoir-IE work."""

    def __init__(self, username: str, job_id: str, workspace: str = "default") -> None:
        self.username = username
        self.job_id = job_id
        self.workspace = workspace

    def _state(self) -> dict[str, Any]:
        frame = list_jobs(self.username, self.workspace, limit=20)
        if frame.empty or "job_id" not in frame.columns:
            return {}
        hit = frame.loc[frame["job_id"].astype(str).eq(self.job_id)]
        return hit.iloc[0].to_dict() if not hit.empty else {}

    @property
    def cancelled(self) -> bool:
        state = self._state()
        return bool(state.get("cancel_requested"))

    @property
    def paused(self) -> bool:
        state = self._state()
        return bool(state.get("pause_requested"))

    def checkpoint(self, message: str = "") -> None:
        state = self._state()
        if bool(state.get("cancel_requested")):
            raise JobCancelled("Cancellation requested by the workspace operator.")
        while bool(state.get("pause_requested")) and not bool(state.get("cancel_requested")):
            update_job_record(self.username, self.job_id, status="Paused", message=message or "Paused by operator.", workspace=self.workspace)
            _time.sleep(0.5)
            state = self._state()
        if bool(state.get("cancel_requested")):
            raise JobCancelled("Cancellation requested while the job was paused.")

    def progress(self, value: float, message: str = "") -> None:
        self.checkpoint(message)
        update_job_record(self.username, self.job_id, progress=float(value), message=message or None, workspace=self.workspace)


_BASE_RUN_JOB_WORKER = _run_job_worker
_JOB_TASKS: dict[str, Callable[..., Any]] = {}


def _run_job_worker_v2(username: str, job_id: str, task: Callable[..., Any], workspace: str) -> None:
    context = JobContext(username, job_id, workspace)
    try:
        context.checkpoint("Worker accepted.")
        update_job_record(username, job_id, status="Running", progress=5, message="Worker started.", workspace=workspace)
        with _FUTURES_LOCK:
            _FUTURES[job_id] = _FUTURES.get(job_id)
        try:
            signature = _inspect.signature(task)
            accepts_context = len([
                p for p in signature.parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]) >= 1
        except (TypeError, ValueError):
            accepts_context = False
        result = task(context) if accepts_context else task()
        context.checkpoint("Finalizing.")
        update_job_record(
            username,
            job_id,
            status="Completed",
            progress=100,
            message="Worker completed." if result is not None else "Worker completed with no result.",
            result=_serialize_job_result(result),
            workspace=workspace,
        )
    except JobCancelled as exc:
        update_job_record(username, job_id, status="Cancelled", progress=0, message=str(exc), workspace=workspace)
    except Exception as exc:
        update_job_record(
            username, job_id, status="Failed", progress=100,
            message=type(exc).__name__ + ": " + str(exc)[:500],
            workspace=workspace,
        )
    finally:
        with _FUTURES_LOCK:
            _FUTURES.pop(job_id, None)
            _JOB_TASKS.pop(job_id, None)


def submit_background_job(
    username: str,
    module: str,
    job_type: str,
    payload: Mapping[str, Any],
    task: Callable[..., Any],
    workspace: str = "default",
) -> str:
    jid = create_job_record(username, module, job_type, payload, workspace)
    with _FUTURES_LOCK:
        _JOB_TASKS[jid] = task
        _FUTURES[jid] = _EXECUTOR.submit(_run_job_worker_v2, username, jid, task, workspace)
    return jid


def request_job_action(
    username: str,
    job_id: str,
    action: str,
    workspace: str = "default",
) -> bool:
    """Perform a real cooperative job action and preserve the audit state."""
    normalized = str(action or "").strip().lower()
    if normalized not in {"cancel", "pause", "resume", "retry"}:
        return False

    frame = list_jobs(username, workspace, limit=1000)
    if frame.empty:
        return False
    hit = frame.loc[frame["job_id"].astype(str).eq(str(job_id))]
    if hit.empty:
        return False
    row = hit.iloc[0].to_dict()
    table = "shoir_internal.jobs" if _remote() else "shoir_ent_jobs"
    wid = workspace_key(username, workspace)

    def execute(sql: str, vals: list[Any]) -> None:
        with (_pg_connect() if _remote() else _local_connect()) as conn:
            if _remote():
                with conn.cursor() as cur:
                    cur.execute(sql, vals)
                conn.commit()
            else:
                conn.execute(sql, vals)
                conn.commit()

    placeholder = "%s" if _remote() else "?"
    where = f"job_id={placeholder} AND workspace_id={placeholder}"

    if normalized == "cancel":
        if str(row.get("status")) == "Queued":
            sql = f"UPDATE {table} SET status={placeholder},progress={placeholder},message={placeholder},cancel_requested={placeholder},updated_at={placeholder} WHERE {where}"
            vals = ["Cancelled", 0.0, "Cancelled before execution.", True, now_iso(), job_id, wid]
        else:
            sql = f"UPDATE {table} SET cancel_requested={placeholder},updated_at={placeholder} WHERE {where}"
            vals = [True, now_iso(), job_id, wid]
        execute(sql, vals)
        return True

    if normalized == "pause":
        sql = f"UPDATE {table} SET pause_requested={placeholder},status={placeholder},message={placeholder},updated_at={placeholder} WHERE {where}"
        vals = [True, "Paused", "Pause requested by operator.", now_iso(), job_id, wid]
        execute(sql, vals)
        return True

    if normalized == "resume":
        sql = f"UPDATE {table} SET pause_requested={placeholder},status={placeholder},message={placeholder},updated_at={placeholder} WHERE {where}"
        vals = [False, "Running", "Resume requested by operator.", now_iso(), job_id, wid]
        execute(sql, vals)
        return True

    task = _JOB_TASKS.get(str(job_id))
    if task is None:
        # The job may have survived a process restart; preserve the retry state
        # without pretending that an in-memory callable still exists.
        sql = f"UPDATE {table} SET status={placeholder},progress=0,message={placeholder},attempts=attempts+1,cancel_requested={placeholder},pause_requested={placeholder},updated_at={placeholder} WHERE {where}"
        execute(sql, vals=["Queued", "Retry queued; task will be re-submitted by the owning worker.", False, False, job_id, wid])
        return True

    sql = f"UPDATE {table} SET status={placeholder},progress=0,message={placeholder},attempts=attempts+1,cancel_requested={placeholder},pause_requested={placeholder},updated_at={placeholder} WHERE {where}"
    execute(sql, ["Queued", "Retry requested.", False, False, job_id, wid])
    with _FUTURES_LOCK:
        _FUTURES[job_id] = _EXECUTOR.submit(_run_job_worker_v2, username, job_id, task, workspace)
    return True


# Monitoring / streaming-style ingestion ------------------------------------------------

def record_monitoring_event(
    username: str,
    metric: str,
    value: float,
    status: str = "Normal",
    asset_id: str = "",
    rule_id: str = "",
    message: str = "",
    workspace: str = "default",
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    eid = "MON-" + uuid.uuid4().hex[:12].upper()
    stamp = now_iso()
    vals = (eid, wid, rule_id or None, asset_id or None, str(metric), float(value), str(status), str(message), stamp)
    table = "shoir_internal.monitoring_events" if _remote() else "shoir_ent_monitoring_events"
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""INSERT INTO {table}
                    (event_id,workspace_id,rule_id,asset_id,metric,value,status,message,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                f"""INSERT INTO {table}
                (event_id,workspace_id,rule_id,asset_id,metric,value,status,message,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", vals)
            conn.commit()
    return eid


def monitoring_events_frame(username: str, workspace: str = "default", limit: int = 2000) -> pd.DataFrame:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    table = "shoir_internal.monitoring_events" if _remote() else "shoir_ent_monitoring_events"
    placeholder = "%s" if _remote() else "?"
    sql = f"SELECT * FROM {table} WHERE workspace_id={placeholder} ORDER BY created_at DESC LIMIT " + str(max(1, min(5000, int(limit))))
    with (_pg_connect() if _remote() else _local_connect()) as conn:
        return pd.read_sql_query(sql, conn, params=[wid])


def analyze_telemetry(
    df: pd.DataFrame,
    timestamp_col: str = "",
    value_col: str = "",
    group_col: str = "",
    window: int = 20,
    z_threshold: float = 3.0,
) -> pd.DataFrame:
    """Detect deterministic rolling anomalies without dropping observations.

    A stable/zero-variance baseline is handled explicitly: a material change
    from that baseline is still an anomaly instead of becoming NaN and then
    being silently converted to zero.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    work = df.copy()
    timestamp_col = (
        timestamp_col
        if timestamp_col in work.columns
        else next(iter(_find_columns_like(work, ("timestamp", "time", "date"))), "")
    )
    value_col = (
        value_col
        if value_col in work.columns
        else next(iter(_find_columns_like(work, ("value", "reading", "measurement", "metric"))), "")
    )
    if not value_col:
        numeric = [c for c in work.columns if pd.api.types.is_numeric_dtype(work[c])]
        value_col = numeric[0] if numeric else ""
    if not value_col:
        return pd.DataFrame()

    if timestamp_col:
        work[timestamp_col] = pd.to_datetime(work[timestamp_col], errors="coerce")
        work = work.dropna(subset=[timestamp_col]).sort_values(timestamp_col)
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna(subset=[value_col])

    def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        prior = out[value_col].shift(1)
        size = max(3, int(window))
        roll_mean = prior.rolling(size, min_periods=3).mean()
        roll_std = prior.rolling(size, min_periods=3).std(ddof=1)

        out["Rolling Mean"] = roll_mean
        out["Rolling Std"] = roll_std

        eps = 1e-12
        std_ok = roll_std > eps
        raw_z = (out[value_col] - roll_mean) / roll_std.where(std_ok)
        raw_z = raw_z.replace([np.inf, -np.inf], np.nan)

        stable_baseline = (
            roll_mean.notna()
            & (~std_ok | roll_std.isna())
            & ((out[value_col] - roll_mean).abs() > np.maximum(eps, roll_mean.abs() * 1e-9))
        )
        z = raw_z.fillna(0.0)
        z = z.mask(stable_baseline, np.sign(out[value_col] - roll_mean) * (float(z_threshold) + 1.0))

        out["Z Score"] = z
        out["Anomaly"] = out["Z Score"].abs() >= float(z_threshold)
        return out

    group_key = group_col if group_col in work.columns else None
    if group_key:
        pieces = [score_frame(g) for _, g in work.groupby(group_key, dropna=False)]
        return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    return score_frame(work)




def _find_columns_like(df: pd.DataFrame, tokens: Sequence[str]) -> list[str]:
    out=[]
    for col in df.columns:
        lowered=str(col).lower().replace("_"," ")
        if any(t in lowered for t in tokens):
            out.append(str(col))
    return out


def evaluate_monitoring_rule(df: pd.DataFrame, metric_col: str, operator: str, threshold: float) -> pd.DataFrame:
    """Evaluate an explicit threshold rule and append a stable alert status."""
    if metric_col not in df.columns:
        raise ValueError(f"Metric column '{metric_col}' was not found.")
    out=df.copy()
    values=pd.to_numeric(out[metric_col],errors="coerce")
    op=str(operator).strip()
    if op==">": mask=values>float(threshold)
    elif op==">=": mask=values>=float(threshold)
    elif op=="<": mask=values<float(threshold)
    elif op=="<=": mask=values<=float(threshold)
    elif op=="==": mask=values==float(threshold)
    else: raise ValueError("Unsupported monitoring operator.")
    out["Alert"]=mask.fillna(False)
    out["Threshold"]=float(threshold)
    out["Rule Status"]=np.where(out["Alert"],"Attention","Normal")
    return out


def build_enterprise_visual_frames(module: str, username: str, workspace: str = "default") -> list[tuple[str, pd.DataFrame]]:
    """Collect enterprise-facing frames while reusing native module datasets."""
    import streamlit as st
    frames: list[tuple[str, pd.DataFrame]] = []
    m = str(module)

    try:
        if m in {"Live Industrial Digital Twin", "Digital Twin & Discrete-Event Simulation", "Predictive Maintenance Digital Twin", "Industrial Simulation Lab"}:
            twin = load_twin_state(username, workspace)
            if not twin.empty:
                frames.append(("Digital Twin Live State", twin))
            replay = twin_replay(username, workspace=workspace, limit=200)
            if not replay.empty:
                frames.append(("Digital Twin Replay", replay))

        if m in {"Industrial Control Center", "Control Tower", "Industrial Operating System"}:
            health_state = {
                "Production":{"records":len(st.session_state.get("mes_wo_df",[])),"status":"Ready","kpi":"Production"},
                "Supply":{"records":len(st.session_state.get("customers_list",[])),"status":"Ready","kpi":"Supply"},
                "Inventory":{"records":len(st.session_state.get("meio_data",[])) if isinstance(st.session_state.get("meio_data"),list) else 0,"status":"Ready","kpi":"Inventory"},
                "Quality":{"records":len(st.session_state.get("quality_df",[])) if isinstance(st.session_state.get("quality_df"),pd.DataFrame) else 0,"status":"Ready","kpi":"Quality"},
                "Maintenance":{"records":len(st.session_state.get("maint_df",[])) if isinstance(st.session_state.get("maint_df"),pd.DataFrame) else 0,"status":"Ready","kpi":"Maintenance"},
                "Transport":{"records":len(st.session_state.get("fleet_list",[])),"status":"Ready","kpi":"Transport"},
                "Workforce":{"records":len(st.session_state.get("work_elements",[])) if isinstance(st.session_state.get("work_elements"),pd.DataFrame) else 0,"status":"Ready","kpi":"Workforce"},
                "Energy":{"records":len(st.session_state.get("energy_units",[])) if isinstance(st.session_state.get("energy_units"),pd.DataFrame) else 0,"status":"Ready","kpi":"Energy"},
                "Carbon":{"records":len(st.session_state.get("sustain_df",[])) if isinstance(st.session_state.get("sustain_df"),pd.DataFrame) else 0,"status":"Ready","kpi":"Carbon"},
            }
            frames.append(("Control Tower Health", build_control_tower_health(health_state)))

        if m == "Industrial Connectivity Hub":
            frame = connector_health_frame(username, workspace)
            if not frame.empty:
                frames.append(("Connector Health", frame))

        if m in {"Team Workspaces & RBAC","Enterprise Integration & Collaboration","Enterprise Integration","Collaboration Suite"}:
            frame = collaboration_frame(username, workspace)
            if not frame.empty:
                frames.append(("Collaboration Activity", frame))

        if m in {"Enterprise Security & Governance"}:
            policy = security_policy(username, workspace)
            frames.append(("Security Policy", pd.DataFrame([policy])))

        if m in {"Industrial Data Platform","Engineering Validation Center","AI Copilot","Industrial Data Model & Digital Thread"}:
            df = st.session_state.get("data_platform_latest_df")
            if isinstance(df, pd.DataFrame) and not df.empty:
                report=profile_data_intelligence(df, st.session_state.get("data_intelligence_reference") if isinstance(st.session_state.get("data_intelligence_reference"),pd.DataFrame) else None)
                quality=pd.DataFrame([
                    {"Metric":"Data Quality Score","Value":report["data_quality_score"]},
                    {"Metric":"Missing %","Value":report["missing_pct"]},
                    {"Metric":"Duplicate Rows","Value":report["duplicate_rows"]},
                    {"Metric":"Outlier Cells","Value":sum(report["outlier_counts"].values())},
                    {"Metric":"Duplicate Columns","Value":report["duplicate_columns"]},
                ])
                frames.append(("Data Intelligence Profile", quality))

        if m in {"Industrial Simulation Lab","Experiment Lab","Engineering Model Registry","Advanced Planning & Scheduling","AI Copilot"}:
            jobs=list_jobs(username,workspace)
            if not jobs.empty:
                frames.append(("Background Jobs", jobs))

        if m in {"Experiment Lab","Statistical Hypothesis Testing","Literature & Citation Matrix","LaTeX Document Formatter"}:
            for key,label in [("experiment_results","Research Results"),("experiment_factorial_effects","Factor Effects"),("experiment_mc_results","Monte Carlo Results"),("stats_result_df","Statistics")]:
                value=st.session_state.get(key)
                if isinstance(value,pd.DataFrame) and not value.empty:
                    frames.append((label,value))

        if m in {"Capital Investment & Engineering Economics","Engineering Economics & Finance","Engineering Economics & Financial Analysis"}:
            for key,label in [("fin_cash_flows","Cash Flows"),("df_cf","Cash Flow Result"),("df_eua","Economic Life"),("df_dep","Depreciation")]:
                value=st.session_state.get(key)
                if isinstance(value,pd.DataFrame) and not value.empty:
                    frames.append((label,value))

        if m in {"Industrial Sustainability & LCA","Carbon Accounting"}:
            for key,label in [("sustain_df","Sustainability Inputs"),("sustain_result","Sustainability Result"),("carbon_latest_df","Carbon Metrics")]:
                value=st.session_state.get(key)
                if isinstance(value,pd.DataFrame) and not value.empty:
                    frames.append((label,value))

        if m in {"Workforce Engineering","Human Factors & Ergonomics","Human Factors"}:
            value=st.session_state.get("work_elements")
            if isinstance(value,pd.DataFrame) and not value.empty:
                frames.append(("Workforce / Human Factors", value))
            tasks=st.session_state.get("ergonomic_tasks")
            if isinstance(tasks,list) and tasks:
                frames.append(("Ergonomic Risk Register", pd.DataFrame(tasks)))

        if m == "Engineering Model Registry":
            registry=st.session_state.get("model_registry_df")
            if isinstance(registry,pd.DataFrame) and not registry.empty:
                frames.append(("Model Registry",registry))

        if m in {"Industrial Data Platform","Global Project & Digital Thread"}:
            artifacts=list_artifacts(username,workspace=workspace,limit=200)
            if not artifacts.empty:
                frames.append(("Persistent Artifacts",artifacts))
    except Exception:
        # Visualization is observational infrastructure; a visualization error
        # must never prevent the underlying engineering module from rendering.
        return frames
    return frames


def _render_enterprise_visual_evidence(module: str, username: str, workspace: str = "default") -> None:
    import streamlit as st
    try:
        from shoir_live_visuals import build_visualization_suite
    except Exception as exc:
        st.caption(f"Universal visualization engine unavailable: {type(exc).__name__}")
        return

    frames = build_enterprise_visual_frames(module, username, workspace)
    if not frames:
        return

    rendered = 0
    with st.expander("📈 Enterprise Evidence Graphs", expanded=False):
        st.caption("These views are generated from the existing module/enterprise datasets. No presentation-only observations are created.")
        for label, frame in frames:
            suite = build_visualization_suite(frame, context=label, max_figures=3)
            if not suite:
                continue
            st.markdown(f"#### {label}")
            for title, fig in suite:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False, "responsive": True})
                try:
                    fp = figure_hash(fig)
                    record_artifact(
                        username,
                        "figure_provenance",
                        title,
                        {"module": module, "dataset": label, "figure_hash": fp, "figure_json_sha256": fp},
                        workspace,
                    )
                except Exception:
                    pass
                try:
                    st.download_button(
                        "📥 Download exact figure · PNG",
                        data=fig.to_image(format="png", width=1600, height=900, scale=2),
                        file_name=re.sub(r"[^A-Za-z0-9]+","_",title).strip("_").lower()+".png",
                        mime="image/png",
                        key="ent_fig_png_"+hashlib.sha1((module+"|"+label+"|"+title).encode()).hexdigest()[:12],
                    )
                except Exception:
                    pass
                rendered += 1
                if rendered >= 15:
                    break
            if rendered >= 15:
                break


_BASE_ENTERPRISE_RENDER = render_enterprise_integration_surface


def render_enterprise_integration_surface(module: str, username: str, tier: str) -> None:
    """Keep the established enterprise surface and layer its evidence suite on top."""
    workspace = str(
        st.session_state.get("shoir_workspace_name")
        or st.session_state.get("workspace")
        or st.session_state.get("active_workspace_name")
        or "default"
    )
    _BASE_ENTERPRISE_RENDER(module, username, tier)
    _render_enterprise_visual_evidence(str(module), username, workspace)


def persist_dataframe_artifact(
    username: str,
    module: str,
    name: str,
    frame: pd.DataFrame,
    workspace: str = "default",
    max_rows: int = 10000,
) -> str:
    """Persist a bounded dataframe snapshot as a governed artifact."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    bounded = frame.head(max(1, min(10000, int(max_rows)))).copy()
    payload = {
        "module": str(module),
        "columns": [str(c) for c in bounded.columns],
        "rows": bounded.to_dict("records"),
        "row_count": int(len(bounded)),
    }
    return record_artifact(username, "dataset_snapshot", name, payload, workspace)


def data_intelligence_frame(report: Mapping[str, Any]) -> pd.DataFrame:
    """Convert the deterministic data-quality profile into chart-ready rows."""
    rows = [
        {"Metric": "Data Quality Score", "Value": float(report.get("data_quality_score", 0.0))},
        {"Metric": "Missing %", "Value": float(report.get("missing_pct", 0.0))},
        {"Metric": "Duplicate Row %", "Value": float(report.get("duplicate_row_pct", 0.0))},
        {"Metric": "Duplicate Columns", "Value": float(report.get("duplicate_columns", 0))},
        {"Metric": "Outlier Cells", "Value": float(sum(report.get("outlier_counts", {}).values()))},
    ]
    for col, drift in dict(report.get("drift_psi", {})).items():
        rows.append({"Metric": f"Drift PSI · {col}", "Value": float(drift)})
    return pd.DataFrame(rows)


def figure_hash(fig: Any) -> str:
    try:
        return hashlib.sha256(fig.to_json().encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(str(fig).encode("utf-8")).hexdigest()
