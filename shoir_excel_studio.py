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
