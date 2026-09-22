"""Research-grade data ingestion and statistics helpers for Shoir-IE.

The helpers in this module are deliberately framework-light so they can be unit-tested
independently of Streamlit. They normalize common spreadsheet export problems, expose
safe statistical input choices, and provide reproducible results for research workflows.
"""

from __future__ import annotations

from io import BytesIO
from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats


_HEADER_KEYWORDS = {
    "id", "experiment", "run", "group", "condition", "treatment", "control",
    "scenario", "sample", "outcome", "response", "target", "value", "score",
    "regret", "freshness", "completeness", "conflict", "uncertainty", "shock",
    "split", "date", "time", "cost", "quality", "throughput"
}


def _text(v) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip()


def _header_score(row: Sequence[object]) -> float:
    vals = [_text(v) for v in row]
    nonempty = [v for v in vals if v]
    if len(nonempty) < 2:
        return -1.0
    meaningful = 0
    text_like = 0
    for value in nonempty:
        low = value.lower().replace("_", " ").replace("-", " ")
        tokens = set(low.split())
        if any(k in low for k in _HEADER_KEYWORDS) or tokens & _HEADER_KEYWORDS:
            meaningful += 1
        try:
            float(value.replace(",", ""))
        except Exception:
            text_like += 1
    uniqueness = len(set(nonempty)) / max(1, len(nonempty))
    return (
        len(nonempty) * 1.5
        + meaningful * 4.0
        + text_like * 0.5
        + uniqueness
    )


def detect_header_row(raw: pd.DataFrame, max_scan_rows: int = 60) -> int:
    """Detect the most likely header row in a raw, header=None dataframe.

    Designed to handle Excel exports with title/metadata rows above the actual
    tabular header. Ties prefer the earliest row.
    """
    if raw.empty:
        return 0
    scan = raw.head(max_scan_rows)
    scores = [(idx, _header_score(row)) for idx, row in enumerate(scan.itertuples(index=False, name=None))]
    best_idx, best_score = max(scores, key=lambda item: (item[1], -item[0]))
    if best_score < 0:
        return 0
    return best_idx


def normalize_column_names(columns: Iterable[object]) -> list[str]:
    """Return clean, unique, non-blank column names."""
    result: list[str] = []
    used: dict[str, int] = {}
    for i, col in enumerate(columns, start=1):
        name = _text(col)
        if not name or name.lower().startswith("unnamed"):
            name = f"Column {i}"
        name = " ".join(name.replace("\n", " ").split()).strip()
        count = used.get(name, 0)
        used[name] = count + 1
        if count:
            name = f"{name} ({count + 1})"
        result.append(name)
    return result


def coerce_numeric_columns(df: pd.DataFrame, threshold: float = 0.85) -> pd.DataFrame:
    """Convert mostly-numeric object columns to numeric while preserving labels."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            continue
        s = out[col]
        nonblank = s.notna() & s.astype(str).str.strip().ne("")
        if nonblank.sum() == 0:
            continue
        cleaned = (
            s.astype(str)
            .str.strip()
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
        )
        converted = pd.to_numeric(cleaned, errors="coerce")
        ratio = converted[nonblank].notna().mean()
        if ratio >= threshold:
            # Keep percentages as proportions when every non-null value looks like a %.
            original_text = s[nonblank].astype(str).str.strip()
            percent_like = original_text.str.endswith("%").mean() >= 0.8
            if percent_like:
                converted = converted / 100.0
            out[col] = converted
    return out


def clean_research_dataframe(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Detect header, remove empty content, normalize names, and coerce numeric data."""
    if raw is None or raw.empty:
        return pd.DataFrame(), 0

    # Preserve row positions while detecting the header so the UI can report the
    # real source-sheet row number. Empty rows are removed only after the header
    # has been identified.
    raw = raw.dropna(axis=1, how="all")
    if raw.empty:
        return pd.DataFrame(), 0

    header_row = detect_header_row(raw)
    header = normalize_column_names(raw.iloc[header_row].tolist())
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = header
    data = data.dropna(axis=0, how="all").dropna(axis=1, how="all")

    # Drop columns whose cleaned names are placeholders and whose contents are empty.
    keep_cols = []
    for col in data.columns:
        series = data[col]
        if series.notna().any():
            keep_cols.append(col)
    data = data[keep_cols]
    data.columns = normalize_column_names(data.columns)
    data = coerce_numeric_columns(data)

    # Remove accidental completely empty rows introduced by mixed-type imports.
    data = data.dropna(axis=0, how="all").reset_index(drop=True)
    return data, header_row


def read_research_upload(file_bytes: bytes, filename: str, sheet_name: Optional[str] = None) -> tuple[pd.DataFrame, int, list[str]]:
    """Read CSV/XLSX bytes, automatically detect headers, and return clean data."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        raw = pd.read_csv(BytesIO(file_bytes), header=None)
        clean, header_row = clean_research_dataframe(raw)
        return clean, header_row, ["CSV"]

    if lower.endswith(".xlsx"):
        xls = pd.ExcelFile(BytesIO(file_bytes), engine="openpyxl")
        sheets = xls.sheet_names
        selected = sheet_name or sheets[0]
        raw = pd.read_excel(xls, sheet_name=selected, header=None)
        clean, header_row = clean_research_dataframe(raw)
        return clean, header_row, sheets

    raise ValueError("Unsupported file type. Please upload CSV or XLSX.")


def groupable_columns(df: pd.DataFrame, max_unique: int = 30) -> list[str]:
    """Return categorical or low-cardinality numeric columns suitable for grouping."""
    cols: list[str] = []
    for col in df.columns:
        s = df[col].dropna()
        if s.empty:
            continue
        nunique = s.nunique(dropna=True)
        unique_ratio = nunique / max(1, len(s))
        name = str(col)
        identifier_like = bool(
            pd.Series([name]).str.contains(
                r"(^|[ _-])(id|identifier|index|key)([ _-]|$)",
                case=False,
                regex=True,
            ).iloc[0]
        )
        # High-cardinality identifier fields (Scenario ID, Subject ID, etc.) are
        # not meaningful experimental grouping variables even when the dataset
        # is small enough to have <= max_unique distinct values.
        if identifier_like and unique_ratio > 0.80:
            continue
        if (
            pd.api.types.is_object_dtype(df[col])
            or pd.api.types.is_string_dtype(df[col])
            or isinstance(df[col].dtype, pd.CategoricalDtype)
        ):
            if 2 <= nunique <= max_unique:
                cols.append(col)
        elif pd.api.types.is_numeric_dtype(df[col]):
            if 2 <= nunique <= max_unique:
                cols.append(col)
    return cols


def groups_from_column(df: pd.DataFrame, group_col: str) -> pd.Series:
    """Create a stable categorical representation of a group column."""
    s = df[group_col]
    if pd.api.types.is_numeric_dtype(s):
        return s.map(lambda x: f"{x:g}" if pd.notna(x) else np.nan)
    return s.astype("string").str.strip()


def paired_from_long(
    df: pd.DataFrame,
    outcome_col: str,
    pair_col: str,
    condition_col: str,
    condition_1: str,
    condition_2: str,
) -> pd.DataFrame:
    """Pivot long-format paired data into matched numeric columns."""
    work = df[[pair_col, condition_col, outcome_col]].copy()
    work[outcome_col] = pd.to_numeric(work[outcome_col], errors="coerce")
    work = work.dropna(subset=[pair_col, condition_col, outcome_col])
    work[condition_col] = work[condition_col].astype(str).str.strip()
    work = work[work[condition_col].isin([condition_1, condition_2])]
    if work.empty:
        return pd.DataFrame(columns=[condition_1, condition_2])

    # Repeated measurements within a pair/condition are reduced to their mean.
    pivot = work.pivot_table(
        index=pair_col,
        columns=condition_col,
        values=outcome_col,
        aggfunc="mean",
    )
    if condition_1 not in pivot.columns or condition_2 not in pivot.columns:
        return pd.DataFrame(columns=[condition_1, condition_2])
    pivot = pivot[[condition_1, condition_2]].dropna()
    return pivot


def eta_squared(groups: Sequence[np.ndarray]) -> float:
    """One-way ANOVA eta-squared."""
    arrays = [np.asarray(g, dtype=float) for g in groups if len(g) > 0]
    if len(arrays) < 2:
        return float("nan")
    grand = np.concatenate(arrays).mean()
    ss_between = sum(len(g) * (g.mean() - grand) ** 2 for g in arrays)
    ss_total = sum(((g - grand) ** 2).sum() for g in arrays)
    return float(ss_between / ss_total) if ss_total > 0 else 0.0


def cohens_d(x: Sequence[float], y: Sequence[float]) -> float:
    """Cohen's d using the pooled standard deviation."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    nx, ny = len(x), len(y)
    if nx < 2 or ny < 2:
        return float("nan")
    vx, vy = np.var(x, ddof=1), np.var(y, ddof=1)
    pooled = np.sqrt(((nx - 1) * vx + (ny - 1) * vy) / (nx + ny - 2))
    return float((x.mean() - y.mean()) / pooled) if pooled > 0 else 0.0


def tukey_hsd_table(groups: dict[str, Sequence[float]]) -> pd.DataFrame:
    """Return pairwise Tukey HSD results when supported by installed SciPy."""
    names = list(groups.keys())
    arrays = [np.asarray(groups[n], dtype=float) for n in names]
    if len(arrays) < 2:
        return pd.DataFrame()

    # scipy.stats.tukey_hsd is available in modern SciPy releases.
    if not hasattr(stats, "tukey_hsd"):
        return pd.DataFrame({
            "Comparison": [],
            "Adjusted p-value": [],
            "Note": ["SciPy Tukey HSD is unavailable in this environment."]
        })

    result = stats.tukey_hsd(*arrays)
    ci = result.confidence_interval(confidence_level=0.95)
    rows = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            rows.append({
                "Group 1": names[i],
                "Group 2": names[j],
                "Mean Difference": float(arrays[i].mean() - arrays[j].mean()),
                "Tukey Statistic": float(result.statistic[i, j]),
                "Adjusted p-value": float(result.pvalue[i, j]),
                "95% CI Lower": float(ci.low[i, j]),
                "95% CI Upper": float(ci.high[i, j]),
            })
    return pd.DataFrame(rows)


def holm_adjust(p_values: Sequence[float]) -> np.ndarray:
    """Holm step-down adjusted p-values."""
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    if n == 0:
        return np.array([])
    order = np.argsort(p)
    adj = np.empty(n, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        value = min(1.0, (n - rank) * p[idx])
        running = max(running, value)
        adj[idx] = running
    return adj
