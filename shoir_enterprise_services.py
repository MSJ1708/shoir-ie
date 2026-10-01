"""Cross-cutting enterprise capability layer for Shoir-IE.

This module intentionally augments existing specialist modules instead of
creating duplicate business logic. It adds operational governance, health,
collaboration, knowledge, job controls, secure-file metadata, and artifact
provenance around the existing application state.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


CAPABILITY_STATE = {
    "IoT Digital Twin": ["node_mesh_df", "sensor_stream", "dt_workstations", "twin_tel"],
    "Live Industrial Digital Twin": ["twin_tel", "telemetry_events"],
    "Control Tower": ["control_tower_metrics", "control_tower_disruption_df"],
    "Industrial Control Center": ["control_center_metrics"],
    "Industrial Connectivity Hub": ["conn_df", "connector_profiles", "erp_connectors"],
    "Enterprise Integration & Collaboration": ["erp_connectors", "workspace_users", "audit_report_history"],
    "Enterprise Security & Governance": ["security_roles", "audit_governance_ledger"],
    "Persistence": ["saved_projects", "enterprise_artifact_ledger"],
    "Team Workspaces & RBAC": ["workspace_members_df"],
    "Engineering Model Registry": ["model_registry_df"],
    "Research Workspace": ["forecast_universal_result"],
    "Experiment Engine": [
        "experiment_engine_design_df", "experiment_engine_effects_df",
        "experiment_engine_mc_samples", "experiment_engine_bootstrap_df",
        "experiment_engine_sensitivity_df", "experiment_engine_replication_df",
    ],
    "Executive Report Center": ["exec_report_df"],
    "Engineering Economics & Finance": ["capex_result"],
    "Capital Investment & Engineering Economics": ["capex_result"],
    "Industrial Sustainability & LCA": ["sustain_result"],
    "Human Factors & Ergonomics (NIOSH)": ["human_factors_df", "ergonomics_result"],
    "Geospatial Network Designer": ["supply_nodes", "fleet_vehicles", "route_data", "df_routes"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_file_metadata(filename: str, payload: bytes, allowed_extensions: Sequence[str] = (".csv", ".xlsx", ".xls", ".pdf", ".txt", ".md", ".json")) -> dict[str, Any]:
    """Validate filename shape and return non-secret upload provenance.

    The raw bytes are not persisted by this helper.
    """
    name = os.path.basename(str(filename or "").strip())
    suffix = PurePath(name).suffix.lower()
    if not name or name in {".", ".."}:
        raise ValueError("A valid filename is required.")
    if suffix and suffix not in {str(x).lower() for x in allowed_extensions}:
        raise ValueError(f"Unsupported file type: {suffix}")
    if any(ord(ch) < 32 for ch in name):
        raise ValueError("Filename contains control characters.")
    if len(name) > 180:
        raise ValueError("Filename is too long.")
    raw = bytes(payload or b"")
    return {
        "filename": name,
        "extension": suffix or "none",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "captured_at": utc_now(),
    }


def _safe_frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    if isinstance(value, list):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    if isinstance(value, dict):
        numeric = {
            str(k): v for k, v in value.items()
            if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)
        }
        return pd.DataFrame([numeric]) if numeric else pd.DataFrame()
    return pd.DataFrame()


def current_module_frames(module: str) -> list[tuple[str, pd.DataFrame]]:
    keys = list(CAPABILITY_STATE.get(module, []))
    out: list[tuple[str, pd.DataFrame]] = []
    seen: set[str] = set()
    for key in keys + list(st.session_state.keys()):
        if str(key) in seen or str(key).startswith(("_", "password", "token", "secret", "otp")):
            continue
        value = st.session_state.get(key)
        if not isinstance(value, (pd.DataFrame, list, dict)):
            continue
        frame = _safe_frame(value)
        if frame.empty:
            continue
        words = [w for w in re.findall(r"[a-z0-9]+", str(module).lower()) if len(w) > 3]
        if key not in keys and words and not any(w in str(key).lower() for w in words):
            continue
        out.append((str(key), frame))
        seen.add(str(key))
        if len(out) >= 12:
            break
    return out


def data_intelligence_profile(df: pd.DataFrame, reference: pd.DataFrame | None = None) -> dict[str, Any]:
    """Return explainable schema, unit, ID, quality, outlier and drift diagnostics."""
    if not isinstance(df, pd.DataFrame):
        df = _safe_frame(df)
    rows, cols = df.shape
    numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    date_like: list[str] = []
    id_like: list[str] = []
    unit_hints: list[dict[str, str]] = []
    outliers: dict[str, int] = {}
    for col in df.columns:
        name = str(col)
        low = name.lower()
        if any(tok in low for tok in ("id", "code", "sku", "asset", "order", "serial", "part")):
            id_like.append(name)
        if any(tok in low for tok in ("date", "time", "timestamp")) or pd.api.types.is_datetime64_any_dtype(df[col]):
            date_like.append(name)
        unit = re.search(r"(?:\(([^)]+)\)|\[([^\]]+)\]|_([a-zA-Z%]+))$", name)
        if unit:
            unit_hints.append({"Column": name, "Unit": next(x for x in unit.groups() if x)})
        if pd.api.types.is_numeric_dtype(df[col]):
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(s) >= 8:
                q1, q3 = s.quantile([0.25, 0.75])
                iqr = q3 - q1
                outliers[name] = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum()) if iqr > 0 else 0
    missing_pct = float(df.isna().mean().mean() * 100) if cols else 100.0
    duplicate_pct = float(df.duplicated().mean() * 100) if rows else 0.0
    drift = detect_data_drift(df, reference) if isinstance(reference, pd.DataFrame) and not reference.empty else {"available": False}
    return {
        "rows": int(rows),
        "columns": int(cols),
        "numeric_columns": numeric,
        "date_like_columns": date_like,
        "id_like_columns": id_like,
        "unit_hints": unit_hints,
        "outlier_counts": outliers,
        "missing_pct": round(missing_pct, 3),
        "duplicate_pct": round(duplicate_pct, 3),
        "drift": drift,
        "quality_score": round(max(0.0, min(100.0, 100.0 - missing_pct * 0.7 - duplicate_pct * 0.4 - min(20.0, sum(outliers.values()) / max(1, rows) * 100.0))), 1),
    }


def detect_data_drift(current: pd.DataFrame, reference: pd.DataFrame | None) -> dict[str, Any]:
    if reference is None or reference.empty or current.empty:
        return {"available": False}
    common = [c for c in current.columns if c in reference.columns]
    rows: list[dict[str, Any]] = []
    for col in common:
        a = pd.to_numeric(current[col], errors="coerce")
        b = pd.to_numeric(reference[col], errors="coerce")
        if a.notna().sum() >= 5 and b.notna().sum() >= 5:
            ma, mb = float(a.mean()), float(b.mean())
            sb, sa = float(a.std(ddof=1)), float(b.std(ddof=1))
            scale = max(abs(mb), abs(sb), 1e-9)
            rows.append({"Field": str(col), "Metric": "Mean shift", "Value": abs(ma - mb) / scale})
        else:
            pa = current[col].astype(str).value_counts(normalize=True)
            pb = reference[col].astype(str).value_counts(normalize=True)
            cats = set(pa.index) | set(pb.index)
            shift = sum(abs(float(pa.get(k, 0)) - float(pb.get(k, 0))) for k in cats) / 2
            rows.append({"Field": str(col), "Metric": "Distribution shift", "Value": float(shift)})
    table = pd.DataFrame(rows)
    return {
        "available": not table.empty,
        "fields_checked": int(len(table)),
        "max_shift": float(table["Value"].max()) if not table.empty else 0.0,
        "flagged_fields": int((table["Value"] > 0.20).sum()) if not table.empty else 0,
        "table": table,
    }


def record_workspace_artifact(artifact_type: str, name: str, owner: str, payload: Mapping[str, Any] | None = None) -> str:
    """Record artifact provenance in workspace state; durable persistence captures it."""
    ledger = st.session_state.setdefault("enterprise_artifact_ledger", [])
    payload_dict = dict(payload or {})
    fingerprint = hashlib.sha256(
        json.dumps({"type": artifact_type, "name": name, "payload": payload_dict}, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16].upper()
    row = {
        "artifact_id": f"ART-{fingerprint}",
        "artifact_type": artifact_type,
        "name": str(name)[:180],
        "owner": str(owner)[:120],
        "created_at": utc_now(),
        "fingerprint": fingerprint,
        "payload": payload_dict,
    }
    ledger[:] = [x for x in ledger if x.get("artifact_id") != row["artifact_id"]]
    ledger.append(row)
    return row["artifact_id"]


def connector_health_frame() -> pd.DataFrame:
    configured: list[dict[str, Any]] = []
    for key in ("erp_connectors", "conn_df", "connector_profiles"):
        value = st.session_state.get(key)
        frame = _safe_frame(value)
        if not frame.empty:
            for r in frame.to_dict("records"):
                text = " ".join(str(v) for v in r.values())
                low = text.lower()
                protocol = next((p for p in ("SAP", "Oracle", "SQL", "REST", "MQTT", "OPC-UA", "WMS", "MES", "ERP") if p.lower() in low), "")
                status = next((str(r.get(k)) for k in r if "status" in str(k).lower() and str(r.get(k)).strip()), "Configured")
                configured.append({
                    "System": str(r.get("system_name", r.get("name", r.get("System", protocol or "Connector")))),
                    "Protocol": protocol or str(r.get("protocol", r.get("system_type", "Configured"))),
                    "Status": status,
                    "Freshness": str(r.get("last_sync", r.get("last_test", "Not measured"))),
                })
    supported = ["SAP", "Oracle", "SQL", "REST", "MQTT", "OPC-UA", "WMS", "MES", "ERP"]
    existing_protocols = {str(r["Protocol"]).upper() for r in configured}
    rows = configured.copy()
    for p in supported:
        if not any(p.upper() in x for x in existing_protocols):
            rows.append({"System": p, "Protocol": p, "Status": "Available · not configured", "Freshness": "Not connected"})
    return pd.DataFrame(rows).drop_duplicates(subset=["System", "Protocol"], keep="first")


def build_control_tower_health() -> pd.DataFrame:
    domains = {
        "Production": ("production", "manufacturing", "oee", "throughput"),
        "Supply": ("supply", "supplier", "procurement"),
        "Inventory": ("inventory", "stock", "safety"),
        "Quality": ("quality", "defect", "spc"),
        "Maintenance": ("maintenance", "asset", "vibration"),
        "Transport": ("transport", "fleet", "route", "shipment"),
        "Workforce": ("workforce", "staff", "operator", "ergonomic"),
        "Energy": ("energy", "power", "kwh"),
        "Carbon": ("carbon", "emission", "tco2"),
    }

    explicit = _safe_frame(st.session_state.get("control_tower_metrics"))
    explicit_lookup: dict[str, dict[str, Any]] = {}
    if not explicit.empty:
        domain_col = next((c for c in explicit.columns if str(c).lower() in {"domain","area","category","kpi"}), None)
        value_col = next((c for c in explicit.columns if str(c).lower() in {"value","score","health","status"}), None)
        if domain_col:
            for row in explicit.to_dict("records"):
                key = str(row.get(domain_col, "")).lower()
                explicit_lookup[key] = row

    rows = []
    for domain, tokens in domains.items():
        candidate = None
        for key, value in st.session_state.items():
            if str(key).startswith(("_", "password", "token", "secret", "otp")):
                continue
            if isinstance(value, (pd.DataFrame, list, dict)) and any(tok in str(key).lower() for tok in tokens):
                frame = _safe_frame(value)
                if not frame.empty:
                    candidate = (str(key), frame)
                    break
        exact = explicit_lookup.get(domain.lower())
        if candidate:
            key, frame = candidate
            profile = data_intelligence_profile(frame)
            rows.append({"Domain": domain, "Status": "Ready" if profile["quality_score"] >= 85 else "Review", "Records": len(frame), "Quality Score": profile["quality_score"], "Source": key})
        elif exact:
            raw_status = exact.get("Status", exact.get("Health", "Observed KPI"))
            numeric = exact.get("Value", exact.get("Health", np.nan))
            rows.append({"Domain": domain, "Status": str(raw_status), "Records": 1, "Quality Score": np.nan, "Source": "control_tower_metrics", "KPI Value": numeric})
        else:
            rows.append({"Domain": domain, "Status": "No linked KPI", "Records": 0, "Quality Score": np.nan, "Source": "Not linked"})

    return pd.DataFrame(rows)


def replay_twin_frame() -> pd.DataFrame:
    frames = []
    for key in ("sensor_stream", "twin_tel"):
        frame = _safe_frame(st.session_state.get(key))
        if not frame.empty:
            f = frame.copy()
            metric = next((c for c in f.columns if str(c).lower() in {"metric", "measure"}), None)
            value = next((c for c in f.columns if str(c).lower() in {"value", "measurement", "reading"}), None)
            ts = next((c for c in f.columns if any(x in str(c).lower() for x in ("time", "timestamp", "date", "ts"))), None)
            asset = next((c for c in f.columns if any(x in str(c).lower() for x in ("asset", "sensor", "node", "workstation"))), None)
            if value:
                cols = {value: "Value"}
                if metric: cols[metric] = "Metric"
                if ts: cols[ts] = "Timestamp"
                if asset: cols[asset] = "Asset"
                out = f[list(cols)].rename(columns=cols)
                out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
                out = out.dropna(subset=["Value"])
                frames.append(out)
    if not frames:
        try:
            with sqlite3.connect("enterprise_full_workspace.db") as conn:
                stored = pd.read_sql("SELECT asset_id AS Asset, ts AS Timestamp, metric AS Metric, value AS Value, source AS Source FROM telemetry_events ORDER BY id DESC LIMIT 500", conn)
            stored["Value"] = pd.to_numeric(stored["Value"], errors="coerce")
            return stored.dropna(subset=["Value"])
        except Exception:
            return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def detect_twin_anomalies(df: pd.DataFrame, z_threshold: float = 3.0) -> pd.DataFrame:
    """Flag statistical anomalies without claiming machine-failure diagnosis."""
    if not isinstance(df, pd.DataFrame) or df.empty or "Value" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    if "Metric" not in out.columns:
        out["Metric"] = "Value"
    out["Mean"] = out.groupby("Metric")["Value"].transform("mean")
    out["Std Dev"] = out.groupby("Metric")["Value"].transform("std").fillna(0.0)
    out["Z-Score"] = (out["Value"] - out["Mean"]) / out["Std Dev"].replace(0, np.nan)
    out["Median"] = out.groupby("Metric")["Value"].transform("median")
    out["MAD"] = (out["Value"] - out["Median"]).abs().groupby(out["Metric"]).transform("median")
    out["Robust Z-Score"] = 0.6745 * (out["Value"] - out["Median"]) / out["MAD"].replace(0, np.nan)
    threshold = float(z_threshold)
    out["Alert"] = np.where(
        (out["Z-Score"].abs() >= threshold) | (out["Robust Z-Score"].abs() >= threshold),
        "Investigate",
        "Normal",
    )
    return out


def replay_twin_what_if(df: pd.DataFrame, metric: str, delta_pct: float) -> pd.DataFrame:
    if df.empty or "Value" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    mask = out["Metric"].astype(str).eq(metric) if "Metric" in out.columns else pd.Series(True, index=out.index)
    out["Baseline Value"] = out["Value"]
    out["Scenario Value"] = out["Value"]
    out.loc[mask, "Scenario Value"] = out.loc[mask, "Value"] * (1.0 + float(delta_pct) / 100.0)
    out["Delta"] = out["Scenario Value"] - out["Baseline Value"]
    out["Scenario"] = f"{metric} {delta_pct:+.1f}%"
    return out


def control_job(job_id: str, action: str) -> None:
    from industrial_experience import update_job
    with sqlite3.connect("enterprise_full_workspace.db") as conn:
        row = conn.execute("SELECT status FROM experience_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise ValueError("Job not found.")
    status = str(row[0])
    transitions = {
        "pause": {"Queued": "Paused", "Running": "Paused"},
        "resume": {"Paused": "Running"},
        "cancel": {"Queued": "Cancelled", "Running": "Cancelled", "Paused": "Cancelled"},
        "retry": {"Failed": "Queued", "Cancelled": "Queued"},
    }
    target = transitions.get(action, {}).get(status)
    if target is None:
        raise ValueError(f"Cannot {action} job in status {status}.")
    update_job(job_id, target, 0.0 if target in {"Queued", "Running"} else 100.0, f"Operator action: {action}")


def job_history_frame() -> pd.DataFrame:
    try:
        with sqlite3.connect("enterprise_full_workspace.db") as conn:
            return pd.read_sql(
                "SELECT job_id,module,job_type,status,progress,message,started_at,finished_at FROM experience_jobs ORDER BY COALESCE(started_at,finished_at) DESC LIMIT 250",
                conn,
            )
    except Exception:
        return pd.DataFrame()


def calculate_tco(cost_drivers: pd.DataFrame, years: int = 5, discount_rate: float = 0.08) -> tuple[pd.DataFrame, dict[str, float]]:
    """Calculate a transparent discounted total-cost-of-ownership schedule."""
    required = {"Driver", "Annual Cost", "Year 1 Cost"}
    if not required <= set(cost_drivers.columns):
        raise ValueError("TCO table requires Driver, Annual Cost and Year 1 Cost.")
    d = cost_drivers.copy()
    d["Annual Cost"] = pd.to_numeric(d["Annual Cost"], errors="coerce").fillna(0.0)
    d["Year 1 Cost"] = pd.to_numeric(d["Year 1 Cost"], errors="coerce").fillna(0.0)
    years = int(max(1, min(30, years)))
    rate = float(discount_rate)
    if rate <= -1.0:
        raise ValueError("Discount rate must be greater than -100%.")
    recurring = float(d["Annual Cost"].sum())
    one_time = float(d["Year 1 Cost"].sum())
    rows = []
    for year in range(1, years + 1):
        nominal = recurring + (one_time if year == 1 else 0.0)
        rows.append({"Year": year, "Nominal Cost": nominal, "Present Value": nominal / ((1.0 + rate) ** year)})
    schedule = pd.DataFrame(rows)
    return schedule, {
        "TCO (Nominal)": float(schedule["Nominal Cost"].sum()),
        "TCO (Discounted)": float(schedule["Present Value"].sum()),
        "Annual Recurring Cost": recurring,
        "Year 1 One-Time Cost": one_time,
        "Years": float(years),
        "Discount Rate": rate,
    }


def add_research_citation(
    title: str,
    authors: str,
    year: int | str,
    source: str,
    identifier: str,
    owner: str,
    research_id: str = "",
) -> dict[str, Any]:
    citations = st.session_state.setdefault("research_citations", [])
    citation = {
        "citation_id": "CIT-" + hashlib.sha1(
            f"{title}|{authors}|{year}|{identifier}|{owner}".encode("utf-8")
        ).hexdigest()[:12].upper(),
        "title": str(title).strip(),
        "authors": str(authors).strip(),
        "year": str(year).strip(),
        "source": str(source).strip(),
        "identifier": str(identifier).strip(),
        "research_id": str(research_id or ""),
        "owner": str(owner),
        "created_at": utc_now(),
    }
    citations[:] = [x for x in citations if x.get("citation_id") != citation["citation_id"]]
    citations.append(citation)
    record_workspace_artifact("citation", citation["title"], owner, citation)
    return citation


def knowledge_context() -> str:
    docs = st.session_state.get("knowledge_documents", [])
    parts = []
    for doc in docs[-12:]:
        summary = str(doc.get("excerpt", ""))[:1800]
        parts.append(f"[{doc.get('title','Knowledge')}] {summary}")
    return "\n".join(parts)


def render_knowledge_layer(username: str) -> None:
    st.markdown("#### 📚 Knowledge Layer")
    st.caption("Link standards, engineering methods, SOPs, manuals and company notes to the Copilot workspace.")
    upload = st.file_uploader("Add a knowledge document", type=["txt","md","pdf"], key="knowledge_layer_upload")
    linked = st.multiselect(
        "Link to modules",
        ["AI Copilot","Engineering Decision Center","Experiment Engine","Industrial Simulation Lab","Quality Engineering & Reliability","Advanced Planning & Scheduling"],
        default=["AI Copilot"],
        key="knowledge_layer_modules",
    )
    if upload is not None:
        try:
            meta = safe_file_metadata(upload.name, upload.getvalue(), [".txt",".md",".pdf"])
            raw = upload.getvalue()
            text = ""
            if meta["extension"] in {".txt",".md"}:
                text = raw.decode("utf-8", errors="replace")
            else:
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(raw))
                    text = "\n".join(page.extract_text() or "" for page in reader.pages)
                except Exception as exc:
                    text = f"PDF text extraction unavailable: {type(exc).__name__}"
            docs = st.session_state.setdefault("knowledge_documents", [])
            docs[:] = [d for d in docs if d.get("sha256") != meta["sha256"]]
            docs.append({
                **meta,
                "title": upload.name,
                "linked_modules": linked,
                "excerpt": text[:20000],
            })
            record_workspace_artifact("knowledge", upload.name, username, {"sha256": meta["sha256"], "linked_modules": linked})
            st.success("Knowledge document linked to the workspace.")
        except Exception as exc:
            st.error(f"Knowledge import failed safely: {exc}")
    docs = st.session_state.get("knowledge_documents", [])
    if docs:
        st.dataframe(pd.DataFrame([{k:d.get(k) for k in ["title","extension","bytes","sha256","captured_at","linked_modules"]} for d in docs]), use_container_width=True, hide_index=True)
        st.text_area("Copilot knowledge context preview", knowledge_context(), height=160, disabled=True)


def render_enterprise_bridge(module: str, tier: str, username: str) -> None:
    """Render only the capability overlay relevant to the selected module."""
    module = str(module)
    frames = current_module_frames(module)
    with st.expander("🧩 Enterprise Capability Layer", expanded=False):
        st.caption("Existing module logic remains authoritative. This layer adds cross-module governance, persistence, operational controls and visualization context.")
        tabs = st.tabs(["Governance","Data Intelligence","Operations","Collaboration","Research","Knowledge"])
        with tabs[0]:
            profile = data_intelligence_profile(frames[0][1]) if frames else {"rows":0,"columns":0,"quality_score":0,"missing_pct":100,"duplicate_pct":100,"numeric_columns":[],"date_like_columns":[],"id_like_columns":[],"unit_hints":[],"outlier_counts":{},"drift":{"available":False}}
            cols = st.columns(4)
            cols[0].metric("Data quality", f"{profile['quality_score']:.1f}%")
            cols[1].metric("Rows", f"{profile['rows']:,}")
            cols[2].metric("Numeric fields", f"{len(profile['numeric_columns']):,}")
            cols[3].metric("Outlier cells", f"{sum(profile['outlier_counts'].values()):,}")
            artifact_type = (
                "report" if module == "Executive Report Center" else
                "decision" if module == "Engineering Decision Center" else
                "experiment" if module in {"Experiment Engine","Experiment Lab"} else
                "model" if module == "Engineering Model Registry" else
                "project" if module == "Persistence" else
                "module_state"
            )
            artifact_id = record_workspace_artifact(
                artifact_type,
                module,
                username,
                {"rows": profile["rows"], "columns": profile["columns"], "quality_score": profile["quality_score"]},
            )
            st.caption(f"Workspace artifact fingerprint: {artifact_id}")
            if frames:
                st.dataframe(pd.DataFrame([{
                    "Field": f,
                    "Role": "ID" if f in profile["id_like_columns"] else ("Date/Time" if f in profile["date_like_columns"] else "Measure" if f in profile["numeric_columns"] else "Attribute"),
                } for f in frames[0][1].columns]), use_container_width=True, hide_index=True)
            st.markdown("**Durability:** " + ("Managed cloud backend configured" if _durable_ready() else "Local/ephemeral backend — configure the managed database for restart-safe cloud persistence."))
        with tabs[1]:
            if frames:
                table = data_intelligence_profile(frames[0][1])
                st.dataframe(pd.DataFrame([{"Metric":"Missing %","Value":table["missing_pct"]},{"Metric":"Duplicate %","Value":table["duplicate_pct"]},{"Metric":"Quality Score","Value":table["quality_score"]}]), use_container_width=True, hide_index=True)
                if table["unit_hints"]:
                    st.dataframe(pd.DataFrame(table["unit_hints"]), use_container_width=True, hide_index=True)
                if table["outlier_counts"]:
                    st.dataframe(pd.DataFrame([{"Field":k,"Outliers":v} for k,v in table["outlier_counts"].items() if v]), use_container_width=True, hide_index=True)
        with tabs[2]:
            if module in {"IoT Digital Twin","Live Industrial Digital Twin"}:
                twin = replay_twin_frame()
                if twin.empty:
                    st.info("No telemetry state is currently available for replay.")
                else:
                    st.dataframe(twin.head(100), use_container_width=True, hide_index=True)
                    z_threshold = st.number_input("Anomaly alert z-score threshold", 1.0, 6.0, 3.0, 0.1, key=f"twin_z_threshold_{hash(module)&0xffff:04x}")
                    anomalies = detect_twin_anomalies(twin, z_threshold)
                    st.session_state["enterprise_twin_anomalies_df"] = anomalies.copy(deep=True)
                    if not anomalies.empty:
                        flagged = anomalies[anomalies["Alert"] == "Investigate"]
                        st.metric("Telemetry observations flagged", f"{len(flagged):,}")
                        if not flagged.empty:
                            st.dataframe(flagged.head(100), use_container_width=True, hide_index=True)
                    metrics = sorted(twin["Metric"].dropna().astype(str).unique()) if "Metric" in twin.columns else []
                    if metrics:
                        metric = st.selectbox("Replay metric", metrics, key=f"twin_replay_metric_{hash(module)&0xffff:04x}")
                        metric_df = twin[twin["Metric"].astype(str) == metric].copy()
                        if "Timestamp" in metric_df.columns:
                            x = pd.to_datetime(metric_df["Timestamp"], errors="coerce")
                            fig = px.line(metric_df.assign(_time=x), x="_time", y="Value", markers=True, title=f"{metric} · Scenario Replay")
                            st.plotly_chart(fig, use_container_width=True)
                        delta = st.slider("What-if delta (%)", -50.0, 50.0, 0.0, 0.5, key=f"twin_whatif_delta_{hash(module)&0xffff:04x}")
                        if st.button("🔄 Replay what-if scenario", use_container_width=True, key=f"twin_whatif_{hash(module)&0xffff:04x}"):
                            scenario = replay_twin_what_if(twin, metric, delta)
                            st.session_state["twin_whatif_result"] = scenario
                            record_workspace_artifact("simulation", f"Twin what-if · {metric}", username, {"delta_pct": delta, "rows": len(scenario)})
                    if isinstance(st.session_state.get("twin_whatif_result"), pd.DataFrame):
                        st.dataframe(st.session_state["twin_whatif_result"], use_container_width=True, hide_index=True)
            elif module in {"Control Tower","Industrial Control Center"}:
                health = build_control_tower_health()
                st.session_state["enterprise_control_tower_health_df"] = health.copy(deep=True)
                st.dataframe(health, use_container_width=True, hide_index=True)
                if not health.empty:
                    fig = px.imshow(health[["Records","Quality Score"]].fillna(0).T, text_auto=True, aspect="auto", title="Unified Operations Health Map")
                    st.plotly_chart(fig, use_container_width=True)
            elif module == "Industrial Connectivity Hub" or module == "Enterprise Integration & Collaboration":
                health = connector_health_frame()
                st.session_state["enterprise_connector_health_df"] = health.copy(deep=True)
                st.dataframe(health, use_container_width=True, hide_index=True)
                if not health.empty:
                    st.plotly_chart(px.bar(health, x="Protocol", color="Status", title="Connector Health & Coverage"), use_container_width=True)
            elif "Jobs" in module or module in {"Industrial Simulation Lab","Experiment Engine","Multi-Objective Optimization","Robust & Resilient Optimization"}:
                jobs = job_history_frame()
                if jobs.empty:
                    st.info("No queued/running job history is currently stored.")
                else:
                    st.session_state["enterprise_job_history_df"] = jobs.copy(deep=True)
                    st.dataframe(jobs, use_container_width=True, hide_index=True)
                    st.caption("Job controls change the persisted orchestration state; they do not falsely claim to interrupt a solver already executing outside this process.")
                    for _, row in jobs.head(10).iterrows():
                        c1,c2,c3,c4 = st.columns(4)
                        c1.write(row["job_id"])
                        if c2.button("Pause", key=f"job_pause_{row['job_id']}"):
                            try: control_job(row["job_id"], "pause"); st.rerun()
                            except Exception as exc: st.error(str(exc))
                        if c3.button("Resume", key=f"job_resume_{row['job_id']}"):
                            try: control_job(row["job_id"], "resume"); st.rerun()
                            except Exception as exc: st.error(str(exc))
                        if c4.button("Cancel", key=f"job_cancel_{row['job_id']}"):
                            try: control_job(row["job_id"], "cancel"); st.rerun()
                            except Exception as exc: st.error(str(exc))
                    if str(row["status"]) in {"Failed", "Cancelled"}:
                        if st.button("Retry", key=f"job_retry_{row['job_id']}"):
                            try: control_job(row["job_id"], "retry"); st.rerun()
                            except Exception as exc: st.error(str(exc))
            else:
                st.info("Operational overlay is available when the selected module exposes a live table, telemetry, connector profile or job registry.")
        with tabs[3]:
            if module == "Engineering Decision Center":
                linked = []
                for key in ("carbon_latest_df", "sustain_result", "enterprise_tco_schedule_df"):
                    frame = _safe_frame(st.session_state.get(key))
                    if not frame.empty:
                        linked.append((key, frame))
                if linked:
                    st.markdown("##### 🌱 Sustainability / economics evidence linked to decision")
                    for key, frame in linked:
                        st.caption(f"Source: {key}")
                        st.dataframe(frame.head(100), use_container_width=True, hide_index=True)

            if module in {"Team Workspaces & RBAC","Enterprise Integration & Collaboration","Engineering Decision Center"}:
                st.markdown("##### 👥 Comments, mentions and assignments")
                comment = st.text_area("Comment", key=f"enterprise_comment_{hash(module)&0xffff:04x}")
                mention_targets = st.text_input("Mention users", placeholder="@engineering @manager", key=f"enterprise_mentions_{hash(module)&0xffff:04x}")
                ac1, ac2, ac3 = st.columns(3)
                with ac1:
                    assignee = st.text_input("Assignee", value="", key=f"enterprise_assignee_{hash(module)&0xffff:04x}")
                with ac2:
                    reviewer_role = st.selectbox("Reviewer role", ["Engineer","Manager","Approver","Viewer"], key=f"enterprise_reviewer_{hash(module)&0xffff:04x}")
                with ac3:
                    assignment = st.text_input("Assignment", placeholder="Verify Service KPI by Friday", key=f"enterprise_assignment_{hash(module)&0xffff:04x}")
                if st.button("💬 Save collaboration update", use_container_width=True, key=f"enterprise_collab_save_{hash(module)&0xffff:04x}"):
                    from industrial_experience import add_comment
                    combined = comment.strip()
                    if mention_targets.strip():
                        combined = (combined + " " + mention_targets.strip()).strip()
                    decision_id = st.session_state.get("decision_active_id") or st.session_state.get("decision_governed_card", {}).get("decision_id")
                    add_comment(None, decision_id, username, combined)
                    if decision_id:
                        try:
                            from industrial_experience import decision_approval_history
                            approval_history = decision_approval_history(decision_id)
                            st.session_state["enterprise_decision_approval_history_df"] = approval_history.copy(deep=True)
                        except Exception:
                            pass
                    assignments = st.session_state.setdefault("enterprise_collaboration_assignments", [])
                    if assignment.strip():
                        assignments.append({
                            "Assignment": assignment.strip(),
                            "Assignee": assignee.strip() or "Unassigned",
                            "Reviewer Role": reviewer_role,
                            "Status": "Open",
                            "Created By": username,
                            "Created At": utc_now(),
                        })
                        record_workspace_artifact("assignment", assignment.strip(), username, {"assignee": assignee.strip(), "reviewer_role": reviewer_role})
                    st.success("Collaboration update saved.")
                assignments = st.session_state.get("enterprise_collaboration_assignments", [])
                if assignments:
                    st.dataframe(pd.DataFrame(assignments), use_container_width=True, hide_index=True)
                approval_history = st.session_state.get("enterprise_decision_approval_history_df")
                if module == "Engineering Decision Center" and isinstance(approval_history, pd.DataFrame) and not approval_history.empty:
                    st.markdown("##### ✅ Approval history")
                    st.dataframe(approval_history, use_container_width=True, hide_index=True)

                if module == "Engineering Decision Center":
                    st.markdown("##### 🔁 Decision-to-Value Verification")
                    try:
                        from industrial_experience import decision_to_value_frame
                        value_frame = decision_to_value_frame(owner=username)
                    except Exception:
                        value_frame = pd.DataFrame()
                    if value_frame.empty:
                        st.info("No implemented or verified decision outcomes are recorded yet.")
                    else:
                        st.dataframe(value_frame, use_container_width=True, hide_index=True)
                        plot = value_frame.dropna(subset=["Predicted","Actual"]).copy()
                        if not plot.empty:
                            st.plotly_chart(
                                px.bar(plot, x="KPI", y=["Predicted","Actual"], barmode="group",
                                       title="Predicted vs Actual KPI Outcomes"),
                                use_container_width=True,
                            )
                        st.caption("Variance is calculated from recorded implementation outcomes; it is not a forecast.")

            elif module in {"Enterprise Security & Governance","Enterprise Integration & Collaboration","Persistence"}:
                roles = st.session_state.get("workspace_users", st.session_state.get("workspace_members_df", []))
                st.dataframe(_safe_frame(roles), use_container_width=True, hide_index=True)
                st.markdown("**Security configuration status**")
                st.write({
                    "RBAC": bool(roles is not None),
                    "Workspace isolation": True,
                    "Audit trail": True,
                    "SSO/OIDC": "Configured" if st.secrets.get("oidc", {}) else "Configuration surface",
                    "MFA": "Configured" if st.secrets.get("mfa", {}) else "Configuration surface",
                    "Secrets management": "Streamlit secrets / environment variables",
                    "Security scanning": "CI hook available",
                })
                audit_note = st.text_input("Audit event note", key=f"enterprise_audit_note_{hash(module)&0xffff:04x}")
                if st.button("🔐 Record audit event", use_container_width=True, key=f"enterprise_audit_save_{hash(module)&0xffff:04x}"):
                    with sqlite3.connect("enterprise_full_workspace.db") as conn:
                        conn.execute("INSERT INTO security_events(username,event_type,details,created_at) VALUES(?,?,?,?)",
                                     (username, "Enterprise Capability Audit", audit_note[:500], utc_now()))
                        conn.commit()
                    st.success("Audit event recorded.")
            else:
                st.info("Use the Collaboration or Security module for team/governance controls.")
        with tabs[4]:
            if module in {"Experiment Lab","Experiment Engine","Industrial Simulation Lab"}:
                st.markdown("##### 📝 Research & Reproducibility")
                try:
                    from industrial_experience import load_research_protocol, research_runs_frame, research_decisions_frame, _safe_key
                    study_id = st.session_state.get("sx_research_study_id")
                    protocol = load_research_protocol(study_id, owner=username) if study_id else None
                    runs = research_runs_frame(study_id, owner=username) if study_id else pd.DataFrame()
                    decisions = research_decisions_frame(username)
                    st.session_state["enterprise_research_runs_df"] = runs.copy(deep=True)
                    st.session_state["enterprise_research_decisions_df"] = decisions.copy(deep=True)
                except Exception:
                    protocol, runs, decisions = None, pd.DataFrame(), pd.DataFrame()
                if protocol:
                    st.dataframe(pd.DataFrame([
                        {"Field":"Research ID","Value":protocol.get("research_id")},
                        {"Field":"Protocol hash","Value":protocol.get("protocol_hash")},
                        {"Field":"Methodology","Value":protocol.get("methodology")},
                        {"Field":"Primary endpoint","Value":protocol.get("primary_endpoint")},
                        {"Field":"Runs captured","Value":len(runs)},
                    ]), use_container_width=True, hide_index=True)
                    if st.button("📝 Generate manuscript draft", use_container_width=True, key=f"research_manuscript_{hash(module)&0xffff:04x}"):
                        summary = protocol.get("protocol_notes", "")
                        manuscript = (
                            f"# {protocol.get('title','Research Study')}\n\n"
                            f"## Research question\n{protocol.get('research_question','')}\n\n"
                            f"## Objective\n{protocol.get('objective','')}\n\n"
                            f"## Hypotheses\n**H1:** {protocol.get('hypothesis','')}\n\n"
                            f"**H0:** {protocol.get('null_hypothesis','')}\n\n"
                            f"## Method\n{protocol.get('methodology','')} with {protocol.get('sample_size',0)} planned scenarios and {protocol.get('replications',0)} replications per scenario.\n\n"
                            f"## Primary endpoint\n{protocol.get('primary_endpoint','')}\n\n"
                            f"## Reproducibility\nProtocol hash: {protocol.get('protocol_hash','')}\nRandom seed: {protocol.get('random_seed','')}\n\n"
                            f"## Results status\n{len(runs)} persisted run(s) are currently linked to this study. This draft intentionally does not invent scientific findings.\n\n"
                            f"## Limitations\n{summary}\n"
                        )
                        st.session_state["research_manuscript_draft"] = manuscript
                        record_workspace_artifact("research_manuscript", protocol.get("title","Research Study"), username, {"protocol_hash": protocol.get("protocol_hash"), "runs": len(runs)})
                    citations = st.session_state.setdefault("research_citations", [])
                    st.markdown("##### 📚 Citation matrix")
                    with st.form(f"citation_form_{hash(module)&0xffff:04x}"):
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            cit_title = st.text_input("Citation title")
                            cit_authors = st.text_input("Authors")
                            cit_source = st.text_input("Journal / source")
                        with cc2:
                            cit_year = st.text_input("Year")
                            cit_identifier = st.text_input("DOI / URL / identifier")
                            cit_submit = st.form_submit_button("➕ Add citation", use_container_width=True)
                        if cit_submit:
                            if cit_title.strip() and cit_authors.strip():
                                add_research_citation(cit_title, cit_authors, cit_year, cit_source, cit_identifier, username, protocol.get("research_id",""))
                                st.success("Citation added to the research workspace.")
                            else:
                                st.warning("Citation title and authors are required.")
                    visible_citations = [x for x in citations if not x.get("research_id") or x.get("research_id") == protocol.get("research_id")]
                    if visible_citations:
                        st.dataframe(pd.DataFrame(visible_citations), use_container_width=True, hide_index=True)

                    if st.session_state.get("research_manuscript_draft"):
                        st.text_area("Manuscript draft", st.session_state["research_manuscript_draft"], height=320)
                        st.download_button("📥 Download manuscript Markdown", data=st.session_state["research_manuscript_draft"].encode("utf-8"), file_name=f"{_safe_key(protocol.get('study_id','study'))}_manuscript.md", mime="text/markdown", use_container_width=True)
                else:
                    st.info("Open or create a research study in Experiment Lab to enable manuscript drafting and reproducibility evidence.")
                supplemental = st.file_uploader("Add supplementary research file metadata", type=["csv","xlsx","pdf","zip"], key=f"research_supp_{hash(module)&0xffff:04x}")
                if supplemental is not None:
                    meta = safe_file_metadata(supplemental.name, supplemental.getvalue(), [".csv",".xlsx",".pdf",".zip"])
                    record_workspace_artifact("supplementary_file", supplemental.name, username, meta)
                    st.success(f"Supplementary file fingerprint recorded: {meta['sha256'][:16]}…")
            else:
                st.caption("Research controls are available from Experiment Lab / Experiment Engine.")

        if module in {"Engineering Economics & Finance", "Capital Investment & Engineering Economics"}:
            st.markdown("##### 💰 Lifecycle Cost / TCO View")
            drivers = st.data_editor(
                st.session_state.setdefault(
                    "enterprise_tco_drivers",
                    pd.DataFrame({
                        "Driver": ["Initial CAPEX", "Maintenance", "Energy", "Labor", "Software / Support"],
                        "Annual Cost": [0.0, 12000.0, 18000.0, 25000.0, 5000.0],
                        "Year 1 Cost": [150000.0, 0.0, 0.0, 0.0, 0.0],
                    }),
                ),
                num_rows="dynamic", use_container_width=True, key=f"enterprise_tco_editor_{hash(module)&0xffff:04x}",
            )
            tc1, tc2 = st.columns(2)
            years = tc1.number_input("TCO horizon (years)", 1, 30, 5, key=f"enterprise_tco_years_{hash(module)&0xffff:04x}")
            rate = tc2.number_input("TCO discount rate", -0.5, 0.5, 0.08, 0.01, key=f"enterprise_tco_rate_{hash(module)&0xffff:04x}")
            if st.button("💰 Calculate TCO", use_container_width=True, key=f"enterprise_tco_run_{hash(module)&0xffff:04x}"):
                try:
                    schedule, summary = calculate_tco(drivers, years, rate)
                    st.session_state["enterprise_tco_schedule_df"] = schedule
                    st.session_state["enterprise_tco_summary"] = summary
                    record_workspace_artifact("economics", "Total Cost of Ownership", username, summary)
                except Exception as exc:
                    st.error(f"TCO calculation failed safely: {exc}")
            if st.session_state.get("enterprise_tco_summary"):
                ts = st.session_state["enterprise_tco_summary"]
                a1, a2, a3 = st.columns(3)
                a1.metric("Discounted TCO", f"{ts['TCO (Discounted)']:,.2f}")
                a2.metric("Nominal TCO", f"{ts['TCO (Nominal)']:,.2f}")
                a3.metric("Recurring / year", f"{ts['Annual Recurring Cost']:,.2f}")
                tco_df = st.session_state.get("enterprise_tco_schedule_df", pd.DataFrame())
                if isinstance(tco_df, pd.DataFrame) and not tco_df.empty:
                    st.dataframe(tco_df, use_container_width=True, hide_index=True)
                    st.plotly_chart(
                        px.line(tco_df, x="Year", y=["Nominal Cost", "Present Value"], markers=True, title="TCO Lifecycle Curve"),
                        use_container_width=True,
                    )

        with tabs[5]:
            if module in {"AI Copilot","Advanced Engineering Copilot","Engineering Decision Center","Experiment Engine"}:
                render_knowledge_layer(username)
            else:
                docs = st.session_state.get("knowledge_documents", [])
                st.caption(f"Linked knowledge documents available to this workspace: {len(docs)}")
                if docs:
                    st.dataframe(pd.DataFrame([{"Title":d.get("title"),"Modules":d.get("linked_modules",[]),"Hash":d.get("sha256")} for d in docs]), use_container_width=True, hide_index=True)


def _durable_ready() -> bool:
    try:
        from durable_account_store import durable_backend_configured
        return bool(durable_backend_configured())
    except Exception:
        return False
