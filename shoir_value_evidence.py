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
import json
import math
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = "enterprise_full_workspace.db"

# Reference planning benchmarks, not claimed industry averages.
_TASK_PROFILES = [
    ("ShadowShift — Micro-Loss & Recovery Intelligence", 0, 0, "Calibrate a traditional-versus-ShadowShift study time baseline from paired measured tasks before making time-saving claims."),
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
    evidence_state TEXT NOT NULL DEFAULT 'Reference estimate',
    reviewer_reference TEXT NOT NULL DEFAULT '',
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
    created_at TEXT NOT NULL,
    evidence_state TEXT NOT NULL DEFAULT 'Reference estimate',
    reviewer_reference TEXT NOT NULL DEFAULT ''
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
    created_at TEXT NOT NULL,
    evidence_state TEXT NOT NULL DEFAULT 'Reference estimate',
    reviewer_reference TEXT NOT NULL DEFAULT '',
    bridge_sha256 TEXT NOT NULL DEFAULT ''
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

def ensure_value_evidence_db(db_path: str | None = None) -> None:
    """Create the value-evidence schema and safely upgrade older local databases."""
    path = str(db_path or DB_PATH)
    try:
        with sqlite3.connect(path, timeout=30) as conn:
            conn.executescript(_SCHEMA)
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(shoir_value_financial_bridges)")}
            table_migrations = {
                "shoir_value_task_baselines": {
                    "evidence_state": "ALTER TABLE shoir_value_task_baselines ADD COLUMN evidence_state TEXT NOT NULL DEFAULT 'Reference estimate'",
                    "reviewer_reference": "ALTER TABLE shoir_value_task_baselines ADD COLUMN reviewer_reference TEXT NOT NULL DEFAULT ''",
                },
                "shoir_value_snapshots": {
                    "evidence_state": "ALTER TABLE shoir_value_snapshots ADD COLUMN evidence_state TEXT NOT NULL DEFAULT 'Reference estimate'",
                    "reviewer_reference": "ALTER TABLE shoir_value_snapshots ADD COLUMN reviewer_reference TEXT NOT NULL DEFAULT ''",
                },
                "shoir_value_financial_bridges": {
                    "evidence_state": "ALTER TABLE shoir_value_financial_bridges ADD COLUMN evidence_state TEXT NOT NULL DEFAULT 'Reference estimate'",
                    "reviewer_reference": "ALTER TABLE shoir_value_financial_bridges ADD COLUMN reviewer_reference TEXT NOT NULL DEFAULT ''",
                    "bridge_sha256": "ALTER TABLE shoir_value_financial_bridges ADD COLUMN bridge_sha256 TEXT NOT NULL DEFAULT ''",
                },
            }
            for table_name, migrations in table_migrations.items():
                columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}
                for column, statement in migrations.items():
                    if column not in columns:
                        conn.execute(statement)
            conn.commit()
    except Exception as exc:
        # A locally unavailable optional evidence store must not prevent the
        # application from starting. The warning leaves a diagnostic trail.
        import logging
        logging.getLogger(__name__).warning(
            "Value-evidence database initialization failed for %s: %s",
            path, type(exc).__name__,
        )


def task_profile(module: str) -> dict[str, Any]:
    name = str(module or "Default").strip()
    lower = name.casefold()
    exact = next((p for p in _TASK_PROFILES if p[0].casefold() == lower), None)
    if exact:
        label, baseline, shoir, purpose = exact
        return {"task": label, "baseline_minutes": baseline, "shoir_minutes": shoir, "purpose": purpose}
    keyword_map = [
        (("shadowshift", "micro-loss", "micro loss"), "ShadowShift — Micro-Loss & Recovery Intelligence"),
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
                "SELECT task,baseline_minutes,shoir_minutes,studies_per_year,hourly_rate,currency,source,evidence_state,reviewer_reference FROM shoir_value_task_baselines WHERE owner=? AND module=?",
                (str(owner), str(module)),
            ).fetchone()
        if row:
            return {"task": row[0], "baseline_minutes": row[1], "shoir_minutes": row[2], "studies_per_year": row[3], "hourly_rate": row[4], "currency": row[5], "source": row[6], "evidence_state": row[7], "reviewer_reference": row[8]}
    except Exception:
        pass
    return None

def _require_finite(value: Any, field: str, *, minimum: float = 0.0) -> float:
    """Reject invalid evidence inputs instead of silently converting them to zero."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite; NaN and infinity are not accepted.")
    if number < minimum:
        raise ValueError(f"{field} must be at least {minimum:g}.")
    return number


def calculate_time_value(
    baseline_minutes: float,
    shoir_minutes: float,
    studies_per_year: float = 1.0,
    hourly_rate: float = 0.0,
) -> dict[str, float]:
    baseline_h = _require_finite(baseline_minutes, "Baseline minutes") / 60.0
    shoir_h = _require_finite(shoir_minutes, "Shoir-IE minutes") / 60.0
    frequency = _require_finite(studies_per_year, "Studies per year")
    rate = _require_finite(hourly_rate, "Hourly rate")
    saved_h = baseline_h - shoir_h
    annual_h = saved_h * frequency
    annual_value = annual_h * rate
    values = {
        "baseline_hours": baseline_h,
        "shoir_hours": shoir_h,
        "hours_saved": saved_h,
        "annual_capacity_hours": annual_h,
        "annual_time_value": annual_value,
    }
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("Time-value calculation exceeded the finite numeric range.")
    return values


def calculate_financial_bridge(
    baseline_cost: float,
    post_cost: float,
    implementation_cost: float,
    frequency_per_year: float = 1.0,
) -> dict[str, Any]:
    baseline = _require_finite(baseline_cost, "Baseline cost")
    post = _require_finite(post_cost, "Post-deployment cost")
    implementation = _require_finite(implementation_cost, "Implementation cost")
    frequency = _require_finite(frequency_per_year, "Periods per year")
    calculated_period_net = baseline - post - implementation
    operational_delta = baseline - post
    annualized_operational = operational_delta * frequency
    annual_net = annualized_operational - implementation
    roi = (annual_net / implementation * 100.0) if implementation > 0 else None
    payback = (
        implementation / (annualized_operational / 12.0)
        if annualized_operational > 0 and implementation > 0
        else None
    )
    numeric_values = [calculated_period_net, operational_delta, annualized_operational, annual_net]
    numeric_values.extend(value for value in (roi, payback) if value is not None)
    if not all(math.isfinite(value) for value in numeric_values):
        raise ValueError("Financial value calculation exceeded the finite numeric range.")
    return {
        # Keep the legacy key for compatibility; it is a calculation, not a verified outcome.
        "verified_period_benefit": calculated_period_net,
        "calculated_period_net_benefit": calculated_period_net,
        "annualized_operational_benefit": annualized_operational,
        "annual_net_benefit": annual_net,
        "roi_percent": roi,
        "payback_months": payback,
        "classification": "Calculated scenario estimate; not a verified or realized benefit",
        "calculation_version": "value-bridge/1.0.0",
    }


def save_financial_bridge_record(
    owner: str,
    module: str,
    baseline_cost: float,
    post_cost: float,
    implementation_cost: float,
    frequency_per_year: float = 1.0,
    *,
    source: str = "",
    evidence_state: str = "Reference estimate",
    reviewer_reference: str = "",
    currency: str = "SAR",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Persist a financial estimate with explicit evidence-state and review metadata."""
    owner_value, module_value = str(owner or "").strip(), str(module or "").strip()
    source_value, reviewer_value = str(source or "").strip(), str(reviewer_reference or "").strip()
    currency_value = str(currency or "").strip().upper()
    accepted_states = {
        "Reference estimate",
        "Customer measured",
        "Independent review record (user-attested; not authenticated)",
    }
    if not owner_value or not module_value:
        raise ValueError("A non-empty owner and module are required.")
    if len(owner_value) > 200 or len(module_value) > 200:
        raise ValueError("Owner or module name is too long.")
    if evidence_state not in accepted_states:
        raise ValueError("Unsupported financial evidence state.")
    if evidence_state != "Reference estimate" and not source_value:
        raise ValueError("A source reference is required for measured or reviewed financial records.")
    if evidence_state.startswith("Independent review") and not reviewer_value:
        raise ValueError("A reviewer reference is required for an independent-review record; it is recorded as user-attested, not authenticated.")
    if len(source_value) > 500 or len(reviewer_value) > 500:
        raise ValueError("Source and reviewer references must be 500 characters or fewer.")
    if not currency_value or len(currency_value) > 8:
        raise ValueError("Currency must be a short non-empty code.")

    path = str(db_path or DB_PATH)
    result = calculate_financial_bridge(baseline_cost, post_cost, implementation_cost, frequency_per_year)
    created = _now()
    bridge_id = "VB-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + hashlib.sha256(
        f"{owner_value}|{module_value}|{baseline_cost}|{post_cost}|{implementation_cost}|{created}".encode("utf-8")
    ).hexdigest()[:10].upper()
    payload = {
        "bridge_id": bridge_id,
        "owner": owner_value,
        "module": module_value,
        "baseline_cost": float(baseline_cost),
        "post_cost": float(post_cost),
        "implementation_cost": float(implementation_cost),
        "frequency_per_year": float(frequency_per_year),
        "currency": currency_value,
        "source": source_value or "Reference planning estimate",
        "evidence_state": evidence_state,
        "reviewer_reference": reviewer_value,
        "calculation": result,
        "created_at": created,
    }
    bridge_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    ensure_value_evidence_db(path)
    with sqlite3.connect(path, timeout=30) as conn:
        conn.execute(
            """INSERT INTO shoir_value_financial_bridges
               (bridge_id,owner,module,baseline_cost,post_cost,implementation_cost,
                verified_economic_benefit,frequency_per_year,annualized_operational_benefit,
                annual_net_benefit,roi_percent,payback_months,currency,source,created_at,
                evidence_state,reviewer_reference,bridge_sha256)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bridge_id, owner_value, module_value, float(baseline_cost), float(post_cost),
                float(implementation_cost), float(result["calculated_period_net_benefit"]),
                float(frequency_per_year), float(result["annualized_operational_benefit"]),
                float(result["annual_net_benefit"]),
                float(result["roi_percent"]) if result["roi_percent"] is not None else 0.0,
                float(result["payback_months"]) if result["payback_months"] is not None else None,
                currency_value, payload["source"], created, evidence_state, reviewer_value, bridge_hash,
            ),
        )
        conn.commit()
    return {
        **payload,
        "calculation": result,
        "bridge_sha256": bridge_hash,
        "source_authentication": "Not independently authenticated by Shoir-IE",
    }


def save_task_baseline(
    owner: str,
    module: str,
    task: str,
    baseline_minutes: float,
    shoir_minutes: float,
    studies_per_year: float,
    hourly_rate: float,
    *,
    currency: str = "SAR",
    source: str = "",
    evidence_state: str = "Reference estimate",
    reviewer_reference: str = "",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Store explicitly supplied comparable task times and their evidence label."""
    owner_value, module_value = str(owner or "").strip(), str(module or "").strip()
    task_value, source_value = str(task or "").strip(), str(source or "").strip()
    reviewer_value = str(reviewer_reference or "").strip()
    accepted_states = {"Reference estimate", "Customer measured"}
    if not owner_value or not module_value or not task_value:
        raise ValueError("Owner, module, and task are required to save a time baseline.")
    if evidence_state not in accepted_states:
        raise ValueError("Unsupported task-time evidence state.")
    if evidence_state == "Customer measured" and not source_value:
        raise ValueError("Customer-measured task times require a source reference.")
    if any(len(value) > max_length for value, max_length in (
        (owner_value, 200), (module_value, 200), (task_value, 200),
        (source_value, 500), (reviewer_value, 500),
    )):
        raise ValueError("A task-time evidence field exceeds its length limit.")
    values = calculate_time_value(baseline_minutes, shoir_minutes, studies_per_year, hourly_rate)
    baseline = values["baseline_hours"] * 60.0
    shoir = values["shoir_hours"] * 60.0
    frequency = _require_finite(studies_per_year, "Studies per year")
    rate = _require_finite(hourly_rate, "Hourly rate")
    path = str(db_path or DB_PATH)
    ensure_value_evidence_db(path)
    timestamp = _now()
    with sqlite3.connect(path, timeout=30) as conn:
        conn.execute(
            """INSERT INTO shoir_value_task_baselines
               (owner,module,task,baseline_minutes,shoir_minutes,studies_per_year,hourly_rate,
                currency,source,updated_at,evidence_state,reviewer_reference)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(owner,module) DO UPDATE SET
               task=excluded.task,baseline_minutes=excluded.baseline_minutes,shoir_minutes=excluded.shoir_minutes,
               studies_per_year=excluded.studies_per_year,hourly_rate=excluded.hourly_rate,
               currency=excluded.currency,source=excluded.source,updated_at=excluded.updated_at,
               evidence_state=excluded.evidence_state,reviewer_reference=excluded.reviewer_reference""",
            (
                owner_value, module_value, task_value, baseline, shoir, frequency, rate,
                currency, source_value or "Reference planning benchmark", timestamp,
                evidence_state, reviewer_value,
            ),
        )
        conn.commit()
    return {
        "owner": owner_value, "module": module_value, "task": task_value,
        "baseline_minutes": baseline, "shoir_minutes": shoir,
        "studies_per_year": frequency, "hourly_rate": rate, "currency": currency,
        "source": source_value or "Reference planning benchmark",
        "evidence_state": evidence_state, "reviewer_reference": reviewer_value,
        "updated_at": timestamp,
    }


def record_time_snapshot(
    owner: str,
    module: str,
    task: str,
    values: dict[str, Any],
    source: str,
    db_path: str | None = None,
) -> str:
    path = str(db_path or DB_PATH)
    ensure_value_evidence_db(path)
    snapshot_id = "VE-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + hashlib.sha256(f"{owner}|{module}|{task}|{_now()}".encode("utf-8")).hexdigest()[:10].upper()
    evidence_state = str(values.get("evidence_state", "Reference estimate") or "Reference estimate")
    reviewer_reference = str(values.get("reviewer_reference", "") or "")
    if evidence_state not in {"Reference estimate", "Customer measured"}:
        raise ValueError("Unsupported time-snapshot evidence state.")
    if evidence_state == "Customer measured" and not str(source or "").strip():
        raise ValueError("Customer-measured time snapshots require a source reference.")
    with sqlite3.connect(path, timeout=30) as conn:
        conn.execute(
            """INSERT INTO shoir_value_snapshots
               (snapshot_id,owner,module,task,baseline_minutes,shoir_minutes,hours_saved,
                annual_capacity_hours,annual_time_value,currency,source,created_at,
                evidence_state,reviewer_reference)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (snapshot_id, str(owner), str(module), str(task), values["baseline_hours"] * 60.0, values["shoir_hours"] * 60.0, values["hours_saved"], values["annual_capacity_hours"], values["annual_time_value"], str(values.get("currency", "SAR") or "SAR"), str(source), _now(), evidence_state, reviewer_reference),
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
    if form_submit and not any(
        x in text for x in (
            "run", "generate", "calculate", "compute", "solve", "optimize", "simulate",
            "forecast", "analyze", "analyse", "validate", "predict", "schedule", "compare",
            "evaluate", "execute", "build", "clean", "process", "apply", "test", "derive",
            "recommend", "refresh", "start", "create", "design", "model", "inspect",
            "classify", "benchmark", "check", "map", "route", "plan", "search",
        "result", "results", "produce", "launch", "solve",
        )
    ):
        return False
    keywords = (
        "run", "generate", "calculate", "compute", "solve", "optimize", "simulate",
        "forecast", "analyze", "analyse", "validate", "predict", "schedule", "compare",
        "evaluate", "execute", "build", "clean", "process", "apply", "test", "derive",
        "recommend", "refresh", "start", "create", "design", "model", "inspect",
        "classify", "benchmark", "check", "map", "route", "plan", "search",
    )
    return bool(any(x in text for x in keywords))

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
    """Report measured application latency without mislabelling it as engineering time saved.

    Application execution time is not comparable to the end-to-end engineering task
    baseline. Only the Value Evidence Engine's explicit before/after task inputs may
    be used to calculate task-time differences.
    """
    if "shadowshift" in str(module or "").casefold():
        return
    run = st.session_state.get("shoir_value_active_run")
    if not isinstance(run, dict) or str(run.get("module", "")) != str(module):
        return

    started = _safe_float(run.get("started_at"), 0.0)
    if started <= 0:
        st.session_state.pop("shoir_value_active_run", None)
        return
    elapsed = max(0.0, time.perf_counter() - started)
    label = str(run.get("label", "Result generation"))[:120]

    st.markdown(
        f"""<div class="hero-card" style="margin:16px 0 14px 0;">
        <div class="kicker">EXECUTION RECEIPT · {html.escape(str(module))}</div>
        <div class="hero-title">Observed application execution duration</div>
        <div class="hero-copy">This is software execution time for the current action. It is not the total time an engineer spends completing the task and is not evidence of hours saved, annual capacity released, or financial benefit.</div>
        </div>""",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Observed application duration", f"{elapsed:,.2f} seconds")
    c2.metric("Claimed engineering time saved", "Not calculated")
    c3.metric("Claimed financial benefit", "Not calculated")
    st.caption(
        f"Action: {label}. Record comparable end-to-end baseline and post-deployment task times "
        "in Value Evidence Engine before calculating task-time differences. The app does not "
        "create an operational savings snapshot from render latency."
    )
    st.session_state["shoir_value_last_receipt"] = {
        "module": str(module),
        "label": label,
        "elapsed_seconds": elapsed,
        "classification": "Measured application execution duration only",
        "time_saved_hours": None,
        "labor_value": None,
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
    c4.metric("Evidence status", "Saved baseline — source not authenticated" if saved else "Reference estimate")

    st.markdown("#### 2 · Financial value")
    st.code("Calculated Period Net Benefit = Baseline Cost − Post-Deployment Cost − Implementation Cost", language="text")
    f1, f2, f3, f4 = st.columns(4)
    baseline_cost = f1.number_input("Baseline cost / period (SAR)", min_value=0.0, value=0.0, step=100.0, key="ve_fin_baseline")
    post_cost = f2.number_input("Post-deployment cost / period (SAR)", min_value=0.0, value=0.0, step=100.0, key="ve_fin_post")
    implementation = f3.number_input("Implementation cost (SAR)", min_value=0.0, value=0.0, step=100.0, key="ve_fin_impl")
    financial_freq = f4.number_input("Periods per year", min_value=1.0, value=float(freq), step=1.0, key="ve_fin_freq")
    fb = calculate_financial_bridge(baseline_cost, post_cost, implementation, financial_freq)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Calculated net benefit / period", f"SAR {fb['calculated_period_net_benefit']:,.0f}")
    m2.metric("Annualized operating benefit", f"SAR {fb['annualized_operational_benefit']:,.0f}")
    m3.metric("Annual net benefit", f"SAR {fb['annual_net_benefit']:,.0f}")
    m4.metric("ROI", f"{fb['roi_percent']:,.1f}%" if fb["roi_percent"] is not None else "N/A")
    m5.metric("Payback", f"{fb['payback_months']:,.1f} months" if fb["payback_months"] is not None else "N/A")

    if baseline_cost or post_cost or implementation:
        bridge = pd.DataFrame({
            "Component": ["Baseline cost", "Post-deployment cost", "Implementation cost", "Calculated period net benefit"],
            "SAR": [baseline_cost, -post_cost, -implementation, fb["verified_period_benefit"]],
        })
        fig = px.bar(bridge, x="SAR", y="Component", orientation="h", text="SAR", title="Financial value bridge")
        fig.update_layout(height=320, margin=dict(l=16,r=16,t=56,b=20))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Save financial evidence record", expanded=False):
        bridge_source = st.text_input("Financial evidence source / reference", key="ve_fin_source")
        bridge_state = st.selectbox(
            "Financial evidence classification",
            [
                "Reference estimate",
                "Customer measured",
                "Independent review record (user-attested; not authenticated)",
            ],
            key="ve_fin_state",
        )
        reviewer_reference = ""
        if bridge_state.startswith("Independent review"):
            reviewer_reference = st.text_input(
                "Independent reviewer / review artifact reference",
                key="ve_fin_reviewer_reference",
                help="This field records a user-attested review reference. Shoir-IE does not authenticate the reviewer or certify the independent review.",
            )
        st.caption("Saving preserves the assumptions and source reference; it does not independently verify the stated costs or any realized benefit.")
        if st.button("💾 Save financial evidence record", type="primary", use_container_width=True, key="ve_fin_save"):
            try:
                saved_bridge = save_financial_bridge_record(
                    owner, module, baseline_cost, post_cost, implementation, financial_freq,
                    source=bridge_source,
                    evidence_state=bridge_state,
                    reviewer_reference=reviewer_reference,
                    currency="SAR",
                )
                st.success(
                    f"Saved {saved_bridge['bridge_id']} · {saved_bridge['calculation']['classification']} · "
                    f"SHA-256 {saved_bridge['bridge_sha256'][:16]}…"
                )
                st.caption("The source is recorded but not independently authenticated by Shoir-IE.")
                st.rerun()
            except Exception as exc:
                st.error(f"Financial evidence record could not be saved safely: {type(exc).__name__}: {exc}")

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
        confidence = st.selectbox("Evidence state", ["Reference estimate", "Customer measured"], key="ve_snapshot_conf")
        if st.button("💾 Save time-value snapshot", type="primary", use_container_width=True, key="ve_snapshot_save"):
            if not source.strip() and confidence != "Reference estimate":
                st.error("Customer-measured values require a source reference.")
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

    st.caption("Reference task times are planning assumptions. Financial values are calculated from entered cost inputs, and source references are recorded but not authenticated. ROI and payback are scenario calculations, not verified or realized benefits.")
