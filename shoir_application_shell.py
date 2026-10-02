"""Unified Shoir-IE application shell and cross-cutting engineering surfaces.

This layer consolidates the existing Industrial Home, 160 Operating System,
Excellence Hub, Global Product Dock and module navigation into one calm shell.
It deliberately reuses existing specialist modules instead of replacing them.
"""

from __future__ import annotations

import html
import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import pandas as pd
import plotly.express as px
import streamlit as st

SHELL_VERSION = "3.0"

NAV_GROUPS = {
    "HOME": "⌂ Home",
    "WORKBENCH": "▦ Workbench",
    "DATA": "◫ Data",
    "ANALYZE": "◈ Analyze",
    "SIMULATE": "◌ Simulate",
    "OPTIMIZE": "◇ Optimize",
    "OPERATIONS": "⚙ Operations",
    "DECISIONS": "✓ Decisions",
    "RESEARCH": "🧪 Research",
    "KNOWLEDGE": "📚 Knowledge",
    "ADMIN": "⚙ Admin",
}

MODULE_GROUP_RULES = (
    ("Data", ("excel", "data", "workbook", "dataset", "inventory playback")),
    ("Production", ("production", "manufacturing", "shop floor", "line balancing", "planning", "scheduling", "capacity")),
    ("Quality", ("quality", "six sigma", "reliability", "spc", "defect")),
    ("Supply Chain", ("supply", "supplier", "inventory", "warehouse", "logistics", "fleet", "routing", "meio")),
    ("Maintenance", ("maintenance", "predictive", "digital twin")),
    ("Facilities", ("facility", "layout", "slotting", "agv", "geospatial")),
    ("Workforce", ("workforce", "human factors", "ergonomics")),
    ("Economics", ("economics", "finance", "capital investment", "roi", "cost")),
    ("Sustainability", ("carbon", "sustainability", "green ie", "lca", "energy")),
    ("Research", ("research", "experiment", "hypothesis", "regression", "paper", "latex", "literature", "falsification", "isomorphism", "zero-knowledge", "quantum-classical")),
    ("AI & Automation", ("copilot", "agentic", "automation", "ai")),
    ("Operations", ("control center", "control tower", "execution", "mes", "connectivity", "iot", "telemetry")),
    ("Platform & Governance", ("admin", "security", "governance", "persistence", "rbac", "benchmark", "digital thread", "decision")),
)

PROVENANCE_STATES = ("LIVE", "IMPORTED", "SIMULATED", "DEMO")

PASTED_SPEC_UPDATES = {
    "one_application_shell": "Unified application shell over existing engines",
    "module_launcher": "Searchable grouped module launcher with recents",
    "universal_workflow": "Data → Validate → Model → Run → Visualize → Compare → Explain → Decide → Export → Verify",
    "reduced_tabs": "Grouped platform surfaces and progressive disclosure",
    "digital_thread_everywhere": "Persistent lineage/trace context",
    "universal_inspector": "Cross-module provenance/assumption/run inspector",
    "provenance_state_contract": "LIVE / IMPORTED / SIMULATED / DEMO distinction",
    "run_center": "First-class durable run center",
    "decision_outcomes": "Decision → Implementation → Actual KPI → Variance → Learning loop",
    "copilot_navigation": "Global Copilot/search orchestration entry point",
    "evidence_drawer": "Explain-this-number provenance surface",
    "admin_separation": "Administration separated from engineering workspace",
    "performance_path": "Application-shell boundary for future service extraction",
    "dataset_catalog": "Central dataset catalog over existing dataset registries",
    "research_reproducibility": "Experiment reproduction metadata and evidence links",
    "trust_center": "Global trust/readiness view",
    "presentation_mode": "Clutter-free presentation surface",
    "restrained_visuals": "Calm control-room / engineering-IDE visual language",
    "domain_engines": "Specialist modules remain engines behind shared contracts",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shoir_shell_decision_outcomes (
    outcome_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    actual_metrics_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    owner TEXT,
    status TEXT NOT NULL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_shoir_shell_outcomes_decision
    ON shoir_shell_decision_outcomes(decision_id, observed_at DESC);
"""


def _db(path: str = "enterprise_full_workspace.db") -> sqlite3.Connection:
    return sqlite3.connect(path, timeout=30)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_shell_schema(db_path: str = "enterprise_full_workspace.db") -> None:
    try:
        with _db(db_path) as conn:
            for statement in SCHEMA_SQL.strip().split(";\n"):
                if statement.strip():
                    conn.execute(statement)
            conn.commit()
    except Exception:
        pass


def _safe_df(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, Mapping):
        for candidate in ("data", "df", "table", "dataframe", "result"):
            nested = value.get(candidate)
            if isinstance(nested, pd.DataFrame):
                return nested
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    if isinstance(value, (list, tuple)):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _first_dataframe() -> tuple[pd.DataFrame, str]:
    preferred = (
        "universal_active_dataset",
        "excel_studio_visual_df",
        "industrial_workbook_current_df",
        "data_platform_latest_df",
        "unified_data",
        "os160_cleaned_df",
        "copilot_workbook",
    )
    for key in preferred:
        value = st.session_state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value, key

    for key, value in list(st.session_state.items()):
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value, str(key)
        if isinstance(value, Mapping):
            frame = _safe_df(value)
            if not frame.empty:
                return frame, str(key)
    return pd.DataFrame(), ""


def infer_provenance(default: str = "DEMO") -> str:
    explicit = str(st.session_state.get("shoir_data_status", "")).upper().strip()
    if explicit in PROVENANCE_STATES:
        return explicit

    key = str(st.session_state.get("shoir_data_source_key", "")).lower()
    if key in {"live", "iot", "telemetry", "connector"}:
        return "LIVE"
    if key in {"imported", "upload", "workbook"}:
        return "IMPORTED"
    if key in {"simulated", "scenario", "simulation"}:
        return "SIMULATED"

    _, discovered_key = _first_dataframe()
    joined = f"{key} {discovered_key}".lower()
    if any(token in joined for token in ("upload", "import", "excel_studio", "universal_active", "workbook_current")):
        return "IMPORTED"
    if any(token in joined for token in ("scenario", "simulation", "forecast", "monte", "experiment")):
        return "SIMULATED"
    return default


def set_provenance(status: str, source: str = "", version: str = "") -> None:
    state = str(status).upper()
    if state not in PROVENANCE_STATES:
        raise ValueError(f"Unsupported provenance status: {status}")
    st.session_state["shoir_data_status"] = state
    if source:
        st.session_state["shoir_data_source"] = source
    if version:
        st.session_state["shoir_data_version"] = version


def data_readiness(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        return {
            "score": 0.0, "rows": 0, "columns": 0,
            "missing_pct": 100.0, "duplicate_pct": 0.0,
            "warnings": ["No active engineering dataset is available."],
        }
    rows = len(df)
    cols = len(df.columns)
    missing_pct = float(df.isna().mean().mean() * 100.0) if cols else 100.0
    duplicate_pct = float(df.duplicated().mean() * 100.0) if rows else 0.0
    score = max(0.0, min(100.0, 100.0 - (missing_pct * 0.55) - (duplicate_pct * 0.45)))
    warnings: list[str] = []
    if missing_pct > 10:
        warnings.append(f"Missingness is {missing_pct:.1f}%.")
    if duplicate_pct > 5:
        warnings.append(f"Duplicate rows are {duplicate_pct:.1f}%.")
    if cols == 0:
        warnings.append("Dataset contains no columns.")
    return {
        "score": score, "rows": rows, "columns": cols,
        "missing_pct": missing_pct, "duplicate_pct": duplicate_pct,
        "warnings": warnings,
    }


def module_group(module: str) -> str:
    value = str(module or "").lower()
    for group, needles in MODULE_GROUP_RULES:
        if any(needle in value for needle in needles):
            return group
    return "Industrial Engineering"


def build_module_index(allowed_modules: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Module": str(module), "Group": module_group(str(module)), "Purpose": "Specialist engineering engine", "Status": "Available"}
            for module in allowed_modules
        ]
    )


def _recent_modules(allowed_modules: Sequence[str]) -> list[str]:
    recent = [str(x) for x in st.session_state.get("shoir_recent_modules", [])]
    allowed = {str(x) for x in allowed_modules}
    return [x for x in recent if x in allowed][:6]


def remember_module(module: str) -> None:
    module = str(module)
    recent = [module] + [str(x) for x in st.session_state.get("shoir_recent_modules", []) if str(x) != module]
    st.session_state["shoir_recent_modules"] = recent[:8]


def render_global_search(allowed_modules: Sequence[str]) -> None:
    """Search modules and durable engineering objects from the same shell."""
    query = st.text_input(
        "⌘ Search Shoir-IE",
        placeholder="Search modules, datasets, runs, decisions…",
        key="shoir_shell_global_search",
    )
    if not query.strip():
        return
    term = query.strip().lower()
    module_hits = [m for m in allowed_modules if term in str(m).lower() or term in module_group(str(m)).lower()]
    dataset_hits = _query_df(
        """SELECT dataset_id,name,source,owner,updated_at
           FROM os160_datasets ORDER BY updated_at DESC LIMIT 500"""
    )
    run_hits = _query_df(
        """SELECT run_id,module,job_type,status,created_at
           FROM os160_runs ORDER BY created_at DESC LIMIT 500"""
    )
    decision_hits = _query_df(
        """SELECT decision_id,title,module,status,updated_at
           FROM os160_decisions ORDER BY updated_at DESC LIMIT 500"""
    )
    if not dataset_hits.empty:
        dataset_hits = dataset_hits[dataset_hits.astype(str).apply(
            lambda col: col.str.lower().str.contains(term, regex=False)
        ).any(axis=1)]
    if not run_hits.empty:
        run_hits = run_hits[run_hits.astype(str).apply(
            lambda col: col.str.lower().str.contains(term, regex=False)
        ).any(axis=1)]
    if not decision_hits.empty:
        decision_hits = decision_hits[decision_hits.astype(str).apply(
            lambda col: col.str.lower().str.contains(term, regex=False)
        ).any(axis=1)]

    with st.expander("⌘ Search results", expanded=True):
        if module_hits:
            st.markdown("**Modules**")
            for idx, name in enumerate(module_hits[:12]):
                if st.button(f"Open · {name}", key=f"shoir_global_module_{idx}", use_container_width=True):
                    st.session_state["_shoir_requested_module"] = str(name)
                    st.session_state["shoir_shell_global_search"] = ""
                    st.rerun()
        if not dataset_hits.empty:
            st.markdown("**Datasets**")
            st.dataframe(dataset_hits.head(20), use_container_width=True, hide_index=True)
        if not run_hits.empty:
            st.markdown("**Runs**")
            st.dataframe(run_hits.head(20), use_container_width=True, hide_index=True)
        if not decision_hits.empty:
            st.markdown("**Decisions**")
            st.dataframe(decision_hits.head(20), use_container_width=True, hide_index=True)
        if not module_hits and dataset_hits.empty and run_hits.empty and decision_hits.empty:
            st.info("No matching engineering objects were found.")


def _module_choices(allowed_modules: Sequence[str], section: str, search: str) -> list[str]:
    modules = [str(x) for x in allowed_modules]
    q = str(search or "").strip().lower()

    def in_section(name: str) -> bool:
        group = module_group(name)
        low = name.lower()
        if section in {"HOME", "WORKBENCH"}:
            return True
        if section == "DATA":
            return group == "Data"
        if section == "ANALYZE":
            return group in {"Production", "Quality", "Supply Chain", "Economics", "Sustainability", "Data"}
        if section == "SIMULATE":
            return any(k in low for k in ("simulation", "digital twin", "monte carlo", "scenario", "agv", "forecast"))
        if section == "OPTIMIZE":
            return any(k in low for k in ("optimiz", "milp", "routing", "planning", "scheduling", "inventory", "meio", "fleet"))
        if section == "OPERATIONS":
            return group in {"Operations", "Maintenance", "Facilities", "Production"}
        if section == "DECISIONS":
            return any(k in low for k in ("decision", "economics", "scenario", "benchmark"))
        if section == "RESEARCH":
            return group == "Research" or "research" in low
        if section == "KNOWLEDGE":
            return any(k in low for k in ("copilot", "knowledge", "benchmark", "standards", "literature"))
        if section == "ADMIN":
            return any(k in low for k in ("admin", "security", "governance", "subscription", "persistence", "connectivity"))
        return True

    filtered = [x for x in modules if in_section(x) and (not q or q in x.lower() or q in module_group(x).lower())]
    if not filtered and q:
        filtered = [x for x in modules if q in x.lower()]
    return filtered or modules


def _badge(label: str, tone: str = "neutral") -> str:
    tones = {
        "good": ("#ecfdf5", "#047857", "#a7f3d0"),
        "info": ("#eff6ff", "#1d4ed8", "#bfdbfe"),
        "warn": ("#fffbeb", "#b45309", "#fde68a"),
        "bad": ("#fef2f2", "#b91c1c", "#fecaca"),
        "neutral": ("#f8fafc", "#475569", "#cbd5e1"),
    }
    bg, fg, border = tones.get(tone, tones["neutral"])
    return (
        f"<span style='display:inline-block;padding:5px 9px;border-radius:999px;"
        f"background:{bg};color:{fg};border:1px solid {border};font-size:11px;"
        f"font-weight:800;letter-spacing:.04em'>{label}</span>"
    )


def provenance_badge(status: str) -> str:
    state = str(status).upper()
    tone = {"LIVE": "good", "IMPORTED": "info", "SIMULATED": "warn", "DEMO": "neutral"}.get(state, "neutral")
    return _badge(state, tone)


def render_shell_css() -> None:
    st.markdown(
        """
<style>
.shoir-shell-top {display:grid;grid-template-columns:minmax(270px,1.7fr) repeat(5,minmax(95px,.55fr));gap:8px;margin:0 0 14px;padding:8px;border:1px solid #dbe4ef;border-radius:17px;background:rgba(255,255,255,.82);backdrop-filter:blur(12px);box-shadow:0 8px 25px rgba(15,23,42,.045);}
.shoir-shell-cell {min-height:52px;padding:8px 10px;border-radius:11px;background:#f8fafc;}
.shoir-shell-label {font-size:9px;font-weight:900;letter-spacing:.09em;text-transform:uppercase;color:#94a3b8;}
.shoir-shell-value {margin-top:3px;font-size:12px;font-weight:850;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.shoir-shell-workflow {display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0 16px;}
.shoir-shell-step {padding:6px 9px;border-radius:999px;border:1px solid #dbe4ef;background:#fff;color:#64748b;font-size:10px;font-weight:850;}
.shoir-shell-step.active {color:#0f766e;border-color:#99f6e4;background:#f0fdfa;}
.shoir-shell-step.done {color:#1d4ed8;border-color:#bfdbfe;background:#eff6ff;}
.shoir-shell-divider {color:#cbd5e1;font-weight:900;}
.shoir-shell-section {margin-top:8px;margin-bottom:7px;color:#0f172a;font-size:18px;font-weight:900;letter-spacing:-.02em;}
.shoir-shell-card {border:1px solid #dbe4ef;border-radius:16px;padding:13px 15px;background:#fff;box-shadow:0 7px 24px rgba(15,23,42,.04);}
.shoir-shell-muted {color:#64748b;font-size:12px;line-height:1.5;}
.shoir-presentation [data-testid="stSidebar"] {display:none !important;}
.shoir-home-hero {padding:28px 30px;border-radius:22px;background:linear-gradient(135deg,#071524,#173b77 55%,#0f766e);color:#fff;box-shadow:0 18px 48px rgba(15,23,42,.14);margin:0 0 16px;}
.shoir-home-eyebrow {font-size:11px;font-weight:900;letter-spacing:.14em;color:#7dd3fc;text-transform:uppercase;}
.shoir-home-title {font-size:34px;font-weight:950;letter-spacing:-.035em;line-height:1.05;margin-top:6px;}
.shoir-home-copy {font-size:14px;color:#dbeafe;line-height:1.55;margin-top:8px;max-width:900px;}
.shoir-home-step {height:100%;padding:17px;border:1px solid #dbe4ef;border-radius:16px;background:#fff;box-shadow:0 8px 24px rgba(15,23,42,.035);}
.shoir-home-step-num {display:inline-flex;width:28px;height:28px;align-items:center;justify-content:center;border-radius:999px;background:#eff6ff;color:#1d4ed8;font-weight:900;font-size:12px;}
.shoir-home-step-title {margin-top:8px;font-size:15px;font-weight:900;color:#0f172a;}
.shoir-home-step-copy {margin-top:4px;font-size:12px;color:#64748b;line-height:1.45;}
.shoir-home-section {margin-top:18px;margin-bottom:9px;font-size:20px;font-weight:900;color:#0f172a;letter-spacing:-.02em;}
.shoir-presentation .block-container {max-width:1450px !important;padding-top:1.2rem !important;}
@media(max-width:1050px){.shoir-shell-top{grid-template-columns:1.7fr repeat(3,1fr);}}
@media(max-width:700px){.shoir-shell-top{grid-template-columns:1fr 1fr;}}
</style>
""",
        unsafe_allow_html=True,
    )


def render_application_header(username: str, tier: str, module: str) -> None:
    df, source_key = _first_dataframe()
    ready = data_readiness(df)
    provenance = infer_provenance()
    project = (
        st.session_state.get("shoir_project_name")
        or st.session_state.get("active_workspace_name")
        or st.session_state.get("workspace")
        or "No active project"
    )
    dataset = (
        st.session_state.get("shoir_data_source")
        or st.session_state.get("shoir_data_version")
        or source_key
        or "No active dataset"
    )
    run_id = (
        st.session_state.get("shoir_latest_run_id")
        or st.session_state.get("last_run_id")
        or "No active run"
    )
    project_safe = html.escape(str(project))
    dataset_safe = html.escape(str(dataset))
    username_safe = html.escape(str(username))
    run_safe = html.escape(str(run_id))
    tier_safe = html.escape(str(tier))
    st.markdown(
        f"""
<div class="shoir-shell-top">
  <div class="shoir-shell-cell"><div class="shoir-shell-label">Shoir-IE Workspace</div><div class="shoir-shell-value">{project_safe} · {username_safe}</div></div>
  <div class="shoir-shell-cell"><div class="shoir-shell-label">Dataset</div><div class="shoir-shell-value">{dataset_safe}</div></div>
  <div class="shoir-shell-cell"><div class="shoir-shell-label">Readiness</div><div class="shoir-shell-value">{ready['score']:.0f}%</div></div>
  <div class="shoir-shell-cell"><div class="shoir-shell-label">State</div><div class="shoir-shell-value">{provenance}</div></div>
  <div class="shoir-shell-cell"><div class="shoir-shell-label">Run</div><div class="shoir-shell-value">{run_safe}</div></div>
  <div class="shoir-shell-cell"><div class="shoir-shell-label">Tier</div><div class="shoir-shell-value">{tier_safe}</div></div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_module_workflow(module: str, provenance: str | None = None) -> None:
    state = provenance or infer_provenance()
    steps = ["DATA", "VALIDATE", "MODEL", "RUN", "VISUALIZE", "COMPARE", "EXPLAIN", "DECIDE", "EXPORT", "VERIFY"]
    active_index = 3 if st.session_state.get("last_run_id") or st.session_state.get("shoir_latest_run_id") else 1
    if st.session_state.get("unified_readiness_score", 0):
        active_index = max(active_index, 2)
    chips = []
    for idx, step in enumerate(steps):
        tone = "active" if idx == active_index else ("done" if idx < active_index else "")
        chips.append(f"<span class='shoir-shell-step {tone}'>{idx+1:02d} {step}</span>")
        if idx < len(steps) - 1:
            chips.append("<span class='shoir-shell-divider'>›</span>")
    st.markdown(
        f"""
<div class="shoir-shell-section">{module}</div>
<div class="shoir-shell-muted">Shared engineering workflow · {provenance_badge(state)}</div>
<div class="shoir-shell-workflow">{''.join(chips)}</div>
""",
        unsafe_allow_html=True,
    )


def _trust_metrics(username: str, tier: str) -> dict[str, Any]:
    df, _ = _first_dataframe()
    ready = data_readiness(df)
    durable = bool(st.session_state.get("remote_session_token") and st.session_state.get("authenticated"))
    result = {
        "data_readiness": ready["score"],
        "provenance": infer_provenance(),
        "durable_session": durable,
        "assumptions": len(st.session_state.get("shoir_assumptions", [])) if isinstance(st.session_state.get("shoir_assumptions", []), list) else 0,
        "tier": tier,
        "user": username,
        "warnings": ready["warnings"],
    }
    try:
        from shoir_160 import health_snapshot, feature_matrix_stats
        h = health_snapshot()
        s = feature_matrix_stats()
        result["platform_health"] = float(h.get("score", 0.0))
        result["verified_capabilities"] = int(s.get("verified", 0))
        result["capabilities"] = int(s.get("total", 160))
    except Exception:
        result["platform_health"] = 0.0
        result["verified_capabilities"] = 0
        result["capabilities"] = 160
    return result


def render_inspector(module: str, username: str, tier: str) -> None:
    metrics = _trust_metrics(username, tier)
    df, source_key = _first_dataframe()

    def body() -> None:
        st.markdown("### Inspector")
        st.markdown(f"**Module:** {module}")
        st.markdown(f"**Data state:** {provenance_badge(metrics['provenance'])}", unsafe_allow_html=True)
        st.markdown(f"**Dataset source:** \`{source_key or 'none'}\`")
        st.markdown(f"**Readiness:** \`{metrics['data_readiness']:.1f}%\`")
        st.markdown(f"**Rows × columns:** \`{len(df):,} × {len(df.columns):,}\`")
        st.markdown(f"**Assumptions:** \`{metrics['assumptions']}\`")
        st.markdown(f"**Platform health:** \`{metrics['platform_health']:.0f}%\`")
        st.markdown(f"**Run ID:** \`{st.session_state.get('shoir_latest_run_id') or st.session_state.get('last_run_id') or 'not assigned'}\`")
        st.markdown(f"**Version:** \`{st.session_state.get('shoir_data_version', 'session/latest')}\`")
        if metrics["warnings"]:
            st.markdown("**Warnings**")
            for warning in metrics["warnings"]:
                st.warning(warning)
        with st.expander("Provenance details", expanded=False):
            st.json({
                "state": metrics["provenance"],
                "source_key": source_key,
                "source": st.session_state.get("shoir_data_source"),
                "version": st.session_state.get("shoir_data_version"),
                "hash": st.session_state.get("shoir_data_hash"),
            })

    popover = getattr(st, "popover", None)
    if callable(popover):
        with popover("🔎 Inspector"):
            body()
    else:
        with st.expander("🔎 Inspector", expanded=False):
            body()



def _activate_shared_dataset(
    df: pd.DataFrame,
    *,
    filename: str,
    sheet: str,
    signature: str = "",
) -> None:
    """Publish one imported/cleaned table as the shared Shoir-IE active dataset."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("The active dataset must be a pandas DataFrame.")
    active = df.copy(deep=True)
    digest = str(signature or "")
    if not digest:
        import hashlib
        digest = hashlib.sha256(active.to_csv(index=False).encode("utf-8", errors="replace")).hexdigest()
    st.session_state["universal_active_dataset"] = active
    st.session_state["excel_studio_visual_df"] = active
    st.session_state["data_platform_latest_df"] = active
    st.session_state["unified_data"] = active
    st.session_state["industrial_workbook_current_df"] = active
    st.session_state["shoir_data_status"] = "IMPORTED"
    st.session_state["shoir_data_source_key"] = "upload"
    st.session_state["shoir_data_source"] = f"{filename} · {sheet}" if sheet else str(filename)
    st.session_state["shoir_data_version"] = str(digest)[:12]
    st.session_state["shoir_data_hash"] = str(digest)
    st.session_state["shoir_active_workbook_sheet"] = str(sheet)


def _process_home_upload(uploaded: Any) -> tuple[dict[str, pd.DataFrame], str]:
    raw = uploaded.getvalue()
    from shoir_excel_studio import process_uploaded_workbook
    result = process_uploaded_workbook(raw, str(uploaded.name))
    sheets = result.get("cleaned_sheets") or result.get("raw_sheets") or {}
    cleaned = {
        str(name): frame.copy(deep=True)
        for name, frame in sheets.items()
        if isinstance(frame, pd.DataFrame)
    }
    cleaned = {name: frame for name, frame in cleaned.items() if not frame.empty}
    if not cleaned:
        raise ValueError("The uploaded file contained no usable data tables after inspection.")
    return cleaned, str(result.get("signature") or "")


def render_data_hub(username: str, tier: str) -> None:
    """Central data handoff used by Home and Data; downstream modules share the active table."""
    st.markdown("### Load your industrial data")
    st.caption(
        "Upload once. Shoir-IE cleans the file, keeps the multi-sheet workbook available, "
        "and publishes the active sheet to analysis, simulation, optimization and decision tools."
    )
    upload = st.file_uploader(
        "📤 Upload Excel / CSV / TSV / TXT",
        type=["xlsx", "xlsm", "xls", "csv", "tsv", "txt"],
        key="shoir_data_hub_upload",
        help="The uploaded file is processed through the existing Excel Intelligence cleaning and governance pipeline.",
    )
    if upload is not None:
        import hashlib
        signature = hashlib.sha256(upload.getvalue()).hexdigest()
        if signature != st.session_state.get("_shoir_data_hub_signature"):
            with st.spinner("Inspecting, cleaning and connecting your data…"):
                sheets, processed_signature = _process_home_upload(upload)
                st.session_state["industrial_workbook"] = sheets
                st.session_state["industrial_workbook_formulas"] = {name: {} for name in sheets}
                st.session_state["industrial_workbook_variables"] = {}
                st.session_state["industrial_workbook_id"] = None
                st.session_state["_shoir_data_hub_signature"] = signature
                st.session_state["_shoir_data_hub_filename"] = str(upload.name)
                first_sheet = next(iter(sheets))
                _activate_shared_dataset(
                    sheets[first_sheet],
                    filename=str(upload.name),
                    sheet=first_sheet,
                    signature=processed_signature or signature,
                )
                st.session_state["industrial_workbook_current_df"] = sheets[first_sheet].copy(deep=True)
                st.session_state["industrial_workbook_last_upload_signature"] = signature
                st.success(
                    f"Connected {len(sheets):,} cleaned sheet(s) from **{upload.name}**. "
                    "The active dataset is now available to downstream engineering tools."
                )
                st.rerun()

    sheets = st.session_state.get("industrial_workbook", {})
    if isinstance(sheets, Mapping) and sheets:
        names = [str(name) for name in sheets]
        active = str(st.session_state.get("shoir_active_workbook_sheet") or names[0])
        if active not in names:
            active = names[0]
        choice = st.selectbox(
            "Active sheet",
            names,
            index=names.index(active),
            key="shoir_data_hub_sheet",
        )
        if choice != st.session_state.get("shoir_active_workbook_sheet"):
            _activate_shared_dataset(
                sheets[choice],
                filename=str(st.session_state.get("_shoir_data_hub_filename") or "Industrial Workbook"),
                sheet=choice,
                signature=str(st.session_state.get("shoir_data_hash") or ""),
            )
            st.rerun()
        active_df = st.session_state.get("universal_active_dataset", pd.DataFrame())
        if isinstance(active_df, pd.DataFrame) and not active_df.empty:
            ready = data_readiness(active_df)
            a,b,c,d = st.columns(4)
            a.metric("Rows", f"{len(active_df):,}")
            b.metric("Columns", f"{len(active_df.columns):,}")
            c.metric("Readiness", f"{ready['score']:.0f}%")
            d.metric("State", infer_provenance())
            st.dataframe(active_df.head(12), use_container_width=True, hide_index=True)
            if ready["warnings"]:
                st.caption(" · ".join(ready["warnings"][:2]))
    else:
        st.info("No shared dataset yet. Upload an industrial workbook above or open Industrial Workbook to start from a built-in engineering template.")


def render_industrial_home(username: str, tier: str) -> None:
    """Calm first-run landing page with an explicit engineering workflow guide."""
    username_safe = html.escape(str(username or "Engineer"))
    st.markdown(
        f"""
<div class="shoir-home-hero">
  <div class="shoir-home-eyebrow">SHOIR-IE · INDUSTRIAL ENGINEERING DECISION PLATFORM</div>
  <div class="shoir-home-title">Welcome to Shoir-IE, {username_safe}.</div>
  <div class="shoir-home-copy">This is your engineering workspace. Bring in a workbook, choose the right tool, validate the evidence, visualize the result, and carry the decision through implementation and learning.</div>
</div>
""",
        unsafe_allow_html=True,
    )

    steps = [
        ("01", "Load data", "Upload Excel/CSV and let Shoir-IE clean, structure and connect the active table."),
        ("02", "Choose a tool", "Use the sidebar sections to move between Workbench, Data, Analyze, Simulate and Optimize."),
        ("03", "Validate", "Review missing values, duplicates, units and assumptions before relying on a result."),
        ("04", "Analyze & visualize", "Run the specialist engineering engine and inspect the live result graph."),
        ("05", "Decide & learn", "Compare scenarios, export evidence, implement the action and record the actual KPI."),
    ]
    st.markdown("### Your 5-step Shoir-IE workflow")
    cols = st.columns(5)
    for col, (num, title, copy) in zip(cols, steps):
        with col:
            st.markdown(
                f"<div class='shoir-home-step'><span class='shoir-home-step-num'>{num}</span>"
                f"<div class='shoir-home-step-title'>{title}</div><div class='shoir-home-step-copy'>{copy}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div class='shoir-home-section'>Start here</div>", unsafe_allow_html=True)
    actions = st.columns(3)
    with actions[0]:
        if st.button("📊 Open Industrial Workbook", type="primary", use_container_width=True, key="shoir_home_open_workbook"):
            st.session_state["_shoir_requested_module"] = "Industrial Workbook"
            st.session_state["shoir_shell_section"] = "WORKBENCH"
            st.rerun()
    with actions[1]:
        if st.button("🧹 Open Excel Intelligence", use_container_width=True, key="shoir_home_open_excel"):
            st.session_state["_shoir_requested_module"] = "Excel Data Cleaning & Import"
            st.session_state["shoir_shell_section"] = "DATA"
            st.rerun()
    with actions[2]:
        if st.button("⚙ Open Core IE Tools", use_container_width=True, key="shoir_home_open_core"):
            st.session_state["_shoir_requested_module"] = "Core IE Tools"
            st.session_state["shoir_shell_section"] = "ANALYZE"
            st.rerun()

    st.markdown("### Where each section takes you")
    guide = pd.DataFrame([
        {"Section": "Workbench", "Use it for": "Workbook, formulas, templates, query pipelines and fast engineering productivity."},
        {"Section": "Data", "Use it for": "Import, cleaning, data readiness, datasets, versions and governance."},
        {"Section": "Analyze", "Use it for": "Quality, production, supply chain, economics and other diagnostic studies."},
        {"Section": "Simulate", "Use it for": "Scenario, Monte Carlo, digital twin and uncertainty workflows."},
        {"Section": "Optimize", "Use it for": "MILP, routing, scheduling, inventory and planning decisions."},
        {"Section": "Operations", "Use it for": "Control tower, maintenance, facilities, connectivity and execution workflows."},
        {"Section": "Decisions", "Use it for": "Evidence-backed decision records, implementation tracking and actual outcomes."},
        {"Section": "Research / Knowledge", "Use it for": "Experiments, literature, standards, learning and reusable knowledge."},
    ])
    st.dataframe(guide, use_container_width=True, hide_index=True)

    has_data = isinstance(st.session_state.get("universal_active_dataset"), pd.DataFrame) and not st.session_state["universal_active_dataset"].empty
    st.markdown("### 1 · Load your data", unsafe_allow_html=True)
    render_data_hub(username, tier)
    if not has_data:
        st.caption("For a first walkthrough, upload any clean industrial table above; the next screen will show the same dataset inside the workbook and module workflows.")



def render_application_shell(
    *,
    username: str,
    tier: str,
    allowed_modules: Sequence[str],
    current_module: str | None = None,
    is_admin: bool = False,
) -> tuple[str, str | None]:
    ensure_shell_schema()
    render_shell_css()

    nav_labels = [key for key in NAV_GROUPS.keys() if is_admin or key != "ADMIN"]
    current_section = str(st.session_state.get("shoir_shell_section", "HOME"))
    if not is_admin and current_section == "ADMIN":
        current_section = "HOME"
        st.session_state["shoir_shell_section"] = "HOME"
        st.session_state.pop("shoir_shell_section_radio", None)
    try:
        current_index = nav_labels.index(current_section)
    except ValueError:
        current_index = 0

    previous_section = st.session_state.get("_shoir_shell_previous_section")
    section_changed = previous_section != current_section
    explicit_module_request = bool(
        st.session_state.get("_shoir_requested_module")
        and str(current_module or "") == str(st.session_state.get("_shoir_requested_module"))
    )

    with st.sidebar:
        st.markdown("## SHOIR-IE")
        st.caption("Industrial Engineering Decision Platform")
        st.markdown(f"{_badge('CONNECTED', 'good')} {_badge(str(tier), 'info')}", unsafe_allow_html=True)
        st.markdown("---")

        section = st.radio(
            "Primary navigation",
            nav_labels,
            index=current_index,
            format_func=lambda x: NAV_GROUPS[x],
            key="shoir_shell_section_radio",
            label_visibility="collapsed",
        )
        if not is_admin and section == "ADMIN":
            section = "HOME"
        st.session_state["shoir_shell_section"] = section

        # Section changes are intentional navigation events. A module click
        # inside the active section should instead dispatch the selected module.
        if section != current_section:
            section_changed = True
        st.session_state["_shoir_shell_previous_section"] = section

        st.markdown("#### Module Launcher")
        search = st.text_input(
            "⌕ Search modules",
            value="",
            placeholder="Excel, forecasting, quality, MILP…",
            key="shoir_shell_module_search",
            label_visibility="collapsed",
        )

        recent = _recent_modules(allowed_modules)
        recent_choice = "—"
        if recent:
            st.caption("Recent")
            recent_key = f"shoir_shell_recent_{section}"
            if st.session_state.get(recent_key) not in ["—"] + recent:
                st.session_state.pop(recent_key, None)
            recent_choice = st.selectbox(
                "Recent modules",
                ["—"] + recent,
                key=recent_key,
                label_visibility="collapsed",
            )

        choices = _module_choices(allowed_modules, section, search)
        if current_module and current_module in choices:
            default_module = current_module
        elif recent_choice != "—":
            default_module = recent_choice
        else:
            default_module = choices[0] if choices else (list(allowed_modules)[0] if allowed_modules else "MILP Solvers")

        default_index = choices.index(default_module) if default_module in choices else 0
        labels = {str(module): f"{module_group(str(module))} · {str(module)}" for module in choices}
        selector_key = f"shoir_shell_module_selector_{section}"
        if st.session_state.get(selector_key) not in choices:
            st.session_state.pop(selector_key, None)
        selected_label = st.selectbox(
            "Select module",
            list(choices),
            index=default_index,
            format_func=lambda x: labels.get(str(x), str(x)),
            key=selector_key,
            label_visibility="collapsed",
        )
        remember_module(selected_label)

        st.markdown("---")
        action_cols = st.columns(2)
        with action_cols[0]:
            if st.button("＋ New study", use_container_width=True, key="shoir_shell_new_study"):
                st.session_state["shoir_new_study_requested"] = True
        with action_cols[1]:
            if st.button("▣ Present", use_container_width=True, key="shoir_shell_present"):
                st.session_state["shoir_shell_surface"] = "presentation"

        quick = st.columns(3)
        with quick[0]:
            if st.button("✓ Trust", use_container_width=True, key="shoir_shell_trust"):
                st.session_state["shoir_shell_surface"] = "trust"
        with quick[1]:
            if st.button("▶ Runs", use_container_width=True, key="shoir_shell_runs"):
                st.session_state["shoir_shell_surface"] = "runs"
        with quick[2]:
            if st.button("⌘ Copilot", use_container_width=True, key="shoir_shell_copilot"):
                st.session_state["shoir_shell_surface"] = "copilot"

        platform = st.columns(2)
        with platform[0]:
            if st.button("⚡ Operating System", use_container_width=True, key="shoir_shell_os"):
                st.session_state["shoir_shell_surface"] = "os"
        with platform[1]:
            if st.button("✨ Excellence Hub", use_container_width=True, key="shoir_shell_excellence"):
                st.session_state["shoir_shell_surface"] = "excellence"

        st.markdown("---")
        with st.expander(f"👤 {username}", expanded=False):
            st.markdown(f"**Tier:** {tier}")
            st.markdown(f"**Role:** {st.session_state.get('user_role', 'Engineer')}")
            st.markdown(f"**Email:** {st.session_state.get('user_email', 'N/A')}")
            if st.button("Edit Account / Profile", use_container_width=True, key="shoir_shell_edit_account"):
                st.session_state["selected_nav"] = "Edit Account"
                st.session_state["shoir_shell_surface"] = "edit_account"

        if st.button("Lock / Logout Workspace", use_container_width=True, key="shoir_shell_logout"):
            st.session_state["shoir_shell_logout_requested"] = True

        st.markdown("---")
        st.caption(f"Shoir-IE shell v{SHELL_VERSION}")

    selected_module = str(selected_label or current_module or (list(allowed_modules)[0] if allowed_modules else "MILP Solvers"))
    surface = st.session_state.pop("shoir_shell_surface", None)

    if surface == "edit_account":
        st.session_state["selected_nav"] = "Edit Account"
        surface = None
    elif surface == "admin" and not is_admin:
        st.session_state["selected_nav"] = "Dashboard"
        surface = None
    else:
        st.session_state["selected_nav"] = "Dashboard"

    # Explicit module requests (including Open Industrial Workbook) always win
    # over section landing surfaces. This fixes the former "button does nothing"
    # behavior for modules inside the Workbench section.
    if explicit_module_request:
        surface = None
    elif surface is None and section_changed:
        if section == "HOME":
            surface = "home"
        elif section == "WORKBENCH":
            surface = "workbench"
        elif section == "DATA":
            surface = "catalog"
        elif section == "DECISIONS":
            surface = "decisions"
        elif section == "KNOWLEDGE":
            surface = "trust"

    if st.session_state.pop("shoir_new_study_requested", False):
        surface = "new_study"
    if st.session_state.pop("shoir_shell_logout_requested", False):
        surface = "logout"

    render_application_header(username, tier, selected_module)
    render_global_search(allowed_modules)
    return selected_module, surface


def _query_df(sql: str, params: Sequence[Any] = (), db_path: str = "enterprise_full_workspace.db") -> pd.DataFrame:
    try:
        with _db(db_path) as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def render_data_catalog(username: str, tier: str) -> None:
    st.markdown("## Data Catalog")
    st.caption("One place for governed datasets, quality, ownership, versions and downstream use.")

    df = _query_df(
        """SELECT dataset_id,name,source,fingerprint,owner,created_at,updated_at
           FROM os160_datasets ORDER BY updated_at DESC LIMIT 500"""
    )
    excel_catalog = st.session_state.get("excel_studio_dataset_catalog", [])
    if isinstance(excel_catalog, list) and excel_catalog:
        excel_rows = []
        for item in excel_catalog[-100:]:
            if isinstance(item, Mapping):
                source = item.get("source", {}) if isinstance(item.get("source"), Mapping) else {}
                excel_rows.append({
                    "dataset_id": item.get("dataset_id") or item.get("key") or item.get("filename") or "excel-session",
                    "name": item.get("filename") or item.get("dataset_id") or "Excel Studio dataset",
                    "source": item.get("filename") or source.get("name") or "Excel Studio",
                    "fingerprint": source.get("sha256") or item.get("signature") or "",
                    "owner": username,
                    "created_at": item.get("saved_utc") or item.get("created_at") or "",
                    "updated_at": item.get("saved_utc") or item.get("updated_at") or "",
                })
        if excel_rows:
            session_df = pd.DataFrame(excel_rows)
            if df.empty:
                df = session_df
            else:
                df = pd.concat([df, session_df], ignore_index=True).drop_duplicates(subset=["dataset_id"], keep="first")
    active, source_key = _first_dataframe()
    if not df.empty:
        search = st.text_input("Search datasets", placeholder="production, maintenance, SKU…", key="shoir_catalog_search")
        if search.strip():
            term = search.strip().lower()
            mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(term, regex=False)).any(axis=1)
            df = df[mask]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Registered datasets", f"{len(df):,}")
        c2.metric("Visible datasets", f"{len(df):,}")
        c3.metric("Current readiness", f"{data_readiness(active)['score']:.0f}%")
        c4.metric("Current state", infer_provenance())
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No durable dataset registrations are visible yet. The active session dataset is still available.")
        if not active.empty:
            ready = data_readiness(active)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Rows", f"{len(active):,}")
            c2.metric("Columns", f"{len(active.columns):,}")
            c3.metric("Readiness", f"{ready['score']:.0f}%")
            c4.metric("State", infer_provenance())
            st.dataframe(active.head(250), use_container_width=True, hide_index=True)
    with st.expander("Dataset details", expanded=False):
        st.markdown(f"**Source key:** \`{source_key or 'none'}\`")
        st.markdown(f"**Source:** \`{st.session_state.get('shoir_data_source', 'not declared')}\`")
        st.markdown(f"**Version:** \`{st.session_state.get('shoir_data_version', 'session/latest')}\`")
        st.markdown(f"**Hash:** \`{st.session_state.get('shoir_data_hash', 'not available')}\`")
        st.caption("The catalog is additive and reuses the existing dataset registry rather than creating a competing storage model.")


def render_run_center(username: str, tier: str) -> None:
    st.markdown("## Run Center")
    st.caption("Durable computation history, diagnostics and reproducibility context.")

    runs = _query_df(
        """SELECT run_id,module,job_type,status,progress,message,duration_ms,owner,created_at,updated_at
           FROM os160_runs ORDER BY created_at DESC LIMIT 300"""
    )
    if runs.empty:
        st.info("No durable runs are registered yet.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Runs", f"{len(runs):,}")
    c2.metric("Complete", f"{int((runs['status'].astype(str).str.lower() == 'completed').sum()):,}")
    c3.metric("Active", f"{int(runs['status'].astype(str).str.lower().isin(['running','queued','paused']).sum()):,}")
    c4.metric("Median duration", f"{runs['duration_ms'].dropna().median():,.0f} ms" if runs["duration_ms"].notna().any() else "—")

    status_values = sorted(runs["status"].dropna().astype(str).unique())
    status_filter = st.multiselect("Status", status_values, default=status_values, key="shoir_run_status")
    shown = runs[runs["status"].astype(str).isin(status_filter)] if status_filter else runs.iloc[0:0]
    st.dataframe(shown, use_container_width=True, hide_index=True)

    selected = st.selectbox("Inspect run", shown["run_id"].tolist() if not shown.empty else runs["run_id"].tolist(), key="shoir_run_select")
    one = runs[runs["run_id"] == selected]
    if not one.empty:
        row = one.iloc[0]
        with st.expander("Run evidence & replay context", expanded=True):
            try:
                payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            except Exception:
                payload = {"raw_payload": str(row["payload_json"])}
            manifest = {
                "shell_version": SHELL_VERSION,
                "run_id": str(row["run_id"]),
                "module": str(row["module"]),
                "job_type": str(row["job_type"]),
                "status": str(row["status"]),
                "progress": float(row["progress"]) if pd.notna(row["progress"]) else None,
                "message": str(row["message"]) if pd.notna(row["message"]) else "",
                "duration_ms": float(row["duration_ms"]) if pd.notna(row["duration_ms"]) else None,
                "owner": str(row["owner"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "data_state": infer_provenance(),
                "data_source": st.session_state.get("shoir_data_source"),
                "data_version": st.session_state.get("shoir_data_version"),
                "data_hash": st.session_state.get("shoir_data_hash"),
                "payload": payload,
            }
            st.json(manifest)
            st.download_button(
                "📦 Download reproducibility manifest",
                data=json.dumps(manifest, indent=2, default=str).encode("utf-8"),
                file_name=f"shoir_{row['run_id']}_reproducibility.json",
                mime="application/json",
                use_container_width=True,
                key=f"shoir_run_manifest_{row['run_id']}",
            )


def _parse_json_object(text_value: str) -> dict[str, Any]:
    parsed = json.loads(str(text_value or "{}"))
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed


def record_decision_outcome(decision_id: str, actual_metrics: Mapping[str, Any], owner: str, status: str = "Observed", notes: str = "") -> str:
    ensure_shell_schema()
    import hashlib
    fingerprint = hashlib.sha256(f"{decision_id}|{owner}|{_now()}".encode("utf-8")).hexdigest()[:10].upper()
    outcome_id = "OUT-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + fingerprint
    with _db() as conn:
        conn.execute(
            """INSERT INTO shoir_shell_decision_outcomes
               (outcome_id,decision_id,actual_metrics_json,observed_at,owner,status,notes)
               VALUES(?,?,?,?,?,?,?)""",
            (outcome_id, str(decision_id), json.dumps(dict(actual_metrics), sort_keys=True, default=str), _now(), owner, status, notes),
        )
        conn.commit()
    return outcome_id


def _decision_outcome_frame(decision_id: str) -> pd.DataFrame:
    return _query_df(
        """SELECT outcome_id,decision_id,actual_metrics_json,observed_at,owner,status,notes
           FROM shoir_shell_decision_outcomes
           WHERE decision_id=? ORDER BY observed_at DESC""",
        (decision_id,),
    )


def _flatten_variance(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for key in sorted(set(expected).intersection(actual)):
        try:
            exp = float(expected[key])
            act = float(actual[key])
            rows.append({"Metric": key, "Expected": exp, "Actual": act, "Variance": act - exp, "Variance %": ((act - exp) / abs(exp) * 100.0) if exp != 0 else math.nan})
        except (TypeError, ValueError):
            rows.append({"Metric": key, "Expected": expected[key], "Actual": actual[key], "Variance": "n/a", "Variance %": "n/a"})
    return pd.DataFrame(rows)


def render_decision_center(username: str, tier: str) -> None:
    st.markdown("## Decision Center")
    st.caption("Analysis → Scenario → Decision → Implementation → Actual KPI → Variance → Learning.")

    decisions = _query_df(
        """SELECT decision_id,title,module,status,metrics_json,assumptions_json,uncertainty_json,owner,created_at,updated_at
           FROM os160_decisions ORDER BY updated_at DESC LIMIT 250"""
    )
    if decisions.empty:
        st.info("No decision records exist yet. Create one from an engineering module or the 160 Operating System.")
        return

    outcome_count = int(_query_df("SELECT COUNT(*) AS n FROM shoir_shell_decision_outcomes").iloc[0]["n"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Decisions", f"{len(decisions):,}")
    c2.metric("Approved", f"{int(decisions['status'].astype(str).str.lower().eq('approved').sum()):,}")
    c3.metric("Implemented", f"{int(decisions['status'].astype(str).str.lower().isin(['implemented','verified']).sum()):,}")
    c4.metric("Outcomes", f"{outcome_count:,}")

    st.dataframe(decisions[["decision_id","title","module","status","owner","updated_at"]], use_container_width=True, hide_index=True)
    selected = st.selectbox("Decision to inspect", decisions["decision_id"].tolist(), key="shoir_decision_select")
    row = decisions[decisions["decision_id"] == selected].iloc[0]
    try:
        expected = json.loads(row["metrics_json"]) if row["metrics_json"] else {}
    except Exception:
        expected = {}

    left, right = st.columns([1, 1.25])
    with left:
        st.markdown("### Expected / governed baseline")
        st.json({
            "decision_id": str(row["decision_id"]),
            "title": str(row["title"]),
            "status": str(row["status"]),
            "metrics": expected,
            "assumptions": json.loads(row["assumptions_json"]) if row["assumptions_json"] else {},
            "uncertainty": json.loads(row["uncertainty_json"]) if row["uncertainty_json"] else {},
        })
        with st.form("shoir_decision_outcome_form"):
            actual_text = st.text_area("Actual KPI values (JSON)", value=json.dumps(expected, indent=2, default=str), height=180)
            notes = st.text_area("Observation / learning note", height=90)
            status = st.selectbox("Outcome status", ["Observed", "Verified", "Needs review"], key="shoir_outcome_status")
            submitted = st.form_submit_button("Record actual outcome", type="primary", use_container_width=True)
            if submitted:
                try:
                    actual = _parse_json_object(actual_text)
                    oid = record_decision_outcome(str(selected), actual, username, status=status, notes=notes)
                    st.session_state["shoir_latest_outcome_id"] = oid
                    st.success(f"Outcome {oid} recorded.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Outcome could not be recorded safely: {exc}")

    with right:
        st.markdown("### Expected vs actual")
        outcomes = _decision_outcome_frame(str(selected))
        if outcomes.empty:
            st.info("No post-implementation outcome has been recorded yet.")
        else:
            latest = outcomes.iloc[0]
            try:
                actual = json.loads(latest["actual_metrics_json"])
            except Exception:
                actual = {}
            variance = _flatten_variance(expected, actual)
            if variance.empty:
                st.info("No numeric overlapping KPIs were available for variance analysis.")
            else:
                st.dataframe(variance, use_container_width=True, hide_index=True)
                numeric_variance = variance[pd.to_numeric(variance["Variance"], errors="coerce").notna()].copy()
                if not numeric_variance.empty:
                    fig = px.bar(numeric_variance, x="Metric", y="Variance", title="Actual minus expected")
                    fig.update_layout(height=300, margin=dict(l=10,r=10,t=55,b=10))
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.caption(f"Latest outcome: {latest['outcome_id']} · {latest['observed_at']} · {latest['status']}")
            if latest["notes"]:
                st.markdown(f"**Learning note:** {latest['notes']}")


def render_trust_center(username: str, tier: str) -> None:
    """Evidence-led Knowledge & Trust workspace.

    The surface reports observed state, provenance and capability evidence
    separately. It never converts readiness into a blanket trust guarantee.
    """
    from shoir_160 import feature_matrix, feature_readiness_by_area

    metrics = _trust_metrics(username, tier)
    df, source_key = _first_dataframe()
    provenance = metrics["provenance"]
    docs = st.session_state.get("knowledge_documents", [])
    docs = docs if isinstance(docs, list) else []

    st.markdown(
        """
        <style>
        .kt-hero{padding:25px 28px;border-radius:22px;background:linear-gradient(135deg,#0b1220,#172554 55%,#0f766e);color:#fff;box-shadow:0 16px 36px rgba(15,23,42,.14);margin-bottom:16px}
        .kt-kicker{font-size:11px;font-weight:850;letter-spacing:.12em;text-transform:uppercase;color:#7dd3fc}
        .kt-title{font-size:30px;font-weight:900;letter-spacing:-.03em;margin-top:4px}
        .kt-sub{font-size:13px;color:#dbeafe;max-width:1000px;margin-top:7px}
        .kt-pill{display:inline-block;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);font-size:11px;margin:12px 6px 0 0}
        .kt-note{padding:13px 15px;border:1px solid #dbe4f0;border-radius:14px;background:#f8fafc;color:#475569}
        </style>
        <div class="kt-hero">
          <div class="kt-kicker">Knowledge · Evidence · Governance</div>
          <div class="kt-title">📚 Knowledge & Trust Center</div>
          <div class="kt-sub">See what Shoir-IE actually knows, where the current data came from, what has been verified, and which capabilities are evidence-backed. Imported, simulated and live states stay explicitly separated.</div>
          <span class="kt-pill">Provenance-aware</span><span class="kt-pill">Evidence ledger</span><span class="kt-pill">Knowledge library</span><span class="kt-pill">No blanket trust claims</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Data readiness", f"{metrics['data_readiness']:.0f}%")
    c2.metric("Current data state", provenance)
    c3.metric("Platform health", f"{metrics['platform_health']:.0f}%")
    c4.metric("Verified capabilities", f"{metrics['verified_capabilities']}/{metrics['capabilities']}")

    tabs = st.tabs(["Overview", "Knowledge Library", "Evidence & Lineage", "Capability Coverage"])

    with tabs[0]:
        left, right = st.columns([1.35, 1])
        with left:
            st.markdown("### Current evidence state")
            rows = [
                {"Signal":"Provenance","Value":provenance,"Meaning":"LIVE / IMPORTED / SIMULATED / DEMO state of the active workspace data."},
                {"Signal":"Active dataset","Value":source_key or "None","Meaning":"The dataset currently exposed to shared engineering surfaces."},
                {"Signal":"Rows × columns","Value":f"{len(df):,} × {len(df.columns):,}","Meaning":"Observed size of the active dataset."},
                {"Signal":"Data warnings","Value":str(len(metrics["warnings"])),"Meaning":"Deterministic data-readiness warnings from the current dataset."},
                {"Signal":"Assumptions recorded","Value":str(metrics["assumptions"]),"Meaning":"Explicit assumptions stored in the workspace."},
                {"Signal":"Knowledge documents","Value":str(len(docs)),"Meaning":"Documents currently linked to this workspace session."},
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            if source_key:
                st.markdown(
                    f"<div class='kt-note'><b>Trace:</b> {html.escape(source_key)} · "
                    f"<b>version:</b> {html.escape(str(st.session_state.get('shoir_data_version','session/latest')))} · "
                    f"<b>hash:</b> {html.escape(str(st.session_state.get('shoir_data_hash','not recorded'))[:20])}…</div>",
                    unsafe_allow_html=True,
                )
            for warning in metrics["warnings"]:
                st.warning(warning)
        with right:
            matrix = feature_matrix()
            coverage_counts = matrix["coverage"].value_counts().rename_axis("Coverage").reset_index(name="Features")
            if not coverage_counts.empty:
                st.plotly_chart(
                    px.donut(coverage_counts, names="Coverage", values="Features", title="Capability evidence coverage", hole=0.58),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
            st.caption("Capability coverage is a descriptive inventory of recorded evidence states, not a guarantee of runtime behavior.")

    with tabs[1]:
        st.markdown("### Knowledge library")
        st.caption("Add manuals, SOPs, standards, engineering notes and research references that Copilot can treat as workspace context.")
        try:
            from shoir_enterprise_services import render_knowledge_layer
            render_knowledge_layer(username)
        except Exception as exc:
            st.error(f"Knowledge library could not load safely: {type(exc).__name__}: {exc}")

    with tabs[2]:
        st.markdown("### Evidence and lineage")
        st.caption("Trace datasets and capability claims without exposing secrets.")
        evidence = _query_df(
            "SELECT source_type, COUNT(*) AS records, AVG(confidence) AS mean_confidence FROM os160_evidence_ledger GROUP BY source_type ORDER BY records DESC"
        )
        lineage = _query_df(
            "SELECT source_module, operation, COUNT(*) AS records FROM os160_lineage GROUP BY source_module, operation ORDER BY records DESC LIMIT 50"
        )
        a, b = st.columns(2)
        with a:
            st.markdown("#### Evidence ledger")
            if evidence.empty:
                st.info("No capability evidence records are currently indexed.")
            else:
                st.dataframe(evidence, use_container_width=True, hide_index=True)
                st.plotly_chart(
                    px.bar(evidence, x="source_type", y="records", title="Evidence records by source"),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
        with b:
            st.markdown("#### Data lineage")
            if lineage.empty:
                st.info("No lineage events are currently indexed.")
            else:
                st.dataframe(lineage, use_container_width=True, hide_index=True)
                st.plotly_chart(
                    px.bar(lineage.head(12), x="records", y="source_module", orientation="h", title="Lineage activity by module"),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
        st.markdown("#### Current run / version trace")
        trace = pd.DataFrame([
            {"Trace item":"Latest run ID","Value":st.session_state.get("shoir_latest_run_id") or st.session_state.get("last_run_id") or "Not assigned"},
            {"Trace item":"Data version","Value":st.session_state.get("shoir_data_version","session/latest")},
            {"Trace item":"Data source","Value":st.session_state.get("shoir_data_source") or source_key or "Not recorded"},
            {"Trace item":"Workspace","Value":st.session_state.get("shoir_workspace_name") or st.session_state.get("workspace") or "default"},
        ])
        st.dataframe(trace, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.markdown("### Capability coverage by area")
        by_area = feature_readiness_by_area()
        if not by_area.empty:
            fig = px.bar(
                by_area,
                x="area",
                y="Features",
                color="state",
                barmode="stack",
                title="Recorded capability state by product area",
            )
            fig.update_layout(height=420, xaxis_title="", yaxis_title="Capabilities", legend_title="State")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.dataframe(by_area, use_container_width=True, hide_index=True)
        st.markdown("#### Verified capability index")
        matrix = feature_matrix()
        verified = matrix[matrix["coverage"].astype(str).str.casefold().eq("verified")]
        if verified.empty:
            st.info("No capabilities are currently marked Verified in the evidence matrix.")
        else:
            st.dataframe(
                verified[["id","name","area","state","coverage","evidence"]],
                use_container_width=True,
                hide_index=True,
            )

    st.caption(
        "Trust is built from traceable evidence: the center reports observed data, provenance, capability records and governance context separately rather than using a single confidence score."
    )


def render_presentation_mode(username: str, tier: str, module: str) -> None:
    st.markdown("<style>section[data-testid='stSidebar']{display:none !important;} .block-container{max-width:1450px !important;}</style>", unsafe_allow_html=True)
    df, source_key = _first_dataframe()
    provenance = infer_provenance()
    ready = data_readiness(df)
    st.markdown(
        f"""
<div style='padding:25px 28px;border-radius:23px;background:linear-gradient(135deg,#08111f,#172554 52%,#0f766e);color:white;margin-bottom:18px'>
  <div style='font-size:11px;font-weight:900;letter-spacing:.14em;color:#7dd3fc'>SHOIR-IE · PRESENTATION MODE</div>
  <div style='font-size:34px;font-weight:900;letter-spacing:-.03em;margin-top:4px'>{module}</div>
  <div style='font-size:14px;color:#dbeafe;margin-top:8px'>Engineering decision workspace · {provenance}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    numeric = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
    metrics = []
    for col in numeric[:4]:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if not series.empty:
            metrics.append((str(col), float(series.mean()), float(series.iloc[-1] - series.mean())))
    fallback = [("Readiness", ready["score"], None), ("Rows", len(df), None), ("Columns", len(df.columns), None), ("State", provenance, None)]
    while len(metrics) < 4:
        metrics.append(fallback[len(metrics)])

    cols = st.columns(4)
    for c, (label, value, delta) in zip(cols, metrics[:4]):
        c.metric(label, f"{value:.2f}" if isinstance(value, float) else str(value), f"{delta:+.2f}" if isinstance(delta, (int,float)) else None)

    st.markdown("### Decision view")
    if numeric:
        y = numeric[0]
        x_candidates = [c for c in df.columns if c != y]
        x = x_candidates[0] if x_candidates else None
        plot = df[[x,y]].dropna() if x else df[[y]].dropna()
        fig = px.line(plot, x=x, y=y, markers=True, title=f"{module} · {y}") if x else px.line(plot, y=y, title=f"{module} · {y}")
        fig.update_layout(height=430, margin=dict(l=8,r=8,t=60,b=8))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No numeric active dataset is available for a primary trend chart.")

    st.markdown(
        f"""
<div class="shoir-shell-card">
  <b>Evidence context</b>
  <div class="shoir-shell-muted">Dataset source: {source_key or 'none'} · Readiness: {ready['score']:.1f}% · State: {provenance}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    if st.button("← Return to engineering workspace", type="primary", use_container_width=True, key="shoir_presentation_return"):
        st.session_state.pop("shoir_shell_surface", None)
        st.rerun()


def render_new_study(username: str, tier: str, current_module: str) -> None:
    st.markdown("## New Engineering Study")
    st.caption("Start with an objective, then let the common workflow connect data, modeling, scenarios and decisions.")
    title = st.text_input("Study title", value=f"{current_module} study", key="shoir_new_study_title")
    objective = st.text_area("Decision objective", placeholder="What operational or research decision are you trying to support?", height=110, key="shoir_new_study_objective")
    if st.button("Create study workspace", type="primary", use_container_width=True, key="shoir_create_study"):
        try:
            from shoir_unified_product import create_unified_study
            sid = create_unified_study(title, current_module, username, objective or "Engineering decision support")
            st.session_state["unified_study_id"] = sid
            st.session_state["shoir_project_name"] = title
            st.success(f"Study {sid} created.")
        except Exception as exc:
            st.error(f"Study could not be created safely: {exc}")
    st.info("Existing module data is preserved; this action creates a governed study container rather than replacing your current workspace.")


def render_shell_surface(surface: str, username: str, tier: str, module: str, allowed_modules: Sequence[str], is_admin: bool = False) -> None:
    surface = str(surface or "")
    if surface == "home":
        render_industrial_home(username, tier)
    elif surface == "catalog":
        render_data_catalog(username, tier)
    elif surface == "runs":
        render_run_center(username, tier)
    elif surface == "decisions":
        render_decision_center(username, tier)
    elif surface == "trust":
        render_trust_center(username, tier)
    elif surface == "presentation":
        render_presentation_mode(username, tier, module)
    elif surface == "new_study":
        render_new_study(username, tier, module)
    elif surface == "workbench":
        try:
            from shoir_adoption_engine import render_adoption_center
            render_adoption_center(username, tier, initial_tab="Home")
        except Exception as exc:
            st.error(f"Workbench could not render safely: {exc}")
    elif surface == "copilot":
        try:
            from shoir_copilot_orchestrator import build_workflow_plan
            df, _ = _first_dataframe()
            if df.empty:
                st.info("Upload or select a dataset before starting a module-aware Copilot workflow.")
            else:
                prompt = st.text_area("Ask Shoir to orchestrate the engineering task", placeholder="Clean this workbook, determine data readiness, run an analysis and prepare the evidence pack.", height=120, key="shoir_shell_copilot_prompt")
                if st.button("Plan workflow", type="primary", use_container_width=True, key="shoir_shell_copilot_plan"):
                    st.session_state["shoir_shell_copilot_plan_result"] = build_workflow_plan(prompt, module, df)
                plan = st.session_state.get("shoir_shell_copilot_plan_result")
                if plan:
                    st.markdown("### Proposed workflow")
                    for idx, step in enumerate(plan.get("steps", []), 1):
                        st.markdown(f"{idx}. **{step.get('tool','step')}** — {step.get('detail','')}")
                    st.caption("State-changing operations remain approval-gated by the existing Copilot/runtime controls.")
        except Exception as exc:
            st.warning(f"Copilot shell could not render: {exc}")
    elif surface == "os":
        try:
            from shoir_160 import render_160_command_center
            render_160_command_center(username, tier)
        except Exception as exc:
            st.error(f"Industrial Operating System could not render safely: {exc}")
    elif surface == "excellence":
        try:
            from industrial_excellence_hub import render_platform_excellence_hub
            render_platform_excellence_hub(username, tier)
        except Exception as exc:
            st.error(f"Excellence Hub could not render safely: {exc}")
    elif surface == "admin" and is_admin:
        st.info("Administrative capabilities remain in the existing Admin Panel. The application shell keeps them visually separate from engineering workflows.")
    elif surface == "edit_account":
        st.session_state["selected_nav"] = "Edit Account"
    elif surface == "logout":
        st.session_state["selected_nav"] = "Dashboard"
        user = st.session_state.get("current_user", "")
        if user:
            try:
                from workspace_persistence import save_user_workspace
                save_user_workspace(user, st.session_state)
            except Exception:
                pass
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


def render_post_module_context(module: str, username: str, tier: str) -> None:
    provenance = infer_provenance()
    render_module_workflow(module, provenance)
    render_inspector(module, username, tier)


def shell_health_snapshot() -> dict[str, Any]:
    df, source_key = _first_dataframe()
    return {
        "shell_version": SHELL_VERSION,
        "provenance": infer_provenance(),
        "source_key": source_key,
        "readiness": data_readiness(df),
        "spec_updates": dict(PASTED_SPEC_UPDATES),
    }
