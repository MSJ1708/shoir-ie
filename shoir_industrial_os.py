"""Shoir-IE Industrial Operating System -- complete cross-cutting integration layer.

This module deepens the existing Shoir-IE kernel instead of replacing specialist
modules. It provides:
- governed module manifests and maturity
- durable Project / Digital Thread / Scenario / Decision objects
- uncertainty + experiment utilities
- visualization intelligence
- engineering formulas / KPI ontology
- forecasting and optimization diagnostics
- connector metadata / self-diagnostics
- ROI, verification, reproducibility and industrial story helpers
- a compact Engineering Canvas / Control Tower work surface

All analytics are data-grounded. No production integration is claimed unless the
connected runtime reports that integration as available.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from shoir_platform_core import (
    capability_ledger as core_capability_ledger,
    render_platform_completion as render_core_completion,
    render_engineering_canvas as render_core_canvas,
    db_backend as core_db_backend,
    ensure_core_schema,
)
import plotly.express as px
import streamlit as st


WORKFLOW_STEPS = (
    "DATA", "VALIDATE", "MAP", "MODEL", "RUN", "VISUALIZE",
    "COMPARE", "EXPLAIN", "DECIDE", "EXPORT", "VERIFY",
)

CAPABILITY_STATES = ("Verified", "Implemented", "Foundation", "Integration-ready")

DOMAIN_ALIASES: dict[str, tuple[str, ...]] = {
    "production": ("production", "capacity", "line", "oee", "shop", "manufacturing"),
    "quality": ("quality", "spc", "defect", "fmea", "six sigma", "capability"),
    "maintenance": ("maintenance", "reliability", "asset health", "downtime", "predictive"),
    "supply_chain": ("supply", "inventory", "warehouse", "supplier", "logistics", "routing"),
    "economics": ("economics", "finance", "investment", "npv", "irr", "capex", "opex", "cost"),
    "sustainability": ("carbon", "energy", "sustainability", "lca", "emission"),
    "workforce": ("workforce", "staffing", "ergonomic", "labor", "human factors"),
    "research": ("research", "experiment", "hypothesis", "statistical", "paper"),
    "digital_twin": ("digital twin", "iot", "telemetry", "simulation", "des"),
    "decision": ("decision", "scenario", "compare", "benchmark"),
}


@dataclass(frozen=True)
class ModuleManifest:
    identity: str
    purpose: str
    inputs: tuple[str, ...] = ("dataset",)
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    units: tuple[str, ...] = ()
    validation_rules: tuple[str, ...] = ("rows_present", "unique_columns", "missing_values_review")
    transformations: tuple[str, ...] = ()
    model: str = "specialist_engine"
    solver: str = ""
    outputs: tuple[str, ...] = ("results", "kpis")
    kpis: tuple[str, ...] = ()
    recommended_visualizations: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ("summary_statistics", "percentiles")
    assumptions: tuple[str, ...] = ()
    scenario_support: bool = True
    export_formats: tuple[str, ...] = ("xlsx", "csv", "json")
    persistence: bool = True
    permissions: tuple[str, ...] = ("READ", "ANALYZE", "EXPORT")
    maturity: str = "Implemented"
    verification_tests: tuple[str, ...] = ("contract", "sanity", "regression")


MODULE_DEFAULTS: dict[str, ModuleManifest] = {
    "Industrial Problem Solver": ModuleManifest(
        "Industrial Problem Solver",
        "Translate an engineering objective into a governed analysis workflow.",
        outputs=("workflow_plan", "required_data", "recommended_capabilities"),
        kpis=("readiness", "coverage"),
        recommended_visualizations=("workflow", "readiness"),
        permissions=("READ", "ANALYZE", "RECOMMEND", "PREPARE"),
        maturity="Implemented",
    ),
    "Engineering Model Registry": ModuleManifest(
        "Engineering Model Registry",
        "Govern versions, assumptions, solvers and reproducibility metadata.",
        outputs=("model_record", "reproducibility_manifest"),
        kpis=("verification", "reproducibility"),
        recommended_visualizations=("model_lifecycle", "verification_matrix"),
        permissions=("READ", "ANALYZE", "APPROVE", "EXPORT"),
    ),
    "Experiment Engine": ModuleManifest(
        "Experiment Engine",
        "Design, execute and audit deterministic experiments and uncertainty studies.",
        inputs=("dataset", "factors", "responses", "seed"),
        outputs=("design", "response", "effects", "uncertainty"),
        kpis=("effect_size", "confidence", "power"),
        recommended_visualizations=("effect_plot", "interaction_plot", "distribution", "sensitivity"),
        permissions=("READ", "ANALYZE", "SIMULATE", "PREPARE", "EXPORT"),
    ),
    "Decision Center": ModuleManifest(
        "Decision Center",
        "Compare alternatives, evidence, constraints and implementation outcomes.",
        outputs=("decision_card", "scenario_comparison", "verification"),
        kpis=("impact", "risk", "constraint_compliance"),
        recommended_visualizations=("scenario_delta", "tornado", "tradeoff"),
        permissions=("READ", "ANALYZE", "RECOMMEND", "PREPARE", "APPROVE", "EXPORT"),
    ),
}


INDUSTRIAL_TEMPLATES: list[dict[str, Any]] = [
    {"name": "Production Capacity Study", "goal": "Increase throughput", "modules": ["Capacity Analysis", "Bottleneck Analysis", "Optimization", "Scenario Comparison"]},
    {"name": "Line Balancing Study", "goal": "Balance work content", "modules": ["Line Balancing", "Work Measurement", "Scenario Comparison"]},
    {"name": "Inventory Optimization", "goal": "Reduce inventory while maintaining service", "modules": ["Inventory", "Forecasting", "Optimization", "Scenario Comparison"]},
    {"name": "Warehouse Slotting", "goal": "Reduce travel and improve service", "modules": ["Warehouse Analysis", "Slotting", "Geospatial Analysis"]},
    {"name": "Supplier Risk Assessment", "goal": "Improve supply resilience", "modules": ["Supplier Risk", "Inventory", "Scenario Comparison"]},
    {"name": "Maintenance Optimization", "goal": "Reduce downtime", "modules": ["Maintenance", "Reliability", "Forecasting", "Scenario Comparison"]},
    {"name": "OEE Investigation", "goal": "Improve equipment effectiveness", "modules": ["OEE", "SPC", "Bottleneck Analysis"]},
    {"name": "Facility Layout", "goal": "Reduce material movement", "modules": ["Facility Layout", "Travel Analysis", "Geospatial Analysis"]},
    {"name": "Workforce Sizing", "goal": "Right-size staffing", "modules": ["Workforce", "Scheduling", "Optimization"]},
    {"name": "Transport Optimization", "goal": "Reduce transport cost/distance", "modules": ["Routing", "Network Optimization", "Scenario Comparison"]},
    {"name": "Quality Investigation", "goal": "Reduce defects", "modules": ["SPC", "Pareto", "Capability", "FMEA"]},
    {"name": "Energy Assessment", "goal": "Reduce energy intensity", "modules": ["Energy Analytics", "Forecasting", "Scenario Comparison"]},
    {"name": "Carbon Assessment", "goal": "Measure and reduce carbon intensity", "modules": ["Carbon Accounting", "LCA", "Scenario Comparison"]},
    {"name": "Capital Investment", "goal": "Evaluate investment alternatives", "modules": ["CAPEX/OPEX", "NPV/IRR", "Monte Carlo", "Decision Center"]},
    {"name": "Demand Forecast", "goal": "Improve demand visibility", "modules": ["Forecasting", "Backtesting", "Scenario Forecast"]},
    {"name": "Production Scheduling", "goal": "Meet demand with constraints", "modules": ["APS", "Scheduling", "Optimization", "Scenario Comparison"]},
    {"name": "Six Sigma Project", "goal": "Reduce process variation", "modules": ["SPC", "Capability", "DOE", "Hypothesis Testing"]},
    {"name": "Simulation Study", "goal": "Stress-test system behavior", "modules": ["DES", "Monte Carlo", "Sensitivity", "Scenario Comparison"]},
    {"name": "Research Experiment", "goal": "Generate reproducible evidence", "modules": ["Protocol", "DOE", "Statistical Analysis", "Reproducibility"]},
]


PROBLEM_WORKFLOWS: dict[str, list[str]] = {
    "Reduce Cost": ["Data Quality", "Cost Driver Analysis", "Scenario Comparison", "Optimization", "Decision Center"],
    "Increase Throughput": ["Capacity Analysis", "Bottleneck Analysis", "Scheduling", "Optimization", "Scenario Comparison"],
    "Improve Quality": ["Quality Profile", "SPC", "Pareto", "Root Cause / DOE", "Verification"],
    "Reduce Inventory": ["Forecasting", "Inventory Analysis", "Safety Stock", "Optimization", "Scenario Comparison"],
    "Improve Delivery": ["Demand Profile", "Capacity / Scheduling", "Routing", "Scenario Comparison", "Verification"],
    "Reduce Downtime": ["Maintenance Profile", "Reliability", "Downtime Drivers", "Scenario Simulation", "Verification"],
    "Optimize Workforce": ["Work Measurement", "Staffing Analysis", "Scheduling", "Optimization", "Scenario Comparison"],
    "Reduce Energy": ["Energy Profile", "Baseline", "Scenario Simulation", "Optimization", "Verification"],
    "Reduce Carbon": ["Carbon Baseline", "Hotspot Analysis", "Scenario Comparison", "Optimization", "Verification"],
    "Design Facility": ["Demand / Flow", "Layout", "Travel Analysis", "Simulation", "Comparison"],
    "Improve Reliability": ["Asset History", "Failure Analysis", "Reliability Model", "Maintenance Scenario", "Verification"],
    "Analyze Investment": ["Cash Flow", "NPV / IRR", "Sensitivity", "Monte Carlo", "Decision Center"],
    "Conduct Research": ["Protocol", "Data Validation", "Experimental Design", "Statistical Analysis", "Reproducibility"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def jsonable(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def dataframe_digest(df: pd.DataFrame) -> str:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ""
    schema = "|".join(f"{c}:{df[c].dtype}" for c in df.columns)
    try:
        body = pd.util.hash_pandas_object(df, index=True).values.tobytes()
    except Exception:
        body = df.to_csv(index=True).encode("utf-8", errors="replace")
    return hashlib.sha256(schema.encode("utf-8") + body).hexdigest()


def active_dataframe() -> tuple[pd.DataFrame, str]:
    preferred = (
        "universal_active_dataset", "excel_studio_visual_df", "data_platform_latest_df",
        "industrial_workbook_current_df", "os160_cleaned_df", "copilot_workbook",
        "excel_studio_df", "forecast_df", "quality_df", "experiment_df",
    )
    for key in preferred:
        value = st.session_state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=True), key
    for key, value in st.session_state.items():
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(deep=True), str(key)
    return pd.DataFrame(), ""


def profile_data(df: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {
            "rows": 0, "columns": 0, "missing_cells": 0, "duplicate_rows": 0,
            "missing_pct": 100.0, "duplicate_pct": 0.0, "numeric_columns": [],
            "date_columns": [], "constant_columns": [], "id_columns": [], "readiness": 0.0,
            "warnings": ["No active engineering dataset."],
        }
    rows, cols = df.shape
    numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    dates: list[str] = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            dates.append(str(c))
            continue
        if s.dtype == object:
            sample = s.dropna().astype(str).head(40)
            if len(sample) >= 5:
                parsed = pd.to_datetime(sample, errors="coerce")
                if float(parsed.notna().mean()) >= 0.8:
                    dates.append(str(c))
    missing_cells = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    missing_pct = missing_cells / max(1, rows * cols) * 100.0
    duplicate_pct = duplicate_rows / max(1, rows) * 100.0
    id_columns = [str(c) for c in df.columns if re.search(r"(?:^|_|\b)(id|code|sku|asset|order|serial|part)(?:$|_|\b)", str(c), flags=re.I)]
    constant_columns = [str(c) for c in df.columns if len(df) > 1 and df[c].nunique(dropna=False) <= 1]
    warnings: list[str] = []
    if missing_pct > 10:
        warnings.append(f"Missingness {missing_pct:.1f}% exceeds the normal review threshold.")
    if duplicate_pct > 5:
        warnings.append(f"Duplicate rows {duplicate_pct:.1f}% should be reviewed.")
    if not numeric:
        warnings.append("No numeric measures detected.")
    score = 100.0 - min(45.0, missing_pct * 0.55) - min(35.0, duplicate_pct * 0.45)
    if not numeric:
        score -= 10
    return {
        "rows": rows, "columns": cols, "missing_cells": missing_cells, "duplicate_rows": duplicate_rows,
        "missing_pct": round(missing_pct, 2), "duplicate_pct": round(duplicate_pct, 2),
        "numeric_columns": numeric, "date_columns": dates, "constant_columns": constant_columns,
        "id_columns": id_columns, "readiness": round(max(0.0, min(100.0, score)), 1), "warnings": warnings,
    }


def normalize_provenance(default: str = "DEMO") -> str:
    value = str(st.session_state.get("shoir_data_status", "")).upper().strip()
    if value in {"LIVE", "IMPORTED", "SIMULATED", "DEMO"}:
        return value
    _, key = active_dataframe()
    blob = " ".join([
        str(st.session_state.get("shoir_data_source_key", "")),
        str(st.session_state.get("shoir_data_source", "")),
        key,
    ]).lower()
    if any(x in blob for x in ("iot", "telemetry", "connector", "live")):
        return "LIVE"
    if any(x in blob for x in ("upload", "import", "excel", "workbook")):
        return "IMPORTED"
    if any(x in blob for x in ("simulation", "scenario", "forecast", "experiment", "monte")):
        return "SIMULATED"
    return default


def module_manifest(module: str, *, allowed_modules: Sequence[str] | None = None) -> dict[str, Any]:
    name = str(module)
    if name in MODULE_DEFAULTS:
        result = asdict(MODULE_DEFAULTS[name])
    else:
        domain = next((d for d, aliases in DOMAIN_ALIASES.items() if any(a in name.lower() for a in aliases)), "general")
        visuals = {
            "production": ("trend", "utilization", "waterfall"),
            "quality": ("control_chart", "pareto", "histogram"),
            "maintenance": ("failure_distribution", "trend", "risk"),
            "supply_chain": ("network", "inventory_profile", "distribution"),
            "economics": ("cashflow", "sensitivity", "waterfall"),
            "sustainability": ("energy_trend", "hotspot", "waterfall"),
            "workforce": ("staffing_profile", "balance", "utilization"),
            "research": ("effect_plot", "residuals", "distribution"),
            "digital_twin": ("state_map", "replay", "scenario"),
            "decision": ("scenario_delta", "tornado", "tradeoff"),
            "general": ("auto", "distribution", "correlation"),
        }[domain]
        result = asdict(ModuleManifest(
            identity=name,
            purpose=f"Specialist Shoir-IE engineering module for {domain.replace('_', ' ')} workflows.",
            recommended_visualizations=visuals,
            maturity="Implemented" if (not allowed_modules or name in allowed_modules) else "Foundation",
        ))
    result["workflow"] = list(WORKFLOW_STEPS)
    result["generated_at"] = now_iso()
    result["contract_version"] = "2.0"
    return result


def capability_maturity(feature_catalog: Sequence[Mapping[str, Any]] | None = None) -> pd.DataFrame:
    try:
        from shoir_160 import FEATURES_160
        raw = list(feature_catalog or FEATURES_160)
    except Exception:
        raw = []
    rows: list[dict[str, Any]] = []
    for item in raw:
        state = str(item.get("maturity") or item.get("status") or item.get("state") or "Foundation")
        if state == "Operational":
            state = "Implemented"
        if state not in CAPABILITY_STATES:
            state = "Foundation"
        rows.append({
            "ID": item.get("id"),
            "Capability": item.get("name", item.get("Capability", "Unknown")),
            "Area": item.get("area", item.get("Area", "Platform")),
            "Status": state,
            "Coverage": float(item.get("coverage", 0.0) or 0.0),
            "Test coverage": float(item.get("test_coverage", 0.0) or 0.0),
            "Last verification": item.get("last_verification", "Not recorded"),
            "Dependencies": item.get("dependencies", ""),
            "Deployment": item.get("deployment", ""),
        })
    return pd.DataFrame(rows)


def _safe_workspace() -> tuple[str, str]:
    username = str(st.session_state.get("current_user") or st.session_state.get("username") or "anonymous")
    workspace = str(
        st.session_state.get("shoir_workspace_name")
        or st.session_state.get("active_workspace_name")
        or st.session_state.get("workspace")
        or "default"
    )
    return username, workspace


def persist_object(
    object_type: str,
    name: str,
    payload: Mapping[str, Any],
    *,
    artifact_id: str | None = None,
) -> str:
    username, workspace = _safe_workspace()
    try:
        from shoir_enterprise_layer import record_artifact
        return record_artifact(
            username, object_type, name, jsonable(dict(payload)),
            workspace=workspace, artifact_id=artifact_id,
        )
    except Exception:
        # Local session fallback keeps the UX functional in deployments where
        # the enterprise layer is not configured yet.
        key = f"shoir_os_{object_type}_objects"
        items = dict(st.session_state.get(key, {}))
        aid = artifact_id or f"{object_type[:4].upper()}-{uuid.uuid4().hex[:10].upper()}"
        items[aid] = {"id": aid, "name": name, **jsonable(dict(payload))}
        st.session_state[key] = items
        return aid


def list_persisted_objects(object_type: str, limit: int = 100) -> pd.DataFrame:
    username, workspace = _safe_workspace()
    try:
        from shoir_enterprise_layer import list_artifacts
        df = list_artifacts(username, artifact_type=object_type, workspace=workspace, limit=limit)
        if not df.empty:
            return df
    except Exception:
        pass
    items = st.session_state.get(f"shoir_os_{object_type}_objects", {})
    if not isinstance(items, Mapping) or not items:
        return pd.DataFrame()
    return pd.DataFrame(list(items.values())).head(limit)


def create_project(
    name: str,
    objective: str = "",
    problem_statement: str = "",
    scope: str = "",
    baseline: Mapping[str, Any] | None = None,
) -> str:
    project_id = f"PRJ-{uuid.uuid4().hex[:12].upper()}"
    payload = {
        "project_id": project_id,
        "objective": str(objective).strip(),
        "problem_statement": str(problem_statement).strip(),
        "scope": str(scope).strip(),
        "baseline": jsonable(baseline or {}),
        "datasets": [], "mappings": [], "models": [], "experiments": [],
        "scenarios": [], "runs": [], "results": [], "decisions": [],
        "approvals": [], "implementation": [], "actual_kpis": [], "variance": [],
        "documents": [], "audit_history": [],
        "status": "Active", "created_at": now_iso(), "updated_at": now_iso(),
    }
    st.session_state["shoir_project_id"] = project_id
    st.session_state["shoir_project_name"] = str(name).strip() or project_id
    st.session_state["shoir_project_payload"] = payload
    return persist_object("project", str(name).strip() or project_id, payload, artifact_id=project_id)


def active_project() -> dict[str, Any] | None:
    payload = st.session_state.get("shoir_project_payload")
    if isinstance(payload, Mapping):
        return dict(payload)
    projects = list_persisted_objects("project", limit=25)
    if not projects.empty:
        row = projects.iloc[0].to_dict()
        try:
            nested = json.loads(row.get("payload_json", "{}"))
            if isinstance(nested, Mapping):
                recovered = dict(nested)
                recovered.setdefault("name", row.get("name", "Project"))
                recovered.setdefault("project_id", row.get("artifact_id", ""))
                return recovered
        except Exception:
            pass
    return None


def attach_project_object(kind: str, object_id: str, **metadata: Any) -> None:
    payload = active_project()
    if not payload:
        return
    plural = {
        "dataset": "datasets", "mapping": "mappings", "model": "models",
        "experiment": "experiments", "scenario": "scenarios", "run": "runs",
        "result": "results", "decision": "decisions", "approval": "approvals",
        "implementation": "implementation", "kpi": "actual_kpis", "variance": "variance",
        "document": "documents",
    }.get(kind, f"{kind}s")
    payload.setdefault(plural, [])
    payload[plural].append({"id": object_id, **jsonable(metadata), "attached_at": now_iso()})
    payload["updated_at"] = now_iso()
    st.session_state["shoir_project_payload"] = payload
    persist_object("project", str(payload.get("name") or st.session_state.get("shoir_project_name") or payload["project_id"]), payload, artifact_id=str(payload["project_id"]))


def sync_dataset_thread(df: pd.DataFrame, source_name: str = "") -> dict[str, Any]:
    username, workspace = _safe_workspace()
    digest = dataframe_digest(df)
    dataset_name = source_name or str(st.session_state.get("shoir_data_source") or "Active Dataset")
    try:
        from shoir_enterprise_layer import upsert_canonical_entity, upsert_canonical_relationship
        dataset_id = upsert_canonical_entity(
            username, "Dataset", dataset_name, source="platform_os",
            state={"rows": len(df), "columns": list(map(str, df.columns)), "sha256": digest},
            status="Observed", workspace=workspace,
        )
        attach_project_object("dataset", dataset_id, name=dataset_name, sha256=digest, rows=len(df), columns=len(df.columns))
        entities = {"Dataset": dataset_id}
        # Create governed hints only when the data supports them.
        joined = " ".join(map(str, df.columns)).lower()
        if "asset" in joined:
            asset_col = next(c for c in df.columns if "asset" in str(c).lower())
            values = [x for x in pd.Series(df[asset_col]).dropna().astype(str).unique()[:25]]
            for value in values:
                aid = upsert_canonical_entity(
                    username, "Asset", value, source="dataset", state={"source_dataset": dataset_name},
                    workspace=workspace,
                )
                upsert_canonical_relationship(username, dataset_id, aid, "CONTAINS", workspace=workspace)
                entities.setdefault("Asset", []).append(aid) if isinstance(entities.get("Asset"), list) else entities.__setitem__("Asset", [aid])
        process_col = next((c for c in df.columns if any(token in str(c).lower() for token in ("process", "operation", "workcenter", "work_center"))), None)
        if process_col is not None:
            for value in [x for x in pd.Series(df[process_col]).dropna().astype(str).unique()[:25]]:
                pid = upsert_canonical_entity(username, "Process", value, source="dataset", state={"source_dataset": dataset_name}, workspace=workspace)
                upsert_canonical_relationship(username, dataset_id, pid, "FEEDS_PROCESS", workspace=workspace)
                entities.setdefault("Process", []).append(pid) if isinstance(entities.get("Process"), list) else entities.__setitem__("Process", [pid])
        kpi_candidates = [c for c in df.select_dtypes(include=np.number).columns if any(token in str(c).lower() for token in ("throughput", "oee", "utilization", "cost", "quality", "defect", "energy", "carbon", "service", "lead"))]
        for col in kpi_candidates[:12]:
            kid = upsert_canonical_entity(username, "KPI", str(col), source="dataset", state={"source_dataset": dataset_name, "unit_hint": str(col)}, workspace=workspace)
            upsert_canonical_relationship(username, dataset_id, kid, "MEASURES", workspace=workspace)
            entities.setdefault("KPI", []).append(kid)
        return {"dataset_id": dataset_id, "sha256": digest, "entities": entities, "workspace": workspace}
    except Exception as exc:
        return {"dataset_id": "", "sha256": digest, "entities": {}, "workspace": workspace, "warning": f"{type(exc).__name__}: {exc}"}


def evidence_manifest(
    module: str,
    *,
    result: Any = None,
    assumptions: Mapping[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    df, source_key = active_dataframe()
    profile = profile_data(df)
    manifest = {
        "manifest_version": "2.0",
        "module": str(module),
        "created_at": now_iso(),
        "actor": str(st.session_state.get("current_user", "unknown")),
        "workspace": _safe_workspace()[1],
        "provenance": normalize_provenance(),
        "source_key": source_key,
        "dataset": {
            "rows": int(len(df)), "columns": int(len(df.columns)),
            "sha256": dataframe_digest(df), "profile": profile,
        },
        "parameters": jsonable(parameters or {}),
        "assumptions": jsonable(assumptions or {}),
        "run_id": run_id or st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id"),
        "code_version": str(os.environ.get("GIT_COMMIT") or os.environ.get("SHOIR_GIT_COMMIT") or "runtime"),
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "result_fingerprint": hashlib.sha256(repr(jsonable(result)).encode("utf-8")).hexdigest() if result is not None else "",
        "workflow": list(WORKFLOW_STEPS),
    }
    return manifest


def build_reproducibility_manifest(module: str, *, parameters: Mapping[str, Any] | None = None, scenario: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = evidence_manifest(module, parameters=parameters)
    result["scenario"] = jsonable(scenario or {})
    result["seed"] = st.session_state.get("experiment_seed") or st.session_state.get("mc_seed") or st.session_state.get("seed")
    result["solver"] = st.session_state.get("selected_solver") or st.session_state.get("solver")
    result["environment"] = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    return result


def save_evidence(module: str, name: str, manifest: Mapping[str, Any]) -> str:
    aid = persist_object("evidence", name, manifest)
    st.session_state["shoir_last_evidence_manifest"] = dict(manifest)
    return aid


def uncertainty_summary(values: Sequence[float] | pd.Series | np.ndarray, confidence: float = 0.95, threshold: float | None = None) -> dict[str, Any]:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size == 0:
        return {"n": 0, "mean": None, "std": None, "lower": None, "upper": None, "p10": None, "p50": None, "p90": None, "probability_above": {}}
    alpha = 1.0 - float(confidence)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    se = std / math.sqrt(arr.size) if arr.size > 1 else 0.0
    # Normal approximation is stated as an approximation, not a distributional fact.
    z = 1.96 if abs(confidence - 0.95) < 1e-9 else 1.645 if abs(confidence - 0.90) < 1e-9 else 2.576
    lower = mean - z * se
    upper = mean + z * se
    return {
        "n": int(arr.size), "mean": mean, "std": std, "lower": lower, "upper": upper,
        "p10": float(np.quantile(arr, 0.10)), "p50": float(np.quantile(arr, 0.50)),
        "p90": float(np.quantile(arr, 0.90)), "confidence": float(confidence),
        "probability_above": (
            {str(float(threshold)): float(np.mean(arr > float(threshold)))}
            if threshold is not None else {}
        ),
    }


def monte_carlo_summary(
    distributions: Mapping[str, Mapping[str, float]],
    expression: str,
    *,
    samples: int = 5000,
    seed: int = 2026,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rng = np.random.default_rng(int(seed))
    n = max(100, min(int(samples), 200_000))
    cols: dict[str, np.ndarray] = {}
    for name, spec in distributions.items():
        dist = str(spec.get("distribution", "normal")).lower()
        if dist == "normal":
            cols[name] = rng.normal(float(spec.get("mean", 0)), float(spec.get("std", 1)), n)
        elif dist in {"uniform", "rectangular"}:
            cols[name] = rng.uniform(float(spec.get("low", 0)), float(spec.get("high", 1)), n)
        elif dist in {"triangular", "triangle"}:
            cols[name] = rng.triangular(float(spec.get("low", 0)), float(spec.get("mode", 0.5)), float(spec.get("high", 1)), n)
        elif dist in {"lognormal", "log-normal"}:
            cols[name] = rng.lognormal(float(spec.get("mean", 0)), float(spec.get("sigma", 1)), n)
        else:
            raise ValueError(f"Unsupported distribution: {dist}")
    # Evaluation is intentionally constrained to arithmetic expressions and a
    # small allow-list of NumPy functions; arbitrary Python execution is never
    # accepted from the Monte Carlo expression field.
    import ast
    local = {k: pd.Series(v) for k, v in cols.items()}
    allowed_names = set(local) | {"np"}
    allowed_np = {"abs", "sqrt", "exp", "log", "log10", "minimum", "maximum", "clip"}
    tree = ast.parse(str(expression), mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
                             ast.USub, ast.UAdd, ast.Load, ast.Name, ast.Constant, ast.Call, ast.Attribute)):
            if isinstance(node, ast.Name) and node.id not in allowed_names:
                raise ValueError(f"Unknown expression name: {node.id}")
            if isinstance(node, ast.Attribute):
                if not isinstance(node.value, ast.Name) or node.value.id != "np" or node.attr not in allowed_np:
                    raise ValueError("Only allow-listed np.* functions are permitted.")
            if isinstance(node, ast.Call) and not isinstance(node.func, ast.Attribute):
                raise ValueError("Function calls must use an allow-listed np.* function.")
            continue
        raise ValueError(f"Unsupported expression operation: {type(node).__name__}")
    result = pd.eval(str(expression), local_dict=local, global_dict={"np": np, "__builtins__": {}}, engine="python", parser="python")
    if not isinstance(result, (pd.Series, np.ndarray, np.generic, int, float)):
        raise ValueError("Expression did not produce a numeric result.")
    if isinstance(result, pd.Series):
        y = pd.to_numeric(result, errors="coerce")
    else:
        y = pd.Series(result)
    sample_df = pd.DataFrame(cols)
    sample_df["Result"] = y.to_numpy()
    summary = uncertainty_summary(y.dropna())
    summary.update({"samples": n, "seed": int(seed), "expression": expression})
    return sample_df, summary


def bootstrap_summary(values: Sequence[float] | pd.Series, *, replications: int = 2000, seed: int = 2026) -> dict[str, Any]:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size == 0:
        return {"n": 0, "replications": 0}
    rng = np.random.default_rng(int(seed))
    reps = max(200, min(int(replications), 50_000))
    means = np.empty(reps)
    for i in range(reps):
        means[i] = float(np.mean(rng.choice(arr, size=arr.size, replace=True)))
    u = uncertainty_summary(means)
    u.update({"n": int(arr.size), "replications": reps, "seed": int(seed)})
    return u


def sensitivity_table(
    base_value: float,
    parameter_effects: Mapping[str, float],
    *,
    low: float = -1.0,
    high: float = 1.0,
) -> pd.DataFrame:
    rows = []
    for parameter, effect in parameter_effects.items():
        e = float(effect)
        rows.append({"Parameter": str(parameter), "Low": base_value + e * low, "Base": base_value, "High": base_value + e * high, "Range": abs(e * (high - low))})
    return pd.DataFrame(rows).sort_values("Range", ascending=False, ignore_index=True)


def compare_scenarios(scenarios: Mapping[str, Mapping[str, float]], *, baseline: str | None = None) -> pd.DataFrame:
    if not scenarios:
        return pd.DataFrame()
    names = list(scenarios)
    base_name = baseline if baseline in scenarios else names[0]
    base = pd.Series(scenarios[base_name], dtype=float)
    rows = []
    for name, payload in scenarios.items():
        current = pd.Series(payload, dtype=float)
        all_keys = list(dict.fromkeys([*base.index.tolist(), *current.index.tolist()]))
        for k in all_keys:
            b = float(base.get(k, np.nan)); c = float(current.get(k, np.nan))
            rows.append({
                "Scenario": name, "KPI": k, "Baseline": b, "Value": c,
                "Delta": c - b if np.isfinite(b) and np.isfinite(c) else np.nan,
                "% Change": ((c - b) / b * 100.0) if np.isfinite(b) and np.isfinite(c) and b != 0 else np.nan,
            })
    return pd.DataFrame(rows)


def scenario_record(name: str, values: Mapping[str, float], *, parent: str = "Baseline", assumptions: Mapping[str, Any] | None = None, stress_case: bool = False) -> dict[str, Any]:
    payload = {
        "scenario_id": f"SCN-{uuid.uuid4().hex[:12].upper()}",
        "name": name,
        "parent": parent,
        "values": jsonable(dict(values)),
        "assumptions": jsonable(dict(assumptions or {})),
        "stress_case": bool(stress_case),
        "created_at": now_iso(),
    }
    persist_object("scenario", name, payload)
    attach_project_object("scenario", payload["scenario_id"], name=name, parent=parent)
    return payload


def decision_record(
    title: str,
    *,
    baseline: Mapping[str, Any],
    alternatives: Sequence[Mapping[str, Any]],
    constraints: Sequence[str] = (),
    evidence: Sequence[Mapping[str, Any]] = (),
    uncertainty: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "decision_id": f"DEC-{uuid.uuid4().hex[:12].upper()}",
        "title": title,
        "status": "Draft",
        "baseline": jsonable(dict(baseline)),
        "alternatives": jsonable(list(alternatives)),
        "constraints": jsonable(list(constraints)),
        "evidence": jsonable(list(evidence)),
        "uncertainty": jsonable(dict(uncertainty or {})),
        "approval_required": True,
        "created_at": now_iso(),
    }
    persist_object("decision", title, payload)
    attach_project_object("decision", payload["decision_id"], title=title, status="Draft")
    st.session_state["shoir_latest_decision_id"] = payload["decision_id"]
    st.session_state["shoir_last_decision"] = payload
    return payload


def engineering_story(
    *,
    happened: str,
    why: str,
    change: str,
    what_if: str,
    monitor: str,
    actual: str = "Not yet verified",
) -> dict[str, str]:
    return {
        "What happened?": happened,
        "Why did it happen?": why,
        "What can we change?": change,
        "What happens if we change it?": what_if,
        "What should be monitored?": monitor,
        "What actually happened?": actual,
    }


def visualization_recommendations(df: pd.DataFrame) -> list[dict[str, str]]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return [{"chart": "dataset_profile", "reason": "No data available; show readiness and schema instead."}]
    numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    dates = profile_data(df)["date_columns"]
    categorical = [str(c) for c in df.columns if str(c) not in numeric + dates]
    rec: list[dict[str, str]] = []
    if dates and numeric:
        rec.append({"chart": "time_series", "reason": "Date/time dimension plus numeric measures detected."})
    if len(numeric) >= 2:
        rec.append({"chart": "correlation_heatmap", "reason": "Multiple numeric measures can be compared for association."})
    if categorical and numeric:
        rec.append({"chart": "grouped_summary", "reason": "Categorical dimensions with numeric measures support grouped comparisons."})
    if numeric:
        rec.append({"chart": "distribution", "reason": "Numeric measures support distribution and percentile views."})
    if any("defect" in c.lower() or "quality" in c.lower() for c in df.columns):
        rec.extend([
            {"chart": "pareto", "reason": "Quality/defect fields detected."},
            {"chart": "control_chart", "reason": "Quality context supports process monitoring where ordered data exists."},
        ])
    if any("scenario" in c.lower() or "case" in c.lower() for c in df.columns):
        rec.extend([
            {"chart": "scenario_delta", "reason": "Scenario-like grouping detected."},
            {"chart": "tornado", "reason": "Scenario KPI deltas can be shown as driver ranges."},
        ])
    return rec[:8]


def build_auto_visual(df: pd.DataFrame, recommendation: Mapping[str, str] | None = None):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    rec = (recommendation or {}).get("chart", "")
    numeric = list(df.select_dtypes(include=np.number).columns)
    p = profile_data(df)
    if rec == "time_series" and p["date_columns"] and numeric:
        x = p["date_columns"][0]; y = numeric[0]
        temp = df[[x, y]].copy()
        temp[x] = pd.to_datetime(temp[x], errors="coerce")
        temp = temp.dropna().sort_values(x)
        return px.line(temp, x=x, y=y, markers=True, title=f"{y} over time")
    if rec == "correlation_heatmap" and len(numeric) >= 2:
        corr = df[numeric].corr(numeric_only=True)
        return px.imshow(corr, text_auto=".2f", title="Measure correlation")
    if rec == "grouped_summary":
        categorical = [c for c in df.columns if c not in numeric and c not in p["date_columns"]]
        if categorical and numeric:
            s = df.groupby(categorical[0])[numeric[0]].mean(numeric_only=True).reset_index()
            return px.bar(s, x=categorical[0], y=numeric[0], title=f"{numeric[0]} by {categorical[0]}")
    if numeric:
        return px.histogram(df, x=numeric[0], title=f"Distribution of {numeric[0]}")
    return None


def forecast_operations(df: pd.DataFrame, *, target: str | None = None, horizon: int = 7) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = df.copy(deep=True)
    if data.empty:
        return pd.DataFrame(), {"status": "No data"}
    p = profile_data(data)
    target = target or next((c for c in p["numeric_columns"] if any(k in c.lower() for k in ("demand", "sales", "qty", "volume", "output"))), p["numeric_columns"][0] if p["numeric_columns"] else None)
    if not target:
        return pd.DataFrame(), {"status": "No numeric target detected"}
    y = pd.to_numeric(data[target], errors="coerce").dropna().reset_index(drop=True)
    if y.empty:
        return pd.DataFrame(), {"status": "Target contains no numeric observations", "target": target}
    window = min(12, max(3, len(y) // 4))
    baseline = float(y.tail(window).mean())
    residual = y - y.rolling(window).mean()
    sigma = float(residual.dropna().std(ddof=1)) if residual.dropna().size > 1 else float(y.std(ddof=1) or 0.0)
    rows = []
    last_idx = len(y)
    for h in range(1, max(1, int(horizon)) + 1):
        rows.append({
            "Horizon": h, "P50": baseline, "P80": baseline + 1.2816 * sigma,
            "P95": baseline + 1.6449 * sigma, "Lower": baseline - 1.6449 * sigma,
        })
    pred = pd.DataFrame(rows)
    return pred, {
        "status": "Completed",
        "target": target,
        "model": f"Rolling-{window} baseline with residual interval approximation",
        "MAE": float(np.mean(np.abs(y.tail(window) - baseline))) if len(y) >= window else float("nan"),
        "RMSE": float(np.sqrt(np.mean((y.tail(window) - baseline) ** 2))) if len(y) >= window else float("nan"),
        "Bias": float(np.mean(y.tail(window) - baseline)) if len(y) >= window else float("nan"),
        "drift": float(y.tail(window).mean() - y.head(min(window, len(y))).mean()),
    }


def optimization_diagnostics(result: Any) -> dict[str, Any]:
    """Extract transparent optimization diagnostics from common result envelopes."""
    payload: dict[str, Any] = result if isinstance(result, Mapping) else {}
    candidates = payload.get("solver", payload)
    out = {
        "objective": candidates.get("objective") if isinstance(candidates, Mapping) else None,
        "status": candidates.get("status") if isinstance(candidates, Mapping) else None,
        "feasible": candidates.get("feasible") if isinstance(candidates, Mapping) else None,
        "optimality": candidates.get("optimality") if isinstance(candidates, Mapping) else None,
        "gap": candidates.get("gap") if isinstance(candidates, Mapping) else None,
        "runtime_ms": candidates.get("runtime_ms") if isinstance(candidates, Mapping) else None,
        "solver": candidates.get("name") or candidates.get("solver") if isinstance(candidates, Mapping) else None,
        "binding_constraints": candidates.get("binding_constraints", []) if isinstance(candidates, Mapping) else [],
        "shadow_prices": candidates.get("shadow_prices", {}) if isinstance(candidates, Mapping) else {},
    }
    if str(out["status"]).lower() in {"infeasible", "undefined", "unbounded"}:
        out["infeasibility_analysis"] = "Model reports no feasible optimum; inspect binding constraints, bounds and target relaxation."
    return out


def formula_registry() -> list[dict[str, Any]]:
    return [
        {"name": "OEE", "formula": "Availability × Performance × Quality", "unit": "%", "inputs": ["Availability %", "Performance %", "Quality %"], "valid_range": "0..100%"},
        {"name": "Utilization", "formula": "Loaded time / Available time", "unit": "%", "inputs": ["Loaded time", "Available time"], "valid_range": "0..100%+"},
        {"name": "Throughput", "formula": "Completed units / Time", "unit": "units/time", "inputs": ["Completed units", "Time"], "valid_range": "non-negative"},
        {"name": "Little's Law", "formula": "WIP = Throughput × Flow time", "unit": "units", "inputs": ["Throughput", "Flow time"], "valid_range": "non-negative"},
        {"name": "Safety Stock", "formula": "z × demand_std × sqrt(lead_time)", "unit": "units", "inputs": ["service z", "demand std", "lead time"], "valid_range": "non-negative"},
        {"name": "NPV", "formula": "Σ(CFt / (1+r)^t) + initial investment", "unit": "currency", "inputs": ["Cash flows", "Discount rate"], "valid_range": "rate ≠ -1"},
        {"name": "CO2e Intensity", "formula": "CO2e / Functional unit", "unit": "tCO2e/unit", "inputs": ["CO2e", "Functional unit"], "valid_range": "non-negative"},
    ]


def check_numeric_sanity(df: pd.DataFrame, numeric_columns: Iterable[str]) -> pd.DataFrame:
    rows = []
    for col in numeric_columns:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        finite = np.isfinite(s.dropna().to_numpy(dtype=float))
        values = s.dropna()
        rows.append({
            "Measure": str(col), "Finite": bool(finite.all()) if values.size else True,
            "Min": float(values.min()) if not values.empty else np.nan,
            "Max": float(values.max()) if not values.empty else np.nan,
            "Mean": float(values.mean()) if not values.empty else np.nan,
            "Negative values": int((values < 0).sum()) if not values.empty else 0,
            "Zero values": int((values == 0).sum()) if not values.empty else 0,
            "Status": "PASS" if values.empty or bool(finite.all()) else "REVIEW",
        })
    return pd.DataFrame(rows)


def verification_report(df: pd.DataFrame, result: Any = None) -> dict[str, Any]:
    profile = profile_data(df)
    checks = [
        ("Inputs present", profile["rows"] > 0),
        ("Unique columns", len(df.columns) == len(set(map(str, df.columns))) if isinstance(df, pd.DataFrame) else False),
        ("Numeric sanity", bool(check_numeric_sanity(df, profile["numeric_columns"])["Finite"].all()) if profile["numeric_columns"] else True),
        ("No blocking missingness", profile["missing_pct"] <= 25.0),
    ]
    if isinstance(result, Mapping):
        if "status" in result:
            checks.append(("Engine status", str(result.get("status")).lower() not in {"error", "failed"}))
        if "feasible" in result:
            checks.append(("Feasible", bool(result.get("feasible"))))
    passed = sum(1 for _, ok in checks if ok)
    return {
        "status": "PASS" if passed == len(checks) else "REVIEW",
        "passed": passed, "total": len(checks),
        "checks": [{"Check": name, "Status": "PASS" if ok else "REVIEW"} for name, ok in checks],
    }



def factorial_design(factors: Mapping[str, Sequence[Any]]) -> pd.DataFrame:
    """Create a full-factorial design with deterministic ordering."""
    if not factors:
        return pd.DataFrame()
    names = list(factors)
    levels = [list(factors[name]) for name in names]
    if any(len(x) == 0 for x in levels):
        raise ValueError("Every factor needs at least one level.")
    rows = []
    for combo in __import__("itertools").product(*levels):
        rows.append({name: value for name, value in zip(names, combo)})
    return pd.DataFrame(rows)


def effect_sizes(df: pd.DataFrame, factor: str, response: str) -> pd.DataFrame:
    if factor not in df.columns or response not in df.columns:
        return pd.DataFrame()
    groups = []
    for level, sub in df.groupby(factor, dropna=False):
        y = pd.to_numeric(sub[response], errors="coerce").dropna()
        groups.append({"Level": str(level), "N": len(y), "Mean": y.mean(), "Std": y.std(ddof=1)})
    out = pd.DataFrame(groups)
    if out.empty:
        return out
    grand = pd.to_numeric(df[response], errors="coerce").dropna().mean()
    out["Effect vs grand"] = out["Mean"] - grand
    if len(out) == 2:
        a = pd.to_numeric(df.loc[df[factor].astype(str) == str(out.iloc[0]["Level"]), response], errors="coerce").dropna()
        b = pd.to_numeric(df.loc[df[factor].astype(str) == str(out.iloc[1]["Level"]), response], errors="coerce").dropna()
        pooled = math.sqrt(((len(a)-1)*a.var(ddof=1) + (len(b)-1)*b.var(ddof=1)) / max(1, len(a)+len(b)-2))
        out["Cohen_d_vs_next"] = ((a.mean()-b.mean())/pooled) if pooled > 0 else np.nan
    return out


def holm_adjust(pvalues: Sequence[float]) -> np.ndarray:
    p = np.asarray(pd.to_numeric(pd.Series(pvalues), errors="coerce"), dtype=float)
    out = np.full_like(p, np.nan)
    valid = np.where(np.isfinite(p))[0]
    order = valid[np.argsort(p[valid])]
    m = len(order)
    running = 0.0
    for rank, idx in enumerate(order):
        adjusted = min(1.0, (m-rank) * p[idx])
        running = max(running, adjusted)
        out[idx] = running
    return out


def approximate_power(effect_size: float, n_per_group: int, alpha: float = 0.05) -> float:
    """Two-sided normal approximation for planning only."""
    from scipy.stats import norm
    n = max(2, int(n_per_group))
    z_alpha = float(norm.ppf(1.0 - alpha / 2.0))
    noncentral = abs(float(effect_size)) * math.sqrt(n / 2.0)
    return float(norm.cdf(noncentral - z_alpha) + norm.cdf(-noncentral - z_alpha))


def residual_diagnostics(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, Any]:
    a = pd.to_numeric(pd.Series(actual), errors="coerce")
    f = pd.to_numeric(pd.Series(predicted), errors="coerce")
    mask = a.notna() & f.notna()
    a, f = a[mask], f[mask]
    if a.empty:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "residual_std": None}
    r = a.to_numpy(dtype=float) - f.to_numpy(dtype=float)
    return {
        "n": int(len(r)),
        "mae": float(np.mean(np.abs(r))),
        "rmse": float(np.sqrt(np.mean(r**2))),
        "bias": float(np.mean(r)),
        "residual_std": float(np.std(r, ddof=1)) if len(r) > 1 else 0.0,
    }


def schema_drift(current: pd.DataFrame, previous: pd.DataFrame) -> dict[str, Any]:
    cur = [str(x) for x in getattr(current, "columns", [])]
    prev = [str(x) for x in getattr(previous, "columns", [])]
    added = [x for x in cur if x not in prev]
    removed = [x for x in prev if x not in cur]
    common = [x for x in cur if x in prev]
    dtype_changes = []
    for c in common:
        if str(current[c].dtype) != str(previous[c].dtype):
            dtype_changes.append({"Column": c, "Current": str(current[c].dtype), "Previous": str(previous[c].dtype)})
    return {"status": "DRIFT" if added or removed or dtype_changes else "STABLE", "added": added, "removed": removed, "dtype_changes": dtype_changes}


def deep_data_quality(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    rows = []
    profile = profile_data(df)
    for check, status, detail in [
        ("Duplicate columns", "PASS" if len(df.columns) == len(set(map(str, df.columns))) else "REVIEW", str(len(df.columns)-len(set(map(str, df.columns))))),
        ("Duplicate rows", "PASS" if profile["duplicate_rows"] == 0 else "REVIEW", f"{profile['duplicate_rows']:,}"),
        ("Missing cells", "PASS" if profile["missing_cells"] == 0 else "REVIEW", f"{profile['missing_cells']:,}"),
        ("Constant columns", "PASS" if not profile["constant_columns"] else "INFO", ", ".join(profile["constant_columns"]) or "None"),
        ("ID-like columns", "INFO", ", ".join(profile["id_columns"]) or "None detected"),
        ("Date/time columns", "INFO", ", ".join(profile["date_columns"]) or "None detected"),
    ]:
        rows.append({"Check": check, "Status": status, "Detail": detail})
    return pd.DataFrame(rows)


def benchmark_snapshot(actual: Mapping[str, float], benchmark: Mapping[str, float]) -> pd.DataFrame:
    keys = list(dict.fromkeys([*actual.keys(), *benchmark.keys()]))
    rows = []
    for k in keys:
        a = float(actual.get(k, np.nan)); b = float(benchmark.get(k, np.nan))
        rows.append({"KPI": str(k), "Observed": a, "Benchmark": b, "Delta": a-b if np.isfinite(a) and np.isfinite(b) else np.nan,
                     "% vs benchmark": ((a-b)/b*100.0) if np.isfinite(a) and np.isfinite(b) and b != 0 else np.nan})
    return pd.DataFrame(rows)


def render_alerts() -> None:
    with st.expander("Industrial Alerts", expanded=False):
        df, _ = active_dataframe()
        if df.empty:
            st.info("Alerts require observed data or connector telemetry.")
            return
        nums = list(df.select_dtypes(include=np.number).columns[:8])
        if not nums:
            st.info("No numeric signals available for threshold rules.")
            return
        col = st.selectbox("Signal", nums, key="shoir_os_alert_signal")
        threshold = st.number_input("Attention threshold", value=float(pd.to_numeric(df[col], errors="coerce").median() if pd.to_numeric(df[col], errors="coerce").notna().any() else 0.0), key="shoir_os_alert_threshold")
        greater = st.checkbox("Alert when value is above threshold", value=True, key="shoir_os_alert_greater")
        s = pd.to_numeric(df[col], errors="coerce")
        hits = df[s.gt(threshold) if greater else s.lt(threshold)]
        if hits.empty:
            st.success("No rows currently violate the configured rule.")
        else:
            st.warning(f"{len(hits):,} observed row(s) match the alert rule.")
            st.dataframe(hits.head(250), use_container_width=True, hide_index=True)

def module_self_diagnostics(allowed_modules: Sequence[str]) -> pd.DataFrame:
    df, _ = active_dataframe()
    checks = profile_data(df)
    rows = [
        {"System": "Application", "Status": "PASS", "Detail": "Streamlit runtime is executing."},
        {"System": "Dataset", "Status": "PASS" if checks["rows"] else "REVIEW", "Detail": f"{checks['rows']:,} rows in active dataset."},
        {"System": "Visualization", "Status": "PASS" if df.empty or checks["numeric_columns"] else "REVIEW", "Detail": f"{len(checks['numeric_columns'])} numeric measure(s)."},
        {"System": "Module catalog", "Status": "PASS" if allowed_modules else "REVIEW", "Detail": f"{len(allowed_modules)} modules exposed."},
    ]
    try:
        from shoir_enterprise_layer import durable_backend_configured
        remote = bool(durable_backend_configured())
        rows.append({"System": "Durable database", "Status": "PASS" if remote else "FOUNDATION", "Detail": "Remote/PostgreSQL path configured." if remote else "SQLite/local fallback is active."})
    except Exception:
        rows.append({"System": "Durable database", "Status": "FOUNDATION", "Detail": "Enterprise persistence layer not resolved in this runtime."})
    try:
        from shoir_enterprise_layer import connector_health_frame
        username, workspace = _safe_workspace()
        ch = connector_health_frame(username, workspace)
        rows.append({"System": "Connectors", "Status": "PASS" if not ch.empty else "FOUNDATION", "Detail": f"{len(ch)} connector health record(s)."})
    except Exception:
        rows.append({"System": "Connectors", "Status": "FOUNDATION", "Detail": "No persisted connector health records yet."})
    try:
        from shoir_enterprise_layer import list_jobs
        username, workspace = _safe_workspace()
        jobs = list_jobs(username, workspace=workspace, limit=20)
        rows.append({"System": "Background jobs", "Status": "PASS" if not jobs.empty else "FOUNDATION", "Detail": f"{len(jobs)} recent job(s)."})
    except Exception:
        rows.append({"System": "Background jobs", "Status": "FOUNDATION", "Detail": "Job history not available in this runtime."})
    return pd.DataFrame(rows)


def problem_solver(prompt: str, modules: Sequence[str]) -> dict[str, Any]:
    p = str(prompt or "").strip().lower()
    # Operational intent mapping is deterministic and explainable. It is a
    # routing aid, not a quality ranking of modules.
    intent_terms = {
        "Reduce Cost": ("cost", "expense", "opex", "capex", "save"),
        "Increase Throughput": ("throughput", "capacity", "output", "bottleneck", "limited machine"),
        "Improve Quality": ("quality", "defect", "scrap", "yield", "cpk", "variation"),
        "Reduce Inventory": ("inventory", "stock", "safety stock", "stockout", "wip"),
        "Improve Delivery": ("late order", "late orders", "delivery", "due date", "on time", "service level", "orders"),
        "Reduce Downtime": ("downtime", "breakdown", "availability", "maintenance"),
        "Optimize Workforce": ("workforce", "staffing", "operator", "labor", "headcount", "shift"),
        "Reduce Energy": ("energy", "electricity", "kwh", "power"),
        "Reduce Carbon": ("carbon", "co2", "emission", "emissions"),
        "Design Facility": ("facility", "layout", "warehouse design", "material flow"),
        "Improve Reliability": ("reliability", "failure", "mtbf", "mttr"),
        "Analyze Investment": ("investment", "npv", "irr", "payback", "business case"),
        "Conduct Research": ("research", "hypothesis", "experiment", "study", "statistical", "anova"),
    }
    scored_goals = []
    for goal, terms in intent_terms.items():
        score = sum(1 for term in terms if term in p)
        if score:
            scored_goals.append((score, goal))
    # Prefer a delivery interpretation when both "orders" and capacity
    # limitations appear; this mirrors the actual engineering problem framing.
    if "orders" in p and any(x in p for x in ("late", "due", "delivery")):
        goal = "Improve Delivery"
    elif scored_goals:
        scored_goals.sort(key=lambda item: (-item[0], item[1]))
        goal = scored_goals[0][1]
    else:
        goal = "Analyze an industrial problem"

    candidates: list[tuple[int, str]] = []
    for name in modules:
        n = str(name).lower()
        score = 0
        for aliases in DOMAIN_ALIASES.values():
            hits = sum(1 for term in aliases if term in p and term in n)
            score += hits
        if score:
            candidates.append((score, str(name)))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    workflow = PROBLEM_WORKFLOWS.get(goal, ["Data Quality", "Method Selection", "Scenario Analysis", "Decision Center", "Verification"])
    required = ["objective", "data", "constraints", "baseline", "target"]
    if goal in {"Improve Delivery", "Increase Throughput"}:
        required += ["orders / demand", "capacity calendar"]
    elif goal == "Analyze Investment":
        required += ["cash flows", "discount rate"]
    elif goal == "Conduct Research":
        required += ["protocol", "variables", "response definition"]
    return {
        "goal": goal,
        "workflow": workflow,
        "module_hints": [name for _, name in candidates[:8]],
        "required_signals": required,
    }


def roi_snapshot(baseline: Mapping[str, float], post: Mapping[str, float]) -> dict[str, float]:
    keys = sorted(set(baseline) | set(post))
    out: dict[str, float] = {}
    for k in keys:
        b = float(baseline.get(k, np.nan)); p = float(post.get(k, np.nan))
        if np.isfinite(b) and np.isfinite(p):
            out[str(k)] = p - b
    return out


def connector_contracts() -> pd.DataFrame:
    systems = [
        ("Excel/CSV", "file", "import/export"),
        ("SQL", "database", "fetch/push"),
        ("REST", "http", "fetch/push"),
        ("SAP", "erp", "adapter"),
        ("Oracle", "erp", "adapter"),
        ("MES", "industrial", "adapter"),
        ("WMS", "industrial", "adapter"),
        ("ERP", "industrial", "adapter"),
        ("MQTT", "iot", "telemetry"),
        ("OPC-UA", "industrial", "telemetry"),
        ("SFTP", "file", "fetch/push"),
        ("IoT", "iot", "telemetry"),
    ]
    return pd.DataFrame([
        {"Connector": n, "Type": t, "Contract": op, "Status": "Adapter contract" if t not in {"file"} else "Supported", "Secret policy": "Reference only"} for n, t, op in systems
    ])


def kpi_registry() -> pd.DataFrame:
    rows = []
    for item in formula_registry():
        rows.append({
            "KPI": item["name"], "Definition": item["formula"], "Unit": item["unit"],
            "Direction": "Higher is better" if item["name"] in {"OEE", "Utilization", "Throughput"} else "Context dependent",
            "Target": "Project-defined", "Threshold": "Project-defined", "Source": "Governed calculation/measurement",
            "Frequency": "Project-defined", "Verification": "Input + dimensional + regression checks",
        })
    rows.extend([
        {"KPI": "Decision Regret", "Definition": "Outcome penalty relative to the selected reference decision.", "Unit": "normalized", "Direction": "Lower is better", "Target": "Project-defined", "Threshold": "Project-defined", "Source": "Experiment / Decision Center", "Frequency": "Run", "Verification": "Scenario replay"},
        {"KPI": "Forecast Error", "Definition": "Observed minus predicted response; use MAE/RMSE/Bias as appropriate.", "Unit": "measure unit", "Direction": "Lower absolute error is better", "Target": "Project-defined", "Threshold": "Project-defined", "Source": "Forecast Operations", "Frequency": "Forecast cycle", "Verification": "Backtest"},
    ])
    return pd.DataFrame(rows)



def template_catalog() -> pd.DataFrame:
    return pd.DataFrame(INDUSTRIAL_TEMPLATES)


def select_template(name: str) -> dict[str, Any] | None:
    for template in INDUSTRIAL_TEMPLATES:
        if str(template["name"]).strip().lower() == str(name).strip().lower():
            return dict(template)
    return None


def workspace_mode() -> str:
    mode = str(st.session_state.get("shoir_view_mode", "Engineer")).strip()
    return mode if mode in {"Engineer", "Manager", "Executive"} else "Engineer"


def set_localization(language: str) -> None:
    lang = "Arabic" if str(language).lower().startswith("arab") else "English"
    st.session_state["shoir_language"] = lang
    st.session_state["shoir_rtl"] = lang == "Arabic"


def platform_health_snapshot() -> dict[str, Any]:
    username, workspace = _safe_workspace()
    remote = False
    try:
        from shoir_enterprise_layer import durable_backend_configured
        remote = bool(durable_backend_configured())
    except Exception:
        remote = False
    jobs = pd.DataFrame()
    connectors = pd.DataFrame()
    entities = pd.DataFrame()
    try:
        from shoir_enterprise_layer import list_jobs, connector_health_frame, canonical_entities_frame
        jobs = list_jobs(username, workspace=workspace, limit=20)
        connectors = connector_health_frame(username, workspace)
        entities = canonical_entities_frame(username, workspace, limit=300)
    except Exception:
        pass
    return {
        "application": True,
        "database": remote,
        "database_mode": "PostgreSQL/Supabase" if remote else "SQLite/local fallback",
        "jobs": len(jobs),
        "connectors": len(connectors),
        "canonical_entities": len(entities),
        "runtime": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }


def render_templates() -> None:
    with st.expander("Industrial Templates / One-Click Assessments", expanded=False):
        choices = [x["name"] for x in INDUSTRIAL_TEMPLATES]
        choice = st.selectbox("Template", choices, key="shoir_os_template_choice")
        template = select_template(choice)
        if template:
            st.markdown(f"**Goal:** {template['goal']}")
            st.markdown("**Preconfigured workflow:** " + " → ".join(template["modules"]))
            if st.button("Start template", type="primary", key="shoir_os_template_start"):
                st.session_state["shoir_selected_template"] = template
                st.session_state["shoir_problem_goal"] = template["goal"]
                st.success("Template loaded. Existing specialist modules remain the calculation owners.")
            st.dataframe(template_catalog(), use_container_width=True, hide_index=True, height=260)


def render_run_center() -> None:
    with st.expander("Run Center / Background Jobs / Replay", expanded=False):
        username, workspace = _safe_workspace()
        try:
            from shoir_enterprise_layer import list_jobs, request_job_action
            jobs = list_jobs(username, workspace=workspace, limit=50)
        except Exception:
            jobs = pd.DataFrame()
        if jobs.empty:
            st.info("No persisted background jobs are recorded yet.")
        else:
            st.dataframe(jobs, use_container_width=True, hide_index=True, height=260)
            ids = list(jobs.get("job_id", pd.Series(dtype=str)).astype(str))
            if ids:
                job_id = st.selectbox("Run control", ids, key="shoir_os_job_id")
                action = st.selectbox("Action", ["pause", "resume", "cancel"], key="shoir_os_job_action")
                if st.button("Apply run control", key="shoir_os_job_action_button"):
                    result = request_job_action(job_id, action)
                    st.info(str(result))
        manifest = build_reproducibility_manifest(str(st.session_state.get("selected_module", "Engineering")))
        st.download_button(
            "Download reproducibility manifest",
            data=json.dumps(manifest, indent=2, default=str).encode("utf-8"),
            file_name="shoir_reproducibility_manifest.json",
            mime="application/json",
            key="shoir_os_repro_manifest_2",
        )


def render_connector_health() -> None:
    with st.expander("Connector Framework / Health", expanded=False):
        st.dataframe(connector_contracts(), use_container_width=True, hide_index=True, height=280)
        username, workspace = _safe_workspace()
        try:
            from shoir_enterprise_layer import connector_health_frame
            health = connector_health_frame(username, workspace)
        except Exception:
            health = pd.DataFrame()
        if health.empty:
            st.caption("No connector health records are currently persisted. Adapter contracts are ready, but no production endpoint is claimed as connected.")
        else:
            st.dataframe(health, use_container_width=True, hide_index=True, height=220)


def render_security_and_collaboration() -> None:
    with st.expander("Security / Collaboration / Knowledge", expanded=False):
        username, workspace = _safe_workspace()
        left, right = st.columns(2)
        with left:
            comment = st.text_area("Project comment", height=80, key="shoir_os_collab_comment", placeholder="Attach a review note to this project or decision.")
            if st.button("Save review comment", key="shoir_os_collab_save"):
                try:
                    from shoir_enterprise_layer import add_collaboration_item
                    item_id = add_collaboration_item(username, "project", "Platform review", comment, workspace=workspace)
                    st.success(f"Collaboration item {item_id} saved.")
                except Exception as exc:
                    st.warning(f"Collaboration service unavailable: {type(exc).__name__}: {exc}")
            st.caption("Comments are scoped to the current workspace and use the existing enterprise collaboration layer.")
        with right:
            query = st.text_input("Search approved knowledge", key="shoir_os_knowledge_q")
            if query.strip():
                try:
                    from shoir_enterprise_layer import search_knowledge
                    result = search_knowledge(username, query, workspace=workspace)
                    st.write(result)
                except Exception as exc:
                    st.info(f"Knowledge search unavailable: {type(exc).__name__}: {exc}")


def build_presentation_package(module: str) -> bytes:
    """Build a portable executive/engineering evidence ZIP."""
    import io
    import zipfile
    from pptx import Presentation
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    df, _ = active_dataframe()
    manifest = build_reproducibility_manifest(module)
    profile = profile_data(df)
    story = engineering_story(
        happened="See the measured KPI and active result tables.",
        why="Use the evidence trace and data profile to inspect drivers.",
        change="Compare governed scenarios and constraints.",
        what_if="Stress-test assumptions with the scenario / uncertainty tools.",
        monitor="Track the decision KPI and verification outcome.",
    )

    ppt = io.BytesIO()
    prs = Presentation()
    slides = [
        ("Shoir-IE Executive Summary", f"{module}\nGenerated {now_iso()}"),
        ("Data & Readiness", json.dumps(profile, indent=2, default=str)[:3500]),
        ("Industrial Story", "\n".join(f"{k}: {v}" for k, v in story.items())),
        ("Reproducibility", json.dumps(manifest, indent=2, default=str)[:3500]),
    ]
    for title, body in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    prs.save(ppt)

    pdf = io.BytesIO()
    page = canvas.Canvas(pdf, pagesize=A4)
    width, height = A4
    y = height - 48
    page.setFont("Helvetica-Bold", 16)
    page.drawString(40, y, f"Shoir-IE Evidence Pack · {module}")
    y -= 28
    page.setFont("Helvetica", 9)
    lines = [
        f"Generated: {now_iso()}",
        f"Provenance: {manifest.get('provenance')}",
        f"Rows: {profile.get('rows', 0):,} · Columns: {profile.get('columns', 0):,}",
        f"Readiness: {profile.get('readiness', 0):.1f}%",
        f"Dataset SHA-256: {manifest.get('dataset', {}).get('sha256')}",
        "",
        "Engineering Story:",
        *[f"{k}: {v}" for k, v in story.items()],
    ]
    for line in lines:
        if y < 58:
            page.showPage(); y = height - 48; page.setFont("Helvetica", 9)
        page.drawString(40, y, str(line)[:145])
        y -= 14
    page.save()

    xlsx = io.BytesIO()
    with pd.ExcelWriter(xlsx, engine="xlsxwriter") as writer:
        pd.DataFrame([profile]).to_excel(writer, sheet_name="Data Profile", index=False)
        kpi_registry().to_excel(writer, sheet_name="KPI Registry", index=False)
        pd.DataFrame(formula_registry()).to_excel(writer, sheet_name="Formula Registry", index=False)
        pd.DataFrame([manifest]).to_excel(writer, sheet_name="Evidence Manifest", index=False)

    index = {
        "package_version": "1.0",
        "module": module,
        "files": ["presentation.pptx", "evidence.pdf", "evidence.xlsx", "manifest.json"],
        "generated_at": now_iso(),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("presentation.pptx", ppt.getvalue())
        z.writestr("evidence.pdf", pdf.getvalue())
        z.writestr("evidence.xlsx", xlsx.getvalue())
        z.writestr("manifest.json", json.dumps({**manifest, "index": index}, indent=2, default=str))
    return out.getvalue()


def render_presentation_report() -> None:
    with st.expander("Presentation / Report Center", expanded=False):
        module = str(st.session_state.get("selected_module", "Engineering"))
        manifest = build_reproducibility_manifest(module)
        st.markdown("**Executive narrative**")
        for step in ("Executive Summary", "Problem", "Baseline", "Scenario comparison", "Key drivers", "Risk / uncertainty", "Evidence"):
            st.markdown(f"**{step}** — {module} workspace evidence is available in the current project/run context.")
        st.download_button(
            "Download PPTX + PDF + Excel evidence pack",
            data=build_presentation_package(module),
            file_name=f"shoir_{re.sub(r'[^A-Za-z0-9]+','_',module).lower()}_evidence_pack.zip",
            mime="application/zip",
            key="shoir_os_presentation_pack",
        )
        st.download_button(
            "JSON audit/evidence pack",
            data=json.dumps(manifest, indent=2, default=str).encode("utf-8"),
            file_name=f"shoir_{re.sub(r'[^A-Za-z0-9]+','_',module).lower()}_evidence.json",
            mime="application/json",
            key="shoir_os_audit_pack",
        )


def render_modes_and_localization() -> None:
    with st.expander("Experience Modes / Localization / Accessibility", expanded=False):
        a, b, c = st.columns(3)
        with a:
            mode = st.selectbox("Information density", ["Engineer", "Manager", "Executive"], index=["Engineer", "Manager", "Executive"].index(workspace_mode()), key="shoir_os_mode")
            st.session_state["shoir_view_mode"] = mode
        with b:
            language = st.selectbox("Language", ["English", "Arabic"], index=0 if not st.session_state.get("shoir_rtl") else 1, key="shoir_os_language")
            set_localization(language)
        with c:
            reduced = st.checkbox("Reduced motion", value=bool(st.session_state.get("shoir_reduced_motion", False)), key="shoir_os_reduced_motion")
            st.session_state["shoir_reduced_motion"] = reduced
        if st.session_state.get("shoir_rtl"):
            st.markdown("<style>.shoir-os-canvas,.shoir-os-canvas *{direction:rtl;text-align:right}.shoir-os-panel{text-align:right}</style>", unsafe_allow_html=True)
        st.caption("Engineer exposes the full workflow; Manager emphasizes KPI/scenario/decision; Executive emphasizes impact/risk/status. Arabic applies RTL to the platform surface; specialist text is shown in its authored language unless separately localized.")

def render_capability_status() -> None:
    df = core_capability_ledger()
    if df.empty:
        st.info("Capability matrix is not loaded.")
        return
    counts = df["Status"].value_counts().reindex(CAPABILITY_STATES, fill_value=0)
    cols = st.columns(4)
    for idx, status in enumerate(CAPABILITY_STATES):
        with cols[idx]:
            st.metric(status, int(counts[status]))
    q = st.text_input("Search capability status", key="shoir_os_capability_search", placeholder="scenario, data, optimization, security…")
    shown = df[df["Capability"].astype(str).str.contains(q, case=False, na=False)] if q.strip() else df
    st.dataframe(shown, use_container_width=True, hide_index=True, height=320)


def render_project_workspace() -> None:
    project = active_project()
    with st.expander("Project Workspace", expanded=project is not None):
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Project name", value=str(project and project.get("name") or st.session_state.get("shoir_project_name") or ""), key="shoir_os_project_name")
            objective = st.text_input("Objective", value=str(project and project.get("objective") or ""), key="shoir_os_project_objective")
        with c2:
            problem = st.text_input("Problem statement", value=str(project and project.get("problem_statement") or ""), key="shoir_os_project_problem")
            scope = st.text_input("Scope", value=str(project and project.get("scope") or ""), key="shoir_os_project_scope")
        with c3:
            if st.button("Create / Save Project", type="primary", key="shoir_os_project_save"):
                if name.strip():
                    create_project(name, objective, problem, scope)
                    st.success("Project workspace saved.")
        if project:
            st.caption(f"Project {project.get('project_id', '—')} · {project.get('status', 'Active')} · updated {project.get('updated_at', '—')}")
            counts = {k: len(project.get(k, [])) for k in ("datasets", "models", "experiments", "scenarios", "runs", "decisions")}
            st.dataframe(pd.DataFrame([counts]), use_container_width=True, hide_index=True)


def render_scenario_lab() -> None:
    df, _ = active_dataframe()
    with st.expander("Scenario Laboratory", expanded=False):
        st.caption("Create governed scenarios, quantify deltas, and keep uncertainty visible.")
        cols = st.columns(4)
        with cols[0]:
            scenario_name = st.text_input("Scenario name", "Scenario A", key="shoir_os_scenario_name")
            parent = st.text_input("Parent", "Baseline", key="shoir_os_scenario_parent")
        with cols[1]:
            kpi_names = list(df.select_dtypes(include=np.number).columns[:4]) if not df.empty else ["KPI"]
            kpi = st.selectbox("KPI", kpi_names, key="shoir_os_scenario_kpi")
            value = st.number_input("Value", value=0.0, key="shoir_os_scenario_value")
        with cols[2]:
            stress = st.checkbox("Stress case", key="shoir_os_scenario_stress")
            assumption = st.text_input("Assumption note", key="shoir_os_scenario_assumption")
        with cols[3]:
            if st.button("Save Scenario", type="primary", key="shoir_os_scenario_save"):
                record = scenario_record(scenario_name, {kpi: value}, parent=parent, assumptions={"note": assumption}, stress_case=stress)
                st.success(f"Saved {record['scenario_id']}.")
        scenarios = list_persisted_objects("scenario", limit=50)
        if not scenarios.empty:
            with st.expander("Scenario records", expanded=False):
                st.dataframe(scenarios, use_container_width=True, hide_index=True)


def render_experiment_lab() -> None:
    with st.expander("Experiment & Uncertainty Engine", expanded=False):
        st.caption("Deterministic seeds, Monte Carlo, bootstrap, sensitivity and experiment records share one evidence lifecycle.")
        mode = st.selectbox("Method", ["Monte Carlo", "Bootstrap", "Sensitivity", "Full Factorial DOE", "Power / Effect Size"], key="shoir_os_exp_mode")
        seed = int(st.number_input("Seed", min_value=0, max_value=2_000_000_000, value=2026, step=1, key="shoir_os_exp_seed"))
        if mode == "Monte Carlo":
            mean = st.number_input("Mean", value=100.0, key="shoir_os_mc_mean")
            std = st.number_input("Std dev", min_value=0.0, value=10.0, key="shoir_os_mc_std")
            threshold = st.number_input("Constraint threshold (optional)", value=120.0, key="shoir_os_mc_threshold")
            samples = int(st.number_input("Samples", min_value=100, max_value=100_000, value=5000, step=100, key="shoir_os_mc_samples"))
            if st.button("Run Monte Carlo", type="primary", key="shoir_os_mc_run"):
                sim, summary = monte_carlo_summary(
                    {"X": {"distribution": "normal", "mean": mean, "std": std}},
                    "X",
                    samples=samples,
                    seed=seed,
                )
                summary["probability_above"] = {str(float(threshold)): float((sim["Result"] > threshold).mean())}
                st.session_state["shoir_os_mc_last"] = sim
                st.session_state["shoir_os_mc_summary"] = summary
        elif mode == "Bootstrap":
            df, _ = active_dataframe()
            nums = list(df.select_dtypes(include=np.number).columns) if not df.empty else []
            if not nums:
                st.info("Bootstrap needs at least one numeric measure.")
            else:
                col = st.selectbox("Measure", nums, key="shoir_os_boot_col")
                reps = int(st.number_input("Replications", 200, 10000, 2000, 200, key="shoir_os_boot_reps"))
                if st.button("Bootstrap mean", key="shoir_os_boot_run"):
                    st.session_state["shoir_os_boot_summary"] = bootstrap_summary(df[col], replications=reps, seed=seed)
        elif mode == "Full Factorial DOE":
            factors_text = st.text_area("Factors (Factor=level1,level2 per line)", value="Speed=10,20\nFeed=1,2", key="shoir_os_doe_factors")
            if st.button("Build factorial design", key="shoir_os_doe_run"):
                factors = {}
                for line in factors_text.splitlines():
                    if "=" not in line:
                        continue
                    name, values = line.split("=", 1)
                    factors[name.strip()] = [x.strip() for x in values.split(",") if x.strip()]
                try:
                    st.session_state["shoir_os_doe_design"] = factorial_design(factors)
                except ValueError as exc:
                    st.error(str(exc))
            if isinstance(st.session_state.get("shoir_os_doe_design"), pd.DataFrame):
                st.dataframe(st.session_state["shoir_os_doe_design"], use_container_width=True, hide_index=True)
                if st.button("Save experiment design", key="shoir_os_doe_save"):
                    persist_object("experiment", "Factorial DOE", {
                        "design": st.session_state["shoir_os_doe_design"].to_dict("records"),
                        "seed": seed, "created_at": now_iso(),
                    })
                    st.success("Experiment design saved.")
        elif mode == "Power / Effect Size":
            effect = st.number_input("Expected standardized effect (Cohen d)", value=0.5, key="shoir_os_power_effect")
            n_group = st.number_input("Replications per group", min_value=2, max_value=100000, value=20, key="shoir_os_power_n")
            alpha = st.number_input("Alpha", min_value=0.001, max_value=0.2, value=0.05, key="shoir_os_power_alpha")
            power = approximate_power(effect, int(n_group), alpha)
            st.metric("Approx. power", f"{power:.1%}")
        else:
            base = st.number_input("Base value", value=100.0, key="shoir_os_sens_base")
            effects_text = st.text_area("Parameter effects (name=value per line)", value="Capacity=8\nDemand=-4\nDowntime=-6", key="shoir_os_sens_effects")
            if st.button("Build sensitivity table", key="shoir_os_sens_run"):
                effects = {}
                for line in effects_text.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        try:
                            effects[k.strip()] = float(v.strip())
                        except ValueError:
                            pass
                st.session_state["shoir_os_sens_last"] = sensitivity_table(base, effects)
        if st.session_state.get("shoir_os_mc_summary"):
            st.json(st.session_state["shoir_os_mc_summary"])
        if st.session_state.get("shoir_os_boot_summary"):
            st.json(st.session_state["shoir_os_boot_summary"])
        if isinstance(st.session_state.get("shoir_os_sens_last"), pd.DataFrame):
            st.dataframe(st.session_state["shoir_os_sens_last"], use_container_width=True, hide_index=True)
        df, _ = active_dataframe()
        if not df.empty:
            recs = visualization_recommendations(df)
            st.caption("Recommended visual evidence")
            st.write(" · ".join(r["chart"] for r in recs[:5]))


def render_control_tower() -> None:
    df, source = active_dataframe()
    profile = profile_data(df)
    with st.expander("Industrial Control Tower", expanded=False):
        st.caption("Observed signals only. Missing live telemetry is not replaced with invented values.")
        if df.empty:
            st.info("Control Tower is waiting for an active dataset or connected telemetry.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Data readiness", f"{profile['readiness']:.0f}%")
            c2.metric("Rows", f"{profile['rows']:,}")
            c3.metric("Measures", len(profile["numeric_columns"]))
            c4.metric("Provenance", normalize_provenance())
            if profile["warnings"]:
                st.warning(" · ".join(profile["warnings"]))
            st.dataframe(check_numeric_sanity(df, profile["numeric_columns"]), use_container_width=True, hide_index=True)


def render_copilot_governance(allowed_modules: Sequence[str]) -> None:
    with st.expander("Ask Shoir • Problem Solver / Copilot Governance", expanded=False):
        prompt = st.text_area(
            "Engineering request",
            placeholder="We have late orders, limited machine capacity and a missing shift calendar.",
            key="shoir_os_problem_prompt",
            height=85,
        )
        if st.button("Build governed plan", type="primary", key="shoir_os_plan"):
            plan = problem_solver(prompt, allowed_modules)
            st.session_state["shoir_os_plan_result"] = plan
        plan = st.session_state.get("shoir_os_plan_result")
        if isinstance(plan, Mapping):
            st.markdown(f"**Goal:** {plan['goal']}")
            st.markdown("**Workflow:** " + " → ".join(plan["workflow"]))
            st.markdown("**Required signals:** " + ", ".join(plan["required_signals"]))
            if plan["module_hints"]:
                st.markdown("**Module hints:** " + ", ".join(plan["module_hints"]))
            st.info("Planning is read/analyze/recommend/prepare only. Operational execution remains separately permission-gated.")


def render_data_intelligence(df: pd.DataFrame) -> None:
    with st.expander("Data Intelligence • KPI Ontology • Formula Registry", expanded=False):
        if df.empty:
            st.info("Load a dataset to activate profile, schema-drift, KPI and formula views.")
            return
        profile = profile_data(df)
        a, b, c = st.columns(3)
        a.metric("Readiness", f"{profile['readiness']:.1f}%")
        b.metric("Missing", f"{profile['missing_pct']:.1f}%")
        c.metric("Duplicate rows", f"{profile['duplicate_pct']:.1f}%")
        st.markdown("**Recommended visualization suite**")
        st.dataframe(pd.DataFrame(visualization_recommendations(df)), use_container_width=True, hide_index=True)
        with st.expander("KPI ontology", expanded=False):
            st.dataframe(kpi_registry(), use_container_width=True, hide_index=True)
        with st.expander("Formula registry", expanded=False):
            st.dataframe(pd.DataFrame(formula_registry()), use_container_width=True, hide_index=True)


def render_platform_health(allowed_modules: Sequence[str]) -> None:
    with st.expander("Shoir-IE Self-Diagnostics • Capability Maturity", expanded=False):
        h = module_self_diagnostics(allowed_modules)
        st.dataframe(h, use_container_width=True, hide_index=True)
        if st.button("Refresh diagnostics", key="shoir_os_refresh_health"):
            st.rerun()
        render_capability_status()


def render_platform_canvas(module: str, allowed_modules: Sequence[str]) -> None:
    df, _ = active_dataframe()
    profile = profile_data(df)
    manifest = module_manifest(module, allowed_modules=allowed_modules)
    prov = normalize_provenance()
    st.markdown(
        f"""
<div class="shoir-os-canvas">
  <div class="shoir-os-header">
    <div><div class="shoir-os-kicker">ENGINEERING CANVAS</div><div class="shoir-os-title">{module}</div></div>
    <div class="shoir-os-badge">{prov} · {manifest['maturity']}</div>
  </div>
  <div class="shoir-os-grid">
    <div class="shoir-os-panel"><b>DATA</b><span>{profile['rows']:,} rows · {profile['columns']:,} cols</span><span>Readiness {profile['readiness']:.1f}%</span></div>
    <div class="shoir-os-panel"><b>MODEL</b><span>{manifest['model']}</span><span>Lifecycle {len(manifest['workflow'])} stages</span></div>
    <div class="shoir-os-panel"><b>KPIs</b><span>{', '.join(manifest.get('kpis', [])[:3]) or 'Module-defined KPIs'}</span><span>Evidence governed</span></div>
    <div class="shoir-os-panel"><b>SCENARIOS</b><span>Baseline → alternatives → stress</span><span>Uncertainty supported</span></div>
    <div class="shoir-os-panel"><b>VISUALIZE</b><span>Auto-recommendation active</span><span>{len(visualization_recommendations(df))} candidate views</span></div>
    <div class="shoir-os-panel"><b>VERIFY</b><span>Contract + sanity + regression</span><span>Run replay metadata</span></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_story_and_roi() -> None:
    with st.expander("Industrial Story • Impact / ROI", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.text_area("What happened?", key="shoir_os_story_happened", height=65)
            st.text_area("Why did it happen?", key="shoir_os_story_why", height=65)
            st.text_area("What can we change?", key="shoir_os_story_change", height=65)
        with c2:
            st.text_area("What happens if we change it?", key="shoir_os_story_whatif", height=65)
            st.text_area("What should be monitored?", key="shoir_os_story_monitor", height=65)
            st.text_area("What actually happened?", key="shoir_os_story_actual", height=65)
        if st.button("Save engineering story", key="shoir_os_story_save"):
            story = engineering_story(
                happened=st.session_state.get("shoir_os_story_happened", ""),
                why=st.session_state.get("shoir_os_story_why", ""),
                change=st.session_state.get("shoir_os_story_change", ""),
                what_if=st.session_state.get("shoir_os_story_whatif", ""),
                monitor=st.session_state.get("shoir_os_story_monitor", ""),
                actual=st.session_state.get("shoir_os_story_actual", "") or "Not yet verified",
            )
            persist_object("engineering_story", "Engineering Story", story)
            st.success("Engineering story saved to the governed artifact layer.")
        st.caption("ROI values should come from measured baselines and verified outcomes, not generic savings claims.")


def render_platform_os_surface(module: str, allowed_modules: Sequence[str]) -> None:
    """Render the complete cross-cutting OS surface after specialist modules."""
    if not st.session_state.get("authenticated"):
        return
    install_css()
    render_platform_canvas(str(module), allowed_modules)
    controls = st.radio(
        "Industrial OS workspace",
        ["Work", "Intelligence", "Governance", "Platform"],
        horizontal=True,
        key="shoir_os_workspace_area",
    )
    views = {
        "Work": ["Project Workspace", "Industrial Templates", "Scenario Laboratory", "Data Intelligence"],
        "Intelligence": ["Problem Solver / Copilot", "Visualization Intelligence", "Forecast Operations", "Digital Thread", "Control Tower", "Alerts / Monitoring"],
        "Governance": ["Decision & Evidence", "Experiment / Uncertainty", "Verification / Replay", "Story / ROI", "Presentation / Reports", "Run Center"],
        "Platform": ["Self-Diagnostics", "Capability Maturity", "Connector Framework", "Formula + KPI Registry", "Security / Collaboration", "Experience / Localization", "Benchmarking"],
    }
    view = st.selectbox("Workspace view", views[controls], key="shoir_os_workspace_view")
    if view == "Project Workspace":
        render_project_workspace()
    elif view == "Scenario Laboratory":
        render_scenario_lab()
    elif view == "Data Intelligence":
        df, _ = active_dataframe(); render_data_intelligence(df)
    elif view == "Problem Solver / Copilot":
        render_copilot_governance(allowed_modules)
    elif view == "Visualization Intelligence":
        df, _ = active_dataframe()
        with st.expander("Visualization Intelligence", expanded=True):
            if df.empty:
                st.info("Load data to receive chart recommendations.")
            else:
                recs = visualization_recommendations(df)
                for rec in recs:
                    st.markdown(f"**{rec['chart']}** — {rec['reason']}")
                fig = build_auto_visual(df, recs[0] if recs else None)
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True, key="shoir_os_auto_visual")
    elif view == "Forecast Operations":
        df, _ = active_dataframe()
        with st.expander("Forecast Operations", expanded=True):
            pred, meta = forecast_operations(df)
            if pred.empty:
                st.info(meta.get("status", "Forecast unavailable."))
            else:
                st.dataframe(pred, use_container_width=True, hide_index=True)
                st.json(meta)
                st.plotly_chart(px.line(pred, x="Horizon", y=["P50", "P80", "P95"], markers=True, title=f"Forecast · {meta['target']}"), use_container_width=True, key="shoir_os_forecast")
    elif view == "Digital Thread":
        with st.expander("Digital Thread", expanded=True):
            df, source = active_dataframe()
            if not df.empty:
                if st.button("Map active dataset into Digital Thread", key="shoir_os_thread_sync", type="primary"):
                    result = sync_dataset_thread(df, source)
                    st.session_state["shoir_os_thread_result"] = result
                result = st.session_state.get("shoir_os_thread_result")
                if result:
                    st.json(result)
            try:
                from shoir_enterprise_layer import canonical_entities_frame, canonical_relationships_frame
                username, workspace = _safe_workspace()
                entities = canonical_entities_frame(username, workspace, limit=300)
                relationships = canonical_relationships_frame(username, workspace, limit=500)
                if entities.empty:
                    st.info("No canonical thread records yet.")
                else:
                    st.dataframe(entities[["entity_type", "name", "source", "status", "updated_at"]], use_container_width=True, hide_index=True)
                    if not relationships.empty:
                        st.caption(f"{len(relationships)} governed relationships")
            except Exception as exc:
                st.info(f"Digital Thread persistence not available: {type(exc).__name__}: {exc}")
    elif view == "Decision & Evidence":
        with st.expander("Decision Center + Evidence", expanded=True):
            st.caption("A decision remains Draft until a user explicitly approves it.")
            title = st.text_input("Decision title", "Engineering Decision", key="shoir_os_decision_title")
            kpi = st.text_input("Primary KPI", "Throughput", key="shoir_os_decision_kpi")
            baseline = st.number_input("Baseline value", value=0.0, key="shoir_os_decision_base")
            alternative = st.number_input("Alternative value", value=0.0, key="shoir_os_decision_alt")
            if st.button("Create evidence-backed decision", key="shoir_os_decision_create", type="primary"):
                decision = decision_record(
                    title,
                    baseline={kpi: baseline},
                    alternatives=[{"name": "Alternative", kpi: alternative}],
                    evidence=[evidence_manifest(str(module), parameters={"kpi": kpi})],
                    uncertainty=uncertainty_summary([baseline, alternative]),
                )
                save_evidence(str(module), f"{title} Evidence", evidence_manifest(str(module), result=decision))
                st.success(f"Draft decision {decision['decision_id']} created.")
            decisions = list_persisted_objects("decision", 25)
            if not decisions.empty:
                st.dataframe(decisions, use_container_width=True, hide_index=True)
    elif view == "Experiment / Uncertainty":
        render_experiment_lab()
    elif view == "Verification / Replay":
        with st.expander("Verification / Replay", expanded=True):
            df, _ = active_dataframe()
            report = verification_report(df, st.session_state.get("shoir_universal_postflight"))
            st.metric("Verification", report["status"], f"{report['passed']}/{report['total']} checks")
            st.dataframe(pd.DataFrame(report["checks"]), use_container_width=True, hide_index=True)
            manifest = build_reproducibility_manifest(str(module))
            st.download_button(
                "Export reproducibility manifest",
                data=json.dumps(manifest, indent=2, default=str).encode("utf-8"),
                file_name=f"shoir_{re.sub(r'[^A-Za-z0-9]+','_',str(module)).lower()}_reproducibility.json",
                mime="application/json",
                key="shoir_os_repro_manifest",
            )
    elif view == "Story / ROI":
        render_story_and_roi()
    elif view == "Industrial Templates":
        render_templates()
    elif view == "Control Tower":
        render_control_tower()
    elif view == "Alerts / Monitoring":
        render_alerts()
    elif view == "Presentation / Reports":
        render_presentation_report()
    elif view == "Run Center":
        render_run_center()
    elif view == "Security / Collaboration":
        render_security_and_collaboration()
    elif view == "Experience / Localization":
        render_modes_and_localization()
    elif view == "Benchmarking":
        with st.expander("Benchmarking / Observed vs Reference", expanded=True):
            df, _ = active_dataframe()
            if df.empty or not list(df.select_dtypes(include=np.number).columns):
                st.info("Load observed data to compare against a reference benchmark.")
            else:
                num = list(df.select_dtypes(include=np.number).columns[:6])
                actual = {str(c): float(pd.to_numeric(df[c], errors="coerce").mean()) for c in num}
                default = "\n".join(f"{k}=0" for k in num)
                text_ref = st.text_area("Reference values (KPI=value per line)", value=default, key="shoir_os_benchmark_ref")
                benchmark = {}
                for line in text_ref.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        try: benchmark[k.strip()] = float(v.strip())
                        except ValueError: pass
                st.dataframe(benchmark_snapshot(actual, benchmark), use_container_width=True, hide_index=True)
    elif view == "Self-Diagnostics":
        render_platform_health(allowed_modules)
    elif view == "Capability Maturity":
        render_capability_status()
    elif view == "Connector Framework":
        render_connector_health()
    elif view == "Formula + KPI Registry":
        with st.expander("Formula + KPI Registry", expanded=True):
            st.dataframe(kpi_registry(), use_container_width=True, hide_index=True)
            st.dataframe(pd.DataFrame(formula_registry()), use_container_width=True, hide_index=True)


    # Deep platform-completion console: evidence ledger, full DOE, forecasting,
    # connector execution, decision memory, diagnostics and browser-movable canvas.
    try:
        ensure_core_schema()
        render_core_canvas()
        render_core_completion(str(module), active_dataframe()[0], allowed_modules=allowed_modules)
    except Exception as exc:
        st.warning(f"Advanced platform completion surface unavailable: {type(exc).__name__}: {exc}")


def install_css() -> None:
    if st.session_state.get("_shoir_os_css_v2"):
        return
    st.markdown(
        """
<style>
.shoir-os-canvas{margin:8px 0 16px;padding:16px;border:1px solid #dbe4ef;border-radius:20px;background:linear-gradient(135deg,#ffffff,#f7fafc);box-shadow:0 12px 34px rgba(15,23,42,.06)}
.shoir-os-header{display:flex;justify-content:space-between;gap:12px;align-items:center}
.shoir-os-kicker{font-size:10px;letter-spacing:.09em;font-weight:900;color:#0f766e}
.shoir-os-title{font-size:22px;font-weight:900;color:#0f172a}
.shoir-os-badge{font-size:10px;font-weight:900;padding:7px 10px;border-radius:999px;background:#eff6ff;border:1px solid #dbeafe;color:#1d4ed8}
.shoir-os-grid{display:grid;grid-template-columns:repeat(6,minmax(100px,1fr));gap:8px;margin-top:12px}
.shoir-os-panel{min-height:74px;padding:10px;border-radius:14px;background:rgba(248,250,252,.9);border:1px solid #e2e8f0}
.shoir-os-panel b{display:block;font-size:9px;letter-spacing:.08em;color:#94a3b8}
.shoir-os-panel span{display:block;font-size:11px;color:#334155;margin-top:5px;line-height:1.35}
@media(max-width:980px){.shoir-os-grid{grid-template-columns:repeat(3,minmax(100px,1fr))}}
@media(max-width:620px){.shoir-os-grid{grid-template-columns:repeat(2,minmax(100px,1fr))}.shoir-os-header{align-items:flex-start;flex-direction:column}}
</style>
""",
        unsafe_allow_html=True,
    )
    st.session_state["_shoir_os_css_v2"] = True


__all__ = [
    "WORKFLOW_STEPS", "CAPABILITY_STATES", "ModuleManifest", "INDUSTRIAL_TEMPLATES",
    "problem_solver", "module_manifest", "capability_maturity", "dataframe_digest",
    "profile_data", "active_dataframe", "evidence_manifest", "build_reproducibility_manifest",
    "uncertainty_summary", "monte_carlo_summary", "bootstrap_summary", "sensitivity_table",
    "compare_scenarios", "scenario_record", "decision_record", "visualization_recommendations",
    "build_auto_visual", "forecast_operations", "optimization_diagnostics", "verification_report",
    "module_self_diagnostics", "connector_contracts", "kpi_registry", "formula_registry",
    "engineering_story", "roi_snapshot", "sync_dataset_thread", "render_platform_os_surface",
    "template_catalog", "select_template", "forecast_operations", "optimization_diagnostics",
    "verification_report", "platform_health_snapshot", "build_presentation_package",
    "factorial_design", "effect_sizes", "holm_adjust", "approximate_power",
    "residual_diagnostics", "schema_drift", "deep_data_quality", "benchmark_snapshot",
]