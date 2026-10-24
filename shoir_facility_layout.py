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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facility_workspace_metadata(
                owner TEXT NOT NULL,
                workspace TEXT NOT NULL,
                data_origin TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(owner, workspace)
            )
            """
        )
        conn.commit()


def _get_data_origin(owner: str, workspace: str) -> str:
    ensure_facility_schema()
    with _db() as conn:
        row = conn.execute(
            "SELECT data_origin FROM facility_workspace_metadata WHERE owner=? AND workspace=?",
            (owner, workspace),
        ).fetchone()
    return str(row[0]) if row else "EXISTING_DATA_ORIGIN_UNVERIFIED"


def _set_data_origin(owner: str, workspace: str, data_origin: str) -> None:
    allowed = {
        "SYNTHETIC_STARTER_DATA",
        "USER_EDITED_OR_MIXED",
        "IMPORTED_OR_UPSERTED",
        "EXISTING_DATA_ORIGIN_UNVERIFIED",
    }
    if data_origin not in allowed:
        raise ValueError("Unsupported facility data-origin status.")
    ensure_facility_schema()
    with _db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO facility_workspace_metadata(owner,workspace,data_origin,updated_at)
            VALUES(?,?,?,?)
            """,
            (owner, workspace, data_origin, _now()),
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
    was_empty = depts.empty and flows.empty
    legacy_rows_present = isinstance(st.session_state.get("facility_depts"), list) and bool(st.session_state.get("facility_depts"))
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
    # Brand-new auto-populated examples are labelled synthetic. Existing rows
    # predating the provenance table remain explicitly unverified.
    with _db() as conn:
        origin_row = conn.execute(
            "SELECT data_origin FROM facility_workspace_metadata WHERE owner=? AND workspace=?",
            (owner, workspace),
        ).fetchone()
    if origin_row is None:
        _set_data_origin(
            owner, workspace,
            "SYNTHETIC_STARTER_DATA"
            if was_empty and not legacy_rows_present and not depts.empty
            else "EXISTING_DATA_ORIGIN_UNVERIFIED",
        )
    st.session_state["facility_depts"] = depts.to_dict("records")
    st.session_state["facility_flows_df"] = flows.copy(deep=True)
    return depts, flows


def _flow_distance_metrics(
    flows: pd.DataFrame, cost_per_load_meter_sar: float | None = None
) -> dict[str, Any]:
    """Compute daily weighted flow-distance and optional uniform-rate cost."""
    if flows is None or flows.empty:
        if cost_per_load_meter_sar is not None:
            rate = float(cost_per_load_meter_sar)
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError("Handling cost rate must be finite and greater than zero.")
        else:
            rate = None
        return {
            "status": "NO_DATA",
            "connection_count": 0,
            "weighted_flow_distance_load_m_per_day": 0.0,
            "cost_rate_sar_per_load_meter": rate,
            "estimated_daily_handling_cost_sar": None,
            "formula": "weighted flow-distance = sum(loads/day × distance in metres)",
            "provenance": "No flow records are available.",
            "warnings": ["Add validated directed flow records before interpreting flow-distance or handling cost."],
        }
    required = {"loads_day", "distance_m"}
    if not required.issubset(flows.columns):
        raise ValueError(f"Flow metrics require columns {sorted(required)}.")
    weighted = 0.0
    for index, row in flows.iterrows():
        try:
            loads = float(row["loads_day"])
            distance = float(row["distance_m"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Flow row {index!r} has a non-numeric load or distance.") from exc
        if not math.isfinite(loads) or not math.isfinite(distance):
            raise ValueError(f"Flow row {index!r} has a non-finite load or distance.")
        if loads < 0 or distance < 0:
            raise ValueError(f"Flow row {index!r} has a negative load or distance.")
        weighted += loads * distance
    if not math.isfinite(weighted):
        raise ValueError("Weighted flow-distance is not finite; review input magnitudes.")
    rate: float | None = None
    estimated_cost: float | None = None
    warnings = []
    if cost_per_load_meter_sar is not None:
        rate = float(cost_per_load_meter_sar)
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Handling cost rate must be finite and greater than zero.")
        estimated_cost = weighted * rate
        if not math.isfinite(estimated_cost):
            raise ValueError("Estimated handling cost is not finite; review rate and flow magnitudes.")
        warnings.append(
            "Cost is an estimate using one user-provided uniform SAR per load-metre rate for every flow; actual transport/handling differences are not modelled."
        )
    else:
        warnings.append("Handling cost is not calculated until a positive, user-approved rate is supplied.")
    return {
        "status": "COMPLETED",
        "connection_count": int(len(flows)),
        "weighted_flow_distance_load_m_per_day": weighted,
        "cost_rate_sar_per_load_meter": rate,
        "estimated_daily_handling_cost_sar": estimated_cost,
        "formula": "weighted flow-distance = Σ(loads/day × distance (m)); estimated daily cost = weighted flow-distance × user-supplied SAR per load-metre rate",
        "provenance": "User/workspace flow records; no real-world cost rate is inferred.",
        "warnings": warnings,
    }


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
    """Render every department with directional connections and edge detail."""
    fig = go.Figure()
    if not flows.empty:
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
                    mode="lines",
                    line=dict(width=max(1.8, min(9.0, 1.5 + float(row.loads_day) / 40))),
                    name=f"{row.from_id} → {row.to_id}",
                    hovertemplate=(
                        f"<b>{row.from_id} → {row.to_id}</b><br>"
                        f"Loads/day: {float(row.loads_day):,.0f}<br>"
                        f"Distance: {float(row.distance_m):,.1f} m<br>"
                        f"SLP: {row.relationship}<br>"
                        f"Handling: {row.transport}<extra></extra>"
                    ),
                    showlegend=True,
                )
            )
            fig.add_annotation(
                x=float(trow["x"]),
                y=float(trow["y"]),
                ax=float(srow["x"]),
                ay=float(srow["y"]),
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                text="",
                showarrow=True,
                arrowhead=3,
                arrowsize=1.1,
                arrowwidth=1.6,
                opacity=0.85,
            )
    if not depts.empty:
        fig.add_trace(
            go.Scatter(
                x=depts["x"],
                y=depts["y"],
                mode="markers+text",
                text=depts["id"],
                textposition="middle center",
                marker=dict(size=32),
                customdata=depts[["name"]].astype(str).values,
                hovertemplate="<b>%{text}</b><br>%{customdata[0]}<extra></extra>",
                showlegend=False,
            )
        )
        for row in depts.itertuples(index=False):
            fig.add_annotation(
                x=float(row.x), y=float(row.y) + 7,
                text=str(row.name), showarrow=False,
                font=dict(size=10),
            )
    fig.update_layout(
        height=520,
        title="Department process map · directional material flow",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        legend=dict(orientation="v"),
        margin=dict(l=10, r=10, t=50, b=10),
        plot_bgcolor="#f8fafc",
        paper_bgcolor="rgba(0,0,0,0)",
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
            raw_rel = getattr(row, "relationship", "")
            rel = "" if _import_blank(raw_rel) else str(raw_rel).strip().upper()
            records.append({
                "From": frm, "To": to,
                "From Department": names[frm],
                "To Department": names[to],
                "Daily Loads": float(row.loads_day),
                "Distance (m)": float(row.distance_m),
                "REL": rel,
                "Score": rel_scores.get(rel),
                "Reason": str(getattr(row, "reason", "") or ""),
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


def _slp_heatmap_values(matrix: pd.DataFrame) -> pd.DataFrame:
    """Convert SLP relationship codes to scores without deprecated DataFrame.applymap.

    Series.map is supported across the pandas versions used by Shoir-IE and maps
    unknown/unconnected cells to NaN so Plotly renders those cells as blank.
    """
    scores = {"A": 4, "E": 3, "I": 2, "O": 1, "U": 0, "X": -1}
    return matrix.apply(lambda column: column.map(scores))


def _shortest_path(
    flows: pd.DataFrame,
    start: str,
    end: str,
    avoid: str | None = None,
    avoid_flow_id: str | None = None,
) -> tuple[list[str], float, float]:
    """Find the shortest directed process path, optionally excluding a department or edge."""
    graph: dict[str, list[tuple[str,float,float,str]]] = {}
    for r in flows.itertuples(index=False):
        flow_id = str(getattr(r, "flow_id", ""))
        if avoid_flow_id and flow_id == str(avoid_flow_id):
            continue
        if avoid and (str(r.from_id) == avoid or str(r.to_id) == avoid):
            continue
        graph.setdefault(str(r.from_id), []).append((str(r.to_id), float(r.distance_m), float(r.loads_day), flow_id))
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
        for nxt, edge_dist, loads, _flow_id in graph.get(node, []):
            if nxt in path:
                continue
            heapq.heappush(heap, (dist + edge_dist, nxt, path + [nxt], volume + loads))
    return [], math.inf, 0.0

def _file_to_frames(upload: Any) -> dict[str, pd.DataFrame]:
    raw = upload.getvalue()
    name = str(upload.name)
    try:
        from shoir_excel_studio import process_uploaded_workbook
    except ModuleNotFoundError as exc:
        # Fall back only when the optional processor module itself is absent.
        # A broken processor or missing transitive dependency must be visible.
        if exc.name != "shoir_excel_studio":
            raise
        process_uploaded_workbook = None

    if process_uploaded_workbook is not None:
        result = process_uploaded_workbook(raw, name)
        sheets = result.get("cleaned_sheets") or result.get("raw_sheets") or {}
        frames = {
            str(k): v.copy(deep=True)
            for k, v in sheets.items()
            if isinstance(v, pd.DataFrame) and not v.empty
        }
        if not frames:
            raise ValueError(
                f"The workbook processor returned no non-empty worksheets for {name!r}. "
                "Check the file's sheets and headers, then try importing it again."
            )
        return frames

    lower = name.lower()
    if lower.endswith(".csv"):
        return {"Data": pd.read_csv(io.BytesIO(raw))}
    if lower.endswith(".tsv") or lower.endswith(".txt"):
        return {"Data": pd.read_csv(io.BytesIO(raw), sep="\t")}
    return {str(s): pd.read_excel(io.BytesIO(raw), sheet_name=s) for s in pd.ExcelFile(io.BytesIO(raw)).sheet_names}


_DEPARTMENT_IMPORT_ALIASES = {
    "id": ("id", "dept id", "department id", "dept_id", "department_id"),
    "name": ("name", "department", "department name", "dept name"),
    "x": ("x", "x coord", "x coordinate"),
    "y": ("y", "y coord", "y coordinate"),
    "area_sqm": ("area_sqm", "area", "area m2", "area sqm", "area (m²)", "footprint"),
}
_FLOW_IMPORT_ALIASES = {
    "flow_id": ("flow_id", "flow id", "connection id"),
    "from_id": ("from_id", "from id", "from", "source", "source department"),
    "to_id": ("to_id", "to id", "to", "destination", "destination department"),
    "loads_day": ("loads_day", "loads/day", "daily loads", "loads per day"),
    "distance_m": ("distance_m", "distance", "distance m", "distance meters"),
    "relationship": ("relationship", "rel", "slp"),
    "reason": ("reason", "primary reason", "process step"),
    "transport": ("transport", "handling", "handling mode"),
}


def _import_column_map(
    frame: pd.DataFrame, aliases: dict[str, tuple[str, ...]], label: str
) -> dict[str, Any]:
    """Map supported header aliases and reject ambiguous duplicate fields."""
    alias_to_field = {
        _key(alias): field
        for field, names in aliases.items()
        for alias in names
    }
    found: dict[str, Any] = {}
    for column in frame.columns:
        field = alias_to_field.get(_key(str(column).strip()))
        if field is None:
            continue
        if field in found:
            raise ValueError(
                f"{label} contains more than one column for {field!r}; "
                "rename or remove the duplicate column before importing."
            )
        found[field] = column
    return found


def _import_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        missing = pd.isna(value)
        return bool(missing) if not hasattr(missing, "__len__") else False
    except (TypeError, ValueError):
        return False


def _import_text(value: Any, field: str, default: str | None = None) -> str:
    if _import_blank(value):
        if default is not None:
            return default
        raise ValueError(f"{field} is required.")
    text = str(value).strip()
    if not text:
        if default is not None:
            return default
        raise ValueError(f"{field} is required.")
    return text


def _import_number(
    value: Any,
    field: str,
    *,
    default: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if _import_blank(value):
        if default is None:
            raise ValueError(f"{field} is required.")
        return float(default)
    raw = str(value).strip().replace(",", "")
    try:
        number = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid number; received {value!r}.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite; received {value!r}.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field} must be at least {minimum:g}; received {number:g}.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} must be at most {maximum:g}; received {number:g}.")
    return number


def _import_data(
    frames: dict[str, pd.DataFrame], owner: str, workspace: str
) -> tuple[int, int]:
    """Validate the complete facility import before atomically writing any rows.

    Import is additive/upsert-based for backwards compatibility. Invalid rows,
    duplicate identifiers/edges, or dangling endpoints abort the entire import
    rather than leaving departments saved without their corresponding flows.
    """
    if not frames:
        return 0, 0

    department_frame: pd.DataFrame | None = None
    department_columns: dict[str, Any] = {}
    flow_frame: pd.DataFrame | None = None
    flow_columns: dict[str, Any] = {}

    for sheet_name, frame in frames.items():
        if not isinstance(frame, pd.DataFrame):
            raise ValueError(f"Import sheet {sheet_name!r} is not a tabular dataset.")
        columns = _import_column_map(
            frame, _DEPARTMENT_IMPORT_ALIASES, f"Sheet {sheet_name!r}"
        )
        if {"id", "name"} <= set(columns) and department_frame is None:
            department_frame, department_columns = frame, columns
        columns = _import_column_map(
            frame, _FLOW_IMPORT_ALIASES, f"Sheet {sheet_name!r}"
        )
        if {"from_id", "to_id"} <= set(columns) and flow_frame is None:
            flow_frame, flow_columns = frame, columns

    department_rows: list[dict[str, Any]] = []
    seen_department_ids: set[str] = set()
    seen_department_names: set[str] = set()
    if department_frame is not None:
        required_department_fields = {"id", "name", "x", "y", "area_sqm"}
        missing_fields = sorted(required_department_fields - set(department_columns))
        if missing_fields:
            raise ValueError(
                "Departments sheet is missing required column(s): "
                + ", ".join(missing_fields)
                + ". Include ID, Name, X, Y, and Area; unknown geometry must not be fabricated."
            )
        for row_number, row in enumerate(department_frame.to_dict("records"), 2):
            if all(_import_blank(value) for value in row.values()):
                continue
            department_id = _import_text(
                row.get(department_columns["id"]), f"Departments row {row_number} ID"
            )
            name = _import_text(
                row.get(department_columns["name"]),
                f"Departments row {row_number} name",
            )
            id_key, name_key = department_id.casefold(), name.casefold()
            if id_key in seen_department_ids:
                raise ValueError(f"Duplicate department ID {department_id!r} in import.")
            if name_key in seen_department_names:
                raise ValueError(f"Duplicate department name {name!r} in import.")
            seen_department_ids.add(id_key)
            seen_department_names.add(name_key)
            department_rows.append(
                {
                    "id": department_id,
                    "name": name,
                    "x": _import_number(
                        row.get(department_columns["x"]),
                        f"Departments row {row_number} X",
                        minimum=0.0,
                        maximum=100.0,
                    ),
                    "y": _import_number(
                        row.get(department_columns["y"]),
                        f"Departments row {row_number} Y",
                        minimum=0.0,
                        maximum=100.0,
                    ),
                    "area_sqm": _import_number(
                        row.get(department_columns["area_sqm"]),
                        f"Departments row {row_number} area_sqm",
                        minimum=0.01,
                    ),
                }
            )

    raw_flow_rows: list[dict[str, Any]] = []
    seen_flow_ids: set[str] = set()
    if flow_frame is not None:
        required_flow_fields = {"from_id", "to_id", "loads_day", "distance_m"}
        missing_fields = sorted(required_flow_fields - set(flow_columns))
        if missing_fields:
            raise ValueError(
                "From/To flow sheet is missing required column(s): "
                + ", ".join(missing_fields)
                + ". Include From_ID, To_ID, Loads_Day, and Distance_M; measurements must not be inferred."
            )
        for row_number, row in enumerate(flow_frame.to_dict("records"), 2):
            if all(_import_blank(value) for value in row.values()):
                continue
            flow_id = _import_text(
                row.get(flow_columns.get("flow_id")),
                f"Flows row {row_number} flow ID",
                default="",
            )
            from_id = _import_text(
                row.get(flow_columns["from_id"]), f"Flows row {row_number} From ID"
            )
            to_id = _import_text(
                row.get(flow_columns["to_id"]), f"Flows row {row_number} To ID"
            )
            if from_id == to_id:
                raise ValueError(
                    f"Flows row {row_number} must connect two different departments."
                )
            if flow_id:
                folded_id = flow_id.casefold()
                if folded_id in seen_flow_ids:
                    raise ValueError(f"Duplicate flow ID {flow_id!r} in import.")
                seen_flow_ids.add(folded_id)
            raw_relationship = row.get(flow_columns.get("relationship"))
            relationship = (
                "" if _import_blank(raw_relationship)
                else _import_text(raw_relationship, f"Flows row {row_number} relationship").upper()
            )
            if relationship and relationship not in {"A", "E", "I", "O", "U", "X"}:
                raise ValueError(
                    f"Flows row {row_number} has unsupported SLP relationship "
                    f"{relationship!r}; use A, E, I, O, U, or X, or leave it blank to mark it missing."
                )
            raw_flow_rows.append(
                {
                    "flow_id": flow_id,
                    "from_id": from_id,
                    "to_id": to_id,
                    "loads_day": _import_number(
                        row.get(flow_columns["loads_day"]),
                        f"Flows row {row_number} loads_day",
                        minimum=0.0,
                    ),
                    "distance_m": _import_number(
                        row.get(flow_columns["distance_m"]),
                        f"Flows row {row_number} distance_m",
                        minimum=0.0,
                    ),
                    "relationship": relationship,
                    "reason": _import_text(
                        row.get(flow_columns.get("reason")),
                        f"Flows row {row_number} reason",
                        default="Imported flow",
                    ),
                    "transport": _import_text(
                        row.get(flow_columns.get("transport")),
                        f"Flows row {row_number} transport",
                        default="Forklift",
                    ),
                }
            )

    if not department_rows and not raw_flow_rows:
        return 0, 0

    # Read the workspace's existing identifiers before validation. No writes
    # occur until every department and every flow has passed all checks.
    ensure_facility_schema()
    with _db() as conn:
        existing_departments = conn.execute(
            "SELECT dept_id, name, active FROM facility_departments "
            "WHERE owner=? AND workspace=?",
            (owner, workspace),
        ).fetchall()
        existing_flows = conn.execute(
            "SELECT flow_id, from_id, to_id FROM facility_flows "
            "WHERE owner=? AND workspace=?",
            (owner, workspace),
        ).fetchall()

    incoming_department_ids = {row["id"].casefold(): row["id"] for row in department_rows}
    existing_id_lookup = {str(row[0]).casefold(): str(row[0]) for row in existing_departments}
    for department_id in incoming_department_ids.values():
        existing_id = existing_id_lookup.get(department_id.casefold())
        if existing_id is not None and existing_id != department_id:
            raise ValueError(
                f"Department ID {department_id!r} differs only by letter case "
                f"from existing ID {existing_id!r}."
            )

    incoming_exact_ids = {row["id"] for row in department_rows}
    existing_names = {
        str(name).strip().casefold()
        for department_id, name, active in existing_departments
        if bool(active) and str(department_id) not in incoming_exact_ids
    }
    for row in department_rows:
        if row["name"].casefold() in existing_names:
            raise ValueError(
                f"Department name {row['name']!r} already exists in this workspace; "
                "edit the existing department or choose a unique name."
            )
        existing_names.add(row["name"].casefold())

    valid_department_ids = {
        str(department_id)
        for department_id, _name, active in existing_departments
        if bool(active)
    } | incoming_exact_ids

    existing_flow_by_id = {str(flow_id).casefold(): str(flow_id) for flow_id, _, _ in existing_flows}
    reserved_flow_ids = set(existing_flow_by_id) | seen_flow_ids
    flow_rows: list[dict[str, Any]] = []
    next_generated_id = 1
    for row in raw_flow_rows:
        flow_id = row["flow_id"]
        if flow_id:
            prior_id = existing_flow_by_id.get(flow_id.casefold())
            if prior_id is not None and prior_id != flow_id:
                raise ValueError(
                    f"Flow ID {flow_id!r} differs only by letter case from existing "
                    f"flow ID {prior_id!r}."
                )
        else:
            while True:
                candidate = f"FIMP{next_generated_id:03d}"
                next_generated_id += 1
                if candidate.casefold() not in reserved_flow_ids:
                    flow_id = candidate
                    reserved_flow_ids.add(flow_id.casefold())
                    break
        row["flow_id"] = flow_id
        if row["from_id"] not in valid_department_ids:
            raise ValueError(
                f"Flow {flow_id!r} references unknown From department {row['from_id']!r}."
            )
        if row["to_id"] not in valid_department_ids:
            raise ValueError(
                f"Flow {flow_id!r} references unknown To department {row['to_id']!r}."
            )
        flow_rows.append(row)

    # Flow IDs may update an existing edge, but two IDs cannot represent the
    # same directed edge. The reverse direction remains a distinct valid edge.
    existing_edges = {
        (str(from_id), str(to_id)): str(flow_id)
        for flow_id, from_id, to_id in existing_flows
    }
    seen_edges: set[tuple[str, str]] = set()
    for row in flow_rows:
        edge = (row["from_id"], row["to_id"])
        if edge in seen_edges:
            raise ValueError(
                f"Duplicate directed flow {edge[0]!r} → {edge[1]!r} in import."
            )
        seen_edges.add(edge)
        existing_id = existing_edges.get(edge)
        if existing_id is not None and existing_id != row["flow_id"]:
            raise ValueError(
                f"Directed flow {edge[0]!r} → {edge[1]!r} already exists as "
                f"{existing_id!r}; update that flow ID rather than duplicating the edge."
            )

    with _db() as conn:
        for row in department_rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO facility_departments
                (owner,workspace,dept_id,name,x,y,area_sqm,active,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    owner, workspace, row["id"], row["name"], row["x"],
                    row["y"], row["area_sqm"], 1, _now(),
                ),
            )
        for row in flow_rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO facility_flows
                (owner,workspace,flow_id,from_id,to_id,loads_day,distance_m,
                 relationship,reason,transport,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    owner, workspace, row["flow_id"], row["from_id"], row["to_id"],
                    row["loads_day"], row["distance_m"], row["relationship"],
                    row["reason"], row["transport"], _now(),
                ),
            )
        conn.execute(
            """
            INSERT OR REPLACE INTO facility_workspace_metadata(owner,workspace,data_origin,updated_at)
            VALUES(?,?,?,?)
            """,
            (owner, workspace, "IMPORTED_OR_UPSERTED", _now()),
        )
        conn.commit()

    return len(department_rows), len(flow_rows)


def _export_workbook(
    depts: pd.DataFrame,
    flows: pd.DataFrame,
    slp: pd.DataFrame,
    data_origin: str = "EXISTING_DATA_ORIGIN_UNVERIFIED",
    cost_per_load_meter_sar: float | None = None,
) -> bytes:
    out = io.BytesIO()
    metrics = _flow_distance_metrics(flows, cost_per_load_meter_sar)
    flow_metrics = pd.DataFrame([
        {"Metric": "Status", "Value": metrics["status"]},
        {"Metric": "Connection count", "Value": metrics["connection_count"]},
        {"Metric": "Weighted flow-distance (load·m/day)", "Value": metrics["weighted_flow_distance_load_m_per_day"]},
        {"Metric": "Handling rate (SAR/load·m)", "Value": metrics["cost_rate_sar_per_load_meter"]},
        {"Metric": "Estimated handling cost (SAR/day)", "Value": metrics["estimated_daily_handling_cost_sar"]},
        {"Metric": "Formula", "Value": metrics["formula"]},
        {"Metric": "Provenance", "Value": metrics["provenance"]},
        {"Metric": "Limitations / warnings", "Value": " ".join(metrics["warnings"])},
    ])
    provenance = pd.DataFrame([
        {"Field": "Facility data-origin status", "Value": data_origin},
        {"Field": "Export generated (UTC)", "Value": _now()},
        {"Field": "Flow-distance definition", "Value": "Σ(Loads/day × distance in metres)"},
        {"Field": "Handling-cost basis", "Value": "User-provided uniform rate per load-metre; omitted when no positive rate is configured."},
        {"Field": "Interpretation", "Value": "An imported, edited, synthetic, or unverified dataset is not automatically validated plant data."},
    ])
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        depts.to_excel(writer, index=False, sheet_name="Departments")
        flows.to_excel(writer, index=False, sheet_name="From_To_Flows")
        slp.to_excel(writer, index=False, sheet_name="SLP_Relationships")
        _matrix(depts,slp).to_excel(writer, sheet_name="SLP_Matrix")
        flow_metrics.to_excel(writer, index=False, sheet_name="Flow_Metrics")
        provenance.to_excel(writer, index=False, sheet_name="Provenance")
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

    data_origin = _get_data_origin(owner, workspace)
    if data_origin == "SYNTHETIC_STARTER_DATA":
        st.warning("SYNTHETIC starter example · The initial departments and flows are illustrative only. Replace them with verified plant measurements before making operational decisions.")
    elif data_origin == "IMPORTED_OR_UPSERTED":
        st.info("IMPORTED data · Source rows are preserved through this facility model, but import success does not independently validate plant measurements.")
    elif data_origin == "USER_EDITED_OR_MIXED":
        st.info("USER-EDITED / MIXED data · This workspace contains edited or combined values. Verify source measurements and assumptions before relying on results.")
    else:
        st.warning("DATA ORIGIN UNVERIFIED · This facility data predates origin tracking or its source is unknown. Validate it before operational use.")

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
                        _set_data_origin(owner, workspace, "USER_EDITED_OR_MIXED")
                        st.success(f"{name} ({did}) is now part of the persistent department registry. It will appear in From-To and SLP immediately.")
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
                        _set_data_origin(owner, workspace, "USER_EDITED_OR_MIXED")
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
                    _set_data_origin(owner, workspace, "USER_EDITED_OR_MIXED")
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
        flow_rate = st.number_input(
            "Uniform handling cost rate (SAR per load-metre; enter 0 until a rate is approved)",
            min_value=0.0, value=0.0, step=0.001, format="%.6f",
            key="fl_handling_cost_rate",
            help="This rate is applied uniformly to all flows. Use only a plant-approved rate; the app does not invent transport costs.",
        )
        try:
            flow_metrics = _flow_distance_metrics(
                flows, float(flow_rate) if float(flow_rate) > 0 else None
            )
        except ValueError as exc:
            st.error(f"Flow-distance calculation is unavailable until the flow data are corrected: {exc}")
        else:
            mc1, mc2 = st.columns(2)
            mc1.metric(
                "Weighted flow-distance",
                f"{flow_metrics['weighted_flow_distance_load_m_per_day']:,.2f} load·m/day",
            )
            if flow_metrics["estimated_daily_handling_cost_sar"] is None:
                mc2.metric("Estimated handling cost", "Rate not configured")
            else:
                mc2.metric(
                    "Estimated daily handling cost",
                    f"SAR {flow_metrics['estimated_daily_handling_cost_sar']:,.2f}",
                )
            st.caption(flow_metrics["formula"])
            for warning in flow_metrics["warnings"]:
                st.caption("Assumption / limitation: " + warning)
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
                if not frm or not to or frm==to:
                    st.error("Choose two different departments.")
                elif not flows.empty and ((flows["from_id"].astype(str)==frm) & (flows["to_id"].astype(str)==to)).any():
                    st.warning("That directed connection already exists. Edit the existing edge below instead of creating a duplicate.")
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
                    _set_data_origin(owner, workspace, "USER_EDITED_OR_MIXED")
                    st.success(f"Connected {frm} → {to}. The From-To and SLP surfaces are updated.")
                    st.rerun()
        with b:
            st.plotly_chart(_flow_process_figure(depts,flows),use_container_width=True,config={"displayModeBar":False})
            connected = flows[flows["from_id"].isin(ids) & flows["to_id"].isin(ids)].copy()
            if not connected.empty:
                node_ids = ids
                node_index = {node: i for i, node in enumerate(node_ids)}
                fig_sankey = go.Figure(go.Sankey(
                    arrangement="snap",
                    node=dict(label=node_ids, pad=14, thickness=18),
                    link=dict(
                        source=[node_index[str(v)] for v in connected["from_id"]],
                        target=[node_index[str(v)] for v in connected["to_id"]],
                        value=[max(0.0, float(v)) for v in connected["loads_day"]],
                    ),
                ))
                fig_sankey.update_layout(
                    height=330,
                    title="Material-flow volume by department",
                    margin=dict(l=8,r=8,t=50,b=8),
                )
                st.plotly_chart(fig_sankey,use_container_width=True,config={"displayModeBar":False})
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
                    if frm2==to2:
                        st.error("From and To departments must be different.")
                    elif not flows.empty and ((flows["from_id"].astype(str)==frm2) & (flows["to_id"].astype(str)==to2) & (flows["flow_id"].astype(str)!=fid)).any():
                        st.warning("That directed connection already exists. Edit that connection instead of creating a duplicate.")
                    else:
                        with _db() as conn:
                            conn.execute(
                                "UPDATE facility_flows SET from_id=?,to_id=?,loads_day=?,distance_m=?,relationship=?,reason=?,transport=?,updated_at=? WHERE owner=? AND workspace=? AND flow_id=?",
                                (frm2,to2,loads2,dist2,rel2,reason2,mode2,_now(),owner,workspace,fid),
                            )
                            conn.commit()
                        _set_data_origin(owner, workspace, "USER_EDITED_OR_MIXED")
                        st.success("Connection updated; all dependent views use the new edge.")
                        st.rerun()
            if st.button("🗑️ Remove connection",use_container_width=True,key="fl_delete_flow"):
                with _db() as conn:
                    conn.execute("DELETE FROM facility_flows WHERE owner=? AND workspace=? AND flow_id=?",(owner,workspace,fid))
                    conn.commit()
                _set_data_origin(owner, workspace, "USER_EDITED_OR_MIXED")
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
                heat = _slp_heatmap_values(matrix)
                st.plotly_chart(px.imshow(heat,text_auto=True,aspect="auto",title="SLP closeness heatmap · A=4 … X=-1"),use_container_width=True,config={"displayModeBar":False})

    with tabs[3]:
         st.markdown("### Process scenario laboratory")
         st.caption("Test the operational effect of changing the department network: remove a department or remove a connection, then compare the resulting route and travel burden with the baseline.")
         ids=depts["id"].astype(str).tolist()
         if len(ids)>=2 and not flows.empty:
             p1,p2,p3=st.columns(3)
             start=p1.selectbox("Process starts at",ids,key="fl_scenario_start")
             end=p2.selectbox("Process ends at",ids,index=min(1,len(ids)-1),key="fl_scenario_end")
             mode=p3.selectbox("Scenario change",["Avoid department","Remove connection"],key="fl_scenario_mode")
             if start==end:
                 st.warning("Choose different start and end departments to calculate a route change.")
             else:
                 base_path,base_dist,base_vol=_shortest_path(flows,start,end,None)
                 scenario_label="No change"
                 if mode=="Avoid department":
                     avoid=st.selectbox("Avoid / relocate department",["None"]+ids,key="fl_scenario_avoid")
                     avoid_id=None if avoid=="None" else avoid
                     alt_path,alt_dist,alt_vol=_shortest_path(flows,start,end,avoid_id)
                     scenario_label="Avoid "+(avoid_id or "none")
                 else:
                     flow_options={str(r.flow_id):f"{r.flow_id} · {r.from_id} → {r.to_id}" for r in flows.itertuples()}
                     removed_flow=st.selectbox("Remove / reroute connection",list(flow_options),format_func=flow_options.get,key="fl_scenario_flow")
                     alt_path,alt_dist,alt_vol=_shortest_path(flows,start,end,None,removed_flow)
                     scenario_label="Remove "+removed_flow

                 c1,c2,c3,c4=st.columns(4)
                 c1.metric("Baseline path", " → ".join(base_path) if base_path else "No route")
                 c2.metric("Baseline distance", f"{base_dist:.1f} m" if math.isfinite(base_dist) else "—")
                 c3.metric("Scenario path", " → ".join(alt_path) if alt_path else "No route")
                 if math.isfinite(base_dist) and math.isfinite(alt_dist):
                     delta=alt_dist-base_dist
                     pct=(delta/base_dist*100) if base_dist else 0.0
                     c4.metric("Distance change", f"{delta:+.1f} m", f"{pct:+.1f}%")
                 else:
                     c4.metric("Distance change", "No alternate route")

                 comparison=pd.DataFrame([
                     {"Scenario":"Baseline","Path":" → ".join(base_path) if base_path else "No route","Distance (m)":base_dist if math.isfinite(base_dist) else None,"Daily Loads on Path":base_vol if base_path else None},
                     {"Scenario":scenario_label,"Path":" → ".join(alt_path) if alt_path else "No route","Distance (m)":alt_dist if math.isfinite(alt_dist) else None,"Daily Loads on Path":alt_vol if alt_path else None},
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
        export_rate = st.session_state.get("fl_handling_cost_rate", 0.0)
        export=_export_workbook(
            depts, flows, slp, data_origin,
            float(export_rate) if float(export_rate) > 0 else None,
        )
        st.download_button("📥 Download Facility Model Workbook",data=export,file_name="shoir_ie_facility_layout.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",type="primary",use_container_width=True,key="fl_export_workbook")
        st.download_button("📄 Download From-To CSV",data=flows.to_csv(index=False).encode("utf-8"),file_name="facility_from_to.csv",mime="text/csv",use_container_width=True,key="fl_export_fromto")
        st.caption("The workbook contains Departments, From_To_Flows, SLP_Relationships, SLP_Matrix, Flow_Metrics and Provenance sheets.")

    # Keep the legacy state contract synchronized for older modules that read it.
    st.session_state["facility_depts"]=depts.to_dict("records")
    st.session_state["facility_flows_df"]=flows.copy(deep=True)
    st.session_state["facility_layout_live"]=depts.copy(deep=True)
