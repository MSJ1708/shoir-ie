"""Authenticated AppTest smoke checks for the additive 100-tool library.

These tests verify that the routed capability form renders and runs in the actual
Streamlit page with disposable in-memory session state. They do not substitute for
the separate hosted-browser, durable-persistence or production integration gates.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "Engineering_Tool_Library.py"


def _authed_library(tier="Research Pack"):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(PAGE, default_timeout=60)
    at.session_state["authenticated"] = True
    at.session_state["current_user"] = "disposable-tool-library-checker"
    # Research Pack inherits ordinary capabilities through Enterprise, but not
    # Enterprise Plus. This allows testing of all the targets in this tranche.
    at.session_state["user_tier"] = tier
    at.run(timeout=60)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    return at


def _open(at, tool_id, name):
    at.selectbox(key="tool_library_detail").select(f"{tool_id} · {name}")
    at.run(timeout=60)
    assert not at.exception, (
        f"{tool_id} form failed to render:\n"
        + "\n".join(str(error.value) for error in at.exception)
    )


def _run(at, tool_id):
    button = at.button(key=f"{tool_id}_run_button")
    button.click()
    at.run(timeout=60)
    assert not at.exception, (
        f"{tool_id} action failed:\n"
        + "\n".join(str(error.value) for error in at.exception)
    )
    result = at.session_state.get(f"shoir_{tool_id}_result")
    assert result is not None, (
        f"{tool_id} returned no result; visible errors: "
        + " | ".join(str(error.value) for error in at.error)
    )
    return result["result"]


def test_tool_library_public_preview_is_read_only_without_authentication():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(PAGE, default_timeout=60)
    at.run(timeout=60)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert any("Engineering Tool Library" in item.value for item in at.title)
    assert any("PUBLIC READ-ONLY PREVIEW" in item.value for item in at.info)

    # Public visitors can inspect a capability contract, but cannot execute it.
    at.selectbox(key="tool_library_detail").select("T016 · Unit and Currency Converter")
    at.run(timeout=60)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert any("cannot execute calculations" in item.value.lower() for item in at.info)
    assert not any(getattr(button, "key", None) == "T016_run_button" for button in at.button)


def test_public_explore_modules_links_to_the_grouped_library():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("with auth_tab3:")
    section = source[start:start + 30000]
    assert "st.page_link(" in section
    assert '"pages/Engineering_Tool_Library.py"' in section
    assert "Browse the 100-tool Engineering Library" in section
def test_extended_specialist_forms_render_and_run_with_golden_defaults():
    at = _authed_library()

    _open(at, "T016", "Unit and Currency Converter")
    unit_result = _run(at, "T016")
    assert unit_result["converted_value"] == pytest.approx(1.0)

    _open(at, "T022", "Work Sampling Analyzer")
    sample_result = _run(at, "T022")
    assert sample_result["total_observations"] == 100
    assert sample_result["minimum_observations_for_target_margin"] == 385

    _open(at, "T028", "Root-Cause Analysis Toolkit")
    pareto_result = _run(at, "T028")
    assert pareto_result["total_count"] == 100
    assert pareto_result["categories_to_reach_80_percent"] == 2

    _open(at, "T029", "5S and Workplace Audit")
    audit_result = _run(at, "T029")
    assert audit_result["overall_5s_score_pct_equal_pillar_weight"] == pytest.approx(70.0)

    _open(at, "T030", "Kaizen and A3 Improvement Manager")
    a3_result = _run(at, "T030")
    assert a3_result["target_progress_pct"] == pytest.approx(50.0)
    assert a3_result["outcome_status"] != "VERIFIED_SAVINGS"

    _open(at, "T031", "Statistical Process Control")
    spc_result = _run(at, "T031")
    assert spc_result["mean"] == pytest.approx(10.5)

    _open(at, "T040", "Quality Cost and Defect Analyzer")
    copq_result = _run(at, "T040")
    assert copq_result["cost_of_poor_quality"] == pytest.approx(190.0)

    _open(at, "T042", "MTBF and MTTR Analyzer")
    reliability_result = _run(at, "T042")
    assert reliability_result["mtbf_hours"] == pytest.approx(200.0)
    assert reliability_result["mttr_hours"] == pytest.approx(2.0)

    _open(at, "T056", "ABC/XYZ Inventory Analyzer")
    inventory_result = _run(at, "T056")
    assert inventory_result["annual_usage_value_total"] == pytest.approx(1000.0)

    _open(at, "T075", "Forecast and Model Drift Monitor")
    drift_result = _run(at, "T075")
    assert drift_result["status"] == "DRIFT_ALERT"
    assert drift_result["mae"] == pytest.approx(7 / 3)

    _open(at, "T085", "Statistical Power and Sample-Size Planner")
    power_result = _run(at, "T085")
    assert power_result["required_n_per_group"] == 64
    assert power_result["total_sample_size"] == 128


def test_cutting_stock_solver_is_exposed_in_the_existing_facilities_tool():
    at = _authed_library()
    _open(at, "T066", "Cutting Stock and Bin Packing")
    # This is a separate solver action under the existing target, not a new top-level
    # module. A solver exception must remain visible and must not erase prior state.
    button = at.button(key="T066_CUT_run_button")
    button.click()
    at.run(timeout=60)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_T066_CUT_result")
    assert result is not None, "Cutting-stock action did not return a structured result."
    assert result["result"]["status"] == "OPTIMAL"
    assert result["result"]["stock_count"] == 2

def test_lower_tier_cannot_render_or_execute_research_only_tool():
    from streamlit.testing.v1 import AppTest

    at = _authed_library(tier="Starter")
    _open(at, "T085", "Statistical Power and Sample-Size Planner")
    assert any(
        "does not grant this target capability" in str(item.value).lower()
        for item in at.warning
    )
    assert "shoir_T085_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T085_run_button")



def test_new_data_tools_render_and_run_in_validation_mode():
    at = _authed_library()

    _open(at, "T013", "Data Quality Profiler")
    profile = _run(at, "T013")
    assert profile["status"] == "PROFILED"
    assert profile["metrics"]["row_count"] == 5
    assert profile["metrics"]["missing_cell_count"] == 1

    _open(at, "T017", "Data Join and Merge Studio")
    joined = _run(at, "T017")
    assert joined["status"] == "PREVIEWED"
    assert joined["metrics"]["output_rows"] == 3
    assert joined["metrics"]["unmatched_right_input_rows"] == 1

    _open(at, "T018", "Time-Series Data Processor")
    processed = _run(at, "T018")
    assert processed["status"] == "PROCESSED"
    assert processed["metrics"]["duplicate_timestamp_rows"] == 2
    assert processed["metrics"]["missing_intervals"] == 1

    _open(at, "T019", "Synthetic Industrial Data Generator")
    synthetic = _run(at, "T019")
    assert synthetic["status"] == "GENERATED_SYNTHETIC"
    assert synthetic["source"] == "SYNTHETIC"
    assert len(synthetic["dataset"]) == 100
    assert set(synthetic["dataset"]["data_status"]) == {"SYNTHETIC"}


def test_lower_tier_cannot_run_mid_tier_join_preview():
    from streamlit.testing.v1 import AppTest

    at = _authed_library(tier="Starter")
    _open(at, "T017", "Data Join and Merge Studio")
    assert any("does not grant this target capability" in str(item.value).lower() for item in at.warning)
    assert "shoir_T017_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T017_run_button")


def test_manufacturing_operations_tools_render_and_run_with_golden_defaults():
    at = _authed_library()

    _open(at, "T024", "Production Line Balancer")
    line_result = _run(at, "T024")
    assert line_result["status"] == "FEASIBLE_HEURISTIC"
    assert line_result["metrics"]["total_work_content"] == pytest.approx(12.0)
    assert line_result["metrics"]["station_count"] == 3
    assert line_result["metrics"]["line_efficiency_percent"] == pytest.approx(12 / 18 * 100)

    _open(at, "T025", "Bottleneck and Constraint Analyzer")
    bottleneck = _run(at, "T025")
    assert bottleneck["metrics"]["candidate_stage"] == "Welding"
    assert bottleneck["metrics"]["evidence_label"] == "INFERRED_FROM_CYCLE_TIME"

    _open(at, "T027", "Value Stream Mapping Studio")
    vsm = _run(at, "T027")
    assert vsm["metrics"]["value_added_time"] == pytest.approx(8.0)
    assert vsm["metrics"]["explicit_lead_time"] == pytest.approx(53.0)
    assert vsm["metrics"]["process_cycle_efficiency_percent"] == pytest.approx(8 / 53 * 100)

    _open(at, "T070", "Queuing and Service-System Analyzer")
    queue = _run(at, "T070")
    assert queue["metrics"]["utilization_percent"] == pytest.approx(100 * 2 / 3)
    assert queue["metrics"]["mean_time_in_system"] == pytest.approx(1.0)
    assert queue["metrics"]["mean_queue_wait"] == pytest.approx(2 / 3)


def test_starter_cannot_render_or_execute_mid_tier_line_balancer():
    at = _authed_library(tier="Starter")
    _open(at, "T024", "Production Line Balancer")
    assert any("does not grant this target capability" in str(item.value).lower() for item in at.warning)
    assert "shoir_T024_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T024_run_button")


def test_quality_planning_and_risk_tools_render_and_run_with_golden_defaults():
    at = _authed_library()

    _open(at, "T034", "Acceptance Sampling Planner")
    sampling = _run(at, "T034")
    assert sampling["status"] == "CALCULATED"
    assert 0 <= sampling["metrics"]["producer_risk_at_aql"] <= 1
    assert 0 <= sampling["metrics"]["consumer_risk_at_ltpd"] <= 1
    assert len(sampling["operating_characteristic"]) == 21

    _open(at, "T051", "Demand Forecasting Studio")
    forecast = _run(at, "T051")
    assert forecast["status"] == "FORECASTED"
    assert forecast["metrics"]["selected_model_by_holdout_mae"] == "naive_last_value"
    assert len(forecast["backtest"]) == 2
    assert len(forecast["forecast"]) == 2

    _open(at, "T054", "Material Requirements Planner")
    mrp = _run(at, "T054")
    assert mrp["status"] == "PLANNED"
    assert mrp["metrics"]["planned_order_count"] == 8
    assert {row["item"] for row in mrp["planned_releases"]} == {"PRODUCT", "COMP_A", "COMP_B", "RAW_X"}

    _open(at, "T072", "Monte Carlo Risk Simulator")
    simulation = _run(at, "T072")
    assert simulation["status"] == "SIMULATED"
    assert simulation["metrics"]["iterations"] == 5000
    assert simulation["metrics"]["p05"] <= simulation["metrics"]["p50"] <= simulation["metrics"]["p95"]
    assert sum(row["count"] for row in simulation["histogram"]) == 5000


def test_starter_cannot_execute_acceptance_sampling_planner():
    at = _authed_library(tier="Starter")
    _open(at, "T034", "Acceptance Sampling Planner")
    assert any("does not grant this target capability" in str(item.value).lower() for item in at.warning)
    assert "shoir_T034_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T034_run_button")


def test_ols_regression_tool_renders_runs_and_reports_golden_metrics():
    at = _authed_library(tier="Professional")
    _open(at, "T036", "Regression and ANOVA Studio")
    result = _run(at, "T036")
    metrics = result["metrics"]
    coefficients = result["coefficient_table"].set_index("Term")["Coefficient"]
    assert coefficients["Intercept"] == pytest.approx(1.0)
    assert coefficients["Load"] == pytest.approx(2.0)
    assert metrics["R_squared"] == pytest.approx(1.0)
    assert len(result["prediction_residuals"]) == 6


def test_research_hypothesis_testing_tool_runs_in_research_pack():
    at = _authed_library(tier="Research Pack")
    _open(at, "T037", "Hypothesis Testing Assistant")
    result = _run(at, "T037")
    assert result["status"] == "CALCULATED"
    assert result["metrics"]["test_type"] == "one_sample"
    assert result["metrics"]["n_sample_a"] == 6
    assert 0 <= result["metrics"]["p_value"] <= 1
    assert result["metrics"]["confidence_interval_lower"] < result["metrics"]["confidence_interval_upper"]


def test_starter_cannot_render_or_execute_research_hypothesis_testing():
    at = _authed_library(tier="Starter")
    _open(at, "T037", "Hypothesis Testing Assistant")
    assert any("does not grant this target capability" in str(item.value).lower() for item in at.warning)
    assert "shoir_T037_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T037_run_button")


def test_quality_asset_supplier_and_sustainability_tools_run_in_validation_mode():
    at = _authed_library(tier="Research Pack")

    _open(at, "T038", "FMEA Manager")
    fmea = _run(at, "T038")
    assert fmea["metrics"]["failure_mode_count"] == 2
    assert fmea["metrics"]["maximum_rpn"] == 96
    assert len(fmea["revision_history"]) == 0

    _open(at, "T039", "CAPA and 8D Manager")
    capa = _run(at, "T039")
    assert capa["metrics"]["closure_ready"] is False
    assert capa["record"]["evidence_state"] == "USER_ENTERED_UNVERIFIED"
    assert capa["record"]["revision"] == 1
    assert len(at.session_state["shoir_capa_8d_register"]) == 1

    _open(at, "T043", "Preventive Maintenance Planner")
    maintenance = _run(at, "T043")
    assert maintenance["metrics"]["overdue_tasks"] == 1
    assert maintenance["metrics"]["due_within_30_days"] == 1

    _open(at, "T045", "Spare Parts and Criticality Planner")
    spares = _run(at, "T045")
    assert spares["metrics"]["parts_count"] == 2
    assert spares["metrics"]["parts_below_reorder_point"] >= 1

    _open(at, "T058", "Supplier Performance and Risk Scorecard")
    suppliers = _run(at, "T058")
    supplier_rows = suppliers["scorecard"].set_index("supplier")
    assert supplier_rows.loc["Supplier A", "weighted_score_on_available_evidence"] == pytest.approx(84)
    assert supplier_rows.loc["Supplier B", "evidence_coverage_percent"] == pytest.approx(80)

    _open(at, "T077", "Energy Performance Optimizer")
    energy = _run(at, "T077")
    assert energy["metrics"]["baseline_kwh_per_unit"] == pytest.approx(10)
    assert energy["metrics"]["estimated_energy_difference_kwh"] == pytest.approx(210)

    _open(at, "T079", "Water and Waste Efficiency Analyzer")
    resources = _run(at, "T079")
    assert resources["metrics"]["total_water_input_m3"] == pytest.approx(104)
    assert resources["metrics"]["total_recycling_rate_percent"] == pytest.approx(17 / 44 * 100)

    _open(at, "T083", "Evidence-Based ROI Tracker")
    roi = _run(at, "T083")
    assert roi["metrics"]["net_benefit_after_implementation_cost"] == pytest.approx(2000)
    assert roi["metrics"]["verified_savings"] is False
    assert roi["metrics"]["evidence_state"] == "ESTIMATE_ONLY"


def test_starter_cannot_render_or_execute_professional_spare_parts_planner():
    at = _authed_library(tier="Starter")
    _open(at, "T045", "Spare Parts and Criticality Planner")
    assert any("does not grant this target capability" in str(item.value).lower() for item in at.warning)
    assert "shoir_T045_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T045_run_button")


def test_hazard_sop_assignment_scenario_portfolio_evidence_and_kpi_tools_run():
    at = _authed_library(tier="Research Pack")

    _open(at, "T047", "Job Safety and Hazard Register")
    hazards = _run(at, "T047")
    assert hazards["metrics"]["hazard_count"] == 2
    assert hazards["metrics"]["maximum_residual_score"] == 12

    _open(at, "T052", "Sales and Operations Planning")
    sop = _run(at, "T052")
    assert sop["metrics"]["capacity_exceeded_periods"] == 1
    assert sop["metrics"]["ending_backlog_units"] == pytest.approx(0)
    assert sop["metrics"]["ending_inventory_units"] == pytest.approx(0)

    _open(at, "T063", "Assignment and Scheduling Optimizer")
    assignment = _run(at, "T063")
    assert assignment["metrics"]["total_assignment_cost"] == pytest.approx(6)
    assert assignment["metrics"]["assignment_complete"] is True

    _open(at, "T073", "What-If Scenario Manager")
    scenarios = _run(at, "T073")
    assert scenarios["metrics"]["baseline_capacity_units"] == pytest.approx(99.75)
    assert scenarios["metrics"]["scenarios_meeting_entered_demand"] == 2

    _open(at, "T084", "Engineering Project Portfolio Scorer")
    portfolio = _run(at, "T084")
    assert portfolio["metrics"]["top_ranked_project_id"] == "PR-02"
    assert portfolio["metrics"]["top_weighted_score"] == pytest.approx(85)

    _open(at, "T086", "Hypothesis and Evidence Register")
    evidence = _run(at, "T086")
    assert evidence["metrics"]["evidence_record_count"] == 1
    assert evidence["metrics"]["independently_verified_count"] == 0

    _open(at, "T094", "KPI Dashboard and Alert Center")
    kpis = _run(at, "T094")
    assert kpis["metrics"]["alert_count"] == 2
    assert kpis["metrics"]["stale_metric_count"] == 1
    assert kpis["metrics"]["alert_and_stale_count"] == 1


def test_starter_cannot_execute_enterprise_kpi_alert_center():
    at = _authed_library(tier="Starter")
    _open(at, "T094", "KPI Dashboard and Alert Center")
    assert any("does not grant this target capability" in str(item.value).lower() for item in at.warning)
    assert "shoir_T094_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T094_run_button")


def test_field_mapper_and_safety_incident_trends_run_in_streamlit():
    at = _authed_library(tier="Starter")
    _open(at, "T015", "Industrial Field Mapper")
    mapped = _run(at, "T015")
    table = mapped["mapping_table"].set_index("source_column")
    assert table.loc["Asset ID", "canonical_field"] == "asset_id"
    assert table.loc["Produced Units", "canonical_field"] == "units_produced"
    assert table.loc["custom_field", "mapping_status"] == "UNMAPPED"

    # Safety trend analysis belongs to Mid-Tier Pro and above, not Starter.
    restricted = _authed_library(tier="Mid-Tier Pro")
    _open(restricted, "T050", "Safety Incident Trend Analyzer")
    incidents = _run(restricted, "T050")
    assert incidents["metrics"]["incident_count"] == 4
    assert incidents["metrics"]["exposure_hours"] == pytest.approx(22000)
    assert incidents["metrics"]["overall_incident_rate"] == pytest.approx(4 / 22000 * 200000)
    assert incidents["metrics"]["incident_categories"] == 2


def test_starter_is_denied_safety_incident_trend_action():
    at = _authed_library(tier="Starter")
    _open(at, "T050", "Safety Incident Trend Analyzer")
    assert any("does not grant this target capability" in str(item.value).lower() for item in at.warning)
    assert "shoir_T050_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T050_run_button")
