"""Validated first-pass deterministic engines for nineteen focused Shoir-IE targets.

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


def profile_dataframe(frame: pd.DataFrame, *, max_rows: int = 250_000, max_columns: int = 500) -> dict[str, Any]:
    """Profile an imported table without mutating or deleting source rows.

    Numeric outliers use the descriptive 1.5-IQR flag only; they are not
    automatically removed and are not proof of erroneous observations.
    """
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Data quality profiling requires a pandas DataFrame.")
    if frame.empty or len(frame.columns) == 0:
        raise ValueError("Provide a non-empty table with at least one column.")
    if len(frame) > max_rows or len(frame.columns) > max_columns or len(frame) * len(frame.columns) > 2_000_000:
        raise ValueError("The profiling limit is 250,000 rows, 500 columns and 2,000,000 cells per run.")
    rows: list[dict[str, Any]] = []
    for name in frame.columns:
        series = frame[name]
        non_missing = series.dropna()
        row: dict[str, Any] = {
            "column": str(name),
            "dtype": str(series.dtype),
            "row_count": int(len(series)),
            "missing_count": int(series.isna().sum()),
            "missing_pct": float(series.isna().mean() * 100),
            "distinct_non_null": int(non_missing.nunique(dropna=True)),
            "constant_non_null": bool(len(non_missing) > 0 and non_missing.nunique(dropna=True) <= 1),
            "numeric_min": None,
            "numeric_max": None,
            "numeric_mean": None,
            "numeric_std_sample": None,
            "iqr_outlier_count": None,
            "example_values": [str(value)[:120] for value in non_missing.drop_duplicates().head(3).tolist()],
        }
        if pd.api.types.is_numeric_dtype(series.dtype) and len(non_missing):
            numeric = pd.to_numeric(non_missing, errors="coerce").dropna()
            if len(numeric):
                q1 = float(numeric.quantile(0.25))
                q3 = float(numeric.quantile(0.75))
                iqr = q3 - q1
                row.update({
                    "numeric_min": float(numeric.min()),
                    "numeric_max": float(numeric.max()),
                    "numeric_mean": float(numeric.mean()),
                    "numeric_std_sample": float(numeric.std(ddof=1)) if len(numeric) > 1 else None,
                    "iqr_outlier_count": int(((numeric < q1 - 1.5 * iqr) | (numeric > q3 + 1.5 * iqr)).sum()) if iqr > 0 else 0,
                })
        rows.append(row)
    duplicate_rows = int(frame.duplicated(keep="first").sum())
    warnings: list[str] = []
    if duplicate_rows:
        warnings.append(f"{duplicate_rows} duplicate row(s) were found; none were removed.")
    missing_columns = [str(name) for name in frame.columns if frame[name].isna().any()]
    if missing_columns:
        warnings.append(f"Missing values appear in {len(missing_columns)} column(s); source data was not changed.")
    if any(bool(row["constant_non_null"]) for row in rows):
        warnings.append("One or more columns are constant among non-missing values.")
    return {
        "status": "PROFILED",
        "method": "Non-destructive profile: missingness, distinct values, numeric summary and descriptive 1.5-IQR flags",
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "duplicate_row_count": duplicate_rows,
        "duplicate_row_pct": float(duplicate_rows / len(frame) * 100),
        "column_profile": pd.DataFrame(rows),
        "warnings": warnings,
        "source_unchanged": True,
    }


def join_dataframes(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_key: str,
    right_key: str,
    how: str = "left",
    max_rows: int = 250_000,
) -> dict[str, Any]:
    """Join tables with key/cardinality checks and an explicit row limit.

    A many-to-many join is rejected rather than risking an unexpected row
    explosion. Source frames are never mutated.
    """
    if not isinstance(left, pd.DataFrame) or not isinstance(right, pd.DataFrame):
        raise ValueError("Both inputs must be tabular DataFrames.")
    if left.empty or right.empty:
        raise ValueError("Both left and right tables must contain at least one row.")
    if len(left) > max_rows or len(right) > max_rows:
        raise ValueError(f"Each input table is limited to {max_rows:,} rows.")
    left_key, right_key = str(left_key).strip(), str(right_key).strip()
    if not left_key or left_key not in left.columns:
        raise ValueError("The selected left join key does not exist in the left table.")
    if not right_key or right_key not in right.columns:
        raise ValueError("The selected right join key does not exist in the right table.")
    if how not in {"inner", "left", "right", "outer"}:
        raise ValueError("Join type must be inner, left, right or outer.")
    left_duplicate_rows = int(left.loc[left[left_key].notna(), left_key].duplicated(keep=False).sum())
    right_duplicate_rows = int(right.loc[right[right_key].notna(), right_key].duplicated(keep=False).sum())
    if left_duplicate_rows and right_duplicate_rows:
        raise ValueError(
            "Both selected keys contain duplicates; this could create a many-to-many row explosion. "
            "Resolve duplicates or choose validated unique keys before joining."
        )
    if how == "outer" and len(left) + len(right) > max_rows:
        raise ValueError(f"An outer join is limited to {max_rows:,} potential output rows.")
    indicator_name = "_shoir_join_source"
    while indicator_name in left.columns or indicator_name in right.columns:
        indicator_name = "_" + indicator_name
    result = left.merge(
        right,
        left_on=left_key,
        right_on=right_key,
        how=how,
        indicator=indicator_name,
        suffixes=("_left", "_right"),
        sort=False,
    )
    if len(result) > max_rows:
        raise ValueError(f"The join would exceed the {max_rows:,}-row output limit.")
    left_key_values = set(left.loc[left[left_key].notna(), left_key].tolist())
    right_key_values = set(right.loc[right[right_key].notna(), right_key].tolist())
    left_unmatched = int((left[left_key].isna() | ~left[left_key].isin(right_key_values)).sum())
    right_unmatched = int((right[right_key].isna() | ~right[right_key].isin(left_key_values)).sum())
    warnings: list[str] = []
    if left_duplicate_rows or right_duplicate_rows:
        warnings.append("A one-to-many relationship exists. Output row count may exceed one source table.")
    if left_unmatched or right_unmatched:
        warnings.append("Some input keys do not match; unmatched-row counts are reported separately.")
    return {
        "status": "JOINED",
        "method": f"{how.upper()} join with duplicate-key profiling and source-row reconciliation",
        "join_type": how,
        "left_rows": int(len(left)),
        "right_rows": int(len(right)),
        "result_rows": int(len(result)),
        "left_duplicate_key_rows": left_duplicate_rows,
        "right_duplicate_key_rows": right_duplicate_rows,
        "left_unmatched_rows": left_unmatched,
        "right_unmatched_rows": right_unmatched,
        "source_rows_preserved": True,
        "warnings": warnings,
        "joined_data": result,
    }


def process_time_series(
    frame: pd.DataFrame,
    *,
    timestamp_column: str,
    value_columns: Sequence[str],
    local_timezone: str = "UTC",
    frequency: str | None = None,
    aggregation: str = "mean",
    duplicate_policy: str = "mean",
    max_rows: int = 250_000,
) -> dict[str, Any]:
    """Parse, sort and optionally resample a time series with explicit policies."""
    from zoneinfo import ZoneInfo

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("Provide a non-empty DataFrame for time-series processing.")
    if len(frame) > max_rows:
        raise ValueError(f"Time-series processing is limited to {max_rows:,} rows.")
    if timestamp_column not in frame.columns:
        raise ValueError(f"Timestamp column '{timestamp_column}' was not found.")
    if isinstance(value_columns, (str, bytes)):
        raise ValueError("Value columns must be supplied as a sequence of column names.")
    columns = list(dict.fromkeys(str(name).strip() for name in value_columns if str(name).strip()))
    if not columns:
        raise ValueError("Select at least one numeric value column.")
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise ValueError(f"Value column(s) not found: {', '.join(missing)}.")
    try:
        ZoneInfo(str(local_timezone))
    except Exception as exc:
        raise ValueError("Enter a valid IANA time zone, such as UTC or Asia/Riyadh.") from exc
    if aggregation not in {"mean", "sum", "min", "max", "median"}:
        raise ValueError("Aggregation must be mean, sum, min, max or median.")
    if duplicate_policy not in {"mean", "keep", "error"}:
        raise ValueError("Duplicate policy must be mean, keep or error.")

    warnings: list[str] = []
    try:
        parsed = pd.to_datetime(frame[timestamp_column], errors="coerce")
        if parsed.dt.tz is None:
            parsed = parsed.dt.tz_localize(local_timezone, ambiguous="NaT", nonexistent="NaT")
        else:
            parsed = parsed.dt.tz_convert(local_timezone)
    except (AttributeError, TypeError, ValueError):
        # Mixed aware offsets can produce object dtype. Normalize those timestamps
        # through UTC before converting to the requested display/analysis zone.
        parsed = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True).dt.tz_convert(local_timezone)
        warnings.append("Mixed timestamp offsets were normalized through UTC before local-time conversion.")
    invalid_timestamps = int(parsed.isna().sum())
    if invalid_timestamps:
        warnings.append(f"{invalid_timestamps} row(s) had invalid, ambiguous or nonexistent local timestamps and were excluded.")
    cleaned = pd.DataFrame({"_timestamp": parsed})
    numeric_conversion_failures = 0
    for column in columns:
        original = frame[column]
        numeric = pd.to_numeric(original, errors="coerce")
        numeric_conversion_failures += int((original.notna() & numeric.isna()).sum())
        cleaned[column] = numeric
    cleaned = cleaned.loc[cleaned["_timestamp"].notna()].sort_values("_timestamp", kind="stable")
    duplicate_count = int(cleaned["_timestamp"].duplicated(keep="first").sum())
    if duplicate_count and duplicate_policy == "error":
        raise ValueError(f"{duplicate_count} duplicate timestamp row(s) found; resolve them or choose a different policy.")
    if duplicate_count and duplicate_policy == "mean":
        cleaned = cleaned.groupby("_timestamp", as_index=False)[columns].mean()
    cleaned = cleaned.rename(columns={"_timestamp": "timestamp"})
    empty_period_count = 0
    if frequency and str(frequency).strip():
        try:
            indexed = cleaned.set_index("timestamp")
            observed_counts = indexed[columns].notna().any(axis=1).resample(str(frequency).strip()).sum()
            cleaned = indexed[columns].resample(str(frequency).strip()).agg(aggregation).reset_index()
            empty_period_count = int((observed_counts == 0).sum())
        except Exception as exc:
            raise ValueError(f"Resampling frequency or aggregation is invalid: {exc}") from exc
        if empty_period_count:
            warnings.append(f"{empty_period_count} resampled period(s) contain no valid source values.")
    if numeric_conversion_failures:
        warnings.append(f"{numeric_conversion_failures} non-numeric value(s) were converted to missing values.")
    if cleaned.empty:
        raise ValueError("No valid timestamped observations remain after parsing.")
    return {
        "status": "PROCESSED",
        "method": "Timestamp parsing, explicit timezone conversion, stable sort and optional resampling",
        "timestamp_column": str(timestamp_column),
        "timezone": str(local_timezone),
        "frequency": str(frequency).strip() if frequency and str(frequency).strip() else None,
        "aggregation": aggregation if frequency and str(frequency).strip() else None,
        "duplicate_policy": duplicate_policy,
        "source_rows": int(len(frame)),
        "processed_rows": int(len(cleaned)),
        "invalid_timestamp_rows": invalid_timestamps,
        "duplicate_timestamp_rows": duplicate_count,
        "numeric_conversion_failures": numeric_conversion_failures,
        "empty_resampled_periods": empty_period_count,
        "warnings": warnings,
        "series": cleaned,
    }


def generate_synthetic_industrial_data(*, row_count: int = 250, seed: int = 42) -> dict[str, Any]:
    """Generate repeatable hourly synthetic production data; never plant telemetry."""
    import numpy as np

    if isinstance(row_count, bool) or not isinstance(row_count, int) or not 1 <= row_count <= 100_000:
        raise ValueError("Synthetic row count must be a whole number from 1 to 100,000.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2_147_483_647:
        raise ValueError("Random seed must be a whole number from 0 to 2,147,483,647.")
    rng = np.random.default_rng(seed)
    timestamp = pd.date_range("2026-01-01 00:00:00", periods=row_count, freq="h", tz="UTC")
    line_id = rng.choice(["LINE-A", "LINE-B", "LINE-C"], size=row_count, p=[0.45, 0.35, 0.20])
    demand = rng.poisson(lam=72, size=row_count)
    cycle_seconds = np.clip(rng.normal(loc=42.0, scale=5.0, size=row_count), 20.0, 75.0)
    downtime_minutes = np.clip(rng.gamma(shape=1.7, scale=2.5, size=row_count), 0.0, 50.0)
    theoretical_capacity = np.floor(np.maximum(0.0, 3600.0 - downtime_minutes * 60.0) / cycle_seconds).astype(int)
    output = np.minimum(demand, theoretical_capacity)
    defect_rate = np.where(line_id == "LINE-C", 0.035, 0.02)
    defects = rng.binomial(n=output, p=defect_rate)
    energy_kwh = np.maximum(0.0, output * rng.normal(loc=0.42, scale=0.035, size=row_count))
    data = pd.DataFrame({
        "timestamp_utc": timestamp,
        "line_id": line_id,
        "demand_units": demand.astype(int),
        "cycle_time_seconds": cycle_seconds.round(3),
        "downtime_minutes": downtime_minutes.round(3),
        "output_units": output.astype(int),
        "defect_units": defects.astype(int),
        "good_units": (output - defects).astype(int),
        "energy_kwh": energy_kwh.round(4),
    })
    return {
        "status": "SYNTHETIC",
        "method": "Seeded hourly factory-line generator; values are artificial and not sampled from a real plant",
        "provenance": "SYNTHETIC",
        "row_count": int(row_count),
        "seed": int(seed),
        "parameters": {
            "start_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "line_ids": ["LINE-A", "LINE-B", "LINE-C"],
            "demand_distribution": "Poisson(lambda=72 units/hour)",
            "cycle_time_distribution": "Normal(mean=42 seconds, sd=5 seconds), clipped to 20–75 seconds",
            "downtime_distribution": "Gamma(shape=1.7, scale=2.5 minutes), clipped to 0–50 minutes",
        },
        "warning": "Synthetic teaching/test records only; never treat these values as live or measured plant performance.",
        "data": data,
    }


def plan_acceptance_sampling(
    *,
    aql_fraction: float = 0.01,
    ltpd_fraction: float = 0.05,
    producer_risk: float = 0.05,
    consumer_risk: float = 0.10,
    max_sample_size: int = 1500,
    max_acceptance_number: int = 50,
) -> dict[str, Any]:
    """Find the smallest single-sample plan satisfying binomial AQL/LTPD risks.

    This is a large-lot binomial approximation, not a substitute for a contractually
    required ISO/ANSI/ASQ sampling standard or a finite-lot hypergeometric plan.
    """
    from scipy.stats import binom

    aql = _finite_number(aql_fraction, "AQL defect fraction")
    ltpd = _finite_number(ltpd_fraction, "LTPD defect fraction")
    alpha = _finite_number(producer_risk, "Producer risk")
    beta = _finite_number(consumer_risk, "Consumer risk")
    if not 0 < aql < ltpd < 1:
        raise ValueError("AQL and LTPD must be fractions with 0 < AQL < LTPD < 1.")
    if not 0 < alpha < 1 or not 0 < beta < 1:
        raise ValueError("Producer and consumer risks must be strictly between zero and one.")
    if isinstance(max_sample_size, bool) or not isinstance(max_sample_size, int) or not 1 <= max_sample_size <= 5000:
        raise ValueError("Maximum sample size must be a whole number from 1 to 5,000.")
    if isinstance(max_acceptance_number, bool) or not isinstance(max_acceptance_number, int) or not 0 <= max_acceptance_number <= 100:
        raise ValueError("Maximum acceptance number must be a whole number from 0 to 100.")
    for n in range(1, max_sample_size + 1):
        for c in range(0, min(n, max_acceptance_number) + 1):
            p_accept_aql = float(binom.cdf(c, n, aql))
            p_accept_ltpd = float(binom.cdf(c, n, ltpd))
            if p_accept_aql >= 1.0 - alpha and p_accept_ltpd <= beta:
                return {
                    "status": "CALCULATED",
                    "method": "Smallest-n single-sample binomial operating-characteristic search",
                    "assumption": "Large lot; independent inspection outcomes; constant defect probability; no finite-lot correction.",
                    "aql_fraction": aql,
                    "ltpd_fraction": ltpd,
                    "producer_risk_target": alpha,
                    "consumer_risk_target": beta,
                    "sample_size_n": n,
                    "acceptance_number_c": c,
                    "rejection_number": c + 1,
                    "probability_accept_at_aql": p_accept_aql,
                    "probability_accept_at_ltpd": p_accept_ltpd,
                    "producer_risk_at_aql": 1.0 - p_accept_aql,
                    "consumer_risk_at_ltpd": p_accept_ltpd,
                    "max_sample_size_searched": max_sample_size,
                    "warning": "Plan is an analytical binomial approximation. Confirm the governing standard, lot size and contractual sampling rule before release inspection.",
                }
    return {
        "status": "LIMIT_REACHED",
        "method": "Smallest-n single-sample binomial operating-characteristic search",
        "assumption": "Large lot; independent inspection outcomes; constant defect probability; no finite-lot correction.",
        "sample_size_n": None,
        "acceptance_number_c": None,
        "probability_accept_at_aql": None,
        "probability_accept_at_ltpd": None,
        "message": "No plan satisfying both risks was found within the configured sample/acceptance limits. Increase search limits or review risk requirements.",
    }


def analyze_mm1_queue(
    arrival_rate: float,
    service_rate: float,
    *,
    rate_unit: str = "per minute",
) -> dict[str, Any]:
    """Calculate stable M/M/1 metrics under Poisson/exponential and FIFO assumptions."""
    lam = _finite_number(arrival_rate, "Arrival rate")
    mu = _finite_number(service_rate, "Service rate")
    unit = str(rate_unit).strip()
    if lam <= 0:
        raise ValueError("Arrival rate must be greater than zero.")
    if mu <= 0:
        raise ValueError("Service rate must be greater than zero.")
    if not unit:
        raise ValueError("State the time basis for the rates, such as per minute.")
    utilization = lam / mu
    assumptions = [
        "Single server, FIFO discipline, steady-state M/M/1 queue.",
        "Poisson arrivals and independent exponentially distributed service times.",
        "Arrival and service rates must use the same unit and population definition.",
    ]
    if utilization >= 1.0:
        return {
            "status": "UNSTABLE",
            "method": "M/M/1 analytical queue",
            "arrival_rate": lam,
            "service_rate": mu,
            "rate_unit": unit,
            "utilization_fraction": utilization,
            "utilization_pct": utilization * 100.0,
            "mean_customers_in_system": None,
            "mean_customers_in_queue": None,
            "mean_time_in_system": None,
            "mean_waiting_time_in_queue": None,
            "assumptions": assumptions,
            "warning": "Arrival rate is at least the service rate; no finite steady-state queue/wait estimates are reported.",
        }
    mean_system = utilization / (1.0 - utilization)
    mean_queue = utilization * utilization / (1.0 - utilization)
    mean_system_time = 1.0 / (mu - lam)
    mean_queue_time = utilization / (mu - lam)
    return {
        "status": "STABLE",
        "method": "M/M/1 analytical queue",
        "arrival_rate": lam,
        "service_rate": mu,
        "rate_unit": unit,
        "utilization_fraction": utilization,
        "utilization_pct": utilization * 100.0,
        "mean_customers_in_system": mean_system,
        "mean_customers_in_queue": mean_queue,
        "mean_time_in_system": mean_system_time,
        "mean_waiting_time_in_queue": mean_queue_time,
        "time_unit": f"time units implied by rates ({unit})",
        "assumptions": assumptions,
        "warning": "Analytical estimate under M/M/1 assumptions; validate the arrival/service distributions and actual queue discipline.",
    }
