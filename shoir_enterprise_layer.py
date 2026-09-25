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


def _local_connect(db_path: str = DEFAULT_DB):
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
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
        latency_ms REAL, detail TEXT, checked_at TEXT NOT NULL, checked_by TEXT)""",
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
        latency_ms double precision, detail text, checked_at timestamptz NOT NULL, checked_by text)""",
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
]


def ensure_enterprise_schema(db_path: str = DEFAULT_DB) -> None:
    """Create the additive enterprise layer in private schema/local tables."""
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                for sql in REMOTE_DDL:
                    cur.execute(sql)
                cur.execute("REVOKE ALL ON SCHEMA shoir_internal FROM anon, authenticated")
                cur.execute("REVOKE ALL ON ALL TABLES IN SCHEMA shoir_internal FROM anon, authenticated")
            conn.commit()
        return
    with _local_connect(db_path) as conn:
        for sql in LOCAL_DDL:
            conn.execute(sql)
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
        " WHERE workspace_id=%s ORDER BY updated_at DESC LIMIT " % "%" if _remote() else
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
) -> str:
    ensure_enterprise_schema()
    wid = workspace_key(username, workspace)
    cid = "CONN-" + hashlib.sha256((wid + "|" + name + "|" + system_type + "|" + protocol).encode()).hexdigest()[:14].upper()
    stamp = now_iso()
    params = (cid, wid, name, system_type, protocol, endpoint, status, latency_ms, detail, stamp, username)
    if _remote():
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_internal.connector_health
                    (connector_id,workspace_id,name,system_type,protocol,endpoint,status,latency_ms,detail,checked_at,checked_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(connector_id) DO UPDATE SET
                    status=EXCLUDED.status,latency_ms=EXCLUDED.latency_ms,detail=EXCLUDED.detail,
                    checked_at=EXCLUDED.checked_at,checked_by=EXCLUDED.checked_by""",
                    params,
                )
            conn.commit()
    else:
        with _local_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_ent_connector_health
                (connector_id,workspace_id,name,system_type,protocol,endpoint,status,latency_ms,detail,checked_at,checked_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(connector_id) DO UPDATE SET
                status=excluded.status,latency_ms=excluded.latency_ms,detail=excluded.detail,
                checked_at=excluded.checked_at,checked_by=excluded.checked_by""",
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
    st = str(system_type or "").strip().upper()
    pr = str(protocol or "").strip().upper()
    ep = str(endpoint or "").strip()
    supported_systems = {"SAP", "ORACLE", "WMS", "MES", "ERP", "SQL", "REST", "MQTT", "OPC-UA"}
    supported_protocols = {"REST", "ODATA", "SQL", "JDBC", "MQTT", "OPC-UA", "HTTPS"}
    errors = []
    if st not in supported_systems:
        errors.append("Unsupported system type.")
    if pr not in supported_protocols:
        errors.append("Unsupported protocol profile.")
    if pr in {"REST", "ODATA", "HTTPS"} and ep and not re.match(r"^https?://", ep, flags=re.I):
        errors.append("HTTP-based endpoints must use http:// or https://.")
    if pr in {"MQTT"} and ep and not re.match(r"^(mqtt|mqtts)://", ep, flags=re.I):
        errors.append("MQTT endpoint should use mqtt:// or mqtts://.")
    if pr in {"OPC-UA"} and ep and not re.match(r"^opc.tcp://", ep, flags=re.I):
        errors.append("OPC-UA endpoint should use opc.tcp://.")
    return {"valid": not errors, "errors": errors, "system_type": st, "protocol": pr}


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
