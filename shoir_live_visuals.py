"""Universal live visualization studio for Shoir-IE modules.

The studio is intentionally data-driven: it never invents observations. It
discovers editable/result tables already present in the current Streamlit
workspace and lets the user generate interactive Plotly views from them.
"""

from __future__ import annotations

import io
import hashlib
import json
import re
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


_MODULE_KEYS = {
    "Engineering Validation Center": ["validation_df", "validation_result"],
    "Industrial Operating System": ["os_compare_result", "os_process_result", "os_drift_result", "os_verify_result"],
    "Global Project & Digital Thread": ["global_thread_nodes", "global_thread_edges", "global_thread_project"],
    "Advanced Engineering Copilot": ["copilot_orchestrator_run", "copilot_orchestrator_figure_json", "copilot_staged_decision_id", "copilot_orchestrator_export", "copilot_clean_audit"],
    "MILP Solvers": ["milp_result_df", "milp_summary_df", "milp_allocation_flow_df"],
    "Industrial Data Model & Digital Thread": ["thread_df", "thread_rel"],
    "Advanced Planning & Scheduling": ["aps_demand", "aps_bom", "aps_orders", "aps_schedule_result"],
    "Manufacturing Execution System": ["mes_wo_df", "mes_events_df", "mes_oee_df", "mes_oee_result"],
    "Quality Engineering & Reliability": ["quality_df", "quality_spc_result", "quality_limits_result", "msa_df", "anova_df", "fmea_df", "fmea_result"],
    "Industrial Simulation Lab": ["sim_des_result", "sim_agent_result", "sd"],
    "3D Factory Designer": ["factory3d_df", "factory3d_dist_result"],
    "Multi-Objective Optimization": ["multiobj_df", "multiobj_result", "pareto", "optimization_pareto_df", "optimization_result_df"],
    "Robust & Resilient Optimization": ["robust_df", "robust_result", "robust_result_df"],
    "Experiment Lab": ["experiment_df", "experiment_results", "experiment_doe_design", "experiment_factorial_effects", "experiment_factorial_summary", "experiment_mc_results", "experiment_mc_result_summary", "experiment_bootstrap_results", "experiment_bootstrap_summary", "experiment_replication_summary", "experiment_sensitivity_results"],
    "Engineering Decision Center": ["decision_metrics_df", "decision_alternatives_df", "decision_kpi_df", "decision_verification_df", "decision_outcomes_df"],
    "Industrial Data Platform": ["data_platform_latest_df"],
    "Capital Investment & Engineering Economics": ["capex_df", "capex_result"],
    "Workforce Engineering": ["work_elements", "balance_result", "skills_df"],
    "Industrial Sustainability & LCA": ["sustain_df", "sustain_result"],
    "Benchmarking & Engineering Standards": ["benchmark_actual", "benchmark_targets", "benchmark_result", "benchmark_roi_df"],
    "Advanced ML Demand Forecasting": ["forecast_df", "forecast_result", "forecast_metrics"],
    "Scenario Versioning & Comparison": ["scenario_df"],
    "Predictive Maintenance Digital Twin": ["maint_df", "maint_result"],
    "Localization & Multi-Currency": ["currency_df", "currency_result", "trade_rules_df"],
    "IoT Digital Twin": ["node_mesh_df", "sensor_stream", "dt_workstations", "twin_tel", "twin_whatif_result", "enterprise_twin_anomalies_df", "enterprise_artifact_ledger"],
    "Live Industrial Digital Twin": ["twin_tel", "twin_whatif_result", "enterprise_twin_anomalies_df", "enterprise_artifact_ledger"],
    "Industrial Connectivity Hub": ["conn_df", "connector_profiles", "erp_connectors", "enterprise_connector_health_df", "connectivity_health_df", "connector_sample_df"],
    "Industrial Control Center": ["control_center_metrics", "enterprise_control_tower_health_df"],
    "Enterprise Integration & Collaboration": ["erp_connectors", "workspace_users", "audit_report_history", "enterprise_connector_health_df", "enterprise_collaboration_assignments", "enterprise_artifact_ledger"],
    "Persistence": ["enterprise_artifact_ledger"],
    "Enterprise Security & Governance": ["security_roles", "audit_governance_ledger", "enterprise_artifact_ledger", "enterprise_security_posture_df", "security_file_scan_df"],
    "Team Workspaces & RBAC": ["workspace_members_df", "workspace_users", "enterprise_collaboration_assignments", "enterprise_artifact_ledger"],
    "Engineering Model Registry": ["model_registry_df", "enterprise_artifact_ledger"],
    "Research Workspace": ["enterprise_research_runs_df", "enterprise_research_decisions_df"],
    "Experiment Engine": ["experiment_engine_design_df", "experiment_engine_effects_df", "experiment_engine_fitted_df", "experiment_engine_mc_samples", "experiment_engine_bootstrap_df", "experiment_engine_sensitivity_df", "experiment_engine_replication_df", "enterprise_artifact_ledger"],
    "Executive Report Center": ["exec_report_df", "enterprise_artifact_ledger"],
    "Jobs System": ["enterprise_job_history_df"],
    "Knowledge Layer": ["knowledge_documents"],
    "Human Factors & Ergonomics (NIOSH)": ["ergonomic_tasks", "time_studies", "mtm_library"],
    "Geospatial Network Designer": ["supply_nodes", "fleet_vehicles", "enterprise_artifact_ledger"],
    "Digital Twin & Discrete-Event Simulation": ["dt_workstations","event_logs","sim_des_result","sim_agent_result","sd","enterprise_artifact_ledger"],
    "Digital Twin & DES": ["dt_workstations","event_logs","sim_des_result","sim_agent_result","sd","enterprise_artifact_ledger"],
    "Predictive Maintenance Hub": ["maintenance_assets","maintenance_telemetry","enterprise_twin_anomalies_df","enterprise_artifact_ledger"],
    "Engineering Economics & Finance": ["economic_summary","df_economic_summary","df_amort","capex_result","enterprise_artifact_ledger"],
    "Green IE & Sustainability": ["lca_materials","carbon_latest_df","sustain_result","enterprise_artifact_ledger"],
    "Control Tower": ["control_tower_metrics", "control_tower_disruption_df", "enterprise_control_tower_health_df", "enterprise_artifact_ledger"],
    "Cryptographic Ledger": ["ledger_history"],
    "Carbon Accounting": ["carbon_latest_df"],
    "Industrial Workbook": ["industrial_workbook_current_df", "industrial_workbook_query_result_df", "industrial_workbook_analysis_df", "industrial_workbook_formula_audit_df", "industrial_workbook_semantic_map_df"],
}

# Conflict-resolution registry: richer enterprise result aliases are additive.
def _extend_module_keys(module_name: str, *keys: str) -> None:
    current = list(_MODULE_KEYS.get(module_name, []))
    for key in keys:
        if key not in current:
            current.append(key)
    _MODULE_KEYS[module_name] = current

_extend_module_keys("Industrial Simulation Lab", "job_history_df", "realtime_monitoring_df")
_extend_module_keys("Digital Twin & Discrete-Event Simulation", "agv_fleet", "des_queues", "iot_sensors", "kanban_buffers", "reliability_data", "digital_twin_state_snapshot", "digital_twin_replay_df")
_extend_module_keys("IoT Digital Twin", "telemetry_events")
_extend_module_keys("Industrial Connectivity Hub", "connectivity_health_df")
_extend_module_keys("AI Copilot", "knowledge_registry_df")
_extend_module_keys("Enterprise Integration & Collaboration", "collaboration_roster_df", "connectivity_health_df", "enterprise_security_posture_df", "collaboration_assignment_df")
_extend_module_keys("Engineering Model Registry", "model_reproducibility_catalog", "model_registry_governance_df")
_extend_module_keys("Experiment Lab", "research_reproducibility_df")
_extend_module_keys("Experiment Engine", "research_reproducibility_df")
_extend_module_keys("Research Workspace", "forecast_universal_result")
_extend_module_keys("Industrial Control Center", "control_tower_health_df")
_extend_module_keys("Engineering Control Tower", "control_tower_unified_health_df")
_extend_module_keys("Capital Investment & Engineering Economics", "fin_cash_flows", "mc_results", "engineering_economics_tco_df", "engineering_economics_cashflow_df")
_extend_module_keys("Workforce Engineering", "human_factors_workforce_df")
_extend_module_keys("Human Factors & Ergonomics (NIOSH)", "mtm_slots", "human_factors_metrics_df", "human_factors_workforce_df")
_extend_module_keys("Industrial Sustainability & LCA", "carbon_sources", "energy_units", "lca_materials", "sustainability_decision_bridge_df", "sustainability_decision_df")
_extend_module_keys("Live Industrial Digital Twin", "digital_twin_state_snapshot", "digital_twin_state_df", "digital_twin_scenarios_df", "digital_twin_replay_df", "digital_twin_replay_result_df")
_extend_module_keys("Advanced ML Demand Forecasting", "forecast_universal_df", "forecast_universal_result")
_extend_module_keys("Geospatial Network Designer", "demand_markets", "geospatial_network_routes_df", "geospatial_intelligence_df")
_extend_module_keys("Team Workspaces & RBAC", "collaboration_assignment_df", "enterprise_collaboration_assignments")
_extend_module_keys("Executive Report Center", "report_provenance_df")
_extend_module_keys("Predictive Maintenance Digital Twin", "digital_twin_state_df", "digital_twin_replay_result_df")
_extend_module_keys("Enterprise Security & Governance", "enterprise_security_posture_df", "enterprise_security_roles_df", "security_scan_df", "security_file_scan_df")
_extend_module_keys("Persistence", "enterprise_security_posture_df", "shoir_artifact_catalog", "job_history_df", "cloud_persistence_health_df")
_extend_module_keys("Green IE & Sustainability", "lca_materials", "carbon_latest_df", "sustain_result")
_extend_module_keys("Control Tower", "control_tower_unified_health_df")



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
        # Many orchestration surfaces store the actual result table inside a
        # run envelope. Prefer that nested evidence over metadata so the
        # universal visualization engine can render it directly.
        for nested_key in ("result", "results", "data", "frame", "table"):
            nested = value.get(nested_key)
            if isinstance(nested, (pd.DataFrame, list, dict)):
                nested_frame = _as_frame(nested)
                if not nested_frame.empty:
                    return nested_frame
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


def discover_visual_tables(module: str, preferred_key: str | None = None, *, allow_global_fallback: bool = True) -> list[tuple[str, str, pd.DataFrame]]:
    """Discover safe, non-secret tables relevant to the active module.

    preferred_key is placed first when it contains a usable DataFrame. This
    lets Universal Module Parity focus the same chart studio on its canonical
    module dataset while retaining the module-specific result tables.
    """
    result: list[tuple[str, str, pd.DataFrame]] = []
    seen: set[str] = set()

    if preferred_key and preferred_key in st.session_state:
        preferred_df = _as_frame(st.session_state.get(preferred_key))
        if not preferred_df.empty:
            result.append((str(preferred_key).replace("_", " ").title(), preferred_key, preferred_df))
            seen.add(preferred_key)

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

    # Optional final fallback for interactive use. Audits disable this path
    # so one module can never inherit another module's unrelated table.
    if allow_global_fallback and not result:
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


def _find_col(df: pd.DataFrame, tokens: tuple[str, ...]) -> str | None:
    for col in df.columns:
        name = str(col).lower().replace("_", " ").replace("-", " ")
        if any(token in name for token in tokens):
            return str(col)
    return None


def _auto_chart_choice(df: pd.DataFrame) -> str:
    """Choose a useful chart from structural signals, not invented semantics."""
    cols = [str(c) for c in df.columns]
    nums = _numeric_columns(df)
    categorical = _categorical_columns(df)
    dates = _coerce_datetime_columns(df)
    source = _find_col(df, ("source", "from", "origin", "customer", "facility", "warehouse"))
    target = _find_col(df, ("target", "to", "destination", "warehouse", "facility", "customer"))
    value = _find_col(df, ("value", "volume", "flow", "quantity", "qty"))
    start = _find_col(df, ("start", "begin", "planned start"))
    finish = _find_col(df, ("finish", "end", "completion", "planned finish"))
    delta = _find_col(df, ("delta", "change", "impact", "variance"))
    baseline = _find_col(df, ("baseline", "base"))
    effect = _find_col(df, ("effect", "coefficient"))
    term = _find_col(df, ("term", "factor", "driver"))
    target_metric = _find_col(df, ("target", "goal"))
    actual_metric = _find_col(df, ("actual", "observed"))
    propagated = _find_col(df, ("propagated kpi", "bootstrap statistic", "bootstrap effect"))
    sensitivity = _find_col(df, ("sensitivity", "elasticity", "importance"))
    defect_metric = _find_col(df, ("defect", "failure", "rpn", "risk priority"))

    ci_low = _find_col(df, ("ci low", "lower 95", "lower ci"))
    ci_high = _find_col(df, ("ci high", "upper 95", "upper ci"))
    if source and target and value:
        return "Sankey"
    if start and finish:
        return "Gantt"
    if delta and baseline:
        return "Waterfall"
    if propagated:
        return "Distribution"
    if target_metric and actual_metric:
        return "Bar"
    if sensitivity:
        return "Sensitivity Plot"
    if effect and term:
        return "Bar"
    if ci_low and ci_high and term:
        return "Bar"
    if defect_metric:
        return "Pareto"
    if len(nums) >= 3:
        return "3D Scatter"
    if len(nums) >= 2 and dates:
        return "Line"
    if len(nums) >= 2:
        return "Sensitivity Plot"
    if nums and categorical:
        return "Bar"
    if nums:
        return "Distribution"
    if categorical:
        return "Categorical Distribution"
    return "Bar"


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
        return "Categorical Distribution" if (x in _categorical_columns(df) and not y) else "Bar"
    return _auto_chart_choice(df)


def _make_figure(df: pd.DataFrame, chart: str, x: str | None, y: str | None, z: str | None, title: str) -> go.Figure | None:
    if df.empty:
        return None

    numeric = _numeric_columns(df)
    categorical = _categorical_columns(df)

    if chart in {"Heatmap", "Correlation Heatmap"}:
        if len(numeric) < 2:
            return None
        corr = df[numeric].corr(numeric_only=True)
        return px.imshow(corr, text_auto=".2f", aspect="auto", title=title or "Correlation Heatmap")

    if chart in {"Categorical Distribution", "Count by Category"}:
        category = x if x in df.columns else (categorical[0] if categorical else None)
        if category is None:
            return None
        work = df[[category]].copy()
        work[category] = work[category].astype("string").fillna("(Missing)")
        counts = work[category].value_counts(dropna=False).rename_axis(category).reset_index(name="Count").head(50)
        return px.bar(counts, x=category, y="Count", text="Count", title=title or f"Count by {category}")

    if chart in {"Distribution", "Histogram"}:
        metric = y or (numeric[0] if numeric else None)
        if metric is None:
            return None
        return px.histogram(df, x=metric, nbins=30, marginal="box", title=title or f"Distribution · {metric}")

    if chart == "Box":
        metric = y or (numeric[0] if numeric else None)
        if metric is None:
            return None
        return px.box(df, y=metric, points="outliers", title=title or f"Distribution · {metric}")

    if chart == "Control Chart" or chart == "SPC":
        metric = y or (numeric[0] if numeric else None)
        if metric is None:
            return None
        work = df.copy()
        if x and x in work.columns:
            work = work[[x, metric]].copy()
        else:
            work = work[[metric]].copy()
            work["__observation"] = np.arange(1, len(work) + 1)
            x = "__observation"
        work[metric] = pd.to_numeric(work[metric], errors="coerce")
        work = work.dropna(subset=[metric])
        if work.empty:
            return None
        x_values = work[x]
        values = work[metric]
        mean = float(values.mean())
        sigma = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        ucl, lcl = mean + 3 * sigma, mean - 3 * sigma
        fig = go.Figure()
        fig.add_scatter(x=x_values, y=values, mode="lines+markers", name=metric)
        fig.add_scatter(x=x_values, y=[mean] * len(values), mode="lines", name="Center line")
        fig.add_scatter(x=x_values, y=[ucl] * len(values), mode="lines", name="UCL")
        fig.add_scatter(x=x_values, y=[lcl] * len(values), mode="lines", name="LCL")
        fig.update_layout(title=title or f"SPC Control Chart · {metric}", xaxis_title=x or "Observation", yaxis_title=metric)
        return fig

    if chart == "Pareto":
        metric = y or (numeric[0] if numeric else None)
        if metric is None:
            return None
        category = x or (categorical[0] if categorical else None)
        d = df.copy()
        if category and category in d.columns:
            d[metric] = pd.to_numeric(d[metric], errors="coerce")
            d = d.dropna(subset=[metric]).groupby(category, as_index=False)[metric].sum().sort_values(metric, ascending=False)
            d["Cumulative %"] = d[metric].cumsum() / max(d[metric].sum(), 1e-12) * 100
            fig = go.Figure()
            fig.add_bar(x=d[category].astype(str), y=d[metric], name=metric)
            fig.add_scatter(x=d[category].astype(str), y=d["Cumulative %"], name="Cumulative %", yaxis="y2", mode="lines+markers")
            fig.update_layout(
                title=title or f"Pareto · {metric}",
                yaxis_title=metric,
                yaxis2=dict(title="Cumulative %", overlaying="y", side="right", range=[0, 100]),
            )
            return fig

    if chart == "Waterfall":
        metric = y or (numeric[0] if numeric else None)
        category = x or (categorical[0] if categorical else None)
        if metric is None:
            return None
        d = df.copy()
        if category:
            d = d[[category, metric]].dropna().head(40)
            return go.Figure(go.Waterfall(
                x=d[category].astype(str).tolist(),
                y=pd.to_numeric(d[metric], errors="coerce").tolist(),
                measure=["relative"] * len(d),
            )).update_layout(title=title or f"Waterfall · {metric}")
        return None

    if chart == "Sensitivity Plot":
        outcome = y or (numeric[0] if numeric else None)
        inputs = [col for col in numeric if col != outcome]
        if outcome is None or not inputs:
            return None
        strengths = []
        for col in inputs:
            pair = df[[col, outcome]].apply(pd.to_numeric, errors="coerce").dropna()
            corr = pair[col].corr(pair[outcome]) if len(pair) >= 3 else np.nan
            strengths.append({"Driver": col, "Sensitivity": abs(float(corr)) if pd.notna(corr) else 0.0, "Direction": float(corr) if pd.notna(corr) else 0.0})
        d = pd.DataFrame(strengths).sort_values("Sensitivity", ascending=True)
        return px.bar(d, x="Sensitivity", y="Driver", orientation="h", hover_data=["Direction"], title=title or f"Sensitivity · {outcome}")

    if chart == "Sankey":
        source = _find_col(df, ("source", "from", "origin")) or (x if x in df.columns else None)
        target = _find_col(df, ("target", "to", "destination")) or (z if z in df.columns else None)
        value = _find_col(df, ("value", "volume", "flow", "quantity", "qty"))
        if source and target and value:
            d = df[[source, target, value]].dropna().copy()
            d[value] = pd.to_numeric(d[value], errors="coerce")
            d = d.dropna(subset=[value]).groupby([source, target], as_index=False)[value].sum()
            labels = pd.Index(pd.concat([d[source].astype(str), d[target].astype(str)]).unique())
            index = {label: i for i, label in enumerate(labels)}
            return go.Figure(go.Sankey(
                arrangement="snap",
                node=dict(label=labels.tolist(), pad=15, thickness=16),
                link=dict(
                    source=d[source].astype(str).map(index),
                    target=d[target].astype(str).map(index),
                    value=d[value].tolist(),
                ),
            )).update_layout(title=title or "Flow / Sankey Map", height=520)
        return None

    if chart == "Gantt":
        start = _find_col(df, ("start", "begin", "planned start"))
        finish = _find_col(df, ("finish", "end", "completion", "planned finish"))
        task = _find_col(df, ("task", "order", "job", "activity", "machine", "project"))
        if not start or not finish:
            dates = _coerce_datetime_columns(df)
            if len(dates) >= 2:
                start, finish = dates[:2]
        if not start or not finish:
            return None
        work = df.copy()
        work[start] = pd.to_datetime(work[start], errors="coerce")
        work[finish] = pd.to_datetime(work[finish], errors="coerce")
        work = work.dropna(subset=[start, finish])
        if work.empty:
            return None
        task = task or "Task"
        if task not in work.columns:
            work[task] = [f"Task {i+1}" for i in range(len(work))]
        return px.timeline(work, x_start=start, x_end=finish, y=task, title=title or "Engineering Gantt")

    if chart == "Network Map":
        source = _find_col(df, ("source", "from", "origin")) or (categorical[0] if categorical else None)
        target = _find_col(df, ("target", "to", "destination")) or (categorical[1] if len(categorical) > 1 else None)
        if not source or not target:
            return None
        edges = df[[source, target]].dropna().astype(str)
        nodes = sorted(set(edges[source]) | set(edges[target]))
        if not nodes:
            return None
        pos = {node: (float(i % 8), float(-(i // 8))) for i, node in enumerate(nodes)}
        fig = go.Figure()
        for _, row in edges.head(500).iterrows():
            x0, y0 = pos[row[source]]
            x1, y1 = pos[row[target]]
            fig.add_scatter(x=[x0, x1, None], y=[y0, y1, None], mode="lines", hoverinfo="none", showlegend=False)
        fig.add_scatter(
            x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes],
            mode="markers+text", text=nodes, textposition="top center",
            hovertext=nodes, hoverinfo="text", name="Nodes",
            marker=dict(size=16),
        )
        fig.update_layout(title=title or "Engineering Network Map", xaxis=dict(showgrid=False, showticklabels=False), yaxis=dict(showgrid=False, showticklabels=False))
        return fig

    if chart == "3D Scatter" and len(numeric) >= 3:
        x3 = x if x in numeric else numeric[0]
        y3 = y if y in numeric else numeric[1]
        z3 = z if z in numeric else numeric[2]
        return px.scatter_3d(df, x=x3, y=y3, z=z3, title=title or "3D Engineering View")

    if chart == "Pie" and x and y:
        return px.pie(df, names=x, values=y, title=title or f"Share of {y}")

    if not x and y:
        return px.bar(df, y=y, title=title or y)
    if chart == "Line" and x and y:
        return px.line(df, x=x, y=y, markers=True, title=title or f"{y} over {x}")
    if chart == "Area" and x and y:
        return px.area(df, x=x, y=y, title=title or f"{y} over {x}")
    if chart == "Scatter" and x and y:
        return px.scatter(df, x=x, y=y, title=title or f"{y} vs {x}")
    return px.bar(df, x=x, y=y, title=title or f"{y} by {x}" if y else title or "Engineering Data")


def _render_auto_kpi_dashboard(module: str, df: pd.DataFrame, chart_token: str) -> None:
    """Generate a compact KPI dashboard and one automatically selected engineering view."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return
    st.markdown("### ⚡ Auto-Generated KPI Dashboard")
    numeric = _numeric_columns(df)
    missing_pct = float(df.isna().mean().mean() * 100) if len(df.columns) else 100.0
    cards = [
        ("Rows", f"{len(df):,}", "dataset"),
        ("Columns", f"{len(df.columns):,}", "schema"),
        ("Missing", f"{missing_pct:.1f}%", "data quality"),
        ("Numeric KPIs", f"{len(numeric):,}", "measures"),
    ]
    cols = st.columns(4)
    for col, (label, value, detail) in zip(cols, cards):
        col.metric(label, value, detail)

    if numeric:
        kpi_cols = st.columns(min(4, len(numeric)))
        for idx, metric_name in enumerate(numeric[:4]):
            values = pd.to_numeric(df[metric_name], errors="coerce").dropna()
            if not values.empty:
                kpi_cols[idx].metric(f"Avg · {metric_name}", f"{values.mean():,.3g}", f"n={len(values):,}")

    auto_chart = _auto_chart_choice(df)
    # Select compatible fields for the automatic view.
    nums = _numeric_columns(df)
    cats = _categorical_columns(df)
    dates = _coerce_datetime_columns(df)
    x = dates[0] if dates else (cats[0] if cats else None)
    y = nums[0] if nums else None
    z = nums[2] if len(nums) >= 3 else None
    if auto_chart == "Gantt":
        x = y = z = None
    elif auto_chart in {"Sankey", "Network Map"}:
        x = y = z = None
    elif auto_chart == "Heatmap":
        x = y = z = None
    elif auto_chart == "3D Scatter":
        x = nums[0] if nums else None
        y = nums[1] if len(nums) > 1 else None
        z = nums[2] if len(nums) > 2 else None
    elif auto_chart == "Sensitivity Plot":
        x = None
        y = nums[0] if nums else None
    elif auto_chart == "Waterfall":
        x = cats[0] if cats else None
        y = _find_col(df, ("delta", "change", "impact", "variance")) or (nums[0] if nums else None)

    fig = _make_figure(df, auto_chart, x, y, z, f"{module} · Auto view")
    if fig is not None:
        st.caption(f"Auto-selected visualization: **{auto_chart}**")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False, "responsive": True})
        try:
            token = hashlib.sha1(str(module).encode("utf-8")).hexdigest()[:12]
            st.session_state[f"liveviz_last_figure_json_{token}"] = fig.to_json()
            st.session_state[f"liveviz_last_chart_config_{token}"] = {"chart": auto_chart, "x": x, "y": y, "z": z, "mode": "auto-dashboard"}
        except Exception:
            pass
    else:
        st.info("No compatible automatic visualization could be inferred from the current table. Use Custom Engineering Views below.")


def render_live_visualization_studio(module: str, *, expanded: bool = False, preferred_key: str | None = None) -> None:
    """Render the live chart studio beneath an active module."""
    tables = discover_visual_tables(module, preferred_key=preferred_key)
    with st.expander("📊 Live Engineering Visualization Studio", expanded=expanded):
        st.caption("Charts use the current module/workspace data. Edit a table, change the controls, and the visualization updates on the next Streamlit rerun.")
        if not tables:
            st.info("No result table is available yet. The workflow visual below shows the governed engineering path; it is not a measurement.")
            steps = ["Import", "Validate", "Analyze", "Visualize", "Decide", "Export"]
            workflow_fig = go.Figure()
            workflow_fig.add_trace(
                go.Scatter(
                    x=list(range(len(steps))),
                    y=[0] * len(steps),
                    mode="lines+markers+text",
                    text=steps,
                    textposition="top center",
                    hovertemplate="%{text}<extra></extra>",
                    showlegend=False,
                    marker={"size": 15},
                    line={"width": 3},
                )
            )
            workflow_fig.update_layout(
                title=f"{module} · Engineering workflow",
                height=260,
                xaxis={"showgrid": False, "showticklabels": False, "zeroline": False},
                yaxis={"visible": False},
                margin={"l": 20, "r": 20, "t": 55, "b": 20},
            )
            st.plotly_chart(
                workflow_fig,
                use_container_width=True,
                config={"displayModeBar": True, "displaylogo": False, "responsive": True},
            )
            return

        labels = [label for label, _, _ in tables]
        default_source_index = 0
        if preferred_key:
            preferred_labels = [i for i, (_, key, _) in enumerate(tables) if key == preferred_key]
            if preferred_labels:
                default_source_index = preferred_labels[0]
        table_label = st.selectbox("Data source", labels, index=default_source_index, key=f"liveviz_source_{hash(module) & 0xFFFF:04x}")
        df = tables[labels.index(table_label)][2].copy()
        _render_auto_kpi_dashboard(module, df, f"{hash(module) & 0xFFFF:04x}")


        # Avoid accidentally visualizing secrets or enormous payloads.
        if len(df) > 10000:
            df = df.head(10000).copy()

        nums = _numeric_columns(df)
        cats = _categorical_columns(df)
        dates = _coerce_datetime_columns(df)
        cols = [str(c) for c in df.columns]

        if not cols:
            st.info("This table has no columns to visualize.")
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
            suggestions = ["Auto", "Line", "Bar", "Area", "Scatter", "Distribution", "Histogram", "Box", "Pie", "Pareto", "Waterfall", "Sankey", "Heatmap", "Correlation Heatmap", "Health Heatmap", "Control Chart", "SPC", "Anomaly Timeline", "Metric Trend", "Sensitivity Plot", "Gantt", "Network Map", "3D Scatter"]
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

        # Preserve the exact rendered chart in a JSON-safe form so the
        # universal parity evidence exporter can package the same view.
        try:
            chart_token = hashlib.sha1(str(module).encode("utf-8")).hexdigest()[:12]
            st.session_state[f"liveviz_last_figure_json_{chart_token}"] = fig.to_json()
            st.session_state[f"liveviz_last_chart_config_{chart_token}"] = {
                "source_key": tables[labels.index(table_label)][1],
                "chart": actual_chart,
                "x": x,
                "y": y,
                "z": z,
                "aggregation": aggregation,
                "filter_column": None if filter_col == "(none)" else filter_col,
                "filter_value": filter_value,
                "title": title,
            }
        except Exception:
            pass

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


# ---------------------------------------------------------------------------
# Enterprise Visualization Extension
# ---------------------------------------------------------------------------
# These additions deliberately reuse the existing Universal Visualization
# engine. They provide module-aware evidence suites without creating a second
# charting stack.

_BASE_AUTO_CHART_CHOICE = _auto_chart_choice
_BASE_MAKE_FIGURE = _make_figure


def _auto_chart_choice(df: pd.DataFrame) -> str:
    """Choose a visualization using explicit industrial semantics first."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return "Bar"
    names = [str(c).lower().replace("_", " ") for c in df.columns]
    numeric = _numeric_columns(df)
    dates = _coerce_datetime_columns(df)

    has_health = any("health" in n or "status" in n for n in names)
    has_area = any(any(k in n for k in ("area", "domain", "function", "system")) for n in names)
    has_anomaly = any("anomaly" in n or "outlier" in n for n in names)
    has_scenario = any("scenario" in n or "case" in n for n in names)
    has_timestamp = bool(dates)
    has_control_limits = any("ucl" in n or "lcl" in n or "upper control" in n or "lower control" in n for n in names)

    if has_control_limits and numeric:
        return "Control Chart"
    if has_health and has_area and numeric and any(
        "health score" in n or n.strip() == "score" or "health %" in n or "health percentage" in n
        for n in names
    ):
        return "Health Heatmap"
    if has_anomaly and has_timestamp and numeric:
        return "Anomaly Timeline"
    if has_scenario and len(numeric) >= 2:
        return "Sensitivity Plot"
    return _BASE_AUTO_CHART_CHOICE(df)


def _make_figure(
    df: pd.DataFrame,
    chart: str,
    x: str | None,
    y: str | None,
    z: str | None,
    title: str,
) -> go.Figure | None:
    if df.empty:
        return None

    numeric = _numeric_columns(df)
    categorical = _categorical_columns(df)

    if chart == "Health Heatmap":
        area = _find_col(df, ("area", "domain", "function", "system", "category"))
        score = _find_col(df, ("health score", "score", "health"))
        if area and score:
            work = df[[area, score]].copy()
            work[score] = pd.to_numeric(work[score], errors="coerce")
            work = work.dropna(subset=[score]).drop_duplicates(subset=[area], keep="last")
            if not work.empty:
                work["__score"] = work[score].clip(0, 100)
                matrix = work.set_index(area)[["__score"]].T
                return px.imshow(
                    matrix,
                    text_auto=".0f",
                    aspect="auto",
                    zmin=0,
                    zmax=100,
                    title=title or "Industrial Health Heatmap",
                )
        return None

    if chart == "Anomaly Timeline":
        date_col = x if x in df.columns else (_coerce_datetime_columns(df) or [None])[0]
        metric = y if y in df.columns else (numeric[0] if numeric else None)
        if date_col and metric:
            work = df.copy()
            work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
            work[metric] = pd.to_numeric(work[metric], errors="coerce")
            work = work.dropna(subset=[date_col, metric])
            if work.empty:
                return None
            fig = px.line(work, x=date_col, y=metric, markers=True, title=title or f"Anomaly Timeline · {metric}")
            anomaly_col = _find_col(work, ("anomaly", "outlier", "alert"))
            if anomaly_col:
                mask = work[anomaly_col].astype(str).str.lower().isin({"true", "1", "yes", "anomaly", "alert", "critical"})
                flagged = work.loc[mask]
                if not flagged.empty:
                    fig.add_scatter(
                        x=flagged[date_col],
                        y=flagged[metric],
                        mode="markers",
                        marker={"size": 11, "symbol": "x"},
                        name="Anomaly / Alert",
                    )
            return fig
        return None

    if chart == "Metric Trend":
        date_col = x if x in df.columns else (_coerce_datetime_columns(df) or [None])[0]
        metric = y if y in df.columns else (numeric[0] if numeric else None)
        if date_col and metric:
            work = df.copy()
            work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
            work[metric] = pd.to_numeric(work[metric], errors="coerce")
            work = work.dropna(subset=[date_col, metric]).sort_values(date_col)
            return px.line(work, x=date_col, y=metric, markers=True, title=title or f"Metric Trend · {metric}")
        return None

    if chart == "Categorical Distribution":
        category = x if x in df.columns else (categorical[0] if categorical else None)
        if category is None:
            return None
        counts = (
            df[category].astype("string").fillna("<Missing>")
            .value_counts(dropna=False)
            .head(60)
            .rename_axis(str(category))
            .reset_index(name="Count")
        )
        if counts.empty:
            return None
        return px.bar(
            counts,
            x=str(category),
            y="Count",
            title=title or f"Category distribution · {category}",
        )

    if chart == "Data Completeness":
        completeness = (
            df.notna().mean()
            .mul(100.0)
            .sort_values()
            .head(80)
        )
        if completeness.empty:
            return None
        return px.bar(
            x=completeness.index.astype(str),
            y=completeness.values,
            range_y=[0, 100],
            title=title or "Data completeness by field",
            labels={"x": "Field", "y": "Completeness %"},
        )

    if chart == "Temporal Distribution":
        date_col = x if x in df.columns else (_coerce_datetime_columns(df) or [None])[0]
        if date_col is None:
            return None
        values = pd.to_datetime(df[date_col], errors="coerce").dropna()
        if values.empty:
            return None
        counts = values.dt.floor("D").value_counts().sort_index()
        return px.bar(
            x=counts.index,
            y=counts.values,
            title=title or f"Observations over time · {date_col}",
            labels={"x": str(date_col), "y": "Observations"},
        )

    return _BASE_MAKE_FIGURE(df, chart, x, y, z, title)


def build_visualization_suite(
    df: pd.DataFrame,
    context: str = "",
    max_figures: int = 5,
) -> list[tuple[str, go.Figure]]:
    """Create a small, deterministic set of complementary engineering views.

    The suite uses only columns present in the supplied data. No values are
    generated solely for presentation. Existing chart primitives are reused.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []

    numeric = _numeric_columns(df)
    dates = _coerce_datetime_columns(df)
    categorical = _categorical_columns(df)
    plan: list[tuple[str, str, str | None, str | None, str | None]] = []
    seen: set[str] = set()

    def add(chart: str, title: str, x: str | None = None, y: str | None = None, z: str | None = None) -> None:
        if len(plan) >= max_figures or chart in seen:
            return
        fig = _make_figure(df, chart, x, y, z, title)
        if fig is not None:
            plan.append((title, chart, x, y, z))
            seen.add(chart)

    area = _find_col(df, ("area", "domain", "function", "system", "category"))
    health = _find_col(df, ("health score", "score", "health"))
    if area and health and numeric:
        add("Health Heatmap", f"{context} · Health map" if context else "Health map", area, health)

    source = _find_col(df, ("source", "from", "origin"))
    target = _find_col(df, ("target", "to", "destination"))
    flow = _find_col(df, ("value", "volume", "flow", "quantity", "qty"))
    if source and target and flow:
        add("Sankey", f"{context} · Flow map" if context else "Flow map")

    start = _find_col(df, ("start", "begin", "planned start"))
    finish = _find_col(df, ("finish", "end", "completion", "planned finish"))
    if start and finish:
        add("Gantt", f"{context} · Execution timeline" if context else "Execution timeline")

    if dates and numeric:
        add("Metric Trend", f"{context} · Operational trend" if context else "Operational trend", dates[0], numeric[0])

    anomaly = _find_col(df, ("anomaly", "outlier", "alert"))
    if anomaly and dates and numeric:
        add("Anomaly Timeline", f"{context} · Anomalies" if context else "Anomalies", dates[0], numeric[0])

    defectish = next((c for c in numeric if any(k in str(c).lower() for k in ("defect", "failure", "scrap", "downtime"))), None)
    if defectish and categorical:
        add("Pareto", f"{context} · Failure / defect Pareto" if context else "Failure / defect Pareto", categorical[0], defectish)

    if len(numeric) >= 2:
        add("Scatter", f"{context} · Variable relationship" if context else "Variable relationship", numeric[0], numeric[1])
        add("Sensitivity Plot", f"{context} · Sensitivity" if context else "Sensitivity")

    if numeric:
        add("Distribution", f"{context} · Distribution" if context else "Distribution", None, numeric[0])

    if not plan and categorical and numeric:
        add("Bar", f"{context} · KPI by category" if context else "KPI by category", categorical[0], numeric[0])
    if not plan and categorical:
        add("Categorical Distribution", f"{context} · Category counts" if context else "Category counts", categorical[0], None)
    if not plan and dates:
        add("Temporal Distribution", f"{context} · Observation frequency" if context else "Observation frequency", dates[0], None)
    if not plan:
        add("Data Completeness", f"{context} · Data completeness" if context else "Data completeness")

    suite: list[tuple[str, go.Figure]] = []
    for title, chart, x, y, z in plan:
        fig = _make_figure(df, chart, x, y, z, title)
        if fig is not None:
            suite.append((title, fig))
    return suite[:max(1, int(max_figures))]


def visualization_contract_report(module: str, max_figures: int = 4) -> pd.DataFrame:
    """Verify that every non-empty discoverable module table has a graph suite."""
    rows: list[dict[str, Any]] = []
    for label, key, frame in discover_visual_tables(str(module)):
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        suite = ensure_visualization_suite(frame, context=str(module), max_figures=max_figures)
        rows.append({
            "Module": str(module),
            "Table": str(label),
            "State Key": str(key),
            "Rows": int(len(frame)),
            "Columns": int(len(frame.columns)),
            "Graphs": int(len(suite)),
            "Status": "Verified" if suite else "No compatible chart",
            "Primary Chart": str(suite[0][0]) if suite else "",
        })
    return pd.DataFrame(rows, columns=["Module","Table","State Key","Rows","Columns","Graphs","Status","Primary Chart"])

MODULE_VISUAL_CONTRACTS = {
    "Operating System": ("Metric Trend", "Health Heatmap", "Sankey"),
    "Project & Digital Thread": ("Sankey", "Network Map", "Bar"),
    "Copilot": ("Metric Trend", "Distribution", "Bar"),
    "Quality": ("Pareto", "SPC", "Distribution"),
    "OEE": ("Metric Trend", "Pareto", "Distribution"),
    "Forecast": ("Metric Trend", "Distribution", "Scatter"),
    "Optimization": ("Pareto", "Sensitivity Plot", "Scatter"),
    "Economics": ("Waterfall", "Metric Trend", "Distribution"),
    "Simulation": ("Metric Trend", "Distribution", "Scatter"),
    "Maintenance": ("Metric Trend", "Anomaly Timeline", "Distribution"),
    "Workforce": ("Bar", "Metric Trend", "Distribution"),
    "Sustainability": ("Sankey", "Distribution", "Bar"),
    "Digital Twin": ("Metric Trend", "Anomaly Timeline", "Line"),
    "Control Tower": ("Health Heatmap", "Metric Trend", "Bar"),
    "Connectivity": ("Bar", "Metric Trend", "Distribution"),
    "Geospatial": ("Network Map", "Sankey", "Scatter"),
    "Research": ("Scatter", "Distribution", "Sensitivity Plot"),
}


def _module_visual_keys(module: str) -> list[str]:
    return list(_MODULE_KEYS.get(str(module), []))


def ensure_visualization_suite(df: pd.DataFrame, context: str = "", max_figures: int = 4) -> list[tuple[str, go.Figure]]:
    """Universal visualization contract: every non-empty table gets a real view.

    The first attempt uses the industrial chart suite. If a future/custom
    table cannot satisfy a semantic chart, the deterministic completeness view
    is the final safety net; it visualizes only values present in the table.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    suite = build_visualization_suite(df, context=context, max_figures=max_figures)
    if suite:
        return suite
    completeness = df.notna().mean().mul(100.0).sort_values(ascending=True)
    if completeness.empty:
        return []
    fig = px.bar(
        x=completeness.index.astype(str),
        y=completeness.values,
        range_y=[0, 100],
        title=f"{context} · Data completeness" if context else "Data completeness",
        labels={"x": "Field", "y": "Completeness %"},
    )
    return [("Data completeness", fig)]


def audit_all_module_visualizations(max_figures: int = 4) -> pd.DataFrame:
    """Audit the actual discoverable workspace for every catalog module.

    The audit intentionally calls discover_visual_tables rather than only the
    static key registry. This means a new module can inherit the universal
    visualization contract simply by putting a safe table into workspace state.
    Populated tables must yield at least one real Plotly figure; modules with no
    current data remain explicitly marked Ready · awaiting data.
    """
    try:
        from industrial_platform import PLATFORM_CATALOG
        catalog_names = [
            str(item.get("name"))
            for item in PLATFORM_CATALOG
            if isinstance(item, dict) and item.get("name")
        ]
    except Exception:
        catalog_names = []
    module_names = list(dict.fromkeys([*catalog_names, *_MODULE_KEYS.keys()]))

    rows = []
    for module in module_names:
        tables = discover_visual_tables(module, allow_global_fallback=False)
        if not tables:
            rows.append({
                "Module": module,
                "Tables": 0,
                "Rows": 0,
                "Graphs": 0,
                "Status": "Ready · awaiting data",
                "Contract": ", ".join(_contract_for_module(module)),
            })
            continue

        graph_tables = 0
        total_rows = 0
        graph_types = []
        failures = []
        seen_keys = set()
        for label, key, frame in tables:
            if key in seen_keys or not isinstance(frame, pd.DataFrame) or frame.empty:
                continue
            seen_keys.add(key)
            total_rows += int(len(frame))
            suite = ensure_visualization_suite(frame, context=module, max_figures=max_figures)
            if suite:
                graph_tables += 1
                graph_types.append(suite[0][0])
            else:
                failures.append(key)

        status = "Verified" if graph_tables == len(seen_keys) and not failures else "Gap"
        rows.append({
            "Module": module,
            "Tables": len(seen_keys),
            "Rows": total_rows,
            "Graphs": graph_tables,
            "Status": status,
            "Contract": ", ".join(_contract_for_module(module)),
            "Primary Views": ", ".join(graph_types[:6]),
            "Failed State Keys": ", ".join(failures[:6]),
        })
    return pd.DataFrame(rows, columns=["Module","Tables","Rows","Graphs","Status","Contract","Primary Views","Failed State Keys"])


def _contract_for_module(module: str) -> tuple[str, ...]:
    name = str(module).lower()
    for family, charts in MODULE_VISUAL_CONTRACTS.items():
        if family.lower() in name:
            return charts
    return ("Auto visualization",)


def visualization_readiness_summary(max_figures: int = 4) -> dict[str, Any]:
    audit = audit_all_module_visualizations(max_figures=max_figures)
    total = len(audit)
    verified = int(audit["Status"].eq("Verified").sum()) if total else 0
    awaiting = int(audit["Status"].eq("Ready · awaiting data").sum()) if total else 0
    gaps = int(audit["Status"].eq("Gap").sum()) if total else 0
    return {
        "modules": total,
        "verified": verified,
        "awaiting_data": awaiting,
        "gaps": gaps,
        "coverage_pct": round((verified + awaiting) / max(1, total) * 100.0, 1),
    }


def figure_fingerprint(fig: go.Figure) -> str:
    """Stable SHA-256 fingerprint of the exact Plotly figure JSON."""
    return hashlib.sha256(fig.to_json().encode("utf-8")).hexdigest()


_BASE_AUTO_KPI_DASHBOARD = _render_auto_kpi_dashboard


def _render_auto_kpi_dashboard(module: str, df: pd.DataFrame, chart_token: str) -> None:
    """Render KPI cards plus a complementary evidence graph set."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return

    st.markdown("### ⚡ Auto-Generated KPI Dashboard")
    numeric = _numeric_columns(df)
    missing_pct = float(df.isna().mean().mean() * 100) if len(df.columns) else 100.0
    cards = [
        ("Rows", f"{len(df):,}", "dataset"),
        ("Columns", f"{len(df.columns):,}", "schema"),
        ("Missing", f"{missing_pct:.1f}%", "data quality"),
        ("Numeric KPIs", f"{len(numeric):,}", "measures"),
    ]
    cols = st.columns(4)
    for col, (label, value, detail) in zip(cols, cards):
        col.metric(label, value, detail)

    if numeric:
        kpi_cols = st.columns(min(4, len(numeric)))
        for idx, metric_name in enumerate(numeric[:4]):
            values = pd.to_numeric(df[metric_name], errors="coerce").dropna()
            if not values.empty:
                kpi_cols[idx].metric(
                    f"Avg · {metric_name}",
                    f"{values.mean():,.3g}",
                    f"n={len(values):,}",
                )

    suite = build_visualization_suite(df, context=str(module), max_figures=4)
    if not suite:
        st.info("No compatible automatic engineering visualization could be inferred from the current table.")
        return

    st.caption(
        "Universal Visualization selected complementary views from the actual module data: "
        + ", ".join(title.split(" · ")[-1] for title, _ in suite)
        + "."
    )
    for idx, (title, fig) in enumerate(suite):
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "scrollZoom": True,
                "responsive": True,
            },
        )
        if idx == 0:
            try:
                st.session_state[f"liveviz_last_figure_json_{chart_token}"] = fig.to_json()
                st.session_state[f"liveviz_last_chart_config_{chart_token}"] = {
                    "source_key": "auto-suite",
                    "chart": "suite",
                    "title": title,
                    "mode": "auto-suite",
                }
            except Exception:
                pass
