"""Shoir-IE Universal Industrial Engine.

A thin integration kernel over the existing workbook, Digital Thread, Copilot,
persistence, enterprise governance and visualization systems.  It deliberately
avoids creating parallel domain engines.  Its job is to make every module
behave like a consistent industrial workspace: inspect -> analyze -> visualize
-> explain -> trace -> act -> record.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

ENGINE_ACTION_LEVELS = (
    "Read",
    "Analyze",
    "Simulate",
    "Recommend",
    "Prepare",
    "Execute",
    "Admin",
)

AGENT_ROUTES = {
    "Forecast Agent": ("forecast", "demand", "capacity", "predict", "time series"),
    "Scheduling Agent": ("schedule", "sequencing", "production plan", "dispatch", "aps"),
    "Maintenance Agent": ("maintenance", "failure", "downtime", "asset health", "predictive"),
    "Quality Agent": ("quality", "defect", "spc", "capability", "sigma", "pareto"),
    "Supply Chain Agent": ("supply chain", "inventory", "warehouse", "logistics", "routing", "supplier"),
    "Energy Agent": ("energy", "power", "kwh", "electricity"),
    "Carbon Agent": ("carbon", "co2", "emission", "sustainability"),
    "Finance Agent": ("cost", "capex", "opex", "npv", "investment", "finance"),
    "Research Agent": ("research", "hypothesis", "experiment", "statistical", "paper"),
    "Operations Agent": ("throughput", "bottleneck", "line balance", "lean", "flow"),
    "Risk & Safety Agent": ("risk", "safety", "hazop", "hazid", "fmea", "bowtie"),
    "Resource Agent": ("resource", "labor", "workforce", "capacity", "space", "energy"),
    "Facilities Agent": ("layout", "facility", "warehouse layout", "travel distance"),
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_SENSITIVE_KEY_FRAGMENTS = ("password", "token", "secret", "otp", "api_key", "authorization", "payment")


def _redact(value: Any, key: str = "") -> Any:
    if any(fragment in str(key).lower() for fragment in _SENSITIVE_KEY_FRAGMENTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v, key) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

def _safe_frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    if isinstance(value, list):
        return pd.DataFrame(value)
    if isinstance(value, dict):
        for key in ("result", "results", "data", "frame", "table"):
            nested = value.get(key)
            if isinstance(nested, (pd.DataFrame, list, dict)):
                frame = _safe_frame(nested)
                if not frame.empty:
                    return frame
        scalars = {
            str(k): v for k, v in value.items()
            if isinstance(v, (str, int, float, np.integer, np.floating))
            and not isinstance(v, bool)
        }
        return pd.DataFrame([scalars]) if scalars else pd.DataFrame()
    return pd.DataFrame()

def module_tables(module: str, preferred_key: str | None = None) -> list[tuple[str, str, pd.DataFrame]]:
    try:
        from shoir_live_visuals import discover_visual_tables
        return discover_visual_tables(module, preferred_key=preferred_key)
    except Exception:
        return []

def data_readiness(df: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(df, pd.DataFrame):
        df = _safe_frame(df)
    rows, cols = df.shape
    missing = int(df.isna().sum().sum()) if not df.empty else 0
    duplicate_rows = int(df.duplicated().sum()) if not df.empty else 0
    duplicate_columns = int(df.columns.duplicated().sum())
    non_empty = max(1, rows * max(1, cols))
    score = max(
        0.0,
        min(
            100.0,
            100.0
            - min(25.0, missing / non_empty * 100.0)
            - min(25.0, duplicate_rows / max(1, rows) * 100.0)
            - min(25.0, duplicate_columns * 5.0),
        ),
    )
    return {
        "rows": int(rows),
        "columns": int(cols),
        "missing_cells": missing,
        "duplicate_rows": duplicate_rows,
        "duplicate_columns": duplicate_columns,
        "score": round(score, 1),
        "ready": bool(rows > 0 and duplicate_columns == 0 and score >= 85.0),
    }

def guaranteed_figure(df: pd.DataFrame, title: str = "Universal Engineering View") -> go.Figure | None:
    """Return a real figure whenever a non-empty, displayable table exists."""
    frame = _safe_frame(df)
    if frame.empty or len(frame.columns) == 0:
        return None
    try:
        from shoir_live_visuals import ensure_visualization_suite
        suite = ensure_visualization_suite(frame, context=title, max_figures=1)
        if suite:
            return suite[0][1]
    except Exception:
        pass

    numeric = [str(c) for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
    categorical = [str(c) for c in frame.columns if not pd.api.types.is_numeric_dtype(frame[c])]
    if numeric:
        metric = numeric[0]
        values = pd.to_numeric(frame[metric], errors="coerce").dropna()
        if not values.empty:
            return px.histogram(values, x=values, nbins=30, title=f"{title} · {metric}")
    if categorical:
        col = categorical[0]
        counts = (
            frame[col].astype("string").fillna("<Missing>")
            .value_counts(dropna=False)
            .head(60)
            .rename_axis(col)
            .reset_index(name="Count")
        )
        if not counts.empty:
            return px.bar(counts, x=col, y="Count", title=f"{title} · {col}")
    completeness = frame.notna().mean().mul(100).sort_values().head(80)
    return px.bar(
        x=completeness.index.astype(str),
        y=completeness.values,
        range_y=[0, 100],
        title=f"{title} · Data completeness",
        labels={"x": "Field", "y": "Completeness %"},
    ) if not completeness.empty else None

def pivot_table(
    df: pd.DataFrame,
    rows: Sequence[str],
    values: Sequence[str],
    columns: Sequence[str] | None = None,
    aggregation: str = "mean",
    filters: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    frame = _safe_frame(df)
    if frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    if filters:
        for col, value in filters.items():
            if col in work.columns and value not in (None, "", "All"):
                work = work[work[col].astype(str) == str(value)]
    row_fields = [str(c) for c in rows if str(c) in work.columns]
    value_fields = [str(c) for c in values if str(c) in work.columns]
    column_fields = [str(c) for c in (columns or []) if str(c) in work.columns]
    if not row_fields or not value_fields:
        raise ValueError("Pivot requires at least one row field and one value field.")
    agg_map = {"mean": "mean", "sum": "sum", "min": "min", "max": "max", "count": "count", "median": "median"}
    if aggregation not in agg_map:
        raise ValueError(f"Unsupported pivot aggregation: {aggregation}")
    if not column_fields and len(row_fields) == 1 and len(value_fields) == 1 and len(work) * max(1, len(work.columns)) >= 100_000:
        try:
            import duckdb  # type: ignore
            row_col, value_col = row_fields[0], value_fields[0]
            quote = lambda name: '"' + str(name).replace('"', '""') + '"'
            sql_agg = {"mean": "AVG", "sum": "SUM", "count": "COUNT", "min": "MIN", "max": "MAX", "median": "MEDIAN"}[aggregation]
            con = duckdb.connect()
            try:
                con.register("shoir_pivot_frame", work[[row_col, value_col]].copy())
                return con.execute(
                    f"SELECT {quote(row_col)} AS {quote(row_col)}, {sql_agg}(CAST({quote(value_col)} AS DOUBLE)) AS {quote(value_col)} "
                    f"FROM shoir_pivot_frame GROUP BY {quote(row_col)} ORDER BY {quote(row_col)}"
                ).df()
            finally:
                con.close()
        except Exception:
            pass

    result = pd.pivot_table(
        work,
        index=row_fields,
        columns=column_fields or None,
        values=value_fields,
        aggfunc=agg_map[aggregation],
        dropna=False,
        margins=False,
    )
    result = result.reset_index()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = [
            " · ".join(str(part) for part in col if str(part) not in ("", "None"))
            for col in result.columns.to_list()
        ]
    return result.reset_index(drop=True)

def dependency_graph(
    module: str,
    formulas: Mapping[str, Mapping[str, str]] | None = None,
    query_steps: Sequence[Mapping[str, Any]] | None = None,
    semantic_map: Mapping[str, Any] | None = None,
    source_tables: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def node(node_id: str, label: str, kind: str, detail: str = "") -> None:
        if not any(x["id"] == node_id for x in nodes):
            nodes.append({"id": node_id, "label": label, "kind": kind, "detail": detail})

    def edge(a: str, b: str, relation: str) -> None:
        if a and b and a != b and not any(e["source"] == a and e["target"] == b and e["relation"] == relation for e in edges):
            edges.append({"source": a, "target": b, "relation": relation})

    root = f"module:{module}"
    node(root, module, "Module")
    for source in source_tables or []:
        sid = f"source:{source}"
        node(sid, source, "Dataset")
        edge(sid, root, "feeds")
    for sheet, refs in (formulas or {}).items():
        sid = f"sheet:{sheet}"
        node(sid, sheet, "Sheet")
        edge(root, sid, "contains")
        for cell, expr in refs.items():
            fid = f"formula:{sheet}!{str(cell).upper()}"
            node(fid, f"{sheet}!{str(cell).upper()}", "Formula", str(expr))
            edge(sid, fid, "defines")
            for target in re.findall(r"(?:(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))!)?\$?([A-Za-z]{1,3})\$?\d+", str(expr)):
                target_sheet = target[0] or target[1] or sheet
                ref = target[2]
                rid = f"cell:{target_sheet}!{ref.upper()}"
                node(rid, f"{target_sheet}!{ref.upper()}", "Cell")
                edge(rid, fid, "input")
    for idx, step in enumerate(query_steps or [], 1):
        qid = f"query:{idx}"
        node(qid, f"Query step {idx} · {step.get('type', 'step')}", "Transform", json.dumps(dict(step), default=str))
        edge(root, qid, "transforms")
        if idx > 1:
            edge(f"query:{idx-1}", qid, "precedes")
    for sheet, mapping in (semantic_map or {}).items():
        sid = f"sheet:{sheet}"
        node(sid, sheet, "Sheet")
        for col, role in (mapping or {}).items():
            rid = f"semantic:{sheet}:{col}"
            node(rid, f"{col} → {role}", "Semantic")
            edge(sid, rid, "maps")
    return pd.DataFrame(nodes), pd.DataFrame(edges)

def dependency_figure(nodes: pd.DataFrame, edges: pd.DataFrame, title: str = "Industrial Dependency Graph") -> go.Figure | None:
    if nodes is None or nodes.empty:
        return None
    ids = nodes["id"].astype(str).tolist()
    pos = {node_id: (float(i % 8), float(-(i // 8))) for i, node_id in enumerate(ids)}
    fig = go.Figure()
    for row in edges.to_dict("records") if isinstance(edges, pd.DataFrame) else []:
        a, b = row.get("source"), row.get("target")
        if a not in pos or b not in pos:
            continue
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        fig.add_scatter(x=[x0, x1, None], y=[y0, y1, None], mode="lines", hoverinfo="none", showlegend=False)
    fig.add_scatter(
        x=[pos[x][0] for x in ids],
        y=[pos[x][1] for x in ids],
        text=nodes["label"].astype(str).tolist(),
        mode="markers+text",
        textposition="top center",
        hovertext=nodes.get("detail", pd.Series([""] * len(nodes))).astype(str).tolist(),
        hoverinfo="text",
        marker={"size": 16},
        showlegend=False,
    )
    fig.update_layout(
        title=title,
        height=420,
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return fig

def explain_number(
    module: str,
    source: str,
    frame: pd.DataFrame,
    column: str,
    row_index: int | None = None,
    formula: str = "",
    assumptions: Sequence[str] | None = None,
    uncertainty: str = "Not provided",
    dependencies: Sequence[str] | None = None,
) -> dict[str, Any]:
    df = _safe_frame(frame)
    if column not in df.columns:
        raise KeyError(f"Unknown metric column: {column}")
    value = None
    if row_index is not None and 0 <= int(row_index) < len(df):
        value = df.iloc[int(row_index)][column]
    else:
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        value = float(series.mean()) if not series.empty else (df[column].dropna().iloc[0] if df[column].notna().any() else None)
    try:
        value_display = f"{float(value):,.6g}" if value is not None else "n/a"
    except Exception:
        value_display = str(value)
    return {
        "Metric": column,
        "Value": value_display,
        "Module": module,
        "Source": source,
        "Formula": formula or "Source value / calculated result",
        "Filters": "Current active table selection",
        "Transformations": "Visible query/workbook transformations",
        "Assumptions": "; ".join(str(x) for x in (assumptions or [])) or "None recorded",
        "Timestamp": _now(),
        "Version": "universal-engine-v1",
        "Uncertainty": uncertainty,
        "Dependencies": "; ".join(str(x) for x in (dependencies or [])) or "Not explicitly recorded",
    }

def choose_agent(prompt: str) -> dict[str, Any]:
    text = str(prompt or "").strip().lower()
    scores = {
        name: sum(1 for token in tokens if token in text)
        for name, tokens in AGENT_ROUTES.items()
    }
    ordered = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    winner, score = ordered[0]
    if score == 0:
        winner = "Orchestrator Agent"
    return {
        "agent": winner,
        "confidence": round(score / max(1, len(AGENT_ROUTES[winner]) if winner in AGENT_ROUTES else 1), 2),
        "scores": scores,
        "routing_reason": "Keyword/intent match over the current governed agent catalogue; use the existing Copilot orchestrator for execution.",
    }

def action_gate(requested_level: str, tier: str, approved: bool = False, admin: bool = False) -> dict[str, Any]:
    level = str(requested_level)
    if level not in ENGINE_ACTION_LEVELS:
        return {"allowed": False, "reason": "Unknown action level."}
    tier_low = str(tier).lower()
    if level == "Read":
        return {"allowed": True, "reason": "Read-only inspection is available."}
    if level in {"Analyze", "Simulate", "Recommend"}:
        allowed = any(x in tier_low for x in ("starter", "pro", "professional", "enterprise", "research", "trial"))
        return {"allowed": allowed, "reason": "Tier permits analytical actions." if allowed else "Current tier does not expose this action."}
    if level == "Prepare":
        return {"allowed": ("enterprise" in tier_low or "research" in tier_low), "reason": "Preparation is governed by tier."}
    if level == "Execute":
        return {"allowed": bool(approved and ("enterprise" in tier_low or admin)), "reason": "Execution requires explicit approval and an enterprise/admin context."}
    return {"allowed": bool(admin), "reason": "Administrative actions require an administrator."}

def runtime_choice(df: pd.DataFrame) -> dict[str, Any]:
    frame = _safe_frame(df)
    cells = int(frame.shape[0] * frame.shape[1])
    duckdb_available = False
    pyarrow_available = False
    try:
        import duckdb  # type: ignore
        duckdb_available = True
    except Exception:
        pass
    try:
        import pyarrow  # type: ignore
        pyarrow_available = True
    except Exception:
        pass
    engine = "duckdb" if duckdb_available and cells >= 100_000 else "pandas"
    return {
        "engine": engine,
        "cells": cells,
        "mode": "vectorized/columnar" if engine == "duckdb" else "in-memory",
        "duckdb_available": duckdb_available,
        "pyarrow_available": pyarrow_available,
    }

def black_box_event(module: str, kind: str, payload: Mapping[str, Any], username: str = "unknown") -> dict[str, Any]:
    safe_payload = json.loads(json.dumps(_redact(dict(payload)), default=str))
    canonical = json.dumps(
        {"module": module, "kind": kind, "payload": safe_payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    event = {
        "event_id": "BB-" + hashlib.sha256(canonical).hexdigest()[:16].upper(),
        "timestamp": _now(),
        "module": str(module),
        "kind": str(kind),
        "payload": safe_payload,
        "fingerprint": hashlib.sha256(canonical).hexdigest(),
        "actor": str(username),
    }
    try:
        from shoir_enterprise_layer import record_artifact
        workspace = "default"
        try:
            import streamlit as st
            workspace = str(
                st.session_state.get("shoir_workspace_name")
                or st.session_state.get("workspace")
                or "default"
            )
        except Exception:
            pass
        record_artifact(username, "industrial_black_box_event", event["event_id"], event, workspace)
    except Exception:
        pass
    return event

def record_action(action: str, payload: Mapping[str, Any] | None = None, username: str = "unknown") -> dict[str, Any]:
    event = black_box_event("Universal Engine", action, payload or {}, username)
    try:
        import streamlit as st
        st.session_state.setdefault("shoir_universal_action_log", []).append(event)
        st.session_state["shoir_universal_action_log"] = st.session_state["shoir_universal_action_log"][-100:]
    except Exception:
        pass
    return event

def build_script(actions: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Shoir-IE Universal Engine replay script",
        "# Generated from recorded, user-initiated actions.",
    ]
    for event in actions:
        kind = re.sub(r"[^A-Za-z0-9_]+", "_", str(event.get("kind", "action"))).strip("_").lower() or "action"
        payload = json.dumps(event.get("payload", {}), sort_keys=True, default=str)
        lines.append(f"record_action({kind!r}, {payload})")
    return "\n".join(lines) + "\n"

def trust_snapshot(username: str, tier: str) -> pd.DataFrame:
    rows = [
        {"Control": "Workspace actor", "Status": str(username) or "unknown", "Evidence": "Current authenticated workspace context"},
        {"Control": "Tier", "Status": str(tier), "Evidence": "Current application access tier"},
        {"Control": "Execution gate", "Status": "Approval required", "Evidence": "Universal Engine blocks execute actions without approval"},
        {"Control": "Visualization", "Status": "Universal contract", "Evidence": "Real workspace tables only; deterministic fallback when compatible"},
        {"Control": "Audit", "Status": "Enabled", "Evidence": "Black-box event fingerprint + existing enterprise artifact ledger"},
        {"Control": "Secrets", "Status": "Redacted", "Evidence": "Discovery blocks password/token/secret/payment state keys"},
    ]
    try:
        from durable_account_store import durable_backend_configured
        rows.append({
            "Control": "Durable backend",
            "Status": "Configured" if durable_backend_configured() else "Local/managed backend check",
            "Evidence": "Existing durable account storage service",
        })
    except Exception:
        pass
    return pd.DataFrame(rows)

def _render_ui(module: str, tier: str, username: str) -> None:
    import streamlit as st

    tables = module_tables(module)
    force_open = False
    try:
        force_open = bool(st.session_state.pop("force_universal_engine", False))
    except Exception:
        force_open = False
    with st.expander("🧠 Universal Industrial Engine", expanded=force_open):
        st.caption("One shared engine around every module: Quick Analyze · Pivot · Explain · Dependencies · Agents · Automation · Trust.")
        if tables:
            st.success(f"Universal data contract ready · {len(tables)} data source(s) discovered.")
        else:
            st.info("No module result table is currently populated. Import data or run the native module; the visualization contract remains available.")
        tabs = st.tabs(["⚡ Quick Analyze", "📊 Industrial Pivot", "🔎 Explain & Trace", "🤖 Agents", "⚙ Automation", "🛡 Trust", "🏭 IE Operating System"])
        
        with tabs[0]:
            if not tables:
                st.info("Quick Analyze activates automatically when the current module exposes a safe table.")
            else:
                labels = [x[0] for x in tables]
                choice = st.selectbox("Data source", labels, key="uie_source_" + hashlib.sha1(module.encode()).hexdigest()[:8])
                df = tables[labels.index(choice)][2]
                ready = data_readiness(df)
                runtime = runtime_choice(df)
                a, b, c, d = st.columns(4)
                a.metric("Rows", f"{ready['rows']:,}")
                b.metric("Columns", f"{ready['columns']:,}")
                c.metric("Readiness", f"{ready['score']:.1f}%")
                d.metric("Runtime", runtime["engine"])
                fig = guaranteed_figure(df, f"{module} · Universal Quick Analyze")
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})
                st.dataframe(df.head(500), use_container_width=True, hide_index=True)
                if st.button("📝 Record analysis snapshot", key="uie_record_analysis_" + hashlib.sha1(module.encode()).hexdigest()[:8]):
                    record_action("analysis_snapshot", {"module": module, "source": choice, "readiness": ready}, username)
                    st.success("Analysis snapshot added to the Industrial Black Box.")

        with tabs[1]:
            if not tables:
                st.info("Load a table first.")
            else:
                labels = [x[0] for x in tables]
                choice = st.selectbox("Pivot source", labels, key="uie_pivot_source_" + hashlib.sha1(module.encode()).hexdigest()[:8])
                df = tables[labels.index(choice)][2]
                cols = [str(c) for c in df.columns]
                nums = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
                cats = [str(c) for c in df.columns if str(c) not in nums]
                rows = st.multiselect("Rows", cats, default=cats[:1], key="uie_pivot_rows_" + hashlib.sha1(module.encode()).hexdigest()[:8])
                vals = st.multiselect("Values", nums, default=nums[:1], key="uie_pivot_vals_" + hashlib.sha1(module.encode()).hexdigest()[:8])
                pivot_cols = st.multiselect("Columns (optional)", cats, key="uie_pivot_cols_" + hashlib.sha1(module.encode()).hexdigest()[:8])
                agg = st.selectbox("Aggregation", ["mean", "sum", "count", "min", "max", "median"], key="uie_pivot_agg_" + hashlib.sha1(module.encode()).hexdigest()[:8])
                if rows and vals:
                    try:
                        pvt = pivot_table(df, rows, vals, pivot_cols, agg)
                        st.dataframe(pvt, use_container_width=True, hide_index=True)
                        fig = guaranteed_figure(pvt, f"{module} · Industrial Pivot")
                        if fig is not None:
                            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                        if st.button("💾 Save pivot to workspace", key="uie_pivot_save_" + hashlib.sha1(module.encode()).hexdigest()[:8]):
                            st.session_state["universal_pivot_result_df"] = pvt.copy(deep=True)
                            record_action("pivot_saved", {"module": module, "rows": list(rows), "values": list(vals), "aggregation": agg}, username)
                            st.success("Industrial Pivot result saved to the workspace.")
                    except Exception as exc:
                        st.error(f"Pivot generation failed safely: {exc}")

        with tabs[2]:
            if not tables:
                st.info("Load a table first.")
            else:
                labels = [x[0] for x in tables]
                choice = st.selectbox("Trace source", labels, key="uie_trace_source_" + hashlib.sha1(module.encode()).hexdigest()[:8])
                df = tables[labels.index(choice)][2]
                numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
                metric = st.selectbox("Number / KPI", numeric or [str(df.columns[0])], key="uie_explain_metric_" + hashlib.sha1(module.encode()).hexdigest()[:8])
                explanation = explain_number(module, choice, df, metric)
                st.dataframe(pd.DataFrame([explanation]), use_container_width=True, hide_index=True)
                formulas = {}
                try:
                    import streamlit as st
                    formulas = st.session_state.get("industrial_workbook_formulas", {}) or {}
                except Exception:
                    pass
                sem = {}
                try:
                    sem = st.session_state.get("industrial_workbook_semantic_map", {}) or {}
                except Exception:
                    pass
                nodes, edges = dependency_graph(module, formulas=formulas, semantic_map=sem, source_tables=[choice])
                fig = dependency_figure(nodes, edges, f"{module} · Explainable dependency graph")
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                st.caption("Every explanation is explicitly labelled with source, assumptions, uncertainty and dependencies; absent evidence is shown rather than invented.")

        with tabs[3]:
            prompt = st.text_area("Engineering goal", placeholder="Example: Find why throughput fell and forecast tomorrow.", key="uie_agent_prompt")
            if prompt.strip():
                route = choose_agent(prompt)
                r1, r2 = st.columns(2)
                r1.metric("Routed agent", route["agent"])
                r2.metric("Routing confidence", f"{100 * route['confidence']:.0f}%")
                st.dataframe(pd.DataFrame([{"Agent": k, "Keyword hits": v} for k, v in route["scores"].items()]), use_container_width=True, hide_index=True)
                if st.button("🧭 Record agent route", key="uie_agent_record"):
                    record_action("agent_route", route, username)
                    st.success("Route recorded. Execution remains in the existing governed Copilot/orchestration layer.")

        with tabs[4]:
            actions = st.session_state.get("shoir_universal_action_log", [])
            st.write(f"Recorded actions: **{len(actions)}**")
            if actions:
                st.dataframe(pd.DataFrame(actions).drop(columns=["payload"], errors="ignore"), use_container_width=True, hide_index=True)
                st.download_button(
                    "📜 Export replay script",
                    data=build_script(actions).encode("utf-8"),
                    file_name="shoir_ie_universal_replay.py",
                    mime="text/x-python",
                    use_container_width=True,
                    key="uie_replay_export",
                )
            action = st.selectbox("Permission level", ENGINE_ACTION_LEVELS, key="uie_action_level")
            approved = st.checkbox("Explicit approval recorded for this action", key="uie_action_approval")
            admin = bool(st.session_state.get("is_admin") or st.session_state.get("admin") or st.session_state.get("is_workspace_admin"))
            gate = action_gate(action, tier, approved=approved, admin=admin)
            st.metric("Action gate", "ALLOWED" if gate["allowed"] else "BLOCKED")
            st.caption(gate["reason"])
            if st.button("Record governed action", key="uie_record_governed_action"):
                if gate["allowed"]:
                    record_action("governed_" + action.lower(), {"module": module, "approved": approved}, username)
                    st.success("Governed action recorded; no external operational execution is performed by this surface.")
                else:
                    st.warning("Action was not recorded because its governance gate is not satisfied.")

        with tabs[5]:
            st.dataframe(trust_snapshot(username, tier), use_container_width=True, hide_index=True)
            st.caption("Trust Center complements the existing enterprise security, audit, connector and persistence layers; it is intentionally read-only.")

        with tabs[6]:
            try:
                from shoir_engineering_os import render_operating_system_layer
                render_operating_system_layer(module, username)
            except Exception as exc:
                st.warning("Industrial Engineering OS layer is temporarily unavailable; native and universal analysis remain available.")
                with st.expander("IE Operating System diagnostic", expanded=False):
                    st.code(f"{type(exc).__name__}: {exc}")

def render_universal_engine_surface(module: str, tier: str = "Starter Tier", username: str = "unknown") -> None:
    _render_ui(str(module), str(tier), str(username))

def postflight_contract(module: str, username: str = "unknown", preferred_key: str | None = None) -> dict[str, Any]:
    """Create a machine-readable universal contract after a module run."""
    tables = module_tables(module, preferred_key=preferred_key)
    source = tables[0][1] if tables else ""
    frame = tables[0][2] if tables else pd.DataFrame()
    validation = data_readiness(frame)
    fig = guaranteed_figure(frame, f"{module} · Universal") if not frame.empty else None
    contract = {
        "module": module,
        "source_key": source,
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "readiness": validation,
        "graph_available": fig is not None,
    }
    signature = hashlib.sha256(json.dumps(contract, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    try:
        import streamlit as st
        prior = st.session_state.get("shoir_universal_postflight_signature")
        event_id = st.session_state.get("shoir_universal_postflight_event_id")
        if prior != signature:
            event = black_box_event(module, "module_postflight", contract, username)
            event_id = event["event_id"]
            st.session_state["shoir_universal_postflight_signature"] = signature
            st.session_state["shoir_universal_postflight_event_id"] = event_id
    except Exception:
        event_id = None
    contract["event_id"] = event_id
    contract["signature"] = signature
    return contract

def universal_health_report(module: str) -> dict[str, Any]:
    tables = module_tables(module)
    if not tables:
        return {"module": module, "status": "Ready · awaiting data", "tables": 0, "graphs": 0}
    graph_count = 0
    for _, _, frame in tables:
        try:
            if guaranteed_figure(frame, module) is not None:
                graph_count += 1
        except Exception:
            continue
    return {
        "module": module,
        "status": "Verified" if graph_count == len(tables) else "Gap",
        "tables": len(tables),
        "graphs": graph_count,
    }
