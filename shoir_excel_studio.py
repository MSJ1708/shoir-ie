"""Professional Excel ingestion, cleaning and workbook assembly for Shoir-IE.

The goal is not merely to remove whitespace. This service turns a raw export into
an organized, traceable and presentation-ready workbook while preserving a raw
archive and an auditable record of every automatic transformation.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd


ERROR_TOKENS = {"#N/A", "#VALUE!", "#DIV/0!", "#REF!", "#NAME?", "#NULL!", "#NUM!"}
ID_EXACT = {
    "id", "sku", "code", "serial", "serialnumber", "partnumber", "partno",
    "barcode", "employeeid", "employeeidnumber", "accountnumber", "accountno",
    "orderid", "workorder", "workorderid", "assetid", "customerid", "supplierid",
    "productid", "materialid", "zipcode", "postalcode", "phone", "phonenumber",
}
DATE_HINTS = {"date", "datetime", "time", "timestamp", "created", "updated", "due"}
BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "active", "inactive"}


def _normalise_text(value: Any) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value if value is not None else ""))
    return re.sub(r"\s+", " ", value).strip()


def _normalise_header(value: Any, position: int) -> str:
    text = _normalise_text(value)
    if not text or text.lower().startswith("unnamed"):
        text = f"Column {position + 1}"
    return text


def _deduplicate_headers(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    used: dict[str, int] = {}
    for i, value in enumerate(values):
        base = _normalise_header(value, i)
        count = used.get(base, 0) + 1
        used[base] = count
        result.append(base if count == 1 else f"{base} ({count})")
    return result


def _header_score(row: pd.Series) -> float:
    vals = [_normalise_text(v) for v in row.tolist()]
    nonblank = [v for v in vals if v]
    if not nonblank:
        return -1.0

    unique_ratio = len(set(v.casefold() for v in nonblank)) / len(nonblank)
    text_ratio = sum(not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", v) for v in nonblank) / len(nonblank)
    word_only_rate = sum(
        bool(re.search(r"[A-Za-z]", v)) and not bool(re.search(r"\d", v))
        for v in nonblank
    ) / len(nonblank)
    digit_rate = sum(bool(re.search(r"\d", v)) for v in nonblank) / len(nonblank)
    date_like_rate = sum(
        bool(re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", v))
        or bool(re.fullmatch(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", v))
        for v in nonblank
    ) / len(nonblank)

    # Header rows tend to be short, unique, word-oriented labels. Data rows
    # commonly contain digits, dates, identifiers and measurements. Penalize
    # those signals enough to prefer the actual schema row over the first data row.
    return (
        len(nonblank)
        + unique_ratio * 2.0
        + text_ratio
        + word_only_rate * 2.5
        - digit_rate * 2.0
        - date_like_rate * 3.0
    )


def detect_header_row(raw: pd.DataFrame, scan_rows: int = 20) -> int:
    """Find the most table-like row near the top of a raw worksheet."""
    if raw.empty:
        return 0
    limit = min(scan_rows, len(raw))
    scores = [(_header_score(raw.iloc[i]), i) for i in range(limit)]
    scores.sort(reverse=True)
    return scores[0][1] if scores and scores[0][0] >= 2 else 0


def _read_raw_workbook(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    if not raw:
        raise ValueError("The uploaded file is empty.")
    lower = str(filename).lower()
    if lower.endswith(".csv"):
        return {"CSV": pd.read_csv(io.BytesIO(raw), header=None, dtype=object)}
    if lower.endswith(".xlsx"):
        book = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
        return {
            str(sheet): pd.read_excel(book, sheet_name=sheet, header=None, dtype=object)
            for sheet in book.sheet_names
        }
    raise ValueError("Only .xlsx and .csv files are supported.")


def _is_identifier(name: str, series: pd.Series) -> bool:
    norm = re.sub(r"[^a-z0-9]+", "", name.lower())
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    if norm in ID_EXACT or ("id" in tokens and len(tokens) <= 3):
        return True
    sample = series.dropna().astype(str).str.strip().head(200)
    if sample.empty:
        return False
    leading_zero_rate = float(sample.str.fullmatch(r"0\d+").mean())
    return leading_zero_rate >= 0.20


def _coerce_series(series: pd.Series, name: str) -> tuple[pd.Series, str]:
    s = series.copy()
    if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
        s = s.map(lambda v: _normalise_text(v) if isinstance(v, str) else v)
        s = s.replace(list(ERROR_TOKENS), pd.NA)

    nonblank = s.dropna().astype(str).str.strip()
    if nonblank.empty:
        return s, "Empty / unknown"

    if _is_identifier(name, s):
        return s.astype("string"), "Identifier / text"

    normal = (
        s.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("€", "", regex=False)
        .str.replace("£", "", regex=False)
    )

    percent_rate = float(nonblank.str.endswith("%").mean())
    if percent_rate >= 0.75:
        pct = pd.to_numeric(normal.str.rstrip("%"), errors="coerce")
        if float(pct.notna().mean()) >= 0.94:
            return pct / 100.0, "Percentage"

    compact_name = re.sub(r"[^a-z0-9]+", "", name.lower())
    name_tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
    has_date_name = bool(name_tokens & DATE_HINTS)
    date_signal = float(nonblank.str.contains(r"[-/:]|[A-Za-z]{3,}", regex=True).mean()) >= 0.60

    numeric = pd.to_numeric(normal, errors="coerce")
    numeric_rate = float(numeric.notna().mean()) if len(s) else 0.0

    # Parse dates only when the data itself looks date-like. This prevents
    # numeric durations/counts in columns named "Lead Time", "Cycle Time", etc.
    # from being silently converted into timestamps.
    if (has_date_name or date_signal) and (date_signal or numeric_rate < 0.85):
        parsed_date = pd.to_datetime(s, errors="coerce")
        date_rate = float(parsed_date.notna().mean()) if len(s) else 0.0
        if date_rate >= 0.94:
            return parsed_date, "Date / time"

    if numeric_rate >= 0.94:
        return numeric, "Number"

    lowered = nonblank.str.lower()
    if len(lowered) >= 5 and float(lowered.isin(BOOL_VALUES).mean()) >= 0.95:
        mapping = {
            "true": True, "false": False, "yes": True, "no": False,
            "y": True, "n": False, "active": True, "inactive": False,
        }
        return lowered.map(mapping).astype("boolean"), "Boolean"

    return s.astype("string"), "Text"


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Apply conservative, reversible, audit-friendly automatic cleaning."""
    if not isinstance(df, pd.DataFrame):
        raise ValueError("A pandas DataFrame is required.")

    out = df.copy(deep=True)
    audit: list[dict[str, str]] = []

    blank_rows = int(out.isna().all(axis=1).sum())
    blank_cols = int(out.isna().all(axis=0).sum())
    if blank_rows:
        out = out.dropna(axis=0, how="all")
        audit.append({"Action": "Remove blank rows", "Details": f"Removed {blank_rows:,} fully blank row(s)."})
    if blank_cols:
        out = out.dropna(axis=1, how="all")
        audit.append({"Action": "Remove blank columns", "Details": f"Removed {blank_cols:,} fully blank column(s)."})

    if out.empty:
        return out, audit

    old_cols = list(out.columns)
    out.columns = _deduplicate_headers(out.columns)
    if list(out.columns) != old_cols:
        audit.append({"Action": "Normalize headers", "Details": "Trimmed whitespace/control characters and made duplicate headers unique."})

    error_count = 0
    for col in out.columns:
        before = out[col].copy()
        out[col] = out[col].map(lambda v: _normalise_text(v) if isinstance(v, str) else v)
        out[col] = out[col].replace(list(ERROR_TOKENS), pd.NA)
        error_count += int(before.astype(str).isin(ERROR_TOKENS).sum())
    if error_count:
        audit.append({"Action": "Handle Excel errors", "Details": f"Replaced {error_count:,} standard Excel error token(s) with blanks."})

    if len(out.columns) >= 2:
        first_col = str(out.columns[0])
        first_values = pd.to_numeric(out.iloc[:, 0], errors="coerce")
        sequential = False
        if first_values.notna().all() and len(first_values) >= 3:
            vals = first_values.astype(float).to_numpy()
            sequential = bool(np.allclose(vals, np.arange(len(vals))) or np.allclose(vals, np.arange(1, len(vals) + 1)))
        if first_col.lower().startswith("column 1") and sequential:
            out = out.drop(columns=[out.columns[0]])
            audit.append({"Action": "Remove export index column", "Details": "Dropped the leading sequential row-index column from the source export."})

    before_dupes = len(out)
    out = out.drop_duplicates(keep="first").reset_index(drop=True)
    if len(out) != before_dupes:
        audit.append({"Action": "Remove duplicate rows", "Details": f"Removed {before_dupes - len(out):,} exact duplicate row(s)."})

    type_counts: dict[str, int] = {}
    for col in list(out.columns):
        converted, inferred = _coerce_series(out[col], str(col))
        out[col] = converted
        type_counts[inferred] = type_counts.get(inferred, 0) + 1
    audit.append({
        "Action": "Infer data types",
        "Details": "; ".join(f"{k}: {v}" for k, v in sorted(type_counts.items())),
    })
    return out, audit


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    rows, cols = int(len(df)), int(len(df.columns))
    missing = int(df.isna().sum().sum())
    cells = max(1, rows * max(1, cols))
    missing_pct = 100.0 * missing / cells
    duplicates = int(df.duplicated().sum()) if rows else 0
    score = max(0.0, min(100.0, 100.0 - missing_pct * 0.65 - (duplicates / max(1, rows)) * 25.0))
    numeric = int(sum(pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c]) for c in df.columns))
    dates = int(sum(pd.api.types.is_datetime64_any_dtype(df[c]) for c in df.columns))
    booleans = int(sum(pd.api.types.is_bool_dtype(df[c]) for c in df.columns))
    return {
        "Rows": rows,
        "Columns": cols,
        "Missing cells": missing,
        "Missing %": round(missing_pct, 2),
        "Duplicate rows": duplicates,
        "Quality score": round(score, 1),
        "Numeric columns": numeric,
        "Date/time columns": dates,
        "Boolean columns": booleans,
        "Text columns": max(0, cols - numeric - dates - booleans),
    }


def _safe_sheet(name: str, used: set[str], prefix: str = "") -> str:
    cleaned = re.sub(r"[:\\/?*\[\]]+", "", str(name or "")).strip()
    cleaned = (prefix + cleaned)[:31] or "Sheet"
    base = cleaned
    i = 2
    while cleaned in used:
        suffix = f" ({i})"
        cleaned = (base[:31-len(suffix)] + suffix)[:31]
        i += 1
    used.add(cleaned)
    return cleaned


def _cell_is_na(value: Any) -> bool:
    try:
        result = pd.isna(value)
        return bool(result) if not isinstance(result, (list, tuple, np.ndarray, pd.Series)) else False
    except Exception:
        return False


def _write_df(
    ws: Any,
    df: pd.DataFrame,
    start_row: int,
    start_col: int,
    header_fmt: Any,
    date_fmt: Any,
    datetime_fmt: Any,
    number_fmt: Any,
) -> None:
    for j, col in enumerate(df.columns):
        ws.write(start_row, start_col + j, str(col), header_fmt)
    for i, row in enumerate(df.itertuples(index=False, name=None), start_row + 1):
        for j, value in enumerate(row):
            cell = "" if _cell_is_na(value) else value
            fmt = None
            if isinstance(value, pd.Timestamp):
                fmt = datetime_fmt if (value.hour or value.minute or value.second) else date_fmt
                cell = value.to_pydatetime()
            elif pd.api.types.is_number(value):
                fmt = number_fmt
            ws.write(i, start_col + j, cell, fmt)



def _column_role(name: str, series: pd.Series) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
    tokens = set(norm.split())
    if tokens & {"id", "sku", "code", "serial", "part", "asset", "order", "customer", "employee"}:
        return "Identifier"
    if tokens & {"date", "time", "timestamp", "created", "updated", "due"}:
        return "Time"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "Time"
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return "Measure"
    nunique = int(series.nunique(dropna=True))
    if len(series) and nunique <= min(25, max(5, int(len(series) * 0.20))):
        return "Dimension"
    return "Text / Attribute"


def _infer_display_type(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "Date / time"
    if pd.api.types.is_bool_dtype(series):
        return "Boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "Number"
    return "Text"


def _column_format(workbook: Any, series: pd.Series):
    if pd.api.types.is_datetime64_any_dtype(series):
        return workbook.add_format({"num_format": "yyyy-mm-dd"})
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return workbook.add_format({"num_format": "#,##0.00"})
    if pd.api.types.is_bool_dtype(series):
        return workbook.add_format({"align": "center"})
    return None


def _potential_outlier_count(series: pd.Series) -> int:
    if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        return 0
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 8:
        return 0
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = float(q3 - q1)
    if iqr <= 0:
        return 0
    lower, upper = float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)
    return int(((values < lower) | (values > upper)).sum())


def _sheet_intelligence(df: pd.DataFrame, name: str) -> dict[str, Any]:
    numeric = [
        str(c) for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
    ]
    dates = [str(c) for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    identifiers = [str(c) for c in df.columns if _column_role(str(c), df[c]) == "Identifier"]
    dimensions = [str(c) for c in df.columns if _column_role(str(c), df[c]) == "Dimension"]
    missing = int(df.isna().sum().sum())
    duplicates = int(df.duplicated().sum()) if len(df) else 0
    outliers = int(sum(_potential_outlier_count(df[c]) for c in df.columns))
    completeness = round(100.0 - (missing / max(1, len(df) * max(1, len(df.columns)))) * 100.0, 1)
    issues = int(missing > 0) + int(duplicates > 0) + int(outliers > 0)
    quality = max(0.0, round(completeness - (duplicates / max(1, len(df))) * 25.0 - (outliers / max(1, len(df) * max(1, len(numeric)))) * 10.0, 1))
    if quality >= 95 and issues == 0:
        status = "READY"
    elif quality >= 85:
        status = "READY WITH REVIEW"
    else:
        status = "REVIEW REQUIRED"

    if dates and numeric:
        visual = "Trend / time-series"
    elif len(numeric) >= 2:
        visual = "Scatter / relationship"
    elif numeric and dimensions:
        visual = "Category comparison"
    elif numeric:
        visual = "Distribution"
    elif dimensions:
        visual = "Category distribution"
    else:
        visual = "Data completeness"

    next_action = (
        "Proceed to analysis"
        if status == "READY"
        else "Review missing values / duplicates / outlier flags"
    )
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "missing": missing,
        "duplicates": duplicates,
        "outliers": outliers,
        "completeness": completeness,
        "quality": quality,
        "status": status,
        "numeric": numeric,
        "dates": dates,
        "identifiers": identifiers,
        "dimensions": dimensions,
        "visual": visual,
        "next_action": next_action,
    }



def build_ultimate_workbook(
    title: str,
    sheets: dict[str, pd.DataFrame],
    raw_sheets: dict[str, pd.DataFrame],
    audits: dict[str, list[dict[str, str]]],
    profiles: dict[str, dict[str, Any]],
) -> bytes:
    """Build a polished, navigable industrial workbook with an executive layer."""
    buf = io.BytesIO()
    with pd.ExcelWriter(
        buf,
        engine="xlsxwriter",
        datetime_format="yyyy-mm-dd hh:mm",
        date_format="yyyy-mm-dd",
    ) as writer:
        workbook = writer.book
        workbook.set_properties({
            "title": title,
            "subject": "Shoir-IE Industrial Excel Intelligence Workbook",
            "author": "Shoir-IE",
            "comments": (
                "Automatically assembled by Shoir-IE. Clean working data, "
                "quality intelligence, analysis blueprint, audit trail and raw source archives."
            ),
        })

        # Design system for a restrained professional industrial workbook.
        dark = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#17324D"})
        accent = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#0F766E"})
        pale = workbook.add_format({"bg_color": "#F4F7FA", "font_color": "#334155"})
        title_fmt = workbook.add_format({"bold": True, "font_size": 20, "font_color": "#17324D"})
        subtitle_fmt = workbook.add_format({"font_size": 10, "font_color": "#64748B", "italic": True})
        section_fmt = workbook.add_format({"bold": True, "font_size": 13, "font_color": "#17324D"})
        note_fmt = workbook.add_format({"text_wrap": True, "valign": "top", "font_color": "#475569"})
        link_fmt = workbook.add_format({"font_color": "#2563EB", "underline": True, "bold": True})
        good_fmt = workbook.add_format({"bold": True, "font_color": "#166534", "bg_color": "#DCFCE7"})
        review_fmt = workbook.add_format({"bold": True, "font_color": "#92400E", "bg_color": "#FEF3C7"})
        alert_fmt = workbook.add_format({"bold": True, "font_color": "#991B1B", "bg_color": "#FEE2E2"})
        card_label_fmt = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#17324D", "align": "center", "valign": "vcenter"})
        card_value_fmt = workbook.add_format({"bold": True, "font_size": 18, "font_color": "#17324D", "bg_color": "#F4F7FA", "align": "center", "valign": "vcenter"})
        number_fmt = workbook.add_format({"num_format": "#,##0.00"})
        percent_fmt = workbook.add_format({"num_format": "0.0%"})
        date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})
        datetime_fmt = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})
        used: set[str] = set()

        intelligence: dict[str, dict[str, Any]] = {}
        clean_names: dict[str, str] = {}
        raw_names: dict[str, str] = {}
        dictionary_rows: list[dict[str, Any]] = []
        quality_rows: list[dict[str, Any]] = []
        blueprint_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []
        issue_rows: list[dict[str, Any]] = []

        for original, df in sheets.items():
            info = _sheet_intelligence(df, original)
            intelligence[original] = info
            clean_names[original] = _safe_sheet(original, used, "CLEAN - ")
            raw_names[original] = _safe_sheet(original, used, "RAW - ")

            quality_rows.append({
                "Sheet": clean_names[original],
                "Source": original,
                "Rows": info["rows"],
                "Columns": info["columns"],
                "Missing cells": info["missing"],
                "Missing %": round(100.0 - info["completeness"], 1),
                "Duplicate rows": info["duplicates"],
                "Potential outliers": info["outliers"],
                "Quality": info["quality"],
                "Status": info["status"],
            })
            blueprint_rows.append({
                "Sheet": clean_names[original],
                "Source": original,
                "Identifier fields": ", ".join(info["identifiers"][:6]) or "—",
                "Time fields": ", ".join(info["dates"][:4]) or "—",
                "Measure fields": ", ".join(info["numeric"][:8]) or "—",
                "Dimension fields": ", ".join(info["dimensions"][:8]) or "—",
                "Recommended visual": info["visual"],
                "Next recommended action": info["next_action"],
            })

            if info["missing"]:
                issue_rows.append({
                    "Severity": "REVIEW",
                    "Sheet": clean_names[original],
                    "Issue": "Missing values",
                    "Count": info["missing"],
                    "Action": "Review blanks before statistical analysis or KPI reporting.",
                })
            if info["duplicates"]:
                issue_rows.append({
                    "Severity": "REVIEW",
                    "Sheet": clean_names[original],
                    "Issue": "Duplicate rows",
                    "Count": info["duplicates"],
                    "Action": "Confirm whether duplicates are legitimate transactions or repeated exports.",
                })
            if info["outliers"]:
                issue_rows.append({
                    "Severity": "REVIEW",
                    "Sheet": clean_names[original],
                    "Issue": "Potential statistical outliers",
                    "Count": info["outliers"],
                    "Action": "Investigate flagged numeric values; Shoir-IE does not delete them automatically.",
                })

            for col in df.columns:
                role = _column_role(str(col), df[col])
                dtype = _infer_display_type(df[col])
                nonnull = int(df[col].notna().sum())
                missing_pct = round(float(df[col].isna().mean() * 100) if len(df) else 100.0, 2)
                unique = int(df[col].nunique(dropna=True))
                sample = [str(x) for x in df[col].dropna().head(3).tolist()]
                if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
                    nums = pd.to_numeric(df[col], errors="coerce").dropna()
                    minimum = f"{nums.min():,.4g}" if not nums.empty else "—"
                    maximum = f"{nums.max():,.4g}" if not nums.empty else "—"
                else:
                    minimum = "—"
                    maximum = "—"
                suggested = {
                    "Identifier": "Join keys / traceability",
                    "Time": "Trend analysis / time-series",
                    "Measure": "KPI / statistics / charting",
                    "Dimension": "Grouping / segmentation",
                    "Text / Attribute": "Description / annotation",
                }[role]
                dictionary_rows.append({
                    "Sheet": clean_names[original],
                    "Column": str(col),
                    "Role": role,
                    "Type": dtype,
                    "Non-null": nonnull,
                    "Missing %": missing_pct,
                    "Unique": unique,
                    "Example 1": sample[0] if len(sample) > 0 else "—",
                    "Example 2": sample[1] if len(sample) > 1 else "—",
                    "Example 3": sample[2] if len(sample) > 2 else "—",
                    "Min": minimum,
                    "Max": maximum,
                    "Suggested use": suggested,
                })
            for event in audits.get(original, []):
                audit_rows.append({"Sheet": clean_names[original], "Source": original, **event})

        # ---------- START HERE ----------
        start = workbook.add_worksheet("START HERE")
        used.add("START HERE")
        start.hide_gridlines(2)
        start.set_tab_color("#17324D")
        start.set_column("A:A", 24)
        start.set_column("B:B", 66)
        start.set_column("C:C", 24)
        start.merge_range("A1:C2", title, title_fmt)
        start.write("A3", "Shoir-IE Industrial Excel Intelligence Workbook", section_fmt)
        start.write("A5", "How this workbook is organized", section_fmt)
        start.write("A6", "1", dark)
        start.write("B6", "START HERE — navigation and workbook map")
        start.write_url("A7", "internal:'EXECUTIVE DASHBOARD'!A1", "EXECUTIVE DASHBOARD", link_fmt)
        start.write("B7", "Management-ready summary of scale, quality and readiness.")
        start.write_url("A8", "internal:'DATA QUALITY CENTER'!A1", "DATA QUALITY CENTER", link_fmt)
        start.write("B8", "Missing values, duplicates, potential outliers and review actions.")
        start.write_url("A9", "internal:'DATA DICTIONARY'!A1", "DATA DICTIONARY", link_fmt)
        start.write("B9", "What every field means structurally: role, type, completeness and examples.")
        start.write_url("A10", "internal:'ANALYSIS BLUEPRINT'!A1", "ANALYSIS BLUEPRINT", link_fmt)
        start.write("B10", "What Shoir-IE recommends doing next with each sheet.")
        start.write_url("A11", "internal:'CLEANING AUDIT'!A1", "CLEANING AUDIT", link_fmt)
        start.write("B11", "Every automatic transformation recorded for traceability.")
        start.write("A13", "Clean working sheets", section_fmt)
        start.write("A14", "Sheet", dark)
        start.write("B14", "Purpose", dark)
        row = 15
        for original in sheets:
            name = clean_names[original]
            start.write_url(row - 1, 0, f"internal:'{name}'!A1", name, link_fmt)
            start.write(row - 1, 1, f"Working table prepared from source sheet '{original}'.")
            row += 1
        row += 1
        start.write(row - 1, 0, "Traceability", section_fmt)
        start.merge_range(
            row, 0, row + 2, 2,
            "The CLEAN sheets are intended for working, analysis and presentation. "
            "Hidden RAW sheets preserve the imported source values. Shoir-IE does not silently discard "
            "potential outliers; they are flagged for review so engineering judgment remains visible.",
            note_fmt,
        )
        start.set_zoom(90)
        start.freeze_panes(5, 0)

        # ---------- EXECUTIVE DASHBOARD ----------
        dash = workbook.add_worksheet("EXECUTIVE DASHBOARD")
        used.add("EXECUTIVE DASHBOARD")
        dash.hide_gridlines(2)
        dash.set_tab_color("#0F766E")
        dash.set_column("A:A", 25)
        dash.set_column("B:H", 16)
        dash.set_column("I:N", 16)
        dash.merge_range("A1:N2", f"{title} · Executive Dashboard", title_fmt)
        dash.write("A3", f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", subtitle_fmt)

        total_rows = sum(info["rows"] for info in intelligence.values())
        total_columns = sum(info["columns"] for info in intelligence.values())
        total_missing = sum(info["missing"] for info in intelligence.values())
        total_issues = sum(int(info["missing"] > 0) + int(info["duplicates"] > 0) + int(info["outliers"] > 0) for info in intelligence.values())
        avg_quality = round(float(np.mean([info["quality"] for info in intelligence.values()])) if intelligence else 0.0, 1)

        card_metrics = [
            ("SOURCE SHEETS", len(sheets)),
            ("RECORDS", total_rows),
            ("FIELDS", total_columns),
            ("AVG QUALITY", f"{avg_quality:.1f}%"),
            ("MISSING CELLS", total_missing),
            ("REVIEW ITEMS", total_issues),
        ]
        for idx, (label, value) in enumerate(card_metrics):
            c = idx * 2
            dash.merge_range(4, c, 4, c + 1, label, card_label_fmt)
            dash.merge_range(5, c, 6, c + 1, value, card_value_fmt)
        dash.write("A8", "Readiness by source", section_fmt)
        q_frame = pd.DataFrame(quality_rows)
        _write_df(dash, q_frame, 8, 0, dark, date_fmt, datetime_fmt, number_fmt)
        dash.freeze_panes(9, 0)
        if len(q_frame):
            for j, col in enumerate(q_frame.columns):
                dash.set_column(j, j, 17 if col not in {"Sheet", "Source", "Status"} else 24)
            dash.conditional_format(9, 8, 8 + len(q_frame), 8, {
                "type": "3_color_scale", "min_color": "#FEE2E2", "mid_color": "#FEF3C7", "max_color": "#DCFCE7"
            })
            chart = workbook.add_chart({"type": "column"})
            sheet_col = list(q_frame.columns).index("Sheet")
            quality_col = list(q_frame.columns).index("Quality")
            chart.add_series({
                "name": "Quality",
                "categories": ["EXECUTIVE DASHBOARD", 9, sheet_col, 8 + len(q_frame), sheet_col],
                "values": ["EXECUTIVE DASHBOARD", 9, quality_col, 8 + len(q_frame), quality_col],
                "fill": {"color": "#0F766E"},
                "border": {"color": "#0F766E"},
            })
            chart.set_title({"name": "Sheet quality"})
            chart.set_y_axis({"min": 0, "max": 100, "name": "Quality %"})
            chart.set_legend({"none": True})
            chart.set_size({"width": 560, "height": 290})
            dash.insert_chart(8, 10, chart)
        dash.write("A" + str(11 + len(q_frame) + 2), "Workbook operating sequence", section_fmt)
        dash.merge_range(12 + len(q_frame), 0, 14 + len(q_frame), 8,
                         "IMPORT → CLEAN → QUALITY CHECK → UNDERSTAND FIELDS → ANALYZE → VISUALIZE → EXPORT. "
                         "Use the Analysis Blueprint as the bridge from cleaned data to the next engineering workflow.",
                         note_fmt)

        # ---------- DATA QUALITY CENTER ----------
        quality_ws = workbook.add_worksheet("DATA QUALITY CENTER")
        used.add("DATA QUALITY CENTER")
        quality_ws.hide_gridlines(2)
        quality_ws.set_tab_color("#D97706")
        quality_ws.set_column("A:A", 24)
        quality_ws.set_column("B:H", 18)
        quality_ws.set_column("I:I", 72)
        quality_ws.merge_range("A1:I2", "DATA QUALITY CENTER", title_fmt)
        quality_ws.write("A3", "Quality issues are surfaced for review; Shoir-IE does not hide or silently delete suspicious values.", subtitle_fmt)
        _write_df(quality_ws, q_frame, 4, 0, dark, date_fmt, datetime_fmt, number_fmt)
        quality_ws.freeze_panes(5, 0)
        if len(q_frame):
            quality_ws.autofilter(4, 0, 4 + len(q_frame), len(q_frame.columns) - 1)
        issue_frame = pd.DataFrame(issue_rows or [{
            "Severity": "PASS",
            "Sheet": "Workbook",
            "Issue": "No automatic review flags",
            "Count": 0,
            "Action": "The current workbook passed the automatic quality checks.",
        }])
        start_issue = 4 + len(q_frame) + 3
        quality_ws.write(start_issue - 1, 0, "Review register", section_fmt)
        _write_df(quality_ws, issue_frame, start_issue, 0, dark, date_fmt, datetime_fmt, number_fmt)
        quality_ws.set_column("F:F", 18)
        quality_ws.set_column("E:E", 12)
        quality_ws.set_column("F:F", 72)
        quality_ws.conditional_format(start_issue + 1, 0, start_issue + len(issue_frame), 0, {
            "type": "text", "criteria": "containing", "value": "PASS", "format": good_fmt
        })
        quality_ws.conditional_format(start_issue + 1, 0, start_issue + len(issue_frame), 0, {
            "type": "text", "criteria": "containing", "value": "REVIEW", "format": review_fmt
        })

        # ---------- DATA DICTIONARY ----------
        dict_ws = workbook.add_worksheet("DATA DICTIONARY")
        used.add("DATA DICTIONARY")
        dict_ws.hide_gridlines(2)
        dict_ws.set_tab_color("#2563EB")
        dict_ws.set_column("A:A", 24)
        dict_ws.set_column("B:B", 30)
        dict_ws.set_column("C:D", 18)
        dict_ws.set_column("E:G", 14)
        dict_ws.set_column("H:J", 28)
        dict_ws.set_column("K:L", 14)
        dict_ws.set_column("M:M", 32)
        dict_ws.merge_range("A1:M2", "DATA DICTIONARY · Field Intelligence", title_fmt)
        dict_ws.write("A3", "Roles are structural suggestions, not business semantics invented from thin evidence.", subtitle_fmt)
        dict_frame = pd.DataFrame(dictionary_rows)
        _write_df(dict_ws, dict_frame, 4, 0, dark, date_fmt, datetime_fmt, number_fmt)
        dict_ws.freeze_panes(5, 0)
        if len(dict_frame):
            dict_ws.autofilter(4, 0, 4 + len(dict_frame), len(dict_frame.columns) - 1)
            dict_ws.conditional_format(5, 5, 4 + len(dict_frame), 5, {
                "type": "3_color_scale", "min_color": "#DCFCE7", "mid_color": "#FEF3C7", "max_color": "#FEE2E2"
            })

        # ---------- ANALYSIS BLUEPRINT ----------
        blue_ws = workbook.add_worksheet("ANALYSIS BLUEPRINT")
        used.add("ANALYSIS BLUEPRINT")
        blue_ws.hide_gridlines(2)
        blue_ws.set_tab_color("#7C3AED")
        blue_ws.set_column("A:A", 25)
        blue_ws.set_column("B:B", 24)
        blue_ws.set_column("C:F", 32)
        blue_ws.set_column("G:H", 28)
        blue_ws.merge_range("A1:H2", "ANALYSIS BLUEPRINT · From Clean Data to Engineering Work", title_fmt)
        blue_ws.write("A3", "Use this sheet as the handoff from data preparation into Shoir-IE's analysis modules.", subtitle_fmt)
        blue_frame = pd.DataFrame(blueprint_rows)
        _write_df(blue_ws, blue_frame, 4, 0, dark, date_fmt, datetime_fmt, number_fmt)
        blue_ws.freeze_panes(5, 0)
        if len(blue_frame):
            blue_ws.autofilter(4, 0, 4 + len(blue_frame), len(blue_frame.columns) - 1)

        # ---------- CLEANING AUDIT ----------
        audit_ws = workbook.add_worksheet("CLEANING AUDIT")
        used.add("CLEANING AUDIT")
        audit_ws.hide_gridlines(2)
        audit_ws.set_tab_color("#64748B")
        audit_ws.set_column("A:B", 24)
        audit_ws.set_column("C:C", 30)
        audit_ws.set_column("D:D", 96)
        audit_ws.merge_range("A1:D2", "CLEANING AUDIT · Exact Automatic Transformations", title_fmt)
        audit_ws.write("A3", "This log explains what Shoir-IE changed. Raw source sheets remain hidden for traceability.", subtitle_fmt)
        audit_frame = pd.DataFrame(audit_rows or [{
            "Sheet": "", "Source": "", "Action": "No changes required", "Details": "Source data was already clean.",
        }])
        _write_df(audit_ws, audit_frame, 4, 0, dark, date_fmt, datetime_fmt, number_fmt)
        audit_ws.freeze_panes(5, 0)
        if len(audit_frame):
            audit_ws.autofilter(4, 0, 4 + len(audit_frame), len(audit_frame.columns) - 1)
        audit_ws.set_row(3, 28)

        # ---------- CLEAN WORKING SHEETS ----------
        for original, df in sheets.items():
            clean_name = clean_names[original]
            raw_name = raw_names[original]
            info = intelligence[original]

            ws = workbook.add_worksheet(clean_name)
            ws.hide_gridlines(2)
            ws.set_tab_color("#0F766E" if info["status"] == "READY" else "#D97706")
            ws.freeze_panes(7, 0)
            ws.set_zoom(90)
            ws.set_column(0, len(df.columns) - 1, 14)
            if len(df.columns):
                widths = []
                for col in df.columns:
                    values = [str(x) for x in df[col].head(80).tolist()]
                    width = min(38, max(12, len(str(col)) + 2, max([len(v) for v in values] + [0]) + 2))
                    widths.append(width)
                for j, width in enumerate(widths):
                    ws.set_column(j, j, width)

            ws.merge_range(0, 0, 1, max(1, len(df.columns) + 5), f"{clean_name} · {original}", title_fmt)
            ws.write(2, 0, f"Status: {info['status']}", good_fmt if info["status"] == "READY" else review_fmt)
            ws.write(2, 1, f"Quality {info['quality']:.1f}%", section_fmt)
            ws.write(2, 2, f"Rows {info['rows']:,}", pale)
            ws.write(2, 3, f"Fields {info['columns']:,}", pale)
            ws.write(2, 4, f"Missing {info['missing']:,}", pale)
            ws.write(2, 5, f"Potential outliers {info['outliers']:,}", pale)
            ws.write(4, 0, "Working data", section_fmt)
            ws.write(5, 0, "Use filters to isolate records; hidden RAW archive remains available for source tracing.", subtitle_fmt)

            # Header row + data with semantic column formats.
            for j, col in enumerate(df.columns):
                ws.write(6, j, str(col), dark)
                ws.write_comment(6, j, f"Role: {_column_role(str(col), df[col])}\nType: {_infer_display_type(df[col])}")
            for i, row_values in enumerate(df.itertuples(index=False, name=None), 7):
                for j, value in enumerate(row_values):
                    cell = "" if _cell_is_na(value) else value
                    fmt = _column_format(workbook, df.iloc[:, j])
                    ws.write(i, j, cell, fmt)

            if len(df.columns) and len(df):
                end_row = 6 + len(df)
                ws.autofilter(6, 0, end_row, len(df.columns) - 1)
                table_name = re.sub(r"[^A-Za-z0-9_]", "_", f"T_{clean_name}")[:240] or f"T_{len(used)}"
                try:
                    ws.add_table(6, 0, end_row, len(df.columns) - 1, {
                        "name": table_name,
                        "style": "Table Style Medium 4",
                        "columns": [{"header": str(c)} for c in df.columns],
                    })
                except Exception:
                    pass

                # Make blanks visible without overwriting the underlying data.
                ws.conditional_format(7, 0, end_row, len(df.columns) - 1, {
                    "type": "blanks", "format": review_fmt
                })
                for j, col in enumerate(df.columns):
                    if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
                        ws.conditional_format(7, j, end_row, j, {
                            "type": "3_color_scale",
                            "min_color": "#FEE2E2",
                            "mid_color": "#FEF3C7",
                            "max_color": "#DCFCE7",
                        })
                    ws.set_column(j, j, min(42, max(12, len(str(col)) + 3)))

                # One truthful chart per cleaned sheet when numeric data exists.
                numeric_cols = [
                    c for c in df.columns
                    if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
                ]
                if numeric_cols:
                    y = numeric_cols[0]
                    y_idx = list(df.columns).index(y)
                    x_col = info["dates"][0] if info["dates"] else (
                        info["dimensions"][0] if info["dimensions"] else next(
                            (str(c) for c in df.columns if str(c) != str(y)), str(y)
                        )
                    )
                    x_idx = list(df.columns).index(x_col)
                    chart = workbook.add_chart({"type": "line" if x_col in info["dates"] else "column"})
                    chart.add_series({
                        "name": [clean_name, 6, y_idx],
                        "categories": [clean_name, 7, x_idx, end_row, x_idx],
                        "values": [clean_name, 7, y_idx, end_row, y_idx],
                    })
                    chart.set_title({"name": f"{y} · {x_col}"})
                    chart.set_legend({"none": True})
                    chart.set_size({"width": 620, "height": 300})
                    ws.insert_chart(3, max(2, len(df.columns) + 1), chart)

            # Hidden source archive.
            raw_ws = workbook.add_worksheet(raw_name)
            raw_ws.hide()
            raw_ws.write(0, 0, f"RAW ARCHIVE · {original}", title_fmt)
            raw_ws.write(1, 0, "Original imported values. Do not edit this sheet; use a CLEAN sheet for working.", subtitle_fmt)
            _write_df(raw_ws, raw_sheets.get(original, pd.DataFrame()), 3, 0, dark, date_fmt, datetime_fmt, number_fmt)
            raw_ws.freeze_panes(4, 0)
            raw_ws.set_column(0, max(0, len(raw_sheets.get(original, pd.DataFrame()).columns) - 1), 15)

        # Navigation links on every governance sheet.
        for sheet_name in ["EXECUTIVE DASHBOARD", "DATA QUALITY CENTER", "DATA DICTIONARY", "ANALYSIS BLUEPRINT", "CLEANING AUDIT"]:
            ws = workbook.get_worksheet_by_name(sheet_name)
            if ws is not None:
                ws.write_url("A" + str(ws.dim_rowmax + 2), "internal:'START HERE'!A1", "← Back to START HERE", link_fmt)

    return buf.getvalue()

def build_ultimate_bundle(
    title: str,
    xlsx_bytes: bytes,
    audits: dict[str, list[dict[str, str]]],
    profiles: dict[str, dict[str, Any]],
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("shoir_ie_ultimate_workbook.xlsx", xlsx_bytes)
        zf.writestr("cleaning_audit.json", json.dumps(audits, indent=2, ensure_ascii=False).encode("utf-8"))
        zf.writestr("quality_profiles.json", json.dumps(profiles, indent=2, ensure_ascii=False).encode("utf-8"))
        zf.writestr(
            "README.txt",
            (
                f"{title}\n\n"
                "The workbook is automatically cleaned and assembled into a presentation-ready working file. "
                "START HERE is the navigation hub; CLEAN sheets are the working data; RAW sheets preserve the imported source; "
                "DATA DICTIONARY, QUALITY CHECKS and CLEANING AUDIT explain the transformation trail."
            ).encode("utf-8"),
        )
    return buf.getvalue()


def process_uploaded_workbook(raw: bytes, filename: str) -> dict[str, Any]:
    signature = hashlib.sha256(raw).hexdigest()
    raw_sheets = _read_raw_workbook(raw, filename)
    cleaned: dict[str, pd.DataFrame] = {}
    audits: dict[str, list[dict[str, str]]] = {}
    profiles: dict[str, dict[str, Any]] = {}

    for source_name, raw_df in raw_sheets.items():
        header_row = detect_header_row(raw_df)
        if raw_df.empty:
            table = pd.DataFrame()
        else:
            headers = _deduplicate_headers(raw_df.iloc[header_row].tolist())
            table = raw_df.iloc[header_row + 1:].copy()
            table.columns = headers
            table = table.dropna(axis=1, how="all").dropna(axis=0, how="all")

        cleaned_df, audit = clean_dataframe(table)
        cleaned[source_name] = cleaned_df
        audits[source_name] = [
            {"Action": "Detect table header", "Details": f"Detected source header row {header_row + 1}."}
        ] + audit
        profiles[source_name] = profile_dataframe(cleaned_df)

    xlsx = build_ultimate_workbook(
        f"Shoir-IE — {filename}",
        cleaned,
        raw_sheets,
        audits,
        profiles,
    )
    return {
        "signature": signature,
        "filename": filename,
        "raw_sheets": raw_sheets,
        "cleaned_sheets": cleaned,
        "audits": audits,
        "profiles": profiles,
        "xlsx": xlsx,
        "bundle": build_ultimate_bundle(f"Shoir-IE — {filename}", xlsx, audits, profiles),
    }


def render_excel_data_cleaning_studio(tier: str, username: str) -> None:
    import streamlit as st

    from shoir_tier_capabilities import tier_allows

    if not tier_allows(tier, "Starter"):
        st.warning("This workspace is not included in your current package.")
        return

    st.markdown("## 📊 Excel Intelligence & Data Cleaning Studio")
    st.caption(
        "Drop in a messy workbook. Shoir-IE automatically detects table headers, removes presentation noise, "
        "normalizes types, preserves identifiers, documents every transformation, and assembles a professional workbook."
    )

    upload = st.file_uploader(
        "Upload raw Excel / CSV",
        type=["xlsx", "csv"],
        key="excel_studio_upload",
        help="Messy exports, multi-sheet workbooks and title/metadata rows are supported.",
    )
    if upload is not None:
        raw = upload.getvalue()
        signature = hashlib.sha256(raw).hexdigest()
        if st.session_state.get("excel_studio_signature") != signature:
            try:
                with st.spinner("Building your professional workbook…"):
                    result = process_uploaded_workbook(raw, upload.name)
                st.session_state["excel_studio_signature"] = signature
                st.session_state["excel_studio_result"] = result
                st.success(
                    f"✅ Automatically assembled **{len(result['cleaned_sheets'])} sheet(s)**. "
                    "Your original data is preserved in hidden RAW archive sheets."
                )
            except Exception as exc:
                st.error(f"Excel could not be transformed safely: {type(exc).__name__}: {exc}")

    result = st.session_state.get("excel_studio_result")
    if not isinstance(result, dict):
        st.info("Upload a raw workbook to activate automatic formatting and the full workbook assembly.")
        return

    cleaned = result["cleaned_sheets"]
    profiles = result["profiles"]
    audits = result["audits"]
    profile_frame = pd.DataFrame([{"Sheet": k, **v} for k, v in profiles.items()])

    # Feed the selected clean table into the universal visualization layer so
    # this module is never graph-less after a successful import.
    if cleaned:
        default_visual_sheet = st.session_state.get("excel_studio_sheet")
        if default_visual_sheet not in cleaned:
            default_visual_sheet = next(iter(cleaned))
        st.session_state["excel_studio_visual_df"] = cleaned[default_visual_sheet].copy(deep=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sheets", len(cleaned))
    m2.metric("Rows", f"{sum(len(v) for v in cleaned.values()):,}")
    m3.metric("Transformations", f"{sum(len(v) for v in audits.values()):,}")
    m4.metric("Avg. quality", f"{float(profile_frame['Quality score'].mean()):.1f}%" if not profile_frame.empty else "—")

    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Clean Data", "Dictionary & Audit", "Export"])
    with tab1:
        st.dataframe(profile_frame, use_container_width=True, hide_index=True)
        st.markdown("### Workbook structure")
        st.markdown("**START HERE → EXECUTIVE SUMMARY → CLEAN sheets → DATA DICTIONARY → QUALITY CHECKS → CLEANING AUDIT**")
        st.caption("RAW sheets are intentionally hidden in the Excel file but retained for traceability.")

    with tab2:
        sheet = st.selectbox("Clean sheet", list(cleaned), key="excel_studio_sheet")
        df = cleaned[sheet]
        st.session_state["excel_studio_visual_df"] = df.copy(deep=True)
        st.dataframe(df.head(1000), use_container_width=True, hide_index=True)
        a, b = st.columns(2)
        with a:
            if st.button("↻ Re-run cleaning", key="excel_studio_reclean", use_container_width=True):
                cleaned_df, new_audit = clean_dataframe(df)
                cleaned[sheet] = cleaned_df
                audits[sheet].extend(new_audit)
                profiles[sheet] = profile_dataframe(cleaned_df)
                result["xlsx"] = build_ultimate_workbook(
                    f"Shoir-IE — {result['filename']}", cleaned, result["raw_sheets"], audits, profiles
                )
                result["bundle"] = build_ultimate_bundle(
                    f"Shoir-IE — {result['filename']}", result["xlsx"], audits, profiles
                )
                st.session_state["excel_studio_result"] = result
                st.rerun()
        with b:
            if st.button("↩ Restore original", key="excel_studio_restore", use_container_width=True):
                raw_df = result["raw_sheets"][sheet]
                header_row = detect_header_row(raw_df)
                table = raw_df.iloc[header_row + 1:].copy()
                table.columns = _deduplicate_headers(raw_df.iloc[header_row].tolist())
                table = table.dropna(axis=1, how="all").dropna(axis=0, how="all")
                cleaned_df, restore_audit = clean_dataframe(table)
                result["cleaned_sheets"][sheet] = cleaned_df
                result["audits"][sheet] = [
                    {"Action": "Restore", "Details": "Restored from the preserved source sheet and re-applied safe cleaning."}
                ] + restore_audit
                result["profiles"][sheet] = profile_dataframe(cleaned_df)
                result["xlsx"] = build_ultimate_workbook(
                    f"Shoir-IE — {result['filename']}",
                    result["cleaned_sheets"],
                    result["raw_sheets"],
                    result["audits"],
                    result["profiles"],
                )
                result["bundle"] = build_ultimate_bundle(
                    f"Shoir-IE — {result['filename']}", result["xlsx"], result["audits"], result["profiles"]
                )
                st.session_state["excel_studio_result"] = result
                st.rerun()

    with tab3:
        dictionary_rows = []
        for sheet, frame in cleaned.items():
            for col in frame.columns:
                dictionary_rows.append({
                    "Sheet": sheet,
                    "Column": str(col),
                    "Type": (
                        "Date / time" if pd.api.types.is_datetime64_any_dtype(frame[col])
                        else "Boolean" if pd.api.types.is_bool_dtype(frame[col])
                        else "Number" if pd.api.types.is_numeric_dtype(frame[col])
                        else "Text"
                    ),
                    "Non-null": int(frame[col].notna().sum()),
                    "Missing %": round(float(frame[col].isna().mean() * 100) if len(frame) else 100.0, 2),
                    "Examples": " | ".join(str(x) for x in frame[col].dropna().head(3).tolist())[:200],
                })
        st.dataframe(pd.DataFrame(dictionary_rows), use_container_width=True, hide_index=True)
        audit_frame = pd.DataFrame([
            {"Sheet": k, **event} for k, events in audits.items() for event in events
        ])
        st.markdown("### Cleaning audit")
        st.dataframe(audit_frame, use_container_width=True, hide_index=True)

    with tab4:
        safe_name = re.sub(r"[^A-Za-z0-9]+", "_", result["filename"]).strip("_").lower()
        st.download_button(
            "📥 Download Ultimate Excel Workbook",
            result["xlsx"],
            file_name=f"shoir_ie_ultimate_{safe_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
        st.download_button(
            "📦 Download Complete Workbook Package",
            result["bundle"],
            file_name=f"shoir_ie_ultimate_{safe_name}.zip",
            mime="application/zip",
            use_container_width=True,
        )
