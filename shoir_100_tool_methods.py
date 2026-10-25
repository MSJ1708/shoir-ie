"""Deterministic, scoped methods for selected Shoir-IE 100-tool targets.

These functions expose declared methods and limits. They do not replace authenticated
browser acceptance, persistent workspace storage, or source-system validation.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import binom, weibull_min
from scipy.special import gamma
from statistics import NormalDist


METHOD_VERSION = "1.0.0"
MAX_ROWS = 250_000


def _finite(value: Any, name: str) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    return value


def _frame(value: Any, name: str = "Dataset") -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise ValueError(f"{name} must be a table.")
    if value.empty or len(value) > MAX_ROWS:
        raise ValueError(f"{name} must contain between 1 and {MAX_ROWS:,} rows.")
    if not len(value.columns) or not value.columns.is_unique:
        raise ValueError(f"{name} must have columns with unique names.")
    return value


def require_tool_access(tier: str, tool_id: str, actor: str) -> dict[str, Any]:
    """Enforce canonical target IDs at execution time and deny unknown inputs."""
    from shoir_100_tool_registry import TOOL_CATALOG
    from shoir_tier_capabilities import tier_allows

    raw = str(tier or "").strip().casefold()
    allowed_names = (
        "Starter", "Mid-Tier Pro", "Professional", "Enterprise",
        "Enterprise Plus", "Research Pack",
    )
    canonical = {}
    for name in allowed_names:
        canonical[name.casefold()] = name
        canonical[(name + " tier").casefold()] = name
        canonical[(name + " plan").casefold()] = name
    # Real app registration/renewal flows store price-bearing tier labels.
    # Normalize only explicit supported labels; unknown labels remain denied.
    explicit_aliases = {
        "starter tier ($29)": "Starter",
        "mid-tier pro ($79)": "Mid-Tier Pro",
        "professional tier ($129)": "Professional",
        "enterprise tier ($199)": "Enterprise",
        "enterprise plus tier ($399)": "Enterprise Plus",
        "research pack ($30 add-on)": "Research Pack",
        "research pack add-on": "Research Pack",
    }
    canonical.update(explicit_aliases)
    current = canonical.get(raw)
    if current is None:
        raise PermissionError("Unrecognized subscription tier; access is denied by default.")
    identity = str(actor or "").strip().casefold()
    if not identity or identity in {"guest", "anonymous", "none", "null", "unauthenticated"}:
        raise PermissionError("Sign in with an authorized account before running this tool.")
    tool = next((row for row in TOOL_CATALOG if row.get("tool_id") == str(tool_id).strip()), None)
    if tool is None:
        raise PermissionError("Unknown Shoir-IE tool ID; access is denied by default.")
    required = str(tool.get("target_minimum_tier", "")).strip()
    if required not in allowed_names or not tier_allows(current, required):
        raise PermissionError(f"{tool.get('canonical_name', tool_id)} requires the {required or 'mapped'} tier.")
    return tool


def profile_dataframe(frame: pd.DataFrame) -> dict[str, Any]:
    """Describe missingness, duplicates, types, numeric ranges and IQR flags."""
    frame = _frame(frame)
    rows = []
    for column in frame.columns:
        series = frame[column]
        nonmissing = series.dropna()
        numeric = pd.to_numeric(nonmissing, errors="coerce")
        wholly_numeric = len(nonmissing) > 0 and int(numeric.notna().sum()) == len(nonmissing)
        metrics: dict[str, Any] = {}
        if wholly_numeric:
            arr = numeric.astype(float)
            q1, q3 = float(arr.quantile(.25)), float(arr.quantile(.75))
            iqr = q3 - q1
            metrics = {
                "mean": float(arr.mean()), "sample_std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
                "min": float(arr.min()), "max": float(arr.max()),
                "iqr_outlier_count": int(((arr < q1 - 1.5 * iqr) | (arr > q3 + 1.5 * iqr)).sum()),
            }
        rows.append({
            "column": str(column), "dtype": str(series.dtype), "row_count": len(frame),
            "missing_count": int(series.isna().sum()),
            "missing_pct": round(float(series.isna().mean() * 100), 4),
            "unique_nonmissing": int(series.nunique(dropna=True)),
            "numeric_profile": wholly_numeric, **metrics,
        })
    return {
        "status": "PROFILED", "tool_id": "T013", "method_version": METHOD_VERSION,
        "row_count": len(frame), "column_count": len(frame.columns),
        "duplicate_row_count": int(frame.duplicated().sum()),
        "missing_cell_count": int(frame.isna().sum().sum()),
        "columns": pd.DataFrame(rows),
        "warnings": ["IQR outliers are review flags, not proof of bad data.",
                     "Profiling is read-only; no source rows were removed."],
    }


def join_dataframes(
    left: pd.DataFrame, right: pd.DataFrame, left_keys: Sequence[str],
    right_keys: Sequence[str] | None = None, how: str = "left",
    cardinality: str = "many_to_one", confirm_many_to_many: bool = False,
) -> dict[str, Any]:
    """Join tables with null-key and cardinality checks plus row reconciliation."""
    left, right = _frame(left, "Left table"), _frame(right, "Right table")
    lk = [str(k) for k in left_keys]
    rk = [str(k) for k in (right_keys if right_keys is not None else left_keys)]
    if not lk or len(lk) != len(rk) or any(k not in left.columns for k in lk) or any(k not in right.columns for k in rk):
        raise ValueError("Select matching, existing key columns on both tables.")
    if how not in {"left", "right", "inner", "outer"}:
        raise ValueError("Join type must be left, right, inner, or outer.")
    if cardinality not in {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}:
        raise ValueError("Choose an explicit supported join cardinality.")
    if left[lk].isna().any().any() or right[rk].isna().any().any():
        raise ValueError("Null join keys are blocked; clean or explicitly resolve them before joining.")
    left_dups = int(left.duplicated(subset=lk, keep=False).sum())
    right_dups = int(right.duplicated(subset=rk, keep=False).sum())
    if cardinality == "many_to_many" and not confirm_many_to_many:
        raise ValueError("Many-to-many join is blocked until its row-multiplication risk is explicitly confirmed.")
    try:
        result = left.merge(
            right, how=how, left_on=lk, right_on=rk, sort=False,
            validate=None if cardinality == "many_to_many" else cardinality,
            indicator="_join_status", suffixes=("_left", "_right"),
        )
    except pd.errors.MergeError as exc:
        raise ValueError(f"Join violates the declared {cardinality.replace('_', ' ')} contract: {exc}") from exc
    counts = result["_join_status"].value_counts().to_dict()
    result = result.drop(columns=["_join_status"])
    if len(result) > MAX_ROWS:
        raise ValueError(f"Join would produce more than {MAX_ROWS:,} rows; no output was committed.")
    return {
        "status": "JOINED", "tool_id": "T017", "method_version": METHOD_VERSION,
        "method": f"{how} join with declared {cardinality} relationship",
        "left_rows": len(left), "right_rows": len(right), "output_rows": len(result),
        "left_duplicate_key_rows": left_dups, "right_duplicate_key_rows": right_dups,
        "join_status_counts": {str(k): int(v) for k, v in counts.items()},
        "data": result,
        "warnings": ["Input tables were not modified.",
                     "Row counts can change according to join type and matching keys."],
    }


def process_time_series(
    frame: pd.DataFrame, timestamp_column: str, value_columns: Sequence[str],
    target_timezone: str = "UTC", resample_rule: str = "",
    aggregation: str = "mean",
) -> dict[str, Any]:
    """Normalize timestamps, sort records and optionally resample explicitly."""
    frame = _frame(frame)
    if timestamp_column not in frame.columns:
        raise ValueError("Choose an existing timestamp column.")
    values = [str(c) for c in value_columns]
    if not values or any(c not in frame.columns for c in values):
        raise ValueError("Choose at least one existing measurement column.")
    if aggregation not in {"mean", "sum", "min", "max", "last", "first"}:
        raise ValueError("Aggregation must be mean, sum, min, max, last, or first.")
    parsed = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True)
    bad = int(parsed.isna().sum())
    valid = frame.loc[parsed.notna()].copy()
    valid["_timestamp_utc"] = parsed.loc[parsed.notna()]
    if valid.empty:
        raise ValueError("No valid timestamps were found; the input table was not modified.")
    try:
        valid["_timestamp"] = valid["_timestamp_utc"].dt.tz_convert(target_timezone)
    except Exception as exc:
        raise ValueError(f"Unsupported timezone: {target_timezone}") from exc
    dupes = int(valid["_timestamp"].duplicated(keep=False).sum())
    valid = valid.sort_values("_timestamp", kind="stable")
    numeric = valid[values].apply(pd.to_numeric, errors="coerce")
    bad_numeric = int(numeric.isna().sum().sum())
    valid[values] = numeric
    valid = valid.drop(columns=["_timestamp_utc"])
    diffs = valid["_timestamp"].diff().dropna().dt.total_seconds()
    gap_count = 0
    median_interval = float(diffs.median()) if not diffs.empty else None
    if median_interval and median_interval > 0:
        gap_count = int((diffs > 1.5 * median_interval).sum())
    output = valid.set_index("_timestamp")
    output.index.name = "timestamp"
    output = output.drop(columns=[timestamp_column], errors="ignore")
    resampled_rows = None
    if str(resample_rule or "").strip():
        try:
            if aggregation == "last":
                output = output[values].resample(resample_rule).last()
            elif aggregation == "first":
                output = output[values].resample(resample_rule).first()
            else:
                output = getattr(output[values].resample(resample_rule), aggregation)()
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid resample rule or aggregation: {exc}") from exc
        resampled_rows = len(output)
    output = output.reset_index()
    return {
        "status": "PROCESSED", "tool_id": "T018", "method_version": METHOD_VERSION,
        "method": "Timestamp parse to UTC, convert to selected timezone, stable chronological sort; optional explicit resampling.",
        "rows_in": len(frame), "rows_out": len(output), "invalid_timestamp_rows": bad,
        "duplicate_timestamp_rows": dupes, "numeric_missing_or_invalid_cells": bad_numeric,
        "gap_count_vs_median_interval": gap_count, "median_interval_seconds": median_interval,
        "resampled_rows": resampled_rows, "data": output,
        "warnings": ["Timezone-naive source timestamps are interpreted as UTC by pandas.",
                     "Resampling may aggregate or create empty time bins; review the row counts.",
                     "Invalid timestamps were excluded from the processed output."],
    }


def generate_synthetic_industrial_data(
    rows: int = 250, seed: int = 42, start_date: str = "2026-01-01",
) -> dict[str, Any]:
    """Create reproducible, visibly synthetic production observations."""
    rows = int(_finite(rows, "Row count"))
    seed = int(_finite(seed, "Random seed"))
    if rows < 1 or rows > 10_000:
        raise ValueError("Synthetic row count must be between 1 and 10,000.")
    if seed < 0 or seed > 2**32 - 1:
        raise ValueError("Random seed must be between 0 and 4,294,967,295.")
    try:
        start = pd.Timestamp(date.fromisoformat(str(start_date)))
    except ValueError as exc:
        raise ValueError("Start date must be a valid YYYY-MM-DD date.") from exc
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        "timestamp": start + pd.to_timedelta(np.arange(rows), unit="h"),
        "asset_id": rng.choice(["SYN-M01", "SYN-M02", "SYN-M03"], size=rows),
        "units_produced": rng.poisson(48, size=rows),
        "cycle_time_seconds": np.round(rng.normal(72, 6, size=rows).clip(35, 120), 2),
        "defect_count": rng.binomial(48, 0.025, size=rows),
        "energy_kwh": np.round(rng.normal(21, 2.5, size=rows).clip(1), 3),
    })
    frame["data_status"] = "SYNTHETIC"
    return {
        "status": "GENERATED", "tool_id": "T019", "method_version": METHOD_VERSION,
        "seed": seed, "row_count": rows, "data": frame,
        "provenance": "Synthetic values generated locally from documented seeded distributions; not plant measurements.",
        "warnings": ["Synthetic data must not be presented as live observations or verified savings."],
    }


def acceptance_sampling_oc(
    sample_size: int, acceptance_number: int, aql_percent: float, ltpd_percent: float,
) -> dict[str, Any]:
    """Evaluate an explicitly specified single-sample binomial OC plan."""
    if isinstance(sample_size, bool) or int(sample_size) != sample_size or sample_size < 1 or sample_size > 1_000_000:
        raise ValueError("Sample size must be a whole number from 1 to 1,000,000.")
    if isinstance(acceptance_number, bool) or int(acceptance_number) != acceptance_number or acceptance_number < 0 or acceptance_number >= sample_size:
        raise ValueError("Acceptance number must be a whole number from zero to sample size minus one.")
    aql, ltpd = _finite(aql_percent, "AQL") / 100.0, _finite(ltpd_percent, "LTPD") / 100.0
    if not 0 < aql < ltpd < 1:
        raise ValueError("Require 0% < AQL < LTPD < 100%.")
    n, c = int(sample_size), int(acceptance_number)
    pa_aql = float(binom.cdf(c, n, aql))
    pa_ltpd = float(binom.cdf(c, n, ltpd))
    return {
        "status": "CALCULATED", "tool_id": "T034", "method_version": METHOD_VERSION,
        "method": "Single-sample binomial operating-characteristic calculation for a large-lot approximation.",
        "sample_size": n, "acceptance_number": c, "aql_percent": aql_percent, "ltpd_percent": ltpd_percent,
        "probability_accept_at_aql": pa_aql, "producer_risk_at_aql": 1.0 - pa_aql,
        "probability_accept_at_ltpd": pa_ltpd, "consumer_risk_at_ltpd": pa_ltpd,
        "warnings": ["This evaluates the user-specified plan; it does not select a standards-certified plan.",
                     "Finite-lot correction, switching rules, and formal standard compliance are not included."],
    }


def mm1_queue(arrival_rate: float, service_rate: float, time_unit: str = "hour") -> dict[str, Any]:
    """Analytical steady-state M/M/1 queue; rates must share one time unit."""
    lam = _finite(arrival_rate, "Arrival rate")
    mu = _finite(service_rate, "Service rate")
    unit = str(time_unit or "").strip()
    if lam <= 0 or mu <= 0:
        raise ValueError("Arrival and service rates must both be greater than zero.")
    if not unit or len(unit) > 30:
        raise ValueError("Provide a valid common time unit such as hour or minute.")
    rho = lam / mu
    if rho >= 1:
        return {
            "status": "UNSTABLE", "tool_id": "T070", "method_version": METHOD_VERSION,
            "arrival_rate": lam, "service_rate": mu, "utilization": rho,
            "time_unit": unit,
            "warnings": ["M/M/1 steady state does not exist because arrival rate must be lower than service rate."],
        }
    lq = rho * rho / (1.0 - rho)
    l = rho / (1.0 - rho)
    wq = lq / lam
    w = 1.0 / (mu - lam)
    return {
        "status": "CALCULATED", "tool_id": "T070", "method_version": METHOD_VERSION,
        "method": "Steady-state M/M/1 queueing equations; Poisson arrivals, exponential service, one server, FCFS, infinite buffer/population.",
        "arrival_rate": lam, "service_rate": mu, "utilization": rho,
        "Lq_expected_queue_length": lq, "L_expected_system_length": l,
        "Wq_expected_wait": wq, "W_expected_system_time": w,
        "time_unit": unit, "assumptions": ["Arrival and service rates use the same time basis.",
                                             "No balking, reneging, batching, or finite capacity."],
        "warnings": ["Analytical M/M/1 estimate; not a discrete-event simulation or measured plant result."],
    }


def cost_variance(components: Sequence[Mapping[str, Any]], currency: str) -> dict[str, Any]:
    """Reconcile actual, standard and planned costs using explicit components."""
    unit = str(currency or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", unit):
        raise ValueError("Provide a three-letter currency code such as SAR, USD, or EUR.")
    if not isinstance(components, Sequence) or isinstance(components, (str, bytes)) or not components:
        raise ValueError("Provide at least one cost component.")
    records, seen = [], set()
    for index, row in enumerate(components, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Cost component {index} must be a mapping.")
        name = str(row.get("component", "")).strip()
        if not name or name in seen:
            raise ValueError(f"Cost component {index} needs a unique, non-empty name.")
        seen.add(name)
        actual = _finite(row.get("actual"), f"{name} actual")
        standard = _finite(row.get("standard"), f"{name} standard")
        plan = _finite(row.get("plan"), f"{name} plan")
        if min(actual, standard, plan) < 0:
            raise ValueError(f"{name} costs cannot be negative; record credits separately.")
        records.append({
            "component": name, "actual_cost": actual, "standard_cost": standard, "plan_cost": plan,
            "actual_minus_standard": actual - standard, "actual_minus_plan": actual - plan,
            "standard_variance": "UNFAVORABLE" if actual > standard else "FAVORABLE" if actual < standard else "ON STANDARD",
            "plan_variance": "UNFAVORABLE" if actual > plan else "FAVORABLE" if actual < plan else "ON PLAN",
        })
    table = pd.DataFrame(records)
    totals = {column: float(table[column].sum()) for column in (
        "actual_cost", "standard_cost", "plan_cost", "actual_minus_standard", "actual_minus_plan"
    )}
    return {
        "status": "RECONCILED", "tool_id": "T082", "method_version": METHOD_VERSION,
        "currency": unit, "components": table, "totals": totals,
        "method": "Component-wise actual minus standard and actual minus plan; positive cost variance is unfavorable.",
        "warnings": ["Variance is only as complete as supplied component definitions and period scope.",
                     "Arithmetic does not independently verify source ledgers or prove realized savings."],
    }


def portfolio_score(
    projects: Sequence[Mapping[str, Any]], weights: Mapping[str, Any],
    rating_min: float = 0.0, rating_max: float = 5.0,
) -> dict[str, Any]:
    """Rank projects by transparent weighted scores and ±10% weight screening."""
    if not isinstance(projects, Sequence) or isinstance(projects, (str, bytes)) or not projects:
        raise ValueError("Provide at least one project with criterion scores.")
    if not isinstance(weights, Mapping) or not weights:
        raise ValueError("Provide positive weights for the scoring criteria.")
    low, high = _finite(rating_min, "Minimum rating"), _finite(rating_max, "Maximum rating")
    if high <= low:
        raise ValueError("Maximum rating must be greater than minimum rating.")
    clean_weights = {str(k).strip(): _finite(v, f"Weight for {k}") for k, v in weights.items()}
    if any(not key for key in clean_weights) or any(value < 0 for value in clean_weights.values()) or sum(clean_weights.values()) <= 0:
        raise ValueError("Criterion names must be non-empty; weights must be non-negative with positive total.")
    names, rows = set(), []
    for index, project in enumerate(projects, 1):
        if not isinstance(project, Mapping):
            raise ValueError(f"Project {index} must be a mapping.")
        name = str(project.get("name", "")).strip()
        scores = project.get("scores")
        if not name or name in names or not isinstance(scores, Mapping):
            raise ValueError(f"Project {index} needs a unique name and a score mapping.")
        names.add(name)
        missing = set(clean_weights) - set(scores)
        if missing:
            raise ValueError(f"{name} is missing criterion scores: {sorted(missing)}.")
        clean_scores = {key: _finite(scores[key], f"{name} score for {key}") for key in clean_weights}
        if any(value < low or value > high for value in clean_scores.values()):
            raise ValueError(f"{name} scores must be between {low:g} and {high:g}.")
        normalized_scores = {key: (value - low) / (high - low) for key, value in clean_scores.items()}
        total_weight = sum(clean_weights.values())
        score_pct = sum(normalized_scores[k] * clean_weights[k] / total_weight for k in clean_weights) * 100.0
        rows.append({"project": name, "weighted_score_pct": score_pct, **{f"rating_{k}": v for k, v in clean_scores.items()}})
    scores_df = pd.DataFrame(rows).sort_values(["weighted_score_pct", "project"], ascending=[False, True], kind="stable").reset_index(drop=True)
    scores_df.insert(0, "rank", np.arange(1, len(scores_df) + 1))
    normalized_weights = {key: value / sum(clean_weights.values()) for key, value in clean_weights.items()}
    base_ranks = dict(zip(scores_df["project"], scores_df["rank"]))
    sensitivity = {name: {"base_rank": int(rank), "best_rank": int(rank), "worst_rank": int(rank)} for name, rank in base_ranks.items()}
    for criterion in clean_weights:
        for factor in (0.9, 1.1):
            trial = dict(clean_weights)
            trial[criterion] *= factor
            denominator = sum(trial.values())
            trial_scores = []
            for project in projects:
                score_map = project["scores"]
                score = sum(((float(score_map[k]) - low) / (high - low)) * trial[k] / denominator for k in clean_weights) * 100.0
                trial_scores.append((str(project["name"]), score))
            order = [name for name, _ in sorted(trial_scores, key=lambda item: (-item[1], item[0]))]
            for rank, name in enumerate(order, 1):
                sensitivity[name]["best_rank"] = min(sensitivity[name]["best_rank"], rank)
                sensitivity[name]["worst_rank"] = max(sensitivity[name]["worst_rank"], rank)
    return {
        "status": "SCORED", "tool_id": "T084", "method_version": METHOD_VERSION,
        "method": "Min-max normalized criterion ratings combined by declared non-negative weights normalized to sum to one.",
        "weights": pd.DataFrame([{"criterion": k, "raw_weight": clean_weights[k], "normalized_weight_pct": normalized_weights[k] * 100.0} for k in clean_weights]),
        "scores": scores_df, "sensitivity": pd.DataFrame([{"project": name, **value} for name, value in sensitivity.items()]),
        "rating_min": low, "rating_max": high,
        "warnings": ["Criteria, ratings and weights are subjective decision inputs, not objective truth.",
                     "Sensitivity is a limited ±10% one-weight-at-a-time rank screen, not a probabilistic uncertainty model."],
    }


def line_balance(tasks: Sequence[Mapping[str, Any]], cycle_time: float) -> dict[str, Any]:
    """Assign precedence-constrained tasks by a largest-eligible-task heuristic."""
    cycle = _finite(cycle_time, "Cycle time")
    if cycle <= 0:
        raise ValueError("Cycle time must be greater than zero.")
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)) or not tasks:
        raise ValueError("Provide a task list with duration and predecessor definitions.")
    rows, by_name = [], {}
    for i, item in enumerate(tasks, 1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Task row {i} must be a mapping.")
        name = str(item.get("task", "")).strip()
        duration = _finite(item.get("duration"), f"{name or i} duration")
        pred_raw = item.get("predecessors", "")
        predecessors = [p.strip() for p in str(pred_raw or "").split(",") if p.strip()]
        if not name or name in by_name:
            raise ValueError(f"Task row {i} needs a unique non-empty task name.")
        if duration <= 0 or duration > cycle:
            raise ValueError(f"Task {name} duration must be > 0 and <= cycle time.")
        by_name[name] = {"task": name, "duration": duration, "predecessors": predecessors}
        rows.append(by_name[name])
    for item in rows:
        unknown = set(item["predecessors"]) - set(by_name)
        if unknown or item["task"] in item["predecessors"]:
            raise ValueError(f"Task {item['task']} has unknown or self predecessors: {sorted(unknown)}.")
    remaining = set(by_name)
    completed: set[str] = set()
    assignments = []
    station_loads = []
    station = 0
    while remaining:
        eligible = [name for name in remaining if set(by_name[name]["predecessors"]).issubset(completed)]
        if not eligible:
            raise ValueError("Task precedence contains a cycle or unresolved dependency.")
        station += 1
        load = 0.0
        while True:
            eligible = [name for name in remaining if set(by_name[name]["predecessors"]).issubset(completed)]
            fitting = [name for name in eligible if load + by_name[name]["duration"] <= cycle + 1e-9]
            if not fitting:
                break
            chosen = sorted(fitting, key=lambda name: (-by_name[name]["duration"], name))[0]
            task = by_name[chosen]
            assignments.append({"task": chosen, "duration": task["duration"], "predecessors": ", ".join(task["predecessors"]), "station": station, "station_sequence": sum(a["station"] == station for a in assignments) + 1})
            load += task["duration"]
            completed.add(chosen)
            remaining.remove(chosen)
        station_loads.append({"station": station, "work_content": load, "cycle_time": cycle, "idle_time": cycle-load, "utilization_pct": load/cycle*100.0})
    total = sum(row["duration"] for row in rows)
    minimum = math.ceil(total / cycle)
    efficiency = total / (station * cycle)
    smoothness = math.sqrt(sum((cycle - row["work_content"]) ** 2 for row in station_loads))
    return {
        "status": "HEURISTIC_BALANCED", "tool_id": "T024", "method_version": METHOD_VERSION,
        "method": "Largest eligible task heuristic with precedence constraints; this is not a proof of global optimality.",
        "tasks": pd.DataFrame(assignments), "stations": pd.DataFrame(station_loads),
        "total_work_content": total, "cycle_time": cycle, "station_count": station,
        "theoretical_minimum_stations": minimum, "efficiency_pct": efficiency*100.0,
        "balance_delay_pct": (1-efficiency)*100.0, "smoothness_index": smoothness,
        "warnings": ["Task durations and precedence relationships are user inputs and should be validated against observed work.",
                     "A feasible heuristic assignment is not necessarily the optimal line balance."],
    }


def root_cause_analysis(
    items: Sequence[Mapping[str, Any]], five_whys: Sequence[str] | None = None,
    action_owner: str = "", action: str = "", due_date: str = "",
) -> dict[str, Any]:
    """Build a Pareto table and optionally record a reviewed five-why hypothesis."""
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or not items:
        raise ValueError("Provide at least one category and count.")
    totals: dict[str, float] = {}
    for i, row in enumerate(items, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Cause row {i} must be a mapping.")
        category = str(row.get("category", "")).strip()
        count = _finite(row.get("count"), f"{category or i} count")
        if not category or count < 0:
            raise ValueError(f"Cause row {i} needs a name and a non-negative count.")
        totals[category] = totals.get(category, 0.0) + count
    total = sum(totals.values())
    if total <= 0:
        raise ValueError("At least one cause count must be greater than zero.")
    pareto = pd.DataFrame([{"category": key, "count": count} for key, count in totals.items()])
    pareto = pareto.sort_values(["count", "category"], ascending=[False, True], kind="stable").reset_index(drop=True)
    pareto["share_pct"] = pareto["count"] / total * 100.0
    pareto["cumulative_share_pct"] = pareto["share_pct"].cumsum()
    whys = [str(x).strip() for x in (five_whys or [])]
    if whys and (len(whys) != 5 or any(not x for x in whys)):
        raise ValueError("Provide either no five-why answers or exactly five non-empty answers.")
    action_text, owner_text, due_text = str(action or "").strip(), str(action_owner or "").strip(), str(due_date or "").strip()
    action_record = {"owner": owner_text, "action": action_text, "due_date": due_text, "status": "ACTION_RECORDED" if action_text and owner_text else "ACTION_INCOMPLETE"}
    return {
        "status": "ANALYZED", "tool_id": "T028", "method_version": METHOD_VERSION,
        "method": "Frequency/cost Pareto ranking; the five-why chain is a hypothesis for review, not proven causation.",
        "pareto": pareto, "total_count": total, "five_whys": pd.DataFrame([{"why_level": i+1, "statement": w} for i, w in enumerate(whys)]),
        "action": action_record,
        "warnings": ["Pareto ranking does not establish causation.",
                     "Five-why responses and countermeasures should be checked against evidence and reviewed with process owners."],
    }


def audit_5s(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Score documented 5S checklist observations while preserving action/evidence fields."""
    categories = {"Sort", "Set in order", "Shine", "Standardize", "Sustain"}
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("Provide at least one 5S audit checklist row.")
    clean, seen = [], set()
    for i, row in enumerate(records, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Audit row {i} must be a mapping.")
        area, category = str(row.get("area", "")).strip(), str(row.get("category", "")).strip()
        score = _finite(row.get("score"), f"{area or i} score")
        if not area or category not in categories:
            raise ValueError(f"Audit row {i} must include an area and one of the five 5S categories.")
        key = (area, category)
        if key in seen:
            raise ValueError(f"Duplicate 5S category {category} for area {area}.")
        seen.add(key)
        if score < 0 or score > 5:
            raise ValueError("5S score must be between 0 and 5.")
        clean.append({
            "area": area, "category": category, "score": score, "score_pct": score/5*100.0,
            "evidence": str(row.get("evidence", "") or "").strip(),
            "owner": str(row.get("owner", "") or "").strip(),
            "action": str(row.get("action", "") or "").strip(),
            "due_date": str(row.get("due_date", "") or "").strip(),
        })
    details = pd.DataFrame(clean)
    by_area = details.groupby("area", as_index=False).agg(
        average_score=("score", "mean"), score_pct=("score_pct", "mean"),
        checklist_items=("category", "count"),
    ).sort_values(["score_pct", "area"], ascending=[True, True], kind="stable")
    by_category = details.groupby("category", as_index=False).agg(
        average_score=("score", "mean"), score_pct=("score_pct", "mean"),
        checklist_items=("area", "count"),
    ).sort_values(["score_pct", "category"], ascending=[True, True], kind="stable")
    return {
        "status": "AUDIT_SCORED", "tool_id": "T029", "method_version": METHOD_VERSION,
        "method": "User-rated 0–5 checklist score; score percent = rating / 5 × 100.",
        "details": details, "area_summary": by_area, "category_summary": by_category,
        "overall_score_pct": float(details["score_pct"].mean()),
        "actions_open": int(((details["action"] != "") & (details["owner"] == "")).sum()),
        "warnings": ["This is a structured workplace audit record, not a certified safety or regulatory inspection.",
                     "Scores depend on defined rubric, evidence quality and reviewer consistency."],
    }


def a3_improvement(
    title: str, problem: str, metric: str, unit: str, baseline: float, target: float,
    direction: str, countermeasure: str, owner: str, due_date: str,
    actual: float | None = None, actual_evidence: str = "", implementation_cost: float = 0.0,
) -> dict[str, Any]:
    """Structure an A3 improvement plan and keep estimated vs evidenced outcomes separate."""
    title, problem, metric, unit = (str(x or "").strip() for x in (title, problem, metric, unit))
    countermeasure, owner, due_date, evidence = (str(x or "").strip() for x in (countermeasure, owner, due_date, actual_evidence))
    if not all((title, problem, metric, unit, countermeasure, owner, due_date)):
        raise ValueError("Provide title, problem, metric/unit, countermeasure, owner and due date.")
    base, target_value = _finite(baseline, "Baseline"), _finite(target, "Target")
    cost = _finite(implementation_cost, "Implementation cost")
    if cost < 0 or direction not in {"lower", "higher"}:
        raise ValueError("Implementation cost cannot be negative; direction must be lower or higher.")
    actual_value = None if actual is None else _finite(actual, "Actual post-change result")
    target_met = None if actual_value is None else (actual_value <= target_value if direction == "lower" else actual_value >= target_value)
    improvement = None
    if actual_value is not None:
        improvement = base - actual_value if direction == "lower" else actual_value - base
    evidence_complete = actual_value is not None and bool(evidence)
    return {
        "status": "ACTUAL_AND_EVIDENCE_RECORDED" if evidence_complete else "PLAN_ONLY_OR_UNVERIFIED",
        "tool_id": "T030", "method_version": METHOD_VERSION,
        "title": title, "problem": problem, "metric": metric, "unit": unit,
        "baseline": base, "target": target_value, "direction": direction,
        "countermeasure": countermeasure, "owner": owner, "due_date": due_date,
        "actual_post_change": actual_value, "absolute_improvement": improvement,
        "percent_improvement": None if actual_value is None or base == 0 else improvement / abs(base) * 100.0,
        "target_met": target_met, "implementation_cost": cost,
        "actual_evidence": evidence,
        "actual_measurement_recorded": actual_value is not None,
        "evidence_reference_recorded": bool(evidence),
        "verification_status": "PENDING_REVIEW" if evidence_complete else "NOT_SUBMITTED",
        "outcome_verified": False,
        "warnings": ["A3 plan data alone is not proof of realized benefit.",
                     "Outcome is only marked evidence-recorded when an actual result and an evidence reference are supplied."],
    }


def quality_cost_analysis(records: Sequence[Mapping[str, Any]], currency: str) -> dict[str, Any]:
    """Calculate defect-related scrap, rework and inspection cost from supplied records."""
    unit = str(currency or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", unit):
        raise ValueError("Provide a three-letter currency code such as SAR, USD, or EUR.")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("Provide at least one defect/cost record.")
    out = []
    for i, row in enumerate(records, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Defect row {i} must be a mapping.")
        name = str(row.get("defect_type", "")).strip()
        if not name:
            raise ValueError(f"Defect row {i} needs a defect type.")
        scrap_qty = _finite(row.get("scrap_qty", 0), f"{name} scrap quantity")
        scrap_unit_cost = _finite(row.get("scrap_unit_cost", 0), f"{name} scrap unit cost")
        rework_hours = _finite(row.get("rework_hours", 0), f"{name} rework hours")
        rework_rate = _finite(row.get("rework_cost_per_hour", 0), f"{name} rework rate")
        inspection = _finite(row.get("inspection_cost", 0), f"{name} inspection cost")
        if min(scrap_qty, scrap_unit_cost, rework_hours, rework_rate, inspection) < 0:
            raise ValueError(f"{name} cost quantities and rates cannot be negative.")
        scrap_cost, rework_cost = scrap_qty * scrap_unit_cost, rework_hours * rework_rate
        out.append({
            "defect_type": name, "scrap_qty": scrap_qty, "scrap_cost": scrap_cost,
            "rework_hours": rework_hours, "rework_cost": rework_cost,
            "inspection_cost": inspection, "cost_of_poor_quality": scrap_cost+rework_cost+inspection,
        })
    details = pd.DataFrame(out)
    totals = {column: float(details[column].sum()) for column in ("scrap_cost", "rework_cost", "inspection_cost", "cost_of_poor_quality")}
    return {
        "status": "COSTED", "tool_id": "T040", "method_version": METHOD_VERSION,
        "currency": unit, "details": details, "totals": totals,
        "method": "Cost of poor quality = modeled scrap cost + modeled rework cost + supplied inspection cost.",
        "warnings": ["Use one period and scope across all records; avoid counting the same cost in multiple categories.",
                     "Only the entered categories are included; source ledgers and realized savings are not independently verified."],
    }


def inventory_policy(
    annual_demand: float, order_cost: float, annual_holding_cost_per_unit: float,
    mean_demand_per_period: float, std_demand_per_period: float, lead_time_periods: float,
    service_z: float = 1.645,
) -> dict[str, Any]:
    """Calculate EOQ and a simple demand-only safety stock/reorder point."""
    d, s, h = (_finite(annual_demand, "Annual demand"), _finite(order_cost, "Order cost"),
               _finite(annual_holding_cost_per_unit, "Annual holding cost per unit"))
    mean, std = _finite(mean_demand_per_period, "Mean demand"), _finite(std_demand_per_period, "Demand standard deviation")
    lead, z = _finite(lead_time_periods, "Lead time"), _finite(service_z, "Service Z")
    if min(d, s, h) <= 0 or mean < 0 or std < 0 or lead < 0 or z < 0:
        raise ValueError("Demand, order cost and holding cost must be positive; other demand/lead parameters cannot be negative.")
    eoq = math.sqrt(2*d*s/h)
    safety = z * std * math.sqrt(lead)
    lead_demand = mean * lead
    return {
        "status": "CALCULATED", "tool_id": "T055", "method_version": METHOD_VERSION,
        "method": "EOQ = sqrt(2DS/H); safety stock = z × demand standard deviation × sqrt(lead periods); reorder point = mean lead-time demand + safety stock.",
        "eoq_units": eoq, "expected_orders_per_year": d/eoq,
        "annual_ordering_cost_at_eoq": d/eoq*s, "annual_holding_cost_at_eoq": eoq/2*h,
        "expected_lead_time_demand_units": lead_demand, "safety_stock_units": safety,
        "reorder_point_units": lead_demand+safety, "service_z": z,
        "warnings": ["Assumes lead time is deterministic and demand variation is independent across periods.",
                     "The selected Z value must be consistent with the service-level convention used by your organization."],
    }


def abc_xyz_analysis(
    frame: pd.DataFrame, sku_column: str, unit_cost_column: str,
    demand_columns: Sequence[str], abc_a_pct: float = 80.0,
    abc_b_pct: float = 95.0, xyz_x_cv: float = 0.5, xyz_y_cv: float = 1.0,
) -> dict[str, Any]:
    """Segment SKU value (ABC) and demand variability (XYZ) using declared thresholds."""
    frame = _frame(frame, "Inventory table")
    demand_cols = [str(c) for c in demand_columns]
    if sku_column not in frame.columns or unit_cost_column not in frame.columns or not demand_cols or any(c not in frame.columns for c in demand_cols):
        raise ValueError("Select an SKU, unit-cost column and one or more demand-period columns.")
    a, b = _finite(abc_a_pct, "ABC A cutoff"), _finite(abc_b_pct, "ABC B cutoff")
    x, y = _finite(xyz_x_cv, "XYZ X CV threshold"), _finite(xyz_y_cv, "XYZ Y CV threshold")
    if not 0 < a < b <= 100 or x < 0 or y < x:
        raise ValueError("Require 0 < ABC A cutoff < B cutoff <= 100 and non-negative ordered CV thresholds.")
    data = frame.copy(deep=True)
    data[sku_column] = data[sku_column].astype(str).str.strip()
    if data[sku_column].eq("").any() or data[sku_column].duplicated().any():
        raise ValueError("SKU identifiers must be non-empty and unique.")
    cost = pd.to_numeric(data[unit_cost_column], errors="coerce")
    demand = data[demand_cols].apply(pd.to_numeric, errors="coerce")
    if cost.isna().any() or demand.isna().any().any() or (cost < 0).any() or (demand < 0).any().any():
        raise ValueError("Unit costs and demand observations must be numeric, complete and non-negative.")
    usage = demand.sum(axis=1)
    value = usage * cost
    total_value = float(value.sum())
    if total_value <= 0:
        raise ValueError("Total inventory usage value must be greater than zero to calculate ABC classes.")
    variability = demand.std(axis=1, ddof=1).div(demand.mean(axis=1).replace(0, np.nan))
    ranked = pd.DataFrame({
        "sku": data[sku_column], "unit_cost": cost, "period_demand_total": usage,
        "usage_value_over_selected_periods": value, "demand_cv": variability,
    }).sort_values(["usage_value_over_selected_periods", "sku"], ascending=[False, True], kind="stable").reset_index(drop=True)
    ranked["value_share_pct"] = ranked["usage_value_over_selected_periods"] / total_value * 100.0
    ranked["cumulative_value_pct_before_item"] = ranked["value_share_pct"].cumsum().shift(fill_value=0.0)
    ranked["ABC_class"] = np.where(ranked["cumulative_value_pct_before_item"] < a, "A",
                            np.where(ranked["cumulative_value_pct_before_item"] < b, "B", "C"))
    ranked["XYZ_class"] = np.where(ranked["demand_cv"].isna() | (ranked["demand_cv"] > y), "Z",
                            np.where(ranked["demand_cv"] <= x, "X", "Y"))
    ranked["ABC_XYZ_class"] = ranked["ABC_class"] + ranked["XYZ_class"]
    return {
        "status": "SEGMENTED", "tool_id": "T056", "method_version": METHOD_VERSION,
        "method": "ABC by cumulative usage value; XYZ by coefficient of variation across the selected demand columns.",
        "items": ranked, "abc_a_cutoff_pct": a, "abc_b_cutoff_pct": b,
        "xyz_x_cv_cutoff": x, "xyz_y_cv_cutoff": y,
        "warnings": ["Usage value covers only the selected demand periods; it is not annualized unless the source periods represent a year.",
                     "Zero-mean demand is classed Z because CV is undefined.",
                     "ABC/XYZ thresholds are editable business rules, not universal standards."],
    }


def bottleneck_analysis(operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare station capacity from declared cycle time, available time, and downtime."""
    if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes)) or not operations:
        raise ValueError("Provide at least one operation/station row.")
    records, seen = [], set()
    for i, op in enumerate(operations, 1):
        if not isinstance(op, Mapping):
            raise ValueError(f"Operation row {i} must be a mapping.")
        name = str(op.get("operation", "")).strip()
        cycle = _finite(op.get("cycle_time_seconds"), f"{name or i} cycle time")
        available = _finite(op.get("available_hours"), f"{name or i} available hours")
        downtime = _finite(op.get("downtime_hours", 0), f"{name or i} downtime")
        observed = _finite(op.get("observed_units", 0), f"{name or i} observed units")
        if not name or name in seen:
            raise ValueError(f"Operation row {i} needs a unique name.")
        if cycle <= 0 or available <= 0 or downtime < 0 or downtime >= available or observed < 0:
            raise ValueError(f"{name} requires positive cycle/available time, downtime below available time, and non-negative observed units.")
        seen.add(name)
        capacity = (available - downtime) * 3600.0 / cycle
        records.append({"operation": name, "cycle_time_seconds": cycle, "available_hours": available,
                        "downtime_hours": downtime, "observed_units": observed,
                        "estimated_capacity_units_per_window": capacity,
                        "observed_vs_capacity_pct": observed/capacity*100.0})
    frame = pd.DataFrame(records).sort_values(["estimated_capacity_units_per_window", "operation"], kind="stable").reset_index(drop=True)
    frame["capacity_rank"] = np.arange(1, len(frame)+1)
    frame["bottleneck_candidate"] = frame["capacity_rank"] == 1
    return {
        "status": "CAPACITY_SCREENED", "tool_id": "T025", "method_version": METHOD_VERSION,
        "method": "Estimated capacity = (available hours − downtime hours) × 3600 / cycle time in seconds.",
        "operations": frame, "bottleneck_candidate": str(frame.iloc[0]["operation"]),
        "estimated_system_capacity_units_per_window": float(frame.iloc[0]["estimated_capacity_units_per_window"]),
        "warnings": ["This is an input-based bottleneck candidate, not proof of the true system constraint.",
                     "Use synchronized time windows, comparable product mix and measured queues/throughput."],
    }


def oee_analysis(planned_minutes: float, downtime_minutes: float, ideal_cycle_seconds: float,
                 total_count: float, good_count: float) -> dict[str, Any]:
    """Calculate OEE components with a warning when performance exceeds 100%."""
    planned = _finite(planned_minutes, "Planned production minutes")
    downtime = _finite(downtime_minutes, "Downtime minutes")
    ideal = _finite(ideal_cycle_seconds, "Ideal cycle seconds")
    total = _finite(total_count, "Total count")
    good = _finite(good_count, "Good count")
    if planned <= 0 or ideal <= 0 or downtime < 0 or downtime >= planned:
        raise ValueError("Planned time and ideal cycle must be positive; downtime must be less than planned time.")
    if total <= 0 or good < 0 or good > total:
        raise ValueError("Total count must be positive and good count must be between zero and total count.")
    operating = planned - downtime
    availability = operating / planned
    performance = (total * ideal / 60.0) / operating
    quality = good / total
    warnings = ["Time and counts must share one comparable production window; confirm the ideal-cycle standard."]
    if performance > 1.0 + 1e-9:
        warnings.append("Performance exceeds 100%; investigate units, standard cycle time and count boundaries. The value is not capped.")
    return {
        "status": "CALCULATED", "tool_id": "T026", "method_version": METHOD_VERSION,
        "method": "Availability = operating/planned time; performance = ideal cycle × total count/operating time; quality = good/total; OEE = A×P×Q.",
        "planned_minutes": planned, "downtime_minutes": downtime, "operating_minutes": operating,
        "availability_pct": availability*100, "performance_pct": performance*100,
        "quality_pct": quality*100, "oee_pct": availability*performance*quality*100,
        "total_count": total, "good_count": good, "defect_count": total-good,
        "warnings": warnings,
    }


def weibull_reliability(failure_times: Sequence[Any]) -> dict[str, Any]:
    """Fit a 2-parameter Weibull to positive, uncensored failure-time observations."""
    if not isinstance(failure_times, Sequence) or isinstance(failure_times, (str, bytes)) or len(failure_times) < 3:
        raise ValueError("Provide at least three observed positive failure times.")
    data = np.asarray([_finite(x, "Failure time") for x in failure_times], dtype=float)
    if (data <= 0).any():
        raise ValueError("Failure times must be positive and use a consistent time unit.")
    beta, _, eta = weibull_min.fit(data, floc=0.0)
    if not np.isfinite(beta) or not np.isfinite(eta) or beta <= 0 or eta <= 0:
        raise ValueError("Weibull fitting did not return positive parameters.")
    b = lambda p: float(eta * (-math.log(1-p))**(1/beta))
    return {
        "status": "FITTED", "tool_id": "T041", "method_version": METHOD_VERSION,
        "method": "Two-parameter Weibull maximum likelihood with location fixed at zero; assumes uncensored observations.",
        "sample_size": len(data), "shape_beta": float(beta), "scale_eta": float(eta),
        "B10": b(0.10), "B50": b(0.50), "B90": b(0.90),
        "theoretical_mean_life": float(eta * gamma(1.0 + 1.0/beta)),
        "empirical_mean_failure_time": float(data.mean()),
        "warnings": ["Censored and still-operating assets are not supported and may bias the fit if omitted.",
                     "Percentile life estimates are distribution-based estimates, not guarantees for an individual asset."],
    }


def bin_pack_1d(item_lengths: Sequence[Any], stock_length: float, kerf: float = 0.0) -> dict[str, Any]:
    """First-fit-decreasing one-dimensional bin/cutting heuristic."""
    stock, saw = _finite(stock_length, "Stock length"), _finite(kerf, "Kerf")
    if stock <= 0 or saw < 0:
        raise ValueError("Stock length must be positive and kerf cannot be negative.")
    if not isinstance(item_lengths, Sequence) or isinstance(item_lengths, (str, bytes)) or not item_lengths:
        raise ValueError("Provide at least one item length.")
    items = [(_finite(x, f"Item {i} length"), i) for i, x in enumerate(item_lengths, 1)]
    if any(x <= 0 or x > stock for x, _ in items):
        raise ValueError("Each item length must be positive and not exceed stock length.")
    bins: list[list[tuple[float, int]]] = []
    for length, idx in sorted(items, key=lambda x: (-x[0], x[1])):
        placed = False
        for bucket in bins:
            used_piece_length = sum(x for x, _ in bucket)
            used_kerf = saw * max(0, len(bucket) - 1)
            additional_kerf = saw if bucket else 0.0
            if used_piece_length + used_kerf + length + additional_kerf <= stock + 1e-9:
                bucket.append((length, idx)); placed = True; break
        if not placed:
            bins.append([(length, idx)])
    rows = []
    for i, bucket in enumerate(bins, 1):
        piece = sum(x for x, _ in bucket)
        waste = stock-piece-saw*max(0, len(bucket)-1)
        rows.append({"stock_id": i, "item_indices": ", ".join(str(idx) for _, idx in sorted(bucket, key=lambda x:x[1])),
                     "item_count": len(bucket), "piece_length_total": piece,
                     "kerf_total": saw*max(0,len(bucket)-1), "waste_length": waste,
                     "utilization_pct": (piece+saw*max(0,len(bucket)-1))/stock*100})
    total_piece = sum(x for x,_ in items)
    total_kerf = saw*sum(max(0,len(bucket)-1) for bucket in bins)
    total_stock = stock*len(bins)
    return {
        "status": "HEURISTIC_PACKED", "tool_id": "T066", "method_version": METHOD_VERSION,
        "method": "First-fit-decreasing 1D heuristic; output is feasible for declared lengths but not guaranteed globally optimal.",
        "stock_length": stock, "kerf": saw, "item_count": len(items), "stock_count": len(bins),
        "total_piece_length": total_piece, "total_kerf": total_kerf,
        "total_waste_length": total_stock-total_piece-total_kerf,
        "overall_utilization_pct": (total_piece+total_kerf)/total_stock*100.0,
        "stocks": pd.DataFrame(rows),
        "warnings": ["Grain, trim, defects, clamp zones, cut sequence and dimensional tolerances are not modeled."],
    }


def forecast_drift_report(actuals: Sequence[Any], predictions: Sequence[Any],
                          max_abs_bias: float, max_mape_pct: float) -> dict[str, Any]:
    """Compare paired later actuals with predictions and flag explicit bias/MAPE limits."""
    if not isinstance(actuals, Sequence) or isinstance(actuals, (str, bytes)) or not isinstance(predictions, Sequence) or isinstance(predictions, (str, bytes)):
        raise ValueError("Actuals and predictions must be numeric sequences.")
    if len(actuals) != len(predictions) or len(actuals) < 2:
        raise ValueError("Actuals and predictions must have equal length and at least two observations.")
    actual = np.asarray([_finite(x, "Actual value") for x in actuals], dtype=float)
    predicted = np.asarray([_finite(x, "Prediction") for x in predictions], dtype=float)
    bias_limit, mape_limit = _finite(max_abs_bias, "Bias threshold"), _finite(max_mape_pct, "MAPE threshold")
    if bias_limit < 0 or mape_limit < 0:
        raise ValueError("Drift thresholds cannot be negative.")
    error = predicted-actual
    abs_error = np.abs(error)
    nonzero = actual != 0
    mape = float(np.mean(abs_error[nonzero]/np.abs(actual[nonzero]))*100) if nonzero.any() else None
    flagged = abs(float(error.mean())) > bias_limit or (mape is not None and mape > mape_limit)
    return {
        "status": "DRIFT_FLAGGED" if flagged else "WITHIN_DECLARED_THRESHOLDS",
        "tool_id": "T075", "method_version": METHOD_VERSION,
        "method": "Paired bias, MAE, RMSE and MAPE; MAPE excludes zero actual values.",
        "observations": len(actual), "bias_prediction_minus_actual": float(error.mean()),
        "mae": float(abs_error.mean()), "rmse": float(np.sqrt(np.mean(error**2))),
        "mape_pct_nonzero_actuals": mape, "zero_actual_count_excluded_from_mape": int((~nonzero).sum()),
        "abs_bias_threshold": bias_limit, "mape_threshold_pct": mape_limit,
        "observations_table": pd.DataFrame({"index": np.arange(1,len(actual)+1), "actual": actual,
                                            "prediction": predicted, "error": error, "absolute_error": abs_error}),
        "warnings": ["Use an out-of-time evaluation window not used for fitting/tuning the model.",
                     "Thresholds are process-specific; a drift flag is not proof of root cause."],
    }


def two_sample_mean_power(effect_size: float, population_std: float,
                          alpha: float = 0.05, desired_power: float = 0.80) -> dict[str, Any]:
    """Normal approximation for two independent means with equal allocation and variance."""
    effect = abs(_finite(effect_size, "Minimum detectable difference"))
    std = _finite(population_std, "Population standard deviation")
    alpha_value = _finite(alpha, "Alpha")
    power = _finite(desired_power, "Desired power")
    if effect <= 0 or std <= 0 or not 0 < alpha_value < 1 or not 0.5 < power < 1:
        raise ValueError("Effect and standard deviation must be positive; alpha in (0,1), power in (0.5,1).")
    normal = NormalDist()
    zcrit, zpower = normal.inv_cdf(1-alpha_value/2), normal.inv_cdf(power)
    n = int(math.ceil(2*((zcrit+zpower)*std/effect)**2))
    shift = effect*math.sqrt(n/(2*std**2))
    achieved = 1-normal.cdf(zcrit-shift)+normal.cdf(-zcrit-shift)
    return {
        "status": "PLANNED", "tool_id": "T085", "method_version": METHOD_VERSION,
        "method": "Two-sided normal approximation for two independent group means with equal sizes and common standard deviation.",
        "minimum_detectable_difference": effect, "population_standard_deviation": std,
        "alpha": alpha_value, "desired_power": power,
        "sample_size_per_group": n, "total_sample_size": 2*n,
        "normal_approximation_achieved_power": float(achieved),
        "warnings": ["Assumes independent observations, equal allocation, common variance and an approximately normal estimator.",
                     "No attrition, cluster design, unequal variance or multiple-comparison adjustment is included."],
    }


def mtbf_mttr_analysis(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate MTBF/MTTR from completed failure intervals with declared uptime and repair time."""
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)) or not events:
        raise ValueError("Provide at least one completed failure/repair interval.")
    rows = []
    for index, event in enumerate(events, 1):
        if not isinstance(event, Mapping):
            raise ValueError(f"Interval {index} must be a mapping.")
        uptime = _finite(event.get("uptime_hours"), f"Interval {index} uptime")
        repair = _finite(event.get("repair_hours"), f"Interval {index} repair time")
        if uptime < 0 or repair < 0 or (uptime == 0 and repair == 0):
            raise ValueError(f"Interval {index} needs non-negative uptime/repair time and cannot have both zero.")
        rows.append({"interval": index, "uptime_hours": uptime, "repair_hours": repair})
    details = pd.DataFrame(rows)
    uptime_total = float(details["uptime_hours"].sum())
    repair_total = float(details["repair_hours"].sum())
    n = len(details)
    availability = uptime_total / (uptime_total + repair_total) if uptime_total + repair_total > 0 else None
    return {
        "status": "CALCULATED", "tool_id": "T042", "method_version": METHOD_VERSION,
        "method": "MTBF = summed uptime / number of completed failures; MTTR = summed repair time / completed repairs; interval availability = uptime / (uptime + repair time).",
        "intervals": details, "failure_count": n, "total_uptime_hours": uptime_total,
        "total_repair_hours": repair_total, "mtbf_hours": uptime_total/n if uptime_total > 0 else None,
        "mttr_hours": repair_total/n,
        "interval_availability_pct": None if availability is None else availability*100.0,
        "warnings": ["Intervals must be complete and from the same observation scope.",
                     "Censoring, confidence intervals and failure-mode stratification are not included."],
    }


def preview_reversible_cleaning(
    frame: pd.DataFrame, trim_strings: bool = True,
    duplicate_policy: str = "keep", missing_policy: str = "keep",
    fill_value: Any = "",
) -> dict[str, Any]:
    """Create a reversible cleaning candidate and change log without mutating input."""
    frame = _frame(frame)
    if duplicate_policy not in {"keep", "drop_exact"}:
        raise ValueError("Duplicate policy must be keep or drop_exact.")
    if missing_policy not in {"keep", "drop_rows", "fill_value"}:
        raise ValueError("Missing policy must be keep, drop_rows, or fill_value.")
    original = frame.copy(deep=True)
    candidate = frame.copy(deep=True)
    events = []
    if trim_strings:
        for column in candidate.columns:
            if pd.api.types.is_object_dtype(candidate[column]) or pd.api.types.is_string_dtype(candidate[column]):
                old = candidate[column].copy(deep=True)
                mask = old.map(lambda x: isinstance(x, str) and x != x.strip())
                count = int(mask.sum())
                if count:
                    candidate[column] = old.map(lambda x: x.strip() if isinstance(x, str) else x)
                    events.append({"operation": "trim_whitespace", "column": str(column), "affected_cells": count})
    if missing_policy == "drop_rows":
        dropped = int(candidate.isna().any(axis=1).sum())
        candidate = candidate.dropna(axis=0, how="any").copy()
        if dropped:
            events.append({"operation": "drop_rows_with_missing_values", "column": "*", "affected_cells": dropped})
    elif missing_policy == "fill_value":
        for column in candidate.columns:
            count = int(candidate[column].isna().sum())
            if count:
                candidate[column] = candidate[column].fillna(fill_value)
                events.append({"operation": "fill_missing", "column": str(column), "affected_cells": count})
    removed = 0
    if duplicate_policy == "drop_exact":
        before = len(candidate)
        candidate = candidate.drop_duplicates(keep="first").copy()
        removed = before-len(candidate)
        if removed:
            events.append({"operation": "drop_exact_duplicates", "column": "*", "affected_cells": removed})
    if candidate.empty:
        raise ValueError("Cleaning preview would remove every row; input remains unchanged.")
    return {
        "status": "PREVIEW_READY", "tool_id": "T014", "method_version": METHOD_VERSION,
        "source": original, "candidate": candidate, "change_log": pd.DataFrame(events, columns=["operation","column","affected_cells"]),
        "rows_before": len(original), "rows_after": len(candidate), "rows_removed": len(original)-len(candidate),
        "missing_cells_before": int(original.isna().sum().sum()),
        "missing_cells_after": int(candidate.isna().sum().sum()),
        "exact_duplicate_rows_removed": removed, "apply_confirmed": False,
        "warnings": ["This operation creates a candidate copy; source data is not changed.",
                     "Review the change log and column values before applying. Fill values can change inferred column types."],
    }


def map_industrial_fields(
    frame: pd.DataFrame, field_mapping: Mapping[str, str],
) -> dict[str, Any]:
    """Rename explicitly mapped source fields to unique canonical names, retaining raw input."""
    frame = _frame(frame)
    if not isinstance(field_mapping, Mapping) or not field_mapping:
        raise ValueError("Provide at least one canonical-field to source-column mapping.")
    mapping = {}
    for canonical, source in field_mapping.items():
        dst, src = str(canonical or "").strip(), str(source or "").strip()
        if not dst or not src or src not in frame.columns:
            raise ValueError(f"Mapping {canonical!r} must reference an existing source column and non-empty canonical name.")
        if dst in mapping or src in mapping.values():
            raise ValueError("Canonical target names and source columns must be unique within the mapping.")
        mapping[dst] = src
    output_names = [mapping.get(str(col), str(col)) for col in frame.columns]
    if len(output_names) != len(set(output_names)):
        raise ValueError("Mapping would create duplicate column names; choose unambiguous canonical targets.")
    output = frame.copy(deep=True)
    rename = {src: dst for dst, src in mapping.items()}
    mapped = output.rename(columns=rename, errors="raise")
    detail = pd.DataFrame([{
        "canonical_field": target, "source_column": source,
        "nonmissing_values": int(frame[source].notna().sum()),
        "missing_values": int(frame[source].isna().sum()),
        "source_dtype": str(frame[source].dtype),
        "mapping_confirmation": "USER_SELECTED",
    } for target, source in mapping.items()])
    return {
        "status": "MAPPED", "tool_id": "T015", "method_version": METHOD_VERSION,
        "source": frame.copy(deep=True), "mapped": mapped,
        "mapping": detail,
        "warnings": ["The raw source copy is preserved in this result.",
                     "Field names are mapped by explicit user choice; values are not semantically inferred or converted."],
    }


def value_stream_summary(stages: Sequence[Mapping[str, Any]], demand_units: float,
                         available_minutes_per_period: float, period_label: str = "shift") -> dict[str, Any]:
    """Calculate a VSM timing summary from explicitly supplied stages, WIP and demand."""
    demand = _finite(demand_units, "Demand units per period")
    available = _finite(available_minutes_per_period, "Available minutes per period")
    period = str(period_label or "").strip()
    if demand <= 0 or available <= 0 or not period:
        raise ValueError("Demand, available production time and period label must be positive/non-empty.")
    if not isinstance(stages, Sequence) or isinstance(stages, (str, bytes)) or not stages:
        raise ValueError("Provide at least one VSM process stage.")
    records, seen = [], set()
    for i, row in enumerate(stages, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Stage {i} must be a mapping.")
        name = str(row.get("stage", "")).strip()
        cycle = _finite(row.get("cycle_time_seconds"), f"{name or i} cycle time")
        changeover = _finite(row.get("changeover_minutes", 0), f"{name or i} changeover")
        wip = _finite(row.get("wip_units", 0), f"{name or i} WIP")
        value_added = bool(row.get("value_added", True))
        if not name or name in seen or cycle <= 0 or changeover < 0 or wip < 0:
            raise ValueError(f"Stage {i} needs a unique name, positive cycle time, and non-negative changeover/WIP.")
        seen.add(name)
        records.append({"stage": name, "cycle_time_seconds": cycle, "cycle_time_minutes": cycle/60.0,
                        "changeover_minutes": changeover, "wip_units": wip, "value_added": value_added,
                        "estimated_wait_minutes": wip/(demand/available)})
    table = pd.DataFrame(records)
    total_process = float(table["cycle_time_minutes"].sum())
    total_value_added = float(table.loc[table["value_added"], "cycle_time_minutes"].sum())
    total_wait = float(table["estimated_wait_minutes"].sum())
    lead_time = total_process + total_wait
    return {
        "status": "SUMMARIZED", "tool_id": "T027", "method_version": METHOD_VERSION,
        "method": "Lead-time estimate = summed process cycle time + Σ(WIP units / demand rate).",
        "stages": table, "demand_units_per_period": demand,
        "available_minutes_per_period": available, "period_label": period,
        "takt_time_minutes_per_unit": available/demand,
        "total_process_cycle_minutes": total_process,
        "total_value_added_minutes": total_value_added,
        "total_wip_units": float(table["wip_units"].sum()),
        "estimated_queue_wait_minutes": total_wait, "estimated_lead_time_minutes": lead_time,
        "value_added_time_pct_of_estimated_lead_time": total_value_added/lead_time*100.0 if lead_time > 0 else None,
        "warnings": ["Estimated waiting time assumes steady demand at the supplied period rate; actual queue dynamics can differ.",
                     "Batch sizes, uptime, transport time, information delays and product mix are not inferred."],
    }


def fmea_prioritization(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute traditional RPN from disclosed 1–10 severity/occurrence/detection inputs."""
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("Provide at least one FMEA failure mode.")
    output = []
    for i, row in enumerate(records, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"FMEA row {i} must be a mapping.")
        mode = str(row.get("failure_mode", "")).strip()
        effect = str(row.get("effect", "") or "").strip()
        cause = str(row.get("cause", "") or "").strip()
        s = _finite(row.get("severity"), f"{mode or i} severity")
        o = _finite(row.get("occurrence"), f"{mode or i} occurrence")
        d = _finite(row.get("detection"), f"{mode or i} detection")
        if not mode or any(v < 1 or v > 10 or int(v) != v for v in (s,o,d)):
            raise ValueError(f"FMEA row {i} needs a name and integer ratings from 1 through 10.")
        output.append({
            "failure_mode": mode, "effect": effect, "cause": cause,
            "severity": int(s), "occurrence": int(o), "detection": int(d),
            "RPN": int(s*o*d), "recommended_action": str(row.get("recommended_action","") or "").strip(),
            "action_owner": str(row.get("action_owner","") or "").strip(),
            "due_date": str(row.get("due_date","") or "").strip(),
        })
    table = pd.DataFrame(output).sort_values(["severity","RPN","failure_mode"], ascending=[False,False,True], kind="stable").reset_index(drop=True)
    table["priority_rank"] = np.arange(1,len(table)+1)
    return {
        "status": "PRIORITIZED", "tool_id": "T038", "method_version": METHOD_VERSION,
        "method": "Traditional risk priority number = severity × occurrence × detection, using user-assigned ordinal ratings.",
        "failure_modes": table,
        "warnings": ["RPN is a prioritization aid, not a precise risk probability; severity should also be reviewed independently.",
                     "Rating scales require a consistent team rubric and accountable engineering review."],
    }


def capa_completeness(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Check CAPA/8D records for documented containment, cause, corrective action, and effectiveness."""
    required = ("issue", "containment", "root_cause", "corrective_action", "owner", "due_date", "effectiveness_evidence")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("Provide at least one CAPA/8D record.")
    output = []
    for i, row in enumerate(records, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"CAPA record {i} must be a mapping.")
        fields = {key: str(row.get(key, "") or "").strip() for key in required}
        if not fields["issue"]:
            raise ValueError(f"CAPA record {i} needs a non-empty issue description.")
        missing = [key for key in required[1:] if not fields[key]]
        output.append({
            **fields, "missing_fields": ", ".join(missing),
            "readiness": "READY_FOR_REVIEW" if not missing else "INCOMPLETE",
            "review_status": str(row.get("review_status", "Pending") or "Pending").strip(),
        })
    table = pd.DataFrame(output)
    return {
        "status": "REVIEWED", "tool_id": "T039", "method_version": METHOD_VERSION,
        "method": "Completeness checklist; no independent certification of root cause or action effectiveness is inferred.",
        "records": table, "ready_for_review_count": int((table["readiness"]=="READY_FOR_REVIEW").sum()),
        "incomplete_count": int((table["readiness"]=="INCOMPLETE").sum()),
        "warnings": ["This checklist does not replace a quality-system approval, evidence review or effectiveness verification."],
    }


def preventive_maintenance_plan(tasks: Sequence[Mapping[str, Any]], plan_date: str) -> dict[str, Any]:
    """Calculate next due dates for interval-based preventive maintenance tasks."""
    try:
        as_of = date.fromisoformat(str(plan_date))
    except ValueError as exc:
        raise ValueError("Plan date must be a valid YYYY-MM-DD date.") from exc
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)) or not tasks:
        raise ValueError("Provide at least one preventive maintenance task.")
    output = []
    seen = set()
    for i, row in enumerate(tasks, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Maintenance task {i} must be a mapping.")
        asset = str(row.get("asset_id", "")).strip()
        task = str(row.get("task", "")).strip()
        skill = str(row.get("required_skill", "") or "").strip()
        interval = _finite(row.get("interval_days"), f"{task or i} interval")
        duration = _finite(row.get("duration_hours"), f"{task or i} duration")
        try:
            last_done = date.fromisoformat(str(row.get("last_done_date", "")))
        except ValueError as exc:
            raise ValueError(f"{task or i} needs a last_done_date in YYYY-MM-DD format.") from exc
        key = (asset, task)
        if not asset or not task or key in seen or interval < 1 or int(interval) != interval or duration <= 0:
            raise ValueError(f"Maintenance row {i} needs unique asset/task IDs, integer interval days and positive duration.")
        seen.add(key)
        due = last_done + pd.Timedelta(days=int(interval))
        due_date = due.date() if hasattr(due, "date") else due
        delta = (due_date-as_of).days
        output.append({
            "asset_id": asset, "task": task, "required_skill": skill, "interval_days": int(interval),
            "duration_hours": duration, "last_done_date": last_done.isoformat(),
            "next_due_date": due_date.isoformat(), "days_until_due": delta,
            "status": "OVERDUE" if delta < 0 else "DUE" if delta == 0 else "SCHEDULED",
            "owner": str(row.get("owner", "") or "").strip(),
        })
    table = pd.DataFrame(output).sort_values(["days_until_due","asset_id","task"], kind="stable").reset_index(drop=True)
    return {
        "status": "PLANNED", "tool_id": "T043", "method_version": METHOD_VERSION,
        "method": "Next due date = last completed date + prescribed interval in calendar days.",
        "as_of_date": as_of.isoformat(), "tasks": table,
        "overdue_count": int((table["status"]=="OVERDUE").sum()),
        "warnings": ["Calendar intervals do not account for operating-hour triggers, asset condition, holidays, permits, or available technician schedules."],
    }


def spare_parts_criticality(records: Sequence[Mapping[str, Any]], service_z: float = 1.645) -> dict[str, Any]:
    """Calculate annual usage value, demand-only safety stock, reorder point and criticality."""
    z = _finite(service_z, "Service Z")
    if z < 0:
        raise ValueError("Service Z cannot be negative.")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("Provide at least one spare-part record.")
    output = []
    seen = set()
    for i, row in enumerate(records, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Spare-part row {i} must be a mapping.")
        part = str(row.get("part_id", "")).strip()
        demand = _finite(row.get("annual_demand"), f"{part or i} annual demand")
        unit_cost = _finite(row.get("unit_cost"), f"{part or i} unit cost")
        lead = _finite(row.get("lead_time_days"), f"{part or i} lead time")
        daily_std = _finite(row.get("daily_demand_std"), f"{part or i} daily demand std")
        stock = _finite(row.get("stock_on_hand"), f"{part or i} stock")
        criticality = _finite(row.get("criticality_1_to_5"), f"{part or i} criticality")
        if not part or part in seen or min(demand,unit_cost,lead,daily_std,stock) < 0 or criticality < 1 or criticality > 5 or int(criticality)!=criticality:
            raise ValueError(f"Spare-part row {i} needs unique ID, non-negative quantities/costs and integer criticality 1–5.")
        seen.add(part)
        mean_daily = demand/365.0
        safety = z*daily_std*math.sqrt(lead)
        rop = mean_daily*lead+safety
        output.append({
            "part_id": part, "annual_demand": demand, "unit_cost": unit_cost,
            "annual_usage_value": demand*unit_cost, "lead_time_days": lead,
            "criticality_1_to_5": int(criticality), "stock_on_hand": stock,
            "mean_daily_demand": mean_daily, "safety_stock": safety,
            "reorder_point": rop, "reorder_needed": stock <= rop,
            "recommended_order_qty_to_rop": max(0.0, math.ceil(rop-stock)),
            "estimated_days_of_cover": stock/mean_daily if mean_daily > 0 else None,
        })
    table = pd.DataFrame(output).sort_values(["criticality_1_to_5","reorder_needed","annual_usage_value"], ascending=[False,False,False], kind="stable").reset_index(drop=True)
    return {
        "status": "PRIORITIZED", "tool_id": "T045", "method_version": METHOD_VERSION,
        "method": "Daily mean demand = annual demand/365; safety stock = z × daily demand standard deviation × sqrt(lead days); reorder point = mean lead demand + safety stock.",
        "parts": table, "service_z": z,
        "warnings": ["Lead time is assumed fixed; demand variability is assumed independent by day.",
                     "Criticality is user-rated; validate BOM, interchangeability and supplier lead time before acting."],
    }


def hazard_risk_register(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute inherent and residual risk scores from disclosed severity/likelihood ratings."""
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("Provide at least one hazard record.")
    output = []
    for i, row in enumerate(records, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Hazard row {i} must be a mapping.")
        hazard = str(row.get("hazard", "")).strip()
        if not hazard:
            raise ValueError(f"Hazard row {i} needs a hazard description.")
        scores = [_finite(row.get(key), f"{hazard} {key}") for key in (
            "severity", "likelihood", "residual_severity", "residual_likelihood")]
        if any(v < 1 or v > 5 or int(v) != v for v in scores):
            raise ValueError(f"{hazard}: severity and likelihood ratings must be integers from 1 through 5.")
        s, l, rs, rl = (int(v) for v in scores)
        output.append({
            "hazard": hazard, "location": str(row.get("location", "") or "").strip(),
            "inherent_severity": s, "inherent_likelihood": l, "inherent_score": s*l,
            "existing_controls": str(row.get("existing_controls", "") or "").strip(),
            "residual_severity": rs, "residual_likelihood": rl, "residual_score": rs*rl,
            "owner": str(row.get("owner", "") or "").strip(),
            "action": str(row.get("action", "") or "").strip(),
            "due_date": str(row.get("due_date", "") or "").strip(),
        })
    table = pd.DataFrame(output).sort_values(["residual_score","inherent_score","hazard"], ascending=[False,False,True], kind="stable").reset_index(drop=True)
    table["priority_rank"] = np.arange(1,len(table)+1)
    return {
        "status": "RISK_SCREENED", "tool_id": "T047", "method_version": METHOD_VERSION,
        "method": "Simple ordinal severity × likelihood scoring; residual ratings are entered assumptions after controls.",
        "hazards": table,
        "warnings": ["This risk register is not a certified workplace risk assessment or safety approval.",
                     "Residual ratings must be justified by effective controls, evidence and competent safety review."],
    }

def maintenance_backlog_priority(
    records: Sequence[Mapping[str, Any]],
    skill_capacity_hours: Mapping[str, Any],
) -> dict[str, Any]:
    """Prioritize maintenance work with a transparent, skills-capacity greedy heuristic.

    Jobs are ordered by criticality (descending), days overdue (descending), then
    shorter duration and work-order ID. This is a deterministic heuristic, not a
    globally optimal scheduling solver; it models one required skill per order.
    """
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("Provide at least one maintenance work order.")
    if not isinstance(skill_capacity_hours, Mapping) or not skill_capacity_hours:
        raise ValueError("Provide available labor hours for at least one skill.")
    capacities: dict[str, float] = {}
    for skill, raw_hours in skill_capacity_hours.items():
        name = str(skill or "").strip()
        hours = _finite(raw_hours, f"{name or 'Unnamed skill'} capacity hours")
        if not name or hours < 0 or name in capacities:
            raise ValueError("Skill capacities need unique non-empty skill names and non-negative hours.")
        capacities[name] = hours

    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(records, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Work order {index} must be a mapping.")
        work_id = str(row.get("work_order_id", "") or "").strip()
        asset = str(row.get("asset_id", "") or "").strip()
        description = str(row.get("description", "") or "").strip()
        skill = str(row.get("required_skill", "") or "").strip()
        hours = _finite(row.get("estimated_hours"), f"{work_id or index} estimated hours")
        criticality = _finite(row.get("criticality_1_to_5"), f"{work_id or index} criticality")
        overdue = _finite(row.get("days_overdue", 0), f"{work_id or index} days overdue")
        if (
            not work_id or work_id in seen or not asset or not skill
            or hours <= 0 or criticality < 1 or criticality > 5 or int(criticality) != criticality
            or overdue < 0 or int(overdue) != overdue
        ):
            raise ValueError(
                f"Work order {index} needs a unique ID, asset, skill, positive hours, "
                "integer criticality 1–5, and non-negative integer days overdue."
            )
        seen.add(work_id)
        jobs.append({
            "work_order_id": work_id, "asset_id": asset, "description": description,
            "required_skill": skill, "estimated_hours": hours,
            "criticality_1_to_5": int(criticality), "days_overdue": int(overdue),
        })

    jobs.sort(key=lambda j: (
        -j["criticality_1_to_5"], -j["days_overdue"],
        j["estimated_hours"], j["work_order_id"],
    ))
    remaining = dict(capacities)
    planned = []
    for rank, job in enumerate(jobs, 1):
        skill = job["required_skill"]
        available = remaining.get(skill)
        if available is None:
            status = "DEFERRED_SKILL_NOT_CONFIGURED"
        elif job["estimated_hours"] <= available + 1e-9:
            status = "SCHEDULED_BY_PRIORITY_HEURISTIC"
            remaining[skill] = max(0.0, available - job["estimated_hours"])
        else:
            status = "DEFERRED_SKILL_CAPACITY"
        planned.append({
            **job, "priority_rank": rank, "available_skill_hours_before": available,
            "allocation_status": status,
        })
    order_table = pd.DataFrame(planned)
    capacity_table = pd.DataFrame([
        {"skill": skill, "available_hours": capacities[skill],
         "planned_hours": capacities[skill] - remaining[skill],
         "remaining_hours": remaining[skill]}
        for skill in sorted(capacities)
    ])
    selected_count = int(order_table["allocation_status"].eq("SCHEDULED_BY_PRIORITY_HEURISTIC").sum())
    return {
        "status": "PRIORITIZED_HEURISTIC", "tool_id": "T049", "method_version": METHOD_VERSION,
        "method": "Greedy scheduling by criticality, days overdue, duration and work-order ID, constrained by skill-hour budgets.",
        "work_orders": order_table, "skill_capacity": capacity_table,
        "scheduled_count": selected_count, "deferred_count": int(len(order_table) - selected_count),
        "warnings": [
            "This deterministic greedy heuristic is not a globally optimal schedule.",
            "It models one required skill per work order and does not solve shift calendars, precedence, access permits, or downtime windows.",
            "Criticality and overdue days are inputs and should be reviewed by accountable maintenance staff.",
        ],
    }


def sales_operations_reconciliation(
    periods: Sequence[Mapping[str, Any]],
    initial_inventory_units: Any = 0,
    initial_backlog_units: Any = 0,
) -> dict[str, Any]:
    """Reconcile period demand, capacity-limited production, inventory and carried backlog."""
    if not isinstance(periods, Sequence) or isinstance(periods, (str, bytes)) or not periods:
        raise ValueError("Provide at least one planning period.")
    inventory = _finite(initial_inventory_units, "Initial inventory units")
    backlog = _finite(initial_backlog_units, "Initial backlog units")
    if inventory < 0 or backlog < 0:
        raise ValueError("Initial inventory and backlog cannot be negative.")
    seen: set[str] = set()
    output = []
    for index, row in enumerate(periods, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Planning period {index} must be a mapping.")
        period = str(row.get("period", "") or "").strip()
        demand = _finite(row.get("demand_units"), f"{period or index} demand units")
        plan = _finite(row.get("planned_production_units"), f"{period or index} planned production")
        capacity = _finite(row.get("available_capacity_units"), f"{period or index} capacity")
        if not period or period in seen or min(demand, plan, capacity) < 0:
            raise ValueError(f"Period {index} needs a unique label and non-negative demand, plan and capacity.")
        seen.add(period)
        opening_inventory, opening_backlog = inventory, backlog
        production = min(plan, capacity)
        total_requirement = demand + opening_backlog
        available_supply = opening_inventory + production
        inventory = max(0.0, available_supply - total_requirement)
        backlog = max(0.0, total_requirement - available_supply)
        output.append({
            "period": period,
            "opening_inventory_units": opening_inventory,
            "opening_backlog_units": opening_backlog,
            "demand_units": demand,
            "planned_production_units": plan,
            "available_capacity_units": capacity,
            "capacity_limited_production_units": production,
            "capacity_shortfall_vs_plan_units": max(0.0, plan - capacity),
            "total_requirement_units": total_requirement,
            "available_supply_units": available_supply,
            "ending_inventory_units": inventory,
            "ending_backlog_units": backlog,
            "fulfilled_current_period_units": max(0.0, min(demand, available_supply - opening_backlog)),
        })
    table = pd.DataFrame(output)
    return {
        "status": "RECONCILED", "tool_id": "T052", "method_version": METHOD_VERSION,
        "method": "Production is capped at available capacity; inventory and backlog carry forward period-by-period in the supplied order.",
        "periods": table,
        "total_demand_units": float(table["demand_units"].sum()),
        "total_production_units": float(table["capacity_limited_production_units"].sum()),
        "ending_inventory_units": float(table.iloc[-1]["ending_inventory_units"]),
        "ending_backlog_units": float(table.iloc[-1]["ending_backlog_units"]),
        "total_capacity_shortfall_vs_plan_units": float(table["capacity_shortfall_vs_plan_units"].sum()),
        "warnings": [
            "This is a transparent volume reconciliation, not a complete enterprise S&OP process.",
            "It assumes one product family and one unit basis; material mix, labor, setup, lead time, cost and service constraints are not modeled.",
            "Production plans, capacity and demand should come from dated, authorized source data before operational use.",
        ],
    }


def supplier_performance_scorecard(
    records: Sequence[Mapping[str, Any]],
    weights: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate a traceable weighted supplier score; incomplete suppliers remain unranked.

    Every score is normalized to 0–100 where larger is better, including the
    supplied risk-management score (100 means stronger controls/lower assessed risk).
    """
    metric_names = ("quality", "delivery", "cost", "risk_management")
    default_weights = {"quality": 0.35, "delivery": 0.35, "cost": 0.15, "risk_management": 0.15}
    source_weights = weights if weights is not None else default_weights
    if not isinstance(source_weights, Mapping):
        raise ValueError("Weights must be a mapping of quality, delivery, cost and risk_management.")
    clean_weights: dict[str, float] = {}
    for metric in metric_names:
        weight = _finite(source_weights.get(metric), f"{metric} weight")
        if weight < 0:
            raise ValueError("Supplier-score weights cannot be negative.")
        clean_weights[metric] = weight
    total_weight = sum(clean_weights.values())
    if total_weight <= 0:
        raise ValueError("At least one supplier-score weight must be positive.")
    clean_weights = {key: value / total_weight for key, value in clean_weights.items()}

    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise ValueError("Provide at least one supplier record.")
    output = []
    seen: set[str] = set()
    for index, row in enumerate(records, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Supplier row {index} must be a mapping.")
        supplier = str(row.get("supplier", "") or "").strip()
        if not supplier or supplier in seen:
            raise ValueError(f"Supplier row {index} needs a unique non-empty supplier name.")
        seen.add(supplier)
        scores: dict[str, float | None] = {}
        missing = []
        for metric in metric_names:
            raw = row.get(f"{metric}_score")
            is_missing = raw is None or (isinstance(raw, str) and not raw.strip())
            if not is_missing:
                try:
                    is_missing = bool(pd.isna(raw))
                except (TypeError, ValueError):
                    is_missing = False
            if is_missing:
                scores[metric] = None
                missing.append(metric)
                continue
            value = _finite(raw, f"{supplier} {metric} score")
            if value < 0 or value > 100:
                raise ValueError(f"{supplier} {metric} score must be between 0 and 100.")
            scores[metric] = value
        complete = not missing
        weighted_score = (
            sum(float(scores[m]) * clean_weights[m] for m in metric_names)
            if complete else None
        )
        output.append({
            "supplier": supplier, **{f"{m}_score": scores[m] for m in metric_names},
            "completeness": "COMPLETE" if complete else "INCOMPLETE",
            "missing_evidence": ", ".join(missing),
            "weighted_score_0_to_100": weighted_score,
        })
    table = pd.DataFrame(output)
    table["_complete_sort"] = table["weighted_score_0_to_100"].notna()
    table = table.sort_values(
        ["_complete_sort", "weighted_score_0_to_100", "supplier"],
        ascending=[False, False, True], na_position="last", kind="stable",
    ).drop(columns=["_complete_sort"]).reset_index(drop=True)
    table["rank"] = pd.array(
        [i + 1 if pd.notna(score) else None for i, score in enumerate(table["weighted_score_0_to_100"])],
        dtype="Int64",
    )
    return {
        "status": "SCORED_WITH_EVIDENCE_GAPS", "tool_id": "T058", "method_version": METHOD_VERSION,
        "method": "Weighted mean of four normalized 0–100 scores; suppliers missing any component are deliberately left unranked.",
        "weights": clean_weights, "suppliers": table,
        "ranked_supplier_count": int(table["weighted_score_0_to_100"].notna().sum()),
        "unranked_supplier_count": int(table["weighted_score_0_to_100"].isna().sum()),
        "warnings": [
            "Weights are user-selected policy choices, not objectively correct universal priorities.",
            "All score scales must be normalized so higher means better; risk_management_score means control maturity / lower assessed risk.",
            "This scorecard is not a probability of supplier failure and does not replace evidence-based supplier qualification.",
        ],
    }


def simulate_single_station_des(
    customers: Any = 500,
    mean_interarrival: Any = 1.0,
    mean_service: Any = 0.8,
    arrival_distribution: str = "exponential",
    service_distribution: str = "exponential",
    warmup_customers: Any = 50,
    replications: Any = 20,
    seed: Any = 42,
) -> dict[str, Any]:
    """Run a reproducible single-station FCFS discrete-event queue simulation.

    Supported arrival/service distributions are exponential or constant. The
    event times are generated from a local seeded RNG; no plant system is read
    or controlled. Results summarize each replication after the warm-up customers.
    """
    n_value = _finite(customers, "Customer count")
    warm_value = _finite(warmup_customers, "Warm-up customer count")
    reps_value = _finite(replications, "Replication count")
    seed_value = _finite(seed, "Random seed")
    arrival_mean = _finite(mean_interarrival, "Mean interarrival time")
    service_mean = _finite(mean_service, "Mean service time")
    arrival_kind = str(arrival_distribution or "").strip().lower()
    service_kind = str(service_distribution or "").strip().lower()
    if int(n_value) != n_value or n_value < 10 or n_value > 10000:
        raise ValueError("Customer count must be an integer from 10 through 10,000.")
    if int(warm_value) != warm_value or warm_value < 0 or warm_value >= n_value - 1:
        raise ValueError("Warm-up count must be an integer from 0 to fewer than customers minus one.")
    if int(reps_value) != reps_value or reps_value < 2 or reps_value > 100:
        raise ValueError("Replication count must be an integer from 2 through 100.")
    if int(seed_value) != seed_value or seed_value < 0 or seed_value > 2**32 - 1:
        raise ValueError("Random seed must be an integer from 0 through 2^32−1.")
    if arrival_mean <= 0 or service_mean <= 0:
        raise ValueError("Mean interarrival and service times must be positive.")
    if arrival_kind not in {"exponential", "constant"} or service_kind not in {"exponential", "constant"}:
        raise ValueError("Arrival and service distributions must be exponential or constant.")

    rng = np.random.default_rng(int(seed_value))
    rows = []
    for replication in range(1, int(reps_value) + 1):
        interarrivals = (
            rng.exponential(arrival_mean, int(n_value))
            if arrival_kind == "exponential" else np.full(int(n_value), arrival_mean)
        )
        service = (
            rng.exponential(service_mean, int(n_value))
            if service_kind == "exponential" else np.full(int(n_value), service_mean)
        )
        arrivals = np.cumsum(interarrivals)
        starts = np.zeros(int(n_value), dtype=float)
        departures = np.zeros(int(n_value), dtype=float)
        for i in range(int(n_value)):
            starts[i] = max(arrivals[i], departures[i - 1] if i else 0.0)
            departures[i] = starts[i] + service[i]

        included = slice(int(warm_value), int(n_value))
        observation_start = float(arrivals[int(warm_value)])
        observation_end = float(departures[-1])
        observation_time = observation_end - observation_start
        waits = starts[included] - arrivals[included]
        systems = departures[included] - arrivals[included]
        if observation_time <= 0:
            raise ValueError("Simulation produced a non-positive observation window.")
        busy_overlap = float(sum(
            max(0.0, min(float(departures[i]), observation_end) - max(float(starts[i]), observation_start))
            for i in range(int(n_value))
        ))
        utilization_pct = min(100.0, max(0.0, 100.0 * busy_overlap / observation_time))
        throughput = len(waits) / observation_time
        rows.append({
            "replication": replication,
            "customers_observed_after_warmup": int(n_value) - int(warm_value),
            "observation_time_units": observation_time,
            "mean_wait_time_units": float(np.mean(waits)),
            "p95_wait_time_units": float(np.quantile(waits, 0.95)),
            "mean_time_in_system_units": float(np.mean(systems)),
            "throughput_customers_per_time_unit": float(throughput),
            "utilization_pct": utilization_pct,
        })
    table = pd.DataFrame(rows)
    offered_load = service_mean / arrival_mean
    warnings = [
        "This is a single-server FCFS queue; setups, outages, priority rules, multiple stations and finite buffers are not modeled.",
        "Synthetic simulation results are not plant measurements or a promise of throughput, savings, or service.",
        "Mean arrival/service parameters are model inputs; calibrate them against timestamped observations before operational use.",
    ]
    if offered_load >= 1.0:
        warnings.append("Mean service time is at least the mean interarrival time (offered load ≥ 1); long-run queue stability should not be assumed.")
    return {
        "status": "SIMULATED", "tool_id": "T071", "method_version": METHOD_VERSION,
        "method": "Discrete-event event-time model: arrival → queue wait → service start → departure; FCFS single server; output summaries exclude the configured warm-up customers.",
        "configuration": {
            "customers_per_replication": int(n_value), "warmup_customers": int(warm_value),
            "replications": int(reps_value), "seed": int(seed_value),
            "mean_interarrival": arrival_mean, "mean_service": service_mean,
            "arrival_distribution": arrival_kind, "service_distribution": service_kind,
            "offered_load_service_to_interarrival": offered_load,
            "provenance": "SYNTHETIC_SIMULATION",
        },
        "replication_results": table,
        "mean_wait_time_units": float(table["mean_wait_time_units"].mean()),
        "p95_wait_time_units": float(table["p95_wait_time_units"].mean()),
        "mean_time_in_system_units": float(table["mean_time_in_system_units"].mean()),
        "throughput_customers_per_time_unit": float(table["throughput_customers_per_time_unit"].mean()),
        "mean_utilization_pct": float(table["utilization_pct"].mean()),
        "warnings": warnings,
    }
