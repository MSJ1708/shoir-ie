"""Industrial Decision Command Center.

A single, auditable workspace over the existing Shoir-IE modules. It intentionally
uses the same session state/database instead of creating parallel data stores.
"""
from __future__ import annotations
import io, json, sqlite3, hashlib, re
from datetime import datetime
import pandas as pd
import streamlit as st
import plotly.express as px

from industrial_platform_excellence import (
    CANONICAL_TIERS,
    module_availability,
    tier_matrix,
    canonical_tier,
    deep_data_quality,
    infer_column_types,
    validate_schema,
    copilot_execution_plan,
    ensure_excellence_db,
    dataframe_fingerprint,
    reproducibility_manifest,
)
from shoir_upgrade import read_uploaded_workbook, build_excel_report

def _db_table(name: str, limit: int = 250) -> pd.DataFrame:
    try:
        with sqlite3.connect("enterprise_full_workspace.db") as conn:
            return pd.read_sql(f"SELECT * FROM {name} LIMIT {int(limit)}", conn)
    except Exception:
        return pd.DataFrame()

def _session_tables() -> list[tuple[str,str,pd.DataFrame]]:
    out=[]
    ignored={"copilot_workbook_original","copilot_workbook","upgrade_audit"}
    for key,val in st.session_state.items():
        if key in ignored or str(key).startswith(("_","password","upgrade_","copilot_")):
            continue
        if isinstance(val,pd.DataFrame) and len(val.columns):
            out.append((str(key).replace("_"," ").title(),key,val.copy(deep=True)))
        elif isinstance(val,list) and val and isinstance(val[0],dict):
            try:
                df=pd.DataFrame(val)
                if len(df.columns):
                    out.append((str(key).replace("_"," ").title(),key,df))
            except Exception:
                pass
    return out

def _reset_table(key: str) -> None:
    snapshot_key="_command_snapshot_"+key
    current=st.session_state.get(key)
    if snapshot_key not in st.session_state:
        st.session_state[snapshot_key]=current.copy(deep=True) if isinstance(current,pd.DataFrame) else current
    snap=st.session_state[snapshot_key]
    if isinstance(current,list) and isinstance(snap,pd.DataFrame):
        st.session_state[key]=snap.where(pd.notna(snap),None).to_dict("records")
    elif isinstance(snap,pd.DataFrame):
        st.session_state[key]=snap.copy(deep=True)
    else:
        st.session_state[key]=snap
    st.session_state.pop(snapshot_key,None)

def render_command_center(username: str, tier: str) -> None:
    ensure_excellence_db()
    st.header("🏭 Industrial Decision Command Center")
    st.caption("One control surface for data health, connected modules, scenario governance, reproducibility, reports and safe Copilot execution plans.")

    canon=canonical_tier(tier)
    tab_health, tab_modules, tab_scenarios, tab_copilot, tab_reports = st.tabs([
        "🩺 Platform Health","🧩 Modules & Tiers","🧪 Scenarios","🤖 Copilot Plans","📤 Reporting"
    ])

    with tab_health:
        tables=_session_tables()
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Tier",canon)
        c2.metric("Active session tables",len(tables))
        db_tables=_db_table("platform_datasets")
        c3.metric("Registered datasets",len(db_tables))
        events=_db_table("platform_events")
        c4.metric("Platform events",len(events))
        if tables:
            rows=[]
            for label,key,df in tables:
                q=deep_data_quality(df)
                rows.append({"Table":label,"Rows":len(df),"Columns":len(df.columns),"Quality %":q["score"],"Missing %":q["missing_pct"],"Duplicates %":q["duplicate_pct"],"Fingerprint":q["fingerprint"]})
            health=pd.DataFrame(rows).sort_values(["Quality %","Rows"],ascending=[True,False])
            st.dataframe(health,use_container_width=True,hide_index=True)
            selected=st.selectbox("Inspect table",health["Table"].tolist(),key="cc_health_table")
            selected_df=next(df for label,_,df in tables if label==selected)
            with st.expander("Schema & validation",expanded=True):
                st.dataframe(infer_column_types(selected_df),use_container_width=True,hide_index=True)
                st.json(validate_schema(selected_df))
            xlsx=build_excel_report("Shoir-IE Platform Health",[( "Table Health",health),(selected,selected_df)])
            st.download_button("📥 Download Health Workbook",xlsx,"shoir_ie_platform_health.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
        else:
            st.info("No editable session tables are loaded yet. Open a data module or import a dataset.")

    with tab_modules:
        st.subheader("Capability Map")
        st.dataframe(module_availability(tier),use_container_width=True,hide_index=True)
        st.subheader("Tier Architecture")
        st.dataframe(tier_matrix(),use_container_width=True,hide_index=True)
        st.caption("Existing account labels are normalized to these canonical tiers without changing stored account history.")

    with tab_scenarios:
        st.subheader("Scenario Governance")
        with sqlite3.connect("enterprise_full_workspace.db") as conn:
            sc=_db_table("platform_scenarios")
        if sc.empty:
            st.info("No saved scenarios yet. Use Scenario Versioning & Comparison or Experiment Lab to create them.")
        else:
            st.dataframe(sc,use_container_width=True,hide_index=True)
            metric_cols=[c for c in ["kpis_json","parameters_json"] if c in sc.columns]
            st.download_button("📥 Download Scenario Registry",sc.to_csv(index=False).encode(),"scenario_registry.csv","text/csv",use_container_width=True)

    with tab_copilot:
        st.subheader("Safe Copilot Execution Planner")
        prompt=st.text_area("Describe the workflow you want Copilot to perform",placeholder="Import the demand workbook, clean it, forecast demand, test a 30% supplier disruption and prepare a report.",key="cc_copilot_plan_prompt")
        if st.button("Generate Plan",type="primary",use_container_width=True,key="cc_plan"):
            st.session_state["cc_plan_result"]=copilot_execution_plan(prompt)
        plan=st.session_state.get("cc_plan_result")
        if plan:
            st.warning("Approval gate: the plan is a proposal. No write/execute action is performed here.")
            st.dataframe(pd.DataFrame(plan["steps"]),use_container_width=True,hide_index=True)
            st.json({"approval_required":plan["approval_required"],"guardrail":plan["guardrail"]})
            if st.button("✅ Approve Plan for Next Copilot Step",use_container_width=True,key="cc_plan_approve"):
                st.session_state["cc_plan_approved"]=True
                st.success("Plan approved. The execution-ready steps are retained in this session; individual module runs remain explicit and auditable.")
                st.download_button("📋 Download Execution Plan",json.dumps(plan,indent=2).encode(),"copilot_execution_plan.json","application/json",use_container_width=True)

    with tab_reports:
        st.subheader("One-Click Platform Snapshot")
        tables=_session_tables()
        if tables:
            export_tables=[(label,df) for label,_,df in tables]
            manifest= pd.DataFrame([
                {"Artifact":label,"Rows":len(df),"Columns":len(df.columns),"Fingerprint":dataframe_fingerprint(df),"Generated At":datetime.utcnow().isoformat(timespec="seconds"),"Actor":username}
                for label,df in export_tables
            ])
            xlsx=build_excel_report("Shoir-IE | Platform Snapshot",export_tables+[("Reproducibility Manifest",manifest)])
            st.download_button("📊 Download Full Excel Snapshot",xlsx,"shoir_ie_platform_snapshot.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
            st.download_button("📋 Download Manifest",manifest.to_csv(index=False).encode(),"shoir_ie_reproducibility_manifest.csv","text/csv",use_container_width=True)
        else:
            st.info("Load module data first, then return here to export the current platform state.")
