"""Unified Shoir-IE application shell and cross-cutting engineering surfaces.

This layer consolidates the existing Industrial Home, 160 Operating System,
Excellence Hub, Global Product Dock and module navigation into one calm shell.
It deliberately reuses existing specialist modules instead of replacing them.
"""

from __future__ import annotations

from shoir_repository import sqlite_connect as shoir_sqlite_connect
import logging

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
    return shoir_sqlite_connect(path, timeout=30)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_shell_schema(db_path: str = "enterprise_full_workspace.db") -> None:
    try:
        with _db(db_path) as conn:
            for statement in SCHEMA_SQL.strip().split(";\n"):
                if statement.strip():
                    conn.execute(statement)
            conn.commit()
    except Exception as exc:
        logging.getLogger(__name__).warning("Optional operation failed safely: %s: %s", type(exc).__name__, exc)


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


def render_application_shell(
    *,
    username: str,
    tier: str,
    allowed_modules: Sequence[str],
    current_module: str | None = None,
    is_admin: bool = False,
) -> tuple[str, str | None]:
    ensure_shell_schema()
    try:
        from shoir_universal_platform_kernel import install_visualization_contract
        install_visualization_contract()
    except Exception as exc:
        logging.getLogger(__name__).warning("Optional operation failed safely: %s: %s", type(exc).__name__, exc)
    render_shell_css()

    nav_labels = list(NAV_GROUPS.keys())
    current_section = str(st.session_state.get("shoir_shell_section", "HOME"))
    try:
        current_index = nav_labels.index(current_section)
    except ValueError:
        current_index = 0

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
        st.session_state["shoir_shell_section"] = section

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
    else:
        st.session_state["selected_nav"] = "Dashboard"

    if section == "WORKBENCH":
        surface = surface or "workbench"
    elif section == "DATA":
        surface = surface or "catalog"
    elif section == "DECISIONS":
        surface = surface or "decisions"
    elif section == "KNOWLEDGE":
        surface = surface or "trust"

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
    st.markdown("## Trust Center")
    st.caption("A factual status surface for data, provenance, computation and governance context.")

    metrics = _trust_metrics(username, tier)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Data readiness", f"{metrics['data_readiness']:.0f}%")
    c2.metric("Platform health", f"{metrics['platform_health']:.0f}%")
    c3.metric("Verified capabilities", f"{metrics['verified_capabilities']}/{metrics['capabilities']}")
    c4.metric("Assumptions", str(metrics["assumptions"]))

    rows = [
        {"Control": "Data provenance", "Status": metrics["provenance"], "Detail": "Explicit platform state contract"},
        {"Control": "Durable session", "Status": "Connected" if metrics["durable_session"] else "Local/session fallback", "Detail": "Workspace persistence connection state"},
        {"Control": "Uncertainty", "Status": "Present" if metrics["assumptions"] > 0 else "None recorded", "Detail": "Assumption count is shown separately from measured outputs"},
        {"Control": "Platform health", "Status": f"{metrics['platform_health']:.0f}%", "Detail": "Existing 160 OS health snapshot"},
        {"Control": "Capability evidence", "Status": f"{metrics['verified_capabilities']}/{metrics['capabilities']}", "Detail": "Existing capability evidence/verification catalog"},
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with st.expander("Trust interpretation", expanded=False):
        st.markdown("Trust metrics are descriptive, not guarantees. Imported, simulated and demo content remain distinct labels; external connectivity is only treated as live when the application explicitly declares it.")
    for warning in metrics["warnings"]:
        st.warning(warning)


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
    if surface == "catalog":
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
                    st.session_state["shoir_shell_copilot_plan"] = build_workflow_plan(prompt, module, df)
                plan = st.session_state.get("shoir_shell_copilot_plan")
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
            except Exception as exc:
                logging.getLogger(__name__).warning("Optional operation failed safely: %s: %s", type(exc).__name__, exc)
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


def render_post_module_context(module: str, username: str, tier: str) -> None:
    """Apply the universal platform kernel before every specialist renderer."""
    try:
        from shoir_universal_platform_kernel import install_and_render_module_context
        install_and_render_module_context(str(module), show_copilot=True)
    except Exception as _kernel_error:
        # Preserve the existing shell context if the additive kernel is unavailable.
        provenance = infer_provenance()
        render_module_workflow(module, provenance)
        render_inspector(module, username, tier)
        with st.expander("Universal platform kernel diagnostic", expanded=False):
            st.code(f"{type(_kernel_error).__name__}: {_kernel_error}")


def shell_health_snapshot() -> dict[str, Any]:
    df, source_key = _first_dataframe()
    return {
        "shell_version": SHELL_VERSION,
        "provenance": infer_provenance(),
        "source_key": source_key,
        "readiness": data_readiness(df),
        "spec_updates": dict(PASTED_SPEC_UPDATES),
    }
