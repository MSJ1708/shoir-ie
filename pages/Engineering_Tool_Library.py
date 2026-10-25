"""Additive Engineering Tool Library for Shoir-IE.

This page is status-led and checks the logged-in tier before displaying actions.
Only VERIFIED_WORKING is a production-readiness assertion. The limited-validation
methods are expressly labelled and remain unverified until end-to-end acceptance passes;
they remain IMPLEMENTED_NEEDS_VALIDATION until authenticated E2E and independent
acceptance checks pass. Existing routes and navigation are left unchanged.
"""
import base64
import hashlib
import io
import json
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from shoir_tool_run_persistence import persist_tool_run_record
from shoir_100_tool_statistics_engines import ordinary_least_squares, supported_t_test
from shoir_100_tool_quality_engines import build_capa_8d_record, score_fmea_register
from shoir_100_tool_asset_engines import plan_preventive_maintenance, plan_spare_part_criticality, score_supplier_performance
from shoir_100_tool_sustainability_engines import analyze_energy_intensity, analyze_water_waste_efficiency, calculate_roi_evidence
from shoir_100_tool_decision_engines import (build_hazard_register, reconcile_sop_scenario, solve_assignment_cost_matrix, compare_capacity_scenarios, score_project_portfolio, build_hypothesis_evidence_register, evaluate_kpi_thresholds)
from shoir_100_tool_data_quality_engines import CANONICAL_INDUSTRIAL_FIELDS, map_industrial_fields, analyze_safety_incident_trends
from shoir_100_tool_lineage_engines import build_dataset_lineage_record
from shoir_100_tool_reliability_engines import fit_weibull_reliability
from shoir_100_tool_solver_diagnostics import solve_and_diagnose_linear_program
from shoir_100_tool_maintenance_engine import optimize_maintenance_backlog
from shoir_100_tool_msa_engine import analyze_crossed_gage_rr
from shoir_100_tool_anomaly_engine import screen_time_series_anomalies
from shoir_100_tool_simulation_engine import simulate_serial_flow_line
from shoir_100_tool_reproducibility import build_reproducibility_pack
from shoir_100_tool_research_report import build_research_methods_report
from shoir_100_tool_power_engine import plan_t_test_power

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
from shoir_100_tool_operations_engines import (
    analyze_bottleneck, analyze_mm1_queue, balance_production_line, build_value_stream_metrics,
)
from shoir_100_tool_planning_engines import (
    evaluate_acceptance_sampling_plan, forecast_demand_series,
    plan_material_requirements, simulate_monte_carlo_outcome,
)
from shoir_100_tool_extended_engines import (
    analyze_abc_xyz_inventory, analyze_mtbf_mttr, analyze_pareto_root_cause,
    analyze_quality_cost_defects, analyze_spc_individuals, analyze_work_sampling,
    assess_5s_audit, build_kaizen_a3_record, convert_units_or_currency,
    generate_synthetic_industrial_data, monitor_forecast_drift, plan_two_sample_t_sample_size,
    preview_data_join, process_time_series, profile_data_quality, solve_cutting_stock,
)

def _fingerprint(*values):
    return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()


def _run_engine_tool(tool_id, signature, button_label, calculation):
    """Run a deterministic validation-mode method after server-side entitlement enforcement."""
    # Defend the action boundary independently of card visibility. T066_CUT is a
    # second method under canonical target T066 and must inherit the same policy.
    canonical_tool_id = str(tool_id).split("_", 1)[0]
    decision = target_tool_access_decision(canonical_tool_id, st.session_state.get("user_tier"))
    if not decision["allowed"]:
        st.warning(
            f"Execution denied for {canonical_tool_id}. Required tier: "
            f"{decision.get('required_tier') or 'unresolved policy'}."
        )
        return None
    if st.button(button_label, key=f"{tool_id}_run_button", type="primary"):
        try:
            outcome = calculation()
        except RuntimeError:
            st.error(
                "The calculation or optimization solver could not complete. "
                "The last successful result was preserved; review solver availability, status and constraints."
            )
        except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
            st.error(
                f"Input validation or calculation was not completed: {exc}. "
                "The last successful result was preserved."
            )
        else:
            status = outcome.get("status") if isinstance(outcome, dict) else None
            if isinstance(status, str) and status.strip() and status.upper() not in {"FAILED", "ERROR", "INVALID"}:
                result_key = f"shoir_{tool_id}_result"
                st.session_state[result_key] = {
                    "signature": signature,
                    "source": "MANUAL INPUT — not independently verified; defaults are SYNTHETIC",
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                    "result": outcome,
                    "persistence_status": "SAVE_PENDING",
                }
                # Save through the existing owner-scoped workspace backend. A
                # failed save never discards the calculated in-session result.
                persist_tool_run_record(
                    st.session_state.get("current_user", ""),
                    st.session_state,
                    result_key,
                )
            else:
                st.error("The method returned no usable result status; the prior result was preserved.")

    saved = st.session_state.get(f"shoir_{tool_id}_result")
    if not isinstance(saved, dict):
        return None
    if saved.get("signature") != signature:
        st.warning("STALE — one or more inputs changed. Rerun before using this saved result.")
    result = saved.get("result", {})
    persistence_status = saved.get("persistence_status", "SESSION_ONLY_SAVE_FAILED")
    persistence_labels = {
        "MANAGED_WORKSPACE_SAVED": "saved to managed workspace",
        "LOCAL_SQLITE_SAVED_MAY_BE_EPHEMERAL": "local development save only — may be ephemeral",
        "SESSION_ONLY_SAVE_FAILED": "session-only — workspace save failed",
        "SESSION_ONLY_PERSISTENCE_MODE_UNVERIFIED": "session-only — persistence mode unverified",
    }
    st.caption(
        f"Result: {result.get('status', 'UNRESOLVED')} · {saved.get('source', 'UNVERIFIED')} · "
        f"executed {saved.get('executed_at', 'timestamp unavailable')} · "
        f"{persistence_labels.get(persistence_status, 'persistence status unverified')}"
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
        # Scalar metrics have mixed types by design (numeric, text, boolean, null).
        # Render them consistently as text so Arrow does not try to coerce every
        # value into the first observed numeric/string type.
        metric_rows = [
            {"Metric": key, "Value": "—" if value is None else str(value)}
            for key, value in metrics.items()
        ]
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
# The catalog is public/read-only; internal routing details and all calculation actions
# remain behind authentication and the target-specific server-side entitlement check.
is_authenticated = bool(st.session_state.get("authenticated")) and bool(
    str(st.session_state.get("current_user", "")).strip()
)
tier = str(st.session_state.get("user_tier", "")) if is_authenticated else ""
if not is_authenticated:
    st.info(
        "PUBLIC READ-ONLY PREVIEW — browse the 100 target capabilities, intended inputs/outputs, "
        "tier and readiness. Sign in to view internal routing details or run eligible validation methods."
    )
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
    if is_authenticated:
        rows.append({
            "ID": item["tool_id"], "Capability": item["canonical_name"],
            "Workbench": item["workbench"], "Minimum tier": item["target_minimum_tier"],
            "Package access": "Allowed" if d["allowed"] else "Restricted",
            "Implementation status": item["implementation_status"],
            "Executable in target registry": "Yes" if e["executable"] else "No — acceptance pending",
            "Existing candidate route": item["existing_module_or_route"],
        })
    else:
        rows.append({
            "ID": item["tool_id"], "Capability": item["canonical_name"],
            "Workbench": item["workbench"], "Minimum tier": item["target_minimum_tier"],
            "Readiness status": item["implementation_status"],
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
        if is_authenticated:
            st.markdown("**Candidate existing route**")
            st.write(item["existing_module_or_route"])
            st.markdown("**Current readiness**")
            st.write(item["implementation_status"])
            st.markdown("**Source candidates**")
            st.code("\n".join(item["source_files"]), language="text")
            st.markdown("**Outstanding gap**")
            st.write(item["remaining_gap"])
        else:
            st.markdown("**Minimum tier**")
            st.write(item["target_minimum_tier"])
            st.markdown("**Current readiness**")
            st.write(item["implementation_status"])
    if not is_authenticated:
        st.info("Sign in to Shoir-IE to use eligible tools. This public preview cannot execute calculations or open protected workspace routes.")
        st.stop()

    decision = target_tool_execution_decision(selected_id, tier)
    if not decision["allowed"]:
        st.warning(f'This package does not grant this target capability. Required tier: {decision["required_tier"]}.')
        # Do not render specialist inputs/actions or expose previously shown output
        # for a denied target. Direct calls are also guarded in _run_engine_tool.
        st.stop()
    else:
        if not decision["executable"]:
            st.warning("This target cannot be marked executable in the new library until its acceptance tests and authenticated end-to-end evidence pass. A separately entitled existing route may still be opened below.")
        # Offer a route hand-off only to a named legacy module already available
        # under the user's real tier. Do not use the target label to widen access.
        if item["implementation_status"] in {
            "IMPLEMENTED_NEEDS_VALIDATION", "FOUNDATION_ONLY", "EXTERNAL_CONFIGURATION_REQUIRED"
        }:
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

        if selected_id == "T020":
            st.warning("LIMITED VALIDATION MODE — the hash detects changes in the supplied table and metadata. It is not a digital signature, proof of authenticity, or automatic control over all legacy downstream routes.")
            st.markdown("### Dataset Versioning and Lineage")
            st.caption("Record the dataset version, source metadata, transformations and any downstream runs whose dataset fingerprint you know. Raw dataset cells are not embedded in the lineage record.")
            dataset_name = st.text_input("Dataset name", "Production Example", key="t020_dataset_name")
            source_type = st.selectbox("Source provenance", ["IMPORTED", "LIVE", "SYNTHETIC", "USER_ENTERED"], index=2, key="t020_source_type")
            source_reference = st.text_input("Source file / system reference", "synthetic-example.csv", key="t020_source_reference")
            parent_version = st.text_input("Parent version ID (optional)", "", key="t020_parent_version")
            dataset_frame = st.data_editor(pd.DataFrame({
                "period":["P1","P2","P3"],
                "units_produced":[100,110,95],
                "downtime_minutes":[5.0,3.0,12.0],
            }), num_rows="dynamic", use_container_width=True, key="t020_dataset_editor", hide_index=True)
            transformations = st.data_editor(pd.DataFrame([
                {"step":"01","operation":"Validate required columns","method_version":"1"},
                {"step":"02","operation":"Review units and missing values","method_version":"1"},
            ]), num_rows="dynamic", use_container_width=True, key="t020_transformations_editor", hide_index=True)
            st.caption("Downstream run fingerprints are optional. Provide the exact dataset fingerprint recorded by a prior run; empty fingerprints cannot be declared current or stale.")
            runs_frame = st.data_editor(pd.DataFrame(columns=["run_id","dataset_fingerprint"]), num_rows="dynamic",
                                         use_container_width=True, key="t020_downstream_runs", hide_index=True)
            signature = _fingerprint(
                dataset_name, source_type, source_reference, parent_version,
                dataset_frame.to_json(orient="split", date_format="iso"),
                transformations.to_json(orient="split", date_format="iso"),
                runs_frame.to_json(orient="split", date_format="iso"),
            )
            def _calculate_t020():
                prior = list(st.session_state.get("shoir_dataset_lineage_versions", []))
                record = build_dataset_lineage_record(
                    dataset_frame, dataset_name=dataset_name, source_type=source_type,
                    source_reference=source_reference, parent_version_id=parent_version,
                    transformations=transformations.to_dict(orient="records"),
                    downstream_runs=runs_frame,
                    prior_versions=prior,
                )
                if not prior or prior[-1].get("version_id") != record["version_id"]:
                    updated_history = [*prior, record][-100:]
                    st.session_state["shoir_dataset_lineage_versions"] = updated_history
                record["version_history_count"] = len(st.session_state.get("shoir_dataset_lineage_versions", []))
                return record
            saved = _run_engine_tool("T020", signature, "Create dataset version and check lineage", _calculate_t020)
            if saved and saved.get("signature") == signature:
                record = saved["result"]
                st.metric("Dataset version", record["version_id"])
                st.code(record["dataset_fingerprint"], language="text")
                st.caption(
                    f'{record["row_count"]:,} rows · {record["column_count"]:,} columns · '
                    f'{record["metrics"]["transformation_count"]} transformations · '
                    f'{record["metrics"]["stale_downstream_run_count"]} stale linked runs · '
                    f'{record.get("version_history_count", 0)} versions retained in workspace state'
                )
                if record["metrics"]["changed_since_previous_version"]:
                    st.warning("VERSION CHANGED — prior source/transform metadata or dataset content differs from the last recorded version.")
                if record["stale_downstream_runs"]:
                    st.dataframe(pd.DataFrame(record["stale_downstream_runs"]), use_container_width=True, hide_index=True)
                if record["uncheckable_downstream_run_ids"]:
                    st.info("Run freshness could not be evaluated for: " + ", ".join(record["uncheckable_downstream_run_ids"]))
                st.dataframe(pd.DataFrame(record["schema"]), use_container_width=True, hide_index=True)
                st.dataframe(pd.DataFrame(record["transformations"]), use_container_width=True, hide_index=True)

        elif selected_id == "T015":
            st.warning("VALIDATION MODE — mapping suggestions are based on field names, not proven data semantics. Confirm units and business definitions before using downstream calculations.")
            st.markdown("### Industrial Field Mapper")
            st.caption("Original field names are retained. Upload an optional CSV or edit the synthetic example, then confirm each suggested canonical field.")
            upload = st.file_uploader("Optional industrial source CSV", type=["csv"], key="t015_field_upload")
            source = "SYNTHETIC"
            sample = pd.DataFrame({
                "Asset ID":["A-01","A-02","A-03"],
                "Produced Units":[120,95,110],
                "downtime_minutes":[5.0,12.0,4.0],
                "kWh":[28.0,24.0,27.0],
                "custom_field":["example","example","example"],
            })
            editor_key = "t015_field_synthetic_editor"
            upload_error = None
            if upload is not None:
                try:
                    raw = upload.getvalue()
                    if len(raw) > 10 * 1024 * 1024:
                        raise ValueError("CSV exceeds the 10 MiB limit")
                    sample = pd.read_csv(io.BytesIO(raw))
                    if sample.empty:
                        raise ValueError("CSV has no data rows")
                    if sample.shape[1] > 200:
                        raise ValueError("CSV has more than 200 columns")
                    source = "IMPORTED"
                    editor_key = "t015_field_import_" + hashlib.sha256(raw).hexdigest()[:12]
                except Exception as exc:
                    upload_error = f"Source CSV rejected ({type(exc).__name__}). Previous source/result is unchanged."
            if upload_error:
                st.error(upload_error)
            if sample.shape[1] == 0:
                st.info("Provide at least one source column.")
            else:
                source_frame = st.data_editor(sample, num_rows="dynamic", use_container_width=True, key=editor_key, hide_index=True)
                field_ids = list(CANONICAL_INDUSTRIAL_FIELDS)
                manual_mapping = {}
                if source_frame.columns.tolist():
                    st.markdown("**Column mapping review**")
                    for column in source_frame.columns:
                        suggested = map_industrial_fields([str(column)])["mapping_table"].iloc[0]["canonical_field"]
                        options = ["Auto-suggest (review)", "Leave unmapped", *field_ids]
                        default_option = "Auto-suggest (review)" if suggested else "Leave unmapped"
                        selected = st.selectbox(
                            f"{column} → canonical field",
                            options,
                            index=options.index(default_option),
                            format_func=lambda value, suggestion=suggested: (
                                f"Auto-suggest: {CANONICAL_INDUSTRIAL_FIELDS[suggestion]['label']}" if value == "Auto-suggest (review)" and suggestion
                                else ("Auto-suggest (no match)" if value == "Auto-suggest (review)" else ("Leave unmapped" if value == "Leave unmapped" else CANONICAL_INDUSTRIAL_FIELDS[value]["label"]))
                            ),
                            key="t015_map_" + hashlib.sha1(str(column).encode("utf-8")).hexdigest()[:12],
                        )
                        if selected == "Auto-suggest (review)":
                            continue
                        manual_mapping[str(column)] = "" if selected == "Leave unmapped" else selected
                signature = _fingerprint(source_frame.to_json(orient="split", date_format="iso"), manual_mapping, source)
                saved = None if upload_error else _run_engine_tool(
                    "T015", signature, "Preview canonical field mapping",
                    lambda: map_industrial_fields([str(col) for col in source_frame.columns], manual_mapping),
                )
                if saved and saved.get("signature") == signature:
                    table = saved["result"].get("mapping_table")
                    if isinstance(table, pd.DataFrame):
                        st.dataframe(table, use_container_width=True, hide_index=True)
                    st.caption(
                        f"Source: {source} · original columns preserved · "
                        f"canonical dictionary: {saved['result'].get('metrics', {}).get('canonical_dictionary_version')}"
                    )

        elif selected_id == "T016":
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

        elif selected_id == "T034":
            st.warning("LIMITED VALIDATION MODE — this evaluates a supplied sampling plan and its operating-characteristic curve; it does not select a plan to satisfy a quality standard.")
            st.markdown("### Acceptance sampling planner")
            st.caption("Finite-lot, random sampling without replacement. AQL and LTPD risks depend on the supplied lot size, sample size and acceptance number.")
            c1, c2, c3 = st.columns(3)
            with c1:
                lot_size = st.number_input("Lot size (units)", min_value=1, max_value=10000000, value=1000, step=100, key="t034_lot")
            with c2:
                sample_size = st.number_input("Sample size (units)", min_value=1, max_value=int(lot_size), value=min(50, int(lot_size)), step=1, key="t034_sample")
            with c3:
                acceptance_number = st.number_input("Acceptance number c", min_value=0, max_value=max(0, int(sample_size)-1), value=min(1, max(0, int(sample_size)-1)), step=1, key="t034_accept")
            c4, c5 = st.columns(2)
            with c4:
                aql = st.number_input("AQL reference (%)", min_value=0.0, max_value=99.0, value=1.0, step=0.5, key="t034_aql")
            with c5:
                ltpd = st.number_input("LTPD reference (%)", min_value=0.1, max_value=100.0, value=5.0, step=0.5, key="t034_ltpd")
            signature = _fingerprint(int(lot_size), int(sample_size), int(acceptance_number), aql, ltpd)
            saved = _run_engine_tool(
                "T034", signature, "Evaluate single-sampling plan",
                lambda: evaluate_acceptance_sampling_plan(int(lot_size), int(sample_size), int(acceptance_number), aql, ltpd),
            )
            if saved and saved["signature"] == signature:
                result = saved["result"]
                metrics = result.get("metrics", {})
                st.dataframe(pd.DataFrame([{
                    "P(accept | AQL)": metrics.get("probability_of_acceptance_at_aql"),
                    "Producer risk α": metrics.get("producer_risk_at_aql"),
                    "P(accept | LTPD)": metrics.get("probability_of_acceptance_at_ltpd"),
                    "Consumer risk β": metrics.get("consumer_risk_at_ltpd"),
                }]), use_container_width=True, hide_index=True)
                oc = pd.DataFrame(result.get("operating_characteristic", []))
                if not oc.empty:
                    st.line_chart(oc.set_index("defective_percent")["probability_of_acceptance"])
                st.caption("Percent defective is rounded to a whole defective-unit count for the finite lot; verify the required sampling standard before releasing lots.")

        elif selected_id == "T036":
            st.warning("LIMITED VALIDATION MODE — numeric-only OLS with classical standard errors. Review residuals, linearity, independence and constant-variance assumptions; association is not causation.")
            st.markdown("### Regression and ANOVA Studio — OLS")
            st.caption("All rows must be complete finite numeric values. Categorical encoding, imputation, robust standard errors and automatic predictor selection are not implemented.")
            regression_frame = st.data_editor(
                pd.DataFrame({"Load": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "Output": [3.0, 5.0, 7.0, 9.0, 11.0, 13.0]}),
                num_rows="dynamic", use_container_width=True, key="t036_regression_data", hide_index=True,
            )
            regression_cols = list(regression_frame.columns)
            if len(regression_cols) >= 2:
                c1, c2 = st.columns(2)
                with c1:
                    response_col = st.selectbox("Response variable", regression_cols, index=1, key="t036_response")
                with c2:
                    predictor_cols = st.multiselect(
                        "Predictor variables", [col for col in regression_cols if col != response_col],
                        default=[regression_cols[0]], key="t036_predictors",
                    )
                alpha = st.selectbox("Significance level α", [0.01, 0.05, 0.10], index=1, key="t036_alpha")
                signature = _fingerprint(
                    regression_frame.to_json(orient="split", date_format="iso"),
                    response_col, predictor_cols, alpha,
                )
                saved = _run_engine_tool(
                    "T036", signature, "Fit OLS model",
                    lambda: ordinary_least_squares(regression_frame, response_col, predictor_cols, alpha=alpha),
                )
                if saved and saved["signature"] == signature:
                    result = saved["result"]
                    metrics = result.get("metrics", {})
                    st.dataframe(result.get("coefficient_table", pd.DataFrame()), use_container_width=True, hide_index=True)
                    st.caption(
                        f"R²: {metrics.get('R_squared', float('nan')):.4f} · "
                        f"Adjusted R²: {metrics.get('adjusted_R_squared', float('nan')):.4f} · "
                        f"Observations: {metrics.get('observations', 0)} · "
                        f"Residual df: {metrics.get('residual_degrees_of_freedom', 0)}"
                    )
                    residual_table = result.get("prediction_residuals", pd.DataFrame())
                    if isinstance(residual_table, pd.DataFrame) and not residual_table.empty:
                        st.scatter_chart(residual_table, x="Fitted", y="Residual")
                        st.dataframe(residual_table, use_container_width=True, hide_index=True)

        elif selected_id == "T037":
            st.warning("RESEARCH PACK · LIMITED VALIDATION MODE — supported t-tests only. A p-value does not prove practical importance or causation; review the study design and assumptions.")
            st.markdown("### Hypothesis Testing Assistant")
            test_type = st.selectbox(
                "Supported test", ["one_sample", "independent_welch", "paired"],
                format_func=lambda value: {
                    "one_sample": "One-sample Student t-test",
                    "independent_welch": "Independent Welch two-sample t-test",
                    "paired": "Paired t-test (A − B)",
                }[value], key="t037_test_type",
            )
            sample_a_text = st.text_area(
                "Sample A values (comma-separated; use measured observations)",
                "2, 4, 6, 5, 7, 8", height=80, key="t037_sample_a",
            )
            sample_b_text = ""
            sample_b = None
            if test_type != "one_sample":
                sample_b_text = st.text_area(
                    "Sample B values (comma-separated; paired order must match for paired tests)",
                    "1, 3, 4, 5, 5, 7", height=80, key="t037_sample_b",
                )
                try:
                    sample_b = [float(token.strip()) for token in sample_b_text.split(",") if token.strip()]
                except ValueError:
                    sample_b = []
            c1, c2, c3 = st.columns(3)
            with c1:
                null_difference = st.number_input("Null mean difference", value=0.0, step=0.5, key="t037_null")
            with c2:
                alpha = st.selectbox("Alpha", [0.01, 0.05, 0.10], index=1, key="t037_alpha")
            with c3:
                alternative = st.selectbox("Alternative", ["two-sided", "greater", "less"], key="t037_alternative")
            try:
                sample_a = [float(token.strip()) for token in sample_a_text.split(",") if token.strip()]
            except ValueError:
                sample_a = []
            signature = _fingerprint(test_type, sample_a_text, sample_b_text, null_difference, alpha, alternative)
            def _calculate_t037():
                return supported_t_test(
                    sample_a, test_type=test_type, sample_b=sample_b,
                    null_difference=null_difference, alpha=alpha, alternative=alternative,
                )
            saved = _run_engine_tool("T037", signature, "Run supported hypothesis test", _calculate_t037)
            if saved and saved["signature"] == signature:
                metrics = saved["result"].get("metrics", {})
                c1, c2, c3 = st.columns(3)
                c1.metric("t statistic", f'{metrics.get("t_statistic", float("nan")):.4g}')
                c2.metric("p-value", f'{metrics.get("p_value", float("nan")):.4g}')
                c3.metric("Degrees of freedom", f'{metrics.get("degrees_of_freedom", float("nan")):.3g}')
                st.dataframe(pd.DataFrame([{
                    "Estimated mean difference": metrics.get("estimated_mean_difference"),
                    "Null difference": metrics.get("null_difference"),
                    "Confidence interval lower": metrics.get("confidence_interval_lower"),
                    "Confidence interval upper": metrics.get("confidence_interval_upper"),
                    "Cohen's d": metrics.get("cohens_d"),
                    "Alpha": metrics.get("alpha"),
                    "Alternative": metrics.get("alternative"),
                }]), use_container_width=True, hide_index=True)

        elif selected_id == "T038":
            st.warning("LIMITED VALIDATION MODE — FMEA ratings are subjective screening scores. Review high-severity hazards separately; an RPN is not a probability or safety acceptance decision.")
            st.markdown("### FMEA Manager")
            st.caption("Edit one row per failure mode. Score severity, occurrence and detection from 1 (lower) to 10 (higher); action status and dates are retained in the saved run.")
            fmea_default = pd.DataFrame([
                {"failure_mode":"Seal leak","effect":"Fluid loss","cause":"Wear","current_controls":"Routine inspection","severity":8,"occurrence":3,"detection":4,"recommended_action":"Review seal interval","owner":"Maintenance lead","due_date":"2026-11-01","action_status":"Open"},
                {"failure_mode":"Guard missing","effect":"Exposure to moving parts","cause":"Guard bypass","current_controls":"Shift check","severity":10,"occurrence":2,"detection":2,"recommended_action":"Restore guard and inspect interlock","owner":"Safety lead","due_date":"2026-10-30","action_status":"In Progress"},
            ])
            fmea_frame = st.data_editor(fmea_default, num_rows="dynamic", use_container_width=True, key="t038_fmea_editor", hide_index=True)
            signature = _fingerprint(fmea_frame.to_json(orient="split", date_format="iso"))
            def _calculate_t038():
                result = score_fmea_register(fmea_frame)
                history = list(st.session_state.get("shoir_fmea_revision_history", []))
                previous = st.session_state.get("shoir_T038_result")
                if isinstance(previous, dict) and previous.get("signature") and previous.get("signature") != signature:
                    prior_result = previous.get("result", {})
                    prior_register = prior_result.get("register")
                    if isinstance(prior_register, pd.DataFrame):
                        history.append({
                            "signature": previous["signature"],
                            "saved_at": previous.get("executed_at", ""),
                            "row_count": int(len(prior_register)),
                            "prior_register_json": prior_register.to_json(orient="records", date_format="iso"),
                        })
                result["revision_history"] = history[-50:]
                st.session_state["shoir_fmea_revision_history"] = history[-50:]
                return result
            saved = _run_engine_tool("T038", signature, "Score FMEA register", _calculate_t038)
            if saved and saved.get("signature") == signature:
                st.caption(f'Revision snapshots available: {len(saved["result"].get("revision_history", []))}')
                st.info("These rankings must be reviewed using your approved FMEA scoring criteria. No automatic risk acceptance is inferred.")

        elif selected_id == "T039":
            st.warning("LIMITED VALIDATION MODE — the tool organizes CAPA/8D records but does not independently establish root cause, approval or action effectiveness.")
            st.markdown("### CAPA and 8D Manager")
            prior_records = st.session_state.get("shoir_capa_8d_register", [])
            if prior_records:
                st.caption("Saved CAPA/8D register (revision history is retained by record ID).")
                st.dataframe(pd.DataFrame([{
                    "Record ID": record.get("record_id"),
                    "Revision": record.get("revision", 1),
                    "Problem": record.get("problem_statement"),
                    "Owner": record.get("owner"),
                    "Status": record.get("status"),
                    "Due date": record.get("due_date"),
                    "Evidence state": record.get("evidence_state"),
                } for record in prior_records]), use_container_width=True, hide_index=True)
            c1, c2 = st.columns(2)
            with c1:
                record_id = st.text_input("Record ID", "CAPA-001", key="t039_record_id")
                problem = st.text_input("Problem statement", "Repeat defect on assembly line", key="t039_problem")
                owner = st.text_input("Accountable owner", "Quality lead", key="t039_owner")
                team = st.text_input("Cross-functional team", "Quality, production, maintenance", key="t039_team")
                opened = st.text_input("Opened date (YYYY-MM-DD)", "2026-10-24", key="t039_opened")
                due = st.text_input("Due date (YYYY-MM-DD)", "2026-11-20", key="t039_due")
                status = st.selectbox("Lifecycle status", ["Open", "Containment", "Root Cause Analysis", "Corrective Action", "Verification", "Closed"], key="t039_status")
            with c2:
                containment = st.text_area("Containment / immediate correction", "Segregate affected stock and inspect the current lot.", key="t039_containment")
                root_cause = st.text_area("Root-cause finding (state evidence)", "", key="t039_root_cause")
                corrective = st.text_area("Corrective action", "", key="t039_corrective")
                verification = st.text_input("Effectiveness evidence reference", "", key="t039_verification")
                prevention = st.text_area("Prevent recurrence / update standard", "", key="t039_prevention")
                lessons = st.text_area("Lessons learned / related processes", "", key="t039_lessons")
                verifier = st.text_input("Verifier name (user-entered, not authenticated)", "", key="t039_verifier")
                verification_date = st.text_input("Verification date (YYYY-MM-DD)", "", key="t039_verification_date")
            signature = _fingerprint(record_id, problem, owner, team, opened, due, status, containment, root_cause, corrective, verification, prevention, lessons, verifier, verification_date)
            def _calculate_t039():
                result = build_capa_8d_record(
                    record_id=record_id, problem_statement=problem, owner=owner,
                    opened_date=opened, due_date=due, status=status, team=team,
                    containment=containment, root_cause=root_cause,
                    corrective_actions=corrective, verification_evidence=verification,
                    preventive_action=prevention, lessons_learned=lessons,
                    verified_by=verifier, verification_date=verification_date,
                )
                record = dict(result["record"])
                register = list(st.session_state.get("shoir_capa_8d_register", []))
                existing_index = next((i for i, item in enumerate(register) if item.get("record_id") == record_id.strip()), None)
                if existing_index is None:
                    record["revision"] = 1
                    record["revision_history"] = []
                    register.append(record)
                else:
                    prior = register[existing_index]
                    history = list(prior.get("revision_history", []))
                    prior_snapshot = {k: v for k, v in prior.items() if k != "revision_history"}
                    history.append(prior_snapshot)
                    record["revision"] = int(prior.get("revision", 1)) + 1
                    record["revision_history"] = history[-50:]
                    register[existing_index] = record
                st.session_state["shoir_capa_8d_register"] = register
                result["record"] = record
                result["register"] = pd.DataFrame([{
                    "record_id": item.get("record_id"),
                    "revision": item.get("revision", 1),
                    "problem_statement": item.get("problem_statement"),
                    "owner": item.get("owner"),
                    "status": item.get("status"),
                    "due_date": item.get("due_date"),
                    "evidence_state": item.get("evidence_state"),
                } for item in register])
                return result
            saved = _run_engine_tool("T039", signature, "Save CAPA/8D record", _calculate_t039)
            if saved and saved.get("signature") == signature:
                st.json(saved["result"].get("record", {}))
                st.caption("User-entered evidence and reviewer names remain unverified by Shoir-IE.")

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

        elif selected_id == "T041":
            st.warning("LIMITED VALIDATION MODE — two-parameter Weibull maximum likelihood assumes independent comparable lifetimes and non-informative right-censoring. Confidence intervals, model selection and formal fit tests are not included.")
            st.markdown("### Weibull Reliability Analyzer")
            st.caption("Enter time-to-failure/exposure in one consistent unit. Set event_observed = 1 for a recorded failure and 0 for a right-censored observation (e.g. still operating at last inspection).")
            reliability_frame = st.data_editor(pd.DataFrame({
                "time_to_event":[12.0,18.0,21.0,27.0,32.0,38.0,41.0,48.0,57.0,63.0,71.0,80.0],
                "event_observed":[1,1,1,1,1,1,1,1,1,1,1,1],
            }), num_rows="dynamic", use_container_width=True, key="t041_weibull_editor", hide_index=True)
            c1,c2=st.columns(2)
            with c1:
                time_col=st.selectbox("Time-to-event column",list(reliability_frame.columns),index=0,key="t041_time_col")
            with c2:
                event_col=st.selectbox("Event/censor indicator",list(reliability_frame.columns),index=1 if len(reliability_frame.columns)>1 else 0,key="t041_event_col")
            horizons_text=st.text_input("Reliability horizons (comma-separated, same time unit)","20, 40, 60, 80",key="t041_horizons")
            try:
                horizons=[float(v.strip()) for v in horizons_text.split(",") if v.strip()]
            except ValueError:
                horizons=[]
            signature=_fingerprint(reliability_frame.to_json(orient="split",date_format="iso"),time_col,event_col,horizons_text)
            saved=_run_engine_tool(
                "T041",signature,"Fit Weibull reliability model",
                lambda: fit_weibull_reliability(reliability_frame,time_col=time_col,event_col=event_col,horizons=horizons),
            )
            if saved and saved.get("signature")==signature:
                result=saved["result"]
                metrics=result.get("metrics",{})
                c1,c2,c3=st.columns(3)
                c1.metric("Weibull shape β",f'{metrics.get("weibull_shape",float("nan")):.4g}')
                c2.metric("Weibull scale η",f'{metrics.get("weibull_scale",float("nan")):.4g}')
                c3.metric("B10 life",f'{metrics.get("B10_life",float("nan")):.4g}')
                st.caption(
                    f'Observed failures: {metrics.get("observed_failures",0)} · '
                    f'Right-censored: {metrics.get("right_censored_count",0)} · '
                    f'Hazard: {metrics.get("hazard_interpretation","not available")}'
                )
                curve=result.get("fitted_curve")
                if isinstance(curve,pd.DataFrame) and not curve.empty:
                    st.markdown("**Fitted reliability curve**")
                    st.line_chart(curve.set_index("time")["fitted_reliability"])
                table=result.get("reliability_at_horizons")
                if isinstance(table,pd.DataFrame):
                    st.dataframe(table,use_container_width=True,hide_index=True)

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

        elif selected_id == "T070":
            st.warning("LIMITED VALIDATION MODE — M/M/1 is a single-server steady-state model; do not apply it when rates or distribution assumptions do not fit the process.")
            st.markdown("### Queuing and service-system analyzer")
            st.caption("Arrival and service rates must use the same rate unit. Times are returned in the reciprocal time unit.")
            arrival_rate = st.number_input("Arrival rate (jobs/hour)", min_value=0.001, value=2.0, step=0.25, key="t070_arrival_rate")
            service_rate = st.number_input("Service rate (jobs/hour)", min_value=0.001, value=3.0, step=0.25, key="t070_service_rate")
            signature = _fingerprint(arrival_rate, service_rate)
            saved = _run_engine_tool(
                "T070", signature, "Calculate M/M/1 queue metrics",
                lambda: analyze_mm1_queue(arrival_rate, service_rate),
            )
            if saved and saved["signature"] == signature:
                metrics = saved["result"].get("metrics", {})
                st.bar_chart(pd.DataFrame({
                    "Mean count (jobs)": [metrics.get("mean_number_in_system", 0),
                                          metrics.get("mean_number_in_queue", 0)],
                }, index=["In system", "In queue"]))
                st.bar_chart(pd.DataFrame({
                    "Mean time (hours)": [metrics.get("mean_time_in_system", 0),
                                          metrics.get("mean_queue_wait", 0)],
                }, index=["In system", "Waiting in queue"]))
                st.caption(
                    f"Utilization: {metrics.get('utilization_percent', 0):.2f}% · "
                    f"Mean queue wait: {metrics.get('mean_queue_wait', 0):.3f} h · "
                    f"Mean system time: {metrics.get('mean_time_in_system', 0):.3f} h"
                )

        elif selected_id == "T058":
            st.warning("LIMITED VALIDATION MODE — scores and weights are user-defined; missing criteria remain visible as evidence coverage, not as zero scores.")
            st.markdown("### Supplier Performance and Risk Scorecard")
            supplier_frame = st.data_editor(pd.DataFrame([
                {"supplier":"Supplier A","quality_score":90.0,"delivery_score":80.0,"cost_score":70.0,"responsiveness_score":100.0,"evidence_date":"2026-10-01"},
                {"supplier":"Supplier B","quality_score":70.0,"delivery_score":70.0,"cost_score":None,"responsiveness_score":60.0,"evidence_date":""},
            ]), num_rows="dynamic", use_container_width=True, key="t058_supplier_editor", hide_index=True)
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                quality_weight = st.number_input("Quality weight", min_value=0.0, value=0.40, step=0.05, key="t058_quality_weight")
            with c2:
                delivery_weight = st.number_input("Delivery weight", min_value=0.0, value=0.30, step=0.05, key="t058_delivery_weight")
            with c3:
                cost_weight = st.number_input("Cost weight", min_value=0.0, value=0.20, step=0.05, key="t058_cost_weight")
            with c4:
                response_weight = st.number_input("Responsiveness weight", min_value=0.0, value=0.10, step=0.05, key="t058_response_weight")
            threshold = st.number_input("Minimum acceptable score (0–100)", min_value=0.0, max_value=100.0, value=70.0, step=5.0, key="t058_threshold")
            weights = {"quality_score":quality_weight,"delivery_score":delivery_weight,"cost_score":cost_weight,"responsiveness_score":response_weight}
            signature = _fingerprint(supplier_frame.to_json(orient="split", date_format="iso"), weights, threshold)
            _run_engine_tool("T058", signature, "Score supplier evidence", lambda: score_supplier_performance(supplier_frame, weights=weights, minimum_acceptable_score=threshold))

        elif selected_id == "T072":
            st.warning("SYNTHETIC RISK MODEL — outcomes are simulated, not measured savings. Inputs are sampled independently; correlations are not inferred.")
            st.markdown("### Monte Carlo risk simulator")
            st.caption("Additive model: base outcome + sum(coefficient × sampled input). Use one outcome unit consistently.")
            input_frame = st.data_editor(pd.DataFrame({
                "Input": ["Demand units", "Downtime hours"],
                "Distribution": ["uniform", "triangular"],
                "Low": [800.0, 0.0], "Mode": [900.0, 2.0], "High": [1100.0, 6.0],
                "Mean": [900.0, 2.0], "Std Dev": [50.0, 1.0],
                "Coefficient": [100.0, -1500.0],
            }), num_rows="dynamic", use_container_width=True, key="t072_inputs", hide_index=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                base_outcome = st.number_input("Base outcome", value=100000.0, step=1000.0, key="t072_base")
            with c2:
                iterations = st.number_input("Iterations", min_value=100, max_value=200000, value=5000, step=1000, key="t072_iterations")
            with c3:
                seed = st.number_input("Reproducible random seed", min_value=0, max_value=4294967295, value=42, step=1, key="t072_seed")
            inputs = [{
                "name": row.get("Input"), "distribution": row.get("Distribution"),
                "low": row.get("Low"), "mode": row.get("Mode"), "high": row.get("High"),
                "mean": row.get("Mean"), "sd": row.get("Std Dev"), "coefficient": row.get("Coefficient"),
            } for row in input_frame.to_dict(orient="records")]
            signature = _fingerprint(input_frame.to_json(orient="split"), base_outcome, int(iterations), int(seed))
            saved = _run_engine_tool(
                "T072", signature, "Run seeded Monte Carlo simulation",
                lambda: simulate_monte_carlo_outcome(inputs, base_outcome, int(iterations), int(seed)),
            )
            if saved and saved["signature"] == signature:
                result = saved["result"]
                metrics = result.get("metrics", {})
                st.bar_chart(pd.DataFrame({
                    "Simulation count": [row["count"] for row in result.get("histogram", [])],
                }, index=[f"{row['bin_start']:.1f}–{row['bin_end']:.1f}" for row in result.get("histogram", [])]))
                st.dataframe(pd.DataFrame([{
                    "Mean": metrics.get("mean"), "Std. dev.": metrics.get("standard_deviation"),
                    "P05": metrics.get("p05"), "Median": metrics.get("p50"), "P95": metrics.get("p95"),
                    "P(outcome < 0)": metrics.get("probability_outcome_below_zero"),
                    "Half-mean delta": metrics.get("half_mean_absolute_difference"),
                }]), use_container_width=True, hide_index=True)
                st.dataframe(pd.DataFrame(result.get("sensitivity", [])), use_container_width=True, hide_index=True)

        elif selected_id == "T073":
            st.warning("LIMITED VALIDATION MODE — deterministic capacity arithmetic, not discrete-event simulation. Results remain estimates under entered cycle time, availability and yield.")
            st.markdown("### What-If Scenario Manager")
            scenario_frame = st.data_editor(pd.DataFrame([
                {"scenario_id":"Baseline","available_minutes_per_period":420.0,"cycle_time_minutes_per_unit":4.0,"yield_percent":95.0},
                {"scenario_id":"Shorter cycle","available_minutes_per_period":420.0,"cycle_time_minutes_per_unit":3.5,"yield_percent":95.0},
                {"scenario_id":"Added time","available_minutes_per_period":450.0,"cycle_time_minutes_per_unit":4.0,"yield_percent":95.0},
            ]), num_rows="dynamic", use_container_width=True, key="t073_scenario_editor", hide_index=True)
            scenario_ids = [str(v) for v in scenario_frame["scenario_id"].tolist()] if "scenario_id" in scenario_frame else []
            c1, c2 = st.columns(2)
            with c1:
                baseline_id = st.selectbox("Baseline scenario", scenario_ids, key="t073_baseline") if scenario_ids else ""
            with c2:
                demand = st.number_input("Demand per period (good units)", min_value=0.0, value=100.0, step=10.0, key="t073_demand")
            signature = _fingerprint(scenario_frame.to_json(orient="split", date_format="iso"), baseline_id, demand)
            _run_engine_tool("T073", signature, "Compare capacity scenarios", lambda: compare_capacity_scenarios(scenario_frame, demand_units=demand, baseline_scenario_id=baseline_id))

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

        elif selected_id == "T083":
            st.warning("LIMITED VALIDATION MODE — cost deltas and ROI are calculated from user-entered inputs. Even reviewed evidence is not independently verified here and must not be marketed as proven savings.")
            st.markdown("### Evidence-Based ROI Tracker")
            st.caption("Enter a comparable baseline and post-intervention cost, implementation cost, period, and source references. Outputs are estimates until independently reviewed.")
            c1, c2, c3 = st.columns(3)
            with c1:
                baseline_cost = st.number_input("Baseline cost (currency units)", min_value=0.0, value=10000.0, step=100.0, key="t083_baseline_cost")
            with c2:
                post_cost = st.number_input("Post-intervention cost", min_value=0.0, value=7000.0, step=100.0, key="t083_post_cost")
            with c3:
                implementation_cost = st.number_input("Implementation cost", min_value=0.0, value=1000.0, step=100.0, key="t083_implementation_cost")
            c1, c2 = st.columns(2)
            with c1:
                currency = st.text_input("Currency code", "SAR", max_chars=3, key="t083_currency")
                measurement_start = st.text_input("Measurement start (YYYY-MM-DD)", "2026-01-01", key="t083_measure_start")
                baseline_ref = st.text_input("Baseline evidence reference", "BASELINE-REF", key="t083_baseline_ref")
                cost_ref = st.text_input("Implementation cost evidence reference", "COST-REF", key="t083_cost_ref")
            with c2:
                measurement_end = st.text_input("Measurement end (YYYY-MM-DD)", "2026-03-31", key="t083_measure_end")
                post_ref = st.text_input("Post-intervention evidence reference", "POST-REF", key="t083_post_ref")
                verifier = st.text_input("Reviewer name (user-entered)", "", key="t083_verifier")
                evidence_reviewed = st.checkbox("I have reviewed the source references for comparability", value=False, key="t083_reviewed")
            signature = _fingerprint(baseline_cost, post_cost, implementation_cost, currency, measurement_start, measurement_end, baseline_ref, post_ref, cost_ref, verifier, evidence_reviewed)
            saved = _run_engine_tool(
                "T083", signature, "Calculate conditional ROI and evidence status",
                lambda: calculate_roi_evidence(
                    baseline_cost=baseline_cost, post_intervention_cost=post_cost,
                    implementation_cost=implementation_cost, currency=currency,
                    measurement_start=measurement_start, measurement_end=measurement_end,
                    baseline_evidence_reference=baseline_ref, post_evidence_reference=post_ref,
                    implementation_cost_reference=cost_ref, verifier_name=verifier,
                    evidence_reviewed=evidence_reviewed,
                ),
            )
            if saved and saved.get("signature") == signature:
                st.json(saved["result"].get("evidence_ledger", {}))
                st.info("The result's verified_savings field always remains false until a separate independent review process exists.")

        elif selected_id == "T084":
            st.warning("LIMITED VALIDATION MODE — multi-criteria scores and weights are judgment-based. Ranking is not ROI or a budget-constrained portfolio optimum.")
            st.markdown("### Engineering Project Portfolio Scorer")
            portfolio_frame = st.data_editor(pd.DataFrame([
                {"project_id":"PR-01","project_name":"Line improvement","estimated_cost":1000.0,"impact_score":90.0,"strategic_fit_score":80.0,"feasibility_score":70.0,"confidence_score":60.0},
                {"project_id":"PR-02","project_name":"Tooling upgrade","estimated_cost":500.0,"impact_score":80.0,"strategic_fit_score":90.0,"feasibility_score":90.0,"confidence_score":80.0},
            ]), num_rows="dynamic", use_container_width=True, key="t084_portfolio_editor", hide_index=True)
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                w_impact = st.number_input("Impact weight", min_value=0.0, value=0.35, step=0.05, key="t084_w_impact")
            with c2:
                w_strategy = st.number_input("Strategic-fit weight", min_value=0.0, value=0.30, step=0.05, key="t084_w_strategy")
            with c3:
                w_feasible = st.number_input("Feasibility weight", min_value=0.0, value=0.20, step=0.05, key="t084_w_feasible")
            with c4:
                w_confidence = st.number_input("Confidence weight", min_value=0.0, value=0.15, step=0.05, key="t084_w_confidence")
            currency = st.text_input("Cost currency code", "SAR", max_chars=3, key="t084_currency")
            weights = {"impact_score":w_impact,"strategic_fit_score":w_strategy,"feasibility_score":w_feasible,"confidence_score":w_confidence}
            signature = _fingerprint(portfolio_frame.to_json(orient="split", date_format="iso"), weights, currency)
            _run_engine_tool("T084", signature, "Score project portfolio", lambda: score_project_portfolio(portfolio_frame, weights=weights, currency=currency))

        elif selected_id == "T086":
            st.warning("RESEARCH PACK · LIMITED VALIDATION MODE — this registers user-entered evidence links and review states; it does not fetch or independently authenticate cited sources.")
            st.markdown("### Hypothesis and Evidence Register")
            evidence_frame = st.data_editor(pd.DataFrame([
                {"evidence_id":"E-001","claim_or_hypothesis":"Cycle time may improve after setup standardization","source_reference":"SYNTHETIC-DEMO-REF","method_or_run":"T036 / example run","review_state":"UNREVIEWED","reviewer":"","review_date":"","limitations":"Illustrative example; not plant evidence"},
            ]), num_rows="dynamic", use_container_width=True, key="t086_evidence_editor", hide_index=True)
            signature = _fingerprint(evidence_frame.to_json(orient="split", date_format="iso"))
            _run_engine_tool("T086", signature, "Validate and save evidence register", lambda: build_hypothesis_evidence_register(evidence_frame))

        elif selected_id == "T085":
            st.warning("RESEARCH PACK · LIMITED VALIDATION MODE — this is a t-test planning calculation, not a guarantee of significance or a substitute for a reviewed study design.")
            st.markdown("### Statistical power and sample-size planner")
            st.caption("The calculation assumes the selected t-test design and a user-supplied standardized effect size. Clustering, attrition, multiple-comparison adjustments and complex longitudinal designs are not included.")
            effect = st.number_input("Standardized effect size (Cohen's d; positive)", min_value=0.01, max_value=10.0, value=0.5, step=0.05, key="t085_effect")
            design = st.selectbox("Supported study design", ["one_sample", "paired", "two_independent_equal_n"], key="t085_design")
            alternative = st.selectbox("Alternative hypothesis", ["two-sided", "greater", "less"], key="t085_alternative")
            alpha = st.selectbox("Significance alpha", [0.01, 0.05, 0.10], index=1, key="t085_alpha")
            power = st.slider("Target statistical power", min_value=0.5, max_value=0.99, value=0.8, step=0.01, key="t085_power")
            max_n = st.number_input("Maximum sample size searched", min_value=10, max_value=10000, value=500, step=10, key="t085_max_n")
            signature = _fingerprint(effect, design, alternative, alpha, power, max_n)
            _run_engine_tool(
                "T085", signature, "Estimate statistical power and sample size",
                lambda: plan_t_test_power(
                    effect_size_d=float(effect), alpha=float(alpha), target_power=float(power),
                    design=design, alternative=alternative, maximum_sample_size=int(max_n),
                ),
            )

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

        elif selected_id == "T024":
            st.warning("LIMITED VALIDATION MODE — this is a deterministic precedence-constrained heuristic, not a proof of a globally minimum station count.")
            st.markdown("### Production line balancer")
            st.caption("Task durations and cycle time must use the same time unit. Predecessors are comma-separated task IDs and must appear earlier in the station sequence.")
            task_defaults = pd.DataFrame({
                "Task": ["A", "B", "C", "D", "E"],
                "Duration": [3.0, 2.0, 4.0, 2.0, 1.0],
                "Predecessors": ["", "A", "A", "B,C", "D"],
            })
            task_frame = st.data_editor(task_defaults, num_rows="dynamic", use_container_width=True,
                                        key="t024_tasks", hide_index=True)
            cycle = st.number_input("Target cycle time (same unit as task durations)", min_value=0.01, value=6.0, step=0.5, key="t024_cycle")
            station_limit = st.number_input("Optional station limit (0 = no limit)", min_value=0, max_value=100, value=0, step=1, key="t024_station_limit")
            task_records = []
            for row in task_frame.to_dict(orient="records"):
                task_name = "" if pd.isna(row.get("Task")) else str(row.get("Task")).strip()
                duration = row.get("Duration")
                predecessors = "" if pd.isna(row.get("Predecessors")) else str(row.get("Predecessors"))
                if not task_name and (duration is None or pd.isna(duration)) and not predecessors.strip():
                    continue
                task_records.append({
                    "name": task_name, "duration": duration,
                    "predecessors": [part.strip() for part in predecessors.split(",") if part.strip()],
                })
            signature = _fingerprint(task_records, cycle, int(station_limit))
            saved = _run_engine_tool(
                "T024", signature, "Balance production line",
                lambda: balance_production_line(task_records, cycle, max_stations=int(station_limit) if station_limit else None),
            )
            if saved and saved["signature"] == signature:
                metrics = saved["result"].get("metrics", {})
                stations = saved["result"].get("station_summary", [])
                if stations:
                    st.bar_chart(pd.DataFrame({"Load": [row["load"] for row in stations],
                                               "Idle time": [row["idle_time"] for row in stations]},
                                              index=[f"Station {row['station']}" for row in stations]))
                    st.dataframe(pd.DataFrame(stations), use_container_width=True, hide_index=True)
                st.caption(
                    f"Line efficiency: {metrics.get('line_efficiency_percent', 0):.2f}% · "
                    f"Balance delay: {metrics.get('balance_delay_percent', 0):.2f}% · "
                    f"theoretical minimum stations: {metrics.get('theoretical_minimum_stations', '—')}"
                )

        elif selected_id == "T025":
            st.warning("LIMITED VALIDATION MODE — cycle-time data indicates a potential constraint; observed output identifies a low-throughput signal, not proven causality.")
            st.markdown("### Bottleneck and constraint screening")
            basis = st.selectbox(
                "Evidence basis", ["cycle_time", "measured_throughput"],
                format_func=lambda value: "Cycle time (inferred)" if value == "cycle_time" else "Measured throughput (observed signal)",
                key="t025_basis",
            )
            if basis == "cycle_time":
                st.caption("Enter positive cycle times in the same time-per-unit unit across stages.")
                stage_frame = st.data_editor(pd.DataFrame({
                    "Stage": ["Cutting", "Welding", "Inspection"],
                    "Cycle time (minutes/unit)": [2.0, 4.0, 1.5],
                }), num_rows="dynamic", use_container_width=True, key="t025_cycle_stages", hide_index=True)
                stage_records = [{"name": row.get("Stage"), "cycle_time": row.get("Cycle time (minutes/unit)")}
                                 for row in stage_frame.to_dict(orient="records")]
            else:
                st.caption("Enter measured rates from the same observation window and in the same units.")
                stage_frame = st.data_editor(pd.DataFrame({
                    "Stage": ["Cutting", "Welding", "Inspection"],
                    "Measured throughput (units/hour)": [28.0, 22.0, 25.0],
                }), num_rows="dynamic", use_container_width=True, key="t025_throughput_stages", hide_index=True)
                stage_records = [{"name": row.get("Stage"), "measured_throughput": row.get("Measured throughput (units/hour)")}
                                 for row in stage_frame.to_dict(orient="records")]
            signature = _fingerprint(stage_records, basis)
            saved = _run_engine_tool(
                "T025", signature, "Screen candidate constraint",
                lambda: analyze_bottleneck(stage_records, basis=basis),
            )
            if saved and saved["signature"] == signature:
                result = saved["result"]
                st.caption(result["metrics"]["evidence_label"].replace("_", " "))
                st.dataframe(pd.DataFrame(result.get("stage_summary", [])), use_container_width=True, hide_index=True)
                st.bar_chart(pd.DataFrame(
                    {"Metric value": [row["metric_value"] for row in result.get("stage_summary", [])]},
                    index=[row["stage"] for row in result.get("stage_summary", [])],
                ))
                for warning in result.get("warnings", []):
                    st.info(warning)

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

        elif selected_id == "T027":
            st.warning("LIMITED VALIDATION MODE — this is an editable timing/WIP summary, not a complete material and information flow map.")
            st.markdown("### Value stream timing summary")
            st.caption("Cycle and wait times use the same time unit. Waiting is entered explicitly and is not inferred from WIP or demand.")
            vsm_frame = st.data_editor(pd.DataFrame({
                "Process": ["Cutting", "Welding", "Inspection"],
                "Cycle time (minutes)": [2.0, 5.0, 1.0],
                "Waiting time (minutes)": [10.0, 30.0, 5.0],
                "WIP (units)": [4.0, 12.0, 3.0],
            }), num_rows="dynamic", use_container_width=True, key="t027_vsm_processes", hide_index=True)
            processes = [{
                "name": row.get("Process"),
                "cycle_time": row.get("Cycle time (minutes)"),
                "wait_time": row.get("Waiting time (minutes)"),
                "wip": row.get("WIP (units)"),
            } for row in vsm_frame.to_dict(orient="records")]
            signature = _fingerprint(vsm_frame.to_json(orient="split", date_format="iso"))
            saved = _run_engine_tool(
                "T027", signature, "Calculate value-stream timing",
                lambda: build_value_stream_metrics(processes),
            )
            if saved and saved["signature"] == signature:
                metrics = saved["result"].get("metrics", {})
                st.bar_chart(pd.DataFrame({
                    "Time": [metrics.get("value_added_time", 0), metrics.get("waiting_time", 0)],
                }, index=["Value-added time", "Waiting time"]))
                st.dataframe(pd.DataFrame(saved["result"].get("process_summary", [])),
                             use_container_width=True, hide_index=True)
                st.caption(
                    f"Explicit lead time: {metrics.get('explicit_lead_time', 0):.2f} · "
                    f"Process cycle efficiency: {metrics.get('process_cycle_efficiency_percent', 0):.2f}% · "
                    f"Total WIP: {metrics.get('total_wip', 0):.2f}"
                )

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

        elif selected_id == "T043":
            st.warning("LIMITED VALIDATION MODE — due dates use calendar-day intervals. No labor, skill, runtime-hour or downtime-window optimization is performed.")
            st.markdown("### Preventive Maintenance Planner")
            st.caption("Enter the last completed date and interval; the next due date is calculated deterministically.")
            maintenance_frame = st.data_editor(pd.DataFrame([
                {"task_id":"PM-001","asset_id":"PUMP-01","task":"Inspect seal and coupling","interval_days":30,"last_completed_date":"2026-09-01","estimated_duration_hours":2.0,"required_skill":"Mechanical","downtime_window":"Night shift"},
                {"task_id":"PM-002","asset_id":"COMP-02","task":"Check vibration","interval_days":30,"last_completed_date":"2026-10-10","estimated_duration_hours":1.5,"required_skill":"Reliability","downtime_window":"Weekend"},
                {"task_id":"PM-003","asset_id":"CONV-01","task":"Inspect belt","interval_days":90,"last_completed_date":"2026-10-20","estimated_duration_hours":1.0,"required_skill":"Mechanical","downtime_window":"Planned stop"},
            ]), num_rows="dynamic", use_container_width=True, key="t043_maintenance_editor", hide_index=True)
            as_of = st.text_input("As-of date (YYYY-MM-DD)", "2026-10-24", key="t043_as_of")
            signature = _fingerprint(maintenance_frame.to_json(orient="split", date_format="iso"), as_of)
            _run_engine_tool("T043", signature, "Calculate maintenance due dates", lambda: plan_preventive_maintenance(maintenance_frame, as_of))

        elif selected_id == "T045":
            st.warning("LIMITED VALIDATION MODE — reorder points use a normal approximation to lead-time demand; intermittent spares and supplier constraints are not modeled.")
            st.markdown("### Spare Parts and Criticality Planner")
            spares_frame = st.data_editor(pd.DataFrame([
                {"part_id":"SP-001","asset_id":"PUMP-01","annual_demand":1000,"daily_demand_stddev":2.0,"lead_time_days":5,"unit_cost":20.0,"current_stock":10,"on_order":5,"criticality_score":5},
                {"part_id":"SP-002","asset_id":"COMP-02","annual_demand":120,"daily_demand_stddev":0.5,"lead_time_days":20,"unit_cost":180.0,"current_stock":1,"on_order":0,"criticality_score":4},
            ]), num_rows="dynamic", use_container_width=True, key="t045_spares_editor", hide_index=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                operating_days = st.number_input("Operating days per year", min_value=1.0, value=250.0, step=5.0, key="t045_operating_days")
            with c2:
                service_z = st.number_input("Safety-stock service factor z", min_value=0.0, value=1.645, step=0.05, key="t045_service_z")
            signature = _fingerprint(spares_frame.to_json(orient="split", date_format="iso"), operating_days, service_z)
            _run_engine_tool("T045", signature, "Calculate spare-parts reorder points", lambda: plan_spare_part_criticality(spares_frame, operating_days_per_year=operating_days, service_factor_z=service_z))

        elif selected_id == "T047":
            st.warning("LIMITED VALIDATION MODE — initial/residual ratings are human-entered screening scores. This is not a certified safety assessment or approval to accept residual risk.")
            st.markdown("### Job Safety and Hazard Register")
            hazard_frame = st.data_editor(pd.DataFrame([
                {"hazard_id":"H-001","hazard":"Hot surface","potential_harm":"Burn","likelihood_1_to_5":4,"severity_1_to_5":4,"residual_likelihood_1_to_5":2,"residual_severity_1_to_5":4,"current_controls":"Guard and training","additional_controls":"Inspect guard","owner":"Safety lead","due_date":"2026-11-01","status":"Open"},
                {"hazard_id":"H-002","hazard":"Pinch point","potential_harm":"Hand injury","likelihood_1_to_5":2,"severity_1_to_5":5,"residual_likelihood_1_to_5":3,"residual_severity_1_to_5":4,"current_controls":"Interlock","additional_controls":"Test interlock monthly","owner":"Maintenance","due_date":"2026-10-30","status":"In Progress"},
            ]), num_rows="dynamic", use_container_width=True, key="t047_hazard_editor", hide_index=True)
            signature = _fingerprint(hazard_frame.to_json(orient="split", date_format="iso"))
            _run_engine_tool("T047", signature, "Score and save hazard register", lambda: build_hazard_register(hazard_frame))

        elif selected_id == "T049":
            st.warning("LIMITED VALIDATION MODE — MILP assigns whole work orders to the supplied skill/window slots. Review all high-criticality unscheduled work; this is not a certified maintenance schedule.")
            st.markdown("### Maintenance Backlog Optimizer")
            st.caption("Select work under per-slot labor-hour capacity, required skill and downtime window. Priority score is criticality × 1000 plus a capped due-date urgency component; this prioritization rule is explicit and editable in source, not an industry standard.")
            work_orders = st.data_editor(pd.DataFrame([
                {"work_order_id":"WO-A","asset_id":"PUMP-01","description":"Critical seal repair","estimated_hours":3.0,"criticality_1_to_5":5,"required_skill":"Mechanical","required_window":"Day","due_date":"2026-10-25"},
                {"work_order_id":"WO-B","asset_id":"CONV-01","description":"Conveyor inspection","estimated_hours":2.0,"criticality_1_to_5":4,"required_skill":"Mechanical","required_window":"Day","due_date":"2026-11-05"},
                {"work_order_id":"WO-C","asset_id":"PUMP-02","description":"Lubrication and checks","estimated_hours":2.0,"criticality_1_to_5":3,"required_skill":"Mechanical","required_window":"Day","due_date":"2026-10-29"},
                {"work_order_id":"WO-D","asset_id":"PANEL-01","description":"Electrical repair","estimated_hours":2.0,"criticality_1_to_5":5,"required_skill":"Electrical","required_window":"Night","due_date":"2026-10-25"},
            ]), num_rows="dynamic", use_container_width=True, key="t049_work_orders", hide_index=True)
            slots = st.data_editor(pd.DataFrame([
                {"slot_id":"DAY-MECH-4H","skill":"Mechanical","downtime_window":"Day","available_hours":4.0},
                {"slot_id":"NIGHT-ELEC-3H","skill":"Electrical","downtime_window":"Night","available_hours":3.0},
            ]), num_rows="dynamic", use_container_width=True, key="t049_capacity_slots", hide_index=True)
            as_of = st.text_input("Planning as-of date (YYYY-MM-DD)", "2026-10-24", key="t049_as_of")
            signature = _fingerprint(work_orders.to_json(orient="split",date_format="iso"),slots.to_json(orient="split",date_format="iso"),as_of)
            saved = _run_engine_tool(
                "T049", signature, "Optimize maintenance backlog",
                lambda: optimize_maintenance_backlog(work_orders,slots,as_of_date=as_of),
            )
            if saved and saved.get("signature")==signature:
                result=saved["result"]
                st.caption(f'Solver status: {result.get("solver_status",result.get("status"))}')
                plan=result.get("work_plan")
                if isinstance(plan,pd.DataFrame) and not plan.empty:
                    st.dataframe(plan,use_container_width=True,hide_index=True)
                utilization=result.get("slot_utilization")
                if isinstance(utilization,pd.DataFrame) and not utilization.empty:
                    st.markdown("**Slot utilization**")
                    st.dataframe(utilization,use_container_width=True,hide_index=True)
                metrics=result.get("metrics",{})
                if metrics.get("optimal"):
                    c1,c2,c3=st.columns(3)
                    c1.metric("Scheduled orders",metrics.get("scheduled_count",0))
                    c2.metric("Unscheduled orders",metrics.get("unscheduled_count",0))
                    c3.metric("Scheduled labor hours",f'{metrics.get("scheduled_hours",0):.2f}')

        elif selected_id == "T050":
            st.warning("LIMITED VALIDATION MODE — rate trends depend on complete exposure-hour denominators and consistent reporting rules. Trends are not causal findings or a certified safety audit.")
            st.markdown("### Safety Incident Trend Analyzer")
            st.caption("Enter one row per period and incident category. Exposure hours must be repeated consistently across categories within the same period; they are counted once in the denominator.")
            incidents = st.data_editor(pd.DataFrame([
                {"period":"2026-Q1","incident_category":"Slip / trip","incident_count":2,"exposure_hours":10000.0},
                {"period":"2026-Q1","incident_category":"Pinch point","incident_count":1,"exposure_hours":10000.0},
                {"period":"2026-Q2","incident_category":"Slip / trip","incident_count":1,"exposure_hours":12000.0},
                {"period":"2026-Q2","incident_category":"Pinch point","incident_count":0,"exposure_hours":12000.0},
            ]), num_rows="dynamic", use_container_width=True, key="t050_incident_editor", hide_index=True)
            rate_denominator = st.selectbox("Rate denominator (exposure hours)", [1000.0, 10000.0, 200000.0], index=2, key="t050_rate_denominator")
            signature = _fingerprint(incidents.to_json(orient="split", date_format="iso"), rate_denominator)
            saved = _run_engine_tool(
                "T050", signature, "Analyze incident counts and rates",
                lambda: analyze_safety_incident_trends(incidents, rate_denominator_hours=rate_denominator),
            )
            if saved and saved.get("signature") == signature:
                result = saved["result"]
                period_table = result.get("period_summary")
                category_table = result.get("category_summary")
                if isinstance(period_table, pd.DataFrame) and not period_table.empty:
                    st.markdown("**Rate by period**")
                    st.line_chart(period_table.set_index("period")["incidents_per_rate_denominator_hours"])
                    st.dataframe(period_table, use_container_width=True, hide_index=True)
                if isinstance(category_table, pd.DataFrame) and not category_table.empty:
                    st.markdown("**Reported incident categories**")
                    st.bar_chart(category_table.set_index("incident_category")["incident_count"])
                    st.dataframe(category_table, use_container_width=True, hide_index=True)

        elif selected_id == "T051":
            st.warning("LIMITED VALIDATION MODE — compares only a naive last-value baseline and a rolling moving average; no seasonality, exogenous variables or prediction intervals are inferred.")
            st.markdown("### Demand forecasting studio")
            st.caption("Enter chronological, equally spaced demand observations in one consistent unit. The tail holdout is evaluated walk-forward without random shuffling.")
            observations_text = st.text_area("Demand observations (oldest to newest, comma-separated)", "10, 12, 14, 16, 18, 20", height=80, key="t051_observations")
            c1, c2, c3 = st.columns(3)
            with c1:
                horizon = st.number_input("Future periods", min_value=1, max_value=500, value=2, step=1, key="t051_horizon")
            with c2:
                holdout = st.number_input("Chronological holdout periods", min_value=1, max_value=1000, value=2, step=1, key="t051_holdout")
            with c3:
                window = st.number_input("Moving-average window", min_value=2, max_value=1000, value=2, step=1, key="t051_window")
            signature = _fingerprint(observations_text, int(horizon), int(holdout), int(window))
            def _calculate_t051():
                values = [float(token.strip()) for token in observations_text.split(",") if token.strip()]
                return forecast_demand_series(values, int(horizon), holdout_periods=int(holdout), moving_average_window=int(window))
            saved = _run_engine_tool("T051", signature, "Compare demand forecasts", _calculate_t051)
            if saved and saved["signature"] == signature:
                result = saved["result"]
                metrics = result.get("metrics", {})
                st.dataframe(pd.DataFrame([
                    {"Model": "Naive last value", **metrics.get("naive_last_value", {})},
                    {"Model": f"Moving average ({metrics.get('moving_average_window')})", **metrics.get("moving_average", {})},
                ]), use_container_width=True, hide_index=True)
                fc = pd.DataFrame(result.get("forecast", []))
                if not fc.empty:
                    st.line_chart(fc.set_index("period_ahead")[["naive_last_value", "moving_average", "selected_forecast"]])
                    st.dataframe(fc, use_container_width=True, hide_index=True)
                st.caption(f"Selected by holdout MAE: {metrics.get('selected_model_by_holdout_mae', '—')}")

        elif selected_id == "T052":
            st.warning("LIMITED VALIDATION MODE — aggregate S&OP reconciliation follows rows in the order entered. Material lead times, BOMs, detailed labor and finite-capacity constraints are not modeled.")
            st.markdown("### Sales and Operations Planning")
            sop_frame = st.data_editor(pd.DataFrame([
                {"period":"P1","demand_units":100.0,"planned_production_units":90.0,"capacity_units":100.0},
                {"period":"P2","demand_units":80.0,"planned_production_units":100.0,"capacity_units":90.0},
                {"period":"P3","demand_units":100.0,"planned_production_units":90.0,"capacity_units":100.0},
            ]), num_rows="dynamic", use_container_width=True, key="t052_sop_editor", hide_index=True)
            c1, c2 = st.columns(2)
            with c1:
                opening_inventory = st.number_input("Starting inventory (units)", min_value=0.0, value=0.0, step=10.0, key="t052_open_inventory")
            with c2:
                opening_backlog = st.number_input("Starting backlog (units)", min_value=0.0, value=0.0, step=10.0, key="t052_open_backlog")
            signature = _fingerprint(sop_frame.to_json(orient="split", date_format="iso"), opening_inventory, opening_backlog)
            _run_engine_tool("T052", signature, "Reconcile demand, supply and capacity", lambda: reconcile_sop_scenario(sop_frame, starting_inventory_units=opening_inventory, starting_backlog_units=opening_backlog))

        elif selected_id == "T054":
            st.warning("LIMITED VALIDATION MODE — deterministic multilevel lot-for-lot MRP only. Pre-horizon releases are rejected; this is not a finite-capacity schedule.")
            st.markdown("### Material requirements planner")
            st.caption("Periods are integer buckets. BOM quantities are units per parent item. Components are required by the parent's planned-order release period.")
            horizon = st.number_input("Planning horizon (periods)", min_value=1, max_value=520, value=6, step=1, key="t054_horizon")
            bom_frame = st.data_editor(pd.DataFrame({
                "Parent": ["PRODUCT", "PRODUCT", "COMP_A"],
                "Component": ["COMP_A", "COMP_B", "RAW_X"],
                "Quantity per parent": [2.0, 1.0, 3.0],
            }), num_rows="dynamic", use_container_width=True, key="t054_bom", hide_index=True)
            mps_frame = st.data_editor(pd.DataFrame({
                "Item": ["PRODUCT", "PRODUCT"], "Period": [4, 5], "Demand": [10.0, 5.0],
            }), num_rows="dynamic", use_container_width=True, key="t054_mps", hide_index=True)
            c1, c2 = st.columns(2)
            with c1:
                inventory_json = st.text_area("On-hand inventory (JSON item: quantity)", '{"PRODUCT":0,"COMP_A":0,"COMP_B":0,"RAW_X":0}', height=90, key="t054_inventory")
                lead_json = st.text_area("Lead times (JSON item: whole periods)", '{"PRODUCT":1,"COMP_A":1,"COMP_B":1,"RAW_X":1}', height=90, key="t054_leads")
            with c2:
                receipts_json = st.text_area("Scheduled receipts (JSON list)", '[]', height=90, key="t054_receipts")
                st.info("Lot sizing is lot-for-lot. Review inventory, scheduled receipts and lead-time calendars before using planned releases.")
            bom_rows = [{"parent": row.get("Parent"), "component": row.get("Component"), "quantity_per": row.get("Quantity per parent")} for row in bom_frame.to_dict(orient="records")]
            mps_rows = [{"item": row.get("Item"), "period": row.get("Period"), "demand": row.get("Demand")} for row in mps_frame.to_dict(orient="records")]
            signature = _fingerprint(bom_frame.to_json(orient="split"), mps_frame.to_json(orient="split"),
                                     inventory_json, lead_json, receipts_json, int(horizon))
            def _calculate_t054():
                return plan_material_requirements(
                    bom_rows, mps_rows, int(horizon), json.loads(inventory_json),
                    json.loads(lead_json), json.loads(receipts_json),
                )
            saved = _run_engine_tool("T054", signature, "Calculate material requirements", _calculate_t054)
            if saved and saved["signature"] == signature:
                result = saved["result"]
                st.dataframe(pd.DataFrame(result.get("period_plans", [])), use_container_width=True, hide_index=True)
                st.markdown("**Planned order releases**")
                st.dataframe(pd.DataFrame(result.get("planned_releases", [])), use_container_width=True, hide_index=True)

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

        elif selected_id == "T077":
            st.warning("LIMITED VALIDATION MODE — compares measured consumption against a selected measured baseline; projected differences are not verified savings and no live equipment control is performed.")
            st.markdown("### Energy Performance Optimizer — Baseline Analysis")
            energy_frame = st.data_editor(pd.DataFrame([
                {"period":"Baseline","production_units":100.0,"energy_kwh":1000.0},
                {"period":"Comparison 1","production_units":120.0,"energy_kwh":900.0},
                {"period":"Comparison 2","production_units":90.0,"energy_kwh":990.0},
            ]), num_rows="dynamic", use_container_width=True, key="t077_energy_editor", hide_index=True)
            periods = [str(v) for v in energy_frame["period"].tolist()] if "period" in energy_frame else []
            baseline_period = st.selectbox("Measured baseline period", periods, key="t077_baseline_period") if periods else ""
            tariff = st.number_input("Optional energy tariff per kWh (0 = not supplied)", min_value=0.0, value=0.0, step=0.01, key="t077_tariff")
            include_factor = st.checkbox("Calculate emissions using a sourced factor", value=False, key="t077_include_factor")
            c1, c2 = st.columns(2)
            with c1:
                factor = st.number_input("Emission factor (kg CO₂e/kWh)", min_value=0.0, value=0.4, step=0.01, disabled=not include_factor, key="t077_factor")
                factor_source = st.text_input("Factor source/reference", "", disabled=not include_factor, key="t077_factor_source")
            with c2:
                factor_date = st.text_input("Factor date (YYYY-MM-DD)", "", disabled=not include_factor, key="t077_factor_date")
                st.caption("Energy factors and tariff are user supplied, not fetched live.")
            signature = _fingerprint(energy_frame.to_json(orient="split", date_format="iso"), baseline_period, tariff, include_factor, factor, factor_source, factor_date)
            _run_engine_tool(
                "T077", signature, "Compare energy intensity",
                lambda: analyze_energy_intensity(
                    energy_frame, baseline_period,
                    tariff_per_kwh=tariff if tariff > 0 else None,
                    emission_factor_kg_per_kwh=factor if include_factor else None,
                    factor_source=factor_source if include_factor else "",
                    factor_date=factor_date if include_factor else "",
                ),
            )

        elif selected_id == "T079":
            st.warning("LIMITED VALIDATION MODE — normalized resource metrics are not an audited environmental disclosure. Input minus wastewater is only an apparent difference without a complete process boundary.")
            st.markdown("### Water and Waste Efficiency Analyzer")
            resource_frame = st.data_editor(pd.DataFrame([
                {"period":"P1","production_units":100.0,"water_input_m3":50.0,"wastewater_m3":32.0,"waste_generated_kg":20.0,"waste_recycled_kg":5.0},
                {"period":"P2","production_units":120.0,"water_input_m3":54.0,"wastewater_m3":35.0,"waste_generated_kg":24.0,"waste_recycled_kg":12.0},
            ]), num_rows="dynamic", use_container_width=True, key="t079_resource_editor", hide_index=True)
            signature = _fingerprint(resource_frame.to_json(orient="split", date_format="iso"))
            _run_engine_tool("T079", signature, "Analyze water and waste efficiency", lambda: analyze_water_waste_efficiency(resource_frame))

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

        elif selected_id == "T062":
            st.warning("LIMITED VALIDATION MODE — this diagnostic tool solves continuous linear programs only. Mixed-integer scheduling is not included; unsupported IIS/conflict reports are never fabricated.")
            st.markdown("### Constraint and Solver Diagnostics")
            st.caption("Edit objective coefficients and bounds, then define constraints using the same variable names. The result shows actual HiGHS status and recomputed constraint residuals.")
            variables_frame = st.data_editor(pd.DataFrame([
                {"variable":"x","objective_coefficient":3.0,"lower_bound":0.0,"upper_bound":None},
                {"variable":"y","objective_coefficient":2.0,"lower_bound":0.0,"upper_bound":None},
            ]), num_rows="fixed", use_container_width=True, key="t062_variables_editor", hide_index=True, disabled=["variable"])
            variable_names = [str(v) for v in variables_frame["variable"].tolist()]
            constraints_default = pd.DataFrame([
                {"constraint_id":"C1","sense":"<=","rhs":4.0,"x":1.0,"y":1.0},
                {"constraint_id":"C2","sense":"<=","rhs":2.0,"x":1.0,"y":0.0},
                {"constraint_id":"C3","sense":"<=","rhs":3.0,"x":0.0,"y":1.0},
            ])
            if variable_names != ["x","y"]:
                constraints_default = pd.DataFrame(columns=["constraint_id","sense","rhs",*variable_names])
            constraint_frame = st.data_editor(constraints_default, num_rows="dynamic", use_container_width=True, key="t062_constraints_editor", hide_index=True)
            objective_sense = st.selectbox("Objective", ["maximize","minimize"], index=0, key="t062_objective_sense")
            signature = _fingerprint(
                variables_frame.to_json(orient="split",date_format="iso"),
                constraint_frame.to_json(orient="split",date_format="iso"),
                objective_sense,
            )
            saved = _run_engine_tool(
                "T062", signature, "Solve LP and diagnose constraints",
                lambda: solve_and_diagnose_linear_program(variables_frame,constraint_frame,objective_sense=objective_sense),
            )
            if saved and saved.get("signature")==signature:
                result=saved["result"]
                st.caption(f'Solver: {result.get("solver_name","not run")} · code {result.get("solver_status_code","not available")} · {result.get("solver_message","")}')
                if result.get("status")=="OPTIMAL":
                    st.metric("Objective value",f'{result.get("objective_value",float("nan")):.5g}')
                    st.dataframe(result.get("variables",pd.DataFrame()),use_container_width=True,hide_index=True)
                diagnostics=result.get("constraint_diagnostics")
                if isinstance(diagnostics,pd.DataFrame):
                    st.dataframe(diagnostics,use_container_width=True,hide_index=True)
                if result.get("status")=="INFEASIBLE":
                    st.error("The current model is infeasible. Review bounds and constraints; no unsupported conflict set is provided.")
                elif result.get("status")=="UNBOUNDED":
                    st.error("The current objective is unbounded under the supplied bounds/constraints.")
                elif result.get("status")=="LIMIT_REACHED":
                    st.warning("Solver stopped at a limit; no optimal solution is claimed.")

        elif selected_id == "T063":
            st.warning("LIMITED VALIDATION MODE — solves only the supplied square one-to-one cost matrix. Skills, precedence, calendars, setup times and broader schedule constraints are not included.")
            st.markdown("### Assignment and Scheduling Optimizer")
            assignment_frame = st.data_editor(pd.DataFrame({
                "job":["Job A","Job B","Job C"],
                "Machine 1":[4.0,2.0,3.0],
                "Machine 2":[3.0,5.0,2.0],
                "Machine 3":[6.0,4.0,1.0],
            }), num_rows="dynamic", use_container_width=True, key="t063_assignment_matrix", hide_index=True)
            signature = _fingerprint(assignment_frame.to_json(orient="split", date_format="iso"))
            _run_engine_tool("T063", signature, "Solve one-to-one assignment", lambda: solve_assignment_cost_matrix(assignment_frame))

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
                        result_key = "shoir_t066_result"
                        st.session_state[result_key] = {
                            "signature": signature,
                            "source": source,
                            "result": outcome,
                            "executed_at": datetime.now(timezone.utc).isoformat(),
                            "persistence_status": "SAVE_PENDING",
                        }
                        persist_tool_run_record(
                            st.session_state.get("current_user", ""), st.session_state, result_key
                        )
                    except ValueError as exc:
                        st.error(f"Input validation failed: {exc}. Previous successful result was preserved.")
            saved = st.session_state.get("shoir_t066_result")
            if isinstance(saved, dict):
                if saved.get("signature") != signature:
                    st.warning("STALE — the table, capacity or provenance changed. Rerun before using the saved result.")
                persist_label = {
                    "MANAGED_WORKSPACE_SAVED": "saved to managed workspace",
                    "LOCAL_SQLITE_SAVED_MAY_BE_EPHEMERAL": "local development save only — may be ephemeral",
                    "SESSION_ONLY_SAVE_FAILED": "session-only — workspace save failed",
                    "SESSION_ONLY_PERSISTENCE_MODE_UNVERIFIED": "session-only — persistence mode unverified",
                }.get(saved.get("persistence_status"), "persistence status unverified")
                st.caption(f'Result status: {saved["result"]["status"]} · Input provenance: {saved["source"]} · {persist_label}')
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
                        result_key = "shoir_t076_result"
                        st.session_state[result_key] = {
                            "signature": signature,
                            "source": source,
                            "result": outcome,
                            "executed_at": datetime.now(timezone.utc).isoformat(),
                            "persistence_status": "SAVE_PENDING",
                        }
                        persist_tool_run_record(
                            st.session_state.get("current_user", ""), st.session_state, result_key
                        )
                    except ValueError as exc:
                        st.error(f"Event-log validation failed: {exc}. Previous successful result was preserved.")
            saved = st.session_state.get("shoir_t076_result")
            if isinstance(saved, dict):
                if saved.get("signature") != signature:
                    st.warning("STALE — the event log or reference sequence changed. Rerun before relying on this result.")
                persist_label = {
                    "MANAGED_WORKSPACE_SAVED": "saved to managed workspace",
                    "LOCAL_SQLITE_SAVED_MAY_BE_EPHEMERAL": "local development save only — may be ephemeral",
                    "SESSION_ONLY_SAVE_FAILED": "session-only — workspace save failed",
                    "SESSION_ONLY_PERSISTENCE_MODE_UNVERIFIED": "session-only — persistence mode unverified",
                }.get(saved.get("persistence_status"), "persistence status unverified")
                st.caption(f'Result status: {saved["result"]["status"]} · Input provenance: {saved["source"]} · {persist_label}')
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
        elif selected_id == "T013":
            st.warning("LIMITED VALIDATION MODE — profiling is non-destructive. Review findings before changing source data.")
            st.markdown("### Data quality profiler")
            st.caption("The sample table is synthetic. No missing values, duplicates or outliers are removed automatically.")
            input_frame = pd.DataFrame({
                "asset_id": ["A-01", "A-02", "A-03", "A-04", "A-04"],
                "cycle_time_seconds": [31.0, 32.0, 30.0, 88.0, 88.0],
                "inspection_result": ["Pass", "Pass", None, "Review", "Review"],
            })
            edited_frame = st.data_editor(input_frame, num_rows="dynamic", use_container_width=True,
                                          key="t013_data_quality_editor", hide_index=True)
            iqr_multiplier = st.number_input("IQR outlier multiplier", min_value=0.1, value=1.5, step=0.1, key="t013_iqr_multiplier")
            signature = _fingerprint(edited_frame.to_json(orient="split", date_format="iso"), float(iqr_multiplier))
            _run_engine_tool(
                "T013", signature, "Profile data quality",
                lambda: profile_data_quality(edited_frame, iqr_multiplier=float(iqr_multiplier)),
            )

        elif selected_id == "T017":
            st.warning("LIMITED VALIDATION MODE — inspect cardinality and unmatched-key warnings before accepting a merge.")
            st.markdown("### Data join and merge preview")
            st.caption("The example is synthetic. Input tables are copied and the output is a preview; source tables are not overwritten.")
            left_default = pd.DataFrame({
                "order_id": ["O-101", "O-102", "O-103"],
                "planned_units": [120, 80, 45],
            })
            right_default = pd.DataFrame({
                "order_ref": ["O-101", "O-102", "O-104"],
                "actual_units": [118, 80, 22],
            })
            join_col_left, join_col_right = st.columns(2)
            with join_col_left:
                st.markdown("**Left table**")
                left_frame = st.data_editor(left_default, num_rows="dynamic", use_container_width=True,
                                            key="t017_join_left", hide_index=True)
            with join_col_right:
                st.markdown("**Right table**")
                right_frame = st.data_editor(right_default, num_rows="dynamic", use_container_width=True,
                                             key="t017_join_right", hide_index=True)
            if len(left_frame.columns) and len(right_frame.columns):
                k1, k2, k3 = st.columns(3)
                with k1:
                    left_key = st.selectbox("Left join key", list(left_frame.columns), key="t017_left_key")
                with k2:
                    right_key = st.selectbox("Right join key", list(right_frame.columns), key="t017_right_key")
                with k3:
                    how = st.selectbox("Join type", ["left", "inner", "outer", "right"], key="t017_join_type")
                signature = _fingerprint(left_frame.to_json(orient="split", date_format="iso"),
                                          right_frame.to_json(orient="split", date_format="iso"),
                                          left_key, right_key, how)
                _run_engine_tool(
                    "T017", signature, "Preview table join",
                    lambda: preview_data_join(left_frame, right_frame, left_key, right_key, how=how),
                )
            else:
                st.info("Add at least one named column to each input table before defining a join.")

        elif selected_id == "T018":
            st.warning("LIMITED VALIDATION MODE — time-series processing reports gaps and duplicates but does not silently impute or delete them.")
            st.markdown("### Time-series processor")
            st.caption("The sample observations are synthetic and expressed in UTC. Choose the source timezone for naive timestamps.")
            input_frame = pd.DataFrame({
                "timestamp": ["2026-10-01T08:00:00Z", "2026-10-01T09:00:00Z",
                              "2026-10-01T09:00:00Z", "2026-10-01T11:00:00Z"],
                "units_produced": [28, 31, 29, 35],
                "downtime_minutes": [5.0, 0.0, 2.0, 1.0],
            })
            edited_frame = st.data_editor(input_frame, num_rows="dynamic", use_container_width=True,
                                          key="t018_timeseries_editor", hide_index=True)
            value_options = [c for c in edited_frame.columns if c != "timestamp"]
            if not value_options:
                st.info("Add at least one value field beside the timestamp field.")
            else:
                c1, c2, c3 = st.columns(3)
                with c1:
                    source_timezone = st.selectbox("Timezone for naive timestamps", ["UTC", "Asia/Riyadh", "Europe/London", "America/Chicago"], key="t018_timezone")
                with c2:
                    frequency = st.selectbox("Resampling interval", ["15min", "1h", "1D"], index=1, key="t018_frequency")
                with c3:
                    aggregation = st.selectbox("Aggregation", ["mean", "sum", "min", "max", "first", "last"], key="t018_aggregation")
                value_cols = st.multiselect("Numeric value fields", value_options, default=[value_options[0]], key="t018_value_cols")
                signature = _fingerprint(edited_frame.to_json(orient="split", date_format="iso"),
                                         source_timezone, frequency, aggregation, value_cols)
                saved = _run_engine_tool(
                    "T018", signature, "Process time series",
                    lambda: process_time_series(edited_frame, "timestamp", value_cols,
                                                source_timezone=source_timezone,
                                                frequency=frequency, aggregation=aggregation),
                )
                if isinstance(saved, dict) and saved.get("signature") == signature:
                    result = saved.get("result", {})
                    series = result.get("resampled_series")
                    if isinstance(series, pd.DataFrame) and not series.empty and value_cols:
                        st.markdown("**Resampled trend**")
                        st.line_chart(series.set_index("timestamp_utc")[value_cols])

        elif selected_id == "T094":
            st.warning("LIMITED VALIDATION MODE — these are local threshold/freshness checks only. No live connector, alert delivery, cross-run deduplication or notification is implied.")
            st.markdown("### KPI Dashboard and Alert Center")
            kpi_frame = st.data_editor(pd.DataFrame([
                {"metric_name":"Scrap","observed_value":8.0,"threshold":5.0,"direction":"ABOVE","unit":"%","last_updated_date":"2026-10-20","owner":"Quality"},
                {"metric_name":"OEE","observed_value":70.0,"threshold":75.0,"direction":"BELOW","unit":"%","last_updated_date":"2026-10-01","owner":"Production"},
            ]), num_rows="dynamic", use_container_width=True, key="t094_kpi_editor", hide_index=True)
            c1, c2 = st.columns(2)
            with c1:
                as_of = st.text_input("As-of date (YYYY-MM-DD)", "2026-10-24", key="t094_as_of")
            with c2:
                stale_days = st.number_input("Stale after (calendar days)", min_value=0, value=7, step=1, key="t094_stale_days")
            signature = _fingerprint(kpi_frame.to_json(orient="split", date_format="iso"), as_of, stale_days)
            _run_engine_tool("T094", signature, "Evaluate KPI thresholds and freshness", lambda: evaluate_kpi_thresholds(kpi_frame, as_of_date=as_of, stale_after_days=int(stale_days)))

        elif selected_id == "T033":
            st.warning("LIMITED VALIDATION MODE — crossed Gauge R&R assumes a balanced parts × appraisers × replicates design; review the study design and measurement units before using results.")
            st.markdown("### Measurement Systems Analysis — crossed Gauge R&R")
            st.caption("Synthetic starter data are provided for testing. Replace them with approved measurement readings and keep one consistent measurement unit.")
            msa_default = pd.DataFrame([
                {"part_id":"P1","appraiser":"A1","measurement":10.0},
                {"part_id":"P1","appraiser":"A1","measurement":10.1},
                {"part_id":"P1","appraiser":"A1","measurement":9.9},
                {"part_id":"P1","appraiser":"A2","measurement":10.2},
                {"part_id":"P1","appraiser":"A2","measurement":10.1},
                {"part_id":"P1","appraiser":"A2","measurement":10.3},
                {"part_id":"P2","appraiser":"A1","measurement":20.0},
                {"part_id":"P2","appraiser":"A1","measurement":20.1},
                {"part_id":"P2","appraiser":"A1","measurement":19.9},
                {"part_id":"P2","appraiser":"A2","measurement":20.2},
                {"part_id":"P2","appraiser":"A2","measurement":20.1},
                {"part_id":"P2","appraiser":"A2","measurement":20.3},
                {"part_id":"P3","appraiser":"A1","measurement":30.0},
                {"part_id":"P3","appraiser":"A1","measurement":30.1},
                {"part_id":"P3","appraiser":"A1","measurement":29.9},
                {"part_id":"P3","appraiser":"A2","measurement":30.2},
                {"part_id":"P3","appraiser":"A2","measurement":30.1},
                {"part_id":"P3","appraiser":"A2","measurement":30.3},
            ])
            msa_frame = st.data_editor(msa_default, num_rows="dynamic", use_container_width=True, key="t033_measurement_editor", hide_index=True)
            part_col = st.selectbox("Part identifier column", list(msa_frame.columns), index=list(msa_frame.columns).index("part_id") if "part_id" in msa_frame.columns else 0, key="t033_part_col")
            appraiser_col = st.selectbox("Appraiser column", list(msa_frame.columns), index=list(msa_frame.columns).index("appraiser") if "appraiser" in msa_frame.columns else min(1, len(msa_frame.columns)-1), key="t033_appraiser_col")
            numeric_cols = [col for col in msa_frame.columns if pd.api.types.is_numeric_dtype(msa_frame[col])]
            measure_default = numeric_cols[0] if numeric_cols else msa_frame.columns[-1]
            measurement_col = st.selectbox("Measurement column", list(msa_frame.columns), index=list(msa_frame.columns).index(measure_default), key="t033_measurement_col")
            tolerance_text = st.text_input("Specification tolerance width (optional)", "", key="t033_tolerance")
            signature = _fingerprint(msa_frame.to_json(orient="split", date_format="iso"), part_col, appraiser_col, measurement_col, tolerance_text)
            _run_engine_tool(
                "T033", signature, "Analyze Gauge R&R",
                lambda: analyze_crossed_gage_rr(
                    msa_frame, part_col=part_col, appraiser_col=appraiser_col,
                    measurement_col=measurement_col,
                    tolerance_width=float(tolerance_text) if tolerance_text.strip() else None,
                ),
            )

        elif selected_id == "T048":
            st.warning("OFFLINE DATA SCREEN — this method does not connect to live telemetry, diagnose a physical fault or prove causation.")
            st.markdown("### Equipment Anomaly Monitor")
            st.caption("The built-in observations are synthetic. Review flagged values with calibration, maintenance and process context; flags can be false positives.")
            anomaly_default = pd.DataFrame([
                {"timestamp":"2026-10-24T08:00:00Z","series_id":"SYNTHETIC-ASSET-01","value":10.0},
                {"timestamp":"2026-10-24T09:00:00Z","series_id":"SYNTHETIC-ASSET-01","value":10.1},
                {"timestamp":"2026-10-24T10:00:00Z","series_id":"SYNTHETIC-ASSET-01","value":9.9},
                {"timestamp":"2026-10-24T11:00:00Z","series_id":"SYNTHETIC-ASSET-01","value":10.2},
                {"timestamp":"2026-10-24T12:00:00Z","series_id":"SYNTHETIC-ASSET-01","value":9.8},
                {"timestamp":"2026-10-24T13:00:00Z","series_id":"SYNTHETIC-ASSET-01","value":10.05},
                {"timestamp":"2026-10-24T14:00:00Z","series_id":"SYNTHETIC-ASSET-01","value":9.95},
                {"timestamp":"2026-10-24T15:00:00Z","series_id":"SYNTHETIC-ASSET-01","value":40.0},
            ])
            anomaly_frame = st.data_editor(anomaly_default, num_rows="dynamic", use_container_width=True, key="t048_anomaly_editor", hide_index=True)
            anomaly_cols = list(anomaly_frame.columns)
            timestamp_col = st.selectbox("Timestamp column", anomaly_cols, index=anomaly_cols.index("timestamp") if "timestamp" in anomaly_cols else 0, key="t048_timestamp_col")
            series_col = st.selectbox("Series / asset column", anomaly_cols, index=anomaly_cols.index("series_id") if "series_id" in anomaly_cols else min(1, len(anomaly_cols)-1), key="t048_series_col")
            numeric_cols = [col for col in anomaly_cols if pd.api.types.is_numeric_dtype(anomaly_frame[col])]
            value_default = numeric_cols[0] if numeric_cols else anomaly_cols[-1]
            value_col = st.selectbox("Measured value column", anomaly_cols, index=anomaly_cols.index(value_default), key="t048_value_col")
            threshold = st.slider("Modified robust z-score threshold", min_value=2.0, max_value=10.0, value=3.5, step=0.1, key="t048_threshold")
            as_of = st.text_input("As-of timestamp (ISO-8601 with timezone)", "2026-10-25T00:00:00Z", key="t048_as_of")
            signature = _fingerprint(anomaly_frame.to_json(orient="split", date_format="iso"), timestamp_col, series_col, value_col, threshold, as_of)
            _run_engine_tool(
                "T048", signature, "Screen imported time series for anomalies",
                lambda: screen_time_series_anomalies(
                    anomaly_frame, timestamp_col=timestamp_col, series_col=series_col,
                    value_col=value_col, threshold=float(threshold), as_of_datetime=as_of,
                    minimum_points_per_series=5,
                ),
            )

        elif selected_id == "T071":
            st.warning("SIMULATION ONLY — this is a discrete-event serial-flow model, not a live digital twin or a controller. Verify arrival, service and resource assumptions against measured process data.")
            st.markdown("### Discrete-Event Simulation")
            stations_default = pd.DataFrame([
                {"sequence":1,"station_id":"Station A","servers":1,"mean_service_minutes":3.0,"service_time_cv":0.0},
                {"sequence":2,"station_id":"Station B","servers":1,"mean_service_minutes":4.0,"service_time_cv":0.0},
                {"sequence":3,"station_id":"Station C","servers":1,"mean_service_minutes":2.0,"service_time_cv":0.0},
            ])
            stations = st.data_editor(stations_default, num_rows="dynamic", use_container_width=True, key="t071_station_editor", hide_index=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                entity_count = st.number_input("Entities", min_value=10, max_value=5000, value=200, step=10, key="t071_entity_count")
                warmup = st.number_input("Warm-up entities excluded", min_value=0, max_value=4998, value=20, step=1, key="t071_warmup")
            with c2:
                interarrival = st.number_input("Mean interarrival time (minutes)", min_value=0.01, value=5.0, step=0.5, key="t071_interarrival")
                arrival_pattern = st.selectbox("Arrival pattern", ["fixed", "exponential"], key="t071_arrival_pattern")
            with c3:
                replications = st.number_input("Replications", min_value=1, max_value=20, value=5, step=1, key="t071_replications")
                random_seed = st.number_input("Random seed", min_value=0, value=42, step=1, key="t071_seed")
            signature = _fingerprint(stations.to_json(orient="split", date_format="iso"), entity_count, warmup, interarrival, arrival_pattern, replications, random_seed)
            _run_engine_tool(
                "T071", signature, "Run discrete-event simulation",
                lambda: simulate_serial_flow_line(
                    stations, entity_count=int(entity_count), mean_interarrival_minutes=float(interarrival),
                    arrival_pattern=arrival_pattern, warmup_entities=int(warmup),
                    replications=int(replications), random_seed=int(random_seed),
                ),
            )

        elif selected_id == "T087":
            st.warning("RESEARCH PACK · METADATA-ONLY REPRODUCIBILITY PACK — source data are excluded, and checksums do not authenticate the source or independently validate calculations.")
            st.markdown("### Reproducibility Pack Generator")
            st.caption("Only scalar metadata is packaged. Do not enter personal data, credentials, connection strings or raw observations.")
            project_name = st.text_input("Project / study label", "Synthetic study", key="t087_project")
            app_version = st.text_input("Shoir-IE version label", "NOT_RECORDED", key="t087_app_version")
            git_ref = st.text_input("Git commit or study reference", "NOT_RECORDED", key="t087_git_ref")
            fingerprint_default = hashlib.sha256(b"SHOIR-IE SYNTHETIC DEMO DATASET v1").hexdigest()
            dataset_fingerprint = st.text_input("Dataset SHA-256 fingerprint", fingerprint_default, key="t087_fingerprint")
            method_name = st.text_input("Method name", "Illustrative engineering method", key="t087_method")
            method_version = st.text_input("Method version", "User-entered", key="t087_method_version")
            parameters_text = st.text_area("Method parameters (JSON scalar object)", '{"source_state":"SYNTHETIC","seed":42}', key="t087_parameters")
            output_text = st.text_area("Output summary (JSON scalar object)", '{"source_state":"SYNTHETIC","result_state":"ILLUSTRATIVE_ONLY"}', key="t087_outputs")
            seed_text = st.text_input("Random seed (optional integer)", "42", key="t087_seed")
            signature = _fingerprint(project_name, app_version, git_ref, dataset_fingerprint, method_name, method_version, parameters_text, output_text, seed_text)
            def build_t087():
                try:
                    parameters_obj = json.loads(parameters_text)
                    output_obj = json.loads(output_text)
                    if not isinstance(parameters_obj, dict) or not isinstance(output_obj, dict):
                        raise ValueError("Parameters and output summary must each be a JSON object.")
                    seed_value = int(seed_text) if seed_text.strip() else None
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid reproducibility input: {exc}") from exc
                return build_reproducibility_pack(
                    project_name=project_name, app_version=app_version, git_commit=git_ref,
                    dataset_fingerprint=dataset_fingerprint, method_name=method_name,
                    method_version=method_version, parameters=parameters_obj,
                    output_summary=output_obj, random_seed=seed_value,
                )
            saved = _run_engine_tool("T087", signature, "Build reproducibility ZIP", build_t087)
            if saved and saved.get("signature") == signature:
                artifact = saved.get("result", {}).get("archive_base64")
                if artifact:
                    st.download_button(
                        "Download reproducibility ZIP", base64.b64decode(artifact),
                        file_name="shoir_ie_reproducibility_pack.zip", mime="application/zip",
                        key="T087_archive_download",
                    )

        elif selected_id == "T090":
            st.warning("RESEARCH PACK · REPORT DRAFT — the report structures user-supplied methods and results; it does not independently verify calculations or citations.")
            st.markdown("### Research Report and Methods Builder")
            title = st.text_input("Report title", "Synthetic methods report", key="t090_title")
            authors = st.text_input("Authors / team (optional)", "", key="t090_authors")
            purpose = st.text_area("Purpose / research question", "Document the method, assumptions and limitations for a study.", key="t090_purpose")
            method_name = st.text_input("Method name", "Example analysis method", key="t090_method")
            method_version = st.text_input("Method version", "1.0", key="t090_method_version")
            dataset_description = st.text_area("Dataset description", "Synthetic demo data only; not measured plant or customer observations.", key="t090_dataset")
            formula = st.text_area("Formulae / equations", "", key="t090_formula")
            parameters = st.text_area("Parameters / configuration", "Replace these defaults with values from the executed study.", key="t090_parameters")
            results_summary = st.text_area("Results summary", "Illustrative placeholder only. Replace with a result from a validated run.", key="t090_results")
            limitations = st.text_area("Limitations (one per line)", "Synthetic data only\nNot independently reviewed", key="t090_limitations")
            signature = _fingerprint(title, authors, purpose, method_name, method_version, dataset_description, formula, parameters, results_summary, limitations)
            saved = _run_engine_tool(
                "T090", signature, "Generate research methods report",
                lambda: build_research_methods_report(
                    title=title, authors_or_team=authors, purpose=purpose,
                    method_name=method_name, method_version=method_version,
                    dataset_description=dataset_description, formula_or_equations=formula,
                    parameters=parameters, results_summary=results_summary,
                    limitations=[line.strip() for line in limitations.splitlines() if line.strip()],
                ),
            )
            if saved and saved.get("signature") == signature:
                report_result = saved.get("result", {})
                report_text = report_result.get("report_markdown")
                if isinstance(report_text, str) and report_text:
                    st.download_button(
                        "Download research methods Markdown", report_text.encode("utf-8"),
                        file_name=f"{report_result.get('file_name','shoir_ie_research_report')}.md",
                        mime="text/markdown", key="T090_report_download",
                    )

        elif selected_id == "T019":
            st.warning("SYNTHETIC ONLY — this generator creates practice data, not real industrial observations or verified benchmarks.")
            st.markdown("### Synthetic industrial data generator")
            c1, c2 = st.columns(2)
            with c1:
                row_count = st.number_input("Rows to generate", min_value=1, max_value=100000, value=100, step=1, key="t019_row_count")
                seed = st.number_input("Reproducible random seed", min_value=0, value=42, step=1, key="t019_seed")
            with c2:
                defect_rate = st.number_input("Synthetic defect probability", min_value=0.0, max_value=1.0, value=0.03, step=0.01, key="t019_defect_rate")
                downtime_rate = st.number_input("Synthetic probability of downtime per period", min_value=0.0, max_value=1.0, value=0.10, step=0.01, key="t019_downtime_rate")
            signature = _fingerprint(int(row_count), int(seed), float(defect_rate), float(downtime_rate))
            _run_engine_tool(
                "T019", signature, "Generate synthetic dataset",
                lambda: generate_synthetic_industrial_data(int(row_count), int(seed),
                                                           defect_rate=float(defect_rate),
                                                           downtime_rate=float(downtime_rate)),
            )

        else:
            # A catalogued target without a wired, validated method must never render as
            # an empty/blank page or pretend a successful run. Give the user its real state
            # and the next safe action while preserving the existing Workbench navigation.
            st.warning(
                f"{selected_id} is catalogued, but a dedicated runnable method is not wired "
                "to this library entry yet. No calculation was run."
            )
            st.markdown("**Current gap**")
            st.write(item.get("remaining_gap", "No gap details are recorded. Treat the capability as unverified."))
            st.markdown("**Existing route candidate**")
            st.write(item.get("existing_module_or_route", "No route has been mapped."))
            st.info(
                "Use the existing Workbench module only for functionality it actually provides. "
                "This library entry does not imply that the full target capability is implemented "
                "or that an unconfigured integration is connected."
            )

else:
    st.warning("No target capabilities match these filters. Change the workbench, status or search.")
