"""Typed operational decision helpers for Shoir-IE targets T047/T052/T063/T073/T084/T086/T094.

These bounded methods do not certify safety, optimize a complete plant schedule,
authenticate research evidence, or send alerts to external systems.
"""
from __future__ import annotations

from datetime import date
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


def _txt(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _frame(value: Any, label: str, *, maximum: int = 1000) -> pd.DataFrame:
    frame = value.copy(deep=True) if isinstance(value, pd.DataFrame) else pd.DataFrame(list(value))
    if frame.empty:
        raise ValueError(f"{label} requires at least one row.")
    if frame.columns.has_duplicates:
        raise ValueError(f"{label} must have unique column names.")
    if len(frame) > maximum:
        raise ValueError(f"{label} is limited to {maximum} rows.")
    return frame


def _num(value: Any, label: str, *, minimum: float | None = None, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    if positive and result <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return result


def _date(value: Any, label: str) -> date:
    raw = _txt(value)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{label} must use YYYY-MM-DD format.")
    return parsed


def build_hazard_register(rows: Any) -> dict[str, Any]:
    """Score initial/residual hazards on explicitly user-entered 1–5 scales."""
    frame = _frame(rows, "Hazard register")
    required = {"hazard_id", "hazard", "potential_harm", "likelihood_1_to_5", "severity_1_to_5",
                "residual_likelihood_1_to_5", "residual_severity_1_to_5", "current_controls",
                "additional_controls", "owner", "due_date", "status"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Hazard register is missing columns: " + ", ".join(missing) + ".")
    seen, output = set(), []
    for i, raw in enumerate(frame.to_dict(orient="records"), start=1):
        hazard_id, hazard, harm = _txt(raw.get("hazard_id")), _txt(raw.get("hazard")), _txt(raw.get("potential_harm"))
        if not hazard_id or not hazard or not harm:
            raise ValueError(f"Hazard row {i} requires an ID, hazard description and potential harm.")
        if hazard_id.casefold() in seen:
            raise ValueError(f"Duplicate hazard ID '{hazard_id}'.")
        seen.add(hazard_id.casefold())
        ratings = {}
        for field in ("likelihood_1_to_5", "severity_1_to_5", "residual_likelihood_1_to_5", "residual_severity_1_to_5"):
            val = _num(raw.get(field), f"Hazard row {i} {field}", minimum=1)
            if not val.is_integer() or val > 5:
                raise ValueError(f"Hazard row {i} {field} must be a whole number from 1 to 5.")
            ratings[field] = int(val)
        due = _txt(raw.get("due_date"))
        if due:
            _date(due, f"Hazard row {i} due_date")
        status = _txt(raw.get("status")) or "Open"
        if status not in {"Open", "In Progress", "Controlled", "Closed"}:
            raise ValueError(f"Hazard row {i} status must be Open, In Progress, Controlled or Closed.")
        output.append({
            "hazard_id": hazard_id, "hazard": hazard, "potential_harm": harm, **ratings,
            "initial_risk_score": ratings["likelihood_1_to_5"] * ratings["severity_1_to_5"],
            "residual_risk_score": ratings["residual_likelihood_1_to_5"] * ratings["residual_severity_1_to_5"],
            "current_controls": _txt(raw.get("current_controls")),
            "additional_controls": _txt(raw.get("additional_controls")),
            "owner": _txt(raw.get("owner")), "due_date": due, "status": status,
        })
    result = pd.DataFrame(output).sort_values(
        ["residual_risk_score", "severity_1_to_5", "hazard_id"],
        ascending=[False, False, True], kind="stable"
    ).reset_index(drop=True)
    return {
        "tool_id": "T047", "status": "CALCULATED",
        "method": "Initial and residual hazard screening using likelihood × severity",
        "formula": "Risk score = user-rated likelihood (1–5) × user-rated severity (1–5); score ≥ 15 is an illustrative screening flag only",
        "assumptions": [
            "Ratings are ordinal, user-entered screening scores; an equal product does not mean equal consequences.",
            "Initial and residual ratings must use the organization's approved scale and review process; the score ≥ 15 count is illustrative and not a universal risk band.",
        ],
        "warnings": [
            "This register is not a certified safety assessment, legal compliance check or substitute for a competent safety professional.",
            "A lower residual score is only a recorded assessment of controls; control effectiveness must be independently evaluated.",
        ],
        "metrics": {
            "hazard_count": int(len(result)),
            "high_initial_score_count": int((result["initial_risk_score"] >= 15).sum()),
            "high_residual_score_count": int((result["residual_risk_score"] >= 15).sum()),
            "open_action_count": int(result["status"].isin(["Open", "In Progress"]).sum()),
            "maximum_residual_score": int(result["residual_risk_score"].max()),
        },
        "hazard_register": result,
    }


def reconcile_sop_scenario(
    rows: Any,
    *,
    starting_inventory_units: float = 0,
    starting_backlog_units: float = 0,
) -> dict[str, Any]:
    """Perform period-sequenced demand/supply/capacity reconciliation."""
    frame = _frame(rows, "S&OP plan")
    required = {"period", "demand_units", "planned_production_units", "capacity_units"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("S&OP plan is missing columns: " + ", ".join(missing) + ".")
    start_inventory = _num(starting_inventory_units, "Starting inventory", minimum=0)
    backlog = _num(starting_backlog_units, "Starting backlog", minimum=0)
    periods = [_txt(v) for v in frame["period"]]
    if any(not p for p in periods) or len({p.casefold() for p in periods}) != len(periods):
        raise ValueError("S&OP period labels must be non-empty and unique.")
    inventory = start_inventory
    output = []
    for i, raw in enumerate(frame.to_dict(orient="records"), start=1):
        demand = _num(raw.get("demand_units"), f"S&OP row {i} demand_units", minimum=0)
        production = _num(raw.get("planned_production_units"), f"S&OP row {i} planned_production_units", minimum=0)
        capacity = _num(raw.get("capacity_units"), f"S&OP row {i} capacity_units", minimum=0)
        open_inventory, open_backlog = inventory, backlog
        available = open_inventory + production
        required_units = demand + open_backlog
        end_inventory = max(0.0, available - required_units)
        end_backlog = max(0.0, required_units - available)
        utilization = production / capacity * 100.0 if capacity > 0 else (0.0 if production == 0 else None)
        output.append({
            "period": _txt(raw.get("period")),
            "opening_inventory_units": open_inventory,
            "opening_backlog_units": open_backlog,
            "demand_units": demand,
            "planned_production_units": production,
            "capacity_units": capacity,
            "capacity_exceeded": bool(production > capacity),
            "capacity_utilization_percent": utilization,
            "available_supply_units": available,
            "ending_inventory_units": end_inventory,
            "ending_backlog_units": end_backlog,
        })
        inventory, backlog = end_inventory, end_backlog
    result = pd.DataFrame(output)
    over = int(result["capacity_exceeded"].sum())
    return {
        "tool_id": "T052", "status": "CALCULATED",
        "method": "Sequential aggregate demand/supply reconciliation (period order is input order)",
        "formulas": {
            "available supply": "opening inventory + planned production",
            "period requirement": "current demand + opening backlog",
            "ending inventory": "max(0, available supply − period requirement)",
            "ending backlog": "max(0, period requirement − available supply)",
            "capacity utilization": "planned production / capacity × 100% where capacity > 0",
        },
        "assumptions": [
            "Rows are in chronological period order; no automatic calendar sorting is applied.",
            "Production is treated as available within the same period; lead times, BOMs, workforce constraints and lot sizes are not modeled.",
        ],
        "warnings": [
            "This is aggregate reconciliation, not a finite-capacity or material-constrained schedule.",
            "Capacity overages are reported rather than hidden; investigate them before adopting the plan.",
        ],
        "metrics": {
            "period_count": int(len(result)),
            "total_demand_units": float(result["demand_units"].sum()),
            "total_planned_production_units": float(result["planned_production_units"].sum()),
            "capacity_exceeded_periods": over,
            "ending_inventory_units": float(inventory),
            "ending_backlog_units": float(backlog),
        },
        "reconciliation": result,
    }


def solve_assignment_cost_matrix(cost_table: Any) -> dict[str, Any]:
    """Solve a square one-to-one minimum-cost assignment problem."""
    frame = _frame(cost_table, "Assignment cost matrix", maximum=200)
    if "job" not in frame.columns:
        raise ValueError("Assignment cost matrix must contain a 'job' column and resource cost columns.")
    jobs = [_txt(v) for v in frame["job"]]
    resources = [str(c).strip() for c in frame.columns if c != "job"]
    if not resources or len(jobs) != len(resources):
        raise ValueError("This assignment method requires a square matrix: one unique resource for each job.")
    if any(not j for j in jobs) or len({j.casefold() for j in jobs}) != len(jobs):
        raise ValueError("Job names must be non-empty and unique.")
    if any(not r for r in resources) or len({r.casefold() for r in resources}) != len(resources):
        raise ValueError("Resource names must be non-empty and unique.")
    try:
        costs = frame[resources].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("All assignment costs must be numeric; missing costs are not silently imputed.") from exc
    if not np.isfinite(costs).all():
        raise ValueError("Assignment costs must be finite and complete.")
    if (costs < 0).any():
        raise ValueError("Assignment costs must be non-negative.")
    row_ind, col_ind = linear_sum_assignment(costs)
    assignments = pd.DataFrame({
        "job": [jobs[i] for i in row_ind],
        "assigned_resource": [resources[j] for j in col_ind],
        "cost": [float(costs[i, j]) for i, j in zip(row_ind, col_ind)],
    })
    total = float(assignments["cost"].sum())
    return {
        "tool_id": "T063", "status": "OPTIMAL_FOR_ASSIGNMENT_MODEL",
        "method": "Linear-sum assignment (Hungarian algorithm) on a square one-to-one cost matrix",
        "formula": "Minimize sum(cost[job, assigned resource]) subject to one assignment per job and resource",
        "assumptions": [
            "Every job must be assigned to exactly one resource and each resource may be used once.",
            "Only the supplied costs are optimized; skills, capacities, precedence, setup and calendar constraints are not modeled.",
        ],
        "warnings": ["Optimality applies only to this cost-matrix model, not to a wider production schedule with unmodeled constraints."],
        "metrics": {
            "job_count": int(len(jobs)),
            "resource_count": int(len(resources)),
            "total_assignment_cost": total,
            "average_assignment_cost": float(total / len(jobs)),
            "assignment_complete": bool(len(assignments) == len(jobs)),
        },
        "assignments": assignments,
    }


def compare_capacity_scenarios(
    rows: Any,
    *,
    demand_units: float,
    baseline_scenario_id: str,
) -> dict[str, Any]:
    """Compare scenario capacity under explicit available-time, cycle-time and yield assumptions."""
    frame = _frame(rows, "Capacity scenarios", maximum=200)
    required = {"scenario_id", "available_minutes_per_period", "cycle_time_minutes_per_unit", "yield_percent"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Capacity scenarios are missing columns: " + ", ".join(missing) + ".")
    demand = _num(demand_units, "Demand units", minimum=0)
    baseline_id = _txt(baseline_scenario_id)
    ids = [_txt(v) for v in frame["scenario_id"]]
    if any(not x for x in ids) or len({x.casefold() for x in ids}) != len(ids):
        raise ValueError("Scenario IDs must be non-empty and unique.")
    if baseline_id not in ids:
        raise ValueError(f"Baseline scenario '{baseline_id}' was not found.")
    output = []
    for i, raw in enumerate(frame.to_dict(orient="records"), start=1):
        minutes = _num(raw.get("available_minutes_per_period"), f"Scenario row {i} available minutes", minimum=0)
        cycle = _num(raw.get("cycle_time_minutes_per_unit"), f"Scenario row {i} cycle time", positive=True)
        yield_pct = _num(raw.get("yield_percent"), f"Scenario row {i} yield percent", positive=True)
        if yield_pct > 100:
            raise ValueError(f"Scenario row {i} yield percent must not exceed 100.")
        capacity = minutes / cycle * yield_pct / 100.0
        output.append({
            "scenario_id": _txt(raw.get("scenario_id")),
            "available_minutes_per_period": minutes,
            "cycle_time_minutes_per_unit": cycle,
            "yield_percent": yield_pct,
            "estimated_good_units_capacity": capacity,
            "demand_units": demand,
            "capacity_gap_units": capacity - demand,
        })
    result = pd.DataFrame(output)
    baseline_capacity = float(result.loc[result["scenario_id"] == baseline_id, "estimated_good_units_capacity"].iloc[0])
    result["capacity_delta_vs_baseline_units"] = result["estimated_good_units_capacity"] - baseline_capacity
    result["meets_entered_demand"] = result["estimated_good_units_capacity"] >= demand
    best = result.loc[result["estimated_good_units_capacity"].idxmax(), "scenario_id"]
    return {
        "tool_id": "T073", "status": "CALCULATED",
        "method": "Capacity what-if comparison based on available time, cycle time and yield",
        "formula": "Estimated good-unit capacity = available minutes / cycle-time minutes per unit × yield fraction",
        "assumptions": [
            "The same definition of available time, cycle time and yield is applied to every scenario.",
            "No stochastic variation, product mix, labor constraints or sequence-dependent setup is modeled.",
        ],
        "warnings": ["This is a deterministic what-if calculation, not a discrete-event simulation or evidence that a scenario will achieve the estimated output."],
        "metrics": {
            "scenario_count": int(len(result)),
            "baseline_scenario_id": baseline_id,
            "baseline_capacity_units": baseline_capacity,
            "highest_capacity_scenario_id": str(best),
            "scenarios_meeting_entered_demand": int(result["meets_entered_demand"].sum()),
        },
        "scenario_comparison": result,
    }


def score_project_portfolio(
    rows: Any,
    *,
    weights: dict[str, float] | None = None,
    currency: str = "SAR",
) -> dict[str, Any]:
    """Score project proposals on supplied 0–100 criteria with explicit weights."""
    frame = _frame(rows, "Project portfolio")
    criteria = ["impact_score", "strategic_fit_score", "feasibility_score", "confidence_score"]
    required = {"project_id", "project_name", "estimated_cost", *criteria}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Project portfolio is missing columns: " + ", ".join(missing) + ".")
    weight_map = weights or {"impact_score": 0.35, "strategic_fit_score": 0.30, "feasibility_score": 0.20, "confidence_score": 0.15}
    if set(weight_map) != set(criteria):
        raise ValueError("Weights must specify impact_score, strategic_fit_score, feasibility_score and confidence_score.")
    parsed_weights = {k: _num(v, f"Weight {k}", minimum=0) for k, v in weight_map.items()}
    weight_sum = sum(parsed_weights.values())
    if weight_sum <= 0:
        raise ValueError("At least one project-scoring weight must be greater than zero.")
    currency = _txt(currency).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("Currency must be a three-letter code.")
    output, seen = [], set()
    for i, raw in enumerate(frame.to_dict(orient="records"), start=1):
        project_id, name = _txt(raw.get("project_id")), _txt(raw.get("project_name"))
        if not project_id or not name:
            raise ValueError(f"Portfolio row {i} requires project ID and name.")
        if project_id.casefold() in seen:
            raise ValueError(f"Duplicate project ID '{project_id}'.")
        seen.add(project_id.casefold())
        scores = {}
        for criterion in criteria:
            val = _num(raw.get(criterion), f"Portfolio row {i} {criterion}", minimum=0)
            if val > 100:
                raise ValueError(f"Portfolio row {i} {criterion} must not exceed 100.")
            scores[criterion] = val
        cost = _num(raw.get("estimated_cost"), f"Portfolio row {i} estimated_cost", minimum=0)
        score = sum(scores[k] * parsed_weights[k] for k in criteria) / weight_sum
        output.append({
            "project_id": project_id, "project_name": name, "estimated_cost": cost, **scores,
            "weighted_score": score,
            "score_per_cost_unit": score / cost if cost > 0 else None,
            "cost_currency": currency,
        })
    result = pd.DataFrame(output).sort_values(["weighted_score", "project_id"], ascending=[False, True], kind="stable").reset_index(drop=True)
    result.insert(0, "rank_by_configured_score", range(1, len(result)+1))
    return {
        "tool_id": "T084", "status": "CALCULATED",
        "method": "Weighted multi-criteria portfolio score",
        "formula": "Portfolio score = sum(criterion score × criterion weight) / sum(weights), each criterion 0–100",
        "assumptions": [
            "Scores and weights are judgment-based inputs and do not represent objective probabilities.",
            "Cost is displayed for context; score-per-cost is not ROI or a budget-constrained portfolio optimum.",
        ],
        "warnings": ["Check weight and score sensitivity before ranking actual investment proposals; ties and uncertainty can change priority."],
        "metrics": {
            "project_count": int(len(result)),
            "top_ranked_project_id": str(result.iloc[0]["project_id"]),
            "top_weighted_score": float(result.iloc[0]["weighted_score"]),
            "currency": currency,
            "weight_total_before_normalization": float(weight_sum),
        },
        "portfolio": result,
    }


def build_hypothesis_evidence_register(rows: Any) -> dict[str, Any]:
    """Validate a typed hypothesis/evidence register without granting independent verification."""
    frame = _frame(rows, "Hypothesis evidence register")
    required = {"evidence_id", "claim_or_hypothesis", "source_reference", "method_or_run", "review_state", "reviewer", "review_date", "limitations"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Evidence register is missing columns: " + ", ".join(missing) + ".")
    allowed = {"UNREVIEWED", "SUPPORTS", "CONTRADICTS", "INCONCLUSIVE", "NEEDS_REVIEW"}
    seen, output = set(), []
    for i, raw in enumerate(frame.to_dict(orient="records"), start=1):
        evidence_id, claim = _txt(raw.get("evidence_id")), _txt(raw.get("claim_or_hypothesis"))
        if not evidence_id or not claim:
            raise ValueError(f"Evidence row {i} requires evidence ID and claim/hypothesis.")
        if evidence_id.casefold() in seen:
            raise ValueError(f"Duplicate evidence ID '{evidence_id}'.")
        seen.add(evidence_id.casefold())
        state = _txt(raw.get("review_state")) or "UNREVIEWED"
        if state not in allowed:
            raise ValueError(f"Evidence row {i} review_state must be one of: {', '.join(sorted(allowed))}.")
        reviewer, review_date = _txt(raw.get("reviewer")), _txt(raw.get("review_date"))
        if state != "UNREVIEWED" and (not reviewer or not review_date):
            raise ValueError(f"Evidence row {i} requires reviewer and review_date for state '{state}'.")
        if review_date:
            _date(review_date, f"Evidence row {i} review_date")
        source = _txt(raw.get("source_reference"))
        output.append({
            "evidence_id": evidence_id, "claim_or_hypothesis": claim,
            "source_reference": source, "source_gap": "MISSING_SOURCE_REFERENCE" if not source else "SOURCE_REFERENCE_ENTERED_NOT_VERIFIED",
            "method_or_run": _txt(raw.get("method_or_run")), "review_state": state,
            "reviewer": reviewer, "review_date": review_date, "limitations": _txt(raw.get("limitations")),
            "independently_verified": False,
        })
    result = pd.DataFrame(output)
    return {
        "tool_id": "T086", "status": "CALCULATED",
        "method": "Typed hypothesis/evidence register validation",
        "assumptions": [
            "The register records user-provided source references and review metadata; it does not fetch or independently authenticate cited sources.",
            "Review state is a recorded user entry, not proof of scientific validity or independent verification.",
        ],
        "warnings": ["Do not treat a SOURCE_REFERENCE_ENTERED_NOT_VERIFIED label as proof that a source supports the claim."],
        "metrics": {
            "evidence_record_count": int(len(result)),
            "missing_source_reference_count": int((result["source_gap"] == "MISSING_SOURCE_REFERENCE").sum()),
            "unreviewed_count": int((result["review_state"] == "UNREVIEWED").sum()),
            "contradictory_count": int((result["review_state"] == "CONTRADICTS").sum()),
            "independently_verified_count": 0,
        },
        "evidence_register": result,
    }


def evaluate_kpi_thresholds(
    rows: Any,
    *,
    as_of_date: str,
    stale_after_days: int = 7,
) -> dict[str, Any]:
    """Evaluate user-configured above/below thresholds and data freshness; no notifications are sent."""
    frame = _frame(rows, "KPI threshold table")
    required = {"metric_name", "observed_value", "threshold", "direction", "unit", "last_updated_date", "owner"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("KPI table is missing columns: " + ", ".join(missing) + ".")
    as_of = _date(as_of_date, "As-of date")
    stale_limit = _num(stale_after_days, "Stale threshold days", minimum=0)
    if not stale_limit.is_integer():
        raise ValueError("Stale threshold days must be a whole number.")
    names, output = set(), []
    for i, raw in enumerate(frame.to_dict(orient="records"), start=1):
        name = _txt(raw.get("metric_name"))
        if not name:
            raise ValueError(f"KPI row {i} requires a metric name.")
        if name.casefold() in names:
            raise ValueError(f"Duplicate KPI metric '{name}'.")
        names.add(name.casefold())
        observed = _num(raw.get("observed_value"), f"KPI row {i} observed_value")
        threshold = _num(raw.get("threshold"), f"KPI row {i} threshold")
        direction = _txt(raw.get("direction")).upper()
        if direction not in {"ABOVE", "BELOW"}:
            raise ValueError(f"KPI row {i} direction must be ABOVE or BELOW.")
        updated = _date(raw.get("last_updated_date"), f"KPI row {i} last_updated_date")
        if updated > as_of:
            raise ValueError(f"KPI row {i} last_updated_date cannot be after the as-of date.")
        age = (as_of - updated).days
        crossed = observed > threshold if direction == "ABOVE" else observed < threshold
        stale = age > int(stale_limit)
        state = "ALERT_STALE" if crossed and stale else ("ALERT" if crossed else ("STALE" if stale else "OK"))
        output.append({
            "metric_name": name, "observed_value": observed, "threshold": threshold,
            "direction": direction, "unit": _txt(raw.get("unit")),
            "last_updated_date": updated.isoformat(), "data_age_days": age,
            "stale_after_days": int(stale_limit), "owner": _txt(raw.get("owner")),
            "threshold_crossed": bool(crossed), "is_stale": bool(stale), "status": state,
        })
    result = pd.DataFrame(output)
    return {
        "tool_id": "T094", "status": "CALCULATED",
        "method": "User-configured KPI threshold and freshness evaluation",
        "assumptions": [
            "Thresholds and direction are defined by the workspace owner; they are not inferred from statistical control limits.",
            "Freshness is measured in calendar days from the supplied as-of date.",
        ],
        "warnings": ["This produces an alert snapshot only. It does not send notifications, de-duplicate across runs, or establish a live data feed."],
        "metrics": {
            "kpi_count": int(len(result)),
            "alert_count": int(result["threshold_crossed"].sum()),
            "stale_metric_count": int(result["is_stale"].sum()),
            "alert_and_stale_count": int((result["status"] == "ALERT_STALE").sum()),
            "as_of_date": as_of.isoformat(),
        },
        "kpi_status": result,
    }
