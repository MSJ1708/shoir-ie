"""Validated first-pass deterministic engines for focused Shoir-IE target tools.

Scope:
* T016 converts supported dimensional units and currencies only with a dated user-supplied rate.
* T031 builds an Individuals/Moving-Range chart and reports points outside 3-sigma limits only.
* T040 reconciles a scoped scrap/rework/inspection quality-cost estimate.
* T042 calculates MTBF/MTTR from complete recorded failure/repair events.
* T056 classifies inventory by explicit ABC cumulative-value and XYZ demand-CV thresholds.
* T021 calculates observed, normal and allowance-adjusted standard time.
* T022 estimates work-sampling proportions with individual Wilson confidence intervals.
* T023 calculates takt time, implied capacity and capacity gap using one declared time basis.
* T026 calculates availability, performance, quality and OEE with reconciled loss-time outputs.
* T028 builds a count-based Pareto summary and optional 5-Why/action record.
* T029 scores an editable 5S checklist with transparent owner/due-date follow-up flags.
* T030 validates A3 baseline/target/outcome records and calculates signed target progress.
* T032 calculates Cp/Cpk from pooled within-subgroup sigma and Pp/Ppk from overall sample sigma.
* T055 calculates classical EOQ, safety stock and reorder point under explicit assumptions.
* T066 is a one-dimensional cutting/bin-packing MILP with a per-piece kerf allowance.
* T075 is a threshold-based forecast error monitor, not an automatic retraining service.
* T078 multiplies activity data by a dated, user-supplied emissions factor; it is not an audit.
* T081 computes end-of-period NPV, simple payback and constrained conventional-cash-flow IRR.
* T085 is a balanced independent two-sample t-test planner using the noncentral t distribution.

These methods are first-pass deterministic engines. Catalog and unit tests do not replace authenticated
browser, persistence, export, or live-data acceptance checks.
"""
from __future__ import annotations

import math
from datetime import date as _date
from collections.abc import Mapping, Sequence
from itertools import product
from typing import Any

import numpy as np
import pandas as pd
import pulp
from scipy.stats import f, nct, norm, t


def _finite_number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number.")
    return result


def solve_cutting_stock(
    stock_length: float,
    parts: Sequence[Mapping[str, Any]],
    kerf: float = 0.0,
    *,
    max_items: int = 120,
    time_limit_seconds: int = 15,
) -> dict[str, Any]:
    """Minimize stock pieces for a 1-D cutting/bin-packing MILP.

    Kerf is an explicit per-produced-piece allowance, used as
    part length + kerf in feasibility. This conservative convention is exposed
    in the result rather than silently assuming a saw-cut convention.
    The method is bounded to protect interactive use and requires CBC via PuLP.
    """
    stock = _finite_number(stock_length, "Stock length")
    kerf_value = _finite_number(kerf, "Kerf")
    if stock <= 0:
        raise ValueError("Stock length must be greater than zero.")
    if kerf_value < 0:
        raise ValueError("Kerf cannot be negative.")
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1:
        raise ValueError("max_items must be a positive integer.")
    if isinstance(time_limit_seconds, bool) or not isinstance(time_limit_seconds, int) or time_limit_seconds < 1:
        raise ValueError("time_limit_seconds must be a positive integer.")
    if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes)) or not parts:
        raise ValueError("Provide at least one part definition.")

    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for idx, raw in enumerate(parts, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Part row {idx} must be an object with name, length and quantity.")
        name = str(raw.get("name", "")).strip()
        if not name:
            raise ValueError(f"Part row {idx} needs a non-empty name.")
        if name in seen_names:
            raise ValueError(f"Part names must be unique. Duplicate: {name}.")
        seen_names.add(name)
        length = _finite_number(raw.get("length"), f"Length for {name}")
        qty_value = _finite_number(raw.get("quantity"), f"Quantity for {name}")
        if length <= 0:
            raise ValueError(f"Length for {name} must be greater than zero.")
        if qty_value <= 0 or not qty_value.is_integer():
            raise ValueError(f"Quantity for {name} must be a positive whole number.")
        quantity = int(qty_value)
        normalized.append({
            "name": name,
            "length": length,
            "quantity": quantity,
            "effective_length": length + kerf_value,
        })

    total_items = sum(item["quantity"] for item in normalized)
    if total_items > max_items:
        raise ValueError(
            f"This interactive solver supports at most {max_items} individual pieces per run; "
            f"the request contains {total_items}. Reduce the problem size or use a dedicated solver."
        )
    oversized = [
        {"part": item["name"], "effective_length": item["effective_length"]}
        for item in normalized if item["effective_length"] > stock + 1e-9
    ]
    physical_total = sum(item["length"] * item["quantity"] for item in normalized)
    kerf_total = kerf_value * total_items
    if oversized:
        return {
            "status": "INFEASIBLE",
            "method": "1-D integer bin-packing MILP; kerf is charged per produced piece",
            "stock_length": stock,
            "kerf_per_piece": kerf_value,
            "total_items": total_items,
            "stock_count": None,
            "physical_length_total": physical_total,
            "kerf_allowance_total": kerf_total,
            "total_stock_length": None,
            "physical_utilization_pct": None,
            "waste_length": None,
            "issues": oversized,
            "cut_plan": pd.DataFrame(),
            "message": "At least one part plus its kerf allowance exceeds the available stock length.",
        }

    model = pulp.LpProblem("shoir_1d_cutting_stock", pulp.LpMinimize)
    bins = range(total_items)
    choices = range(len(normalized))
    used = {
        b: pulp.LpVariable(f"stock_used_{b}", lowBound=0, upBound=1, cat=pulp.LpBinary)
        for b in bins
    }
    allocation = {
        (i, b): pulp.LpVariable(
            f"part_{i}_in_stock_{b}",
            lowBound=0,
            upBound=normalized[i]["quantity"],
            cat=pulp.LpInteger,
        )
        for i in choices for b in bins
    }
    model += pulp.lpSum(used[b] for b in bins), "minimize_stock_count"
    for i in choices:
        model += (
            pulp.lpSum(allocation[(i, b)] for b in bins) == normalized[i]["quantity"],
            f"demand_{i}",
        )
    for b in bins:
        model += (
            pulp.lpSum(normalized[i]["effective_length"] * allocation[(i, b)] for i in choices)
            <= stock * used[b],
            f"stock_capacity_{b}",
        )
        if b < total_items - 1:
            model += used[b] >= used[b + 1], f"symmetry_{b}"

    try:
        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_seconds)
        if not solver.available():
            raise RuntimeError("PuLP's CBC solver is not available in this runtime.")
        model.solve(solver)
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Cutting-stock solver failed to execute: {type(exc).__name__}.") from exc

    solver_status = str(pulp.LpStatus.get(model.status, "Undefined")).upper().replace(" ", "_")
    if solver_status != "OPTIMAL":
        return {
            "status": solver_status,
            "method": "1-D integer bin-packing MILP; kerf is charged per produced piece",
            "stock_length": stock,
            "kerf_per_piece": kerf_value,
            "total_items": total_items,
            "stock_count": None,
            "physical_length_total": physical_total,
            "kerf_allowance_total": kerf_total,
            "total_stock_length": None,
            "physical_utilization_pct": None,
            "waste_length": None,
            "issues": [],
            "cut_plan": pd.DataFrame(),
            "message": "No proven optimal cutting plan was returned; inspect solver status before acting.",
        }

    patterns: dict[tuple[int, ...], int] = {}
    for b in bins:
        if (pulp.value(used[b]) or 0) < 0.5:
            continue
        pattern = tuple(
            int(round(pulp.value(allocation[(i, b)]) or 0))
            for i in choices
        )
        if sum(pattern) > 0:
            patterns[pattern] = patterns.get(pattern, 0) + 1

    stock_count = sum(patterns.values())
    total_stock_length = stock_count * stock
    waste = total_stock_length - physical_total - kerf_total
    plan_rows = []
    for pattern, count in sorted(patterns.items(), key=lambda item: item[0], reverse=True):
        counts_text = ", ".join(
            f"{normalized[i]['name']} x {qty}"
            for i, qty in enumerate(pattern) if qty
        )
        physical_per_stock = sum(normalized[i]["length"] * qty for i, qty in enumerate(pattern))
        piece_count = sum(pattern)
        kerf_per_stock = kerf_value * piece_count
        effective_per_stock = physical_per_stock + kerf_per_stock
        plan_rows.append({
            "Pattern": len(plan_rows) + 1,
            "Stocks": count,
            "Part mix": counts_text,
            "Pieces per stock": piece_count,
            "Physical length per stock": physical_per_stock,
            "Kerf allowance per stock": kerf_per_stock,
            "Used length incl. allowance": effective_per_stock,
            "Waste per stock": stock - effective_per_stock,
        })

    return {
        "status": "OPTIMAL",
        "method": "1-D integer bin-packing MILP; kerf is charged per produced piece",
        "stock_length": stock,
        "kerf_per_piece": kerf_value,
        "total_items": total_items,
        "stock_count": int(stock_count),
        "physical_length_total": physical_total,
        "kerf_allowance_total": kerf_total,
        "total_stock_length": total_stock_length,
        "physical_utilization_pct": (physical_total / total_stock_length * 100) if total_stock_length else 0.0,
        "waste_length": max(0.0, waste),
        "issues": [],
        "cut_plan": pd.DataFrame(plan_rows),
        "message": "Optimality was reported by the configured CBC solver; validate material and saw conventions before production use.",
    }


def monitor_forecast_drift(
    predictions: Sequence[float],
    actuals: Sequence[float],
    max_mae: float,
    *,
    window: int | None = None,
) -> dict[str, Any]:
    """Monitor forecast fit against later actuals using an absolute MAE threshold.

    This is a threshold check, not a self-training detector, causal explanation,
    or automatic retraining service. Actual zero values are excluded from MAPE
    and counted in the returned metadata.
    """
    if isinstance(predictions, (str, bytes)) or isinstance(actuals, (str, bytes)):
        raise ValueError("Predictions and actuals must be numeric sequences.")
    try:
        pred = [_finite_number(x, "Prediction") for x in predictions]
        obs = [_finite_number(x, "Actual") for x in actuals]
    except TypeError as exc:
        raise ValueError("Predictions and actuals must be numeric sequences.") from exc
    if len(pred) != len(obs):
        raise ValueError("Predictions and actuals must contain the same number of observations.")
    if len(pred) < 2:
        raise ValueError("At least two aligned prediction/actual pairs are required.")
    limit = _finite_number(max_mae, "Maximum MAE")
    if limit < 0:
        raise ValueError("Maximum MAE cannot be negative.")
    if window is not None:
        if isinstance(window, bool) or not isinstance(window, int) or window < 2:
            raise ValueError("Window must be an integer of at least 2.")
        if window > len(pred):
            raise ValueError("Window cannot exceed the number of aligned observations.")
        pred, obs = pred[-window:], obs[-window:]
    residuals = [a - p for p, a in zip(pred, obs)]
    absolute_errors = [abs(x) for x in residuals]
    mae = sum(absolute_errors) / len(residuals)
    rmse = math.sqrt(sum(x * x for x in residuals) / len(residuals))
    bias = sum(residuals) / len(residuals)
    nonzero = [(p, a) for p, a in zip(pred, obs) if a != 0]
    mape = (
        sum(abs(a - p) / abs(a) for p, a in nonzero) / len(nonzero) * 100
        if nonzero else None
    )
    frame = pd.DataFrame({
        "Observation": range(1, len(pred) + 1),
        "Prediction": pred,
        "Actual": obs,
        "Error (actual - prediction)": residuals,
        "Absolute error": absolute_errors,
    })
    return {
        "status": "DRIFT_ALERT" if mae > limit else "WITHIN_THRESHOLD",
        "method": "Absolute MAE threshold monitor",
        "observations": len(pred),
        "mae": mae,
        "rmse": rmse,
        "bias_actual_minus_prediction": bias,
        "mape_pct_excluding_zero_actuals": mape,
        "zero_actuals_excluded_from_mape": len(obs) - len(nonzero),
        "max_mae_threshold": limit,
        "window": len(pred),
        "warning": "Threshold alarms indicate degraded forecast fit; they do not identify cause or retrain a model.",
        "series": frame,
    }


def analyze_work_sampling(
    activity_counts: Mapping[str, int],
    confidence_level: float = 0.95,
    target_margin_pct: float = 5.0,
) -> dict[str, Any]:
    """Estimate activity proportions with individual Wilson score intervals.

    Counts must be mutually exclusive, exhaustive observations from a stated
    random/representative sampling plan. The Wilson intervals are per activity,
    not simultaneous multinomial intervals. The planning count uses the
    conservative p=0.5 binomial approximation for the stated margin.
    """
    if not isinstance(activity_counts, Mapping) or len(activity_counts) < 2:
        raise ValueError("Provide at least two activity categories with observation counts.")

    normalized: list[tuple[str, int]] = []
    seen: set[str] = set()
    for raw_name, raw_count in activity_counts.items():
        name = str(raw_name or "").strip()
        if not name:
            raise ValueError("Every activity category needs a non-empty name.")
        key = name.casefold()
        if key in seen:
            raise ValueError(f"Activity category names must be unique after trimming/case normalization (normalized names must be unique): {name}.")
        seen.add(key)
        if isinstance(raw_count, bool):
            raise ValueError(f"Observation count for {name} must be a whole number.")
        count_value = _finite_number(raw_count, f"Observation count for {name}")
        if count_value < 0 or not count_value.is_integer():
            raise ValueError(f"Observation count for {name} must be a non-negative whole number.")
        normalized.append((name, int(count_value)))

    total = sum(count for _, count in normalized)
    if total <= 0:
        raise ValueError("Total observations must be greater than zero.")

    confidence = _finite_number(confidence_level, "Confidence level")
    if not 0 < confidence < 1:
        raise ValueError("Confidence level must be greater than 0 and less than 1.")
    margin_pct = _finite_number(target_margin_pct, "Target margin of error")
    if not 0 < margin_pct < 50:
        raise ValueError("Target margin of error must be greater than 0 and less than 50 percent.")

    z_value = float(norm.ppf(0.5 + confidence / 2.0))
    z_squared = z_value * z_value
    rows: list[dict[str, Any]] = []
    for name, count in normalized:
        p_hat = count / total
        denominator = 1.0 + z_squared / total
        center = (p_hat + z_squared / (2.0 * total)) / denominator
        half_width = (
            z_value
            * math.sqrt(p_hat * (1.0 - p_hat) / total + z_squared / (4.0 * total * total))
            / denominator
        )
        lower = max(0.0, center - half_width)
        upper = min(1.0, center + half_width)
        rows.append({
            "Activity": name,
            "Observations": count,
            "Observed proportion (%)": 100.0 * p_hat,
            f"{confidence:.1%} Wilson lower (%)": 100.0 * lower,
            f"{confidence:.1%} Wilson upper (%)": 100.0 * upper,
            "Interval width (percentage points)": 100.0 * (upper - lower),
        })

    # Keep the sample-size rule reproducible and conservative for any unknown p.
    required_n = math.ceil(z_squared * 0.25 / ((margin_pct / 100.0) ** 2))
    adequate = total >= required_n
    frame = pd.DataFrame(rows).sort_values(
        ["Observed proportion (%)", "Activity"], ascending=[False, True]
    ).reset_index(drop=True)
    return {
        "status": "SAMPLE_TARGET_MET" if adequate else "MORE_OBSERVATIONS_RECOMMENDED",
        "method": "Work sampling proportions with individual Wilson score confidence intervals",
        "total_observations": total,
        "activity_count": len(normalized),
        "confidence_level": confidence,
        "target_margin_of_error_pct": margin_pct,
        "minimum_observations_for_target_margin": required_n,
        "target_sample_size_met": adequate,
        "activity_summary": frame,
        "formula": (
            "Proportion = category count / total observations. Wilson score intervals are used for each "
            "binomial category proportion. Planning n = ceil(z^2 × 0.25 / margin^2), using the conservative p=0.5."
        ),
        "assumptions": (
            "Observations are representative and approximately independent; every observation belongs to exactly "
            "one listed category; the Wilson intervals are per-category, not simultaneous intervals; the target "
            "margin uses a conservative normal-approximation planning rule."
        ),
        "warning": (
            f"{total} observations are below the conservative planning target of {required_n} for a "
            f"±{margin_pct:g} percentage-point margin at {confidence:.1%} confidence."
            if not adequate else
            "The conservative planning target is met; review sampling-frame representativeness and timing before generalizing."
        ),
    }


def analyze_pareto_root_cause(
    category_counts: Mapping[str, int],
    *,
    problem_statement: str = "",
    why_chain: Sequence[str] = (),
    countermeasure: str = "",
    owner: str = "",
    due_date: str = "",
) -> dict[str, Any]:
    """Build a reproducible Pareto table and optionally record a complete 5-Why chain.

    Pareto concentration describes the observed counts and does not establish
    causation. A 5-Why record is a hypothesis/evidence structure requiring
    human verification, not proof of a physical root cause.
    """
    if not isinstance(category_counts, Mapping) or not category_counts:
        raise ValueError("Provide a non-empty category-to-count mapping.")
    normalized: list[tuple[str, int]] = []
    seen: set[str] = set()
    for raw_name, raw_count in category_counts.items():
        name = str(raw_name or "").strip()
        if not name:
            raise ValueError("Every Pareto category needs a non-empty name.")
        key = name.casefold()
        if key in seen:
            raise ValueError(f"Pareto category names must be unique after trimming/case normalization (normalized names must be unique): {name}.")
        seen.add(key)
        if isinstance(raw_count, bool):
            raise ValueError(f"Count for {name} must be a non-negative whole number.")
        count_value = _finite_number(raw_count, f"Count for {name}")
        if count_value < 0 or not count_value.is_integer():
            raise ValueError(f"Count for {name} must be a non-negative whole number.")
        normalized.append((name, int(count_value)))
    total = sum(count for _, count in normalized)
    if total <= 0:
        raise ValueError("Total Pareto count must be greater than zero.")

    normalized.sort(key=lambda item: (-item[1], item[0].casefold()))
    cumulative = 0
    rows: list[dict[str, Any]] = []
    for name, count in normalized:
        cumulative += count
        rows.append({
            "Category": name,
            "Count": count,
            "Share (%)": count / total * 100.0,
            "Cumulative count": cumulative,
            "Cumulative (%)": cumulative / total * 100.0,
        })
    frame = pd.DataFrame(rows)
    top_count = 0
    for row in rows:
        top_count += 1
        if row["Cumulative (%)"] >= 80.0:
            break

    raw_whys = list(why_chain) if not isinstance(why_chain, (str, bytes)) else [why_chain]
    whys = [str(item or "").strip() for item in raw_whys if str(item or "").strip()]
    if len(whys) not in (0, 5):
        raise ValueError("Provide either no 5-Why chain or exactly five non-empty why statements.")
    problem = str(problem_statement or "").strip()
    action = str(countermeasure or "").strip()
    action_owner = str(owner or "").strip()
    date_value = str(due_date or "").strip()
    if date_value:
        try:
            _date.fromisoformat(date_value)
        except ValueError as exc:
            raise ValueError("Action due date must use ISO YYYY-MM-DD format.") from exc
    if whys and not problem:
        raise ValueError("A problem statement is required when recording a 5-Why chain.")

    follow_up_complete = bool(whys and action and action_owner and date_value)
    if whys:
        status = "ROOT_CAUSE_REVIEW_RECORDED" if follow_up_complete else "FOLLOW_UP_INCOMPLETE"
    else:
        status = "PARETO_ONLY"
    return {
        "status": status,
        "method": "Descending Pareto analysis plus optional structured 5-Why/action record",
        "total_count": total,
        "category_count": len(normalized),
        "categories_to_reach_80_percent": top_count,
        "pareto_summary": frame,
        "problem_statement": problem,
        "why_chain": [{"why": i + 1, "statement": statement} for i, statement in enumerate(whys)],
        "countermeasure": action,
        "owner": action_owner,
        "due_date": date_value,
        "follow_up_complete": follow_up_complete,
        "formula": "Share = category count / total count; cumulative share = cumulative count / total count.",
        "warning": (
            "Pareto concentration and 5-Why statements do not prove causation. Validate proposed causes with process evidence."
            if follow_up_complete else
            "Pareto analysis only or an incomplete 5-Why follow-up record; assign and verify countermeasures before claiming corrective action."
        ),
    }


def assess_5s_audit(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Score an editable 5S checklist on a transparent 0–4 rubric.

    Each of the five pillars must be represented. Scores and notes are
    self-assessments, not a safety or quality certification. Items scoring 0–2
    should have an accountable owner and ISO due date.
    """
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or not items:
        raise ValueError("Provide a non-empty 5S checklist as a list of item objects.")

    canonical_categories = {
        "sort": "Sort",
        "set in order": "Set in Order",
        "shine": "Shine",
        "standardize": "Standardize",
        "sustain": "Sustain",
    }
    normalized: list[dict[str, Any]] = []
    seen_criteria: set[str] = set()
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Checklist row {index} must be an object.")
        raw_category = " ".join(str(raw.get("category", "") or "").strip().replace("_", " ").split())
        category = canonical_categories.get(raw_category.casefold())
        if category is None:
            raise ValueError(
                f"Checklist row {index} category must be one of Sort, Set in Order, Shine, Standardize or Sustain."
            )
        criterion = str(raw.get("criterion", "") or "").strip()
        if not criterion:
            raise ValueError(f"Checklist row {index} needs a criterion.")
        criterion_key = criterion.casefold()
        if criterion_key in seen_criteria:
            raise ValueError(f"Checklist criteria must be unique; duplicate: {criterion}.")
        seen_criteria.add(criterion_key)
        raw_score = raw.get("score")
        if isinstance(raw_score, bool):
            raise ValueError(f"Score for {criterion} must be a whole number from 0 to 4.")
        score_value = _finite_number(raw_score, f"Score for {criterion}")
        if not score_value.is_integer() or not 0 <= score_value <= 4:
            raise ValueError(f"Score for {criterion} must be a whole number from 0 to 4.")
        evidence = str(raw.get("evidence", "") or "").strip()
        owner = str(raw.get("owner", "") or "").strip()
        due_date = str(raw.get("due_date", "") or "").strip()
        if due_date:
            try:
                _date.fromisoformat(due_date)
            except ValueError as exc:
                raise ValueError(f"Due date for {criterion} must use ISO YYYY-MM-DD format.") from exc
        needs_follow_up = score_value <= 2
        normalized.append({
            "Category": category,
            "Criterion": criterion,
            "Score (0–4)": int(score_value),
            "Score (%)": score_value / 4.0 * 100.0,
            "Evidence reference": evidence,
            "Owner": owner,
            "Due date": due_date,
            "Follow-up": (
                "Assigned" if needs_follow_up and owner and due_date
                else "Owner/date needed" if needs_follow_up
                else "No low-score action flagged"
            ),
        })

    covered = {row["Category"] for row in normalized}
    expected = set(canonical_categories.values())
    if covered != expected:
        missing = sorted(expected - covered)
        raise ValueError("Checklist must include at least one criterion for each 5S pillar; missing: " + ", ".join(missing))

    checklist = pd.DataFrame(normalized)
    pillar_rows = []
    for category in canonical_categories.values():
        part = checklist[checklist["Category"] == category]
        average = float(part["Score (0–4)"].mean())
        pillar_rows.append({
            "5S pillar": category,
            "Criteria": int(len(part)),
            "Average score (0–4)": average,
            "Pillar score (%)": average / 4.0 * 100.0,
            "Low-score items (≤2)": int((part["Score (0–4)"] <= 2).sum()),
        })
    pillar_summary = pd.DataFrame(pillar_rows)
    overall_equal_pillar_pct = float(pillar_summary["Pillar score (%)"].mean())
    item_weighted_pct = float(checklist["Score (0–4)"].mean() / 4.0 * 100.0)
    priority_actions = checklist[checklist["Score (0–4)"] <= 2].copy().reset_index(drop=True)
    owner_gaps = int(((priority_actions["Owner"].str.strip() == "") | (priority_actions["Due date"].str.strip() == "")).sum())
    if len(priority_actions) and owner_gaps:
        status = "FOLLOW_UP_DETAILS_MISSING"
    elif len(priority_actions):
        status = "FOLLOW_UP_REQUIRED"
    else:
        status = "AUDIT_RECORDED"
    return {
        "status": status,
        "method": "Editable 5S checklist with a disclosed 0–4 self-assessment rubric",
        "overall_5s_score_pct_equal_pillar_weight": overall_equal_pillar_pct,
        "item_weighted_score_pct": item_weighted_pct,
        "criteria_count": int(len(checklist)),
        "priority_action_count": int(len(priority_actions)),
        "priority_action_assignment_gaps": owner_gaps,
        "checklist": checklist,
        "pillar_summary": pillar_summary,
        "priority_actions": priority_actions,
        "formula": "Pillar score = mean item score / 4 × 100; overall score = unweighted mean of the five pillar scores.",
        "rubric": "0 = absent; 1 = largely absent; 2 = inconsistent/partial; 3 = implemented with gaps; 4 = consistently sustained. Adapt and approve this rubric locally.",
        "warning": (
            (f"{len(priority_actions)} checklist item(s) scored 2 or below; {owner_gaps} need an assigned owner and ISO due date."
             if len(priority_actions) else
             "No item scored 2 or below on this self-assessed checklist.")
            + " This is a self-assessment, not a certified audit or independent verification."
        ),
    }


def build_kaizen_a3_record(
    *,
    title: str,
    problem_statement: str,
    metric_name: str,
    unit: str,
    baseline_value: Any,
    target_value: Any,
    root_cause_hypothesis: str,
    countermeasure: str,
    owner: str,
    due_date: str,
    actual_after_value: Any = None,
    baseline_evidence: str = "",
    post_change_evidence: str = "",
    implementation_status: str = "Planned",
    review_date: str = "",
) -> dict[str, Any]:
    """Validate an A3 improvement record and calculate signed progress toward target.

    Target progress is an algebraic ratio; it does not assume which direction is
    operationally desirable. Actual outcomes are explicitly unverified unless
    a human review state, review date and post-change evidence reference exist.
    This builder records one revision's method/fields; UI persistence owns history.
    """
    fields = {
        "A3 title": title,
        "Problem statement": problem_statement,
        "Metric name": metric_name,
        "Metric unit": unit,
        "Root-cause hypothesis": root_cause_hypothesis,
        "Countermeasure": countermeasure,
        "Owner": owner,
        "Due date": due_date,
    }
    cleaned = {key: str(value or "").strip() for key, value in fields.items()}
    for field_name, value in cleaned.items():
        if not value:
            raise ValueError(f"{field_name} is required.")
    due = cleaned["Due date"]
    try:
        _date.fromisoformat(due)
    except ValueError as exc:
        raise ValueError("Due date must use ISO YYYY-MM-DD format.") from exc

    status = str(implementation_status or "").strip()
    allowed_statuses = {"Planned", "In Progress", "Implemented", "Verified", "Closed"}
    if status not in allowed_statuses:
        raise ValueError("Status must be Planned, In Progress, Implemented, Verified or Closed.")

    baseline = _finite_number(baseline_value, "Baseline value")
    target = _finite_number(target_value, "Target value")
    if math.isclose(target, baseline, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Target value must differ from baseline value.")
    if isinstance(actual_after_value, str) and not actual_after_value.strip():
        actual_after_value = None
    actual = None if actual_after_value is None else _finite_number(actual_after_value, "Actual after-change value")
    baseline_ref = str(baseline_evidence or "").strip()
    post_ref = str(post_change_evidence or "").strip()
    review = str(review_date or "").strip()
    if review:
        try:
            _date.fromisoformat(review)
        except ValueError as exc:
            raise ValueError("Review date must use ISO YYYY-MM-DD format.") from exc
    if status in {"Verified", "Closed"} and (actual is None or not post_ref or not review):
        raise ValueError("Verified/Closed status requires an actual result, post-change evidence reference and review date.")

    progress = None if actual is None else (actual - baseline) / (target - baseline) * 100.0
    remaining = None if actual is None else target - actual
    warnings = []
    if not baseline_ref:
        warnings.append("Baseline evidence reference was not provided.")
    if actual is None:
        outcome_status = "NOT_MEASURED"
        warnings.append("No post-change measurement is recorded; do not report realized benefit or verified savings.")
    elif status not in {"Verified", "Closed"}:
        outcome_status = "OBSERVED_NOT_VERIFIED"
        warnings.append("A post-change value is present but is not marked verified by a dated human review with evidence.")
    else:
        outcome_status = "HUMAN_REVIEW_RECORDED"
    if progress is not None and (progress < 0.0 or progress > 100.0):
        warnings.append("Progress falls outside 0–100%; inspect measurement timing, target direction and process variation.")
    warning_text = " ".join(warnings)
    if outcome_status != "HUMAN_REVIEW_RECORDED" and "do not report realized benefit or verified savings" not in warning_text.casefold():
        warning_text = (warning_text + " " if warning_text else "") + "Do not report realized benefit or verified savings without a dated human review and supporting evidence."
    if outcome_status == "HUMAN_REVIEW_RECORDED" and not warning_text:
        warning_text = "A dated human review and post-change evidence reference are recorded; this is not an audited savings certificate."

    return {
        "status": status,
        "outcome_status": outcome_status,
        "title": cleaned["A3 title"],
        "problem_statement": cleaned["Problem statement"],
        "metric_name": cleaned["Metric name"],
        "unit": cleaned["Metric unit"],
        "baseline_value": baseline,
        "target_value": target,
        "actual_after_value": actual,
        "target_progress_pct": progress,
        "remaining_difference_to_target": remaining,
        "root_cause_hypothesis": cleaned["Root-cause hypothesis"],
        "countermeasure": cleaned["Countermeasure"],
        "owner": cleaned["Owner"],
        "due_date": due,
        "baseline_evidence": baseline_ref,
        "post_change_evidence": post_ref,
        "review_date": review,
        "formula": "Progress (%) = (actual after change − baseline) / (target − baseline) × 100. Values are not clamped; direction is not inferred.",
        "assumptions": "The metric, unit, baseline, target and time window must be comparable; a root-cause statement is a hypothesis unless independently evidenced.",
        "warnings": warnings,
        "warning": warning_text,
    }


def calculate_time_study(
    observation_times: Sequence[float],
    performance_rating_pct: float = 100.0,
    allowance_pct: float = 0.0,
    *,
    time_unit: str = "minutes",
) -> dict[str, Any]:
    """Calculate normal and standard time with explicit allowance conventions.

    Allowance is a percentage of standard time:
    normal = mean observed time × rating / 100
    standard = normal / (1 − allowance / 100).
    Observations are not automatically removed as outliers.
    """
    if isinstance(observation_times, (str, bytes)):
        raise ValueError("Observation times must be a numeric sequence, not text.")
    try:
        raw_values = list(observation_times)
    except TypeError as exc:
        raise ValueError("Observation times must be a numeric sequence.") from exc
    if not raw_values:
        raise ValueError("Enter at least one observed time.")
    if any(isinstance(value, bool) for value in raw_values):
        raise ValueError("Observation times must be numeric values, not booleans.")
    values = [_finite_number(value, "Observation time") for value in raw_values]
    if any(value <= 0 for value in values):
        raise ValueError("Every observation time must be greater than zero.")

    rating = _finite_number(performance_rating_pct, "Performance rating")
    allowance = _finite_number(allowance_pct, "Allowance")
    unit = str(time_unit or "").strip()
    if rating <= 0:
        raise ValueError("Performance rating must be greater than zero percent.")
    if allowance < 0 or allowance >= 100:
        raise ValueError("Allowance must be at least 0 and less than 100 percent.")
    if not unit:
        raise ValueError("Time unit must be provided explicitly.")

    mean_time = sum(values) / len(values)
    normal_time = mean_time * rating / 100.0
    standard_time = normal_time / (1.0 - allowance / 100.0)
    sample_sd = float(pd.Series(values, dtype=float).std(ddof=1)) if len(values) > 1 else None
    frame = pd.DataFrame({
        "Observation": range(1, len(values) + 1),
        f"Observed time ({unit})": values,
        f"Deviation from mean ({unit})": [value - mean_time for value in values],
    })
    return {
        "status": "CALCULATED",
        "method": "Time study: arithmetic mean, performance-rating adjustment, and allowance as a percentage of standard time",
        "observation_count": len(values),
        "time_unit": unit,
        "mean_observed_time": mean_time,
        "sample_standard_deviation": sample_sd,
        "performance_rating_pct": rating,
        "normal_time": normal_time,
        "allowance_pct_of_standard_time": allowance,
        "standard_time": standard_time,
        "formula": "Normal time = mean observed time × rating / 100; standard time = normal time / (1 − allowance / 100).",
        "warning": (
            "Fewer than 10 observations were supplied; review representativeness before setting a production standard."
            if len(values) < 10 else
            "Observations are retained as entered; investigate unusual values using the process context rather than automatic deletion."
        ),
        "observations": frame,
    }


def calculate_takt_capacity(
    available_time: float,
    demand_units: float,
    cycle_time: float,
    *,
    time_unit: str = "minutes",
) -> dict[str, Any]:
    """Calculate takt time and implied capacity from consistent time units.

    Available time and demand refer to the same production period; cycle time
    is time per unit in that same period's time unit. Assumes one sequential
    resource and excludes losses not reflected in the inputs.
    """
    available = _finite_number(available_time, "Available production time")
    demand_value = _finite_number(demand_units, "Demand")
    cycle = _finite_number(cycle_time, "Cycle time")
    unit = str(time_unit or "").strip()
    if available <= 0:
        raise ValueError("Available production time must be greater than zero.")
    if demand_value <= 0 or not demand_value.is_integer():
        raise ValueError("Demand must be a positive whole number of units per period.")
    if cycle <= 0:
        raise ValueError("Cycle time must be greater than zero.")
    if not unit:
        raise ValueError("Time unit must be provided explicitly.")

    demand = int(demand_value)
    takt = available / demand
    capacity = available / cycle
    gap = capacity - demand
    utilization = (demand / capacity) * 100.0
    meets_demand = gap >= -1e-9
    return {
        "status": "CAPACITY_MEETS_DEMAND" if meets_demand else "CAPACITY_BELOW_DEMAND",
        "method": "Takt time = net available time / demand; implied capacity = net available time / observed cycle time",
        "time_unit": unit,
        "available_time_per_period": available,
        "demand_units_per_period": demand,
        "cycle_time_per_unit": cycle,
        "takt_time_per_unit": takt,
        "implied_capacity_units_per_period": capacity,
        "capacity_gap_units_per_period": gap,
        "demand_load_pct_of_implied_capacity": utilization,
        "feasible_at_stated_cycle_time": meets_demand,
        "assumptions": "Available time, demand and cycle time refer to the same production period; one sequential resource; cycle time is constant; no unmodeled losses or parallel resources.",
        "formula": "Takt = available time / demand; capacity = available time / cycle time; capacity gap = capacity − demand.",
    }


def _two_sample_t_power(effect_size: float, n_per_group: int, alpha: float) -> float:
    df = 2 * n_per_group - 2
    noncentrality = effect_size * math.sqrt(n_per_group / 2.0)
    critical = float(t.ppf(1.0 - alpha / 2.0, df))
    upper = float(nct.sf(critical, df, noncentrality))
    lower = float(nct.cdf(-critical, df, noncentrality))
    power = upper + lower
    if not math.isfinite(power):
        # SciPy's noncentral-t CDF can lose numerical stability at very large
        # degrees of freedom. In that regime, use the documented normal-limit
        # approximation so NaN cannot distort the sample-size search.
        upper = float(norm.sf(critical - noncentrality))
        lower = float(norm.cdf(-critical - noncentrality))
        power = upper + lower
    return min(1.0, max(0.0, power))


def plan_two_sample_t_sample_size(
    effect_size: float,
    alpha: float = 0.05,
    target_power: float = 0.80,
    *,
    max_n_per_group: int = 10000,
) -> dict[str, Any]:
    """Find balanced per-group n for a two-sided independent two-sample t-test.

    Effect size is standardized Cohen's d. Assumptions: independent observations,
    approximately normal outcomes, equal population variances, equal sample
    sizes, no multiplicity adjustment and no dropout inflation.
    """
    d = _finite_number(effect_size, "Effect size")
    a = _finite_number(alpha, "Alpha")
    target = _finite_number(target_power, "Target power")
    if d <= 0:
        raise ValueError("Effect size must be greater than zero and expressed as standardized Cohen's d.")
    if not 0 < a < 1:
        raise ValueError("Alpha must be strictly between 0 and 1.")
    if not 0 < target < 1:
        raise ValueError("Target power must be strictly between 0 and 1.")
    if target <= a:
        raise ValueError("Target power should exceed alpha for a useful design.")
    if isinstance(max_n_per_group, bool) or not isinstance(max_n_per_group, int) or max_n_per_group < 2:
        raise ValueError("max_n_per_group must be an integer of at least 2.")

    maximum_power = _two_sample_t_power(d, max_n_per_group, a)
    if maximum_power < target:
        return {
            "status": "LIMIT_REACHED",
            "method": "Balanced independent two-sample t-test; noncentral t power with normal-limit fallback for numerical stability",
            "effect_size_cohens_d": d,
            "alpha": a,
            "target_power": target,
            "required_n_per_group": None,
            "total_sample_size": None,
            "achieved_power": maximum_power,
            "search_limit_per_group": max_n_per_group,
            "assumptions": "Two-sided test; independent observations; normal outcomes; equal variances; balanced groups; no multiplicity/dropout adjustment. For extreme degrees of freedom only, normal-limit fallback may be used when the noncentral-t calculation is non-finite.",
            "message": "The requested power was not reached within the configured search limit.",
        }

    low, high = 2, max_n_per_group
    while low < high:
        mid = (low + high) // 2
        if _two_sample_t_power(d, mid, a) >= target:
            high = mid
        else:
            low = mid + 1
    n = low
    achieved = _two_sample_t_power(d, n, a)
    previous = _two_sample_t_power(d, n - 1, a) if n > 2 else 0.0
    return {
        "status": "CALCULATED",
        "method": "Balanced independent two-sample t-test; noncentral t power",
        "effect_size_cohens_d": d,
        "alpha": a,
        "target_power": target,
        "required_n_per_group": n,
        "total_sample_size": 2 * n,
        "achieved_power": achieved,
        "power_at_n_minus_1": previous,
        "search_limit_per_group": max_n_per_group,
        "assumptions": "Two-sided test; independent observations; normal outcomes; equal variances; balanced groups; no multiplicity/dropout adjustment.",
        "message": "Sample size is conditional on the stated design and assumptions; use a suitable design-specific calculation for other tests.",
    }


def calculate_oee(
    planned_time: float, downtime: float, ideal_cycle_time: float,
    total_count: float, good_count: float, *, time_unit: str = "minutes",
) -> dict[str, Any]:
    """Calculate OEE using aligned time/count inputs; never silently cap values."""
    planned = _finite_number(planned_time, "Planned production time")
    down = _finite_number(downtime, "Downtime")
    ideal_cycle = _finite_number(ideal_cycle_time, "Ideal cycle time")
    total_value = _finite_number(total_count, "Total count")
    good_value = _finite_number(good_count, "Good count")
    unit = str(time_unit or "").strip()
    if planned <= 0:
        raise ValueError("Planned production time must be greater than zero.")
    if down < 0 or down >= planned:
        raise ValueError("Downtime must be non-negative and less than planned production time.")
    if ideal_cycle <= 0:
        raise ValueError("Ideal cycle time must be greater than zero.")
    if total_value <= 0 or not total_value.is_integer():
        raise ValueError("Total count must be a positive whole number.")
    if good_value < 0 or not good_value.is_integer():
        raise ValueError("Good count must be a non-negative whole number.")
    if good_value > total_value:
        raise ValueError("Good count cannot exceed total count.")
    if not unit:
        raise ValueError("Time unit must be provided explicitly.")

    total, good = int(total_value), int(good_value)
    operating = planned - down
    availability = operating / planned
    performance = ideal_cycle * total / operating
    quality = good / total
    oee = availability * performance * quality
    expected = ideal_cycle * good / planned
    if not math.isclose(oee, expected, rel_tol=1e-10, abs_tol=1e-12):
        raise ArithmeticError("OEE reconciliation failed; inspect inputs and calculation.")
    ideal_total_time = ideal_cycle * total
    losses = pd.DataFrame([
        {"Component": "Recorded downtime", f"Time equivalent ({unit})": down},
        {"Component": "Performance gap (operating minus ideal total-output time)", f"Time equivalent ({unit})": operating - ideal_total_time},
        {"Component": "Rejected units at ideal cycle time", f"Time equivalent ({unit})": ideal_cycle * (total - good)},
    ])
    review = performance > 1.0 + 1e-9 or oee > 1.0 + 1e-9
    return {
        "status": "REVIEW_PERFORMANCE_OR_OEE_ABOVE_100_PERCENT" if review else "CALCULATED",
        "method": "OEE = availability × performance × quality",
        "planned_time": planned, "downtime": down, "operating_time": operating,
        "ideal_cycle_time": ideal_cycle, "total_count": total, "good_count": good,
        "availability_pct": availability * 100.0,
        "performance_pct": performance * 100.0,
        "quality_pct": quality * 100.0,
        "oee_pct": oee * 100.0,
        "time_unit": unit, "losses": losses,
        "formula": "Availability=(planned−downtime)/planned; performance=ideal cycle×total/operating; quality=good/total; OEE=product.",
        "assumptions": "Downtime is within planned time; ideal cycle is appropriate for the product mix; counts cover the same period and scope.",
        "warning": "Performance/OEE above 100% indicates definitions or inputs need reconciliation; no metric is silently capped." if review else "Confirm source timestamps, cycle-time basis and loss definitions before making operational decisions.",
    }


def analyze_process_capability(
    measurements: Sequence[float], lsl: float, usl: float, *,
    subgroup_size: int, unit: str = "units",
) -> dict[str, Any]:
    """Compute Cp/Cpk using pooled within-subgroup sigma, and Pp/Ppk overall sigma."""
    if isinstance(measurements, (str, bytes)):
        raise ValueError("Measurements must be a numeric sequence, not text.")
    try:
        raw = list(measurements)
    except TypeError as exc:
        raise ValueError("Measurements must be a numeric sequence.") from exc
    if len(raw) < 4:
        raise ValueError("Provide at least four measurements across at least two subgroups.")
    if any(isinstance(value, bool) for value in raw):
        raise ValueError("Measurements must be numeric values, not booleans.")
    values = [_finite_number(v, "Measurement") for v in raw]
    lower, upper = _finite_number(lsl, "Lower specification limit"), _finite_number(usl, "Upper specification limit")
    if lower >= upper:
        raise ValueError("Lower specification limit must be less than upper specification limit.")
    if isinstance(subgroup_size, bool) or not isinstance(subgroup_size, int) or subgroup_size < 2:
        raise ValueError("Subgroup size must be an integer of at least 2.")
    if len(values) % subgroup_size:
        raise ValueError("Measurement count must be divisible by subgroup size.")
    subgroup_count = len(values) // subgroup_size
    if subgroup_count < 2:
        raise ValueError("Provide at least two consecutive subgroups.")
    normalized_unit = str(unit or "").strip()
    if not normalized_unit:
        raise ValueError("Measurement unit must be provided explicitly.")
    n = len(values)
    mean_value = sum(values) / n
    overall_sigma = math.sqrt(sum((v - mean_value) ** 2 for v in values) / (n - 1))
    within_sumsq = 0.0
    subgroup_means = []
    for offset in range(0, n, subgroup_size):
        subgroup = values[offset:offset + subgroup_size]
        subgroup_mean = sum(subgroup) / subgroup_size
        subgroup_means.append(subgroup_mean)
        within_sumsq += sum((v - subgroup_mean) ** 2 for v in subgroup)
    within_sigma = math.sqrt(within_sumsq / (n - subgroup_count))
    if within_sigma <= 0 or overall_sigma <= 0:
        raise ValueError("Capability indices are undefined when within or overall variation is zero.")
    cp = (upper - lower) / (6.0 * within_sigma)
    cpk = min(upper - mean_value, mean_value - lower) / (3.0 * within_sigma)
    pp = (upper - lower) / (6.0 * overall_sigma)
    ppk = min(upper - mean_value, mean_value - lower) / (3.0 * overall_sigma)
    frame = pd.DataFrame({
        "Observation": range(1, n + 1),
        f"Measurement ({normalized_unit})": values,
        "Subgroup": [i // subgroup_size + 1 for i in range(n)],
    })
    return {
        "status": "CALCULATED",
        "method": "Cp/Cpk use pooled within-subgroup sample sigma; Pp/Ppk use overall sample sigma.",
        "sample_count": n, "subgroup_count": subgroup_count, "subgroup_size": subgroup_size,
        "mean": mean_value, "lsl": lower, "usl": upper, "unit": normalized_unit,
        "within_sigma": within_sigma, "overall_sigma": overall_sigma,
        "cp": cp, "cpk": cpk, "pp": pp, "ppk": ppk,
        "cpl": (mean_value - lower) / (3.0 * within_sigma),
        "cpu": (upper - mean_value) / (3.0 * within_sigma),
        "ppl": (mean_value - lower) / (3.0 * overall_sigma),
        "ppu": (upper - mean_value) / (3.0 * overall_sigma),
        "subgroup_means": subgroup_means, "series": frame,
        "formula": "Cp=(USL−LSL)/(6×within sigma); Cpk=min(USL−mean,mean−LSL)/(3×within sigma); Pp/Ppk use overall sample sigma.",
        "assumptions": "Consecutive equal-size rational subgroups and a stable measurement method; this function does not perform normality or statistical-control tests.",
        "warning": "Fewer than 25 subgroups supplied. Review stability, normality, measurement system and sampling design before interpreting capability.",
    }


def plan_inventory_policy(
    mean_daily_demand: float, daily_demand_stddev: float, lead_time_days: float,
    order_cost_per_order: float, annual_holding_cost_per_unit: float, *,
    operating_days_per_year: int = 365, service_factor_z: float = 1.645,
) -> dict[str, Any]:
    """Classical EOQ, safety stock and reorder point with explicit assumptions."""
    demand = _finite_number(mean_daily_demand, "Mean daily demand")
    sigma = _finite_number(daily_demand_stddev, "Daily demand standard deviation")
    lead = _finite_number(lead_time_days, "Lead time")
    order_cost = _finite_number(order_cost_per_order, "Order cost")
    holding = _finite_number(annual_holding_cost_per_unit, "Annual holding cost")
    z = _finite_number(service_factor_z, "Service factor z")
    if demand <= 0:
        raise ValueError("Mean daily demand must be greater than zero.")
    if sigma < 0 or lead < 0:
        raise ValueError("Demand standard deviation and lead time cannot be negative.")
    if order_cost <= 0 or holding <= 0:
        raise ValueError("Order cost and annual holding cost must both be greater than zero.")
    if isinstance(operating_days_per_year, bool) or not isinstance(operating_days_per_year, int) or not 1 <= operating_days_per_year <= 366:
        raise ValueError("Operating days per year must be an integer from 1 through 366.")
    if z < 0:
        raise ValueError("Service factor z cannot be negative.")
    annual_demand = demand * operating_days_per_year
    eoq = math.sqrt(2.0 * annual_demand * order_cost / holding)
    safety_stock = z * sigma * math.sqrt(lead)
    reorder_point = demand * lead + safety_stock
    return {
        "status": "CALCULATED",
        "method": "Classical EOQ with safety stock under independent daily demand and deterministic lead time.",
        "annual_demand_units": annual_demand, "economic_order_quantity_units": eoq,
        "safety_stock_units": safety_stock, "reorder_point_units": reorder_point,
        "mean_daily_demand_units": demand, "daily_demand_stddev_units": sigma,
        "lead_time_days": lead, "service_factor_z": z,
        "operating_days_per_year": operating_days_per_year,
        "order_cost_per_order": order_cost, "annual_holding_cost_per_unit": holding,
        "formula": "EOQ=sqrt(2×annual demand×order cost/annual holding cost); safety stock=z×daily demand SD×sqrt(lead days); reorder point=mean daily demand×lead days+safety stock.",
        "assumptions": "Demand/lead time are in days; stable independent daily demand; deterministic lead time; consistent annual holding-cost/currency basis.",
        "warning": "Adjust for intermittent/correlated demand, variable lead time, minimum order quantities, perishability and multi-echelon effects.",
    }


def calculate_carbon_emissions(
    activity_amount: float, emission_factor_kg_co2e_per_activity_unit: float, *,
    activity_unit: str, factor_unit: str, factor_source: str, factor_date: str, boundary: str,
) -> dict[str, Any]:
    """Multiply activity by explicitly supplied emission factor, without audit claims."""
    amount = _finite_number(activity_amount, "Activity amount")
    factor = _finite_number(emission_factor_kg_co2e_per_activity_unit, "Emission factor")
    unit, factor_units = str(activity_unit or "").strip(), str(factor_unit or "").strip()
    source, date_text, bound = str(factor_source or "").strip(), str(factor_date or "").strip(), str(boundary or "").strip()
    if amount < 0 or factor < 0:
        raise ValueError("Activity amount and emission factor must be non-negative.")
    if not all((unit, factor_units, source, bound)):
        raise ValueError("Activity unit, factor unit, factor source and accounting boundary are required.")
    try:
        parsed_date = _date.fromisoformat(date_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("Factor date must use ISO YYYY-MM-DD format.") from exc
    if parsed_date.isoformat() != date_text:
        raise ValueError("Factor date must use ISO YYYY-MM-DD format.")
    kilograms = amount * factor
    return {
        "status": "CALCULATED_FROM_USER_SUPPLIED_FACTOR",
        "method": "Activity data multiplied by user-supplied emission factor.",
        "activity_amount": amount, "activity_unit": unit,
        "emission_factor_kg_co2e_per_activity_unit": factor,
        "factor_unit_label": factor_units, "factor_source": source, "factor_date": date_text,
        "boundary": bound, "emissions_kg_co2e": kilograms, "emissions_tonnes_co2e": kilograms / 1000.0,
        "formula": "Emissions (kg CO2e)=activity amount×emission factor; tonnes CO2e=kg CO2e/1,000.",
        "warning": "The factor and activity records were not independently verified. Confirm units, source, date and accounting boundary; this is not an audited GHG disclosure.",
    }


def analyze_engineering_economics(
    cash_flows: Sequence[float], discount_rate_pct: float, *,
    currency: str, period_unit: str = "years",
) -> dict[str, Any]:
    """Compute NPV/simple payback; report IRR only for a conventional bracketed root."""
    if isinstance(cash_flows, (str, bytes)):
        raise ValueError("Cash flows must be a numeric sequence, not text.")
    try:
        raw = list(cash_flows)
    except TypeError as exc:
        raise ValueError("Cash flows must be a numeric sequence.") from exc
    if not 2 <= len(raw) <= 101:
        raise ValueError("Provide 2 through 101 cash flows (time zero plus up to 100 later periods).")
    if any(isinstance(value, bool) for value in raw):
        raise ValueError("Cash flows must be numeric values, not booleans.")
    flows = [_finite_number(v, "Cash flow") for v in raw]
    discount = _finite_number(discount_rate_pct, "Discount rate")
    curr, period = str(currency or "").strip(), str(period_unit or "").strip()
    if discount <= -100:
        raise ValueError("Discount rate must be greater than -100 percent.")
    if not curr or not period:
        raise ValueError("Currency and period unit are required.")
    rate = discount / 100.0
    discounted = [flow / ((1.0 + rate) ** i) for i, flow in enumerate(flows)]
    npv = sum(discounted)
    cumulative, running = [], 0.0
    for flow in flows:
        running += flow
        cumulative.append(running)
    payback = None
    if flows[0] < 0:
        for i in range(1, len(flows)):
            prior, current = cumulative[i-1], cumulative[i]
            if prior < 0 <= current and flows[i] > 0:
                payback = float((i - 1) + (-prior / flows[i]))
                break
    signs = [1 if f > 0 else -1 for f in flows if f != 0]
    sign_changes = sum(a != b for a, b in zip(signs, signs[1:]))
    irr_rate, irr_status = None, "NOT_CALCULATED_NONCONVENTIONAL_CASH_FLOWS"
    if flows[0] < 0 and sign_changes == 1:
        def npv_at(r: float) -> float:
            return sum(flow / ((1.0 + r) ** i) for i, flow in enumerate(flows))
        lo, hi = -0.99, 0.1
        f_lo, f_hi = npv_at(lo), npv_at(hi)
        while f_lo * f_hi > 0 and hi < 10.0:
            hi = min(10.0, hi * 2.0 + 0.1)
            f_hi = npv_at(hi)
        if f_lo == 0:
            irr_rate = lo
        elif f_hi == 0:
            irr_rate = hi
        elif (f_lo < 0 < f_hi) or (f_hi < 0 < f_lo):
            for _ in range(200):
                mid = (lo + hi) / 2.0
                f_mid = npv_at(mid)
                if abs(f_mid) < 1e-10 or (hi - lo) < 1e-12:
                    lo = hi = mid
                    break
                if (f_lo < 0 <= f_mid) or (f_mid < 0 <= f_lo):
                    hi, f_hi = mid, f_mid
                else:
                    lo, f_lo = mid, f_mid
            irr_rate = (lo + hi) / 2.0
        irr_status = "CALCULATED" if irr_rate is not None else "IRR_OUTSIDE_SUPPORTED_SEARCH_RANGE"
    frame = pd.DataFrame({
        "Period": range(len(flows)), f"Cash flow ({curr})": flows,
        f"Discounted cash flow ({curr})": discounted,
        f"Cumulative cash flow ({curr})": cumulative,
    })
    return {
        "status": "CALCULATED", "method": "End-of-period NPV; simple interpolated payback; IRR only when a supported conventional root is bracketed.",
        "currency": curr, "period_unit": period, "cash_flows": flows,
        "discount_rate_pct": discount, "npv": npv,
        "irr_pct": irr_rate * 100.0 if irr_rate is not None else None,
        "irr_status": irr_status, "simple_payback_periods": payback,
        "sign_changes_in_nonzero_cash_flows": sign_changes, "cash_flow_schedule": frame,
        "formula": "NPV=sum(CF_t/(1+r)^t) including CF_0 at t=0; IRR solves NPV(r)=0; simple payback is undiscounted.",
        "assumptions": "Cash flows are evenly spaced end-of-period amounts after CF_0; currency is consistent; no tax, inflation or financing treatment is inferred.",
        "warning": "Scenario calculation only, not verified realized benefit. IRR is omitted for nonconventional cash flows or unsupported roots." if irr_rate is None else "Scenario calculation only, not verified realized benefit. Review cash-flow timing, taxes, inflation and financing as applicable.",
    }



def convert_units_or_currency(
    amount: float, from_unit: str, to_unit: str, *,
    exchange_rate: float | None = None, exchange_rate_date: str = "",
    exchange_rate_source: str = "",
) -> dict[str, Any]:
    """Convert supported physical units or currencies using a dated user rate.

    Currency rate means target-currency units per one source-currency unit.
    The function never fetches, fabricates or implies a live exchange rate.
    """
    value = _finite_number(amount, "Value to convert")
    source, target = str(from_unit or "").strip(), str(to_unit or "").strip()
    if not source or not target:
        raise ValueError("Source and target units or currencies are required.")
    unit_defs = {
        "mm": ("length", .001, "m"), "cm": ("length", .01, "m"),
        "m": ("length", 1., "m"), "km": ("length", 1000., "m"),
        "in": ("length", .0254, "m"), "ft": ("length", .3048, "m"),
        "mi": ("length", 1609.344, "m"),
        "mg": ("mass", 1e-6, "kg"), "g": ("mass", .001, "kg"),
        "kg": ("mass", 1., "kg"), "lb": ("mass", .45359237, "kg"),
        "oz": ("mass", .028349523125, "kg"),
        "ms": ("time", .001, "s"), "s": ("time", 1., "s"),
        "min": ("time", 60., "s"), "h": ("time", 3600., "s"),
        "day": ("time", 86400., "s"),
        "ml": ("volume", 1e-6, "m³"), "l": ("volume", .001, "m³"),
        "m³": ("volume", 1., "m³"), "gal": ("volume", .003785411784, "m³"),
        "wh": ("energy", 3600., "J"), "kwh": ("energy", 3.6e6, "J"),
        "mj": ("energy", 1e6, "J"), "gj": ("energy", 1e9, "J"),
        "pa": ("pressure", 1., "Pa"), "kpa": ("pressure", 1000., "Pa"),
        "bar": ("pressure", 100000., "Pa"), "psi": ("pressure", 6894.757293168, "Pa"),
    }
    aliases = {
        "millimeter": "mm", "millimeters": "mm", "centimeter": "cm",
        "centimeters": "cm", "meter": "m", "meters": "m", "metre": "m",
        "kilometer": "km", "kilometers": "km", "inch": "in", "inches": "in",
        "foot": "ft", "feet": "ft", "mile": "mi", "miles": "mi",
        "milligram": "mg", "gram": "g", "grams": "g", "kilogram": "kg",
        "kilograms": "kg", "pound": "lb", "pounds": "lb", "ounce": "oz",
        "second": "s", "seconds": "s", "minute": "min", "minutes": "min",
        "hour": "h", "hours": "h", "days": "day", "milliliter": "ml",
        "millilitre": "ml", "liter": "l", "litre": "l", "gallon": "gal",
        "gallons": "gal", "cubic meter": "m³", "cubic metre": "m³",
        "watt-hour": "wh", "kilowatt-hour": "kwh", "megajoule": "mj",
        "gigajoule": "gj", "celsius": "°c", "fahrenheit": "°f", "kelvin": "k",
    }
    a = aliases.get(source.casefold(), source.casefold())
    b = aliases.get(target.casefold(), target.casefold())
    curr = {"sar","usd","eur","gbp","aed","inr","jpy","cny","kwd","bhd","qar","omr","egp","pkr","try","cad","aud","chf","sgd","krw"}
    if a in curr or b in curr:
        if a not in curr or b not in curr:
            raise ValueError("Currency codes cannot be converted to physical units.")
        if a == b:
            return {"status":"CONVERTED_SAME_CURRENCY","method":"Same currency; no exchange rate required",
                    "input_value":value,"source_unit":source.upper(),"target_unit":target.upper(),
                    "converted_value":value,"exchange_rate_target_per_source":1.0,
                    "exchange_rate_date":None,"exchange_rate_source":"Same currency; no external rate required",
                    "formula":"Same source and target currency; value is unchanged.",
                    "warning":"No currency exchange was performed."}
        rate = _finite_number(exchange_rate, "Exchange rate") if exchange_rate is not None else math.nan
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("A positive exchange rate (target currency per source currency unit) is required.")
        rate_source, date_text = str(exchange_rate_source or "").strip(), str(exchange_rate_date or "").strip()
        if not rate_source:
            raise ValueError("Exchange-rate source is required.")
        try:
            parsed = _date.fromisoformat(date_text)
        except (TypeError, ValueError) as exc:
            raise ValueError("Exchange-rate date must use ISO YYYY-MM-DD format.") from exc
        if parsed.isoformat() != date_text:
            raise ValueError("Exchange-rate date must use ISO YYYY-MM-DD format.")
        return {"status":"CONVERTED_USING_USER_SUPPLIED_RATE","method":"Explicit user-supplied exchange rate",
                "input_value":value,"source_unit":source.upper(),"target_unit":target.upper(),
                "converted_value":value*rate,"exchange_rate_target_per_source":rate,
                "exchange_rate_date":date_text,"exchange_rate_source":rate_source,
                "formula":"Converted amount = source amount × (target currency units / source currency unit).",
                "warning":"Rate metadata is user supplied and unverified; confirm quote direction, effective date, fees and accounting policy."}
    temps = {"°c","°f","k","celsius","fahrenheit","kelvin"}
    if a in temps or b in temps:
        if a not in temps or b not in temps:
            raise ValueError("Temperature units can only be converted to another temperature unit.")
        if a in {"°c","celsius"}: kelvin=value+273.15
        elif a in {"°f","fahrenheit"}: kelvin=(value-32)*(5/9)+273.15
        else: kelvin=value
        if kelvin < 0: raise ValueError("Absolute temperature cannot be below 0 K.")
        if b in {"°c","celsius"}: converted=kelvin-273.15
        elif b in {"°f","fahrenheit"}: converted=(kelvin-273.15)*(9/5)+32
        else: converted=kelvin
        dimension, formula = "temperature", "Convert source temperature to kelvin, then to target scale."
    else:
        sd, td = unit_defs.get(a), unit_defs.get(b)
        if sd is None or td is None:
            raise ValueError(f"Unsupported unit or currency: {source!r} or {target!r}.")
        if sd[0] != td[0]:
            raise ValueError(f"Incompatible dimensions: {sd[0]} cannot be converted to {td[0]}.")
        dimension=sd[0]
        converted=value*sd[1]/td[1]
        formula=f"Converted value = input × {sd[1]:g} / {td[1]:g} using base unit {sd[2]}."
    return {"status":"CONVERTED","method":"Dimension-checked fixed-factor conversion",
            "input_value":value,"source_unit":source,"target_unit":target,
            "converted_value":converted,"dimension":dimension,"formula":formula,
            "warning":"Confirm significant figures, standards and rounding before regulated reporting."}


def analyze_spc_individuals(measurements: Sequence[float], *, unit: str = "units") -> dict[str, Any]:
    """Build Individuals/Moving-Range control limits; detect points outside limits only."""
    if isinstance(measurements, (str, bytes)): raise ValueError("Measurements must be a numeric sequence, not text.")
    try: raw=list(measurements)
    except TypeError as exc: raise ValueError("Measurements must be a numeric sequence.") from exc
    if len(raw)<3: raise ValueError("Provide at least three consecutive measurements for an Individuals chart.")
    if any(isinstance(v,bool) for v in raw): raise ValueError("Measurements must be numeric values, not booleans.")
    values=[_finite_number(v,"SPC measurement") for v in raw]
    normalized_unit=str(unit or "").strip()
    if not normalized_unit: raise ValueError("Measurement unit must be provided explicitly.")
    mr=[None]+[abs(values[i]-values[i-1]) for i in range(1,len(values))]
    mrbar=sum(float(v) for v in mr[1:])/(len(values)-1)
    if mrbar<=0: raise ValueError("Moving-range average is zero; an Individuals sigma estimate cannot be established.")
    mean=sum(values)/len(values)
    sigma=mrbar/1.128
    ucl, lcl=mean+3*sigma, mean-3*sigma
    mrucl=3.267*mrbar
    i_signals=[i+1 for i,v in enumerate(values) if v>ucl or v<lcl]
    mr_signals=[i+1 for i,v in enumerate(mr[1:],start=1) if float(v)>mrucl]
    chart=pd.DataFrame({
        "Observation":range(1,len(values)+1),f"Measurement ({normalized_unit})":values,
        f"I center ({normalized_unit})":[mean]*len(values),f"I UCL ({normalized_unit})":[ucl]*len(values),
        f"I LCL ({normalized_unit})":[lcl]*len(values),"Moving range":mr,
        "MR center":[mrbar]*len(values),"MR UCL":[mrucl]*len(values),"MR LCL":[0.]*len(values)})
    return {"status":"POINTS_OUTSIDE_CONTROL_LIMITS" if i_signals or mr_signals else "NO_POINT_OUTSIDE_CALCULATED_LIMITS",
            "method":"Individuals/Moving-Range chart: d2=1.128, D4=3.267, D3=0; 3-sigma I limits.",
            "sample_count":len(values),"unit":normalized_unit,"mean":mean,"moving_range_average":mrbar,
            "estimated_within_sigma":sigma,"individuals_ucl":ucl,"individuals_lcl":lcl,
            "moving_range_ucl":mrucl,"moving_range_lcl":0.,"individuals_signal_observations":i_signals,
            "moving_range_signal_end_observations":mr_signals,"chart_data":chart,
            "formula":"I limits=grand mean ± 3×(average moving range/1.128); MR UCL=3.267×average moving range; MR LCL=0.",
            "assumptions":"Chronological measurements from a consistent process and measurement system. Control limits are not specification limits.",
            "warning":"Only points beyond the calculated 3-sigma limits are detected; no Nelson/Western Electric rules, normality check or stability certification is performed."}


def analyze_quality_cost_defects(
    total_units: float, defective_units: float, scrap_units: float, rework_units: float,
    scrap_cost_per_unit: float, rework_cost_per_unit: float, inspection_cost: float, *,
    currency: str = "SAR", period: str = "unspecified period",
) -> dict[str, Any]:
    """Reconcile scrap, rework and inspection costs using explicit disjoint dispositions."""
    nums=[_finite_number(v,n) for v,n in [
        (total_units,"Total produced units"),(defective_units,"Defective units"),(scrap_units,"Scrap units"),
        (rework_units,"Rework units"),(scrap_cost_per_unit,"Scrap cost per unit"),
        (rework_cost_per_unit,"Rework cost per unit"),(inspection_cost,"Inspection cost")]]
    totalv, defectv, scrapv, reworkv, scraprate, reworkrate, inspect=nums
    curr, period_text=str(currency or "").strip().upper(),str(period or "").strip()
    if totalv<=0 or not totalv.is_integer(): raise ValueError("Total produced units must be a positive whole number.")
    if any(v<0 or not v.is_integer() for v in (defectv,scrapv,reworkv)): raise ValueError("Defect, scrap and rework counts must be non-negative whole numbers.")
    if defectv>totalv: raise ValueError("Defective units cannot exceed total produced units.")
    if scrapv+reworkv>defectv: raise ValueError("Scrap and rework dispositions cannot exceed the defective-unit count.")
    if any(v<0 for v in (scraprate,reworkrate,inspect)): raise ValueError("Unit costs and inspection cost cannot be negative.")
    if not curr or not period_text: raise ValueError("Currency and period must be provided.")
    total,defective,scrap,rework=map(int,(totalv,defectv,scrapv,reworkv))
    sc=scrap*scraprate; rc=rework*reworkrate; copq=sc+rc+inspect
    breakdown=pd.DataFrame([
        {"Cost component":"Scrap",f"Cost ({curr})":sc},
        {"Cost component":"Rework",f"Cost ({curr})":rc},
        {"Cost component":"Inspection",f"Cost ({curr})":inspect}])
    return {"status":"CALCULATED","method":"Scoped COPQ proxy = scrap + rework + inspection cost",
            "period":period_text,"currency":curr,"total_units":total,"defective_units":defective,
            "scrap_units":scrap,"rework_units":rework,"defective_rate_pct":defective/total*100,
            "scrap_rate_pct":scrap/total*100,"rework_rate_pct":rework/total*100,
            "scrap_cost":sc,"rework_cost":rc,"inspection_cost":inspect,"cost_of_poor_quality":copq,
            "copq_per_produced_unit":copq/total,"cost_breakdown":breakdown,
            "formula":"COPQ proxy=scrap units×scrap cost/unit + rework units×rework cost/unit + inspection cost.",
            "assumptions":"Scrap and rework are mutually exclusive dispositions among defective units; costs share one currency/period.",
            "warning":"This scoped estimate excludes warranty, returns, prevention, other appraisal and opportunity costs; it is not a complete quality-cost ledger."}


def analyze_mtbf_mttr(operating_hours: float, repair_durations_hours: Sequence[float]) -> dict[str, Any]:
    """Calculate MTBF and MTTR from complete recorded failures and repairs."""
    operating=_finite_number(operating_hours,"Accumulated operating hours")
    if operating<=0: raise ValueError("Accumulated operating hours must be greater than zero.")
    if isinstance(repair_durations_hours,(str,bytes)): raise ValueError("Repair durations must be a numeric sequence, not text.")
    try: raw=list(repair_durations_hours)
    except TypeError as exc: raise ValueError("Repair durations must be a numeric sequence.") from exc
    if not raw: raise ValueError("Provide at least one observed failure repair duration.")
    if any(isinstance(v,bool) for v in raw): raise ValueError("Repair durations must be numeric values, not booleans.")
    durations=[_finite_number(v,"Repair duration") for v in raw]
    if any(v<0 for v in durations): raise ValueError("Repair durations cannot be negative.")
    count=len(durations); mtbf=operating/count; mttr=sum(durations)/count
    availability=mtbf/(mtbf+mttr) if mtbf+mttr>0 else None
    frame=pd.DataFrame({"Failure event":range(1,count+1),"Repair duration (hours)":durations})
    return {"status":"CALCULATED","method":"MTBF=operating hours/recorded failures; MTTR=mean recorded repair duration.",
            "operating_hours":operating,"failure_count":count,"total_repair_hours":sum(durations),
            "mtbf_hours":mtbf,"mttr_hours":mttr,
            "steady_state_availability_estimate_pct":availability*100 if availability is not None else None,
            "repair_summary":frame,"formula":"MTBF=operating hours/failures; MTTR=Σ repair duration/failures; availability approximation=MTBF/(MTBF+MTTR).",
            "assumptions":"Complete recorded failures/repairs only; operating hours exclude repair downtime; censoring and incomplete windows are not modeled.",
            "warning":"Availability is a simplified steady-state estimate. Validate failure definitions, asset boundary and observation window."}


def analyze_abc_xyz_inventory(
    items: Sequence[Mapping[str, Any]], *, a_threshold: float=.80, b_threshold: float=.95,
    x_cv_max: float=.50, y_cv_max: float=1.0, currency: str="SAR",
) -> dict[str, Any]:
    """Classify SKUs by annual usage value (ABC) and population demand CV (XYZ)."""
    if isinstance(items,(str,bytes)): raise ValueError("Inventory items must be structured SKU records, not text.")
    try: raw=list(items)
    except TypeError as exc: raise ValueError("Inventory items must be a sequence of records.") from exc
    if not raw: raise ValueError("Provide at least one SKU record.")
    ac,bc,xc,yc=(_finite_number(a_threshold,"A threshold"),_finite_number(b_threshold,"B threshold"),
                   _finite_number(x_cv_max,"X CV threshold"),_finite_number(y_cv_max,"Y CV threshold"))
    curr=str(currency or "").strip().upper()
    if not (0<ac<bc<=1): raise ValueError("ABC thresholds must satisfy 0 < A threshold < B threshold <= 1.")
    if xc<0 or yc<=xc: raise ValueError("Variability thresholds must satisfy 0 <= X threshold < Y threshold.")
    if not curr: raise ValueError("Currency code is required.")
    records=[]; seen=set(); histlen=None
    for item in raw:
        if not isinstance(item,Mapping): raise ValueError("Each SKU must be an object containing sku, annual_demand, unit_cost and period_demand.")
        sku=str(item.get("sku") or "").strip()
        if not sku: raise ValueError("Every SKU must have a non-empty identifier.")
        if sku.casefold() in seen: raise ValueError(f"Duplicate SKU identifier: {sku}.")
        seen.add(sku.casefold())
        demand=_finite_number(item.get("annual_demand"),f"Annual demand for {sku}")
        cost=_finite_number(item.get("unit_cost"),f"Unit cost for {sku}")
        history=item.get("period_demand")
        if not isinstance(history,Sequence) or isinstance(history,(str,bytes)) or len(history)<2:
            raise ValueError(f"SKU {sku} needs at least two period_demand observations.")
        if histlen is None: histlen=len(history)
        if len(history)!=histlen: raise ValueError("All SKUs must use the same number of historical demand periods.")
        vals=[_finite_number(v,f"Demand observation for {sku}") for v in history]
        if demand<0 or cost<0 or any(v<0 for v in vals): raise ValueError("Demand and unit costs cannot be negative.")
        mean=sum(vals)/len(vals)
        cv=(math.sqrt(sum((v-mean)**2 for v in vals)/len(vals))/mean) if mean>0 else None
        xyz="X" if cv is not None and cv<=xc else "Y" if cv is not None and cv<=yc else "Z"
        records.append({"SKU":sku,"Annual demand (units)":demand,f"Unit cost ({curr})":cost,
                        f"Annual usage value ({curr})":demand*cost,"Mean demand per period":mean,
                        "Demand CV (population)":cv,"XYZ":xyz})
    key=f"Annual usage value ({curr})"; total_value=sum(r[key] for r in records)
    if total_value<=0: raise ValueError("Total annual usage value must be greater than zero for ABC classification.")
    records.sort(key=lambda r:(-r[key],r["SKU"].casefold()))
    cumulative=0.
    for r in records:
        prior=cumulative; share=r[key]/total_value; cumulative+=share
        r["Annual usage share (%)"]=share*100; r["Cumulative usage value (%)"]=cumulative*100
        r["ABC"]="A" if prior<ac else "B" if prior<bc else "C"
        r["ABC/XYZ class"]=f"{r['ABC']}-{r['XYZ']}"
    return {"status":"CALCULATED","method":"ABC by descending annual usage value; XYZ by population CV of aligned demand periods.",
            "sku_count":len(records),"currency":curr,"annual_usage_value_total":total_value,
            "a_threshold_pct":ac*100,"b_threshold_pct":bc*100,"x_cv_max":xc,"y_cv_max":yc,
            "classification":pd.DataFrame(records),
            "formula":"Annual usage value=annual demand×unit cost; ABC uses cumulative value; CV=population SD(period demand)/mean period demand.",
            "assumptions":"SKU costs share a currency; annual demand is consistently defined; histories have matching period frequencies; cutoffs are explicit.",
            "warning":"This segmentation does not determine reorder quantities or certify service levels. Review seasonality, criticality, lead time and data completeness."}


__all__ = [
    "analyze_work_sampling",
    "analyze_pareto_root_cause",
    "assess_5s_audit",
    "convert_units_or_currency",
    "analyze_spc_individuals",
    "analyze_quality_cost_defects",
    "analyze_mtbf_mttr",
    "analyze_abc_xyz_inventory",
    "calculate_oee",
    "analyze_process_capability",
    "plan_inventory_policy",
    "calculate_carbon_emissions",
    "analyze_engineering_economics",
    "build_kaizen_a3_record",
    "calculate_time_study",
    "calculate_takt_capacity",
    "monitor_forecast_drift",
    "plan_two_sample_t_sample_size",
]


# --- Additional user-facing specialist methods wired into the 100-tool Workbench ---

def balance_production_line(
    tasks: Sequence[Mapping[str, Any]],
    cycle_time: float,
    *,
    time_unit: str = "seconds",
) -> dict[str, Any]:
    """Build a precedence-feasible greedy line balance (not a global optimizer).

    Tasks are emitted in a stable topological order, then packed sequentially
    into stations without exceeding the declared cycle time. The method is
    intentionally described as a heuristic so its result is not mistaken for
    a proof of globally optimal station count.
    """
    cycle = _finite_number(cycle_time, "Cycle time")
    unit = str(time_unit or "").strip()
    if cycle <= 0:
        raise ValueError("Cycle time must be greater than zero.")
    if not unit:
        raise ValueError("Time unit is required.")
    if isinstance(tasks, (str, bytes)) or not isinstance(tasks, Sequence) or not tasks:
        raise ValueError("Provide at least one task object.")
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for i, task in enumerate(tasks, start=1):
        if not isinstance(task, Mapping):
            raise ValueError(f"Task row {i} must be an object.")
        task_id = str(task.get("task_id", task.get("id", ""))).strip()
        if not task_id:
            raise ValueError(f"Task row {i} needs a task_id.")
        if task_id in ids:
            raise ValueError(f"Task IDs must be unique. Duplicate: {task_id}.")
        ids.add(task_id)
        duration = _finite_number(task.get("duration"), f"Duration for task {task_id}")
        if duration <= 0:
            raise ValueError(f"Duration for task {task_id} must be greater than zero.")
        raw_predecessors = task.get("predecessors", [])
        if raw_predecessors is None or raw_predecessors == "":
            predecessors = []
        elif isinstance(raw_predecessors, str):
            predecessors = [p.strip() for p in raw_predecessors.split(",") if p.strip()]
        elif isinstance(raw_predecessors, Sequence) and not isinstance(raw_predecessors, (str, bytes)):
            predecessors = [str(p).strip() for p in raw_predecessors if str(p).strip()]
        else:
            raise ValueError(f"Predecessors for task {task_id} must be a list or comma-separated text.")
        if task_id in predecessors:
            raise ValueError(f"Task {task_id} cannot depend on itself.")
        if len(predecessors) != len(set(predecessors)):
            raise ValueError(f"Task {task_id} contains duplicate predecessors.")
        normalized.append({"task_id": task_id, "duration": duration, "predecessors": predecessors})

    for task in normalized:
        unknown = sorted(set(task["predecessors"]) - ids)
        if unknown:
            raise ValueError(f"Task {task['task_id']} references unknown predecessor(s): {', '.join(unknown)}.")
    oversized = [
        {"task_id": task["task_id"], "duration": task["duration"]}
        for task in normalized if task["duration"] > cycle + 1e-9
    ]
    if oversized:
        return {
            "status": "INFEASIBLE",
            "method": "Stable topological order plus sequential greedy station packing",
            "cycle_time": cycle,
            "time_unit": unit,
            "station_count": None,
            "theoretical_minimum_stations": math.ceil(sum(t["duration"] for t in normalized) / cycle),
            "efficiency_pct": None,
            "balance_delay_pct": None,
            "issues": oversized,
            "station_summary": pd.DataFrame(),
            "task_assignment": pd.DataFrame(),
            "warning": "At least one task exceeds the cycle-time limit; split or redesign that task before balancing.",
        }

    remaining = list(normalized)
    scheduled: set[str] = set()
    ordered: list[dict[str, Any]] = []
    while remaining:
        ready_index = next(
            (i for i, task in enumerate(remaining) if set(task["predecessors"]).issubset(scheduled)),
            None,
        )
        if ready_index is None:
            raise ValueError("Task precedence graph contains a cycle; no valid topological order exists.")
        task = remaining.pop(ready_index)
        ordered.append(task)
        scheduled.add(task["task_id"])

    stations: list[list[dict[str, Any]]] = []
    current_station: list[dict[str, Any]] = []
    current_load = 0.0
    for task in ordered:
        if current_station and current_load + task["duration"] > cycle + 1e-9:
            stations.append(current_station)
            current_station = []
            current_load = 0.0
        current_station.append(task)
        current_load += task["duration"]
    if current_station:
        stations.append(current_station)

    assignment_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    task_station: dict[str, int] = {}
    for station_number, station_tasks in enumerate(stations, start=1):
        load = sum(task["duration"] for task in station_tasks)
        for order, task in enumerate(station_tasks, start=1):
            task_station[task["task_id"]] = station_number
            assignment_rows.append({
                "Task": task["task_id"],
                "Duration": task["duration"],
                "Predecessors": ", ".join(task["predecessors"]) or "—",
                "Station": station_number,
                "Sequence in station": order,
            })
        summary_rows.append({
            "Station": station_number,
            "Tasks": ", ".join(task["task_id"] for task in station_tasks),
            f"Work content ({unit})": load,
            f"Idle time ({unit})": max(0.0, cycle - load),
            "Station utilization (%)": load / cycle * 100.0,
        })
    # Topological ordering and sequential station packing must never put a task
    # before any of its predecessors; validate the invariant before returning.
    violations = [
        (task["task_id"], pred)
        for task in normalized for pred in task["predecessors"]
        if task_station[pred] > task_station[task["task_id"]]
    ]
    if violations:
        raise RuntimeError("Internal line-balance invariant failed: a predecessor is assigned after its task.")
    total_work = sum(task["duration"] for task in normalized)
    denominator = len(stations) * cycle
    efficiency = total_work / denominator * 100.0 if denominator else 0.0
    return {
        "status": "FEASIBLE_HEURISTIC",
        "method": "Stable topological order plus sequential greedy station packing; not a global optimum proof",
        "cycle_time": cycle,
        "time_unit": unit,
        "task_count": len(normalized),
        "total_work_content": total_work,
        "station_count": len(stations),
        "theoretical_minimum_stations": math.ceil(total_work / cycle),
        "efficiency_pct": efficiency,
        "balance_delay_pct": 100.0 - efficiency,
        "precedence_validated": True,
        "issues": [],
        "station_summary": pd.DataFrame(summary_rows),
        "task_assignment": pd.DataFrame(assignment_rows),
        "warning": "Heuristic assignment only. Review task precedence, physical layout, skill constraints and observed cycle times before use.",
    }


def analyze_bottleneck_capacity(
    processes: Sequence[Mapping[str, Any]],
    demand_units_per_period: float,
    *,
    period_label: str = "period",
) -> dict[str, Any]:
    """Identify the lowest-capacity process and compare it with stated demand."""
    demand = _finite_number(demand_units_per_period, "Demand per period")
    period = str(period_label or "").strip()
    if demand <= 0:
        raise ValueError("Demand per period must be greater than zero.")
    if not period:
        raise ValueError("Period label is required (for example, shift or day).")
    if isinstance(processes, (str, bytes)) or not isinstance(processes, Sequence) or not processes:
        raise ValueError("Provide at least one process capacity object.")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, process in enumerate(processes, start=1):
        if not isinstance(process, Mapping):
            raise ValueError(f"Process row {i} must be an object.")
        name = str(process.get("process", process.get("name", ""))).strip()
        if not name:
            raise ValueError(f"Process row {i} needs a name.")
        if name.casefold() in seen:
            raise ValueError(f"Process names must be unique; duplicate: {name}.")
        seen.add(name.casefold())
        capacity = _finite_number(process.get("capacity"), f"Capacity for {name}")
        if capacity < 0:
            raise ValueError(f"Capacity for {name} cannot be negative.")
        utilization = demand / capacity * 100.0 if capacity > 0 else None
        rows.append({
            "Process": name,
            f"Capacity ({period})": capacity,
            "Demand ({period})": demand,
            "Demand utilization (%)": utilization,
            f"Capacity gap ({period})": capacity - demand,
            "Bottleneck": False,
        })
    bottleneck_index = min(range(len(rows)), key=lambda i: rows[i][f"Capacity ({period})"])
    rows[bottleneck_index]["Bottleneck"] = True
    bottleneck_capacity = rows[bottleneck_index][f"Capacity ({period})"]
    shortfall = max(0.0, demand - bottleneck_capacity)
    status = "CAPACITY_SHORTFALL" if shortfall > 1e-9 else "CAPACITY_MEETS_DEMAND"
    frame = pd.DataFrame(rows).sort_values(
        by=[f"Capacity ({period})", "Process"], kind="stable"
    ).reset_index(drop=True)
    return {
        "status": status,
        "method": "Capacity comparison using user-entered, same-period process capacities",
        "demand_units_per_period": demand,
        "bottleneck_process": rows[bottleneck_index]["Process"],
        "bottleneck_capacity_per_period": bottleneck_capacity,
        "capacity_shortfall_per_period": shortfall,
        "capacity_headroom_per_period": max(0.0, bottleneck_capacity - demand),
        "minimum_recovery_capacity_required": shortfall,
        "process_capacity_table": frame,
        "assumptions": "Capacities and demand refer to the same product mix, time period and unit basis. This is a capacity screen, not causal proof that the lowest-capacity process alone explains observed losses.",
    }


def build_value_stream_map(
    steps: Sequence[Mapping[str, Any]],
    demand_units_per_period: float,
    available_time_per_period: float,
    *,
    time_unit: str = "minutes",
) -> dict[str, Any]:
    """Compute a first-pass VSM lead-time view from cycle, uptime, batch and WIP inputs."""
    demand = _finite_number(demand_units_per_period, "Demand per period")
    available = _finite_number(available_time_per_period, "Available time per period")
    unit = str(time_unit or "").strip()
    if demand <= 0 or not demand.is_integer():
        raise ValueError("Demand per period must be a positive whole number.")
    if available <= 0:
        raise ValueError("Available time per period must be greater than zero.")
    if not unit:
        raise ValueError("Time unit is required.")
    if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence) or not steps:
        raise ValueError("Provide at least one process-step object.")
    flow_rate = demand / available
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, Mapping):
            raise ValueError(f"Step row {i} must be an object.")
        name = str(step.get("step", step.get("name", ""))).strip()
        if not name:
            raise ValueError(f"Step row {i} needs a name.")
        if name.casefold() in seen:
            raise ValueError(f"Process-step names must be unique; duplicate: {name}.")
        seen.add(name.casefold())
        cycle = _finite_number(step.get("cycle_time"), f"Cycle time for {name}")
        changeover = _finite_number(step.get("changeover_time", 0), f"Changeover time for {name}")
        uptime_pct = _finite_number(step.get("uptime_pct", 100), f"Uptime percentage for {name}")
        wip = _finite_number(step.get("wip_units", 0), f"WIP units for {name}")
        batch = _finite_number(step.get("batch_size", 1), f"Batch size for {name}")
        if cycle <= 0:
            raise ValueError(f"Cycle time for {name} must be greater than zero.")
        if changeover < 0 or wip < 0:
            raise ValueError(f"Changeover and WIP cannot be negative for {name}.")
        if not 0 < uptime_pct <= 100:
            raise ValueError(f"Uptime percentage for {name} must be greater than 0 and at most 100.")
        if batch <= 0 or not batch.is_integer():
            raise ValueError(f"Batch size for {name} must be a positive whole number.")
        value_added = bool(step.get("value_added", False))
        queue_time = wip / flow_rate
        effective_cycle = cycle / (uptime_pct / 100.0)
        changeover_per_unit = changeover / batch
        effective_process_time = effective_cycle + changeover_per_unit
        rows.append({
            "Process step": name,
            f"Cycle time ({unit})": cycle,
            f"Changeover time ({unit}/batch)": changeover,
            "Batch size (units)": int(batch),
            "Uptime (%)": uptime_pct,
            "WIP before step (units)": wip,
            f"Queue lead time ({unit})": queue_time,
            f"Availability-adjusted process time ({unit}/unit)": effective_process_time,
            "Value added": value_added,
        })
    frame = pd.DataFrame(rows)
    va_time = sum(
        float(row[f"Cycle time ({unit})"])
        for row in rows if row["Value added"]
    )
    queue_time_total = sum(float(row[f"Queue lead time ({unit})"]) for row in rows)
    adjusted_process_time = sum(float(row[f"Availability-adjusted process time ({unit}/unit)"]) for row in rows)
    lead_time = queue_time_total + adjusted_process_time
    return {
        "status": "CALCULATED_ESTIMATE",
        "method": "First-pass VSM: queue time = WIP / required flow rate; process time adjusts cycle time for stated uptime and adds changeover/batch",
        "time_unit": unit,
        "demand_units_per_period": demand,
        "available_time_per_period": available,
        "required_flow_rate_units_per_time": flow_rate,
        "value_added_time": va_time,
        "total_queue_lead_time": queue_time_total,
        "availability_adjusted_process_time": adjusted_process_time,
        "estimated_total_lead_time": lead_time,
        "value_added_share_pct": (va_time / lead_time * 100.0) if lead_time > 0 else 0.0,
        "process_steps": frame,
        "assumptions": "Steady throughput, same time basis, WIP recorded before each step, no rework/transport delays unless represented in WIP, and user-entered uptime. This is a screening map, not a calibrated discrete-event simulation.",
        "warning": "Validate the process sequence, WIP boundaries, batch convention, uptime period and observed timestamps before operational use.",
    }


def analyze_fmea(failure_modes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Rank user-entered FMEA rows using classic S×O×D RPN plus severity override."""
    if isinstance(failure_modes, (str, bytes)) or not isinstance(failure_modes, Sequence) or not failure_modes:
        raise ValueError("Provide at least one failure-mode object.")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, item in enumerate(failure_modes, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Failure-mode row {i} must be an object.")
        mode = str(item.get("failure_mode", item.get("mode", ""))).strip()
        if not mode:
            raise ValueError(f"Failure-mode row {i} needs a failure_mode description.")
        if mode.casefold() in seen:
            raise ValueError(f"Failure-mode descriptions must be unique; duplicate: {mode}.")
        seen.add(mode.casefold())
        scores: dict[str, int] = {}
        for key in ("severity", "occurrence", "detection"):
            value = _finite_number(item.get(key), f"{key.title()} score for {mode}")
            if not value.is_integer() or not 1 <= value <= 10:
                raise ValueError(f"{key.title()} score for {mode} must be a whole number from 1 through 10.")
            scores[key] = int(value)
        rpn = scores["severity"] * scores["occurrence"] * scores["detection"]
        severe = scores["severity"] >= 9
        # Bands are a configurable convention, not a universal FMEA standard.
        risk_band = "HIGH — review" if severe or rpn >= 200 else "MEDIUM — review" if rpn >= 100 else "LOWER — review"
        rows.append({
            "Failure mode": mode,
            "Effect": str(item.get("effect", "")).strip(),
            "Cause": str(item.get("cause", "")).strip(),
            "Existing controls": str(item.get("existing_controls", "")).strip(),
            "Severity": scores["severity"],
            "Occurrence": scores["occurrence"],
            "Detection": scores["detection"],
            "RPN (S×O×D)": rpn,
            "Severity ≥ 9 review": severe,
            "Review priority band": risk_band,
            "Recommended action": str(item.get("action", "")).strip(),
            "Owner": str(item.get("owner", "")).strip(),
            "Due date": str(item.get("due_date", "")).strip(),
        })
    frame = pd.DataFrame(rows).sort_values(
        by=["Severity ≥ 9 review", "RPN (S×O×D)", "Severity"],
        ascending=[False, False, False], kind="stable",
    ).reset_index(drop=True)
    return {
        "status": "CALCULATED_REQUIRES_ENGINEERING_REVIEW",
        "method": "Classic Risk Priority Number = Severity × Occurrence × Detection; severity ≥ 9 is surfaced separately",
        "failure_mode_count": len(frame),
        "highest_rpn": int(frame["RPN (S×O×D)"].max()),
        "high_severity_count": int(frame["Severity ≥ 9 review"].sum()),
        "failure_modes": frame,
        "assumptions": "Score anchors, risk-band thresholds and detection meaning must be defined by the organization's approved FMEA procedure.",
        "warning": "RPN and score bands are prioritization aids, not objective risk truth. High-severity hazards require review even when RPN is lower; assign actions and approve controls through the site's safety/quality process.",
    }


def analyze_mm1_queue(arrival_rate_per_period: float, service_rate_per_period: float, *, time_unit: str = "hours") -> dict[str, Any]:
    """Analyze a stable M/M/1 queue with exponential arrivals/service and one server."""
    arrival = _finite_number(arrival_rate_per_period, "Arrival rate")
    service = _finite_number(service_rate_per_period, "Service rate")
    unit = str(time_unit or "").strip()
    if arrival < 0:
        raise ValueError("Arrival rate cannot be negative.")
    if service <= 0:
        raise ValueError("Service rate must be greater than zero.")
    if not unit:
        raise ValueError("Time unit for rates is required.")
    utilization = arrival / service
    if utilization >= 1.0:
        raise ValueError("M/M/1 system is unstable: arrival rate must be strictly below service rate.")
    mean_number_system = arrival / (service - arrival)
    mean_number_queue = (arrival * arrival) / (service * (service - arrival)) if arrival else 0.0
    mean_time_system = 1.0 / (service - arrival)
    mean_time_queue = mean_number_queue / arrival if arrival else 0.0
    return {
        "status": "STABLE_M_M_1",
        "model": "M/M/1 steady-state queue",
        "arrival_rate_per_time": arrival,
        "service_rate_per_time": service,
        "utilization_pct": utilization * 100.0,
        "mean_customers_in_system": mean_number_system,
        "mean_customers_waiting": mean_number_queue,
        "mean_time_in_system": mean_time_system,
        "mean_waiting_time_in_queue": mean_time_queue,
        "time_unit": unit,
        "formula": "rho=lambda/mu; L=lambda/(mu-lambda); Lq=lambda^2/(mu*(mu-lambda)); W=1/(mu-lambda); Wq=Lq/lambda for lambda>0",
        "assumptions": "Single server, stationary Poisson arrivals, exponential service times, first-in-first-out, infinite buffer and population, stable utilization below 100%.",
        "warning": "This is an analytical M/M/1 model; validate arrival/service distributions and resource count before applying it to an actual service system.",
    }


def analyze_industrial_cost_variance(
    standard_quantity_per_unit: float,
    actual_output_units: float,
    actual_input_quantity: float,
    standard_unit_cost: float,
    actual_unit_cost: float,
    *,
    currency: str = "SAR",
    period: str = "",
) -> dict[str, Any]:
    """Reconcile material price, usage and total variance against actual output."""
    std_qty_per_unit = _finite_number(standard_quantity_per_unit, "Standard input quantity per output unit")
    output_qty = _finite_number(actual_output_units, "Actual output units")
    actual_qty = _finite_number(actual_input_quantity, "Actual input quantity")
    std_price = _finite_number(standard_unit_cost, "Standard unit cost")
    actual_price = _finite_number(actual_unit_cost, "Actual unit cost")
    curr = str(currency or "").strip().upper()
    period_text = str(period or "").strip()
    if std_qty_per_unit <= 0:
        raise ValueError("Standard input quantity per output unit must be greater than zero.")
    if output_qty <= 0:
        raise ValueError("Actual output units must be greater than zero.")
    if actual_qty < 0 or std_price < 0 or actual_price < 0:
        raise ValueError("Actual input and unit costs cannot be negative.")
    if not curr:
        raise ValueError("Currency code is required.")
    allowed_standard_qty = std_qty_per_unit * output_qty
    standard_cost = allowed_standard_qty * std_price
    actual_cost = actual_qty * actual_price
    price_variance = actual_qty * (actual_price - std_price)
    usage_variance = (actual_qty - allowed_standard_qty) * std_price
    total_variance = actual_cost - standard_cost
    reconciled_variance = price_variance + usage_variance
    if not math.isclose(total_variance, reconciled_variance, rel_tol=1e-9, abs_tol=1e-7):
        raise RuntimeError("Internal cost-variance reconciliation failed.")
    breakdown = pd.DataFrame([
        {"Variance component": "Price variance", f"Amount ({curr})": price_variance, "Interpretation": "Positive is adverse; negative is favorable"},
        {"Variance component": "Usage variance", f"Amount ({curr})": usage_variance, "Interpretation": "Positive is adverse; negative is favorable"},
        {"Variance component": "Total variance", f"Amount ({curr})": total_variance, "Interpretation": "Actual cost minus standard allowed cost for actual output"},
    ])
    return {
        "status": "RECONCILED",
        "currency": curr,
        "period": period_text or "UNSPECIFIED — add the measured period",
        "standard_quantity_allowed": allowed_standard_qty,
        "actual_input_quantity": actual_qty,
        "standard_cost_for_actual_output": standard_cost,
        "actual_input_cost": actual_cost,
        "price_variance": price_variance,
        "usage_variance": usage_variance,
        "total_variance": total_variance,
        "variance_reconciles": True,
        "variance_breakdown": breakdown,
        "formula": "SQ=standard quantity per unit×actual output; price variance=AQ×(AP−SP); usage variance=(AQ−SQ)×SP; total variance=actual cost−standard cost",
        "warning": "This is a scoped direct-material variance. Include labor, overhead, scrap/rework, yield, exchange-rate and accounting-policy effects separately when relevant.",
    }


def calculate_roi_evidence(
    baseline_cost: float,
    post_change_cost: float,
    implementation_cost: float,
    *,
    currency: str = "SAR",
    measurement_window: str = "",
    baseline_evidence: str = "",
    outcome_evidence: str = "",
    verifier: str = "",
) -> dict[str, Any]:
    """Calculate ROI from comparable user-provided costs without self-certifying evidence."""
    baseline = _finite_number(baseline_cost, "Baseline cost")
    post = _finite_number(post_change_cost, "Post-change cost")
    implementation = _finite_number(implementation_cost, "Implementation cost")
    curr = str(currency or "").strip().upper()
    window = str(measurement_window or "").strip()
    baseline_ref = str(baseline_evidence or "").strip()
    outcome_ref = str(outcome_evidence or "").strip()
    reviewer = str(verifier or "").strip()
    if baseline < 0 or post < 0 or implementation < 0:
        raise ValueError("Baseline, post-change and implementation costs cannot be negative.")
    if not curr:
        raise ValueError("Currency code is required.")
    gross = baseline - post
    net = gross - implementation
    roi_pct = net / implementation * 100.0 if implementation > 0 else None
    missing = []
    if not window:
        missing.append("measurement window")
    if not baseline_ref:
        missing.append("baseline evidence reference")
    if not outcome_ref:
        missing.append("post-change evidence reference")
    if not reviewer:
        missing.append("independent verifier")
    return {
        "status": "CALCULATED — HUMAN VERIFICATION REQUIRED",
        "currency": curr,
        "measurement_window": window or "UNSPECIFIED",
        "baseline_cost": baseline,
        "post_change_cost": post,
        "implementation_cost": implementation,
        "gross_cost_reduction": gross,
        "net_benefit_after_implementation": net,
        "roi_pct": roi_pct,
        "break_even_or_better": net >= 0,
        "baseline_evidence_reference": baseline_ref or "NOT PROVIDED",
        "outcome_evidence_reference": outcome_ref or "NOT PROVIDED",
        "verifier": reviewer or "NOT ASSIGNED",
        "verification_status": "REQUIRES_HUMAN_VERIFICATION",
        "missing_verification_items": missing,
        "formula": "Gross cost reduction = baseline cost − post-change cost; net benefit = gross reduction − implementation cost; ROI = net benefit / implementation cost × 100% when implementation cost > 0",
        "warning": "A reference or verifier name does not independently prove an outcome. Do not claim realized/verified savings until a responsible reviewer checks comparability, source evidence, measurement window and confounders.",
    }


def plan_preventive_maintenance(
    tasks: Sequence[Mapping[str, Any]],
    as_of_date: str,
) -> dict[str, Any]:
    """Calculate interval-based due dates and overdue state from explicit task records.

    This is a date/interval planner; it does not solve labor or downtime-window
    scheduling constraints and must not be presented as an optimized schedule.
    """
    from datetime import date, timedelta

    try:
        as_of = date.fromisoformat(str(as_of_date or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("As-of date must be a valid ISO date (YYYY-MM-DD).") from exc
    if isinstance(tasks, (str, bytes)) or not isinstance(tasks, Sequence) or not tasks:
        raise ValueError("Provide at least one maintenance task object.")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, task in enumerate(tasks, start=1):
        if not isinstance(task, Mapping):
            raise ValueError(f"Maintenance row {i} must be an object.")
        asset = str(task.get("asset", "")).strip()
        name = str(task.get("task", task.get("task_name", ""))).strip()
        skill = str(task.get("required_skill", task.get("skill", ""))).strip()
        if not asset or not name:
            raise ValueError(f"Maintenance row {i} needs both asset and task names.")
        key = (asset.casefold(), name.casefold())
        if key in seen:
            raise ValueError(f"Duplicate maintenance task for asset {asset}: {name}.")
        seen.add(key)
        try:
            last_done = date.fromisoformat(str(task.get("last_completed_date", "")).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Last completed date for {asset} / {name} must use YYYY-MM-DD.") from exc
        interval_value = _finite_number(task.get("interval_days"), f"Interval days for {asset} / {name}")
        duration = _finite_number(task.get("estimated_duration_hours", 1), f"Duration hours for {asset} / {name}")
        if not interval_value.is_integer() or interval_value <= 0:
            raise ValueError(f"Interval days for {asset} / {name} must be a positive whole number.")
        if duration <= 0:
            raise ValueError(f"Estimated duration for {asset} / {name} must be greater than zero.")
        interval = int(interval_value)
        due = last_done + timedelta(days=interval)
        days_until_due = (due - as_of).days
        rows.append({
            "Asset": asset,
            "Maintenance task": name,
            "Required skill": skill or "NOT SPECIFIED",
            "Last completed": last_done.isoformat(),
            "Interval (days)": interval,
            "Next due date": due.isoformat(),
            "Days until due": days_until_due,
            "Estimated labor (hours)": duration,
            "Status": "OVERDUE" if days_until_due < 0 else "DUE TODAY" if days_until_due == 0 else "UPCOMING",
            "Assigned owner": str(task.get("owner", "")).strip() or "UNASSIGNED",
        })
    frame = pd.DataFrame(rows).sort_values(
        by=["Days until due", "Asset", "Maintenance task"], kind="stable"
    ).reset_index(drop=True)
    return {
        "status": "PLAN_CALCULATED",
        "as_of_date": as_of.isoformat(),
        "maintenance_task_count": len(frame),
        "overdue_task_count": int((frame["Days until due"] < 0).sum()),
        "due_within_7_days_count": int(((frame["Days until due"] >= 0) & (frame["Days until due"] <= 7)).sum()),
        "total_estimated_labor_hours": float(frame["Estimated labor (hours)"].sum()),
        "maintenance_plan": frame,
        "assumptions": "Next due date = last completed date + interval days. Calendar days are used; no business calendar, asset criticality, skill capacity, parts availability or downtime-window optimization is applied.",
        "warning": "This is an interval-based planning list, not a resource-feasible maintenance schedule. Review equipment manuals, site safety requirements, operating windows and qualified maintenance procedures.",
    }


def assess_job_hazards(hazards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Screen hazards using user-defined 1–5 severity and likelihood scores.

    Residual score is computed only when both residual ratings are supplied.
    The numeric scores are a screening aid, not a certified risk assessment.
    """
    if isinstance(hazards, (str, bytes)) or not isinstance(hazards, Sequence) or not hazards:
        raise ValueError("Provide at least one hazard object.")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, hazard in enumerate(hazards, start=1):
        if not isinstance(hazard, Mapping):
            raise ValueError(f"Hazard row {i} must be an object.")
        name = str(hazard.get("hazard", hazard.get("hazard_description", ""))).strip()
        if not name:
            raise ValueError(f"Hazard row {i} needs a hazard description.")
        if name.casefold() in seen:
            raise ValueError(f"Hazard descriptions must be unique; duplicate: {name}.")
        seen.add(name.casefold())
        def rating(key: str, required: bool) -> int | None:
            raw = hazard.get(key)
            if raw is None or str(raw).strip() == "":
                if required:
                    raise ValueError(f"{key.replace('_', ' ').title()} rating is required for hazard: {name}.")
                return None
            value = _finite_number(raw, f"{key.replace('_', ' ').title()} rating for {name}")
            if not value.is_integer() or not 1 <= value <= 5:
                raise ValueError(f"{key.replace('_', ' ').title()} rating for {name} must be a whole number from 1 through 5.")
            return int(value)
        severity = rating("severity", True)
        likelihood = rating("likelihood", True)
        residual_severity = rating("residual_severity", False)
        residual_likelihood = rating("residual_likelihood", False)
        initial_score = int(severity) * int(likelihood)
        residual_score = (
            residual_severity * residual_likelihood
            if residual_severity is not None and residual_likelihood is not None else None
        )
        controls = str(hazard.get("existing_controls", hazard.get("controls", ""))).strip()
        action = str(hazard.get("required_action", hazard.get("action", ""))).strip()
        owner = str(hazard.get("owner", "")).strip()
        review_date = str(hazard.get("review_date", "")).strip()
        rows.append({
            "Hazard": name,
            "Work/activity": str(hazard.get("activity", "")).strip(),
            "Potential consequence": str(hazard.get("consequence", "")).strip(),
            "Initial severity (1–5)": severity,
            "Initial likelihood (1–5)": likelihood,
            "Initial risk score": initial_score,
            "Existing controls": controls or "NOT DOCUMENTED",
            "Residual severity (1–5)": residual_severity,
            "Residual likelihood (1–5)": residual_likelihood,
            "Residual risk score": residual_score,
            "Additional action": action or "REVIEW REQUIRED",
            "Owner": owner or "UNASSIGNED",
            "Review date": review_date or "NOT SET",
            "Control evidence recorded": bool(controls),
            "Action owner assigned": bool(owner),
        })
    frame = pd.DataFrame(rows).sort_values(
        by=["Initial risk score", "Hazard"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    return {
        "status": "HAZARD_SCREEN_REQUIRES_QUALIFIED_REVIEW",
        "hazard_count": len(frame),
        "high_screen_score_count": int((frame["Initial risk score"] >= 15).sum()),
        "missing_controls_count": int((~frame["Control evidence recorded"]).sum()),
        "unassigned_actions_count": int((~frame["Action owner assigned"]).sum()),
        "hazard_register": frame,
        "method": "Screening score = severity × likelihood, using user-defined 1–5 rating scales",
        "warning": "This is not a certified safety assessment and does not determine legal compliance. A qualified site safety professional must define the approved risk matrix, validate controls and residual ratings, and authorize any work.",
    }


def plan_material_requirements(
    bom: Sequence[Mapping[str, Any]],
    parent_demand_units: float,
    *,
    inventory: Mapping[str, Any] | None = None,
    due_period: int = 0,
) -> dict[str, Any]:
    """Explode a validated one-level BOM and net component requirements.

    This intentionally supports one-level BOM only; recursive assemblies,
    alternate components, scrap/yield factors and pegging are not inferred.
    """
    demand_value = _finite_number(parent_demand_units, "Parent demand")
    if demand_value <= 0 or not demand_value.is_integer():
        raise ValueError("Parent demand must be a positive whole number of assemblies.")
    if isinstance(due_period, bool) or not isinstance(due_period, int):
        raise ValueError("Due period must be a whole number index (0 for the current period).")
    if isinstance(bom, (str, bytes)) or not isinstance(bom, Sequence) or not bom:
        raise ValueError("Provide at least one BOM component object.")
    stock = inventory or {}
    if not isinstance(stock, Mapping):
        raise ValueError("Inventory must be a mapping keyed by component name.")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, component in enumerate(bom, start=1):
        if not isinstance(component, Mapping):
            raise ValueError(f"BOM row {i} must be an object.")
        name = str(component.get("component", component.get("item", ""))).strip()
        if not name:
            raise ValueError(f"BOM row {i} needs a component name.")
        if name.casefold() in seen:
            raise ValueError(f"Duplicate BOM component: {name}.")
        seen.add(name.casefold())
        qty_per = _finite_number(component.get("qty_per_parent"), f"Quantity per parent for {name}")
        if qty_per <= 0:
            raise ValueError(f"Quantity per parent for {name} must be greater than zero.")
        if not qty_per.is_integer():
            raise ValueError(f"Quantity per parent for {name} must be a whole number for this planner.")
        comp_inventory = stock.get(name, {})
        if comp_inventory is None:
            comp_inventory = {}
        if not isinstance(comp_inventory, Mapping):
            raise ValueError(f"Inventory record for {name} must be an object.")
        on_hand = _finite_number(comp_inventory.get("on_hand", 0), f"On-hand inventory for {name}")
        receipts = _finite_number(comp_inventory.get("scheduled_receipts", 0), f"Scheduled receipts for {name}")
        safety = _finite_number(comp_inventory.get("safety_stock", 0), f"Safety stock for {name}")
        lead_value = _finite_number(comp_inventory.get("lead_time_periods", component.get("lead_time_periods", 0)), f"Lead time periods for {name}")
        lot_value = _finite_number(comp_inventory.get("lot_size_multiple", component.get("lot_size_multiple", 1)), f"Lot size multiple for {name}")
        if min(on_hand, receipts, safety) < 0:
            raise ValueError(f"Inventory, scheduled receipts and safety stock cannot be negative for {name}.")
        if not lead_value.is_integer() or lead_value < 0:
            raise ValueError(f"Lead time periods for {name} must be a non-negative whole number.")
        if not lot_value.is_integer() or lot_value <= 0:
            raise ValueError(f"Lot size multiple for {name} must be a positive whole number.")
        gross = demand_value * qty_per
        net = max(0.0, gross + safety - on_hand - receipts)
        multiple = int(lot_value)
        planned = int(math.ceil(net / multiple) * multiple) if net > 0 else 0
        lead = int(lead_value)
        rows.append({
            "Component": name,
            "Quantity per parent": int(qty_per),
            "Parent demand": int(demand_value),
            "Gross requirement": int(gross),
            "On hand": on_hand,
            "Scheduled receipts": receipts,
            "Safety stock": safety,
            "Net requirement": net,
            "Lot size multiple": multiple,
            "Planned order receipt": planned,
            "Lead time (periods)": lead,
            "Due period": due_period,
            "Planned order release period": due_period - lead,
            "Release before current period": due_period - lead < 0,
        })
    frame = pd.DataFrame(rows)
    return {
        "status": "ONE_LEVEL_MRP_CALCULATED",
        "parent_demand_units": int(demand_value),
        "due_period": due_period,
        "component_count": len(frame),
        "total_gross_component_requirement": float(frame["Gross requirement"].sum()),
        "total_planned_order_receipts": float(frame["Planned order receipt"].sum()),
        "components": frame,
        "assumptions": "One-level BOM with integer quantity per parent; available supply = on hand + scheduled receipts; net = max(0, gross + safety stock − available); planned receipt rounds upward to the configured lot multiple.",
        "warning": "One-level planning only. Validate BOM revisions, yield/scrap, scheduled receipt timing, unit-of-measure, lot sizing, order calendars, recursive BOM cycles and component substitutions before operational use.",
    }


def score_project_portfolio(
    criteria: Sequence[Mapping[str, Any]],
    alternatives: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rank alternatives with explicit weights and min-max normalization."""
    if isinstance(criteria, (str, bytes)) or not isinstance(criteria, Sequence) or not criteria:
        raise ValueError("Provide at least one scoring criterion.")
    if isinstance(alternatives, (str, bytes)) or not isinstance(alternatives, Sequence) or len(alternatives) < 2:
        raise ValueError("Provide at least two project alternatives.")
    normalized_criteria: list[dict[str, Any]] = []
    seen_criteria: set[str] = set()
    for i, criterion in enumerate(criteria, start=1):
        if not isinstance(criterion, Mapping):
            raise ValueError(f"Criterion row {i} must be an object.")
        name = str(criterion.get("name", "")).strip()
        if not name:
            raise ValueError(f"Criterion row {i} needs a name.")
        if name.casefold() in seen_criteria:
            raise ValueError(f"Duplicate criterion: {name}.")
        seen_criteria.add(name.casefold())
        weight = _finite_number(criterion.get("weight"), f"Weight for {name}")
        direction = str(criterion.get("direction", "maximize")).strip().lower()
        if weight < 0:
            raise ValueError(f"Weight for {name} cannot be negative.")
        if direction not in {"maximize", "minimize"}:
            raise ValueError(f"Direction for {name} must be 'maximize' or 'minimize'.")
        normalized_criteria.append({"name": name, "weight": weight, "direction": direction})
    total_weight = sum(c["weight"] for c in normalized_criteria)
    if total_weight <= 0:
        raise ValueError("At least one criterion weight must be greater than zero.")
    normalized_alternatives: list[dict[str, Any]] = []
    seen_alternatives: set[str] = set()
    for i, alternative in enumerate(alternatives, start=1):
        if not isinstance(alternative, Mapping):
            raise ValueError(f"Alternative row {i} must be an object.")
        name = str(alternative.get("name", alternative.get("project", ""))).strip()
        scores = alternative.get("scores")
        if not name or not isinstance(scores, Mapping):
            raise ValueError(f"Alternative row {i} needs a name and scores object.")
        if name.casefold() in seen_alternatives:
            raise ValueError(f"Duplicate project alternative: {name}.")
        seen_alternatives.add(name.casefold())
        values = {}
        for criterion in normalized_criteria:
            key = criterion["name"]
            if key not in scores:
                raise ValueError(f"Project {name} is missing a score for criterion {key}.")
            values[key] = _finite_number(scores[key], f"Score for {name} / {key}")
        normalized_alternatives.append({"name": name, "scores": values})
    ranges: dict[str, tuple[float, float]] = {}
    for criterion in normalized_criteria:
        vals = [a["scores"][criterion["name"]] for a in normalized_alternatives]
        ranges[criterion["name"]] = (min(vals), max(vals))
    rows: list[dict[str, Any]] = []
    for alternative in normalized_alternatives:
        row: dict[str, Any] = {"Project": alternative["name"]}
        weighted_total = 0.0
        for criterion in normalized_criteria:
            key = criterion["name"]
            low, high = ranges[key]
            value = alternative["scores"][key]
            if math.isclose(low, high, rel_tol=1e-12, abs_tol=1e-12):
                normalized_score = 100.0
            elif criterion["direction"] == "maximize":
                normalized_score = (value - low) / (high - low) * 100.0
            else:
                normalized_score = (high - value) / (high - low) * 100.0
            row[f"{key} score (0–100)"] = normalized_score
            row[f"{key} weight"] = criterion["weight"]
            weighted_total += normalized_score * criterion["weight"]
        row["Weighted score (0–100)"] = weighted_total / total_weight
        rows.append(row)
    frame = pd.DataFrame(rows).sort_values(
        by=["Weighted score (0–100)", "Project"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    frame.insert(0, "Rank", range(1, len(frame) + 1))
    return {
        "status": "SCORED — WEIGHTS ARE USER-DEFINED",
        "method": "Criterion-level min-max normalization to 0–100, direction-aware, weighted average by user-supplied criterion weights",
        "project_count": len(frame),
        "criteria_count": len(normalized_criteria),
        "total_weight": total_weight,
        "ranking": frame,
        "criteria": pd.DataFrame(normalized_criteria),
        "assumptions": "All project scores must be numeric and comparable within each criterion. Weights are subjective inputs. A criterion with identical scores across projects receives 100 for all projects and contributes no discrimination.",
        "warning": "This is a decision aid, not an objective or universally correct ranking. Sensitivity to weights has not been calculated in this first implementation; review weights and data quality before selecting a project.",
    }


def merge_data_tables(
    left_records: Sequence[Mapping[str, Any]],
    right_records: Sequence[Mapping[str, Any]],
    left_key: str,
    right_key: str,
    *,
    join_type: str = "left",
    duplicate_policy: str = "allow",
    max_output_rows: int = 100_000,
) -> dict[str, Any]:
    """Join two supplied tables and report cardinality and unmatched records."""
    if isinstance(left_records, (str, bytes)) or not isinstance(left_records, Sequence) or not left_records:
        raise ValueError("Left table must contain at least one record.")
    if isinstance(right_records, (str, bytes)) or not isinstance(right_records, Sequence) or not right_records:
        raise ValueError("Right table must contain at least one record.")
    if not left_key or not right_key:
        raise ValueError("Choose a join key for each table.")
    join_how = str(join_type or "").strip().lower()
    if join_how not in {"left", "right", "inner", "outer"}:
        raise ValueError("Join type must be left, right, inner or outer.")
    duplicate_mode = str(duplicate_policy or "").strip().lower()
    if duplicate_mode not in {"allow", "reject"}:
        raise ValueError("Duplicate-key policy must be allow or reject.")
    if isinstance(max_output_rows, bool) or not isinstance(max_output_rows, int) or max_output_rows < 1:
        raise ValueError("Maximum output rows must be a positive integer.")
    left = pd.DataFrame(list(left_records))
    right = pd.DataFrame(list(right_records))
    if left.empty or right.empty:
        raise ValueError("Both tables must contain records.")
    for label, df, key in (("Left", left, left_key), ("Right", right, right_key)):
        if key not in df.columns:
            raise ValueError(f"{label} table is missing join key '{key}'.")
        if df[key].isna().any():
            raise ValueError(f"{label} join key '{key}' contains missing values; clean or map them explicitly.")
    left_dups = int(left[left_key].duplicated(keep=False).sum())
    right_dups = int(right[right_key].duplicated(keep=False).sum())
    if duplicate_mode == "reject" and (left_dups or right_dups):
        raise ValueError(
            f"Duplicate join keys are not allowed under the selected policy (left duplicate rows={left_dups}, right duplicate rows={right_dups})."
        )
    try:
        merged = left.merge(
            right, how=join_how, left_on=left_key, right_on=right_key,
            suffixes=("_left", "_right"), indicator=True, sort=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Tables could not be joined safely: {exc}") from exc
    if len(merged) > max_output_rows:
        raise ValueError(
            f"Join would create {len(merged):,} rows, exceeding the configured output limit of {max_output_rows:,}. "
            "Inspect duplicate keys or choose a more selective join."
        )
    indicator_counts = merged["_merge"].value_counts()
    matched = int(indicator_counts.get("both", 0))
    left_only = int(indicator_counts.get("left_only", 0))
    right_only = int(indicator_counts.get("right_only", 0))
    merged = merged.drop(columns=["_merge"])
    return {
        "status": "JOIN_COMPLETED",
        "join_type": join_how,
        "left_input_rows": int(len(left)),
        "right_input_rows": int(len(right)),
        "output_rows": int(len(merged)),
        "matched_output_rows": matched,
        "left_only_output_rows": left_only,
        "right_only_output_rows": right_only,
        "left_duplicate_key_rows": left_dups,
        "right_duplicate_key_rows": right_dups,
        "duplicate_policy": duplicate_mode,
        "joined_table": merged,
        "assumptions": "Duplicate keys are either explicitly allowed (which can multiply rows) or rejected. Key values are compared as supplied; normalize types/case/whitespace before merging when appropriate.",
        "warning": "Review duplicate-key diagnostics and output row-count changes. A many-to-many join can multiply records; the joined table is not proof of correct business-key mapping.",
    }


def process_time_series(
    records: Sequence[Mapping[str, Any]],
    timestamp_column: str,
    *,
    timezone_name: str = "UTC",
    expected_interval: str = "",
    resample_frequency: str = "",
    aggregation: str = "mean",
) -> dict[str, Any]:
    """Normalize timestamped records, report duplicate/gap diagnostics and optionally resample."""
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence) or not records:
        raise ValueError("Provide at least one timestamped record.")
    timestamp_key = str(timestamp_column or "").strip()
    tz_name = str(timezone_name or "").strip()
    if not timestamp_key or not tz_name:
        raise ValueError("Timestamp-column name and timezone are required.")
    df = pd.DataFrame(list(records))
    if timestamp_key not in df.columns:
        raise ValueError(f"Timestamp column '{timestamp_key}' was not found.")
    if df[timestamp_key].isna().any():
        raise ValueError("Timestamp column contains missing values; resolve them explicitly before processing.")
    try:
        parsed = pd.to_datetime(df[timestamp_key], errors="raise")
        if isinstance(parsed.dtype, pd.DatetimeTZDtype):
            localized = parsed.dt.tz_convert("UTC")
        elif pd.api.types.is_datetime64_dtype(parsed.dtype):
            localized = parsed.dt.tz_localize(tz_name, ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC")
        else:
            # Mixed offsets/strings are normalized via UTC parse rather than silently dropped.
            localized = pd.to_datetime(df[timestamp_key], errors="raise", utc=True)
    except Exception as exc:
        raise ValueError(f"Timestamps could not be parsed/localized safely: {exc}") from exc
    df[timestamp_key] = localized
    df = df.sort_values(timestamp_key, kind="stable").reset_index(drop=True)
    duplicate_count = int(df[timestamp_key].duplicated(keep=False).sum())
    gap_rows: list[dict[str, Any]] = []
    interval = None
    if str(expected_interval or "").strip():
        try:
            interval = pd.to_timedelta(str(expected_interval).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Expected interval must be a valid duration such as '15min' or '1h'.") from exc
        if pd.isna(interval) or interval <= pd.Timedelta(0):
            raise ValueError("Expected interval must be greater than zero.")
        unique_stamps = df[timestamp_key].drop_duplicates().sort_values().reset_index(drop=True)
        for i in range(1, len(unique_stamps)):
            delta = unique_stamps.iloc[i] - unique_stamps.iloc[i - 1]
            if delta > interval:
                missing_n = max(0, int(delta // interval) - 1)
                if missing_n > 0:
                    gap_rows.append({
                        "Previous timestamp (UTC)": unique_stamps.iloc[i - 1],
                        "Next timestamp (UTC)": unique_stamps.iloc[i],
                        "Observed gap": str(delta),
                        "Expected interval": str(interval),
                        "Expected missing observations": missing_n,
                    })
    output = df.copy()
    agg = str(aggregation or "").strip().lower()
    resample = str(resample_frequency or "").strip()
    if resample:
        allowed = {"mean", "sum", "min", "max", "first", "last"}
        if agg not in allowed:
            raise ValueError(f"Aggregation must be one of: {', '.join(sorted(allowed))}.")
        try:
            indexed = df.set_index(timestamp_key)
            numeric_cols = list(indexed.select_dtypes(include="number").columns)
            if not numeric_cols:
                raise ValueError("Resampling requires at least one numeric measurement column.")
            output = getattr(indexed[numeric_cols].resample(resample), agg)().reset_index()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Resampling failed: {exc}") from exc
    return {
        "status": "TIME_SERIES_PROCESSED",
        "input_rows": int(len(df)),
        "output_rows": int(len(output)),
        "duplicate_timestamp_rows": duplicate_count,
        "gap_count": len(gap_rows),
        "expected_missing_observations": sum(int(g["Expected missing observations"]) for g in gap_rows),
        "timezone_storage": "UTC",
        "input_timezone_assumption": tz_name,
        "resampled": bool(resample),
        "aggregation": agg if resample else "not applied",
        "gap_diagnostics": pd.DataFrame(gap_rows),
        "processed_series": output,
        "assumptions": "Naive timestamps are interpreted in the supplied timezone and normalized to UTC. Missing, invalid or ambiguous timestamps fail rather than being silently dropped. Only numeric columns are resampled.",
        "warning": "Check daylight-saving changes, source timestamp semantics and aggregation meaning before operational use. A gap report is not proof of a sensor outage.",
    }


def generate_synthetic_industrial_data(
    row_count: int = 100,
    *,
    seed: int = 42,
    start_timestamp: str = "2026-01-01T00:00:00Z",
    interval_minutes: int = 60,
    defect_rate_pct: float = 2.0,
    mean_downtime_minutes: float = 5.0,
    energy_kwh_per_unit: float = 0.5,
) -> dict[str, Any]:
    """Generate reproducible teaching/test data that remains explicitly SYNTHETIC."""
    if isinstance(row_count, bool) or not isinstance(row_count, int) or not 1 <= row_count <= 100_000:
        raise ValueError("Row count must be a whole number from 1 through 100000.")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("Random seed must be a non-negative whole number.")
    if isinstance(interval_minutes, bool) or not isinstance(interval_minutes, int) or interval_minutes <= 0:
        raise ValueError("Timestamp interval must be a positive whole number of minutes.")
    defect_rate = _finite_number(defect_rate_pct, "Defect rate percentage")
    downtime_mean = _finite_number(mean_downtime_minutes, "Mean downtime minutes")
    energy_factor = _finite_number(energy_kwh_per_unit, "Energy per unit")
    if not 0 <= defect_rate <= 100:
        raise ValueError("Defect rate percentage must be between 0 and 100.")
    if downtime_mean < 0 or energy_factor < 0:
        raise ValueError("Downtime and energy factor cannot be negative.")
    try:
        start = pd.Timestamp(start_timestamp)
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        else:
            start = start.tz_convert("UTC")
    except Exception as exc:
        raise ValueError("Start timestamp must be parseable ISO date/time text.") from exc
    rng = np.random.default_rng(seed)
    output_count = rng.poisson(lam=100.0, size=row_count)
    defect_count = rng.binomial(n=output_count, p=defect_rate / 100.0)
    downtime = rng.exponential(scale=max(downtime_mean, 1e-9), size=row_count) if downtime_mean > 0 else np.zeros(row_count)
    energy = output_count * energy_factor * rng.normal(loc=1.0, scale=0.05, size=row_count)
    energy = np.maximum(0.0, energy)
    df = pd.DataFrame({
        "timestamp_utc": [start + pd.Timedelta(minutes=interval_minutes * i) for i in range(row_count)],
        "total_output_units": output_count.astype(int),
        "defective_units": defect_count.astype(int),
        "downtime_minutes": downtime,
        "energy_kwh": energy,
        "data_provenance": "SYNTHETIC",
        "random_seed": seed,
    })
    return {
        "status": "SYNTHETIC_DATA_GENERATED",
        "data_provenance": "SYNTHETIC",
        "row_count": row_count,
        "seed": seed,
        "start_timestamp_utc": start.isoformat(),
        "interval_minutes": interval_minutes,
        "actual_synthetic_defect_rate_pct": (
            float(defect_count.sum() / output_count.sum() * 100.0) if output_count.sum() > 0 else None
        ),
        "synthetic_dataset": df,
        "warning": "Every row is simulated, not a real plant measurement. Do not combine with live data without retaining the SYNTHETIC provenance label.",
    }


def plan_acceptance_sampling(
    aql_rate: float,
    ltpd_rate: float,
    producer_risk: float = 0.05,
    consumer_risk: float = 0.10,
    *,
    max_sample_size: int = 500,
) -> dict[str, Any]:
    """Search a single-sample binomial attributes plan meeting producer/consumer risks."""
    aql = _finite_number(aql_rate, "AQL defect fraction")
    ltpd = _finite_number(ltpd_rate, "LTPD defect fraction")
    alpha = _finite_number(producer_risk, "Producer risk")
    beta = _finite_number(consumer_risk, "Consumer risk")
    if not 0 <= aql < ltpd <= 1:
        raise ValueError("Require 0 ≤ AQL defect fraction < LTPD defect fraction ≤ 1.")
    if not 0 < alpha < 1 or not 0 < beta < 1:
        raise ValueError("Producer and consumer risks must each be strictly between 0 and 1.")
    if isinstance(max_sample_size, bool) or not isinstance(max_sample_size, int) or not 1 <= max_sample_size <= 5000:
        raise ValueError("Maximum sample size must be a whole number from 1 through 5000.")
    from scipy.stats import binom

    found = None
    for n in range(1, max_sample_size + 1):
        for c in range(0, n + 1):
            p_accept_aql = float(binom.cdf(c, n, aql))
            p_accept_ltpd = float(binom.cdf(c, n, ltpd))
            if p_accept_aql >= 1 - alpha and p_accept_ltpd <= beta:
                found = (n, c, p_accept_aql, p_accept_ltpd)
                break
        if found:
            break
    if found is None:
        return {
            "status": "NO_PLAN_WITHIN_SEARCH_LIMIT",
            "aql_rate": aql,
            "ltpd_rate": ltpd,
            "producer_risk_target": alpha,
            "consumer_risk_target": beta,
            "max_sample_size": max_sample_size,
            "sample_size": None,
            "acceptance_number": None,
            "warning": "No binomial single-sample plan was found under the supplied risk targets and search limit. Increase the limit or review the target risks; do not use a partial plan.",
        }
    n, c, p_aql, p_ltpd = found
    return {
        "status": "PLAN_FOUND",
        "method": "Single-sample attributes plan using binomial acceptance probabilities",
        "aql_rate": aql,
        "ltpd_rate": ltpd,
        "producer_risk_target": alpha,
        "consumer_risk_target": beta,
        "sample_size": n,
        "acceptance_number": c,
        "reject_if_defectives_at_least": c + 1,
        "probability_of_acceptance_at_aql": p_aql,
        "actual_producer_risk_at_aql": 1.0 - p_aql,
        "probability_of_acceptance_at_ltpd": p_ltpd,
        "actual_consumer_risk_at_ltpd": p_ltpd,
        "max_sample_size": max_sample_size,
        "formula": "Pa(p)=P(X≤c), X~Binomial(n,p); require Pa(AQL)≥1−producer risk and Pa(LTPD)≤consumer risk",
        "assumptions": "Independent inspected units, constant defect probability and binomial approximation; finite-lot hypergeometric sampling, switching rules and multiple sampling are not included.",
        "warning": "Validate the applicable contractual/standard sampling scheme and finite-lot conditions. This first-pass planner is not a standards certification.",
    }


def analyze_process_mining(event_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize event-log variants, directly-follow relations and case durations."""
    if isinstance(event_records, (str, bytes)) or not isinstance(event_records, Sequence) or not event_records:
        raise ValueError("Provide at least one event-log record.")
    df = pd.DataFrame(list(event_records))
    required = {"case_id", "activity", "timestamp"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Event log is missing required columns: {', '.join(missing)}.")
    for key in ("case_id", "activity"):
        if df[key].isna().any() or df[key].astype(str).str.strip().eq("").any():
            raise ValueError(f"Event log column '{key}' contains missing/blank values.")
        df[key] = df[key].astype(str).str.strip()
    if df["timestamp"].isna().any():
        raise ValueError("Event log timestamp contains missing values.")
    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise", utc=True)
    except Exception as exc:
        raise ValueError(f"Event log timestamps could not be parsed: {exc}") from exc
    df = df.sort_values(["case_id", "timestamp"], kind="stable").reset_index(drop=True)
    variants: list[dict[str, Any]] = []
    transitions: dict[tuple[str, str], dict[str, Any]] = {}
    durations: list[dict[str, Any]] = []
    variant_counts: dict[tuple[str, ...], int] = {}
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    for case_id, case_df in df.groupby("case_id", sort=False):
        activities = list(case_df["activity"])
        variant = tuple(activities)
        variant_counts[variant] = variant_counts.get(variant, 0) + 1
        starts[activities[0]] = starts.get(activities[0], 0) + 1
        ends[activities[-1]] = ends.get(activities[-1], 0) + 1
        durations.append({
            "Case ID": case_id,
            "Event count": len(case_df),
            "Start activity": activities[0],
            "End activity": activities[-1],
            "Duration (seconds)": float((case_df["timestamp"].iloc[-1] - case_df["timestamp"].iloc[0]).total_seconds()),
        })
        for source, target in zip(activities, activities[1:]):
            item = transitions.setdefault((source, target), {"Transition": f"{source} → {target}", "From activity": source, "To activity": target, "Occurrences": 0, "Cases": set()})
            item["Occurrences"] += 1
            item["Cases"].add(str(case_id))
    for variant, count in variant_counts.items():
        variants.append({"Variant": " → ".join(variant), "Cases": count, "Events per case": len(variant)})
    transition_rows = [
        {**{k: v for k, v in value.items() if k != "Cases"}, "Distinct cases": len(value["Cases"])}
        for value in transitions.values()
    ]
    duration_frame = pd.DataFrame(durations).sort_values("Case ID", kind="stable").reset_index(drop=True)
    return {
        "status": "EVENT_LOG_ANALYZED",
        "event_count": int(len(df)),
        "case_count": int(df["case_id"].nunique()),
        "activity_count": int(df["activity"].nunique()),
        "variant_count": len(variant_counts),
        "median_case_duration_seconds": float(duration_frame["Duration (seconds)"].median()),
        "start_activities": pd.DataFrame([{"Activity": k, "Cases": v} for k, v in sorted(starts.items())]),
        "end_activities": pd.DataFrame([{"Activity": k, "Cases": v} for k, v in sorted(ends.items())]),
        "variants": pd.DataFrame(variants).sort_values(["Cases", "Variant"], ascending=[False, True], kind="stable").reset_index(drop=True),
        "directly_follows": pd.DataFrame(transition_rows).sort_values(["Occurrences", "Transition"], ascending=[False, True], kind="stable").reset_index(drop=True) if transition_rows else pd.DataFrame(columns=["Transition", "From activity", "To activity", "Occurrences", "Distinct cases"]),
        "case_durations": duration_frame,
        "warning": "This is an event-log summary, not full conformance checking or causal analysis. Validate event completeness, lifecycle semantics, timestamp timezone and the case identifier.",
    }


def analyze_water_waste_efficiency(process_flows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reconcile process input, product output and waste quantities on a common unit basis."""
    if isinstance(process_flows, (str, bytes)) or not isinstance(process_flows, Sequence) or not process_flows:
        raise ValueError("Provide at least one process flow object.")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, item in enumerate(process_flows, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Flow row {i} must be an object.")
        process = str(item.get("process", "")).strip()
        unit = str(item.get("unit", "")).strip()
        period = str(item.get("period", "")).strip()
        if not process or not unit:
            raise ValueError(f"Flow row {i} needs process and unit labels.")
        if process.casefold() in seen:
            raise ValueError(f"Process names must be unique for this analysis; duplicate: {process}.")
        seen.add(process.casefold())
        input_qty = _finite_number(item.get("input_quantity"), f"Input quantity for {process}")
        output_qty = _finite_number(item.get("product_output_quantity"), f"Product output quantity for {process}")
        waste_qty = _finite_number(item.get("waste_quantity"), f"Waste quantity for {process}")
        if min(input_qty, output_qty, waste_qty) < 0:
            raise ValueError(f"Flow quantities cannot be negative for {process}.")
        if input_qty <= 0:
            raise ValueError(f"Input quantity must be greater than zero for {process}.")
        balance = input_qty - output_qty - waste_qty
        rows.append({
            "Process": process,
            "Period": period or "UNSPECIFIED",
            "Unit": unit,
            "Input quantity": input_qty,
            "Product output quantity": output_qty,
            "Waste quantity": waste_qty,
            "Unreconciled balance": balance,
            "Output yield (%)": output_qty / input_qty * 100.0,
            "Waste intensity (%)": waste_qty / input_qty * 100.0,
            "Balance closes": math.isclose(balance, 0.0, rel_tol=1e-9, abs_tol=1e-7),
        })
    units = {row["Unit"] for row in rows}
    periods = {row["Period"] for row in rows}
    if len(units) != 1:
        raise ValueError("All process quantities must use the same unit; convert units before combining results.")
    frame = pd.DataFrame(rows)
    common_period = len(periods) == 1
    if common_period:
        total_in = float(frame["Input quantity"].sum())
        total_out = float(frame["Product output quantity"].sum())
        total_waste = float(frame["Waste quantity"].sum())
        total_balance = total_in - total_out - total_waste
        overall_yield = total_out / total_in * 100.0 if total_in > 0 else 0.0
        overall_waste_intensity = total_waste / total_in * 100.0 if total_in > 0 else 0.0
    else:
        # Cross-period totals/rates are not comparable without a common time basis.
        total_in = total_out = total_waste = total_balance = None
        overall_yield = overall_waste_intensity = None
    return {
        "status": "FLOW_BALANCE_CALCULATED" if common_period else "FLOW_BALANCE_CALCULATED_PER_PROCESS_ONLY",
        "process_count": len(frame),
        "measurement_period": next(iter(periods)) if common_period else "MIXED — only per-process results are aggregated",
        "unit": next(iter(units)),
        "total_input_quantity": total_in,
        "total_product_output_quantity": total_out,
        "total_waste_quantity": total_waste,
        "total_unreconciled_balance": total_balance,
        "overall_output_yield_pct": overall_yield,
        "overall_waste_intensity_pct": overall_waste_intensity,
        "all_process_balances_close": bool(frame["Balance closes"].all()),
        "process_balance_table": frame,
        "warning": "This is a scoped material/water flow balance. Confirm identical measurement boundaries, density/concentration basis where relevant, measurement periods and loss streams; cross-period totals are omitted when measurement periods differ. A non-zero balance needs investigation, not automatic allocation.",
    }


def analyze_weibull_reliability(failure_times: Sequence[float]) -> dict[str, Any]:
    """Fit a two-parameter Weibull model to uncensored positive failure times."""
    if isinstance(failure_times, (str, bytes)) or not isinstance(failure_times, Sequence) or len(failure_times) < 5:
        raise ValueError("Provide at least five uncensored failure-time observations.")
    values = [_finite_number(v, f"Failure time observation {i}") for i, v in enumerate(failure_times, start=1)]
    if any(v <= 0 for v in values):
        raise ValueError("Failure times must be strictly greater than zero.")
    if len(set(values)) < 3:
        raise ValueError("At least three distinct failure times are required for a meaningful fit.")
    from scipy.stats import weibull_min
    data = np.asarray(values, dtype=float)
    try:
        shape, location, scale = weibull_min.fit(data, floc=0)
    except Exception as exc:
        raise ValueError(f"Weibull fit did not converge: {exc}") from exc
    if not math.isfinite(shape) or not math.isfinite(scale) or shape <= 0 or scale <= 0:
        raise ValueError("Weibull fit returned invalid shape or scale parameters.")
    log_likelihood = float(np.sum(weibull_min.logpdf(data, shape, loc=0, scale=scale)))
    parameter_count = 2
    aic = 2 * parameter_count - 2 * log_likelihood
    b10 = float(scale * (-math.log(0.90)) ** (1.0 / shape))
    b50 = float(scale * (-math.log(0.50)) ** (1.0 / shape))
    mean_ttf = float(scale * math.gamma(1.0 + 1.0 / shape))
    percentiles = sorted(set([0.10, 0.25, 0.50, 0.75, 0.90]))
    curve = pd.DataFrame([
        {
            "Failure probability (%)": probability * 100.0,
            "Time at percentile": float(scale * (-math.log(1.0 - probability)) ** (1.0 / shape)),
            "Reliability (%)": (1.0 - probability) * 100.0,
        }
        for probability in percentiles
    ])
    return {
        "status": "WEIBULL_FIT_UNCENSORED_DATA",
        "method": "Two-parameter Weibull maximum-likelihood fit with location fixed at zero",
        "sample_size": int(len(data)),
        "shape_beta": float(shape),
        "scale_eta": float(scale),
        "location": 0.0,
        "mean_time_to_failure": mean_ttf,
        "B10_life": b10,
        "B50_median_life": b50,
        "log_likelihood": log_likelihood,
        "AIC": float(aic),
        "minimum_observed_time": float(np.min(data)),
        "maximum_observed_time": float(np.max(data)),
        "reliability_percentiles": curve,
        "assumptions": "Positive independent uncensored failure times, two-parameter Weibull distribution, fixed zero location, consistent unit of time.",
        "warning": "Right-censored/interval-censored data and confidence intervals are not handled in this first implementation. The fit is not a maintenance guarantee; inspect sample quality, failure mode consistency and fit adequacy with a reliability engineer.",
    }


def analyze_spare_parts_criticality(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Prioritize spare parts from demand, lead time, safety stock, criticality and on-hand supply."""
    if isinstance(parts, (str, bytes)) or not isinstance(parts, Sequence) or not parts:
        raise ValueError("Provide at least one spare-part record.")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, part in enumerate(parts, start=1):
        if not isinstance(part, Mapping):
            raise ValueError(f"Spare-part row {i} must be an object.")
        name = str(part.get("part", part.get("sku", ""))).strip()
        if not name:
            raise ValueError(f"Spare-part row {i} needs a part/SKU name.")
        if name.casefold() in seen:
            raise ValueError(f"Duplicate spare-part name: {name}.")
        seen.add(name.casefold())
        demand = _finite_number(part.get("average_daily_demand", 0), f"Daily demand for {name}")
        lead = _finite_number(part.get("lead_time_days"), f"Lead time for {name}")
        safety = _finite_number(part.get("safety_stock", 0), f"Safety stock for {name}")
        on_hand = _finite_number(part.get("on_hand", 0), f"On-hand stock for {name}")
        receipts = _finite_number(part.get("scheduled_receipts", 0), f"Scheduled receipts for {name}")
        cost = _finite_number(part.get("unit_cost", 0), f"Unit cost for {name}")
        criticality = _finite_number(part.get("criticality_score"), f"Criticality score for {name}")
        if demand < 0 or lead < 0 or min(safety, on_hand, receipts, cost) < 0:
            raise ValueError(f"Demand, lead time, inventory and cost values cannot be negative for {name}.")
        if not criticality.is_integer() or not 1 <= criticality <= 5:
            raise ValueError(f"Criticality score for {name} must be a whole number from 1 through 5.")
        reorder_point = demand * lead + safety
        stock_position = on_hand + receipts
        order_qty = max(0.0, reorder_point - stock_position)
        coverage_days = stock_position / demand if demand > 0 else None
        lead_gap_days = max(0.0, lead - coverage_days) if coverage_days is not None else (lead if reorder_point > stock_position else 0.0)
        shortage = order_qty > 1e-9
        rows.append({
            "Part": name,
            "Criticality (1–5)": int(criticality),
            "Average daily demand": demand,
            "Lead time (days)": lead,
            "Safety stock": safety,
            "On-hand": on_hand,
            "Scheduled receipts": receipts,
            "Stock position": stock_position,
            "Reorder point": reorder_point,
            "Suggested replenishment quantity": order_qty,
            "Stock coverage (days)": coverage_days,
            "Lead-time coverage gap (days)": lead_gap_days,
            "Unit cost": cost,
            "Replenishment value": order_qty * cost,
            "Below reorder point": shortage,
        })
    frame = pd.DataFrame(rows).sort_values(
        by=["Below reorder point", "Criticality (1–5)", "Lead-time coverage gap (days)", "Part"],
        ascending=[False, False, False, True], kind="stable",
    ).reset_index(drop=True)
    return {
        "status": "SPARE_PARTS_SCREEN_CALCULATED",
        "part_count": len(frame),
        "parts_below_reorder_point": int(frame["Below reorder point"].sum()),
        "estimated_replenishment_value": float(frame["Replenishment value"].sum()),
        "priority_table": frame,
        "method": "Reorder point = average daily demand × lead time days + safety stock; stock position = on-hand + scheduled receipts",
        "warning": "Demand and lead time are assumed stable and expressed in compatible units. This screening model does not optimize multi-echelon inventory, supplier risk, shelf life, service levels or purchase-order constraints.",
    }


def analyze_safety_incident_trends(periods: Sequence[Mapping[str, Any]], *, rate_base_hours: float = 200_000.0) -> dict[str, Any]:
    """Compute period-level incident and lost-workday rates with category breakdowns."""
    if isinstance(periods, (str, bytes)) or not isinstance(periods, Sequence) or not periods:
        raise ValueError("Provide at least one period-level safety record.")
    base_hours = _finite_number(rate_base_hours, "Incident rate base hours")
    if base_hours <= 0:
        raise ValueError("Rate base hours must be greater than zero.")
    period_rows: list[dict[str, Any]] = []
    category_rows: list[dict[str, Any]] = []
    seen_periods: set[str] = set()
    for i, record in enumerate(periods, start=1):
        if not isinstance(record, Mapping):
            raise ValueError(f"Safety period row {i} must be an object.")
        period = str(record.get("period", "")).strip()
        categories = record.get("incidents_by_category")
        hours = _finite_number(record.get("work_hours"), f"Work hours for period {period or i}")
        lost_days = _finite_number(record.get("lost_workdays", 0), f"Lost workdays for period {period or i}")
        if not period:
            raise ValueError(f"Safety period row {i} needs a period label.")
        if period in seen_periods:
            raise ValueError(f"Duplicate safety reporting period: {period}.")
        seen_periods.add(period)
        if hours <= 0:
            raise ValueError(f"Work hours must be greater than zero for period {period}.")
        if lost_days < 0:
            raise ValueError(f"Lost workdays cannot be negative for period {period}.")
        if not isinstance(categories, Mapping) or not categories:
            raise ValueError(f"Period {period} needs an incidents_by_category object.")
        count_total = 0
        for category, raw_count in categories.items():
            label = str(category).strip()
            if not label:
                raise ValueError(f"Incident category names cannot be blank in period {period}.")
            count_value = _finite_number(raw_count, f"Incident count for {label} / {period}")
            if not count_value.is_integer() or count_value < 0:
                raise ValueError(f"Incident count for {label} / {period} must be a non-negative whole number.")
            count = int(count_value)
            count_total += count
            category_rows.append({"Period": period, "Category": label, "Incidents": count, "Work hours": hours})
        period_rows.append({
            "Period": period,
            "Total incidents": count_total,
            "Work hours": hours,
            "Lost workdays": lost_days,
            "Incident rate per base hours": count_total / hours * base_hours,
            "Lost-workday rate per base hours": lost_days / hours * base_hours,
        })
    trend = pd.DataFrame(period_rows)
    category = pd.DataFrame(category_rows)
    return {
        "status": "SAFETY_TREND_CALCULATED",
        "period_count": len(trend),
        "total_incidents": int(trend["Total incidents"].sum()),
        "total_lost_workdays": float(trend["Lost workdays"].sum()),
        "rate_base_hours": base_hours,
        "period_trend": trend,
        "category_breakdown": category,
        "warning": "Rates depend on accurate comparable work-hour denominators and reporting coverage. Trends and category counts do not prove causation or replace incident investigation and required reporting.",
    }


def optimize_warehouse_slotting(
    items: Sequence[Mapping[str, Any]],
    slots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Greedy slotting heuristic: high-pick SKUs receive nearest compatible slots that fit."""
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence) or not items:
        raise ValueError("Provide at least one SKU/item.")
    if isinstance(slots, (str, bytes)) or not isinstance(slots, Sequence) or not slots:
        raise ValueError("Provide at least one warehouse slot.")
    normalized_items: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    for i, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Item row {i} must be an object.")
        sku = str(item.get("sku", "")).strip()
        group = str(item.get("compatibility_group", "*")).strip() or "*"
        if not sku:
            raise ValueError(f"Item row {i} needs an SKU.")
        if sku.casefold() in seen_items:
            raise ValueError(f"Duplicate SKU: {sku}.")
        seen_items.add(sku.casefold())
        picks = _finite_number(item.get("picks_per_day"), f"Daily picks for {sku}")
        storage = _finite_number(item.get("storage_units"), f"Storage units for {sku}")
        current_distance = _finite_number(item.get("current_distance_m", 0), f"Current distance for {sku}")
        if picks < 0 or storage <= 0 or current_distance < 0:
            raise ValueError(f"Pick rate/current distance must be non-negative and storage capacity positive for {sku}.")
        normalized_items.append({"sku": sku, "picks_per_day": picks, "storage_units": storage, "compatibility_group": group, "current_distance_m": current_distance})
    normalized_slots: list[dict[str, Any]] = []
    seen_slots: set[str] = set()
    for i, slot in enumerate(slots, start=1):
        if not isinstance(slot, Mapping):
            raise ValueError(f"Slot row {i} must be an object.")
        slot_id = str(slot.get("slot_id", "")).strip()
        group = str(slot.get("compatibility_group", "*")).strip() or "*"
        if not slot_id:
            raise ValueError(f"Slot row {i} needs a slot_id.")
        if slot_id.casefold() in seen_slots:
            raise ValueError(f"Duplicate slot ID: {slot_id}.")
        seen_slots.add(slot_id.casefold())
        distance = _finite_number(slot.get("distance_m"), f"Distance for slot {slot_id}")
        capacity = _finite_number(slot.get("capacity_units"), f"Capacity for slot {slot_id}")
        if distance < 0 or capacity <= 0:
            raise ValueError(f"Distance must be non-negative and slot capacity positive for {slot_id}.")
        normalized_slots.append({"slot_id": slot_id, "distance_m": distance, "capacity_units": capacity, "compatibility_group": group})
    available_slots = list(normalized_slots)
    assignments: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = []
    for item in sorted(normalized_items, key=lambda x: (-x["picks_per_day"], -x["storage_units"], x["sku"])):
        candidates = [
            s for s in available_slots
            if s["capacity_units"] >= item["storage_units"]
            and (item["compatibility_group"] == "*" or s["compatibility_group"] == "*" or s["compatibility_group"] == item["compatibility_group"])
        ]
        if not candidates:
            unassigned.append({
                "SKU": item["sku"],
                "Picks per day": item["picks_per_day"],
                "Required storage units": item["storage_units"],
                "Compatibility group": item["compatibility_group"],
                "Reason": "No available slot meets capacity and compatibility constraints",
            })
            continue
        slot = min(candidates, key=lambda s: (s["distance_m"], s["slot_id"]))
        available_slots.remove(slot)
        improvement = item["current_distance_m"] - slot["distance_m"]
        assignments.append({
            "SKU": item["sku"],
            "Slot": slot["slot_id"],
            "Picks per day": item["picks_per_day"],
            "Required storage units": item["storage_units"],
            "Slot capacity units": slot["capacity_units"],
            "Distance to slot (m)": slot["distance_m"],
            "Current distance (m)": item["current_distance_m"],
            "One-way distance improvement (m)": improvement,
            "Estimated round-trip distance change (m/day)": -2.0 * improvement * item["picks_per_day"],
        })
    assigned_frame = pd.DataFrame(assignments)
    unassigned_frame = pd.DataFrame(unassigned)
    total_daily_change = float(assigned_frame["Estimated round-trip distance change (m/day)"].sum()) if not assigned_frame.empty else 0.0
    return {
        "status": "SLOTTING_HEURISTIC_COMPLETE" if not unassigned else "SLOTTING_PARTIAL_UNASSIGNED_ITEMS",
        "item_count": len(normalized_items),
        "assigned_count": len(assignments),
        "unassigned_count": len(unassigned),
        "remaining_slot_count": len(available_slots),
        "estimated_round_trip_distance_change_m_per_day": total_daily_change,
        "assignments": assigned_frame,
        "unassigned_items": unassigned_frame,
        "method": "Sort by picks/day then assign the nearest available compatible slot that meets storage capacity; greedy heuristic, not globally optimal.",
        "warning": "Distance change uses the entered current and proposed one-way distances and assumes a round trip per pick. Validate dimensions, access/safety, zoning, co-picking, replenishment and actual travel paths before implementing a slot change.",
    }


def optimize_task_resource_assignment(
    task_names: Sequence[str],
    resource_names: Sequence[str],
    cost_matrix: Sequence[Sequence[float]],
) -> dict[str, Any]:
    """Solve a rectangular one-to-one task/resource assignment using linear assignment."""
    if isinstance(task_names, (str, bytes)) or not isinstance(task_names, Sequence) or not task_names:
        raise ValueError("Provide task names.")
    if isinstance(resource_names, (str, bytes)) or not isinstance(resource_names, Sequence) or not resource_names:
        raise ValueError("Provide resource names.")
    tasks = [str(x).strip() for x in task_names]
    resources = [str(x).strip() for x in resource_names]
    if any(not x for x in tasks) or len(set(x.casefold() for x in tasks)) != len(tasks):
        raise ValueError("Task names must be non-blank and unique.")
    if any(not x for x in resources) or len(set(x.casefold() for x in resources)) != len(resources):
        raise ValueError("Resource names must be non-blank and unique.")
    if isinstance(cost_matrix, (str, bytes)) or not isinstance(cost_matrix, Sequence):
        raise ValueError("Cost matrix must be a numeric list of lists.")
    try:
        costs = np.asarray(cost_matrix, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Cost matrix must contain only finite numeric costs.") from exc
    if costs.shape != (len(tasks), len(resources)):
        raise ValueError(f"Cost matrix dimensions must be {len(tasks)} tasks × {len(resources)} resources.")
    if not np.isfinite(costs).all():
        raise ValueError("Cost matrix values must be finite; represent unavailable pairs using a separate supported constraint model.")
    from scipy.optimize import linear_sum_assignment
    row_idx, col_idx = linear_sum_assignment(costs)
    assignments = [
        {"Task": tasks[int(i)], "Resource": resources[int(j)], "Assignment cost": float(costs[i, j])}
        for i, j in zip(row_idx, col_idx)
    ]
    assigned_tasks = {row["Task"] for row in assignments}
    unassigned = [task for task in tasks if task not in assigned_tasks]
    return {
        "status": "OPTIMAL_ONE_TO_ONE_ASSIGNMENT" if not unassigned else "PARTIAL_ASSIGNMENT_NEEDS_MORE_RESOURCES",
        "task_count": len(tasks),
        "resource_count": len(resources),
        "assigned_count": len(assignments),
        "unassigned_tasks": unassigned,
        "total_assignment_cost": float(sum(row["Assignment cost"] for row in assignments)),
        "assignments": pd.DataFrame(assignments),
        "method": "Minimum-cost rectangular linear assignment via the Hungarian algorithm",
        "warning": "This solver supports one-to-one assignment cost only. It does not implement multi-period schedules, calendars, skill constraints, precedence, resource capacity or overtime/labor rules.",
    }


def compare_energy_performance_scenarios(
    baseline: Mapping[str, Any],
    alternatives: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare energy intensity, energy cost and emissions for user-defined scenarios."""
    if not isinstance(baseline, Mapping):
        raise ValueError("Provide a baseline object.")
    if isinstance(alternatives, (str, bytes)) or not isinstance(alternatives, Sequence) or not alternatives:
        raise ValueError("Provide at least one alternative energy scenario.")
    def read_metrics(item: Mapping[str, Any], label: str) -> tuple[float, float, float, float]:
        energy = _finite_number(item.get("energy_kwh"), f"Energy (kWh) for {label}")
        output = _finite_number(item.get("output_units"), f"Output units for {label}")
        rate = _finite_number(item.get("cost_per_kwh"), f"Energy cost/kWh for {label}")
        factor = _finite_number(item.get("emission_factor_kg_per_kwh"), f"Emission factor for {label}")
        if energy < 0 or output <= 0 or rate < 0 or factor < 0:
            raise ValueError(f"Energy and factors cannot be negative and output must be positive for {label}.")
        return energy, output, rate, factor
    base_name = str(baseline.get("name", "Baseline")).strip() or "Baseline"
    base_energy, base_output, base_rate, base_factor = read_metrics(baseline, base_name)
    if base_energy <= 0:
        raise ValueError("Baseline energy must be greater than zero to compare intensity savings.")
    base_intensity = base_energy / base_output
    base_cost = base_energy * base_rate
    base_emissions = base_energy * base_factor
    rows: list[dict[str, Any]] = []
    seen: set[str] = {base_name.casefold()}
    for i, alternative in enumerate(alternatives, start=1):
        if not isinstance(alternative, Mapping):
            raise ValueError(f"Energy scenario {i} must be an object.")
        name = str(alternative.get("name", "")).strip()
        if not name:
            raise ValueError(f"Energy scenario {i} needs a name.")
        if name.casefold() in seen:
            raise ValueError(f"Scenario names must be unique, including the baseline: {name}.")
        seen.add(name.casefold())
        energy, output, rate, factor = read_metrics(alternative, name)
        intensity = energy / output
        cost = energy * rate
        emissions = energy * factor
        rows.append({
            "Scenario": name,
            "Energy (kWh)": energy,
            "Output units": output,
            "Energy intensity (kWh/unit)": intensity,
            "Energy cost": cost,
            "Emissions (kg CO₂e)": emissions,
            "Energy intensity change vs baseline (%)": (intensity / base_intensity - 1.0) * 100.0,
            "Energy cost change vs baseline (%)": ((cost / base_cost - 1.0) * 100.0) if base_cost > 0 else None,
            "Emissions change vs baseline (%)": ((emissions / base_emissions - 1.0) * 100.0) if base_emissions > 0 else None,
        })
    frame = pd.DataFrame(rows).sort_values(
        by=["Energy intensity (kWh/unit)", "Scenario"], ascending=[True, True], kind="stable"
    ).reset_index(drop=True)
    return {
        "status": "ENERGY_SCENARIOS_COMPARED",
        "baseline": base_name,
        "baseline_energy_intensity_kwh_per_unit": base_intensity,
        "baseline_energy_cost": base_cost,
        "baseline_emissions_kg_co2e": base_emissions,
        "best_intensity_scenario": str(frame.iloc[0]["Scenario"]),
        "scenario_count": len(frame),
        "scenario_comparison": frame,
        "method": "Compare measured/specified energy, output, price and emissions factors per scenario; rank by energy intensity.",
        "warning": "Scenario comparison only; this does not control plant equipment or prove achievable savings. Use comparable measurement boundaries and factor sources/dates, and clearly distinguish modeled scenarios from measured operations.",
    }


def map_industrial_fields(
    source_columns: Sequence[str],
    *,
    canonical_fields: Mapping[str, Sequence[str]] | None = None,
    manual_mapping: Mapping[str, str] | None = None,
    minimum_confidence: float = 0.65,
) -> dict[str, Any]:
    """Suggest source-to-canonical industrial field mappings; never auto-confirms fuzzy matches."""
    import re
    from difflib import SequenceMatcher

    if isinstance(source_columns, (str, bytes)) or not isinstance(source_columns, Sequence) or not source_columns:
        raise ValueError("Provide at least one source column name.")
    threshold = _finite_number(minimum_confidence, "Minimum mapping confidence")
    if not 0 <= threshold <= 1:
        raise ValueError("Minimum mapping confidence must be between 0 and 1.")
    defaults: dict[str, tuple[str, ...]] = {
        "timestamp": ("timestamp", "time stamp", "datetime", "date time", "event time", "recorded at", "date"),
        "asset_id": ("asset id", "asset", "equipment id", "machine id", "tag id"),
        "process": ("process", "operation", "work center", "workstation", "station"),
        "product_id": ("product id", "product", "sku", "item", "part number", "material"),
        "order_id": ("order id", "order", "work order", "production order", "job id"),
        "quantity": ("quantity", "qty", "units", "output", "production quantity", "produced units"),
        "defect_count": ("defect count", "defects", "rejects", "rejected units", "defective units"),
        "scrap_quantity": ("scrap", "scrap quantity", "scrap units", "waste quantity"),
        "cycle_time": ("cycle time", "ct", "processing time", "operation time"),
        "planned_time": ("planned time", "scheduled time", "planned production time"),
        "run_time": ("run time", "runtime", "operating time", "operating minutes"),
        "downtime": ("downtime", "down time", "stoppage time", "idle time", "lost time"),
        "good_count": ("good count", "good units", "accepted units", "conforming units"),
        "total_count": ("total count", "total units", "inspected units", "produced quantity"),
        "energy_kwh": ("energy kwh", "energy consumption", "electricity kwh", "kwh"),
        "work_hours": ("work hours", "labor hours", "labour hours", "hours worked"),
        "incident_count": ("incidents", "incident count", "injuries", "safety incidents"),
        "cost": ("cost", "amount", "unit cost", "total cost", "expense"),
        "currency": ("currency", "currency code", "cost currency"),
        "unit": ("unit", "uom", "unit of measure", "measurement unit"),
        "batch_size": ("batch size", "lot size", "batch quantity"),
        "wip_units": ("wip", "wip units", "work in process", "queue units"),
        "demand": ("demand", "forecast demand", "customer demand", "required quantity"),
        "inventory": ("inventory", "on hand", "on hand quantity", "stock"),
        "lead_time": ("lead time", "lead time days", "supplier lead time"),
    }
    canonical: dict[str, tuple[str, ...]] = {}
    raw_fields = canonical_fields or defaults
    for key, aliases in raw_fields.items():
        target = str(key).strip()
        if not target:
            raise ValueError("Canonical field identifiers cannot be blank.")
        if isinstance(aliases, (str, bytes)) or not isinstance(aliases, Sequence):
            raise ValueError(f"Aliases for canonical field '{target}' must be a list of strings.")
        canonical[target] = tuple([target, *(str(alias).strip() for alias in aliases if str(alias).strip())])

    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()

    normalized_aliases: dict[str, set[str]] = {
        target: {normalize(alias) for alias in aliases}
        for target, aliases in canonical.items()
    }
    columns = [str(col).strip() for col in source_columns]
    if any(not col for col in columns):
        raise ValueError("Source column names cannot be blank.")
    if len({col.casefold() for col in columns}) != len(columns):
        raise ValueError("Source column names must be unique, ignoring case.")
    manual = dict(manual_mapping or {})
    unknown_manual_sources = sorted(set(manual) - set(columns))
    if unknown_manual_sources:
        raise ValueError(f"Manual mapping includes unknown source column(s): {', '.join(unknown_manual_sources)}.")
    for source, target in manual.items():
        if target not in canonical:
            raise ValueError(f"Manual mapping for '{source}' refers to unknown canonical field '{target}'.")
    used_canonical: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    for source in columns:
        source_norm = normalize(source)
        if source in manual:
            target = manual[source]
            prior = used_canonical.get(target)
            if prior is not None:
                raise ValueError(f"Canonical field '{target}' is manually mapped by both '{prior}' and '{source}'.")
            used_canonical[target] = source
            results.append({
                "Source column": source, "Suggested canonical field": target,
                "Confidence": 1.0, "Mapping status": "MANUALLY_CONFIRMED",
                "Candidate alternatives": "", "Original name preserved": True,
            })
            continue
        candidate_scores: list[tuple[float, str]] = []
        for target, aliases in normalized_aliases.items():
            score = max(
                [1.0 if source_norm == alias else SequenceMatcher(None, source_norm, alias).ratio() for alias in aliases]
                or [0.0]
            )
            candidate_scores.append((score, target))
        candidate_scores.sort(key=lambda item: (-item[0], item[1]))
        best_score, best_target = candidate_scores[0]
        alternatives = "; ".join(f"{target} ({score:.2f})" for score, target in candidate_scores[1:4])
        prior_source = used_canonical.get(best_target)
        if best_score >= 0.999 and prior_source is None:
            status = "EXACT_ALIAS — CONFIRM"
            used_canonical[best_target] = source
            proposed = best_target
        elif best_score >= threshold and prior_source is None:
            status = "SUGGESTED — CONFIRM REQUIRED"
            proposed = best_target
            used_canonical[best_target] = source
        elif prior_source is not None and best_score >= threshold:
            status = "AMBIGUOUS_DUPLICATE_TARGET"
            proposed = ""
            alternatives = f"{best_target} already suggested for {prior_source}; " + alternatives
        else:
            status = "UNMAPPED — MANUAL REVIEW"
            proposed = ""
        results.append({
            "Source column": source, "Suggested canonical field": proposed,
            "Confidence": round(float(best_score), 4), "Mapping status": status,
            "Candidate alternatives": alternatives, "Original name preserved": True,
        })
    frame = pd.DataFrame(results)
    return {
        "status": "FIELD_MAPPING_SUGGESTIONS_READY",
        "source_column_count": len(columns),
        "mapped_or_suggested_count": int(frame["Suggested canonical field"].astype(str).str.strip().ne("").sum()),
        "needs_manual_review_count": int(frame["Mapping status"].str.contains("REVIEW|AMBIGUOUS|CONFIRM REQUIRED", regex=True).sum()),
        "canonical_field_count": len(canonical),
        "mapping_table": frame,
        "canonical_field_ids": list(canonical),
        "warning": "Fuzzy suggestions are never proof of semantic equivalence. Confirm each mapping against the source data dictionary and keep the original source column names.",
    }


def prioritize_maintenance_backlog(
    work_orders: Sequence[Mapping[str, Any]],
    available_hours: float,
    *,
    available_skills: Sequence[str] | None = None,
    overdue_weight_per_day: float = 2.0,
    due_soon_days: int = 3,
    due_soon_bonus: float = 8.0,
) -> dict[str, Any]:
    """Greedy work-order prioritization under a supplied labor-hour budget."""
    hours = _finite_number(available_hours, "Available maintenance labor hours")
    overdue_weight = _finite_number(overdue_weight_per_day, "Overdue priority weight")
    due_bonus = _finite_number(due_soon_bonus, "Due-soon priority bonus")
    if hours < 0:
        raise ValueError("Available maintenance labor hours cannot be negative.")
    if overdue_weight < 0 or due_bonus < 0:
        raise ValueError("Priority weights cannot be negative.")
    if isinstance(due_soon_days, bool) or not isinstance(due_soon_days, int) or due_soon_days < 0:
        raise ValueError("Due-soon threshold must be a non-negative whole number of days.")
    if isinstance(work_orders, (str, bytes)) or not isinstance(work_orders, Sequence) or not work_orders:
        raise ValueError("Provide at least one maintenance work order.")
    skills = {str(s).strip().casefold() for s in (available_skills or []) if str(s).strip()}
    restrict_skills = available_skills is not None
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, order in enumerate(work_orders, start=1):
        if not isinstance(order, Mapping):
            raise ValueError(f"Work order row {i} must be an object.")
        order_id = str(order.get("work_order_id", order.get("id", ""))).strip()
        description = str(order.get("task", order.get("description", ""))).strip()
        if not order_id or not description:
            raise ValueError(f"Work order row {i} needs a work_order_id and task description.")
        if order_id.casefold() in seen:
            raise ValueError(f"Work order IDs must be unique; duplicate: {order_id}.")
        seen.add(order_id.casefold())
        criticality = _finite_number(order.get("criticality_score"), f"Criticality score for {order_id}")
        days_due = _finite_number(order.get("days_until_due"), f"Days until due for {order_id}")
        duration = _finite_number(order.get("estimated_hours"), f"Estimated hours for {order_id}")
        if not criticality.is_integer() or not 1 <= criticality <= 5:
            raise ValueError(f"Criticality score for {order_id} must be a whole number from 1 through 5.")
        if duration <= 0:
            raise ValueError(f"Estimated hours for {order_id} must be greater than zero.")
        if not days_due.is_integer():
            raise ValueError(f"Days until due for {order_id} must be a whole number.")
        skill = str(order.get("required_skill", "")).strip()
        skill_available = not restrict_skills or not skill or skill.casefold() in skills
        days_int = int(days_due)
        score = int(criticality) * 10.0 + max(0, -days_int) * overdue_weight
        if 0 <= days_int <= due_soon_days:
            score += due_bonus
        normalized.append({
            "Work order ID": order_id,
            "Task": description,
            "Asset": str(order.get("asset", "")).strip() or "UNSPECIFIED",
            "Criticality (1–5)": int(criticality),
            "Days until due": days_int,
            "Estimated hours": duration,
            "Required skill": skill or "NOT SPECIFIED",
            "Skill available": skill_available,
            "Priority score": score,
        })
    ordered = sorted(normalized, key=lambda x: (-x["Priority score"], x["Days until due"], x["Work order ID"]))
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    used_hours = 0.0
    for order in ordered:
        if not order["Skill available"]:
            deferred.append({**order, "Deferral reason": "Required skill not in available-skill list"})
        elif used_hours + order["Estimated hours"] <= hours + 1e-9:
            selected.append(order)
            used_hours += order["Estimated hours"]
        else:
            deferred.append({**order, "Deferral reason": "Insufficient remaining labor hours"})
    return {
        "status": "BACKLOG_PRIORITIZED",
        "work_order_count": len(normalized),
        "selected_count": len(selected),
        "deferred_count": len(deferred),
        "available_labor_hours": hours,
        "selected_labor_hours": used_hours,
        "remaining_labor_hours": max(0.0, hours - used_hours),
        "selected_work_orders": pd.DataFrame(selected),
        "deferred_work_orders": pd.DataFrame(deferred),
        "method": "Greedy sort by user-defined criticality/due-date score, then fit eligible tasks within the labor-hour limit",
        "priority_formula": "priority = criticality×10 + max(0, overdue days)×overdue_weight + due_soon_bonus when due within the configured window",
        "warning": "This is a transparent prioritization heuristic, not an optimized maintenance schedule. Check asset risk, permits, parts, shift calendars, task dependencies and safety-critical requirements before dispatch.",
    }


def reconcile_sop_plan(
    periods: Sequence[Mapping[str, Any]],
    *,
    starting_inventory: float = 0.0,
) -> dict[str, Any]:
    """Reconcile time-phased demand, planned production, supply constraints and inventory/backlog."""
    inventory = _finite_number(starting_inventory, "Starting inventory")
    if inventory < 0:
        raise ValueError("Starting inventory cannot be negative.")
    if isinstance(periods, (str, bytes)) or not isinstance(periods, Sequence) or not periods:
        raise ValueError("Provide at least one S&OP period object.")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    opening_backlog = 0.0
    for i, period in enumerate(periods, start=1):
        if not isinstance(period, Mapping):
            raise ValueError(f"S&OP period row {i} must be an object.")
        label = str(period.get("period", "")).strip()
        if not label:
            raise ValueError(f"S&OP period row {i} needs a label.")
        if label.casefold() in seen:
            raise ValueError(f"S&OP period labels must be unique; duplicate: {label}.")
        seen.add(label.casefold())
        demand = _finite_number(period.get("demand"), f"Demand for {label}")
        planned = _finite_number(period.get("planned_production"), f"Planned production for {label}")
        receipts = _finite_number(period.get("scheduled_receipts", 0), f"Scheduled receipts for {label}")
        capacity_raw = period.get("production_capacity")
        capacity = None if capacity_raw is None or str(capacity_raw).strip() == "" else _finite_number(capacity_raw, f"Production capacity for {label}")
        safety = _finite_number(period.get("target_safety_stock", 0), f"Target safety stock for {label}")
        if min(demand, planned, receipts, safety) < 0 or (capacity is not None and capacity < 0):
            raise ValueError(f"Demand, planned production, receipts, capacity and safety stock cannot be negative for {label}.")
        if capacity is not None and planned > capacity:
            effective_production = capacity
            capacity_reduction = planned - capacity
        else:
            effective_production = planned
            capacity_reduction = 0.0
        opening_inventory = inventory
        supply = opening_inventory + effective_production + receipts
        required = demand + opening_backlog + safety
        raw_balance = supply - demand - opening_backlog
        if raw_balance >= 0:
            ending_inventory = raw_balance
            ending_backlog = 0.0
        else:
            ending_inventory = 0.0
            ending_backlog = -raw_balance
        demand_available_for_current_period = max(0.0, supply - opening_backlog)
        demand_fulfilled = min(demand, demand_available_for_current_period)
        service_level = demand_fulfilled / demand * 100.0 if demand > 0 else 100.0
        safety_stock_gap = max(0.0, safety - ending_inventory)
        rows.append({
            "Period": label,
            "Opening inventory": opening_inventory,
            "Demand": demand,
            "Planned production": planned,
            "Production capacity": capacity,
            "Capacity-constrained production": effective_production,
            "Production above capacity": capacity_reduction,
            "Scheduled receipts": receipts,
            "Opening backlog": opening_backlog,
            "Available supply": supply,
            "Demand fulfilled from current supply": demand_fulfilled,
            "Demand service level (%)": service_level,
            "Ending inventory": ending_inventory,
            "Ending backlog": ending_backlog,
            "Target safety stock": safety,
            "Safety stock gap": safety_stock_gap,
        })
        inventory = ending_inventory
        opening_backlog = ending_backlog
    frame = pd.DataFrame(rows)
    return {
        "status": "SOP_RECONCILED",
        "period_count": len(frame),
        "total_demand": float(frame["Demand"].sum()),
        "total_capacity_constrained_production": float(frame["Capacity-constrained production"].sum()),
        "total_production_above_capacity": float(frame["Production above capacity"].sum()),
        "ending_inventory": float(frame.iloc[-1]["Ending inventory"]),
        "ending_backlog": float(frame.iloc[-1]["Ending backlog"]),
        "periods_below_full_service": int((frame["Demand service level (%)"] < 99.999).sum()),
        "period_plan": frame,
        "assumptions": "Single aggregate product family; demand is served from opening inventory, capacity-constrained production and scheduled receipts. Unmet demand is carried forward as backlog; safety stock is reported as a target rather than double-counted in total demand.",
        "warning": "This is a deterministic aggregate balance, not a full finite-capacity S&OP optimizer. Use compatible units and periods; validate product mix, production calendars, lead times, workforce and inventory policies before commitment.",
    }


def score_supplier_performance(
    suppliers: Sequence[Mapping[str, Any]],
    criteria_weights: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate weighted supplier scorecards on user-entered 0–100 criterion scores."""
    if isinstance(suppliers, (str, bytes)) or not isinstance(suppliers, Sequence) or not suppliers:
        raise ValueError("Provide at least one supplier record.")
    if not isinstance(criteria_weights, Mapping) or not criteria_weights:
        raise ValueError("Provide one or more criterion weights.")
    weights: dict[str, float] = {}
    for key, raw_weight in criteria_weights.items():
        name = str(key).strip()
        weight = _finite_number(raw_weight, f"Weight for supplier criterion {name}")
        if not name:
            raise ValueError("Supplier criterion names cannot be blank.")
        if weight < 0:
            raise ValueError(f"Weight for supplier criterion '{name}' cannot be negative.")
        weights[name] = weight
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("At least one supplier criterion weight must be greater than zero.")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, supplier in enumerate(suppliers, start=1):
        if not isinstance(supplier, Mapping):
            raise ValueError(f"Supplier row {i} must be an object.")
        name = str(supplier.get("supplier", supplier.get("name", ""))).strip()
        if not name:
            raise ValueError(f"Supplier row {i} needs a name.")
        if name.casefold() in seen:
            raise ValueError(f"Supplier names must be unique; duplicate: {name}.")
        seen.add(name.casefold())
        scores = supplier.get("scores")
        if not isinstance(scores, Mapping):
            raise ValueError(f"Supplier '{name}' needs a scores object.")
        normalized_scores: dict[str, float] = {}
        missing: list[str] = []
        weighted_sum = 0.0
        supplied_weight = 0.0
        for criterion, weight in weights.items():
            if criterion not in scores or scores[criterion] is None or str(scores[criterion]).strip() == "":
                missing.append(criterion)
                continue
            value = _finite_number(scores[criterion], f"Score for supplier {name} / {criterion}")
            if not 0 <= value <= 100:
                raise ValueError(f"Score for supplier '{name}' / '{criterion}' must be between 0 and 100.")
            normalized_scores[criterion] = value
            weighted_sum += value * weight
            supplied_weight += weight
        complete = not missing
        composite = weighted_sum / total_weight if complete else None
        row: dict[str, Any] = {
            "Supplier": name,
            "Composite score (0–100)": composite,
            "Score status": "COMPLETE" if complete else "INCOMPLETE — DO NOT RANK",
            "Missing criteria": ", ".join(missing),
            "Data as of": str(supplier.get("data_as_of", "")).strip() or "NOT PROVIDED",
            "Evidence reference": str(supplier.get("evidence_reference", "")).strip() or "NOT PROVIDED",
            "Risk/mitigation notes": str(supplier.get("risk_mitigation", "")).strip() or "NOT PROVIDED",
        }
        for criterion in weights:
            row[f"{criterion} score"] = normalized_scores.get(criterion)
        rows.append(row)
    frame = pd.DataFrame(rows)
    complete_frame = frame[frame["Score status"] == "COMPLETE"].sort_values(
        by=["Composite score (0–100)", "Supplier"], ascending=[False, True], kind="stable"
    )
    ranked_names = {name: rank for rank, name in enumerate(complete_frame["Supplier"].tolist(), start=1)}
    frame["Rank among complete scores"] = frame["Supplier"].map(ranked_names).astype("Int64")
    return {
        "status": "SUPPLIER_SCORECARD_CALCULATED",
        "supplier_count": len(frame),
        "complete_score_count": int((frame["Score status"] == "COMPLETE").sum()),
        "incomplete_score_count": int((frame["Score status"] != "COMPLETE").sum()),
        "criteria_weights": dict(weights),
        "total_weight": total_weight,
        "scorecard": frame.sort_values(
            by=["Score status", "Rank among complete scores", "Supplier"],
            ascending=[True, True, True], na_position="last", kind="stable"
        ).reset_index(drop=True),
        "warning": "Weights and 0–100 scores are user-defined. Incomplete suppliers are not ranked. Verify evidence recency, score rubric and conflict-of-interest controls before procurement decisions.",
    }


# Additional specialist engines integrated into the 100-tool Workbench.
# Each method is intentionally scoped to a documented baseline; unsupported
# assumptions are surfaced in result metadata rather than silently inferred.

def _finite_vector(values: Sequence[Any], field: str, *, minimum: int = 2) -> list[float]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{field} must be a sequence of numeric observations.")
    result = [_finite_number(value, f"{field} item {i}") for i, value in enumerate(values, start=1)]
    if len(result) < minimum:
        raise ValueError(f"{field} must contain at least {minimum} observations.")
    return result


def fit_simple_linear_regression(
    observations: Sequence[Mapping[str, Any]], *, alpha: float = 0.05
) -> dict[str, Any]:
    """Fit ordinary least squares for one numeric predictor and one response.

    Returns coefficient inference and the regression ANOVA decomposition. This
    is a descriptive first-order model, not a causal model or an extrapolation
    guarantee. Inputs must already be cleaned and appropriately ordered if time
    is a predictor.
    """
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise ValueError("Observations must be a JSON list of {x, y} objects.")
    if len(observations) < 3:
        raise ValueError("Simple linear regression needs at least three observations.")
    level = _finite_number(alpha, "Alpha")
    if not 0 < level < 1:
        raise ValueError("Alpha must be strictly between 0 and 1.")
    xs: list[float] = []
    ys: list[float] = []
    for index, item in enumerate(observations, start=1):
        if not isinstance(item, Mapping) or "x" not in item or "y" not in item:
            raise ValueError(f"Observation {index} must contain numeric x and y values.")
        xs.append(_finite_number(item["x"], f"Observation {index} x"))
        ys.append(_finite_number(item["y"], f"Observation {index} y"))
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    sxx = float(np.sum((x - x_mean) ** 2))
    if sxx <= np.finfo(float).eps:
        raise ValueError("Predictor x must contain at least two distinct values.")
    slope = float(np.sum((x - x_mean) * (y - y_mean)) / sxx)
    intercept = float(y_mean - slope * x_mean)
    fitted = intercept + slope * x
    residuals = y - fitted
    sse = float(np.sum(residuals ** 2))
    sst = float(np.sum((y - y_mean) ** 2))
    if sst <= np.finfo(float).eps:
        raise ValueError("Response y must vary; R-squared is undefined for a constant response.")
    ssr = max(0.0, sst - sse)
    n = len(x)
    df_regression = 1
    df_residual = n - 2
    mse = sse / df_residual
    residual_se = math.sqrt(max(mse, 0.0))
    slope_se = residual_se / math.sqrt(sxx)
    if slope_se <= np.finfo(float).eps:
        t_stat = math.copysign(math.inf, slope) if slope != 0 else 0.0
        p_value = 0.0 if slope != 0 else 1.0
        slope_ci = (slope, slope)
    else:
        t_stat = slope / slope_se
        p_value = float(2 * t.sf(abs(t_stat), df_residual))
        margin = float(t.ppf(1 - level / 2, df_residual) * slope_se)
        slope_ci = (slope - margin, slope + margin)
    if sse <= np.finfo(float).eps and ssr > 0:
        f_stat = math.inf
        f_p_value = 0.0
    elif mse > 0:
        f_stat = (ssr / df_regression) / mse
        f_p_value = float(f.sf(f_stat, df_regression, df_residual))
    else:
        f_stat = 0.0
        f_p_value = 1.0
    r_squared = min(1.0, max(0.0, 1 - sse / sst))
    adjusted_r_squared = 1 - (1 - r_squared) * (n - 1) / df_residual
    residual_frame = pd.DataFrame({
        "Observation": np.arange(1, n + 1),
        "X": x,
        "Observed Y": y,
        "Fitted Y": fitted,
        "Residual": residuals,
    })
    anova_table = pd.DataFrame([
        {"Source": "Regression", "Sum of squares": ssr, "df": df_regression, "Mean square": ssr / df_regression, "F": f_stat, "p-value": f_p_value},
        {"Source": "Residual", "Sum of squares": sse, "df": df_residual, "Mean square": mse, "F": None, "p-value": None},
        {"Source": "Total", "Sum of squares": sst, "df": n - 1, "Mean square": None, "F": None, "p-value": None},
    ])
    return {
        "status": "CALCULATED",
        "method": "Ordinary least squares; one predictor; two-sided coefficient test",
        "n": n,
        "intercept": intercept,
        "slope": slope,
        "slope_standard_error": slope_se,
        "slope_t_statistic": t_stat,
        "slope_p_value": p_value,
        "slope_confidence_level": 1 - level,
        "slope_confidence_interval": slope_ci,
        "r_squared": r_squared,
        "adjusted_r_squared": adjusted_r_squared,
        "residual_standard_error": residual_se,
        "anova_table": anova_table,
        "residuals": residual_frame,
        "formula": "y_hat = intercept + slope*x; R² = 1 − SSE/SST",
        "assumptions": "Linear mean relation, independent errors, stable error variance and suitable residual distribution for classical inference. Inspect residual plots before relying on p-values or intervals.",
        "warning": "Association is not proof of causation. This implementation supports one numeric predictor only; no polynomial, multivariable, robust or time-series regression is implied.",
    }


def run_one_way_anova(
    groups: Mapping[str, Sequence[Any]], *, alpha: float = 0.05
) -> dict[str, Any]:
    """Run one-way fixed-factor ANOVA for independent groups with finite values."""
    if not isinstance(groups, Mapping) or len(groups) < 2:
        raise ValueError("Provide at least two named groups for one-way ANOVA.")
    level = _finite_number(alpha, "Alpha")
    if not 0 < level < 1:
        raise ValueError("Alpha must be strictly between 0 and 1.")
    normalized: dict[str, list[float]] = {}
    for raw_name, values in groups.items():
        name = str(raw_name or "").strip()
        if not name:
            raise ValueError("Every ANOVA group needs a non-empty name.")
        if name in normalized:
            raise ValueError(f"ANOVA group names must be unique: {name}.")
        normalized[name] = _finite_vector(values, f"Group {name}", minimum=2)
    all_values = np.asarray([value for values in normalized.values() for value in values], dtype=float)
    grand_mean = float(np.mean(all_values))
    ss_between = float(sum(len(values) * (float(np.mean(values)) - grand_mean) ** 2 for values in normalized.values()))
    ss_within = float(sum(sum((np.asarray(values) - float(np.mean(values))) ** 2) for values in normalized.values()))
    n = len(all_values)
    k = len(normalized)
    df_between = k - 1
    df_within = n - k
    if df_within <= 0:
        raise ValueError("ANOVA needs residual degrees of freedom.")
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within
    if ms_within <= np.finfo(float).eps:
        raise ValueError("Within-group variance is zero; the classical F statistic is undefined for this fixture.")
    f_stat = ms_between / ms_within
    p_value = float(f.sf(f_stat, df_between, df_within))
    ss_total = ss_between + ss_within
    summary = pd.DataFrame([
        {"Group": name, "n": len(values), "Mean": float(np.mean(values)), "Standard deviation": float(np.std(values, ddof=1))}
        for name, values in normalized.items()
    ])
    table = pd.DataFrame([
        {"Source": "Between groups", "Sum of squares": ss_between, "df": df_between, "Mean square": ms_between, "F": f_stat, "p-value": p_value},
        {"Source": "Within groups", "Sum of squares": ss_within, "df": df_within, "Mean square": ms_within, "F": None, "p-value": None},
        {"Source": "Total", "Sum of squares": ss_total, "df": n - 1, "Mean square": None, "F": None, "p-value": None},
    ])
    return {
        "status": "CALCULATED",
        "method": "One-way independent-groups ANOVA",
        "group_count": k,
        "observation_count": n,
        "df_between": df_between,
        "df_within": df_within,
        "f_statistic": f_stat,
        "p_value": p_value,
        "eta_squared": ss_between / ss_total if ss_total > 0 else 0.0,
        "alpha": level,
        "decision": "REJECT_EQUAL_MEANS_NULL" if p_value < level else "FAIL_TO_REJECT_EQUAL_MEANS_NULL",
        "group_summary": summary,
        "anova_table": table,
        "assumptions": "Independent observations, approximate within-group normality and comparable group variances. Inspect study design and residuals; post-hoc pairwise tests are not included.",
        "warning": "A significant omnibus test indicates that not all group means are equal; it does not identify which groups differ or establish causation.",
    }


def run_welch_t_test(
    sample_a: Sequence[Any], sample_b: Sequence[Any], *, alpha: float = 0.05
) -> dict[str, Any]:
    """Welch two-sided t-test for two independent numeric samples."""
    a = _finite_vector(sample_a, "Sample A", minimum=2)
    b = _finite_vector(sample_b, "Sample B", minimum=2)
    level = _finite_number(alpha, "Alpha")
    if not 0 < level < 1:
        raise ValueError("Alpha must be strictly between 0 and 1.")
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    mean_a, mean_b = float(np.mean(arr_a)), float(np.mean(arr_b))
    var_a, var_b = float(np.var(arr_a, ddof=1)), float(np.var(arr_b, ddof=1))
    component_a, component_b = var_a / len(a), var_b / len(b)
    standard_error = math.sqrt(component_a + component_b)
    if standard_error <= np.finfo(float).eps:
        raise ValueError("Both samples have zero estimated uncertainty; a finite Welch test is undefined.")
    df_denominator = (component_a ** 2) / (len(a) - 1) + (component_b ** 2) / (len(b) - 1)
    if df_denominator <= 0:
        raise ValueError("Welch degrees of freedom could not be established.")
    degrees_freedom = (component_a + component_b) ** 2 / df_denominator
    difference = mean_a - mean_b
    statistic = difference / standard_error
    p_value = float(2 * t.sf(abs(statistic), degrees_freedom))
    margin = float(t.ppf(1 - level / 2, degrees_freedom) * standard_error)
    pooled_descriptive_sd = math.sqrt((var_a + var_b) / 2)
    effect_size = difference / pooled_descriptive_sd if pooled_descriptive_sd > 0 else None
    return {
        "status": "CALCULATED",
        "method": "Welch independent two-sample t-test (two-sided)",
        "n_a": len(a),
        "n_b": len(b),
        "mean_a": mean_a,
        "mean_b": mean_b,
        "mean_difference_a_minus_b": difference,
        "standard_error": standard_error,
        "degrees_of_freedom": degrees_freedom,
        "t_statistic": statistic,
        "p_value": p_value,
        "alpha": level,
        "confidence_interval_level": 1 - level,
        "mean_difference_confidence_interval": (difference - margin, difference + margin),
        "descriptive_standardized_difference": effect_size,
        "decision": "REJECT_NULL" if p_value < level else "FAIL_TO_REJECT_NULL",
        "assumptions": "Independent observations and suitable sampling; Welch's method does not assume equal population variances. Small samples still require attention to distribution shape and outliers.",
        "warning": "A p-value is not the probability that the null hypothesis is true. Report the effect estimate, confidence interval, study design and practical context.",
    }


def forecast_demand_baselines(
    observations: Sequence[Any], *, holdout_periods: int = 3,
    horizon: int = 3, moving_average_window: int = 3
) -> dict[str, Any]:
    """Compare simple fixed-horizon demand baselines on a chronological holdout.

    Baselines are naïve-last-value, training mean and trailing moving average.
    This deliberately does not claim automatic seasonality detection or prediction
    intervals. Holdout observations are never used to fit a baseline.
    """
    values = _finite_vector(observations, "Demand history", minimum=5)
    for value, name, minimum, maximum in (
        (holdout_periods, "Holdout periods", 2, len(values) - 3),
        (horizon, "Forecast horizon", 1, 100),
        (moving_average_window, "Moving-average window", 1, len(values)),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer from {minimum} through {maximum}.")
    split = len(values) - holdout_periods
    train = np.asarray(values[:split], dtype=float)
    test = np.asarray(values[split:], dtype=float)
    if moving_average_window > len(train):
        raise ValueError("Moving-average window cannot exceed the pre-holdout training history.")
    training_mean = float(np.mean(train))
    trailing_train_mean = float(np.mean(train[-moving_average_window:]))
    candidates = {
        "Naive last value": np.repeat(float(train[-1]), len(test)),
        "Training mean": np.repeat(training_mean, len(test)),
        "Trailing moving average": np.repeat(trailing_train_mean, len(test)),
    }
    metric_rows = []
    for name, predicted in candidates.items():
        errors = test - predicted
        metric_rows.append({
            "Model": name,
            "Holdout MAE": float(np.mean(np.abs(errors))),
            "Holdout RMSE": float(math.sqrt(np.mean(errors ** 2))),
            "Holdout bias (actual − forecast)": float(np.mean(errors)),
        })
    metric_frame = pd.DataFrame(metric_rows).sort_values(
        ["Holdout MAE", "Holdout RMSE", "Model"], kind="stable"
    ).reset_index(drop=True)
    selected_model = str(metric_frame.iloc[0]["Model"])
    full = np.asarray(values, dtype=float)
    future_values = {
        "Naive last value": float(full[-1]),
        "Training mean": float(np.mean(full)),
        "Trailing moving average": float(np.mean(full[-moving_average_window:])),
    }
    forecast = pd.DataFrame({
        "Forecast step": np.arange(1, horizon + 1),
        "Selected baseline": [selected_model] * horizon,
        "Forecast": [future_values[selected_model]] * horizon,
    })
    backtest = pd.DataFrame({
        "Holdout step": np.arange(1, holdout_periods + 1),
        "Observed demand": test,
        **candidates,
    })
    return {
        "status": "BASELINES_COMPARED",
        "observation_count": len(values),
        "training_count": len(train),
        "holdout_count": len(test),
        "selected_model": selected_model,
        "metrics": metric_frame,
        "backtest": backtest,
        "forecast": forecast,
        "method": "Chronological holdout comparison of three simple demand baselines",
        "warning": "This is a baseline forecast only. No seasonality/trend model, prediction intervals, exogenous drivers or inventory service-level guarantee are included. Validate out-of-sample performance before operational use.",
    }


def simulate_monte_carlo_net_value(
    components: Sequence[Mapping[str, Any]], *, iterations: int = 10_000,
    seed: int = 42, output_unit: str = "user-defined units"
) -> dict[str, Any]:
    """Monte Carlo net-value screening for independent declared benefit/cost inputs.

    Roles apply a positive sign to benefits and a negative sign to costs. Inputs
    are sampled independently; the method does not create correlations between
    components. It is a scenario model, not measured savings or a live twin.
    """
    if not isinstance(components, Sequence) or isinstance(components, (str, bytes)) or not 1 <= len(components) <= 30:
        raise ValueError("Provide between 1 and 30 component definitions.")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 100 <= iterations <= 500_000:
        raise ValueError("Iterations must be an integer from 100 through 500000.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be a non-negative 32-bit integer.")
    unit_label = str(output_unit or "").strip()
    if not unit_label or len(unit_label) > 50:
        raise ValueError("Output unit must be a non-empty label of at most 50 characters.")
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(components, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Component {index} must be an object.")
        name = str(raw.get("name", "")).strip()
        role = str(raw.get("role", "")).strip().lower()
        distribution = str(raw.get("distribution", "")).strip().lower()
        if not name or name.casefold() in names:
            raise ValueError(f"Component names must be non-empty and unique (problem at component {index}).")
        names.add(name.casefold())
        if role not in {"benefit", "cost"}:
            raise ValueError(f"Component '{name}' role must be benefit or cost.")
        if distribution not in {"normal", "uniform", "triangular", "constant"}:
            raise ValueError(f"Component '{name}' has an unsupported distribution.")
        item: dict[str, Any] = {"name": name, "role": role, "distribution": distribution}
        if distribution == "normal":
            item["mean"] = _finite_number(raw.get("mean"), f"{name} mean")
            item["sd"] = _finite_number(raw.get("sd"), f"{name} standard deviation")
            if item["sd"] <= 0:
                raise ValueError(f"Component '{name}' normal standard deviation must be greater than zero.")
        elif distribution == "uniform":
            item["low"] = _finite_number(raw.get("low"), f"{name} low")
            item["high"] = _finite_number(raw.get("high"), f"{name} high")
            if item["high"] <= item["low"]:
                raise ValueError(f"Component '{name}' high must be greater than low.")
        elif distribution == "triangular":
            item["low"] = _finite_number(raw.get("low"), f"{name} low")
            item["mode"] = _finite_number(raw.get("mode"), f"{name} mode")
            item["high"] = _finite_number(raw.get("high"), f"{name} high")
            if not item["low"] <= item["mode"] <= item["high"] or item["high"] <= item["low"]:
                raise ValueError(f"Component '{name}' must satisfy low < high and low <= mode <= high.")
        else:
            item["value"] = _finite_number(raw.get("value"), f"{name} value")
        normalized.append(item)
    rng = np.random.default_rng(seed)
    draws: dict[str, np.ndarray] = {}
    signed_draws: dict[str, np.ndarray] = {}
    signed_components: list[np.ndarray] = []
    for item in normalized:
        kind = item["distribution"]
        if kind == "normal":
            raw_values = rng.normal(item["mean"], item["sd"], size=iterations)
        elif kind == "uniform":
            raw_values = rng.uniform(item["low"], item["high"], size=iterations)
        elif kind == "triangular":
            raw_values = rng.triangular(item["low"], item["mode"], item["high"], size=iterations)
        else:
            raw_values = np.full(iterations, item["value"], dtype=float)
        direction = 1.0 if item["role"] == "benefit" else -1.0
        draws[item["name"]] = raw_values
        signed_draws[item["name"]] = raw_values * direction
        signed_components.append(raw_values * direction)
    outcomes = np.sum(np.column_stack(signed_components), axis=1)
    percentiles = {str(p): float(np.percentile(outcomes, p)) for p in (1, 5, 25, 50, 75, 95, 99)}
    component_rows = []
    for item in normalized:
        signed = signed_draws[item["name"]]
        if float(np.std(signed)) <= np.finfo(float).eps or float(np.std(outcomes)) <= np.finfo(float).eps:
            correlation = None
        else:
            correlation = float(np.corrcoef(signed, outcomes)[0, 1])
        component_rows.append({
            "Component": item["name"],
            "Role": item["role"].title(),
            "Distribution": item["distribution"],
            "Mean input": float(np.mean(draws[item["name"]])),
            "Standard deviation": float(np.std(draws[item["name"]], ddof=1)) if iterations > 1 else 0.0,
            "Correlation with net outcome (not causal)": correlation,
        })
    checkpoints = sorted(set(min(iterations, max(100, int(iterations * fraction))) for fraction in (0.1, 0.25, 0.5, 0.75, 1.0)))
    convergence = pd.DataFrame([
        {"Trials": n, "Running mean": float(np.mean(outcomes[:n]))}
        for n in checkpoints
    ])
    return {
        "status": "SIMULATION_COMPLETED",
        "iterations": iterations,
        "seed": seed,
        "output_unit": unit_label,
        "mean": float(np.mean(outcomes)),
        "standard_deviation": float(np.std(outcomes, ddof=1)) if iterations > 1 else 0.0,
        "probability_negative_pct": float(100 * np.mean(outcomes < 0)),
        "percentiles": percentiles,
        "component_summary": pd.DataFrame(component_rows),
        "convergence": convergence,
        "sample_outcomes": pd.DataFrame({
            "Trial": np.arange(1, min(iterations, 2000) + 1),
            f"Net outcome ({unit_label})": outcomes[:min(iterations, 2000)],
        }),
        "method": "Independent Monte Carlo sampling; benefits positive, costs negative; NumPy default_rng",
        "assumptions": "Each declared component is sampled independently using its specified distribution. Any dependence/correlation, tax effects, timing/discounting or real-world measurement uncertainty must be modeled separately.",
        "warning": "This simulated net outcome is not verified ROI, audited savings, a forecast guarantee or an automatic plant-control result. It is conditional on user-entered distributions and assumptions.",
    }


def analyze_crossed_gage_rr(
    observations: Sequence[Mapping[str, Any]], *,
    part_field: str = "part",
    operator_field: str = "operator",
    trial_field: str = "trial",
    measurement_field: str = "measurement",
    tolerance: float | None = None,
) -> dict[str, Any]:
    """Estimate crossed, balanced Gage R&R variance components by two-way ANOVA.

    Requires at least 2 parts, 2 operators and 2 repeat trials, with exactly
    one finite measurement per part/operator/trial combination. Components use
    the balanced random-effects ANOVA estimators; negative estimates are
    truncated at zero and explicitly called out in the returned warnings.
    This is a transparent statistical screening method, not a certification
    of an organization's measurement-system procedure.
    """
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence) or not observations:
        raise ValueError("Provide a non-empty list of crossed part/operator/trial measurements.")
    fields = [str(part_field).strip(), str(operator_field).strip(), str(trial_field).strip(), str(measurement_field).strip()]
    if any(not item for item in fields) or len(set(fields)) != 4:
        raise ValueError("Part, operator, trial and measurement field names must be non-empty and distinct.")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(observations, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Observation {index} must be an object.")
        missing = [field for field in fields if field not in item]
        if missing:
            raise ValueError(f"Observation {index} is missing fields: {', '.join(missing)}.")
        part = str(item[part_field]).strip()
        operator = str(item[operator_field]).strip()
        trial = str(item[trial_field]).strip()
        if not part or not operator or not trial:
            raise ValueError(f"Observation {index} must have non-empty part, operator and trial identifiers.")
        key = (part, operator, trial)
        if key in seen:
            raise ValueError(f"Duplicate part/operator/trial observation: {key}.")
        seen.add(key)
        rows.append({
            "part": part, "operator": operator, "trial": trial,
            "measurement": _finite_number(item[measurement_field], f"Measurement {index}"),
        })
    parts = sorted({row["part"] for row in rows})
    operators = sorted({row["operator"] for row in rows})
    trials = sorted({row["trial"] for row in rows})
    p, o, r = len(parts), len(operators), len(trials)
    if p < 2 or o < 2 or r < 2:
        raise ValueError("Crossed Gage R&R needs at least two parts, two operators and two repeat trials.")
    expected_n = p * o * r
    if len(rows) != expected_n:
        raise ValueError("The study must be balanced: every part/operator/trial combination must appear exactly once.")
    frame = pd.DataFrame(rows)
    counts = frame.groupby(["part", "operator"], observed=True)["trial"].nunique()
    if not counts.eq(r).all():
        raise ValueError("The study is not balanced: each part/operator cell needs the same number of trials.")
    grand = float(frame["measurement"].mean())
    part_means = frame.groupby("part", observed=True)["measurement"].mean().reindex(parts)
    operator_means = frame.groupby("operator", observed=True)["measurement"].mean().reindex(operators)
    cell_means = frame.groupby(["part", "operator"], observed=True)["measurement"].mean()
    ss_part = float(o * r * np.sum((part_means.to_numpy(dtype=float) - grand) ** 2))
    ss_operator = float(p * r * np.sum((operator_means.to_numpy(dtype=float) - grand) ** 2))
    ss_interaction = 0.0
    for part in parts:
        for operator in operators:
            cell = float(cell_means.loc[(part, operator)])
            ss_interaction += r * (cell - float(part_means.loc[part]) - float(operator_means.loc[operator]) + grand) ** 2
    ss_repeat = 0.0
    for row in rows:
        cell = float(cell_means.loc[(row["part"], row["operator"])])
        ss_repeat += (row["measurement"] - cell) ** 2
    df_part = p - 1
    df_operator = o - 1
    df_interaction = (p - 1) * (o - 1)
    df_repeat = p * o * (r - 1)
    ms_part = ss_part / df_part
    ms_operator = ss_operator / df_operator
    ms_interaction = ss_interaction / df_interaction
    ms_repeat = ss_repeat / df_repeat
    raw_components = {
        "Repeatability variance": ms_repeat,
        "Part × operator interaction variance": (ms_interaction - ms_repeat) / r,
        "Operator variance": (ms_operator - ms_interaction) / (p * r),
        "Part-to-part variance": (ms_part - ms_interaction) / (o * r),
    }
    truncated = [name for name, value in raw_components.items() if value < 0]
    variance_components = {name: max(0.0, float(value)) for name, value in raw_components.items()}
    grr_variance = (
        variance_components["Repeatability variance"]
        + variance_components["Part × operator interaction variance"]
        + variance_components["Operator variance"]
    )
    part_variance = variance_components["Part-to-part variance"]
    total_variance = grr_variance + part_variance
    if total_variance <= np.finfo(float).eps:
        raise ValueError("No measurable variation was found; variance-component ratios cannot be estimated.")
    tolerance_value = None if tolerance is None else _finite_number(tolerance, "Study tolerance")
    if tolerance_value is not None and tolerance_value <= 0:
        raise ValueError("Study tolerance must be greater than zero when supplied.")
    rows_out: list[dict[str, Any]] = []
    for name in ("Repeatability variance", "Part × operator interaction variance", "Operator variance", "Part-to-part variance"):
        variance = variance_components[name]
        sd = math.sqrt(variance)
        rows_out.append({
            "Component": name,
            "Variance": variance,
            "Standard deviation": sd,
            "% of total variance": variance / total_variance * 100,
            "% of total study variation": sd / math.sqrt(total_variance) * 100,
        })
    component_table = pd.DataFrame(rows_out)
    repeatability_sd = math.sqrt(variance_components["Repeatability variance"])
    reproducibility_sd = math.sqrt(
        variance_components["Operator variance"] + variance_components["Part × operator interaction variance"]
    )
    grr_sd = math.sqrt(grr_variance)
    part_sd = math.sqrt(part_variance)
    table = pd.DataFrame([
        {"Source": "Part", "Sum of squares": ss_part, "df": df_part, "Mean square": ms_part},
        {"Source": "Operator", "Sum of squares": ss_operator, "df": df_operator, "Mean square": ms_operator},
        {"Source": "Part × operator", "Sum of squares": ss_interaction, "df": df_interaction, "Mean square": ms_interaction},
        {"Source": "Repeatability / residual", "Sum of squares": ss_repeat, "df": df_repeat, "Mean square": ms_repeat},
    ])
    warnings = []
    if truncated:
        warnings.append("Negative raw variance-component estimate(s) were truncated at zero: " + ", ".join(truncated) + ". Consider study design and method suitability.")
    if tolerance_value is None:
        pct_tolerance = None
    else:
        pct_tolerance = (6 * grr_sd / tolerance_value) * 100
    ndc = int(math.floor(1.41 * part_sd / grr_sd)) if grr_sd > 0 else None
    return {
        "status": "CROSSED_GAGE_RR_SCREENED",
        "method": "Balanced crossed Gage R&R variance-component screening (two-way random-effects ANOVA)",
        "part_count": p,
        "operator_count": o,
        "repeat_count": r,
        "measurement_count": len(rows),
        "repeatability_sd": repeatability_sd,
        "reproducibility_sd": reproducibility_sd,
        "gage_rr_sd": grr_sd,
        "part_to_part_sd": part_sd,
        "total_study_sd": math.sqrt(total_variance),
        "gage_rr_percent_variance": grr_variance / total_variance * 100,
        "gage_rr_percent_study_variation": grr_sd / math.sqrt(total_variance) * 100,
        "part_percent_variance": part_variance / total_variance * 100,
        "number_of_distinct_categories": ndc,
        "tolerance": tolerance_value,
        "percent_tolerance": pct_tolerance,
        "variance_components": component_table,
        "anova_table": table,
        "negative_component_truncations": truncated,
        "warnings": warnings,
        "assumptions": "Balanced crossed design; parts/operator/trials are represented in every combination. Component estimates use the classical balanced random-effects ANOVA equations and may be unstable with small studies.",
        "warning": "This is a statistical screening result, not automatically a compliant/certified MSA. Confirm the organization's required standard, measurement resolution, part selection, study design, tolerance and acceptance criteria before release decisions.",
    }


def analyze_full_factorial_2level(
    observations: Sequence[Mapping[str, Any]],
    *,
    response_field: str = "response",
    factor_fields: Sequence[str] = (),
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Analyze a complete 2-level factorial with main and pairwise interaction terms.

    Inputs use -1/+1 coded factor values. Every full-factorial combination must
    exist. Effects and regression diagnostics are returned; coefficient
    inference is reported only when residual degrees of freedom and residual
    variance are available. This does not automatically generate a randomized
    run order or cover blocking, center points or higher-order interactions.
    """
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence) or not observations:
        raise ValueError("Provide a non-empty list of factorial run objects.")
    factors = [str(field).strip() for field in factor_fields]
    response = str(response_field).strip()
    if not response or len(factors) < 2 or len(factors) > 6:
        raise ValueError("Choose one response and between two and six factor columns.")
    if len(set(factors)) != len(factors) or response in factors or any(not field for field in factors):
        raise ValueError("Response and factor field names must be distinct and non-empty.")
    level = _finite_number(alpha, "Alpha")
    if not 0 < level < 1:
        raise ValueError("Alpha must be strictly between 0 and 1.")
    names = ["Intercept", *factors]
    term_columns: list[np.ndarray] = [np.ones(len(observations), dtype=float)]
    x_factors: dict[str, np.ndarray] = {}
    y_values: list[float] = []
    for index, row in enumerate(observations, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Run {index} must be an object.")
        for key in [response, *factors]:
            if key not in row:
                raise ValueError(f"Run {index} is missing column '{key}'.")
    for factor in factors:
        values = np.asarray([_finite_number(row[factor], f"{factor} in run {i}") for i, row in enumerate(observations, start=1)], dtype=float)
        unique = set(np.unique(values).tolist())
        if not unique.issubset({-1.0, 1.0}) or not {-1.0, 1.0}.issubset(unique):
            raise ValueError(f"Factor '{factor}' must use both coded levels -1 and +1 only.")
        x_factors[factor] = values
    y_values = [_finite_number(row[response], f"{response} in run {i}") for i, row in enumerate(observations, start=1)]
    combo_counts: dict[tuple[int, ...], int] = {}
    for i in range(len(observations)):
        combination = tuple(int(x_factors[factor][i]) for factor in factors)
        combo_counts[combination] = combo_counts.get(combination, 0) + 1
    expected = set(product((-1, 1), repeat=len(factors)))
    missing = sorted(expected - set(combo_counts))
    if missing:
        raise ValueError(f"Full factorial is incomplete; {len(missing)} factor combination(s) are missing.")
    terms: list[tuple[str, np.ndarray]] = [("Intercept", np.ones(len(observations), dtype=float))]
    for factor in factors:
        terms.append((factor, x_factors[factor]))
    for i, left in enumerate(factors):
        for right in factors[i+1:]:
            terms.append((f"{left} × {right}", x_factors[left] * x_factors[right]))
    names = [term[0] for term in terms]
    x = np.column_stack([term[1] for term in terms])
    y = np.asarray(y_values, dtype=float)
    coefficients, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank != x.shape[1]:
        raise ValueError("The selected factorial model is rank-deficient for these observations.")
    fitted = x @ coefficients
    residuals = y - fitted
    sse = float(np.sum(residuals ** 2))
    grand_mean = float(np.mean(y))
    sst = float(np.sum((y - grand_mean) ** 2))
    df_residual = len(y) - x.shape[1]
    mse = sse / df_residual if df_residual > 0 else None
    covariance = np.linalg.pinv(x.T @ x) * mse if mse is not None and mse > np.finfo(float).eps else None
    term_rows: list[dict[str, Any]] = []
    for i, (name, _) in enumerate(terms):
        if name == "Intercept":
            continue
        coefficient = float(coefficients[i])
        effect = 2.0 * coefficient
        standard_error = None if covariance is None else math.sqrt(max(0.0, float(covariance[i, i])))
        if standard_error is None or standard_error <= np.finfo(float).eps:
            t_stat = None
            p_value = None
        else:
            t_stat = coefficient / standard_error
            p_value = float(2 * t.sf(abs(t_stat), df_residual))
        term_rows.append({
            "Term": name, "Coefficient": coefficient, "Estimated effect (high − low)": effect,
            "Standard error": standard_error, "t statistic": t_stat, "p-value": p_value,
            "Inference available": p_value is not None,
        })
    return {
        "status": "FACTORIAL_ANALYZED",
        "method": "Complete 2-level factorial; OLS with main effects and pairwise interactions",
        "run_count": len(y),
        "factor_count": len(factors),
        "factor_fields": factors,
        "response_field": response,
        "factorial_combinations": len(expected),
        "minimum_replicates_per_combination": min(combo_counts.values()),
        "residual_degrees_of_freedom": df_residual,
        "model_rank": int(rank),
        "r_squared": (1 - sse / sst) if sst > np.finfo(float).eps else None,
        "residual_standard_error": math.sqrt(mse) if mse is not None else None,
        "effects": pd.DataFrame(term_rows).sort_values("Estimated effect (high − low)", key=lambda series: series.abs(), ascending=False).reset_index(drop=True),
        "run_results": pd.DataFrame({
            "Run": np.arange(1, len(y) + 1), "Observed response": y,
            "Fitted response": fitted, "Residual": residuals,
        }),
        "model_coefficients": {name: float(value) for name, value in zip(names, coefficients)},
        "alpha": level,
        "assumptions": "Factors are coded -1/+1; the design contains every full-factorial combination. Classical inference additionally requires appropriate error assumptions and positive residual degrees of freedom; run order randomization must be planned separately.",
        "warning": "The model includes main effects and pairwise interactions only. No blocking, center-point curvature, higher-order interaction screening, multiplicity correction or automatic randomization is included; statistical association is not proof of causation.",
    }


def detect_equipment_anomalies(
    observations: Sequence[Mapping[str, Any]], *,
    timestamp_field: str = "timestamp",
    value_field: str = "value",
    threshold: float = 3.5,
) -> dict[str, Any]:
    """Flag unusual readings with a robust median/MAD score on supplied time-series data.

    This is an offline detector for imported/user-supplied observations. It does
    not provide a live sensor connection, predictive-maintenance model or causal
    diagnosis. When the median and IQR are both zero, non-baseline values are
    flagged as deviations from a stable baseline without fabricating an infinite
    score.
    """
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence) or len(observations) < 8:
        raise ValueError("Provide at least eight time-stamped observations for anomaly screening.")
    timestamp_name = str(timestamp_field or "").strip()
    value_name = str(value_field or "").strip()
    if not timestamp_name or not value_name or timestamp_name == value_name:
        raise ValueError("Timestamp and value field names must be non-empty and distinct.")
    limit = _finite_number(threshold, "Anomaly threshold")
    if not 1.0 <= limit <= 10.0:
        raise ValueError("Anomaly threshold must be between 1.0 and 10.0.")
    records = []
    seen_timestamps: set[pd.Timestamp] = set()
    for i, item in enumerate(observations, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Observation {i} must be an object.")
        if timestamp_name not in item or value_name not in item:
            raise ValueError(f"Observation {i} must contain '{timestamp_name}' and '{value_name}'.")
        timestamp = pd.to_datetime(item[timestamp_name], utc=True, errors="coerce")
        if pd.isna(timestamp):
            raise ValueError(f"Observation {i} has an invalid timestamp.")
        if timestamp in seen_timestamps:
            raise ValueError(f"Duplicate timestamp detected: {timestamp.isoformat()}.")
        seen_timestamps.add(timestamp)
        records.append({"Timestamp": timestamp, "Value": _finite_number(item[value_name], f"Value in observation {i}")})
    frame = pd.DataFrame(records).sort_values("Timestamp").reset_index(drop=True)
    values = frame["Value"].to_numpy(dtype=float)
    median = float(np.median(values))
    deviations = np.abs(values - median)
    mad = float(np.median(deviations))
    iqr = float(np.percentile(values, 75) - np.percentile(values, 25))
    warnings: list[str] = []
    if mad > np.finfo(float).eps:
        score = 0.67448975 * (values - median) / mad
        method = "Robust modified z-score using median absolute deviation"
    elif iqr > np.finfo(float).eps:
        robust_scale = iqr / 1.349
        score = (values - median) / robust_scale
        method = "IQR-scaled robust deviation (MAD was zero)"
        warnings.append("MAD was zero; an IQR-scaled fallback was used. Review distribution shape before applying a maintenance threshold.")
    else:
        score = np.where(deviations > np.finfo(float).eps, np.sign(values - median) * (limit + 1.0), 0.0)
        method = "Stable-baseline deviation fallback (MAD and IQR were zero)"
        warnings.append("Most readings are identical; any distinct reading is flagged as a deviation from the stable baseline. Verify sensor resolution and known operating modes.")
    frame["Robust score"] = score
    frame["Threshold"] = limit
    frame["Anomaly"] = np.abs(score) >= limit
    frame["Deviation from median"] = values - median
    anomaly_rows = frame.loc[frame["Anomaly"]].copy().reset_index(drop=True)
    return {
        "status": "ANOMALIES_SCREENED",
        "method": method,
        "observation_count": len(frame),
        "anomaly_count": len(anomaly_rows),
        "anomaly_rate_pct": float(len(anomaly_rows) / len(frame) * 100),
        "threshold": limit,
        "median_baseline": median,
        "mad": mad,
        "iqr": iqr,
        "latest_observation_utc": frame["Timestamp"].iloc[-1].isoformat(),
        "anomaly_table": anomaly_rows,
        "observations": frame,
        "warnings": warnings,
        "warning": "Offline statistical screening only. This is not a live equipment monitor, diagnosis, calibrated failure predictor or automated maintenance controller. Validate sensor context, operating modes, false positives and source freshness before operational decisions.",
    }


def simulate_mm1_discrete_event(
    arrival_rate_per_time: float,
    service_rate_per_time: float,
    *,
    jobs: int = 5000,
    replications: int = 10,
    warmup_fraction: float = 0.1,
    seed: int = 42,
    time_unit: str = "time units",
) -> dict[str, Any]:
    """Discrete-event FCFS simulation of a single-server M/M/1 queue.

    Inter-arrival and service times are independent exponential random variables.
    The simulator is intentionally limited to one server and one queue; rates,
    seed and warm-up are explicit, and replication summaries are reproducible.
    """
    arrival_rate = _finite_number(arrival_rate_per_time, "Arrival rate")
    service_rate = _finite_number(service_rate_per_time, "Service rate")
    if arrival_rate <= 0 or service_rate <= 0:
        raise ValueError("Arrival and service rates must be greater than zero.")
    if isinstance(jobs, bool) or not isinstance(jobs, int) or not 100 <= jobs <= 200_000:
        raise ValueError("Jobs per replication must be a whole number from 100 through 200000.")
    if isinstance(replications, bool) or not isinstance(replications, int) or not 2 <= replications <= 50:
        raise ValueError("Replications must be a whole number from 2 through 50.")
    warmup = _finite_number(warmup_fraction, "Warm-up fraction")
    if not 0 <= warmup < 0.5:
        raise ValueError("Warm-up fraction must be at least 0 and less than 0.5.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be a non-negative 32-bit integer.")
    unit = str(time_unit or "").strip()
    if not unit or len(unit) > 50:
        raise ValueError("Time unit must be a non-empty label of at most 50 characters.")
    rng = np.random.default_rng(seed)
    warmup_jobs = int(math.floor(jobs * warmup))
    rep_rows: list[dict[str, Any]] = []
    customer_frames: list[pd.DataFrame] = []
    for replication in range(1, replications + 1):
        inter_arrivals = rng.exponential(1.0 / arrival_rate, size=jobs)
        arrivals = np.cumsum(inter_arrivals)
        services = rng.exponential(1.0 / service_rate, size=jobs)
        starts = np.empty(jobs, dtype=float)
        departures = np.empty(jobs, dtype=float)
        starts[0] = arrivals[0]
        departures[0] = starts[0] + services[0]
        for index in range(1, jobs):
            starts[index] = max(arrivals[index], departures[index - 1])
            departures[index] = starts[index] + services[index]
        waiting = starts - arrivals
        sojourn = departures - arrivals
        included = slice(warmup_jobs, jobs)
        start_time = float(arrivals[warmup_jobs])
        end_time = float(departures[-1])
        elapsed = max(end_time - start_time, np.finfo(float).eps)
        # Count service intervals crossing the warm-up boundary as busy time,
        # while still measuring utilization only inside the post-warm-up window.
        clipped_busy = float(np.sum(np.maximum(
            0.0,
            np.minimum(departures, end_time) - np.maximum(starts, start_time),
        )))
        mean_wait = float(np.mean(waiting[included]))
        p95_wait = float(np.percentile(waiting[included], 95))
        mean_sojourn = float(np.mean(sojourn[included]))
        throughput = float((jobs - warmup_jobs) / elapsed)
        utilization = min(1.0, max(0.0, clipped_busy / elapsed))
        rep_rows.append({
            "Replication": replication,
            f"Mean queue wait ({unit})": mean_wait,
            f"P95 queue wait ({unit})": p95_wait,
            f"Mean time in system ({unit})": mean_sojourn,
            "Throughput (jobs / time unit)": throughput,
            "Server utilization (%)": utilization * 100,
            "Customers included after warm-up": jobs - warmup_jobs,
        })
        if replication == 1:
            customer_frames.append(pd.DataFrame({
                "Job": np.arange(1, jobs + 1),
                f"Arrival ({unit})": arrivals,
                f"Service start ({unit})": starts,
                f"Departure ({unit})": departures,
                f"Queue wait ({unit})": waiting,
                f"Time in system ({unit})": sojourn,
                "Warm-up excluded": np.arange(jobs) < warmup_jobs,
            }))
    rep_frame = pd.DataFrame(rep_rows)
    metric_columns = [
        f"Mean queue wait ({unit})", f"P95 queue wait ({unit})",
        f"Mean time in system ({unit})", "Throughput (jobs / time unit)",
        "Server utilization (%)",
    ]
    summary_rows = []
    for metric in metric_columns:
        values = rep_frame[metric].to_numpy(dtype=float)
        mean = float(np.mean(values))
        se = float(np.std(values, ddof=1) / math.sqrt(len(values)))
        margin = float(t.ppf(0.975, len(values) - 1) * se)
        summary_rows.append({
            "Metric": metric,
            "Mean across replications": mean,
            "95% CI lower": mean - margin,
            "95% CI upper": mean + margin,
        })
    warning = "One-server FCFS M/M/1 simulation only; arrivals/services are exponential, independent and identically distributed. No process routing, multiple servers, resource failures, shift calendars or plant data calibration are included."
    stable = arrival_rate < service_rate
    if not stable:
        warning += " Arrival rate is at least the service rate; a stationary queue is not stable and wait/WIP should be interpreted as a finite-horizon overload scenario."
    return {
        "status": "DISCRETE_EVENT_SIMULATED",
        "method": "Single-server FCFS M/M/1 discrete-event simulation with explicit warm-up and independent replications",
        "arrival_rate_per_time": arrival_rate,
        "service_rate_per_time": service_rate,
        "utilization_theoretical_pct": arrival_rate / service_rate * 100,
        "stable_queue": stable,
        "jobs_per_replication": jobs,
        "replications": replications,
        "warmup_fraction": warmup,
        "warmup_jobs_excluded": warmup_jobs,
        "seed": seed,
        "time_unit": unit,
        "replication_summary": rep_frame,
        "metric_summary": pd.DataFrame(summary_rows),
        "sample_customer_events": customer_frames[0].iloc[:min(jobs, 2000)].copy(),
        "warning": warning,
        "assumptions": "Synthetic exponential inter-arrival and service times, FCFS discipline, one server and identical replication settings. Random seed is retained for reproducibility.",
    }


def optimize_supply_chain_network(
    suppliers: Sequence[Mapping[str, Any]],
    sites: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    *,
    unmet_demand_penalty_per_unit: float,
    time_limit_seconds: float = 10.0,
) -> dict[str, Any]:
    """Solve a single-period capacitated transportation model with route disruptions.

    Supply capacities constrain shipments; site demand is either met by routes or
    explicitly reported as unmet demand with a user-declared penalty. Routes marked
    unavailable are disabled, making the same input schema suitable for what-if
    disruption scenarios. This is not a multi-period network design optimizer.
    """
    for group, label in ((suppliers, "Suppliers"), (sites, "Sites"), (routes, "Routes")):
        if isinstance(group, (str, bytes)) or not isinstance(group, Sequence) or not group:
            raise ValueError(f"Provide a non-empty {label.lower()} list.")
    penalty = _finite_number(unmet_demand_penalty_per_unit, "Unmet-demand penalty per unit")
    time_limit = _finite_number(time_limit_seconds, "Solver time limit")
    if penalty <= 0:
        raise ValueError("Unmet-demand penalty must be greater than zero.")
    if not 0.1 <= time_limit <= 120:
        raise ValueError("Solver time limit must be between 0.1 and 120 seconds.")

    def normalize_named_records(records: Sequence[Mapping[str, Any]], name_field: str, quantity_field: str, label: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for i, row in enumerate(records, start=1):
            if not isinstance(row, Mapping):
                raise ValueError(f"{label} row {i} must be an object.")
            name = str(row.get(name_field, "")).strip()
            qty = _finite_number(row.get(quantity_field), f"{label} {name or i} {quantity_field}")
            if not name or name in result:
                raise ValueError(f"{label} names must be non-empty and unique.")
            if qty < 0:
                raise ValueError(f"{label} {name} {quantity_field} cannot be negative.")
            result[name] = qty
        return result

    supply = normalize_named_records(suppliers, "supplier", "supply_capacity", "Supplier")
    demand = normalize_named_records(sites, "site", "demand", "Site")
    route_map: dict[tuple[str, str], dict[str, Any]] = {}
    for i, route in enumerate(routes, start=1):
        if not isinstance(route, Mapping):
            raise ValueError(f"Route row {i} must be an object.")
        source = str(route.get("supplier", "")).strip()
        destination = str(route.get("site", "")).strip()
        if source not in supply or destination not in demand:
            raise ValueError(f"Route {i} references an unknown supplier or site.")
        key = (source, destination)
        if key in route_map:
            raise ValueError(f"Duplicate route found for {source} → {destination}.")
        cost = _finite_number(route.get("unit_cost"), f"Route {source} → {destination} unit cost")
        capacity = _finite_number(route.get("capacity"), f"Route {source} → {destination} capacity")
        if cost < 0 or capacity < 0:
            raise ValueError("Route cost and capacity cannot be negative.")
        available = route.get("available", True)
        if not isinstance(available, bool):
            raise ValueError(f"Route {source} → {destination} available flag must be boolean.")
        route_map[key] = {"unit_cost": cost, "capacity": capacity, "available": available}

    model = pulp.LpProblem("shoir_single_period_supply_chain_transport", pulp.LpMinimize)
    shipment_vars = {
        key: pulp.LpVariable(f"ship_{i}", lowBound=0, upBound=item["capacity"] if item["available"] else 0)
        for i, (key, item) in enumerate(route_map.items(), start=1)
    }
    unmet_vars = {
        site: pulp.LpVariable(f"unmet_{i}", lowBound=0)
        for i, site in enumerate(demand, start=1)
    }
    model += pulp.lpSum(route_map[key]["unit_cost"] * shipment_vars[key] for key in route_map) + penalty * pulp.lpSum(unmet_vars.values())
    for supplier, capacity in supply.items():
        model += pulp.lpSum(
            var for (source, _), var in shipment_vars.items() if source == supplier
        ) <= capacity, f"supplier_capacity_{list(supply).index(supplier)}"
    for site, requested in demand.items():
        model += pulp.lpSum(
            var for (_, destination), var in shipment_vars.items() if destination == site
        ) + unmet_vars[site] == requested, f"site_demand_{list(demand).index(site)}"
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit)
    try:
        model.solve(solver)
    except Exception as exc:
        return {
            "status": "SOLVER_ERROR",
            "solver_status": "ERROR",
            "error": f"Supply chain solver could not execute ({type(exc).__name__}). Check the packaged solver and model inputs.",
            "warning": "No optimal solution is claimed when the solver could not run.",
        }
    status = str(pulp.LpStatus.get(model.status, "Unknown"))
    if status not in {"Optimal", "Not Solved", "Undefined", "Infeasible", "Unbounded"}:
        status = "Unknown"
    if status != "Optimal":
        return {
            "status": status.upper().replace(" ", "_"),
            "solver_status": status,
            "warning": "A proven optimal solution was not returned; inspect solver availability, model size and time limits before using any plan.",
        }
    shipment_rows = []
    for key, variable in shipment_vars.items():
        amount = max(0.0, float(variable.value() or 0.0))
        item = route_map[key]
        shipment_rows.append({
            "Supplier": key[0], "Site": key[1], "Units shipped": amount,
            "Unit transport cost": item["unit_cost"], "Route capacity": item["capacity"],
            "Route available": item["available"], "Transport cost": amount * item["unit_cost"],
        })
    site_rows = []
    for site, requested in demand.items():
        shipped = sum(row["Units shipped"] for row in shipment_rows if row["Site"] == site)
        missing = max(0.0, requested - shipped)
        site_rows.append({
            "Site": site, "Demand": requested, "Units supplied": shipped,
            "Unmet demand": missing, "Service level (%)": (shipped / requested * 100) if requested > 0 else 100.0,
        })
    supplier_rows = []
    for supplier, capacity in supply.items():
        shipped = sum(row["Units shipped"] for row in shipment_rows if row["Supplier"] == supplier)
        supplier_rows.append({"Supplier": supplier, "Supply capacity": capacity, "Units shipped": shipped, "Unused capacity": max(0.0, capacity - shipped)})
    shipments = pd.DataFrame(shipment_rows)
    site_frame = pd.DataFrame(site_rows)
    supplier_frame = pd.DataFrame(supplier_rows)
    return {
        "status": "OPTIMAL",
        "solver_status": status,
        "transport_cost": float(shipments["Transport cost"].sum()) if not shipments.empty else 0.0,
        "total_unmet_demand": float(site_frame["Unmet demand"].sum()),
        "unmet_demand_penalty_per_unit": penalty,
        "objective_cost_including_unmet_penalty": float(pulp.value(model.objective) or 0.0),
        "total_demand": float(site_frame["Demand"].sum()),
        "total_supply_capacity": float(supplier_frame["Supply capacity"].sum()),
        "total_units_shipped": float(shipments["Units shipped"].sum()),
        "shipment_plan": shipments,
        "site_service": site_frame,
        "supplier_utilization": supplier_frame,
        "method": "Single-period capacitated transportation LP; route availability is a scenario input and unmet demand receives an explicit penalty.",
        "warning": "This is a single-period transport optimization, not a multi-echelon or time-phased network design model. Verify route capacity, transport unit costs, sourcing restrictions, delivery times, emissions and supplier risks before commitment.",
    }


def simulate_discrete_event_process(
    process_steps: Sequence[Mapping[str, Any]],
    *,
    job_count: int,
    mean_interarrival_time: float,
    arrival_distribution: str = "deterministic",
    warmup_jobs: int = 0,
    replications: int = 1,
    random_seed: int = 42,
    time_unit: str = "minutes",
) -> dict[str, Any]:
    """Run an event-driven FCFS production route with finite servers and replications.

    Supported interarrival/service distributions are deterministic or exponential.
    Each job follows the declared station order; each station uses FCFS queues and
    a fixed number of identical parallel servers. This intentionally does not claim
    to model failures, setups, alternate routing, priorities or shared labor pools.
    """
    import heapq
    import random
    from collections import deque

    if isinstance(process_steps, (str, bytes)) or not isinstance(process_steps, Sequence) or not process_steps:
        raise ValueError("Provide at least one process-station record.")
    if isinstance(job_count, bool) or not isinstance(job_count, int) or not 2 <= job_count <= 10000:
        raise ValueError("Job count must be a whole number from 2 through 10,000.")
    if isinstance(warmup_jobs, bool) or not isinstance(warmup_jobs, int) or not 0 <= warmup_jobs < job_count:
        raise ValueError("Warm-up jobs must be a whole number from zero up to job_count minus one.")
    if isinstance(replications, bool) or not isinstance(replications, int) or not 1 <= replications <= 100:
        raise ValueError("Replications must be a whole number from 1 through 100.")
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("Random seed must be a whole number.")
    unit = str(time_unit or "").strip()
    if not unit:
        raise ValueError("A time unit is required.")
    interarrival_mean = _finite_number(mean_interarrival_time, "Mean interarrival time")
    if interarrival_mean <= 0:
        raise ValueError("Mean interarrival time must be greater than zero.")
    arrival_dist = str(arrival_distribution or "").strip().lower()
    if arrival_dist not in {"deterministic", "exponential"}:
        raise ValueError("Arrival distribution must be deterministic or exponential.")

    stations: list[dict[str, Any]] = []
    station_names: set[str] = set()
    for index, raw in enumerate(process_steps, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Process station row {index} must be an object.")
        name = str(raw.get("station", raw.get("name", ""))).strip()
        if not name:
            raise ValueError(f"Process station row {index} needs a station name.")
        if name.casefold() in station_names:
            raise ValueError(f"Station names must be unique; duplicate: {name}.")
        station_names.add(name.casefold())
        servers = raw.get("servers", 1)
        if isinstance(servers, bool) or not isinstance(servers, int) or not 1 <= servers <= 100:
            raise ValueError(f"Server count for station '{name}' must be a whole number from 1 through 100.")
        mean_service = _finite_number(raw.get("mean_service_time"), f"Mean service time for {name}")
        if mean_service <= 0:
            raise ValueError(f"Mean service time for station '{name}' must be greater than zero.")
        distribution = str(raw.get("service_distribution", "deterministic")).strip().lower()
        if distribution not in {"deterministic", "exponential"}:
            raise ValueError(f"Service distribution for '{name}' must be deterministic or exponential.")
        stations.append({
            "name": name,
            "servers": servers,
            "mean_service_time": mean_service,
            "service_distribution": distribution,
        })

    retained_count = job_count - warmup_jobs
    replication_rows: list[dict[str, Any]] = []
    station_rows: list[dict[str, Any]] = []

    for replication_index in range(replications):
        seed = random_seed + replication_index
        rng = random.Random(seed)
        arrival_times = [0.0]
        for _ in range(1, job_count):
            if arrival_dist == "deterministic":
                interval = interarrival_mean
            else:
                interval = rng.expovariate(1.0 / interarrival_mean)
            arrival_times.append(arrival_times[-1] + interval)

        records = [{
            "job_id": job_id,
            "arrival_time": arrival_times[job_id],
            "station_waits": [0.0] * len(stations),
            "station_service": [0.0] * len(stations),
            "completion_time": None,
        } for job_id in range(job_count)]
        runtime = [{
            "queue": deque(),
            "busy_servers": 0,
            "busy_time": 0.0,
            "waits_by_job": {},
        } for _ in stations]
        events: list[tuple[float, int, int, str, tuple[Any, ...]]] = []
        sequence = 0

        def schedule(event_time: float, priority: int, event_name: str, payload: tuple[Any, ...]) -> None:
            nonlocal sequence
            heapq.heappush(events, (event_time, priority, sequence, event_name, payload))
            sequence += 1

        def start_queued_jobs(station_index: int, event_time: float) -> None:
            station = stations[station_index]
            state = runtime[station_index]
            while state["busy_servers"] < station["servers"] and state["queue"]:
                job_id, queue_arrival = state["queue"].popleft()
                waiting = max(0.0, event_time - queue_arrival)
                service_mean = station["mean_service_time"]
                if station["service_distribution"] == "deterministic":
                    service_time = service_mean
                else:
                    service_time = rng.expovariate(1.0 / service_mean)
                records[job_id]["station_waits"][station_index] = waiting
                records[job_id]["station_service"][station_index] = service_time
                state["waits_by_job"][job_id] = waiting
                state["busy_servers"] += 1
                schedule(
                    event_time + service_time,
                    0,
                    "service_complete",
                    (job_id, station_index, service_time),
                )

        # Arrivals are discrete events; service completions have priority at tied times.
        for job_id, event_time in enumerate(arrival_times):
            schedule(event_time, 1, "station_arrival", (job_id, 0, event_time))

        while events:
            event_time, _priority, _sequence, event_name, payload = heapq.heappop(events)
            if event_name == "station_arrival":
                job_id, station_index, _arrival_time = payload
                runtime[station_index]["queue"].append((job_id, event_time))
                start_queued_jobs(station_index, event_time)
                continue

            job_id, station_index, service_time = payload
            state = runtime[station_index]
            state["busy_servers"] -= 1
            state["busy_time"] += service_time
            next_station = station_index + 1
            if next_station < len(stations):
                schedule(event_time, 1, "station_arrival", (job_id, next_station, event_time))
            else:
                records[job_id]["completion_time"] = event_time
            start_queued_jobs(station_index, event_time)

        retained = records[warmup_jobs:]
        if any(record["completion_time"] is None for record in retained):
            raise RuntimeError("Simulation ended with an incomplete retained job.")
        makespan = max(float(record["completion_time"]) for record in records)
        observation_start = float(retained[0]["arrival_time"])
        observation_end = max(float(record["completion_time"]) for record in retained)
        observation_duration = observation_end - observation_start
        if observation_duration <= 0 or not math.isfinite(observation_duration):
            raise RuntimeError("Simulation produced a non-positive observation duration.")

        flow_times = [float(r["completion_time"]) - float(r["arrival_time"]) for r in retained]
        total_waits = [sum(float(v) for v in r["station_waits"]) for r in retained]
        total_service = [sum(float(v) for v in r["station_service"]) for r in retained]
        replication_rows.append({
            "Replication": replication_index + 1,
            "Seed": seed,
            "Retained jobs": retained_count,
            f"Observation duration ({unit})": observation_duration,
            f"Throughput (jobs/{unit})": retained_count / observation_duration,
            f"Average flow time ({unit})": float(np.mean(flow_times)),
            f"Average total queue wait ({unit})": float(np.mean(total_waits)),
            f"Average total service time ({unit})": float(np.mean(total_service)),
            "Jobs with queue wait (%)": float(np.mean([value > 1e-12 for value in total_waits]) * 100.0),
            f"Simulation makespan ({unit})": makespan,
        })

        denominator = makespan
        for station_index, station in enumerate(stations):
            waits = [float(r["station_waits"][station_index]) for r in retained]
            services = [float(r["station_service"][station_index]) for r in retained]
            station_rows.append({
                "Replication": replication_index + 1,
                "Station": station["name"],
                "Servers": station["servers"],
                f"Mean service input ({unit})": station["mean_service_time"],
                f"Average retained-job queue wait ({unit})": float(np.mean(waits)),
                f"Average retained-job service time ({unit})": float(np.mean(services)),
                "Utilization across all simulated jobs (%)": (
                    float(runtime[station_index]["busy_time"]) / (denominator * station["servers"]) * 100.0
                    if denominator > 0 else 0.0
                ),
                f"Total station busy time ({unit})": float(runtime[station_index]["busy_time"]),
            })

    replication_frame = pd.DataFrame(replication_rows)
    station_frame = pd.DataFrame(station_rows)
    metric_columns = [
        f"Throughput (jobs/{unit})",
        f"Average flow time ({unit})",
        f"Average total queue wait ({unit})",
        f"Average total service time ({unit})",
        "Jobs with queue wait (%)",
    ]
    metric_summary = []
    for column in metric_columns:
        values = replication_frame[column].astype(float).to_numpy()
        metric_summary.append({
            "Metric": column,
            "Mean across replications": float(np.mean(values)),
            "P05 across replications": float(np.percentile(values, 5)),
            "P95 across replications": float(np.percentile(values, 95)),
        })

    station_summary_rows = []
    for station_name, group in station_frame.groupby("Station", sort=False):
        util = group["Utilization across all simulated jobs (%)"].astype(float).to_numpy()
        wait_col = f"Average retained-job queue wait ({unit})"
        station_summary_rows.append({
            "Station": station_name,
            "Servers": int(group["Servers"].iloc[0]),
            f"Average queue wait ({unit})": float(group[wait_col].mean()),
            "Mean utilization across replications (%)": float(np.mean(util)),
            "P05 utilization (%)": float(np.percentile(util, 5)),
            "P95 utilization (%)": float(np.percentile(util, 95)),
        })

    return {
        "status": "DISCRETE_EVENT_SIMULATION_COMPLETED",
        "method": "Event-driven FCFS serial process route with finite parallel servers; deterministic or exponential interarrivals/service times; independent seeded replications.",
        "job_count": job_count,
        "warmup_jobs_excluded_from_performance_metrics": warmup_jobs,
        "replications": replications,
        "base_random_seed": random_seed,
        "arrival_distribution": arrival_dist,
        "station_count": len(stations),
        "time_unit": unit,
        "metric_summary": pd.DataFrame(metric_summary),
        "replication_results": replication_frame,
        "station_summary": pd.DataFrame(station_summary_rows),
        "station_replication_details": station_frame,
        "limitations": [
            "Every job follows the stations in the supplied order and queues FCFS; alternate routing, priorities, setups, breakdowns, rework and shared labor resources are not modeled.",
            "Warm-up is excluded by dropping the first N completed job IDs from performance metrics; it is not a time-based warm-up deletion.",
            "Utilization includes all simulated jobs, including warm-up jobs. Service-time distributions are limited to deterministic and exponential.",
            "Simulation outputs are model-derived; calibrate process assumptions against measured data and validate before operational decisions.",
        ],
        "data_provenance": "USER_ENTERED_UNVERIFIED",
    }


def run_solver_diagnostics(
    variable_spec: Mapping[str, Mapping[str, Any]],
    objective_coefficients: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
    *,
    direction: str = "minimize",
    time_limit_seconds: float = 10.0,
    feasibility_tolerance: float = 1e-7,
) -> dict[str, Any]:
    """Build and solve a bounded/continuous-or-integer linear model and audit its solution.

    Supported variable categories are Continuous, Integer and Binary. This is a
    compact LP/MILP diagnostics runner: it reports the actual solver termination
    state and independently recomputes variable-bound and constraint violations.
    It does not infer an IIS or claim an optimal result from a merely feasible
    time-limited incumbent.
    """
    if not isinstance(variable_spec, Mapping) or not variable_spec:
        raise ValueError("Provide a non-empty JSON object of variable specifications.")
    if not isinstance(objective_coefficients, Mapping) or not objective_coefficients:
        raise ValueError("Provide a non-empty objective coefficient object.")
    if isinstance(constraints, (str, bytes)) or not isinstance(constraints, Sequence):
        raise ValueError("Constraints must be a JSON list of constraint records.")
    direction_value = str(direction or "").strip().lower()
    if direction_value not in {"minimize", "min", "maximize", "max"}:
        raise ValueError("Objective direction must be minimize or maximize.")
    time_limit = _finite_number(time_limit_seconds, "Solver time limit")
    if not 0.1 <= time_limit <= 300:
        raise ValueError("Solver time limit must be between 0.1 and 300 seconds.")
    tolerance = _finite_number(feasibility_tolerance, "Feasibility tolerance")
    if not 1e-10 <= tolerance <= 1e-2:
        raise ValueError("Feasibility tolerance must be between 1e-10 and 0.01.")

    normalized_specs: dict[str, dict[str, Any]] = {}
    for raw_name, raw_spec in variable_spec.items():
        name = str(raw_name).strip()
        if not name or name in normalized_specs:
            raise ValueError("Variable names must be non-empty and unique.")
        if not isinstance(raw_spec, Mapping):
            raise ValueError(f"Variable specification for '{name}' must be an object.")
        category = str(raw_spec.get("category", "Continuous")).strip().lower()
        categories = {"continuous": pulp.LpContinuous, "integer": pulp.LpInteger, "binary": pulp.LpBinary}
        if category not in categories:
            raise ValueError(f"Variable '{name}' category must be Continuous, Integer or Binary.")
        low_raw, high_raw = raw_spec.get("low", 0), raw_spec.get("up")
        low = None if low_raw is None or str(low_raw).strip() == "" else _finite_number(low_raw, f"Lower bound for {name}")
        high = None if high_raw is None or str(high_raw).strip() == "" else _finite_number(high_raw, f"Upper bound for {name}")
        if low is not None and high is not None and low > high:
            raise ValueError(f"Lower bound exceeds upper bound for variable '{name}'.")
        if category == "binary":
            if (low is not None and low > 0) or (high is not None and high < 1):
                raise ValueError(f"Binary variable '{name}' bounds must allow values 0 and/or 1.")
            low, high = 0.0, 1.0
        normalized_specs[name] = {"low": low, "up": high, "category": category, "pulp_category": categories[category]}

    objective: dict[str, float] = {}
    for raw_name, raw_coeff in objective_coefficients.items():
        name = str(raw_name).strip()
        if name not in normalized_specs:
            raise ValueError(f"Objective references unknown variable '{name}'.")
        objective[name] = _finite_number(raw_coeff, f"Objective coefficient for {name}")
    if not objective:
        raise ValueError("At least one objective coefficient is required.")

    normalized_constraints: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for index, raw in enumerate(constraints, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Constraint row {index} must be an object.")
        name = str(raw.get("name", f"constraint_{index}")).strip() or f"constraint_{index}"
        if name.casefold() in used_names:
            raise ValueError(f"Constraint names must be unique; duplicate: {name}.")
        used_names.add(name.casefold())
        coefficients_raw = raw.get("coefficients")
        if not isinstance(coefficients_raw, Mapping) or not coefficients_raw:
            raise ValueError(f"Constraint '{name}' needs a non-empty coefficients object.")
        coefficients: dict[str, float] = {}
        for raw_var, raw_coeff in coefficients_raw.items():
            var_name = str(raw_var).strip()
            if var_name not in normalized_specs:
                raise ValueError(f"Constraint '{name}' references unknown variable '{var_name}'.")
            coefficients[var_name] = _finite_number(raw_coeff, f"Coefficient of {var_name} in constraint {name}")
        sense_raw = str(raw.get("sense", "<=")).strip()
        senses = {"<=": pulp.LpConstraintLE, "≤": pulp.LpConstraintLE, ">=": pulp.LpConstraintGE, "≥": pulp.LpConstraintGE, "=": pulp.LpConstraintEQ, "==": pulp.LpConstraintEQ}
        if sense_raw not in senses:
            raise ValueError(f"Constraint '{name}' sense must be <=, >= or ==.")
        rhs = _finite_number(raw.get("rhs"), f"Right-hand side for constraint {name}")
        normalized_constraints.append({"name": name, "coefficients": coefficients, "sense": senses[sense_raw], "sense_label": sense_raw, "rhs": rhs})

    problem = pulp.LpProblem(
        "ShoirIE_Solver_Diagnostics",
        pulp.LpMinimize if direction_value in {"minimize", "min"} else pulp.LpMaximize,
    )
    variables = {
        name: pulp.LpVariable(name, lowBound=spec["low"], upBound=spec["up"], cat=spec["pulp_category"])
        for name, spec in normalized_specs.items()
    }
    problem += pulp.lpSum(coefficient * variables[name] for name, coefficient in objective.items()), "objective"
    for item in normalized_constraints:
        expression = pulp.lpSum(coefficient * variables[name] for name, coefficient in item["coefficients"].items())
        if item["sense"] == pulp.LpConstraintLE:
            problem += expression <= item["rhs"], item["name"]
        elif item["sense"] == pulp.LpConstraintGE:
            problem += expression >= item["rhs"], item["name"]
        else:
            problem += expression == item["rhs"], item["name"]

    try:
        solver_status_code = problem.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit))
    except Exception as exc:
        return {
            "status": "SOLVER_ERROR",
            "solver_status": "SOLVER_ERROR",
            "solver_message": f"{type(exc).__name__}: {str(exc)[:400]}",
            "objective_value": None,
            "variable_values": pd.DataFrame(columns=["Variable", "Value", "Category", "Lower bound", "Upper bound", "Bound status"]),
            "constraint_diagnostics": pd.DataFrame(columns=["Constraint", "Relation", "Right-hand side", "LHS value", "Violation", "Status"]),
            "warnings": ["The model was validated, but the configured CBC solver did not return a result; do not use a prior result as if this run succeeded."],
            "data_provenance": "USER_ENTERED_UNVERIFIED",
        }

    solver_status = pulp.LpStatus.get(solver_status_code, f"UNKNOWN_STATUS_{solver_status_code}")
    solution_status_code = getattr(problem, "sol_status", None)
    solution_status = pulp.LpSolution.get(solution_status_code, "UNKNOWN_SOLUTION_STATUS")
    variable_rows: list[dict[str, Any]] = []
    violations: list[str] = []
    all_values_assigned = True
    all_bounds_ok = True

    for name, variable in variables.items():
        raw_value = variable.varValue
        value = None if raw_value is None else float(raw_value)
        spec = normalized_specs[name]
        bound_violation = 0.0
        if value is None or not math.isfinite(value):
            all_values_assigned = False
            all_bounds_ok = False
            bound_status = "NO_FINITE_VALUE"
            violations.append(f"{name}: no finite solution value")
        else:
            if spec["low"] is not None:
                bound_violation = max(bound_violation, float(spec["low"]) - value)
            if spec["up"] is not None:
                bound_violation = max(bound_violation, value - float(spec["up"]))
            if spec["category"] in {"integer", "binary"}:
                bound_violation = max(bound_violation, abs(value - round(value)))
            bound_violation = max(0.0, bound_violation)
            if bound_violation > tolerance:
                all_bounds_ok = False
                bound_status = "VIOLATED"
                violations.append(f"{name}: bound/integrality violation {bound_violation:g}")
            else:
                bound_status = "SATISFIED"
        variable_rows.append({
            "Variable": name,
            "Value": value,
            "Category": spec["category"],
            "Lower bound": spec["low"],
            "Upper bound": spec["up"],
            "Bound violation": bound_violation,
            "Bound status": bound_status,
        })

    constraint_rows: list[dict[str, Any]] = []
    all_constraints_ok = True
    for item in normalized_constraints:
        # Recompute the left-hand side independently from the original model
        # coefficients rather than trusting the solver's residual bookkeeping.
        lhs_value = None
        if all_values_assigned:
            lhs_value = sum(float(item["coefficients"][name]) * float(variables[name].varValue) for name in item["coefficients"])
            if item["sense"] == pulp.LpConstraintLE:
                violation = max(0.0, lhs_value - item["rhs"])
            elif item["sense"] == pulp.LpConstraintGE:
                violation = max(0.0, item["rhs"] - lhs_value)
            else:
                violation = abs(lhs_value - item["rhs"])
            status = "SATISFIED" if violation <= tolerance else "VIOLATED"
        else:
            violation = None
            status = "NO_FINITE_CANDIDATE"
        if violation is None or violation > tolerance:
            all_constraints_ok = False
            if violation is not None:
                violations.append(f"{item['name']}: constraint violation {violation:g}")
        constraint_rows.append({
            "Constraint": item["name"],
            "Relation": item["sense_label"],
            "Right-hand side": item["rhs"],
            "LHS value": lhs_value,
            "Violation": violation,
            "Status": status,
        })

    complete_feasible_candidate = all_values_assigned and all_bounds_ok and all_constraints_ok
    objective_value = None
    if complete_feasible_candidate:
        obj = pulp.value(problem.objective)
        if obj is not None and math.isfinite(float(obj)):
            objective_value = float(obj)

    if solver_status == "Infeasible":
        interpretation_status = "INFEASIBLE"
        warnings = ["The solver reported infeasibility; no feasible decision should be inferred from any leftover variable values."]
        objective_value = None
    elif solver_status == "Unbounded":
        interpretation_status = "UNBOUNDED"
        warnings = ["The solver reported an unbounded objective; review missing bounds, sign conventions and formulation before using the model."]
        objective_value = None
    elif solver_status == "Optimal" and complete_feasible_candidate and objective_value is not None:
        interpretation_status = "OPTIMAL_FEASIBLE"
        warnings = []
    elif complete_feasible_candidate and solver_status not in {"Infeasible", "Unbounded", "Undefined"}:
        interpretation_status = "FEASIBLE_NOT_PROVEN_OPTIMAL"
        warnings = ["A feasible candidate exists, but optimality has not been proven by the solver status."]
    else:
        interpretation_status = "NO_VERIFIED_FEASIBLE_SOLUTION"
        warnings = ["No independently verified feasible candidate was found; inspect solver status and listed violations."]
    if violations:
        warnings.append("One or more variable or constraint residual checks failed; see the diagnostic tables.")

    return {
        "status": interpretation_status,
        "solver_status": solver_status,
        "solution_status": solution_status,
        "objective_direction": "minimize" if direction_value in {"minimize", "min"} else "maximize",
        "objective_value": objective_value,
        "variable_count": len(variables),
        "constraint_count": len(normalized_constraints),
        "feasibility_tolerance": tolerance,
        "time_limit_seconds": time_limit,
        "variable_values": pd.DataFrame(variable_rows),
        "constraint_diagnostics": pd.DataFrame(constraint_rows),
        "independent_feasibility_check": bool(complete_feasible_candidate),
        "violations": violations,
        "warnings": warnings,
        "limitations": [
            "Only a linear objective and linear constraints are supported; variable categories are Continuous, Integer and Binary.",
            "An infeasibility explanation/IIS is not generated. The returned residual checks validate a candidate but do not prove model correctness or completeness.",
            "A time-limited feasible incumbent is explicitly not labeled optimal unless the solver reports Optimal.",
        ],
        "data_provenance": "USER_ENTERED_UNVERIFIED",
    }


def build_reproducibility_pack(
    tool_id: str,
    canonical_name: str,
    result: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    include_input_snapshot: bool = False,
    include_result_tables: bool = False,
    max_payload_bytes: int = 20_000_000,
) -> dict[str, Any]:
    """Create a provenance ZIP with hashes, version metadata and optional sanitized inputs/tables.

    Secrets and common credential/PII-bearing fields are redacted. Raw input values
    and detailed result tables are opt-in. The pack records a SHA-256 fingerprint
    even when the raw input snapshot is intentionally not included. This is an
    evidence/reproducibility artifact, not a formal proof or certification.
    """
    import hashlib
    import importlib.metadata
    import io
    import json
    import platform
    import re
    import sys
    import zipfile
    from datetime import datetime, timezone

    target_id = str(tool_id or "").strip().upper()
    if not re.fullmatch(r"T\d{3}", target_id) or not 1 <= int(target_id[1:]) <= 100:
        raise ValueError("Tool ID must use a canonical T001–T100 identifier.")
    name = str(canonical_name or "").strip()
    if not name:
        raise ValueError("A canonical tool name is required.")
    if not isinstance(result, Mapping):
        raise ValueError("A completed result object is required to build a reproducibility pack.")
    if inputs is not None and not isinstance(inputs, Mapping):
        raise ValueError("Inputs must be a JSON-compatible object.")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("Metadata must be a JSON-compatible object.")
    if isinstance(max_payload_bytes, bool) or not isinstance(max_payload_bytes, int) or not 1024 <= max_payload_bytes <= 100_000_000:
        raise ValueError("Maximum payload bytes must be an integer between 1,024 and 100,000,000.")

    sensitive_key = re.compile(
        r"(?:password|passphrase|secret|token|authorization|cookie|api[_ -]?key|service[_ -]?role|"
        r"private[_ -]?key|connection[_ -]?string|database[_ -]?url|email|phone|mobile|national[_ -]?id|"
        r"passport|ssn|access[_ -]?key|refresh[_ -]?token|employee[_ -]?name|person[_ -]?name|"
        r"customer[_ -]?contact|contact[_ -]?name|operator[_ -]?name)",
        re.IGNORECASE,
    )
    sensitive_column = re.compile(
        r"(?:password|passphrase|secret|token|authorization|cookie|api[_ -]?key|service[_ -]?role|"
        r"private[_ -]?key|connection[_ -]?string|database[_ -]?url|email|e_mail|phone|mobile|national[_ -]?id|"
        r"passport|ssn|access[_ -]?key|refresh[_ -]?token|employee[_ -]?name|person[_ -]?name|"
        r"customer[_ -]?contact|contact[_ -]?name|operator[_ -]?name)",
        re.IGNORECASE,
    )
    secret_text = re.compile(
        r"(?i)\b(password|passphrase|secret|token|api[_ -]?key|service[_ -]?role[_ -]?key|access[_ -]?key)\b(\s*[:=]\s*)([^\s,;]+)|\bBearer\s+[A-Za-z0-9._~+/-]+=*"
    )

    def _replace_secret_text(match: Any) -> str:
        if match.group(1) is not None:
            return f"{match.group(1)}{match.group(2) or ''}[REDACTED]"
        return "Bearer [REDACTED]"

    def _safe_string(raw: Any) -> str:
        value = str(raw)
        value = secret_text.sub(_replace_secret_text, value)
        # Remove userinfo from a URL while retaining scheme and host for diagnostics.
        value = re.sub(r"(?i)(https?|postgres(?:ql)?|mysql)://[^/@\s:]+(?::[^/@\s]*)?@", r"\1://[REDACTED]@", value)
        return value[:5000]

    def _normalise(value: Any, *, prefix: str, files: dict[str, bytes], include_tables: bool, depth: int = 0) -> Any:
        if depth > 12:
            raise ValueError("The result is nested too deeply to package safely.")
        if value is None or isinstance(value, (bool, int, str)):
            return _safe_string(value) if isinstance(value, str) else value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, Mapping):
            clean: dict[str, Any] = {}
            for raw_key, raw_value in value.items():
                key = _safe_string(raw_key)
                if sensitive_key.search(key):
                    clean[key] = "[REDACTED]"
                else:
                    clean[key] = _normalise(
                        raw_value, prefix=f"{prefix}_{re.sub(r'[^A-Za-z0-9_-]+', '_', key)[:40]}",
                        files=files, include_tables=include_tables, depth=depth + 1,
                    )
            return clean
        if isinstance(value, (list, tuple, set)):
            return [
                _normalise(item, prefix=f"{prefix}_{index + 1}", files=files, include_tables=include_tables, depth=depth + 1)
                for index, item in enumerate(list(value))
            ]
        if isinstance(value, pd.DataFrame):
            columns = [str(col) for col in value.columns]
            row_count = int(len(value))
            if include_tables:
                safe_frame = value.copy()
                redacted_columns: list[str] = []
                for col in columns:
                    if sensitive_column.search(col):
                        safe_frame[col] = "[REDACTED]"
                        redacted_columns.append(col)
                table_name = "tables/" + (re.sub(r"[^A-Za-z0-9_-]+", "_", prefix).strip("_") or "result")[:100] + ".csv"
                payload = safe_frame.to_csv(index=False).encode("utf-8")
                if len(payload) > max_payload_bytes:
                    raise ValueError(f"Table {prefix} exceeds the configured {max_payload_bytes:,}-byte payload limit.")
                if table_name in files:
                    suffix = hashlib.sha256(payload).hexdigest()[:8]
                    table_name = table_name.removesuffix(".csv") + "_" + suffix + ".csv"
                files[table_name] = payload
                return {
                    "artifact_type": "csv_table",
                    "path": table_name,
                    "row_count": row_count,
                    "columns": columns,
                    "redacted_columns": redacted_columns,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            return {
                "artifact_type": "omitted_table_metadata",
                "row_count": row_count,
                "columns": columns,
                "sha256": hashlib.sha256(value.to_csv(index=False).encode("utf-8")).hexdigest(),
                "note": "Table values are not embedded; enable detailed result tables to include sanitized CSVs.",
            }
        if isinstance(value, pd.Series):
            return _normalise(value.to_dict(), prefix=prefix, files=files, include_tables=include_tables, depth=depth + 1)
        if isinstance(value, np.ndarray):
            return _normalise(value.tolist(), prefix=prefix, files=files, include_tables=include_tables, depth=depth + 1)
        if isinstance(value, np.generic):
            return _normalise(value.item(), prefix=prefix, files=files, include_tables=include_tables, depth=depth + 1)
        if hasattr(value, "isoformat") and callable(value.isoformat):
            try:
                return value.isoformat()
            except Exception:
                pass
        if isinstance(value, bytes):
            return {"artifact_type": "binary_omitted", "byte_count": len(value), "sha256": hashlib.sha256(value).hexdigest()}
        return _safe_string(value)

    files: dict[str, bytes] = {}
    result_content = _normalise(
        result, prefix=target_id.lower(), files=files, include_tables=include_result_tables
    )
    result_payload = json.dumps(result_content, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    if len(result_payload) > max_payload_bytes:
        raise ValueError(f"Result summary exceeds the configured {max_payload_bytes:,}-byte payload limit.")
    files["result_summary.json"] = result_payload

    input_object = dict(inputs or {})
    safe_inputs = _normalise(
        input_object, prefix="inputs", files=files, include_tables=False
    )
    input_payload = json.dumps(safe_inputs, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    input_fingerprint = hashlib.sha256(input_payload).hexdigest()
    if include_input_snapshot:
        if len(input_payload) > max_payload_bytes:
            raise ValueError(f"Input snapshot exceeds the configured {max_payload_bytes:,}-byte payload limit.")
        files["input_snapshot_redacted.json"] = input_payload

    metadata_safe = _normalise(
        dict(metadata or {}), prefix="metadata", files=files, include_tables=False
    )
    metadata_payload = json.dumps(metadata_safe, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    if len(metadata_payload) > 250_000:
        raise ValueError("User metadata cannot exceed 250,000 bytes.")
    files["run_metadata.json"] = metadata_payload

    dependency_versions: dict[str, str] = {}
    for distribution in ("numpy", "pandas", "scipy", "PuLP", "streamlit"):
        try:
            dependency_versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            dependency_versions[distribution] = "NOT_INSTALLED"

    generated_at = datetime.now(timezone.utc).isoformat()
    files["README.txt"] = (
        f"Shoir-IE Reproducibility Pack — {target_id} {name}\n\n"
        f"Generated UTC: {generated_at}\n"
        f"Configuration SHA-256 (redacted configuration): {input_fingerprint}\n"
        f"Input snapshot included: {bool(include_input_snapshot)}\n"
        f"Detailed result tables included: {bool(include_result_tables)}\n\n"
        "Verify payload hashes against SHA256SUMS.txt. Review manifest redaction policy and limitations.\n"
        "This bundle is not proof of engineering correctness or a substitute for method review.\n"
    ).encode("utf-8")
    files_manifest = [
        {"path": path, "byte_count": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        for path, payload in sorted(files.items())
    ]
    manifest = {
        "format": "shoir-ie-reproducibility-pack",
        "format_version": 1,
        "tool_id": target_id,
        "canonical_name": name,
        "generated_at_utc": generated_at,
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "dependency_versions": dependency_versions,
        "configuration_sha256": input_fingerprint,
        "configuration_snapshot_included": bool(include_input_snapshot),
        "detailed_result_tables_included": bool(include_result_tables),
        "metadata": metadata_safe,
        "payload_files": files_manifest,
        "redaction_policy": {
            "sensitive_mapping_keys": "Values are replaced with [REDACTED] when their key names match common secret/credential/contact patterns.",
            "sensitive_table_columns": "Common secret/credential/contact columns are replaced with [REDACTED] when detailed tables are included.",
            "input_snapshot": "Opt-in; redacted JSON only. Hashes alone do not prove the correctness or completeness of source inputs.",
        },
        "limitations": [
            "This bundle provides reproducibility metadata and fingerprints, not a mathematical proof, audit certification or guarantee that the execution environment is identical.",
            "Table cells whose column names do not indicate sensitive content may still contain confidential data; review contents before sharing.",
            "The manifest hashes payload files but deliberately does not attempt to hash itself or the checksum file.",
        ],
    }
    manifest_payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    checksum_payload = "\n".join(
        f"{item['sha256']}  {item['path']}" for item in files_manifest
    ).encode("utf-8") + b"\n"

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member_path, payload in sorted(files.items()):
            archive.writestr(member_path, payload)
        archive.writestr("manifest.json", manifest_payload)
        archive.writestr("SHA256SUMS.txt", checksum_payload)
    bundle = archive_buffer.getvalue()
    if len(bundle) > max_payload_bytes:
        raise ValueError(f"Reproducibility ZIP exceeds the configured {max_payload_bytes:,}-byte payload limit.")

    inventory = pd.DataFrame([
        {"Path": path, "Bytes": len(payload), "SHA-256": hashlib.sha256(payload).hexdigest()}
        for path, payload in sorted(files.items())
    ] + [
        {"Path": "manifest.json", "Bytes": len(manifest_payload), "SHA-256": hashlib.sha256(manifest_payload).hexdigest()},
        {"Path": "SHA256SUMS.txt", "Bytes": len(checksum_payload), "SHA-256": hashlib.sha256(checksum_payload).hexdigest()},
    ])
    return {
        "status": "REPRODUCIBILITY_PACK_CREATED",
        "tool_id": target_id,
        "canonical_name": name,
        "filename": f"shoir_ie_{target_id.lower()}_reproducibility_pack.zip",
        "bundle_bytes": bundle,
        "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "bundle_byte_count": len(bundle),
        "input_fingerprint_sha256": input_fingerprint,
        "manifest": manifest,
        "artifact_inventory": inventory,
        "included_payload_paths": sorted(files),
        "data_provenance": "PACKAGED_FROM_SAVED_SESSION_RESULT",
        "warnings": [
            "Review bundle contents before sharing; non-sensitive-looking data columns may contain confidential information.",
            "Input values are excluded by default; only their redacted fingerprint is included unless the input snapshot option is enabled.",
        ],
    }


def optimize_facility_location_flow(
    facilities: Sequence[Mapping[str, Any]],
    customers: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    *,
    time_limit_seconds: float = 10.0,
) -> dict[str, Any]:
    """Minimize facility opening plus route shipment costs for one planning period.

    This is a capacitated, single-period facility-location MILP. Each customer
    demand must be met exactly; facility and route capacities are hard bounds.
    A returned optimal solution is independently rechecked against these bounds.
    It does not model uncertainty, multiple periods, production processes or
    alternate routing through intermediate transshipment nodes.
    """
    import pulp

    def _records(value: Any, name: str, *, maximum: int) -> list[Mapping[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError(f"{name} must be a list of records.")
        if not 1 <= len(value) <= maximum:
            raise ValueError(f"{name} must contain between 1 and {maximum} records.")
        if any(not isinstance(item, Mapping) for item in value):
            raise ValueError(f"Every {name} item must be an object.")
        return list(value)

    facilities_raw = _records(facilities, "Facilities", maximum=50)
    customers_raw = _records(customers, "Customers", maximum=500)
    routes_raw = _records(routes, "Routes", maximum=5000)
    limit = _finite_number(time_limit_seconds, "Solver time limit")
    if not 0.1 <= limit <= 300:
        raise ValueError("Solver time limit must be between 0.1 and 300 seconds.")

    def _identifier(raw: Mapping[str, Any], field: str, label: str) -> str:
        value = str(raw.get(field, "")).strip()
        if not value or len(value) > 100:
            raise ValueError(f"{label} must be a non-empty identifier no longer than 100 characters.")
        return value

    normalized_facilities: list[dict[str, Any]] = []
    facility_ids: set[str] = set()
    for row in facilities_raw:
        fid = _identifier(row, "id", "Facility ID")
        if fid.casefold() in facility_ids:
            raise ValueError(f"Facility IDs must be unique; duplicate: {fid}.")
        facility_ids.add(fid.casefold())
        capacity = _finite_number(row.get("capacity"), f"Facility {fid} capacity")
        fixed_cost = _finite_number(row.get("fixed_opening_cost"), f"Facility {fid} opening cost")
        if capacity <= 0:
            raise ValueError(f"Facility {fid} capacity must be greater than zero.")
        if fixed_cost < 0:
            raise ValueError(f"Facility {fid} opening cost cannot be negative.")
        normalized_facilities.append({"id": fid, "capacity": capacity, "fixed_opening_cost": fixed_cost})

    normalized_customers: list[dict[str, Any]] = []
    customer_ids: set[str] = set()
    for row in customers_raw:
        cid = _identifier(row, "id", "Customer ID")
        if cid.casefold() in customer_ids:
            raise ValueError(f"Customer IDs must be unique; duplicate: {cid}.")
        customer_ids.add(cid.casefold())
        demand = _finite_number(row.get("demand"), f"Customer {cid} demand")
        if demand <= 0:
            raise ValueError(f"Customer {cid} demand must be greater than zero.")
        normalized_customers.append({"id": cid, "demand": demand})

    facility_lookup = {x["id"].casefold(): x["id"] for x in normalized_facilities}
    customer_lookup = {x["id"].casefold(): x["id"] for x in normalized_customers}
    total_demand = sum(x["demand"] for x in normalized_customers)
    normalized_routes: list[dict[str, Any]] = []
    route_keys: set[tuple[str, str]] = set()
    for index, row in enumerate(routes_raw, start=1):
        fid_raw = _identifier(row, "facility", f"Route {index} facility")
        cid_raw = _identifier(row, "customer", f"Route {index} customer")
        fid = facility_lookup.get(fid_raw.casefold())
        cid = customer_lookup.get(cid_raw.casefold())
        if fid is None or cid is None:
            raise ValueError(f"Route {index} references an unknown facility or customer.")
        key = (fid.casefold(), cid.casefold())
        if key in route_keys:
            raise ValueError(f"Only one route per facility/customer pair is supported; duplicate route {fid} → {cid}.")
        route_keys.add(key)
        unit_cost = _finite_number(row.get("unit_cost"), f"Route {index} unit cost")
        route_capacity = _finite_number(row.get("capacity", total_demand), f"Route {index} capacity")
        if unit_cost < 0 or route_capacity < 0:
            raise ValueError("Route unit cost and capacity must be non-negative.")
        available = row.get("available", True)
        if not isinstance(available, bool):
            raise ValueError(f"Route {index} available must be true or false.")
        if not available:
            route_capacity = 0.0
        normalized_routes.append({
            "facility": fid,
            "customer": cid,
            "unit_cost": unit_cost,
            "capacity": route_capacity,
            "available": available,
            "index": index,
        })

    model = pulp.LpProblem("ShoirIE_Facility_Location_Flow", pulp.LpMinimize)
    open_vars = {
        i: pulp.LpVariable(f"facility_open_{i}", cat=pulp.LpBinary)
        for i in range(len(normalized_facilities))
    }
    flow_vars = {
        r["index"] - 1: pulp.LpVariable(
            f"route_flow_{r['index'] - 1}", lowBound=0, upBound=r["capacity"], cat=pulp.LpContinuous
        )
        for r in normalized_routes
    }
    facility_index = {x["id"]: i for i, x in enumerate(normalized_facilities)}
    model += (
        pulp.lpSum(f["fixed_opening_cost"] * open_vars[i] for i, f in enumerate(normalized_facilities))
        + pulp.lpSum(r["unit_cost"] * flow_vars[i] for i, r in enumerate(normalized_routes))
    )
    for i, facility in enumerate(normalized_facilities):
        outbound = pulp.lpSum(
            flow_vars[j] for j, route in enumerate(normalized_routes) if route["facility"] == facility["id"]
        )
        model += outbound <= facility["capacity"] * open_vars[i], f"facility_capacity_{i}"
    for i, customer in enumerate(normalized_customers):
        inbound = pulp.lpSum(
            flow_vars[j] for j, route in enumerate(normalized_routes) if route["customer"] == customer["id"]
        )
        model += inbound == customer["demand"], f"customer_demand_{i}"

    try:
        model.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=limit))
    except pulp.PulpSolverError:
        return {
            "status": "SOLVER_UNAVAILABLE",
            "solver_status": "CBC solver unavailable",
            "objective_value": None,
            "flow_table": pd.DataFrame(),
            "facility_table": pd.DataFrame(),
            "customer_balance": pd.DataFrame(),
            "violations": ["Install or configure an available PuLP-compatible MILP solver, then rerun."],
            "assumptions": "Single-period deterministic facility location and route allocation.",
            "warning": "No solution was claimed because the solver could not execute.",
        }

    solver_status = str(pulp.LpStatus.get(model.status, model.status))
    if model.status != pulp.LpStatusOptimal:
        status = "INFEASIBLE" if model.status == pulp.LpStatusInfeasible else "SOLVER_LIMIT_OR_ERROR"
        warning = (
            "No allocation satisfies every demand and facility/route capacity constraint."
            if status == "INFEASIBLE"
            else "The solver did not prove an optimal allocation within the available limits. Do not use this result as a plan."
        )
        return {
            "status": status,
            "solver_status": solver_status,
            "objective_value": None,
            "flow_table": pd.DataFrame(),
            "facility_table": pd.DataFrame(),
            "customer_balance": pd.DataFrame(),
            "violations": [warning],
            "assumptions": "Single-period deterministic facility location and route allocation.",
            "warning": warning,
        }

    tol = 1e-6
    flow_rows: list[dict[str, Any]] = []
    for j, route in enumerate(normalized_routes):
        value = float(pulp.value(flow_vars[j]) or 0.0)
        if abs(value) < tol:
            value = 0.0
        flow_rows.append({
            "Facility": route["facility"], "Customer": route["customer"],
            "Shipment units": value, "Unit cost": route["unit_cost"],
            "Variable cost": value * route["unit_cost"], "Route capacity": route["capacity"],
            "Route available": route["available"],
        })
    flow_df = pd.DataFrame(flow_rows)
    facility_rows: list[dict[str, Any]] = []
    violations: list[str] = []
    fixed_cost_total = 0.0
    for i, facility in enumerate(normalized_facilities):
        opened = float(pulp.value(open_vars[i]) or 0.0) >= 0.5
        shipped = float(flow_df.loc[flow_df["Facility"] == facility["id"], "Shipment units"].sum())
        if shipped > facility["capacity"] + tol:
            violations.append(f"Facility {facility['id']} exceeds capacity.")
        if not opened and shipped > tol:
            violations.append(f"Closed facility {facility['id']} ships a positive quantity.")
        fixed_cost_total += facility["fixed_opening_cost"] if opened else 0.0
        facility_rows.append({
            "Facility": facility["id"], "Open": opened,
            "Fixed opening cost": facility["fixed_opening_cost"] if opened else 0.0,
            "Capacity": facility["capacity"], "Assigned units": shipped,
            "Utilization (%)": 100.0 * shipped / facility["capacity"],
        })
    customer_rows: list[dict[str, Any]] = []
    for customer in normalized_customers:
        delivered = float(flow_df.loc[flow_df["Customer"] == customer["id"], "Shipment units"].sum())
        gap = delivered - customer["demand"]
        if abs(gap) > tol:
            violations.append(f"Customer {customer['id']} demand does not reconcile.")
        customer_rows.append({
            "Customer": customer["id"], "Demand": customer["demand"],
            "Delivered": delivered, "Balance error": gap,
            "Status": "SATISFIED" if abs(gap) <= tol else "VIOLATION",
        })
    if not flow_df.empty and ((flow_df["Shipment units"] > flow_df["Route capacity"] + tol).any() or (flow_df["Shipment units"] < -tol).any()):
        violations.append("A route violates its capacity or non-negativity bound.")
    variable_cost_total = float(flow_df["Variable cost"].sum())
    objective_value = fixed_cost_total + variable_cost_total
    solver_objective = float(pulp.value(model.objective))
    if abs(objective_value - solver_objective) > max(tol, abs(solver_objective) * tol):
        violations.append("Independent objective recomputation does not match the solver objective.")
    independent_ok = not violations
    return {
        "status": "OPTIMAL_FEASIBLE" if independent_ok else "OPTIMAL_SOLUTION_FAILED_AUDIT",
        "solver_status": solver_status,
        "objective_value": objective_value if independent_ok else None,
        "solver_objective_value": solver_objective,
        "fixed_opening_cost": fixed_cost_total,
        "variable_shipment_cost": variable_cost_total,
        "facility_count": len(normalized_facilities),
        "customer_count": len(normalized_customers),
        "route_count": len(normalized_routes),
        "open_facility_count": sum(1 for row in facility_rows if row["Open"]),
        "independent_feasibility_check": independent_ok,
        "violations": violations,
        "flow_table": flow_df,
        "facility_table": pd.DataFrame(facility_rows),
        "customer_balance": pd.DataFrame(customer_rows),
        "assumptions": "Single-period deterministic demand; candidate facilities have fixed opening costs and capacity; each enabled route has a unit cost and capacity; every customer demand must be met exactly.",
        "warning": "This is a modelled plan from user-declared data, not a live logistics optimization or guaranteed real-world cost.",
        "limitations": [
            "No multi-period inventory, intermediate transshipment, variable production cost, uncertainty, carbon objective or demand forecast.",
            "Binary facility opening choices and continuous shipment quantities are optimized for the supplied one-period problem only.",
        ],
    }


def get_student_practice_problem(topic_id: str) -> dict[str, Any]:
    """Return a deterministic practice prompt without revealing the answer key."""
    problems = {
        "takt_time": {
            "label": "Takt time",
            "question": "A line has 420 production minutes available in a shift and must produce 210 units. What is takt time?",
            "unit": "minutes per unit",
            "formula": "Takt time = available production time ÷ customer demand",
            "explanation": "420 available minutes ÷ 210 required units = 2 minutes per unit. Takt is the pace required to meet demand, not the measured cycle time.",
            "answer": 2.0, "tolerance": 0.01,
        },
        "oee_percent": {
            "label": "Overall equipment effectiveness (OEE)",
            "question": "Availability is 90%, performance is 80%, and quality is 95%. What is OEE as a percentage?",
            "unit": "percent",
            "formula": "OEE = availability × performance × quality",
            "explanation": "Convert to fractions and multiply: 0.90 × 0.80 × 0.95 = 0.684, or 68.4%. Use consistent definitions so losses are not double counted.",
            "answer": 68.4, "tolerance": 0.1,
        },
        "eoq_units": {
            "label": "Economic order quantity (EOQ)",
            "question": "Annual demand is 10,000 units, order cost is SAR 50 per order, and annual holding cost is SAR 2 per unit. Calculate EOQ.",
            "unit": "units per order",
            "formula": "EOQ = √(2 × annual demand × order cost ÷ annual holding cost per unit)",
            "explanation": "EOQ = √(2 × 10,000 × 50 ÷ 2) = √500,000 ≈ 707.11 units per order. This classical formula assumes stable demand and constant order/holding costs.",
            "answer": math.sqrt(500000.0), "tolerance": 1.0,
        },
        "process_capability_cp": {
            "label": "Process capability Cp",
            "question": "The lower specification limit is 10 mm, the upper specification limit is 16 mm, and within-subgroup sigma is 1 mm. What is Cp?",
            "unit": "dimensionless index",
            "formula": "Cp = (USL − LSL) ÷ (6 × within-subgroup sigma)",
            "explanation": "Cp = (16 − 10) ÷ (6 × 1) = 1.00. Cp compares specification width with process spread; it does not account for process centering.",
            "answer": 1.0, "tolerance": 0.01,
        },
        "npv_sar": {
            "label": "Net present value (NPV)",
            "question": "An investment costs SAR 1,000 now and returns SAR 600 at the end of each of the next two years. At a 10% annual discount rate, what is NPV?",
            "unit": "SAR",
            "formula": "NPV = −initial investment + Σ(cash flow at t ÷ (1 + discount rate)^t)",
            "explanation": "NPV = −1,000 + 600/1.10 + 600/1.10² ≈ SAR 41.32. This uses end-of-year cash flows and excludes tax, inflation and financing effects.",
            "answer": -1000.0 + 600.0/1.10 + 600.0/(1.10**2), "tolerance": 0.5,
        },
    }
    key = str(topic_id or "").strip().lower()
    if key not in problems:
        raise ValueError("Choose a supported practice topic.")
    p = problems[key]
    return {
        "topic_id": key,
        "topic": p["label"],
        "question": p["question"],
        "unit": p["unit"],
        "formula": p["formula"],
        "method": "Deterministic worked example",
        "data_provenance": "SYNTHETIC_EXERCISE",
    }


def evaluate_student_practice_answer(topic_id: str, submitted_answer: Any) -> dict[str, Any]:
    """Grade a numeric answer against a worked-example key and explain the method."""
    prompt = get_student_practice_problem(topic_id)
    answer = _finite_number(submitted_answer, "Your answer")
    problems = {
        "takt_time": (2.0, 0.01, "420 available production minutes ÷ 210 required units = 2 minutes/unit."),
        "oee_percent": (68.4, 0.1, "0.90 availability × 0.80 performance × 0.95 quality = 0.684 = 68.4%."),
        "eoq_units": (math.sqrt(500000.0), 1.0, "√(2 × 10,000 × 50 ÷ 2) = √500,000 ≈ 707.11 units/order."),
        "process_capability_cp": (1.0, 0.01, "(16 − 10) ÷ (6 × 1) = 1.00."),
        "npv_sar": (-1000.0 + 600.0/1.10 + 600.0/(1.10**2), 0.5, "−1,000 + 600/1.10 + 600/1.10² ≈ SAR 41.32."),
    }
    expected, tolerance, working = problems[prompt["topic_id"]]
    error = abs(answer - expected)
    correct = error <= tolerance
    return {
        "status": "PRACTICE_ANSWER_CHECKED",
        "topic": prompt["topic"],
        "is_correct": correct,
        "submitted_answer": answer,
        "expected_answer": float(expected),
        "absolute_error": float(error),
        "tolerance": float(tolerance),
        "unit": prompt["unit"],
        "formula": prompt["formula"],
        "worked_solution": working,
        "explanation": {
            "takt_time": "Takt is the production pace required by demand; it is not the measured cycle time.",
            "oee_percent": "Keep availability, performance and quality definitions consistent so the same loss is not counted twice.",
            "eoq_units": "Classical EOQ assumes stable demand and constant order and holding costs; it is not a safety-stock calculation.",
            "process_capability_cp": "Cp compares specification width with process spread and does not account for process centering or prove statistical control.",
            "npv_sar": "This example uses end-of-year cash flows and excludes tax, inflation and financing effects.",
        }[prompt["topic_id"]],
        "message": "Correct — well done." if correct else "Not quite. Compare your result with the worked solution and try again.",
        "data_provenance": "SYNTHETIC_EXERCISE",
        "limitations": ["These are fixed practice examples, not a diagnosis of any real plant or process."],
    }


def build_guided_study_plan(
    goal: str,
    *,
    available_data_fields: Sequence[str] | str = (),
    completed_tool_ids: Sequence[str] = (),
    tier: str = "Starter",
) -> dict[str, Any]:
    """Build an explainable next-step plan without inventing analysis results."""
    from shoir_tool_registry import get_tool, tier_allows_tool

    workflows = {
        "capacity_bottleneck": {
            "label": "Production capacity and bottleneck",
            "steps": ["T011", "T013", "T025", "T073", "T083", "T095"],
        },
        "facility_layout": {
            "label": "Facility layout and material flow",
            "steps": ["T065", "T069", "T095"],
        },
        "quality_capability": {
            "label": "Quality and process capability",
            "steps": ["T013", "T031", "T032", "T038", "T095"],
        },
        "inventory_planning": {
            "label": "Inventory and replenishment",
            "steps": ["T054", "T055", "T056", "T095"],
        },
        "maintenance_reliability": {
            "label": "Maintenance and reliability",
            "steps": ["T042", "T041", "T043", "T049", "T095"],
        },
        "energy_sustainability": {
            "label": "Energy and sustainability",
            "steps": ["T077", "T078", "T079", "T095"],
        },
    }
    input_contracts = {
        "T011": ["source_file"],
        "T013": ["validated_dataset"],
        "T025": ["process_table", "demand", "time_unit"],
        "T073": ["baseline_kpis", "scenario_changes"],
        "T083": ["baseline_cost", "post_change_cost", "measurement_window", "evidence_reference"],
        "T095": ["result_set", "assumptions", "source_provenance"],
        "T065": ["departments", "from_to_flows", "distances"],
        "T069": ["facility_table", "customer_demands", "routes", "unit_costs", "capacities"],
        "T031": ["measurements", "sample_order", "process_phase"],
        "T032": ["measurements", "lsl", "usl", "subgroup_size"],
        "T038": ["failure_modes"],
        "T054": ["bill_of_materials", "parent_demand", "on_hand_inventory", "lead_times"],
        "T055": ["mean_daily_demand", "demand_sd", "lead_time", "order_cost", "holding_cost"],
        "T056": ["annual_demand", "unit_cost", "period_demand"],
        "T042": ["operating_hours", "complete_failure_repair_events"],
        "T041": ["failure_times"],
        "T043": ["asset_schedule", "maintenance_intervals", "due_dates"],
        "T049": ["work_orders", "available_hours", "skills"],
        "T077": ["baseline_energy", "alternative_scenarios", "output_units", "energy_cost"],
        "T078": ["activity_amount", "emission_factor", "factor_source", "factor_date"],
        "T079": ["water_inputs", "product_outputs", "waste_flows", "units", "period"],
    }
    goal_key = str(goal or "").strip().lower()
    if goal_key not in workflows:
        raise ValueError("Choose one of the supported guided-study goals.")
    if isinstance(available_data_fields, str):
        field_values = [x.strip() for x in available_data_fields.replace(";", ",").split(",") if x.strip()]
    else:
        field_values = list(available_data_fields or ())
    normalized_fields = {str(x).strip().lower().replace(" ", "_") for x in field_values if str(x).strip()}
    completed = {str(x).strip().upper() for x in (completed_tool_ids or ())}
    if any(not isinstance(x, str) or len(x) != 4 or not x.startswith("T") or not x[1:].isdigit() for x in completed):
        raise ValueError("Completed tool references must be canonical IDs such as T025.")

    rows = []
    restricted_count = 0
    missing_count = 0
    foundation_count = 0
    completed_count = 0
    for position, tool_id in enumerate(workflows[goal_key]["steps"], start=1):
        tool = get_tool(tool_id)
        if not isinstance(tool, Mapping):
            raise ValueError(f"Guided workflow refers to unknown canonical tool {tool_id}.")
        allowed = bool(tier_allows_tool(tier, tool_id))
        readiness = str(tool.get("implementation_status", "UNRESOLVED"))
        required = input_contracts.get(tool_id, [])
        missing = [field for field in required if field not in normalized_fields]
        if not allowed:
            status = "TIER_RESTRICTED"
            next_action = f"Requires {tool.get('target_minimum_tier', 'a higher package')}; the wizard does not bypass access controls."
            restricted_count += 1
        elif tool_id in completed:
            status = "COMPLETED_IN_SESSION"
            next_action = "Review the saved result and confirm its input assumptions."
            completed_count += 1
        elif readiness == "FOUNDATION_ONLY":
            status = "FOUNDATION_ONLY"
            next_action = "This capability is not complete yet; use only a separately supported workflow."
            foundation_count += 1
        elif missing:
            status = "INPUTS_MISSING"
            next_action = "Provide: " + ", ".join(missing)
            missing_count += 1
        else:
            status = "READY"
            next_action = "Open this tool and validate the inputs before running it."
        rows.append({
            "Step": position,
            "Tool ID": tool_id,
            "Tool": tool.get("canonical_name", tool_id),
            "Minimum tier": tool.get("target_minimum_tier", "UNRESOLVED"),
            "Catalog readiness": readiness,
            "Step status": status,
            "Required input fields": ", ".join(required) if required else "Confirm requirements in tool",
            "Missing input fields": ", ".join(missing),
            "Next action": next_action,
        })
    steps = pd.DataFrame(rows)
    ready_steps = steps[steps["Step status"] == "READY"]
    next_step = None if ready_steps.empty else {
        "tool_id": str(ready_steps.iloc[0]["Tool ID"]),
        "canonical_name": str(ready_steps.iloc[0]["Tool"]),
        "step": int(ready_steps.iloc[0]["Step"]),
    }
    return {
        "status": "GUIDED_PLAN_CREATED",
        "goal": workflows[goal_key]["label"],
        "goal_id": goal_key,
        "tier": str(tier),
        "steps": steps,
        "step_count": len(steps),
        "ready_step_count": int((steps["Step status"] == "READY").sum()),
        "missing_input_step_count": missing_count,
        "tier_restricted_step_count": restricted_count,
        "foundation_only_step_count": foundation_count,
        "completed_step_count": completed_count,
        "next_recommended_step": next_step,
        "available_data_fields": sorted(normalized_fields),
        "method": "Rule-based guided workflow using the canonical target registry; no analysis is run by the wizard.",
        "warning": "This is a study plan, not an engineering result. Run each tool separately, validate its data and assumptions, and do not treat estimates as realized outcomes.",
        "data_provenance": "USER-PROVIDED INPUT INVENTORY AND CANONICAL TOOL REGISTRY",
    }


def monitor_equipment_anomalies(
    observations: Sequence[Mapping[str, Any]],
    *,
    value_field: str = "value",
    timestamp_field: str = "timestamp",
    modified_z_threshold: float = 3.5,
    max_age_hours: float = 72.0,
    evaluation_time_utc: Any = None,
) -> dict[str, Any]:
    """Flag point anomalies using a global median/MAD baseline and disclose freshness.

    The zero-MAD branch uses a documented absolute-deviation fallback. This is a
    screening method, not a predictive-maintenance model or causal diagnosis.
    """
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise ValueError("Observations must be a JSON list of timestamp/value records.")
    if not 5 <= len(observations) <= 50000:
        raise ValueError("Anomaly monitoring requires between 5 and 50,000 observations.")
    if any(not isinstance(row, Mapping) for row in observations):
        raise ValueError("Every observation must be an object.")
    threshold = _finite_number(modified_z_threshold, "Modified-z threshold")
    if not 1.0 <= threshold <= 10.0:
        raise ValueError("Modified-z threshold must be between 1.0 and 10.0.")
    max_age = _finite_number(max_age_hours, "Maximum data age in hours")
    if not 0.01 <= max_age <= 8760:
        raise ValueError("Maximum data age must be between 0.01 and 8,760 hours.")
    if not str(value_field).strip() or not str(timestamp_field).strip():
        raise ValueError("Timestamp and value column names are required.")

    records = []
    for index, row in enumerate(observations, start=1):
        timestamp = pd.to_datetime(row.get(timestamp_field), utc=True, errors="coerce")
        if pd.isna(timestamp):
            raise ValueError(f"Observation {index} has a missing or invalid timestamp.")
        if value_field not in row:
            raise ValueError(f"Observation {index} is missing value field {value_field!r}.")
        value = _finite_number(row[value_field], f"Observation {index} value")
        records.append({"timestamp": timestamp, "value": value, "source_row": index})
    frame = pd.DataFrame(records)
    original_times = list(frame["timestamp"])
    out_of_order = sum(1 for i in range(1, len(original_times)) if original_times[i] < original_times[i-1])
    duplicate_timestamps = int(frame["timestamp"].duplicated(keep=False).sum())
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)

    values = frame["value"].to_numpy(dtype=float)
    median = float(np.median(values))
    deviations = np.abs(values - median)
    mad = float(np.median(deviations))
    warnings = []
    if mad > max(1e-12, abs(median) * 1e-12):
        modified_z = 0.6744897501960817 * (values - median) / mad
        anomalies = np.abs(modified_z) > threshold
        method = "GLOBAL_MEDIAN_MAD_MODIFIED_Z"
        frame["modified_z_score"] = modified_z
    else:
        absolute_limit = max(1e-9, abs(median) * 0.01)
        anomalies = deviations > absolute_limit
        frame["modified_z_score"] = None
        method = "ZERO_MAD_ABSOLUTE_DEVIATION_FALLBACK"
        warnings.append(
            f"Baseline MAD is zero; points more than {absolute_limit:.6g} from the median are flagged using an absolute-deviation fallback."
        )
    frame["is_anomaly"] = anomalies.astype(bool)
    frame["baseline_median"] = median
    frame["baseline_mad"] = mad

    if evaluation_time_utc is None or not str(evaluation_time_utc).strip():
        evaluation_time = pd.Timestamp.now(tz="UTC")
    else:
        evaluation_time = pd.to_datetime(evaluation_time_utc, utc=True, errors="coerce")
        if pd.isna(evaluation_time):
            raise ValueError("Evaluation time must be a valid UTC-compatible timestamp.")
    latest = frame["timestamp"].max()
    age_hours = float((evaluation_time - latest).total_seconds() / 3600.0)
    if age_hours < -0.0833333333:
        freshness = "FUTURE_TIMESTAMP"
        warnings.append("Latest observation is more than five minutes ahead of the evaluation time.")
    elif age_hours <= max_age:
        freshness = "FRESH"
    else:
        freshness = "STALE"
        warnings.append(f"Latest observation is {age_hours:.1f} hours old, exceeding the {max_age:g}-hour freshness limit.")
    if out_of_order:
        warnings.append(f"{out_of_order} observations were out of timestamp order and were sorted for analysis.")
    if duplicate_timestamps:
        warnings.append(f"{duplicate_timestamps} rows share duplicate timestamps; check sampling and deduplicate if appropriate.")
    anomaly_frame = frame.loc[frame["is_anomaly"]].copy().reset_index(drop=True)
    count = int(frame["is_anomaly"].sum())
    return {
        "status": "ANOMALIES_DETECTED" if count else "NO_ANOMALIES_DETECTED",
        "detection_method": method,
        "value_field": str(value_field),
        "timestamp_field": str(timestamp_field),
        "observation_count": int(len(frame)),
        "anomaly_count": count,
        "anomaly_rate_pct": 100.0 * count / len(frame),
        "baseline_median": median,
        "baseline_mad": mad,
        "modified_z_threshold": threshold,
        "freshness_status": freshness,
        "latest_observation_utc": latest.isoformat(),
        "data_age_hours": age_hours,
        "maximum_data_age_hours": max_age,
        "out_of_order_rows": out_of_order,
        "duplicate_timestamp_rows": duplicate_timestamps,
        "series": frame,
        "anomalies": anomaly_frame,
        "warnings": warnings,
        "method_limitations": [
            "Uses a global point-anomaly baseline and does not model seasonality, operating modes, multivariate relationships, or causal faults.",
            "False positives depend on the supplied threshold and the representativeness of the observation window.",
            "Freshness is reported separately; fresh data does not establish sensor accuracy or plant connectivity.",
        ],
        "data_provenance": "USER_ENTERED_UNVERIFIED",
    }


def assess_capa_8d_records(
    records: Sequence[Mapping[str, Any]],
    *,
    as_of_date: Any = None,
) -> dict[str, Any]:
    """Validate CAPA/8D register records and flag missing evidence and due dates.

    This method is a record-quality/workflow assistant. It never certifies that a
    root cause is correct, an action is effective, or a 8D program is compliant.
    """
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("CAPA/8D records must be a JSON list of objects.")
    if not 1 <= len(records) <= 5000:
        raise ValueError("Provide between 1 and 5,000 CAPA/8D records.")
    if any(not isinstance(row, Mapping) for row in records):
        raise ValueError("Every CAPA/8D record must be an object.")

    if as_of_date is None or not str(as_of_date).strip():
        as_of = pd.Timestamp.now(tz="UTC").date()
    else:
        parsed_as_of = pd.to_datetime(as_of_date, errors="coerce")
        if pd.isna(parsed_as_of):
            raise ValueError("As-of date must be a valid date.")
        as_of = parsed_as_of.date()

    required_fields = {
        "D1 team": "team",
        "D2 problem statement": "problem_statement",
        "D3 containment action": "containment_action",
        "D4 root cause": "root_cause",
        "D5 corrective action": "corrective_action",
        "D6 implementation evidence": "implementation_evidence",
        "D7 recurrence prevention": "preventive_action",
        "D8 closure review": "closure_review",
    }
    status_values = {"OPEN", "IN_PROGRESS", "PENDING_EFFECTIVENESS", "CLOSED"}
    ids: set[str] = set()
    output_rows: list[dict[str, Any]] = []
    missing_total = overdue_total = 0
    for index, raw in enumerate(records, start=1):
        capa_id = str(raw.get("capa_id", "")).strip()
        title = str(raw.get("title", "")).strip()
        if not capa_id or len(capa_id) > 100:
            raise ValueError(f"Record {index} needs a CAPA ID no longer than 100 characters.")
        if capa_id.casefold() in ids:
            raise ValueError(f"CAPA IDs must be unique; duplicate ID: {capa_id}.")
        ids.add(capa_id.casefold())
        if not title:
            raise ValueError(f"Record {capa_id} needs a non-empty title.")
        status = str(raw.get("status", "OPEN")).strip().upper()
        if status not in status_values:
            raise ValueError(f"Record {capa_id} status must be one of {', '.join(sorted(status_values))}.")

        opened_raw = str(raw.get("opened_date", "")).strip()
        due_raw = str(raw.get("due_date", "")).strip()
        opened_date = pd.to_datetime(opened_raw, errors="coerce").date() if opened_raw else None
        due_date = pd.to_datetime(due_raw, errors="coerce").date() if due_raw else None
        if opened_raw and opened_date is None:
            raise ValueError(f"Record {capa_id} has an invalid opened_date.")
        if due_raw and due_date is None:
            raise ValueError(f"Record {capa_id} has an invalid due_date.")
        if opened_date and due_date and due_date < opened_date:
            raise ValueError(f"Record {capa_id} due date cannot precede its opened date.")

        missing = [
            label for label, field in required_fields.items()
            if not str(raw.get(field, "") or "").strip()
        ]
        if not str(raw.get("owner", "") or "").strip():
            missing.append("Accountable owner")
        if not str(raw.get("evidence_reference", "") or "").strip():
            missing.append("Evidence reference")
        if not opened_date:
            missing.append("Opened date")
        if not due_date:
            missing.append("Due date")
        if status == "CLOSED":
            if not str(raw.get("effectiveness_evidence", "") or "").strip():
                missing.append("Effectiveness evidence")
            if not str(raw.get("reviewer", "") or "").strip():
                missing.append("Closure reviewer")
            if not str(raw.get("approval_reference", "") or "").strip():
                missing.append("Closure approval reference")
        missing = list(dict.fromkeys(missing))
        is_overdue = bool(due_date and due_date < as_of and status != "CLOSED")
        if is_overdue:
            overdue_total += 1
        if missing:
            missing_total += 1
        completeness_pct = 100.0 * (len(required_fields) + 4 - len(missing)) / (len(required_fields) + 4)
        if status == "CLOSED" and not missing:
            workflow_state = "CLOSED_RECORD_COMPLETE"
        elif status == "CLOSED" and missing:
            workflow_state = "CLOSURE_EVIDENCE_INCOMPLETE"
        elif is_overdue:
            workflow_state = "OVERDUE"
        elif missing:
            workflow_state = "REQUIRES_EVIDENCE"
        elif status == "PENDING_EFFECTIVENESS":
            workflow_state = "PENDING_EFFECTIVENESS"
        else:
            workflow_state = status
        output_rows.append({
            "CAPA ID": capa_id,
            "Title": title,
            "Status": status,
            "Workflow state": workflow_state,
            "Owner": str(raw.get("owner", "") or "").strip(),
            "Opened date": opened_date.isoformat() if opened_date else "",
            "Due date": due_date.isoformat() if due_date else "",
            "Overdue": is_overdue,
            "Missing items": "; ".join(missing),
            "Missing item count": len(missing),
            "Completeness (%)": completeness_pct,
            "Reviewer": str(raw.get("reviewer", "") or "").strip(),
            "Evidence reference": str(raw.get("evidence_reference", "") or "").strip(),
        })
    frame = pd.DataFrame(output_rows)
    status_counts = frame["Workflow state"].value_counts().rename_axis("Workflow state").reset_index(name="Records")
    return {
        "status": "CAPA_REGISTER_REVIEWED",
        "record_count": int(len(frame)),
        "overdue_count": overdue_total,
        "records_with_missing_evidence": missing_total,
        "complete_closure_count": int((frame["Workflow state"] == "CLOSED_RECORD_COMPLETE").sum()),
        "workflow_summary": status_counts,
        "records": frame,
        "as_of_date": as_of.isoformat(),
        "required_eight_discipline_fields": list(required_fields.keys()),
        "method": "Structured 8D/CAPA field-completeness, due-date and closure-evidence screening",
        "warning": "This register checks record completeness and status only. It does not verify the truth of root-cause claims, action effectiveness, regulatory compliance or engineering safety.",
        "data_provenance": "USER_ENTERED_UNVERIFIED",
    }