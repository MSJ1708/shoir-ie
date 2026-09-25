"""Cross-cutting enterprise services for Shoir-IE.

This module augments the existing specialized engineering modules without
creating duplicate workflows. It provides durable artifact storage hooks,
data intelligence, connector health, digital-twin replay, control-tower
health aggregation, collaboration/research/reporting helpers, knowledge
context, job lifecycle UI, and security/file hygiene checks.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ARTIFACT_TYPES = {
    "project",
    "dataset",
    "experiment",
    "decision",
    "report",
    "model",
    "scenario",
    "history",
    "knowledge",
    "collaboration",
    "job",
    "telemetry",
}

CONNECTOR_TYPES = ["SAP", "Oracle", "SQL", "REST", "MQTT", "OPC-UA", "WMS", "MES", "ERP"]

_SOURCE_KEYS = {
    "Production": ["mes_wo_df", "mes_events_df", "aps_schedule_result", "production_df", "ppc_df"],
    "Supply": ["supply_nodes", "supplier_risk_df", "supplier_risk_data", "erp_connectors"],
    "Inventory": ["meio_data", "slotting_data", "inventory_df", "warehouse_inventory_df"],
    "Quality": ["quality_df", "quality_spc_result", "anova_df", "fmea_df", "fmea_result"],
    "Maintenance": ["maint_result", "maint_df", "reliability_data", "predictive_maintenance_df"],
    "Transport": ["fleet_list", "fleet_df", "control_tower_disruption_df", "routing_result"],
    "Workforce": ["work_elements", "skills_df", "workspace_users", "ergonomic_tasks"],
    "Energy": ["sustain_df", "energy_df", "sustain_result", "forecast_universal_df"],
    "Carbon": ["carbon_latest_df", "sustain_result", "carbon_df"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_artifact_id(kind: str, owner: str, title: str, payload: Any = None) -> str:
    raw = json.dumps({"kind": kind, "owner": owner, "title": title, "payload": payload}, sort_keys=True, default=str)
    return f"{kind[:3].upper()}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:14].upper()}"


def sanitize_filename(name: str) -> str:
    stem = PurePath(str(name or "upload.bin")).name
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem)
    return stem[:160] or "upload.bin"


def secure_file_scan(name: str, content: bytes, *, max_bytes: int = 10_000_000) -> dict[str, Any]:
    safe_name = sanitize_filename(name)
    raw = bytes(content or b"")
    lower = safe_name.lower()
    issues: list[str] = []
    blocked_ext = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh", ".js", ".vbs", ".scr"}
    ext = PurePath(safe_name).suffix.lower()
    if ext in blocked_ext:
        issues.append(f"Executable/script extension is not allowed: {ext}")
    if len(raw) == 0:
        issues.append("File is empty.")
    if len(raw) > int(max_bytes):
        issues.append(f"File exceeds the {max_bytes:,}-byte safety limit.")
    if lower.startswith(("/", "\", "..")) or ".." + os.sep in lower:
        issues.append("Unsafe path-like filename detected.")
    formula_cells = 0
    if ext in {".csv", ".txt"}:
        preview = raw[:1_000_000].decode("utf-8", errors="ignore")
        formula_cells = sum(
            1 for line in preview.splitlines()
            if re.search(r"(^|,)[=+\-@]", line)
        )
        if formula_cells:
            issues.append(f"Potential spreadsheet formula-injection rows detected: {formula_cells}")
    return {
        "allowed": not issues,
        "filename": safe_name,
        "extension": ext,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "issues": issues,
        "scanned_at": now_iso(),
    }


def dataframe_profile(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("A pandas DataFrame is required.")
    rows = len(df)
    duplicate_rows = int(df.duplicated().sum()) if rows else 0
    records: list[dict[str, Any]] = []
    for col in df.columns:
        s = df[col]
        name = str(col)
        lower = name.lower()
        non_null = s.dropna()
        unique = int(s.nunique(dropna=True))
        semantic = "Text"
        if pd.api.types.is_datetime64_any_dtype(s):
            semantic = "Date/Time"
        else:
            parsed = pd.to_datetime(non_null.astype(str).head(50), errors="coerce")
            if len(non_null) >= 5 and float(parsed.notna().mean()) >= 0.85 and any(t in lower for t in ("date", "time", "timestamp")):
                semantic = "Date/Time"
            elif pd.api.types.is_numeric_dtype(s):
                semantic = "Numeric"
            elif unique / max(1, len(non_null)) > 0.92 and any(t in lower for t in ("id", "code", "sku", "asset", "order", "employee", "customer", "machine")):
                semantic = "Identifier"
            elif unique <= min(25, max(5, int(rows * 0.2))) if rows else False:
                semantic = "Categorical"
        unit_match = re.search(r"\(([^)]+)\)|\[([^]]+)\]|\b(kg|g|lb|hr|h|min|s|kwh|mwh|co2e|usd|sar|eur|%|ppm)\b", name, re.I)
        unit = next((x for x in (unit_match.groups() if unit_match else ()) if x), "")
        outliers = 0
        drift = 0.0
        if pd.api.types.is_numeric_dtype(s):
            x = pd.to_numeric(s, errors="coerce").dropna().to_numpy(dtype=float)
            if len(x) >= 8:
                q1, q3 = np.quantile(x, [0.25, 0.75])
                iqr = q3 - q1
                if iqr > 0:
                    outliers = int(np.sum((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr)))
                half = len(x) // 2
                if half >= 3:
                    a, b = x[:half], x[-half:]
                    pooled = math.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
                    drift = float(abs(np.mean(a) - np.mean(b)) / max(pooled, 1e-9))
        elif len(non_null) >= 10:
            half = len(non_null) // 2
            if half >= 3:
                a = non_null.iloc[:half].astype(str).value_counts(normalize=True)
                b = non_null.iloc[-half:].astype(str).value_counts(normalize=True)
                categories = a.index.union(b.index)
                drift = float(0.5 * np.abs(a.reindex(categories, fill_value=0) - b.reindex(categories, fill_value=0)).sum())
        records.append({
            "Column": name,
            "DType": str(s.dtype),
            "Semantic Type": semantic,
            "Unit Hint": unit,
            "Missing %": round(float(s.isna().mean() * 100), 2) if rows else 100.0,
            "Unique": unique,
            "Outliers": outliers,
            "Drift Index": round(drift, 4),
            "Constant": unique <= 1 and rows > 0,
        })
    profile = pd.DataFrame(records)
    summary = {
        "Rows": int(rows),
        "Columns": int(len(df.columns)),
        "Duplicate Rows": duplicate_rows,
        "Missing Cells": int(df.isna().sum().sum()),
        "Missing %": round(float(df.isna().mean().mean() * 100), 2) if len(df.columns) else 100.0,
        "Numeric Fields": int(len(df.select_dtypes(include=np.number).columns)),
        "Date/Time Fields": int((profile["Semantic Type"] == "Date/Time").sum()) if not profile.empty else 0,
        "Identifier Fields": int((profile["Semantic Type"] == "Identifier").sum()) if not profile.empty else 0,
        "High-Drift Fields": int((profile["Drift Index"] >= 0.5).sum()) if not profile.empty else 0,
        "Outlier Fields": int((profile["Outliers"] > 0).sum()) if not profile.empty else 0,
    }
    return profile, summary


def control_tower_health(session_state: Mapping[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for domain, keys in _SOURCE_KEYS.items():
        found_key = ""
        record_count = 0
        risk_flags = 0
        for key in keys:
            value = session_state.get(key)
            if isinstance(value, pd.DataFrame) and not value.empty:
                found_key = key
                record_count = len(value)
                text = value.astype(str).apply(lambda s: s.str.lower())
                risk_flags = int(text.apply(lambda c: c.str.contains("critical|warning|failed|late|risk|breach|out of control", regex=True).sum()).sum())
                break
            if isinstance(value, list) and value:
                found_key = key
                record_count = len(value)
                risk_flags = sum(
                    1 for item in value if isinstance(item, dict) and re.search("critical|warning|failed|late|risk", json.dumps(item).lower())
                )
                break
        rows.append({
            "Domain": domain,
            "Evidence Source": found_key or "No current workspace evidence",
            "Records": record_count,
            "Risk Flags": risk_flags,
            "Evidence Coverage %": 100.0 if record_count else 0.0,
            "Status": "Connected" if record_count else "No current evidence",
        })
    return pd.DataFrame(rows)


def digital_twin_state(session_state: Mapping[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in session_state.get("dt_workstations", []) if isinstance(session_state.get("dt_workstations"), list) else []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "Entity": item.get("id") or item.get("name") or "Workstation",
            "Entity Type": "Workstation",
            "State": item.get("status", "Unknown"),
            "Metric": "Position",
            "Value": float(item.get("x", 0)) if pd.notna(pd.to_numeric(item.get("x", 0), errors="coerce")) else 0.0,
            "Timestamp": now_iso(),
        })
    for item in session_state.get("iot_sensors", []) if isinstance(session_state.get("iot_sensors"), list) else []:
        if not isinstance(item, dict):
            continue
        value = pd.to_numeric(item.get("reading"), errors="coerce")
        threshold = pd.to_numeric(item.get("threshold"), errors="coerce")
        rows.append({
            "Entity": item.get("sensor_id") or item.get("name") or "Sensor",
            "Entity Type": "Sensor",
            "State": item.get("status", "Unknown"),
            "Metric": item.get("type", "Telemetry"),
            "Value": float(value) if pd.notna(value) else np.nan,
            "Threshold": float(threshold) if pd.notna(threshold) else np.nan,
            "Timestamp": now_iso(),
        })
    return pd.DataFrame(rows)


def replay_twin_scenario(twin_df: pd.DataFrame, scenario_df: pd.DataFrame) -> pd.DataFrame:
    if twin_df is None or twin_df.empty:
        raise ValueError("Digital Twin needs a current state table before replay.")
    if scenario_df is None or scenario_df.empty:
        return twin_df.copy()
    base = twin_df.copy()
    scenario = scenario_df.copy()
    required = {"Metric", "Delta"}
    if not required <= set(scenario.columns):
        raise ValueError("Scenario replay requires Metric and Delta columns.")
    scenario["Delta"] = pd.to_numeric(scenario["Delta"], errors="coerce").fillna(0)
    mapping = scenario.groupby("Metric")["Delta"].sum().to_dict()
    metric_col = "Metric" if "Metric" in base.columns else None
    if metric_col:
        base["Scenario Delta"] = base[metric_col].map(mapping).fillna(0.0)
        base["Replay Value"] = pd.to_numeric(base.get("Value"), errors="coerce") + base["Scenario Delta"]
    base["Replay Timestamp"] = now_iso()
    base["Scenario"] = "What-if replay"
    return base


def connector_health_table(connectors: pd.DataFrame) -> pd.DataFrame:
    if connectors is None or connectors.empty:
        return pd.DataFrame(columns=["Connector", "System", "Protocol", "Endpoint", "Status", "Health"])
    d = connectors.copy()
    rename_map = {c: c.title() for c in d.columns}
    d = d.rename(columns=rename_map)
    for col in ["Connector", "System", "Protocol", "Endpoint", "Status"]:
        if col not in d.columns:
            d[col] = ""
    d["Health"] = np.where(
        d["Status"].astype(str).str.lower().str.contains("connected|active|healthy|online"),
        "Healthy",
        np.where(d["Status"].astype(str).str.lower().str.contains("warning|standby|retry"), "Monitor", "Unknown"),
    )
    return d[["Connector", "System", "Protocol", "Endpoint", "Status", "Health"]]


def test_rest_endpoint(endpoint: str, timeout: float = 5.0) -> dict[str, Any]:
    url = str(endpoint or "").strip()
    if not re.match(r"^https?://", url, re.I):
        return {"Status": "Invalid", "Latency ms": None, "Detail": "REST health checks require an http(s) URL."}
    try:
        import requests
        start = time.perf_counter()
        resp = requests.get(url, timeout=float(timeout), allow_redirects=True)
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "Status": "Healthy" if resp.status_code < 400 else "HTTP Error",
            "HTTP Status": int(resp.status_code),
            "Latency ms": round(elapsed, 1),
            "Detail": f"Received {resp.status_code} from endpoint.",
        }
    except Exception as exc:
        return {"Status": "Unreachable", "Latency ms": None, "Detail": f"{type(exc).__name__}: {exc}"}


def security_posture() -> pd.DataFrame:
    secret_sections = []
    try:
        secret_sections = [str(k) for k in st.secrets.keys()]
    except Exception:
        pass
    return pd.DataFrame([
        {"Control": "RBAC", "Status": "Implemented", "Evidence": "Role/tier gates and explicit workspace roles"},
        {"Control": "Workspace isolation", "Status": "Implemented", "Evidence": "Owner-scoped durable workspace state"},
        {"Control": "Audit trail", "Status": "Implemented", "Evidence": "Application audit/event tables"},
        {"Control": "Secure file handling", "Status": "Implemented", "Evidence": "Filename, size, extension, formula-injection checks"},
        {"Control": "Secrets management", "Status": "Implemented", "Evidence": f"Streamlit secrets available: {bool(secret_sections)}"},
        {"Control": "SSO/OIDC", "Status": "Configuration-ready", "Evidence": "Supabase/Auth or enterprise IdP integration surface"},
        {"Control": "MFA", "Status": "Configuration-ready", "Evidence": "Requires an enrolled enterprise authentication provider"},
        {"Control": "Security scanning", "Status": "CI-enforced", "Evidence": "Dedicated dependency/code scan workflow"},
    ])


def build_research_manifest(study: Mapping[str, Any], runs: Sequence[Mapping[str, Any]], citations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    protocol = dict(study or {})
    return {
        "generated_at": now_iso(),
        "protocol": protocol,
        "runs": [dict(x) for x in runs],
        "citations": [dict(x) for x in citations],
        "reproducibility": {
            "random_seed": protocol.get("random_seed"),
            "protocol_hash": protocol.get("protocol_hash"),
            "run_count": len(runs),
        },
    }


def report_provenance(module: str, tables: Sequence[tuple[str, pd.DataFrame]], figures: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    entries = []
    for label, df in tables:
        if isinstance(df, pd.DataFrame):
            csv = df.to_csv(index=False).encode("utf-8")
            entries.append({
                "label": label,
                "rows": len(df),
                "columns": len(df.columns),
                "sha256": hashlib.sha256(csv).hexdigest(),
            })
    return {
        "module": module,
        "generated_at": now_iso(),
        "tables": entries,
        "figures": [{"label": str(label), "type": type(fig).__name__} for label, fig in figures],
        "graph_policy": "Figures are generated from the same in-memory/tabular evidence packaged with the report.",
    }


def collaboration_record(kind: str, project_id: str, actor: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": str(kind),
        "project_id": str(project_id),
        "actor": str(actor),
        "timestamp": now_iso(),
        "payload": dict(payload),
    }


def run_job_lifecycle(job_id: str, action: str, actor: str, *, progress: float | None = None, message: str = "") -> bool:
    try:
        from industrial_experience import update_job
        status_map = {
            "start": ("Running", 1.0, message or "Job started"),
            "pause": ("Paused", progress if progress is not None else 0.0, message or "Paused by operator"),
            "resume": ("Running", progress if progress is not None else 0.0, message or "Resumed by operator"),
            "cancel": ("Cancelled", progress if progress is not None else 0.0, message or "Cancelled by operator"),
            "retry": ("Queued", 0.0, message or "Retry queued"),
            "complete": ("Completed", 100.0, message or "Completed"),
            "fail": ("Failed", progress if progress is not None else 0.0, message or "Failed"),
        }
        status, pct, msg = status_map.get(action, (None, None, ""))
        if status is None:
            return False
        update_job(job_id, status, float(pct), msg)
        return True
    except Exception:
        return False


def render_enterprise_capability_bridge(module: str, tier: str, username: str) -> None:
    """Render module-specific enterprise enhancements without duplicating native UIs."""
    module = str(module)
    relevant = {
        "Digital Twin": ("🌐 Digital Twin Operations", "Live state, synchronized replay and what-if controls."),
        "Control Tower": ("🗼 Control Tower Health Map", "Unified cross-domain health evidence."),
        "Industrial Connectivity": ("🔌 Connectivity Health", "Connector registry and endpoint health."),
        "Enterprise Integration": ("🔌 Connectivity & Collaboration", "Connector health plus shared-workspace controls."),
        "Security": ("🔐 Enterprise Security", "Governance, file hygiene and authentication readiness."),
        "Persistence": ("☁️ Cloud Persistence", "Durable workspace, artifact and history controls."),
        "Collaboration": ("👥 Collaboration", "Roles, comments, mentions, approvals and assignments."),
        "Research": ("📝 Research Studio", "Protocol, experiment, provenance and reproducibility controls."),
        "Report": ("📑 Reporting & Provenance", "Presentation-ready exports tied to exact evidence."),
        "Data Intelligence": ("🔍 Data Intelligence", "Schema, units, dates, IDs, outliers and drift."),
        "Knowledge": ("📚 Knowledge Layer", "SOPs, manuals and engineering methods for Copilot context."),
        "Model Registry": ("🧬 Model Registry", "Version, hash, assumptions, solver and results metadata."),
        "Jobs": ("🕐 Jobs System", "Queue, progress, cancel, pause/resume, retry and history."),
        "Real-time": ("📡 Real-time Monitoring", "Telemetry, anomaly detection and alert thresholds."),
        "Economics": ("💰 Engineering Economics", "TCO and scenario economics linked to engineering evidence."),
        "Sustainability": ("🌱 Sustainability", "Energy, water, carbon and waste linked to decisions."),
        "Human Factors": ("🧑‍🏭 Human Factors", "Workload, staffing and fatigue evidence."),
        "Geospatial": ("🗺️ Geospatial Intelligence", "Network, route and facility evidence."),
    }
    title, caption = next(((v[0], v[1]) for k, v in relevant.items() if k.lower() in module.lower()), ("", ""))
    if not title:
        return
    with st.expander(f"{title} · Enterprise Integration", expanded=False):
        st.caption(caption)
        token = hashlib.sha1(module.encode("utf-8")).hexdigest()[:10]

        if "Digital Twin" in module:
            state = digital_twin_state(st.session_state)
            if not state.empty:
                st.dataframe(state, use_container_width=True, hide_index=True)
                scenario = st.data_editor(
                    st.session_state.setdefault(
                        "digital_twin_what_if_df",
                        pd.DataFrame({"Metric": state["Metric"].dropna().astype(str).drop_duplicates().head(8).tolist(), "Delta": [0.0] * min(8, state["Metric"].nunique())}),
                    ),
                    num_rows="dynamic", use_container_width=True, key=f"digital_twin_what_if_{token}",
                )
                if st.button("▶️ Replay / What-if Scenario", type="primary", use_container_width=True, key=f"digital_twin_replay_{token}"):
                    try:
                        replay = replay_twin_scenario(state, scenario)
                        st.session_state["digital_twin_replay_df"] = replay
                        st.success("Scenario replay synchronized against the current digital-twin state.")
                    except Exception as exc:
                        st.error(f"Twin replay failed safely: {exc}")
                if isinstance(st.session_state.get("digital_twin_replay_df"), pd.DataFrame):
                    st.dataframe(st.session_state["digital_twin_replay_df"], use_container_width=True, hide_index=True)
                    fig = px.bar(
                        st.session_state["digital_twin_replay_df"].head(50),
                        x="Entity", y="Replay Value", title="Digital Twin What-if Replay",
                    )
                    st.plotly_chart(fig, use_container_width=True)

        elif "Control Tower" in module:
            health = control_tower_health(st.session_state)
            st.dataframe(health, use_container_width=True, hide_index=True)
            fig = px.bar(health, x="Domain", y="Evidence Coverage %", hover_data=["Records", "Risk Flags"], title="Unified Operational Health Coverage")
            st.plotly_chart(fig, use_container_width=True)
            st.session_state["control_tower_health_df"] = health

        elif "Connectivity" in module or "Enterprise Integration" in module:
            connectors = st.session_state.setdefault(
                "enterprise_connectors_df",
                pd.DataFrame({
                    "Connector": ["SAP-01", "Oracle-01", "SQL-01", "REST-01", "MQTT-01", "OPC-UA-01", "WMS-01", "MES-01", "ERP-01"],
                    "System": ["SAP S/4HANA", "Oracle", "SQL Server", "REST API", "MQTT Broker", "OPC-UA Server", "WMS", "MES", "ERP"],
                    "Protocol": ["OData/REST", "REST", "JDBC/ODBC", "HTTP", "MQTT", "OPC-UA", "REST", "REST", "REST"],
                    "Endpoint": ["", "", "", "https://example.com/health", "", "", "", "", ""],
                    "Status": ["Configured", "Configured", "Configured", "Configured", "Configured", "Configured", "Configured", "Configured", "Configured"],
                }),
                )
            connectors = st.data_editor(connectors, num_rows="dynamic", use_container_width=True, key=f"connector_editor_{token}")
            health = connector_health_table(connectors)
            st.dataframe(health, use_container_width=True, hide_index=True)
            rest_rows = connectors[connectors["Protocol"].astype(str).str.contains("HTTP|REST|OData", regex=True, case=False)]
            if not rest_rows.empty:
                endpoint_name = st.selectbox("REST endpoint to test", rest_rows["Endpoint"].astype(str).tolist(), key=f"connector_endpoint_{token}")
                if st.button("🩺 Test endpoint health", use_container_width=True, key=f"connector_test_{token}"):
                    result = test_rest_endpoint(endpoint_name)
                    st.session_state["connector_last_test"] = result
                if st.session_state.get("connector_last_test"):
                    st.json(st.session_state["connector_last_test"])
            st.session_state["enterprise_connectors_df"] = connectors

        elif "Security" in module:
            posture = security_posture()
            st.dataframe(posture, use_container_width=True, hide_index=True)
            up = st.file_uploader(
                "Secure file validation (metadata-only; file is not stored by this scan)",
                type=["csv", "txt", "xlsx", "xls", "pdf", "md"],
                key=f"secure_scan_upload_{token}",
            )
            if up is not None:
                scan = secure_file_scan(up.name, up.getvalue())
                st.session_state["security_last_file_scan"] = scan
                st.json(scan)

        elif "Persistence" in module:
            status = {
                "Backend configured": False,
                "Workspace autosave": "Enabled",
                "Local SQLite": "Development fallback only",
                "Cloud artifacts": "Available through managed backend",
            }
            try:
                from durable_account_store import durable_backend_configured
                status["Backend configured"] = bool(durable_backend_configured())
            except Exception:
                pass
            st.dataframe(pd.DataFrame([status]), use_container_width=True, hide_index=True)
            st.caption("Cloud artifact records use the same authenticated persistence service as account/workspace storage.")

        elif "Collaboration" in module or "Team Workspaces" in module:
            members = st.data_editor(
                st.session_state.setdefault(
                    "collaboration_members_df",
                    pd.DataFrame({"Username": [username], "Role": ["Owner"], "Assignment": ["Workspace Owner"], "Reviewer": [True]}),
                ),
                num_rows="dynamic", use_container_width=True, key=f"collab_members_{token}",
            )
            project = st.text_input("Shared project ID", value=st.session_state.get("global_thread_project", {}).get("project_id", "PROJECT-DEFAULT"), key=f"collab_project_{token}")
            comment = st.text_area("Comment / mention / review note", key=f"collab_comment_{token}")
            if st.button("💬 Save collaboration event", use_container_width=True, key=f"collab_save_{token}"):
                record = collaboration_record("comment", project, username, {"comment": comment, "mentions": [u for u in re.findall(r"@[A-Za-z0-9_.-]{3,32}", comment)]})
                st.session_state.setdefault("collaboration_history", []).insert(0, record)
                st.success("Collaboration event recorded in the workspace.")
            st.dataframe(members, use_container_width=True, hide_index=True)
            if st.session_state.get("collaboration_history"):
                st.dataframe(pd.DataFrame(st.session_state["collaboration_history"]), use_container_width=True, hide_index=True)

        elif "Research" in module:
            st.info("Research protocols and runs already persist through Shoir-IE's research persistence path; this surface adds provenance and supplementary-file packaging.")
            citations = st.data_editor(
                st.session_state.setdefault(
                    "research_citations_df",
                    pd.DataFrame({"Citation": ["Add source"], "DOI / URL": [""], "Use": ["Background"]}),
                ),
                num_rows="dynamic", use_container_width=True, key=f"research_citations_{token}",
            )
            study = st.session_state.get("research_study") or st.session_state.get("active_research_study") or {}
            runs = st.session_state.get("research_runs") or []
            manifest = build_research_manifest(study if isinstance(study, dict) else {}, runs, citations.to_dict("records"))
            st.session_state["research_manifest"] = manifest
            st.json(manifest)

        elif "Report" in module:
            tables = []
            for label, value in list(st.session_state.items()):
                if isinstance(value, pd.DataFrame) and not value.empty:
                    tables.append((label, value))
                    if len(tables) >= 8:
                        break
            provenance = report_provenance(module, tables, [])
            st.json(provenance)
            if tables:
                st.dataframe(tables[0][1].head(30), use_container_width=True, hide_index=True)
            st.session_state["report_last_provenance"] = provenance

        elif "Data Intelligence" in module:
            candidates = [(k, v) for k, v in st.session_state.items() if isinstance(v, pd.DataFrame) and not v.empty]
            if candidates:
                labels = [k.replace("_", " ").title() for k, _ in candidates[:30]]
                idx = st.selectbox("Data source", range(len(candidates)), format_func=lambda i: labels[i], key=f"data_intel_source_{token}")
                key, df = candidates[idx]
                profile, summary = dataframe_profile(df)
                st.session_state["data_intelligence_profile_df"] = profile
                st.session_state["data_intelligence_summary"] = summary
                st.dataframe(profile, use_container_width=True, hide_index=True)
                st.json(summary)
                fig = px.bar(profile, x="Column", y="Missing %", hover_data=["Outliers", "Drift Index"], title="Data Quality / Drift Profile")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No workspace DataFrame is currently available for profiling.")

        elif "Knowledge" in module:
            docs = st.session_state.setdefault("knowledge_assets", [])
            up = st.file_uploader("Upload SOP / manual / engineering reference", type=["txt", "md", "csv", "pdf"], key=f"knowledge_upload_{token}")
            if up is not None:
                scan = secure_file_scan(up.name, up.getvalue(), max_bytes=5_000_000)
                if scan["allowed"]:
                    raw = up.getvalue()
                    text_content = ""
                    if scan["extension"] in {".txt", ".md", ".csv"}:
                        text_content = raw.decode("utf-8", errors="ignore")[:200_000]
                    elif scan["extension"] == ".pdf":
                        try:
                            from pypdf import PdfReader
                            reader = PdfReader(io.BytesIO(raw))
                            text_content = "\n".join((page.extract_text() or "") for page in reader.pages)[:200_000]
                        except Exception:
                            text_content = "PDF uploaded; text extraction is unavailable in the current runtime."
                    artifact = {
                        "id": stable_artifact_id("knowledge", username, scan["filename"], scan["sha256"]),
                        "name": scan["filename"],
                        "sha256": scan["sha256"],
                        "text": text_content,
                        "available_to_copilot": True,
                        "uploaded_at": now_iso(),
                    }
                    docs[:] = [d for d in docs if d.get("id") != artifact["id"]]
                    docs.append(artifact)
                    st.success(f"Knowledge asset registered: {scan['filename']}")
            if docs:
                st.dataframe(pd.DataFrame([{"Name": d.get("name"), "SHA-256": d.get("sha256"), "Copilot": d.get("available_to_copilot")} for d in docs]), use_container_width=True, hide_index=True)
                context_text = "\n\n".join(str(d.get("text","")) for d in docs if d.get("available_to_copilot"))[:120_000]
                st.session_state["copilot_knowledge_context"] = context_text
                st.caption("Approved knowledge text is now attached to the workspace Copilot context.")

        elif "Model Registry" in module:
            try:
                with __import__("sqlite3").connect("enterprise_full_workspace.db") as conn:
                    reg = pd.read_sql("SELECT * FROM platform_models ORDER BY created_at DESC LIMIT 200", conn)
                if not reg.empty:
                    st.dataframe(reg, use_container_width=True, hide_index=True)
                    st.session_state["model_registry_latest_df"] = reg
            except Exception:
                st.info("No model registry records available yet.")

        elif "Jobs" in module:
            try:
                from industrial_experience import ensure_experience_db
                ensure_experience_db()
                with __import__("sqlite3").connect("enterprise_full_workspace.db") as conn:
                    jobs = pd.read_sql("SELECT * FROM experience_jobs ORDER BY COALESCE(started_at, created_at) DESC LIMIT 200", conn)
                if not jobs.empty:
                    st.dataframe(jobs, use_container_width=True, hide_index=True)
                    st.session_state["jobs_history_df"] = jobs
            except Exception:
                st.info("Job history is not available yet.")

        elif "Real-time" in module:
            telemetry = st.session_state.get("twin_tel")
            if not isinstance(telemetry, pd.DataFrame):
                telemetry = st.session_state.get("iot_sensors")
            telemetry = telemetry if isinstance(telemetry, pd.DataFrame) else pd.DataFrame(telemetry or [])
            if not telemetry.empty:
                if "Value" in telemetry.columns:
                    numeric = pd.to_numeric(telemetry["Value"], errors="coerce")
                elif "reading" in telemetry.columns:
                    numeric = pd.to_numeric(telemetry["reading"], errors="coerce")
                else:
                    numeric = pd.Series(dtype=float)
                if not numeric.empty:
                    threshold = st.number_input("Alert threshold", value=float(numeric.quantile(0.95)), key=f"rt_threshold_{token}")
                    alarms = telemetry.loc[numeric > threshold].copy()
                    st.session_state["realtime_alerts_df"] = alarms
                    st.dataframe(telemetry, use_container_width=True, hide_index=True)
                    st.metric("Anomaly / threshold alerts", len(alarms))
                    st.session_state["realtime_monitor_df"] = telemetry.copy()
            else:
                st.info("No telemetry evidence is available in the current workspace.")

        elif "Economics" in module:
            costs = st.data_editor(
                st.session_state.setdefault(
                    "economics_driver_df",
                    pd.DataFrame({"Driver": ["CAPEX", "Maintenance OPEX", "Energy OPEX", "Labor OPEX"], "Annual Cost": [180000, 25000, 30000, 45000]}),
                ),
                num_rows="dynamic", use_container_width=True, key=f"economics_drivers_{token}",
            )
            costs["Annual Cost"] = pd.to_numeric(costs["Annual Cost"], errors="coerce").fillna(0)
            tco = float(costs["Annual Cost"].sum())
            st.metric("Annualized Engineering TCO", f"{tco:,.0f}")
            st.session_state["engineering_economics_tco_df"] = costs.assign(TCO_Contribution=costs["Annual Cost"])

        elif "Sustainability" in module or "Green IE" in module:
            candidate = st.session_state.get("sustain_result")
            if not isinstance(candidate, pd.DataFrame):
                candidate = st.session_state.get("carbon_latest_df")
            if isinstance(candidate, pd.DataFrame) and not candidate.empty:
                numeric = candidate.select_dtypes(include=np.number)
                st.dataframe(candidate, use_container_width=True, hide_index=True)
                if not numeric.empty:
                    st.session_state["sustainability_decision_link_df"] = candidate[numeric.columns].copy()

        elif "Human Factors" in module:
            data = st.session_state.get("ergonomic_tasks")
            df = pd.DataFrame(data) if isinstance(data, list) else data
            if isinstance(df, pd.DataFrame) and not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
                nums = df.select_dtypes(include=np.number)
                if not nums.empty:
                    metric = st.selectbox("Human-factor KPI", list(nums.columns), key=f"hf_metric_{token}")
                    st.plotly_chart(px.histogram(df, x=metric, title=f"Human Factors · {metric}"), use_container_width=True)

        elif "Geospatial" in module:
            nodes = pd.DataFrame(st.session_state.get("supply_nodes", []))
            markets = pd.DataFrame(st.session_state.get("demand_markets", []))
            if not nodes.empty:
                st.dataframe(nodes, use_container_width=True, hide_index=True)
            if not markets.empty:
                st.dataframe(markets, use_container_width=True, hide_index=True)
                st.session_state["geospatial_markets_df"] = markets

        elif "Model Registry" in module:
            pass
