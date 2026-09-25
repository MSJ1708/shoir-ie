"""Universal module parity layer for Shoir-IE.

Every module receives the same engineering workflow surface:
Import -> Validate -> Results -> Live Graphs -> Export -> Persist.

The layer is deliberately additive. Existing module-specific engines, tables,
calculations and controls remain responsible for their domain behavior; this
module provides a consistent cross-module data/evidence contract around them.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def module_token(module: str) -> str:
    return hashlib.sha1(str(module).encode("utf-8")).hexdigest()[:12]


def parity_keys(module: str) -> dict[str, str]:
    token = module_token(module)
    return {
        "data": f"module_parity_data_{token}",
        "original": f"module_parity_original_{token}",
        "meta": f"module_parity_meta_{token}",
        "validation": f"module_parity_validation_{token}",
        "clean_audit": f"module_parity_clean_audit_{token}",
        "results": f"module_parity_results_{token}",
        "signature": f"module_parity_signature_{token}",
        "workbook": f"module_parity_workbook_{token}",
    }


def _slug(module: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(module)).strip("_").lower()


def _as_frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    if isinstance(value, list):
        if not value:
            return pd.DataFrame()
        if all(isinstance(item, dict) for item in value):
            return pd.DataFrame(value)
        return pd.DataFrame({"Value": value})
    if isinstance(value, dict):
        scalar = {
            str(k): v
            for k, v in value.items()
            if isinstance(v, (str, int, float, bool, np.integer, np.floating))
            and not isinstance(v, bool)
        }
        return pd.DataFrame([scalar]) if scalar else pd.DataFrame()
    return pd.DataFrame()


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return str(value)


def validate_module_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Return deterministic, non-destructive data-quality diagnostics."""
    if not isinstance(df, pd.DataFrame):
        df = _as_frame(df)

    rows, cols = df.shape
    duplicate_columns = int(len(df.columns) - len(set(map(str, df.columns))))
    duplicate_rows = int(df.duplicated().sum()) if not df.empty else 0
    missing_cells = int(df.isna().sum().sum()) if not df.empty else 0
    empty_strings = 0
    if not df.empty:
        for col in df.columns:
            try:
                empty_strings += int(df[col].astype("string").str.strip().eq("").sum())
            except Exception:
                continue

    numeric_columns = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    date_like_columns: list[str] = []
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            date_like_columns.append(str(col))
            continue
        if series.dtype == object:
            sample = series.dropna().astype(str).head(40)
            if len(sample) >= 5:
                parsed = pd.to_datetime(sample, errors="coerce")
                if float(parsed.notna().mean()) >= 0.8:
                    date_like_columns.append(str(col))

    constant_columns = [
        str(c) for c in df.columns
        if len(df) > 1 and df[c].nunique(dropna=False) <= 1
    ]

    negative_numeric_cells = 0
    for col in numeric_columns:
        try:
            negative_numeric_cells += int(pd.to_numeric(df[col], errors="coerce").lt(0).sum())
        except Exception:
            continue

    checks = [
        {
            "Check": "Dataset contains rows",
            "Status": "PASS" if rows > 0 else "REVIEW",
            "Detail": f"{rows:,} rows",
        },
        {
            "Check": "Column names are unique",
            "Status": "PASS" if duplicate_columns == 0 else "REVIEW",
            "Detail": "No duplicate columns" if duplicate_columns == 0 else f"{duplicate_columns} duplicate column name(s)",
        },
        {
            "Check": "Duplicate rows",
            "Status": "PASS" if duplicate_rows == 0 else "REVIEW",
            "Detail": "None" if duplicate_rows == 0 else f"{duplicate_rows:,} duplicate row(s)",
        },
        {
            "Check": "Missing cells",
            "Status": "PASS" if missing_cells == 0 else "REVIEW",
            "Detail": "None" if missing_cells == 0 else f"{missing_cells:,} missing cell(s)",
        },
        {
            "Check": "Empty text cells",
            "Status": "PASS" if empty_strings == 0 else "REVIEW",
            "Detail": "None" if empty_strings == 0 else f"{empty_strings:,} empty text cell(s)",
        },
        {
            "Check": "Numeric measures",
            "Status": "PASS" if numeric_columns else "INFO",
            "Detail": f"{len(numeric_columns):,} numeric column(s)",
        },
        {
            "Check": "Date/time fields",
            "Status": "PASS" if date_like_columns else "INFO",
            "Detail": f"{len(date_like_columns):,} date-like column(s)",
        },
        {
            "Check": "Constant columns",
            "Status": "PASS" if not constant_columns else "INFO",
            "Detail": "None" if not constant_columns else f"{len(constant_columns)} constant column(s)",
        },
        {
            "Check": "Negative numeric cells",
            "Status": "INFO",
            "Detail": f"{negative_numeric_cells:,} negative numeric cell(s); review against domain rules.",
        },
    ]

    penalty = 0.0
    if rows == 0:
        penalty += 40
    if duplicate_columns:
        penalty += min(25, duplicate_columns * 5)
    if rows:
        penalty += min(20, (duplicate_rows / rows) * 100)
        penalty += min(20, (missing_cells / max(1, rows * max(1, cols))) * 100)

    score = round(max(0.0, min(100.0, 100.0 - penalty)), 1)
    status = "PASS" if rows > 0 and duplicate_columns == 0 and score >= 90 else "REVIEW"

    return {
        "status": status,
        "score": score,
        "rows": rows,
        "columns": cols,
        "duplicate_columns": duplicate_columns,
        "duplicate_rows": duplicate_rows,
        "missing_cells": missing_cells,
        "empty_strings": empty_strings,
        "numeric_columns": numeric_columns,
        "date_like_columns": date_like_columns,
        "constant_columns": constant_columns,
        "negative_numeric_cells": negative_numeric_cells,
        "checks": checks,
    }


def summarize_module_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(df, pd.DataFrame):
        df = _as_frame(df)

    validation = validate_module_dataframe(df)
    numeric_summary = pd.DataFrame()
    if validation["numeric_columns"] and not df.empty:
        numeric_summary = (
            df[validation["numeric_columns"]]
            .apply(pd.to_numeric, errors="coerce")
            .agg(["count", "mean", "median", "min", "max"])
            .T.reset_index()
            .rename(columns={"index": "Measure"})
            .round(6)
        )

    return {
        "Rows": int(len(df)),
        "Columns": int(len(df.columns)),
        "Numeric Measures": int(len(validation["numeric_columns"])),
        "Missing Cells": int(validation["missing_cells"]),
        "Duplicate Rows": int(validation["duplicate_rows"]),
        "Data Quality Score": float(validation["score"]),
        "Readiness": validation["status"],
        "numeric_summary": numeric_summary,
    }


def _seed_from_known_module_table(module: str, keys: dict[str, str]) -> None:
    if isinstance(st.session_state.get(keys["data"]), pd.DataFrame) and not st.session_state[keys["data"]].empty:
        return
    try:
        from shoir_live_visuals import _MODULE_KEYS
        for state_key in _MODULE_KEYS.get(module, []):
            candidate = st.session_state.get(state_key)
            if isinstance(candidate, pd.DataFrame) and not candidate.empty:
                seed = candidate.copy(deep=True)
                st.session_state[keys["data"]] = seed
                st.session_state[keys["original"]] = seed.copy(deep=True)
                st.session_state[keys["validation"]] = validate_module_dataframe(seed)
                st.session_state[keys["results"]] = summarize_module_dataframe(seed)
                st.session_state[keys["meta"]] = {
                    "source": f"Existing module state · {state_key}",
                    "source_sheet": "",
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                }
                return
    except Exception:
        pass


def _init_state(module: str) -> dict[str, str]:
    keys = parity_keys(module)
    if keys["data"] not in st.session_state:
        st.session_state[keys["data"]] = pd.DataFrame()
        st.session_state[keys["original"]] = pd.DataFrame()
        st.session_state[keys["validation"]] = validate_module_dataframe(pd.DataFrame())
        st.session_state[keys["clean_audit"]] = []
        st.session_state[keys["results"]] = summarize_module_dataframe(pd.DataFrame())
        st.session_state[keys["meta"]] = {
            "source": "No dataset imported yet",
            "source_sheet": "",
            "imported_at": "",
        }
    # Re-seed from a known module table on later runs when the module renderer
    # has already initialized its domain-specific state. We never seed from
    # unrelated global workspace tables.
    _seed_from_known_module_table(module, keys)
    return keys


def _import_workbook(uploaded: Any) -> tuple[dict[str, pd.DataFrame], str]:
    from shoir_upgrade import read_uploaded_workbook
    books = read_uploaded_workbook(uploaded.getvalue(), uploaded.name)
    if not books:
        raise ValueError("The uploaded workbook contains no readable sheets.")
    return books, hashlib.sha256(uploaded.getvalue()).hexdigest()


def _store_import(module: str, raw_df: pd.DataFrame, filename: str, sheet: str, signature: str) -> None:
    keys = parity_keys(module)
    raw = raw_df.copy(deep=True)
    st.session_state[keys["data"]] = raw
    st.session_state[keys["original"]] = raw.copy(deep=True)
    st.session_state[keys["signature"]] = signature
    st.session_state[keys["clean_audit"]] = []
    st.session_state[keys["validation"]] = validate_module_dataframe(raw)
    st.session_state[keys["results"]] = summarize_module_dataframe(raw)
    st.session_state[keys["meta"]] = {
        "source": filename,
        "source_sheet": sheet,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }


def _apply_module_edit(module: str, edited: pd.DataFrame) -> None:
    keys = parity_keys(module)
    current = edited.copy(deep=True)
    st.session_state[keys["data"]] = current
    st.session_state[keys["validation"]] = validate_module_dataframe(current)
    st.session_state[keys["results"]] = summarize_module_dataframe(current)


def _build_export_xlsx(module: str, df: pd.DataFrame, validation: dict[str, Any], results: dict[str, Any], figure: go.Figure | None) -> bytes:
    from shoir_upgrade import build_excel_report

    validation_df = pd.DataFrame(validation.get("checks", []))
    results_df = results.get("numeric_summary", pd.DataFrame())
    if not isinstance(results_df, pd.DataFrame):
        results_df = pd.DataFrame()

    tables = [
        ("Module Data", df),
        ("Validation", validation_df),
        ("Results Summary", results_df),
    ]
    figures = [("Live Engineering Chart", figure)] if figure is not None else []
    return build_excel_report("Shoir-IE | " + module + " | Universal Parity", tables, figures)


def _build_export_zip(
    module: str,
    df: pd.DataFrame,
    validation: dict[str, Any],
    results: dict[str, Any],
    xlsx: bytes,
    figure_json: str | None,
) -> bytes:
    safe = _slug(module) or "module"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{safe}_data.csv", df.to_csv(index=False).encode("utf-8"))
        zf.writestr(f"{safe}_validation.json", json.dumps(validation, indent=2, default=_json_default).encode("utf-8"))
        serializable_results = {
            k: (v.to_dict(orient="records") if isinstance(v, pd.DataFrame) else v)
            for k, v in results.items()
        }
        zf.writestr(f"{safe}_results.json", json.dumps(serializable_results, indent=2, default=_json_default).encode("utf-8"))
        zf.writestr(f"{safe}_universal_parity.xlsx", xlsx)

        if figure_json:
            try:
                fig = go.Figure(json.loads(figure_json))
                zf.writestr(f"{safe}_live_chart.html", fig.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8"))
                zf.writestr(f"{safe}_live_chart.json", figure_json.encode("utf-8"))
            except Exception:
                pass

        manifest = {
            "module": module,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract": ["import", "validation", "live_graph", "results", "export", "persistence"],
            "observation_rows": int(len(df)),
            "observation_columns": int(len(df.columns)),
            "data_quality_score": validation.get("score"),
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

    return buf.getvalue()


def _render_validation_card(validation: dict[str, Any]) -> None:
    status = validation.get("status", "REVIEW")
    icon = "✅" if status == "PASS" else "🟡"
    st.markdown(f"**{icon} Data readiness: {status}**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Quality Score", f'{float(validation.get("score", 0.0)):.1f}%')
    c2.metric("Rows", f'{int(validation.get("rows", 0)):,}')
    c3.metric("Missing Cells", f'{int(validation.get("missing_cells", 0)):,}')
    c4.metric("Duplicate Rows", f'{int(validation.get("duplicate_rows", 0)):,}')
    checks = pd.DataFrame(validation.get("checks", []))
    if not checks.empty:
        with st.expander("🔎 Validation checks", expanded=False):
            st.dataframe(checks, use_container_width=True, hide_index=True)


def _render_prepare(module: str, keys: dict[str, str]) -> None:
    token = module_token(module)
    st.markdown("## 📦 Universal Module Studio")
    st.caption("A consistent engineering workspace for every module: Import → Validate → Analyze → Export → Persist.")
    st.markdown(f"**Active module:** {module}  ·  **Workspace contract:** PARITY-{token.upper()}")

    up = st.file_uploader(
        "📤 Import Excel / CSV",
        type=["xlsx", "csv"],
        key=f"module_parity_upload_{token}",
        help="The imported dataset is kept separate from authentication secrets and is included in workspace persistence.",
    )

    if up is not None:
        try:
            books, signature = _import_workbook(up)
            st.session_state[keys["workbook"]] = books
            sheet_names = list(books.keys())
            current_sheet = st.selectbox("Workbook sheet", sheet_names, key=f"module_parity_sheet_{token}")
            import_signature = f"{signature}:{current_sheet}"
            if st.session_state.get(keys["signature"]) != import_signature:
                _store_import(module, books[current_sheet], up.name, current_sheet, import_signature)
                st.success(f"Imported {len(books[current_sheet]):,} rows × {len(books[current_sheet].columns):,} columns from {current_sheet}.")
        except Exception as exc:
            st.error(f"Import failed safely: {exc}")

    df = st.session_state.get(keys["data"], pd.DataFrame())
    if not isinstance(df, pd.DataFrame):
        df = _as_frame(df)

    if df.empty:
        st.info("No module dataset is loaded yet. Import an Excel/CSV file above to activate validation, live graphs and evidence exports.")
    else:
        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            key=f"module_parity_editor_{token}",
        )
        _apply_module_edit(module, edited)
        df = edited.copy(deep=True)

    current_validation = validate_module_dataframe(df)
    st.session_state[keys["validation"]] = current_validation
    st.session_state[keys["results"]] = summarize_module_dataframe(df)
    _render_validation_card(current_validation)

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ Validate & Record", type="primary", use_container_width=True, key=f"module_parity_validate_{token}"):
            st.session_state[keys["validation"]] = validate_module_dataframe(df)
            st.session_state[keys["results"]] = summarize_module_dataframe(df)
            st.session_state[keys["meta"]]["validated_at"] = datetime.now(timezone.utc).isoformat()
            st.success("Validation snapshot recorded in the workspace.")
    with c2:
        if st.button("✨ Auto Clean & Revalidate", use_container_width=True, key=f"module_parity_clean_{token}"):
            try:
                from shoir_upgrade import clean_dataframe
                cleaned, audit = clean_dataframe(df)
                st.session_state[keys["data"]] = cleaned.copy(deep=True)
                st.session_state[keys["validation"]] = validate_module_dataframe(cleaned)
                st.session_state[keys["results"]] = summarize_module_dataframe(cleaned)
                st.session_state[keys["clean_audit"]] = audit
                st.success("Cleaning completed; the original imported snapshot remains available for reset.")
            except Exception as exc:
                st.error(f"Cleaning failed safely: {exc}")
    with c3:
        if st.button("↩️ Reset to Imported Snapshot", use_container_width=True, key=f"module_parity_reset_{token}"):
            original = st.session_state.get(keys["original"], pd.DataFrame())
            restored = original.copy(deep=True) if isinstance(original, pd.DataFrame) else pd.DataFrame()
            st.session_state[keys["data"]] = restored
            st.session_state[keys["clean_audit"]] = []
            st.session_state[keys["validation"]] = validate_module_dataframe(restored)
            st.session_state[keys["results"]] = summarize_module_dataframe(restored)
            st.success("Module dataset restored to the imported snapshot.")

    meta = st.session_state.get(keys["meta"], {})
    source = meta.get("source", "No source recorded") if isinstance(meta, dict) else "No source recorded"
    sheet = meta.get("source_sheet", "") if isinstance(meta, dict) else ""
    st.caption(f"Source: {source}{(' · ' + sheet) if sheet else ''} · Changes are captured by the workspace autosave.")


def _render_results(module: str, keys: dict[str, str]) -> None:
    token = module_token(module)
    df = st.session_state.get(keys["data"], pd.DataFrame())
    if not isinstance(df, pd.DataFrame):
        df = _as_frame(df)

    result_options: list[tuple[str, str, pd.DataFrame]] = [("Universal Module Dataset", keys["data"], df)]
    try:
        from shoir_live_visuals import discover_visual_tables
        seen = {keys["data"]}
        for label, state_key, candidate in discover_visual_tables(module):
            if state_key in seen:
                continue
            result_options.append((label, state_key, candidate.copy(deep=True)))
            seen.add(state_key)
    except Exception:
        pass

    labels = [x[0] for x in result_options]
    selected_label = st.selectbox("Result dataset", labels, key=f"module_parity_result_source_{token}")
    result_df = result_options[labels.index(selected_label)][2]

    summary = summarize_module_dataframe(result_df)
    validation = validate_module_dataframe(result_df)
    st.session_state[keys["results"]] = summary
    st.session_state[keys["validation"]] = validation

    st.markdown("### 📈 Results")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Rows", f'{summary["Rows"]:,}')
    c2.metric("Columns", f'{summary["Columns"]:,}')
    c3.metric("Numeric Measures", f'{summary["Numeric Measures"]:,}')
    c4.metric("Quality", f'{summary["Data Quality Score"]:.1f}%')
    c5.metric("Readiness", summary["Readiness"])

    if not result_df.empty:
        st.dataframe(result_df.head(500), use_container_width=True, hide_index=True)
    else:
        st.info("No tabular result has been produced yet. Import data above or run the module's own calculation to populate this surface.")

    numeric_summary = summary.get("numeric_summary", pd.DataFrame())
    if isinstance(numeric_summary, pd.DataFrame) and not numeric_summary.empty:
        with st.expander("📐 Numeric result statistics", expanded=False):
            st.dataframe(numeric_summary, use_container_width=True, hide_index=True)

    try:
        from shoir_live_visuals import render_live_visualization_studio
        render_live_visualization_studio(module, expanded=False, preferred_key=keys["data"])
    except Exception as exc:
        st.warning("Live Visualization Studio is temporarily unavailable; tabular results remain available.")
        with st.expander("Visualization diagnostic"):
            st.code(f"{type(exc).__name__}: {exc}")

    figure_json = st.session_state.get(f"liveviz_last_figure_json_{token}")
    figure: go.Figure | None = None
    if isinstance(figure_json, str) and figure_json:
        try:
            figure = go.Figure(json.loads(figure_json))
        except Exception:
            figure = None

    xlsx_bytes: bytes | None = None
    if not result_df.empty:
        try:
            xlsx_bytes = _build_export_xlsx(module, result_df, validation, summary, figure)
        except Exception as exc:
            st.warning(f"Workbook export could not be generated for this result set: {exc}")

    st.markdown("### 📤 Export & Evidence")
    ea, eb, ec = st.columns(3)
    with ea:
        if xlsx_bytes is not None:
            st.download_button(
                "📥 Download Excel evidence",
                data=xlsx_bytes,
                file_name=f"shoir_ie_{_slug(module)}_parity.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"module_parity_xlsx_{token}",
            )
    with eb:
        st.download_button(
            "📄 Download CSV results",
            data=result_df.to_csv(index=False).encode("utf-8"),
            file_name=f"shoir_ie_{_slug(module)}_results.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"module_parity_csv_{token}",
        )
    with ec:
        zip_bytes = _build_export_zip(
            module,
            result_df,
            validation,
            summary,
            xlsx_bytes or b"",
            figure_json if isinstance(figure_json, str) else None,
        )
        st.download_button(
            "🗂️ Download evidence bundle",
            data=zip_bytes,
            file_name=f"shoir_ie_{_slug(module)}_evidence.zip",
            mime="application/zip",
            use_container_width=True,
            key=f"module_parity_zip_{token}",
        )

    st.caption("Persistence: the parity dataset, validation snapshot and results summary live in workspace state and are captured by Shoir-IE autosave; the configured durable backend remains authoritative in managed deployments.")


def render_universal_module_parity(module: str, *, phase: str = "prepare") -> None:
    """Render the shared module parity surface.

    phase='prepare' belongs before the module engine; phase='results' belongs
    after it. Splitting these stages prevents module-specific calculations from
    being disrupted while still giving every module the same contract.
    """
    if not module:
        return

    keys = _init_state(module)

    if phase == "prepare":
        _render_prepare(module, keys)
    elif phase == "results":
        _render_results(module, keys)
    else:
        raise ValueError("phase must be 'prepare' or 'results'")
