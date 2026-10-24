"""Bounded, reproducible quality, forecast, MRP and uncertainty methods."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.stats import hypergeom


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    return result


def _integer(value: Any, label: str, minimum: int, maximum: int | None = None) -> int:
    number = _number(value, label)
    if not number.is_integer():
        raise ValueError(f"{label} must be a whole number.")
    result = int(number)
    if result < minimum or (maximum is not None and result > maximum):
        bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{label} must be {bound}.")
    return result


def evaluate_acceptance_sampling_plan(
    lot_size: int,
    sample_size: int,
    acceptance_number: int,
    aql_percent: float,
    ltpd_percent: float,
    *,
    curve_points: int = 21,
) -> dict[str, Any]:
    """Evaluate a finite-lot, single-sampling plan with an exact hypergeometric OC curve.

    The user supplies n and c; this method evaluates that plan. It does not
    select a plan that meets prescribed producer/consumer risk targets.
    Percent defectives are converted to the nearest whole defective count.
    """
    lot = _integer(lot_size, "Lot size", 1, 10_000_000)
    sample = _integer(sample_size, "Sample size", 1, lot)
    accept = _integer(acceptance_number, "Acceptance number", 0, sample - 1)
    aql = _number(aql_percent, "AQL percent")
    ltpd = _number(ltpd_percent, "LTPD percent")
    points = _integer(curve_points, "Curve points", 5, 101)
    if not 0 <= aql < ltpd <= 100:
        raise ValueError("Require 0 <= AQL < LTPD <= 100 percent.")
    def defectives(rate: float) -> int:
        return min(lot, max(0, int(math.floor(rate * lot / 100.0 + 0.5))))
    def probability_accepted(rate: float) -> float:
        count = defectives(rate)
        return float(hypergeom.cdf(accept, lot, count, sample))
    pa_aql = probability_accepted(aql)
    pa_ltpd = probability_accepted(ltpd)
    curve = []
    for rate in np.linspace(0.0, 100.0, points):
        pct = float(rate)
        curve.append({
            "defective_percent": round(pct, 6),
            "defective_count_assumed": defectives(pct),
            "probability_of_acceptance": probability_accepted(pct),
        })
    return {
        "status": "CALCULATED",
        "method": "Finite-lot single-sampling plan; hypergeometric operating-characteristic curve",
        "metrics": {
            "lot_size": lot, "sample_size": sample, "acceptance_number": accept,
            "aql_percent": aql, "ltpd_percent": ltpd,
            "defectives_assumed_at_aql": defectives(aql),
            "defectives_assumed_at_ltpd": defectives(ltpd),
            "probability_of_acceptance_at_aql": pa_aql,
            "producer_risk_at_aql": 1.0 - pa_aql,
            "probability_of_acceptance_at_ltpd": pa_ltpd,
            "consumer_risk_at_ltpd": pa_ltpd,
        },
        "operating_characteristic": curve,
        "formulas": {
            "probability_of_acceptance": "P(X <= c), X ~ Hypergeometric(N=lot size, K=defective units, n=sample size)",
            "producer_risk_at_aql": "1 − P(accept lot at the assumed AQL defect rate)",
            "consumer_risk_at_ltpd": "P(accept lot at the assumed LTPD defect rate)",
        },
        "assumptions": [
            "Sampling is random without replacement from a finite, homogeneous lot.",
            "AQL/LTPD percentages are converted to nearest whole defective counts; small lots make that rounding material.",
            "AQL and LTPD are analyst-supplied reference points, not certifications or universal standard-plan defaults.",
        ],
        "warnings": [
            "This evaluates a user-specified n/c plan; it does not design a plan to meet externally mandated risk targets.",
            "Check the governing quality standard, sampling method and contractual acceptance rules before use.",
        ],
    }


def forecast_demand_series(
    observations: Sequence[float],
    horizon: int,
    *,
    holdout_periods: int = 2,
    moving_average_window: int = 2,
) -> dict[str, Any]:
    """Compare a last-value-naive baseline with a rolling moving-average forecast.

    Evaluation uses a chronological one-step-ahead walk-forward holdout. There are
    no fitted seasonal terms or probabilistic forecast intervals.
    """
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)) or len(observations) < 4:
        raise ValueError("Provide at least four chronological demand observations.")
    values = [_number(v, "Demand observation") for v in observations]
    if any(v < 0 for v in values):
        raise ValueError("Demand observations cannot be negative.")
    h = _integer(horizon, "Forecast horizon", 1, 500)
    holdout = _integer(holdout_periods, "Holdout periods", 1, len(values) - 2)
    window = _integer(moving_average_window, "Moving-average window", 2, len(values) - holdout)
    training_size = len(values) - holdout
    train = values[:training_size]
    actuals = values[training_size:]
    history = list(train)
    naive_predictions: list[float] = []
    moving_predictions: list[float] = []
    for actual in actuals:
        naive_predictions.append(history[-1])
        moving_predictions.append(sum(history[-window:]) / window)
        history.append(actual)

    def error_metrics(actual: list[float], predicted: list[float]) -> dict[str, Any]:
        errors = [p - a for a, p in zip(actual, predicted)]
        mae = sum(abs(e) for e in errors) / len(errors)
        rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
        mape_values = [abs((p - a) / a) for a, p in zip(actual, predicted) if a != 0]
        return {
            "mae": mae, "rmse": rmse,
            "mape_percent": (sum(mape_values) / len(mape_values) * 100.0) if mape_values else None,
            "bias_forecast_minus_actual": sum(errors) / len(errors),
        }

    naive_scores = error_metrics(actuals, naive_predictions)
    moving_scores = error_metrics(actuals, moving_predictions)
    chosen = "naive_last_value" if naive_scores["mae"] <= moving_scores["mae"] else "moving_average"
    future_naive = [values[-1]] * h
    moving_history = list(values)
    future_moving: list[float] = []
    for _ in range(h):
        prediction = sum(moving_history[-window:]) / window
        future_moving.append(prediction)
        moving_history.append(prediction)
    future = [{
        "period_ahead": i + 1,
        "naive_last_value": future_naive[i],
        "moving_average": future_moving[i],
        "selected_forecast": future_naive[i] if chosen == "naive_last_value" else future_moving[i],
    } for i in range(h)]
    backtest = [{
        "period_index": training_size + i + 1,
        "actual": actuals[i],
        "naive_last_value_prediction": naive_predictions[i],
        "moving_average_prediction": moving_predictions[i],
    } for i in range(holdout)]
    return {
        "status": "FORECASTED",
        "method": "Chronological walk-forward comparison: last-value naive vs recursive moving average",
        "metrics": {
            "observation_count": len(values), "training_observation_count": training_size,
            "holdout_periods": holdout, "forecast_horizon": h,
            "moving_average_window": window, "selected_model_by_holdout_mae": chosen,
            "naive_last_value": naive_scores, "moving_average": moving_scores,
        },
        "backtest": backtest,
        "forecast": future,
        "formulas": {
            "naive_last_value": "forecast(t+1) = last available actual observation",
            "moving_average": "forecast(t+1) = mean of the most recent window observations",
            "mae": "mean(|forecast − actual|)", "rmse": "sqrt(mean((forecast − actual)^2))",
        },
        "assumptions": [
            "Observations are chronological and equally spaced; values are demand quantities in one consistent unit.",
            "The moving-average future forecast is recursive; future actuals are not available.",
            "The selected model is chosen only by holdout MAE; this is a small-baseline comparison, not an exhaustive forecasting study.",
        ],
        "warnings": [
            "No forecast intervals, seasonal decomposition, exogenous variables or structural-break model are included.",
            "A short holdout can make model ranking unstable; inspect the observed series before operational planning.",
        ],
    }


def plan_material_requirements(
    bom: Sequence[Mapping[str, Any]],
    master_schedule: Sequence[Mapping[str, Any]],
    horizon_periods: int,
    inventory: Mapping[str, Any],
    lead_times: Mapping[str, Any],
    scheduled_receipts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Multilevel lot-for-lot MRP with parent planned releases driving component demand.

    Periods are integer buckets 1..H. Requirements whose lead-time release would
    fall before period 1 are rejected rather than silently shifted or under-planned.
    """
    horizon = _integer(horizon_periods, "Planning horizon", 1, 520)
    if not isinstance(bom, Sequence) or isinstance(bom, (str, bytes)):
        raise ValueError("BOM must be a sequence of parent/component rows.")
    if not isinstance(master_schedule, Sequence) or isinstance(master_schedule, (str, bytes)) or not master_schedule:
        raise ValueError("Provide at least one master-schedule demand row.")
    if not isinstance(inventory, Mapping) or not isinstance(lead_times, Mapping):
        raise ValueError("Inventory and lead times must be item-to-value mappings.")
    receipts = list(scheduled_receipts or [])
    normalized_bom: list[dict[str, Any]] = []
    pair_set: set[tuple[str, str]] = set()
    items: set[str] = set()
    for index, row in enumerate(bom, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"BOM row {index} must be an object.")
        parent = str(row.get("parent", "")).strip()
        component = str(row.get("component", "")).strip()
        if not parent or not component or parent == component:
            raise ValueError(f"BOM row {index} needs distinct parent and component item codes.")
        pair = (parent, component)
        if pair in pair_set:
            raise ValueError(f"Duplicate BOM component row: {parent} -> {component}.")
        pair_set.add(pair)
        qty = _number(row.get("quantity_per"), f"Quantity per {parent}/{component}")
        if qty <= 0:
            raise ValueError(f"Quantity per {parent}/{component} must be greater than zero.")
        normalized_bom.append({"parent": parent, "component": component, "quantity_per": qty})
        items.update((parent, component))

    normalized_mps: list[dict[str, Any]] = []
    for index, row in enumerate(master_schedule, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Master schedule row {index} must be an object.")
        item = str(row.get("item", "")).strip()
        if not item:
            raise ValueError(f"Master schedule row {index} needs an item code.")
        period = _integer(row.get("period"), f"Period for {item}", 1, horizon)
        demand = _number(row.get("demand"), f"Demand for {item} in period {period}")
        if demand < 0:
            raise ValueError("Demand cannot be negative in the master schedule.")
        items.add(item)
        normalized_mps.append({"item": item, "period": period, "demand": demand})

    for item, value in inventory.items():
        items.add(str(item).strip())
        qty = _number(value, f"On-hand inventory for {item}")
        if qty < 0:
            raise ValueError(f"On-hand inventory for {item} cannot be negative.")
    for row in receipts:
        if not isinstance(row, Mapping):
            raise ValueError("Each scheduled receipt must be an object.")
        item = str(row.get("item", "")).strip()
        if not item:
            raise ValueError("Each scheduled receipt needs an item code.")
        period = _integer(row.get("period"), f"Receipt period for {item}", 1, horizon)
        quantity = _number(row.get("quantity"), f"Receipt quantity for {item}")
        if quantity < 0:
            raise ValueError("Scheduled receipt quantities cannot be negative.")
        items.add(item)

    normalized_leads: dict[str, int] = {}
    for item in items:
        if item not in lead_times:
            raise ValueError(f"Lead time is missing for item {item}.")
        normalized_leads[item] = _integer(lead_times[item], f"Lead time for {item}", 0, horizon)

    children: dict[str, list[dict[str, Any]]] = {item: [] for item in items}
    indegree = {item: 0 for item in items}
    for row in normalized_bom:
        children[row["parent"]].append(row)
        indegree[row["component"]] += 1
    ready = [item for item in items if indegree[item] == 0]
    topo: list[str] = []
    while ready:
        parent = ready.pop(0)
        topo.append(parent)
        for row in children[parent]:
            indegree[row["component"]] -= 1
            if indegree[row["component"]] == 0:
                ready.append(row["component"])
    if len(topo) != len(items):
        raise ValueError("The BOM contains a cycle; multilevel MRP cannot be calculated.")

    gross = {item: [0.0] * (horizon + 1) for item in items}
    for row in normalized_mps:
        gross[row["item"]][row["period"]] += row["demand"]
    scheduled = {item: [0.0] * (horizon + 1) for item in items}
    for row in receipts:
        scheduled[str(row["item"]).strip()][_integer(row.get("period"), "Receipt period", 1, horizon)] += _number(row.get("quantity"), "Receipt quantity")

    period_plans: list[dict[str, Any]] = []
    planned_releases: list[dict[str, Any]] = []
    for item in topo:
        projected = _number(inventory.get(item, 0), f"On-hand inventory for {item}")
        item_releases = []
        for period in range(1, horizon + 1):
            before = projected + scheduled[item][period]
            requirement = gross[item][period]
            net = max(0.0, requirement - before)
            planned_receipt = net
            release_period = period - normalized_leads[item] if net > 1e-9 else None
            if release_period is not None and release_period < 1:
                raise ValueError(
                    f"Planned release for item {item} in receipt period {period} falls before the planning horizon. "
                    "Extend the horizon or move the master-schedule demand later; no partial plan was returned."
                )
            projected = before + planned_receipt - requirement
            if abs(projected) < 1e-9:
                projected = 0.0
            row = {
                "item": item, "period": period, "gross_requirement": requirement,
                "scheduled_receipts": scheduled[item][period], "projected_available_before_requirement": before,
                "net_requirement": net, "planned_order_receipt": planned_receipt,
                "projected_available_end": projected,
                "planned_release_period": release_period,
            }
            period_plans.append(row)
            if net > 1e-9:
                rel = {"item": item, "release_period": int(release_period), "receipt_period": period,
                       "quantity": net, "lead_time_periods": normalized_leads[item]}
                planned_releases.append(rel)
                item_releases.append(rel)
        for bom_row in children[item]:
            component = bom_row["component"]
            for planned in item_releases:
                gross[component][planned["release_period"]] += planned["quantity"] * bom_row["quantity_per"]

    return {
        "status": "PLANNED",
        "method": "Multilevel material requirements planning, lot-for-lot netting",
        "metrics": {
            "item_count": len(items), "bom_link_count": len(normalized_bom),
            "horizon_periods": horizon, "planned_order_count": len(planned_releases),
            "planned_order_quantity_total": sum(row["quantity"] for row in planned_releases),
            "shortage_periods": sum(row["net_requirement"] > 1e-9 for row in period_plans),
        },
        "period_plans": period_plans,
        "planned_releases": planned_releases,
        "formulas": {
            "net_requirement": "max(0, gross requirement − projected available before requirement)",
            "lot_for_lot_receipt": "planned order receipt = net requirement",
            "release_period": "receipt period − item lead time (in integer periods)",
            "dependent_component_demand": "parent planned order release quantity × quantity per parent",
        },
        "assumptions": [
            "Lot-for-lot, deterministic demand, no scrap/yield loss, no capacity constraint and fixed integer lead times.",
            "Components are required at the parent planned-order release period.",
            "Periods 1..H are the entire planning window. Any release before period 1 is rejected rather than silently shifted.",
        ],
        "warnings": [
            "Validate units, BOM revisions, scrap/yield, supplier calendars, lot-size rules and execution constraints before issuing work orders.",
            "This is materials planning, not a finite-capacity production schedule.",
        ],
    }


def simulate_monte_carlo_outcome(
    inputs: Sequence[Mapping[str, Any]],
    base_outcome: float,
    iterations: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    """Seeded additive Monte Carlo model with independent declared input distributions.

    Each input contributes coefficient × sampled value to the base outcome. The
    model does not infer dependencies or correlations; users must not assume these.
    """
    if not isinstance(inputs, Sequence) or isinstance(inputs, (str, bytes)) or not inputs:
        raise ValueError("Define at least one random input.")
    base = _number(base_outcome, "Base outcome")
    n = _integer(iterations, "Iterations", 100, 200_000)
    seed_value = _integer(seed, "Random seed", 0, 2**32 - 1)
    rng = np.random.default_rng(seed_value)
    sampled: dict[str, np.ndarray] = {}
    coefficients: dict[str, float] = {}
    for index, spec in enumerate(inputs, start=1):
        if not isinstance(spec, Mapping):
            raise ValueError(f"Input {index} must be a mapping.")
        name = str(spec.get("name", "")).strip()
        if not name:
            raise ValueError(f"Input {index} needs a non-empty name.")
        if name in sampled:
            raise ValueError(f"Input names must be unique. Duplicate: {name}.")
        distribution = str(spec.get("distribution", "")).strip().lower()
        coefficient = _number(spec.get("coefficient"), f"Coefficient for {name}")
        if distribution == "uniform":
            low = _number(spec.get("low"), f"Uniform low for {name}")
            high = _number(spec.get("high"), f"Uniform high for {name}")
            if low > high:
                raise ValueError(f"Uniform low for {name} cannot exceed its high.")
            values = rng.uniform(low, high, n) if low != high else np.full(n, low, dtype=float)
        elif distribution == "triangular":
            low = _number(spec.get("low"), f"Triangular low for {name}")
            mode = _number(spec.get("mode"), f"Triangular mode for {name}")
            high = _number(spec.get("high"), f"Triangular high for {name}")
            if low > mode or mode > high:
                raise ValueError(f"Triangular input {name} must satisfy low <= mode <= high.")
            values = np.full(n, low, dtype=float) if low == high else rng.triangular(low, mode, high, n)
        elif distribution == "normal":
            mean = _number(spec.get("mean"), f"Normal mean for {name}")
            sd = _number(spec.get("sd"), f"Normal standard deviation for {name}")
            if sd < 0:
                raise ValueError(f"Normal standard deviation for {name} cannot be negative.")
            values = np.full(n, mean, dtype=float) if sd == 0 else rng.normal(mean, sd, n)
        else:
            raise ValueError(f"Unsupported distribution for {name}: {distribution}. Use uniform, triangular or normal.")
        sampled[name] = values
        coefficients[name] = coefficient
    outcomes = np.full(n, base, dtype=float)
    for name, values in sampled.items():
        outcomes += coefficients[name] * values
    if not np.isfinite(outcomes).all():
        raise ValueError("Simulation produced non-finite outcomes; review input ranges and coefficients.")

    mean = float(outcomes.mean())
    stddev = float(outcomes.std(ddof=1))
    percentiles = {str(p): float(np.percentile(outcomes, p)) for p in (5, 50, 95)}
    half = n // 2
    first_mean = float(outcomes[:half].mean())
    second_mean = float(outcomes[half:].mean())
    hist_counts, hist_edges = np.histogram(outcomes, bins=20)
    histogram = [
        {"bin_start": float(hist_edges[i]), "bin_end": float(hist_edges[i + 1]), "count": int(hist_counts[i])}
        for i in range(len(hist_counts))
    ]
    sensitivity = []
    for name, values in sampled.items():
        correlation = float(np.corrcoef(values, outcomes)[0, 1]) if float(values.std()) > 0 and stddev > 0 else 0.0
        sensitivity.append({
            "input": name, "coefficient": coefficients[name],
            "pearson_correlation_with_outcome": correlation,
            "interpretation": "screening association under this sampled model; not causality",
        })
    sensitivity.sort(key=lambda row: abs(row["pearson_correlation_with_outcome"]), reverse=True)
    return {
        "status": "SIMULATED",
        "method": "Independent-seed Monte Carlo; additive outcome model",
        "metrics": {
            "iterations": n, "seed": seed_value, "base_outcome": base,
            "mean": mean, "standard_deviation": stddev,
            "p05": percentiles["5"], "p50": percentiles["50"], "p95": percentiles["95"],
            "probability_outcome_below_zero": float(np.mean(outcomes < 0)),
            "mean_first_half": first_mean, "mean_second_half": second_mean,
            "half_mean_absolute_difference": abs(first_mean - second_mean),
        },
        "histogram": histogram, "sensitivity": sensitivity,
        "formulas": {
            "outcome": "base outcome + sum(coefficient_i × sampled input_i)",
            "mean": "arithmetic mean of simulated outcomes",
            "p05_p50_p95": "empirical 5th, 50th and 95th percentiles",
            "probability_below_zero": "count(outcome < 0) / iterations",
        },
        "assumptions": [
            "Inputs are independently sampled; no correlation or dependence is modeled.",
            "The output model is additive and coefficients are supplied by the analyst.",
            "The half-sample mean comparison is a diagnostic only, not a formal convergence proof.",
        ],
        "warnings": [
            "This is a synthetic stochastic model; outputs are not realized savings, probabilities from plant data, or a calibrated digital twin.",
            "Pearson sensitivity is a screening association under this model, not causal analysis.",
        ],
    }
