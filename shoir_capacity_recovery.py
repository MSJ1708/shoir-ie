"""Validated production-capacity and downtime-recovery calculation service.

Pure calculations only: no factory connection, persistence, or claim that a scenario
predicts actual performance. Numeric errors are reported rather than silently coerced
to zero or clipped.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd

FORMULA_VERSION = "capacity-recovery/1.0.0"
REQUIRED_COLUMNS = ("Line", "PlannedMin", "DowntimeMin", "IdealCycleSec", "TotalCount", "GoodCount")
NUMERIC_COLUMNS = REQUIRED_COLUMNS[1:]


def _finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def validate_production_events(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate production rows without mutating input or replacing bad values."""
    if not isinstance(events, pd.DataFrame):
        raise TypeError("Production events must be a pandas DataFrame.")
    errors: list[str] = []
    warnings: list[str] = []
    if events.columns.duplicated().any():
        errors.append("Duplicate column names are not allowed.")
    missing = [column for column in REQUIRED_COLUMNS if column not in events.columns]
    if missing:
        errors.extend(f"Missing required column: {column}" for column in missing)
        return events.copy(deep=True), {
            "valid": False, "errors": errors, "warnings": warnings,
            "rows": len(events), "required_columns": list(REQUIRED_COLUMNS),
        }
    if events.empty:
        errors.append("Production events are empty.")

    frame = events.loc[:, list(REQUIRED_COLUMNS)].copy(deep=True)
    line_values = frame["Line"].astype("string").str.strip()
    bad_lines = line_values.isna() | line_values.eq("")
    if bool(bad_lines.any()):
        errors.append(f"Line must be non-empty for every row ({int(bad_lines.sum())} invalid).")
    frame["Line"] = line_values

    for column in NUMERIC_COLUMNS:
        converted = pd.to_numeric(frame[column], errors="coerce")
        invalid = converted.isna() | ~converted.map(_finite_number)
        if bool(invalid.any()):
            errors.append(f"{column} contains {int(invalid.sum())} missing, non-numeric, or non-finite value(s).")
        frame[column] = converted

    ready = frame.loc[:, list(NUMERIC_COLUMNS)].notna().all(axis=1)
    if bool(ready.any()):
        valid_rows = frame.loc[ready]
        for column in ("PlannedMin", "IdealCycleSec"):
            bad = valid_rows[column] <= 0
            if bool(bad.any()):
                errors.append(f"{column} must be greater than zero ({int(bad.sum())} invalid row(s)).")
        for column in ("DowntimeMin", "TotalCount", "GoodCount"):
            bad = valid_rows[column] < 0
            if bool(bad.any()):
                errors.append(f"{column} cannot be negative ({int(bad.sum())} invalid row(s)).")
        bad_downtime = valid_rows["DowntimeMin"] > valid_rows["PlannedMin"]
        if bool(bad_downtime.any()):
            errors.append(f"DowntimeMin exceeds PlannedMin in {int(bad_downtime.sum())} row(s).")
        bad_good = valid_rows["GoodCount"] > valid_rows["TotalCount"]
        if bool(bad_good.any()):
            errors.append(f"GoodCount exceeds TotalCount in {int(bad_good.sum())} row(s).")
        no_runtime = (
            (valid_rows["PlannedMin"] <= valid_rows["DowntimeMin"])
            & (valid_rows["TotalCount"] > 0)
        )
        if bool(no_runtime.any()):
            errors.append("Rows with production output must have positive runtime after downtime.")
        zero_output = valid_rows["TotalCount"] == 0
        if bool(zero_output.any()):
            warnings.append(f"{int(zero_output.sum())} row(s) report zero output; performance and quality interpretation may be limited.")
        runtime = valid_rows["PlannedMin"] - valid_rows["DowntimeMin"]
        perf = valid_rows["TotalCount"] * valid_rows["IdealCycleSec"] / (runtime.replace(0, float("nan")) * 60.0)
        if bool((perf > 1.0 + 1e-9).fillna(False).any()):
            warnings.append("Observed output exceeds ideal-cycle capacity in one or more rows; check cycle-time units and data quality. Values are not capped.")

    return frame, {
        "valid": not errors, "errors": errors, "warnings": warnings,
        "rows": int(len(frame)), "required_columns": list(REQUIRED_COLUMNS),
    }


def calculate_line_metrics(events: pd.DataFrame) -> pd.DataFrame:
    """Calculate availability, performance, quality, OEE and theoretical capacity.

    Availability = runtime / planned time.
    Performance = total count × ideal cycle seconds / runtime seconds.
    Quality = good count / total count.
    OEE = availability × performance × quality.
    Performance is not capped at 100%; a value above 100% is a diagnostic.
    """
    frame, report = validate_production_events(events)
    if not report["valid"]:
        raise ValueError("Invalid production events: " + " ".join(report["errors"]))

    frame["_RuntimeMin"] = frame["PlannedMin"] - frame["DowntimeMin"]
    frame["_IdealSeconds"] = frame["TotalCount"] * frame["IdealCycleSec"]
    frame["_TheoreticalCapacity"] = frame["PlannedMin"] * 60.0 / frame["IdealCycleSec"]
    grouped = frame.groupby("Line", sort=False, dropna=False).agg(
        PlannedMin=("PlannedMin", "sum"),
        DowntimeMin=("DowntimeMin", "sum"),
        RuntimeMin=("_RuntimeMin", "sum"),
        TotalCount=("TotalCount", "sum"),
        GoodCount=("GoodCount", "sum"),
        IdealSeconds=("_IdealSeconds", "sum"),
        TheoreticalCapacityUnits=("_TheoreticalCapacity", "sum"),
    )
    grouped["AvailabilityPct"] = grouped["RuntimeMin"] / grouped["PlannedMin"] * 100.0
    grouped["PerformancePct"] = grouped.apply(
        lambda row: row["IdealSeconds"] / (row["RuntimeMin"] * 60.0) * 100.0
        if row["RuntimeMin"] > 0 else 0.0, axis=1,
    )
    grouped["QualityPct"] = grouped.apply(
        lambda row: row["GoodCount"] / row["TotalCount"] * 100.0
        if row["TotalCount"] > 0 else float("nan"), axis=1,
    )
    grouped["OEEPct"] = grouped["AvailabilityPct"] * grouped["PerformancePct"] * grouped["QualityPct"] / 10000.0
    grouped["GoodUnitsPerPlannedHour"] = grouped["GoodCount"] / grouped["PlannedMin"] * 60.0
    grouped["CapacityAtTargetOEE_85Pct"] = grouped["TheoreticalCapacityUnits"] * 0.85
    grouped["OEEStatus"] = grouped["OEEPct"].map(
        lambda value: "Not available" if not _finite_number(value)
        else ("Diagnostic: above 100%" if value > 100.0 else "Calculated")
    )
    grouped.index.name = "Line"
    return grouped.reset_index().drop(columns=["IdealSeconds"])


def estimate_downtime_recovery(events: pd.DataFrame, downtime_reduction_fraction: float) -> pd.DataFrame:
    """Estimate incremental good units if a fraction of observed downtime is recovered.

    This simulated scenario assumes observed row-level performance and quality remain
    unchanged during recovered time. It is not a forecast or a savings guarantee.
    """
    if not _finite_number(downtime_reduction_fraction):
        raise ValueError("Downtime reduction fraction must be a finite number from 0 to 1.")
    fraction = float(downtime_reduction_fraction)
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("Downtime reduction fraction must be between 0 and 1.")
    frame, report = validate_production_events(events)
    if not report["valid"]:
        raise ValueError("Invalid production events: " + " ".join(report["errors"]))

    frame["_RuntimeMin"] = frame["PlannedMin"] - frame["DowntimeMin"]
    frame["_RecoveredMin"] = frame["DowntimeMin"] * fraction
    frame["_ObservedPerformance"] = frame.apply(
        lambda row: row["TotalCount"] * row["IdealCycleSec"] / (row["_RuntimeMin"] * 60.0)
        if row["_RuntimeMin"] > 0 else 0.0, axis=1,
    )
    frame["_ObservedQuality"] = frame.apply(
        lambda row: row["GoodCount"] / row["TotalCount"] if row["TotalCount"] > 0 else 0.0,
        axis=1,
    )
    frame["EstimatedAdditionalGoodUnits"] = (
        frame["_RecoveredMin"] * 60.0 / frame["IdealCycleSec"]
        * frame["_ObservedPerformance"] * frame["_ObservedQuality"]
    )
    result = frame.groupby("Line", sort=False).agg(
        PlannedMin=("PlannedMin", "sum"),
        ObservedDowntimeMin=("DowntimeMin", "sum"),
        RecoveredDowntimeMin=("_RecoveredMin", "sum"),
        ObservedGoodUnits=("GoodCount", "sum"),
        EstimatedAdditionalGoodUnits=("EstimatedAdditionalGoodUnits", "sum"),
    ).reset_index()
    result["ScenarioClassification"] = "Simulated"
    result["Assumption"] = "Observed row-level performance and quality remain unchanged during recovered time."
    return result


def _canonical_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for row in frame.loc[:, list(REQUIRED_COLUMNS)].to_dict(orient="records"):
        records.append({
            key: str(value).strip() if key == "Line" else float(value)
            for key, value in row.items()
        })
    return records


def build_evidence_manifest(
    events: pd.DataFrame,
    line_metrics: pd.DataFrame,
    recovery_scenario: pd.DataFrame | None = None,
    *,
    source_name: str = "user-provided production data",
    source_type: str = "unspecified",
) -> dict[str, Any]:
    """Link input/output hashes and assumptions; hashes do not verify source truth."""
    frame, report = validate_production_events(events)
    if not report["valid"]:
        raise ValueError("Cannot create evidence for invalid data: " + " ".join(report["errors"]))
    input_payload = json.dumps(_canonical_records(frame), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    metrics_payload = line_metrics.to_json(orient="records", double_precision=15, force_ascii=False)
    scenario_payload = recovery_scenario.to_json(orient="records", double_precision=15, force_ascii=False) if recovery_scenario is not None else "null"
    return {
        "manifest_version": "1.0",
        "formula_version": FORMULA_VERSION,
        "source_name": str(source_name)[:240],
        "source_type": str(source_type)[:80],
        "input_sha256": hashlib.sha256(input_payload.encode("utf-8")).hexdigest(),
        "result_sha256": hashlib.sha256((metrics_payload + "|" + scenario_payload).encode("utf-8")).hexdigest(),
        "row_count": int(len(frame)),
        "line_count": int(frame["Line"].nunique()),
        "result_classification": "Calculated",
        "scenario_classification": "Simulated" if recovery_scenario is not None else None,
        "validation": {"valid": report["valid"], "warnings": report["warnings"]},
        "assumptions": [
            "Each row represents a consistent line and reporting interval.",
            "PlannedMin and DowntimeMin use minutes; IdealCycleSec uses seconds per unit.",
            "TotalCount and GoodCount refer to the same reporting interval and product definition.",
            "A source hash provides integrity evidence, not independent verification of source truth.",
        ],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def analyze_capacity_recovery(
    events: pd.DataFrame,
    *,
    downtime_reduction_fraction: float = 0.25,
    source_name: str = "user-provided production data",
    source_type: str = "unspecified",
) -> dict[str, Any]:
    """Run validation, baseline metrics, scenario estimate, and evidence manifest."""
    normalized, validation = validate_production_events(events)
    if not validation["valid"]:
        return {"validation": validation, "line_metrics": pd.DataFrame(),
                "recovery_scenario": pd.DataFrame(), "evidence": None}
    metrics = calculate_line_metrics(normalized)
    scenario = estimate_downtime_recovery(normalized, downtime_reduction_fraction)
    evidence = build_evidence_manifest(
        normalized, metrics, scenario, source_name=source_name, source_type=source_type,
    )
    return {"validation": validation, "line_metrics": metrics,
            "recovery_scenario": scenario, "evidence": evidence}


def render_capacity_recovery(tier: str = "Starter", username: str = "unknown") -> None:
    """Render the validated study workflow inside the existing Streamlit platform."""
    import io
    import plotly.express as px
    import streamlit as st

    st.subheader("Production Bottleneck & Capacity Recovery Study")
    st.caption(
        "Validate production-event data, calculate line-level OEE, compare a bounded "
        "downtime-recovery scenario, and export a traceable study. Scenarios are estimates, "
        "not promises of factory performance."
    )

    demo = pd.DataFrame({
        "Line": ["Line A", "Line B", "Line C"],
        "PlannedMin": [480, 480, 480],
        "DowntimeMin": [42, 78, 55],
        "IdealCycleSec": [48, 60, 54],
        "TotalCount": [520, 390, 455],
        "GoodCount": [505, 378, 439],
    })
    st.info(
        "The starter table below is synthetic demonstration data, not real factory data. "
        "Upload a CSV or edit the table to analyze your own records."
    )

    uploaded = st.file_uploader(
        "Optional: import production-event CSV",
        type=["csv"],
        key="capacity_recovery_csv_upload",
        help="Required columns: Line, PlannedMin, DowntimeMin, IdealCycleSec, TotalCount, GoodCount.",
    )
    if uploaded is not None:
        try:
            upload_bytes = uploaded.getvalue()
            upload_sha = hashlib.sha256(upload_bytes).hexdigest()
            if st.session_state.get("capacity_recovery_uploaded_sha") != upload_sha:
                imported = pd.read_csv(io.BytesIO(upload_bytes))
                st.session_state["capacity_recovery_events"] = imported
                st.session_state["capacity_recovery_source_name"] = uploaded.name
                st.session_state["capacity_recovery_source_type"] = "imported CSV"
                st.session_state["capacity_recovery_uploaded_sha"] = upload_sha
                st.session_state.pop("capacity_recovery_result", None)
                st.session_state["capacity_recovery_line_metrics"] = pd.DataFrame()
                st.session_state["capacity_recovery_scenario"] = pd.DataFrame()
        except Exception as exc:
            st.error(f"CSV import failed. The existing study data was not replaced. Details: {type(exc).__name__}: {exc}")
    if "capacity_recovery_events" not in st.session_state:
        st.session_state["capacity_recovery_events"] = demo.copy(deep=True)
        st.session_state["capacity_recovery_source_name"] = "synthetic-demo.csv"
        st.session_state["capacity_recovery_source_type"] = "synthetic demonstration data"

    edited = st.data_editor(
        st.session_state["capacity_recovery_events"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="capacity_recovery_events_editor",
    )
    st.session_state["capacity_recovery_events"] = edited.copy(deep=True)

    reduction_pct = st.slider(
        "Scenario: downtime reduction (%)",
        min_value=0,
        max_value=100,
        value=25,
        step=5,
        help="A what-if assumption only. It does not assert that this reduction is achievable.",
        key="capacity_recovery_reduction_pct",
    )
    if st.button("Validate and analyze capacity", type="primary", use_container_width=True,
                 key="capacity_recovery_analyze"):
        result = analyze_capacity_recovery(
            edited,
            downtime_reduction_fraction=reduction_pct / 100.0,
            source_name=st.session_state.get("capacity_recovery_source_name", "user-provided production data"),
            source_type=st.session_state.get("capacity_recovery_source_type", "user-entered data"),
        )
        st.session_state["capacity_recovery_result"] = result
        st.session_state["capacity_recovery_line_metrics"] = result["line_metrics"]
        st.session_state["capacity_recovery_scenario"] = result["recovery_scenario"]

    result = st.session_state.get("capacity_recovery_result")
    if result and result.get("evidence"):
        current_frame, current_validation = validate_production_events(edited)
        inputs_match = False
        if current_validation["valid"]:
            current_evidence = build_evidence_manifest(
                current_frame,
                result["line_metrics"],
                result["recovery_scenario"],
                source_name=st.session_state.get("capacity_recovery_source_name", "user-provided production data"),
                source_type=st.session_state.get("capacity_recovery_source_type", "user-entered data"),
            )
            inputs_match = current_evidence["input_sha256"] == result["evidence"]["input_sha256"]
        if not inputs_match:
            st.session_state.pop("capacity_recovery_result", None)
            st.session_state["capacity_recovery_line_metrics"] = pd.DataFrame()
            st.session_state["capacity_recovery_scenario"] = pd.DataFrame()
            st.info("The input table has changed since the last analysis. Re-run the study to refresh results and evidence.")
            result = None

    if not result:
        validation_frame, validation = validate_production_events(edited)
        st.subheader("Input validation")
        if validation["valid"]:
            st.success(f"Input structure is valid ({validation['rows']} row(s)). Run the analysis to calculate results.")
        else:
            st.error("The study cannot be calculated until the input errors below are corrected.")
            for error in validation["errors"]:
                st.write(f"• {error}")
        for warning in validation["warnings"]:
            st.warning(warning)
        return

    validation = result["validation"]
    if not validation["valid"]:
        st.error("Analysis blocked: invalid input data.")
        for error in validation["errors"]:
            st.write(f"• {error}")
        return

    metrics = result["line_metrics"]
    scenario = result["recovery_scenario"]
    if metrics.empty:
        st.warning("No line metrics are available for the current dataset.")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Lines analyzed", f"{len(metrics):,}")
    m2.metric("Good units observed", f"{metrics['GoodCount'].sum():,.0f}")
    m3.metric("Observed downtime (min)", f"{metrics['DowntimeMin'].sum():,.1f}")

    st.subheader("Baseline: calculated line performance")
    st.dataframe(metrics, use_container_width=True, hide_index=True)
    st.plotly_chart(
        px.bar(metrics, x="Line", y="OEEPct", title="Calculated OEE by line",
               labels={"OEEPct": "OEE (%)", "Line": "Production line"}),
        use_container_width=True,
    )
    if (metrics["OEEPct"] > 100).any():
        st.warning("At least one OEE result exceeds 100%. Check ideal-cycle units and source data; the engine has not silently capped the result.")
    if metrics["OEEPct"].isna().any():
        st.warning("At least one OEE result is unavailable because quality cannot be calculated from zero total output.")

    st.subheader(f"What-if: recover {reduction_pct}% of observed downtime")
    st.caption("Simulated estimates assume observed row-level performance and quality remain unchanged during recovered time.")
    st.dataframe(scenario, use_container_width=True, hide_index=True)
    st.plotly_chart(
        px.bar(scenario, x="Line", y="EstimatedAdditionalGoodUnits",
               title="Estimated additional good units under the scenario",
               labels={"EstimatedAdditionalGoodUnits": "Estimated units", "Line": "Production line"}),
        use_container_width=True,
    )

    evidence = result["evidence"]
    with st.expander("Trust & evidence manifest", expanded=False):
        st.write("Result type: Calculated. Downtime recovery scenario: Simulated.")
        st.write("Input SHA-256:", evidence["input_sha256"])
        st.write("Result SHA-256:", evidence["result_sha256"])
        st.write("Formula version:", evidence["formula_version"])
        st.write("Source:", evidence["source_name"], "—", evidence["source_type"])
        st.write("Assumptions and limits:")
        for assumption in evidence["assumptions"]:
            st.write(f"• {assumption}")
        for warning in evidence["validation"]["warnings"]:
            st.warning(warning)

    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            metrics.to_excel(writer, sheet_name="Baseline Metrics", index=False)
            scenario.to_excel(writer, sheet_name="Recovery Scenario", index=False)
            pd.DataFrame([{
                "Formula version": evidence["formula_version"],
                "Source name": evidence["source_name"],
                "Source type": evidence["source_type"],
                "Input SHA-256": evidence["input_sha256"],
                "Result SHA-256": evidence["result_sha256"],
                "Result classification": evidence["result_classification"],
                "Scenario classification": evidence["scenario_classification"],
                "Created at": evidence["created_at"],
            }]).to_excel(writer, sheet_name="Evidence", index=False)
            pd.DataFrame({"Assumption": evidence["assumptions"]}).to_excel(writer, sheet_name="Assumptions", index=False)
        st.download_button(
            "Download capacity study (Excel)",
            data=buffer.getvalue(),
            file_name="shoir_ie_capacity_recovery_study.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="capacity_recovery_download",
        )
    except Exception as exc:
        st.error(f"Excel export could not be generated. Results remain visible. Details: {type(exc).__name__}: {exc}")
