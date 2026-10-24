"""Two-parameter Weibull reliability fit with right-censored observations (T041)."""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def fit_weibull_reliability(
    data: pd.DataFrame,
    *,
    time_col: str,
    event_col: str,
    horizons: Sequence[float],
) -> dict[str, Any]:
    """Maximum-likelihood Weibull fit; event_col=1 means failure, 0 means right-censored."""
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("Reliability data must be a non-empty dataframe.")
    if data.columns.has_duplicates:
        raise ValueError("Reliability data must have unique column names.")
    if time_col not in data.columns or event_col not in data.columns:
        raise ValueError("Select existing time-to-event and event-observed columns.")
    if time_col == event_col:
        raise ValueError("Time-to-event and event-observed must be different columns.")
    if len(data) > 100_000:
        raise ValueError("Reliability input is limited to 100000 observations.")
    try:
        times = pd.to_numeric(data[time_col], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Time-to-event values must be numeric; invalid rows are not dropped.") from exc
    if not np.isfinite(times).all() or (times <= 0).any():
        raise ValueError("All time-to-event values must be finite and strictly positive.")
    raw_events = data[event_col]
    try:
        events_num = pd.to_numeric(raw_events, errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Event-observed values must be 1 for observed failure or 0 for right-censoring.") from exc
    if not np.isfinite(events_num).all() or not np.isin(events_num, [0.0, 1.0]).all():
        raise ValueError("Event-observed values must be 1 for observed failure or 0 for right-censoring.")
    events = events_num.astype(bool)
    failure_times = times[events]
    failure_count = int(events.sum())
    censored_count = int((~events).sum())
    if failure_count < 2:
        raise ValueError("At least two observed failures are required for this Weibull fit.")
    if np.unique(failure_times).size < 2:
        raise ValueError("At least two distinct observed failure times are required for a finite two-parameter fit.")

    try:
        horizon_values = np.asarray(list(horizons), dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Reliability horizons must be numeric.") from exc
    if horizon_values.ndim != 1 or horizon_values.size == 0:
        raise ValueError("Provide at least one positive time horizon in the same time unit as the observations.")
    if not np.isfinite(horizon_values).all() or (horizon_values <= 0).any():
        raise ValueError("All reliability horizons must be finite and strictly positive.")
    if horizon_values.size > 200:
        raise ValueError("Reliability analysis accepts at most 200 requested horizons.")

    log_times = np.log(times)
    log_failure_times = log_times[events]
    min_log_scale = float(np.log(times.min()) - 10.0)
    max_log_scale = float(np.log(times.max()) + 10.0)
    # Optimization occurs in log(parameter) space so both parameters remain positive.
    def negative_log_likelihood(params: np.ndarray) -> float:
        log_shape, log_scale = float(params[0]), float(params[1])
        shape = math.exp(log_shape)
        scaled_logs = np.clip(shape * (log_times - log_scale), -700.0, 100.0)
        cumulative_hazard = float(np.exp(scaled_logs).sum())
        ll = (
            failure_count * log_shape
            - failure_count * shape * log_scale
            + (shape - 1.0) * float(log_failure_times.sum())
            - cumulative_hazard
        )
        return -ll if math.isfinite(ll) else float("inf")

    start = np.asarray([math.log(1.5), float(np.log(np.median(times)))], dtype=float)
    fit = minimize(
        negative_log_likelihood,
        start,
        method="L-BFGS-B",
        bounds=[(-4.0, 4.0), (min_log_scale, max_log_scale)],
        options={"maxiter": 5000, "ftol": 1e-12, "gtol": 1e-8},
    )
    if not bool(fit.success) or not np.isfinite(fit.x).all() or not math.isfinite(float(fit.fun)):
        raise RuntimeError("Weibull maximum-likelihood fitting did not converge; inspect the sample/censoring pattern and retry.")
    shape, scale = math.exp(float(fit.x[0])), math.exp(float(fit.x[1]))
    if not (math.isfinite(shape) and shape > 0 and math.isfinite(scale) and scale > 0):
        raise RuntimeError("Weibull fitting returned invalid parameters; result was not accepted.")

    def survival(t: np.ndarray | float) -> np.ndarray | float:
        result = np.exp(-np.power(np.asarray(t, dtype=float) / scale, shape))
        return result

    def hazard(t: np.ndarray | float) -> np.ndarray | float:
        t_array = np.asarray(t, dtype=float)
        return (shape / scale) * np.power(t_array / scale, shape - 1.0)

    horizon_survival = np.asarray(survival(horizon_values), dtype=float)
    horizon_table = pd.DataFrame({
        "time_horizon": horizon_values,
        "reliability_probability": horizon_survival,
        "cumulative_failure_probability": 1.0 - horizon_survival,
        "hazard_rate_per_time_unit": np.asarray(hazard(horizon_values), dtype=float),
    }).sort_values("time_horizon", kind="stable").reset_index(drop=True)

    b10 = float(scale * (-math.log(1.0 - 0.10)) ** (1.0 / shape))
    b50 = float(scale * (-math.log(1.0 - 0.50)) ** (1.0 / shape))
    curve_upper = max(float(times.max()), float(horizon_values.max()))
    curve = np.linspace(float(times.min()), curve_upper, num=100)
    curve_table = pd.DataFrame({
        "time": curve,
        "fitted_reliability": np.asarray(survival(curve), dtype=float),
        "fitted_cumulative_failure_probability": 1.0 - np.asarray(survival(curve), dtype=float),
        "fitted_hazard_rate": np.asarray(hazard(curve), dtype=float),
    })
    warnings = [
        "This is a two-parameter Weibull maximum-likelihood fit with a fixed location of zero.",
        "It assumes independent, comparable lifetimes and non-informative right-censoring; left truncation and competing risks are not modeled.",
        "Parameter confidence intervals, model-selection comparisons and formal goodness-of-fit tests are not included in this bounded implementation.",
        "Confirm time origin, operating exposure, maintenance/repair policy and censoring definition before interpreting results.",
    ]
    if censored_count == 0:
        warnings.append("No censored observations were supplied; this is a complete-event sample.")
    if shape < 1.0:
        hazard_interpretation = "decreasing fitted hazard over time"
    elif shape > 1.0:
        hazard_interpretation = "increasing fitted hazard over time"
    else:
        hazard_interpretation = "approximately constant fitted hazard over time"

    return {
        "tool_id": "T041",
        "status": "CALCULATED",
        "method": "Two-parameter Weibull maximum likelihood with right censoring; location fixed at zero",
        "formula": "S(t) = exp(−(t/scale)^shape); hazard(t) = (shape/scale) × (t/scale)^(shape−1)",
        "parameters": {"shape": shape, "scale": scale, "location": 0.0},
        "assumptions": [
            "event_observed=1 denotes failure observed at the supplied time; event_observed=0 denotes right-censoring at that time.",
            "All observations use a consistent exposure-time unit and an appropriate time origin.",
            "The two-parameter Weibull model is a candidate description, not proof that this distribution is appropriate.",
        ],
        "warnings": warnings,
        "metrics": {
            "observation_count": int(len(times)),
            "observed_failures": failure_count,
            "right_censored_count": censored_count,
            "failure_fraction": float(failure_count / len(times)),
            "weibull_shape": shape,
            "weibull_scale": scale,
            "B10_life": b10,
            "B50_median_life": b50,
            "negative_log_likelihood": float(fit.fun),
            "optimizer_success": True,
            "hazard_interpretation": hazard_interpretation,
        },
        "reliability_at_horizons": horizon_table,
        "fitted_curve": curve_table,
        "parameters_confidence_intervals": None,
    }
