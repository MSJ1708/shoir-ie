"""Investor-grade Industrial Control Center demo.

This module deliberately keeps the incubator story in one place:
Plant Risk -> Digital Thread -> Predictive Maintenance -> Simulation
-> Multi-Objective Optimization -> Decision -> ROI -> Verification.

The scenario is synthetic/demo data. It is designed to demonstrate workflow,
evidence traceability and business impact without pretending that live plant
data exists when it does not.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from shoir_enterprise_layer import (
    build_control_tower_health,
    save_twin_snapshot,
    save_twin_scenario,
    twin_what_if,
    twin_replay,
    list_twin_scenarios,
)
from shoir_optimization import pareto_weight_sweep
from shoir_enterprise_services import record_workspace_artifact


DEMO_KEY = "investor_control_center"
STAGES = [
    ("risk", "🚨", "Plant Risk"),
    ("thread", "🧬", "Digital Thread"),
    ("maintenance", "🛠️", "Predictive Maintenance"),
    ("simulation", "🧪", "Simulation"),
    ("optimization", "⚖️", "Optimization"),
    ("decision", "🎯", "Decision"),
    ("impact", "💰", "ROI / Impact"),
    ("verification", "✅", "Verified Result"),
]


def _state(key: str, default: Any = None) -> Any:
    return st.session_state.get(f"{DEMO_KEY}_{key}", default)


def _set(key: str, value: Any) -> None:
    st.session_state[f"{DEMO_KEY}_{key}"] = value


def _default_inputs() -> dict[str, float]:
    return {
        "production_oee": 76.0,
        "quality_yield": 96.2,
        "maintenance_risk": 90.0,
        "inventory_cover": 1.4,
        "order_protection": 86.0,
        "demand_multiplier": 1.0,
        "energy_kwh_unit": 1.48,
        "scrap_pct": 3.8,
        "maintenance_backlog_h": 42.0,
        "supplier_delay_h": 18.0,
        "overtime_sar": 86000.0,
    }


def _plant_from_inputs(values: dict[str, float]) -> pd.DataFrame:
    production = float(values["production_oee"])
    quality = float(values["quality_yield"])
    maintenance = float(values["maintenance_risk"])
    inventory = float(values["inventory_cover"])
    order = float(values["order_protection"])
    energy = float(values["energy_kwh_unit"])
    scrap = float(values.get("scrap_pct", 3.8))
    backlog = float(values.get("maintenance_backlog_h", 42.0))
    supplier_delay = float(values.get("supplier_delay_h", 18.0))

    quality_health = float(np.clip(100.0 - scrap * 12.0, 25.0, 100.0))
    inventory_health = float(np.clip(inventory / 5.0 * 100.0, 20.0, 100.0))
    energy_health = float(np.clip(100.0 - max(0.0, energy - 1.0) * 120.0, 25.0, 100.0))
    workforce_health = float(np.clip(100.0 - backlog * 1.2, 25.0, 100.0))
    supply_health = float(np.clip(100.0 - supplier_delay * 2.0, 20.0, 100.0))
    rows = [
        ["Production", round(production, 1), "Attention" if production < 88 else "Healthy", "Line 2 OEE", f"{production:.0f}% OEE"],
        ["Supply", round(supply_health, 1), "At Risk" if supply_health < 70 else "Healthy", "Supplier delay", f"{supplier_delay:.0f} h late"],
        ["Quality", round(quality_health, 1), "Critical" if scrap >= 4.0 else "Review", "Scrap rate", f"+{scrap:.1f}%"],
        ["Maintenance", round(100.0 - maintenance * 0.18, 1), "Critical" if maintenance >= 75 else ("Review" if maintenance >= 50 else "Healthy"), "Compressor C-204", f"{maintenance:.0f}% risk"],
        ["Inventory", round(inventory_health, 1), "At Risk" if inventory < 2 else "Review", "Motor bearings", f"{inventory:.1f} days cover"],
        ["Workforce", round(workforce_health, 1), "At Risk" if backlog >= 30 else "Healthy", "Maintenance backlog", f"{backlog:.0f} h"],
        ["Energy", round(energy_health, 1), "At Risk" if energy > 1.40 else "Healthy", "Specific energy", f"{energy:.2f} kWh/unit"],
        ["Customer Order", round(order, 1), "At Risk" if order < 90 else "Protected", "72h order", f"{order:.0f}% protected"],
    ]
    return pd.DataFrame(rows, columns=["Area", "Health %", "Status", "Primary Signal", "KPI"])


def _ensure_defaults() -> None:
    if _state("started") is None:
        _set("started", False)
    if _state("completed") is None:
        _set("completed", [])
    if _state("inputs") is None:
        _set("inputs", _default_inputs())
    if _state("plant") is None:
        _set("plant", _plant_from_inputs(_state("inputs")))


def _reset_flow_only() -> None:
    for key in ("started", "completed", "risk", "thread", "tower", "maintenance",
                "simulation", "optimization", "decision", "impact", "verification",
                "rescue_case", "decision_persisted", "twin_persistence_warning", "decision_persistence_warning"):
        st.session_state.pop(f"{DEMO_KEY}_{key}", None)
    for key in list(st.session_state.keys()):
        if str(key).startswith(f"{DEMO_KEY}_input_"):
            st.session_state.pop(key, None)
    _set("started", False)
    _set("completed", [])


def _apply_inputs(values: dict[str, float], username: str, preset_name: str = "") -> None:
    _set("inputs", {k: float(v) for k, v in values.items()})
    _set("active_preset", str(preset_name or ""))
    _set("plant", _plant_from_inputs(_state("inputs")))
    _reset_flow_only()
    _set("active_preset", str(preset_name or ""))
    try:
        save_twin_scenario(
            username,
            "Investor Demo · Custom Plant State",
            _state("inputs"),
            parent_name="Live",
            notes="User-adjusted synthetic demo assumptions.",
        )
    except Exception:
        pass


def _preset(name: str) -> dict[str, float]:
    base = _default_inputs()
    presets = {
        "Compressor deterioration": {
            **base,
            "production_oee": 76.0,
            "maintenance_risk": 90.0,
            "inventory_cover": 1.4,
            "order_protection": 86.0,
            "energy_kwh_unit": 1.48,
        },
        "Demand surge": {
            **base,
            "production_oee": 84.0,
            "quality_yield": 96.0,
            "maintenance_risk": 68.0,
            "inventory_cover": 2.0,
            "order_protection": 78.0,
            "demand_multiplier": 1.20,
            "energy_kwh_unit": 1.36,
        },
        "Flagship 72-hour crisis": {
            **base,
            "production_oee": 76.0,
            "quality_yield": 96.2,
            "maintenance_risk": 90.0,
            "inventory_cover": 1.4,
            "order_protection": 86.0,
            "demand_multiplier": 1.0,
            "energy_kwh_unit": 1.48,
            "scrap_pct": 3.8,
            "maintenance_backlog_h": 42.0,
            "supplier_delay_h": 18.0,
            "overtime_sar": 86000.0,
        },
        "Stable recovery": {
            **base,
            "production_oee": 93.0,
            "quality_yield": 98.2,
            "maintenance_risk": 24.0,
            "inventory_cover": 4.5,
            "order_protection": 98.0,
            "demand_multiplier": 1.00,
            "energy_kwh_unit": 1.16,
        },
    }
    return presets.get(name, base)


def _mark(stage: str) -> None:
    completed = list(_state("completed", []))
    if stage not in completed:
        completed.append(stage)
        _set("completed", completed)


def _is_done(stage: str) -> bool:
    return stage in _state("completed", [])


def _reset() -> None:
    prefix = f"{DEMO_KEY}_"
    for key in list(st.session_state.keys()):
        if str(key).startswith(prefix):
            st.session_state.pop(key, None)


def _pretty_number(value: float, digits: int = 0) -> str:
    return f"{float(value):,.{digits}f}"


def _format_sar(value: float) -> str:
    return f"SAR {_pretty_number(value)}"


def _risk_analysis(inputs: dict[str, float] | None = None) -> pd.DataFrame:
    v = inputs or _state("inputs", _default_inputs())
    production_risk = float(np.clip(100.0 - v["production_oee"], 5.0, 95.0))
    inventory_risk = float(np.clip(75.0 - v["inventory_cover"] * 8.0, 10.0, 90.0))
    quality_risk = float(np.clip((100.0 - v["quality_yield"]) * 14.0 + v.get("scrap_pct", 0.0) * 2.0, 5.0, 90.0))
    supply_risk = float(np.clip(v.get("supplier_delay_h", 0.0) * 2.2, 5.0, 95.0))
    workforce_risk = float(np.clip(v.get("maintenance_backlog_h", 0.0) * 1.5, 5.0, 95.0))
    energy_risk = float(np.clip(max(0.0, v.get("energy_kwh_unit", 1.2) - 1.15) * 55.0, 5.0, 90.0))
    return pd.DataFrame(
        [
            ["C-204", "Compressor", round(v["maintenance_risk"], 1), "Vibration + temperature trend", "Critical" if v["maintenance_risk"] >= 75 else "Medium", "Maintenance"],
            ["LINE-02", "Production line", round(production_risk, 1), "OEE deterioration + stops", "High" if production_risk >= 20 else "Medium", "Production"],
            ["INV-MTR", "Bearing stock", round(inventory_risk, 1), "Low critical-spares cover", "High" if inventory_risk >= 60 else "Medium", "Inventory"],
            ["Q-07", "Quality signal", round(quality_risk, 1), "Scrap / process drift", "High" if quality_risk >= 35 else "Medium", "Quality"],
            ["SUP-18", "Supplier delivery", round(supply_risk, 1), "Late critical-part delivery", "High" if supply_risk >= 40 else "Medium", "Supply"],
            ["MW-BACKLOG", "Maintenance workforce", round(workforce_risk, 1), "Maintenance backlog", "High" if workforce_risk >= 40 else "Medium", "Workforce"],
            ["COMP-ENERGY", "Energy signal", round(energy_risk, 1), "Compressor loading / energy", "High" if energy_risk >= 30 else "Medium", "Energy"],
        ],
        columns=["Asset", "Type", "Risk %", "Evidence", "Severity", "Domain"],
    )


def _twin_frame() -> pd.DataFrame:
    v = _state("inputs", _default_inputs())
    return pd.DataFrame(
        [
            ["FAC-RYD-01", "Facility", "Al Noor Advanced Manufacturing", "Operational"],
            ["LINE-01", "Process", "Assembly Line 1", "Healthy"],
            ["LINE-02", "Process", "Assembly Line 2", f"OEE {v['production_oee']:.0f}% · At Risk"],
            ["LINE-03", "Process", "Assembly Line 3", "Available for re-sequencing"],
            ["C-204", "Asset", "Main Air Compressor", f"{v['maintenance_risk']:.0f}% maintenance risk"],
            ["WO-4821", "Order", "Customer Order · 72h horizon", f"{v['order_protection']:.0f}% protected"],
            ["MAT-BRG-08", "Material", "Motor Bearing", f"{v['inventory_cover']:.1f} days cover"],
            ["Q-07", "Quality", "Seal inspection characteristic", f"Scrap +{v.get('scrap_pct', 3.8):.1f}%"],
            ["SUP-18", "Supplier", "Critical component supplier", f"{v.get('supplier_delay_h', 18.0):.0f} h late"],
            ["MW-BACKLOG", "Workforce", "Maintenance team", f"{v.get('maintenance_backlog_h', 42.0):.0f} h backlog"],
            ["ENERGY-01", "Energy", "Compressor energy signal", f"{v.get('energy_kwh_unit', 1.48):.2f} kWh/unit"],
            ["OUT-72H", "Outcome", "Customer delivery outcome", "Tracking"],
        ],
        columns=["ID", "Type", "Name", "State"],
    )


def _thread_figure() -> go.Figure:
    labels = [
        "Facility", "Line 2", "Compressor C-204", "Bearing Material",
        "72h Order", "Quality Signal", "Supplier", "Workforce",
        "Energy", "Production Plan", "Decision", "Verified Outcome"
    ]
    source = [0, 1, 2, 3, 4, 5, 6, 7, 2, 1, 9]
    target = [1, 2, 10, 2, 10, 10, 4, 10, 8, 9, 11]
    value = [3, 4, 5, 2, 6, 3, 2, 2, 2, 4, 6]
    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(label=labels, pad=18, thickness=18),
            link=dict(source=source, target=target, value=value),
        )
    )
    fig.update_layout(
        title="Digital Thread · Asset → Process → Order → Decision → Outcome",
        height=360,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig



def _rescue_case(inputs: dict[str, float] | None = None) -> dict[str, Any]:
    """Return the repeatable flagship case study and intervention impact."""
    v = inputs or _state("inputs", _default_inputs())
    flagship = str(_state("active_preset", "")) == "Flagship 72-hour crisis"
    if flagship:
        baseline = {
            "Customer delivery": "AT RISK",
            "Production shortfall %": 9.4,
            "Unplanned downtime h": 14.2,
            "Scrap change %": 3.8,
            "Overtime SAR": 86000.0,
            "Energy change %": 8.1,
            "Financial exposure SAR": 1520000.0,
        }
        intervention = {
            "Customer delivery": "PROTECTED",
            "Production shortfall %": 0.8,
            "Unplanned downtime h": 3.1,
            "Scrap change %": 0.9,
            "Overtime SAR": 29000.0,
            "Energy change %": 2.4,
            "Financial exposure SAR": 210000.0,
        }
    else:
        severity = float(np.clip((100.0 - v["production_oee"]) / 24.0 + v["maintenance_risk"] / 120.0, 0.5, 2.0))
        baseline = {
            "Customer delivery": "AT RISK" if v["order_protection"] < 90 else "PROTECTED",
            "Production shortfall %": round(5.0 * severity, 1),
            "Unplanned downtime h": round(7.1 * severity, 1),
            "Scrap change %": round(v.get("scrap_pct", 2.5), 1),
            "Overtime SAR": round(v.get("overtime_sar", 60000.0), 0),
            "Energy change %": round(max(0.0, (v["energy_kwh_unit"] - 1.20) * 28.0), 1),
            "Financial exposure SAR": round(850000.0 * severity, 0),
        }
        baseline["Customer delivery"] = "AT RISK" if baseline["Production shortfall %"] > 5 else baseline["Customer delivery"]
        intervention = {
            "Customer delivery": "PROTECTED",
            "Production shortfall %": round(max(0.4, baseline["Production shortfall %"] * 0.16), 1),
            "Unplanned downtime h": round(max(2.4, baseline["Unplanned downtime h"] * 0.22), 1),
            "Scrap change %": round(max(0.4, baseline["Scrap change %"] * 0.24), 1),
            "Overtime SAR": round(max(20000.0, baseline["Overtime SAR"] * 0.34), 0),
            "Energy change %": round(max(1.2, baseline["Energy change %"] * 0.30), 1),
            "Financial exposure SAR": round(baseline["Financial exposure SAR"] * 0.14, 0),
        }
    return {
        "baseline": baseline,
        "intervention": intervention,
        "intervention_cost": 152000.0,
        "avoided_exposure": max(0.0, baseline["Financial exposure SAR"] - intervention["Financial exposure SAR"]),
        "action_plan": [
            "Move maintenance into the next planned micro-window",
            "Reallocate two technicians to C-204",
            "Reserve critical bearing inventory",
            "Re-sequence production across Lines 2 and 3",
            "Shift selected jobs to Line 3",
            "Adjust compressor operating parameters",
            "Increase temporary quality inspection",
            "Recalculate the 72-hour production schedule",
            "Monitor C-204 and the order continuously",
        ],
    }


@st.cache_data(show_spinner=False, ttl=3600)
def _predictive_maintenance(inputs: dict[str, float] | None = None) -> pd.DataFrame:
    v = inputs or _state("inputs", _default_inputs())
    hours = np.arange(0, 72, 6)
    rng = np.random.default_rng(20261004)
    rows = []
    for asset, start, slope in [
        ("C-204", float(v["maintenance_risk"]) * 0.56, 0.49),
        ("LINE-02", float(100.0 - v["production_oee"]) + 18.0, 0.30),
        ("MTR-117", max(10.0, float(75.0 - v["inventory_cover"] * 10.0)), 0.16),
    ]:
        noise = rng.normal(0, 1.2, len(hours))
        risk = np.clip(start + slope * hours, 0, 99) + noise
        for h, r in zip(hours, risk):
            rows.append([asset, int(h), float(np.clip(r, 0, 99))])
    return pd.DataFrame(rows, columns=["Asset", "Hour", "Risk %"])


@st.cache_data(show_spinner=False, ttl=3600)
def _simulation(inputs: dict[str, float] | None = None, seed: int = 20261004) -> Dict[str, Any]:
    v = inputs or _state("inputs", _default_inputs())
    rng = np.random.default_rng(seed)
    reps = 1500
    horizon = 72
    demand = 9000.0 * float(v["demand_multiplier"])
    capacity = 130.0
    baseline_availability = float(np.clip(v["production_oee"] / 100.0, 0.55, 0.99))
    intervention_availability = float(np.clip(
        baseline_availability + 0.06 + (v["maintenance_risk"] / 100.0) * 0.05, 0.60, 0.995
    ))
    baseline_quality = float(np.clip(v["quality_yield"] / 100.0, 0.80, 0.999))
    intervention_quality = float(np.clip(baseline_quality + 0.015, 0.82, 0.999))
    scenarios = {
        "Baseline": {"availability": baseline_availability, "quality": baseline_quality, "energy": float(v["energy_kwh_unit"])},
        "Intervention": {"availability": intervention_availability, "quality": intervention_quality, "energy": max(0.85, float(v["energy_kwh_unit"]) - 0.08)},
    }
    summary = []
    samples = {}
    for name, p in scenarios.items():
        hourly = np.clip(
            rng.normal(p["availability"], 0.035, (reps, horizon)), 0.55, 0.995
        )
        gross = hourly.sum(axis=1) * capacity
        output = gross * p["quality"]
        downtime = horizon * (1.0 - hourly.mean(axis=1))
        otif = np.clip(output / demand * 100.0, 0, 100)
        energy = output * p["energy"]
        summary.append(
            [
                name,
                float(np.mean(output)),
                float(np.percentile(output, 10)),
                float(np.percentile(output, 90)),
                float(np.mean(otif)),
                float(np.mean(downtime)),
                float(np.mean(energy)),
            ]
        )
        samples[name] = output

    result = pd.DataFrame(
        summary,
        columns=[
            "Scenario", "Throughput", "P10 Throughput", "P90 Throughput",
            "OTIF %", "Downtime h", "Energy kWh",
        ],
    )
    return {"summary": result, "samples": samples, "reps": reps, "horizon": horizon}


def _optimization(inputs: dict[str, float] | None = None) -> Dict[str, Any]:
    v = inputs or _state("inputs", _default_inputs())
    sim = _state("simulation")
    if sim is not None:
        base_otif = float(sim["summary"].loc[sim["summary"]["Scenario"].eq("Baseline"), "OTIF %"].iloc[0])
    else:
        base_otif = float(np.clip(v["order_protection"], 50.0, 99.0))
    base_risk = float(v["maintenance_risk"])
    alternatives = pd.DataFrame(
        [
            ["Do Nothing", 0, 1190, base_risk, round(base_otif, 1), "No intervention"],
            ["Preventive Rescue", 152000, 1120, max(8.0, base_risk - 28.0), min(99.0, base_otif + 7.0), "Inspect C-204 + stage bearing kit"],
            ["Reroute + Rescue", 167000, 1180, max(6.0, base_risk - 34.0), min(99.0, base_otif + 9.0), "Rescue + order reroute"],
            ["Capacity Expansion", 210000, 1220, max(5.0, base_risk - 24.0), min(99.0, base_otif + 11.0), "Add temporary capacity"],
        ],
        columns=["Alternative", "Cost SAR", "Carbon kg", "Risk", "Service %", "Intervention"],
    )
    feasible = alternatives[alternatives["Service %"] >= 95].copy()
    if feasible.empty:
        feasible = alternatives.sort_values("Service %", ascending=False).head(1).copy()
    scored = pareto_weight_sweep(
        feasible,
        ["Cost SAR", "Risk", "Carbon kg"],
        weights=[0.45, 0.35, 0.20],
        minimize=[True, True, True],
    )
    choice = scored.iloc[0].to_dict()
    return {"alternatives": alternatives, "scored": scored, "choice": choice}


def _decision() -> Dict[str, Any]:
    opt = _state("optimization")
    choice = opt["choice"]
    sim = _state("simulation")
    summary = sim["summary"]
    base = summary.loc[summary["Scenario"].eq("Baseline")].iloc[0]
    inter = summary.loc[summary["Scenario"].eq("Intervention")].iloc[0]
    rescue = _state("rescue_case", _rescue_case())
    decision = {
        "title": "72-Hour Factory Rescue",
        "recommendation": "Preventive Rescue" if str(_state("active_preset", "")) == "Flagship 72-hour crisis" else str(choice["Alternative"]),
        "why": "Protect the customer order while reducing maintenance risk, quality loss, overtime and energy exposure without buying permanent capacity.",
        "baseline_otif": float(base["OTIF %"]),
        "expected_otif": float(inter["OTIF %"]),
        "baseline_downtime": float(rescue["baseline"]["Unplanned downtime h"]),
        "expected_downtime": float(rescue["intervention"]["Unplanned downtime h"]),
        "expected_throughput": float(inter["Throughput"]),
        "intervention_cost": float(rescue["intervention_cost"]),
        "risk_before": float(_state("inputs", _default_inputs())["maintenance_risk"]),
        "risk_after": max(8.0, float(_state("inputs", _default_inputs())["maintenance_risk"]) - 28.0),
        "rescue_case": rescue,
    }
    return decision


def _impact(decision: Dict[str, Any]) -> Dict[str, float]:
    rescue = decision.get("rescue_case") or _rescue_case()
    baseline_exposure = float(rescue["baseline"]["Financial exposure SAR"])
    avoided_exposure = float(rescue["avoided_exposure"])
    intervention_cost = float(rescue["intervention_cost"])
    net_value = avoided_exposure - intervention_cost
    roi = net_value / max(intervention_cost, 1.0) * 100.0
    time_manual_hours = 7.0
    time_shoir_minutes = 8.0
    return {
        "baseline_exposure": baseline_exposure,
        "avoided_exposure": avoided_exposure,
        "net_value": net_value,
        "roi": roi,
        "manual_hours": time_manual_hours,
        "shoir_minutes": time_shoir_minutes,
        "time_saved_hours": time_manual_hours - time_shoir_minutes / 60.0,
    }


def _verify(decision: Dict[str, Any]) -> pd.DataFrame:
    # A deterministic post-decision verification realization, not a claim of
    # real plant performance.
    expected = {
        "Throughput": decision["expected_throughput"],
        "OTIF %": decision["expected_otif"],
        "Downtime h": decision["expected_downtime"],
        "Maintenance risk": decision["risk_after"],
    }
    actual = {
        "Throughput": expected["Throughput"] * 0.998,
        "OTIF %": expected["OTIF %"] - 0.25,
        "Downtime h": expected["Downtime h"] + 0.18,
        "Maintenance risk": expected["Maintenance risk"] + 0.8,
    }
    targets = {
        "Throughput": (9000.0, "≥", 50.0),
        "OTIF %": (95.0, "≥", 0.5),
        "Downtime h": (6.5, "≤", 0.6),
        "Maintenance risk": (15.0, "≤", 2.0),
    }
    rows = []
    for metric, value in actual.items():
        target, direction, tolerance = targets[metric]
        passed = value >= target - tolerance if direction == "≥" else value <= target + tolerance
        rows.append(
            [
                metric,
                expected[metric],
                value,
                target,
                direction,
                "PASS" if passed else "REVIEW",
            ]
        )
    return pd.DataFrame(
        rows,
        columns=["KPI", "Expected", "Verified", "Target", "Rule", "Status"],
    )


def _persist_twin(username: str) -> None:
    try:
        twin = _twin_frame().rename(columns={"ID": "Asset"})
        twin["Scenario"] = "Investor Demo · Live"
        twin["Value"] = twin["State"]
        save_twin_snapshot(
            username,
            twin[["Asset", "Type", "Name", "Value", "Scenario"]],
            source="investor-demo",
            scenario_name="Investor Demo · Live",
        )
        save_twin_scenario(
            username,
            "72-Hour Factory Rescue",
            {
                "scenario": "Synthetic plant rescue",
                "plant": "Al Noor Advanced Manufacturing",
                "seed": 20261004,
                "horizon_hours": 72,
            },
            parent_name="Live",
            notes="Investor demo scenario; synthetic data only.",
        )
    except Exception as exc:
        _set("twin_persistence_warning", f"{type(exc).__name__}: {exc}")


def _persist_decision(username: str, decision: Dict[str, Any]) -> None:
    try:
        payload = {
            "title": decision["title"],
            "recommendation": decision["recommendation"],
            "expected_otif": round(decision["expected_otif"], 2),
            "expected_throughput": round(decision["expected_throughput"], 1),
            "intervention_cost": round(decision["intervention_cost"], 2),
            "risk_before": decision["risk_before"],
            "risk_after": decision["risk_after"],
            "source": "investor-demo",
        }
        record_workspace_artifact(
            "investor_decision",
            "72-Hour Factory Rescue",
            username,
            payload,
        )
        save_twin_scenario(
            username,
            "72-Hour Factory Rescue · Approved",
            payload,
            parent_name="72-Hour Factory Rescue",
            notes="Decision record created by the investor demonstration flow.",
        )
        _set("decision_persisted", True)
    except Exception as exc:
        _set("decision_persistence_warning", f"{type(exc).__name__}: {exc}")


def _run_all(username: str) -> None:
    _set("started", True)
    inputs = _state("inputs", _default_inputs())
    _set("plant", _plant_from_inputs(inputs))
    _set("risk", _risk_analysis(inputs))
    _set("rescue_case", _rescue_case(inputs))
    _mark("risk")
    _set("thread", _twin_frame())
    _set("tower", build_control_tower_health(
        {
            "Production": {"records": 128, "alerts": 4, "status": "Attention", "kpi": "83% OEE"},
            "Supply": {"records": 41, "alerts": 1, "status": "Review", "kpi": "95% supplier fill"},
            "Inventory": {"records": 84, "alerts": 2, "status": "Review", "kpi": "2.1 days bearing cover"},
            "Quality": {"records": 67, "alerts": 1, "status": "Review", "kpi": "1.8× drift signal"},
            "Maintenance": {"records": 22, "alerts": 3, "status": "Attention", "kpi": "82% C-204 risk"},
            "Transport": {"records": 19, "alerts": 0, "status": "Healthy", "kpi": "94% route readiness"},
            "Workforce": {"records": 58, "alerts": 1, "status": "Review", "kpi": "97% staffing"},
            "Energy": {"records": 72, "alerts": 0, "status": "Healthy", "kpi": "1.32 kWh/unit"},
            "Carbon": {"records": 9, "alerts": 0, "status": "Healthy", "kpi": "1.19 tCO2e modelled"},
        }
    ))
    _persist_twin(username)
    _mark("thread")
    _set("maintenance", _predictive_maintenance(inputs))
    _mark("maintenance")
    _set("simulation", _simulation(inputs))
    _mark("simulation")
    _set("optimization", _optimization(inputs))
    _mark("optimization")
    _set("decision", _decision())
    _persist_decision(username, _state("decision"))
    _mark("decision")
    _set("impact", _impact(_state("decision")))
    _mark("impact")
    _set("verification", _verify(_state("decision")))
    _mark("verification")


def _button(stage: str, label: str) -> None:
    disabled = False
    if stage != "risk":
        previous = STAGES[[x[0] for x in STAGES].index(stage) - 1][0]
        disabled = not _is_done(previous)
    if st.button(label, type="primary", use_container_width=True, disabled=disabled, key=f"{DEMO_KEY}_btn_{stage}"):
        _run_single(stage)


def _run_single(stage: str) -> None:
    # Single-step mode intentionally uses the same deterministic functions as
    # full-flow mode so the evidence is identical regardless of presentation style.
    username = str(st.session_state.get("current_user") or "demo_user")
    if stage == "risk":
        _set("started", True)
        inputs = _state("inputs", _default_inputs())
        _set("risk", _risk_analysis(inputs))
        _set("rescue_case", _rescue_case(inputs))
        _mark("risk")
    elif stage == "thread":
        _set("thread", _twin_frame())
        _persist_twin(username)
        _mark("thread")
    elif stage == "maintenance":
        inputs = _state("inputs", _default_inputs())
        _set("maintenance", _predictive_maintenance(inputs))
        _mark("maintenance")
    elif stage == "simulation":
        inputs = _state("inputs", _default_inputs())
        _set("simulation", _simulation(inputs))
        _mark("simulation")
    elif stage == "optimization":
        _set("optimization", _optimization())
        _mark("optimization")
    elif stage == "decision":
        _set("decision", _decision())
        _persist_decision(username, _state("decision"))
        _mark("decision")
    elif stage == "impact":
        if _state("decision") is None:
            _set("decision", _decision())
        _set("impact", _impact(_state("decision")))
        _mark("impact")
    elif stage == "verification":
        _set("verification", _verify(_state("decision")))
        _mark("verification")



# ---------------------------------------------------------------------------
# Industrial Command Center 2.0 — additive presentation and interaction layer.
# The existing industrial calculations remain the source of truth.
# ---------------------------------------------------------------------------
CC_UI_KEY = f"{DEMO_KEY}_ui"

def _ui_state(key: str, default: Any = None) -> Any:
    return st.session_state.get(f"{CC_UI_KEY}_{key}", default)


def _ui_set(key: str, value: Any) -> None:
    st.session_state[f"{CC_UI_KEY}_{key}"] = value


def _init_ui_state() -> None:
    defaults = {
        "view_mode": "Command Center",
        "density": "Comfortable",
        "inspector_id": "C-204",
        "whatif_result": None,
        "whatif_open": False,
        "evidence_open": False,
        "decision_status": "RECOMMENDED",
        "decision_owner": "Industrial Engineering",
        "saved_scenarios": [],
        "command_nonce": "",
        "inspector_open": False,
        "focus_domain": "Cross-domain",
    }
    for key, value in defaults.items():
        if _ui_state(key) is None:
            _ui_set(key, value)


def _inject_command_center_css() -> None:
    density = _ui_state("density", "Comfortable")
    pad = "14px" if density == "Comfortable" else "9px"
    st.markdown(
        f"""
        <style>
        .cc-shell {{ margin: -8px 0 14px 0; }}
        .cc-card {{
            border: 1px solid rgba(148,163,184,.18);
            border-radius: 18px;
            padding: {pad}px 16px;
            background: linear-gradient(145deg, rgba(20,27,37,.96), rgba(13,19,28,.96));
            box-shadow: 0 8px 28px rgba(0,0,0,.12);
        }}
        .cc-card-soft {{
            border: 1px solid rgba(148,163,184,.14);
            border-radius: 16px;
            padding: {pad}px 14px;
            background: rgba(20,27,37,.72);
        }}
        .cc-kicker {{
            font-size: 11px; text-transform: uppercase; letter-spacing: .13em;
            color: rgba(226,232,240,.62); font-weight: 700;
        }}
        .cc-value {{ font-size: 27px; font-weight: 800; line-height: 1.0; margin-top: 4px; }}
        .cc-label {{ font-size: 12px; color: rgba(226,232,240,.66); margin-top: 7px; }}
        .cc-good {{ color: #8ee3b2; }}
        .cc-warn {{ color: #ffd37a; }}
        .cc-danger {{ color: #ff9292; }}
        .cc-muted {{ color: rgba(226,232,240,.55); }}
        .cc-title {{
            font-size: 34px; font-weight: 850; line-height: 1.05; letter-spacing: -.02em;
        }}
        .cc-subtitle {{ font-size: 14px; color: rgba(226,232,240,.72); max-width: 970px; margin-top: 8px; }}
        .cc-pill {{
            display:inline-block; padding:4px 9px; border-radius:999px;
            font-size:10px; font-weight:800; letter-spacing:.08em;
            border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.05);
        }}
        .cc-step {{
            display:flex; gap:8px; align-items:center; justify-content:center;
            min-height:44px; border:1px solid rgba(148,163,184,.14);
            border-radius:12px; background:rgba(255,255,255,.025);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _cc_confidence_profile(risk: pd.DataFrame | None = None) -> dict[str, float]:
    """Synthetic evidence profile for the demo; not a live telemetry confidence score."""
    risk_count = int(len(risk)) if isinstance(risk, pd.DataFrame) else 0
    completeness = 100.0 if risk_count >= 7 else 88.0
    freshness = 96.0
    conflict_free = 93.0
    model_stability = 92.0
    overall = round(
        completeness * 0.30 + freshness * 0.20 + conflict_free * 0.20 + model_stability * 0.30,
        1,
    )
    return {
        "overall": overall,
        "completeness": completeness,
        "freshness": freshness,
        "conflict_free": conflict_free,
        "model_stability": model_stability,
    }


def _cc_rescue() -> dict[str, Any]:
    return _state("rescue_case", _rescue_case())


def _cc_risk() -> pd.DataFrame:
    risk = _state("risk")
    if isinstance(risk, pd.DataFrame):
        return risk
    return _risk_analysis(_state("inputs", _default_inputs()))


def _cc_inspector_options() -> list[str]:
    thread = _state("thread")
    if isinstance(thread, pd.DataFrame) and "ID" in thread.columns:
        return [str(x) for x in thread["ID"].tolist()]
    return [str(x) for x in _twin_frame()["ID"].tolist()]


def _cc_entity_detail(entity_id: str) -> dict[str, Any]:
    v = _state("inputs", _default_inputs())
    risk = _cc_risk()
    lookup = {
        "FAC-RYD-01": ("Facility", "Al Noor Advanced Manufacturing", "Operational", "Plant-wide rescue coordination"),
        "LINE-01": ("Process", "Assembly Line 1", "Healthy", "Reference capacity / alternate flow"),
        "LINE-02": ("Process", "Assembly Line 2", f"OEE {v['production_oee']:.0f}%", "Primary production constraint"),
        "LINE-03": ("Process", "Assembly Line 3", "Available", "Recovery capacity / reroute"),
        "C-204": ("Asset", "Main Air Compressor", f"{v['maintenance_risk']:.0f}% maintenance risk", "Critical asset driving the rescue"),
        "WO-4821": ("Customer Order", "Customer Order · 72h horizon", f"{v['order_protection']:.0f}% protected", "Service commitment"),
        "MAT-BRG-08": ("Material", "Motor Bearing", f"{v['inventory_cover']:.1f} days cover", "Critical spare availability"),
        "Q-07": ("Quality", "Seal inspection characteristic", f"+{v.get('scrap_pct', 3.8):.1f}% scrap", "Quality-loss trigger"),
        "SUP-18": ("Supplier", "Critical component supplier", f"{v.get('supplier_delay_h', 18.0):.0f} h late", "Supply constraint"),
        "MW-BACKLOG": ("Workforce", "Maintenance team", f"{v.get('maintenance_backlog_h', 42.0):.0f} h backlog", "Execution capacity"),
        "ENERGY-01": ("Energy", "Compressor energy signal", f"{v.get('energy_kwh_unit', 1.48):.2f} kWh/unit", "Efficiency / loading signal"),
        "OUT-72H": ("Outcome", "Customer delivery outcome", "Tracking", "Closed-loop verification"),
    }
    typ, name, state, impact = lookup.get(entity_id, ("Entity", entity_id, "Tracked", "Digital Thread entity"))
    row = risk.loc[risk["Asset"].astype(str).eq(entity_id)] if isinstance(risk, pd.DataFrame) else pd.DataFrame()
    rvalue = float(row["Risk %"].iloc[0]) if not row.empty else None
    if entity_id == "C-204":
        rvalue = float(v["maintenance_risk"])
    return {"type": typ, "name": name, "state": state, "impact": impact, "risk": rvalue}


def _render_command_palette(username: str) -> None:
    _init_ui_state()
    st.markdown("#### ⌘ Command Palette")
    c1, c2, c3 = st.columns([1.15, 1.0, 2.2])
    view_options = ["Command Center", "Executive", "Engineering", "Maintenance", "Supply Chain", "Sustainability"]
    with c1:
        mode = st.selectbox(
            "Workspace view",
            view_options,
            index=view_options.index(_ui_state("view_mode", "Command Center")),
            key=f"{CC_UI_KEY}_view_mode",
        )
        _ui_set("view_mode", mode)
    with c2:
        density_options = ["Comfortable", "Compact"]
        density = st.selectbox(
            "Display density",
            density_options,
            index=density_options.index(_ui_state("density", "Comfortable")),
            key=f"{CC_UI_KEY}_density",
        )
        _ui_set("density", density)
    with c3:
        command = st.text_input(
            "Command",
            placeholder="Try: full rescue · risk · executive · what if · evidence · inspector · reset",
            key=f"{CC_UI_KEY}_command",
            help="Enter a command and press Return. Commands act on the same Command Center state.",
        )
    normalized = str(command or "").strip().lower()
    last = str(_ui_state("command_nonce", ""))
    if normalized and normalized != last:
        _ui_set("command_nonce", normalized)
        if (("full" in normalized) or ("rescue" in normalized and "plan" not in normalized)):
            _run_all(username)
            st.rerun()
        elif normalized in {"risk", "analyze risk", "plant risk"}:
            _run_single("risk")
            st.rerun()
        elif "executive" in normalized:
            _ui_set("view_mode", "Executive")
            st.rerun()
        elif "engineering" in normalized:
            _ui_set("view_mode", "Engineering")
            st.rerun()
        elif "maintenance" in normalized:
            _ui_set("view_mode", "Maintenance")
            st.rerun()
        elif "supply" in normalized:
            _ui_set("view_mode", "Supply Chain")
            st.rerun()
        elif "sustain" in normalized:
            _ui_set("view_mode", "Sustainability")
            st.rerun()
        elif "what" in normalized and "if" in normalized:
            _ui_set("whatif_open", True)
            st.rerun()
        elif "evidence" in normalized:
            _ui_set("evidence_open", True)
            st.rerun()
        elif "inspector" in normalized:
            _ui_set("inspector_open", True)
            st.rerun()
        elif normalized == "reset":
            _reset()
            st.rerun()


def _render_top_cockpit() -> None:
    values = _state("inputs", _default_inputs())
    plant = _state("plant", _plant_from_inputs(values))
    rescue = _cc_rescue()
    baseline = rescue["baseline"]
    intervention = rescue["intervention"]
    risk = _cc_risk()
    conf = _cc_confidence_profile(risk)
    plant_health = float(pd.to_numeric(plant["Health %"], errors="coerce").mean())
    risk_top = risk.sort_values("Risk %", ascending=False).iloc[0]
    exposure = float(baseline["Financial exposure SAR"])
    improved = float(intervention["Financial exposure SAR"])
    saved = float(rescue["avoided_exposure"])
    mode = _ui_state("view_mode", "Command Center")

    st.markdown(
        f"""
        <div class="cc-shell">
          <div class="cc-card">
            <div class="cc-kicker">Industrial Operating System · Command Center 2.0</div>
            <div class="cc-title">Plant Situation Room</div>
            <div class="cc-subtitle">
              Make the situation legible first. Then trace the evidence, test the future,
              select the intervention, quantify business impact and verify the result.
            </div>
            <div style="margin-top:12px;">
              <span class="cc-pill">◆ {mode.upper()}</span>
              <span class="cc-pill" style="margin-left:6px;">◉ SYNTHETIC DEMO</span>
              <span class="cc-pill" style="margin-left:6px;">72H DECISION WINDOW</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Current situation")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Customer commitment", f"{values['order_protection']:.0f}%", "AT RISK" if values["order_protection"] < 90 else "PROTECTED")
    k2.metric("Plant health", f"{plant_health:.0f}%", "calculated")
    k3.metric("Highest risk", str(risk_top["Asset"]), f"{float(risk_top['Risk %']):.0f}%")
    k4.metric("Financial exposure", _format_sar(exposure), "do nothing")
    k5.metric("Avoided exposure", _format_sar(saved), f"→ {_format_sar(improved)}")

    if mode == "Executive":
        st.info(
            f"**Executive readout:** the plant is currently exposed to a 72-hour service risk. "
            f"Shoir-IE's modelled rescue reduces financial exposure from {_format_sar(exposure)} "
            f"to {_format_sar(improved)} under this synthetic scenario. "
            f"Model confidence profile: {conf['overall']:.0f}%."
        )
    elif mode == "Maintenance":
        st.info(
            f"**Maintenance readout:** C-204 is the primary risk driver at "
            f"{values['maintenance_risk']:.0f}% modelled risk with "
            f"{values.get('maintenance_backlog_h', 42.0):.0f} h backlog."
        )
    elif mode == "Supply Chain":
        st.info(
            f"**Supply readout:** critical supplier delay is "
            f"{values.get('supplier_delay_h', 18.0):.0f} h and bearing cover is "
            f"{values['inventory_cover']:.1f} days."
        )
    elif mode == "Sustainability":
        st.info(
            f"**Sustainability readout:** specific energy is {values['energy_kwh_unit']:.2f} kWh/unit "
            f"and the intervention models a reduction in the energy-change signal."
        )
    elif mode == "Engineering":
        st.info(
            f"**Engineering readout:** the current risk set contains {len(risk)} connected signals. "
            f"The highest-ranked asset is {risk_top['Asset']} at {float(risk_top['Risk %']):.0f}%."
        )
    else:
        st.warning(
            f"**Situation:** the plant is not failing because of one number. "
            f"The connected risk comes from {len(risk)} interacting signals across operations."
        )

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown("#### 🧠 Recommended rescue")
        st.markdown(
            f"""
            <div class="cc-card">
              <div class="cc-kicker">Decision recommendation</div>
              <div class="cc-value">PREVENTIVE RESCUE</div>
              <div class="cc-label">Protect the 72-hour customer commitment while reducing operational exposure.</div>
              <div style="margin-top:12px;font-size:13px;">
                <b>Modelled exposure:</b> {_format_sar(exposure)} → {_format_sar(improved)}
                &nbsp; · &nbsp; <b>Avoided:</b> {_format_sar(saved)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        p = rescue["action_plan"]
        with st.expander("View the 9-step rescue plan", expanded=False):
            for i, action in enumerate(p, 1):
                st.markdown(f"**{i:02d}** · {action}")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("🎯 Review decision evidence", use_container_width=True, key=f"{CC_UI_KEY}_jump_decision"):
                    _ui_set("view_mode", "Engineering")
                    st.rerun()
            with b2:
                if st.button("🧪 Re-test the rescue", use_container_width=True, key=f"{CC_UI_KEY}_retest"):
                    inputs = _state("inputs", _default_inputs())
                    _set("simulation", _simulation(inputs))
                    _set("optimization", _optimization(inputs))
                    _set("decision", _decision())
                    _set("impact", _impact(_state("decision")))
                    _set("verification", _verify(_state("decision")))
                    _set("completed", list(dict.fromkeys(_state("completed", []) + ["risk", "thread", "maintenance", "simulation", "optimization", "decision", "impact", "verification"])))
                    st.rerun()
    with right:
        st.markdown("#### 📊 Decision confidence")
        cc1, cc2 = st.columns(2)
        cc1.metric("Model confidence", f"{conf['overall']:.0f}%")
        cc2.metric("Evidence completeness", f"{conf['completeness']:.0f}%")
        st.progress(conf["overall"] / 100.0)
        st.caption(
            f"Freshness {conf['freshness']:.0f}% · conflict-free {conf['conflict_free']:.0f}% · "
            f"model stability {conf['model_stability']:.0f}%. Synthetic demo profile."
        )
        st.markdown("#### 🔎 Top risk drivers")
        driver = risk.nlargest(4, "Risk %")[["Asset", "Risk %", "Domain", "Evidence"]].copy()
        driver["Risk %"] = driver["Risk %"].map(lambda x: f"{float(x):.0f}%")
        st.dataframe(driver, use_container_width=True, hide_index=True)

    st.markdown("#### 🧭 Decision pipeline")
    rail_cols = st.columns(6)
    stages = [
        ("01", "RISK", _is_done("risk")),
        ("02", "EVIDENCE", _is_done("thread")),
        ("03", "FUTURE", _is_done("simulation")),
        ("04", "ACTION", _is_done("decision")),
        ("05", "VALUE", _is_done("impact")),
        ("06", "VERIFY", _is_done("verification")),
    ]
    for col, (num, label, done) in zip(rail_cols, stages):
        with col:
            state = "COMPLETE" if done else "PENDING"
            marker = "✓" if done else num
            cls = "cc-good" if done else "cc-muted"
            st.markdown(
                f'<div class="cc-step"><span class="{cls}" title="{state}"><b>{marker}</b></span><span style="font-size:11px;">{label}</span></div>',
                unsafe_allow_html=True,
            )


def _render_health_map_and_inspector() -> None:
    plant = _state("plant", _plant_from_inputs(_state("inputs", _default_inputs())))
    left, right = st.columns([1.35, 1])
    with left:
        st.markdown("#### 🗺️ Plant health map")
        metric = st.radio("Map metric", ["Health %", "Risk %"], horizontal=True, key=f"{CC_UI_KEY}_health_metric")
        if metric == "Health %":
            plot = plant[["Area", "Health %"]].copy()
            fig = px.bar(plot.sort_values("Health %"), x="Health %", y="Area", orientation="h", range_x=[0, 100], title="Operational health")
        else:
            risk = _cc_risk().copy()
            plot = risk.groupby("Domain", as_index=False)["Risk %"].max().sort_values("Risk %")
            fig = px.bar(plot, x="Risk %", y="Domain", orientation="h", range_x=[0, 100], title="Cross-domain risk")
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "displaylogo": False})

        st.markdown("#### 🆚 Do nothing vs Shoir-IE")
        rescue = _cc_rescue()
        base = rescue["baseline"]
        inter = rescue["intervention"]
        compare = pd.DataFrame(
            {
                "Metric": ["Customer delivery", "Production shortfall", "Downtime", "Scrap", "Overtime", "Energy", "Financial exposure"],
                "Do Nothing": [
                    base["Customer delivery"], f"{base['Production shortfall %']:.1f}%", f"{base['Unplanned downtime h']:.1f} h",
                    f"+{base['Scrap change %']:.1f}%", _format_sar(base["Overtime SAR"]), f"+{base['Energy change %']:.1f}%",
                    _format_sar(base["Financial exposure SAR"]),
                ],
                "Shoir-IE": [
                    inter["Customer delivery"], f"{inter['Production shortfall %']:.1f}%", f"{inter['Unplanned downtime h']:.1f} h",
                    f"+{inter['Scrap change %']:.1f}%", _format_sar(inter["Overtime SAR"]), f"+{inter['Energy change %']:.1f}%",
                    _format_sar(inter["Financial exposure SAR"]),
                ],
            }
        )
        st.dataframe(compare, use_container_width=True, hide_index=True)
        fig2 = px.bar(
            pd.DataFrame({
                "Scenario": ["Do Nothing", "Shoir-IE"],
                "Exposure SAR": [base["Financial exposure SAR"], inter["Financial exposure SAR"]],
            }),
            x="Scenario", y="Exposure SAR", title="Modelled financial exposure",
        )
        fig2.update_layout(height=240, margin=dict(l=10, r=10, t=45, b=10), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False, "displaylogo": False})

    with right:
        st.markdown("#### 🔍 Persistent Inspector")
        options = _cc_inspector_options()
        current = str(_ui_state("inspector_id", "C-204"))
        if current not in options:
            current = options[0] if options else ""
        selected = st.selectbox(
            "Inspect entity",
            options,
            index=options.index(current) if options else 0,
            key=f"{CC_UI_KEY}_inspector_id",
        ) if options else ""
        if selected:
            _ui_set("inspector_id", selected)
            detail = _cc_entity_detail(selected)
            st.markdown(
                f"""
                <div class="cc-card">
                  <div class="cc-kicker">{detail['type']}</div>
                  <div class="cc-value" style="font-size:22px;">{detail['name']}</div>
                  <div class="cc-label">{detail['state']}</div>
                  <div style="margin-top:10px;"><b>Why it matters:</b> {detail['impact']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if detail["risk"] is not None:
                st.metric("Modelled risk", f"{detail['risk']:.0f}%")
            related = {
                "C-204": "Line 2 · Bearing · Maintenance workforce · Energy · Customer order",
                "LINE-02": "C-204 · Production plan · Quality · Customer order",
                "WO-4821": "Line 2 · Production plan · Supplier · Outcome",
                "MAT-BRG-08": "C-204 · Supplier · Maintenance",
                "SUP-18": "Bearing · Production plan · Customer order",
                "Q-07": "Line 2 · C-204 · Customer order",
            }.get(selected, "Facility · Production · Decision · Outcome")
            st.markdown("**Connected to**")
            st.caption(related)
            a1, a2 = st.columns(2)
            with a1:
                st.button("🧪 Simulate entity", use_container_width=True, key=f"{CC_UI_KEY}_inspect_sim")
            with a2:
                if st.button("📋 Explain evidence", use_container_width=True, key=f"{CC_UI_KEY}_inspect_explain"):
                    _ui_set("evidence_open", True)
                    st.rerun()


def _render_why_recommendation() -> None:
    st.markdown("#### 🧠 Why did Shoir-IE recommend Preventive Rescue?")
    v = _state("inputs", _default_inputs())
    risk = _cc_risk().sort_values("Risk %", ascending=False).head(5).copy()
    factors = pd.DataFrame(
        [
            ["Customer protection", f"{v['order_protection']:.0f}%", 40.0, "Protect the 72-hour commitment"],
            ["Maintenance risk", f"{v['maintenance_risk']:.0f}%", 30.0, "Avoid a critical C-204 disruption"],
            ["Operational resilience", f"{v['inventory_cover']:.1f} d / {v.get('supplier_delay_h',18.0):.0f} h", 20.0, "Protect spare-part and supply continuity"],
            ["Cost / energy", f"{v.get('overtime_sar',86000.0):,.0f} SAR / {v['energy_kwh_unit']:.2f}", 10.0, "Limit recovery cost and energy penalty"],
        ],
        columns=["Decision factor", "Current signal", "Decision weight %", "Role"],
    )
    st.dataframe(factors, use_container_width=True, hide_index=True)
    risk["Risk %"] = risk["Risk %"].map(lambda x: f"{float(x):.0f}%")
    st.dataframe(risk[["Asset", "Risk %", "Domain", "Evidence"]], use_container_width=True, hide_index=True)
    st.caption(
        "The weights make the recommendation explainable. They are demonstration policy weights, "
        "not a claim that a real plant would use these exact priorities."
    )


def _render_what_if_mode() -> None:
    st.caption("What-If creates an isolated future state. It does not overwrite current plant inputs.")
    v = _state("inputs", _default_inputs())
    w1, w2, w3, w4 = st.columns(4)
    oee = w1.slider("Line 2 OEE", 50.0, 99.0, float(v["production_oee"]), 0.5, key=f"{CC_UI_KEY}_whatif_oee")
    maint = w2.slider("C-204 risk", 5.0, 99.0, float(v["maintenance_risk"]), 1.0, key=f"{CC_UI_KEY}_whatif_maint")
    inv = w3.slider("Bearing cover", 0.5, 7.0, float(v["inventory_cover"]), 0.1, key=f"{CC_UI_KEY}_whatif_inv")
    supp = w4.slider("Supplier delay", 0.0, 120.0, float(v.get("supplier_delay_h", 18.0)), 1.0, key=f"{CC_UI_KEY}_whatif_supplier")
    if st.button("▶ Run What-If", type="primary", use_container_width=True, key=f"{CC_UI_KEY}_run_whatif"):
        changes = {
            "Production OEE": oee - float(v["production_oee"]),
            "C-204 Risk": maint - float(v["maintenance_risk"]),
            "Bearing Cover": inv - float(v["inventory_cover"]),
            "Supplier Delay": supp - float(v.get("supplier_delay_h", 18.0)),
        }
        base_df = pd.DataFrame([{
            "Production OEE": float(v["production_oee"]),
            "C-204 Risk": float(v["maintenance_risk"]),
            "Bearing Cover": float(v["inventory_cover"]),
            "Supplier Delay": float(v.get("supplier_delay_h", 18.0)),
        }])
        scenario_df, audit_df = twin_what_if(base_df, changes)
        scenario_inputs = dict(v)
        scenario_inputs.update({
            "production_oee": float(scenario_df["Production OEE"].iloc[0]),
            "maintenance_risk": float(scenario_df["C-204 Risk"].iloc[0]),
            "inventory_cover": float(scenario_df["Bearing Cover"].iloc[0]),
            "supplier_delay_h": float(scenario_df["Supplier Delay"].iloc[0]),
        })
        sim = _simulation(scenario_inputs, seed=20261004)
        s = sim["summary"]
        b = s[s["Scenario"].eq("Baseline")].iloc[0]
        i = s[s["Scenario"].eq("Intervention")].iloc[0]
        result = {
            "audit": audit_df,
            "summary": pd.DataFrame(
                [
                    ["OTIF", float(b["OTIF %"]), float(i["OTIF %"])],
                    ["Downtime h", float(b["Downtime h"]), float(i["Downtime h"])],
                    ["Throughput", float(b["Throughput"]), float(i["Throughput"])],
                    ["Energy kWh", float(b["Energy kWh"]), float(i["Energy kWh"])],
                ],
                columns=["Metric", "Current / Baseline", "What-If Intervention"],
            ),
            "inputs": scenario_inputs,
        }
        _ui_set("whatif_result", result)
    result = _ui_state("whatif_result")
    if result:
        st.dataframe(result["summary"].round(2), use_container_width=True, hide_index=True)
        with st.expander("What changed?", expanded=False):
            st.dataframe(result["audit"].round(2), use_container_width=True, hide_index=True)
        st.caption("What-If results are isolated from the live demo state.")


def _render_scenario_library(username: str) -> None:
    with st.expander("🗂️ Scenario Library & workspace", expanded=False):
        st.caption("Save, name and revisit scenarios without changing any connected plant.")
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Save current scenario as", placeholder="e.g. Night shift recovery", key=f"{CC_UI_KEY}_scenario_name")
        if c2.button("💾 Save scenario", use_container_width=True, key=f"{CC_UI_KEY}_save_scenario"):
            scenario_name = name.strip() or f"Scenario · {time.strftime('%Y-%m-%d %H:%M')}"
            try:
                save_twin_scenario(
                    username,
                    scenario_name,
                    _state("inputs", _default_inputs()),
                    parent_name="Command Center 2.0",
                    notes="Saved from Industrial Command Center workspace.",
                )
                saved = list(_ui_state("saved_scenarios", []))
                if scenario_name not in saved:
                    saved.append(scenario_name)
                _ui_set("saved_scenarios", saved[-20:])
                st.success(f"Scenario saved: {scenario_name}")
            except Exception as exc:
                st.warning(f"Scenario save unavailable: {type(exc).__name__}")
        builtins = ["Flagship 72-hour crisis", "Compressor deterioration", "Demand surge", "Stable recovery"]
        st.markdown("**Quick scenarios**")
        cols = st.columns(4)
        for col, preset_name in zip(cols, builtins):
            with col:
                if st.button(preset_name, use_container_width=True, key=f"{CC_UI_KEY}_quick_{preset_name.replace(' ','_')}"):
                    _apply_inputs(_preset(preset_name), username, preset_name)
                    st.rerun()

        saved = list(_ui_state("saved_scenarios", []))
        if saved:
            chosen = st.selectbox("Saved in this session", saved, key=f"{CC_UI_KEY}_saved_select")
            if st.button("↻ Load saved scenario", use_container_width=True, key=f"{CC_UI_KEY}_load_saved"):
                try:
                    df = list_twin_scenarios(username)
                    row = df.loc[df["name"].astype(str).eq(chosen)] if "name" in df.columns else pd.DataFrame()
                    if row.empty:
                        st.warning("Saved scenario was not found in the workspace.")
                    else:
                        import json
                        payload = json.loads(str(row.iloc[0]["parameters_json"]))
                        filtered = {k: float(val) for k, val in payload.items() if k in _default_inputs()}
                        _apply_inputs(filtered, username, chosen)
                        st.rerun()
                except Exception as exc:
                    st.warning(f"Scenario load unavailable: {type(exc).__name__}")
        if st.button("↻ Refresh saved scenarios", use_container_width=True, key=f"{CC_UI_KEY}_refresh_scenarios"):
            try:
                df = list_twin_scenarios(username)
                names = df["name"].astype(str).tolist() if "name" in df.columns else []
                _ui_set("saved_scenarios", names[:30])
                st.success(f"Loaded {len(names[:30])} workspace scenarios.")
            except Exception as exc:
                st.warning(f"Scenario refresh unavailable: {type(exc).__name__}")


def _render_evidence_chain() -> None:
    v = _state("inputs", _default_inputs())
    rescue = _cc_rescue()
    st.markdown("#### 🔗 Evidence Chain · How did Shoir-IE get these numbers?")
    evidence = pd.DataFrame(
        [
            ["Customer exposure", "WO-4821 / 72h commitment", f"{v['order_protection']:.0f}% protected", "Synthetic scenario input"],
            ["Production loss", "LINE-02", f"{rescue['baseline']['Production shortfall %']:.1f}%", "Rescue-case model"],
            ["Downtime", "C-204 / LINE-02", f"{rescue['baseline']['Unplanned downtime h']:.1f} h", "Rescue-case model"],
            ["Quality loss", "Q-07", f"+{rescue['baseline']['Scrap change %']:.1f}%", "Synthetic scenario input"],
            ["Recovery cost", "Workforce / OT", _format_sar(rescue["baseline"]["Overtime SAR"]), "Synthetic scenario input"],
            ["Energy signal", "ENERGY-01", f"+{rescue['baseline']['Energy change %']:.1f}%", "Rescue-case model"],
            ["Financial exposure", "Combined operating impact", _format_sar(rescue["baseline"]["Financial exposure SAR"]), "Synthetic scenario result"],
        ],
        columns=["Outcome", "Trace", "Value", "Evidence source"],
    )
    st.dataframe(evidence, use_container_width=True, hide_index=True)
    st.info(
        "Traceability rule: every investor-demo number is explicitly labelled as synthetic or modelled. "
        "Customer deployments should replace these nodes with source-system records and approved calculation rules."
    )
    ver = _state("verification")
    if isinstance(ver, pd.DataFrame):
        digest = hashlib.sha256(ver.to_csv(index=False).encode("utf-8")).hexdigest()
        st.caption(f"Verification evidence hash: {digest[:16]}…")
        with st.expander("Full verification hash", expanded=False):
            st.code(digest, language="text")


def _render_decision_governance() -> None:
    st.markdown("#### 🛡️ Decision Governance")
    status_options = ["RECOMMENDED", "UNDER REVIEW", "APPROVED", "EXECUTION", "MONITORING", "VERIFIED"]
    status = str(_ui_state("decision_status", "RECOMMENDED"))
    owner = str(_ui_state("decision_owner", "Industrial Engineering"))
    c1, c2, c3 = st.columns([1.3, 1.3, 1])
    with c1:
        new_status = st.selectbox(
            "Decision state",
            status_options,
            index=status_options.index(status),
            key=f"{CC_UI_KEY}_decision_status",
        )
        _ui_set("decision_status", new_status)
    with c2:
        new_owner = st.text_input("Decision owner", owner, key=f"{CC_UI_KEY}_decision_owner")
        _ui_set("decision_owner", new_owner)
    with c3:
        if st.button("💾 Record status", use_container_width=True, key=f"{CC_UI_KEY}_record_status"):
            username = str(st.session_state.get("current_user") or "demo_user")
            try:
                save_twin_scenario(
                    username,
                    f"72-Hour Factory Rescue · {new_status}",
                    {
                        "status": new_status,
                        "owner": new_owner,
                        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "recommendation": "Preventive Rescue",
                    },
                    parent_name="72-Hour Factory Rescue",
                    notes="Command Center governance event; demo workflow.",
                )
                st.success("Governance state recorded.")
            except Exception as exc:
                st.warning(f"Governance record unavailable: {type(exc).__name__}")
    timeline = status_options
    idx = timeline.index(new_status)
    st.progress((idx + 1) / len(timeline))
    st.caption("Governance actions are demonstration records; approval does not execute a real plant action.")


def _render_closed_loop() -> None:
    st.markdown("#### 🔄 Closed-loop decision")
    status = str(_ui_state("decision_status", "RECOMMENDED"))
    rescue = _cc_rescue()
    base = rescue["baseline"]["Financial exposure SAR"]
    after = rescue["intervention"]["Financial exposure SAR"]
    stages = ["Detect", "Understand", "Predict", "Simulate", "Optimize", "Decide", "Execute", "Measure", "Learn"]
    completed = {"RECOMMENDED": 6, "UNDER REVIEW": 6, "APPROVED": 6, "EXECUTION": 7, "MONITORING": 8, "VERIFIED": 9}.get(status, 6)
    cols = st.columns(len(stages))
    for i, (col, stage) in enumerate(zip(cols, stages), 1):
        with col:
            mark = "✓" if i <= completed else "○"
            color = "cc-good" if i <= completed else "cc-muted"
            st.markdown(f'<div class="cc-step"><span class="{color}"><b>{mark}</b></span><span style="font-size:9px;">{stage}</span></div>', unsafe_allow_html=True)
    st.caption(
        f"Expected exposure {_format_sar(base)} → {_format_sar(after)}. "
        f"Current governance state: **{status}**. "
        "Real deployments close the loop by comparing verified plant outcomes with model expectations."
    )


def _render_executive_summary() -> None:
    rescue = _cc_rescue()
    b = rescue["baseline"]
    i = rescue["intervention"]
    st.markdown(
        f"""
        <div class="cc-card">
          <div class="cc-kicker">Executive View</div>
          <div class="cc-value" style="font-size:24px;">72-HOUR CUSTOMER COMMITMENT</div>
          <div style="margin-top:10px;font-size:14px;">
            The modelled situation is <b>AT RISK</b>. Shoir-IE recommends <b>PREVENTIVE RESCUE</b>.
          </div>
          <div style="margin-top:12px;">
            <b>{b['Production shortfall %']:.1f}% → {i['Production shortfall %']:.1f}%</b>
            &nbsp; · &nbsp;
            <b>{b['Unplanned downtime h']:.1f}h → {i['Unplanned downtime h']:.1f}h</b>
            &nbsp; · &nbsp;
            <b>{_format_sar(b['Financial exposure SAR'])} → {_format_sar(i['Financial exposure SAR'])}</b>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Synthetic demonstration scenario; same underlying Command Center state as the engineering workflow.")


def _render_command_center_upgrade(username: str) -> None:
    _init_ui_state()
    _inject_command_center_css()
    _render_command_palette(username)
    _render_top_cockpit()
    with st.expander("⚙️ Customize Command Center", expanded=False):
        st.caption("Customize the role lens and focus without altering industrial calculations.")
        f1, f2 = st.columns(2)
        with f1:
            focus_options = ["Cross-domain", "Production", "Maintenance", "Quality", "Supply", "Inventory", "Energy", "Workforce", "Customer"]
            focus = st.selectbox("Primary focus domain", focus_options, index=focus_options.index(_ui_state("focus_domain", "Cross-domain")), key=f"{CC_UI_KEY}_focus")
            _ui_set("focus_domain", focus)
            if focus != "Cross-domain":
                risk = _cc_risk()
                focus_risk = risk[risk["Domain"].astype(str).eq(focus)]
                if not focus_risk.empty:
                    st.dataframe(focus_risk, use_container_width=True, hide_index=True)
        with f2:
            st.radio("Preferred starting lens", ["Situation", "Recommendation", "Evidence"], horizontal=True, key=f"{CC_UI_KEY}_starting_lens")
    _render_health_map_and_inspector()
    with st.expander("🧠 Explain the recommendation", expanded=False):
        _render_why_recommendation()
    with st.expander("🔮 What-If Studio", expanded=_ui_state("whatif_open", False)):
        _render_what_if_mode()
    _render_scenario_library(username)
    with st.expander("🔗 Evidence Chain", expanded=_ui_state("evidence_open", False)):
        _render_evidence_chain()
    with st.expander("🛡️ Decision Governance", expanded=False):
        _render_decision_governance()
    _render_executive_summary()
    _render_closed_loop()

def _render_stage_rail() -> None:
    cols = st.columns(len(STAGES))
    for col, (key, icon, label) in zip(cols, STAGES):
        with col:
            done = _is_done(key)
            marker = "✓" if done else icon
            st.markdown(
                f"<div style='text-align:center;padding:8px 3px;border-radius:12px;"
                f"border:1px solid rgba(120,120,120,.25);min-height:62px;'>"
                f"<div style='font-size:22px'>{marker}</div>"
                f"<div style='font-size:11px;font-weight:600'>{label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _render_plant_controls(username: str) -> None:
    """Interactive plant scenario controls; edits feed every downstream stage."""
    values = dict(_state("inputs", _default_inputs()))
    st.markdown("### 🎛️ Change Plant Situation")
    st.caption(
        "Edit the synthetic operating conditions below. Shoir-IE will recalculate risk, "
        "maintenance, simulation, optimization, ROI and verification from the new state."
    )

    p1, p2, p3 = st.columns(3)
    production = p1.slider(
        "Line 2 OEE (%)", 50.0, 99.0, float(values["production_oee"]), 0.5,
        key=f"{DEMO_KEY}_input_production"
    )
    maintenance = p2.slider(
        "C-204 maintenance risk (%)", 5.0, 99.0, float(values["maintenance_risk"]), 1.0,
        key=f"{DEMO_KEY}_input_maintenance"
    )
    quality = p3.slider(
        "Quality yield (%)", 85.0, 99.9, float(values["quality_yield"]), 0.1,
        key=f"{DEMO_KEY}_input_quality"
    )
    p4, p5, p6 = st.columns(3)
    inventory = p4.slider(
        "Bearing inventory cover (days)", 0.5, 7.0, float(values["inventory_cover"]), 0.1,
        key=f"{DEMO_KEY}_input_inventory"
    )
    order = p5.slider(
        "72h customer order protection (%)", 50.0, 100.0, float(values["order_protection"]), 1.0,
        key=f"{DEMO_KEY}_input_order"
    )
    demand = p6.slider(
        "Demand multiplier", 0.80, 1.50, float(values["demand_multiplier"]), 0.05,
        key=f"{DEMO_KEY}_input_demand"
    )
    energy = st.slider(
        "Specific energy (kWh / unit)", 0.80, 2.50, float(values["energy_kwh_unit"]), 0.01,
        key=f"{DEMO_KEY}_input_energy"
    )

    with st.expander("⚙️ Advanced crisis factors", expanded=True):
        q1, q2, q3, q4 = st.columns(4)
        scrap = q1.number_input(
            "Scrap change (%)", 0.0, 15.0, float(values.get("scrap_pct", 3.8)), 0.1,
            key=f"{DEMO_KEY}_input_scrap"
        )
        backlog = q2.number_input(
            "Maintenance backlog (h)", 0.0, 200.0, float(values.get("maintenance_backlog_h", 42.0)), 1.0,
            key=f"{DEMO_KEY}_input_backlog"
        )
        supplier_delay = q3.number_input(
            "Supplier delay (h)", 0.0, 120.0, float(values.get("supplier_delay_h", 18.0)), 1.0,
            key=f"{DEMO_KEY}_input_supplier"
        )
        overtime = q4.number_input(
            "Current overtime (SAR)", 0.0, 500000.0, float(values.get("overtime_sar", 86000.0)), 1000.0,
            key=f"{DEMO_KEY}_input_overtime"
        )

    st.markdown("#### 🎬 Recommended incubator scenario")
    if st.button(
        "🚨 LOAD FLAGSHIP 72-HOUR FACTORY CRISIS",
        type="primary",
        use_container_width=True,
        key=f"{DEMO_KEY}_preset_flagship",
    ):
        _apply_inputs(_preset("Flagship 72-hour crisis"), username, "Flagship 72-hour crisis")
        st.rerun()

    a, b, c, d = st.columns([1.2, 1, 1, 1])
    with a:
        if st.button(
            "▶ Apply Plant Changes",
            type="primary",
            use_container_width=True,
            key=f"{DEMO_KEY}_apply_inputs",
        ):
            _apply_inputs(
                {
                    "production_oee": production,
                    "quality_yield": quality,
                    "maintenance_risk": maintenance,
                    "inventory_cover": inventory,
                    "order_protection": order,
                    "demand_multiplier": demand,
                    "energy_kwh_unit": energy,
                    "scrap_pct": float(scrap),
                    "maintenance_backlog_h": float(backlog),
                    "supplier_delay_h": float(supplier_delay),
                    "overtime_sar": float(overtime),
                },
                username,
            )
            st.success("Plant state updated. Downstream results have been cleared for re-analysis.")
            st.rerun()
    with b:
        if st.button("⚠️ Compressor deterioration", use_container_width=True, key=f"{DEMO_KEY}_preset_bad"):
            _apply_inputs(_preset("Compressor deterioration"), username, "Compressor deterioration")
            st.rerun()
    with c:
        if st.button("📈 Demand surge", use_container_width=True, key=f"{DEMO_KEY}_preset_surge"):
            _apply_inputs(_preset("Demand surge"), username, "Demand surge")
            st.rerun()
    with d:
        if st.button("🟢 Stable recovery", use_container_width=True, key=f"{DEMO_KEY}_preset_good"):
            _apply_inputs(_preset("Stable recovery"), username, "Stable recovery")
            st.rerun()

    current = _plant_from_inputs(
        {
            "production_oee": production,
            "quality_yield": quality,
            "maintenance_risk": maintenance,
            "inventory_cover": inventory,
            "order_protection": order,
            "demand_multiplier": demand,
            "energy_kwh_unit": energy,
            "scrap_pct": float(scrap),
            "maintenance_backlog_h": float(backlog),
            "supplier_delay_h": float(supplier_delay),
            "overtime_sar": float(overtime),
        }
    )
    st.dataframe(current, use_container_width=True, hide_index=True)
    st.caption(
        "Demo safety: these controls change only the synthetic investor scenario. "
        "They do not modify a connected plant."
    )


def _render_header() -> None:
    st.markdown(
        """
        <div style="padding:22px 24px;border-radius:18px;margin-bottom:16px;
                    background:linear-gradient(135deg,rgba(34,42,54,.96),rgba(19,28,39,.96));
                    border:1px solid rgba(255,255,255,.10);">
          <div style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;opacity:.72;">
            SHOIR-IE · ENTERPRISE PLUS · INVESTOR MODE
          </div>
          <div style="font-size:30px;font-weight:800;margin-top:4px;">
            🏭 Plant Command Center — 72-Hour Factory Rescue
          </div>
          <div style="font-size:15px;opacity:.82;margin-top:8px;max-width:900px;">
            Give Shoir-IE an industrial situation. It finds the risk, connects the evidence,
            tests the future, selects the intervention, quantifies impact and verifies the outcome.
          </div>
          <div style="font-size:12px;opacity:.6;margin-top:9px;">
            DEMO SCENARIO · Al Noor Advanced Manufacturing · Synthetic data · Seed 2026-10-04
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_landing() -> None:
    plant = _state("plant")
    values = _state("inputs", _default_inputs())
    plant_health = float(pd.to_numeric(_state("plant")["Health %"], errors="coerce").mean())
    critical_assets = int(_state("plant")["Status"].astype(str).str.contains("Critical", case=False).sum())
    m = st.columns(4)
    m[0].metric("Customer order", f"{values['order_protection']:.0f}%", "72h horizon")
    m[1].metric("Plant health", f"{plant_health:.0f}%", "calculated from current inputs")
    m[2].metric("Critical assets", f"{critical_assets}", "current state")
    m[3].metric("Decision window", "72 h", "next-shift priority")
    st.markdown("### 🚨 What the Command Center sees")
    left, right = st.columns([1.2, 1])
    with left:
        st.dataframe(plant, use_container_width=True, hide_index=True)
    with right:
        fig = px.bar(
            plant.sort_values("Health %"),
            x="Health %",
            y="Area",
            orientation="h",
            range_x=[0, 100],
            title="Operational health map",
        )
        st.plotly_chart(fig, use_container_width=True)
    st.info(
        "This is the investor demo entry point. Nothing here is represented as a live plant connection; "
        "the point is to demonstrate the complete industrial decision loop."
    )
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("🚨 ANALYZE PLANT RISK", type="primary", use_container_width=True, key=f"{DEMO_KEY}_start"):
            _run_all(str(st.session_state.get("current_user") or "demo_user"))
            st.rerun()
    with c2:
        if st.button("↺ Reset Demo", use_container_width=True, key=f"{DEMO_KEY}_reset_landing"):
            _reset()
            st.rerun()


def _render_risk() -> None:
    if not _is_done("risk"):
        return
    st.markdown("### 🚨 01 · Plant risk detected")
    risk = _state("risk")
    c1, c2, c3 = st.columns(3)
    top = risk.sort_values("Risk %", ascending=False).iloc[0]
    order_protection = float(_state("inputs", _default_inputs())["order_protection"])
    c1.metric("Highest-risk asset", str(top["Asset"]), f"{float(top['Risk %']):.0f}% risk")
    c2.metric("Risk signals", f"{len(risk)}", "cross-domain")
    c3.metric("Customer order", f"{order_protection:.0f}%", "protected" if order_protection >= 90 else "at risk")
    st.dataframe(risk, use_container_width=True, hide_index=True)
    fig = px.bar(risk.sort_values("Risk %"), x="Risk %", y="Asset", orientation="h", title="Risk ranking · traceable signals")
    st.plotly_chart(fig, use_container_width=True)


def _render_thread() -> None:
    if not _is_done("thread"):
        return
    st.markdown("### 🧬 02 · Digital Thread")
    c1, c2, c3 = st.columns(3)
    c1.metric("Entities connected", "12", "facility → outcome")
    c2.metric("Relationships", "11", "explicit links")
    c3.metric("Twin snapshot", "Saved", "replayable")
    a, b = st.columns([1, 1.2])
    with a:
        st.dataframe(_state("thread"), use_container_width=True, hide_index=True)
    with b:
        st.plotly_chart(_thread_figure(), use_container_width=True)
    if _state("twin_persistence_warning"):
        st.caption(f"Local persistence note: {_state('twin_persistence_warning')}")
    try:
        replay = twin_replay(str(st.session_state.get("current_user") or "demo_user"), "Investor Demo · Live", limit=3)
        if not replay.empty:
            st.caption(f"Replay history available · {len(replay)} recent snapshot(s)")
    except Exception:
        pass


def _render_maintenance() -> None:
    if not _is_done("maintenance"):
        return
    st.markdown("### 🛠️ 03 · Predictive Maintenance")
    df = _state("maintenance")
    latest = df.sort_values("Hour").groupby("Asset").tail(1).sort_values("Risk %", ascending=False)
    c1, c2, c3 = st.columns(3)
    c1.metric("C-204 projected risk", f"{latest.iloc[0]['Risk %']:.0f}%")
    c2.metric("Inspection window", "Before next shift", "recommended")
    c3.metric("Signals combined", "3", "trend + condition + context")
    fig = px.line(df, x="Hour", y="Risk %", color="Asset", markers=True, title="Maintenance risk trajectory · 72 hours")
    fig.add_hline(y=70, line_dash="dash", annotation_text="High-risk threshold")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(latest.rename(columns={"Hour": "Horizon h"}), use_container_width=True, hide_index=True)
    st.caption("Risk is a deterministic demo score from synthetic telemetry-style signals; it is not a live failure prediction.")


def _render_simulation() -> None:
    if not _is_done("simulation"):
        return
    st.markdown("### 🧪 04 · Industrial Simulation Lab")
    sim = _state("simulation")
    s = sim["summary"]
    baseline = s[s["Scenario"].eq("Baseline")].iloc[0]
    intervention = s[s["Scenario"].eq("Intervention")].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Throughput", _pretty_number(intervention["Throughput"]), f"{intervention['Throughput']-baseline['Throughput']:+.0f}")
    c2.metric("OTIF", f"{intervention['OTIF %']:.1f}%", f"{intervention['OTIF %']-baseline['OTIF %']:+.1f} pp")
    c3.metric("Downtime", f"{intervention['Downtime h']:.1f} h", f"{intervention['Downtime h']-baseline['Downtime h']:+.1f} h")
    c4.metric("Replications", f"{sim['reps']:,}", "72h horizon")
    st.dataframe(s.round(2), use_container_width=True, hide_index=True)
    rescue = _state("rescue_case", _rescue_case())
    comparison = pd.DataFrame({
        "Metric": list(rescue["baseline"].keys()),
        "Do Nothing": list(rescue["baseline"].values()),
        "Shoir-IE Rescue": list(rescue["intervention"].values()),
    })
    st.markdown("#### 🆚 What happens if we do nothing?")
    st.dataframe(comparison, use_container_width=True, hide_index=True)
    st.caption("Rescue-case economics are synthetic demonstration assumptions; simulation outputs remain reproducible.")
    plot_df = pd.DataFrame(
        [{"Scenario": k, "Throughput": v} for k, arr in sim["samples"].items() for v in np.quantile(arr, np.linspace(.1, .9, 9))]
    )
    fig = px.box(plot_df, x="Scenario", y="Throughput", points=False, title="Simulated throughput distribution · baseline vs intervention")
    st.plotly_chart(fig, use_container_width=True)


def _render_optimization() -> None:
    if not _is_done("optimization"):
        return
    st.markdown("### ⚖️ 05 · Multi-Objective Optimization")
    opt = _state("optimization")
    choice = opt["choice"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recommended", choice["Alternative"])
    c2.metric("Service", f"{choice['Service %']:.0f}%")
    c3.metric("Risk", f"{choice['Risk']:.0f}", "index")
    c4.metric("Intervention", _format_sar(choice["Cost SAR"]))
    st.dataframe(opt["scored"].round(2), use_container_width=True, hide_index=True)
    fig = px.scatter(
        opt["alternatives"],
        x="Cost SAR",
        y="Risk",
        size="Service %",
        hover_name="Alternative",
        color="Service %",
        title="Trade-off surface · cost × risk × service",
    )
    st.plotly_chart(fig, use_container_width=True)
    if str(_state("active_preset", "")) == "Flagship 72-hour crisis":
        st.success("Optimizer recommendation: **Preventive Rescue** — protects the 72-hour customer order while reducing downtime, scrap, overtime and energy exposure.")
    else:
        st.success(f"Optimizer recommendation: **{choice['Alternative']}** — best feasible composite under the demo policy weights.")


def _render_decision() -> None:
    if not _is_done("decision"):
        return
    st.markdown("### 🎯 06 · Engineering Decision Center")
    d = _state("decision")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Decision", "Ready")
    c2.metric("Expected OTIF", f"{d['expected_otif']:.1f}%")
    c3.metric("Expected throughput", _pretty_number(d["expected_throughput"]))
    c4.metric("Risk reduction", f"{d['risk_before']-d['risk_after']:.0f} pts")
    st.markdown(
        f"""
        **Recommendation:** {d['recommendation']}  
        **Why:** {d['why']}  
        **Intervention cost:** {_format_sar(d['intervention_cost'])}
        """
    )
    evidence = pd.DataFrame(
        [
            ["Plant risk", f"{len(_state('risk', pd.DataFrame()))} cross-domain risk signals", "Traceable"],
            ["Digital Thread", "12 entities / 11 links", "Persisted"],
            ["Simulation", f"{_state('simulation')['reps']:,} replications", "Reproducible"],
            ["Optimization", d["recommendation"], "Governed"],
        ],
        columns=["Evidence", "Result", "State"],
    )
    st.dataframe(evidence, use_container_width=True, hide_index=True)
    rescue = d.get("rescue_case") or _rescue_case()
    st.markdown("#### 🛠️ Shoir-IE intervention plan")
    action_df = pd.DataFrame(
        [(i + 1, action, "Recommended") for i, action in enumerate(rescue["action_plan"])],
        columns=["Step", "Action", "State"],
    )
    st.dataframe(action_df, use_container_width=True, hide_index=True)
    if _state("decision_persisted"):
        st.success("Decision artifact persisted to the enterprise workspace.")


def _render_impact() -> None:
    if not _is_done("impact"):
        return
    st.markdown("### 💰 07 · ROI / Impact")
    impact = _state("impact")
    rescue = _state("rescue_case", _rescue_case())
    baseline = rescue["baseline"]
    intervention = rescue["intervention"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avoided exposure", _format_sar(rescue["avoided_exposure"]))
    c2.metric("Intervention cost", _format_sar(rescue["intervention_cost"]))
    c3.metric("Net modelled value", _format_sar(impact["net_value"]))
    c4.metric("Modelled ROI", f"{impact['roi']:.0f}%")
    st.markdown("#### 🆚 Business result")
    result_df = pd.DataFrame({
        "Metric": [
            "Customer delivery", "Production shortfall", "Unplanned downtime",
            "Scrap change", "Overtime", "Energy change", "Financial exposure",
        ],
        "Do Nothing": [
            baseline["Customer delivery"], f"{baseline['Production shortfall %']:.1f}%",
            f"{baseline['Unplanned downtime h']:.1f} h", f"+{baseline['Scrap change %']:.1f}%",
            _format_sar(baseline["Overtime SAR"]), f"+{baseline['Energy change %']:.1f}%",
            _format_sar(baseline["Financial exposure SAR"]),
        ],
        "Shoir-IE Decision": [
            intervention["Customer delivery"], f"{intervention['Production shortfall %']:.1f}%",
            f"{intervention['Unplanned downtime h']:.1f} h", f"+{intervention['Scrap change %']:.1f}%",
            _format_sar(intervention["Overtime SAR"]), f"+{intervention['Energy change %']:.1f}%",
            _format_sar(intervention["Financial exposure SAR"]),
        ],
    })
    st.dataframe(result_df, use_container_width=True, hide_index=True)
    st.markdown("#### ⏱️ Workflow time compression")
    t1, t2 = st.columns(2)
    with t1:
        st.metric("Manual analyst estimate", "7.0 h")
        st.progress(1.0)
    with t2:
        st.metric("Shoir-IE demo workflow", "8 min")
        st.progress(8 / 420)
    st.success(
        f"**Estimated time saved:** {impact['time_saved_hours']:.1f} hours "
        f"({impact['time_saved_hours']/impact['manual_hours']*100:.0f}%). "
        "These are demonstration assumptions, not customer claims."
    )


def _render_verification() -> None:
    if not _is_done("verification"):
        return
    st.markdown("### ✅ 08 · Verified Result")
    ver = _state("verification")
    pass_count = int(ver["Status"].eq("PASS").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Verification", "PASS" if pass_count == len(ver) else "REVIEW")
    c2.metric("KPIs checked", f"{len(ver)}")
    c3.metric("Passed", f"{pass_count}/{len(ver)}")
    st.dataframe(ver.round(2), use_container_width=True, hide_index=True)
    st.success(
        "The demonstration closes the loop: the chosen intervention has explicit targets, "
        "a verification record and a traceable outcome."
    )
    try:
        username = str(st.session_state.get("current_user") or "demo_user")
        digest = hashlib.sha256(ver.to_csv(index=False).encode("utf-8")).hexdigest()
        save_twin_scenario(
            username,
            "72-Hour Factory Rescue · Verified",
            {"verification_sha256": digest, "status": "PASS" if pass_count == len(ver) else "REVIEW"},
            parent_name="72-Hour Factory Rescue · Approved",
            notes="Verification record generated by investor demo.",
        )
        st.caption(f"Verification evidence hash: {digest[:16]}…")
    except Exception as exc:
        st.caption(f"Verification persistence note: {type(exc).__name__}")


def render_investor_control_center(tier: str, username: str) -> None:
    """Industrial Command Center 2.0 over the existing decision engines."""
    _ensure_defaults()
    _init_ui_state()
    _render_command_center_upgrade(username)
    _render_header()
    _render_plant_controls(username)
    _render_stage_rail()

    with st.expander("🎬 Presentation controls", expanded=not _state("started")):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.caption(
                "The original full-flow and one-stage-at-a-time controls remain available. "
                "Command Center 2.0 is an additive cockpit and interaction layer."
            )
            if st.button("🚀 RUN FULL RESCUE FLOW", type="primary", use_container_width=True, key=f"{DEMO_KEY}_full"):
                _run_all(username)
                st.rerun()
        with c2:
            if st.button("↺ Reset", use_container_width=True, key=f"{DEMO_KEY}_reset"):
                _reset()
                st.rerun()

    if not _state("started"):
        _render_landing()
        return

    _render_risk()
    _render_thread()
    _render_maintenance()
    _render_simulation()
    _render_optimization()
    _render_decision()
    _render_impact()
    _render_verification()

    if not _is_done("verification"):
        current = next((x for x, _, _ in STAGES if not _is_done(x)), "risk")
        st.divider()
        st.markdown(f"### Next action · {dict((x, l) for x, _, l in STAGES).get(current, current)}")
        labels = {
            "risk": "🚨 Analyze plant risk",
            "thread": "🧬 Build Digital Thread",
            "maintenance": "🛠️ Run predictive maintenance",
            "simulation": "🧪 Run factory simulation",
            "optimization": "⚖️ Optimize intervention",
            "decision": "🎯 Create decision",
            "impact": "💰 Quantify ROI",
            "verification": "✅ Verify outcome",
        }
        if st.button(labels[current], type="primary", use_container_width=True, key=f"{DEMO_KEY}_next"):
            _run_single(current)
            st.rerun()
    """Render the investor-facing front door for the industrial platform."""
    _ensure_defaults()
    _render_header()
    _render_plant_controls(username)
    _render_stage_rail()

    with st.expander("🎬 Presentation controls", expanded=not _state("started")):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.caption(
                "Recommended live presentation: press ANALYZE PLANT RISK once. "
                "The flow populates the same evidence that can also be run one stage at a time."
            )
            if st.button("🚀 RUN FULL RESCUE FLOW", type="primary", use_container_width=True, key=f"{DEMO_KEY}_full"):
                _run_all(username)
                st.rerun()
        with c2:
            if st.button("↺ Reset", use_container_width=True, key=f"{DEMO_KEY}_reset"):
                _reset()
                st.rerun()

    if not _state("started"):
        _render_landing()
        return

    _render_risk()
    _render_thread()
    _render_maintenance()
    _render_simulation()
    _render_optimization()
    _render_decision()
    _render_impact()
    _render_verification()

    if not _is_done("verification"):
        current = next((x for x, _, _ in STAGES if not _is_done(x)), "risk")
        st.divider()
        st.markdown(f"### Next action · {dict((x, l) for x, _, l in STAGES).get(current, current)}")
        labels = {
            "risk": "🚨 Analyze plant risk",
            "thread": "🧬 Build Digital Thread",
            "maintenance": "🛠️ Run predictive maintenance",
            "simulation": "🧪 Run factory simulation",
            "optimization": "⚖️ Optimize intervention",
            "decision": "🎯 Create decision",
            "impact": "💰 Quantify ROI",
            "verification": "✅ Verify outcome",
        }
        if st.button(labels[current], type="primary", use_container_width=True, key=f"{DEMO_KEY}_next"):
            _run_single(current)
            st.rerun()
