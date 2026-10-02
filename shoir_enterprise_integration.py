"""Enterprise Integration & Collaboration workspace.

A practical shared-data/connectors/collaboration surface. External connectors are
described honestly as configured/validation-ready unless the application has
an explicit live connector implementation.
"""
from __future__ import annotations

import io
import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


DB_PATH = "enterprise_full_workspace.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _workspace() -> str:
    return str(
        st.session_state.get("shoir_workspace_name")
        or st.session_state.get("workspace")
        or st.session_state.get("active_workspace_name")
        or "default"
    )[:120]


def _db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, timeout=30)


def _slug(v: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(v)).strip("_").lower()


def ensure_enterprise_workspace_schema() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_connectors(
                owner TEXT NOT NULL,
                workspace TEXT NOT NULL,
                connector_id TEXT NOT NULL,
                name TEXT NOT NULL,
                system_type TEXT NOT NULL,
                endpoint TEXT,
                status TEXT NOT NULL DEFAULT 'Draft',
                last_validated TEXT,
                notes TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(owner,workspace,connector_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_collaboration(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                workspace TEXT NOT NULL,
                kind TEXT NOT NULL,
                subject TEXT NOT NULL,
                details TEXT,
                assignee TEXT,
                reviewer TEXT,
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_data_assets(
                owner TEXT NOT NULL,
                workspace TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                sheet TEXT,
                rows INTEGER NOT NULL,
                columns INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(owner,workspace,asset_id)
            )
            """
        )
        conn.commit()


def _connectors(owner: str, workspace: str) -> pd.DataFrame:
    ensure_enterprise_workspace_schema()
    with _db() as conn:
        return pd.read_sql_query(
            """
            SELECT connector_id,name,system_type,endpoint,status,last_validated,notes,updated_at
            FROM workspace_connectors
            WHERE owner=? AND workspace=?
            ORDER BY updated_at DESC
            """,
            conn,
            params=(owner,workspace),
        )


def _activity(owner: str, workspace: str) -> pd.DataFrame:
    ensure_enterprise_workspace_schema()
    with _db() as conn:
        return pd.read_sql_query(
            """
            SELECT id,kind,subject,details,assignee,reviewer,status,created_at
            FROM workspace_collaboration
            WHERE owner=? AND workspace=?
            ORDER BY id DESC LIMIT 250
            """,
            conn,
            params=(owner,workspace),
        )


def _asset_list(owner: str, workspace: str) -> pd.DataFrame:
    ensure_enterprise_workspace_schema()
    with _db() as conn:
        return pd.read_sql_query(
            """
            SELECT asset_id,filename,sheet,rows,columns,sha256,created_at
            FROM workspace_data_assets
            WHERE owner=? AND workspace=?
            ORDER BY created_at DESC
            """,
            conn,
            params=(owner,workspace),
        )


def _validate_endpoint(endpoint: str) -> tuple[str, str]:
    endpoint = str(endpoint or "").strip()
    if not endpoint:
        return "Configuration needed", "Add an endpoint or connection descriptor."
    if endpoint.lower().startswith(("postgresql://","postgres://","https://","http://","mqtt://","opc.tcp://")):
        return "Validation-ready", "Address format is structurally recognized. Live connectivity is not claimed until a provisioned connector reports success."
    if endpoint.startswith("/") or endpoint.lower().startswith(("server=","host=","dsn=")):
        return "Validation-ready", "Connection descriptor captured for provisioning."
    return "Review", "Use a recognized URI or server/DSN descriptor."


def _import_dataset(upload: Any) -> tuple[dict[str,pd.DataFrame], str]:
    raw = upload.getvalue()
    name = str(upload.name)
    try:
        from shoir_excel_studio import process_uploaded_workbook
        result = process_uploaded_workbook(raw, name)
        sheets = result.get("cleaned_sheets") or result.get("raw_sheets") or {}
        if sheets:
            digest = str(result.get("signature") or "")
            return {str(k): v.copy(deep=True) for k,v in sheets.items() if isinstance(v,pd.DataFrame) and not v.empty}, digest
    except Exception:
        pass
    lower=name.lower()
    if lower.endswith(".csv"):
        return {"Data":pd.read_csv(io.BytesIO(raw))},""
    if lower.endswith(".tsv") or lower.endswith(".txt"):
        return {"Data":pd.read_csv(io.BytesIO(raw),sep="\t")},""
    xls=pd.ExcelFile(io.BytesIO(raw))
    return {str(s):pd.read_excel(io.BytesIO(raw),sheet_name=s) for s in xls.sheet_names},""


def _hash_df(df: pd.DataFrame) -> str:
    import hashlib
    return hashlib.sha256(df.to_csv(index=False).encode("utf-8",errors="replace")).hexdigest()


def _publish_active(df: pd.DataFrame, filename: str, sheet: str, digest: str = "") -> None:
    try:
        from shoir_application_shell import _activate_shared_dataset
        _activate_shared_dataset(df,filename=filename,sheet=sheet,signature=digest or _hash_df(df))
    except Exception:
        st.session_state["universal_active_dataset"]=df.copy(deep=True)
        st.session_state["industrial_workbook_current_df"]=df.copy(deep=True)
        st.session_state["shoir_data_status"]="IMPORTED"
        st.session_state["shoir_data_source"]=f"{filename} · {sheet}"
        st.session_state["shoir_data_source_key"]="upload"


def render_enterprise_integration(tier: str, username: str) -> None:
    owner,workspace=str(username),_workspace()
    ensure_enterprise_workspace_schema()
    connectors=_connectors(owner,workspace)
    activity=_activity(owner,workspace)
    assets=_asset_list(owner,workspace)

    try:
        from shoir_enterprise_services import connector_health_frame, data_intelligence_profile
        health=connector_health_frame()
    except Exception:
        health=pd.DataFrame()

    st.markdown(
        """
        <style>
        .ei-hero{padding:24px 28px;border-radius:22px;background:linear-gradient(135deg,#0b1220,#172554 52%,#0f766e);color:#fff;box-shadow:0 16px 36px rgba(15,23,42,.14);margin-bottom:16px}
        .ei-kicker{font-size:11px;font-weight:850;letter-spacing:.12em;text-transform:uppercase;color:#7dd3fc}
        .ei-title{font-size:30px;font-weight:900;letter-spacing:-.03em;margin-top:4px}
        .ei-sub{color:#dbeafe;max-width:1000px;font-size:13px;margin-top:6px}
        .ei-pill{display:inline-block;padding:5px 9px;border:1px solid rgba(255,255,255,.14);border-radius:999px;background:rgba(255,255,255,.08);margin:12px 6px 0 0;font-size:11px}
        </style>
        <div class="ei-hero">
          <div class="ei-kicker">Platform · Integration & Collaboration</div>
          <div class="ei-title">🔗 Enterprise Integration & Collaboration Hub</div>
          <div class="ei-sub">Connect shared data, register enterprise systems, coordinate engineering work, and keep an auditable record of what is configured, what is imported, and what still needs provisioning.</div>
          <span class="ei-pill">Shared data</span><span class="ei-pill">Connector registry</span><span class="ei-pill">Team work</span><span class="ei-pill">Audit-ready</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    live_status=health["Status"].astype(str).str.contains("Connected|Healthy|Live|Operational",case=False,regex=True).sum() if not health.empty else 0
    validation_ready=connectors["status"].astype(str).str.contains("Validation|Configured",case=False,regex=True).sum() if not connectors.empty else 0
    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric("Registered systems",len(connectors))
    c2.metric("Validation-ready",int(validation_ready))
    c3.metric("Imported assets",len(assets))
    c4.metric("Open work items",int((activity["status"]=="Open").sum()) if not activity.empty else 0)
    c5.metric("Explicit live statuses",int(live_status))

    tabs=st.tabs(["🌐 Integration Map","🔌 Connector Registry","📥 Shared Data","👥 Collaboration","🛡️ Audit & Export"])

    with tabs[0]:
        st.markdown("### Enterprise integration map")
        st.caption("The map distinguishes provisioned/live systems from configuration-ready adapters. No connector is presented as live without an explicit status.")
        systems=list(connectors.to_dict("records"))
        if health is not None and not health.empty:
            for r in health.head(9).to_dict("records"):
                if not any(str(x.get("system_type"))==str(r.get("Protocol")) for x in systems):
                    systems.append({"name":str(r.get("System")),"system_type":str(r.get("Protocol")),"status":str(r.get("Status"))})
        systems=[r for r in systems if str(r.get("name") or r.get("System") or "").strip()]
        if systems:
            fig=go.Figure()
            center=(0,0)
            angles=[2*math.pi*i/max(1,len(systems)) for i in range(len(systems))]
            radius=1.0
            fig.add_trace(go.Scatter(x=[0],y=[0],mode="markers+text",text=["Shoir-IE"],textposition="middle center",marker=dict(size=42),showlegend=False))
            for angle,row in zip(angles,systems):
                x,y=radius*math.cos(angle),radius*math.sin(angle)
                fig.add_trace(go.Scatter(x=[0,x],y=[0,y],mode="lines",line=dict(width=1.5),showlegend=False,hoverinfo="skip"))
                name=str(row.get("name") or row.get("System"))
                status=str(row.get("status") or row.get("Status") or "Draft")
                fig.add_trace(go.Scatter(x=[x],y=[y],mode="markers+text",text=[name],textposition="top center",marker=dict(size=25),name=name,hovertemplate=f"{name}<br>Status: {status}<extra></extra>"))
            fig.update_layout(height=450,title="System-to-workspace topology",xaxis=dict(visible=False),yaxis=dict(visible=False),showlegend=False,margin=dict(l=10,r=10,t=55,b=10),plot_bgcolor="#f8fafc",paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})
        else:
            st.info("No enterprise systems are registered yet. Add a connector in Connector Registry.")
        if not health.empty:
            st.markdown("#### Adapter availability and health context")
            st.plotly_chart(px.bar(health,x="Protocol",color="Status",title="Connector coverage"),use_container_width=True,config={"displayModeBar":False})

    with tabs[1]:
        st.markdown("### Connector registry")
        with st.form("ei_add_connector"):
            a,b,c=st.columns(3)
            with a:
                cid=st.text_input("Connector ID",value=f"CON-{len(connectors)+1:03d}")
                name=st.text_input("System name",value="MES Production")
            with b:
                system=st.selectbox("System / protocol",["SAP","Oracle","SQL","REST","MQTT","OPC-UA","WMS","MES","ERP","Other"])
                endpoint=st.text_input("Endpoint / DSN",placeholder="https://… or host=…")
            with c:
                notes=st.text_input("Notes",placeholder="Purpose, owner, refresh expectation")
                save=st.form_submit_button("➕ Register connector",type="primary",use_container_width=True)
        if save:
            status,detail=_validate_endpoint(endpoint)
            with _db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO workspace_connectors(owner,workspace,connector_id,name,system_type,endpoint,status,last_validated,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (owner,workspace,cid.strip() or f"CON-{len(connectors)+1:03d}",name.strip() or "Unnamed system",system,endpoint.strip(),status,None,notes.strip(),_now()),
                )
                conn.commit()
            st.success(f"Connector registered · {status}. {detail}")
            st.rerun()

        if not connectors.empty:
            st.dataframe(connectors.rename(columns={"connector_id":"ID","name":"System","system_type":"Protocol","endpoint":"Endpoint / DSN","last_validated":"Validated","updated_at":"Updated"}),use_container_width=True,hide_index=True)
            sel=st.selectbox("Select connector to validate",connectors["connector_id"].astype(str).tolist(),key="ei_validate_select")
            selected=connectors[connectors["connector_id"].astype(str)==sel].iloc[0]
            if st.button("✓ Validate configuration",type="primary",use_container_width=True,key="ei_validate_btn"):
                status,detail=_validate_endpoint(selected["endpoint"])
                with _db() as conn:
                    conn.execute("UPDATE workspace_connectors SET status=?,last_validated=?,updated_at=? WHERE owner=? AND workspace=? AND connector_id=?",(status,_now(),_now(),owner,workspace,sel))
                    conn.commit()
                st.success(f"{status}: {detail}")
                st.rerun()
            if st.button("🗑️ Remove connector",use_container_width=True,key="ei_remove_connector"):
                with _db() as conn:
                    conn.execute("DELETE FROM workspace_connectors WHERE owner=? AND workspace=? AND connector_id=?",(owner,workspace,sel))
                    conn.commit()
                st.success("Connector removed.")
                st.rerun()
        else:
            st.info("No connectors are registered.")

    with tabs[2]:
        st.markdown("### Shared data handoff")
        st.caption("Upload a workbook once, select its active sheet, and publish that table into Shoir-IE's common dataset contract so downstream modules can reuse it.")
        upload=st.file_uploader("📥 Import Excel / CSV / TSV / TXT",type=["xlsx","xlsm","xls","csv","tsv","txt"],key="ei_shared_upload")
        if upload is not None:
            try:
                frames,digest=_import_dataset(upload)
                names=list(frames)
                sheet=st.selectbox("Imported sheet",names,key="ei_import_sheet")
                df=frames[sheet]
                if st.button("🔗 Publish sheet to shared workspace",type="primary",use_container_width=True,key="ei_publish_data"):
                    _publish_active(df,str(upload.name),sheet,digest)
                    asset_id="DATA-"+_hash_df(df)[:14].upper()
                    with _db() as conn:
                        conn.execute("INSERT OR REPLACE INTO workspace_data_assets(owner,workspace,asset_id,filename,sheet,rows,columns,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(owner,workspace,asset_id,str(upload.name),sheet,len(df),len(df.columns),_hash_df(df),_now()))
                        conn.commit()
                    try:
                        from shoir_enterprise_services import record_workspace_artifact
                        record_workspace_artifact("dataset",str(upload.name),owner,{"sheet":sheet,"rows":len(df),"columns":len(df.columns)})
                    except Exception:
                        pass
                    st.success(f"{upload.name} · {sheet} is now the shared active dataset.")
                    st.rerun()
                st.dataframe(df.head(18),use_container_width=True,hide_index=True)
                profile={"rows":len(df),"columns":len(df.columns),"quality_score":0}
                try:
                    from shoir_enterprise_services import data_intelligence_profile
                    profile=data_intelligence_profile(df)
                except Exception:
                    pass
                x,y,z=st.columns(3)
                x.metric("Rows",f"{len(df):,}")
                y.metric("Columns",f"{len(df.columns):,}")
                z.metric("Quality",f"{profile['quality_score']:.1f}%")
            except Exception as exc:
                st.error(f"Import failed safely: {type(exc).__name__}: {exc}")
        if not assets.empty:
            st.markdown("#### Shared asset register")
            st.dataframe(assets,use_container_width=True,hide_index=True)

    with tabs[3]:
        st.markdown("### Collaboration board")
        st.caption("Store engineering comments, assignments and review ownership against the current workspace.")
        with st.form("ei_collab_form"):
            a,b=st.columns(2)
            with a:
                kind=st.selectbox("Work item",["Comment","Assignment","Review"])
                subject=st.text_input("Subject",placeholder="Validate warehouse capacity assumptions")
                details=st.text_area("Details",height=90)
            with b:
                assignee=st.text_input("Assignee",placeholder="engineering")
                reviewer=st.text_input("Reviewer",placeholder="manager")
                submit=st.form_submit_button("💬 Add work item",type="primary",use_container_width=True)
        if submit and subject.strip():
            with _db() as conn:
                conn.execute("INSERT INTO workspace_collaboration(owner,workspace,kind,subject,details,assignee,reviewer,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(owner,workspace,kind,subject.strip(),details.strip(),assignee.strip(),reviewer.strip(),"Open",_now()))
                conn.commit()
            st.success("Collaboration item saved to the shared workspace.")
            st.rerun()
        if not activity.empty:
            st.dataframe(activity,use_container_width=True,hide_index=True)
            open_ids=activity.loc[activity["status"]=="Open","id"].tolist()
            if open_ids:
                pick=st.selectbox("Work item to update",open_ids,key="ei_collab_update_select")
                c1,c2=st.columns(2)
                with c1:
                    new_status=st.selectbox("Status",["Open","In Review","Blocked","Done"],key="ei_collab_status")
                with c2:
                    if st.button("✓ Update status",use_container_width=True,key="ei_collab_update_btn"):
                        with _db() as conn:
                            conn.execute("UPDATE workspace_collaboration SET status=? WHERE id=? AND owner=? AND workspace=?",(new_status,int(pick),owner,workspace))
                            conn.commit()
                        st.success("Work item updated.")
                        st.rerun()
        else:
            st.info("No collaboration items yet.")

    with tabs[4]:
        st.markdown("### Audit-ready workspace record")
        st.caption("Review the current integration state, shared assets and collaboration activity without exposing secrets.")
        audit_rows=[
            {"Area":"Workspace","Value":workspace,"State":"Bound"},
            {"Area":"Owner","Value":owner,"State":"Bound"},
            {"Area":"Registered connectors","Value":len(connectors),"State":"Tracked"},
            {"Area":"Shared datasets","Value":len(assets),"State":"Tracked"},
            {"Area":"Collaboration items","Value":len(activity),"State":"Tracked"},
            {"Area":"Live connector claims","Value":int(live_status),"State":"Only explicit statuses"},
        ]
        st.dataframe(pd.DataFrame(audit_rows),use_container_width=True,hide_index=True)
        out=io.BytesIO()
        with pd.ExcelWriter(out,engine="openpyxl") as writer:
            connectors.to_excel(writer,index=False,sheet_name="Connectors")
            assets.to_excel(writer,index=False,sheet_name="Shared_Assets")
            activity.to_excel(writer,index=False,sheet_name="Collaboration")
            pd.DataFrame(audit_rows).to_excel(writer,index=False,sheet_name="Audit")
        st.download_button("📥 Download Enterprise Workspace Pack",data=out.getvalue(),file_name="shoir_ie_enterprise_workspace.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",type="primary",use_container_width=True,key="ei_export_pack")
        st.download_button("📄 Download collaboration CSV",data=activity.to_csv(index=False).encode("utf-8"),file_name="enterprise_collaboration.csv",mime="text/csv",use_container_width=True,key="ei_export_collab")
