"""Regression tests for managed staging persistence wiring in the enterprise layer."""
import json
import pandas as pd
import pytest

import shoir_enterprise_layer as enterprise


def test_canonical_entity_upsert_uses_managed_staging_record_and_skips_sqlite(monkeypatch):
    calls = []
    monkeypatch.setattr(
        enterprise, "_staging_platform_save",
        lambda *args: calls.append(args) or {"ok": True},
    )
    monkeypatch.setattr(
        enterprise, "ensure_enterprise_schema",
        lambda *args, **kwargs: pytest.fail("staging path must not create process-local schema"),
    )
    entity_id = enterprise.upsert_canonical_entity(
        "synthetic-user", "Asset", "Press 100", source="source-id:press-100",
        state={"capacity_tph": 15.5}, workspace="plant-a",
    )
    assert entity_id.startswith("CEN-")
    assert calls[0][2] == "canonical_entity"
    assert calls[0][3] == entity_id
    assert calls[0][4]["entity_type"] == "Asset"
    assert calls[0][4]["state_json"] == {"capacity_tph": 15.5}


def test_canonical_entity_read_uses_scoped_managed_records(monkeypatch):
    monkeypatch.setattr(
        enterprise, "_staging_platform_list",
        lambda *args, **kwargs: [{
            "entity_key": "CEN-1",
            "payload_json": {
                "entity_type": "Asset", "name": "Press 100", "source": "asset:100",
                "status": "Observed", "state_json": {"capacity_tph": 15.5},
                "created_by": "synthetic-user",
            },
            "content_hash": "a" * 64, "version": 2,
            "created_at": "2026-11-04T00:00:00Z", "updated_at": "2026-11-04T01:00:00Z",
        }],
    )
    monkeypatch.setattr(
        enterprise, "ensure_enterprise_schema",
        lambda *args, **kwargs: pytest.fail("staging read must not query local SQLite"),
    )
    frame = enterprise.canonical_entities_frame("synthetic-user", "plant-a", limit=100)
    assert len(frame) == 1
    assert frame.iloc[0]["entity_key"] == "CEN-1"
    assert frame.iloc[0]["name"] == "Press 100"
    assert frame.iloc[0]["version"] == 2


def test_artifact_list_uses_workspace_scoped_managed_records(monkeypatch):
    monkeypatch.setattr(
        enterprise, "_staging_platform_list",
        lambda *args, **kwargs: [{
            "entity_key": "ART-1",
            "payload_json": {"artifact_type": "report", "name": "capacity", "payload": {"rows": 12}},
            "content_hash": "b" * 64, "version": 1,
            "created_at": "2026-11-04T00:00:00Z", "updated_at": "2026-11-04T00:00:00Z",
        }],
    )
    monkeypatch.setattr(
        enterprise, "ensure_enterprise_schema",
        lambda *args, **kwargs: pytest.fail("staging read must not query local SQLite"),
    )
    frame = enterprise.list_artifacts("synthetic-user", "report", "plant-a", 100)
    assert len(frame) == 1
    assert frame.iloc[0]["artifact_id"] == "ART-1"
    assert frame.iloc[0]["artifact_type"] == "report"


def test_staging_job_update_loads_exact_job_then_saves_version(monkeypatch):
    reads, writes = [], []
    monkeypatch.setattr(
        enterprise, "_staging_platform_list",
        lambda *args, **kwargs: reads.append((args, kwargs)) or [{
            "entity_key": "JOB-1",
            "payload_json": {"job_id": "JOB-1", "status": "Running", "progress": 10},
        }],
    )
    monkeypatch.setattr(
        enterprise, "_staging_platform_save",
        lambda *args: writes.append(args) or {"ok": True},
    )
    monkeypatch.setattr(
        enterprise, "ensure_enterprise_schema",
        lambda *args, **kwargs: pytest.fail("staging update must not update process-local SQLite"),
    )
    enterprise.update_job_record(
        "synthetic-user", "JOB-1", status="Completed", progress=100,
        result={"rows": 5}, workspace="plant-a",
    )
    assert reads[0][1]["entity_key"] == "JOB-1"
    assert writes[0][2] == "job"
    assert writes[0][3] == "JOB-1"
    assert writes[0][4]["status"] == "Completed"
    assert writes[0][4]["progress"] == 100
    assert writes[0][4]["finished_at"]


def test_staging_knowledge_document_rejects_size_over_edge_payload_limit(monkeypatch):
    monkeypatch.setattr(enterprise, "_staging_platform_identity", lambda username: ("synthetic-user", "session"))
    monkeypatch.setattr(
        enterprise, "_staging_platform_save",
        lambda *args: pytest.fail("oversize content must not be sent or truncated"),
    )
    with pytest.raises(ValueError, match="200 KiB"):
        enterprise.add_knowledge_document(
            "synthetic-user", "large-doc", "x" * (201 * 1024), workspace="plant-a"
        )
