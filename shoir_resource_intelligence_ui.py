"""Streamlit surface for Industrial Resource Intelligence.

The UI is deliberately nested inside the existing Shoir-IE Workbench. It uses
explicit manual/imported inputs, per-user workspace persistence and human gates.
It does not claim multi-company shared tenancy or live industrial connectivity.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping
from uuid import uuid4

import pandas as pd

from shoir_resource_intelligence import (
    USER_INPUT_PROVENANCE_VALUES,
    validate_resource_passport,
    append_resource_passport_revision,
    verify_resource_passport_history,
    validate_import_rows,
    detect_resource_loss,
    assess_resource_compatibility,
    optimize_resource_network,
    optimize_period_aligned_resource_network,
    simulate_supplier_disruption,
    evaluate_safety_gate,
    calculate_exchange_value,
    calculate_environmental_impact,
    rank_resource_improvement_projects,
    assess_resource_substitution,
    forecast_resource_quality,
    calculate_supply_reliability,
    propagate_network_impact,
    rank_resource_cascade,
    detect_resource_bottleneck,
    assess_infrastructure_route,
    calculate_resource_intensity_change,
    monitor_resource_intensity_persistence,
    calculate_energy_balance,
    screen_waste_heat_recovery,
    optimize_single_contaminant_water_reuse,
    validate_exchange_agreement,
    assess_exchange_delivery,
)


STATE_PREFIX = "shoir_resource_intelligence_"


def _finite_float(raw: Any, label: str, *, minimum: float | None = None) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return value


def _json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc.msg}.") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _json_array(raw: str, label: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc.msg}.") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a JSON array of objects.")
    return value


def _persist_workspace(st, user: str) -> tuple[bool, str]:
    """Save only to the current user's personal workspace in this first release slice."""
    if isinstance(st.session_state.get("shoir_active_organization_workspace"), dict):
        return False, (
            "Organization-shared persistence is not enabled for this module yet. "
            "No resource data was written to the shared workspace."
        )
    try:
        from durable_account_store import durable_backend_configured
        from workspace_persistence import save_user_workspace
        if not save_user_workspace(user, st.session_state):
            return False, str(st.session_state.get("_workspace_save_error") or "Workspace save was not confirmed.")
        if durable_backend_configured():
            return True, "Saved to the configured managed per-user workspace. Reload after signing in again to verify recovery."
        return True, "Saved to the local workspace fallback. It may not survive a hosted restart."
    except Exception:
        return False, "Workspace save failed. The current data remains only in this session."


def _render_result(st, title: str, value: Any) -> None:
    st.markdown(f"**{title}**")
    st.json(value, expanded=False)


def render_resource_intelligence_workbench(st, *, user: str, tier: str) -> None:
    """Render the integrated module inside the existing Workbench dispatcher."""
    from industrial_platform_excellence import tier_allows

    st.subheader("🏭 Industrial Resource Intelligence")
    st.caption(
        "Industrial Resource Intelligence & Resilience System · Industrial Exchange Intelligence Twin (IEIT)"
    )
    st.info(
        "Engineering workspace foundation. Entered and imported data are not independently verified. "
        "No live supplier availability, plant connectivity, permits, operational controls or customer savings are assumed."
    )

    actor = str(st.session_state.get("current_user") or "").strip()
    if st.session_state.get("authenticated") is not True or actor.casefold() in {"", "guest", "guest visitor", "anonymous"}:
        st.error("Sign in with an active Shoir-IE account before using this module.")
        return
    if actor.casefold() != str(user or "").strip().casefold():
        st.error("The active session identity does not match the Workbench actor. Access is denied.")
        return
    if not tier_allows(tier, "Enterprise"):
        st.warning("Industrial Resource Intelligence requires the Enterprise capability level.")
        return

    facility = st.session_state.get(STATE_PREFIX + "facility", {})
    passports = st.session_state.get(STATE_PREFIX + "passports", [])
    passport_history = st.session_state.get(STATE_PREFIX + "passport_history", [])
    demands = st.session_state.get(STATE_PREFIX + "demands", [])
    routes = st.session_state.get(STATE_PREFIX + "routes", [])
    results = st.session_state.get(STATE_PREFIX + "results", {})
    imports = st.session_state.get(STATE_PREFIX + "import_validation", None)
    agreements = st.session_state.get(STATE_PREFIX + "agreements", [])
    deliveries = st.session_state.get(STATE_PREFIX + "deliveries", [])

    if not isinstance(facility, dict):
        facility = {}
    if not isinstance(passports, list):
        passports = []
    if not isinstance(passport_history, list):
        passport_history = []
    if not isinstance(demands, list):
        demands = []
    if not isinstance(routes, list):
        routes = []
    if not isinstance(results, dict):
        results = {}
    if not isinstance(agreements, list):
        agreements = []
    if not isinstance(deliveries, list):
        deliveries = []

    head1, head2, head3, head4 = st.columns(4)
    head1.metric("Facility", facility.get("name") or "Not configured")
    head2.metric("Resource passports", len(passports))
    head3.metric("Demand records", len(demands))
    head4.metric("Exchange routes", len(routes))
    if st.button("💾 Save workspace data", key="sri_save_workspace", type="primary"):
        ok, message = _persist_workspace(st, actor)
        if ok:
            st.success(message)
        else:
            st.warning(message)

    tabs = st.tabs([
        "Overview & Import", "Resource Passports", "Loss & Recovery",
        "Compatibility", "Network Optimizer", "Resilience",
        "Safety Gate", "Proof of Value", "Quality & Reliability",
        "Resource Memory", "Infrastructure & Bottlenecks", "Exchange Assurance",
        "Environmental Impact", "Investment Prioritization", "Reports",
    ])

    with tabs[0]:
        st.markdown("#### 1 · Facility profile")
        with st.form("sri_facility_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Facility name", value=str(facility.get("name") or ""))
            industry = c2.text_input("Industry", value=str(facility.get("industry") or ""))
            c3, c4 = st.columns(2)
            location = c3.text_input("Location", value=str(facility.get("location") or ""))
            facility_code = c4.text_input("Facility code", value=str(facility.get("facility_id") or ""))
            save_facility = st.form_submit_button("Save facility profile")
        if save_facility:
            if not all(str(x).strip() for x in (name, industry, location, facility_code)):
                st.error("Facility name, industry, location and facility code are all required.")
            else:
                facility = {
                    "facility_id": facility_code.strip(),
                    "name": name.strip(),
                    "industry": industry.strip(),
                    "location": location.strip(),
                    "provenance": "MANUAL",
                }
                st.session_state[STATE_PREFIX + "facility"] = facility
                st.success("Facility profile recorded as MANUAL input.")
        st.markdown("#### 2 · Import resource passport rows")
        st.caption(
            "CSV or Excel must contain facility_id, name, resource_type, available_quantity, unit and provenance. "
            "Optional quality must be a JSON object string. Excel imports read the first worksheet. The source file is not modified."
        )
        upload = st.file_uploader(
            "Upload CSV or Excel resource records",
            type=["csv", "xlsx", "xls"],
            key="sri_resource_csv_upload",
        )
        if upload is not None and st.button("Validate imported rows", key="sri_validate_import"):
            try:
                if not facility:
                    raise ValueError("Create a facility profile before importing resource passports.")
                raw_upload = upload.getvalue()
                from shoir_excel_runtime import MAX_UPLOAD_BYTES, _validate_ooxml_package
                from shoir_upgrade import read_uploaded_workbook
                if not raw_upload:
                    raise ValueError("The uploaded resource file is empty.")
                if len(raw_upload) > MAX_UPLOAD_BYTES:
                    raise ValueError(
                        f"The resource import exceeds the Shoir-IE upload limit of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                    )
                # Reuse Shoir-IE's OOXML path/member/expansion checks before workbook parsing.
                _validate_ooxml_package(raw_upload, upload.name)
                imported_sheets = read_uploaded_workbook(raw_upload, upload.name)
                if not imported_sheets:
                    raise ValueError("No readable worksheets or tables were found.")
                first_sheet_name, frame = next(iter(imported_sheets.items()))
                if not isinstance(frame, pd.DataFrame) or frame.empty:
                    raise ValueError("The first worksheet or table is empty.")
                rows = frame.to_dict("records")
                for row in rows:
                    if str(row.get("facility_id") or "").strip().casefold() != str(facility.get("facility_id") or "").strip().casefold():
                        raise ValueError("Every imported row must belong to the currently selected facility.")
                    quality_value = row.get("quality")
                    if isinstance(quality_value, str) and quality_value.strip():
                        row["quality"] = json.loads(quality_value)
                    elif quality_value is None or (
                        pd.api.types.is_scalar(quality_value) and bool(pd.isna(quality_value))
                    ) or (isinstance(quality_value, str) and not quality_value.strip()):
                        row["quality"] = {}
                imported = validate_import_rows(rows)
                st.session_state[STATE_PREFIX + "import_validation"] = imported
                st.session_state[STATE_PREFIX + "import_source_name"] = upload.name + " · " + str(first_sheet_name)
                imports = imported
            except Exception as exc:
                st.error(f"Import validation failed safely: {exc}")
        if imports:
            _render_result(st, "Import validation result", imports)
            if imports.get("accepted") and st.button("Add valid rows to resource passports", key="sri_add_imported"):
                existing_ids = {str(item.get("resource_id")) for item in passports}
                additions = [item for item in imports["accepted"] if str(item.get("resource_id")) not in existing_ids]
                passports = passports + additions
                for item in additions:
                    passport_history = append_resource_passport_revision(passport_history, item, actor=actor)
                st.session_state[STATE_PREFIX + "passports"] = passports
                st.session_state[STATE_PREFIX + "passport_history"] = passport_history
                st.success(f"Added {len(additions)} validated rows and recorded workspace revisions. Provenance remains as supplied; no source row was rewritten.")

    with tabs[1]:
        st.markdown("#### Resource passport")
        if not facility:
            st.warning("Create the facility profile before adding a resource passport.")
        with st.form("sri_passport_form"):
            c1, c2 = st.columns(2)
            resource_name = c1.text_input("Resource name")
            resource_type = c2.selectbox(
                "Resource type",
                ["Water", "Wastewater", "Steam", "Condensate", "Electricity", "Waste heat",
                 "Fuel", "Industrial gas", "Raw material", "Chemical", "Metal", "Scrap",
                 "By-product", "Residue", "Other"],
            )
            c3, c4 = st.columns(2)
            quantity = c3.text_input("Available quantity (numeric)")
            unit = c4.text_input("Unit (e.g. m3/day, kg/h, kWh)")
            category = st.text_input("Resource category", value="INDUSTRIAL_RESOURCE")
            owner = st.text_input("Resource owner / responsible organization")
            description_en = st.text_area("Resource description (English)", height=55)
            description_ar = st.text_area("وصف المورد (العربية)", height=55)
            source_process = st.text_input("Originating process")
            source_equipment = st.text_input("Originating equipment / asset")
            quality_json = st.text_area("Measured quality properties (JSON object)", value="{}", height=90)
            c5, c6 = st.columns(2)
            provenance = c5.selectbox("Data provenance", list(USER_INPUT_PROVENANCE_VALUES), index=1)
            measured_at = c6.text_input("Measurement timestamp (ISO-8601 with timezone)", value="")
            c7, c8 = st.columns(2)
            temperature = c7.text_input("Temperature °C (optional)", value="")
            pressure = c8.text_input("Pressure kPa (optional)", value="")
            source_reference = st.text_input("Source / meter reference")
            availability_window = st.text_input("Availability schedule / window")
            seasonal_variation = st.text_input("Seasonal or historical variation note")
            storage_requirements = st.text_input("Storage requirements")
            transport_requirements = st.text_input("Transportation / handling requirements")
            laboratory_reference = st.text_input("Laboratory evidence reference")
            certificate_reference = st.text_input("Certificate reference")
            certificate_valid_until = st.text_input("Certificate valid until (YYYY-MM-DD)")
            treatment_notes = st.text_input("Treatment notes")
            safety_restrictions = st.text_area("Safety restrictions", height=70)
            add_passport = st.form_submit_button("Create resource passport")
        if add_passport:
            try:
                if not facility:
                    raise ValueError("Configure a facility first.")
                qobj = _json_object(quality_json, "Quality properties")
                payload = {
                    "facility_id": facility["facility_id"], "name": resource_name,
                    "resource_type": resource_type, "category": category,
                    "available_quantity": quantity, "unit": unit, "quality": qobj,
                    "provenance": provenance, "measured_at": measured_at or None,
                    "temperature_c": temperature or None, "pressure_kpa": pressure or None,
                    "owner": owner, "description_en": description_en, "description_ar": description_ar,
                    "source_process": source_process, "source_equipment": source_equipment,
                    "source_reference": source_reference, "availability_window": availability_window,
                    "seasonal_variation": seasonal_variation, "storage_requirements": storage_requirements,
                    "transport_requirements": transport_requirements,
                    "laboratory_evidence_reference": laboratory_reference,
                    "certificate_reference": certificate_reference,
                    "certificate_valid_until": certificate_valid_until,
                    "treatment_notes": treatment_notes, "safety_restrictions": safety_restrictions,
                }
                passport = validate_resource_passport(payload)
                passports.append(passport)
                passport_history = append_resource_passport_revision(passport_history, passport, actor=actor)
                st.session_state[STATE_PREFIX + "passports"] = passports
                st.session_state[STATE_PREFIX + "passport_history"] = passport_history
                st.success(f"Resource passport created: {passport['resource_id']} · {passport['provenance']}")
            except Exception as exc:
                st.error(f"Passport not created: {exc}")
        if passports:
            st.dataframe(pd.DataFrame([{
                "Resource ID": item.get("resource_id"),
                "Resource": item.get("name"),
                "Type": item.get("resource_type"),
                "Available": item.get("available_quantity"),
                "Unit": item.get("unit"),
                "Provenance": item.get("provenance"),
                "Approval": item.get("approval_status"),
            } for item in passports]), use_container_width=True, hide_index=True)
            selected_resource = st.selectbox(
                "Inspect passport",
                [str(item["resource_id"]) for item in passports],
                key="sri_passport_inspector",
            )
            inspected = next(item for item in passports if str(item["resource_id"]) == selected_resource)
            _render_result(st, "Resource passport detail", inspected)
        else:
            st.caption("No resource passports recorded yet.")

    with tabs[2]:
        st.markdown("#### Resource balance and suspected-loss screening")
        c1, c2 = st.columns(2)
        incoming = c1.text_input("Measured input quantity", key="sri_loss_input")
        accounted = c2.text_input("Accounted output quantity", key="sri_loss_output")
        c3, c4 = st.columns(2)
        balance_unit = c3.text_input("Common unit", key="sri_loss_unit")
        tolerance = c4.text_input("Balance tolerance (%)", value="1.0", key="sri_loss_tolerance")
        loss_provenance = st.selectbox("Measurement provenance", list(USER_INPUT_PROVENANCE_VALUES), index=0, key="sri_loss_provenance")
        if st.button("Calculate resource balance", key="sri_run_loss"):
            try:
                result = detect_resource_loss(
                    incoming, accounted, unit=balance_unit,
                    tolerance_percent=tolerance, evidence_provenance=loss_provenance,
                )
                results["loss_screen"] = result
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Balance calculation failed: {exc}")
        if "loss_screen" in results:
            _render_result(st, "Loss-screen result", results["loss_screen"])

        with st.expander("Energy balance and waste-heat recovery screening"):
            st.markdown("**Same-boundary energy balance**")
            e1, e2 = st.columns(2)
            energy_input = e1.text_input("Energy input (kWh)", key="sri_energy_input")
            useful_output = e2.text_input("Useful energy output (kWh)", key="sri_energy_useful")
            e3, e4 = st.columns(2)
            waste_heat_output = e3.text_input("Waste heat output (kWh)", key="sri_energy_waste_heat")
            other_energy_output = e4.text_input("Other energy output (kWh)", value="0", key="sri_energy_other")
            energy_tolerance = st.text_input("Energy balance tolerance (%)", value="1.0", key="sri_energy_tolerance")
            if st.button("Calculate energy balance", key="sri_run_energy_balance"):
                try:
                    results["energy_balance"] = calculate_energy_balance(
                        energy_input, useful_output, waste_heat_output,
                        other_energy_output, tolerance_percent=energy_tolerance,
                    )
                    st.session_state[STATE_PREFIX + "results"] = results
                except Exception as exc:
                    st.error(f"Energy balance calculation failed: {exc}")
            if "energy_balance" in results:
                _render_result(st, "Energy balance result", results["energy_balance"])

            st.divider()
            st.markdown("**Waste-heat temperature-approach screen**")
            h1, h2 = st.columns(2)
            source_temp = h1.text_input("Heat source temperature (°C)", key="sri_heat_source_temp")
            sink_temp = h2.text_input("Heat sink required temperature (°C)", key="sri_heat_sink_temp")
            h3, h4 = st.columns(2)
            heat_rate = h3.text_input("Available waste-heat rate (kW)", key="sri_heat_rate")
            approach_temp = h4.text_input("Minimum temperature approach (°C)", key="sri_heat_approach")
            h5, h6 = st.columns(2)
            operating_hours = h5.text_input("Annual operating hours (optional)", key="sri_heat_hours")
            energy_value = h6.text_input("Thermal energy value per kWh (optional)", key="sri_heat_value")
            if st.button("Screen waste-heat recovery", key="sri_run_heat_recovery"):
                try:
                    results["heat_recovery_screen"] = screen_waste_heat_recovery(
                        source_temp, sink_temp, heat_rate,
                        minimum_approach_temperature_c=approach_temp,
                        annual_operating_hours=operating_hours if operating_hours.strip() else None,
                        energy_value_per_kwh=energy_value if energy_value.strip() else None,
                    )
                    st.session_state[STATE_PREFIX + "results"] = results
                except Exception as exc:
                    st.error(f"Waste-heat screening failed: {exc}")
            if "heat_recovery_screen" in results:
                _render_result(st, "Waste-heat temperature screen", results["heat_recovery_screen"])
                st.warning("A passed temperature screen is not heat exchanger design or verified heat recovery.")

        with st.expander("Single-contaminant water reuse allocation screen"):
            st.caption(
                "This preliminary LP maximizes reuse over explicitly confirmed connections while respecting one blended-contaminant limit. "
                "It is not a full water-pinch study, treatment design or water-quality approval."
            )
            water_sources = st.text_area(
                "Water sources JSON",
                value='[]',
                key="sri_water_sources",
                height=110,
                help='Each source: source_id, available_flow, flow_unit, concentration, concentration_unit.',
            )
            water_sinks = st.text_area(
                "Water demand sinks JSON",
                value='[]',
                key="sri_water_sinks",
                height=110,
                help='Each sink: sink_id, required_flow, flow_unit, maximum_concentration, concentration_unit.',
            )
            water_connections = st.text_area(
                "Confirmed source-to-sink connections JSON",
                value='[]',
                key="sri_water_connections",
                height=110,
                help='Each connection: source_id, sink_id, connection_confirmed=true, connection_evidence_reference, optional capacity.',
            )
            w1, w2, w3 = st.columns(3)
            contaminant_name = w1.text_input("Contaminant / quality parameter", key="sri_water_contaminant")
            concentration_unit = w2.text_input("Concentration unit", value="mg/L", key="sri_water_concentration_unit")
            water_flow_unit = w3.text_input("Flow unit", value="m3/day", key="sri_water_flow_unit")
            if st.button("Optimize preliminary water reuse", key="sri_run_water_reuse"):
                try:
                    result = optimize_single_contaminant_water_reuse(
                        _json_array(water_sources, "Water sources"),
                        _json_array(water_sinks, "Water demand sinks"),
                        _json_array(water_connections, "Water connections"),
                        contaminant=contaminant_name,
                        concentration_unit=concentration_unit,
                        flow_unit=water_flow_unit,
                    )
                    results["water_reuse_screen"] = result
                    st.session_state[STATE_PREFIX + "results"] = results
                except Exception as exc:
                    st.error(f"Water reuse optimization failed: {exc}")
            if "water_reuse_screen" in results:
                _render_result(st, "Water reuse allocation", results["water_reuse_screen"])
                st.warning("This one-contaminant allocation is not treatment qualification or authorization to reuse water.")

    with tabs[3]:
        st.markdown("#### Engineering compatibility screen")
        if not passports:
            st.info("Add a resource passport to assess compatibility.")
        else:
            supply_id = st.selectbox("Supply resource", [str(x["resource_id"]) for x in passports], key="sri_compat_supply")
            demand_type = st.text_input("Buyer-required resource type", key="sri_compat_type")
            demand_unit = st.text_input("Buyer-required unit (exact match)", key="sri_compat_unit")
            limits_text = st.text_area(
                "Buyer quality limits JSON",
                value='{"pH":{"min":6.5,"max":8.5}}',
                key="sri_compat_limits",
                height=90,
            )
            lab_required = st.checkbox("Further laboratory testing is required", key="sri_compat_lab")
            engineering_review = st.checkbox("Additional engineering review is required", key="sri_compat_review")
            if st.button("Assess compatibility", key="sri_run_compatibility"):
                try:
                    supply = next(x for x in passports if str(x["resource_id"]) == supply_id)
                    demand = {
                        "resource_type": demand_type,
                        "unit": demand_unit,
                        "quality_limits": _json_object(limits_text, "Buyer quality limits"),
                    }
                    result = assess_resource_compatibility(
                        supply, demand,
                        laboratory_test_required=lab_required,
                        engineering_review_required=engineering_review,
                    )
                    results["compatibility"] = result
                    st.session_state[STATE_PREFIX + "results"] = results
                except Exception as exc:
                    st.error(f"Compatibility assessment failed: {exc}")
        if "compatibility" in results:
            _render_result(st, "Compatibility result", results["compatibility"])

        with st.expander("Industrial resource substitution candidate"):
            st.caption("A substitute remains a candidate until product, equipment, laboratory, engineering, safety and environmental qualification is completed.")
            if passports:
                substitute_id = st.selectbox(
                    "Candidate substitute resource",
                    [str(item["resource_id"]) for item in passports],
                    key="sri_substitute_resource",
                )
                substitute_requirement = st.text_area(
                    "Buyer / process substitution requirements JSON",
                    value='{"resource_type":"Water","unit":"m3/day","quality_limits":{"pH":{"min":6.5,"max":8.5}}}',
                    key="sri_substitute_requirement",
                    height=90,
                )
                s1, s2 = st.columns(2)
                product_status = s1.selectbox(
                    "Product quality assessment",
                    ["NOT_ASSESSED", "TEST_REQUIRED", "PASS", "FAIL"],
                    key="sri_sub_product_status",
                )
                equipment_status = s2.selectbox(
                    "Equipment compatibility assessment",
                    ["NOT_ASSESSED", "TEST_REQUIRED", "PASS", "FAIL"],
                    key="sri_sub_equipment_status",
                )
                s3, s4 = st.columns(2)
                lab_ref = s3.text_input("Substitution laboratory evidence reference", key="sri_sub_lab_ref")
                engineering_ref = s4.text_input("Substitution engineering review reference", key="sri_sub_engineering_ref")
                s5, s6 = st.columns(2)
                safety_ref = s5.text_input("Substitution safety review reference", key="sri_sub_safety_ref")
                environmental_ref = s6.text_input("Substitution environmental review reference", key="sri_sub_environmental_ref")
                if st.button("Assess substitution candidate", key="sri_run_substitution"):
                    try:
                        candidate = next(item for item in passports if str(item["resource_id"]) == substitute_id)
                        results["substitution"] = assess_resource_substitution(
                            candidate,
                            _json_object(substitute_requirement, "Substitution requirement"),
                            product_quality_status=product_status,
                            equipment_compatibility_status=equipment_status,
                            laboratory_evidence_reference=lab_ref,
                            engineering_review_reference=engineering_ref,
                            safety_review_reference=safety_ref,
                            environmental_review_reference=environmental_ref,
                        )
                        st.session_state[STATE_PREFIX + "results"] = results
                    except Exception as exc:
                        st.error(f"Substitution assessment failed: {exc}")
                if "substitution" in results:
                    _render_result(st, "Substitution candidate assessment", results["substitution"])
                    st.warning("A candidate assessment never authorizes substituting a material or changing process conditions.")
            else:
                st.info("Create a passport before assessing resource substitution.")

    with tabs[4]:
        st.markdown("#### Controlled exchange candidates and network optimizer")
        st.caption("Routes are explicit user-entered candidates. Every route is rechecked against resource type, unit and buyer quality limits before optimization.")
        if passports and demands:
            with st.form("sri_demand_form"):
                c1, c2 = st.columns(2)
                demand_name = c1.text_input("Demand name")
                new_demand_type = c2.text_input("Required resource type")
                c3, c4 = st.columns(2)
                required_quantity = c3.text_input("Required quantity")
                demand_unit_new = c4.text_input("Required unit")
                demand_limits = st.text_area("Quality limits JSON", value="{}", height=80)
                add_demand = st.form_submit_button("Add demand")
            if add_demand:
                try:
                    demand = {
                        "demand_id": str(uuid4()), "name": demand_name,
                        "resource_type": new_demand_type,
                        "required_quantity": _finite_float(required_quantity, "Required quantity", minimum=0.000000001),
                        "unit": demand_unit_new,
                        "quality_limits": _json_object(demand_limits, "Quality limits"),
                        "provenance": "MANUAL",
                    }
                    if not demand["name"].strip() or demand["required_quantity"] <= 0 or not demand["unit"].strip():
                        raise ValueError("Demand name, positive quantity and unit are required.")
                    demands.append(demand)
                    st.session_state[STATE_PREFIX + "demands"] = demands
                    st.success("Demand record added as MANUAL input.")
                except Exception as exc:
                    st.error(f"Demand not added: {exc}")
        else:
            st.caption("Add at least one resource passport. Demand creation is available after a passport exists.")
            if passports:
                with st.form("sri_demand_form_first"):
                    d1, d2 = st.columns(2)
                    demand_name = d1.text_input("Demand name")
                    new_demand_type = d2.text_input("Required resource type")
                    d3, d4 = st.columns(2)
                    required_quantity = d3.text_input("Required quantity")
                    demand_unit_new = d4.text_input("Required unit")
                    demand_limits = st.text_area("Quality limits JSON", value="{}", height=80)
                    add_demand = st.form_submit_button("Add demand")
                if add_demand:
                    try:
                        demand = {
                            "demand_id": str(uuid4()), "name": demand_name,
                            "resource_type": new_demand_type, "required_quantity": _finite_float(required_quantity, "Required quantity", minimum=0.000000001),
                            "unit": demand_unit_new, "quality_limits": _json_object(demand_limits, "Quality limits"),
                            "provenance": "MANUAL",
                        }
                        if not demand["name"].strip() or demand["required_quantity"] <= 0 or not demand["unit"].strip():
                            raise ValueError("Demand name, positive quantity and unit are required.")
                        demands.append(demand)
                        st.session_state[STATE_PREFIX + "demands"] = demands
                        st.success("Demand record added as MANUAL input.")
                    except Exception as exc:
                        st.error(f"Demand not added: {exc}")
        if demands:
            st.dataframe(pd.DataFrame([{
                "Demand ID": x["demand_id"], "Demand": x["name"], "Type": x["resource_type"],
                "Quantity": x["required_quantity"], "Unit": x["unit"], "Provenance": x["provenance"],
            } for x in demands]), use_container_width=True, hide_index=True)
        if passports and demands:
            with st.form("sri_route_form"):
                r1, r2 = st.columns(2)
                supply_choice = r1.selectbox("Route supply", [str(x["resource_id"]) for x in passports])
                demand_choice = r2.selectbox("Route demand", [str(x["demand_id"]) for x in demands])
                r3, r4, r5 = st.columns(3)
                route_cost = r3.text_input("Resource unit cost (enter 0 only if confirmed)")
                transport_cost = r4.text_input("Transport cost / unit (enter 0 only if confirmed)")
                treatment_cost = r5.text_input("Treatment cost / unit (enter 0 only if confirmed)")
                route_capacity = st.text_input("Confirmed maximum physical route quantity (required)")
                add_route = st.form_submit_button("Add exchange candidate")
            if add_route:
                try:
                    route = {
                        "supply_id": supply_choice, "demand_id": demand_choice,
                        "unit_cost": _finite_float(route_cost, "Resource unit cost", minimum=0),
                        "transport_cost_per_unit": _finite_float(transport_cost, "Transport cost per unit", minimum=0),
                        "treatment_cost_per_unit": _finite_float(treatment_cost, "Treatment cost per unit", minimum=0),
                    }
                    route["capacity"] = _finite_float(route_capacity, "Confirmed maximum route quantity", minimum=0.000000001)
                    routes.append(route)
                    st.session_state[STATE_PREFIX + "routes"] = routes
                    st.success("Exchange candidate recorded. Engineering qualification remains pending.")
                except Exception as exc:
                    st.error(f"Route not added: {exc}")
        if routes:
            st.dataframe(pd.DataFrame(routes), use_container_width=True, hide_index=True)
        if st.button("Run constrained network optimization", key="sri_run_optimizer", type="primary"):
            try:
                result = optimize_resource_network(passports, demands, routes)
                results["optimization"] = result
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Network optimization failed safely: {exc}")
        if "optimization" in results:
            _render_result(st, "Optimization result", results["optimization"])

        with st.expander("Time-bucketed resource allocation (no automatic carryover)"):
            st.caption(
                "Provide supply, demand and candidate routes separately for each period (for example, shift or date). "
                "The optimizer never moves supply between periods and does not infer storage."
            )
            scheduled_supplies = st.text_area(
                "Time-bucketed supplies JSON",
                value="[]",
                key="sri_scheduled_supplies",
                height=100,
                help='Each row: id, period_id, resource_type, available_quantity, unit, quality.',
            )
            scheduled_demands = st.text_area(
                "Time-bucketed demands JSON",
                value="[]",
                key="sri_scheduled_demands",
                height=100,
                help='Each row: id, period_id, resource_type, required_quantity, unit, quality_limits.',
            )
            scheduled_routes = st.text_area(
                "Time-bucketed route constraints JSON",
                value="[]",
                key="sri_scheduled_routes",
                height=100,
                help='Each row: supply_id, demand_id, period_id, unit_cost, transport_cost_per_unit, treatment_cost_per_unit, capacity.',
            )
            allow_scheduled_shortage = st.checkbox(
                "Allow unmet demand and report shortage",
                value=True,
                key="sri_allow_scheduled_shortage",
            )
            scheduled_shortage_penalty = st.text_input(
                "Scenario shortage penalty per unit",
                value="1000000",
                key="sri_scheduled_shortage_penalty",
            )
            if st.button("Optimize by period", key="sri_run_period_optimizer"):
                try:
                    results["period_optimization"] = optimize_period_aligned_resource_network(
                        _json_array(scheduled_supplies, "Time-bucketed supplies"),
                        _json_array(scheduled_demands, "Time-bucketed demands"),
                        _json_array(scheduled_routes, "Time-bucketed routes"),
                        allow_shortage=allow_scheduled_shortage,
                        shortage_penalty_per_unit=_finite_float(
                            scheduled_shortage_penalty, "Scenario shortage penalty", minimum=0
                        ),
                    )
                    st.session_state[STATE_PREFIX + "results"] = results
                except Exception as exc:
                    st.error(f"Time-bucketed optimization failed: {exc}")
            if "period_optimization" in results:
                _render_result(st, "Period-aligned optimization result", results["period_optimization"])
                st.warning("Period alignment does not establish a physical connection, storage availability, production schedule or maintenance approval.")

    with tabs[5]:
        st.markdown("#### Supply disruption and dependency propagation")
        if passports:
            shock_supplier = st.selectbox("Supplier resource affected", [str(x["resource_id"]) for x in passports], key="sri_shock_supplier")
            fraction = st.slider("Supply reduction", min_value=0.0, max_value=1.0, value=0.25, step=0.05, key="sri_shock_fraction")
            if st.button("Simulate supply reduction", key="sri_run_shock"):
                try:
                    result = simulate_supplier_disruption(
                        passports, demands, routes,
                        supplier_id=shock_supplier, supply_reduction_fraction=fraction,
                    )
                    results["disruption"] = result
                    st.session_state[STATE_PREFIX + "results"] = results
                except Exception as exc:
                    st.error(f"Disruption simulation failed: {exc}")
        graph_text = st.text_area(
            "Directed dependency edges JSON",
            value='[{"from":"Supplier A","to":"Treatment Unit"},{"from":"Treatment Unit","to":"Production Line"}]',
            key="sri_dependency_edges",
            height=100,
        )
        source_node = st.text_input("Disrupted node", value="Supplier A", key="sri_dependency_source")
        if st.button("Trace downstream dependencies", key="sri_trace_dependencies"):
            try:
                results["dependency_impact"] = propagate_network_impact(
                    _json_array(graph_text, "Dependency edges"), affected_node=source_node
                )
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Dependency analysis failed: {exc}")
        for key in ("disruption", "dependency_impact"):
            if key in results:
                _render_result(st, key.replace("_", " ").title(), results[key])

    with tabs[6]:
        st.markdown("#### Non-overridable human safety and approval gate")
        st.caption("Critical failures block progression. Recording a reference is not equivalent to independent review or permit approval.")
        critical = st.checkbox("Critical safety failure or prohibited condition exists", key="sri_safety_critical")
        lab_required_gate = st.checkbox("Laboratory test is required", key="sri_safety_lab_required")
        lab_passed_choice = st.selectbox("Laboratory result", ["Not supplied", "Pass", "Fail"], key="sri_safety_lab_result")
        a1, a2 = st.columns(2)
        engineering_ref = a1.text_input("Qualified engineering approval reference", key="sri_eng_ref")
        safety_ref = a2.text_input("Safety approval reference", key="sri_safety_ref")
        environmental_ref = st.text_input("Environmental approval reference", key="sri_environment_ref")
        if st.button("Evaluate safety gate", key="sri_evaluate_safety"):
            result = evaluate_safety_gate(
                critical_failure=critical,
                laboratory_required=lab_required_gate,
                laboratory_passed=True if lab_passed_choice == "Pass" else (False if lab_passed_choice == "Fail" else None),
                engineering_approval_reference=engineering_ref,
                safety_approval_reference=safety_ref,
                environmental_approval_reference=environmental_ref,
            )
            results["safety_gate"] = result
            st.session_state[STATE_PREFIX + "results"] = results
        if "safety_gate" in results:
            _render_result(st, "Safety-gate outcome", results["safety_gate"])
            st.warning("This screen never authorizes a physical transfer, production change or contractual commitment.")

    with tabs[7]:
        st.markdown("#### Financial proof of value")
        st.caption("Enter a consistent reporting period and actual or estimated costs. Blank inputs are not treated as zero.")
        value_fields = [
            ("avoided_disposal_cost", "Supplier avoided disposal cost"),
            ("supplier_sale_revenue", "Supplier resource-sale revenue"),
            ("supplier_preparation_cost", "Supplier preparation cost"),
            ("supplier_testing_cost", "Supplier testing cost"),
            ("supplier_handling_delivery_cost", "Supplier handling and delivery cost"),
            ("avoided_alternative_purchase_cost", "Buyer avoided alternative purchase cost"),
            ("buyer_treatment_cost", "Buyer treatment cost"),
            ("buyer_transport_cost", "Buyer transport cost"),
            ("buyer_testing_cost", "Buyer testing cost"),
            ("buyer_additional_operating_cost", "Buyer additional operating cost"),
        ]
        entered = {}
        for index in range(0, len(value_fields), 2):
            c1, c2 = st.columns(2)
            for col, (key, label) in zip((c1, c2), value_fields[index:index+2]):
                entered[key] = col.text_input(label, key="sri_value_" + key)
        currency = st.text_input("Currency code", value="SAR", key="sri_value_currency")
        evidence_status = st.selectbox("Evidence level", ["FORECAST", "ESTIMATED", "MEASURED"], key="sri_value_status")
        if st.button("Calculate exchange value", key="sri_calculate_value"):
            try:
                if any(str(value).strip() == "" for value in entered.values()):
                    raise ValueError("Complete all financial inputs; blanks are not assumed to be zero.")
                result = calculate_exchange_value(
                    **{key: float(value) for key, value in entered.items()},
                    currency=currency, evidence_status=evidence_status,
                )
                results["proof_of_value"] = result
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Value calculation failed: {exc}")
        if "proof_of_value" in results:
            _render_result(st, "Value calculation", results["proof_of_value"])

        st.divider()
        st.markdown("**Production-normalized resource intensity comparison**")
        st.caption("This is an intensity comparison, not verified savings or causal attribution.")
        v1, v2 = st.columns(2)
        base_usage = v1.text_input("Baseline resource usage", key="sri_intensity_base_usage")
        base_output = v2.text_input("Baseline production output", key="sri_intensity_base_output")
        v3, v4 = st.columns(2)
        current_usage = v3.text_input("Reporting-period resource usage", key="sri_intensity_current_usage")
        current_output = v4.text_input("Reporting-period production output", key="sri_intensity_current_output")
        v5, v6 = st.columns(2)
        intensity_usage_unit = v5.text_input("Usage unit", key="sri_intensity_usage_unit")
        intensity_output_unit = v6.text_input("Production unit", key="sri_intensity_output_unit")
        if st.button("Compare normalized resource intensity", key="sri_compare_intensity"):
            try:
                results["resource_intensity"] = calculate_resource_intensity_change(
                    base_usage, base_output, current_usage, current_output,
                    usage_unit=intensity_usage_unit, production_unit=intensity_output_unit,
                )
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Intensity comparison failed: {exc}")
        if "resource_intensity" in results:
            _render_result(st, "Normalized intensity comparison", results["resource_intensity"])

        st.divider()
        st.markdown("**Resource performance persistence monitor**")
        st.caption("Compare repeated dated resource-use measurements with the declared production-normalized baseline. This flags deviations; it does not determine cause or verify savings.")
        persistence_observations = st.text_area(
            "Dated usage and production observations JSON",
            value="[]",
            key="sri_persistence_observations",
            height=110,
            help='Example: [{"timestamp":"2026-11-01T00:00:00+03:00","usage":900,"production":100},{"timestamp":"2026-11-08T00:00:00+03:00","usage":950,"production":100}]',
        )
        p1, p2 = st.columns(2)
        degradation_threshold = p1.text_input("Degradation alert threshold (%)", value="5.0", key="sri_persistence_threshold")
        required_periods = p2.number_input("Consecutive periods to alert", min_value=1, max_value=24, value=2, step=1, key="sri_persistence_periods")
        if st.button("Monitor resource performance persistence", key="sri_run_persistence_monitor"):
            try:
                results["performance_persistence"] = monitor_resource_intensity_persistence(
                    base_usage,
                    base_output,
                    _json_array(persistence_observations, "Performance observations"),
                    usage_unit=intensity_usage_unit,
                    production_unit=intensity_output_unit,
                    degradation_threshold_percent=degradation_threshold,
                    required_consecutive_periods=int(required_periods),
                )
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Performance persistence monitoring failed: {exc}")
        if "performance_persistence" in results:
            _render_result(st, "Performance persistence result", results["performance_persistence"])

    with tabs[8]:
        st.markdown("#### Quality and supply history")
        quality_history = st.text_area(
            "Quality observations JSON",
            value="[]",
            key="sri_quality_history",
            height=120,
        )
        reliability_history = st.text_area(
            "Delivery history JSON",
            value="[]",
            key="sri_reliability_history",
            height=120,
        )
        if st.button("Run quality and reliability screening", key="sri_quality_reliability"):
            try:
                observations = _json_array(quality_history, "Quality observations")
                delivery_rows = _json_array(reliability_history, "Delivery history")
                results["quality_forecast"] = forecast_resource_quality(observations)
                results["supply_reliability"] = calculate_supply_reliability(delivery_rows)
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"History screening failed: {exc}")
        for key in ("quality_forecast", "supply_reliability"):
            if key in results:
                _render_result(st, key.replace("_", " ").title(), results[key])

    with tabs[9]:
        st.markdown("#### Resource digital memory and cascade sequencing")
        st.caption("This first version records passport revisions in the current saved workspace only; it is not a certified chain-of-custody ledger.")
        if passports:
            _render_result(st, "Current passport snapshot", passports)
        memory_check = verify_resource_passport_history(passport_history)
        st.metric("Recorded passport revisions", len(passport_history))
        st.metric("Workspace revision-chain status", memory_check["status"])
        if passport_history:
            st.dataframe(pd.DataFrame([{
                "Resource ID": item.get("resource_id"),
                "Revision": item.get("revision_no"),
                "Recorded At": item.get("recorded_at"),
                "Recorded By": item.get("recorded_by"),
                "Content SHA-256": item.get("content_sha256"),
                "Revision SHA-256": item.get("revision_sha256"),
            } for item in passport_history]), use_container_width=True, hide_index=True)
            _render_result(st, "Revision-chain verification", memory_check)
        st.caption(
            "Workspace hash checks can reveal accidental or partial edits to stored history. "
            "They are not an immutable ledger, independent timestamp authority or certified chain of custody."
        )
        cascade_json = st.text_area(
            "Recovery opportunities JSON",
            value='[{"opportunity_id":"OP-1","action":"REDUCE"},{"opportunity_id":"OP-2","action":"RECOVER"},{"opportunity_id":"OP-3","action":"EXTERNAL_EXCHANGE"}]',
            key="sri_cascade_opportunities",
            height=100,
        )
        if st.button("Rank resource cascade", key="sri_rank_cascade"):
            try:
                results["cascade"] = rank_resource_cascade(_json_array(cascade_json, "Recovery opportunities"))
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Cascade ranking failed: {exc}")
        if "cascade" in results:
            _render_result(st, "Prevention-first resource cascade", results["cascade"])

    with tabs[10]:
        st.markdown("#### Bottleneck and physical infrastructure screening")
        st.caption("These checks use explicit user-entered capacities and route evidence. Proximity is not proof of a physical connection.")
        st.markdown("**Capacity bottleneck**")
        c1, c2 = st.columns(2)
        bottleneck_required = c1.text_input("Required resource quantity", key="sri_bottleneck_required")
        bottleneck_unit = c2.text_input("Required unit", key="sri_bottleneck_unit")
        capacities_json = st.text_area(
            "Capacity constraints JSON",
            value="[]",
            key="sri_bottleneck_capacities",
            height=100,
            help='Example: [{"constraint":"Treatment capacity","capacity":80,"unit":"m3/day"},{"constraint":"Storage withdrawal","capacity":60,"unit":"m3/day"}]',
        )
        if st.button("Detect limiting capacity", key="sri_detect_bottleneck"):
            try:
                results["bottleneck"] = detect_resource_bottleneck(
                    bottleneck_required,
                    unit=bottleneck_unit,
                    capacity_constraints=_json_array(capacities_json, "Capacity constraints"),
                )
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Bottleneck screening failed: {exc}")
        if "bottleneck" in results:
            _render_result(st, "Bottleneck result", results["bottleneck"])

        st.divider()
        st.markdown("**Preliminary transport / shared-infrastructure route screen**")
        connection_choice = st.selectbox(
            "Physical connection evidence",
            ["Not supplied", "Confirmed by user", "Unavailable"],
            key="sri_infrastructure_connection",
        )
        r1, r2 = st.columns(2)
        route_distance = r1.text_input("Route distance (km)", key="sri_infrastructure_distance")
        route_mode = r2.text_input("Transport / infrastructure mode", key="sri_infrastructure_mode")
        r3, r4 = st.columns(2)
        route_capacity = r3.text_input("Declared route capacity", key="sri_infrastructure_capacity")
        route_required = r4.text_input("Required quantity", key="sri_infrastructure_required")
        route_unit = st.text_input("Shared capacity / required unit", key="sri_infrastructure_unit")
        r5, r6 = st.columns(2)
        route_access = r5.text_input("Route access / survey evidence reference", key="sri_route_access")
        route_permit = r6.text_input("Permit reference", key="sri_route_permit")
        route_engineering = st.text_input("Engineering review reference", key="sri_route_engineering")
        if st.button("Assess preliminary infrastructure feasibility", key="sri_assess_infrastructure"):
            try:
                result = assess_infrastructure_route({
                    "connection_confirmed": (
                        True if connection_choice == "Confirmed by user"
                        else False if connection_choice == "Unavailable" else None
                    ),
                    "distance_km": route_distance,
                    "capacity": route_capacity,
                    "required_quantity": route_required,
                    "unit": route_unit,
                    "capacity_unit": route_unit,
                    "transport_mode": route_mode,
                    "route_access_evidence": route_access,
                    "permit_reference": route_permit,
                    "engineering_review_reference": route_engineering,
                })
                results["infrastructure_route"] = result
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Infrastructure screening failed: {exc}")
        if "infrastructure_route" in results:
            _render_result(st, "Infrastructure route result", results["infrastructure_route"])
            st.warning("A preliminary screen does not establish surveyed route access, hydraulic design, permit validity or construction approval.")

    with tabs[11]:
        st.markdown("#### Digital exchange agreement draft and delivery assurance")
        st.caption(
            "This records entered exchange terms and delivery evidence for review. "
            "It is not a signed contract, participant authorization, legal determination or physical transfer approval."
        )
        if not passports:
            st.info("Create a resource passport before drafting an exchange agreement.")
        else:
            with st.form("sri_exchange_agreement_form"):
                a1, a2 = st.columns(2)
                supplier = a1.text_input("Supplier organization / facility")
                buyer = a2.text_input("Buyer organization / facility")
                resource_ids = [str(item["resource_id"]) for item in passports]
                resource_choice = st.selectbox("Resource passport", resource_ids, key="sri_agreement_resource")
                selected_passport = next(item for item in passports if str(item["resource_id"]) == resource_choice)
                st.caption(f"Resource: {selected_passport['name']} · {selected_passport['resource_type']} · {selected_passport['unit']}")
                a3, a4 = st.columns(2)
                agreed_quantity = a3.text_input("Agreed quantity")
                quantity_tolerance = a4.text_input("Quantity tolerance (%)", value="0")
                delivery_schedule = st.text_input("Delivery schedule / period")
                quality_terms = st.text_area(
                    "Agreed quality limits JSON (minimum / maximum)",
                    value="{}",
                    height=100,
                )
                certificate_required = st.checkbox("A valid certificate is required for each delivery", value=True)
                treatment_responsibility = st.text_input("Treatment responsibility")
                testing_requirements = st.text_input("Testing requirements")
                shortage_response = st.text_area("Shortage response arrangement", height=60)
                rejection_procedure = st.text_area("Rejection / quarantine procedure", height=60)
                st.markdown("**Human approval references (references only; not signatures)**")
                ap1, ap2 = st.columns(2)
                engineering_approval = ap1.text_input("Engineering approval reference")
                safety_approval = ap2.text_input("Safety approval reference")
                ap3, ap4 = st.columns(2)
                environmental_approval = ap3.text_input("Environmental approval reference")
                commercial_approval = ap4.text_input("Commercial approval reference")
                create_agreement = st.form_submit_button("Create exchange agreement draft")
            if create_agreement:
                try:
                    agreement = validate_exchange_agreement({
                        "supplier": supplier,
                        "buyer": buyer,
                        "resource_id": resource_choice,
                        "resource_name": selected_passport["name"],
                        "agreed_quantity": agreed_quantity,
                        "unit": selected_passport["unit"],
                        "quantity_tolerance_percent": quantity_tolerance,
                        "quality_limits": _json_object(quality_terms, "Agreed quality limits"),
                        "delivery_schedule": delivery_schedule,
                        "certificate_required": certificate_required,
                        "treatment_responsibility": treatment_responsibility,
                        "testing_requirements": testing_requirements,
                        "shortage_response": shortage_response,
                        "rejection_procedure": rejection_procedure,
                        "approval_references": {
                            "engineering": engineering_approval,
                            "safety": safety_approval,
                            "environmental": environmental_approval,
                            "commercial": commercial_approval,
                        },
                    })
                    agreements.append(agreement)
                    st.session_state[STATE_PREFIX + "agreements"] = agreements
                    st.success(f"Agreement draft recorded: {agreement['agreement_id']} · {agreement['status']}")
                except Exception as exc:
                    st.error(f"Agreement draft was not created: {exc}")

        if agreements:
            st.markdown("**Recorded exchange drafts**")
            st.dataframe(pd.DataFrame([{
                "Agreement ID": item["agreement_id"],
                "Supplier": item["supplier"],
                "Buyer": item["buyer"],
                "Resource": item["resource_name"],
                "Quantity": item["agreed_quantity"],
                "Unit": item["unit"],
                "Status": item["status"],
                "Contract status": item["contract_status"],
            } for item in agreements]), use_container_width=True, hide_index=True)
            with st.form("sri_delivery_record_form"):
                agreement_options = [
                    f"{item['agreement_id']} · {item['supplier']} → {item['buyer']}"
                    for item in agreements
                ]
                selected_agreement_label = st.selectbox("Agreement", agreement_options, key="sri_delivery_agreement")
                selected_agreement_id = selected_agreement_label.split(" · ", 1)[0]
                selected_agreement = next(item for item in agreements if item["agreement_id"] == selected_agreement_id)
                d1, d2 = st.columns(2)
                delivery_date = d1.text_input("Delivery date (YYYY-MM-DD)")
                delivered_quantity = d2.text_input("Actual delivered quantity")
                quality_measurements = st.text_area("Measured delivery quality JSON", value="{}", height=90)
                d3, d4 = st.columns(2)
                certificate_reference_delivery = d3.text_input("Certificate reference")
                certificate_valid_until_delivery = d4.text_input("Certificate valid until (YYYY-MM-DD)")
                delivery_evidence_reference = st.text_input("Delivery / scale ticket / laboratory evidence reference")
                record_delivery = st.form_submit_button("Record and assess delivery")
            if record_delivery:
                try:
                    delivery_result = assess_exchange_delivery(
                        selected_agreement,
                        {
                            "delivery_date": delivery_date,
                            "delivered_quantity": delivered_quantity,
                            "quality": _json_object(quality_measurements, "Delivery quality measurements"),
                            "certificate_reference": certificate_reference_delivery,
                            "certificate_valid_until": certificate_valid_until_delivery,
                            "delivery_evidence_reference": delivery_evidence_reference,
                        },
                    )
                    deliveries.append(delivery_result)
                    st.session_state[STATE_PREFIX + "deliveries"] = deliveries
                    st.success(f"Delivery assessment recorded: {delivery_result['status']}")
                except Exception as exc:
                    st.error(f"Delivery assessment failed: {exc}")
        if deliveries:
            st.markdown("**Delivery assurance history**")
            st.dataframe(pd.DataFrame([{
                "Delivery ID": item["delivery_id"],
                "Agreement ID": item["agreement_id"],
                "Date": item["delivery_date"],
                "Expected": item["expected_quantity"],
                "Delivered": item["delivered_quantity"],
                "Unit": item["unit"],
                "Status": item["status"],
                "Deviations": ", ".join(item["deviations"]),
                "Human acceptance required": item["human_acceptance_required"],
            } for item in deliveries]), use_container_width=True, hide_index=True)
            selected_delivery = st.selectbox(
                "Inspect delivery assessment",
                [item["delivery_id"] for item in deliveries],
                key="sri_delivery_inspector",
            )
            _render_result(st, "Delivery assurance detail", next(item for item in deliveries if item["delivery_id"] == selected_delivery))
            st.warning("Delivery assessments are evidence records. A person must review and accept/reject the delivery under the applicable agreement.")

    with tabs[12]:
        st.markdown("#### Environmental impact and burden-shifting assessment")
        st.caption("Use factor values and references appropriate to the reporting boundary, geography and period. No factor is supplied or certified by this module.")
        environmental_quantities = [
            ("avoided_freshwater_m3", "Avoided freshwater (m³)"),
            ("avoided_wastewater_m3", "Avoided wastewater (m³)"),
            ("avoided_electricity_kwh", "Avoided electricity (kWh)"),
            ("avoided_fuel_kwh", "Avoided fuel energy (kWh)"),
            ("diverted_waste_kg", "Diverted waste (kg)"),
            ("added_treatment_electricity_kwh", "Added treatment electricity (kWh)"),
            ("added_transport_tonne_km", "Added transport (tonne-km)"),
            ("added_chemical_kg", "Added chemicals (kg)"),
            ("added_residual_waste_kg", "Added residual waste (kg)"),
        ]
        env_values = {}
        for index in range(0, len(environmental_quantities), 2):
            left, right = st.columns(2)
            for col, (key, label) in zip((left, right), environmental_quantities[index:index+2]):
                env_values[key] = col.text_input(label, key="sri_env_" + key)
        env1, env2, env3 = st.columns(3)
        reporting_period = env1.text_input("Reporting period", key="sri_env_period")
        facility_boundary = env2.text_input("Facility / system boundary", key="sri_env_boundary")
        geography = env3.text_input("Geography", value=str(facility.get("location") or ""), key="sri_env_geography")
        factors_json = st.text_area(
            "Versioned environmental factors JSON",
            value="{}",
            key="sri_environmental_factors",
            height=170,
            help='Required keys: freshwater, wastewater, electricity, fuel, waste_diversion, transport, chemical, residual_waste. Each requires value, exact unit, source_reference and version.',
        )
        env_status = st.selectbox("Environmental evidence level", ["FORECAST", "ESTIMATED", "MEASURED"], key="sri_env_status")
        if st.button("Calculate bounded environmental impact", key="sri_run_environmental"):
            try:
                if any(str(value).strip() == "" for value in env_values.values()):
                    raise ValueError("Enter every physical quantity explicitly. Use 0 only when the measured/assumed quantity is zero.")
                results["environmental_impact"] = calculate_environmental_impact(
                    reporting_period=reporting_period,
                    facility_boundary=facility_boundary,
                    geography=geography,
                    **{key: _finite_float(value, key, minimum=0) for key, value in env_values.items()},
                    factors=_json_object(factors_json, "Environmental factors"),
                    evidence_status=env_status,
                )
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Environmental calculation failed: {exc}")
        if "environmental_impact" in results:
            _render_result(st, "Environmental impact result", results["environmental_impact"])
            st.warning("This is a factor-based estimate using caller-supplied data. Do not publish a verified emissions or environmental claim without factor review, boundary validation and independent assurance.")

    with tabs[13]:
        st.markdown("#### Industrial improvement project prioritization")
        st.caption("This is a transparent multi-criteria ranking, not investment approval, ROI or a substitute for a business case.")
        projects_json = st.text_area(
            "Improvement project register JSON",
            value="[]",
            key="sri_investment_projects",
            height=200,
            help='Each project: project_id, name, feasibility_score, resource_impact_score, reliability_score, data_confidence_score, risk_score, implementation_difficulty_score (all 1–5), capex, annual_gross_benefit, annual_opex, currency, safety_status and evidence_reference.',
        )
        weights_json = st.text_area(
            "Scoring weights JSON (illustrative defaults; review before use)",
            value='{"feasibility":0.25,"resource_impact":0.25,"reliability":0.15,"data_confidence":0.15,"risk":0.10,"implementation_difficulty":0.10}',
            key="sri_investment_weights",
            height=90,
        )
        if st.button("Rank improvement projects", key="sri_rank_projects"):
            try:
                results["investment_prioritization"] = rank_resource_improvement_projects(
                    _json_array(projects_json, "Improvement projects"),
                    weights=_json_object(weights_json, "Project scoring weights"),
                )
                st.session_state[STATE_PREFIX + "results"] = results
            except Exception as exc:
                st.error(f"Project prioritization failed: {exc}")
        if "investment_prioritization" in results:
            _render_result(st, "Investment prioritization result", results["investment_prioritization"])
            st.warning("Projects blocked by safety are not approved. Scores and simple payback use entered assumptions and are not verified financial returns.")

    with tabs[14]:
        st.markdown("#### Reports and evidence export")
        report = {
            "report_type": "Industrial Resource Intelligence workspace snapshot",
            "status": "ENGINEERING_WORKSPACE_NOT_OPERATIONAL_AUTHORIZATION",
            "facility": facility,
            "resource_passports": passports,
            "passport_revision_history": passport_history,
            "passport_revision_integrity_check": verify_resource_passport_history(passport_history),
            "demands": demands,
            "exchange_candidates": routes,
            "exchange_agreements": agreements,
            "delivery_assessments": deliveries,
            "environmental_impact": results.get("environmental_impact"),
            "investment_prioritization": results.get("investment_prioritization"),
            "results": results,
            "limitations": [
                "No live supplier or customer participation is asserted.",
                "No cross-company tenant sharing is enabled by this module version.",
                "No physical infrastructure or transport route is presumed to exist.",
                "Safety and regulatory approvals are not independently verified.",
                "Forecast and financial statuses retain their evidence limitations.",
                "No production or equipment control is performed.",
            ],
        }
        st.download_button(
            "Download workspace evidence JSON",
            data=json.dumps(report, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
            file_name="industrial_resource_intelligence_evidence.json",
            mime="application/json",
            key="sri_export_json",
        )
        st.caption("Exports contain the current workspace snapshot and its recorded provenance. Review access controls before sharing.")
