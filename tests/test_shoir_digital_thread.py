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



def test_workspace_sync_preserves_asset_node_identity_when_display_name_changes(monkeypatch):
    import shoir_digital_thread as thread
    import shoir_enterprise_layer as enterprise

    session_state = {}
    monkeypatch.setattr(thread.st, "session_state", session_state, raising=False)
    frame_holder = {
        "frame": pd.DataFrame({
            "asset_id": ["ASSET-1001"],
            "asset_name": ["Press 1001"],
            "capacity_tph": [18.5],
        })
    }
    monkeypatch.setattr(
        thread, "_safe_workspace_frames",
        lambda: [("Manufacturing", frame_holder["frame"])],
    )
    monkeypatch.setattr(thread, "_discover_experience_records", lambda _owner: ([], []))
    monkeypatch.setattr(enterprise, "upsert_canonical_entity", lambda *args, **kwargs: (
        kwargs.get("state", {}).get("thread_node_id", "")
    ))
    monkeypatch.setattr(enterprise, "upsert_canonical_relationship", lambda *args, **kwargs: "CREL-TEST")
    monkeypatch.setattr(enterprise, "record_canonical_event", lambda *args, **kwargs: "CEVT-TEST")

    thread.sync_workspace_to_thread("synthetic-user")
    asset_nodes = [
        node for node in session_state[thread._keys()["nodes"]]
        if node.get("node_type") == "Asset"
    ]
    assert len(asset_nodes) == 1
    original_id = asset_nodes[0]["node_id"]

    frame_holder["frame"] = pd.DataFrame({
        "asset_id": ["ASSET-1001"],
        "asset_name": ["Main Press"],
        "capacity_tph": [19.0],
    })
    thread.sync_workspace_to_thread("synthetic-user")
    asset_nodes = [
        node for node in session_state[thread._keys()["nodes"]]
        if node.get("node_type") == "Asset"
    ]
    assert len(asset_nodes) == 1
    assert asset_nodes[0]["node_id"] == original_id
    assert asset_nodes[0]["name"] == "Main Press"
    assert "Press 1001" in asset_nodes[0]["metadata"]["name_aliases"]


def test_managed_node_rename_preserves_canonical_id_edges_aliases_and_future_sync(monkeypatch):
    from types import SimpleNamespace
    import shoir_digital_thread as thread

    keys = thread._keys()
    state = {}
    monkeypatch.setattr(thread, "st", SimpleNamespace(session_state=state))
    thread.ensure_thread_state("synthetic-user")

    node_id = thread._upsert_node(
        "Asset",
        "Press 1001",
        "asset:1001",
        "Manufacturing",
        metadata={"canonical": True},
        identity_key="ERP:ASSET:1001",
    )
    edge_id = thread._upsert_edge(node_id, "PRO-1001", "participates in")
    renamed = thread.rename_thread_node(node_id, "Main Press")

    assert renamed["node_id"] == node_id
    assert renamed["name"] == "Main Press"
    assert renamed["metadata"]["display_name_override"] is True
    assert "Press 1001" in renamed["metadata"]["name_aliases"]
    assert state[keys["edges"]][0]["edge_id"] == edge_id
    assert state[keys["edges"]][0]["source_id"] == node_id

    # A later source refresh still uses the immutable business key and must not
    # silently overwrite the user's managed display-name override.
    refreshed_id = thread._upsert_node(
        "Asset",
        "Press 1001",
        "asset:1001",
        "Manufacturing",
        metadata={"capacity_tph": 19.0},
        identity_key="ERP:ASSET:1001",
    )
    refreshed = state[keys["nodes"]][0]
    assert refreshed_id == node_id
    assert refreshed["node_id"] == node_id
    assert refreshed["name"] == "Main Press"
    assert refreshed["metadata"]["capacity_tph"] == 19.0
    assert refreshed["metadata"]["display_name_override"] is True
    assert "Press 1001" in refreshed["metadata"]["name_aliases"]


def test_managed_node_rename_rejects_duplicate_name_for_same_source(monkeypatch):
    from types import SimpleNamespace
    import pytest
    import shoir_digital_thread as thread

    keys = thread._keys()
    state = {}
    monkeypatch.setattr(thread, "st", SimpleNamespace(session_state=state))
    thread.ensure_thread_state("synthetic-user")
    first = thread._upsert_node("Asset", "Press A", "asset:duplicate", identity_key="ERP:A")
    thread._upsert_node("Asset", "Press B", "asset:duplicate", identity_key="ERP:B")

    with pytest.raises(ValueError, match="already exists"):
        thread.rename_thread_node(first, "Press B")
    assert [node["name"] for node in state[keys["nodes"]]] == ["Press A", "Press B"]


def test_renamed_node_record_preserves_original_and_adds_alias():
    from shoir_digital_thread import renamed_node_record

    original = {
        "node_id": "AST-1001",
        "node_type": "Asset",
        "name": "Press 1001",
        "source": "asset:1001",
        "metadata": {"name_aliases": ["Legacy Press"]},
    }
    updated = renamed_node_record(original, "Main Press")
    assert original["name"] == "Press 1001"
    assert original["metadata"]["name_aliases"] == ["Legacy Press"]
    assert updated["node_id"] == original["node_id"]
    assert updated["name"] == "Main Press"
    assert updated["metadata"]["name_aliases"] == ["Legacy Press", "Press 1001"]
    assert updated["metadata"]["display_name_override"] is True


def test_digital_thread_rename_save_uses_authenticated_managed_workspace(monkeypatch):
    from types import SimpleNamespace
    import shoir_digital_thread as thread
    import durable_account_store
    import workspace_persistence

    session_state = {
        "authenticated": True,
        "current_user": "tester",
        "remote_session_token": "opaque-test-token",
        "shoir_digital_thread_rename_history": [{"event_id": "DTR-1"}],
    }
    calls = []
    monkeypatch.setattr(thread, "st", SimpleNamespace(session_state=session_state))
    monkeypatch.setattr(durable_account_store, "durable_backend_configured", lambda: True)
    monkeypatch.setattr(
        workspace_persistence,
        "save_user_workspace",
        lambda actor, state: calls.append((actor, state)) or True,
    )

    assert thread.persist_digital_thread_workspace("tester") is True
    assert calls == [("tester", session_state)]


def test_digital_thread_rename_save_fails_closed_without_managed_backend(monkeypatch):
    from types import SimpleNamespace
    import pytest
    import shoir_digital_thread as thread
    import durable_account_store

    monkeypatch.setattr(
        thread,
        "st",
        SimpleNamespace(session_state={"authenticated": True, "current_user": "tester"}),
    )
    monkeypatch.setattr(durable_account_store, "durable_backend_configured", lambda: False)

    with pytest.raises(RuntimeError, match="not configured"):
        thread.persist_digital_thread_workspace("tester")


def test_digital_thread_rename_save_denies_guest_and_wrong_actor(monkeypatch):
    from types import SimpleNamespace
    import pytest
    import shoir_digital_thread as thread

    monkeypatch.setattr(
        thread,
        "st",
        SimpleNamespace(session_state={"authenticated": True, "current_user": "another-user"}),
    )
    with pytest.raises(PermissionError, match="does not match"):
        thread.persist_digital_thread_workspace("tester")

    monkeypatch.setattr(
        thread,
        "st",
        SimpleNamespace(session_state={"authenticated": True, "current_user": "Guest Visitor"}),
    )
    with pytest.raises(PermissionError, match="Guest and anonymous"):
        thread.persist_digital_thread_workspace("Guest Visitor")


def test_digital_thread_rename_save_requires_remote_write_confirmation(monkeypatch):
    from types import SimpleNamespace
    import pytest
    import shoir_digital_thread as thread
    import durable_account_store
    import workspace_persistence

    monkeypatch.setattr(
        thread,
        "st",
        SimpleNamespace(session_state={"authenticated": True, "current_user": "tester"}),
    )
    monkeypatch.setattr(durable_account_store, "durable_backend_configured", lambda: True)
    monkeypatch.setattr(workspace_persistence, "save_user_workspace", lambda actor, state: False)

    with pytest.raises(RuntimeError, match="not confirmed"):
        thread.persist_digital_thread_workspace("tester")


def test_legacy_source_identity_preserves_node_id_across_rename_and_sync(monkeypatch):
    from types import SimpleNamespace
    import shoir_digital_thread as thread

    keys = thread._keys()
    state = {}
    monkeypatch.setattr(thread, "st", SimpleNamespace(session_state=state))
    thread.ensure_thread_state("synthetic-user")

    original_id = thread._upsert_node(
        "Asset", "Press 1001", "Manufacturing|canonical|Asset|Press 1001", "Manufacturing"
    )
    thread.rename_thread_node(original_id, "Main Press")
    # Simulate a source refresh that changes the display column and therefore
    # computes a different legacy name-based ID; the unique source must recover
    # the previously issued ID and keep the user's display override.
    refreshed_id = thread._upsert_node(
        "Asset", "Press 1002", "Manufacturing|canonical|Asset|Press 1001", "Manufacturing"
    )

    assert refreshed_id == original_id
    assert state[keys["nodes"]][0]["node_id"] == original_id
    assert state[keys["nodes"]][0]["name"] == "Main Press"
    assert "Press 1001" in state[keys["nodes"]][0]["metadata"]["name_aliases"]


def test_legacy_source_identity_fails_closed_when_duplicate_nodes_exist(monkeypatch):
    from types import SimpleNamespace
    import pytest
    import shoir_digital_thread as thread

    keys = thread._keys()
    state = {}
    monkeypatch.setattr(thread, "st", SimpleNamespace(session_state=state))
    thread.ensure_thread_state("synthetic-user")
    source = "Manufacturing|canonical|Asset|legacy"
    state[keys["nodes"]] = [
        {"node_id": "AST-LEGACY-1", "node_type": "Asset", "name": "Press A", "source": source, "metadata": {}},
        {"node_id": "AST-LEGACY-2", "node_type": "Asset", "name": "Press B", "source": source, "metadata": {}},
    ]

    with pytest.raises(ValueError, match="multiple existing nodes"):
        thread._upsert_node("Asset", "Main Press", source, "Manufacturing")
