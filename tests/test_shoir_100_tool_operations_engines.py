"""Golden and boundary tests for bounded manufacturing and queueing methods."""
from __future__ import annotations

import pytest

from shoir_100_tool_operations_engines import (
    analyze_bottleneck,
    analyze_mm1_queue,
    balance_production_line,
    build_value_stream_metrics,
)


def _line_fixture():
    return [
        {"name": "A", "duration": 3, "predecessors": []},
        {"name": "B", "duration": 2, "predecessors": ["A"]},
        {"name": "C", "duration": 4, "predecessors": ["A"]},
        {"name": "D", "duration": 2, "predecessors": ["B", "C"]},
        {"name": "E", "duration": 1, "predecessors": ["D"]},
    ]


def test_line_balancer_matches_hand_calculated_precedence_fixture():
    result = balance_production_line(_line_fixture(), cycle_time=6)
    assert result["status"] == "FEASIBLE_HEURISTIC"
    metrics = result["metrics"]
    assert metrics["task_count"] == 5
    assert metrics["total_work_content"] == pytest.approx(12)
    assert metrics["theoretical_minimum_stations"] == 2
    assert metrics["station_count"] == 3
    assert metrics["line_efficiency_percent"] == pytest.approx(12 / 18 * 100)
    assert metrics["balance_delay_percent"] == pytest.approx(100 - 12 / 18 * 100)
    assert metrics["precedence_respected"] is True
    assignment = result["assignment"]
    by_name = {row["task"]: row for row in assignment}
    for row in assignment:
        for predecessor in row["predecessors"]:
            assert by_name[predecessor]["station"] <= row["station"]
            if by_name[predecessor]["station"] == row["station"]:
                assert by_name[predecessor]["sequence"] < row["sequence"]
    assert sum(row["load"] for row in result["station_summary"]) == pytest.approx(12)
    assert all(row["load"] <= 6 for row in result["station_summary"])


def test_line_balancer_rejects_cycles_unknown_predecessors_and_oversize_tasks():
    with pytest.raises(ValueError, match="cycle"):
        balance_production_line([
            {"name": "A", "duration": 1, "predecessors": ["B"]},
            {"name": "B", "duration": 1, "predecessors": ["A"]},
        ], cycle_time=4)
    with pytest.raises(ValueError, match="unknown predecessor"):
        balance_production_line([{"name": "A", "duration": 1, "predecessors": ["Z"]}], cycle_time=4)
    with pytest.raises(ValueError, match="exceeds the cycle time"):
        balance_production_line([{"name": "A", "duration": 5, "predecessors": []}], cycle_time=4)


def test_line_balancer_does_not_call_heuristic_overrun_proven_infeasibility():
    result = balance_production_line(_line_fixture(), cycle_time=6, max_stations=2)
    assert result["status"] == "FEASIBLE_HEURISTIC_STATION_LIMIT_EXCEEDED"
    assert result["metrics"]["station_limit_satisfied"] is False
    assert "not proof" in result["warnings"][0]


def test_bottleneck_cycle_time_labels_inference_and_identifies_longest_stage():
    result = analyze_bottleneck([
        {"name": "Cutting", "cycle_time": 2},
        {"name": "Welding", "cycle_time": 4},
        {"name": "Inspection", "cycle_time": 1.5},
    ], basis="cycle_time")
    assert result["status"] == "INFERRED_CONSTRAINT_REVIEW_REQUIRED"
    assert result["metrics"]["candidate_stage"] == "Welding"
    assert result["metrics"]["candidate_value"] == pytest.approx(4)
    assert result["metrics"]["evidence_label"] == "INFERRED_FROM_CYCLE_TIME"
    assert any("validate" in warning for warning in result["warnings"])


def test_bottleneck_throughput_labels_observed_signal_not_causality():
    result = analyze_bottleneck([
        {"name": "Cutting", "measured_throughput": 28},
        {"name": "Welding", "measured_throughput": 22},
        {"name": "Inspection", "measured_throughput": 25},
    ], basis="measured_throughput")
    assert result["metrics"]["candidate_stage"] == "Welding"
    assert result["metrics"]["candidate_value"] == pytest.approx(22)
    assert result["metrics"]["evidence_label"] == "OBSERVED_LOW_THROUGHPUT_REVIEW_REQUIRED"


def test_bottleneck_rejects_missing_or_single_stage_inputs():
    with pytest.raises(ValueError, match="at least two"):
        analyze_bottleneck([{"name": "A", "cycle_time": 2}], basis="cycle_time")
    with pytest.raises(ValueError, match="numeric"):
        analyze_bottleneck([
            {"name": "A", "cycle_time": 2}, {"name": "B", "cycle_time": None},
        ], basis="cycle_time")


def test_value_stream_map_metrics_match_hand_calculated_fixture():
    result = build_value_stream_metrics([
        {"name": "Cutting", "cycle_time": 2, "wait_time": 10, "wip": 4},
        {"name": "Welding", "cycle_time": 5, "wait_time": 30, "wip": 12},
        {"name": "Inspection", "cycle_time": 1, "wait_time": 5, "wip": 3},
    ])
    metrics = result["metrics"]
    assert metrics["value_added_time"] == pytest.approx(8)
    assert metrics["waiting_time"] == pytest.approx(45)
    assert metrics["explicit_lead_time"] == pytest.approx(53)
    assert metrics["process_cycle_efficiency_percent"] == pytest.approx(8 / 53 * 100)
    assert metrics["total_wip"] == pytest.approx(19)
    assert metrics["longest_cycle_process"] == "Welding"


def test_value_stream_rejects_negative_wait_or_wip_and_nonpositive_cycle():
    with pytest.raises(ValueError, match="cannot be negative"):
        build_value_stream_metrics([{"name": "A", "cycle_time": 1, "wait_time": -1}])
    with pytest.raises(ValueError, match="cannot be negative"):
        build_value_stream_metrics([{"name": "A", "cycle_time": 1, "wait_time": 0, "wip": -1}])


def test_mm1_queue_matches_known_stable_analytic_case():
    result = analyze_mm1_queue(arrival_rate=2, service_rate=3)
    m = result["metrics"]
    assert m["utilization_fraction"] == pytest.approx(2 / 3)
    assert m["mean_time_in_system"] == pytest.approx(1)
    assert m["mean_queue_wait"] == pytest.approx(2 / 3)
    assert m["mean_number_in_system"] == pytest.approx(2)
    assert m["mean_number_in_queue"] == pytest.approx(4 / 3)
    assert m["mean_service_time"] == pytest.approx(1 / 3)
    assert m["mean_interarrival_time"] == pytest.approx(1 / 2)


def test_mm1_queue_rejects_unstable_or_invalid_rates():
    with pytest.raises(ValueError, match="unstable"):
        analyze_mm1_queue(arrival_rate=3, service_rate=3)
    with pytest.raises(ValueError, match="unstable"):
        analyze_mm1_queue(arrival_rate=4, service_rate=3)
    with pytest.raises(ValueError, match="greater than zero"):
        analyze_mm1_queue(arrival_rate=0, service_rate=3)


def test_methods_do_not_mutate_input_records():
    tasks = _line_fixture()
    original = [dict(row) for row in tasks]
    balance_production_line(tasks, cycle_time=6)
    assert tasks == original
