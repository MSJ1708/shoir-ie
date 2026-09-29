"""Shoir-IE universal platform kernel.

Cross-cutting contracts for every engineering module:
DATA -> VALIDATE -> MODEL -> RUN -> VISUALIZE -> COMPARE -> EXPLAIN ->
DECIDE -> EXPORT -> VERIFY.

The kernel is additive. Domain engines keep ownership of their calculations;
the kernel supplies common workflow state, provenance, evidence, performance,
reproducibility, visualization labeling, and adapter metadata.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
from shoir_repository import sqlite_connect as shoir_sqlite_connect
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd
import streamlit as st

WORKFLOW_STEPS = (
    "DATA",
    "VALIDATE",
    "MODEL",
    "RUN",
    "VISUALIZE",
    "COMPARE",
    "EXPLAIN",
    "DECIDE",
    "EXPORT",
    "VERIFY",
)

PROVENANCE_STATES = ("LIVE", "IMPORTED", "SIMULATED", "DEMO")
WORKFLOW_VERSION = "1.0"
_KERNEL_FLAG = "_shoir_universal_kernel_v1"

GROUPED_160_VIEWS = {
    "Work": ("Overview", "Data", "Scenarios"),
    "Intelligence": ("Digital Thread", "Copilot", "Insights"),
    "Governance": ("Decisions", "Runs & Evidence"),
    "Platform": ("Connectors", "160 Matrix"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def active_dataframe() -> tuple[pd.DataFrame, str]:
    preferred = (
        "universal_active_dataset",
        "excel_studio_visual_df",
        "industrial_workbook_current_df",
        "data_platform_latest_df",
        "unified_data",
        "os160_cleaned_df",
        "copilot_workbook",
        "excel_studio_df",
    )
    for key in preferred:
        value = st.session_state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value, key
    for key, value in list(st.session_state.items()):
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value, str(key)
    return pd.DataFrame(), ""


def dataset_hash(df: pd.DataFrame) -> str:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ""
    try:
        payload = pd.util.hash_pandas_object(df, index=True).values.tobytes()
        schema = "|".join(f"{c}:{df[c].dtype}" for c in df.columns).encode("utf-8")
        return hashlib.sha256(payload + schema).hexdigest()
    except Exception:
        return hashlib.sha256(df.to_csv(index=True).encode("utf-8", errors="replace")).hexdigest()


def readiness_snapshot(df: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {
            "score": 0.0,
            "rows": 0,
            "columns": 0,
            "missing_pct": 100.0,
            "duplicate_pct": 0.0,
            "numeric_columns": 0,
            "warnings": ["No active engineering dataset."],
        }
    rows, cols = len(df), len(df.columns)
    missing_pct = float(df.isna().mean().mean() * 100.0) if cols else 100.0
    duplicate_pct = float(df.duplicated().mean() * 100.0) if rows else 0.0
    warnings = []
    if missing_pct > 10:
        warnings.append(f"Missingness is {missing_pct:.1f}%.")
    if duplicate_pct > 5:
        warnings.append(f"Duplicate rows are {duplicate_pct:.1f}%.")
    score = max(0.0, min(100.0, 100.0 - 0.55 * missing_pct - 0.45 * duplicate_pct))
    return {
        "score": score,
        "rows": rows,
        "columns": cols,
        "missing_pct": missing_pct,
        "duplicate_pct": duplicate_pct,
        "numeric_columns": len(df.select_dtypes(include=np.number).columns),
        "warnings": warnings,
    }


@st.cache_data(ttl=600, max_entries=64, show_spinner=False)
def cached_profile(df: pd.DataFrame) -> dict[str, Any]:
    snap = readiness_snapshot(df)
    snap["fingerprint"] = dataset_hash(df)
    snap["columns"] = [str(c) for c in df.columns]
    snap["dtypes"] = {str(c): str(df[c].dtype) for c in df.columns}
    return snap


def paginate_dataframe(df: pd.DataFrame, page: int = 1, page_size: int = 250) -> tuple[pd.DataFrame, int, int]:
    page_size = max(25, min(int(page_size), 2000))
    total_pages = max(1, math.ceil(len(df) / page_size))
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * page_size
    return df.iloc[start:start + page_size], page, total_pages


def set_provenance(status: str, *, source: str = "", version: str = "", data_hash: str = "") -> None:
    state = str(status).upper().strip()
    if state not in PROVENANCE_STATES:
        raise ValueError(f"Unsupported provenance status: {status}")
    st.session_state["shoir_data_status"] = state
    if source:
        st.session_state["shoir_data_source"] = source
    if version:
        st.session_state["shoir_data_version"] = version
    if data_hash:
        st.session_state["shoir_data_hash"] = data_hash


def provenance() -> str:
    state = str(st.session_state.get("shoir_data_status", "")).upper().strip()
    if state in PROVENANCE_STATES:
        return state
    source_key = str(st.session_state.get("shoir_data_source_key", "")).lower()
    if source_key in {"live", "iot", "telemetry", "connector"}:
        return "LIVE"
    if source_key in {"imported", "upload", "workbook"}:
        return "IMPORTED"
    if source_key in {"simulated", "scenario", "simulation"}:
        return "SIMULATED"
    _, key = active_dataframe()
    joined = f"{source_key} {key}".lower()
    if any(x in joined for x in ("upload", "import", "excel", "workbook")):
        return "IMPORTED"
    if any(x in joined for x in ("scenario", "simulation", "forecast", "monte", "experiment")):
        return "SIMULATED"
    return "DEMO"


def init_module_contract(module: str) -> dict[str, Any]:
    df, source_key = active_dataframe()
    profile = cached_profile(df) if not df.empty else readiness_snapshot(df)
    ctx = {
        "version": WORKFLOW_VERSION,
        "module": str(module),
        "dataset_key": source_key,
        "dataset_hash": profile.get("fingerprint") or dataset_hash(df),
        "provenance": provenance(),
        "readiness": profile,
        "run_id": st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id"),
        "started_at": now_iso(),
        "started_monotonic": time.perf_counter(),
    }
    st.session_state["shoir_universal_module_contract"] = ctx
    stage_map = dict(st.session_state.get("shoir_universal_workflow_stage_by_module", {}))
    history_map = dict(st.session_state.get("shoir_universal_workflow_history_by_module", {}))
    stage_map.setdefault(str(module), "DATA")
    history_map.setdefault(str(module), [])
    st.session_state["shoir_universal_workflow_stage_by_module"] = stage_map
    st.session_state["shoir_universal_workflow_history_by_module"] = history_map
    return ctx


def workflow_state(module: str | None = None) -> dict[str, Any]:
    target = str(module or (st.session_state.get("shoir_universal_module_contract") or {}).get("module") or "Engineering")
    stage_map = dict(st.session_state.get("shoir_universal_workflow_stage_by_module", {}))
    history_map = dict(st.session_state.get("shoir_universal_workflow_history_by_module", {}))
    stage = str(stage_map.get(target, "DATA"))
    if stage not in WORKFLOW_STEPS:
        stage = "DATA"
    return {
        "module": target,
        "stage": stage,
        "index": WORKFLOW_STEPS.index(stage),
        "history": list(history_map.get(target, [])),
    }


def _stage_ready(stage: str, ctx: Mapping[str, Any]) -> tuple[bool, str]:
    idx = WORKFLOW_STEPS.index(stage)
    current = workflow_state(str(ctx.get("module") or "Engineering"))["index"]
    profile = ctx.get("readiness") or {}
    has_data = int(profile.get("rows", 0)) > 0
    run_id = bool(ctx.get("run_id") or st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id"))
    result_present = any(
        isinstance(v, pd.DataFrame) and not v.empty
        for v in st.session_state.values()
    )
    if stage == "DATA":
        return True, "Dataset entry point is available."
    if stage == "VALIDATE":
        return has_data, "A non-empty dataset is required."
    if stage == "MODEL":
        return has_data and (float(profile.get("score", 0.0)) >= 50.0 or current >= 1), "Resolve major data-readiness issues before modeling."
    if stage == "RUN":
        return current >= 2, "Complete DATA, VALIDATE and MODEL stages first."
    if stage == "VISUALIZE":
        return run_id or result_present or current >= 3, "A run or analysis result is required."
    if stage in {"COMPARE", "EXPLAIN", "DECIDE", "EXPORT"}:
        return result_present or run_id or current >= 4, "An analysis result/run is required."
    if stage == "VERIFY":
        return bool(run_id or current >= 8), "A recorded run or decision evidence is required."
    return idx <= current + 1, "Advance through the workflow in order."


def advance_workflow(target: str, ctx: Mapping[str, Any]) -> tuple[bool, str]:
    target = str(target).upper()
    if target not in WORKFLOW_STEPS:
        return False, "Unknown workflow stage."
    current = workflow_state()["index"]
    target_idx = WORKFLOW_STEPS.index(target)
    if target_idx > current + 1:
        return False, "Workflow stages must be completed in order."
    ready, reason = _stage_ready(target, ctx)
    if not ready:
        return False, reason
    module = str(ctx.get("module") or "Engineering")
    stage_map = dict(st.session_state.get("shoir_universal_workflow_stage_by_module", {}))
    history_map = dict(st.session_state.get("shoir_universal_workflow_history_by_module", {}))
    stage_map[module] = target
    history = list(history_map.get(module, []))
    history.append({"stage": target, "timestamp": now_iso(), "module": module})
    history_map[module] = history[-30:]
    st.session_state["shoir_universal_workflow_stage_by_module"] = stage_map
    st.session_state["shoir_universal_workflow_history_by_module"] = history_map
    return True, f"Workflow moved to {target}."


def workflow_gate(required_stage: str) -> bool:
    idx = WORKFLOW_STEPS.index(str(required_stage).upper())
    current = workflow_state()["index"]
    return current >= idx


def _badge(state: str) -> str:
    tones = {
        "LIVE": ("#ecfdf5", "#047857", "#a7f3d0"),
        "IMPORTED": ("#eff6ff", "#1d4ed8", "#bfdbfe"),
        "SIMULATED": ("#fffbeb", "#b45309", "#fde68a"),
        "DEMO": ("#f8fafc", "#475569", "#cbd5e1"),
    }
    bg, fg, border = tones.get(state, tones["DEMO"])
    return (
        f"<span style='display:inline-block;padding:4px 8px;border-radius:999px;"
        f"background:{bg};color:{fg};border:1px solid {border};font-size:10px;"
        f"font-weight:900;letter-spacing:.04em'>{state}</span>"
    )


def render_universal_workflow(module: str, ctx: Mapping[str, Any]) -> None:
    state = workflow_state(module)
    st.markdown("### Universal Engineering Workflow")
    chips = []
    for i, step in enumerate(WORKFLOW_STEPS):
        cls = "active" if i == state["index"] else ("done" if i < state["index"] else "")
        chips.append(
            f"<span style='display:inline-block;margin:2px;padding:6px 9px;border-radius:999px;"
            f"border:1px solid #dbe4ef;background:{'#eff6ff' if cls=='done' else '#f0fdfa' if cls=='active' else '#fff'};"
            f"color:{'#1d4ed8' if cls=='done' else '#0f766e' if cls=='active' else '#64748b'};"
            f"font-size:10px;font-weight:850'>{i+1:02d} {step}</span>"
        )
    st.markdown(" ".join(chips), unsafe_allow_html=True)
    st.caption(
        f"{module} · {_badge(str(ctx.get('provenance', 'DEMO')))} · "
        f"Readiness {float((ctx.get('readiness') or {}).get('score', 0.0)):.0f}%"
    )
    current_idx = state["index"]
    if current_idx < len(WORKFLOW_STEPS) - 1:
        next_stage = WORKFLOW_STEPS[current_idx + 1]
        ready, reason = _stage_ready(next_stage, ctx)
        c1, c2 = st.columns([1, 2])
        with c1:
            if st.button(
                f"Advance → {next_stage}",
                key=f"shoir_universal_advance_{module}",
                disabled=not ready,
                use_container_width=True,
            ):
                ok, msg = advance_workflow(next_stage, ctx)
                if ok:
                    st.rerun()
        with c2:
            st.caption(reason if not ready else f"Next gate: {next_stage} is available.")
    else:
        st.success("Verification stage reached. Exported evidence and decision records can be audited from the shell.")


def _captured_source_bytes() -> tuple[str, bytes]:
    for key, value in list(st.session_state.items()):
        name = str(key).lower()
        if not any(token in name for token in ("upload", "workbook", "raw")):
            continue
        try:
            if isinstance(value, (bytes, bytearray)) and value:
                return str(key), bytes(value)
            getter = getattr(value, "getvalue", None)
            if callable(getter):
                raw = getter()
                if isinstance(raw, (bytes, bytearray)) and raw:
                    return str(key), bytes(raw)
        except Exception:
            continue
    return "", b""


def _evidence_payload(module: str, ctx: Mapping[str, Any], figure_count: int = 0) -> dict[str, Any]:
    df, source_key = active_dataframe()
    profile = ctx.get("readiness") or readiness_snapshot(df)
    return {
        "platform": "Shoir-IE",
        "workflow_version": WORKFLOW_VERSION,
        "module": module,
        "captured_at": now_iso(),
        "provenance": provenance(),
        "dataset": {
            "session_key": source_key,
            "source": st.session_state.get("shoir_data_source"),
            "version": st.session_state.get("shoir_data_version"),
            "sha256": st.session_state.get("shoir_data_hash") or profile.get("fingerprint"),
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "missing_cells": int(df.isna().sum().sum()) if not df.empty else 0,
        },
        "workflow": workflow_state(module),
        "run_id": st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id"),
        "copilot_prompt": str(st.session_state.get("shoir_universal_copilot_prompt") or st.session_state.get("os160_prompt") or ""),
        "figure_provenance": dict(st.session_state.get("shoir_last_figure_provenance") or {}),
        "figures_captured": int(figure_count),
        "assumptions": _jsonable(st.session_state.get("shoir_assumptions", [])),
        "software": {
            "python": __import__("sys").version.split()[0],
            "streamlit": getattr(st, "__version__", "unknown"),
        },
    }


def build_reproduction_package(module: str, ctx: Mapping[str, Any], results: Any = None, parameters: Mapping[str, Any] | None = None) -> bytes:
    df, _ = active_dataframe()
    evidence = _evidence_payload(module, ctx)
    evidence["parameters"] = _jsonable(dict(parameters or st.session_state.get("shoir_run_parameters", {})))
    evidence["result_summary"] = _jsonable(
        results.to_dict(orient="records")[:200] if isinstance(results, pd.DataFrame) else results
    )
    raw_csv = df.to_csv(index=False).encode("utf-8") if not df.empty else b""
    profile = cached_profile(df) if not df.empty else readiness_snapshot(df)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(evidence, indent=2, default=str))
        zf.writestr("dataset.csv", raw_csv)
        source_key, source_bytes = _captured_source_bytes()
        if source_bytes:
            safe_key = re.sub(r"[^A-Za-z0-9._-]+", "_", str(source_key)).strip("._") or "captured_source"
            zf.writestr(f"source/{safe_key}.bin", source_bytes)
        zf.writestr("dataset_profile.json", json.dumps(profile, indent=2, default=str))
        audit = st.session_state.get("shoir_excel_cleaning_audit") or st.session_state.get("os160_clean_audit")
        if audit:
            zf.writestr("cleaning_audit.json", json.dumps(_jsonable(audit), indent=2, default=str))
        fig = st.session_state.get("shoir_last_figure")
        if fig is not None and hasattr(fig, "to_json"):
            zf.writestr("figures/last_figure.json", fig.to_json())
        zf.writestr(
            "workflow_history.json",
            json.dumps(workflow_state(module).get("history", []), indent=2, default=str),
        )
        zf.writestr(
            "session_parameters.json",
            json.dumps(_jsonable(dict(st.session_state.get("shoir_run_parameters", {}))), indent=2, default=str),
        )
    return buf.getvalue()


def register_reproduction_package(module: str, ctx: Mapping[str, Any], results: Any = None, parameters: Mapping[str, Any] | None = None) -> None:
    st.session_state["shoir_last_reproduction_manifest"] = _evidence_payload(module, ctx)
    st.session_state["shoir_last_reproduction_package"] = build_reproduction_package(module, ctx, results, parameters)


def render_reproduction_controls(module: str, ctx: Mapping[str, Any]) -> None:
    with st.expander("Reproducibility & Evidence", expanded=False):
        st.caption("Captured package: dataset snapshot, provenance, workflow history, parameters, cleaning audit and available figure evidence.")
        if st.button("Create reproduction package", key=f"shoir_repro_create_{module}"):
            register_reproduction_package(module, ctx)
            st.success("Reproduction package captured from the current workflow state.")
        package = st.session_state.get("shoir_last_reproduction_package")
        if package:
            st.download_button(
                "Download reproduction package",
                data=package,
                file_name=f"shoir_{hashlib.sha256(str(module).encode()).hexdigest()[:10]}_reproduction.zip",
                mime="application/zip",
                key=f"shoir_repro_download_{module}",
                use_container_width=True,
            )
        manifest = st.session_state.get("shoir_last_reproduction_manifest")
        if manifest:
            prompt = str(manifest.get("copilot_prompt") or "").strip()
            if prompt and not st.session_state.get("shoir_reproduction_result"):
                if st.button("Reproduce captured workflow", key=f"shoir_repro_run_{module}", use_container_width=True):
                    try:
                        df, _ = active_dataframe()
                        if df.empty:
                            raise ValueError("The captured workflow has no active dataset to reproduce.")
                        from shoir_copilot_orchestrator import run_orchestration
                        reproduction = run_orchestration(
                            prompt,
                            str(module),
                            df.copy(deep=True),
                            context={
                                "actor": st.session_state.get("current_user", "unknown"),
                                "workspace": st.session_state.get("workspace", "default"),
                            },
                        )
                        st.session_state["shoir_reproduction_result"] = reproduction
                        st.success("Captured workflow reproduced from the current dataset snapshot.")
                    except Exception as exc:
                        st.error(f"Reproduction could not be completed safely: {type(exc).__name__}: {exc}")
            repro = st.session_state.get("shoir_reproduction_result")
            if isinstance(repro, Mapping):
                st.markdown("**Reproduction result**")
                st.write({
                    "run_id": repro.get("run_id"),
                    "module": repro.get("module"),
                    "status": repro.get("status") or repro.get("analysis_meta", {}).get("status"),
                })
            st.json(manifest)


def render_universal_inspector(module: str, ctx: Mapping[str, Any]) -> None:
    df, source_key = active_dataframe()
    profile = ctx.get("readiness") or readiness_snapshot(df)
    run_id = st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id") or "not assigned"
    source = st.session_state.get("shoir_data_source") or source_key or "not declared"
    version = st.session_state.get("shoir_data_version") or "session/latest"
    digest = st.session_state.get("shoir_data_hash") or profile.get("fingerprint") or "not available"
    project = st.session_state.get("shoir_project_name") or st.session_state.get("active_workspace_name") or "No active project"
    warnings = profile.get("warnings") or []

    trace_rows = []
    try:
        with shoir_sqlite_connect("enterprise_full_workspace.db", timeout=5) as conn:
            entity_rows = conn.execute(
                "SELECT entity_type,name,status FROM os160_entities ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        trace_rows = [{"type": str(row[0]), "name": str(row[1]), "status": str(row[2])} for row in entity_rows]
    except Exception:
        trace_rows = []
    trace_summary = " → ".join(
        str(x) for x in (
            "Dataset",
            "Process",
            "KPI",
            "Scenario",
            "Run",
            "Decision",
            "Outcome",
        )
    )
    timing = st.session_state.get("shoir_last_engine_timing", {})
    try:
        timing_text = f"{float(timing.get('duration_ms', 0.0)):.0f} ms"
    except Exception:
        timing_text = "not recorded"

    # A compact interactive Trace/Evidence control sits above the persistent right drawer.
    tc1, tc2 = st.columns([1, 1])
    with tc1:
        show_trace = st.checkbox("Trace context", value=False, key=f"shoir_trace_toggle_{module}")
    with tc2:
        manifest = _evidence_payload(module, ctx)
        st.download_button(
            "Evidence manifest",
            data=json.dumps(manifest, indent=2, default=str).encode("utf-8"),
            file_name=f"shoir_{hashlib.sha256(str(module).encode()).hexdigest()[:10]}_evidence.json",
            mime="application/json",
            key=f"shoir_evidence_manifest_{module}",
            use_container_width=True,
        )
    if show_trace:
        st.markdown("**Digital Thread trace**")
        st.caption(trace_summary)
        if trace_rows:
            st.dataframe(pd.DataFrame(trace_rows), use_container_width=True, hide_index=True, height=190)
        else:
            st.info("No persisted canonical entity records are available yet; the trace contract remains active for this module.")

    html = f"""
<style>
#shoir-universal-inspector {{
position:fixed;right:18px;top:118px;width:300px;max-height:72vh;overflow:auto;
z-index:9999;background:rgba(255,255,255,.97);border:1px solid #dbe4ef;border-radius:18px;
box-shadow:0 18px 50px rgba(15,23,42,.16);padding:14px;font-family:Inter,system-ui,sans-serif;
}}
#shoir-universal-inspector .label {{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#94a3b8;font-weight:900}}
#shoir-universal-inspector .value {{font-size:12px;color:#0f172a;font-weight:750;margin-bottom:9px;word-break:break-word}}
#shoir-universal-inspector .state {{display:inline-block;padding:4px 7px;border-radius:999px;font-size:9px;font-weight:900}}
</style>
<div id="shoir-universal-inspector">
  <div style="font-size:15px;font-weight:900;color:#0f172a">Inspector</div>
  <div style="font-size:11px;color:#64748b;margin:2px 0 10px">{module}</div>
  <div class="label">Data state</div><div class="value">{_badge(provenance())}</div>
  <div class="label">Project</div><div class="value">{project}</div>
  <div class="label">Dataset</div><div class="value">{source}</div>
  <div class="label">Version</div><div class="value">{version}</div>
  <div class="label">SHA-256</div><div class="value">{digest}</div>
  <div class="label">Readiness</div><div class="value">{float(profile.get('score',0.0)):.1f}% · {int(profile.get('rows',0)):,} × {int(profile.get('columns',0)):,}</div>
  <div class="label">Run</div><div class="value">{run_id}</div>
  <div class="label">Workflow</div><div class="value">{workflow_state(module)['stage']} · {len(workflow_state(module)['history'])} recorded transitions</div>
  <div class="label">Execution</div><div class="value">{timing_text}</div>
  <div class="label">Why this number?</div>
  <div style="font-size:10px;color:#475569;line-height:1.45">
    Values are derived from the active dataset and the recorded workflow state.
    Use the provenance package below to inspect source, version, fingerprint,
    assumptions and run context.
  </div>
  <div class="label" style="margin-top:10px">Warnings</div>
  <div class="value">{'; '.join(str(x) for x in warnings) if warnings else 'None recorded'}</div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


def render_global_copilot_bar(allowed_modules: Sequence[str] | None = None) -> None:
    st.markdown("### Ask Shoir")
    prompt = st.text_input(
        "Global engineering Copilot",
        placeholder="Clean this workbook, check readiness, compare scenarios, prepare evidence…",
        key="shoir_universal_copilot_prompt",
        label_visibility="collapsed",
    )
    if not prompt.strip():
        return
    current_module = str(st.session_state.get("selected_module", "Engineering"))
    try:
        from shoir_copilot_orchestrator import build_workflow_plan
        df, _ = active_dataframe()
        plan = build_workflow_plan(prompt, current_module, df)
        st.session_state["shoir_universal_copilot_plan"] = plan
        st.info("Workflow plan prepared from the active data; execution remains approval-gated.")
        with st.expander("Copilot plan", expanded=True):
            for idx, step in enumerate(plan.get("steps", []), 1):
                st.markdown(f"{idx}. **{step.get('step') or step.get('tool') or 'Step'}** — {step.get('detail','')}")
    except Exception as exc:
        st.warning(f"Copilot planning unavailable: {type(exc).__name__}: {exc}")


def install_visualization_contract() -> None:
    if st.session_state.get(_KERNEL_FLAG):
        return
    st.markdown(
        """<style>
        [data-testid="stMetric"]{border:1px solid #dbe4ef;border-radius:14px;padding:10px 12px;background:#fff;box-shadow:0 5px 16px rgba(15,23,42,.035)}
        [data-testid="stButton"]>button{border-radius:10px;font-weight:750}
        [data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stSelectbox"]>div{border-radius:10px}
        .stExpander{border-radius:14px}
        h1,h2,h3{letter-spacing:-.02em}
        </style>""",
        unsafe_allow_html=True,
    )
    original = st.plotly_chart

    def contracted_plotly_chart(figure: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            state = provenance()
            source = st.session_state.get("shoir_data_source") or "active dataset"
            version = st.session_state.get("shoir_data_version") or "session"
            run_id = st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id") or "n/a"
            if hasattr(figure, "add_annotation"):
                figure.add_annotation(
                    x=1,
                    y=1.02,
                    xref="paper",
                    yref="paper",
                    text=f"{state} · {source} · {version} · run {run_id}",
                    showarrow=False,
                    xanchor="right",
                    yanchor="bottom",
                    font=dict(size=9),
                    opacity=0.72,
                )
                figure.update_layout(margin=dict(t=max(58, int(getattr(figure.layout.margin, "t", 0) or 0))))
            st.session_state["shoir_last_figure_provenance"] = {
                "state": state,
                "source": source,
                "version": version,
                "run_id": run_id,
                "captured_at": now_iso(),
            }
        except Exception as exc:
            st.session_state.setdefault("shoir_platform_warnings", []).append({"scope": "plot_provenance", "type": type(exc).__name__, "message": str(exc)[:500], "at": now_iso()})
        return original(figure, *args, **kwargs)

    st.plotly_chart = contracted_plotly_chart
    st.session_state[_KERNEL_FLAG] = True


def domain_engine_metadata(module: str) -> dict[str, Any]:
    name = str(module)
    return {
        "contract_version": WORKFLOW_VERSION,
        "engine": name,
        "inputs": ["dataset", "validated_schema", "parameters"],
        "outputs": ["results", "visualizations", "evidence"],
        "lifecycle": list(WORKFLOW_STEPS),
        "provenance_required": True,
        "reproducibility_required": True,
    }


@contextmanager
def domain_engine_run(module: str):
    ctx = init_module_contract(module)
    started = time.perf_counter()
    try:
        yield ctx
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        st.session_state["shoir_last_engine_timing"] = {
            "module": module,
            "duration_ms": round(elapsed_ms, 2),
            "captured_at": now_iso(),
        }
        st.session_state["shoir_last_engine_contract"] = domain_engine_metadata(module)


def finalize_module_contract(module: str) -> dict[str, Any]:
    """Finalize cross-module timing/evidence metadata after the renderer executes."""
    ctx = dict(st.session_state.get("shoir_universal_module_contract", {}))
    ctx["module"] = str(module)
    ctx["completed_at"] = now_iso()
    started = ctx.get("started_monotonic")
    if isinstance(started, (int, float)):
        ctx["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
    else:
        ctx["duration_ms"] = None
    df, source_key = active_dataframe()
    profile = cached_profile(df) if not df.empty else readiness_snapshot(df)
    ctx["dataset_key"] = source_key
    ctx["dataset_hash"] = st.session_state.get("shoir_data_hash") or profile.get("fingerprint") or dataset_hash(df)
    ctx["provenance"] = provenance()
    ctx["readiness"] = profile
    ctx["run_id"] = st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id")
    st.session_state["shoir_universal_module_contract"] = ctx
    # Reconcile runtime observations into the governed workflow state.
    state = workflow_state(module)
    observed_index = state["index"]
    if ctx.get("run_id"):
        observed_index = max(observed_index, WORKFLOW_STEPS.index("RUN"))
    if st.session_state.get("shoir_last_figure_provenance"):
        observed_index = max(observed_index, WORKFLOW_STEPS.index("VISUALIZE"))
    if st.session_state.get("os160_last_decision") or st.session_state.get("shoir_latest_decision_id"):
        observed_index = max(observed_index, WORKFLOW_STEPS.index("DECIDE"))
    if st.session_state.get("shoir_latest_outcome_id"):
        observed_index = max(observed_index, WORKFLOW_STEPS.index("VERIFY"))
    if observed_index != state["index"]:
        stage_map = dict(st.session_state.get("shoir_universal_workflow_stage_by_module", {}))
        history_map = dict(st.session_state.get("shoir_universal_workflow_history_by_module", {}))
        stage = WORKFLOW_STEPS[observed_index]
        stage_map[str(module)] = stage
        history = list(history_map.get(str(module), []))
        history.append({"stage": stage, "timestamp": now_iso(), "module": str(module), "source": "runtime-observation"})
        history_map[str(module)] = history[-30:]
        st.session_state["shoir_universal_workflow_stage_by_module"] = stage_map
        st.session_state["shoir_universal_workflow_history_by_module"] = history_map
    st.session_state["shoir_last_module_contract"] = {**domain_engine_metadata(module), "timing_ms": ctx["duration_ms"], "completed_at": ctx["completed_at"]}
    st.session_state["shoir_last_evidence_manifest"] = _evidence_payload(module, ctx)
    return ctx


def evidence_manifest(module: str = "") -> dict[str, Any]:
    current = st.session_state.get("shoir_last_evidence_manifest")
    if isinstance(current, Mapping):
        return dict(current)
    target = module or str(st.session_state.get("selected_module", "Engineering"))
    ctx = init_module_contract(target)
    return _evidence_payload(target, ctx)


def submit_universal_background_job(
    username: str,
    module: str,
    job_type: str,
    payload: Mapping[str, Any],
    task: Callable[[], Any],
    workspace: str = "default",
) -> str:
    """Route expensive domain work through the enterprise background-job service."""
    from shoir_enterprise_layer import submit_background_job
    return submit_background_job(
        str(username),
        str(module),
        str(job_type),
        dict(payload),
        task,
        workspace=str(workspace),
    )


def platform_snapshot(module: str = "") -> dict[str, Any]:
    df, source_key = active_dataframe()
    profile = cached_profile(df) if not df.empty else readiness_snapshot(df)
    return {
        "kernel_version": WORKFLOW_VERSION,
        "module": module,
        "workflow": workflow_state(),
        "provenance": provenance(),
        "dataset_key": source_key,
        "profile": profile,
        "run_id": st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id"),
        "engine_timing": st.session_state.get("shoir_last_engine_timing", {}),
        "contract": domain_engine_metadata(module) if module else {},
    }


def install_and_render_module_context(module: str, *, show_copilot: bool = False) -> dict[str, Any]:
    install_visualization_contract()
    ctx = init_module_contract(module)
    render_universal_workflow(module, ctx)
    render_universal_inspector(module, ctx)
    render_reproduction_controls(module, ctx)
    if show_copilot:
        render_global_copilot_bar()
    return ctx


__all__ = [
    "WORKFLOW_STEPS",
    "PROVENANCE_STATES",
    "GROUPED_160_VIEWS",
    "active_dataframe",
    "cached_profile",
    "paginate_dataframe",
    "set_provenance",
    "provenance",
    "init_module_contract",
    "workflow_state",
    "advance_workflow",
    "workflow_gate",
    "render_universal_workflow",
    "build_reproduction_package",
    "render_reproduction_controls",
    "render_universal_inspector",
    "render_global_copilot_bar",
    "install_visualization_contract",
    "domain_engine_metadata",
    "domain_engine_run",
    "submit_universal_background_job",
    "platform_snapshot",
    "finalize_module_contract",
    "evidence_manifest",
    "install_and_render_module_context",
]
