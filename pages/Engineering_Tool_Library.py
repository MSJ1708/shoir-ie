"""Additive Engineering Tool Library for Shoir-IE.

This page is status-led and checks the logged-in tier before displaying actions.
Only VERIFIED_WORKING is a production-readiness assertion. The two limited-scope
methods T066/T076 may be exercised as explicitly labelled validation-mode tools;
they remain IMPLEMENTED_NEEDS_VALIDATION until authenticated E2E and independent
acceptance checks pass. Existing routes and navigation are left unchanged.
"""
import hashlib
import io
import json
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from shoir_100_tool_registry import (
    TOOL_TARGETS, TOOL_STATUSES, TOOL_TIER_ORDER, WORKBENCHES,
    target_tool_access_decision, target_tool_execution_decision,
)
from shoir_100_tool_engines import (
    analyze_process_event_log, calculate_carbon_emissions,
    calculate_engineering_economics, calculate_inventory_policy,
    calculate_oee, calculate_process_capability, calculate_standard_time,
    calculate_takt_capacity, first_fit_decreasing_bin_pack,
)
from shoir_100_tool_extended_engines import (
    analyze_abc_xyz_inventory, analyze_mtbf_mttr, analyze_pareto_root_cause,
    analyze_quality_cost_defects, analyze_spc_individuals, analyze_work_sampling,
    assess_5s_audit, build_kaizen_a3_record, convert_units_or_currency,
    monitor_forecast_drift, plan_two_sample_t_sample_size, solve_cutting_stock,
)

def _fingerprint(*values):
    return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()


def _run_engine_tool(tool_id, signature, button_label, calculation):
    """Run one deterministic validation-mode method and preserve last success on bad input."""
    if st.button(button_label, key=f"{tool_id}_run_button", type="primary"):
        try:
            outcome = calculation()
        except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
            st.error(
                f"Calculation was not completed: {exc}. "
                "The last successful result was preserved."
            )
        else:
            status = outcome.get("status") if isinstance(outcome, dict) else None
            if isinstance(status, str) and status.strip() and status.upper() not in {"FAILED", "ERROR", "INVALID"}:
                st.session_state[f"shoir_{tool_id}_result"] = {
                    "signature": signature,
                    "source": "USER-ENTERED — not independently verified",
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                    "result": outcome,
                }
            else:
                st.error("The method returned no usable result status; the prior result was preserved.")

    saved = st.session_state.get(f"shoir_{tool_id}_result")
    if not isinstance(saved, dict):
        return None
    if saved.get("signature") != signature:
        st.warning("STALE — one or more inputs changed. Rerun before using this saved result.")
    result = saved.get("result", {})
    st.caption(
        f"Result: {result.get('status', 'UNRESOLVED')} · {saved.get('source', 'UNVERIFIED')} · "
        f"executed {saved.get('executed_at', 'timestamp unavailable')} · session-only result"
    )
    metrics = result.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    if not metrics:
        excluded = {"status", "method", "formulas", "formula", "assumptions", "warnings", "warning", "provenance", "message"}
        metrics = {
            key: value for key, value in result.items()
            if key not in excluded and not isinstance(value, (dict, list, tuple, pd.DataFrame, pd.Series)) and value is not None
        }
    if metrics:
        metric_rows = [{"Metric": key, "Value": value} for key, value in metrics.items()]
        st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, hide_index=True)
    for table_name, table in result.items():
        if isinstance(table, pd.DataFrame):
            st.markdown(f"**{table_name.replace('_', ' ').title()}**")
            if table.empty:
                st.info(f"{table_name.replace('_', ' ').title()} is empty for the current inputs.")
            else:
                st.dataframe(table, use_container_width=True, hide_index=True)
                st.download_button(
                    f"Download {table_name.replace('_', ' ').title()} CSV",
                    table.to_csv(index=False).encode("utf-8"),
                    f"shoir_ie_{tool_id.lower()}_{table_name}.csv", "text/csv",
                    key=f"{tool_id}_{table_name}_export",
                )
    with st.expander("Formula, assumptions and limitations", expanded=False):
        st.markdown("**Method**")
        st.write(result.get("method", result.get("message", "Method not supplied")))
        formulas = result.get("formulas", {})
        if isinstance(formulas, dict) and formulas:
            st.markdown("**Formulas**")
            st.dataframe(
                pd.DataFrame([{"Result": key, "Formula": value} for key, value in formulas.items()]),
                use_container_width=True, hide_index=True,
            )
        elif result.get("formula"):
            st.markdown("**Formula**")
            st.write(result["formula"])
        st.markdown("**Assumptions**")
        assumptions = result.get("assumptions", [])
        if isinstance(assumptions, str):
            assumptions = [assumptions]
        for statement in assumptions:
            st.write(f"• {statement}")
        if result.get("provenance"):
            st.json(result["provenance"])
    warnings = result.get("warnings", [])
    if isinstance(warnings, str):
        warnings = [warnings]
    if result.get("warning"):
        warnings = [*warnings, str(result["warning"])]
    for warning in warnings:
        st.warning(warning)

    # Include source, method, formula and assumptions in the download, not only a rendered KPI.
    csv_rows = [
        {"Section": "Metadata", "Name": "tool_id", "Value": tool_id},
        {"Section": "Metadata", "Name": "status", "Value": result.get("status", "")},
        {"Section": "Metadata", "Name": "method", "Value": result.get("method", "")},
        {"Section": "Metadata", "Name": "source", "Value": saved.get("source", "")},
        {"Section": "Metadata", "Name": "executed_at_utc", "Value": saved.get("executed_at", "")},
    ]
    csv_rows.extend({"Section": "Metric", "Name": key, "Value": value} for key, value in metrics.items())
    csv_rows.extend({"Section": "Formula", "Name": key, "Value": value}
                    for key, value in result.get("formulas", {}).items())
    csv_rows.extend({"Section": "Assumption", "Name": str(i+1), "Value": value}
                    for i, value in enumerate(result.get("assumptions", [])))
    csv_rows.extend({"Section": "Warning", "Name": str(i+1), "Value": value}
                    for i, value in enumerate(result.get("warnings", [])))
    payload = pd.DataFrame(csv_rows).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download calculation, assumptions and provenance (CSV)",
        payload, f"shoir_ie_{tool_id.lower()}_result.csv", "text/csv",
        key=f"{tool_id}_result_download",
    )
    return saved


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

        if selected_id == "T016":
            st.warning("VALIDATION MODE — currency rates are user-supplied and dated; this is not a live FX feed.")
            st.markdown("### Unit and currency converter")
            amount = st.number_input("Amount", value=100.0, step=1.0, key="t016_amount")
            from_unit = st.text_input("From unit (e.g. cm, kWh, °C, SAR)", "cm", key="t016_from_unit")
            to_unit = st.text_input("To unit (e.g. m, MJ, °F, USD)", "m", key="t016_to_unit")
            rate = st.number_input("Optional target-units per source-unit currency rate (0 = not provided)", min_value=0.0, value=0.0, step=0.01, key="t016_rate")
            rate_date = st.text_input("Exchange-rate date (YYYY-MM-DD)", "", key="t016_rate_date")
            rate_source = st.text_input("Exchange-rate source/reference", "", key="t016_rate_source")
            signature = _fingerprint(amount, from_unit, to_unit, rate, rate_date, rate_source)
            _run_engine_tool("T016", signature, "Convert units / currency", lambda: convert_units_or_currency(amount, from_unit, to_unit, exchange_rate=rate if rate > 0 else None, exchange_rate_date=rate_date, exchange_rate_source=rate_source))

        elif selected_id == "T022":
            st.warning("VALIDATION MODE — work sampling estimates a proportion and uncertainty; sample-frame representativeness must be reviewed.")
            st.markdown("### Work-sampling analyzer")
            counts_text = st.text_area("Activity counts as JSON", '{"Productive": 60, "Idle": 40}', height=95, key="t022_counts_json")
            confidence = st.selectbox("Confidence level", [0.90, 0.95, 0.99], index=1, key="t022_confidence")
            margin = st.number_input("Target margin of error (percentage points)", min_value=1.0, max_value=25.0, value=5.0, step=1.0, key="t022_margin")
            signature = _fingerprint(counts_text, confidence, margin)
            saved = _run_engine_tool("T022", signature, "Analyze work sample", lambda: analyze_work_sampling(json.loads(counts_text), confidence_level=confidence, target_margin_pct=margin))
            if saved and saved["signature"] == signature:
                frame = saved["result"].get("activity_summary")
                if isinstance(frame, pd.DataFrame) and not frame.empty and "Activity" in frame and "Observed proportion (%)" in frame:
                    st.bar_chart(frame.set_index("Activity")["Observed proportion (%)"])

        elif selected_id == "T028":
            st.warning("VALIDATION MODE — Pareto shows frequency distribution, not proven causation. 5-Why entries are hypotheses requiring review.")
            st.markdown("### Pareto and root-cause review")
            counts_text = st.text_area("Category counts as JSON", '{"Machine": 60, "Material": 30, "Method": 10}', height=95, key="t028_counts_json")
            problem = st.text_input("Problem statement", "Repeated line stoppages", key="t028_problem")
            why_text = st.text_area("Five-Why chain (one entry per line)", "Why 1: unexpected stops occur\nWhy 2: sensor faults are recorded\nWhy 3: sensor mounts vibrate loose\nWhy 4: inspection is not specified\nWhy 5: the maintenance standard omits the mount", height=130, key="t028_whys")
            countermeasure = st.text_input("Proposed countermeasure", "Add a mount inspection to the preventive checklist", key="t028_countermeasure")
            owner = st.text_input("Action owner", "Maintenance lead", key="t028_owner")
            due = st.text_input("Due date (YYYY-MM-DD)", "2026-11-01", key="t028_due")
            signature = _fingerprint(counts_text, problem, why_text, countermeasure, owner, due)
            saved = _run_engine_tool("T028", signature, "Build Pareto and root-cause record", lambda: analyze_pareto_root_cause(json.loads(counts_text), problem_statement=problem, why_chain=[x.strip() for x in why_text.splitlines() if x.strip()], countermeasure=countermeasure, owner=owner, due_date=due))
            if saved and saved["signature"] == signature:
                frame = saved["result"].get("pareto_summary")
                if isinstance(frame, pd.DataFrame) and not frame.empty and "Category" in frame and "Count" in frame:
                    st.bar_chart(frame.set_index("Category")["Count"])

        elif selected_id == "T029":
            st.warning("VALIDATION MODE — editable self-assessment, not a certified safety, quality or 5S audit.")
            st.markdown("### 5S workplace audit")
            default_5s = [
                {"category":"Sort","criterion":"Remove unnecessary items","score":1,"evidence":"synthetic example","owner":"Area owner","due_date":"2026-11-01"},
                {"category":"Set in Order","criterion":"Label storage locations","score":2,"evidence":"synthetic example","owner":"Shift lead","due_date":"2026-11-01"},
                {"category":"Shine","criterion":"Clean work stations","score":3,"evidence":"synthetic example","owner":"Shift lead","due_date":"2026-11-01"},
                {"category":"Standardize","criterion":"Display standard work","score":4,"evidence":"synthetic example","owner":"Process engineer","due_date":"2026-11-01"},
                {"category":"Sustain","criterion":"Run weekly reviews","score":4,"evidence":"synthetic example","owner":"Area owner","due_date":"2026-11-01"},
            ]
            items_text = st.text_area("5S checklist items as JSON", json.dumps(default_5s, ensure_ascii=False, indent=2), height=230, key="t029_items_json")
            signature = _fingerprint(items_text)
            saved = _run_engine_tool("T029", signature, "Score 5S audit checklist", lambda: assess_5s_audit(json.loads(items_text)))
            if saved and saved["signature"] == signature:
                frame = saved["result"].get("pillar_summary")
                if isinstance(frame, pd.DataFrame) and not frame.empty:
                    st.bar_chart(frame.set_index("5S pillar") if "5S pillar" in frame else frame)

        elif selected_id == "T030":
            st.warning("VALIDATION MODE — progress is not savings. Outcomes remain unverified without comparable baseline/post-change evidence and human review.")
            st.markdown("### Kaizen and A3 improvement record")
            title = st.text_input("A3 title", "Reduce cycle time", key="t030_title")
            problem = st.text_input("Problem statement", "Cycle time exceeds target", key="t030_problem")
            metric = st.text_input("Metric name", "Cycle time", key="t030_metric")
            unit = st.text_input("Metric unit", "minutes per unit", key="t030_unit")
            baseline = st.number_input("Baseline value", value=100.0, step=1.0, key="t030_baseline")
            target = st.number_input("Target value", value=80.0, step=1.0, key="t030_target")
            root = st.text_input("Root-cause hypothesis", "Setup standard is not consistently followed", key="t030_root")
            countermeasure = st.text_input("Countermeasure", "Standardize and audit setup steps", key="t030_countermeasure")
            owner = st.text_input("Owner", "Process engineer", key="t030_owner")
            due = st.text_input("Due date (YYYY-MM-DD)", "2026-11-15", key="t030_due")
            actual_known = st.checkbox("Record an actual after-change measurement", value=True, key="t030_actual_known")
            actual = st.number_input("Actual after-change value", value=90.0, step=1.0, key="t030_actual")
            baseline_evidence = st.text_input("Baseline evidence reference", "example-baseline-id", key="t030_baseline_evidence")
            post_evidence = st.text_input("Post-change evidence reference", "", key="t030_post_evidence")
            status = st.selectbox("Implementation status", ["Planned", "In Progress", "Implemented", "Verified", "Closed"], index=1, key="t030_status")
            signature = _fingerprint(title, problem, metric, unit, baseline, target, root, countermeasure, owner, due, actual_known, actual, baseline_evidence, post_evidence, status)
            _run_engine_tool("T030", signature, "Build A3 improvement record", lambda: build_kaizen_a3_record(title=title, problem_statement=problem, metric_name=metric, unit=unit, baseline_value=baseline, target_value=target, root_cause_hypothesis=root, countermeasure=countermeasure, owner=owner, due_date=due, actual_after_value=actual if actual_known else None, baseline_evidence=baseline_evidence, post_change_evidence=post_evidence, implementation_status=status))

        elif selected_id == "T031":
            st.warning("VALIDATION MODE — Individuals/Moving Range chart detects points outside calculated 3-sigma limits only; it does not certify stability.")
            st.markdown("### Statistical process control — Individuals / Moving Range")
            values_text = st.text_area("Chronological measurements (comma-separated)", "10, 11, 9, 10, 12, 11", height=80, key="t031_measurements")
            unit = st.text_input("Measurement unit", "mm", key="t031_unit")
            signature = _fingerprint(values_text, unit)
            saved = _run_engine_tool("T031", signature, "Calculate control limits", lambda: analyze_spc_individuals([float(x.strip()) for x in values_text.split(",") if x.strip()], unit=unit))
            if saved and saved["signature"] == signature:
                frame = saved["result"].get("series")
                if isinstance(frame, pd.DataFrame) and not frame.empty and {"Observation", "Measurement"}.issubset(frame.columns):
                    st.line_chart(frame.set_index("Observation")["Measurement"])

        elif selected_id == "T040":
            st.warning("VALIDATION MODE — scoped cost-of-poor-quality estimate, not a complete quality-cost ledger.")
            st.markdown("### Quality cost and defect analyzer")
            total_units = st.number_input("Total produced units", min_value=1.0, value=100.0, step=10.0, key="t040_total")
            defective = st.number_input("Defective units", min_value=0.0, value=10.0, step=1.0, key="t040_defective")
            scrap = st.number_input("Scrap units", min_value=0.0, value=2.0, step=1.0, key="t040_scrap")
            rework = st.number_input("Rework units", min_value=0.0, value=5.0, step=1.0, key="t040_rework")
            scrap_cost = st.number_input("Scrap cost per unit", min_value=0.0, value=20.0, step=1.0, key="t040_scrap_cost")
            rework_cost = st.number_input("Rework cost per unit", min_value=0.0, value=6.0, step=1.0, key="t040_rework_cost")
            inspect_cost = st.number_input("Inspection cost for period", min_value=0.0, value=120.0, step=10.0, key="t040_inspection_cost")
            currency = st.text_input("Currency code", "SAR", key="t040_currency")
            period = st.text_input("Period label", "Example month", key="t040_period")
            signature = _fingerprint(total_units, defective, scrap, rework, scrap_cost, rework_cost, inspect_cost, currency, period)
            _run_engine_tool("T040", signature, "Calculate scoped quality cost", lambda: analyze_quality_cost_defects(total_units, defective, scrap, rework, scrap_cost, rework_cost, inspect_cost, currency=currency, period=period))

        elif selected_id == "T042":
            st.warning("VALIDATION MODE — assumes complete failure/repair records; censoring and incomplete observation windows are not modeled.")
            st.markdown("### MTBF and MTTR analyzer")
            operating_hours = st.number_input("Accumulated operating hours", min_value=0.01, value=600.0, step=10.0, key="t042_operating_hours")
            repairs_text = st.text_input("Completed repair durations in hours (comma-separated)", "2, 1, 3", key="t042_repairs")
            signature = _fingerprint(operating_hours, repairs_text)
            _run_engine_tool("T042", signature, "Calculate MTBF and MTTR", lambda: analyze_mtbf_mttr(operating_hours, [float(x.strip()) for x in repairs_text.split(",") if x.strip()]))

        elif selected_id == "T056":
            st.warning("VALIDATION MODE — ABC/XYZ results depend on supplied cost/demand windows and editable thresholds.")
            st.markdown("### ABC/XYZ inventory analyzer")
            items_text = st.text_area("Inventory items as JSON (SKU, annual_demand, unit_cost, period_demand)", '[{"sku":"A","annual_demand":100,"unit_cost":8,"period_demand":[8,10,12]},{"sku":"B","annual_demand":50,"unit_cost":3,"period_demand":[1,10,3]},{"sku":"C","annual_demand":25,"unit_cost":2,"period_demand":[1,20,0]}]', height=130, key="t056_items_json")
            currency = st.text_input("Currency code", "SAR", key="t056_currency")
            signature = _fingerprint(items_text, currency)
            saved = _run_engine_tool("T056", signature, "Classify ABC/XYZ inventory", lambda: analyze_abc_xyz_inventory(json.loads(items_text), currency=currency))
            if saved and saved["signature"] == signature:
                frame = saved["result"].get("classification")
                if isinstance(frame, pd.DataFrame) and not frame.empty and {"SKU", "Annual usage value"}.issubset(frame.columns):
                    st.bar_chart(frame.set_index("SKU")["Annual usage value"])

        elif selected_id == "T075":
            st.warning("VALIDATION MODE — forecast thresholds alert on error; they do not diagnose cause or trigger retraining.")
            st.markdown("### Forecast and model drift monitor")
            predictions_text = st.text_input("Predictions (comma-separated)", "10, 20, 30", key="t075_predictions")
            actuals_text = st.text_input("Later actuals (same order and length)", "12, 18, 33", key="t075_actuals")
            max_mae = st.number_input("Maximum acceptable MAE", min_value=0.0, value=2.0, step=0.5, key="t075_max_mae")
            window = st.number_input("Trailing evaluation window (0 = all pairs)", min_value=0, value=0, step=1, key="t075_window")
            signature = _fingerprint(predictions_text, actuals_text, max_mae, window)
            saved = _run_engine_tool("T075", signature, "Evaluate forecast drift", lambda: monitor_forecast_drift([float(x.strip()) for x in predictions_text.split(",") if x.strip()], [float(x.strip()) for x in actuals_text.split(",") if x.strip()], max_mae, window=int(window) if window else None))
            if saved and saved["signature"] == signature:
                frame = saved["result"].get("series")
                if isinstance(frame, pd.DataFrame) and not frame.empty and {"Prediction", "Actual"}.issubset(frame.columns):
                    st.line_chart(frame[["Prediction", "Actual"]])

        elif selected_id == "T085":
            st.warning("VALIDATION MODE — balanced independent two-sample t-test assumptions are not automatically verified.")
            st.markdown("### Statistical power and sample-size planner")
            effect = st.number_input("Standardized effect size (Cohen's d; positive)", min_value=0.01, value=0.5, step=0.05, key="t085_effect")
            alpha = st.selectbox("Two-sided significance alpha", [0.01, 0.05, 0.10], index=1, key="t085_alpha")
            power = st.slider("Target statistical power", min_value=0.5, max_value=0.99, value=0.8, step=0.01, key="t085_power")
            max_n = st.number_input("Maximum n per group searched", min_value=10, max_value=10000, value=500, step=10, key="t085_max_n")
            signature = _fingerprint(effect, alpha, power, max_n)
            _run_engine_tool("T085", signature, "Estimate sample size", lambda: plan_two_sample_t_sample_size(effect_size=effect, alpha=alpha, target_power=power, max_n_per_group=int(max_n)))

        elif selected_id == "T021":
            st.warning("LIMITED VALIDATION MODE — these calculations do not replace a reviewed time-study protocol.")
            st.markdown("### Time study and standard time")
            st.caption("Enter observations in one consistent time unit. Demo observations are synthetic and should be replaced with approved study data.")
            observations_text = st.text_input("Observed times (comma-separated; same unit)", "0.50, 0.60, 0.55", key="t021_observations")
            rating = st.number_input("Performance rating (%)", min_value=0.01, max_value=300.0, value=110.0, step=1.0, key="t021_rating")
            allowance = st.number_input("Allowance (%)", min_value=0.0, max_value=99.9, value=15.0, step=0.5, key="t021_allowance")
            basis_label = st.selectbox("Allowance convention", ["Allowance as % of normal time", "Allowance as % of standard time"], key="t021_allowance_basis")
            basis = "normal_time" if basis_label == "Allowance as % of normal time" else "standard_time"
            signature = _fingerprint(observations_text, rating, allowance, basis)
            saved = _run_engine_tool(
                "T021", signature, "Calculate standard time",
                lambda: calculate_standard_time(
                    [float(part.strip()) for part in observations_text.split(",") if part.strip()],
                    rating, allowance, allowance_basis=basis,
                ),
            )
            if saved and saved["signature"] == signature:
                m = saved["result"]["metrics"]
                st.bar_chart(pd.DataFrame({"Time": [m["observed_mean"], m["normal_time"], m["standard_time"]]},
                                          index=["Observed mean", "Normal time", "Standard time"]))

        elif selected_id == "T023":
            st.warning("LIMITED VALIDATION MODE — capacity is theoretical and excludes unmodelled downtime, yield loss and resource constraints.")
            st.markdown("### Takt time and capacity")
            st.caption("All time values are in minutes; available time, demand and cycle time must refer to the same production period.")
            available_minutes = st.number_input("Net available time (minutes per period)", min_value=0.01, value=480.0, step=30.0, key="t023_available")
            demand_units = st.number_input("Demand (units in that period)", min_value=0.01, value=400.0, step=10.0, key="t023_demand")
            cycle_minutes = st.number_input("Measured cycle time (minutes per unit)", min_value=0.01, value=1.2, step=0.1, key="t023_cycle")
            signature = _fingerprint(available_minutes, demand_units, cycle_minutes)
            saved = _run_engine_tool(
                "T023", signature, "Calculate takt and capacity",
                lambda: calculate_takt_capacity(available_minutes, demand_units, cycle_minutes),
            )
            if saved and saved["signature"] == signature:
                m = saved["result"]["metrics"]
                st.bar_chart(pd.DataFrame({"Minutes": [m["takt_time_minutes_per_unit"], cycle_minutes]},
                                          index=["Takt time", "Cycle time"]))
                st.bar_chart(pd.DataFrame({"Units per period": [m["theoretical_capacity_units"], demand_units]},
                                          index=["Theoretical capacity", "Demand"]))

        elif selected_id == "T026":
            st.warning("LIMITED VALIDATION MODE — OEE conventions differ by plant; confirm planned-time and ideal-cycle definitions first.")
            st.markdown("### OEE and loss analysis")
            st.caption("Time inputs use minutes except ideal cycle time, which uses seconds per unit. Counts must use the same production window.")
            planned = st.number_input("Planned production time (minutes)", min_value=0.01, value=480.0, step=30.0, key="t026_planned")
            downtime = st.number_input("Downtime inside planned time (minutes)", min_value=0.0, value=30.0, step=5.0, key="t026_downtime")
            ideal_cycle = st.number_input("Ideal cycle time (seconds per unit)", min_value=0.01, value=30.0, step=1.0, key="t026_ideal_cycle")
            total_count = st.number_input("Total units produced", min_value=1, value=800, step=10, key="t026_total")
            good_count = st.number_input("Good units produced", min_value=0, value=760, step=10, key="t026_good")
            signature = _fingerprint(planned, downtime, ideal_cycle, total_count, good_count)
            saved = _run_engine_tool(
                "T026", signature, "Calculate OEE and losses",
                lambda: calculate_oee(planned, downtime, ideal_cycle, total_count, good_count),
            )
            if saved and saved["signature"] == signature:
                m = saved["result"]["metrics"]
                st.bar_chart(pd.DataFrame({"Percent": [m["availability_percent"], m["performance_percent"],
                                                          m["quality_percent"], m["oee_percent"]]},
                                          index=["Availability", "Performance", "Quality", "OEE"]))

        elif selected_id == "T032":
            st.warning("LIMITED VALIDATION MODE — capability indices assume rational subgroups and a representative process; normality/stability are not certified.")
            st.markdown("### Process capability")
            st.caption("Measurements must be in subgroup order. At least two complete subgroups are required.")
            measurements_text = st.text_input("Measurements (comma-separated)", "9, 10, 11, 9, 10, 11", key="t032_measurements")
            lsl = st.number_input("Lower specification limit (LSL)", value=6.0, step=0.5, key="t032_lsl")
            usl = st.number_input("Upper specification limit (USL)", value=14.0, step=0.5, key="t032_usl")
            subgroup_size = st.number_input("Subgroup size", min_value=2, max_value=50, value=3, step=1, key="t032_subgroup_size")
            signature = _fingerprint(measurements_text, lsl, usl, subgroup_size)
            saved = _run_engine_tool(
                "T032", signature, "Calculate Cp, Cpk, Pp and Ppk",
                lambda: calculate_process_capability(
                    [float(part.strip()) for part in measurements_text.split(",") if part.strip()],
                    lsl, usl, subgroup_size=int(subgroup_size),
                ),
            )
            if saved and saved["signature"] == signature:
                m = saved["result"]["metrics"]
                st.bar_chart(pd.DataFrame({"Index": [m["Cp"], m["Cpk"], m["Pp"], m["Ppk"]]},
                                          index=["Cp", "Cpk", "Pp", "Ppk"]))

        elif selected_id == "T055":
            st.warning("LIMITED VALIDATION MODE — inventory policy output depends on the demand, lead-time and service assumptions entered here.")
            st.markdown("### EOQ, safety stock and reorder point")
            annual_demand = st.number_input("Annual demand (units/year)", min_value=0.01, value=10000.0, step=500.0, key="t055_demand")
            order_cost = st.number_input("Order cost (per order)", min_value=0.01, value=50.0, step=5.0, key="t055_order_cost")
            holding_cost = st.number_input("Annual holding cost (per unit/year)", min_value=0.01, value=2.0, step=0.5, key="t055_holding")
            lead_time = st.number_input("Lead time (working days)", min_value=0.0, value=5.0, step=1.0, key="t055_lead")
            working_days = st.number_input("Working days per year", min_value=1.0, value=250.0, step=5.0, key="t055_working")
            daily_std = st.number_input("Daily demand standard deviation (units/day)", min_value=0.0, value=3.0, step=0.5, key="t055_std")
            z_value = st.number_input("One-sided service factor z (e.g. 1.645 ≈ 95%)", min_value=0.0, value=1.645, step=0.05, key="t055_z")
            signature = _fingerprint(annual_demand, order_cost, holding_cost, lead_time, working_days, daily_std, z_value)
            saved = _run_engine_tool(
                "T055", signature, "Calculate inventory policy",
                lambda: calculate_inventory_policy(
                    annual_demand, order_cost, holding_cost, lead_time,
                    working_days_per_year=working_days, daily_demand_std=daily_std, service_factor_z=z_value,
                ),
            )
            if saved and saved["signature"] == signature:
                m = saved["result"]["metrics"]
                st.bar_chart(pd.DataFrame({"Units": [m["EOQ_units"], m["safety_stock_units"], m["reorder_point_units"]]},
                                          index=["EOQ", "Safety stock", "Reorder point"]))

        elif selected_id == "T078":
            st.warning("LIMITED VALIDATION MODE — use a sourced, dated factor with a matching activity unit; this is not an audited carbon disclosure.")
            st.markdown("### Carbon emissions calculator")
            st.caption("No default emissions factor is supplied. You must provide its value, source, version, date and scope boundary.")
            quantity = st.number_input("Activity quantity", min_value=0.0, value=0.0, step=1.0, key="t078_quantity")
            factor = st.number_input("Factor (kg CO₂e per activity unit)", min_value=0.0, value=0.0, step=0.01, key="t078_factor")
            unit = st.text_input("Activity unit (must match factor unit)", value="kWh", key="t078_unit")
            factor_source = st.text_input("Factor source / citation", value="", key="t078_source")
            factor_version = st.text_input("Factor version / dataset year", value="", key="t078_version")
            factor_date = st.text_input("Factor date (YYYY-MM-DD)", value="", key="t078_date")
            boundary = st.text_input("Reporting scope / boundary", value="", key="t078_boundary")
            signature = _fingerprint(quantity, factor, unit, factor_source, factor_version, factor_date, boundary)
            saved = _run_engine_tool(
                "T078", signature, "Calculate supplied-factor emissions",
                lambda: calculate_carbon_emissions(
                    quantity, factor, activity_unit=unit, factor_source=factor_source,
                    factor_version=factor_version, factor_date=factor_date, scope_boundary=boundary,
                ),
            )
            if saved and saved["signature"] == signature:
                m = saved["result"]["metrics"]
                st.metric("Estimated emissions", f'{m["emissions_kg_co2e"]:,.3f} kg CO₂e')
                st.caption(f'{m["emissions_tonnes_co2e"]:,.6f} metric tonnes CO₂e')

        elif selected_id == "T081":
            st.warning("LIMITED VALIDATION MODE — confirm cash-flow timing, currency and discount-rate convention before using the result.")
            st.markdown("### Engineering economics")
            st.caption("Enter cash flows in period order beginning at period 0. Demo values are synthetic.")
            cash_flows_text = st.text_input("Cash flows (comma-separated; period 0 first)", "-1000, 500, 600", key="t081_flows")
            discount_rate = st.number_input("Discount rate (% per period)", min_value=-99.0, max_value=10000.0, value=10.0, step=1.0, key="t081_discount")
            currency_code = st.text_input("Three-letter currency code", value="SAR", max_chars=3, key="t081_currency")
            period_unit = st.selectbox("Cash-flow period", ["year", "month", "quarter"], key="t081_period")
            signature = _fingerprint(cash_flows_text, discount_rate, currency_code, period_unit)
            saved = _run_engine_tool(
                "T081", signature, "Calculate NPV, IRR and payback",
                lambda: calculate_engineering_economics(
                    [float(part.strip()) for part in cash_flows_text.split(",") if part.strip()],
                    discount_rate, currency_code=currency_code, period_unit=period_unit,
                ),
            )
            if saved and saved["signature"] == signature:
                m = saved["result"]["metrics"]
                if m.get("NPV") is not None:
                    st.metric("Net present value", f'{m["NPV"]:,.2f} {saved["result"]["units"]["npv"]}')
                if m.get("IRR_percent") is not None:
                    st.metric("Internal rate of return", f'{m["IRR_percent"]:,.3f}%')
                if m.get("simple_payback_periods") is not None:
                    st.metric("Simple payback", f'{m["simple_payback_periods"]:,.3f} {period_unit}s')

        elif selected_id == "T066":
            st.warning("LIMITED VALIDATION MODE — check the result against an independent reference before using it for an operational decision.")
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


            with st.expander("Cutting-stock pattern optimisation (MILP)", expanded=False):
                st.caption("Uses a constrained integer optimization model and an explicit kerf allowance. Solver output must be checked against real stock, saw and production rules before use.")
                stock_length = st.number_input("Raw stock length (same units as part lengths)", min_value=0.01, value=12.0, step=1.0, key="t066_cut_stock_length")
                kerf = st.number_input("Kerf per cut (same length units)", min_value=0.0, value=0.0, step=0.01, key="t066_cut_kerf")
                parts_text = st.text_area("Parts (JSON list with name, length and integer quantity)", value='[{"name":"A","length":6,"quantity":4}]', height=110, key="t066_cut_parts_json")
                cut_signature = _fingerprint(stock_length, kerf, parts_text)
                def _cutting_stock_calculation():
                    parts = json.loads(parts_text)
                    if not isinstance(parts, list):
                        raise ValueError("Parts must be a JSON list.")
                    return solve_cutting_stock(stock_length, parts, kerf=kerf)
                saved_cut = _run_engine_tool("T066_CUT", cut_signature, "Optimise cutting-stock patterns", _cutting_stock_calculation)
                if saved_cut and saved_cut["signature"] == cut_signature:
                    cut_result = saved_cut["result"]
                    if "stock_count" in cut_result:
                        st.metric("Raw stock bars", cut_result["stock_count"])
                    if "waste_length" in cut_result:
                        st.metric("Total estimated waste", f'{cut_result["waste_length"]:,.3f}')

        elif selected_id == "T076":
            st.warning("LIMITED VALIDATION MODE — this is event-log exploration, not a certified process-conformance assessment.")
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
