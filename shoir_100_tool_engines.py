"""Deterministic target engines for supported bin-packing and event-log analysis.

Limits are explicit: bin packing is 1-D First-Fit Decreasing (feasible heuristic,
not an optimality proof or cutting-stock pattern optimizer). Process mining emits
directly-follows counts, waits/durations, and optional exact reference-trace checks;
it is not a full Petri-net conformance engine. Inputs are never mutated in place.
"""
from __future__ import annotations
import math
from typing import Any, Sequence
import pandas as pd


def _positive_finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and greater than zero.")
    return number


def first_fit_decreasing_bin_pack(
    items: pd.DataFrame, capacity: float, *,
    item_col: str = "item", size_col: str = "size", quantity_col: str | None = "quantity",
) -> dict[str, Any]:
    """Return a feasible 1-D First-Fit Decreasing assignment and capacity accounting."""
    cap = _positive_finite(capacity, "Capacity")
    if not isinstance(items, pd.DataFrame):
        raise ValueError("Items must be supplied as a table.")
    missing = [name for name in (item_col, size_col) if name not in items.columns]
    if missing:
        raise ValueError("Missing required item columns: " + ", ".join(missing))
    if items.empty:
        raise ValueError("Add at least one item before running bin packing.")
    source = items.copy(deep=True)
    if source[item_col].isna().any() or source[item_col].astype(str).str.strip().eq("").any():
        raise ValueError("Every item must have a non-empty name.")
    source["_size_numeric"] = pd.to_numeric(source[size_col], errors="coerce")
    if source["_size_numeric"].isna().any() or not source["_size_numeric"].map(math.isfinite).all():
        raise ValueError("Every item size must be a finite number.")
    if (source["_size_numeric"] <= 0).any():
        raise ValueError("Every item size must be greater than zero.")
    if (source["_size_numeric"] > cap).any():
        raise ValueError("An item size exceeds bin capacity.")

    expanded = []
    for input_index, row in source.iterrows():
        quantity = row[quantity_col] if quantity_col and quantity_col in source.columns else 1
        try:
            q = float(quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("Item quantity must be a positive whole number.") from exc
        if not math.isfinite(q) or q < 1 or not q.is_integer():
            raise ValueError("Item quantity must be a positive whole number.")
        for instance in range(1, int(q) + 1):
            expanded.append({"item": str(row[item_col]).strip(), "size": float(row["_size_numeric"]),
                             "source_row": str(input_index), "instance": instance, "_order": len(expanded)})
    ordered = sorted(expanded, key=lambda item: (-item["size"], item["_order"]))
    bins: list[dict[str, Any]] = []
    assignments = []
    eps = 1e-9
    for item in ordered:
        chosen = next((bin_row for bin_row in bins if bin_row["used"] + item["size"] <= cap + eps), None)
        if chosen is None:
            chosen = {"bin_id": len(bins) + 1, "used": 0.0, "items": []}
            bins.append(chosen)
        chosen["items"].append(item)
        chosen["used"] += item["size"]
        assignments.append({"Item": item["item"], "Instance": item["instance"], "Size": item["size"],
                            "Bin": chosen["bin_id"], "Bin load after placement": chosen["used"]})
    bin_rows = []
    for b in bins:
        used = float(b["used"])
        bin_rows.append({"Bin": b["bin_id"],
                         "Items": ", ".join(f'{i["item"]} #{i["instance"]}' for i in b["items"]),
                         "Used capacity": used, "Capacity": cap,
                         "Unused capacity": max(0.0, cap-used), "Utilization (%)": used/cap*100})
    total_size = sum(item["size"] for item in expanded)
    cap_total = len(bins) * cap
    return {
        "status": "HEURISTIC_FEASIBLE",
        "method": "First-Fit Decreasing (1-D bin packing)",
        "optimality_proven": False,
        "metrics": {"item_instances": len(expanded), "bins_used": len(bins), "item_size_total": total_size,
                    "capacity_total": cap_total, "unused_capacity_total": max(0.0, cap_total-total_size),
                    "utilization_percent": total_size/cap_total*100 if cap_total else 0.0},
        "assignments": pd.DataFrame(assignments), "bins": pd.DataFrame(bin_rows),
        "warnings": [
            "First-Fit Decreasing is a feasible heuristic, not proof of minimum-bin optimality.",
            "One-dimensional packing only; cutting-stock pattern generation and multi-dimensional packing are not implemented.",
        ],
    }


def analyze_process_event_log(
    events: pd.DataFrame, *, case_col: str = "case_id", activity_col: str = "activity",
    timestamp_col: str = "timestamp", reference_sequence: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Calculate directly-follows counts, activity/case metrics and inter-event waits."""
    if not isinstance(events, pd.DataFrame):
        raise ValueError("Event log must be supplied as a table.")
    required = (case_col, activity_col, timestamp_col)
    missing = [name for name in required if name not in events.columns]
    if missing:
        raise ValueError("Missing required event-log columns: " + ", ".join(missing))
    if events.empty:
        raise ValueError("Add event records before running process mining.")
    source = events.copy(deep=True)
    for col in (case_col, activity_col):
        if source[col].isna().any() or source[col].astype(str).str.strip().eq("").any():
            raise ValueError(f"Event-log field '{col}' must not be empty.")
        source[col] = source[col].astype(str).str.strip()
    ts = pd.to_datetime(source[timestamp_col], errors="coerce", utc=True)
    if ts.isna().any():
        raise ValueError(f"Event-log field '{timestamp_col}' contains invalid timestamps.")
    source["_ts_utc"] = ts
    source["_input_order"] = range(len(source))
    source = source.sort_values([case_col, "_ts_utc", "_input_order"], kind="mergesort").reset_index(drop=True)
    source["_next_activity"] = source.groupby(case_col, sort=False)[activity_col].shift(-1)
    source["_next_ts"] = source.groupby(case_col, sort=False)["_ts_utc"].shift(-1)
    transitions = source[source["_next_activity"].notna()].copy()
    if transitions.empty:
        dfg = pd.DataFrame(columns=["From activity","To activity","transition_count",
                                    "mean_wait_minutes","median_wait_minutes","transition_share_percent"])
    else:
        transitions["wait_minutes"] = (transitions["_next_ts"]-transitions["_ts_utc"]).dt.total_seconds()/60
        dfg = (transitions.groupby([activity_col,"_next_activity"], dropna=False)
               .agg(transition_count=(case_col,"size"), mean_wait_minutes=("wait_minutes","mean"),
                    median_wait_minutes=("wait_minutes","median")).reset_index()
               .rename(columns={activity_col:"From activity","_next_activity":"To activity"})
               .sort_values(["transition_count","From activity","To activity"],
                            ascending=[False,True,True]).reset_index(drop=True))
        dfg["transition_share_percent"] = dfg["transition_count"]/len(transitions)*100.0

    reference = [str(v).strip() for v in (reference_sequence or ()) if str(v).strip()]
    case_rows = []
    for case_id, group in source.groupby(case_col, sort=False):
        group = group.sort_values(["_ts_utc","_input_order"], kind="mergesort")
        activities = group[activity_col].tolist()
        start, end = group["_ts_utc"].iloc[0], group["_ts_utc"].iloc[-1]
        row = {"Case": str(case_id), "Events": len(group), "Activity trace": " → ".join(activities),
               "Start (UTC)": start.isoformat(), "End (UTC)": end.isoformat(),
               "Duration (minutes)": float((end-start).total_seconds()/60)}
        if reference:
            row["Exact reference-trace match"] = activities == reference
        case_rows.append(row)
    cases = pd.DataFrame(case_rows)
    activities = (source.groupby(activity_col)
                  .agg(event_count=(case_col,"size"),case_count=(case_col,"nunique")).reset_index()
                  .rename(columns={activity_col:"Activity","event_count":"Event count","case_count":"Case count"})
                  .sort_values(["Event count","Activity"],ascending=[False,True]).reset_index(drop=True))
    durations = cases["Duration (minutes)"].astype(float)
    return {
        "status": "ANALYZED",
        "method": "Directly-follows graph and case-duration analysis (timestamps normalized to UTC)",
        "metrics": {"case_count": int(len(cases)), "event_count": int(len(source)),
                    "transition_count": int(len(transitions)), "activity_count": int(source[activity_col].nunique()),
                    "mean_case_duration_minutes": float(durations.mean()),
                    "median_case_duration_minutes": float(durations.median())},
        "cases": cases, "directly_follows": dfg, "activities": activities,
        "warnings": [
            "Basic event-log analysis only: directly-follows frequencies and elapsed times are provided.",
            "Reference conformance is an exact ordered-trace comparison, not full Petri-net alignment.",
            "Timestamps are normalized to UTC; interpret the source timezone correctly before import.",
        ],
    }
