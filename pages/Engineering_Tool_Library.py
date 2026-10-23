"""Additive Engineering Tool Library for Shoir-IE.

This page is intentionally status-led. It does not execute a target unless the
registry marks it VERIFIED_WORKING and the current tier is allowed. Existing
module routes and navigation are left unchanged.
"""
import pandas as pd
import streamlit as st

from shoir_100_tool_registry import (
    TOOL_TARGETS, TOOL_STATUSES, TOOL_TIER_ORDER, WORKBENCHES,
    target_tool_access_decision, target_tool_execution_decision,
)

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
else:
    st.warning("No target capabilities match these filters. Change the workbench, status or search.")
