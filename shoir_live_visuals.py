"""Universal live visualization studio for Shoir-IE modules.

The studio is intentionally data-driven: it never invents observations. It
discovers editable/result tables already present in the current Streamlit
workspace and lets the user generate interactive Plotly views from them.
"""

from __future__ import annotations

import io
import re
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


_MODULE_KEYS = {
    "Engineering Validation Center": ["validation_df", "validation_result"],
    "Industrial Data Model & Digital Thread": ["thread_df", "thread_rel"],
    "Advanced Planning & Scheduling": ["aps_demand", "aps_bom", "aps_orders", "aps_schedule_result"],
    "Manufacturing Execution System": ["mes_wo_df", "mes_events_df", "mes_oee_df", "mes_oee_result"],
    "Quality Engineering & Reliability": ["quality_df", "quality_spc_result", "quality_limits_result", "msa_df", "anova_df", "fmea_df", "fmea_result"],
    "Industrial Simulation Lab": ["sim_des_result", "sim_agent_result", "sd"],
    "3D Factory Designer": ["factory3d_df", "factory3d_dist_result"],
    "Industrial Connectivity Hub": ["conn_df"],
    "Multi-Objective Optimization": ["multiobj_df", "multiobj_result", "pareto"],
    "Robust & Resilient Optimization": ["robust_df", "robust_result"],
    "Engineering Model Registry": ["model_registry_df"],
    "Experiment Lab": ["experiment_df", "experiment_results"],
    "Industrial Control Center": ["control_center_metrics"],
    "Engineering Decision Center": ["decision_metrics_df"],
    "Industrial Data Platform": ["data_platform_latest_df"],
    "Capital Investment & Engineering Economics": ["capex_df", "capex_result"],
    "Workforce Engineering": ["work_elements", "balance_result", "skills_df"],
    "Industrial Sustainability & LCA": ["sustain_df", "sustain_result"],
    "Benchmarking & Engineering Standards": ["benchmark_actual", "benchmark_targets", "benchmark_result"],
    "Live Industrial Digital Twin": ["twin_tel"],
    "Advanced ML Demand Forecasting": ["forecast_df", "forecast_result"],
    "Scenario Versioning & Comparison": ["scenario_df"],
    "Team Workspaces & RBAC": ["workspace_members_df"],
    "Executive Report Center": ["exec_report_df"],
    "Predictive Maintenance Digital Twin": ["maint_df", "maint_result"],
    "Localization & Multi-Currency": ["currency_df", "currency_result", "trade_rules_df"],
    "Enterprise Security & Governance": ["security_roles"],
    "Control Tower": ["control_tower_metrics", "control_tower_disruption_df"],
    "Cryptographic Ledger": ["ledger_history"],
    "Carbon Accounting": ["carbon_latest_df"],
}


def _as_frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    if isinstance(value, list):
        if not value:
            return pd.DataFrame()
        if all(isinstance(x, dict) for x in value):
            return pd.DataFrame(value)
        return pd.DataFrame({"Value": value})
    if isinstance(value, dict):
        # Results with scalar values become a useful one-row KPI table.
        flat = {}
        for k, v in value.items():
            if isinstance(v, (str, int, float, bool, np.integer, np.floating)) and not isinstance(v, bool):
                flat[str(k)] = v
        return pd.DataFrame([flat]) if flat else pd.DataFrame()
    return pd.DataFrame()


def _is_candidate_key(key: str) -> bool:
    k = str(key).lower()
    blocked = (
        "password", "token", "secret", "otp", "payment", "uploader",
        "copilot_messages", "chat", "signature", "_snapshot",
    )
    if any(x in k for x in blocked):
        return False
    return not k.startswith(("_", "signin_", "reg_"))


def discover_visual_tables(module: str) -> list[tuple[str, str, pd.DataFrame]]:
    """Discover safe, non-secret tables relevant to the active module."""
    result: list[tuple[str, str, pd.DataFrame]] = []
    seen: set[str] = set()

    for key in _MODULE_KEYS.get(module, []):
        if key in st.session_state:
            df = _as_frame(st.session_state.get(key))
            if not df.empty and key not in seen:
                result.append((key.replace("_", " ").title(), key, df))
                seen.add(key)

    # Prefer keys whose names overlap the module name, so a newly added module
    # benefits automatically without another hard-coded registry entry.
    words = [w for w in re.findall(r"[a-z0-9]+", module.lower()) if len(w) >= 4]
    for key, value in list(st.session_state.items()):
        if key in seen or not _is_candidate_key(str(key)):
            continue
        if not isinstance(value, (pd.DataFrame, list, dict)):
            continue
        if words and not any(w in str(key).lower() for w in words):
            continue
        df = _as_frame(value)
        if not df.empty:
            result.append((str(key).replace("_", " ").title(), str(key), df))
            seen.add(str(key))

    # Finally, allow safe workspace tables as a fallback. This prevents a new
    # module from shipping without visualization solely because its state key
    # was not registered yet.
    if not result:
        for key, value in list(st.session_state.items()):
            if key in seen or not _is_candidate_key(str(key)):
                continue
            if not isinstance(value, (pd.DataFrame, list, dict)):
                continue
            df = _as_frame(value)
            if not df.empty and len(df.columns) >= 1:
                result.append((str(key).replace("_", " ").title(), str(key), df))
                seen.add(str(key))
            if len(result) >= 8:
                break

    return result[:12]


def _coerce_datetime_columns(df: pd.DataFrame) -> list[str]:
    candidates: list[str] = []
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            candidates.append(str(col))
            continue
        if s.dtype == object:
            sample = s.dropna().astype(str).head(30)
            if len(sample) >= 5:
                parsed = pd.to_datetime(sample, errors="coerce")
                if float(parsed.notna().mean()) >= 0.8:
                    candidates.append(str(col))
    return candidates


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _categorical_columns(df: pd.DataFrame) -> list[str]:
    return [
        str(c) for c in df.columns
        if not pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_datetime64_any_dtype(df[c])
    ]


def _prepare(df: pd.DataFrame, x: str | None, y: str | None, aggregation: str, filter_col: str | None, filter_value: str | None) -> pd.DataFrame:
    work = df.copy()

    if filter_col and filter_value and filter_col in work.columns and filter_value != "All":
        work = work[work[filter_col].astype(str) == filter_value]

    needed = [c for c in (x, y) if c and c in work.columns]
    if needed:
        work = work.dropna(subset=needed)

    if x and y and aggregation != "Raw" and x in work.columns and y in work.columns:
        numeric_y = pd.to_numeric(work[y], errors="coerce")
        work = work.assign(__chart_y=numeric_y).dropna(subset=["__chart_y"])
        grouped = work.groupby(x, dropna=False, as_index=False)["__chart_y"]
        if aggregation == "Mean":
            work = grouped.mean().rename(columns={"__chart_y": y})
        elif aggregation == "Median":
            work = grouped.median().rename(columns={"__chart_y": y})
        elif aggregation == "Sum":
            work = grouped.sum().rename(columns={"__chart_y": y})
        elif aggregation == "Count":
            work = work.groupby(x, dropna=False, as_index=False).size().rename(columns={"size": y})

    return work


def _suggest_chart(df: pd.DataFrame, x: str | None, y: str | None) -> str:
    if y and x:
        if x in _coerce_datetime_columns(df):
            return "Line"
        if pd.api.types.is_numeric_dtype(df[x]):
            return "Scatter"
        return "Bar"
    if y:
        return "Histogram"
    if x:
        return "Bar"
    return "Heatmap"


def _make_figure(df: pd.DataFrame, chart: str, x: str | None, y: str | None, z: str | None, title: str) -> go.Figure | None:
    if df.empty:
        return None

    if chart == "Heatmap":
        nums = _numeric_columns(df)
        if len(nums) < 2:
            return None
        corr = df[nums].corr(numeric_only=True)
        fig = px.imshow(corr, text_auto=".2f", aspect="auto", title=title or "Correlation Heatmap")
    elif chart == "Histogram" and y:
        fig = px.histogram(df, x=y, nbins=30, title=title or f"Distribution · {y}")
    elif chart == "Box" and y:
        fig = px.box(df, y=y, points="outliers", title=title or f"Distribution · {y}")
    elif chart == "Pie" and x and y:
        fig = px.pie(df, names=x, values=y, title=title or f"Share of {y}")
    elif chart == "Pareto" and y:
        d = df[[y]].dropna().copy()
        if x and x in df.columns:
            d[x] = df.loc[d.index, x]
            d = d.groupby(x, as_index=False)[y].sum().sort_values(y, ascending=False)
            d["Cumulative %"] = d[y].cumsum() / d[y].sum() * 100
            fig = go.Figure()
            fig.add_bar(x=d[x].astype(str), y=d[y], name=y)
            fig.add_scatter(x=d[x].astype(str), y=d["Cumulative %"], name="Cumulative %", yaxis="y2", mode="lines+markers")
            fig.update_layout(title=title or f"Pareto · {y}", yaxis2=dict(title="Cumulative %", overlaying="y", side="right", range=[0,100]))
        else:
            d["Cumulative %"] = d[y].cumsum() / d[y].sum() * 100
            fig = go.Figure()
            fig.add_bar(x=list(range(1, len(d)+1)), y=d[y], name=y)
            fig.add_scatter(x=list(range(1, len(d)+1)), y=d["Cumulative %"], name="Cumulative %", yaxis="y2", mode="lines+markers")
            fig.update_layout(title=title or f"Pareto · {y}", yaxis2=dict(title="Cumulative %", overlaying="y", side="right", range=[0,100]))
    elif chart == "3D Scatter" and x and y and z:
        fig = px.scatter_3d(df, x=x, y=y, z=z, title=title or "3D Engineering View")
    elif not x and y:
        fig = px.bar(df, y=y, title=title or y)
    elif chart == "Line":
        fig = px.line(df, x=x, y=y, markers=True, title=title or f"{y} over {x}")
    elif chart == "Area":
        fig = px.area(df, x=x, y=y, title=title or f"{y} over {x}")
    elif chart == "Scatter":
        fig = px.scatter(df, x=x, y=y, title=title or f"{y} vs {x}", trendline="ols" if len(df) >= 8 and pd.api.types.is_numeric_dtype(df[x]) else None)
    else:
        fig = px.bar(df, x=x, y=y, title=title or f"{y} by {x}")

    fig.update_layout(
        height=430,
        margin=dict(l=12, r=18, t=55, b=12),
        template="plotly_white",
        hovermode="x unified" if chart in {"Line", "Area"} else "closest",
        legend_title_text="",
    )
    return fig


def render_live_visualization_studio(module: str, *, expanded: bool = False) -> None:
    """Render the live chart studio beneath an active module."""
    tables = discover_visual_tables(module)
    with st.expander("📊 Live Engineering Visualization Studio", expanded=expanded):
        st.caption("Charts use the current module/workspace data. Edit a table, change the controls, and the visualization updates on the next Streamlit rerun.")
        if not tables:
            st.info("Add or import a numeric engineering table in this module to generate a live graph.")
            return

        labels = [label for label, _, _ in tables]
        table_label = st.selectbox("Data source", labels, key=f"liveviz_source_{hash(module) & 0xFFFF:04x}")
        df = tables[labels.index(table_label)][2].copy()

        # Avoid accidentally visualizing secrets or enormous payloads.
        if len(df) > 10000:
            df = df.head(10000).copy()

        nums = _numeric_columns(df)
        cats = _categorical_columns(df)
        dates = _coerce_datetime_columns(df)
        cols = [str(c) for c in df.columns]

        if not nums and len(cols) < 2:
            st.info("This table needs at least one numeric measure and a useful category/time field for a graph.")
            return

        default_y = nums[0] if nums else None
        x_options = ["(none)"] + cols
        default_x = next((c for c in dates if c != default_y), next((c for c in cats if c != default_y), "(none)"))

        c1, c2, c3 = st.columns([1.25, 1.25, 1])
        with c1:
            x_choice = st.selectbox("X-axis", x_options, index=x_options.index(default_x), key=f"liveviz_x_{hash(module) & 0xFFFF:04x}")
        with c2:
            y_choice = st.selectbox("Y-axis", ["(none)"] + nums, index=1 if default_y else 0, key=f"liveviz_y_{hash(module) & 0xFFFF:04x}")
        with c3:
            z_choice = st.selectbox("3D Z-axis", ["(none)"] + nums, index=0, key=f"liveviz_z_{hash(module) & 0xFFFF:04x}")

        x = None if x_choice == "(none)" else x_choice
        y = None if y_choice == "(none)" else y_choice
        z = None if z_choice == "(none)" else z_choice

        c4, c5, c6 = st.columns([1.2, 1.2, 1.4])
        with c4:
            suggestions = ["Auto", "Line", "Bar", "Area", "Scatter", "Histogram", "Box", "Pie", "Pareto", "Heatmap", "3D Scatter"]
            chart_choice = st.selectbox("Visualization", suggestions, key=f"liveviz_chart_{hash(module) & 0xFFFF:04x}")
        with c5:
            aggregation = st.selectbox("Aggregation", ["Raw", "Mean", "Median", "Sum", "Count"], key=f"liveviz_agg_{hash(module) & 0xFFFF:04x}")
        with c6:
            title = st.text_input("Chart title", value=f"{module} · {y or 'relationships'}", key=f"liveviz_title_{hash(module) & 0xFFFF:04x}")

        filter_col = st.selectbox("Optional filter", ["(none)"] + cols, key=f"liveviz_filtercol_{hash(module) & 0xFFFF:04x}")
        filter_value = "All"
        if filter_col != "(none)":
            values = sorted(df[filter_col].dropna().astype(str).unique().tolist())
            filter_value = st.selectbox("Filter value", ["All"] + values[:500], key=f"liveviz_filterval_{hash(module) & 0xFFFF:04x}")

        actual_chart = _suggest_chart(df, x, y) if chart_choice == "Auto" else chart_choice
        prepared = _prepare(df, x, y, aggregation, None if filter_col == "(none)" else filter_col, filter_value)
        fig = _make_figure(prepared, actual_chart, x, y, z, title)

        if fig is None:
            st.warning("This visualization needs compatible columns. Try a numeric Y-axis, a category/date X-axis, or choose Heatmap.")
            return

        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Rows visualized", f"{len(prepared):,}")
        q2.metric("Variables", f"{len(prepared.columns):,}")
        q3.metric("Numeric measures", f"{len(nums):,}")
        q4.metric("View", actual_chart)

        st.plotly_chart(fig, use_container_width=True, config={
            "displayModeBar": True,
            "displaylogo": False,
            "scrollZoom": True,
            "responsive": True,
        })

        left, right = st.columns(2)
        with left:
            try:
                html_bytes = fig.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8")
                st.download_button(
                    "📥 Download interactive chart (HTML)",
                    data=html_bytes,
                    file_name=f"shoir_ie_{re.sub(r'[^A-Za-z0-9]+','_',module).lower()}_chart.html",
                    mime="text/html",
                    use_container_width=True,
                    key=f"liveviz_html_{hash(module) & 0xFFFF:04x}",
                )
            except Exception as exc:
                st.caption(f"Interactive export unavailable: {exc}")
        with right:
            st.download_button(
                "📄 Download chart data (CSV)",
                data=prepared.to_csv(index=False).encode("utf-8"),
                file_name=f"shoir_ie_{re.sub(r'[^A-Za-z0-9]+','_',module).lower()}_chart_data.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"liveviz_csv_{hash(module) & 0xFFFF:04x}",
            )
