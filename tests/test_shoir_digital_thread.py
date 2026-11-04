import pandas as pd

from shoir_digital_thread import network_figure, sankey_figure, stable_id


def test_thread_ids_are_stable():
    assert stable_id("Dataset", "Orders", "orders.csv") == stable_id("Dataset", "Orders", "orders.csv")
    assert stable_id("Dataset", "Orders", "orders.csv") != stable_id("Dataset", "Demand", "demand.csv")


def test_digital_thread_graphs_render():
    nodes = [
        {"node_id": "DAT-1", "node_type": "Dataset", "name": "Orders", "status": "Observed"},
        {"node_id": "PRO-1", "node_type": "Process", "name": "Planning", "status": "Observed"},
        {"node_id": "KPI-1", "node_type": "KPI", "name": "Throughput", "status": "Observed"},
    ]
    edges = [
        {"source_id": "DAT-1", "target_id": "PRO-1", "relation": "feeds process"},
        {"source_id": "PRO-1", "target_id": "KPI-1", "relation": "produces KPI"},
    ]
    assert network_figure(nodes, edges) is not None
    assert sankey_figure(nodes, edges) is not None


def test_thread_export_frames_are_tabular():
    assert isinstance(pd.DataFrame({"node_id": ["DAT-1"]}), pd.DataFrame)


def test_thread_vocabulary_covers_full_decision_spine():
    expected = {
        "Dataset", "Asset", "Process", "Product", "Material", "Order",
        "Workforce", "Quality", "Maintenance", "Energy", "Cost", "Scenario",
        "KPI", "Model", "Experiment", "Decision", "Outcome",
    }
    from shoir_digital_thread import THREAD_TYPES
    assert set(THREAD_TYPES) == expected



def test_source_identity_is_independent_of_display_name():
    assert stable_id("Asset", "Main Press", "asset:1001") == stable_id("Asset", "Press Line One", "asset:1001")
    assert stable_id("Asset", "Main Press", "asset:1001") != stable_id("Asset", "Main Press", "asset:1002")


def test_rename_preserves_legacy_node_id_and_existing_edges(monkeypatch):
    from types import SimpleNamespace
    import shoir_digital_thread as thread

    keys = thread._keys()
    node = {
        "node_id": "AST-LEGACY-1001",
        "node_type": "Asset",
        "name": "Press 1001",
        "source": "asset:1001",
        "module": "Manufacturing",
        "status": "Observed",
        "metadata": {},
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    edge = {
        "edge_id": "EDGE-1",
        "source_id": node["node_id"],
        "target_id": "PRO-1",
        "relation": "participates in",
    }
    fake_st = SimpleNamespace(session_state={
        keys["nodes"]: [node],
        keys["edges"]: [edge],
        keys["version"]: 1,
        keys["project"]: {"updated_at": ""},
    })
    monkeypatch.setattr(thread, "st", fake_st)

    renamed = thread.rename_thread_node(node["node_id"], "Main Press")
    assert renamed["node_id"] == "AST-LEGACY-1001"
    assert renamed["source"] == "asset:1001"
    assert renamed["name"] == "Main Press"
    assert renamed["metadata"]["display_name_override"] is True
    assert "Press 1001" in renamed["metadata"]["name_aliases"]
    assert fake_st.session_state[keys["edges"]][0] == edge

    refreshed_id = thread._upsert_node(
        "Asset", "Press 1001", "asset:1001", "Manufacturing",
        metadata={"field": "Asset ID"},
    )
    refreshed = fake_st.session_state[keys["nodes"]][0]
    assert refreshed_id == "AST-LEGACY-1001"
    assert refreshed["node_id"] == "AST-LEGACY-1001"
    assert refreshed["name"] == "Main Press"
    assert refreshed["metadata"]["display_name_override"] is True
    assert refreshed["metadata"]["field"] == "Asset ID"
