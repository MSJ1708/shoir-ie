"""Shoir-IE unified industrial product experience.

A cross-cutting product layer that makes the existing engineering engines feel
like one cohesive operating system: studies, data readiness, scenarios,
decisions, implementation, memory, health, reporting, command palette and
showcase presentation.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import sqlite3
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd
import plotly.express as px

from industrial_experience import (
    create_decision,
    ensure_experience_db,
    feature_stats,
    register_lineage,
    transition_decision,
)


COMMAND_ACTIONS = [
    "Open Unified Study Center",
    "Open Universal Industrial Engine",
    "Check Data Readiness",
    "Create Decision Card",
    "Open Implementation Tracker",
    "Open Industrial Memory",
    "Open Platform Health",
    "Showcase Mode",
    "Export Evidence Pack",
]

WORKFLOW_STEPS = [
    ("01", "Prepare", "Frame the problem and load the right data."),
    ("02", "Validate", "Check schema, quality, units and assumptions."),
    ("03", "Run", "Execute optimization, simulation, forecast or analysis."),
    ("04", "Inspect", "Compare scenarios and understand drivers."),
    ("05", "Decide", "Create a governed decision with evidence."),
    ("06", "Implement", "Assign actions and track actual results."),
    ("07", "Learn", "Capture what happened and reuse the knowledge."),
]

STARTER_SCENARIOS = [
    {"Scenario": "Baseline", "Cost": 100.0, "Service": 95.0, "Carbon": 100.0, "Risk": 10.0, "Capacity": 90.0},
    {"Scenario": "Scenario A", "Cost": 94.0, "Service": 97.0, "Carbon": 92.0, "Risk": 9.0, "Capacity": 94.0},
    {"Scenario": "Scenario B", "Cost": 88.0, "Service": 96.0, "Carbon": 86.0, "Risk": 12.0, "Capacity": 98.0},
]

DOMAIN_RECOMMENDATIONS = {
    "warehouse": ["Run slotting / layout analysis", "Compare travel distance and throughput", "Validate capacity and service constraints"],
    "supply": ["Run network / routing optimization", "Stress-test demand and lead-time", "Capture service-versus-cost trade-offs"],
    "quality": ["Check SPC / capability readiness", "Investigate Pareto drivers", "Create a corrective-action decision"],
    "maintenance": ["Validate telemetry", "Review failure-risk drivers", "Convert the maintenance result into a planned action"],
    "sustain": ["Check Scope 1/2/3 data", "Compare carbon and operating-cost scenarios", "Document assumptions and emission factors"],
    "simulation": ["Validate inputs and distributions", "Compare replications with confidence intervals", "Record the model and scenario evidence"],
    "planning": ["Validate demand and capacity", "Compare finite-capacity scenarios", "Track the implementation KPI after release"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db(path: str = "enterprise_full_workspace.db"):
    return sqlite3.connect(path, timeout=30)


def _key(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:10]


def ensure_unified_db(path: str = "enterprise_full_workspace.db") -> None:
    ensure_experience_db(path)
    with _db(path) as conn:
        for statement in [
            "CREATE TABLE IF NOT EXISTS unified_implementation_actions(action_id TEXT PRIMARY KEY,study_id TEXT,action TEXT,owner TEXT,due_date TEXT,status TEXT,kpi TEXT,baseline REAL,target REAL,actual REAL,notes TEXT,created_at TEXT,updated_at TEXT)",
            "CREATE TABLE IF NOT EXISTS unified_scenario_values(id INTEGER PRIMARY KEY AUTOINCREMENT,study_id TEXT,scenario TEXT,metric TEXT,value REAL,unit TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS unified_dataset_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,study_id TEXT,source_name TEXT,rows INTEGER,columns INTEGER,quality REAL,readiness_json TEXT,created_at TEXT)",
            "CREATE TABLE IF NOT EXISTS unified_module_state(module TEXT PRIMARY KEY,last_opened TEXT,readiness REAL,study_id TEXT,updated_at TEXT)",
        ]:
            conn.execute(statement)
        conn.commit()


def _starter_for_module(module: str) -> pd.DataFrame:
    lower = str(module).lower()
    if any(x in lower for x in ("quality", "reliability")):
        return pd.DataFrame({"Process": ["Line A", "Line B", "Line C", "Line D"], "Baseline": [94, 91, 88, 96], "Scenario": [96, 93, 92, 97], "Unit": ["%"] * 4})
    if any(x in lower for x in ("maintenance", "asset")):
        return pd.DataFrame({"Asset": ["CNC-01", "Press-02", "Robot-03", "Pump-04"], "Baseline": [82, 75, 91, 68], "Scenario": [90, 83, 95, 79], "Unit": ["health index"] * 4})
    if any(x in lower for x in ("carbon", "sustain", "energy")):
        return pd.DataFrame({"Area": ["Line A", "Line B", "Warehouse", "Fleet"], "Baseline": [120, 95, 80, 110], "Scenario": [105, 84, 66, 92], "Unit": ["tCO2e"] * 4})
    if any(x in lower for x in ("warehouse", "facility", "layout")):
        return pd.DataFrame({"Area": ["Receiving", "Storage", "Pick", "Pack"], "Baseline": [100, 82, 94, 88], "Scenario": [94, 91, 101, 97], "Unit": ["index"] * 4})
    return pd.DataFrame({"Area": ["Demand", "Capacity", "Service", "Inventory", "Risk"], "Baseline": [100, 100, 95, 100, 10], "Scenario": [108, 110, 97, 92, 8], "Unit": ["index", "index", "%", "index", "index"]})


def assess_data_readiness(df: pd.DataFrame, required: Optional[Sequence[str]] = None) -> dict:
    required = list(required or [])
    if not isinstance(df, pd.DataFrame):
        return {"score": 0.0, "checks": [{"name": "Table present", "status": False, "detail": "No table is available."}]}

    checks: list[dict[str, Any]] = []
    checks.append({"name": "Rows available", "status": len(df) > 0, "detail": f"{len(df):,} row(s) loaded."})
    checks.append({"name": "Unique column names", "status": not df.columns.duplicated().any(), "detail": "Column names are unique." if not df.columns.duplicated().any() else "Duplicate column names detected."})
    missing_required = [c for c in required if c not in df.columns]
    checks.append({"name": "Required columns", "status": not missing_required, "detail": "All required columns found." if not missing_required else "Missing: " + ", ".join(missing_required[:8])})
    missing_pct = float(df.isna().mean().mean() * 100) if len(df.columns) else 100.0
    checks.append({"name": "Missingness", "status": missing_pct <= 5.0, "detail": f"{missing_pct:.1f}% missing values."})
    duplicate_pct = float(df.duplicated().mean() * 100) if len(df) else 0.0
    checks.append({"name": "Duplicate rows", "status": duplicate_pct <= 2.0, "detail": f"{duplicate_pct:.1f}% duplicate rows."})
    numeric = df.select_dtypes(include=np.number)
    finite = bool(np.isfinite(numeric.to_numpy(dtype=float)).all()) if not numeric.empty else True
    checks.append({"name": "Finite numeric values", "status": finite, "detail": "Numeric values are finite." if finite else "NaN/Inf values require attention."})
    negative_count = int((numeric < 0).sum().sum()) if not numeric.empty else 0
    checks.append({"name": "Negative values", "status": negative_count == 0, "detail": f"{negative_count:,} negative numeric value(s)."})
    outliers = 0
    for col in numeric.columns:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) >= 8:
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                outliers += int(((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).sum())
    checks.append({"name": "Outlier scan", "status": outliers == 0, "detail": f"{outliers:,} potential outlier value(s) flagged."})
    passed = sum(bool(c["status"]) for c in checks)
    return {"score": round(100.0 * passed / max(1, len(checks)), 1), "checks": checks, "passed": passed, "total": len(checks)}


def scenario_metrics(df: pd.DataFrame) -> dict:
    if df.empty or "Scenario" not in df.columns:
        return {"rows": int(len(df))}
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    return {"scenarios": int(df["Scenario"].nunique()), "metrics": len(numeric), "baseline": str(df.iloc[0]["Scenario"])}


def save_scenario_table(study_id: str, df: pd.DataFrame) -> None:
    ensure_unified_db()
    if df.empty or "Scenario" not in df.columns:
        return
    with _db() as conn:
        conn.execute("DELETE FROM unified_scenario_values WHERE study_id=?", (study_id,))
        for rec in df.to_dict("records"):
            scenario = str(rec.get("Scenario", ""))
            for metric, value in rec.items():
                if metric == "Scenario":
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                conn.execute(
                    "INSERT INTO unified_scenario_values(study_id,scenario,metric,value,unit,created_at) VALUES(?,?,?,?,?,?)",
                    (study_id, scenario, metric, numeric, "", _now()),
                )
        conn.commit()


def load_scenario_table(study_id: str) -> pd.DataFrame:
    ensure_unified_db()
    with _db() as conn:
        data = pd.read_sql(
            "SELECT scenario AS Scenario, metric, value FROM unified_scenario_values WHERE study_id=? ORDER BY scenario,metric",
            conn,
            params=(study_id,),
        )
    if data.empty:
        return pd.DataFrame(STARTER_SCENARIOS)
    wide = data.pivot_table(index="Scenario", columns="metric", values="value", aggfunc="first").reset_index()
    return wide


def create_unified_study(title: str, module: str, owner: str, objective: str) -> str:
    ensure_unified_db()
    from industrial_experience import save_project
    return save_project(title, module, owner, {"objective": objective, "workflow": [x[1] for x in WORKFLOW_STEPS]})


def _implementation_df(study_id: Optional[str]) -> pd.DataFrame:
    ensure_unified_db()
    if not study_id:
        return pd.DataFrame(columns=["Action", "Owner", "Due", "Status", "KPI", "Baseline", "Target", "Actual", "Notes"])
    with _db() as conn:
        df = pd.read_sql(
            "SELECT action AS Action, owner AS Owner, due_date AS Due, status AS Status, kpi AS KPI, baseline AS Baseline, target AS Target, actual AS Actual, notes AS Notes, action_id FROM unified_implementation_actions WHERE study_id=? ORDER BY due_date",
            conn,
            params=(study_id,),
        )
    return df


def _save_implementation(study_id: str, df: pd.DataFrame) -> None:
    ensure_unified_db()
    with _db() as conn:
        conn.execute("DELETE FROM unified_implementation_actions WHERE study_id=?", (study_id,))
        for rec in df.fillna("").to_dict("records"):
            conn.execute(
                "INSERT INTO unified_implementation_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "ACT-" + uuid.uuid4().hex[:10].upper(),
                    study_id,
                    str(rec.get("Action", ""))[:180],
                    str(rec.get("Owner", ""))[:80],
                    str(rec.get("Due", ""))[:40],
                    str(rec.get("Status", "Planned"))[:40],
                    str(rec.get("KPI", ""))[:100],
                    float(rec.get("Baseline") or 0),
                    float(rec.get("Target") or 0),
                    float(rec.get("Actual") or 0),
                    str(rec.get("Notes", ""))[:800],
                    _now(),
                    _now(),
                ),
            )
        conn.commit()


def explain_scenario(row: Mapping[str, Any], baseline: Mapping[str, Any]) -> str:
    observations = []
    for metric in ("Cost", "Service", "Carbon", "Risk", "Capacity"):
        if metric in row and metric in baseline:
            try:
                delta = float(row[metric]) - float(baseline[metric])
                direction = "higher" if delta > 0 else "lower" if delta < 0 else "unchanged"
                observations.append(f"{metric}: {direction} by {abs(delta):.1f}.")
            except (TypeError, ValueError):
                pass
    return " ".join(observations) if observations else "Add comparable numeric scenario metrics to explain this result."


def recommendations_for(module: str, readiness_score: float, scenario_count: int, decision_status: str) -> list[str]:
    lower = str(module).lower()
    domain = next((key for key in DOMAIN_RECOMMENDATIONS if key in lower), None)
    suggestions = list(DOMAIN_RECOMMENDATIONS.get(domain, ["Validate the current dataset", "Compare at least two scenarios", "Create a governed decision card"]))
    if readiness_score < 100:
        suggestions.insert(0, "Resolve the open data-readiness checks before using the result.")
    if scenario_count < 2:
        suggestions.append("Create an alternative scenario before deciding.")
    if decision_status in {"Draft", ""}:
        suggestions.append("Move the decision through validation and review once evidence is complete.")
    return suggestions[:5]


def platform_health_snapshot() -> pd.DataFrame:
    ensure_unified_db()
    checks = []
    try:
        import importlib.util
        modules = {
            "Optimization engine": "pulp",
            "Statistics engine": "scipy",
            "Visualization engine": "plotly",
            "Workbook engine": "openpyxl",
        }
        for label, name in modules.items():
            checks.append({"Service": label, "Status": "Ready" if importlib.util.find_spec(name) else "Attention", "Detail": name})
    except Exception as exc:
        checks.append({"Service": "Python runtime", "Status": "Attention", "Detail": str(exc)[:120]})
    with _db() as conn:
        for table, label in [
            ("experience_projects", "Studies store"),
            ("experience_decisions", "Decision store"),
            ("unified_implementation_actions", "Implementation store"),
            ("experience_observability", "Observability store"),
        ]:
            try:
                count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                checks.append({"Service": label, "Status": "Ready", "Detail": f"{count:,} record(s)"})
            except sqlite3.Error as exc:
                checks.append({"Service": label, "Status": "Attention", "Detail": str(exc)[:120]})
    return pd.DataFrame(checks)


def evidence_bundle(study: Mapping[str, Any], data: pd.DataFrame, scenarios: pd.DataFrame, implementation: pd.DataFrame, readiness: Mapping[str, Any], actor: str) -> bytes:
    manifest = {
        "generated_at": _now(),
        "actor": actor,
        "study": dict(study),
        "data_readiness": dict(readiness),
        "scenario_metrics": scenario_metrics(scenarios),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("study.json", json.dumps(manifest, indent=2, default=str).encode("utf-8"))
        archive.writestr("input_data.csv", data.to_csv(index=False).encode("utf-8"))
        archive.writestr("scenario_comparison.csv", scenarios.to_csv(index=False).encode("utf-8"))
        archive.writestr("implementation_tracker.csv", implementation.to_csv(index=False).encode("utf-8"))
        archive.writestr("readiness.json", json.dumps(dict(readiness), indent=2, default=str).encode("utf-8"))
    return buffer.getvalue()


def render_showcase(module: str, title: str, scenarios: pd.DataFrame, study_id: Optional[str]) -> None:
    import streamlit as st
    baseline = scenarios.iloc[0].to_dict() if not scenarios.empty else {}
    selected = scenarios.iloc[1].to_dict() if len(scenarios) > 1 else baseline
    st.markdown(
        "<div class='ui-showcase'>"
        "<div class='ui-kicker'>SHOIR-IE · INDUSTRIAL DECISION STORY</div>"
        "<div class='ui-title'>{}</div>"
        "<div class='ui-copy'>From problem framing to validated decision and implementation evidence.</div>"
        "</div>".format(html.escape(title)),
        unsafe_allow_html=True,
    )
    cards = st.columns(4)
    for col, label, key in zip(cards, ["Baseline", "Cost delta", "Service delta", "Risk delta"], ["baseline", "Cost", "Service", "Risk"]):
        if key == "baseline":
            col.metric(label, str(baseline.get("Scenario", "—")))
        else:
            try:
                delta = float(selected.get(key, 0)) - float(baseline.get(key, 0))
                col.metric(label, f"{delta:+.1f}")
            except (TypeError, ValueError):
                col.metric(label, "—")
    steps = st.columns(7)
    for col, (num, name, _) in zip(steps, WORKFLOW_STEPS):
        col.markdown("<div class='ui-show-step'><b>{}</b><br>{}</div>".format(num, name), unsafe_allow_html=True)
    if len(scenarios) >= 2:
        chart = scenarios.melt(id_vars=["Scenario"], value_vars=[c for c in ["Cost", "Service", "Carbon", "Risk", "Capacity"] if c in scenarios.columns], var_name="Metric", value_name="Value")
        if not chart.empty:
            fig = px.line(chart, x="Scenario", y="Value", color="Metric", markers=True, title="Decision landscape")
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown("### What happens next")
    st.markdown("✓ Validate the evidence  ·  ✓ Review assumptions  ·  ✓ Approve the decision  ·  ✓ Track actual KPI")
    if study_id:
        st.caption("Study ID: " + str(study_id))


def render_unified_workspace(module: str, tier: str, username: str) -> None:
    import streamlit as st

    ensure_unified_db()
    key = _key(module)
    st.markdown(
        "<div class='ui-hero'><div class='ui-kicker'>INDUSTRIAL ENGINEERING OPERATING SYSTEM</div>"
        "<div class='ui-title'>Shoir-IE Unified Study & Decision Center</div>"
        "<div class='ui-copy'>One continuous thread from problem → data → model → scenario → decision → implementation → lesson learned.</div>"
        "<div class='ui-pills'><span>● Evidence-first</span><span>✓ Governed decisions</span><span>◈ Reusable knowledge</span></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        .ui-hero{padding:30px;border-radius:24px;background:linear-gradient(135deg,#07121f 0%,#182a63 52%,#0b6b61 100%);color:#fff;box-shadow:0 22px 50px rgba(15,23,42,.16);margin-bottom:16px;position:relative;overflow:hidden}
        .ui-hero:after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 0%,rgba(255,255,255,.08) 46%,transparent 60%);transform:translateX(-120%);animation:uiShimmer 9s ease-in-out infinite}
        @keyframes uiShimmer{0%,60%{transform:translateX(-120%)}80%,100%{transform:translateX(120%)}}
        .ui-kicker{font-size:11px;letter-spacing:.13em;font-weight:850;color:#7dd3fc}.ui-title{font-size:32px;font-weight:900;line-height:1.12;margin-top:6px}.ui-copy{color:#dbeafe;font-size:14px;max-width:1000px;margin-top:9px}.ui-pills{display:flex;flex-wrap:wrap;gap:9px;margin-top:15px}.ui-pills span{padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);font-size:11px}
        .ui-showcase{padding:30px;border-radius:24px;background:linear-gradient(135deg,#0b1220,#1e3a8a 55%,#0f766e);color:#fff;box-shadow:0 22px 52px rgba(15,23,42,.18);position:relative;overflow:hidden}
        .ui-showcase:after{content:"";position:absolute;inset:0;background:linear-gradient(105deg,transparent,rgba(255,255,255,.08),transparent);transform:translateX(-120%);animation:uiShimmer 10s infinite}
        .ui-show-step{padding:9px 7px;border:1px solid #dbe4f0;border-radius:12px;background:#fff;text-align:center;font-size:11px;color:#334155;min-height:54px}
        @media (prefers-reduced-motion:reduce){.ui-hero:after,.ui-showcase:after{animation:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "unified_study_id" not in st.session_state:
        st.session_state["unified_study_id"] = None

    top = st.columns(4)
    with top[0]:
        st.metric("Current tier", tier.replace(" Tier", ""))
    with top[1]:
        with _db() as conn:
            study_count = int(conn.execute("SELECT COUNT(*) FROM experience_projects WHERE owner=?", (username,)).fetchone()[0])
        st.metric("Your studies", f"{study_count:,}")
    with top[2]:
        with _db() as conn:
            decision_count = int(conn.execute("SELECT COUNT(*) FROM experience_decisions WHERE owner=?", (username,)).fetchone()[0])
        st.metric("Your decisions", f"{decision_count:,}")
    with top[3]:
        st.metric("Platform capabilities", "{}/60".format(feature_stats()["implemented"]))

    tabs = st.tabs(["🏠 Overview", "📥 Data Readiness", "🧪 Scenarios", "📝 Decision", "🛠 Implementation", "🧠 Memory", "🩺 Health", "🎬 Showcase", "📦 Export"])

    with tabs[0]:
        a, b = st.columns([1.2, 1], gap="large")
        with a:
            title = st.text_input("Study title", value=st.session_state.get("unified_title", module + " Improvement Study"), key="ui_study_title")
            objective = st.text_area("Engineering objective", value=st.session_state.get("unified_objective", "Define the problem, evidence and target outcome before changing the operation."), key="ui_study_objective", height=90)
            if st.button("✨ Create / Save Study", type="primary", use_container_width=True, key="ui_save_study"):
                pid = create_unified_study(title, module, username, objective)
                st.session_state["unified_study_id"] = pid
                st.session_state["unified_title"] = title
                st.session_state["unified_objective"] = objective
                st.success("Study saved: " + pid)
        with b:
            st.markdown("#### The digital thread")
            for num, name, desc in WORKFLOW_STEPS:
                st.markdown(f"**{num} · {name}** — {desc}")
        if st.session_state.get("unified_study_id"):
            st.info("Active study: " + str(st.session_state["unified_study_id"]))
        st.markdown("#### Before / After")
        before_after = st.data_editor(
            pd.DataFrame({"KPI": ["Cost index", "Service %", "Carbon index", "Risk index"], "Before": [100, 95, 100, 10], "After": [92, 97, 86, 8]}),
            use_container_width=True,
            hide_index=True,
            key="ui_before_after",
        )
        ba = before_after.melt(id_vars="KPI", var_name="State", value_name="Value")
        fig = px.bar(ba, x="KPI", y="Value", color="State", barmode="group", title="Before / After impact view")
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=55, b=10))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        readiness_score = float(st.session_state.get("unified_readiness_score", 0))
        scenario_count = int(st.session_state.get("unified_scenario_count", 1))
        recs = recommendations_for(module, readiness_score, scenario_count, st.session_state.get("unified_decision_status", "Draft"))
        with st.container(border=True):
            st.markdown("#### Next best actions")
            for rec in recs:
                st.markdown("✓ " + rec)

    with tabs[1]:
        st.markdown("#### Data Readiness Gate")
        source = st.file_uploader("📥 Upload Excel or CSV", type=["xlsx", "csv"], key="ui_data_upload")
        if source is not None:
            try:
                raw = source.getvalue()
                data = pd.read_excel(io.BytesIO(raw)) if source.name.lower().endswith("xlsx") else pd.read_csv(io.BytesIO(raw))
                st.session_state["unified_data"] = data
                st.session_state["unified_source"] = source.name
                st.success("Dataset loaded and ready for validation.")
            except Exception as exc:
                st.error("The dataset could not be read safely. Check that the file is a valid Excel/CSV workbook.")
                st.caption("Technical detail: " + str(exc)[:180])
        if "unified_data" not in st.session_state:
            if st.button("🧪 Load module starter dataset", use_container_width=True, key="ui_load_starter"):
                st.session_state["unified_data"] = _starter_for_module(module)
                st.session_state["unified_source"] = "Shoir-IE starter dataset"
        data = st.session_state.get("unified_data", _starter_for_module(module))
        required_text = st.text_input("Required columns (comma separated)", value="", key="ui_required_columns", placeholder="e.g. SKU, Demand, Date")
        required = [x.strip() for x in required_text.split(",") if x.strip()]
        ready = assess_data_readiness(data, required)
        st.session_state["unified_readiness_score"] = ready["score"]
        if st.session_state.get("unified_study_id"):
            with _db() as conn:
                conn.execute("INSERT INTO unified_dataset_runs(study_id,source_name,rows,columns,quality,readiness_json,created_at) VALUES(?,?,?,?,?,?,?)", (st.session_state["unified_study_id"], st.session_state.get("unified_source", "session"), len(data), len(data.columns), ready["score"], json.dumps(ready, default=str), _now()))
                conn.commit()
        d1, d2, d3 = st.columns(3)
        d1.metric("Readiness score", f'{ready["score"]:.1f}%')
        d2.metric("Checks passed", f'{ready["passed"]}/{ready["total"]}')
        d3.metric("Rows", f'{len(data):,}')
        checks_df = pd.DataFrame(ready["checks"])
        checks_df["Status"] = checks_df["status"].map(lambda x: "✓ PASS" if x else "⚠ REVIEW")
        st.dataframe(checks_df[["name", "Status", "detail"]].rename(columns={"name":"Check","detail":"Details"}), use_container_width=True, hide_index=True)
        nums = [c for c in data.columns if pd.api.types.is_numeric_dtype(data[c])]
        if nums:
            metric = st.selectbox("Readiness metric preview", nums, key="ui_readiness_metric")
            chart = px.histogram(data, x=metric, nbins=20, title=f"Data distribution · {metric}")
            chart.update_layout(height=300, margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})
        st.dataframe(data.head(1000), use_container_width=True, hide_index=True)

    with tabs[2]:
        st.markdown("#### Scenario Laboratory")
        study_id = st.session_state.get("unified_study_id") or "SESSION"
        if "unified_scenarios" not in st.session_state:
            st.session_state["unified_scenarios"] = pd.DataFrame(STARTER_SCENARIOS)
        scenarios = st.data_editor(st.session_state["unified_scenarios"], num_rows="dynamic", use_container_width=True, hide_index=True, key="ui_scenarios")
        st.session_state["unified_scenarios"] = scenarios
        st.session_state["unified_scenario_count"] = int(scenarios["Scenario"].nunique()) if "Scenario" in scenarios.columns else 0
        if st.button("💾 Save Scenario Set", type="primary", use_container_width=True, key="ui_save_scenarios"):
            if st.session_state.get("unified_study_id"):
                save_scenario_table(st.session_state["unified_study_id"], scenarios)
                register_lineage("study", st.session_state["unified_study_id"], "scenario_set", st.session_state["unified_study_id"], "contains", username)
                st.success("Scenario set saved to the study.")
            else:
                st.warning("Create a study first so the scenario set can be persisted.")
        if not scenarios.empty and "Scenario" in scenarios.columns:
            metrics = [c for c in scenarios.columns if c != "Scenario" and pd.api.types.is_numeric_dtype(scenarios[c])]
            if metrics:
                metric = st.selectbox("Comparison metric", metrics, key="ui_scenario_metric")
                fig = px.bar(scenarios, x="Scenario", y=metric, text=metric, title=f"Scenario comparison · {metric}")
                fig.update_layout(height=340, margin=dict(l=10, r=10, t=55, b=10))
                fig.update_traces(textposition="outside")
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                st.markdown("#### Explain my result")
                sel = st.selectbox("Scenario", list(scenarios["Scenario"]), key="ui_explain_scenario")
                row = scenarios[scenarios["Scenario"] == sel].iloc[0].to_dict()
                baseline = scenarios.iloc[0].to_dict()
                st.info(explain_scenario(row, baseline))

    with tabs[3]:
        st.markdown("#### Governed Decision Card")
        did = st.session_state.get("unified_decision_id")
        decision_title = st.text_input("Decision title", value=st.session_state.get("unified_title", module) + " decision", key="ui_decision_title")
        chosen = st.text_input("Chosen scenario", value="", key="ui_chosen_scenario")
        rationale = st.text_area("Decision rationale", value="", height=90, key="ui_decision_rationale")
        metrics_payload = {"scenario": chosen or "Not selected", "readiness": st.session_state.get("unified_readiness_score", 0)}
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📝 Create Decision Card", type="primary", use_container_width=True, key="ui_create_decision"):
                did = create_decision(decision_title, module, metrics_payload, {"objective": st.session_state.get("unified_objective", "")}, {"scenario": chosen, "readiness": st.session_state.get("unified_readiness_score", 0)}, username)
                st.session_state["unified_decision_id"] = did
                st.session_state["unified_decision_status"] = "Draft"
                if st.session_state.get("unified_study_id"):
                    register_lineage("study", st.session_state["unified_study_id"], "decision", did, "produced", username)
                st.success("Decision created: " + did)
        with c2:
            if did:
                next_status = st.selectbox("Move decision to", ["Validated", "Proposed", "Review", "Approved", "Implemented", "Verified"], key="ui_decision_next")
                if st.button("➡️ Transition Decision", use_container_width=True, key="ui_transition_decision"):
                    try:
                        transition_decision(did, username, next_status, rationale)
                        st.session_state["unified_decision_status"] = next_status
                        st.success("Decision status updated to " + next_status + ".")
                    except Exception as exc:
                        st.error("Decision transition could not be completed: " + str(exc)[:180])
        if did:
            with _db() as conn:
                row = conn.execute("SELECT decision_id,title,status,metrics_json,assumptions_json,uncertainty_json,owner,updated_at FROM experience_decisions WHERE decision_id=?", (did,)).fetchone()
            if row:
                st.markdown("#### Decision evidence")
                st.dataframe(pd.DataFrame([{
                    "ID": row[0], "Title": row[1], "Status": row[2], "Owner": row[6], "Updated": row[7],
                    "Metrics": row[3], "Assumptions": row[4], "Uncertainty": row[5]
                }]), use_container_width=True, hide_index=True)
                st.markdown("✓ Evidence captured  ·  ✓ Approval state tracked  ·  ✓ Reproducible record")

    with tabs[4]:
        st.markdown("#### Implementation Tracker")
        study_id = st.session_state.get("unified_study_id")
        tracker = _implementation_df(study_id)
        if tracker.empty:
            tracker = pd.DataFrame([{"Action":"Measure agreed KPI after implementation","Owner":"","Due":"","Status":"Planned","KPI":"Primary KPI","Baseline":0.0,"Target":0.0,"Actual":0.0,"Notes":""}])
        edited = st.data_editor(tracker.drop(columns=["action_id"], errors="ignore"), num_rows="dynamic", use_container_width=True, hide_index=True, key="ui_implementation")
        if study_id and st.button("💾 Save Implementation Plan", type="primary", use_container_width=True, key="ui_save_implementation"):
            _save_implementation(study_id, edited)
            st.success("Implementation plan saved.")
        if not edited.empty:
            status_counts = edited["Status"].value_counts().reset_index(name="Actions")
            status_counts.columns = ["Status", "Actions"]
            fig = px.bar(status_counts, x="Status", y="Actions", title="Implementation status")
            fig.update_layout(height=280, margin=dict(l=10, r=10, t=55, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            kpi_cols = [c for c in ["Baseline","Target","Actual"] if c in edited.columns]
            if kpi_cols:
                kpi_plot = edited[["Action"] + kpi_cols].melt(id_vars="Action", var_name="Stage", value_name="Value")
                st.plotly_chart(px.bar(kpi_plot, x="Action", y="Value", color="Stage", barmode="group", title="KPI tracking"), use_container_width=True, config={"displayModeBar": False})

    with tabs[5]:
        st.markdown("#### Industrial Decision Memory")
        memory_search = st.text_input("Search previous problems, lessons or decisions", key="ui_memory_search")
        with _db() as conn:
            query = "SELECT memory_id,problem,data_ref,model_ref,scenario_ref,decision_ref,actual_result,lesson,owner,updated_at FROM experience_memory ORDER BY updated_at DESC LIMIT 100"
            mem = pd.read_sql(query, conn)
        if memory_search.strip():
            term = "%" + memory_search.strip() + "%"
            with _db() as conn:
                mem = pd.read_sql(
                    "SELECT memory_id,problem,data_ref,model_ref,scenario_ref,decision_ref,actual_result,lesson,owner,updated_at FROM experience_memory WHERE problem LIKE ? OR lesson LIKE ? ORDER BY updated_at DESC LIMIT 100",
                    conn,
                    params=(term, term),
                )
        if mem.empty:
            st.info("No decision memories yet. Capture the first lesson learned below.")
        else:
            st.dataframe(mem, use_container_width=True, hide_index=True)
        p1, p2 = st.columns(2)
        with p1:
            problem = st.text_area("Problem", key="ui_mem_problem")
            lesson = st.text_area("Lesson learned", key="ui_mem_lesson")
        with p2:
            actual = st.text_area("Actual result", key="ui_mem_actual")
            if st.button("🧠 Save to Industrial Memory", type="primary", use_container_width=True, key="ui_save_memory"):
                memory_id = "MEM-" + uuid.uuid4().hex[:12].upper()
                with _db() as conn:
                    conn.execute(
                        "INSERT INTO experience_memory VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (memory_id, problem[:800], "", "", str(st.session_state.get("unified_scenario_count", "")), str(st.session_state.get("unified_decision_id", "")), actual[:1000], lesson[:1200], username, _now(), _now()),
                    )
                    conn.commit()
                st.success("Lesson stored in Industrial Decision Memory: " + memory_id)

    with tabs[6]:
        st.markdown("#### Platform Health")
        health = platform_health_snapshot()
        total = len(health)
        ready = int((health["Status"] == "Ready").sum()) if total else 0
        st.metric("Services healthy", f"{ready}/{total}")
        st.progress(ready / max(1, total), text=f"{ready}/{total} checks ready")
        st.dataframe(health, use_container_width=True, hide_index=True)
        if st.button("🔄 Refresh Health", use_container_width=True, key="ui_health_refresh"):
            st.rerun()

    with tabs[7]:
        render_showcase(module, st.session_state.get("unified_title", module + " Improvement Study"), st.session_state.get("unified_scenarios", pd.DataFrame(STARTER_SCENARIOS)), st.session_state.get("unified_study_id"))

    with tabs[8]:
        data = st.session_state.get("unified_data", _starter_for_module(module))
        scenarios = st.session_state.get("unified_scenarios", pd.DataFrame(STARTER_SCENARIOS))
        implementation = _implementation_df(st.session_state.get("unified_study_id"))
        ready = assess_data_readiness(data)
        study = {
            "study_id": st.session_state.get("unified_study_id"),
            "title": st.session_state.get("unified_title", module),
            "module": module,
            "tier": tier,
            "decision_id": st.session_state.get("unified_decision_id"),
        }
        st.markdown("### Evidence Export Center")
        st.caption("A single package for the engineering trail — inputs, scenarios, implementation and validation evidence.")
        st.download_button("📦 Download Complete Evidence Pack", evidence_bundle(study, data, scenarios, implementation, ready, username), file_name="shoir_ie_unified_evidence.zip", mime="application/zip", type="primary", use_container_width=True)
        e1,e2,e3 = st.columns(3)
        e1.download_button("📄 Download Study Manifest", json.dumps(study, indent=2).encode(), file_name="study_manifest.json", mime="application/json", use_container_width=True)
        e2.download_button("📊 Download Scenario CSV", scenarios.to_csv(index=False).encode(), file_name="scenario_comparison.csv", mime="text/csv", use_container_width=True)
        e3.download_button("🛠 Download Implementation CSV", implementation.to_csv(index=False).encode(), file_name="implementation_tracker.csv", mime="text/csv", use_container_width=True)


def render_global_product_dock(module: str, tier: str, username: str) -> None:
    """Small, calm global command bar shared by legacy modules too."""
    import streamlit as st

    ensure_unified_db()
    key = _key(module)
    study_id = st.session_state.get("unified_study_id")
    readiness = float(st.session_state.get("unified_readiness_score", 0.0))
    st.markdown(
        "<div class='dock-title'>⌘ Shoir-IE Workspace</div>",
        unsafe_allow_html=True,
    )
    d1,d2,d3,d4 = st.columns([1.8, 1, 1, 1.2])
    with d1:
        choice = st.selectbox("Command", COMMAND_ACTIONS, key="global_command_palette_" + key, label_visibility="collapsed")
    with d2:
        st.metric("Study", "Active" if study_id else "Not set")
    with d3:
        st.metric("Data", f"{readiness:.0f}%")
    with d4:
        if st.button("▶ Open", type="primary", use_container_width=True, key="global_command_open_" + key):
            mapping = {
                "Open Unified Study Center": "open",
                "Open Universal Industrial Engine": "universal",
                "Check Data Readiness": "readiness",
                "Create Decision Card": "decision",
                "Open Implementation Tracker": "implementation",
                "Open Industrial Memory": "memory",
                "Open Platform Health": "health",
                "Showcase Mode": "showcase",
                "Export Evidence Pack": "export",
            }
            st.session_state["global_command_action"] = mapping[choice]
            if choice == "Open Unified Study Center":
                st.session_state["force_unified_workspace"] = True
                st.rerun()

    action = st.session_state.pop("global_command_action", None)
    if action and action != "open":
        if action == "universal":
            st.session_state["force_universal_engine"] = True
            st.rerun()
        with st.expander("⌘ Quick workspace action", expanded=True):
            if action == "readiness":
                data = st.session_state.get("unified_data", _starter_for_module(module))
                ready = assess_data_readiness(data)
                st.session_state["unified_readiness_score"] = ready["score"]
                st.metric("Data readiness", f'{ready["score"]:.1f}%')
                tbl = pd.DataFrame(ready["checks"])
                tbl["Status"] = tbl["status"].map(lambda x: "✓ PASS" if x else "⚠ REVIEW")
                st.dataframe(tbl[["name","Status","detail"]].rename(columns={"name":"Check","detail":"Details"}), use_container_width=True, hide_index=True)
            elif action == "decision":
                st.info("Open the Unified Study & Decision Center → Decision tab to create the governed Decision Card.")
                st.session_state["force_unified_workspace"] = True
                st.rerun()
            elif action == "implementation":
                st.info("Open the Unified Study & Decision Center → Implementation tab to track owners, dates and actual KPIs.")
                st.session_state["force_unified_workspace"] = True
                st.rerun()
            elif action == "memory":
                st.info("Open the Unified Study & Decision Center → Memory tab to search prior lessons.")
                st.session_state["force_unified_workspace"] = True
                st.rerun()
            elif action == "health":
                health = platform_health_snapshot()
                st.dataframe(health, use_container_width=True, hide_index=True)
            elif action == "showcase":
                st.session_state["showcase_inline"] = True
            elif action == "export":
                st.session_state["export_inline"] = True

    if st.session_state.pop("showcase_inline", False):
        render_showcase(module, module + " · Showcase", st.session_state.get("unified_scenarios", pd.DataFrame(STARTER_SCENARIOS)), study_id)
    if st.session_state.pop("export_inline", False):
        data = st.session_state.get("unified_data", _starter_for_module(module))
        scenarios = st.session_state.get("unified_scenarios", pd.DataFrame(STARTER_SCENARIOS))
        ready = assess_data_readiness(data)
        implementation = _implementation_df(study_id)
        study = {"study_id": study_id, "module": module, "tier": tier}
        st.download_button(
            "📦 Download Quick Evidence Pack",
            evidence_bundle(study, data, scenarios, implementation, ready, username),
            file_name="shoir_ie_quick_evidence.zip",
            mime="application/zip",
            use_container_width=True,
            key="global_quick_evidence_" + key,
        )

def copilot_context() -> str:
    """Human-readable platform context for the AI Copilot system prompt."""
    capabilities = [
        "Unified Studies",
        "Data Readiness Gate",
        "Scenario Laboratory",
        "Before / After impact analysis",
        "Explain My Result",
        "Governed Decision Cards",
        "Implementation Tracker",
        "Industrial Decision Memory",
        "Platform Health",
        "Showcase Mode",
        "Universal Evidence Export",
        "Command Palette",
        "Universal Industrial Engine",
        "Industrial Pivot",
        "Explain & Trace",
        "Automation replay",
        "Trust Center",
        "cross-module recommendations",
    ]
    return (
        "Shoir-IE now operates as one unified industrial product. "
        "Its shared workflow is Problem → Data → Model → Scenario → Decision → Implementation → Lesson. "
        "Available cross-cutting experience surfaces: " + ", ".join(capabilities) + ". "
        "Use evidence-first language, never invent values, clearly separate measured results from assumptions, "
        "and prefer preview/approval before any destructive action."
    )
