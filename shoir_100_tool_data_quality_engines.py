"""Bounded data mapping and safety trend methods for Shoir-IE targets T015/T050."""
from __future__ import annotations

import math
import re
from typing import Any, Mapping

import pandas as pd


CANONICAL_INDUSTRIAL_FIELDS = {
    "timestamp": {
        "label": "Timestamp",
        "aliases": ["timestamp", "datetime", "date_time", "event_time", "recorded_at", "time_stamp"],
        "description": "Observation/event time; clarify timezone before time-series analysis.",
    },
    "asset_id": {
        "label": "Asset ID",
        "aliases": ["asset", "asset_id", "equipment_id", "machine_id", "equipment", "machine"],
        "description": "Stable identifier of the machine or asset.",
    },
    "process_id": {
        "label": "Process ID",
        "aliases": ["process", "process_id", "operation_id", "operation", "process_step"],
        "description": "Stable identifier for the production process or operation.",
    },
    "product_id": {
        "label": "Product ID",
        "aliases": ["product", "product_id", "sku", "item_code", "part_number", "part_id"],
        "description": "Identifier of the produced or handled product.",
    },
    "order_id": {
        "label": "Order ID",
        "aliases": ["order", "order_id", "work_order", "work_order_id", "job_id", "production_order"],
        "description": "Production/work order or job identifier.",
    },
    "shift": {
        "label": "Shift",
        "aliases": ["shift", "shift_name", "crew", "work_shift"],
        "description": "Shift/crew label.",
    },
    "operator_id": {
        "label": "Operator ID",
        "aliases": ["operator", "operator_id", "employee_id", "worker_id", "staff_id"],
        "description": "Operator/worker identifier; treat as potentially personal data.",
    },
    "units_produced": {
        "label": "Units produced",
        "aliases": ["units_produced", "produced_units", "output_qty", "production_qty", "quantity_produced", "total_units"],
        "description": "Total produced units over the stated window.",
    },
    "good_units": {
        "label": "Good units",
        "aliases": ["good_units", "good_qty", "accepted_units", "conforming_units"],
        "description": "Units accepted as conforming to the stated definition.",
    },
    "defect_count": {
        "label": "Defect count",
        "aliases": ["defect_count", "defects", "defective_units", "ng_count", "reject_count"],
        "description": "Defects or defective units; clarify which count convention is used.",
    },
    "downtime_minutes": {
        "label": "Downtime (minutes)",
        "aliases": ["downtime", "downtime_minutes", "down_time_min", "unplanned_downtime_minutes", "stop_minutes"],
        "description": "Downtime minutes for the stated period.",
    },
    "cycle_time_seconds": {
        "label": "Cycle time (seconds)",
        "aliases": ["cycle_time", "cycle_time_seconds", "ct_sec", "cycle_sec", "processing_time_seconds"],
        "description": "Cycle time in seconds; confirm unit before comparing with other sources.",
    },
    "planned_production_minutes": {
        "label": "Planned production time (minutes)",
        "aliases": ["planned_production_minutes", "planned_time_min", "available_production_minutes", "planned_runtime_minutes"],
        "description": "Time planned for production; confirm availability definition.",
    },
    "energy_kwh": {
        "label": "Energy (kWh)",
        "aliases": ["energy_kwh", "kwh", "energy_consumption_kwh", "electricity_kwh", "consumption_kwh"],
        "description": "Energy quantity in kWh; do not map other energy units without conversion.",
    },
    "scrap_units": {
        "label": "Scrap units",
        "aliases": ["scrap", "scrap_units", "scrapped_units", "scrap_qty"],
        "description": "Units scrapped under the declared defect/cost convention.",
    },
    "demand_units": {
        "label": "Demand (units)",
        "aliases": ["demand", "demand_units", "forecast_demand", "required_qty", "order_demand"],
        "description": "Demand quantity within the stated time bucket.",
    },
}


def _normalize_column(value: Any) -> str:
    raw = str(value or "").strip().casefold()
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")


def map_industrial_fields(
    columns: list[str] | tuple[str, ...],
    manual_mapping: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Suggest canonical mappings and apply explicit user overrides without renaming source columns."""
    source_columns = [str(col) for col in columns]
    if not source_columns:
        raise ValueError("At least one source column is required.")
    if any(not col.strip() for col in source_columns):
        raise ValueError("Source columns must have non-empty names.")
    if len({col.casefold() for col in source_columns}) != len(source_columns):
        raise ValueError("Source column names must be unique ignoring case.")
    overrides = dict(manual_mapping or {})
    unknown_override_sources = sorted(set(overrides) - set(source_columns))
    if unknown_override_sources:
        raise ValueError("Manual mapping refers to missing source columns: " + ", ".join(unknown_override_sources))
    canonical_ids = set(CANONICAL_INDUSTRIAL_FIELDS)
    invalid_targets = sorted({str(value) for value in overrides.values() if value not in canonical_ids and value != ""})
    if invalid_targets:
        raise ValueError("Manual mapping contains unknown canonical target(s): " + ", ".join(invalid_targets))

    alias_index = {}
    for field_id, metadata in CANONICAL_INDUSTRIAL_FIELDS.items():
        for alias in [field_id, *metadata["aliases"]]:
            alias_index[_normalize_column(alias)] = field_id
    rows = []
    for source in source_columns:
        normalized = _normalize_column(source)
        suggested = alias_index.get(normalized)
        if source in overrides:
            selected = str(overrides[source])
            status = "MANUALLY_MAPPED" if selected else "UNMAPPED"
            confidence = "USER_CONFIRMED" if selected else "NO_MAPPING"
            mapping = selected or None
        else:
            mapping = suggested
            status = "SUGGESTED_REVIEW_REQUIRED" if suggested else "UNMAPPED"
            confidence = "HIGH_ALIAS_MATCH_NEEDS_CONFIRMATION" if suggested else "NO_MAPPING"
        meta = CANONICAL_INDUSTRIAL_FIELDS.get(mapping or "", {})
        rows.append({
            "source_column": source,
            "normalized_source": normalized,
            "suggested_canonical_field": suggested or "",
            "canonical_field": mapping or "",
            "canonical_label": meta.get("label", ""),
            "mapping_status": status,
            "confidence": confidence,
            "units_or_semantics": meta.get("description", ""),
            "original_column_preserved": source,
        })
    mapped = [row["canonical_field"] for row in rows if row["canonical_field"]]
    duplicates = sorted({field for field in mapped if mapped.count(field) > 1})
    if duplicates:
        for row in rows:
            if row["canonical_field"] in duplicates:
                row["mapping_status"] = "DUPLICATE_CANONICAL_TARGET_REVIEW"
    result_frame = pd.DataFrame(rows)
    return {
        "tool_id": "T015",
        "status": "MAPPING_PREVIEW",
        "method": "Alias-based industrial field suggestions plus explicit user-confirmed overrides",
        "assumptions": [
            "Suggestions are based only on normalized field names and a versioned internal alias dictionary.",
            "A suggested name match is not proof that the source data uses the expected units or business definition.",
            "The original source column names are returned unchanged; this function does not mutate the source dataset.",
        ],
        "warnings": [
            "Review every suggested mapping and unit before running downstream calculations.",
            "Duplicate canonical targets require human review; no source columns are merged or discarded.",
        ],
        "metrics": {
            "source_column_count": int(len(source_columns)),
            "suggested_or_confirmed_count": int(sum(bool(field) for field in mapped)),
            "unmapped_count": int((result_frame["mapping_status"] == "UNMAPPED").sum()),
            "duplicate_target_count": int(len(duplicates)),
            "canonical_dictionary_version": "shoir-industrial-fields-v1",
        },
        "mapping_table": result_frame,
        "duplicate_canonical_targets": duplicates,
        "original_columns": source_columns,
    }


def analyze_safety_incident_trends(
    rows: Any,
    *,
    rate_denominator_hours: float = 200_000.0,
) -> dict[str, Any]:
    """Summarize incidents and rates per exposure hours; do not infer causal effects."""
    frame = rows.copy(deep=True) if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    required = {"period", "incident_category", "incident_count", "exposure_hours"}
    if frame.empty:
        raise ValueError("Safety incident data requires at least one row.")
    if frame.columns.has_duplicates:
        raise ValueError("Safety incident data must have unique column names.")
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Safety incident data is missing columns: " + ", ".join(missing))
    denominator = float(rate_denominator_hours)
    if not math.isfinite(denominator) or denominator <= 0:
        raise ValueError("Rate denominator hours must be finite and greater than zero.")
    if len(frame) > 10000:
        raise ValueError("Safety incident data is limited to 10000 rows.")
    data = []
    for ix, raw in enumerate(frame.to_dict(orient="records"), start=1):
        period = str(raw.get("period") or "").strip()
        category = str(raw.get("incident_category") or "").strip()
        if not period or not category:
            raise ValueError(f"Incident row {ix} requires a period and incident category.")
        try:
            count = float(raw.get("incident_count"))
            hours = float(raw.get("exposure_hours"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Incident row {ix} count and exposure hours must be numeric.") from exc
        if not math.isfinite(count) or count < 0 or not count.is_integer():
            raise ValueError(f"Incident row {ix} incident_count must be a non-negative integer.")
        if not math.isfinite(hours) or hours < 0:
            raise ValueError(f"Incident row {ix} exposure_hours must be finite and non-negative.")
        data.append({
            "period": period, "incident_category": category,
            "incident_count": int(count), "exposure_hours": hours,
        })
    table = pd.DataFrame(data)
    # Each period's exposure denominator must be provided only once or be identical
    # for every category row; summing repeated denominators would double-count hours.
    exposure_counts = table.groupby("period", dropna=False)["exposure_hours"].nunique()
    if (exposure_counts > 1).any():
        periods = exposure_counts[exposure_counts > 1].index.tolist()
        raise ValueError("Exposure hours must be identical across category rows for a period to prevent denominator double counting: " + ", ".join(map(str, periods)))
    duplicated = table.duplicated(["period", "incident_category"], keep=False)
    if duplicated.any():
        raise ValueError("Each period/category combination must be unique. Aggregate duplicate rows before analysis.")
    period_exposure = table.groupby("period", as_index=False)["exposure_hours"].first()
    period_counts = table.groupby("period", as_index=False)["incident_count"].sum()
    period_summary = period_counts.merge(period_exposure, on="period", validate="one_to_one")
    period_summary["incidents_per_rate_denominator_hours"] = period_summary.apply(
        lambda row: row["incident_count"] / row["exposure_hours"] * denominator if row["exposure_hours"] > 0 else None,
        axis=1,
    )
    period_summary["rate_denominator_hours"] = denominator
    category_summary = table.groupby("incident_category", as_index=False).agg(
        incident_count=("incident_count", "sum"),
    )
    total_exposure = float(period_exposure["exposure_hours"].sum())
    total_incidents = int(period_summary["incident_count"].sum())
    total_rate = total_incidents / total_exposure * denominator if total_exposure > 0 else None
    category_summary["share_of_reported_incidents_percent"] = (
        category_summary["incident_count"] / total_incidents * 100 if total_incidents > 0 else None
    )
    category_summary = category_summary.sort_values(["incident_count", "incident_category"], ascending=[False, True], kind="stable").reset_index(drop=True)
    period_summary = period_summary.sort_values(["period"], kind="stable").reset_index(drop=True)
    return {
        "tool_id": "T050",
        "status": "CALCULATED",
        "method": "Incident counts and exposure-hour-normalized rates",
        "formula": "Incident rate = incident count / exposure hours × configured denominator (default 200000 hours)",
        "assumptions": [
            "Counts and exposure hours use compatible period and organizational boundaries.",
            "The exposure denominator is counted once per period even when a category breakdown is supplied.",
            "The rate denominator defaults to 200,000 exposure hours and is an explicit configuration, not a jurisdiction-specific reporting rule.",
        ],
        "warnings": [
            "Trend association does not establish causation; category rates may be unstable for small counts.",
            "Verify reporting definitions, exposure-hour completeness, near-miss inclusion and organizational boundaries before comparing rates.",
            "A period with zero exposure hours has no defined rate; the rate is left blank rather than treated as zero.",
        ],
        "metrics": {
            "period_count": int(len(period_summary)),
            "incident_count": total_incidents,
            "exposure_hours": total_exposure,
            "overall_incident_rate": total_rate,
            "rate_denominator_hours": denominator,
            "incident_categories": int(category_summary["incident_category"].nunique()),
        },
        "period_summary": period_summary,
        "category_summary": category_summary,
    }
