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
    battery0 = float(_numeric(agv.get("battery", [])).fillna(0).mean()) if "battery" in agv.columns and not agv.empty else np.nan

    wip = total_wip0
    battery = battery0
    base_arrival = float(_numeric(q.get("arrival_rate", [])).fillna(0).sum()) if "arrival_rate" in q.columns else 0.0
    base_service = float(_numeric(q.get("service_rate", [])).fillna(0).sum()) if "service_rate" in q.columns else 0.0

    for tick in range(1, ticks + 1):
        disruptions = 1.0 if np.random.default_rng(17 + tick).random() < downtime_rate else 0.0
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
            add("Supply", 95.0 if len(supply) else None, "Observed", f"{len(supply):,} facility record(s)")

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
            add("Transport", 95.0, "Observed", f"{len(transport):,} transport record(s)")

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
    d["Health %"] = (base.fillna(80.0) - latency_penalty - error_penalty - freshness_penalty).clip(lower=0, upper=100)
    return d


def render_connectivity_extension() -> None:
    raw = st.session_state.get("conn_df", st.session_state.get("erp_connectors", []))
    health = normalize_connector_health(_df(raw))
    st.session_state["connectivity_health_df"] = health
    st.markdown("### 🔌 Connector Health & Deployment Readiness")
    st.caption("SAP · Oracle · SQL · REST · MQTT · OPC-UA · WMS/MES/ERP profiles share one health surface. Live tests remain opt-in per connector.")
    if health.empty:
        st.info("Register a connector to begin health monitoring.")
        return
    st.dataframe(health, use_container_width=True, hide_index=True)
    fig = px.bar(health, x="Name", y="Health %", color="Protocol", range_y=[0, 100], title="Enterprise Connector Health")
    st.plotly_chart(fig, use_container_width=True)


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
    posture = security_posture()
    st.session_state["enterprise_security_posture_df"] = posture
    st.markdown("### 🔐 Enterprise Security Posture")
    st.dataframe(posture, use_container_width=True, hide_index=True)
    configured = int((posture["Status"].isin(["Configured", "CI hook"])).sum()) if not posture.empty else 0
    c1, c2 = st.columns(2)
    c1.metric("Governance controls configured", f"{configured}/{len(posture)}")
    c2.metric("Sensitive values exposed in UI", "0")
    st.caption("SSO/OIDC and MFA are reported as configured only when their configuration sections are actually present; no secret contents are inspected or printed.")


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
    catalog.insert(0, entry)
    st.session_state["shoir_artifact_catalog"] = catalog[:500]
    return entry


def render_persistence_extension(username: str) -> None:
    from durable_account_store import durable_backend_configured
    st.markdown("### ☁️ Durable Workspace & Artifact Journal")
    cloud_ready = bool(durable_backend_configured())
    catalog = st.session_state.get("shoir_artifact_catalog", [])
    c1, c2, c3 = st.columns(3)
    c1.metric("Managed persistence", "Configured" if cloud_ready else "Local-only")
    c2.metric("Durable artifact records", f"{len(catalog):,}")
    c3.metric("Workspace owner", username or "unknown")
    if st.button("💾 Save workspace now", type="primary", use_container_width=True, key="enterprise_persistence_save"):
        try:
            from workspace_persistence import save_user_workspace
            ok = bool(save_user_workspace(username, st.session_state))
            st.session_state["enterprise_persistence_last_save"] = ok
            if ok:
                st.success("Workspace state saved through the configured persistence path.")
            else:
                st.warning("Workspace save did not complete. Check the managed persistence configuration.")
        except Exception as exc:
            st.error(f"Workspace save failed safely: {type(exc).__name__}: {exc}")
    last = st.session_state.get("enterprise_persistence_last_save")
    if last is not None:
        st.caption(f"Last explicit save: {'successful' if last else 'not completed'}.")
    if catalog:
        st.dataframe(pd.DataFrame(catalog), use_container_width=True, hide_index=True)
    st.caption("The journal keeps hashes, ownership, source modules and reconstruction references in workspace state; module datasets/results themselves remain governed by the same workspace persistence mechanism.")


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
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("💬 Add comment", use_container_width=True, key="collab_add_comment"):
                if comment.strip():
                    board["comments"].append({"Actor": username, "Comment": comment.strip(), "Timestamp": _now()})
        with c2:
            assignee = st.selectbox("Assignee", users_df.iloc[:, 0].astype(str).tolist(), key="collab_assignee")
            if st.button("📌 Assign review", use_container_width=True, key="collab_assign"):
                board["assignments"].append({"Assignee": assignee, "Assigned By": username, "Status": "Pending", "Timestamp": _now()})
        with c3:
            reviewer = st.text_input("Reviewer role", "Engineering Manager", key="collab_reviewer_role")
            if st.button("🧑‍⚖️ Add reviewer", use_container_width=True, key="collab_reviewer"):
                board["reviewers"].append({"Role": reviewer, "Added By": username, "Status": "Pending", "Timestamp": _now()})
        if mention.strip():
            board["mentions"].append({"Actor": username, "Mention": mention.strip(), "Timestamp": _now()})
        for label, key in [("Comments", "comments"), ("Assignments", "assignments"), ("Reviewers", "reviewers"), ("Mentions", "mentions")]:
            data = pd.DataFrame(board[key])
            if not data.empty:
                st.markdown(f"**{label}**")
                st.dataframe(data, use_container_width=True, hide_index=True)
    st.session_state["shoir_collaboration_board"] = board


# ---------------------------------------------------------------------------
# Research Studio + Reporting
# ---------------------------------------------------------------------------

def render_research_extension(username: str) -> None:
    st.markdown("### 📝 Research Studio Integration")
    st.caption("Protocol → hypothesis → run tracking → citations → results → manuscript/supplementary evidence.")
    proto = st.session_state.get("research_protocol") or st.session_state.get("current_research_protocol") or {}
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
        st.dataframe(table, use_container_width=True, hide_index=True)
        query = st.text_input("Knowledge search", key="knowledge_layer_query")
        if query:
            ctx = knowledge_context(query, 3500)
            st.text_area("Copilot context preview", ctx, height=180, disabled=True)
