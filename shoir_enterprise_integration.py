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


_REGISTRY_COLUMNS = {
    "connectors": ["connector_id","name","system_type","endpoint","status","last_validated","notes","updated_at"],
    "activity": ["id","kind","subject","details","assignee","reviewer","status","created_at"],
    "assets": ["asset_id","filename","sheet","rows","columns","sha256","created_at"],
}


def _registry_key(kind: str, owner: str, workspace: str) -> str:
    """Stable per-user/workspace cache key; values are included in workspace autosave."""
    import hashlib
    # Account names use the authentication system's case-insensitive identity;
    # workspace labels are preserved exactly because local storage scopes them case-sensitively.
    scope = f"{str(owner or '').strip().lower()}::{str(workspace or 'default').strip()}"
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:24]
    return f"ei_registry_v1_{kind}_{digest}"


def _legacy_registry_frame(kind: str, owner: str, workspace: str) -> pd.DataFrame:
    """One-time local SQLite migration path for records created before state-backed persistence."""
    ensure_enterprise_workspace_schema()
    queries = {
        "connectors": (
            """SELECT connector_id,name,system_type,endpoint,status,last_validated,notes,updated_at
               FROM workspace_connectors WHERE owner=? AND workspace=? ORDER BY updated_at DESC""",
            (owner, workspace),
        ),
        "activity": (
            """SELECT id,kind,subject,details,assignee,reviewer,status,created_at
               FROM workspace_collaboration WHERE owner=? AND workspace=? ORDER BY id DESC LIMIT 250""",
            (owner, workspace),
        ),
        "assets": (
            """SELECT asset_id,filename,sheet,rows,columns,sha256,created_at
               FROM workspace_data_assets WHERE owner=? AND workspace=? ORDER BY created_at DESC""",
            (owner, workspace),
        ),
    }
    if kind not in queries:
        raise ValueError(f"Unknown integration registry: {kind}")
    query, params = queries[kind]
    with _db() as conn:
        return pd.read_sql_query(query, conn, params=params)


def _registry_frame(kind: str, owner: str, workspace: str, state: Any = None) -> pd.DataFrame:
    """Read a workspace-scoped registry from durable user state, seeding from SQLite once."""
    state = st.session_state if state is None else state
    if kind not in _REGISTRY_COLUMNS:
        raise ValueError(f"Unknown integration registry: {kind}")
    key = _registry_key(kind, owner, workspace)
    if key in state:
        cached = state.get(key)
        if isinstance(cached, pd.DataFrame):
            frame = cached.copy(deep=True)
        elif isinstance(cached, list):
            frame = pd.DataFrame(cached)
        else:
            frame = pd.DataFrame(columns=_REGISTRY_COLUMNS[kind])
        return frame.reindex(columns=_REGISTRY_COLUMNS[kind])

    frame = _legacy_registry_frame(kind, owner, workspace)
    state[key] = frame.to_dict("records")
    return frame.reindex(columns=_REGISTRY_COLUMNS[kind])


def _write_registry_frame(kind: str, owner: str, workspace: str, frame: pd.DataFrame, state: Any = None) -> None:
    """Stage a registry mutation in the user's persistent workspace snapshot."""
    state = st.session_state if state is None else state
    if kind not in _REGISTRY_COLUMNS:
        raise ValueError(f"Unknown integration registry: {kind}")
    normalized = frame.copy(deep=True).reindex(columns=_REGISTRY_COLUMNS[kind])
    # Lists of scalar records serialize more predictably than widget-owned DataFrames.
    state[_registry_key(kind, owner, workspace)] = normalized.to_dict("records")


def _persist_owner_workspace(owner: str) -> bool:
    """Persist immediately after a high-value integration mutation, not just on a later rerun."""
    try:
        from workspace_persistence import save_user_workspace
        return bool(save_user_workspace(owner, st.session_state))
    except Exception:
        return False


def _connectors(owner: str, workspace: str) -> pd.DataFrame:
    return _registry_frame("connectors", owner, workspace)


def _activity(owner: str, workspace: str) -> pd.DataFrame:
    return _registry_frame("activity", owner, workspace)


def _asset_list(owner: str, workspace: str) -> pd.DataFrame:
    return _registry_frame("assets", owner, workspace)


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
    registry_keys = [
        _registry_key("connectors", owner, workspace),
        _registry_key("activity", owner, workspace),
        _registry_key("assets", owner, workspace),
    ]
    migrate_legacy_registry = not all(key in st.session_state for key in registry_keys)
    connectors=_connectors(owner,workspace)
    activity=_activity(owner,workspace)
    assets=_asset_list(owner,workspace)
    if migrate_legacy_registry and (not connectors.empty or not activity.empty or not assets.empty):
        if _persist_owner_workspace(owner):
            st.caption("Legacy local integration records were copied into the authenticated user workspace snapshot.")

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
             st.markdown("### Start here")
             st.markdown("**Register a system → validate it → publish shared data → coordinate work**")
             adapter_catalog = pd.DataFrame({
                 "Adapter":["SAP","Oracle","SQL","REST","MQTT","OPC-UA","WMS","MES","ERP"],
                 "Purpose":["ERP","ERP","Database","API","Telemetry","Industrial protocol","Warehouse","Execution","Enterprise planning"],
                 "Configured":[0]*9,
             })
             st.plotly_chart(
                 px.bar(adapter_catalog,x="Adapter",y="Configured",title="Enterprise adapter catalog"),
                 use_container_width=True,
                 config={"displayModeBar":False},
             )
             st.info("No external systems are configured yet. The catalog describes adapter types; it does not claim a live connection.")
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
            now = _now()
            connector_id = cid.strip() or f"CON-{len(connectors)+1:03d}"
            connector_row = {
                "connector_id": connector_id,
                "name": name.strip() or "Unnamed system",
                "system_type": system,
                "endpoint": endpoint.strip(),
                "status": status,
                "last_validated": None,
                "notes": notes.strip(),
                "updated_at": now,
            }
            with _db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO workspace_connectors(owner,workspace,connector_id,name,system_type,endpoint,status,last_validated,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (owner,workspace,connector_id,connector_row["name"],system,endpoint.strip(),status,None,notes.strip(),now),
                )
                conn.commit()
            updated = connectors[connectors["connector_id"].astype(str) != connector_id].copy()
            updated = pd.concat([updated, pd.DataFrame([connector_row])], ignore_index=True)
            _write_registry_frame("connectors", owner, workspace, updated)
            durable = _persist_owner_workspace(owner)
            st.success(f"Connector registered · {status}. {detail}")
            if not durable:
                st.warning("The connector was recorded in this session, but durable workspace storage did not confirm the save. Check your managed persistence configuration.")
            st.rerun()

        if not connectors.empty:
            st.dataframe(connectors.rename(columns={"connector_id":"ID","name":"System","system_type":"Protocol","endpoint":"Endpoint / DSN","last_validated":"Validated","updated_at":"Updated"}),use_container_width=True,hide_index=True)
            sel=st.selectbox("Select connector",connectors["connector_id"].astype(str).tolist(),key="ei_validate_select")
            selected=connectors[connectors["connector_id"].astype(str)==sel].iloc[0]
            with st.expander("✏️ Edit selected connector",expanded=False):
                with st.form("ei_edit_connector_form"):
                    e1,e2,e3=st.columns(3)
                    with e1:
                        edit_name=st.text_input("System name",value=str(selected["name"]))
                    with e2:
                        protocol_options=["SAP","Oracle","SQL","REST","MQTT","OPC-UA","WMS","MES","ERP","Other"]
                        edit_system=st.selectbox("System / protocol",protocol_options,index=(protocol_options.index(str(selected["system_type"])) if str(selected["system_type"]) in protocol_options else 9))
                    with e3:
                        edit_endpoint=st.text_input("Endpoint / DSN",value=str(selected["endpoint"] or ""))
                        edit_notes=st.text_input("Notes",value=str(selected["notes"] or ""))
                    save_edit=st.form_submit_button("💾 Save connector changes",type="primary",use_container_width=True)
                if save_edit:
                    edit_status,detail=_validate_endpoint(edit_endpoint)
                    now = _now()
                    edit_values = {
                        "name": edit_name.strip() or str(selected["name"]),
                        "system_type": edit_system,
                        "endpoint": edit_endpoint.strip(),
                        "status": edit_status,
                        "last_validated": None,
                        "notes": edit_notes.strip(),
                        "updated_at": now,
                    }
                    with _db() as conn:
                        conn.execute("UPDATE workspace_connectors SET name=?,system_type=?,endpoint=?,status=?,last_validated=NULL,notes=?,updated_at=? WHERE owner=? AND workspace=? AND connector_id=?",(edit_values["name"],edit_system,edit_endpoint.strip(),edit_status,edit_notes.strip(),now,owner,workspace,sel))
                        conn.commit()
                    updated = connectors.copy()
                    mask = updated["connector_id"].astype(str) == str(sel)
                    for field, value in edit_values.items():
                        updated.loc[mask, field] = value
                    _write_registry_frame("connectors", owner, workspace, updated)
                    durable = _persist_owner_workspace(owner)
                    st.success(f"Connector updated · {edit_status}. {detail}")
                    if not durable:
                        st.warning("The update is in the current session, but durable workspace storage did not confirm the save.")
                    st.rerun()
            if st.button("✓ Validate configuration",type="primary",use_container_width=True,key="ei_validate_btn"):
                status,detail=_validate_endpoint(selected["endpoint"])
                now = _now()
                with _db() as conn:
                    conn.execute("UPDATE workspace_connectors SET status=?,last_validated=?,updated_at=? WHERE owner=? AND workspace=? AND connector_id=?",(status,now,now,owner,workspace,sel))
                    conn.commit()
                updated = connectors.copy()
                mask = updated["connector_id"].astype(str) == str(sel)
                updated.loc[mask, "status"] = status
                updated.loc[mask, "last_validated"] = now
                updated.loc[mask, "updated_at"] = now
                _write_registry_frame("connectors", owner, workspace, updated)
                durable = _persist_owner_workspace(owner)
                st.success(f"{status}: {detail}")
                if not durable:
                    st.warning("The validation result is in the current session, but durable workspace storage did not confirm the save.")
                st.rerun()
            if st.button("🗑️ Remove connector",use_container_width=True,key="ei_remove_connector"):
                with _db() as conn:
                    conn.execute("DELETE FROM workspace_connectors WHERE owner=? AND workspace=? AND connector_id=?",(owner,workspace,sel))
                    conn.commit()
                updated = connectors[connectors["connector_id"].astype(str) != str(sel)].copy()
                _write_registry_frame("connectors", owner, workspace, updated)
                durable = _persist_owner_workspace(owner)
                st.success("Connector removed.")
                if not durable:
                    st.warning("The removal is in the current session, but durable workspace storage did not confirm the save.")
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
                    asset_hash = _hash_df(df)
                    created_at = _now()
                    asset_row = {
                        "asset_id": asset_id,
                        "filename": str(upload.name),
                        "sheet": str(sheet),
                        "rows": int(len(df)),
                        "columns": int(len(df.columns)),
                        "sha256": asset_hash,
                        "created_at": created_at,
                    }
                    with _db() as conn:
                        conn.execute("INSERT OR REPLACE INTO workspace_data_assets(owner,workspace,asset_id,filename,sheet,rows,columns,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(owner,workspace,asset_id,str(upload.name),sheet,len(df),len(df.columns),asset_hash,created_at))
                        conn.commit()
                    updated_assets = assets[assets["asset_id"].astype(str) != asset_id].copy()
                    updated_assets = pd.concat([updated_assets, pd.DataFrame([asset_row])], ignore_index=True)
                    _write_registry_frame("assets", owner, workspace, updated_assets)
                    try:
                        from shoir_enterprise_services import record_workspace_artifact
                        record_workspace_artifact("dataset",str(upload.name),owner,{"sheet":sheet,"rows":len(df),"columns":len(df.columns),"sha256":asset_hash})
                    except Exception:
                        pass
                    durable = _persist_owner_workspace(owner)
                    st.success(f"{upload.name} · {sheet} is now the shared active dataset.")
                    if not durable:
                        st.warning("The dataset is active in this session, but durable workspace storage did not confirm the save.")
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
            created_at = _now()
            work_item_id = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
            activity_row = {
                "id": work_item_id,
                "kind": kind,
                "subject": subject.strip(),
                "details": details.strip(),
                "assignee": assignee.strip(),
                "reviewer": reviewer.strip(),
                "status": "Open",
                "created_at": created_at,
            }
            with _db() as conn:
                conn.execute("INSERT OR REPLACE INTO workspace_collaboration(id,owner,workspace,kind,subject,details,assignee,reviewer,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(work_item_id,owner,workspace,kind,subject.strip(),details.strip(),assignee.strip(),reviewer.strip(),"Open",created_at))
                conn.commit()
            updated_activity = pd.concat([pd.DataFrame([activity_row]), activity], ignore_index=True)
            _write_registry_frame("activity", owner, workspace, updated_activity)
            durable = _persist_owner_workspace(owner)
            st.success("Collaboration item saved to the workspace.")
            if not durable:
                st.warning("The item is in the current session, but durable workspace storage did not confirm the save.")
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
                        updated_activity = activity.copy()
                        updated_activity.loc[updated_activity["id"].astype(str) == str(pick), "status"] = new_status
                        _write_registry_frame("activity", owner, workspace, updated_activity)
                        durable = _persist_owner_workspace(owner)
                        st.success("Work item updated.")
                        if not durable:
                            st.warning("The status change is in the current session, but durable workspace storage did not confirm the save.")
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
