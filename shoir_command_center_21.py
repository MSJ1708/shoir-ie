"""Industrial Command Center 2.1 interaction layer.

This module is deliberately additive: it reuses the existing investor demo state
and calculation engines while providing a richer operator experience around them.
Synthetic/modelled values remain clearly identified as demo assumptions.
"""
from __future__ import annotations

import inspect
import time
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

import shoir_investor_demo as demo


CC21_KEY = "industrial_command_center_21"
ROLE_OPTIONS = [
    "Command Center",
    "Executive",
    "Engineering",
    "Maintenance",
    "Supply Chain",
    "Quality",
    "Sustainability",
]
FOCUS_OPTIONS = [
    "Cross-domain",
    "Production",
    "Maintenance",
    "Quality",
    "Supply",
    "Inventory",
    "Energy",
    "Workforce",
    "Customer",
]

FLOOR = {
    "Receiving & Stores": (0, 75, 24, 17, "Supply"),
    "Production Line 1": (28, 52, 20, 25, "Production"),
    "Production Line 2": (51, 52, 20, 25, "Production"),
    "Production Line 3": (74, 52, 20, 25, "Production"),
    "Quality": (28, 22, 20, 19, "Quality"),
    "Maintenance": (51, 22, 20, 19, "Maintenance"),
    "Utilities": (74, 22, 20, 19, "Energy"),
    "Shipping": (0, 22, 24, 19, "Customer"),
}
ENTITY_POINTS = {
    "FAC-RYD-01": ("Receiving & Stores", 10, 83),
    "LINE-01": ("Production Line 1", 38, 64),
    "LINE-02": ("Production Line 2", 61, 64),
    "LINE-03": ("Production Line 3", 84, 64),
    "C-204": ("Maintenance", 61, 32),
    "Q-07": ("Quality", 38, 32),
    "SUP-18": ("Receiving & Stores", 18, 83),
    "MAT-BRG-08": ("Receiving & Stores", 18, 68),
    "MW-BACKLOG": ("Maintenance", 69, 32),
    "ENERGY-01": ("Utilities", 85, 32),
    "WO-4821": ("Shipping", 12, 32),
    "OUT-72H": ("Shipping", 12, 30),
}


def _ui_get(key: str, default: Any = None) -> Any:
    return st.session_state.get(f"{CC21_KEY}_{key}", default)


def _ui_set(key: str, value: Any) -> None:
    st.session_state[f"{CC21_KEY}_{key}"] = value


def _supports_kw(fn: Any, name: str) -> bool:
    try:
        return name in inspect.signature(fn).parameters
    except Exception:
        return False


def _button(label: str, *, key: str, shortcut: str | None = None, **kwargs: Any) -> bool:
    if shortcut and _supports_kw(st.button, "shortcut"):
        kwargs["shortcut"] = shortcut
    return bool(st.button(label, key=key, **kwargs))


def _plotly(fig: go.Figure, *, key: str, config: dict[str, Any] | None = None) -> Any:
    kwargs: dict[str, Any] = {
        "use_container_width": True,
        "key": key,
        "config": config or {"displayModeBar": False, "displaylogo": False},
    }
    if _supports_kw(st.plotly_chart, "on_select"):
        kwargs["on_select"] = "rerun"
        kwargs["selection_mode"] = ["points"]
    return st.plotly_chart(fig, **kwargs)


def _selected_point(event: Any) -> dict[str, Any] | None:
    if event is None:
        return None
    try:
        selection = getattr(event, "selection", None)
        if selection is None and isinstance(event, dict):
            selection = event.get("selection")
        points = selection.get("points", []) if isinstance(selection, dict) else getattr(selection, "points", [])
        if points:
            point = points[0]
            if isinstance(point, dict):
                return point
            return dict(point)
    except Exception:
        return None
    return None


def _ensure_state() -> None:
    defaults = {
        "palette_open": False,
        "inspector_open": True,
        "inspector_id": "C-204",
        "role": "Command Center",
        "focus": "Cross-domain",
        "risk_threshold": 70.0,
        "service_target": 95.0,
        "cost_weight": 25.0,
        "risk_weight": 30.0,
        "service_weight": 35.0,
        "carbon_weight": 10.0,
        "last_action": "",
        "floor_metric": "Health",
        "thread_selected": "",
        "policy_open": False,
        "alternatives_open": False,
        "governance_open": False,
    }
    for key, value in defaults.items():
        if _ui_get(key) is None:
            _ui_set(key, value)


def _inputs() -> dict[str, float]:
    return dict(demo._state("inputs", demo._default_inputs()))


@st.cache_data(show_spinner=False, ttl=3600)
def _dynamic_rescue_model(values_tuple: tuple[tuple[str, float], ...]) -> dict[str, Any]:
    v = dict(values_tuple)
    ref = demo._default_inputs()

    def ratio(value: float, reference: float, low: float = 0.25, high: float = 2.5) -> float:
        return float(np.clip(value / reference if reference else 1.0, low, high))

    severity = (
        0.22 * ratio(max(1.0, 100.0 - v["production_oee"]), max(1.0, 100.0 - ref["production_oee"]))
        + 0.24 * ratio(v["maintenance_risk"], ref["maintenance_risk"])
        + 0.14 * ratio(ref["inventory_cover"], max(0.25, v["inventory_cover"]))
        + 0.12 * ratio(v.get("supplier_delay_h", 18.0), ref.get("supplier_delay_h", 18.0))
        + 0.10 * ratio(v.get("scrap_pct", 3.8), ref.get("scrap_pct", 3.8))
        + 0.10 * ratio(v.get("maintenance_backlog_h", 42.0), ref.get("maintenance_backlog_h", 42.0))
        + 0.08 * ratio(max(0.05, v["energy_kwh_unit"] - 1.0), max(0.05, ref["energy_kwh_unit"] - 1.0))
    )

    baseline = {
        "Customer delivery": "AT RISK" if v["order_protection"] < 90 else "PROTECTED",
        "Production shortfall %": round(9.4 * severity, 1),
        "Unplanned downtime h": round(14.2 * severity, 1),
        "Scrap change %": round(max(0.2, 3.8 * (0.70 + 0.30 * severity)), 1),
        "Overtime SAR": round(max(0.0, v.get("overtime_sar", 86000.0) * (0.70 + 0.30 * severity)), 0),
        "Energy change %": round(max(0.3, 8.1 * (0.55 + 0.45 * severity)), 1),
        "Financial exposure SAR": round(1520000.0 * severity, 0),
    }

    maintenance_delta = float(np.clip((ref["maintenance_risk"] - v["maintenance_risk"]) / 50.0, -1.0, 1.0))
    inventory_delta = float(np.clip((v["inventory_cover"] - ref["inventory_cover"]) / 3.0, -1.0, 1.0))
    supplier_delta = float(np.clip((v.get("supplier_delay_h", 18.0) - ref.get("supplier_delay_h", 18.0)) / 18.0, -1.0, 1.0))
    backlog_delta = float(np.clip((v.get("maintenance_backlog_h", 42.0) - ref.get("maintenance_backlog_h", 42.0)) / 42.0, -1.0, 1.0))
    recovery = float(np.clip(
        1.0
        + 0.12 * maintenance_delta
        + 0.08 * inventory_delta
        - 0.06 * supplier_delta
        - 0.04 * backlog_delta,
        0.78,
        1.22,
    ))

    intervention = {
        "Customer delivery": "PROTECTED" if baseline["Production shortfall %"] <= 6.0 else "AT RISK",
        "Production shortfall %": round(max(0.3, baseline["Production shortfall %"] * 0.085106 / recovery), 1),
        "Unplanned downtime h": round(max(1.5, baseline["Unplanned downtime h"] * 0.21831 / recovery), 1),
        "Scrap change %": round(max(0.2, baseline["Scrap change %"] * 0.236842 / recovery), 1),
        "Overtime SAR": round(max(12000.0, baseline["Overtime SAR"] * 0.337209 / recovery), 0),
        "Energy change %": round(max(0.5, baseline["Energy change %"] * 0.296296 / recovery), 1),
        "Financial exposure SAR": round(max(50000.0, baseline["Financial exposure SAR"] * 0.138158 / recovery), 0),
    }
    intervention["Customer delivery"] = (
        "PROTECTED" if intervention["Production shortfall %"] <= 2.0 and v["order_protection"] >= 80
        else "AT RISK"
    )

    avoided = max(0.0, baseline["Financial exposure SAR"] - intervention["Financial exposure SAR"])
    return {
        "baseline": baseline,
        "intervention": intervention,
        "intervention_cost": 152000.0,
        "avoided_exposure": avoided,
        "net_value": max(0.0, avoided - 152000.0),
        "roi": max(0.0, (avoided - 152000.0) / 152000.0 * 100.0),
        "severity": severity,
        "recovery": recovery,
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


def _dynamic_rescue(values: dict[str, float] | None = None) -> dict[str, Any]:
    v = values or _inputs()
    return _dynamic_rescue_model(tuple(sorted((str(k), float(val)) for k, val in v.items())))


def _policy_alternatives(values: dict[str, float]) -> pd.DataFrame:
    v = values
    risk = float(v["maintenance_risk"])
    service = float(np.clip(v["order_protection"], 50.0, 99.0))
    base_cost = 152000.0
    rows = [
        ["Do Nothing", 0.0, max(5.0, risk + 17.0), max(45.0, service - 6.0), 1190.0, "Accept current exposure"],
        ["Preventive Rescue", base_cost, max(5.0, risk - 28.0), min(99.0, service + 7.0), 1120.0, "C-204 micro-window + bearing reserve"],
        ["Reroute + Rescue", 167000.0, max(4.0, risk - 34.0), min(99.0, service + 9.0), 1180.0, "Rescue + line/customer reroute"],
        ["Capacity Expansion", 210000.0, max(3.0, risk - 24.0), min(99.0, service + 11.0), 1220.0, "Temporary capacity uplift"],
    ]
    df = pd.DataFrame(rows, columns=["Alternative", "Cost SAR", "Risk", "Service %", "Carbon kg", "Action"])
    weights = {
        "cost": float(_ui_get("cost_weight", 25.0)),
        "risk": float(_ui_get("risk_weight", 30.0)),
        "service": float(_ui_get("service_weight", 35.0)),
        "carbon": float(_ui_get("carbon_weight", 10.0)),
    }
    total = sum(weights.values()) or 1.0
    for key in weights:
        weights[key] = weights[key] / total
    cost_max = max(float(df["Cost SAR"].max()), 1.0)
    carbon_max = max(float(df["Carbon kg"].max()), 1.0)
    df["Policy score"] = (
        weights["cost"] * (1.0 - df["Cost SAR"] / cost_max)
        + weights["risk"] * (1.0 - df["Risk"] / 140.0)
        + weights["service"] * (df["Service %"] / 100.0)
        + weights["carbon"] * (1.0 - df["Carbon kg"] / carbon_max)
    ) * 100.0
    service_target = float(_ui_get("service_target", 95.0))
    if float(v["order_protection"]) < service_target:
        df.loc[df["Service %"] < service_target, "Policy score"] -= 20.0
        df.loc[(df["Alternative"] == "Do Nothing") & (df["Service %"] < service_target), "Policy score"] -= 60.0
    return df.sort_values(["Policy score", "Service %"], ascending=[False, False]).reset_index(drop=True)


def _open_inspector(entity_id: str) -> None:
    _ui_set("inspector_id", str(entity_id))
    _ui_set("inspector_open", True)


def _build_thread_graph() -> go.Figure:
    labels = [
        "Facility", "Line 2", "Compressor C-204", "Bearing", "72h Order",
        "Quality", "Supplier", "Workforce", "Energy", "Production Plan",
        "Decision", "Outcome",
    ]
    x = [0.02, 0.18, 0.38, 0.38, 0.18, 0.38, 0.38, 0.38, 0.38, 0.58, 0.78, 0.95]
    y = [0.50, 0.70, 0.85, 0.55, 0.30, 0.30, 0.10, 0.10, 0.95, 0.70, 0.50, 0.50]
    edges = [(0,1),(1,2),(2,10),(3,2),(4,10),(5,10),(6,4),(7,10),(2,8),(1,9),(9,11),(10,11)]
    fig = go.Figure()
    for a, b in edges:
        fig.add_trace(go.Scatter(
            x=[x[a], x[b]], y=[y[a], y[b]], mode="lines",
            line=dict(width=2), hoverinfo="none", showlegend=False,
        ))
    risk_map = {
        "Compressor C-204": 90.0,
        "Line 2": max(5.0, 100.0 - _inputs()["production_oee"]),
        "Bearing": max(10.0, 75.0 - _inputs()["inventory_cover"] * 8.0),
    }
    sizes = []
    custom = []
    for label in labels:
        sizes.append(26 if label in risk_map else 19)
        custom.append(label)
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="markers+text", text=labels, textposition="bottom center",
        marker=dict(size=sizes, line=dict(width=1)),
        customdata=custom,
        hovertemplate="<b>%{customdata}</b><extra>Click to inspect</extra>",
        showlegend=False,
    ))
    fig.update_layout(
        title="Interactive Digital Thread · click a node to inspect it",
        height=430, xaxis=dict(visible=False, range=[-0.05,1.03]),
        yaxis=dict(visible=False, range=[-0.05,1.05]),
        margin=dict(l=10,r=10,t=55,b=20),
    )
    return fig


def _thread_label_to_entity(label: str) -> str:
    mapping = {
        "Facility": "FAC-RYD-01", "Line 2": "LINE-02",
        "Compressor C-204": "C-204", "Bearing": "MAT-BRG-08",
        "72h Order": "WO-4821", "Quality": "Q-07",
        "Supplier": "SUP-18", "Workforce": "MW-BACKLOG",
        "Energy": "ENERGY-01", "Production Plan": "LINE-02",
        "Decision": "OUT-72H", "Outcome": "OUT-72H",
    }
    return mapping.get(label, "C-204")


def _build_floor_map() -> go.Figure:
    values = _inputs()
    fig = go.Figure()
    for name, (x, y, w, h, domain) in FLOOR.items():
        health = {
            "Production Line 1": 93.0,
            "Production Line 2": float(values["production_oee"]),
            "Production Line 3": 88.0,
            "Receiving & Stores": float(np.clip(values["inventory_cover"] / 5.0 * 100.0, 20, 100)),
            "Quality": float(np.clip(100 - values.get("scrap_pct", 3.8) * 12, 20, 100)),
            "Maintenance": float(np.clip(100 - values["maintenance_risk"] * 0.55, 10, 100)),
            "Utilities": float(np.clip(100 - max(0, values["energy_kwh_unit"] - 1.0) * 120, 10, 100)),
            "Shipping": float(values["order_protection"]),
        }[name]
        metric = str(_ui_get("floor_metric", "Health"))
        value = health if metric == "Health" else 100.0 - health
        fig.add_trace(go.Scatter(
            x=[x + w/2], y=[y + h/2], mode="markers+text",
            marker=dict(size=44, opacity=0.75),
            text=[name], textposition="middle center",
            customdata=[[name, domain, round(health,1)]],
            hovertemplate="<b>%{customdata[0]}</b><br>Domain: %{customdata[1]}<br>Health: %{customdata[2]}%<extra>Click to focus</extra>",
            name=name, showlegend=False,
        ))
        fig.add_shape(type="rect", x0=x, y0=y, x1=x+w, y1=y+h,
                      line=dict(width=2), fillcolor="rgba(120,140,160,0.08)")
        fig.add_annotation(x=x+w/2, y=y+h-2, text=f"{value:.0f}%", showarrow=False, font=dict(size=11))
    for entity_id, (zone, ex, ey) in ENTITY_POINTS.items():
        domain = FLOOR[zone][4]
        fig.add_trace(go.Scatter(
            x=[ex], y=[ey], mode="markers",
            marker=dict(size=11, opacity=0.95, symbol="diamond"),
            customdata=[["ENTITY", entity_id, domain]],
            hovertemplate="<b>%{customdata[1]}</b><br>Domain: %{customdata[2]}<extra>Click to inspect</extra>",
            name=entity_id, showlegend=False,
        ))
    fig.update_layout(
        title="Plant spatial situation map · synthetic floor plan · click a zone or entity",
        height=480, xaxis=dict(visible=False, range=[-3,100]),
        yaxis=dict(visible=False, range=[0,100]), margin=dict(l=5,r=5,t=55,b=5),
    )
    return fig


def _entity_from_floor(point: dict[str, Any] | None) -> str | None:
    if not point:
        return None
    custom = point.get("customdata")
    if isinstance(custom, (list, tuple)) and custom:
        if len(custom) >= 2 and str(custom[0]) == "ENTITY":
            return str(custom[1])
        zone = str(custom[0])
        by_zone = {
            "Production Line 1": "LINE-01", "Production Line 2": "LINE-02",
            "Production Line 3": "LINE-03", "Maintenance": "C-204",
            "Quality": "Q-07", "Utilities": "ENERGY-01",
            "Receiving & Stores": "MAT-BRG-08", "Shipping": "WO-4821",
        }
        return by_zone.get(zone)
    return None


def _role_data(role: str) -> tuple[str, str, list[tuple[str, str, str]], list[str]]:
    v = _inputs()
    rescue = _dynamic_rescue(v)
    if role == "Executive":
        return (
            "72-hour commitment",
            "Decision and financial exposure at a glance.",
            [
                ("Customer protection", f"{v['order_protection']:.0f}%", "target ≥ 95%"),
                ("Avoided exposure", demo._format_sar(rescue["avoided_exposure"]), "modelled"),
                ("Net modelled value", demo._format_sar(rescue["net_value"]), "after intervention"),
                ("Modelled ROI", f"{rescue['roi']:.0f}%", "synthetic case"),
            ],
            ["Review recommendation", "Review evidence", "Open decision governance"],
        )
    if role == "Engineering":
        return (
            "engineering constraints",
            "Capacity, trade-offs and intervention policy.",
            [
                ("Line 2 OEE", f"{v['production_oee']:.1f}%", "constraint"),
                ("Highest risk", f"{v['maintenance_risk']:.0f}%", "C-204"),
                ("Service target", f"{_ui_get('service_target',95.0):.0f}%", "policy"),
                ("Policy focus", f"{_ui_get('risk_weight',30.0):.0f}%", "risk weight"),
            ],
            ["Tune policy", "Compare alternatives", "Run What-If"],
        )
    if role == "Maintenance":
        return (
            "asset reliability",
            "Critical assets, work backlog and intervention timing.",
            [
                ("C-204 risk", f"{v['maintenance_risk']:.0f}%", "critical"),
                ("Backlog", f"{v.get('maintenance_backlog_h',42):.0f} h", "workload"),
                ("Bearing cover", f"{v['inventory_cover']:.1f} d", "spare"),
                ("Inspection", "Next micro-window", "recommended"),
            ],
            ["Inspect C-204", "Open What-If", "Review evidence"],
        )
    if role == "Supply Chain":
        return (
            "supply resilience",
            "Material cover, supplier delay and customer protection.",
            [
                ("Supplier delay", f"{v.get('supplier_delay_h',18):.0f} h", "critical"),
                ("Bearing cover", f"{v['inventory_cover']:.1f} d", "critical spare"),
                ("Customer protection", f"{v['order_protection']:.0f}%", "service"),
                ("Reroute option", "Available", "alternative"),
            ],
            ["Inspect supplier", "Reserve bearing", "Compare reroute"],
        )
    if role == "Quality":
        return (
            "quality stability",
            "Yield, scrap exposure and containment.",
            [
                ("Yield", f"{v['quality_yield']:.1f}%", "current"),
                ("Scrap", f"+{v.get('scrap_pct',3.8):.1f}%", "signal"),
                ("Quality risk", f"{float(demo._risk_analysis(v).loc[3,'Risk %']):.0f}%", "Q-07"),
                ("Containment", "Temporary inspection", "recommended"),
            ],
            ["Inspect Q-07", "Open evidence", "Run What-If"],
        )
    if role == "Sustainability":
        return (
            "resource performance",
            "Energy, carbon trade-offs and resilience.",
            [
                ("Specific energy", f"{v['energy_kwh_unit']:.2f}", "kWh/unit"),
                ("Carbon proxy", f"{float(_policy_alternatives(v)['Carbon kg'].min()):,.0f}", "kg modelled"),
                ("Energy improvement", f"{max(0.0, v['energy_kwh_unit']-max(0.85,v['energy_kwh_unit']-0.08)):.2f}", "kWh/unit"),
                ("Carbon weight", f"{_ui_get('carbon_weight',10.0):.0f}%", "policy"),
            ],
            ["Tune carbon weight", "Compare alternatives", "Explain recommendation"],
        )
    return (
        "cross-domain situation",
        "One operating picture across customer, production, asset, supply and value.",
        [
            ("Customer protection", f"{v['order_protection']:.0f}%", "72h horizon"),
            ("Plant health", f"{pd.to_numeric(demo._plant_from_inputs(v)['Health %']).mean():.0f}%", "calculated"),
            ("C-204 risk", f"{v['maintenance_risk']:.0f}%", "top risk"),
            ("Avoided exposure", demo._format_sar(rescue["avoided_exposure"]), "modelled"),
        ],
        ["Analyze risk", "Run full rescue", "Open What-If"],
    )


def _role_action(action: str) -> None:
    normalized = str(action).strip().lower()
    _ui_set("last_action", action)
    if "what-if" in normalized:
        _ui_set("whatif_open", True)
    elif "evidence" in normalized or "recommendation" in normalized:
        _ui_set("evidence_open", True)
    elif "governance" in normalized:
        _ui_set("governance_open", True)
    elif "policy" in normalized or "carbon weight" in normalized:
        _ui_set("policy_open", True)
    elif "alternative" in normalized or "reroute" in normalized or "compare" in normalized:
        _ui_set("alternatives_open", True)
    elif "c-204" in normalized:
        _open_inspector("C-204")
    elif "bearing" in normalized:
        _open_inspector("MAT-BRG-08")
    elif "supplier" in normalized:
        _open_inspector("SUP-18")
    elif "q-07" in normalized:
        _open_inspector("Q-07")
    elif "risk" in normalized:
        demo._run_single("risk")
    elif "rescue" in normalized:
        demo._run_all(str(st.session_state.get("current_user") or "demo_user"))


def _render_role_workspace() -> None:
    role = str(_ui_get("role", "Command Center"))
    title, subtitle, metrics, actions = _role_data(role)
    st.markdown(f"#### 🎛️ {role} workspace · {title}")
    st.caption(subtitle)
    cols = st.columns(len(metrics))
    for col, (label, value, delta) in zip(cols, metrics):
        with col:
            st.metric(label, value, delta)
    buttons = st.columns(min(3, len(actions)))
    for idx, action in enumerate(actions[:3]):
        with buttons[idx]:
            if st.button(action, use_container_width=True, key=f"{CC21_KEY}_role_action_{idx}_{role}"):
                _role_action(action)
                st.rerun()
    v = _inputs()
    if role == "Executive":
        rescue = _dynamic_rescue(v)
        fig = go.Figure(go.Bar(
            x=["Do Nothing", "Shoir-IE"],
            y=[rescue["baseline"]["Financial exposure SAR"], rescue["intervention"]["Financial exposure SAR"]],
            text=[demo._format_sar(rescue["baseline"]["Financial exposure SAR"]), demo._format_sar(rescue["intervention"]["Financial exposure SAR"])],
            textposition="auto",
        ))
        fig.update_layout(title="Modelled exposure · executive view", yaxis_title="SAR", height=290)
        _plotly(fig, key=f"{CC21_KEY}_role_exec")
    elif role == "Engineering":
        risk = demo._risk_analysis(v).copy().sort_values("Risk %", ascending=False)
        st.dataframe(risk, use_container_width=True, hide_index=True)
        alt = _policy_alternatives(v)
        _plotly(px.scatter(alt, x="Cost SAR", y="Risk", size="Service %", hover_name="Alternative", text="Alternative", title="Engineering trade-off frontier"), key=f"{CC21_KEY}_role_engineering")
    elif role == "Maintenance":
        maintenance = demo._predictive_maintenance(v)
        fig = px.line(maintenance, x="Hour", y="Risk %", color="Asset", markers=True, title="Reliability trajectory · next 72 hours")
        fig.add_hline(y=float(_ui_get("risk_threshold",70.0)), line_dash="dash", annotation_text="Configured alert threshold")
        _plotly(fig, key=f"{CC21_KEY}_role_maintenance")
    elif role == "Supply Chain":
        df = pd.DataFrame({
            "Signal": ["Supplier delay", "Bearing cover", "Customer protection"],
            "Current": [v.get("supplier_delay_h",18.0), v["inventory_cover"], v["order_protection"]],
        })
        st.dataframe(df.round(2), use_container_width=True, hide_index=True)
        _plotly(px.bar(_policy_alternatives(v), x="Alternative", y="Service %", title="Service outcome by intervention"), key=f"{CC21_KEY}_role_supply")
    elif role == "Quality":
        q = float(np.clip(100 - v.get("scrap_pct",3.8) * 12, 20, 100))
        fig = go.Figure(go.Bar(x=["Yield health","Quality health"], y=[v["quality_yield"], q]))
        fig.update_layout(title="Quality stability · current state", yaxis=dict(range=[0,100]), height=290)
        _plotly(fig, key=f"{CC21_KEY}_role_quality")
    elif role == "Sustainability":
        alt = _policy_alternatives(v)
        _plotly(px.scatter(alt, x="Carbon kg", y="Risk", size="Service %", hover_name="Alternative", title="Carbon × risk trade-off"), key=f"{CC21_KEY}_role_sustainability")
    else:
        alt = _policy_alternatives(v)
        fig = px.scatter(alt, x="Risk", y="Service %", size="Cost SAR", hover_name="Alternative",
                         title="Decision frontier · configurable policy weights")
        _plotly(fig, key=f"{CC21_KEY}_role_frontier")


def _render_focus_panel() -> None:
    focus = str(_ui_get("focus", "Cross-domain"))
    risk = demo._risk_analysis(_inputs())
    if focus == "Cross-domain":
        return
    if focus == "Customer":
        st.markdown("#### 🎯 Focus lens · Customer")
        c1,c2,c3 = st.columns(3)
        c1.metric("Order", "WO-4821")
        c2.metric("Protection", f"{_inputs()['order_protection']:.0f}%")
        c3.metric("Target", f"{float(_ui_get('service_target',95.0)):.0f}%")
        if st.button("🔍 Inspect WO-4821", use_container_width=True, key=f"{CC21_KEY}_focus_customer"):
            _open_inspector("WO-4821")
            st.rerun()
        return
    subset = risk[risk["Domain"].astype(str).eq(focus)]
    st.markdown(f"#### 🎯 Focus lens · {focus}")
    if subset.empty:
        st.info(f"No dedicated signal is currently registered for {focus}. The cross-domain graph remains available.")
        return
    row = subset.sort_values("Risk %", ascending=False).iloc[0]
    c1,c2,c3 = st.columns(3)
    c1.metric("Primary signal", str(row["Asset"]))
    c2.metric("Risk", f"{float(row['Risk %']):.0f}%")
    c3.metric("Alert threshold", f"{float(_ui_get('risk_threshold',70.0)):.0f}%")
    if st.button(f"🔍 Inspect {row['Asset']}", use_container_width=True, key=f"{CC21_KEY}_focus_inspect_{focus}"):
        _open_inspector(str(row["Asset"]))
        st.rerun()


def _reset_upgrade_view() -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith(f"{CC21_KEY}_"):
            st.session_state.pop(key, None)
    _ensure_state()


def _render_cockpit() -> None:
    v = _inputs()
    plant = demo._plant_from_inputs(v)
    risk = demo._risk_analysis(v)
    econ = _dynamic_rescue(v)
    alternatives = _policy_alternatives(v)
    choice = alternatives.iloc[0] if not alternatives.empty else None
    recommendation = str(choice["Alternative"]) if choice is not None else "Preventive Rescue"
    conf = demo._cc_confidence_profile(risk)
    plant_health = float(pd.to_numeric(plant["Health %"], errors="coerce").mean())
    top = risk.sort_values("Risk %", ascending=False).iloc[0]

    st.markdown(
        """
        <div style="padding:20px 22px;border-radius:18px;margin-bottom:14px;
                    background:linear-gradient(145deg,rgba(20,27,37,.98),rgba(10,16,24,.98));
                    border:1px solid rgba(148,163,184,.18);">
          <div style="font-size:11px;letter-spacing:.13em;text-transform:uppercase;opacity:.66;">
            INDUSTRIAL OPERATING SYSTEM · COMMAND CENTER 2.1
          </div>
          <div style="font-size:31px;font-weight:850;margin-top:4px;">Plant Situation Room</div>
          <div style="font-size:14px;opacity:.76;margin-top:7px;">
            See the situation, follow the evidence, test the future, choose the intervention,
            quantify value and close the loop — without leaving the Command Center.
          </div>
          <div style="margin-top:10px;font-size:11px;opacity:.62;">
            SYNTHETIC DEMO · 72-HOUR DECISION WINDOW · PARAMETERIZED ECONOMIC MODEL
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Customer commitment", f"{v['order_protection']:.0f}%", "AT RISK" if v["order_protection"] < 90 else "PROTECTED")
    k2.metric("Plant health", f"{plant_health:.0f}%", "calculated")
    k3.metric("Highest risk", str(top["Asset"]), f"{float(top['Risk %']):.0f}%")
    k4.metric("Do-nothing exposure", demo._format_sar(econ["baseline"]["Financial exposure SAR"]), "modelled")
    k5.metric("Avoided exposure", demo._format_sar(econ["avoided_exposure"]), "modelled")

    left,right = st.columns([1.35,1])
    with left:
        st.markdown(f"#### 🧠 Recommended rescue · **{recommendation}**")
        st.success(
            f"Protect the 72-hour customer commitment while balancing cost, risk, service and carbon. "
            f"Modelled exposure moves from {demo._format_sar(econ['baseline']['Financial exposure SAR'])} "
            f"to {demo._format_sar(econ['intervention']['Financial exposure SAR'])}."
        )
        with st.expander("View the 9-step rescue plan", expanded=False):
            for i, action in enumerate(econ["action_plan"], 1):
                st.markdown(f"**{i:02d}** · {action}")
    with right:
        st.markdown("#### 📊 Decision confidence")
        c1,c2 = st.columns(2)
        c1.metric("Model confidence", f"{conf['overall']:.0f}%")
        c2.metric("Evidence completeness", f"{conf['completeness']:.0f}%")
        st.progress(conf["overall"] / 100.0)
        st.caption(
            f"Freshness {conf['freshness']:.0f}% · conflict-free {conf['conflict_free']:.0f}% · "
            f"model stability {conf['model_stability']:.0f}%. Synthetic demo profile."
        )
    driver = risk.nlargest(4, "Risk %")[["Asset","Risk %","Domain","Evidence"]].copy()
    driver["Risk %"] = driver["Risk %"].map(lambda x: f"{float(x):.0f}%")
    with st.expander("🔎 Top risk drivers", expanded=False):
        st.dataframe(driver, use_container_width=True, hide_index=True)
    st.markdown("#### 🧭 Decision pipeline")
    stages = [
        ("01","RISK",demo._is_done("risk")),("02","EVIDENCE",demo._is_done("thread")),
        ("03","FUTURE",demo._is_done("simulation")),("04","ACTION",demo._is_done("decision")),
        ("05","VALUE",demo._is_done("impact")),("06","VERIFY",demo._is_done("verification")),
    ]
    cols=st.columns(6)
    for col,(num,label,done) in zip(cols,stages):
        with col:
            st.caption(("✓ " if done else f"{num} ") + label + (" · COMPLETE" if done else " · PENDING"))

def _render_palette() -> None:
    st.markdown("#### ⌘ Command Center control")
    a, b, c = st.columns([1.3, 1.3, 2.6])
    with a:
        role = st.selectbox("Role", ROLE_OPTIONS, index=ROLE_OPTIONS.index(_ui_get("role","Command Center")),
                            key=f"{CC21_KEY}_role")
        _ui_set("role", role)
    with b:
        focus = st.selectbox("Focus", FOCUS_OPTIONS, index=FOCUS_OPTIONS.index(_ui_get("focus","Cross-domain")),
                             key=f"{CC21_KEY}_focus")
        _ui_set("focus", focus)
    with c:
        launcher_a, launcher_b, launcher_c = st.columns([1,1,1.4])
        with launcher_a:
            opened = _button("⌘K / Ctrl+K", key=f"{CC21_KEY}_shortcut_ctrl", shortcut="Ctrl+K",
                             use_container_width=True, help="Global Command Palette shortcut when supported by this Streamlit version.")
            if opened:
                _ui_set("palette_open", True)
        with launcher_b:
            opened_mac = _button("Mac ⌘K", key=f"{CC21_KEY}_shortcut_cmd", shortcut="Cmd+K",
                                 use_container_width=True)
            if opened_mac:
                _ui_set("palette_open", True)
        with launcher_c:
            if st.button("↺ Reset workspace view", use_container_width=True, key=f"{CC21_KEY}_reset_view"):
                for k in ("role","focus","palette_open","inspector_open","whatif_open","evidence_open","governance_open"):
                    if k in {"role","focus"}:
                        continue
                    _ui_set(k, False)
                st.rerun()

    if _ui_get("palette_open", False):
        with st.container(border=True):
            p1, p2 = st.columns([4,1])
            with p1:
                command = st.text_input(
                    "Command Palette",
                    value=str(_ui_get("palette_command","")),
                    placeholder="Try: risk · full rescue · inspector C-204 · what if · executive · evidence · reset",
                    key=f"{CC21_KEY}_command",
                )
                _ui_set("palette_command", command)
            with p2:
                if st.button("Close", use_container_width=True, key=f"{CC21_KEY}_palette_close"):
                    _ui_set("palette_open", False)
                    st.rerun()
            normalized = str(command).strip().lower()
            last = str(_ui_get("last_command", ""))
            if normalized and normalized != last:
                _ui_set("last_command", normalized)
                if "inspector" in normalized:
                    parts = normalized.split()
                    entity = next((x for x in parts if x.upper() in demo._twin_frame()["ID"].astype(str).str.upper().tolist()), "C-204")
                    _open_inspector(entity)
                elif "what" in normalized and "if" in normalized:
                    _ui_set("whatif_open", True)
                elif "full" in normalized and "rescue" in normalized:
                    demo._run_all(str(st.session_state.get("current_user") or "demo_user"))
                elif normalized in {"risk","analyze risk","plant risk"}:
                    demo._run_single("risk")
                elif normalized in {"executive","engineering","maintenance","supply","supply chain","quality","sustainability","command center"}:
                    aliases = {"supply":"Supply Chain","supply chain":"Supply Chain"}
                    _ui_set("role", aliases.get(normalized, normalized.title() if normalized != "command center" else "Command Center"))
                elif "evidence" in normalized:
                    _ui_set("evidence_open", True)
                elif normalized in {"governance", "decision governance"}:
                    _ui_set("governance_open", True)
                elif "alternative" in normalized or "compare" in normalized:
                    _ui_set("alternatives_open", True)
                elif "policy" in normalized or "settings" in normalized:
                    _ui_set("policy_open", True)
                elif normalized == "reset":
                    _reset_upgrade_view()
                    demo._reset()
                elif "thread" in normalized:
                    _ui_set("thread_selected", "LINE-02")
                if normalized:
                    st.rerun()


def _render_policy_controls() -> None:
    with st.expander("⚙️ Command Center 2.1 policy & display settings", expanded=bool(_ui_get("policy_open", False))):
        st.caption("These preferences change the Command Center lens and recommendation policy; they do not modify the industrial calculation engines.")
        c1,c2,c3,c4 = st.columns(4)
        rt = c1.slider("Risk alert threshold", 40.0, 90.0, float(_ui_get("risk_threshold",70)), 1.0, key=f"{CC21_KEY}_risk_threshold")
        sw = c2.slider("Service target (%)", 80.0, 99.0, float(_ui_get("service_target",95)), 1.0, key=f"{CC21_KEY}_service_target")
        cw = c3.slider("Cost weight", 0.0, 100.0, float(_ui_get("cost_weight",25)), 1.0, key=f"{CC21_KEY}_cost_weight")
        rw = c4.slider("Risk weight", 0.0, 100.0, float(_ui_get("risk_weight",30)), 1.0, key=f"{CC21_KEY}_risk_weight")
        c5,c6,c7 = st.columns(3)
        srvw = c5.slider("Service weight", 0.0, 100.0, float(_ui_get("service_weight",35)), 1.0, key=f"{CC21_KEY}_service_weight")
        cbw = c6.slider("Carbon weight", 0.0, 100.0, float(_ui_get("carbon_weight",10)), 1.0, key=f"{CC21_KEY}_carbon_weight")
        density = c7.selectbox("Map metric", ["Health","Risk"], index=0 if _ui_get("floor_metric","Health")=="Health" else 1, key=f"{CC21_KEY}_floor_metric")
        _ui_set("risk_threshold", rt); _ui_set("service_target", sw); _ui_set("cost_weight",cw); _ui_set("risk_weight",rw); _ui_set("service_weight",srvw); _ui_set("carbon_weight",cbw); _ui_set("floor_metric",density)


def _render_thread_and_floor() -> None:
    st.markdown("### 🧬 Interactive Digital Thread + Plant Spatial Map")
    left, right = st.columns([1.05, 1.15])
    with left:
        event = _plotly(_build_thread_graph(), key=f"{CC21_KEY}_thread_graph")
        point = _selected_point(event)
        if point:
            entity = _thread_label_to_entity(str(point.get("customdata", "")))
            if entity:
                _open_inspector(entity)
                st.rerun()
        st.caption("Click a node to inspect it. The original Sankey remains below as the continuity/flow view.")
        _plotly(demo._thread_figure(), key=f"{CC21_KEY}_thread_sankey")
    with right:
        metric = st.radio("Spatial map metric", ["Health","Risk"], horizontal=True,
                          index=0 if _ui_get("floor_metric","Health")=="Health" else 1,
                          key=f"{CC21_KEY}_floor_radio")
        _ui_set("floor_metric", metric)
        event = _plotly(_build_floor_map(), key=f"{CC21_KEY}_floor_map")
        point = _selected_point(event)
        entity = _entity_from_floor(point)
        if entity:
            _open_inspector(entity)
            st.rerun()
        st.caption("The floor plan is synthetic and geospatially neutral; click a zone or an entity marker to follow the same Inspector used by the Digital Thread.")


def _render_inspector() -> None:
    if not _ui_get("inspector_open", True):
        if st.button("🔍 Open Inspector", use_container_width=True, key=f"{CC21_KEY}_open_inspector"):
            _ui_set("inspector_open", True)
            st.rerun()
        return
    st.markdown("### 🔎 Persistent Inspector")
    a,b = st.columns([1,5])
    with a:
        if st.button("× Close", use_container_width=True, key=f"{CC21_KEY}_close_inspector"):
            _ui_set("inspector_open", False)
            st.rerun()
    with b:
        st.caption("The Inspector follows selections from the Digital Thread, plant map and commands. Selection persists across reruns.")
    thread = demo._twin_frame()
    ids = thread["ID"].astype(str).tolist()
    current = str(_ui_get("inspector_id","C-204"))
    if current not in ids:
        current = ids[0]
    selected = st.selectbox("Inspect entity", ids, index=ids.index(current), key=f"{CC21_KEY}_inspector_select")
    _ui_set("inspector_id", selected)
    detail = demo._cc_entity_detail(selected)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Type", str(detail["type"]))
    c2.metric("State", str(detail["state"]))
    c3.metric("Risk", f"{float(detail['risk']):.0f}%" if detail["risk"] is not None else "—")
    c4.metric("Focus", str(detail["impact"]))
    risk = demo._risk_analysis(_inputs())
    row = risk.loc[risk["Asset"].astype(str).eq(selected)]
    if not row.empty:
        st.dataframe(row, use_container_width=True, hide_index=True)
    connections = {
        "C-204": "LINE-02 · MAT-BRG-08 · MW-BACKLOG · ENERGY-01 · WO-4821",
        "LINE-02": "FAC-RYD-01 · C-204 · Q-07 · WO-4821 · LINE-03",
        "SUP-18": "MAT-BRG-08 · WO-4821 · LINE-02",
        "MAT-BRG-08": "C-204 · SUP-18 · MW-BACKLOG",
        "Q-07": "LINE-02 · C-204 · WO-4821",
    }.get(selected, "Facility · Process · Decision · Outcome")
    st.info(f"**Connected to:** {connections}")
    with st.container(border=True):
        st.markdown("**Inspector drawer actions**")
        a1,a2,a3 = st.columns(3)
        with a1:
            if st.button("🧪 Simulate this entity", use_container_width=True, key=f"{CC21_KEY}_inspect_whatif"):
                _ui_set("whatif_open", True)
                st.rerun()
        with a2:
            if st.button("📋 Explain its evidence", use_container_width=True, key=f"{CC21_KEY}_inspect_evidence"):
                _ui_set("evidence_open", True)
                st.rerun()
        with a3:
            if st.button("🗂️ Save current scenario", use_container_width=True, key=f"{CC21_KEY}_inspect_save"):
                try:
                    demo.save_twin_scenario(
                        str(st.session_state.get("current_user") or "demo_user"),
                        f"Inspector · {selected} · {time.strftime('%Y-%m-%d %H:%M')}",
                        _inputs(), parent_name="Command Center 2.1",
                        notes=f"Saved from Inspector selection {selected}.",
                    )
                    st.success("Scenario saved to the enterprise workspace.")
                except Exception as exc:
                    st.warning(f"Scenario save unavailable: {type(exc).__name__}")


def _render_what_if() -> None:
    with st.expander("🔮 What-If Studio · operational + financial re-evaluation", expanded=bool(_ui_get("whatif_open", False))):
        st.caption("Every What-If run creates an isolated scenario, reruns the deterministic simulation and recalculates the full modelled financial rescue case. Live plant state is unchanged.")
        v = _inputs()
        c1,c2,c3,c4 = st.columns(4)
        oee = c1.slider("Line 2 OEE", 50.0,99.0,float(v["production_oee"]),0.5,key=f"{CC21_KEY}_wi_oee")
        maint = c2.slider("C-204 risk",5.0,99.0,float(v["maintenance_risk"]),1.0,key=f"{CC21_KEY}_wi_maint")
        inv = c3.slider("Bearing cover",0.5,7.0,float(v["inventory_cover"]),0.1,key=f"{CC21_KEY}_wi_inv")
        supp = c4.slider("Supplier delay",0.0,120.0,float(v.get("supplier_delay_h",18)),1.0,key=f"{CC21_KEY}_wi_supp")
        if st.button("▶ Recalculate future state", type="primary", use_container_width=True, key=f"{CC21_KEY}_wi_run"):
            scenario = dict(v)
            scenario.update({
                "production_oee": float(oee), "maintenance_risk": float(maint),
                "inventory_cover": float(inv), "supplier_delay_h": float(supp),
            })
            sim = demo._simulation(scenario, seed=20261004)
            econ = _dynamic_rescue(scenario)
            alt = _policy_alternatives(scenario)
            choice = alt.iloc[0].to_dict()
            summary = sim["summary"].copy()
            _ui_set("whatif_result_21", {
                "inputs": scenario, "simulation": sim, "economics": econ,
                "alternatives": alt, "choice": choice,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        result = _ui_get("whatif_result_21")
        if result:
            econ = result["economics"]
            sim = result["simulation"]["summary"]
            base = sim.loc[sim["Scenario"].eq("Baseline")].iloc[0]
            inter = sim.loc[sim["Scenario"].eq("Intervention")].iloc[0]
            st.markdown("#### Future operational state")
            m = st.columns(4)
            m[0].metric("OTIF", f"{inter['OTIF %']:.1f}%", f"{inter['OTIF %']-base['OTIF %']:+.1f} pp")
            m[1].metric("Throughput", demo._pretty_number(inter["Throughput"]), f"{inter['Throughput']-base['Throughput']:+.0f}")
            m[2].metric("Downtime", f"{inter['Downtime h']:.1f} h", f"{inter['Downtime h']-base['Downtime h']:+.1f} h")
            m[3].metric("Energy", demo._pretty_number(inter["Energy kWh"]), "scenario")
            st.dataframe(sim.round(2), use_container_width=True, hide_index=True)
            st.markdown("#### Financial re-evaluation")
            e = pd.DataFrame([
                ["Financial exposure", demo._format_sar(econ["baseline"]["Financial exposure SAR"]), demo._format_sar(econ["intervention"]["Financial exposure SAR"])],
                ["Avoided exposure", "—", demo._format_sar(econ["avoided_exposure"])],
                ["Intervention cost", "—", demo._format_sar(econ["intervention_cost"])],
                ["Net modelled value", "—", demo._format_sar(econ["net_value"])],
                ["Modelled ROI", "—", f"{econ['roi']:.0f}%"],
                ["Customer delivery", econ["baseline"]["Customer delivery"], econ["intervention"]["Customer delivery"]],
            ], columns=["Metric","Baseline","What-If Intervention"])
            st.dataframe(e, use_container_width=True, hide_index=True)
            st.markdown("#### Decision alternative under current policy")
            st.dataframe(result["alternatives"].round(2), use_container_width=True, hide_index=True)
            st.success(f"Policy recommendation: **{choice['Alternative']}** · {choice['Action']}")
            if st.button("↺ Clear What-If result", use_container_width=True, key=f"{CC21_KEY}_wi_clear"):
                _ui_set("whatif_result_21", None)
                _ui_set("whatif_open", False)
                st.rerun()


def _render_evidence_and_governance() -> None:
    rescue = _dynamic_rescue(_inputs())
    evidence = pd.DataFrame([
        ["Scenario input", "Plant controls", "Synthetic / user-entered", "Current session"],
        ["Risk evidence", "7 cross-domain signals", "Synthetic model", "Command Center risk state"],
        ["Future model", "72h Monte Carlo", "Deterministic seed 20261004", "1,500 replications"],
        ["Decision policy", "Cost / risk / service / carbon weights", "Configurable policy", "Workspace settings"],
        ["Financial model", "Exposure → intervention → avoided exposure", "Calibrated parameterized demo model", "Sensitivity enabled"],
    ], columns=["Layer","Evidence","Source / method","Trace"])
    st.dataframe(evidence, use_container_width=True, hide_index=True)
    st.markdown("#### Modelled economic trace")
    c1,c2,c3 = st.columns(3)
    c1.metric("Baseline exposure", demo._format_sar(rescue["baseline"]["Financial exposure SAR"]))
    c2.metric("Intervention exposure", demo._format_sar(rescue["intervention"]["Financial exposure SAR"]))
    c3.metric("Avoided exposure", demo._format_sar(rescue["avoided_exposure"]))
    st.caption("These economics are synthetic/modelled. They are deliberately not represented as verified customer savings.")
    ver = demo._state("verification")
    if isinstance(ver, pd.DataFrame):
        digest = demo.hashlib.sha256(ver.to_csv(index=False).encode("utf-8")).hexdigest()
        st.caption(f"Verification evidence hash: {digest[:16]}…")
    else:
        st.caption("Generate the decision flow to attach a verification hash. Governance controls are still available for staging.")
    st.markdown("#### 🛡️ Decision governance")
    demo._render_decision_governance()

def render_investor_control_center_21(tier: str, username: str) -> None:
    """Render the upgraded Command Center while preserving all original stages."""
    _ensure_state()
    demo._ensure_defaults()
    demo._init_ui_state()

    _render_cockpit()
    _render_palette()
    _render_role_workspace()
    _render_focus_panel()
    _render_policy_controls()

    with st.expander("⚖️ Intervention alternatives & recommendation policy", expanded=bool(_ui_get("alternatives_open", False))):
        st.caption("Tune the decision policy above, compare all available interventions, then send the preferred alternative into the preserved engineering decision flow.")
        alt = _policy_alternatives(_inputs())
        st.dataframe(alt.round(2), use_container_width=True, hide_index=True)
        _plotly(px.scatter(alt, x="Cost SAR", y="Risk", size="Service %", hover_name="Alternative", text="Alternative", title="Configurable intervention frontier"), key=f"{CC21_KEY}_alternatives")
        if not alt.empty and st.button(f"🎯 Use {alt.iloc[0]['Alternative']} as working policy choice", type="primary", use_container_width=True, key=f"{CC21_KEY}_use_alt"):
            _ui_set("last_action", f"Policy choice · {alt.iloc[0]['Alternative']}")
            st.success(f"Working recommendation set to {alt.iloc[0]['Alternative']}. Existing optimization and decision stages remain authoritative for execution.")

    with st.expander("🧠 Why this recommendation?", expanded=False):
        demo._render_why_recommendation()
    demo._render_scenario_library(username)

    st.markdown("### 🏭 Industrial Situation Map")
    _render_thread_and_floor()
    _render_inspector()
    _render_what_if()

    with st.expander("🔗 Evidence & Decision Governance", expanded=bool(_ui_get("evidence_open", False) or _ui_get("governance_open", False))):
        _render_evidence_and_governance()
        with st.expander("Original evidence trace", expanded=False):
            demo._render_evidence_chain()
    with st.expander("🧑‍💼 Executive View", expanded=_ui_get("role","Command Center")=="Executive"):
        demo._render_executive_summary()
    with st.expander("🔄 Closed-loop lifecycle", expanded=False):
        demo._render_closed_loop()

    st.markdown("---")
    st.markdown("### Existing Industrial Decision Flow · preserved")
    demo._render_header()
    demo._render_plant_controls(username)
    demo._render_stage_rail()

    with st.expander("🎬 Presentation controls", expanded=not demo._state("started")):
        c1,c2 = st.columns([2,1])
        with c1:
            st.caption("The original step-by-step flow and one-click rescue flow are preserved unchanged below the 2.1 cockpit.")
            if st.button("🚀 RUN FULL RESCUE FLOW", type="primary", use_container_width=True, key=f"{CC21_KEY}_full"):
                demo._run_all(username)
                st.rerun()
        with c2:
            if st.button("↺ Reset", use_container_width=True, key=f"{CC21_KEY}_reset"):
                demo._reset()
                _ui_set("inspector_open", True)
                _ui_set("palette_open", False)
                st.rerun()

    if not demo._state("started"):
        demo._render_landing()
        return

    demo._render_risk()
    demo._render_thread()
    demo._render_maintenance()
    demo._render_simulation()
    demo._render_optimization()
    demo._render_decision()
    demo._render_impact()
    demo._render_verification()

    if not demo._is_done("verification"):
        current = next((x for x, _, _ in demo.STAGES if not demo._is_done(x)), "risk")
        st.divider()
        st.markdown(f"### Next action · {dict((x, l) for x, _, l in demo.STAGES).get(current, current)}")
        labels = {
            "risk": "🚨 Analyze plant risk", "thread": "🧬 Build Digital Thread",
            "maintenance": "🛠️ Run predictive maintenance", "simulation": "🧪 Run factory simulation",
            "optimization": "⚖️ Optimize intervention", "decision": "🎯 Create decision",
            "impact": "💰 Quantify ROI", "verification": "✅ Verify outcome",
        }
        if st.button(labels[current], type="primary", use_container_width=True, key=f"{CC21_KEY}_next"):
            demo._run_single(current)
            st.rerun()
