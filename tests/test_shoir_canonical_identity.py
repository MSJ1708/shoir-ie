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
    monkeypatch.setattr(layer, "APP_ENVIRONMENT", "local")
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


def test_canonical_identity_lookup_fails_closed_on_case_insensitive_duplicate_legacy_alias(tmp_path, monkeypatch):
    database_path = str(tmp_path / "canonical-identity-duplicates.db")
    monkeypatch.setattr(layer, "DEFAULT_DB", database_path)
    monkeypatch.setattr(layer, "_remote", lambda: False)
    monkeypatch.setattr(layer, "APP_ENVIRONMENT", "local")
    layer.ensure_enterprise_schema()
    workspace_id = layer.workspace_key("tester", "site-a")
    stamp = layer.now_iso()

    with layer._local_connect() as conn:
        for entity_id, legacy_name in (
            ("CEN-LEGACY-1", "Press 1001"),
            ("CEN-LEGACY-2", "press 1001"),
        ):
            conn.execute(
                """INSERT INTO shoir_ent_canonical_entities
                (entity_id,workspace_id,entity_type,name,source,status,state_json,
                 content_hash,created_by,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entity_id, workspace_id, "Asset", legacy_name,
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


def test_staging_canonical_identity_uses_managed_records_across_rename(monkeypatch):
    records = [{
        "entity_key": "CEN-LEGACY-1001",
        "payload_json": {
            "entity_id": "CEN-LEGACY-1001",
            "entity_type": "Asset",
            "name": "Press 1001",
            "source": "asset:1001",
            "status": "Observed",
            "state_json": {"legacy_record": True},
        },
    }]
    saves = []
    monkeypatch.setattr(layer, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        layer, "_staging_platform_list",
        lambda *args, **kwargs: list(records),
    )
    def save(username, workspace, record_type, entity_key, payload):
        saves.append((record_type, entity_key, payload))
        records[:] = [{
            "entity_key": entity_key,
            "payload_json": payload,
            "content_hash": payload.get("content_hash", ""),
            "version": 2,
            "created_at": "2026-11-04T00:00:00Z",
            "updated_at": "2026-11-04T01:00:00Z",
        }]
        return {"ok": True}
    monkeypatch.setattr(layer, "_staging_platform_save", save)
    monkeypatch.setattr(
        layer, "ensure_enterprise_schema",
        lambda *args, **kwargs: pytest.fail("staging must not fall back to local schema"),
    )

    first = layer.upsert_canonical_entity(
        "synthetic-user", "Asset", "Main Press", "asset:1001",
        state={"thread_node_id": "AST-LEGACY-1001", "metadata": {"name_aliases": ["Press 1001"]}},
        workspace="site-a",
    )
    second = layer.upsert_canonical_entity(
        "synthetic-user", "Asset", "Main Press Assembly", "asset:1001",
        state={"thread_node_id": "AST-LEGACY-1001", "metadata": {"name_aliases": ["Press 1001", "Main Press"]}},
        workspace="site-a",
    )
    assert first == "CEN-LEGACY-1001"
    assert second == first
    assert len(saves) == 2
    assert all(save[0] == "canonical_entity" for save in saves)
    assert all(save[1] == first for save in saves)
    assert saves[-1][2]["name"] == "Main Press Assembly"


def test_staging_canonical_identity_fails_closed_on_ambiguous_alias(monkeypatch):
    records = [
        {"entity_key": "CEN-LEGACY-1", "payload_json": {
            "entity_id": "CEN-LEGACY-1", "entity_type": "Asset",
            "name": "Press 1001", "source": "asset:1001",
            "state_json": {"legacy_record": True},
        }},
        {"entity_key": "CEN-LEGACY-2", "payload_json": {
            "entity_id": "CEN-LEGACY-2", "entity_type": "Asset",
            "name": "press 1001", "source": "asset:1001",
            "state_json": {"legacy_record": True},
        }},
    ]
    monkeypatch.setattr(layer, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(layer, "_staging_platform_list", lambda *args, **kwargs: records)
    monkeypatch.setattr(
        layer, "_staging_platform_save",
        lambda *args, **kwargs: pytest.fail("ambiguous identity must not write"),
    )
    with pytest.raises(RuntimeError, match="Legacy display name maps to multiple"):
        layer.upsert_canonical_entity(
            "synthetic-user", "Asset", "Main Press", "asset:1001",
            state={"thread_node_id": "AST-1001", "metadata": {"name_aliases": ["Press 1001"]}},
            workspace="site-a",
        )
