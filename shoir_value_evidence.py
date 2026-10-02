"""Shoir-IE Value Evidence Engine.

Cross-cutting value layer:
- task-specific reference time baselines
- customer-calibrated time savings
- annual capacity released
- financial value bridge
- ROI / payback
- evidence status and export
"""
from __future__ import annotations

import hashlib
import html
import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = "enterprise_full_workspace.db"

# Reference planning benchmarks, not claimed industry averages.
_TASK_PROFILES = [
    ("Excel Data Cleaning & Import", 180, 15, "Clean, profile, repair and validate an operational workbook."),
    ("Industrial Workbook", 150, 10, "Build an engineering workbook from inputs through decisions."),
    ("Facility Layout & Warehousing", 300, 20, "Evaluate layout, storage, flow and department relationships."),
    ("Production Planning & Control", 240, 15, "Build a production plan, MRP view and schedule."),
    ("Scheduling", 240, 15, "Construct and compare feasible production schedules."),
    ("MILP Solvers", 240, 10, "Formulate and solve an industrial optimization model."),
    ("Inventory", 150, 8, "Analyze replenishment, stock levels and inventory policies."),
    ("Quality", 210, 12, "Analyze quality, SPC, defects, root causes or capability."),
    ("Simulation", 300, 15, "Build scenarios, run simulation and compare operating states."),
    ("Monte Carlo", 300, 15, "Model uncertainty and quantify risk across scenarios."),
    ("Predictive Maintenance", 180, 10, "Assess asset health, failure exposure and maintenance priorities."),
    ("Sustainability", 240, 12, "Quantify energy, carbon or resource-efficiency opportunities."),
    ("Carbon", 240, 12, "Build a carbon footprint and evaluate reduction scenarios."),
    ("Human Factors", 180, 10, "Evaluate ergonomics, workload and human-system performance."),
    ("Geospatial", 210, 12, "Analyze facility, transport and network geography."),
    ("Engineering Economics", 180, 10, "Evaluate economic trade-offs, investment and payback."),
    ("Research", 480, 30, "Run a research-grade engineering analysis with reproducible evidence."),
    ("Statistics", 240, 15, "Perform statistical testing, regression or experimental analysis."),
    ("Venture Studio", 180, 10, "Move from customer problem to pilot evidence and value case."),
    ("AI Copilot", 120, 5, "Plan and accelerate a multi-step engineering workflow."),
    ("Default", 120, 10, "Complete the selected engineering workflow."),
]

_METRICS = [
    ("Engineering hours", "Time", "lower_is_better", "hours"),
    ("Planning-cycle time", "Time", "lower_is_better", "hours"),
    ("Scenario turnaround", "Time", "lower_is_better", "hours"),
    ("Report-production time", "Time", "lower_is_better", "hours"),
    ("Data-quality defects", "Quality", "lower_is_better", "defects"),
    ("Rework cycles", "Quality", "lower_is_better", "cycles"),
    ("Inventory impact", "Inventory", "lower_is_better", "SAR"),
    ("Transport distance", "Logistics", "lower_is_better", "km"),
    ("Transport cost", "Logistics", "lower_is_better", "SAR"),
    ("Scrap & rework value", "Quality", "lower_is_better", "SAR"),
    ("Downtime exposure", "Operations", "lower_is_better", "SAR"),
    ("Energy consumption", "Sustainability", "lower_is_better", "kWh"),
    ("Carbon impact", "Sustainability", "lower_is_better", "kgCO2e"),
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shoir_value_task_baselines (
    owner TEXT NOT NULL,
    module TEXT NOT NULL,
    task TEXT NOT NULL,
    baseline_minutes REAL NOT NULL,
    shoir_minutes REAL NOT NULL,
    studies_per_year REAL NOT NULL DEFAULT 1,
    hourly_rate REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'SAR',
    source TEXT NOT NULL DEFAULT 'Reference planning benchmark',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(owner, module)
);
CREATE TABLE IF NOT EXISTS shoir_value_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    module TEXT NOT NULL,
    task TEXT NOT NULL,
    baseline_minutes REAL NOT NULL,
    shoir_minutes REAL NOT NULL,
    hours_saved REAL NOT NULL,
    annual_capacity_hours REAL NOT NULL,
    annual_time_value REAL NOT NULL,
    currency TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shoir_value_financial_bridges (
    bridge_id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    module TEXT NOT NULL,
    baseline_cost REAL NOT NULL,
    post_cost REAL NOT NULL,
    implementation_cost REAL NOT NULL,
    verified_economic_benefit REAL NOT NULL,
    frequency_per_year REAL NOT NULL,
    annualized_operational_benefit REAL NOT NULL,
    annual_net_benefit REAL NOT NULL,
    roi_percent REAL NOT NULL,
    payback_months REAL,
    currency TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")[:70]

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default

def ensure_value_evidence_db() -> None:
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            for statement in _SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.commit()
    except Exception:
        pass

def task_profile(module: str) -> dict[str, Any]:
    name = str(module or "Default").strip()
    lower = name.casefold()
    exact = next((p for p in _TASK_PROFILES if p[0].casefold() == lower), None)
    if exact:
        label, baseline, shoir, purpose = exact
        return {"task": label, "baseline_minutes": baseline, "shoir_minutes": shoir, "purpose": purpose}
    keyword_map = [
        (("layout", "warehouse", "facility"), "Facility Layout & Warehousing"),
        (("schedule", "planning", "ppc"), "Production Planning & Control"),
        (("inventory", "stock"), "Inventory"),
        (("quality", "spc", "fmea", "defect"), "Quality"),
        (("simulation", "digital twin"), "Simulation"),
        (("monte carlo", "uncertainty"), "Monte Carlo"),
        (("maintenance", "asset health", "reliability"), "Predictive Maintenance"),
        (("sustainability", "energy", "green"), "Sustainability"),
        (("carbon", "emissions"), "Carbon"),
        (("ergonomic", "human factor"), "Human Factors"),
        (("geospatial", "network", "transport"), "Geospatial"),
        (("economics", "finance", "capex"), "Engineering Economics"),
        (("research", "hypothesis", "paper", "experiment"), "Research"),
        (("statistics", "regression", "doe"), "Statistics"),
        (("venture", "pilot", "customer", "investor"), "Venture Studio"),
        (("copilot", "agent"), "AI Copilot"),
        (("milp", "optimization", "solver", "routing"), "MILP Solvers"),
        (("excel", "data cleaning", "import"), "Excel Data Cleaning & Import"),
        (("workbook",), "Industrial Workbook"),
    ]
    for keys, label in keyword_map:
        if any(k in lower for k in keys):
            p = next(x for x in _TASK_PROFILES if x[0] == label)
            return {"task": p[0], "baseline_minutes": p[1], "shoir_minutes": p[2], "purpose": p[3]}
    p = _TASK_PROFILES[-1]
    return {"task": p[0], "baseline_minutes": p[1], "shoir_minutes": p[2], "purpose": p[3]}

def _saved_baseline(owner: str, module: str) -> dict[str, Any] | None:
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            row = conn.execute(
                "SELECT task,baseline_minutes,shoir_minutes,studies_per_year,hourly_rate,currency,source FROM shoir_value_task_baselines WHERE owner=? AND module=?",
                (str(owner), str(module)),
            ).fetchone()
        if row:
            return {"task": row[0], "baseline_minutes": row[1], "shoir_minutes": row[2], "studies_per_year": row[3], "hourly_rate": row[4], "currency": row[5], "source": row[6]}
    except Exception:
        pass
    return None

def calculate_time_value(baseline_minutes: float, shoir_minutes: float, studies_per_year: float = 1.0, hourly_rate: float = 0.0) -> dict[str, float]:
    baseline_h = _safe_float(baseline_minutes) / 60.0
    shoir_h = _safe_float(shoir_minutes) / 60.0
    frequency = max(0.0, _safe_float(studies_per_year, 1.0))
    saved_h = baseline_h - shoir_h
    annual_h = saved_h * frequency
    annual_value = annual_h * max(0.0, _safe_float(hourly_rate))
    return {"baseline_hours": baseline_h, "shoir_hours": shoir_h, "hours_saved": saved_h, "annual_capacity_hours": annual_h, "annual_time_value": annual_value}

def calculate_financial_bridge(baseline_cost: float, post_cost: float, implementation_cost: float, frequency_per_year: float = 1.0) -> dict[str, float | None]:
    baseline = max(0.0, _safe_float(baseline_cost))
    post = max(0.0, _safe_float(post_cost))
    implementation = max(0.0, _safe_float(implementation_cost))
    frequency = max(0.0, _safe_float(frequency_per_year, 1.0))
    verified_period = baseline - post - implementation
    operational_delta = baseline - post
    annualized_operational = operational_delta * frequency
    annual_net = annualized_operational - implementation
    roi = (annual_net / implementation * 100.0) if implementation > 0 else None
    payback = (implementation / (annualized_operational / 12.0)) if annualized_operational > 0 and implementation > 0 else None
    return {"verified_period_benefit": verified_period, "annualized_operational_benefit": annualized_operational, "annual_net_benefit": annual_net, "roi_percent": roi, "payback_months": payback}

def record_time_snapshot(owner: str, module: str, task: str, values: dict[str, Any], source: str) -> str:
    snapshot_id = "VE-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + hashlib.sha256(f"{owner}|{module}|{task}|{_now()}".encode("utf-8")).hexdigest()[:10].upper()
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute(
            "INSERT INTO shoir_value_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (snapshot_id, str(owner), str(module), str(task), values["baseline_hours"] * 60.0, values["shoir_hours"] * 60.0, values["hours_saved"], values["annual_capacity_hours"], values["annual_time_value"], str(values.get("currency", "SAR") or "SAR"), str(source), _now()),
        )
        conn.commit()
    return snapshot_id

def result_button_should_track(label: str = "", button_type: str = "", form_submit: bool = False) -> bool:
    """Classify likely result-generating controls without touching save/navigation controls."""
    text = str(label or "").strip().casefold()
    excluded = (
        "save", "download", "export", "logout", "lock", "login", "register", "ticket",
        "approve", "decline", "delete", "remove", "decommission", "account", "profile",
        "return", "back", "next", "open", "view", "unlock", "invite", "share", "reset",
        "add to workspace", "record snapshot", "record governed action",
    )
    if any(x in text for x in excluded):
        return False
    keywords = (
        "run", "generate", "calculate", "compute", "solve", "optimize", "simulate",
        "forecast", "analyze", "analyse", "validate", "predict", "schedule", "compare",
        "evaluate", "execute", "build", "clean", "process", "apply", "test", "derive",
        "recommend", "refresh", "start", "create", "design", "model", "inspect",
        "classify", "benchmark", "check", "map", "route", "plan", "search",
    )
    return bool(form_submit or any(x in text for x in keywords) or str(button_type).casefold() == "primary")

def begin_result_timer(module: str, label: str) -> None:
    """Start timing the user's result-generation action."""
    now = time.perf_counter()
    st.session_state["shoir_value_active_run"] = {
        "module": str(module or "Default"),
        "label": str(label or "Result generation"),
        "started_at": now,
        "started_wall": _now(),
    }

def render_value_receipt(module: str, username: str) -> None:
    """Show actual post-click execution time versus a traditional task baseline."""
    run = st.session_state.get("shoir_value_active_run")
    if not isinstance(run, dict) or str(run.get("module", "")) != str(module):
        return

    started = _safe_float(run.get("started_at"), 0.0)
    if started <= 0:
        return
    elapsed = max(0.0, time.perf_counter() - started)

    profile = task_profile(module)
    saved = _saved_baseline(str(username or "unknown"), module) or {}
    traditional_minutes = _safe_float(saved.get("baseline_minutes", profile["baseline_minutes"]))
    traditional_hours = traditional_minutes / 60.0
    time_saved = traditional_hours - (elapsed / 3600.0)
    saved_positive = max(0.0, time_saved)
    saved_pct = (saved_positive / traditional_hours * 100.0) if traditional_hours > 0 else 0.0

    studies = max(1.0, _safe_float(saved.get("studies_per_year", 1.0), 1.0))
    hourly = _safe_float(saved.get("hourly_rate", 250.0), 250.0)
    if hourly <= 0:
        hourly = 250.0
    currency = str(saved.get("currency", "SAR") or "SAR").upper()
    annual_hours = saved_positive * studies
    labor_value = saved_positive * hourly
    annual_labor_value = annual_hours * hourly

    st.markdown(
        f"""<div class="hero-card" style="margin:16px 0 14px 0;border-color:#99f6e4;background:linear-gradient(135deg,#f0fdfa,#ffffff 62%,#eff6ff);">
        <div class="kicker">RESULT VALUE RECEIPT · {html.escape(str(module))}</div>
        <div class="hero-title">⏱️ This result just saved measurable engineering time</div>
        <div class="hero-copy">Compared with the traditional time required for the same task. Shoir-IE time is measured from the result-generating action to completion; the traditional time is a configurable task-specific reference baseline.</div>
        </div>""",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Traditional time", f"{traditional_hours:,.2f} h")
    c2.metric("Shoir-IE actual time", f"{elapsed / 3600.0:,.2f} h")
    c3.metric("Time saved", f"{saved_positive:,.2f} h", delta=f"{saved_pct:,.0f}% less time" if traditional_hours > 0 else None)
    c4.metric(f"Est. labor value · {currency}", f"{currency} {labor_value:,.0f}")

    a1, a2, a3 = st.columns(3)
    a1.metric("Annual capacity released", f"{annual_hours:,.1f} h")
    a2.metric("Annual labor-value equivalent", f"{currency} {annual_labor_value:,.0f}")
    a3.metric("Result action", str(run.get("label", "Result generation"))[:55])

    with st.expander("Calibrate the traditional-time and money baseline", expanded=False):
        st.caption("The traditional time is a planning reference unless you replace it with your real measured customer baseline. The hourly value is an editable planning assumption, not a claimed industry average.")
        key = "shoir_result_calibrate_" + _slug(module)
        with st.form(key):
            b1, b2, b3 = st.columns(3)
            baseline_input = b1.number_input("Traditional task time (minutes)", min_value=0.0, value=float(traditional_minutes), step=5.0, key=key+"_baseline")
            freq_input = b2.number_input("Tasks / studies per year", min_value=1.0, value=float(studies), step=1.0, key=key+"_frequency")
            hourly_input = b3.number_input(f"Loaded engineering value / hour ({currency})", min_value=0.0, value=float(hourly), step=10.0, key=key+"_hourly")
            source_input = st.text_input("Traditional-time source / reference", value=str(saved.get("source", "Reference planning benchmark")), key=key+"_source")
            save_input = st.form_submit_button("Save value baseline", type="primary", use_container_width=True)
        if save_input:
            with sqlite3.connect(DB_PATH, timeout=30) as conn:
                conn.execute(
                    """INSERT INTO shoir_value_task_baselines
                       (owner,module,task,baseline_minutes,shoir_minutes,studies_per_year,hourly_rate,currency,source,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(owner,module) DO UPDATE SET
                       task=excluded.task,baseline_minutes=excluded.baseline_minutes,
                       shoir_minutes=excluded.shoir_minutes,studies_per_year=excluded.studies_per_year,
                       hourly_rate=excluded.hourly_rate,currency=excluded.currency,
                       source=excluded.source,updated_at=excluded.updated_at""",
                    (str(username or "unknown"), str(module), profile["task"], baseline_input,
                     max(0.01, elapsed/60.0), freq_input, hourly_input, currency,
                     source_input.strip()[:300] or "Reference planning benchmark", _now()),
                )
                conn.commit()
            st.success("Value baseline saved for this module.")
            st.rerun()

    st.caption(
        f"Measured at {elapsed:,.2f}s after '{str(run.get('label','result'))[:80]}'. "
        f"Traditional reference: {traditional_minutes:,.0f} min. "
        f"Time released: {saved_positive:,.2f} h. "
        f"Money shown is an estimated labor-value equivalent using {currency} {hourly:,.0f}/h."
    )
    st.session_state["shoir_value_last_receipt"] = {
        "module": str(module),
        "label": str(run.get("label", "Result generation")),
        "elapsed_seconds": elapsed,
        "traditional_minutes": traditional_minutes,
        "time_saved_hours": saved_positive,
        "labor_value": labor_value,
        "currency": currency,
        "created_at": _now(),
    }
    st.session_state.pop("shoir_value_active_run", None)

def render_value_pulse(module: str, username: str) -> None:
    """Compatibility entry point: render the post-result receipt when a result run is active."""
    ensure_value_evidence_db()
    render_value_receipt(module, username)

def render_value_evidence_engine(owner: str, current_module: str = "Venture Studio") -> None:
    """Full professional evidence workspace for Venture Studio."""
    ensure_value_evidence_db()
    module = str(current_module or "Venture Studio")
    profile = task_profile(module)
    saved = _saved_baseline(owner, module) or {}
    current = dict(profile)
    current.update(saved)
    st.markdown("### 💎 Value Evidence Engine")
    st.caption("Convert engineering improvement into customer-specific, evidence-backed time and financial value. Reference estimates are separated from measured evidence.")
    st.markdown(
        """<div class="hero-card">
        <div class="kicker">EVIDENCE-FIRST VALUE MODEL</div>
        <div class="hero-title">Engineering improvement → measurable business value</div>
        <div class="hero-copy">Use the task baseline to quantify time released, then attach customer evidence to financial impact. Nothing is presented as a verified result until the source is recorded.</div>
        </div>""",
        unsafe_allow_html=True,
    )

    st.markdown("#### 1 · Time value")
    st.code("Hours Saved = Baseline Study Time − Shoir-IE Study Time\nAnnual Capacity Released = Hours Saved × Studies Per Year", language="text")
    a, b, c, d = st.columns(4)
    baseline = a.number_input("Baseline study time (minutes)", min_value=0.0, value=float(current["baseline_minutes"]), step=5.0, key="ve_full_baseline")
    shoir = b.number_input("Shoir-IE study time (minutes)", min_value=0.0, value=float(current["shoir_minutes"]), step=1.0, key="ve_full_shoir")
    freq = c.number_input("Studies per year", min_value=1.0, value=float(current.get("studies_per_year", 1.0)), step=1.0, key="ve_full_freq")
    hourly = d.number_input("Loaded engineering value / hour (SAR)", min_value=0.0, value=float(current.get("hourly_rate", 0.0)), step=10.0, key="ve_full_hourly")
    tv = calculate_time_value(baseline, shoir, freq, hourly)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hours saved / study", f"{tv['hours_saved']:,.2f} h")
    c2.metric("Annual capacity released", f"{tv['annual_capacity_hours']:,.1f} h")
    c3.metric("Annual time value", f"SAR {tv['annual_time_value']:,.0f}")
    c4.metric("Evidence status", "Customer-calibrated" if saved else "Reference estimate")

    st.markdown("#### 2 · Financial value")
    st.code("Verified Economic Benefit = Baseline Cost − Post-Deployment Cost − Implementation Cost", language="text")
    f1, f2, f3, f4 = st.columns(4)
    baseline_cost = f1.number_input("Baseline cost / period (SAR)", min_value=0.0, value=0.0, step=100.0, key="ve_fin_baseline")
    post_cost = f2.number_input("Post-deployment cost / period (SAR)", min_value=0.0, value=0.0, step=100.0, key="ve_fin_post")
    implementation = f3.number_input("Implementation cost (SAR)", min_value=0.0, value=0.0, step=100.0, key="ve_fin_impl")
    financial_freq = f4.number_input("Periods per year", min_value=1.0, value=float(freq), step=1.0, key="ve_fin_freq")
    fb = calculate_financial_bridge(baseline_cost, post_cost, implementation, financial_freq)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Verified benefit / period", f"SAR {fb['verified_period_benefit']:,.0f}")
    m2.metric("Annualized operating benefit", f"SAR {fb['annualized_operational_benefit']:,.0f}")
    m3.metric("Annual net benefit", f"SAR {fb['annual_net_benefit']:,.0f}")
    m4.metric("ROI", f"{fb['roi_percent']:,.1f}%" if fb["roi_percent"] is not None else "N/A")
    m5.metric("Payback", f"{fb['payback_months']:,.1f} months" if fb["payback_months"] is not None else "N/A")

    if baseline_cost or post_cost or implementation:
        bridge = pd.DataFrame({
            "Component": ["Baseline cost", "Post-deployment cost", "Implementation cost", "Verified economic benefit"],
            "SAR": [baseline_cost, -post_cost, -implementation, fb["verified_period_benefit"]],
        })
        fig = px.bar(bridge, x="SAR", y="Component", orientation="h", text="SAR", title="Financial value bridge")
        fig.update_layout(height=320, margin=dict(l=16,r=16,t=56,b=20))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Save verified financial bridge", expanded=False):
        bridge_source = st.text_input("Financial evidence source / reference", key="ve_fin_source")
        bridge_state = st.selectbox(
            "Financial evidence state",
            ["Reference estimate", "Customer measured", "Audited"],
            key="ve_fin_state",
        )
        if st.button("💾 Save financial value bridge", type="primary", use_container_width=True, key="ve_fin_save"):
            if bridge_state != "Reference estimate" and not bridge_source.strip():
                st.error("Customer measured or audited financial values require a source reference.")
            else:
                bridge_id = "VB-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + hashlib.sha256(
                    f"{owner}|{module}|{baseline_cost}|{post_cost}|{implementation}|{_now()}".encode("utf-8")
                ).hexdigest()[:10].upper()
                with sqlite3.connect(DB_PATH, timeout=30) as conn:
                    conn.execute(
                        """INSERT INTO shoir_value_financial_bridges
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            bridge_id, owner, module,
                            float(baseline_cost), float(post_cost), float(implementation),
                            float(fb["verified_period_benefit"]),
                            float(financial_freq),
                            float(fb["annualized_operational_benefit"]),
                            float(fb["annual_net_benefit"]),
                            float(fb["roi_percent"] or 0.0),
                            float(fb["payback_months"]) if fb["payback_months"] is not None else None,
                            "SAR",
                            bridge_source.strip()[:300] or "Reference planning estimate",
                            _now(),
                        ),
                    )
                    conn.commit()
                st.success(f"Financial bridge {bridge_id} saved.")
                st.rerun()

    st.markdown("#### 3 · Industrial value scorecard")
    metric_df = pd.DataFrame(_METRICS, columns=["Metric", "Category", "Direction", "Unit"])
    metric_df["Evidence status"] = "Needs baseline + post value"
    metric_df["How value is proven"] = metric_df["Metric"].map({
        "Engineering hours": "Baseline task time vs Shoir-IE task time.",
        "Planning-cycle time": "Planning elapsed time before vs after.",
        "Scenario turnaround": "Scenario creation + comparison elapsed time.",
        "Report-production time": "Time to produce a decision-ready report.",
        "Data-quality defects": "Defects detected and confirmed against ground truth.",
        "Rework cycles": "Baseline rework cycles vs post-deployment.",
        "Inventory impact": "Measured inventory cost / level delta with source.",
        "Transport distance": "Measured route distance before vs after.",
        "Transport cost": "Measured freight cost before vs after.",
        "Scrap & rework value": "Verified scrap/rework cost delta.",
        "Downtime exposure": "Measured downtime cost exposure before vs after.",
        "Energy consumption": "Measured kWh baseline vs post.",
        "Carbon impact": "Measured kgCO2e baseline vs post.",
    })
    st.dataframe(metric_df, use_container_width=True, hide_index=True)

    with st.expander("Save this value snapshot"):
        source = st.text_input("Evidence source / reference", key="ve_snapshot_source")
        confidence = st.selectbox("Evidence state", ["Reference estimate", "Customer measured", "Audited"], key="ve_snapshot_conf")
        if st.button("💾 Save time-value snapshot", type="primary", use_container_width=True, key="ve_snapshot_save"):
            if not source.strip() and confidence != "Reference estimate":
                st.error("Customer measured or audited values require a source reference.")
            else:
                with sqlite3.connect(DB_PATH, timeout=30) as conn:
                    conn.execute(
                        """INSERT INTO shoir_value_task_baselines
                           (owner,module,task,baseline_minutes,shoir_minutes,studies_per_year,hourly_rate,currency,source,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(owner,module) DO UPDATE SET
                           task=excluded.task,baseline_minutes=excluded.baseline_minutes,shoir_minutes=excluded.shoir_minutes,
                           studies_per_year=excluded.studies_per_year,hourly_rate=excluded.hourly_rate,
                           currency=excluded.currency,source=excluded.source,updated_at=excluded.updated_at""",
                        (owner,module,profile["task"],baseline,shoir,freq,hourly,"SAR",source.strip()[:300] or "Reference planning benchmark",_now()),
                    )
                    conn.commit()
                snapshot_values = dict(tv)
                snapshot_values["currency"] = "SAR"
                snapshot_id = record_time_snapshot(owner, module, profile["task"], snapshot_values, source.strip() or "Reference planning benchmark")
                st.success(f"Value snapshot {snapshot_id} saved with its evidence state.")
                st.rerun()

    st.caption("Reference task times are planning assumptions until replaced with customer baseline data. Financial values remain customer-specific; ROI and payback are not reported as verified until the underlying costs and source evidence are supplied.")
