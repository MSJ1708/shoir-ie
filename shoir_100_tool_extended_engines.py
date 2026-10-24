"""Additional deterministic engines for the Shoir-IE 100-tool library.

This module adds only methods not already implemented in shoir_100_tool_engines.py.
Currency conversion uses user-supplied dated rates only; outputs are estimates, not
safety/quality certifications. Full end-to-end readiness is tracked separately.
"""
from __future__ import annotations

import math
from datetime import date as _date
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import pulp
from scipy.stats import nct, norm, t

from shoir_100_tool_engines import _finite_number

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


def profile_data_quality(data: pd.DataFrame, *, iqr_multiplier: float = 1.5) -> dict[str, Any]:
    """Non-destructively profile nulls, duplicates, types, distributions and IQR outliers."""
    if not isinstance(data, pd.DataFrame):
        raise ValueError("Data must be supplied as a table.")
    if data.empty:
        raise ValueError("Add at least one row before profiling data quality.")
    if len(data.columns) == 0:
        raise ValueError("The dataset must contain at least one field.")
    if data.columns.duplicated().any():
        raise ValueError("Column names must be unique before profiling.")
    try:
        multiplier = _finite_number(iqr_multiplier, "IQR multiplier")
    except ValueError as exc:
        raise
    if multiplier <= 0:
        raise ValueError("IQR multiplier must be greater than zero.")

    source = data.copy(deep=True)
    field_rows = []
    total_missing = int(source.isna().sum().sum())
    for column in source.columns:
        series = source[column]
        missing = int(series.isna().sum())
        row: dict[str, Any] = {
            "field": str(column),
            "dtype": str(series.dtype),
            "row_count": int(len(source)),
            "non_missing": int(series.notna().sum()),
            "missing": missing,
            "missing_pct": round(missing / len(source) * 100.0, 4),
            "unique_non_missing": int(series.nunique(dropna=True)),
            "numeric_mean": None,
            "numeric_min": None,
            "numeric_max": None,
            "numeric_std": None,
            "iqr_outlier_count": 0,
        }
        if pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype):
            numeric = pd.to_numeric(series, errors="coerce").dropna().astype(float)
            if not numeric.map(math.isfinite).all():
                raise ValueError(f"Numeric field {column!r} contains an infinite value.")
            if not numeric.empty:
                q1 = float(numeric.quantile(0.25))
                q3 = float(numeric.quantile(0.75))
                spread = q3 - q1
                lower = q1 - multiplier * spread
                upper = q3 + multiplier * spread
                row.update({
                    "numeric_mean": float(numeric.mean()),
                    "numeric_min": float(numeric.min()),
                    "numeric_max": float(numeric.max()),
                    "numeric_std": float(numeric.std(ddof=1)) if len(numeric) > 1 else 0.0,
                    "iqr_outlier_count": int(((numeric < lower) | (numeric > upper)).sum()),
                })
        field_rows.append(row)

    duplicate_rows = int(source.duplicated(keep="first").sum())
    fields = pd.DataFrame(field_rows)
    warnings = []
    if total_missing:
        warnings.append(f"{total_missing} missing cell(s) found; no values were changed or deleted.")
    if duplicate_rows:
        warnings.append(f"{duplicate_rows} duplicate row(s) found; no rows were removed.")
    outlier_fields = int((fields["iqr_outlier_count"] > 0).sum())
    if outlier_fields:
        warnings.append(f"IQR screening flagged potential outliers in {outlier_fields} numeric field(s); review them rather than assuming they are errors.")
    return {
        "status": "PROFILED",
        "method": "Non-destructive schema, missingness, duplicate-row, numeric summary and Tukey IQR screening.",
        "metrics": {
            "row_count": int(len(source)),
            "column_count": int(len(source.columns)),
            "missing_cell_count": total_missing,
            "duplicate_row_count": duplicate_rows,
            "numeric_fields_with_iqr_outliers": outlier_fields,
        },
        "field_profile": fields,
        "source_row_count": int(len(source)),
        "source_column_count": int(len(source.columns)),
        "formulas": {
            "missing_pct": "100 × missing cells in field / total rows",
            "IQR bounds": "Q1 − k×(Q3−Q1), Q3 + k×(Q3−Q1); k is an explicit input",
            "duplicate_rows": "Rows identical across all input columns after pandas value comparison",
        },
        "assumptions": [
            f"Input preserved as {len(source)} rows × {len(source.columns)} columns; profiling is read-only.",
            f"IQR multiplier k={multiplier:g}; an outlier flag is a screening signal, not proof of data error.",
        ],
        "warnings": warnings,
    }


def preview_data_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_key: str,
    right_key: str,
    *,
    how: str = "left",
) -> dict[str, Any]:
    """Preview a relational join without mutating either source and report cardinality risks."""
    if not isinstance(left, pd.DataFrame) or not isinstance(right, pd.DataFrame):
        raise ValueError("Both left and right inputs must be tables.")
    if left.empty or right.empty:
        raise ValueError("Both datasets must contain at least one row.")
    if left.columns.duplicated().any() or right.columns.duplicated().any():
        raise ValueError("Column names must be unique in both datasets.")
    if not str(left_key or "").strip() or left_key not in left.columns:
        raise ValueError("Select a valid left-side join key.")
    if not str(right_key or "").strip() or right_key not in right.columns:
        raise ValueError("Select a valid right-side join key.")
    join_type = str(how or "").strip().lower()
    if join_type not in {"left", "right", "inner", "outer"}:
        raise ValueError("Join type must be left, right, inner or outer.")
    for side_name, frame, key in (("left", left, left_key), ("right", right, right_key)):
        key_values = frame[key]
        if key_values.isna().any() or key_values.astype(str).str.strip().eq("").any():
            raise ValueError(f"The {side_name} join key {key!r} contains missing or blank values; resolve them explicitly first.")

    left_source = left.copy(deep=True)
    right_source = right.copy(deep=True)
    left_dupe_rows = int(left_source[left_key].duplicated(keep=False).sum())
    right_dupe_rows = int(right_source[right_key].duplicated(keep=False).sum())
    marker = "__shoir_join_status"
    while marker in set(left_source.columns) | set(right_source.columns):
        marker += "_"
    merged = left_source.merge(
        right_source,
        how=join_type,
        left_on=left_key,
        right_on=right_key,
        indicator=marker,
        suffixes=("_left", "_right"),
        sort=False,
    )
    states = merged[marker].value_counts()
    matched_rows = int(states.get("both", 0))
    left_only_rows = int(states.get("left_only", 0))
    right_only_rows = int(states.get("right_only", 0))
    visible = merged.drop(columns=[marker])
    warnings = []
    if left_dupe_rows:
        warnings.append(f"Left key has {left_dupe_rows} row(s) whose key value is duplicated; joining may multiply rows.")
    if right_dupe_rows:
        warnings.append(f"Right key has {right_dupe_rows} row(s) whose key value is duplicated; joining may multiply rows.")
    if left_only_rows:
        warnings.append(f"{left_only_rows} output row(s) did not match a right-side key.")
    if right_only_rows:
        warnings.append(f"{right_only_rows} output row(s) did not match a left-side key.")
    return {
        "status": "PREVIEWED",
        "method": f"Pandas {join_type} join preview; source dataframes copied before merge.",
        "join_type": join_type,
        "metrics": {
            "left_input_rows": int(len(left_source)),
            "right_input_rows": int(len(right_source)),
            "output_rows": int(len(visible)),
            "matched_output_rows": matched_rows,
            "unmatched_left_output_rows": left_only_rows,
            "unmatched_right_output_rows": right_only_rows,
            "left_duplicate_key_rows": left_dupe_rows,
            "right_duplicate_key_rows": right_dupe_rows,
        },
        "merged_preview": visible,
        "join_audit": pd.DataFrame([
            {"measure": "Left input rows", "count": int(len(left_source))},
            {"measure": "Right input rows", "count": int(len(right_source))},
            {"measure": "Output rows", "count": int(len(visible))},
            {"measure": "Matched output rows", "count": matched_rows},
            {"measure": "Unmatched left output rows", "count": left_only_rows},
            {"measure": "Unmatched right output rows", "count": right_only_rows},
            {"measure": "Left duplicated-key rows", "count": left_dupe_rows},
            {"measure": "Right duplicated-key rows", "count": right_dupe_rows},
        ]),
        "formulas": {
            "row_reconciliation": "Output rows are counted after the selected join; repeated keys can legitimately multiply rows.",
            "match_counts": "Pandas merge indicator before it is removed from the displayed output.",
        },
        "assumptions": [
            f"Left key: {left_key}; right key: {right_key}; join type: {join_type}.",
            "No source rows were removed or overwritten; review cardinality warnings before accepting a join.",
        ],
        "warnings": warnings,
    }


def process_time_series(
    data: pd.DataFrame,
    timestamp_col: str,
    value_cols: Sequence[str],
    *,
    source_timezone: str = "UTC",
    frequency: str = "1h",
    aggregation: str = "mean",
) -> dict[str, Any]:
    """Normalize timestamps to UTC, report duplicates/gaps, and resample with explicit aggregation."""
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("Add a non-empty timestamped table before processing a time series.")
    if data.columns.duplicated().any():
        raise ValueError("Column names must be unique before processing a time series.")
    if timestamp_col not in data.columns:
        raise ValueError(f"Timestamp field {timestamp_col!r} was not found.")
    selected_values = [str(c) for c in value_cols]
    if not selected_values or len(set(selected_values)) != len(selected_values):
        raise ValueError("Select one or more distinct numeric value fields.")
    missing_columns = [c for c in selected_values if c not in data.columns]
    if missing_columns:
        raise ValueError("Missing numeric value field(s): " + ", ".join(missing_columns))
    agg = str(aggregation or "").strip().lower()
    if agg not in {"mean", "sum", "min", "max", "first", "last"}:
        raise ValueError("Aggregation must be mean, sum, min, max, first or last.")
    freq = str(frequency or "").strip()
    try:
        offset = pd.tseries.frequencies.to_offset(freq)
    except (ValueError, TypeError) as exc:
        raise ValueError("Choose a valid resampling frequency such as 15min, 1h or 1D.") from exc
    if getattr(offset, "n", 1) <= 0:
        raise ValueError("Resampling frequency must be positive.")
    zone = str(source_timezone or "").strip()
    if not zone:
        raise ValueError("Supply the source timezone (use UTC if timestamps are already UTC).")

    source = data.copy(deep=True)
    stamps = pd.to_datetime(source[timestamp_col], errors="coerce")
    invalid_stamps = int(stamps.isna().sum())
    if invalid_stamps:
        raise ValueError(f"{invalid_stamps} timestamp(s) could not be parsed.")
    try:
        if stamps.dt.tz is None:
            stamps = stamps.dt.tz_localize(zone, ambiguous="raise", nonexistent="raise")
        stamps = stamps.dt.tz_convert("UTC")
    except Exception as exc:
        raise ValueError(f"Timezone localization/conversion failed for {zone!r}: check timezone and daylight-saving ambiguity.") from exc

    duplicate_timestamp_rows = int(stamps.duplicated(keep=False).sum())
    source[timestamp_col] = stamps
    numeric_invalid = {}
    for col in selected_values:
        converted = pd.to_numeric(source[col], errors="coerce")
        invalid_count = int((converted.isna() & source[col].notna()).sum())
        if invalid_count:
            numeric_invalid[col] = invalid_count
        non_null_numeric = converted.dropna().astype(float)
        if not non_null_numeric.map(math.isfinite).all():
            raise ValueError(f"Value field {col!r} contains an infinite value.")
        source[col] = converted
    if numeric_invalid:
        raise ValueError("Non-numeric values in selected field(s): " + ", ".join(f"{k} ({v})" for k, v in numeric_invalid.items()))

    source = source.sort_values(timestamp_col).set_index(timestamp_col)
    resampled = source[selected_values].resample(offset).agg(agg)
    resampled.index.name = "timestamp_utc"
    expected_index = pd.date_range(resampled.index.min(), resampled.index.max(), freq=offset)
    # Normalize both indexes to UTC, which also makes timezone-aware DST transitions explicit.
    expected = len(expected_index)
    missing_intervals = int(resampled[selected_values].isna().all(axis=1).sum())
    output = resampled.reset_index()
    warnings = []
    if duplicate_timestamp_rows:
        warnings.append(f"{duplicate_timestamp_rows} source row(s) share a timestamp; the selected {agg} aggregation combines them.")
    if missing_intervals:
        warnings.append(f"{missing_intervals} resampled interval(s) contain no observations; they are shown as missing, not imputed.")
    return {
        "status": "PROCESSED",
        "method": f"Timestamp parsing/localization to UTC then {freq} resampling with {agg}.",
        "metrics": {
            "input_rows": int(len(data)),
            "output_intervals": int(len(output)),
            "duplicate_timestamp_rows": duplicate_timestamp_rows,
            "expected_intervals": int(expected),
            "missing_intervals": missing_intervals,
        },
        "resampled_series": output,
        "formulas": {
            "timestamp normalization": "Localize naive timestamps using the selected source timezone, then convert to UTC.",
            "resampling": f"Group observations into {freq} intervals using {agg}; empty intervals remain null.",
        },
        "assumptions": [
            f"Source timezone: {zone}; output timezone: UTC; frequency: {freq}; aggregation: {agg}.",
            "No interpolation or automatic deletion is applied; duplicate and missing intervals remain visible.",
        ],
        "warnings": warnings,
    }


def generate_synthetic_industrial_data(
    row_count: int,
    seed: int,
    *,
    defect_rate: float = 0.03,
    downtime_rate: float = 0.10,
) -> dict[str, Any]:
    """Generate deterministic practice data explicitly marked SYNTHETIC, never measured plant data."""
    import random
    from datetime import timedelta

    if isinstance(row_count, bool) or not isinstance(row_count, int) or not 1 <= row_count <= 100_000:
        raise ValueError("Row count must be a whole number between 1 and 100000.")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("Seed must be a non-negative whole number.")
    defects = _finite_number(defect_rate, "Defect rate")
    downtime = _finite_number(downtime_rate, "Downtime rate")
    if not 0 <= defects <= 1:
        raise ValueError("Defect rate must be between 0 and 1 inclusive.")
    if not 0 <= downtime <= 1:
        raise ValueError("Downtime rate must be between 0 and 1 inclusive.")

    rng = random.Random(seed)
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    rows = []
    for idx in range(row_count):
        produced = rng.randint(80, 120)
        defective = sum(1 for _ in range(produced) if rng.random() < defects)
        cycle = max(0.1, rng.gauss(32.0, 4.0))
        downtime_minutes = 0.0 if rng.random() > downtime else rng.uniform(1.0, 30.0)
        rows.append({
            "timestamp_utc": start + pd.Timedelta(hours=idx),
            "station_id": f"ST-{1 + (idx % 4):02d}",
            "units_produced": produced,
            "good_units": produced - defective,
            "defect_count": defective,
            "cycle_time_seconds": round(cycle, 4),
            "downtime_minutes": round(downtime_minutes, 3),
            "energy_kwh": round(produced * rng.uniform(0.35, 0.65), 4),
            "data_status": "SYNTHETIC",
        })
    dataset = pd.DataFrame(rows)
    return {
        "status": "GENERATED_SYNTHETIC",
        "method": "Seeded pseudorandom practice data with bounded production, binomial defect sampling, positive cycle-time draw and optional downtime.",
        "source": "SYNTHETIC",
        "seed": seed,
        "metrics": {
            "row_count": int(len(dataset)),
            "seed": seed,
            "synthetic_defect_rate_parameter": defects,
            "synthetic_downtime_probability_parameter": downtime,
        },
        "dataset": dataset,
        "formulas": {
            "good_units": "units_produced − defect_count",
            "energy_kwh": "units_produced × seeded random factor in [0.35, 0.65]",
        },
        "assumptions": [
            "All rows and values are synthetic and generated for practice; they are not observations from a real plant.",
            "The seed makes this implementation reproducible; distributions are illustrative, not calibrated to an industrial process.",
        ],
        "warnings": ["SYNTHETIC — do not report these data as real production, achieved savings or a calibrated benchmark."],
    }
