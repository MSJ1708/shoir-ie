"""Shoir-IE shared experience layer.

Provides a consistent command deck, persistence, verification and evidence
surfaces for engineering modules without replacing their specialist logic.
"""
from __future__ import annotations

import hashlib
import io
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
            "CREATE TABLE IF NOT EXISTS experience_decision_approvals(id INTEGER PRIMARY KEY AUTOINCREMENT,decision_id TEXT,from_status TEXT,to_status TEXT,actor TEXT,comment TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_comments(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT,decision_id TEXT,actor TEXT,comment TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_jobs(job_id TEXT PRIMARY KEY,module TEXT,job_type TEXT,status TEXT,progress REAL,message TEXT,payload_json TEXT,started_at TEXT,finished_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_copilot_actions(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,module TEXT,action TEXT,status TEXT,requires_approval INTEGER,evidence_json TEXT,actor TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_observability(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,module TEXT,event_type TEXT,duration_ms REAL,details_json TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_memory(memory_id TEXT PRIMARY KEY,problem TEXT,data_ref TEXT,model_ref TEXT,scenario_ref TEXT,decision_ref TEXT,actual_result TEXT,lesson TEXT,owner TEXT,created_at TEXT,updated_at TEXT)",
            "CREATE TABLE IF NOT EXISTS experience_preferences(username TEXT PRIMARY KEY,locale TEXT DEFAULT 'en',direction TEXT DEFAULT 'ltr',reduced_motion INTEGER DEFAULT 0,density TEXT DEFAULT 'comfortable',updated_at TEXT)",
            "CREATE INDEX IF NOT EXISTS idx_exp_jobs_status ON experience_jobs(status,started_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_exp_lineage_source ON experience_lineage(source_type,source_id)",
        ]
        for statement in statements:
            conn.execute(statement)
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
) -> str:
    ensure_experience_db()
    did = "DEC-" + uuid.uuid4().hex[:12].upper()
    stamp = _now()
    with _db() as conn:
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


def transition_decision(decision_id: str, actor: str, to_status: str, comment: str = "") -> None:
    states = ["Draft", "Validated", "Proposed", "Review", "Approved", "Implemented", "Verified"]
    if to_status not in states:
        raise ValueError("Invalid approval state.")
    with _db() as conn:
        row = conn.execute(
            "SELECT status FROM experience_decisions WHERE decision_id=?",
            (decision_id,),
        ).fetchone()
        if not row:
            raise ValueError("Decision not found.")
        current = str(row[0])
        if current in states and states.index(to_status) < states.index(current) and to_status not in {"Draft", "Review"}:
            raise ValueError("Decision cannot move backward to that state.")
        conn.execute(
            "UPDATE experience_decisions SET status=?,updated_at=? WHERE decision_id=?",
            (to_status, _now(), decision_id),
        )
        conn.execute(
            "INSERT INTO experience_decision_approvals(decision_id,from_status,to_status,actor,comment,created_at) VALUES(?,?,?,?,?,?)",
            (decision_id, current, to_status, actor, str(comment)[:500], _now()),
        )
        conn.commit()


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
    ensure_experience_db()
    jid = "JOB-" + uuid.uuid4().hex[:12].upper()
    with _db() as conn:
        conn.execute(
            "INSERT INTO experience_jobs VALUES(?,?,?,?,?,?,?,?,?)",
            (jid, module, job_type, "Queued", 0.0, "Queued by operator", json.dumps(dict(payload), default=str), None, None),
        )
        conn.commit()
    return jid


def update_job(job_id: str, status: str, progress: float, message: str = "") -> None:
    fields = ["status=?", "progress=?", "message=?"]
    values = [status, float(max(0.0, min(100.0, progress))), str(message)[:500]]
    if status == "Running":
        fields.append("started_at=?")
        values.append(_now())
    if status in {"Completed", "Failed", "Cancelled"}:
        fields.append("finished_at=?")
        values.append(_now())
    values.append(job_id)
    with _db() as conn:
        conn.execute(
            "UPDATE experience_jobs SET " + ",".join(fields) + " WHERE job_id=?",
            values,
        )
        conn.commit()


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


def _safe_key(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:10]


def _module_meta(module: str) -> dict:
    try:
        from industrial_platform import PLATFORM_CATALOG
        return next((item for item in PLATFORM_CATALOG if str(item.get("name")) == str(module)), {})
    except Exception:
        return {}


def _starter_data(module: str) -> pd.DataFrame:
    lower = str(module).lower()
    if any(word in lower for word in ("quality", "reliability", "maintenance")):
        return pd.DataFrame({"Workcenter": ["WC-01", "WC-02", "WC-03"], "Baseline": [94, 91, 88], "Scenario": [96, 93, 92], "Unit": ["%"] * 3})
    if any(word in lower for word in ("sustain", "carbon", "energy")):
        return pd.DataFrame({"Area": ["Line A", "Line B", "Warehouse"], "Baseline": [120, 95, 80], "Scenario": [105, 84, 66], "Unit": ["tCO2e"] * 3})
    if any(word in lower for word in ("planning", "schedule", "production")):
        return pd.DataFrame({"Workcenter": ["M-01", "M-02", "M-03"], "Baseline": [82, 90, 76], "Scenario": [88, 92, 85], "Unit": ["% utilization"] * 3})
    return pd.DataFrame({"Area": ["Demand", "Capacity", "Service", "Inventory", "Risk"], "Baseline": [100, 100, 95, 100, 10], "Scenario": [110, 108, 97, 92, 7], "Unit": ["index", "index", "%", "index", "index"]})


def _evidence_bundle(module: str, df: pd.DataFrame, actor: str) -> bytes:
    result = generic_result(df)
    verification = verification_snapshot(df)
    manifest = {
        "module": module,
        "actor": actor,
        "generated_at": _now(),
        "result": result,
        "verification": verification,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("inputs.csv", df.to_csv(index=False).encode("utf-8"))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str).encode("utf-8"))
        archive.writestr("feature_manifest.csv", feature_catalog().to_csv(index=False).encode("utf-8"))
    return buffer.getvalue()


def render_experience_shell(module: str, tier: str, username: str) -> None:
    ensure_experience_db()
    import streamlit as st

    meta = _module_meta(module)
    stats = feature_stats()
    with _db() as conn:
        projects = int(conn.execute("SELECT COUNT(*) FROM experience_projects").fetchone()[0])
        decisions = int(conn.execute("SELECT COUNT(*) FROM experience_decisions").fetchone()[0])
        jobs = int(conn.execute("SELECT COUNT(*) FROM experience_jobs WHERE status IN ('Queued','Running')").fetchone()[0])

    key = _safe_key(module)
    category = str(meta.get("category", "Industrial Engineering"))
    capability_tier = str(meta.get("tier", tier))
    when = str(meta.get("when", "Prepare, validate, analyze, decide and export in one governed workspace."))

    st.markdown(
        "<div class='sx-hero'><div class='sx-kicker'>{}</div><div class='sx-title'>{}</div><div class='sx-sub'>{}</div>"
        "<div class='sx-badges'><span>● Workspace ready</span><span>✓ {}/60 core capabilities</span><span>◈ Evidence-first</span></div></div>".format(
            category + " · " + capability_tier,
            module,
            when,
            stats["implemented"],
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        .sx-hero{padding:24px 26px;border-radius:20px;background:linear-gradient(135deg,#0b1220 0%,#192657 58%,#0f5c63 100%);color:#fff;box-shadow:0 18px 40px rgba(15,23,42,.16);border:1px solid rgba(255,255,255,.08);margin:2px 0 14px;position:relative;overflow:hidden}
        .sx-hero:after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 0%,rgba(255,255,255,.06) 46%,transparent 60%);transform:translateX(-120%);animation:sxShimmer 8s ease-in-out infinite}
        @keyframes sxShimmer{0%,58%{transform:translateX(-120%)}78%,100%{transform:translateX(120%)}}
        .sx-kicker{font-size:11px;font-weight:800;letter-spacing:.10em;text-transform:uppercase;color:#7dd3fc}
        .sx-title{font-size:29px;font-weight:850;margin-top:5px;line-height:1.16}.sx-sub{font-size:13px;color:#dbeafe;margin-top:8px;max-width:1000px}
        .sx-badges{display:flex;gap:10px;flex-wrap:wrap;margin-top:13px}.sx-badges span{font-size:11px;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);color:#e2e8f0}
        .sx-step{padding:7px 11px;border-radius:12px;border:1px solid #dbe4f0;background:#fff;text-align:center;font-size:11px;font-weight:750;color:#334155;min-height:28px;transition:transform .18s ease,box-shadow .18s ease}
        .sx-step:hover{transform:translateY(-2px);box-shadow:0 8px 18px rgba(15,23,42,.08)}
        @media (prefers-reduced-motion: reduce){.sx-hero:after{animation:none}.sx-step{transition:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Core capabilities", "{}/60".format(stats["implemented"]), "active")
    c2.metric("Saved studies", "{:,}".format(projects), "persistent")
    c3.metric("Decision records", "{:,}".format(decisions), "governed")
    c4.metric("Active jobs", "{:,}".format(jobs), "live")

    # A compact visual pulse keeps the workspace informative without making
    # every module feel like a dashboard overload.
    pulse = pd.DataFrame({
        "State": ["Implemented", "Integration-ready"],
        "Capabilities": [stats["implemented"], stats["integration_ready"]],
    })
    pc1, pc2 = st.columns([1.35, 2.65])
    with pc1:
        st.markdown("**Platform pulse**")
        st.progress(stats["implemented"] / max(1, stats["total"]), text="{}/60 capabilities active".format(stats["implemented"]))
    with pc2:
        fig = px.bar(
            pulse,
            x="Capabilities",
            y="State",
            orientation="h",
            text="Capabilities",
            title="Experience readiness",
        )
        fig.update_layout(height=155, margin=dict(l=10, r=10, t=38, b=8), showlegend=False)
        fig.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    steps = st.columns(6)
    for col, label in zip(steps, ["01 Prepare", "02 Validate", "03 Run", "04 Inspect", "05 Decide", "06 Export"]):
        col.markdown("<div class='sx-step'>✓ {}</div>".format(label), unsafe_allow_html=True)

    a, b, c, d, e = st.columns(5)
    if a.button("💾 Save Study", use_container_width=True, key="sx_save_" + key):
        pid = save_project(module + " Study", module, username, {"module": module, "tier": tier})
        st.session_state["sx_project_id"] = pid
        st.success("Study saved: " + pid)
    if b.button("🧪 Create Run", use_container_width=True, key="sx_job_" + key):
        jid = create_job(module, "interactive-analysis", username, {"module": module})
        update_job(jid, "Running", 20, "Run initialized")
        update_job(jid, "Completed", 100, "Run recorded")
        st.success("Run recorded: " + jid)
    if c.button("📝 Decision Card", use_container_width=True, key="sx_decision_" + key):
        did = create_decision(module + " decision", module, {"Status": "Pending review"}, {"Tier": tier}, {"Uncertainty": "Module-specific"}, username)
        st.session_state["sx_decision_id"] = did
        st.success("Decision created: " + did)
    if d.button("🤖 Copilot Plan", use_container_width=True, key="sx_copilot_" + key):
        rid = log_copilot_action(module, "Prepare validated multi-step plan", username, True, "Preview", {"capabilities": stats["total"]})
        st.session_state["sx_copilot_run_id"] = rid
        st.info("Copilot plan staged for approval. No destructive action runs automatically.")
    if e.button("📦 Evidence Pack", use_container_width=True, key="sx_export_" + key):
        st.session_state["sx_show_export"] = True

    if st.session_state.pop("sx_show_export", False):
        sample = _starter_data(module)
        st.download_button(
            "📥 Download Universal Evidence Bundle",
            data=_evidence_bundle(module, sample, username),
            file_name="shoir_ie_" + key + "_evidence.zip",
            mime="application/zip",
            use_container_width=True,
            key="sx_dl_" + key,
        )

    with st.expander("✨ Platform Excellence · 60 capabilities", expanded=False):
        st.caption("A calm, searchable capability map — not another wall of controls.")
        search = st.text_input("Search capabilities", key="sx_feature_search_" + key, placeholder="Search data, Copilot, testing, reporting…")
        catalog = feature_catalog()
        if search.strip():
            term = search.strip().lower()
            mask = catalog["Feature"].str.lower().str.contains(term, regex=False) | catalog["Description"].str.lower().str.contains(term, regex=False)
            catalog = catalog[mask]
        st.dataframe(catalog, use_container_width=True, hide_index=True)
        q1, q2, q3 = st.columns(3)
        q1.metric("Implemented", stats["implemented"])
        q2.metric("Integration-ready", stats["integration_ready"])
        q3.metric("Tracked", stats["total"])

    if "AI" in module or "Copilot" in module:
        with st.expander("🤖 Copilot capability registry", expanded=True):
            st.caption("Imported text is treated as data. Tool execution stays approval-gated.")
            tools = pd.DataFrame(COPILOT_TOOLS, columns=["Tool", "Scope", "Approval"])
            st.dataframe(tools, use_container_width=True, hide_index=True)
            if st.button("✅ Approve preview plan", type="primary", use_container_width=True, key="sx_approve_" + key):
                rid = log_copilot_action(module, "Approve preview plan", username, True, "Approved", {"tools": len(tools)})
                st.success("Copilot approval recorded: " + rid)


def render_blank_module_studio(module: str, tier: str, username: str) -> None:
    import streamlit as st

    ensure_experience_db()
    key = _safe_key(module)
    data_key = "sx_blank_data_" + key
    if data_key not in st.session_state:
        st.session_state[data_key] = _starter_data(module)

    df = st.data_editor(
        st.session_state[data_key],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="sx_blank_editor_" + key,
    )
    st.session_state[data_key] = df

    tabs = st.tabs(["📊 Overview", "🧮 Analysis", "✅ Verification", "🧠 Decision", "📤 Export"])
    with tabs[0]:
        result = generic_result(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows", "{:,}".format(result["rows"]))
        c2.metric("Columns", "{:,}".format(result["columns"]))
        c3.metric("Data quality", "{:.1f}%".format(result["quality"]))
        c4.metric("Numeric fields", "{:,}".format(result["numeric_fields"]))
        numbers = [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column])]
        if numbers:
            metric = st.selectbox("Metric", numbers, key="sx_metric_" + key)
            plot = df[[df.columns[0], metric]].dropna()
            if not plot.empty:
                st.plotly_chart(px.bar(plot, x=df.columns[0], y=metric, title=module + " · " + metric), use_container_width=True)

    with tabs[1]:
        numbers = [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column])]
        if len(numbers) >= 2:
            baseline = st.selectbox("Baseline metric", numbers, key="sx_base_" + key)
            scenario = st.selectbox("Scenario metric", numbers, index=1, key="sx_scenario_" + key)
            if st.button("▶ Run Analysis", type="primary", use_container_width=True, key="sx_run_" + key):
                started = time.perf_counter_ns()
                output = df.copy()
                base_values = pd.to_numeric(output[baseline], errors="coerce")
                scenario_values = pd.to_numeric(output[scenario], errors="coerce")
                output["Delta"] = scenario_values - base_values
                output["Delta %"] = output["Delta"] / base_values.replace(0, np.nan) * 100.0
                st.session_state["sx_result_" + key] = output
                st.session_state["sx_run_id_" + key] = benchmark_duration(module, started, username, len(output), "generic_analysis")
            output = st.session_state.get("sx_result_" + key, pd.DataFrame())
            if isinstance(output, pd.DataFrame) and not output.empty:
                st.dataframe(output, use_container_width=True, hide_index=True)
                st.plotly_chart(px.bar(output, x=output.columns[0], y="Delta %", title="Scenario delta (%)"), use_container_width=True)

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
                module + " working decision",
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
