"""Focused deterministic operations methods for the Shoir-IE 100-tool library."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def _finite(value: Any, label: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    if positive and number <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    if nonnegative and number < 0:
        raise ValueError(f"{label} cannot be negative.")
    return number


def _sequence(value: Any, label: str) -> Sequence:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError(f"Provide at least one {label}.")
    return value


def _name(row: Mapping[str, Any], label: str) -> str:
    value = str(row.get("name", row.get("stage", row.get("task", ""))) or "").strip()
    if not value:
        raise ValueError(f"{label} needs a non-empty name.")
    return value


def _predecessors(value: Any) -> list[str]:
    if value is None or (isinstance(value, str) and value == ""):
        return []
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, str)):
        items = list(value)
    else:
        raise ValueError("Predecessors must be a list or comma-separated text.")
    result = []
    for item in items:
        item = str(item).strip()
        if item and item not in result:
            result.append(item)
    return result


def balance_production_line(
    tasks: Sequence[Mapping[str, Any]],
    cycle_time: float,
    *,
    max_stations: int | None = None,
) -> dict[str, Any]:
    """Assign precedence-constrained tasks using a Largest Eligible Task heuristic.

    The assignment is a feasible deterministic heuristic, not a proof of a globally
    minimum station count. Exceeding an optional station limit does not prove
    mathematical infeasibility for that limit.
    """
    records = _sequence(tasks, "task")
    cycle = _finite(cycle_time, "Cycle time", positive=True)
    if max_stations is not None and (
        isinstance(max_stations, bool) or not isinstance(max_stations, int) or max_stations < 1
    ):
        raise ValueError("max_stations must be a positive whole number when supplied.")

    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Task row {index} must be an object.")
        name = _name(raw, f"Task row {index}")
        if name in names:
            raise ValueError(f"Task names must be unique. Duplicate: {name}.")
        names.add(name)
        duration = _finite(raw.get("duration"), f"Duration for {name}", positive=True)
        if duration > cycle + 1e-12:
            raise ValueError(f"Task {name} duration exceeds the cycle time and cannot fit in any station.")
        preds = _predecessors(raw.get("predecessors", []))
        if name in preds:
            raise ValueError(f"Task {name} cannot be its own predecessor.")
        normalized.append({"name": name, "duration": duration, "predecessors": preds, "input_index": index - 1})

    by_name = {row["name"]: row for row in normalized}
    for row in normalized:
        missing = [pred for pred in row["predecessors"] if pred not in by_name]
        if missing:
            raise ValueError(f"Task {row['name']} references unknown predecessor(s): {', '.join(missing)}.")

    dependencies = {row["name"]: set(row["predecessors"]) for row in normalized}
    unsorted = set(by_name)
    topo_done: set[str] = set()
    while unsorted:
        ready = [n for n in by_name if n in unsorted and dependencies[n].issubset(topo_done)]
        if not ready:
            raise ValueError("The precedence network contains a cycle; no valid line balance exists.")
        for name in ready:
            topo_done.add(name)
            unsorted.remove(name)

    remaining = set(by_name)
    assigned_order: list[str] = []
    station_summary: list[dict[str, Any]] = []
    assigned_station: dict[str, int] = {}
    while remaining:
        station_number = len(station_summary) + 1
        station_tasks: list[str] = []
        station_load = 0.0
        while True:
            assigned = set(assigned_order)
            eligible = [
                n for n in by_name
                if n in remaining and dependencies[n].issubset(assigned)
            ]
            fitting = [
                n for n in eligible
                if by_name[n]["duration"] <= cycle - station_load + 1e-12
            ]
            if not fitting:
                break
            chosen = min(fitting, key=lambda n: (-by_name[n]["duration"], by_name[n]["input_index"]))
            station_tasks.append(chosen)
            station_load += by_name[chosen]["duration"]
            assigned_order.append(chosen)
            assigned_station[chosen] = station_number
            remaining.remove(chosen)
        if not station_tasks:
            raise RuntimeError("The scheduling heuristic could not place an eligible task.")
        station_summary.append({
            "station": station_number,
            "tasks": station_tasks,
            "load": round(station_load, 10),
            "idle_time": round(max(0.0, cycle - station_load), 10),
            "utilization_percent": round(100.0 * station_load / cycle, 6),
        })

    total_work = sum(row["duration"] for row in normalized)
    station_count = len(station_summary)
    efficiency = 100.0 * total_work / (station_count * cycle)
    limit_satisfied = max_stations is None or station_count <= max_stations
    status = "FEASIBLE_HEURISTIC" if limit_satisfied else "FEASIBLE_HEURISTIC_STATION_LIMIT_EXCEEDED"
    assignment = [
        {"task": name, "duration": by_name[name]["duration"],
         "predecessors": list(by_name[name]["predecessors"]),
         "station": assigned_station[name], "sequence": index + 1}
        for index, name in enumerate(assigned_order)
    ]
    return {
        "status": status,
        "method": "Largest Eligible Task (LET) precedence-constrained heuristic",
        "metrics": {
            "task_count": len(normalized), "cycle_time": cycle,
            "total_work_content": round(total_work, 10),
            "station_count": station_count,
            "theoretical_minimum_stations": math.ceil(total_work / cycle),
            "line_efficiency_percent": round(efficiency, 6),
            "balance_delay_percent": round(100.0 - efficiency, 6),
            "station_limit": max_stations,
            "station_limit_satisfied": limit_satisfied, "precedence_respected": True,
        },
        "station_summary": station_summary, "assignment": assignment,
        "formulas": {
            "theoretical_minimum_stations": "ceil(total task work content / cycle time)",
            "line_efficiency_percent": "100 × total work content / (actual stations × cycle time)",
            "balance_delay_percent": "100 − line efficiency",
        },
        "assumptions": [
            "All task durations use the same time unit and target cycle time.",
            "Precedence requires every predecessor to occur earlier in the sequence; no plant-specific zoning constraints are modeled.",
            "This deterministic heuristic is not a proof of global optimality.",
        ],
        "warnings": [] if limit_satisfied else [
            "The feasible heuristic assignment exceeds the requested station limit. This is not proof that no assignment with that limit exists."
        ],
    }


def analyze_bottleneck(stages: Sequence[Mapping[str, Any]], *, basis: str = "cycle_time") -> dict[str, Any]:
    """Screen constraints using one comparable basis; do not infer causation from a low output alone."""
    records = _sequence(stages, "stage")
    if len(records) < 2:
        raise ValueError("Provide at least two stages for a useful bottleneck comparison.")
    if basis not in {"cycle_time", "measured_throughput"}:
        raise ValueError("basis must be 'cycle_time' or 'measured_throughput'.")
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    key = "cycle_time" if basis == "cycle_time" else "measured_throughput"
    label = "cycle time" if basis == "cycle_time" else "measured throughput"
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Stage row {index} must be an object.")
        name = _name(raw, f"Stage row {index}")
        if name in names:
            raise ValueError(f"Stage names must be unique. Duplicate: {name}.")
        names.add(name)
        normalized.append({"stage": name, "metric_value": _finite(raw.get(key), f"{label.title()} for {name}", positive=True)})
    if basis == "cycle_time":
        value = max(row["metric_value"] for row in normalized)
        candidates = [row["stage"] for row in normalized if math.isclose(row["metric_value"], value, rel_tol=1e-9, abs_tol=1e-12)]
        evidence, status = "INFERRED_FROM_CYCLE_TIME", "INFERRED_CONSTRAINT_REVIEW_REQUIRED"
        warning = "This nominates the largest supplied cycle time; validate buffers, downtime, variability and demand before deciding it is the system constraint."
        metric_name = "cycle time (larger is more limiting)"
    else:
        value = min(row["metric_value"] for row in normalized)
        candidates = [row["stage"] for row in normalized if math.isclose(row["metric_value"], value, rel_tol=1e-9, abs_tol=1e-12)]
        evidence, status = "OBSERVED_LOW_THROUGHPUT_REVIEW_REQUIRED", "OBSERVED_LOW_THROUGHPUT_REVIEW_REQUIRED"
        warning = "Low observed throughput is a signal for investigation, not proof that the stage caused the line constraint."
        metric_name = "measured throughput (smaller is more limiting)"
    candidate_set = set(candidates)
    return {
        "status": status, "method": "Consistent-basis stage constraint screening",
        "metrics": {"basis": basis, "candidate_stages": candidates, "candidate_stage": candidates[0],
                    "candidate_value": value, "metric_name": metric_name, "evidence_label": evidence,
                    "stage_count": len(normalized)},
        "stage_summary": [{**row, "candidate_constraint": row["stage"] in candidate_set} for row in normalized],
        "formulas": {"cycle_time_basis": "candidate = arg max(stage cycle time)",
                     "measured_throughput_basis": "candidate = arg min(measured stage throughput)"},
        "assumptions": ["All stages use the same measurement unit and observation window within the selected basis.",
                        "Cycle-time screening is inference; throughput screening identifies an observed low-output signal only."],
        "warnings": [warning],
    }


def build_value_stream_metrics(processes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate explicitly entered process cycle/wait times and WIP; not a full VSM editor."""
    records = _sequence(processes, "process")
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Process row {index} must be an object.")
        name = _name(raw, f"Process row {index}")
        if name in names:
            raise ValueError(f"Process names must be unique. Duplicate: {name}.")
        names.add(name)
        normalized.append({
            "process": name,
            "cycle_time": _finite(raw.get("cycle_time"), f"Cycle time for {name}", positive=True),
            "wait_time": _finite(raw.get("wait_time"), f"Wait time for {name}", nonnegative=True),
            "wip": _finite(raw.get("wip", 0), f"WIP for {name}", nonnegative=True),
        })
    value_added = sum(row["cycle_time"] for row in normalized)
    waiting = sum(row["wait_time"] for row in normalized)
    lead_time = value_added + waiting
    longest = max(normalized, key=lambda row: row["cycle_time"])
    return {
        "status": "CALCULATED", "method": "Explicit process cycle-time and waiting-time aggregation",
        "metrics": {
            "process_count": len(normalized), "value_added_time": round(value_added, 10),
            "waiting_time": round(waiting, 10), "explicit_lead_time": round(lead_time, 10),
            "process_cycle_efficiency_percent": round(100.0 * value_added / lead_time, 6) if lead_time else 0.0,
            "total_wip": round(sum(row["wip"] for row in normalized), 10),
            "longest_cycle_process": longest["process"], "longest_cycle_time": longest["cycle_time"],
        },
        "process_summary": [{**row, "lead_time_contribution": row["cycle_time"] + row["wait_time"]} for row in normalized],
        "formulas": {
            "value_added_time": "sum(process cycle times)",
            "explicit_lead_time": "sum(process cycle times + explicitly entered waiting times)",
            "process_cycle_efficiency_percent": "100 × value-added time / explicit lead time",
            "total_wip": "sum of entered WIP values",
        },
        "assumptions": ["Cycle and waiting times share a time unit; WIP values share a compatible quantity definition.",
                        "Wait time is entered by the analyst and is not inferred from WIP or demand.",
                        "This is a simple editable VSM timing basis, not a full material/information-flow map."],
        "warnings": ["Validate time windows, demand, WIP definitions and process boundaries before operational decisions."],
    }


def analyze_mm1_queue(arrival_rate: float, service_rate: float) -> dict[str, Any]:
    """Calculate steady-state M/M/1 metrics under a one-server stable-queue assumption."""
    arrival = _finite(arrival_rate, "Arrival rate", positive=True)
    service = _finite(service_rate, "Service rate", positive=True)
    if arrival >= service:
        raise ValueError("The M/M/1 queue is unstable for steady-state analysis: arrival rate must be below service rate.")
    utilization = arrival / service
    system_time = 1.0 / (service - arrival)
    queue_wait = arrival / (service * (service - arrival))
    system_count, queue_count = arrival * system_time, arrival * queue_wait
    return {
        "status": "CALCULATED", "method": "M/M/1 steady-state analytical queue model",
        "metrics": {
            "arrival_rate": arrival, "service_rate": service,
            "utilization_fraction": utilization, "utilization_percent": 100.0 * utilization,
            "mean_time_in_system": system_time, "mean_queue_wait": queue_wait,
            "mean_service_time": 1.0 / service, "mean_interarrival_time": 1.0 / arrival,
            "mean_number_in_system": system_count, "mean_number_in_queue": queue_count,
        },
        "formulas": {
            "utilization": "rho = arrival_rate / service_rate",
            "mean_time_in_system": "W = 1 / (service_rate − arrival_rate)",
            "mean_queue_wait": "Wq = arrival_rate / (service_rate × (service_rate − arrival_rate))",
            "mean_number_in_system": "L = arrival_rate × W",
            "mean_number_in_queue": "Lq = arrival_rate × Wq",
        },
        "assumptions": ["Poisson arrivals, exponential service, one server, first-come/first-served, stationary stable steady state.",
                        "Arrival and service rates use the same time-rate unit; output times are in its reciprocal."],
        "warnings": ["Do not apply M/M/1 when arrival rate is at least the service rate or assumptions are not defensible."],
    }
