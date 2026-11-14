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
import uuid
from shoir_sqlite import ClosingSQLiteConnection
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# Canonical entity vocabulary for the Industrial Decision Operating System.
# Domain modules own their calculations; this module owns cross-domain identity
# and relationships. Every other integration layer should reference this list
# instead of defining a competing entity taxonomy.
THREAD_TYPES = [
    "Dataset",
    "Asset",
    "Process",
    "Product",
    "Material",
    "Order",
    "Workforce",
    "Quality",
    "Maintenance",
    "Energy",
    "Cost",
    "Scenario",
    "KPI",
    "Model",
    "Experiment",
    "Decision",
    "Outcome",
]

CANONICAL_LIFECYCLE = [
    "Asset", "Process", "Product", "Material", "Order", "Workforce",
    "Quality", "Maintenance", "Energy", "Cost", "Scenario", "Decision", "Outcome",
]

CANONICAL_FIELD_ALIASES = {
    "Asset": ("asset", "asset_id", "machine", "equipment", "facility", "workcenter", "work_center", "node"),
    "Process": ("process", "operation", "activity", "route", "workcenter", "work_center"),
    "Product": ("product", "product_id", "sku", "part", "part_number", "item"),
    "Material": ("material", "material_id", "component", "raw_material", "bom"),
    "Order": ("order", "order_id", "work_order", "workorder", "sales_order", "purchase_order"),
    "Workforce": ("operator", "employee", "employee_id", "worker", "technician", "staff", "workforce"),
    "Quality": ("quality", "defect", "failure", "scrap", "yield", "inspection", "nonconformance"),
    "Maintenance": ("maintenance", "failure", "downtime", "mtbf", "mttr", "rul", "reliability"),
    "Energy": ("energy", "kwh", "electricity", "power", "water"),
    "Cost": ("cost", "price", "opex", "capex", "expense", "revenue"),
    "Scenario": ("scenario", "case", "variant", "alternative"),
    "Decision": ("decision", "recommendation", "action"),
    "Outcome": ("outcome", "actual", "result", "verification", "impact"),
}



def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "item"


def stable_id(
    node_type: str,
    name: str,
    source: str = "",
    identity_key: str = "",
) -> str:
    """Return a stable graph ID; prefer immutable external identity over labels."""
    immutable_key = str(identity_key or "").strip()
    raw = (
        f"{node_type}|identity|{immutable_key}"
        if immutable_key
        else f"{node_type}|{name}|{source}"
    )
    return f"{node_type[:3].upper()}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12].upper()}"


def _stable_identity_column(frame: pd.DataFrame, node_type: str) -> str:
    """Find an explicit business-key column, without inferring from personal names."""
    candidates = {
        "Asset": ("asset_id", "equipment_id", "machine_id", "asset_tag", "equipment_tag", "tag_number", "tag_id"),
        "Product": ("product_id", "sku", "part_number", "product_code"),
        "Material": ("material_id", "material_code", "component_id", "item_code"),
        "Order": ("order_id", "work_order_id", "purchase_order_id", "sales_order_id"),
        "Quality": ("nonconformance_id", "nc_id", "inspection_id", "quality_record_id"),
        "Maintenance": ("maintenance_order_id", "notification_id", "failure_id"),
        "Energy": ("meter_id", "energy_meter_id", "measurement_point_id"),
        "Cost": ("cost_center_id", "cost_object_id"),
        "Scenario": ("scenario_id",),
        "Decision": ("decision_id",),
        "Outcome": ("outcome_id",),
        "Model": ("model_id",),
        "Experiment": ("study_id", "experiment_id"),
    }
    allowed = set(candidates.get(node_type, ()))
    for column in frame.columns:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_")
        if normalized in allowed:
            return str(column)
    return ""


WORKFORCE_AGGREGATE_FIELDS = {
    "operator_count", "operators_count", "staff_count", "headcount",
    "workforce_count", "crew_size", "fte", "technician_count",
}


def _workforce_aggregate_columns(frame: pd.DataFrame) -> list[str]:
    """Select aggregate count measures only; never employee names or personal IDs."""
    selected = []
    for column in frame.columns:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_")
        if normalized in WORKFORCE_AGGREGATE_FIELDS:
            selected.append(str(column))
    return selected


def _display_column(frame: pd.DataFrame, node_type: str, identity_column: str) -> str:
    tokens = {
        "Asset": ("asset_name", "equipment_name", "machine_name", "asset_label", "equipment_label", "name", "description"),
        "Product": ("product_name", "description", "name", "label"),
        "Material": ("material_name", "description", "name", "label"),
        "Order": ("order_name", "description", "name", "label"),
        "Quality": ("description", "defect_name", "name", "label"),
        "Maintenance": ("description", "maintenance_type", "name", "label"),
        "Energy": ("meter_name", "measurement_point_name", "name", "label"),
        "Cost": ("cost_center_name", "cost_object_name", "name", "label"),
    }.get(node_type, ("name", "description", "label"))
    for column in frame.columns:
        if str(column) == identity_column:
            continue
        normalized = re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_")
        if normalized in tokens:
            return str(column)
    return identity_column


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


def renamed_node_record(node: dict[str, Any], new_name: str) -> dict[str, Any]:
    """Return a renamed display record without changing the node's canonical ID."""
    clean_name = str(new_name or "").strip()
    if not clean_name:
        raise ValueError("Enter a non-empty display name.")
    clean_name = clean_name[:180]
    node_id = str(node.get("node_id") or "").strip()
    node_type = str(node.get("node_type") or "").strip()
    if not node_id or not node_type:
        raise ValueError("This Digital Thread node has no stable identity and cannot be renamed safely.")

    updated = dict(node)
    old_name = str(updated.get("name") or "").strip()
    if old_name == clean_name:
        return updated
    if not str(updated.get("source") or "").strip():
        updated["source"] = f"thread-node:{node_id}"

    raw_metadata = updated.get("metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    raw_aliases = metadata.get("name_aliases", [])
    aliases = list(raw_aliases) if isinstance(raw_aliases, (list, tuple)) else []
    if old_name and old_name not in aliases:
        aliases.append(old_name)
    metadata["name_aliases"] = list(dict.fromkeys(
        str(value).strip()[:180]
        for value in aliases
        if str(value or "").strip()
    ))[-30:]
    metadata["display_name_override"] = True
    metadata["display_name_updated_at"] = _now()
    updated["metadata"] = metadata
    updated["name"] = clean_name
    updated["updated_at"] = _now()
    return updated


def rename_thread_node(node_id: str, new_name: str) -> dict[str, Any]:
    """Rename one node while retaining its ID and every connected edge."""
    keys = _keys()
    nodes = st.session_state[keys["nodes"]]
    target_index = next(
        (idx for idx, node in enumerate(nodes) if str(node.get("node_id") or "") == str(node_id)),
        None,
    )
    if target_index is None:
        raise ValueError("The selected Digital Thread node no longer exists.")

    updated = renamed_node_record(nodes[target_index], new_name)
    for idx, other in enumerate(nodes):
        if idx == target_index:
            continue
        if (
            str(other.get("node_type") or "") == str(updated.get("node_type") or "")
            and str(other.get("source") or "").strip() == str(updated.get("source") or "").strip()
            and str(other.get("name") or "").strip().casefold() == str(updated.get("name") or "").strip().casefold()
        ):
            raise ValueError("A node with this source and display name already exists.")

    nodes[target_index] = updated
    st.session_state[keys["version"]] = int(st.session_state.get(keys["version"], 1)) + 1
    if isinstance(st.session_state.get(keys["project"]), dict):
        st.session_state[keys["project"]]["updated_at"] = _now()
    return updated


def persist_digital_thread_workspace(username: str) -> bool:
    """Persist the graph through the authenticated managed workspace backend only."""
    actor = str(st.session_state.get("current_user") or "").strip()
    requested = str(username or "").strip()
    if st.session_state.get("authenticated") is not True:
        raise PermissionError("Sign in with an active Shoir-IE account before saving Digital Thread changes.")
    if not actor or actor.casefold() in {"guest", "guest visitor", "anonymous"}:
        raise PermissionError("Guest and anonymous sessions cannot save Digital Thread changes.")
    if not requested or actor.casefold() != requested.casefold():
        raise PermissionError("The requested identity does not match the signed-in account.")

    from durable_account_store import durable_backend_configured
    from workspace_persistence import save_user_workspace

    if not durable_backend_configured():
        raise RuntimeError("Managed workspace persistence is not configured; no Digital Thread change was saved.")
    if not save_user_workspace(actor, st.session_state):
        raise RuntimeError("The managed workspace save failed; the Digital Thread change was not confirmed.")
    return True


def _upsert_node(
    node_type: str,
    name: str,
    source: str = "",
    module: str = "",
    status: str = "Observed",
    metadata: dict[str, Any] | None = None,
    identity_key: str = "",
) -> str:
    keys = _keys()
    node_id = stable_id(node_type, name, source, identity_key=identity_key)
    nodes = st.session_state[keys["nodes"]]
    next_metadata = dict(metadata or {})

    # Prefer the immutable ID. For pre-existing nodes without an explicit
    # business key, a unique source key preserves the issued ID across a rename.
    existing_index = next(
        (idx for idx, existing in enumerate(nodes) if existing.get("node_id") == node_id),
        None,
    )
    if existing_index is None and not str(identity_key or "").strip() and str(source or "").strip():
        source_matches = [
            idx for idx, existing in enumerate(nodes)
            if existing.get("node_type") == node_type
            and str(existing.get("source") or "").strip() == str(source).strip()
        ]
        if len(source_matches) > 1:
            raise ValueError(
                "This Digital Thread source key maps to multiple existing nodes. "
                "Resolve the duplicate identity records before synchronizing."
            )
        if len(source_matches) == 1:
            existing_index = source_matches[0]

    if existing_index is not None:
        existing = nodes[existing_index]
        existing_id = str(existing.get("node_id") or node_id)
        old_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
        next_metadata = {**old_metadata, **next_metadata}
        aliases = list(old_metadata.get("name_aliases", [])) if isinstance(old_metadata.get("name_aliases"), (list, tuple)) else []
        incoming_aliases = next_metadata.get("name_aliases", [])
        if isinstance(incoming_aliases, (list, tuple)):
            aliases.extend(incoming_aliases)
        old_name = str(existing.get("name") or "").strip()
        new_name = str(name or "").strip()
        display_override = old_metadata.get("display_name_override") is True
        if old_name and old_name != new_name:
            aliases.append(old_name)
        aliases = list(dict.fromkeys(
            str(value).strip()[:180]
            for value in aliases
            if str(value or "").strip()
        ))
        if aliases:
            next_metadata["name_aliases"] = aliases[-30:]
        if display_override:
            next_metadata["display_name_override"] = True
            if old_metadata.get("display_name_updated_at"):
                next_metadata["display_name_updated_at"] = old_metadata["display_name_updated_at"]
        payload = {
            "node_id": existing_id,
            "node_type": node_type,
            "name": (old_name if display_override else new_name)[:180],
            "source": str(source)[:240],
            "module": str(module)[:180],
            "status": str(status)[:80],
            "metadata": next_metadata,
            "updated_at": _now(),
        }
        nodes[existing_index] = payload
        return existing_id

    if identity_key:
        next_metadata.setdefault("identity_basis", "immutable_external_key")
    payload = {
        "node_id": node_id,
        "node_type": node_type,
        "name": str(name)[:180],
        "source": str(source)[:240],
        "module": str(module)[:180],
        "status": str(status)[:80],
        "metadata": next_metadata,
        "updated_at": _now(),
    }
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
        with sqlite3.connect("enterprise_full_workspace.db", timeout=10, factory=ClosingSQLiteConnection) as conn:
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
            # Include governed platform Decision Center records when present.
            try:
                platform_rows = conn.execute(
                    "SELECT decision_id,title,module,status,created_at,created_at FROM platform_decisions WHERE created_by=? ORDER BY created_at DESC LIMIT 100",
                    (owner,),
                ).fetchall()
                for row in platform_rows:
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

            # Include Experiment Engine runs from the platform experiment ledger.
            try:
                experiment_rows = conn.execute(
                    "SELECT experiment_id,name,module,created_by,created_at FROM platform_experiments WHERE created_by=? ORDER BY created_at DESC LIMIT 100",
                    (owner,),
                ).fetchall()
                for row in experiment_rows:
                    studies.append({
                        "study_id": row[0],
                        "research_id": row[0],
                        "title": row[1],
                        "methodology": "Platform experiment run",
                        "module": row[2],
                        "updated_at": row[4],
                    })
            except Exception:
                pass

            # De-duplicate records across the legacy and platform stores.
            studies = list({str(x["study_id"]): x for x in studies}.values())
            decisions = list({str(x["decision_id"]): x for x in decisions}.values())

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
            identity_key=f"dataset:{module}",
        )
        dataset_ids.append(dataset_id)

        process_id = process_by_module.get(module) or _upsert_node(
            "Process", module, f"module:{module}", module,
            identity_key=f"process:{module}",
        )
        process_by_module[module] = process_id
        _upsert_edge(dataset_id, process_id, "feeds process")

        canonical_by_type: dict[str, list[str]] = {}
        for node_type, aliases in CANONICAL_FIELD_ALIASES.items():
            if node_type == "Process":
                values = [module]
                matched_cols = []
                canonical_by_type[node_type] = values
                continue
            matched_cols = [
                col for col in df.columns
                if any(alias in str(col).lower().replace("-", "_").replace(" ", "_") for alias in aliases)
            ]

            # Do not copy employee names, operator names or employee IDs into the
            # general-purpose Digital Thread. Represent workforce information only
            # through explicitly aggregated count fields in this cross-domain graph.
            if node_type == "Workforce":
                aggregate_cols = _workforce_aggregate_columns(df)
                values = []
                for column in aggregate_cols[:6]:
                    numeric = pd.to_numeric(df[column], errors="coerce").dropna()
                    if numeric.empty:
                        continue
                    cohort_name = f"{module} workforce cohort"
                    node_id = _upsert_node(
                        "Workforce",
                        cohort_name,
                        f"{module}|workforce|aggregate|{column}",
                        module,
                        status="Observed",
                        metadata={
                            "aggregate_only": True,
                            "aggregate_field": str(column),
                            "observations": int(len(numeric)),
                            "mean_count": float(numeric.mean()),
                        },
                        identity_key=f"workforce-cohort:{module}:{column}",
                    )
                    values.append(cohort_name)
                    _upsert_edge(dataset_id, node_id, "contains aggregated workforce measures")
                    _upsert_edge(process_id, node_id, "uses aggregated workforce")
                canonical_by_type[node_type] = values
                continue

            # If a trusted business key column is available, pair it with a
            # display column and use the business key—not the display label—to
            # generate the stable identity. This makes rename refreshes update the
            # same node instead of creating a second asset/product/order.
            identity_column = _stable_identity_column(df, node_type)
            if identity_column:
                display_column = _display_column(df, node_type, identity_column)
                values = []
                pairs = df[[identity_column, display_column]].dropna(subset=[identity_column]).drop_duplicates().head(40)
                for _, row in pairs.iterrows():
                    identity_value = str(row[identity_column]).strip()
                    display_value = str(row[display_column]).strip() if pd.notna(row[display_column]) else identity_value
                    if not identity_value or not display_value:
                        continue
                    identity_key = f"{module}|{node_type}|{identity_column}|{identity_value}"
                    node_id = _upsert_node(
                        node_type,
                        display_value,
                        f"{module}|canonical|{node_type}|{identity_column}",
                        module,
                        status="Observed",
                        metadata={
                            "canonical": True,
                            "fields": [str(identity_column), str(display_column)],
                            "identity_field": str(identity_column),
                        },
                        identity_key=identity_key,
                    )
                    values.append(display_value)
                    _upsert_edge(dataset_id, node_id, f"contains {node_type.lower()}")
                    _upsert_edge(process_id, node_id, f"uses {node_type.lower()}")
                canonical_by_type[node_type] = values
                continue

            values = []
            for col in matched_cols[:4]:
                try:
                    for value in df[col].dropna().astype(str).drop_duplicates().head(40):
                        clean_value = value.strip()
                        if clean_value and clean_value not in values:
                            values.append(clean_value)
                except Exception:
                    continue
            canonical_by_type[node_type] = values
            for value in values[:40]:
                node_id = _upsert_node(
                    node_type,
                    value,
                    f"{module}|canonical|{node_type}|{value}",
                    module,
                    status="Observed",
                    metadata={"canonical": True, "fields": matched_cols[:4]},
                )
                _upsert_edge(dataset_id, node_id, f"contains {node_type.lower()}")
                _upsert_edge(process_id, node_id, f"uses {node_type.lower()}")

        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        for col in numeric_cols[:12]:
            kpi_id = _upsert_node(
                "KPI",
                str(col),
                f"{module}|kpi|{col}",
                module,
                metadata={"dtype": str(df[col].dtype)},
                identity_key=f"kpi:{module}:{col}",
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
            model_id = _upsert_node(
                "Model", f"{module} analytical model", source, module,
                status=model_status, identity_key=f"model:{module}",
            )
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
            identity_key=f"experiment:{study['study_id']}",
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
            identity_key=f"decision:{decision['decision_id']}",
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
            identity_key=f"outcome:{decision['decision_id']}",
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

    for left_type, right_type in zip(CANONICAL_LIFECYCLE, CANONICAL_LIFECYCLE[1:]):
        left_nodes = [n for n in nodes if n["node_type"] == left_type and n.get("module") in {module, ""}]
        right_nodes = [n for n in nodes if n["node_type"] == right_type and n.get("module") in {module, ""}]
        if left_nodes and right_nodes:
            for left in left_nodes[:6]:
                for right in right_nodes[:6]:
                    _upsert_edge(
                        left["node_id"],
                        right["node_id"],
                        f"canonical {left_type.lower()} to {right_type.lower()}",
                    )

    workspace = str(
        st.session_state.get("shoir_workspace_name")
        or st.session_state.get("workspace")
        or st.session_state.get("active_workspace_name")
        or "default"
    )

    # Durable canonical store is the source of truth; session state is a cache.
    try:
        from shoir_enterprise_layer import (
            upsert_canonical_entity, upsert_canonical_relationship, record_canonical_event,
        )
        canonical_ids = {}
        for node in nodes:
            state = dict(node)
            state["thread_node_id"] = node.get("node_id")
            entity_id = upsert_canonical_entity(
                owner,
                str(node.get("node_type", "Entity")),
                str(node.get("name", "")),
                str(node.get("source", "")),
                state=state,
                status=str(node.get("status", "Observed")),
                workspace=workspace,
            )
            canonical_ids[str(node.get("node_id"))] = entity_id
        relationship_ids = []
        for edge in st.session_state[_keys()["edges"]]:
            source_id = canonical_ids.get(str(edge.get("source_id")))
            target_id = canonical_ids.get(str(edge.get("target_id")))
            if not source_id or not target_id:
                continue
            relationship_ids.append(
                upsert_canonical_relationship(
                    owner,
                    source_id,
                    target_id,
                    str(edge.get("relation", "Linked")),
                    status=str(edge.get("status", "Linked")),
                    metadata=edge.get("metadata", {}),
                    workspace=workspace,
                )
            )
        record_canonical_event(
            owner,
            "digital_thread_sync",
            {
                "project_id": st.session_state[_keys()["project"]].get("project_id", "global-thread"),
                "module": active_module or "global",
                "entity_count": len(canonical_ids),
                "relationship_count": len(relationship_ids),
                "canonical_lifecycle": CANONICAL_LIFECYCLE,
            },
            workspace=workspace,
        )
    except Exception:
        # The graph remains available in-session if a persistence backend is temporarily unavailable.
        pass

    try:
        from shoir_enterprise_layer import record_artifact
        record_artifact(
            owner,
            "digital_thread_state",
            st.session_state[_keys()["project"]].get("project_id", "global-thread"),
            {
                "project": st.session_state[_keys()["project"]],
                "nodes": nodes,
                "edges": st.session_state[_keys()["edges"]],
                "canonical_lifecycle": CANONICAL_LIFECYCLE,
                "version": int(st.session_state.get(_keys()["version"], 1)) + 1,
            },
            workspace,
        )
    except Exception:
        pass

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


def _restore_thread_from_artifact(owner: str, workspace: str = "default") -> bool:
    """Recover the most recent durable Digital Thread snapshot into session state."""
    try:
        from shoir_enterprise_layer import list_artifacts
        table = list_artifacts(owner, "digital_thread_state", workspace, limit=1)
        if table.empty or "payload_json" not in table.columns:
            return False
        raw = table.iloc[0]["payload_json"]
        payload = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        project = payload.get("project")
        nodes = payload.get("nodes")
        edges = payload.get("edges")
        if not isinstance(project, dict) or not isinstance(nodes, list) or not isinstance(edges, list):
            return False
        keys = ensure_thread_state(owner)
        if st.session_state.get(keys["nodes"]) or st.session_state.get(keys["edges"]):
            return False
        st.session_state[keys["project"]] = project
        st.session_state[keys["nodes"]] = nodes
        st.session_state[keys["edges"]] = edges
        st.session_state[keys["sync"]] = project.get("updated_at", _now())
        st.session_state[keys["version"]] = int(payload.get("version", 1))
        return True
    except Exception:
        return False


def _restore_thread_from_canonical_store(owner: str, workspace: str = "default") -> bool:
    """Restore the canonical Digital Thread from durable entities/relationships."""
    try:
        from shoir_enterprise_layer import canonical_entities_frame, canonical_relationships_frame
        entities = canonical_entities_frame(owner, workspace, limit=5000)
        relationships = canonical_relationships_frame(owner, workspace, limit=10000)
        if entities.empty:
            return False
        keys = ensure_thread_state(owner)
        nodes = []
        canonical_to_thread = {}
        for row in entities.to_dict("records"):
            try:
                payload = json.loads(row.get("state_json") or "{}")
            except Exception:
                payload = {}
            thread_node = {
                "node_id": payload.get("thread_node_id") or row["entity_id"],
                "node_type": str(row.get("entity_type", "Entity")),
                "name": str(row.get("name", "")),
                "source": str(row.get("source", "")),
                "module": str(payload.get("module", "")),
                "status": str(row.get("status", "Observed")),
                "metadata": payload.get("metadata", {}),
                "updated_at": str(row.get("updated_at") or row.get("created_at") or _now()),
            }
            nodes.append(thread_node)
            canonical_to_thread[str(row["entity_id"])] = thread_node["node_id"]

        edges = []
        for row in relationships.to_dict("records"):
            source = canonical_to_thread.get(str(row.get("source_entity_id")))
            target = canonical_to_thread.get(str(row.get("target_entity_id")))
            if not source or not target:
                continue
            try:
                metadata = json.loads(row.get("metadata_json") or "{}")
            except Exception:
                metadata = {}
            edges.append({
                "edge_id": str(row.get("relationship_id")),
                "source_id": source,
                "target_id": target,
                "relation": str(row.get("relation", "Linked")),
                "status": str(row.get("status", "Linked")),
                "metadata": metadata,
                "updated_at": str(row.get("updated_at") or row.get("created_at") or _now()),
            })
        st.session_state[keys["nodes"]] = nodes
        st.session_state[keys["edges"]] = edges
        st.session_state[keys["sync"]] = _now()
        st.session_state[keys["version"]] = max(1, int(st.session_state.get(keys["version"], 1)))
        if nodes:
            st.session_state[keys["project"]]["updated_at"] = _now()
        return bool(nodes)
    except Exception:
        return False


def canonical_flow_figure(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> go.Figure | None:
    """Plot only observed canonical lifecycle objects; never create measurements."""
    allowed = set(CANONICAL_LIFECYCLE)
    selected = [node for node in nodes if node.get("node_type") in allowed]
    if not selected or not edges:
        return None
    index = {node["node_id"]: idx for idx, node in enumerate(selected)}
    labels = [f"{node['node_type']} · {str(node.get('name', ''))[:36]}" for node in selected]
    sources, targets, values = [], [], []
    for edge in edges:
        if edge.get("source_id") in index and edge.get("target_id") in index:
            sources.append(index[edge["source_id"]])
            targets.append(index[edge["target_id"]])
            values.append(1)
    if not sources:
        return None
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node={"label": labels, "pad": 12, "thickness": 14},
        link={"source": sources, "target": targets, "value": values},
    ))
    fig.update_layout(title="Canonical Industrial Decision Flow", height=620, margin={"l":10,"r":10,"t":60,"b":10})
    return fig

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

    # First-open experience: recover durable canonical state before artifact/session state.
    if not st.session_state.get(keys["sync"]):
        workspace = str(
            st.session_state.get("shoir_workspace_name")
            or st.session_state.get("workspace")
            or st.session_state.get("active_workspace_name")
            or "default"
        )
        restored = _restore_thread_from_canonical_store(username, workspace)
        if not restored:
            _restore_thread_from_artifact(username, workspace)

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
        st.markdown("### Canonical entity lifecycle")
        for row_start in range(0, len(THREAD_TYPES), 6):
            kinds = THREAD_TYPES[row_start : row_start + 6]
            step_cols = st.columns(len(kinds))
            for offset, kind in enumerate(kinds):
                idx = row_start + offset
                step_cols[offset].markdown(
                    f"<div class='sx-step'>{idx+1}. {kind}<br><small>{counts[kind]:,}</small></div>",
                    unsafe_allow_html=True,
                )

        missing_layers = [kind for kind in THREAD_TYPES if counts[kind] == 0]
        if missing_layers:
            st.info("Layers not populated yet: " + ", ".join(missing_layers) + ". Run a workspace sync or create the missing record explicitly.")
        else:
            st.success(f"✅ All {len(THREAD_TYPES)} canonical entity layers are represented in this project.")

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
            selected_id = st.selectbox("Select any canonical thread item", list(labels.keys()), format_func=labels.get, key="global_thread_trace_node")
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
        st.markdown("### Rename an existing node (keep its canonical ID)")
        if raw_nodes:
            rename_labels = {
                str(node["node_id"]): f"{node['node_type']} · {node['name']}"
                for node in raw_nodes
            }
            rename_target_id = st.selectbox(
                "Node to rename",
                list(rename_labels.keys()),
                format_func=rename_labels.get,
                key="global_thread_rename_target",
            )
            selected_rename_node = next(
                (node for node in raw_nodes if str(node.get("node_id")) == str(rename_target_id)),
                None,
            )
            if selected_rename_node:
                proposed_name = st.text_input(
                    "New display name",
                    value=str(selected_rename_node.get("name") or ""),
                    key=f"global_thread_rename_name_{rename_target_id}",
                )
                if st.button(
                    "Save display name and keep canonical ID",
                    use_container_width=True,
                    key="global_thread_rename_save",
                ):
                    previous_nodes = [
                        {**node, "metadata": dict(node.get("metadata") or {})}
                        for node in raw_nodes
                    ]
                    previous_version = int(st.session_state.get(keys["version"], 1))
                    previous_project_updated = project.get("updated_at", "")
                    raw_history = st.session_state.get("shoir_digital_thread_rename_history", [])
                    previous_history = list(raw_history) if isinstance(raw_history, list) else []
                    previous_name = str(selected_rename_node.get("name") or "")
                    try:
                        renamed = rename_thread_node(rename_target_id, proposed_name)
                        workspace_name = str(
                            st.session_state.get("shoir_workspace_name")
                            or st.session_state.get("workspace")
                            or st.session_state.get("active_workspace_name")
                            or "default"
                        )
                        history_entry = {
                            "event_id": "DTR-" + uuid.uuid4().hex[:14].upper(),
                            "actor": username,
                            "workspace": workspace_name,
                            "node_id": renamed["node_id"],
                            "node_type": renamed["node_type"],
                            "previous_name": previous_name,
                            "new_name": renamed["name"],
                            "created_at": _now(),
                        }
                        st.session_state["shoir_digital_thread_rename_history"] = (
                            previous_history + [history_entry]
                        )[-200:]
                        persist_digital_thread_workspace(username)
                        st.success(
                            "Display name saved to the managed workspace. "
                            f"Canonical ID remains {renamed['node_id']}. "
                            f"Change reference: {history_entry['event_id']}"
                        )
                        st.rerun()
                    except Exception as exc:
                        st.session_state[keys["nodes"]] = previous_nodes
                        st.session_state[keys["version"]] = previous_version
                        if isinstance(st.session_state.get(keys["project"]), dict):
                            st.session_state[keys["project"]]["updated_at"] = previous_project_updated
                        st.session_state["shoir_digital_thread_rename_history"] = previous_history
                        st.error(
                            "The managed workspace save could not be confirmed. "
                            "The previous node label has been restored in this session. "
                            f"Reason: {exc}"
                        )
            rename_history = st.session_state.get("shoir_digital_thread_rename_history", [])
            st.markdown("### Recent rename history")
            st.caption(
                "This history is saved with the authenticated workspace. "
                "It is not an append-only or tamper-proof enterprise audit log."
            )
            if isinstance(rename_history, list) and rename_history:
                history_frame = pd.DataFrame(rename_history[-25:][::-1])
                visible_columns = [
                    column for column in (
                        "created_at", "actor", "node_type", "previous_name",
                        "new_name", "node_id", "event_id",
                    )
                    if column in history_frame.columns
                ]
                st.dataframe(history_frame[visible_columns], use_container_width=True, hide_index=True)
            else:
                st.info("No saved node-renames are recorded in this workspace yet.")
        else:
            st.info("Sync the workspace before renaming a Digital Thread node.")

        st.markdown("### Create a node manually")
        n1, n2, n3, n4 = st.columns(4)
        with n1:
            node_type = st.selectbox("Type", THREAD_TYPES, key="global_thread_new_type")
        with n2:
            node_name = st.text_input("Name", key="global_thread_new_name")
        with n3:
            node_status = st.selectbox("Status", ["Observed", "Inferred", "Pending verification"], key="global_thread_new_status")
        with n4:
            manual_identity = st.text_input(
                "Stable business ID (optional)",
                key="global_thread_new_identity",
                help="Use an immutable asset, product, order, project or decision ID. Do not enter passwords or personal identifiers.",
            )
        if st.button("＋ Add node", use_container_width=True, key="global_thread_add_node"):
            if node_name.strip():
                _upsert_node(
                    node_type,
                    node_name.strip(),
                    f"manual:{username}:{uuid.uuid4().hex}",
                    module,
                    node_status,
                    metadata={"identity_key_provided": bool(manual_identity.strip())},
                    identity_key=manual_identity.strip(),
                )
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
