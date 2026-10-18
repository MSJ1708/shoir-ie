"""Evidence-linked production bottleneck and capacity-recovery study.

This is a deterministic screening model, not a discrete-event simulation and not a
claim about actual plant output. It makes assumptions explicit, validates inputs,
hashes the study contract, scopes saved records to an owner, and supports later
comparison with source-referenced operational outcomes.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd

DB_PATH = "enterprise_full_workspace.db"
CALCULATION_VERSION = "capacity-recovery/1.0.0"
MAX_STATIONS = 200
MAX_IMPORT_ROWS = 1000
MAX_IMPORT_COLUMNS = 100
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

STATION_COLUMNS = (
    "Station",
    "Cycle Time (sec/unit)",
    "Available Time (min/shift)",
    "Availability (%)",
    "Parallel Resources",
    "Scenario Cycle Time (sec/unit)",
    "Scenario Availability (%)",
    "Scenario Parallel Resources",
)
BASELINE_IMPORT_FIELDS = (
    "Station",
    "Cycle Time (sec/unit)",
    "Available Time (min/shift)",
    "Availability (%)",
    "Parallel Resources",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shoir_capacity_recovery_studies (
    study_id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    study_name TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    result_sha256 TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    results_json TEXT NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT NOT NULL,
    data_source TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_capacity_studies_owner_created
    ON shoir_capacity_recovery_studies(owner, created_at DESC);
CREATE TABLE IF NOT EXISTS shoir_capacity_recovery_outcomes (
    outcome_id TEXT PRIMARY KEY,
    study_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    expected_good_units REAL NOT NULL,
    actual_good_units REAL NOT NULL,
    variance_units REAL NOT NULL,
    variance_pct REAL,
    tolerance_pct REAL NOT NULL,
    within_tolerance INTEGER NOT NULL,
    measurement_period TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    notes TEXT NOT NULL,
    study_input_sha256 TEXT NOT NULL,
    outcome_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(study_id) REFERENCES shoir_capacity_recovery_studies(study_id)
);
CREATE INDEX IF NOT EXISTS idx_capacity_outcomes_owner_study
    ON shoir_capacity_recovery_outcomes(owner, study_id, created_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _finite_number(
    value: Any,
    field: str,
    *,
    minimum: float | None = 0.0,
    maximum: float | None = None,
) -> float:
    """Parse a numeric input without silently replacing invalid values."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite; NaN and infinity are not allowed.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field} must be at least {minimum:g}.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} must be no more than {maximum:g}.")
    return number


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite values cannot be included in a reproducible study payload.")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def starter_station_table() -> pd.DataFrame:
    """Clearly synthetic starter inputs; replace these before a real plant study."""
    return pd.DataFrame(
        [
            {
                "Station": "Cutting",
                "Cycle Time (sec/unit)": 40.0,
                "Available Time (min/shift)": 420.0,
                "Availability (%)": 90.0,
                "Parallel Resources": 1,
                "Scenario Cycle Time (sec/unit)": 38.0,
                "Scenario Availability (%)": 92.0,
                "Scenario Parallel Resources": 1,
            },
            {
                "Station": "Assembly",
                "Cycle Time (sec/unit)": 55.0,
                "Available Time (min/shift)": 420.0,
                "Availability (%)": 85.0,
                "Parallel Resources": 1,
                "Scenario Cycle Time (sec/unit)": 45.0,
                "Scenario Availability (%)": 92.0,
                "Scenario Parallel Resources": 1,
            },
            {
                "Station": "Inspection",
                "Cycle Time (sec/unit)": 75.0,
                "Available Time (min/shift)": 420.0,
                "Availability (%)": 96.0,
                "Parallel Resources": 1,
                "Scenario Cycle Time (sec/unit)": 70.0,
                "Scenario Availability (%)": 96.0,
                "Scenario Parallel Resources": 1,
            },
        ],
        columns=STATION_COLUMNS,
    )


def _normalize_station_table(stations: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(stations, pd.DataFrame):
        raise ValueError("Station inputs must be provided as a table.")
    if stations.empty:
        raise ValueError("Add at least one station before calculating capacity.")
    if len(stations) > MAX_STATIONS:
        raise ValueError(f"A study can contain at most {MAX_STATIONS} stations.")
    if stations.columns.duplicated().any():
        raise ValueError("Station input columns must have unique names.")

    missing = [column for column in STATION_COLUMNS if column not in stations.columns]
    if missing:
        raise ValueError("Station table is missing required columns: " + ", ".join(missing))

    frame = stations.loc[:, list(STATION_COLUMNS)].copy()
    if frame["Station"].isna().any():
        raise ValueError("Every station must have a name.")
    frame["Station"] = frame["Station"].astype(str).str.strip()
    if frame["Station"].eq("").any():
        raise ValueError("Every station must have a non-empty name.")
    duplicate_names = frame["Station"].str.casefold().duplicated(keep=False)
    if duplicate_names.any():
        repeated = sorted(frame.loc[duplicate_names, "Station"].unique().tolist())
        raise ValueError("Station names must be unique (case-insensitive): " + ", ".join(repeated))

    numeric_rules = {
        "Cycle Time (sec/unit)": (0.0, 1e9, False),
        "Available Time (min/shift)": (0.0, 1e6, False),
        "Availability (%)": (0.0, 100.0, False),
        "Parallel Resources": (1.0, 10000.0, True),
        "Scenario Cycle Time (sec/unit)": (0.0, 1e9, False),
        "Scenario Availability (%)": (0.0, 100.0, False),
        "Scenario Parallel Resources": (1.0, 10000.0, True),
    }
    for column, (minimum, maximum, integer_only) in numeric_rules.items():
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.isna().any():
            bad_rows = (series.isna()).to_numpy().nonzero()[0]
            raise ValueError(f"{column} has missing or non-numeric values at row(s): " + ", ".join(str(int(i) + 1) for i in bad_rows[:10]))
        if not series.map(lambda x: math.isfinite(float(x))).all():
            raise ValueError(f"{column} must contain only finite values.")
        if (series < minimum).any():
            qualifier = "greater than zero" if minimum == 0 and "Cycle Time" in column else f"at least {minimum:g}"
            raise ValueError(f"{column} must be {qualifier}.")
        if maximum is not None and (series > maximum).any():
            raise ValueError(f"{column} must not exceed {maximum:g}.")
        if integer_only and not series.map(lambda x: float(x).is_integer()).all():
            raise ValueError(f"{column} must contain whole-number resource counts.")
        frame[column] = series.astype(int) if integer_only else series.astype(float)

    # Available time may be zero for a planned shutdown; cycle time must be > 0.
    for column in ("Cycle Time (sec/unit)", "Scenario Cycle Time (sec/unit)"):
        if (frame[column] <= 0).any():
            raise ValueError(f"{column} must be greater than zero.")
    return frame.reset_index(drop=True)


def read_station_upload(payload: bytes, filename: str) -> pd.DataFrame:
    """Read a bounded CSV or XLSX upload without trusting its filename or headers."""
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError("Uploaded file contents must be bytes.")
    if not payload:
        raise ValueError("The uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Uploads are limited to {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB.")
    name = str(filename or "").strip().casefold()
    try:
        if name.endswith(".csv"):
            text = bytes(payload).decode("utf-8-sig")
            try:
                header = next(csv.reader(io.StringIO(text, newline="")))
            except StopIteration as exc:
                raise ValueError("The CSV file is empty.") from exc
            normalized_header = [str(item).strip() for item in header]
            if any(not item for item in normalized_header):
                raise ValueError("Every imported column needs a non-empty header.")
            if len(normalized_header) > MAX_IMPORT_COLUMNS:
                raise ValueError(f"Imports are limited to {MAX_IMPORT_COLUMNS} columns.")
            if pd.Index(normalized_header).duplicated().any():
                raise ValueError("The CSV contains duplicate column names after trimming whitespace.")
            frame = pd.read_csv(io.BytesIO(bytes(payload)), nrows=MAX_IMPORT_ROWS + 1)
        elif name.endswith(".xlsx"):
            frame = pd.read_excel(io.BytesIO(bytes(payload)), sheet_name=0, nrows=MAX_IMPORT_ROWS + 1, engine="openpyxl")
        else:
            raise ValueError("Only CSV and XLSX files are supported.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"The file could not be parsed as a valid {'.csv' if name.endswith('.csv') else '.xlsx'} workbook.") from exc

    if frame.empty:
        raise ValueError("The file contains no data rows.")
    if len(frame) > MAX_IMPORT_ROWS:
        raise ValueError(f"Imports are limited to {MAX_IMPORT_ROWS} station rows.")
    if len(frame.columns) > MAX_IMPORT_COLUMNS:
        raise ValueError(f"Imports are limited to {MAX_IMPORT_COLUMNS} columns.")
    frame.columns = [str(column).strip() for column in frame.columns]
    if any(not column for column in frame.columns):
        raise ValueError("Every imported column needs a non-empty header.")
    if pd.Index(frame.columns).duplicated().any():
        raise ValueError("The imported table contains duplicate column names after normalization.")
    return frame


def map_imported_station_data(frame: pd.DataFrame, column_mapping: Mapping[str, str]) -> pd.DataFrame:
    """Map imported data columns into the baseline schema; initialize scenario to baseline.

    Scenario columns intentionally start equal to the baseline. An engineer must
    edit the proposed scenario explicitly rather than inheriting hidden improvements.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("The imported file contains no tabular records.")
    if len(frame) > MAX_IMPORT_ROWS:
        raise ValueError(f"Imports are limited to {MAX_IMPORT_ROWS} station rows.")
    if frame.columns.duplicated().any():
        raise ValueError("The imported table contains duplicate column names.")
    missing_targets = [field for field in BASELINE_IMPORT_FIELDS if field not in column_mapping]
    if missing_targets:
        raise ValueError("Choose a source column for: " + ", ".join(missing_targets))
    mapped_sources = [column_mapping[field] for field in BASELINE_IMPORT_FIELDS]
    if any(source not in frame.columns for source in mapped_sources):
        raise ValueError("A mapped source column no longer exists in the uploaded table.")
    if len(set(mapped_sources)) != len(mapped_sources):
        raise ValueError("Each engineering field must map to a different source column.")

    imported = pd.DataFrame(
        {field: frame[column_mapping[field]].copy() for field in BASELINE_IMPORT_FIELDS}
    )
    imported["Scenario Cycle Time (sec/unit)"] = imported["Cycle Time (sec/unit)"]
    imported["Scenario Availability (%)"] = imported["Availability (%)"]
    imported["Scenario Parallel Resources"] = imported["Parallel Resources"]
    return _normalize_station_table(imported)


def analyze_capacity_recovery(
    stations: pd.DataFrame,
    demand_units_per_shift: float,
    overall_first_pass_yield_pct: float = 100.0,
) -> dict[str, Any]:
    """Calculate deterministic line-capacity bounds and a transparent what-if scenario."""
    frame = _normalize_station_table(stations)
    demand = _finite_number(demand_units_per_shift, "Demand (good units/shift)", maximum=1e12)
    yield_pct = _finite_number(
        overall_first_pass_yield_pct, "Overall first-pass yield (%)", maximum=100.0
    )

    baseline = (
        frame["Available Time (min/shift)"] * 60.0
        * frame["Parallel Resources"] / frame["Cycle Time (sec/unit)"]
        * frame["Availability (%)"] / 100.0
    )
    proposed = (
        frame["Available Time (min/shift)"] * 60.0
        * frame["Scenario Parallel Resources"] / frame["Scenario Cycle Time (sec/unit)"]
        * frame["Scenario Availability (%)"] / 100.0
    )
    min_baseline = float(baseline.min())
    min_proposed = float(proposed.min())
    baseline_bottlenecks = frame.loc[baseline.sub(min_baseline).abs() <= 1e-9, "Station"].tolist()
    scenario_bottlenecks = frame.loc[proposed.sub(min_proposed).abs() <= 1e-9, "Station"].tolist()
    baseline_good = min_baseline * yield_pct / 100.0
    proposed_good = min_proposed * yield_pct / 100.0

    def summary(gross: float, good: float, bottlenecks: list[str]) -> dict[str, Any]:
        gap = max(0.0, demand - good)
        return {
            "bottleneck_stations": bottlenecks,
            "gross_capacity_units_per_shift": gross,
            "good_capacity_units_per_shift": good,
            "demand_units_per_shift": demand,
            "shortfall_units_per_shift": gap,
            "surplus_units_per_shift": max(0.0, good - demand),
            "capacity_coverage_pct": (good / demand * 100.0) if demand > 0 else None,
        }

    station_results = frame.copy()
    station_results["Baseline Capacity (units/shift)"] = baseline
    station_results["Scenario Capacity (units/shift)"] = proposed
    station_results["Baseline Binding Constraint"] = baseline.sub(min_baseline).abs() <= 1e-9
    station_results["Scenario Binding Constraint"] = proposed.sub(min_proposed).abs() <= 1e-9

    normalized_inputs = {
        "calculation_version": CALCULATION_VERSION,
        "stations": frame.to_dict("records"),
        "demand_units_per_shift": demand,
        "overall_first_pass_yield_pct": yield_pct,
    }
    delta_units = proposed_good - baseline_good
    return {
        "calculation_version": CALCULATION_VERSION,
        "classification": "Calculated deterministic capacity estimate",
        "input_sha256": _sha256(normalized_inputs),
        "assumptions": [
            "Stations are treated as a serial line processing a comparable unit.",
            "Station capacity = available minutes × 60 × parallel resources ÷ cycle time × availability fraction.",
            "Overall first-pass yield is applied once to the line bottleneck capacity.",
            "Buffering, blocking, starvation, product mix, rework, finite setup schedules and stochastic variation are not simulated.",
            "Fractional units are theoretical capacity equivalents, not a promise of integer realized output.",
        ],
        "baseline": summary(min_baseline, baseline_good, baseline_bottlenecks),
        "scenario": summary(min_proposed, proposed_good, scenario_bottlenecks),
        "delta": {
            "additional_good_units_per_shift": delta_units,
            "capacity_change_pct": (delta_units / baseline_good * 100.0) if baseline_good > 0 else None,
        },
        "station_results": station_results,
        "warnings": [
            "Replace the synthetic starter values with reviewed plant data before using this result for an operational decision.",
            "This is a deterministic capacity screening model, not a calibrated digital twin or discrete-event simulation.",
            "A bottleneck flag identifies the lowest calculated station capacity; it does not prove root cause or guarantee the benefit of a proposed change.",
        ],
    }


def calculate_capacity_value_sensitivity(
    additional_good_units_per_shift: float,
    operating_shifts_per_year: float,
    contribution_or_avoided_cost_per_unit: float,
    implementation_cost: float,
) -> dict[str, Any]:
    """Calculate a user-assumption sensitivity, explicitly classified as an estimate."""
    delta = _finite_number(additional_good_units_per_shift, "Additional good units/shift", minimum=-1e12, maximum=1e12)
    shifts = _finite_number(operating_shifts_per_year, "Operating shifts/year", maximum=1e6)
    unit_value = _finite_number(contribution_or_avoided_cost_per_unit, "Contribution or avoided cost per unit", maximum=1e12)
    implementation = _finite_number(implementation_cost, "Implementation cost", maximum=1e15)
    annual_units = delta * shifts
    annual_gross = annual_units * unit_value
    annual_net = annual_gross - implementation
    if not all(math.isfinite(value) for value in (annual_units, annual_gross, annual_net)):
        raise ValueError("Financial sensitivity exceeded the finite numeric range.")
    roi = (annual_net / implementation * 100.0) if implementation > 0 else None
    payback = (implementation / (annual_gross / 12.0)) if implementation > 0 and annual_gross > 0 else None
    return {
        "classification": "Estimated scenario sensitivity — not realized savings",
        "additional_good_units_per_shift": delta,
        "operating_shifts_per_year": shifts,
        "modeled_incremental_units_per_year": annual_units,
        "assumed_value_per_unit": unit_value,
        "modeled_annual_gross_value": annual_gross,
        "implementation_cost": implementation,
        "modeled_first_year_net_value": annual_net,
        "roi_percent": roi,
        "payback_months": payback,
    }


def ensure_capacity_recovery_db(db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(_SCHEMA)
        connection.commit()


def _result_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    station_results = payload.get("station_results")
    if isinstance(station_results, pd.DataFrame):
        payload["station_results"] = station_results.to_dict("records")
    return payload


def save_capacity_study(
    owner: str,
    study_name: str,
    stations: pd.DataFrame,
    demand_units_per_shift: float,
    overall_first_pass_yield_pct: float = 100.0,
    *,
    data_source: str = "Manual station inputs",
    operating_shifts_per_year: float = 0.0,
    contribution_or_avoided_cost_per_unit: float = 0.0,
    implementation_cost: float = 0.0,
    decision: str = "Investigate bottleneck",
    rationale: str = "",
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """Persist a reproducible, owner-scoped study and return its provenance record."""
    owner_value = str(owner or "").strip()
    name = str(study_name or "").strip()
    source = str(data_source or "").strip()
    decision_value = str(decision or "").strip()
    rationale_value = str(rationale or "").strip()
    if not owner_value:
        raise ValueError("A signed-in owner is required to save a study.")
    if not name or len(name) > 120:
        raise ValueError("Study name must contain 1–120 characters.")
    if not source or len(source) > 500:
        raise ValueError("A data-source reference of 1–500 characters is required.")
    if not decision_value or len(decision_value) > 120:
        raise ValueError("A decision state of 1–120 characters is required.")
    if len(rationale_value) > 4000:
        raise ValueError("Decision rationale must be 4,000 characters or fewer.")

    frame = _normalize_station_table(stations)
    demand = _finite_number(demand_units_per_shift, "Demand (good units/shift)")
    yield_pct = _finite_number(overall_first_pass_yield_pct, "Overall first-pass yield (%)", maximum=100.0)
    shifts = _finite_number(operating_shifts_per_year, "Operating shifts/year")
    unit_value = _finite_number(contribution_or_avoided_cost_per_unit, "Contribution or avoided cost per unit")
    implementation = _finite_number(implementation_cost, "Implementation cost")

    analysis = analyze_capacity_recovery(frame, demand, yield_pct)
    sensitivity = calculate_capacity_value_sensitivity(
        analysis["delta"]["additional_good_units_per_shift"],
        shifts, unit_value, implementation,
    )
    inputs = {
        "stations": frame.to_dict("records"),
        "demand_units_per_shift": demand,
        "overall_first_pass_yield_pct": yield_pct,
        "operating_shifts_per_year": shifts,
        "contribution_or_avoided_cost_per_unit": unit_value,
        "implementation_cost": implementation,
        "data_source": source,
    }
    input_hash = _sha256({"calculation_version": CALCULATION_VERSION, "inputs": inputs})
    result = _result_payload(analysis)
    result["financial_sensitivity"] = sensitivity
    result["data_source"] = source
    result_hash = _sha256(result)
    created = _now()
    study_id = "CAP-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8].upper()

    ensure_capacity_recovery_db(db_path)
    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """INSERT INTO shoir_capacity_recovery_studies
               (study_id,owner,study_name,calculation_version,input_sha256,result_sha256,
                inputs_json,results_json,decision,rationale,data_source,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                study_id, owner_value, name, CALCULATION_VERSION, input_hash, result_hash,
                _canonical_json(inputs), _canonical_json(result), decision_value,
                rationale_value, source, created,
            ),
        )
        connection.commit()
    return load_capacity_study(study_id, owner_value, db_path=db_path) or {}


def list_capacity_studies(
    owner: str, *, limit: int = 50, db_path: str = DB_PATH
) -> pd.DataFrame:
    owner_value = str(owner or "").strip()
    if not owner_value:
        return pd.DataFrame(columns=["study_id", "study_name", "created_at", "decision", "input_sha256", "result_sha256"])
    take = int(limit)
    if take < 1 or take > 200:
        raise ValueError("Study-list limit must be between 1 and 200.")
    ensure_capacity_recovery_db(db_path)
    with sqlite3.connect(db_path, timeout=30) as connection:
        return pd.read_sql_query(
            """SELECT study_id,study_name,created_at,decision,input_sha256,result_sha256
               FROM shoir_capacity_recovery_studies
               WHERE owner=? ORDER BY created_at DESC LIMIT ?""",
            connection, params=(owner_value, take),
        )


def load_capacity_study(
    study_id: str, owner: str, *, db_path: str = DB_PATH
) -> dict[str, Any] | None:
    owner_value = str(owner or "").strip()
    id_value = str(study_id or "").strip()
    if not owner_value or not id_value:
        return None
    ensure_capacity_recovery_db(db_path)
    with sqlite3.connect(db_path, timeout=30) as connection:
        row = connection.execute(
            """SELECT study_id,owner,study_name,calculation_version,input_sha256,result_sha256,
                      inputs_json,results_json,decision,rationale,data_source,created_at
               FROM shoir_capacity_recovery_studies WHERE study_id=? AND owner=?""",
            (id_value, owner_value),
        ).fetchone()
    if row is None:
        return None
    return {
        "study_id": row[0],
        "owner": row[1],
        "study_name": row[2],
        "calculation_version": row[3],
        "input_sha256": row[4],
        "result_sha256": row[5],
        "inputs": json.loads(row[6]),
        "results": json.loads(row[7]),
        "decision": row[8],
        "rationale": row[9],
        "data_source": row[10],
        "created_at": row[11],
    }


def record_capacity_outcome(
    study_id: str,
    owner: str,
    actual_good_units_per_shift: float,
    *,
    measurement_period: str,
    source_reference: str,
    tolerance_pct: float = 5.0,
    notes: str = "",
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """Compare a saved scenario to a user-submitted, source-referenced actual.

    The tolerance check is arithmetic; the platform cannot authenticate the
    underlying source or claim independent verification merely because it exists.
    """
    study = load_capacity_study(study_id, owner, db_path=db_path)
    if study is None:
        raise ValueError("The requested study does not exist for this owner.")
    actual = _finite_number(actual_good_units_per_shift, "Actual good units/shift")
    tolerance = _finite_number(tolerance_pct, "Tolerance (%)", maximum=100.0)
    period = str(measurement_period or "").strip()
    source = str(source_reference or "").strip()
    notes_value = str(notes or "").strip()
    if not period or len(period) > 120:
        raise ValueError("Measurement period must contain 1–120 characters.")
    if not source or len(source) > 500:
        raise ValueError("A source reference is required for measured outcomes (1–500 characters).")
    if len(notes_value) > 4000:
        raise ValueError("Outcome notes must be 4,000 characters or fewer.")

    expected = float(study["results"]["scenario"]["good_capacity_units_per_shift"])
    variance = actual - expected
    variance_pct = (variance / expected * 100.0) if expected > 0 else None
    within = abs(variance_pct) <= tolerance if variance_pct is not None else actual == 0.0
    created = _now()
    outcome_id = "OUT-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8].upper()
    body = {
        "outcome_id": outcome_id,
        "study_id": study["study_id"],
        "owner": study["owner"],
        "expected_good_units_per_shift": expected,
        "actual_good_units_per_shift": actual,
        "variance_units_per_shift": variance,
        "variance_pct": variance_pct,
        "tolerance_pct": tolerance,
        "within_tolerance": within,
        "measurement_period": period,
        "source_reference": source,
        "notes": notes_value,
        "study_input_sha256": study["input_sha256"],
        "calculation_version": study["calculation_version"],
        "created_at": created,
    }
    outcome_hash = _sha256(body)
    ensure_capacity_recovery_db(db_path)
    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """INSERT INTO shoir_capacity_recovery_outcomes
               (outcome_id,study_id,owner,expected_good_units,actual_good_units,variance_units,
                variance_pct,tolerance_pct,within_tolerance,measurement_period,source_reference,
                notes,study_input_sha256,outcome_sha256,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                outcome_id, study["study_id"], study["owner"], expected, actual, variance,
                variance_pct, tolerance, int(within), period, source, notes_value,
                study["input_sha256"], outcome_hash, created,
            ),
        )
        connection.commit()
    body["outcome_sha256"] = outcome_hash
    body["classification"] = "Measured input with source reference; source authenticity not independently verified"
    return body


def list_capacity_outcomes(
    study_id: str, owner: str, *, db_path: str = DB_PATH
) -> pd.DataFrame:
    study = load_capacity_study(study_id, owner, db_path=db_path)
    if study is None:
        return pd.DataFrame(columns=[
            "outcome_id", "measurement_period", "expected_good_units",
            "actual_good_units", "variance_units", "variance_pct",
            "within_tolerance", "source_reference", "created_at",
        ])
    ensure_capacity_recovery_db(db_path)
    with sqlite3.connect(db_path, timeout=30) as connection:
        return pd.read_sql_query(
            """SELECT outcome_id,measurement_period,expected_good_units,actual_good_units,
                      variance_units,variance_pct,tolerance_pct,within_tolerance,
                      source_reference,outcome_sha256,created_at
               FROM shoir_capacity_recovery_outcomes
               WHERE study_id=? AND owner=? ORDER BY created_at DESC""",
            connection, params=(study["study_id"], study["owner"]),
        )
