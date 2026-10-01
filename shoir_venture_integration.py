"""Shoir-IE venture/incubator capabilities integrated into existing modules.

This is intentionally NOT a new top-level destination.  It adds governed tabs to
existing Shoir-IE workspaces and persists the underlying venture objects in the
same workspace database used by the platform.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from shoir_repository import sqlite_connect


DB_PATH = "enterprise_full_workspace.db"


MODULE_TABS = {
    "Industrial Operating System": ("venture", "readiness", "demo"),
    "Industrial Problem Solver": ("venture", "onboarding"),
    "Industrial Data Model & Digital Thread": ("stakeholders", "cases"),
    "Global Project & Digital Thread": ("stakeholders", "cases"),
    "Experiment Lab": ("pilots", "comparison"),
    "Experiment Engine": ("hypothesis", "comparison"),
    "Research AI": ("hypothesis", "evidence"),
    "Capital Investment & Engineering Economics": ("business", "roi"),
    "Engineering Decision Center": ("business", "roi", "cases"),
    "Engineering Model Registry": ("evidence", "data_room"),
    "Executive Report Center": ("data_room", "cases", "demo"),
    "Industrial Control Center": ("traction", "readiness"),
    "Benchmarking & Engineering Standards": ("market", "readiness"),
    "Engineering Validation Center": ("readiness", "evidence"),
    "Industrial Workbook": ("onboarding", "venture"),
}

SCHEMA = {
    "venture_projects": """
        CREATE TABLE IF NOT EXISTS venture_projects (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            name TEXT NOT NULL, problem TEXT, customer TEXT, stage TEXT,
            value_proposition TEXT, status TEXT, created_at TEXT, updated_at TEXT
        )
    """,
    "venture_stakeholders": """
        CREATE TABLE IF NOT EXISTS venture_stakeholders (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            name TEXT NOT NULL, organization TEXT, role TEXT, segment TEXT,
            status TEXT, notes TEXT, created_at TEXT, updated_at TEXT
        )
    """,
    "venture_pilots": """
        CREATE TABLE IF NOT EXISTS venture_pilots (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            name TEXT NOT NULL, customer TEXT, hypothesis TEXT, baseline REAL,
            target REAL, actual REAL, status TEXT, start_date TEXT, end_date TEXT,
            created_at TEXT, updated_at TEXT
        )
    """,
    "venture_hypotheses": """
        CREATE TABLE IF NOT EXISTS venture_hypotheses (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            statement TEXT NOT NULL, metric TEXT, threshold REAL, result REAL,
            confidence REAL, status TEXT, decision TEXT, created_at TEXT, updated_at TEXT
        )
    """,
    "venture_evidence": """
        CREATE TABLE IF NOT EXISTS venture_evidence (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            title TEXT NOT NULL, evidence_type TEXT, source TEXT, strength TEXT,
            linked_object TEXT, content TEXT, sha256 TEXT, created_at TEXT, updated_at TEXT
        )
    """,
    "venture_business_models": """
        CREATE TABLE IF NOT EXISTS venture_business_models (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            name TEXT NOT NULL, pricing_model TEXT, price REAL, units REAL,
            variable_cost REAL, fixed_cost REAL, gross_margin REAL,
            notes TEXT, created_at TEXT, updated_at TEXT
        )
    """,
    "venture_market_items": """
        CREATE TABLE IF NOT EXISTS venture_market_items (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            name TEXT NOT NULL, item_type TEXT, segment TEXT, source TEXT,
            positioning TEXT, strengths TEXT, gaps TEXT, notes TEXT,
            created_at TEXT, updated_at TEXT
        )
    """,
    "venture_investor_docs": """
        CREATE TABLE IF NOT EXISTS venture_investor_docs (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            title TEXT NOT NULL, category TEXT, status TEXT, source TEXT,
            description TEXT, artifact_id TEXT, created_at TEXT, updated_at TEXT
        )
    """,
    "venture_cases": """
        CREATE TABLE IF NOT EXISTS venture_cases (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            title TEXT NOT NULL, customer TEXT, problem TEXT, intervention TEXT,
            baseline REAL, outcome REAL, unit TEXT, evidence_id TEXT,
            status TEXT, narrative TEXT, created_at TEXT, updated_at TEXT
        )
    """,
    "venture_events": """
        CREATE TABLE IF NOT EXISTS venture_events (
            id TEXT PRIMARY KEY, workspace TEXT NOT NULL, owner TEXT NOT NULL,
            event_type TEXT NOT NULL, object_type TEXT, object_id TEXT,
            payload TEXT, created_at TEXT
        )
    """,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ctx() -> tuple[str, str]:
    owner = str(st.session_state.get("current_user") or st.session_state.get("username") or "anonymous")
    workspace = str(
        st.session_state.get("shoir_workspace_name")
        or st.session_state.get("active_workspace_name")
        or st.session_state.get("workspace")
        or "default"
    )
    return owner, workspace


def _db():
    return sqlite_connect(DB_PATH, timeout=30)


def ensure_venture_schema() -> None:
    with _db() as conn:
        for sql in SCHEMA.values():
            conn.execute(sql)
        conn.commit()


def _id(prefix: str, payload: Any = "") -> str:
    raw = f"{prefix}|{payload}|{_now()}|{uuid.uuid4().hex}"
    return f"{prefix}-{hashlib.sha256(raw.encode()).hexdigest()[:14].upper()}"


def _event(event_type: str, object_type: str = "", object_id: str = "", payload: Any = None) -> None:
    owner, workspace = _ctx()
    with _db() as conn:
        conn.execute(
            "INSERT INTO venture_events(id,workspace,owner,event_type,object_type,object_id,payload,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (_id("EVT"), workspace, owner, event_type, object_type, object_id, json.dumps(payload or {}, default=str), _now()),
        )
        conn.commit()


def _insert(table: str, fields: dict[str, Any]) -> str:
    owner, workspace = _ctx()
    record_id = fields.pop("id", None) or _id(table[:4].upper())
    fields.update({"id": record_id, "workspace": workspace, "owner": owner, "created_at": _now(), "updated_at": _now()})
    columns = list(fields)
    placeholders = ",".join("?" for _ in columns)
    with _db() as conn:
        conn.execute(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
            [fields[c] for c in columns],
        )
        conn.commit()
    _event("created", table, record_id, fields)
    return record_id


def _frame(table: str) -> pd.DataFrame:
    _, workspace = _ctx()
    with _db() as conn:
        return pd.read_sql_query(
            f"SELECT * FROM {table} WHERE workspace=? ORDER BY updated_at DESC",
            conn, params=[workspace],
        )


def _delete(table: str, record_id: str) -> None:
    _, workspace = _ctx()
    with _db() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id=? AND workspace=?", (record_id, workspace))
        conn.commit()
    _event("deleted", table, record_id)


def _metric_value(value: Any) -> float | None:
    try:
        x = float(value)
        return x if pd.notna(x) else None
    except Exception:
        return None


def _add_delete_control(table: str, frame: pd.DataFrame, key: str) -> None:
    if frame.empty:
        return
    ids = frame["id"].astype(str).tolist()
    selected = st.selectbox("Select record", ids, key=f"{key}_delete_select")
    if st.button("Delete selected record", key=f"{key}_delete", use_container_width=True):
        _delete(table, selected)
        st.rerun()


def _header(title: str, subtitle: str) -> None:
    st.markdown(f"### {title}")
    st.caption(subtitle)


def _render_venture() -> None:
    _header("Venture Studio", "Develop the venture inside the existing Industrial Operating System: problem → customer → value → pilot → evidence → decision.")
    df = _frame("venture_projects")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Venture projects", len(df))
    c2.metric("Active", int((df["status"].astype(str).str.lower() == "active").sum()) if not df.empty else 0)
    c3.metric("Validated", int((df["stage"].astype(str).str.lower() == "validated").sum()) if not df.empty else 0)
    c4.metric("Customers named", int(df["customer"].replace("", pd.NA).notna().sum()) if not df.empty else 0)
    with st.form("venture_project_form"):
        name = st.text_input("Venture / project name")
        problem = st.text_area("Problem to solve")
        customer = st.text_input("Target customer / segment")
        value = st.text_area("Value proposition")
        stage = st.selectbox("Stage", ["Idea", "Problem validated", "Solution validated", "Pilot", "Validated", "Scale"])
        status = st.selectbox("Status", ["Draft", "Active", "Paused", "Validated", "Archived"])
        if st.form_submit_button("Create venture workspace record", type="primary") and name.strip():
            _insert("venture_projects", {"name": name.strip(), "problem": problem, "customer": customer, "value_proposition": value, "stage": stage, "status": status})
            st.success("Venture record persisted in the active workspace.")
            st.rerun()
    if not df.empty:
        st.dataframe(df[["name","customer","stage","status","updated_at"]], use_container_width=True, hide_index=True)


def _render_stakeholders() -> None:
    _header("Customer & Stakeholder Hub", "CRM-style stakeholder records connected to pilots, evidence and case studies.")
    df = _frame("venture_stakeholders")
    with st.form("stakeholder_form"):
        a,b = st.columns(2)
        name = a.text_input("Person / organization")
        organization = b.text_input("Organization")
        role = a.text_input("Role")
        segment = b.text_input("Segment")
        status = a.selectbox("Relationship status", ["Prospect","Interviewed","Pilot","Customer","Champion","Inactive"])
        notes = b.text_area("Notes")
        if st.form_submit_button("Add stakeholder", type="primary") and name.strip():
            _insert("venture_stakeholders", {"name":name.strip(),"organization":organization,"role":role,"segment":segment,"status":status,"notes":notes})
            st.success("Stakeholder saved.")
            st.rerun()
    if not df.empty:
        st.dataframe(df[["name","organization","role","segment","status","notes"]], use_container_width=True, hide_index=True)
        _add_delete_control("venture_stakeholders", df, "stakeholder")


def _render_pilots() -> None:
    _header("Pilot Manager", "Plan pilots, record baselines/targets/actuals, and keep pilot outcomes tied to evidence.")
    df = _frame("venture_pilots")
    with st.form("pilot_form"):
        name = st.text_input("Pilot name")
        customer = st.text_input("Customer")
        hypothesis = st.text_area("Pilot hypothesis")
        a,b,c = st.columns(3)
        baseline = a.number_input("Baseline", value=0.0)
        target = b.number_input("Target", value=0.0)
        actual = c.number_input("Actual", value=0.0)
        status = st.selectbox("Status", ["Planned","Running","Completed","Verified","Stopped"])
        if st.form_submit_button("Create / record pilot", type="primary") and name.strip():
            _insert("venture_pilots", {"name":name.strip(),"customer":customer,"hypothesis":hypothesis,"baseline":baseline,"target":target,"actual":actual,"status":status,"start_date":"","end_date":""})
            st.success("Pilot saved.")
            st.rerun()
    if not df.empty:
        display = df[["name","customer","status","baseline","target","actual"]].copy()
        display["Target gap"] = pd.to_numeric(display["actual"],errors="coerce") - pd.to_numeric(display["target"],errors="coerce")
        st.dataframe(display, use_container_width=True, hide_index=True)


def _render_hypothesis() -> None:
    _header("Hypothesis → Evidence", "Convert a testable claim into a measured result and an explicit evidence-backed decision.")
    df = _frame("venture_hypotheses")
    with st.form("hypothesis_form"):
        statement = st.text_area("Hypothesis statement")
        metric = st.text_input("Measured metric")
        a,b,c = st.columns(3)
        threshold = a.number_input("Success threshold", value=0.0)
        result = b.number_input("Observed result", value=0.0)
        confidence = c.slider("Confidence", 0.0, 1.0, 0.5, 0.05)
        status = st.selectbox("Evidence status", ["Untested","Testing","Supported","Inconclusive","Refuted"])
        decision = st.text_input("Decision / next action")
        if st.form_submit_button("Record hypothesis result", type="primary") and statement.strip():
            _insert("venture_hypotheses", {"statement":statement.strip(),"metric":metric,"threshold":threshold,"result":result,"confidence":confidence,"status":status,"decision":decision})
            st.success("Hypothesis and result persisted.")
            st.rerun()
    if not df.empty:
        st.dataframe(df[["statement","metric","threshold","result","confidence","status","decision"]], use_container_width=True, hide_index=True)


def _render_business() -> None:
    _header("Business Model + Pricing", "Model pricing, unit economics and gross margin using explicit assumptions.")
    df = _frame("venture_business_models")
    with st.form("business_form"):
        name = st.text_input("Model name")
        pricing = st.selectbox("Pricing model", ["Subscription","Per study","Per site","Per user","Usage-based","Enterprise contract","Custom"])
        a,b,c,d = st.columns(4)
        price = a.number_input("Price / unit", min_value=0.0, value=100.0)
        units = b.number_input("Units / period", min_value=0.0, value=1.0)
        variable = c.number_input("Variable cost / unit", min_value=0.0, value=20.0)
        fixed = d.number_input("Fixed cost / period", min_value=0.0, value=0.0)
        margin = ((price-variable)/price*100.0) if price else 0.0
        st.metric("Gross margin", f"{margin:.1f}%")
        notes = st.text_area("Assumptions / notes")
        if st.form_submit_button("Save business model", type="primary") and name.strip():
            _insert("venture_business_models", {"name":name.strip(),"pricing_model":pricing,"price":price,"units":units,"variable_cost":variable,"fixed_cost":fixed,"gross_margin":margin,"notes":notes})
            st.success("Business model saved.")
            st.rerun()
    if not df.empty:
        st.dataframe(df[["name","pricing_model","price","units","variable_cost","fixed_cost","gross_margin"]], use_container_width=True, hide_index=True)


def _render_roi() -> None:
    _header("ROI / Value Evidence", "Connect baseline and measured outcome values rather than treating an estimate as a verified impact claim.")
    pilots = _frame("venture_pilots")
    cases = _frame("venture_cases")
    rows = []
    if not pilots.empty:
        for r in pilots.to_dict("records"):
            base, actual = _metric_value(r.get("baseline")), _metric_value(r.get("actual"))
            if base is not None and actual is not None:
                rows.append({"Source":"Pilot","Name":r["name"],"Baseline":base,"Actual":actual,"Delta":actual-base,"Status":r["status"]})
    if not cases.empty:
        for r in cases.to_dict("records"):
            base, outcome = _metric_value(r.get("baseline")), _metric_value(r.get("outcome"))
            if base is not None and outcome is not None:
                rows.append({"Source":"Case","Name":r["title"],"Baseline":base,"Actual":outcome,"Delta":outcome-base,"Status":r["status"]})
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Record a pilot or case baseline/outcome to generate measured value evidence.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.plotly_chart(px.bar(df, x="Name", y="Delta", color="Source", title="Measured value delta"), use_container_width=True)
    st.caption("Positive/negative direction is domain-dependent; interpret the delta using the KPI definition and unit.")


def _render_evidence() -> None:
    _header("Evidence Vault", "A durable evidence index for sources, artifacts, hypotheses, pilots and decisions.")
    df = _frame("venture_evidence")
    with st.form("evidence_form"):
        title = st.text_input("Evidence title")
        typ = st.selectbox("Type", ["Pilot result","Experiment result","Customer interview","Usage data","Financial","Technical","Market","Other"])
        source = st.text_input("Source / artifact reference")
        strength = st.selectbox("Strength", ["Unassessed","Weak","Moderate","Strong","Verified"])
        linked = st.text_input("Linked hypothesis / pilot / decision ID")
        content = st.text_area("Evidence note")
        if st.form_submit_button("Store evidence", type="primary") and title.strip():
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            _insert("venture_evidence", {"title":title.strip(),"evidence_type":typ,"source":source,"strength":strength,"linked_object":linked,"content":content,"sha256":digest})
            st.success("Evidence stored with a content hash.")
            st.rerun()
    if not df.empty:
        st.dataframe(df[["id","title","evidence_type","source","strength","linked_object","sha256","updated_at"]], use_container_width=True, hide_index=True)


def _render_data_room() -> None:
    _header("Investor Data Room", "Organize investor-facing evidence without duplicating the underlying project, experiment or report artifacts.")
    df = _frame("venture_investor_docs")
    with st.form("data_room_form"):
        title = st.text_input("Document / artifact title")
        category = st.selectbox("Category", ["Company","Product","Market","Traction","Pilots","Financial","Technology","Legal","Evidence"])
        status = st.selectbox("Status", ["Draft","Ready","Verified","Needs update"])
        source = st.text_input("Source / file reference")
        artifact = st.text_input("Existing Shoir-IE artifact ID (optional)")
        description = st.text_area("Description")
        if st.form_submit_button("Add to data room", type="primary") and title.strip():
            _insert("venture_investor_docs", {"title":title.strip(),"category":category,"status":status,"source":source,"description":description,"artifact_id":artifact})
            st.success("Data-room index entry saved.")
            st.rerun()
    if not df.empty:
        st.dataframe(df[["title","category","status","source","artifact_id","updated_at"]], use_container_width=True, hide_index=True)


def _render_traction() -> None:
    _header("Product / Traction Analytics", "A workspace-level operating view of projects, stakeholders, pilots, hypotheses, evidence and cases.")
    tables = {
        "Projects": _frame("venture_projects"),
        "Stakeholders": _frame("venture_stakeholders"),
        "Pilots": _frame("venture_pilots"),
        "Hypotheses": _frame("venture_hypotheses"),
        "Evidence": _frame("venture_evidence"),
        "Cases": _frame("venture_cases"),
    }
    c = st.columns(6)
    for i,(label,frame) in enumerate(tables.items()):
        c[i].metric(label, len(frame))
    if any(not x.empty for x in tables.values()):
        trend = pd.DataFrame({"Object":[k for k,v in tables.items()],"Count":[len(v) for v in tables.values()]})
        st.plotly_chart(px.bar(trend,x="Object",y="Count",title="Workspace activity footprint"),use_container_width=True)
    events = _frame("venture_events")
    if not events.empty:
        st.caption(f"{len(events)} venture lifecycle events recorded in this workspace.")
        st.dataframe(events[["event_type","object_type","object_id","created_at"]].head(50),use_container_width=True,hide_index=True)


def _render_market() -> None:
    _header("Market & Competitive Intelligence", "Record market/competitor observations and link them to positioning and readiness work.")
    df = _frame("venture_market_items")
    with st.form("market_form"):
        name = st.text_input("Company / market item")
        typ = st.selectbox("Item type", ["Competitor","Customer segment","Market signal","Partner","Alternative"])
        segment = st.text_input("Segment")
        source = st.text_input("Source")
        positioning = st.text_area("Positioning / observation")
        strengths = st.text_area("Strengths")
        gaps = st.text_area("Gaps / risks")
        if st.form_submit_button("Save market intelligence", type="primary") and name.strip():
            _insert("venture_market_items", {"name":name.strip(),"item_type":typ,"segment":segment,"source":source,"positioning":positioning,"strengths":strengths,"gaps":gaps,"notes":""})
            st.success("Market intelligence saved.")
            st.rerun()
    if not df.empty:
        st.dataframe(df[["name","item_type","segment","source","positioning","strengths","gaps"]],use_container_width=True,hide_index=True)


def _readiness_scores() -> dict[str,float]:
    projects = _frame("venture_projects")
    stakeholders = _frame("venture_stakeholders")
    pilots = _frame("venture_pilots")
    hypotheses = _frame("venture_hypotheses")
    evidence = _frame("venture_evidence")
    cases = _frame("venture_cases")
    return {
        "Problem": 100.0 if (not projects.empty and projects["problem"].astype(str).str.strip().ne("").any()) else 0.0,
        "Customer": min(100.0, len(stakeholders) * 20.0),
        "Pilot": min(100.0, len(pilots) * 50.0),
        "Evidence": min(100.0, len(evidence) * 25.0),
        "Hypothesis": min(100.0, len(hypotheses) * 25.0),
        "Case": min(100.0, len(cases) * 50.0),
    }


def _render_readiness() -> None:
    _header("Product-Market-Fit / Readiness Dashboard", "A transparent readiness view derived from recorded workspace evidence; it is not a predictive market verdict.")
    scores = _readiness_scores()
    frame = pd.DataFrame({"Dimension":list(scores),"Coverage":list(scores.values())})
    st.plotly_chart(px.bar(frame,x="Dimension",y="Coverage",range_y=[0,100],title="Evidence coverage by readiness dimension"),use_container_width=True)
    st.dataframe(frame,use_container_width=True,hide_index=True)
    missing = frame.loc[frame["Coverage"] < 100, "Dimension"].tolist()
    if missing:
        st.warning("Evidence gaps: " + ", ".join(missing))
    else:
        st.success("All tracked readiness dimensions have recorded coverage. Verification remains evidence-specific.")


def _render_comparison() -> None:
    _header("Pilot / Experiment Comparison", "Compare baseline, target and observed outcomes from the same workspace.")
    pilots = _frame("venture_pilots")
    if pilots.empty:
        st.info("No pilots recorded yet.")
        return
    d = pilots[["name","baseline","target","actual","status"]].copy()
    for col in ["baseline","target","actual"]:
        d[col] = pd.to_numeric(d[col],errors="coerce")
    st.dataframe(d,use_container_width=True,hide_index=True)
    long = d.melt(id_vars=["name","status"],value_vars=["baseline","target","actual"],var_name="Measure",value_name="Value").dropna()
    if not long.empty:
        st.plotly_chart(px.bar(long,x="name",y="Value",color="Measure",barmode="group",title="Pilot outcome comparison"),use_container_width=True)


def _render_onboarding() -> None:
    _header("Guided Onboarding", "A first-run path embedded in the existing module: define the problem, identify the customer, load evidence, run a pilot and create a decision.")
    steps = [
        ("1","Define problem","Create a venture/project record."),
        ("2","Identify customer","Add a stakeholder/customer record."),
        ("3","Create test","Create a pilot or hypothesis."),
        ("4","Capture evidence","Store the result/source in Evidence Vault."),
        ("5","Decide","Use Decision Center with the recorded evidence."),
    ]
    for number,title,detail in steps:
        st.markdown(f"**{number}. {title}** — {detail}")
    if st.button("Initialize a guided starter workspace", type="primary", use_container_width=True, key="venture_onboarding_seed"):
        if _frame("venture_projects").empty:
            _insert("venture_projects", {"name":"Starter Venture Workspace","problem":"Define the operational/customer problem","customer":"Initial target customer","value_proposition":"Value proposition to validate","stage":"Idea","status":"Active"})
        if _frame("venture_hypotheses").empty:
            _insert("venture_hypotheses", {"statement":"The proposed solution improves the selected KPI versus baseline.","metric":"Primary KPI","threshold":0.0,"result":0.0,"confidence":0.0,"status":"Untested","decision":"Run pilot"})
        st.success("Guided workspace initialized with editable records.")
        st.rerun()


def _render_cases() -> None:
    _header("Case-Study Management", "Turn verified pilot/engineering outcomes into reusable customer stories linked to evidence.")
    df = _frame("venture_cases")
    with st.form("case_form"):
        title = st.text_input("Case-study title")
        customer = st.text_input("Customer")
        problem = st.text_area("Problem")
        intervention = st.text_area("Intervention")
        a,b,c = st.columns(3)
        baseline = a.number_input("Baseline KPI", value=0.0)
        outcome = b.number_input("Outcome KPI", value=0.0)
        unit = c.text_input("Unit")
        evidence_id = st.text_input("Evidence ID")
        status = st.selectbox("Case status", ["Draft","Pilot","Verified","Published"])
        narrative = st.text_area("Narrative")
        if st.form_submit_button("Save case study", type="primary") and title.strip():
            _insert("venture_cases", {"title":title.strip(),"customer":customer,"problem":problem,"intervention":intervention,"baseline":baseline,"outcome":outcome,"unit":unit,"evidence_id":evidence_id,"status":status,"narrative":narrative})
            st.success("Case study saved.")
            st.rerun()
    if not df.empty:
        st.dataframe(df[["title","customer","status","baseline","outcome","unit","evidence_id"]],use_container_width=True,hide_index=True)


def _render_demo() -> None:
    _header("End-to-End Demo Mode", "A guided presentation path using the actual workspace records—no fabricated traction or ROI.")
    projects = _frame("venture_projects")
    pilots = _frame("venture_pilots")
    evidence = _frame("venture_evidence")
    cases = _frame("venture_cases")
    st.progress(1.0 if not projects.empty else 0.2, text="01 · Venture / problem")
    st.progress(1.0 if not pilots.empty else 0.2, text="02 · Pilot / experiment")
    st.progress(1.0 if not evidence.empty else 0.2, text="03 · Evidence")
    st.progress(1.0 if not cases.empty else 0.2, text="04 · Customer case")
    st.markdown("### Presentation sequence")
    for label,ok in [
        ("Problem and customer",not projects.empty),
        ("Pilot baseline → target → actual",not pilots.empty),
        ("Evidence and provenance",not evidence.empty),
        ("Verified customer case",not cases.empty),
    ]:
        st.checkbox(label, value=ok, disabled=True, key=f"demo_{hashlib.sha1(label.encode()).hexdigest()[:8]}")
    st.info("Use the existing Executive Report Center export flow to package the populated workspace into presentation artifacts.")


def render_venture_capabilities(module: str, tier: str = "", username: str = "") -> None:
    """Render only the capability tabs mapped to the selected existing module."""
    if not module or module not in MODULE_TABS:
        return
    ensure_venture_schema()
    selected = MODULE_TABS[module]
    labels = {
        "venture":"🚀 Venture Studio",
        "stakeholders":"👥 Customers & Stakeholders",
        "pilots":"🧪 Pilot Manager",
        "hypothesis":"🔬 Hypothesis → Evidence",
        "business":"💼 Business Model + Pricing",
        "roi":"📈 ROI / Value Evidence",
        "evidence":"🗄️ Evidence Vault",
        "data_room":"📂 Investor Data Room",
        "traction":"📊 Product / Traction Analytics",
        "demo":"🎬 End-to-End Demo",
        "market":"🌐 Market & Competitive Intelligence",
        "readiness":"🧭 PMF / Readiness",
        "comparison":"⚖️ Pilot / Experiment Comparison",
        "onboarding":"✨ Guided Onboarding",
        "cases":"📚 Case Studies",
    }
    if not selected:
        return
    st.markdown("---")
    st.caption("Integrated venture workflow tabs · shared workspace persistence · evidence-first governance")
    tabs = st.tabs([labels[x] for x in selected])
    renderers = {
        "venture":_render_venture, "stakeholders":_render_stakeholders,
        "pilots":_render_pilots, "hypothesis":_render_hypothesis,
        "business":_render_business, "roi":_render_roi,
        "evidence":_render_evidence, "data_room":_render_data_room,
        "traction":_render_traction, "demo":_render_demo,
        "market":_render_market, "readiness":_render_readiness,
        "comparison":_render_comparison, "onboarding":_render_onboarding,
        "cases":_render_cases,
    }
    for tab, key in zip(tabs, selected):
        with tab:
            renderers[key]()
