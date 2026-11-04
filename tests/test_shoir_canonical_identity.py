import json
import sqlite3
from types import SimpleNamespace

import pytest
import shoir_enterprise_layer as layer


def test_canonical_identity_survives_display_name_rename(tmp_path, monkeypatch):
    database_path = str(tmp_path / "canonical-identity.db")
    monkeypatch.setattr(layer, "DEFAULT_DB", database_path)
    monkeypatch.setattr(layer, "_remote", lambda: False)

    layer.ensure_enterprise_schema()
    workspace_id = layer.workspace_key("tester", "site-a")
    legacy_entity_id = layer.canonical_entity_id(
        "tester", "site-a", "Asset", "Press 1001", "asset:1001"
    )
    state_json = json.dumps({"legacy_record": True})
    stamp = layer.now_iso()
    with layer._local_connect() as conn:
        conn.execute(
            """INSERT INTO shoir_ent_canonical_entities
            (entity_id,workspace_id,entity_type,name,source,status,state_json,
             content_hash,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                legacy_entity_id, workspace_id, "Asset", "Press 1001", "asset:1001",
                "Observed", state_json, "legacy-hash", "tester", stamp, stamp,
            ),
        )
        conn.commit()

    renamed_entity_id, rename_event_id = layer.persist_thread_node_rename(
        "tester",
        "site-a",
        {
            "node_id": "AST-LEGACY-1001",
            "node_type": "Asset",
            "name": "Main Press",
            "source": "asset:1001",
            "module": "Manufacturing",
            "status": "Observed",
            "metadata": {
                "display_name_override": True,
                "name_aliases": ["Press 1001"],
            },
        },
        previous_name="Press 1001",
    )
    assert renamed_entity_id == legacy_entity_id
    with layer._local_connect() as conn:
        event = conn.execute(
            "SELECT event_type,entity_id,payload_json FROM shoir_ent_canonical_events WHERE event_id=?",
            (rename_event_id,),
        ).fetchone()
    assert event is not None
    assert event[0] == "digital_thread_node_renamed"
    assert event[1] == legacy_entity_id
    assert json.loads(event[2])["canonical_id_preserved"] is True

    first_id = layer.upsert_canonical_entity(
        "tester", "Asset", "Main Press", "asset:1001",
        state={"thread_node_id": "AST-LEGACY-1001", "metadata": {"display_name_override": True}},
        workspace="site-a",
    )
    second_id = layer.upsert_canonical_entity(
        "tester", "Asset", "Main Press Assembly", "asset:1001",
        state={"thread_node_id": "AST-LEGACY-1001", "metadata": {"display_name_override": True}},
        workspace="site-a",
    )

    entities = layer.canonical_entities_frame("tester", "site-a", entity_type="Asset")
    assert first_id == legacy_entity_id
    assert second_id == legacy_entity_id
    assert len(entities) == 1
    assert entities.iloc[0]["entity_id"] == legacy_entity_id
    assert entities.iloc[0]["name"] == "Main Press Assembly"
    assert entities.iloc[0]["source"] == "asset:1001"



def test_failed_rename_audit_event_rolls_back_entity_update(tmp_path, monkeypatch):
    database_path = str(tmp_path / "canonical-rename-rollback.db")
    monkeypatch.setattr(layer, "DEFAULT_DB", database_path)
    monkeypatch.setattr(layer, "_remote", lambda: False)
    fixed_hex = "ABCDEF1234567890ABCDEF1234567890"
    monkeypatch.setattr(layer.uuid, "uuid4", lambda: SimpleNamespace(hex=fixed_hex))

    layer.ensure_enterprise_schema()
    workspace_id = layer.workspace_key("tester", "site-a")
    entity_id = layer.canonical_entity_id(
        "tester", "site-a", "Asset", "Press 1001", "asset:1001"
    )
    stamp = layer.now_iso()
    with layer._local_connect() as conn:
        conn.execute(
            """INSERT INTO shoir_ent_canonical_entities
            (entity_id,workspace_id,entity_type,name,source,status,state_json,
             content_hash,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                entity_id, workspace_id, "Asset", "Press 1001", "asset:1001",
                "Observed", json.dumps({"thread_node_id": "AST-LEGACY-1001"}),
                "before-hash", "tester", stamp, stamp,
            ),
        )
        conn.execute(
            """INSERT INTO shoir_ent_canonical_events
            (event_id,workspace_id,event_type,entity_id,relationship_id,
             payload_json,actor,created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                "CEVT-" + fixed_hex[:14], workspace_id, "existing_event",
                entity_id, None, "{}", "tester", stamp,
            ),
        )
        conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        layer.persist_thread_node_rename(
            "tester",
            "site-a",
            {
                "node_id": "AST-LEGACY-1001",
                "node_type": "Asset",
                "name": "Main Press",
                "source": "asset:1001",
                "status": "Observed",
                "metadata": {"display_name_override": True},
            },
            previous_name="Press 1001",
        )

    entities = layer.canonical_entities_frame("tester", "site-a", entity_type="Asset")
    assert len(entities) == 1
    assert entities.iloc[0]["entity_id"] == entity_id
    assert entities.iloc[0]["name"] == "Press 1001"
    assert entities.iloc[0]["content_hash"] == "before-hash"
