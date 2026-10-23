"""Deterministic specialist engines introduced for the 100-tool workbench.

Only methods documented here are implemented. Bin packing currently supports a
one-dimensional First-Fit Decreasing feasibility heuristic (not an optimality
proof and not a cutting-stock pattern optimizer). Process mining currently
supports directly-follows counts, case duration/waits, and optional exact-sequence
comparison against a supplied reference trace (not a full Petri-net conformance
engine). Inputs are copied, validated and never mutated in place.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import pandas as pd


def _finite_positive(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be finite and greater than zero.")
    return result


def first_fit_decreasing_bin_pack(
    items: pd.DataFrame,
    capacity: float,
    *,
    item_col: str = "item",
    size_col: str = "size",
    quantity_col: str | None = "quantity",
) -> dict[str, Any]:
    """Create a valid one-dimensional bin assignment with First-Fit Decreasing.

    Required columns are item_col and size_col; quantity_col is optional. The
    function expands integer quantities, sorts by descending size, then assigns
    each instance to the first existing bin where it fits, otherwise a new bin.
    The output is a feasible heuristic, not a minimum-bin optimality certificate.
    """
    cap = _finite_positive(capacity, "Capacity")
    if not isinstance(items, pd.DataFrame):
        raise ValueError("Items must be supplied as a table.")
    required = [item_col, size_col]
    missing = [col for col in required if col not in items.columns]
    if missing:
        raise ValueError("Missing required item columns: " + ", ".join(missing))
    if items.empty:
        raise ValueError("Add at least one item before running bin packing.")

    source = items.copy(deep=True)
    if source[item_col].isna().any() or source[item_col].astype(str).str.strip().eq("").any():
        raise ValueError("Every item must have a non-empty name.")
    source["_size_num"] = pd.to_numeric(source[size_col], errors="coerce")
    if source["_size_num"].isna().any():
        raise ValueError("Every item size must be numeric.")
    if not source["_size_num"].map(math.isfinite).all():
        raise ValueError("Item sizes must be finite.")
    if (source["_size_num"] <= 0).any():
        raise ValueError("Every item size must be greater than zero.")
    if (source["_size_num"] > cap).any():
        largest = float(source["_size_num"].max())
        raise ValueError(f"An item size ({largest:g}) exceeds bin capacity ({cap:g}).")

    instances: list[dict[str, Any]] = []
    for row_num, row in source.iterrows():
        raw_quantity: Any = 1
        if quantity_col and quantity_col in source.columns:
            raw_quantity = row[quantity_col]
        try:
            quantity_float = float(raw_quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("Item quantity must be a positive whole number.") from exc
        if not math.isfinite(quantity_float) or quantity_float < 1 or not quantity_float.is_integer():
            raise ValueError("Item quantity must be a positive whole number.")
        size = float(row["_size_num"])
        for sequence in range(1, int(quantity_float) + 1):
            instances.append({
                "item": str(row[item_col]).strip(),
                "size": size,
                "source_row": str(row_num),
                "instance": sequence,
                "_stable_order": len(instances),
            })

    ordered = sorted(instances, key=lambda row: (-row["size"], row["_stable_order"]))
    bins: list[dict[str, Any]] = []
    assigned: list[dict[str, Any]] = []
    epsilon = 1e-9
    for item in ordered:
        target = None
        for candidate in bins:
            if candidate["used"] + item["size"] <= cap + epsilon:
                target = candidate
                break
        if target is None:
            target = {"bin_id": len(bins) + 1, "used": 0.0, "items": []}
            bins.append(target)
        target["items"].append(item)
        target["used"] += item["size"]
        assigned.append({
            "Item": item["item"],
            "Instance": item["instance"],
            "Size": item["size"],
            "Bin": target["bin_id"],
            "Bin load after placement": target["used"],
        })

    bin_rows = []
    for candidate in bins:
        used = float(candidate["used"])
        waste = max(0.0, cap - used)
        bin_rows.append({
            "Bin": candidate["bin_id"],
            "Items": ", ".join(f'{x["item"]} #{x["instance"]}' for x in candidate["items"]),
            "Used capacity": used,
            "Capacity": cap,
            "Unused capacity": waste,
            "Utilization (%)": (used / cap) * 100.0,
        })
    total_size = sum(item["size"] for item in instances)
    total_capacity = len(bins) * cap
    return {
        "status": "HEURISTIC_FEASIBLE",
        "method": "First-Fit Decreasing (1-D bin packing)",
        "optimality_proven": False,
        "metrics": {
            "item_instances": len(instances),
            "bins_used": len(bins),
            "item_size_total": total_size,
            "capacity_total": total_capacity,
            "unused_capacity_total": max(0.0, total_capacity - total_size),
            "utilization_percent": (total_size / total_capacity * 100.0) if total_capacity else 0.0,
        },
        "assignments": pd.DataFrame(assigned),
        "bins": pd.DataFrame(bin_rows),
        "warnings": [
            "Feasible First-Fit Decreasing heuristic only; the result is not proof of a minimum-bin optimum.",
            "One-dimensional packing is supported. Cutting-stock pattern optimization and multi-dimensional packing are not implemented.",
        ],
    }


def analyze_process_event_log(
    events: pd.DataFrame,
    *,
    case_col: str = "case_id",
    activity_col: str = "activity",
    timestamp_col: str = "timestamp",
    reference_sequence: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Analyze event logs with directly-follows, case duration and wait-time metrics."""
    if not isinstance(events, pd.DataFrame):
        raise ValueError("Event log must be supplied as a table.")
    required = [case_col, activity_col, timestamp_col]
    missing = [col for col in required if col not in events.columns]
    if missing:
        raise ValueError("Missing required event-log columns: " + ", ".join(missing))
    if events.empty:
        raise ValueError("Add event records before running process mining.")

    source = events.copy(deep=True)
    for col in (case_col, activity_col):
        if source[col].isna().any() or source[col].astype(str).str.strip().eq("").any():
            raise ValueError(f"Event-log field '{col}' must not be empty.")
        source[col] = source[col].astype(str).str.strip()
    parsed = pd.to_datetime(source[timestamp_col], errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError(f"Event-log field '{timestamp_col}' contains invalid timestamps.")
    source["_parsed_timestamp"] = parsed
    source["_input_order"] = range(len(source))
    source = source.sort_values(
        [case_col, "_parsed_timestamp", "_input_order"], kind="mergesort"
    ).reset_index(drop=True)

    source["_next_activity"] = source.groupby(case_col, sort=False)[activity_col].shift(-1)
    source["_next_timestamp"] = source.groupby(case_col, sort=False)["_parsed_timestamp"].shift(-1)
    transitions = source[source["_next_activity"].notna()].copy()
    if not transitions.empty:
        transitions["wait_minutes"] = (
            transitions["_next_timestamp"] - transitions["_parsed_timestamp"]
        ).dt.total_seconds() / 60.0
        dfg = (
            transitions.groupby([activity_col, "_next_activity"], dropna=False)
            .agg(
                transition_count=(case_col, "size"),
                mean_wait_minutes=("wait_minutes", "mean"),
                median_wait_minutes=("wait_minutes", "median"),
            )
            .reset_index()
            .rename(columns={activity_col: "From activity", "_next_activity": "To activity"})
            .sort_values(["transition_count", "From activity", "To activity"], ascending=[False, True, True])
            .reset_index(drop=True)
        )
        dfg["transition_share_percent"] = (
            dfg["transition_count"] / len(transitions) * 100.0
        )
    else:
        dfg = pd.DataFrame(columns=[
            "From activity", "To activity", "transition_count",
            "mean_wait_minutes", "median_wait_minutes", "transition_share_percent",
        ])

    cases: list[dict[str, Any]] = []
    reference = [str(value).strip() for value in reference_sequence or () if str(value).strip()]
    for case_id, group in source.groupby(case_col, sort=False):
        ordered = group.sort_values(["_parsed_timestamp", "_input_order"], kind="mergesort")
        activities = ordered[activity_col].tolist()
        start = ordered["_parsed_timestamp"].iloc[0]
        end = ordered["_parsed_timestamp"].iloc[-1]
        case_row = {
            "Case": str(case_id),
            "Events": int(len(ordered)),
            "Activity trace": " → ".join(activities),
            "Start (UTC)": start.isoformat(),
            "End (UTC)": end.isoformat(),
            "Duration (minutes)": float((end - start).total_seconds() / 60.0),
        }
        if reference:
            case_row["Exact reference-trace match"] = activities == reference
        cases.append(case_row)
    case_table = pd.DataFrame(cases)
    activity_table = (
        source.groupby(activity_col)
        .agg(event_count=(case_col, "size"), case_count=(case_col, "nunique"))
        .reset_index()
        .rename(columns={activity_col: "Activity", "event_count": "Event count", "case_count": "Case count"})
        .sort_values(["Event count", "Activity"], ascending=[False, True])
        .reset_index(drop=True)
    )
    durations = case_table["Duration (minutes)"].astype(float)
    metrics = {
        "case_count": int(len(case_table)),
        "event_count": int(len(source)),
        "transition_count": int(len(transitions)),
        "activity_count": int(source[activity_col].nunique()),
        "mean_case_duration_minutes": float(durations.mean()),
        "median_case_duration_minutes": float(durations.median()),
    }
    warnings = [
        "Basic event-log analysis only: directly-follows frequencies and elapsed times are provided.",
        "Reference conformance, when supplied, is an exact ordered-trace comparison, not full Petri-net alignment.",
        "All event timestamps are normalized to UTC; ensure the source timezone is interpreted correctly before import.",
    ]
    return {
        "status": "ANALYZED",
        "method": "Directly-follows graph and case-duration analysis",
        "metrics": metrics,
        "cases": case_table,
        "directly_follows": dfg,
        "activities": activity_table,
        "warnings": warnings,
    }
