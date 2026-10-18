"""Validated production-capacity and downtime-recovery calculation service.

Pure calculations only: no factory connection, persistence, or claim that a scenario
predicts actual performance. Numeric errors are reported rather than silently coerced
to zero or clipped.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd

FORMULA_VERSION = "capacity-recovery/1.0.0"
REQUIRED_COLUMNS = ("Line", "PlannedMin", "DowntimeMin", "IdealCycleSec", "TotalCount", "GoodCount")
NUMERIC_COLUMNS = REQUIRED_COLUMNS[1:]


def _finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def validate_production_events(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate production rows without mutating input or replacing bad values."""
    if not isinstance(events, pd.DataFrame):
        raise TypeError("Production events must be a pandas DataFrame.")
    errors: list[str] = []
    warnings: list[str] = []
    if events.columns.duplicated().any():
        errors.append("Duplicate column names are not allowed.")
    missing = [column for column in REQUIRED_COLUMNS if column not in events.columns]
    if missing:
        errors.extend(f"Missing required column: {column}" for column in missing)
        return events.copy(deep=True), {
            "valid": False, "errors": errors, "warnings": warnings,
            "rows": len(events), "required_columns": list(REQUIRED_COLUMNS),
        }
    if events.empty:
        errors.append("Production events are empty.")

    frame = events.loc[:, list(REQUIRED_COLUMNS)].copy(deep=True)
    line_values = frame["Line"].astype("string").str.strip()
    bad_lines = line_values.isna() | line_values.eq("")
    if bool(bad_lines.any()):
        errors.append(f"Line must be non-empty for every row ({int(bad_lines.sum())} invalid).")
    frame["Line"] = line_values

    for column in NUMERIC_COLUMNS:
        converted = pd.to_numeric(frame[column], errors="coerce")
        invalid = converted.isna() | ~converted.map(_finite_number)
        if bool(invalid.any()):
            errors.append(f"{column} contains {int(invalid.sum())} missing, non-numeric, or non-finite value(s).")
        frame[column] = converted

    ready = frame.loc[:, list(NUMERIC_COLUMNS)].notna().all(axis=1)
    if bool(ready.any()):
        valid_rows = frame.loc[ready]
        for column in ("PlannedMin", "IdealCycleSec"):
            bad = valid_rows[column] <= 0
            if bool(bad.any()):
                errors.append(f"{column} must be greater than zero ({int(bad.sum())} invalid row(s)).")
        for column in ("DowntimeMin", "TotalCount", "GoodCount"):
            bad = valid_rows[column] < 0
            if bool(bad.any()):
                errors.append(f"{column} cannot be negative ({int(bad.sum())} invalid row(s)).")
        bad_downtime = valid_rows["DowntimeMin"] > valid_rows["PlannedMin"]
        if bool(bad_downtime.any()):
            errors.append(f"DowntimeMin exceeds PlannedMin in {int(bad_downtime.sum())} row(s).")
        bad_good = valid_rows["GoodCount"] > valid_rows["TotalCount"]
        if bool(bad_good.any()):
            errors.append(f"GoodCount exceeds TotalCount in {int(bad_good.sum())} row(s).")
        no_runtime = (
            (valid_rows["PlannedMin"] <= valid_rows["DowntimeMin"])
            & (valid_rows["TotalCount"] > 0)
        )
        if bool(no_runtime.any()):
            errors.append("Rows with production output must have positive runtime after downtime.")
        zero_output = valid_rows["TotalCount"] == 0
        if bool(zero_output.any()):
            warnings.append(f"{int(zero_output.sum())} row(s) report zero output; performance and quality interpretation may be limited.")
        runtime = valid_rows["PlannedMin"] - valid_rows["DowntimeMin"]
        perf = valid_rows["TotalCount"] * valid_rows["IdealCycleSec"] / (runtime.replace(0, float("nan")) * 60.0)
        if bool((perf > 1.0 + 1e-9).fillna(False).any()):
            warnings.append("Observed output exceeds ideal-cycle capacity in one or more rows; check cycle-time units and data quality. Values are not capped.")

    return frame, {
        "valid": not errors, "errors": errors, "warnings": warnings,
        "rows": int(len(frame)), "required_columns": list(REQUIRED_COLUMNS),
    }


def calculate_line_metrics(events: pd.DataFrame) -> pd.DataFrame:
    """Calculate availability, performance, quality, OEE and theoretical capacity.

    Availability = runtime / planned time.
    Performance = total count × ideal cycle seconds / runtime seconds.
    Quality = good count / total count.
    OEE = availability × performance × quality.
    Performance is not capped at 100%; a value above 100% is a diagnostic.
    """
    frame, report = validate_production_events(events)
    if not report["valid"]:
        raise ValueError("Invalid production events: " + " ".join(report["errors"]))

    frame["_RuntimeMin"] = frame["PlannedMin"] - frame["DowntimeMin"]
    frame["_IdealSeconds"] = frame["TotalCount"] * frame["IdealCycleSec"]
    frame["_TheoreticalCapacity"] = frame["PlannedMin"] * 60.0 / frame["IdealCycleSec"]
    grouped = frame.groupby("Line", sort=False, dropna=False).agg(
        PlannedMin=("PlannedMin", "sum"),
        DowntimeMin=("DowntimeMin", "sum"),
        RuntimeMin=("_RuntimeMin", "sum"),
        TotalCount=("TotalCount", "sum"),
        GoodCount=("GoodCount", "sum"),
        IdealSeconds=("_IdealSeconds", "sum"),
        TheoreticalCapacityUnits=("_TheoreticalCapacity", "sum"),
    )
    grouped["AvailabilityPct"] = grouped["RuntimeMin"] / grouped["PlannedMin"] * 100.0
    grouped["PerformancePct"] = grouped.apply(
        lambda row: row["IdealSeconds"] / (row["RuntimeMin"] * 60.0) * 100.0
        if row["RuntimeMin"] > 0 else 0.0, axis=1,
    )
    grouped["QualityPct"] = grouped.apply(
        lambda row: row["GoodCount"] / row["TotalCount"] * 100.0
        if row["TotalCount"] > 0 else float("nan"), axis=1,
    )
    grouped["OEEPct"] = grouped["AvailabilityPct"] * grouped["PerformancePct"] * grouped["QualityPct"] / 10000.0
    grouped["GoodUnitsPerPlannedHour"] = grouped["GoodCount"] / grouped["PlannedMin"] * 60.0
    grouped["CapacityAtTargetOEE_85Pct"] = grouped["TheoreticalCapacityUnits"] * 0.85
    grouped["OEEStatus"] = grouped["OEEPct"].map(
        lambda value: "Not available" if not _finite_number(value)
        else ("Diagnostic: above 100%" if value > 100.0 else "Calculated")
    )
    grouped.index.name = "Line"
    return grouped.reset_index().drop(columns=["IdealSeconds"])


def estimate_downtime_recovery(events: pd.DataFrame, downtime_reduction_fraction: float) -> pd.DataFrame:
    """Estimate incremental good units if a fraction of observed downtime is recovered.

    This simulated scenario assumes observed row-level performance and quality remain
    unchanged during recovered time. It is not a forecast or a savings guarantee.
    """
    if not _finite_number(downtime_reduction_fraction):
        raise ValueError("Downtime reduction fraction must be a finite number from 0 to 1.")
    fraction = float(downtime_reduction_fraction)
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("Downtime reduction fraction must be between 0 and 1.")
    frame, report = validate_production_events(events)
    if not report["valid"]:
        raise ValueError("Invalid production events: " + " ".join(report["errors"]))

    frame["_RuntimeMin"] = frame["PlannedMin"] - frame["DowntimeMin"]
    frame["_RecoveredMin"] = frame["DowntimeMin"] * fraction
    frame["_ObservedPerformance"] = frame.apply(
        lambda row: row["TotalCount"] * row["IdealCycleSec"] / (row["_RuntimeMin"] * 60.0)
        if row["_RuntimeMin"] > 0 else 0.0, axis=1,
    )
    frame["_ObservedQuality"] = frame.apply(
        lambda row: row["GoodCount"] / row["TotalCount"] if row["TotalCount"] > 0 else 0.0,
        axis=1,
    )
    frame["EstimatedAdditionalGoodUnits"] = (
        frame["_RecoveredMin"] * 60.0 / frame["IdealCycleSec"]
        * frame["_ObservedPerformance"] * frame["_ObservedQuality"]
    )
    result = frame.groupby("Line", sort=False).agg(
        PlannedMin=("PlannedMin", "sum"),
        ObservedDowntimeMin=("DowntimeMin", "sum"),
        RecoveredDowntimeMin=("_RecoveredMin", "sum"),
        ObservedGoodUnits=("GoodCount", "sum"),
        EstimatedAdditionalGoodUnits=("EstimatedAdditionalGoodUnits", "sum"),
    ).reset_index()
    result["ScenarioClassification"] = "Simulated"
    result["Assumption"] = "Observed row-level performance and quality remain unchanged during recovered time."
    return result


def _canonical_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for row in frame.loc[:, list(REQUIRED_COLUMNS)].to_dict(orient="records"):
        records.append({
            key: str(value).strip() if key == "Line" else float(value)
            for key, value in row.items()
        })
    return records


def build_evidence_manifest(
    events: pd.DataFrame,
    line_metrics: pd.DataFrame,
    recovery_scenario: pd.DataFrame | None = None,
    *,
    source_name: str = "user-provided production data",
    source_type: str = "unspecified",
) -> dict[str, Any]:
    """Link input/output hashes and assumptions; hashes do not verify source truth."""
    frame, report = validate_production_events(events)
    if not report["valid"]:
        raise ValueError("Cannot create evidence for invalid data: " + " ".join(report["errors"]))
    input_payload = json.dumps(_canonical_records(frame), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    metrics_payload = line_metrics.to_json(orient="records", double_precision=15, force_ascii=False)
    scenario_payload = recovery_scenario.to_json(orient="records", double_precision=15, force_ascii=False) if recovery_scenario is not None else "null"
    return {
        "manifest_version": "1.0",
        "formula_version": FORMULA_VERSION,
        "source_name": str(source_name)[:240],
        "source_type": str(source_type)[:80],
        "input_sha256": hashlib.sha256(input_payload.encode("utf-8")).hexdigest(),
        "result_sha256": hashlib.sha256((metrics_payload + "|" + scenario_payload).encode("utf-8")).hexdigest(),
        "row_count": int(len(frame)),
        "line_count": int(frame["Line"].nunique()),
        "result_classification": "Calculated",
        "scenario_classification": "Simulated" if recovery_scenario is not None else None,
        "validation": {"valid": report["valid"], "warnings": report["warnings"]},
        "assumptions": [
            "Each row represents a consistent line and reporting interval.",
            "PlannedMin and DowntimeMin use minutes; IdealCycleSec uses seconds per unit.",
            "TotalCount and GoodCount refer to the same reporting interval and product definition.",
            "A source hash provides integrity evidence, not independent verification of source truth.",
        ],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def analyze_capacity_recovery(
    events: pd.DataFrame,
    *,
    downtime_reduction_fraction: float = 0.25,
    source_name: str = "user-provided production data",
    source_type: str = "unspecified",
) -> dict[str, Any]:
    """Run validation, baseline metrics, scenario estimate, and evidence manifest."""
    normalized, validation = validate_production_events(events)
    if not validation["valid"]:
        return {"validation": validation, "line_metrics": pd.DataFrame(),
                "recovery_scenario": pd.DataFrame(), "evidence": None}
    metrics = calculate_line_metrics(normalized)
    scenario = estimate_downtime_recovery(normalized, downtime_reduction_fraction)
    evidence = build_evidence_manifest(
        normalized, metrics, scenario, source_name=source_name, source_type=source_type,
    )
    return {"validation": validation, "line_metrics": metrics,
            "recovery_scenario": scenario, "evidence": evidence}
