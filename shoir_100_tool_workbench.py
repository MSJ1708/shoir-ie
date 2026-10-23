"""Streamlit renderer for the grouped Engineering Tool Library."""
from __future__ import annotations

import json
import hashlib
from typing import Any

from shoir_100_tool_registry import TOOL_CATALOG, get_tool, tool_access_allowed, tool_is_actionable
from shoir_100_tool_runtime import (
    carbon_emissions, clean_dataframe, convert_unit, engineering_economics,
    generate_synthetic_industrial_data, inventory_policy, monte_carlo_triangular,
    mtbf_mttr, oee, process_capability, profile_dataframe, read_dataset_bytes,
    result_to_csv_bytes, takt_capacity, time_study, work_sampling,
)


def _frame_fingerprint(frame: Any) -> str:
    try:
        import pandas as pd
        signature = str(tuple((str(c), str(frame[c].dtype)) for c in frame.columns))
        values = pd.util.hash_pandas_object(frame, index=True).values.tobytes()
        return hashlib.sha256(signature.encode("utf-8") + values).hexdigest()
    except Exception:
        return hashlib.sha256(frame.to_json(orient="split", date_format="iso", default_handler=str).encode("utf-8")).hexdigest()


def _parse_numbers(raw: str, label: str) -> list[float]:
    try:
        values = [float(part.strip()) for part in str(raw).replace(";", ",").split(",") if part.strip()]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a comma-separated list of numbers.") from exc
    if not values:
        raise ValueError(f"Enter at least one value for {label}.")
    return values


def _show_result(st: Any, result: dict[str, Any]) -> None:
    import pandas as pd
    st.markdown(f"**Method:** {result.get('method', 'Method not supplied')}")
    if result.get("provenance") or result.get("status"):
        st.caption(f"Status: {result.get('status')} · Provenance: {result.get('provenance', 'USER_INPUT')} · Fingerprint: {result.get('source_fingerprint', '')[:16]}")
    metric_rows = []
    for key, value in result.get("metrics", {}).items():
        unit = result.get("units", {}).get(key, "")
        display_value = "Not available" if value is None else value
        metric_rows.append({"Metric": key.replace("_", " ").title(), "Value": display_value, "Unit": unit})
    st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, hide_index=True)
    chart = [row for row in result.get("chart", []) if row.get("value") is not None]
    if chart and len(chart) > 1:
        st.bar_chart(pd.DataFrame(chart).set_index("metric"), height=220)
    if result.get("assumptions"):
        with st.expander("Formula, assumptions and limitations", expanded=True):
            for item in result["assumptions"]:
                st.write(f"• {item}")
    for warning in result.get("warnings", []):
        st.warning(warning)
    report = result_to_csv_bytes(result)
    st.download_button(
        "Export this result (CSV)", data=report,
        file_name=f"shoir_{result.get('tool_id','tool').lower()}_result.csv",
        mime="text/csv", key=f"shoir100_export_{result.get('tool_id')}",
    )


def _read_dataset_ui(st: Any, pd: Any, tool_id: str) -> None:
    st.subheader("Dataset context")
    st.caption("An upload is parsed before the workbench replaces its session-scoped dataset. Existing saved workbooks are not altered by this importer.")
    upload = st.file_uploader("Upload a CSV or Excel workbook", type=["csv", "xlsx", "xls"], key="shoir100_uploader")
    if upload is not None:
        try:
            parsed = read_dataset_bytes(upload.name, upload.getvalue())
            if isinstance(parsed, dict):
                names = list(parsed)
                if not names:
                    st.error("No sheets were found; the existing dataset was kept.")
                else:
                    sheet = st.selectbox("Preview sheet", names, key="shoir100_sheet")
                    candidate = parsed[sheet]
                    st.caption(f"Workbook: {upload.name} · selected sheet: {sheet}")
                    st.dataframe(candidate.head(50), use_container_width=True)
                    if st.button("Use selected sheet in this session", key="shoir100_apply_sheet"):
                        st.session_state["_shoir100_previous_dataset"] = st.session_state.get("_shoir100_dataset")
                        st.session_state["_shoir100_dataset"] = candidate.copy(deep=True)
                        st.session_state["_shoir100_clean_candidate"] = None
                        st.session_state["_shoir100_clean_audit"] = None
                        st.session_state["_shoir100_clean_source_fingerprint"] = None
                        st.session_state["_shoir100_dataset_name"] = f"{upload.name} · {sheet}"
                        st.session_state["_shoir100_dataset_provenance"] = "IMPORTED"
                        st.success("Sheet loaded in the current session. Cross-login persistence is not implied.")
            else:
                st.caption(f"Parsed file: {upload.name}")
                st.dataframe(parsed.head(50), use_container_width=True)
                if st.button("Use dataset in this session", key="shoir100_apply_dataset"):
                    st.session_state["_shoir100_previous_dataset"] = st.session_state.get("_shoir100_dataset")
                    st.session_state["_shoir100_dataset"] = parsed.copy(deep=True)
                    st.session_state["_shoir100_clean_candidate"] = None
                    st.session_state["_shoir100_clean_audit"] = None
                    st.session_state["_shoir100_clean_source_fingerprint"] = None
                    st.session_state["_shoir100_dataset_name"] = upload.name
                    st.session_state["_shoir100_dataset_provenance"] = "IMPORTED"
                    st.success("Dataset loaded in the current session. The prior dataset remains recoverable with Undo.")
        except Exception as exc:
            st.error(str(exc))
            st.info("The previous valid session dataset has not been replaced.")
    current = st.session_state.get("_shoir100_dataset")
    if current is not None:
        st.caption(f"Current dataset: {st.session_state.get('_shoir100_dataset_name', 'Unnamed dataset')} · {len(current):,} rows × {len(current.columns):,} columns · {st.session_state.get('_shoir100_dataset_provenance', 'IMPORTED')}")
        st.dataframe(current.head(20), use_container_width=True)


def render_100_tool_workbench(tier: str, username: str) -> None:
    import pandas as pd
    import streamlit as st

    st.header("Engineering Tool Library")
    st.caption("100 stable tool IDs across ten workbenches. This is an additive workspace inside the current application shell; it does not replace the existing navigation or modules.")
    st.info("Only tools with an implemented deterministic action are executable here. A mapped route or catalog card is not proof of a validated specialist engine. Readiness and access are checked separately.")

    filter_col1, filter_col2 = st.columns([1.2, 1])
    labels = ["All workbenches"] + list(dict.fromkeys(row["workbench"] for row in TOOL_CATALOG))
    with filter_col1:
        selected_workbench = st.selectbox("Workbench", labels, key="shoir100_workbench_filter")
    with filter_col2:
        selected_readiness = st.selectbox("Readiness", ["All statuses", "Executable actions", "Needs validation", "Foundation only", "Missing", "Requires configuration"], key="shoir100_readiness_filter")

    candidates = list(TOOL_CATALOG)
    if selected_workbench != "All workbenches":
        candidates = [row for row in candidates if row["workbench"] == selected_workbench]
    status_filter = {
        "Executable actions": {"IMPLEMENTED_NEEDS_VALIDATION", "VERIFIED_WORKING"},
        "Needs validation": {"IMPLEMENTED_NEEDS_VALIDATION"},
        "Foundation only": {"FOUNDATION_ONLY"},
        "Missing": {"MISSING", "BLOCKED"},
        "Requires configuration": {"EXTERNAL_CONFIGURATION_REQUIRED"},
    }.get(selected_readiness)
    if status_filter:
        candidates = [row for row in candidates if row["implementation_status"] in status_filter]
    if not candidates:
        st.info("No tools match these filters. Clear one filter to browse the catalog.")
        return

    def display_label(row: dict[str, Any]) -> str:
        allowed = tool_access_allowed(row["tool_id"], tier)
        lock = "" if allowed else " · 🔒"
        return f'{row["tool_id"]} · {row["canonical_name"]} · {row["target_minimum_tier"]}{lock}'

    selected_id = st.selectbox("Select a tool", [row["tool_id"] for row in candidates], format_func=lambda key: display_label(get_tool(key) or {}), key="shoir100_tool_choice")
    tool = get_tool(selected_id)
    if not tool:
        st.error("Tool registry entry not found. No action was executed.")
        return

    head_col, status_col = st.columns([3, 1.2])
    with head_col:
        st.subheader(f'{tool["tool_id"]} · {tool["canonical_name"]}')
        st.caption(tool.get("purpose", "Purpose not yet documented."))
        if tool.get("existing_module_or_route"):
            st.caption(f'Related existing module/route: {tool["existing_module_or_route"]}')
    with status_col:
        st.metric("Minimum tier", tool["target_minimum_tier"])
        st.write(f'Status: **{tool["implementation_status"]}**')

    if not tool_access_allowed(tool["tool_id"], tier):
        st.warning(f'Access denied: {tool["canonical_name"]} requires {tool["target_minimum_tier"]}. Your current tier is {tier}.')
        st.info("You can review the purpose and readiness status, but no protected tool action will execute.")
        return

    if not tool_is_actionable(tool["tool_id"]):
        status = tool["implementation_status"]
        if status == "EXTERNAL_CONFIGURATION_REQUIRED":
            st.warning("This capability requires approved integration configuration and an authenticated non-production test.")
        elif status == "MISSING":
            st.error("No operational implementation is available for this target yet. It is listed for traceability only.")
        else:
            st.info("This target is not yet executable in this new library. Use the related existing module if appropriate, and treat the target's specialist acceptance as unverified.")
        st.caption("No sample result or synthetic success is generated for a foundation-only or missing tool.")
        return

    if selected_id in {"T011", "T013", "T014"}:
        _read_dataset_ui(st, pd, selected_id)
    if selected_id == "T011":
        st.info("Import readiness: CSV/XLS/XLSX only; up to 25 MiB; uploaded file is previewed before the explicit session apply action.")
        current = st.session_state.get("_shoir100_dataset")
        if current is not None:
            st.success("A dataset is available to this session. Use T013 to profile it or T014 to preview reversible cleaning.")
        return

    if selected_id == "T013":
        current = st.session_state.get("_shoir100_dataset")
        if current is None:
            st.info("Upload and explicitly apply a CSV/XLSX dataset above, then run the profile. No data is inferred from examples.")
            return
        if st.button("Profile current dataset", key="shoir100_profile"):
            try:
                result = profile_dataframe(current)
                _show_result(st, result)
                st.dataframe(pd.DataFrame(result["tables"]["columns"]), use_container_width=True)
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T014":
        current = st.session_state.get("_shoir100_dataset")
        if current is None:
            st.info("Upload and explicitly apply a source dataset before cleaning.")
            return
        duplicate = st.checkbox("Remove exact duplicate rows in the candidate", value=True, key="shoir100_drop_duplicates")
        strategy = st.selectbox("Missing-value handling", ["keep", "drop_rows", "fill_median"], format_func=lambda x: {"keep":"Keep missing values","drop_rows":"Drop rows with any missing values","fill_median":"Fill numeric missing values with column median"}[x], key="shoir100_missing_strategy")
        if st.button("Preview cleaning (source unchanged)", key="shoir100_clean_preview"):
            try:
                candidate, audit = clean_dataframe(current, drop_duplicates=duplicate, missing_strategy=strategy)
                st.session_state["_shoir100_clean_candidate"] = candidate
                st.session_state["_shoir100_clean_audit"] = audit
                st.session_state["_shoir100_clean_source_fingerprint"] = _frame_fingerprint(current)
            except ValueError as exc:
                st.error(str(exc))
        candidate = st.session_state.get("_shoir100_clean_candidate")
        audit = st.session_state.get("_shoir100_clean_audit")
        if candidate is not None and audit:
            st.json(audit)
            st.dataframe(candidate.head(50), use_container_width=True)
            if st.button("Apply candidate to session", key="shoir100_clean_apply"):
                expected_source = st.session_state.get("_shoir100_clean_source_fingerprint")
                if expected_source != _frame_fingerprint(current):
                    st.warning("This cleaning preview is stale because the source dataset changed. Preview again before applying.")
                    st.session_state["_shoir100_clean_candidate"] = None
                    st.session_state["_shoir100_clean_audit"] = None
                else:
                    st.session_state["_shoir100_previous_dataset"] = current.copy(deep=True)
                    st.session_state["_shoir100_dataset"] = candidate.copy(deep=True)
                    st.session_state["_shoir100_dataset_provenance"] = "IMPORTED"
                    st.session_state["_shoir100_clean_candidate"] = None
                    st.session_state["_shoir100_clean_audit"] = None
                    st.success("Candidate applied. The prior dataset is available through Undo in this session.")
        if st.button("Undo last session dataset change", key="shoir100_clean_undo"):
            previous = st.session_state.get("_shoir100_previous_dataset")
            if previous is None:
                st.warning("No recoverable prior dataset is available in this session.")
            else:
                st.session_state["_shoir100_dataset"] = previous.copy(deep=True)
                st.session_state["_shoir100_previous_dataset"] = None
                st.success("The previous session dataset has been restored.")
        return

    if selected_id == "T016":
        st.subheader("Unit converter")
        c1, c2, c3 = st.columns(3)
        with c1:
            value = st.number_input("Value", value=1.0, key="shoir100_unit_value")
        all_units = ["m","cm","mm","km","ft","in","kg","g","lb","tonne","s","min","h","day","°C","°F","K"]
        with c2:
            src = st.selectbox("From unit", all_units, index=0, key="shoir100_unit_src")
        with c3:
            dst = st.selectbox("To unit", all_units, index=1, key="shoir100_unit_dst")
        if st.button("Convert units", key="shoir100_convert"):
            try:
                _show_result(st, convert_unit(value, src, dst))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T019":
        st.subheader("Synthetic industrial data")
        c1, c2 = st.columns(2)
        with c1:
            n = st.number_input("Rows", min_value=1, max_value=10000, value=100, step=1, key="shoir100_synth_rows")
        with c2:
            seed = st.number_input("Random seed", min_value=0, max_value=2147483647, value=7, step=1, key="shoir100_synth_seed")
        if st.button("Generate synthetic dataset", key="shoir100_generate_synthetic"):
            result = generate_synthetic_industrial_data(int(n), int(seed))
            st.session_state["_shoir100_synthetic_candidate"] = result
        result = st.session_state.get("_shoir100_synthetic_candidate")
        if result:
            st.warning(result["note"])
            st.caption(f'Provenance: SYNTHETIC · seed={result["seed"]} · fingerprint={result["source_fingerprint"][:16]}')
            st.dataframe(pd.DataFrame(result["records"]), use_container_width=True)
            csv_data = pd.DataFrame(result["records"]).to_csv(index=False).encode("utf-8-sig")
            st.download_button("Export synthetic practice data (CSV)", csv_data, "shoir_synthetic_practice_data.csv", "text/csv", key="shoir100_synthetic_export")
        return

    if selected_id == "T021":
        st.subheader("Time study")
        raw_times = st.text_input("Observed times (comma-separated)", value="10, 12, 11, 10.5, 11.5", key="shoir100_times")
        rating = st.number_input("Performance rating (%)", min_value=1.0, max_value=250.0, value=100.0, key="shoir100_rating")
        allowance = st.number_input("Allowance as % of total standard time", min_value=0.0, max_value=99.9, value=15.0, key="shoir100_allowance")
        unit = st.selectbox("Time unit", ["s","min","h"], key="shoir100_time_unit")
        if st.button("Calculate standard time", key="shoir100_time_study"):
            try:
                _show_result(st, time_study(_parse_numbers(raw_times, "Observed times"), rating, allowance, unit))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T022":
        st.subheader("Work sampling")
        c1, c2 = st.columns(2)
        with c1:
            active = st.number_input("Activity observations", min_value=0, value=30, step=1, key="shoir100_sample_active")
        with c2:
            total = st.number_input("Total observations", min_value=1, value=100, step=1, key="shoir100_sample_total")
        if st.button("Estimate activity proportion", key="shoir100_sample_run"):
            try:
                _show_result(st, work_sampling(active, total))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T023":
        c1, c2, c3 = st.columns(3)
        with c1:
            available = st.number_input("Available production time", min_value=0.001, value=480.0, key="shoir100_takt_time")
        with c2:
            demand = st.number_input("Required demand (units)", min_value=0.001, value=120.0, key="shoir100_takt_demand")
        with c3:
            unit = st.selectbox("Available time unit", ["min","h","s"], key="shoir100_takt_unit")
        if st.button("Calculate takt and capacity", key="shoir100_takt_run"):
            try:
                _show_result(st, takt_capacity(available, demand, unit))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T026":
        st.subheader("OEE and loss analysis")
        cols = st.columns(5)
        planned = cols[0].number_input("Planned time", min_value=0.001, value=480.0, key="shoir100_oee_planned")
        down = cols[1].number_input("Downtime", min_value=0.0, value=60.0, key="shoir100_oee_down")
        cycle = cols[2].number_input("Ideal cycle", min_value=0.001, value=0.5, key="shoir100_oee_cycle")
        total = cols[3].number_input("Total count", min_value=1, value=600, key="shoir100_oee_total")
        good = cols[4].number_input("Good count", min_value=0, value=570, key="shoir100_oee_good")
        unit = st.selectbox("Time unit for planned/downtime/cycle", ["min","s","h"], key="shoir100_oee_unit")
        if st.button("Calculate OEE", key="shoir100_oee_run"):
            try:
                _show_result(st, oee(planned, down, cycle, int(total), int(good), unit))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T032":
        st.subheader("Process capability")
        values = st.text_input("Observed measurements (comma-separated)", value="9, 10, 11, 10.5, 9.5", key="shoir100_cap_values")
        c1, c2 = st.columns(2)
        with c1:
            lsl = st.number_input("Lower specification limit", value=8.0, key="shoir100_lsl")
        with c2:
            usl = st.number_input("Upper specification limit", value=12.0, key="shoir100_usl")
        if st.button("Calculate capability indices", key="shoir100_cap_run"):
            try:
                _show_result(st, process_capability(_parse_numbers(values, "Observed measurements"), lsl, usl))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T042":
        c1, c2, c3 = st.columns(3)
        period = c1.number_input("Observation period (hours)", min_value=0.001, value=100.0, key="shoir100_mtbf_period")
        down = c2.number_input("Downtime (hours)", min_value=0.0, value=10.0, key="shoir100_mtbf_down")
        failures = c3.number_input("Failure count", min_value=0, value=3, step=1, key="shoir100_mtbf_failures")
        if st.button("Calculate MTBF/MTTR", key="shoir100_mtbf_run"):
            try:
                _show_result(st, mtbf_mttr(period, down, int(failures)))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T055":
        st.subheader("EOQ / reorder policy")
        cols = st.columns(4)
        annual = cols[0].number_input("Annual demand", min_value=0.001, value=10000.0, key="shoir100_eoq_demand")
        order_cost = cols[1].number_input("Order cost", min_value=0.001, value=50.0, key="shoir100_eoq_order_cost")
        hold_cost = cols[2].number_input("Annual holding cost/unit", min_value=0.001, value=2.0, key="shoir100_eoq_hold")
        days = cols[3].number_input("Working days/year", min_value=1, value=250, key="shoir100_eoq_days")
        cols2 = st.columns(4)
        daily = cols2[0].number_input("Mean daily demand", min_value=0.0, value=40.0, key="shoir100_eoq_daily")
        lead = cols2[1].number_input("Lead time (days)", min_value=0.0, value=5.0, key="shoir100_eoq_lead")
        daily_sd = cols2[2].number_input("Daily demand std dev", min_value=0.0, value=0.0, key="shoir100_eoq_sd")
        z = cols2[3].number_input("Service z value", min_value=0.0, value=0.0, key="shoir100_eoq_z")
        if st.button("Calculate inventory policy", key="shoir100_eoq_run"):
            try:
                _show_result(st, inventory_policy(annual, order_cost, hold_cost, daily, lead, daily_demand_std=daily_sd, service_z=z, working_days=days))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T072":
        cols = st.columns(4)
        low = cols[0].number_input("Low", value=0.0, key="shoir100_mc_low")
        mode = cols[1].number_input("Most likely", value=10.0, key="shoir100_mc_mode")
        high = cols[2].number_input("High", value=20.0, key="shoir100_mc_high")
        iterations = cols[3].number_input("Iterations", min_value=100, max_value=100000, value=5000, step=100, key="shoir100_mc_n")
        seed = st.number_input("Random seed", min_value=0, max_value=2147483647, value=7, key="shoir100_mc_seed")
        if st.button("Run Monte Carlo", key="shoir100_mc_run"):
            try:
                _show_result(st, monte_carlo_triangular(low, mode, high, int(iterations), int(seed)))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T078":
        cols = st.columns(3)
        activity = cols[0].number_input("Activity quantity", min_value=0.0, value=1000.0, key="shoir100_carbon_activity")
        factor = cols[1].number_input("Emissions factor", min_value=0.0, value=0.5, key="shoir100_carbon_factor")
        activity_unit = cols[2].text_input("Activity unit", value="kWh", key="shoir100_carbon_activity_unit")
        emission_unit = st.text_input("Output emissions unit", value="kg CO₂e", key="shoir100_carbon_emission_unit")
        source = st.text_input("Factor source/reference", value="", key="shoir100_carbon_source")
        version = st.text_input("Factor version", value="", key="shoir100_carbon_version")
        factor_date = st.text_input("Factor date (YYYY-MM-DD)", value="", key="shoir100_carbon_date")
        if st.button("Calculate emissions estimate", key="shoir100_carbon_run"):
            try:
                _show_result(st, carbon_emissions(activity, factor, activity_unit=activity_unit, emission_unit=emission_unit, factor_source=source, factor_version=version, factor_date=factor_date))
            except ValueError as exc:
                st.error(str(exc))
        return

    if selected_id == "T081":
        st.subheader("Engineering economics")
        cashflows = st.text_input("Cash flows (comma-separated; first value is period 0)", value="-100, 60, 60", key="shoir100_npv_cashflows")
        rate = st.number_input("Discount rate (%)", min_value=-99.9, max_value=1000.0, value=10.0, key="shoir100_npv_rate")
        if st.button("Calculate NPV / IRR / discounted payback", key="shoir100_npv_run"):
            try:
                _show_result(st, engineering_economics(_parse_numbers(cashflows, "Cash flows"), rate))
            except ValueError as exc:
                st.error(str(exc))
        return

    st.info("This tool has a registry entry but no executable action was registered. The request is not treated as completed.")
