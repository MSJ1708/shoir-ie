from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.shoir_storage_recovery_manifest import (
    ManifestError,
    create_manifest,
    verify_manifest,
)


def test_manifest_creates_and_verifies_exported_storage_bytes(tmp_path):
    export_root = tmp_path / "export"
    (export_root / "workspace-a" / "dataset-1").mkdir(parents=True)
    (export_root / "workspace-a" / "dataset-1" / "one.csv").write_bytes(b"id,value\nA-1,10\n")
    (export_root / "workspace-b").mkdir()
    (export_root / "workspace-b" / "empty.csv").write_bytes(b"")

    manifest_path = tmp_path / "evidence" / "storage-manifest.json"
    created = create_manifest(export_root, manifest_path)
    assert created["status"] == "MANIFEST_CREATED"
    assert created["object_count"] == 2
    assert created["total_bytes"] == len(b"id,value\nA-1,10\n")
    assert manifest_path.exists()

    verified = verify_manifest(export_root, manifest_path)
    assert verified["status"] == "RESTORE_BYTES_VERIFIED"
    assert verified["verified"] is True
    assert verified["missing_paths"] == []
    assert verified["extra_paths"] == []
    assert verified["changed_paths"] == []


def test_manifest_reports_missing_extra_and_changed_storage_objects(tmp_path):
    export_root = tmp_path / "backup"
    export_root.mkdir()
    (export_root / "same.csv").write_bytes(b"before")
    (export_root / "missing.csv").write_bytes(b"will be missing")
    manifest_path = tmp_path / "storage-manifest.json"
    create_manifest(export_root, manifest_path)

    (export_root / "same.csv").write_bytes(b"after")
    (export_root / "missing.csv").unlink()
    (export_root / "extra.csv").write_bytes(b"unexpected")
    result = verify_manifest(export_root, manifest_path)
    assert result["verified"] is False
    assert result["missing_paths"] == ["missing.csv"]
    assert result["extra_paths"] == ["extra.csv"]
    assert result["changed_paths"] == ["same.csv"]


def test_manifest_rejects_tampered_manifest_and_unsafe_object_path(tmp_path):
    export_root = tmp_path / "export"
    export_root.mkdir()
    (export_root / "one.csv").write_bytes(b"one")
    manifest_path = tmp_path / "manifest.json"
    create_manifest(export_root, manifest_path)

    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["objects"][0]["path"] = "../outside.csv"
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ManifestError, match="unsafe"):
        verify_manifest(export_root, manifest_path)


def test_manifest_refuses_symbolic_links_when_supported(tmp_path):
    export_root = tmp_path / "export"
    export_root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_bytes(b"not part of the export")
    link = export_root / "linked.csv"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available on this runner.")
    with pytest.raises(ManifestError, match="symbolic-link"):
        create_manifest(export_root, tmp_path / "manifest.json")


def test_manifest_must_be_written_outside_object_directory(tmp_path):
    export_root = tmp_path / "export"
    export_root.mkdir()
    with pytest.raises(ManifestError, match="outside"):
        create_manifest(export_root, export_root / "manifest.json")


def test_manifest_detects_manifest_metadata_tampering(tmp_path):
    export_root = tmp_path / "export"
    export_root.mkdir()
    (export_root / "one.csv").write_bytes(b"one")
    manifest_path = tmp_path / "manifest.json"
    create_manifest(export_root, manifest_path)

    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["total_bytes"] += 1
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ManifestError, match="total_bytes"):
        verify_manifest(export_root, manifest_path)
