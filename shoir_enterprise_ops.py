"""Integrated enterprise operations/governance layers for Shoir-IE.

These helpers extend existing modules instead of creating parallel workflows.
They are intentionally additive and data-grounded: missing operational data is
shown as unavailable rather than replaced with invented performance.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _df(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    if isinstance(value, list):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return pd.DataFrame()


def _numeric(series: Any) -> pd.Series:
    return pd.to_numeric(pd.Series(series), errors="coerce")


def _render_universal_viz(module: str, preferred_key: str | None = None) -> None:
    """Attach the shared visualization studio without inventing data."""
    try:
        from shoir_live_visuals import render_live_visualization_studio
        render_live_visualization_studio(module, expanded=False, preferred_key=preferred_key)
    except Exception as exc:
        st.info(f"Universal visualization is temporarily unavailable for this module: {type(exc).__name__}.")
    

def _status_health(status: str) -> float | None:
    s = str(status or "").strip().lower()
    if not s:
        return None
    if any(x in s for x in ("critical", "failed", "down", "error", "offline")):
        return 25.0
    if any(x in s for x in ("warning", "degraded", "standby", "maintenance", "review")):
        return 65.0
    if any(x in s for x in ("active", "running", "connected", "healthy", "optimal", "normal", "ready", "verified")):
        return 95.0
    if any(x in s for x in ("pending", "queued")):
        return 75.0
    return None


# ---------------------------------------------------------------------------
# Digital Twin + scenario replay / what-if
# ---------------------------------------------------------------------------

def build_twin_state_frame(
    workstations: Any,
    agv_fleet: Any,
    des_queues: Any,
    sensors: Any,
    buffers: Any,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    ws = _df(workstations)
    for _, r in ws.iterrows():
        health = _status_health(r.get("status"))
        rows.append({
            "Entity": str(r.get("id") or r.get("name") or "Workstation"),
            "Domain": "Production",
            "Status": str(r.get("status") or "Unknown"),
            "Health": health,
            "Load": np.nan,
            "Source": "Workstation state",
        })

    agv = _df(agv_fleet)
    for _, r in agv.iterrows():
        battery = float(_numeric([r.get("battery")]).fillna(np.nan).iloc[0]) if pd.notna(_numeric([r.get("battery")]).iloc[0]) else np.nan
        rows.append({
            "Entity": str(r.get("agv_id") or r.get("id") or "AGV"),
            "Domain": "Transport",
            "Status": str(r.get("status") or "Unknown"),
            "Health": max(0.0, min(100.0, battery)) if np.isfinite(battery) else _status_health(r.get("status")),
            "Load": np.nan,
            "Source": "AGV telemetry",
        })

    q = _df(des_queues)
    for _, r in q.iterrows():
        arr = float(_numeric([r.get("arrival_rate")]).fillna(0).iloc[0])
        srv = float(_numeric([r.get("service_rate")]).fillna(0).iloc[0])
        util = 100.0 * arr / srv if srv > 0 else np.nan
        rows.append({
            "Entity": str(r.get("queue_id") or r.get("station") or "Queue"),
            "Domain": "Process Flow",
            "Status": "Stable" if np.isfinite(util) and util <= 85 else ("Risk" if np.isfinite(util) else "Unknown"),
            "Health": max(0.0, min(100.0, 100.0 - max(0.0, util - 70.0) * 2.0)) if np.isfinite(util) else np.nan,
            "Load": util,
            "Source": "DES queue state",
        })

    s = _df(sensors)
    for _, r in s.iterrows():
        reading = float(_numeric([r.get("reading")]).fillna(np.nan).iloc[0]) if pd.notna(_numeric([r.get("reading")]).iloc[0]) else np.nan
        threshold = float(_numeric([r.get("threshold")]).fillna(np.nan).iloc[0]) if pd.notna(_numeric([r.get("threshold")]).iloc[0]) else np.nan
        health = None
        if np.isfinite(reading) and np.isfinite(threshold) and threshold > 0:
            health = max(0.0, min(100.0, 100.0 - max(0.0, reading / threshold - 0.7) * 333.0))
        rows.append({
            "Entity": str(r.get("sensor_id") or r.get("name") or "Sensor"),
            "Domain": "Telemetry",
            "Status": str(r.get("status") or "Unknown"),
            "Health": health,
            "Load": (reading / threshold * 100.0) if np.isfinite(reading) and np.isfinite(threshold) and threshold else np.nan,
            "Source": "Sensor state",
        })

    b = _df(buffers)
    for _, r in b.iterrows():
        current = float(_numeric([r.get("current_wip")]).fillna(np.nan).iloc[0]) if pd.notna(_numeric([r.get("current_wip")]).iloc[0]) else np.nan
        cap = float(_numeric([r.get("max_capacity")]).fillna(np.nan).iloc[0]) if pd.notna(_numeric([r.get("max_capacity")]).iloc[0]) else np.nan
        util = 100.0 * current / cap if np.isfinite(current) and np.isfinite(cap) and cap > 0 else np.nan
        rows.append({
            "Entity": str(r.get("buffer_id") or "Buffer"),
            "Domain": "WIP",
            "Status": str(r.get("state") or "Unknown"),
            "Health": max(0.0, min(100.0, 100.0 - max(0.0, util - 75.0) * 4.0)) if np.isfinite(util) else np.nan,
            "Load": util,
            "Source": "Kanban buffer state",
        })

    return pd.DataFrame(rows)


def run_twin_what_if(
    queue_df: pd.DataFrame,
    buffer_df: pd.DataFrame,
    agv_df: pd.DataFrame,
    *,
    service_multiplier: float = 1.0,
    arrival_multiplier: float = 1.0,
    downtime_rate: float = 0.0,
    battery_drain: float = 2.0,
    ticks: int = 24,
) -> pd.DataFrame:
    """Replay a deterministic what-if scenario from current twin state."""
    q = _df(queue_df)
    b = _df(buffer_df)
    agv = _df(agv_df)
    if q.empty and b.empty and agv.empty:
        return pd.DataFrame()

    service_multiplier = max(0.1, float(service_multiplier))
    arrival_multiplier = max(0.0, float(arrival_multiplier))
    downtime_rate = max(0.0, min(1.0, float(downtime_rate)))
    battery_drain = max(0.0, float(battery_drain))
    ticks = max(1, min(240, int(ticks)))

    rows: list[dict[str, Any]] = []
    total_wip0 = float(_numeric(b.get("current_wip", [])).fillna(0).sum()) if "current_wip" in b.columns else 0.0
    active_agv0 = int((agv.get("status", pd.Series(dtype=object)).astype(str).str.lower().isin(["moving", "active", "navigating", "picking"])).sum()) if not agv.empty else 0
    battery_values = _numeric(agv.get("battery", [])).dropna() if "battery" in agv.columns and not agv.empty else pd.Series(dtype=float)
    battery0 = float(battery_values.mean()) if not battery_values.empty else np.nan

    wip = total_wip0
    battery = battery0
    base_arrival = float(_numeric(q.get("arrival_rate", [])).fillna(0).sum()) if "arrival_rate" in q.columns else 0.0
    base_service = float(_numeric(q.get("service_rate", [])).fillna(0).sum()) if "service_rate" in q.columns else 0.0

    rng = np.random.default_rng(1708)
    for tick in range(1, ticks + 1):
        disruptions = 1.0 if rng.random() < downtime_rate else 0.0
        effective_service = base_service * service_multiplier * (1.0 - disruptions)
        arrivals = base_arrival * arrival_multiplier
        flow_delta = arrivals - effective_service
        wip = max(0.0, wip + flow_delta)
        if np.isfinite(battery):
            battery = max(0.0, battery - battery_drain * max(0.0, 1.0 - disruptions))
        util = 100.0 * arrivals / effective_service if effective_service > 0 else np.nan
        rows.append({
            "Tick": tick,
            "Scenario": "What-if",
            "Arrivals": arrivals,
            "Effective Service": effective_service,
            "Utilization %": util,
            "WIP": wip,
            "AGV Avg Battery %": battery,
            "Active AGVs": active_agv0,
            "Downtime Shock": bool(disruptions),
        })
    return pd.DataFrame(rows)


def render_digital_twin_extension(username: str = "unknown") -> None:
    st.markdown("### 🔄 Twin Synchronization & Scenario Replay")
    st.caption("Adds a governed replay layer to the existing Digital Twin. Current asset, queue, buffer and AGV state is the starting point; what-if output is explicitly simulated.")
    workstations = st.session_state.get("dt_workstations", [])
    agv = st.session_state.get("agv_fleet", [])
    queues = st.session_state.get("des_queues", [])
    sensors = st.session_state.get("iot_sensors", [])
    buffers = st.session_state.get("kanban_buffers", [])

    snapshot = build_twin_state_frame(workstations, agv, queues, sensors, buffers)
    st.session_state["digital_twin_state_snapshot"] = snapshot
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entities synchronized", f"{len(snapshot):,}")
    c2.metric("Assets / machines", f"{len(_df(workstations)):,}")
    c3.metric("Live sensors", f"{len(_df(sensors)):,}")
    c4.metric("Queues / buffers", f"{len(_df(queues)) + len(_df(buffers)):,}")

    with st.expander("🎬 Replay / What-if", expanded=False):
        w1, w2, w3, w4 = st.columns(4)
        service = w1.slider("Service-rate multiplier", 0.50, 1.50, 1.00, 0.05, key="twin_ext_service")
        arrival = w2.slider("Demand / arrival multiplier", 0.50, 1.75, 1.00, 0.05, key="twin_ext_arrival")
        downtime = w3.slider("Random downtime shock rate", 0.00, 0.50, 0.05, 0.01, key="twin_ext_downtime")
        drain = w4.number_input("AGV battery drain / tick", 0.0, 20.0, 2.0, 0.5, key="twin_ext_battery")
        ticks = st.slider("Replay ticks", 4, 96, 24, 4, key="twin_ext_ticks")
        if st.button("▶ Run synchronized what-if replay", type="primary", use_container_width=True, key="twin_ext_run"):
            result = run_twin_what_if(_df(queues), _df(buffers), _df(agv), service_multiplier=service, arrival_multiplier=arrival, downtime_rate=downtime, battery_drain=drain, ticks=ticks)
            st.session_state["digital_twin_replay_df"] = result
            st.success("What-if replay completed from the current twin state.")
        result = st.session_state.get("digital_twin_replay_df", pd.DataFrame())
        if isinstance(result, pd.DataFrame) and not result.empty:
            st.dataframe(result, use_container_width=True, hide_index=True)
            fig = px.line(result, x="Tick", y=["WIP", "Utilization %"], title="Digital Twin Scenario Replay")
            st.plotly_chart(fig, use_container_width=True)
            st.download_button("📥 Download replay evidence", result.to_csv(index=False).encode(), "shoir_ie_twin_replay.csv", "text/csv", use_container_width=True)


# ---------------------------------------------------------------------------
# Control Tower
# ---------------------------------------------------------------------------

def build_control_tower_health(state: Mapping[str, Any]) -> pd.DataFrame:
    frames: list[dict[str, Any]] = []

    def add(area: str, value: float | None, status: str, signal: str):
        frames.append({"Area": area, "Health %": value, "Status": status, "Signal": signal})

    ws = _df(state.get("workstations"))
    if not ws.empty and "status" in ws.columns:
        counts = ws["status"].astype(str).str.lower()
        health = float(counts.isin(["running", "active", "operating", "healthy", "optimal"]).mean() * 100)
        add("Production", health, "Observed", f"{len(ws):,} workstation(s)")

    supply = _df(state.get("supply"))
    if not supply.empty:
        util_col = next((c for c in supply.columns if "util" in str(c).lower()), None)
        if util_col:
            util = float(_numeric(supply[util_col]).mean())
            add("Supply", max(0.0, min(100.0, 100.0 - max(0.0, util - 80.0) * 3.0)), "Observed", f"Mean utilization {util:.1f}%")
        else:
            add("Supply", None, "Review", f"{len(supply):,} facility record(s); no measurable health/utilization signal mapped.")

    inv = _df(state.get("inventory"))
    if not inv.empty:
        stock = next((c for c in inv.columns if any(x in str(c).lower() for x in ("stock", "inventory"))), None)
        threshold = next((c for c in inv.columns if any(x in str(c).lower() for x in ("threshold", "safety", "reorder"))), None)
        if stock and threshold:
            s = _numeric(inv[stock]); t = _numeric(inv[threshold])
            ratio = float((s >= t).mean() * 100) if len(inv) else None
            add("Inventory", ratio, "Observed", "Stock vs safety threshold")

    quality = _df(state.get("quality"))
    if not quality.empty:
        numeric = quality.select_dtypes(include=np.number)
        if not numeric.empty:
            missing = float(numeric.isna().mean().mean() * 100)
            add("Quality", max(0.0, 100.0 - missing * 2.0), "Observed", f"{len(numeric.columns)} numeric quality measure(s)")

    maint = _df(state.get("maintenance"))
    if not maint.empty:
        health_col = next((c for c in maint.columns if str(c).lower() in {"health", "health score", "risk score"}), None)
        if health_col:
            vals = _numeric(maint[health_col]).dropna()
            if "risk" in str(health_col).lower():
                score = float(100.0 - vals.mean()) if len(vals) else None
            else:
                score = float(vals.mean()) if len(vals) else None
            add("Maintenance", score, "Observed", str(health_col))

    transport = _df(state.get("transport"))
    if not transport.empty:
        battery = next((c for c in transport.columns if "battery" in str(c).lower()), None)
        if battery:
            add("Transport", float(_numeric(transport[battery]).mean()), "Observed", "Fleet battery signal")
        else:
            add("Transport", None, "Review", f"{len(transport):,} transport record(s); no measurable health/battery signal mapped.")

    workforce = _df(state.get("workforce"))
    if not workforce.empty:
        productivity = next((c for c in workforce.columns if any(x in str(c).lower() for x in ("productive", "utilization", "capacity", "efficiency"))), None)
        score = float(_numeric(workforce[productivity]).mean()) if productivity else None
        add("Workforce", score, "Observed" if score is not None else "Review", "Workforce utilization/capacity signal")

    energy = _df(state.get("energy"))
    if not energy.empty:
        numeric = energy.select_dtypes(include=np.number)
        if not numeric.empty:
            vals = numeric.mean(axis=1).dropna()
            score = None if vals.empty else float(max(0.0, min(100.0, 100.0 - (vals.mean() / max(vals.max(), 1e-9)) * 50.0)))
            add("Energy", score, "Observed", "Relative energy intensity signal")

    carbon = _df(state.get("carbon"))
    if not carbon.empty:
        emissions = next((c for c in carbon.columns if any(x in str(c).lower() for x in ("co2", "carbon", "emission"))), None)
        if emissions:
            vals = _numeric(carbon[emissions]).dropna()
            score = None if vals.empty else float(max(0.0, min(100.0, 100.0 - (vals.mean() / max(vals.max(), 1e-9)) * 50.0)))
            add("Carbon", score, "Observed", "Relative emissions signal")

    expected_areas = [
        "Production", "Supply", "Inventory", "Quality", "Maintenance",
        "Transport", "Workforce", "Energy", "Carbon",
    ]
    present = {row["Area"] for row in frames}
    for area in expected_areas:
        if area not in present:
            add(area, None, "No data", "No source dataset or measurable KPI signal is currently mapped.")

    return pd.DataFrame(frames)


def render_control_tower_extension() -> None:
    state = {
        "workstations": st.session_state.get("dt_workstations", []),
        "supply": st.session_state.get("supply_nodes", []),
        "inventory": st.session_state.get("inventory_playback", st.session_state.get("meio_data", [])),
        "quality": st.session_state.get("quality_df", []),
        "maintenance": st.session_state.get("maintenance_assets", []),
        "transport": st.session_state.get("agv_fleet", []),
        "workforce": st.session_state.get("work_elements", []),
        "energy": st.session_state.get("energy_units", []),
        "carbon": st.session_state.get("carbon_sources", []),
    }
    health = build_control_tower_health(state)
    st.session_state["control_tower_unified_health_df"] = health
    st.markdown("### 🗼 Unified Industrial Health Map")
    st.caption("Health is calculated only where an observable signal exists. Areas without source data stay blank rather than showing fabricated status.")
    if health.empty:
        st.info("No cross-domain operational datasets are currently available.")
        return
    st.dataframe(health, use_container_width=True, hide_index=True)
    plot_df = health.dropna(subset=["Health %"]).copy()
    if not plot_df.empty:
        fig = px.bar(plot_df, x="Area", y="Health %", color="Status", hover_data=["Signal"], range_y=[0, 100], title="Production · Supply · Inventory · Quality · Maintenance · Transport · Workforce · Energy · Carbon")
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Connectivity + health monitoring
# ---------------------------------------------------------------------------

def normalize_connector_health(df: pd.DataFrame) -> pd.DataFrame:
    d = _df(df)
    if d.empty:
        return pd.DataFrame(columns=["Name", "System Type", "Protocol", "Status", "Health %", "Latency ms", "Freshness min", "Errors"])
    d = d.rename(columns={
        "connector_id": "Connector ID",
        "system_name": "Name",
        "protocol": "Protocol",
        "status": "Status",
        "last_sync": "Last Sync",
    }).copy()
    if "Name" not in d.columns:
        d["Name"] = [f"Connector {i+1}" for i in range(len(d))]
    if "System Type" not in d.columns:
        d["System Type"] = "Unclassified"
    if "Protocol" not in d.columns:
        d["Protocol"] = "Configured"
    if "Status" not in d.columns:
        d["Status"] = "Unknown"
    d["Latency ms"] = _numeric(d.get("Latency ms", pd.Series([np.nan] * len(d), index=d.index)))
    d["Freshness min"] = _numeric(d.get("Freshness min", pd.Series([np.nan] * len(d), index=d.index)))
    d["Errors"] = _numeric(d.get("Errors", pd.Series([0] * len(d), index=d.index))).fillna(0)
    base = d["Status"].map(lambda x: _status_health(x) if x else np.nan)
    latency_penalty = d["Latency ms"].fillna(0).clip(lower=0) * 0.2
    error_penalty = d["Errors"].clip(lower=0) * 5.0
    freshness_penalty = d["Freshness min"].fillna(0).clip(lower=0) * 0.5
    d["Health %"] = (base - latency_penalty - error_penalty - freshness_penalty).clip(lower=0, upper=100)
    return d


def render_connectivity_extension() -> None:
    from shoir_enterprise_layer import (
        connector_health_frame, connector_run_frame, test_connector_profile,
        schedule_connector_sync, validate_connector_profile,
    )

    username = st.session_state.get("current_user", "unknown")
    workspace = str(
        st.session_state.get("shoir_workspace_name")
        or st.session_state.get("workspace")
        or st.session_state.get("active_workspace_name")
        or "default"
    )
    raw = st.session_state.get("conn_df", st.session_state.get("erp_connectors", []))
    health = normalize_connector_health(_df(raw))
    persisted = connector_health_frame(username, workspace)
    if not persisted.empty:
        persisted = persisted.rename(columns={
            "name": "Name", "system_type": "System Type", "protocol": "Protocol",
            "status": "Status", "latency_ms": "Latency ms", "detail": "Errors",
            "checked_at": "Last Sync",
        })
        health = pd.concat([health, persisted], ignore_index=True)
        if "Name" in health.columns and "Protocol" in health.columns:
            health = health.drop_duplicates(subset=["Name", "Protocol"], keep="last")
    st.session_state["connectivity_health_df"] = health

    st.markdown("### 🔌 Connector Health & Deployment Readiness")
    st.caption("One governed adapter surface for SAP · Oracle · WMS · MES · ERP · REST · SQL · MQTT · OPC-UA. Live tests are opt-in; secret values are never stored in connector records.")

    with st.expander("🧭 Live Connection Wizard", expanded=False):
        left, right = st.columns(2)
        with left:
            system_type = st.selectbox("System", ["SAP","ORACLE","WMS","MES","ERP","REST","SQL","MQTT","OPC-UA"], key="conn_wizard_system")
            defaults = {"SAP":"ODATA","ORACLE":"SQL","WMS":"REST","MES":"REST","ERP":"REST","REST":"REST","SQL":"SQL","MQTT":"MQTT","OPC-UA":"OPC-UA"}
            protocols = ["REST","ODATA","HTTPS","SQL","JDBC","MQTT","OPC-UA"]
            default_protocol = defaults.get(system_type, "REST")
            protocol = st.selectbox("Protocol / adapter", protocols, index=protocols.index(default_protocol), key="conn_wizard_protocol")
            name = st.text_input("Connection name", value=f"{system_type} connection", key="conn_wizard_name")
        with right:
            endpoint = st.text_input("Endpoint / DSN", placeholder="https://… | postgresql://… | sqlite:///… | mqtt://… | opc.tcp://…", key="conn_wizard_endpoint")
            secret_ref = st.text_input("Secret reference (optional)", placeholder="env:SAP_API_TOKEN", type="password", key="conn_wizard_secret_ref", help="Reference only. The secret value is never persisted.")
            timeout = st.number_input("Timeout (seconds)", 1.0, 60.0, 8.0, 1.0, key="conn_wizard_timeout")

        profile = validate_connector_profile(system_type, protocol, endpoint)
        if profile["valid"]:
            st.success(f"Adapter ready · {profile.get("adapter", protocol)}")
        else:
            st.warning("Configuration needs attention: " + " ".join(profile["errors"]))

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🧪 Test connection", type="primary", use_container_width=True, key="conn_wizard_test"):
                if not endpoint.strip():
                    st.warning("Enter an endpoint before testing.")
                else:
                    result = test_connector_profile(username, name, system_type, protocol, endpoint, secret_ref, workspace, float(timeout))
                    st.session_state["connector_last_test"] = result
                    st.rerun()
        with c2:
            interval = st.number_input("Sync interval (minutes)", 1, 10080, 60, 5, key="conn_wizard_interval")
            enabled = st.checkbox("Enable schedule", value=True, key="conn_wizard_enabled")
            if st.button("⏱️ Save synchronization schedule", use_container_width=True, key="conn_wizard_schedule"):
                last = st.session_state.get("connector_last_test") or {}
                connector_id = str(last.get("connector_id") or "")
                if not connector_id:
                    st.warning("Test the connection first so a connector ID exists.")
                else:
                    sid = schedule_connector_sync(username, connector_id, int(interval), workspace, bool(enabled))
                    st.success(f"Synchronization schedule saved · {sid}")

    last = st.session_state.get("connector_last_test")
    if isinstance(last, dict):
        st.markdown(f"**Last connector test:** {last.get("status","Unknown")} · {float(last.get("latency_ms",0.0)):.1f} ms · {last.get("detail","")}")

    if health.empty:
        st.info("Register or test a connector above to begin health monitoring.")
    else:
        st.dataframe(health, use_container_width=True, hide_index=True)
        if "Health %" in health.columns:
            fig = px.bar(health, x="Name", y="Health %", color="Protocol", range_y=[0,100], title="Enterprise Connector Health")
            st.plotly_chart(fig, use_container_width=True)
        runs = connector_run_frame(username, workspace, 100)
        if not runs.empty:
            st.markdown("#### Connector Test / Sync History")
            st.dataframe(runs, use_container_width=True, hide_index=True)

    _render_universal_viz("Industrial Connectivity Hub", "connectivity_health_df")

# ---------------------------------------------------------------------------
# Enterprise Security
# ---------------------------------------------------------------------------

def security_posture() -> pd.DataFrame:
    checks: list[dict[str, Any]] = []

    def add(control: str, status: str, evidence: str):
        checks.append({"Control": control, "Status": status, "Evidence": evidence})

    add("RBAC", "Configured" if st.session_state.get("current_role") else "Review", "Active role is scoped in workspace session.")
    add("Workspace isolation", "Configured" if st.session_state.get("current_user") else "Review", "User-scoped workspace state is used by the persistence layer.")
    add("Audit trail", "Configured" if os.path.exists("enterprise_full_workspace.db") else "Review", "Application audit tables are available when the local/managed store is active.")

    secret_keys = []
    try:
        for section in ("database", "admin", "anthropic", "authentication", "oidc", "sso", "mfa"):
            try:
                block = st.secrets[section]
                if isinstance(block, Mapping):
                    secret_keys.extend([f"{section}.{k}" for k in block.keys()])
            except Exception:
                pass
    except Exception:
        pass

    oidc = any(k.startswith("oidc.") or k.startswith("sso.") or k.startswith("authentication.") for k in secret_keys)
    mfa = any(k.startswith("mfa.") for k in secret_keys)
    add("SSO / OIDC", "Configured" if oidc else "Not configured", "Configuration presence only; secret values are never displayed.")
    add("MFA", "Configured" if mfa else "Not configured", "Configuration presence only; secret values are never displayed.")

    protected = [k for k in st.session_state.keys() if re.search(r"password|token|secret|otp|payment", str(k), re.I)]
    add("Secure file/session handling", "Configured", f"{len(protected)} sensitive session key(s) excluded from workspace persistence.")
    add("Security scanning", "CI hook" if os.path.exists(".github/workflows") else "Review", "Repository CI configuration is the source of truth for automated scanning.")
    return pd.DataFrame(checks)


def render_security_extension() -> None:
    from shoir_enterprise_layer import security_maturity_status, security_access_check, inspect_upload

    username = st.session_state.get("current_user", "unknown")
    workspace = str(st.session_state.get("shoir_workspace_name") or st.session_state.get("workspace") or st.session_state.get("active_workspace_name") or "default")
    posture = security_posture()
    st.session_state["enterprise_security_posture_df"] = posture

    with st.expander("🔐 Secure File Handling", expanded=False):
        uploaded = st.file_uploader("Security-scan an engineering file", type=["csv","xlsx","txt","md","json","pdf","docx"], key="enterprise_security_file_scan_upload")
        if uploaded is not None:
            raw = uploaded.getvalue()
            try:
                scan_result = inspect_upload(uploaded.name, raw, uploaded.type or "")
                scan = pd.DataFrame([
                    {"Check":"SHA-256","Status":"PASS","Evidence":scan_result["sha256"]},
                    {"Check":"File size","Status":"PASS" if scan_result["bytes"] <= 50_000_000 else "FAIL","Evidence":f"{scan_result["bytes"]:,} bytes"},
                    {"Check":"Upload safety","Status":"PASS" if scan_result["safe"] else "FAIL","Evidence":"; ".join(scan_result["reasons"]) or "Extension/container/signature checks passed"},
                ])
                st.session_state["security_file_scan_df"] = scan
                st.dataframe(scan, use_container_width=True, hide_index=True)
                if not scan_result["safe"]:
                    st.error("File rejected by the secure upload gate.")
            except Exception as exc:
                st.error("Secure upload scan failed safely: " + str(exc))

    st.markdown("### 🔐 Enterprise Security Posture")
    st.dataframe(posture, use_container_width=True, hide_index=True)
    maturity = security_maturity_status(username, workspace)
    st.markdown("### 🛡️ Security Control Maturity")
    st.dataframe(maturity, use_container_width=True, hide_index=True)
    gate = security_access_check(username, "connector_sync", workspace, require_approval=False)
    message = "Allowed" if gate["allowed"] else "Blocked"
    if gate["reasons"]:
        message += " · " + " ".join(gate["reasons"])
    st.caption("Current connector-sync authorization: " + message)
    configured = int(maturity["State"].isin(["Verified","Connected","Configured"]).sum()) if not maturity.empty else 0
    c1, c2 = st.columns(2)
    c1.metric("Controls configured / verified", f"{configured}/{len(maturity)}")
    c2.metric("Sensitive session keys", f"{sum(1 for key in st.session_state.keys() if re.search(r"password|token|secret|otp|payment", str(key), re.I)):,}")
    st.caption("SSO/OIDC and MFA remain provider/session dependent. Secret values are never displayed or stored in connector health records.")
    _render_universal_viz("Enterprise Security & Governance", "enterprise_security_posture_df")


# ---------------------------------------------------------------------------
# Cloud persistence + collaboration
# ---------------------------------------------------------------------------

def artifact_fingerprint(value: Any) -> str:
    if isinstance(value, pd.DataFrame):
        raw = value.to_csv(index=False).encode("utf-8")
    else:
        raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def record_artifact(kind: str, name: str, value: Any, source_module: str, owner: str = "unknown", reference: str = "") -> dict[str, Any]:
    entry = {
        "artifact_id": "ART-" + hashlib.sha1(f"{owner}|{kind}|{name}|{_now()}".encode()).hexdigest()[:12].upper(),
        "kind": str(kind),
        "name": str(name),
        "source_module": str(source_module),
        "reference": str(reference),
        "sha256": artifact_fingerprint(value),
        "rows": int(len(value)) if isinstance(value, pd.DataFrame) else None,
        "columns": int(len(value.columns)) if isinstance(value, pd.DataFrame) else None,
        "created_at": _now(),
        "owner": owner,
    }
    catalog = st.session_state.setdefault("shoir_artifact_catalog", [])
    same = next(
        (
            item for item in catalog
            if item.get("kind") == entry["kind"]
            and item.get("name") == entry["name"]
            and item.get("source_module") == entry["source_module"]
            and item.get("sha256") == entry["sha256"]
        ),
        None,
    )
    if same is not None:
        return same
    catalog.insert(0, entry)
    st.session_state["shoir_artifact_catalog"] = catalog[:500]
    return entry


def render_persistence_extension(username: str, show_controls: bool = True) -> None:
    from durable_account_store import durable_backend_configured
    from workspace_persistence import save_user_workspace, load_user_workspace
    st.markdown("### ☁️ Durable Workspace & Artifact Journal")
    cloud_ready = bool(durable_backend_configured())
    catalog = st.session_state.get("shoir_artifact_catalog", [])
    last_save = st.session_state.get("workspace_last_save_ok", st.session_state.get("enterprise_persistence_last_save"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Managed persistence", "Configured" if cloud_ready else "Not configured")
    c2.metric("Artifact records", f"{len(catalog):,}")
    c3.metric("Owner", username or "unknown")
    c4.metric("Last workspace save", "OK" if last_save is True else ("Failed" if last_save is False else "Not recorded"))
    if show_controls:
        save_col, restore_col = st.columns(2)
        with save_col:
            if st.button("💾 Save workspace now", type="primary", use_container_width=True, key="enterprise_persistence_save"):
                try:
                    ok = bool(save_user_workspace(username, st.session_state))
                    st.session_state["enterprise_persistence_last_save"] = ok
                    st.session_state["workspace_last_save_ok"] = ok
                    if ok:
                        st.success("Workspace saved through the active persistence backend.")
                    else:
                        st.warning("Workspace save did not complete. No success message is shown unless the persistence call returned success.")
                except Exception as exc:
                    st.error(f"Workspace save failed safely: {type(exc).__name__}: {exc}")
        with restore_col:
            if st.button("🔄 Restore saved workspace", use_container_width=True, key="enterprise_persistence_restore"):
                try:
                    ok = bool(load_user_workspace(username, st.session_state))
                    if ok:
                        st.success("Saved workspace state restored. The page will refresh with the recovered values.")
                        st.rerun()
                    else:
                        st.warning("No restorable workspace record was returned by the active persistence backend.")
                except Exception as exc:
                    st.error(f"Workspace restore failed safely: {type(exc).__name__}: {exc}")
    if catalog:
        st.dataframe(pd.DataFrame(catalog), use_container_width=True, hide_index=True)
    st.caption("Workspace state, including module datasets/results and artifact metadata, follows the configured persistence path. Exported binary files are represented by provenance/hash metadata unless separately stored in a connected file/object store.")


def render_collaboration_extension(username: str) -> None:
    st.markdown("### 👥 Engineering Collaboration Board")
    users = st.session_state.get("workspace_users", [])
    users_df = _df(users)
    if users_df.empty:
        users_df = pd.DataFrame({"User": [username], "Role": ["Owner"]})
    st.session_state["collaboration_roster_df"] = users_df

    board = st.session_state.setdefault(
        "shoir_collaboration_board",
        {"assignments": [], "mentions": [], "comments": [], "reviewers": []},
    )
    with st.expander("Comments · Mentions · Assignments · Reviewers", expanded=False):
        comment = st.text_area("Comment", key="collab_comment_text")
        mention = st.text_input("Mention", placeholder="@Engineer or @Manager", key="collab_mention_text")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("💬 Add comment", use_container_width=True, key="collab_add_comment"):
                if comment.strip():
                    board["comments"].append({"Actor": username, "Comment": comment.strip(), "Timestamp": _now()})
                    try:
                        from industrial_experience import add_comment
                        add_comment(
                            st.session_state.get("active_project_id") or st.session_state.get("project_id"),
                            st.session_state.get("decision_active_id"),
                            username,
                            comment.strip(),
                        )
                    except Exception:
                        pass
        with c2:
            if st.button("🔔 Add mention", use_container_width=True, key="collab_add_mention"):
                if mention.strip():
                    board["mentions"].append({"Actor": username, "Mention": mention.strip(), "Timestamp": _now()})
        with c3:
            assignee = st.selectbox("Assignee", users_df.iloc[:, 0].astype(str).tolist(), key="collab_assignee")
            if st.button("📌 Assign review", use_container_width=True, key="collab_assign"):
                board["assignments"].append({"Assignee": assignee, "Assigned By": username, "Status": "Pending", "Timestamp": _now()})
        with c4:
            reviewer = st.text_input("Reviewer role", "Engineering Manager", key="collab_reviewer_role")
            if st.button("🧑‍⚖️ Add reviewer", use_container_width=True, key="collab_reviewer"):
                board["reviewers"].append({"Role": reviewer, "Added By": username, "Status": "Pending", "Timestamp": _now()})
        for label, key in [("Comments", "comments"), ("Assignments", "assignments"), ("Reviewers", "reviewers"), ("Mentions", "mentions")]:
            data = pd.DataFrame(board[key])
            if not data.empty:
                st.markdown(f"**{label}**")
                st.dataframe(data, use_container_width=True, hide_index=True)
    st.session_state["shoir_collaboration_board"] = board
    board_frame = pd.DataFrame([x for key in ("assignments", "reviewers") for x in board.get(key, [])])
    if not board_frame.empty:
        st.session_state["collaboration_assignment_df"] = board_frame
    _render_universal_viz("Team Workspaces & RBAC", "collaboration_assignment_df")


# ---------------------------------------------------------------------------
# Research Studio + Reporting
# ---------------------------------------------------------------------------

def _latex_escape(text: str) -> str:
    replacements = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "_": "\\_",
        "#": "\\#",
        "{": "\\{",
        "}": "\\}",
    }
    return "".join(replacements.get(char, char) for char in str(text or ""))


def build_research_manuscript(
    protocol: Mapping[str, Any],
    citations: pd.DataFrame,
    results_tables: Sequence[tuple[str, pd.DataFrame]],
    username: str,
) -> tuple[str, str]:
    """Generate an evidence-bounded manuscript scaffold in Markdown and LaTeX."""
    protocol = dict(protocol or {})
    title = str(protocol.get("title") or protocol.get("research_question") or "Shoir-IE Engineering Study").strip()

    md_lines = [
        f"# {title}",
        "",
        "## Abstract",
        f"**Objective:** {protocol.get('objective') or '[not recorded]'}",
        f"**Research question:** {protocol.get('research_question') or '[not recorded]'}",
        f"**Hypothesis:** {protocol.get('hypothesis') or '[not recorded]'}",
        "",
        "## Methods",
        f"- Methodology: {protocol.get('methodology') or '[not recorded]'}",
        f"- Primary endpoint: {protocol.get('primary_endpoint') or '[not recorded]'}",
        f"- Sample size: {protocol.get('sample_size') if protocol.get('sample_size') is not None else '[not recorded]'}",
        f"- Replications: {protocol.get('replications') if protocol.get('replications') is not None else '[not recorded]'}",
        f"- Alpha: {protocol.get('alpha') if protocol.get('alpha') is not None else '[not recorded]'}",
        f"- Confidence level: {protocol.get('confidence_level') if protocol.get('confidence_level') is not None else '[not recorded]'}",
        f"- Random seed: {protocol.get('random_seed') if protocol.get('random_seed') is not None else '[not recorded]'}",
        "",
        "## Results",
    ]

    has_results = False
    for name, frame in results_tables:
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            has_results = True
            md_lines.append(f"### {name}")
            md_lines.append(frame.head(50).to_html(index=False))
            md_lines.append("")
    if not has_results:
        md_lines.append("[No verified result table is currently recorded.]")

    md_lines.extend([
        "",
        "## Discussion",
        "[Interpret the observed results, uncertainty, practical implications, and competing explanations using only the recorded evidence.]",
        "",
        "## Limitations",
        "- Confirm all assumptions, exclusions, data-quality findings, and validation limitations before submission.",
        "",
        "## Reproducibility",
        f"- Study owner: {username}",
        f"- Protocol hash: {protocol.get('protocol_hash') or '[not recorded]'}",
        "- Include the supplementary evidence bundle and provenance manifest with the manuscript.",
        "",
        "## References",
    ])

    if isinstance(citations, pd.DataFrame) and not citations.empty:
        for _, row in citations.iterrows():
            citation = str(row.get("Citation", "")).strip()
            locator = str(row.get("DOI / URL", "")).strip()
            combined = citation or locator
            if combined:
                md_lines.append(f"- {combined}")
    if len(md_lines) == 0:
        md_lines.append("[No citation records]")

    latex_title = _latex_escape(title)
    latex_lines = [
        "\\documentclass{article}",
        "\\usepackage[margin=1in]{geometry}",
        "\\begin{document}",
        f"\\section*{{{latex_title}}}",
        f"\\textbf{{Objective:}} {_latex_escape(protocol.get('objective') or '[not recorded]')}\\par",
        f"\\textbf{{Research question:}} {_latex_escape(protocol.get('research_question') or '[not recorded]')}\\par",
        f"\\textbf{{Hypothesis:}} {_latex_escape(protocol.get('hypothesis') or '[not recorded]')}",
        "\\section*{Methods}",
        "\\begin{itemize}",
        f"\\item Methodology: {_latex_escape(protocol.get('methodology') or '[not recorded]')}",
        f"\\item Primary endpoint: {_latex_escape(protocol.get('primary_endpoint') or '[not recorded]')}",
        f"\\item Replications: {_latex_escape(protocol.get('replications') if protocol.get('replications') is not None else '[not recorded]')}",
        "\\end{itemize}",
        "\\section*{Results}",
        "Insert verified study tables and exact exported figures from the supplementary evidence bundle.",
        "\\section*{Discussion}",
        "Interpret only the recorded evidence and documented limitations.",
        "\\section*{Reproducibility}",
        f"Study owner: {_latex_escape(username)}. Protocol hash: {_latex_escape(protocol.get('protocol_hash') or '[not recorded]')}.",
        "\\end{document}",
    ]

    return "\n".join(md_lines) + "\n", "\n".join(latex_lines) + "\n"


def render_research_extension(username: str) -> None:
    st.markdown("### 📝 Research Studio Integration")
    st.caption("Protocol → hypothesis → run tracking → citations → results → manuscript/supplementary evidence.")
    proto = st.session_state.get("research_protocol") or st.session_state.get("current_research_protocol") or {}
    if not proto:
        try:
            from industrial_experience import load_research_protocol
            study_id = st.session_state.get("sx_research_study_id") or st.session_state.get("active_research_study_id")
            if study_id:
                proto = load_research_protocol(str(study_id), username) or {}
        except Exception:
            proto = {}
    if isinstance(proto, dict) and proto:
        pcols = st.columns(4)
        pcols[0].metric("Hypothesis", "Defined" if proto.get("hypothesis") else "Missing")
        pcols[1].metric("Primary endpoint", "Defined" if proto.get("primary_endpoint") else "Missing")
        pcols[2].metric("Replications", proto.get("replications", "—"))
        pcols[3].metric("Protocol lock", "Locked" if proto.get("protocol_locked") else "Draft")
    with st.expander("📚 Citations & supplementary evidence", expanded=False):
        citations = st.data_editor(
            st.session_state.setdefault(
                "research_citations_df",
                pd.DataFrame({"Citation": [""], "Role": ["Background"], "DOI / URL": [""], "Notes": [""]}),
            ),
            num_rows="dynamic", use_container_width=True, key="research_citations_editor",
        )
        files = st.data_editor(
            st.session_state.setdefault(
                "research_supplementary_df",
                pd.DataFrame({"File": ["results.csv", "figures/", "protocol.json"], "Purpose": ["Results", "Figures", "Protocol"]}),
            ),
            num_rows="dynamic", use_container_width=True, key="research_supplementary_editor",
        )
        st.session_state["research_citations_df"] = citations.copy(deep=True)
        st.session_state["research_supplementary_df"] = files.copy(deep=True)
        if st.button("🧾 Create manuscript evidence manifest", use_container_width=True, key="research_manifest"):
            manifest = {
                "generated_at": _now(),
                "owner": username,
                "protocol": proto,
                "citations": citations.to_dict("records"),
                "supplementary": files.to_dict("records"),
                "artifact_catalog": st.session_state.get("shoir_artifact_catalog", []),
            }
            st.session_state["research_manuscript_manifest"] = manifest
            st.success("Research manuscript evidence manifest staged.")
        manifest = st.session_state.get("research_manuscript_manifest")
        if isinstance(manifest, dict):
            st.download_button("📥 Download research manifest", json.dumps(manifest, indent=2, default=str).encode(), "shoir_ie_research_manifest.json", "application/json", use_container_width=True)

        protocol_for_paper = proto if isinstance(proto, dict) else {}
        result_tables = []
        for key in [
            "experiment_results", "experiment_factorial_effects", "experiment_mc_results",
            "experiment_bootstrap_results", "experiment_sensitivity_results",
            "experiment_engine_effects_df", "experiment_engine_mc_samples",
            "experiment_engine_bootstrap_df", "experiment_engine_sensitivity_df",
            "experiment_engine_replication_df",
        ]:
            frame = _df(st.session_state.get(key))
            if not frame.empty:
                result_tables.append((key.replace("_", " ").title(), frame))
        st.markdown("#### 📝 Manuscript & Supplementary Package")
        st.caption("Generates a reproducible manuscript scaffold from the recorded protocol and observed result tables. Missing findings stay marked as gaps.")
        if st.button("✍️ Generate manuscript draft", use_container_width=True, key="research_generate_manuscript"):
            md, tex = build_research_manuscript(protocol_for_paper, citations, result_tables, username)
            st.session_state["research_manuscript_md"] = md
            st.session_state["research_manuscript_tex"] = tex
            st.success("Manuscript scaffold generated from the recorded evidence.")
        md = st.session_state.get("research_manuscript_md")
        tex = st.session_state.get("research_manuscript_tex")
        if isinstance(md, str) and md:
            st.download_button("📄 Download manuscript (Markdown)", md.encode("utf-8"), "shoir_ie_manuscript.md", "text/markdown", use_container_width=True, key="research_md_download")
        if isinstance(tex, str) and tex:
            st.download_button("📐 Download manuscript scaffold (LaTeX)", tex.encode("utf-8"), "shoir_ie_manuscript.tex", "text/x-tex", use_container_width=True, key="research_tex_download")
    _render_universal_viz("Experiment Lab", None)


def build_provenance_manifest(module: str, tables: Sequence[tuple[str, pd.DataFrame]], owner: str) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "module": module,
        "owner": owner,
        "generated_at": _now(),
        "tables": [
            {
                "name": name,
                "rows": int(len(df)) if isinstance(df, pd.DataFrame) else 0,
                "columns": int(len(df.columns)) if isinstance(df, pd.DataFrame) else 0,
                "sha256": artifact_fingerprint(df),
            }
            for name, df in tables
            if isinstance(df, pd.DataFrame)
        ],
        "chart": st.session_state.get("liveviz_last_chart_config_" + hashlib.sha1(str(module).encode()).hexdigest()[:12], {}),
    }


def render_reporting_extension(module: str, tables: Sequence[tuple[str, pd.DataFrame]], username: str) -> None:
    manifest = build_provenance_manifest(module, tables, username)
    st.session_state["report_provenance_manifest"] = manifest
    with st.expander("📑 Provenance & exact-graph export manifest", expanded=False):
        st.json(manifest)
        st.caption("The existing Excel/PDF/PowerPoint export actions should receive the same figure object used by the module. This manifest records the source hashes and the exact chart configuration used for reconstruction.")
        st.download_button("📥 Download provenance manifest", json.dumps(manifest, indent=2, default=str).encode(), f"shoir_ie_{re.sub(r'[^A-Za-z0-9]+','_',module).lower()}_provenance.json", "application/json", use_container_width=True)
    _render_universal_viz(module, None)


# ---------------------------------------------------------------------------
# Data Intelligence
# ---------------------------------------------------------------------------

_UNIT_RE = re.compile(r"(?:\(|\[)?\s*(kg|g|mg|lb|ton|t|m|km|cm|mm|l|ml|m3|m²|m2|s|sec|min|hr|h|day|days|%)\s*(?:\)|\])?$", re.I)


def infer_data_intelligence(df: pd.DataFrame, previous: pd.DataFrame | None = None) -> pd.DataFrame:
    d = _df(df)
    rows = []
    for col in d.columns:
        name = str(col)
        lower = name.lower()
        unit = ""
        m = _UNIT_RE.search(name)
        if m:
            unit = m.group(1)
        series = d[col]
        parsed_date = pd.to_datetime(series, errors="coerce") if series.dtype == object else series
        date_like = bool(pd.api.types.is_datetime64_any_dtype(series) or (len(series.dropna()) >= 5 and parsed_date.notna().mean() >= 0.8))
        unique_ratio = float(series.nunique(dropna=True) / max(1, len(series)))
        numeric = pd.api.types.is_numeric_dtype(series)
        outliers = 0
        if numeric:
            s = pd.to_numeric(series, errors="coerce").dropna()
            if len(s) >= 8:
                q1, q3 = s.quantile([0.25, 0.75])
                iqr = q3 - q1
                if iqr > 0:
                    outliers = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
        id_like = bool(re.search(r"(^id$|_id$|id_|identifier|code$|sku|asset|order|wo)", lower))
        drift = np.nan
        if isinstance(previous, pd.DataFrame) and col in previous.columns and numeric:
            old = pd.to_numeric(previous[col], errors="coerce").dropna()
            new = pd.to_numeric(series, errors="coerce").dropna()
            if len(old) >= 10 and len(new) >= 10 and old.std(ddof=1) > 0 and new.std(ddof=1) > 0:
                old_sample = old.sample(min(2000, len(old)), random_state=42)
                new_sample = new.sample(min(2000, len(new)), random_state=42)
                drift = float((new_sample.mean() - old_sample.mean()) / max(abs(old_sample.mean()), 1e-9) * 100)
        rows.append({
            "Column": name,
            "Type": str(series.dtype),
            "Numeric": numeric,
            "Date-like": date_like,
            "ID-like": id_like,
            "Inferred Unit": unit or "Unspecified",
            "Missing %": float(series.isna().mean() * 100),
            "Unique %": unique_ratio * 100,
            "Outliers": outliers,
            "Drift % vs prior": drift,
        })
    return pd.DataFrame(rows)


def render_data_intelligence_extension(module: str, df: pd.DataFrame, previous: pd.DataFrame | None = None) -> None:
    intel = infer_data_intelligence(df, previous)
    st.session_state[f"data_intelligence_{hashlib.sha1(str(module).encode()).hexdigest()[:10]}"] = intel
    st.markdown("### 🔍 Data Intelligence")
    if intel.empty:
        st.info("No table is available for schema intelligence.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fields profiled", f"{len(intel):,}")
    c2.metric("ID-like fields", f"{int(intel['ID-like'].sum()):,}")
    c3.metric("Date-like fields", f"{int(intel['Date-like'].sum()):,}")
    c4.metric("Total outliers", f"{int(intel['Outliers'].sum()):,}")
    st.dataframe(intel, use_container_width=True, hide_index=True)
    _render_universal_viz(module, f"data_intelligence_{hashlib.sha1(str(module).encode()).hexdigest()[:10]}")


# ---------------------------------------------------------------------------
# Knowledge Layer
# ---------------------------------------------------------------------------

def _extract_upload_text(uploaded: Any) -> str:
    name = str(getattr(uploaded, "name", "")).lower()
    raw = uploaded.getvalue()
    if name.endswith((".txt", ".md", ".csv")):
        try:
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return str(raw[:10000])
    if name.endswith(".xlsx"):
        try:
            book = pd.ExcelFile(io.BytesIO(raw))
            chunks = []
            for sheet in book.sheet_names[:10]:
                frame = pd.read_excel(io.BytesIO(raw), sheet_name=sheet)
                chunks.append(f"## {sheet}\n{frame.head(100).to_csv(index=False)}")
            return "\n".join(chunks)
        except Exception:
            return ""
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((page.extract_text() or "") for page in reader.pages[:30])
        except Exception:
            return ""
    if name.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return ""
    return ""


def knowledge_context(query: str = "", max_chars: int = 6000) -> str:
    sources = st.session_state.get("shoir_knowledge_sources", [])
    if not sources:
        return ""
    q_terms = [x for x in re.findall(r"[a-z0-9_]+", str(query).lower()) if len(x) >= 3]
    ranked = []
    for src in sources:
        text = str(src.get("text", ""))
        lower = text.lower()
        score = sum(lower.count(term) for term in q_terms) if q_terms else 0
        ranked.append((score, src))
    ranked.sort(key=lambda x: (-x[0], str(x[1].get("name", ""))))
    blocks = []
    remaining = max_chars
    for score, src in ranked:
        body = str(src.get("text", ""))[:max(0, remaining - 300)]
        if not body:
            continue
        blocks.append(f"[Knowledge source: {src.get('name','unknown')}; relevance={score}]\n{body}")
        remaining -= len(body) + 120
        if remaining <= 0:
            break
    return "\n\n".join(blocks)


def render_knowledge_extension(username: str = "unknown") -> None:
    st.markdown("### 📚 Industrial Knowledge Layer")
    st.caption("Upload SOPs, manuals, standards notes and company guidance. Sources are hashed, stored in workspace state, and made available as evidence context to Copilot.")
    up = st.file_uploader("Upload knowledge source", type=["txt", "md", "csv", "xlsx", "pdf", "docx"], key="knowledge_layer_upload")
    sources = st.session_state.setdefault("shoir_knowledge_sources", [])
    st.session_state.setdefault("knowledge_registry_df", pd.DataFrame(columns=["Source","SHA-256","Owner","Uploaded","Characters"]))
    if up is not None:
        signature = hashlib.sha256(up.getvalue()).hexdigest()
        if not any(x.get("sha256") == signature for x in sources):
            extracted = _extract_upload_text(up)
            if extracted:
                sources.insert(0, {
                    "name": up.name,
                    "sha256": signature,
                    "owner": username,
                    "uploaded_at": _now(),
                    "text": extracted[:200000],
                })
                record_artifact("Knowledge", up.name, extracted, "AI Copilot", username, "shoir_knowledge_sources")
                st.success(f"Knowledge source added: {up.name}")
            else:
                st.warning("The file was accepted but no extractable text was found.")
    if sources:
        table = pd.DataFrame([{
            "Source": x.get("name"),
            "SHA-256": x.get("sha256", "")[:16] + "…",
            "Owner": x.get("owner"),
            "Uploaded": x.get("uploaded_at"),
            "Characters": len(str(x.get("text", ""))),
        } for x in sources])
        st.session_state["knowledge_registry_df"] = table.copy(deep=True)
        st.dataframe(table, use_container_width=True, hide_index=True)
        query = st.text_input("Knowledge search", key="knowledge_layer_query")
        if query:
            ctx = knowledge_context(query, 3500)
            st.text_area("Copilot context preview", ctx, height=180, disabled=True)
    _render_universal_viz("AI Copilot", None)


# ---------------------------------------------------------------------------
# Model registry, jobs, real-time monitoring, economics, sustainability,
# human factors and geospatial integration layers
# ---------------------------------------------------------------------------

def render_model_registry_extension(username: str = "unknown") -> None:
    st.markdown("### 🧬 Model Reproducibility Layer")
    st.caption("Adds solver-version and result-hash governance to the existing Model Registry without replacing its current records.")
    registry = st.session_state.get("model_registry_df", pd.DataFrame())
    reg = _df(registry)
    c1, c2, c3 = st.columns(3)
    model_version = c1.text_input("Model version", "1.1.0", key="model_ext_version")
    solver_version = c2.text_input("Solver / runtime version", "CBC / HiGHS / SciPy", key="model_ext_solver")
    result_ref = c3.text_input("Result reference", "current workspace result", key="model_ext_result_ref")
    if st.button("🧬 Record reproducibility snapshot", use_container_width=True, key="model_ext_record"):
        entry = {
            "Model Version": model_version.strip(),
            "Solver Version": solver_version.strip(),
            "Result Reference": result_ref.strip(),
            "Data Hash": artifact_fingerprint(reg) if not reg.empty else "",
            "Recorded By": username,
            "Recorded At": _now(),
        }
        catalog = st.session_state.setdefault("model_reproducibility_catalog", [])
        catalog.insert(0, entry)
        st.session_state["model_reproducibility_catalog"] = catalog[:200]
        record_artifact("Model Snapshot", model_version, entry, "Engineering Model Registry", username, "model_reproducibility_catalog")
        st.success("Reproducibility snapshot recorded.")
    data = pd.DataFrame(st.session_state.get("model_reproducibility_catalog", []))
    if not data.empty:
        st.dataframe(data, use_container_width=True, hide_index=True)
    _render_universal_viz("Engineering Model Registry", "model_registry_governance_df")


def render_jobs_extension(username: str = "unknown", module: str = "Industrial Simulation Lab") -> None:
    st.markdown("### 🕐 Engineering Job Control")
    st.caption("Uses the existing durable job registry for queue, progress, pause/resume, cancellation and retry state. Execution remains operator-controlled unless a worker backend is configured.")
    try:
        from industrial_experience import create_job, update_job, ensure_experience_db
        ensure_experience_db()
        with st.expander("Create / control job", expanded=False):
            job_type = st.selectbox("Job type", ["Simulation", "Optimization", "Forecast", "Report", "Data profiling"], key=f"job_ext_type_{module}")
            payload_text = st.text_area("Job payload JSON", '{"priority":"standard","requested_by":"operator"}', key=f"job_ext_payload_{module}")
            if st.button("➕ Queue job", use_container_width=True, key=f"job_ext_queue_{module}"):
                try:
                    payload = json.loads(payload_text)
                except Exception:
                    payload = {"raw_payload": payload_text}
                jid = create_job(module, job_type, username, payload)
                st.session_state["job_ext_active"] = jid
                st.success(f"Queued {jid}")
            active = st.session_state.get("job_ext_active")
            if active:
                state = st.selectbox("State action", ["Running", "Paused", "Queued", "Cancelled", "Completed", "Failed"], key=f"job_ext_state_{module}")
                progress = st.slider("Progress %", 0, 100, 50, key=f"job_ext_progress_{module}")
                if st.button("🔄 Apply job state", use_container_width=True, key=f"job_ext_update_{module}"):
                    update_job(active, state, progress, f"Operator set state to {state}.")
                    st.success(f"{active} → {state}")
        try:
            import sqlite3
            with sqlite3.connect("enterprise_full_workspace.db") as conn:
                history = pd.read_sql(
                    "SELECT job_id,module,job_type,status,progress,message,started_at,finished_at FROM experience_jobs ORDER BY COALESCE(started_at, finished_at) DESC LIMIT 200",
                    conn,
                )
            if not history.empty:
                st.dataframe(history, use_container_width=True, hide_index=True)
                st.session_state["job_history_df"] = history
                _render_universal_viz(module, "job_history_df")
        except Exception as exc:
            st.warning(f"Job history unavailable: {type(exc).__name__}: {exc}")
    except Exception as exc:
        st.warning(f"Job controls unavailable: {type(exc).__name__}: {exc}")


def build_realtime_monitoring(df: pd.DataFrame, threshold: float | None = None) -> pd.DataFrame:
    d = _df(df)
    if d.empty:
        return pd.DataFrame()
    d = d.copy()
    time_col = next((c for c in d.columns if any(x in str(c).lower() for x in ("timestamp", "time", "date"))), None)
    value_col = next((c for c in d.columns if pd.api.types.is_numeric_dtype(d[c]) and any(x in str(c).lower() for x in ("value", "reading", "measurement", "vibration", "temperature", "pressure"))), None)
    if value_col is None:
        nums = [c for c in d.columns if pd.api.types.is_numeric_dtype(d[c])]
        value_col = nums[0] if nums else None
    if value_col is None:
        return d
    values = _numeric(d[value_col])
    mean = float(values.mean()) if values.notna().any() else np.nan
    sd = float(values.std(ddof=1)) if values.notna().sum() > 1 else 0.0
    d["Z-Score"] = (values - mean) / max(sd, 1e-9)
    d["Anomaly"] = d["Z-Score"].abs() >= 3.0
    if threshold is not None:
        d["Threshold"] = float(threshold)
        d["Threshold Breach"] = values > float(threshold)
    if time_col:
        d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
        d = d.sort_values(time_col)
    return d


def _load_persisted_telemetry(limit: int = 500) -> pd.DataFrame:
    try:
        import sqlite3
        with sqlite3.connect("enterprise_full_workspace.db", timeout=10) as conn:
            data = pd.read_sql(
                "SELECT asset_id AS Asset, ts AS Timestamp, metric AS Metric, value AS Value, source AS Source "
                "FROM telemetry_events ORDER BY id DESC LIMIT ?",
                conn,
                params=(int(limit),),
            )
        return data.sort_values("Timestamp")
    except Exception:
        return pd.DataFrame()


def render_realtime_monitoring_extension(sensor_df: Any = None, module: str = "Digital Twin & DES") -> None:
    source = _df(sensor_df if sensor_df is not None else st.session_state.get("iot_sensors", []))
    persisted = _load_persisted_telemetry()
    if not persisted.empty and (source.empty or "Timestamp" not in source.columns):
        source = persisted
    monitor = build_realtime_monitoring(source)
    st.session_state[f"realtime_monitoring_{hashlib.sha1(module.encode()).hexdigest()[:10]}"] = monitor
    st.markdown("### 📡 Real-Time Monitoring & Anomaly Detection")
    if monitor.empty:
        st.info("No telemetry stream is available yet.")
        return
    numeric = [c for c in monitor.columns if pd.api.types.is_numeric_dtype(monitor[c])]
    metric = st.selectbox("Telemetry measure", numeric, key=f"rt_metric_{module}")
    threshold = st.number_input("Optional alert threshold", value=float(_numeric(monitor[metric]).median()) if monitor[metric].notna().any() else 0.0, key=f"rt_threshold_{module}")
    if st.button("↻ Refresh persisted telemetry", use_container_width=True, key=f"rt_refresh_{module}"):
        refreshed = _load_persisted_telemetry()
        if not refreshed.empty:
            source = refreshed
    updated = build_realtime_monitoring(source, threshold)
    st.session_state[f"realtime_monitoring_{hashlib.sha1(module.encode()).hexdigest()[:10]}"] = updated
    anomalies = int(updated.get("Anomaly", pd.Series(dtype=bool)).sum()) if "Anomaly" in updated.columns else 0
    breaches = int(updated.get("Threshold Breach", pd.Series(dtype=bool)).sum()) if "Threshold Breach" in updated.columns else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Samples", f"{len(updated):,}")
    c2.metric("3σ anomalies", f"{anomalies:,}")
    c3.metric("Threshold breaches", f"{breaches:,}")
    st.dataframe(updated, use_container_width=True, hide_index=True)
    if metric in updated.columns:
        time_col = next((c for c in updated.columns if pd.api.types.is_datetime64_any_dtype(updated[c])), None)
        fig = px.line(updated, x=time_col if time_col else updated.index, y=metric, title=f"{module} · Live Monitoring")
        st.plotly_chart(fig, use_container_width=True)
    _render_universal_viz(module, f"realtime_monitoring_{hashlib.sha1(module.encode()).hexdigest()[:10]}")


def render_economics_extension(username: str = "unknown") -> None:
    st.markdown("### 💰 Total Cost of Ownership & Decision Economics")
    st.caption("Extends the existing engineering-economics workflow with lifecycle TCO and scenario-ready economics evidence.")
    base_capex = float(st.number_input("CAPEX", 0.0, 1e9, 150000.0, key="econ_ext_capex"))
    annual_opex = float(st.number_input("Annual OPEX", 0.0, 1e9, 35000.0, key="econ_ext_opex"))
    years = int(st.number_input("Lifecycle years", 1, 50, 10, key="econ_ext_years"))
    salvage = float(st.number_input("End-of-life salvage", 0.0, 1e9, 10000.0, key="econ_ext_salvage"))
    discount = float(st.number_input("Discount rate", 0.0, 1.0, 0.10, key="econ_ext_discount"))
    rows = []
    balance = base_capex
    discounted_opex = 0.0
    for year in range(1, years + 1):
        discounted = annual_opex / ((1 + discount) ** year)
        discounted_opex += discounted
        rows.append({"Year": year, "OPEX": annual_opex, "Discounted OPEX": discounted})
    tco_nominal = base_capex + annual_opex * years - salvage
    tco_discounted = base_capex + discounted_opex - salvage / ((1 + discount) ** years)
    out = pd.DataFrame(rows)
    out["Cumulative Nominal OPEX"] = out["OPEX"].cumsum()
    st.session_state["engineering_economics_tco_df"] = out
    c1, c2, c3 = st.columns(3)
    c1.metric("Nominal TCO", f"{tco_nominal:,.2f}")
    c2.metric("Discounted TCO", f"{tco_discounted:,.2f}")
    c3.metric("Lifecycle", f"{years} yr")
    st.dataframe(out, use_container_width=True, hide_index=True)
    st.plotly_chart(px.line(out, x="Year", y=["OPEX", "Discounted OPEX"], title="Lifecycle OPEX Profile"), use_container_width=True)
    record_artifact("Economics", "TCO", out, "Engineering Economics", username, "engineering_economics_tco_df")


def render_sustainability_extension(username: str = "unknown") -> None:
    st.markdown("### 🌱 Sustainability-to-Decision Bridge")
    carbon = _df(st.session_state.get("carbon_sources", []))
    energy = _df(st.session_state.get("energy_units", []))
    lca = _df(st.session_state.get("lca_materials", []))
    rows = []
    if not carbon.empty:
        col = next((c for c in carbon.columns if any(x in str(c).lower() for x in ("co2", "emission", "carbon"))), None)
        val = float(_numeric(carbon[col]).sum()) if col else np.nan
        rows.append({"Metric": "Carbon", "Value": val, "Unit": "Configured source unit"})
    if not energy.empty:
        col = next((c for c in energy.columns if any(x in str(c).lower() for x in ("kwh", "energy", "consumption"))), None)
        val = float(_numeric(energy[col]).sum()) if col else np.nan
        rows.append({"Metric": "Energy", "Value": val, "Unit": "Configured source unit"})
    if not lca.empty:
        numeric = lca.select_dtypes(include=np.number)
        for col in list(numeric.columns)[:3]:
            rows.append({"Metric": f"LCA · {col}", "Value": float(_numeric(lca[col]).sum()), "Unit": "Source unit"})
    summary = pd.DataFrame(rows)
    st.session_state["sustainability_decision_bridge_df"] = summary
    if summary.empty:
        st.info("No sustainability source data is currently available.")
        return
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.plotly_chart(px.bar(summary, x="Metric", y="Value", title="Sustainability KPI Bridge"), use_container_width=True)
    _render_universal_viz("Industrial Sustainability & LCA", "sustainability_decision_bridge_df")


def render_benchmarking_evidence(username: str = "unknown") -> None:
    """Extend the existing Benchmarking module with measured ROI evidence."""
    from benchmark_harness import calculate_roi_evidence

    st.markdown("### 🧪 Benchmark & ROI Evidence Lab")
    st.caption("Enter measured baseline and Shoir-IE timings. The calculator does not invent savings; it exposes the assumptions used to derive them.")
    c1, c2, c3 = st.columns(3)
    baseline = c1.number_input("Baseline cycle time (minutes)", 0.0, 100000.0, 240.0, 5.0, key="roi_baseline_minutes")
    shoir = c2.number_input("Shoir-IE cycle time (minutes)", 0.0, 100000.0, 18.0, 1.0, key="roi_shoir_minutes")
    runs = c3.number_input("Annual runs", 0.0, 10000000.0, 250.0, 10.0, key="roi_annual_runs")
    c4, c5, c6 = st.columns(3)
    hourly_rate = c4.number_input("Engineering labor rate / hour", 0.0, 100000.0, 50.0, 5.0, key="roi_hourly_rate")
    implementation_cost = c5.number_input("Implementation cost", 0.0, 100000000.0, 25000.0, 1000.0, key="roi_implementation_cost")
    adoption = c6.slider("Expected adoption fraction", 0.0, 1.0, 1.0, 0.05, key="roi_adoption_fraction")
    result = calculate_roi_evidence(baseline, shoir, runs, hourly_rate, implementation_cost, adoption)
    metrics = pd.DataFrame([{
        "Metric": "Annual hours saved", "Value": result["annual_hours_saved"], "Unit": "hours/year",
    }, {
        "Metric": "Annual labor value", "Value": result["annual_labor_value"], "Unit": "currency/year",
    }, {
        "Metric": "First-year net value", "Value": result["first_year_net_value"], "Unit": "currency",
    }, {
        "Metric": "Cycle reduction", "Value": result["cycle_reduction_pct"] or 0.0, "Unit": "%",
    }])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Annual hours saved", f"{result["annual_hours_saved"]:,.1f}")
    m2.metric("Annual labor value", f"{result["annual_labor_value"]:,.2f}")
    payback = result["payback_months"]
    m3.metric("Payback", f"{payback:,.1f} months" if payback is not None else "Not reached")
    m4.metric("Cycle reduction", f"{result["cycle_reduction_pct"]:,.1f}%" if result["cycle_reduction_pct"] is not None else "n/a")
    st.dataframe(metrics, use_container_width=True, hide_index=True)
    st.caption("Evidence status: " + result["evidence_status"] + ". Replace defaults with measured pilot data before using the values externally.")
    st.session_state["benchmark_roi_df"] = metrics.copy(deep=True)
    _render_universal_viz("Benchmarking & Engineering Standards", "benchmark_roi_df")

def render_human_factors_extension(username: str = "unknown") -> None:
    st.markdown("### 🧑‍🏭 Workforce & Human-Factors Decision Layer")
    tasks = _df(st.session_state.get("ergonomic_tasks", []))
    studies = _df(st.session_state.get("time_studies", []))
    source = tasks if not tasks.empty else studies
    if source.empty:
        st.info("No ergonomic or time-study records are available.")
        return
    numeric = list(source.select_dtypes(include=np.number).columns)
    if not numeric:
        st.dataframe(source, use_container_width=True, hide_index=True)
        return
    metrics = []
    for col in numeric[:6]:
        values = _numeric(source[col]).dropna()
        mean_value = float(values.mean()) if len(values) else np.nan
        p95_value = float(values.quantile(0.95)) if len(values) else np.nan
        metrics.append({
            "Measure": col,
            "Mean": mean_value,
            "P95": p95_value,
            "Spread (P95-Mean)": p95_value - mean_value if np.isfinite(mean_value) and np.isfinite(p95_value) else np.nan,
            "CV %": float(values.std(ddof=1) / values.mean() * 100) if len(values) > 1 and values.mean() else np.nan,
        })
    result = pd.DataFrame(metrics)
    st.session_state["human_factors_metrics_df"] = result
    st.dataframe(result, use_container_width=True, hide_index=True)
    st.plotly_chart(px.bar(
        result,
        x="Measure",
        y="Mean",
        hover_data=["P95", "Spread (P95-Mean)", "CV %"],
        title="Human Factors / Workload Measures",
    ), use_container_width=True)
    st.caption("These outputs are engineering workload measures, not medical or clinical assessments.")


def render_geospatial_extension(username: str = "unknown") -> None:
    st.markdown("### 🗺️ Geospatial Network Intelligence")
    nodes = _df(st.session_state.get("supply_nodes", []))
    markets = _df(st.session_state.get("demand_markets", []))
    if nodes.empty or markets.empty:
        st.info("Provide both facility and demand-market coordinates to build the network intelligence view.")
        return
    rows = []
    rate = float(st.number_input("Scenario freight-rate multiplier", 0.5, 2.0, 1.0, 0.05, key="geo_ext_rate"))
    for _, n in nodes.iterrows():
        for _, m in markets.iterrows():
            if not {"lat", "lon"} <= set(n.index) or not {"lat", "lon"} <= set(m.index):
                continue
            dist = float(np.hypot(float(n["lat"]) - float(m["lat"]), float(n["lon"]) - float(m["lon"])) * 111.0)
            demand = float(_numeric([m.get("demand_tons_yr", 0)]).fillna(0).iloc[0])
            rows.append({
                "Origin": str(n.get("name", n.get("id", "Facility"))),
                "Destination": str(m.get("market", "Market")),
                "Distance km": dist,
                "Demand tons/yr": demand,
                "Scenario Freight Cost": dist * demand * rate,
            })
    routes = pd.DataFrame(rows)
    st.session_state["geospatial_network_routes_df"] = routes
    st.dataframe(routes.head(100), use_container_width=True, hide_index=True)
    if not routes.empty:
        st.plotly_chart(px.scatter(routes, x="Distance km", y="Scenario Freight Cost", size="Demand tons/yr", hover_data=["Origin","Destination"], title="Geospatial Route / Cost Surface"), use_container_width=True)


def render_artifact_journal_for_tables(module: str, tables: Sequence[tuple[str, pd.DataFrame]], username: str) -> None:
    for name, frame in tables:
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            record_artifact("Table", name, frame, module, username, "workspace-state")
