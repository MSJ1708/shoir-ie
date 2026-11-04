import json

import pytest

import shoir_enterprise_layer as layer


def _seed_legacy_entity(database_path, username="tester", workspace="site-a"):
    layer.ensure_enterprise_schema()
    workspace_id = layer.workspace_key(username, workspace)
    legacy_entity_id = layer.canonical_entity_id(
        username, workspace, "Asset", "Press 1001", "asset:1001"
    )
    stamp = layer.now_iso()
    with layer._local_connect() as conn:
        conn.execute(
            """INSERT INTO shoir_ent_canonical_entities
            (entity_id,workspace_id,entity_type,name,source,status,state_json,
             content_hash,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                legacy_entity_id, workspace_id, "Asset", "Press 1001",
                "asset:1001", "Observed", json.dumps({"legacy_record": True}),
                "legacy-hash", username, stamp, stamp,
            ),
        )
        conn.commit()
    return legacy_entity_id


def test_canonical_identity_survives_display_rename_from_legacy_row(tmp_path, monkeypatch):
    database_path = str(tmp_path / "canonical-identity.db")
    monkeypatch.setattr(layer, "DEFAULT_DB", database_path)
    monkeypatch.setattr(layer, "_remote", lambda: False)
    legacy_entity_id = _seed_legacy_entity(database_path)

    first_id = layer.upsert_canonical_entity(
        "tester",
        "Asset",
        "Main Press",
        "asset:1001",
        state={
            "thread_node_id": "AST-LEGACY-1001",
            "metadata": {
                "display_name_override": True,
                "name_aliases": ["Press 1001"],
            },
        },
        workspace="site-a",
    )
    second_id = layer.upsert_canonical_entity(
        "tester",
        "Asset",
        "Main Press Assembly",
        "asset:1001",
        state={
            "thread_node_id": "AST-LEGACY-1001",
            "metadata": {
                "display_name_override": True,
                "name_aliases": ["Press 1001", "Main Press"],
            },
        },
        workspace="site-a",
    )

    entities = layer.canonical_entities_frame("tester", "site-a", entity_type="Asset")
    assert first_id == legacy_entity_id
    assert second_id == legacy_entity_id
    assert len(entities) == 1
    assert entities.iloc[0]["entity_id"] == legacy_entity_id
    assert entities.iloc[0]["name"] == "Main Press Assembly"
    assert entities.iloc[0]["source"] == "asset:1001"
    assert entities.iloc[0]["content_hash"] != "legacy-hash"


def test_canonical_identity_lookup_fails_closed_on_duplicate_legacy_alias(tmp_path, monkeypatch):
    database_path = str(tmp_path / "canonical-identity-duplicates.db")
    monkeypatch.setattr(layer, "DEFAULT_DB", database_path)
    monkeypatch.setattr(layer, "_remote", lambda: False)
    layer.ensure_enterprise_schema()
    workspace_id = layer.workspace_key("tester", "site-a")
    stamp = layer.now_iso()

    with layer._local_connect() as conn:
        for entity_id in ("CEN-LEGACY-1", "CEN-LEGACY-2"):
            conn.execute(
                """INSERT INTO shoir_ent_canonical_entities
                (entity_id,workspace_id,entity_type,name,source,status,state_json,
                 content_hash,created_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entity_id, workspace_id, "Asset", "Press 1001",
                    "asset:1001", "Observed", json.dumps({"legacy_record": True}),
                    entity_id, "tester", stamp, stamp,
                ),
            )
        conn.commit()

    with pytest.raises(RuntimeError, match="Legacy display name maps to multiple"):
        layer.upsert_canonical_entity(
            "tester",
            "Asset",
            "Main Press",
            "asset:1001",
            state={
                "thread_node_id": "AST-LEGACY-1001",
                "metadata": {"name_aliases": ["Press 1001"]},
            },
            workspace="site-a",
        )


def test_canonical_entity_id_is_stable_for_explicit_identity_key():
    first = layer.canonical_entity_id(
        "tester", "site-a", "Asset", "Press 1001", "asset:1001",
        identity_key="AST-1001",
    )
    renamed = layer.canonical_entity_id(
        "tester", "site-a", "Asset", "Main Press", "asset:1001",
        identity_key="AST-1001",
    )
    different = layer.canonical_entity_id(
        "tester", "site-a", "Asset", "Main Press", "asset:1001",
        identity_key="AST-1002",
    )
    assert first == renamed
    assert first != different
