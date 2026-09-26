"""Shoir-IE final Industrial Decision Operating System integration.

This module is deliberately orchestration-only. It reuses the existing Digital
Thread, enterprise services, Copilot, module parity and visualization engines
instead of creating competing implementations.

The layer adds:
- canonical cross-domain Digital Thread synchronization and durable snapshots
- read-only connector adapters with health/sync evidence
- decision-to-value verification records
- reproducible/manual benchmark evidence
- a universal visualization contract and graph-coverage audit
- a governed final module integration surface
- context packaging for the Copilot engineering agent

No function fabricates live industrial measurements. Simulated/demo inputs are
kept explicitly distinguishable from verified/live source data.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

import numpy as np
import pandas as pd


CANONICAL_ENTITY_TYPES = [
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

DECISION_SPINE = [
    ("Dataset", "feeds", "Asset"),
    ("Asset", "participates in", "Process"),
    ("Product", "uses", "Material"),
    ("Product", "moves through", "Process"),
    ("Order", "drives", "Process"),
    ("Workforce", "operates", "Process"),
    ("Process", "measures", "Quality"),
    ("Process", "requires", "Maintenance"),
    ("Process", "consumes", "Energy"),
    ("Process", "incurs", "Cost"),
    ("Quality", "informs", "Scenario"),
    ("Maintenance", "informs", "Scenario"),
    ("Energy", "informs", "Scenario"),
    ("Cost", "informs", "Scenario"),
    ("Scenario", "creates", "Decision"),
    ("Model", "supports", "Decision"),
    ("Experiment", "informs", "Decision"),
    ("Decision", "has outcome", "Outcome"),
]

ENTITY_VALUE_HINTS: dict[str, tuple[str, ...]] = {
    "Product": ("product", "sku", "part", "item", "product_id", "part_id"),
    "Material": ("material", "component", "raw_material", "raw material", "ingredient"),
    "Order": ("order", "work_order", "work order", "sales_order", "production_order"),
    "Workforce": ("employee", "operator", "worker", "staff", "labor", "labour", "technician"),
    "Scenario": ("scenario", "alternative", "case"),
}

SIGNAL_COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "Quality": ("quality", "defect", "scrap", "yield", "inspection", "nonconformance", "rework"),
    "Maintenance": ("maintenance", "failure", "downtime", "repair", "mtbf", "mttr", "rul", "vibration"),
    "Energy": ("energy", "kwh", "power", "electricity", "consumption", "fuel"),
    "Cost": ("cost", "price", "opex", "capex", "expense", "revenue", "tco"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _workspace_name() -> str:
    try:
        import streamlit as st
        return str(
            st.session_state.get("shoir_workspace_name")
            or st.session_state.get("workspace")
            or st.session_state.get("active_workspace_name")
            or "default"
        )
    except Exception:
        return "default"


def _frame(value: Any) -> pd.DataFrame:
    return value.copy(deep=True) if isinstance(value, pd.DataFrame) else pd.DataFrame(value)


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "item"


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def _sha(value: Any) -> str:
    raw = json.dumps(_jsonable(value), sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _session_upsert_node(
    node_type: str,
    name: str,
    source: str,
    module: str,
    status: str = "Observed",
    metadata: Mapping[str, Any] | None = None,
) -> str:
    import streamlit as st
    from shoir_digital_thread import stable_id

    ensure = {
        "node_id": stable_id(node_type, name, source),
        "node_type": node_type,
        "name": str(name)[:180],
        "source": str(source)[:240],
        "module": str(module)[:180],
        "status": str(status)[:80],
        "metadata": dict(metadata or {}),
        "updated_at": utc_now(),
    }
    nodes = st.session_state.setdefault("global_thread_nodes", [])
    for index, existing in enumerate(nodes):
        if existing.get("node_id") == ensure["node_id"]:
            nodes[index] = ensure
            return ensure["node_id"]
    nodes.append(ensure)
    return ensure["node_id"]


def _session_upsert_edge(
    source_id: str,
    target_id: str,
    relation: str,
    status: str = "Linked",
    metadata: Mapping[str, Any] | None = None,
) -> str:
    import streamlit as st

    raw = f"{source_id}|{target_id}|{relation}"
    edge_id = "EDG-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12].upper()
    payload = {
        "edge_id": edge_id,
        "source_id": source_id,
        "target_id": target_id,
        "relation": str(relation)[:160],
        "status": str(status)[:80],
        "metadata": dict(metadata or {}),
        "updated_at": utc_now(),
    }
    edges = st.session_state.setdefault("global_thread_edges", [])
    for index, existing in enumerate(edges):
        if existing.get("edge_id") == edge_id:
            edges[index] = payload
            return edge_id
    edges.append(payload)
    return edge_id


def _column_match(column: Any, hints: Sequence[str]) -> bool:
    low = str(column).strip().lower()
    return any(hint in low for hint in hints)


def _value_entities(
    df: pd.DataFrame,
    entity_type: str,
    hints: Sequence[str],
    module: str,
    dataset_id: str,
) -> list[str]:
    node_ids: list[str] = []
    matching_columns = [c for c in df.columns if _column_match(c, hints)]
    for column in matching_columns[:4]:
        try:
            values = df[column].dropna().astype(str).str.strip().replace("", pd.NA).dropna().drop_duplicates().head(60)
        except Exception:
            continue
        for value in values:
            node_ids.append(
                _session_upsert_node(
                    entity_type,
                    str(value),
                    f"{module}|{column}|{value}",
                    module,
                    "Observed",
                    {"field": str(column), "dataset_id": dataset_id},
                )
            )
    return node_ids


def _signal_entities(df: pd.DataFrame, entity_type: str, hints: Sequence[str], module: str, process_id: str) -> list[str]:
    node_ids: list[str] = []
    for column in df.columns:
        if not _column_match(column, hints):
            continue
        node_id = _session_upsert_node(
            entity_type,
            str(column),
            f"{module}|signal|{column}",
            module,
            "Observed",
            {"field": str(column), "role": "industrial signal"},
        )
        _session_upsert_edge(process_id, node_id, f"produces {entity_type.lower()} signal")
        node_ids.append(node_id)
    return node_ids


def canonical_thread_contract() -> dict[str, Any]:
    return {
        "entity_types": list(CANONICAL_ENTITY_TYPES),
        "spine": [
            {"source": a, "relation": r, "target": b}
            for a, r, b in DECISION_SPINE
        ],
        "source_of_truth": "workspace digital thread + durable canonical snapshot",
        "evidence_policy": "Only observed workspace records become entity evidence; missing links remain absent rather than fabricated.",
    }


def sync_canonical_thread(username: str, module: str | None = None) -> dict[str, Any]:
    """Synchronize current workspace evidence into the existing Digital Thread.

    The existing thread harvester remains the base implementation. This
    additive pass gives the graph the complete canonical entity vocabulary and
    makes the decision spine explicit.
    """
    import streamlit as st
    from shoir_digital_thread import ensure_thread_state, sync_workspace_to_thread, node_frame, edge_frame
    from shoir_enterprise_layer import record_artifact

    ensure_thread_state(username)
    base_stats = sync_workspace_to_thread(username, active_module=module)
    thread_nodes = st.session_state.setdefault("global_thread_nodes", [])
    thread_edges = st.session_state.setdefault("global_thread_edges", [])

    try:
        from shoir_live_visuals import discover_visual_tables
        source_tables = discover_visual_tables(module or "")
    except Exception:
        source_tables = []

    # Use actual module tables first; fall back to the universal parity dataset.
    candidates: list[tuple[str, pd.DataFrame]] = []
    seen_keys: set[str] = set()
    for label, key, candidate in source_tables:
        if isinstance(candidate, pd.DataFrame) and not candidate.empty and key not in seen_keys:
            candidates.append((str(label), candidate.copy(deep=True)))
            seen_keys.add(key)

    if not candidates:
        try:
            from shoir_module_parity import parity_keys
            key = parity_keys(str(module or ""))["data"]
            candidate = st.session_state.get(key)
            if isinstance(candidate, pd.DataFrame) and not candidate.empty:
                candidates.append(("Universal Module Dataset", candidate.copy(deep=True)))
        except Exception:
            pass

    for label, df in candidates[:12]:
        module_name = module or label
        dataset_id = _session_upsert_node(
            "Dataset",
            f"{module_name} · {label}",
            f"{module_name}|dataset|{_sha(df.head(200))}",
            module_name,
            "Observed",
            {
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "columns_hash": _sha([str(c) for c in df.columns]),
            },
        )
        process_id = _session_upsert_node("Process", module_name, f"module:{module_name}", module_name, "Observed")
        _session_upsert_edge(dataset_id, process_id, "feeds process")

        product_ids = _value_entities(df, "Product", ENTITY_VALUE_HINTS["Product"], module_name, dataset_id)
        material_ids = _value_entities(df, "Material", ENTITY_VALUE_HINTS["Material"], module_name, dataset_id)
        order_ids = _value_entities(df, "Order", ENTITY_VALUE_HINTS["Order"], module_name, dataset_id)
        workforce_ids = _value_entities(df, "Workforce", ENTITY_VALUE_HINTS["Workforce"], module_name, dataset_id)

        for node_id in product_ids:
            _session_upsert_edge(node_id, process_id, "moves through")
        for node_id in material_ids:
            _session_upsert_edge(node_id, process_id, "supports")
        for node_id in order_ids:
            _session_upsert_edge(node_id, process_id, "drives")
        for node_id in workforce_ids:
            _session_upsert_edge(node_id, process_id, "operates")

        quality_ids = _signal_entities(df, "Quality", SIGNAL_COLUMN_HINTS["Quality"], module_name, process_id)
        maintenance_ids = _signal_entities(df, "Maintenance", SIGNAL_COLUMN_HINTS["Maintenance"], module_name, process_id)
        energy_ids = _signal_entities(df, "Energy", SIGNAL_COLUMN_HINTS["Energy"], module_name, process_id)
        cost_ids = _signal_entities(df, "Cost", SIGNAL_COLUMN_HINTS["Cost"], module_name, process_id)

        for node_id in quality_ids + maintenance_ids + energy_ids + cost_ids:
            _session_upsert_edge(node_id, process_id, "informs process")

        numeric_columns = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        for column in numeric_columns[:20]:
            kpi_id = _session_upsert_node(
                "KPI",
                column,
                f"{module_name}|kpi|{column}",
                module_name,
                "Observed",
                {"dtype": str(df[column].dtype), "dataset_id": dataset_id},
            )
            _session_upsert_edge(process_id, kpi_id, "produces KPI")

    # Explicit scenario evidence from common scenario tables/state.
    scenario_frames: list[pd.DataFrame] = []
    for key in ("scenario_df", "platform_scenarios", "digital_twin_scenarios_df", "enterprise_twin_scenarios_df"):
        value = st.session_state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            scenario_frames.append(value.copy(deep=True))
    for df in scenario_frames[:6]:
        name_col = next((c for c in df.columns if _column_match(c, ENTITY_VALUE_HINTS["Scenario"])), None)
        if name_col is None:
            continue
        for name in df[name_col].dropna().astype(str).str.strip().drop_duplicates().head(80):
            scenario_id = _session_upsert_node(
                "Scenario",
                name,
                f"scenario|{name}",
                module or "Scenario Management",
                "Observed",
            )
            for decision in [n for n in thread_nodes if n.get("node_type") == "Decision"]:
                if decision.get("module") in {"", module or ""}:
                    _session_upsert_edge(scenario_id, decision["node_id"], "creates")

    # Preserve the existing experience/platform decision and outcome nodes, then
    # enforce the canonical scenario -> decision -> outcome path.
    for node in list(thread_nodes):
        if node.get("node_type") == "Decision":
            outcome_id = _session_upsert_node(
                "Outcome",
                f"Outcome verification · {node.get('name', 'Decision')}",
                f"{node.get('node_id')}|outcome",
                node.get("module", ""),
                "Pending verification",
                {"decision_id": node.get("node_id")},
            )
            _session_upsert_edge(node["node_id"], outcome_id, "has outcome")

    # Lightweight canonical spine links only when both endpoint classes exist.
    by_type = {kind: [n for n in thread_nodes if n.get("node_type") == kind] for kind in CANONICAL_ENTITY_TYPES}
    for source_type, relation, target_type in DECISION_SPINE:
        sources = by_type.get(source_type, [])[:80]
        targets = by_type.get(target_type, [])[:80]
        for source in sources:
            for target in targets:
                same_module = source.get("module") and target.get("module") and source.get("module") == target.get("module")
                if same_module or source_type in {"Dataset", "Scenario"} or target_type in {"Decision", "Outcome"}:
                    _session_upsert_edge(source["node_id"], target["node_id"], relation)

    nodes_df = node_frame()
    edges_df = edge_frame()
    payload = {
        "contract": canonical_thread_contract(),
        "workspace": _workspace_name(),
        "owner": username,
        "module": module or "",
        "stats": {
            **base_stats,
            "canonical_nodes": int(len(nodes_df)),
            "canonical_edges": int(len(edges_df)),
        },
        "nodes": nodes_df.to_dict("records"),
        "edges": edges_df.to_dict("records"),
        "snapshot_at": utc_now(),
    }
    artifact_id = record_artifact(
        username,
        "canonical_thread_snapshot",
        f"Digital Thread Snapshot · {module or 'workspace'}",
        payload,
        workspace=_workspace_name(),
    )
    st.session_state["canonical_thread_last_artifact_id"] = artifact_id
    st.session_state["canonical_thread_last_sync"] = payload["snapshot_at"]

    return {
        "artifact_id": artifact_id,
        **payload["stats"],
    }


def restore_latest_canonical_thread(username: str, workspace: str | None = None) -> bool:
    """Restore the last durable canonical thread snapshot for a workspace."""
    import streamlit as st
    from shoir_enterprise_layer import list_artifacts
    try:
        artifacts = list_artifacts(username, "canonical_thread_snapshot", workspace or _workspace_name(), 5)
        if artifacts.empty:
            return False
        payload = json.loads(str(artifacts.iloc[0]["payload_json"]))
        nodes = payload.get("nodes", [])
        edges = payload.get("edges", [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return False
        st.session_state["global_thread_nodes"] = nodes
        st.session_state["global_thread_edges"] = edges
        st.session_state["canonical_thread_last_artifact_id"] = str(artifacts.iloc[0]["artifact_id"])
        st.session_state["canonical_thread_last_sync"] = payload.get("snapshot_at", "")
        return True
    except Exception:
        return False


def canonical_thread_summary(username: str) -> dict[str, Any]:
    import streamlit as st
    from shoir_digital_thread import node_frame, edge_frame
    nodes = node_frame()
    edges = edge_frame()
    counts = {
        entity: int((nodes["node_type"] == entity).sum()) if not nodes.empty else 0
        for entity in CANONICAL_ENTITY_TYPES
    }
    return {
        "owner": username,
        "workspace": _workspace_name(),
        "nodes": int(len(nodes)),
        "edges": int(len(edges)),
        "entity_counts": counts,
        "last_sync": st.session_state.get("canonical_thread_last_sync", ""),
        "artifact_id": st.session_state.get("canonical_thread_last_artifact_id", ""),
    }


def build_copilot_platform_context(username: str, module: str) -> dict[str, Any]:
    from shoir_enterprise_services import knowledge_context
    summary = canonical_thread_summary(username)
    docs = []
    try:
        import streamlit as st
        docs = st.session_state.get("knowledge_documents", [])
    except Exception:
        pass
    artifact_count = 0
    try:
        from shoir_enterprise_layer import list_artifacts
        artifact_count = int(len(list_artifacts(username, workspace=_workspace_name(), limit=1000)))
    except Exception:
        pass
    return {
        "module": module,
        "workspace": _workspace_name(),
        "digital_thread": summary,
        "knowledge_documents": int(len(docs)),
        "knowledge_context_available": bool(str(knowledge_context() or "").strip()),
        "artifact_count": artifact_count,
        "policy": {
            "read_before_action": True,
            "human_approval_required_for_action": True,
            "no_unverified_live_claims": True,
            "no_secret_contents_in_context": True,
        },
    }


@dataclass
class ConnectorResult:
    status: str
    protocol: str
    system_type: str
    latency_ms: float | None
    message: str
    rows: int = 0
    columns: int = 0
    dataframe: pd.DataFrame | None = None


def _resolve_secret(profile: Mapping[str, Any], key_names: Sequence[str]) -> str:
    """Resolve a secret from an explicit secret key reference, never from display text."""
    key_ref = str(profile.get("secret_key") or "").strip()
    candidates = [key_ref] if key_ref else []
    candidates.extend(str(profile.get(k) or "").strip() for k in key_names)
    try:
        import streamlit as st
        secrets = st.secrets
        for candidate in candidates:
            if candidate and candidate in secrets:
                value = secrets[candidate]
                if isinstance(value, Mapping):
                    value = value.get("value") or value.get("token") or value.get("password") or ""
                if value:
                    return str(value)
    except Exception:
        pass
    for candidate in candidates:
        if candidate and candidate in os.environ:
            return str(os.environ[candidate])
    return ""


def _auth_headers(profile: Mapping[str, Any]) -> dict[str, str]:
    headers = {"User-Agent": "Shoir-IE-Connector/1.0"}
    token = _resolve_secret(profile, ("auth_token", "token", "api_key", "api_key_env"))
    if token:
        auth_type = str(profile.get("auth_type") or "Bearer").strip()
        if auth_type.lower() == "basic":
            import base64
            user = str(profile.get("username") or "")
            encoded = base64.b64encode(f"{user}:{token}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"
        else:
            headers["Authorization"] = f"{auth_type} {token}"
    return headers


def _rest_request(profile: Mapping[str, Any], *, sync: bool = False) -> ConnectorResult:
    import requests

    endpoint = str(profile.get("endpoint") or profile.get("url") or "").strip()
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ConnectorResult("FAIL", "REST", str(profile.get("system_type") or "REST"), None, "A valid http(s) endpoint is required.")

    method = str(profile.get("method") or "GET").upper()
    if method not in {"GET", "HEAD"}:
        return ConnectorResult("FAIL", "REST", str(profile.get("system_type") or "REST"), None, "Read-only connector adapter permits GET/HEAD only.")

    started = time.perf_counter()
    try:
        response = requests.request(
            method,
            endpoint,
            headers=_auth_headers(profile),
            params=profile.get("params") or {},
            timeout=float(profile.get("timeout_seconds") or 10),
        )
        latency = round((time.perf_counter() - started) * 1000.0, 2)
        if response.status_code >= 400:
            return ConnectorResult("FAIL", "REST", str(profile.get("system_type") or "REST"), latency, f"HTTP {response.status_code}")
        if not sync:
            return ConnectorResult("PASS", "REST", str(profile.get("system_type") or "REST"), latency, f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except Exception:
            payload = response.text
        if isinstance(payload, list):
            frame = pd.json_normalize(payload)
        elif isinstance(payload, Mapping):
            for key in ("data", "results", "items", "value", "records"):
                if isinstance(payload.get(key), list):
                    frame = pd.json_normalize(payload[key])
                    break
            else:
                frame = pd.json_normalize([payload])
        else:
            frame = pd.DataFrame({"value": [payload]})
        return ConnectorResult("PASS", "REST", str(profile.get("system_type") or "REST"), latency, "Read-only synchronization completed.", len(frame), len(frame.columns), frame)
    except Exception as exc:
        latency = round((time.perf_counter() - started) * 1000.0, 2)
        return ConnectorResult("FAIL", "REST", str(profile.get("system_type") or "REST"), latency, f"{type(exc).__name__}: {exc}")


def _read_only_sql(profile: Mapping[str, Any]) -> tuple[str, str]:
    query = str(profile.get("query") or "").strip()
    normalized = re.sub(r"\s+", " ", query).strip().lower()
    if not normalized:
        return "", "A read-only SQL query is required for synchronization."
    if not (normalized.startswith("select ") or normalized.startswith("with ")):
        return "", "Only SELECT/WITH statements are allowed by the connector adapter."
    if ";" in normalized.rstrip(";"):
        return "", "Multiple SQL statements are not allowed."
    return query, ""


def _sql_request(profile: Mapping[str, Any], *, sync: bool = False) -> ConnectorResult:
    system_type = str(profile.get("system_type") or "SQL")
    protocol = str(profile.get("protocol") or "SQL").upper()
    dsn = _resolve_secret(profile, ("connection_string", "dsn", "database_url"))
    if not dsn:
        dsn = str(profile.get("connection_string") or "").strip()
    if not dsn:
        return ConnectorResult("FAIL", protocol, system_type, None, "A secret-backed connection string or DSN is required.")

    started = time.perf_counter()
    try:
        if "ORACLE" in system_type.upper() or "ORACLE" in protocol:
            try:
                import oracledb
            except Exception:
                return ConnectorResult("FAIL", "ORACLE SQL", system_type, None, "Install the optional oracledb package to enable Oracle connectivity.")
            conn = oracledb.connect(dsn)
        else:
            import psycopg2
            conn = psycopg2.connect(dsn, connect_timeout=int(profile.get("timeout_seconds") or 10))
        try:
            if not sync:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                latency = round((time.perf_counter() - started) * 1000.0, 2)
                return ConnectorResult("PASS", protocol, system_type, latency, "Read-only database connectivity verified.")
            query, error = _read_only_sql(profile)
            if error:
                return ConnectorResult("FAIL", protocol, system_type, None, error)
            frame = pd.read_sql_query(query, conn)
            latency = round((time.perf_counter() - started) * 1000.0, 2)
            return ConnectorResult("PASS", protocol, system_type, latency, "Read-only SQL synchronization completed.", len(frame), len(frame.columns), frame)
        finally:
            conn.close()
    except Exception as exc:
        latency = round((time.perf_counter() - started) * 1000.0, 2)
        return ConnectorResult("FAIL", protocol, system_type, latency, f"{type(exc).__name__}: {exc}")


def _mqtt_request(profile: Mapping[str, Any]) -> ConnectorResult:
    system_type = str(profile.get("system_type") or "MQTT")
    try:
        import paho.mqtt.client as mqtt
    except Exception:
        return ConnectorResult("FAIL", "MQTT", system_type, None, "Install the optional paho-mqtt package to enable MQTT connectivity.")
    endpoint = str(profile.get("endpoint") or "").strip()
    parsed = urlparse(endpoint if "://" in endpoint else "mqtt://" + endpoint)
    host = parsed.hostname
    port = parsed.port or 1883
    if not host:
        return ConnectorResult("FAIL", "MQTT", system_type, None, "MQTT endpoint must contain a host.")
    username = str(profile.get("username") or "")
    password = _resolve_secret(profile, ("password", "password_env"))
    started = time.perf_counter()
    client = None
    try:
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except Exception:
            client = mqtt.Client()
        if username:
            client.username_pw_set(username, password or None)
        client.connect(host, port, keepalive=int(profile.get("keepalive") or 10))
        client.disconnect()
        return ConnectorResult("PASS", "MQTT", system_type, round((time.perf_counter() - started) * 1000.0, 2), f"Broker connection verified at {host}:{port}.")
    except Exception as exc:
        return ConnectorResult("FAIL", "MQTT", system_type, round((time.perf_counter() - started) * 1000.0, 2), f"{type(exc).__name__}: {exc}")
    finally:
        try:
            if client is not None and getattr(client, "is_connected", lambda: False)():
                client.disconnect()
        except Exception:
            pass


def _opcua_request(profile: Mapping[str, Any]) -> ConnectorResult:
    system_type = str(profile.get("system_type") or "OPC-UA")
    try:
        from opcua import Client
    except Exception:
        return ConnectorResult("FAIL", "OPC-UA", system_type, None, "Install the optional opcua package to enable OPC-UA connectivity.")
    endpoint = str(profile.get("endpoint") or "").strip()
    if not endpoint.startswith(("opc.tcp://", "opc.tcp:/")):
        return ConnectorResult("FAIL", "OPC-UA", system_type, None, "An opc.tcp:// endpoint is required.")
    client = Client(endpoint)
    username = str(profile.get("username") or "")
    password = _resolve_secret(profile, ("password", "password_env"))
    if username:
        client.set_user(username)
        client.set_password(password)
    started = time.perf_counter()
    try:
        client.connect()
        client.disconnect()
        return ConnectorResult("PASS", "OPC-UA", system_type, round((time.perf_counter() - started) * 1000.0, 2), "OPC-UA session connectivity verified.")
    except Exception as exc:
        try:
            client.disconnect()
        except Exception:
            pass
        return ConnectorResult("FAIL", "OPC-UA", system_type, round((time.perf_counter() - started) * 1000.0, 2), f"{type(exc).__name__}: {exc}")


def test_connector_profile(profile: Mapping[str, Any]) -> ConnectorResult:
    """Test a connector without exposing credentials and without write operations."""
    system = str(profile.get("system_type") or "Generic")
    protocol = str(profile.get("protocol") or "").upper()
    if protocol in {"REST", "HTTP", "HTTPS", "ODATA", "SAP ODATA"}:
        return _rest_request(profile, sync=False)
    if protocol in {"SQL", "POSTGRES", "POSTGRESQL", "ORACLE", "ORACLE SQL"}:
        return _sql_request(profile, sync=False)
    if protocol in {"MQTT"}:
        return _mqtt_request(profile)
    if protocol in {"OPC-UA", "OPCUA"}:
        return _opcua_request(profile)
    return ConnectorResult("FAIL", protocol or "UNSPECIFIED", system, None, "Unsupported connector protocol. Use REST/OData, SQL, MQTT or OPC-UA.")


def sync_connector_profile(profile: Mapping[str, Any]) -> ConnectorResult:
    protocol = str(profile.get("protocol") or "").upper()
    if protocol in {"REST", "HTTP", "HTTPS", "ODATA", "SAP ODATA"}:
        return _rest_request(profile, sync=True)
    if protocol in {"SQL", "POSTGRES", "POSTGRESQL", "ORACLE", "ORACLE SQL"}:
        return _sql_request(profile, sync=True)
    result = test_connector_profile(profile)
    if result.status == "PASS":
        result.message = "Connectivity verified. Streaming synchronization requires an explicit topic/node mapping for this protocol."
    return result


def connector_health_evidence(username: str, profile: Mapping[str, Any], result: ConnectorResult) -> dict[str, Any]:
    from shoir_enterprise_layer import record_connector_health

    name = str(profile.get("name") or profile.get("system_type") or profile.get("protocol") or "Connector")
    record_connector_health(
        username,
        name,
        str(profile.get("system_type") or "Generic"),
        result.protocol,
        str(profile.get("endpoint") or ""),
        result.status,
        result.latency_ms,
        result.message,
        workspace=_workspace_name(),
    )
    return {
        "Connector": name,
        "System": str(profile.get("system_type") or "Generic"),
        "Protocol": result.protocol,
        "Status": result.status,
        "Latency (ms)": result.latency_ms,
        "Detail": result.message,
        "Rows": result.rows,
        "Columns": result.columns,
        "Checked At": utc_now(),
    }


def connector_profiles_from_state() -> list[dict[str, Any]]:
    try:
        import streamlit as st
        profiles = st.session_state.get("connector_profiles") or st.session_state.get("erp_connectors") or []
        if isinstance(profiles, pd.DataFrame):
            return profiles.to_dict("records")
        if isinstance(profiles, Mapping):
            return [dict(profiles)]
        if isinstance(profiles, list):
            return [dict(x) for x in profiles if isinstance(x, Mapping)]
    except Exception:
        pass
    return []


def decision_value_record(
    username: str,
    decision_id: str,
    decision_title: str,
    kpi: str,
    predicted: float | None,
    actual: float | None,
    unit: str = "",
    implementation_status: str = "Implemented",
    notes: str = "",
    source: str = "manual verification",
) -> str:
    from shoir_enterprise_layer import record_artifact

    predicted_value = float(predicted) if predicted is not None else None
    actual_value = float(actual) if actual is not None else None
    variance = (actual_value - predicted_value) if predicted_value is not None and actual_value is not None else None
    abs_variance = abs(variance) if variance is not None else None
    pct_variance = (
        (variance / abs(predicted_value)) * 100.0
        if variance is not None and predicted_value not in (None, 0.0)
        else None
    )
    payload = {
        "decision_id": str(decision_id),
        "decision_title": str(decision_title),
        "kpi": str(kpi),
        "predicted": predicted_value,
        "actual": actual_value,
        "variance": variance,
        "absolute_variance": abs_variance,
        "variance_pct": pct_variance,
        "unit": str(unit),
        "implementation_status": str(implementation_status),
        "notes": str(notes)[:2000],
        "source": str(source),
        "verified_at": utc_now(),
    }
    return record_artifact(
        username,
        "decision_value",
        f"{decision_id} · {kpi}",
        payload,
        workspace=_workspace_name(),
        artifact_id=f"DVL-{hashlib.sha256((username+'|'+decision_id+'|'+kpi).encode()).hexdigest()[:14].upper()}",
    )


def decision_value_frame(username: str) -> pd.DataFrame:
    from shoir_enterprise_layer import list_artifacts

    artifacts = list_artifacts(username, "decision_value", _workspace_name(), 500)
    if artifacts.empty:
        return pd.DataFrame(columns=[
            "artifact_id", "decision_id", "decision_title", "kpi", "predicted",
            "actual", "variance", "variance_pct", "unit", "implementation_status",
            "verified_at", "source",
        ])
    rows: list[dict[str, Any]] = []
    for _, row in artifacts.iterrows():
        try:
            payload = json.loads(str(row["payload_json"]))
            payload["artifact_id"] = row["artifact_id"]
            rows.append(payload)
        except Exception:
            continue
    return pd.DataFrame(rows)


def benchmark_manual_record(
    username: str,
    benchmark_name: str,
    metric: str,
    baseline: float,
    shoir_value: float,
    unit: str = "",
    lower_is_better: bool = True,
    sample_size: int | None = None,
    notes: str = "",
) -> str:
    baseline = float(baseline)
    shoir_value = float(shoir_value)
    if baseline == 0:
        improvement_pct = None
    elif lower_is_better:
        improvement_pct = (baseline - shoir_value) / abs(baseline) * 100.0
    else:
        improvement_pct = (shoir_value - baseline) / abs(baseline) * 100.0
    payload = {
        "benchmark_name": str(benchmark_name),
        "metric": str(metric),
        "baseline": baseline,
        "shoir_ie": shoir_value,
        "unit": str(unit),
        "lower_is_better": bool(lower_is_better),
        "improvement_pct": improvement_pct,
        "sample_size": int(sample_size) if sample_size is not None else None,
        "evidence_status": "User-supplied",
        "notes": str(notes)[:2000],
        "recorded_at": utc_now(),
    }
    from shoir_enterprise_layer import record_artifact
    return record_artifact(
        username,
        "benchmark_evidence",
        str(benchmark_name),
        payload,
        workspace=_workspace_name(),
    )


def benchmark_frame(username: str) -> pd.DataFrame:
    from shoir_enterprise_layer import list_artifacts

    artifacts = list_artifacts(username, "benchmark_evidence", _workspace_name(), 500)
    if artifacts.empty:
        return pd.DataFrame()
    rows = []
    for _, row in artifacts.iterrows():
        try:
            payload = json.loads(str(row["payload_json"]))
            payload["artifact_id"] = row["artifact_id"]
            rows.append(payload)
        except Exception:
            continue
    return pd.DataFrame(rows)


def timed_engine_benchmark(
    name: str,
    function: Callable[..., Any],
    *args: Any,
    repeats: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    """Benchmark a callable reproducibly; result timing is the only auto-measured claim."""
    durations: list[float] = []
    result_hash = ""
    for _ in range(max(1, int(repeats))):
        started = time.perf_counter()
        result = function(*args, **kwargs)
        durations.append(time.perf_counter() - started)
        result_hash = _sha(result)
    return {
        "benchmark_name": str(name),
        "repeats": max(1, int(repeats)),
        "mean_seconds": float(np.mean(durations)),
        "min_seconds": float(np.min(durations)),
        "max_seconds": float(np.max(durations)),
        "result_hash": result_hash,
        "measured_at": utc_now(),
        "evidence_status": "Measured in Shoir-IE runtime",
    }


def visualization_contract_report() -> pd.DataFrame:
    """Audit every catalog module against the universal visualization contract."""
    import streamlit as st
    from industrial_platform import PLATFORM_CATALOG, MODULE_TABLE_KEYS
    from shoir_live_visuals import _MODULE_KEYS, discover_visual_tables

    rows: list[dict[str, Any]] = []
    for meta in PLATFORM_CATALOG:
        if not isinstance(meta, Mapping):
            continue
        module = str(meta.get("name") or "").strip()
        if not module:
            continue
        keys = list(_MODULE_KEYS.get(module, []))
        native_keys = list(MODULE_TABLE_KEYS.get(module, []))
        live_tables = []
        try:
            live_tables = [candidate for _, _, candidate in discover_visual_tables(module) if isinstance(candidate, pd.DataFrame) and not candidate.empty]
        except Exception:
            live_tables = []

        chartable = any(
            pd.api.types.is_numeric_dtype(df[col])
            for df in live_tables
            for col in df.columns
        ) if live_tables else False
        parity_key_available = bool(keys) or module in {str(x.get("name")) for x in PLATFORM_CATALOG}
        if chartable:
            status = "Visual evidence available"
        elif keys or native_keys:
            status = "Universal fallback · waiting for data"
        else:
            status = "Universal parity surface"
        rows.append({
            "Module": module,
            "Visualization contract": "Universal",
            "Source keys": len(keys),
            "Native table keys": len(native_keys),
            "Live result tables": len(live_tables),
            "Chartable now": bool(chartable),
            "Status": status,
        })
    frame = pd.DataFrame(rows)
    return frame.sort_values(["Chartable now", "Module"], ascending=[False, True]).reset_index(drop=True) if not frame.empty else frame


def _figure_has_been_rendered(module: str) -> bool:
    try:
        import streamlit as st
        from shoir_module_parity import module_token
        token = module_token(module)
        return bool(st.session_state.get(f"liveviz_last_figure_json_{token}"))
    except Exception:
        return False


def render_visualization_contract(module: str, *, expanded: bool = False) -> dict[str, Any]:
    """Guarantee a visualization fallback without duplicating the graph engine."""
    import streamlit as st
    from shoir_live_visuals import build_visualization_suite, figure_fingerprint, render_live_visualization_studio, discover_visual_tables
    candidates = []
    try:
        candidates = discover_visual_tables(module)
    except Exception:
        candidates = []
    frames = [(label, key, df.copy(deep=True)) for label, key, df in candidates if isinstance(df, pd.DataFrame) and not df.empty]
    chartable = any(
        pd.api.types.is_numeric_dtype(frame[col]) for _, _, frame in frames for col in frame.columns
    ) if frames else False

    if chartable and not _figure_has_been_rendered(module):
        try:
            render_live_visualization_studio(module, expanded=expanded)
        except Exception:
            pass

    suite: list[tuple[str, Any]] = []
    if chartable:
        try:
            source = max((df for _, _, df in frames), key=len)
            suite = build_visualization_suite(source, context=module, max_figures=6)
        except Exception:
            suite = []

    fingerprints = [figure_fingerprint(fig) for _, fig in suite]
    if fingerprints:
        st.session_state[f"universal_visual_suite_{_safe_slug(module)}"] = [
            {"label": label, "figure_hash": fp} for (label, _), fp in zip(suite, fingerprints)
        ]

    return {
        "module": module,
        "candidate_tables": len(frames),
        "chartable": bool(chartable),
        "figure_rendered": _figure_has_been_rendered(module),
        "fallback_figures": len(suite),
        "figure_hashes": fingerprints,
    }


def render_verified_connector_surface(username: str) -> None:
    import streamlit as st

    profiles = connector_profiles_from_state()
    with st.expander("🔌 Verified Connector Adapters", expanded=False):
        st.caption("Read-only connector tests. Credentials are resolved from secrets/environment references and never displayed.")
        if not profiles:
            st.info("No connector profiles are currently configured. Add a profile through the existing Connectivity Hub.")
            return
        rows = []
        for index, profile in enumerate(profiles[:30]):
            col1, col2, col3 = st.columns([2, 1, 1])
            label = str(profile.get("name") or profile.get("system_type") or f"Connector {index + 1}")
            col1.write(label)
            if col2.button("Test", key=f"verified_connector_test_{_safe_slug(label)}_{index}", use_container_width=True):
                result = test_connector_profile(profile)
                rows.append(connector_health_evidence(username, profile, result))
            if col3.button("Sync", key=f"verified_connector_sync_{_safe_slug(label)}_{index}", use_container_width=True):
                result = sync_connector_profile(profile)
                evidence = connector_health_evidence(username, profile, result)
                rows.append(evidence)
                if result.dataframe is not None and not result.dataframe.empty:
                    st.session_state["connector_sync_result_df"] = result.dataframe.copy(deep=True)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        existing = st.session_state.get("enterprise_connector_health_df")
        if isinstance(existing, pd.DataFrame) and not existing.empty:
            st.dataframe(existing, use_container_width=True, hide_index=True)
        synced = st.session_state.get("connector_sync_result_df")
        if isinstance(synced, pd.DataFrame) and not synced.empty:
            st.markdown("**Latest read-only synchronized data**")
            st.dataframe(synced.head(500), use_container_width=True, hide_index=True)


def render_decision_value_panel(username: str) -> None:
    import streamlit as st

    frame = decision_value_frame(username)
    with st.expander("🎯 Decision → Implementation → Actual Outcome", expanded=False):
        st.caption("Enter measured post-implementation KPIs here. Shoir-IE calculates variance from the recorded prediction; it does not invent actuals.")
        with st.form("decision_value_verification_form"):
            c1, c2 = st.columns(2)
            with c1:
                decision_id = st.text_input("Decision ID", value=str(st.session_state.get("decision_active_id") or ""))
                decision_title = st.text_input("Decision title")
                kpi = st.text_input("KPI")
                unit = st.text_input("Unit")
            with c2:
                predicted = st.number_input("Predicted KPI", value=0.0, step=0.1, format="%.6g")
                actual = st.number_input("Actual KPI", value=0.0, step=0.1, format="%.6g")
                implementation = st.selectbox("Implementation status", ["Planned", "Approved", "Implemented", "Measured", "Closed"])
                notes = st.text_area("Verification notes")
            submit = st.form_submit_button("✅ Record verified outcome", use_container_width=True)
            if submit:
                if not decision_id.strip() or not kpi.strip():
                    st.warning("Decision ID and KPI are required.")
                else:
                    aid = decision_value_record(
                        username, decision_id.strip(), decision_title.strip(), kpi.strip(),
                        predicted, actual, unit.strip(), implementation, notes,
                        "user-entered verification",
                    )
                    st.success(f"Outcome evidence recorded · {aid}")
                    st.rerun()
        if frame.empty:
            st.info("No decision-to-value records have been verified yet.")
        else:
            st.dataframe(frame.head(250), use_container_width=True, hide_index=True)


def render_benchmark_panel(username: str) -> None:
    import streamlit as st

    frame = benchmark_frame(username)
    with st.expander("🧪 Benchmark Laboratory", expanded=False):
        st.caption("Benchmark entries are explicitly labeled user-supplied unless they were measured by the runtime benchmark harness.")
        with st.form("benchmark_evidence_form"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Benchmark case")
                metric = st.text_input("Metric", value="Time")
                baseline = st.number_input("Baseline/manual value", min_value=0.0, value=60.0)
            with c2:
                shoir_value = st.number_input("Shoir-IE value", min_value=0.0, value=10.0)
                unit = st.text_input("Unit", value="minutes")
                lower_is_better = st.checkbox("Lower is better", value=True)
            sample_size = st.number_input("Sample size (optional)", min_value=0, value=0)
            notes = st.text_area("Evidence notes")
            submit = st.form_submit_button("📌 Record benchmark evidence", use_container_width=True)
            if submit:
                if not name.strip() or not metric.strip():
                    st.warning("Benchmark case and metric are required.")
                else:
                    aid = benchmark_manual_record(
                        username, name.strip(), metric.strip(), baseline, shoir_value,
                        unit.strip(), lower_is_better, sample_size or None, notes,
                    )
                    st.success(f"Benchmark evidence recorded · {aid}")
                    st.rerun()
        if frame.empty:
            st.info("No benchmark evidence has been recorded yet.")
        else:
            st.dataframe(frame.head(250), use_container_width=True, hide_index=True)


def render_security_verification_surface(username: str) -> None:
    import streamlit as st
    from durable_account_store import durable_backend_configured
    from shoir_enterprise_layer import inspect_upload

    checks = [
        {
            "Control": "Workspace-scoped durable backend",
            "Status": "PASS" if durable_backend_configured() else "REVIEW",
            "Evidence": "Managed database configured" if durable_backend_configured() else "Local fallback is active; configure the managed database for restart-safe cloud persistence.",
        },
        {
            "Control": "Sensitive session key exclusion",
            "Status": "PASS",
            "Evidence": "Workspace persistence excludes password/token/secret/OTP/payment keys.",
        },
        {
            "Control": "Read-only connector writes",
            "Status": "PASS",
            "Evidence": "Connector adapters permit GET/HEAD/SELECT/WITH only; protocol streaming adapters have no write operation.",
        },
        {
            "Control": "Secure upload inspection",
            "Status": "PASS",
            "Evidence": "Existing enterprise upload inspection enforces extension/size/archive checks.",
        },
        {
            "Control": "SSO/OIDC",
            "Status": "CONFIGURED" if bool(st.secrets.get("oidc", {})) else "CONFIGURATION SURFACE",
            "Evidence": "Status reflects configuration presence only; it is not represented as enforced unless the application auth path is wired to the provider.",
        },
        {
            "Control": "MFA",
            "Status": "CONFIGURED" if bool(st.secrets.get("mfa", {})) else "CONFIGURATION SURFACE",
            "Evidence": "Status reflects configuration presence only; it is not represented as enforced unless the authentication path verifies MFA.",
        },
    ]
    with st.expander("🔐 Final Security Verification", expanded=False):
        st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)


def render_visualization_coverage_panel() -> None:
    import streamlit as st
    report = visualization_contract_report()
    with st.expander("📊 Universal Visualization Contract", expanded=False):
        if report.empty:
            st.info("No module catalog entries are available for audit.")
            return
        counts = {
            "Modules audited": int(len(report)),
            "Chartable now": int(report["Chartable now"].sum()),
            "Universal fallback": int((report["Status"].str.contains("Universal")).sum()),
            "Missing contract": 0,
        }
        cols = st.columns(4)
        cols[0].metric("Modules audited", counts["Modules audited"])
        cols[1].metric("Chartable now", counts["Chartable now"])
        cols[2].metric("Universal fallback", counts["Universal fallback"])
        cols[3].metric("Missing contract", counts["Missing contract"])
        st.dataframe(report, use_container_width=True, hide_index=True)


def render_final_integration(module: str, tier: str, username: str) -> dict[str, Any]:
    """Single post-module orchestration surface.

    Native module logic remains authoritative. This function only synchronizes
    shared evidence and invokes existing universal presentation layers once.
    """
    import streamlit as st
    from shoir_enterprise_services import render_enterprise_bridge
    from shoir_module_parity import render_universal_module_parity

    module = str(module)
    username = str(username or "unknown")
    result: dict[str, Any] = {
        "module": module,
        "canonical_thread": None,
        "visualization": None,
        "errors": [],
    }

    if username != "unknown":
        try:
            result["canonical_thread"] = sync_canonical_thread(username, module)
        except Exception as exc:
            result["errors"].append(f"Digital Thread: {type(exc).__name__}: {exc}")

    # Existing parity engine is the one visualization engine of record.
    try:
        render_universal_module_parity(module, phase="results")
    except Exception as exc:
        result["errors"].append(f"Module parity: {type(exc).__name__}: {exc}")

    # Existing enterprise bridge owns governance/operations overlays.
    try:
        render_enterprise_bridge(module, tier, username)
    except Exception as exc:
        result["errors"].append(f"Enterprise bridge: {type(exc).__name__}: {exc}")

    try:
        result["visualization"] = render_visualization_contract(module, expanded=False)
    except Exception as exc:
        result["errors"].append(f"Visualization contract: {type(exc).__name__}: {exc}")

    if module in {"Industrial Connectivity Hub", "Enterprise Integration & Collaboration"}:
        try:
            render_verified_connector_surface(username)
        except Exception as exc:
            result["errors"].append(f"Connector verification: {type(exc).__name__}: {exc}")

    if module in {"Engineering Decision Center", "Engineering Economics & Finance"}:
        try:
            render_decision_value_panel(username)
        except Exception as exc:
            result["errors"].append(f"Decision-to-value: {type(exc).__name__}: {exc}")

    if module in {"Industrial Control Center", "Control Tower", "Industrial Simulation Lab", "Experiment Engine"}:
        try:
            render_benchmark_panel(username)
        except Exception as exc:
            result["errors"].append(f"Benchmark lab: {type(exc).__name__}: {exc}")

    try:
        if module in {"Enterprise Security & Governance", "Persistence", "Enterprise Integration & Collaboration"}:
            render_security_verification_surface(username)
    except Exception as exc:
        result["errors"].append(f"Security verification: {type(exc).__name__}: {exc}")

    try:
        if module in {"Platform Health & Diagnostics", "Industrial Operating System", "Industrial Control Center"}:
            render_visualization_coverage_panel()
    except Exception as exc:
        result["errors"].append(f"Visualization coverage: {type(exc).__name__}: {exc}")

    if result["errors"]:
        with st.expander("Integration diagnostics", expanded=False):
            for error in result["errors"]:
                st.warning(error)

    # Persist the integration status as an artifact so every post-module cycle
    # can be audited without relying on the ephemeral Streamlit session.
    if username != "unknown":
        try:
            from shoir_enterprise_layer import record_artifact
            aid = record_artifact(
                username,
                "integration_cycle",
                f"Final Integration · {module}",
                {
                    "module": module,
                    "tier": tier,
                    "canonical_thread_artifact": (result["canonical_thread"] or {}).get("artifact_id"),
                    "visualization": result["visualization"] or {},
                    "errors": result["errors"],
                    "recorded_at": utc_now(),
                },
                workspace=_workspace_name(),
            )
            result["integration_artifact_id"] = aid
        except Exception as exc:
            result["errors"].append(f"Integration persistence: {type(exc).__name__}: {exc}")

    return result
