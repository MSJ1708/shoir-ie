"""Robust imported-series anomaly screen with explicit freshness and no live-connector claim (T048)."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


_MAD_NORMALIZER = 0.6744897501960817


def screen_time_series_anomalies(
    data: pd.DataFrame,
    *,
    timestamp_col: str,
    series_col: str,
    value_col: str,
    threshold: float = 3.5,
    as_of_datetime: str,
    minimum_points_per_series: int = 5,
) -> dict[str, Any]:
    """Flag global median/MAD outliers within each imported time series."""
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("Anomaly screen requires a non-empty time-series table.")
    if data.columns.has_duplicates:
        raise ValueError("Time-series input must have unique column names.")
    if len(data) > 1_000_000:
        raise ValueError("Anomaly screen is limited to 1000000 rows.")
    selected = [timestamp_col, series_col, value_col]
    if len(set(selected)) != 3 or any(col not in data.columns for col in selected):
        raise ValueError("Select three distinct existing timestamp, series and numeric value columns.")
    try:
        threshold_val = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("Anomaly threshold must be numeric.") from exc
    if not math.isfinite(threshold_val) or not 2.0 <= threshold_val <= 10.0:
        raise ValueError("Anomaly threshold must be finite and between 2 and 10.")
    try:
        min_points = int(minimum_points_per_series)
    except (TypeError, ValueError) as exc:
        raise ValueError("Minimum observations must be a whole number from 5 to 10000.") from exc
    if min_points < 5 or min_points > 10000 or min_points != minimum_points_per_series:
        raise ValueError("Minimum observations must be a whole number from 5 to 10000.")
    try:
        as_of = pd.Timestamp(as_of_datetime)
    except (TypeError, ValueError) as exc:
        raise ValueError("As-of timestamp must be ISO-8601 with a timezone, e.g. 2026-10-24T12:00:00Z.") from exc
    if as_of.tzinfo is None:
        raise ValueError("As-of timestamp must include a timezone.")
    as_of = as_of.tz_convert("UTC")

    frame = data[selected].copy(deep=True)
    if frame.isna().any().any():
        raise ValueError("Missing timestamp/series/value rows are not silently dropped.")
    frame[series_col] = frame[series_col].astype(str).str.strip()
    if (frame[series_col] == "").any():
        raise ValueError("Series identifiers must be non-empty.")
    try:
        frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], errors="raise", utc=True)
        frame[value_col] = pd.to_numeric(frame[value_col], errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Timestamps must be parseable and values must be numeric.") from exc
    if frame[timestamp_col].isna().any() or not np.isfinite(frame[value_col].to_numpy(dtype=float)).all():
        raise ValueError("Timestamp and numeric values must be finite and valid.")
    if (frame[timestamp_col] > as_of).any():
        raise ValueError("Observation timestamps cannot be after the as-of timestamp.")
    if frame.duplicated([series_col, timestamp_col]).any():
        raise ValueError("Each series/timestamp combination must be unique; aggregate duplicate observations explicitly.")

    rows = []
    series_summaries = []
    for series_name, group in frame.groupby(series_col, sort=True):
        group = group.sort_values(timestamp_col, kind="stable")
        values = group[value_col].to_numpy(dtype=float)
        n = len(values)
        if n < min_points:
            raise ValueError(f"Series '{series_name}' has {n} observations; at least {min_points} are required.")
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        flagged_count = 0
        for _, raw in group.iterrows():
            value = float(raw[value_col])
            delta = value - median
            if mad > 0:
                robust_z = _MAD_NORMALIZER * delta / mad
                flagged = abs(robust_z) > threshold_val
                reason = "ABOVE_ROBUST_MAD_THRESHOLD" if flagged else "WITHIN_THRESHOLD"
            else:
                robust_z = None
                flagged = delta != 0
                reason = "MAD_ZERO_DEVIATION" if flagged else "CONSTANT_BASELINE"
            flagged_count += int(flagged)
            age_days = float((as_of - raw[timestamp_col]).total_seconds() / 86400.0)
            rows.append({
                "series_id": str(series_name),
                "timestamp_utc": raw[timestamp_col].isoformat(),
                "value": value,
                "series_median": median,
                "series_mad": mad,
                "modified_robust_z_score": float(robust_z) if robust_z is not None and math.isfinite(float(robust_z)) else None,
                "anomaly_flag": bool(flagged),
                "anomaly_reason": reason,
                "data_age_days": age_days,
            })
        series_summaries.append({
            "series_id": str(series_name),
            "observation_count": int(n),
            "median": median,
            "median_absolute_deviation": mad,
            "flagged_count": int(flagged_count),
            "flagged_percent": float(flagged_count / n * 100.0),
            "latest_timestamp_utc": group[timestamp_col].max().isoformat(),
            "latest_data_age_days": float((as_of - group[timestamp_col].max()).total_seconds() / 86400.0),
        })
    result_frame = pd.DataFrame(rows).sort_values(["series_id", "timestamp_utc"], kind="stable").reset_index(drop=True)
    summary_frame = pd.DataFrame(series_summaries)
    total = len(result_frame)
    flagged_total = int(result_frame["anomaly_flag"].sum())
    warnings = [
        "This offline robust-MAD screen flags unusual observations relative to each supplied series; it does not diagnose a physical fault or establish cause.",
        "Global median/MAD may mask sustained shifts or regime changes; combine with domain thresholds/control charts and reviewed maintenance context.",
        "A flag is a review prompt and may be a false positive. Review sensor calibration, timestamp alignment and source quality before taking operational action.",
        "This function analyzes the supplied table only; it does not subscribe to live telemetry or configure the external monitoring connector.",
    ]
    if (summary_frame["median_absolute_deviation"] == 0).any():
        warnings.append("At least one series has zero MAD; non-median values are flagged without a finite robust z-score.")
    return {
        "tool_id": "T048",
        "status": "CALCULATED_OFFLINE_DATA",
        "method": "Per-series modified robust z-score using median absolute deviation (MAD)",
        "formula": "Modified robust z = 0.67448975 × (value − series median) / MAD; flag when absolute score exceeds threshold",
        "threshold": threshold_val,
        "as_of_datetime_utc": as_of.isoformat(),
        "warnings": warnings,
        "assumptions": [
            "The supplied timestamps and measurement values are comparable within each series.",
            "The chosen global-series baseline is appropriate; this method is not a rolling change-point detector.",
            "At least the configured minimum observation count is present for every series.",
        ],
        "metrics": {
            "observation_count": int(total),
            "series_count": int(len(summary_frame)),
            "flagged_observation_count": flagged_total,
            "flagged_observation_percent": float(flagged_total / total * 100) if total else 0.0,
            "threshold": threshold_val,
            "latest_observation_age_days": float(result_frame["data_age_days"].min()) if total else None,
            "oldest_observation_age_days": float(result_frame["data_age_days"].max()) if total else None,
            "external_connector_live": False,
        },
        "anomaly_table": result_frame,
        "series_summary": summary_frame,
    }
