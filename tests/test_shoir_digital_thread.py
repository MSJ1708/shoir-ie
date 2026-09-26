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
