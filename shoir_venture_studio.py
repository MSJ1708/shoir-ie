"""Shoir-IE Venture Studio: durable incubator / investment evidence workspace.

The workspace is intentionally evidence-first and graph-friendly: persisted commercial facts
feed the executive charts, readiness diagnostics, value calculations, and investor exports.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import math
import sqlite3
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from industrial_experience import ensure_experience_db

DB_PATH = "enterprise_full_workspace.db"
PILOT_STAGES = ["Discovery", "Baseline", "Pilot Setup", "Deployment", "Measurement", "Customer Feedback", "Decision"]
PILOT_STATUSES = ["Active", "Complete", "Converted", "Paused", "Not Proceeding"]
CONFIDENCE = ["Low", "Medium", "High", "Audited"]
ARTIFACT_CATEGORIES = ["Product", "Problem", "Market", "Customer Evidence", "Pilots", "ROI", "Traction", "Roadmap", "Security", "Financial Model"]
DEMO_STORY = [
    ("01 · 0:00–1:00", "Raw workbook", "Start with the messy operational workbook and expose missing values and duplicate rows."),
    ("02 · 1:00–2:00", "Data quality", "Show the evidence-preserving cleanup: findings first, remediation second, activated dataset third."),
    ("03 · 2:00–3:00", "Industrial Workbook", "Move into Inputs → Data → Calculations → KPIs → Simulation → Optimization → Scenarios → Decisions → Dashboard."),
    ("04 · 3:00–4:00", "Facility / Flow", "Trace material movement through a compact Sankey-style process path."),
    ("05 · 4:00–5:00", "Scenario comparison", "Compare baseline and alternative operating states using the same deterministic dataset."),
    ("06 · 5:00–6:00", "Value evidence", "Show measured baseline/post logic and an illustrative value bridge without claiming universal savings."),
    ("07 · 6:00–7:00", "Decision / report", "Close with a reproducible executive report and a clear handoff into real customer evidence."),
]

VALUE_METRIC_TEMPLATES = [
    ("Hours saved", "Time", "lower_is_better", "hours"),
    ("Planning-cycle time reduced", "Time", "lower_is_better", "hours"),
    ("Scenario turnaround time", "Time", "lower_is_better", "hours"),
    ("Report-production time", "Time", "lower_is_better", "hours"),
    ("Data defects detected", "Quality", "higher_is_better", "issues"),
    ("Rework cycles", "Quality", "lower_is_better", "cycles"),
    ("Inventory impact", "Inventory", "lower_is_better", "currency"),
    ("Transport distance", "Logistics", "lower_is_better", "km"),
    ("Transport cost", "Logistics", "lower_is_better", "currency"),
    ("Scrap / rework value", "Quality", "lower_is_better", "currency"),
    ("Downtime exposure", "Operations", "lower_is_better", "currency"),
    ("Energy impact", "Sustainability", "lower_is_better", "kWh"),
    ("Carbon impact", "Sustainability", "lower_is_better", "kgCO2e"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS venture_customers (
    customer_id TEXT PRIMARY KEY, owner TEXT NOT NULL, target_customer TEXT, end_user TEXT,
    beneficiary TEXT, adopting_organization TEXT, problem_statement TEXT, current_workaround TEXT,
    interview_notes TEXT, pain_severity REAL, pain_frequency TEXT, current_process_time_hours REAL,
    current_process_cost REAL, error_burden TEXT, buying_process TEXT, objections TEXT,
    requested_features TEXT, pilot_status TEXT, next_action TEXT, source_ref TEXT, source_date TEXT,
    confidence TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_venture_customers_owner ON venture_customers(owner, updated_at DESC);

CREATE TABLE IF NOT EXISTS venture_pilots (
    pilot_id TEXT PRIMARY KEY, owner TEXT NOT NULL, customer_id TEXT, title TEXT NOT NULL,
    stage TEXT NOT NULL, status TEXT NOT NULL, champion TEXT, business_problem TEXT,
    baseline_summary TEXT, pilot_setup TEXT, deployment_notes TEXT, measurement_plan TEXT,
    customer_feedback TEXT, decision_notes TEXT, start_date TEXT, target_date TEXT, next_action TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_venture_pilots_owner ON venture_pilots(owner, updated_at DESC);

CREATE TABLE IF NOT EXISTS venture_hypotheses (
    hypothesis_id TEXT PRIMARY KEY, owner TEXT NOT NULL, statement TEXT NOT NULL, metric TEXT NOT NULL,
    baseline TEXT, baseline_unit TEXT, experiment TEXT, result TEXT, decision TEXT, status TEXT NOT NULL,
    confidence TEXT, source_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS venture_evidence (
    evidence_id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL, evidence_type TEXT NOT NULL,
    source TEXT, source_date TEXT, confidence TEXT, description TEXT, linked_object_type TEXT,
    linked_object_id TEXT, artifact_url TEXT, content TEXT, checksum TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_venture_evidence_owner ON venture_evidence(owner, created_at DESC);

CREATE TABLE IF NOT EXISTS venture_value_measurements (
    value_id TEXT PRIMARY KEY, owner TEXT NOT NULL, pilot_id TEXT, metric TEXT NOT NULL, category TEXT,
    direction TEXT NOT NULL, unit TEXT, baseline_value REAL, post_value REAL,
    frequency_per_year REAL DEFAULT 1, unit_value REAL DEFAULT 0, currency TEXT,
    implementation_cost REAL DEFAULT 0, source_ref TEXT, source_date TEXT, confidence TEXT,
    notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS venture_quality_metrics (
    quality_id TEXT PRIMARY KEY, owner TEXT NOT NULL, pilot_id TEXT, issues_detected REAL,
    issues_confirmed REAL, baseline_rework_hours REAL, post_rework_hours REAL,
    source_ref TEXT, source_date TEXT, confidence TEXT, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS venture_artifacts (
    artifact_id TEXT PRIMARY KEY, owner TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL,
    content TEXT NOT NULL, source_url TEXT, source_date TEXT, confidence TEXT, version INTEGER NOT NULL DEFAULT 1,
    checksum TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(owner, category, title)
);
CREATE TABLE IF NOT EXISTS venture_artifact_versions (
    version_id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL, version INTEGER NOT NULL, content TEXT NOT NULL,
    source_url TEXT, source_date TEXT, confidence TEXT, checksum TEXT, saved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS venture_product_events (
    event_id TEXT PRIMARY KEY, owner TEXT NOT NULL, event_type TEXT NOT NULL, feature TEXT,
    value REAL, details_json TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_venture_events_owner ON venture_product_events(owner, created_at DESC);

CREATE TABLE IF NOT EXISTS venture_market_claims (
    claim_id TEXT PRIMARY KEY, owner TEXT NOT NULL, competitor_or_alternative TEXT, claim_type TEXT,
    claim TEXT NOT NULL, source_url TEXT, source_date TEXT, confidence TEXT, notes TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS venture_case_studies (
    case_id TEXT PRIMARY KEY, owner TEXT NOT NULL, pilot_id TEXT NOT NULL, title TEXT NOT NULL,
    content TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS venture_business_model (
    model_id TEXT PRIMARY KEY, owner TEXT NOT NULL, offering TEXT NOT NULL, target_segment TEXT,
    billing_model TEXT, price REAL, currency TEXT, sales_motion TEXT, evidence_required TEXT,
    notes TEXT, updated_at TEXT NOT NULL, UNIQUE(owner, offering)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _db() -> sqlite3.Connection:
    ensure_experience_db()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    for statement in SCHEMA.split(";\n"):
        if statement.strip():
            conn.execute(statement)
    conn.commit()
    return conn


def ensure_venture_db() -> None:
    with _db() as conn:
        conn.commit()


def _query(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    try:
        with _db() as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def _scalar(sql: str, params: tuple[Any, ...] = (), default: float = 0.0) -> float:
    try:
        with _db() as conn:
            row = conn.execute(sql, params).fetchone()
        return float(row[0]) if row and row[0] is not None else default
    except Exception:
        return default


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else fallback
    except Exception:
        return fallback


def _optional_float(value: Any) -> float | None:
    """Parse a numeric value while preserving an unmeasured/blank state as None."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _maybe_first_result(owner: str) -> None:
    """Record first successful Venture Studio result once per session."""
    if st.session_state.get("venture_first_result_recorded"):
        return
    try:
        start = datetime.fromisoformat(str(st.session_state.get("venture_session_started_at")))
        seconds = max(0.0, (datetime.now(timezone.utc) - start).total_seconds())
    except Exception:
        seconds = 0.0
    st.session_state["venture_first_result_recorded"] = True
    track_event(owner, "first_result", "Venture Studio", details={"time_to_first_result_seconds": seconds})


def track_event(owner: str, event_type: str, feature: str = "", value: float | None = None, details: dict[str, Any] | None = None) -> None:
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO venture_product_events VALUES(?,?,?,?,?,?,?)",
                (_id("EVT"), str(owner), str(event_type), str(feature), value, json.dumps(details or {}, default=str), _now()),
            )
            conn.commit()
    except Exception:
        pass


def value_calculation(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    """Calculate measured operational effect without inventing missing measurements."""
    d = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    baseline = _optional_float(d.get("baseline_value", d.get("Baseline")))
    post = _optional_float(d.get("post_value", d.get("Post")))
    frequency_raw = _optional_float(d.get("frequency_per_year", d.get("Frequency / year")))
    frequency = max(0.0, frequency_raw if frequency_raw is not None else 1.0)
    unit_value_raw = _optional_float(d.get("unit_value", d.get("Unit value")))
    unit_value = max(0.0, unit_value_raw) if unit_value_raw is not None else None
    implementation_raw = _optional_float(d.get("implementation_cost", 0.0))
    implementation = max(0.0, implementation_raw if implementation_raw is not None else 0.0)
    direction = str(d.get("direction", d.get("Direction", "lower_is_better"))).strip().lower()

    valid = baseline is not None and post is not None and direction in {"lower_is_better", "higher_is_better"}
    effect = 0.0
    if valid:
        effect = (baseline - post) if direction == "lower_is_better" else (post - baseline)
    annualized_effect = effect * frequency if valid else 0.0
    economic_value = annualized_effect * unit_value if valid and unit_value is not None else 0.0

    return {
        "valid": 1.0 if valid else 0.0,
        "priced": 1.0 if valid and unit_value is not None else 0.0,
        "delta": effect,
        "annualized_effect": annualized_effect,
        "economic_value": economic_value,
        "implementation_cost": implementation,
        "currency": str(d.get("currency", d.get("Currency", "")) or "").strip().upper(),
    }


def quality_evidence_calculation(row: pd.Series | dict[str, Any]) -> dict[str, float]:
    d = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    detected_raw = _optional_float(d.get("issues_detected", d.get("Issues detected")))
    confirmed_raw = _optional_float(d.get("issues_confirmed", d.get("Issues confirmed")))
    baseline = _optional_float(d.get("baseline_rework_hours", d.get("Baseline rework hours")))
    post = _optional_float(d.get("post_rework_hours", d.get("Post rework hours")))
    detected = max(0.0, detected_raw if detected_raw is not None else 0.0)
    confirmed = max(0.0, confirmed_raw if confirmed_raw is not None else 0.0)
    rate = (detected / confirmed * 100.0) if confirmed > 0 else 0.0
    avoided = (baseline - post) if baseline is not None and post is not None else 0.0
    return {
        "error_detection_rate_percent": rate,
        "rework_avoided_hours": avoided,
    }


def value_summary(values: pd.DataFrame) -> dict[str, Any]:
    """Summarize measured value and block silent aggregation of mixed currencies."""
    empty = {
        "measured_rows": 0.0,
        "priced_rows": 0.0,
        "annualized_benefit": 0.0,
        "implementation_cost": 0.0,
        "net_value": 0.0,
        "roi_percent": 0.0,
        "payback_months": 0.0,
        "currency": "",
        "mixed_currency": 0.0,
    }
    if values.empty:
        return empty

    calc = values.apply(value_calculation, axis=1, result_type="expand")
    valid_mask = calc["valid"].gt(0)
    valid = calc.loc[valid_mask]

    unit_col = "unit_value" if "unit_value" in values.columns else "Unit value" if "Unit value" in values.columns else None
    currency_col = "currency" if "currency" in values.columns else "Currency" if "Currency" in values.columns else None
    if unit_col is not None:
        priced_mask = valid_mask & values[unit_col].map(_optional_float).notna()
        priced = calc.loc[priced_mask]
    else:
        priced_mask = pd.Series(False, index=values.index)
        priced = calc.iloc[0:0]

    currencies: list[str] = []
    if currency_col is not None and not priced.empty:
        currencies = sorted({
            str(x).strip().upper()
            for x in values.loc[priced_mask, currency_col].tolist()
            if str(x).strip()
        })
    mixed_currency = len(currencies) > 1

    benefit = 0.0 if mixed_currency else float(priced["economic_value"].sum())
    implementation = float(valid["implementation_cost"].max()) if not valid.empty else 0.0
    net = benefit - implementation
    roi = (net / implementation * 100.0) if implementation > 0 and benefit != 0 and not mixed_currency else 0.0
    payback = (implementation / (benefit / 12.0)) if benefit > 0 and implementation > 0 and not mixed_currency else 0.0
    currency = "MIXED" if mixed_currency else (currencies[0] if currencies else "")

    return {
        "measured_rows": float(len(valid)),
        "priced_rows": float(len(priced)),
        "annualized_benefit": benefit,
        "implementation_cost": implementation,
        "net_value": net,
        "roi_percent": roi,
        "payback_months": payback,
        "currency": currency,
        "mixed_currency": 1.0 if mixed_currency else 0.0,
    }


def _style_fig(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=54, b=20),
        template="plotly_white",
        hoverlabel=dict(namelength=-1),
    )
    return fig


def _show_fig(fig: go.Figure, height: int = 320, title: str = "") -> None:
    if title:
        fig.update_layout(title=dict(text=html.escape(title), x=0.0, xanchor="left"))
    st.plotly_chart(
        _style_fig(fig, height),
        use_container_width=True,
        config={"displaylogo": False, "responsive": True},
    )

def _customer_df(owner: str) -> pd.DataFrame:
    return _query(
        """SELECT customer_id,target_customer,end_user,beneficiary,adopting_organization,
                  pain_severity,pain_frequency,pilot_status,next_action,source_date,confidence,updated_at
           FROM venture_customers WHERE owner=? ORDER BY updated_at DESC""",
        (owner,),
    )


def _pilot_df(owner: str) -> pd.DataFrame:
    return _query(
        """SELECT pilot_id,customer_id,title,stage,status,champion,start_date,target_date,next_action,updated_at
           FROM venture_pilots WHERE owner=? ORDER BY updated_at DESC""",
        (owner,),
    )


def _customer_record(owner: str, customer_id: str | None) -> dict[str, Any]:
    if not customer_id:
        return {}
    df = _query("SELECT * FROM venture_customers WHERE owner=? AND customer_id=?", (owner, customer_id))
    return df.iloc[0].to_dict() if not df.empty else {}


def _pilot_record(owner: str, pilot_id: str | None) -> dict[str, Any]:
    if not pilot_id:
        return {}
    df = _query("SELECT * FROM venture_pilots WHERE owner=? AND pilot_id=?", (owner, pilot_id))
    return df.iloc[0].to_dict() if not df.empty else {}


def _render_header(owner: str) -> None:
    customer_count = int(_scalar("SELECT COUNT(*) FROM venture_customers WHERE owner=?", (owner,)))
    pilot_count = int(_scalar("SELECT COUNT(*) FROM venture_pilots WHERE owner=?", (owner,)))
    evidence_count = int(_scalar("SELECT COUNT(*) FROM venture_evidence WHERE owner=?", (owner,)))
    artifact_count = int(_scalar("SELECT COUNT(*) FROM venture_artifacts WHERE owner=?", (owner,)))
    st.markdown(
        """
        <style>
        .venture-hero{padding:26px 30px;border:1px solid #dbe4ef;border-radius:22px;background:linear-gradient(135deg,#071525,#173c78 58%,#0f766e);color:#fff;box-shadow:0 18px 48px rgba(15,23,42,.14);margin:4px 0 16px}
        .venture-kicker{font-size:10px;font-weight:900;letter-spacing:.16em;text-transform:uppercase;color:#7dd3fc}
        .venture-title{font-size:32px;font-weight:950;letter-spacing:-.04em;line-height:1.05;margin-top:5px}
        .venture-copy{font-size:13px;color:#dbeafe;max-width:950px;line-height:1.55;margin-top:8px}
        .venture-note{border-left:4px solid #2563eb;padding:9px 12px;background:#eff6ff;color:#1e3a8a;border-radius:8px;font-size:12px;line-height:1.5}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="venture-hero">
          <div class="venture-kicker">Incubator / investment evidence layer</div>
          <div class="venture-title">🚀 Venture Studio · From engineering capability to venture proof</div>
          <div class="venture-copy">Capture customer pain, run measurable pilots, connect hypotheses to evidence, calculate customer-specific value, preserve investor artifacts, and turn completed pilots into proof packages — without inventing traction or universal savings claims.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    r = st.columns(7)
    for col, label in zip(r, ["Customer", "Pilot", "Hypothesis", "Evidence", "Value", "Decision", "Outcome"]):
        col.caption(label)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Customers / stakeholders", f"{customer_count:,}")
    c2.metric("Pilots", f"{pilot_count:,}")
    c3.metric("Evidence records", f"{evidence_count:,}")
    c4.metric("Controlled artifacts", f"{artifact_count:,}")


def _render_overview(owner: str) -> None:
    """Executive evidence cockpit: show the venture proof chain without inventing traction."""
    customers = int(_scalar("SELECT COUNT(*) FROM venture_customers WHERE owner=?", (owner,)))
    pilots = int(_scalar("SELECT COUNT(*) FROM venture_pilots WHERE owner=?", (owner,)))
    completed = int(_scalar("SELECT COUNT(*) FROM venture_pilots WHERE owner=? AND status IN ('Complete','Converted')", (owner,)))
    hypotheses = int(_scalar("SELECT COUNT(*) FROM venture_hypotheses WHERE owner=?", (owner,)))
    evidence = int(_scalar("SELECT COUNT(*) FROM venture_evidence WHERE owner=?", (owner,)))
    value_rows = int(_scalar("SELECT COUNT(*) FROM venture_value_measurements WHERE owner=?", (owner,)))
    artifacts = int(_scalar("SELECT COUNT(*) FROM venture_artifacts WHERE owner=?", (owner,)))
    cases = int(_scalar("SELECT COUNT(*) FROM venture_case_studies WHERE owner=?", (owner,)))

    metrics = [
        ("Customers", customers),
        ("Active pilots", max(0, pilots - completed)),
        ("Completed pilots", completed),
        ("Hypotheses", hypotheses),
        ("Evidence", evidence),
        ("Value rows", value_rows),
        ("Artifacts", artifacts),
        ("Case studies", cases),
    ]
    cards = st.columns(4)
    for i, (label, value) in enumerate(metrics):
        cards[i % 4].metric(label, f"{value:,}")

    pipeline = pd.DataFrame(
        {
            "Proof stage": ["Customers", "Pilots", "Completed pilots", "Hypotheses", "Evidence", "Measured value", "Controlled artifacts", "Case studies"],
            "Records": [customers, pilots, completed, hypotheses, evidence, value_rows, artifacts, cases],
        }
    )
    _show_fig(
        px.bar(pipeline, x="Records", y="Proof stage", orientation="h", text="Records", range_x=[0, max(1, int(pipeline["Records"].max()))]),
        360,
        "Venture proof pipeline",
    )

    c1, c2 = st.columns(2)
    with c1:
        stages = _query("SELECT stage FROM venture_pilots WHERE owner=?", (owner,))
        if not stages.empty:
            stage_counts = stages["stage"].value_counts().reindex(PILOT_STAGES).fillna(0).reset_index()
            stage_counts.columns = ["Stage", "Pilots"]
            _show_fig(px.bar(stage_counts, x="Stage", y="Pilots", text="Pilots"), 300, "Pilot stage distribution")
    with c2:
        confidence = _query("SELECT confidence FROM venture_evidence WHERE owner=? AND confidence IS NOT NULL AND TRIM(confidence)<>''", (owner,))
        if not confidence.empty:
            confidence_counts = confidence["confidence"].value_counts().reindex(CONFIDENCE).fillna(0).reset_index()
            confidence_counts.columns = ["Confidence", "Evidence"]
            _show_fig(px.bar(confidence_counts, x="Confidence", y="Evidence", text="Evidence"), 300, "Evidence confidence mix")

    values = _query("SELECT * FROM venture_value_measurements WHERE owner=?", (owner,))
    summary = value_summary(values)
    if summary["mixed_currency"]:
        st.warning("Value evidence contains multiple currencies. Economic benefit, ROI and payback are intentionally withheld until the value set is currency-consistent.")
    elif summary["priced_rows"] > 0:
        st.metric(
            f"Measured annualized benefit · {summary['currency'] or 'currency'}",
            f"{summary['annualized_benefit']:,.2f}",
        )
        value_chart = values.copy()
        value_chart["Value"] = pd.to_numeric(value_chart["economic_value"], errors="coerce")
        value_chart = value_chart.dropna(subset=["Value"]).loc[value_chart["Value"] != 0].head(12)
        if not value_chart.empty:
            _show_fig(px.bar(value_chart, x="Value", y="metric", orientation="h", text="Value"), 330, "Measured economic value")

    actions: list[dict[str, str]] = []
    customer_actions = _query(
        "SELECT target_customer AS Record, next_action AS NextAction FROM venture_customers WHERE owner=? AND TRIM(COALESCE(next_action,''))<>''",
        (owner,),
    )
    pilot_actions = _query(
        "SELECT title AS Record, next_action AS NextAction FROM venture_pilots WHERE owner=? AND TRIM(COALESCE(next_action,''))<>''",
        (owner,),
    )
    for _, row in pd.concat([customer_actions, pilot_actions], ignore_index=True).head(8).iterrows():
        actions.append({"Record": str(row.get("Record", "")), "Next action": str(row.get("NextAction", ""))})
    if actions:
        st.markdown("#### Next-action queue")
        st.dataframe(pd.DataFrame(actions), use_container_width=True, hide_index=True)
    else:
        st.info("No next actions are recorded yet. Add a customer or pilot follow-up to make the operating queue actionable.")


def _render_customer(owner: str) -> None:
    st.markdown("### 👥 Customer & Stakeholder Hub")
    st.caption("Customer records capture the problem, workaround, process burden, buying path, objections, requested features, pilot status and source metadata.")
    df = _customer_df(owner)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        pain_plot = df[["target_customer", "pain_severity"]].copy()
        pain_plot["target_customer"] = pain_plot["target_customer"].fillna("Unnamed").astype(str)
        with c1:
            _show_fig(px.bar(pain_plot, x="target_customer", y="pain_severity", text="pain_severity"), 300, "Pain severity by stakeholder")
        scatter = df[["pain_severity", "current_process_time_hours"]].apply(pd.to_numeric, errors="coerce").dropna()
        with c2:
            if len(scatter) >= 2:
                _show_fig(px.scatter(scatter, x="current_process_time_hours", y="pain_severity"), 300, "Pain vs current process burden")
            else:
                st.info("Add at least two customer records with process time to activate the burden relationship chart.")
    options = ["➕ New customer"] + ([] if df.empty else [str(x) for x in df["customer_id"]])
    selected = st.selectbox("Customer record", options, key="venture_customer_select")
    existing = _customer_record(owner, None if selected.startswith("➕") else selected)
    with st.form("venture_customer_form"):
        a, b, c = st.columns(3)
        target = a.text_input("Target customer", value=str(existing.get("target_customer", "")))
        end_user = b.text_input("End user", value=str(existing.get("end_user", "")))
        beneficiary = c.text_input("Beneficiary", value=str(existing.get("beneficiary", "")))
        org = st.text_input("Adopting organization", value=str(existing.get("adopting_organization", "")))
        problem = st.text_area("Problem statement", value=str(existing.get("problem_statement", "")), height=80)
        workaround = st.text_area("Current workaround", value=str(existing.get("current_workaround", "")), height=65)
        interview = st.text_area("Interview notes / evidence", value=str(existing.get("interview_notes", "")), height=85)
        p1, p2, p3 = st.columns(3)
        pain = p1.number_input("Pain severity (0–10)", 0.0, 10.0, _safe_float(existing.get("pain_severity")), 0.5)
        frequency = p2.text_input("Pain frequency", value=str(existing.get("pain_frequency", "")))
        process_hours = p3.number_input("Current process time (hours)", 0.0, value=_safe_float(existing.get("current_process_time_hours")), step=0.5)
        p4, p5 = st.columns(2)
        process_cost = p4.number_input("Current process cost", 0.0, value=_safe_float(existing.get("current_process_cost")), step=10.0)
        error_burden = p5.text_input("Error burden", value=str(existing.get("error_burden", "")))
        buying = st.text_area("Buying / adoption process", value=str(existing.get("buying_process", "")), height=65)
        objections = st.text_area("Objections", value=str(existing.get("objections", "")), height=55)
        requested = st.text_area("Requested features", value=str(existing.get("requested_features", "")), height=55)
        q1, q2, q3 = st.columns(3)
        default_status = str(existing.get("pilot_status", "Active"))
        pilot_status = q1.selectbox("Pilot status", PILOT_STATUSES, index=PILOT_STATUSES.index(default_status) if default_status in PILOT_STATUSES else 0)
        next_action = q2.text_input("Next action", value=str(existing.get("next_action", "")))
        default_conf = str(existing.get("confidence", "Medium"))
        confidence = q3.selectbox("Confidence", CONFIDENCE, index=CONFIDENCE.index(default_conf) if default_conf in CONFIDENCE else 1)
        q4, q5 = st.columns(2)
        source_ref = q4.text_input("Source / interview reference", value=str(existing.get("source_ref", "")))
        source_date = q5.text_input("Source date", value=str(existing.get("source_date", "")))
        submitted = st.form_submit_button("💾 Save customer evidence", type="primary", use_container_width=True)
    if submitted:
        stamp, customer_id = _now(), str(existing.get("customer_id") or _id("CUS"))
        with _db() as conn:
            if existing:
                conn.execute(
                    """UPDATE venture_customers SET target_customer=?,end_user=?,beneficiary=?,adopting_organization=?,
                       problem_statement=?,current_workaround=?,interview_notes=?,pain_severity=?,pain_frequency=?,
                       current_process_time_hours=?,current_process_cost=?,error_burden=?,buying_process=?,objections=?,
                       requested_features=?,pilot_status=?,next_action=?,source_ref=?,source_date=?,confidence=?,updated_at=?
                       WHERE customer_id=? AND owner=?""",
                    (target,end_user,beneficiary,org,problem,workaround,interview,pain,frequency,process_hours,process_cost,error_burden,buying,objections,requested,pilot_status,next_action,source_ref,source_date,confidence,stamp,customer_id,owner),
                )
            else:
                conn.execute(
                    """INSERT INTO venture_customers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (customer_id,owner,target,end_user,beneficiary,org,problem,workaround,interview,pain,frequency,process_hours,process_cost,error_burden,buying,objections,requested,pilot_status,next_action,source_ref,source_date,confidence,stamp,stamp),
                )
            conn.commit()
        track_event(owner, "customer_saved", "Customer & Stakeholder Hub")
        _maybe_first_result(owner)
        st.success(f"Customer evidence saved · {customer_id}")
        st.rerun()


def _render_pilots(owner: str) -> None:
    st.markdown("### 🧪 Pilot Manager")
    st.caption("Discovery → Baseline → Pilot Setup → Deployment → Measurement → Customer Feedback → Decision")
    df = _pilot_df(owner)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        stage_counts = df["stage"].value_counts().reindex(PILOT_STAGES).fillna(0).reset_index()
        stage_counts.columns = ["Stage", "Pilots"]
        _show_fig(px.bar(stage_counts, x="Stage", y="Pilots", text="Pilots"), 300, "Pilot funnel by stage")
        status_counts = df["status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Pilots"]
        _show_fig(px.bar(status_counts, x="Status", y="Pilots", text="Pilots"), 300, "Pilot status")
    customers = _query("SELECT customer_id,target_customer,adopting_organization FROM venture_customers WHERE owner=? ORDER BY updated_at DESC", (owner,))
    customer_options = ["➕ Unlinked"] + ([] if customers.empty else [f"{r.customer_id} · {r.target_customer or r.adopting_organization or 'Customer'}" for r in customers.itertuples()])
    pilot_options = ["➕ New pilot"] + ([] if df.empty else list(df["pilot_id"].astype(str)))
    selected = st.selectbox("Pilot record", pilot_options, key="venture_pilot_select")
    existing = _pilot_record(owner, None if selected.startswith("➕") else selected)
    current_customer_id = str(existing.get("customer_id", "") or "")
    selected_customer_default = next((x for x in customer_options if x.startswith(current_customer_id)), customer_options[0])
    with st.form("venture_pilot_form"):
        p1, p2, p3 = st.columns(3)
        customer_label = p1.selectbox("Customer / stakeholder", customer_options, index=customer_options.index(selected_customer_default))
        title = p2.text_input("Pilot title", value=str(existing.get("title", "")))
        stg = str(existing.get("stage", "Discovery"))
        stage = p3.selectbox("Stage", PILOT_STAGES, index=PILOT_STAGES.index(stg) if stg in PILOT_STAGES else 0)
        stat = str(existing.get("status", "Active"))
        status = st.selectbox("Pilot status", PILOT_STATUSES, index=PILOT_STATUSES.index(stat) if stat in PILOT_STATUSES else 0)
        champion = st.text_input("Customer champion", value=str(existing.get("champion", "")))
        business_problem = st.text_area("Business problem", value=str(existing.get("business_problem", "")), height=70)
        baseline = st.text_area("Baseline definition / source", value=str(existing.get("baseline_summary", "")), height=70)
        setup = st.text_area("Pilot setup", value=str(existing.get("pilot_setup", "")), height=60)
        deployment = st.text_area("Deployment notes", value=str(existing.get("deployment_notes", "")), height=60)
        measurement = st.text_area("Measurement plan", value=str(existing.get("measurement_plan", "")), height=70)
        feedback = st.text_area("Customer feedback", value=str(existing.get("customer_feedback", "")), height=60)
        decision = st.text_area("Pilot decision", value=str(existing.get("decision_notes", "")), height=60)
        d1, d2, d3 = st.columns(3)
        start = d1.text_input("Start date", value=str(existing.get("start_date", "")))
        target = d2.text_input("Target date", value=str(existing.get("target_date", "")))
        next_action = d3.text_input("Next action", value=str(existing.get("next_action", "")))
        submitted = st.form_submit_button("💾 Save pilot", type="primary", use_container_width=True)
    if submitted:
        customer_id = "" if customer_label.startswith("➕") else customer_label.split(" · ", 1)[0]
        stamp, pilot_id = _now(), str(existing.get("pilot_id") or _id("PIL"))
        with _db() as conn:
            vals = (customer_id,title,stage,status,champion,business_problem,baseline,setup,deployment,measurement,feedback,decision,start,target,next_action,stamp)
            if existing:
                conn.execute(
                    """UPDATE venture_pilots SET customer_id=?,title=?,stage=?,status=?,champion=?,business_problem=?,
                       baseline_summary=?,pilot_setup=?,deployment_notes=?,measurement_plan=?,customer_feedback=?,
                       decision_notes=?,start_date=?,target_date=?,next_action=?,updated_at=?
                       WHERE pilot_id=? AND owner=?""",
                    vals + (pilot_id,owner),
                )
            else:
                conn.execute(
                    """INSERT INTO venture_pilots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pilot_id,owner)+vals[:-1]+(stamp,stamp),
                )
            conn.commit()
        track_event(owner, "pilot_saved", "Pilot Manager")
        _maybe_first_result(owner)
        st.success(f"Pilot saved · {pilot_id}")
        st.rerun()
    if selected and not selected.startswith("➕"):
        idx = PILOT_STAGES.index(str(existing.get("stage"))) if str(existing.get("stage")) in PILOT_STAGES else 0
        cols = st.columns(len(PILOT_STAGES))
        for i, (col, label) in enumerate(zip(cols, PILOT_STAGES)):
            symbol = "✓" if i < idx else "●" if i == idx else "○"
            col.markdown(f"<div style='text-align:center;border:1px solid #dbe4ef;border-radius:11px;padding:8px'><b>{symbol}</b><br><span style='font-size:10px'>{html.escape(label)}</span></div>", unsafe_allow_html=True)


def _render_hypothesis_evidence(owner: str) -> None:
    st.markdown("### 🔎 Hypothesis → Evidence")
    st.caption("Hypothesis → Metric → Baseline → Experiment → Result → Evidence → Decision.")
    hyp = _query("SELECT hypothesis_id,statement,metric,baseline,experiment,result,decision,status,confidence,source_ref,updated_at FROM venture_hypotheses WHERE owner=? ORDER BY updated_at DESC", (owner,))
    ev = _query("SELECT evidence_id,title,evidence_type,source,source_date,confidence,linked_object_type,linked_object_id,artifact_url,checksum,created_at FROM venture_evidence WHERE owner=? ORDER BY created_at DESC", (owner,))
    if not hyp.empty:
        st.dataframe(hyp, use_container_width=True, hide_index=True)
        status_counts = hyp["status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Hypotheses"]
        _show_fig(px.bar(status_counts, x="Status", y="Hypotheses", text="Hypotheses"), 280, "Hypothesis status")
        confidence_counts = hyp["confidence"].value_counts().reset_index()
        confidence_counts.columns = ["Confidence", "Hypotheses"]
        _show_fig(px.bar(confidence_counts, x="Confidence", y="Hypotheses", text="Hypotheses"), 280, "Hypothesis confidence")
    h1,h2=st.columns(2)
    with h1:
        with st.form("venture_hypothesis_form"):
            statement=st.text_area("Hypothesis")
            metric=st.text_input("Metric")
            baseline=st.text_input("Baseline")
            unit=st.text_input("Baseline unit")
            experiment=st.text_area("Experiment / method")
            result=st.text_area("Result")
            decision=st.text_area("Decision")
            status=st.selectbox("Status",["Proposed","Testing","Supported","Rejected","Inconclusive"])
            confidence=st.selectbox("Confidence",CONFIDENCE,index=1)
            source_ref=st.text_input("Source reference")
            submit_h=st.form_submit_button("💾 Save hypothesis",type="primary",use_container_width=True)
        if submit_h:
            if not statement.strip() or not metric.strip():
                st.error("Hypothesis and metric are required.")
            else:
                hid=_id("HYP")
                with _db() as conn:
                    conn.execute("INSERT INTO venture_hypotheses VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(hid,owner,statement,metric,baseline,unit,experiment,result,decision,status,confidence,source_ref,_now(),_now()))
                    conn.commit()
                track_event(owner,"hypothesis_saved","Hypothesis & Evidence")
                _maybe_first_result(owner)
                st.success(f"Hypothesis saved · {hid}")
                st.rerun()
    with h2:
        with st.form("venture_evidence_form"):
            title=st.text_input("Evidence title")
            evidence_type=st.selectbox("Evidence type",["Interview","Pilot Measurement","Experiment","Dataset","Customer Approval","Document","Calculation","Other"])
            source=st.text_input("Source / owner")
            source_date=st.text_input("Source date")
            confidence=st.selectbox("Evidence confidence",CONFIDENCE,index=1)
            description=st.text_area("What does this evidence prove?")
            link_type=st.selectbox("Linked object type",["Customer","Pilot","Hypothesis","Value","Artifact","Decision"])
            link_id=st.text_input("Linked object ID")
            artifact_url=st.text_input("Artifact / URL")
            content=st.text_area("Evidence note / excerpt",height=90)
            submit_e=st.form_submit_button("🔐 Preserve evidence record",type="primary",use_container_width=True)
        if submit_e:
            if not title.strip() or not source.strip():
                st.error("Evidence title and source are required.")
            else:
                content=content[:8000]; eid=_id("EVD")
                with _db() as conn:
                    conn.execute("INSERT INTO venture_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(eid,owner,title[:180],evidence_type,source[:300],source_date[:32],confidence,description[:1000],link_type,link_id[:120],artifact_url[:1000],content,_hash(content+source+source_date),_now()))
                    conn.commit()
                track_event(owner,"evidence_saved","Evidence Vault")
                _maybe_first_result(owner)
                st.success(f"Evidence preserved · {eid}")
                st.rerun()
    if not hyp.empty:
        claimed=int((hyp["source_ref"].fillna("").astype(str).str.strip()!="").sum())
        st.metric("Hypotheses with a source reference",f"{claimed}/{len(hyp)}")
    if not ev.empty:
        st.dataframe(ev,use_container_width=True,hide_index=True)


def _default_value_table() -> pd.DataFrame:
    """Return blank measurement fields so zero is never confused with an unmeasured value."""
    return pd.DataFrame([
        {
            "Metric": m,
            "Category": c,
            "Direction": d,
            "Unit": u,
            "Baseline": np.nan,
            "Post": np.nan,
            "Frequency / year": 1.0,
            "Unit value": np.nan,
            "Currency": "SAR",
            "Source ref": "",
            "Source date": "",
            "Confidence": "Medium",
            "Notes": "",
        }
        for m, c, d, u in VALUE_METRIC_TEMPLATES
    ])


def _render_value_evidence(owner: str) -> None:
    st.markdown("### 💰 Value Evidence Center")
    st.caption("Enter customer baseline and post-deployment measurements. The calculation engine does not impose a universal savings percentage.")
    pilots=_pilot_df(owner)
    options=["Workspace / not pilot-specific"] + ([] if pilots.empty else [f"{x.pilot_id} · {x.title}" for x in pilots.itertuples()])
    pilot_choice=st.selectbox("Attach value evidence to",options,key="venture_value_pilot")
    pilot_id="" if pilot_choice.startswith("Workspace") else pilot_choice.split(" · ",1)[0]
    existing=_query(
        """SELECT metric AS Metric,category AS Category,direction AS Direction,unit AS Unit,baseline_value AS Baseline,
                  post_value AS Post,frequency_per_year AS 'Frequency / year',unit_value AS 'Unit value',
                  currency AS Currency,source_ref AS 'Source ref',source_date AS 'Source date',confidence AS Confidence,notes AS Notes
           FROM venture_value_measurements WHERE owner=? AND pilot_id=? ORDER BY rowid""",(owner,pilot_id))
    edited=st.data_editor(existing if not existing.empty else _default_value_table(),num_rows="dynamic",use_container_width=True,hide_index=True,key="venture_value_editor_" + (pilot_id or "workspace"))
    implementation_cost=st.number_input("Implementation cost for this value set",min_value=0.0,value=0.0,step=100.0,key="venture_value_implementation_cost_" + (pilot_id or "workspace"))
    preview=[]
    for _,row in edited.iterrows():
        calc=value_calculation(row)
        preview.append({"Metric":row.get("Metric",""),"Delta":calc["delta"],"Annualized effect":calc["annualized_effect"],"Economic value":calc["economic_value"]})
    preview_df = pd.DataFrame(preview)
    if not preview_df.empty:
        st.markdown("#### Calculated impact")
        st.dataframe(preview_df,use_container_width=True,hide_index=True)
        chartable = preview_df[preview_df["Metric"].astype(str).str.strip()!=""].copy()
        if not chartable.empty:
            _show_fig(px.bar(chartable, x="Economic value", y="Metric", orientation="h", text_auto=".2f"), 340, "Annualized economic value by metric")
    norm=edited.rename(columns={"Baseline":"baseline_value","Post":"post_value","Frequency / year":"frequency_per_year","Unit value":"unit_value","Direction":"direction"}).copy()
    if not norm.empty:
        norm["implementation_cost"]=implementation_cost
        s=value_summary(norm)
        c1,c2,c3,c4,c5=st.columns(5)
        c1.metric("Measured rows",f"{s['measured_rows']:.0f}")
        c2.metric("Priced rows",f"{s['priced_rows']:.0f}")
        if s["mixed_currency"]:
            c3.metric("Annualized benefit", "N/A · mixed currency")
            c4.metric("Pilot ROI", "N/A")
            c5.metric("Payback", "N/A")
        else:
            currency_label = s["currency"] or "currency"
            c3.metric(f"Annualized benefit · {currency_label}", f"{s['annualized_benefit']:,.2f}")
            c4.metric("Pilot ROI", f"{s['roi_percent']:,.1f}%" if s["implementation_cost"] > 0 and s["annualized_benefit"] != 0 else "N/A")
            c5.metric("Payback", f"{s['payback_months']:,.1f} months" if s["payback_months"] else "N/A")
        valid_plot=norm.copy()
        valid_plot["baseline_value"]=pd.to_numeric(valid_plot["baseline_value"],errors="coerce")
        valid_plot["post_value"]=pd.to_numeric(valid_plot["post_value"],errors="coerce")
        valid_plot=valid_plot.dropna(subset=["baseline_value","post_value"])
        if not valid_plot.empty:
            melted=valid_plot[["Metric","baseline_value","post_value"]].melt(id_vars="Metric",var_name="Stage",value_name="Value")
            melted["Stage"]=melted["Stage"].map({"baseline_value":"Baseline","post_value":"Post"})
            _show_fig(px.bar(melted,x="Metric",y="Value",color="Stage",barmode="group"),360,"Baseline vs post-deployment")
        if s["implementation_cost"] > 0:
            wf=go.Figure(go.Waterfall(orientation="h",measure=["relative","total"],y=["Measured annualized benefit","Net value"],x=[s["annualized_benefit"],s["net_value"]],text=[f"{s['annualized_benefit']:,.0f}",f"{s['net_value']:,.0f}"],textposition="outside"))
            _show_fig(wf,300,"Value bridge")
    if st.button("💾 Save value evidence set",type="primary",use_container_width=True,key="venture_value_save"):
        with _db() as conn:
            conn.execute("DELETE FROM venture_value_measurements WHERE owner=? AND pilot_id=?",(owner,pilot_id))
            skipped=0
            for _,row in edited.iterrows():
                metric=str(row.get("Metric","")).strip()
                if not metric: continue
                if _optional_float(row.get("Baseline")) is None or _optional_float(row.get("Post")) is None:
                    skipped += 1
                    continue
                if not str(row.get("Source ref","")).strip():
                    skipped += 1
                    continue
                conn.execute(
                    """INSERT INTO venture_value_measurements VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (_id("VAL"),owner,pilot_id,metric[:150],str(row.get("Category",""))[:80],str(row.get("Direction","lower_is_better")),str(row.get("Unit",""))[:40],
                     _optional_float(row.get("Baseline")),_optional_float(row.get("Post")),_optional_float(row.get("Frequency / year")),
                     _optional_float(row.get("Unit value")),str(row.get("Currency","SAR"))[:8],implementation_cost,str(row.get("Source ref",""))[:300],
                     str(row.get("Source date",""))[:32],str(row.get("Confidence","Medium")),str(row.get("Notes",""))[:1000],_now(),_now())
                )
            conn.commit()
        track_event(owner,"value_evidence_saved","Value Evidence Center",details={"saved_rows": int(max(0, len(edited)-skipped)), "skipped_rows": int(skipped)})
        _maybe_first_result(owner)
        msg="Customer-specific value evidence saved."
        if skipped: msg += f" {skipped} incomplete rows were not stored because baseline/post and source reference are required."
        st.success(msg); st.rerun()
    st.markdown('<div class="venture-note">ROI = (verified annualized economic benefit − implementation cost) / implementation cost. Payback uses the same measured annualized benefit. Mixed currencies are blocked. Replace every input with pilot data before presenting ROI.</div>',unsafe_allow_html=True)


    st.markdown("#### 🧪 Error detection & rework evidence")
    quality=_query("SELECT quality_id,pilot_id,issues_detected,issues_confirmed,baseline_rework_hours,post_rework_hours,source_ref,source_date,confidence,notes,updated_at FROM venture_quality_metrics WHERE owner=? AND pilot_id=? ORDER BY updated_at DESC LIMIT 20",(owner,pilot_id))
    if not quality.empty:
        qrow=quality.iloc[0]
        qcalc=quality_evidence_calculation(qrow)
        qc1,qc2=st.columns(2)
        qc1.metric("Error Detection Rate",f"{qcalc['error_detection_rate_percent']:.1f}%" if qrow['issues_confirmed'] else "N/A")
        qc2.metric("Rework avoided",f"{qcalc['rework_avoided_hours']:.1f} h" if pd.notna(qrow['baseline_rework_hours']) and pd.notna(qrow['post_rework_hours']) else "N/A")
        qplot=pd.DataFrame({"Measure":["Issues detected","Issues confirmed"],"Value":[qrow['issues_detected'] or 0,qrow['issues_confirmed'] or 0]})
        _show_fig(px.bar(qplot,x="Measure",y="Value",text="Value"),280,"Data-quality issues detected vs ground truth")
        rqplot=pd.DataFrame({"Stage":["Baseline","Post"],"Hours":[qrow['baseline_rework_hours'],qrow['post_rework_hours']]})
        if rqplot['Hours'].notna().all(): _show_fig(px.bar(rqplot,x="Stage",y="Hours",text="Hours"),280,"Rework hours before vs after")
    else:
        st.info("Enter confirmed issue counts and rework hours to activate the controlled quality-value metrics.")
    with st.form("venture_quality_metrics_form"):
        q1,q2,q3=st.columns(3)
        issues_detected=q1.number_input("Issues detected before analysis",min_value=0.0,value=float(quality.iloc[0]['issues_detected']) if not quality.empty and pd.notna(quality.iloc[0]['issues_detected']) else 0.0,step=1.0)
        issues_confirmed=q2.number_input("Issues confirmed in ground truth",min_value=0.0,value=float(quality.iloc[0]['issues_confirmed']) if not quality.empty and pd.notna(quality.iloc[0]['issues_confirmed']) else 0.0,step=1.0)
        baseline_rework=q3.number_input("Baseline rework hours",min_value=0.0,value=float(quality.iloc[0]['baseline_rework_hours']) if not quality.empty and pd.notna(quality.iloc[0]['baseline_rework_hours']) else 0.0,step=0.5)
        post_rework=st.number_input("Post-deployment rework hours",min_value=0.0,value=float(quality.iloc[0]['post_rework_hours']) if not quality.empty and pd.notna(quality.iloc[0]['post_rework_hours']) else 0.0,step=0.5)
        qref,qdate,qconf=st.columns(3)
        q_source=qref.text_input("Quality evidence source reference",value=str(quality.iloc[0]['source_ref']) if not quality.empty else "")
        q_date=qdate.text_input("Quality evidence source date",value=str(quality.iloc[0]['source_date']) if not quality.empty else "")
        q_conf=qconf.selectbox("Quality evidence confidence",CONFIDENCE,index=CONFIDENCE.index(str(quality.iloc[0]['confidence'])) if not quality.empty and str(quality.iloc[0]['confidence']) in CONFIDENCE else 1)
        q_notes=st.text_area("Quality evidence notes",value=str(quality.iloc[0]['notes']) if not quality.empty else "",height=60)
        qsave=st.form_submit_button("💾 Save quality evidence",type="primary",use_container_width=True)
    if qsave:
        if not q_source.strip(): st.error("A source reference is required for quality evidence.")
        else:
            stamp=_now()
            with _db() as conn:
                conn.execute("DELETE FROM venture_quality_metrics WHERE owner=? AND pilot_id=?",(owner,pilot_id))
                conn.execute("INSERT INTO venture_quality_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(_id("QLT"),owner,pilot_id,issues_detected,issues_confirmed,baseline_rework,post_rework,q_source[:300],q_date[:32],q_conf,q_notes[:1200],stamp,stamp))
                conn.commit()
            track_event(owner,"quality_evidence_saved","Value Evidence Center",details={"pilot_id":pilot_id})
            st.success("Error-detection and rework evidence saved.")
            st.rerun()

def _artifact_df(owner: str) -> pd.DataFrame:
    return _query("SELECT artifact_id,category,title,version,source_url,source_date,confidence,checksum,updated_at FROM venture_artifacts WHERE owner=? ORDER BY category,title",(owner,))


def save_artifact(owner:str,category:str,title:str,content:str,source_url:str,source_date:str,confidence:str)->str:
    content=str(content)[:20000]; checksum=_hash(content); stamp=_now()
    with _db() as conn:
        row=conn.execute("SELECT artifact_id,version,content,source_url,source_date,confidence,checksum FROM venture_artifacts WHERE owner=? AND category=? AND title=?",(owner,category,title)).fetchone()
        if row:
            aid,version,old_content,old_url,old_date,old_conf,old_hash=row; new_version=int(version)+1
            conn.execute("INSERT INTO venture_artifact_versions VALUES(?,?,?,?,?,?,?,?,?)",(_id("VER"),aid,int(version),old_content,old_url,old_date,old_conf,old_hash,stamp))
            conn.execute("UPDATE venture_artifacts SET content=?,source_url=?,source_date=?,confidence=?,version=?,checksum=?,updated_at=? WHERE artifact_id=? AND owner=?",(content,source_url,source_date,confidence,new_version,checksum,stamp,aid,owner))
        else:
            aid=_id("ART")
            conn.execute("INSERT INTO venture_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(aid,owner,category,title[:180],content,source_url[:1000],source_date[:32],confidence,1,checksum,stamp,stamp))
        conn.commit()
    return aid


def _room_export(owner:str)->bytes:
    frames={
        "customers.csv":_query("SELECT * FROM venture_customers WHERE owner=?",(owner,)),
        "pilots.csv":_query("SELECT * FROM venture_pilots WHERE owner=?",(owner,)),
        "hypotheses.csv":_query("SELECT * FROM venture_hypotheses WHERE owner=?",(owner,)),
        "evidence.csv":_query("SELECT * FROM venture_evidence WHERE owner=?",(owner,)),
        "value_measurements.csv":_query("SELECT * FROM venture_value_measurements WHERE owner=?",(owner,)),
        "quality_metrics.csv":_query("SELECT * FROM venture_quality_metrics WHERE owner=?",(owner,)),
        "artifacts.csv":_artifact_df(owner),
        "market_claims.csv":_query("SELECT * FROM venture_market_claims WHERE owner=?",(owner,)),
        "case_studies.csv":_query("SELECT * FROM venture_case_studies WHERE owner=?",(owner,)),
        "business_model.csv":_query("SELECT * FROM venture_business_model WHERE owner=?",(owner,)),
    }
    manifest={"generated_at":_now(),"owner":owner,"evidence_policy":"Keep source/date/confidence metadata attached; DEMO data is synthetic.","artifact_categories":ARTIFACT_CATEGORIES}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        for name,frame in frames.items(): z.writestr(name,frame.to_csv(index=False).encode("utf-8"))
        detailed=_query("SELECT artifact_id,category,title,content,source_url,source_date,confidence,version,checksum,updated_at FROM venture_artifacts WHERE owner=? ORDER BY category,title",(owner,))
        versions=_query("SELECT * FROM venture_artifact_versions WHERE artifact_id IN (SELECT artifact_id FROM venture_artifacts WHERE owner=?) ORDER BY artifact_id,version",(owner,))
        z.writestr("artifact_content.json",json.dumps(detailed.to_dict("records"),indent=2,default=str).encode("utf-8"))
        z.writestr("artifact_versions.csv",versions.to_csv(index=False).encode("utf-8"))
        z.writestr("manifest.json",json.dumps(manifest,indent=2).encode("utf-8"))
    return buf.getvalue()


def _render_data_room(owner:str)->None:
    st.markdown("### 🗄️ Investor Data Room")
    st.caption("Product → Problem → Market → Customer Evidence → Pilots → ROI → Traction → Roadmap → Security → Financial Model")
    artifacts=_artifact_df(owner)
    if not artifacts.empty: st.dataframe(artifacts,use_container_width=True,hide_index=True)
    a,b=st.columns([1.2,2])
    with a:
        with st.form("venture_artifact_form"):
            category=st.selectbox("Artifact category",ARTIFACT_CATEGORIES)
            title=st.text_input("Artifact title")
            content=st.text_area("Artifact content / summary",height=180)
            source_url=st.text_input("Source URL / evidence link")
            source_date=st.text_input("Source date")
            confidence=st.selectbox("Confidence",CONFIDENCE,index=1)
            submit=st.form_submit_button("💾 Save controlled artifact",type="primary",use_container_width=True)
    with b:
        st.markdown("#### Room completeness")
        room=pd.DataFrame([{"Category":cat,"Artifacts":int((artifacts["category"]==cat).sum()) if not artifacts.empty else 0,"Status":"Recorded" if not artifacts.empty and (artifacts["category"]==cat).any() else "Missing"} for cat in ARTIFACT_CATEGORIES])
        st.dataframe(room,use_container_width=True,hide_index=True)
        room_plot=room.copy()
        room_plot["RecordedFlag"]=room_plot["Status"].map({"Recorded":1,"Missing":0})
        _show_fig(px.bar(room_plot,x="Category",y="RecordedFlag",text="Status"),320,"Investor room completeness")
        missing=room[room["Status"]=="Missing"]
        if not missing.empty:
            st.warning("Missing room categories: " + ", ".join(missing["Category"].tolist()))
    if submit:
        if not title.strip() or not content.strip(): st.error("Artifact category, title and content are required.")
        else:
            aid=save_artifact(owner,category,title,content,source_url,source_date,confidence)
            track_event(owner,"artifact_saved",category)
            _maybe_first_result(owner)
            st.success(f"Artifact saved · {aid}"); st.rerun()
    if not artifacts.empty:
        selected_artifact=st.selectbox("Artifact version history",["None"]+list(artifacts["artifact_id"].astype(str)),key="venture_artifact_history")
        if selected_artifact!="None":
            versions=_query("SELECT version,source_url,source_date,confidence,checksum,saved_at FROM venture_artifact_versions WHERE artifact_id=? ORDER BY version DESC",(selected_artifact,))
            if versions.empty: st.caption("Version 1 · initial artifact")
            else: st.dataframe(versions,use_container_width=True,hide_index=True)
    st.download_button("📦 Download Investor Data Room package",_room_export(owner),file_name="shoir_ie_investor_data_room.zip",mime="application/zip",type="primary",use_container_width=True,key="venture_room_export")


def _render_readiness(owner:str)->None:
    st.markdown("### 📈 Product-Market-Fit / Readiness Dashboard")
    st.caption("Evidence checklist, not a predictive score. Each area shows the concrete record required to support readiness.")
    customers=_query("SELECT * FROM venture_customers WHERE owner=? ORDER BY updated_at DESC",(owner,))
    pilots=_query("SELECT * FROM venture_pilots WHERE owner=? ORDER BY updated_at DESC",(owner,))
    evidence=_query("SELECT * FROM venture_evidence WHERE owner=? ORDER BY created_at DESC",(owner,))
    artifacts=_artifact_df(owner)
    pricing=_query("SELECT * FROM venture_business_model WHERE owner=?",(owner,))
    active_df=st.session_state.get("universal_active_dataset")
    data_ready=isinstance(active_df,pd.DataFrame) and not active_df.empty
    customer_problem=not customers.empty and customers["problem_statement"].fillna("").astype(str).str.strip().ne("").any()
    customer_interview=not customers.empty and customers["interview_notes"].fillna("").astype(str).str.strip().ne("").any()
    icp=not customers.empty and customers["target_customer"].fillna("").astype(str).str.strip().ne("") .any()
    buying=not customers.empty and customers["buying_process"].fillna("").astype(str).str.strip().ne("").any()
    pilot_baseline=not pilots.empty and pilots["baseline_summary"].fillna("").astype(str).str.strip().ne("").any()
    pilot_measurement=not pilots.empty and pilots["measurement_plan"].fillna("").astype(str).str.strip().ne("").any()
    deploy=not pilots.empty and pilots["stage"].isin(["Deployment","Measurement","Customer Feedback","Decision"]).any()
    complete=(not pilots.empty and pilots["status"].isin(["Complete","Converted"]).sum() >= 1)
    repeatable=(not pilots.empty and pilots["status"].isin(["Complete","Converted"]).sum() >= 2)
    security=not artifacts.empty and artifacts["category"].eq("Security").any()
    product=not artifacts.empty and artifacts["category"].eq("Product").any()
    evidence_source=not evidence.empty and evidence["source"].fillna("").astype(str).str.strip().ne("").any()
    evidence_date=not evidence.empty and evidence["source_date"].fillna("").astype(str).str.strip().ne("").any()
    wtp=evidence_source and not pricing.empty and buying
    feedback=not pilots.empty and pilots["customer_feedback"].fillna("").astype(str).str.strip().ne("").any()
    rows=[
        ("Problem validation",customer_problem and customer_interview and evidence_source,"Customer problem + interview evidence"),
        ("ICP definition",icp,"Target customer is explicitly recorded"),
        ("MVP completeness",product,"Product artifact is controlled in the Investor Room"),
        ("Data readiness",data_ready,"Active shared engineering dataset is available"),
        ("Deployment readiness",deploy,"Pilot has reached deployment or later"),
        ("Security readiness",security,"Security artifact is recorded"),
        ("Pilot readiness",pilot_baseline and pilot_measurement,"Baseline and measurement plan are preserved"),
        ("Customer evidence",evidence_source and evidence_date,"Evidence has source and date metadata"),
        ("Willingness-to-pay evidence",wtp,"Buying process + pricing hypothesis + sourced evidence"),
        ("Repeatability",repeatable,"At least two pilots are complete or converted"),
        ("Adoption readiness",complete and feedback,"Completed pilot with customer feedback"),
    ]
    frame=pd.DataFrame(rows,columns=["Readiness area","Supported","Evidence condition"])
    frame["Status"]=frame["Supported"].map({True:"✓ Supported",False:"⚠ Gap"})
    support_pct=float(frame["Supported"].mean()*100) if not frame.empty else 0.0
    c1,c2,c3=st.columns(3)
    c1.metric("Readiness areas supported",f"{int(frame['Supported'].sum())}/{len(frame)}")
    c2.metric("Evidence coverage",f"{support_pct:.0f}%")
    c3.metric("Repeatable pilots",f"{int(pilots['status'].isin(['Complete','Converted']).sum()) if not pilots.empty else 0}")
    st.dataframe(frame[["Readiness area","Status","Evidence condition"]],use_container_width=True,hide_index=True)
    plot=frame.copy(); plot["Coverage"]=plot["Supported"].astype(int)*100
    _show_fig(px.bar(plot.sort_values("Coverage"),x="Coverage",y="Readiness area",orientation="h",text="Status",range_x=[0,100]),430,"Evidence-based readiness coverage")
    gaps=frame.loc[~frame["Supported"],"Readiness area"].tolist()
    if gaps: st.info("Current evidence gaps: " + " · ".join(gaps[:7]))

def _render_traction(owner:str)->None:
    st.markdown("### 📊 Product & Traction Analytics")
    st.caption("Owner-scoped operational analytics. No customer-sensitive records are exposed in these charts.")
    since=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat(timespec="seconds")
    projects=_scalar("SELECT COUNT(*) FROM experience_projects WHERE owner=?",(owner,))
    datasets=_scalar("SELECT COUNT(*) FROM os160_datasets WHERE owner=?",(owner,))
    runs=_scalar("SELECT COUNT(*) FROM os160_runs WHERE owner=?",(owner,))
    scenarios=_scalar("SELECT COUNT(*) FROM os160_scenarios WHERE owner=?",(owner,))
    events=_query("SELECT event_type AS Event,feature AS Feature,COUNT(*) AS Events FROM venture_product_events WHERE owner=? GROUP BY event_type,feature ORDER BY Events DESC",(owner,))
    pilots=_scalar("SELECT COUNT(*) FROM venture_pilots WHERE owner=?",(owner,))
    converted=_scalar("SELECT COUNT(*) FROM venture_pilots WHERE owner=? AND status='Converted'",(owner,))
    conversion=converted/pilots*100 if pilots else 0
    cards=st.columns(7)
    metrics=[("Projects",projects),("Datasets",datasets),("Runs",runs),("Scenarios",scenarios),("Tracked events",float(events["Events"].sum()) if not events.empty else 0),("Pilots",pilots),("Pilot conversion",conversion)]
    for i,(label,val) in enumerate(metrics):
        cards[i].metric(label,f"{val:.1f}%" if label=="Pilot conversion" else f"{val:,.0f}")
    if not events.empty:
        _show_fig(px.bar(events.head(12),x="Events",y="Feature",color="Event",orientation="h",text="Events"),390,"Tracked feature adoption")
        daily=_query("SELECT substr(created_at,1,10) AS Day,COUNT(*) AS Events FROM venture_product_events WHERE owner=? AND created_at>=? GROUP BY Day ORDER BY Day",(owner,since))
        if not daily.empty:
            _show_fig(px.line(daily,x="Day",y="Events",markers=True),300,"Venture activity · last 30 days")
    ttfr=_query("SELECT details_json FROM venture_product_events WHERE owner=? AND event_type='first_result' ORDER BY created_at DESC LIMIT 200",(owner,))
    seconds=[]
    for raw in ttfr.get("details_json",pd.Series(dtype=str)).tolist():
        try: seconds.append(float(json.loads(raw).get("time_to_first_result_seconds",0)))
        except Exception: pass
    if seconds: st.metric("Time to first result · tracked sessions",f"{np.mean(seconds):.1f} s")
    st.caption("Platform objects are counted only where their tables expose owner identifiers; Venture events are explicitly product-analytics records.")

def _demo_data()->dict[str,Any]:
    rng=np.random.default_rng(2026); n=24
    products=[f"SKU-{x:03d}" for x in range(1,7)]; departments=["Receiving","Machining","Assembly","Pack"]
    raw=pd.DataFrame({"Order":np.arange(1,n+1),"SKU":[products[i%6] for i in range(n)],"Department":[departments[i%4] for i in range(n)],"Demand":rng.integers(70,180,n),"Cycle Time (min)":np.round(rng.uniform(2.2,7.8,n),2),"Distance (m)":rng.integers(20,180,n),"Defects":rng.integers(0,5,n)})
    raw.loc[3,"Demand"]=np.nan; raw=pd.concat([raw,raw.iloc[[5]]],ignore_index=True)
    quality={"rows":len(raw),"missing_cells":int(raw.isna().sum().sum()),"duplicate_rows":int(raw.duplicated().sum())}
    clean=raw.fillna({"Demand":raw["Demand"].median()}).drop_duplicates().reset_index(drop=True)
    flow=pd.DataFrame({"From":["Receiving","Machining","Assembly"],"To":["Machining","Assembly","Pack"],"Flow units / day":[520,480,455],"Distance m":[95,65,42]})
    scenarios=pd.DataFrame([{"Scenario":"Baseline","Throughput units/day":455,"Travel distance m/day":2020,"Planning hours":8},{"Scenario":"Scenario A","Throughput units/day":482,"Travel distance m/day":1760,"Planning hours":5},{"Scenario":"Scenario B","Throughput units/day":493,"Travel distance m/day":1635,"Planning hours":4}])
    roi={"Baseline hours / study":8.0,"Shoir-IE hours / study":3.0,"Studies / year":50.0,"Loaded labor cost / hour":50.0}
    roi["Hours saved / study"]=roi["Baseline hours / study"]-roi["Shoir-IE hours / study"]
    roi["Capacity released / year"]=roi["Hours saved / study"]*roi["Studies / year"]
    roi["Illustrative capacity value / year"]=roi["Capacity released / year"]*roi["Loaded labor cost / hour"]
    return {"raw":raw,"quality":quality,"clean":clean,"flow":flow,"scenarios":scenarios,"roi":roi}


def _demo_report(data:dict[str,Any])->bytes:
    q=data["quality"]; r=data["roi"]
    lines=[
        "# Shoir-IE Executive Demo Report","",
        "Mode: DEMO / SYNTHETIC · fixed seed 2026","",
        "## Industrial question","Can a connected workflow reduce planning and analysis friction while preserving a reproducible evidence trail?","",
        "## Evidence chain","Raw Excel → Data Quality → Industrial Workbook → Facility / Flow → Engineering Analysis → Scenario Comparison → Decision → Value → Executive output","",
        "## Data quality",f"- Source rows: {q['rows']}",f"- Missing cells detected: {q['missing_cells']}",f"- Duplicate rows detected: {q['duplicate_rows']}","",
        "## Scenario comparison",data["scenarios"].to_csv(index=False),"",
        "## Illustrative value calculation",
        f"- Baseline effort: {r['Baseline hours / study']:.1f} h/study",
        f"- Shoir-IE effort: {r['Shoir-IE hours / study']:.1f} h/study",
        f"- Illustrative studies/year: {r['Studies / year']:.0f}",
        f"- Illustrative loaded labor cost: USD {r['Loaded labor cost / hour']:.0f}/h",
        f"- Released analyst capacity: {r['Capacity released / year']:.1f} h/year",
        f"- Illustrative capacity value: USD {r['Illustrative capacity value / year']:.2f}/year","",
        "These values are synthetic demonstration values and are not Shoir-IE performance claims.",
    ]
    return "\n".join(lines).encode("utf-8")


def _render_demo(owner:str)->None:
    st.markdown("### 🎬 End-to-End Demo / Story Mode")
    st.caption("Deterministic, synthetic and presentation-safe. No customer data is used.")
    if not st.session_state.get("venture_demo_viewed"):
        track_event(owner,"demo_viewed","End-to-End Demo Mode")
        st.session_state["venture_demo_viewed"]=True
    data=_demo_data()
    st.markdown("#### 7-minute presenter controller")
    story_labels = [f"{i+1}. {title} · {timebox}" for i, (timebox, title, _) in enumerate(DEMO_STORY)]
    step_index = st.selectbox("Demo step", range(len(DEMO_STORY)), format_func=lambda i: story_labels[i], key="venture_demo_step")
    timebox, title, narrative = DEMO_STORY[step_index]
    st.progress((step_index + 1) / len(DEMO_STORY))
    st.info(f"**{timebox} · {title}**  
{narrative}")
    if st.button("🚀 Load deterministic demo into Shoir-IE", type="primary", use_container_width=True, key="venture_demo_load"):
        st.session_state["universal_active_dataset"] = data["clean"].copy()
        st.session_state["industrial_workbook_current_df"] = data["clean"].copy()
        st.session_state["copilot_workbook"] = {
            "DEMO_RAW": data["raw"].copy(),
            "DEMO_CLEAN": data["clean"].copy(),
            "DEMO_FLOW": data["flow"].copy(),
            "DEMO_SCENARIOS": data["scenarios"].copy(),
        }
        st.session_state["shoir_data_status"] = "DEMO"
        st.session_state["shoir_data_source"] = "Deterministic Venture Demo · seed 2026"
        st.session_state["shoir_data_version"] = "demo-2026"
        track_event(owner, "demo_loaded", "End-to-End Demo Mode", details={"seed": 2026, "rows": int(len(data["clean"]))})
        st.success("Deterministic demo is loaded into the shared Shoir-IE workspace. Open Industrial Workbook next to continue the story.")
    tabs=st.tabs(["Raw Excel","Data Quality","Industrial Workbook","Facility / Flow","Engineering","Scenario","ROI / Report"])
    with tabs[0]: st.dataframe(data["raw"],use_container_width=True,hide_index=True)
    with tabs[1]:
        q=data["quality"]; c=st.columns(3); c[0].metric("Rows",q["rows"]); c[1].metric("Missing cells",q["missing_cells"]); c[2].metric("Duplicate rows",q["duplicate_rows"])
        st.dataframe(data["clean"],use_container_width=True,hide_index=True); st.success("Synthetic clean/activated dataset prepared.")
    with tabs[2]:
        st.markdown("**Inputs | Data | Calculations | KPIs | Simulation | Optimization | Scenarios | Decisions | Dashboard**")
        st.dataframe(data["clean"].head(12),use_container_width=True,hide_index=True)
    with tabs[3]:
        st.dataframe(data["flow"],use_container_width=True,hide_index=True)
        sankey=go.Figure(go.Sankey(node=dict(label=["Receiving","Machining","Assembly","Pack"]),link=dict(source=[0,1,2],target=[1,2,3],value=data["flow"]["Flow units / day"].tolist())))
        _show_fig(sankey,330,"Synthetic material-flow path")
        st.caption("DEMO flow only · this is not a customer facility map.")
    with tabs[4]:
        st.write("Focused question: how does a facility/flow alternative change throughput, travel distance and planning effort?")
        st.dataframe(data["scenarios"].iloc[[0,2]],use_container_width=True,hide_index=True)
    with tabs[5]:
        st.dataframe(data["scenarios"],use_container_width=True,hide_index=True)
        melted=data["scenarios"].melt(id_vars="Scenario",var_name="KPI",value_name="Value")
        _show_fig(px.bar(melted,x="Scenario",y="Value",color="KPI",barmode="group"),360,"Scenario stress test")
        deltas=data["scenarios"].copy()
        base=deltas.iloc[0]
        delta_frame=pd.DataFrame({"KPI":["Throughput","Travel distance","Planning hours"],"Delta":[deltas.iloc[-1]["Throughput units/day"]-base["Throughput units/day"],deltas.iloc[-1]["Travel distance m/day"]-base["Travel distance m/day"],deltas.iloc[-1]["Planning hours"]-base["Planning hours"]]})
        _show_fig(px.bar(delta_frame,x="KPI",y="Delta",text="Delta"),300,"Scenario B delta vs baseline")
        if not st.session_state.get("venture_demo_scenario_recorded"):
            track_event(owner,"scenario_compared","End-to-End Demo Mode")
            st.session_state["venture_demo_scenario_recorded"]=True
    with tabs[6]:
        r=data["roi"]; c=st.columns(4)
        c[0].metric("Hours saved / study",f"{r['Hours saved / study']:.1f}")
        c[1].metric("Capacity released",f"{r['Capacity released / year']:.0f} h/year")
        c[2].metric("Illustrative value",f"USD {r['Illustrative capacity value / year']:,.0f}/yr")
        c[3].metric("Mode","DEMO")
        if st.download_button("📄 Export deterministic executive demo report",_demo_report(data),file_name="shoir_ie_executive_demo_report.md",mime="text/markdown",type="primary",use_container_width=True,key="venture_demo_report"):
            track_event(owner,"report_exported","End-to-End Demo Mode")


def _render_market(owner:str)->None:
    st.markdown("### 🌐 Market & Competitive Intelligence")
    st.caption("Build a sourced map of competitors, substitutes, spreadsheet alternatives, build-vs-buy choices and pricing signals.")
    df=_query("SELECT claim_id,competitor_or_alternative,claim_type,claim,source_url,source_date,confidence,notes,updated_at FROM venture_market_claims WHERE owner=? ORDER BY updated_at DESC",(owner,))
    if not df.empty: st.dataframe(df,use_container_width=True,hide_index=True)
    with st.form("venture_market_form"):
        competitor=st.text_input("Competitor / alternative")
        claim_type=st.selectbox("Type",["Competitor","Substitute workflow","Spreadsheet","Build vs Buy","Pricing signal","Market evidence","Customer alternative"])
        claim=st.text_area("Documented claim"); source_url=st.text_input("Source URL"); source_date=st.text_input("Source date")
        confidence=st.selectbox("Confidence",CONFIDENCE,index=1); notes=st.text_area("Notes / caveat")
        submitted=st.form_submit_button("💾 Save market evidence",type="primary",use_container_width=True)
    if submitted:
        if not claim.strip(): st.error("A documented claim is required.")
        else:
            cid=_id("MKT")
            with _db() as conn:
                conn.execute("INSERT INTO venture_market_claims VALUES(?,?,?,?,?,?,?,?,?,?,?)",(cid,owner,competitor,claim_type,claim[:1200],source_url[:1000],source_date[:32],confidence,notes[:1200],_now(),_now())); conn.commit()
            track_event(owner,"market_claim_saved","Market & Competitive Intelligence"); _maybe_first_result(owner); st.success(f"Market evidence saved · {cid}"); st.rerun()


def _render_case_study(owner:str)->None:
    st.markdown("### 📝 Case Study Studio")
    st.caption("Case studies are gated on a completed/converted pilot, preserved baseline, evidence and measured value.")
    pilots=_pilot_df(owner)
    if pilots.empty: st.info("Create a pilot first."); return
    selected=st.selectbox("Completed pilot",list(pilots["pilot_id"].astype(str)),key="venture_case_pilot")
    pilot=_pilot_record(owner,selected)
    evidence=_query("SELECT evidence_id,title,evidence_type,source,source_date,confidence FROM venture_evidence WHERE owner=? AND linked_object_type='Pilot' AND linked_object_id=?",(owner,selected))
    values=_query("SELECT * FROM venture_value_measurements WHERE owner=? AND pilot_id=?",(owner,selected))
    summary=value_summary(values)
    checks=[
        ("Pilot completed / converted",str(pilot.get("status")) in {"Complete","Converted"}),
        ("Baseline preserved",bool(str(pilot.get("baseline_summary","")).strip())),
        ("Evidence preserved",not evidence.empty),
        ("Measured value present",summary["measured_rows"] > 0),
        ("Economic value basis present",summary["priced_rows"] > 0),
    ]
    check_df=pd.DataFrame(checks,columns=["Requirement","Pass"]); check_df["Pass"]=check_df["Pass"].map(lambda x:"✓ PASS" if x else "⚠ MISSING"); st.dataframe(check_df,use_container_width=True,hide_index=True)
    evidence_conf=evidence["confidence"].value_counts().reset_index() if not evidence.empty else pd.DataFrame()
    if not evidence_conf.empty:
        evidence_conf.columns=["Confidence","Evidence"]
        _show_fig(px.bar(evidence_conf,x="Confidence",y="Evidence",text="Evidence"),280,"Case-study evidence confidence")
    value_valid=values.copy()
    value_valid["Baseline"]=pd.to_numeric(value_valid["baseline_value"],errors="coerce")
    value_valid["Post"]=pd.to_numeric(value_valid["post_value"],errors="coerce")
    value_valid=value_valid.dropna(subset=["Baseline","Post"])
    if not value_valid.empty:
        case_chart=value_valid[["metric","Baseline","Post"]].head(12).melt(id_vars="metric",var_name="Stage",value_name="Value")
        _show_fig(px.bar(case_chart,x="metric",y="Value",color="Stage",barmode="group"),330,"Case-study measured change")
    if any(x is False for _,x in checks): st.warning("The pilot is not yet eligible for a case study."); return
    customer=_customer_record(owner,str(pilot.get("customer_id","")))
    quote=st.text_area("Customer quote / approval text (optional; enter only approved wording)")
    title=st.text_input("Case study title",value=f"{pilot.get('title','Industrial Pilot')} · Proof of Value")
    content=f"""# {title}

## Customer / context
- Target customer: {customer.get('target_customer','')}
- Adopting organization: {customer.get('adopting_organization','')}

## Problem
{pilot.get('business_problem','')}

## Baseline
{pilot.get('baseline_summary','')}

## Intervention
{pilot.get('pilot_setup','')}
{pilot.get('deployment_notes','')}

## Measurement
{pilot.get('measurement_plan','')}

## Result / customer feedback
{pilot.get('customer_feedback','')}

## Value evidence
- Annualized measured economic benefit: {summary.get('annualized_benefit',0):,.2f}
- Implementation cost: {summary.get('implementation_cost',0):,.2f}
- Net value: {summary.get('net_value',0):,.2f}
- ROI: {summary.get('roi_percent',0):,.1f}%
- Payback: {summary.get('payback_months',0):,.1f} months

## Approved customer wording
{quote}

## Evidence rule
Generated only after baseline, evidence and measured value records are preserved in Shoir-IE.
"""
    if st.button("✅ Generate proof package",type="primary",use_container_width=True,key="venture_case_generate"):
        cid=_id("CASE")
        with _db() as conn:
            conn.execute("INSERT INTO venture_case_studies VALUES(?,?,?,?,?,?,?)",(cid,owner,selected,title[:180],content,0,_now())); conn.commit()
        artifact_id=save_artifact(owner,"Customer Evidence",title,content,"",_now(),"Medium")
        track_event(owner,"case_study_generated","Case Study Studio",details={"case_id":cid,"artifact_id":artifact_id,"pilot_id":selected})
        _maybe_first_result(owner)
        st.success(f"Case study package prepared · {cid} · Investor Room artifact {artifact_id}")
    st.download_button("📄 Download case study draft",content.encode("utf-8"),file_name="shoir_ie_case_study.md",mime="text/markdown",use_container_width=True,key="venture_case_download")


def _render_business_model(owner:str)->None:
    st.markdown("### 💳 Business Model + Pricing")
    st.caption("Pricing is stored as a hypothesis with evidence requirements; it is not treated as willingness-to-pay proof.")
    df=_query("SELECT offering,target_segment,billing_model,price,currency,sales_motion,evidence_required,notes,updated_at FROM venture_business_model WHERE owner=? ORDER BY offering",(owner,))
    if not df.empty:
        st.dataframe(df,use_container_width=True,hide_index=True)
        price_plot=df[["offering","price","currency"]].copy()
        price_plot["price"]=pd.to_numeric(price_plot["price"],errors="coerce").fillna(0)
        _show_fig(px.bar(price_plot,x="offering",y="price",text="price",facet_col="currency"),320,"Pricing hypotheses")
    with st.form("venture_business_model_form"):
        offering=st.text_input("Offering"); target=st.text_input("Target segment")
        billing=st.selectbox("Billing model",["Pilot","Monthly SaaS","Annual SaaS","Enterprise","Professional Services","University / Research"])
        price=st.number_input("Price hypothesis",min_value=0.0,value=0.0,step=100.0); currency=st.selectbox("Currency",["SAR","USD","EUR"])
        motion=st.text_input("Sales motion",value="Pilot → Platform"); evidence_required=st.text_input("Evidence needed to validate pricing"); notes=st.text_area("Notes")
        submit=st.form_submit_button("💾 Save pricing hypothesis",type="primary",use_container_width=True)
    if submit:
        if not offering.strip(): st.error("Offering is required.")
        else:
            with _db() as conn:
                conn.execute(
                    """INSERT INTO venture_business_model VALUES(?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(owner,offering) DO UPDATE SET target_segment=excluded.target_segment,
                       billing_model=excluded.billing_model,price=excluded.price,currency=excluded.currency,
                       sales_motion=excluded.sales_motion,evidence_required=excluded.evidence_required,
                       notes=excluded.notes,updated_at=excluded.updated_at""",
                    (_id("BM"),owner,offering[:180],target[:300],billing,price,currency,motion[:500],evidence_required[:700],notes[:1200],_now()),
                ); conn.commit()
            track_event(owner,"pricing_hypothesis_saved","Business Model + Pricing"); _maybe_first_result(owner); st.success("Pricing hypothesis saved.")


def render_venture_studio(tier:str,username:str,current_module:str="Venture Studio")->None:
    del tier,current_module
    ensure_venture_db(); owner=str(username or "unknown")
    if "venture_session_started_at" not in st.session_state:
        st.session_state["venture_session_started_at"]=_now(); track_event(owner,"workspace_opened","Venture Studio")
    _render_header(owner)
    tabs=st.tabs(["🧭 Overview","👥 Customer","🧪 Pilots","🔎 Hypothesis → Evidence","💰 Value & ROI","🗄️ Investor Room","📈 Readiness","📊 Traction","🎬 Demo Mode","🌐 Market Intel","📝 Case Study","💳 Business Model"])
    with tabs[0]:
        _render_overview(owner)
    for tab,renderer in zip(tabs[1:],[_render_customer,_render_pilots,_render_hypothesis_evidence,_render_value_evidence,_render_data_room,_render_readiness,_render_traction,_render_demo,_render_market,_render_case_study,_render_business_model]):
        with tab: renderer(owner)
