"""Deterministic starter industrial-engineering calculations with explicit units.

Methods in this module are calculators, not evidence of actual plant performance.
Inputs must be measured/approved by the user; results expose formulas and scope.
"""

from __future__ import annotations

import math
from statistics import NormalDist, mean, stdev
from typing import Any, Iterable

_TIME_TO_SECONDS = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "min": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "day": 86400.0,
    "days": 86400.0,
}
TIME_UNIT_OPTIONS = ("s", "min", "h", "day")


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite; NaN and infinity are not supported.")
    return number


def _time_factor(unit: str, field: str) -> tuple[str, float]:
    key = str(unit or "").strip().lower()
    if key not in _TIME_TO_SECONDS:
        raise ValueError(f"{field} must use one of the supported time units: seconds, minutes, hours, or days.")
    return key, _TIME_TO_SECONDS[key]


def calculate_standard_time(
    observed_times: Iterable[float],
    time_unit: str,
    performance_rating_percent: float,
    allowance_percent: float,
) -> dict[str, Any]:
    """Compute mean observed, normal, and standard time.

    Allowance convention: allowance_percent is the fraction of standard time
    reserved for personal needs, fatigue, and unavoidable delays. Therefore
    standard_time = normal_time / (1 - allowance_fraction).
    """
    _, factor = _time_factor(time_unit, "Time unit")
    try:
        observations = [_finite(v, "Observed time") for v in observed_times]
    except TypeError as exc:
        raise ValueError("Observed times must be a sequence of numeric observations.") from exc
    if not observations:
        raise ValueError("Enter at least one observed cycle time.")
    if any(v <= 0 for v in observations):
        raise ValueError("Observed cycle times must be greater than zero.")
    rating = _finite(performance_rating_percent, "Performance rating (%)")
    allowance = _finite(allowance_percent, "Allowance (%)")
    if rating <= 0 or rating > 200:
        raise ValueError("Performance rating must be greater than 0% and no more than 200%.")
    if allowance < 0 or allowance >= 100:
        raise ValueError("Allowance must be at least 0% and below 100%.")
    observed_mean = mean(observations)
    normal_time = observed_mean * rating / 100.0
    standard_time = normal_time / (1.0 - allowance / 100.0)
    sample_sd = stdev(observations) if len(observations) > 1 else 0.0
    cv_percent = (sample_sd / observed_mean * 100.0) if observed_mean else 0.0
    values = [observed_mean, normal_time, standard_time, sample_sd]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("The standard-time calculation produced a non-finite result.")
    unit = str(time_unit).strip()
    return {
        "status": "COMPLETED",
        "observation_count": len(observations),
        "mean_observed_time": observed_mean,
        "sample_standard_deviation": sample_sd,
        "coefficient_of_variation_percent": cv_percent,
        "performance_rating_percent": rating,
        "normal_time": normal_time,
        "allowance_percent": allowance,
        "standard_time": standard_time,
        "time_unit": unit,
        "method": "Arithmetic mean of valid observed cycle times; normal time adjusted by performance rating; standard time grossed up for allowance as a fraction of standard time.",
        "formula": "mean = sum(observations) / n; normal = mean × rating / 100; standard = normal / (1 − allowance / 100)",
        "assumptions": [
            "All observed times use the same time unit and represent comparable work cycles.",
            "Performance rating is the user's stated assessment; it is not inferred by the calculator.",
            "Allowance is defined as a percentage of standard time, not a percentage added to normal time.",
            "Sampling representativeness and work-method consistency must be reviewed by the engineer.",
        ],
        "warnings": ["One observation is insufficient to estimate process-time variability." ] if len(observations) < 2 else [],
        "provenance": "User-supplied observations and rating/allowance inputs; no plant data are fetched.",
    }


def calculate_work_sampling(
    activity_count: int,
    total_observations: int,
    confidence_percent: float = 95.0,
    target_margin_percent: float = 5.0,
) -> dict[str, Any]:
    """Estimate an activity proportion with a Wilson score confidence interval."""
    activity_raw = _finite(activity_count, "Activity count")
    total_raw = _finite(total_observations, "Total observations")
    confidence = _finite(confidence_percent, "Confidence level (%)")
    margin = _finite(target_margin_percent, "Target margin of error (%)")
    if not activity_raw.is_integer() or not total_raw.is_integer():
        raise ValueError("Activity and total observation counts must be integers.")
    successes, n = int(activity_raw), int(total_raw)
    if n <= 0:
        raise ValueError("Total observations must be greater than zero.")
    if successes < 0 or successes > n:
        raise ValueError("Activity count must be between zero and total observations.")
    if confidence <= 50 or confidence >= 100:
        raise ValueError("Confidence level must be greater than 50% and below 100%.")
    if margin <= 0 or margin >= 50:
        raise ValueError("Target margin of error must be greater than 0% and below 50%.")
    p = successes / n
    z = NormalDist().inv_cdf(0.5 + confidence / 200.0)
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denominator
    half_width = (
        z * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))
        / denominator
    )
    lower = max(0.0, center - half_width)
    upper = min(1.0, center + half_width)
    margin_fraction = margin / 100.0
    required_n = math.ceil((z2 * 0.25) / (margin_fraction * margin_fraction))
    warnings = []
    if n < required_n:
        warnings.append(
            f"Sample size is below the conservative planning estimate of {required_n} observations "
            f"for ±{margin:g} percentage points at {confidence:g}% confidence."
        )
    if p in (0.0, 1.0):
        warnings.append("No observed variation in this sample does not prove the true activity proportion is zero or one.")
    return {
        "status": "COMPLETED",
        "activity_count": successes,
        "non_activity_count": n - successes,
        "total_observations": n,
        "activity_proportion": p,
        "activity_percent": p * 100.0,
        "confidence_percent": confidence,
        "wilson_interval_lower_percent": lower * 100.0,
        "wilson_interval_upper_percent": upper * 100.0,
        "target_margin_percent": margin,
        "conservative_required_sample_size": required_n,
        "additional_observations_suggested": max(0, required_n - n),
        "method": "Wilson score interval for a binomial activity proportion; conservative worst-case sample size uses p=0.5.",
        "formula": "p = x/n; Wilson interval uses z for the stated confidence; planning n = ceil(z² × 0.25 / margin²)",
        "assumptions": [
            "Observations represent the population and time window of interest.",
            "Each observation is classified consistently as activity or non-activity.",
            "The simple binomial interval does not correct for clustered or dependent observations.",
        ],
        "warnings": warnings,
        "provenance": "User-supplied observation counts and stated confidence/margin; no activity classification is inferred.",
    }


def calculate_takt_capacity(
    demand_units: float,
    demand_period: str,
    available_time: float,
    available_time_unit: str,
    planned_unavailable_time: float = 0.0,
    unavailable_time_unit: str = "min",
    cycle_time: float | None = None,
    cycle_time_unit: str = "min",
    takt_output_unit: str = "min",
) -> dict[str, Any]:
    """Calculate takt and optional capacity feasibility for one explicit period.

    All durations are converted to seconds internally. Demand and available
    productive time must refer to the same user-defined period (e.g. one shift).
    """
    demand = _finite(demand_units, "Demand")
    available = _finite(available_time, "Available time")
    breaks = _finite(planned_unavailable_time, "Planned unavailable time")
    period = str(demand_period or "").strip()
    if not period:
        raise ValueError("Specify the period shared by demand and available time (for example, one shift).")
    if demand <= 0:
        raise ValueError("Demand must be greater than zero.")
    if available <= 0:
        raise ValueError("Available time must be greater than zero.")
    if breaks < 0:
        raise ValueError("Planned unavailable time cannot be negative.")
    _, available_factor = _time_factor(available_time_unit, "Available-time unit")
    _, breaks_factor = _time_factor(unavailable_time_unit, "Unavailable-time unit")
    _, takt_factor = _time_factor(takt_output_unit, "Takt display unit")
    available_seconds = available * available_factor
    breaks_seconds = breaks * breaks_factor
    net_seconds = available_seconds - breaks_seconds
    if net_seconds <= 0:
        raise ValueError("Planned unavailable time must be less than available time.")
    takt_seconds = net_seconds / demand
    takt_display = takt_seconds / takt_factor
    output: dict[str, Any] = {
        "status": "COMPLETED",
        "demand_units_per_period": demand,
        "period": period,
        "available_time": available,
        "available_time_unit": str(available_time_unit).strip(),
        "planned_unavailable_time": breaks,
        "planned_unavailable_time_unit": str(unavailable_time_unit).strip(),
        "net_available_time_seconds": net_seconds,
        "takt_time": takt_display,
        "takt_time_unit": f"{str(takt_output_unit).strip()}/unit",
        "method": "Convert available and planned unavailable durations to seconds, subtract unavailable time, then divide net productive time by demand.",
        "formula": "takt time = (available time − planned unavailable time) / demand",
        "assumptions": [
            "Demand and available time refer to the same user-defined period.",
            "All planned breaks/downtime are represented in planned unavailable time.",
            "Takt is a demand-paced target, not a measured cycle time or a guaranteed production rate.",
        ],
        "warnings": [],
        "provenance": "User-supplied demand and shift/time assumptions; no actual plant capacity is implied.",
    }
    if cycle_time is None:
        output.update({
            "cycle_time": None,
            "capacity_units_per_period": None,
            "capacity_margin_units": None,
            "capacity_feasible": None,
        })
        output["warnings"].append("Capacity feasibility was not evaluated because no measured/assumed cycle time was supplied.")
        return output
    cycle = _finite(cycle_time, "Cycle time")
    if cycle <= 0:
        raise ValueError("Cycle time must be greater than zero.")
    _, cycle_factor = _time_factor(cycle_time_unit, "Cycle-time unit")
    cycle_seconds = cycle * cycle_factor
    capacity = net_seconds / cycle_seconds
    if not math.isfinite(capacity):
        raise ValueError("The capacity calculation produced a non-finite result.")
    output.update({
        "cycle_time": cycle,
        "cycle_time_unit": str(cycle_time_unit).strip(),
        "cycle_time_seconds": cycle_seconds,
        "capacity_units_per_period": capacity,
        "capacity_margin_units": capacity - demand,
        "capacity_feasible": capacity >= demand,
    })
    output["formula"] += "; theoretical capacity = net available time / cycle time"
    output["warnings"].append(
        "Theoretical capacity assumes the supplied cycle time applies throughout the net available period and excludes unmodelled losses."
    )
    return output
