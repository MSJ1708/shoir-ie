"""Additive 100-tool library and a small set of deterministic quick methods.

The library is embedded in the existing Core IE Tools module to preserve the current
navigation and page layout. A catalog entry is not permission to execute a specialist
method: only named engines in QUICK_ENGINE_IDS can be dispatched here. Other entries
link to the existing route (when permitted) or remain visibly incomplete.
"""
from __future__ import annotations

import io
import hashlib
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from shoir_100_tool_registry import (
    TOOL_BY_ID,
    TOOL_CATALOG,
    VALID_IMPLEMENTATION_STATUSES,
    tool_access_allowed,
    validate_tool_catalog,
    visible_tools,
)

MAX_PROFILE_BYTES = 20 * 1024 * 1024
QUICK_ENGINE_IDS = {"T011", "T013", "T014", "T016", "T019", "T021", "T022", "T023", "T026", "T032", "T042", "T055", "T078", "T081"}


def _dataframe_fingerprint(frame: pd.DataFrame) -> str:
    """Stable in-session source signature for stale-preview protection."""
    signature = json.dumps(
        {"columns": [str(x) for x in frame.columns], "dtypes": [str(x) for x in frame.dtypes]},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    try:
        values = pd.util.hash_pandas_object(frame, index=True).values.tobytes()
    except (TypeError, ValueError):
        values = frame.to_json(orient="split", date_format="iso", default_handler=str).encode("utf-8")
    return hashlib.sha256(signature + values).hexdigest()


def import_dataset_preview(filename: Any, payload: Any, sheet_name: Any = None) -> dict[str, Any]:
    """Parse CSV/XLS/XLSX into a staged frame without mutating the active dataset."""
    name = str(filename or "").strip()
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise ValueError("The uploaded file is empty. The active dataset was not changed.")
    if len(payload) > MAX_PROFILE_BYTES:
        raise ValueError(f"The file exceeds the {MAX_PROFILE_BYTES // (1024 * 1024)} MiB import limit. The active dataset was not changed.")
    suffix = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    try:
        if suffix == "csv":
            try:
                frame = pd.read_csv(io.BytesIO(payload))
            except UnicodeDecodeError:
                frame = pd.read_csv(io.BytesIO(payload), encoding="utf-8-sig")
            selected_sheet = None
        elif suffix in {"xlsx", "xlsm", "xls"}:
            workbook = pd.ExcelFile(io.BytesIO(payload))
            if not workbook.sheet_names:
                raise ValueError("The workbook has no readable sheets.")
            selected_sheet = str(sheet_name or workbook.sheet_names[0])
            if selected_sheet not in workbook.sheet_names:
                raise ValueError(f"Sheet '{selected_sheet}' was not found in the uploaded workbook.")
            frame = pd.read_excel(workbook, sheet_name=selected_sheet)
        else:
            raise ValueError("Unsupported file type. Upload CSV, XLSX, XLSM, or XLS.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The file could not be parsed as a supported CSV/Excel workbook. The active dataset was not changed.") from exc
    if not isinstance(frame, pd.DataFrame) or len(frame.columns) == 0:
        raise ValueError("The selected file or sheet has no columns. The active dataset was not changed.")
    warnings = []
    if frame.empty:
        warnings.append("The selected sheet has columns but no data rows.")
    if not frame.columns.is_unique:
        warnings.append("Duplicate column names were detected; rename them before using the profiler or cleaner.")
    return {
        "status": "STAGED", "tool_id": "T011", "canonical_name": "Universal Data Importer",
        "data_status": "IMPORTED", "filename": name, "sheet_name": selected_sheet,
        "dataframe": frame.copy(deep=True),
        "metrics": {"row_count": int(len(frame)), "column_count": int(len(frame.columns)),
                    "missing_cells": int(frame.isna().sum().sum())},
        "method": "CSV or selected Excel sheet is parsed into a staged dataframe before explicit session apply.",
        "assumptions": ["The uploaded file is untrusted input and is parsed as data, never as executable instructions.",
                        "Applying the staged dataset is a separate user action; cross-login persistence is not implied."],
        "warnings": warnings, "source_fingerprint": hashlib.sha256(bytes(payload)).hexdigest(),
        "input_bytes": len(payload),
    }


def reversible_clean_candidate(
    dataframe: Any, *, drop_duplicates: bool = True, missing_strategy: str = "keep",
) -> dict[str, Any]:
    """Create a candidate copy and audit; never mutate the user's source frame."""
    if not isinstance(dataframe, pd.DataFrame):
        raise ValueError("A pandas DataFrame is required before cleaning.")
    if len(dataframe) > 1_000_000 or len(dataframe.columns) > 500:
        raise ValueError("Cleaner limit is 1,000,000 rows and 500 columns.")
    if not dataframe.columns.is_unique:
        raise ValueError("Column names must be unique before cleaning; the source table was not modified.")
    if missing_strategy not in {"keep", "drop_rows", "fill_median"}:
        raise ValueError("Missing-value strategy must be keep, drop_rows, or fill_median.")
    source = dataframe.copy(deep=True)
    candidate = source.copy(deep=True)
    source_fingerprint = _dataframe_fingerprint(source)
    source_rows = len(source)
    source_missing = int(source.isna().sum().sum())
    removed_duplicates = 0
    if drop_duplicates:
        candidate = candidate.drop_duplicates().copy()
        removed_duplicates = source_rows - len(candidate)
    dropped_missing = 0
    filled_cells = 0
    warnings = []
    if missing_strategy == "drop_rows":
        before = len(candidate)
        candidate = candidate.dropna().copy()
        dropped_missing = before - len(candidate)
    elif missing_strategy == "fill_median":
        for column in candidate.select_dtypes(include="number").columns:
            count = int(candidate[column].isna().sum())
            if count:
                median_value = candidate[column].median()
                if pd.notna(median_value):
                    candidate[column] = candidate[column].fillna(median_value)
                    filled_cells += count
        remaining = int(candidate.isna().sum().sum())
        if remaining:
            warnings.append(f"{remaining} missing cells remain, because this cleaner does not auto-fill nonnumeric columns.")
    return {
        "status": "PREVIEW", "tool_id": "T014", "canonical_name": "Reversible Data Cleaner",
        "data_status": "IMPORTED",
        "dataframe": candidate.copy(deep=True),
        "metrics": {"source_rows": int(source_rows), "candidate_rows": int(len(candidate)),
                    "removed_duplicate_rows": int(removed_duplicates), "dropped_missing_rows": int(dropped_missing),
                    "source_missing_cells": int(source_missing), "imputed_numeric_cells": int(filled_cells),
                    "candidate_missing_cells": int(candidate.isna().sum().sum())},
        "method": "Candidate-copy cleaning: exact duplicate-row removal followed by the selected missing-value strategy.",
        "assumptions": ["The original dataframe is not mutated by preview.", "Median imputation applies only to numeric columns.",
                        "Undo is session-scoped and does not imply durable version history."],
        "warnings": warnings, "source_fingerprint": source_fingerprint,
        "candidate_fingerprint": _dataframe_fingerprint(candidate),
        "missing_strategy": missing_strategy, "drop_duplicates": bool(drop_duplicates),
    }


class ToolEntitlementError(PermissionError):
    """Raised before execution when the canonical tool ID is not entitled."""


class ToolNotImplementedError(NotImplementedError):
    """Raised when a target has no standalone engine and must not be faked."""


def _finite_number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite.")
    return result


def profile_dataframe(frame: pd.DataFrame) -> dict[str, Any]:
    """Profile a copy of the source frame; never mutate or silently clean it."""
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("A pandas DataFrame is required.")
    if frame.empty or len(frame.columns) == 0:
        raise ValueError("The selected dataset has no rows or columns.")
    if len(frame) > 1_000_000 or len(frame.columns) > 500:
        raise ValueError("The profiler limit is 1,000,000 rows and 500 columns.")
    source = frame.copy(deep=True)
    if not source.columns.is_unique:
        raise ValueError("Column names must be unique before profiling. Rename duplicate columns and retry; the source dataset was not modified.")
    rows = len(source)
    column_rows: list[dict[str, Any]] = []
    for column in source.columns:
        series = source[column]
        missing_count = int(series.isna().sum())
        item: dict[str, Any] = {
            "column": str(column),
            "dtype": str(series.dtype),
            "rows": rows,
            "missing_count": missing_count,
            "missing_percent": round(100.0 * missing_count / rows, 3),
            "unique_nonmissing": int(series.nunique(dropna=True)),
            "outlier_count_iqr": None,
        }
        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            if len(numeric) >= 4:
                q1, q3 = numeric.quantile([0.25, 0.75])
                iqr = float(q3 - q1)
                if math.isfinite(iqr):
                    low, high = float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)
                    item["outlier_count_iqr"] = int(((numeric < low) | (numeric > high)).sum())
            item["mean"] = float(numeric.mean()) if len(numeric) else None
            item["minimum"] = float(numeric.min()) if len(numeric) else None
            item["maximum"] = float(numeric.max()) if len(numeric) else None
        column_rows.append(item)
    return {
        "status": "PROFILED",
        "data_status": "IMPORTED",
        "rows": rows,
        "columns": len(source.columns),
        "duplicate_rows": int(source.duplicated().sum()),
        "missing_cells": int(source.isna().sum().sum()),
        "missing_percent": round(100.0 * int(source.isna().sum().sum()) / (rows * len(source.columns)), 3),
        "column_profile": column_rows,
        "source_preserved": True,
        "method": "Missingness/type/unique profile; numeric IQR fences use Q1 − 1.5×IQR and Q3 + 1.5×IQR.",
        "warnings": ["IQR outliers are review candidates, not automatic deletions or proof of erroneous data."],
    }


_UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "m": ("length", 1.0), "km": ("length", 1000.0), "cm": ("length", 0.01),
    "mm": ("length", 0.001), "ft": ("length", 0.3048), "in": ("length", 0.0254),
    "kg": ("mass", 1.0), "g": ("mass", 0.001), "lb": ("mass", 0.45359237),
    "tonne": ("mass", 1000.0),
    "s": ("time", 1.0), "min": ("time", 60.0), "h": ("time", 3600.0),
    "day": ("time", 86400.0),
    "J": ("energy", 1.0), "kJ": ("energy", 1000.0), "MJ": ("energy", 1_000_000.0),
    "kWh": ("energy", 3_600_000.0), "MWh": ("energy", 3_600_000_000.0),
}
_CURRENCY_CODES = {"SAR", "USD", "EUR", "GBP", "AED"}


def convert_quantity(
    value: Any,
    source_unit: str,
    target_unit: str,
    *,
    exchange_rate: Any = None,
    rate_date: str = "",
    rate_source: str = "",
) -> dict[str, Any]:
    """Convert supported like-dimension units; FX rate means target units per source unit."""
    amount = _finite_number(value, "Value")
    source = str(source_unit or "").strip()
    target = str(target_unit or "").strip()
    if source in _CURRENCY_CODES or target in _CURRENCY_CODES:
        if source not in _CURRENCY_CODES or target not in _CURRENCY_CODES:
            raise ValueError("Currency cannot be converted to a physical unit.")
        if source == target:
            return {
                "status": "CALCULATED", "value": amount, "unit": target,
                "method": "Identity currency conversion; no exchange rate needed.",
                "rate_date": None, "rate_source": None,
                "warnings": ["No live exchange rate was fetched."],
            }
        rate = _finite_number(exchange_rate, "Exchange rate")
        if rate <= 0:
            raise ValueError("Exchange rate must be greater than zero.")
        if not str(rate_date or "").strip() or not str(rate_source or "").strip():
            raise ValueError("Provide the exchange-rate date and source for currency conversions.")
        converted = amount * rate
        return {
            "status": "CALCULATED", "value": converted, "unit": target,
            "method": f"{amount:g} {source} × {rate:g} {target}/{source}.",
            "rate_date": str(rate_date).strip(), "rate_source": str(rate_source).strip(),
            "warnings": ["Exchange rate is user-supplied; this tool does not fetch or verify a current rate."],
        }
    if source not in _UNIT_FACTORS or target not in _UNIT_FACTORS:
        raise ValueError("Choose supported physical units from the available unit list.")
    source_dimension, source_factor = _UNIT_FACTORS[source]
    target_dimension, target_factor = _UNIT_FACTORS[target]
    if source_dimension != target_dimension:
        raise ValueError(f"Incompatible dimensions: {source_dimension} cannot convert to {target_dimension}.")
    converted = amount * source_factor / target_factor
    return {
        "status": "CALCULATED", "value": converted, "unit": target,
        "method": f"Base-unit conversion: value × {source_factor:g} / {target_factor:g}.",
        "rate_date": None, "rate_source": None, "warnings": [],
    }


def generate_synthetic_industrial_data(rows: int = 500, seed: int = 42, start: str = "2026-01-01") -> pd.DataFrame:
    """Generate reproducible labelled sample data only; values never claim to be live telemetry."""
    if isinstance(rows, bool) or not isinstance(rows, (int, np.integer)) or rows < 1 or rows > 10_000:
        raise ValueError("Rows must be an integer from 1 to 10,000.")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0 or seed > 2**32 - 1:
        raise ValueError("Seed must be an integer from 0 to 4,294,967,295.")
    try:
        start_time = pd.Timestamp(start)
    except Exception as exc:
        raise ValueError("Start time must be a valid date/time.") from exc
    if pd.isna(start_time):
        raise ValueError("Start time must be a valid date/time.")
    rng = np.random.default_rng(int(seed))
    demand = rng.poisson(80, int(rows)).astype(int)
    downtime = np.round(rng.exponential(2.5, int(rows)), 2)
    runtime_fraction = np.clip(1.0 - downtime / 60.0, 0.0, 1.0)
    output = np.maximum(0, np.rint(demand * runtime_fraction)).astype(int)
    defects = rng.binomial(output, 0.02).astype(int)
    energy = np.round(output * 0.55 + rng.normal(0, 2.0, int(rows)), 2)
    energy = np.maximum(0, energy)
    return pd.DataFrame({
        "timestamp": pd.date_range(start=start_time, periods=int(rows), freq="h"),
        "demand_units": demand,
        "actual_output_units": output,
        "downtime_minutes": downtime,
        "defect_units": defects,
        "energy_kwh": energy,
        "data_status": "SYNTHETIC",
        "seed": int(seed),
    })


def _parse_observations(observed_times: Any) -> list[float]:
    if isinstance(observed_times, str):
        raw_values = [item.strip() for item in observed_times.replace("\n", ",").split(",") if item.strip()]
    elif isinstance(observed_times, Sequence):
        raw_values = list(observed_times)
    else:
        raise ValueError("Observed times must be a comma-separated list or a sequence of numbers.")
    if not raw_values:
        raise ValueError("Enter at least one observed time.")
    values = [_finite_number(value, f"Observation {i + 1}") for i, value in enumerate(raw_values)]
    if any(value <= 0 for value in values):
        raise ValueError("Observed times must be greater than zero.")
    if len(values) > 100_000:
        raise ValueError("At most 100,000 observations are supported.")
    return values




def _parse_measurements(raw_values: Any) -> list[float]:
    """Parse measurement values without imposing a positive-only restriction."""
    if isinstance(raw_values, str):
        parts = [item.strip() for item in raw_values.replace("\n", ",").split(",") if item.strip()]
    elif isinstance(raw_values, Sequence):
        parts = list(raw_values)
    else:
        raise ValueError("Measurements must be a comma-separated list or a sequence of numbers.")
    if not parts:
        raise ValueError("Enter at least one measurement.")
    if len(parts) > 100_000:
        raise ValueError("At most 100,000 measurements are supported.")
    return [_finite_number(value, f"Measurement {i + 1}") for i, value in enumerate(parts)]

def time_study_standard_time(
    observed_times: Any,
    performance_rating_pct: Any = 100.0,
    allowance_pct: Any = 0.0,
) -> dict[str, Any]:
    values = _parse_observations(observed_times)
    rating = _finite_number(performance_rating_pct, "Performance rating")
    allowance = _finite_number(allowance_pct, "Allowance")
    if rating <= 0 or rating > 200:
        raise ValueError("Performance rating must be greater than 0% and at most 200%.")
    if allowance < 0 or allowance > 100:
        raise ValueError("Allowance must be between 0% and 100%.")
    mean_time = float(np.mean(values))
    normal_time = mean_time * rating / 100.0
    standard_time = normal_time * (1.0 + allowance / 100.0)
    return {
        "status": "CALCULATED", "tool_id": "T021", "method": "Normal time = mean observed time × performance rating; standard time = normal time × (1 + allowance).",
        "metrics": {
            "observations": len(values), "mean_observed_time": mean_time,
            "sample_standard_deviation": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            "performance_rating_pct": rating, "normal_time": normal_time,
            "allowance_pct_of_normal_time": allowance, "standard_time": standard_time,
        },
        "assumptions": ["All observations use one consistent time unit.", "Allowance is expressed as a percentage of normal time; other allowance conventions produce different results."],
        "warnings": ["A single observation has no estimable sample variation." ] if len(values) == 1 else [],
        "data_status": "USER_INPUT",
    }


def work_sampling_interval(activity_count: Any, total_observations: Any, confidence_pct: Any = 95.0) -> dict[str, Any]:
    if isinstance(activity_count, bool) or isinstance(total_observations, bool):
        raise ValueError("Counts must be integers.")
    try:
        active = int(activity_count)
        total = int(total_observations)
    except (TypeError, ValueError) as exc:
        raise ValueError("Counts must be integers.") from exc
    if active != activity_count or total != total_observations:
        raise ValueError("Counts must be whole numbers.")
    if total <= 0 or active < 0 or active > total:
        raise ValueError("Require total observations > 0 and 0 ≤ activity count ≤ total observations.")
    confidence = _finite_number(confidence_pct, "Confidence level")
    z_by_confidence = {90.0: 1.6448536269514722, 95.0: 1.959963984540054, 99.0: 2.5758293035489004}
    if confidence not in z_by_confidence:
        raise ValueError("Confidence must be 90%, 95%, or 99%.")
    z = z_by_confidence[confidence]
    p = active / total
    denom = 1.0 + (z * z) / total
    center = (p + (z * z) / (2.0 * total)) / denom
    half = z * math.sqrt((p * (1.0 - p) / total) + ((z * z) / (4.0 * total * total))) / denom
    lower, upper = max(0.0, center - half), min(1.0, center + half)
    return {
        "status": "CALCULATED", "tool_id": "T022", "method": "Wilson score confidence interval for a binomial activity proportion.",
        "metrics": {
            "activity_count": active, "total_observations": total, "estimated_proportion": p,
            "estimated_percent": 100.0 * p, "confidence_pct": confidence,
            "lower_bound_percent": lower * 100.0, "upper_bound_percent": upper * 100.0,
            "interval_width_percentage_points": 200.0 * half,
        },
        "assumptions": ["Observations are representative and independent.", "The Wilson interval estimates a proportion; it does not correct for biased sampling."],
        "warnings": ["Sample size is below 30; consider a larger sample and a pre-defined precision target."] if total < 30 else [],
        "data_status": "USER_INPUT",
    }


def takt_time_capacity(
    available_time: Any,
    demand_units: Any,
    cycle_time: Any,
) -> dict[str, Any]:
    available = _finite_number(available_time, "Available production time")
    demand = _finite_number(demand_units, "Demand")
    cycle = _finite_number(cycle_time, "Cycle time")
    if available <= 0 or demand <= 0 or cycle <= 0:
        raise ValueError("Available time, demand, and cycle time must all be greater than zero.")
    takt = available / demand
    capacity = available / cycle
    utilization = 100.0 * demand * cycle / available
    return {
        "status": "CALCULATED", "tool_id": "T023", "method": "Takt = available production time / demand; theoretical capacity = available production time / cycle time.",
        "metrics": {
            "available_time_per_period": available, "demand_units_per_period": demand,
            "cycle_time_per_unit": cycle, "takt_time_per_unit": takt,
            "theoretical_capacity_units_per_period": capacity, "implied_utilization_pct": utilization,
            "capacity_shortfall_units_per_period": max(0.0, demand - capacity),
        },
        "assumptions": ["Available time and cycle time use the same unit; demand is units per the same period."],
        "warnings": ["Implied utilization exceeds 100%; the stated cycle time cannot meet demand within the available time."] if utilization > 100.0 else [],
        "data_status": "USER_INPUT",
    }




def oee_analysis(planned_production_time: Any, downtime: Any, ideal_cycle_time: Any, total_count: Any, good_count: Any) -> dict[str, Any]:
    planned = _finite_number(planned_production_time, "Planned production time")
    down = _finite_number(downtime, "Downtime")
    ideal_cycle = _finite_number(ideal_cycle_time, "Ideal cycle time")
    total = _finite_number(total_count, "Total output")
    good = _finite_number(good_count, "Good output")
    if planned <= 0:
        raise ValueError("Planned production time must be greater than zero.")
    if down < 0 or down > planned:
        raise ValueError("Downtime must be between zero and planned production time.")
    if ideal_cycle <= 0:
        raise ValueError("Ideal cycle time must be greater than zero.")
    if not total.is_integer() or not good.is_integer():
        raise ValueError("Total and good output counts must be whole numbers.")
    if total <= 0 or good < 0 or good > total:
        raise ValueError("Require total output > 0 and 0 ≤ good output ≤ total output.")
    operating = planned - down
    if operating <= 0:
        raise ValueError("Operating time is zero; OEE cannot be calculated.")
    availability, performance, quality = operating / planned, ideal_cycle * total / operating, good / total
    warnings = []
    if performance > 1.0:
        warnings.append("Performance exceeds 100%; check ideal cycle time, units, and output counting.")
    return {
        "status": "CALCULATED", "tool_id": "T026",
        "method": "Availability = operating time / planned time; performance = ideal cycle time × total output / operating time; quality = good output / total output; OEE = availability × performance × quality.",
        "metrics": {
            "planned_production_time": planned, "downtime": down, "operating_time": operating,
            "availability_pct": 100.0 * availability, "performance_pct": 100.0 * performance,
            "quality_pct": 100.0 * quality, "oee_pct": 100.0 * availability * performance * quality,
            "total_output": total, "good_output": good, "defective_output": total - good,
        },
        "assumptions": ["Time inputs and ideal cycle time must use compatible units (for example, minutes and minutes per unit)."],
        "warnings": warnings + ["Loss-category Pareto and six-big-loss reconciliation are not included in this base OEE calculation."],
        "data_status": "USER_INPUT",
    }


def process_capability(measurements: Any, lower_spec_limit: Any, upper_spec_limit: Any, within_subgroup_sigma: Any = None) -> dict[str, Any]:
    values = _parse_measurements(measurements)
    lsl, usl = _finite_number(lower_spec_limit, "Lower specification limit"), _finite_number(upper_spec_limit, "Upper specification limit")
    if lsl >= usl:
        raise ValueError("Lower specification limit must be below upper specification limit.")
    overall_sigma = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    if not math.isfinite(overall_sigma) or overall_sigma <= 0:
        raise ValueError("At least two measurements with non-zero variation are required.")
    mean = float(np.mean(values))
    pp = (usl - lsl) / (6.0 * overall_sigma)
    ppk = min((usl - mean) / (3.0 * overall_sigma), (mean - lsl) / (3.0 * overall_sigma))
    cp = cpk = None
    warnings = ["Capability indices do not prove process stability or normality. Confirm control-chart stability, subgroup design, and distribution assumptions before acceptance decisions."]
    if within_subgroup_sigma not in (None, ""):
        within_sigma = _finite_number(within_subgroup_sigma, "Within-subgroup sigma")
        if within_sigma <= 0:
            raise ValueError("Within-subgroup sigma must be greater than zero.")
        cp = (usl - lsl) / (6.0 * within_sigma)
        cpk = min((usl - mean) / (3.0 * within_sigma), (mean - lsl) / (3.0 * within_sigma))
    else:
        warnings.append("Cp/Cpk are omitted without a supplied within-subgroup standard deviation; Pp/Ppk use overall sample standard deviation.")
    return {
        "status": "CALCULATED", "tool_id": "T032",
        "method": "Pp = (USL−LSL)/(6s_overall); Ppk = min((USL−mean)/(3s_overall),(mean−LSL)/(3s_overall)); Cp/Cpk use supplied within-subgroup sigma.",
        "metrics": {"sample_count": len(values), "mean": mean, "overall_sample_sigma": overall_sigma, "lower_spec_limit": lsl, "upper_spec_limit": usl, "Cp": cp, "Cpk": cpk, "Pp": pp, "Ppk": ppk},
        "assumptions": ["Measurements and specification limits use the same unit.", "Within-subgroup sigma must come from an appropriate subgroup design, not an assumed constant."],
        "warnings": warnings,
        "data_status": "USER_INPUT",
    }


def mtbf_mttr_analysis(operating_hours: Any, failure_count: Any, repair_hours: Any) -> dict[str, Any]:
    operating = _finite_number(operating_hours, "Operating hours")
    if isinstance(failure_count, bool):
        raise ValueError("Failure count must be a whole number.")
    try:
        count = int(failure_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("Failure count must be a whole number.") from exc
    if count <= 0 or count != failure_count:
        raise ValueError("Failure count must be a positive whole number.")
    if operating <= 0:
        raise ValueError("Operating hours must be greater than zero.")
    repairs = _parse_observations(repair_hours)
    if len(repairs) != count:
        raise ValueError(f"Provide one positive repair-duration value for each of the {count} failures.")
    mtbf, mttr = operating / count, float(np.mean(repairs))
    return {
        "status": "CALCULATED", "tool_id": "T042",
        "method": "MTBF = operating hours / observed failure count; MTTR = mean supplied repair duration; inherent availability = MTBF/(MTBF+MTTR).",
        "metrics": {"operating_hours": operating, "failure_count": count, "MTBF_hours": mtbf, "MTTR_hours": mttr, "inherent_availability_pct": 100.0 * mtbf / (mtbf + mttr), "repair_observation_count": len(repairs)},
        "assumptions": ["Repair durations use hours, and operating hours/failure counts describe the same asset population and observation window."],
        "warnings": ["Censoring, mixed asset populations, preventive maintenance downtime and confidence intervals are not modeled."],
        "data_status": "USER_INPUT",
    }


def inventory_policy(annual_demand: Any, order_cost: Any, annual_holding_cost_per_unit: Any, daily_demand_mean: Any, daily_demand_sigma: Any, lead_time_days: Any, service_factor_z: Any) -> dict[str, Any]:
    demand = _finite_number(annual_demand, "Annual demand")
    order = _finite_number(order_cost, "Order cost")
    holding = _finite_number(annual_holding_cost_per_unit, "Annual holding cost per unit")
    daily_mean = _finite_number(daily_demand_mean, "Mean daily demand")
    daily_sigma = _finite_number(daily_demand_sigma, "Daily demand standard deviation")
    lead = _finite_number(lead_time_days, "Lead time")
    z = _finite_number(service_factor_z, "Service factor z")
    if demand <= 0 or order <= 0 or holding <= 0:
        raise ValueError("Annual demand, order cost, and annual holding cost per unit must all be positive.")
    if daily_mean < 0 or daily_sigma < 0 or lead < 0 or z < 0:
        raise ValueError("Daily demand, demand standard deviation, lead time, and service factor cannot be negative.")
    eoq = math.sqrt((2.0 * demand * order) / holding)
    mean_lead_demand = daily_mean * lead
    sigma_lead_demand = daily_sigma * math.sqrt(lead)
    safety_stock = z * sigma_lead_demand
    return {
        "status": "CALCULATED", "tool_id": "T055",
        "method": "EOQ = sqrt(2DS/H); safety stock = z × σ_daily × sqrt(lead time); reorder point = mean daily demand × lead time + safety stock.",
        "metrics": {"EOQ_units": eoq, "orders_per_year_at_EOQ": demand / eoq, "mean_lead_time_demand_units": mean_lead_demand, "safety_stock_units": safety_stock, "reorder_point_units": mean_lead_demand + safety_stock, "service_factor_z": z, "lead_time_days": lead},
        "assumptions": ["Daily demand observations are independent with finite variance; lead time is deterministic in days; z is a one-sided normal service factor."],
        "warnings": ["Check lot-size constraints, discrete units, seasonal demand, variable lead time, and empirical demand distribution before deployment."],
        "data_status": "USER_INPUT",
    }


def carbon_emissions(activity_quantity: Any, emission_factor: Any, quantity_unit: str, emission_unit: str, factor_source: str, factor_date: str) -> dict[str, Any]:
    activity = _finite_number(activity_quantity, "Activity quantity")
    factor = _finite_number(emission_factor, "Emission factor")
    if activity < 0 or factor < 0:
        raise ValueError("Activity quantity and emission factor cannot be negative.")
    if not str(quantity_unit or "").strip() or not str(emission_unit or "").strip():
        raise ValueError("Provide the activity unit and resulting emission unit.")
    if not str(factor_source or "").strip() or not str(factor_date or "").strip():
        raise ValueError("Provide the emission-factor source and date.")
    return {
        "status": "CALCULATED", "tool_id": "T078", "data_status": "USER_INPUT",
        "method": "Emissions = activity quantity × emission factor.",
        "metrics": {"activity_quantity": activity, "emission_factor": factor, "total_emissions": activity * factor, "activity_unit": str(quantity_unit).strip(), "emission_unit": str(emission_unit).strip()},
        "assumptions": ["The factor unit must match the stated activity unit and resulting emission unit; scope/boundary depend on the factor provider."],
        "warnings": ["Factor source/date are recorded as supplied and are not independently verified; this is not an audited greenhouse-gas disclosure."],
        "factor_source": str(factor_source).strip(), "factor_date": str(factor_date).strip(),
    }


def engineering_economics(cash_flows: Any, discount_rate_pct: Any) -> dict[str, Any]:
    if isinstance(cash_flows, str):
        raw_values = [item.strip() for item in cash_flows.replace("\n", ",").split(",") if item.strip()]
    elif isinstance(cash_flows, Sequence):
        raw_values = list(cash_flows)
    else:
        raise ValueError("Cash flows must be a comma-separated list ordered by period.")
    if len(raw_values) < 2:
        raise ValueError("Enter at least a period-0 cash flow and one future period.")
    if len(raw_values) > 60:
        raise ValueError("At most 60 equally spaced cash-flow periods are supported.")
    flows = [_finite_number(value, f"Cash flow for period {i}") for i, value in enumerate(raw_values)]
    if any(abs(value) > 1e15 for value in flows):
        raise ValueError("Cash flows exceed the supported numerical magnitude of 1e15.")
    rate = _finite_number(discount_rate_pct, "Discount rate")
    if rate <= -100 or rate > 1000:
        raise ValueError("Discount rate must be greater than -100% and no more than 1,000%.")
    discount = rate / 100.0
    def npv_at(discount_rate: float) -> float:
        return sum(flow / ((1.0 + discount_rate) ** period) for period, flow in enumerate(flows))
    npv = npv_at(discount)
    cumulative, cumulative_discounted = flows[0], flows[0]
    simple_payback = discounted_payback = None
    for period in range(1, len(flows)):
        prior, prior_discounted = cumulative, cumulative_discounted
        cumulative += flows[period]
        discounted_flow = flows[period] / ((1.0 + discount) ** period)
        cumulative_discounted += discounted_flow
        if simple_payback is None and prior < 0 <= cumulative:
            simple_payback = (period - 1) + (-prior / flows[period]) if flows[period] > 0 else float(period)
        if discounted_payback is None and prior_discounted < 0 <= cumulative_discounted:
            discounted_payback = (period - 1) + (-prior_discounted / discounted_flow) if discounted_flow > 0 else float(period)

    warnings = []
    irr_pct = None
    conventional_flow = flows[0] < 0 and any(value > 0 for value in flows[1:]) and all(value >= 0 for value in flows[1:])
    if conventional_flow:
        if abs(npv_at(0.0)) < 1e-12:
            irr_pct = 0.0
        else:
            low_rate, high_rate = -0.99, 1000.0
            low_npv, high_npv = npv_at(low_rate), npv_at(high_rate)
            if math.isfinite(low_npv) and math.isfinite(high_npv) and low_npv * high_npv < 0:
                try:
                    irr_pct = 100.0 * brentq(npv_at, low_rate, high_rate, maxiter=500)
                except (ValueError, RuntimeError, OverflowError):
                    warnings.append("IRR root search did not converge; inspect the cash-flow values and use an independently verified financial model.")
            else:
                warnings.append("A unique IRR could not be bracketed in the supported rate domain (-99%, 100,000%).")
    else:
        warnings.append("IRR is omitted because the series is not a conventional initial-outflow-then-nonnegative-inflows pattern; non-conventional cash flows can have multiple IRRs.")
    if simple_payback is None:
        warnings.append("The cash-flow series does not recover its initial cumulative investment during the supplied periods.")
    return {
        "status": "CALCULATED", "tool_id": "T081",
        "method": "NPV = sum(CF_t/(1+r)^t), including period-0 cash flow. For a conventional initial-outflow then nonnegative-inflow series, IRR is the bracketed rate in (-99%, 100,000%) with NPV equal to zero. Payback is linearly interpolated in the first period where cumulative cash flow becomes non-negative.",
        "metrics": {"period_count_including_period_zero": len(flows), "discount_rate_pct": rate, "NPV": npv, "IRR_pct": irr_pct, "simple_payback_periods": simple_payback, "discounted_payback_periods": discounted_payback},
        "assumptions": ["Cash flows are equally spaced periods in one currency; period 0 occurs now; the discount rate is per period.", "IRR is reported only for conventional cash-flow patterns with one bracketed root."],
        "warnings": warnings,
        "cash_flows": flows,
        "data_status": "USER_INPUT",
    }

def run_tool_calculation(tier: str, tool_id: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Execute only the small, tested deterministic engine set; fail closed otherwise."""
    canonical_id = str(tool_id or "").strip().upper()
    if not tool_access_allowed(tier, canonical_id):
        raise ToolEntitlementError("This tool is not included in the active package, or the package is not recognized.")
    spec = TOOL_BY_ID.get(canonical_id)
    if spec is None:
        raise ToolNotImplementedError("Unknown tool ID; no execution was performed.")
    args = dict(inputs or {})
    if canonical_id == "T011":
        result = import_dataset_preview(args.get("filename"), args.get("payload"), args.get("sheet_name"))
    elif canonical_id == "T013":
        result = profile_dataframe(args.get("dataframe"))
    elif canonical_id == "T014":
        result = reversible_clean_candidate(
            args.get("dataframe"), drop_duplicates=bool(args.get("drop_duplicates", True)),
            missing_strategy=str(args.get("missing_strategy", "keep")),
        )
    elif canonical_id == "T016":
        result = convert_quantity(
            args.get("value"), args.get("source_unit", ""), args.get("target_unit", ""),
            exchange_rate=args.get("exchange_rate"), rate_date=str(args.get("rate_date") or ""),
            rate_source=str(args.get("rate_source") or ""),
        )
    elif canonical_id == "T019":
        result = {"status": "GENERATED", "data_status": "SYNTHETIC", "dataframe": generate_synthetic_industrial_data(
            args.get("rows", 500), args.get("seed", 42), args.get("start", "2026-01-01")
        ), "method": "Seeded NumPy Generator; generated rows are synthetic and are not live observations.", "warnings": ["Do not merge these rows into a live dataset without explicit review."]}
    elif canonical_id == "T021":
        result = time_study_standard_time(args.get("observed_times", ""), args.get("performance_rating_pct", 100.0), args.get("allowance_pct", 0.0))
    elif canonical_id == "T022":
        result = work_sampling_interval(args.get("activity_count"), args.get("total_observations"), args.get("confidence_pct", 95.0))
    elif canonical_id == "T023":
        result = takt_time_capacity(args.get("available_time"), args.get("demand_units"), args.get("cycle_time"))
    elif canonical_id == "T026":
        result = oee_analysis(args.get("planned_production_time"), args.get("downtime"), args.get("ideal_cycle_time"), args.get("total_count"), args.get("good_count"))
    elif canonical_id == "T032":
        result = process_capability(args.get("measurements", ""), args.get("lower_spec_limit"), args.get("upper_spec_limit"), args.get("within_subgroup_sigma"))
    elif canonical_id == "T042":
        result = mtbf_mttr_analysis(args.get("operating_hours"), args.get("failure_count"), args.get("repair_hours", ""))
    elif canonical_id == "T055":
        result = inventory_policy(args.get("annual_demand"), args.get("order_cost"), args.get("annual_holding_cost_per_unit"), args.get("daily_demand_mean"), args.get("daily_demand_sigma"), args.get("lead_time_days"), args.get("service_factor_z"))
    elif canonical_id == "T078":
        result = carbon_emissions(args.get("activity_quantity"), args.get("emission_factor"), str(args.get("quantity_unit") or ""), str(args.get("emission_unit") or ""), str(args.get("factor_source") or ""), str(args.get("factor_date") or ""))
    elif canonical_id == "T081":
        result = engineering_economics(args.get("cash_flows", ""), args.get("discount_rate_pct"))
    else:
        raise ToolNotImplementedError(
            f"{canonical_id} ({spec['canonical_name']}) has no standalone deterministic engine in this workbench yet. "
            "No substitute calculation was run; open the related module if available or treat this target as incomplete."
        )
    result["tool_id"] = canonical_id
    result["canonical_name"] = spec["canonical_name"]
    result["required_tier"] = spec["minimum_tier"]
    result.setdefault("generated_at_utc", datetime.now(timezone.utc).isoformat())
    result.setdefault("data_status", "IMPORTED" if canonical_id == "T013" else "USER_INPUT")
    result.setdefault("warnings", [])
    return result


def _show_result(st: Any, result: Mapping[str, Any]) -> None:
    st.caption(f"Status: {result.get('status', 'UNKNOWN')} · Data: {result.get('data_status', 'USER_INPUT')} · Method: {result.get('method', 'See method notes')}")
    metrics = result.get("metrics")
    if isinstance(metrics, Mapping):
        items = list(metrics.items())
        for offset in range(0, len(items), 3):
            cols = st.columns(min(3, len(items) - offset))
            for col, (key, value) in zip(cols, items[offset:offset + 3]):
                if isinstance(value, (int, float, np.integer, np.floating)) and math.isfinite(float(value)):
                    shown = f"{float(value):,.4g}"
                else:
                    shown = str(value)
                col.metric(str(key).replace("_", " ").title(), shown)
    profile = result.get("column_profile")
    if isinstance(profile, list):
        st.dataframe(pd.DataFrame(profile), use_container_width=True, hide_index=True)
        if profile:
            chart_data = pd.DataFrame(profile).set_index("column")[["missing_percent"]]
            st.bar_chart(chart_data, y="missing_percent")
    synthetic = result.get("dataframe")
    if isinstance(synthetic, pd.DataFrame):
        st.dataframe(synthetic.head(30), use_container_width=True, hide_index=True)
        st.line_chart(synthetic.set_index("timestamp")[["demand_units", "actual_output_units"]])
    if result.get("assumptions"):
        st.markdown("**Assumptions**")
        for assumption in result["assumptions"]:
            st.write(f"• {assumption}")
    for warning in result.get("warnings", []):
        st.warning(str(warning))


def _render_quick_tools(st: Any, tier: str) -> None:
    tabs = st.tabs([
        "T013 · Data Profile", "T016 · Unit / Currency", "T019 · Synthetic Data",
        "T021 · Time Study", "T022 · Work Sampling", "T023 · Takt / Capacity",
        "More methods",
    ])
    with tabs[0]:
        st.write("Read-only profile for a staged CSV/XLSX file. The active dataset is not replaced.")
        upload = st.file_uploader("Choose CSV or Excel workbook", type=["csv", "xlsx", "xlsm", "xls"], key="shoir100_profiler_upload")
        if upload is not None:
            if upload.size > MAX_PROFILE_BYTES:
                st.error("This profiler accepts files up to 20 MiB. Your active dataset was not changed.")
            else:
                try:
                    raw_bytes = upload.getvalue()
                    if upload.name.lower().endswith(".csv"):
                        frame = pd.read_csv(io.BytesIO(raw_bytes))
                    else:
                        xls = pd.ExcelFile(io.BytesIO(raw_bytes))
                        sheet = st.selectbox("Source sheet", xls.sheet_names, key="shoir100_profiler_sheet")
                        frame = pd.read_excel(xls, sheet_name=sheet)
                    st.caption(f"Staged: {upload.name} · {len(frame):,} rows × {len(frame.columns):,} columns. Source is preserved.")
                    st.dataframe(frame.head(10), use_container_width=True, hide_index=True)
                    if st.button("Profile staged data", key="shoir100_profile_button", type="primary"):
                        result = run_tool_calculation(tier, "T013", {"dataframe": frame})
                        st.session_state["shoir100_last_profile"] = result
                except ToolEntitlementError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Could not read/profile this file. The previous valid result is preserved. Details: {type(exc).__name__}: {exc}")
        prior = st.session_state.get("shoir100_last_profile")
        if isinstance(prior, Mapping) and prior.get("tool_id") == "T013":
            _show_result(st, prior)

    with tabs[1]:
        mode = st.radio("Conversion type", ["Physical unit", "Currency with supplied rate"], horizontal=True, key="shoir100_convert_mode")
        value = st.number_input("Value to convert", value=100.0, key="shoir100_convert_value")
        units = sorted(_UNIT_FACTORS.keys())
        if mode == "Physical unit":
            c1, c2 = st.columns(2)
            source_unit = c1.selectbox("From unit", units, index=units.index("m"), key="shoir100_from_unit")
            target_unit = c2.selectbox("To unit", units, index=units.index("cm"), key="shoir100_to_unit")
            rate = None
            rate_date = ""
            rate_source = ""
        else:
            codes = sorted(_CURRENCY_CODES)
            c1, c2 = st.columns(2)
            source_unit = c1.selectbox("From currency", codes, index=codes.index("SAR"), key="shoir100_from_ccy")
            target_unit = c2.selectbox("To currency", codes, index=codes.index("USD"), key="shoir100_to_ccy")
            rate = st.number_input("Rate (target units per 1 source unit)", min_value=0.0000001, value=0.27, format="%.7f", key="shoir100_fx_rate")
            rate_date = st.text_input("Rate date (YYYY-MM-DD)", key="shoir100_fx_date")
            rate_source = st.text_input("Rate source / reference", key="shoir100_fx_source")
        if st.button("Convert", key="shoir100_convert_button", type="primary"):
            try:
                result = run_tool_calculation(tier, "T016", {
                    "value": value, "source_unit": source_unit, "target_unit": target_unit,
                    "exchange_rate": rate, "rate_date": rate_date, "rate_source": rate_source,
                })
                st.session_state["shoir100_last_convert"] = result
            except Exception as exc:
                st.error(f"Conversion not completed: {exc}")
        prior = st.session_state.get("shoir100_last_convert")
        if isinstance(prior, Mapping) and prior.get("tool_id") == "T016":
            _show_result(st, prior)

    with tabs[2]:
        st.info("Generated rows are marked SYNTHETIC. They are for practice/testing, never live plant observations.")
        n = st.number_input("Rows to generate", min_value=1, max_value=10_000, value=500, step=100, key="shoir100_synth_n")
        seed = st.number_input("Random seed", min_value=0, max_value=4_294_967_295, value=42, step=1, key="shoir100_synth_seed")
        start = st.text_input("Start timestamp", value="2026-01-01", key="shoir100_synth_start")
        if st.button("Generate synthetic dataset", key="shoir100_synth_button", type="primary"):
            try:
                result = run_tool_calculation(tier, "T019", {"rows": int(n), "seed": int(seed), "start": start})
                st.session_state["shoir100_last_synth"] = result
            except Exception as exc:
                st.error(f"Synthetic generation failed: {exc}")
        prior = st.session_state.get("shoir100_last_synth")
        if isinstance(prior, Mapping) and prior.get("tool_id") == "T019":
            _show_result(st, prior)

    with tabs[3]:
        observations = st.text_area("Observed times, comma-separated", value="10, 11.2, 9.8, 10.5, 10.1", key="shoir100_time_observations")
        unit = st.selectbox("Time unit", ["seconds", "minutes", "hours"], key="shoir100_time_unit")
        c1, c2 = st.columns(2)
        rating = c1.number_input("Performance rating (%)", min_value=1.0, max_value=200.0, value=100.0, step=5.0, key="shoir100_time_rating")
        allowance = c2.number_input("Allowance (% of normal time)", min_value=0.0, max_value=100.0, value=15.0, step=1.0, key="shoir100_time_allowance")
        if st.button("Calculate standard time", key="shoir100_time_button", type="primary"):
            try:
                result = run_tool_calculation(tier, "T021", {"observed_times": observations, "performance_rating_pct": rating, "allowance_pct": allowance})
                result["metrics"]["time_unit"] = unit
                for key in ("mean_observed_time", "sample_standard_deviation", "normal_time", "standard_time"):
                    result["metrics"][key] = result["metrics"][key]
                st.session_state["shoir100_last_time"] = result
            except Exception as exc:
                st.error(f"Time study not completed: {exc}")
        prior = st.session_state.get("shoir100_last_time")
        if isinstance(prior, Mapping) and prior.get("tool_id") == "T021":
            st.caption(f"All times are in {prior.get('metrics', {}).get('time_unit', unit)}.")
            _show_result(st, prior)

    with tabs[4]:
        c1, c2, c3 = st.columns(3)
        activity = c1.number_input("Observations showing activity", min_value=0, value=42, step=1, key="shoir100_sample_activity")
        total = c2.number_input("Total observations", min_value=1, value=100, step=1, key="shoir100_sample_total")
        confidence = c3.selectbox("Confidence", [90.0, 95.0, 99.0], index=1, key="shoir100_sample_confidence")
        if st.button("Estimate proportion and interval", key="shoir100_sample_button", type="primary"):
            try:
                result = run_tool_calculation(tier, "T022", {"activity_count": int(activity), "total_observations": int(total), "confidence_pct": confidence})
                st.session_state["shoir100_last_sample"] = result
            except Exception as exc:
                st.error(f"Work sampling not completed: {exc}")
        prior = st.session_state.get("shoir100_last_sample")
        if isinstance(prior, Mapping) and prior.get("tool_id") == "T022":
            _show_result(st, prior)

    with tabs[5]:
        c1, c2, c3 = st.columns(3)
        available = c1.number_input("Available production time per period", min_value=0.001, value=420.0, key="shoir100_takt_available")
        demand = c2.number_input("Demand (units per same period)", min_value=0.001, value=240.0, key="shoir100_takt_demand")
        cycle = c3.number_input("Observed cycle time per unit", min_value=0.001, value=1.5, key="shoir100_takt_cycle")
        time_unit = st.selectbox("Matching time unit", ["minutes", "seconds", "hours"], key="shoir100_takt_unit")
        if st.button("Calculate takt and capacity", key="shoir100_takt_button", type="primary"):
            try:
                result = run_tool_calculation(tier, "T023", {"available_time": available, "demand_units": demand, "cycle_time": cycle})
                result["metrics"]["time_unit"] = time_unit
                st.session_state["shoir100_last_takt"] = result
            except Exception as exc:
                st.error(f"Takt/capacity calculation not completed: {exc}")
        prior = st.session_state.get("shoir100_last_takt")
        if isinstance(prior, Mapping) and prior.get("tool_id") == "T023":
            st.caption(f"Both available time and cycle time are in {prior.get('metrics', {}).get('time_unit', time_unit)}.")
            _show_result(st, prior)



    with tabs[6]:
        st.caption("These methods expose formulas and limitations. Use one consistent unit system per calculation.")
        with st.expander("T026 · OEE and core losses", expanded=True):
            if not tool_access_allowed(tier, "T026"):
                st.info("🔒 This quick method requires **Mid-Tier Pro** or higher, according to the canonical tool policy.")
            else:
                a, b, d = st.columns(3)
                planned = a.number_input("Planned time", min_value=0.001, value=480.0, key="shoir100_oee_planned")
                downtime = b.number_input("Downtime", min_value=0.0, value=45.0, key="shoir100_oee_downtime")
                ideal_cycle = d.number_input("Ideal cycle time per unit", min_value=0.0001, value=0.5, key="shoir100_oee_cycle")
                a, b = st.columns(2)
                total_count = a.number_input("Total output", min_value=1.0, value=800.0, key="shoir100_oee_total")
                good_count = b.number_input("Good output", min_value=0.0, value=784.0, key="shoir100_oee_good")
                if st.button("Calculate OEE", key="shoir100_oee_button", type="primary"):
                    try:
                        st.session_state["shoir100_last_oee"] = run_tool_calculation(tier, "T026", {
                            "planned_production_time": planned, "downtime": downtime, "ideal_cycle_time": ideal_cycle,
                            "total_count": total_count, "good_count": good_count,
                        })
                    except Exception as exc:
                        st.error(f"OEE calculation not completed: {exc}")
                if isinstance(st.session_state.get("shoir100_last_oee"), Mapping):
                    _show_result(st, st.session_state["shoir100_last_oee"])

        with st.expander("T032 · Process Capability (Cp/Cpk/Pp/Ppk)"):
            if not tool_access_allowed(tier, "T032"):
                st.info("🔒 This quick method requires **Mid-Tier Pro** or higher, according to the canonical tool policy.")
            else:
                measurements = st.text_area("Measurements, comma-separated", value="9.8, 10.0, 10.1, 9.9, 10.2, 9.7", key="shoir100_cap_measurements")
                a, b, d = st.columns(3)
                lsl = a.number_input("LSL", value=9.0, key="shoir100_cap_lsl")
                usl = b.number_input("USL", value=11.0, key="shoir100_cap_usl")
                within_sigma = d.number_input("Within-subgroup sigma (optional; 0 omits Cp/Cpk)", min_value=0.0, value=0.0, key="shoir100_cap_sigma")
                if st.button("Calculate capability", key="shoir100_cap_button", type="primary"):
                    try:
                        st.session_state["shoir100_last_capability"] = run_tool_calculation(tier, "T032", {
                            "measurements": measurements, "lower_spec_limit": lsl, "upper_spec_limit": usl,
                            "within_subgroup_sigma": within_sigma if within_sigma > 0 else None,
                        })
                    except Exception as exc:
                        st.error(f"Capability not calculated: {exc}")
                if isinstance(st.session_state.get("shoir100_last_capability"), Mapping):
                    _show_result(st, st.session_state["shoir100_last_capability"])

        with st.expander("T042 · MTBF / MTTR"):
            if not tool_access_allowed(tier, "T042"):
                st.info("🔒 This quick method requires **Professional** or higher, according to the canonical tool policy.")
            else:
                a, b = st.columns(2)
                operating_hours = a.number_input("Observed operating hours", min_value=0.001, value=1000.0, key="shoir100_mtbf_operating")
                failure_count = b.number_input("Failures in that window", min_value=1, value=5, step=1, key="shoir100_mtbf_failures")
                repairs = st.text_input("Repair durations in hours, one per failure", value="2, 1.5, 3, 2.5, 1", key="shoir100_mtbf_repairs")
                if st.button("Calculate reliability metrics", key="shoir100_mtbf_button", type="primary"):
                    try:
                        st.session_state["shoir100_last_mtbf"] = run_tool_calculation(tier, "T042", {
                            "operating_hours": operating_hours, "failure_count": int(failure_count), "repair_hours": repairs,
                        })
                    except Exception as exc:
                        st.error(f"Reliability calculation not completed: {exc}")
                if isinstance(st.session_state.get("shoir100_last_mtbf"), Mapping):
                    _show_result(st, st.session_state["shoir100_last_mtbf"])

        with st.expander("T055 · EOQ, safety stock and reorder point"):
            if not tool_access_allowed(tier, "T055"):
                st.info("🔒 This quick method requires **Mid-Tier Pro** or higher, according to the canonical tool policy.")
            else:
                a, b, d = st.columns(3)
                annual_demand = a.number_input("Annual demand", min_value=0.001, value=12000.0, key="shoir100_inv_annual")
                order_cost = b.number_input("Order cost", min_value=0.001, value=50.0, key="shoir100_inv_order")
                holding = d.number_input("Annual holding cost per unit", min_value=0.001, value=2.0, key="shoir100_inv_holding")
                a, b, d = st.columns(3)
                daily_mean = a.number_input("Mean daily demand", min_value=0.0, value=40.0, key="shoir100_inv_daily_mean")
                daily_sigma = b.number_input("Daily demand standard deviation", min_value=0.0, value=5.0, key="shoir100_inv_daily_sigma")
                lead = d.number_input("Lead time (days)", min_value=0.0, value=5.0, key="shoir100_inv_lead")
                service = st.selectbox("One-sided normal service factor z", [1.282, 1.645, 1.960, 2.326], index=2, key="shoir100_inv_z")
                if st.button("Calculate inventory policy", key="shoir100_inv_button", type="primary"):
                    try:
                        st.session_state["shoir100_last_inventory"] = run_tool_calculation(tier, "T055", {
                            "annual_demand": annual_demand, "order_cost": order_cost, "annual_holding_cost_per_unit": holding,
                            "daily_demand_mean": daily_mean, "daily_demand_sigma": daily_sigma, "lead_time_days": lead,
                            "service_factor_z": service,
                        })
                    except Exception as exc:
                        st.error(f"Inventory policy not calculated: {exc}")
                if isinstance(st.session_state.get("shoir100_last_inventory"), Mapping):
                    _show_result(st, st.session_state["shoir100_last_inventory"])

        with st.expander("T078 · Carbon emissions"):
            if not tool_access_allowed(tier, "T078"):
                st.info("🔒 This quick method requires **Mid-Tier Pro** or higher, according to the canonical tool policy.")
            else:
                a, b = st.columns(2)
                activity = a.number_input("Activity quantity", min_value=0.0, value=1000.0, key="shoir100_carbon_qty")
                factor = b.number_input("Emission factor per activity unit", min_value=0.0, value=0.42, key="shoir100_carbon_factor")
                a, b = st.columns(2)
                quantity_unit = a.text_input("Activity unit (for example, kWh)", value="kWh", key="shoir100_carbon_unit")
                emission_unit = b.text_input("Emission unit (for example, kg CO2e)", value="kg CO2e", key="shoir100_carbon_emission_unit")
                factor_source = st.text_input("Factor source/reference", key="shoir100_carbon_source")
                factor_date = st.text_input("Factor date/version", key="shoir100_carbon_date")
                if st.button("Calculate emissions", key="shoir100_carbon_button", type="primary"):
                    try:
                        st.session_state["shoir100_last_carbon"] = run_tool_calculation(tier, "T078", {
                            "activity_quantity": activity, "emission_factor": factor, "quantity_unit": quantity_unit,
                            "emission_unit": emission_unit, "factor_source": factor_source, "factor_date": factor_date,
                        })
                    except Exception as exc:
                        st.error(f"Emission calculation not completed: {exc}")
                if isinstance(st.session_state.get("shoir100_last_carbon"), Mapping):
                    _show_result(st, st.session_state["shoir100_last_carbon"])

        with st.expander("T081 · NPV and payback"):
            if not tool_access_allowed(tier, "T081"):
                st.info("🔒 This quick method requires **Mid-Tier Pro** or higher, according to the canonical tool policy.")
            else:
                flows = st.text_area("Cash flows by equally spaced period, including period 0", value="-1000, 300, 350, 400, 450", key="shoir100_econ_flows")
                rate = st.number_input("Discount rate per period (%)", min_value=-99.99, max_value=1000.0, value=8.0, key="shoir100_econ_rate")
                if st.button("Calculate project economics", key="shoir100_econ_button", type="primary"):
                    try:
                        st.session_state["shoir100_last_economics"] = run_tool_calculation(tier, "T081", {
                            "cash_flows": flows, "discount_rate_pct": rate,
                        })
                    except Exception as exc:
                        st.error(f"Engineering economics not calculated: {exc}")
                if isinstance(st.session_state.get("shoir100_last_economics"), Mapping):
                    _show_result(st, st.session_state["shoir100_last_economics"])

def _render_catalog(st: Any, tier: str, allowed_modules: Sequence[str]) -> None:
    query = st.text_input("Search tool IDs, names, workbenches, or related modules", key="shoir100_catalog_search")
    workbench_options = ["All workbenches"] + list(dict.fromkeys(row["workbench"] for row in TOOL_CATALOG))
    workbench = st.selectbox("Workbench", workbench_options, key="shoir100_catalog_workbench")
    status_options = ["All readiness states"] + sorted(VALID_IMPLEMENTATION_STATUSES)
    readiness = st.selectbox("Readiness", status_options, key="shoir100_catalog_status")
    matches = visible_tools(tier, workbench=None if workbench == "All workbenches" else workbench, query=query, include_locked=True)
    if readiness != "All readiness states":
        matches = [item for item in matches if item["implementation_status"] == readiness]
    st.caption(f"{len(matches)} catalog entries match. Access uses the canonical tool ID, not a renamed display label.")
    if not matches:
        st.info("No tools match these filters. Clear a filter or try a shorter search.")
        return
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in matches:
        groups.setdefault(item["workbench"], []).append(item)
    for group_name, group_items in groups.items():
        with st.expander(f"{group_name} · {len(group_items)} tools", expanded=bool(query)):
            for item in group_items:
                accessible = bool(item["accessible"])
                locked_suffix = "" if accessible else " · 🔒 locked"
                with st.expander(f"{item['tool_id']} · {item['canonical_name']}{locked_suffix}", expanded=False):
                    st.caption(f"Minimum tier: {item['minimum_tier']} · Readiness: {item['implementation_status']}")
                    st.write(item["summary"])
                    st.markdown(f"**Inputs:** {item['input_contract']}")
                    st.markdown(f"**Expected outputs:** {item['output_contract']}")
                    st.caption(f"Evidence: {item['browser_test']} · {item['integration_test']}")
                    if not accessible:
                        st.warning(f"This tool requires **{item['minimum_tier']}**. Execution is blocked for your current package.")
                    elif item["tool_id"] in QUICK_ENGINE_IDS:
                        st.info("Executable in the **Quick tools** tab. The browser matrix still needs completion.")
                    elif item["existing_route"] and item["existing_route"] in allowed_modules and item["existing_route"] != "Core IE Tools":
                        if st.button("Open related workspace", key=f"shoir100_route_{item['tool_id']}"):
                            st.session_state["_shoir_requested_module"] = item["existing_route"]
                            st.session_state["shoir_shell_section"] = "WORKBENCH"
                            st.rerun()
                        st.caption("Related module route found. This is not proof that every target acceptance item is already implemented.")
                    elif item["existing_route"]:
                        st.caption(f"Related module: {item['existing_route']}. Its own route/tier policy remains in force.")
                    else:
                        st.warning("No standalone execution route is declared. This target is not executable from the catalog.")


def render_100_tool_workbench(st: Any, tier: str, allowed_modules: Sequence[str], username: str = "unknown") -> None:
    """Render the additive, collapsible library inside the existing Core IE Tools page."""
    with st.expander("🧰 100-Tool Engineering Library", expanded=False):
        st.caption(
            "This adds a searchable library inside the existing page; the main Shoir-IE layout and navigation stay unchanged. "
            "A readiness label is evidence status, not marketing status. No unverified target is represented as fully working."
        )
        tabs = st.tabs(["Quick tools", "100-tool catalog", "Readiness & tier rules"])
        with tabs[0]:
            _render_quick_tools(st, tier)
        with tabs[1]:
            _render_catalog(st, tier, allowed_modules)
        with tabs[2]:
            errors = validate_tool_catalog()
            if errors:
                st.error("The tool registry failed its invariant checks.")
                for error in errors:
                    st.write(error)
            counts = pd.Series([row["implementation_status"] for row in TOOL_CATALOG]).value_counts()
            metrics = st.columns(3)
            metrics[0].metric("Target tools", len(TOOL_CATALOG))
            metrics[1].metric("With standalone quick engine", len(QUICK_ENGINE_IDS))
            metrics[2].metric("Authenticated browser verified", sum(row["browser_test"] == "PASS" for row in TOOL_CATALOG))
            st.dataframe(counts.rename_axis("readiness").reset_index(name="count"), use_container_width=True, hide_index=True)
            st.markdown("**Package rules**")
            st.write("Starter → Mid-Tier Pro → Professional → Enterprise → Enterprise Plus is the ordinary tier ladder.")
            st.write("Research Pack inherits ordinary access through Enterprise plus its research tools; it does not grant Enterprise Plus.")
            st.write("Enterprise Plus does not automatically grant Research Pack-only tools.")
            st.write("Unknown tool IDs and unknown tier labels fail closed in this library.")
            st.warning(
                "The catalog crosswalk is not an authenticated end-to-end pass. T013, T016, T019, T021, T022, T023, T026, T032, T042, T055, T078, and T081 expose standalone quick engines here; "
                "other entries must use an allowed related workspace or remain incomplete. Production release gates are separate."
            )
