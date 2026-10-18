"""Streamlit workspace for production bottleneck and capacity recovery.

Presentation-only orchestration stays separate from deterministic formulas and
owner-scoped persistence in shoir_capacity_recovery.py.
"""
from __future__ import annotations

import io

import pandas as pd
import plotly.express as px


def render_capacity_recovery_workspace(tier="Enterprise", username="unknown"):
    import streamlit as st

    from shoir_capacity_recovery import (
        analyze_capacity_recovery,
        calculate_capacity_value_sensitivity,
        list_capacity_outcomes,
        list_capacity_studies,
        load_capacity_study,
        map_imported_station_data,
        record_capacity_outcome,
        save_capacity_study,
        starter_station_table,
    )
    import io

    st.subheader("Production Bottleneck & Capacity Recovery Study")
    st.caption(
        "Build a transparent station-capacity baseline, identify the binding station, "
        "compare an explicitly edited recovery scenario, preserve a reproducible study, "
        "and later compare its forecast with source-referenced actual output."
    )
    st.warning(
        "Starter values are synthetic demonstration data. Capacity is a deterministic screening estimate, "
        "not a calibrated simulation, a guaranteed throughput result, or verified financial savings."
    )

    # Load saved studies before constructing stateful editors so a selected
    # record repopulates the visible controls on the same rerun.
    try:
        saved_capacity_studies = list_capacity_studies(username)
    except Exception as exc:
        saved_capacity_studies = pd.DataFrame()
        st.error(f"Saved capacity studies could not be read safely: {type(exc).__name__}: {exc}")

    if not saved_capacity_studies.empty:
        st.markdown("#### Open an existing study")
        study_options = {
            f"{row.study_id} · {row.study_name} · {row.created_at}": row.study_id
            for row in saved_capacity_studies.itertuples(index=False)
        }
        selected_study_label = st.selectbox(
            "Saved studies in your workspace",
            ["— Start or continue the current study —"] + list(study_options),
            key="os_capacity_load_selection",
        )
        if st.button("Load selected study", key="os_capacity_load_button", use_container_width=True):
            study_id_to_load = study_options.get(selected_study_label)
            if not study_id_to_load:
                st.info("Select a saved study first.")
            else:
                try:
                    loaded = load_capacity_study(study_id_to_load, username)
                    if loaded is None:
                        st.error("That study is not available in your workspace.")
                    else:
                        st.session_state["os_capacity_recovery_table"] = pd.DataFrame(loaded["inputs"]["stations"])
                        st.session_state["os_capacity_demand"] = float(loaded["inputs"]["demand_units_per_shift"])
                        st.session_state["os_capacity_yield"] = float(loaded["inputs"]["overall_first_pass_yield_pct"])
                        st.session_state["os_capacity_shifts_year"] = float(loaded["inputs"]["operating_shifts_per_year"])
                        st.session_state["os_capacity_unit_value"] = float(loaded["inputs"]["contribution_or_avoided_cost_per_unit"])
                        st.session_state["os_capacity_impl_cost"] = float(loaded["inputs"]["implementation_cost"])
                        st.session_state["os_capacity_data_source"] = str(loaded["data_source"])
                        st.session_state["os_capacity_study_name"] = str(loaded["study_name"])
                        st.session_state["os_capacity_decision"] = str(loaded["decision"])
                        st.session_state["os_capacity_rationale"] = str(loaded["rationale"])
                        st.session_state["os_capacity_loaded_study"] = loaded
                        st.session_state.pop("os_capacity_station_editor", None)
                        st.success(f"Loaded {loaded['study_id']}. Inputs and calculation version were restored.")
                except Exception as exc:
                    st.error(f"Study could not be loaded safely: {type(exc).__name__}: {exc}")
    else:
        st.caption("No saved capacity-recovery studies are available for this account yet.")

    st.markdown("#### Import existing production data (optional)")
    with st.expander("Map a CSV or Excel table to engineering fields", expanded=False):
        upload = st.file_uploader(
            "Station data (.csv or .xlsx; first worksheet used)",
            type=["csv", "xlsx"],
            key="os_capacity_upload",
            help="Imports are limited to 10 MiB and 1,000 station rows. The upload is optional and is never required to start Shoir-IE.",
        )
        imported_frame = None
        if upload is not None:
            payload = upload.getvalue()
            if len(payload) > 10 * 1024 * 1024:
                st.error("This upload exceeds the 10 MiB limit. Reduce the file size and try again.")
            else:
                try:
                    if upload.name.casefold().endswith(".csv"):
                        imported_frame = pd.read_csv(io.BytesIO(payload), nrows=1001)
                    else:
                        imported_frame = pd.read_excel(io.BytesIO(payload), sheet_name=0, nrows=1001)
                    if imported_frame.empty:
                        st.error("The first worksheet contains no data rows.")
                        imported_frame = None
                    elif len(imported_frame) > 1000:
                        st.error("The imported table exceeds the 1,000-row limit.")
                        imported_frame = None
                    else:
                        imported_frame.columns = [str(column).strip() for column in imported_frame.columns]
                        if any(not column for column in imported_frame.columns):
                            st.error("Every imported column needs a non-empty header.")
                            imported_frame = None
                        elif pd.Index(imported_frame.columns).duplicated().any():
                            st.error("Column names are duplicated after normalization. Rename them before mapping.")
                            imported_frame = None
                        else:
                            st.dataframe(imported_frame.head(20), use_container_width=True, hide_index=True)
                except Exception as exc:
                    imported_frame = None
                    st.error(f"Import failed safely: {type(exc).__name__}: {exc}")

        if imported_frame is not None:
            source_options = ["— choose a column —"] + list(imported_frame.columns)
            mapping = {}
            targets = [
                ("Station", "Station / workstation name"),
                ("Cycle Time (sec/unit)", "Cycle time (seconds per unit)"),
                ("Available Time (min/shift)", "Available production time (minutes per shift)"),
                ("Availability (%)", "Availability (0–100%)"),
                ("Parallel Resources", "Parallel resources (whole number)"),
            ]
            for field, label in targets:
                default_index = source_options.index(field) if field in source_options else 0
                mapping[field] = st.selectbox(
                    label,
                    source_options,
                    index=default_index,
                    key="os_capacity_map_" + field.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", ""),
                )
            if st.button("Apply validated column mapping", key="os_capacity_apply_mapping", type="primary"):
                if any(value == "— choose a column —" for value in mapping.values()):
                    st.error("Map every required engineering field before importing.")
                else:
                    try:
                        mapped = map_imported_station_data(imported_frame, mapping)
                        st.session_state["os_capacity_recovery_table"] = mapped
                        st.session_state["os_capacity_data_source"] = "Imported file: " + upload.name
                        st.session_state.pop("os_capacity_station_editor", None)
                        st.session_state.pop("os_capacity_loaded_study", None)
                        st.success("Mapped data passed structural, numeric, unit-range, and row-limit validation. Scenario values start equal to baseline.")
                    except Exception as exc:
                        st.error(f"Mapped data was rejected: {type(exc).__name__}: {exc}")

    st.markdown("#### 1 · Baseline and recovery scenario")
    st.caption(
        "Cycle times use seconds/unit; available time uses minutes/shift; availability is a percent from 0 to 100; "
        "parallel resources must be whole numbers. The scenario starts at the baseline unless you change it."
    )
    st.session_state.setdefault("os_capacity_recovery_table", starter_station_table())
    stations = st.data_editor(
        st.session_state["os_capacity_recovery_table"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="os_capacity_station_editor",
    )
    st.session_state["os_capacity_recovery_table"] = stations.copy()

    demand_col, yield_col = st.columns(2)
    with demand_col:
        demand_units = st.number_input(
            "Demand (good units/shift)", min_value=0.0, step=10.0,
            key="os_capacity_demand",
            help="Set the required good output per shift. Zero is permitted for capacity-only studies.",
        )
    with yield_col:
        yield_pct = st.number_input(
            "Overall first-pass yield (%)", min_value=0.0, max_value=100.0, step=0.5,
            key="os_capacity_yield",
            help="Applied once to the line's lowest calculated station capacity.",
        )
    st.markdown("#### 2 · Source, assumptions, and decision")
    st.session_state.setdefault("os_capacity_data_source", "Synthetic demonstration data — replace with measured plant data")
    st.session_state.setdefault("os_capacity_study_name", "Production Capacity Recovery")
    st.session_state.setdefault("os_capacity_demand", 340.0)
    st.session_state.setdefault("os_capacity_yield", 96.0)
    st.session_state.setdefault("os_capacity_shifts_year", 0.0)
    st.session_state.setdefault("os_capacity_unit_value", 0.0)
    st.session_state.setdefault("os_capacity_impl_cost", 0.0)
    st.session_state.setdefault("os_capacity_decision", "Investigate bottleneck")
    st.session_state.setdefault("os_capacity_rationale", "")
    st.text_input(
        "Data source / reference",
        key="os_capacity_data_source",
        help="Use a workbook/source reference or keep the synthetic-data notice until real inputs are supplied.",
    )
    st.text_input("Study name", key="os_capacity_study_name")
    decision = st.selectbox(
        "Current decision status",
        ["Investigate bottleneck", "Run controlled pilot", "Adopt after operational validation", "Reject scenario", "Other"],
        key="os_capacity_decision",
    )
    rationale = st.text_area(
        "Decision rationale / next test",
        placeholder="Record the evidence, unresolved risks, and the next validation step.",
        key="os_capacity_rationale",
    )

    st.markdown("#### 3 · Capacity result")
    result = None
    comparison_figure = None
    try:
        result = analyze_capacity_recovery(stations, demand_units, yield_pct)
    except Exception as exc:
        st.error(f"Capacity calculation is blocked by invalid inputs: {type(exc).__name__}: {exc}")

    if result is not None:
        baseline = result["baseline"]
        scenario = result["scenario"]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Baseline good capacity", f"{baseline['good_capacity_units_per_shift']:,.1f} units/shift")
        k2.metric("Scenario good capacity", f"{scenario['good_capacity_units_per_shift']:,.1f} units/shift", delta=f"{result['delta']['additional_good_units_per_shift']:+,.1f} units/shift")
        k3.metric("Baseline shortfall", f"{baseline['shortfall_units_per_shift']:,.1f} units/shift")
        k4.metric("Scenario shortfall", f"{scenario['shortfall_units_per_shift']:,.1f} units/shift")
        bottleneck_a, bottleneck_b = st.columns(2)
        bottleneck_a.write("**Baseline binding station(s)**")
        bottleneck_a.write(", ".join(baseline["bottleneck_stations"]) or "Not identified")
        bottleneck_b.write("**Scenario binding station(s)**")
        bottleneck_b.write(", ".join(scenario["bottleneck_stations"]) or "Not identified")

        chart_data = pd.concat([
            stations[["Station"]].assign(Plan="Baseline", **{"Capacity (units/shift)": result["station_results"]["Baseline Capacity (units/shift)"]}),
            stations[["Station"]].assign(Plan="Recovery scenario", **{"Capacity (units/shift)": result["station_results"]["Scenario Capacity (units/shift)"]}),
        ], ignore_index=True)
        comparison_figure = px.bar(
            chart_data, x="Station", y="Capacity (units/shift)", color="Plan", barmode="group",
            title="Baseline vs recovery scenario — station capacity",
        )
        comparison_figure.update_layout(height=380, margin=dict(l=16, r=16, t=56, b=24))
        st.plotly_chart(comparison_figure, use_container_width=True)
        st.dataframe(result["station_results"], use_container_width=True, hide_index=True)

        summary_table = pd.DataFrame([
            {"Metric": "Good capacity (units/shift)", "Baseline": baseline["good_capacity_units_per_shift"], "Recovery scenario": scenario["good_capacity_units_per_shift"]},
            {"Metric": "Shortfall (units/shift)", "Baseline": baseline["shortfall_units_per_shift"], "Recovery scenario": scenario["shortfall_units_per_shift"]},
            {"Metric": "Surplus (units/shift)", "Baseline": baseline["surplus_units_per_shift"], "Recovery scenario": scenario["surplus_units_per_shift"]},
            {"Metric": "Capacity coverage (%)", "Baseline": baseline["capacity_coverage_pct"], "Recovery scenario": scenario["capacity_coverage_pct"]},
            {"Metric": "Binding station(s)", "Baseline": ", ".join(baseline["bottleneck_stations"]), "Recovery scenario": ", ".join(scenario["bottleneck_stations"])},
        ])
        with st.expander("Calculation contract and limitations", expanded=False):
            st.write("**Classification:** " + result["classification"])
            st.write("**Calculation version:** " + result["calculation_version"])
            st.write("**Input SHA-256:** " + result["input_sha256"])
            st.write("**Model assumptions and exclusions:**")
            for assumption in result["assumptions"]:
                st.write("• " + assumption)
            for warning in result["warnings"]:
                st.warning(warning)
            st.caption("A reproducible hash demonstrates that a defined input/result payload can be identified; it does not certify the source data or independently verify the model.")
        st.markdown("#### Optional customer-specific value sensitivity")
        st.caption("Financial values remain estimates until operational outcomes and the agreed cost/value basis are measured. Blank or zero assumptions are not silently replaced with industry averages.")
        e1, e2, e3 = st.columns(3)
        with e1:
            shifts_per_year = st.number_input("Operating shifts/year", min_value=0.0, step=25.0, key="os_capacity_shifts_year")
        with e2:
            unit_value = st.number_input("Contribution / avoided cost per additional good unit (SAR)", min_value=0.0, step=1.0, key="os_capacity_unit_value")
        with e3:
            implementation_cost = st.number_input("Implementation cost (SAR)", min_value=0.0, step=1000.0, key="os_capacity_impl_cost")
        if shifts_per_year > 0 and unit_value > 0:
            sensitivity = calculate_capacity_value_sensitivity(
                result["delta"]["additional_good_units_per_shift"], shifts_per_year, unit_value, implementation_cost
            )
            st.caption(sensitivity["classification"])
            v1, v2, v3 = st.columns(3)
            v1.metric("Modeled incremental units/year", f"{sensitivity['modeled_incremental_units_per_year']:,.0f}")
            v2.metric("Modeled annual gross value", f"SAR {sensitivity['modeled_annual_gross_value']:,.0f}")
            v3.metric("Modeled first-year net value", f"SAR {sensitivity['modeled_first_year_net_value']:,.0f}")
            x1, x2 = st.columns(2)
            x1.metric("ROI sensitivity", f"{sensitivity['roi_percent']:,.1f}%" if sensitivity["roi_percent"] is not None else "N/A")
            x2.metric("Simple payback sensitivity", f"{sensitivity['payback_months']:,.1f} months" if sensitivity["payback_months"] is not None else "N/A")
        else:
            st.info("Enter operating shifts/year and a customer-supported unit value to calculate a scenario-only financial sensitivity.")

        lineage_table = pd.DataFrame([
            {"Field": "Source", "Value": st.session_state.get("os_capacity_data_source", "")},
            {"Field": "Calculation version", "Value": result["calculation_version"]},
            {"Field": "Classification", "Value": result["classification"]},
            {"Field": "Input SHA-256", "Value": result["input_sha256"]},
            {"Field": "Decision", "Value": decision},
            {"Field": "Decision rationale", "Value": rationale},
        ])
        render_exports(
            "Production Bottleneck & Capacity Recovery",
            [("Station Results", result["station_results"]), ("Scenario Summary", summary_table), ("Assumptions & Data Lineage", lineage_table)],
            [("Capacity Comparison", comparison_figure)] if comparison_figure is not None else [],
            tier,
            username,
        )

        if st.button("Save reproducible capacity study", type="primary", use_container_width=True, key="os_capacity_save_study"):
            try:
                saved = save_capacity_study(
                    username,
                    str(st.session_state.get("os_capacity_study_name", "")).strip(),
                    stations,
                    demand_units,
                    yield_pct,
                    data_source=str(st.session_state.get("os_capacity_data_source", "")).strip(),
                    operating_shifts_per_year=float(st.session_state.get("os_capacity_shifts_year", 0.0)),
                    contribution_or_avoided_cost_per_unit=float(st.session_state.get("os_capacity_unit_value", 0.0)),
                    implementation_cost=float(st.session_state.get("os_capacity_impl_cost", 0.0)),
                    decision=decision,
                    rationale=rationale,
                )
                st.session_state["os_capacity_loaded_study"] = saved
                st.success(f"Saved {saved['study_id']} with input and result hashes. Save status does not imply operational verification.")
            except Exception as exc:
                st.error(f"Study could not be saved safely: {type(exc).__name__}: {exc}")

    loaded_study = st.session_state.get("os_capacity_loaded_study")
    if isinstance(loaded_study, dict) and loaded_study.get("study_id"):
        st.markdown("#### 4 · Record actual operational outcome")
        st.caption(
            "This section compares a source-referenced actual good-output figure with the saved scenario capacity estimate. "
            "Entering a source reference records provenance but does not authenticate the source or independently verify the measurement."
        )
        st.write(f"**Saved study:** {loaded_study['study_id']} · {loaded_study['study_name']}")
        with st.form("os_capacity_outcome_form"):
            actual_units = st.number_input("Actual good units/shift", min_value=0.0, value=0.0, step=1.0)
            measurement_period = st.text_input("Measurement period / shifts", placeholder="e.g. 2026-10-12 to 2026-10-18 · day shift")
            source_reference = st.text_input("Source reference", placeholder="e.g. MES export ID, report name, or controlled log")
            tolerance_pct = st.number_input("Acceptable capacity variance (%)", min_value=0.0, max_value=100.0, value=5.0, step=0.5)
            outcome_notes = st.text_area("Outcome notes", placeholder="Product mix, downtime, exclusions, or differences from study assumptions")
            record_outcome = st.form_submit_button("Record and compare actual outcome", type="primary", use_container_width=True)
        if record_outcome:
            try:
                outcome = record_capacity_outcome(
                    loaded_study["study_id"], username, actual_units,
                    measurement_period=measurement_period, source_reference=source_reference,
                    tolerance_pct=tolerance_pct, notes=outcome_notes,
                )
                st.session_state["os_capacity_last_outcome"] = outcome
                st.success("Outcome recorded as a source-referenced measurement submission; it is not labelled independently verified.")
            except Exception as exc:
                st.error(f"Outcome was not recorded: {type(exc).__name__}: {exc}")
        last_outcome = st.session_state.get("os_capacity_last_outcome")
        if isinstance(last_outcome, dict) and last_outcome.get("study_id") == loaded_study["study_id"]:
            st.dataframe(pd.DataFrame([{
                "Expected scenario capacity (units/shift)": last_outcome["expected_good_units_per_shift"],
                "Actual good output (units/shift)": last_outcome["actual_good_units_per_shift"],
                "Variance (units/shift)": last_outcome["variance_units_per_shift"],
                "Variance (%)": last_outcome["variance_pct"],
                "Within selected tolerance": last_outcome["within_tolerance"],
                "Outcome classification": last_outcome["classification"],
            }]), use_container_width=True, hide_index=True)
            st.caption("Tolerance is an arithmetic comparison only. It is not a safety threshold or independent verification.")
        try:
            prior_outcomes = list_capacity_outcomes(loaded_study["study_id"], username)
            if not prior_outcomes.empty:
                st.dataframe(prior_outcomes, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.warning(f"Outcome history is unavailable: {type(exc).__name__}: {exc}")
