"""Focused, deterministic engineering calculations used by Shoir-IE Tool Library.

These routines implement only explicitly scoped calculations. They do not claim
that the full specialist acceptance contract for each target tool is satisfied.
"""
from __future__ import annotations

import math
import random
import statistics
from statistics import NormalDist
from typing import Any, Mapping, Sequence

from scipy.stats import weibull_min


def _finite_number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def work_sampling(activity_observations: int, total_observations: int, confidence: float = 0.95) -> dict[str, Any]:
    """Estimate an activity proportion and Wilson score interval.

    The interval assumes independent Bernoulli observations from the population
    and does not correct for clustered, stratified, or biased sampling.
    """
    if isinstance(activity_observations, bool) or isinstance(total_observations, bool):
        raise ValueError("Observation counts must be integers, not booleans.")
    if not isinstance(activity_observations, int) or not isinstance(total_observations, int):
        raise ValueError("Observation counts must be whole numbers.")
    if total_observations <= 0:
        raise ValueError("Total observations must be greater than zero.")
    if activity_observations < 0 or activity_observations > total_observations:
        raise ValueError("Activity observations must be between zero and total observations.")
    confidence = _finite_number(confidence, "Confidence level")
    if confidence not in {0.90, 0.95, 0.99}:
        raise ValueError("Confidence level must be 0.90, 0.95, or 0.99.")
    n = total_observations
    p = activity_observations / n
    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    denom = 1.0 + (z * z / n)
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt((p * (1.0 - p) / n) + (z * z / (4.0 * n * n))) / denom
    lower, upper = max(0.0, center - half), min(1.0, center + half)
    margin = (upper - lower) / 2.0
    warnings = []
    if n < 30:
        warnings.append("Small sample (n<30): treat the estimate as preliminary.")
    if margin > 0.10:
        warnings.append("The confidence interval is wider than 10 percentage points.")
    return {
        "activity_count": activity_observations,
        "total_count": n,
        "proportion": p,
        "percent": p * 100.0,
        "confidence": confidence,
        "ci_lower": lower,
        "ci_upper": upper,
        "margin_of_error": margin,
        "adequate_sample": n >= 30 and margin <= 0.10,
        "method": "Wilson score interval for a binomial proportion",
        "assumptions": ["Independent observations", "Representative sampling", "Binary activity classification"],
        "warnings": warnings,
    }


def fit_weibull_uncensored(failure_times: Sequence[float]) -> dict[str, Any]:
    """Fit a two-parameter Weibull model to complete, uncensored positive times.

    Right-/left-censored records are not supported by this function and must not
    be passed as ordinary failures.
    """
    values = [_finite_number(v, "Failure time") for v in failure_times]
    if len(values) < 3:
        raise ValueError("At least three complete failure times are required for this fit.")
    if any(v <= 0 for v in values):
        raise ValueError("Every complete failure time must be strictly positive.")
    shape, _loc, scale = weibull_min.fit(values, floc=0)
    if not (math.isfinite(shape) and math.isfinite(scale) and shape > 0 and scale > 0):
        raise ValueError("Weibull fit did not produce valid positive parameters.")
    sorted_values = sorted(values)
    fitted_cdf = [float(weibull_min.cdf(v, shape, loc=0, scale=scale)) for v in sorted_values]
    empirical_cdf = [(i + 1) / len(sorted_values) for i in range(len(sorted_values))]
    ks_distance = max(abs(emp - fit) for emp, fit in zip(empirical_cdf, fitted_cdf))
    log_likelihood = float(sum(weibull_min.logpdf(v, shape, loc=0, scale=scale) for v in values))
    median_life = float(scale * math.log(2.0) ** (1.0 / shape))
    warnings = []
    if len(values) < 10:
        warnings.append("Fewer than 10 failures: parameter and fit-diagnostic uncertainty may be high.")
    warnings.append("Fit assumes independent, complete, uncensored time-to-failure observations.")
    return {
        "count": len(values),
        "shape": float(shape),
        "scale": float(scale),
        "median_life": median_life,
        "log_likelihood": log_likelihood,
        "ks_distance_descriptive": float(ks_distance),
        "sorted_times": sorted_values,
        "empirical_cdf": empirical_cdf,
        "fitted_cdf": fitted_cdf,
        "method": "Two-parameter Weibull maximum-likelihood fit with location fixed at zero",
        "censoring_supported": False,
        "warnings": warnings,
    }


def mtbf_mttr(operating_hours: float, failure_count: int, repair_hours: Sequence[float]) -> dict[str, Any]:
    """Calculate MTBF from cumulative operating hours and MTTR from repair episodes."""
    operating = _finite_number(operating_hours, "Operating hours")
    if operating <= 0:
        raise ValueError("Operating hours must be greater than zero.")
    if isinstance(failure_count, bool) or not isinstance(failure_count, int) or failure_count <= 0:
        raise ValueError("Failure count must be a positive whole number.")
    repairs = [_finite_number(v, "Repair duration in hours") for v in repair_hours]
    if len(repairs) != failure_count:
        raise ValueError("Provide exactly one repair duration for each counted failure.")
    if any(v < 0 for v in repairs):
        raise ValueError("Repair durations cannot be negative.")
    mean_repair = statistics.fmean(repairs)
    warnings = []
    if mean_repair == 0:
        warnings.append("Mean repair duration is zero; confirm the input represents actual repair time.")
    return {
        "operating_hours": operating,
        "failure_count": failure_count,
        "repair_count": len(repairs),
        "mtbf_hours": operating / failure_count,
        "mttr_hours": mean_repair,
        "method": "MTBF = cumulative operating hours / counted failures; MTTR = arithmetic mean of repair durations",
        "assumptions": ["Operating hours and repair durations use hours", "The failure count matches the repair episodes"],
        "warnings": warnings,
    }


def inventory_policy(
    annual_demand: float,
    order_cost: float,
    annual_holding_cost_per_unit: float,
    mean_demand_per_period: float,
    std_demand_per_period: float,
    lead_time_periods: float,
    service_z: float,
) -> dict[str, Any]:
    """Calculate EOQ, safety stock, and reorder point under independent-period demand.

    Lead time is expressed in the same base period as demand mean and standard
    deviation; service_z is a caller-supplied standard-normal quantile.
    """
    annual_demand = _finite_number(annual_demand, "Annual demand")
    order_cost = _finite_number(order_cost, "Order cost")
    holding = _finite_number(annual_holding_cost_per_unit, "Annual holding cost per unit")
    mean_demand = _finite_number(mean_demand_per_period, "Mean demand per period")
    sigma = _finite_number(std_demand_per_period, "Demand standard deviation per period")
    lead = _finite_number(lead_time_periods, "Lead time in periods")
    z = _finite_number(service_z, "Service factor z")
    if annual_demand <= 0 or order_cost < 0 or holding <= 0:
        raise ValueError("Annual demand and holding cost must be positive; order cost cannot be negative.")
    if mean_demand < 0 or sigma < 0 or lead <= 0 or z < 0:
        raise ValueError("Mean demand/standard deviation/z cannot be negative; lead time must be positive.")
    eoq = math.sqrt((2.0 * annual_demand * order_cost) / holding)
    safety = z * sigma * math.sqrt(lead)
    cycle_demand = mean_demand * lead
    warnings = []
    if sigma == 0:
        warnings.append("Zero demand variation was supplied; calculated safety stock is zero.")
    return {
        "eoq_units": eoq,
        "safety_stock_units": safety,
        "reorder_point_units": cycle_demand + safety,
        "expected_lead_time_demand_units": cycle_demand,
        "method": "EOQ = sqrt(2DS/H); safety stock = z·sigma·sqrt(L); reorder point = mean demand·L + safety stock",
        "assumptions": [
            "Constant annual demand and order/holding costs for EOQ",
            "Lead time uses the same period as per-period demand statistics",
            "Demand errors are independent with constant per-period standard deviation",
            "Service factor z is supplied for the selected target service level",
        ],
        "warnings": warnings,
    }


def _draw_independent_driver(spec: Mapping[str, Any], rng: random.Random, name: str) -> float:
    if not isinstance(spec, Mapping):
        raise ValueError(f"Driver {name!r} configuration must be an object.")
    kind = str(spec.get("distribution", "")).strip().lower()
    if kind == "normal":
        mean = _finite_number(spec.get("mean"), f"{name} mean")
        sd = _finite_number(spec.get("sd"), f"{name} standard deviation")
        if sd < 0:
            raise ValueError(f"{name} standard deviation cannot be negative.")
        return rng.gauss(mean, sd)
    if kind == "uniform":
        low = _finite_number(spec.get("low"), f"{name} low")
        high = _finite_number(spec.get("high"), f"{name} high")
        if low > high:
            raise ValueError(f"{name} low cannot exceed high.")
        return rng.uniform(low, high)
    if kind == "triangular":
        low = _finite_number(spec.get("low"), f"{name} low")
        mode = _finite_number(spec.get("mode"), f"{name} mode")
        high = _finite_number(spec.get("high"), f"{name} high")
        if not low <= mode <= high or low == high:
            raise ValueError(f"{name} must satisfy low <= mode <= high and low < high.")
        return rng.triangular(low, high, mode)
    if kind == "lognormal":
        mu = _finite_number(spec.get("mu"), f"{name} log-mean")
        sigma = _finite_number(spec.get("sigma"), f"{name} log standard deviation")
        if sigma < 0:
            raise ValueError(f"{name} log standard deviation cannot be negative.")
        return rng.lognormvariate(mu, sigma)
    raise ValueError(f"{name} distribution must be normal, uniform, triangular, or lognormal.")


def _pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    dx = [v - mx for v in x]
    dy = [v - my for v in y]
    den = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if den == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / den


def monte_carlo_independent_sum(
    drivers: Mapping[str, Mapping[str, Any]], iterations: int = 10000, seed: int = 42
) -> dict[str, Any]:
    """Simulate the sum of independent numeric drivers using a recorded seed.

    All drivers must represent compatible units. Correlation between drivers is
    not modeled. Split-half mean comparison is a screening indicator, not proof
    of statistical convergence or a causal sensitivity analysis.
    """
    if not isinstance(drivers, Mapping) or not 1 <= len(drivers) <= 8:
        raise ValueError("Provide between one and eight independent numeric drivers.")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 1000 <= iterations <= 100000:
        raise ValueError("Iterations must be a whole number between 1,000 and 100,000.")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Seed must be a whole number.")
    names = [str(name).strip() for name in drivers]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("Every risk driver must have a unique non-empty name.")
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {
        name: [_draw_independent_driver(drivers[name], rng, name) for _ in range(iterations)]
        for name in names
    }
    outcomes = [sum(samples[name][i] for name in names) for i in range(iterations)]
    if not all(math.isfinite(v) for v in outcomes):
        raise ValueError("Simulation produced non-finite outcomes; review the distribution parameters.")
    ordered = sorted(outcomes)
    def percentile(probability: float) -> float:
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * probability))]
    mean = statistics.fmean(outcomes)
    sd = statistics.stdev(outcomes)
    half = iterations // 2
    mean_a = statistics.fmean(outcomes[:half])
    mean_b = statistics.fmean(outcomes[half:])
    split_gap = abs(mean_a - mean_b) / max(abs(mean), sd, 1e-12)
    warnings = [
        "Drivers are sampled independently; cross-driver correlation is not modeled.",
        "Correlation sensitivity scores are descriptive associations, not causal effects.",
        "All driver values must use compatible units before their sum is meaningful.",
    ]
    return {
        "iterations": iterations,
        "seed": seed,
        "mean": mean,
        "standard_deviation": sd,
        "p05": percentile(0.05),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "split_half_relative_mean_gap": split_gap,
        "split_half_screen_passed": split_gap <= 0.05,
        "input_sensitivity_correlation": {name: _pearson(values, outcomes) for name, values in samples.items()},
        "sampled_drivers": samples,
        "outcomes": outcomes,
        "method": "Seeded Monte Carlo simulation with independent named drivers",
        "warnings": warnings,
    }
