"""Streamlit surface for Industrial Resource Intelligence.

The UI is deliberately nested inside the existing Shoir-IE Workbench. It uses
explicit manual/imported inputs, per-user workspace persistence and human gates.
It does not claim multi-company shared tenancy or live industrial connectivity.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pandas as pd

from shoir_resource_intelligence import (
    PROVENANCE_VALUES,
    ResourceValidationError,
    validate_resource_passport,
    validate_import_rows,
    detect_resource_loss,
    assess_resource_compatibility,
    optimize_resource_network,
    simulate_supplier_disruption,
    evaluate_safety_gate,
    calculate_exchange_value,
    forecast_resource_quality,
    calculate_supply_reliability,
    propagate_network_impact,
    rank_resource_cascade,
)


STATE_PREFIX = "shoir_resource_intelligence_"


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
        mode = "managed per-user workspace" if durable_backend_configured() else "local fallback"
        return True, f"Saved to the {mode}. Local fallback may not survive a hosted restart."
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
    demands = st.session_state.get(STATE_PREFIX + "demands", [])
    routes = st.session_state.get(STATE_PREFIX + "routes", [])
    results = st.session_state.get(STATE_PREFIX + "results", {})
    imports = st.session_state.get(STATE_PREFIX + "import_validation", None)

    if not isinstance(facility, dict):
        facility = {}
    if not isinstance(passports, list):
        passports = []
    if not isinstance(demands, list):
        demands = []
    if not isinstance(routes, list):
        routes = []
    if not isinstance(results, dict):
        results = {}

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
        "Resource Memory", "Reports",
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
            "CSV must contain facility_id, name, resource_type, available_quantity, unit and provenance. "
            "Optional quality must be a JSON object string. The source file is not modified."
        )
        upload = st.file_uploader(
            "Upload CSV resource records",
            type=["csv"],
            key="sri_resource_csv_upload",
        )
        if upload is not None and st.button("Validate imported rows", key="sri_validate_import"):
            try:
                frame = pd.read_csv(upload)
                rows = frame.to_dict("records")
                for row in rows:
                    if isinstance(row.get("quality"), str) and row["quality"].strip():
                        row["quality"] = json.loads(row["quality"])
                    elif not row.get("quality"):
                        row["quality"] = {}
                imported = validate_import_rows(rows)
                st.session_state[STATE_PREFIX + "import_validation"] = imported
                st.session_state[STATE_PREFIX + "import_source_name"] = upload.name
                imports = imported
            except Exception as exc:
                st.error(f"Import validation failed safely: {exc}")
        if imports:
            _render_result(st, "Import validation result", imports)
            if imports.get("accepted") and st.button("Add valid rows to resource passports", key="sri_add_imported"):
                existing_ids = {str(item.get("resource_id")) for item in passports}
                additions = [item for item in imports["accepted"] if str(item.get("resource_id")) not in existing_ids]
                passports = passports + additions
                st.session_state[STATE_PREFIX + "passports"] = passports
                st.success(f"Added {len(additions)} validated rows. Provenance remains as supplied; no source row was rewritten.")

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
            quality_json = st.text_area("Measured quality properties (JSON object)", value="{}", height=90)
            c5, c6 = st.columns(2)
            provenance = c5.selectbox("Data provenance", list(PROVENANCE_VALUES), index=2)
            measured_at = c6.text_input("Measurement timestamp (ISO-8601 with timezone)", value="")
            c7, c8 = st.columns(2)
            temperature = c7.text_input("Temperature °C (optional)", value="")
            pressure = c8.text_input("Pressure kPa (optional)", value="")
            source_reference = st.text_input("Source / laboratory / meter reference")
            treatment_notes = st.text_input("Treatment and handling notes")
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
                    "source_reference": source_reference, "treatment_notes": treatment_notes,
                    "safety_restrictions": safety_restrictions,
                }
                passport = validate_resource_passport(payload)
                passports.append(passport)
                st.session_state[STATE_PREFIX + "passports"] = passports
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
        loss_provenance = st.selectbox("Measurement provenance", list(PROVENANCE_VALUES), index=1, key="sri_loss_provenance")
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
                        "required_quantity": float(required_quantity),
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
                            "resource_type": new_demand_type, "required_quantity": float(required_quantity),
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
                route_cost = r3.text_input("Resource unit cost")
                transport_cost = r4.text_input("Transport cost / unit")
                treatment_cost = r5.text_input("Treatment cost / unit", value="0")
                route_capacity = st.text_input("Maximum route quantity (blank = supply/demand limit)")
                add_route = st.form_submit_button("Add exchange candidate")
            if add_route:
                try:
                    route = {
                        "supply_id": supply_choice, "demand_id": demand_choice,
                        "unit_cost": float(route_cost),
                        "transport_cost_per_unit": float(transport_cost),
                        "treatment_cost_per_unit": float(treatment_cost),
                    }
                    if route_capacity.strip():
                        route["capacity"] = float(route_capacity)
                    if min(route["unit_cost"], route["transport_cost_per_unit"], route["treatment_cost_per_unit"]) < 0:
                        raise ValueError("Route costs cannot be negative.")
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
            _render_result(st, "Current passport history snapshot", passports)
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
        st.markdown("#### Reports and evidence export")
        report = {
            "report_type": "Industrial Resource Intelligence workspace snapshot",
            "status": "ENGINEERING_WORKSPACE_NOT_OPERATIONAL_AUTHORIZATION",
            "facility": facility,
            "resource_passports": passports,
            "demands": demands,
            "exchange_candidates": routes,
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
