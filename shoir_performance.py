"""Shoir-IE performance primitives.

Centralizes the latency safeguards used by the shared visualization/parity
surfaces. The goal is to keep interactive work bounded even when users bring
very large Excel workbooks into the workspace.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Iterable

import numpy as np
import pandas as pd
import streamlit as st

# These are deliberately conservative browser/rendering budgets rather than
# data-loss limits. The source DataFrame is never modified or truncated.
DEFAULT_PLOT_POINTS = max(500, int(os.getenv("SHOIR_PLOT_MAX_POINTS", "5000")))
DEFAULT_PREVIEW_ROWS = max(100, int(os.getenv("SHOIR_PREVIEW_ROWS", "500")))
DEFAULT_GANTT_POINTS = max(250, int(os.getenv("SHOIR_GANTT_MAX_POINTS", "1000")))
DEFAULT_NETWORK_EDGES = max(250, int(os.getenv("SHOIR_NETWORK_MAX_EDGES", "1200")))
DEFAULT_WORKBOOK_CACHE_ENTRIES = max(1, int(os.getenv("SHOIR_WORKBOOK_CACHE_ENTRIES", "6")))


def as_frame(value: Any) -> pd.DataFrame:
    """Return a DataFrame without an unnecessary deep copy."""
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, list):
        if not value:
            return pd.DataFrame()
        if all(isinstance(item, dict) for item in value):
            return pd.DataFrame(value)
        return pd.DataFrame({"Value": value})
    if isinstance(value, dict):
        for key in ("result", "results", "data", "frame", "table"):
            nested = value.get(key)
            if isinstance(nested, (pd.DataFrame, list, dict)):
                frame = as_frame(nested)
                if not frame.empty:
                    return frame
        flat = {
            str(key): value
            for key, value in value.items()
            if isinstance(value, (str, int, float, bool, np.integer, np.floating))
            and not isinstance(value, bool)
        }
        return pd.DataFrame([flat]) if flat else pd.DataFrame()
    return pd.DataFrame()


def evenly_spaced_indices(length: int, limit: int) -> np.ndarray:
    length = int(length)
    limit = max(1, int(limit))
    if length <= limit:
        return np.arange(length, dtype=np.int64)
    # Always preserve the first and last observations, with deterministic
    # interior points. This avoids a biased "head only" chart.
    idx = np.linspace(0, length - 1, num=limit, dtype=np.int64)
    return np.unique(np.concatenate(([0, length - 1], idx)))


def sample_for_plot(
    df: pd.DataFrame,
    *,
    max_points: int = DEFAULT_PLOT_POINTS,
    chart: str = "",
) -> pd.DataFrame:
    """Return a deterministic plotting sample while preserving the source."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame() if not isinstance(df, pd.DataFrame) else df
    chart_name = str(chart).lower().strip()
    if "gantt" in chart_name or "timeline" in chart_name:
        max_points = min(int(max_points), DEFAULT_GANTT_POINTS)
    elif "network" in chart_name:
        max_points = min(int(max_points), DEFAULT_NETWORK_EDGES)
    elif "3d" in chart_name:
        max_points = min(int(max_points), 3000)
    elif chart_name in {"distribution", "histogram"}:
        max_points = min(int(max_points), 10000)
    max_points = max(250, int(max_points))
    if len(df) <= max_points:
        return df
    return df.iloc[evenly_spaced_indices(len(df), max_points)]


def sample_preview(df: pd.DataFrame, rows: int = DEFAULT_PREVIEW_ROWS) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or len(df) <= int(rows):
        return df
    return df.iloc[evenly_spaced_indices(len(df), int(rows))]


def limit_categories(values: Iterable[Any], max_categories: int = 500) -> list[str]:
    """Return deterministic UI filter values without rendering huge menus."""
    seq = pd.Series(list(values), dtype="string").dropna()
    if seq.empty:
        return []
    counts = seq.value_counts(dropna=False)
    return [str(v) for v in counts.head(max(1, int(max_categories))).index.tolist()]


def fast_datetime_like_columns(df: pd.DataFrame, sample_size: int = 40) -> list[str]:
    """Detect likely date columns without scanning every cell of huge objects."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    result: list[str] = []
    sample_size = max(5, int(sample_size))
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            result.append(str(column))
            continue
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            sample = series.dropna().astype(str).head(sample_size)
            if len(sample) >= 5:
                parsed = pd.to_datetime(sample, errors="coerce")
                if float(parsed.notna().mean()) >= 0.8:
                    result.append(str(column))
    return result


def lightweight_frame_signature(df: pd.DataFrame, sample_rows: int = 12) -> str:
    """Cheap, session-friendly visual signature.

    It deliberately hashes only a small deterministic edge sample. This is
    used for render caches, never as a data-integrity hash.
    """
    if not isinstance(df, pd.DataFrame):
        return "empty"
    edge = sample_preview(df, max(2, int(sample_rows)))
    try:
        hashed = pd.util.hash_pandas_object(edge, index=True).values.tobytes()
    except Exception:
        hashed = repr(edge.astype("string").to_dict(orient="list")).encode("utf-8")
    payload = repr(
        (
            tuple(str(c) for c in df.columns),
            tuple(str(dtype) for dtype in df.dtypes),
            int(len(df)),
            hashed.hex(),
        )
    ).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


@st.cache_data(show_spinner=False, max_entries=DEFAULT_WORKBOOK_CACHE_ENTRIES)
def cached_workbook_read(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    """Read an uploaded workbook once per content hash in a Streamlit session."""
    if not raw:
        raise ValueError("The uploaded file is empty.")
    from shoir_upgrade import read_uploaded_workbook

    return read_uploaded_workbook(raw, filename)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_bytes_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def quick_readiness(df: pd.DataFrame, sample_rows: int = 5000) -> dict[str, Any]:
    """Fast, explicitly sampled readiness telemetry for interactive UI surfaces."""
    if not isinstance(df, pd.DataFrame):
        return {"rows": 0, "columns": 0, "missing_cells": 0, "duplicate_rows": 0, "score": 0.0, "ready": False, "approximate": True}
    sample = sample_preview(df, sample_rows)
    rows, cols = df.shape
    missing = int(sample.isna().sum().sum()) if not sample.empty else 0
    duplicate_rows = int(sample.duplicated().sum()) if not sample.empty else 0
    cells = max(1, len(sample) * max(1, cols))
    sample_missing_pct = missing / cells * 100.0
    sample_duplicate_pct = duplicate_rows / max(1, len(sample)) * 100.0
    score = max(0.0, min(100.0, 100.0 - min(25.0, sample_missing_pct) - min(25.0, sample_duplicate_pct)))
    return {
        "rows": int(rows),
        "columns": int(cols),
        "missing_cells": missing,
        "duplicate_rows": duplicate_rows,
        "score": round(score, 1),
        "ready": bool(rows > 0 and score >= 85.0),
        "approximate": bool(len(sample) < rows),
        "sample_rows": int(len(sample)),
    }


def chart_budget(chart: str) -> int:
    name = str(chart).lower()
    if "gantt" in name or "timeline" in name:
        return DEFAULT_GANTT_POINTS
    if "network" in name:
        return DEFAULT_NETWORK_EDGES
    if "3d" in name:
        return 3000
    if name in {"distribution", "histogram"}:
        return 10000
    return DEFAULT_PLOT_POINTS
