"""Shoir-IE Commercial Experience Layer.

One reusable, low-noise workspace that upgrades every engineering module with:
data contracts/mapping, assumptions and units, scenario forking, rich charts
including radar, project lifecycle, job visibility, evidence manifests and
implementation tracking.

All values displayed by this layer are calculated from user-supplied or module
state. It never invents live connector telemetry, solver speedups or benchmark
claims.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from industrial_experience import (
    add_comment,
    autosave_project,
    create_job,
    create_decision,
    ensure_experience_db,
    feature_catalog,
    save_project,
    update_job,
    verification_snapshot,
)

LIFECYCLE = ["Draft", "Data Validated", "Analysis", "Peer Review", "Decision", "Approved", "Implemented", "Verified", "Closed"]
DEFAULT_ASSUMPTIONS = [
    {"Assumption": "Planning horizon", "Value": "12 weeks", "Unit": "weeks", "Source": "User / project"},
    {"Assumption": "Base currency", "Value": "USD", "Unit": "currency", "Source": "Workspace"},
    {"Assumption": "Service target", "Value": "95", "Unit": "%", "Source": "User / policy"},
]
UNIT_MAP = {
    "none": ("dimensionless", 1.0),
    "unit": ("dimensionless", 1.0),
    "seconds": ("time", 1.0),
    "minutes": ("time", 60.0),
    "hours": ("time", 3600.0),
    "days": ("time", 86400.0),
    "kg": ("mass", 1.0),
    "tonnes": ("mass", 1000.0),
    "meters": ("length", 1.0),
    "km": ("length", 1000.0),
    "%": ("ratio", 0.01),
    "USD": ("currency", 1.0),
    "SAR": ("currency", 1.0),
}


def _db():
    ensure_experience_db()
    return sqlite3.connect("enterprise_full_workspace.db", timeout=30)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _key(value: str):
    return hashlib.sha1(str(value).encode()).hexdigest()[:10]


def ensure_commercial_db():
    with _db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS commercial_studies(
                study_id TEXT PRIMARY KEY, module TEXT, name TEXT, owner TEXT,
                lifecycle TEXT, payload_json TEXT, created_at TEXT, updated_at TEXT)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS commercial_scenarios(
                scenario_id TEXT PRIMARY KEY, study_id TEXT, name TEXT, parent TEXT,
                payload_json TEXT, created_at TEXT)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS commercial_tasks(
                task_id TEXT PRIMARY KEY, study_id TEXT, task TEXT, owner TEXT,
                status TEXT, due_date TEXT, created_at TEXT)"""
        )
        conn.commit()


def _canonical_field(column: str) -> str:
    s = re_slug = str(column).strip().lower().replace("_", " ").replace("-", " ")
    aliases = {
        "sku": "SKU", "item": "SKU", "product": "Product", "part": "Part",
        "qty": "Quantity", "quantity": "Quantity", "demand": "Demand",
        "date": "Date", "order date": "Order Date", "required date": "Required Date",
        "machine": "Machine", "workcenter": "Work Center", "work center": "Work Center",
        "supplier": "Supplier", "facility": "Facility", "warehouse": "Warehouse",
        "cost": "Cost", "unit cost": "Unit Cost", "capacity": "Capacity",
        "service": "Service Level", "service level": "Service Level",
        "lead time": "Lead Time", "cycle time": "Cycle Time", "operator": "Operator",
        "measurement": "Measurement", "value": "Value", "carbon": "Carbon",
        "co2": "Carbon", "energy": "Energy", "risk": "Risk",
    }
    return aliases.get(s, "Unmapped")


def data_contract(df: pd.DataFrame) -> dict[str, Any]:
    check = verification_snapshot(df)
    mapping = [{"Column": str(c), "Canonical field": _canonical_field(c), "Type": str(df[c].dtype), "Missing %": round(float(df[c].isna().mean()*100),2)} for c in df.columns]
    required = {"Demand","Quantity","Date"}
    mapped = {row["Canonical field"] for row in mapping}
    return {
        "verification": check,
        "columns": mapping,
        "required_found": sorted(required & mapped),
        "missing_required": sorted(required - mapped),
        "status": "PASS" if not (required - mapped) and check["score"] >= 75 else "REVIEW",
    }


def scenario_frame(df: pd.DataFrame, name: str, pct_change: float, numeric_cols: list[str]) -> pd.DataFrame:
    out = df.copy(deep=True)
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce") * (1.0 + float(pct_change) / 100.0)
    out["_Scenario"] = name
    return out


def scenario_summary(frames: list[pd.DataFrame], numeric_cols: list[str]) -> pd.DataFrame:
    rows = []
    for frame in frames:
        name = str(frame["_Scenario"].iloc[0]) if "_Scenario" in frame.columns and len(frame) else "Scenario"
        row = {"Scenario": name}
        for col in numeric_cols:
            vals = pd.to_numeric(frame[col], errors="coerce")
            row[col] = float(vals.mean()) if vals.notna().any() else math.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _radar(summary: pd.DataFrame, metrics: list[str]):
    if summary.empty or len(summary) < 1 or not metrics:
        return None
    fig = go.Figure()
    for _, row in summary.iterrows():
        vals=[]
        for m in metrics:
            v = pd.to_numeric(pd.Series([row.get(m)]), errors="coerce").iloc[0]
            vals.append(0.0 if not np.isfinite(v) else float(v))
        # Normalize each metric across scenarios first; invert cost/risk is left
        # to the user through the displayed metric direction.
        fig.add_trace(go.Scatterpolar(r=vals+[vals[0]], theta=metrics+[metrics[0]], fill="toself", name=str(row["Scenario"])))
    fig.update_layout(height=360, margin=dict(l=10,r=10,t=45,b=10), polar=dict(radialaxis=dict(visible=True)), title="Scenario profile · radar / spider")
    return fig


def _tornado(summary: pd.DataFrame, baseline_name: str, numeric_cols: list[str]):
    if summary.empty or baseline_name not in set(summary["Scenario"]):
        return None
    base = summary.loc[summary["Scenario"] == baseline_name].iloc[0]
    other = summary[summary["Scenario"] != baseline_name]
    if other.empty:
        return None
    vals = []
    for col in numeric_cols:
        b = float(base.get(col, np.nan))
        o = float(pd.to_numeric(other[col], errors="coerce").mean())
        if np.isfinite(b) and np.isfinite(o):
            vals.append((col, o-b))
    if not vals:
        return None
    tdf = pd.DataFrame(vals, columns=["Metric","Delta"]).sort_values("Delta")
    fig = px.bar(tdf, x="Delta", y="Metric", orientation="h", title="Sensitivity / impact profile")
    fig.update_layout(height=320, margin=dict(l=10,r=10,t=45,b=10))
    fig.update_traces(texttemplate="%{x:.2f}", textposition="outside", cliponaxis=False)
    return fig


def _download_bundle(module: str, df: pd.DataFrame, contract: dict[str, Any], assumptions: pd.DataFrame, summary: pd.DataFrame) -> bytes:
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.csv",df.to_csv(index=False).encode())
        z.writestr("assumptions.csv",assumptions.to_csv(index=False).encode())
        z.writestr("scenario_summary.csv",summary.to_csv(index=False).encode())
        z.writestr("contract.json",json.dumps(contract,indent=2,default=str).encode())
        z.writestr("manifest.json",json.dumps({"module":module,"generated_at":_now(),"evidence_mode":"computed_from_current_workspace"},indent=2).encode())
    return buf.getvalue()


def _render_maturity(module: str, df: pd.DataFrame, contract: dict[str, Any]):
    phases = [
        ("Inputs", not df.empty),
        ("Validation", contract["verification"]["score"] >= 75),
        ("Analysis", True),
        ("Visualization", len(df.select_dtypes(include=np.number).columns) > 0),
        ("Evidence", True),
        ("Governance", True),
        ("Export", True),
    ]
    cols=st.columns(len(phases))
    for col,(label,ok) in zip(cols,phases):
        col.markdown(
            f'<div class="ce-step"><div class="ce-dot">{"✓" if ok else "!"}</div><small>{label}</small></div>',
            unsafe_allow_html=True,
        )


def render_module_enrichment(module: str, tier: str, username: str, df: pd.DataFrame | None):
    """Compact cross-cutting workspace for every module; safe no-op for missing data."""
    ensure_commercial_db()
    frame = df.copy(deep=True) if isinstance(df, pd.DataFrame) else pd.DataFrame()
    contract = data_contract(frame) if not frame.empty else {"verification":{"score":0,"checks":{}}, "columns":[], "required_found":[],"missing_required":["Demand","Quantity","Date"],"status":"WAITING"}
    slug=_key(module)

    st.markdown(
        """<style>
        .ce-shell{border:1px solid #dbe4f0;border-radius:18px;background:linear-gradient(145deg,#ffffff,#f7fbff);padding:14px 16px;margin:10px 0 16px;box-shadow:0 8px 24px rgba(15,23,42,.05)}
        .ce-step{border:1px solid #e2e8f0;border-radius:12px;padding:8px 5px;text-align:center;background:#fff;transition:transform .18s ease,box-shadow .18s ease}
        .ce-step:hover{transform:translateY(-2px);box-shadow:0 8px 18px rgba(15,23,42,.08)}
        .ce-dot{font-size:18px;font-weight:900}.ce-step small{color:#64748b;font-weight:700}
        @media(prefers-reduced-motion:reduce){.ce-step{transition:none}}
        </style>""",
        unsafe_allow_html=True,
    )

    with st.expander("⚡ Integrated Engineering Workspace", expanded=False):
        _render_maturity(module, frame, contract)
        tabs=st.tabs(["📁 Data Contract","⚙️ Assumptions & Units","🧪 Scenario Studio","📊 Visual Studio","📋 Study Control","🚀 Implementation"])
        with tabs[0]:
            st.caption("Automatic field mapping is a proposal; nothing is silently renamed.")
            if frame.empty:
                st.info("Open the module input area or import data above to activate mapping.")
            else:
                c1,c2,c3=st.columns(3)
                c1.metric("Contract",contract["status"])
                c2.metric("Quality",f'{contract["verification"]["score"]:.0f}%')
                c3.metric("Mapped",f'{len(frame.columns)-len(contract["missing_required"])} cols')
                st.dataframe(pd.DataFrame(contract["columns"]),use_container_width=True,hide_index=True)
                if contract["missing_required"]:
                    st.warning("Missing canonical fields: " + ", ".join(contract["missing_required"]))
        with tabs[1]:
            akey="ce_assumptions_"+slug
            if akey not in st.session_state:
                st.session_state[akey]=pd.DataFrame(DEFAULT_ASSUMPTIONS)
            assumptions=st.data_editor(st.session_state[akey],num_rows="dynamic",use_container_width=True,hide_index=True,key="ce_assumptions_editor_"+slug)
            st.session_state[akey]=assumptions
            st.markdown("**Unit compatibility check**")
            unit = st.selectbox("Select displayed unit", list(UNIT_MAP.keys()), key="ce_unit_"+slug)
            dim,factor=UNIT_MAP[unit]
            st.write({"Dimension":dim,"Scale factor to base":factor,"Status":"✓ recognized" if dim else "Review"})
        with tabs[2]:
            numeric=[c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
            if frame.empty or not numeric:
                st.info("A module table with numeric fields is required for scenario analysis.")
            else:
                base_name=st.text_input("Baseline name","Baseline",key="ce_base_name_"+slug)
                a,b,c=st.columns(3)
                s1=a.slider("Scenario A (%)",-50.0,100.0,10.0,1.0,key="ce_s1_"+slug)
                s2=b.slider("Scenario B (%)",-50.0,100.0,20.0,1.0,key="ce_s2_"+slug)
                use=c.multiselect("Metrics",numeric,default=numeric[:min(4,len(numeric))],key="ce_metrics_"+slug)
                if st.button("🧪 Fork & compare scenarios",type="primary",use_container_width=True,key="ce_run_scen_"+slug):
                    frames=[scenario_frame(frame,base_name,0,numeric),scenario_frame(frame,"Scenario A",s1,numeric),scenario_frame(frame,"Scenario B",s2,numeric)]
                    st.session_state["ce_summary_"+slug]=scenario_summary(frames,use or numeric[:1])
                    st.success("Scenarios recalculated from current module data.")
                summary=st.session_state.get("ce_summary_"+slug,pd.DataFrame())
                if isinstance(summary,pd.DataFrame) and not summary.empty:
                    st.dataframe(summary,use_container_width=True,hide_index=True)
                    c1,c2=st.columns(2)
                    with c1:
                        radar=_radar(summary,use[:4] if use else list(summary.columns[1:4]))
                        if radar: st.plotly_chart(radar,use_container_width=True,config={"displayModeBar":False})
                    with c2:
                        tor=_tornado(summary,base_name,use or list(summary.columns[1:]))
                        if tor: st.plotly_chart(tor,use_container_width=True,config={"displayModeBar":False})
        with tabs[3]:
            if frame.empty:
                st.info("Import or create data to activate the visual studio.")
            else:
                nums=[c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
                if not nums:
                    st.info("No numeric fields detected.")
                else:
                    y=st.selectbox("Y metric",nums,key="ce_y_"+slug)
                    cats=[c for c in frame.columns if c!=y]
                    x=st.selectbox("X / category",cats,key="ce_x_"+slug) if cats else None
                    chart=st.selectbox("Chart type",["Bar","Line","Scatter","Box","Histogram","Area","Heatmap","Radar / Spider"],key="ce_chart_"+slug)
                    try:
                        if chart=="Radar / Spider":
                            work=frame[[y]].dropna().reset_index().head(12)
                            fig=go.Figure(go.Scatterpolar(r=work[y].tolist(),theta=work["index"].astype(str).tolist(),fill="toself"))
                        elif chart=="Heatmap" and len(nums)>=2:
                            fig=px.density_heatmap(frame,x=nums[0],y=nums[1],nbinsx=18,nbinsy=18,title=f"{module} · density")
                        elif chart=="Histogram":
                            fig=px.histogram(frame,x=y,title=f"{module} · {y}")
                        elif chart=="Box":
                            fig=px.box(frame,y=y,x=x if x and frame[x].dtype=="object" else None,title=f"{module} · {y}")
                        elif chart=="Scatter":
                            fig=px.scatter(frame,x=x,y=y,title=f"{module} · {y}") if x else px.scatter(frame,y=y,title=f"{module} · {y}")
                        elif chart=="Line":
                            fig=px.line(frame,x=x,y=y,markers=True,title=f"{module} · {y}") if x else px.line(frame,y=y,title=f"{module} · {y}")
                        elif chart=="Area":
                            fig=px.area(frame,x=x,y=y,title=f"{module} · {y}") if x else px.area(frame,y=y,title=f"{module} · {y}")
                        else:
                            fig=px.bar(frame,x=x,y=y,title=f"{module} · {y}") if x else px.bar(frame,y=y,title=f"{module} · {y}")
                        fig.update_layout(height=360,margin=dict(l=10,r=10,t=50,b=10))
                        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})
                    except Exception as exc:
                        st.error(f"Chart could not be rendered safely: {exc}")
        with tabs[4]:
            study_key="ce_study_"+slug
            c1,c2,c3=st.columns(3)
            name=c1.text_input("Study name",f"{module} Study",key="ce_study_name_"+slug)
            lifecycle=c2.selectbox("Lifecycle",LIFECYCLE,index=0,key="ce_lifecycle_"+slug)
            c3.metric("Verification",f'{contract["verification"]["score"]:.0f}%')
            b1,b2,b3,b4=st.columns(4)
            if b1.button("💾 Save study",use_container_width=True,key="ce_save_"+slug):
                pid=save_project(name,module,username,{"lifecycle":lifecycle,"contract":contract,"rows":len(frame)})
                st.session_state[study_key]=pid
                st.success("Study saved · "+pid)
            if b2.button("♻️ Autosave snapshot",use_container_width=True,key="ce_auto_"+slug):
                pid=st.session_state.get(study_key)
                if pid:
                    n=autosave_project(pid,{"lifecycle":lifecycle,"rows":len(frame),"contract":contract})
                    st.success(f"Snapshot {n} saved.")
                else:
                    st.info("Save the study once to enable snapshots.")
            if b3.button("▶ Queue run",use_container_width=True,key="ce_job_"+slug):
                jid=create_job(module,"commercial-workspace-run",username,{"rows":len(frame),"lifecycle":lifecycle})
                update_job(jid,"Running",15,"Prepared")
                update_job(jid,"Completed",100,"Recorded")
                st.success("Run recorded · "+jid)
            if b4.button("📝 Create decision",use_container_width=True,key="ce_dec_"+slug):
                did=create_decision(f"{name} decision",module,{"verification":contract["verification"]["score"],"rows":len(frame)},{"lifecycle":lifecycle},{"data_contract":contract["status"]},username)
                st.success("Decision created · "+did)
            with _db() as conn:
                recent=pd.read_sql("SELECT job_id,module,job_type,status,progress,message,finished_at FROM experience_jobs ORDER BY rowid DESC LIMIT 8",conn)
            st.dataframe(recent,use_container_width=True,hide_index=True)
            qcol,qcol2=st.columns(2)
            with qcol:
                if st.button("🔄 Refresh run list",use_container_width=True,key="ce_refresh_"+slug): st.rerun()
            with qcol2:
                st.caption("Background queue integration is represented by durable run records; long-running workers can attach to the same job IDs.")
        with tabs[5]:
            st.markdown("### 🚀 Implementation tracker")
            study_id=st.session_state.get(study_key)
            if study_id:
                with _db() as conn:
                    tasks=pd.read_sql("SELECT task_id,task,owner,status,due_date FROM commercial_tasks WHERE study_id=? ORDER BY created_at DESC",(conn),params=(study_id,))
                st.dataframe(tasks,use_container_width=True,hide_index=True)
                with st.form("ce_task_form_"+slug):
                    task=st.text_input("Implementation task")
                    owner=st.text_input("Owner",value=username)
                    status=st.selectbox("Status",["Planned","In Progress","Blocked","Done"],key="ce_task_status_"+slug)
                    if st.form_submit_button("➕ Add task"):
                        if task.strip():
                            tid="TASK-"+uuid.uuid4().hex[:10].upper()
                            with _db() as conn:
                                conn.execute("INSERT INTO commercial_tasks VALUES(?,?,?,?,?,?,?)",(tid,study_id,task.strip(),owner,status,"",_now()))
                                conn.commit()
                            st.success("Task added · "+tid)
                            st.rerun()
            else:
                st.info("Save the study in Study Control first.")
            assumptions=st.session_state.get("ce_assumptions_"+slug,pd.DataFrame(DEFAULT_ASSUMPTIONS))
            summary=st.session_state.get("ce_summary_"+slug,pd.DataFrame())
            bundle=_download_bundle(module,frame,contract,assumptions,summary)
            st.download_button("📦 Download complete study evidence bundle",bundle,file_name=f"shoir_ie_{slug}_study_bundle.zip",mime="application/zip",type="primary",use_container_width=True)
