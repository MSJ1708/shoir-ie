"""Finite-capacity maintenance backlog selection under slot skill/window constraints (T049)."""
from __future__ import annotations

from datetime import date
import math
from typing import Any

import pandas as pd
import pulp


def _required_frame(value: Any, label: str, required: set[str], *, maximum: int = 2000) -> pd.DataFrame:
    frame = value.copy(deep=True) if isinstance(value, pd.DataFrame) else pd.DataFrame(list(value))
    if frame.columns.has_duplicates:
        raise ValueError(f"{label} must have unique column names.")
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: " + ", ".join(missing))
    if len(frame) > maximum:
        raise ValueError(f"{label} is limited to {maximum} rows.")
    return frame


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _date(value: Any, label: str, *, optional: bool = False) -> date | None:
    raw = _text(value)
    if not raw and optional:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{label} must use YYYY-MM-DD format.")
    return parsed


def optimize_maintenance_backlog(
    work_orders: Any,
    slots: Any,
    *,
    as_of_date: str,
) -> dict[str, Any]:
    """Select work orders that fit available skill/window slots using a binary MILP."""
    jobs = _required_frame(
        work_orders, "Maintenance work orders",
        {"work_order_id", "asset_id", "description", "estimated_hours", "criticality_1_to_5",
         "required_skill", "required_window", "due_date"},
    )
    resources = _required_frame(
        slots, "Maintenance capacity slots",
        {"slot_id", "skill", "downtime_window", "available_hours"},
    )
    if jobs.empty:
        raise ValueError("At least one maintenance work order is required.")
    if resources.empty:
        raise ValueError("At least one maintenance capacity slot is required.")
    as_of = _date(as_of_date, "As-of date")
    job_ids = [_text(v) for v in jobs["work_order_id"]]
    slot_ids = [_text(v) for v in resources["slot_id"]]
    if any(not x for x in job_ids) or len({x.casefold() for x in job_ids}) != len(job_ids):
        raise ValueError("Work-order IDs must be non-empty and unique.")
    if any(not x for x in slot_ids) or len({x.casefold() for x in slot_ids}) != len(slot_ids):
        raise ValueError("Capacity slot IDs must be non-empty and unique.")

    normalized_jobs = []
    for i, raw in enumerate(jobs.to_dict(orient="records"), start=1):
        order_id = _text(raw.get("work_order_id"))
        asset = _text(raw.get("asset_id"))
        description = _text(raw.get("description"))
        if not order_id or not asset or not description:
            raise ValueError(f"Work order row {i} requires work_order_id, asset_id and description.")
        try:
            duration = float(raw.get("estimated_hours"))
            criticality_float = float(raw.get("criticality_1_to_5"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Work order row {i} duration and criticality must be numeric.") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"Work order row {i} estimated_hours must be finite and positive.")
        if not math.isfinite(criticality_float) or not criticality_float.is_integer() or not 1 <= criticality_float <= 5:
            raise ValueError(f"Work order row {i} criticality_1_to_5 must be a whole number from 1 to 5.")
        required_skill = _text(raw.get("required_skill")) or "Any"
        required_window = _text(raw.get("required_window")) or "Any"
        due = _date(raw.get("due_date"), f"Work order row {i} due_date", optional=True)
        days_to_due = None if due is None else (due - as_of).days
        urgency = 0 if days_to_due is None else min(999, max(0, 30 - days_to_due))
        # Every priority component is explicit. The objective maximizes the total
        # priority score of scheduled work, rather than guaranteeing strict order.
        score = int(criticality_float) * 1000 + int(urgency)
        normalized_jobs.append({
            "work_order_id": order_id, "asset_id": asset, "description": description,
            "estimated_hours": duration, "criticality_1_to_5": int(criticality_float),
            "required_skill": required_skill, "required_window": required_window,
            "due_date": "" if due is None else due.isoformat(), "days_to_due": days_to_due,
            "priority_score": score,
        })

    normalized_slots = []
    for i, raw in enumerate(resources.to_dict(orient="records"), start=1):
        slot_id = _text(raw.get("slot_id"))
        skill = _text(raw.get("skill")) or "Any"
        window = _text(raw.get("downtime_window")) or "Any"
        try:
            hours = float(raw.get("available_hours"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Capacity slot row {i} available_hours must be numeric.") from exc
        if not math.isfinite(hours) or hours < 0:
            raise ValueError(f"Capacity slot row {i} available_hours must be finite and non-negative.")
        normalized_slots.append({"slot_id": slot_id, "skill": skill, "downtime_window": window, "available_hours": hours})

    def matches(required: str, offered: str) -> bool:
        return required.casefold() == "any" or offered.casefold() == "any" or required.casefold() == offered.casefold()

    eligible = {}
    for ji, job in enumerate(normalized_jobs):
        for si, slot in enumerate(normalized_slots):
            if matches(job["required_skill"], slot["skill"]) and matches(job["required_window"], slot["downtime_window"]):
                eligible[(ji, si)] = pulp.LpVariable(f"assign_job_{ji}_slot_{si}", cat=pulp.LpBinary)

    model = pulp.LpProblem("ShoirIE_Maintenance_Backlog", pulp.LpMaximize)
    model += pulp.lpSum(normalized_jobs[ji]["priority_score"] * var for (ji, _), var in eligible.items())
    for ji in range(len(normalized_jobs)):
        vars_for_job = [var for (j, _), var in eligible.items() if j == ji]
        if vars_for_job:
            model += pulp.lpSum(vars_for_job) <= 1, f"one_slot_per_job_{ji}"
    for si, slot in enumerate(normalized_slots):
        vars_for_slot = [
            normalized_jobs[ji]["estimated_hours"] * var
            for (ji, s), var in eligible.items() if s == si
        ]
        if vars_for_slot:
            model += pulp.lpSum(vars_for_slot) <= slot["available_hours"], f"slot_capacity_{si}"

    solver = pulp.PULP_CBC_CMD(msg=False)
    if not solver.available():
        raise RuntimeError("The CBC MILP solver is not available in this environment; no heuristic fallback was substituted.")
    model.solve(solver)
    solver_status = pulp.LpStatus.get(model.status, f"UNKNOWN_{model.status}")
    if solver_status != "Optimal":
        return {
            "tool_id": "T049",
            "status": "SOLVER_ERROR" if solver_status not in {"Infeasible", "Unbounded"} else solver_status.upper(),
            "method": "Binary MILP selection of maintenance work orders under slot-hour, skill and window constraints",
            "solver_status": solver_status,
            "warnings": ["The optimization did not return an optimal allocation. No heuristic substitute or successful schedule is presented."],
            "metrics": {"work_order_count": len(normalized_jobs), "slot_count": len(normalized_slots), "optimal": False},
            "work_plan": pd.DataFrame(),
        }

    assignments = {}
    for (ji, si), var in eligible.items():
        value = pulp.value(var)
        if value is not None and value > 0.5:
            assignments[ji] = si
    planned = []
    for ji, job in enumerate(normalized_jobs):
        si = assignments.get(ji)
        if si is not None:
            slot = normalized_slots[si]
            state = "SCHEDULED"
            slot_id = slot["slot_id"]
        else:
            eligible_slots = [
                slot for slot in normalized_slots
                if matches(job["required_skill"], slot["skill"]) and matches(job["required_window"], slot["downtime_window"])
            ]
            state = "NOT_SCHEDULED_CAPACITY_TRADEOFF" if eligible_slots else "NOT_SCHEDULED_NO_ELIGIBLE_SKILL_WINDOW"
            slot_id = ""
        planned.append({**job, "assigned_slot_id": slot_id, "schedule_status": state})
    work_plan = pd.DataFrame(planned).sort_values(
        ["schedule_status", "priority_score", "due_date", "work_order_id"],
        ascending=[True, False, True, True], kind="stable", na_position="last",
    ).reset_index(drop=True)
    slot_rows = []
    for si, slot in enumerate(normalized_slots):
        chosen = [
            normalized_jobs[ji] for ji, assigned_slot in assignments.items() if assigned_slot == si
        ]
        used = float(sum(job["estimated_hours"] for job in chosen))
        slot_rows.append({
            **slot, "scheduled_work_orders": len(chosen), "scheduled_hours": used,
            "remaining_hours": float(slot["available_hours"] - used),
            "utilization_percent": used / slot["available_hours"] * 100 if slot["available_hours"] > 0 else None,
        })
    scheduled = [normalized_jobs[ji] for ji in assignments]
    return {
        "tool_id": "T049",
        "status": "OPTIMAL",
        "method": "Binary MILP selection under skill, downtime-window, one-slot-per-order and slot-hour constraints",
        "formula": "Maximize Σ(priority_scoreᵢ × assignmentᵢⱼ); each work order is assigned to at most one eligible slot and each slot's scheduled hours cannot exceed capacity.",
        "solver_status": solver_status,
        "assumptions": [
            "Work orders are indivisible; they are either assigned wholly to one slot or left unscheduled.",
            "Skills and downtime windows match exact labels, with Any acting as a wildcard.",
            "Priority score = criticality × 1000 + min(999, max(0, 30 − days_to_due)); this is a transparent prioritization rule, not an industry standard.",
            "Slots are independent capacities; shared technicians, dependencies, setup sequences and actual calendar conflicts are not modeled.",
        ],
        "warnings": [
            "An optimal result is optimal only for this supplied slot/score model, not a certified maintenance schedule.",
            "Review critical work orders left unscheduled and validate the skill/window labels and available hours before issuing work.",
        ],
        "metrics": {
            "work_order_count": int(len(normalized_jobs)),
            "slot_count": int(len(normalized_slots)),
            "scheduled_count": int(len(scheduled)),
            "unscheduled_count": int(len(normalized_jobs) - len(scheduled)),
            "scheduled_hours": float(sum(j["estimated_hours"] for j in scheduled)),
            "scheduled_priority_score": int(sum(j["priority_score"] for j in scheduled)),
            "optimal": True,
        },
        "work_plan": work_plan,
        "slot_utilization": pd.DataFrame(slot_rows),
    }
