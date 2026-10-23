"""Additive Engineering Tool Library for Shoir-IE.

This page is intentionally status-led. It does not execute a target unless the
registry marks it VERIFIED_WORKING and the current tier is allowed. Existing
module routes and navigation are left unchanged.
"""
import hashlib
import io
import pandas as pd
import streamlit as st

from shoir_100_tool_registry import (
    TOOL_TARGETS, TOOL_STATUSES, TOOL_TIER_ORDER, WORKBENCHES,
    target_tool_access_decision, target_tool_execution_decision,
)
from shoir_100_tool_engines import analyze_process_event_log, first_fit_decreasing_bin_pack

st.set_page_config(page_title="Engineering Tool Library | Shoir-IE", page_icon="🧭", layout="wide")
# Keep internal readiness/route-gap details behind an authenticated app session.
# The main public Explore Modules experience remains the customer-facing entry point.
if not st.session_state.get("authenticated") or not str(st.session_state.get("current_user", "")).strip():
    st.title("Engineering Tool Library")
    st.info("Sign in to Shoir-IE to view the personalized engineering tool library.")
    st.stop()

tier = str(st.session_state.get("user_tier", ""))
st.title("Engineering Tool Library")
st.caption("100 target capabilities · grouped by workbench · status and entitlement are separate from a catalogue name.")
st.info("This library distinguishes reusable existing routes from validated target behavior. A target marked needs-validation, foundation-only, missing or configuration-required is not represented as end-to-end verified.")
st.caption(f"Your current package: {tier or 'Unresolved — protected tools fail closed'}")
c1, c2, c3 = st.columns([1.5,1,1])
with c1:
    wb = st.selectbox("Workbench", ("All workbenches", *WORKBENCHES), key="tool_library_workbench")
with c2:
    status_filter = st.selectbox("Readiness", ("All statuses", *sorted(TOOL_STATUSES)), key="tool_library_status")
with c3:
    query = st.text_input("Search tools", placeholder="e.g. OEE, facility layout, forecasting", key="tool_library_search")
rows = []
q = query.strip().casefold()
for item in TOOL_TARGETS:
    if wb != "All workbenches" and item["workbench"] != wb:
        continue
    if status_filter != "All statuses" and item["implementation_status"] != status_filter:
        continue
    if q and q not in " ".join(str(item.get(k,"")) for k in ("tool_id","canonical_name","existing_module_or_route","calculation_or_action","workbench")).casefold():
        continue
    d = target_tool_access_decision(item["tool_id"], tier)
    e = target_tool_execution_decision(item["tool_id"], tier)
    rows.append({
        "ID": item["tool_id"], "Capability": item["canonical_name"],
        "Workbench": item["workbench"], "Minimum tier": item["target_minimum_tier"],
        "Package access": "Allowed" if d["allowed"] else "Restricted",
        "Implementation status": item["implementation_status"],
        "Executable in target registry": "Yes" if e["executable"] else "No — acceptance pending",
        "Existing candidate route": item["existing_module_or_route"],
    })
st.caption(f"{len(rows)} of {len(TOOL_TARGETS)} target capabilities match. Existing routes remain available under their current app contracts; this table does not override or assert those routes are verified.")
if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    choices = [r["ID"] + " · " + r["Capability"] for r in rows]
    selected = st.selectbox("Inspect capability contract", choices, key="tool_library_detail")
    selected_id = selected.split(" · ",1)[0]
    item = next(x for x in TOOL_TARGETS if x["tool_id"] == selected_id)
    st.subheader(f'{item["tool_id"]} · {item["canonical_name"]}')
    left, right = st.columns(2)
    with left:
        st.markdown("**Purpose / behavior**")
        st.write(item["calculation_or_action"])
        st.markdown("**Required inputs**")
        st.write(item["input_contract"])
        st.markdown("**Expected outputs**")
        st.write(item["output_contract"])
    with right:
        st.markdown("**Candidate existing route**")
        st.write(item["existing_module_or_route"])
        st.markdown("**Current readiness**")
        st.write(item["implementation_status"])
        st.markdown("**Source candidates**")
        st.code("\n".join(item["source_files"]), language="text")
        st.markdown("**Outstanding gap**")
        st.write(item["remaining_gap"])
    decision = target_tool_execution_decision(selected_id, tier)
    if not decision["allowed"]:
        st.warning(f'This package does not grant this target capability. Required tier: {decision["required_tier"]}.')
    else:
        if not decision["executable"]:
            st.warning("This target cannot be marked executable in the new library until its acceptance tests and authenticated end-to-end evidence pass. A separately entitled existing route may still be opened below.")
        # Offer a route hand-off only to a named legacy module already available
        # under the user's real tier. Do not use the target label to widen access.
        if item["implementation_status"] == "IMPLEMENTED_NEEDS_VALIDATION":
            try:
                from industrial_platform_excellence import module_availability
                available = module_availability(tier)
                available_rows = {
                    str(row["Module"]): str(row["Category"])
                    for _, row in available.iterrows()
                }
                candidates = [
                    part.strip()
                    for part in item["existing_module_or_route"].split("/")
                    if part.strip()
                ]
                eligible = [name for name in candidates if name in available_rows]
                if eligible:
                    candidate = eligible[0]
                    st.caption("Open an existing module under its current route-level entitlement; this does not certify the broader target capability.")
                    if st.button(f"Open existing module: {candidate}", key=f"open_target_legacy_{selected_id}", type="primary"):
                        st.session_state["workbench_module_selector"] = f'{available_rows[candidate]} · {candidate}'
                        st.switch_page("pages/Industrial_Engineering_Workbench.py")
            except Exception as exc:
                # Keep the user's workspace intact and provide a safe visible reason;
                # never silently swallow a route hand-off failure.
                st.warning(
                    f"Could not prepare the existing-module hand-off ({type(exc).__name__}). "
                    "Your data was not changed. Use the normal Workbench navigation."
                )

        if selected_id == "T066":
            st.markdown("### Run bin packing")
            st.caption("Supported method: one-dimensional First-Fit Decreasing. This is a feasible heuristic, not proof of a minimum-bin optimum; cutting-stock patterns and 2-D/3-D packing are not supported.")
            upload = st.file_uploader("Optional item CSV", type=["csv"], key="t066_binpack_upload")
            source = "SYNTHETIC"
            editor_key = "t066_binpack_synthetic_editor"
            input_frame = pd.DataFrame({
                "item": ["Part A", "Part B", "Part C", "Part D", "Part E", "Part F"],
                "size": [6, 5, 5, 4, 4, 2],
                "quantity": [1, 1, 1, 1, 1, 1],
            })
            upload_error = None
            if upload is not None:
                try:
                    raw_upload = upload.getvalue()
                    input_frame = pd.read_csv(io.BytesIO(raw_upload))
                    source = "IMPORTED"
                    editor_key = "t066_binpack_import_" + hashlib.sha256(raw_upload).hexdigest()[:12]
                except Exception as exc:
                    upload_error = f"CSV import rejected ({type(exc).__name__}). The sample and prior result are unchanged."
            if upload_error:
                st.error(upload_error)
            st.caption(f"Input provenance: {source}. The initial table is illustrative synthetic data, not plant measurements.")
            edited_items = st.data_editor(input_frame, num_rows="dynamic", use_container_width=True,
                                          key=editor_key, hide_index=True)
            capacity = st.number_input("Bin capacity (same units as item size)", min_value=0.01,
                                       value=10.0, step=0.5, key="t066_binpack_capacity")
            signature = hashlib.sha256(
                (edited_items.to_csv(index=True) + "|" + repr(float(capacity)) + "|" + source).encode("utf-8")
            ).hexdigest()
            if st.button("Run bin-packing analysis", key="t066_binpack_run", type="primary"):
                if upload_error:
                    st.error("Resolve the uploaded file error before running this analysis.")
                else:
                    try:
                        outcome = first_fit_decreasing_bin_pack(edited_items, float(capacity))
                        st.session_state["shoir_t066_result"] = {
                            "signature": signature, "source": source, "result": outcome,
                        }
                    except ValueError as exc:
                        st.error(f"Input validation failed: {exc}. Previous successful result was preserved.")
            saved = st.session_state.get("shoir_t066_result")
            if isinstance(saved, dict):
                if saved.get("signature") != signature:
                    st.warning("STALE — the table, capacity or provenance changed. Rerun before using the saved result.")
                st.caption(f'Result status: {saved["result"]["status"]} · Input provenance: {saved["source"]} · current-session result (durable project save not yet implemented)')
                metrics = saved["result"]["metrics"]
                metric_cols = st.columns(4)
                metric_cols[0].metric("Bins used", f'{metrics["bins_used"]:,}')
                metric_cols[1].metric("Item instances", f'{metrics["item_instances"]:,}')
                metric_cols[2].metric("Unused capacity", f'{metrics["unused_capacity_total"]:,.3f}')
                metric_cols[3].metric("Utilization", f'{metrics["utilization_percent"]:,.2f}%')
                st.dataframe(saved["result"]["assignments"], use_container_width=True, hide_index=True)
                st.markdown("**Bin load and remaining capacity**")
                st.dataframe(saved["result"]["bins"], use_container_width=True, hide_index=True)
                if not saved["result"]["bins"].empty:
                    chart = saved["result"]["bins"].set_index("Bin")[["Used capacity", "Unused capacity"]]
                    st.bar_chart(chart)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.download_button("Download item assignments CSV",
                                       saved["result"]["assignments"].to_csv(index=False).encode("utf-8"),
                                       "shoir_ie_bin_packing_assignments.csv", "text/csv",
                                       key="t066_binpack_assignments_export")
                with col_b:
                    st.download_button("Download bin summary CSV",
                                       saved["result"]["bins"].to_csv(index=False).encode("utf-8"),
                                       "shoir_ie_bin_packing_summary.csv", "text/csv",
                                       key="t066_binpack_bins_export")
                for warning in saved["result"]["warnings"]:
                    st.warning(warning)

        elif selected_id == "T076":
            st.markdown("### Analyze a process event log")
            st.caption("Calculates directly-follows transitions, case duration and inter-event waits. Optional reference-trace comparison is exact sequence matching, not a full Petri-net conformance method.")
            upload = st.file_uploader("Optional process event-log CSV", type=["csv"], key="t076_process_upload")
            source = "SYNTHETIC"
            editor_key = "t076_process_synthetic_editor"
            input_frame = pd.DataFrame([
                {"case_id":"C1","activity":"Start","timestamp":"2026-10-01T08:00:00Z"},
                {"case_id":"C1","activity":"Inspect","timestamp":"2026-10-01T08:03:00Z"},
                {"case_id":"C1","activity":"Pack","timestamp":"2026-10-01T08:05:00Z"},
                {"case_id":"C2","activity":"Start","timestamp":"2026-10-01T09:00:00Z"},
                {"case_id":"C2","activity":"Inspect","timestamp":"2026-10-01T09:04:00Z"},
                {"case_id":"C2","activity":"Pack","timestamp":"2026-10-01T09:10:00Z"},
            ])
            upload_error = None
            if upload is not None:
                try:
                    raw_upload = upload.getvalue()
                    input_frame = pd.read_csv(io.BytesIO(raw_upload))
                    source = "IMPORTED"
                    editor_key = "t076_process_import_" + hashlib.sha256(raw_upload).hexdigest()[:12]
                except Exception as exc:
                    upload_error = f"CSV import rejected ({type(exc).__name__}). The sample and prior result are unchanged."
            if upload_error:
                st.error(upload_error)
            st.caption(f"Input provenance: {source}. The initial event log is synthetic demonstration data.")
            edited_events = st.data_editor(input_frame, num_rows="dynamic", use_container_width=True,
                                           key=editor_key, hide_index=True)
            reference_text = st.text_input(
                "Optional expected activity sequence (comma-separated)",
                value="Start, Inspect, Pack", key="t076_reference_trace",
            )
            reference = [part.strip() for part in reference_text.split(",") if part.strip()]
            signature = hashlib.sha256(
                (edited_events.to_csv(index=True) + "|" + repr(reference) + "|" + source).encode("utf-8")
            ).hexdigest()
            if st.button("Analyze event log", key="t076_process_run", type="primary"):
                if upload_error:
                    st.error("Resolve the uploaded file error before running this analysis.")
                else:
                    try:
                        outcome = analyze_process_event_log(edited_events, reference_sequence=reference or None)
                        st.session_state["shoir_t076_result"] = {
                            "signature": signature, "source": source, "result": outcome,
                        }
                    except ValueError as exc:
                        st.error(f"Event-log validation failed: {exc}. Previous successful result was preserved.")
            saved = st.session_state.get("shoir_t076_result")
            if isinstance(saved, dict):
                if saved.get("signature") != signature:
                    st.warning("STALE — the event log or reference sequence changed. Rerun before relying on this result.")
                st.caption(f'Result status: {saved["result"]["status"]} · Input provenance: {saved["source"]} · current-session result (durable project save not yet implemented)')
                metrics = saved["result"]["metrics"]
                metric_cols = st.columns(4)
                metric_cols[0].metric("Cases", f'{metrics["case_count"]:,}')
                metric_cols[1].metric("Events", f'{metrics["event_count"]:,}')
                metric_cols[2].metric("Activities", f'{metrics["activity_count"]:,}')
                metric_cols[3].metric("Mean case duration", f'{metrics["mean_case_duration_minutes"]:,.2f} min')
                st.markdown("**Case traces and duration**")
                st.dataframe(saved["result"]["cases"], use_container_width=True, hide_index=True)
                st.markdown("**Directly-follows transitions and waiting time**")
                dfg = saved["result"]["directly_follows"].copy()
                if not dfg.empty:
                    dfg["Transition"] = dfg["From activity"].astype(str) + " → " + dfg["To activity"].astype(str)
                    st.bar_chart(dfg.set_index("Transition")["transition_count"])
                else:
                    st.info("No transitions can be calculated from the current event log; provide at least two ordered events within a case.")
                st.dataframe(saved["result"]["directly_follows"], use_container_width=True, hide_index=True)
                st.markdown("**Activity frequency**")
                st.dataframe(saved["result"]["activities"], use_container_width=True, hide_index=True)
                exports = [
                    ("Download case metrics CSV", "cases", "shoir_ie_process_mining_cases.csv"),
                    ("Download directly-follows CSV", "directly_follows", "shoir_ie_process_mining_transitions.csv"),
                    ("Download activity summary CSV", "activities", "shoir_ie_process_mining_activities.csv"),
                ]
                export_cols = st.columns(len(exports))
                for col, (label, key, filename) in zip(export_cols, exports):
                    with col:
                        st.download_button(label, saved["result"][key].to_csv(index=False).encode("utf-8"),
                                           filename, "text/csv", key=f"t076_export_{key}")
                for warning in saved["result"]["warnings"]:
                    st.warning(warning)
else:
    st.warning("No target capabilities match these filters. Change the workbench, status or search.")
