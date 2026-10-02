"""Facility Layout, Material Handling & Warehousing workspace.

Persistent department registry + editable From-To flows + SLP relationships +
scenario routing. The workspace is intentionally self-contained so CRUD edits
immediately drive every visual and analysis surface.
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


def _workspace(owner: str) -> str:
    return str(
        st.session_state.get("shoir_workspace_name")
        or st.session_state.get("workspace")
        or st.session_state.get("active_workspace_name")
        or "default"
    )[:120]


def _db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, timeout=30)


def _key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value)).strip("_").lower()


def _default_departments() -> list[dict[str, Any]]:
    return [
        {"id": "D1", "name": "Receiving & Unloading", "x": 10, "y": 80, "area_sqm": 450},
        {"id": "D2", "name": "Raw Material Storage", "x": 30, "y": 80, "area_sqm": 600},
        {"id": "D3", "name": "CNC Machining Center", "x": 30, "y": 50, "area_sqm": 800},
        {"id": "D4", "name": "Sub-Assembly Line", "x": 70, "y": 50, "area_sqm": 700},
        {"id": "D5", "name": "Quality Testing & QC", "x": 70, "y": 20, "area_sqm": 350},
        {"id": "D6", "name": "Finished Goods & Shipping", "x": 90, "y": 20, "area_sqm": 500},
    ]


def _default_flows() -> list[dict[str, Any]]:
    return [
        {"flow_id": "F001", "from_id": "D1", "to_id": "D2", "loads_day": 120, "distance_m": 22.0, "relationship": "A", "reason": "Receiving to storage"},
        {"flow_id": "F002", "from_id": "D2", "to_id": "D3", "loads_day": 150, "distance_m": 30.0, "relationship": "A", "reason": "High transfer volume"},
        {"flow_id": "F003", "from_id": "D2", "to_id": "D4", "loads_day": 20, "distance_m": 45.0, "relationship": "O", "reason": "Occasional replenishment"},
        {"flow_id": "F004", "from_id": "D3", "to_id": "D4", "loads_day": 180, "distance_m": 40.0, "relationship": "E", "reason": "Sequential workflow"},
        {"flow_id": "F005", "from_id": "D3", "to_id": "D5", "loads_day": 15, "distance_m": 55.0, "relationship": "O", "reason": "Inspection handoff"},
        {"flow_id": "F006", "from_id": "D4", "to_id": "D5", "loads_day": 160, "distance_m": 30.0, "relationship": "A", "reason": "Quality handoff"},
        {"flow_id": "F007", "from_id": "D4", "to_id": "D6", "loads_day": 30, "distance_m": 48.0, "relationship": "O", "reason": "Direct staging"},
        {"flow_id": "F008", "from_id": "D5", "to_id": "D6", "loads_day": 170, "distance_m": 22.0, "relationship": "E", "reason": "Finished goods release"},
    ]


def ensure_facility_schema() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facility_departments(
                owner TEXT NOT NULL,
                workspace TEXT NOT NULL,
                dept_id TEXT NOT NULL,
                name TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                area_sqm REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(owner, workspace, dept_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facility_flows(
                owner TEXT NOT NULL,
                workspace TEXT NOT NULL,
                flow_id TEXT NOT NULL,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                loads_day REAL NOT NULL DEFAULT 0,
                distance_m REAL NOT NULL DEFAULT 0,
                relationship TEXT NOT NULL DEFAULT 'O',
                reason TEXT,
                transport TEXT NOT NULL DEFAULT 'Forklift',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(owner, workspace, flow_id)
            )
            """
        )
        conn.commit()


def _load_departments(owner: str, workspace: str) -> pd.DataFrame:
    ensure_facility_schema()
    with _db() as conn:
        df = pd.read_sql_query(
            """
            SELECT dept_id AS id,name,x,y,area_sqm
            FROM facility_departments
            WHERE owner=? AND workspace=? AND active=1
            ORDER BY dept_id
            """,
            conn,
            params=(owner, workspace),
        )
    return df


def _load_flows(owner: str, workspace: str) -> pd.DataFrame:
    ensure_facility_schema()
    with _db() as conn:
        df = pd.read_sql_query(
            """
            SELECT flow_id,from_id,to_id,loads_day,distance_m,relationship,
                   reason,transport,updated_at
            FROM facility_flows
            WHERE owner=? AND workspace=?
            ORDER BY flow_id
            """,
            conn,
            params=(owner, workspace),
        )
    return df


def _save_departments(owner: str, workspace: str, rows: list[dict[str, Any]]) -> None:
    ensure_facility_schema()
    now = _now()
    with _db() as conn:
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO facility_departments
                (owner,workspace,dept_id,name,x,y,area_sqm,active,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    owner, workspace, str(row["id"]).strip(), str(row["name"]).strip(),
                    float(row["x"]), float(row["y"]), float(row["area_sqm"]), 1, now,
                ),
            )
        conn.commit()


def _seed_or_migrate(owner: str, workspace: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    depts = _load_departments(owner, workspace)
    flows = _load_flows(owner, workspace)
    if depts.empty:
        legacy = st.session_state.get("facility_depts")
        rows = legacy if isinstance(legacy, list) and legacy else _default_departments()
        _save_departments(owner, workspace, rows)
        depts = _load_departments(owner, workspace)
    if flows.empty and len(depts) >= 2:
        ids = set(depts["id"].astype(str))
        defaults = [r for r in _default_flows() if r["from_id"] in ids and r["to_id"] in ids]
        if defaults:
            with _db() as conn:
                for r in defaults:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO facility_flows
                        (owner,workspace,flow_id,from_id,to_id,loads_day,distance_m,relationship,reason,transport,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            owner, workspace, r["flow_id"], r["from_id"], r["to_id"],
                            r["loads_day"], r["distance_m"], r["relationship"],
                            r["reason"], "Forklift", _now(),
                        ),
                    )
                conn.commit()
            flows = _load_flows(owner, workspace)
    st.session_state["facility_depts"] = depts.to_dict("records")
    st.session_state["facility_flows_df"] = flows.copy(deep=True)
    return depts, flows


def _distance(a: pd.Series, b: pd.Series) -> float:
    return float(math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"])))


def _layout_figure(depts: pd.DataFrame, flows: pd.DataFrame | None = None) -> go.Figure:
    fig = go.Figure()
    if flows is not None and not flows.empty:
        for row in flows.itertuples(index=False):
            s = depts[depts["id"].astype(str) == str(row.from_id)]
            t = depts[depts["id"].astype(str) == str(row.to_id)]
            if s.empty or t.empty:
                continue
            srow, trow = s.iloc[0], t.iloc[0]
            fig.add_trace(
                go.Scatter(
                    x=[srow["x"], trow["x"], None],
                    y=[srow["y"], trow["y"], None],
                    mode="lines",
                    line=dict(width=max(1.0, min(7.0, 1.0 + float(row.loads_day) / 50.0))),
                    hovertemplate=f"{row.from_id} → {row.to_id}<br>{float(row.loads_day):,.0f} loads/day<br>{float(row.distance_m):,.1f} m<extra></extra>",
                    showlegend=False,
                )
            )
    for row in depts.itertuples(index=False):
        side = max(5.0, min(18.0, math.sqrt(max(1.0, float(row.area_sqm))) / 3.2))
        x, y = float(row.x), float(row.y)
        fig.add_shape(
            type="rect",
            x0=x - side / 2, x1=x + side / 2,
            y0=y - side / 2, y1=y + side / 2,
            line=dict(width=2),
            fillcolor="rgba(37,99,235,0.16)",
        )
    fig.add_trace(
        go.Scatter(
            x=depts["x"], y=depts["y"], mode="markers+text",
            text=depts["id"], textposition="middle center",
            marker=dict(size=28, line=dict(width=2)),
            customdata=depts[["name","area_sqm"]].astype(str).values,
            hovertemplate="<b>%{text}</b><br>%{customdata[0]}<br>%{customdata[1]} m²<extra></extra>",
            showlegend=False,
        )
    )
    for row in depts.itertuples(index=False):
        fig.add_annotation(x=float(row.x), y=float(row.y) + 8, text=str(row.name), showarrow=False, font=dict(size=10))
    fig.update_layout(
        height=560, margin=dict(l=10,r=10,t=35,b=10),
        xaxis=dict(range=[0,105], title="X · plant coordinates", gridcolor="#e2e8f0", zeroline=False),
        yaxis=dict(range=[0,105], title="Y · plant coordinates", gridcolor="#e2e8f0", zeroline=False),
        plot_bgcolor="#f8fafc", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _flow_process_figure(depts: pd.DataFrame, flows: pd.DataFrame) -> go.Figure:
    """Render every department, plus directional connections where defined."""
    fig = go.Figure()
    for row in flows.itertuples(index=False):
        s = depts[depts["id"].astype(str) == str(row.from_id)]
        t = depts[depts["id"].astype(str) == str(row.to_id)]
        if s.empty or t.empty:
            continue
        srow, trow = s.iloc[0], t.iloc[0]
        fig.add_trace(
            go.Scatter(
                x=[srow["x"], trow["x"]],
                y=[srow["y"], trow["y"]],
                mode="lines+markers",
                line=dict(width=max(1.5, min(8.0, 1 + float(row.loads_day)/45))),
                marker=dict(size=9),
                name=f"{row.from_id} → {row.to_id}",
                hovertemplate=f"{row.from_id} → {row.to_id}<br>Loads/day: {float(row.loads_day):,.0f}<br>Distance: {float(row.distance_m):,.1f} m<br>REL: {row.relationship}<extra></extra>",
            )
        )
    if not depts.empty:
        fig.add_trace(
            go.Scatter(
                x=depts["x"], y=depts["y"], mode="markers+text",
                text=depts["id"], textposition="middle center",
                marker=dict(size=32),
                customdata=depts[["name"]].astype(str).values,
                hovertemplate="<b>%{text}</b><br>%{customdata[0]}<extra></extra>",
                showlegend=False,
            )
        )
        for row in depts.itertuples(index=False):
            fig.add_annotation(x=float(row.x), y=float(row.y)+7, text=str(row.name), showarrow=False, font=dict(size=10))
    fig.update_layout(
        height=520, title="Department process map · connected and unconnected nodes",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        legend=dict(orientation="v"),
        margin=dict(l=10,r=10,t=50,b=10),
        plot_bgcolor="#f8fafc", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _flow_matrix(depts: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    """Return a complete From-To load matrix, including zero/unconnected pairs."""
    ids = depts["id"].astype(str).tolist()
    out = pd.DataFrame(0.0, index=ids, columns=ids)
    if not flows.empty:
        for row in flows.itertuples(index=False):
            frm, to = str(row.from_id), str(row.to_id)
            if frm in out.index and to in out.columns:
                out.loc[frm, to] += float(row.loads_day)
    out.index.name = "From / To"
    return out


def _slp_frame(depts: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    """Return explicit rows for every department pair.

    A newly added department therefore appears immediately in SLP even before
    a user creates its first process connection.
    """
    names = {str(r.id): str(r.name) for r in depts.itertuples()}
    flow_lookup = {
        (str(r.from_id), str(r.to_id)): r for r in flows.itertuples(index=False)
    } if not flows.empty else {}
    ids = list(names)
    records = []
    rel_scores = {"A": 4, "E": 3, "I": 2, "O": 1, "U": 0, "X": -1}

    for frm in ids:
        for to in ids:
            if frm == to:
                continue
            row = flow_lookup.get((frm, to))
            if row is None:
                records.append({
                    "From": frm, "To": to,
                    "From Department": names[frm],
                    "To Department": names[to],
                    "Daily Loads": 0.0,
                    "Distance (m)": 0.0,
                    "REL": "—",
                    "Score": None,
                    "Reason": "No connection defined",
                    "Status": "Unconnected",
                })
                continue
            rel = str(row.relationship).upper()
            records.append({
                "From": frm, "To": to,
                "From Department": names[frm],
                "To Department": names[to],
                "Daily Loads": float(row.loads_day),
                "Distance (m)": float(row.distance_m),
                "REL": rel,
                "Score": rel_scores.get(rel, 1),
                "Reason": str(row.reason or ""),
                "Status": "Connected",
            })
    return pd.DataFrame(records)


def _matrix(depts: pd.DataFrame, slp: pd.DataFrame) -> pd.DataFrame:
    ids = depts["id"].astype(str).tolist()
    out = pd.DataFrame("", index=ids, columns=ids)
    for r in slp.to_dict("records"):
        if str(r["From"]) in out.index and str(r["To"]) in out.columns:
            rel = str(r.get("REL", ""))
            if rel != "—":
                out.loc[str(r["From"]), str(r["To"])] = rel
    return out


def _shortest_path(flows: pd.DataFrame, start: str, end: str, avoid: str | None = None) -> tuple[list[str], float, float]:
    graph: dict[str, list[tuple[str,float,float]]] = {}
    for r in flows.itertuples(index=False):
        if avoid and (str(r.from_id) == avoid or str(r.to_id) == avoid):
            continue
        graph.setdefault(str(r.from_id), []).append((str(r.to_id), float(r.distance_m), float(r.loads_day)))
        graph.setdefault(str(r.to_id), []).append((str(r.from_id), float(r.distance_m), float(r.loads_day)))
    import heapq
    heap = [(0.0, start, [start], 0.0)]
    seen: dict[str,float] = {}
    while heap:
        dist, node, path, volume = heapq.heappop(heap)
        if node in seen and seen[node] <= dist:
            continue
        seen[node] = dist
        if node == end:
            return path, dist, volume
        for nxt, edge_dist, loads in graph.get(node, []):
            if nxt in path:
                continue
            heapq.heappush(heap, (dist + edge_dist, nxt, path + [nxt], volume + loads))
    return [], math.inf, 0.0


def _file_to_frames(upload: Any) -> dict[str, pd.DataFrame]:
    raw = upload.getvalue()
    name = str(upload.name)
    try:
        from shoir_excel_studio import process_uploaded_workbook
        result = process_uploaded_workbook(raw, name)
        sheets = result.get("cleaned_sheets") or result.get("raw_sheets") or {}
        if sheets:
            return {str(k): v.copy(deep=True) for k,v in sheets.items() if isinstance(v, pd.DataFrame) and not v.empty}
    except Exception:
        pass
    lower = name.lower()
    if lower.endswith(".csv"):
        return {"Data": pd.read_csv(io.BytesIO(raw))}
    if lower.endswith(".tsv") or lower.endswith(".txt"):
        return {"Data": pd.read_csv(io.BytesIO(raw), sep="\t")}
    return {str(s): pd.read_excel(io.BytesIO(raw), sheet_name=s) for s in pd.ExcelFile(io.BytesIO(raw)).sheet_names}


def _import_data(frames: dict[str,pd.DataFrame], owner: str, workspace: str) -> tuple[int,int]:
    dept_df = next((v for k,v in frames.items() if {"id","name"} <= {str(c).lower() for c in v.columns}), pd.DataFrame())
    flow_df = next((v for k,v in frames.items() if {"from_id","to_id"} <= {str(c).lower() for c in v.columns}), pd.DataFrame())
    if dept_df.empty and frames:
        candidate = next(iter(frames.values()))
        columns = {str(c).strip().lower(): c for c in candidate.columns}
        rename = {}
        for canonical, aliases in {
            "id":["id","dept id","department id"],
            "name":["name","department","department name"],
            "x":["x","x coord","x coordinate"],
            "y":["y","y coord","y coordinate"],
            "area_sqm":["area_sqm","area","area m2","area (m²)"],
        }.items():
            found = next((columns[a] for a in aliases if a in columns), None)
            if found is not None: rename[found] = canonical
        temp = candidate.rename(columns=rename)
        if {"id","name"} <= set(temp.columns):
            dept_df = temp
    dep_count = flow_count = 0
    if not dept_df.empty:
        rows=[]
        for r in dept_df.to_dict("records"):
            rows.append({
                "id": str(r.get("id") or r.get("dept_id") or "").strip(),
                "name": str(r.get("name") or "Department").strip(),
                "x": float(pd.to_numeric(r.get("x",50), errors="coerce") if pd.notna(r.get("x",50)) else 50),
                "y": float(pd.to_numeric(r.get("y",50), errors="coerce") if pd.notna(r.get("y",50)) else 50),
                "area_sqm": float(pd.to_numeric(r.get("area_sqm",400), errors="coerce") if pd.notna(r.get("area_sqm",400)) else 400),
            })
        rows=[r for r in rows if r["id"]]
        _save_departments(owner,workspace,rows); dep_count=len(rows)
    if not flow_df.empty:
        columns={str(c).strip().lower(): c for c in flow_df.columns}
        records=[]
        for i,r in enumerate(flow_df.to_dict("records"),1):
            get=lambda *names, default="": next((r.get(columns[n]) for n in names if n in columns),default)
            records.append({
                "flow_id": str(get("flow_id","flow id",default=f"FIMP{i:03d}")).strip(),
                "from_id": str(get("from_id","from","source",default="")).strip(),
                "to_id": str(get("to_id","to","destination",default="")).strip(),
                "loads_day": float(pd.to_numeric(get("loads_day","loads/day","daily loads",default=0),errors="coerce") or 0),
                "distance_m": float(pd.to_numeric(get("distance_m","distance","distance m",default=0),errors="coerce") or 0),
                "relationship": str(get("relationship","rel",default="O") or "O").upper()[:1],
                "reason": str(get("reason","primary reason",default="Imported flow")),
                "transport": str(get("transport","handling",default="Forklift")),
            })
        records=[r for r in records if r["from_id"] and r["to_id"]]
        with _db() as conn:
            for r in records:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO facility_flows
                    (owner,workspace,flow_id,from_id,to_id,loads_day,distance_m,relationship,reason,transport,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (owner,workspace,r["flow_id"],r["from_id"],r["to_id"],r["loads_day"],r["distance_m"],r["relationship"],r["reason"],r["transport"],_now()),
                )
            conn.commit()
        flow_count=len(records)
    return dep_count, flow_count


def _export_workbook(depts: pd.DataFrame, flows: pd.DataFrame, slp: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        depts.to_excel(writer, index=False, sheet_name="Departments")
        flows.to_excel(writer, index=False, sheet_name="From_To_Flows")
        slp.to_excel(writer, index=False, sheet_name="SLP_Relationships")
        matrix=_matrix(depts,slp)
        matrix.to_excel(writer, sheet_name="SLP_Matrix")
    return out.getvalue()


def render_facility_layout(tier: str, username: str) -> None:
    owner, workspace = str(username), _workspace(username)
    depts, flows = _seed_or_migrate(owner, workspace)

    st.markdown(
        """
        <style>
        .fl-hero{padding:24px 28px;border-radius:22px;background:linear-gradient(135deg,#0b1220,#1e3a8a 55%,#0f766e);color:#fff;box-shadow:0 16px 36px rgba(15,23,42,.14);margin-bottom:16px}
        .fl-kicker{font-size:11px;font-weight:850;letter-spacing:.12em;text-transform:uppercase;color:#7dd3fc}
        .fl-title{font-size:30px;font-weight:900;letter-spacing:-.03em;margin-top:4px}
        .fl-sub{color:#dbeafe;max-width:950px;font-size:13px;margin-top:6px}
        .fl-pill{display:inline-block;padding:5px 9px;border:1px solid rgba(255,255,255,.14);border-radius:999px;background:rgba(255,255,255,.08);margin:12px 6px 0 0;font-size:11px}
        </style>
        <div class="fl-hero">
          <div class="fl-kicker">Facilities · Layout Engineering</div>
          <div class="fl-title">🏭 Facility Layout & Warehousing Studio</div>
          <div class="fl-sub">Build the physical department layout, connect departments into a material-flow network, evaluate SLP relationships, and test alternate process paths without losing the underlying registry.</div>
          <span class="fl-pill">Persistent CRUD</span><span class="fl-pill">Connected From-To</span><span class="fl-pill">Live SLP</span><span class="fl-pill">Scenario routing</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if depts.empty:
        st.warning("No departments are registered. Add the first department in Block Layout & CRUD.")
    slp = _slp_frame(depts, flows)

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Departments", f"{len(depts):,}")
    c2.metric("Connections", f"{len(flows):,}")
    c3.metric("Total area", f"{depts['area_sqm'].sum():,.0f} m²" if not depts.empty else "0 m²")
    c4.metric("Daily movement", f"{flows['loads_day'].sum():,.0f}" if not flows.empty else "0")
    c5.metric("Connected pairs", f"{flows[['from_id','to_id']].drop_duplicates().shape[0]:,}" if not flows.empty else "0")

    tabs=st.tabs(["🗺️ Block Layout & CRUD","🔗 From-To Flow & Connections","📐 SLP & Relationship Matrix","🧪 Process What-If","📥 Import / Export"])

    with tabs[0]:
        left,right=st.columns([1.8,1])
        with left:
            st.plotly_chart(_layout_figure(depts,flows),use_container_width=True,config={"displayModeBar":False})
            st.markdown("#### Department register")
            st.dataframe(depts.rename(columns={"id":"Dept ID","name":"Department","x":"X","y":"Y","area_sqm":"Area (m²)"}),use_container_width=True,hide_index=True)
        with right:
            action=st.radio("Layout action",["Add","Edit","Remove"],horizontal=True,key="fl_crud_action")
            if action=="Add":
                with st.form("fl_add_dept"):
                    did=st.text_input("Department ID","D7",key="fl_add_id")
                    name=st.text_input("Department name","Packaging & Palletizing",key="fl_add_name")
                    x=st.number_input("X coordinate",0.0,100.0,50.0,1.0,key="fl_add_x")
                    y=st.number_input("Y coordinate",0.0,100.0,50.0,1.0,key="fl_add_y")
                    area=st.number_input("Footprint (m²)",25.0,10000.0,400.0,25.0,key="fl_add_area")
                    submit=st.form_submit_button("➕ Add department",type="primary",use_container_width=True)
                if submit:
                    did=did.strip()
                    if not did or not name.strip(): st.error("Department ID and name are required.")
                    elif did in set(depts["id"].astype(str)): st.error(f"Department ID {did} already exists.")
                    else:
                        _save_departments(owner,workspace,[{"id":did,"name":name,"x":x,"y":y,"area_sqm":area}])
                        st.success(f"{name} ({did}) is now part of the live department registry. It will appear in From-To and SLP immediately.")
                        st.rerun()
            elif action=="Edit":
                ids=depts["id"].astype(str).tolist()
                if ids:
                    selected=st.selectbox("Department to edit",ids,key="fl_edit_dept")
                    row=depts[depts["id"].astype(str)==selected].iloc[0]
                    with st.form("fl_edit_dept_form"):
                        name=st.text_input("Department name",str(row["name"]),key="fl_edit_name")
                        x=st.number_input("X coordinate",0.0,100.0,float(row["x"]),1.0,key="fl_edit_x")
                        y=st.number_input("Y coordinate",0.0,100.0,float(row["y"]),1.0,key="fl_edit_y")
                        area=st.number_input("Footprint (m²)",25.0,10000.0,float(row["area_sqm"]),25.0,key="fl_edit_area")
                        save=st.form_submit_button("💾 Save department",type="primary",use_container_width=True)
                    if save:
                        _save_departments(owner,workspace,[{"id":selected,"name":name,"x":x,"y":y,"area_sqm":area}])
                        st.success("Department updated. Connected flows and SLP read the same persistent registry.")
                        st.rerun()
                else: st.info("Add a department first.")
            else:
                ids=depts["id"].astype(str).tolist()
                target=st.selectbox("Department to remove",ids if ids else ["None"],key="fl_del_dept")
                confirm=st.checkbox("I understand that its connections will also be removed.",key="fl_del_confirm")
                if st.button("🗑️ Remove department",type="primary",disabled=target=="None" or not confirm,use_container_width=True,key="fl_del_btn"):
                    with _db() as conn:
                        conn.execute("UPDATE facility_departments SET active=0,updated_at=? WHERE owner=? AND workspace=? AND dept_id=?",( _now(),owner,workspace,target))
                        conn.execute("DELETE FROM facility_flows WHERE owner=? AND workspace=? AND (from_id=? OR to_id=?)",(owner,workspace,target,target))
                        conn.commit()
                    st.success("Department and dependent connections removed from the active process model.")
                    st.rerun()

    with tabs[1]:
        st.markdown("### Connect departments to model the process")
        st.markdown("#### From-To load matrix")
        st.dataframe(
            _flow_matrix(depts, flows),
            use_container_width=True,
        )
        st.caption("Every connection below feeds the From-To table, process map, SLP relationship matrix, and what-if routing. Direction matters; the route model also uses the connection as a navigable edge.")
        a,b=st.columns([1.1,1.4])
        ids=depts["id"].astype(str).tolist()
        with a:
            with st.form("fl_add_flow"):
                frm=st.selectbox("From department",ids if ids else [""],key="fl_flow_from")
                to=st.selectbox("To department",ids if ids else [""],key="fl_flow_to")
                loads=st.number_input("Loads / day",0.0,100000.0,100.0,5.0,key="fl_flow_loads")
                distance=st.number_input("Travel distance (m)",0.0,10000.0,25.0,1.0,key="fl_flow_distance")
                rel=st.selectbox("SLP relationship",["A","E","I","O","U","X"],index=0,key="fl_flow_rel")
                transport=st.selectbox("Handling mode",["Forklift","AMR / AGV","Conveyor","Pallet Jack","Manual"],key="fl_flow_transport")
                reason=st.text_input("Reason / process step","Material transfer",key="fl_flow_reason")
                add=st.form_submit_button("🔗 Create connection",type="primary",use_container_width=True)
            if add:
                if not frm or not to or frm==to: st.error("Choose two different departments.")
                else:
                    flow_id=f"F{len(flows)+1:03d}"
                    existing=set(flows["flow_id"].astype(str)) if not flows.empty else set()
                    while flow_id in existing: flow_id=f"F{int(flow_id[1:])+1:03d}"
                    with _db() as conn:
                        conn.execute(
                            "INSERT INTO facility_flows(owner,workspace,flow_id,from_id,to_id,loads_day,distance_m,relationship,reason,transport,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (owner,workspace,flow_id,frm,to,loads,distance,rel,reason,transport,_now()),
                        )
                        conn.commit()
                    st.success(f"Connected {frm} → {to}. The live From-To and SLP surfaces are updated.")
                    st.rerun()
        with b:
            st.plotly_chart(_flow_process_figure(depts,flows),use_container_width=True,config={"displayModeBar":False})
        st.markdown("#### Edit or remove an existing connection")
        if not flows.empty:
            labels={str(r.flow_id):f"{r.flow_id} · {r.from_id} → {r.to_id}" for r in flows.itertuples()}
            fid=st.selectbox("Connection",list(labels),format_func=labels.get,key="fl_edit_flow_id")
            current=flows[flows["flow_id"].astype(str)==fid].iloc[0]
            with st.form("fl_edit_flow_form"):
                e1,e2,e3=st.columns(3)
                with e1:
                    frm2=st.selectbox("From",ids,index=ids.index(str(current["from_id"])) if str(current["from_id"]) in ids else 0,key="fl_e_from")
                    to2=st.selectbox("To",ids,index=ids.index(str(current["to_id"])) if str(current["to_id"]) in ids else min(1,len(ids)-1),key="fl_e_to")
                    loads2=st.number_input("Loads/day",0.0,100000.0,float(current["loads_day"]),5.0,key="fl_e_loads")
                with e2:
                    dist2=st.number_input("Distance (m)",0.0,10000.0,float(current["distance_m"]),1.0,key="fl_e_dist")
                    rel2=st.selectbox("SLP relationship",["A","E","I","O","U","X"],index=["A","E","I","O","U","X"].index(str(current["relationship"])) if str(current["relationship"]) in ["A","E","I","O","U","X"] else 3,key="fl_e_rel")
                    mode2=st.selectbox("Handling mode",["Forklift","AMR / AGV","Conveyor","Pallet Jack","Manual"],index=["Forklift","AMR / AGV","Conveyor","Pallet Jack","Manual"].index(str(current["transport"])) if str(current["transport"]) in ["Forklift","AMR / AGV","Conveyor","Pallet Jack","Manual"] else 0,key="fl_e_mode")
                with e3:
                    reason2=st.text_input("Reason / process step",str(current["reason"] or ""))
                    up=st.form_submit_button("💾 Update connection",type="primary",use_container_width=True)
                if up:
                    if frm2==to2: st.error("From and To departments must be different.")
                    else:
                        with _db() as conn:
                            conn.execute(
                                "UPDATE facility_flows SET from_id=?,to_id=?,loads_day=?,distance_m=?,relationship=?,reason=?,transport=?,updated_at=? WHERE owner=? AND workspace=? AND flow_id=?",
                                (frm2,to2,loads2,dist2,rel2,reason2,mode2,_now(),owner,workspace,fid),
                            )
                            conn.commit()
                        st.success("Connection updated; all dependent views use the new edge.")
                        st.rerun()
            if st.button("🗑️ Remove connection",use_container_width=True,key="fl_delete_flow"):
                with _db() as conn:
                    conn.execute("DELETE FROM facility_flows WHERE owner=? AND workspace=? AND flow_id=?",(owner,workspace,fid))
                    conn.commit()
                st.success("Connection removed.")
                st.rerun()
            flow_view=flows.copy()
            st.dataframe(flow_view.rename(columns={"flow_id":"Flow ID","from_id":"From","to_id":"To","loads_day":"Loads/day","distance_m":"Distance (m)","relationship":"REL","reason":"Reason","transport":"Handling"}),use_container_width=True,hide_index=True)
        else:
            st.info("No process connections yet. Create the first connection from the form above.")

    with tabs[2]:
        st.markdown("### Systematic Layout Planning")
        st.caption("SLP reads the same persistent connections used by the From-To process model. Every department pair is shown; unconnected pairs are explicitly marked so new departments never disappear from the SLP model.")
        st.dataframe(slp,use_container_width=True,hide_index=True)
        if not depts.empty:
            matrix=_matrix(depts,slp)
            st.markdown("#### Relationship matrix")
            st.dataframe(matrix,use_container_width=True)
            numeric=slp.groupby("REL",as_index=False).agg(Connections=("REL","size"),Daily_Loads=("Daily Loads","sum")) if not slp.empty else pd.DataFrame()
            if not numeric.empty:
                st.plotly_chart(px.bar(numeric,x="REL",y="Connections",text="Connections",title="SLP relationship mix"),use_container_width=True,config={"displayModeBar":False})
            if not slp.empty:
                heat=matrix.replace("",float("nan")).replace("—",float("nan"))
                heat=heat.applymap({"A":4,"E":3,"I":2,"O":1,"U":0,"X":-1}.get)
                st.plotly_chart(px.imshow(heat,text_auto=True,aspect="auto",title="SLP closeness heatmap · A=4 … X=-1"),use_container_width=True,config={"displayModeBar":False})

    with tabs[3]:
        st.markdown("### Process scenario laboratory")
        st.caption("See how a selected routing path changes when a department is avoided. This is a graph/path calculation, not a claim about real-world traffic performance.")
        ids=depts["id"].astype(str).tolist()
        if len(ids)>=2 and not flows.empty:
            p1,p2,p3=st.columns(3)
            start=p1.selectbox("Process starts at",ids,key="fl_scenario_start")
            end=p2.selectbox("Process ends at",ids,index=min(1,len(ids)-1),key="fl_scenario_end")
            avoid=p3.selectbox("Avoid / relocate department",["None"]+ids,key="fl_scenario_avoid")
            avoid_id=None if avoid=="None" else avoid
            base_path,base_dist,base_vol=_shortest_path(flows,start,end,None)
            alt_path,alt_dist,alt_vol=_shortest_path(flows,start,end,avoid_id)
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Baseline path", " → ".join(base_path) if base_path else "No route")
            c2.metric("Baseline distance", f"{base_dist:.1f} m" if math.isfinite(base_dist) else "—")
            c3.metric("Alternate path", " → ".join(alt_path) if alt_path else "No route")
            c4.metric("Alternate distance", f"{alt_dist:.1f} m" if math.isfinite(alt_dist) else "—")
            comparison=pd.DataFrame([
                {"Scenario":"Baseline","Path":" → ".join(base_path) if base_path else "No route","Distance (m)":base_dist if math.isfinite(base_dist) else None},
                {"Scenario":"Avoid "+(avoid_id or "none"),"Path":" → ".join(alt_path) if alt_path else "No route","Distance (m)":alt_dist if math.isfinite(alt_dist) else None},
            ])
            st.dataframe(comparison,use_container_width=True,hide_index=True)
            if comparison["Distance (m)"].notna().any():
                st.plotly_chart(px.bar(comparison.dropna(subset=["Distance (m)"]),x="Scenario",y="Distance (m)",text="Distance (m)",title="Routing distance impact"),use_container_width=True,config={"displayModeBar":False})
        else:
            st.info("Create at least two departments and one connection to activate path scenarios.")

    with tabs[4]:
        st.markdown("### Move layouts between Shoir-IE workspaces")
        upload=st.file_uploader("📥 Import Departments / From-To workbook",type=["xlsx","xlsm","xls","csv","tsv","txt"],key="fl_import")
        if upload is not None:
            try:
                frames=_file_to_frames(upload)
                dep_count,flow_count=_import_data(frames,owner,workspace)
                if dep_count or flow_count:
                    st.success(f"Imported {dep_count:,} department(s) and {flow_count:,} connection(s). They are now live in this workspace.")
                    st.rerun()
                st.error("No recognizable department or flow table was found. Use Department columns ID, Name, X, Y, Area and flow columns From_ID, To_ID, Loads_Day, Distance_M, Relationship.")
            except Exception as exc:
                st.error(f"Import failed safely: {type(exc).__name__}: {exc}")
        st.markdown("#### Export current facility model")
        export=_export_workbook(depts,flows,slp)
        st.download_button("📥 Download Facility Model Workbook",data=export,file_name="shoir_ie_facility_layout.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",type="primary",use_container_width=True,key="fl_export_workbook")
        st.download_button("📄 Download From-To CSV",data=flows.to_csv(index=False).encode("utf-8"),file_name="facility_from_to.csv",mime="text/csv",use_container_width=True,key="fl_export_fromto")
        st.caption("The workbook contains Departments, From_To_Flows, SLP_Relationships and SLP_Matrix sheets.")

    # Keep the legacy state contract synchronized for older modules that read it.
    st.session_state["facility_depts"]=depts.to_dict("records")
    st.session_state["facility_flows_df"]=flows.copy(deep=True)
    st.session_state["facility_layout_live"]=depts.copy(deep=True)
