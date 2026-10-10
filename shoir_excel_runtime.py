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
import io
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd
import streamlit as st

MAX_UPLOAD_BYTES = 75 * 1024 * 1024


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

    return {
        "signature": signature,
        "filename": str(filename),
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
                "Source formulas": "Not rescanned in fast export",
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
    message = f"{type(error).__name__}: {error}"
    session_state["excel_studio_safe_error_signature"] = str(signature)
    session_state["excel_studio_safe_error"] = message
    return message


def prepare_exports(result: dict[str, Any]) -> None:
    if not isinstance(result, dict) or not result.get("cleaned_sheets"):
        raise ValueError("There is no processed workbook available to export.")

    p = _load_primitives()
    cleaned = result["cleaned_sheets"]
    raw_sheets = result.get("raw_sheets") or {}
    audits = result.get("audits") or {}
    profiles = result.get("profiles") or {}
    field_intelligence = result.get("field_intelligence") or []
    review_register = result.get("review_register") or []
    before_after = result.get("before_after") or []
    cross_sheet_map = result.get("cross_sheet_map") or []
    source_metadata = _source_metadata(result)

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
        formula_inventory=[],
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


def render_excel_intelligence_safe(tier: str, username: str) -> None:
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
            cached_message = str(st.session_state.get("excel_studio_safe_error") or "This upload previously failed validation.")
            st.error(f"Excel upload could not be loaded safely: {cached_message}")

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

    tabs = st.tabs(["Overview", "Clean Data", "Quality Center", "Field Intelligence", "Export"])

    with tabs[0]:
        st.markdown("### Workbook loaded")
        st.dataframe(
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
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("### Before vs after")
        st.dataframe(pd.DataFrame(result.get("before_after", [])), use_container_width=True, hide_index=True)
        st.markdown("### Source provenance")
        st.dataframe(pd.DataFrame(_source_metadata(result)), use_container_width=True, hide_index=True)
        st.info(
            "The upload path is intentionally lazy: the application becomes usable as soon as the data is cleaned. "
            "Workbook packaging is separate so a large export cannot prevent the core workspace from loading."
        )

    with tabs[1]:
        selected = st.selectbox("Clean sheet", sheet_names, index=sheet_names.index(selected), key="excel_studio_safe_sheet")
        df = cleaned[selected]
        _activate_shared_dataset(df, result["filename"], selected, result["signature"])
        st.caption(
            f"{selected} · {len(df):,} rows × {len(df.columns):,} fields · "
            f"{profiles.get(selected, {}).get('Readiness', '—')}"
        )
        st.dataframe(df.head(2000), use_container_width=True, hide_index=True)

    with tabs[2]:
        review_frame = pd.DataFrame(result.get("review_register", []))
        if review_frame.empty:
            st.success("No automated review exceptions detected.")
        else:
            st.dataframe(review_frame, use_container_width=True, hide_index=True)
            counts = review_frame["Severity"].value_counts().rename_axis("Severity").reset_index(name="Count")
            st.dataframe(counts, use_container_width=True, hide_index=True)
        st.caption("Potential outliers are flags for review; they are never silently deleted by the interactive upload path.")

    with tabs[3]:
        field_frame = pd.DataFrame(result.get("field_intelligence", []))
        st.dataframe(field_frame, use_container_width=True, hide_index=True)

    with tabs[4]:
        st.markdown("### Download center")
        if result.get("xlsx") is None:
            st.info(
                "No export has been built yet. This is intentional — building a full multi-sheet workbook can be "
                "expensive for large source files."
            )
            if st.button(
                "⚙️ Prepare Industrial Excel Workbook",
                type="primary",
                use_container_width=True,
                key="excel_studio_safe_prepare_export",
            ):
                try:
                    with st.spinner("Assembling the downloadable workbook…"):
                        prepare_exports(result)
                    st.session_state["excel_studio_safe_result"] = result
                    st.success("Download package prepared.")
                except Exception as exc:
                    st.error(
                        f"The source workbook is loaded, but export preparation failed safely: "
                        f"{type(exc).__name__}: {exc}"
                    )
        if result.get("xlsx") is not None:
            safe_name = re.sub(r"[^A-Za-z0-9]+", "_", str(result["filename"])).strip("_").lower()
            st.download_button(
                "📥 Download Industrial Excel Intelligence Workbook",
                result["xlsx"],
                file_name=f"shoir_ie_industrial_{safe_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
                key="excel_studio_safe_download_xlsx",
            )
            if result.get("bundle") is not None:
                st.download_button(
                    "📦 Download Complete Evidence Package",
                    result["bundle"],
                    file_name=f"shoir_ie_industrial_{safe_name}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="excel_studio_safe_download_bundle",
                )
            st.caption(
                "Fast export preserves the governed CLEAN tables, review register, field intelligence, provenance and RAW archive. "
                "Source formulas are not rescanned during the safe export path."
            )


def process_upload_for_data_hub(raw: bytes, filename: str) -> tuple[dict[str, pd.DataFrame], str]:
    result = process_fast(raw, filename)
    return result["cleaned_sheets"], result["signature"]
