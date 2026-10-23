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


def _finite_number(value: Any, label: str) -> float:
    """Parse a finite numeric input without silently coercing invalid values."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    return number


def calculate_standard_time(
    observations: Sequence[float],
    performance_rating_percent: float,
    allowance_percent: float,
    *,
    allowance_basis: str = "normal_time",
) -> dict[str, Any]:
    """Compute observed summary, normal time and standard time under an explicit allowance basis.

    If allowances are expressed as a percentage of normal time:
      standard_time = normal_time * (1 + allowance)
    If allowances are expressed as a percentage of standard time:
      standard_time = normal_time / (1 - allowance)
    """
    if isinstance(observations, (str, bytes)) or not observations:
        raise ValueError("Enter at least one observed time.")
    values = [_finite_number(v, "Observed time") for v in observations]
    if any(v < 0 for v in values):
        raise ValueError("Observed times cannot be negative.")
    rating = _finite_number(performance_rating_percent, "Performance rating")
    allowance = _finite_number(allowance_percent, "Allowance percentage")
    if rating <= 0:
        raise ValueError("Performance rating must be greater than zero.")
    if not 0 <= allowance < 100:
        raise ValueError("Allowance must be at least 0% and less than 100%.")
    if allowance_basis not in {"normal_time", "standard_time"}:
        raise ValueError("Allowance basis must be 'normal_time' or 'standard_time'.")
    observed_mean = sum(values) / len(values)
    normal_time = observed_mean * rating / 100.0
    allowance_fraction = allowance / 100.0
    standard_time = (normal_time * (1.0 + allowance_fraction)
                     if allowance_basis == "normal_time"
                     else normal_time / (1.0 - allowance_fraction))
    return {
        "status": "CALCULATED",
        "method": "Mean observed time × performance rating; explicit allowance convention",
        "units": "Same time unit as observations",
        "metrics": {
            "observation_count": len(values),
            "observed_mean": observed_mean,
            "observed_median": float(pd.Series(values).median()),
            "observed_min": min(values),
            "observed_max": max(values),
            "normal_time": normal_time,
            "standard_time": standard_time,
        },
        "formulas": {
            "normal_time": "mean(observations) × performance_rating_percent / 100",
            "standard_time": (
                "normal_time × (1 + allowance_percent / 100)"
                if allowance_basis == "normal_time"
                else "normal_time / (1 - allowance_percent / 100)"
            ),
        },
        "assumptions": [
            "All observations use the same time unit and refer to the same defined work element.",
            "Performance rating and allowance values are user-supplied study assumptions.",
            f"Allowance is interpreted as a percentage of {allowance_basis.replace('_', ' ')}.",
        ],
        "warnings": [],
    }


def calculate_takt_capacity(
    available_time_minutes: float,
    demand_units: float,
    cycle_time_minutes: float,
) -> dict[str, Any]:
    """Compute takt time and theoretical cycle-time capacity for one defined period."""
    available = _finite_number(available_time_minutes, "Available production time")
    demand = _finite_number(demand_units, "Demand")
    cycle = _finite_number(cycle_time_minutes, "Cycle time")
    if available <= 0:
        raise ValueError("Available production time must be greater than zero.")
    if demand <= 0:
        raise ValueError("Demand must be greater than zero.")
    if cycle <= 0:
        raise ValueError("Cycle time must be greater than zero.")
    takt = available / demand
    capacity = available / cycle
    gap = capacity - demand
    return {
        "status": "CALCULATED",
        "method": "Takt = net available time / demand; theoretical capacity = net available time / cycle time",
        "units": {"available_time": "minutes per stated period", "demand": "units per stated period",
                  "takt": "minutes per unit", "capacity": "units per stated period"},
        "metrics": {
            "takt_time_minutes_per_unit": takt,
            "theoretical_capacity_units": capacity,
            "maximum_whole_units_at_cycle_time": math.floor(capacity + 1e-12),
            "capacity_gap_units": gap,
            "demand_feasible_at_cycle_time": capacity + 1e-12 >= demand,
            "cycle_time_vs_takt_percent": cycle / takt * 100.0,
        },
        "formulas": {
            "takt_time": "available_time_minutes / demand_units",
            "theoretical_capacity": "available_time_minutes / cycle_time_minutes",
        },
        "assumptions": [
            "Available production time is net time after breaks and planned non-production time.",
            "Demand and cycle time refer to the same period and compatible unit basis.",
            "Capacity is theoretical and excludes unmodelled stops, yield losses, staffing limits and variability.",
        ],
        "warnings": [],
    }


def calculate_oee(
    planned_production_minutes: float,
    downtime_minutes: float,
    ideal_cycle_seconds: float,
    total_count: int,
    good_count: int,
) -> dict[str, Any]:
    """Calculate OEE using time- and count-compatible inputs and a mutually consistent loss split."""
    planned = _finite_number(planned_production_minutes, "Planned production time")
    downtime = _finite_number(downtime_minutes, "Downtime")
    ideal_cycle = _finite_number(ideal_cycle_seconds, "Ideal cycle time")
    try:
        total_raw, good_raw = float(total_count), float(good_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("Total and good counts must be whole numbers.") from exc
    if not total_raw.is_integer() or not good_raw.is_integer():
        raise ValueError("Total and good counts must be whole numbers.")
    total, good = int(total_raw), int(good_raw)
    if planned <= 0:
        raise ValueError("Planned production time must be greater than zero.")
    if downtime < 0 or downtime >= planned:
        raise ValueError("Downtime must be at least zero and less than planned production time.")
    if ideal_cycle <= 0:
        raise ValueError("Ideal cycle time must be greater than zero.")
    if total <= 0:
        raise ValueError("Total output must be greater than zero.")
    if good < 0 or good > total:
        raise ValueError("Good output must be between zero and total output.")
    operating = planned - downtime
    availability = operating / planned
    # Convert ideal cycle seconds to minutes to match the duration inputs.
    ideal_cycle_minutes = ideal_cycle / 60.0
    performance = ideal_cycle_minutes * total / operating
    quality = good / total
    oee = availability * performance * quality
    losses = {
        "availability_loss_fraction": 1.0 - availability,
        "performance_loss_fraction": availability * (1.0 - performance),
        "quality_loss_fraction": availability * performance * (1.0 - quality),
    }
    return {
        "status": "CALCULATED",
        "method": "OEE = Availability × Performance × Quality",
        "units": {"time": "minutes", "ideal_cycle_time": "seconds per unit", "counts": "units",
                  "factors": "fraction and percent"},
        "metrics": {
            "operating_time_minutes": operating,
            "availability_fraction": availability, "availability_percent": availability * 100,
            "performance_fraction": performance, "performance_percent": performance * 100,
            "quality_fraction": quality, "quality_percent": quality * 100,
            "oee_fraction": oee, "oee_percent": oee * 100,
            "availability_loss_percent": losses["availability_loss_fraction"] * 100,
            "performance_loss_percent_of_planned_time": losses["performance_loss_fraction"] * 100,
            "quality_loss_percent_of_planned_time": losses["quality_loss_fraction"] * 100,
        },
        "formulas": {
            "availability": "(planned_production_minutes - downtime_minutes) / planned_production_minutes",
            "performance": "(ideal_cycle_seconds / 60 × total_count) / operating_time_minutes",
            "quality": "good_count / total_count",
            "oee": "availability × performance × quality",
        },
        "assumptions": [
            "Ideal cycle seconds are converted to minutes to match planned and downtime inputs.",
            "The loss split is sequential and sums to 1 - OEE; do not add it to a separate OEE loss figure.",
            "The calculation uses the definitions supplied here; local OEE conventions must be reconciled before operational use.",
        ],
        "warnings": (["Performance is above 100%; verify the ideal cycle time, time basis and production counts."]
                    if performance > 1.0 + 1e-9 else []),
    }


def calculate_process_capability(
    measurements: Sequence[float],
    lower_spec_limit: float,
    upper_spec_limit: float,
    *,
    subgroup_size: int,
) -> dict[str, Any]:
    """Compute Cp/Cpk from pooled within-subgroup variation and Pp/Ppk from overall sample variation."""
    if isinstance(measurements, (str, bytes)) or not measurements:
        raise ValueError("Enter at least two rational subgroups of measurements.")
    values = [_finite_number(v, "Measurement") for v in measurements]
    lsl = _finite_number(lower_spec_limit, "Lower specification limit")
    usl = _finite_number(upper_spec_limit, "Upper specification limit")
    if lsl >= usl:
        raise ValueError("Lower specification limit must be less than upper specification limit.")
    if not isinstance(subgroup_size, int) or isinstance(subgroup_size, bool) or subgroup_size < 2:
        raise ValueError("Subgroup size must be a whole number of at least 2.")
    if len(values) < 2 * subgroup_size or len(values) % subgroup_size != 0:
        raise ValueError("Use at least two complete subgroups; measurement count must be divisible by subgroup size.")
    n = len(values)
    overall_mean = sum(values) / n
    overall_sse = sum((v - overall_mean) ** 2 for v in values)
    overall_sigma = math.sqrt(overall_sse / (n - 1))
    subgroup_count = n // subgroup_size
    within_sse = 0.0
    for start in range(0, n, subgroup_size):
        group = values[start:start + subgroup_size]
        mean = sum(group) / subgroup_size
        within_sse += sum((v - mean) ** 2 for v in group)
    within_df = n - subgroup_count
    within_sigma = math.sqrt(within_sse / within_df) if within_df > 0 else 0.0
    if within_sigma <= 0 or overall_sigma <= 0:
        raise ValueError("Observed variation is zero; capability ratios are undefined without a validated resolution model.")
    mean = overall_mean
    cp = (usl - lsl) / (6.0 * within_sigma)
    cpu = (usl - mean) / (3.0 * within_sigma)
    cpl = (mean - lsl) / (3.0 * within_sigma)
    pp = (usl - lsl) / (6.0 * overall_sigma)
    ppu = (usl - mean) / (3.0 * overall_sigma)
    ppl = (mean - lsl) / (3.0 * overall_sigma)
    return {
        "status": "CALCULATED",
        "method": "Cp/Cpk use pooled within-subgroup standard deviation; Pp/Ppk use overall sample standard deviation",
        "units": "Same unit as measurements and specification limits",
        "metrics": {
            "sample_size": n, "subgroup_count": subgroup_count, "process_mean": mean,
            "within_subgroup_sigma": within_sigma, "overall_sample_sigma": overall_sigma,
            "Cp": cp, "Cpu": cpu, "Cpl": cpl, "Cpk": min(cpu, cpl),
            "Pp": pp, "Ppu": ppu, "Ppl": ppl, "Ppk": min(ppu, ppl),
        },
        "formulas": {
            "Cp": "(USL - LSL) / (6 × within_subgroup_sigma)",
            "Cpk": "min((USL - mean) / (3 × within_subgroup_sigma), (mean - LSL) / (3 × within_subgroup_sigma))",
            "Pp": "(USL - LSL) / (6 × overall_sample_sigma)",
            "Ppk": "min((USL - mean) / (3 × overall_sample_sigma), (mean - LSL) / (3 × overall_sample_sigma))",
        },
        "assumptions": [
            "Measurements are ordered into rational subgroups of the stated fixed size.",
            "Capability interpretation assumes the sampling process is representative; normality and statistical stability are not certified by these indices.",
            "Specification limits are supplied limits, not calculated control limits.",
        ],
        "warnings": ["Cpk/Ppk may be negative if the sample mean is outside a specification limit."],
    }


def calculate_inventory_policy(
    annual_demand: float,
    order_cost_per_order: float,
    annual_holding_cost_per_unit: float,
    lead_time_days: float,
    *,
    working_days_per_year: float = 250.0,
    daily_demand_std: float = 0.0,
    service_factor_z: float = 1.645,
) -> dict[str, Any]:
    """Calculate EOQ and a fixed-lead-time reorder point with explicit service factor."""
    demand = _finite_number(annual_demand, "Annual demand")
    order_cost = _finite_number(order_cost_per_order, "Order cost")
    holding_cost = _finite_number(annual_holding_cost_per_unit, "Annual holding cost per unit")
    lead = _finite_number(lead_time_days, "Lead time")
    working = _finite_number(working_days_per_year, "Working days per year")
    daily_std = _finite_number(daily_demand_std, "Daily demand standard deviation")
    z = _finite_number(service_factor_z, "Service factor (z)")
    if demand <= 0 or order_cost <= 0 or holding_cost <= 0 or working <= 0:
        raise ValueError("Demand, order cost, annual holding cost and working days must be greater than zero.")
    if lead < 0 or daily_std < 0 or z < 0:
        raise ValueError("Lead time, daily demand standard deviation and service factor cannot be negative.")
    eoq = math.sqrt(2.0 * demand * order_cost / holding_cost)
    daily_mean = demand / working
    safety_stock = z * daily_std * math.sqrt(lead)
    reorder_point = daily_mean * lead + safety_stock
    annual_ordering_cost = demand / eoq * order_cost
    annual_cycle_stock_holding_cost = eoq / 2.0 * holding_cost
    return {
        "status": "CALCULATED",
        "method": "EOQ with fixed lead time and safety stock based on daily-demand standard deviation",
        "units": {"demand": "units/year", "inventory": "units", "lead_time": "working days"},
        "metrics": {
            "EOQ_units": eoq, "average_daily_demand_units": daily_mean,
            "safety_stock_units": safety_stock, "reorder_point_units": reorder_point,
            "annual_ordering_cost": annual_ordering_cost,
            "annual_cycle_stock_holding_cost": annual_cycle_stock_holding_cost,
        },
        "formulas": {
            "EOQ": "sqrt(2 × annual_demand × order_cost_per_order / annual_holding_cost_per_unit)",
            "safety_stock": "z × daily_demand_standard_deviation × sqrt(lead_time_days)",
            "reorder_point": "average_daily_demand × lead_time_days + safety_stock",
        },
        "assumptions": [
            "EOQ assumes steady annual demand, constant order cost, constant annual holding cost and no quantity discounts.",
            "Reorder point assumes fixed lead time in working days and independent, stable daily demand; the user-supplied z value defines the service approximation.",
            "The inventory quantities may be fractional; operational rounding policy must be set by the user.",
        ],
        "warnings": [],
    }


def calculate_carbon_emissions(
    activity_quantity: float,
    factor_kg_co2e_per_unit: float,
    *,
    activity_unit: str,
    factor_source: str,
    factor_version: str,
    factor_date: str,
    scope_boundary: str,
) -> dict[str, Any]:
    """Multiply user-supplied activity data by a sourced/versioned factor in kg CO2e per activity unit."""
    quantity = _finite_number(activity_quantity, "Activity quantity")
    factor = _finite_number(factor_kg_co2e_per_unit, "Emissions factor")
    if quantity < 0 or factor < 0:
        raise ValueError("Activity quantity and emissions factor cannot be negative.")
    labels = {
        "activity unit": str(activity_unit or "").strip(),
        "factor source": str(factor_source or "").strip(),
        "factor version": str(factor_version or "").strip(),
        "factor date": str(factor_date or "").strip(),
        "scope boundary": str(scope_boundary or "").strip(),
    }
    missing = [name for name, value in labels.items() if not value]
    if missing:
        raise ValueError("Provide " + ", ".join(missing) + " before calculating emissions.")
    kg = quantity * factor
    return {
        "status": "CALCULATED",
        "method": "Activity quantity × supplied emissions factor",
        "units": {"activity": labels["activity unit"], "emissions": "kg CO2e and metric tonnes CO2e"},
        "metrics": {"activity_quantity": quantity, "factor_kg_co2e_per_unit": factor,
                    "emissions_kg_co2e": kg, "emissions_tonnes_co2e": kg / 1000.0},
        "formulas": {"emissions_kg_co2e": "activity_quantity × factor_kg_co2e_per_unit",
                     "emissions_tonnes_co2e": "emissions_kg_co2e / 1000"},
        "assumptions": [
            "The supplied factor's unit must match the activity unit exactly; this function does not perform cross-unit or currency conversion.",
            "Scope boundary and factor citation/version are supplied by the user and are not independently audited.",
            "Results are estimates from supplied data, not an audited greenhouse-gas disclosure.",
        ],
        "provenance": labels,
        "warnings": [],
    }


def calculate_engineering_economics(
    cash_flows: Sequence[float],
    discount_rate_percent: float,
    *,
    period_unit: str = "year",
) -> dict[str, Any]:
    """Calculate NPV, a bracketed IRR for conventional cashflows, and simple payback."""
    if isinstance(cash_flows, (str, bytes)) or len(cash_flows) < 2:
        raise ValueError("Enter an initial cash flow and at least one later-period cash flow.")
    flows = [_finite_number(v, "Cash flow") for v in cash_flows]
    if len(flows) > 101:
        raise ValueError("At most 101 cash-flow periods (period 0 through period 100) are supported.")
    rate_pct = _finite_number(discount_rate_percent, "Discount rate")
    if rate_pct <= -100:
        raise ValueError("Discount rate must be greater than -100%.")
    if period_unit not in {"year", "month", "quarter"}:
        raise ValueError("Period unit must be year, month or quarter.")
    rate = rate_pct / 100.0

    def npv_at(r: float) -> float:
        base = 1.0 + r
        if base <= 0:
            raise ValueError("Discount rate is outside the valid domain.")
        value = 0.0
        for period, flow in enumerate(flows):
            try:
                denominator = math.pow(base, period)
                if denominator == 0 or not math.isfinite(denominator):
                    raise ValueError
                term = flow / denominator
            except (OverflowError, ZeroDivisionError, ValueError) as exc:
                raise ValueError("Cash flows and discount rate exceed the supported numeric range.") from exc
            if not math.isfinite(term) or not math.isfinite(value + term):
                raise ValueError("Cash flows and discount rate exceed the supported numeric range.")
            value += term
        return value

    npv = npv_at(rate)
    nonzero_signs = [1 if flow > 0 else -1 for flow in flows if flow != 0]
    sign_changes = sum(nonzero_signs[i] != nonzero_signs[i - 1] for i in range(1, len(nonzero_signs)))
    irr = None
    irr_status = "NOT_UNIQUE_CONVENTIONAL_CASHFLOW"
    if flows[0] < 0 and sign_changes == 1:
        low, high = -0.99, 10.0
        try:
            f_low, f_high = npv_at(low), npv_at(high)
            if f_low == 0:
                irr, irr_status = low * 100.0, "BRACKETED"
            elif f_high == 0:
                irr, irr_status = high * 100.0, "BRACKETED"
            elif (f_low < 0) != (f_high < 0):
                magnitude = max(1.0, sum(abs(x) for x in flows))
                for _ in range(200):
                    mid = (low + high) / 2.0
                    f_mid = npv_at(mid)
                    if abs(f_mid) <= 1e-12 * magnitude or high - low <= 1e-12:
                        irr, irr_status = mid * 100.0, "BRACKETED"
                        break
                    if (f_low < 0) == (f_mid < 0):
                        low, f_low = mid, f_mid
                    else:
                        high, f_high = mid, f_mid
                if irr is None:
                    irr = ((low + high) / 2.0) * 100.0
                    irr_status = "BRACKETED"
            else:
                irr_status = "NO_ROOT_IN_SUPPORTED_BRACKET"
        except ValueError:
            irr_status = "NUMERIC_RANGE_LIMIT"
    elif flows[0] >= 0:
        irr_status = "INITIAL_CASHFLOW_NOT_NEGATIVE"

    cumulative = flows[0]
    payback = None
    if cumulative >= 0:
        payback = 0.0
    else:
        for period, flow in enumerate(flows[1:], start=1):
            previous = cumulative
            cumulative += flow
            if previous < 0 and cumulative >= 0 and flow > 0:
                payback = (period - 1) + (-previous / flow)
                break
    warnings = []
    if irr is None:
        warnings.append(
            "IRR was not reported because this cash-flow pattern did not have a validated root "
            "inside the supported bracket; this avoids implying a unique IRR when it is not established."
        )
    if payback is None:
        warnings.append("Simple payback is not reached within the supplied periods.")
    return {
        "status": "CALCULATED",
        "method": "NPV at the specified discount rate; bracketed IRR only for conventional one-sign-change cash flows; simple undiscounted payback",
        "units": {"cash_flows": "currency per stated period", "npv": "same currency", "irr": "percent per period"},
        "metrics": {"NPV": npv, "IRR_percent": irr, "IRR_status": irr_status,
                    "simple_payback_periods": payback, "period_count_after_initial": len(flows) - 1},
        "formulas": {
            "NPV": "sum(CF_t / (1 + discount_rate)^t), including CF_0",
            "IRR": "rate r satisfying sum(CF_t / (1 + r)^t) = 0, reported only when bracketed for a conventional cash-flow pattern",
            "simple_payback": "first period cumulative undiscounted cash flow reaches zero, linearly interpolated within that period",
        },
        "assumptions": [
            "Cash flows occur at equal period intervals and period 0 is immediate.",
            f"Discount-rate periods are expressed in {period_unit}s; cash-flow currency is user-supplied.",
            "IRR may have multiple/no roots; this method reports it only for conventional cash flows with a supported bracket.",
            "Simple payback ignores discounting and cash flows after the recovery point.",
        ],
        "warnings": warnings,
    }


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
    if source.duplicated(subset=[case_col, "_ts_utc"]).any():
        raise ValueError(
            "Multiple events in one case share a timestamp; resolve event ordering "
            "or provide an unambiguous sequence before analysis."
        )
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
