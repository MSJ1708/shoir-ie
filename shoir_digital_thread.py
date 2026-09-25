"""Global Project + Digital Thread for Shoir-IE.

Creates a persistent, workspace-scoped traceability graph:
Dataset -> Asset -> Process -> KPI -> Model -> Experiment -> Decision -> Outcome

The canonical graph is stored in Streamlit session state, which is already
captured by the Shoir-IE workspace autosave/durable persistence path.
No synthetic measurements are created; unresolved links are explicitly marked
as pending or inferred from available workspace metadata.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


THREAD_TYPES = [
    "Dataset",
    "Asset",
    "Process",
    "KPI",
    "Model",
    "Experiment",
    "Decision",
    "Outcome",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "item"


def stable_id(node_type: str, name: str, source: str = "") -> str:
    raw = f"{node_type}|{name}|{source}"
    return f"{node_type[:3].upper()}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12].upper()}"


def _keys() -> dict[str, str]:
    return {
        "project": "global_thread_project",
        "nodes": "global_thread_nodes",
        "edges": "global_thread_edges",
        "sync": "global_thread_last_sync",
        "version": "global_thread_version",
    }


def ensure_thread_state(owner: str) -> dict[str, Any]:
    keys = _keys()
    if keys["project"] not in st.session_state or not isinstance(st.session_state.get(keys["project"]), dict):
        st.session_state[keys["project"]] = {
            "project_id": "PRJ-" + hashlib.sha1(f"{owner}|global".encode("utf-8")).hexdigest()[:12].upper(),
            "name": "Shoir-IE Global Engineering Project",
            "description": "Cross-module engineering workspace with end-to-end traceability.",
            "status": "Active",
            "owner": owner,
            "created_at": _now(),
            "updated_at": _now(),
        }
    if not isinstance(st.session_state.get(keys["nodes"]), list):
        st.session_state[keys["nodes"]] = []
    if not isinstance(st.session_state.get(keys["edges"]), list):
        st.session_state[keys["edges"]] = []
    st.session_state.setdefault(keys["sync"], "")
    st.session_state.setdefault(keys["version"], 1)
    return keys


def _upsert_node(node_type: str, name: str, source: str = "", module: str = "", status: str = "Observed", metadata: dict[str, Any] | None = None) -> str:
    keys = _keys()
    node_id = stable_id(node_type, name, source)
    nodes = st.session_state[keys["nodes"]]
    payload = {
        "node_id": node_id,
        "node_type": node_type,
        "name": str(name)[:180],
        "source": str(source)[:240],
        "module": str(module)[:180],
        "status": str(status)[:80],
        "metadata": metadata or {},
        "updated_at": _now(),
    }
    for idx, existing in enumerate(nodes):
        if existing.get("node_id") == node_id:
            nodes[idx] = payload
            return node_id
    nodes.append(payload)
    return node_id


def _upsert_edge(source_id: str, target_id: str, relation: str, status: str = "Linked", metadata: dict[str, Any] | None = None) -> str:
    keys = _keys()
    raw = f"{source_id}|{target_id}|{relation}"
    edge_id = f"EDG-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12].upper()}"
    edges = st.session_state[keys["edges"]]
    payload = {
        "edge_id": edge_id,
        "source_id": source_id,
        "target_id": target_id,
        "relation": str(relation)[:160],
        "status": str(status)[:80],
        "metadata": metadata or {},
        "updated_at": _now(),
    }
    for idx, existing in enumerate(edges):
        if existing.get("edge_id") == edge_id:
            edges[idx] = payload
            return edge_id
    edges.append(payload)
    return edge_id


def _safe_workspace_frames() -> Iterable[tuple[str, pd.DataFrame]]:
    try:
        from shoir_live_visuals import _MODULE_KEYS
    except Exception:
        _MODULE_KEYS = {}

    seen: set[str] = set()
    for module, state_keys in _MODULE_KEYS.items():
        for state_key in state_keys:
            value = st.session_state.get(state_key)
            if isinstance(value, pd.DataFrame) and not value.empty and state_key not in seen:
                seen.add(state_key)
                yield module, value.copy(deep=True)


def _discover_experience_records(owner: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    studies: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    try:
        with sqlite3.connect("enterprise_full_workspace.db", timeout=10) as conn:
            rows = conn.execute(
                "SELECT study_id,research_id,title,methodology,module,updated_at FROM experience_research_studies WHERE owner=? ORDER BY updated_at DESC LIMIT 100",
                (owner,),
            ).fetchall()
            for row in rows:
                studies.append({
                    "study_id": row[0],
                    "research_id": row[1],
                    "title": row[2],
                    "methodology": row[3],
                    "module": row[4],
                    "updated_at": row[5],
                })
            rows = conn.execute(
                "SELECT decision_id,title,module,status,created_at,updated_at FROM experience_decisions WHERE owner=? ORDER BY updated_at DESC LIMIT 100",
                (owner,),
            ).fetchall()
            for row in rows:
                decisions.append({
                    "decision_id": row[0],
                    "title": row[1],
                    "module": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "updated_at": row[5],
                })
    except Exception:
        pass
    return studies, decisions


def sync_workspace_to_thread(owner: str, active_module: str | None = None) -> dict[str, int]:
    """Harvest safe workspace evidence into a canonical traceability graph."""
    ensure_thread_state(owner)
    dataset_ids: list[str] = []
    process_by_module: dict[str, str] = {}
    kpi_count = 0
    model_count = 0

    for module, df in _safe_workspace_frames():
        if active_module and module != active_module:
            # Keep previously synchronized modules; only harvest this active
            # module during scoped refreshes.
            continue

        source_key = f"{module}|workspace"
        dataset_id = _upsert_node(
            "Dataset",
            f"{module} dataset",
            source_key,
            module,
            metadata={"rows": int(len(df)), "columns": int(len(df.columns)), "column_names": [str(c) for c in df.columns[:80]]},
        )
        dataset_ids.append(dataset_id)

        process_id = process_by_module.get(module) or _upsert_node("Process", module, f"module:{module}", module)
        process_by_module[module] = process_id
        _upsert_edge(dataset_id, process_id, "feeds process")

        lowered = {str(c).lower(): c for c in df.columns}
        asset_cols = [c for c in df.columns if any(k in str(c).lower() for k in ("asset", "machine", "facility", "workcenter", "equipment", "node"))]
        for col in asset_cols[:3]:
            vals = df[col].dropna().astype(str).drop_duplicates().head(40)
            for value in vals:
                asset_id = _upsert_node("Asset", value, f"{module}|{col}|{value}", module, metadata={"field": str(col)})
                _upsert_edge(dataset_id, asset_id, f"identifies {col}")
                _upsert_edge(asset_id, process_id, "participates in")

        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        for col in numeric_cols[:12]:
            kpi_id = _upsert_node(
                "KPI",
                str(col),
                f"{module}|kpi|{col}",
                module,
                metadata={"dtype": str(df[col].dtype)},
            )
            _upsert_edge(process_id, kpi_id, "produces KPI")
            _upsert_edge(dataset_id, kpi_id, "measures")
            kpi_count += 1

        result_keys = [
            key for key in st.session_state.keys()
            if not str(key).startswith(("_", "password", "token", "secret", "otp"))
            and any(term in str(key).lower() for term in ("result", "forecast", "optimization", "model", "schedule", "prediction"))
        ]
        module_result_keys = [k for k in result_keys if module.lower().split()[0] in str(k).lower()]
        if module_result_keys or numeric_cols:
            source = module_result_keys[0] if module_result_keys else f"module:{module}"
            model_status = "Observed" if module_result_keys else "Inferred"
            model_id = _upsert_node("Model", f"{module} analytical model", source, module, status=model_status)
            model_count += 1
            for col in numeric_cols[:4]:
                _upsert_edge(_stable_kpi_for(module, col), model_id, "supports model")

    studies, decisions = _discover_experience_records(owner)

    experiment_ids: list[str] = []
    for study in studies:
        experiment_id = _upsert_node(
            "Experiment",
            study["title"],
            study["study_id"],
            study.get("module", "") or "Experiment Lab",
            status="Observed",
            metadata={"research_id": study["research_id"], "methodology": study["methodology"]},
        )
        experiment_ids.append(experiment_id)

    decision_ids: list[str] = []
    for decision in decisions:
        decision_id = _upsert_node(
            "Decision",
            decision["title"],
            decision["decision_id"],
            decision.get("module", ""),
            status=decision["status"],
            metadata={"decision_id": decision["decision_id"]},
        )
        decision_ids.append(decision_id)

        # Explicitly represent outcome state. "Pending" is not an invented
        # result; it makes the missing verification step visible.
        outcome_id = _upsert_node(
            "Outcome",
            f"Outcome verification · {decision['title']}",
            f"{decision['decision_id']}|outcome",
            decision.get("module", ""),
            status="Pending verification",
            metadata={"decision_id": decision["decision_id"]},
        )
        _upsert_edge(decision_id, outcome_id, "has outcome")

    # Link the canonical spine using observed nodes and module affinity.
    nodes = st.session_state[_keys()["nodes"]]
    for module in process_by_module:
        process_id = process_by_module[module]
        module_kpis = [n for n in nodes if n["node_type"] == "KPI" and n["module"] == module]
        module_models = [n for n in nodes if n["node_type"] == "Model" and n["module"] == module]
        module_experiments = [n for n in nodes if n["node_type"] == "Experiment" and (not n["module"] or n["module"] == module)]
        module_decisions = [n for n in nodes if n["node_type"] == "Decision" and (not n["module"] or n["module"] == module)]

        for kpi in module_kpis[:6]:
            for model in module_models[:2]:
                _upsert_edge(kpi["node_id"], model["node_id"], "feeds model")
        for model in module_models[:2]:
            for experiment in module_experiments[:3]:
                _upsert_edge(model["node_id"], experiment["node_id"], "tested by experiment")
            for decision in module_decisions[:3]:
                _upsert_edge(model["node_id"], decision["node_id"], "supports decision")
        for experiment in module_experiments[:3]:
            for decision in module_decisions[:3]:
                _upsert_edge(experiment["node_id"], decision["node_id"], "informs decision")

    st.session_state[_keys()["sync"]] = _now()
    st.session_state[_keys()["version"]] = int(st.session_state.get(_keys()["version"], 1)) + 1
    st.session_state[_keys()["project"]]["updated_at"] = _now()
    return {
        "datasets": len({n["node_id"] for n in nodes if n["node_type"] == "Dataset"}),
        "assets": len({n["node_id"] for n in nodes if n["node_type"] == "Asset"}),
        "processes": len({n["node_id"] for n in nodes if n["node_type"] == "Process"}),
        "kpis": kpi_count,
        "models": model_count,
        "experiments": len(experiment_ids),
        "decisions": len(decision_ids),
        "outcomes": len({n["node_id"] for n in nodes if n["node_type"] == "Outcome"}),
        "edges": len(st.session_state[_keys()["edges"]]),
    }


def _stable_kpi_for(module: str, col: str) -> str:
    return stable_id("KPI", str(col), f"{module}|kpi|{col}")


def node_frame() -> pd.DataFrame:
    ensure_thread_state("")
    rows = st.session_state[_keys()["nodes"]]
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["node_id", "node_type", "name", "source", "module", "status", "updated_at"])
    out["metadata"] = out["metadata"].map(lambda value: json.dumps(value, default=str, ensure_ascii=False))
    return out


def edge_frame() -> pd.DataFrame:
    ensure_thread_state("")
    rows = st.session_state[_keys()["edges"]]
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["edge_id", "source_id", "target_id", "relation", "status", "updated_at"])
    out["metadata"] = out["metadata"].map(lambda value: json.dumps(value, default=str, ensure_ascii=False))
    return out


def _layered_positions(nodes: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    buckets = {kind: [n for n in nodes if n["node_type"] == kind] for kind in THREAD_TYPES}
    for layer_index, kind in enumerate(THREAD_TYPES):
        items = buckets[kind]
        for idx, node in enumerate(items):
            x = float(layer_index)
            if len(items) == 1:
                y = 0.0
            else:
                y = (idx - (len(items) - 1) / 2) / max(1.0, len(items) - 1) * 10.0
            positions[node["node_id"]] = (x, y)
    return positions


def network_figure(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], title: str = "Global Digital Thread") -> go.Figure | None:
    if not nodes:
        return None
    positions = _layered_positions(nodes)
    fig = go.Figure()

    for edge in edges:
        if edge["source_id"] not in positions or edge["target_id"] not in positions:
            continue
        x0, y0 = positions[edge["source_id"]]
        x1, y1 = positions[edge["target_id"]]
        fig.add_trace(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode="lines",
            line=dict(width=1.5),
            hoverinfo="none",
            showlegend=False,
        ))

    for kind in THREAD_TYPES:
        subset = [n for n in nodes if n["node_type"] == kind]
        if not subset:
            continue
        xs, ys, labels, hover = [], [], [], []
        for node in subset:
            x, y = positions[node["node_id"]]
            xs.append(x)
            ys.append(y)
            labels.append(node["name"][:28])
            hover.append(f"{kind} · {node['name']}<br>Status: {node.get('status','')}")
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=labels,
            textposition="middle right",
            hovertext=hover,
            hoverinfo="text",
            marker=dict(size=18),
            name=kind,
        ))

    fig.update_layout(
        title=title,
        height=650,
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(len(THREAD_TYPES))),
            ticktext=THREAD_TYPES,
            showgrid=False,
            zeroline=False,
            showline=False,
        ),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=20, r=20, t=55, b=20),
        template="plotly_white",
        legend_title_text="Thread layer",
    )
    return fig


def sankey_figure(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> go.Figure | None:
    if not edges:
        return None
    index = {n["node_id"]: i for i, n in enumerate(nodes)}
    labels = [f"{n['node_type']} · {n['name'][:34]}" for n in nodes]
    sources, targets, values = [], [], []
    for edge in edges:
        if edge["source_id"] in index and edge["target_id"] in index:
            sources.append(index[edge["source_id"]])
            targets.append(index[edge["target_id"]])
            values.append(1)
    if not sources:
        return None
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=labels, pad=16, thickness=14),
        link=dict(source=sources, target=targets, value=values),
    ))
    fig.update_layout(title="Traceability Flow · Dataset to Outcome", height=560, margin=dict(l=10, r=10, t=55, b=10))
    return fig


def trace_from(node_id: str) -> list[dict[str, Any]]:
    nodes = {n["node_id"]: n for n in st.session_state.get(_keys()["nodes"], [])}
    edges = st.session_state.get(_keys()["edges"], [])
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge["source_id"], []).append(edge["target_id"])
    path = []
    seen: set[str] = set()

    def walk(current: str) -> None:
        if current in seen or current not in nodes:
            return
        seen.add(current)
        path.append(nodes[current])
        for target in adjacency.get(current, [])[:12]:
            walk(target)

    walk(node_id)
    return path


def _export_bundle(project: dict[str, Any], nodes: pd.DataFrame, edges: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    manifest = {
        "project": project,
        "contract": ["Dataset", "Asset", "Process", "KPI", "Model", "Experiment", "Decision", "Outcome"],
        "generated_at": _now(),
        "node_count": int(len(nodes)),
        "edge_count": int(len(edges)),
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(project, indent=2, default=str).encode("utf-8"))
        zf.writestr("digital_thread_nodes.csv", nodes.to_csv(index=False).encode("utf-8"))
        zf.writestr("digital_thread_edges.csv", edges.to_csv(index=False).encode("utf-8"))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
    return buf.getvalue()


def render_global_project_digital_thread(module: str, username: str) -> None:
    keys = ensure_thread_state(username)
    project = st.session_state[keys["project"]]

    st.markdown("## 🌐 Global Project & Digital Thread")
    st.caption("One engineering project connects evidence across Shoir-IE instead of leaving datasets, analyses, decisions and outcomes in isolated modules.")

    p1, p2 = st.columns([1.5, 1])
    with p1:
        project["name"] = st.text_input("Project name", value=project.get("name", ""), key="global_thread_project_name")
        project["description"] = st.text_area("Project description", value=project.get("description", ""), height=75, key="global_thread_project_description")
    with p2:
        project["status"] = st.selectbox("Project status", ["Active", "On Hold", "Completed", "Archived"], index=["Active", "On Hold", "Completed", "Archived"].index(project.get("status", "Active")), key="global_thread_project_status")
        st.metric("Project ID", project.get("project_id", "—"))
    project["updated_at"] = _now()

    # First-open experience: automatically harvest the current workspace once
    # so the user lands on an evidence-backed graph rather than an empty canvas.
    if not st.session_state.get(keys["sync"]):
        try:
            sync_workspace_to_thread(username, active_module=None)
        except Exception:
            pass

    c1, c2, c3, c4 = st.columns(4)
    nodes = node_frame()
    raw_nodes = st.session_state[keys["nodes"]]
    raw_edges = st.session_state[keys["edges"]]
    counts = {kind: sum(1 for n in raw_nodes if n["node_type"] == kind) for kind in THREAD_TYPES}
    c1.metric("Thread nodes", f"{len(raw_nodes):,}")
    c2.metric("Traceability links", f"{len(raw_edges):,}")
    c3.metric("Experiments + Decisions", f'{counts["Experiment"] + counts["Decision"]:,}')
    c4.metric("Last sync", st.session_state.get(keys["sync"]) or "Never")

    if st.button("🔄 Sync Entire Workspace into Digital Thread", type="primary", use_container_width=True, key="global_thread_sync"):
        with st.spinner("Harvesting datasets, assets, KPIs, models, experiments and decisions..."):
            stats = sync_workspace_to_thread(username)
        st.success("Digital Thread synchronized: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
        st.rerun()

    tabs = st.tabs(["🧭 Overview", "🕸️ Thread Map", "🧬 Trace an Item", "🔗 Manage Links", "📦 Evidence"])

    with tabs[0]:
        st.markdown("### Canonical lifecycle")
        step_cols = st.columns(len(THREAD_TYPES))
        for idx, kind in enumerate(THREAD_TYPES):
            step_cols[idx].markdown(f"<div class='sx-step'>{idx+1}. {kind}<br><small>{counts[kind]:,}</small></div>", unsafe_allow_html=True)

        missing_layers = [kind for kind in THREAD_TYPES if counts[kind] == 0]
        if missing_layers:
            st.info("Layers not populated yet: " + ", ".join(missing_layers) + ". Run a workspace sync or create the missing record explicitly.")
        else:
            st.success("✅ All eight traceability layers are represented in this project.")

        if raw_nodes:
            st.dataframe(nodes.head(300), use_container_width=True, hide_index=True)

    with tabs[1]:
        node_type_filter = st.multiselect("Thread layers", THREAD_TYPES, default=THREAD_TYPES, key="global_thread_layers")
        selected_ids = {n["node_id"] for n in raw_nodes if n["node_type"] in node_type_filter}
        filtered_nodes = [n for n in raw_nodes if n["node_id"] in selected_ids]
        filtered_edges = [e for e in raw_edges if e["source_id"] in selected_ids and e["target_id"] in selected_ids]
        fig = network_figure(filtered_nodes, filtered_edges)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No traceability graph yet. Sync the workspace to create the graph.")
        sankey = sankey_figure(filtered_nodes, filtered_edges)
        if sankey is not None:
            st.plotly_chart(sankey, use_container_width=True)

    with tabs[2]:
        if not raw_nodes:
            st.info("Sync the workspace first.")
        else:
            labels = {n["node_id"]: f"{n['node_type']} · {n['name']}" for n in raw_nodes}
            selected_id = st.selectbox("Select any Dataset / Asset / KPI / Model / Experiment / Decision / Outcome", list(labels.keys()), format_func=labels.get, key="global_thread_trace_node")
            traced = trace_from(selected_id)
            st.metric("Reachable trace items", len(traced))
            if traced:
                st.dataframe(pd.DataFrame(traced), use_container_width=True, hide_index=True)

    with tabs[3]:
        st.markdown("### Add explicit traceability link")
        if raw_nodes:
            labels = {n["node_id"]: f"{n['node_type']} · {n['name']}" for n in raw_nodes}
            left, right = st.columns(2)
            with left:
                source_id = st.selectbox("Source node", list(labels.keys()), format_func=labels.get, key="global_thread_source")
            with right:
                target_id = st.selectbox("Target node", list(labels.keys()), format_func=labels.get, key="global_thread_target")
            relation = st.text_input("Relationship", value="depends on", key="global_thread_relation")
            if st.button("🔗 Create traceability link", use_container_width=True, key="global_thread_link"):
                if source_id == target_id:
                    st.warning("A node cannot link to itself.")
                else:
                    _upsert_edge(source_id, target_id, relation)
                    st.session_state[keys["project"]]["updated_at"] = _now()
                    st.success("Traceability link created.")
        else:
            st.info("Sync the workspace first to populate nodes.")
        st.markdown("### Create a node manually")
        n1, n2, n3 = st.columns(3)
        with n1:
            node_type = st.selectbox("Type", THREAD_TYPES, key="global_thread_new_type")
        with n2:
            node_name = st.text_input("Name", key="global_thread_new_name")
        with n3:
            node_status = st.selectbox("Status", ["Observed", "Inferred", "Pending verification"], key="global_thread_new_status")
        if st.button("＋ Add node", use_container_width=True, key="global_thread_add_node"):
            if node_name.strip():
                _upsert_node(node_type, node_name.strip(), f"manual:{username}", module, node_status)
                st.success("Node added to the project thread.")
            else:
                st.warning("Enter a node name first.")

    with tabs[4]:
        try:
            from shoir_upgrade import build_excel_report
            excel = build_excel_report(
                "Shoir-IE | Global Digital Thread",
                [("Nodes", nodes), ("Edges", edge_frame())],
            )
            st.download_button(
                "📊 Download Digital Thread Excel",
                excel,
                f"shoir_ie_{_slug(project.get('name','global_thread'))}_digital_thread.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as exc:
            st.warning(f"Excel export unavailable: {exc}")

        bundle = _export_bundle(project, nodes, edge_frame())
        st.download_button(
            "📦 Download complete thread evidence bundle",
            bundle,
            f"shoir_ie_{_slug(project.get('name','global_thread'))}_digital_thread.zip",
            "application/zip",
            use_container_width=True,
        )

        st.markdown("### Traceability coverage")
        coverage = pd.DataFrame([{"Layer": kind, "Nodes": counts[kind], "Present": counts[kind] > 0} for kind in THREAD_TYPES])
        st.dataframe(coverage, use_container_width=True, hide_index=True)

    st.caption("Persistence: project metadata and Digital Thread nodes/links live in the user workspace state and are captured by the existing autosave/durable persistence path.")
