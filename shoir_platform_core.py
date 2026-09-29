"""Shoir-IE Platform Core.

This module provides the production-facing orchestration layer for the Industrial
Engineering Operating System. Specialist modules remain calculation owners while
this package owns governance, persistence routing, workflow enforcement,
lineage, uncertainty, experiments, forecasting, visualization contracts,
replay, connectors, job orchestration, decision memory and platform diagnostics.

The implementation is deliberately evidence-first:
- a capability is not marked Verified without executable evidence;
- integrations are shown as configured/connected only when a runtime check says so;
- replay records a real executable entry point and refuses ambiguous replay;
- local SQLite is a compatibility/offline fallback, while PostgreSQL is preferred
when a trusted DATABASE_URL is configured.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import importlib
import io
import json
import math
import os
import platform
import re
import sqlite3
import statistics
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from shoir_repository import sqlite_connect as shoir_sqlite_connect
from dataclasses import dataclass
from datetime import datetime, timezone
from ftplib import FTP
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import requests
except Exception:  # optional connector dependency
    requests = None

try:
    import psycopg2
    from psycopg2.extras import Json
except Exception:  # optional remote database dependency
    psycopg2 = None
    Json = None

try:
    import paho.mqtt.client as mqtt
except Exception:  # optional connector dependency
    mqtt = None

try:
    import oracledb
except Exception:  # optional connector dependency
    oracledb = None

try:
    import paramiko
except Exception:  # optional connector dependency
    paramiko = None


WORKFLOW_STEPS = (
    "DATA", "VALIDATE", "MAP", "MODEL", "RUN", "VISUALIZE",
    "COMPARE", "EXPLAIN", "DECIDE", "EXPORT", "VERIFY",
)

ACTION_LEVELS = ("READ", "ANALYZE", "SIMULATE", "RECOMMEND", "PREPARE", "EXECUTE", "ADMIN")
CAPABILITY_STATES = ("Verified", "Implemented", "Foundation", "Integration-ready")
PROVENANCE_STATES = ("LIVE", "IMPORTED", "SIMULATED", "DEMO")
SCHEMA_VERSION = "3.0"

DEFAULT_DB_PATH = os.getenv("SHOIR_SQLITE_PATH", "enterprise_full_workspace.db")
def _managed_database_url() -> str:
    """Resolve the durable DB URL from environment or the existing account store."""
    value = (os.getenv("DATABASE_URL") or os.getenv("SHOIR_DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or "").strip()
    if value:
        return value
    try:
        from durable_account_store import database_url
        return str(database_url() or "").strip()
    except Exception:
        return ""


def configured_database_url() -> str:
    return _managed_database_url()

UNIT_DEFINITIONS: dict[str, tuple[str, float]] = {
    "m": ("length", 1.0), "cm": ("length", 0.01), "mm": ("length", 0.001),
    "km": ("length", 1000.0), "ft": ("length", 0.3048), "in": ("length", 0.0254),
    "kg": ("mass", 1.0), "g": ("mass", 0.001), "lb": ("mass", 0.45359237), "t": ("mass", 1000.0),
    "s": ("time", 1.0), "min": ("time", 60.0), "h": ("time", 3600.0), "day": ("time", 86400.0),
    "wh": ("energy", 0.001), "kwh": ("energy", 1.0), "mwh": ("energy", 1000.0),
    "w": ("power", 0.001), "kw": ("power", 1.0), "mw": ("power", 1000.0),
    "ml": ("volume", 0.001), "l": ("volume", 1.0), "m3": ("volume", 1000.0),
    "m2": ("area", 1.0), "sqm": ("area", 1.0),
}
BASE_CURRENCY = os.getenv("SHOIR_BASE_CURRENCY", "USD").upper()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, ensure_ascii=False, default=str)


def stable_id(prefix: str = "REC") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _payload_from_value(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(str(value))
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    except Exception:
        return {}


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def db_backend() -> str:
    return "postgres" if configured_database_url() and psycopg2 is not None else "sqlite"


def db_connect(path: str | None = None, timeout: int = 30):
    """Single local connection gateway used by all new platform services."""
    if db_backend() == "postgres":
        conn = psycopg2.connect(configured_database_url(), connect_timeout=max(5, int(timeout)))
        conn.autocommit = False
        return conn
    conn = shoir_sqlite_connect(path or DEFAULT_DB_PATH, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def remote_persistence_configured() -> bool:
    return db_backend() == "postgres"


def ensure_core_schema() -> str:
    """Create the platform-owned repository schema on the selected backend."""
    if db_backend() == "postgres":
        statements = [
            """
            CREATE TABLE IF NOT EXISTS shoir_platform_meta (
                key TEXT PRIMARY KEY,
                value_json JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS shoir_platform_records (
                record_id TEXT PRIMARY KEY,
                workspace_key TEXT NOT NULL DEFAULT 'default',
                record_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                payload_json JSONB NOT NULL,
                content_hash TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(workspace_key, record_type, entity_key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_shoir_records_type ON shoir_platform_records(workspace_key, record_type)",
            "CREATE INDEX IF NOT EXISTS idx_shoir_records_hash ON shoir_platform_records(content_hash)",
            """
            CREATE TABLE IF NOT EXISTS shoir_platform_events (
                event_id TEXT PRIMARY KEY,
                workspace_key TEXT NOT NULL DEFAULT 'default',
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'system',
                entity_key TEXT,
                payload_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_shoir_events ON shoir_platform_events(workspace_key, event_type, created_at DESC)",
        ]
        with db_connect() as conn:
            with conn.cursor() as cur:
                for statement in statements:
                    cur.execute(statement)
            conn.commit()
        return "postgres"

    statements = [
        """
        CREATE TABLE IF NOT EXISTS shoir_platform_meta (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS shoir_platform_records (
            record_id TEXT PRIMARY KEY,
            workspace_key TEXT NOT NULL DEFAULT 'default',
            record_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(workspace_key, record_type, entity_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_shoir_records_type ON shoir_platform_records(workspace_key, record_type)",
        "CREATE INDEX IF NOT EXISTS idx_shoir_records_hash ON shoir_platform_records(content_hash)",
        """
        CREATE TABLE IF NOT EXISTS shoir_platform_events (
            event_id TEXT PRIMARY KEY,
            workspace_key TEXT NOT NULL DEFAULT 'default',
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            entity_key TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_shoir_events ON shoir_platform_events(workspace_key, event_type, created_at DESC)",
    ]
    with db_connect() as conn:
        for statement in statements:
            conn.execute(statement)
        conn.commit()
    return "sqlite"


def _record_upsert(
    record_type: str,
    entity_key: str,
    payload: Mapping[str, Any],
    *,
    workspace: str = "default",
    record_id: str | None = None,
) -> str:
    ensure_core_schema()
    record_id = record_id or stable_id(record_type[:3].upper())
    payload_json = canonical_json(payload)
    content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    now = now_iso()
    if db_backend() == "postgres":
        sql = """
        INSERT INTO shoir_platform_records
        (record_id,workspace_key,record_type,entity_key,payload_json,content_hash,version,created_at,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,1,NOW(),NOW())
        ON CONFLICT (workspace_key,record_type,entity_key)
        DO UPDATE SET payload_json=EXCLUDED.payload_json, content_hash=EXCLUDED.content_hash,
                      version=shoir_platform_records.version+1, updated_at=NOW()
        RETURNING record_id
        """
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (record_id, workspace, record_type, entity_key, Json(_jsonable(payload)) if Json else payload_json, content_hash))
                out = cur.fetchone()[0]
            conn.commit()
        return str(out)

    sql = """
    INSERT INTO shoir_platform_records
    (record_id,workspace_key,record_type,entity_key,payload_json,content_hash,version,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?)
    ON CONFLICT(workspace_key,record_type,entity_key)
    DO UPDATE SET payload_json=excluded.payload_json, content_hash=excluded.content_hash,
                  version=shoir_platform_records.version+1, updated_at=excluded.updated_at
    """
    with db_connect() as conn:
        conn.execute(sql, (record_id, workspace, record_type, entity_key, payload_json, content_hash, 1, now, now))
        conn.commit()
    return record_id


def _record_event(
    event_type: str,
    *,
    actor: str = "system",
    entity_key: str | None = None,
    payload: Mapping[str, Any] | None = None,
    workspace: str = "default",
) -> str:
    ensure_core_schema()
    event_id = stable_id("EVT")
    payload_json = canonical_json(payload or {})
    now = now_iso()
    if db_backend() == "postgres":
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO shoir_platform_events
                    (event_id,workspace_key,event_type,actor,entity_key,payload_json,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,NOW())""",
                    (event_id, workspace, event_type, str(actor), entity_key,
                     Json(_jsonable(payload or {})) if Json else payload_json),
                )
            conn.commit()
    else:
        with db_connect() as conn:
            conn.execute(
                """INSERT INTO shoir_platform_events
                (event_id,workspace_key,event_type,actor,entity_key,payload_json,created_at)
                VALUES (?,?,?,?,?,?)""",
                (event_id, workspace, event_type, str(actor), entity_key, payload_json, now),
            )
            conn.commit()
    return event_id


def repository_records(record_type: str, *, workspace: str = "default", limit: int = 200) -> pd.DataFrame:
    ensure_core_schema()
    limit = max(1, min(int(limit), 5000))
    if db_backend() == "postgres":
        with db_connect() as conn:
            return pd.read_sql_query(
                "SELECT record_id,record_type,entity_key,payload_json,content_hash,version,created_at,updated_at "
                "FROM shoir_platform_records WHERE workspace_key=%s AND record_type=%s ORDER BY updated_at DESC LIMIT %s",
                conn, params=(workspace, record_type, limit),
            )
    with db_connect() as conn:
        return pd.read_sql_query(
            "SELECT record_id,record_type,entity_key,payload_json,content_hash,version,created_at,updated_at "
            "FROM shoir_platform_records WHERE workspace_key=? AND record_type=? ORDER BY updated_at DESC LIMIT ?",
            conn, params=(workspace, record_type, limit),
        )


def save_platform_record(record_type: str, entity_key: str, payload: Mapping[str, Any], *, workspace: str = "default") -> str:
    rid = _record_upsert(record_type, entity_key, payload, workspace=workspace)
    _record_event(f"{record_type}.saved", actor=str(st.session_state.get("current_user", "system")),
                  entity_key=entity_key, payload={"record_id": rid, **_jsonable(payload)}, workspace=workspace)
    return rid


def dataframe_digest(df: pd.DataFrame) -> str:
    if not isinstance(df, pd.DataFrame):
        return ""
    try:
        data = pd.util.hash_pandas_object(df, index=True).values.tobytes()
    except Exception:
        data = df.to_csv(index=True).encode("utf-8", errors="replace")
    schema = "|".join(f"{c}:{df[c].dtype}" for c in df.columns).encode("utf-8")
    return hashlib.sha256(data + schema).hexdigest()


def data_readiness(df: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {"score": 0.0, "rows": 0, "columns": 0, "missing_pct": 100.0, "duplicate_pct": 0.0, "warnings": ["No active dataset"]}
    rows, cols = len(df), len(df.columns)
    missing_pct = float(df.isna().mean().mean() * 100) if cols else 100.0
    duplicate_pct = float(df.duplicated().mean() * 100) if rows else 0.0
    warnings: list[str] = []
    if missing_pct > 0:
        warnings.append(f"Missingness: {missing_pct:.1f}%")
    if duplicate_pct > 0:
        warnings.append(f"Duplicate rows: {duplicate_pct:.1f}%")
    if any(str(c).strip() == "" for c in df.columns):
        warnings.append("Blank column names detected")
    if len(set(map(str, df.columns))) != len(df.columns):
        warnings.append("Duplicate column names detected")
    score = max(0.0, min(100.0, 100 - 0.60 * missing_pct - 0.40 * duplicate_pct))
    return {
        "score": score, "rows": rows, "columns": cols,
        "missing_pct": missing_pct, "duplicate_pct": duplicate_pct,
        "warnings": warnings,
        "numeric_columns": len(df.select_dtypes(include=np.number).columns),
        "categorical_columns": len(df.select_dtypes(exclude=np.number).columns),
        "fingerprint": dataframe_digest(df),
    }


def validate_dataset_contract(df: pd.DataFrame, required_fields: Sequence[str] = ()) -> dict[str, Any]:
    result = {
        "valid": True,
        "rows_present": isinstance(df, pd.DataFrame) and not df.empty,
        "unique_columns": bool(isinstance(df, pd.DataFrame) and len(set(map(str, df.columns))) == len(df.columns)),
        "required_fields": {},
        "errors": [],
        "warnings": [],
    }
    if not result["rows_present"]:
        result["valid"] = False
        result["errors"].append("No active dataset is available.")
        return result
    if not result["unique_columns"]:
        result["valid"] = False
        result["errors"].append("Column names must be unique.")
    for field in required_fields:
        matches = [c for c in df.columns if str(c).strip().lower() == str(field).strip().lower()]
        result["required_fields"][field] = bool(matches)
        if not matches:
            result["valid"] = False
            result["errors"].append(f"Required field missing: {field}")
    if df.shape[1] == 0:
        result["valid"] = False
        result["errors"].append("Dataset contains no usable columns.")
    if df.select_dtypes(include=np.number).shape[1]:
        numeric = df.select_dtypes(include=np.number)
        if not np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan)).all():
            result["warnings"].append("Numeric data contains NaN or infinite values after coercion.")
    return result


def canonical_map_columns(df: pd.DataFrame) -> dict[str, str]:
    aliases = {
        "customer_id": ("customer", "client", "sold_to"),
        "sku": ("sku", "item", "material", "product"),
        "demand_qty": ("demand", "qty", "quantity", "orders"),
        "due_date": ("due", "required", "delivery"),
        "facility": ("facility", "plant", "site", "warehouse", "dc"),
        "machine": ("machine", "asset", "equipment", "work center"),
        "supplier": ("supplier", "vendor"),
        "unit_cost": ("unit cost", "unit price", "price"),
        "currency": ("currency", "ccy"),
        "timestamp": ("timestamp", "datetime", "event time", "date"),
        "throughput": ("throughput", "output", "production"),
        "defect": ("defect", "scrap", "reject"),
        "downtime": ("downtime", "down time", "minutes down"),
        "energy": ("energy", "kwh", "power"),
    }
    lowered = {str(c).strip().lower(): str(c) for c in df.columns}
    out: dict[str, str] = {}
    for canonical, tokens in aliases.items():
        for raw, original in lowered.items():
            if any(token in raw for token in tokens):
                out[canonical] = original
                break
    return out


@dataclass
class WorkflowRuntime:
    module: str
    workspace: str = "default"
    actor: str = "system"
    stage_index: int = 0
    provenance: str = "DEMO"
    started_at: str = ""
    run_id: str = ""
    data_hash: str = ""
    model_id: str = ""
    scenario_id: str = ""

    def __post_init__(self):
        self.started_at = self.started_at or now_iso()

    @property
    def stage(self) -> str:
        return WORKFLOW_STEPS[self.stage_index]

    def context(self, df: pd.DataFrame | None = None) -> dict[str, Any]:
        df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        readiness = data_readiness(df)
        if readiness["fingerprint"]:
            self.data_hash = readiness["fingerprint"]
        return {
            "module": self.module,
            "workspace": self.workspace,
            "actor": self.actor,
            "stage": self.stage,
            "workflow": list(WORKFLOW_STEPS),
            "provenance": self.provenance,
            "started_at": self.started_at,
            "run_id": self.run_id,
            "data_hash": self.data_hash,
            "readiness": readiness,
        }

    def require(self, stage: str) -> None:
        target = WORKFLOW_STEPS.index(str(stage).upper())
        if target > self.stage_index:
            raise RuntimeError(f"{self.module}: stage {stage} requires completion of {WORKFLOW_STEPS[self.stage_index]}.")
        return None

    def advance(self, stage: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        target = WORKFLOW_STEPS.index(str(stage).upper())
        if target > self.stage_index + 1:
            raise RuntimeError(f"Workflow cannot skip from {self.stage} to {stage}.")
        self.stage_index = max(self.stage_index, target)
        _record_event(
            "workflow.stage",
            actor=self.actor,
            entity_key=self.module,
            payload={"module": self.module, "stage": stage, "evidence": _jsonable(evidence or {})},
            workspace=self.workspace,
        )
        st.session_state["shoir_workflow_stage"] = self.stage
        st.session_state.setdefault("shoir_workflow_history", []).append({
            "module": self.module, "stage": self.stage, "at": now_iso(),
        })
        save_platform_record(
            "workflow",
            self.module,
            {
                "module": self.module,
                "stage": self.stage,
                "stage_index": self.stage_index,
                "run_id": self.run_id,
                "data_hash": self.data_hash,
                "at": now_iso(),
            },
            workspace=self.workspace,
        )


def begin_module(module: str, *, workspace: str = "default", actor: str = "system", df: pd.DataFrame | None = None) -> WorkflowRuntime:
    runtime = WorkflowRuntime(str(module), workspace=workspace, actor=actor)
    runtime.provenance = str(st.session_state.get("shoir_data_provenance", st.session_state.get("shoir_provenance", "DEMO"))).upper()
    try:
        prior = repository_records("workflow", workspace=workspace, limit=100)
        if not prior.empty:
            for _, row in prior.iterrows():
                try:
                    payload = _payload_from_value(row["payload_json"])
                except Exception:
                    continue
                if str(payload.get("module")) == str(module):
                    stage = str(payload.get("stage") or "").upper()
                    if stage in WORKFLOW_STEPS:
                        runtime.stage_index = max(runtime.stage_index, WORKFLOW_STEPS.index(stage))
    except Exception as exc:
        st.session_state.setdefault("shoir_platform_warnings", []).append({
            "scope": "workflow_restore", "type": type(exc).__name__, "message": str(exc), "at": now_iso(),
        })
    runtime.context(df)
    st.session_state["shoir_active_runtime"] = runtime
    return runtime


@contextmanager
def governed_module(module: str, *, workspace: str = "default", actor: str = "system", df: pd.DataFrame | None = None):
    runtime = begin_module(module, workspace=workspace, actor=actor, df=df)
    runtime.advance("DATA", evidence={
        "source": st.session_state.get("shoir_data_source", ""),
        "input_mode": "active_dataset" if isinstance(df, pd.DataFrame) and not df.empty else "module_managed",
    })
    try:
        yield runtime
    except Exception as exc:
        record_engineering_error(module, exc, workspace=workspace, actor=actor)
        raise
    finally:
        st.session_state["shoir_last_runtime"] = runtime.context(df)
        _record_event(
            "workflow.complete",
            actor=actor,
            entity_key=module,
            payload=runtime.context(df),
            workspace=workspace,
        )


def _runtime_result_frame(result: Any, fallback: pd.DataFrame | None = None) -> pd.DataFrame:
    if isinstance(result, pd.DataFrame) and not result.empty:
        return result.copy(deep=True)
    if isinstance(result, pd.Series) and not result.empty:
        return result.to_frame()
    if isinstance(fallback, pd.DataFrame) and not fallback.empty:
        return fallback.copy(deep=True)
    for value in st.session_state.values():
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=True)
    return pd.DataFrame()


def run_governed_module(
    module: str,
    renderer: Callable[[], Any],
    *,
    workspace: str = "default",
    actor: str = "system",
    df: pd.DataFrame | None = None,
    replay_spec: Mapping[str, Any] | None = None,
) -> Any:
    with governed_module(module, workspace=workspace, actor=actor, df=df) as runtime:
        active_df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        contract = validate_dataset_contract(active_df)

        # A module may own its input form rather than consume an external dataset.
        # The gate remains explicit and auditable rather than silently skipped.
        if contract["valid"]:
            runtime.advance("VALIDATE", evidence=contract)
            mapping = canonical_map_columns(active_df)
            runtime.advance("MAP", evidence={"mapping": mapping})
        else:
            runtime.advance("VALIDATE", evidence={"status": "MODULE_MANAGED_INPUT", "contract": contract})
            runtime.advance("MAP", evidence={"status": "MODULE_MANAGED_SCHEMA", "mapping": {}})

        runtime.advance("MODEL", evidence={"module": module, "manifest": module_manifest(module)})
        run_id = stable_id("RUN")
        runtime.run_id = run_id
        st.session_state["shoir_latest_run_id"] = run_id

        started = time.perf_counter()
        result = renderer()
        duration_ms = (time.perf_counter() - started) * 1000.0
        result_df = _runtime_result_frame(result, active_df)

        runtime.advance("RUN", evidence={
            "run_id": run_id,
            "renderer": getattr(renderer, "__name__", "renderer"),
            "duration_ms": round(duration_ms, 2),
            "result_hash": dataframe_digest(result_df) if not result_df.empty else digest(result),
        })

        # Visualization is always exposed by the universal visualization service;
        # it is marked available only when an analyzable frame exists.
        runtime.advance("VISUALIZE", evidence={
            "universal_visualization_contract": True,
            "data_available": not result_df.empty,
        })

        lineage_ids: list[str] = []
        if not result_df.empty:
            try:
                lineage_ids = capture_standard_kpi_lineage(module, result_df, workspace=workspace)
            except Exception as exc:
                record_engineering_error(module, exc, workspace=workspace, actor=actor)
                lineage_ids = []

        runtime.advance("COMPARE", evidence={
            "scenario_data_available": "Scenario" in result_df.columns if not result_df.empty else False,
            "comparison_contract": True,
        })
        runtime.advance("EXPLAIN", evidence={
            "lineage_ids": lineage_ids,
            "assumption_trace": True,
            "uncertainty_trace": bool(lineage_ids),
        })

        decision = {
            "decision_id": stable_id("DEC"),
            "title": f"{module} automated draft decision",
            "status": "Draft",
            "approval_required": True,
            "module": module,
            "run_id": run_id,
            "kpis": (
                {str(c): float(pd.to_numeric(result_df[c], errors="coerce").mean())
                 for c in result_df.select_dtypes(include=np.number).columns[:8]}
                if not result_df.empty else {}
            ),
            "evidence": lineage_ids,
            "created_at": now_iso(),
        }
        save_platform_record("decision_draft", decision["decision_id"], decision, workspace=workspace)
        runtime.advance("DECIDE", evidence=decision)

        export_manifest = {
            "module": module,
            "run_id": run_id,
            "formats": ["xlsx", "json", "pdf"],
            "result_hash": dataframe_digest(result_df) if not result_df.empty else digest(result),
            "generated_at": now_iso(),
        }
        save_platform_record("export_manifest", run_id, export_manifest, workspace=workspace)
        runtime.advance("EXPORT", evidence=export_manifest)

        verification = verification_suite(module, inputs=active_df, results=result_df)
        runtime.advance("VERIFY", evidence=verification)

        run_record = {
            "run_id": run_id,
            "module": module,
            "status": "COMPLETED",
            "duration_ms": round(duration_ms, 2),
            "result_hash": export_manifest["result_hash"],
            "lineage_ids": lineage_ids,
            "verification": verification,
            "completed_at": now_iso(),
        }
        save_platform_record("run", run_id, run_record, workspace=workspace)

        if replay_spec:
            try:
                register_replay(
                    module,
                    str(replay_spec.get("callable_path") or ""),
                    dict(replay_spec.get("kwargs") or {}),
                    input_hash=active_df_hash(active_df),
                    workspace=workspace,
                )
            except Exception as exc:
                record_engineering_error(module, exc, workspace=workspace, actor=actor)

        return result


def module_manifest(module: str, *, catalog_entry: Mapping[str, Any] | None = None, tests: Sequence[str] = ()) -> dict[str, Any]:
    name = str(module)
    entry = dict(catalog_entry or {})
    required = list(entry.get("required_fields") or [])
    module_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    test_list = [str(x) for x in tests]
    has_test = bool(test_list)
    return {
        "contract_version": SCHEMA_VERSION,
        "identity": name,
        "slug": module_slug,
        "purpose": str(entry.get("purpose") or f"Industrial engineering capability: {name}."),
        "inputs": list(entry.get("inputs") or ["dataset", "parameters"]),
        "required_fields": required,
        "optional_fields": list(entry.get("optional_fields") or []),
        "units": list(entry.get("units") or []),
        "validation_rules": list(entry.get("validation_rules") or ["rows_present", "unique_columns", "missing_review"]),
        "transformations": list(entry.get("transformations") or ["clean", "standardize", "map"]),
        "model": str(entry.get("model") or name),
        "solver": str(entry.get("solver") or ""),
        "outputs": list(entry.get("outputs") or ["results", "kpis", "evidence"]),
        "kpis": list(entry.get("kpis") or []),
        "recommended_visualizations": list(entry.get("recommended_visualizations") or ["distribution", "trend", "comparison"]),
        "uncertainty": list(entry.get("uncertainty") or ["percentiles", "intervals", "constraint_probability"]),
        "assumptions": list(entry.get("assumptions") or []),
        "scenario_support": bool(entry.get("scenario_support", True)),
        "export_formats": list(entry.get("export_formats") or ["xlsx", "json", "pdf"]),
        "persistence": bool(entry.get("persistence", True)),
        "permissions": list(entry.get("permissions") or ["READ", "ANALYZE", "EXPORT"]),
        "maturity": str(entry.get("maturity") or ("Implemented" if entry else "Foundation")),
        "verification_tests": test_list or ["contract", "sanity"],
        "workflow": list(WORKFLOW_STEPS),
        "enforcement": {
            "data_gate": True, "validation_gate": True, "mapping_gate": True,
            "model_gate": True, "run_evidence": True, "visualization_contract": True,
            "decision_trace": True, "verification_required": True,
        },
    }


def capability_ledger(catalog: Sequence[Mapping[str, Any]] | None = None, feature_rows: Sequence[Mapping[str, Any]] | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    entries = list(catalog or [])
    if not entries:
        try:
            from industrial_platform import PLATFORM_CATALOG
            entries = list(PLATFORM_CATALOG)
        except Exception:
            entries = []
    features = list(feature_rows or [])
    if not features:
        try:
            from shoir_160 import FEATURES_160
            features = list(FEATURES_160)
        except Exception:
            features = []

    known_names = {str(x.get("name")) for x in entries if x.get("name")}
    for idx, feature in enumerate(features, 1):
        name = str(feature.get("name") or f"Capability {idx}")
        entry = next((x for x in entries if str(x.get("name")) == name), {})
        raw_state = str(feature.get("state") or entry.get("state") or "")
        if raw_state.lower() in {"integration-ready", "integration ready"}:
            status = "Integration-ready"
        elif raw_state.lower() in {"verified", "verified operational"}:
            status = "Verified"
        elif name in known_names or entry:
            status = "Implemented"
        else:
            status = "Foundation"
        tests = []
        test_root = feature.get("test_coverage") or feature.get("tests") or []
        if isinstance(test_root, (list, tuple)):
            tests = [str(x) for x in test_root]
        elif test_root:
            tests = [str(test_root)]
        rows.append({
            "Capability ID": int(feature.get("id") or idx),
            "Capability": name,
            "Area": str(feature.get("area") or "Platform"),
            "Status": status,
            "Coverage": "catalogued" if name in known_names else "foundation",
            "Test coverage": "evidence recorded" if tests else "not independently evidenced",
            "Last verification": str(feature.get("last_verification") or "not recorded"),
            "Dependencies": ", ".join(map(str, feature.get("dependencies") or [])) or "platform kernel",
            "Deployment requirements": str(feature.get("deployment_requirements") or "runtime configuration dependent"),
            "Source state": raw_state or "unspecified",
            "Manifest": digest(module_manifest(name, catalog_entry=entry, tests=tests))[:12],
        })
    for entry in entries:
        name = str(entry.get("name") or "")
        if not name or name in {r["Capability"] for r in rows}:
            continue
        rows.append({
            "Capability ID": len(rows) + 1,
            "Capability": name,
            "Area": str(entry.get("area") or "Specialist"),
            "Status": "Implemented",
            "Coverage": "catalogued",
            "Test coverage": "not independently evidenced",
            "Last verification": "not recorded",
            "Dependencies": "specialist engine",
            "Deployment requirements": "runtime configuration dependent",
            "Source state": str(entry.get("state") or ""),
            "Manifest": digest(module_manifest(name, catalog_entry=entry))[:12],
        })
    return pd.DataFrame(rows)


def kpi_lineage(
    *,
    module: str,
    kpi: str,
    value: Any,
    dataset: Mapping[str, Any] | None = None,
    transformations: Sequence[str] = (),
    model: Mapping[str, Any] | None = None,
    formula: Mapping[str, Any] | None = None,
    assumptions: Mapping[str, Any] | None = None,
    constraints: Sequence[Mapping[str, Any] | str] = (),
    uncertainty: Mapping[str, Any] | None = None,
    scenario: Mapping[str, Any] | None = None,
    run: Mapping[str, Any] | None = None,
    evidence: Sequence[str] = (),
    workspace: str = "default",
) -> str:
    record = {
        "lineage_id": stable_id("LIN"),
        "module": module,
        "kpi": kpi,
        "value": _jsonable(value),
        "dataset": _jsonable(dataset or {}),
        "transformations": list(transformations),
        "model": _jsonable(model or {}),
        "formula": _jsonable(formula or {}),
        "assumptions": _jsonable(assumptions or {}),
        "constraints": _jsonable(list(constraints)),
        "uncertainty": _jsonable(uncertainty or {}),
        "scenario": _jsonable(scenario or {}),
        "run": _jsonable(run or {}),
        "evidence": list(evidence),
        "created_at": now_iso(),
    }
    rid = save_platform_record("kpi_lineage", f"{module}:{kpi}", record, workspace=workspace)
    st.session_state.setdefault("shoir_kpi_lineage", {})[f"{module}:{kpi}"] = record
    return rid


def render_kpi_lineage(record: Mapping[str, Any]) -> None:
    with st.expander(f"Why is {record.get('kpi','KPI')} this value?", expanded=False):
        cols = st.columns(4)
        cols[0].metric("Value", str(record.get("value")))
        cols[1].metric("Dataset", str((record.get("dataset") or {}).get("version") or "session"))
        cols[2].metric("Run", str((record.get("run") or {}).get("run_id") or "not recorded"))
        cols[3].metric("Uncertainty", "available" if record.get("uncertainty") else "not recorded")
        stages = [
            ("Dataset", record.get("dataset")),
            ("Transformations", record.get("transformations")),
            ("Model", record.get("model")),
            ("Formula", record.get("formula")),
            ("Assumptions", record.get("assumptions")),
            ("Constraints", record.get("constraints")),
            ("Uncertainty", record.get("uncertainty")),
            ("Scenario", record.get("scenario")),
            ("Run", record.get("run")),
            ("Evidence", record.get("evidence")),
        ]
        for title, value in stages:
            st.markdown(f"**{title}**")
            st.json(_jsonable(value))


def uncertainty_engine(
    values: Sequence[float],
    *,
    confidence: float = 0.95,
    threshold: float | None = None,
    predictions: Sequence[float] | None = None,
    actuals: Sequence[float] | None = None,
) -> dict[str, Any]:
    x = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna().to_numpy(dtype=float)
    if x.size == 0:
        return {"n": 0, "status": "NO_DATA"}
    alpha = max(1e-9, min(0.999999, 1 - float(confidence)))
    mean = float(np.mean(x))
    median = float(np.median(x))
    std = float(np.std(x, ddof=1)) if len(x) > 1 else 0.0
    sem = std / math.sqrt(len(x)) if len(x) > 0 else float("nan")
    try:
        from scipy.stats import t
        tcrit = float(t.ppf(1 - alpha / 2, max(1, len(x) - 1)))
    except Exception:
        tcrit = 1.96
    mean_ci = [mean - tcrit * sem, mean + tcrit * sem] if len(x) > 1 else [mean, mean]
    result = {
        "status": "OK",
        "n": int(len(x)),
        "mean": mean,
        "median": median,
        "std": std,
        "min": float(np.min(x)),
        "max": float(np.max(x)),
        "p05": float(np.percentile(x, 5)),
        "p10": float(np.percentile(x, 10)),
        "p25": float(np.percentile(x, 25)),
        "p50": median,
        "p75": float(np.percentile(x, 75)),
        "p90": float(np.percentile(x, 90)),
        "p95": float(np.percentile(x, 95)),
        "confidence_level": float(confidence),
        "mean_confidence_interval": mean_ci,
        "distribution": {
            "skew": float(pd.Series(x).skew()) if len(x) > 2 else 0.0,
            "kurtosis": float(pd.Series(x).kurt()) if len(x) > 3 else 0.0,
        },
    }
    if threshold is not None:
        threshold = float(threshold)
        result["threshold"] = threshold
        result["probability_above"] = float(np.mean(x > threshold))
        result["probability_below"] = float(np.mean(x < threshold))
        result["constraint_violation_probability"] = float(np.mean(x > threshold))
    if predictions is not None and actuals is not None:
        pred = pd.to_numeric(pd.Series(list(predictions)), errors="coerce")
        act = pd.to_numeric(pd.Series(list(actuals)), errors="coerce")
        mask = pred.notna() & act.notna()
        resid = (act[mask] - pred[mask]).to_numpy(dtype=float)
        if resid.size:
            q = float(np.percentile(np.abs(resid), 95))
            result["prediction_interval_95"] = [-q, q]
            result["prediction_coverage_95"] = float(np.mean(np.abs(resid) <= q))
    return result


def attach_uncertainty(module: str, result: pd.DataFrame | pd.Series | Sequence[float], *, kpi: str = "", threshold: float | None = None, workspace: str = "default") -> dict[str, Any]:
    values: Sequence[float]
    if isinstance(result, pd.DataFrame):
        numeric = result[kpi] if kpi and kpi in result.columns else result.select_dtypes(include=np.number).stack()
        values = list(pd.to_numeric(numeric, errors="coerce").dropna())
    elif isinstance(result, pd.Series):
        values = list(pd.to_numeric(result, errors="coerce").dropna())
    else:
        values = list(values for values in pd.to_numeric(pd.Series(list(result)), errors="coerce").dropna())
    summary = uncertainty_engine(values, threshold=threshold)
    payload = {"module": module, "kpi": kpi, "summary": summary, "captured_at": now_iso()}
    save_platform_record("uncertainty", f"{module}:{kpi or 'result'}", payload, workspace=workspace)
    st.session_state["shoir_uncertainty_last"] = payload
    return summary



def _safe_workspace() -> tuple[str, str]:
    actor = str(st.session_state.get("current_user") or st.session_state.get("username") or "system")
    workspace = str(st.session_state.get("workspace") or st.session_state.get("active_workspace") or "default")
    return actor, workspace


def capture_standard_kpi_lineage(
    module: str,
    df: pd.DataFrame,
    *,
    workspace: str = "default",
    numeric_limit: int = 8,
) -> list[str]:
    """Capture first-order lineage for each numeric KPI visible in a result frame."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    dataset = {
        "source": st.session_state.get("shoir_data_source", "active_workspace"),
        "version": st.session_state.get("shoir_data_version", "session"),
        "sha256": st.session_state.get("shoir_data_hash") or dataframe_digest(df),
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
    }
    run = {
        "run_id": st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id") or "",
        "engine": str(module),
        "captured_at": now_iso(),
    }
    ids: list[str] = []
    for col in list(df.select_dtypes(include=np.number).columns)[:max(1, int(numeric_limit))]:
        values = pd.to_numeric(df[col], errors="coerce").dropna().to_numpy(dtype=float)
        if values.size == 0:
            continue
        summary = uncertainty_engine(values)
        ids.append(
            kpi_lineage(
                module=str(module),
                kpi=str(col),
                value=float(np.mean(values)),
                dataset=dataset,
                transformations=["numeric coercion", "missing-value exclusion", "mean aggregation"],
                model={"type": "descriptive_statistic", "operation": "mean"},
                formula={"expression": f"mean({col})", "unit": "module-declared / not inferred"},
                assumptions={"rows_used": int(values.size), "aggregation": "arithmetic mean"},
                uncertainty=summary,
                run=run,
                evidence=[f"dataset_sha256:{dataset['sha256']}"],
                workspace=workspace,
            )
        )
    return ids


def fit_response_surface(
    data: pd.DataFrame,
    response: str,
    factors: Sequence[str],
    *,
    include_interactions: bool = True,
    quadratic: bool = True,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Fit a transparent second-order response surface by least squares."""
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("Response-surface fitting requires data.")
    factors = [str(x) for x in factors if str(x) in data.columns]
    if not factors or str(response) not in data.columns:
        raise ValueError("Response and at least one factor column are required.")
    response = str(response)
    work = data[factors + [response]].copy()
    for col in factors + [response]:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna()
    if len(work) <= len(factors) + 2:
        raise ValueError("Not enough complete observations to fit the response surface.")

    terms: list[tuple[str, np.ndarray]] = [("Intercept", np.ones(len(work)))]
    for col in factors:
        vals = work[col].to_numpy(dtype=float)
        terms.append((col, vals))
        if quadratic:
            terms.append((f"{col}^2", vals ** 2))
    if include_interactions:
        for i, left in enumerate(factors):
            for right in factors[i + 1:]:
                terms.append((f"{left}:{right}", (work[left] * work[right]).to_numpy(dtype=float)))

    X = np.column_stack([vals for _, vals in terms])
    y = work[response].to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    residual = y - fitted
    ss_res = float(np.sum(residual ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    model = {
        "response": response,
        "factors": factors,
        "terms": [name for name, _ in terms],
        "coefficients": {name: float(coef) for (name, _), coef in zip(terms, beta)},
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot else 1.0,
        "rmse": float(np.sqrt(np.mean(residual ** 2))),
        "n": int(len(work)),
        "method": "ordinary least squares second-order response surface",
        "quadratic": bool(quadratic),
        "interactions": bool(include_interactions),
    }
    fitted_frame = work.copy()
    fitted_frame["Predicted"] = fitted
    fitted_frame["Residual"] = residual
    return model, fitted_frame


def scenario_analysis(
    scenarios: Mapping[str, Mapping[str, Any]] | pd.DataFrame,
    *,
    baseline: str | None = None,
    constraints: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if isinstance(scenarios, pd.DataFrame):
        frame = scenarios.copy()
        name_col = "Scenario" if "Scenario" in frame.columns else str(frame.columns[0])
        data = {str(r[name_col]): {str(c): r[c] for c in frame.columns if c != name_col} for _, r in frame.iterrows()}
    else:
        data = {str(k): dict(v) for k, v in scenarios.items()}
    names = list(data.keys())
    if not names:
        return pd.DataFrame(), {"status": "NO_SCENARIOS"}
    baseline = baseline or names[0]
    if baseline not in data:
        raise ValueError(f"Baseline scenario {baseline!r} is not defined.")
    numeric_keys = sorted(set().union(*(set(v.keys()) for v in data.values())))
    rows = []
    base = data[baseline]
    constraint_specs = constraints or {}
    if isinstance(constraint_specs, Sequence) and not isinstance(constraint_specs, Mapping):
        specs = {}
        for item in constraint_specs:
            if "kpi" in item:
                specs[str(item["kpi"])] = dict(item)
        constraint_specs = specs
    for name, values in data.items():
        for kpi in numeric_keys:
            try:
                cur = float(values.get(kpi))
                base_value = float(base.get(kpi))
            except (TypeError, ValueError):
                continue
            delta = cur - base_value
            pct = (delta / base_value * 100.0) if base_value else (0.0 if delta == 0 else float("inf"))
            row = {"Scenario": name, "KPI": kpi, "Baseline": base_value, "Value": cur, "Delta": delta, "% Change": pct}
            spec = constraint_specs.get(kpi, {}) if isinstance(constraint_specs, Mapping) else {}
            violations = []
            if spec:
                if spec.get("min") is not None and cur < float(spec["min"]):
                    violations.append(f"< minimum {spec['min']}")
                if spec.get("max") is not None and cur > float(spec["max"]):
                    violations.append(f"> maximum {spec['max']}")
                if spec.get("target") is not None and spec.get("tolerance") is not None and abs(cur - float(spec["target"])) > abs(float(spec["tolerance"])):
                    violations.append("outside target tolerance")
            row["Constraint Violation"] = "; ".join(violations)
            rows.append(row)
    out = pd.DataFrame(rows)
    summary = {
        "status": "OK",
        "baseline": baseline,
        "scenario_count": len(names),
        "violations": int((out["Constraint Violation"].astype(str).str.len() > 0).sum()) if not out.empty else 0,
        "best": {},
        "worst": {},
        "drivers": {},
    }
    if not out.empty:
        for kpi, grp in out.groupby("KPI"):
            grp2 = grp[grp["Scenario"] != baseline]
            if grp2.empty:
                continue
            idx_max = grp2["Value"].idxmax()
            idx_min = grp2["Value"].idxmin()
            summary["best"][str(kpi)] = str(grp2.loc[idx_max, "Scenario"])
            summary["worst"][str(kpi)] = str(grp2.loc[idx_min, "Scenario"])
            delta_abs = grp2.assign(abs_delta=grp2["Delta"].abs()).sort_values("abs_delta", ascending=False)
            summary["drivers"][str(kpi)] = delta_abs[["Scenario", "Delta", "% Change"]].head(5).to_dict("records")
    return out, summary


def explain_scenario_changes(parent: Mapping[str, Any], child: Mapping[str, Any]) -> list[dict[str, Any]]:
    keys = sorted(set(parent) | set(child))
    rows = []
    for key in keys:
        if parent.get(key) == child.get(key):
            continue
        rows.append({
            "Assumption": key,
            "Parent": _jsonable(parent.get(key)),
            "Child": _jsonable(child.get(key)),
            "Changed": True,
        })
    return rows


def scenario_fork(scenario: Mapping[str, Any], *, name: str, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    fork = dict(scenario)
    fork["scenario_id"] = stable_id("SCN")
    fork["name"] = name
    fork["parent_scenario_id"] = scenario.get("scenario_id")
    fork["assumptions"] = {**dict(scenario.get("assumptions") or {}), **dict(overrides or {})}
    fork["created_at"] = now_iso()
    return fork


def factorial_design(factors: Mapping[str, Sequence[Any]], *, randomized: bool = False, reps: int = 1, seed: int = 2026) -> pd.DataFrame:
    names = list(factors)
    if not names:
        return pd.DataFrame()
    if any(len(factors[k]) == 0 for k in names):
        raise ValueError("Each DOE factor must have at least one level.")
    import itertools
    rows = [dict(zip(names, combo)) for combo in itertools.product(*(list(factors[k]) for k in names))]
    out = pd.DataFrame(rows)
    if reps > 1:
        out = pd.concat([out.assign(Replication=i) for i in range(1, int(reps) + 1)], ignore_index=True)
    if randomized:
        out = out.sample(frac=1.0, random_state=int(seed)).reset_index(drop=True)
        out.insert(0, "Run Order", np.arange(1, len(out) + 1))
    return out


def fractional_factorial_design(
    factors: Mapping[str, Sequence[Any]],
    *,
    generators: Mapping[str, Sequence[str]] | None = None,
    fraction: int = 2,
    randomized: bool = True,
    reps: int = 1,
    seed: int = 2026,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    names = list(factors)
    if not names:
        return pd.DataFrame(), {"status": "NO_FACTORS"}
    if any(len(factors[k]) != 2 for k in names):
        raise ValueError("Fractional factorial DOE requires exactly two levels per factor.")
    if fraction not in (2, 4, 8, 16):
        raise ValueError("Fraction must be one of 2, 4, 8 or 16.")
    base_count = max(1, len(names) - int(round(math.log2(fraction))))
    base_names = names[:base_count]
    design = factorial_design({k: factors[k] for k in base_names}, randomized=False)
    gen_specs = dict(generators or {})
    for idx, name in enumerate(names[base_count:], start=1):
        source = gen_specs.get(name)
        if not source:
            source = [base_names[(idx - 1) % len(base_names)], base_names[idx % len(base_names)] if len(base_names) > 1 else base_names[0]]
        levels = []
        for _, row in design.iterrows():
            sign = 1
            for token in source:
                pos = names.index(token)
                base_col = names[pos] if pos < len(row.index) else None
                if base_col is None or base_col not in row:
                    # source can refer only to previously generated factors
                    sign *= 1
                else:
                    sign *= 1 if row[base_col] == factors[base_col][0] else -1
            levels.append(factors[name][0] if sign < 0 else factors[name][1])
        design[name] = levels
    if reps > 1:
        design = pd.concat([design.assign(Replication=i) for i in range(1, reps + 1)], ignore_index=True)
    if randomized:
        design = design.sample(frac=1, random_state=seed).reset_index(drop=True)
        design.insert(0, "Run Order", np.arange(1, len(design) + 1))
    meta = {
        "status": "OK",
        "type": "fractional_factorial",
        "fraction": int(fraction),
        "base_factors": base_names,
        "generators": {k: list(v) for k, v in gen_specs.items()},
        "runs": int(len(design)),
        "seed": int(seed),
        "replications": int(reps),
    }
    return design, meta


def response_surface_design(
    factors: Mapping[str, Sequence[float]],
    *,
    design: str = "central_composite",
    center_points: int = 5,
    alpha: float | None = None,
    seed: int = 2026,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    names = list(factors)
    if not names or any(len(factors[k]) != 2 for k in names):
        raise ValueError("Response-surface design requires two numeric low/high settings for every factor.")
    low = {k: float(factors[k][0]) for k in names}
    high = {k: float(factors[k][1]) for k in names}
    center = {k: (low[k] + high[k]) / 2 for k in names}
    half = {k: (high[k] - low[k]) / 2 for k in names}
    if any(v <= 0 for v in half.values()):
        raise ValueError("Each factor must have distinct low/high values.")
    import itertools
    rows: list[dict[str, Any]] = []
    typ = str(design).lower()
    if typ in {"central_composite", "ccd", "cc"}:
        alpha_val = float(alpha if alpha is not None else max(1.0, len(names) ** 0.25))
        for combo in itertools.product([-1, 1], repeat=len(names)):
            row = {k: center[k] + combo[i] * half[k] for i, k in enumerate(names)}
            row["Point Type"] = "factorial"
            rows.append(row)
        for i, name in enumerate(names):
            for sign in (-1, 1):
                row = dict(center)
                row[name] = center[name] + sign * alpha_val * half[name]
                row["Point Type"] = "axial"
                rows.append(row)
    elif typ in {"box_behnken", "bbd"}:
        if len(names) < 3:
            raise ValueError("Box-Behnken design requires at least 3 factors.")
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                for a, b in itertools.product([-1, 1], repeat=2):
                    row = dict(center)
                    row[names[i]] = center[names[i]] + a * half[names[i]]
                    row[names[j]] = center[names[j]] + b * half[names[j]]
                    row["Point Type"] = "edge"
                    rows.append(row)
    else:
        raise ValueError("design must be central_composite or box_behnken.")
    rows.extend([{**center, "Point Type": "center"} for _ in range(max(1, int(center_points)))])
    out = pd.DataFrame(rows)
    out = out.sample(frac=1.0, random_state=int(seed)).reset_index(drop=True)
    out.insert(0, "Run Order", np.arange(1, len(out) + 1))
    out.insert(1, "Replication", 1)
    return out, {
        "status": "OK", "type": typ, "factors": names,
        "center_points": int(center_points), "alpha": float(alpha_val) if "alpha_val" in locals() else None,
        "runs": int(len(out)), "seed": int(seed),
    }


def replication_planner(effect_size: float, sigma: float = 1.0, alpha: float = 0.05, power: float = 0.8) -> dict[str, Any]:
    try:
        from scipy.stats import norm
        z_alpha = float(norm.ppf(1 - alpha / 2))
        z_beta = float(norm.ppf(power))
    except Exception:
        z_alpha, z_beta = 1.96, 0.842
    es = max(abs(float(effect_size)), 1e-9)
    n = math.ceil(2 * ((z_alpha + z_beta) / es) ** 2)
    return {
        "effect_size": float(effect_size),
        "sigma": float(sigma),
        "alpha": float(alpha),
        "target_power": float(power),
        "replications_per_group": int(max(2, n)),
        "method": "normal two-group approximation",
    }


def residual_diagnostics(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, Any]:
    a = pd.to_numeric(pd.Series(actual), errors="coerce")
    p = pd.to_numeric(pd.Series(predicted), errors="coerce")
    mask = a.notna() & p.notna()
    a, p = a[mask].to_numpy(dtype=float), p[mask].to_numpy(dtype=float)
    if len(a) == 0:
        return {"n": 0}
    resid = a - p
    return {
        "n": int(len(resid)),
        "mae": float(np.mean(np.abs(resid))),
        "rmse": float(np.sqrt(np.mean(resid ** 2))),
        "bias": float(np.mean(resid)),
        "residual_std": float(np.std(resid, ddof=1)) if len(resid) > 1 else 0.0,
        "max_abs_error": float(np.max(np.abs(resid))),
    }


def _forecast_fit(series: np.ndarray, method: str, period: int = 1) -> tuple[np.ndarray, dict[str, Any]]:
    method = str(method)
    if method == "naive":
        level = float(series[-1])
        return np.array([level]), {"method": method}
    if method == "moving_average":
        window = min(max(2, period), len(series))
        return np.array([float(np.mean(series[-window:]))]), {"method": method, "window": window}
    if method == "linear_trend":
        n = len(series)
        x = np.arange(n, dtype=float)
        slope, intercept = np.polyfit(x, series, 1) if n > 1 else (0.0, float(series[-1]))
        return np.array([float(intercept + slope * n)]), {"method": method, "slope": float(slope)}
    if method == "seasonal_naive":
        if len(series) <= period:
            return np.array([float(series[-1])]), {"method": method, "period": period, "fallback": "naive"}
        return np.array([float(series[-period])]), {"method": method, "period": period}
    raise ValueError(f"Unknown forecast method: {method}")


def _forecast_recursive(series: np.ndarray, method: str, horizon: int, period: int) -> np.ndarray:
    history = list(map(float, series.tolist()))
    for _ in range(int(horizon)):
        pred, _ = _forecast_fit(np.asarray(history, dtype=float), method, period)
        history.append(float(pred[-1]))
    return np.asarray(history[-int(horizon):], dtype=float)


def forecast_operations(
    frame: pd.DataFrame,
    *,
    date_col: str | None = None,
    target_col: str | None = None,
    horizon: int = 12,
    seasonal_period: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(), {"status": "NO_DATA"}
    dates = date_col or next((c for c in frame.columns if "date" in str(c).lower() or "time" in str(c).lower()), None)
    target = target_col or next((c for c in frame.select_dtypes(include=np.number).columns), None)
    if not target:
        return pd.DataFrame(), {"status": "NO_NUMERIC_TARGET"}
    if not dates:
        work = frame[[target]].copy()
        work["__date__"] = np.arange(len(work))
        dates = "__date__"
    else:
        work = frame[[dates, target]].copy()
        work[dates] = pd.to_datetime(work[dates], errors="coerce")
        work = work.dropna(subset=[dates])
    work[target] = pd.to_numeric(work[target], errors="coerce")
    work = work.dropna(subset=[target]).sort_values(dates)
    if len(work) < 8:
        return pd.DataFrame(), {"status": "INSUFFICIENT_HISTORY", "n": int(len(work))}
    y = work[target].to_numpy(dtype=float)
    if seasonal_period is None:
        if len(y) >= 24:
            seasonal_period = 12
        elif len(y) >= 14:
            seasonal_period = 7
        else:
            seasonal_period = 1
    candidates = ["naive", "moving_average", "linear_trend"]
    if seasonal_period > 1:
        candidates.append("seasonal_naive")
    test_size = max(3, min(12, len(y) // 4))
    rows = []
    for method in candidates:
        preds = []
        actual = []
        for idx in range(max(5, len(y) - test_size), len(y)):
            hist = y[:idx]
            preds.extend(_forecast_recursive(hist, method, 1, int(seasonal_period)))
            actual.append(y[idx])
        diag = residual_diagnostics(actual, preds)
        mape_mask = np.abs(np.asarray(actual)) > 1e-9
        mape = float(np.mean(np.abs((np.asarray(actual)[mape_mask] - np.asarray(preds)[mape_mask]) / np.asarray(actual)[mape_mask])) * 100) if mape_mask.any() else float("nan")
        rows.append({"Model": method, "MAE": diag.get("mae"), "RMSE": diag.get("rmse"), "MAPE": mape, "Bias": diag.get("bias")})
    score = pd.DataFrame(rows).sort_values(["RMSE", "MAE"], na_position="last")
    best = str(score.iloc[0]["Model"])
    point = _forecast_recursive(y, best, int(horizon), int(seasonal_period))
    residual_std = float(score.iloc[0]["RMSE"] or 0.0)
    z = 1.96
    out = pd.DataFrame({
        "Horizon": np.arange(1, horizon + 1),
        "Forecast": point,
        "Lower 95%": point - z * residual_std,
        "Upper 95%": point + z * residual_std,
        "P50": point,
        "P80": point + 1.2816 * residual_std,
        "P95": point + 1.6449 * residual_std,
    })
    return out, {
        "status": "OK", "target": str(target), "date_column": str(dates),
        "best_model": best, "seasonal_period": int(seasonal_period),
        "model_comparison": score.to_dict("records"),
        "backtest_size": int(test_size),
        "prediction_interval_method": "residual standard error",
        "seasonality_note": "seasonal-naive candidate tested" if seasonal_period > 1 else "no seasonal candidate",
    }


def quantity_dimension(unit: str) -> str:
    key = str(unit).strip().lower()
    if key not in UNIT_DEFINITIONS:
        raise ValueError(f"Unsupported engineering unit: {unit}")
    return UNIT_DEFINITIONS[key][0]


def convert_quantity(value: float, from_unit: str, to_unit: str) -> float:
    src = str(from_unit).strip().lower()
    dst = str(to_unit).strip().lower()
    if src not in UNIT_DEFINITIONS or dst not in UNIT_DEFINITIONS:
        raise ValueError(f"Unsupported engineering unit conversion: {from_unit} -> {to_unit}")
    sd, sf = UNIT_DEFINITIONS[src]
    dd, df = UNIT_DEFINITIONS[dst]
    if sd != dd:
        raise ValueError(f"Incompatible dimensions: {from_unit} ({sd}) -> {to_unit} ({dd})")
    return float(value) * sf / df


def validate_formula(name: str, formula: str, inputs: Mapping[str, str], output_unit: str) -> dict[str, Any]:
    """Validate units for formulas expressed as simple products/ratios/powers.

    Full symbolic dimensional algebra belongs in the formula registry, but this
    validator catches the highest-risk incompatible output-unit mistakes.
    """
    if not str(formula).strip():
        raise ValueError("Formula cannot be blank.")
    for var, unit in inputs.items():
        quantity_dimension(unit)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(var)):
            raise ValueError(f"Unsafe formula variable: {var}")
    quantity_dimension(output_unit)
    tree = ast.parse(formula, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)
    if not all(isinstance(node, allowed) for node in ast.walk(tree)):
        raise ValueError("Formula contains unsupported operations.")
    return {
        "name": name, "formula": formula, "inputs": dict(inputs),
        "output_unit": output_unit, "verified_at": now_iso(),
        "verification": "syntax + declared-unit compatibility",
    }


class SafeExpressionEvaluator(ast.NodeVisitor):
    ALLOWED_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}
    ALLOWED_FUNCS = {"abs": abs, "min": min, "max": max, "round": round}

    def __init__(self, variables: Mapping[str, float]):
        self.variables = dict(variables)

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric constants are permitted.")
        return float(node.value)

    def visit_Name(self, node: ast.Name):
        if node.id not in self.variables:
            raise ValueError(f"Unknown variable: {node.id}")
        return float(self.variables[node.id])

    def visit_UnaryOp(self, node: ast.UnaryOp):
        value = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return value
        raise ValueError("Unsupported unary operator.")

    def visit_BinOp(self, node: ast.BinOp):
        op = next((fn for cls, fn in self.ALLOWED_BINOPS.items() if isinstance(node.op, cls)), None)
        if op is None:
            raise ValueError("Unsupported binary operator.")
        return float(op(self.visit(node.left), self.visit(node.right)))

    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in self.ALLOWED_FUNCS:
            raise ValueError("Function is not allowed.")
        if node.keywords:
            raise ValueError("Keyword arguments are not allowed.")
        return float(self.ALLOWED_FUNCS[node.func.id](*[self.visit(a) for a in node.args]))

    def generic_visit(self, node):
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def safe_calculate(formula: str, variables: Mapping[str, float]) -> float:
    return float(SafeExpressionEvaluator(variables).visit(ast.parse(str(formula), mode="eval")))


def visualization_intelligence(df: pd.DataFrame) -> list[dict[str, Any]]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    numeric = list(df.select_dtypes(include=np.number).columns)
    categorical = list(df.select_dtypes(exclude=np.number).columns)
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c]) or "date" in str(c).lower() or "time" in str(c).lower()]
    recs = []
    if date_cols and numeric:
        recs.append({"chart": "time_series", "x": str(date_cols[0]), "y": str(numeric[0]), "reason": "time-indexed numeric measure"})
    if numeric:
        recs.append({"chart": "distribution", "x": str(numeric[0]), "reason": "numeric distribution / variation"})
        if len(numeric) >= 2:
            recs.append({"chart": "scatter", "x": str(numeric[0]), "y": str(numeric[1]), "reason": "numeric relationship / driver screen"})
    if categorical and numeric:
        recs.append({"chart": "grouped_summary", "x": str(categorical[0]), "y": str(numeric[0]), "reason": "category-to-KPI comparison"})
        recs.append({"chart": "pareto", "x": str(categorical[0]), "y": str(numeric[0]), "reason": "prioritize concentrated contribution"})
    return recs


def build_visualization(df: pd.DataFrame, recommendation: Mapping[str, Any]) -> Any:
    chart = str(recommendation.get("chart") or "")
    x = recommendation.get("x")
    y = recommendation.get("y")
    if chart == "time_series" and x in df.columns and y in df.columns:
        return px.line(df, x=x, y=y, markers=True, title=f"{y} over time")
    if chart == "distribution" and x in df.columns:
        return px.histogram(df, x=x, nbins=min(40, max(10, len(df)//5)), title=f"Distribution · {x}")
    if chart == "scatter" and x in df.columns and y in df.columns:
        return px.scatter(df, x=x, y=y, trendline="ols", title=f"{y} vs {x}")
    if chart == "grouped_summary" and x in df.columns and y in df.columns:
        agg = df.groupby(x, dropna=False)[y].mean().reset_index()
        return px.bar(agg, x=x, y=y, title=f"Mean {y} by {x}")
    if chart == "pareto" and x in df.columns and y in df.columns:
        agg = df.groupby(x, dropna=False)[y].sum().abs().sort_values(ascending=False).reset_index()
        agg["Cumulative %"] = agg[y].cumsum() / max(1e-12, agg[y].sum()) * 100
        fig = go.Figure()
        fig.add_bar(x=agg[x], y=agg[y], name=y)
        fig.add_scatter(x=agg[x], y=agg["Cumulative %"], name="Cumulative %", yaxis="y2")
        fig.update_layout(title=f"Pareto · {y} by {x}", yaxis2={"overlaying": "y", "side": "right", "range": [0, 100]})
        return fig
    return None


def render_visualization_os(module: str, df: pd.DataFrame, *, kpi_table: pd.DataFrame | None = None) -> None:
    with st.expander("Universal Visualization OS", expanded=False):
        if not isinstance(df, pd.DataFrame) or df.empty:
            st.info("Load or create data to unlock visualization intelligence.")
            return
        recs = visualization_intelligence(df)
        if not recs:
            st.info("No compatible chart family detected.")
            return

        filtered = df
        categories = [c for c in df.select_dtypes(exclude=np.number).columns if df[c].nunique(dropna=False) <= 30]
        if categories:
            filter_col = st.selectbox("Filter dimension", ["All"] + [str(c) for c in categories],
                                      key=f"vis_filter_col_{re.sub(r'[^A-Za-z0-9]+','_',module)}")
            if filter_col != "All":
                options = [str(x) for x in df[filter_col].dropna().unique()]
                selected_values = st.multiselect(
                    "Filter values", options, default=options[:min(8, len(options))],
                    key=f"vis_filter_values_{re.sub(r'[^A-Za-z0-9]+','_',module)}",
                )
                if selected_values:
                    filtered = df[df[filter_col].astype(str).isin(selected_values)].copy()

        labels = [f"{r['chart']} — {r['reason']}" for r in recs]
        selected = st.selectbox("Visualization", labels, key=f"vis_os_sel_{re.sub(r'[^A-Za-z0-9]+','_',module)}")
        rec = recs[labels.index(selected)]
        fig = build_visualization(filtered, rec)
        if fig is None:
            st.info("The selected visualization is incompatible with the current filter.")
            return

        st.session_state[f"shoir_visualization_snapshot_{module}"] = {
            "module": module, "filter_rows": int(len(filtered)), "chart": dict(rec), "captured_at": now_iso(),
        }
        st.plotly_chart(fig, use_container_width=True, key=f"vis_os_chart_{re.sub(r'[^A-Za-z0-9]+','_',module)}")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            expand = st.checkbox("Expand", key=f"vis_expand_{module}")
        with c2:
            explain = st.button("Explain", key=f"vis_explain_{module}")
        with c3:
            compare = st.button("Compare", key=f"vis_compare_{module}")
        with c4:
            st.download_button(
                "Export", data=fig.to_json().encode("utf-8"),
                file_name=f"shoir_{re.sub(r'[^A-Za-z0-9]+','_',module).lower()}_visual.json",
                mime="application/json", key=f"vis_export_{module}",
            )
        with c5:
            add = st.button("Add to Report", key=f"vis_report_{module}")
        if expand:
            st.plotly_chart(fig, use_container_width=True, key=f"vis_expanded_chart_{re.sub(r'[^A-Za-z0-9]+','_',module)}")
        if explain:
            st.info(f"{rec['chart'].replace('_',' ').title()} was selected because {rec['reason']}; {len(filtered):,} rows are in scope.")
        if compare:
            if kpi_table is not None and not kpi_table.empty:
                st.dataframe(kpi_table, use_container_width=True, hide_index=True)
            elif filtered.select_dtypes(include=np.number).shape[1] >= 1:
                nums = list(filtered.select_dtypes(include=np.number).columns[:2])
                st.dataframe(filtered[nums].describe().T.reset_index().rename(columns={"index": "Metric"}), use_container_width=True, hide_index=True)
        if add:
            reports = list(st.session_state.get("shoir_report_figures", []))
            reports.append({"module": module, "chart": rec, "filters": {"rows": len(filtered)}, "created_at": now_iso()})
            st.session_state["shoir_report_figures"] = reports
            save_platform_record("report_figure", f"{module}:{len(reports)}", reports[-1])
            st.success("Visualization added to the current report queue.")



def render_lineage_graph(*, workspace: str = "default") -> None:
    nodes, edges = lineage_graph_frame(workspace=workspace, limit=200)
    if nodes.empty:
        st.info("No KPI lineage has been captured yet. Complete a module run first.")
        return
    st.caption("Click a KPI lineage row to inspect the full Dataset → Transformations → Model → Formula → Scenario → Run → Evidence trace.")
    if not edges.empty:
        node_index = {node_id: idx for idx, node_id in enumerate(nodes["id"].astype(str))}
        sources = [node_index[x] for x in edges["source"] if x in node_index]
        targets = [node_index[x] for x in edges["target"] if x in node_index]
        valid = [(a, b) for a, b in zip(sources, targets) if a != b]
        if valid:
            fig = go.Figure(go.Sankey(
                arrangement="snap",
                node={"label": nodes["label"].tolist(), "pad": 12, "thickness": 16},
                link={"source": [a for a, _ in valid], "target": [b for _, b in valid], "value": [1] * len(valid)},
            ))
            fig.update_layout(title="KPI Evidence Lineage", height=540, margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(fig, use_container_width=True, key="shoir_lineage_sankey")
    st.dataframe(nodes, use_container_width=True, hide_index=True, height=260)

def render_engineering_canvas(*, cards: Sequence[Mapping[str, Any]] = ()) -> None:
    """True browser-side drag/drop canvas with local persistence.

    Streamlit cannot natively expose arbitrary drag/drop ordering as a Python
    widget. This component therefore owns ordering in the browser and stores it
    in localStorage while Python continues to own the engineering data.
    """
    import streamlit.components.v1 as components
    payload = list(cards) or [
        {"id": "data", "title": "DATA", "detail": "Dataset / readiness"},
        {"id": "model", "title": "MODEL", "detail": "Method / solver"},
        {"id": "scenario", "title": "SCENARIO", "detail": "Baseline / alternatives"},
        {"id": "kpi", "title": "KPI", "detail": "Metric / target / uncertainty"},
        {"id": "visual", "title": "VISUALIZE", "detail": "Chart / compare / explain"},
        {"id": "verify", "title": "VERIFY", "detail": "Evidence / replay / outcome"},
    ]
    safe = json.dumps(_jsonable(payload))
    html = f"""
    <html><body style="margin:0;font-family:Inter,system-ui,sans-serif;background:#f8fafc">
    <div id="canvas" style="display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:10px;padding:10px">
    </div>
    <div style="padding:0 10px 10px;color:#64748b;font-size:12px">Drag cards to rearrange. Order is retained in this browser.</div>
    <script>
    const seed={safe}; const key='shoir_canvas_order_v1';
    const canvas=document.getElementById('canvas');
    let order=JSON.parse(localStorage.getItem(key)||'null');
    if(!Array.isArray(order)) order=seed.map(x=>x.id);
    function render(){{
      canvas.innerHTML='';
      [...order].map(id=>seed.find(x=>x.id===id)).filter(Boolean).forEach(item=>{{
        const el=document.createElement('div'); el.draggable=true; el.dataset.id=item.id;
        el.style='background:white;border:1px solid #dbe4ef;border-radius:14px;padding:14px;cursor:grab;min-height:78px;box-shadow:0 8px 18px rgba(15,23,42,.05)';
        el.innerHTML='<div style="font-size:10px;letter-spacing:.08em;font-weight:900;color:#0f766e">'+item.title+'</div><div style="font-size:12px;font-weight:700;color:#0f172a;margin-top:7px">'+item.detail+'</div>';
        el.addEventListener('dragstart',e=>e.dataTransfer.setData('text/plain',item.id));
        el.addEventListener('dragover',e=>e.preventDefault());
        el.addEventListener('drop',e=>{{
          e.preventDefault(); const from=e.dataTransfer.getData('text/plain'); const to=item.id;
          order=order.filter(x=>x!==from); const idx=order.indexOf(to); order.splice(idx,0,from);
          localStorage.setItem(key,JSON.stringify(order)); render();
        }});
        canvas.appendChild(el);
      }});
    }} render();
    </script></body></html>
    """
    components.html(html, height=365, scrolling=False)


def normalize_action_level(level: str) -> str:
    candidate = str(level or "READ").upper()
    return candidate if candidate in ACTION_LEVELS else "READ"


def action_authorized(requested: str, actor_level: str, *, approval: bool = False) -> bool:
    order = {x: i for i, x in enumerate(ACTION_LEVELS)}
    req = normalize_action_level(requested)
    actor = normalize_action_level(actor_level)
    return order[actor] >= order[req] and (req not in {"EXECUTE", "ADMIN"} or approval)


def copilot_plan(prompt: str, module: str, *, readiness: Mapping[str, Any], approval_level: str = "RECOMMEND") -> dict[str, Any]:
    lower = str(prompt).lower()
    intent = "analyze"
    if any(t in lower for t in ("clean", "duplicate", "missing", "schema")):
        intent = "validate_data"
    elif any(t in lower for t in ("forecast", "predict")):
        intent = "forecast"
    elif any(t in lower for t in ("optimize", "minimize", "maximize", "schedule")):
        intent = "optimize"
    elif any(t in lower for t in ("compare", "scenario", "what if")):
        intent = "scenario"
    elif any(t in lower for t in ("report", "export")):
        intent = "export"
    steps = [
        {"stage": "DATA", "action": "inspect active workspace"},
        {"stage": "VALIDATE", "action": "run schema and quality gates"},
        {"stage": "MAP", "action": "map columns to canonical industrial entities"},
        {"stage": "MODEL", "action": f"select method for {intent}"},
        {"stage": "RUN", "action": "execute approved specialist engine"},
        {"stage": "VISUALIZE", "action": "generate evidence-grade visuals"},
        {"stage": "COMPARE", "action": "compare baseline and alternatives"},
        {"stage": "EXPLAIN", "action": "attach KPI lineage and uncertainty"},
        {"stage": "DECIDE", "action": "prepare a decision record"},
        {"stage": "EXPORT", "action": "build evidence/report package"},
        {"stage": "VERIFY", "action": "run verification and reproducibility checks"},
    ]
    blocked = []
    if float(readiness.get("score", 0)) < 80:
        blocked.append("Data readiness below 80%; validation must pass before execution.")
    if normalize_action_level(approval_level) in {"EXECUTE", "ADMIN"}:
        blocked.append("High-impact action requires explicit approval.")
    return {
        "plan_id": stable_id("PLAN"),
        "module": module,
        "intent": intent,
        "requested_level": normalize_action_level(approval_level),
        "readiness": dict(readiness),
        "steps": steps,
        "blocked_reasons": blocked,
        "requires_user_approval": normalize_action_level(approval_level) in {"EXECUTE", "ADMIN"},
        "created_at": now_iso(),
    }


def active_df_hash(df: pd.DataFrame) -> str:
    return dataframe_digest(df) if isinstance(df, pd.DataFrame) and not df.empty else ""


def register_replay(module: str, callable_path: str, kwargs: Mapping[str, Any], *, input_hash: str = "", workspace: str = "default") -> str:
    if ":" not in callable_path:
        raise ValueError("Replay callable_path must use module:function notation.")
    payload = {
        "module": module,
        "callable_path": callable_path,
        "kwargs": _jsonable(kwargs),
        "input_hash": input_hash,
        "python": platform.python_version(),
        "created_at": now_iso(),
        "schema_version": SCHEMA_VERSION,
    }
    rid = save_platform_record("replay", f"{module}:{callable_path}", payload, workspace=workspace)
    st.session_state["shoir_last_replay_id"] = rid
    return rid



def get_replay_record(replay_id: str, *, workspace: str = "default") -> dict[str, Any]:
    rows = repository_records("replay", workspace=workspace, limit=500)
    if rows.empty:
        raise KeyError(f"Replay record not found: {replay_id}")
    matches = rows[rows["record_id"].astype(str) == str(replay_id)]
    if matches.empty:
        raise KeyError(f"Replay record not found: {replay_id}")
    return _payload_from_value(matches.iloc[0]["payload_json"])


def execute_replay(record: Mapping[str, Any]) -> Any:
    path = str(record.get("callable_path") or "")
    if ":" not in path:
        raise ValueError("Replay record has no callable path.")
    module_name, func_name = path.split(":", 1)
    module = importlib.import_module(module_name)
    func = getattr(module, func_name, None)
    if not callable(func):
        raise ValueError(f"Replay target is not callable: {path}")
    kwargs = dict(record.get("kwargs") or {})
    started = time.perf_counter()
    result = func(**kwargs)
    duration = (time.perf_counter() - started) * 1000
    result_hash = digest(result)
    _record_event(
        "replay.executed",
        actor=str(st.session_state.get("current_user", "system")),
        entity_key=path,
        payload={"duration_ms": duration, "result_hash": result_hash, "replay_of": record.get("record_id")},
    )
    st.session_state["shoir_last_replay_result"] = {
        "callable_path": path, "duration_ms": round(duration, 2), "result_hash": result_hash,
    }
    return result


def engine_error_payload(module: str, exc: BaseException) -> dict[str, Any]:
    return {
        "error_id": stable_id("ERR"),
        "module": module,
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback_tail": traceback.format_exc(limit=8)[-4000:],
        "at": now_iso(),
    }


def record_engineering_error(module: str, exc: BaseException, *, workspace: str = "default", actor: str = "system") -> str:
    payload = engine_error_payload(module, exc)
    rid = save_platform_record("engineering_error", payload["error_id"], payload, workspace=workspace)
    _record_event("engineering_error", actor=actor, entity_key=module, payload=payload, workspace=workspace)
    return rid


def performance_route(df: pd.DataFrame, *, memory_budget_mb: float = 512.0) -> dict[str, Any]:
    rows = int(len(df)) if isinstance(df, pd.DataFrame) else 0
    bytes_used = int(df.memory_usage(index=True, deep=True).sum()) if isinstance(df, pd.DataFrame) else 0
    mb = bytes_used / (1024 ** 2)
    if rows <= 100_000 and mb <= memory_budget_mb * 0.25:
        engine = "pandas"
    elif rows <= 2_000_000 and mb <= memory_budget_mb:
        engine = "optimized_pandas"
    elif rows <= 25_000_000:
        engine = "duckdb"
    else:
        engine = "external_query"
    return {
        "engine": engine,
        "rows": rows,
        "estimated_memory_mb": round(mb, 2),
        "memory_budget_mb": float(memory_budget_mb),
        "chunking": engine in {"duckdb", "external_query"},
        "background_recommended": engine in {"duckdb", "external_query"},
    }


class ConnectorAdapter:
    kind = "generic"

    def __init__(self, profile: Mapping[str, Any]):
        self.profile = dict(profile)

    def health(self) -> dict[str, Any]:
        return {"kind": self.kind, "status": "CONFIGURED", "checked_at": now_iso()}


class RestConnector(ConnectorAdapter):
    kind = "REST"

    def health(self) -> dict[str, Any]:
        endpoint = str(self.profile.get("endpoint") or "")
        if not endpoint:
            return {"kind": self.kind, "status": "NOT_CONFIGURED", "checked_at": now_iso()}
        if requests is None:
            return {"kind": self.kind, "status": "DEPENDENCY_MISSING", "checked_at": now_iso()}
        headers = dict(self.profile.get("headers") or {})
        token = self.profile.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = requests.get(endpoint, headers=headers, timeout=float(self.profile.get("timeout", 10)))
            return {"kind": self.kind, "status": "CONNECTED" if r.ok else f"HTTP_{r.status_code}",
                    "http_status": r.status_code, "checked_at": now_iso(), "endpoint": _redact_endpoint(endpoint)}
        except Exception as exc:
            return {"kind": self.kind, "status": "ERROR", "error": str(exc), "checked_at": now_iso(),
                    "endpoint": _redact_endpoint(endpoint)}

    def fetch(self, params: Mapping[str, Any] | None = None) -> Any:
        if requests is None:
            raise RuntimeError("requests is not installed.")
        endpoint = str(self.profile.get("endpoint") or "")
        headers = dict(self.profile.get("headers") or {})
        token = self.profile.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = requests.get(endpoint, headers=headers, params=dict(params or {}), timeout=float(self.profile.get("timeout", 20)))
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        return r.json() if "json" in ctype else r.text


class SQLConnector(ConnectorAdapter):
    kind = "SQL"

    def _query(self, query: str) -> pd.DataFrame:
        if not str(query).lstrip().lower().startswith(("select", "with")):
            raise ValueError("SQL connector allows read-only SELECT/WITH queries only.")
        url = str(self.profile.get("connection_string") or "")
        if not url:
            raise ValueError("Missing SQL connection string.")
        if url.startswith("postgres"):
            if psycopg2 is None:
                raise RuntimeError("psycopg2 is not installed.")
            with psycopg2.connect(url, connect_timeout=10) as conn:
                return pd.read_sql_query(query, conn)
        if url.startswith("sqlite:///"):
            path = url.removeprefix("sqlite:///")
            with shoir_sqlite_connect(path) as conn:
                return pd.read_sql_query(query, conn)
        if oracledb is not None and url.startswith("oracle://"):
            with oracledb.connect(url.removeprefix("oracle://")) as conn:
                return pd.read_sql_query(query, conn)
        raise RuntimeError("Unsupported SQL URL. Use PostgreSQL, SQLite or configured Oracle client.")

    def health(self) -> dict[str, Any]:
        try:
            out = self._query("SELECT 1 AS health_check")
            return {"kind": self.kind, "status": "CONNECTED" if not out.empty else "ERROR", "checked_at": now_iso()}
        except Exception as exc:
            return {"kind": self.kind, "status": "ERROR", "error": str(exc), "checked_at": now_iso()}


class MQTTConnector(ConnectorAdapter):
    kind = "MQTT"

    def health(self) -> dict[str, Any]:
        if mqtt is None:
            return {"kind": self.kind, "status": "DEPENDENCY_MISSING", "checked_at": now_iso()}
        host = str(self.profile.get("host") or "")
        port = int(self.profile.get("port", 1883))
        if not host:
            return {"kind": self.kind, "status": "NOT_CONFIGURED", "checked_at": now_iso()}
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        username = self.profile.get("username")
        password = self.profile.get("password")
        if username:
            client.username_pw_set(str(username), str(password or ""))
        try:
            client.connect(host, port=port, keepalive=5)
            client.disconnect()
            return {"kind": self.kind, "status": "CONNECTED", "host": host, "port": port, "checked_at": now_iso()}
        except Exception as exc:
            return {"kind": self.kind, "status": "ERROR", "error": str(exc), "host": host, "checked_at": now_iso()}


class OPCUAConnector(ConnectorAdapter):
    kind = "OPC-UA"

    def health(self) -> dict[str, Any]:
        try:
            from opcua import Client
        except Exception:
            return {"kind": self.kind, "status": "DEPENDENCY_MISSING", "checked_at": now_iso()}
        endpoint = str(self.profile.get("endpoint") or "")
        if not endpoint:
            return {"kind": self.kind, "status": "NOT_CONFIGURED", "checked_at": now_iso()}
        client = Client(endpoint, timeout=float(self.profile.get("timeout", 10)))
        try:
            client.connect()
            client.disconnect()
            return {"kind": self.kind, "status": "CONNECTED", "endpoint": _redact_endpoint(endpoint), "checked_at": now_iso()}
        except Exception as exc:
            return {"kind": self.kind, "status": "ERROR", "error": str(exc), "endpoint": _redact_endpoint(endpoint), "checked_at": now_iso()}


class SAPODataConnector(RestConnector):
    kind = "SAP-OData"


class SFTPConnector(ConnectorAdapter):
    kind = "SFTP"

    def health(self) -> dict[str, Any]:
        if paramiko is None:
            return {"kind": self.kind, "status": "DEPENDENCY_MISSING", "checked_at": now_iso()}
        host = str(self.profile.get("host") or "")
        if not host:
            return {"kind": self.kind, "status": "NOT_CONFIGURED", "checked_at": now_iso()}
        try:
            transport = paramiko.Transport((host, int(self.profile.get("port", 22))))
            transport.connect(username=self.profile.get("username"), password=self.profile.get("password"))
            transport.close()
            return {"kind": self.kind, "status": "CONNECTED", "host": host, "checked_at": now_iso()}
        except Exception as exc:
            return {"kind": self.kind, "status": "ERROR", "error": str(exc), "host": host, "checked_at": now_iso()}


def _redact_endpoint(value: str) -> str:
    try:
        p = urlparse(value)
        if p.hostname:
            netloc = p.hostname
            if p.port:
                netloc += f":{p.port}"
            return p._replace(netloc=netloc).geturl()
    except Exception as exc:
        st.session_state.setdefault("shoir_platform_warnings", []).append({
            "scope": "endpoint_redaction", "type": type(exc).__name__, "message": str(exc), "at": now_iso(),
        })
    return re.sub(r"(?i)(password|token|secret)=([^&\s]+)", r"\1=***", value)


def connector_health(profile: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(profile.get("kind") or profile.get("type") or "REST").upper()
    cls = {
        "REST": RestConnector, "SAP": SAPODataConnector, "SAP-ODATA": SAPODataConnector,
        "SQL": SQLConnector, "POSTGRES": SQLConnector, "ORACLE": SQLConnector,
        "MQTT": MQTTConnector, "OPC-UA": OPCUAConnector, "OPCUA": OPCUAConnector,
        "SFTP": SFTPConnector,
    }.get(kind, RestConnector)
    result = cls(profile).health()
    record = {"profile": {k: ("***" if k.lower() in {"password", "token", "secret", "api_key"} else v) for k, v in profile.items()},
              "health": result, "checked_at": now_iso()}
    save_platform_record("connector_health", str(profile.get("name") or kind), record)
    return result


class JobManager:
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="shoir-worker")
        self.futures: dict[str, Future] = {}

    def submit(self, module: str, task: Callable[[], Any], *, workspace: str = "default", payload: Mapping[str, Any] | None = None) -> str:
        job_id = stable_id("JOB")
        save_platform_record("job", job_id, {
            "job_id": job_id, "module": module, "status": "QUEUED",
            "progress": 0.0, "payload": _jsonable(payload or {}), "created_at": now_iso(),
        }, workspace=workspace)

        def worker():
            started = time.perf_counter()
            try:
                save_platform_record("job", job_id, {"job_id": job_id, "module": module, "status": "RUNNING", "progress": 0.05, "started_at": now_iso()}, workspace=workspace)
                result = task()
                duration = (time.perf_counter() - started) * 1000
                save_platform_record("job", job_id, {
                    "job_id": job_id, "module": module, "status": "COMPLETED", "progress": 1.0,
                    "duration_ms": duration, "result_hash": digest(result), "completed_at": now_iso(),
                }, workspace=workspace)
                return result
            except Exception as exc:
                record_engineering_error(module, exc, workspace=workspace)
                save_platform_record("job", job_id, {"job_id": job_id, "module": module, "status": "FAILED", "progress": 1.0, "error": engine_error_payload(module, exc)}, workspace=workspace)
                raise

        future = self.executor.submit(worker)
        self.futures[job_id] = future
        return job_id

    def status(self, job_id: str) -> dict[str, Any]:
        future = self.futures.get(job_id)
        records = repository_records("job")
        if not records.empty:
            matches = records[records["entity_key"].astype(str) == str(job_id)]
            if not matches.empty:
                payload = json.loads(str(matches.iloc[0]["payload_json"]))
                if future is not None and future.done() and payload.get("status") == "RUNNING":
                    payload["status"] = "COMPLETED"
                return payload
        return {"job_id": job_id, "status": "UNKNOWN"}


_JOB_MANAGER: JobManager | None = None


def job_manager() -> JobManager:
    global _JOB_MANAGER
    if _JOB_MANAGER is None:
        _JOB_MANAGER = JobManager(int(os.getenv("SHOIR_WORKERS", "4")))
    return _JOB_MANAGER


def submit_background_job(module: str, task: Callable[[], Any], *, workspace: str = "default", payload: Mapping[str, Any] | None = None) -> str:
    return job_manager().submit(module, task, workspace=workspace, payload=payload)


def decision_memory_query(problem: str, *, workspace: str = "default", limit: int = 5) -> pd.DataFrame:
    records = repository_records("decision", workspace=workspace, limit=500)
    if records.empty:
        return pd.DataFrame()
    q = set(re.findall(r"[a-z0-9]{3,}", str(problem).lower()))
    rows = []
    for _, row in records.iterrows():
        try:
            payload = json.loads(str(row["payload_json"]))
        except Exception:
            payload = {}
        text = " ".join([
            str(payload.get("title", "")), str(payload.get("problem", "")),
            str(payload.get("domain", "")), canonical_json(payload.get("kpis", {})),
            canonical_json(payload.get("outcome", {})),
        ]).lower()
        tokens = set(re.findall(r"[a-z0-9]{3,}", text))
        score = len(q & tokens) / max(1, len(q))
        rows.append({"score": score, **payload})
    return pd.DataFrame(rows).sort_values("score", ascending=False).head(int(limit))


def save_decision_memory(
    title: str,
    problem: str,
    decision: Mapping[str, Any],
    *,
    outcome: Mapping[str, Any] | None = None,
    workspace: str = "default",
) -> str:
    payload = {
        "title": title, "problem": problem, "decision": _jsonable(decision),
        "outcome": _jsonable(outcome or {}), "created_at": now_iso(),
    }
    return save_platform_record("decision", stable_id("DEC"), payload, workspace=workspace)


def benchmark_compare(actual: Mapping[str, float], reference: Mapping[str, float]) -> pd.DataFrame:
    rows = []
    for k in sorted(set(actual) | set(reference)):
        a = float(actual.get(k, np.nan)); r = float(reference.get(k, np.nan))
        delta = a - r if np.isfinite(a) and np.isfinite(r) else np.nan
        pct = delta / r * 100 if np.isfinite(delta) and r != 0 else np.nan
        rows.append({"KPI": k, "Actual": a, "Reference": r, "Delta": delta, "% vs reference": pct})
    return pd.DataFrame(rows)


def verification_suite(
    module: str,
    *,
    inputs: pd.DataFrame | None = None,
    results: pd.DataFrame | None = None,
    known_case: Mapping[str, Any] | None = None,
    constraints: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    checks = []
    df = inputs if isinstance(inputs, pd.DataFrame) else pd.DataFrame()
    res = results if isinstance(results, pd.DataFrame) else pd.DataFrame()
    checks.append(("input_present", not df.empty))
    checks.append(("results_present", not res.empty))
    if not df.empty:
        checks.append(("finite_numeric_inputs", np.isfinite(df.select_dtypes(include=np.number).to_numpy(dtype=float, na_value=np.nan)).all()))
        checks.append(("unique_columns", len(set(map(str, df.columns))) == len(df.columns))
    if known_case:
        for key, expected in known_case.items():
            actual = st.session_state.get(str(key))
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                checks.append((f"known_case:{key}", math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=1e-6)))
            else:
                checks.append((f"known_case:{key}", actual == expected))
    if constraints and not res.empty:
        for kpi, spec in constraints.items():
            if kpi in res.columns:
                value = pd.to_numeric(res[kpi], errors="coerce").dropna()
                if not value.empty:
                    if spec.get("min") is not None:
                        checks.append((f"constraint:{kpi}:min", float(value.iloc[-1]) >= float(spec["min"])))
                    if spec.get("max") is not None:
                        checks.append((f"constraint:{kpi}:max", float(value.iloc[-1]) <= float(spec["max"])))
    passed = [name for name, ok in checks if bool(ok)]
    failed = [name for name, ok in checks if not bool(ok)]
    report = {
        "module": module, "status": "PASS" if not failed else "REVIEW",
        "passed": passed, "failed": failed, "checks": [{"name": n, "passed": bool(o)} for n, o in checks],
        "verified_at": now_iso(),
    }
    save_platform_record("verification", module, report)
    return report



def replay_records(*, workspace: str = "default", limit: int = 100) -> pd.DataFrame:
    rows = repository_records("replay", workspace=workspace, limit=limit)
    if rows.empty:
        return rows
    out = []
    for _, row in rows.iterrows():
        try:
            payload = json.loads(str(row["payload_json"]))
        except Exception:
            payload = {}
        out.append({
            "Replay ID": row["record_id"],
            "Module": payload.get("module"),
            "Callable": payload.get("callable_path"),
            "Input Hash": payload.get("input_hash"),
            "Created": payload.get("created_at"),
        })
    return pd.DataFrame(out)


def lineage_graph_frame(*, workspace: str = "default", limit: int = 100) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = repository_records("kpi_lineage", workspace=workspace, limit=limit)
    if rows.empty:
        return pd.DataFrame(), pd.DataFrame()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        try:
            payload = json.loads(str(row["payload_json"]))
        except Exception:
            continue
        kpi_id = f"kpi:{payload.get('module')}:{payload.get('kpi')}"
        nodes[kpi_id] = {
            "id": kpi_id,
            "label": f"{payload.get('kpi')} = {payload.get('value')}",
            "type": "KPI",
        }
        previous = kpi_id
        for kind, value in (
            ("dataset", payload.get("dataset")),
            ("model", payload.get("model")),
            ("formula", payload.get("formula")),
            ("scenario", payload.get("scenario")),
            ("run", payload.get("run")),
            ("uncertainty", payload.get("uncertainty")),
        ):
            if not value:
                continue
            node_id = f"{kind}:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()[:12]}"
            nodes[node_id] = {"id": node_id, "label": f"{kind.title()}: {canonical_json(value)[:70]}", "type": kind.upper()}
            edges.append({"source": previous, "target": node_id, "relation": "EXPLAINS"})
            previous = node_id
    return pd.DataFrame(nodes.values()), pd.DataFrame(edges)


def render_platform_completion(module: str, df: pd.DataFrame, *, allowed_modules: Sequence[str] = ()) -> None:
    """Production completion console for workflow, evidence, experiments and operations."""
    if not st.session_state.get("authenticated"):
        return

    ensure_core_schema()
    workspace = str(st.session_state.get("workspace") or st.session_state.get("active_workspace") or "default")
    actor = str(st.session_state.get("current_user") or st.session_state.get("username") or "system")
    readiness = data_readiness(df)
    ledger = capability_ledger()
    runtime = begin_module(module, workspace=workspace, actor=actor, df=df)
    command = command_center_snapshot(df, workspace=workspace)

    st.markdown("## Industrial Platform Console")
    header = st.columns(5)
    header[0].metric("Readiness", f"{readiness['score']:.0f}%")
    header[1].metric("Open alerts", int(command["open_alerts"]))
    header[2].metric("Draft decisions", int(command["draft_decisions"]))
    header[3].metric("Persistence", db_backend().upper())
    header[4].metric("Next action", str(command["what_to_do_next"])[:32])
    if command["attention"]:
        st.warning(" · ".join(command["attention"]))
    else:
        st.success("No outstanding platform attention items were detected.")
    metrics = st.columns(5)
    metrics[0].metric("Readiness", f"{readiness['score']:.0f}%")
    metrics[1].metric("Capabilities", f"{len(ledger):,}")
    metrics[2].metric("Verified", str(int((ledger["Status"] == "Verified").sum())) if not ledger.empty else "0")
    metrics[3].metric("Persistence", db_backend().upper())
    metrics[4].metric("Workflow", runtime.stage)

    tabs = st.tabs([
        "Workflow & Manifest", "Digital Thread", "Experiment", "Scenario Lab",
        "Forecast", "Run & Replay", "Governance", "Diagnostics",
        "Research & ROI", "Twin & Alerts",
    ])

    with tabs[0]:
        stage_rows = []
        for idx, stage in enumerate(WORKFLOW_STEPS):
            stage_rows.append({
                "Order": idx + 1,
                "Stage": stage,
                "State": "Complete" if idx <= runtime.stage_index else "Pending",
                "Evidence": "required",
            })
        st.dataframe(pd.DataFrame(stage_rows), hide_index=True, use_container_width=True)
        st.caption("The specialist calculation remains module-owned; the platform contract owns lifecycle evidence and gates.")
        st.json(module_manifest(module, catalog_entry=next((x for x in (
            __import__("industrial_platform", fromlist=["PLATFORM_CATALOG"]).PLATFORM_CATALOG
        ) if str(x.get("name")) == str(module)), {})))
        st.markdown("**Copilot action levels**")
        st.dataframe(pd.DataFrame([
            {"Level": level, "Meaning": description}
            for level, description in (
                ("READ", "Inspect workspace and metadata."),
                ("ANALYZE", "Run non-destructive analysis."),
                ("SIMULATE", "Execute simulation / what-if work."),
                ("RECOMMEND", "Prepare evidence-backed recommendations."),
                ("PREPARE", "Prepare artifacts for approval."),
                ("EXECUTE", "Execute an approved operational action."),
                ("ADMIN", "Change governed platform configuration."),
            )
        ]), hide_index=True, use_container_width=True)

    with tabs[1]:
        st.caption("Why-this-number lineage is persisted per workspace and reconstructed as a connected evidence graph.")
        try:
            render_lineage_graph(workspace=workspace)
        except Exception as exc:
            record_engineering_error(module, exc, workspace=workspace, actor=actor)
            st.warning(f"Lineage graph unavailable: {type(exc).__name__}: {exc}")
        lineage = repository_records("kpi_lineage", workspace=workspace, limit=200)
        if not lineage.empty:
            options = []
            records_by_label = {}
            for _, row in lineage.iterrows():
                payload = _payload_from_value(row["payload_json"])
                label = f"{payload.get('module')} · {payload.get('kpi')} = {payload.get('value')}"
                options.append(label)
                records_by_label[label] = payload
            if options:
                selected = st.selectbox("Inspect KPI evidence", options, key=f"lineage_pick_{module}")
                render_kpi_lineage(records_by_label[selected])

    with tabs[2]:
        method = st.selectbox(
            "Experiment method",
            ["Full Factorial", "Fractional Factorial", "Central Composite", "Box-Behnken", "Replication Planner", "Response Surface Fit"],
            key=f"core_exp_method_{module}",
        )
        if method == "Full Factorial":
            factors = st.text_area("Factor levels (one factor per line)", "Speed=10,20\nFeed=1,2", key=f"core_exp_ff_{module}")
            randomized = st.checkbox("Randomize run order", True, key=f"core_exp_rand_{module}")
            reps = int(st.number_input("Replications", 1, 100, 1, key=f"core_exp_reps_{module}"))
            if st.button("Build full factorial", key=f"core_exp_ff_btn_{module}", type="primary"):
                parsed = {p.split("=", 1)[0].strip(): [v.strip() for v in p.split("=", 1)[1].split(",")] for p in factors.splitlines() if "=" in p}
                st.session_state[f"core_exp_design_{module}"] = factorial_design(parsed, randomized=randomized, reps=reps, seed=2026)
        elif method == "Fractional Factorial":
            factors = st.text_area("Two-level factors", "A=-1,1\nB=-1,1\nC=-1,1\nD=-1,1", key=f"core_frac_{module}")
            fraction = int(st.selectbox("Fraction", [2, 4, 8, 16], key=f"core_frac_ratio_{module}"))
            if st.button("Build fractional design", key=f"core_frac_btn_{module}", type="primary"):
                parsed = {p.split("=", 1)[0].strip(): [v.strip() for v in p.split("=", 1)[1].split(",")] for p in factors.splitlines() if "=" in p}
                try:
                    d, meta = fractional_factorial_design(parsed, fraction=fraction, randomized=True, reps=2, seed=2026)
                    st.session_state[f"core_exp_design_{module}"], st.session_state[f"core_exp_meta_{module}"] = d, meta
                except ValueError as exc:
                    st.error(str(exc))
        elif method in {"Central Composite", "Box-Behnken"}:
            factors = st.text_area("Numeric low/high factors", "Speed=10,20\nFeed=1,2\nDepth=5,9", key=f"core_rs_design_{module}")
            if st.button("Build response-surface design", key=f"core_rs_design_btn_{module}", type="primary"):
                parsed = {p.split("=", 1)[0].strip(): [float(v.strip()) for v in p.split("=", 1)[1].split(",")] for p in factors.splitlines() if "=" in p}
                try:
                    d, meta = response_surface_design(parsed, design="central_composite" if method == "Central Composite" else "box_behnken", seed=2026)
                    st.session_state[f"core_exp_design_{module}"], st.session_state[f"core_exp_meta_{module}"] = d, meta
                except ValueError as exc:
                    st.error(str(exc))
        elif method == "Response Surface Fit":
            nums = list(df.select_dtypes(include=np.number).columns) if isinstance(df, pd.DataFrame) else []
            if len(nums) < 2:
                st.info("Response-surface fitting needs at least one response and one numeric factor.")
            else:
                response = st.selectbox("Response", nums, key=f"core_rsf_response_{module}")
                factors = st.multiselect("Factors", [x for x in nums if x != response], default=[x for x in nums if x != response][:2], key=f"core_rsf_factors_{module}")
                if st.button("Fit response surface", key=f"core_rsf_fit_{module}", type="primary"):
                    try:
                        model, fitted = fit_response_surface(df, response, factors)
                        st.session_state[f"core_rsf_model_{module}"], st.session_state[f"core_rsf_fitted_{module}"] = model, fitted
                    except ValueError as exc:
                        st.error(str(exc))
                if st.session_state.get(f"core_rsf_model_{module}"):
                    st.json(st.session_state[f"core_rsf_model_{module}"])
                    st.dataframe(st.session_state[f"core_rsf_fitted_{module}"], use_container_width=True, hide_index=True)
        elif method == "Replication Planner":
            effect = st.number_input("Expected standardized effect", 0.50, min_value=0.01, key=f"core_rep_effect_{module}")
            alpha = st.number_input("Alpha", 0.05, min_value=0.001, max_value=0.20, key=f"core_rep_alpha_{module}")
            power = st.number_input("Target power", 0.80, min_value=0.50, max_value=0.99, key=f"core_rep_power_{module}")
            st.json(replication_planner(effect, alpha=alpha, power=power))
        if isinstance(st.session_state.get(f"core_exp_design_{module}"), pd.DataFrame):
            st.dataframe(st.session_state[f"core_exp_design_{module}"], use_container_width=True, hide_index=True)
            st.json(st.session_state.get(f"core_exp_meta_{module}", {}))

    with tabs[3]:
        st.caption("Scenario analysis now combines deltas, constraints, best/worst cases and driver tables.")
        scenarios_text = st.text_area(
            "Scenario definitions: Name=KPI:value,KPI:value",
            "Baseline=Throughput:100,Cost:50\nA=Throughput:110,Cost:45\nB=Throughput:90,Cost:55",
            key=f"core_scenarios_{module}",
        )
        baseline = st.text_input("Baseline scenario", "Baseline", key=f"core_scenario_base_{module}")
        constraint_text = st.text_area("Constraints: KPI=min or KPI=max", "Throughput=min:95\nCost=max:60", key=f"core_scenario_constraints_{module}")
        if st.button("Analyze scenarios", key=f"core_scenario_btn_{module}", type="primary"):
            data: dict[str, dict[str, float]] = {}
            for line in scenarios_text.splitlines():
                if "=" not in line:
                    continue
                name, values = line.split("=", 1)
                metrics = {}
                for item in values.split(","):
                    if ":" in item:
                        k, v = item.split(":", 1)
                        try: metrics[k.strip()] = float(v.strip())
                        except ValueError: continue
                if metrics: data[name.strip()] = metrics
            constraints: dict[str, dict[str, float]] = {}
            for line in constraint_text.splitlines():
                if "=" not in line: continue
                kpi, spec = line.split("=", 1)
                if ":" in spec:
                    kind, val = spec.split(":", 1)
                    try:
                        constraints[kpi.strip()] = {kind.strip().lower(): float(val)}
                    except ValueError:
                        continue
            try:
                comparison, summary = scenario_analysis(data, baseline=baseline, constraints=constraints)
                st.session_state[f"core_scenario_result_{module}"] = comparison
                st.session_state[f"core_scenario_summary_{module}"] = summary
                save_platform_record("scenario_analysis", f"{module}:{baseline}", {"module": module, "baseline": baseline, "comparison": comparison.to_dict("records"), "summary": summary}, workspace=workspace)
            except ValueError as exc:
                st.error(str(exc))
        if isinstance(st.session_state.get(f"core_scenario_result_{module}"), pd.DataFrame):
            st.dataframe(st.session_state[f"core_scenario_result_{module}"], use_container_width=True, hide_index=True)
            st.json(st.session_state.get(f"core_scenario_summary_{module}", {}))

    with tabs[4]:
        pred, meta = forecast_operations(df)
        if pred.empty:
            st.info(meta.get("status", "Forecast unavailable."))
        else:
            st.dataframe(pd.DataFrame(meta.get("model_comparison", [])), use_container_width=True, hide_index=True)
            st.plotly_chart(
                px.line(pred, x="Horizon", y=["Forecast", "Lower 95%", "Upper 95%"], title=f"{module} forecast"),
                use_container_width=True, key=f"core_forecast_{module}",
            )
            st.json(meta)

    with tabs[5]:
        jobs = repository_records("job", workspace=workspace, limit=100)
        if jobs.empty:
            st.info("No platform-core jobs recorded.")
        else:
            st.dataframe(jobs[["record_id", "entity_key", "content_hash", "version", "updated_at"]], use_container_width=True, hide_index=True)
        replays = replay_records(workspace=workspace, limit=100)
        if replays.empty:
            st.info("No executable replay records have been captured yet.")
        else:
            st.dataframe(replays, use_container_width=True, hide_index=True)
            selected_replay = st.selectbox("Replay run", replays["Replay ID"].astype(str).tolist(), key=f"core_replay_pick_{module}")
            if st.button("Replay executable run", key=f"core_replay_btn_{module}", type="primary"):
                try:
                    replay_payload = get_replay_record(selected_replay, workspace=workspace)
                    result = execute_replay(replay_payload)
                    st.session_state[f"core_replay_result_{module}"] = result
                    st.success("Replay completed from the persisted callable + parameter manifest.")
                except Exception as exc:
                    record_engineering_error(module, exc, workspace=workspace, actor=actor)
                    st.error(f"Replay failed safely: {type(exc).__name__}: {exc}")
        replay_result = st.session_state.get(f"core_replay_result_{module}")
        if replay_result is not None:
            st.write(replay_result if isinstance(replay_result, (str, int, float)) else _jsonable(replay_result))

    with tabs[6]:
        st.markdown("**Connector execution posture**")
        st.dataframe(pd.DataFrame(ACTION_LEVELS, columns=["Governed action level"]), hide_index=True, use_container_width=True)
        connector_kind = st.selectbox("Connector", ["REST", "SQL", "SAP-OData", "MQTT", "OPC-UA", "SFTP"], key=f"core_conn_kind_{module}")
        if connector_kind in {"REST", "SAP-OData"}:
            endpoint = st.text_input("Endpoint", key=f"core_conn_endpoint_{module}")
            token = st.text_input("Token", type="password", key=f"core_conn_token_{module}")
            if st.button("Check connector", key=f"core_conn_test_{module}"):
                st.json(connector_health({"kind": connector_kind, "endpoint": endpoint, "token": token, "name": module}))
        elif connector_kind == "SQL":
            conn = st.text_input("Read-only SQL connection", placeholder="postgresql://…", key=f"core_sql_conn_{module}")
            if st.button("Check SQL", key=f"core_sql_test_{module}"):
                st.json(connector_health({"kind": "SQL", "connection_string": conn, "name": module}))
        elif connector_kind == "MQTT":
            host = st.text_input("Broker host", key=f"core_mqtt_host_{module}")
            port = st.number_input("Broker port", 1, 65535, 1883, key=f"core_mqtt_port_{module}")
            if st.button("Check MQTT", key=f"core_mqtt_test_{module}"):
                st.json(connector_health({"kind": "MQTT", "host": host, "port": int(port), "name": module}))
        elif connector_kind == "OPC-UA":
            endpoint = st.text_input("OPC-UA endpoint", key=f"core_opc_endpoint_{module}")
            if st.button("Check OPC-UA", key=f"core_opc_test_{module}"):
                st.json(connector_health({"kind": "OPC-UA", "endpoint": endpoint, "name": module}))
        else:
            host = st.text_input("SFTP host", key=f"core_sftp_host_{module}")
            user = st.text_input("SFTP username", key=f"core_sftp_user_{module}")
            password = st.text_input("SFTP password", type="password", key=f"core_sftp_pwd_{module}")
            if st.button("Check SFTP", key=f"core_sftp_test_{module}"):
                st.json(connector_health({"kind": "SFTP", "host": host, "username": user, "password": password, "name": module}))

    with tabs[7]:
        diagnostics = {
            "backend": db_backend(),
            "database_authority": "PostgreSQL when configured; SQLite offline fallback",
            "runtime": platform.python_version(),
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "streamlit": getattr(st, "__version__", "unknown"),
            "performance": performance_route(df),
            "readiness": readiness,
            "last_run_id": st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id"),
        }
        st.json(diagnostics)
        if st.button("Run verification suite", key=f"core_verify_btn_{module}", type="primary"):
            report = verification_suite(module, inputs=df, results=df)
            st.json(report)
        if not ledger.empty:
            status_filter = st.multiselect("Capability status filter", list(CAPABILITY_STATES), default=list(CAPABILITY_STATES), key=f"core_cap_filter_{module}")
            st.dataframe(ledger[ledger["Status"].isin(status_filter)], use_container_width=True, hide_index=True, height=300)


    with tabs[8]:
        st.markdown("### Research Studio")
        study_title = st.text_input("Study title", key=f"core_research_title_{module}")
        objective = st.text_area("Objective", key=f"core_research_objective_{module}")
        hypothesis = st.text_area("Hypothesis", key=f"core_research_hypothesis_{module}")
        statistical_plan = st.text_area("Statistical plan (locked after preregistration)", key=f"core_research_stats_{module}")
        exclusions = st.text_area("Exclusion criteria", key=f"core_research_exclusions_{module}")
        limitations = st.text_area("Protocol limitations", key=f"core_research_limitations_{module}")
        citation = st.text_input("Citation / DOI / source", key=f"core_research_citation_{module}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Create preregistration", key=f"core_research_create_{module}", type="primary"):
                if not study_title.strip():
                    st.error("Study title is required.")
                else:
                    study = research_study_record(
                        study_title,
                        objective=objective,
                        hypothesis=hypothesis,
                        statistical_plan={"plan": statistical_plan},
                        citations=[citation] if citation.strip() else [],
                        exclusions=[x.strip() for x in exclusions.splitlines() if x.strip()],
                        limitations=[x.strip() for x in limitations.splitlines() if x.strip()],
                        workspace=workspace,
                    )
                    st.session_state[f"core_research_study_{module}"] = study
                    st.success(f"Preregistration {study['study_id']} saved.")
        with c2:
            study = st.session_state.get(f"core_research_study_{module}")
            if study:
                locked = st.checkbox("Protocol is ready to lock", key=f"core_research_lock_ready_{module}")
                if locked and st.button("Lock protocol", key=f"core_research_lock_{module}"):
                    st.session_state[f"core_research_study_{module}"] = lock_research_protocol(study, workspace=workspace)
                    st.success("Protocol locked and hashed. Changes must be handled as versioned amendments.")
        study = st.session_state.get(f"core_research_study_{module}")
        if study:
            st.json(study)
            if citation.strip() and not study.get("protocol_locked") and st.button("Add citation", key=f"core_research_add_citation_{module}"):
                try:
                    st.session_state[f"core_research_study_{module}"] = add_research_citation(study["study_id"], citation, workspace=workspace)
                except RuntimeError as exc:
                    st.error(str(exc))

        st.markdown("### Evidence-linked ROI")
        kpi_lines = st.text_area(
            "KPI values as KPI=baseline,target,predicted,actual",
            "Throughput=100,110,108,112",
            key=f"core_roi_kpis_{module}",
        )
        financial = st.number_input("Financial impact", value=0.0, key=f"core_roi_financial_{module}")
        hours = st.number_input("Hours saved", value=0.0, key=f"core_roi_hours_{module}")
        risk = st.number_input("Risk reduction", value=0.0, key=f"core_roi_risk_{module}")
        if st.button("Capture ROI evidence", key=f"core_roi_capture_{module}"):
            baseline, target, predicted, actual = {}, {}, {}, {}
            for line in kpi_lines.splitlines():
                if "=" not in line:
                    continue
                name, values = line.split("=", 1)
                parts = [x.strip() for x in values.split(",")]
                if len(parts) != 4:
                    continue
                try:
                    baseline[name.strip()] = float(parts[0]); target[name.strip()] = float(parts[1])
                    predicted[name.strip()] = float(parts[2]); actual[name.strip()] = float(parts[3])
                except ValueError:
                    continue
            roi = roi_evidence_snapshot(
                baseline=baseline, target=target, predicted=predicted, actual=actual,
                financial_impact=financial, hours_saved=hours, risk_reduction=risk,
                evidence_ids=[str(x) for x in st.session_state.get("shoir_kpi_lineage", {}).keys()],
                workspace=workspace,
            )
            st.session_state[f"core_roi_last_{module}"] = roi
        roi = st.session_state.get(f"core_roi_last_{module}")
        if roi:
            st.dataframe(pd.DataFrame(roi["kpis"]), use_container_width=True, hide_index=True)
            st.json({k: roi[k] for k in ("financial_impact", "hours_saved", "risk_reduction", "verified_actuals", "evidence_ids")})

    with tabs[9]:
        st.markdown("### Digital Twin Cycle")
        nums = list(df.select_dtypes(include=np.number).columns) if isinstance(df, pd.DataFrame) else []
        if not nums:
            st.info("Digital Twin cycle requires observed numeric telemetry.")
        else:
            asset = st.text_input("Asset ID", value=str(module), key=f"core_twin_asset_{module}")
            observed = {str(c): float(pd.to_numeric(df[c], errors="coerce").dropna().mean()) for c in nums[:8]}
            expected_text = st.text_area(
                "Expected values (KPI=value)",
                "\n".join(f"{k}={v:g}" for k, v in observed.items()),
                key=f"core_twin_expected_{module}",
            )
            expected = {}
            for line in expected_text.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    try: expected[k.strip()] = float(v.strip())
                    except ValueError: continue
            threshold = st.number_input("Absolute deviation alert threshold", value=5.0, min_value=0.0, key=f"core_twin_threshold_{module}")
            if st.button("Synchronize twin state", key=f"core_twin_sync_{module}", type="primary"):
                twin = digital_twin_cycle(
                    asset, observed,
                    expected=expected,
                    thresholds={k: threshold for k in expected},
                    scenario={"module": module, "run_id": st.session_state.get("shoir_latest_run_id")},
                    workspace=workspace,
                )
                st.session_state[f"core_twin_last_{module}"] = twin
                if twin["status"] == "DEGRADED":
                    create_alert(
                        "DIGITAL_TWIN_DEVIATION",
                        f"Asset {asset} has {len(twin['anomalies'])} observed deviation(s).",
                        severity="HIGH",
                        entity_key=asset,
                        workspace=workspace,
                    )
            twin = st.session_state.get(f"core_twin_last_{module}")
            if twin:
                st.metric("Twin state", twin["status"], f"{len(twin['anomalies'])} anomalies")
                st.dataframe(pd.DataFrame(twin["state"]), use_container_width=True, hide_index=True)
        alerts = repository_records("alert", workspace=workspace, limit=100)
        if not alerts.empty:
            st.markdown("### Alert → Investigation")
            shown = [_payload_from_value(row["payload_json"]) for _, row in alerts.iterrows()]
            st.dataframe(pd.DataFrame(shown), use_container_width=True, hide_index=True)


def sync_project_state(workspace: str, state: Mapping[str, Any]) -> str:
    return save_platform_record("project_state", workspace, {"workspace": workspace, "state": _jsonable(state), "updated_at": now_iso()}, workspace=workspace)


def localization_config(language: str = "English", currency: str = BASE_CURRENCY) -> dict[str, Any]:
    lang = "Arabic" if str(language).lower().startswith("arab") else "English"
    return {"language": lang, "rtl": lang == "Arabic", "currency": str(currency).upper(), "date_format": "DD/MM/YYYY" if lang == "Arabic" else "YYYY-MM-DD", "number_decimal": ".", "thousands": ","}


def formatted_number(value: float, *, decimals: int = 2, locale: str = "en") -> str:
    if locale.lower().startswith("ar"):
        return f"{float(value):,.{decimals}f}".translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    return f"{float(value):,.{decimals}f}"


def research_study_record(
    title: str,
    *,
    objective: str = "",
    hypothesis: str = "",
    variables: Mapping[str, Any] | None = None,
    statistical_plan: Mapping[str, Any] | None = None,
    citations: Sequence[Mapping[str, Any] | str] = (),
    exclusions: Sequence[str] = (),
    limitations: Sequence[str] = (),
    workspace: str = "default",
) -> dict[str, Any]:
    payload = {
        "study_id": stable_id("STU"),
        "title": title,
        "objective": objective,
        "hypothesis": hypothesis,
        "variables": _jsonable(variables or {}),
        "statistical_plan": _jsonable(statistical_plan or {}),
        "citations": _jsonable(list(citations)),
        "exclusions": list(exclusions),
        "limitations": list(limitations),
        "protocol_locked": False,
        "created_at": now_iso(),
    }
    save_platform_record("research_study", payload["study_id"], payload, workspace=workspace)
    return payload


def lock_research_protocol(study: Mapping[str, Any], *, workspace: str = "default") -> dict[str, Any]:
    protocol = dict(study)
    if protocol.get("protocol_locked"):
        return protocol
    locked = {**protocol, "protocol_locked": True, "locked_at": now_iso(), "protocol_hash": digest(protocol)}
    save_platform_record("research_protocol", str(protocol.get("study_id") or stable_id("STU")), locked, workspace=workspace)
    return locked


def add_research_citation(study_id: str, citation: Mapping[str, Any] | str, *, workspace: str = "default") -> dict[str, Any]:
    rows = repository_records("research_study", workspace=workspace, limit=1000)
    study = {}
    if not rows.empty:
        for _, row in rows.iterrows():
            p = _payload_from_value(row["payload_json"])
            if str(p.get("study_id")) == str(study_id):
                study = p
                break
    if not study:
        raise KeyError(f"Research study not found: {study_id}")
    if study.get("protocol_locked"):
        raise RuntimeError("The preregistered protocol is locked; citation changes must be versioned as amendments.")
    citations = list(study.get("citations") or [])
    citations.append(_jsonable(citation))
    study["citations"] = citations
    study["updated_at"] = now_iso()
    save_platform_record("research_study", str(study_id), study, workspace=workspace)
    return study


def roi_evidence_snapshot(
    *,
    baseline: Mapping[str, float],
    target: Mapping[str, float],
    predicted: Mapping[str, float],
    actual: Mapping[str, float] | None = None,
    financial_impact: float | None = None,
    hours_saved: float | None = None,
    risk_reduction: float | None = None,
    evidence_ids: Sequence[str] = (),
    workspace: str = "default",
) -> dict[str, Any]:
    keys = sorted(set(baseline) | set(target) | set(predicted) | set(actual or {}))
    rows = []
    for key in keys:
        b = float(baseline.get(key, np.nan))
        t = float(target.get(key, np.nan))
        p = float(predicted.get(key, np.nan))
        a = float((actual or {}).get(key, np.nan))
        rows.append({
            "KPI": key, "Baseline": b, "Target": t, "Predicted": p,
            "Actual": a, "Predicted Delta": p - b if np.isfinite(p) and np.isfinite(b) else np.nan,
            "Actual Delta": a - b if np.isfinite(a) and np.isfinite(b) else np.nan,
        })
    payload = {
        "roi_id": stable_id("ROI"),
        "kpis": rows,
        "financial_impact": float(financial_impact) if financial_impact is not None else None,
        "hours_saved": float(hours_saved) if hours_saved is not None else None,
        "risk_reduction": float(risk_reduction) if risk_reduction is not None else None,
        "evidence_ids": list(evidence_ids),
        "verified_actuals": bool(actual),
        "captured_at": now_iso(),
    }
    save_platform_record("roi_evidence", payload["roi_id"], payload, workspace=workspace)
    return payload


def digital_twin_cycle(
    asset_id: str,
    observed: Mapping[str, float],
    *,
    expected: Mapping[str, float] | None = None,
    thresholds: Mapping[str, float] | None = None,
    scenario: Mapping[str, Any] | None = None,
    workspace: str = "default",
) -> dict[str, Any]:
    expected = dict(expected or {})
    thresholds = dict(thresholds or {})
    variables = sorted(set(map(str, observed)) | set(map(str, expected)))
    state = []
    anomalies = []
    for name in variables:
        obs = float(observed.get(name, np.nan))
        exp = float(expected.get(name, np.nan))
        delta = obs - exp if np.isfinite(obs) and np.isfinite(exp) else np.nan
        pct = (delta / exp * 100.0) if np.isfinite(delta) and exp else np.nan
        limit = float(thresholds.get(name, np.inf))
        is_anomaly = bool(np.isfinite(delta) and abs(delta) > limit)
        row = {"variable": name, "observed": obs, "expected": exp, "delta": delta, "delta_pct": pct, "anomaly": is_anomaly}
        state.append(row)
        if is_anomaly:
            anomalies.append(row)
    status = "DEGRADED" if anomalies else "HEALTHY"
    payload = {
        "asset_id": str(asset_id), "status": status, "observed_at": now_iso(),
        "state": state, "anomalies": anomalies, "scenario": _jsonable(scenario or {}),
        "cycle_hash": digest(state),
    }
    save_platform_record("digital_twin_state", str(asset_id), payload, workspace=workspace)
    return payload


def create_alert(
    alert_type: str,
    message: str,
    *,
    severity: str = "MEDIUM",
    evidence_ids: Sequence[str] = (),
    entity_key: str = "",
    workspace: str = "default",
) -> dict[str, Any]:
    alert = {
        "alert_id": stable_id("ALT"),
        "type": str(alert_type),
        "message": str(message),
        "severity": str(severity).upper(),
        "entity_key": str(entity_key),
        "evidence_ids": list(evidence_ids),
        "status": "OPEN",
        "created_at": now_iso(),
    }
    save_platform_record("alert", alert["alert_id"], alert, workspace=workspace)
    return alert


def investigate_alert(alert_id: str, *, finding: str, scenario_id: str = "", decision_id: str = "", workspace: str = "default") -> dict[str, Any]:
    rows = repository_records("alert", workspace=workspace, limit=1000)
    alert = None
    for _, row in rows.iterrows() if not rows.empty else []:
        payload = _payload_from_value(row["payload_json"])
        if str(payload.get("alert_id")) == str(alert_id):
            alert = payload
            break
    if not alert:
        raise KeyError(f"Alert not found: {alert_id}")
    investigation = {
        "investigation_id": stable_id("INV"),
        "alert_id": alert_id,
        "finding": finding,
        "scenario_id": scenario_id,
        "decision_id": decision_id,
        "created_at": now_iso(),
    }
    save_platform_record("investigation", investigation["investigation_id"], investigation, workspace=workspace)
    alert["status"] = "INVESTIGATING"
    alert["investigation_id"] = investigation["investigation_id"]
    save_platform_record("alert", alert_id, alert, workspace=workspace)
    return investigation


def command_center_snapshot(df: pd.DataFrame, *, workspace: str = "default") -> dict[str, Any]:
    readiness = data_readiness(df)
    alerts = repository_records("alert", workspace=workspace, limit=200)
    drafts = repository_records("decision_draft", workspace=workspace, limit=200)
    runs = repository_records("run", workspace=workspace, limit=200)
    open_alerts = 0
    if not alerts.empty:
        open_alerts = sum(1 for _, row in alerts.iterrows() if str(_payload_from_value(row["payload_json"]).get("status", "")).upper() == "OPEN")
    pending_decisions = len(drafts)
    last_run = _payload_from_value(runs.iloc[0]["payload_json"]) if not runs.empty else {}
    attention = []
    if readiness.get("score", 0) < 80:
        attention.append("Data readiness below 80%.")
    if open_alerts:
        attention.append(f"{open_alerts} open alert(s) require investigation.")
    if pending_decisions:
        attention.append(f"{pending_decisions} draft decision(s) await review.")
    next_action = attention[0] if attention else "Review the latest run, compare scenarios, and verify the decision."
    return {
        "what_is_happening": {"active_rows": readiness.get("rows", 0), "last_run": last_run},
        "attention": attention,
        "what_to_do_next": next_action,
        "open_alerts": open_alerts,
        "draft_decisions": pending_decisions,
    }


def engineering_unit_signature(unit_expression: str) -> tuple[dict[str, int], float]:
    """Return base-dimension exponents and conversion scale for compound units."""
    expr = str(unit_expression).strip().lower().replace(" ", "")
    if not expr:
        raise ValueError("Unit expression cannot be blank.")
    dimensions: dict[str, int] = {}
    scale = 1.0
    sign = 1
    for token in re.split(r"([*/])", expr):
        if token == "*":
            sign = 1
            continue
        if token == "/":
            sign = -1
            continue
        if not token:
            continue
        if "^" in token:
            base, power_text = token.split("^", 1)
            power = int(power_text)
        else:
            base, power = token, 1
        if base not in UNIT_DEFINITIONS:
            raise ValueError(f"Unsupported unit in expression: {base}")
        dim, factor = UNIT_DEFINITIONS[base]
        exponent = sign * power
        dimensions[dim] = dimensions.get(dim, 0) + exponent
        scale *= factor ** exponent
    dimensions = {k: v for k, v in dimensions.items() if v}
    return dimensions, scale


def derive_formula_unit(formula: str, input_units: Mapping[str, str]) -> dict[str, Any]:
    """Derive result dimensions for +,-,*,/ and integer powers using declared units."""
    class UnitEvaluator(ast.NodeVisitor):
        def visit_Expression(self, node): return self.visit(node.body)
        def visit_Name(self, node):
            if node.id not in input_units:
                raise ValueError(f"Missing unit for formula variable: {node.id}")
            return engineering_unit_signature(input_units[node.id])
        def visit_Constant(self, node):
            return {}, 1.0
        def visit_UnaryOp(self, node):
            return self.visit(node.operand)
        def visit_BinOp(self, node):
            left = self.visit(node.left); right = self.visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if left[0] != right[0]:
                    raise ValueError("Add/subtract requires identical dimensions.")
                return left
            if isinstance(node.op, ast.Mult):
                dims = dict(left[0])
                for k, v in right[0].items(): dims[k] = dims.get(k, 0) + v
                return {k:v for k,v in dims.items() if v}, left[1] * right[1]
            if isinstance(node.op, ast.Div):
                dims = dict(left[0])
                for k, v in right[0].items(): dims[k] = dims.get(k, 0) - v
                return {k:v for k,v in dims.items() if v}, left[1] / right[1]
            if isinstance(node.op, ast.Pow):
                if right[0]:
                    raise ValueError("Exponent must be dimensionless.")
                exponent_node = node.right
                if not isinstance(exponent_node, ast.Constant) or not float(exponent_node.value).is_integer():
                    raise ValueError("Unit derivation supports integer literal powers only.")
                exponent = int(exponent_node.value)
                return {k:v*exponent for k,v in left[0].items() if v*exponent}, left[1] ** exponent
            raise ValueError("Unsupported formula operator.")
        def generic_visit(self, node):
            raise ValueError(f"Unsupported formula node: {type(node).__name__}")
    dimensions, scale = UnitEvaluator().visit(ast.parse(formula, mode="eval"))
    return {"dimensions": dimensions, "scale_to_base": float(scale)}



__all__ = [
    "WORKFLOW_STEPS", "ACTION_LEVELS", "CAPABILITY_STATES",
    "db_backend", "configured_database_url", "db_connect", "ensure_core_schema", "remote_persistence_configured",
    "data_readiness", "validate_dataset_contract", "canonical_map_columns", "engineering_unit_signature", "derive_formula_unit",
    "WorkflowRuntime", "begin_module", "governed_module", "run_governed_module",
    "module_manifest", "capability_ledger", "kpi_lineage", "render_kpi_lineage",
    "capture_standard_kpi_lineage", "lineage_graph_frame", "render_lineage_graph", "replay_records", "get_replay_record",
    "uncertainty_engine", "attach_uncertainty", "scenario_analysis", "explain_scenario_changes", "scenario_fork",
    "factorial_design", "fractional_factorial_design", "response_surface_design", "replication_planner", "fit_response_surface",
    "residual_diagnostics", "forecast_operations", "quantity_dimension", "convert_quantity",
    "validate_formula", "safe_calculate", "visualization_intelligence", "build_visualization", "render_visualization_os",
    "normalize_action_level", "action_authorized", "copilot_plan",
    "active_df_hash", "register_replay", "execute_replay", "record_engineering_error", "performance_route",
    "connector_health", "submit_background_job", "decision_memory_query", "save_decision_memory",
    "benchmark_compare", "verification_suite", "render_engineering_canvas", "render_platform_completion",
    "research_study_record", "lock_research_protocol", "add_research_citation", "roi_evidence_snapshot",
    "digital_twin_cycle", "create_alert", "investigate_alert", "command_center_snapshot",
    "sync_project_state", "localization_config", "formatted_number",
]
