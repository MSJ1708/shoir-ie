"""Safe, lazy Excel ingestion surface for Shoir-IE.

The production Excel module used to build the full XLSX + ZIP evidence package
while handling the upload event. On large workbooks that could spike memory
before Streamlit had a chance to render the page. This module separates:
1) upload/clean/inspect (fast path), from
2) workbook/evidence export (explicit user action).

It reuses the existing Excel Intelligence cleaning primitives, so domain
semantics and governance rules remain centralized.
"""
from __future__ import annotations

import hashlib
import json
import io
import logging
import math
import re
import zipfile
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd
import streamlit as st

MAX_UPLOAD_BYTES = 75 * 1024 * 1024
MAX_OOXML_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_OOXML_MEMBER_BYTES = 256 * 1024 * 1024
MAX_OOXML_MEMBER_COUNT = 10_000
MAX_OOXML_COMPRESSION_RATIO = 500
MAX_FORMULA_SCAN_CELLS = 2_000_000
MAX_FORMULA_INVENTORY_ROWS = 10_000
MAX_RENDER_PREVIEW_ROWS = 2_000
MAX_RENDER_PREVIEW_COLUMNS = 50
MAX_RENDER_JSON_CHARS = 250_000
MAX_RENDER_CHART_POINTS = 20_000

_LOGGER = logging.getLogger(__name__)


def _log_excel_error(context: str, error: Exception) -> str:
    """Log diagnostic details server-side and return a non-sensitive reference ID."""
    reference = uuid.uuid4().hex[:12].upper()
    _LOGGER.error(
        "Excel Intelligence failure %s in %s",
        reference,
        context,
        exc_info=(type(error), error, error.__traceback__),
    )
    return reference


def bounded_excel_preview(frame: pd.DataFrame, max_rows: int = MAX_RENDER_PREVIEW_ROWS,
                          max_columns: int = MAX_RENDER_PREVIEW_COLUMNS) -> pd.DataFrame:
    """Return a display-only slice so very wide/large workbooks cannot overwhelm Streamlit."""
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    rows = max(1, min(int(max_rows), MAX_RENDER_PREVIEW_ROWS))
    columns = max(1, min(int(max_columns), MAX_RENDER_PREVIEW_COLUMNS))
    return frame.iloc[:rows, :columns]


def _excel_display_scalar(value: Any, max_text_length: int = 2000) -> Any:
    """Convert non-scalar/mixed object cells to Arrow-safe display-only text."""
    if value is None:
        return pd.NA
    try:
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and bool(missing):
            return pd.NA
    except (TypeError, ValueError):
        pass

    if isinstance(value, bytes):
        rendered = value.decode("utf-8", errors="replace")
    elif isinstance(value, str):
        rendered = value
    elif isinstance(value, (bool, int, float, np.integer, np.floating, np.bool_)):
        rendered = str(value)
    else:
        try:
            rendered = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            rendered = str(value)

    rendered = str(rendered)
    if len(rendered) > max_text_length:
        rendered = rendered[: max_text_length - 1] + "…"
    return rendered


def _safe_excel_display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Build a display-only frame with unique string headers and safe object cells."""
    display = frame.copy(deep=True).reset_index(drop=True)
    names: list[str] = []
    seen: dict[str, int] = {}
    for original in display.columns:
        base = str(original)
        seen[base] = seen.get(base, 0) + 1
        names.append(base if seen[base] == 1 else f"{base} ({seen[base]})")
    display.columns = names

    # Streamlit's Arrow serializer can reject mixed Python objects, nested cells
    # and custom values. Convert only object-typed cells in this display copy;
    # analytical/source DataFrames remain untouched.
    for position in range(display.shape[1]):
        if pd.api.types.is_object_dtype(display.iloc[:, position].dtype):
            display[names[position]] = pd.array(
                [_excel_display_scalar(value) for value in display.iloc[:, position].tolist()],
                dtype="string",
            )
    return display


def _render_excel_dataframe(frame: pd.DataFrame, label: str) -> None:
    """Render a bounded Arrow-safe table and degrade to text if rendering fails."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        st.info(f"{label} is empty or not available yet.")
        return

    bounded = bounded_excel_preview(frame)
    has_object_cells = any(
        pd.api.types.is_object_dtype(bounded.dtypes.iloc[position])
        for position in range(bounded.shape[1])
    )
    preview = _safe_excel_display_frame(bounded)
    try:
        st.dataframe(preview, width="stretch", hide_index=True)
    except Exception as exc:
        _log_excel_error("dataframe rendering", exc)
        st.warning(
            f"{label} could not be displayed as an interactive table. "
            "Showing a small text preview instead."
        )
        try:
            st.text(preview.iloc[:50, :20].to_string(index=False, max_rows=50, max_cols=20))
        except Exception as fallback_exc:
            _log_excel_error("dataframe text fallback rendering", fallback_exc)
            st.error(f"{label} could not be rendered. The underlying data remains available for export.")

    if has_object_cells:
        st.caption(
            "Mixed/nested values are shown as text and text longer than 2,000 characters is shortened "
            "in this display only. The underlying data and exports are unchanged."
        )

    if len(frame) > len(preview) or len(frame.columns) > len(preview.columns):
        st.caption(
            f"Showing {len(preview):,} row(s) and {len(preview.columns):,} column(s) in this preview "
            f"from {len(frame):,} row(s) and {len(frame.columns):,} column(s). "
            "The source data is not truncated by this display limit."
        )


def _render_excel_plotly_figure(figure: Any, label: str = "Analysis chart") -> None:
    """Render Plotly only when its point count is safe for the browser."""
    if figure is None:
        return
    try:
        point_count = 0
        for trace in getattr(figure, "data", ()):
            trace_points = []
            for attribute in ("x", "y", "z", "values", "labels"):
                values = getattr(trace, attribute, None)
                if values is not None:
                    try:
                        trace_points.append(len(values))
                    except (TypeError, ValueError):
                        continue
            point_count += max(trace_points, default=0)

        if point_count > MAX_RENDER_CHART_POINTS:
            st.warning(
                f"{label} contains {point_count:,} plotted points, above the "
                f"{MAX_RENDER_CHART_POINTS:,}-point display limit. The chart was not drawn "
                "to protect the browser; the full result table and evidence remain available."
            )
            return
        st.plotly_chart(figure, width="stretch")
    except Exception as exc:
        _log_excel_error("chart rendering", exc)
        st.warning(
            f"{label} could not be rendered. The underlying analysis table and evidence remain available."
        )


def _render_excel_json(value: Any, label: str) -> None:
    """Render JSON-safe, bounded evidence with a readable fallback."""
    try:
        serialized = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except Exception as exc:
        _log_excel_error("JSON evidence formatting", exc)
        st.warning(f"{label} could not be formatted. The complete evidence remains downloadable.")
        try:
            st.text(str(value)[:MAX_RENDER_JSON_CHARS])
        except Exception:
            st.error(f"{label} could not be rendered. The full evidence remains in the downloadable package.")
        return

    if len(serialized) > MAX_RENDER_JSON_CHARS:
        st.code(serialized[:MAX_RENDER_JSON_CHARS], language="json")
        st.caption(
            f"{label} preview shortened to {MAX_RENDER_JSON_CHARS:,} characters. "
            "The complete evidence remains in the downloadable package."
        )
        return

    try:
        st.json(json.loads(serialized))
    except Exception as exc:
        _log_excel_error("interactive JSON evidence rendering", exc)
        st.warning(f"{label} could not be displayed interactively. A text fallback is shown below.")
        try:
            st.code(serialized, language="json")
        except Exception as fallback_exc:
            _log_excel_error("JSON text fallback rendering", fallback_exc)
            st.error(f"{label} could not be rendered. The full evidence remains in the downloadable package.")


def _validate_ooxml_package(raw: bytes, filename: str) -> None:
    """Reject oversized, suspicious or path-traversing OOXML packages before parsing."""
    lower = str(filename or "").casefold()
    if not lower.endswith((".xlsx", ".xlsm")):
        return

    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as package:
            members = package.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("The uploaded Excel workbook is not a valid OOXML package.") from exc

    if not members:
        raise ValueError("The uploaded Excel workbook package is empty.")
    if len(members) > MAX_OOXML_MEMBER_COUNT:
        raise ValueError(
            f"The workbook contains too many package members ({len(members):,}); "
            f"the limit is {MAX_OOXML_MEMBER_COUNT:,}."
        )

    total_uncompressed = 0
    seen_names: set[str] = set()
    for member in members:
        normalized = str(member.filename or "").replace(chr(92), "/")
        clean_path = normalized.rstrip("/")
        parts = clean_path.split("/")
        drive_qualified = bool(parts and re.match(r"^[A-Za-z]:", parts[0]))
        if (
            not clean_path
            or chr(0) in normalized
            or normalized.startswith("/")
            or drive_qualified
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("The workbook contains an unsafe package path.")
        path_key = normalized.casefold()
        if path_key in seen_names:
            raise ValueError("The workbook contains duplicate package member paths.")
        seen_names.add(path_key)

        # Excel OOXML packages use stored/deflated members. Reject exotic
        # compression and symlink entries rather than relying on downstream
        # parsers to interpret them consistently.
        if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ValueError("The workbook contains an unsupported package compression method.")
        unix_mode = (int(member.external_attr) >> 16) & 0o170000
        if unix_mode == 0o120000:
            raise ValueError("Symbolic links are not supported in workbook packages.")

        if member.flag_bits & 0x1:
            raise ValueError("Encrypted workbook package members are not supported.")
        if member.file_size > MAX_OOXML_MEMBER_BYTES:
            raise ValueError(
                f"Workbook package member {normalized!r} exceeds the "
                f"{MAX_OOXML_MEMBER_BYTES / (1024 * 1024):.0f} MB safety limit."
            )
        total_uncompressed += int(member.file_size)
        if total_uncompressed > MAX_OOXML_UNCOMPRESSED_BYTES:
            raise ValueError(
                "The workbook expands beyond the allowed uncompressed package size "
                f"of {MAX_OOXML_UNCOMPRESSED_BYTES / (1024 * 1024):.0f} MB."
            )

        if member.file_size and not member.compress_size:
            raise ValueError("The workbook contains a suspicious zero-byte compressed member.")
        if member.compress_size:
            ratio = float(member.file_size) / float(member.compress_size)
            if ratio > MAX_OOXML_COMPRESSION_RATIO:
                raise ValueError(
                    "The workbook contains an unusually compressed package member; "
                    "the upload was rejected to protect processing resources."
                )


def _load_primitives():
    from shoir_excel_studio import (
        _deduplicate_headers,
        _enhanced_clean_dataframe,
        _enhanced_detect_header_row,
        _enhanced_read_raw_workbook,
        _enhanced_profile_dataframe,
        _field_intelligence_rows,
        _quality_review_register,
        _cross_sheet_map,
        build_ultimate_workbook,
        build_ultimate_bundle,
    )
    return {
        "deduplicate_headers": _deduplicate_headers,
        "clean": _enhanced_clean_dataframe,
        "detect_header": _enhanced_detect_header_row,
        "read": _enhanced_read_raw_workbook,
        "profile": _enhanced_profile_dataframe,
        "field_intelligence": _field_intelligence_rows,
        "review": _quality_review_register,
        "cross_sheet_map": _cross_sheet_map,
        "build_workbook": build_ultimate_workbook,
        "build_bundle": build_ultimate_bundle,
    }


def _read_raw_sheets(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    if not raw:
        raise ValueError("The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        size_mb = len(raw) / (1024 * 1024)
        raise ValueError(
            f"This upload is {size_mb:,.1f} MB. The interactive import path is "
            f"limited to {MAX_UPLOAD_BYTES / (1024 * 1024):,.0f} MB so the application "
            "stays responsive. Split the workbook into smaller logical workbooks "
            "or save only the required sheets and retry."
        )

    name = str(filename or "upload.xlsx")
    lower = name.lower()
    p = _load_primitives()
    if lower.endswith(".xls"):
        # The main Excel studio parser intentionally targets modern OOXML files.
        # The shared Data Hub advertises .xls, so handle legacy workbooks here
        # explicitly instead of letting an unsupported format crash the app.
        try:
            book = pd.ExcelFile(io.BytesIO(raw), engine="xlrd")
        except ImportError as exc:
            raise ValueError(
                "Legacy .xls support is not installed on this deployment. "
                "Save the workbook as .xlsx and retry."
            ) from exc
        except Exception as exc:
            raise ValueError(f"Legacy .xls workbook could not be opened: {exc}") from exc
        return {
            str(sheet): pd.read_excel(book, sheet_name=sheet, header=None, dtype=object)
            for sheet in book.sheet_names
        }

    if lower.endswith((".xlsx", ".xlsm", ".csv", ".tsv", ".txt")):
        _validate_ooxml_package(raw, name)
        return p["read"](raw, name)

    raise ValueError("Supported imports are .xlsx, .xlsm, .xls, .csv, .tsv and .txt.")


def _extract_tables(raw_sheets: Mapping[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    p = _load_primitives()
    cleaned: dict[str, pd.DataFrame] = {}
    header_rows: dict[str, int] = {}

    for source_name, raw_df in raw_sheets.items():
        if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
            continue

        header_row = int(p["detect_header"](raw_df))
        header_row = max(0, min(header_row, len(raw_df) - 1))
        headers = p["deduplicate_headers"](raw_df.iloc[header_row].tolist())
        table = raw_df.iloc[header_row + 1:].copy()
        table.columns = headers
        table = table.dropna(axis=1, how="all").dropna(axis=0, how="all")
        cleaned_df, _ = p["clean"](table)

        header_rows[str(source_name)] = header_row
        if not cleaned_df.empty:
            cleaned[str(source_name)] = cleaned_df

    if not cleaned:
        raise ValueError("The workbook contained no usable data rows after table detection and cleaning.")

    return cleaned, header_rows


def process_fast(raw: bytes, filename: str) -> dict[str, Any]:
    """Clean/profile the workbook without generating XLSX/ZIP exports."""
    signature = hashlib.sha256(raw).hexdigest()
    raw_sheets = _read_raw_sheets(raw, filename)
    cleaned, header_rows = _extract_tables(raw_sheets)
    p = _load_primitives()

    profiles: dict[str, dict[str, Any]] = {}
    fields: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    audits: dict[str, list[dict[str, str]]] = {}

    for sheet, frame in cleaned.items():
        raw_frame = raw_sheets[sheet]
        audit = [
            {
                "Action": "Detect table header",
                "Details": f"Detected source header row {header_rows.get(sheet, 0) + 1}.",
            },
            {
                "Action": "Fast import mode",
                "Details": "Interactive upload intentionally skipped workbook/ZIP export generation until explicitly requested.",
            },
        ]
        profiles[sheet] = p["profile"](frame)
        fields.extend(p["field_intelligence"](frame, sheet))
        reviews.extend(p["review"](frame, sheet))
        audits[sheet] = audit
        # Keep a reference to source structure without copying it into a second
        # workbook package during import.
        _ = raw_frame

    from shoir_excel_foundation import fast_workbook_fidelity_report

    return {
        "signature": signature,
        "filename": str(filename),
        "fidelity_report": fast_workbook_fidelity_report(raw, filename),
        "formula_inventory": [],
        "formula_counts_by_sheet": {},
        "formula_scan_status": "NOT_SCANNED",
        "raw_sheets": raw_sheets,
        "cleaned_sheets": cleaned,
        "profiles": profiles,
        "field_intelligence": fields,
        "review_register": reviews,
        "audits": audits,
        "header_rows": header_rows,
        "before_after": [
            {
                "Sheet": sheet,
                "Source rows": max(0, len(raw_sheets[sheet]) - header_rows.get(sheet, 0) - 1),
                "Clean rows": len(frame),
                "Rows removed": max(
                    0,
                    len(raw_sheets[sheet]) - header_rows.get(sheet, 0) - 1 - len(frame),
                ),
                "Source columns": len(raw_sheets[sheet].columns),
                "Clean columns": len(frame.columns),
                "Columns removed": max(0, len(raw_sheets[sheet].columns) - len(frame.columns)),
            }
            for sheet, frame in cleaned.items()
        ],
        "cross_sheet_map": p["cross_sheet_map"](cleaned),
        "module_readiness": [],
        "data_contract": [],
        "relationship_integrity": [],
        "duplicate_candidates": [],
        "privacy_scan": [],
        "formula_quality": [],
        # These are deliberately lazy. The legacy/default public API still
        # returns bytes; only this interactive path postpones the expensive work.
        "xlsx": None,
        "bundle": None,
    }


def scan_source_formulas(result: dict[str, Any], raw_bytes: bytes | bytearray) -> dict[str, Any]:
    """Collect bounded source formulas as inert evidence; never execute them."""
    if not isinstance(result, dict) or not isinstance(raw_bytes, (bytes, bytearray)):
        raise ValueError("A processed workbook and its current uploaded bytes are required.")
    filename = str(result.get("filename") or "")
    if not filename.casefold().endswith((".xlsx", ".xlsm")):
        raise ValueError("Source formula inspection is available for XLSX and XLSM workbooks.")

    raw = bytes(raw_bytes)
    expected_signature = str(result.get("signature") or "")
    if not expected_signature or hashlib.sha256(raw).hexdigest() != expected_signature:
        raise ValueError("The uploaded workbook changed. Re-import it before scanning source formulas.")
    _validate_ooxml_package(raw, filename)

    try:
        import openpyxl

        book = openpyxl.load_workbook(
            io.BytesIO(raw),
            read_only=True,
            data_only=False,
            keep_vba=False,
        )
    except Exception as exc:
        raise ValueError(
            f"Source formulas could not be inspected safely: {type(exc).__name__}."
        ) from exc

    inventory: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    scanned_cells = 0
    try:
        for worksheet in book.worksheets:
            rows = int(getattr(worksheet, "max_row", 0) or 0)
            columns = int(getattr(worksheet, "max_column", 0) or 0)
            declared_cells = rows * columns
            if scanned_cells + declared_cells > MAX_FORMULA_SCAN_CELLS:
                raise ValueError(
                    "The workbook's used ranges exceed the formula-inspection limit of "
                    f"{MAX_FORMULA_SCAN_CELLS:,} cells. The workbook remains available for "
                    "cleaning and analysis; only formula-text inspection was skipped."
                )
            actual_worksheet_cells = 0
            formula_count = 0
            for row in worksheet.iter_rows():
                actual_worksheet_cells += len(row)
                if scanned_cells + actual_worksheet_cells > MAX_FORMULA_SCAN_CELLS:
                    raise ValueError(
                        "The workbook exceeded the formula-inspection cell limit while reading. "
                        "The workbook remains available for cleaning and analysis; only formula-text "
                        "inspection was skipped."
                    )
                for cell in row:
                    value = cell.value
                    if isinstance(value, str) and value.startswith("="):
                        formula_count += 1
                        if len(inventory) < MAX_FORMULA_INVENTORY_ROWS:
                            inventory.append(
                                {
                                    "Sheet": str(worksheet.title),
                                    "Cell": str(cell.coordinate),
                                    "Formula": value,
                                    "Type": "Original source formula",
                                    "Note": (
                                        "Archived as inert text for traceability. "
                                        "It is not executed or copied into the CLEAN data sheet."
                                    ),
                                }
                            )
            scanned_cells += max(declared_cells, actual_worksheet_cells)
            counts[str(worksheet.title)] = formula_count
    finally:
        try:
            book.close()
        except Exception:
            pass

    total_formulas = sum(counts.values())
    result["formula_inventory"] = inventory
    result["formula_counts_by_sheet"] = counts
    result["formula_count"] = total_formulas
    result["formula_scan_status"] = (
        "SAMPLED" if total_formulas > MAX_FORMULA_INVENTORY_ROWS else "COMPLETE"
    )
    result["formula_scan_cells"] = scanned_cells
    result["source_metadata"] = _source_metadata(result)
    return {
        "status": result["formula_scan_status"],
        "formula_count": total_formulas,
        "inventory_rows": len(inventory),
        "scanned_cells": scanned_cells,
        "counts_by_sheet": dict(counts),
    }


def _source_metadata(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    signature = str(result.get("signature") or "")
    rows = []
    headers = result.get("header_rows") or {}
    raw_sheets = result.get("raw_sheets") or {}
    for sheet, frame in raw_sheets.items():
        rows.append(
            {
                "File": str(result.get("filename") or ""),
                "SHA256": signature,
                "Imported": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "Source type": "Excel / delimited text",
                "Source sheet": str(sheet),
                "Source rows": int(len(frame)),
                "Source columns": int(len(frame.columns)),
                "Detected header row": int(headers.get(sheet, 0)) + 1,
                "Detected table blocks": 1,
                "Merged ranges": 0,
                "Source formulas": (result.get("formula_counts_by_sheet") or {}).get(str(sheet), "Not scanned"),
            }
        )
    return rows


def _clear_previous_upload(session_state: Any) -> None:
    """Clear any previous workbook before attempting to load a different upload."""
    session_state["excel_studio_safe_result"] = None
    session_state.pop("excel_studio_safe_signature", None)
    session_state.pop("excel_studio_safe_error_signature", None)
    session_state.pop("excel_studio_safe_error", None)


def _record_upload_failure(session_state: Any, signature: str, error: Exception) -> str:
    """Hide stale exports and cache a clear error for the currently selected file."""
    session_state["excel_studio_safe_result"] = None
    session_state.pop("excel_studio_safe_signature", None)
    reference = _log_excel_error("workbook upload and inspection", error)
    message = f"Workbook validation failed. No source data was changed. Reference: EXCEL-{reference}."
    session_state["excel_studio_safe_error_signature"] = str(signature)
    session_state["excel_studio_safe_error"] = message
    return message


def prepare_exports(
    result: dict[str, Any],
    acknowledged_fidelity_risk: bool = False,
) -> None:
    if not isinstance(result, dict) or not result.get("cleaned_sheets"):
        raise ValueError("There is no processed workbook available to export.")

    fidelity = result.get("fidelity_report") or {}
    if fidelity.get("Requires acknowledgement") is True and acknowledged_fidelity_risk is not True:
        raise PermissionError(
            "Review the source workbook fidelity warnings and explicitly acknowledge them before export. "
            "The original upload remains unchanged."
        )

    p = _load_primitives()
    cleaned = result["cleaned_sheets"]
    raw_sheets = result.get("raw_sheets") or {}
    audits = result.get("audits") or {}
    profiles = result.get("profiles") or {}
    field_intelligence = result.get("field_intelligence") or []
    review_register = result.get("review_register") or []
    before_after = result.get("before_after") or []
    cross_sheet_map = result.get("cross_sheet_map") or []
    source_metadata = result.get("source_metadata") or _source_metadata(result)
    formula_inventory = list(result.get("formula_inventory") or [])

    title = f"Shoir-IE — {result.get('filename', 'Industrial Workbook')}"
    result["xlsx"] = p["build_workbook"](
        title,
        cleaned,
        raw_sheets,
        audits,
        profiles,
        source_metadata=source_metadata,
        field_intelligence=field_intelligence,
        review_register=review_register,
        before_after=before_after,
        formula_inventory=formula_inventory,
        cross_sheet_map=cross_sheet_map,
    )
    result["bundle"] = p["build_bundle"](
        title,
        result["xlsx"],
        audits,
        profiles,
        cleaned_sheets=cleaned,
        raw_sheets=raw_sheets,
        field_intelligence=field_intelligence,
        review_register=review_register,
        source_metadata=source_metadata,
    )


def _activate_shared_dataset(df: pd.DataFrame, filename: str, sheet: str, signature: str) -> None:
    """Publish the selected clean table to the existing shared workspace state."""
    active = df.copy(deep=True)
    st.session_state["universal_active_dataset"] = active
    st.session_state["excel_studio_visual_df"] = active
    st.session_state["data_platform_latest_df"] = active
    st.session_state["unified_data"] = active
    st.session_state["industrial_workbook_current_df"] = active
    st.session_state["shoir_data_status"] = "IMPORTED"
    st.session_state["shoir_data_source_key"] = "upload"
    st.session_state["shoir_data_source"] = f"{filename} · {sheet}"
    st.session_state["shoir_data_version"] = str(signature)[:12]
    st.session_state["shoir_data_hash"] = signature
    st.session_state["shoir_active_workbook_sheet"] = str(sheet)


def excel_intelligence_request_fingerprint(prompt: str, sheet_name: str, df: pd.DataFrame) -> str:
    """Bind a proposed Copilot plan to the exact prompt, sheet and selected data."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Excel Intelligence requires a pandas DataFrame.")
    payload = {
        "prompt": str(prompt or "").strip(),
        "sheet": str(sheet_name or ""),
        "data": df.to_json(orient="split", date_format="iso", default_handler=str),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def excel_intelligence_plan_fingerprint(plan: Mapping[str, Any]) -> str:
    """Hash the exact deterministic plan displayed for human approval."""
    encoded = json.dumps(
        dict(plan),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_excel_intelligence_plan(
    prompt: str,
    sheet_name: str,
    df: pd.DataFrame,
    username: str | None = None,
) -> dict[str, Any]:
    """Build a review-first plan bound to the signed-in actor and workspace."""
    instruction = str(prompt or "").strip()
    if not instruction:
        raise ValueError("Enter an instruction before building a Copilot plan.")
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError("Select a non-empty cleaned worksheet before planning an analysis.")

    owner = str(username or st.session_state.get("current_user") or "").strip()
    session_actor = str(st.session_state.get("current_user") or "").strip()
    if (
        st.session_state.get("authenticated") is not True
        or owner.casefold() in {"", "guest", "guest visitor", "anonymous"}
        or session_actor.casefold() != owner.casefold()
    ):
        raise PermissionError("An active authenticated Shoir-IE session is required to create a Copilot plan.")

    workspace = str(st.session_state.get("workspace_id") or "default")
    from shoir_copilot_orchestrator import build_workflow_plan

    plan = build_workflow_plan(instruction, "Excel Intelligence", df.copy(deep=True))
    return {
        # A fresh identifier binds a single explicit human approval to one
        # planned execution. Rebuilding even an identical request creates a
        # new plan and therefore requires a new approval.
        "plan_id": uuid.uuid4().hex,
        "owner_username": owner.casefold(),
        "workspace_id": workspace,
        "request_fingerprint": excel_intelligence_request_fingerprint(instruction, sheet_name, df),
        "plan_fingerprint": excel_intelligence_plan_fingerprint(plan),
        "prompt": instruction,
        "sheet_name": str(sheet_name),
        "plan": plan,
        "planner": "Shoir-IE deterministic Copilot orchestrator",
        "external_model_used": False,
    }


def _require_live_excel_entitlement(actor: str, tier: str) -> dict[str, Any]:
    """Revalidate the caller's current account and subscription on the server."""
    from durable_account_store import edge_backend_configured, edge_session_entitlement
    from shoir_tier_capabilities import normalize_tier
    from shoir_excel_entitlements import excel_intelligence_allowed

    try:
        backend_ready = edge_backend_configured()
    except Exception as exc:
        raise PermissionError("Live account verification is unavailable. Excel Intelligence is disabled.") from exc
    if not backend_ready:
        raise PermissionError("Live account verification is unavailable. Excel Intelligence is disabled.")
    session_token = str(st.session_state.get("remote_session_token") or "").strip()
    if not session_token:
        raise PermissionError("The authenticated workspace session could not be verified. Sign in again.")

    try:
        live_account = edge_session_entitlement(actor, session_token)
    except Exception as exc:
        raise PermissionError("The authenticated workspace session could not be revalidated. Sign in again.") from exc

    if not isinstance(live_account, dict) or live_account.get("error") == "SUBSCRIPTION_EXPIRED":
        raise PermissionError("The subscription has expired or could not be verified. Sign in again.")
    live_username = str(live_account.get("username") or "").strip()
    live_tier = str(live_account.get("tier") or "").strip()
    if live_account.get("ok") is not True or live_account.get("active") is not True:
        raise PermissionError("The authenticated account is inactive or its current access could not be verified.")
    if live_username.casefold() != str(actor or "").strip().casefold():
        raise PermissionError("The live account session does not match the signed-in user.")
    if not live_tier:
        raise PermissionError("The current subscription tier could not be verified. Sign in again.")
    session_tier = str(st.session_state.get("user_tier") or "").strip()
    if (
        not session_tier
        or normalize_tier(session_tier) != normalize_tier(live_tier)
        or normalize_tier(str(tier or "")) != normalize_tier(live_tier)
    ):
        raise PermissionError("The subscription changed during this session. Sign in again to refresh your access.")

    expiry_value = live_account.get("expires_at")
    if not expiry_value:
        raise PermissionError("The live subscription expiry could not be verified. Excel Intelligence is disabled.")
    expiry_text = expiry_value.isoformat() if hasattr(expiry_value, "isoformat") else str(expiry_value)
    try:
        expiry = datetime.fromisoformat(expiry_text.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PermissionError("The live subscription expiry is invalid. Excel Intelligence is disabled.") from exc
    if expiry <= datetime.now(timezone.utc):
        raise PermissionError("The subscription has expired. Sign in again to access renewal options.")
    if not excel_intelligence_allowed(live_tier):
        raise PermissionError("The current subscription does not include Excel Intelligence.")

    return {
        "username": live_username,
        "tier": live_tier,
        "active": True,
        "expires_at": expiry.isoformat(),
    }


def execute_excel_intelligence_plan(
    prompt: str,
    sheet_name: str,
    df: pd.DataFrame,
    plan_envelope: Mapping[str, Any],
    username: str,
    tier: str,
    approved: bool,
) -> dict[str, Any]:
    """Execute only a current, approved Copilot plan against a copy of the data."""
    if approved is not True:
        raise PermissionError("Explicit approval is required before Copilot execution.")

    actor = str(username or "").strip()
    session_actor = str(st.session_state.get("current_user") or "").strip()
    if (
        st.session_state.get("authenticated") is not True
        or actor.casefold() in {"", "guest", "guest visitor", "anonymous"}
        or session_actor.casefold() != actor.casefold()
    ):
        raise PermissionError("An active authenticated Shoir-IE session is required.")

    # Reject cross-user/workspace plan replay before making a live entitlement
    # request for the caller. A plan can never be used to probe another account.
    workspace = str(st.session_state.get("workspace_id") or "default")
    plan_owner = str(plan_envelope.get("owner_username") or "").strip()
    plan_workspace = str(plan_envelope.get("workspace_id") or "")
    if plan_owner.casefold() != actor.casefold() or plan_workspace != workspace:
        raise PermissionError("This Copilot plan belongs to another user or workspace.")

    expected = excel_intelligence_request_fingerprint(prompt, sheet_name, df)
    supplied = str(plan_envelope.get("request_fingerprint") or "")
    if not supplied or supplied != expected:
        raise ValueError("The plan is stale. Rebuild it after changing the instruction, worksheet or data.")

    live_account = _require_live_excel_entitlement(actor, tier)
    live_tier = str(live_account["tier"])

    plan = plan_envelope.get("plan")
    if not isinstance(plan, Mapping) or plan.get("requires_approval") is not True:
        raise ValueError("A valid approval-required Copilot plan is required.")

    # Verify that the exact plan reviewed in the UI is still the plan being run.
    # Rebuild it server-side from the current request/data rather than trusting
    # plan fields supplied by mutable client/session state.
    from shoir_copilot_orchestrator import build_workflow_plan
    canonical_plan = build_workflow_plan(prompt, "Excel Intelligence", df.copy(deep=True))
    canonical_plan_fingerprint = excel_intelligence_plan_fingerprint(canonical_plan)
    supplied_plan_fingerprint = str(plan_envelope.get("plan_fingerprint") or "")
    if (
        supplied_plan_fingerprint != canonical_plan_fingerprint
        or excel_intelligence_plan_fingerprint(plan) != canonical_plan_fingerprint
    ):
        raise ValueError("The approved plan changed or is stale. Rebuild and review the current plan before execution.")

    plan_id = str(plan_envelope.get("plan_id") or "").strip()
    if not re.fullmatch(r"[a-f0-9]{32}", plan_id):
        raise ValueError("This plan has no valid one-use identifier. Build and review a new plan.")

    registry_key = "excel_intelligence_copilot_execution_registry"
    registry = st.session_state.get(registry_key)
    if not isinstance(registry, dict):
        registry = {"in_progress": [], "completed": []}
    in_progress = [str(value) for value in registry.get("in_progress", [])]
    completed = [str(value) for value in registry.get("completed", [])]
    if plan_id in in_progress or plan_id in completed:
        raise PermissionError(
            "This approved plan has already run or is currently running. "
            "Build a new plan and review it before another execution."
        )

    # Claim the one-use plan before invoking the analysis engine. This blocks
    # double-clicks and reruns in the same authenticated Streamlit session.
    registry["in_progress"] = [*in_progress, plan_id]
    registry["completed"] = completed[-500:]
    st.session_state[registry_key] = registry

    try:
        # The orchestrator receives an isolated copy. The source/cleaned worksheet
        # is never modified by this analysis route.
        source_snapshot = df.copy(deep=True)
        from shoir_copilot_orchestrator import run_orchestration

        run = run_orchestration(
            str(prompt).strip(),
            "Excel Intelligence",
            df.copy(deep=True),
            context={"actor": actor, "username": actor, "workspace": workspace},
        )
        if not df.equals(source_snapshot):
            raise RuntimeError("Copilot unexpectedly modified the source dataframe; execution was stopped.")
        if not isinstance(run, dict) or not isinstance(run.get("export"), (bytes, bytearray)):
            raise RuntimeError("Copilot did not produce a valid evidence export; no success state was recorded.")

        approved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        approval_evidence = {
            "schema_version": "1.0",
            "plan_id": plan_id,
            "actor": actor,
            "workspace": workspace,
            "approved": True,
            "approved_at_utc": approved_at,
            "source_worksheet": str(sheet_name),
            "source_data_fingerprint": expected,
            "request_fingerprint": supplied,
            "plan_fingerprint": canonical_plan_fingerprint,
            "planner": "Shoir-IE deterministic Copilot orchestrator",
            "external_model_used": False,
            "source_data_preserved": True,
            "execution_status": "COMPLETED",
        }

        evidence_manifest = run.get("evidence_manifest")
        if not isinstance(evidence_manifest, dict):
            evidence_manifest = {}
            run["evidence_manifest"] = evidence_manifest
        evidence_manifest["approval"] = approval_evidence

        # Include the approval record in the downloadable evidence archive as
        # well as the UI manifest. Rebuild the ZIP rather than mutating or
        # replacing the analysis workbook.
        evidence_buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(bytes(run["export"])), "r") as source_archive:
            with zipfile.ZipFile(evidence_buffer, "w", compression=zipfile.ZIP_DEFLATED) as target_archive:
                for item in source_archive.infolist():
                    if item.filename == "copilot_approval.json":
                        continue
                    target_archive.writestr(item, source_archive.read(item.filename))
                target_archive.writestr(
                    "copilot_approval.json",
                    json.dumps(approval_evidence, ensure_ascii=False, indent=2).encode("utf-8"),
                )

        run["export"] = evidence_buffer.getvalue()
        run["approval_record"] = approval_evidence
        run["plan_id"] = plan_id
        run["source_sheet"] = str(sheet_name)
        run["source_data_fingerprint"] = expected
        run["planner"] = "Shoir-IE deterministic Copilot orchestrator"
        run["external_model_used"] = False

        registry = st.session_state.get(registry_key)
        if not isinstance(registry, dict):
            registry = {"in_progress": [], "completed": []}
        registry["completed"] = [*[
            str(value) for value in registry.get("completed", []) if str(value) != plan_id
        ], plan_id][-500:]
        st.session_state[registry_key] = registry
        return run
    finally:
        registry = st.session_state.get(registry_key)
        if isinstance(registry, dict):
            registry["in_progress"] = [
                str(value) for value in registry.get("in_progress", []) if str(value) != plan_id
            ]
            st.session_state[registry_key] = registry


def render_excel_intelligence_safe(tier: str, username: str, enable_copilot: bool = False) -> None:
    if enable_copilot:
        # The premium route is independently protected here as well as in the
        # platform dispatcher. Never rely on hiding a Workbench menu item.
        from shoir_excel_entitlements import (
            excel_intelligence_allowed,
            excel_intelligence_entitlement_config,
            excel_intelligence_minimum_tier,
        )

        actor = str(username or "").strip()
        session_actor = str(st.session_state.get("current_user") or "").strip()
        if (
            st.session_state.get("authenticated") is not True
            or actor.casefold() in {"", "guest", "guest visitor", "anonymous"}
            or session_actor.casefold() != actor.casefold()
        ):
            st.warning("Sign in with an active Shoir-IE account before using Excel Intelligence.")
            return
        entitlement = excel_intelligence_entitlement_config()
        try:
            live_entitlement = _require_live_excel_entitlement(actor, tier)
        except PermissionError:
            st.warning(
                "Your current Shoir-IE session and subscription could not be verified. "
                "Sign in again before using Excel Intelligence."
            )
            return
        tier = str(live_entitlement["tier"])
        if not excel_intelligence_allowed(tier):
            st.warning(
                f"Excel Intelligence requires {excel_intelligence_minimum_tier()}. "
                f"Your current tier is {tier}."
            )
            if not entitlement["valid"]:
                _LOGGER.warning(
                    "Excel Intelligence entitlement configuration is invalid; fail-closed tier applied: %s",
                    entitlement.get("warning"),
                )
                st.error(
                    "Excel Intelligence access is restricted by server configuration. "
                    "Please contact your Shoir-IE administrator."
                )
            return
    else:
        # Preserve the separate Starter Excel Data Cleaning & Import module.
        from shoir_tier_capabilities import tier_allows

        if not tier_allows(tier, "Starter"):
            st.warning("This workspace is not included in your current package.")
            return

    st.markdown("## 📊 Excel Intelligence & Data Cleaning Studio")
    st.caption(
        "Safe import mode: upload → clean → inspect → activate. "
        "Large workbook exports are generated only when you explicitly prepare a download."
    )

    upload = st.file_uploader(
        "Upload raw Excel / CSV / TSV / TXT",
        type=["xlsx", "xlsm", "xls", "csv", "tsv", "txt"],
        key="excel_studio_safe_upload",
        help=(
            "Modern .xlsx/.xlsm plus legacy .xls and common delimited text exports are supported. "
            f"Interactive imports are limited to {MAX_UPLOAD_BYTES / (1024 * 1024):.0f} MB."
        ),
    )

    if upload is not None:
        raw = upload.getvalue()
        signature = hashlib.sha256(raw).hexdigest()
        current_signature = st.session_state.get("excel_studio_safe_signature")
        cached_error_signature = st.session_state.get("excel_studio_safe_error_signature")

        if current_signature != signature and cached_error_signature != signature:
            # The newly selected file supersedes any previous workbook. Never
            # leave an old workbook/export visible if this replacement fails.
            _clear_previous_upload(st.session_state)
            try:
                with st.spinner("Inspecting and cleaning your workbook…"):
                    result = process_fast(raw, upload.name)
                st.session_state["excel_studio_safe_signature"] = signature
                st.session_state["excel_studio_safe_result"] = result
                st.session_state.pop("excel_studio_safe_error_signature", None)
                st.session_state.pop("excel_studio_safe_error", None)
                # Immediately make the first clean table available to downstream
                # engineering tools without creating an export package.
                first_sheet = next(iter(result["cleaned_sheets"]))
                _activate_shared_dataset(
                    result["cleaned_sheets"][first_sheet],
                    result["filename"],
                    first_sheet,
                    result["signature"],
                )
                st.success(
                    f"✅ Loaded {len(result['cleaned_sheets']):,} cleaned sheet(s) "
                    f"from **{result['filename']}** without blocking the application on export generation."
                )
            except Exception as exc:
                message = _record_upload_failure(st.session_state, signature, exc)
                st.error(f"Excel upload could not be loaded safely: {message}")
        elif cached_error_signature == signature and current_signature != signature:
            st.error(
                "This upload previously failed validation. No source data was changed. "
                "Select a different file or try again."
            )

    result = st.session_state.get("excel_studio_safe_result")
    if not isinstance(result, dict):
        st.info("Upload a valid workbook to activate the safe Excel Intelligence workflow.")
        return
    if upload is not None and str(result.get("signature") or "") != signature:
        # Defence in depth: never expose downloads/results from any other upload.
        st.info("The selected upload has not been processed successfully. Previous workbook results are hidden.")
        return

    cleaned = result.get("cleaned_sheets") or {}
    profiles = result.get("profiles") or {}
    if not cleaned:
        st.warning("No usable tables are currently active.")
        return

    sheet_names = list(cleaned)
    selected = st.session_state.get("excel_studio_safe_sheet") or sheet_names[0]
    if selected not in cleaned:
        selected = sheet_names[0]
    st.session_state["excel_studio_visual_df"] = cleaned[selected].copy(deep=True)
    _activate_shared_dataset(cleaned[selected], result["filename"], selected, result["signature"])

    scores = [float(v.get("Quality score", 0.0)) for v in profiles.values()]
    high_reviews = sum(1 for x in result.get("review_register", []) if x.get("Severity") == "High")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Sheets", len(cleaned))
    m2.metric("Clean rows", f"{sum(len(v) for v in cleaned.values()):,}")
    m3.metric("Avg quality", f"{float(np.mean(scores)):.1f}%" if scores else "—")
    m4.metric("Review items", f"{len(result.get('review_register', [])):,}")
    m5.metric("High priority", high_reviews)

    tab_names = ["Overview", "Clean Data", "Quality Center", "Field Intelligence"]
    if enable_copilot:
        tab_names.append("Copilot")
    tab_names.append("Export")
    tabs = st.tabs(tab_names)

    with tabs[0]:
        st.markdown("### Workbook loaded")
        _render_excel_dataframe(
            pd.DataFrame(
                [
                    {
                        "Sheet": name,
                        "Rows": len(frame),
                        "Columns": len(frame.columns),
                        "Quality": f"{profiles.get(name, {}).get('Quality score', 0):.1f}%",
                        "Readiness": profiles.get(name, {}).get("Readiness", "—"),
                    }
                    for name, frame in cleaned.items()
                ]
            ),
            "Workbook overview",
        )
        st.markdown("### Before vs after")
        _render_excel_dataframe(pd.DataFrame(result.get("before_after", [])), "Before and after")
        st.markdown("### Source provenance")
        _render_excel_dataframe(pd.DataFrame(_source_metadata(result)), "Source provenance")
        st.info(
            "The upload path is intentionally lazy: the application becomes usable as soon as the data is cleaned. "
            "Workbook packaging is separate so a large export cannot prevent the core workspace from loading."
        )
        fidelity = result.get("fidelity_report") or {}
        st.markdown("### Workbook feature preservation")
        if fidelity.get("Requires acknowledgement") is True:
            st.warning(str(fidelity.get("Fidelity warning") or "The source has features that may not survive a data-focused export."))
            st.caption(
                "Features requiring review: "
                + "; ".join(str(x) for x in fidelity.get("Unsupported features", []))
            )
        else:
            st.success(str(fidelity.get("Fidelity warning") or "No unsupported workbook features were detected."))
        st.caption(
            "The uploaded source remains unchanged. The generated Industrial Excel Intelligence workbook is a separate, "
            "data-focused output and does not replace the original file."
        )
        if enable_copilot:
            st.markdown("### Source formula inspection")
            formula_status = str(result.get("formula_scan_status") or "NOT_SCANNED")
            extension = str(result.get("filename") or "").casefold()
            if extension.endswith((".xlsx", ".xlsm")) and formula_status in {"NOT_SCANNED", "BLOCKED"}:
                if formula_status == "NOT_SCANNED":
                    st.caption(
                        f"Workbook package inspection detected {int(fidelity.get('Formula cells', 0) or 0):,} "
                        "formula cell(s). Formula text is not scanned until you request it."
                    )
                else:
                    st.warning(
                        "The previous source formula inspection could not complete. "
                        "No formula results are being shown."
                    )
                if upload is not None and st.button(
                    "Inspect source formulas",
                    width="stretch",
                    key="excel_intelligence_scan_source_formulas",
                ):
                    try:
                        with st.spinner("Scanning source formulas as inert evidence…"):
                            scan_result = scan_source_formulas(result, upload.getvalue())
                        result["formula_scan_error"] = ""
                        st.session_state["excel_studio_safe_result"] = result
                        st.success(
                            f"Scanned {scan_result['scanned_cells']:,} cell(s) and found "
                            f"{scan_result['formula_count']:,} formula(s)."
                        )
                    except Exception as exc:
                        reference = _log_excel_error("source formula inspection", exc)
                        result["formula_scan_status"] = "BLOCKED"
                        result["formula_scan_error"] = (
                            "Source formula inspection failed. No formula results were produced."
                        )
                        st.session_state["excel_studio_safe_result"] = result
                        st.error(
                            "Source formula inspection was not completed. "
                            f"No formula results were produced. Reference: EXCEL-{reference}."
                        )
            elif extension.endswith((".xlsx", ".xlsm")):
                formula_count = int(result.get("formula_count", 0) or 0)
                st.caption(
                    f"Formula inspection status: {formula_status} · "
                    f"{formula_count:,} formula(s) found."
                )
                formulas = result.get("formula_inventory") or []
                if formulas:
                    _render_excel_dataframe(pd.DataFrame(formulas), "Source formula inventory")
                if formula_status == "SAMPLED":
                    st.warning(
                        f"Only the first {MAX_FORMULA_INVENTORY_ROWS:,} source formulas are included "
                        "in the evidence inventory. The total formula count is shown above."
                    )
                st.caption(
                    "Formula strings are stored as inert text in the separate output workbook. "
                    "They are not executed, rewritten or silently restored into cleaned data."
                )
            else:
                st.caption("Source formula inventory is available only for XLSX and XLSM workbooks.")

    with tabs[1]:
        selected = st.selectbox("Clean sheet", sheet_names, index=sheet_names.index(selected), key="excel_studio_safe_sheet")
        df = cleaned[selected]
        _activate_shared_dataset(df, result["filename"], selected, result["signature"])
        st.caption(
            f"{selected} · {len(df):,} rows × {len(df.columns):,} fields · "
            f"{profiles.get(selected, {}).get('Readiness', '—')}"
        )
        _render_excel_dataframe(df, "Clean data")

    with tabs[2]:
        review_items = result.get("review_register") or []
        review_preview_items = (
            review_items[:MAX_RENDER_PREVIEW_ROWS]
            if isinstance(review_items, (list, tuple))
            else []
        )
        review_frame = pd.DataFrame(review_preview_items)
        if not review_items:
            st.success("No automated review exceptions detected.")
        else:
            _render_excel_dataframe(review_frame, "Quality review")
            if len(review_items) > MAX_RENDER_PREVIEW_ROWS:
                st.caption(
                    f"Showing the first {MAX_RENDER_PREVIEW_ROWS:,} of {len(review_items):,} review records."
                )
            severity_counts: dict[str, int] = {}
            if isinstance(review_items, (list, tuple)):
                for item in review_items:
                    if isinstance(item, Mapping):
                        severity = str(item.get("Severity") or "Unspecified")
                        severity_counts[severity] = severity_counts.get(severity, 0) + 1
            if severity_counts:
                counts = pd.DataFrame(
                    [{"Severity": key, "Count": value} for key, value in sorted(severity_counts.items())]
                )
                _render_excel_dataframe(counts, "Review severity counts")
            else:
                st.caption("A severity breakdown is not available for these review records.")
        st.caption("Potential outliers are flags for review; they are never silently deleted by the interactive upload path.")

    with tabs[3]:
        field_frame = pd.DataFrame(result.get("field_intelligence", []))
        _render_excel_dataframe(field_frame, "Field intelligence")

    if enable_copilot:
        with tabs[4]:
            st.markdown("### Excel Copilot")
            st.caption(
                "Describe an analysis in your own words. Shoir-IE inspects the selected cleaned sheet, "
                "proposes a reviewable plan, and runs supported deterministic analysis only after approval."
            )
            st.info(
                "This route uses Shoir-IE's deterministic Copilot orchestrator. It does not call an external "
                "LLM, send workbook contents to an external AI provider, overwrite the source workbook, or "
                "silently execute workbook edits. Unsupported requests are reported as limitations rather "
                "than treated as completed operations."
            )
            copilot_prompt = st.text_area(
                "What would you like Shoir-IE to analyse?",
                key="excel_intelligence_copilot_prompt",
                height=110,
                placeholder="Example: analyse throughput and cost, identify trends, compare scenarios and prepare an evidence workbook.",
            )
            if st.button(
                "Build execution plan",
                type="primary",
                width="stretch",
                key="excel_intelligence_copilot_build_plan",
            ):
                try:
                    envelope = build_excel_intelligence_plan(
                        copilot_prompt, selected, cleaned[selected], username=username
                    )
                    approval_key = "excel_intelligence_copilot_approved_" + str(envelope["plan_id"])[:12]
                    # A rebuilt plan always needs a new, explicit approval even
                    # when the instruction and workbook contents are identical.
                    st.session_state[approval_key] = False
                    st.session_state["excel_intelligence_copilot_plan"] = envelope
                    st.session_state.pop("excel_intelligence_copilot_run", None)
                    st.session_state.pop("excel_intelligence_copilot_run_fingerprint", None)
                    st.success("A reviewable plan has been prepared. No analysis has run yet.")
                except Exception as exc:
                    reference = _log_excel_error("Copilot plan preparation", exc)
                    st.error(
                        "Shoir-IE could not prepare this analysis plan. "
                        f"No analysis was executed. Reference: EXCEL-{reference}."
                    )

            envelope = st.session_state.get("excel_intelligence_copilot_plan")
            current_fingerprint = (
                excel_intelligence_request_fingerprint(copilot_prompt, selected, cleaned[selected])
                if str(copilot_prompt or "").strip()
                else ""
            )
            if isinstance(envelope, dict):
                if current_fingerprint != str(envelope.get("request_fingerprint") or ""):
                    st.warning("This plan is stale because the instruction, worksheet or data changed. Build a new plan before execution.")
                else:
                    plan = envelope.get("plan") or {}
                    st.markdown("#### Proposed plan")
                    st.caption(
                        f"Planner: {envelope.get('planner')} · Sheet: {envelope.get('sheet_name')} · "
                        f"Approval required: {'Yes' if plan.get('requires_approval') else 'No'}"
                    )
                    if plan.get("intent"):
                        st.write(f"**Detected intent:** {plan['intent'].get('label', 'Engineering analysis')}")
                        st.caption(str(plan["intent"].get("reason") or ""))
                    if plan.get("method"):
                        st.write(f"**Selected method:** {plan['method'].get('method', 'Not specified')}")
                    _render_excel_dataframe(pd.DataFrame(plan.get("steps") or []), "Copilot proposed steps")
                    st.caption("Execution is read-only against a copy of the selected cleaned sheet. The source workbook remains unchanged.")
                    plan_id = str(envelope.get("plan_id") or "")
                    approval_key = "excel_intelligence_copilot_approved_" + plan_id[:12]
                    registry = st.session_state.get("excel_intelligence_copilot_execution_registry") or {}
                    already_executed = plan_id in [str(value) for value in registry.get("completed", [])]
                    if already_executed:
                        st.success("This approved plan has already completed. Build a new plan to run another analysis.")
                    approved = st.checkbox(
                        "I have reviewed this plan and approve running the analysis.",
                        key=approval_key,
                        disabled=already_executed,
                    )
                    if st.button(
                        "Approve and run analysis",
                        type="primary",
                        disabled=(not approved or already_executed),
                        width="stretch",
                        key="excel_intelligence_copilot_execute",
                    ):
                        try:
                            run = execute_excel_intelligence_plan(
                                copilot_prompt,
                                selected,
                                cleaned[selected],
                                envelope,
                                username,
                                tier,
                                approved=approved,
                            )
                            st.session_state["excel_intelligence_copilot_run"] = run
                            st.session_state["excel_intelligence_copilot_run_fingerprint"] = current_fingerprint
                            st.success("The approved analysis completed and an evidence bundle was generated.")
                        except Exception as exc:
                            reference = _log_excel_error("Copilot execution", exc)
                            st.error(
                                "The approved analysis could not be completed. "
                                "No success was recorded. Reference: "
                                f"EXCEL-{reference}."
                            )

            run = st.session_state.get("excel_intelligence_copilot_run")
            run_fingerprint = st.session_state.get("excel_intelligence_copilot_run_fingerprint")
            if isinstance(run, dict) and run_fingerprint == current_fingerprint and current_fingerprint:
                st.markdown("#### Analysis result")
                inspection = run.get("inspection") or {}
                metrics = run.get("analysis_meta") or {}
                m1, m2, m3 = st.columns(3)
                m1.metric("Rows inspected", f"{int(inspection.get('rows', 0)):,}")
                m2.metric("Missing cells", f"{int(inspection.get('missing_cells', 0)):,}")
                m3.metric("Analysis type", str(metrics.get("type") or "—").replace("_", " ").title())
                result_df = run.get("result")
                if isinstance(result_df, pd.DataFrame):
                    _render_excel_dataframe(result_df, "Copilot analysis results")
                figure = run.get("figure")
                if figure is not None:
                    _render_excel_plotly_figure(figure, "Copilot analysis chart")
                st.markdown("**Explanation**")
                st.write(str(run.get("explanation") or "No explanation was generated."))
                with st.expander("Evidence manifest and analysis assumptions"):
                    _render_excel_json(
                        run.get("evidence_manifest") or {},
                        "Evidence manifest",
                    )
                    _render_excel_json(metrics, "Analysis assumptions")
                try:
                    with zipfile.ZipFile(io.BytesIO(bytes(run["export"])), "r") as archive:
                        workbook_bytes = archive.read("copilot_analysis.xlsx")
                    st.download_button(
                        "Download Copilot analysis workbook",
                        workbook_bytes,
                        file_name=f"shoir_ie_excel_copilot_{str(run.get('run_id') or 'run').lower()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="excel_intelligence_copilot_download_xlsx",
                    )
                    st.download_button(
                        "Download complete Copilot evidence package",
                        bytes(run["export"]),
                        file_name=f"shoir_ie_excel_copilot_{str(run.get('run_id') or 'run').lower()}.zip",
                        mime="application/zip",
                        key="excel_intelligence_copilot_download_bundle",
                    )
                except Exception as exc:
                    reference = _log_excel_error("Copilot evidence verification", exc)
                    st.error(
                        "The Copilot evidence package could not be reopened safely. "
                        f"Reference: EXCEL-{reference}."
                    )

    export_tab_index = 5 if enable_copilot else 4
    with tabs[export_tab_index]:
        st.markdown("### Download center")
        fidelity = result.get("fidelity_report") or {}
        requires_fidelity_ack = fidelity.get("Requires acknowledgement") is True
        fidelity_acknowledged = False
        if requires_fidelity_ack:
            st.warning(
                "Review the unsupported source features below before preparing the data-focused output. "
                "The original upload will remain unchanged."
            )
            st.caption("; ".join(str(x) for x in fidelity.get("Unsupported features", [])))
            fidelity_acknowledged = st.checkbox(
                "I reviewed the source workbook fidelity warnings and understand the generated copy may not preserve those features.",
                key="excel_fidelity_ack_" + str(result.get("signature") or "source")[:12],
            )
        if result.get("xlsx") is None:
            st.info(
                "No export has been built yet. This is intentional — building a full multi-sheet workbook can be "
                "expensive for large source files."
            )
            if st.button(
                "⚙️ Prepare Industrial Excel Workbook",
                type="primary",
                disabled=requires_fidelity_ack and not fidelity_acknowledged,
                width="stretch",
                key="excel_studio_safe_prepare_export",
            ):
                try:
                    with st.spinner("Assembling the downloadable workbook…"):
                        prepare_exports(
                            result,
                            acknowledged_fidelity_risk=fidelity_acknowledged,
                        )
                    st.session_state["excel_studio_safe_result"] = result
                    st.success("Download package prepared.")
                except Exception as exc:
                    reference = _log_excel_error("workbook export preparation", exc)
                    st.error(
                        "The source workbook is loaded, but the export package could not be prepared. "
                        f"Reference: EXCEL-{reference}."
                    )
        if result.get("xlsx") is not None:
            safe_name = re.sub(r"[^A-Za-z0-9]+", "_", str(result["filename"])).strip("_").lower()
            st.download_button(
                "📥 Download Industrial Excel Intelligence Workbook",
                result["xlsx"],
                file_name=f"shoir_ie_industrial_{safe_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                width="stretch",
                key="excel_studio_safe_download_xlsx",
            )
            if result.get("bundle") is not None:
                st.download_button(
                    "📦 Download Complete Evidence Package",
                    result["bundle"],
                    file_name=f"shoir_ie_industrial_{safe_name}.zip",
                    mime="application/zip",
                    width="stretch",
                    key="excel_studio_safe_download_bundle",
                )
            st.caption(
                "Fast export preserves the governed CLEAN tables, review register, field intelligence, provenance and RAW archive. "
                "Source formulas are not rescanned during the safe export path."
            )


def process_upload_for_data_hub(raw: bytes, filename: str) -> tuple[dict[str, pd.DataFrame], str]:
    result = process_fast(raw, filename)
    return result["cleaned_sheets"], result["signature"]
