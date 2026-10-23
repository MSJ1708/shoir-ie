"""Validated first-pass deterministic engines for seven focused Shoir-IE targets.

Scope:
* T022 estimates work-sampling proportions with individual Wilson confidence intervals.
* T028 builds a count-based Pareto summary and optional 5-Why/action record.
* T029 scores an editable 5S checklist with transparent owner/due-date follow-up flags.
* T030 validates A3 baseline/target/outcome records and calculates signed target progress.
* T066 is a one-dimensional cutting/bin-packing MILP with a per-piece kerf allowance.
* T075 is a threshold-based forecast error monitor, not an automatic retraining service.
* T085 is a balanced independent two-sample t-test planner using the noncentral t distribution.
"""
from __future__ import annotations

import math
from datetime import date as _date
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import pulp
from scipy.stats import nct, norm, t


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
            raise ValueError(f"Activity category names must be unique after trimming/case normalization: {name}.")
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
            raise ValueError(f"Pareto category names must be unique after trimming/case normalization: {name}.")
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
            f"{len(priority_actions)} checklist item(s) scored 2 or below; {owner_gaps} need an assigned owner and ISO due date."
            if len(priority_actions) else
            "No item scored 2 or below on this self-assessed checklist. This is not a certified audit or independent verification."
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
        "warning": " ".join(warnings) if warnings else "A dated human review and post-change evidence reference are recorded; this is not an audited savings certificate.",
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


__all__ = [
    "analyze_work_sampling",
    "analyze_pareto_root_cause",
    "assess_5s_audit",
    "build_kaizen_a3_record",
    "calculate_time_study",
    "calculate_takt_capacity",
    "monitor_forecast_drift",
    "plan_two_sample_t_sample_size",
]
