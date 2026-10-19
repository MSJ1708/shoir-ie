"""Shoir-IE shared experience layer.

Provides a consistent command deck, persistence, verification and evidence
surfaces for engineering modules without replacing their specialist logic.
"""
from __future__ import annotations

import gzip
import hashlib
import html
import io
import math
import json
import sqlite3
import time
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd
import plotly.express as px

from shoir_experiment_engine import render_experiment_engine
from shoir_module_customization import (
    apply_display_labels,
    default_module_profile,
    display_field_label,
    get_module_profile,
)

try:
    from durable_account_store import (
        durable_backend_configured,
        ensure_remote_research_schema,
        upsert_remote_research_study,
        remote_research_study,
        remote_research_studies,
        upsert_remote_research_run,
        remote_research_runs,
    )
except Exception:  # Local/unit-test fallback when the durable module is unavailable.
    durable_backend_configured = lambda: False
    ensure_remote_research_schema = lambda: None
    upsert_remote_research_study = lambda *_args, **_kwargs: None
    remote_research_study = lambda *_args, **_kwargs: None
    remote_research_studies = lambda *_args, **_kwargs: []
    upsert_remote_research_run = lambda *_args, **_kwargs: None
    remote_research_runs = lambda *_args, **_kwargs: []



FEATURES_60 = [
    ("01", "Canonical industrial data model", "Shared industrial entities and identifiers.", "Implemented"),
    ("02", "Digital thread", "Explicit relationships and impact tracing.", "Implemented"),
    ("03", "Units & dimensional analysis", "Unit metadata and validation hooks.", "Implemented"),
    ("04", "Currency / FX normalization", "Configurable currency normalization.", "Implemented"),
    ("05", "Dataset contracts", "Reusable schema and rule contracts.", "Implemented"),
    ("06", "Data quality gates", "Quality scoring before analysis.", "Implemented"),
    ("07", "Data lineage", "Source-to-decision provenance.", "Implemented"),
    ("08", "Engineering model registry", "Versioned model snapshots and hashes.", "Implemented"),
    ("09", "Reproducibility manifests", "Run metadata and evidence manifests.", "Implemented"),
    ("10", "Experiment lab", "Persisted controlled scenario studies.", "Implemented"),
    ("11", "DOE / factorial analysis", "Controlled factor-study workspace hooks.", "Implemented"),
    ("12", "Replication / confidence tracking", "Replication and confidence metadata.", "Implemented"),
    ("13", "Monte Carlo workflows", "Structured stochastic run surfaces.", "Implemented"),
    ("14", "Scenario sweeps", "Batch alternative comparison surfaces.", "Implemented"),
    ("15", "Background job registry", "Durable queued/running/completed jobs.", "Implemented"),
    ("16", "Cancel / resume controls", "Durable operator run-state controls.", "Implemented"),
    ("17", "E2E test hooks", "Stable keys for browser workflows.", "Implemented"),
    ("18", "Visual regression hooks", "Stable shell classes and empty states.", "Implemented"),
    ("19", "Accessibility", "Clear labels, hierarchy and reduced motion.", "Implemented"),
    ("20", "Arabic / RTL readiness", "Persisted locale/direction preference.", "Implemented"),
    ("21", "Command palette", "Global module/action search foundation.", "Implemented"),
    ("22", "Universal search", "Searchable engineering workspace foundation.", "Implemented"),
    ("23", "Saved studies / projects", "Durable studies with ownership.", "Implemented"),
    ("24", "Autosave / recovery", "Timestamped project snapshots.", "Implemented"),
    ("25", "Undo / redo foundation", "Snapshot history for future UI controls.", "Implemented"),
    ("26", "Unified decision objects", "Common decision schema.", "Implemented"),
    ("27", "Impact graph", "Relationship-based impact tracing.", "Implemented"),
    ("28", "Copilot tool registry", "Governed tool catalog.", "Implemented"),
    ("29", "Copilot evidence ledger", "Auditable Copilot action records.", "Implemented"),
    ("30", "Prompt-injection guardrails", "Imported text remains data; actions need approval.", "Implemented"),
    ("31", "Connector profiles", "Connector metadata and configuration.", "Implemented"),
    ("32", "Connector freshness health", "Latency, error and freshness fields.", "Implemented"),
    ("33", "Time-series telemetry", "Timestamped asset measurements.", "Implemented"),
    ("34", "DB migration discipline", "Idempotent persistent schema setup.", "Implemented"),
    ("35", "Backup / restore", "Evidence bundle and restore-ready export.", "Implemented"),
    ("36", "Observability", "Run IDs and duration records.", "Implemented"),
    ("37", "Human-readable error states", "Operator-focused diagnostics.", "Implemented"),
    ("38", "Numerical verification", "Finite-value and shape checks.", "Implemented"),
    ("39", "Conservation / balance checks", "Configurable balance validation hook.", "Implemented"),
    ("40", "Benchmark datasets", "Source/date benchmark metadata.", "Implemented"),
    ("41", "Evidence-based ROI calculator", "Transparent assumption-driven value model.", "Implemented"),
    ("42", "Executive reporting pack", "Executive evidence export surface.", "Implemented"),
    ("43", "Engineering reporting pack", "Detailed engineering evidence export.", "Implemented"),
    ("44", "Audit / research pack", "Manifest and lineage evidence.", "Implemented"),
    ("45", "Onboarding", "Starter workflow and template foundation.", "Implemented"),
    ("46", "Guided workflows / templates", "Reusable engineering starters.", "Implemented"),
    ("47", "Module maturity indicators", "Readiness and capability status.", "Implemented"),
    ("48", "Cross-module recommendations", "Rule-based next-step foundation.", "Implemented"),
    ("49", "Approval workflow", "Draft through Verified decision lifecycle.", "Implemented"),
    ("50", "Collaboration / comments", "Persisted workspace comments.", "Implemented"),
    ("51", "Multi-tenant foundation", "Workspace ownership fields.", "Implemented"),
    ("52", "Secret-management guidance", "Secrets excluded from experience persistence.", "Implemented"),
    ("53", "Docker / on-prem readiness", "Deployment integration hooks.", "Integration-ready"),
    ("54", "Security scanning hooks", "CI security integration hooks.", "Integration-ready"),
    ("55", "Performance benchmark harness", "Run timing and row-volume metadata.", "Implemented"),
    ("56", "Plugin registry", "Optional engineering adapter registry.", "Implemented"),
    ("57", "Model marketplace / certification", "Model validation/certification metadata.", "Implemented"),
    ("58", "Self-diagnosing platform", "Platform health surfaces.", "Implemented"),
    ("59", "Industrial Decision Memory", "Problem-to-lesson decision history.", "Implemented"),
    ("60", "Universal export / download", "One-click evidence bundle.", "Implemented"),
]

COPILOT_TOOLS = [
    ("Validate dataset", "Data", "Approval before model execution"),
    ("Clean workbook", "Data", "Approval before overwrite"),
    ("Register model snapshot", "Governance", "Approval required"),
    ("Run scenario sweep", "Experiment", "Approval required"),
    ("Score model health", "Verification", "Approval required"),
    ("Create decision card", "Decision", "Approval required"),
    ("Prepare executive report", "Reporting", "Approval required"),
    ("Export evidence bundle", "Reporting", "Approval required"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db(path: str = "enterprise_full_workspace.db"):
    return sqlite3.connect(path, timeout=30)


def ensure_experience_db(path: str = "enterprise_full_workspace.db") -> None:
    with _db(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        statements = [
            "CREATE TABLE IF NOT EXISTS experience_projects(project_id TEXT PRIMARY KEY,name TEXT,module TEXT,owner TEXT,status TEXT,payload_json TEXT,created_at TEXT,updated_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_project_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT,snapshot_no INTEGER,payload_json TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_lineage(id INTEGER PRIMARY KEY AUTOINCREMENT,source_type TEXT,source_id TEXT,target_type TEXT,target_id TEXT,relation TEXT,actor TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_decisions(decision_id TEXT PRIMARY KEY,title TEXT,module TEXT,status TEXT,metrics_json TEXT,assumptions_json TEXT,uncertainty_json TEXT,owner TEXT,created_at TEXT,updated_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_decision_specs(decision_id TEXT PRIMARY KEY,baseline_json TEXT,alternatives_json TEXT,constraints_json TEXT,kpis_json TEXT,uncertainty_json TEXT,evidence_json TEXT,verification_json TEXT,owner TEXT,created_at TEXT,updated_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_decision_approvals(id INTEGER PRIMARY KEY AUTOINCREMENT,decision_id TEXT,from_status TEXT,to_status TEXT,actor TEXT,comment TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_comments(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT,decision_id TEXT,actor TEXT,comment TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_decision_outcomes(outcome_id TEXT PRIMARY KEY,decision_id TEXT NOT NULL,owner TEXT NOT NULL,implementation_status TEXT NOT NULL,predicted_json TEXT NOT NULL,actual_json TEXT NOT NULL,variance_json TEXT NOT NULL,lesson TEXT,verified_at TEXT,created_at TEXT)",
            "CREATE INDEX IF NOT EXISTS idx_exp_decision_outcomes_decision ON experience_decision_outcomes(decision_id,created_at DESC)",
            "CREATE TABLE IF NOT EXISTS experience_jobs(job_id TEXT PRIMARY KEY,module TEXT,job_type TEXT,status TEXT,progress REAL,message TEXT,payload_json TEXT,started_at TEXT,finished_at TEXT,owner TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_copilot_actions(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,module TEXT,action TEXT,status TEXT,requires_approval INTEGER,evidence_json TEXT,actor TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_observability(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,module TEXT,event_type TEXT,duration_ms REAL,details_json TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_module_runs(run_id TEXT PRIMARY KEY,module TEXT NOT NULL,owner TEXT NOT NULL,display_name TEXT NOT NULL,project_name TEXT,site_name TEXT,input_hash TEXT NOT NULL,input_rows INTEGER NOT NULL,input_columns_json TEXT NOT NULL,result_columns_json TEXT NOT NULL,input_snapshot_gzip BLOB,result_snapshot_gzip BLOB,profile_json TEXT NOT NULL,metrics_json TEXT NOT NULL,method TEXT,guardrail TEXT,duration_ms REAL NOT NULL,status TEXT NOT NULL,snapshot_status TEXT NOT NULL,created_at TEXT NOT NULL)",
            "CREATE INDEX IF NOT EXISTS idx_exp_module_runs_owner ON experience_module_runs(owner,module,created_at DESC)",
            "CREATE TABLE IF NOT EXISTS experience_memory(memory_id TEXT PRIMARY KEY,problem TEXT,data_ref TEXT,model_ref TEXT,scenario_ref TEXT,decision_ref TEXT,actual_result TEXT,lesson TEXT,owner TEXT,created_at TEXT,updated_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_research_studies(study_id TEXT PRIMARY KEY,research_id TEXT UNIQUE,title TEXT,objective TEXT,research_question TEXT,hypothesis TEXT,null_hypothesis TEXT,methodology TEXT,primary_domain TEXT,transfer_domain TEXT,primary_endpoint TEXT,secondary_metrics_json TEXT,independent_variables_json TEXT,controls_json TEXT,baseline_definition TEXT,treatment_definition TEXT,sample_size INTEGER,replications INTEGER,random_seed INTEGER,alpha REAL,confidence_level REAL,planned_tests_json TEXT,inclusion_criteria TEXT,exclusion_criteria TEXT,data_source TEXT,protocol_notes TEXT,protocol_hash TEXT,protocol_locked INTEGER DEFAULT 0,owner TEXT,created_at TEXT,updated_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_research_runs(run_id TEXT PRIMARY KEY,study_id TEXT NOT NULL,research_id TEXT NOT NULL,owner TEXT NOT NULL,experiment_code TEXT NOT NULL,config_json TEXT NOT NULL,summary_json TEXT NOT NULL,results_csv TEXT NOT NULL,created_at TEXT NOT NULL)",
            "CREATE INDEX IF NOT EXISTS idx_exp_research_runs_study ON experience_research_runs(study_id,created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_exp_research_owner ON experience_research_studies(owner,created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_exp_research_hash ON experience_research_studies(protocol_hash)",
            "CREATE TABLE IF NOT EXISTS experience_preferences(username TEXT PRIMARY KEY,locale TEXT DEFAULT 'en',direction TEXT DEFAULT 'ltr',reduced_motion INTEGER DEFAULT 0,density TEXT DEFAULT 'comfortable',updated_at TEXT)",
            "CREATE INDEX IF NOT EXISTS idx_exp_jobs_status ON experience_jobs(status,started_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_exp_lineage_source ON experience_lineage(source_type,source_id)",
        ]
        for statement in statements:
            conn.execute(statement)
        # Backward-compatible migration: keep prior rows with owner=NULL.
        job_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(experience_jobs)")}
        if "owner" not in job_columns:
            conn.execute("ALTER TABLE experience_jobs ADD COLUMN owner TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_exp_jobs_owner_status "
            "ON experience_jobs(owner,status,started_at DESC)"
        )
        conn.commit()


def feature_catalog() -> pd.DataFrame:
    return pd.DataFrame(FEATURES_60, columns=["ID", "Feature", "Description", "Status"])


def feature_stats() -> dict:
    df = feature_catalog()
    return {
        "total": int(len(df)),
        "implemented": int((df["Status"] == "Implemented").sum()),
        "integration_ready": int((df["Status"] == "Integration-ready").sum()),
    }


def save_project(name: str, module: str, owner: str, payload: Mapping[str, Any]) -> str:
    ensure_experience_db()
    pid = "PRJ-" + uuid.uuid4().hex[:12].upper()
    stamp = _now()
    raw = json.dumps(dict(payload), sort_keys=True, default=str)
    with _db() as conn:
        conn.execute(
            "INSERT INTO experience_projects VALUES(?,?,?,?,?,?,?,?)",
            (pid, str(name).strip()[:160], module, owner, "Draft", raw, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO experience_project_snapshots(project_id,snapshot_no,payload_json,created_at) VALUES(?,?,?,?)",
            (pid, 1, raw, stamp),
        )
        conn.commit()
    return pid


def autosave_project(project_id: str, payload: Mapping[str, Any]) -> int:
    ensure_experience_db()
    raw = json.dumps(dict(payload), sort_keys=True, default=str)
    with _db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(snapshot_no),0) FROM experience_project_snapshots WHERE project_id=?",
            (project_id,),
        ).fetchone()
        number = int(row[0]) + 1
        stamp = _now()
        conn.execute(
            "INSERT INTO experience_project_snapshots(project_id,snapshot_no,payload_json,created_at) VALUES(?,?,?,?)",
            (project_id, number, raw, stamp),
        )
        conn.execute(
            "UPDATE experience_projects SET payload_json=?,updated_at=? WHERE project_id=?",
            (raw, stamp, project_id),
        )
        conn.commit()
    return number


def register_lineage(source_type: str, source_id: str, target_type: str, target_id: str, relation: str, actor: str) -> None:
    ensure_experience_db()
    with _db() as conn:
        conn.execute(
            "INSERT INTO experience_lineage(source_type,source_id,target_type,target_id,relation,actor,created_at) VALUES(?,?,?,?,?,?,?)",
            (source_type, source_id, target_type, target_id, relation, actor, _now()),
        )
        conn.commit()


def create_decision(
    title: str,
    module: str,
    metrics: Mapping[str, Any],
    assumptions: Mapping[str, Any],
    uncertainty: Mapping[str, Any],
    owner: str,
    status: str = "Draft",
    db_path: str = "enterprise_full_workspace.db",
) -> str:
    ensure_experience_db(db_path)
    did = "DEC-" + uuid.uuid4().hex[:12].upper()
    stamp = _now()
    with _db(db_path) as conn:
        conn.execute(
            "INSERT INTO experience_decisions VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                did,
                str(title)[:180],
                module,
                status,
                json.dumps(dict(metrics), default=str),
                json.dumps(dict(assumptions), default=str),
                json.dumps(dict(uncertainty), default=str),
                owner,
                stamp,
                stamp,
            ),
        )
        conn.commit()
    return did

def save_decision_spec(
    decision_id: str,
    owner: str,
    baseline: Mapping[str, Any],
    alternatives: Any,
    constraints: Mapping[str, Any],
    kpis: Any,
    uncertainty: Mapping[str, Any],
    evidence: Any,
    verification: Any,
) -> None:
    """Persist the richer decision card specification beside the governed status record."""
    ensure_experience_db()
    now = _now()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO experience_decision_specs(
                decision_id,baseline_json,alternatives_json,constraints_json,
                kpis_json,uncertainty_json,evidence_json,verification_json,
                owner,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(decision_id) DO UPDATE SET
                baseline_json=excluded.baseline_json,
                alternatives_json=excluded.alternatives_json,
                constraints_json=excluded.constraints_json,
                kpis_json=excluded.kpis_json,
                uncertainty_json=excluded.uncertainty_json,
                evidence_json=excluded.evidence_json,
                verification_json=excluded.verification_json,
                updated_at=excluded.updated_at
            """,
            (
                str(decision_id),
                json.dumps(dict(baseline or {}), default=str),
                json.dumps(alternatives if isinstance(alternatives, list) else list(alternatives or []), default=str),
                json.dumps(dict(constraints or {}), default=str),
                json.dumps(kpis if isinstance(kpis, list) else list(kpis or []), default=str),
                json.dumps(dict(uncertainty or {}), default=str),
                json.dumps(evidence if isinstance(evidence, list) else list(evidence or []), default=str),
                json.dumps(verification if isinstance(verification, list) else list(verification or []), default=str),
                str(owner),
                now,
                now,
            ),
        )
        conn.commit()


def load_decision_spec(decision_id: str, owner: str | None = None) -> dict[str, Any] | None:
    ensure_experience_db()
    query = (
        "SELECT baseline_json,alternatives_json,constraints_json,kpis_json,"
        "uncertainty_json,evidence_json,verification_json,owner,updated_at "
        "FROM experience_decision_specs WHERE decision_id=?"
    )
    params: list[Any] = [str(decision_id)]
    if owner is not None:
        query += " AND owner=?"
        params.append(str(owner))
    with _db() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    keys = ["baseline","alternatives","constraints","kpis","uncertainty","evidence","verification","owner","updated_at"]
    out: dict[str, Any] = {}
    for key, raw in zip(keys, row):
        if key in {"owner","updated_at"}:
            out[key] = raw
            continue
        try:
            out[key] = json.loads(raw or ("{}" if key in {"baseline","constraints","uncertainty"} else "[]"))
        except Exception:
            out[key] = {} if key in {"baseline","constraints","uncertainty"} else []
    return out


def decision_approval_history(decision_id: str, owner: Optional[str] = None) -> pd.DataFrame:
    """Return approval events, optionally restricted to the decision owner."""
    ensure_experience_db()
    with _db() as conn:
        if owner is not None:
            rows = conn.execute(
                """
                SELECT a.from_status,a.to_status,a.actor,a.comment,a.created_at
                FROM experience_decision_approvals AS a
                JOIN experience_decisions AS d ON d.decision_id=a.decision_id
                WHERE a.decision_id=? AND d.owner=?
                ORDER BY a.id ASC
                """,
                (str(decision_id), str(owner)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT from_status,to_status,actor,comment,created_at
                FROM experience_decision_approvals
                WHERE decision_id=?
                ORDER BY id ASC
                """,
                (str(decision_id),),
            ).fetchall()
    return pd.DataFrame(rows, columns=["From","To","Actor","Comment","Timestamp"]) if rows else pd.DataFrame(
        columns=["From","To","Actor","Comment","Timestamp"]
    )


def transition_decision(
    decision_id: str,
    actor: str,
    to_status: str,
    comment: str = "",
    require_owner: bool = False,
) -> None:
    """Transition a decision; user-facing surfaces can enforce decision ownership."""
    states = ["Draft", "Validated", "Proposed", "Review", "Approved", "Implemented", "Verified"]
    if to_status not in states:
        raise ValueError("Invalid approval state.")
    with _db() as conn:
        row = conn.execute(
            "SELECT status,owner FROM experience_decisions WHERE decision_id=?",
            (decision_id,),
        ).fetchone()
        if not row:
            raise ValueError("Decision not found.")
        current, owner = str(row[0]), row[1]
        if require_owner and (owner is None or str(owner) != str(actor)):
            raise PermissionError("Decision not found or not owned by this user.")
        if current in states and states.index(to_status) < states.index(current) and to_status not in {"Draft", "Review"}:
            raise ValueError("Decision cannot move backward to that state.")
        if require_owner:
            cursor = conn.execute(
                "UPDATE experience_decisions SET status=?,updated_at=? WHERE decision_id=? AND owner=?",
                (to_status, _now(), decision_id, str(actor)),
            )
            if cursor.rowcount == 0:
                raise PermissionError("Decision not found or not owned by this user.")
        else:
            conn.execute(
                "UPDATE experience_decisions SET status=?,updated_at=? WHERE decision_id=?",
                (to_status, _now(), decision_id),
            )
        conn.execute(
            "INSERT INTO experience_decision_approvals(decision_id,from_status,to_status,actor,comment,created_at) VALUES(?,?,?,?,?,?)",
            (decision_id, current, to_status, actor, str(comment)[:500], _now()),
        )
        conn.commit()


def calculate_decision_variance(predicted: Mapping[str, Any], actual: Mapping[str, Any]) -> pd.DataFrame:
    """Compare predicted and observed KPI values using the shared decision schema."""
    predicted = dict(predicted or {})
    actual = dict(actual or {})
    rows = []
    for name in sorted(set(predicted) & set(actual)):
        try:
            p = float(predicted[name])
            a = float(actual[name])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(p) and math.isfinite(a)):
            continue
        delta = a - p
        delta_pct = (delta / p * 100.0) if p != 0 else None
        rows.append({
            "KPI": str(name),
            "Predicted": p,
            "Actual": a,
            "Delta": delta,
            "Delta %": delta_pct,
            "Absolute Error": abs(delta),
        })
    return pd.DataFrame(rows, columns=["KPI","Predicted","Actual","Delta","Delta %","Absolute Error"])


def record_decision_outcome(
    decision_id: str,
    owner: str,
    implementation_status: str,
    predicted: Mapping[str, Any],
    actual: Mapping[str, Any],
    lesson: str = "",
    verified_at: Optional[str] = None,
    workspace: str = "default",
    db_path: str = "enterprise_full_workspace.db",
    persist_artifact: bool = True,
) -> str:
    """Persist implementation outcome evidence and link it to Decision Memory."""
    ensure_experience_db(db_path)
    decision_id = str(decision_id).strip()
    owner = str(owner).strip()
    status = str(implementation_status).strip()
    if status not in {"Planned", "Implemented", "Verified"}:
        raise ValueError("Invalid implementation status.")
    with _db(db_path) as conn:
        row = conn.execute("SELECT owner FROM experience_decisions WHERE decision_id=?", (decision_id,)).fetchone()
        if not row:
            raise ValueError("Decision not found.")
        if str(row[0]) != owner:
            raise PermissionError("Decision belongs to another workspace owner.")
    variance = calculate_decision_variance(predicted, actual)
    outcome_id = "OUT-" + uuid.uuid4().hex[:12].upper()
    now = _now()
    actual_payload = dict(actual or {})
    predicted_payload = dict(predicted or {})
    variance_payload = variance.to_dict("records")
    with _db(db_path) as conn:
        conn.execute(
            "INSERT INTO experience_decision_outcomes VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                outcome_id, decision_id, owner, status,
                json.dumps(predicted_payload, default=str, sort_keys=True),
                json.dumps(actual_payload, default=str, sort_keys=True),
                json.dumps(variance_payload, default=str),
                str(lesson or "")[:2000], str(verified_at or "") or None, now,
            ),
        )
        if lesson or actual_payload:
            conn.execute(
                "INSERT INTO experience_memory(memory_id,problem,data_ref,model_ref,scenario_ref,decision_ref,actual_result,lesson,owner,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "MEM-" + uuid.uuid4().hex[:12].upper(),
                    decision_id, "", "", "", decision_id,
                    json.dumps(actual_payload, default=str, sort_keys=True),
                    str(lesson or "")[:2000], owner, now, now,
                ),
            )
        conn.commit()
    if persist_artifact:
        try:
            from shoir_enterprise_layer import record_artifact
            record_artifact(
                owner,
                "decision_outcome",
                outcome_id,
                {
                    "decision_id": decision_id,
                    "implementation_status": status,
                    "predicted": predicted_payload,
                    "actual": actual_payload,
                    "variance": variance_payload,
                    "lesson": str(lesson or "")[:2000],
                },
                workspace,
            )
        except Exception:
            pass

    # Close the loop in the canonical Digital Thread: Decision → Outcome.
    try:
        from shoir_enterprise_layer import (
            upsert_canonical_entity, upsert_canonical_relationship, record_canonical_event,
        )
        decision_entity = upsert_canonical_entity(
            owner, "Decision", decision_id, f"decision:{decision_id}",
            state={"decision_id": decision_id, "status": status},
            status="Implemented" if status == "Implemented" else "Verified" if status == "Verified" else "Proposed",
            workspace=workspace,
        )
        outcome_entity = upsert_canonical_entity(
            owner, "Outcome", outcome_id, f"outcome:{outcome_id}",
            state={
                "decision_id": decision_id,
                "implementation_status": status,
                "predicted": predicted_payload,
                "actual": actual_payload,
                "variance": variance_payload,
                "lesson": str(lesson or "")[:2000],
            },
            status=status,
            workspace=workspace,
        )
        relationship_id = upsert_canonical_relationship(
            owner,
            decision_entity,
            outcome_entity,
            "decision has verified outcome",
            status="Verified" if status == "Verified" else "Linked",
            metadata={"outcome_id": outcome_id},
            workspace=workspace,
        )
        record_canonical_event(
            owner,
            "decision_outcome_recorded",
            {
                "decision_id": decision_id,
                "outcome_id": outcome_id,
                "implementation_status": status,
                "kpi_count": len(variance_payload),
            },
            entity_id=outcome_entity,
            relationship_id=relationship_id,
            workspace=workspace,
        )
    except Exception:
        pass
    return outcome_id


def decision_outcomes_frame(
    decision_id: Optional[str] = None,
    owner: Optional[str] = None,
    db_path: str = "enterprise_full_workspace.db",
) -> pd.DataFrame:
    ensure_experience_db(db_path)
    query = "SELECT outcome_id,decision_id,owner,implementation_status,predicted_json,actual_json,variance_json,lesson,verified_at,created_at FROM experience_decision_outcomes"
    clauses = []
    params = []
    if decision_id is not None:
        clauses.append("decision_id=?")
        params.append(str(decision_id))
    if owner is not None:
        clauses.append("owner=?")
        params.append(str(owner))
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"
    with _db(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params)

def decision_to_value_frame(
    owner: Optional[str] = None,
    decision_id: Optional[str] = None,
    db_path: str = "enterprise_full_workspace.db",
) -> pd.DataFrame:
    """Flatten decision → implementation → actual → variance → lesson evidence."""
    outcomes = decision_outcomes_frame(decision_id=decision_id, owner=owner, db_path=db_path)
    if outcomes.empty:
        return pd.DataFrame(columns=[
            "Outcome ID","Decision ID","Implementation Status","KPI",
            "Predicted","Actual","Delta","Delta %","Absolute Error","Lesson","Verified At",
        ])
    rows = []
    for row in outcomes.to_dict("records"):
        try:
            variance = json.loads(row.get("variance_json") or "[]")
        except Exception:
            variance = []
        for item in variance if isinstance(variance, list) else []:
            rows.append({
                "Outcome ID": row.get("outcome_id"),
                "Decision ID": row.get("decision_id"),
                "Implementation Status": row.get("implementation_status"),
                "KPI": item.get("KPI"),
                "Predicted": item.get("Predicted"),
                "Actual": item.get("Actual"),
                "Delta": item.get("Delta"),
                "Delta %": item.get("Delta %"),
                "Absolute Error": item.get("Absolute Error"),
                "Lesson": row.get("lesson", ""),
                "Verified At": row.get("verified_at"),
            })
    return pd.DataFrame(rows)


def add_comment(project_id: Optional[str], decision_id: Optional[str], actor: str, comment: str) -> None:
    text = str(comment or "").strip()
    if not text:
        return
    ensure_experience_db()
    with _db() as conn:
        conn.execute(
            "INSERT INTO experience_comments(project_id,decision_id,actor,comment,created_at) VALUES(?,?,?,?,?)",
            (project_id, decision_id, actor, text[:1200], _now()),
        )
        conn.commit()


def log_copilot_action(
    module: str,
    action: str,
    actor: str,
    requires_approval: bool = True,
    status: str = "Preview",
    evidence: Optional[Mapping[str, Any]] = None,
    run_id: Optional[str] = None,
) -> str:
    ensure_experience_db()
    rid = run_id or "RUN-" + uuid.uuid4().hex[:12].upper()
    with _db() as conn:
        conn.execute(
            "INSERT INTO experience_copilot_actions(run_id,module,action,status,requires_approval,evidence_json,actor,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                rid,
                module,
                action,
                status,
                int(bool(requires_approval)),
                json.dumps(dict(evidence or {}), default=str),
                actor,
                _now(),
            ),
        )
        conn.commit()
    return rid


def create_job(module: str, job_type: str, actor: str, payload: Mapping[str, Any]) -> str:
    """Create an owned job record; actor is its durable owner identifier."""
    ensure_experience_db()
    jid = "JOB-" + uuid.uuid4().hex[:12].upper()
    with _db() as conn:
        conn.execute(
            """INSERT INTO experience_jobs
               (job_id,module,job_type,status,progress,message,payload_json,started_at,finished_at,owner)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                jid, module, job_type, "Queued", 0.0, "Queued by operator",
                json.dumps(dict(payload), default=str), None, None, str(actor or "").strip() or None,
            ),
        )
        conn.commit()
    return jid


def update_job(
    job_id: str,
    status: str,
    progress: float,
    message: str = "",
    actor: str | None = None,
) -> None:
    """Update a job; user-facing callers should supply actor to enforce ownership.

    The actor-less form is retained for trusted internal workers for backwards
    compatibility. Do not use it to authorize a user-facing request.
    """
    fields = ["status=?", "progress=?", "message=?"]
    values = [status, float(max(0.0, min(100.0, progress))), str(message)[:500]]
    if status == "Running":
        fields.append("started_at=?")
        values.append(_now())
    if status in {"Completed", "Failed", "Cancelled"}:
        fields.append("finished_at=?")
        values.append(_now())
    query = "UPDATE experience_jobs SET " + ",".join(fields) + " WHERE job_id=?"
    values.append(job_id)
    if actor is not None:
        query += " AND owner=?"
        values.append(str(actor))
    with _db() as conn:
        cursor = conn.execute(query, values)
        conn.commit()
        if actor is not None and cursor.rowcount == 0:
            raise PermissionError("Job not found or not owned by this user.")


def benchmark_duration(module: str, start_ns: int, actor: str, rows: int, event: str = "run") -> str:
    rid = "RUN-" + uuid.uuid4().hex[:12].upper()
    duration = max(0.0, (time.perf_counter_ns() - start_ns) / 1000000.0)
    with _db() as conn:
        conn.execute(
            "INSERT INTO experience_observability(run_id,module,event_type,duration_ms,details_json,created_at) VALUES(?,?,?,?,?,?)",
            (rid, module, event, duration, json.dumps({"rows": int(rows), "actor": actor}), _now()),
        )
        conn.commit()
    return rid


def generic_result(df: pd.DataFrame) -> dict:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {"rows": 0, "columns": 0, "quality": 0.0, "numeric_fields": 0, "status": "No data"}
    numeric = df.select_dtypes(include=np.number)
    missing = float(df.isna().mean().mean() * 100) if len(df.columns) else 100.0
    duplicates = float(df.duplicated().mean() * 100) if len(df) else 0.0
    finite = bool(np.isfinite(numeric.to_numpy(dtype=float)).all()) if not numeric.empty else True
    quality = max(0.0, min(100.0, 100.0 - missing * 0.7 - duplicates * 0.4 - (0 if finite else 20)))
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "quality": round(quality, 1),
        "numeric_fields": int(len(numeric.columns)),
        "status": "Ready" if finite else "Check numeric values",
    }


def compute_evidence_roi(monthly_volume: float, unit_cost: float, expected_delta_pct: float) -> dict:
    volume = max(0.0, float(monthly_volume))
    cost = max(0.0, float(unit_cost))
    delta = float(expected_delta_pct) / 100.0
    baseline = volume * cost
    impact = baseline * delta
    return {
        "baseline_monthly_value": baseline,
        "assumption_delta_pct": float(expected_delta_pct),
        "illustrative_monthly_impact": impact,
        "illustrative_annual_impact": impact * 12.0,
    }


def verification_snapshot(df: pd.DataFrame) -> dict:
    numeric = df.select_dtypes(include=np.number) if isinstance(df, pd.DataFrame) else pd.DataFrame()
    checks = {
        "non_empty": isinstance(df, pd.DataFrame) and len(df) > 0,
        "unique_columns": isinstance(df, pd.DataFrame) and not df.columns.duplicated().any(),
        "finite_numbers": bool(np.isfinite(numeric.to_numpy(dtype=float)).all()) if not numeric.empty else True,
        "shape_valid": isinstance(df, pd.DataFrame) and len(df.columns) <= 500 and len(df) <= 1000000,
    }
    passed = sum(1 for value in checks.values() if value)
    return {"checks": checks, "passed": passed, "total": len(checks), "score": round(100.0 * passed / max(1, len(checks)), 1)}



MODULE_RUN_SNAPSHOT_LIMIT_BYTES = 8 * 1024 * 1024


def _module_run_json_safe(value: Any) -> Any:
    """Convert NumPy/Pandas values to strict JSON-safe primitives."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _module_run_json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _module_run_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_module_run_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def build_profiled_module_figure(
    frame: pd.DataFrame,
    chart_x: str | None,
    chart_y: str | None,
    profile: Mapping[str, Any] | None,
    title: str,
):
    """Honor a module's preferred chart when the current data supports it.

    Returns (figure, chart_name, notice). An incompatible preference receives
    a clear fallback notice instead of silently ignoring the user's setting.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None, "Unavailable", "No result rows are available to chart."
    profile = dict(profile or {})
    display_frame = apply_display_labels(frame, profile)
    x_display = display_field_label(chart_x, profile) if chart_x is not None and str(chart_x) in frame.columns else chart_x
    y_display = display_field_label(chart_y, profile) if chart_y is not None and str(chart_y) in frame.columns else chart_y
    if x_display not in display_frame.columns:
        x_display = None
    if y_display not in display_frame.columns:
        y_display = None

    requested = str(profile.get("preferred_chart", "Auto") or "Auto")
    try:
        from shoir_live_visuals import _make_figure, _suggest_chart
        actual = _suggest_chart(display_frame, x_display, y_display) if requested == "Auto" else requested
        figure = _make_figure(display_frame, actual, x_display, y_display, None, title)
        if figure is not None:
            return figure, actual, None
        fallback_chart = _suggest_chart(display_frame, x_display, y_display)
        if fallback_chart == actual:
            fallback_chart = "Bar"
        fallback = _make_figure(display_frame, fallback_chart, x_display, y_display, None, title)
        if fallback is not None:
            return fallback, fallback_chart, (
                f"Your preferred chart ({actual}) needs fields that are not available in this result. "
                f"Showing {fallback_chart} instead."
            )
    except Exception:
        pass

    try:
        numeric = [str(column) for column in display_frame.columns if pd.api.types.is_numeric_dtype(display_frame[column])]
        if not numeric:
            return None, requested, f"{requested} is not compatible with this table; add a numeric measure or choose another chart."
        y_column = y_display if y_display in numeric else numeric[-1]
        from plotly import express as px
        fallback = px.bar(display_frame, x=x_display, y=y_column, title=title) if x_display else px.bar(display_frame, y=y_column, title=title)
        return fallback, "Bar", (
            f"Your preferred chart ({requested}) could not be generated from the current fields. "
            "Showing a compatible Bar chart instead."
        )
    except Exception as exc:
        return None, requested, f"A chart could not be generated safely: {type(exc).__name__}: {exc}"


def save_module_analysis_run(
    module: str,
    owner: str,
    profile: Mapping[str, Any] | None,
    input_frame: pd.DataFrame,
    analysis: Mapping[str, Any],
    duration_ms: float = 0.0,
    status: str = "Completed",
    db_path: str = "enterprise_full_workspace.db",
) -> dict[str, Any]:
    """Persist a user-scoped input/result snapshot, bounded to protect the app."""
    if not isinstance(input_frame, pd.DataFrame):
        raise TypeError("Module run inputs must be a pandas DataFrame.")
    ensure_experience_db(db_path)
    analysis = dict(analysis or {})
    result_frame = analysis.get("result")
    if not isinstance(result_frame, pd.DataFrame):
        result_frame = pd.DataFrame()

    input_raw = input_frame.to_json(orient="split", date_format="iso", default_handler=str).encode("utf-8")
    result_raw = result_frame.to_json(orient="split", date_format="iso", default_handler=str).encode("utf-8")
    input_hash = hashlib.sha256(input_raw).hexdigest()
    compressed_input = gzip.compress(input_raw, compresslevel=6, mtime=0)
    compressed_result = gzip.compress(result_raw, compresslevel=6, mtime=0)
    input_blob = compressed_input if len(compressed_input) <= MODULE_RUN_SNAPSHOT_LIMIT_BYTES else None
    result_blob = compressed_result if len(compressed_result) <= MODULE_RUN_SNAPSHOT_LIMIT_BYTES else None

    if input_blob is not None and result_blob is not None:
        snapshot_status = "Complete"
    elif input_blob is None and result_blob is None:
        snapshot_status = "Input and result snapshots omitted (size limit)"
    elif input_blob is None:
        snapshot_status = "Input snapshot omitted (size limit)"
    else:
        snapshot_status = "Result snapshot omitted (size limit)"

    cleaned_profile = _module_run_json_safe(dict(profile or default_module_profile(module)))
    metrics = _module_run_json_safe(dict(analysis.get("metrics") or {}))
    run_id = "MRUN-" + uuid.uuid4().hex[:16].upper()
    created_at = _now()
    elapsed = max(0.0, float(duration_ms or 0.0))
    values = (
        run_id, str(module), str(owner),
        str(cleaned_profile.get("display_name") or module),
        str(cleaned_profile.get("project_name") or ""),
        str(cleaned_profile.get("site_name") or ""),
        input_hash, int(len(input_frame)),
        json.dumps([str(column) for column in input_frame.columns], ensure_ascii=False),
        json.dumps([str(column) for column in result_frame.columns], ensure_ascii=False),
        input_blob, result_blob,
        json.dumps(cleaned_profile, ensure_ascii=False, default=str),
        json.dumps(metrics, ensure_ascii=False, default=str),
        str(analysis.get("method") or "Module analysis"),
        str(analysis.get("guardrail") or "Verify the result against independent evidence before implementation."),
        elapsed, str(status or "Completed")[:40], snapshot_status, created_at,
    )
    with _db(db_path) as conn:
        conn.execute(
            """INSERT INTO experience_module_runs(
                run_id,module,owner,display_name,project_name,site_name,input_hash,input_rows,
                input_columns_json,result_columns_json,input_snapshot_gzip,result_snapshot_gzip,
                profile_json,metrics_json,method,guardrail,duration_ms,status,snapshot_status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        conn.commit()
    return {
        "run_id": run_id,
        "input_hash": input_hash,
        "snapshot_status": snapshot_status,
        "duration_ms": elapsed,
        "created_at": created_at,
    }


def list_module_analysis_runs(
    module: str,
    owner: str,
    limit: int = 20,
    db_path: str = "enterprise_full_workspace.db",
) -> pd.DataFrame:
    """List only the current owner's runs for the exact module identifier."""
    ensure_experience_db(db_path)
    safe_limit = max(1, min(50, int(limit)))
    with _db(db_path) as conn:
        rows = conn.execute(
            """SELECT run_id,display_name,project_name,site_name,input_rows,input_hash,
                      method,status,snapshot_status,duration_ms,created_at
               FROM experience_module_runs
               WHERE module=? AND owner=?
               ORDER BY created_at DESC, rowid DESC LIMIT ?""",
            (str(module), str(owner), safe_limit),
        ).fetchall()
    return pd.DataFrame(rows, columns=[
        "Run ID", "Workspace name", "Project", "Site", "Input rows", "Input SHA-256",
        "Method", "Status", "Snapshot status", "Duration (ms)", "Created at",
    ])


def load_module_analysis_run(
    run_id: str,
    owner: str,
    db_path: str = "enterprise_full_workspace.db",
) -> dict[str, Any] | None:
    """Load a saved run only for its owner, including whichever bounded snapshots exist."""
    ensure_experience_db(db_path)
    with _db(db_path) as conn:
        row = conn.execute(
            """SELECT run_id,module,owner,display_name,project_name,site_name,input_hash,
                      input_rows,input_columns_json,result_columns_json,input_snapshot_gzip,
                      result_snapshot_gzip,profile_json,metrics_json,method,guardrail,
                      duration_ms,status,snapshot_status,created_at
               FROM experience_module_runs WHERE run_id=? AND owner=?""",
            (str(run_id), str(owner)),
        ).fetchone()
    if not row:
        return None
    (
        saved_id,module,saved_owner,display_name,project_name,site_name,input_hash,
        input_rows,input_columns_json,result_columns_json,input_blob,result_blob,
        raw_profile,raw_metrics,method,guardrail,duration_ms,status,snapshot_status,created_at,
    ) = row

    def decode_json(raw: Any, fallback: Any) -> Any:
        try:
            return json.loads(raw or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback

    def decode_frame(blob: Any, raw_columns: Any) -> pd.DataFrame:
        columns = decode_json(raw_columns, [])
        if not blob:
            return pd.DataFrame(columns=columns if isinstance(columns, list) else [])
        try:
            decoded = gzip.decompress(blob).decode("utf-8")
            return pd.read_json(io.StringIO(decoded), orient="split")
        except Exception:
            return pd.DataFrame(columns=columns if isinstance(columns, list) else [])

    return {
        "run_id": saved_id, "module": module, "owner": saved_owner,
        "display_name": display_name, "project_name": project_name, "site_name": site_name,
        "input_hash": input_hash, "input_rows": int(input_rows or 0),
        "input_df": decode_frame(input_blob, input_columns_json),
        "result_df": decode_frame(result_blob, result_columns_json),
        "profile": decode_json(raw_profile, default_module_profile(module)),
        "metrics": decode_json(raw_metrics, {}),
        "method": method, "guardrail": guardrail,
        "duration_ms": float(duration_ms or 0.0), "status": status,
        "snapshot_status": snapshot_status, "created_at": created_at,
    }


def render_module_run_history(module: str, owner: str, key_suffix: str | None = None) -> None:
    """Render private run history and downloadable snapshots without changing the module shell."""
    import streamlit as st

    ensure_experience_db()
    token = str(key_suffix or hashlib.sha1(str(module).encode("utf-8")).hexdigest()[:10])
    with st.expander("🗂️ Saved module runs & result history", expanded=False):
        st.caption(
            "History is scoped to your account and this module. A saved run documents the selected "
            "inputs/results; it is not proof of a verified plant outcome."
        )
        history = list_module_analysis_runs(module, owner, limit=20)
        if history.empty:
            st.info("No saved runs are available for this module yet.")
            return
        st.dataframe(history.drop(columns=["Input SHA-256"]), use_container_width=True, hide_index=True)
        run_ids = history["Run ID"].astype(str).tolist()
        selector_key = f"module_run_history_selector_{token}"
        if selector_key in st.session_state and str(st.session_state[selector_key]) not in run_ids:
            st.session_state.pop(selector_key, None)
        labels = {
            str(row["Run ID"]): (
                f"{row['Created at']} · {row['Status']} · {row['Workspace name']} · {row['Run ID']}"
            )
            for _, row in history.iterrows()
        }
        selected_id = st.selectbox(
            "Inspect a saved run",
            options=run_ids,
            format_func=lambda value: labels.get(str(value), str(value)),
            key=selector_key,
        )
        record = load_module_analysis_run(selected_id, owner)
        if not record:
            st.warning("This saved run is no longer available to the current account.")
            return
        context = [record["display_name"], record["project_name"], record["site_name"]]
        st.caption(" · ".join(str(value) for value in context if value))
        a,b,c = st.columns(3)
        a.metric("Saved run", record["run_id"])
        b.metric("Input rows", f"{record['input_rows']:,}")
        c.metric("Calculation time", f"{record['duration_ms']:,.1f} ms")
        st.caption(f"Input SHA-256: {record['input_hash']} · {record['snapshot_status']}")
        st.caption(f"Method: {record['method']}")
        if record["guardrail"]:
            st.warning(record["guardrail"])
        if record["snapshot_status"] != "Complete":
            st.info("At least one data snapshot exceeded the 8 MiB compressed-payload limit. Metadata and input hash were preserved.")

        st.markdown("**Saved inputs**")
        if record["input_df"].empty and record["input_rows"]:
            st.info("The input snapshot was omitted or could not be decoded; the schema and hash remain available.")
        elif not record["input_df"].empty:
            st.dataframe(apply_display_labels(record["input_df"], record["profile"]).head(300), use_container_width=True, hide_index=True)
        st.markdown("**Saved calculated results**")
        if record["result_df"].empty:
            st.info("This record has no tabular result snapshot.")
        else:
            st.dataframe(apply_display_labels(record["result_df"], record["profile"]).head(500), use_container_width=True, hide_index=True)
        if record["metrics"]:
            with st.expander("Saved KPI summary", expanded=False):
                st.json(record["metrics"])
        dl1, dl2 = st.columns(2)
        with dl1:
            if not record["input_df"].empty:
                st.download_button(
                    "📥 Download saved inputs",
                    record["input_df"].to_csv(index=False).encode("utf-8"),
                    file_name=f"shoir_ie_{token}_{record['run_id'].lower()}_inputs.csv",
                    mime="text/csv", use_container_width=True,
                    key=f"module_run_inputs_download_{token}_{record['run_id']}",
                )
        with dl2:
            if not record["result_df"].empty:
                st.download_button(
                    "📥 Download saved results",
                    record["result_df"].to_csv(index=False).encode("utf-8"),
                    file_name=f"shoir_ie_{token}_{record['run_id'].lower()}_results.csv",
                    mime="text/csv", use_container_width=True,
                    key=f"module_run_results_download_{token}_{record['run_id']}",
                )


def _research_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def _research_hash(protocol: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(protocol), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_research_protocol(study_id: str, protocol: Mapping[str, Any], owner: str) -> tuple[str, str]:
    """Create/update a protocol without allowing a different owner to claim its ID.

    The local owner check and upsert run in one SQLite write transaction. When
    the managed backend is configured, its upsert has the same owner-conflict
    rule and must succeed before the local write continues.
    """
    ensure_experience_db()
    study_id = str(study_id or "").strip()
    owner = str(owner or "").strip()
    if not study_id:
        raise ValueError("A research study ID is required.")
    if not owner:
        raise ValueError("A research study owner is required.")

    payload = dict(protocol)
    stamp = _now()
    protocol_hash = _research_hash(payload)
    with _db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT research_id,created_at,owner FROM experience_research_studies WHERE study_id=?",
            (study_id,),
        ).fetchone()
        if existing and str(existing[2] or "").strip() != owner:
            raise PermissionError("Research study not found or not owned by this user.")

        research_id = str(existing[0]) if existing else "RSH-" + uuid.uuid4().hex[:12].upper()
        created_at = str(existing[1]) if existing and existing[1] else stamp

        remote_record = {
            "study_id": study_id,
            "research_id": research_id,
            "owner": owner,
            "title": payload.get("title"),
            "protocol": payload,
            "created_at": created_at,
            "updated_at": stamp,
        }
        try:
            if durable_backend_configured():
                upsert_remote_research_study(remote_record)
        except PermissionError:
            # An owner conflict is a security result, not a transient fallback.
            raise
        except Exception:
            # Non-authoritative transport failures retain the existing local
            # fallback behavior; an explicit ownership conflict never does.
            pass

        conn.execute(
            """
            INSERT OR REPLACE INTO experience_research_studies(
                study_id,research_id,title,objective,research_question,hypothesis,
                null_hypothesis,methodology,primary_domain,transfer_domain,
                primary_endpoint,secondary_metrics_json,independent_variables_json,
                controls_json,baseline_definition,treatment_definition,sample_size,
                replications,random_seed,alpha,confidence_level,planned_tests_json,
                inclusion_criteria,exclusion_criteria,data_source,protocol_notes,
                protocol_hash,protocol_locked,owner,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                study_id,
                research_id,
                str(payload.get("title", "")).strip()[:240],
                str(payload.get("objective", "")).strip()[:1500],
                str(payload.get("research_question", "")).strip()[:3000],
                str(payload.get("hypothesis", "")).strip()[:3000],
                str(payload.get("null_hypothesis", "")).strip()[:3000],
                str(payload.get("methodology", "")).strip()[:240],
                str(payload.get("primary_domain", "")).strip()[:120],
                str(payload.get("transfer_domain", "")).strip()[:120],
                str(payload.get("primary_endpoint", "")).strip()[:500],
                json.dumps(_research_list(payload.get("secondary_metrics", [])), ensure_ascii=False),
                json.dumps(_research_list(payload.get("independent_variables", [])), ensure_ascii=False),
                json.dumps(_research_list(payload.get("controls", [])), ensure_ascii=False),
                str(payload.get("baseline_definition", "")).strip()[:2000],
                str(payload.get("treatment_definition", "")).strip()[:2000],
                int(max(1, int(payload.get("sample_size", 100)))),
                int(max(1, int(payload.get("replications", 30)))),
                int(payload.get("random_seed", 2026)),
                float(payload.get("alpha", 0.05)),
                float(payload.get("confidence_level", 0.95)),
                json.dumps(_research_list(payload.get("planned_tests", [])), ensure_ascii=False),
                str(payload.get("inclusion_criteria", "")).strip()[:2000],
                str(payload.get("exclusion_criteria", "")).strip()[:2000],
                str(payload.get("data_source", "")).strip()[:1200],
                str(payload.get("protocol_notes", "")).strip()[:3000],
                protocol_hash,
                int(bool(payload.get("protocol_locked", False))),
                owner,
                created_at,
                stamp,
            ),
        )
        conn.commit()
    return research_id, protocol_hash


def _hydrate_remote_research_to_local(remote: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Restore a durable research record into the local SQLite cache."""
    protocol = remote.get("protocol") if isinstance(remote, Mapping) else None
    if not isinstance(protocol, dict):
        return None
    study_id = str(remote.get("study_id") or "").strip()
    research_id = str(remote.get("research_id") or "").strip()
    owner = str(remote.get("owner") or "").strip()
    if not study_id or not research_id or not owner:
        return None
    protocol = dict(protocol)
    protocol.setdefault("title", remote.get("title") or "Research Study")
    with _db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO experience_research_studies(
                study_id,research_id,title,objective,research_question,hypothesis,
                null_hypothesis,methodology,primary_domain,transfer_domain,
                primary_endpoint,secondary_metrics_json,independent_variables_json,
                controls_json,baseline_definition,treatment_definition,sample_size,
                replications,random_seed,alpha,confidence_level,planned_tests_json,
                inclusion_criteria,exclusion_criteria,data_source,protocol_notes,
                protocol_hash,protocol_locked,owner,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                study_id,
                research_id,
                str(protocol.get("title", "")).strip()[:240],
                str(protocol.get("objective", "")).strip()[:1500],
                str(protocol.get("research_question", "")).strip()[:3000],
                str(protocol.get("hypothesis", "")).strip()[:3000],
                str(protocol.get("null_hypothesis", "")).strip()[:3000],
                str(protocol.get("methodology", "")).strip()[:240],
                str(protocol.get("primary_domain", "")).strip()[:120],
                str(protocol.get("transfer_domain", "")).strip()[:120],
                str(protocol.get("primary_endpoint", "")).strip()[:500],
                json.dumps(_research_list(protocol.get("secondary_metrics", [])), ensure_ascii=False),
                json.dumps(_research_list(protocol.get("independent_variables", [])), ensure_ascii=False),
                json.dumps(_research_list(protocol.get("controls", [])), ensure_ascii=False),
                str(protocol.get("baseline_definition", "")).strip()[:2000],
                str(protocol.get("treatment_definition", "")).strip()[:2000],
                int(max(1, int(protocol.get("sample_size", 100)))),
                int(max(1, int(protocol.get("replications", 30)))),
                int(protocol.get("random_seed", 2026)),
                float(protocol.get("alpha", 0.05)),
                float(protocol.get("confidence_level", 0.95)),
                json.dumps(_research_list(protocol.get("planned_tests", [])), ensure_ascii=False),
                str(protocol.get("inclusion_criteria", "")).strip()[:2000],
                str(protocol.get("exclusion_criteria", "")).strip()[:2000],
                str(protocol.get("data_source", "")).strip()[:1200],
                str(protocol.get("protocol_notes", "")).strip()[:3000],
                str(protocol.get("protocol_hash") or remote.get("protocol_hash") or _research_hash(protocol)),
                int(bool(protocol.get("protocol_locked", False))),
                owner,
                str(remote.get("created_at") or _now()),
                str(remote.get("updated_at") or _now()),
            ),
        )
        conn.commit()
    return load_research_protocol(study_id, owner=owner)


def load_research_protocol(study_id: str, owner: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Load a protocol; user-facing callers must supply owner for isolation."""
    ensure_experience_db()
    with _db() as conn:
        query = """
            SELECT study_id,research_id,title,objective,research_question,hypothesis,
                   null_hypothesis,methodology,primary_domain,transfer_domain,
                   primary_endpoint,secondary_metrics_json,independent_variables_json,
                   controls_json,baseline_definition,treatment_definition,sample_size,
                   replications,random_seed,alpha,confidence_level,planned_tests_json,
                   inclusion_criteria,exclusion_criteria,data_source,protocol_notes,
                   protocol_hash,protocol_locked,owner,created_at,updated_at
            FROM experience_research_studies
            WHERE study_id=?
        """
        params: tuple[Any, ...] = (str(study_id),)
        if owner is not None:
            query += " AND owner=?"
            params += (str(owner),)
        row = conn.execute(query, params).fetchone()
    if not row:
        try:
            remote = remote_research_study(study_id, owner=owner)
            hydrated = _hydrate_remote_research_to_local(remote) if remote else None
            if hydrated:
                return hydrated
        except Exception:
            pass
        return None
    keys = [
        "study_id","research_id","title","objective","research_question","hypothesis",
        "null_hypothesis","methodology","primary_domain","transfer_domain",
        "primary_endpoint","secondary_metrics","independent_variables","controls",
        "baseline_definition","treatment_definition","sample_size","replications",
        "random_seed","alpha","confidence_level","planned_tests","inclusion_criteria",
        "exclusion_criteria","data_source","protocol_notes","protocol_hash",
        "protocol_locked","owner","created_at","updated_at"
    ]
    data = dict(zip(keys, row))
    for field in ("secondary_metrics", "independent_variables", "controls", "planned_tests"):
        try:
            data[field] = json.loads(data[field] or "[]")
        except Exception:
            data[field] = []
    return data


def research_protocol_frame(study_id: str, owner: Optional[str] = None) -> pd.DataFrame:
    protocol = load_research_protocol(study_id, owner=owner)
    if not protocol:
        return pd.DataFrame()
    return pd.DataFrame([{
        "Research ID": protocol["research_id"],
        "Study": protocol["title"],
        "Methodology": protocol["methodology"],
        "Primary domain": protocol["primary_domain"],
        "Transfer domain": protocol["transfer_domain"],
        "Primary endpoint": protocol["primary_endpoint"],
        "Scenarios": protocol["sample_size"],
        "Replications": protocol["replications"],
        "Random seed": protocol["random_seed"],
        "Alpha": protocol["alpha"],
        "Confidence": protocol["confidence_level"],
        "Protocol": "LOCKED" if protocol["protocol_locked"] else "DRAFT",
        "Protocol hash": protocol["protocol_hash"][:20] + "…",
    }])




def list_research_studies(owner: str) -> pd.DataFrame:
    ensure_experience_db()
    try:
        if durable_backend_configured():
            for remote in remote_research_studies(owner):
                try:
                    _hydrate_remote_research_to_local(remote)
                except Exception:
                    pass
    except Exception:
        pass
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT research_id,study_id,title,objective,research_question,methodology,
                   primary_domain,transfer_domain,primary_endpoint,sample_size,
                   replications,random_seed,alpha,confidence_level,protocol_locked,
                   protocol_hash,owner,created_at,updated_at
            FROM experience_research_studies
            WHERE owner=?
            ORDER BY updated_at DESC
            """,
            (owner,),
        ).fetchall()
    columns = [
        "Research ID","Study ID","Title","Objective","Research question",
        "Methodology","Primary domain","Transfer domain","Primary endpoint",
        "Scenarios","Replications","Random seed","Alpha","Confidence",
        "Protocol","Protocol hash","Owner","Created","Updated",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows, columns=columns)
    frame["Protocol"] = frame["Protocol"].map(lambda value: "LOCKED" if bool(value) else "DRAFT")
    frame["Protocol hash"] = frame["Protocol hash"].astype(str).str[:20] + "..."
    return frame


def restore_decision_readiness_study(owner: str) -> tuple[str, str]:
    """Recreate the study/protocol used by the Decision-Readiness research workflow.

    This is a recovery action for a study that was previously created in the
    transient/local workspace but is no longer visible after a restart.
    """
    ensure_experience_db()
    title = "Industrial AI Decision-Readiness Boundary — Experiment 001"
    existing = list_research_studies(owner)
    if not existing.empty:
        match = existing[existing["Title"].astype(str).str.strip().str.casefold() == title.casefold()]
        if not match.empty:
            sid = str(match.iloc[0]["Study ID"])
            protocol = load_research_protocol(sid, owner=owner)
            return sid, str(protocol.get("research_id")) if protocol else str(match.iloc[0]["Research ID"])

    protocol = {
        "title": title,
        "objective": "Determine how evidence degradation and operational disturbances affect industrial decision reliability and whether a reproducible decision-readiness boundary can be identified.",
        "research_question": "Can an industrial decision system identify a measurable boundary beyond which degraded, stale, missing, or conflicting evidence makes an operational recommendation unreliable?",
        "hypothesis": "Joint degradation of evidence quality and operating conditions will produce nonlinear deterioration in industrial decision reliability, allowing a measurable decision-readiness boundary to be identified.",
        "null_hypothesis": "Joint evidence degradation and operational disturbances will not produce a reproducible decision-readiness boundary beyond the effects of the individual factors.",
        "methodology": "Controlled simulation benchmark",
        "primary_domain": "Manufacturing",
        "transfer_domain": "Maintenance",
        "primary_endpoint": "Normalized decision regret",
        "secondary_metrics": ["total cost","throughput","service level","constraint violations","quality impact","energy impact","decision reversal rate"],
        "independent_variables": ["evidence completeness","evidence freshness","evidence conflict","uncertainty level","operational shock severity"],
        "controls": ["scenario seed","baseline operating state","decision objective weights","constraint set","decision horizon"],
        "sample_size": 200,
        "replications": 20,
        "random_seed": 2026,
        "alpha": 0.05,
        "confidence_level": 0.95,
        "data_source": "Shoir-IE controlled synthetic industrial scenarios; public dataset validation in a subsequent phase",
        "baseline_definition": "A documented decision policy operating with complete, fresh and internally consistent evidence under the defined baseline industrial conditions.",
        "treatment_definition": "The same decision problem evaluated under systematically controlled degradation of evidence completeness, freshness, conflict and uncertainty, combined with controlled operational disturbances.",
        "planned_tests": ["confidence intervals","paired comparisons","effect sizes","bootstrap sensitivity","factorial interaction analysis"],
        "inclusion_criteria": "Valid industrial scenarios with complete baseline definitions, finite numeric inputs, specified decision constraints, identifiable evidence-quality conditions, and a computable decision outcome. Scenarios must contain sufficient information to calculate the primary endpoint, normalized decision regret.",
        "exclusion_criteria": "Malformed or incomplete scenarios; missing primary outcome; non-finite or invalid numeric values; unspecified decision constraints; failed model validation; solver or runtime failures unrelated to the decision method; duplicate experimental scenarios that violate the planned sampling design.",
        "protocol_notes": "This study will first use controlled Shoir-IE synthetic industrial scenarios to isolate causal effects of evidence degradation and operational disturbances. The decision-readiness boundary must be derived from experimental evidence and must not be predefined as a desired result. Results from synthetic scenarios may not generalize directly to every real industrial environment. Public external datasets will be used for subsequent validation where suitable. Protocol amendments, parameter changes and deviations from the planned experiment will be recorded explicitly rather than silently changing the original specification.",
        "protocol_locked": False,
        "module": "Experiment Lab",
        "tier": "Research Pack",
    }
    study_id = save_project(title, "Experiment Lab", owner, {"research_protocol": protocol, "protocol_type": "local_research_protocol"})
    research_id, _ = create_research_protocol(study_id, protocol, owner)
    return study_id, research_id


def recover_legacy_research_studies(owner: str) -> pd.DataFrame:
    """Recover protocols persisted inside older project payloads."""
    ensure_experience_db()
    recovered = []
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT project_id,name,module,payload_json,created_at
            FROM experience_projects
            WHERE owner=?
            ORDER BY updated_at DESC
            """,
            (owner,),
        ).fetchall()
        # Also inspect the older app-level saved_projects table. Older releases
        # stored research protocols there without an owner column.
        try:
            legacy_rows = conn.execute(
                "SELECT name,data,updated_at FROM saved_projects ORDER BY updated_at DESC"
            ).fetchall()
        except Exception:
            legacy_rows = []
        for name, raw, updated_at in legacy_rows:
            try:
                payload = json.loads(raw or "{}")
            except Exception:
                continue
            protocol = payload.get("research_protocol")
            if not isinstance(protocol, dict):
                continue
            record_owner = str(payload.get("owner") or payload.get("username") or owner).strip()
            if record_owner.lower() != str(owner).strip().lower():
                continue
            project_id = "LEGACY-" + hashlib.sha1(
                (str(name) + str(owner)).encode("utf-8")
            ).hexdigest()[:12].upper()
            rows.append((project_id, str(name), "Experiment Lab", json.dumps(payload), str(updated_at or _now())))
        # A study ID is globally unique. Never overwrite another owner's
        # already-indexed protocol during recovery.
        existing_ids = {
            str(row[0])
            for row in conn.execute(
                "SELECT study_id FROM experience_research_studies"
            ).fetchall()
        }
    for project_id, name, module, raw, created_at in rows:
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            continue
        protocol = payload.get("research_protocol")
        if not isinstance(protocol, dict) or str(project_id) in existing_ids:
            continue
        try:
            rid, phash = create_research_protocol(str(project_id), protocol, owner)
        except Exception:
            continue
        recovered.append({
            "Study ID": str(project_id),
            "Research ID": rid,
            "Title": str(protocol.get("title") or name or "Recovered research study"),
            "Protocol hash": phash[:20] + "...",
            "Recovered from": "legacy project payload",
            "Original created": created_at,
        })
    return pd.DataFrame(recovered)


def _research_experiment_code(config: Mapping[str, Any]) -> str:
    """Map the protocol's planned A-J conditions to stable experiment labels."""
    key = (
        int(config.get("evidence_completeness", -1)),
        int(config.get("evidence_freshness_hours", -1)),
        int(config.get("evidence_conflict_pct", -1)),
        int(config.get("evidence_uncertainty_pct", -1)),
        float(config.get("shock_severity", -1)),
    )
    known = {
        (100,0,0,0,0.0): "001A",
        (90,0,0,0,0.0): "001B",
        (75,0,0,0,0.0): "001C",
        (50,0,0,0,0.0): "001D",
        (100,6,0,0,0.0): "001E",
        (100,24,0,0,0.0): "001F",
        (100,0,10,0,0.0): "001G",
        (100,0,0,20,0.0): "001H",
        (75,6,10,20,0.0): "001I",
        (75,6,10,20,1.5): "001J",
    }
    return known.get(key, "CUSTOM-" + hashlib.sha1(json.dumps(key).encode("utf-8")).hexdigest()[:8].upper())


def register_research_run(
    study_id: str,
    research_id: str,
    owner: str,
    config: Mapping[str, Any],
    results: pd.DataFrame,
) -> str:
    """Persist a completed controlled experiment and its evidence data."""
    ensure_experience_db()
    run_id = "RRUN-" + uuid.uuid4().hex[:12].upper()
    cfg = dict(config)
    cfg["study_id"] = study_id
    cfg["research_id"] = research_id
    code = _research_experiment_code(cfg)
    summary = {
        "observations": int(len(results)) if isinstance(results, pd.DataFrame) else 0,
        "columns": int(len(results.columns)) if isinstance(results, pd.DataFrame) else 0,
        "mean_decision_regret": (
            float(pd.to_numeric(results["decision_regret"], errors="coerce").mean())
            if isinstance(results, pd.DataFrame) and "decision_regret" in results.columns else None
        ),
        "mean_readiness_score": (
            float(pd.to_numeric(results["readiness_score"], errors="coerce").mean())
            if isinstance(results, pd.DataFrame) and "readiness_score" in results.columns else None
        ),
        "holdout_mean_decision_regret": (
            float(pd.to_numeric(
                results.loc[results["split"].astype(str).str.casefold() == "holdout","decision_regret"],
                errors="coerce",
            ).mean())
            if isinstance(results, pd.DataFrame) and {"decision_regret","split"} <= set(results.columns)
            and not results.loc[results["split"].astype(str).str.casefold() == "holdout"].empty else None
        ),
    }
    created_at = _now()
    raw_results = results.to_csv(index=False) if isinstance(results, pd.DataFrame) else ""
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO experience_research_runs(
                run_id,study_id,research_id,owner,experiment_code,
                config_json,summary_json,results_csv,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id, str(study_id), str(research_id), str(owner), code,
                json.dumps(cfg, ensure_ascii=False, default=str),
                json.dumps(summary, ensure_ascii=False, default=str),
                raw_results,
                created_at,
            ),
        )
        conn.commit()
    try:
        if durable_backend_configured():
            upsert_remote_research_run({
                "run_id": run_id,
                "study_id": study_id,
                "research_id": research_id,
                "owner": owner,
                "experiment_code": code,
                "config": cfg,
                "summary": summary,
                "results_csv": raw_results,
                "created_at": created_at,
            })
    except Exception:
        pass
    return run_id


def import_research_run_csv(
    study_id: str,
    research_id: str,
    owner: str,
    uploaded: Any,
    experiment_code: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    """Import a previously exported Lab CSV into the persistent run registry."""
    ensure_experience_db()
    raw = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not raw:
        raise ValueError("The uploaded CSV is empty.")

    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise ValueError(f"Could not read the CSV: {exc}") from exc

    aliases = {
        "decision_regret": ["decision_regret", "Decision Regret", "decision regret"],
        "readiness_score": ["readiness_score", "Readiness Score", "readiness score"],
        "split": ["split", "Split"],
        "evidence_completeness": ["evidence_completeness", "Evidence Completeness", "evidence completeness"],
        "evidence_freshness_hours": ["evidence_freshness_hours", "Evidence Freshness Hours", "evidence freshness hours"],
        "evidence_conflict_pct": ["evidence_conflict_pct", "Evidence Conflict Pct", "evidence conflict pct"],
        "evidence_uncertainty_pct": ["evidence_uncertainty_pct", "Evidence Uncertainty Pct", "evidence uncertainty pct"],
        "shock_severity": ["shock_severity", "Shock Severity", "shock severity"],
    }

    def resolve(field: str) -> Optional[str]:
        normalized = {str(col).strip().casefold(): col for col in df.columns}
        for alias in aliases[field]:
            if alias.casefold() in normalized:
                return normalized[alias.casefold()]
        return None

    required = {field: resolve(field) for field in aliases}
    missing = [field for field in ("decision_regret", "readiness_score") if not required[field]]
    if missing:
        raise ValueError(
            "This is not a Shoir-IE Evidence Degradation Lab CSV. Missing: "
            + ", ".join(missing)
        )

    clean = df.copy()
    clean = clean.rename(columns={col: field for field, col in required.items() if col})
    for field in ("decision_regret", "readiness_score"):
        clean[field] = pd.to_numeric(clean[field], errors="coerce")
    if "split" not in clean.columns:
        clean["split"] = "development"
    clean["split"] = clean["split"].astype(str)
    if clean["decision_regret"].isna().all():
        raise ValueError("Decision Regret contains no usable numeric values.")
    clean = clean.dropna(subset=["decision_regret"]).reset_index(drop=True)

    config = {
        "study_id": str(study_id),
        "research_id": str(research_id),
        "decision_type": "Next-shift production target",
        "baseline_policy": "Evidence-following policy",
        "scenario_count": int(len(clean)),
        "replications": 1,
        "holdout_fraction": float(
            (clean["split"].str.casefold() == "holdout").mean()
            if len(clean) else 0.0
        ),
        "random_seed": 2026,
    }
    for field in (
        "evidence_completeness",
        "evidence_freshness_hours",
        "evidence_conflict_pct",
        "evidence_uncertainty_pct",
        "shock_severity",
    ):
        if field in clean.columns:
            values = pd.to_numeric(clean[field], errors="coerce").dropna()
            if not values.empty:
                value = float(values.iloc[0])
                config[field] = int(value) if field != "shock_severity" else value

    code = str(experiment_code or "").strip().upper()
    if code in {"", "AUTO"}:
        code = _research_experiment_code(config)
    config["experiment_code"] = code

    run_id = register_research_run(
        study_id=str(study_id),
        research_id=str(research_id),
        owner=str(owner),
        config=config,
        results=clean,
    )
    return run_id, {
        "experiment_code": code,
        "observations": int(len(clean)),
        "mean_decision_regret": float(clean["decision_regret"].mean()),
        "mean_readiness_score": float(clean["readiness_score"].mean()),
    }


def load_research_run(run_id: str, owner: Optional[str] = None) -> Optional[dict[str, Any]]:
    ensure_experience_db()
    with _db() as conn:
        if owner:
            row = conn.execute(
                "SELECT run_id,study_id,research_id,owner,experiment_code,config_json,summary_json,results_csv,created_at FROM experience_research_runs WHERE run_id=? AND owner=?",
                (str(run_id), str(owner)),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT run_id,study_id,research_id,owner,experiment_code,config_json,summary_json,results_csv,created_at FROM experience_research_runs WHERE run_id=?",
                (str(run_id),),
            ).fetchone()
    if not row:
        return None
    keys = ["run_id","study_id","research_id","owner","experiment_code","config_json","summary_json","results_csv","created_at"]
    data = dict(zip(keys,row))
    try: data["config"] = json.loads(data.pop("config_json") or "{}")
    except Exception: data["config"] = {}
    try: data["summary"] = json.loads(data.pop("summary_json") or "{}")
    except Exception: data["summary"] = {}
    data["results"] = pd.read_csv(io.StringIO(data.pop("results_csv") or "")) if data.get("results_csv") else pd.DataFrame()
    return data


def research_runs_frame(study_id: Optional[str], owner: Optional[str] = None) -> pd.DataFrame:
    columns = [
        "Run ID","Experiment","Module","Job type","Status","Progress",
        "Observations","Mean regret","Mean readiness","Message","Created","Finished"
    ]
    if not study_id:
        return pd.DataFrame(columns=columns)
    ensure_experience_db()
    records = []

    # Hydrate durable PostgreSQL runs into the local cache after a restart.
    if owner:
        try:
            if durable_backend_configured():
                for remote in remote_research_runs(owner, str(study_id)):
                    cfg = {}
                    summary = {}
                    try: cfg = dict(remote.get("config") or {})
                    except Exception: cfg = {}
                    try: summary = dict(remote.get("summary") or {})
                    except Exception: summary = {}
                    with _db() as conn:
                        exists = conn.execute(
                            "SELECT 1 FROM experience_research_runs WHERE run_id=? LIMIT 1",
                            (str(remote.get("run_id")),),
                        ).fetchone()
                    if not exists:
                        with _db() as conn:
                            conn.execute(
                                """
                                INSERT INTO experience_research_runs(
                                    run_id,study_id,research_id,owner,experiment_code,
                                    config_json,summary_json,results_csv,created_at
                                ) VALUES(?,?,?,?,?,?,?,?,?)
                                """,
                                (
                                    str(remote.get("run_id")),
                                    str(remote.get("study_id")),
                                    str(remote.get("research_id")),
                                    str(remote.get("owner") or owner),
                                    str(remote.get("experiment_code") or ""),
                                    json.dumps(cfg, ensure_ascii=False, default=str),
                                    json.dumps(summary, ensure_ascii=False, default=str),
                                    str(remote.get("results_csv") or ""),
                                    str(remote.get("created_at") or _now()),
                                ),
                            )
                            conn.commit()
        except Exception:
            pass

    # Primary source: persisted research runs scoped to the requested owner.
    with _db() as conn:
        if owner:
            rows = conn.execute(
                """
                SELECT run_id,experiment_code,config_json,summary_json,created_at
                FROM experience_research_runs
                WHERE study_id=? AND owner=?
                ORDER BY created_at DESC
                """,
                (str(study_id), str(owner)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT run_id,experiment_code,config_json,summary_json,created_at
                FROM experience_research_runs
                WHERE study_id=?
                ORDER BY created_at DESC
                """,
                (str(study_id),),
            ).fetchall()
    for run_id, code, raw_cfg, raw_summary, created_at in rows:
        try: cfg = json.loads(raw_cfg or "{}")
        except Exception: cfg = {}
        try: summary = json.loads(raw_summary or "{}")
        except Exception: summary = {}
        records.append([
            run_id, code,
            "Evidence Degradation & Decision-Readiness Lab",
            "controlled-evidence-experiment",
            "Completed", 100.0,
            summary.get("observations", 0),
            summary.get("holdout_mean_decision_regret", summary.get("mean_decision_regret")),
            summary.get("mean_readiness_score"),
            "Persisted experiment evidence",
            created_at, created_at,
        ])

    # Compatibility source: jobs attributed to the requested owner. Legacy
    # ownerless rows are deliberately not assigned to a user.
    with _db() as conn:
        if owner:
            jobs = conn.execute(
                """
                SELECT job_id,module,job_type,status,progress,message,payload_json,
                       started_at,finished_at
                FROM experience_jobs
                WHERE owner=?
                ORDER BY COALESCE(started_at,finished_at) DESC
                """,
                (str(owner),),
            ).fetchall()
        else:
            jobs = conn.execute(
                """
                SELECT job_id,module,job_type,status,progress,message,payload_json,
                       started_at,finished_at
                FROM experience_jobs
                ORDER BY COALESCE(started_at,finished_at) DESC
                """
            ).fetchall()
    existing_ids = {str(r[0]) for r in records}
    for job_id, module, job_type, status, progress, message, raw, started, finished in jobs:
        try: payload = json.loads(raw or "{}")
        except Exception: payload = {}
        if str(payload.get("study_id", "")) != str(study_id):
            continue
        if str(job_id) in existing_ids:
            continue
        records.append([
            job_id, payload.get("experiment_code",""),
            module, job_type, status, float(progress or 0),
            payload.get("observations", 0),
            payload.get("mean_regret"),
            payload.get("mean_readiness"),
            message, started, finished,
        ])
    return pd.DataFrame(records, columns=columns)


def research_decisions_frame(owner: str) -> pd.DataFrame:
    columns = ["Decision ID","Title","Module","Status","Metrics","Assumptions","Uncertainty","Created","Updated"]
    ensure_experience_db()
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT decision_id,title,module,status,metrics_json,assumptions_json,
                   uncertainty_json,created_at,updated_at
            FROM experience_decisions
            WHERE owner=?
            ORDER BY updated_at DESC
            """,
            (owner,),
        ).fetchall()
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


def research_evidence_bundle(study_id: str, owner: str) -> bytes:
    """Export only the requesting owner's protocol, runs, studies and decisions."""
    protocol = load_research_protocol(study_id, owner=owner)
    if not protocol:
        raise PermissionError("Research study not found or not owned by this user.")
    studies = list_research_studies(owner)
    runs = research_runs_frame(study_id, owner=owner)
    decisions = research_decisions_frame(owner)
    manifest = {
        "bundle_type": "Shoir-IE research workspace evidence",
        "generated_at": _now(),
        "owner": owner,
        "study_id": study_id,
        "research_id": protocol.get("research_id") if protocol else None,
        "protocol_hash": protocol.get("protocol_hash") if protocol else None,
        "note": "Persisted research records only; this bundle does not establish that an experiment has been executed or that a scientific result has been proven.",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
        if protocol:
            archive.writestr("research_protocol.json", json.dumps(protocol, indent=2, ensure_ascii=False, default=str))
        archive.writestr("saved_research_studies.csv", studies.to_csv(index=False).encode("utf-8"))
        archive.writestr("research_runs.csv", runs.to_csv(index=False).encode("utf-8"))
        archive.writestr("decision_records.csv", decisions.to_csv(index=False).encode("utf-8"))
    return buffer.getvalue()


def render_research_workspace(module: str, tier: str, username: str) -> None:
    import streamlit as st
    ensure_experience_db()
    studies = list_research_studies(username)
    active_id = st.session_state.get("sx_research_study_id")
    active_protocol = load_research_protocol(active_id, owner=username) if active_id else None
    decisions = research_decisions_frame(username)
    runs = research_runs_frame(active_id, owner=username)

    st.markdown(
        "<div class='sx-hero'><div class='sx-kicker'>Research Workspace</div>"
        "<div class='sx-title'>🔬 Shoir-IE Research Workspace</div>"
        "<div class='sx-sub'>One place to recover, inspect and manage saved research studies, protocols, run history, decision records and evidence.</div>"
        f"<div class='sx-badges'><span>● {len(studies)} saved studies</span><span>✓ Research records are persistent</span><span>◈ No placeholder action strip</span></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        .sx-hero{padding:24px 26px;border-radius:20px;background:linear-gradient(135deg,#0b1220 0%,#192657 58%,#0f5c63 100%);color:#fff;box-shadow:0 18px 40px rgba(15,23,42,.16);margin:2px 0 16px}
        .sx-kicker{font-size:11px;font-weight:800;letter-spacing:.10em;text-transform:uppercase;color:#7dd3fc}
        .sx-title{font-size:29px;font-weight:850;margin-top:5px;line-height:1.16}.sx-sub{font-size:13px;color:#dbeafe;margin-top:8px;max-width:1000px}
        .sx-badges{display:flex;gap:10px;flex-wrap:wrap;margin-top:13px}.sx-badges span{font-size:11px;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);color:#e2e8f0}
        </style>
        """,
        unsafe_allow_html=True,
    )
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Saved studies", len(studies))
    c2.metric("Active study", "Selected" if active_protocol else "None")
    c3.metric("Runs for active study", len(runs))
    c4.metric("Decision records", len(decisions))

    tabs = st.tabs(["📚 Studies & Recovery","📋 Protocol","🧪 Experiment Engine","🧪 Runs & Results","📝 Decisions","📦 Evidence & Export","📊 Scenario Lab"])

    with tabs[0]:
        st.markdown("### Saved research studies")
        if studies.empty:
            st.info("No research studies are currently indexed for this workspace.")
            st.caption(
                "Your previous Decision-Readiness study can be restored here if a restart cleared the local research cache. "
                "Future saves are also persisted to the managed database when it is configured."
            )
            if st.button(
                "↩️ Restore Decision-Readiness Boundary — Experiment 001",
                type="primary",
                use_container_width=True,
                key="research_restore_decision_readiness",
            ):
                study_id, research_id = restore_decision_readiness_study(username)
                st.session_state["sx_research_study_id"] = study_id
                st.session_state["sx_research_id"] = research_id
                st.success("Research study restored and linked to this workspace.")
                st.rerun()
        else:
            labels = [f"{row['Title']} · {row['Research ID']}" for _, row in studies.iterrows()]
            ids = [str(x) for x in studies["Study ID"].tolist()]
            active_index = ids.index(str(active_id)) if active_id in ids else 0
            choice = st.selectbox("Select a saved study", labels, index=active_index, key="research_saved_study_selector")
            selected_id = ids[labels.index(choice)]
            if st.button("📂 Open selected study", type="primary", use_container_width=True, key="research_open_saved_study"):
                st.session_state["sx_research_study_id"] = selected_id
                st.rerun()
            st.dataframe(studies, use_container_width=True, hide_index=True)

        st.markdown("### Legacy recovery")
        st.caption("Older Shoir-IE versions stored the full protocol inside the project record. Recovery rebuilds the research index from those persisted project payloads.")
        if st.button("♻️ Recover legacy research protocols", use_container_width=True, key="research_recover_legacy"):
            recovered = recover_legacy_research_studies(username)
            if recovered.empty:
                st.info("No unrecovered legacy research protocols were found.")
            else:
                st.success(f"Recovered {len(recovered)} research protocol record(s).")
                st.dataframe(recovered, use_container_width=True, hide_index=True)
                st.rerun()

        if st.button("➕ Start a new research study", use_container_width=True, key="research_new_study"):
            st.session_state.pop("sx_research_study_id", None)
            st.rerun()

    with tabs[1]:
        st.markdown("### Research protocol")
        if active_protocol and active_protocol.get("protocol_locked"):
            st.success("Protocol is LOCKED. It remains readable and reproducible, but its main specification cannot be edited from this screen.")
        elif not active_protocol:
            st.info("No study is selected. Complete the form below to create the first study.")
        
        protocol = active_protocol or {
            "title":"Industrial AI Decision-Readiness Boundary — Experiment 001",
            "objective":"Determine how evidence degradation and operational disturbances affect industrial decision reliability and whether a reproducible decision-readiness boundary can be identified.",
            "research_question":"Can an industrial decision system identify a measurable boundary beyond which degraded, stale, missing, or conflicting evidence makes an operational recommendation unreliable?",
            "hypothesis":"Joint degradation of evidence quality and operating conditions will produce nonlinear deterioration in industrial decision reliability, allowing a measurable decision-readiness boundary to be identified.",
            "null_hypothesis":"Joint evidence degradation and operational disturbances will not produce a reproducible decision-readiness boundary beyond the effects of the individual factors.",
            "methodology":"Controlled simulation benchmark","primary_domain":"Manufacturing","transfer_domain":"Maintenance",
            "primary_endpoint":"Normalized decision regret",
            "secondary_metrics":["total cost","throughput","service level","constraint violations","quality impact","energy impact","decision reversal rate"],
            "independent_variables":["evidence completeness","evidence freshness","evidence conflict","uncertainty level","operational shock severity"],
            "controls":["scenario seed","baseline operating state","decision objective weights","constraint set","decision horizon"],
            "sample_size":200,"replications":20,"random_seed":2026,"alpha":0.05,"confidence_level":0.95,
            "data_source":"Shoir-IE controlled synthetic industrial scenarios; public dataset validation in a subsequent phase",
            "baseline_definition":"A documented decision policy operating with complete, fresh and internally consistent evidence under the defined baseline industrial conditions.",
            "treatment_definition":"The same decision problem evaluated under systematically controlled degradation of evidence completeness, freshness, conflict and uncertainty, combined with controlled operational disturbances.",
            "planned_tests":["confidence intervals","paired comparisons","effect sizes","bootstrap sensitivity","factorial interaction analysis"],
            "inclusion_criteria":"Valid industrial scenarios with complete baseline definitions, finite numeric inputs, specified decision constraints, identifiable evidence-quality conditions, and a computable decision outcome. Scenarios must contain sufficient information to calculate the primary endpoint, normalized decision regret.",
            "exclusion_criteria":"Malformed or incomplete scenarios; missing primary outcome; non-finite or invalid numeric values; unspecified decision constraints; failed model validation; solver or runtime failures unrelated to the decision method; duplicate experimental scenarios that violate the planned sampling design.",
            "protocol_notes":"This study will first use controlled Shoir-IE synthetic industrial scenarios to isolate causal effects of evidence degradation and operational disturbances. The decision-readiness boundary must be derived from experimental evidence and must not be predefined as a desired result. Results from synthetic scenarios may not generalize directly to every real industrial environment. Public external datasets will be used for subsequent validation where suitable. Protocol amendments, parameter changes and deviations from the planned experiment will be recorded explicitly rather than silently changing the original specification.",
            "protocol_locked":False,
        }
        locked = bool(active_protocol and active_protocol.get("protocol_locked"))
        form_key = "research_protocol_form_" + (_safe_key(active_id) if active_id else "new")
        with st.form(form_key, clear_on_submit=False):
            r1,r2 = st.columns([1.7,1])
            with r1:
                title = st.text_input("Study title", value=str(protocol["title"]), disabled=locked, key=form_key+"_title")
                question = st.text_area("Research question", value=str(protocol["research_question"]), height=90, disabled=locked, key=form_key+"_question")
                objective = st.text_area("Study objective", value=str(protocol["objective"]), height=75, disabled=locked, key=form_key+"_objective")
            with r2:
                methods=["Controlled simulation benchmark","Design of experiments (DOE)","Cross-domain transfer benchmark","Monte Carlo study","Hybrid simulation + optimization"]
                domains=["Manufacturing","Warehouse / inventory","Supply chain","Maintenance","Quality","Energy"]
                method_index=methods.index(protocol["methodology"]) if protocol.get("methodology") in methods else 0
                primary_index=domains.index(protocol["primary_domain"]) if protocol.get("primary_domain") in domains else 0
                transfer_index=domains.index(protocol["transfer_domain"]) if protocol.get("transfer_domain") in domains else 3
                methodology=st.selectbox("Methodology",methods,index=method_index,disabled=locked,key=form_key+"_method")
                endpoint=st.text_input("Primary endpoint",value=str(protocol["primary_endpoint"]),disabled=locked,key=form_key+"_endpoint")
                primary_domain=st.selectbox("Primary domain",domains,index=primary_index,disabled=locked,key=form_key+"_primary")
                transfer_domain=st.selectbox("Unseen / transfer domain",domains,index=transfer_index,disabled=locked,key=form_key+"_transfer")
            h1,h0=st.columns(2)
            with h1:
                hypothesis=st.text_area("Primary hypothesis (H1)",value=str(protocol["hypothesis"]),height=90,disabled=locked,key=form_key+"_h1")
            with h0:
                null_hypothesis=st.text_area("Null hypothesis (H0)",value=str(protocol["null_hypothesis"]),height=90,disabled=locked,key=form_key+"_h0")
            v1,v2,v3=st.columns(3)
            with v1:
                secondary=st.text_input("Secondary metrics",value=", ".join(protocol["secondary_metrics"]),disabled=locked,key=form_key+"_secondary")
                independent=st.text_input("Independent variables",value=", ".join(protocol["independent_variables"]),disabled=locked,key=form_key+"_independent")
                controls=st.text_input("Controls / covariates",value=", ".join(protocol["controls"]),disabled=locked,key=form_key+"_controls")
            with v2:
                sample_size=st.number_input("Scenario count",10,100000,int(protocol["sample_size"]),10,disabled=locked,key=form_key+"_sample")
                replications=st.number_input("Replications / scenario",1,10000,int(protocol["replications"]),1,disabled=locked,key=form_key+"_rep")
                random_seed=st.number_input("Random seed",0,2147483647,int(protocol["random_seed"]),1,disabled=locked,key=form_key+"_seed")
            with v3:
                alpha=st.number_input("Significance level (α)",0.001,0.20,float(protocol["alpha"]),0.01,"%.3f",disabled=locked,key=form_key+"_alpha")
                confidence=st.number_input("Confidence level",0.80,0.999,float(protocol["confidence_level"]),0.01,"%.3f",disabled=locked,key=form_key+"_confidence")
                data_source=st.text_input("Data source",value=str(protocol["data_source"]),disabled=locked,key=form_key+"_source")
            baseline=st.text_area("Baseline definition",value=str(protocol["baseline_definition"]),height=70,disabled=locked,key=form_key+"_baseline")
            treatment=st.text_area("Treatment / experimental condition",value=str(protocol["treatment_definition"]),height=70,disabled=locked,key=form_key+"_treatment")
            planned=st.text_input("Planned statistical tests",value=", ".join(protocol["planned_tests"]),disabled=locked,key=form_key+"_tests")
            ic1,ic2=st.columns(2)
            with ic1:
                inclusion=st.text_area("Inclusion criteria",value=str(protocol["inclusion_criteria"]),height=90,disabled=locked,key=form_key+"_include")
            with ic2:
                exclusion=st.text_area("Exclusion criteria",value=str(protocol["exclusion_criteria"]),height=90,disabled=locked,key=form_key+"_exclude")
            notes=st.text_area("Protocol notes / limitations",value=str(protocol["protocol_notes"]),height=120,disabled=locked,key=form_key+"_notes")
            lock_request=st.checkbox("Lock protocol after saving (local integrity lock)",value=locked,disabled=locked,key=form_key+"_lock")
            save=st.form_submit_button("💾 Update Research Study & Protocol" if active_protocol else "💾 Save Research Study & Protocol",type="primary",use_container_width=True,disabled=locked)
        if save:
            errors=[]
            if not title.strip(): errors.append("Study title is required.")
            if len(question.strip())<20: errors.append("Research question should be at least 20 characters.")
            if len(hypothesis.strip())<20: errors.append("H1 should be at least 20 characters.")
            if len(null_hypothesis.strip())<20: errors.append("H0 should be at least 20 characters.")
            if not endpoint.strip(): errors.append("Primary endpoint is required.")
            if primary_domain == transfer_domain: errors.append("Primary and transfer domains must differ.")
            if errors:
                for error in errors: st.error(error)
            else:
                payload={
                    "title":title,"objective":objective,"research_question":question,"hypothesis":hypothesis,
                    "null_hypothesis":null_hypothesis,"methodology":methodology,"primary_domain":primary_domain,
                    "transfer_domain":transfer_domain,"primary_endpoint":endpoint,
                    "secondary_metrics":_research_list(secondary),"independent_variables":_research_list(independent),
                    "controls":_research_list(controls),"baseline_definition":baseline,
                    "treatment_definition":treatment,"sample_size":int(sample_size),"replications":int(replications),
                    "random_seed":int(random_seed),"alpha":float(alpha),"confidence_level":float(confidence),
                    "planned_tests":_research_list(planned),"inclusion_criteria":inclusion,
                    "exclusion_criteria":exclusion,"data_source":data_source,"protocol_notes":notes,
                    "protocol_locked":bool(lock_request),"module":module,"tier":tier,
                }
                if active_protocol:
                    pid=active_protocol["study_id"]
                    autosave_project(pid,{"research_protocol":payload,"protocol_type":"local_research_protocol"})
                else:
                    pid=save_project(title,module,username,{"research_protocol":payload,"protocol_type":"local_research_protocol"})
                rid,phash=create_research_protocol(pid,payload,username)
                st.session_state["sx_research_study_id"]=pid
                st.session_state["sx_research_id"]=rid
                st.session_state["sx_research_protocol_hash"]=phash
                st.success(f"Research study saved: {pid} · Protocol {rid}")
                st.rerun()

    with tabs[2]:
        render_experiment_engine(
            module="Experiment Lab",
            username=username,
            protocol=active_protocol,
        )

    with tabs[3]:
        st.markdown("### Run history")
        if not active_protocol:
            st.info("Select a saved study first.")
        else:
            if runs.empty:
                st.info("No persisted experiment runs exist for this study yet.")
            else:
                st.dataframe(runs, use_container_width=True, hide_index=True)

            st.markdown("#### ♻️ Recover a previously completed Lab run")
            st.caption(
                "Use this only for an experiment that was completed before persistent run history was enabled. "
                "The original CSV is imported into the same research-run registry used by new experiments."
            )
            recovery_file = st.file_uploader(
                "Upload the completed Evidence Degradation Lab CSV",
                type=["csv"],
                key="research_run_recovery_csv",
                help="Expected fields include decision_regret, readiness_score and the evidence-factor columns.",
            )
            rc1, rc2 = st.columns([1, 1])
            with rc1:
                recovery_code = st.selectbox(
                    "Experiment code",
                    ["Auto-detect","001A","001B","001C","001D","001E","001F","001G","001H","001I","001J"],
                    index=0,
                    key="research_run_recovery_code",
                )
            with rc2:
                st.write("")
                st.write("")
                recover_clicked = st.button(
                    "📥 Import & Persist Run",
                    type="primary",
                    use_container_width=True,
                    disabled=recovery_file is None,
                    key="research_run_recovery_button",
                )
            if recover_clicked and recovery_file is not None:
                try:
                    from industrial_experience import import_research_run_csv
                    run_id, summary = import_research_run_csv(
                        study_id=str(active_protocol["study_id"]),
                        research_id=str(active_protocol["research_id"]),
                        owner=str(username),
                        uploaded=recovery_file,
                        experiment_code=None if recovery_code == "Auto-detect" else recovery_code,
                    )
                    st.success(
                        "Recovered {} · {} observations · mean regret {:.5f}".format(
                            summary["experiment_code"],
                            summary["observations"],
                            summary["mean_decision_regret"],
                        )
                    )
                    st.session_state["sx_last_recovered_run_id"] = run_id
                    st.rerun()
                except Exception as exc:
                    st.error("Run recovery failed: " + str(exc))

    with tabs[4]:
        st.markdown("### Decision records")
        if decisions.empty:
            st.info("No persisted decision records exist for this workspace.")
        else:
            st.dataframe(decisions, use_container_width=True, hide_index=True)

    with tabs[5]:
        st.markdown("### Evidence & export")
        if not active_protocol:
            st.info("Select a saved study first.")
        else:
            st.dataframe(
                pd.DataFrame([
                    {"Field":"Research ID","Value":active_protocol["research_id"]},
                    {"Field":"Study ID","Value":active_protocol["study_id"]},
                    {"Field":"Protocol hash","Value":active_protocol["protocol_hash"]},
                    {"Field":"Runs captured","Value":len(runs)},
                    {"Field":"Decision records visible","Value":len(decisions)},
                ]),
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "📥 Download complete research workspace bundle",
                data=research_evidence_bundle(active_protocol["study_id"],username),
                file_name="shoir_ie_" + _safe_key(active_protocol["study_id"]) + "_research_workspace.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True,
                key="research_workspace_export",
            )
            st.caption("The export contains persisted protocol, study index, run history and decision records. It is an evidence archive, not a scientific conclusion.")

    with tabs[6]:
        st.markdown("### 📊 Scenario Lab")
        st.caption(
            "Compare a baseline with controlled industrial alternatives. This scenario matrix complements the Research Protocol and DOE workspace; "
            "it does not replace a validated simulation or an independently verified operating result."
        )

        try:
            from industrial_platform import (
                EXPERIMENT_METRIC_COLUMNS,
                analyze_experiment_scenarios,
                init_platform_db,
                render_export_bar,
                save_experiment,
            )
            init_platform_db()
        except Exception as exc:
            st.error(f"Scenario Lab services could not initialize safely: {type(exc).__name__}: {exc}")
            return

        scenario_defaults = pd.DataFrame({
            "Scenario": ["Baseline", "High Demand", "Supplier Shock", "Capacity Expansion"],
            "Cost": [100000, 125000, 142000, 115000],
            "Service": [95, 90, 82, 98],
            "Risk": [10, 18, 35, 8],
            "Inventory": [5000, 6200, 7000, 4700],
            "Carbon": [1000, 1100, 1300, 850],
        })
        scenario_editor_key = "research_scenario_lab_matrix"
        previous_scenarios = st.session_state.get(scenario_editor_key)
        if not isinstance(previous_scenarios, pd.DataFrame):
            st.session_state[scenario_editor_key] = scenario_defaults.copy(deep=True)
        scenarios = st.data_editor(
            st.session_state[scenario_editor_key],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="research_scenario_lab_editor",
            column_config={
                "Cost": st.column_config.NumberColumn("Cost", min_value=0.0, format="%.2f"),
                "Service": st.column_config.NumberColumn("Service (%)", min_value=0.0, max_value=100.0, format="%.2f"),
                "Risk": st.column_config.NumberColumn("Risk score", min_value=0.0, format="%.2f"),
                "Inventory": st.column_config.NumberColumn("Inventory", min_value=0.0, format="%.2f"),
                "Carbon": st.column_config.NumberColumn("Carbon", min_value=0.0, format="%.2f"),
            },
        )
        st.session_state[scenario_editor_key] = scenarios.copy(deep=True)

        scenario_names = (
            scenarios["Scenario"].fillna("").astype(str).str.strip().tolist()
            if "Scenario" in scenarios.columns else []
        )
        baseline_options = list(dict.fromkeys(name for name in scenario_names if name))
        baseline_key = "research_scenario_lab_baseline"
        if baseline_key in st.session_state and st.session_state[baseline_key] not in baseline_options:
            st.session_state.pop(baseline_key, None)
        if baseline_options:
            baseline_default = st.session_state.get(baseline_key, baseline_options[0])
            if baseline_default not in baseline_options:
                baseline_default = baseline_options[0]
            baseline_scenario = st.selectbox(
                "Baseline scenario",
                baseline_options,
                index=baseline_options.index(baseline_default),
                key=baseline_key,
                help="All deltas are measured against this scenario. Change it to compare alternatives to a different reference point.",
            )
        else:
            baseline_scenario = None
            st.info("Add a non-empty scenario name to select a baseline.")

        # Include the selected baseline in the signature so changing the
        # reference point invalidates the prior saved-result attachment.
        signature_source = scenarios.to_csv(index=False) + "\\nBASELINE=" + str(baseline_scenario)
        current_signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()
        analysis_df = pd.DataFrame()
        try:
            analysis_df = analyze_experiment_scenarios(scenarios, baseline_scenario)
        except (TypeError, ValueError) as exc:
            st.warning(f"Scenario table needs attention before analysis: {exc}")

        run_col, notes_col = st.columns([1.1, 2])
        with run_col:
            save_clicked = st.button(
                "🧪 Analyze & Save",
                type="primary",
                use_container_width=True,
                disabled=len(scenarios) < 2 or analysis_df.empty,
                key="research_scenario_lab_save",
            )
        with notes_col:
            st.caption(
                "Live preview recalculates from the current table. Analyze & Save records the chosen baseline, inputs and computed results to the experiment registry."
            )

        if save_clicked:
            try:
                if len(scenarios) < 2:
                    raise ValueError("At least two scenarios are required for a comparison.")
                saved_analysis = analyze_experiment_scenarios(scenarios, baseline_scenario)
                experiment_id = save_experiment(
                    "Scenario Matrix",
                    "Experiment Lab",
                    scenarios.to_dict("records"),
                    {
                        "baseline_scenario": baseline_scenario,
                        "input_signature": current_signature,
                        "scenario_results": saved_analysis.to_dict("records"),
                    },
                    username,
                )
                st.session_state["research_scenario_lab_saved_id"] = experiment_id
                st.session_state["research_scenario_lab_saved_signature"] = current_signature
                st.session_state["research_scenario_lab_saved_results"] = saved_analysis.copy(deep=True)
                st.success(f"Scenario experiment saved: {experiment_id}")
            except Exception as exc:
                st.error(f"Scenario analysis could not be saved safely: {type(exc).__name__}: {exc}")

        saved_results = st.session_state.get("research_scenario_lab_saved_results", pd.DataFrame())
        saved_results_is_current = (
            isinstance(saved_results, pd.DataFrame)
            and not saved_results.empty
            and st.session_state.get("research_scenario_lab_saved_signature") == current_signature
        )
        if isinstance(saved_results, pd.DataFrame) and not saved_results.empty and not saved_results_is_current:
            st.info("The saved scenario analysis belongs to an earlier input table or baseline. It remains in saved history, but it will not be attached to the current inputs export.")

        if not analysis_df.empty:
            if len(scenarios) < 2:
                st.info("Add at least one alternative scenario to enable comparisons and saving.")
            else:
                st.markdown("#### 📈 KPI comparisons")
                metric_columns = [column for column in EXPERIMENT_METRIC_COLUMNS if column in analysis_df.columns]
                figure_exports = []
                if metric_columns:
                    chart_tabs = st.tabs([f"{column} comparison" for column in metric_columns])
                    for metric_name, chart_tab in zip(metric_columns, chart_tabs):
                        with chart_tab:
                            fig = px.bar(
                                analysis_df,
                                x="Scenario",
                                y=metric_name,
                                color="Baseline",
                                barmode="group",
                                title=f"{metric_name} by scenario",
                                hover_data=["Scenario"],
                            )
                            baseline_rows = analysis_df.loc[analysis_df["Baseline"]]
                            if not baseline_rows.empty:
                                fig.add_hline(
                                    y=float(baseline_rows.iloc[0][metric_name]),
                                    line_dash="dash",
                                    annotation_text=f"Baseline: {float(baseline_rows.iloc[0][metric_name]):,.4g}",
                                )
                            fig.update_layout(height=380, legend_title_text="Selected baseline")
                            st.plotly_chart(
                                fig,
                                use_container_width=True,
                                config={"displayModeBar": True, "responsive": True},
                            )
                            figure_exports.append((f"{metric_name} comparison", fig))

                if {"Cost", "Service"}.issubset(analysis_df.columns):
                    st.markdown("#### ⚖️ Cost versus service trade-off")
                    hover_columns = [column for column in ("Risk", "Inventory", "Carbon") if column in analysis_df.columns]
                    tradeoff = px.scatter(
                        analysis_df,
                        x="Cost",
                        y="Service",
                        color="Scenario",
                        hover_data=hover_columns,
                        title="Cost versus service by scenario",
                    )
                    tradeoff.update_layout(height=420)
                    st.plotly_chart(
                        tradeoff,
                        use_container_width=True,
                        config={"displayModeBar": True, "responsive": True},
                    )
                    figure_exports.append(("Cost versus service trade-off", tradeoff))

                st.markdown("#### Calculated results")
                st.dataframe(analysis_df, use_container_width=True, hide_index=True)
                tables = [
                    ("Scenario Inputs", scenarios),
                    ("Live Scenario Analysis", analysis_df),
                ]
                if saved_results_is_current:
                    tables.append(("Saved Analysis for Current Inputs", saved_results))
                render_export_bar("Experiment Lab", tables, figure_exports, tier, username)

        st.markdown("#### 🗃️ Saved scenario experiments")
        try:
            with sqlite3.connect("enterprise_full_workspace.db") as scenario_conn:
                scenario_history = pd.read_sql_query(
                    """SELECT experiment_id AS "Experiment ID", name AS Name, module AS Module,
                                      created_by AS "Created By", created_at AS "Created At"
                               FROM platform_experiments
                               WHERE module=? AND created_by=?
                               ORDER BY created_at DESC LIMIT 25""",
                    scenario_conn,
                    params=("Experiment Lab", username),
                )
            if scenario_history.empty:
                st.info("No scenario experiments are saved yet.")
            else:
                st.dataframe(scenario_history, use_container_width=True, hide_index=True)
                history_labels = {
                    str(row["Experiment ID"]): f"{row['Name']} · {row['Created At']} · {row['Experiment ID']}"
                    for _, row in scenario_history.iterrows()
                }
                open_key = "research_scenario_lab_history_open"
                if open_key in st.session_state and str(st.session_state[open_key]) not in history_labels:
                    st.session_state.pop(open_key, None)
                selected_experiment_id = st.selectbox(
                    "Inspect saved experiment",
                    list(history_labels),
                    format_func=lambda value: history_labels[str(value)],
                    key=open_key,
                )
                with sqlite3.connect("enterprise_full_workspace.db") as detail_conn:
                    stored = detail_conn.execute(
                        """SELECT scenarios_json, results_json, created_at
                           FROM platform_experiments
                           WHERE experiment_id=? AND module=? AND created_by=?""",
                        (selected_experiment_id, "Experiment Lab", username),
                    ).fetchone()
                if stored:
                    try:
                        stored_inputs = pd.DataFrame(json.loads(stored[0]))
                        stored_results_payload = json.loads(stored[1])
                        # Earlier Experiment Lab versions saved the result rows
                        # as a bare JSON list; current saves wrap them in a
                        # baseline/signature object. Support both schemas.
                        if isinstance(stored_results_payload, dict):
                            stored_result_rows = stored_results_payload.get("scenario_results")
                            if not isinstance(stored_result_rows, list):
                                stored_result_rows = stored_results_payload.get("results", [])
                        elif isinstance(stored_results_payload, list):
                            stored_result_rows = stored_results_payload
                        else:
                            stored_result_rows = []
                        stored_results = pd.DataFrame(stored_result_rows)
                        with st.expander("Saved experiment inputs and results", expanded=False):
                            st.caption(f"Saved at {stored[2]} · {selected_experiment_id}")
                            detail_tabs = st.tabs(["Inputs", "Calculated results", "Trade-off chart"])
                            with detail_tabs[0]:
                                st.dataframe(stored_inputs, use_container_width=True, hide_index=True)
                            with detail_tabs[1]:
                                if stored_results.empty:
                                    st.info("No calculated results were found in this saved record.")
                                else:
                                    st.dataframe(stored_results, use_container_width=True, hide_index=True)
                            with detail_tabs[2]:
                                if {"Cost", "Service"}.issubset(stored_results.columns) and not stored_results.empty:
                                    saved_tradeoff = px.scatter(
                                        stored_results,
                                        x="Cost",
                                        y="Service",
                                        color="Scenario",
                                        title="Saved cost versus service trade-off",
                                    )
                                    st.plotly_chart(saved_tradeoff, use_container_width=True, config={"displayModeBar": True, "responsive": True})
                                else:
                                    st.info("This saved result does not contain both Cost and Service for a trade-off chart.")
                    except Exception as exc:
                        st.warning(f"Saved experiment could not be decoded safely: {type(exc).__name__}: {exc}")
        except Exception as exc:
            st.warning(f"Saved scenario history is temporarily unavailable: {type(exc).__name__}: {exc}")

def _safe_key(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:10]


def _module_meta(module: str) -> dict:
    if str(module) in FALLBACK_MODULE_BLUEPRINTS:
        blueprint = fallback_module_blueprint(module)
        return {
            "name": str(module),
            "category": blueprint["category"],
            "tier": blueprint["tier"],
            "when": blueprint["purpose"],
            "example": blueprint["method"],
        }
    try:
        from industrial_platform import PLATFORM_CATALOG
        return next((item for item in PLATFORM_CATALOG if str(item.get("name")) == str(module)), {})
    except Exception:
        return {}


FALLBACK_MODULE_BLUEPRINT_ROWS = [
    ("Facility Layout & Warehousing", "facility", "Facilities & material flow", "Evaluate department area, from-to movement and travel burden.", "Layout / SLP review", "Department, area, from-to flow and travel-distance fields", "Coordinates and flows must come from the user's actual facility; starter values are illustrative."),
    ("Enterprise Integration & Collaboration", "integration", "Enterprise integration", "Review connector ownership, last-test status, latency and successful synchronization evidence.", "Connector readiness review", "System, protocol, latency, success rate, owner and last-test evidence", "A row in the table does not prove that a connector is live; run a real endpoint test separately."),
    ("AGV Fleet Dispatcher", "logistics", "AGV fleet dispatch", "Compare task demand with vehicle capacity and transport cost.", "Capacity and transport screening", "Task, origin, destination, demand, capacity and distance", "A capacity check is not a collision-free path plan; validate routes and safety controls in the live system."),
    ("Geospatial Network Designer", "logistics", "Network and route design", "Compare site flows, distances, capacity utilization and illustrative transport exposure.", "Network cost / service screening", "Origins, destinations, demand, vehicle capacity, distance and cost", "Do not treat sample coordinates, routes or costs as live geography or quotes."),
    ("Production Planning & Control (PPC)", "schedule", "Production planning & control", "Review work-order load and processing/setup workload by resource.", "Workload and dispatch review", "Work order, machine, quantity, processing time, setup time and due offset", "This fallback calculates workload indicators, not a constraint-validated finite-capacity schedule."),
    ("Lean Manufacturing & Shop Floor Operations", "production", "Lean and shop-floor improvement", "Inspect good-unit yield, scrap and cycle-time patterns before selecting an improvement experiment.", "Yield and loss screening", "Planned/good/scrap units, downtime and cycle time", "A suspected loss is a hypothesis until supported by observed time-study or production evidence."),
    ("Quality Control, Six Sigma & Reliability", "quality", "Quality and reliability", "Evaluate values against explicit specification limits and calculate defect-rate indicators when counts exist.", "Specification and defect review", "Measurements, lower/upper specification limits, defects and inspected quantity", "Capability indices and control limits require a suitable sampling design and assumptions; this fallback does not certify process capability."),
    ("Engineering Economics & Finance", "economics", "Engineering economics", "Compare capital outlay with annual net benefit, simple payback and simple annual return.", "Investment screening", "CapEx, annual benefit, operating cost and project life", "Simple payback/return are not a discounted cash-flow NPV or a guarantee of realized savings."),
    ("Predictive Maintenance Hub", "maintenance", "Maintenance condition triage", "Rank current rows using a transparent within-dataset index built from available condition indicators.", "Condition triage index", "Asset, runtime, temperature, vibration, downtime and failure counts", "The relative index is not a calibrated probability of failure, a diagnosis or a validated predictive model."),
    ("Human Factors & Ergonomics (NIOSH)", "workforce", "Workforce and ergonomics", "Review task cycle time, headcount and recorded ergonomic screening scores.", "Work-content and ergonomic review", "Task, operator, cycle time, ergonomic score, shift hours and headcount", "Do not label a proxy as a validated NIOSH/RULA/REBA assessment; use the appropriate protocol and trained assessor."),
    ("Digital Twin & Discrete-Event Simulation", "simulation", "Discrete-event simulation", "Compare scenario demand, capacity, service and operating outcomes from the current data table.", "Scenario feasibility screening", "Demand, capacity, lead time, downtime and scenario KPIs", "This generic fallback is a scenario screen, not a running discrete-event model unless a native simulation has been executed."),
    ("Green IE & Sustainability", "sustainability", "Green industrial engineering", "Calculate emissions from explicit quantities and factors or compare supplied baseline/scenario footprints.", "Emissions and change review", "Activity, quantity, emission factor, scope and baseline/scenario tCO2e", "Use source-dated, boundary-appropriate emission factors; estimates are not audited ESG disclosures."),
    ("Evidence Degradation & Decision-Readiness Lab", "research", "Evidence degradation research", "Inspect evidence-quality factors, outcome fields and experiment readiness before drawing a decision boundary.", "Research design and evidence review", "Completeness, freshness, conflicts, uncertainty, shock conditions and outcome", "A decision-readiness boundary must be estimated from experiments; it must not be hard-coded as a desired conclusion."),
    ("Statistical Hypothesis Testing", "research", "Statistical analysis", "Inspect effect estimates, standard errors and study design; calculate an approximate interval when supported by inputs.", "Effect and interval review", "Outcome, group, sample size, effect estimate and standard error", "The generic fallback does not replace a correctly specified t-test/ANOVA/regression method or multiplicity review."),
    ("LaTeX Document Formatter", "document", "Technical document preparation", "Track sections, equation checks, reference checks and review status before producing a manuscript.", "Document completeness check", "Section, source-data linkage, equation/reference checks and review status", "Completeness does not validate LaTeX compilation, scientific claims or citations."),
    ("Literature & Citation Matrix", "literature", "Literature evidence management", "Organize papers, DOI metadata, methods, sample sizes and research gaps for review.", "Citation-matrix completeness", "Paper ID, title, authors/year, DOI, method, sample size and research gap", "Do not mark a citation verified unless it has been checked against a reliable source."),
    ("Advanced Regression Analysis", "research", "Regression research", "Summarize supplied effect estimates and standard errors and expose missing inputs before a model is fitted.", "Effect-size and interval review", "Outcome, predictors, estimate, standard error and sample size", "The fallback must not present descriptive intervals as a fitted regression or causal result."),
    ("Live Reproducible Paper Canvas", "document", "Reproducible paper workflow", "Link each manuscript section to data, code/run IDs, review status and reproducibility evidence.", "Reproducibility checklist", "Section, dataset/run reference, equation/reference checks and review status", "A complete checklist is not proof that the paper reruns unless the linked workflow was executed."),
    ("Paper-to-Simulation Auto-Engine", "research", "Paper-to-simulation translation", "Record extracted assumptions, parameters, mappings and validation state before generating a simulation.", "Assumption-to-model mapping", "Parameter, value, unit, source passage, mapping status and test result", "Automated extraction is a draft; confirm units, assumptions and equations against the source paper."),
    ("Automated Theory-to-Code Formalizer", "formal", "Theory-to-code formalization", "Track claims, assumptions, variables, equations, code links and verification status.", "Formalization readiness", "Claim, assumptions, equation/code reference, proof/test status", "A formalization status is not a machine-checked proof unless an actual proof backend completed successfully."),
    ("Automated Code-to-Formal-Proof Verifier", "formal", "Code and proof verification", "Organize the verification claim, code version, assumptions, proof/test results and reviewer disposition.", "Verification evidence review", "Code version/hash, claim, assumptions, proof result and test result", "Do not claim a proof passed when the proof/test result is missing, pending or supplied only as text."),
    ("Adversarially Stressed Synthetic Industrial Twins", "simulation", "Synthetic industrial twin stress testing", "Compare baseline and shock scenarios for demand, capacity, cost, service and risk.", "Shock-scenario comparison", "Baseline conditions, shock factors, seed, demand/capacity and outcome KPIs", "Synthetic results must be labelled synthetic and should not be generalized to a real plant without validation."),
    ("Adversarial AI Peer-Review Swarm", "research", "Adversarial research review", "Track claims, evidence citations, reproducibility questions and reviewer findings in one triage queue.", "Claim/evidence review", "Claim, evidence reference, reproducibility status, severity and reviewer disposition", "AI review findings are suggestions for human review, not an authoritative peer-review acceptance decision."),
    ("Adversarial Chaos & Shock Injector", "simulation", "Operational shock testing", "Define baseline and shock factors, run identifiers, affected constraints and observed output deltas.", "Shock and resilience review", "Shock type, severity, seed, affected process, baseline and outcome", "Do not inject shocks into live operations without an approved, isolated test environment."),
    ("Autonomous Parametric Surrogate Swarm", "simulation", "Surrogate model experiments", "Track input ranges, surrogate predictions, validation residuals and domain-of-validity flags.", "Surrogate validation review", "Input parameters, predicted response, observed response and residual", "A surrogate prediction is not a validated physical outcome; validate against held-out observations."),
    ("Real-Time Quantum-Classical Hybrid Optimization Router", "optimization", "Advanced optimization method routing", "Record problem structure, solver/method selection, feasibility, runtime and objective result.", "Solver suitability review", "Problem type, variables, constraints, method, status, runtime and objective", "The fallback is a routing/readiness checklist, not evidence of quantum hardware execution."),
    ("Decentralized Cryptographic Reproducibility Vault", "security", "Reproducibility and provenance", "Inspect artifact identifiers, content hashes, signatures, owner and verification state.", "Provenance completeness", "Artifact ID/type, source version, hash, signature status and verifier result", "A populated hash field is not a verified signature or an immutable decentralized record."),
    ("🔌 Edge-Connected IoT Digital Twin Bridge", "connectivity", "Edge telemetry bridge", "Review endpoint/protocol setup, telemetry freshness, latency and last-test results.", "Connector readiness review", "Asset, endpoint, protocol, latency, success rate, last test and owner", "Imported or sample telemetry does not prove that an edge device is connected now."),
    ("🔌 Universal Cross-Domain Mathematical Isomorphism Engine (UCMIE)", "math", "Cross-domain model correspondence", "Record mappings between domain entities, units, invariants and constraint-preservation checks.", "Mapping and invariant review", "Source entity, target entity, dimension compatibility and preserved constraint", "A correspondence table is not proof of mathematical isomorphism unless required conditions are formally established."),
    ("🔄 Autonomous Epistemic Cross-Disciplinary Falsification Matrix (AE-FRESM)", "research", "Cross-disciplinary falsification", "Record a claim, domain assumptions, falsifying tests, evidence coverage and reviewer disposition.", "Falsification plan review", "Claim, assumptions, proposed test, evidence reference and result status", "The module should report untested hypotheses as open, not as falsified or confirmed."),
    ("Autonomous Cognitive Operations & Zero-Knowledge Mesh (ACO-ZKMS)", "security", "Governed operations and proof readiness", "Track operation IDs, approvals, artifact references and cryptographic-verification status.", "Governance and proof readiness", "Operation, owner, approval, artifact hash, proof status and audit reference", "A workflow ledger does not itself provide zero-knowledge security guarantees."),
    ("⚡ ACO-ZKMS Master Engine", "security", "Governed orchestration", "Inspect dependencies, approvals, artifact lineage, execution state and verification evidence.", "Orchestration readiness review", "Workflow step, dependency, approval, artifact reference and result status", "Do not represent planned, demo or mocked steps as completed production actions."),
]

FALLBACK_MODULE_BLUEPRINTS = {
    name: {
        "module": name,
        "family": family,
        "focus": focus,
        "purpose": purpose,
        "method": method,
        "inputs": inputs,
        "guardrail": guardrail,
        "first_run": f"Confirm that the input fields and assumptions for {focus.lower()} match your project before running the analysis.",
    }
    for name, family, focus, purpose, method, inputs, guardrail in FALLBACK_MODULE_BLUEPRINT_ROWS
}

# Keep these labels aligned with the actual subscription/module catalogue.
# They are descriptive metadata only and do not replace the application's
# tier-entitlement check.
FALLBACK_MODULE_CATALOG_META = {
    "Facility Layout & Warehousing": ("Facilities", "Starter"),
    "Enterprise Integration & Collaboration": ("Platform", "Starter"),
    "AGV Fleet Dispatcher": ("Logistics", "Mid-Tier Pro"),
    "Geospatial Network Designer": ("Network Design", "Mid-Tier Pro"),
    "Production Planning & Control (PPC)": ("Production", "Mid-Tier Pro"),
    "Lean Manufacturing & Shop Floor Operations": ("Production", "Mid-Tier Pro"),
    "Quality Control, Six Sigma & Reliability": ("Quality", "Mid-Tier Pro"),
    "Engineering Economics & Finance": ("Finance", "Mid-Tier Pro"),
    "Predictive Maintenance Hub": ("Operations", "Enterprise"),
    "Human Factors & Ergonomics (NIOSH)": ("Human Factors", "Enterprise"),
    "Digital Twin & Discrete-Event Simulation": ("Digital Twin", "Enterprise"),
    "Green IE & Sustainability": ("Sustainability", "Enterprise"),
    "Evidence Degradation & Decision-Readiness Lab": ("Research & Experimentation", "Research Pack"),
    "Statistical Hypothesis Testing": ("Research Authoring", "Research Pack"),
    "LaTeX Document Formatter": ("Research Authoring", "Research Pack"),
    "Literature & Citation Matrix": ("Research Authoring", "Research Pack"),
    "Advanced Regression Analysis": ("Research Authoring", "Research Pack"),
    "Live Reproducible Paper Canvas": ("Research Authoring", "Research Pack"),
    "Paper-to-Simulation Auto-Engine": ("Paper-to-Simulation Pipeline", "Research Pack"),
    "Automated Theory-to-Code Formalizer": ("Paper-to-Simulation Pipeline", "Research Pack"),
    "Automated Code-to-Formal-Proof Verifier": ("Paper-to-Simulation Pipeline", "Research Pack"),
    "Adversarially Stressed Synthetic Industrial Twins": ("Paper-to-Simulation Pipeline", "Research Pack"),
    "Adversarial AI Peer-Review Swarm": ("Peer Review & Stress-Testing", "Research Pack"),
    "Adversarial Chaos & Shock Injector": ("Peer Review & Stress-Testing", "Research Pack"),
    "Autonomous Parametric Surrogate Swarm": ("Peer Review & Stress-Testing", "Research Pack"),
    "Real-Time Quantum-Classical Hybrid Optimization Router": ("Advanced Computation Infrastructure", "Research Pack"),
    "Decentralized Cryptographic Reproducibility Vault": ("Advanced Computation Infrastructure", "Research Pack"),
    "🔌 Edge-Connected IoT Digital Twin Bridge": ("Advanced Computation Infrastructure", "Research Pack"),
    "🔌 Universal Cross-Domain Mathematical Isomorphism Engine (UCMIE)": ("Advanced Computation Infrastructure", "Research Pack"),
    "🔄 Autonomous Epistemic Cross-Disciplinary Falsification Matrix (AE-FRESM)": ("Advanced Computation Infrastructure", "Research Pack"),
    "Autonomous Cognitive Operations & Zero-Knowledge Mesh (ACO-ZKMS)": ("Advanced Computation Infrastructure", "Research Pack"),
    "⚡ ACO-ZKMS Master Engine": ("Advanced Computation Infrastructure", "Research Pack"),
}


def fallback_module_blueprint(module: str) -> dict[str, Any]:
    """Return a specific, conservative workflow definition for a generic fallback module."""
    name = str(module)
    blueprint = dict(FALLBACK_MODULE_BLUEPRINTS.get(name, {}))
    category, required_tier = FALLBACK_MODULE_CATALOG_META.get(
        name, ("Industrial Engineering", "Starter")
    )
    blueprint.setdefault("module", name)
    blueprint.setdefault("family", "generic")
    blueprint.setdefault("focus", "Industrial engineering analysis")
    blueprint.setdefault("purpose", "Prepare, validate, compare and export the data for this module.")
    blueprint.setdefault("method", "Baseline / scenario comparison")
    blueprint.setdefault("inputs", "Name rows clearly and provide a numeric KPI or measure.")
    blueprint.setdefault("guardrail", "Confirm assumptions and verify results against the real operating context before acting.")
    blueprint.setdefault("first_run", "Replace illustrative values with observed data and record the source and units.")
    blueprint["category"] = category
    blueprint["tier"] = required_tier
    return blueprint


def analyze_fallback_module(module: str, frame: pd.DataFrame) -> dict[str, Any]:
    """Run a safe, input-driven module-specific analysis for the shared fallback canvas.

    Calculations use only columns present in the user's table. They do not call
    external systems or represent sample data as live data or verified outcomes.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("Add a non-empty input table before running this module analysis.")
    blueprint = fallback_module_blueprint(module)
    family = blueprint["family"]
    result = frame.copy(deep=True)
    metrics: dict[str, Any] = {}
    chart_x = None
    chart_y = None
    chart_kind = "bar"

    def column(*candidates: str) -> str | None:
        normalized = {str(c).strip().lower().replace(" ", "_"): str(c) for c in result.columns}
        for candidate in candidates:
            key = candidate.strip().lower().replace(" ", "_")
            if key in normalized:
                return normalized[key]
        return None

    def numeric(name: str | None) -> pd.Series | None:
        return pd.to_numeric(result[name], errors="coerce") if name and name in result.columns else None

    def first_categorical(*candidates: str) -> str | None:
        for candidate in candidates:
            found = column(candidate)
            if found and not pd.api.types.is_numeric_dtype(result[found]):
                return found
        return next((str(c) for c in result.columns if not pd.api.types.is_numeric_dtype(result[c])), None)

    def record_completeness(columns: list[str]) -> pd.Series:
        block = result[columns]
        present = block.notna().copy()
        for field in columns:
            if pd.api.types.is_object_dtype(block[field]) or pd.api.types.is_string_dtype(block[field]):
                present[field] = present[field] & block[field].astype(str).str.strip().ne("")
        return present.mean(axis=1) * 100.0

    if family == "quality":
        measured = column("Measured_Value", "Measurement", "Value")
        low_name, high_name = column("Lower_Spec", "LSL"), column("Upper_Spec", "USL")
        defect_name, inspected_name = column("Defect_Count", "Defects"), column("Inspected_Count", "Inspected")
        if measured and low_name and high_name:
            val, low, high = numeric(measured), numeric(low_name), numeric(high_name)
            valid = val.notna() & low.notna() & high.notna() & high.ge(low)
            result["Within_Spec"] = valid & val.ge(low) & val.le(high)
            result["Spec_Deviation"] = np.where(valid, np.maximum(low-val, 0) + np.maximum(val-high, 0), np.nan)
            metrics["Within specification (%)"] = round(float(result.loc[valid, "Within_Spec"].mean() * 100), 2) if valid.any() else None
            chart_x, chart_y = first_categorical("Part", "Workcenter", "Line"), measured
        if defect_name and inspected_name:
            defects, inspected = numeric(defect_name), numeric(inspected_name)
            valid_counts = inspected.gt(0) & defects.notna()
            result["Defect_Rate_pct"] = np.where(valid_counts, defects / inspected * 100, np.nan)
            result["First_Pass_Yield_pct"] = np.where(valid_counts, 100 - result["Defect_Rate_pct"], np.nan)
            metrics["Defect rate (%)"] = round(float(result.loc[valid_counts, "Defect_Rate_pct"].mean()), 2) if valid_counts.any() else None
            if not chart_y:
                chart_x, chart_y = first_categorical("Part", "Workcenter", "Line"), "Defect_Rate_pct"
        if not any(k in result.columns for k in ("Within_Spec", "Defect_Rate_pct")):
            raise ValueError("For quality analysis, provide measurement/specification columns or Defect_Count and Inspected_Count.")
    elif family == "maintenance":
        signal_names = [column("Temperature_C", "Temperature"), column("Vibration_mm_s", "Vibration"), column("Downtime_Hours", "Downtime"), column("Failure_Count", "Failures"), column("Runtime_Hours", "Runtime")]
        signals = [name for name in signal_names if name and numeric(name) is not None and numeric(name).notna().any()]
        if not signals:
            raise ValueError("For maintenance triage, include at least one numeric condition indicator such as temperature, vibration, downtime or failure count.")
        normalized = []
        for name in signals:
            values = numeric(name)
            lo, hi = values.quantile(0.05), values.quantile(0.95)
            score = pd.Series(50.0, index=values.index) if pd.isna(lo) or pd.isna(hi) or hi <= lo else ((values-lo)/(hi-lo)*100).clip(0,100)
            normalized.append(score.fillna(0))
        result["Relative_Triage_Index_0_100"] = pd.concat(normalized, axis=1).mean(axis=1)
        result["Relative_Triage_Band"] = pd.cut(result["Relative_Triage_Index_0_100"], [-0.01, 33.333, 66.666, 100.01], labels=["Lower", "Middle", "Higher"]).astype(str)
        metrics["Assets / rows reviewed"] = int(len(result))
        metrics["Mean relative triage index"] = round(float(result["Relative_Triage_Index_0_100"].mean()), 2)
        metrics["Condition indicators used"] = len(signals)
        chart_x, chart_y = first_categorical("Asset", "Machine", "Equipment"), "Relative_Triage_Index_0_100"
    elif family == "inventory":
        onhand_name, demand_name = column("On_Hand_Units", "On_Hand", "Inventory"), column("Daily_Demand_Units", "Daily_Demand", "Demand")
        lead_name, safety_name = column("Lead_Time_Days", "Lead_Time"), column("Safety_Stock_Units", "Safety_Stock")
        if not onhand_name or not demand_name:
            raise ValueError("For inventory review, include On_Hand_Units and Daily_Demand_Units.")
        onhand, demand = numeric(onhand_name), numeric(demand_name)
        valid = demand.gt(0) & onhand.notna()
        result["Days_Of_Cover"] = np.where(valid, onhand / demand, np.nan)
        lead = numeric(lead_name) if lead_name else pd.Series(0.0, index=result.index)
        safety = numeric(safety_name).fillna(0) if safety_name else pd.Series(0.0, index=result.index)
        lead = lead.fillna(0).clip(lower=0)
        result["Reorder_Point_Units"] = lead * demand + safety
        result["Reorder_Review"] = valid & onhand.lt(result["Reorder_Point_Units"])
        metrics["SKUs below reorder point"] = int(result["Reorder_Review"].sum())
        metrics["SKUs reviewed"] = int(valid.sum())
        metrics["Mean days of cover"] = round(float(result.loc[valid, "Days_Of_Cover"].mean()), 2) if valid.any() else None
        chart_x, chart_y = first_categorical("SKU", "Item", "Material"), "Days_Of_Cover"
    elif family == "logistics":
        demand_name, cap_name = column("Demand_Units", "DemandQty", "Demand"), column("Vehicle_Capacity", "Capacity_Units", "Capacity")
        if demand_name and cap_name:
            demand, cap = numeric(demand_name), numeric(cap_name)
            valid = cap.gt(0) & demand.notna()
            result["Capacity_Use_pct"] = np.where(valid, demand/cap*100, np.nan)
            metrics["Rows exceeding vehicle capacity"] = int((valid & demand.gt(cap)).sum())
            metrics["Mean capacity use (%)"] = round(float(result.loc[valid, "Capacity_Use_pct"].mean()), 2) if valid.any() else None
            chart_y = "Capacity_Use_pct"
        distance_name, cost_name = column("Distance_km", "Distance"), column("Cost_SAR_per_km", "Cost_per_km")
        if distance_name and cost_name:
            distance, unit_cost = numeric(distance_name), numeric(cost_name)
            result["Estimated_Transport_Cost"] = distance * unit_cost
            metrics["Estimated transport cost (table currency)"] = round(float(result["Estimated_Transport_Cost"].sum(skipna=True)), 2)
            chart_y = chart_y or "Estimated_Transport_Cost"
        if chart_y is None:
            raise ValueError("For logistics analysis, include demand/capacity or distance/cost columns.")
        chart_x = first_categorical("Task", "Route", "Origin", "Destination", "Vehicle")
    elif family == "facility":
        flow_name, distance_name = column("FromTo_Flows_per_Day", "Flow", "Trips_per_Day"), column("Travel_Distance_m", "Distance_m", "Distance")
        if flow_name and distance_name:
            flow, distance = numeric(flow_name), numeric(distance_name)
            result["Weighted_Flow_Distance"] = flow * distance
            metrics["Total weighted flow-distance (flow × metres)"] = round(float(result["Weighted_Flow_Distance"].sum(skipna=True)), 2)
            chart_y = "Weighted_Flow_Distance"
        area_name = column("Area_m2", "Area")
        if area_name:
            metrics["Total listed area (m²)"] = round(float(numeric(area_name).sum(skipna=True)), 2)
            chart_y = chart_y or area_name
        if chart_y is None:
            raise ValueError("For facility analysis, include department area or from-to flow and distance fields.")
        chart_x = first_categorical("Department", "Workcenter", "Area_Name")
    elif family == "production":
        planned_name, good_name = column("Planned_Units", "Planned_Qty"), column("Good_Units", "Good_Qty")
        scrap_name = column("Scrap_Units", "Scrap_Qty")
        if not planned_name or not good_name:
            raise ValueError("For production analysis, include Planned_Units and Good_Units.")
        planned, good = numeric(planned_name), numeric(good_name)
        valid = planned.gt(0) & good.notna()
        result["Good_Unit_Yield_pct"] = np.where(valid, good/planned*100, np.nan)
        # Use the numeric-coerced series for the weighted calculation. Imported
        # Excel columns often arrive as object/string dtype, whose .sum() may
        # concatenate values or fail instead of calculating a numeric yield.
        total_planned = float(planned.loc[valid].sum())
        total_good = float(good.loc[valid].sum())
        metrics["Weighted good-unit yield (%)"] = round(total_good / total_planned * 100, 2) if valid.any() and total_planned > 0 else None
        if scrap_name:
            scrap = numeric(scrap_name)
            result["Scrap_Rate_pct"] = np.where(valid & scrap.notna(), scrap/planned*100, np.nan)
            metrics["Mean scrap rate (%)"] = round(float(result.loc[valid, "Scrap_Rate_pct"].mean()), 2) if valid.any() else None
        chart_x, chart_y = first_categorical("Line", "Product", "Work_Order"), "Good_Unit_Yield_pct"
    elif family == "sustainability":
        quantity_name, factor_name = column("Quantity", "Quantity_Units"), column("Emission_Factor", "EmissionFactor")
        baseline_name, scenario_name = column("Baseline_tCO2e", "Baseline_tCO2", "Baseline_Emissions"), column("Scenario_tCO2e", "Scenario_tCO2", "Scenario_Emissions")
        if quantity_name and factor_name:
            quantity, factor = numeric(quantity_name), numeric(factor_name)
            result["Calculated_tCO2e"] = quantity * factor / 1000.0
            metrics["Calculated total tCO2e"] = round(float(result["Calculated_tCO2e"].sum(skipna=True)), 4)
            chart_y = "Calculated_tCO2e"
        if baseline_name and scenario_name:
            base, scenario = numeric(baseline_name), numeric(scenario_name)
            result["Scenario_Change_tCO2e"] = scenario - base
            result["Scenario_Change_pct"] = np.where(base.ne(0), (scenario-base)/base.abs()*100, np.nan)
            metrics["Baseline total tCO2e"] = round(float(base.sum(skipna=True)), 4)
            metrics["Scenario total tCO2e"] = round(float(scenario.sum(skipna=True)), 4)
            metrics["Scenario change (%)"] = round(float((scenario.sum(skipna=True)-base.sum(skipna=True))/abs(base.sum(skipna=True))*100), 2) if base.sum(skipna=True) else None
            chart_y = chart_y or "Scenario_Change_tCO2e"
        if chart_y is None:
            raise ValueError("For sustainability analysis, supply Quantity and Emission_Factor or baseline and scenario emissions.")
        chart_x = first_categorical("Activity", "Scope", "Area", "Line")
    elif family == "economics":
        capex_name, benefit_name, opex_name = column("CapEx_SAR", "CapEx", "Capital_Cost"), column("Annual_Benefit_SAR", "Annual_Benefit", "Annual_Savings"), column("Annual_Operating_Cost_SAR", "Annual_Operating_Cost", "Annual_Opex")
        if not capex_name or not benefit_name:
            raise ValueError("For investment screening, include CapEx and Annual_Benefit columns.")
        capex, benefit = numeric(capex_name), numeric(benefit_name)
        opex = numeric(opex_name).fillna(0) if opex_name else pd.Series(0.0, index=result.index)
        result["Annual_Net_Benefit"] = benefit - opex
        valid = capex.gt(0) & result["Annual_Net_Benefit"].gt(0)
        result["Simple_Payback_Years"] = np.where(valid, capex/result["Annual_Net_Benefit"], np.nan)
        result["Simple_Annual_Return_pct"] = np.where(capex.gt(0), result["Annual_Net_Benefit"]/capex*100, np.nan)
        metrics["Total initial CapEx"] = round(float(capex.sum(skipna=True)), 2)
        metrics["Total annual net benefit"] = round(float(result["Annual_Net_Benefit"].sum(skipna=True)), 2)
        metrics["Weighted simple payback (years)"] = round(float(capex.sum()/result["Annual_Net_Benefit"].sum()), 2) if capex.sum()>0 and result["Annual_Net_Benefit"].sum()>0 else None
        chart_x, chart_y = first_categorical("Alternative", "Project", "Option"), "Annual_Net_Benefit"
    elif family == "schedule":
        process_name, setup_name = column("Processing_Min", "Processing_Time_Min"), column("Setup_Min", "Setup_Time_Min")
        if not process_name:
            raise ValueError("For scheduling workload review, include Processing_Min; Setup_Min is optional.")
        result["Work_Content_Minutes"] = numeric(process_name).fillna(0) + (numeric(setup_name).fillna(0) if setup_name else 0)
        machine_name = column("Machine", "Workcenter", "Resource")
        if machine_name:
            grouped = result.groupby(machine_name, dropna=False)["Work_Content_Minutes"].sum().reset_index(name="Total_Work_Content_Min")
            chart_x, chart_y = machine_name, "Total_Work_Content_Min"
            result = result.merge(grouped, on=machine_name, how="left")
            metrics["Resources reviewed"] = int(grouped[machine_name].nunique(dropna=False))
            metrics["Highest resource workload (min)"] = round(float(grouped["Total_Work_Content_Min"].max()), 2) if not grouped.empty else None
        else:
            chart_x, chart_y = first_categorical("Work_Order", "Order", "Product"), "Work_Content_Minutes"
        metrics["Total work content (min)"] = round(float(result["Work_Content_Minutes"].sum()), 2)
    elif family == "research":
        estimate_name, se_name = column("Effect_Estimate", "Estimate", "Coefficient"), column("Standard_Error", "Std_Error", "SE")
        if estimate_name and se_name:
            estimate, standard_error = numeric(estimate_name), numeric(se_name)
            valid = standard_error.gt(0) & estimate.notna()
            result["Approx_Z_Ratio"] = np.where(valid, estimate/standard_error, np.nan)
            result["Normal_Approx_CI95_Lower"] = np.where(valid, estimate-1.96*standard_error, np.nan)
            result["Normal_Approx_CI95_Upper"] = np.where(valid, estimate+1.96*standard_error, np.nan)
            metrics["Rows with valid effect/SE"] = int(valid.sum())
            chart_x, chart_y = first_categorical("Scenario", "Study_ID", "Paper_ID", "Condition"), estimate_name
        else:
            numeric_columns = [str(c) for c in result.columns if pd.api.types.is_numeric_dtype(result[c])]
            if not numeric_columns:
                raise ValueError("For research analysis, include a numeric outcome, effect estimate or quality measure.")
            metrics["Numeric fields available"] = len(numeric_columns)
            metrics["Rows available"] = len(result)
            chart_x, chart_y = first_categorical("Scenario", "Paper_ID", "Study_ID"), numeric_columns[0]
    elif family == "literature":
        expected = [name for name in ("Title", "Authors_Year", "DOI", "Method", "Research_Gap") if name in result.columns]
        if not expected:
            raise ValueError("For the literature matrix, include bibliographic metadata and a Research_Gap or DOI column.")
        completeness = result[expected].notna() & result[expected].astype(str).apply(lambda col: col.str.strip().ne(""))
        result["Metadata_Completeness_pct"] = completeness.mean(axis=1)*100
        metrics["Papers reviewed"] = len(result)
        metrics["Mean metadata completeness (%)"] = round(float(result["Metadata_Completeness_pct"].mean()), 2)
        doi = column("DOI")
        if doi:
            metrics["Rows with DOI text"] = int(result[doi].fillna("").astype(str).str.strip().ne("").sum())
        chart_x, chart_y = first_categorical("Paper_ID", "Title"), "Metadata_Completeness_pct"
    elif family == "document":
        field_names = [name for name in ("Section", "Source_Data_Linked", "Equation_Check", "Reference_Check", "Review_Status") if name in result.columns]
        if not field_names:
            raise ValueError("For document checks, include sections plus source/equation/reference/review status fields.")
        result["Field_Completeness_pct"] = record_completeness(field_names)
        metrics["Artifacts / sections reviewed"] = len(result)
        metrics["Mean field completeness (%)"] = round(float(result["Field_Completeness_pct"].mean()), 2)
        chart_x, chart_y = first_categorical("Section", "Artifact_ID", "Document"), "Field_Completeness_pct"
    elif family == "formal":
        field_names = [name for name in ("Assumptions", "Proof_Status", "Test_Status", "Claim", "Equation_Reference") if name in result.columns]
        if not field_names:
            raise ValueError("For formalization review, include claims, assumptions and proof/test status fields.")
        result["Verification_Record_Completeness_pct"] = record_completeness(field_names)
        metrics["Claims / artifacts reviewed"] = len(result)
        metrics["Mean verification-record completeness (%)"] = round(float(result["Verification_Record_Completeness_pct"].mean()), 2)
        chart_x, chart_y = first_categorical("Artifact_ID", "Claim"), "Verification_Record_Completeness_pct"
    elif family == "security":
        field_names = [name for name in ("Artifact_ID", "Artifact_Type", "Owner", "SHA256", "Signature_Status", "Verification_Status") if name in result.columns]
        if not field_names:
            raise ValueError("For provenance review, include artifact identity, owner and verification-status fields.")
        result["Provenance_Metadata_Completeness_pct"] = record_completeness(field_names)
        metrics["Artifacts reviewed"] = len(result)
        metrics["Mean provenance metadata completeness (%)"] = round(float(result["Provenance_Metadata_Completeness_pct"].mean()), 2)
        chart_x, chart_y = first_categorical("Artifact_ID", "Artifact_Type"), "Provenance_Metadata_Completeness_pct"
    elif family in {"connectivity", "integration"}:
        latency_name, success_name, status_name = column("Latency_ms", "Latency"), column("Success_Rate_pct", "Success_Rate"), column("Status")
        if not status_name and not latency_name and not success_name:
            raise ValueError("For integration readiness, include Status, Latency_ms or Success_Rate_pct from an actual connector test.")
        if success_name:
            success = numeric(success_name)
            result["Success_Rate_pct_numeric"] = success.clip(0, 100)
            metrics["Mean recorded success rate (%)"] = round(float(success.mean()), 2) if success.notna().any() else None
        if latency_name:
            latency = numeric(latency_name)
            metrics["Mean recorded latency (ms)"] = round(float(latency.mean()), 2) if latency.notna().any() else None
        if status_name:
            metrics["Rows with status marked connected/healthy"] = int(result[status_name].astype(str).str.casefold().isin({"connected","healthy","passed","success","ok"}).sum())
        metrics["Connectors / rows reviewed"] = len(result)
        chart_x, chart_y = first_categorical("Connector", "Target_System", "System", "Status"), (success_name if success_name else latency_name)
    elif family == "math":
        field_names = [name for name in ("Dimensional_Compatible", "Constraint_Preserved", "Correspondence", "Evidence_Note") if name in result.columns]
        if not field_names:
            raise ValueError("For cross-domain mapping, include correspondence, dimension compatibility or constraint preservation fields.")
        result["Mapping_Record_Completeness_pct"] = record_completeness(field_names)
        metrics["Mappings reviewed"] = len(result)
        metrics["Mean mapping-record completeness (%)"] = round(float(result["Mapping_Record_Completeness_pct"].mean()), 2)
        chart_x, chart_y = first_categorical("Source_Entity", "Source_Domain", "Mapping_ID"), "Mapping_Record_Completeness_pct"
    elif family == "optimization":
        numeric_columns = [str(c) for c in result.columns if pd.api.types.is_numeric_dtype(result[c])]
        if not numeric_columns:
            raise ValueError("For optimization routing, supply numeric objective/constraint descriptors and record a solver run separately.")
        result["Optimization_Input_Completeness_pct"] = result[numeric_columns].notna().mean(axis=1)*100
        metrics["Alternatives / rows reviewed"] = len(result)
        metrics["Numeric descriptors"] = len(numeric_columns)
        chart_x, chart_y = first_categorical("Scenario", "Problem_Type", "Objective"), numeric_columns[0]
    elif family == "simulation":
        demand_name, capacity_name = column("Demand_Units", "Demand"), column("Capacity_Units", "Capacity")
        if demand_name and capacity_name:
            demand, capacity = numeric(demand_name), numeric(capacity_name)
            valid = capacity.gt(0) & demand.notna()
            result["Demand_to_Capacity_pct"] = np.where(valid, demand/capacity*100, np.nan)
            result["Capacity_Shortfall_Units"] = np.maximum(demand-capacity, 0)
            metrics["Rows with demand above capacity"] = int((valid & demand.gt(capacity)).sum())
            metrics["Total capacity shortfall units"] = round(float(result["Capacity_Shortfall_Units"].sum(skipna=True)), 2)
            chart_y = "Demand_to_Capacity_pct"
        else:
            numeric_columns = [str(c) for c in result.columns if pd.api.types.is_numeric_dtype(result[c])]
            if not numeric_columns:
                raise ValueError("For simulation review, include numeric scenario drivers or outcomes.")
            chart_y = numeric_columns[0]
        chart_x = first_categorical("Scenario", "Asset", "Condition", "Shock")
    elif family == "workforce":
        cycle_name, score_name, count_name = column("Cycle_Time_Sec", "Cycle_Time", "Observed_Time"), column("Ergonomic_Risk_Score", "Risk_Score"), column("Headcount", "Operators")
        if cycle_name:
            cycle = numeric(cycle_name)
            metrics["Mean cycle time (sec)"] = round(float(cycle.mean()), 2) if cycle.notna().any() else None
            result["Cycle_Time_Index"] = cycle
            chart_y = "Cycle_Time_Index"
        if score_name:
            score = numeric(score_name)
            metrics["Mean recorded ergonomic screening score"] = round(float(score.mean()), 2) if score.notna().any() else None
            chart_y = chart_y or score_name
        if count_name:
            metrics["Total listed headcount"] = round(float(numeric(count_name).sum(skipna=True)), 2)
        if chart_y is None:
            raise ValueError("For workforce review, include cycle time, headcount or an explicitly sourced screening score.")
        chart_x = first_categorical("Task", "Operator", "Workcenter")
    else:
        numeric_columns = [str(c) for c in result.columns if pd.api.types.is_numeric_dtype(result[c])]
        if not numeric_columns:
            raise ValueError("Add numeric measures to enable the fallback analysis for this module.")
        baseline_name = numeric_columns[0]
        baseline = numeric(baseline_name).iloc[0]
        for name in numeric_columns[1:]:
            result[f"{name}_Delta_vs_First_Row"] = numeric(name) - baseline
        metrics["Rows reviewed"] = len(result)
        metrics["Numeric measures"] = len(numeric_columns)
        chart_x, chart_y = first_categorical(), numeric_columns[0]

    return {
        "result": result,
        "metrics": metrics,
        "chart_x": chart_x,
        "chart_y": chart_y,
        "chart_kind": chart_kind,
        "method": blueprint["method"],
        "guardrail": blueprint["guardrail"],
    }


def _starter_data(module: str) -> pd.DataFrame:
    """Return editable, domain-shaped demo inputs for generic module fallbacks.

    These are clearly illustrative starter values. They help a user discover the
    expected schema but must never be presented as observations from a real plant.
    """
    lower = str(module).lower()
    blueprint = fallback_module_blueprint(module)
    family = blueprint["family"]

    # Research/engineering infrastructure modules get purpose-built schemas
    # so their fallback workspace is useful before users import real project data.
    if family == "literature":
        return pd.DataFrame({
            "Paper_ID": ["P-001", "P-002", "P-003"],
            "Title": ["Illustrative paper A", "Illustrative paper B", "Illustrative paper C"],
            "Authors_Year": ["Example et al. (2023)", "Example et al. (2024)", "Example et al. (2025)"],
            "DOI": ["", "", ""],
            "Method": ["Simulation", "DOE", "Regression"],
            "Sample_Size": [120, 80, 240],
            "Research_Gap": ["Missing transfer test", "Unclear uncertainty bounds", "Limited external validation"],
            "Citation_Verified": [False, False, False],
        })
    if family == "document":
        return pd.DataFrame({
            "Artifact_ID": ["DOC-001", "DOC-002", "DOC-003", "DOC-004"],
            "Section": ["Problem statement", "Methods", "Results", "Limitations"],
            "Source_Data_Linked": [True, True, False, True],
            "Equation_Check": ["Pending", "Pending", "Pending", "Pending"],
            "Reference_Check": ["Pending", "Pending", "Pending", "Pending"],
            "Review_Status": ["Draft", "Draft", "Draft", "Draft"],
        })
    if family == "formal":
        return pd.DataFrame({
            "Artifact_ID": ["FORM-001", "FORM-002", "FORM-003"],
            "Claim": ["Constraint identity is preserved", "Units remain consistent", "Output is reproducible"],
            "Assumptions": ["Document inputs and scope", "Record units and mappings", "Pin data/code versions"],
            "Equation_Reference": ["EQ-01", "EQ-02", "EQ-03"],
            "Proof_Status": ["Pending", "Pending", "Pending"],
            "Test_Status": ["Not run", "Not run", "Not run"],
        })
    if family == "security":
        return pd.DataFrame({
            "Artifact_ID": ["ART-001", "ART-002", "ART-003"],
            "Artifact_Type": ["Dataset", "Model", "Run"],
            "Owner": ["Operations", "Engineering", "Research"],
            "SHA256": ["", "", ""],
            "Signature_Status": ["Pending", "Pending", "Pending"],
            "Verification_Status": ["Not verified", "Not verified", "Not verified"],
        })
    if family in {"connectivity", "integration"}:
        return pd.DataFrame({
            "Connector": ["MES demo", "ERP demo", "Telemetry demo"],
            "Target_System": ["MES", "ERP", "IoT Gateway"],
            "Protocol": ["REST", "SQL", "MQTT"],
            "Latency_ms": [120, 240, 80],
            "Success_Rate_pct": [99.0, 97.5, 98.0],
            "Last_Test_UTC": ["", "", ""],
            "Status": ["Sample only", "Sample only", "Sample only"],
            "Owner": ["Operations", "IT", "Maintenance"],
        })
    if family == "math":
        return pd.DataFrame({
            "Mapping_ID": ["MAP-001", "MAP-002", "MAP-003"],
            "Source_Domain": ["Production", "Inventory", "Energy"],
            "Target_Domain": ["Quality", "Logistics", "Finance"],
            "Source_Entity": ["Good output", "On-hand stock", "Electricity use"],
            "Correspondence": ["Yield metric", "Coverage metric", "Emission metric"],
            "Dimensional_Compatible": [False, False, False],
            "Constraint_Preserved": [False, False, False],
            "Evidence_Note": ["Needs review", "Needs review", "Needs review"],
        })
    if family == "optimization":
        return pd.DataFrame({
            "Problem_Type": ["Capacity allocation", "Network planning", "Energy scheduling"],
            "Objective": ["Cost", "Service", "Carbon"],
            "Variables": [12, 24, 18],
            "Constraints": [8, 15, 11],
            "Candidate_Method": ["MILP", "LP/MILP", "LP/Robust"],
            "Solver_Status": ["Not run", "Not run", "Not run"],
            "Runtime_ms": [None, None, None],
        })
    if family == "research":
        return pd.DataFrame({
            "Scenario": ["Baseline", "Treatment A", "Treatment B", "Stress Case"],
            "Study_ID": ["STUDY-001"] * 4,
            "Sample_Size": [100, 100, 100, 100],
            "Effect_Estimate": [0.0, 0.18, 0.24, 0.07],
            "Standard_Error": [0.08, 0.09, 0.10, 0.12],
            "Confidence_Level": [0.95, 0.95, 0.95, 0.95],
            "Protocol_Status": ["Draft", "Draft", "Draft", "Draft"],
        })
    if family == "simulation":
        return pd.DataFrame({
            "Scenario": ["Baseline", "Demand Surge", "Supplier Shock", "Capacity Expansion"],
            "Demand_Units": [1000, 1250, 1000, 1100],
            "Capacity_Units": [1100, 1100, 900, 1250],
            "Lead_Time_Days": [6, 9, 12, 6],
            "Downtime_Hours": [12, 18, 24, 8],
            "Cost_SAR": [100000, 125000, 142000, 115000],
            "Service_pct": [95.0, 90.0, 82.0, 98.0],
            "Risk_Score": [10, 18, 35, 8],
        })

    if any(word in lower for word in ("six sigma", "gage", "quality", "reliability", "spc", "fmea", "capability")):
        return pd.DataFrame({
            "Part": ["P-100", "P-100", "P-200", "P-200"],
            "Workcenter": ["WC-01", "WC-01", "WC-02", "WC-02"],
            "Sample": [1, 2, 1, 2],
            "Measured_Value": [10.02, 9.98, 10.14, 9.93],
            "Lower_Spec": [9.5, 9.5, 9.5, 9.5],
            "Upper_Spec": [10.5, 10.5, 10.5, 10.5],
            "Defect_Count": [0, 0, 1, 0],
            "Inspected_Count": [100, 100, 100, 100],
        })
    if any(word in lower for word in ("maintenance", "downtime", "asset health", "predictive")):
        return pd.DataFrame({
            "Asset": ["CNC-01", "Press-02", "Packing-01", "CNC-02"],
            "Runtime_Hours": [1200, 3200, 2100, 1800],
            "Temperature_C": [65.0, 82.0, 71.0, 68.0],
            "Vibration_mm_s": [1.1, 3.8, 2.2, 1.6],
            "Downtime_Hours": [4.0, 18.0, 7.0, 5.0],
            "Failure_Count": [0, 2, 1, 0],
        })
    if any(word in lower for word in ("inventory", "meio", "replenishment", "stock", "warehouse heatmap", "slotting")):
        return pd.DataFrame({
            "SKU": ["SKU-100", "SKU-200", "SKU-300", "SKU-400"],
            "On_Hand_Units": [820, 340, 1250, 90],
            "Daily_Demand_Units": [72, 38, 95, 24],
            "Lead_Time_Days": [6, 9, 4, 12],
            "Safety_Stock_Units": [180, 150, 220, 160],
            "Unit_Cost_SAR": [18.5, 42.0, 12.0, 86.0],
        })
    if any(word in lower for word in ("fleet", "routing", "logistics", "transport", "agv", "geospatial", "network design")):
        return pd.DataFrame({
            "Task": ["T-001", "T-002", "T-003", "T-004"],
            "Origin": ["Plant", "Plant", "DC-01", "Plant"],
            "Destination": ["DC-01", "DC-02", "Customer-A", "Customer-B"],
            "Demand_Units": [120, 85, 60, 100],
            "Vehicle_Capacity": [180, 180, 90, 180],
            "Distance_km": [22.5, 34.0, 15.2, 28.7],
            "Cost_SAR_per_km": [2.4, 2.4, 2.8, 2.4],
            "CO2_kg": [8.1, 12.3, 6.2, 10.2],
        })
    if any(word in lower for word in ("facility", "layout", "factory designer", "from-to", "slp", "material handling")):
        return pd.DataFrame({
            "Department": ["Receiving", "Machining", "Assembly", "Quality", "Shipping"],
            "X_m": [2, 12, 20, 29, 38],
            "Y_m": [4, 8, 8, 5, 4],
            "Area_m2": [120, 260, 310, 140, 180],
            "FromTo_Flows_per_Day": [0, 240, 310, 190, 275],
            "Travel_Distance_m": [18, 12, 9, 14, 10],
        })
    if any(word in lower for word in ("schedule", "planning", "production planning", "dispatch", "gantt", "mrp")):
        return pd.DataFrame({
            "Work_Order": ["WO-001", "WO-002", "WO-003", "WO-004"],
            "Product": ["P-100", "P-200", "P-100", "P-300"],
            "Machine": ["M-01", "M-01", "M-02", "M-03"],
            "Quantity": [100, 160, 140, 90],
            "Processing_Min": [32, 28, 25, 40],
            "Setup_Min": [8, 12, 6, 10],
            "Due_Offset_Hours": [8, 12, 16, 20],
            "Priority": [1, 2, 1, 3],
        })
    if any(word in lower for word in ("production", "manufacturing", "lean", "shop floor", "mes", "oee")):
        return pd.DataFrame({
            "Line": ["Line-01", "Line-02", "Line-03", "Line-04"],
            "Planned_Units": [1000, 900, 1100, 850],
            "Good_Units": [948, 840, 1045, 790],
            "Downtime_Min": [38, 52, 25, 63],
            "Cycle_Time_Sec": [42.0, 45.5, 39.8, 48.0],
            "Scrap_Units": [22, 35, 18, 27],
        })
    if any(word in lower for word in ("forecast", "demand", "time series")):
        return pd.DataFrame({
            "Period": pd.date_range("2026-01-01", periods=8, freq="MS"),
            "Demand_Units": [520, 545, 560, 590, 575, 625, 650, 672],
            "Capacity_Units": [600, 600, 620, 620, 620, 650, 650, 650],
            "Lead_Time_Days": [6.3, 6.0, 6.4, 5.8, 6.1, 5.7, 5.5, 5.4],
            "Inventory_Units": [830, 790, 760, 745, 710, 680, 650, 620],
        })
    if any(word in lower for word in ("sustain", "carbon", "energy", "lca", "environment", "green ie")):
        return pd.DataFrame({
            "Activity": ["Electricity", "Diesel", "Freight", "Natural Gas"],
            "Scope": ["Scope 2", "Scope 1", "Scope 3", "Scope 1"],
            "Quantity": [12000, 2400, 15000, 3200],
            "Emission_Factor": [0.42, 2.68, 0.10, 2.02],
            "Baseline_tCO2e": [5.04, 6.43, 1.50, 6.46],
            "Scenario_tCO2e": [4.25, 5.10, 1.20, 5.80],
        })
    if any(word in lower for word in ("currency", "localization", "multi-currency", "trade rule", "customs")):
        return pd.DataFrame({
            "Item": ["Machine parts", "Industrial sensors", "Freight service", "Spare bearings"],
            "Amount": [18000.0, 7250.0, 3400.0, 5600.0],
            "Currency": ["SAR", "EUR", "USD", "SAR"],
            "Region_From": ["SA", "DE", "US", "SA"],
            "Region_To": ["SA", "SA", "SA", "SA"],
            "Customs_Document_Ready": [True, False, True, True],
        })
    if any(word in lower for word in ("economics", "finance", "capital", "investment", "npv", "benchmark")):
        return pd.DataFrame({
            "Alternative": ["Current state", "Option A", "Option B", "Option C"],
            "CapEx_SAR": [0, 180000, 240000, 125000],
            "Annual_Benefit_SAR": [0, 95000, 112000, 72000],
            "Annual_Operating_Cost_SAR": [0, 12000, 18000, 9000],
            "Project_Life_Years": [5, 5, 7, 5],
            "Risk_Score": [10, 14, 9, 12],
        })
    if any(word in lower for word in ("workforce", "human factors", "ergonomic", "labor", "time study")):
        return pd.DataFrame({
            "Task": ["Load", "Inspect", "Assemble", "Pack"],
            "Operator": ["OP-01", "OP-02", "OP-03", "OP-01"],
            "Cycle_Time_Sec": [42, 58, 75, 36],
            "Ergonomic_Risk_Score": [3, 6, 4, 2],
            "Shift_Hours": [8, 8, 8, 8],
            "Headcount": [2, 1, 3, 2],
        })
    if any(word in lower for word in ("experiment", "scenario", "monte carlo", "sensitivity")) or ("simulation" in lower and "digital twin" not in lower):
        return pd.DataFrame({
            "Scenario": ["Baseline", "Demand Surge", "Supplier Shock", "Capacity Expansion"],
            "Demand_Units": [1000, 1250, 1000, 1100],
            "Capacity_Units": [1100, 1100, 900, 1250],
            "Cost_SAR": [100000, 125000, 142000, 115000],
            "Service_pct": [95.0, 90.0, 82.0, 98.0],
            "Risk_Score": [10, 18, 35, 8],
            "Carbon_kgCO2e": [1000, 1100, 1300, 850],
        })
    if any(word in lower for word in ("research", "hypothesis", "regression", "literature", "paper", "peer review", "formal proof", "decision-readiness", "evidence degradation")):
        return pd.DataFrame({
            "Scenario": ["Baseline", "Treatment A", "Treatment B", "Stress Case"],
            "Sample_Size": [100, 100, 100, 100],
            "Effect_Estimate": [0.0, 0.18, 0.24, 0.07],
            "Standard_Error": [0.08, 0.09, 0.10, 0.12],
            "Confidence_Level": [0.95, 0.95, 0.95, 0.95],
            "Reproducible": [True, True, True, True],
        })
    if any(word in lower for word in ("digital twin", "iot", "telemetry", "connectivity", "sensor", "simulation")):
        return pd.DataFrame({
            "Asset": ["CNC-01", "CNC-02", "Press-01", "Conveyor-01"],
            "Period": [1, 2, 3, 4],
            "Temperature_C": [65.0, 68.2, 82.0, 71.5],
            "Vibration_mm_s": [1.1, 1.6, 3.8, 2.2],
            "Availability_pct": [98.5, 97.0, 91.2, 95.4],
            "Energy_kWh": [120, 128, 165, 142],
        })
    if any(word in lower for word in ("decision", "control tower", "governance", "security", "audit", "ledger", "registry", "collaboration", "workspace", "integration", "platform", "data", "gateway", "api", "webhook", "copilot", "agentic", "venture", "subscription", "persistence")):
        return pd.DataFrame({
            "Entity_ID": ["FAC-001", "MCH-001", "WO-001", "SKU-001"],
            "Entity_Type": ["Facility", "Machine", "Work Order", "SKU"],
            "Status": ["Active", "Review", "Released", "Active"],
            "Owner_Team": ["Operations", "Maintenance", "Production", "Planning"],
            "Readiness_Score": [92, 76, 88, 95],
            "Open_Issues": [0, 3, 1, 0],
        })
    return pd.DataFrame({
        "Workstream": ["Demand", "Capacity", "Service", "Inventory"],
        "Baseline": [100, 100, 95, 100],
        "Scenario": [110, 108, 97, 92],
        "Unit": ["index", "index", "%", "index"],
    })


def _evidence_bundle(module: str, df: pd.DataFrame, actor: str, research_protocol: Optional[Mapping[str, Any]] = None) -> bytes:
    result = generic_result(df)
    verification = verification_snapshot(df)
    try:
        import streamlit as st
        profile = get_module_profile(st.session_state, module, actor)
    except Exception:
        profile = default_module_profile(module)
    manifest = {
        "module": module,
        "display_name": profile.get("display_name", module),
        "project_name": profile.get("project_name", ""),
        "site_name": profile.get("site_name", ""),
        "actor": actor,
        "generated_at": _now(),
        "result": result,
        "verification": verification,
        "module_profile": profile,
    }
    if research_protocol:
        manifest["research_protocol_hash"] = research_protocol.get("protocol_hash")
        manifest["research_id"] = research_protocol.get("research_id")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("inputs.csv", df.to_csv(index=False).encode("utf-8"))
        archive.writestr("display_inputs.csv", apply_display_labels(df, profile).to_csv(index=False).encode("utf-8"))
        archive.writestr("module_profile.json", json.dumps(profile, indent=2, ensure_ascii=False, default=str).encode("utf-8"))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False, default=str).encode("utf-8"))
        archive.writestr("feature_manifest.csv", feature_catalog().to_csv(index=False).encode("utf-8"))
        if research_protocol:
            archive.writestr("research_protocol.json", json.dumps(dict(research_protocol), indent=2, ensure_ascii=False, default=str).encode("utf-8"))
    return buffer.getvalue()


def render_experience_shell(module: str, tier: str, username: str) -> None:
    """Render a restrained shared module shell around specialist engineering engines."""
    ensure_experience_db()
    import streamlit as st

    if "Experiment Lab" in str(module) or "Experimentation" in str(module):
        render_research_workspace(module, tier, username)
        return

    meta = _module_meta(module)
    profile = get_module_profile(st.session_state, module, username)
    key = _safe_key(module)
    category = str(meta.get("category", "Industrial Engineering"))
    capability_tier = str(meta.get("tier", tier))
    when = str(meta.get("when", "Prepare data, run the engineering method, inspect evidence and export the result."))

    with _db() as conn:
        studies = int(conn.execute(
            "SELECT COUNT(*) FROM experience_research_studies WHERE owner=?", (username,)
        ).fetchone()[0])
        decisions = int(conn.execute(
            "SELECT COUNT(*) FROM experience_decisions WHERE owner=?", (username,)
        ).fetchone()[0])
        jobs = int(conn.execute(
            "SELECT COUNT(*) FROM experience_jobs WHERE owner=? AND status IN ('Queued','Running')", (username,)
        ).fetchone()[0])

    active = st.session_state.get("universal_active_dataset")
    sample = active.copy(deep=True) if isinstance(active, pd.DataFrame) and not active.empty else _starter_data(module)
    result = generic_result(sample)

    st.markdown(
        """
        <style>
        .mx-hero{padding:22px 25px;border-radius:20px;background:linear-gradient(135deg,#0b1220,#172554 58%,#0f766e);color:#fff;box-shadow:0 14px 32px rgba(15,23,42,.12);border:1px solid rgba(255,255,255,.08);margin:2px 0 14px;position:relative;overflow:hidden}
        .mx-kicker{font-size:11px;font-weight:850;letter-spacing:.11em;text-transform:uppercase;color:#7dd3fc}
        .mx-title{font-size:28px;font-weight:900;letter-spacing:-.03em;margin-top:4px}
        .mx-sub{font-size:13px;color:#dbeafe;margin-top:7px;max-width:1000px}
        .mx-pill{display:inline-block;font-size:11px;margin:12px 6px 0 0;padding:5px 9px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);color:#e2e8f0}
        .mx-flow{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 14px}
        .mx-step{padding:7px 11px;border-radius:999px;border:1px solid #dbe4f0;background:#fff;font-size:11px;font-weight:800;color:#334155}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="mx-hero">
          <div class="mx-kicker">{html.escape(category)} · {html.escape(capability_tier)}</div>
          <div class="mx-title">{html.escape(str(profile.get("display_name") or module))}</div>
          <div class="mx-sub">{html.escape(when)}</div>
          <div class="mx-sub">{html.escape(" · ".join(str(x) for x in (profile.get("project_name"), profile.get("site_name"), profile.get("owner_team")) if x))}</div>
          <span class="mx-pill">Data-first</span><span class="mx-pill">Evidence-linked</span><span class="mx-pill">Human approval</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Input rows", f"{result['rows']:,}")
    c2.metric("Data readiness", f"{result['quality']:.0f}%")
    c3.metric("Saved studies", f"{studies:,}")
    c4.metric("Decisions", f"{decisions:,}")

    st.markdown(
        '<div class="mx-flow">'
        '<span class="mx-step">1 · Prepare</span>'
        '<span class="mx-step">2 · Validate</span>'
        '<span class="mx-step">3 · Analyze</span>'
        '<span class="mx-step">4 · Visualize</span>'
        '<span class="mx-step">5 · Decide</span>'
        '<span class="mx-step">6 · Export</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    action_cols = st.columns(4)
    with action_cols[0]:
        if st.button("💾 Save study", use_container_width=True, key="mx_save_" + key):
            project_title = str(profile.get("project_name") or (profile.get("display_name", module) + " Study"))
            pid = save_project(project_title, module, username, {"module": module, "display_name": profile.get("display_name", module), "tier": tier, "profile": profile})
            st.session_state["sx_project_id"] = pid
            st.success("Study saved: " + pid)
    with action_cols[1]:
        if st.button("▶ Record run", use_container_width=True, key="mx_run_" + key):
            jid = create_job(module, "interactive-analysis", username, {"module": module})
            update_job(jid, "Running", 20, "Run initialized")
            update_job(jid, "Completed", 100, "Run metadata recorded")
            st.session_state["shoir_latest_run_id"] = jid
            st.success("Run recorded: " + jid)
    with action_cols[2]:
        if st.button("📝 Decision card", use_container_width=True, key="mx_decision_" + key):
            did = create_decision(
                str(profile.get("display_name") or module) + " decision", module,
                {"rows": result["rows"], "quality": result["quality"]},
                {"Tier": tier},
                {"Uncertainty": "Module-specific; inspect source evidence"},
                username,
            )
            st.session_state["sx_decision_id_" + key] = did
            st.success("Decision created: " + did)
    with action_cols[3]:
        if st.button("📦 Evidence pack", use_container_width=True, key="mx_export_" + key):
            st.session_state["mx_show_export_" + key] = True

    if st.session_state.pop("mx_show_export_" + key, False):
        st.download_button(
            "📥 Download evidence bundle",
            data=_evidence_bundle(module, sample, username),
            file_name="shoir_ie_" + key + "_evidence.zip",
            mime="application/zip",
            use_container_width=True,
            key="mx_dl_" + key,
        )

    if jobs:
        st.caption(f"{jobs:,} active orchestration job(s) are associated with this workspace.")

    if "AI" in module or "Copilot" in module:
        with st.expander("🤖 Copilot controls", expanded=False):
            st.caption("Imported text is treated as data. State-changing operations remain approval-gated.")
            try:
                tools = pd.DataFrame(COPILOT_TOOLS, columns=["Tool","Scope","Approval"])
                st.dataframe(tools, use_container_width=True, hide_index=True)
            except Exception:
                st.info("Copilot tool registry is temporarily unavailable.")


def render_blank_module_studio(module: str, tier: str, username: str) -> None:
    import streamlit as st

    # The shared result layer uses this marker to avoid showing a duplicate
    # module playbook when this native fallback canvas already has one.
    st.session_state["shoir_native_fallback_module_active"] = module
    ensure_experience_db()
    key = _safe_key(module)
    data_key = "sx_blank_data_" + key
    active = st.session_state.get("universal_active_dataset")
    if data_key not in st.session_state:
        if isinstance(active, pd.DataFrame) and not active.empty:
            st.session_state[data_key] = active.copy(deep=True)
        else:
            st.session_state[data_key] = _starter_data(module)

    df = st.data_editor(
        st.session_state[data_key],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="sx_blank_editor_" + key,
    )
    st.session_state[data_key] = df
    profile = get_module_profile(st.session_state, module, username, valid_columns=list(df.columns))
    display_df = apply_display_labels(df, profile)
    blueprint = fallback_module_blueprint(module)
    st.caption(
        f"Working profile: {profile['display_name']}"
        + (f" · {profile['project_name']}" if profile.get("project_name") else "")
        + (f" · {profile['site_name']}" if profile.get("site_name") else "")
    )
    st.markdown(f"#### {html.escape(blueprint['focus'])}")
    st.caption(blueprint["purpose"])
    st.caption(f"Recommended first method: **{blueprint['method']}**")

    tabs = st.tabs(["📊 Overview", "🧮 Analysis", "✅ Verification", "🧠 Decision", "📤 Export"])
    with tabs[0]:
        result = generic_result(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows", "{:,}".format(result["rows"]))
        c2.metric("Columns", "{:,}".format(result["columns"]))
        c3.metric("Data quality", "{:.1f}%".format(result["quality"]))
        c4.metric("Numeric fields", "{:,}".format(result["numeric_fields"]))
        primary_kpi = profile.get("primary_kpi")
        if profile.get("target_enabled") and primary_kpi in df.columns and pd.api.types.is_numeric_dtype(df[primary_kpi]):
            target_check = evaluate_kpi_target(df[primary_kpi], profile)
            if target_check:
                precision = int(profile.get("decimal_places", 2))
                target_unit = str(target_check.get("unit") or "")
                actual_text = f"{target_check['actual']:,.{precision}f}" + (f" {target_unit}" if target_unit else "")
                goal_text = f"{target_check['target']:,.{precision}f}" + (f" {target_unit}" if target_unit else "")
                target_cols = st.columns(3)
                target_cols[0].metric(f"{display_field_label(primary_kpi, profile)} · {target_check['statistic']}", actual_text)
                target_cols[1].metric("Configured target", goal_text, delta=target_check["direction"])
                target_cols[2].metric("Target rule", "MEETS TARGET" if target_check["passed"] else "REVIEW")
                st.caption("Configured target comparison only; this is not an independently verified operational outcome.")
        with st.expander("ℹ️ Workflow, required inputs and interpretation limits", expanded=False):
            st.markdown(f"**Purpose:** {blueprint['purpose']}")
            st.markdown(f"**Recommended method:** {blueprint['method']}")
            st.markdown(f"**Useful input fields:** {blueprint['inputs']}")
            st.warning(blueprint["guardrail"])
            st.caption("When this module is seeded without an imported dataset, its sample rows are illustrative templates. They are not live plant measurements or verified outcomes.")
        numbers = [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column])]
        if numbers:
            metric = st.selectbox("Metric", numbers, format_func=lambda value: display_field_label(value, profile), key="sx_metric_" + key)
            metric_index = list(df.columns).index(metric)
            plot = display_df.iloc[:, [0, metric_index]].dropna().copy()
            if not plot.empty:
                st.plotly_chart(
                    px.bar(plot, x=plot.columns[0], y=plot.columns[1], title=profile["display_name"] + " · " + plot.columns[1]),
                    use_container_width=True,
                    config={"displayModeBar": True, "responsive": True},
                )

    with tabs[1]:
        st.markdown(f"### {html.escape(blueprint['method'])}")
        st.caption(blueprint["purpose"])
        st.caption(f"Inputs to verify: {blueprint['inputs']}")
        domain_result_key = "sx_domain_analysis_" + key
        input_signature = hashlib.sha256(
            df.to_json(orient="split", date_format="iso", default_handler=str).encode("utf-8")
        ).hexdigest()
        if st.button(
            "▶ Run module-specific review",
            type="primary",
            use_container_width=True,
            key="sx_domain_run_" + key,
        ):
            run_started_ns = time.perf_counter_ns()
            try:
                analysis = analyze_fallback_module(module, df)
                elapsed_ms = max(0.0, (time.perf_counter_ns() - run_started_ns) / 1_000_000.0)
                run_record = None
                try:
                    run_record = save_module_analysis_run(
                        module, username, profile, df, analysis,
                        duration_ms=elapsed_ms, status="Completed",
                    )
                except Exception as persist_exc:
                    st.warning(
                        "Analysis completed, but the run history could not be updated: "
                        f"{type(persist_exc).__name__}: {persist_exc}"
                    )
                st.session_state[domain_result_key] = {
                    "input_signature": input_signature,
                    "analysis": analysis,
                    "run_id": run_record.get("run_id") if run_record else None,
                    "input_hash": run_record.get("input_hash") if run_record else None,
                    "snapshot_status": run_record.get("snapshot_status") if run_record else "Not saved",
                }
                if run_record:
                    st.success(f"Analysis completed and saved as {run_record['run_id']}.")
                    if run_record["snapshot_status"] != "Complete":
                        st.info(run_record["snapshot_status"] + ". Run metadata and input hash were retained.")
                else:
                    st.success("Module-specific calculation completed in this session.")
            except (TypeError, ValueError, KeyError, ZeroDivisionError) as exc:
                st.session_state.pop(domain_result_key, None)
                st.warning(f"The current table is not ready for this method: {exc}")
            except Exception as exc:
                st.session_state.pop(domain_result_key, None)
                st.error(f"Module analysis stopped safely: {type(exc).__name__}: {exc}")

        saved_domain_result = st.session_state.get(domain_result_key)
        if isinstance(saved_domain_result, dict):
            if saved_domain_result.get("input_signature") != input_signature:
                st.info("Inputs have changed since the last module-specific review. Run the review again before using its previous results.")
            else:
                analysis = saved_domain_result.get("analysis", {})
                analyzed_df = analysis.get("result", pd.DataFrame())
                analysis_metrics = analysis.get("metrics", {})
                if analysis_metrics:
                    metric_items = list(analysis_metrics.items())
                    metric_cols = st.columns(min(4, len(metric_items)))
                    for metric_index, (metric_name, metric_value) in enumerate(metric_items):
                        if metric_value is None:
                            display_value = "N/A"
                        elif isinstance(metric_value, (float, np.floating)):
                            display_value = f"{float(metric_value):,.2f}"
                        elif isinstance(metric_value, (int, np.integer)):
                            display_value = f"{int(metric_value):,}"
                        else:
                            display_value = str(metric_value)
                        metric_cols[metric_index % len(metric_cols)].metric(str(metric_name), display_value)
                if isinstance(analyzed_df, pd.DataFrame) and not analyzed_df.empty:
                    st.dataframe(apply_display_labels(analyzed_df, profile), use_container_width=True, hide_index=True)
                    x_column = analysis.get("chart_x")
                    y_column = analysis.get("chart_y")
                    numeric_columns = [
                        str(column) for column in analyzed_df.columns
                        if pd.api.types.is_numeric_dtype(analyzed_df[column])
                    ]
                    if not y_column or y_column not in analyzed_df.columns or not pd.api.types.is_numeric_dtype(analyzed_df[y_column]):
                        y_column = numeric_columns[-1] if numeric_columns else None
                    chart, actual_chart, chart_notice = build_profiled_module_figure(
                        analyzed_df, x_column, y_column, profile,
                        f"{profile['display_name']} · {display_field_label(y_column, profile) if y_column else 'Analysis'}",
                    )
                    if chart_notice:
                        st.info(chart_notice)
                    if chart is not None:
                        st.caption(f"Visualization: {actual_chart} · configured for this module profile.")
                        st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": True, "responsive": True})
                    if saved_domain_result.get("run_id"):
                        st.caption(
                            f"Saved run: {saved_domain_result['run_id']} · Input SHA-256: {saved_domain_result.get('input_hash', 'unavailable')}"
                        )
                st.warning(analysis.get("guardrail", blueprint["guardrail"]))
                st.caption("Outputs are calculated from the selected table and current assumptions. Save and independently verify any operational decision before implementation.")

        numbers = [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column])]
        if len(numbers) >= 2:
            baseline = st.selectbox(
                profile["baseline_label"] + " KPI",
                numbers,
                format_func=lambda value: display_field_label(value, profile),
                key="sx_base_" + key,
            )
            scenario = st.selectbox(
                profile["scenario_label"] + " KPI",
                numbers,
                index=1,
                format_func=lambda value: display_field_label(value, profile),
                key="sx_scenario_" + key,
            )
            delta_column = profile["scenario_label"] + " − " + profile["baseline_label"]
            pct_column = profile["scenario_label"] + " vs " + profile["baseline_label"] + " (%)"
            if st.button("▶ Run Analysis", type="primary", use_container_width=True, key="sx_run_" + key):
                started = time.perf_counter_ns()
                output = df.copy()
                base_values = pd.to_numeric(output[baseline], errors="coerce")
                scenario_values = pd.to_numeric(output[scenario], errors="coerce")
                output[delta_column] = scenario_values - base_values
                output[pct_column] = output[delta_column] / base_values.replace(0, np.nan) * 100.0
                st.session_state["sx_result_" + key] = output
                st.session_state["sx_run_id_" + key] = benchmark_duration(module, started, username, len(output), "generic_analysis")
            output = st.session_state.get("sx_result_" + key, pd.DataFrame())
            if isinstance(output, pd.DataFrame) and not output.empty:
                st.dataframe(output, use_container_width=True, hide_index=True)
                output_display = apply_display_labels(output, profile)
                st.plotly_chart(
                    px.bar(output_display, x=output_display.columns[0], y=pct_column, title=profile["scenario_label"] + " vs " + profile["baseline_label"] + " (%)"),
                    use_container_width=True,
                    config={"displayModeBar": True, "responsive": True},
                )

    with tabs[2]:
        output = st.session_state.get("sx_result_" + key, df)
        check = verification_snapshot(output)
        v1, v2, v3 = st.columns(3)
        v1.metric("Verification score", "{:.1f}%".format(check["score"]))
        v2.metric("Checks passed", "{}/{}".format(check["passed"], check["total"]))
        v3.metric("Run status", "PASS" if check["score"] >= 100 else "REVIEW")
        verification_table = pd.DataFrame(
            [
                {"Check": name.replace("_", " ").title(), "Status": "✓" if ok else "⚠", "Detail": str(ok)}
                for name, ok in check["checks"].items()
            ]
        )
        st.dataframe(verification_table, use_container_width=True, hide_index=True)

    with tabs[3]:
        if st.button("📝 Create decision from current study", type="primary", use_container_width=True, key="sx_decision_blank_" + key):
            result = generic_result(df)
            did = create_decision(
                str(profile.get("display_name") or module) + " working decision",
                module,
                {"quality": result["quality"], "rows": result["rows"]},
                {"tier": tier},
                {"verification": verification_snapshot(df)},
                username,
            )
            st.session_state["sx_decision_id_" + key] = did
            st.success("Decision created: " + did)
        did = st.session_state.get("sx_decision_id_" + key)
        if did:
            with _db() as conn:
                row = conn.execute(
                    "SELECT decision_id,title,status,owner,created_at FROM experience_decisions WHERE decision_id=?",
                    (did,),
                ).fetchone()
            if row:
                st.dataframe(
                    pd.DataFrame([dict(zip(["ID", "Title", "Status", "Owner", "Created"], row))]),
                    use_container_width=True,
                    hide_index=True,
                )
                if st.button("➡️ Move to Validated", use_container_width=True, key="sx_validate_" + key):
                    transition_decision(did, username, "Validated", "Validation evidence captured from module canvas.")
                    st.success("Decision moved to Validated.")
            with st.expander("📈 Decision-to-Value Verification", expanded=False):
                st.caption("Record what the decision predicted, what actually happened, and the resulting variance. This evidence remains separate from the approval status until a human verifies it.")
                predicted_text = st.text_area("Predicted KPIs (JSON)", value='{"Throughput": 100, "Cost": 5000}', key="sx_predicted_json_" + key, height=110)
                actual_text = st.text_area("Actual KPIs (JSON)", value='{"Throughput": 0, "Cost": 0}', key="sx_actual_json_" + key, height=110)
                outcome_status = st.selectbox("Implementation status", ["Planned", "Implemented", "Verified"], key="sx_outcome_status_" + key)
                lesson = st.text_area("Lesson / explanation", key="sx_outcome_lesson_" + key, height=90)
                if st.button("🧾 Record actual outcome", use_container_width=True, key="sx_record_outcome_" + key):
                    try:
                        predicted = json.loads(predicted_text)
                        actual = json.loads(actual_text)
                        if not isinstance(predicted, dict) or not isinstance(actual, dict):
                            raise ValueError("Predicted and actual KPI payloads must be JSON objects.")
                        active_workspace = str(
                            st.session_state.get("shoir_workspace_name")
                            or st.session_state.get("workspace")
                            or st.session_state.get("active_workspace_name")
                            or "default"
                        )
                        outcome_id = record_decision_outcome(
                            did, username, outcome_status, predicted, actual, lesson.strip(),
                            workspace=active_workspace,
                        )
                        st.session_state["sx_last_outcome_id_" + key] = outcome_id
                        st.success("Outcome recorded: " + outcome_id)
                    except Exception as exc:
                        st.error("Outcome could not be recorded: " + str(exc))

                outcome_df = decision_outcomes_frame(decision_id=did, owner=username)
                st.session_state["decision_outcomes_df"] = outcome_df
                if not outcome_df.empty:
                    latest = outcome_df.iloc[0]
                    try:
                        variance_records = json.loads(latest["variance_json"] or "[]")
                        variance_df = pd.DataFrame(variance_records)
                    except Exception:
                        variance_df = pd.DataFrame()
                    if not variance_df.empty:
                        st.dataframe(variance_df, use_container_width=True, hide_index=True)
                        try:
                            from shoir_live_visuals import build_visualization_suite
                            suite = build_visualization_suite(variance_df, context="Decision-to-Value", max_figures=3)
                            for title, fig in suite:
                                st.plotly_chart(fig, use_container_width=True)
                        except Exception:
                            pass
                    st.dataframe(outcome_df[["outcome_id","implementation_status","lesson","verified_at","created_at"]].head(20), use_container_width=True, hide_index=True)

    with tabs[4]:
        st.download_button(
            "📥 Download Module Evidence Bundle",
            data=_evidence_bundle(module, df, username),
            file_name="shoir_ie_" + key + "_bundle.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
            key="sx_export_download_" + key,
        )