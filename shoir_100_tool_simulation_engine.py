"""Event-based serial flow-line simulation with queues and replications (T071)."""
from __future__ import annotations

import heapq
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import t as student_t


def simulate_serial_flow_line(
    stations: pd.DataFrame,
    *,
    entity_count: int = 200,
    mean_interarrival_minutes: float = 5.0,
    arrival_pattern: str = "fixed",
    warmup_entities: int = 20,
    replications: int = 5,
    random_seed: int = 12345,
) -> dict[str, Any]:
    """Simulate jobs arriving to a fixed, serial route with FIFO queues and pooled station servers."""
    if not isinstance(stations, pd.DataFrame) or stations.empty:
        raise ValueError("Simulation requires at least one station.")
    if stations.columns.has_duplicates:
        raise ValueError("Station table must have unique column names.")
    required = {"sequence", "station_id", "servers", "mean_service_minutes", "service_time_cv"}
    missing = sorted(required - set(stations.columns))
    if missing:
        raise ValueError("Station table is missing columns: " + ", ".join(missing))
    try:
        n_entities = int(entity_count)
        n_warmup = int(warmup_entities)
        n_reps = int(replications)
        seed = int(random_seed)
    except (TypeError, ValueError) as exc:
        raise ValueError("Entity count, warm-up count, replications and seed must be integers.") from exc
    if n_entities < 10 or n_entities > 5000:
        raise ValueError("Entity count must be from 10 to 5000.")
    if n_warmup < 0 or n_warmup >= n_entities - 1:
        raise ValueError("Warm-up entities must be at least 0 and leave at least two measured entities.")
    if n_reps < 1 or n_reps > 20:
        raise ValueError("Replications must be from 1 to 20.")
    if seed < 0 or seed > 2**32 - 1:
        raise ValueError("Random seed must be from 0 to 4294967295.")
    try:
        interarrival = float(mean_interarrival_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mean interarrival minutes must be numeric.") from exc
    if not math.isfinite(interarrival) or interarrival <= 0:
        raise ValueError("Mean interarrival minutes must be finite and positive.")
    pattern = str(arrival_pattern or "").strip().lower()
    if pattern not in {"fixed", "exponential"}:
        raise ValueError("Arrival pattern must be fixed or exponential.")
    frame = stations.copy(deep=True)
    try:
        frame["sequence"] = pd.to_numeric(frame["sequence"], errors="raise")
        frame["servers"] = pd.to_numeric(frame["servers"], errors="raise")
        frame["mean_service_minutes"] = pd.to_numeric(frame["mean_service_minutes"], errors="raise")
        frame["service_time_cv"] = pd.to_numeric(frame["service_time_cv"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("Station sequence, server count, service mean and CV must be numeric.") from exc
    if not np.isfinite(frame[["sequence","servers","mean_service_minutes","service_time_cv"]].to_numpy(dtype=float)).all():
        raise ValueError("Station numeric fields must be finite.")
    if len(frame) > 20:
        raise ValueError("Serial simulation is limited to 20 stations.")
    if frame["sequence"].duplicated().any():
        raise ValueError("Station sequence numbers must be unique.")
    frame["station_id"] = frame["station_id"].astype(str).str.strip()
    if (frame["station_id"] == "").any() or frame["station_id"].str.casefold().duplicated().any():
        raise ValueError("Station IDs must be non-empty and unique.")
    if not np.equal(frame["sequence"].to_numpy(), np.floor(frame["sequence"].to_numpy())).all():
        raise ValueError("Station sequence numbers must be whole integers.")
    if not np.equal(frame["servers"].to_numpy(), np.floor(frame["servers"].to_numpy())).all():
        raise ValueError("Station server counts must be whole integers.")
    if (frame["servers"] < 1).any():
        raise ValueError("Each station must have at least one server.")
    if (frame["mean_service_minutes"] <= 0).any():
        raise ValueError("Mean service minutes must be positive.")
    if ((frame["service_time_cv"] < 0) | (frame["service_time_cv"] > 3)).any():
        raise ValueError("Service-time CV must be between 0 and 3.")
    frame = frame.sort_values("sequence", kind="stable").reset_index(drop=True)
    station_names = frame["station_id"].tolist()
    servers = frame["servers"].astype(int).tolist()
    service_means = frame["mean_service_minutes"].astype(float).tolist()
    service_cvs = frame["service_time_cv"].astype(float).tolist()
    station_count = len(frame)

    replication_rows, entity_rows, station_rows = [], [], []
    def run_replication(rep_index: int) -> None:
        rng = np.random.default_rng(seed + rep_index)
        if pattern == "fixed":
            arrivals = np.arange(n_entities, dtype=float) * interarrival
        else:
            gaps = rng.exponential(interarrival, size=n_entities - 1)
            arrivals = np.concatenate(([0.0], np.cumsum(gaps)))
        n_events = 0
        event_heap = []
        event_seq = 0
        queues = [[] for _ in range(station_count)]
        busy = [0 for _ in range(station_count)]
        jobs = [{
            "arrival": float(arrivals[i]),
            "station_arrival": [None] * station_count,
            "station_start": [None] * station_count,
            "station_end": [None] * station_count,
            "service_time": [None] * station_count,
            "wait_time": [None] * station_count,
            "completion": None,
        } for i in range(n_entities)]
        def push(time_value: float, event_type: str, job_id: int, station_index: int) -> None:
            nonlocal event_seq, n_events
            heapq.heappush(event_heap, (float(time_value), event_seq, event_type, job_id, station_index))
            event_seq += 1
            n_events += 1
        def sample_service(station_index: int) -> float:
            mean = service_means[station_index]
            cv = service_cvs[station_index]
            if cv == 0:
                return mean
            sigma2 = math.log1p(cv * cv)
            mu = math.log(mean) - 0.5 * sigma2
            return float(rng.lognormal(mu, math.sqrt(sigma2)))
        def start_waiting_job(station_index: int, current_time: float) -> None:
            if busy[station_index] >= servers[station_index] or not queues[station_index]:
                return
            job_id = queues[station_index].pop(0)
            job = jobs[job_id]
            service = sample_service(station_index)
            start = float(current_time)
            finish = start + service
            busy[station_index] += 1
            job["station_start"][station_index] = start
            job["service_time"][station_index] = service
            job["wait_time"][station_index] = max(0.0, start - float(job["station_arrival"][station_index]))
            push(finish, "COMPLETE", job_id, station_index)
        for job_id, arrival_time in enumerate(arrivals):
            push(float(arrival_time), "ARRIVAL", job_id, 0)
        while event_heap:
            current_time, _, event_type, job_id, station_index = heapq.heappop(event_heap)
            job = jobs[job_id]
            if event_type == "ARRIVAL":
                job["station_arrival"][station_index] = float(current_time)
                queues[station_index].append(job_id)
                start_waiting_job(station_index, current_time)
            else:
                busy[station_index] -= 1
                job["station_end"][station_index] = float(current_time)
                if station_index + 1 < station_count:
                    push(current_time, "ARRIVAL", job_id, station_index + 1)
                else:
                    job["completion"] = float(current_time)
                start_waiting_job(station_index, current_time)
        # All jobs are drained before the run ends; first n_warmup jobs are warm-up only.
        end_time = max(float(j["completion"]) for j in jobs)
        measured_ids = range(n_warmup, n_entities)
        measured = [jobs[i] for i in measured_ids]
        cycle_times = [float(j["completion"] - j["arrival"]) for j in measured]
        measured_start = float(measured[0]["arrival"])
        measured_end = float(max(j["completion"] for j in measured))
        measurement_window = measured_end - measured_start
        throughput = len(measured) / measurement_window * 60.0 if measurement_window > 0 else None
        waits_by_station = []
        for si, station_id in enumerate(station_names):
            measured_waits = [float(j["wait_time"][si]) for j in measured]
            measured_services = [float(j["service_time"][si]) for j in measured]
            busy_service = float(sum(float(j["service_time"][si]) for j in jobs))
            utilization = busy_service / (end_time * servers[si]) * 100.0 if end_time > 0 else None
            avg_wait = float(np.mean(measured_waits)) if measured_waits else None
            waits_by_station.append(avg_wait or 0.0)
            station_rows.append({
                "replication": rep_index + 1,
                "station_id": station_id,
                "servers": servers[si],
                "mean_service_minutes": service_means[si],
                "service_time_cv": service_cvs[si],
                "average_queue_wait_minutes": avg_wait,
                "average_service_time_minutes": float(np.mean(measured_services)) if measured_services else None,
                "utilization_percent_including_warmup": utilization,
                "measured_entities": len(measured),
            })
        bottleneck_station = station_names[int(np.argmax(waits_by_station))] if station_names else None
        replication_rows.append({
            "replication": rep_index + 1,
            "seed": seed + rep_index,
            "measured_entity_count": len(measured),
            "measurement_window_minutes": measurement_window,
            "throughput_units_per_hour": throughput,
            "average_flow_time_minutes": float(np.mean(cycle_times)),
            "median_flow_time_minutes": float(np.median(cycle_times)),
            "p95_flow_time_minutes": float(np.quantile(cycle_times, 0.95)),
            "average_total_queue_wait_minutes": float(np.mean([sum(float(v) for v in j["wait_time"]) for j in measured])),
            "estimated_bottleneck_by_mean_queue_wait": bottleneck_station,
            "event_count": int(n_events),
        })
        for offset, job in enumerate(measured, start=n_warmup + 1):
            entity_rows.append({
                "replication": rep_index + 1,
                "entity_id": offset,
                "arrival_time_minutes": float(job["arrival"]),
                "completion_time_minutes": float(job["completion"]),
                "flow_time_minutes": float(job["completion"] - job["arrival"]),
                "total_queue_wait_minutes": float(sum(float(v) for v in job["wait_time"])),
                "total_service_time_minutes": float(sum(float(v) for v in job["service_time"])),
            })

    for rep_index in range(n_reps):
        run_replication(rep_index)

    rep_table = pd.DataFrame(replication_rows)
    entity_table = pd.DataFrame(entity_rows)
    station_rep_table = pd.DataFrame(station_rows)
    throughput_values = rep_table["throughput_units_per_hour"].dropna().to_numpy(dtype=float)
    flow_values = rep_table["average_flow_time_minutes"].to_numpy(dtype=float)
    wait_values = rep_table["average_total_queue_wait_minutes"].to_numpy(dtype=float)
    mean_flow = float(np.mean(flow_values))
    mean_wait = float(np.mean(wait_values))
    mean_throughput = float(np.mean(throughput_values)) if throughput_values.size else None
    flow_ci = None
    if len(flow_values) >= 2:
        se = float(np.std(flow_values, ddof=1) / math.sqrt(len(flow_values)))
        critical = float(student_t.ppf(0.975, len(flow_values) - 1))
        flow_ci = [mean_flow - critical * se, mean_flow + critical * se]
    station_summary = station_rep_table.groupby("station_id", as_index=False).agg(
        average_queue_wait_minutes=("average_queue_wait_minutes", "mean"),
        average_service_time_minutes=("average_service_time_minutes", "mean"),
        average_utilization_percent=("utilization_percent_including_warmup", "mean"),
        minimum_utilization_percent=("utilization_percent_including_warmup", "min"),
        maximum_utilization_percent=("utilization_percent_including_warmup", "max"),
    )
    warnings = [
        "This is a discrete-event serial-route model with FIFO station queues and pooled parallel servers; it is not a calibrated digital twin.",
        "Processing times are deterministic when CV=0 and otherwise lognormal with the entered mean and coefficient of variation.",
        "The first configured number of entities are simulated as warm-up and excluded from entity/cycle-time summaries; station utilization spans the full run including warm-up.",
        "The reported bottleneck is based on average queue wait, which is a screening signal rather than proof of a physical constraint.",
        "Routing, blocking, downtime/failures, changeovers, shifts, transport, shared workers and control policies are not modeled.",
    ]
    if n_reps == 1:
        warnings.append("One replication was run; between-replication confidence intervals are not available.")
    return {
        "tool_id": "T071",
        "status": "SIMULATED",
        "method": "Discrete-event serial flow line with event heap, FIFO queues, parallel servers, lognormal service variation and replications",
        "formula": "Events are processed chronologically; service starts when a server becomes available, and the next station receives the entity at previous-station completion.",
        "parameters": {
            "entity_count": n_entities, "warmup_entities": n_warmup,
            "replications": n_reps, "random_seed": seed,
            "mean_interarrival_minutes": interarrival, "arrival_pattern": pattern,
            "stations": frame.to_dict(orient="records"),
        },
        "warnings": warnings,
        "assumptions": [
            "The line has a fixed station sequence, no blocking and no reentrant routes.",
            "Arrivals are fixed-interval or exponential-interarrival; interarrival mean is in minutes.",
            "Service times use a lognormal distribution parameterized by the entered arithmetic mean and CV.",
            "The same configuration is independently rerun with seeds seed through seed+replications−1.",
        ],
        "metrics": {
            "entity_count": n_entities,
            "measured_entity_count_per_replication": n_entities - n_warmup,
            "warmup_entities_excluded": n_warmup,
            "station_count": int(station_count),
            "replications": n_reps,
            "mean_throughput_units_per_hour": mean_throughput,
            "mean_flow_time_minutes": mean_flow,
            "mean_flow_time_approx_95pct_t_interval": flow_ci,
            "mean_total_queue_wait_minutes": mean_wait,
            "highest_mean_queue_wait_station": str(station_summary.loc[station_summary["average_queue_wait_minutes"].idxmax(), "station_id"]),
            "total_events_across_replications": int(rep_table["event_count"].sum()),
            "live_data_connected": False,
        },
        "replication_summary": rep_table,
        "station_summary": station_summary,
        "entity_results": entity_table,
    }
