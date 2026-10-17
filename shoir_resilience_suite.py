"""Resilience, circularity, mobility, humanitarian and local-capability workspaces.

These workspaces are decision-support sandboxes. Sample data is synthetic, results are
model outputs, and no module controls real equipment or performs live routing.
All scenarios are limited to industrial/civilian decision support and do not control real systems.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import linprog


GLOBAL_SUPPLY = "Autonomous Global Supply Chain & Resilient Logistics Network"
CLOSED_LOOP = "Zero-Waste Closed-Loop Mega-Factory (Industrial Symbiosis Engine)"
URBAN_MOBILITY = "Real-Time Urban Mobility & Smart Infrastructure Grid"
HUMANITARIAN = "Fully Automated Emergency Response & Humanitarian Disaster Logistics System"
AKDT = "Autonomous Kinetic-Digital Twin (AKDT) for Industrial Logistics Resilience"
LSIMS = "L-SIMS — Local Capability & Dynamic Industrial Readiness Simulator"

RESILIENCE_MODULES = (GLOBAL_SUPPLY, CLOSED_LOOP, URBAN_MOBILITY, HUMANITARIAN, AKDT, LSIMS)

MODULE_DEFINITIONS = {
    GLOBAL_SUPPLY: {
        "tier": "Enterprise", "category": "Supply Chain Resilience",
        "when": "Stress-test multi-supplier supply networks against capacity loss, lead-time variation, demand shocks, carbon cost and supplier risk.",
        "example": "Edit supplier capacity and destination demand, disable a supplier, then compare allocations, shortages, modeled cost and emissions proxy.",
        "kpis": ("Service level", "Unmet demand", "Modeled cost", "Carbon proxy"),
    },
    CLOSED_LOOP: {
        "tier": "Enterprise", "category": "Circular Manufacturing",
        "when": "Quantify material, water and heat recovery opportunities across a connected industrial site.",
        "example": "Edit recoverable waste and reuse demand, change capture rates, and compare circularity, residual waste and modeled utility-value opportunities.",
        "kpis": ("Material circularity", "Residual waste", "Recovered heat", "Modeled value"),
    },
    URBAN_MOBILITY: {
        "tier": "Enterprise", "category": "Urban Systems",
        "when": "Explore aggregated transport demand, road/transit capacity, signal efficiency, delay and emissions trade-offs.",
        "example": "Change mode share, adjust capacity and test demand peaks using an editable synthetic junction table.",
        "kpis": ("Served demand", "Capacity utilization", "Modeled delay", "Emissions proxy"),
    },
    HUMANITARIAN: {
        "tier": "Enterprise", "category": "Humanitarian Logistics",
        "when": "Plan equitable aid-stock allocation against relief demand, depot capacity, response time and disruption uncertainty.",
        "example": "Prioritize regions, constrain depots or apply a demand surge and inspect modeled coverage, shortages and response-time trade-offs.",
        "kpis": ("Aid fulfillment", "Unmet relief demand", "Response-time proxy", "Depot utilization"),
    },
    AKDT: {
        "tier": "Enterprise Plus", "category": "Industrial Digital Twin",
        "when": "Combine synthetic asset telemetry, availability and alternate capacity into a resilient industrial operations sandbox.",
        "example": "Stress-test assets, simulate a telemetry gap, switch between conceptual cloud and edge modes, and compare health and recovery-capacity indicators.",
        "kpis": ("Asset health index", "Risk flags", "Available capacity", "Telemetry coverage"),
    },
    LSIMS: {
        "tier": "Enterprise", "category": "Local Manufacturing Capability",
        "when": "Map aggregated domestic manufacturing and repair capacity for industrial spare-part families and localization research.",
        "example": "Compare local supplier capacity, qualification confidence, lead time and monthly industrial demand to find capability gaps.",
        "kpis": ("Local content proxy", "Demand fulfilled", "Capability coverage", "Repair capacity"),
    },
}


def _number(frame: pd.DataFrame, field: str, default: float = 0.0) -> pd.Series:
    if field not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(frame[field], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(default).astype(float)


def _clean_table(frame: pd.DataFrame, required: Sequence[str]) -> pd.DataFrame:
    """Return a safe copy with required columns present and finite nonnegative numerics."""
    df = frame.copy(deep=True) if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    for col in required:
        if col not in df.columns:
            df[col] = 0.0
    df = df.replace([np.inf, -np.inf], np.nan)
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).clip(lower=0.0)
    return df.reset_index(drop=True)


def solve_transport_allocation(
    suppliers: pd.DataFrame,
    demands: pd.DataFrame,
    *,
    disabled_suppliers: Sequence[str] = (),
    capacity_scale: float = 1.0,
    demand_scale: float = 1.0,
    cost_weight: float = 1.0,
    lead_weight: float = 0.35,
    risk_weight: float = 0.25,
    carbon_weight: float = 0.0,
    route_adjustments: Mapping[tuple[str, str], float] | None = None,
) -> dict[str, Any]:
    """Solve a transportation LP with explicit shortage variables and finite penalties.

    The shortage variables ensure the model stays feasible when demand exceeds capacity;
    shortages are visible outputs and never silently treated as delivered units.
    """
    supplier_required = ("Capacity", "Unit Cost", "Lead Days", "Risk %", "Carbon kg/unit", "Local Share %")
    demand_required = ("Demand", "Priority", "Due Days")
    s = _clean_table(suppliers, supplier_required)
    d = _clean_table(demands, demand_required)
    if s.empty or d.empty:
        return {
            "status": "No data", "routes": pd.DataFrame(), "shortages": pd.DataFrame(),
            "supplier_summary": pd.DataFrame(), "metrics": {"service_level_pct": 0.0, "unmet_demand": 0.0},
            "message": "Add at least one supplier and one demand destination.",
        }

    s_names = s["Supplier"].astype(str).tolist() if "Supplier" in s.columns else [f"Supplier {i+1}" for i in range(len(s))]
    d_names = d["Destination"].astype(str).tolist() if "Destination" in d.columns else [f"Destination {i+1}" for i in range(len(d))]
    disabled = {str(x) for x in disabled_suppliers}
    effective_capacity = _number(s, "Capacity").to_numpy() * max(0.0, float(capacity_scale))
    effective_capacity = np.asarray([0.0 if name in disabled else cap for name, cap in zip(s_names, effective_capacity)])
    raw_demand = _number(d, "Demand").to_numpy() * max(0.0, float(demand_scale))
    priorities = np.clip(_number(d, "Priority", 1.0).to_numpy(), 1.0, 5.0)
    due = _number(d, "Due Days").to_numpy()
    routes_adjust = route_adjustments or {}
    ns, nd = len(s), len(d)
    shipment_count = ns * nd
    c_ship = []
    for i in range(ns):
        for j in range(nd):
            unit_cost = max(0.0, float(s.iloc[i]["Unit Cost"]))
            lead = max(0.0, float(s.iloc[i]["Lead Days"]))
            risk = min(100.0, max(0.0, float(s.iloc[i]["Risk %"])))
            carbon = max(0.0, float(s.iloc[i]["Carbon kg/unit"]))
            adjusted = max(0.0, float(routes_adjust.get((s_names[i], d_names[j]), 0.0)))
            c_ship.append(
                max(0.0, float(cost_weight)) * unit_cost
                + max(0.0, float(lead_weight)) * lead
                + max(0.0, float(risk_weight)) * risk
                + max(0.0, float(carbon_weight)) * carbon
                + adjusted
            )
    shortage_penalty = max(1000.0, (max(c_ship, default=1.0) + 1.0) * 100.0)
    objective = np.asarray(c_ship + [shortage_penalty * (1.0 + p / 5.0) for p in priorities], dtype=float)

    a_ub = np.zeros((ns, shipment_count + nd), dtype=float)
    for i in range(ns):
        a_ub[i, i * nd:(i + 1) * nd] = 1.0
    b_ub = effective_capacity
    a_eq = np.zeros((nd, shipment_count + nd), dtype=float)
    for j in range(nd):
        for i in range(ns):
            a_eq[j, i * nd + j] = 1.0
        a_eq[j, shipment_count + j] = 1.0
    b_eq = raw_demand
    result = linprog(objective, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=(0, None), method="highs")

    if not result.success:
        return {
            "status": f"Solver issue: {result.message}", "routes": pd.DataFrame(), "shortages": pd.DataFrame(),
            "supplier_summary": pd.DataFrame(), "metrics": {"service_level_pct": 0.0, "unmet_demand": float(raw_demand.sum())},
            "message": "The optimizer could not solve these inputs. Review values and try again.",
        }
    x = result.x[:shipment_count].reshape((ns, nd))
    shortage_values = result.x[shipment_count:]
    routes = []
    for i in range(ns):
        for j in range(nd):
            qty = float(x[i, j])
            if qty > 1e-6:
                routes.append({
                    "Supplier": s_names[i], "Destination": d_names[j], "Allocated units": qty,
                    "Unit cost": float(s.iloc[i]["Unit Cost"]), "Lead days": float(s.iloc[i]["Lead Days"]),
                    "Risk %": float(s.iloc[i]["Risk %"]), "Carbon kg/unit": float(s.iloc[i]["Carbon kg/unit"]),
                    "Local share %": float(s.iloc[i]["Local Share %"]), "Weighted route score": float(c_ship[i * nd + j]),
                })
    route_df = pd.DataFrame(routes, columns=["Supplier", "Destination", "Allocated units", "Unit cost", "Lead days", "Risk %", "Carbon kg/unit", "Local share %", "Weighted route score"])
    shipped_by_dest = x.sum(axis=0)
    shortage_df = pd.DataFrame({
        "Destination": d_names, "Demand": raw_demand, "Fulfilled": shipped_by_dest,
        "Shortage": shortage_values,
        "Service %": np.divide(shipped_by_dest * 100.0, raw_demand, out=np.full(nd, 100.0), where=raw_demand > 0),
        "Priority": priorities, "Due days": due,
    })
    used = x.sum(axis=1)
    supplier_summary = pd.DataFrame({
        "Supplier": s_names, "Effective capacity": effective_capacity, "Allocated": used,
        "Idle capacity": np.maximum(0.0, effective_capacity - used),
        "Utilization %": np.divide(used * 100.0, effective_capacity, out=np.zeros(ns), where=effective_capacity > 0),
        "Status": ["Disabled" if name in disabled else "Available" for name in s_names],
    })
    total_demand = float(raw_demand.sum())
    delivered = float(shipped_by_dest.sum())
    unmet = float(shortage_values.sum())
    carbon = 0.0
    cost = 0.0
    if not route_df.empty:
        carbon = float((route_df["Allocated units"] * route_df["Carbon kg/unit"]).sum())
        cost = float((route_df["Allocated units"] * route_df["Unit cost"]).sum())
    metrics = {
        "total_demand": total_demand, "delivered": delivered, "unmet_demand": unmet,
        "service_level_pct": 100.0 if total_demand <= 0 else delivered * 100.0 / total_demand,
        "modeled_cost": cost, "carbon_proxy_kg": carbon, "weighted_objective": float(result.fun),
        "capacity_total": float(effective_capacity.sum()),
        "local_content_proxy_pct": (
            0.0 if delivered <= 0 else float(
                (route_df["Allocated units"] * route_df["Local share %"]).sum() / delivered
            )
        ) if not route_df.empty else 0.0,
    }
    return {"status": "Optimal", "routes": route_df, "shortages": shortage_df, "supplier_summary": supplier_summary, "metrics": metrics, "message": "Optimal allocation found; any unmet demand is shown explicitly."}


def simulate_disruption_scenarios(
    suppliers: pd.DataFrame, demands: pd.DataFrame, *, iterations: int = 50, seed: int = 17,
    outage_probability: float = 0.12, demand_cv: float = 0.12,
) -> pd.DataFrame:
    """Small, reproducible Monte Carlo stress-test over synthetic supply shocks."""
    rng = np.random.default_rng(int(seed))
    iterations = max(1, min(250, int(iterations)))
    outage_probability = float(np.clip(outage_probability, 0.0, 1.0))
    demand_cv = max(0.0, min(1.0, float(demand_cv)))
    rows = []
    names = suppliers["Supplier"].astype(str).tolist() if "Supplier" in suppliers.columns else []
    for iteration in range(1, iterations + 1):
        disabled = [name for name in names if rng.random() < outage_probability]
        demand_factor = max(0.0, float(rng.normal(1.0, demand_cv)))
        cap_factor = float(np.clip(rng.normal(0.94, 0.10), 0.20, 1.15))
        result = solve_transport_allocation(suppliers, demands, disabled_suppliers=disabled, capacity_scale=cap_factor, demand_scale=demand_factor)
        m = result["metrics"]
        rows.append({
            "Iteration": iteration, "Service %": float(m.get("service_level_pct", 0.0)),
            "Shortage units": float(m.get("unmet_demand", 0.0)),
            "Capacity factor": cap_factor, "Demand factor": demand_factor,
            "Disabled suppliers": ", ".join(disabled) if disabled else "None",
        })
    return pd.DataFrame(rows)


def analyze_closed_loop(
    streams: pd.DataFrame, *, material_capture_pct: float = 75.0, heat_capture_pct: float = 60.0,
    water_capture_pct: float = 65.0, electricity_value_per_kwh: float = 0.30,
    water_value_per_m3: float = 4.0, disposal_cost_per_kg: float = 0.75,
) -> dict[str, Any]:
    df = streams.copy(deep=True)
    fields = ("Recoverable waste kg", "Reuse demand kg", "Heat potential kWh", "Recoverable water m3", "Water reuse demand m3")
    df = _clean_table(df, fields)
    material_capture_pct = float(np.clip(material_capture_pct, 0, 100)) / 100.0
    heat_capture_pct = float(np.clip(heat_capture_pct, 0, 100)) / 100.0
    water_capture_pct = float(np.clip(water_capture_pct, 0, 100)) / 100.0
    available_material = _number(df, "Recoverable waste kg") * material_capture_pct
    reused_material = np.minimum(available_material, _number(df, "Reuse demand kg"))
    residual_material = np.maximum(0.0, _number(df, "Recoverable waste kg") - reused_material)
    available_water = _number(df, "Recoverable water m3") * water_capture_pct
    reused_water = np.minimum(available_water, _number(df, "Water reuse demand m3"))
    residual_water = np.maximum(0.0, _number(df, "Recoverable water m3") - reused_water)
    recovered_heat = _number(df, "Heat potential kWh") * heat_capture_pct
    total_waste = float(_number(df, "Recoverable waste kg").sum())
    total_reused = float(reused_material.sum())
    raw_water = float(_number(df, "Recoverable water m3").sum())
    reused_water_total = float(reused_water.sum())
    recovered_heat_total = float(recovered_heat.sum())
    metrics = {
        "material_circularity_pct": 0.0 if total_waste <= 0 else total_reused * 100.0 / total_waste,
        "material_reused_kg": total_reused, "residual_material_kg": float(residual_material.sum()),
        "water_reuse_pct": 0.0 if raw_water <= 0 else reused_water_total * 100.0 / raw_water,
        "water_reused_m3": reused_water_total, "residual_water_m3": float(residual_water.sum()),
        "recovered_heat_kwh": recovered_heat_total,
        "modeled_value": recovered_heat_total * max(0.0, electricity_value_per_kwh)
        + reused_water_total * max(0.0, water_value_per_m3)
        + total_reused * max(0.0, disposal_cost_per_kg),
        "modeled_disposal_cost": float(residual_material.sum()) * max(0.0, disposal_cost_per_kg),
    }
    result = df.copy()
    result["Captured waste kg"] = available_material
    result["Reused material kg"] = reused_material
    result["Residual material kg"] = residual_material
    result["Recovered heat kWh"] = recovered_heat
    result["Reused water m3"] = reused_water
    result["Residual water m3"] = residual_water
    return {"results": result, "metrics": metrics}


def analyze_urban_mobility(
    junctions: pd.DataFrame, *, car_mode_share_pct: float = 62.0, signal_efficiency_gain_pct: float = 8.0,
    transit_capacity_gain_pct: float = 15.0, demand_shock_pct: float = 0.0,
) -> dict[str, Any]:
    df = junctions.copy(deep=True)
    fields = ("Passenger demand/hr", "Road capacity/hr", "Transit capacity/hr", "Signal efficiency %", "Baseline delay min", "Emissions kg/hr")
    df = _clean_table(df, fields)
    car_share = float(np.clip(car_mode_share_pct, 0, 100)) / 100.0
    demand_factor = max(0.0, 1.0 + float(demand_shock_pct) / 100.0)
    signal_gain = max(0.0, float(signal_efficiency_gain_pct)) / 100.0
    transit_gain = max(0.0, float(transit_capacity_gain_pct)) / 100.0
    demand = _number(df, "Passenger demand/hr") * demand_factor
    road_capacity = _number(df, "Road capacity/hr") * np.clip((_number(df, "Signal efficiency %") / 100.0) + signal_gain, 0.25, 1.25)
    road_capacity = np.maximum(1.0, road_capacity)
    transit_capacity = np.maximum(1.0, _number(df, "Transit capacity/hr") * (1.0 + transit_gain))
    road_flow = demand * car_share
    transit_flow = demand * (1.0 - car_share)
    road_util = road_flow / road_capacity * 100.0
    transit_util = transit_flow / transit_capacity * 100.0
    road_served = np.minimum(road_flow, road_capacity)
    transit_served = np.minimum(transit_flow, transit_capacity)
    excess = np.maximum(0.0, road_flow - road_capacity)
    baseline_delay = _number(df, "Baseline delay min")
    modeled_delay = baseline_delay * (1.0 + np.maximum(0.0, road_util / 100.0 - 0.75) * 2.0)
    emission_baseline = _number(df, "Emissions kg/hr")
    modeled_emissions = emission_baseline * (road_flow / np.maximum(1.0, demand * 0.62))
    result = df.copy()
    result["Demand after shock/hr"] = demand
    result["Road flow/hr"] = road_flow
    result["Transit flow/hr"] = transit_flow
    result["Road utilization %"] = road_util
    result["Transit utilization %"] = transit_util
    result["Modeled queue excess/hr"] = excess
    result["Modeled delay min"] = modeled_delay
    result["Modeled emissions kg/hr"] = modeled_emissions
    total_demand = float(demand.sum())
    served = float((road_served + transit_served).sum())
    metrics = {
        "served_demand_pct": 100.0 if total_demand <= 0 else served * 100.0 / total_demand,
        "served_passengers_hr": served, "demand_passengers_hr": total_demand,
        "average_delay_min": 0.0 if len(result) == 0 else float(modeled_delay.mean()),
        "maximum_road_utilization_pct": 0.0 if len(result) == 0 else float(road_util.max()),
        "maximum_transit_utilization_pct": 0.0 if len(result) == 0 else float(transit_util.max()),
        "modeled_emissions_kg_hr": float(modeled_emissions.sum()),
        "estimated_queue_excess_hr": float(excess.sum()),
    }
    return {"results": result, "metrics": metrics}


def score_asset_health(assets: pd.DataFrame, *, telemetry_dropout_pct: float = 0.0, disruption_pct: float = 0.0, mode: str = "Edge") -> dict[str, Any]:
    df = assets.copy(deep=True)
    fields = ("Vibration mm/s", "Temperature C", "Operating load %", "Availability %", "Alternate capacity %")
    df = _clean_table(df, fields)
    vibration = np.clip(_number(df, "Vibration mm/s") / 12.0, 0.0, 1.5)
    temperature = np.clip((_number(df, "Temperature C") - 20.0) / 100.0, 0.0, 1.5)
    load = np.clip(_number(df, "Operating load %") / 100.0, 0.0, 1.0)
    availability_loss = np.clip(1.0 - _number(df, "Availability %") / 100.0, 0.0, 1.0)
    risk = np.clip(100.0 * (0.30 * vibration / 1.5 + 0.25 * temperature / 1.5 + 0.20 * load + 0.25 * availability_loss), 0.0, 100.0)
    score = 100.0 - risk
    dropout = float(np.clip(telemetry_dropout_pct, 0.0, 100.0))
    disruption = float(np.clip(disruption_pct, 0.0, 100.0)) / 100.0
    alternate = _number(df, "Alternate capacity %") / 100.0
    available = np.clip(_number(df, "Availability %") / 100.0 * (1.0 - disruption) + alternate * disruption, 0.0, 1.0)
    if str(mode).lower() == "edge":
        telemetry_coverage = 100.0 - dropout * 0.55
    else:
        telemetry_coverage = 100.0 - dropout
    result = df.copy()
    result["Modeled risk index %"] = risk
    result["Modeled health index %"] = score
    result["Recovery-adjusted capacity %"] = available * 100.0
    result["Telemetry status"] = "Complete" if dropout <= 0 else ("Partial / buffered" if str(mode).lower() == "edge" else "Degraded")
    metrics = {
        "asset_health_index_pct": 0.0 if len(score) == 0 else float(score.mean()),
        "high_risk_assets": int((risk >= 65).sum()),
        "recovery_capacity_pct": 0.0 if len(available) == 0 else float(available.mean() * 100.0),
        "telemetry_coverage_pct": float(np.clip(telemetry_coverage, 0.0, 100.0)),
    }
    return {"results": result, "metrics": metrics}


def analyze_local_capability(suppliers: pd.DataFrame, demands: pd.DataFrame, *, disabled_suppliers: Sequence[str] = (), capacity_scale: float = 1.0, demand_scale: float = 1.0) -> dict[str, Any]:
    """Aggregate local industrial spare-parts capability by generic part family."""
    supplier_df = suppliers.copy(deep=True)
    demand_df = demands.copy(deep=True)
    if "Part family" not in supplier_df.columns:
        supplier_df["Part family"] = "General industrial spares"
    if "Part family" not in demand_df.columns:
        demand_df["Part family"] = "General industrial spares"
    all_results, all_shortages, all_capacity = [], [], []
    local_content_numerator = 0.0
    delivered_total = 0.0
    for family in sorted(set(supplier_df["Part family"].astype(str)) | set(demand_df["Part family"].astype(str))):
        ss = supplier_df[supplier_df["Part family"].astype(str) == family].copy()
        dd = demand_df[demand_df["Part family"].astype(str) == family].copy()
        if dd.empty:
            continue
        if ss.empty:
            empty_supply = pd.DataFrame(columns=["Supplier", "Capacity", "Unit Cost", "Lead Days", "Risk %", "Carbon kg/unit", "Local Share %"])
            dd_work = dd.rename(columns={"Plant / depot": "Destination", "Monthly demand": "Demand", "Priority": "Priority", "Due days": "Due Days"})
            model = solve_transport_allocation(empty_supply, dd_work)
        else:
            conf = _number(ss, "Qualification confidence %").clip(0, 100)
            mapped = pd.DataFrame({
                "Supplier": ss["Supplier"].astype(str),
                "Capacity": _number(ss, "Monthly capacity") * max(0.0, capacity_scale),
                "Unit Cost": _number(ss, "Unit cost SAR"),
                "Lead Days": _number(ss, "Lead days"),
                "Risk %": 100.0 - conf,
                "Carbon kg/unit": 0.0,
                "Local Share %": _number(ss, "Local content %").clip(0, 100),
            })
            dd_work = pd.DataFrame({
                "Destination": dd["Plant / depot"].astype(str) if "Plant / depot" in dd else dd.index.astype(str),
                "Demand": _number(dd, "Monthly demand") * max(0.0, demand_scale),
                "Priority": _number(dd, "Priority", 1.0).clip(1, 5),
                "Due Days": _number(dd, "Due days"),
            })
            model = solve_transport_allocation(mapped, dd_work, disabled_suppliers=disabled_suppliers, demand_scale=1.0)
        if not model["routes"].empty:
            model["routes"]["Part family"] = family
            # Domestic local-content shares are supplied as editable, not externally certified claims.
            local_content_numerator += float((model["routes"]["Allocated units"] * model["routes"]["Local share %"]).sum())
            delivered_total += float(model["routes"]["Allocated units"].sum())
            all_results.append(model["routes"])
        if not model["shortages"].empty:
            model["shortages"]["Part family"] = family
            all_shortages.append(model["shortages"])
        if not model["supplier_summary"].empty:
            model["supplier_summary"]["Part family"] = family
            all_capacity.append(model["supplier_summary"])
    routes = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    shortages = pd.concat(all_shortages, ignore_index=True) if all_shortages else pd.DataFrame()
    capacity = pd.concat(all_capacity, ignore_index=True) if all_capacity else pd.DataFrame()
    total_demand = 0.0 if shortages.empty else float(shortages["Demand"].sum())
    delivered = 0.0 if routes.empty else float(routes["Allocated units"].sum())
    unmet = 0.0 if shortages.empty else float(shortages["Shortage"].sum())
    metrics = {
        "demand_fulfilled_pct": 100.0 if total_demand <= 0 else delivered * 100.0 / total_demand,
        "monthly_unmet_demand": unmet,
        "local_content_proxy_pct": 0.0 if delivered_total <= 0 else local_content_numerator / delivered_total,
        "supplier_count": int(supplier_df["Supplier"].nunique()) if "Supplier" in supplier_df else len(supplier_df),
        "part_family_coverage": int(len(set(supplier_df["Part family"].astype(str)) & set(demand_df["Part family"].astype(str)))),
        "monthly_repair_capacity": float(_number(supplier_df, "Repair capacity/month").sum()) if "Repair capacity/month" in supplier_df else 0.0,
    }
    return {"routes": routes, "shortages": shortages, "supplier_summary": capacity, "metrics": metrics}


def _default_data(module: str) -> dict[str, pd.DataFrame]:
    if module == GLOBAL_SUPPLY:
        return {
            "suppliers": pd.DataFrame([
                {"Supplier": "Supplier North", "Capacity": 420, "Unit Cost": 14.0, "Lead Days": 4.0, "Risk %": 12, "Carbon kg/unit": 2.1, "Local Share %": 25},
                {"Supplier": "Supplier Central", "Capacity": 360, "Unit Cost": 12.0, "Lead Days": 6.0, "Risk %": 18, "Carbon kg/unit": 1.7, "Local Share %": 40},
                {"Supplier": "Supplier West", "Capacity": 300, "Unit Cost": 16.0, "Lead Days": 3.0, "Risk %": 8, "Carbon kg/unit": 2.5, "Local Share %": 20},
            ]),
            "demands": pd.DataFrame([
                {"Destination": "Distribution Hub A", "Demand": 280, "Priority": 5, "Due Days": 5},
                {"Destination": "Distribution Hub B", "Demand": 350, "Priority": 4, "Due Days": 7},
                {"Destination": "Distribution Hub C", "Demand": 260, "Priority": 3, "Due Days": 8},
            ]),
        }
    if module == HUMANITARIAN:
        return {
            "suppliers": pd.DataFrame([
                {"Supplier": "Relief Depot A", "Capacity": 700, "Unit Cost": 3.2, "Lead Days": 8.0, "Risk %": 10, "Carbon kg/unit": 0.8, "Local Share %": 65},
                {"Supplier": "Relief Depot B", "Capacity": 550, "Unit Cost": 2.7, "Lead Days": 12.0, "Risk %": 15, "Carbon kg/unit": 1.1, "Local Share %": 55},
                {"Supplier": "Regional Stock Hub", "Capacity": 420, "Unit Cost": 4.1, "Lead Days": 5.0, "Risk %": 20, "Carbon kg/unit": 1.4, "Local Share %": 40},
            ]),
            "demands": pd.DataFrame([
                {"Destination": "Relief Region A", "Demand": 420, "Priority": 5, "Due Days": 2},
                {"Destination": "Relief Region B", "Demand": 380, "Priority": 5, "Due Days": 3},
                {"Destination": "Relief Region C", "Demand": 300, "Priority": 3, "Due Days": 5},
            ]),
        }
    if module == CLOSED_LOOP:
        return {
            "streams": pd.DataFrame([
                {"Process": "Heat treatment", "Recoverable waste kg": 280, "Reuse demand kg": 160, "Heat potential kWh": 1800, "Recoverable water m3": 28, "Water reuse demand m3": 18},
                {"Process": "Machining", "Recoverable waste kg": 460, "Reuse demand kg": 290, "Heat potential kWh": 850, "Recoverable water m3": 16, "Water reuse demand m3": 12},
                {"Process": "Packaging", "Recoverable waste kg": 180, "Reuse demand kg": 210, "Heat potential kWh": 250, "Recoverable water m3": 6, "Water reuse demand m3": 4},
                {"Process": "Utilities", "Recoverable waste kg": 90, "Reuse demand kg": 75, "Heat potential kWh": 2200, "Recoverable water m3": 42, "Water reuse demand m3": 30},
            ]),
        }
    if module == URBAN_MOBILITY:
        return {
            "junctions": pd.DataFrame([
                {"Junction": "Corridor A", "Passenger demand/hr": 4200, "Road capacity/hr": 2600, "Transit capacity/hr": 1600, "Signal efficiency %": 78, "Baseline delay min": 14, "Emissions kg/hr": 680},
                {"Junction": "Corridor B", "Passenger demand/hr": 3500, "Road capacity/hr": 2500, "Transit capacity/hr": 1300, "Signal efficiency %": 84, "Baseline delay min": 11, "Emissions kg/hr": 510},
                {"Junction": "Corridor C", "Passenger demand/hr": 2800, "Road capacity/hr": 2100, "Transit capacity/hr": 1400, "Signal efficiency %": 72, "Baseline delay min": 17, "Emissions kg/hr": 430},
                {"Junction": "Freight Link D", "Passenger demand/hr": 1700, "Road capacity/hr": 1800, "Transit capacity/hr": 500, "Signal efficiency %": 88, "Baseline delay min": 8, "Emissions kg/hr": 390},
            ]),
        }
    if module == AKDT:
        return {
            "assets": pd.DataFrame([
                {"Asset": "Conveyor line A", "Vibration mm/s": 4.4, "Temperature C": 68, "Operating load %": 82, "Availability %": 93, "Alternate capacity %": 35},
                {"Asset": "CNC cell B", "Vibration mm/s": 7.6, "Temperature C": 79, "Operating load %": 91, "Availability %": 86, "Alternate capacity %": 42},
                {"Asset": "Packaging cell C", "Vibration mm/s": 2.8, "Temperature C": 56, "Operating load %": 70, "Availability %": 97, "Alternate capacity %": 18},
                {"Asset": "Utility compressor D", "Vibration mm/s": 8.8, "Temperature C": 92, "Operating load %": 88, "Availability %": 81, "Alternate capacity %": 25},
            ]),
            "suppliers": _default_data(GLOBAL_SUPPLY)["suppliers"],
            "demands": _default_data(GLOBAL_SUPPLY)["demands"],
        }
    if module == LSIMS:
        return {
            "suppliers": pd.DataFrame([
                {"Supplier": "Riyadh Precision Works", "Region": "Riyadh", "Part family": "Machined industrial spares", "Monthly capacity": 260, "Lead days": 6, "Qualification confidence %": 94, "Local content %": 100, "Unit cost SAR": 185, "Repair capacity/month": 72},
                {"Supplier": "Jubail Fabrication Hub", "Region": "Jubail", "Part family": "Fabricated industrial spares", "Monthly capacity": 320, "Lead days": 5, "Qualification confidence %": 91, "Local content %": 100, "Unit cost SAR": 148, "Repair capacity/month": 45},
                {"Supplier": "Dammam Components Lab", "Region": "Dammam", "Part family": "Machined industrial spares", "Monthly capacity": 180, "Lead days": 4, "Qualification confidence %": 86, "Local content %": 100, "Unit cost SAR": 210, "Repair capacity/month": 58},
                {"Supplier": "Yanbu Polymer Works", "Region": "Yanbu", "Part family": "Polymer industrial spares", "Monthly capacity": 240, "Lead days": 7, "Qualification confidence %": 89, "Local content %": 100, "Unit cost SAR": 125, "Repair capacity/month": 36},
            ]),
            "demands": pd.DataFrame([
                {"Plant / depot": "Riyadh maintenance center", "Part family": "Machined industrial spares", "Monthly demand": 240, "Priority": 5, "Due days": 8},
                {"Plant / depot": "Eastern Province maintenance center", "Part family": "Fabricated industrial spares", "Monthly demand": 260, "Priority": 4, "Due days": 8},
                {"Plant / depot": "Central utilities maintenance center", "Part family": "Polymer industrial spares", "Monthly demand": 190, "Priority": 3, "Due days": 10},
            ]),
        }
    return {}


def _json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame):
        return []
    normalized = frame.replace([np.inf, -np.inf], np.nan).astype(object)
    normalized = normalized.where(pd.notna(normalized), None)
    return normalized.to_dict("records")


def persist_resilience_run(module: str, username: str, inputs: Mapping[str, pd.DataFrame], results: Mapping[str, Any], db_path: str = "enterprise_full_workspace.db") -> dict[str, str]:
    """Persist an owner-scoped, hashed scenario snapshot in the application database."""
    clean_inputs = {key: _json_records(value) for key, value in inputs.items() if isinstance(value, pd.DataFrame)}
    clean_results = {
        key: _json_records(value) if isinstance(value, pd.DataFrame) else value
        for key, value in results.items()
    }
    payload_inputs = json.dumps(clean_inputs, sort_keys=True, default=str, allow_nan=False, separators=(",", ":"))
    payload_results = json.dumps(clean_results, sort_keys=True, default=str, allow_nan=False, separators=(",", ":"))
    digest = hashlib.sha256(payload_inputs.encode("utf-8")).hexdigest()
    run_id = uuid.uuid4().hex
    stamp = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resilience_scenario_runs (
                run_id TEXT PRIMARY KEY, username TEXT NOT NULL, module TEXT NOT NULL,
                created_at TEXT NOT NULL, input_sha256 TEXT NOT NULL,
                inputs_json TEXT NOT NULL, results_json TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO resilience_scenario_runs VALUES(?,?,?,?,?,?,?)",
            (run_id, str(username or "unknown").casefold(), str(module), stamp, digest, payload_inputs, payload_results),
        )
        conn.commit()
    return {"run_id": run_id, "created_at": stamp, "input_sha256": digest}


def list_resilience_runs(module: str, username: str, db_path: str = "enterprise_full_workspace.db", limit: int = 50) -> pd.DataFrame:
    """Only list snapshots owned by the current user for the current module."""
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resilience_scenario_runs (
                run_id TEXT PRIMARY KEY, username TEXT NOT NULL, module TEXT NOT NULL,
                created_at TEXT NOT NULL, input_sha256 TEXT NOT NULL,
                inputs_json TEXT NOT NULL, results_json TEXT NOT NULL
            )
        """)
        return pd.read_sql_query(
            "SELECT run_id, created_at, input_sha256 FROM resilience_scenario_runs WHERE username=? AND module=? ORDER BY created_at DESC LIMIT ?",
            conn, params=(str(username or "unknown").casefold(), str(module), max(1, min(200, int(limit)))),
        )


def load_resilience_run(run_id: str, module: str, username: str, db_path: str = "enterprise_full_workspace.db") -> dict[str, Any] | None:
    """Load a snapshot only when both owner and immutable module identity match."""
    with sqlite3.connect(db_path, timeout=10) as conn:
        row = conn.execute(
            "SELECT run_id, created_at, input_sha256, inputs_json, results_json FROM resilience_scenario_runs WHERE run_id=? AND username=? AND module=?",
            (str(run_id), str(username or "unknown").casefold(), str(module)),
        ).fetchone()
    if not row:
        return None
    return {
        "run_id": row[0], "created_at": row[1], "input_sha256": row[2],
        "inputs": json.loads(row[3]), "results": json.loads(row[4]),
    }


def _state_key(module: str, name: str) -> str:
    token = hashlib.sha1(str(module).encode("utf-8")).hexdigest()[:10]
    return f"resilience_{token}_{name}"


def _get_editor(st: Any, module: str, name: str, frame: pd.DataFrame) -> pd.DataFrame:
    state_key = _state_key(module, "data_" + name)
    widget_key = _state_key(module, "editor_" + name)
    existing = st.session_state.get(state_key)
    if not isinstance(existing, pd.DataFrame):
        existing = frame.copy(deep=True)
        st.session_state[state_key] = existing
    edited = st.data_editor(existing, key=widget_key, num_rows="dynamic", hide_index=True, use_container_width=True)
    st.session_state[state_key] = edited.copy(deep=True)
    return edited.copy(deep=True)


def _metric(st: Any, columns: Sequence[tuple[str, str]]) -> None:
    if not columns:
        return
    cards = st.columns(min(4, len(columns)))
    for idx, (label, value) in enumerate(columns[:4]):
        cards[idx].metric(label, value)


def _to_num(value: Any, decimals: int = 1) -> str:
    try:
        val = float(value)
        if not math.isfinite(val):
            return "—"
        return f"{val:,.{decimals}f}"
    except Exception:
        return "—"


def _render_transport(module: str, tier: str, username: str, *, humanitarian: bool = False, akdt: bool = False) -> None:
    import streamlit as st
    import plotly.express as px
    import plotly.graph_objects as go
    defaults = _default_data(module)
    if akdt:
        st.markdown("### 1. Industrial asset twin")
        assets = _get_editor(st, module, "assets", defaults["assets"])
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            telemetry_dropout = st.slider("Telemetry gap (%)", 0, 100, 15, 5, key=_state_key(module, "dropout"))
        with c2:
            disruption = st.slider("Capacity disruption (%)", 0, 90, 25, 5, key=_state_key(module, "asset_disruption"))
        with c3:
            edge_mode = st.toggle("Use edge-buffered mode", value=True, key=_state_key(module, "edge_mode"))
        with c4:
            recovery = st.slider("Alternative capacity contribution (%)", 0, 100, 65, 5, key=_state_key(module, "recovery"))
        health = score_asset_health(assets, telemetry_dropout_pct=telemetry_dropout, disruption_pct=disruption, mode="Edge" if edge_mode else "Cloud")
        asset_results = health["results"]
        st.session_state["akdt_asset_health_df"] = asset_results.copy(deep=True)
        _metric(st, [
            ("Asset health index", f"{health['metrics']['asset_health_index_pct']:.1f}%"),
            ("High-risk flags", str(health["metrics"]["high_risk_assets"])),
            ("Recovery-adjusted capacity", f"{health['metrics']['recovery_capacity_pct']:.1f}%"),
            ("Telemetry coverage", f"{health['metrics']['telemetry_coverage_pct']:.1f}%"),
        ])
        st.caption("Edge mode here is a simulated buffering assumption only. No physical asset, network or controller is connected.")
        st.plotly_chart(px.bar(asset_results, x="Asset", y=["Modeled health index %", "Modeled risk index %"], barmode="group", title="Synthetic asset health and risk", template="plotly_white"), use_container_width=True)
        st.markdown("### 2. Alternate-source allocation")
        supplier_defaults = defaults["suppliers"].copy()
        demand_defaults = defaults["demands"].copy()
        col_a, col_b = st.columns(2)
        with col_a:
            suppliers = _get_editor(st, module, "suppliers", supplier_defaults)
        with col_b:
            demands = _get_editor(st, module, "demands", demand_defaults)
        disabled = st.selectbox("Simulated unavailable supplier", ["None"] + suppliers.get("Supplier", pd.Series(dtype=str)).astype(str).tolist(), key=_state_key(module, "disabled_supplier"))
        model = solve_transport_allocation(suppliers, demands, disabled_suppliers=[] if disabled == "None" else [disabled], capacity_scale=max(0.1, 1.0 - disruption / 100.0) * (1.0 + recovery / 100.0 * 0.25))
        st.session_state["akdt_supply_routes_df"] = model["routes"].copy(deep=True)
        st.session_state["akdt_supply_shortages_df"] = model["shortages"].copy(deep=True)
        _render_transport_results(st, px, go, module, model, prefix="AKDT")
        _render_snapshot_actions(st, module, username, {"assets": assets, "suppliers": suppliers, "demands": demands}, {"asset_results": asset_results, "routes": model["routes"], "shortages": model["shortages"]})
        with st.expander("Method, limits and integration readiness"):
            st.write("This is a synthetic industrial digital-twin prototype. Risk scores are transparent heuristics, not trained failure-time models. Edge/cloud is a scenario label, not an active decentralized network.")
            st.write("Future data integration should require explicit connector configuration, validation, audit logging and an approval gate before any production system could act.")
        return

    col_left, col_right = st.columns(2)
    with col_left:
        supplier_title = "Relief depots / stock hubs" if humanitarian else "Suppliers / logistics nodes"
        st.markdown(f"### 1. {supplier_title}")
        suppliers = _get_editor(st, module, "suppliers", defaults["suppliers"])
    with col_right:
        demand_title = "Relief-region demand (kits)" if humanitarian else "Distribution demand"
        st.markdown(f"### 2. {demand_title}")
        demands = _get_editor(st, module, "demands", defaults["demands"])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        capacity_loss = st.slider("Capacity loss (%)", 0, 100, 0, 5, key=_state_key(module, "capacity_loss"))
    with col2:
        demand_shock = st.slider("Demand change (%)", -30, 100, 10 if humanitarian else 0, 5, key=_state_key(module, "demand_shock"))
    with col3:
        lead_weight = st.slider("Lead-time importance", 0.0, 5.0, 0.7 if humanitarian else 0.35, 0.1, key=_state_key(module, "lead_weight"))
    with col4:
        carbon_weight = st.slider("Carbon importance", 0.0, 5.0, 0.3, 0.1, key=_state_key(module, "carbon_weight"))

    disabled_default = "None"
    labels = ["None"] + suppliers.get("Supplier", pd.Series(dtype=str)).astype(str).tolist()
    with st.expander("Additional scenario controls", expanded=False):
        disabled = st.selectbox("Temporarily unavailable supplier / depot", labels, index=0, key=_state_key(module, "disabled"))
        risk_weight = st.slider("Supplier risk importance", 0.0, 5.0, 0.25, 0.1, key=_state_key(module, "risk_weight"))
        cost_weight = st.slider("Direct-cost importance", 0.0, 5.0, 1.0, 0.1, key=_state_key(module, "cost_weight"))
        if humanitarian:
            st.info("Priorities represent relief urgency in this sandbox. Confirmed local needs, access constraints and humanitarian coordination always take precedence over model rankings.")
    model = solve_transport_allocation(
        suppliers, demands, disabled_suppliers=[] if disabled == disabled_default else [disabled],
        capacity_scale=1.0 - capacity_loss / 100.0, demand_scale=max(0.0, 1.0 + demand_shock / 100.0),
        cost_weight=cost_weight, lead_weight=lead_weight, risk_weight=risk_weight, carbon_weight=carbon_weight,
    )
    if humanitarian:
        st.session_state["humanitarian_allocations_df"] = model["routes"].copy(deep=True)
        st.session_state["humanitarian_gaps_df"] = model["shortages"].copy(deep=True)
        st.session_state["humanitarian_depot_utilization_df"] = model["supplier_summary"].copy(deep=True)
    else:
        st.session_state["resilience_global_supply_routes_df"] = model["routes"].copy(deep=True)
        st.session_state["resilience_global_supply_shortages_df"] = model["shortages"].copy(deep=True)
        st.session_state["resilience_global_supply_capacity_df"] = model["supplier_summary"].copy(deep=True)
    _render_transport_results(st, px, go, module, model, prefix="Relief" if humanitarian else "Network")
    run_tab, method_tab = st.tabs(["Scenario robustness", "Method & assumptions"])
    with run_tab:
        left, right = st.columns(2)
        with left:
            reps = st.slider("Monte Carlo trials", 10, 150, 40, 10, key=_state_key(module, "mc_reps"))
            outage_p = st.slider("Supplier outage probability (%)", 0, 60, 12, 2, key=_state_key(module, "mc_outage")) / 100.0
            demand_cv = st.slider("Demand uncertainty (%)", 0, 50, 12, 2, key=_state_key(module, "mc_demand")) / 100.0
            seed = st.number_input("Reproducible random seed", min_value=0, max_value=999999, value=17, step=1, key=_state_key(module, "mc_seed"))
        with right:
            if st.button("Run stress test", type="primary", key=_state_key(module, "mc_run")):
                sim = simulate_disruption_scenarios(suppliers, demands, iterations=int(reps), seed=int(seed), outage_probability=outage_p, demand_cv=demand_cv)
                st.session_state[_state_key(module, "mc_results")] = sim
            sim = st.session_state.get(_state_key(module, "mc_results"))
            if isinstance(sim, pd.DataFrame) and not sim.empty:
                st.metric("Median modeled service", f"{sim['Service %'].median():.1f}%")
                st.metric("10th percentile service", f"{sim['Service %'].quantile(0.10):.1f}%")
                st.plotly_chart(px.histogram(sim, x="Service %", nbins=20, title="Modeled service under random shocks", template="plotly_white"), use_container_width=True)
                st.download_button("Download stress-test CSV", sim.to_csv(index=False).encode("utf-8"), file_name="resilience_stress_test.csv", mime="text/csv", key=_state_key(module, "mc_csv"))
            else:
                st.caption("Run the stress test to create a reproducible uncertainty distribution.")
    with method_tab:
        st.write("The allocation uses a linear transportation model with supply-capacity limits, destination demand balance and explicit shortage variables. Route scores blend user-weighted cost, lead days, supplier risk and a carbon-intensity proxy.")
        st.write("Monte Carlo trials vary demand and available capacity and may disable suppliers. They are synthetic sensitivity tests; they do not represent a calibrated forecast, live availability or a guarantee that all demand can be fulfilled.")
        if humanitarian:
            st.warning("Humanitarian aid quantities and urgency weights must be validated with qualified local coordinators. This screen does not determine real deployment routes or replace safety and access assessments.")
    _render_snapshot_actions(st, module, username, {"suppliers": suppliers, "demands": demands}, {"routes": model["routes"], "shortages": model["shortages"], "supplier_summary": model["supplier_summary"]})


def _render_transport_results(st: Any, px: Any, go: Any, module: str, model: Mapping[str, Any], prefix: str) -> None:
    metrics = model.get("metrics", {})
    _metric(st, [
        ("Modeled service", f"{float(metrics.get('service_level_pct', 0.0)):.1f}%"),
        ("Unmet demand", _to_num(metrics.get("unmet_demand", 0.0), 1)),
        ("Modeled direct cost", _to_num(metrics.get("modeled_cost", 0.0), 0)),
        ("Carbon proxy", f"{_to_num(metrics.get('carbon_proxy_kg', 0.0), 0)} kg"),
    ])
    st.caption(f"Solver: {model.get('status', 'Unknown')}. Model outputs are estimates from the editable assumptions, not verified operating outcomes.")
    routes = model.get("routes", pd.DataFrame())
    shortages = model.get("shortages", pd.DataFrame())
    utilization = model.get("supplier_summary", pd.DataFrame())
    tab_a, tab_b, tab_c = st.tabs(["Allocation flow", "Capacity & service", "Detailed results"])
    with tab_a:
        if routes.empty:
            st.warning("No positive allocations were returned. Check capacity, demand and table values.")
        else:
            fig = px.bar(routes, x="Destination", y="Allocated units", color="Supplier", barmode="group", title=f"{prefix}: allocation by destination", template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
            labels = list(dict.fromkeys(routes["Supplier"].astype(str).tolist() + routes["Destination"].astype(str).tolist()))
            index = {name: i for i, name in enumerate(labels)}
            fig_sankey = go.Figure(data=[go.Sankey(
                node={"label": labels, "pad": 14, "thickness": 16},
                link={
                    "source": [index[x] for x in routes["Supplier"]],
                    "target": [index[x] for x in routes["Destination"]],
                    "value": [max(0.01, float(x)) for x in routes["Allocated units"]],
                    "label": [f"{float(x):.1f} units" for x in routes["Allocated units"]],
                },
            )])
            fig_sankey.update_layout(title="Abstract supplier-to-destination flow (not a geographic map)", font_size=11)
            st.plotly_chart(fig_sankey, use_container_width=True)
    with tab_b:
        if not utilization.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(px.bar(utilization, x="Supplier", y="Utilization %", color="Status" if "Status" in utilization else None, title="Supplier utilization", template="plotly_white"), use_container_width=True)
            with c2:
                if not shortages.empty:
                    st.plotly_chart(px.bar(shortages, x="Destination", y=["Fulfilled", "Shortage"], barmode="stack", title="Demand fulfilment and visible shortfall", template="plotly_white"), use_container_width=True)
            st.dataframe(utilization, use_container_width=True, hide_index=True)
        if not shortages.empty:
            st.dataframe(shortages, use_container_width=True, hide_index=True)
    with tab_c:
        st.markdown("**Allocated route ledger**")
        st.dataframe(routes, use_container_width=True, hide_index=True)
        st.download_button("Download allocation CSV", routes.to_csv(index=False).encode("utf-8"), file_name="resilience_allocations.csv", mime="text/csv", key=_state_key(module, "allocation_csv"))
        st.download_button("Download demand / shortage CSV", shortages.to_csv(index=False).encode("utf-8"), file_name="resilience_demand_status.csv", mime="text/csv", key=_state_key(module, "shortage_csv"))
        st.download_button("Download supplier summary CSV", utilization.to_csv(index=False).encode("utf-8"), file_name="resilience_supplier_summary.csv", mime="text/csv", key=_state_key(module, "capacity_csv"))


def _render_closed_loop(module: str, username: str) -> None:
    import streamlit as st
    import plotly.express as px
    import plotly.graph_objects as go
    streams = _get_editor(st, module, "streams", _default_data(module)["streams"])
    c1, c2, c3 = st.columns(3)
    with c1:
        material = st.slider("Material capture efficiency (%)", 0, 100, 75, 5, key=_state_key(module, "material_capture"))
    with c2:
        heat = st.slider("Heat recovery efficiency (%)", 0, 100, 60, 5, key=_state_key(module, "heat_capture"))
    with c3:
        water = st.slider("Water recovery efficiency (%)", 0, 100, 65, 5, key=_state_key(module, "water_capture"))
    c4, c5, c6 = st.columns(3)
    with c4:
        energy_price = st.number_input("Electricity value (SAR/kWh)", min_value=0.0, max_value=100000.0, value=0.30, step=0.05, key=_state_key(module, "energy_value"))
    with c5:
        water_price = st.number_input("Water value (SAR/m³)", min_value=0.0, max_value=100000.0, value=4.0, step=0.5, key=_state_key(module, "water_value"))
    with c6:
        disposal_cost = st.number_input("Waste disposal cost (SAR/kg)", min_value=0.0, max_value=100000.0, value=0.75, step=0.05, key=_state_key(module, "disposal_cost"))
    analysis = analyze_closed_loop(streams, material_capture_pct=material, heat_capture_pct=heat, water_capture_pct=water, electricity_value_per_kwh=energy_price, water_value_per_m3=water_price, disposal_cost_per_kg=disposal_cost)
    st.session_state["industrial_symbiosis_result_df"] = analysis["results"].copy(deep=True)
    m = analysis["metrics"]
    _metric(st, [
        ("Modeled material circularity", f"{m['material_circularity_pct']:.1f}%"),
        ("Material reused", f"{m['material_reused_kg']:,.1f} kg"),
        ("Recovered heat", f"{m['recovered_heat_kwh']:,.1f} kWh"),
        ("Modeled value opportunity", f"SAR {m['modeled_value']:,.0f}"),
    ])
    st.caption("Circularity and value are scenario estimates. They exclude many site-specific energy, treatment, quality, CAPEX and permitting constraints.")
    tabs = st.tabs(["Material & utility flows", "Results table", "Method & assumptions"])
    with tabs[0]:
        cols = st.columns(2)
        with cols[0]:
            st.plotly_chart(px.bar(analysis["results"], x="Process", y=["Reused material kg", "Residual material kg"], barmode="stack", title="Recoverable material: reuse vs residual", template="plotly_white"), use_container_width=True)
            st.plotly_chart(px.bar(analysis["results"], x="Process", y="Recovered heat kWh", title="Heat recovery potential", template="plotly_white"), use_container_width=True)
        with cols[1]:
            st.plotly_chart(px.bar(analysis["results"], x="Process", y=["Reused water m3", "Residual water m3"], barmode="stack", title="Water recovery: reuse vs residual", template="plotly_white"), use_container_width=True)
            labels = ["Recoverable material", "Reuse loop", "Residual material", "Recoverable heat", "Recovered heat", "Water reclaimed"]
            fig = go.Figure(go.Sankey(
                node={"label": labels},
                link={"source": [0, 0, 3, 4], "target": [1, 2, 4, 5], "value": [
                    max(0.01, m["material_reused_kg"]), max(0.01, m["residual_material_kg"]),
                    max(0.01, m["recovered_heat_kwh"]), max(0.01, m["water_reused_m3"]),
                ]},
            ))
            fig.update_layout(title="Conceptual circular-flow summary (separate units; visual only)")
            st.plotly_chart(fig, use_container_width=True)
    with tabs[1]:
        st.dataframe(analysis["results"], use_container_width=True, hide_index=True)
        st.download_button("Download circularity ledger", analysis["results"].to_csv(index=False).encode("utf-8"), file_name="industrial_symbiosis_ledger.csv", mime="text/csv", key=_state_key(module, "ledger_csv"))
    with tabs[2]:
        st.write("Per process, reusable material is the smaller of waste multiplied by capture efficiency and downstream reuse demand. Captured heat and water are scenario estimates, not measured energy or water balances.")
        st.write("The economic estimate is a simple gross opportunity based on the rates you provide. It is not net savings, because treatment costs, contamination, transport, capital costs, yield loss and quality approvals have not been modeled.")
        st.write("Zero waste / net-zero is not guaranteed. Validate the full material and energy balance and local environmental requirements before acting.")
    _render_snapshot_actions(st, module, username, {"streams": streams}, {"results": analysis["results"], "metrics": m})


def _render_urban_mobility(module: str, username: str) -> None:
    import streamlit as st
    import plotly.express as px
    junctions = _get_editor(st, module, "junctions", _default_data(module)["junctions"])
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        car_share = st.slider("Private vehicle mode share (%)", 0, 100, 62, 5, key=_state_key(module, "car_share"))
    with c2:
        signal_gain = st.slider("Signal-efficiency uplift (%)", 0, 25, 8, 1, key=_state_key(module, "signal_gain"))
    with c3:
        transit_gain = st.slider("Transit capacity uplift (%)", 0, 100, 15, 5, key=_state_key(module, "transit_gain"))
    with c4:
        demand_shock = st.slider("Demand peak / dip (%)", -30, 100, 0, 5, key=_state_key(module, "mobility_shock"))
    analysis = analyze_urban_mobility(junctions, car_mode_share_pct=car_share, signal_efficiency_gain_pct=signal_gain, transit_capacity_gain_pct=transit_gain, demand_shock_pct=demand_shock)
    m, result = analysis["metrics"], analysis["results"]
    st.session_state["urban_mobility_result_df"] = result.copy(deep=True)
    _metric(st, [
        ("Demand served", f"{m['served_demand_pct']:.1f}%"),
        ("Average modeled delay", f"{m['average_delay_min']:.1f} min"),
        ("Peak road utilization", f"{m['maximum_road_utilization_pct']:.1f}%"),
        ("Emissions proxy", f"{m['modeled_emissions_kg_hr']:,.0f} kg/hr"),
    ])
    st.caption("This workspace uses aggregated synthetic corridor data. It is not connected to live traffic signals, transit schedules, road closures or emergency dispatch.")
    tabs = st.tabs(["Congestion & capacity", "Mode and emissions", "Results & method"])
    with tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.bar(result, x="Junction", y=["Road utilization %", "Transit utilization %"], barmode="group", title="Road and transit capacity utilization", template="plotly_white"), use_container_width=True)
        with c2:
            st.plotly_chart(px.bar(result, x="Junction", y=["Baseline delay min", "Modeled delay min"], barmode="group", title="Baseline vs modeled delay", template="plotly_white"), use_container_width=True)
    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.bar(result, x="Junction", y="Modeled queue excess/hr", title="Modeled excess demand proxy", template="plotly_white"), use_container_width=True)
        with c2:
            st.plotly_chart(px.bar(result, x="Junction", y="Modeled emissions kg/hr", title="Modeled emissions proxy by corridor", template="plotly_white"), use_container_width=True)
    with tabs[2]:
        st.dataframe(result, use_container_width=True, hide_index=True)
        st.download_button("Download mobility scenario CSV", result.to_csv(index=False).encode("utf-8"), file_name="urban_mobility_scenario.csv", mime="text/csv", key=_state_key(module, "mobility_csv"))
        st.write("The model splits observed synthetic passenger demand using the chosen mode share, estimates road and transit utilization, and applies simple capacity-sensitive delay and emissions proxies. Calibration against local traffic, signal timing and transit data is required before policy decisions.")
    _render_snapshot_actions(st, module, username, {"junctions": junctions}, {"results": result, "metrics": m})


def _render_l_sims(module: str, username: str) -> None:
    import streamlit as st
    import plotly.express as px
    defaults = _default_data(module)
    left, right = st.columns(2)
    with left:
        st.markdown("### Domestic industrial supplier capability")
        suppliers = _get_editor(st, module, "suppliers", defaults["suppliers"])
    with right:
        st.markdown("### Aggregated spare-part demand")
        demands = _get_editor(st, module, "demands", defaults["demands"])
    c1, c2, c3 = st.columns(3)
    with c1:
        capacity_scale = st.slider("Available local capacity (%)", 0, 130, 100, 5, key=_state_key(module, "local_capacity")) / 100.0
    with c2:
        demand_scale = st.slider("Monthly industrial demand (%)", 50, 180, 100, 5, key=_state_key(module, "local_demand")) / 100.0
    with c3:
        conf_floor = st.slider("Qualification-confidence filter (%)", 0, 100, 70, 5, key=_state_key(module, "confidence_floor"))
    excluded = suppliers.loc[_number(suppliers, "Qualification confidence %") < conf_floor, "Supplier"].astype(str).tolist() if "Qualification confidence %" in suppliers else []
    analysis = analyze_local_capability(suppliers, demands, disabled_suppliers=excluded, capacity_scale=capacity_scale, demand_scale=demand_scale)
    st.session_state["lsims_local_allocations_df"] = analysis["routes"].copy(deep=True)
    st.session_state["lsims_local_gaps_df"] = analysis["shortages"].copy(deep=True)
    st.session_state["lsims_supplier_capacity_df"] = analysis["supplier_summary"].copy(deep=True)
    m = analysis["metrics"]
    _metric(st, [
        ("Monthly industrial demand fulfilled", f"{m['demand_fulfilled_pct']:.1f}%"),
        ("Unmet industrial demand", f"{m['monthly_unmet_demand']:,.1f} units"),
        ("Local-content proxy", f"{m['local_content_proxy_pct']:.1f}%"),
        ("Repair capacity / month", f"{m['monthly_repair_capacity']:,.0f} units"),
    ])
    st.caption("Research/planning sandbox for aggregated domestic industrial spare-part families and repair capability. It does not recommend operational deployment actions.")
    tabs = st.tabs(["Capability allocation", "Supplier confidence & capacity", "Data & assumptions"])
    with tabs[0]:
        if not analysis["routes"].empty:
            st.plotly_chart(px.bar(analysis["routes"], x="Destination", y="Allocated units", color="Supplier", barmode="group", title="Modeled local allocation by plant / depot", template="plotly_white"), use_container_width=True)
            st.dataframe(analysis["routes"], use_container_width=True, hide_index=True)
        else:
            st.info("No allocations were produced. Check part-family labels and available domestic capacity.")
        if not analysis["shortages"].empty:
            st.plotly_chart(px.bar(analysis["shortages"], x="Destination", y="Shortage", color="Part family", title="Industrial part-family capability gaps", template="plotly_white"), use_container_width=True)
            st.dataframe(analysis["shortages"], use_container_width=True, hide_index=True)
    with tabs[1]:
        st.plotly_chart(px.bar(suppliers, x="Supplier", y=["Monthly capacity", "Repair capacity/month"], barmode="group", color_discrete_sequence=None, title="Domestic production and repair capacity", template="plotly_white"), use_container_width=True)
        if "Qualification confidence %" in suppliers:
            st.plotly_chart(px.bar(suppliers, x="Supplier", y="Qualification confidence %", title="User-entered qualification confidence", template="plotly_white"), use_container_width=True)
    with tabs[2]:
        st.write("Demand is matched by the editable, generic industrial spare-part family. A supplier from a different family cannot fill that demand in this model. Capacity, cost, confidence and local-content values are user inputs and require evidence.")
        st.dataframe(analysis["supplier_summary"], use_container_width=True, hide_index=True)
        st.download_button("Download local capability allocation CSV", analysis["routes"].to_csv(index=False).encode("utf-8"), file_name="lsims_local_capability.csv", mime="text/csv", key=_state_key(module, "lsims_routes_csv"))
        st.download_button("Download capability gap CSV", analysis["shortages"].to_csv(index=False).encode("utf-8"), file_name="lsims_capability_gaps.csv", mime="text/csv", key=_state_key(module, "lsims_gaps_csv"))
    _render_snapshot_actions(st, module, username, {"suppliers": suppliers, "demands": demands}, {"routes": analysis["routes"], "shortages": analysis["shortages"], "supplier_summary": analysis["supplier_summary"]})


def _render_snapshot_actions(st: Any, module: str, username: str, inputs: Mapping[str, pd.DataFrame], results: Mapping[str, Any]) -> None:
    import plotly.express as px
    st.markdown("---")
    ptab, htab = st.tabs(["Save & export this run", "Saved runs"])
    with ptab:
        st.caption("Save an owner-scoped snapshot of your current input tables and modeled results. Saving records evidence; it does not verify a real-world outcome.")
        if st.button("Save scenario snapshot", type="primary", key=_state_key(module, "save_snapshot")):
            try:
                frames = {k: v for k, v in results.items() if isinstance(v, pd.DataFrame)}
                values = {k: v for k, v in results.items() if not isinstance(v, pd.DataFrame)}
                record = persist_resilience_run(module, username, inputs, {**frames, "metrics": values.get("metrics", values)})
                st.session_state[_state_key(module, "last_saved_run")] = record
                st.success(f"Saved run {record['run_id'][:12]} · SHA-256 {record['input_sha256'][:16]}…")
            except Exception as exc:
                st.error(f"Snapshot was not saved: {type(exc).__name__}: {exc}")
        last = st.session_state.get(_state_key(module, "last_saved_run"))
        if isinstance(last, dict):
            st.code(f"Run ID: {last['run_id']}\nInput SHA-256: {last['input_sha256']}\nCreated: {last['created_at']}")
        export_payload = {"module": module, "username": str(username or "unknown"), "assumptions": "Editable synthetic scenario; not a verified outcome.", "inputs": {k: _json_records(v) for k, v in inputs.items()}, "results": {k: _json_records(v) if isinstance(v, pd.DataFrame) else v for k, v in results.items()}}
        data = json.dumps(export_payload, indent=2, default=str, allow_nan=False).encode("utf-8")
        st.download_button("Download full run bundle (JSON)", data=data, file_name=f"{_state_key(module, 'run')}.json", mime="application/json", key=_state_key(module, "run_json"))
        primary_frame = next((v for v in results.values() if isinstance(v, pd.DataFrame)), pd.DataFrame())
        try:
            from shoir_module_customization import render_module_customization
            render_module_customization(module, username, primary_frame)
        except Exception as exc:
            st.caption(f"Optional personalization panel unavailable for this run ({type(exc).__name__}).")
    with htab:
        try:
            history = list_resilience_runs(module, username)
            if history.empty:
                st.info("No saved snapshots for this module and user yet.")
            else:
                st.dataframe(history, use_container_width=True, hide_index=True)
                st.download_button("Download saved-run index", history.to_csv(index=False).encode("utf-8"), file_name="resilience_saved_runs.csv", mime="text/csv", key=_state_key(module, "history_csv"))
                selected_run = st.selectbox("Snapshot to inspect", history["run_id"].astype(str).tolist(), format_func=lambda value: value[:12], key=_state_key(module, "inspect_run_id"))
                if st.button("Inspect selected snapshot", key=_state_key(module, "inspect_run_button")):
                    snapshot = load_resilience_run(selected_run, module, username)
                    if snapshot is None:
                        st.error("Snapshot not found for this user and module.")
                    else:
                        st.json({"run_id": snapshot["run_id"], "created_at": snapshot["created_at"], "input_sha256": snapshot["input_sha256"]})
                        with st.expander("Saved input tables", expanded=True):
                            st.json(snapshot["inputs"])
                        with st.expander("Saved modeled results", expanded=True):
                            st.json(snapshot["results"])
                        st.download_button("Download selected snapshot JSON", json.dumps(snapshot, indent=2, default=str).encode("utf-8"), file_name=f"resilience_snapshot_{snapshot['run_id'][:12]}.json", mime="application/json", key=_state_key(module, "inspect_snapshot_json"))
        except Exception as exc:
            st.warning(f"Run history unavailable: {type(exc).__name__}: {exc}")


def render_resilience_module(module: str, tier: str, username: str) -> None:
    """Entry point used by the Shoir-IE specialist module router."""
    import streamlit as st
    if module not in RESILIENCE_MODULES:
        st.error("Unknown resilience workspace. Choose a module from the catalog.")
        return
    try:
        from industrial_platform import tier_allows
        required = MODULE_DEFINITIONS[module]["tier"]
    except Exception as exc:
        st.error("Subscription access could not be verified, so this workspace remains locked.")
        st.caption(f"Access check diagnostic: {type(exc).__name__}")
        return
    if not tier_allows(tier, required):
        st.warning(f"🔒 {module} requires {required}. Current tier: {tier}.")
        return

    info = MODULE_DEFINITIONS[module]
    from shoir_module_customization import get_module_profile
    profile = get_module_profile(st.session_state, module, username)
    display_title = str(profile.get("display_name") or module)
    st.title(info["category"] + " | " + display_title)
    st.write(info["when"])
    project_context = " · ".join(str(profile.get(key) or "").strip() for key in ("project_name", "site_name", "owner_team") if str(profile.get(key) or "").strip())
    if project_context:
        st.caption("Workspace context: " + project_context)
    st.caption("Starter workspace uses editable synthetic data. All outputs are modeled estimates until validated against approved, dated source data.")
    with st.expander("Quick start", expanded=False):
        st.write("1. Review the sample values and replace them with your approved project data. 2. Change the scenario controls. 3. Review graphs and shortages, then export or save a snapshot. 4. Document assumptions before sharing.")
        st.write("Data freshness: sample datasets included with the application. Live integrations are not configured by this module.")
    if module == GLOBAL_SUPPLY:
        _render_transport(module, tier, username)
    elif module == HUMANITARIAN:
        _render_transport(module, tier, username, humanitarian=True)
    elif module == CLOSED_LOOP:
        _render_closed_loop(module, username)
    elif module == URBAN_MOBILITY:
        _render_urban_mobility(module, username)
    elif module == AKDT:
        _render_transport(module, tier, username, akdt=True)
    elif module == LSIMS:
        _render_l_sims(module, username)

