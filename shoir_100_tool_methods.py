"""Deterministic, scoped methods for eight Shoir-IE 100-tool targets.

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
from scipy.stats import binom


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
    canonical["research pack add-on"] = "Research Pack"
    canonical["enterprise plus tier ($399)"] = "Enterprise Plus"
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
