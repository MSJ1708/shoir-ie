"""Bounded maintenance, spare-parts and supplier methods for Shoir-IE targets T043/T045/T058."""
from __future__ import annotations

from datetime import date, timedelta
import math
from typing import Any

import numpy as np
import pandas as pd


def _txt(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _frame(value: Any, label: str, max_rows: int = 1000) -> pd.DataFrame:
    frame = value.copy(deep=True) if isinstance(value, pd.DataFrame) else pd.DataFrame(list(value))
    if frame.empty:
        raise ValueError(f"{label} requires at least one row.")
    if frame.columns.has_duplicates:
        raise ValueError(f"{label} must have unique columns.")
    if len(frame) > max_rows:
        raise ValueError(f"{label} is limited to {max_rows} rows.")
    return frame


def _number(value: Any, label: str, *, minimum: float | None = None, strictly_positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    if strictly_positive and number <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return number


def _day(value: Any, label: str) -> date:
    raw = _txt(value)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{label} must use YYYY-MM-DD format.")
    return parsed


def plan_preventive_maintenance(rows: Any, as_of_date: str) -> dict[str, Any]:
    """Calculate calendar due dates and urgency from the declared interval only."""
    frame = _frame(rows, "Maintenance plan")
    required = {"task_id", "asset_id", "task", "interval_days", "last_completed_date", "estimated_duration_hours", "required_skill", "downtime_window"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Maintenance plan is missing columns: " + ", ".join(missing) + ".")
    as_of = _day(as_of_date, "As-of date")
    seen = set()
    output = []
    for ix, raw in enumerate(frame.to_dict(orient="records"), start=1):
        task_id, asset, task = _txt(raw.get("task_id")), _txt(raw.get("asset_id")), _txt(raw.get("task"))
        if not task_id or not asset or not task:
            raise ValueError(f"Maintenance row {ix} requires task_id, asset_id and task.")
        if task_id.casefold() in seen:
            raise ValueError(f"Duplicate maintenance task_id '{task_id}'.")
        seen.add(task_id.casefold())
        interval_value = _number(raw.get("interval_days"), f"Maintenance row {ix} interval_days", strictly_positive=True)
        if not interval_value.is_integer():
            raise ValueError(f"Maintenance row {ix} interval_days must be a whole number.")
        duration = _number(raw.get("estimated_duration_hours"), f"Maintenance row {ix} estimated_duration_hours", strictly_positive=True)
        completed = _day(raw.get("last_completed_date"), f"Maintenance row {ix} last_completed_date")
        if completed > as_of:
            raise ValueError(f"Maintenance row {ix} last_completed_date cannot be after the as-of date.")
        due = completed + timedelta(days=int(interval_value))
        days_until_due = (due - as_of).days
        due_status = "OVERDUE" if days_until_due < 0 else ("DUE_WITHIN_30_DAYS" if days_until_due <= 30 else "SCHEDULED")
        output.append({
            "task_id": task_id, "asset_id": asset, "task": task,
            "last_completed_date": completed.isoformat(),
            "interval_days": int(interval_value), "next_due_date": due.isoformat(),
            "days_until_due": int(days_until_due), "due_status": due_status,
            "estimated_duration_hours": duration,
            "required_skill": _txt(raw.get("required_skill")),
            "downtime_window": _txt(raw.get("downtime_window")),
        })
    plan = pd.DataFrame(output).sort_values(["next_due_date", "task_id"], kind="stable").reset_index(drop=True)
    return {
        "tool_id": "T043",
        "status": "CALCULATED",
        "method": "Interval-based preventive-maintenance due-date calculation",
        "formula": "Next due date = last completed date + interval days",
        "assumptions": [
            "Intervals are calendar days, not working days or runtime hours.",
            "The plan reports due dates only; it does not optimize labor shifts, skills, or simultaneous downtime constraints.",
        ],
        "warnings": ["Check plant-specific maintenance procedures, runtime triggers, labor rules and approved downtime windows before releasing work orders."],
        "metrics": {
            "task_count": int(len(plan)),
            "overdue_tasks": int((plan["due_status"] == "OVERDUE").sum()),
            "due_within_30_days": int((plan["due_status"] == "DUE_WITHIN_30_DAYS").sum()),
            "total_estimated_hours": float(plan["estimated_duration_hours"].sum()),
            "as_of_date": as_of.isoformat(),
        },
        "maintenance_plan": plan,
    }


def plan_spare_part_criticality(
    rows: Any,
    *,
    operating_days_per_year: float = 250,
    service_factor_z: float = 1.645,
) -> dict[str, Any]:
    """Estimate reorder points using a normal lead-time demand approximation."""
    frame = _frame(rows, "Spare-parts input")
    required = {"part_id", "asset_id", "annual_demand", "daily_demand_stddev", "lead_time_days", "unit_cost", "current_stock", "on_order", "criticality_score"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Spare-parts input is missing columns: " + ", ".join(missing) + ".")
    days = _number(operating_days_per_year, "Operating days per year", strictly_positive=True)
    z = _number(service_factor_z, "Service factor z", minimum=0)
    seen, output = set(), []
    for ix, raw in enumerate(frame.to_dict(orient="records"), start=1):
        part, asset = _txt(raw.get("part_id")), _txt(raw.get("asset_id"))
        if not part or not asset:
            raise ValueError(f"Spare-parts row {ix} requires part_id and asset_id.")
        if part.casefold() in seen:
            raise ValueError(f"Duplicate spare part ID '{part}'.")
        seen.add(part.casefold())
        annual = _number(raw.get("annual_demand"), f"Spare-parts row {ix} annual_demand", minimum=0)
        sigma = _number(raw.get("daily_demand_stddev"), f"Spare-parts row {ix} daily_demand_stddev", minimum=0)
        lead = _number(raw.get("lead_time_days"), f"Spare-parts row {ix} lead_time_days", minimum=0)
        cost = _number(raw.get("unit_cost"), f"Spare-parts row {ix} unit_cost", minimum=0)
        stock = _number(raw.get("current_stock"), f"Spare-parts row {ix} current_stock", minimum=0)
        ordered = _number(raw.get("on_order"), f"Spare-parts row {ix} on_order", minimum=0)
        crit_value = _number(raw.get("criticality_score"), f"Spare-parts row {ix} criticality_score", strictly_positive=True)
        if not crit_value.is_integer() or crit_value > 5:
            raise ValueError(f"Spare-parts row {ix} criticality_score must be a whole number from 1 to 5.")
        mean_daily = annual / days
        mean_lead_demand = mean_daily * lead
        safety = z * sigma * math.sqrt(lead)
        reorder_point = mean_lead_demand + safety
        position = stock + ordered
        reorder_qty = int(math.ceil(max(0.0, reorder_point - position)))
        output.append({
            "part_id": part, "asset_id": asset, "annual_demand": annual,
            "mean_daily_demand": mean_daily, "lead_time_days": lead,
            "mean_lead_time_demand": mean_lead_demand, "safety_stock": safety,
            "reorder_point": reorder_point, "current_stock": stock, "on_order": ordered,
            "inventory_position": position, "recommended_reorder_quantity": reorder_qty,
            "unit_cost": cost, "estimated_reorder_value": reorder_qty * cost,
            "criticality_score_1_to_5": int(crit_value),
            "criticality_weighted_shortfall_units": max(0.0, reorder_point-position) * int(crit_value),
            "stock_status": "BELOW_REORDER_POINT" if position < reorder_point else "AT_OR_ABOVE_REORDER_POINT",
        })
    result = pd.DataFrame(output).sort_values(
        ["criticality_score_1_to_5", "criticality_weighted_shortfall_units"],
        ascending=[False, False], kind="stable",
    ).reset_index(drop=True)
    return {
        "tool_id": "T045",
        "status": "CALCULATED",
        "method": "Lead-time demand reorder-point screen with normal-approximation safety stock",
        "formulas": {
            "mean lead-time demand": "annual demand / operating days per year × lead time days",
            "safety stock": "z × daily demand standard deviation × sqrt(lead time days)",
            "reorder point": "mean lead-time demand + safety stock",
            "reorder quantity": "ceil(max(0, reorder point − on-hand − on-order))",
        },
        "assumptions": [
            "Demand and lead time use the supplied daily basis; demand variability is treated as independent with a normal approximation.",
            "This method does not model intermittent spare-part demand, supplier constraints, obsolescence, MOQ, or shared-equipment failure probabilities.",
        ],
        "warnings": ["Criticality scores are user-defined ranking inputs; validate service factors and stocking rules against plant criticality policy."],
        "metrics": {
            "parts_count": int(len(result)),
            "parts_below_reorder_point": int((result["stock_status"] == "BELOW_REORDER_POINT").sum()),
            "recommended_reorder_value": float(result["estimated_reorder_value"].sum()),
            "criticality_weighted_shortfall": float(result["criticality_weighted_shortfall_units"].sum()),
            "operating_days_per_year": days, "service_factor_z": z,
        },
        "spare_parts_plan": result,
    }


def score_supplier_performance(
    rows: Any,
    *,
    weights: dict[str, float] | None = None,
    minimum_acceptable_score: float = 70.0,
) -> dict[str, Any]:
    """Compute a weighted supplier score and expose evidence coverage per supplier."""
    frame = _frame(rows, "Supplier scorecard")
    fields = ["quality_score", "delivery_score", "cost_score", "responsiveness_score"]
    required = {"supplier", "evidence_date", *fields}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Supplier scorecard is missing columns: " + ", ".join(missing) + ".")
    weight_map = weights or {
        "quality_score": 0.40, "delivery_score": 0.30,
        "cost_score": 0.20, "responsiveness_score": 0.10,
    }
    if set(weight_map) != set(fields):
        raise ValueError("Weights must specify quality_score, delivery_score, cost_score and responsiveness_score.")
    parsed_weights = {key: _number(val, f"Weight {key}", minimum=0) for key, val in weight_map.items()}
    weight_total = sum(parsed_weights.values())
    if weight_total <= 0:
        raise ValueError("At least one supplier score weight must be greater than zero.")
    threshold = _number(minimum_acceptable_score, "Minimum acceptable score", minimum=0)
    if threshold > 100:
        raise ValueError("Minimum acceptable score must not exceed 100.")

    seen, output = set(), []
    total_weight = weight_total
    for ix, raw in enumerate(frame.to_dict(orient="records"), start=1):
        name = _txt(raw.get("supplier"))
        if not name:
            raise ValueError(f"Supplier row {ix} requires a supplier name.")
        if name.casefold() in seen:
            raise ValueError(f"Duplicate supplier '{name}'.")
        seen.add(name.casefold())
        weighted, available_weight = 0.0, 0.0
        scores = {}
        for field in fields:
            value = raw.get(field)
            if value is None or (isinstance(value, float) and math.isnan(value)) or _txt(value) == "":
                scores[field] = None
                continue
            score = _number(value, f"Supplier row {ix} {field}", minimum=0)
            if score > 100:
                raise ValueError(f"Supplier row {ix} {field} must not exceed 100.")
            scores[field] = score
            weighted += score * parsed_weights[field]
            available_weight += parsed_weights[field]
        coverage = available_weight / total_weight * 100.0
        score_value = weighted / available_weight if available_weight > 0 else None
        evidence_date = _txt(raw.get("evidence_date"))
        if evidence_date:
            _day(evidence_date, f"Supplier row {ix} evidence_date")
        if score_value is None or coverage < 80:
            status = "INSUFFICIENT_EVIDENCE"
        elif score_value < threshold:
            status = "BELOW_CONFIGURED_THRESHOLD"
        else:
            status = "MEETS_CONFIGURED_THRESHOLD"
        output.append({
            "supplier": name, **scores, "evidence_date": evidence_date,
            "evidence_coverage_percent": coverage,
            "weighted_score_on_available_evidence": score_value,
            "configured_threshold": threshold, "score_status": status,
        })
    result = pd.DataFrame(output).sort_values(
        ["score_status", "weighted_score_on_available_evidence", "supplier"],
        ascending=[True, False, True], na_position="last", kind="stable",
    ).reset_index(drop=True)
    return {
        "tool_id": "T058",
        "status": "CALCULATED",
        "method": "Weighted supplier scorecard using user-defined 0–100 scores and weights",
        "formula": "Weighted score = sum(score × weight) / sum(available criterion weights)",
        "assumptions": [
            "All score weights are user-defined and are normalized only over criteria with an available score for that supplier.",
            "A score coverage below 80% is labelled INSUFFICIENT_EVIDENCE; it is not treated as a low supplier score.",
            "Scores and evidence dates are user-entered and are not independently verified.",
        ],
        "warnings": ["Weights and the 80% evidence-coverage threshold are configurable judgement rules, not an industry standard or objective supplier risk measure."],
        "metrics": {
            "supplier_count": int(len(result)),
            "insufficient_evidence_count": int((result["score_status"] == "INSUFFICIENT_EVIDENCE").sum()),
            "below_threshold_count": int((result["score_status"] == "BELOW_CONFIGURED_THRESHOLD").sum()),
            "minimum_acceptable_score": threshold,
        },
        "scorecard": result,
    }
