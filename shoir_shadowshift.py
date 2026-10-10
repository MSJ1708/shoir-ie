"""ShadowShift: micro-loss, recovery and next-best-observation intelligence.

This module deliberately separates observed event data from projections. Its
experiment priority is a transparent heuristic, not a causal model or savings claim.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

MODULE_NAME = "ShadowShift — Micro-Loss & Recovery Intelligence"
DB_PATH = os.environ.get("SHOIR_SHADOWSHIFT_DB", "enterprise_full_workspace.db")

EVENT_TYPES = [
    "Waiting / blocked", "Searching for tools or information", "Material unavailable",
    "Equipment stop / reset", "Handoff / communication", "Quality check / rework",
    "Method variation", "Scheduling / release delay", "Other / unclassified",
]
CAUSES = [
    "Material / tool availability", "Equipment / reset", "Handoff / communication",
    "Quality / rework", "Work method / standard", "Scheduling / release",
    "Training / skill", "Layout / travel", "Unknown / not yet tested",
]
EVIDENCE_SOURCES = [
    "Direct observation", "Machine / system log", "Operator report",
    "Supervisor / planner estimate", "Synthetic demo",
]
EVENT_COLUMNS = [
    "Event ID", "Observed at", "Event type", "Station", "Interruption min",
    "Recovery min", "People affected", "Suspected cause", "Evidence strength (1-5)",
    "Evidence source", "Notes",
]

CAUSE_PLAYBOOK: dict[str, dict[str, Any]] = {
    "Material / tool availability": {
        "hypothesis": "Required tools or materials are not ready at point of use.",
        "prediction": "Readiness timestamps explain a repeatable share of observed waiting.",
        "test": "For 5 comparable cycles, timestamp request, point-of-use readiness and work-resume; compare staged versus current practice.",
        "metric": "Waiting minutes per cycle", "effort_min": 20, "target_n": 5,
        "control": "Current tool/material staging", "treatment": "Pre-stage required tools/materials",
    },
    "Equipment / reset": {
        "hypothesis": "A recurring stop or reset procedure contributes to interruption and recovery time.",
        "prediction": "A repeatable stop/reset signature precedes longer recovery events.",
        "test": "For 5 comparable interruptions, record stop cause, approved reset steps and time-to-first-good-cycle. Never bypass safety controls.",
        "metric": "Stop-to-stable-output minutes", "effort_min": 25, "target_n": 5,
        "control": "Current approved response", "treatment": "Approved checklist or maintenance review",
    },
    "Handoff / communication": {
        "hypothesis": "Information or ownership gaps create waiting during handoffs.",
        "prediction": "Handoffs with required information ready have shorter elapsed waits.",
        "test": "Compare 5 current handoffs with 5 using an approved readiness checklist.",
        "metric": "Handoff waiting minutes", "effort_min": 25, "target_n": 10,
        "control": "Current handoff practice", "treatment": "Readiness checklist at handoff",
    },
    "Quality / rework": {
        "hypothesis": "Repeat inspection, rework or unclear acceptance criteria increase recovery burden.",
        "prediction": "Repeat checks show higher burden than first-pass checks.",
        "test": "Tag first-pass and repeat checks for 10 units; compare time and disposition without relaxing quality criteria.",
        "metric": "Inspection / rework minutes per unit", "effort_min": 30, "target_n": 10,
        "control": "Current compliant inspection", "treatment": "Clarified standard work / check sequence",
    },
    "Work method / standard": {
        "hypothesis": "Variation in task sequence or unclear standard work creates inconsistent cycle and recovery time.",
        "prediction": "A task step is repeated, searched for or performed in a different order across comparable cycles.",
        "test": "Observe 5 comparable cycles, code task sequence and recovery, then review variation with the operator.",
        "metric": "Cycle / recovery minutes", "effort_min": 30, "target_n": 5,
        "control": "Current work sequence", "treatment": "Documented, operator-reviewed sequence",
    },
    "Scheduling / release": {
        "hypothesis": "Work waits for a release, priority or dispatch decision after it is otherwise ready.",
        "prediction": "Ready-to-start and release timestamps explain a meaningful share of queue delay.",
        "test": "Timestamp ready, released and started for 5 orders; compare delays by release reason and priority.",
        "metric": "Ready-to-start waiting minutes", "effort_min": 20, "target_n": 5,
        "control": "Current release workflow", "treatment": "Explicit release-readiness rule",
    },
    "Training / skill": {
        "hypothesis": "Task unfamiliarity or missing skill coverage may contribute to searching or recovery.",
        "prediction": "Matched tasks show different assistance/recovery patterns after accounting for product and station.",
        "test": "With permission, compare 5 matched cycles by task familiarity; record assistance, defects and recovery without ranking people from tiny samples.",
        "metric": "Assistance / recovery minutes", "effort_min": 35, "target_n": 10,
        "control": "Current support arrangement", "treatment": "Job aid or approved coaching",
    },
    "Layout / travel": {
        "hypothesis": "Tool, material or information location creates repeated travel or retrieval time.",
        "prediction": "The same retrieval path recurs and a safe point-of-use mock-up shortens it.",
        "test": "Record 5 task paths and retrieval times; mock up a safe temporary point-of-use arrangement before moving anything permanently.",
        "metric": "Retrieval / travel minutes per cycle", "effort_min": 30, "target_n": 5,
        "control": "Current layout", "treatment": "Safe temporary point-of-use mock-up",
    },
    "Unknown / not yet tested": {
        "hypothesis": "The interruption pattern is not yet supported by a specific root-cause explanation.",
        "prediction": "Structured coding of the next 5 events will distinguish competing explanations.",
        "test": "For the next 5 events, record trigger, blocker, station/person affected, interruption end and return-to-normal point before assigning a cause.",
        "metric": "Share of events with evidence-backed cause", "effort_min": 10, "target_n": 5,
        "control": "Unstructured observation", "treatment": "Structured event coding sheet",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _text(value: Any, limit: int = 1000) -> str:
    return str(value if value is not None else "").strip()[:limit]


def ensure_shadowshift_schema(db_path: str = DB_PATH) -> None:
    """Create ShadowShift-only tables without altering existing Shoir-IE tables."""
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS shadowshift_studies (
            study_id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
            process_name TEXT NOT NULL DEFAULT '', observation_window_min REAL NOT NULL DEFAULT 60,
            shift_window_min REAL NOT NULL DEFAULT 480, shifts_per_year REAL NOT NULL DEFAULT 250,
            loaded_hourly_rate_sar REAL NOT NULL DEFAULT 0, downstream_stress_factor REAL NOT NULL DEFAULT 1,
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_shadowshift_study_owner ON shadowshift_studies(owner,updated_at);
        CREATE TABLE IF NOT EXISTS shadowshift_events (
            event_id TEXT PRIMARY KEY, study_id TEXT NOT NULL, owner TEXT NOT NULL, observed_at TEXT NOT NULL,
            event_type TEXT NOT NULL, station TEXT NOT NULL, interruption_min REAL NOT NULL DEFAULT 0,
            recovery_min REAL NOT NULL DEFAULT 0, people_affected INTEGER NOT NULL DEFAULT 1,
            suspected_cause TEXT NOT NULL DEFAULT 'Unknown / not yet tested',
            evidence_strength INTEGER NOT NULL DEFAULT 3, evidence_source TEXT NOT NULL DEFAULT 'Direct observation',
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_shadowshift_events_study ON shadowshift_events(owner,study_id,observed_at);
        CREATE TABLE IF NOT EXISTS shadowshift_experiments (
            experiment_id TEXT PRIMARY KEY, study_id TEXT NOT NULL, owner TEXT NOT NULL, hypothesis TEXT NOT NULL,
            comparison_condition TEXT NOT NULL, test_condition TEXT NOT NULL, primary_metric TEXT NOT NULL,
            unit TEXT NOT NULL, target_n INTEGER NOT NULL, planned_minutes REAL NOT NULL,
            expected_direction TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Planned',
            result_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_shadowshift_experiments_study ON shadowshift_experiments(owner,study_id,created_at);
        CREATE TABLE IF NOT EXISTS shadowshift_snapshots (
            snapshot_id TEXT PRIMARY KEY, study_id TEXT NOT NULL, owner TEXT NOT NULL,
            assumptions_json TEXT NOT NULL, analysis_json TEXT NOT NULL, evidence_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        conn.commit()


def create_study(owner: str, name: str = "New ShadowShift Study", db_path: str = DB_PATH) -> str:
    ensure_shadowshift_schema(db_path)
    sid, now = "SS-" + uuid.uuid4().hex[:12].upper(), _now()
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute(
            """INSERT INTO shadowshift_studies
            (study_id,owner,name,process_name,observation_window_min,shift_window_min,shifts_per_year,
             loaded_hourly_rate_sar,downstream_stress_factor,notes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, _text(owner, 120) or "unknown", _text(name, 180) or "New ShadowShift Study",
             "", 60.0, 480.0, 250.0, 0.0, 1.0, "", now, now),
        )
        conn.commit()
    return sid


def list_studies(owner: str, db_path: str = DB_PATH) -> pd.DataFrame:
    ensure_shadowshift_schema(db_path)
    with sqlite3.connect(db_path, timeout=30) as conn:
        return pd.read_sql_query("SELECT * FROM shadowshift_studies WHERE owner=? ORDER BY updated_at DESC", conn, params=(str(owner),))


def load_study(study_id: str, owner: str, db_path: str = DB_PATH) -> dict[str, Any] | None:
    ensure_shadowshift_schema(db_path)
    with sqlite3.connect(db_path, timeout=30) as conn:
        cursor = conn.execute("SELECT * FROM shadowshift_studies WHERE study_id=? AND owner=?", (str(study_id), str(owner)))
        row = cursor.fetchone()
        return dict(zip([x[0] for x in cursor.description], row)) if row else None


def update_study(study_id: str, owner: str, settings: dict[str, Any], db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute(
            """UPDATE shadowshift_studies SET name=?,process_name=?,observation_window_min=?,shift_window_min=?,
            shifts_per_year=?,loaded_hourly_rate_sar=?,downstream_stress_factor=?,notes=?,updated_at=?
            WHERE study_id=? AND owner=?""",
            (
                _text(settings.get("name"), 180) or "Untitled study", _text(settings.get("process_name"), 180),
                max(1.0, _num(settings.get("observation_window_min"), 60)),
                max(1.0, _num(settings.get("shift_window_min"), 480)),
                max(0.0, _num(settings.get("shifts_per_year"), 250)),
                max(0.0, _num(settings.get("loaded_hourly_rate_sar"), 0)),
                max(1.0, min(3.0, _num(settings.get("downstream_stress_factor"), 1))),
                _text(settings.get("notes"), 4000), _now(), str(study_id), str(owner),
            ),
        )
        conn.commit()


def clean_event_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize edited/imported event logs and apply conservative validation."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    aliases = {
        "event id": "Event ID", "timestamp": "Observed at", "observed at": "Observed at",
        "datetime": "Observed at", "event type": "Event type", "category": "Event type",
        "station": "Station", "workstation": "Station", "interruption minutes": "Interruption min",
        "interruption min": "Interruption min", "recovery minutes": "Recovery min",
        "recovery min": "Recovery min", "people affected": "People affected", "headcount": "People affected",
        "suspected cause": "Suspected cause", "cause": "Suspected cause",
        "evidence strength": "Evidence strength (1-5)", "evidence strength (1-5)": "Evidence strength (1-5)",
        "evidence source": "Evidence source", "source": "Evidence source", "notes": "Notes",
    }
    rename = {col: aliases[str(col).strip().casefold().replace("_", " ")] for col in frame.columns
              if str(col).strip().casefold().replace("_", " ") in aliases}
    d = frame.rename(columns=rename).copy()
    defaults = {
        "Event ID": "", "Observed at": _now(), "Event type": "Other / unclassified",
        "Station": "Unspecified station", "Interruption min": 0, "Recovery min": 0,
        "People affected": 1, "Suspected cause": "Unknown / not yet tested",
        "Evidence strength (1-5)": 3, "Evidence source": "Direct observation", "Notes": "",
    }
    for col, default in defaults.items():
        if col not in d:
            d[col] = default
    d = d[EVENT_COLUMNS].copy()
    d["Interruption min"] = pd.to_numeric(d["Interruption min"], errors="coerce").fillna(0).clip(lower=0)
    d["Recovery min"] = pd.to_numeric(d["Recovery min"], errors="coerce").fillna(0).clip(lower=0)
    d["People affected"] = pd.to_numeric(d["People affected"], errors="coerce").fillna(1).clip(lower=1, upper=10000).astype(int)
    d["Evidence strength (1-5)"] = pd.to_numeric(d["Evidence strength (1-5)"], errors="coerce").fillna(3).clip(1, 5).astype(int)
    blank = d["Event ID"].fillna("").astype(str).str.strip().eq("")
    d["Event ID"] = d["Event ID"].fillna("").astype(str)
    d.loc[blank, "Event ID"] = ["SSE-" + uuid.uuid4().hex[:12].upper() for _ in range(int(blank.sum()))]
    d["Observed at"] = d["Observed at"].fillna("").astype(str).replace("", _now())
    d["Event type"] = d["Event type"].astype(str).where(d["Event type"].astype(str).isin(EVENT_TYPES), "Other / unclassified")
    d["Suspected cause"] = d["Suspected cause"].astype(str).where(d["Suspected cause"].astype(str).isin(CAUSES), "Unknown / not yet tested")
    d["Evidence source"] = d["Evidence source"].astype(str).where(d["Evidence source"].astype(str).isin(EVIDENCE_SOURCES), "Operator report")
    for col in ("Station", "Notes"):
        d[col] = d[col].fillna("").astype(str).str.slice(0, 2000)
    return d.reset_index(drop=True)


def _event_record(record: dict[str, Any], study_id: str, owner: str) -> dict[str, Any]:
    row = {str(k).strip().casefold().replace("_", " "): v for k, v in record.items()}
    def get(name: str, default: Any = "") -> Any:
        return row.get(name.casefold().replace("_", " "), default)
    stamp = _text(get("Observed at"), 80) or _now()
    try:
        parsed = pd.to_datetime(stamp, utc=True, errors="coerce")
        stamp = parsed.isoformat(timespec="seconds") if pd.notna(parsed) else _now()
    except Exception:
        stamp = _now()
    event_type = _text(get("Event type"), 100)
    cause = _text(get("Suspected cause"), 120)
    source = _text(get("Evidence source"), 80)
    return {
        "event_id": _text(get("Event ID"), 64) or "SSE-" + uuid.uuid4().hex[:12].upper(),
        "study_id": str(study_id), "owner": _text(owner, 120) or "unknown", "observed_at": stamp,
        "event_type": event_type if event_type in EVENT_TYPES else "Other / unclassified",
        "station": _text(get("Station"), 120) or "Unspecified station",
        "interruption_min": max(0.0, _num(get("Interruption min"), 0)),
        "recovery_min": max(0.0, _num(get("Recovery min"), 0)),
        "people_affected": max(1, min(10000, int(_num(get("People affected"), 1)))),
        "suspected_cause": cause if cause in CAUSES else "Unknown / not yet tested",
        "evidence_strength": max(1, min(5, int(_num(get("Evidence strength (1-5)"), 3)))),
        "evidence_source": source if source in EVIDENCE_SOURCES else "Operator report",
        "notes": _text(get("Notes"), 2000), "created_at": _now(),
    }


def add_event(study_id: str, owner: str, event: dict[str, Any], db_path: str = DB_PATH) -> str:
    ensure_shadowshift_schema(db_path)
    item = _event_record(event, study_id, owner)
    keys = ("event_id", "study_id", "owner", "observed_at", "event_type", "station", "interruption_min",
            "recovery_min", "people_affected", "suspected_cause", "evidence_strength", "evidence_source", "notes", "created_at")
    with sqlite3.connect(db_path, timeout=30) as conn:
        if not conn.execute("SELECT 1 FROM shadowshift_studies WHERE study_id=? AND owner=?", (study_id, owner)).fetchone():
            raise ValueError("Study not found for the current owner.")
        conn.execute("""INSERT INTO shadowshift_events
            (event_id,study_id,owner,observed_at,event_type,station,interruption_min,recovery_min,
             people_affected,suspected_cause,evidence_strength,evidence_source,notes,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(item[k] for k in keys))
        conn.execute("UPDATE shadowshift_studies SET updated_at=? WHERE study_id=? AND owner=?", (_now(), study_id, owner))
        conn.commit()
    return item["event_id"]


def load_events(study_id: str, owner: str, db_path: str = DB_PATH) -> pd.DataFrame:
    ensure_shadowshift_schema(db_path)
    with sqlite3.connect(db_path, timeout=30) as conn:
        d = pd.read_sql_query(
            """SELECT event_id AS 'Event ID',observed_at AS 'Observed at',event_type AS 'Event type',
            station AS 'Station',interruption_min AS 'Interruption min',recovery_min AS 'Recovery min',
            people_affected AS 'People affected',suspected_cause AS 'Suspected cause',
            evidence_strength AS 'Evidence strength (1-5)',evidence_source AS 'Evidence source',notes AS 'Notes'
            FROM shadowshift_events WHERE study_id=? AND owner=? ORDER BY observed_at,event_id""",
            conn, params=(str(study_id), str(owner)),
        )
    return clean_event_frame(d)


def replace_events(study_id: str, owner: str, frame: pd.DataFrame, db_path: str = DB_PATH) -> int:
    """Replace the selected study's edited rows atomically, with an owner check."""
    ensure_shadowshift_schema(db_path)
    d = clean_event_frame(frame)
    keys = ("event_id", "study_id", "owner", "observed_at", "event_type", "station", "interruption_min",
            "recovery_min", "people_affected", "suspected_cause", "evidence_strength", "evidence_source", "notes", "created_at")
    with sqlite3.connect(db_path, timeout=30) as conn:
        if not conn.execute("SELECT 1 FROM shadowshift_studies WHERE study_id=? AND owner=?", (study_id, owner)).fetchone():
            raise ValueError("Study not found for the current owner.")
        conn.execute("DELETE FROM shadowshift_events WHERE study_id=? AND owner=?", (study_id, owner))
        for record in d.to_dict("records"):
            item = _event_record(record, study_id, owner)
            conn.execute("""INSERT INTO shadowshift_events
                (event_id,study_id,owner,observed_at,event_type,station,interruption_min,recovery_min,
                 people_affected,suspected_cause,evidence_strength,evidence_source,notes,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(item[k] for k in keys))
        conn.execute("UPDATE shadowshift_studies SET updated_at=? WHERE study_id=? AND owner=?", (_now(), study_id, owner))
        conn.commit()
    return len(d)


def calculate_loss_metrics(
    events: pd.DataFrame, observation_window_min: float, shift_window_min: float = 480,
    shifts_per_year: float = 250, loaded_hourly_rate_sar: float = 0, downstream_stress_factor: float = 1,
) -> dict[str, float | int | bool]:
    """Calculate observed data and separately labelled projections."""
    d = clean_event_frame(events)
    window = max(1.0, _num(observation_window_min, 60))
    shift = max(1.0, _num(shift_window_min, 480))
    shifts = max(0.0, _num(shifts_per_year, 250))
    rate = max(0.0, _num(loaded_hourly_rate_sar, 0))
    stress = max(1.0, min(3.0, _num(downstream_stress_factor, 1)))
    interruption = float(d["Interruption min"].sum()) if not d.empty else 0.0
    recovery = float(d["Recovery min"].sum()) if not d.empty else 0.0
    elapsed = interruption + recovery
    labor_min = float(((d["Interruption min"] + d["Recovery min"]) * d["People affected"]).sum()) if not d.empty else 0.0
    n = int(len(d))
    window_factor = min(shift / window, 1.0e6) if n else 0.0
    per_shift = elapsed * window_factor
    labor_hours_shift = (labor_min / window) * shift / 60.0 if n else 0.0
    annual_hours = labor_hours_shift * shifts
    return {
        "event_count": n,
        "interruption_minutes_observed": interruption,
        "recovery_minutes_observed": recovery,
        "observed_elapsed_burden_minutes": elapsed,
        "people_weighted_labor_minutes_observed": labor_min,
        "recovery_share_percent": recovery / elapsed * 100.0 if elapsed else 0.0,
        "high_evidence_events": int((d["Evidence strength (1-5)"] >= 4).sum()) if n else 0,
        "mean_evidence_strength": float(d["Evidence strength (1-5)"].mean()) if n else 0.0,
        "observation_window_minutes": window, "shift_window_minutes": shift,
        "projection_factor": window_factor, "projected_elapsed_burden_minutes_per_shift": per_shift,
        "projected_labor_hours_per_shift": labor_hours_shift, "shifts_per_year": shifts,
        "annual_projected_labor_hours": annual_hours, "loaded_hourly_rate_sar": rate,
        "annual_gross_labor_exposure_sar": annual_hours * rate,
        "downstream_stress_factor": stress,
        "modeled_downstream_extra_minutes_per_shift": max(0.0, stress - 1.0) * per_shift,
        "is_extrapolation": bool(n and window < shift),
    }


def rank_next_experiments(events: pd.DataFrame) -> pd.DataFrame:
    """Prioritize tests using burden, evidence gap, repeat count and test effort."""
    columns = ["Rank", "Cause", "Observed events", "Observed burden min", "Mean evidence (1-5)",
               "Evidence gap", "Priority score (relative)", "Hypothesis", "Prediction", "Recommended test",
               "Primary metric", "Target observations", "Effort min", "Control", "Test condition"]
    d = clean_event_frame(events)
    rows = []
    causes = list(d.groupby("Suspected cause", dropna=False)) if not d.empty else [("Unknown / not yet tested", pd.DataFrame())]
    for cause, group in causes:
        key = str(cause) if str(cause) in CAUSE_PLAYBOOK else "Unknown / not yet tested"
        play = CAUSE_PLAYBOOK[key]
        count = int(len(group))
        burden = float(((group["Interruption min"] + group["Recovery min"]) * group["People affected"]).sum()) if count else 0.0
        strength = float(group["Evidence strength (1-5)"].mean()) if count else 0.0
        gap = max(0.05, 1.0 - strength / 5.0) if count else 1.0
        raw = max(0.1, burden) * gap * math.sqrt(max(1, count)) / max(1.0, float(play["effort_min"]))
        rows.append({
            "Cause": key, "Observed events": count, "Observed burden min": burden,
            "Mean evidence (1-5)": strength, "Evidence gap": gap, "_raw": raw,
            "Hypothesis": play["hypothesis"], "Prediction": play["prediction"], "Recommended test": play["test"],
            "Primary metric": play["metric"], "Target observations": play["target_n"],
            "Effort min": play["effort_min"], "Control": play["control"], "Test condition": play["treatment"],
        })
    out = pd.DataFrame(rows)
    out["Priority score (relative)"] = (out["_raw"] / max(float(out["_raw"].max()), 1e-12) * 100).round(1)
    out = out.sort_values(["Priority score (relative)", "Observed burden min"], ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", range(1, len(out) + 1))
    return out.drop(columns=["_raw"])[columns]


def save_experiment(study_id: str, owner: str, design: dict[str, Any], db_path: str = DB_PATH) -> str:
    ensure_shadowshift_schema(db_path)
    eid, now = "SSX-" + uuid.uuid4().hex[:10].upper(), _now()
    with sqlite3.connect(db_path, timeout=30) as conn:
        if not conn.execute("SELECT 1 FROM shadowshift_studies WHERE study_id=? AND owner=?", (study_id, owner)).fetchone():
            raise ValueError("Study not found for the current owner.")
        conn.execute("""INSERT INTO shadowshift_experiments
            (experiment_id,study_id,owner,hypothesis,comparison_condition,test_condition,primary_metric,unit,
             target_n,planned_minutes,expected_direction,status,result_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, study_id, owner, _text(design.get("hypothesis"), 1000), _text(design.get("comparison_condition"), 500),
             _text(design.get("test_condition"), 500), _text(design.get("primary_metric"), 180), _text(design.get("unit"), 60),
             max(1, min(100000, int(_num(design.get("target_n"), 5)))),
             max(1.0, _num(design.get("planned_minutes"), 20)), _text(design.get("expected_direction"), 80) or "Decrease",
             "Planned", "{}", now, now))
        conn.commit()
    return eid


def list_experiments(study_id: str, owner: str, db_path: str = DB_PATH) -> pd.DataFrame:
    ensure_shadowshift_schema(db_path)
    with sqlite3.connect(db_path, timeout=30) as conn:
        return pd.read_sql_query("""SELECT experiment_id AS 'Experiment ID',hypothesis AS 'Hypothesis',
            comparison_condition AS 'Comparison',test_condition AS 'Test condition',primary_metric AS 'Primary metric',
            unit AS 'Unit',target_n AS 'Target n',planned_minutes AS 'Planned min',
            expected_direction AS 'Expected direction',status AS 'Status',result_json AS 'Result',created_at AS 'Created at'
            FROM shadowshift_experiments WHERE study_id=? AND owner=? ORDER BY created_at DESC""", conn, params=(study_id, owner))


def record_experiment_result(experiment_id: str, study_id: str, owner: str, result: dict[str, Any], db_path: str = DB_PATH) -> bool:
    payload = {
        "control_value": _num(result.get("control_value")), "test_value": _num(result.get("test_value")),
        "unit": _text(result.get("unit"), 60), "conclusion": _text(result.get("conclusion"), 80),
        "observations_completed": max(0, int(_num(result.get("observations_completed")))),
        "notes": _text(result.get("notes"), 2000), "recorded_at": _now(),
    }
    with sqlite3.connect(db_path, timeout=30) as conn:
        cur = conn.execute("""UPDATE shadowshift_experiments SET result_json=?,status='Measured',updated_at=?
            WHERE experiment_id=? AND study_id=? AND owner=?""",
            (json.dumps(payload, sort_keys=True), _now(), experiment_id, study_id, owner))
        conn.commit()
        return cur.rowcount == 1


def save_analysis_snapshot(study_id: str, owner: str, assumptions: dict[str, Any], analysis: dict[str, Any],
                           events: pd.DataFrame, db_path: str = DB_PATH) -> tuple[str, str]:
    ensure_shadowshift_schema(db_path)
    evidence_hash = hashlib.sha256(clean_event_frame(events).to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()
    sid = "SSN-" + uuid.uuid4().hex[:12].upper()
    with sqlite3.connect(db_path, timeout=30) as conn:
        if not conn.execute("SELECT 1 FROM shadowshift_studies WHERE study_id=? AND owner=?", (study_id, owner)).fetchone():
            raise ValueError("Study not found for the current owner.")
        conn.execute("INSERT INTO shadowshift_snapshots VALUES(?,?,?,?,?,?,?)", (
            sid, study_id, owner, json.dumps(assumptions, sort_keys=True, default=str),
            json.dumps(analysis, sort_keys=True, default=str), evidence_hash, _now()))
        conn.commit()
    return sid, evidence_hash


def load_snapshots(study_id: str, owner: str, db_path: str = DB_PATH) -> pd.DataFrame:
    ensure_shadowshift_schema(db_path)
    with sqlite3.connect(db_path, timeout=30) as conn:
        return pd.read_sql_query("""SELECT snapshot_id AS 'Snapshot ID',evidence_sha256 AS 'Evidence SHA-256',
            created_at AS 'Created at' FROM shadowshift_snapshots WHERE study_id=? AND owner=? ORDER BY created_at DESC""",
            conn, params=(study_id, owner))


def _synthetic_events() -> pd.DataFrame:
    now = pd.Timestamp.now(tz="UTC")
    source = [
        ("Waiting / blocked", "Assembly A", 6, 4, 2, "Material / tool availability", 2),
        ("Searching for tools or information", "Assembly A", 3, 2, 1, "Layout / travel", 2),
        ("Handoff / communication", "Inspection B", 5, 3, 1, "Handoff / communication", 3),
        ("Equipment stop / reset", "CNC-02", 8, 9, 1, "Equipment / reset", 3),
        ("Quality check / rework", "Inspection B", 2, 7, 2, "Quality / rework", 3),
        ("Waiting / blocked", "Assembly A", 7, 3, 2, "Material / tool availability", 3),
        ("Method variation", "Packing C", 2, 4, 1, "Work method / standard", 2),
        ("Scheduling / release delay", "Packing C", 4, 2, 1, "Scheduling / release", 2),
    ]
    rows = []
    for i, (typ, station, interrupt, recovery, people, cause, evidence) in enumerate(source, start=1):
        rows.append({
            "Event ID": f"SYNTHETIC-{i:03d}",
            "Observed at": (now - pd.Timedelta(minutes=(len(source)-i)*7)).isoformat(timespec="seconds"),
            "Event type": typ, "Station": station, "Interruption min": interrupt, "Recovery min": recovery,
            "People affected": people, "Suspected cause": cause, "Evidence strength (1-5)": evidence,
            "Evidence source": "Synthetic demo", "Notes": "SYNTHETIC DEMO ONLY — fictional example record.",
        })
    return clean_event_frame(pd.DataFrame(rows))


def render_shadowshift(tier: str, username: str) -> None:
    """Render the authenticated user's complete ShadowShift workspace."""
    import streamlit as st
    import plotly.express as px

    owner = _text(username, 120) or "unknown"
    try:
        studies = list_studies(owner)
        if studies.empty:
            create_study(owner)
            studies = list_studies(owner)
        key = "shadowshift_active_" + hashlib.sha1(owner.encode("utf-8")).hexdigest()[:10]
        current = st.session_state.get(key)
        ids = studies["study_id"].astype(str).tolist()
        if current not in ids:
            current = ids[0]
        st.session_state[key] = current

        st.markdown("""<div style="padding:22px 24px;border-radius:20px;background:linear-gradient(120deg,#0b1220,#15314b 58%,#155e75);color:#f8fafc;margin-bottom:12px">
        <div style="font-size:11px;letter-spacing:.16em;font-weight:800;color:#67e8f9">OPERATIONS INTELLIGENCE · EVIDENCE FIRST</div>
        <div style="font-size:30px;font-weight:850;line-height:1.15;margin-top:8px">ShadowShift</div>
        <div style="font-size:14px;color:#dbeafe;max-width:1000px;margin-top:8px">Measure interruptions and recovery separately. Find where observed burden concentrates. Register the next low-cost experiment before claiming a root cause.</div></div>""", unsafe_allow_html=True)
        st.caption("Enterprise tool · Synthetic demo data is explicitly labeled · No universal savings claims · Observe only with site permission and approved safety procedures.")

        labels = {str(r["study_id"]): f'{r["name"]} · {r["study_id"]}' for _, r in studies.iterrows()}
        c1, c2 = st.columns([4, 1])
        selected = c1.selectbox("Active study", list(labels), index=list(labels).index(current), format_func=lambda x: labels[x], key=key)
        if c2.button("＋ New study", use_container_width=True, key="shadowshift_new_study"):
            sid = create_study(owner)
            st.session_state[key] = sid
            st.rerun()
        study_id = str(selected)
        study = load_study(study_id, owner)
        if not study:
            st.error("Study is not available for this account.")
            return

        events = load_events(study_id, owner)
        metrics = calculate_loss_metrics(events, study["observation_window_min"], study["shift_window_min"],
            study["shifts_per_year"], study["loaded_hourly_rate_sar"], study["downstream_stress_factor"])
        cols = st.columns(5)
        cols[0].metric("Observed events", f'{metrics["event_count"]:,}')
        cols[1].metric("Interruption", f'{metrics["interruption_minutes_observed"]:,.1f} min')
        cols[2].metric("Recovery", f'{metrics["recovery_minutes_observed"]:,.1f} min')
        cols[3].metric("Observed burden", f'{metrics["observed_elapsed_burden_minutes"]:,.1f} min')
        cols[4].metric("High-evidence events", f'{metrics["high_evidence_events"]:,}')
        demo = not events.empty and events["Evidence source"].eq("Synthetic demo").any()
        if demo:
            st.warning("This study contains SYNTHETIC DEMO records. Do not present their metrics as factory observations.")
        elif events.empty:
            st.info("No events recorded yet. Log an interruption or load the clearly marked synthetic example.")

        tabs = st.tabs(["Capture & Log", "Loss Map", "Next Experiment", "Evidence & Export", "Study Setup"])
        with tabs[0]:
            st.markdown("#### Capture interruption and recovery separately")
            st.write("Interruption = time blocked or diverted. Recovery = extra time until normal, stable work resumes.")
            timer_key = "shadowshift_timer_" + hashlib.sha1(f"{owner}|{study_id}".encode()).hexdigest()[:10]
            timer = st.session_state.get(timer_key)
            timer_type = st.selectbox("Timer event type", EVENT_TYPES, key=timer_key + "_type")
            timer_station = st.text_input("Timer station / step", "Unspecified station", key=timer_key + "_station")
            left, right = st.columns(2)
            if timer is None:
                if left.button("▶ Start interruption timer", type="primary", use_container_width=True, key=timer_key + "_start"):
                    st.session_state[timer_key] = {"started": datetime.now(timezone.utc).timestamp(), "type": timer_type, "station": timer_station}
                    st.rerun()
            else:
                elapsed = max(0.0, datetime.now(timezone.utc).timestamp() - float(timer["started"]))
                left.info(f"Timer running · about {elapsed/60:.1f} min elapsed")
                if right.button("■ Stop & log interruption", type="primary", use_container_width=True, key=timer_key + "_stop"):
                    duration = max(0.0, (datetime.now(timezone.utc).timestamp() - float(timer["started"])) / 60)
                    add_event(study_id, owner, {
                        "Observed at": _now(), "Event type": timer["type"], "Station": timer["station"],
                        "Interruption min": round(duration, 3), "Recovery min": 0, "People affected": 1,
                        "Suspected cause": "Unknown / not yet tested", "Evidence strength (1-5)": 4,
                        "Evidence source": "Direct observation",
                        "Notes": "Measured by ShadowShift stopwatch; add recovery separately in editable log.",
                    })
                    st.session_state.pop(timer_key, None)
                    st.success(f"Recorded {duration:.2f} interruption minutes. Recovery remains separate.")
                    st.rerun()

            with st.form(f"shadowshift_manual_event_{study_id}"):
                a, b, c = st.columns(3)
                typ = a.selectbox("Event type", EVENT_TYPES)
                station = b.text_input("Station / step", "Assembly A")
                cause = c.selectbox("Suspected cause (not confirmed)", CAUSES, index=len(CAUSES)-1)
                d, e, f = st.columns(3)
                interrupt = d.number_input("Interruption minutes", min_value=0.0, max_value=100000.0, value=1.0, step=0.5)
                recovery = e.number_input("Recovery to stable work (min)", min_value=0.0, max_value=100000.0, value=0.0, step=0.5)
                people = f.number_input("People affected", min_value=1, max_value=10000, value=1, step=1)
                g, h = st.columns(2)
                strength = g.slider("Evidence strength", 1, 5, 3, help="1 = weak/inferred; 5 = directly verified. Not a statistical confidence interval.")
                source = h.selectbox("Evidence source", EVIDENCE_SOURCES[:-1])
                notes = st.text_area("Observed fact / note (avoid unsupported cause claims)", height=70)
                submitted = st.form_submit_button("＋ Add observed event", type="primary", use_container_width=True)
                if submitted:
                    add_event(study_id, owner, {
                        "Observed at": _now(), "Event type": typ, "Station": station, "Interruption min": interrupt,
                        "Recovery min": recovery, "People affected": people, "Suspected cause": cause,
                        "Evidence strength (1-5)": strength, "Evidence source": source, "Notes": notes,
                    })
                    st.success("Event recorded.")
                    st.rerun()

            events = load_events(study_id, owner)
            if not events.empty:
                st.markdown("#### Editable evidence log")
                edited = st.data_editor(events, use_container_width=True, hide_index=True, num_rows="dynamic", key=f"shadowshift_editor_{study_id}")
                save_col, delete_col = st.columns([1, 2])
                if save_col.button("💾 Save log edits", type="primary", use_container_width=True, key=f"shadowshift_save_{study_id}"):
                    try:
                        count = replace_events(study_id, owner, edited)
                        st.success(f"Saved {count} event rows to this account's study.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not save log edits: {exc}")
                pick = delete_col.selectbox("Remove event", ["— Keep all events —"] + events["Event ID"].astype(str).tolist(), key=f"shadowshift_delete_pick_{study_id}")
                if delete_col.button("Delete selected event", use_container_width=True, key=f"shadowshift_delete_{study_id}") and pick != "— Keep all events —":
                    with sqlite3.connect(DB_PATH, timeout=30) as conn:
                        conn.execute("DELETE FROM shadowshift_events WHERE event_id=? AND study_id=? AND owner=?", (pick, study_id, owner))
                        conn.commit()
                    st.rerun()

            with st.expander("Load synthetic worked example", expanded=False):
                st.caption("Adds eight fictional events. Never mix them with a real study.")
                if st.button("Load synthetic example", key=f"shadowshift_demo_{study_id}"):
                    if not events.empty:
                        st.warning("This study already contains events. Create a separate study before loading synthetic data.")
                    else:
                        replace_events(study_id, owner, _synthetic_events())
                        st.rerun()

            with st.expander("Import existing event log", expanded=False):
                upload = st.file_uploader("CSV or Excel event log", type=["csv", "xlsx"], key=f"shadowshift_upload_{study_id}")
                st.caption("Recognized columns include Event type, Station, Interruption min, Recovery min, People affected, Suspected cause, Evidence strength, Evidence source and Notes.")
                if upload is not None and st.button("Append imported events", key=f"shadowshift_import_{study_id}"):
                    try:
                        imported = pd.read_excel(upload) if upload.name.lower().endswith(".xlsx") else pd.read_csv(upload)
                        normalized = clean_event_frame(imported)
                        combined = pd.concat([load_events(study_id, owner), normalized], ignore_index=True)
                        replace_events(study_id, owner, combined)
                        st.success(f"Imported {len(normalized):,} rows. Review the mappings in the editable log.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Import failed safely: {exc}")

        with tabs[1]:
            st.markdown("#### Where observed loss concentrates")
            events = load_events(study_id, owner)
            metrics = calculate_loss_metrics(events, study["observation_window_min"], study["shift_window_min"],
                study["shifts_per_year"], study["loaded_hourly_rate_sar"], study["downstream_stress_factor"])
            if events.empty:
                st.info("Record or import event rows to generate the loss map.")
            else:
                chart1, chart2 = st.columns(2)
                event_burden = events.assign(**{"Observed burden min": events["Interruption min"] + events["Recovery min"]})
                by_type = event_burden.groupby("Event type", as_index=False).agg(**{"Observed burden min": ("Observed burden min", "sum"), "Events": ("Event ID", "count")}).sort_values("Observed burden min", ascending=False)
                by_station = event_burden.groupby("Station", as_index=False).agg(**{"Observed burden min": ("Observed burden min", "sum"), "Events": ("Event ID", "count")}).sort_values("Observed burden min", ascending=False)
                fig1 = px.bar(by_type, x="Event type", y="Observed burden min", color="Events", title="Observed burden by event type")
                fig1.update_layout(height=350, xaxis_title=None, margin=dict(l=10, r=10, t=55, b=10))
                chart1.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(by_station, x="Station", y="Observed burden min", color="Events", title="Observed burden by station / step")
                fig2.update_layout(height=350, xaxis_title=None, margin=dict(l=10, r=10, t=55, b=10))
                chart2.plotly_chart(fig2, use_container_width=True)
                compare = pd.DataFrame([
                    {"Quantity": "Interruption", "Value": metrics["interruption_minutes_observed"], "Status": "Observed"},
                    {"Quantity": "Recovery", "Value": metrics["recovery_minutes_observed"], "Status": "Observed"},
                    {"Quantity": "Recorded total burden", "Value": metrics["observed_elapsed_burden_minutes"], "Status": "Observed"},
                    {"Quantity": "Per-shift burden", "Value": metrics["projected_elapsed_burden_minutes_per_shift"], "Status": "Modelled extrapolation" if metrics["is_extrapolation"] else "Observed-window equivalent"},
                    {"Quantity": "Downstream stress increment", "Value": metrics["modeled_downstream_extra_minutes_per_shift"], "Status": "Scenario only"},
                ])
                st.dataframe(compare, use_container_width=True, hide_index=True)
                if metrics["is_extrapolation"]:
                    st.warning(f"Per-shift values scale a {metrics['observation_window_minutes']:.0f}-minute observation window by {metrics['projection_factor']:.2f}. Validate with representative shifts.")
                if events["Evidence source"].eq("Synthetic demo").any():
                    st.warning("Synthetic demo rows are present; charts are illustrative, not plant evidence.")

        with tabs[2]:
            st.markdown("#### Next best observation")
            st.write("A transparent heuristic ranks high-burden patterns with weak evidence and affordable tests. It helps choose what to investigate; it does not prove causation.")
            events = load_events(study_id, owner)
            ranked = rank_next_experiments(events)
            st.dataframe(ranked[["Rank", "Cause", "Observed events", "Observed burden min", "Mean evidence (1-5)", "Priority score (relative)"]], use_container_width=True, hide_index=True)
            top = ranked.iloc[0].to_dict()
            st.markdown("##### Recommended low-cost test")
            st.markdown(f"**Hypothesis:** {top['Hypothesis']}")
            st.markdown(f"**Prediction:** {top['Prediction']}")
            st.write(top["Recommended test"])
            st.caption(f"Metric: {top['Primary metric']} · Target: {int(top['Target observations'])} observations · Effort: {int(top['Effort min'])} min · Control: {top['Control']}")

            with st.form(f"shadowshift_register_{study_id}"):
                candidate_causes = ranked["Cause"].drop_duplicates().astype(str).tolist()
                selected_cause = st.selectbox("Hypothesis to register", candidate_causes)
                play = CAUSE_PLAYBOOK[selected_cause]
                comparison = st.text_input("Control / comparison condition", value=play["control"])
                treatment = st.text_input("Proposed test condition", value=play["treatment"])
                metric = st.text_input("Primary metric", value=play["metric"])
                unit = st.text_input("Metric unit", value="minutes")
                target_n = st.number_input("Target observations", min_value=1, max_value=100000, value=int(play["target_n"]), step=1)
                effort = st.number_input("Planned effort (minutes)", min_value=1.0, max_value=100000.0, value=float(play["effort_min"]), step=5.0)
                direction = st.selectbox("Expected direction", ["Decrease", "Increase", "No worse than", "Difference / unknown"])
                if st.form_submit_button("＋ Register experiment before testing", type="primary", use_container_width=True):
                    eid = save_experiment(study_id, owner, {
                        "hypothesis": f"{selected_cause}: {play['hypothesis']}", "comparison_condition": comparison,
                        "test_condition": treatment, "primary_metric": metric, "unit": unit, "target_n": target_n,
                        "planned_minutes": effort, "expected_direction": direction,
                    })
                    st.success(f"Experiment {eid} registered.")
                    st.rerun()

            experiments = list_experiments(study_id, owner)
            if not experiments.empty:
                st.markdown("#### Experiment register")
                st.dataframe(experiments.drop(columns=["Result"], errors="ignore"), use_container_width=True, hide_index=True)
                experiment_labels = {str(r["Experiment ID"]): f'{r["Experiment ID"]} · {str(r["Hypothesis"])[:70]}' for _, r in experiments.iterrows()}
                chosen = st.selectbox("Record a measured result", list(experiment_labels), format_func=lambda x: experiment_labels[x], key=f"shadowshift_result_pick_{study_id}")
                current_result = {}
                try:
                    current_result = json.loads(str(experiments.loc[experiments["Experiment ID"].astype(str).eq(chosen), "Result"].iloc[0] or "{}"))
                except Exception:
                    pass
                with st.form(f"shadowshift_result_{chosen}"):
                    x, y = st.columns(2)
                    control_value = x.number_input("Control / baseline value", value=float(current_result.get("control_value", 0)), key=f"ss_control_{chosen}")
                    test_value = y.number_input("Test condition value", value=float(current_result.get("test_value", 0)), key=f"ss_test_{chosen}")
                    unit_result = st.text_input("Recorded unit", value=str(current_result.get("unit", "")), key=f"ss_unit_{chosen}")
                    n_done = st.number_input("Observations completed", min_value=0, max_value=100000, value=int(current_result.get("observations_completed", 0)), key=f"ss_n_{chosen}")
                    conclusions = ["Inconclusive", "Supports hypothesis", "Does not support hypothesis", "Mixed / needs replication"]
                    old_conclusion = current_result.get("conclusion", "Inconclusive")
                    conclusion = st.selectbox("Evidence conclusion", conclusions, index=conclusions.index(old_conclusion) if old_conclusion in conclusions else 0, key=f"ss_conclusion_{chosen}")
                    result_notes = st.text_area("Result notes / limitations", value=str(current_result.get("notes", "")), key=f"ss_notes_{chosen}")
                    if st.form_submit_button("Save measured result"):
                        if record_experiment_result(chosen, study_id, owner, {
                            "control_value": control_value, "test_value": test_value, "unit": unit_result,
                            "observations_completed": n_done, "conclusion": conclusion, "notes": result_notes,
                        }):
                            st.success("Result saved. It is evidence for review, not by itself causal proof.")
                            st.rerun()
                        else:
                            st.error("Experiment not found in this study.")

        with tabs[3]:
            st.markdown("#### Evidence and decision-ready outputs")
            st.caption("Observed facts, modelled exposure and scenario-only stress are separated. Exposure is not a savings claim.")
            events = load_events(study_id, owner)
            metrics = calculate_loss_metrics(events, study["observation_window_min"], study["shift_window_min"],
                study["shifts_per_year"], study["loaded_hourly_rate_sar"], study["downstream_stress_factor"])
            a, b, c = st.columns(3)
            a.metric("Projected labor hours / shift", f'{metrics["projected_labor_hours_per_shift"]:,.2f}')
            b.metric("Annual gross labor exposure", f'SAR {metrics["annual_gross_labor_exposure_sar"]:,.0f}')
            c.metric("Scenario stress increment", f'{metrics["modeled_downstream_extra_minutes_per_shift"]:,.1f} min/shift')
            st.caption("Annual exposure extrapolates sample burden and applies the supplied loaded hourly rate. It excludes throughput, customer, overtime and margin effects; it is gross exposure, not recoverable value.")
            report = {
                "module": MODULE_NAME, "generated_at": _now(),
                "study": {k: study.get(k) for k in ("study_id", "name", "process_name", "observation_window_min",
                    "shift_window_min", "shifts_per_year", "loaded_hourly_rate_sar", "downstream_stress_factor", "notes")},
                "analysis": metrics, "evidence": events.to_dict("records"),
                "next_experiment_ranking": rank_next_experiments(events).to_dict("records"),
                "experiments": list_experiments(study_id, owner).to_dict("records"),
                "claims_policy": {"annual_exposure": "Modelled extrapolation, not measured savings.",
                    "downstream_stress": "Scenario-only, not an observed loss or causal estimate.",
                    "root_cause": "Hypotheses require controlled observation and replication."},
            }
            jdata = json.dumps(report, indent=2, default=str, ensure_ascii=False)
            left, right = st.columns(2)
            left.download_button("⬇ Download event log (CSV)", events.to_csv(index=False), f"shadowshift_{study_id.lower()}_events.csv", "text/csv", use_container_width=True)
            right.download_button("⬇ Download evidence report (JSON)", jdata, f"shadowshift_{study_id.lower()}_report.json", "application/json", use_container_width=True)
            if st.button("🔐 Save snapshot + evidence hash", type="primary", use_container_width=True, key=f"shadowshift_snapshot_{study_id}"):
                assumptions = {k: study.get(k) for k in ("observation_window_min", "shift_window_min", "shifts_per_year", "loaded_hourly_rate_sar", "downstream_stress_factor")}
                sid, sha = save_analysis_snapshot(study_id, owner, assumptions, metrics, events)
                st.success(f"Snapshot {sid} saved. Event-log SHA-256: {sha}")
            snapshots = load_snapshots(study_id, owner)
            if not snapshots.empty:
                st.markdown("#### Saved evidence snapshots")
                st.dataframe(snapshots, use_container_width=True, hide_index=True)

        with tabs[4]:
            st.markdown("#### Study definition and assumptions")
            st.caption("Set coverage and costing assumptions explicitly. The downstream factor is a scenario stress multiplier, not a measured causal effect.")
            with st.form(f"shadowshift_settings_{study_id}"):
                name = st.text_input("Study name", value=str(study["name"]), max_chars=180)
                process = st.text_input("Process / area", value=str(study["process_name"] or ""))
                x, y, z = st.columns(3)
                window = x.number_input("Observed window (minutes)", min_value=1.0, max_value=1000000.0, value=float(study["observation_window_min"]), step=5.0)
                shift = y.number_input("Nominal shift window (minutes)", min_value=1.0, max_value=1000000.0, value=float(study["shift_window_min"]), step=30.0)
                shifts = z.number_input("Shifts per year", min_value=0.0, max_value=10000.0, value=float(study["shifts_per_year"]), step=10.0)
                r, s = st.columns(2)
                rate = r.number_input("Loaded labor cost (SAR / person-hour)", min_value=0.0, max_value=1000000.0, value=float(study["loaded_hourly_rate_sar"]), step=5.0)
                stress = s.slider("Downstream stress factor (scenario only)", min_value=1.0, max_value=3.0, value=float(study["downstream_stress_factor"]), step=0.1)
                notes = st.text_area("Context, exclusions and protocol", value=str(study["notes"] or ""), height=90)
                if st.form_submit_button("Save study settings", type="primary", use_container_width=True):
                    update_study(study_id, owner, {"name": name, "process_name": process,
                        "observation_window_min": window, "shift_window_min": shift, "shifts_per_year": shifts,
                        "loaded_hourly_rate_sar": rate, "downstream_stress_factor": stress, "notes": notes})
                    st.success("Study settings saved.")
                    st.rerun()
            st.markdown("#### Calculation definitions")
            st.markdown(
                "- **Observed burden** = sum(interruption minutes + recovery minutes).\n"
                "- **People-weighted labor minutes** = sum((interruption + recovery) × people affected).\n"
                "- **Per-shift projection** = observed burden ÷ observed-window minutes × nominal shift minutes.\n"
                "- **Annual gross labor exposure** = projected people-weighted hours/shift × shifts/year × loaded hourly labor cost.\n"
                "- **Downstream stress increment** = projected burden × (stress factor − 1); scenario-only and excluded from labor costing.\n"
                "- **Next-experiment priority** = people-weighted burden × evidence gap × square-root(event count) ÷ estimated test effort; rescaled to 0–100 relative to the top candidate.\n\n"
                "These calculations support decisions; they do not establish causation. Use representative samples, matched comparisons and replication before changing standard work."
            )
    except Exception as exc:
        st.error("ShadowShift encountered a recoverable rendering issue. Other Shoir-IE modules remain available.")
        with st.expander("ShadowShift diagnostic", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}")
