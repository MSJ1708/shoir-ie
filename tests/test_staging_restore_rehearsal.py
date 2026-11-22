from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.staging_restore_rehearsal import (
    load_objects,
    parse_utc,
    safe_object_path,
    validate_migration_history,
)


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


def test_validate_local_target_urls_accepts_only_supabase_local_ports() -> None:
    from scripts.staging_restore_rehearsal import validate_local_target_urls

    validate_local_target_urls(
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        "http://127.0.0.1:54321",
    )


@pytest.mark.parametrize(
    ("db_url", "api_url"),
    [
        ("postgresql://postgres:secret@db.example.supabase.co:5432/postgres", "http://127.0.0.1:54321"),
        ("postgresql://postgres:postgres@127.0.0.1:5432/postgres", "http://127.0.0.1:54321"),
        ("postgresql://postgres:postgres@127.0.0.1:54322/postgres", "https://shoir-ie-app.streamlit.app"),
    ],
)
def test_validate_local_target_urls_rejects_nonlocal_targets(
    db_url: str, api_url: str
) -> None:
    from scripts.staging_restore_rehearsal import validate_local_target_urls

    with pytest.raises(RuntimeError):
        validate_local_target_urls(db_url, api_url)


def test_validate_migration_history_requires_exact_version_and_name_match(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "20261025164602_refresh_refund_policy.sql").write_text(
        "-- migration\n", encoding="utf-8"
    )
    (migration_dir / "20261107120637_shoir_organization_workspaces.sql").write_text(
        "-- migration\n", encoding="utf-8"
    )
    history = [
        {"version": "20261025164602", "name": "refresh_refund_policy"},
        {"version": "20261107120637", "name": "shoir_organization_workspaces"},
    ]

    result = validate_migration_history(history, migration_dir, expected_count=2)

    assert result == {
        "migration_history_count": 2,
        "repository_migration_file_count": 2,
        "migration_history_matches_repository": True,
    }


def test_validate_migration_history_rejects_missing_or_extra_sql_files(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "20261025164602_refresh_refund_policy.sql").write_text(
        "-- migration\n", encoding="utf-8"
    )
    history = [
        {"version": "20261025164602", "name": "refresh_refund_policy"},
        {"version": "20261107120637", "name": "shoir_organization_workspaces"},
    ]

    with pytest.raises(RuntimeError, match="does not exactly match"):
        validate_migration_history(history, migration_dir, expected_count=2)


def test_validate_migration_history_rejects_filename_name_mismatch(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "20261025164602_wrong_name.sql").write_text(
        "-- migration\n", encoding="utf-8"
    )
    history = [{"version": "20261025164602", "name": "actual_name"}]

    with pytest.raises(RuntimeError, match="name_mismatch"):
        validate_migration_history(history, migration_dir, expected_count=1)


def test_validate_migration_history_rejects_duplicate_ledger_versions(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "20261025164602_refresh_refund_policy.sql").write_text(
        "-- migration\n", encoding="utf-8"
    )
    history = [
        {"version": "20261025164602", "name": "refresh_refund_policy"},
        {"version": "20261025164602", "name": "refresh_refund_policy"},
    ]

    with pytest.raises(RuntimeError, match="Duplicate source migration"):
        validate_migration_history(history, migration_dir, expected_count=2)
