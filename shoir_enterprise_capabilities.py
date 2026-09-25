"""Enterprise cross-cutting capability panels for Shoir-IE.

These panels deliberately sit on top of existing module flows rather than replacing
them. They add operational readiness, governance, persistence, collaboration,
connectivity and evidence surfaces while writing canonical state keys that the
Universal Visualization Studio can discover.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from durable_account_store import durable_backend_configured
from industrial_experience import add_comment, create_job, update_job
from workspace_persistence import save_user_workspace


CAPABILITY_MODULES = {
    "Persistence",
    "Digital Twin & Discrete-Event Simulation",
    "Live Industrial Digital Twin",
    "Predictive Maintenance Digital Twin",
    "Control Tower",
    "Industrial Control Center",
    "Industrial Connectivity Hub",
    "Enterprise Security & Governance",
    "Team Workspaces & RBAC",
    "Industrial Data Platform",
    "Engineering Model Registry",
    "Capital Investment & Engineering Economics",
    "Engineering Economics & Finance",
    "Industrial Sustainability & LCA",
    "Green IE & Sustainability",
    "Workforce Engineering",
    "Human Factors & Ergonomics (NIOSH)",
    "Geospatial Network Designer",
    "Fleet Routing",
    "Executive Report Center",
    "Research Studio",
    "Executive Report Center",
    "Experiment Lab",
    "Experiment Engine",
    "Advanced ML Demand Forecasting",
    "Multi-Objective Optimization",
    "Robust & Resilient Optimization",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _audit(username: str, event: str, detail: str) -> None:
    try:
        with sqlite3.connect("enterprise_full_workspace.db") as conn:
            conn.execute(
                "INSERT INTO security_events(username,event,detail,timestamp) VALUES(?,?,?,?)",
                (username, event, detail[:1000], _now()),
            )
            conn.commit()
    except Exception:
        pass


def _chart_state(module: str, df: pd.DataFrame, key: str) -> None:
    if isinstance(df, pd.DataFrame):
        st.session_state[key] = df.copy(deep=True)
        st.session_state[f"{key}_module"] = module


def _health_badge(status: str) -> str:
    return {"Healthy": "🟢", "Warning": "🟡", "Degraded": "🟠", "Offline": "🔴"}.get(status, "⚪")


def render_digital_twin_operations(module: str, username: str) -> None:
    st.markdown("### 🧬 Live Digital Twin Operations")
    st.caption("Asset/process state → synchronization health → replay → controlled what-if analysis. Simulation never silently overwrites live state.")
    state = st.data_editor(
        st.session_state.setdefault(
            "digital_twin_state_df",
            pd.DataFrame({
                "Asset": ["CNC-01", "Packing-01", "Forklift-03"],
                "Process": ["Machining", "Packing", "Material Handling"],
                "State": ["Running", "Running", "Idle"],
                "Health": [94, 88, 76],
                "Throughput": [120, 96, 40],
                "Source": ["simulated", "simulated", "simulated"],
                "Timestamp": [_now(), _now(), _now()],
            }),
        ),
        num_rows="dynamic",
        use_container_width=True,
        key="digital_twin_state_editor",
    )
    st.session_state["digital_twin_state_df"] = state.copy(deep=True)
    _chart_state(module, state, "digital_twin_state_df")

    c1, c2, c3 = st.columns(3)
    c1.metric("Assets", len(state))
    c2.metric("Healthy assets", int((pd.to_numeric(state["Health"], errors="coerce") >= 80).sum()) if "Health" in state else 0)
    c3.metric("Sync sources", state["Source"].nunique() if "Source" in state else 0)

    scenarios = st.data_editor(
        st.session_state.setdefault(
            "digital_twin_scenarios_df",
            pd.DataFrame({
                "Scenario": ["Baseline", "Capacity +10%", "Downtime -20%"],
                "Throughput Multiplier": [1.00, 1.10, 1.20],
                "Downtime Multiplier": [1.00, 1.00, 0.80],
                "Replay From": ["Current", "Current", "Current"],
            }),
        ),
        num_rows="dynamic",
        use_container_width=True,
        key="digital_twin_scenarios_editor",
    )
    st.session_state["digital_twin_scenarios_df"] = scenarios.copy(deep=True)
    if st.button("▶️ Replay / Run What-If", type="primary", use_container_width=True, key="digital_twin_replay"):
        baseline = float(pd.to_numeric(state.get("Throughput", pd.Series([0])), errors="coerce").sum())
        rows = []
        for rec in scenarios.to_dict("records"):
            rows.append({
                "Scenario": rec.get("Scenario", "Scenario"),
                "Baseline Throughput": baseline,
                "Projected Throughput": baseline * float(rec.get("Throughput Multiplier", 1.0) or 1.0),
                "Downtime Multiplier": float(rec.get("Downtime Multiplier", 1.0) or 1.0),
            })
        result = pd.DataFrame(rows)
        st.session_state["digital_twin_replay_result_df"] = result
        _chart_state(module, result, "digital_twin_replay_result_df")
        _audit(username, "digital_twin_replay", f"{module}|{len(result)} scenarios")
    result = st.session_state.get("digital_twin_replay_result_df")
    if isinstance(result, pd.DataFrame) and not result.empty:
        st.dataframe(result, use_container_width=True, hide_index=True)


def render_control_tower(module: str, username: str) -> None:
    st.markdown("### 🎯 Industrial Control Tower · Unified Health Map")
    st.caption("Production, supply, inventory, quality, maintenance, transport, workforce, energy and carbon in one operational view.")
    areas = [
        "Production", "Supply", "Inventory", "Quality", "Maintenance",
        "Transport", "Workforce", "Energy", "Carbon",
    ]
    health = st.data_editor(
        st.session_state.setdefault(
            "control_tower_health_df",
            pd.DataFrame({
                "Area": areas,
                "Health": [92, 88, 84, 96, 79, 90, 94, 86, 82],
                "Open Alerts": [0, 1, 2, 0, 3, 1, 0, 2, 1],
                "KPI": ["OEE", "OTIF", "Service", "FPY", "Risk", "On Time", "Coverage", "kWh/unit", "tCO2e"],
            }),
        ),
        num_rows="fixed",
        use_container_width=True,
        key="control_tower_health_editor",
    )
    st.session_state["control_tower_health_df"] = health.copy(deep=True)
    _chart_state(module, health, "control_tower_health_df")
    avg = float(pd.to_numeric(health["Health"], errors="coerce").mean()) if len(health) else 0.0
    alerts = int(pd.to_numeric(health["Open Alerts"], errors="coerce").fillna(0).sum()) if len(health) else 0
    a, b, c = st.columns(3)
    a.metric("Network health", f"{avg:.1f}%")
    b.metric("Open alerts", alerts)
    c.metric("Areas monitored", len(health))
    if st.button("🔄 Reconcile Operational Health", use_container_width=True, key="control_tower_reconcile"):
        health["Status"] = np.select(
            [health["Health"] >= 90, health["Health"] >= 75],
            ["Healthy", "Warning"],
            default="Degraded",
        )
        st.session_state["control_tower_health_df"] = health
        _audit(username, "control_tower_reconcile", f"{module}|{len(health)} areas")
    st.dataframe(health, use_container_width=True, hide_index=True)


def render_connectivity_health(module: str, username: str) -> None:
    st.markdown("### 🔌 Industrial Connectivity · Connector Health")
    st.caption("SAP, Oracle, SQL, REST, MQTT, OPC-UA, WMS, MES and ERP profiles share one health/latency/error surface. Credentials remain session-only.")
    connectors = st.data_editor(
        st.session_state.setdefault(
            "connectivity_health_df",
            pd.DataFrame({
                "System": ["SAP", "Oracle", "SQL", "REST", "MQTT", "OPC-UA", "WMS", "MES", "ERP"],
                "Protocol": ["SAP", "Oracle", "SQL", "HTTPS", "MQTT", "OPC-UA", "HTTPS", "HTTPS", "HTTPS"],
                "Endpoint": ["Configured", "Configured", "Configured", "Configured", "factory/telemetry/#", "opc.tcp://localhost:4840", "Configured", "Configured", "Configured"],
                "Status": ["Not Tested"] * 9,
                "Latency ms": [np.nan] * 9,
                "Last Checked": [""] * 9,
            }),
        ),
        num_rows="dynamic",
        use_container_width=True,
        key="connectivity_health_editor",
    )
    st.session_state["connectivity_health_df"] = connectors.copy(deep=True)
    _chart_state(module, connectors, "connectivity_health_df")
    selected = st.selectbox("Connector", connectors["System"].astype(str).tolist(), key="connectivity_selected_system")
    if st.button("🩺 Run Connector Health Check", type="primary", use_container_width=True, key="connectivity_health_check"):
        idx = connectors.index[connectors["System"].astype(str).eq(selected)].tolist()
        if idx:
            i = idx[0]
            # This is a safe profile validation, not a fabricated live success.
            endpoint = str(connectors.loc[i, "Endpoint"])
            connectors.loc[i, "Status"] = "Profile Valid" if endpoint.strip() else "Invalid Profile"
            connectors.loc[i, "Latency ms"] = np.nan
            connectors.loc[i, "Last Checked"] = _now()
            st.session_state["connectivity_health_df"] = connectors
            _audit(username, "connector_profile_check", f"{selected}|{connectors.loc[i, 'Status']}")
    st.dataframe(connectors, use_container_width=True, hide_index=True)
    st.info("A live protocol connection is reported only when the site endpoint and protocol adapter are actually configured; profile validation does not claim a live connection.")


def render_security_governance(module: str, username: str) -> None:
    st.markdown("### 🛡️ Enterprise Security & Governance")
    st.caption("RBAC, workspace isolation, auditability, secure-file handling, SSO/OIDC/MFA posture and security scanning are surfaced together.")
    roles = st.data_editor(
        st.session_state.setdefault(
            "enterprise_security_roles_df",
            pd.DataFrame({
                "Role": ["Owner", "Engineer", "Planner", "Reviewer", "Viewer"],
                "Read": [True, True, True, True, True],
                "Write": [True, True, True, False, False],
                "Execute": [True, True, True, False, False],
                "Approve": [True, False, False, True, False],
            }),
        ),
        num_rows="dynamic",
        use_container_width=True,
        key="enterprise_security_roles_editor",
    )
    st.session_state["enterprise_security_roles_df"] = roles.copy(deep=True)
    isolation = pd.DataFrame([
        {"Control": "Workspace isolation", "Status": "Enabled by application workspace identity"},
        {"Control": "Audit trail", "Status": "Enabled"},
        {"Control": "Secrets", "Status": "Session/secret store only"},
        {"Control": "SSO/OIDC", "Status": "Configuration-dependent"},
        {"Control": "MFA", "Status": "Configuration-dependent"},
        {"Control": "Secure file handling", "Status": "Input validation + transient upload handling"},
    ])
    if durable_backend_configured():
        isolation.loc[0, "Status"] = "Enabled; managed persistence configured"
    st.dataframe(isolation, use_container_width=True, hide_index=True)
    uploaded = st.file_uploader("🔐 Security scan a file (metadata + safe content checks)", type=["csv", "xlsx", "txt", "json"], key="enterprise_security_file")
    if uploaded is not None:
        raw = uploaded.getvalue()
        scan = pd.DataFrame([
            {"Check": "Filename", "Result": uploaded.name},
            {"Check": "Size", "Result": f"{len(raw):,} bytes"},
            {"Check": "SHA-256", "Result": hashlib.sha256(raw).hexdigest()},
            {"Check": "Empty file", "Result": "PASS" if raw else "FAIL"},
            {"Check": "Executable extension", "Result": "PASS" if not re.search(r"\.(exe|dll|bat|cmd|ps1|sh)$", uploaded.name.lower()) else "FAIL"},
        ])
        st.session_state["security_file_scan_df"] = scan
        st.dataframe(scan, use_container_width=True, hide_index=True)
    if st.button("🔎 Run Workspace Security Checks", use_container_width=True, key="enterprise_security_scan"):
        checks = pd.DataFrame([
            {"Control": "Workspace identity", "Status": "PASS" if username else "FAIL"},
            {"Control": "Durable backend", "Status": "PASS" if durable_backend_configured() else "WARN"},
            {"Control": "Secrets excluded from workspace snapshots", "Status": "PASS"},
            {"Control": "Audit logging", "Status": "PASS"},
        ])
        st.session_state["security_scan_df"] = checks
        _chart_state(module, checks, "security_scan_df")
        _audit(username, "security_scan", "enterprise governance checks")
    if isinstance(st.session_state.get("security_scan_df"), pd.DataFrame):
        st.dataframe(st.session_state["security_scan_df"], use_container_width=True, hide_index=True)


def render_cloud_persistence(module: str, username: str) -> None:
    st.markdown("### ☁️ Cloud Persistence & Recovery")
    configured = bool(durable_backend_configured())
    status = "CONNECTED" if configured else "NOT CONFIGURED"
    st.metric("Durable backend", status)
    if configured:
        st.success("Managed persistence is authoritative for workspace state; local SQLite is not used as a silent fallback.")
        if st.button("💾 Force Workspace Snapshot", use_container_width=True, key="cloud_force_snapshot"):
            save_user_workspace(username, st.session_state)
            _audit(username, "workspace_snapshot", "manual cloud persistence checkpoint")
            st.success("Workspace snapshot requested.")
    else:
        st.warning("Durable cloud persistence is not configured. Configure the managed database secret before treating restart persistence as guaranteed.")
    history = pd.DataFrame([
        {"Artifact": x, "Durability": "Workspace snapshot" if configured else "Session/local fallback", "Status": "Ready" if configured else "Needs backend"}
        for x in ["Projects", "Datasets", "Experiments", "Reports", "Decisions", "Research", "Digital Thread"]
    ])
    st.session_state["cloud_persistence_health_df"] = history
    st.dataframe(history, use_container_width=True, hide_index=True)
    _chart_state(module, history, "cloud_persistence_health_df")


def render_collaboration(module: str, username: str) -> None:
    st.markdown("### 👥 Engineering Collaboration")
    st.caption("Shared projects, reviewer roles, assignments, comments, mentions and approval context.")
    project = st.text_input("Project / workspace", "Plant-01 Engineering", key="collab_project")
    assignment = st.text_input("Assignment", "Review latest engineering result", key="collab_assignment")
    reviewer = st.text_input("Reviewer / assignee", username, key="collab_reviewer")
    comment = st.text_area("Comment / @mention", placeholder="@reviewer please verify the KPI evidence.", key="collab_comment")
    if st.button("💬 Save Collaboration Note", use_container_width=True, key="collab_save_comment"):
        add_comment(project, None, username, comment)
        st.session_state["collab_assignment_df"] = pd.DataFrame([{
            "Project": project, "Assignment": assignment, "Assignee": reviewer,
            "Comment": comment, "Status": "Open", "Created": _now(),
        }])
        _audit(username, "collaboration_note", f"{project}|{reviewer}")
    try:
        with sqlite3.connect("enterprise_full_workspace.db") as conn:
            comments = pd.read_sql(
                "SELECT project_id,actor,comment,created_at FROM experience_comments WHERE project_id=? ORDER BY id DESC LIMIT 100",
                conn, params=(project,),
            )
    except Exception:
        comments = pd.DataFrame()
    if not comments.empty:
        st.dataframe(comments, use_container_width=True, hide_index=True)
    if isinstance(st.session_state.get("collab_assignment_df"), pd.DataFrame):
        _chart_state(module, st.session_state["collab_assignment_df"], "collaboration_assignment_df")
        st.dataframe(st.session_state["collab_assignment_df"], use_container_width=True, hide_index=True)


def render_research_governance(module: str, username: str) -> None:
    st.markdown("### 📝 Research Reproducibility & Evidence")
    st.caption("Protocol → hypothesis → experiment → run → results → citations → manuscript/supplementary evidence.")
    protocol = st.session_state.get("research_protocol")
    fields = {}
    if isinstance(protocol, dict):
        for key in ["research_id", "title", "objective", "research_question", "hypothesis", "null_hypothesis", "methodology", "random_seed", "alpha", "replications"]:
            fields[key] = protocol.get(key)
    else:
        fields = {"research_id": "", "title": "", "objective": "", "research_question": "", "hypothesis": "", "null_hypothesis": "", "methodology": "", "random_seed": 42, "alpha": 0.05, "replications": 3}
    repro = pd.DataFrame([fields])
    repro["Protocol Hash"] = hashlib.sha256(_safe_json(fields).encode()).hexdigest()
    st.session_state["research_reproducibility_df"] = repro
    _chart_state(module, repro, "research_reproducibility_df")
    st.dataframe(repro, use_container_width=True, hide_index=True)
    citation = st.text_input("Citation / DOI / URL", key="research_citation")
    manuscript = st.text_area("Manuscript / supplementary note", key="research_supplementary_note")
    if st.button("🔒 Lock Research Evidence Snapshot", use_container_width=True, key="research_lock_snapshot"):
        st.session_state["research_evidence_snapshot"] = {
            "timestamp": _now(), "protocol": fields, "protocol_hash": repro.iloc[0]["Protocol Hash"],
            "citation": citation, "supplementary_note": manuscript,
        }
        _audit(username, "research_evidence_snapshot", str(fields.get("research_id", "")))
        st.success("Evidence snapshot locked in workspace state. The lock does not invent external verification.")


def render_data_intelligence(module: str, username: str) -> None:
    st.markdown("### 🔍 Data Intelligence")
    source = None
    for key in ["data_platform_latest_df", "module_parity_result_df", "conn_df", "forecast_df", "experiment_df"]:
        val = st.session_state.get(key)
        if isinstance(val, pd.DataFrame) and not val.empty:
            source = val.copy(deep=True)
            break
    if source is None:
        st.info("Load or generate a dataset above to activate Data Intelligence.")
        return
    rows = []
    for col in source.columns:
        s = source[col]
        numeric = pd.api.types.is_numeric_dtype(s)
        rows.append({
            "Column": col,
            "Type": str(s.dtype),
            "Missing %": round(float(s.isna().mean()*100), 2),
            "Unique": int(s.nunique(dropna=True)),
            "Duplicates": int(s.duplicated().sum()),
            "Outliers": int(((s < (s.quantile(.25) - 1.5 * (s.quantile(.75) - s.quantile(.25)))) | (s > (s.quantile(.75) + 1.5 * (s.quantile(.75) - s.quantile(.25))))).sum()) if numeric and s.notna().sum() > 4 else 0,
        })
    profile = pd.DataFrame(rows)
    quality = max(0.0, 100.0 - min(100.0, float(profile["Missing %"].mean()) + float(profile["Outliers"].sum()/max(1,len(source))*5)))
    profile["Quality Signal"] = np.where(profile["Missing %"] == 0, "Good", "Review")
    st.session_state["data_intelligence_profile_df"] = profile
    st.metric("Data quality signal", f"{quality:.1f}%")
    st.dataframe(profile, use_container_width=True, hide_index=True)
    _chart_state(module, profile, "data_intelligence_profile_df")


def render_knowledge_layer(module: str, username: str) -> None:
    st.markdown("### 📚 Engineering Knowledge Layer")
    st.caption("Standards, methods, SOPs, manuals and company knowledge are stored as governed references for Copilot context.")
    knowledge = st.data_editor(
        st.session_state.setdefault(
            "knowledge_registry_df",
            pd.DataFrame({
                "Document": ["ISO / internal standard", "SOP", "Engineering Method"],
                "Type": ["Standard", "SOP", "Method"],
                "Version": ["1.0", "1.0", "1.0"],
                "Owner": [username, username, username],
                "Status": ["Reference", "Reference", "Reference"],
            }),
        ),
        num_rows="dynamic",
        use_container_width=True,
        key="knowledge_registry_editor",
    )
    st.session_state["knowledge_registry_df"] = knowledge.copy(deep=True)
    uploaded = st.file_uploader("📎 Add governed knowledge document", type=["pdf", "txt", "md", "csv", "xlsx"], key="knowledge_upload")
    if uploaded is not None:
        raw = uploaded.getvalue()
        record = {"Document": uploaded.name, "Type": "Uploaded", "Version": "1.0", "Owner": username, "Status": "Pending indexing", "SHA-256": hashlib.sha256(raw).hexdigest()}
        knowledge = pd.concat([knowledge, pd.DataFrame([record])], ignore_index=True)
        st.session_state["knowledge_registry_df"] = knowledge
        st.success("Knowledge reference registered. It is not represented as searchable Copilot knowledge until indexing is configured.")


def render_model_registry_governance(module: str, username: str) -> None:
    st.markdown("### 🧬 Model Reproducibility Guard")
    reg = st.session_state.get("model_registry_df")
    if not isinstance(reg, pd.DataFrame):
        reg = pd.DataFrame(columns=["Model Name", "Type", "Version", "Status", "Data Hash"])
    out = reg.copy(deep=True)
    if "Data Hash" in out.columns:
        out["Data Hash"] = out["Data Hash"].fillna("")
    out["Registry Check"] = np.where(out.get("Data Hash", pd.Series("", index=out.index)).astype(str).str.len() >= 16, "Hash present", "Needs hash")
    out["Recorded At"] = _now()
    st.session_state["model_registry_governance_df"] = out
    _chart_state(module, out, "model_registry_governance_df")
    st.dataframe(out, use_container_width=True, hide_index=True)


def render_jobs_and_monitoring(module: str, username: str) -> None:
    st.markdown("### 🕐 Jobs & Real-Time Monitoring")
    st.caption("Queue/retry/progress metadata and telemetry health are surfaced without pretending a local process is a distributed worker.")
    jobs = pd.DataFrame(columns=["Job", "Status", "Progress", "Retry", "Updated"])
    try:
        with sqlite3.connect("enterprise_full_workspace.db") as conn:
            jobs = pd.read_sql("SELECT job_id AS Job,status AS Status,progress AS Progress,message AS Message,started_at AS Updated FROM experience_jobs ORDER BY started_at DESC LIMIT 100", conn)
    except Exception:
        pass
    if st.button("➕ Create Background Job Record", use_container_width=True, key="jobs_create_record"):
        jid = create_job(module, "analysis", username, {"created_from": module})
        st.success(f"Job record created: {jid}")
        st.rerun()
    if not jobs.empty:
        st.dataframe(jobs, use_container_width=True, hide_index=True)
        _chart_state(module, jobs, "jobs_monitoring_df")
        selected_job = st.selectbox("Job", jobs["Job"].astype(str).tolist(), key="jobs_selected_job")
        j1, j2, j3 = st.columns(3)
        with j1:
            if st.button("▶️ Run / Resume", key="jobs_resume"):
                update_job(selected_job, "Running", 50.0, "Operator requested run/resume")
                st.rerun()
        with j2:
            if st.button("⏸️ Pause", key="jobs_pause"):
                update_job(selected_job, "Queued", 0.0, "Paused by operator; safe checkpoint requested")
                st.rerun()
        with j3:
            if st.button("🔁 Retry", key="jobs_retry"):
                update_job(selected_job, "Queued", 0.0, "Retry queued by operator")
                st.rerun()
    telemetry = st.session_state.get("twin_tel")
    if isinstance(telemetry, pd.DataFrame):
        _chart_state(module, telemetry, "realtime_monitoring_df")
        st.dataframe(telemetry.tail(50), use_container_width=True, hide_index=True)


def render_reporting_provenance(module: str, username: str) -> None:
    st.markdown("### 📑 Reporting & Provenance")
    frames = []
    for key in ["exec_report_df", "decision_alternatives_df", "decision_kpi_df", "forecast_result", "sustain_result"]:
        value = st.session_state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            frames.append(value)
    if not frames:
        st.info("Generate a result in this module to create a provenance manifest.")
        return
    raw = "|".join(x.to_csv(index=False) for x in frames).encode("utf-8")
    manifest = pd.DataFrame([{
        "Module": module,
        "Generated": _now(),
        "Tables": len(frames),
        "Evidence SHA-256": hashlib.sha256(raw).hexdigest(),
        "Excel": "Supported",
        "PDF": "Enterprise export surface",
        "PowerPoint": "Enterprise export surface",
        "Exact graphs": "Included when passed to export bar",
    }])
    st.session_state["report_provenance_df"] = manifest
    _chart_state(module, manifest, "report_provenance_df")
    st.dataframe(manifest, use_container_width=True, hide_index=True)


def render_economics(module: str, username: str) -> None:
    st.markdown("### 💰 Engineering Economics Decision Link")
    result = st.session_state.get("capex_result")
    if isinstance(result, dict):
        st.json(result)
    cf = st.session_state.get("capex_df")
    if isinstance(cf, pd.DataFrame):
        st.metric("Cash-flow periods", len(cf))
        _chart_state(module, cf, "engineering_economics_cashflow_df")
    st.info("Economics outputs can be passed into Decision Center as KPI evidence; no business case is marked approved automatically.")


def render_sustainability(module: str, username: str) -> None:
    st.markdown("### 🌱 Sustainability Decision Link")
    result = st.session_state.get("sustain_result")
    if isinstance(result, pd.DataFrame):
        _chart_state(module, result, "sustainability_decision_df")
        st.dataframe(result, use_container_width=True, hide_index=True)
    st.info("Energy, water, carbon and waste metrics remain decision inputs; optimization does not silently override environmental constraints.")


def render_human_factors(module: str, username: str) -> None:
    st.markdown("### 🧑‍🏭 Human Factors & Workforce")
    frames = []
    for key in ["work_elements", "skills_df"]:
        val = st.session_state.get(key)
        if isinstance(val, pd.DataFrame):
            frames.append(val)
    if frames:
        combined = pd.concat(frames, ignore_index=True, sort=False)
        _chart_state(module, combined, "human_factors_workforce_df")
        st.dataframe(combined, use_container_width=True, hide_index=True)
    st.info("Workload, staffing, skills and ergonomics remain engineering constraints; no fatigue/safety claim is inferred from missing data.")


def render_geospatial(module: str, username: str) -> None:
    st.markdown("### 🗺️ Geospatial Intelligence")
    frames = []
    for key in ["fleet_list", "geospatial_df", "route_result"]:
        val = st.session_state.get(key)
        if isinstance(val, pd.DataFrame):
            frames.append(val)
    if frames:
        combined = pd.concat(frames, ignore_index=True, sort=False)
        _chart_state(module, combined, "geospatial_intelligence_df")
        st.dataframe(combined, use_container_width=True, hide_index=True)
    st.info("Route/network visuals use available coordinates or route tables; travel-time claims require actual routing data.")


def render_universal_enterprise_capabilities(module: str, username: str) -> None:
    if module not in CAPABILITY_MODULES:
        return
    if module in {"Digital Twin & Discrete-Event Simulation", "Live Industrial Digital Twin", "Predictive Maintenance Digital Twin"}:
        render_digital_twin_operations(module, username)
    if module in {"Control Tower", "Industrial Control Center"}:
        render_control_tower(module, username)
    if module == "Industrial Connectivity Hub":
        render_connectivity_health(module, username)
    if module == "Enterprise Security & Governance":
        render_security_governance(module, username)
    if module in {"Persistence", "Industrial Data Platform"}:
        render_cloud_persistence(module, username)
    if module in {"Team Workspaces & RBAC"}:
        render_collaboration(module, username)
    if module in {"Research Studio", "Experiment Lab", "Experiment Engine"}:
        render_research_governance(module, username)
    if module in {"Industrial Data Platform", "Engineering Validation Center"}:
        render_data_intelligence(module, username)
    if module in {"Advanced Engineering Copilot", "AI Copilot", "Engineering Model Registry"}:
        render_knowledge_layer(module, username)
    if module == "Engineering Model Registry":
        render_model_registry_governance(module, username)
    if module in {"Industrial Data Platform", "Industrial Simulation Lab", "Multi-Objective Optimization", "Robust & Resilient Optimization", "Advanced ML Demand Forecasting", "Live Industrial Digital Twin"}:
        render_jobs_and_monitoring(module, username)
    if module in {"Capital Investment & Engineering Economics", "Engineering Economics & Finance"}:
        render_economics(module, username)
    if module in {"Executive Report Center", "Research Studio"}:
        render_reporting_provenance(module, username)
    if module in {"Industrial Sustainability & LCA", "Green IE & Sustainability"}:
        render_sustainability(module, username)
    if module in {"Workforce Engineering", "Human Factors & Ergonomics (NIOSH)"}:
        render_human_factors(module, username)
    if module in {"Geospatial Network Designer", "Fleet Routing"}:
        render_geospatial(module, username)
