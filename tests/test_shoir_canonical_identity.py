import json

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
    state_json = json.dumps({"thread_node_id": "AST-LEGACY-1001"})
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
