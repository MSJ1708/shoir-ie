from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.staging_restore_rehearsal import load_objects, parse_utc, safe_object_path


def test_safe_object_path_resolves_nested_storage_key(tmp_path: Path) -> None:
    result = safe_object_path(tmp_path, "private-bucket", "folder/image.jpg")
    assert result == (tmp_path / "private-bucket" / "folder" / "image.jpg").resolve()


@pytest.mark.parametrize(
    ("bucket", "name"),
    [
        ("../escape", "file.bin"),
        ("bucket", "../escape.bin"),
        ("bucket", "folder/../../escape.bin"),
        ("bucket", "/absolute.bin"),
        ("bucket", "folder\\\\escape.bin"),
    ],
)
def test_safe_object_path_rejects_path_traversal(
    tmp_path: Path, bucket: str, name: str
) -> None:
    with pytest.raises(ValueError):
        safe_object_path(tmp_path, bucket, name)


def test_load_objects_reads_ndjson_and_skips_blank_lines(tmp_path: Path) -> None:
    manifest = tmp_path / "objects.ndjson"
    manifest.write_text(
        json.dumps({"bucket_id": "private", "name": "one.bin"})
        + "\n\n"
        + json.dumps({"bucket_id": "private", "name": "two.bin"})
        + "\n",
        encoding="utf-8",
    )
    rows = load_objects(manifest)
    assert rows == [
        {"bucket_id": "private", "name": "one.bin"},
        {"bucket_id": "private", "name": "two.bin"},
    ]


def test_load_objects_rejects_invalid_json(tmp_path: Path) -> None:
    manifest = tmp_path / "objects.ndjson"
    manifest.write_text('{"name": "good"}\nnot-json\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        load_objects(manifest)


def test_parse_utc_requires_timezone_and_normalizes() -> None:
    parsed = parse_utc("2026-11-22T12:00:00+03:00")
    assert parsed.isoformat() == "2026-11-22T09:00:00+00:00"
    with pytest.raises(ValueError, match="timezone"):
        parse_utc("2026-11-22T12:00:00")
