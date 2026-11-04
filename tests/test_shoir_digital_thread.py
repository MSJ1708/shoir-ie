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



def test_thread_id_can_use_immutable_identity_across_display_renames():
    from shoir_digital_thread import stable_id

    original = stable_id("Asset", "Press 1001", "import:asset", identity_key="SAP:ASSET:1001")
    renamed = stable_id("Asset", "Main Press", "import:asset", identity_key="SAP:ASSET:1001")
    other = stable_id("Asset", "Main Press", "import:asset", identity_key="SAP:ASSET:1002")
    assert original == renamed
    assert original != other


def test_digital_thread_business_identity_column_and_display_mapping():
    from shoir_digital_thread import _stable_identity_column, _display_column

    frame = pd.DataFrame({
        "asset_id": ["A-100", "A-101"],
        "asset_name": ["Press 100", "Press 101"],
        "operator_name": ["Synthetic Person A", "Synthetic Person B"],
    })
    identity_column = _stable_identity_column(frame, "Asset")
    display_column = _display_column(frame, "Asset", identity_column)
    assert identity_column == "asset_id"
    assert display_column == "asset_name"


def test_workforce_thread_only_selects_aggregate_columns():
    from shoir_digital_thread import _workforce_aggregate_columns

    frame = pd.DataFrame({
        "employee_id": ["EMP-001", "EMP-002"],
        "employee_name": ["Synthetic Person A", "Synthetic Person B"],
        "operator_count": [4, 5],
        "headcount": [8, 9],
    })
    selected = _workforce_aggregate_columns(frame)
    assert selected == ["operator_count", "headcount"]
    assert "employee_id" not in selected
    assert "employee_name" not in selected


def test_graph_node_rename_retains_old_display_name_as_alias(monkeypatch):
    import shoir_digital_thread as thread

    state = {}
    monkeypatch.setattr(thread.st, "session_state", state, raising=False)
    thread.ensure_thread_state("synthetic-user")
    identity = "ERP:ASSET:1001"
    node_id = thread._upsert_node(
        "Asset", "Press 1001", "source:asset", "Manufacturing",
        metadata={"canonical": True}, identity_key=identity,
    )
    renamed_id = thread._upsert_node(
        "Asset", "Main Press", "source:asset", "Manufacturing",
        metadata={"canonical": True}, identity_key=identity,
    )
    assert node_id == renamed_id
    nodes = state[thread._keys()["nodes"]]
    assert len(nodes) == 1
    assert nodes[0]["name"] == "Main Press"
    assert "Press 1001" in nodes[0]["metadata"]["name_aliases"]
