"""Professional Excel ingestion, cleaning and workbook assembly for Shoir-IE.

The goal is not merely to remove whitespace. This service turns a raw export into
an organized, traceable and presentation-ready workbook while preserving a raw
archive and an auditable record of every automatic transformation.
"""

from __future__ import annotations

import hashlib
import math
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


def _decode_text_bytes(raw: bytes) -> tuple[str, str]:
    """Decode delimited text deterministically across common industrial export encodings."""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError("CSV/text encoding could not be decoded safely.") from last_error


def _detect_csv_delimiter(text: str) -> str:
    """Detect common CSV delimiters while avoiding false positives from decimal commas."""
    sample = "\n".join(text.splitlines()[:40])
    try:
        import csv
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\\t|")
        return dialect.delimiter
    except (csv.Error, TypeError, AttributeError):
        candidates = [",", ";", "\\t", "|"]
        lines = [line for line in sample.splitlines() if line.strip()]
        scores = {
            delim: float(np.mean([line.count(delim) for line in lines]))
            if lines else 0.0
            for delim in candidates
        }
        return max(scores, key=scores.get) if max(scores.values(), default=0.0) > 0 else ","


def _read_raw_workbook(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    if not raw:
        raise ValueError("The uploaded file is empty.")
    lower = str(filename).lower()
    if lower.endswith((".csv", ".txt", ".tsv")):
        text, encoding = _decode_text_bytes(raw)
        # Some industrial export pipelines serialize line breaks as literal
        # backslash-n sequences. Only expand them when the decoded payload has
        # no real row breaks; otherwise preserve literal field content exactly.
        if "\\n" in text and "\n" not in text and "\r" not in text:
            text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
        delimiter = _detect_csv_delimiter(text)
        frame = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            header=None,
            dtype=object,
            keep_default_na=False,
            na_filter=False,
        )
        frame.attrs["source_encoding"] = encoding
        frame.attrs["source_delimiter"] = delimiter
        return {"CSV": frame}
    if lower.endswith((".xlsx", ".xlsm")):
        book = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
        return {
            str(sheet): pd.read_excel(book, sheet_name=sheet, header=None, dtype=object)
            for sheet in book.sheet_names
        }
    raise ValueError("Supported imports are .xlsx, .xlsm, .csv, .tsv and .txt.")


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


def build_ultimate_workbook(
    title: str,
    sheets: dict[str, pd.DataFrame],
    raw_sheets: dict[str, pd.DataFrame],
    audits: dict[str, list[dict[str, str]]],
    profiles: dict[str, dict[str, Any]],
) -> bytes:
    """Create a navigable, traceable and presentation-ready XLSX workbook."""
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
            "subject": "Shoir-IE professionally cleaned industrial workbook",
            "author": "Shoir-IE",
            "comments": "Generated by the Shoir-IE Excel Intelligence & Cleaning Studio.",
        })

        navy = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#163A5F"})
        sub = workbook.add_format({"font_color": "#4B6175", "italic": True})
        title_fmt = workbook.add_format({"bold": True, "font_size": 18, "font_color": "#163A5F"})
        section_fmt = workbook.add_format({"bold": True, "font_size": 12, "font_color": "#163A5F"})
        note_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})
        number_fmt = workbook.add_format({"num_format": "#,##0.00"})
        date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})
        datetime_fmt = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})
        used: set[str] = set()
        clean_names: dict[str, str] = {}
        raw_names: dict[str, str] = {}

        start = workbook.add_worksheet("START HERE")
        used.add("START HERE")
        start.set_tab_color("#163A5F")
        start.hide_gridlines(2)
        start.set_column("A:A", 28)
        start.set_column("B:B", 70)
        start.write("A1", title, title_fmt)
        start.write("A2", "Shoir-IE Excel Intelligence Studio", section_fmt)
        start.write("A4", "Workbook map", section_fmt)
        row = 4
        start.write(row, 0, "Sheet", navy)
        start.write(row, 1, "Purpose", navy)
        row += 1
        for fixed_name, purpose in [
            ("EXECUTIVE SUMMARY", "Workbook health and how to use the file."),
            ("DATA DICTIONARY", "Inferred types, completeness and example values."),
            ("QUALITY CHECKS", "Quality and readiness metrics for each cleaned sheet."),
            ("CLEANING AUDIT", "Every automatic transformation applied."),
        ]:
            start.write_url(row, 0, f"internal:'{fixed_name}'!A1", string=fixed_name)
            start.write(row, 1, purpose)
            row += 1

        for original in sheets:
            clean_name = _safe_sheet(original, used, "CLEAN - ")
            raw_name = _safe_sheet(original, used, "RAW - ")
            clean_names[original] = clean_name
            raw_names[original] = raw_name
            start.write_url(row, 0, f"internal:'{clean_name}'!A1", string=clean_name)
            start.write(row, 1, f"Professionally cleaned working table from source sheet '{original}'.")
            row += 1

        start.write(row + 1, 0, "Traceability", section_fmt)
        start.merge_range(
            row + 2, 0, row + 3, 1,
            "CLEAN sheets are the working tables. Hidden RAW sheets preserve the original imported values. "
            "Use the DATA DICTIONARY, QUALITY CHECKS and CLEANING AUDIT to understand what Shoir-IE changed.",
            note_fmt,
        )

        summary = workbook.add_worksheet("EXECUTIVE SUMMARY")
        used.add("EXECUTIVE SUMMARY")
        summary.hide_gridlines(2)
        summary.set_column("A:A", 30)
        summary.set_column("B:B", 26)
        summary.write("A1", title, title_fmt)
        summary.write("A2", f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", sub)
        summary.write("A4", "Workbook health", section_fmt)
        avg_quality = round(float(np.mean([v["Quality score"] for v in profiles.values()])) if profiles else 0.0, 1)
        for i, (label, value) in enumerate([
            ("Source sheets", len(sheets)),
            ("Clean sheets", len(sheets)),
            ("Total cleaned rows", sum(int(v["Rows"]) for v in profiles.values())),
            ("Total columns", sum(int(v["Columns"]) for v in profiles.values())),
            ("Average quality score", avg_quality),
            ("Transformations recorded", sum(len(v) for v in audits.values())),
        ], 5):
            summary.write(i, 0, label, navy)
            summary.write(i, 1, value)
        summary.write("A13", "Suggested workflow", section_fmt)
        summary.merge_range(
            "A14:B17",
            "1. Start with a CLEAN sheet. 2. Review the Data Dictionary. 3. Check Quality Checks. "
            "4. Review the Cleaning Audit. 5. Keep RAW sheets available when you need to trace a value back to its source.",
            note_fmt,
        )

        quality_rows: list[dict[str, Any]] = []
        dictionary_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []

        for original, df in sheets.items():
            clean_name = clean_names[original]
            profile = profiles[original]
            quality_rows.append({
                "Sheet": clean_name,
                "Source": original,
                **profile,
                "Status": "Ready" if profile["Quality score"] >= 90 else "Review",
            })

            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    inferred = "Date / time"
                elif pd.api.types.is_bool_dtype(df[col]):
                    inferred = "Boolean"
                elif pd.api.types.is_numeric_dtype(df[col]):
                    inferred = "Number"
                else:
                    inferred = "Text"
                sample = " | ".join(str(x) for x in df[col].dropna().head(3).tolist())
                dictionary_rows.append({
                    "Sheet": clean_name,
                    "Column": str(col),
                    "Inferred type": inferred,
                    "Non-null": int(df[col].notna().sum()),
                    "Missing %": round(float(df[col].isna().mean() * 100) if len(df) else 100.0, 2),
                    "Example values": sample[:250],
                })

            for event in audits.get(original, []):
                audit_rows.append({"Sheet": clean_name, "Source": original, **event})

            ws = workbook.add_worksheet(clean_name)
            ws.hide_gridlines(2)
            ws.freeze_panes(5, 0)
            ws.set_tab_color("#2F6B8A")
            ws.write("A1", f"{clean_name} — {original}", title_fmt)
            ws.write("A2", "Cleaned, typed, duplicate-checked and presentation-formatted by Shoir-IE.", sub)
            ws.write("A4", "Working data", section_fmt)
            _write_df(ws, df, 4, 0, navy, date_fmt, datetime_fmt, number_fmt)

            if len(df.columns) and len(df):
                ws.autofilter(4, 0, 4 + len(df), len(df.columns) - 1)
                for j, col in enumerate(df.columns):
                    values = [str(x) for x in df[col].head(100).tolist()]
                    width = min(42, max(11, len(str(col)) + 2, max([len(x) for x in values] + [0]) + 2))
                    ws.set_column(j, j, width)
                    if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
                        ws.conditional_format(
                            5, j, 4 + len(df), j,
                            {"type": "3_color_scale", "min_color": "#FEE2E2", "mid_color": "#FEF3C7", "max_color": "#DCFCE7"},
                        )
                table_name = re.sub(r"[^A-Za-z0-9_]", "_", f"T_{clean_name}")[:240] or f"T_{len(used)}"
                try:
                    ws.add_table(4, 0, 4 + len(df), len(df.columns) - 1, {
                        "name": table_name,
                        "style": "Table Style Medium 2",
                        "columns": [{"header": str(c)} for c in df.columns],
                    })
                except Exception:
                    pass

            raw_ws = workbook.add_worksheet(raw_names[original])
            raw_ws.hide()
            raw_ws.write(0, 0, f"RAW ARCHIVE — {original}", title_fmt)
            _write_df(raw_ws, raw_sheets.get(original, pd.DataFrame()), 2, 0, navy, date_fmt, datetime_fmt, number_fmt)

            numeric_cols = [
                c for c in df.columns
                if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
            ]
            if numeric_cols and len(df) >= 2:
                y = numeric_cols[0]
                y_idx = list(df.columns).index(y)
                cat_col = next((c for c in df.columns if c != y and not pd.api.types.is_numeric_dtype(df[c])), df.columns[0])
                cat_idx = list(df.columns).index(cat_col)
                chart_type = "line" if pd.api.types.is_datetime64_any_dtype(df[cat_col]) else "column"
                chart = workbook.add_chart({"type": chart_type})
                chart.add_series({
                    "name": [clean_name, 4, y_idx],
                    "categories": [clean_name, 5, cat_idx, 4 + len(df), cat_idx],
                    "values": [clean_name, 5, y_idx, 4 + len(df), y_idx],
                })
                chart.set_title({"name": f"{y} by {cat_col}"})
                chart.set_legend({"none": True})
                chart.set_size({"width": 700, "height": 340})
                ws.insert_chart(3, len(df.columns) + 2, chart)

        for name, rows, widths in [
            ("QUALITY CHECKS", quality_rows, [28, 24, 14, 12, 16, 16, 16, 18, 18, 14]),
            ("DATA DICTIONARY", dictionary_rows, [28, 32, 20, 14, 14, 44]),
            ("CLEANING AUDIT", audit_rows or [{
                "Sheet": "", "Source": "", "Action": "No changes required",
                "Details": "The source workbook was already clean.",
            }], [28, 24, 30, 90]),
        ]:
            ws = workbook.add_worksheet(name)
            used.add(name)
            ws.hide_gridlines(2)
            frame = pd.DataFrame(rows)
            _write_df(ws, frame, 2, 0, navy, date_fmt, datetime_fmt, number_fmt)
            ws.freeze_panes(3, 0)
            if len(frame.columns) and len(frame):
                ws.autofilter(2, 0, 2 + len(frame), len(frame.columns) - 1)
            for j, width in enumerate(widths):
                ws.set_column(j, j, width)

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
        type=["xlsx", "xlsm", "csv"],
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



# ---------------------------------------------------------------------------
# Shoir-IE Excel Studio quality/governance upgrade layer
# ---------------------------------------------------------------------------
# This layer intentionally builds on the existing ingestion primitives above.
# It adds industrial data-governance, review intelligence and safer export
# without removing the existing API surface.

_ENHANCED_NULL_TOKENS = {
    "", "na", "n/a", "n.a.", "none", "null", "nil", "unknown", "not available",
    "not_applicable", "not applicable", "-", "—", "–", "n.m.", "missing", "?",
}
_PERCENT_NAME_HINTS = {
    "percent", "percentage", "pct", "rate", "ratio", "yield", "oee", "utilization",
    "availability", "performance", "quality", "fpy", "service level",
}
_ENTITY_HINTS = {
    "asset": ("Asset", ("asset", "equipment", "machine", "workcenter", "work centre")),
    "process": ("Process", ("process", "operation", "step", "routing")),
    "product": ("Product", ("product", "sku", "part", "item")),
    "material": ("Material", ("material", "component", "raw material")),
    "order": ("Order", ("order", "work order", "wo")),
    "workforce": ("Workforce", ("employee", "operator", "worker", "workforce")),
    "quality": ("Quality", ("quality", "defect", "scrap", "yield", "fpy")),
    "maintenance": ("Maintenance", ("maintenance", "failure", "repair", "mtbf", "mttr")),
    "energy": ("Energy", ("energy", "electricity", "gas", "kwh", "mwh")),
    "cost": ("Cost", ("cost", "price", "expense", "capex", "opex")),
    "customer": ("Customer", ("customer", "client", "account")),
    "supplier": ("Supplier", ("supplier", "vendor")),
    "time": ("Time", ("date", "datetime", "timestamp", "time", "created", "updated")),
}


def _enhanced_null_normalise(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = df.copy(deep=True)
    changed = 0
    for col in list(out.columns):
        if _is_identifier(str(col), out[col]):
            # Identifiers are deliberately protected: values such as "-" or
            # "NA" may be legitimate codes and must not be rewritten silently.
            continue
        series = out[col]
        mask = series.map(
            lambda v: isinstance(v, str)
            and _normalise_text(v).casefold() in _ENHANCED_NULL_TOKENS
        )
        changed += int(mask.sum())
        if changed:
            out.loc[mask, col] = pd.NA
    return out, changed


def _normalise_accounting_numbers(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = df.copy(deep=True)
    changed = 0
    for col in list(out.columns):
        if _is_identifier(str(col), out[col]):
            continue
        if not (pd.api.types.is_object_dtype(out[col]) or pd.api.types.is_string_dtype(out[col])):
            continue
        def fix(value: Any) -> Any:
            nonlocal changed
            if not isinstance(value, str):
                return value
            text = _normalise_text(value).strip()
            m = re.fullmatch(r"\(([-+]?\d[\d,]*(?:\.\d+)?)\)", text)
            if not m:
                return value
            changed += 1
            return f"-{m.group(1)}"
        out[col] = out[col].map(fix)
    return out, changed


def _enhanced_clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    prepared, missing_changes = _enhanced_null_normalise(df)
    prepared, accounting_changes = _normalise_accounting_numbers(prepared)
    preserved_blank_columns = [
        str(col) for col in df.columns
        if int(df[col].notna().sum()) > 0 and int(prepared[col].notna().sum()) == 0
    ]
    cleaned, audit = _BASE_CLEAN_DATAFRAME(prepared)
    for col in preserved_blank_columns:
        if col not in cleaned.columns:
            cleaned[col] = pd.Series(pd.NA, index=cleaned.index, dtype="string")
            audit.append({
                "Action": "Preserve source field after missing-value normalization",
                "Details": f"Retained source field '{col}' as an explicit blank review field rather than silently dropping it.",
            })
    if missing_changes:
        audit.insert(0, {
            "Action": "Normalize common missing-value tokens",
            "Details": f"Converted {missing_changes:,} non-identifier token(s) such as N/A, NULL, — and ? to blanks.",
        })
    if accounting_changes:
        audit.insert(0, {
            "Action": "Normalize accounting negatives",
            "Details": f"Converted {accounting_changes:,} parenthesized numeric value(s) such as (1,250) to -1250.",
        })
    return cleaned, audit


def _column_role(name: str, series: pd.Series) -> str:
    low = str(name).casefold()
    norm = re.sub(r"[^a-z0-9]+", "", low)
    if _is_identifier(str(name), series):
        return "Identifier"
    if any(h in low for h in ("date", "datetime", "timestamp", "created", "updated", "due")):
        return "Time"
    if any(h in low for h in (
        "qty", "quantity", "amount", "cost", "price", "rate", "time", "duration",
        "demand", "supply", "output", "input", "value", "score", "hours", "seconds",
        "temperature", "pressure", "weight", "energy", "power", "revenue", "margin",
    )) and pd.api.types.is_numeric_dtype(series):
        return "Measure"
    if pd.api.types.is_numeric_dtype(series):
        return "Measure"
    if len(series) and series.nunique(dropna=True) <= max(12, int(len(series) * 0.1)):
        return "Dimension"
    if norm in {"description", "comment", "notes", "remarks"}:
        return "Text"
    return "Attribute"


def _canonical_entity_hint(name: str) -> str:
    low = str(name).casefold()
    for entity, (label, hints) in _ENTITY_HINTS.items():
        if any(h in low for h in hints):
            return label
    return "—"


def _unit_hint(name: str) -> str:
    text = str(name)
    patterns = [
        r"[\(\[]\s*(kg|g|mg|lb|mm|cm|m|km|s|sec|min|hr|hrs|h|hours|kwh|mwh|kw|mw|usd|sar|%|°c|°f|c|f)\s*[\)\]]",
        r"(?:^|[\s_])(?:unit|units)\s*[:=_-]\s*([A-Za-z%°]+)",
        r"(?:^|[\s_])([A-Za-z%°]+)\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            token = match.group(1).lower()
            if token in {"m", "h", "s", "c", "f"} and len(text.split()) == 1:
                continue
            return token
    return "—"


def _type_confidence(series: pd.Series, role: str) -> str:
    if series.empty:
        return "Low"
    if role in {"Identifier", "Time"}:
        return "High"
    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        return "High"
    unique = int(series.nunique(dropna=True))
    if unique <= 1:
        return "High"
    return "Medium"


def _potential_outlier_count(series: pd.Series) -> int:
    if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        return 0
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 8 or values.nunique() < 2:
        return 0
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = float(q3 - q1)
    if iqr > 0:
        low, high = float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)
        return int(((values < low) | (values > high)).sum())
    median = float(values.median())
    mad = float((values - median).abs().median())
    if mad > 0:
        robust_z = 0.6745 * (values - median) / mad
        return int(robust_z.abs().gt(3.5).sum())
    spread = float(values.max() - values.min())
    if spread <= 0:
        return 0
    return int((values != median).sum())


def _date_sanity_count(series: pd.Series) -> int:
    if not pd.api.types.is_datetime64_any_dtype(series):
        return 0
    values = series.dropna()
    if values.empty:
        return 0
    bad = (values.dt.year < 1900) | (values.dt.year > 2100)
    return int(bad.sum())


def _percentage_range_count(name: str, series: pd.Series) -> int:
    low = str(name).casefold()
    if not any(token in low for token in _PERCENT_NAME_HINTS):
        return 0
    if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        return 0
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return 0
    # After percentage normalization, ratios should normally live in [0, 1].
    return int(((values < 0) | (values > 1)).sum())


def _table_block_count(raw: pd.DataFrame, header_row: int) -> int:
    if raw.empty or header_row >= len(raw) - 1:
        return 1
    body = raw.iloc[header_row + 1:].copy()
    if body.empty:
        return 1
    blank_rows = body.isna().all(axis=1).tolist()
    blocks = 1
    for i in range(len(blank_rows) - 1):
        if blank_rows[i] and not blank_rows[i + 1]:
            blocks += 1
    return max(1, min(blocks, 20))


def _schema_fingerprint(df: pd.DataFrame) -> str:
    payload = "|".join(
        f"{str(col).casefold()}::{str(df[col].dtype)}"
        for col in df.columns
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()


def _quality_review_register(df: pd.DataFrame, sheet: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    rows = len(df)
    duplicates = int(df.duplicated().sum()) if rows else 0
    if duplicates:
        issues.append({
            "Severity": "High" if duplicates / max(1, rows) >= 0.05 else "Medium",
            "Sheet": sheet, "Field": "Row level", "Issue": "Duplicate rows detected",
            "Evidence": f"{duplicates:,} exact duplicate row(s).",
            "Recommended action": "Confirm whether repeats are genuine events or accidental duplicates.",
        })
    for col in df.columns:
        series = df[col]
        missing = int(series.isna().sum())
        missing_pct = float(series.isna().mean() * 100) if rows else 100.0
        role = _column_role(str(col), series)
        outliers = _potential_outlier_count(series)
        duplicate_ids = 0
        if role == "Identifier":
            duplicate_ids = int(series.dropna().astype("string").duplicated().sum())
        if missing_pct >= 50:
            issues.append({
                "Severity": "High", "Sheet": sheet, "Field": str(col),
                "Issue": "High missingness", "Evidence": f"{missing:,} missing value(s) ({missing_pct:.1f}%).",
                "Recommended action": "Validate whether the field is required; consider source-system remediation.",
            })
        elif missing_pct >= 20:
            issues.append({
                "Severity": "Medium", "Sheet": sheet, "Field": str(col),
                "Issue": "Material missingness", "Evidence": f"{missing:,} missing value(s) ({missing_pct:.1f}%).",
                "Recommended action": "Confirm the missingness mechanism before analysis.",
            })
        if duplicate_ids:
            issues.append({
                "Severity": "High", "Sheet": sheet, "Field": str(col),
                "Issue": "Duplicate identifier values", "Evidence": f"{duplicate_ids:,} repeated identifier occurrence(s).",
                "Recommended action": "Verify key uniqueness before joins, aggregation or master-data use.",
            })
        if outliers:
            issues.append({
                "Severity": "Low", "Sheet": sheet, "Field": str(col),
                "Issue": "Potential statistical outliers", "Evidence": f"{outliers:,} value(s) outside the 1.5×IQR fence.",
                "Recommended action": "Review the records; do not delete automatically.",
            })
        if series.nunique(dropna=True) <= 1 and len(series) >= 3:
            issues.append({
                "Severity": "Low", "Sheet": sheet, "Field": str(col),
                "Issue": "Constant / near-empty field", "Evidence": "Only one distinct non-null value is present.",
                "Recommended action": "Check whether the field is useful for analysis or should remain metadata.",
            })
        percent_range = _percentage_range_count(str(col), series)
        if percent_range:
            issues.append({
                "Severity": "High", "Sheet": sheet, "Field": str(col),
                "Issue": "Percentage/ratio range violation",
                "Evidence": f"{percent_range:,} value(s) fall outside the normalized 0–1 range.",
                "Recommended action": "Confirm whether the source uses percentages (e.g. 95) or ratios (e.g. 0.95).",
            })
        date_bad = _date_sanity_count(series)
        if date_bad:
            issues.append({
                "Severity": "Medium", "Sheet": sheet, "Field": str(col),
                "Issue": "Date sanity exception", "Evidence": f"{date_bad:,} date(s) fall outside the 1900–2100 review window.",
                "Recommended action": "Validate source dates and time interpretation.",
            })
    if len(df.columns):
        first = df.iloc[:, 0].astype("string").str.casefold()
        subtotal = first.str.contains(r"^(?:grand\s+)?(?:sub)?total$", regex=True, na=False)
        if int(subtotal.sum()):
            issues.append({
                "Severity": "Low", "Sheet": sheet, "Field": str(df.columns[0]),
                "Issue": "Potential subtotal / footer rows",
                "Evidence": f"{int(subtotal.sum()):,} row(s) look like subtotal/total labels.",
                "Recommended action": "Decide whether these rows are source totals or should be excluded from row-level analysis.",
            })
    return issues


def _enhanced_profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    base = _BASE_PROFILE_DATAFRAME(df)
    rows = int(len(df))
    duplicate_ids = 0
    outliers = 0
    constants = 0
    for col in df.columns:
        role = _column_role(str(col), df[col])
        if role == "Identifier":
            duplicate_ids += int(df[col].dropna().astype("string").duplicated().sum())
        outliers += _potential_outlier_count(df[col])
        if len(df) >= 3 and int(df[col].nunique(dropna=True)) <= 1:
            constants += 1
    review_count = len(_quality_review_register(df, "_profile"))
    missing_pct = float(base.get("Missing %", 0.0))
    duplicate_ratio = float(base.get("Duplicate rows", 0)) / max(1, rows) * 100
    duplicate_id_ratio = duplicate_ids / max(1, rows) * 100
    outlier_ratio = outliers / max(1, rows) * 100
    score = max(
        0.0,
        min(
            100.0,
            100.0
            - missing_pct * 0.55
            - duplicate_ratio * 0.25
            - duplicate_id_ratio * 0.20
            - min(outlier_ratio, 20.0) * 0.08
        ),
    )
    status = "READY" if score >= 95 and review_count == 0 else "READY WITH REVIEW" if score >= 80 else "REVIEW REQUIRED"
    return {
        **base,
        "Potential outliers": outliers,
        "Duplicate identifier occurrences": duplicate_ids,
        "Constant columns": constants,
        "Review items": review_count,
        "Quality score": round(score, 1),
        "Readiness": status,
        "Schema fingerprint": _schema_fingerprint(df),
    }


def _field_intelligence_rows(df: pd.DataFrame, sheet: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for col in df.columns:
        series = df[col]
        role = _column_role(str(col), series)
        non_null = int(series.notna().sum())
        missing = int(series.isna().sum())
        examples = " | ".join(str(x) for x in series.dropna().head(3).tolist())[:180]
        unique = int(series.nunique(dropna=True))
        outliers = _potential_outlier_count(series)
        action = "Use as analysis field"
        if role == "Identifier":
            action = "Protect as key / join candidate"
        elif missing:
            action = "Review missing values"
        elif outliers:
            action = "Review potential outliers"
        elif series.nunique(dropna=True) <= 1:
            action = "Review low-information field"
        elif pd.api.types.is_datetime64_any_dtype(series):
            action = "Use as time axis"
        elif role == "Dimension":
            action = "Use for grouping / segmentation"
        inferred_type = (
            "Date / time" if pd.api.types.is_datetime64_any_dtype(series)
            else "Boolean" if pd.api.types.is_bool_dtype(series)
            else "Number" if pd.api.types.is_numeric_dtype(series)
            else "Clock time" if (
                pd.api.types.is_string_dtype(series)
                and float(
                    series.dropna().astype("string").str.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?").mean()
                ) >= 0.75
            )
            else "Text"
        )
        rows.append({
            "Sheet": sheet,
            "Field": str(col),
            "Role": role,
            # "Type" is retained as a stable public compatibility alias for
            # consumers/tests that predate the richer "Inferred type" field.
            "Type": inferred_type,
            "Inferred type": inferred_type,
            "Type confidence": _type_confidence(series, role),
            "Canonical entity": _canonical_entity_hint(str(col)),
            "Unit hint": _unit_hint(str(col)),
            "Rows": int(len(series)),
            "Non-null": non_null,
            "Missing %": round(float(missing / max(1, len(series)) * 100), 2),
            "Unique": unique,
            "Potential outliers": outliers,
            "Example values": examples,
            "Suggested action": action,
        })
    return rows


def _cross_sheet_map(cleaned: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    names = list(cleaned)
    rows: list[dict[str, Any]] = []
    for i, left in enumerate(names):
        left_norm = {re.sub(r"[^a-z0-9]+", "", str(c).casefold()): str(c) for c in cleaned[left].columns}
        for right in names[i + 1:]:
            right_norm = {re.sub(r"[^a-z0-9]+", "", str(c).casefold()): str(c) for c in cleaned[right].columns}
            shared = sorted(set(left_norm) & set(right_norm))
            if shared:
                rows.append({
                    "Sheet A": left,
                    "Sheet B": right,
                    "Potential shared fields": ", ".join(shared[:12]),
                    "Shared field count": len(shared),
                    "Join guidance": "Review key uniqueness and semantic meaning before joining.",
                })
    return rows


def _extract_source_metadata(raw: bytes, filename: str, raw_sheets: dict[str, pd.DataFrame], header_rows: dict[str, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signature = hashlib.sha256(raw).hexdigest()
    imported = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    metadata: list[dict[str, Any]] = []
    formulas: list[dict[str, Any]] = []
    workbook_formula_scanned = False
    try:
        import openpyxl
        if str(filename).lower().endswith(".xlsx"):
            book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
            workbook_formula_scanned = True
            for source_name, frame in raw_sheets.items():
                ws = book[source_name] if source_name in book.sheetnames else None
                formula_count = 0
                formula_limit = 10000
                if ws is not None:
                    for row in ws.iter_rows():
                        for cell in row:
                            value = cell.value
                            if isinstance(value, str) and value.startswith("="):
                                formula_count += 1
                                if len(formulas) < formula_limit:
                                    formulas.append({
                                        "Sheet": source_name,
                                        "Cell": cell.coordinate,
                                        "Formula": value,
                                        "Type": "Original source formula",
                                        "Note": "Archived for traceability; cleaned sheets contain values, not executable source formulas.",
                                    })
                metadata.append({
                    "File": str(filename),
                    "SHA256": signature,
                    "Imported": imported,
                    "Source type": "Excel .xlsx",
                    "Source sheet": source_name,
                    "Sheet state": getattr(ws, "sheet_state", "visible") if ws is not None else "unknown",
                    "Source rows": int(len(raw_sheets[source_name])),
                    "Source columns": int(len(raw_sheets[source_name].columns)),
                    "Detected header row": int(header_rows.get(source_name, 0) + 1),
                    "Detected table blocks": _table_block_count(raw_sheets[source_name], header_rows.get(source_name, 0)),
                    "Merged ranges": int(len(getattr(ws, "merged_cells", []) or [])) if ws is not None else 0,
                    "Source formulas": formula_count,
                })
            try:
                book.close()
            except Exception:
                pass
    except Exception:
        workbook_formula_scanned = False

    if not workbook_formula_scanned:
        delimiter = "—"
        try:
            import csv
            sample = raw[:4096].decode("utf-8-sig", errors="replace")
            delimiter = csv.Sniffer().sniff(sample).delimiter
        except Exception:
            if str(filename).lower().endswith(".csv"):
                delimiter = ","
        for source_name, frame in raw_sheets.items():
            metadata.append({
                "File": str(filename),
                "SHA256": signature,
                "Imported": imported,
                "Source type": "CSV" if str(filename).lower().endswith(".csv") else "Workbook",
                "Source sheet": source_name,
                "Sheet state": "—",
                "Source rows": int(len(frame)),
                "Source columns": int(len(frame.columns)),
                "Detected header row": int(header_rows.get(source_name, 0) + 1),
                "Detected table blocks": _table_block_count(frame, header_rows.get(source_name, 0)),
                "Merged ranges": 0,
                "Source formulas": 0,
                "CSV delimiter": delimiter,
            })
    return metadata, formulas


def _safe_xlsx_write(ws: Any, row: int, col: int, value: Any, fmt: Any = None) -> None:
    if _cell_is_na(value):
        ws.write_blank(row, col, None, fmt)
        return
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, bool):
        ws.write_boolean(row, col, bool(value), fmt)
        return
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        try:
            number = float(value)
            if math.isfinite(number):
                ws.write_number(row, col, number, fmt)
                return
        except Exception:
            pass
    # Never use worksheet.write() for arbitrary strings: strings beginning with
    # "=" can otherwise become formulas. write_string makes the export inert.
    ws.write_string(row, col, str(value), fmt)


def _safe_write_frame(ws: Any, df: pd.DataFrame, start_row: int, start_col: int, header_fmt: Any, date_fmt: Any, datetime_fmt: Any, number_fmt: Any) -> None:
    for j, col in enumerate(df.columns):
        ws.write_string(start_row, start_col + j, str(col), header_fmt)
    for i, row in enumerate(df.itertuples(index=False, name=None), start_row + 1):
        for j, value in enumerate(row):
            fmt = date_fmt if isinstance(value, pd.Timestamp) and not (value.hour or value.minute or value.second) else datetime_fmt if isinstance(value, pd.Timestamp) else number_fmt if pd.api.types.is_number(value) and not isinstance(value, bool) else None
            _safe_xlsx_write(ws, i, start_col + j, value, fmt)


def _safe_table_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", str(name)).strip("_") or "Table"
    base = ("T_" + base)[:200]
    candidate = base
    n = 2
    while candidate in used:
        suffix = f"_{n}"
        candidate = (base[:200 - len(suffix)] + suffix)
        n += 1
    used.add(candidate)
    return candidate


_BASE_CLEAN_DATAFRAME = clean_dataframe
_BASE_PROFILE_DATAFRAME = profile_dataframe


def _enhanced_detect_header_row(raw: pd.DataFrame, scan_rows: int = 25) -> int:
    if raw.empty:
        return 0
    limit = min(scan_rows, len(raw))
    if len(raw) >= 2:
        first = [_normalise_text(v) for v in raw.iloc[0].tolist()]
        second = [_normalise_text(v) for v in raw.iloc[1].tolist()]
        first_nonblank = [v for v in first if v]
        second_nonblank = [v for v in second if v]
        if first_nonblank and len(first_nonblank) >= 2:
            first_is_schema = all(
                bool(re.search(r"[A-Za-z]", v))
                and not bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", v))
                for v in first_nonblank
            )
            second_has_data_signal = any(
                bool(re.search(r"\d", v)) or bool(re.search(r"[-/:]", v))
                for v in second_nonblank
            )
            if first_is_schema and second_has_data_signal:
                return 0
    candidates: list[tuple[float, int]] = []
    for i in range(limit):
        row = raw.iloc[i]
        score = _header_score(row)
        nonblank = [_normalise_text(v) for v in row.tolist() if _normalise_text(v)]
        if not nonblank:
            continue
        next_rows = raw.iloc[i + 1:min(i + 4, len(raw))]
        if not next_rows.empty:
            populated = next_rows.notna().sum(axis=1)
            consistency = float((populated >= max(1, int(len(nonblank) * 0.5))).mean())
            score += consistency * 2.5
            if any(
                bool(re.search(r"\d", _normalise_text(v)))
                or bool(re.search(r"[-/:]", _normalise_text(v)))
                for v in next_rows.astype(object).to_numpy().ravel()
                if _normalise_text(v)
            ):
                score += 1.0
        # Standalone report titles should lose to a row that explains the table
        # schema and is followed by actual records.
        if len(nonblank) <= 2 and i + 1 < len(raw):
            score -= 1.5
        candidates.append((score, i))
    candidates.sort(reverse=True)
    return candidates[0][1] if candidates else 0


def build_ultimate_workbook(
    title: str,
    sheets: dict[str, pd.DataFrame],
    raw_sheets: dict[str, pd.DataFrame],
    audits: dict[str, list[dict[str, str]]],
    profiles: dict[str, dict[str, Any]],
    *,
    source_metadata: list[dict[str, Any]] | None = None,
    field_intelligence: list[dict[str, Any]] | None = None,
    review_register: list[dict[str, Any]] | None = None,
    before_after: list[dict[str, Any]] | None = None,
    formula_inventory: list[dict[str, Any]] | None = None,
    cross_sheet_map: list[dict[str, Any]] | None = None,
) -> bytes:
    source_metadata = source_metadata or []
    field_intelligence = field_intelligence or []
    review_register = review_register or []
    before_after = before_after or []
    formula_inventory = formula_inventory or []
    cross_sheet_map = cross_sheet_map or []

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm", date_format="yyyy-mm-dd") as writer:
        workbook = writer.book
        workbook.set_properties({
            "title": title,
            "subject": "Shoir-IE Industrial Excel Intelligence Workbook",
            "author": "Shoir-IE",
            "comments": "Traceable workbook generated by Shoir-IE Excel Intelligence & Data Governance.",
        })
        navy = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#163A5F", "border": 0})
        teal = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#0F766E"})
        title_fmt = workbook.add_format({"bold": True, "font_size": 20, "font_color": "#163A5F"})
        subtitle_fmt = workbook.add_format({"font_color": "#4B6175", "italic": True})
        section_fmt = workbook.add_format({"bold": True, "font_size": 12, "font_color": "#163A5F"})
        note_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})
        kpi_label_fmt = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#163A5F", "align": "center"})
        kpi_value_fmt = workbook.add_format({"bold": True, "font_size": 16, "font_color": "#163A5F", "align": "center", "border": 1, "border_color": "#D7E2EA"})
        high_fmt = workbook.add_format({"bold": True, "font_color": "#991B1B", "bg_color": "#FEE2E2"})
        medium_fmt = workbook.add_format({"bold": True, "font_color": "#92400E", "bg_color": "#FEF3C7"})
        low_fmt = workbook.add_format({"font_color": "#166534", "bg_color": "#DCFCE7"})
        number_fmt = workbook.add_format({"num_format": "#,##0.00"})
        integer_fmt = workbook.add_format({"num_format": "#,##0"})
        percent_fmt = workbook.add_format({"num_format": "0.0%"})
        date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})
        datetime_fmt = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})
        code_fmt = workbook.add_format({"font_name": "Consolas", "text_wrap": True})
        used: set[str] = set()
        table_names: set[str] = set()
        clean_names: dict[str, str] = {}
        raw_names: dict[str, str] = {}

        start = workbook.add_worksheet("START HERE"); used.add("START HERE"); start.hide_gridlines(2); start.set_tab_color("#163A5F")
        start.set_column("A:A", 32); start.set_column("B:B", 82); start.set_column("C:C", 24)
        start.write("A1", "Shoir-IE · Industrial Excel Intelligence Workbook", title_fmt)
        start.write("A2", title, subtitle_fmt)
        start.write("A4", "Navigation", section_fmt)
        start.write_row("A5", ["Sheet", "Purpose", "Status"], navy)
        nav = [
            ("EXECUTIVE DASHBOARD", "Management-ready health, readiness and workbook KPIs."),
            ("DATA QUALITY CENTER", "Sheet-level quality, missingness, duplicate and outlier intelligence."),
            ("FIELD INTELLIGENCE", "Field roles, type confidence, units, canonical entities and recommended actions."),
            ("VALIDATION & REVIEW", "Actionable review register; nothing is silently deleted as an 'outlier'."),
            ("BEFORE vs AFTER", "What changed between source and cleaned working data."),
            ("SOURCE METADATA", "File hash, source sheet structure, detected headers and formula provenance."),
            ("CLEANING AUDIT", "Exact automatic transformations applied."),
        ]
        if formula_inventory:
            nav.append(("FORMULA INVENTORY", "Source formulas archived as inert evidence for traceability."))
        if cross_sheet_map:
            nav.append(("CROSS-SHEET MAP", "Potential shared fields that could support controlled joins."))
        row = 5
        for fixed_name, purpose in nav:
            start.write_url(row, 0, f"internal:'{fixed_name}'!A1", string=fixed_name)
            start.write(row, 1, purpose)
            row += 1
        for original in sheets:
            clean_name = _safe_sheet(original, used, "CLEAN - ")
            raw_name = _safe_sheet(original, used, "RAW - ")
            clean_names[original] = clean_name; raw_names[original] = raw_name
            start.write_url(row, 0, f"internal:'{clean_name}'!A1", string=clean_name)
            start.write(row, 1, f"Primary cleaned working table from source sheet '{original}'.")
            start.write(row, 2, profiles.get(original, {}).get("Readiness", "—"))
            row += 1
        start.write(row + 1, 0, "Governance principle", section_fmt)
        start.merge_range(row + 2, 0, row + 4, 1,
            "Shoir-IE separates working data from evidence. CLEAN sheets are the analysis-ready tables; "
            "RAW sheets preserve source values; SOURCE METADATA proves where the import came from; "
            "VALIDATION & REVIEW identifies issues without silently changing the analyst's intent.",
            note_fmt)

        summary = workbook.add_worksheet("EXECUTIVE DASHBOARD"); used.add("EXECUTIVE DASHBOARD"); summary.hide_gridlines(2); summary.set_tab_color("#0F766E")
        summary.set_column("A:A", 28); summary.set_column("B:I", 18)
        summary.write("A1", "EXECUTIVE DASHBOARD", title_fmt)
        summary.write("A2", "Decision-ready view of the imported workbook.", subtitle_fmt)
        avg_quality = round(float(np.mean([p["Quality score"] for p in profiles.values()])) if profiles else 0.0, 1)
        total_rows = sum(int(p.get("Rows", 0)) for p in profiles.values())
        total_missing = sum(int(p.get("Missing cells", 0)) for p in profiles.values())
        review_high = sum(1 for x in review_register if x.get("Severity") == "High")
        kpis = [("SOURCE SHEETS", len(sheets)), ("CLEANED ROWS", total_rows), ("FIELDS", sum(int(p.get("Columns", 0)) for p in profiles.values())), ("AVG QUALITY", f"{avg_quality:.1f}%"), ("MISSING CELLS", total_missing), ("REVIEW ITEMS", len(review_register)), ("HIGH PRIORITY", review_high), ("SOURCE HASHED", "YES")]
        for i, (label, value) in enumerate(kpis):
            c = i % 4; r = 4 + (i // 4) * 3
            summary.merge_range(r, c * 2, r, c * 2 + 1, label, kpi_label_fmt)
            summary.merge_range(r + 1, c * 2, r + 1, c * 2 + 1, value, kpi_value_fmt)
        summary.write("A11", "Sheet readiness", section_fmt)
        readiness = pd.DataFrame([
            {
                "Sheet": _safe_sheet(k, set(), "CLEAN - "),
                "Rows": v.get("Rows", 0), "Fields": v.get("Columns", 0),
                "Missing %": v.get("Missing %", 0), "Duplicate rows": v.get("Duplicate rows", 0),
                "Potential outliers": v.get("Potential outliers", 0),
                "Review items": v.get("Review items", 0),
                "Quality": v.get("Quality score", 0), "Readiness": v.get("Readiness", "—"),
            }
            for k, v in profiles.items()
        ])
        _safe_write_frame(summary, readiness, 11, 0, navy, date_fmt, datetime_fmt, number_fmt)
        summary.freeze_panes(12, 0)
        if not readiness.empty:
            chart = workbook.add_chart({"type": "column"})
            chart.add_series({"name": "Quality score", "categories": ["EXECUTIVE DASHBOARD", 12, 0, 11 + len(readiness), 0], "values": ["EXECUTIVE DASHBOARD", 12, 7, 11 + len(readiness), 7]})
            chart.set_title({"name": "Quality/readiness profile"}); chart.set_y_axis({"min": 0, "max": 100}); chart.set_size({"width": 760, "height": 340})
            summary.insert_chart("A24", chart)

        quality = workbook.add_worksheet("DATA QUALITY CENTER"); used.add("DATA QUALITY CENTER"); quality.hide_gridlines(2); quality.set_tab_color("#B45309")
        quality.write("A1", "DATA QUALITY CENTER", title_fmt)
        quality.write("A2", "Automated evidence checks. Scores are readiness heuristics, not a substitute for engineering judgment.", subtitle_fmt)
        qframe = readiness.copy()
        _safe_write_frame(quality, qframe, 3, 0, navy, date_fmt, datetime_fmt, number_fmt)
        if not qframe.empty:
            quality.autofilter(3, 0, 3 + len(qframe), max(0, len(qframe.columns) - 1))
        quality.write("A16", "Review workload by severity", section_fmt)
        severity = pd.DataFrame([{"Severity": s, "Count": sum(1 for x in review_register if x.get("Severity") == s)} for s in ["High", "Medium", "Low"]])
        _safe_write_frame(quality, severity, 17, 0, navy, date_fmt, datetime_fmt, number_fmt)
        if not severity.empty:
            chart = workbook.add_chart({"type": "bar"})
            chart.add_series({"name": "Review items", "categories": ["DATA QUALITY CENTER", 18, 0, 17 + len(severity), 0], "values": ["DATA QUALITY CENTER", 18, 1, 17 + len(severity), 1]})
            chart.set_title({"name": "Review workload by severity"}); chart.set_size({"width": 540, "height": 260}); quality.insert_chart("D17", chart)

        fields = workbook.add_worksheet("FIELD INTELLIGENCE"); used.add("FIELD INTELLIGENCE"); fields.hide_gridlines(2); fields.set_tab_color("#7C3AED")
        fields.write("A1", "FIELD INTELLIGENCE", title_fmt)
        fields.write("A2", "Semantic profiling for engineering analysis, joins and the Digital Thread.", subtitle_fmt)
        fframe = pd.DataFrame(field_intelligence)
        if fframe.empty:
            fframe = pd.DataFrame([{"Sheet": "", "Field": "", "Role": "", "Inferred type": "", "Type confidence": "", "Canonical entity": "", "Unit hint": "", "Rows": 0, "Non-null": 0, "Missing %": 100.0, "Unique": 0, "Potential outliers": 0, "Example values": "", "Suggested action": "No fields detected."}])
        _safe_write_frame(fields, fframe, 3, 0, navy, date_fmt, datetime_fmt, number_fmt)
        fields.freeze_panes(4, 0); fields.autofilter(3, 0, 3 + len(fframe), len(fframe.columns) - 1)
        fields.set_column("A:B", 24); fields.set_column("C:G", 18); fields.set_column("H:N", 20); fields.set_column("O:O", 48)
        type_counts = fframe["Inferred type"].value_counts().reset_index()
        type_counts.columns = ["Type", "Count"]
        if not type_counts.empty:
            chart = workbook.add_chart({"type": "doughnut"})
            chart.add_series({"name": "Field types", "categories": ["FIELD INTELLIGENCE", 4 + len(fframe), 0, 3 + len(fframe) + len(type_counts), 0], "values": ["FIELD INTELLIGENCE", 4 + len(fframe), 1, 3 + len(fframe) + len(type_counts), 1]})
            _safe_write_frame(fields, type_counts, 4 + len(fframe), 0, navy, date_fmt, datetime_fmt, number_fmt)
            chart.set_title({"name": "Field type mix"}); chart.set_size({"width": 460, "height": 280}); fields.insert_chart("Q4", chart)

        review = workbook.add_worksheet("VALIDATION & REVIEW"); used.add("VALIDATION & REVIEW"); review.hide_gridlines(2); review.set_tab_color("#DC2626")
        review.write("A1", "VALIDATION & REVIEW", title_fmt)
        review.write("A2", "Review flags are explicit. Shoir-IE does not silently delete statistical outliers or semantic anomalies.", subtitle_fmt)
        rframe = pd.DataFrame(review_register)
        if rframe.empty:
            rframe = pd.DataFrame([{"Severity": "Info", "Sheet": "—", "Field": "—", "Issue": "No review flags", "Evidence": "No automated exception was detected.", "Recommended action": "Proceed with normal engineering validation."}])
        _safe_write_frame(review, rframe, 3, 0, navy, date_fmt, datetime_fmt, number_fmt)
        review.freeze_panes(4, 0); review.autofilter(3, 0, 3 + len(rframe), len(rframe.columns) - 1)
        if "Severity" in rframe.columns:
            review.conditional_format(4, 0, 3 + len(rframe), 0, {"type": "text", "criteria": "containing", "value": "High", "format": high_fmt})
            review.conditional_format(4, 0, 3 + len(rframe), 0, {"type": "text", "criteria": "containing", "value": "Medium", "format": medium_fmt})
            review.conditional_format(4, 0, 3 + len(rframe), 0, {"type": "text", "criteria": "containing", "value": "Low", "format": low_fmt})
        review.set_column("A:A", 12); review.set_column("B:C", 25); review.set_column("D:D", 32); review.set_column("E:F", 68)

        before = workbook.add_worksheet("BEFORE vs AFTER"); used.add("BEFORE vs AFTER"); before.hide_gridlines(2)
        before.write("A1", "BEFORE vs AFTER", title_fmt); before.write("A2", "How much changed, and what happened to the data shape.", subtitle_fmt)
        baframe = pd.DataFrame(before_after)
        if baframe.empty:
            baframe = pd.DataFrame([{"Sheet": "—", "Source rows": 0, "Clean rows": 0, "Rows removed": 0, "Source columns": 0, "Clean columns": 0, "Columns removed": 0, "Missing before": 0, "Missing after": 0, "Duplicate rows removed": 0, "Schema fingerprint": "—"}])
        _safe_write_frame(before, baframe, 3, 0, navy, date_fmt, datetime_fmt, number_fmt)
        before.freeze_panes(4, 0)
        before.set_column("A:A", 28); before.set_column("B:K", 18)

        meta = workbook.add_worksheet("SOURCE METADATA"); used.add("SOURCE METADATA"); meta.hide_gridlines(2)
        meta.write("A1", "SOURCE METADATA", title_fmt); meta.write("A2", "Import provenance and source-structure facts.", subtitle_fmt)
        mframe = pd.DataFrame(source_metadata)
        _safe_write_frame(meta, mframe, 3, 0, navy, date_fmt, datetime_fmt, number_fmt)
        meta.freeze_panes(4, 0); meta.set_column("A:A", 28); meta.set_column("B:B", 68); meta.set_column("C:Z", 18)
        meta.write("A" + str(max(6, 5 + len(mframe))), "Source hash principle: the SHA256 identifies the exact uploaded byte payload used for this workbook.", code_fmt)

        audit = workbook.add_worksheet("CLEANING AUDIT"); used.add("CLEANING AUDIT"); audit.hide_gridlines(2)
        audit.write("A1", "CLEANING AUDIT", title_fmt); audit.write("A2", "Every automated transformation is recorded for reproducibility.", subtitle_fmt)
        audit_rows = [{"Sheet": k, **event} for k, events in audits.items() for event in events]
        if not audit_rows:
            audit_rows = [{"Sheet": "", "Action": "No changes required", "Details": "The source workbook already satisfied the automatic cleaning rules."}]
        aframe = pd.DataFrame(audit_rows)
        _safe_write_frame(audit, aframe, 3, 0, navy, date_fmt, datetime_fmt, number_fmt)
        audit.freeze_panes(4, 0); audit.set_column("A:A", 28); audit.set_column("B:B", 34); audit.set_column("C:C", 100)

        if formula_inventory:
            finv = workbook.add_worksheet("FORMULA INVENTORY"); used.add("FORMULA INVENTORY"); finv.hide_gridlines(2)
            finv.write("A1", "FORMULA INVENTORY", title_fmt)
            finv.write("A2", "Inert source-formula evidence. Formula text is retained as evidence and is not executed during import.", subtitle_fmt)
            frame = pd.DataFrame(formula_inventory)
            _safe_write_frame(finv, frame, 3, 0, navy, date_fmt, datetime_fmt, number_fmt)
            finv.freeze_panes(4, 0); finv.set_column("A:B", 24); finv.set_column("C:C", 72); finv.set_column("D:E", 32)

        if cross_sheet_map:
            cmap = workbook.add_worksheet("CROSS-SHEET MAP"); used.add("CROSS-SHEET MAP"); cmap.hide_gridlines(2)
            cmap.write("A1", "CROSS-SHEET MAP", title_fmt)
            cmap.write("A2", "Potential shared fields for controlled joins. Shared names do not prove referential integrity.", subtitle_fmt)
            frame = pd.DataFrame(cross_sheet_map)
            _safe_write_frame(cmap, frame, 3, 0, navy, date_fmt, datetime_fmt, number_fmt)
            cmap.freeze_panes(4, 0); cmap.set_column("A:B", 28); cmap.set_column("C:C", 50); cmap.set_column("D:D", 18); cmap.set_column("E:E", 72)

        for original, df in sheets.items():
            clean_name = clean_names[original]; raw_name = raw_names[original]
            ws = workbook.add_worksheet(clean_name); ws.hide_gridlines(2); ws.freeze_panes(6, 0); ws.set_tab_color("#2F6B8A")
            profile = profiles[original]
            ws.set_column("A:A", 24)
            ws.write_url("A1", "internal:'START HERE'!A1", string="← Back to START HERE")
            ws.write("A2", f"{clean_name} — {original}", title_fmt)
            ws.write("A3", f"Readiness: {profile.get('Readiness','—')} | Quality: {profile.get('Quality score',0):.1f}% | Schema: {profile.get('Schema fingerprint','—')}", subtitle_fmt)
            ws.write("A5", "CLEAN WORKING DATA", section_fmt)
            _safe_write_frame(ws, df, 5, 0, navy, date_fmt, datetime_fmt, number_fmt)
            if len(df.columns) and len(df):
                try:
                    end_row = 5 + len(df)
                    ws.add_table(5, 0, end_row, len(df.columns) - 1, {
                        "name": _safe_table_name(clean_name, table_names),
                        "style": "Table Style Medium 2",
                        "columns": [{"header": str(c)} for c in df.columns],
                    })
                    ws.autofilter(5, 0, end_row, len(df.columns) - 1)
                except Exception:
                    pass
            for j, col in enumerate(df.columns):
                sample = [str(x) for x in df[col].head(80).tolist()]
                width = min(46, max(12, len(str(col)) + 2, max([len(x) for x in sample] + [0]) + 2))
                ws.set_column(j, j, width)
                if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
                    ws.conditional_format(6, j, max(6, 5 + len(df)), j, {"type": "3_color_scale", "min_color": "#FEE2E2", "mid_color": "#FEF3C7", "max_color": "#DCFCE7"})
            issues = [x for x in review_register if x.get("Sheet") == original]
            if issues:
                ws.write("A4", f"Review flags: {len(issues)} · see VALIDATION & REVIEW", medium_fmt if any(x.get("Severity") == "High" for x in issues) else subtitle_fmt)
            raw_ws = workbook.add_worksheet(raw_name); raw_ws.hide(); raw_ws.write("A1", f"RAW ARCHIVE — {original}", title_fmt)
            _safe_write_frame(raw_ws, raw_sheets.get(original, pd.DataFrame()), 2, 0, navy, date_fmt, datetime_fmt, number_fmt)

            numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
            if numeric and len(df) >= 2:
                y = numeric[0]; y_idx = list(df.columns).index(y)
                x = next((c for c in df.columns if c != y and (pd.api.types.is_datetime64_any_dtype(df[c]) or not pd.api.types.is_numeric_dtype(df[c]))), None)
                if x is not None:
                    x_idx = list(df.columns).index(x)
                    chart = workbook.add_chart({"type": "line" if pd.api.types.is_datetime64_any_dtype(df[x]) else "column"})
                    chart.add_series({"name": [clean_name, 5, y_idx], "categories": [clean_name, 6, x_idx, 5 + len(df), x_idx], "values": [clean_name, 6, y_idx, 5 + len(df), y_idx]})
                    chart.set_title({"name": f"{y} by {x}"}); chart.set_legend({"none": True}); chart.set_size({"width": 720, "height": 330})
                    ws.insert_chart("A" + str(8), chart)

        # Backward-compatible aliases for downstream consumers that still look
        # for the original workbook sheet names.
        for legacy_name, target, description in [
            ("EXECUTIVE SUMMARY", "EXECUTIVE DASHBOARD", "Legacy navigation alias. Use EXECUTIVE DASHBOARD for the full view."),
            ("DATA DICTIONARY", "FIELD INTELLIGENCE", "Legacy navigation alias. Use FIELD INTELLIGENCE for richer field profiling."),
            ("QUALITY CHECKS", "DATA QUALITY CENTER", "Legacy navigation alias. Use DATA QUALITY CENTER for the governed quality view."),
        ]:
            if legacy_name not in used:
                legacy = workbook.add_worksheet(legacy_name)
                used.add(legacy_name)
                legacy.hide_gridlines(2)
                legacy.write("A1", legacy_name, title_fmt)
                legacy.write("A3", description, subtitle_fmt)
                legacy.write_url("A5", f"internal:'{target}'!A1", string=f"Open {target}")
                legacy.set_column("A:A", 72)

    return buf.getvalue()


def build_ultimate_bundle(
    title: str,
    xlsx_bytes: bytes,
    audits: dict[str, list[dict[str, str]]],
    profiles: dict[str, dict[str, Any]],
    *,
    cleaned_sheets: dict[str, pd.DataFrame] | None = None,
    raw_sheets: dict[str, pd.DataFrame] | None = None,
    field_intelligence: list[dict[str, Any]] | None = None,
    review_register: list[dict[str, Any]] | None = None,
    source_metadata: list[dict[str, Any]] | None = None,
) -> bytes:
    cleaned_sheets = cleaned_sheets or {}
    raw_sheets = raw_sheets or {}
    field_intelligence = field_intelligence or []
    review_register = review_register or []
    source_metadata = source_metadata or []
    manifest = {
        "product": "Shoir-IE Excel Intelligence Studio",
        "title": title,
        "workbook_hash": hashlib.sha256(xlsx_bytes).hexdigest(),
        "source_sheets": list(raw_sheets),
        "cleaned_sheets": list(cleaned_sheets),
        "profiles": profiles,
        "quality_review_items": len(review_register),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("shoir_ie_industrial_excel_workbook.xlsx", xlsx_bytes)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.writestr("cleaning_audit.json", json.dumps(audits, indent=2, ensure_ascii=False))
        zf.writestr("quality_profiles.json", json.dumps(profiles, indent=2, ensure_ascii=False))
        zf.writestr("field_intelligence.csv", pd.DataFrame(field_intelligence).to_csv(index=False))
        zf.writestr("validation_review.csv", pd.DataFrame(review_register).to_csv(index=False))
        zf.writestr("source_metadata.csv", pd.DataFrame(source_metadata).to_csv(index=False))
        for name, frame in cleaned_sheets.items():
            safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name)).strip("_") or "sheet"
            zf.writestr(f"clean_csv/{safe}.csv", frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S"))
        for name, frame in raw_sheets.items():
            safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name)).strip("_") or "sheet"
            zf.writestr(f"raw_csv/{safe}.csv", frame.to_csv(index=False))
        zf.writestr("README.txt", (
            f"{title}\n\n"
            "This package contains a presentation-ready XLSX plus machine-readable evidence files.\n"
            "CLEAN sheets are the working tables. RAW sheets and source metadata preserve provenance. "
            "Validation flags are review prompts, not automatic deletions. Source formulas, when detected, "
            "are archived as inert evidence in FORMULA INVENTORY.\n"
        ))
    return buf.getvalue()


def process_uploaded_workbook(raw: bytes, filename: str) -> dict[str, Any]:
    signature = hashlib.sha256(raw).hexdigest()
    raw_sheets = _read_raw_workbook(raw, filename)
    cleaned: dict[str, pd.DataFrame] = {}
    audits: dict[str, list[dict[str, str]]] = {}
    profiles: dict[str, dict[str, Any]] = {}
    fields: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    before_after: list[dict[str, Any]] = []
    header_rows: dict[str, int] = {}

    for source_name, raw_df in raw_sheets.items():
        header_row = _enhanced_detect_header_row(raw_df)
        # Tiny CSV exports are especially easy to mis-rank: if the detector
        # selects the final row there is no body left, so prefer a valid first
        # schema row when it contains multiple label-like fields.
        if str(filename).lower().endswith(".csv") and len(raw_df) >= 2 and header_row >= len(raw_df) - 1:
            first = [_normalise_text(v) for v in raw_df.iloc[0].tolist() if _normalise_text(v)]
            if len(first) >= 2 and sum(bool(re.search(r"[A-Za-z]", v)) for v in first) >= max(2, len(first) - 1):
                header_row = 0
        header_rows[source_name] = header_row
        if raw_df.empty:
            table = pd.DataFrame()
        else:
            headers = _deduplicate_headers(raw_df.iloc[header_row].tolist())
            table = raw_df.iloc[header_row + 1:].copy()
            table.columns = headers
            table = table.dropna(axis=1, how="all").dropna(axis=0, how="all")
        cleaned_df, audit = _enhanced_clean_dataframe(table)
        cleaned[source_name] = cleaned_df
        audits[source_name] = [{"Action": "Detect table header", "Details": f"Detected source header row {header_row + 1}."}] + audit
        profiles[source_name] = _enhanced_profile_dataframe(cleaned_df)
        fields.extend(_field_intelligence_rows(cleaned_df, source_name))
        reviews.extend(_quality_review_register(cleaned_df, source_name))
        before_after.append({
            "Sheet": source_name,
            "Source rows": int(len(table)),
            "Clean rows": int(len(cleaned_df)),
            "Rows removed": int(max(0, len(table) - len(cleaned_df))),
            "Source columns": int(len(table.columns)),
            "Clean columns": int(len(cleaned_df.columns)),
            "Columns removed": int(max(0, len(table.columns) - len(cleaned_df.columns))),
            "Missing before": int(table.isna().sum().sum()) if not table.empty else 0,
            "Missing after": int(cleaned_df.isna().sum().sum()) if not cleaned_df.empty else 0,
            "Duplicate rows removed": max(0, int(table.duplicated().sum()) - int(cleaned_df.duplicated().sum())) if not table.empty else 0,
            "Schema fingerprint": profiles[source_name].get("Schema fingerprint", "—"),
        })

    source_metadata, formula_inventory = _extract_source_metadata(raw, filename, raw_sheets, header_rows)
    cross_map = _cross_sheet_map(cleaned)
    workbook_title = f"Shoir-IE — {filename}"
    xlsx = build_ultimate_workbook(
        workbook_title, cleaned, raw_sheets, audits, profiles,
        source_metadata=source_metadata,
        field_intelligence=fields,
        review_register=reviews,
        before_after=before_after,
        formula_inventory=formula_inventory,
        cross_sheet_map=cross_map,
    )
    return {
        "signature": signature,
        "filename": filename,
        "raw_sheets": raw_sheets,
        "cleaned_sheets": cleaned,
        "audits": audits,
        "profiles": profiles,
        "field_intelligence": fields,
        "review_register": reviews,
        "before_after": before_after,
        "source_metadata": source_metadata,
        "formula_inventory": formula_inventory,
        "cross_sheet_map": cross_map,
        "xlsx": xlsx,
        "bundle": build_ultimate_bundle(
            workbook_title, xlsx, audits, profiles,
            cleaned_sheets=cleaned,
            raw_sheets=raw_sheets,
            field_intelligence=fields,
            review_register=reviews,
            source_metadata=source_metadata,
        ),
    }


def render_excel_data_cleaning_studio(tier: str, username: str) -> None:
    import streamlit as st
    from shoir_tier_capabilities import tier_allows

    if not tier_allows(tier, "Starter"):
        st.warning("This workspace is not included in your current package.")
        return

    st.markdown("## 📊 Excel Intelligence & Data Cleaning Studio")
    st.caption(
        "Import → profile → clean → validate → map → review → analyze → export. "
        "Shoir-IE preserves raw evidence and creates a governed industrial workbook."
    )
    with st.expander("What Shoir-IE checks automatically", expanded=False):
        st.write("Headers, duplicate columns/rows, identifier preservation, missing-value tokens, accounting negatives, data types, identifier uniqueness, statistical outliers, percentage/ratio ranges, date sanity, source formulas, schema fingerprint, cross-sheet shared fields and provenance hash.")

    left, right = st.columns([5, 1])
    upload = left.file_uploader(
        "Upload raw Excel / CSV",
        type=["xlsx", "xlsm", "csv"],
        key="excel_studio_upload",
        help="Messy exports, title rows and multi-sheet Excel workbooks are supported.",
    )
    if right.button("Clear", use_container_width=True, key="excel_studio_clear"):
        for key in ["excel_studio_signature", "excel_studio_result", "excel_studio_sheet", "excel_studio_visual_df"]:
            st.session_state.pop(key, None)
        st.rerun()

    if upload is not None:
        raw = upload.getvalue()
        signature = hashlib.sha256(raw).hexdigest()
        if st.session_state.get("excel_studio_signature") != signature:
            try:
                with st.spinner("Building governed industrial workbook…"):
                    result = process_uploaded_workbook(raw, upload.name)
                st.session_state["excel_studio_signature"] = signature
                st.session_state["excel_studio_result"] = result
                st.success(
                    f"✅ Processed {len(result['cleaned_sheets']):,} sheet(s), "
                    f"flagged {len(result['review_register']):,} review item(s), and preserved the source hash."
                )
            except Exception as exc:
                st.error(f"Excel could not be transformed safely: {type(exc).__name__}: {exc}")

    result = st.session_state.get("excel_studio_result")
    if not isinstance(result, dict):
        st.info("Upload a workbook to activate the governed Excel workflow.")
        return

    cleaned = result["cleaned_sheets"]
    profiles = result["profiles"]
    audits = result["audits"]
    profile_frame = pd.DataFrame([{"Sheet": k, **v} for k, v in profiles.items()])
    if cleaned:
        selected = st.session_state.get("excel_studio_sheet")
        if selected not in cleaned:
            selected = next(iter(cleaned))
        st.session_state["excel_studio_visual_df"] = cleaned[selected].copy(deep=True)

    scores = [float(v.get("Quality score", 0)) for v in profiles.values()]
    high_reviews = sum(1 for x in result.get("review_register", []) if x.get("Severity") == "High")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Sheets", len(cleaned))
    m2.metric("Clean rows", f"{sum(len(v) for v in cleaned.values()):,}")
    m3.metric("Avg quality", f"{float(np.mean(scores)):.1f}%" if scores else "—")
    m4.metric("Review items", f"{len(result.get('review_register', [])):,}")
    m5.metric("High priority", high_reviews)

    tabs = st.tabs(["Overview", "Clean Data", "Quality Center", "Field Intelligence", "Governance", "Export"])

    with tabs[0]:
        st.dataframe(profile_frame, use_container_width=True, hide_index=True)
        st.markdown("### Before vs after")
        st.dataframe(pd.DataFrame(result.get("before_after", [])), use_container_width=True, hide_index=True)
        st.markdown("### Source provenance")
        st.dataframe(pd.DataFrame(result.get("source_metadata", [])), use_container_width=True, hide_index=True)
        if result.get("cross_sheet_map"):
            st.markdown("### Potential cross-sheet relationships")
            st.dataframe(pd.DataFrame(result["cross_sheet_map"]), use_container_width=True, hide_index=True)
        if result.get("module_readiness"):
            st.markdown("### Recommended Shoir-IE workflows")
            st.dataframe(pd.DataFrame(result["module_readiness"]), use_container_width=True, hide_index=True)

    with tabs[1]:
        sheet = st.selectbox("Clean sheet", list(cleaned), key="excel_studio_sheet")
        df = cleaned[sheet]
        st.session_state["excel_studio_visual_df"] = df.copy(deep=True)
        profile = profiles[sheet]
        st.caption(f"{sheet} · {len(df):,} rows × {len(df.columns):,} fields · {profile.get('Readiness','—')} · schema {profile.get('Schema fingerprint','—')}")
        st.dataframe(df.head(1500), use_container_width=True, hide_index=True)
        sheet_reviews = [x for x in result.get("review_register", []) if x.get("Sheet") == sheet]
        if sheet_reviews:
            st.markdown("#### Review flags for this sheet")
            st.dataframe(pd.DataFrame(sheet_reviews), use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        if c1.button("↻ Re-run cleaning", key="excel_studio_reclean", use_container_width=True):
            cleaned_df, new_audit = clean_dataframe(df)
            result["cleaned_sheets"][sheet] = cleaned_df
            result["audits"][sheet].extend(new_audit)
            result["profiles"][sheet] = _enhanced_profile_dataframe(cleaned_df)
            result["field_intelligence"] = [x for x in result["field_intelligence"] if x.get("Sheet") != sheet] + _field_intelligence_rows(cleaned_df, sheet)
            _refresh_excel_governance(result)
            result["xlsx"] = build_ultimate_workbook(
                f"Shoir-IE — {result['filename']}", result["cleaned_sheets"], result["raw_sheets"], result["audits"], result["profiles"],
                source_metadata=result.get("source_metadata"), field_intelligence=result.get("field_intelligence"),
                review_register=result.get("review_register"), before_after=result.get("before_after"),
                formula_inventory=result.get("formula_inventory"), cross_sheet_map=result.get("cross_sheet_map"),
            )
            result["bundle"] = build_ultimate_bundle(
                f"Shoir-IE — {result['filename']}", result["xlsx"], result["audits"], result["profiles"],
                cleaned_sheets=result["cleaned_sheets"], raw_sheets=result["raw_sheets"],
                field_intelligence=result["field_intelligence"], review_register=result["review_register"],
                source_metadata=result.get("source_metadata"),
            )
            st.session_state["excel_studio_result"] = result
            st.rerun()
        if c2.button("↩ Restore from preserved RAW", key="excel_studio_restore", use_container_width=True):
            raw_df = result["raw_sheets"][sheet]
            meta_by_sheet = {str(m.get("Source sheet", "")): m for m in result.get("source_metadata", [])}
            header_row = int(meta_by_sheet.get(sheet, {}).get("Detected header row", 1)) - 1 if meta_by_sheet.get(sheet) else detect_header_row(raw_df)
            header_row = max(0, min(header_row, max(0, len(raw_df) - 1)))
            table = raw_df.iloc[header_row + 1:].copy()
            table.columns = _deduplicate_headers(raw_df.iloc[header_row].tolist())
            table = table.dropna(axis=1, how="all").dropna(axis=0, how="all")
            restored, restore_audit = _enhanced_clean_dataframe(table)
            result["cleaned_sheets"][sheet] = restored
            result["audits"][sheet] = [{"Action": "Restore", "Details": "Restored from preserved RAW values and re-applied governed cleaning."}] + restore_audit
            result["profiles"][sheet] = _enhanced_profile_dataframe(restored)
            result["field_intelligence"] = [x for x in result.get("field_intelligence", []) if x.get("Sheet") != sheet] + _field_intelligence_rows(restored, sheet)
            _refresh_excel_governance(result)
            st.session_state["excel_studio_result"] = result
            st.rerun()

    with tabs[2]:
        review_frame = pd.DataFrame(result.get("review_register", []))
        if review_frame.empty:
            st.success("No automated review exceptions detected.")
        else:
            st.dataframe(review_frame, use_container_width=True, hide_index=True)
            counts = review_frame["Severity"].value_counts().rename_axis("Severity").reset_index(name="Count")
            st.dataframe(counts, use_container_width=True, hide_index=True)
        st.caption("Potential outliers are flagged for review; Shoir-IE does not delete them automatically.")

    with tabs[3]:
        field_frame = pd.DataFrame(result.get("field_intelligence", []))
        st.dataframe(field_frame, use_container_width=True, hide_index=True)
        if result.get("formula_inventory"):
            with st.expander("Source formula inventory"):
                st.dataframe(pd.DataFrame(result["formula_inventory"]), use_container_width=True, hide_index=True)

    with tabs[4]:
        st.markdown("### Governance intelligence")
        governance_sets = [("Data contract", "data_contract"), ("Relationship integrity", "relationship_integrity"), ("Potential duplicate candidates", "duplicate_candidates"), ("Privacy scan", "privacy_scan"), ("Formula quality", "formula_quality")]
        for label, key in governance_sets:
            st.markdown("#### " + label)
            st.dataframe(pd.DataFrame(result.get(key, [])), use_container_width=True, hide_index=True)
        st.markdown("#### Cleaning recipe")
        st.dataframe(pd.DataFrame([{"Rule": a, "Behavior": b, "Mode": c, "Reason": d} for a, b, c, d in _CLEAN_RECIPE]), use_container_width=True, hide_index=True)
        st.caption("Privacy scanning reports indicators and counts only; raw sensitive values are never copied into governance tables.")

    with tabs[5]:
        safe_name = re.sub(r"[^A-Za-z0-9]+", "_", result["filename"]).strip("_").lower()
        st.download_button(
            "📥 Download Industrial Excel Intelligence Workbook",
            result["xlsx"],
            file_name=f"shoir_ie_industrial_{safe_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
        st.download_button(
            "📦 Download Complete Evidence Package",
            result["bundle"],
            file_name=f"shoir_ie_industrial_{safe_name}.zip",
            mime="application/zip",
            use_container_width=True,
        )


# Final symbol bindings for backward compatibility with imports/tests.
clean_dataframe = _enhanced_clean_dataframe
profile_dataframe = _enhanced_profile_dataframe
detect_header_row = _enhanced_detect_header_row



# Final ingestion hardening: locale-safe CSV, duration-safe typing and
# multi-table provenance review. These overrides keep the public API stable.

def _enhanced_read_raw_workbook(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    if not raw:
        raise ValueError("The uploaded file is empty.")
    lower = str(filename).lower()
    if lower.endswith(".csv"):
        import csv
        decoded = None
        chosen_encoding = "utf-8-sig"
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = raw.decode(encoding)
                chosen_encoding = encoding
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("CSV encoding could not be decoded safely.")
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(decoded[:8192], delimiters=",;\t|")
            delimiter = dialect.delimiter
        except Exception:
            pass
        return {
            "CSV": pd.read_csv(
                io.StringIO(decoded),
                header=None,
                dtype=object,
                sep=delimiter,
                keep_default_na=False,
            )
        }
    if lower.endswith((".xlsx", ".xlsm")):
        book = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
        return {
            str(sheet): pd.read_excel(book, sheet_name=sheet, header=None, dtype=object)
            for sheet in book.sheet_names
        }
    raise ValueError("Only .xlsx, .xlsm and .csv files are supported.")


def _enhanced_coerce_series(series: pd.Series, name: str) -> tuple[pd.Series, str]:
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
        .str.replace("$", "", regex=False)
        .str.replace("€", "", regex=False)
        .str.replace("£", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    percent_rate = float(nonblank.str.endswith("%").mean())
    if percent_rate >= 0.75:
        pct = pd.to_numeric(normal.str.rstrip("%"), errors="coerce")
        if float(pct.notna().mean()) >= 0.94:
            return pct / 100.0, "Percentage"

    numeric = pd.to_numeric(normal, errors="coerce")
    numeric_rate = float(numeric.notna().mean()) if len(s) else 0.0
    lowered_name = str(name).casefold()
    name_tokens = set(re.findall(r"[a-z0-9]+", lowered_name))
    strong_date_name = bool(name_tokens & {"date", "datetime", "timestamp", "created", "updated", "due"})
    full_date_signal = float(
        nonblank.str.contains(
            r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|[A-Za-z]{3,9}\s+\d{1,2}[, ]+\d{4}",
            regex=True,
        ).mean()
    ) >= 0.60
    time_only_signal = float(nonblank.str.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?").mean()) >= 0.75

    if strong_date_name and full_date_signal:
        parsed_date = pd.to_datetime(s, errors="coerce")
        if float(parsed_date.notna().mean()) >= 0.94:
            return parsed_date, "Date / time"
    if time_only_signal and not full_date_signal:
        return s.astype("string"), "Clock time"
    if numeric_rate >= 0.94:
        return numeric, "Number"

    lowered = nonblank.str.lower()
    if len(lowered) >= 5 and float(lowered.isin(BOOL_VALUES).mean()) >= 0.95:
        mapping = {
            "true": True, "false": False, "yes": True, "no": False,
            "y": True, "n": False, "active": True, "inactive": False,
        }
        return lowered.map(mapping).astype("boolean"), "Boolean"

    # Conservative European decimal support: only activate when the majority
    # of values clearly use dot thousands + comma decimals.
    eu_pattern = nonblank.str.fullmatch(r"-?\d{1,3}(?:\.\d{3})+,\d+")
    if float(eu_pattern.mean()) >= 0.75:
        converted = pd.to_numeric(
            nonblank.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        if float(converted.notna().mean()) >= 0.94:
            aligned = pd.Series(pd.NA, index=s.index, dtype="Float64")
            for idx, value in converted.items():
                aligned.loc[idx] = value
            return aligned, "Number"

    return s.astype("string"), "Text"


def _rebuild_excel_result(result: dict[str, Any]) -> dict[str, Any]:
    result["xlsx"] = _postprocess_export_guardrails(build_ultimate_workbook(
        f"Shoir-IE — {result['filename']}",
        result["cleaned_sheets"],
        result["raw_sheets"],
        result["audits"],
        result["profiles"],
        source_metadata=result.get("source_metadata"),
        field_intelligence=result.get("field_intelligence"),
        review_register=result.get("review_register"),
        before_after=result.get("before_after"),
        formula_inventory=result.get("formula_inventory"),
        cross_sheet_map=result.get("cross_sheet_map"),
    ))
    result["bundle"] = build_ultimate_bundle(
        f"Shoir-IE — {result['filename']}",
        result["xlsx"],
        result["audits"],
        result["profiles"],
        cleaned_sheets=result["cleaned_sheets"],
        raw_sheets=result["raw_sheets"],
        field_intelligence=result.get("field_intelligence"),
        review_register=result.get("review_register"),
        source_metadata=result.get("source_metadata"),
    )
    return result


_BASE_PROCESS_UPGRADED = process_uploaded_workbook
_read_raw_workbook = _enhanced_read_raw_workbook
_coerce_series = _enhanced_coerce_series


def process_uploaded_workbook(raw: bytes, filename: str) -> dict[str, Any]:
    result = _BASE_PROCESS_UPGRADED(raw, filename)
    # A second non-empty region separated by blank rows is a review signal.
    for meta in result.get("source_metadata", []):
        blocks = int(meta.get("Detected table blocks", 1) or 1)
        if blocks > 1:
            sheet = str(meta.get("Source sheet", ""))
            result.setdefault("review_register", []).append({
                "Severity": "Medium",
                "Sheet": sheet,
                "Field": "Sheet structure",
                "Issue": "Multiple table blocks detected",
                "Evidence": f"{blocks} non-empty table region(s) were inferred from blank-row separation.",
                "Recommended action": "Verify that all regions belong to one analytical table before downstream joins or aggregation.",
            })
    if result.get("source_metadata"):
        # Rebuild only after structure review flags have been added.
        _rebuild_excel_result(result)
    return result


def _choose_csv_delimiter(text: str) -> str:
    import csv
    candidates = [",", ";", "\t", "|"]
    lines = [line for line in str(text).splitlines() if line.strip()][:40]
    if len(lines) < 2:
        return ","
    scored: list[tuple[float, str]] = []
    for delim in candidates:
        counts = []
        for line in lines:
            try:
                row = next(csv.reader([line], delimiter=delim))
            except Exception:
                row = line.split(delim)
            counts.append(len(row))
        meaningful = [c for c in counts if c > 1]
        if not meaningful:
            continue
        median = float(np.median(meaningful))
        consistency = float(sum(c == meaningful[0] for c in meaningful) / len(meaningful))
        # A delimiter that creates the same 3-column shape across records beats
        # a comma embedded inside a value such as "1,200".
        score = median * 5.0 + consistency * 4.0 + (2.0 if len(set(meaningful)) == 1 else 0.0)
        scored.append((score, delim))
    return max(scored)[1] if scored else ","


def _final_read_raw_workbook(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    if not raw:
        raise ValueError("The uploaded file is empty.")
    lower = str(filename).lower()
    if lower.endswith(".csv"):
        decoded = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("CSV encoding could not be decoded safely.")
        delimiter = _choose_csv_delimiter(decoded)
        return {
            "CSV": pd.read_csv(
                io.StringIO(decoded),
                header=None,
                dtype=object,
                sep=delimiter,
                keep_default_na=False,
            )
        }
    if lower.endswith((".xlsx", ".xlsm")):
        book = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
        try:
            return {
                str(sheet): pd.read_excel(book, sheet_name=sheet, header=None, dtype=object)
                for sheet in book.sheet_names
            }
        finally:
            try:
                book.close()
            except Exception:
                pass
    raise ValueError("Only .xlsx, .xlsm and .csv files are supported.")


def _final_clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    cleaned, audit = _enhanced_clean_dataframe(df)
    # Tight numeric inference after sentinel normalization: values such as
    # ["10", "-"] should become [10, NA] rather than remaining text.
    for col in list(cleaned.columns):
        series = cleaned[col]
        if _is_identifier(str(col), series) or pd.api.types.is_datetime64_any_dtype(series) or pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
            continue
        numeric = pd.to_numeric(series, errors="coerce")
        non_null = int(series.notna().sum())
        if non_null and int(numeric.notna().sum()) == non_null:
            cleaned[col] = numeric
            audit.append({
                "Action": "Finalize numeric inference",
                "Details": f"Converted field '{col}' to numeric after missing-value normalization.",
            })
    return cleaned, audit


def _postprocess_export_guardrails(xlsx_bytes: bytes) -> bytes:
    """Final XLSX safety pass: aliases + inert source-formula text."""
    try:
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
        if "EXECUTIVE SUMMARY" not in book.sheetnames:
            ws = book.create_sheet("EXECUTIVE SUMMARY")
            ws["A1"] = "EXECUTIVE SUMMARY"
            ws["A3"] = "Legacy navigation alias. Use EXECUTIVE DASHBOARD for the full view."
            ws["A5"] = "Open EXECUTIVE DASHBOARD"
            ws["A5"].hyperlink = "#'EXECUTIVE DASHBOARD'!A1"
        if "DATA DICTIONARY" not in book.sheetnames:
            ws = book.create_sheet("DATA DICTIONARY")
            ws["A1"] = "DATA DICTIONARY"
            ws["A3"] = "Legacy navigation alias. Use FIELD INTELLIGENCE for richer field profiling."
            ws["A5"] = "Open FIELD INTELLIGENCE"
            ws["A5"].hyperlink = "#'FIELD INTELLIGENCE'!A1"
        if "QUALITY CHECKS" not in book.sheetnames:
            ws = book.create_sheet("QUALITY CHECKS")
            ws["A1"] = "QUALITY CHECKS"
            ws["A3"] = "Legacy navigation alias. Use DATA QUALITY CENTER for the governed quality view."
            ws["A5"] = "Open DATA QUALITY CENTER"
            ws["A5"].hyperlink = "#'DATA QUALITY CENTER'!A1"

        for ws in book.worksheets:
            if not ws.title.startswith("CLEAN - "):
                continue
            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith("=")):
                        value = str(cell.value)
                        cell._value = value
                        cell.data_type = "s"
        out = io.BytesIO()
        book.save(out)
        try:
            book.close()
        except Exception:
            pass
        return out.getvalue()
    except Exception:
        # Export safety should never make the import unusable; the primary
        # XlsxWriter output remains available if the optional final pass fails.
        return xlsx_bytes


_read_raw_workbook = _final_read_raw_workbook
clean_dataframe = _final_clean_dataframe


# Rebind public names one last time so imports from the module use the hardened
# versions rather than the pre-upgrade implementations.


# ---------------------------------------------------------------------------
# Governance++: repeatable contracts, privacy review, relationship integrity,
# formula consistency and module-readiness intelligence.
# ---------------------------------------------------------------------------

def _normalised_duplicate_candidates(df: pd.DataFrame, sheet: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for col in df.columns:
        if not _is_identifier(str(col), df[col]):
            continue
        values = df[col].dropna().astype(str)
        groups: dict[str, list[str]] = {}
        for value in values.tolist():
            key = re.sub(r"[^a-z0-9]+", "", value.casefold())
            if not key:
                continue
            groups.setdefault(key, []).append(value)
        for key, raw_values in groups.items():
            distinct = sorted(set(raw_values))
            if len(distinct) > 1:
                rows.append({
                    "Sheet": sheet,
                    "Field": str(col),
                    "Normalized key": key,
                    "Source variants": " | ".join(distinct[:8]),
                    "Occurrences": len(raw_values),
                    "Review": "Potential identifier formatting duplicates",
                    "Recommended action": "Confirm whether variants refer to one master entity before joins or aggregation.",
                })
    return rows


def _privacy_scan(cleaned: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rules = [
        ("Email address", re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")),
        ("Phone-like value", re.compile(r"^\+?[0-9][0-9\s().-]{7,}$")),
        ("Government-ID-like", re.compile(r"^\d{9,12}$")),
    ]
    name_hints = {
        "email": "Email field name",
        "phone": "Phone field name",
        "mobile": "Phone field name",
        "national id": "Government-ID field name",
        "passport": "Government-ID field name",
        "ssn": "Government-ID field name",
    }
    results: list[dict[str, Any]] = []
    for sheet, df in cleaned.items():
        for col in df.columns:
            name = str(col).casefold()
            series = df[col].dropna().astype(str).str.strip()
            indicator = None
            for hint, label in name_hints.items():
                if hint in name:
                    indicator = label
                    break
            match_count = 0
            if indicator is None and not series.empty:
                sample = series.head(5000)
                for label, regex in rules:
                    hits = int(sample.map(lambda v: bool(regex.fullmatch(v))).sum())
                    if hits >= max(2, int(len(sample) * 0.10)):
                        indicator = label
                        match_count = int(round(hits / max(1, len(sample)) * len(series)))
                        break
            if indicator:
                results.append({
                    "Sheet": sheet,
                    "Field": str(col),
                    "Indicator": indicator,
                    "Estimated matches": match_count if match_count else int(len(series)),
                    "Action": "Review access, masking and downstream export requirements before distribution.",
                    "Data exposed in scan": "No raw values retained",
                })
    return results


def _relationship_integrity(cleaned: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    names = list(cleaned)
    rows: list[dict[str, Any]] = []
    for i, left_name in enumerate(names):
        left = cleaned[left_name]
        left_norm = {re.sub(r"[^a-z0-9]+", "", str(c).casefold()): str(c) for c in left.columns}
        for right_name in names[i + 1:]:
            right = cleaned[right_name]
            right_norm = {re.sub(r"[^a-z0-9]+", "", str(c).casefold()): str(c) for c in right.columns}
            shared_norm = sorted(set(left_norm) & set(right_norm))
            for norm_key in shared_norm[:12]:
                lcol, rcol = left_norm[norm_key], right_norm[norm_key]
                lv = left[lcol].dropna().astype(str).map(lambda x: re.sub(r"\s+", " ", x.strip().casefold()))
                rv = right[rcol].dropna().astype(str).map(lambda x: re.sub(r"\s+", " ", x.strip().casefold()))
                lset, rset = set(lv), set(rv)
                matched = len(lset & rset)
                unmatched_l = len(lset - rset)
                unmatched_r = len(rset - lset)
                l_unique = int(lv.is_unique)
                r_unique = int(rv.is_unique)
                readiness = (
                    "Strong candidate"
                    if matched and (unmatched_l == 0 or unmatched_r == 0)
                    else "Review before join"
                )
                rows.append({
                    "Sheet A": left_name,
                    "Sheet B": right_name,
                    "Field A": lcol,
                    "Field B": rcol,
                    "Unique A": "Yes" if l_unique else "No",
                    "Unique B": "Yes" if r_unique else "No",
                    "Matched distinct values": matched,
                    "A unmatched values": unmatched_l,
                    "B unmatched values": unmatched_r,
                    "Join readiness": readiness,
                })
    return rows


def _formula_quality_inventory(formula_inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not formula_inventory:
        return []
    buckets: dict[tuple[str, str], list[str]] = {}
    for row in formula_inventory:
        cell = str(row.get("Cell", ""))
        col = re.match(r"[A-Za-z]+", cell)
        key = (str(row.get("Sheet", "")), col.group(0) if col else "—")
        formula = str(row.get("Formula", ""))
        normalized = re.sub(r"\$?[A-Za-z]{1,3}\$?\d+", "<REF>", formula)
        buckets.setdefault(key, []).append(normalized)
    results: list[dict[str, Any]] = []
    for (sheet, col), formulas in buckets.items():
        counts = pd.Series(formulas).value_counts()
        dominant = str(counts.index[0]) if not counts.empty else ""
        inconsistent = int(sum(1 for f in formulas if f != dominant))
        results.append({
            "Sheet": sheet,
            "Formula column": col,
            "Formula cells": len(formulas),
            "Distinct formula patterns": len(counts),
            "Dominant pattern": dominant,
            "Inconsistent cells": inconsistent,
            "Review": "Review fill/copy logic" if inconsistent else "Consistent pattern",
        })
    return results


def _module_readiness(cleaned: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sheet, df in cleaned.items():
        names = {str(c).casefold() for c in df.columns}
        normalized = {re.sub(r"[^a-z0-9]+", "", x) for x in names}
        signals = []
        module = "Data Intelligence"
        next_step = "Use the Universal Visualization and Query layers."
        if {"availability", "performance", "quality"} <= names:
            module = "OEE"; signals.append("Availability + Performance + Quality"); next_step = "Run OEE analysis and trend/ Pareto views."
        elif any("defect" in x or "scrap" in x or "fpy" in x or "yield" in x for x in names):
            module = "Quality"; signals.append("Defect / scrap / yield field"); next_step = "Run Pareto, SPC or capability analysis."
        elif any("asset" in x or "machine" in x for x in names) and any("failure" in x or "downtime" in x or "mtbf" in x for x in names):
            module = "Maintenance"; signals.append("Asset + failure/downtime signal"); next_step = "Run maintenance reliability and anomaly analysis."
        elif any("sku" in x or "inventory" in x or "stock" in x for x in names) and any("demand" in x or "usage" in x for x in names):
            module = "Inventory / Supply Chain"; signals.append("SKU + demand/inventory signal"); next_step = "Run ABC, reorder/safety-stock or forecasting analysis."
        elif any("date" in x or "month" in x or "timestamp" in x for x in names) and any(x in normalized for x in ("demand","output","qty","quantity","volume")):
            module = "Forecasting / Planning"; signals.append("Time axis + measurable demand/output"); next_step = "Run trend, forecast and scenario analysis."
        elif any("cost" in x or "price" in x for x in names) and any(x in normalized for x in ("quantity","qty","demand","output")):
            module = "Economics / Optimization"; signals.append("Cost + operational quantity"); next_step = "Build cost scenarios or optimization inputs."
        else:
            signals.append(f"{len(df.columns):,} mapped fields")
        rows.append({
            "Sheet": sheet,
            "Recommended module": module,
            "Evidence": " · ".join(signals),
            "Confidence": "High" if len(signals) > 1 or module != "Data Intelligence" else "Medium",
            "Recommended next step": next_step,
        })
    return rows


def _data_contract(cleaned: dict[str, pd.DataFrame], field_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contract = []
    for row in field_rows:
        role = str(row.get("Role", ""))
        contract.append({
            "Sheet": row.get("Sheet", ""),
            "Field": row.get("Field", ""),
            "Expected role": role,
            "Inferred type": row.get("Inferred type", ""),
            "Type confidence": row.get("Type confidence", ""),
            "Canonical entity": row.get("Canonical entity", "—"),
            "Unit hint": row.get("Unit hint", "—"),
            "Required candidate": "Yes" if role == "Identifier" else "No",
            "Unique candidate": "Yes" if role == "Identifier" else "No",
            "Missing %": row.get("Missing %", 0),
            "Rule status": "Review" if float(row.get("Missing %", 0) or 0) > 20 else "Ready",
        })
    return contract


_CLEAN_RECIPE = [
    ("Header detection", "Detect a schema row rather than trusting row 1", "Automatic", "Prevents report titles and notes from becoming headers."),
    ("Header normalization", "Trim, normalize and deduplicate column names", "Automatic", "Creates stable field names for downstream modules."),
    ("Blank row/column cleanup", "Remove purely empty presentation noise", "Automatic", "Keeps analytical tables compact."),
    ("Missing-value normalization", "Normalize common null tokens while protecting identifiers", "Automatic", "Makes missingness measurable without corrupting keys."),
    ("Accounting normalization", "Interpret parenthesized negatives as numeric negatives", "Automatic", "Preserves common finance/operations exports."),
    ("Identifier preservation", "Keep IDs as text and report duplicate keys", "Automatic + Review", "Protects leading zeros and master-data identity."),
    ("Type inference", "Infer date, time, number, percentage, boolean and text", "Automatic + Review", "Prepares fields for safe analysis."),
    ("Outlier detection", "Flag IQR/robust outliers; never silently delete", "Review", "Industrial observations can be real events."),
    ("Date sanity", "Flag dates outside the defined review window", "Review", "Prevents obvious temporal corruption."),
    ("Range/ratio checks", "Flag percentage/ratio violations", "Review", "Avoids mixing 95 and 0.95 without intent."),
    ("Provenance", "Hash source bytes and archive source metadata", "Automatic", "Supports reproducibility and evidence."),
    ("Formula archive", "Capture source formulas as inert evidence", "Automatic", "Retains lineage without executing source formulas."),
    ("Relationship checks", "Compare shared fields across sheets", "Review", "Prevents unsafe blind joins."),
    ("Privacy scan", "Identify likely sensitive fields without retaining raw values", "Review", "Reduces accidental exposure in exports."),
]


def _append_governance_plus_to_workbook(xlsx_bytes: bytes, result: dict[str, Any]) -> bytes:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        book = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
        frames = {
            "DATA CONTRACT": pd.DataFrame(result.get("data_contract", [])),
            "RELATIONSHIP INTEGRITY": pd.DataFrame(result.get("relationship_integrity", [])),
            "PRIVACY SCAN": pd.DataFrame(result.get("privacy_scan", [])),
            "FORMULA QUALITY": pd.DataFrame(result.get("formula_quality", [])),
            "DUPLICATE CANDIDATES": pd.DataFrame(result.get("duplicate_candidates", [])),
            "MODULE READINESS": pd.DataFrame(result.get("module_readiness", [])),
            "CLEANING RECIPE": pd.DataFrame([
                {"Rule": a, "Behavior": b, "Mode": c, "Reason": d}
                for a,b,c,d in _CLEAN_RECIPE
            ]),
        }
        for name, frame in frames.items():
            if name in book.sheetnames:
                del book[name]
            ws = book.create_sheet(name)
            ws.freeze_panes = "A2"
            ws.sheet_view.showGridLines = False
            if frame.empty:
                frame = pd.DataFrame([{"Status": "No automated findings for this workbook."}])
            for c_idx, col in enumerate(frame.columns, 1):
                cell = ws.cell(1, c_idx, str(col))
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="163A5F")
                cell.alignment = Alignment(vertical="center")
            for r_idx, row in enumerate(frame.itertuples(index=False, name=None), 2):
                for c_idx, value in enumerate(row, 1):
                    cell = ws.cell(r_idx, c_idx, None if _cell_is_na(value) else value)
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
            ws.auto_filter.ref = ws.dimensions
            for col_cells in ws.columns:
                letter = col_cells[0].column_letter
                width = min(70, max(12, max(len(str(c.value or "")) for c in col_cells[:40]) + 2))
                ws.column_dimensions[letter].width = width
        out = io.BytesIO()
        book.save(out)
        try:
            book.close()
        except Exception:
            pass
        return out.getvalue()
    except Exception:
        return xlsx_bytes



def _refresh_excel_governance(result: dict[str, Any]) -> dict[str, Any]:
    cleaned = result.get("cleaned_sheets", {})
    result["duplicate_candidates"] = [item for sheet, frame in cleaned.items() for item in _normalised_duplicate_candidates(frame, sheet)]
    result["privacy_scan"] = _privacy_scan(cleaned)
    result["relationship_integrity"] = _relationship_integrity(cleaned)
    result["formula_quality"] = _formula_quality_inventory(result.get("formula_inventory", []))
    result["module_readiness"] = _module_readiness(cleaned)
    result["data_contract"] = _data_contract(cleaned, result.get("field_intelligence", []))
    reviews = [issue for sheet, frame in cleaned.items() for issue in _quality_review_register(frame, sheet)]
    for meta in result.get("source_metadata", []):
        blocks = int(meta.get("Detected table blocks", 1) or 1)
        if blocks > 1:
            reviews.append({"Severity":"Medium","Sheet":str(meta.get("Source sheet","")),"Field":"Sheet structure","Issue":"Multiple table blocks detected","Evidence":f"{blocks:,} non-empty table region(s) inferred.","Recommended action":"Verify the regions belong to one analytical table."})
    for item in result["duplicate_candidates"]:
        reviews.append({"Severity":"Medium","Sheet":item["Sheet"],"Field":item["Field"],"Issue":item["Review"],"Evidence":f"{item['Occurrences']:,} occurrence(s): {item['Source variants']}","Recommended action":item["Recommended action"]})
    for item in result["privacy_scan"]:
        reviews.append({"Severity":"High","Sheet":item["Sheet"],"Field":item["Field"],"Issue":"Potential sensitive field","Evidence":f"Indicator: {item['Indicator']}; estimated matches: {item['Estimated matches']:,}.","Recommended action":item["Action"]})
    result["review_register"] = reviews
    return result

_BASE_PROCESS_GOVERNANCE = process_uploaded_workbook


def process_uploaded_workbook(raw: bytes, filename: str) -> dict[str, Any]:
    result = _BASE_PROCESS_GOVERNANCE(raw, filename)
    _refresh_excel_governance(result)
    result["xlsx"] = _append_governance_plus_to_workbook(result["xlsx"], result)
    result["xlsx"] = _postprocess_export_guardrails(result["xlsx"])
    result["bundle"] = build_ultimate_bundle(
        f"Shoir-IE — {result['filename']}",
        result["xlsx"],
        result["audits"],
        result["profiles"],
        cleaned_sheets=result.get("cleaned_sheets", {}),
        raw_sheets=result.get("raw_sheets", {}),
        field_intelligence=result.get("field_intelligence", []),
        review_register=result.get("review_register", []),
        source_metadata=result.get("source_metadata", []),
    )
    return result


def _header_first_csv_delimiter(text: str) -> str:
    import csv
    lines = [line for line in str(text).splitlines() if line.strip()]
    if not lines:
        return ","
    header = lines[0]
    candidates = [",", ";", "\t", "|"]
    counts = {delimiter: header.count(delimiter) for delimiter in candidates}
    best = max(counts, key=counts.get)
    if counts[best] > 0:
        return best
    return _choose_csv_delimiter(text)
def _definitive_read_raw_workbook(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    """Single authoritative reader used by the final processing entry point."""
    if not raw:
        raise ValueError("The uploaded file is empty.")
    lower = str(filename).lower()
    if lower.endswith(".csv"):
        decoded = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("CSV encoding could not be decoded safely.")
        # Handle serialized CSV payloads where row breaks were escaped as
        # literal backslash-n characters. Do this only when no real row
        # separators exist, so legitimate backslash-n field content is kept.
        if "\\n" in decoded and "\n" not in decoded and "\r" not in decoded:
            decoded = decoded.replace("\\r\\n", "\n").replace("\\n", "\n")
        return {
            "CSV": pd.read_csv(
                io.StringIO(decoded),
                header=None,
                dtype=object,
                sep=";" if ";" in decoded.splitlines()[0] else _header_first_csv_delimiter(decoded),
                keep_default_na=False,
            )
        }
    if lower.endswith((".xlsx", ".xlsm")):
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
        try:
            return {
                str(name): pd.DataFrame(list(ws.values), dtype=object)
                for name, ws in ((ws.title, ws) for ws in book.worksheets)
            }
        finally:
            book.close()
    raise ValueError("Only .xlsx, .xlsm and .csv files are supported.")


def _definitive_process_uploaded_workbook(raw: bytes, filename: str) -> dict[str, Any]:
    signature = hashlib.sha256(raw).hexdigest()
    raw_sheets = _definitive_read_raw_workbook(raw, filename)
    cleaned: dict[str, pd.DataFrame] = {}
    audits: dict[str, list[dict[str, str]]] = {}
    profiles: dict[str, dict[str, Any]] = {}
    fields: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    before_after: list[dict[str, Any]] = []
    header_rows: dict[str, int] = {}

    for source_name, raw_df in raw_sheets.items():
        header_row = _enhanced_detect_header_row(raw_df)
        header_rows[source_name] = header_row
        if raw_df.empty:
            table = pd.DataFrame()
        else:
            headers = _deduplicate_headers(raw_df.iloc[header_row].tolist())
            table = raw_df.iloc[header_row + 1:].copy()
            table.columns = headers
            table = table.dropna(axis=1, how="all").dropna(axis=0, how="all")
        cleaned_df, audit = _final_clean_dataframe(table)
        cleaned[source_name] = cleaned_df
        audits[source_name] = [{"Action": "Detect table header", "Details": f"Detected source header row {header_row + 1}."}] + audit
        profiles[source_name] = _enhanced_profile_dataframe(cleaned_df)
        fields.extend(_field_intelligence_rows(cleaned_df, source_name))
        reviews.extend(_quality_review_register(cleaned_df, source_name))
        before_after.append({
            "Sheet": source_name,
            "Source rows": int(len(table)),
            "Clean rows": int(len(cleaned_df)),
            "Rows removed": int(max(0, len(table) - len(cleaned_df))),
            "Source columns": int(len(table.columns)),
            "Clean columns": int(len(cleaned_df.columns)),
            "Columns removed": int(max(0, len(table.columns) - len(cleaned_df.columns))),
            "Missing before": int(table.isna().sum().sum()) if not table.empty else 0,
            "Missing after": int(cleaned_df.isna().sum().sum()) if not cleaned_df.empty else 0,
            "Duplicate rows removed": int(table.duplicated().sum() - cleaned_df.duplicated().sum()) if not table.empty else 0,
            "Schema fingerprint": profiles[source_name].get("Schema fingerprint", "—"),
        })

    source_metadata, formula_inventory = _extract_source_metadata(raw, filename, raw_sheets, header_rows)
    cross_map = _cross_sheet_map(cleaned)
    result = {
        "signature": signature,
        "filename": filename,
        "raw_sheets": raw_sheets,
        "cleaned_sheets": cleaned,
        "audits": audits,
        "profiles": profiles,
        "field_intelligence": fields,
        "review_register": reviews,
        "before_after": before_after,
        "source_metadata": source_metadata,
        "formula_inventory": formula_inventory,
        "cross_sheet_map": cross_map,
    }
    result["xlsx"] = build_ultimate_workbook(
        f"Shoir-IE — {filename}", cleaned, raw_sheets, audits, profiles,
        source_metadata=source_metadata, field_intelligence=fields,
        review_register=reviews, before_after=before_after,
        formula_inventory=formula_inventory, cross_sheet_map=cross_map,
    )
    return result


def _multi_module_readiness(cleaned: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sheet, df in cleaned.items():
        names = {str(c).casefold() for c in df.columns}
        normalized = {re.sub(r"[^a-z0-9]+", "", x) for x in names}
        candidates: list[tuple[str, str, str, str]] = []
        if {"availability", "performance", "quality"} <= names:
            candidates.append(("OEE", "Availability + Performance + Quality", "High", "Run OEE analysis and trend/Pareto views."))
        if any("defect" in x or "scrap" in x or "fpy" in x or "yield" in x for x in names):
            candidates.append(("Quality", "Defect / scrap / yield signal", "High", "Run Pareto, SPC or capability analysis."))
        if any("asset" in x or "machine" in x for x in names) and any("failure" in x or "downtime" in x or "mtbf" in x or "mttr" in x for x in names):
            candidates.append(("Maintenance", "Asset + failure/downtime signal", "High", "Run reliability, downtime and anomaly analysis."))
        if any("sku" in x or "inventory" in x or "stock" in x for x in names) and any("demand" in x or "usage" in x for x in names):
            candidates.append(("Inventory / Supply Chain", "SKU + demand/inventory signal", "High", "Run ABC, reorder, safety-stock or forecasting analysis."))
        if any("date" in x or "month" in x or "timestamp" in x for x in names) and any(x in normalized for x in ("demand", "output", "qty", "quantity", "volume")):
            candidates.append(("Forecasting / Planning", "Time axis + measurable demand/output", "High", "Run trend, forecast and scenario analysis."))
        if any("cost" in x or "price" in x for x in names) and any(x in normalized for x in ("quantity", "qty", "demand", "output")):
            candidates.append(("Economics / Optimization", "Cost + operational quantity", "Medium", "Build cost scenarios or optimization inputs."))
        if not candidates:
            candidates.append(("Data Intelligence", f"{len(df.columns):,} mapped fields", "Medium", "Use the Universal Visualization and Query layers."))
        for module, evidence, confidence, next_step in candidates:
            rows.append({
                "Sheet": sheet,
                "Recommended module": module,
                "Evidence": evidence,
                "Confidence": confidence,
                "Recommended next step": next_step,
            })
    return rows


def _reconcile_clean_sheet_payload(xlsx_bytes: bytes, cleaned: dict[str, pd.DataFrame]) -> bytes:
    """Guarantee the exported CLEAN sheets contain the exact cleaned values."""
    try:
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
        clean_ws = [ws for ws in book.worksheets if ws.title.startswith("CLEAN - ")]
        for source_name, frame in cleaned.items():
            candidates = [
                ws for ws in clean_ws
                if ws.title.replace("CLEAN - ", "", 1).strip() == str(source_name).strip()
            ]
            if not candidates:
                continue
            ws = candidates[0]
            header_row = 5  # zero-based; row 6 in the workbook.
            for j, col in enumerate(frame.columns):
                cell = ws.cell(header_row + 1, j + 1)
                cell._value = str(col)
                cell.data_type = "s"
            for i, row in enumerate(frame.itertuples(index=False, name=None), header_row + 2):
                for j, value in enumerate(row, 1):
                    cell = ws.cell(i, j, None)
                    if _cell_is_na(value):
                        cell._value = None
                        cell.data_type = "n"
                    elif isinstance(value, (pd.Timestamp,)):
                        cell._value = value.to_pydatetime()
                        cell.data_type = "d"
                    elif isinstance(value, (bool, np.bool_)):
                        cell._value = bool(value)
                        cell.data_type = "b"
                    elif isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
                        try:
                            number = float(value)
                            if math.isfinite(number):
                                cell._value = int(value) if float(number).is_integer() else number
                                cell.data_type = "n"
                            else:
                                cell._value = str(value)
                                cell.data_type = "s"
                        except Exception:
                            cell._value = str(value)
                            cell.data_type = "s"
                    else:
                        cell._value = str(value)
                        cell.data_type = "s"
        out = io.BytesIO()
        book.save(out)
        book.close()
        return out.getvalue()
    except Exception:
        return xlsx_bytes


def process_uploaded_workbook(raw: bytes, filename: str) -> dict[str, Any]:
    result = _definitive_process_uploaded_workbook(raw, filename)
    result["module_readiness"] = _multi_module_readiness(result["cleaned_sheets"])
    result["duplicate_candidates"] = [item for sheet, frame in result["cleaned_sheets"].items() for item in _normalised_duplicate_candidates(frame, sheet)]
    result["privacy_scan"] = _privacy_scan(result["cleaned_sheets"])
    result["relationship_integrity"] = _relationship_integrity(result["cleaned_sheets"])
    result["formula_quality"] = _formula_quality_inventory(result.get("formula_inventory", []))
    result["data_contract"] = _data_contract(result["cleaned_sheets"], result.get("field_intelligence", []))
    result["review_register"] = [
        issue for sheet, frame in result["cleaned_sheets"].items() for issue in _quality_review_register(frame, sheet)
    ]
    for meta in result.get("source_metadata", []):
        blocks = int(meta.get("Detected table blocks", 1) or 1)
        if blocks > 1:
            result["review_register"].append({
                "Severity":"Medium","Sheet":str(meta.get("Source sheet","")),"Field":"Sheet structure",
                "Issue":"Multiple table blocks detected","Evidence":f"{blocks:,} non-empty table region(s) inferred.",
                "Recommended action":"Verify the regions belong to one analytical table."
            })
    for item in result["duplicate_candidates"]:
        result["review_register"].append({
            "Severity":"Medium","Sheet":item["Sheet"],"Field":item["Field"],
            "Issue":item["Review"],"Evidence":f"{item['Occurrences']:,} occurrence(s): {item['Source variants']}",
            "Recommended action":item["Recommended action"]
        })
    for item in result["privacy_scan"]:
        result["review_register"].append({
            "Severity":"High","Sheet":item["Sheet"],"Field":item["Field"],
            "Issue":"Potential sensitive field",
            "Evidence":f"Indicator: {item['Indicator']}; estimated matches: {item['Estimated matches']:,}.",
            "Recommended action":item["Action"]
        })
    result["xlsx"] = _append_governance_plus_to_workbook(result["xlsx"], result)
    result["xlsx"] = _postprocess_export_guardrails(result["xlsx"])
    result["xlsx"] = _reconcile_clean_sheet_payload(result["xlsx"], result["cleaned_sheets"])
    result["bundle"] = build_ultimate_bundle(
        f"Shoir-IE — {result['filename']}",
        result["xlsx"], result["audits"], result["profiles"],
        cleaned_sheets=result["cleaned_sheets"], raw_sheets=result["raw_sheets"],
        field_intelligence=result.get("field_intelligence", []),
        review_register=result["review_register"],
        source_metadata=result.get("source_metadata", []),
    )
    return result


# ---------------------------------------------------------------------------
# Enterprise Excel Intelligence Engine
# ---------------------------------------------------------------------------
# This layer extends the existing Excel Studio without removing its public API.
# It focuses on safe automation, explicit review, reproducibility and easy
# hand-off into the rest of Shoir-IE.

import difflib
from collections import Counter

_EXCEL_UNIT_FACTORS = {
    "g": ("mass", 0.001),
    "kg": ("mass", 1.0),
    "mg": ("mass", 0.000001),
    "lb": ("mass", 0.45359237),
    "mm": ("length", 0.001),
    "cm": ("length", 0.01),
    "m": ("length", 1.0),
    "km": ("length", 1000.0),
    "s": ("time", 1.0),
    "sec": ("time", 1.0),
    "min": ("time", 60.0),
    "hr": ("time", 3600.0),
    "h": ("time", 3600.0),
    "hours": ("time", 3600.0),
    "w": ("power", 1.0),
    "kw": ("power", 1000.0),
    "mw": ("power", 1_000_000.0),
    "wh": ("energy", 1.0),
    "kwh": ("energy", 1000.0),
    "mwh": ("energy", 1_000_000.0),
}
_EXCEL_TEMP_UNITS = {"c", "°c", "f", "°f"}
_EXCEL_SECRET_PATTERNS = [
    ("API key", re.compile(r"(?i)\b(?:api[_ -]?key|apikey)\b.{0,8}[=:]\s*[A-Za-z0-9_\-]{12,}")),
    ("Bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("Private key material", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Connection string", re.compile(r"(?i)\b(?:password|pwd)\s*=\s*[^;\s]+")),
]
_EXCEL_ALLOWED_VALUE_HINTS = {
    "status": {"active", "inactive", "open", "closed", "pending", "complete", "completed", "cancelled", "canceled"},
}
_EXCEL_DEFAULT_RULES = [
    {"id": "REQ-001", "rule": "Required identifier non-null", "kind": "required_identifier", "severity": "High", "enabled": True},
    {"id": "NUM-001", "rule": "Numeric fields contain valid numeric values", "kind": "numeric_integrity", "severity": "High", "enabled": True},
    {"id": "PCT-001", "rule": "Percentage fields remain within 0..1 after normalization", "kind": "percentage_range", "severity": "High", "enabled": True},
    {"id": "DATE-001", "rule": "Dates remain within the review window 1900..2100", "kind": "date_range", "severity": "Medium", "enabled": True},
]

def _excel_unit_token(name: str) -> str:
    match = re.search(
        r"[\(\[]\s*(kg|g|mg|lb|mm|cm|km|m|s|sec|min|hr|hrs|h|hours|kwh|mwh|wh|kw|mw|w|°c|°f|c|f)\s*[\)\]]",
        str(name),
        flags=re.IGNORECASE,
    )
    return match.group(1).lower() if match else ""

def _excel_convert_unit_values(series: pd.Series, source_unit: str, target_unit: str) -> tuple[pd.Series, int]:
    src = str(source_unit).strip().lower()
    dst = str(target_unit).strip().lower()
    if src == "hrs":
        src = "hr"
    if dst == "hrs":
        dst = "hr"
    if src in {"°c", "c"} and dst in {"°f", "f"}:
        numeric = pd.to_numeric(series, errors="coerce")
        out = numeric * 9.0 / 5.0 + 32.0
        return out.astype("Float64"), int(numeric.notna().sum())
    if src in {"°f", "f"} and dst in {"°c", "c"}:
        numeric = pd.to_numeric(series, errors="coerce")
        out = (numeric - 32.0) * 5.0 / 9.0
        return out.astype("Float64"), int(numeric.notna().sum())
    if src not in _EXCEL_UNIT_FACTORS or dst not in _EXCEL_UNIT_FACTORS:
        raise ValueError(f"Unsupported unit conversion: {source_unit} -> {target_unit}")
    src_dim, src_factor = _EXCEL_UNIT_FACTORS[src]
    dst_dim, dst_factor = _EXCEL_UNIT_FACTORS[dst]
    if src_dim != dst_dim:
        raise ValueError(f"Incompatible unit dimensions: {source_unit} -> {target_unit}")
    numeric = pd.to_numeric(series, errors="coerce")
    out = numeric * src_factor / dst_factor
    return out.astype("Float64"), int(numeric.notna().sum())

def _excel_missingness_patterns(df: pd.DataFrame, sheet: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if df.empty:
        return rows
    row_missing = df.isna().sum(axis=1)
    for col in df.columns:
        s = df[col]
        missing_mask = s.isna()
        pct = float(missing_mask.mean() * 100.0)
        if pct == 0:
            pattern = "Complete"
        elif pct >= 80:
            pattern = "Structurally sparse"
        else:
            neighbors = [c for c in df.columns if c != col]
            association = 0.0
            for other in neighbors[:30]:
                other_mask = df[other].isna()
                if other_mask.nunique() > 1 and missing_mask.nunique() > 1:
                    corr = missing_mask.astype(float).corr(other_mask.astype(float))
                    if pd.notna(corr):
                        association = max(association, abs(float(corr)))
            row_cluster = 0.0
            if len(row_missing) > 1:
                ranked = row_missing.rank(method="average", pct=True)
                corr = missing_mask.astype(float).corr(ranked)
                row_cluster = abs(float(corr)) if pd.notna(corr) else 0.0
            if max(association, row_cluster) >= 0.5:
                pattern = "Structured-missingness candidate"
            elif pct >= 50:
                pattern = "High missingness"
            elif pct >= 20:
                pattern = "Material missingness"
            else:
                pattern = "Isolated / low missingness"
        rows.append({
            "Sheet": str(sheet),
            "Field": str(col),
            "Missing %": round(pct, 2),
            "Missing count": int(missing_mask.sum()),
            "Pattern": pattern,
        })
    return rows

def _excel_duplicate_intelligence(df: pd.DataFrame, sheet: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    id_cols = [str(c) for c in df.columns if _is_identifier(str(c), df[c])]
    for size in range(2, min(4, len(id_cols)) + 1):
        for combo in __import__("itertools").combinations(id_cols, size):
            work = df[list(combo)].copy()
            dup_mask = work.duplicated(keep=False) & work.notna().all(axis=1)
            count = int(dup_mask.sum())
            if count:
                conflict = 0
                compare_cols = [c for c in df.columns if str(c) not in combo]
                if compare_cols:
                    grouped = df.loc[dup_mask].groupby(list(combo), dropna=False)
                    for _, group in grouped:
                        for col in compare_cols[:30]:
                            if group[col].nunique(dropna=True) > 1:
                                conflict += 1
                                break
                findings.append({
                    "Sheet": sheet,
                    "Type": "Composite key duplicate",
                    "Fields": " + ".join(combo),
                    "Occurrences": count,
                    "Conflicting duplicate groups": conflict,
                    "Review": "Potential composite-key duplication",
                    "Recommended action": "Confirm the intended grain before aggregation or joins.",
                })
    for col in id_cols:
        values = df[col].dropna().astype("string").tolist()
        if len(values) > 5000:
            values = values[:5000]
        normalized_map: dict[str, list[str]] = {}
        for value in values:
            normalized = re.sub(r"[^a-z0-9]+", "", str(value).casefold())
            if normalized:
                normalized_map.setdefault(normalized, []).append(str(value))
        for normalized, variants in normalized_map.items():
            distinct = sorted(set(variants))
            if len(distinct) > 1:
                findings.append({
                    "Sheet": sheet,
                    "Type": "Normalized identifier collision",
                    "Fields": col,
                    "Occurrences": len(variants),
                    "Conflicting duplicate groups": 0,
                    "Source variants": " | ".join(distinct[:10]),
                    "Review": "Potential formatting duplicate",
                    "Recommended action": "Normalize only after confirming that the variants are one entity.",
                })
        sample = sorted(set(str(v) for v in values))
        checked = 0
        for i, left in enumerate(sample[:1500]):
            for right in sample[i + 1:i + 8]:
                if len(left) < 4 or len(right) < 4:
                    continue
                ratio = difflib.SequenceMatcher(None, left.casefold(), right.casefold()).ratio()
                if ratio >= 0.92 and left.casefold() != right.casefold():
                    findings.append({
                        "Sheet": sheet,
                        "Type": "Fuzzy identifier candidate",
                        "Fields": col,
                        "Occurrences": 2,
                        "Source variants": f"{left} | {right}",
                        "Similarity": round(ratio, 3),
                        "Review": "Near-duplicate identifier candidate",
                        "Recommended action": "Confirm whether spelling/casing/formatting differences represent one master entity.",
                    })
                    checked += 1
                    if checked >= 100:
                        break
            if checked >= 100:
                break
    return findings

def _excel_extended_outlier_findings(df: pd.DataFrame, sheet: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for col in df.columns:
        series = df[col]
        if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
            continue
        values = pd.to_numeric(series, errors="coerce").dropna()
        if len(values) < 8 or values.nunique() < 2:
            continue
        median = float(values.median())
        mad = float((values - median).abs().median())
        robust_count = 0
        if mad > 0:
            robust_count = int((abs(0.6745 * (values - median) / mad) > 3.5).sum())
        mean, std = float(values.mean()), float(values.std(ddof=1))
        z_count = int((((values - mean) / std).abs() > 3.0).sum()) if std > 0 else 0
        spike_count = 0
        ordered = values.index
        try:
            diff = values.diff().dropna()
            diff_median = float(diff.abs().median())
            if diff_median > 0:
                spike_count = int((diff.abs() > 8 * diff_median).sum())
        except Exception:
            pass
        flatline = 0
        if len(values) >= 10:
            flatline = int((values.rolling(5).std().fillna(np.nan) == 0).sum())
        if robust_count or z_count or spike_count or flatline:
            findings.append({
                "Severity": "Low",
                "Sheet": sheet,
                "Field": str(col),
                "Issue": "Extended statistical/behavioral outlier review",
                "Evidence": f"Robust-z={robust_count}, z>3={z_count}, abrupt changes={spike_count}, flatline windows={flatline}.",
                "Recommended action": "Review the affected records in context; preserve real industrial events.",
            })
    return findings

def _excel_engineering_limits(df: pd.DataFrame, sheet: str, limits: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    findings = []
    limits = limits or {}
    for col, config in limits.items() if isinstance(limits, dict) else []:
        if col not in df.columns or not isinstance(config, dict):
            continue
        values = pd.to_numeric(df[col], errors="coerce")
        low, high = config.get("min"), config.get("max")
        mask = pd.Series(False, index=df.index)
        if low is not None:
            mask |= values < float(low)
        if high is not None:
            mask |= values > float(high)
        count = int(mask.sum())
        if count:
            findings.append({
                "Severity": "High",
                "Sheet": sheet,
                "Field": str(col),
                "Issue": "Engineering specification limit violation",
                "Evidence": f"{count:,} value(s) outside configured limits [{low}, {high}].",
                "Recommended action": "Verify the physical/specification limit and investigate affected records.",
            })
    return findings

def _excel_profile_enrichment(df: pd.DataFrame, sheet: str) -> list[dict[str, Any]]:
    rows = []
    for col in df.columns:
        series = df[col]
        non_null = series.dropna()
        row = {
            "Sheet": sheet,
            "Field": str(col),
            "Role": _column_role(str(col), series),
            "Type": _field_intelligence_rows(df, sheet)[list(df.columns).index(col)].get("Type", "Text"),
            "Cardinality": int(series.nunique(dropna=True)),
            "Cardinality %": round(float(series.nunique(dropna=True) / max(1, len(series)) * 100), 2),
            "Missing %": round(float(series.isna().mean() * 100), 2),
            "Examples": " | ".join(str(x) for x in non_null.head(5).tolist())[:240],
        }
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            row.update({
                "Min": float(numeric.min()) if not numeric.empty else None,
                "Q1": float(numeric.quantile(0.25)) if not numeric.empty else None,
                "Median": float(numeric.median()) if not numeric.empty else None,
                "Mean": float(numeric.mean()) if not numeric.empty else None,
                "Q3": float(numeric.quantile(0.75)) if not numeric.empty else None,
                "Max": float(numeric.max()) if not numeric.empty else None,
                "Std dev": float(numeric.std(ddof=1)) if len(numeric) > 1 else 0.0,
                "Skewness": float(numeric.skew()) if len(numeric) > 2 else 0.0,
            })
        else:
            counts = non_null.astype("string").value_counts(dropna=False)
            row["Top category"] = str(counts.index[0]) if not counts.empty else ""
            row["Top category count"] = int(counts.iloc[0]) if not counts.empty else 0
        rows.append(row)
    return rows

def _excel_formula_dependencies(formula_inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in formula_inventory:
        formula = str(item.get("Formula", ""))
        if not formula:
            continue
        external = "[" in formula or "]" in formula or re.search(r"https?://", formula, flags=re.I)
        refs = re.findall(r"(?:(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_ ]*))!)?\$?([A-Za-z]{1,3})\$?\d+", formula)
        for sheet_a, sheet_b, cell in refs:
            source_sheet = sheet_a or sheet_b or item.get("Sheet", "")
            rows.append({
                "Source": f"{item.get('Sheet','')}!{item.get('Cell','')}",
                "Referenced cell": f"{source_sheet}!{cell.upper()}",
                "External link": "Yes" if external else "No",
                "Formula": formula,
            })
    return rows

def _excel_source_fidelity(raw: bytes, filename: str) -> list[dict[str, Any]]:
    results = []
    if not str(filename).lower().endswith((".xlsx", ".xlsm")):
        return results
    try:
        import openpyxl
        keep_vba = str(filename).lower().endswith(".xlsm")
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=False, data_only=False, keep_vba=keep_vba, keep_links=False)
        for ws in book.worksheets:
            table_count = len(getattr(ws, "_tables", {}) or {})
            hyperlink_count = sum(1 for row in ws.iter_rows() for cell in row if getattr(cell, "hyperlink", None))
            comment_count = sum(1 for row in ws.iter_rows() for cell in row if getattr(cell, "comment", None))
            validation_count = len(getattr(ws, "data_validations", []).dataValidation) if getattr(ws, "data_validations", None) else 0
            results.append({
                "Sheet": ws.title,
                "State": ws.sheet_state,
                "Rows": ws.max_row,
                "Columns": ws.max_column,
                "Tables": table_count,
                "Merged ranges": len(ws.merged_cells.ranges),
                "Hyperlinks": hyperlink_count,
                "Comments": comment_count,
                "Data validations": validation_count,
                "Has VBA": "Yes" if keep_vba and getattr(book, "vba_archive", None) is not None else "No",
            })
        defined_names = list(getattr(book, "defined_names", {}).keys())
        results.append({
            "Sheet": "[Workbook]",
            "State": "—",
            "Rows": 0,
            "Columns": 0,
            "Tables": 0,
            "Merged ranges": 0,
            "Hyperlinks": 0,
            "Comments": 0,
            "Data validations": 0,
            "Has VBA": f"Named ranges: {len(defined_names):,}",
        })
        book.close()
    except Exception as exc:
        results.append({"Sheet": "[Workbook]", "State": "Review", "Error": f"{type(exc).__name__}: {exc}"})
    return results

def _excel_detect_locale(text: str) -> dict[str, Any]:
    lines = [line for line in str(text).splitlines() if line.strip()][:80]
    comma_decimal = int(sum(bool(re.search(r"\b\d{1,3},\d+\b", line)) for line in lines))
    dot_decimal = int(sum(bool(re.search(r"\b\d+\.\d+\b", line)) for line in lines))
    eu_thousands = int(sum(bool(re.search(r"\b\d{1,3}(?:\.\d{3})+,\d+\b", line)) for line in lines))
    date_eu = int(sum(bool(re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", line)) for line in lines))
    return {
        "Decimal style": "European candidate" if eu_thousands > 0 or comma_decimal > dot_decimal * 1.5 else "Dot-decimal candidate",
        "Comma-decimal signals": comma_decimal,
        "Dot-decimal signals": dot_decimal,
        "European thousands+decimal signals": eu_thousands,
        "Day/month date signals": date_eu,
    }

def _excel_detect_table_blocks(raw_df: pd.DataFrame, header_row: int) -> list[dict[str, Any]]:
    if raw_df.empty:
        return []
    body_start = max(0, header_row)
    blocks = []
    nonblank = ~raw_df.isna().all(axis=1)
    start = None
    blank_streak = 0
    for idx in range(body_start, len(raw_df)):
        if bool(nonblank.iloc[idx]):
            if start is None:
                start = idx
            blank_streak = 0
        else:
            blank_streak += 1
            if start is not None and blank_streak >= 1:
                end = idx - blank_streak
                if end >= start:
                    blocks.append((start, end))
                start = None
    if start is not None:
        blocks.append((start, len(raw_df) - 1))
    merged = []
    for start, end in blocks:
        block = raw_df.iloc[start:end + 1].copy()
        first_candidates = [_normalise_text(v) for v in block.iloc[0].tolist() if _normalise_text(v)] if len(block) else []
        if len(merged) and len(first_candidates) >= 2:
            prior = merged[-1]
            merged.append((start, end))
        else:
            merged.append((start, end))
    results = []
    for number, (start, end) in enumerate(merged, 1):
        frame = raw_df.iloc[start:end + 1].copy()
        local_header = _enhanced_detect_header_row(frame, scan_rows=min(12, len(frame)))
        headers = _deduplicate_headers(frame.iloc[local_header].tolist()) if not frame.empty else []
        data = frame.iloc[local_header + 1:].copy() if len(frame) else pd.DataFrame()
        if headers and not data.empty:
            data.columns = headers
        repeated = 0
        if headers and not data.empty:
            same = data.apply(lambda r: [_normalise_text(v) for v in r.tolist()] == headers, axis=1)
            repeated = int(same.sum())
            if repeated:
                data = data.loc[~same].copy()
        results.append({
            "Table ID": f"T{number:03d}",
            "Start row": int(start + 1),
            "End row": int(end + 1),
            "Header row": int(start + local_header + 1),
            "Rows": int(max(0, len(data))),
            "Columns": int(len(headers)),
            "Repeated header rows removed": repeated,
            "Headers": headers,
            "Frame": data.reset_index(drop=True),
        })
    return results

def _excel_table_catalog(raw_sheets: dict[str, pd.DataFrame]) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    catalog = []
    datasets = {}
    for sheet, raw_df in raw_sheets.items():
        header = _enhanced_detect_header_row(raw_df)
        blocks = _excel_detect_table_blocks(raw_df, header)
        for block in blocks:
            clean, audit = _final_clean_dataframe(block["Frame"])
            key = f"{sheet}::{block['Table ID']}"
            datasets[key] = clean
            catalog.append({
                "Dataset ID": key,
                "Sheet": sheet,
                "Table ID": block["Table ID"],
                "Start row": block["Start row"],
                "End row": block["End row"],
                "Header row": block["Header row"],
                "Rows": int(len(clean)),
                "Columns": int(len(clean.columns)),
                "Repeated header rows removed": block["Repeated header rows removed"],
                "Schema": _schema_fingerprint(clean),
                "Cleaning actions": len(audit),
            })
    return catalog, datasets

def _excel_schema_drift(old_df: pd.DataFrame, new_df: pd.DataFrame) -> dict[str, Any]:
    old_cols = {str(c).casefold(): (str(c), str(old_df[c].dtype)) for c in old_df.columns}
    new_cols = {str(c).casefold(): (str(c), str(new_df[c].dtype)) for c in new_df.columns}
    added = sorted(set(new_cols) - set(old_cols))
    removed = sorted(set(old_cols) - set(new_cols))
    type_changed = []
    renamed_candidates = []
    for common in sorted(set(old_cols) & set(new_cols)):
        if old_cols[common][1] != new_cols[common][1]:
            type_changed.append({
                "Field": new_cols[common][0], "Old type": old_cols[common][1], "New type": new_cols[common][1],
            })
    for old_key in removed:
        for new_key in added:
            sim = difflib.SequenceMatcher(None, old_key, new_key).ratio()
            if sim >= 0.72:
                renamed_candidates.append({"Removed field": old_cols[old_key][0], "Added field": new_cols[new_key][0], "Similarity": round(sim, 3)})
    return {
        "Added fields": [new_cols[x][0] for x in added],
        "Removed fields": [old_cols[x][0] for x in removed],
        "Type changes": type_changed,
        "Renamed field candidates": renamed_candidates,
        "Compatible": not removed and not type_changed,
    }

def _excel_apply_validation_rules(df: pd.DataFrame, rules: list[dict[str, Any]] | None = None, sheet: str = "") -> list[dict[str, Any]]:
    active = [r for r in (rules or _EXCEL_DEFAULT_RULES) if r.get("enabled", True)]
    results = []
    for rule in active:
        kind = str(rule.get("kind", ""))
        severity = str(rule.get("severity", "Medium"))
        if kind == "required_identifier":
            for col in df.columns:
                if _is_identifier(str(col), df[col]):
                    count = int(df[col].isna().sum())
                    if count:
                        results.append({"Rule": rule.get("rule"), "Sheet": str(sheet), "Field": str(col), "Status": "FAIL", "Severity": severity, "Violations": count, "Evidence": f"{count:,} identifier value(s) missing."})
        elif kind == "numeric_integrity":
            for col in df.columns:
                if _column_role(str(col), df[col]) == "Measure":
                    numeric = pd.to_numeric(df[col], errors="coerce")
                    bad = int(df[col].notna().sum() - numeric.notna().sum())
                    if bad:
                        results.append({"Rule": rule.get("rule"), "Field": str(col), "Status": "FAIL", "Severity": severity, "Violations": bad, "Evidence": f"{bad:,} non-numeric value(s) remain in a measure field."})
        elif kind == "percentage_range":
            for col in df.columns:
                bad = _percentage_range_count(str(col), df[col])
                if bad:
                    results.append({"Rule": rule.get("rule"), "Field": str(col), "Status": "FAIL", "Severity": severity, "Violations": bad, "Evidence": f"{bad:,} percentage/ratio value(s) outside 0..1."})
        elif kind == "date_range":
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    bad = _date_sanity_count(df[col])
                    if bad:
                        results.append({"Rule": rule.get("rule"), "Field": str(col), "Status": "FAIL", "Severity": severity, "Violations": bad, "Evidence": f"{bad:,} date(s) outside 1900..2100."})
    return results

def _excel_build_lineage_manifest(result: dict[str, Any]) -> dict[str, Any]:
    source_signature = str(result.get("signature", ""))
    manifest = {
        "lineage_version": "1.0",
        "dataset_id": "DS-" + source_signature[:16].upper(),
        "dataset_version": int(result.get("dataset_version", 1)),
        "source": {
            "filename": result.get("filename", ""),
            "sha256": source_signature,
            "source_type": result.get("import_diagnostics", {}).get("Source type", "Unknown"),
        },
        "structure": result.get("table_catalog", []),
        "schemas": {
            str(sheet): profile.get("Schema fingerprint", "")
            for sheet, profile in result.get("profiles", {}).items()
        },
        "governance": {
            "quality_scores": {str(k): v.get("Quality score", 0) for k, v in result.get("profiles", {}).items()},
            "review_items": len(result.get("review_register", [])),
            "validation_failures": len([x for x in result.get("validation_results", []) if x.get("Status") == "FAIL"]),
        },
        "mapping": result.get("semantic_mapping", []),
        "modules": result.get("module_readiness", []),
        "provenance": {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "transformation_recipe_version": "enterprise-1",
        },
    }
    return manifest

def _excel_export_json(result: dict[str, Any]) -> bytes:
    payload = _excel_build_lineage_manifest(result)
    payload["field_profile"] = result.get("field_profile", [])
    payload["validation_results"] = result.get("validation_results", [])
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode("utf-8")

def _excel_export_clean_csv(result: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    for sheet, frame in result.get("cleaned_sheets", {}).items():
        buf.write(f"### SHEET: {sheet}\n")
        buf.write(frame.to_csv(index=False))
    return buf.getvalue().encode("utf-8")

def _excel_export_parquet(result: dict[str, Any]) -> bytes | None:
    frames = result.get("cleaned_sheets", {})
    if len(frames) != 1:
        return None
    try:
        target = next(iter(frames.values()))
        return target.to_parquet(index=False)
    except Exception:
        return None

def _excel_remediation_preview(df: pd.DataFrame, action: str, field: str = "") -> pd.DataFrame:
    out = df.copy(deep=True)
    if action == "Trim text":
        for col in ([field] if field else list(out.columns)):
            if col in out.columns and (pd.api.types.is_object_dtype(out[col]) or pd.api.types.is_string_dtype(out[col])):
                out[col] = out[col].map(lambda v: _normalise_text(v) if isinstance(v, str) else v)
    elif action == "Normalize missing tokens":
        out, _ = _enhanced_null_normalise(out)
    elif action == "Remove exact duplicate rows":
        out = out.drop_duplicates().reset_index(drop=True)
    elif action == "Numeric coercion":
        if field and field in out.columns:
            out[field] = pd.to_numeric(out[field], errors="coerce")
    else:
        raise ValueError(f"Unsupported remediation: {action}")
    return out

def _excel_semantic_mapping(df: pd.DataFrame) -> list[dict[str, Any]]:
    mappings = []
    canonical = [
        ("Asset ID", "Asset", "asset_id"),
        ("Machine / Equipment", "Asset", "asset_name"),
        ("Process", "Process", "process_name"),
        ("SKU / Product", "Product", "product_id"),
        ("Material", "Material", "material_id"),
        ("Order / Work Order", "Order", "order_id"),
        ("Employee / Operator", "Workforce", "employee_id"),
        ("Defect / Scrap", "Quality", "defect_metric"),
        ("Failure / Downtime", "Maintenance", "failure_metric"),
        ("Energy", "Energy", "energy_value"),
        ("Cost / Price", "Cost", "cost_value"),
        ("Date / Timestamp", "Time", "timestamp"),
    ]
    for col in df.columns:
        text = str(col).casefold()
        scored = []
        for label, entity, field_name in canonical:
            tokens = re.findall(r"[a-z0-9]+", label.casefold())
            score = sum(1 for token in tokens if token in text)
            if _canonical_entity_hint(str(col)) == entity:
                score += 2
            if score:
                scored.append((score, label, entity, field_name))
        scored.sort(reverse=True)
        if scored:
            score, label, entity, field_name = scored[0]
            confidence = "High" if score >= 3 else "Medium"
            mappings.append({
                "Source field": str(col),
                "Canonical field": field_name,
                "Canonical entity": entity,
                "Suggested mapping": label,
                "Confidence": confidence,
                "Approved": False,
            })
        else:
            mappings.append({
                "Source field": str(col),
                "Canonical field": "",
                "Canonical entity": _canonical_entity_hint(str(col)),
                "Suggested mapping": "",
                "Confidence": "Low",
                "Approved": False,
            })
    return mappings

def _excel_persist_result(username: str, result: dict[str, Any]) -> bool:
    try:
        import streamlit as st
        catalog = st.session_state.setdefault("excel_studio_dataset_catalog", [])
        entry = _excel_build_lineage_manifest(result)
        entry["filename"] = result.get("filename", "")
        entry["saved_utc"] = datetime.now(timezone.utc).isoformat()
        entry["status"] = "active"
        signature = str(result.get("signature", ""))
        catalog[:] = [x for x in catalog if x.get("source", {}).get("sha256") != signature]
        catalog.append(entry)
        st.session_state["excel_studio_dataset_catalog"] = catalog[-50:]
        try:
            from workspace_persistence import save_user_workspace
            return bool(save_user_workspace(username, st.session_state))
        except Exception:
            return True
    except Exception:
        return False

def _excel_refresh_governance(result: dict[str, Any]) -> dict[str, Any]:
    cleaned = result.get("cleaned_sheets", {})
    result["field_profile"] = [row for sheet, df in cleaned.items() for row in _excel_profile_enrichment(df, sheet)]
    result["missingness_patterns"] = [row for sheet, df in cleaned.items() for row in _excel_missingness_patterns(df, sheet)]
    for row in result["missingness_patterns"]:
        row["Sheet"] = next((s for s, df in cleaned.items() if row["Field"] in [str(c) for c in df.columns]), row.get("Sheet", ""))
    result["duplicate_intelligence"] = [item for sheet, df in cleaned.items() for item in _excel_duplicate_intelligence(df, sheet)]
    result["extended_outliers"] = [item for sheet, df in cleaned.items() for item in _excel_extended_outlier_findings(df, sheet)]
    result["engineering_limit_findings"] = [item for sheet, df in cleaned.items() for item in _excel_engineering_limits(df, sheet, result.get("engineering_limits", {}))]
    result["semantic_mapping"] = [item for sheet, df in cleaned.items() for item in _excel_semantic_mapping(df)]
    result["validation_results"] = [item for sheet, df in cleaned.items() for item in _excel_apply_validation_rules(df, result.get("validation_rules", _EXCEL_DEFAULT_RULES), sheet)]
    result["formula_dependencies"] = _excel_formula_dependencies(result.get("formula_inventory", []))
    result["formula_gap_findings"] = _excel_formula_gap_scan(result.get("formula_inventory", []))
    result["security_scan"] = _excel_security_scan(cleaned)
    result["review_register"].extend(result.get("formula_gap_findings", []))
    for item in result.get("security_scan", []):
        result["review_register"].append({
            "Severity": "High",
            "Sheet": item["Sheet"],
            "Field": item["Field"],
            "Issue": "Potential secret/security exposure",
            "Evidence": f"{item['Indicator']}: {item['Matches']:,} match(es).",
            "Recommended action": item["Action"],
        })
    result["source_fidelity"] = _excel_source_fidelity(result.get("_raw_bytes", b""), result.get("filename", ""))
    result["unit_catalog"] = [
        {"Sheet": sheet, "Field": str(col), "Detected unit": _excel_unit_token(str(col)),
         "Convertible targets": ", ".join(sorted(
             [u for u in _EXCEL_UNIT_FACTORS if _EXCEL_UNIT_FACTORS[u][0] == _EXCEL_UNIT_FACTORS.get(_excel_unit_token(str(col)), ("", 0))[0]]
         ))}
        for sheet, frame in cleaned.items() for col in frame.columns if _excel_unit_token(str(col))
    ]
    reviews = list(result.get("review_register", []))
    reviews.extend(result["extended_outliers"])
    reviews.extend(result["engineering_limit_findings"])
    for item in result["duplicate_intelligence"]:
        reviews.append({
            "Severity": "Medium",
            "Sheet": item["Sheet"],
            "Field": item.get("Fields", ""),
            "Issue": item["Review"],
            "Evidence": item.get("Source variants", f"{item.get('Occurrences', 0):,} occurrence(s)"),
            "Recommended action": item["Recommended action"],
        })
    for item in result["validation_results"]:
        if item["Status"] == "FAIL":
            reviews.append({
                "Severity": item.get("Severity", "High"),
                "Sheet": item.get("Sheet", ""),
                "Field": item.get("Field", ""),
                "Issue": f"Validation rule failed: {item.get('Rule', '')}",
                "Evidence": item.get("Evidence", ""),
                "Recommended action": "Correct or explicitly approve the exception before downstream analysis.",
            })
    result["review_register"] = reviews
    return result

_BASE_EXCEL_ENGINE_PROCESS = process_uploaded_workbook

def _excel_engine_read(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    if not raw:
        raise ValueError("The uploaded file is empty.")
    lower = str(filename).lower()
    if lower.endswith((".csv", ".tsv", ".txt")):
        text, encoding = _decode_text_bytes(raw)
        if "\\n" in text and "\n" not in text and "\r" not in text:
            text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
        if lower.endswith(".tsv"):
            delimiter = "\t"
        else:
            delimiter = _choose_csv_delimiter(text)
        frame = pd.read_csv(
            io.StringIO(text),
            header=None,
            dtype=object,
            sep=delimiter,
            keep_default_na=False,
            na_filter=False,
        )
        frame.attrs["source_encoding"] = encoding
        frame.attrs["source_delimiter"] = delimiter
        return {"CSV" if lower.endswith(".csv") else "TEXT": frame}
    if lower.endswith((".xlsx", ".xlsm")):
        import openpyxl
        keep_vba = lower.endswith(".xlsm")
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False, keep_vba=keep_vba)
        try:
            return {
                str(ws.title): pd.DataFrame(list(ws.values), dtype=object)
                for ws in book.worksheets
            }
        finally:
            book.close()
    if lower.endswith(".xls"):
        try:
            return {"XLS": pd.read_excel(io.BytesIO(raw), header=None, dtype=object, engine="xlrd")}
        except ImportError as exc:
            raise ValueError("Legacy .xls import requires the xlrd dependency; the workbook was not modified.") from exc
    raise ValueError("Supported imports are .xlsx, .xlsm, .xls, .csv, .tsv and .txt.")

def _excel_process(raw: bytes, filename: str) -> dict[str, Any]:
    # Temporarily replace the reader used by the existing definitive pipeline.
    global _definitive_read_raw_workbook
    previous = _definitive_read_raw_workbook
    try:
        _definitive_read_raw_workbook = _excel_engine_read
        result = _definitive_process_uploaded_workbook(raw, filename)
    finally:
        _definitive_read_raw_workbook = previous
    result["_raw_bytes"] = raw
    result["import_diagnostics"] = {
        "Source type": ("XLSX/XLSM" if str(filename).lower().endswith((".xlsx", ".xlsm")) else
                        "XLS" if str(filename).lower().endswith(".xls") else
                        "TSV" if str(filename).lower().endswith(".tsv") else
                        "CSV/TXT"),
        "Filename": str(filename),
        "File size KB": round(len(raw) / 1024, 1),
        "SHA256": hashlib.sha256(raw).hexdigest(),
    }
    if str(filename).lower().endswith((".csv", ".tsv", ".txt")):
        try:
            text, encoding = _decode_text_bytes(raw)
            result["import_diagnostics"].update(_excel_detect_locale(text))
            result["import_diagnostics"]["Encoding"] = encoding
            result["import_diagnostics"]["Delimiter"] = "\t" if str(filename).lower().endswith(".tsv") else _choose_csv_delimiter(text)
        except Exception:
            pass
    table_catalog, table_datasets = _excel_table_catalog(result.get("raw_sheets", {}))
    result["table_catalog"] = table_catalog
    result["table_datasets"] = table_datasets
    result["dataset_version"] = 1
    result["semantic_mapping"] = [item for sheet, df in result["cleaned_sheets"].items() for item in _excel_semantic_mapping(df)]
    result["ingest_guardrails"] = {
        "Large file": len(raw) >= 25 * 1024 * 1024,
        "Very large file": len(raw) >= 100 * 1024 * 1024,
        "Cell volume": sum(int(df.shape[0] * df.shape[1]) for df in result["raw_sheets"].values()),
        "Processing mode": "chunk-aware CSV/text" if str(filename).lower().endswith((".csv", ".tsv", ".txt")) else "workbook",
    }
    _excel_refresh_governance(result)
    result["lineage_manifest"] = _excel_build_lineage_manifest(result)
    result["xlsx"] = _append_governance_plus_to_workbook(result["xlsx"], result)
    result["xlsx"] = _postprocess_export_guardrails(result["xlsx"])
    result["xlsx"] = _reconcile_clean_sheet_payload(result["xlsx"], result["cleaned_sheets"])
    result["bundle"] = build_ultimate_bundle(
        f"Shoir-IE — {result['filename']}",
        result["xlsx"], result["audits"], result["profiles"],
        cleaned_sheets=result.get("cleaned_sheets", {}),
        raw_sheets=result.get("raw_sheets", {}),
        field_intelligence=result.get("field_intelligence", []),
        review_register=result.get("review_register", []),
        source_metadata=result.get("source_metadata", []),
    )
    return result

def process_uploaded_workbook(raw: bytes, filename: str) -> dict[str, Any]:
    return _excel_process(raw, filename)


def _excel_formula_gap_scan(formula_inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    groups: dict[tuple[str, str], list[int]] = {}
    for item in formula_inventory:
        cell = str(item.get("Cell", ""))
        match = re.fullmatch(r"([A-Za-z]{1,3})(\d+)", cell)
        if match:
            groups.setdefault((str(item.get("Sheet", "")), match.group(1).upper()), []).append(int(match.group(2)))
    for (sheet, col), rows in groups.items():
        rows = sorted(set(rows))
        if len(rows) < 4:
            continue
        gaps: list[int] = []
        for left, right in zip(rows, rows[1:]):
            if right - left > 1:
                gaps.extend(range(left + 1, right))
        if gaps:
            findings.append({
                "Severity": "Medium",
                "Sheet": sheet,
                "Field": col,
                "Issue": "Potential formula gap",
                "Evidence": f"{len(gaps):,} row(s) sit between formula cells in column {col}.",
                "Affected rows": ", ".join(str(x) for x in gaps[:25]),
                "Recommended action": "Check whether missing cells should contain copied formulas or intentional blanks.",
            })
    return findings

def _excel_security_scan(cleaned: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for sheet, frame in cleaned.items():
        for col in frame.columns:
            values = frame[col].dropna().astype(str).head(5000)
            for label, pattern in _EXCEL_SECRET_PATTERNS:
                hits = int(values.map(lambda value: bool(pattern.search(value))).sum())
                if hits:
                    results.append({
                        "Sheet": sheet,
                        "Field": str(col),
                        "Indicator": label,
                        "Matches": hits,
                        "Action": "Mask/remove secrets before sharing or exporting this dataset.",
                    })
                    break
    return results

def _excel_custom_rule_results(df: pd.DataFrame, rules: list[dict[str, Any]], sheet: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        field = str(rule.get("field", ""))
        operator = str(rule.get("operator", ""))
        value = rule.get("value")
        if field not in df.columns:
            results.append({
                "Rule": rule.get("name", "Custom rule"),
                "Sheet": sheet,
                "Field": field,
                "Status": "FAIL",
                "Severity": rule.get("severity", "High"),
                "Violations": len(df),
                "Evidence": f"Configured field '{field}' does not exist.",
            })
            continue
        series = df[field]
        if operator in {">", ">=", "<", "<=", "==", "!="}:
            numeric = pd.to_numeric(series, errors="coerce")
            try:
                target = float(value)
                if operator == ">": mask = numeric <= target
                elif operator == ">=": mask = numeric < target
                elif operator == "<": mask = numeric >= target
                elif operator == "<=": mask = numeric > target
                elif operator == "==": mask = numeric != target
                else: mask = numeric == target
            except Exception:
                mask = pd.Series(True, index=df.index)
        elif operator == "is not null":
            mask = series.isna()
        elif operator == "is null":
            mask = series.notna()
        elif operator == "in":
            allowed = {x.strip().casefold() for x in str(value).split(",") if x.strip()}
            mask = ~series.astype("string").fillna("").str.casefold().isin(allowed)
        elif operator == "not in":
            denied = {x.strip().casefold() for x in str(value).split(",") if x.strip()}
            mask = series.astype("string").fillna("").str.casefold().isin(denied)
        elif operator == "regex":
            try:
                mask = ~series.astype("string").fillna("").str.contains(str(value), regex=True, na=False)
            except Exception:
                mask = pd.Series(True, index=df.index)
        else:
            continue
        violations = int(mask.sum())
        results.append({
            "Rule": rule.get("name", "Custom rule"),
            "Sheet": sheet,
            "Field": field,
            "Status": "FAIL" if violations else "PASS",
            "Severity": rule.get("severity", "Medium"),
            "Violations": violations,
            "Evidence": f"{violations:,} row(s) violate the rule." if violations else "No violations.",
        })
    return results

def _excel_reference_check(clean_df: pd.DataFrame, reference_df: pd.DataFrame, key: str) -> dict[str, Any]:
    if key not in clean_df.columns or key not in reference_df.columns:
        return {"Status": "FAIL", "Reason": f"Key '{key}' must exist in both datasets."}
    left = set(clean_df[key].dropna().astype("string").str.strip())
    right = set(reference_df[key].dropna().astype("string").str.strip())
    unmatched = sorted(left - right)
    return {
        "Status": "PASS" if not unmatched else "REVIEW",
        "Key": key,
        "Input distinct keys": len(left),
        "Reference distinct keys": len(right),
        "Matched keys": len(left & right),
        "Unmatched input keys": len(unmatched),
        "Reference coverage %": round(100.0 * len(left & right) / max(1, len(left)), 2),
        "Sample unmatched": " | ".join(unmatched[:20]),
    }

def _excel_render_professional(tier: str, username: str) -> None:
    import streamlit as st
    from shoir_tier_capabilities import tier_allows
    if not tier_allows(tier, "Starter"):
        st.warning("This workspace is not included in your current package.")
        return
    st.markdown("## 📊 Excel Intelligence & Data Cleaning Studio")
    st.caption("One guided path: Import → Understand → Clean → Validate → Map → Remediate → Visualize → Activate → Export.")
    left, right = st.columns([5, 1])
    upload = left.file_uploader(
        "Drop an Excel/CSV/TSV/TXT file",
        type=["xlsx", "xlsm", "xls", "csv", "tsv", "txt"],
        key="excel_studio_upload",
        help="Messy reports, industrial exports, legacy Excel and delimited text are supported.",
    )
    if right.button("Clear", key="excel_studio_clear_enterprise", use_container_width=True):
        for key in [
            "excel_studio_signature", "excel_studio_result", "excel_studio_sheet",
            "excel_studio_visual_df", "excel_studio_active_dataset",
        ]:
            st.session_state.pop(key, None)
        st.rerun()
    if upload is not None:
        raw = upload.getvalue()
        signature = hashlib.sha256(raw).hexdigest()
        if st.session_state.get("excel_studio_signature") != signature:
            try:
                with st.spinner("Profiling, cleaning and governing the workbook…"):
                    result = process_uploaded_workbook(raw, upload.name)
                st.session_state["excel_studio_signature"] = signature
                st.session_state["excel_studio_result"] = result
                versions = st.session_state.setdefault("excel_studio_versions", [])
                previous = versions[-1] if versions else None
                current_snapshot = {
                    "dataset_id": result["lineage_manifest"]["dataset_id"],
                    "version": len(versions) + 1,
                    "filename": upload.name,
                    "sha256": signature,
                    "schema": {k: v.get("Schema fingerprint", "") for k, v in result["profiles"].items()},
                    "columns": {k: [str(col) for col in frame.columns] for k, frame in result["cleaned_sheets"].items()},
                    "imported_utc": datetime.now(timezone.utc).isoformat(),
                }
                if previous:
                    old_columns = previous.get("columns", {})
                    current_dfs = result.get("cleaned_sheets", {})
                    current_snapshot["schema_drift"] = {
                        sheet: _excel_schema_drift(
                            pd.DataFrame(columns=list(old_columns.get(sheet, []))),
                            pd.DataFrame(columns=[str(col) for col in frame.columns]),
                        )
                        for sheet, frame in current_dfs.items()
                        if sheet in old_columns
                    }
                versions.append(current_snapshot)
                st.session_state["excel_studio_versions"] = versions[-25:]
                _excel_persist_result(username, result)
                st.success(f"Processed {len(result['cleaned_sheets']):,} source sheet(s) and discovered {len(result.get('table_catalog', [])):,} analytical table(s).")
            except Exception as exc:
                st.error(f"Excel could not be transformed safely: {type(exc).__name__}: {exc}")
    result = st.session_state.get("excel_studio_result")
    if not isinstance(result, dict):
        st.info("Upload a file to activate the guided industrial data workflow.")
        return
    cleaned = result.get("cleaned_sheets", {})
    profiles = result.get("profiles", {})
    scores = [float(v.get("Quality score", 0)) for v in profiles.values()]
    high_reviews = sum(1 for x in result.get("review_register", []) if x.get("Severity") == "High")
    c = st.columns(6)
    c[0].metric("Sheets", len(cleaned))
    c[1].metric("Tables", len(result.get("table_catalog", [])))
    c[2].metric("Rows", f"{sum(len(v) for v in cleaned.values()):,}")
    c[3].metric("Avg quality", f"{float(np.mean(scores)):.1f}%" if scores else "—")
    c[4].metric("Review items", len(result.get("review_register", [])))
    c[5].metric("Validation fails", len([x for x in result.get("validation_results", []) if x.get("Status") == "FAIL"]))
    tabs = st.tabs(["1 · Import", "2 · Structure", "3 · Quality", "4 · Map", "5 · Remediate", "6 · Visualize", "7 · Activate", "8 · Version & Export"])
    with tabs[0]:
        st.subheader("Import diagnostics")
        st.dataframe(pd.DataFrame([result.get("import_diagnostics", {})]), use_container_width=True, hide_index=True)
        st.markdown("### What will happen")
        st.write("The original source is retained. Cleaning is conservative. Statistical outliers are flagged, not deleted. Sensitive-field scans retain indicators, not raw values.")
        if result.get("ingest_guardrails", {}).get("Large file"):
            st.warning("Large-file guardrail: the upload is sizeable. Shoir-IE will keep analysis bounded and may sample plots.")
    with tabs[1]:
        st.subheader("Discovered analytical tables")
        catalog = pd.DataFrame(result.get("table_catalog", []))
        if catalog.empty:
            st.info("No independent table blocks were detected.")
        else:
            st.dataframe(catalog, use_container_width=True, hide_index=True)
            labels = catalog["Dataset ID"].tolist()
            chosen = st.selectbox("Open table", labels, key="excel_studio_table_choice")
            if chosen in result.get("table_datasets", {}):
                st.dataframe(result["table_datasets"][chosen].head(1000), use_container_width=True, hide_index=True)
                if st.button("Make this the active dataset", key="excel_studio_activate_table", use_container_width=True):
                    result["active_table_id"] = chosen
                    result["active_table_df"] = result["table_datasets"][chosen].copy(deep=True)
                    st.session_state["excel_studio_result"] = result
                    st.session_state["excel_studio_active_dataset"] = chosen
                    st.success("Active dataset changed. Continue to Map, Visualize or Activate.")
    with tabs[2]:
        st.subheader("Quality & validation")
        q1, q2 = st.columns(2)
        with q1:
            st.dataframe(pd.DataFrame(result.get("validation_results", [])), use_container_width=True, hide_index=True)
            st.dataframe(pd.DataFrame(result.get("missingness_patterns", [])), use_container_width=True, hide_index=True)
        with q2:
            st.dataframe(pd.DataFrame(result.get("extended_outliers", [])), use_container_width=True, hide_index=True)
            st.dataframe(pd.DataFrame(result.get("duplicate_intelligence", [])), use_container_width=True, hide_index=True)
        with st.expander("Source fidelity", expanded=False):
            st.dataframe(pd.DataFrame(result.get("source_fidelity", [])), use_container_width=True, hide_index=True)
        with st.expander("Formula lineage", expanded=False):
            st.dataframe(pd.DataFrame(result.get("formula_dependencies", [])), use_container_width=True, hide_index=True)
    with tabs[3]:
        st.subheader("Data Mapper")
        frames = result.get("table_datasets", {}) or cleaned
        if not frames:
            st.info("No clean dataset available.")
        else:
            active_key = st.session_state.get("excel_studio_active_dataset")
            if active_key in frames:
                map_df = frames[active_key]
            else:
                map_df = next(iter(frames.values()))
            mapping_df = pd.DataFrame(_excel_semantic_mapping(map_df))
            if not mapping_df.empty:
                edited = st.data_editor(mapping_df, use_container_width=True, hide_index=True, key="excel_studio_mapping_editor")
                if st.button("Approve selected mappings", key="excel_studio_approve_mapping", type="primary"):
                    result["semantic_mapping"] = edited.to_dict("records")
                    st.session_state["excel_studio_result"] = result
                    _excel_persist_result(username, result)
                    st.success("Mappings saved to the workspace.")
    with tabs[4]:
        st.subheader("Safe remediation")
        active = result.get("active_table_df")
        if not isinstance(active, pd.DataFrame):
            active = next(iter(cleaned.values())) if cleaned else pd.DataFrame()
        action = st.selectbox("Remediation", ["Trim text", "Normalize missing tokens", "Remove exact duplicate rows", "Numeric coercion"], key="excel_studio_remediation")
        field_options = ["All"] + [str(c) for c in active.columns]
        field = st.selectbox("Field", field_options, key="excel_studio_remediation_field")
        target_field = "" if field == "All" else field
        try:
            preview = _excel_remediation_preview(active, action, target_field)
            before_after_rows = []
            for col in active.columns:
                before_after_rows.append({
                    "Field": str(col),
                    "Rows before": len(active),
                    "Rows after": len(preview),
                    "Missing before": int(active[col].isna().sum()),
                    "Missing after": int(preview[col].isna().sum()),
                })
            st.dataframe(pd.DataFrame(before_after_rows), use_container_width=True, hide_index=True)
            if st.button("Apply remediation", key="excel_studio_apply_remediation", type="primary"):
                if result.get("active_table_id") and result["active_table_id"] in result.get("table_datasets", {}):
                    result["table_datasets"][result["active_table_id"]] = preview.copy(deep=True)
                else:
                    first_sheet = next(iter(cleaned), None)
                    if first_sheet:
                        result["cleaned_sheets"][first_sheet] = preview.copy(deep=True)
                result["active_table_df"] = preview.copy(deep=True)
                _excel_refresh_governance(result)
                _rebuild_excel_result(result)
                st.session_state["excel_studio_result"] = result
                _excel_persist_result(username, result)
                st.success("Remediation applied and governance metrics refreshed.")
                st.rerun()
        except Exception as exc:
            st.error(f"Remediation preview failed safely: {exc}")
    with tabs[5]:
        st.subheader("Universal visualization")
        frames = result.get("table_datasets", {}) or cleaned
        labels = list(frames)
        if not labels:
            st.info("No clean table available.")
        else:
            choice = st.selectbox("Dataset", labels, key="excel_studio_visual_dataset")
            frame = frames[choice]
            st.session_state["excel_studio_visual_df"] = frame.copy(deep=True)
            try:
                from shoir_universal_engine import guaranteed_figure
                fig = guaranteed_figure(frame, f"Excel Studio · {choice}")
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
            except Exception:
                pass
            numeric = [str(c) for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
            categorical = [str(c) for c in frame.columns if str(c) not in numeric]
            if numeric:
                metric = st.selectbox("Metric", numeric, key="excel_studio_chart_metric")
                chart = px.histogram(frame, x=metric, nbins=30, title=f"{metric} distribution")
                st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False, "responsive": True})
            if categorical and numeric:
                cat = st.selectbox("Group", categorical, key="excel_studio_chart_group")
                metric = st.session_state.get("excel_studio_chart_metric", numeric[0])
                grouped = frame.groupby(cat, dropna=False)[metric].mean().reset_index()
                chart = px.bar(grouped.head(60), x=cat, y=metric, title=f"{metric} by {cat}")
                st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False, "responsive": True})
    with tabs[6]:
        st.subheader("Activate the cleaned dataset")
        st.write("This hand-off avoids re-uploading the same Excel file into another Shoir-IE module.")
        frames = result.get("table_datasets", {}) or cleaned
        for name in list(frames)[:12]:
            if st.button(f"Send {name} to Universal Engine / Industrial Workbook", key="excel_studio_activate_" + hashlib.sha1(name.encode()).hexdigest()[:10], use_container_width=True):
                frame = frames[name].copy(deep=True)
                st.session_state["excel_studio_active_dataset"] = name
                st.session_state["excel_studio_active_dataset_df"] = frame
                st.session_state["universal_active_dataset"] = frame
                st.session_state["industrial_workbook_current_df"] = frame
                st.session_state["data_platform_latest_df"] = frame
                result["active_table_id"] = name
                result["active_table_df"] = frame
                result["activation_contract"] = {
                    "dataset": name,
                    "rows": len(frame),
                    "columns": len(frame.columns),
                    "quality": float(np.mean([p.get("Quality score", 0) for p in profiles.values()])) if profiles else 0.0,
                    "activated_utc": datetime.now(timezone.utc).isoformat(),
                    "next_step": "Use the receiving module without re-uploading.",
                }
                st.session_state["excel_studio_result"] = result
                _excel_persist_result(username, result)
                st.success(f"{name} activated in the workspace.")
        st.subheader("Recommended workflows")
        st.dataframe(pd.DataFrame(result.get("module_readiness", [])), use_container_width=True, hide_index=True)
    with tabs[7]:
        st.subheader("Dataset versions")
        st.dataframe(pd.DataFrame(st.session_state.get("excel_studio_versions", [])), use_container_width=True, hide_index=True)
        st.download_button("Export lineage JSON", _excel_export_json(result), file_name="shoir_ie_excel_lineage.json", mime="application/json", use_container_width=True)
        st.download_button("Export clean CSV package", _excel_export_clean_csv(result), file_name="shoir_ie_excel_clean.csv", mime="text/csv", use_container_width=True)
        parquet = _excel_export_parquet(result)
        if parquet:
            st.download_button("Export Parquet", parquet, file_name="shoir_ie_excel_clean.parquet", mime="application/octet-stream", use_container_width=True)
        st.download_button("Download Industrial XLSX", result["xlsx"], file_name="shoir_ie_industrial_clean.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
        st.download_button("Download Evidence ZIP", result["bundle"], file_name="shoir_ie_excel_evidence.zip", mime="application/zip", use_container_width=True)

# Final UI binding for the application import surface.
render_excel_data_cleaning_studio = _excel_render_professional
