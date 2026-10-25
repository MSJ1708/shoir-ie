"""Unified Shoir-IE Engineering Workbench.

The workbench is the user-facing shell for the common industrial platform.
It reuses the established industrial_platform module implementations and the
new excellence layer, with one consistent workflow for data, validation,
execution, scenarios, health, governance and downloads.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
from datetime import datetime
from uuid import uuid4

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import html

from industrial_platform import render_module, PLATFORM_CATALOG, init_platform_db
from shoir_tool_registry import TOOL_TARGETS, TOOL_STATUS_VALUES, tier_allows_tool, tool_status_counts, require_tool_access
from industrial_platform_excellence import (
    CANONICAL_TIERS, MODULE_MATRIX, canonical_tier, tier_allows, tier_matrix,
    module_matrix, module_availability, deep_data_quality, validate_schema,
    validate_units, referential_integrity, constrained_schedule, control_chart,
    proportion_chart, capability_extended, gage_rr_extended, doe_2level_effects,
    reliability_summary, simulation_statistics, warmup_diagnostic,
    bbox_collision_check, flow_distance, pareto_frontier_v2, robust_scenarios,
    economics_sensitivity, workforce_scenario, sustainability_scenario,
    benchmark_gap, build_decision_card, save_decision, record_approval,
    permission_check, connector_validation, copilot_execution_plan,
    reproducibility_manifest, result_health, export_manifest_tables,
    audit_event, ensure_excellence_db,
)

st.set_page_config(page_title="Shoir-IE | Unified Engineering Workbench", page_icon="🏭", layout="wide")
init_platform_db()
ensure_excellence_db()

USER = st.session_state.get("current_user","guest")
RAW_TIER = str(st.session_state.get("user_tier") or "Starter")
TIER = canonical_tier(RAW_TIER)

# Defaults below are explicitly labelled illustrative examples, never plant evidence.
_TOOL022_EXAMPLE_COUNTS = '{"Productive": 60, "Idle": 25, "Setup": 15}'
_TOOL028_EXAMPLE_COUNTS = '{"Machine": 12, "Material": 7, "Method": 3}'
_TOOL029_EXAMPLE_ITEMS = '[{"category":"Sort","criterion":"Remove unnecessary items","score":3,"evidence":"Illustrative example","owner":"","due_date":""},{"category":"Set in Order","criterion":"Label storage locations","score":3,"evidence":"Illustrative example","owner":"","due_date":""},{"category":"Shine","criterion":"Clean workstations","score":3,"evidence":"Illustrative example","owner":"","due_date":""},{"category":"Standardize","criterion":"Display standard work","score":3,"evidence":"Illustrative example","owner":"","due_date":""},{"category":"Sustain","criterion":"Review 5S weekly","score":3,"evidence":"Illustrative example","owner":"","due_date":""}]'
_TOOL033_EXAMPLE_MEASUREMENTS = '[{"part":"P1","operator":"A","trial":"1","value":10},{"part":"P1","operator":"A","trial":"2","value":12},{"part":"P1","operator":"B","trial":"1","value":11},{"part":"P1","operator":"B","trial":"2","value":13},{"part":"P2","operator":"A","trial":"1","value":20},{"part":"P2","operator":"A","trial":"2","value":22},{"part":"P2","operator":"B","trial":"1","value":21},{"part":"P2","operator":"B","trial":"2","value":23},{"part":"P3","operator":"A","trial":"1","value":30},{"part":"P3","operator":"A","trial":"2","value":32},{"part":"P3","operator":"B","trial":"1","value":31},{"part":"P3","operator":"B","trial":"2","value":33}]'
_TOOL036_EXAMPLE_RECORDS = '[{"x":1,"y":2.1},{"x":2,"y":4.0},{"x":3,"y":6.2},{"x":4,"y":7.9},{"x":5,"y":10.2},{"x":6,"y":11.8},{"x":7,"y":14.1},{"x":8,"y":15.9}]'
_TOOL037_EXAMPLE_SAMPLE_A = "2, 4, 6, 8"
_TOOL049_EXAMPLE_WORK_ORDERS = '[{"work_order_id":"WO-1","task":"Critical bearing","asset":"Pump A","criticality_score":5,"days_until_due":-2,"estimated_hours":4,"required_skill":"Mechanical"},{"work_order_id":"WO-2","task":"Calibration","asset":"Gauge B","criticality_score":4,"days_until_due":0,"estimated_hours":3,"required_skill":"Mechanical"},{"work_order_id":"WO-3","task":"Paint repair","asset":"Frame C","criticality_score":2,"days_until_due":5,"estimated_hours":2,"required_skill":"Electrical"}]'
_TOOL058_EXAMPLE_SUPPLIERS = '[{"supplier":"Acme","scores":{"Delivery":90,"Quality":80},"data_as_of":"2026-Q3","evidence_reference":"sample-audit-1"},{"supplier":"Beta","scores":{"Delivery":75},"data_as_of":"2026-Q3","risk_mitigation":"Provide missing quality evidence"},{"supplier":"Gamma","scores":{"Delivery":70,"Quality":100},"data_as_of":"2026-Q3","evidence_reference":"sample-audit-3"}]'
_TOOL015_EXAMPLE_COLUMNS = "Timestamp, Qty, Defects, mystery_label"
_TOOL052_EXAMPLE_PERIODS = '[{"period":"Jan","demand":30,"planned_production":35,"production_capacity":30,"scheduled_receipts":0,"target_safety_stock":15},{"period":"Feb","demand":60,"planned_production":50,"production_capacity":50,"scheduled_receipts":0,"target_safety_stock":20}]'
_TOOL071_EXAMPLE_STATIONS = '[{"station":"Assembly","servers":1,"mean_service_time":2,"service_distribution":"deterministic"},{"station":"Inspection","servers":1,"mean_service_time":1,"service_distribution":"deterministic"}]'
_TOOL062_EXAMPLE_VARIABLES = '{"x":{"low":0,"up":10,"category":"Continuous"},"y":{"low":0,"up":10,"category":"Continuous"}}'
_TOOL062_EXAMPLE_OBJECTIVE = '{"x":3,"y":2}'
_TOOL062_EXAMPLE_CONSTRAINTS = '[{"name":"minimum_output","coefficients":{"x":1,"y":1},"sense":">=","rhs":4},{"name":"balance","coefficients":{"x":1,"y":3},"sense":">=","rhs":6}]'

st.markdown("""
<style>
.workbench-hero{padding:22px 24px;border:1px solid #dbe4f0;border-radius:18px;background:linear-gradient(135deg,#f8fbff,#ffffff 58%,#f0fdfa);box-shadow:0 10px 30px rgba(15,23,42,.06);margin-bottom:18px}
.workbench-kicker{font-size:11px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#0f766e}
.workbench-hero h1{margin:4px 0 4px;font-size:31px;color:#0f172a}
.workbench-hero p{margin:0;color:#64748b}
.result-card{padding:15px 17px;border:1px solid #dbeafe;border-radius:15px;background:#fff;box-shadow:0 5px 18px rgba(15,23,42,.04)}
.action-row{margin-top:10px}
</style>
<div class="workbench-hero">
  <div class="workbench-kicker">Industrial Decision Platform</div>
  <h1>🏭 Shoir-IE Engineering Command Center</h1>
  <p>Validate → Analyze → Visualize → Decide → Export. Technical details stay available without cluttering the engineering result.</p>
</div>
""",unsafe_allow_html=True)

# Header health/status strip
h1,h2,h3,h4,h5 = st.columns(5)
h1.metric("User", USER)
h2.metric("Tier", TIER)
h3.metric("Modules", len(MODULE_MATRIX))
with sqlite3.connect("enterprise_full_workspace.db") as c:
    ds_count = c.execute("SELECT COUNT(*) FROM platform_datasets").fetchone()[0]
    model_count = c.execute("SELECT COUNT(*) FROM platform_models").fetchone()[0]
h4.metric("Datasets", ds_count)
h5.metric("Models", model_count)

st.divider()

def render_engineering_result(value, title="Analysis result", key_prefix="result"):
    """Render structured results as readable KPIs/tables/charts, not raw JSON."""
    st.markdown(f"### {title}")
    if isinstance(value, dict):
        scalar={k:v for k,v in value.items() if not isinstance(v,(dict,list,pd.DataFrame,np.ndarray))}
        frames={k:v for k,v in value.items() if isinstance(v,pd.DataFrame)}
        nested={k:v for k,v in value.items() if isinstance(v,(dict,list))}
        if scalar:
            cols=st.columns(min(4,max(1,len(scalar))))
            for i,(k,v) in enumerate(scalar.items()):
                label=str(k).replace("_"," ").title()
                display=f"{v:,.3f}" if isinstance(v,(float,np.floating)) else f"{v:,}" if isinstance(v,(int,np.integer)) else str(v)
                cols[i%len(cols)].metric(label,display)
        for k,df in frames.items():
            st.markdown(f"**{str(k).replace('_',' ').title()}**")
            st.dataframe(df,use_container_width=True,hide_index=True)
            _render_result_chart(df,f"{str(k).replace('_',' ').title()} chart",f"{key_prefix}_{k}")
        if nested:
            with st.expander("🔎 Detailed diagnostics",expanded=False):
                for k,v in nested.items():
                    st.markdown(f"**{str(k).replace('_',' ').title()}**")
                    if isinstance(v, list):
                        if not v:
                            st.caption("No items.")
                        elif all(isinstance(item, dict) for item in v):
                            st.dataframe(pd.json_normalize(v),use_container_width=True,hide_index=True)
                        else:
                            # Lists of strings/numbers (for example missing evidence items)
                            # are valid diagnostic output, not records for json_normalize.
                            st.write(v)
                    elif isinstance(v, dict):
                        st.dataframe(pd.DataFrame([v]),use_container_width=True,hide_index=True)
        return
    if isinstance(value,pd.DataFrame):
        st.dataframe(value,use_container_width=True,hide_index=True)
        _render_result_chart(value,title+" chart",key_prefix)
        return
    st.write(value)

def _render_result_chart(df,title,key_prefix):
    if not isinstance(df,pd.DataFrame) or df.empty:
        return
    numeric=[c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric:
        return
    y=st.selectbox("Chart metric",numeric,key=f"{key_prefix}_metric")
    x_candidates=[c for c in df.columns if c != y]
    x=st.selectbox("X-axis / category",x_candidates,key=f"{key_prefix}_x") if x_candidates else None
    chart=st.selectbox("Visualization",["Bar","Line","Scatter"],key=f"{key_prefix}_type")
    plot=df[[x,y]].dropna() if x else df[[y]].dropna()
    if plot.empty: return
    if chart=="Line" and x: fig=px.line(plot,x=x,y=y,markers=True,title=title)
    elif chart=="Scatter" and x: fig=px.scatter(plot,x=x,y=y,title=title)
    else: fig=px.bar(plot,x=x,y=y,title=title) if x else px.bar(plot,y=y,title=title)
    fig.update_layout(height=340,margin=dict(l=10,r=10,t=55,b=10))
    st.plotly_chart(fig,use_container_width=True)


def _require_focused_tool_actor():
    """Require a real authenticated account before executing specialist actions."""
    actor = str(st.session_state.get("current_user") or "").strip()
    authenticated = st.session_state.get("authenticated") is True
    if not authenticated or actor.casefold() in {"", "guest", "guest visitor", "anonymous"}:
        raise PermissionError("Sign in with an active Shoir-IE account before running this tool.")
    return actor


def _persist_focused_tool_result(tool_id, result, inputs):
    """Save focused method inputs/results through the existing per-user workspace service."""
    result_key = "shoir_tool_result_" + tool_id
    inputs_key = "shoir_tool_inputs_" + tool_id
    status_key = "shoir_tool_save_status_" + tool_id
    user = str(USER or "").strip()
    if user.casefold() in {"", "guest", "guest visitor", "anonymous"}:
        result["_workspace_persistence"] = "SESSION_ONLY"
        st.session_state[result_key] = result
        st.session_state[inputs_key] = inputs
        st.session_state[status_key] = "SESSION_ONLY"
        return "SESSION_ONLY"

    try:
        from durable_account_store import durable_backend_configured
        from workspace_persistence import save_user_workspace

        managed_backend = bool(durable_backend_configured())
        # The first write stores the calculation with an explicit pending marker.
        # The second write updates that marker after the store confirms the write.
        result["_workspace_persistence"] = "SAVE_PENDING"
        st.session_state[result_key] = result
        st.session_state[inputs_key] = inputs
        st.session_state[status_key] = "SAVE_PENDING"
        if not save_user_workspace(user, st.session_state):
            result["_workspace_persistence"] = "SAVE_FAILED"
            st.session_state[status_key] = "SAVE_FAILED"
            st.session_state[result_key] = result
            return "SAVE_FAILED"

        mode = "SAVED_MANAGED_WORKSPACE" if managed_backend else "SAVED_LOCAL_FALLBACK"
        result["_workspace_persistence"] = mode
        st.session_state[result_key] = result
        st.session_state[status_key] = mode
        if save_user_workspace(user, st.session_state):
            return mode

        # First write confirmed the result/input payload but the updated status
        # marker was not confirmed; retain the safe pending state on reload.
        result["_workspace_persistence"] = "SAVE_STATUS_NOT_CONFIRMED"
        st.session_state[result_key] = result
        st.session_state[status_key] = "SAVE_STATUS_NOT_CONFIRMED"
        return "SAVE_STATUS_NOT_CONFIRMED"
    except Exception:
        result["_workspace_persistence"] = "SAVE_FAILED"
        st.session_state[result_key] = result
        st.session_state[status_key] = "SAVE_FAILED"
        return "SAVE_FAILED"


def _focused_tool_inputs_match(tool_id, current_inputs):
    saved = st.session_state.get("shoir_tool_inputs_" + tool_id)
    return isinstance(saved, dict) and saved == current_inputs


def _show_focused_tool_persistence(tool_id, result, current_inputs):
    mode = str(result.get("_workspace_persistence", "SESSION_ONLY"))
    if not _focused_tool_inputs_match(tool_id, current_inputs):
        st.warning("This result is stale or its input snapshot cannot be confirmed. Rerun the method before using the result.")
    if mode == "SAVED_MANAGED_WORKSPACE":
        st.caption("Result and input snapshot saved to the configured managed per-user workspace.")
    elif mode == "SAVED_LOCAL_FALLBACK":
        st.warning("Result saved to the local workspace fallback only. Managed persistence is not configured; this may not survive a hosted restart.")
    elif mode == "SESSION_ONLY":
        st.caption("Session-only result. Sign in to attempt saving it to your per-user workspace.")
    elif mode == "SAVE_FAILED":
        st.warning("The current result was not confirmed as saved. It remains in this session; any previously saved workspace state was preserved.")
    elif mode == "SAVE_STATUS_NOT_CONFIRMED" or mode == "SAVE_PENDING":
        st.warning("The result payload may have been written, but save confirmation was incomplete. Verify persistence before relying on it after reload.")
    else:
        st.warning("Workspace persistence status is unknown. Rerun or save the study and verify it after reload.")



# Sidebar navigation
# A directory launch selects the existing module through the normal Workbench
# selector. This preserves the established route renderer and its native tier gate.
_pending_tool_module = st.session_state.pop("shoir_pending_tool_module", None)
if _pending_tool_module:
    st.session_state["workbench_module_search"] = ""
    st.session_state["workbench_category"] = "All"
    st.session_state.pop("workbench_module_selector", None)

st.sidebar.header("Workbench")
search = st.sidebar.text_input("🔎 Search modules", "", key="workbench_module_search")
category = st.sidebar.selectbox("Category", ["All"] + sorted({x[0] for x in MODULE_MATRIX}), key="workbench_category")
available = module_availability(RAW_TIER)
filtered = available.copy()
if category != "All":
    filtered = filtered[filtered["Category"] == category]
if search.strip():
    q=search.strip().lower()
    filtered=filtered[filtered["Module"].str.lower().str.contains(q, regex=False)]

labels = filtered["Module"].tolist()
if not labels:
    st.sidebar.warning("No modules match the current filter.")
    selected = "Engineering Validation Center"
else:
    _module_rows = {row["Module"]: row for _, row in filtered.iterrows()}
    _display_labels = [
        f"{_module_rows[m]['Category']} · {m}" for m in labels
    ]
    _display_to_module = dict(zip(_display_labels, labels))
    if _pending_tool_module in _display_to_module.values():
        _forced_label = next((label for label, module in _display_to_module.items() if module == _pending_tool_module), None)
        if _forced_label:
            st.session_state["workbench_module_selector"] = _forced_label
    _selected_display = st.sidebar.selectbox("Module", _display_labels, key="workbench_module_selector")
    selected = _display_to_module[_selected_display]
    _selected_row = _module_rows[selected]
    st.sidebar.markdown(
        f"""<div class="result-card">
        <div style="font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#0f766e">{html.escape(str(_selected_row['Category']))}</div>
        <div style="font-size:15px;font-weight:800;margin-top:4px;color:#0f172a">{html.escape(str(selected))}</div>
        <div style="font-size:11px;color:#64748b;margin-top:4px">Required tier: {html.escape(str(required)) if 'required' in locals() else 'Configured'}</div>
        </div>""",
        unsafe_allow_html=True,
    )

required = next((x[2] for x in MODULE_MATRIX if x[1] == selected), "Starter")
_selected_module_allowed = tier_allows(RAW_TIER, required)
if not _selected_module_allowed:
    # Keep the tool directory usable for discovery on every tier, but do not
    # render the selected legacy module until the directory has completed.
    st.warning(f"🔒 {selected} requires the {required} capability level. Your current tier maps to {TIER}.")
    st.dataframe(available[["Category","Module","Required Tier","Available"]], use_container_width=True, hide_index=True)

# New cross-cutting platform controls
top1,top2,top3,top4 = st.columns(4)
with top1:
    if st.button("📥 Import / Validate", use_container_width=True):
        st.session_state["show_exchange"]=True
with top2:
    if st.button("🧪 Scenario Lab", use_container_width=True):
        st.session_state["show_scenario"]=True
with top3:
    if st.button("🩺 Model Health", use_container_width=True):
        st.session_state["show_health"]=True
with top4:
    if st.button("📋 Decision Card", use_container_width=True):
        st.session_state["show_decision"]=True


# Progressive-disclosure directory: keep the established shell and module routes intact.
# This is a truthful capability directory, not permission to run a foundation-only tool.
_expand_target_directory = bool(st.session_state.pop("shoir_expand_target_directory", False))
with st.expander("🧭 100-tool directory & readiness", expanded=_expand_target_directory):
    st.caption(
        "Browse the target tool set within the existing Workbench. Readiness reflects the source audit, "
        "not a promise of authenticated end-to-end verification. Tools marked Foundation or Missing are "
        "not represented as operational; use the mapped existing module only for the behavior it actually supports."
    )
    status_counts = tool_status_counts()
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Target tools", len(TOOL_TARGETS))
    s2.metric("Mapped; validation open", status_counts.get("IMPLEMENTED_NEEDS_VALIDATION", 0))
    s3.metric("Foundation only", status_counts.get("FOUNDATION_ONLY", 0))
    s4.metric("Verified end-to-end", status_counts.get("VERIFIED_WORKING", 0))
    d1, d2, d3 = st.columns([2, 1, 1])
    with d1:
        tool_query = st.text_input("Find a tool or use case", key="shoir_100_tool_query")
    with d2:
        tool_workbenches = ["All workbenches"] + sorted({str(item["workbench"]) for item in TOOL_TARGETS})
        tool_workbench_filter = st.selectbox("Workbench", tool_workbenches, key="shoir_100_tool_workbench")
    with d3:
        tool_status_filter = st.selectbox(
            "Readiness status", ["All statuses", *TOOL_STATUS_VALUES], key="shoir_100_tool_status"
        )

    directory_rows = []
    q = tool_query.strip().casefold()
    for item in TOOL_TARGETS:
        searchable = " ".join((
            item["tool_id"], item["canonical_name"], item["workbench"],
            item["existing_module_or_route"], item["calculation_or_action"],
            item["input_contract"], item["output_contract"],
        )).casefold()
        if q and q not in searchable:
            continue
        if tool_workbench_filter != "All workbenches" and item["workbench"] != tool_workbench_filter:
            continue
        if tool_status_filter != "All statuses" and item["implementation_status"] != tool_status_filter:
            continue
        directory_rows.append({
            "ID": item["tool_id"],
            "Tool": item["canonical_name"],
            "Workbench": item["workbench"],
            "Minimum tier": item["target_minimum_tier"],
            "Readiness": item["implementation_status"],
            "Allowed by tier": "Yes" if tier_allows_tool(RAW_TIER, item["tool_id"]) else "No",
            "Existing route": item["existing_module_or_route"],
        })
    st.caption(f"Showing {len(directory_rows)} of {len(TOOL_TARGETS)} target tools.")
    if directory_rows:
        st.dataframe(pd.DataFrame(directory_rows), use_container_width=True, hide_index=True)
        choices = [
            f'{item["tool_id"]} · {item["canonical_name"]}'
            for item in TOOL_TARGETS
            if any(row["ID"] == item["tool_id"] for row in directory_rows)
        ]
        chosen = st.selectbox("Inspect tool requirements", choices, key="shoir_100_tool_inspector")
        chosen_id = chosen.split(" · ", 1)[0]
        selected_tool = next((item for item in TOOL_TARGETS if item["tool_id"] == chosen_id), None)
        if selected_tool:
            st.markdown(f"**{selected_tool['canonical_name']}** · {selected_tool['target_minimum_tier']} minimum")
            st.write(selected_tool["calculation_or_action"])
            mapped_route = str(selected_tool["existing_module_or_route"])
            mapped_row = next((row for row in MODULE_MATRIX if row[1] == mapped_route), None)
            if mapped_row:
                legacy_required_tier = mapped_row[2]
                if not tier_allows_tool(RAW_TIER, selected_tool["tool_id"]):
                    st.caption(f"Target access requires {selected_tool['target_minimum_tier']}; direct opening is unavailable on this package.")
                elif not tier_allows(RAW_TIER, legacy_required_tier):
                    st.warning(
                        f"The mapped module keeps its existing {legacy_required_tier} requirement. "
                        "The target directory does not override legacy module permissions."
                    )
                elif st.button(
                    "Open mapped Workbench module",
                    key="shoir_open_mapped_" + selected_tool["tool_id"],
                    use_container_width=True,
                ):
                    st.session_state["shoir_pending_tool_module"] = mapped_route
                    st.rerun()
            st.markdown("**Required inputs**")
            st.write(selected_tool["input_contract"])
            st.markdown("**Expected outputs**")
            st.write(selected_tool["output_contract"])
            st.markdown("**Mapped existing route**")
            st.write(selected_tool["existing_module_or_route"])
            st.markdown("**Source candidates**")
            st.write(", ".join(selected_tool["source_files"]) or "No specialist source identified in targeted search.")
            st.markdown("**Open gap**")
            st.write(selected_tool["remaining_gap"])
            if selected_tool["external_dependency"]:
                st.markdown("**External dependency**")
                st.write(selected_tool["external_dependency"])
            st.caption(
                "Authorization note: this directory does not execute the tool. The mapped legacy route, "
                "Copilot action, API and export path must enforce their own server-side entitlement checks."
            )

            if selected_tool["tool_id"] in {"T015", "T016", "T017", "T018", "T019", "T021", "T022", "T023", "T024", "T025", "T026", "T027", "T028", "T029", "T030", "T031", "T032", "T033", "T034", "T036", "T037", "T038", "T040", "T041", "T042", "T043", "T045", "T047", "T049", "T050", "T052", "T054", "T055", "T056", "T058", "T059", "T062", "T063", "T066", "T070", "T071", "T075", "T076", "T077", "T078", "T079", "T081", "T082", "T083", "T084", "T085", "T087"}:
                st.markdown("---")
                st.markdown("**Run focused specialist method**")
                st.caption(
                    "These first-pass engines run from explicit inputs, keep their assumptions visible, "
                    "and do not connect to or control live plant equipment."
                )
                if not tier_allows_tool(RAW_TIER, selected_tool["tool_id"]):
                    st.warning(
                        f"This target requires {selected_tool['target_minimum_tier']}. "
                        "The method is not executable on the current package."
                    )
                else:
                    with st.form("shoir_target_method_form_" + selected_tool["tool_id"]):
                        if selected_tool["tool_id"] == "T016":
                            st.caption("Prefilled amount and unit pair are illustrative examples. Physical units use fixed conversion factors; currency conversion requires a dated, sourced rate you provide.")
                            amount_to_convert = st.number_input("Value to convert", value=100.0, step=1.0, key="tool016_amount")
                            unit_choices = ["mm", "cm", "m", "km", "in", "ft", "mi", "mg", "g", "kg", "lb", "oz", "ms", "s", "min", "h", "day", "mL", "L", "m³", "gal", "Wh", "kWh", "MJ", "GJ", "Pa", "kPa", "bar", "psi", "°C", "°F", "K", "SAR", "USD", "EUR", "GBP", "AED", "INR", "JPY"]
                            source_unit = st.selectbox("Source unit or currency", unit_choices, index=0, key="tool016_source")
                            target_unit = st.selectbox("Target unit or currency", unit_choices, index=1, key="tool016_target")
                            exchange_rate_value = st.number_input("Exchange rate (target currency per source currency unit)", min_value=0.000001, value=1.0, step=0.01, key="tool016_rate")
                            exchange_rate_date_value = st.text_input("Exchange-rate date (YYYY-MM-DD; currency conversion only)", key="tool016_rate_date")
                            exchange_rate_source_value = st.text_input("Exchange-rate source (currency conversion only)", key="tool016_rate_source")
                            run_method = st.form_submit_button("Convert value", type="primary", use_container_width=True, key="tool016_run")
                        elif selected_tool["tool_id"] == "T031":
                            st.caption("The prefilled observations are SYNTHETIC examples, not plant measurements. Individuals/Moving-Range reports points outside calculated 3-sigma limits; control limits are not specification limits.")
                            spc_measurements_text = st.text_input("Chronological measurements (comma-separated)", "10, 11, 9, 10, 12, 11", key="tool031_measurements")
                            spc_unit = st.text_input("Measurement unit", "units", key="tool031_unit")
                            run_method = st.form_submit_button("Calculate I-MR control limits", type="primary", use_container_width=True, key="tool031_run")
                        elif selected_tool["tool_id"] == "T040":
                            st.caption("Prefilled quantities/costs are SYNTHETIC examples. Replace with a measured period and traceable costs. Scrap and rework are mutually exclusive dispositions of defective units.")
                            quality_period = st.text_input("Measurement period", "Example period — replace with actual period", key="tool040_period")
                            quality_currency = st.text_input("Cost currency code", "SAR", key="tool040_currency")
                            quality_total_units = st.number_input("Total produced units", min_value=1, value=1000, step=100, key="tool040_total")
                            quality_defects = st.number_input("Defective units", min_value=0, value=40, step=5, key="tool040_defects")
                            quality_scrap_units = st.number_input("Scrap units", min_value=0, value=10, step=1, key="tool040_scrap_units")
                            quality_rework_units = st.number_input("Reworked units", min_value=0, value=20, step=1, key="tool040_rework_units")
                            quality_scrap_cost = st.number_input("Scrap cost per unit", min_value=0.0, value=20.0, step=1.0, key="tool040_scrap_cost")
                            quality_rework_cost = st.number_input("Rework cost per unit", min_value=0.0, value=8.0, step=1.0, key="tool040_rework_cost")
                            quality_inspection_cost = st.number_input("Inspection cost for period", min_value=0.0, value=400.0, step=25.0, key="tool040_inspection_cost")
                            run_method = st.form_submit_button("Calculate quality costs", type="primary", use_container_width=True, key="tool040_run")
                        elif selected_tool["tool_id"] == "T042":
                            st.caption("Prefilled repair durations are SYNTHETIC examples, not actual asset history. This uses complete recorded events only and does not infer censored/incomplete intervals.")
                            mtbf_operating_hours = st.number_input("Accumulated operating hours (repair downtime excluded)", min_value=0.001, value=600.0, step=50.0, key="tool042_operating_hours")
                            repair_durations_text = st.text_input("Repair durations in hours (comma-separated)", "2, 1.5, 3", key="tool042_repairs")
                            run_method = st.form_submit_button("Calculate MTBF / MTTR", type="primary", use_container_width=True, key="tool042_run")
                        elif selected_tool["tool_id"] == "T056":
                            st.caption("The prefilled SKU JSON is SYNTHETIC sample inventory; replace it with validated history. ABC uses annual usage value and XYZ uses population coefficient of variation over aligned periods.")
                            inventory_items_json = st.text_area("SKU data (JSON list)", value='[{"sku":"A","annual_demand":100,"unit_cost":8,"period_demand":[8,10,12]},{"sku":"B","annual_demand":50,"unit_cost":3,"period_demand":[1,10,3]},{"sku":"C","annual_demand":25,"unit_cost":2,"period_demand":[1,20,0]}]', key="tool056_items")
                            inventory_currency = st.text_input("Unit-cost currency", "SAR", key="tool056_currency")
                            abc_a_threshold = st.number_input("A-class cumulative cutoff (fraction)", min_value=0.01, max_value=0.99, value=0.80, step=0.01, key="tool056_a_threshold")
                            abc_b_threshold = st.number_input("B-class cumulative cutoff (fraction)", min_value=0.02, max_value=1.0, value=0.95, step=0.01, key="tool056_b_threshold")
                            xyz_x_cutoff = st.number_input("Maximum X demand CV", min_value=0.0, value=0.50, step=0.05, key="tool056_x_cv")
                            xyz_y_cutoff = st.number_input("Maximum Y demand CV", min_value=0.01, value=1.0, step=0.05, key="tool056_y_cv")
                            run_method = st.form_submit_button("Classify ABC / XYZ inventory", type="primary", use_container_width=True, key="tool056_run")
                        elif selected_tool["tool_id"] == "T021":
                            st.caption("Observed times are retained as entered. The allowance is defined as a percentage of standard time.")
                            observation_text = st.text_input(
                                "Observed times (comma-separated)", "1, 2, 3",
                                key="tool021_observations"
                            )
                            unit = st.selectbox(
                                "Time unit for all observations", ["seconds", "minutes", "hours"],
                                index=1, key="tool021_unit"
                            )
                            rating = st.number_input(
                                "Performance rating (%)", min_value=0.001, value=100.0, step=5.0,
                                key="tool021_rating"
                            )
                            allowance = st.number_input(
                                "Allowance (% of standard time)", min_value=0.0, max_value=99.9,
                                value=10.0, step=1.0, key="tool021_allowance"
                            )
                            run_method = st.form_submit_button("Calculate standard time", type="primary", use_container_width=True, key="tool021_run")
                        elif selected_tool["tool_id"] == "T022":
                            st.caption("Illustrative counts are sample data only. Replace them with observations collected under a representative sampling plan.")
                            work_sampling_counts_json = st.text_area(
                                "Activity observation counts (JSON object)",
                                value=_TOOL022_EXAMPLE_COUNTS,
                                help='Example format: {"Productive": 60, "Idle": 25, "Setup": 15}. Counts must be non-negative whole observations.',
                                key="tool022_counts_json",
                            )
                            confidence_option = st.selectbox(
                                "Confidence level", ["90%", "95%", "99%"], index=1, key="tool022_confidence"
                            )
                            margin_pct = st.number_input(
                                "Target margin of error (percentage points)", min_value=0.1,
                                max_value=49.9, value=5.0, step=0.5, key="tool022_margin"
                            )
                            run_method = st.form_submit_button("Analyze work sampling", type="primary", use_container_width=True, key="tool022_run")
                        elif selected_tool["tool_id"] == "T023":
                            st.caption("Available time, demand and cycle time must refer to the same production period and time unit.")
                            available_time = st.number_input(
                                "Net available production time per period", min_value=0.001,
                                value=480.0, step=30.0, key="tool023_available"
                            )
                            demand_units = st.number_input(
                                "Demand (whole units per period)", min_value=1, value=120, step=1,
                                key="tool023_demand"
                            )
                            cycle_time = st.number_input(
                                "Observed cycle time per unit", min_value=0.001,
                                value=3.0, step=0.25, key="tool023_cycle"
                            )
                            unit = st.selectbox(
                                "Time unit shared by available time and cycle time",
                                ["seconds", "minutes", "hours"], index=1, key="tool023_unit"
                            )
                            run_method = st.form_submit_button("Calculate takt and capacity", type="primary", use_container_width=True, key="tool023_run")
                        elif selected_tool["tool_id"] == "T028":
                            st.caption("Pareto concentration is not proof of causation. A complete 5-Why record is optional; use five non-empty lines when recording one.")
                            pareto_counts_json = st.text_area(
                                "Cause/category counts (JSON object)",
                                value=_TOOL028_EXAMPLE_COUNTS,
                                help="Illustrative counts only. Replace with observed, dated counts before operational use.",
                                key="tool028_counts_json",
                            )
                            problem_statement = st.text_input(
                                "Problem statement (required for a 5-Why chain)", key="tool028_problem"
                            )
                            why_chain_text = st.text_area(
                                "Optional five Whys (one statement per line)", key="tool028_whys"
                            )
                            countermeasure_text = st.text_input("Proposed countermeasure", key="tool028_countermeasure")
                            action_owner = st.text_input("Action owner", key="tool028_owner")
                            action_due_date = st.text_input(
                                "Action due date (YYYY-MM-DD)", key="tool028_due_date"
                            )
                            run_method = st.form_submit_button("Analyze Pareto / record causes", type="primary", use_container_width=True, key="tool028_run")
                        elif selected_tool["tool_id"] == "T029":
                            st.caption("Illustrative example values are self-assessment data. Replace them with an approved checklist and verifiable evidence.")
                            audit_items_json = st.text_area(
                                "5S checklist items (JSON list)",
                                value=_TOOL029_EXAMPLE_ITEMS,
                                help='Each item needs category (one per 5S pillar), criterion, score 0–4, and optional evidence/owner/due_date.',
                                key="tool029_items_json",
                            )
                            run_method = st.form_submit_button("Score 5S audit", type="primary", use_container_width=True, key="tool029_run")
                        elif selected_tool["tool_id"] == "T030":
                            st.caption("A3 plans and measured outcomes are kept separate. A Verified/Closed status requires an actual, dated review and a post-change evidence reference.")
                            record_id_input = st.text_input(
                                "Existing A3 record ID to revise (leave blank to create)", key="tool030_record_id"
                            )
                            a3_title = st.text_input("A3 title", key="tool030_title")
                            a3_problem = st.text_area("Problem statement", key="tool030_problem")
                            a3_metric = st.text_input("Metric name", key="tool030_metric")
                            a3_unit = st.text_input("Metric unit", key="tool030_unit")
                            a3_baseline = st.text_input("Baseline value", key="tool030_baseline")
                            a3_target = st.text_input("Target value", key="tool030_target")
                            a3_actual = st.text_input("Actual after-change value (optional until measured)", key="tool030_actual")
                            a3_root_cause = st.text_area("Root-cause hypothesis", key="tool030_root_cause")
                            a3_countermeasure = st.text_area("Countermeasure", key="tool030_countermeasure")
                            a3_owner = st.text_input("Accountable owner", key="tool030_owner")
                            a3_due_date = st.text_input("Due date (YYYY-MM-DD)", key="tool030_due_date")
                            a3_baseline_evidence = st.text_input("Baseline evidence reference (optional but recommended)", key="tool030_baseline_evidence")
                            a3_post_evidence = st.text_input("Post-change evidence reference", key="tool030_post_evidence")
                            a3_status = st.selectbox(
                                "Implementation status", ["Planned", "In Progress", "Implemented", "Verified", "Closed"],
                                index=0, key="tool030_status"
                            )
                            a3_review_date = st.text_input("Human review date (YYYY-MM-DD)", key="tool030_review_date")
                            run_method = st.form_submit_button("Save A3 record / revision", type="primary", use_container_width=True, key="tool030_run")
                        elif selected_tool["tool_id"] == "T059":
                            st.caption("Greedy slotting heuristic assigns high-pick items to the nearest compatible slot meeting capacity; it is not globally optimal.")
                            slotting_items_json = st.text_area("Items (JSON list: sku, picks_per_day, storage_units, compatibility_group, current_distance_m)", value='[{"sku":"SKU-A","picks_per_day":10,"storage_units":4,"compatibility_group":"food","current_distance_m":10},{"sku":"SKU-B","picks_per_day":4,"storage_units":9,"compatibility_group":"chemical","current_distance_m":20}]', key="tool059_items")
                            slotting_slots_json = st.text_area("Slots (JSON list: slot_id, distance_m, capacity_units, compatibility_group)", value='[{"slot_id":"near-food","distance_m":2,"capacity_units":5,"compatibility_group":"food"},{"slot_id":"near-chemical","distance_m":3,"capacity_units":10,"compatibility_group":"chemical"},{"slot_id":"far-general","distance_m":8,"capacity_units":10,"compatibility_group":"*"}]', key="tool059_slots")
                            run_method = st.form_submit_button("Assign nearest compatible slots", type="primary", use_container_width=True, key="tool059_run")
                        elif selected_tool["tool_id"] == "T063":
                            st.caption("One-to-one minimum-cost assignment only; no calendars, precedence, multi-period or skill constraints.")
                            assignment_tasks_json = st.text_area("Task names (JSON list)", '["Task A","Task B","Task C"]', key="tool063_tasks")
                            assignment_resources_json = st.text_area("Resource names (JSON list)", '["Worker 1","Worker 2","Worker 3"]', key="tool063_resources")
                            assignment_costs_json = st.text_area("Cost matrix (JSON list of rows; task rows × resource columns)", '[[9,2,7],[6,4,3],[5,8,1]]', key="tool063_costs")
                            run_method = st.form_submit_button("Solve assignment", type="primary", use_container_width=True, key="tool063_run")
                        elif selected_tool["tool_id"] == "T066":
                            st.caption("One-dimensional cutting stock. Kerf is charged as an allowance per produced piece.")
                            stock_len = st.number_input(
                                "Stock length (consistent length unit)", min_value=0.001,
                                value=12.0, step=0.5, key="tool066_stock_len"
                            )
                            kerf = st.number_input(
                                "Kerf allowance per produced piece", min_value=0.0,
                                value=0.0, step=0.1, key="tool066_kerf"
                            )
                            parts_json = st.text_area(
                                "Parts as JSON", value='[{"name":"A","length":6,"quantity":4}]',
                                help='Each item needs a unique name, positive length and positive integer quantity.',
                                key="tool066_parts_json"
                            )
                            run_method = st.form_submit_button("Solve cutting plan", type="primary", use_container_width=True, key="tool066_run")
                        elif selected_tool["tool_id"] == "T075":
                            st.caption("Checks aligned forecast/actual observations against an absolute mean-absolute-error threshold.")
                            predictions_text = st.text_input(
                                "Predictions (comma-separated)", "10, 20, 30", key="tool075_predictions"
                            )
                            actuals_text = st.text_input(
                                "Later actuals (same order)", "12, 18, 33", key="tool075_actuals"
                            )
                            max_mae = st.number_input(
                                "Maximum acceptable MAE", min_value=0.0, value=2.0, step=0.5,
                                key="tool075_mae_limit"
                            )
                            window = st.number_input(
                                "Trailing window (0 = all observations)", min_value=0, max_value=10000,
                                value=0, step=1, key="tool075_window"
                            )
                            run_method = st.form_submit_button("Check forecast drift", type="primary", use_container_width=True, key="tool075_run")
                        elif selected_tool["tool_id"] == "T026":
                            st.caption("OEE uses aligned planned time, downtime, ideal cycle, total and good output. Values above 100% are flagged for review, not capped.")
                            oee_planned = st.number_input("Planned production time", min_value=0.001, value=480.0, step=30.0, key="tool026_planned")
                            oee_downtime = st.number_input("Recorded downtime", min_value=0.0, value=60.0, step=5.0, key="tool026_downtime")
                            oee_cycle = st.number_input("Ideal cycle time per unit", min_value=0.001, value=2.0, step=0.25, key="tool026_cycle")
                            oee_total = st.number_input("Total output (whole units)", min_value=1, value=200, step=10, key="tool026_total")
                            oee_good = st.number_input("Good output (whole units)", min_value=0, value=190, step=10, key="tool026_good")
                            oee_unit = st.selectbox("Time unit shared by times", ["seconds", "minutes", "hours"], index=1, key="tool026_unit")
                            run_method = st.form_submit_button("Calculate OEE and losses", type="primary", use_container_width=True, key="tool026_run")
                        elif selected_tool["tool_id"] == "T032":
                            st.caption("Enter measurements in chronological order, grouped into equal-size consecutive subgroups. Normality/control are not assumed.")
                            capability_measurements = st.text_input("Measurements (comma-separated)", "9, 10, 11, 9, 10, 11", key="tool032_measurements")
                            capability_lsl = st.number_input("Lower specification limit (LSL)", value=8.0, step=0.1, key="tool032_lsl")
                            capability_usl = st.number_input("Upper specification limit (USL)", value=12.0, step=0.1, key="tool032_usl")
                            capability_subgroup = st.number_input("Consecutive subgroup size", min_value=2, max_value=100, value=3, step=1, key="tool032_subgroup")
                            capability_unit = st.text_input("Measurement unit", "units", key="tool032_unit")
                            run_method = st.form_submit_button("Calculate capability indices", type="primary", use_container_width=True, key="tool032_run")
                        elif selected_tool["tool_id"] == "T055":
                            st.caption("Classical EOQ assumes stable independent daily demand and deterministic lead time.")
                            inv_demand = st.number_input("Mean daily demand (units/day)", min_value=0.001, value=10.0, step=1.0, key="tool055_demand")
                            inv_sd = st.number_input("Daily demand standard deviation", min_value=0.0, value=2.0, step=0.5, key="tool055_sd")
                            inv_lead = st.number_input("Lead time (days)", min_value=0.0, value=4.0, step=1.0, key="tool055_lead")
                            inv_order_cost = st.number_input("Ordering cost per order", min_value=0.001, value=50.0, step=5.0, key="tool055_order_cost")
                            inv_holding_cost = st.number_input("Annual holding cost per unit", min_value=0.001, value=2.0, step=0.5, key="tool055_holding")
                            inv_days = st.number_input("Operating days per year", min_value=1, max_value=366, value=250, step=1, key="tool055_days")
                            service_options = {"90%": 1.2815515655, "95%": 1.6448536270, "97.5%": 1.9599639845, "99%": 2.3263478740}
                            inv_service = st.selectbox("Target cycle service level (normal z factor)", list(service_options), index=1, key="tool055_service")
                            run_method = st.form_submit_button("Calculate inventory policy", type="primary", use_container_width=True, key="tool055_run")
                        elif selected_tool["tool_id"] == "T078":
                            st.caption("Use a dated, sourced emission factor in kg CO2e per activity unit. Factor validity is not independently verified.")
                            carbon_amount = st.number_input("Activity amount", min_value=0.0, value=250.0, step=25.0, key="tool078_amount")
                            carbon_unit = st.text_input("Activity unit", "kWh", key="tool078_unit")
                            carbon_factor = st.number_input("Emission factor (kg CO2e per activity unit)", min_value=0.0, value=0.4, step=0.05, key="tool078_factor")
                            carbon_factor_unit = st.text_input("Factor unit label", "kg CO2e/kWh", key="tool078_factor_unit")
                            carbon_source = st.text_input("Emission factor source", "User supplied factor", key="tool078_source")
                            carbon_date = st.text_input("Factor date (YYYY-MM-DD)", "2026-01-01", key="tool078_date")
                            carbon_boundary = st.text_input("Accounting boundary / scope", "Scope 2 location-based electricity", key="tool078_boundary")
                            run_method = st.form_submit_button("Calculate carbon emissions", type="primary", use_container_width=True, key="tool078_run")
                        elif selected_tool["tool_id"] == "T081":
                            st.caption("Cash flows must be equally spaced; CF0 occurs at time zero. IRR is omitted when a supported conventional root cannot be established.")
                            economics_cash_flows = st.text_input("Cash flows by period (comma-separated; CF0 first)", "-1000, 600, 600", key="tool081_cashflows")
                            economics_rate = st.number_input("Discount rate (%)", min_value=-99.0, value=10.0, step=1.0, key="tool081_rate")
                            economics_currency = st.text_input("Currency code", "SAR", key="tool081_currency")
                            economics_period = st.selectbox("Cash-flow period unit", ["years", "months", "quarters", "weeks", "days"], index=0, key="tool081_period")
                            run_method = st.form_submit_button("Calculate project economics", type="primary", use_container_width=True, key="tool081_run")
                        elif selected_tool["tool_id"] == "T024":
                            st.caption("Greedy precedence-feasible heuristic, not a global optimum proof. JSON task rows are illustrative only.")
                            line_tasks_json = st.text_area(
                                "Tasks (JSON list: task_id, duration, optional predecessors)",
                                value='[{"task_id":"A","duration":2,"predecessors":[]},{"task_id":"B","duration":3,"predecessors":[]},{"task_id":"C","duration":2,"predecessors":["A"]},{"task_id":"D","duration":1,"predecessors":["B","C"]}]',
                                key="tool024_tasks",
                            )
                            line_cycle_time = st.number_input("Station cycle-time limit", min_value=0.001, value=5.0, step=0.5, key="tool024_cycle")
                            line_time_unit = st.selectbox("Task time unit", ["seconds", "minutes", "hours"], index=1, key="tool024_unit")
                            run_method = st.form_submit_button("Balance production line", type="primary", use_container_width=True, key="tool024_run")
                        elif selected_tool["tool_id"] == "T025":
                            st.caption("Capacity comparison only; capacities must share the same period, product mix and units. Example data are synthetic.")
                            bottleneck_processes_json = st.text_area(
                                "Process capacity data (JSON list: process and capacity)",
                                value='[{"process":"Cutting","capacity":110},{"process":"Welding","capacity":80},{"process":"Packing","capacity":95}]',
                                key="tool025_processes",
                            )
                            bottleneck_demand = st.number_input("Required demand per period", min_value=0.001, value=90.0, step=5.0, key="tool025_demand")
                            bottleneck_period = st.text_input("Capacity period / unit label", "units/shift", key="tool025_period")
                            run_method = st.form_submit_button("Identify capacity constraint", type="primary", use_container_width=True, key="tool025_run")
                        elif selected_tool["tool_id"] == "T027":
                            st.caption("First-pass VSM estimate using WIP / required flow rate plus availability-adjusted process time. Validate the process sequence and data boundaries.")
                            vsm_steps_json = st.text_area(
                                "Process steps (JSON list: step, cycle_time, changeover_time, batch_size, uptime_pct, wip_units, value_added)",
                                value='[{"step":"Machine","cycle_time":1,"changeover_time":20,"batch_size":10,"uptime_pct":95,"wip_units":25,"value_added":true},{"step":"Inspect","cycle_time":2,"changeover_time":0,"batch_size":1,"uptime_pct":98,"wip_units":10,"value_added":false}]',
                                key="tool027_steps",
                            )
                            vsm_demand = st.number_input("Demand per production period (whole units)", min_value=1, value=100, step=10, key="tool027_demand")
                            vsm_available_time = st.number_input("Available time in same period", min_value=0.001, value=480.0, step=30.0, key="tool027_available")
                            vsm_time_unit = st.selectbox("Time unit", ["seconds", "minutes", "hours"], index=1, key="tool027_unit")
                            run_method = st.form_submit_button("Calculate value-stream lead time", type="primary", use_container_width=True, key="tool027_run")
                        elif selected_tool["tool_id"] == "T038":
                            st.caption("RPN bands are screening conventions, not a universal standard. High severity is flagged separately even when RPN is low.")
                            fmea_json = st.text_area(
                                "Failure modes (JSON list: failure_mode, severity, occurrence, detection, effect, cause, controls, action, owner, due_date)",
                                value='[{"failure_mode":"Bearing failure","effect":"Unplanned line stop","cause":"Lubrication loss","existing_controls":"Preventive inspection","severity":8,"occurrence":4,"detection":5,"action":"Review lubrication interval","owner":"","due_date":""}]',
                                key="tool038_fmea",
                            )
                            run_method = st.form_submit_button("Rank FMEA risks", type="primary", use_container_width=True, key="tool038_run")
                        elif selected_tool["tool_id"] == "T070":
                            st.caption("Analytical M/M/1 model only; arrivals and service are assumed Poisson/exponential with one stable server.")
                            queue_arrival_rate = st.number_input("Arrival rate (entities per time unit)", min_value=0.0, value=4.0, step=0.5, key="tool070_arrival")
                            queue_service_rate = st.number_input("Service rate (entities per time unit)", min_value=0.001, value=6.0, step=0.5, key="tool070_service")
                            queue_time_unit = st.selectbox("Rate time unit", ["hours", "minutes", "days"], index=0, key="tool070_unit")
                            run_method = st.form_submit_button("Analyze M/M/1 queue", type="primary", use_container_width=True, key="tool070_run")
                        elif selected_tool["tool_id"] == "T082":
                            st.caption("Direct-material variance only. Positive variance is adverse; negative is favorable. Replace all defaults with one comparable measured period.")
                            cost_standard_qty_per_unit = st.number_input("Standard input quantity per output unit", min_value=0.001, value=2.0, step=0.1, key="tool082_std_qty")
                            cost_actual_output = st.number_input("Actual output quantity (whole units)", min_value=1, value=100, step=10, key="tool082_output")
                            cost_actual_input = st.number_input("Actual input quantity", min_value=0.0, value=210.0, step=5.0, key="tool082_actual_qty")
                            cost_standard_price = st.number_input("Standard unit cost", min_value=0.0, value=5.0, step=0.25, key="tool082_std_price")
                            cost_actual_price = st.number_input("Actual unit cost", min_value=0.0, value=6.0, step=0.25, key="tool082_actual_price")
                            cost_currency = st.text_input("Currency code", "SAR", key="tool082_currency")
                            cost_period = st.text_input("Measurement period", "Example period — replace with actual period", key="tool082_period")
                            run_method = st.form_submit_button("Reconcile cost variance", type="primary", use_container_width=True, key="tool082_run")
                        elif selected_tool["tool_id"] == "T083":
                            st.caption("The arithmetic is computed from user-entered costs. Evidence references and a verifier are not treated as proof that savings were realized.")
                            roi_baseline = st.number_input("Comparable baseline cost", min_value=0.0, value=1000.0, step=50.0, key="tool083_baseline")
                            roi_post = st.number_input("Comparable post-change cost", min_value=0.0, value=700.0, step=50.0, key="tool083_post")
                            roi_implementation = st.number_input("Implementation cost", min_value=0.0, value=100.0, step=25.0, key="tool083_implementation")
                            roi_currency = st.text_input("Currency code", "SAR", key="tool083_currency")
                            roi_window = st.text_input("Measurement window", key="tool083_window")
                            roi_baseline_evidence = st.text_input("Baseline evidence reference", key="tool083_baseline_evidence")
                            roi_outcome_evidence = st.text_input("Post-change evidence reference", key="tool083_outcome_evidence")
                            roi_verifier = st.text_input("Independent verifier / reviewer", key="tool083_verifier")
                            run_method = st.form_submit_button("Calculate ROI (verification remains required)", type="primary", use_container_width=True, key="tool083_run")
                        elif selected_tool["tool_id"] == "T017":
                            st.caption("Join keys must be validated. Many-to-many matches may multiply rows; use duplicate rejection for keys expected to be unique.")
                            join_left_json = st.text_area(
                                "Left table (JSON list of records)",
                                value='[{"id":1,"part":"A"},{"id":2,"part":"B"},{"id":3,"part":"C"}]',
                                key="tool017_left",
                            )
                            join_right_json = st.text_area(
                                "Right table (JSON list of records)",
                                value='[{"component_id":1,"cost":10},{"component_id":3,"cost":30},{"component_id":4,"cost":40}]',
                                key="tool017_right",
                            )
                            join_left_key = st.text_input("Left join key", "id", key="tool017_left_key")
                            join_right_key = st.text_input("Right join key", "component_id", key="tool017_right_key")
                            join_type = st.selectbox("Join type", ["left", "inner", "outer", "right"], key="tool017_type")
                            duplicate_policy = st.selectbox("Duplicate key handling", ["allow", "reject"], key="tool017_duplicates")
                            run_method = st.form_submit_button("Preview and reconcile join", type="primary", use_container_width=True, key="tool017_run")
                        elif selected_tool["tool_id"] == "T018":
                            st.caption("Timestamps are normalized to UTC. Gaps and duplicates are reported; invalid timestamps are rejected rather than silently dropped.")
                            time_series_json = st.text_area(
                                "Timestamped records (JSON list)",
                                value='[{"timestamp":"2026-01-01 00:00:00","count":1,"energy":2.0},{"timestamp":"2026-01-01 02:00:00","count":3,"energy":6.0}]',
                                key="tool018_records",
                            )
                            ts_column = st.text_input("Timestamp column", "timestamp", key="tool018_ts_column")
                            ts_timezone = st.selectbox("Timezone for naive timestamps", ["UTC", "Asia/Riyadh", "Europe/London", "America/New_York"], index=1, key="tool018_timezone")
                            ts_expected_interval = st.text_input("Expected sample interval (optional)", "1h", key="tool018_expected_interval")
                            ts_resample_frequency = st.text_input("Resample frequency (optional, e.g. 15min)", "1h", key="tool018_resample")
                            ts_aggregation = st.selectbox("Resampling aggregation", ["mean", "sum", "min", "max", "first", "last"], key="tool018_agg")
                            run_method = st.form_submit_button("Process timestamps and gaps", type="primary", use_container_width=True, key="tool018_run")
                        elif selected_tool["tool_id"] == "T019":
                            st.caption("Generated rows are explicitly labelled SYNTHETIC and are intended for teaching/testing, not claims about a live plant.")
                            synthetic_rows = st.number_input("Rows to generate", min_value=1, max_value=100000, value=100, step=25, key="tool019_rows")
                            synthetic_seed = st.number_input("Random seed", min_value=0, value=42, step=1, key="tool019_seed")
                            synthetic_start = st.text_input("Start timestamp (ISO datetime)", "2026-01-01T00:00:00Z", key="tool019_start")
                            synthetic_interval = st.number_input("Interval (minutes)", min_value=1, value=60, step=15, key="tool019_interval")
                            synthetic_defect_rate = st.number_input("Defect rate (%)", min_value=0.0, max_value=100.0, value=2.0, step=0.5, key="tool019_defect")
                            synthetic_downtime = st.number_input("Mean downtime per record (minutes)", min_value=0.0, value=5.0, step=1.0, key="tool019_downtime")
                            synthetic_energy = st.number_input("Energy per good-scale output unit (kWh)", min_value=0.0, value=0.5, step=0.1, key="tool019_energy")
                            run_method = st.form_submit_button("Generate synthetic dataset", type="primary", use_container_width=True, key="tool019_run")
                        elif selected_tool["tool_id"] == "T034":
                            st.caption("Single-sample binomial plan. Confirm any contractual sampling standard and finite-lot conditions before use.")
                            sampling_aql = st.number_input("AQL defect fraction (%)", min_value=0.0, max_value=99.0, value=1.0, step=0.5, key="tool034_aql")
                            sampling_ltpd = st.number_input("LTPD defect fraction (%)", min_value=0.1, max_value=100.0, value=10.0, step=0.5, key="tool034_ltpd")
                            sampling_alpha = st.number_input("Producer risk (%)", min_value=0.1, max_value=99.0, value=5.0, step=1.0, key="tool034_alpha")
                            sampling_beta = st.number_input("Consumer risk (%)", min_value=0.1, max_value=99.0, value=10.0, step=1.0, key="tool034_beta")
                            sampling_max_n = st.number_input("Maximum sample size to search", min_value=1, max_value=5000, value=500, step=50, key="tool034_max_n")
                            run_method = st.form_submit_button("Find attributes sampling plan", type="primary", use_container_width=True, key="tool034_run")
                        elif selected_tool["tool_id"] == "T041":
                            st.caption("Two-parameter Weibull maximum-likelihood fit for positive uncensored failure times only. Censored observations and confidence intervals are not supported.")
                            weibull_times_json = st.text_area("Uncensored failure times (JSON list, consistent time unit)", value='[120,220,300,410,520,680,800,950,1120,1390]', key="tool041_times")
                            run_method = st.form_submit_button("Fit Weibull reliability model", type="primary", use_container_width=True, key="tool041_run")
                        elif selected_tool["tool_id"] == "T043":
                            st.caption("Interval-based due-date planner. It does not optimize labor, parts or downtime windows.")
                            pm_tasks_json = st.text_area(
                                "Maintenance tasks (JSON list: asset, task, last_completed_date, interval_days, estimated_duration_hours, required_skill, owner)",
                                value='[{"asset":"CNC-01","task":"Lubrication","last_completed_date":"2026-10-01","interval_days":20,"estimated_duration_hours":1.5,"required_skill":"Mechanical","owner":""},{"asset":"CNC-01","task":"Inspection","last_completed_date":"2026-10-20","interval_days":7,"estimated_duration_hours":1,"required_skill":"Technician","owner":""}]',
                                key="tool043_tasks",
                            )
                            pm_as_of_date = st.text_input("Plan as-of date (YYYY-MM-DD)", "2026-10-24", key="tool043_as_of")
                            run_method = st.form_submit_button("Calculate maintenance due list", type="primary", use_container_width=True, key="tool043_run")
                        elif selected_tool["tool_id"] == "T045":
                            st.caption("Reorder point = average daily demand × lead time + safety stock. Criticality is a user-entered score.")
                            spare_parts_json = st.text_area("Spare parts (JSON list: part, average_daily_demand, lead_time_days, safety_stock, on_hand, scheduled_receipts, unit_cost, criticality_score)", value='[{"part":"Bearing","average_daily_demand":2,"lead_time_days":5,"safety_stock":10,"on_hand":5,"scheduled_receipts":0,"unit_cost":20,"criticality_score":5},{"part":"Gasket","average_daily_demand":0.5,"lead_time_days":2,"safety_stock":1,"on_hand":10,"scheduled_receipts":0,"unit_cost":3,"criticality_score":2}]', key="tool045_parts")
                            run_method = st.form_submit_button("Prioritize spare-parts replenishment", type="primary", use_container_width=True, key="tool045_run")
                        elif selected_tool["tool_id"] == "T047":
                            st.caption("Screening register only, not a certified or legally sufficient site safety assessment.")
                            hazard_json = st.text_area(
                                "Hazards (JSON list with hazard, severity 1–5, likelihood 1–5 and optional controls/action/residual ratings)",
                                value='[{"hazard":"Moving conveyor","activity":"Clearing jam","consequence":"Entanglement injury","severity":5,"likelihood":3,"controls":"Lockout/tagout procedure; verify isolation","residual_severity":5,"residual_likelihood":1,"required_action":"Confirm isolation procedure and training","owner":"Safety lead","review_date":"2026-11-01"}]',
                                key="tool047_hazards",
                            )
                            run_method = st.form_submit_button("Screen and review hazards", type="primary", use_container_width=True, key="tool047_run")
                        elif selected_tool["tool_id"] == "T050":
                            st.caption("Rates use the entered period-specific work-hour denominator; trends do not establish causation.")
                            safety_periods_json = st.text_area("Safety periods (JSON list: period, incidents_by_category, work_hours, lost_workdays)", value='[{"period":"2026-Q1","incidents_by_category":{"Slip":2,"Cut":1},"work_hours":20000,"lost_workdays":4},{"period":"2026-Q2","incidents_by_category":{"Slip":1,"Fatigue":1},"work_hours":40000,"lost_workdays":2}]', key="tool050_periods")
                            safety_rate_base = st.number_input("Rate base work hours", min_value=1.0, value=200000.0, step=25000.0, key="tool050_base")
                            run_method = st.form_submit_button("Calculate incident trend and rates", type="primary", use_container_width=True, key="tool050_run")
                        elif selected_tool["tool_id"] == "T054":
                            st.caption("One-level BOM explosion only. Provide the current validated BOM; this does not recursively explode subassemblies.")
                            mrp_bom_json = st.text_area(
                                "Bill of materials (JSON list: component, qty_per_parent, lead_time_periods, lot_size_multiple)",
                                value='[{"component":"Screw","qty_per_parent":4,"lead_time_periods":2,"lot_size_multiple":10},{"component":"Bolt","qty_per_parent":2,"lead_time_periods":1,"lot_size_multiple":1}]',
                                key="tool054_bom",
                            )
                            mrp_inventory_json = st.text_area(
                                "Component inventory (JSON object keyed by component)",
                                value='{"Screw":{"on_hand":20,"scheduled_receipts":0,"safety_stock":5},"Bolt":{"on_hand":30,"scheduled_receipts":0,"safety_stock":0}}',
                                key="tool054_inventory",
                            )
                            mrp_parent_demand = st.number_input("Parent-assembly demand (whole units)", min_value=1, value=10, step=1, key="tool054_demand")
                            mrp_due_period = st.number_input("Demand due period index (0 = current period)", min_value=-120, max_value=120, value=0, step=1, key="tool054_due")
                            run_method = st.form_submit_button("Calculate component requirements", type="primary", use_container_width=True, key="tool054_run")
                        elif selected_tool["tool_id"] == "T076":
                            st.caption("This reconstructs event-log variants and directly-follows transitions. It is not full conformance checking or causal analysis.")
                            process_event_log_json = st.text_area(
                                "Event log (JSON list: case_id, activity, timestamp)",
                                value='[{"case_id":"1","activity":"Receive","timestamp":"2026-01-01T00:00:00Z"},{"case_id":"1","activity":"Inspect","timestamp":"2026-01-01T01:00:00Z"},{"case_id":"2","activity":"Receive","timestamp":"2026-01-01T00:00:00Z"},{"case_id":"2","activity":"Pack","timestamp":"2026-01-01T02:00:00Z"}]',
                                key="tool076_event_log",
                            )
                            run_method = st.form_submit_button("Analyze event-log flow", type="primary", use_container_width=True, key="tool076_run")
                        elif selected_tool["tool_id"] == "T077":
                            st.caption("Scenario comparison only; this does not control industrial equipment or guarantee savings.")
                            energy_baseline_json = st.text_area("Baseline (JSON object: name, energy_kwh, output_units, cost_per_kwh, emission_factor_kg_per_kwh)", value='{"name":"Baseline","energy_kwh":1000,"output_units":100,"cost_per_kwh":0.2,"emission_factor_kg_per_kwh":0.5}', key="tool077_baseline")
                            energy_alternatives_json = st.text_area("Alternatives (JSON list with the same metric fields)", value='[{"name":"Improved","energy_kwh":800,"output_units":100,"cost_per_kwh":0.2,"emission_factor_kg_per_kwh":0.5},{"name":"Lower volume","energy_kwh":700,"output_units":70,"cost_per_kwh":0.2,"emission_factor_kg_per_kwh":0.5}]', key="tool077_alternatives")
                            run_method = st.form_submit_button("Compare energy scenarios", type="primary", use_container_width=True, key="tool077_run")
                        elif selected_tool["tool_id"] == "T079":
                            st.caption("Flow balance requires same-unit quantities and comparable measurement boundaries. Unreconciled balance is reported, not silently allocated.")
                            water_flows_json = st.text_area(
                                "Process flows (JSON list: process, input_quantity, product_output_quantity, waste_quantity, unit, period)",
                                value='[{"process":"Wash","input_quantity":100,"product_output_quantity":85,"waste_quantity":15,"unit":"L","period":"2026-09"},{"process":"Rinse","input_quantity":50,"product_output_quantity":45,"waste_quantity":5,"unit":"L","period":"2026-09"}]',
                                key="tool079_flows",
                            )
                            run_method = st.form_submit_button("Balance water and waste flows", type="primary", use_container_width=True, key="tool079_run")
                        elif selected_tool["tool_id"] == "T084":
                            st.caption("Criterion weights are subjective inputs. Scores are normalized direction-aware; sensitivity analysis is not yet included.")
                            portfolio_criteria_json = st.text_area(
                                "Criteria (JSON list: name, weight, direction maximize/minimize)",
                                value='[{"name":"Cost","weight":2,"direction":"minimize"},{"name":"Quality","weight":1,"direction":"maximize"}]',
                                key="tool084_criteria",
                            )
                            portfolio_alternatives_json = st.text_area(
                                "Project alternatives (JSON list: name and scores object keyed by criterion)",
                                value='[{"name":"Project A","scores":{"Cost":100,"Quality":70}},{"name":"Project B","scores":{"Cost":200,"Quality":90}}]',
                                key="tool084_alternatives",
                            )
                            run_method = st.form_submit_button("Score project portfolio", type="primary", use_container_width=True, key="tool084_run")
                        elif selected_tool["tool_id"] == "T085":
                            st.caption("Balanced, independent, two-sided two-sample t-test; normal outcomes and equal-variance assumptions.")
                            effect_size = st.number_input(
                                "Standardized effect size (Cohen's d)", min_value=0.001,
                                value=0.5, step=0.1, key="tool085_effect_size"
                            )
                            alpha = st.number_input(
                                "Significance level (alpha)", min_value=0.001, max_value=0.5,
                                value=0.05, step=0.01, key="tool085_alpha"
                            )
                            target_power = st.number_input(
                                "Target statistical power", min_value=0.01, max_value=0.999,
                                value=0.80, step=0.05, key="tool085_target_power"
                            )
                            search_limit = st.number_input(
                                "Maximum sample size per group to search", min_value=2, max_value=100000,
                                value=10000, step=100, key="tool085_search_limit"
                            )
                            run_method = st.form_submit_button("Calculate sample size", type="primary", use_container_width=True, key="tool085_run")
                        elif selected_tool["tool_id"] == "T033":
                            st.caption("Crossed gauge R&R using a balanced parts × operators × trials design. Example readings are SYNTHETIC; confirm the method and acceptance criteria with a qualified MSA reviewer.")
                            gage_rr_json = st.text_area("Measurements (JSON list: part, operator, trial, value)", value=_TOOL033_EXAMPLE_MEASUREMENTS, key="tool033_measurements")
                            gage_rr_unit = st.text_input("Measurement unit", "mm", key="tool033_unit")
                            gage_rr_tolerance = st.number_input("Optional engineering tolerance width", min_value=0.001, value=1.0, step=0.1, key="tool033_tolerance")
                            run_method = st.form_submit_button("Calculate crossed gage R&R", type="primary", use_container_width=True, key="tool033_run")
                        elif selected_tool["tool_id"] == "T036":
                            st.caption("Ordinary least squares with an intercept, coefficient diagnostics and overall regression ANOVA. Use numeric, complete, independently collected rows; regression does not establish causation.")
                            regression_records_json = st.text_area("Observations (JSON list of objects)", value=_TOOL036_EXAMPLE_RECORDS, key="tool036_records")
                            regression_response = st.text_input("Response column", "y", key="tool036_response")
                            regression_predictors_text = st.text_input("Predictor columns (comma-separated)", "x", key="tool036_predictors")
                            run_method = st.form_submit_button("Fit regression and ANOVA", type="primary", use_container_width=True, key="tool036_run")
                        elif selected_tool["tool_id"] == "T037":
                            st.caption("Research Pack method subset: two-sided one-sample, independent Welch, and paired t-tests only. Example values are synthetic. Check study design and assumptions before interpretation.")
                            hypothesis_test_type = st.selectbox("Supported test", ["one_sample_t", "welch_t", "paired_t"], format_func=lambda value: {"one_sample_t": "One-sample t-test", "welch_t": "Independent Welch t-test", "paired_t": "Paired t-test"}[value], key="tool037_type")
                            hypothesis_sample_a = st.text_input("Sample A / first measurements (comma-separated)", _TOOL037_EXAMPLE_SAMPLE_A, key="tool037_sample_a")
                            hypothesis_sample_b = st.text_input("Sample B / paired measurements (comma-separated)", "1, 3, 5, 7", key="tool037_sample_b")
                            hypothesis_null_mean = st.number_input("Null hypothesis mean (one-sample test only)", value=4.0, step=0.5, key="tool037_null_mean")
                            hypothesis_alpha = st.number_input("Significance level (alpha)", min_value=0.001, max_value=0.5, value=0.05, step=0.01, key="tool037_alpha")
                            run_method = st.form_submit_button("Run hypothesis test", type="primary", use_container_width=True, key="tool037_run")
                        elif selected_tool["tool_id"] == "T049":
                            st.caption("Greedy maintenance backlog priority under a stated labor-hours budget. It is not a globally optimal schedule; supplied skills and due dates must be checked against the actual CMMS/work plan.")
                            maintenance_orders_json = st.text_area("Maintenance work orders (JSON list)", value=_TOOL049_EXAMPLE_WORK_ORDERS, key="tool049_orders")
                            maintenance_available_hours = st.number_input("Available qualified labor hours in this planning window", min_value=0.0, value=7.0, step=1.0, key="tool049_hours")
                            maintenance_skills_text = st.text_input("Available skills (comma-separated; blank means no skill restriction)", "Mechanical, Electrical", key="tool049_skills")
                            maintenance_due_soon_days = st.number_input("Due-soon window (whole days)", min_value=0, max_value=365, value=3, step=1, key="tool049_due_soon")
                            run_method = st.form_submit_button("Prioritize maintenance backlog", type="primary", use_container_width=True, key="tool049_run")
                        elif selected_tool["tool_id"] == "T058":
                            st.caption("Weighted 0–100 supplier scorecard. Suppliers with missing criteria stay unranked. The weights and scores are user supplied; this is not a verified supplier-risk assessment.")
                            supplier_records_json = st.text_area("Supplier records (JSON list)", value=_TOOL058_EXAMPLE_SUPPLIERS, key="tool058_suppliers")
                            supplier_weights_json = st.text_area("Criterion weights (JSON object; values are relative weights)", value='{"Delivery":0.4,"Quality":0.6}', key="tool058_weights")
                            run_method = st.form_submit_button("Score supplier performance", type="primary", use_container_width=True, key="tool058_run")
                        elif selected_tool["tool_id"] == "T015":
                            st.caption("Suggest source-to-canonical industrial fields; fuzzy matches require confirmation. Original source headers are retained in the mapping table. This does not alter the imported dataset.")
                            field_source_columns = st.text_input("Source column names (comma-separated)", _TOOL015_EXAMPLE_COLUMNS, key="tool015_columns")
                            field_manual_mapping_json = st.text_area("Optional confirmed mapping (JSON object: source header → canonical field ID)", "{}", key="tool015_manual")
                            field_minimum_confidence = st.slider("Minimum confidence for a suggested mapping", min_value=0.0, max_value=1.0, value=0.65, step=0.05, key="tool015_threshold")
                            run_method = st.form_submit_button("Suggest industrial field mappings", type="primary", use_container_width=True, key="tool015_run")
                        elif selected_tool["tool_id"] == "T052":
                            st.caption("Deterministic time-phased S&OP balance. Capacity limits are applied; unmet demand becomes backlog. This is an aggregate plan, not a finite-capacity optimizer.")
                            sop_periods_json = st.text_area("Periods (JSON list)", value=_TOOL052_EXAMPLE_PERIODS, key="tool052_periods")
                            sop_starting_inventory = st.number_input("Starting inventory (units)", min_value=0.0, value=20.0, step=5.0, key="tool052_inventory")
                            run_method = st.form_submit_button("Reconcile S&OP plan", type="primary", use_container_width=True, key="tool052_run")
                        elif selected_tool["tool_id"] == "T071":
                            st.caption("Event-driven FCFS simulation with finite servers, explicit deterministic/exponential arrivals and service times, seeded replications and job-based warm-up exclusion. Not a calibrated digital twin.")
                            des_steps_json = st.text_area("Ordered stations (JSON list)", value=_TOOL071_EXAMPLE_STATIONS, key="tool071_steps")
                            des_job_count = st.number_input("Jobs to simulate", min_value=2, max_value=10000, value=50, step=1, key="tool071_jobs")
                            des_interarrival = st.number_input("Mean interarrival time", min_value=0.001, value=1.0, step=0.5, key="tool071_interarrival")
                            des_arrival_distribution = st.selectbox("Arrival distribution", ["deterministic", "exponential"], key="tool071_arrival_dist")
                            des_warmup_jobs = st.number_input("Initial jobs excluded from performance metrics", min_value=0, max_value=9999, value=5, step=1, key="tool071_warmup")
                            des_replications = st.number_input("Replications", min_value=1, max_value=100, value=10, step=1, key="tool071_replications")
                            des_seed = st.number_input("Base random seed", min_value=-2147483648, max_value=2147483647, value=42, step=1, key="tool071_seed")
                            des_time_unit = st.text_input("Time unit", value="minutes", key="tool071_unit")
                            run_method = st.form_submit_button("Run discrete-event simulation", type="primary", use_container_width=True, key="tool071_run")
                        elif selected_tool["tool_id"] == "T062":
                            st.caption("Run a linear or mixed-integer model and independently check variable bounds/integrality and each constraint residual. Solver status is not the same as proof that the model formulation is correct; no IIS is generated.")
                            solver_variables_json = st.text_area("Variables (JSON object: name → {low, up, category})", value=_TOOL062_EXAMPLE_VARIABLES, key="tool062_variables")
                            solver_objective_json = st.text_area("Objective coefficients (JSON object)", value=_TOOL062_EXAMPLE_OBJECTIVE, key="tool062_objective")
                            solver_constraints_json = st.text_area("Linear constraints (JSON list)", value=_TOOL062_EXAMPLE_CONSTRAINTS, key="tool062_constraints")
                            solver_direction = st.selectbox("Objective direction", ["minimize", "maximize"], key="tool062_direction")
                            solver_time_limit = st.number_input("Solver time limit (seconds)", min_value=0.1, max_value=300.0, value=10.0, step=1.0, key="tool062_time_limit")
                            solver_tolerance = st.select_slider("Feasibility tolerance", options=[1e-7, 1e-6, 1e-5, 1e-4, 1e-3], value=1e-7, key="tool062_tolerance")
                            run_method = st.form_submit_button("Solve and diagnose model", type="primary", use_container_width=True, key="tool062_run")
                        elif selected_tool["tool_id"] == "T087":
                            st.caption("Package a previously completed, authorized tool result with method/environment metadata, configuration fingerprint and SHA-256 checksums. Raw inputs and detailed result tables are opt-in. Review the ZIP contents before sharing.")
                            result_id_candidates = sorted({
                                key.replace("shoir_tool_result_", "")
                                for key in st.session_state.keys()
                                if key.startswith("shoir_tool_result_T")
                                and key != "shoir_tool_result_T087"
                                and isinstance(st.session_state.get(key), dict)
                                and tier_allows_tool(RAW_TIER, key.replace("shoir_tool_result_", ""))
                            })
                            if not result_id_candidates:
                                st.info("Run an entitled engineering tool in this session first. Only completed, currently authorized results are eligible.")
                            result_id_options = result_id_candidates or ["NONE"]
                            source_result_tool_id = st.selectbox(
                                "Completed result to package",
                                options=result_id_options,
                                format_func=lambda tool_id: (
                                    f"{tool_id} · {next((tool.get('canonical_name', tool_id) for tool in TOOL_TARGETS if tool.get('tool_id') == tool_id), tool_id)}"
                                    if tool_id != "NONE" else "No completed authorized result"
                                ),
                                disabled=not bool(result_id_candidates),
                                key="tool087_source_id",
                            )
                            reproducibility_metadata_json = st.text_area(
                                "Run metadata (JSON object; e.g. study reference, reviewer, protocol version)",
                                value='{"study_reference":"demo-study","method_version":"Shoir-IE target engine","notes":"Review before distribution"}',
                                key="tool087_metadata",
                            )
                            include_input_snapshot = st.checkbox(
                                "Include redacted input snapshot (opt-in)",
                                value=False,
                                key="tool087_include_inputs",
                            )
                            include_result_tables = st.checkbox(
                                "Include sanitized result tables (opt-in)",
                                value=False,
                                key="tool087_include_tables",
                            )
                            run_method = st.form_submit_button(
                                "Build reproducibility ZIP",
                                type="primary",
                                use_container_width=True,
                                key="tool087_run",
                                disabled=not bool(result_id_candidates),
                            )

                    if selected_tool["tool_id"] == "T021":
                        current_tool_inputs = {
                            "observation_times_text": observation_text,
                            "performance_rating_pct": rating,
                            "allowance_pct_of_standard_time": allowance,
                            "time_unit": unit,
                        }
                    elif selected_tool["tool_id"] == "T022":
                        current_tool_inputs = {
                            "activity_counts_json": work_sampling_counts_json,
                            "confidence_level": confidence_option,
                            "target_margin_of_error_pct": margin_pct,
                        }
                    elif selected_tool["tool_id"] == "T023":
                        current_tool_inputs = {
                            "available_time_per_period": available_time,
                            "demand_units_per_period": demand_units,
                            "cycle_time_per_unit": cycle_time,
                            "time_unit": unit,
                        }
                    elif selected_tool["tool_id"] == "T028":
                        current_tool_inputs = {
                            "category_counts_json": pareto_counts_json,
                            "problem_statement": problem_statement,
                            "why_chain_text": why_chain_text,
                            "countermeasure": countermeasure_text,
                            "owner": action_owner,
                            "due_date": action_due_date,
                        }
                    elif selected_tool["tool_id"] == "T029":
                        current_tool_inputs = {"checklist_json": audit_items_json}
                    elif selected_tool["tool_id"] == "T030":
                        current_tool_inputs = {
                            "record_id": record_id_input,
                            "title": a3_title,
                            "problem_statement": a3_problem,
                            "metric_name": a3_metric,
                            "unit": a3_unit,
                            "baseline_value": a3_baseline,
                            "target_value": a3_target,
                            "actual_after_value": a3_actual,
                            "root_cause_hypothesis": a3_root_cause,
                            "countermeasure": a3_countermeasure,
                            "owner": a3_owner,
                            "due_date": a3_due_date,
                            "baseline_evidence": a3_baseline_evidence,
                            "post_change_evidence": a3_post_evidence,
                            "implementation_status": a3_status,
                            "review_date": a3_review_date,
                        }
                    elif selected_tool["tool_id"] == "T066":
                        current_tool_inputs = {
                            "stock_length": stock_len, "kerf_allowance": kerf,
                            "parts_json": parts_json,
                        }
                    elif selected_tool["tool_id"] == "T075":
                        current_tool_inputs = {
                            "predictions_text": predictions_text, "actuals_text": actuals_text,
                            "maximum_mae": max_mae, "trailing_window": int(window),
                        }
                    elif selected_tool["tool_id"] == "T026":
                        current_tool_inputs = {"planned_time": oee_planned, "downtime": oee_downtime, "ideal_cycle_time": oee_cycle, "total_count": oee_total, "good_count": oee_good, "time_unit": oee_unit}
                    elif selected_tool["tool_id"] == "T032":
                        current_tool_inputs = {"measurements_text": capability_measurements, "lsl": capability_lsl, "usl": capability_usl, "subgroup_size": int(capability_subgroup), "unit": capability_unit}
                    elif selected_tool["tool_id"] == "T055":
                        current_tool_inputs = {"mean_daily_demand": inv_demand, "daily_demand_stddev": inv_sd, "lead_time_days": inv_lead, "order_cost_per_order": inv_order_cost, "annual_holding_cost_per_unit": inv_holding_cost, "operating_days_per_year": int(inv_days), "service_level": inv_service}
                    elif selected_tool["tool_id"] == "T078":
                        current_tool_inputs = {"activity_amount": carbon_amount, "activity_unit": carbon_unit, "emission_factor": carbon_factor, "factor_unit": carbon_factor_unit, "factor_source": carbon_source, "factor_date": carbon_date, "boundary": carbon_boundary}
                    elif selected_tool["tool_id"] == "T081":
                        current_tool_inputs = {"cash_flows_text": economics_cash_flows, "discount_rate_pct": economics_rate, "currency": economics_currency, "period_unit": economics_period}
                    elif selected_tool["tool_id"] == "T024":
                        current_tool_inputs = {"tasks_json": line_tasks_json, "cycle_time": line_cycle_time, "time_unit": line_time_unit}
                    elif selected_tool["tool_id"] == "T025":
                        current_tool_inputs = {"processes_json": bottleneck_processes_json, "demand_units_per_period": bottleneck_demand, "period_label": bottleneck_period}
                    elif selected_tool["tool_id"] == "T027":
                        current_tool_inputs = {"steps_json": vsm_steps_json, "demand_units_per_period": vsm_demand, "available_time_per_period": vsm_available_time, "time_unit": vsm_time_unit}
                    elif selected_tool["tool_id"] == "T038":
                        current_tool_inputs = {"failure_modes_json": fmea_json}
                    elif selected_tool["tool_id"] == "T070":
                        current_tool_inputs = {"arrival_rate_per_time": queue_arrival_rate, "service_rate_per_time": queue_service_rate, "time_unit": queue_time_unit}
                    elif selected_tool["tool_id"] == "T082":
                        current_tool_inputs = {"standard_quantity_per_unit": cost_standard_qty_per_unit, "actual_output_units": cost_actual_output, "actual_input_quantity": cost_actual_input, "standard_unit_cost": cost_standard_price, "actual_unit_cost": cost_actual_price, "currency": cost_currency, "period": cost_period}
                    elif selected_tool["tool_id"] == "T083":
                        current_tool_inputs = {"baseline_cost": roi_baseline, "post_change_cost": roi_post, "implementation_cost": roi_implementation, "currency": roi_currency, "measurement_window": roi_window, "baseline_evidence": roi_baseline_evidence, "outcome_evidence": roi_outcome_evidence, "verifier": roi_verifier}
                    elif selected_tool["tool_id"] == "T017":
                        current_tool_inputs = {"left_records_json": join_left_json, "right_records_json": join_right_json, "left_key": join_left_key, "right_key": join_right_key, "join_type": join_type, "duplicate_policy": duplicate_policy}
                    elif selected_tool["tool_id"] == "T018":
                        current_tool_inputs = {"records_json": time_series_json, "timestamp_column": ts_column, "timezone_name": ts_timezone, "expected_interval": ts_expected_interval, "resample_frequency": ts_resample_frequency, "aggregation": ts_aggregation}
                    elif selected_tool["tool_id"] == "T019":
                        current_tool_inputs = {"row_count": int(synthetic_rows), "seed": int(synthetic_seed), "start_timestamp": synthetic_start, "interval_minutes": int(synthetic_interval), "defect_rate_pct": synthetic_defect_rate, "mean_downtime_minutes": synthetic_downtime, "energy_kwh_per_unit": synthetic_energy}
                    elif selected_tool["tool_id"] == "T034":
                        current_tool_inputs = {"aql_pct": sampling_aql, "ltpd_pct": sampling_ltpd, "producer_risk_pct": sampling_alpha, "consumer_risk_pct": sampling_beta, "max_sample_size": int(sampling_max_n)}
                    elif selected_tool["tool_id"] == "T041":
                        current_tool_inputs = {"failure_times_json": weibull_times_json}
                    elif selected_tool["tool_id"] == "T043":
                        current_tool_inputs = {"tasks_json": pm_tasks_json, "as_of_date": pm_as_of_date}
                    elif selected_tool["tool_id"] == "T045":
                        current_tool_inputs = {"parts_json": spare_parts_json}
                    elif selected_tool["tool_id"] == "T047":
                        current_tool_inputs = {"hazards_json": hazard_json}
                    elif selected_tool["tool_id"] == "T050":
                        current_tool_inputs = {"periods_json": safety_periods_json, "rate_base_hours": safety_rate_base}
                    elif selected_tool["tool_id"] == "T054":
                        current_tool_inputs = {"bom_json": mrp_bom_json, "inventory_json": mrp_inventory_json, "parent_demand_units": mrp_parent_demand, "due_period": int(mrp_due_period)}
                    elif selected_tool["tool_id"] == "T059":
                        current_tool_inputs = {"items_json": slotting_items_json, "slots_json": slotting_slots_json}
                    elif selected_tool["tool_id"] == "T063":
                        current_tool_inputs = {"tasks_json": assignment_tasks_json, "resources_json": assignment_resources_json, "costs_json": assignment_costs_json}
                    elif selected_tool["tool_id"] == "T077":
                        current_tool_inputs = {"baseline_json": energy_baseline_json, "alternatives_json": energy_alternatives_json}
                    elif selected_tool["tool_id"] == "T084":
                        current_tool_inputs = {"criteria_json": portfolio_criteria_json, "alternatives_json": portfolio_alternatives_json}
                    elif selected_tool["tool_id"] == "T076":
                        current_tool_inputs = {"event_log_json": process_event_log_json}
                    elif selected_tool["tool_id"] == "T079":
                        current_tool_inputs = {"flows_json": water_flows_json}
                    elif selected_tool["tool_id"] == "T016":
                        current_tool_inputs = {"amount": amount_to_convert, "source_unit": source_unit, "target_unit": target_unit, "exchange_rate": exchange_rate_value, "exchange_rate_date": exchange_rate_date_value, "exchange_rate_source": exchange_rate_source_value}
                    elif selected_tool["tool_id"] == "T031":
                        current_tool_inputs = {"measurements_text": spc_measurements_text, "unit": spc_unit}
                    elif selected_tool["tool_id"] == "T040":
                        current_tool_inputs = {"period": quality_period, "currency": quality_currency, "total_units": quality_total_units, "defective_units": quality_defects, "scrap_units": quality_scrap_units, "rework_units": quality_rework_units, "scrap_cost_per_unit": quality_scrap_cost, "rework_cost_per_unit": quality_rework_cost, "inspection_cost": quality_inspection_cost}
                    elif selected_tool["tool_id"] == "T042":
                        current_tool_inputs = {"operating_hours": mtbf_operating_hours, "repair_durations_hours_text": repair_durations_text}
                    elif selected_tool["tool_id"] == "T056":
                        current_tool_inputs = {"items_json": inventory_items_json, "currency": inventory_currency, "a_threshold": abc_a_threshold, "b_threshold": abc_b_threshold, "x_cv_max": xyz_x_cutoff, "y_cv_max": xyz_y_cutoff}
                    elif selected_tool["tool_id"] == "T033":
                        current_tool_inputs = {"measurements_json": gage_rr_json, "unit": gage_rr_unit, "tolerance": gage_rr_tolerance}
                    elif selected_tool["tool_id"] == "T036":
                        current_tool_inputs = {"records_json": regression_records_json, "response": regression_response, "predictors": regression_predictors_text}
                    elif selected_tool["tool_id"] == "T037":
                        current_tool_inputs = {"test_type": hypothesis_test_type, "sample_a_text": hypothesis_sample_a, "sample_b_text": hypothesis_sample_b, "null_mean": hypothesis_null_mean, "alpha": hypothesis_alpha}
                    elif selected_tool["tool_id"] == "T049":
                        current_tool_inputs = {"work_orders_json": maintenance_orders_json, "available_hours": maintenance_available_hours, "available_skills": maintenance_skills_text, "due_soon_days": int(maintenance_due_soon_days)}
                    elif selected_tool["tool_id"] == "T058":
                        current_tool_inputs = {"suppliers_json": supplier_records_json, "weights_json": supplier_weights_json}
                    elif selected_tool["tool_id"] == "T015":
                        current_tool_inputs = {"source_columns": field_source_columns, "manual_mapping_json": field_manual_mapping_json, "minimum_confidence": field_minimum_confidence}
                    elif selected_tool["tool_id"] == "T052":
                        current_tool_inputs = {"periods_json": sop_periods_json, "starting_inventory": sop_starting_inventory}
                    elif selected_tool["tool_id"] == "T071":
                        current_tool_inputs = {"process_steps_json": des_steps_json, "job_count": int(des_job_count), "mean_interarrival_time": des_interarrival, "arrival_distribution": des_arrival_distribution, "warmup_jobs": int(des_warmup_jobs), "replications": int(des_replications), "random_seed": int(des_seed), "time_unit": des_time_unit}
                    elif selected_tool["tool_id"] == "T062":
                        current_tool_inputs = {"variables_json": solver_variables_json, "objective_json": solver_objective_json, "constraints_json": solver_constraints_json, "direction": solver_direction, "time_limit_seconds": solver_time_limit, "feasibility_tolerance": solver_tolerance}
                    elif selected_tool["tool_id"] == "T087":
                        current_tool_inputs = {"source_tool_id": source_result_tool_id, "metadata_json": reproducibility_metadata_json, "include_input_snapshot": include_input_snapshot, "include_result_tables": include_result_tables}
                    else:
                        current_tool_inputs = {
                            "cohen_d": effect_size, "alpha": alpha,
                            "target_power": target_power, "maximum_n_per_group": int(search_limit),
                        }

                    if run_method:
                        # Remove only the in-session output before a new run. The last
                        # successful saved workspace snapshot remains intact if this run fails.
                        st.session_state.pop("shoir_tool_result_" + selected_tool["tool_id"], None)
                        st.session_state.pop("shoir_tool_inputs_" + selected_tool["tool_id"], None)
                        st.session_state.pop("shoir_tool_save_status_" + selected_tool["tool_id"], None)
                        try:
                            _require_focused_tool_actor()
                            require_tool_access(RAW_TIER, selected_tool["tool_id"])
                            from shoir_target_engines import (
                                analyze_work_sampling, analyze_pareto_root_cause,
                                assess_5s_audit, build_kaizen_a3_record,
                                calculate_time_study, calculate_takt_capacity,
                                solve_cutting_stock, monitor_forecast_drift,
                                plan_two_sample_t_sample_size, calculate_oee,
                                analyze_process_capability, plan_inventory_policy,
                                calculate_carbon_emissions, analyze_engineering_economics,
                                convert_units_or_currency, analyze_spc_individuals,
                                analyze_quality_cost_defects, analyze_mtbf_mttr,
                                analyze_abc_xyz_inventory,
                                balance_production_line, analyze_bottleneck_capacity,
                                build_value_stream_map, analyze_fmea, analyze_mm1_queue,
                                analyze_industrial_cost_variance, calculate_roi_evidence,
                                plan_preventive_maintenance, assess_job_hazards,
                                plan_material_requirements, score_project_portfolio,
                                merge_data_tables, process_time_series,
                                generate_synthetic_industrial_data, plan_acceptance_sampling,
                                analyze_process_mining, analyze_water_waste_efficiency,
                                analyze_weibull_reliability, analyze_spare_parts_criticality,
                                analyze_safety_incident_trends, optimize_warehouse_slotting,
                                optimize_task_resource_assignment, compare_energy_performance_scenarios,
                                analyze_measurement_system_gage_rr, fit_regression_anova, run_hypothesis_test,
                                prioritize_maintenance_backlog, score_supplier_performance,
                                map_industrial_fields, reconcile_sop_plan, simulate_discrete_event_process,
                                run_solver_diagnostics, build_reproducibility_pack,
                            )
                            if selected_tool["tool_id"] == "T021":
                                try:
                                    observation_times = [float(item.strip()) for item in observation_text.split(",") if item.strip()]
                                except ValueError as exc:
                                    raise ValueError("Observed times must be comma-separated numbers.") from exc
                                result = calculate_time_study(
                                    observation_times, rating, allowance, time_unit=unit,
                                )
                            elif selected_tool["tool_id"] == "T022":
                                parsed_counts = json.loads(work_sampling_counts_json)
                                if not isinstance(parsed_counts, dict):
                                    raise ValueError("Activity counts must be a JSON object mapping category names to counts.")
                                result = analyze_work_sampling(
                                    parsed_counts,
                                    confidence_level=float(confidence_option.rstrip("%")) / 100.0,
                                    target_margin_pct=margin_pct,
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if work_sampling_counts_json.strip() == _TOOL022_EXAMPLE_COUNTS
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                                result["provenance_warning"] = (
                                    "The example counts are synthetic teaching data; replace them and verify the sampling frame before using the output operationally."
                                    if result["data_provenance"] == "SYNTHETIC_EXAMPLE"
                                    else
                                    "Entered counts were not independently validated against a sampling log or plant system."
                                )
                            elif selected_tool["tool_id"] == "T023":
                                result = calculate_takt_capacity(
                                    available_time, demand_units, cycle_time, time_unit=unit,
                                )
                            elif selected_tool["tool_id"] == "T028":
                                parsed_counts = json.loads(pareto_counts_json)
                                if not isinstance(parsed_counts, dict):
                                    raise ValueError("Pareto counts must be a JSON object mapping category names to counts.")
                                whys = [line.strip() for line in why_chain_text.splitlines() if line.strip()]
                                result = analyze_pareto_root_cause(
                                    parsed_counts,
                                    problem_statement=problem_statement,
                                    why_chain=whys,
                                    countermeasure=countermeasure_text,
                                    owner=action_owner,
                                    due_date=action_due_date,
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if pareto_counts_json.strip() == _TOOL028_EXAMPLE_COUNTS
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                                result["provenance_warning"] = (
                                    "The example counts are synthetic teaching data; replace them and verify the source before operational use."
                                    if result["data_provenance"] == "SYNTHETIC_EXAMPLE"
                                    else
                                    "Entered counts were not independently validated against a source log."
                                )
                            elif selected_tool["tool_id"] == "T029":
                                parsed_items = json.loads(audit_items_json)
                                if not isinstance(parsed_items, list):
                                    raise ValueError("5S checklist must be a JSON list of item objects.")
                                result = assess_5s_audit(parsed_items)
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if audit_items_json.strip() == _TOOL029_EXAMPLE_ITEMS
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                                result["provenance_warning"] = (
                                    "The displayed checklist is illustrative self-assessment data, not a completed plant audit."
                                    if result["data_provenance"] == "SYNTHETIC_EXAMPLE"
                                    else "Checklist evidence was not independently validated against a signed audit."
                                )
                            elif selected_tool["tool_id"] == "T030":
                                result = build_kaizen_a3_record(
                                    title=a3_title,
                                    problem_statement=a3_problem,
                                    metric_name=a3_metric,
                                    unit=a3_unit,
                                    baseline_value=a3_baseline,
                                    target_value=a3_target,
                                    actual_after_value=a3_actual,
                                    root_cause_hypothesis=a3_root_cause,
                                    countermeasure=a3_countermeasure,
                                    owner=a3_owner,
                                    due_date=a3_due_date,
                                    baseline_evidence=a3_baseline_evidence,
                                    post_change_evidence=a3_post_evidence,
                                    implementation_status=a3_status,
                                    review_date=a3_review_date,
                                )
                                result["data_provenance"] = "USER_ENTERED_UNVERIFIED"
                                records = st.session_state.get("shoir_kaizen_a3_records", [])
                                if not isinstance(records, list):
                                    raise ValueError("The saved A3 register is invalid; existing workspace data was preserved.")
                                record_id = str(record_id_input or "").strip()
                                now = datetime.now().astimezone().isoformat(timespec="seconds")
                                known_index = next((i for i, item in enumerate(records) if str(item.get("record_id", "")) == record_id), None) if record_id else None
                                if record_id and known_index is None:
                                    raise ValueError("A3 record ID was not found in this user's workspace. Leave it blank to create a new record.")
                                if known_index is None:
                                    if len(records) >= 500:
                                        raise ValueError("The A3 register reached 500 records; archive records before adding more.")
                                    record_id = "A3-" + uuid4().hex[:10].upper()
                                    result["record_id"] = record_id
                                    result["created_at"] = now
                                    result["updated_at"] = now
                                    result["revision_number"] = 1
                                    result["revision_history"] = []
                                    records.append(dict(result))
                                else:
                                    previous = dict(records[known_index])
                                    history = list(previous.get("revision_history", []))
                                    snapshot_keys = (
                                        "title", "problem_statement", "metric_name", "unit",
                                        "baseline_value", "target_value", "actual_after_value",
                                        "root_cause_hypothesis", "countermeasure", "owner", "due_date",
                                        "baseline_evidence", "post_change_evidence", "review_date",
                                        "status", "outcome_status",
                                    )
                                    history.append({
                                        "revision_number": int(previous.get("revision_number", 1)),
                                        "updated_at": previous.get("updated_at", previous.get("created_at", "")),
                                        "snapshot": {key: previous.get(key) for key in snapshot_keys},
                                    })
                                    result["record_id"] = record_id
                                    result["created_at"] = previous.get("created_at", now)
                                    result["updated_at"] = now
                                    result["revision_number"] = int(previous.get("revision_number", 1)) + 1
                                    result["revision_history"] = history
                                    records[known_index] = dict(result)
                                st.session_state["shoir_kaizen_a3_records"] = records
                            elif selected_tool["tool_id"] == "T059":
                                parsed_slot_items = json.loads(slotting_items_json)
                                parsed_slots = json.loads(slotting_slots_json)
                                if not isinstance(parsed_slot_items, list) or not isinstance(parsed_slots, list):
                                    raise ValueError("Slotting items and slots must each be JSON lists.")
                                result = optimize_warehouse_slotting(parsed_slot_items, parsed_slots)
                            elif selected_tool["tool_id"] == "T063":
                                parsed_assignment_tasks = json.loads(assignment_tasks_json)
                                parsed_assignment_resources = json.loads(assignment_resources_json)
                                parsed_assignment_costs = json.loads(assignment_costs_json)
                                if not isinstance(parsed_assignment_tasks, list) or not isinstance(parsed_assignment_resources, list) or not isinstance(parsed_assignment_costs, list):
                                    raise ValueError("Task names, resource names and cost matrix must each be JSON lists.")
                                result = optimize_task_resource_assignment(parsed_assignment_tasks, parsed_assignment_resources, parsed_assignment_costs)
                            elif selected_tool["tool_id"] == "T066":
                                parsed_parts = json.loads(parts_json)
                                if not isinstance(parsed_parts, list):
                                    raise ValueError("Parts input must be a JSON list of part definitions.")
                                result = solve_cutting_stock(stock_len, parsed_parts, kerf)
                            elif selected_tool["tool_id"] == "T075":
                                try:
                                    predictions = [float(x.strip()) for x in predictions_text.split(",") if x.strip()]
                                    actuals = [float(x.strip()) for x in actuals_text.split(",") if x.strip()]
                                except ValueError as exc:
                                    raise ValueError("Predictions and actuals must be comma-separated numbers.") from exc
                                result = monitor_forecast_drift(
                                    predictions, actuals, max_mae,
                                    window=int(window) if int(window) > 0 else None,
                                )
                            elif selected_tool["tool_id"] == "T026":
                                result = calculate_oee(oee_planned, oee_downtime, oee_cycle, oee_total, oee_good, time_unit=oee_unit)
                            elif selected_tool["tool_id"] == "T032":
                                try:
                                    measured_values = [float(x.strip()) for x in capability_measurements.split(",") if x.strip()]
                                except ValueError as exc:
                                    raise ValueError("Measurements must be comma-separated numbers.") from exc
                                result = analyze_process_capability(measured_values, capability_lsl, capability_usl, subgroup_size=int(capability_subgroup), unit=capability_unit)
                            elif selected_tool["tool_id"] == "T055":
                                result = plan_inventory_policy(inv_demand, inv_sd, inv_lead, inv_order_cost, inv_holding_cost, operating_days_per_year=int(inv_days), service_factor_z=service_options[inv_service])
                            elif selected_tool["tool_id"] == "T078":
                                result = calculate_carbon_emissions(carbon_amount, carbon_factor, activity_unit=carbon_unit, factor_unit=carbon_factor_unit, factor_source=carbon_source, factor_date=carbon_date, boundary=carbon_boundary)
                            elif selected_tool["tool_id"] == "T081":
                                try:
                                    cash_flows = [float(x.strip()) for x in economics_cash_flows.split(",") if x.strip()]
                                except ValueError as exc:
                                    raise ValueError("Cash flows must be comma-separated numbers.") from exc
                                result = analyze_engineering_economics(cash_flows, economics_rate, currency=economics_currency, period_unit=economics_period)
                            elif selected_tool["tool_id"] == "T016":
                                result = convert_units_or_currency(amount_to_convert, source_unit, target_unit, exchange_rate=exchange_rate_value, exchange_rate_date=exchange_rate_date_value, exchange_rate_source=exchange_rate_source_value)
                            elif selected_tool["tool_id"] == "T031":
                                try:
                                    values = [float(item.strip()) for item in spc_measurements_text.split(",") if item.strip()]
                                except ValueError as exc:
                                    raise ValueError("SPC measurements must be comma-separated numbers.") from exc
                                result = analyze_spc_individuals(values, unit=spc_unit)
                            elif selected_tool["tool_id"] == "T040":
                                result = analyze_quality_cost_defects(quality_total_units, quality_defects, quality_scrap_units, quality_rework_units, quality_scrap_cost, quality_rework_cost, quality_inspection_cost, currency=quality_currency, period=quality_period)
                            elif selected_tool["tool_id"] == "T042":
                                try:
                                    durations = [float(item.strip()) for item in repair_durations_text.split(",") if item.strip()]
                                except ValueError as exc:
                                    raise ValueError("Repair durations must be comma-separated numbers.") from exc
                                result = analyze_mtbf_mttr(mtbf_operating_hours, durations)
                            elif selected_tool["tool_id"] == "T056":
                                inventory_items = json.loads(inventory_items_json)
                                if not isinstance(inventory_items, list):
                                    raise ValueError("SKU data must be a JSON list of objects.")
                                result = analyze_abc_xyz_inventory(inventory_items, a_threshold=abc_a_threshold, b_threshold=abc_b_threshold, x_cv_max=xyz_x_cutoff, y_cv_max=xyz_y_cutoff, currency=inventory_currency)
                            elif selected_tool["tool_id"] == "T024":
                                parsed_tasks = json.loads(line_tasks_json)
                                if not isinstance(parsed_tasks, list):
                                    raise ValueError("Tasks input must be a JSON list of task objects.")
                                result = balance_production_line(parsed_tasks, line_cycle_time, time_unit=line_time_unit)
                            elif selected_tool["tool_id"] == "T025":
                                parsed_processes = json.loads(bottleneck_processes_json)
                                if not isinstance(parsed_processes, list):
                                    raise ValueError("Process capacities must be a JSON list of process objects.")
                                result = analyze_bottleneck_capacity(parsed_processes, bottleneck_demand, period_label=bottleneck_period)
                            elif selected_tool["tool_id"] == "T027":
                                parsed_steps = json.loads(vsm_steps_json)
                                if not isinstance(parsed_steps, list):
                                    raise ValueError("Value-stream steps must be a JSON list of step objects.")
                                result = build_value_stream_map(parsed_steps, vsm_demand, vsm_available_time, time_unit=vsm_time_unit)
                            elif selected_tool["tool_id"] == "T038":
                                parsed_fmea = json.loads(fmea_json)
                                if not isinstance(parsed_fmea, list):
                                    raise ValueError("FMEA input must be a JSON list of failure-mode objects.")
                                result = analyze_fmea(parsed_fmea)
                            elif selected_tool["tool_id"] == "T070":
                                result = analyze_mm1_queue(queue_arrival_rate, queue_service_rate, time_unit=queue_time_unit)
                            elif selected_tool["tool_id"] == "T082":
                                result = analyze_industrial_cost_variance(cost_standard_qty_per_unit, cost_actual_output, cost_actual_input, cost_standard_price, cost_actual_price, currency=cost_currency, period=cost_period)
                            elif selected_tool["tool_id"] == "T083":
                                result = calculate_roi_evidence(roi_baseline, roi_post, roi_implementation, currency=roi_currency, measurement_window=roi_window, baseline_evidence=roi_baseline_evidence, outcome_evidence=roi_outcome_evidence, verifier=roi_verifier)
                            elif selected_tool["tool_id"] == "T017":
                                parsed_left = json.loads(join_left_json)
                                parsed_right = json.loads(join_right_json)
                                if not isinstance(parsed_left, list) or not isinstance(parsed_right, list):
                                    raise ValueError("Both join inputs must be JSON lists of records.")
                                result = merge_data_tables(parsed_left, parsed_right, join_left_key, join_right_key, join_type=join_type, duplicate_policy=duplicate_policy)
                            elif selected_tool["tool_id"] == "T018":
                                parsed_series = json.loads(time_series_json)
                                if not isinstance(parsed_series, list):
                                    raise ValueError("Time-series input must be a JSON list of records.")
                                result = process_time_series(parsed_series, ts_column, timezone_name=ts_timezone, expected_interval=ts_expected_interval, resample_frequency=ts_resample_frequency, aggregation=ts_aggregation)
                            elif selected_tool["tool_id"] == "T019":
                                result = generate_synthetic_industrial_data(int(synthetic_rows), seed=int(synthetic_seed), start_timestamp=synthetic_start, interval_minutes=int(synthetic_interval), defect_rate_pct=synthetic_defect_rate, mean_downtime_minutes=synthetic_downtime, energy_kwh_per_unit=synthetic_energy)
                            elif selected_tool["tool_id"] == "T034":
                                result = plan_acceptance_sampling(sampling_aql / 100.0, sampling_ltpd / 100.0, producer_risk=sampling_alpha / 100.0, consumer_risk=sampling_beta / 100.0, max_sample_size=int(sampling_max_n))
                            elif selected_tool["tool_id"] == "T041":
                                parsed_failure_times = json.loads(weibull_times_json)
                                if not isinstance(parsed_failure_times, list):
                                    raise ValueError("Failure-time observations must be a JSON list.")
                                result = analyze_weibull_reliability(parsed_failure_times)
                            elif selected_tool["tool_id"] == "T043":
                                parsed_pm_tasks = json.loads(pm_tasks_json)
                                if not isinstance(parsed_pm_tasks, list):
                                    raise ValueError("Maintenance tasks must be a JSON list of task objects.")
                                result = plan_preventive_maintenance(parsed_pm_tasks, pm_as_of_date)
                            elif selected_tool["tool_id"] == "T045":
                                parsed_parts = json.loads(spare_parts_json)
                                if not isinstance(parsed_parts, list):
                                    raise ValueError("Spare parts must be a JSON list of part objects.")
                                result = analyze_spare_parts_criticality(parsed_parts)
                            elif selected_tool["tool_id"] == "T047":
                                parsed_hazards = json.loads(hazard_json)
                                if not isinstance(parsed_hazards, list):
                                    raise ValueError("Hazards must be a JSON list of hazard objects.")
                                result = assess_job_hazards(parsed_hazards)
                            elif selected_tool["tool_id"] == "T050":
                                parsed_safety_periods = json.loads(safety_periods_json)
                                if not isinstance(parsed_safety_periods, list):
                                    raise ValueError("Safety periods must be a JSON list of period objects.")
                                result = analyze_safety_incident_trends(parsed_safety_periods, rate_base_hours=safety_rate_base)
                            elif selected_tool["tool_id"] == "T054":
                                parsed_bom = json.loads(mrp_bom_json)
                                parsed_inventory = json.loads(mrp_inventory_json)
                                if not isinstance(parsed_bom, list):
                                    raise ValueError("BOM must be a JSON list of component objects.")
                                if not isinstance(parsed_inventory, dict):
                                    raise ValueError("Inventory must be a JSON object keyed by component.")
                                result = plan_material_requirements(parsed_bom, mrp_parent_demand, inventory=parsed_inventory, due_period=int(mrp_due_period))
                            elif selected_tool["tool_id"] == "T076":
                                parsed_events = json.loads(process_event_log_json)
                                if not isinstance(parsed_events, list):
                                    raise ValueError("Event log must be a JSON list of event records.")
                                result = analyze_process_mining(parsed_events)
                            elif selected_tool["tool_id"] == "T077":
                                parsed_energy_baseline = json.loads(energy_baseline_json)
                                parsed_energy_alternatives = json.loads(energy_alternatives_json)
                                if not isinstance(parsed_energy_baseline, dict) or not isinstance(parsed_energy_alternatives, list):
                                    raise ValueError("Energy baseline must be a JSON object and alternatives must be a JSON list.")
                                result = compare_energy_performance_scenarios(parsed_energy_baseline, parsed_energy_alternatives)
                            elif selected_tool["tool_id"] == "T079":
                                parsed_flows = json.loads(water_flows_json)
                                if not isinstance(parsed_flows, list):
                                    raise ValueError("Process flows must be a JSON list of flow records.")
                                result = analyze_water_waste_efficiency(parsed_flows)
                            elif selected_tool["tool_id"] == "T084":
                                parsed_criteria = json.loads(portfolio_criteria_json)
                                parsed_alternatives = json.loads(portfolio_alternatives_json)
                                if not isinstance(parsed_criteria, list) or not isinstance(parsed_alternatives, list):
                                    raise ValueError("Portfolio criteria and alternatives must each be JSON lists.")
                                result = score_project_portfolio(parsed_criteria, parsed_alternatives)
                            elif selected_tool["tool_id"] == "T085":
                                result = plan_two_sample_t_sample_size(
                                    effect_size, alpha, target_power,
                                    max_n_per_group=int(search_limit),
                                )
                            elif selected_tool["tool_id"] == "T033":
                                parsed_measurements = json.loads(gage_rr_json)
                                if not isinstance(parsed_measurements, list):
                                    raise ValueError("Measurements must be a JSON list of reading objects.")
                                result = analyze_measurement_system_gage_rr(
                                    parsed_measurements, tolerance=gage_rr_tolerance, unit=gage_rr_unit
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if gage_rr_json.strip() == _TOOL033_EXAMPLE_MEASUREMENTS
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                            elif selected_tool["tool_id"] == "T036":
                                parsed_regression_records = json.loads(regression_records_json)
                                parsed_predictors = [name.strip() for name in regression_predictors_text.split(",") if name.strip()]
                                if not isinstance(parsed_regression_records, list):
                                    raise ValueError("Regression observations must be a JSON list of objects.")
                                result = fit_regression_anova(
                                    parsed_regression_records, regression_response, parsed_predictors
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if regression_records_json.strip() == _TOOL036_EXAMPLE_RECORDS
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                            elif selected_tool["tool_id"] == "T037":
                                def _parse_test_values(raw: str, label: str) -> list[float]:
                                    try:
                                        values = [float(part.strip()) for part in raw.split(",") if part.strip()]
                                    except ValueError as exc:
                                        raise ValueError(f"{label} must be comma-separated numeric values.") from exc
                                    if not values:
                                        raise ValueError(f"Provide at least two values for {label}.")
                                    return values
                                parsed_sample_a = _parse_test_values(hypothesis_sample_a, "Sample A")
                                parsed_sample_b = _parse_test_values(hypothesis_sample_b, "Sample B") if hypothesis_test_type != "one_sample_t" else None
                                result = run_hypothesis_test(
                                    hypothesis_test_type, parsed_sample_a, parsed_sample_b,
                                    null_mean=hypothesis_null_mean, alpha=hypothesis_alpha,
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if hypothesis_sample_a.strip() == _TOOL037_EXAMPLE_SAMPLE_A
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                            elif selected_tool["tool_id"] == "T049":
                                parsed_work_orders = json.loads(maintenance_orders_json)
                                if not isinstance(parsed_work_orders, list):
                                    raise ValueError("Maintenance work orders must be a JSON list of objects.")
                                skills = [skill.strip() for skill in maintenance_skills_text.split(",") if skill.strip()]
                                result = prioritize_maintenance_backlog(
                                    parsed_work_orders, maintenance_available_hours,
                                    available_skills=skills,
                                    due_soon_days=int(maintenance_due_soon_days),
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if maintenance_orders_json.strip() == _TOOL049_EXAMPLE_WORK_ORDERS
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                            elif selected_tool["tool_id"] == "T058":
                                parsed_suppliers = json.loads(supplier_records_json)
                                parsed_weights = json.loads(supplier_weights_json)
                                if not isinstance(parsed_suppliers, list) or not isinstance(parsed_weights, dict):
                                    raise ValueError("Supplier records must be a JSON list and criterion weights must be a JSON object.")
                                result = score_supplier_performance(parsed_suppliers, parsed_weights)
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if supplier_records_json.strip() == _TOOL058_EXAMPLE_SUPPLIERS
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                            elif selected_tool["tool_id"] == "T015":
                                source_columns = [column.strip() for column in field_source_columns.split(",")]
                                parsed_manual_mapping = json.loads(field_manual_mapping_json)
                                if not isinstance(parsed_manual_mapping, dict):
                                    raise ValueError("Manual field mapping must be a JSON object from source header to canonical field ID.")
                                result = map_industrial_fields(
                                    source_columns,
                                    manual_mapping=parsed_manual_mapping,
                                    minimum_confidence=field_minimum_confidence,
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if field_source_columns.strip() == _TOOL015_EXAMPLE_COLUMNS and not parsed_manual_mapping
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                            elif selected_tool["tool_id"] == "T052":
                                parsed_sop_periods = json.loads(sop_periods_json)
                                if not isinstance(parsed_sop_periods, list):
                                    raise ValueError("S&OP periods must be a JSON list of period records.")
                                result = reconcile_sop_plan(
                                    parsed_sop_periods,
                                    starting_inventory=sop_starting_inventory,
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if sop_periods_json.strip() == _TOOL052_EXAMPLE_PERIODS
                                    else "USER_ENTERED_UNVERIFIED"
                                )
                            elif selected_tool["tool_id"] == "T071":
                                parsed_des_steps = json.loads(des_steps_json)
                                if not isinstance(parsed_des_steps, list):
                                    raise ValueError("DES station setup must be a JSON list of station records.")
                                result = simulate_discrete_event_process(
                                    parsed_des_steps,
                                    job_count=int(des_job_count),
                                    mean_interarrival_time=des_interarrival,
                                    arrival_distribution=des_arrival_distribution,
                                    warmup_jobs=int(des_warmup_jobs),
                                    replications=int(des_replications),
                                    random_seed=int(des_seed),
                                    time_unit=des_time_unit,
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if des_steps_json.strip() == _TOOL071_EXAMPLE_STATIONS
                                    and int(des_job_count) == 50
                                    and float(des_interarrival) == 1.0
                                    and des_arrival_distribution == "deterministic"
                                    and int(des_warmup_jobs) == 5
                                    and int(des_replications) == 10
                                    and int(des_seed) == 42
                                    and des_time_unit == "minutes"
                                    else "MODELLED_FROM_USER_ASSUMPTIONS"
                                )
                            elif selected_tool["tool_id"] == "T062":
                                parsed_solver_variables = json.loads(solver_variables_json)
                                parsed_solver_objective = json.loads(solver_objective_json)
                                parsed_solver_constraints = json.loads(solver_constraints_json)
                                if not isinstance(parsed_solver_variables, dict) or not isinstance(parsed_solver_objective, dict) or not isinstance(parsed_solver_constraints, list):
                                    raise ValueError("Variables and objective must be JSON objects, and constraints must be a JSON list.")
                                result = run_solver_diagnostics(
                                    parsed_solver_variables,
                                    parsed_solver_objective,
                                    parsed_solver_constraints,
                                    direction=solver_direction,
                                    time_limit_seconds=solver_time_limit,
                                    feasibility_tolerance=solver_tolerance,
                                )
                                result["data_provenance"] = (
                                    "SYNTHETIC_EXAMPLE"
                                    if solver_variables_json.strip() == _TOOL062_EXAMPLE_VARIABLES
                                    and solver_objective_json.strip() == _TOOL062_EXAMPLE_OBJECTIVE
                                    and solver_constraints_json.strip() == _TOOL062_EXAMPLE_CONSTRAINTS
                                    and solver_direction == "minimize"
                                    else "MODELLED_FROM_USER_ASSUMPTIONS"
                                )
                            elif selected_tool["tool_id"] == "T087":
                                if source_result_tool_id == "NONE":
                                    raise ValueError("Run an entitled source tool first; no completed result is available to package.")
                                source_tool = require_tool_access(RAW_TIER, source_result_tool_id)
                                source_result = st.session_state.get("shoir_tool_result_" + source_result_tool_id)
                                if not isinstance(source_result, dict):
                                    raise ValueError("The selected source result is no longer available in this session; rerun the source tool.")
                                try:
                                    parsed_repro_metadata = json.loads(reproducibility_metadata_json or "{}")
                                except json.JSONDecodeError as exc:
                                    raise ValueError("Run metadata must be valid JSON.") from exc
                                if not isinstance(parsed_repro_metadata, dict):
                                    raise ValueError("Run metadata must be a JSON object.")
                                source_inputs = st.session_state.get("shoir_tool_inputs_" + source_result_tool_id, {})
                                pack_result = build_reproducibility_pack(
                                    source_result_tool_id,
                                    source_tool["canonical_name"],
                                    source_result,
                                    inputs=source_inputs if isinstance(source_inputs, dict) else {},
                                    metadata=parsed_repro_metadata,
                                    include_input_snapshot=include_input_snapshot,
                                    include_result_tables=include_result_tables,
                                )
                                st.session_state["shoir_tool_bundle_bytes_T087"] = pack_result.pop("bundle_bytes")
                                result = pack_result
                            _persist_focused_tool_result(
                                selected_tool["tool_id"], result, current_tool_inputs
                            )
                        except Exception as exc:
                            st.error(f"Tool run could not be completed safely: {exc}")

                    if selected_tool["tool_id"] in {"T015", "T017", "T018", "T019", "T024", "T025", "T027", "T033", "T034", "T036", "T037", "T038", "T041", "T043", "T045", "T047", "T049", "T050", "T052", "T054", "T058", "T059", "T062", "T063", "T070", "T071", "T076", "T077", "T079", "T082", "T083", "T084"}:
                        result = st.session_state.get("shoir_tool_result_" + selected_tool["tool_id"])
                        if result:
                            _show_focused_tool_persistence(selected_tool["tool_id"], result, current_tool_inputs)
                            render_engineering_result(
                                result,
                                title=selected_tool["canonical_name"],
                                key_prefix="target_" + selected_tool["tool_id"].lower(),
                            )
                    elif selected_tool["tool_id"] == "T087":
                        result = st.session_state.get("shoir_tool_result_T087")
                        bundle_bytes = st.session_state.get("shoir_tool_bundle_bytes_T087")
                        if result:
                            _show_focused_tool_persistence("T087", result, current_tool_inputs)
                            st.metric("ZIP bundle size", f"{int(result.get('bundle_byte_count', 0)):,} bytes")
                            st.code(result.get("bundle_sha256", ""))
                            st.caption("Verify SHA-256 checksums in SHA256SUMS.txt. Review contents before sharing; tables and input snapshots are opt-in.")
                            if isinstance(bundle_bytes, bytes) and bundle_bytes:
                                st.download_button(
                                    "Download reproducibility ZIP",
                                    data=bundle_bytes,
                                    file_name=result.get("filename", "shoir_ie_reproducibility_pack.zip"),
                                    mime="application/zip",
                                    key="tool087_download",
                                    use_container_width=True,
                                )
                            inventory = result.get("artifact_inventory")
                            if isinstance(inventory, pd.DataFrame):
                                st.dataframe(inventory, use_container_width=True, hide_index=True)
                            st.json(result.get("manifest", {}))
                    elif selected_tool["tool_id"] == "T016":
                        result = st.session_state.get("shoir_tool_result_T016")
                        if result:
                            _show_focused_tool_persistence("T016", result, current_tool_inputs)
                            st.metric(f"Converted value ({result['target_unit']})", f"{result['converted_value']:,.8g}")
                            st.markdown(f"**Source value:** {result['input_value']:,.8g} {result['source_unit']}")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            if result.get("exchange_rate_date"):
                                st.caption(f"Rate source: {result['exchange_rate_source']} · rate date: {result['exchange_rate_date']} · rate direction: target per source")
                    elif selected_tool["tool_id"] == "T031":
                        result = st.session_state.get("shoir_tool_result_T031")
                        if result:
                            _show_focused_tool_persistence("T031", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Process mean", f"{result['mean']:,.5g} {result['unit']}")
                            c2.metric("Moving-range average", f"{result['moving_range_average']:,.5g}")
                            c3.metric("I-chart UCL / LCL", f"{result['individuals_ucl']:,.5g} / {result['individuals_lcl']:,.5g}")
                            st.markdown(f"**Signal status:** {result['status']}")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            st.dataframe(result["chart_data"], use_container_width=True, hide_index=True)
                            chart = result["chart_data"]
                            st.plotly_chart(px.line(chart, x="Observation", y=[f"Measurement ({result['unit']})", f"I center ({result['unit']})", f"I UCL ({result['unit']})", f"I LCL ({result['unit']})"], markers=True, title="Individuals control chart"), use_container_width=True)
                            st.plotly_chart(px.line(chart, x="Observation", y=["Moving range", "MR center", "MR UCL", "MR LCL"], markers=True, title="Moving-range control chart"), use_container_width=True)
                    elif selected_tool["tool_id"] == "T040":
                        result = st.session_state.get("shoir_tool_result_T040")
                        if result:
                            _show_focused_tool_persistence("T040", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric(f"Scoped COPQ ({result['currency']})", f"{result['cost_of_poor_quality']:,.2f}")
                            c2.metric("Defective-unit rate", f"{result['defective_rate_pct']:.2f}%")
                            c3.metric(f"COPQ per unit ({result['currency']})", f"{result['copq_per_produced_unit']:,.3f}")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            st.dataframe(result["cost_breakdown"], use_container_width=True, hide_index=True)
                            st.plotly_chart(px.bar(result["cost_breakdown"], x="Cost component", y=f"Cost ({result['currency']})", title="Scoped quality-cost components"), use_container_width=True)
                    elif selected_tool["tool_id"] == "T042":
                        result = st.session_state.get("shoir_tool_result_T042")
                        if result:
                            _show_focused_tool_persistence("T042", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("MTBF", f"{result['mtbf_hours']:,.3f} h")
                            c2.metric("MTTR", f"{result['mttr_hours']:,.3f} h")
                            c3.metric("Availability estimate", f"{result['steady_state_availability_estimate_pct']:.3f}%")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            st.dataframe(result["repair_summary"], use_container_width=True, hide_index=True)
                    elif selected_tool["tool_id"] == "T056":
                        result = st.session_state.get("shoir_tool_result_T056")
                        if result:
                            _show_focused_tool_persistence("T056", result, current_tool_inputs)
                            c1, c2 = st.columns(2)
                            c1.metric("SKUs classified", str(result["sku_count"]))
                            c2.metric(f"Total annual usage value ({result['currency']})", f"{result['annual_usage_value_total']:,.2f}")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            st.dataframe(result["classification"], use_container_width=True, hide_index=True)
                            value_column = f"Annual usage value ({result['currency']})"
                            st.plotly_chart(px.bar(result["classification"], x="SKU", y=value_column, color="ABC", title="ABC value segmentation"), use_container_width=True)
                    elif selected_tool["tool_id"] == "T021":
                        result = st.session_state.get("shoir_tool_result_T021")
                        if result:
                            _show_focused_tool_persistence("T021", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric(f"Mean observed time ({result['time_unit']})", f"{result['mean_observed_time']:,.4g}")
                            c2.metric(f"Normal time ({result['time_unit']})", f"{result['normal_time']:,.4g}")
                            c3.metric(f"Standard time ({result['time_unit']})", f"{result['standard_time']:,.4g}")
                            st.caption(result["formula"])
                            st.caption(result["warning"])
                            st.dataframe(result["observations"], use_container_width=True, hide_index=True)
                            fig = px.line(
                                result["observations"],
                                x="Observation", y=f"Observed time ({result['time_unit']})",
                                markers=True, title="Observed cycle times",
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    elif selected_tool["tool_id"] == "T022":
                        result = st.session_state.get("shoir_tool_result_T022")
                        if result:
                            _show_focused_tool_persistence("T022", result, current_tool_inputs)
                            total_obs = result["total_observations"]
                            required_obs = result["minimum_observations_for_target_margin"]
                            confidence_pct = result["confidence_level"] * 100
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Observed samples", f"{total_obs:,}")
                            c2.metric("Conservative target", f"{required_obs:,}")
                            c3.metric("Confidence", f"{confidence_pct:.0f}%")
                            st.markdown(f"**Sampling status:** {result['status']}")
                            st.caption(result["formula"])
                            st.caption(result["assumptions"])
                            st.caption(result["warning"])
                            st.warning(result["provenance_warning"]) if result["data_provenance"] == "SYNTHETIC_EXAMPLE" else st.caption(result["provenance_warning"])
                            df = result["activity_summary"]
                            st.dataframe(df, use_container_width=True, hide_index=True)
                            low_col = f"{confidence_pct:.1f}% Wilson lower (%)"
                            high_col = f"{confidence_pct:.1f}% Wilson upper (%)"
                            df = df.copy()
                            df["Error above (%)"] = df[high_col] - df["Observed proportion (%)"]
                            df["Error below (%)"] = df["Observed proportion (%)"] - df[low_col]
                            fig = px.bar(
                                df, x="Activity", y="Observed proportion (%)",
                                error_y="Error above (%)", error_y_minus="Error below (%)",
                                title="Observed activity proportions with Wilson intervals",
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    elif selected_tool["tool_id"] == "T023":
                        result = st.session_state.get("shoir_tool_result_T023")
                        if result:
                            _show_focused_tool_persistence("T023", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric(f"Takt time ({result['time_unit']}/unit)", f"{result['takt_time_per_unit']:,.4g}")
                            c2.metric("Implied capacity (units/period)", f"{result['implied_capacity_units_per_period']:,.4g}")
                            c3.metric("Capacity gap (units/period)", f"{result['capacity_gap_units_per_period']:+,.4g}")
                            st.markdown(f"**Capacity status:** {result['status']}")
                            st.caption(result["formula"])
                            st.caption(result["assumptions"])
                            comparison = pd.DataFrame({
                                "Measure": ["Demand", "Implied capacity"],
                                "Units per period": [result["demand_units_per_period"], result["implied_capacity_units_per_period"]],
                            })
                            st.dataframe(comparison, use_container_width=True, hide_index=True)
                            st.plotly_chart(
                                px.bar(comparison, x="Measure", y="Units per period", title="Demand versus implied capacity"),
                                use_container_width=True,
                            )
                    elif selected_tool["tool_id"] == "T028":
                        result = st.session_state.get("shoir_tool_result_T028")
                        if result:
                            _show_focused_tool_persistence("T028", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Total recorded occurrences", f"{result['total_count']:,}")
                            c2.metric("Recorded categories", str(result["category_count"]))
                            c3.metric("Categories reaching 80%", str(result["categories_to_reach_80_percent"]))
                            st.markdown(f"**Analysis status:** {result['status']}")
                            st.caption(result["formula"])
                            st.warning(result["provenance_warning"]) if result["data_provenance"] == "SYNTHETIC_EXAMPLE" else st.caption(result["provenance_warning"])
                            st.warning(result["warning"])
                            pareto = result["pareto_summary"]
                            st.dataframe(pareto, use_container_width=True, hide_index=True)
                            st.plotly_chart(
                                px.bar(pareto, x="Category", y="Count", title="Pareto category counts"),
                                use_container_width=True,
                            )
                            if result["why_chain"]:
                                st.markdown("**Recorded 5-Why chain (requires evidence review)**")
                                st.dataframe(pd.DataFrame(result["why_chain"]), use_container_width=True, hide_index=True)
                                st.markdown(f"**Problem:** {result['problem_statement']}")
                                st.markdown(f"**Countermeasure:** {result['countermeasure'] or 'Not yet recorded'}")
                                st.markdown(f"**Owner:** {result['owner'] or 'Not yet assigned'}")
                                st.markdown(f"**Due date:** {result['due_date'] or 'Not yet set'}")
                    elif selected_tool["tool_id"] == "T029":
                        result = st.session_state.get("shoir_tool_result_T029")
                        if result:
                            _show_focused_tool_persistence("T029", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Overall 5S score (equal pillar weight)", f"{result['overall_5s_score_pct_equal_pillar_weight']:.1f}%")
                            c2.metric("Checklist criteria", str(result["criteria_count"]))
                            c3.metric("Priority actions", str(result["priority_action_count"]))
                            st.markdown(f"**Audit status:** {result['status']}")
                            st.caption(result["rubric"])
                            st.caption(result["formula"])
                            st.warning(result["provenance_warning"]) if result["data_provenance"] == "SYNTHETIC_EXAMPLE" else st.caption(result["provenance_warning"])
                            st.warning(result["warning"])
                            st.dataframe(result["pillar_summary"], use_container_width=True, hide_index=True)
                            st.markdown("**Checklist**")
                            st.dataframe(result["checklist"], use_container_width=True, hide_index=True)
                            if len(result["priority_actions"]):
                                st.markdown("**Items requiring follow-up**")
                                st.dataframe(result["priority_actions"], use_container_width=True, hide_index=True)
                    elif selected_tool["tool_id"] == "T030":
                        result = st.session_state.get("shoir_tool_result_T030")
                        if result:
                            _show_focused_tool_persistence("T030", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("A3 record", result.get("record_id", "Pending"))
                            c2.metric("Revision", str(result.get("revision_number", 1)))
                            c3.metric("Status", result["status"])
                            st.markdown(f"**Problem:** {result['problem_statement']}")
                            st.markdown(f"**Countermeasure:** {result['countermeasure']}")
                            st.markdown(f"**Owner / due date:** {result['owner']} / {result['due_date']}")
                            st.markdown(f"**Baseline → target:** {result['baseline_value']} → {result['target_value']} {result['unit']}")
                            if result["actual_after_value"] is not None:
                                st.markdown(f"**Actual after change:** {result['actual_after_value']} {result['unit']}")
                                st.metric("Algebraic progress to target", f"{result['target_progress_pct']:.1f}%")
                                st.caption(f"Signed remaining difference (target − actual): {result['remaining_difference_to_target']:,.4g} {result['unit']}")
                            st.caption(result["assumptions"])
                            st.warning(result["warning"])
                            records = st.session_state.get("shoir_kaizen_a3_records", [])
                            if records:
                                st.markdown("**Saved A3 register (current workspace)**")
                                overview = [{
                                    "Record ID": item.get("record_id"),
                                    "Title": item.get("title"),
                                    "Status": item.get("status"),
                                    "Owner": item.get("owner"),
                                    "Due date": item.get("due_date"),
                                    "Revision": item.get("revision_number", 1),
                                    "Updated at": item.get("updated_at", item.get("created_at", "")),
                                } for item in records]
                                st.dataframe(pd.DataFrame(overview), use_container_width=True, hide_index=True)
                                if result.get("revision_history"):
                                    st.markdown("**Prior revisions**")
                                    st.dataframe(pd.DataFrame(result["revision_history"]), use_container_width=True, hide_index=True)
                    elif selected_tool["tool_id"] == "T066":
                        result = st.session_state.get("shoir_tool_result_T066")
                        if result:
                            _show_focused_tool_persistence("T066", result, current_tool_inputs)
                            st.markdown(f"**Solver status:** {result['status']}")
                            st.caption(result.get("message", ""))
                            if result.get("status") == "OPTIMAL":
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Stock pieces", f"{result['stock_count']:,}")
                                c2.metric("Physical utilization", f"{result['physical_utilization_pct']:.1f}%")
                                c3.metric("Calculated waste", f"{result['waste_length']:,.3f}")
                                st.dataframe(result["cut_plan"], use_container_width=True, hide_index=True)
                                if not result["cut_plan"].empty:
                                    fig = px.bar(
                                        result["cut_plan"], x="Pattern", y="Stocks",
                                        title="Optimal cutting-pattern allocation",
                                        hover_data=["Part mix", "Pieces per stock", "Waste per stock"],
                                    )
                                    st.plotly_chart(fig, use_container_width=True)
                            elif result.get("issues"):
                                st.dataframe(pd.DataFrame(result["issues"]), use_container_width=True, hide_index=True)
                            else:
                                st.warning("The solver did not prove an optimal plan. Do not use this result as a production cut list.")
                    elif selected_tool["tool_id"] == "T075":
                        result = st.session_state.get("shoir_tool_result_T075")
                        if result:
                            _show_focused_tool_persistence("T075", result, current_tool_inputs)
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("Status", result["status"])
                            c2.metric("MAE", f"{result['mae']:.4g}")
                            c3.metric("RMSE", f"{result['rmse']:.4g}")
                            c4.metric("Mean error", f"{result['bias_actual_minus_prediction']:.4g}")
                            st.caption(result["warning"])
                            st.dataframe(result["series"], use_container_width=True, hide_index=True)
                            fig = px.line(
                                result["series"], x="Observation", y=["Prediction", "Actual"],
                                markers=True, title="Forecasts versus later actuals",
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    elif selected_tool["tool_id"] == "T085":
                        result = st.session_state.get("shoir_tool_result_T085")
                        if result:
                            _show_focused_tool_persistence("T085", result, current_tool_inputs)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Status", result["status"])
                            c2.metric(
                                "Samples per group",
                                str(result["required_n_per_group"]) if result["required_n_per_group"] is not None else "Limit reached",
                            )
                            c3.metric("Achieved power", f"{result['achieved_power']:.3f}")
                            st.caption(result["assumptions"])
                            chart_df = pd.DataFrame({
                                "Metric": ["Target power", "Achieved power"],
                                "Power": [result["target_power"], result["achieved_power"]],
                            })
                            st.plotly_chart(
                                px.bar(chart_df, x="Metric", y="Power", range_y=[0, 1],
                                       title="Requested versus achieved power"),
                                use_container_width=True,
                            )
                            if result["status"] == "LIMIT_REACHED":
                                st.warning(result["message"])
                            else:
                                st.write(result["message"])
                    elif selected_tool["tool_id"] == "T026":
                        result = st.session_state.get("shoir_tool_result_T026")
                        if result:
                            _show_focused_tool_persistence("T026", result, current_tool_inputs)
                            k1, k2, k3, k4 = st.columns(4)
                            k1.metric("Availability", f"{result['availability_pct']:.2f}%")
                            k2.metric("Performance", f"{result['performance_pct']:.2f}%")
                            k3.metric("Quality", f"{result['quality_pct']:.2f}%")
                            k4.metric("OEE", f"{result['oee_pct']:.2f}%")
                            st.caption(result["formula"])
                            st.warning(result["warning"]) if result["status"] != "CALCULATED" else st.caption(result["warning"])
                            st.dataframe(result["losses"], use_container_width=True, hide_index=True)
                            st.plotly_chart(px.bar(result["losses"], x="Component", y=f"Time equivalent ({result['time_unit']})", title="OEE loss decomposition"), use_container_width=True)
                    elif selected_tool["tool_id"] == "T032":
                        result = st.session_state.get("shoir_tool_result_T032")
                        if result:
                            _show_focused_tool_persistence("T032", result, current_tool_inputs)
                            cols = st.columns(4)
                            for col, label, metric in zip(cols, ("Cp", "Cpk", "Pp", "Ppk"), ("cp", "cpk", "pp", "ppk")):
                                col.metric(label, f"{result[metric]:.4f}")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            st.dataframe(result["series"], use_container_width=True, hide_index=True)
                            st.plotly_chart(px.line(result["series"], x="Observation", y=f"Measurement ({result['unit']})", markers=True, title="Process measurements by observation"), use_container_width=True)
                    elif selected_tool["tool_id"] == "T055":
                        result = st.session_state.get("shoir_tool_result_T055")
                        if result:
                            _show_focused_tool_persistence("T055", result, current_tool_inputs)
                            cols = st.columns(3)
                            cols[0].metric("Economic order quantity", f"{result['economic_order_quantity_units']:,.2f}")
                            cols[1].metric("Safety stock", f"{result['safety_stock_units']:,.2f}")
                            cols[2].metric("Reorder point", f"{result['reorder_point_units']:,.2f}")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            st.dataframe(pd.DataFrame([{"Measure": "Annual demand (units)", "Value": result["annual_demand_units"]}, {"Measure": "EOQ (units/order)", "Value": result["economic_order_quantity_units"]}, {"Measure": "Safety stock (units)", "Value": result["safety_stock_units"]}, {"Measure": "Reorder point (units)", "Value": result["reorder_point_units"]}]), use_container_width=True, hide_index=True)
                    elif selected_tool["tool_id"] == "T078":
                        result = st.session_state.get("shoir_tool_result_T078")
                        if result:
                            _show_focused_tool_persistence("T078", result, current_tool_inputs)
                            cols = st.columns(2)
                            cols[0].metric("Emissions", f"{result['emissions_kg_co2e']:,.4g} kg CO2e")
                            cols[1].metric("Emissions", f"{result['emissions_tonnes_co2e']:,.6g} t CO2e")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            st.write(f"Factor source: {result['factor_source']} · date: {result['factor_date']} · boundary: {result['boundary']}")
                    elif selected_tool["tool_id"] == "T081":
                        result = st.session_state.get("shoir_tool_result_T081")
                        if result:
                            _show_focused_tool_persistence("T081", result, current_tool_inputs)
                            cols = st.columns(3)
                            cols[0].metric(f"NPV ({result['currency']})", f"{result['npv']:,.2f}")
                            cols[1].metric("IRR", f"{result['irr_pct']:.3f}%" if result["irr_pct"] is not None else "Not established")
                            cols[2].metric("Simple payback", f"{result['simple_payback_periods']:.3f} periods" if result["simple_payback_periods"] is not None else "Not reached")
                            st.caption(result["formula"])
                            st.warning(result["warning"])
                            st.dataframe(result["cash_flow_schedule"], use_container_width=True, hide_index=True)
                            st.plotly_chart(px.line(result["cash_flow_schedule"], x="Period", y=f"Cumulative cash flow ({result['currency']})", markers=True, title="Cumulative project cash flow"), use_container_width=True)
    else:
        st.info("No target tools match these filters. Clear the search or select All workbenches / All statuses.")

# A denied legacy module may not render, but users can still discover tools and see their tier requirements.
if not _selected_module_allowed:
    st.stop()

# Specialized upgraded surfaces
if selected == "Engineering Validation Center":
    st.subheader("🔎 Engineering Validation Center")
    st.caption("Validate schema, missingness, duplicates, types, units, ranges and cross-table references before running engineering logic.")
    source = st.session_state.get("workbench_df", pd.DataFrame({
        "ID":["A-001","A-002","A-002","A-004"],
        "Value":[10,11,np.nan,999],
        "Unit":["units","units","units","units"],
    }))
    edited = st.data_editor(source, num_rows="dynamic", use_container_width=True, key="wb_validation_editor")
    a,b,c = st.columns(3)
    with a:
        required_cols = st.multiselect("Required columns", list(edited.columns), default=[edited.columns[0]] if len(edited.columns) else [])
    with b:
        unique_cols = st.multiselect("Unique columns", list(edited.columns), default=[])
    with c:
        unit = st.text_input("Primary unit", "units")
    if st.button("🔎 Run Full Validation", type="primary", use_container_width=True):
        schema=validate_schema(edited,required_cols,unique_cols)
        units=validate_units({"Primary":unit})
        st.session_state["wb_validation_result"]={"schema":schema,"units":units}
        audit_event(USER,"validation_run",{"module":selected,"fingerprint":deep_data_quality(edited)["fingerprint"]})
    res=st.session_state.get("wb_validation_result")
    if res:
        m1,m2,m3=st.columns(3)
        m1.metric("Data quality",f"{res['schema']['quality']['score']:.1f}%")
        m2.metric("Validation", "PASS" if res["schema"]["valid"] and res["units"]["valid"] else "ATTENTION")
        m3.metric("Rows", len(edited))
        render_engineering_result(res,"Validation result","validation_result")
    st.dataframe(edited,use_container_width=True)

elif selected == "Industrial Data Model & Digital Thread":
    st.subheader("🔗 Industrial Digital Thread")
    tab1,tab2,tab3 = st.tabs(["Entities","Relationships","Impact Analysis"])
    with tab1:
        entities=st.data_editor(st.session_state.get("wb_entities",pd.DataFrame({
            "ID":["FAC-001","MCH-001","SKU-001","SUP-001"],
            "Name":["Riyadh DC","CNC-01","SKU-A","Supplier A"],
            "Type":["Facility","Machine","SKU","Supplier"],
        })),num_rows="dynamic",use_container_width=True,key="wb_entities_editor")
        st.session_state["wb_entities"]=entities
        entity_type=st.selectbox("Entity type",sorted(entities["Type"].dropna().astype(str).unique()) if "Type" in entities.columns else ["Facility"])
        if st.button("🔗 Sync Entity Records",type="primary",use_container_width=True):
            from industrial_platform import upsert_entities
            count=upsert_entities(entities.rename(columns={"ID":"EntityID"}),"IndustrialEntity","EntityID")
            st.success(f"Synchronized {count:,} entities into the shared digital-thread store.")
    with tab2:
        rel=st.data_editor(st.session_state.get("wb_relationships",pd.DataFrame({
            "From":["FAC-001","FAC-001","MCH-001"],
            "Relationship":["contains","ships","produces"],
            "To":["MCH-001","SKU-001","SKU-001"],
        })),num_rows="dynamic",use_container_width=True,key="wb_relationship_editor")
        st.session_state["wb_relationships"]=rel
        if st.button("🔗 Persist Relationships",type="primary",use_container_width=True):
            from industrial_platform_excellence import upsert_relationships
            st.success(f"Saved {upsert_relationships(rel,USER):,} relationships.")
    with tab3:
        target=st.text_input("Start entity","FAC-001")
        hops=st.number_input("Maximum hops",1,10,4)
        if st.button("🧭 Trace downstream impact",use_container_width=True):
            from industrial_platform_excellence import impact_analysis
            impact=impact_analysis(target,int(hops))
            st.session_state["impact"]=impact
        st.dataframe(st.session_state.get("impact",pd.DataFrame()),use_container_width=True,hide_index=True)

elif selected == "Advanced Planning & Scheduling":
    st.subheader("📅 Advanced Planning & Scheduling")
    tab1,tab2,tab3 = st.tabs(["Orders","Constraints","Schedule"])
    with tab1:
        orders=st.data_editor(st.session_state.get("wb_orders",pd.DataFrame({
            "Order":["WO-001","WO-002","WO-003","WO-004"],
            "Product":["P-100","P-200","P-100","P-300"],
            "Qty":[100,200,150,120],
            "DueDate":[datetime.now()+pd.Timedelta(hours=8),datetime.now()+pd.Timedelta(hours=10),datetime.now()+pd.Timedelta(hours=12),datetime.now()+pd.Timedelta(hours=15)],
            "ProcessingMin":[30,45,25,35],
            "SetupMin":[5,10,5,8],
            "Machine":["M-01","M-01","M-02","M-02"],
            "Priority":[3,1,2,2],
            "MaterialReady":[datetime.now(),datetime.now()+pd.Timedelta(hours=1),datetime.now(),datetime.now()+pd.Timedelta(hours=2)],
        })),num_rows="dynamic",use_container_width=True,key="wb_orders_editor")
        st.session_state["wb_orders"]=orders
    with tab2:
        c1,c2=st.columns(2)
        with c1:
            labor_df=st.data_editor(st.session_state.get("wb_labor",pd.DataFrame({"Machine":["M-01","M-02"],"CapacityHours":[8,8]})),num_rows="dynamic",use_container_width=True,key="wb_labor_editor")
        with c2:
            material_df=st.data_editor(st.session_state.get("wb_material",pd.DataFrame({"Product":["P-100","P-200","P-300"],"Available":[500,300,100]})),num_rows="dynamic",use_container_width=True,key="wb_material_editor")
        maintenance=st.data_editor(st.session_state.get("wb_maintenance",pd.DataFrame({
            "Machine":["M-02"],"Start":[datetime.now()+pd.Timedelta(hours=3)],"End":[datetime.now()+pd.Timedelta(hours=4)],
        })),num_rows="dynamic",use_container_width=True,key="wb_maintenance_editor")
        setup_text=st.text_area("Sequence-dependent setup matrix JSON",'{"P-100|P-200":15,"P-200|P-100":12}')
    with tab3:
        if st.button("▶ Build Constraint-Aware Schedule",type="primary",use_container_width=True):
            setup={}
            try:
                for k,v in json.loads(setup_text).items():
                    a_,b_=k.split("|",1); setup[(a_,b_)]=float(v)
                labor={r["Machine"]:float(r["CapacityHours"]) for r in labor_df.to_dict("records")}
                materials={r["Product"]:float(r["Available"]) for r in material_df.to_dict("records")}
                schedule,diag=constrained_schedule(orders,maintenance,labor,materials,setup)
                st.session_state["wb_schedule"]=schedule
                st.session_state["wb_schedule_diag"]=diag
            except Exception as exc:
                st.error(f"Schedule could not be completed safely: {exc}")
        sch=st.session_state.get("wb_schedule")
        if sch is not None:
            st.dataframe(sch,use_container_width=True,hide_index=True)
            render_engineering_result(st.session_state["wb_schedule_diag"],"Schedule diagnostics","schedule_diag")
            fig=px.timeline(sch,x_start="Start",x_end="Finish",y="Machine",color="Product",hover_data=["Order","LateMin"])
            st.plotly_chart(fig,use_container_width=True)

elif selected == "Quality Engineering & Reliability":
    st.subheader("📈 Quality Engineering & Reliability")
    tab1,tab2,tab3,tab4 = st.tabs(["SPC","Capability / MSA","DOE / ANOVA","Reliability"])
    with tab1:
        vals=st.text_area("Measurements","10,10.1,9.9,10.05,9.95,10.2,10.0,9.8")
        chart=st.selectbox("Chart type",["I-MR","Individuals","p","u"])
        if st.button("📊 Build control chart",type="primary",use_container_width=True):
            try:
                nums=[float(x.strip()) for x in vals.split(",") if x.strip()]
                if chart in {"p","u"}:
                    counts=nums
                    samples=[100]*len(nums)
                    out=proportion_chart(counts,samples,chart)
                else:
                    out=control_chart(nums,chart)
                st.session_state["wb_spc"]=out
            except Exception as exc:
                st.error(f"SPC analysis failed safely: {exc}")
        if "wb_spc" in st.session_state:
            out=st.session_state["wb_spc"]; st.dataframe(out,use_container_width=True,hide_index=True)
            ycol="Rate" if "Rate" in out else "Value"
            st.line_chart(out.set_index(out.columns[0])[[ycol]])
    with tab2:
        qc=st.data_editor(st.session_state.get("wb_qc",pd.DataFrame({"Measurement":[10.1,10.0,9.9,10.2,9.8,10.05],"Part":[1,1,2,2,3,3],"Operator":["A","B","A","B","A","B"]})),num_rows="dynamic",use_container_width=True,key="wb_qc_editor")
        lsl=st.number_input("LSL",value=9.0); usl=st.number_input("USL",value=11.0); target=st.number_input("Target",value=10.0)
        if st.button("🔬 Capability + Gage R&R",use_container_width=True):
            render_engineering_result({"Capability":capability_extended(qc["Measurement"],lsl,usl,target),"Gage R&R":gage_rr_extended(qc)},"Capability & Gage R&R","capability_result")
    with tab3:
        doe=st.data_editor(st.session_state.get("wb_doe",pd.DataFrame({"A":[-1,-1,1,1],"B":[-1,1,-1,1],"Response":[10,12,14,16]})),num_rows="dynamic",use_container_width=True,key="wb_doe_editor")
        response=st.selectbox("Response",list(doe.columns),index=2 if len(doe.columns)>2 else 0)
        factors=st.multiselect("Factors",[c for c in doe.columns if c!=response])
        if factors and st.button("🧪 Estimate effects",use_container_width=True):
            st.dataframe(doe_2level_effects(doe,response,factors),use_container_width=True,hide_index=True)
    with tab4:
        failures=st.text_area("Failure times","10,20,30,40,50,65,80")
        if st.button("📉 Fit reliability model",use_container_width=True):
            try:
                nums=[float(x.strip()) for x in failures.split(",") if x.strip()]
                render_engineering_result(reliability_summary(nums),"Reliability result","reliability_result")
            except Exception as exc:
                st.error(f"Reliability analysis failed safely: {exc}")

elif selected == "Industrial Simulation Lab":
    st.subheader("🧪 Industrial Simulation Lab")
    tab1,tab2 = st.tabs(["Replication Statistics","Warm-up Diagnostics"])
    with tab1:
        sim=st.data_editor(st.session_state.get("wb_sim",pd.DataFrame({"Replication":range(1,11),"Throughput":[95,99,101,98,100,102,97,100,99,101],"MeanWait":[11,13,12,14,10,12,13,11,12,12]})),num_rows="dynamic",use_container_width=True,key="wb_sim_editor")
        metric=st.selectbox("Metric", [c for c in sim.columns if c!="Replication"] or ["Throughput"])
        if st.button("📏 Calculate 95% confidence interval",type="primary",use_container_width=True):
            render_engineering_result(simulation_statistics(sim,metric),"Simulation statistics","simulation_result")
    with tab2:
        series=st.text_area("Observed metric series","100,101,102,102,101,100,100,99,100,100,101,100,100,101,100,100")
        window=st.number_input("Rolling window",3,50,5)
        if st.button("🧭 Diagnose warm-up",use_container_width=True):
            try:
                nums=[float(x.strip()) for x in series.split(",") if x.strip()]
                render_engineering_result(warmup_diagnostic(nums,int(window)),"Warm-up diagnostics","warmup_result")
            except Exception as exc:
                st.error(f"Warm-up diagnostic failed safely: {exc}")

elif selected == "3D Factory Designer":
    st.subheader("🧱 3D Factory Engineering")
    layout=st.data_editor(st.session_state.get("wb_layout",pd.DataFrame({
        "Asset":["CNC-01","Assembly-01","Packing-01","WIP"],
        "Type":["Machine","Station","Station","Storage"],
        "X":[0,5,11,3],"Y":[0,2,2,5],"Z":[0,0,0,0],
        "Length":[2,4,4,3],"Width":[2,2,2,3],"Height":[2,3,3,2],
    })),num_rows="dynamic",use_container_width=True,key="wb_layout_editor")
    st.session_state["wb_layout"]=layout
    fig=px.scatter_3d(layout,x="X",y="Y",z="Z",color="Type",text="Asset",size="Height",title="Factory Model")
    st.plotly_chart(fig,use_container_width=True)
    c1,c2=st.columns(2)
    with c1:
        if st.button("🧱 Collision check",use_container_width=True):
            st.session_state["wb_collisions"]=bbox_collision_check(layout)
    with c2:
        seq=st.text_input("Flow sequence","CNC-01,Assembly-01,Packing-01")
        if st.button("🚶 Analyze flow distance",use_container_width=True):
            st.session_state["wb_flow"]=flow_distance(layout,[x.strip() for x in seq.split(",") if x.strip()])
    if "wb_collisions" in st.session_state:
        st.dataframe(st.session_state["wb_collisions"],use_container_width=True,hide_index=True)
    if "wb_flow" in st.session_state:
        st.metric("Flow distance",f"{st.session_state['wb_flow']['Total Distance']:.2f}")
        st.dataframe(st.session_state["wb_flow"]["Legs"],use_container_width=True,hide_index=True)

elif selected == "Multi-Objective Optimization":
    st.subheader("⚖️ Multi-Objective Optimization")
    df=st.data_editor(st.session_state.get("wb_multi",pd.DataFrame({
        "Scenario":["A","B","C","D"],"Cost":[100,90,120,110],"Carbon":[80,120,60,75],"Service":[94,97,99,96],"Risk":[12,20,8,15]
    })),num_rows="dynamic",use_container_width=True,key="wb_multi_editor")
    objectives=st.multiselect("Objectives",["Cost","Carbon","Service","Risk"],default=["Cost","Carbon","Service"])
    minimize={c:st.checkbox(f"Minimize {c}",value=(c!="Service"),key=f"wb_min_{c}") for c in objectives}
    if objectives and st.button("⚖️ Calculate Pareto frontier",type="primary",use_container_width=True):
        st.session_state["wb_pareto"]=pareto_frontier_v2(df,objectives,[minimize[c] for c in objectives])
    st.dataframe(st.session_state.get("wb_pareto",pd.DataFrame()),use_container_width=True,hide_index=True)

elif selected == "Robust & Resilient Optimization":
    st.subheader("🎲 Robust & Resilient Optimization")
    scenarios=st.data_editor(st.session_state.get("wb_robust",pd.DataFrame({
        "Scenario":["Baseline","High Demand","Supplier Shock","Capacity Expansion"],
        "Demand Mean":[1000,1200,1050,1000],"Demand Std":[100,150,120,100],
        "Capacity":[1100,1100,700,1300],"Disruption Probability":[0.05,0.1,0.2,0.05],
        "Disruption Multiplier":[0.6,0.6,0.5,0.8],
    })),num_rows="dynamic",use_container_width=True,key="wb_robust_editor")
    sims=st.number_input("Simulations",1000,100000,5000,500)
    if st.button("🎲 Run robust scenarios",type="primary",use_container_width=True):
        out=robust_scenarios({},scenarios,int(sims))
        st.session_state["wb_robust_result"]=out
    if "wb_robust_result" in st.session_state:
        st.dataframe(st.session_state["wb_robust_result"],use_container_width=True,hide_index=True)
        st.plotly_chart(px.bar(st.session_state["wb_robust_result"],x="Scenario",y="Service Probability",title="Service probability by scenario"),use_container_width=True)

elif selected == "Capital Investment & Engineering Economics":
    st.subheader("💰 Capital Investment & Engineering Economics")
    capex=st.number_input("Initial investment",0.0,1e9,100000.0,1000.0)
    flows=st.text_input("Annual cash flows","40000,50000,60000,70000")
    c1,c2=st.columns(2)
    rates_text=c1.text_input("Discount rates","0.08,0.10,0.12")
    mult_text=c2.text_input("CAPEX multipliers","0.9,1.0,1.1")
    if st.button("💰 Run sensitivity",type="primary",use_container_width=True):
        try:
            cf=[float(x.strip()) for x in flows.split(",") if x.strip()]
            rates=[float(x.strip()) for x in rates_text.split(",") if x.strip()]
            mult=[float(x.strip()) for x in mult_text.split(",") if x.strip()]
            out=economics_sensitivity(capex,cf,rates,mult)
            st.session_state["wb_econ"]=out
        except Exception as exc:
            st.error(f"Economics calculation failed safely: {exc}")
    if "wb_econ" in st.session_state:
        st.dataframe(st.session_state["wb_econ"],use_container_width=True,hide_index=True)
        st.plotly_chart(px.density_heatmap(st.session_state["wb_econ"],x="Discount Rate",y="CAPEX Multiplier",z="NPV",text_auto=".0f"),use_container_width=True)

elif selected == "Workforce Engineering":
    st.subheader("👷 Workforce Engineering")
    a,b,c=st.columns(3)
    staff=a.number_input("Staff",1,10000,20)
    minutes=b.number_input("Minutes/shift",60.0,1440.0,480.0)
    prod=c.slider("Productive %",1,100,85)
    absent=st.slider("Absenteeism %",0,50,5)
    overtime=st.number_input("Overtime hours",0.0,24.0,2.0)
    wage=st.number_input("Wage/hour",0.0,1000.0,25.0)
    if st.button("👷 Evaluate workforce scenario",type="primary",use_container_width=True):
        render_engineering_result(workforce_scenario(staff,minutes,prod,absent,overtime,wage),"Workforce scenario","workforce_result")

elif selected == "Industrial Sustainability & LCA":
    st.subheader("🌱 Industrial Sustainability & LCA")
    df=st.data_editor(st.session_state.get("wb_lca",pd.DataFrame({
        "Activity":["Electricity","Diesel","Freight","Water","Waste"],
        "Scope":["Scope 2","Scope 1","Scope 3","Resource","Resource"],
        "LifeCycleStage":["Operations","Operations","Distribution","Operations","Operations"],
        "Quantity":[10000,2500,15000,3000,12000],
        "EmissionFactor":[0.42,2.68,0.10,0.0,0.0],
        "Energy_kWh":[10000,0,0,0,0],
        "Water_m3":[0,0,0,3000,0],
        "Waste_kg":[0,0,0,0,12000],
    })),num_rows="dynamic",use_container_width=True,key="wb_lca_editor")
    if st.button("🌱 Calculate lifecycle impacts",type="primary",use_container_width=True):
        st.session_state["wb_lca_result"]=sustainability_scenario(df)
    if "wb_lca_result" in st.session_state:
        r=st.session_state["wb_lca_result"]
        st.metric("Total tCO2e",f"{r['total_tCO2e']:,.3f}")
        st.dataframe(r["scope_summary"],use_container_width=True,hide_index=True)
        st.dataframe(r["detail"],use_container_width=True,hide_index=True)

elif selected == "Benchmarking & Engineering Standards":
    st.subheader("📏 Benchmarking & Engineering Standards")
    actual=st.data_editor(st.session_state.get("wb_bench_actual",pd.DataFrame({"Metric":["OEE","OTIF","Inventory Turns","Energy / Unit"],"Actual":[82,96,5.2,1.8]})),num_rows="dynamic",use_container_width=True,key="wb_bench_actual_editor")
    bench=st.data_editor(st.session_state.get("wb_bench_benchmark",pd.DataFrame({"Metric":["OEE","OTIF","Inventory Turns","Energy / Unit"],"Benchmark":[85,98,6,1.5],"Source":["Configured Target"]*4,"Source Date":["2026-01"]*4})),num_rows="dynamic",use_container_width=True,key="wb_bench_benchmark_editor")
    if st.button("📏 Compare benchmark gaps",type="primary",use_container_width=True):
        st.session_state["wb_bench_result"]=benchmark_gap(actual,bench)
    if "wb_bench_result" in st.session_state:
        st.dataframe(st.session_state["wb_bench_result"],use_container_width=True,hide_index=True)

elif selected == "Engineering Decision Center":
    st.subheader("📋 Engineering Decision Center")
    title=st.text_input("Decision title","Open additional packing capacity")
    metrics_df=st.data_editor(pd.DataFrame({"Metric":["Cost Delta","Service Delta","Carbon Delta"],"Value":[-8.2,2.1,-4.5]}),num_rows="dynamic",use_container_width=True,key="wb_decision_metrics")
    assumptions=st.text_area("Assumptions JSON",'{"Demand":"12-week forecast v4","Capacity":"Verified"}')
    uncertainty=st.text_area("Uncertainty JSON",'{"Demand P95":"Base + 18%","Supplier disruption":"5%"}')
    status=st.selectbox("Status",["Proposed","Needs Revision","Approved","Rejected"])
    if st.button("📋 Save Decision Card",type="primary",use_container_width=True):
        try:
            card=build_decision_card(title,selected,{r["Metric"]:r["Value"] for r in metrics_df.to_dict("records")},json.loads(assumptions),json.loads(uncertainty),status)
            did=save_decision(card,USER)
            st.success(f"Decision saved: {did}")
            st.session_state["last_decision_id"]=did
        except Exception as exc:
            st.error(f"Decision could not be saved safely: {exc}")
    decision_id=st.session_state.get("last_decision_id")
    if decision_id:
        note=st.text_input("Approval note","")
        a1,a2,a3=st.columns(3)
        with a1:
            if st.button("✅ Approve",use_container_width=True) and permission_check(st.session_state.get("role","Viewer"),"approve"):
                st.write(record_approval(decision_id,USER,"Approved",note))
        with a2:
            if st.button("↩ Needs Revision",use_container_width=True) and permission_check(st.session_state.get("role","Viewer"),"approve"):
                st.write(record_approval(decision_id,USER,"Needs Revision",note))
        with a3:
            if st.button("❌ Reject",use_container_width=True) and permission_check(st.session_state.get("role","Viewer"),"approve"):
                st.write(record_approval(decision_id,USER,"Rejected",note))

elif selected == "Advanced Engineering Copilot":
    st.subheader("🧠 Advanced Engineering Copilot")
    st.caption("Planning layer first: Shoir-IE shows the proposed workflow, asks for approval, then hands execution to the relevant deterministic module.")
    prompt=st.text_area("Engineering request","Import the demand workbook, clean it, forecast 12 weeks, test supplier disruption risk, compare scenarios and prepare an executive report.")
    if st.button("🧠 Build execution plan",type="primary",use_container_width=True):
        st.session_state["wb_plan"]=copilot_execution_plan(prompt)
    plan=st.session_state.get("wb_plan")
    if plan:
        render_engineering_result(plan,"Proposed execution plan","copilot_plan")
        approve=st.button("✅ Approve this workflow")
        if approve:
            st.session_state["wb_plan_approved"]=True
            audit_event(USER,"copilot_plan_approved",{"steps":plan["steps"]})
            st.success("Workflow approved. Execute each step from its governed module; this layer does not silently mutate data.")
        st.metric("Approval required","YES" if plan["approval_required"] else "NO")

elif selected == "Industrial Connectivity Hub":
    st.subheader("🔌 Industrial Connectivity Hub")
    conns=st.data_editor(st.session_state.get("wb_connectors",pd.DataFrame({
        "Name":["Plant REST","Plant MQTT","Machine OPC-UA","Analytics SQL"],
        "System Type":["REST","MQTT","OPC-UA","SQL"],
        "Endpoint":["https://example.com/api","mqtts://broker.example","opc.tcp://localhost:4840","sqlite://enterprise_full_workspace.db"]
    })),num_rows="dynamic",use_container_width=True,key="wb_conn_editor")
    for row in conns.to_dict("records"):
        if st.button(f"🧪 Validate {row['Name']}",use_container_width=True,key="conn_"+re.sub(r"[^A-Za-z0-9]","_",str(row["Name"]))):
            render_engineering_result(connector_validation(row["Name"],row["System Type"],row["Endpoint"]),f"Connector validation · {row['Name']}","connector_"+re.sub(r"[^A-Za-z0-9]","_",str(row["Name"])))

elif selected in {"Manufacturing Execution System","Industrial Control Center","Executive Report Center","Enterprise Security & Governance","Team Workspaces & RBAC","Engineering Model Registry","Experiment Lab","Live Industrial Digital Twin","Predictive Maintenance Digital Twin","Advanced ML Demand Forecasting","Localization & Multi-Currency"}:
    # Reuse existing mature module implementations under the unified shell.
    render_module(selected, RAW_TIER, USER)

else:
    render_module(selected, RAW_TIER, USER)

# Universal footer controls
st.divider()
st.subheader("📤 Unified Results & Governance")
source_tables=[]
for key in ["wb_validation_result","wb_schedule","wb_spc","wb_pareto","wb_robust_result","wb_econ","wb_lca_result","wb_bench_result","impact","wb_collisions","wb_flow"]:
    val=st.session_state.get(key)
    if isinstance(val,pd.DataFrame):
        source_tables.append((key,val))
    elif isinstance(val,dict):
        for k,v in val.items():
            if isinstance(v,pd.DataFrame):
                source_tables.append((f"{key}_{k}",v))
if source_tables:
    manifest=export_manifest_tables(selected,source_tables,USER)
    csv=manifest.to_csv(index=False).encode()
    st.download_button("📋 Download audit manifest",csv,f"shoir_ie_{re.sub(r'[^A-Za-z0-9]+','_',selected).lower()}_manifest.csv","text/csv",use_container_width=False)
    # Keep the platform's existing export engine as the canonical workbook/PDF/PPT path.
    from industrial_platform import render_export_bar
    render_export_bar(selected,source_tables,[],RAW_TIER,USER)

with st.expander("🏗️ Tier architecture"):
    st.dataframe(tier_matrix(),use_container_width=True,hide_index=True)
with st.expander("🧩 Complete module map"):
    st.dataframe(module_availability(RAW_TIER),use_container_width=True,hide_index=True)
