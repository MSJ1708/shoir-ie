#!/usr/bin/env python3
"""Restore a Shoir-IE staging backup into an ephemeral local Supabase stack.

This utility is intentionally limited to a disposable local target. It restores
application schemas/data, bucket metadata, Storage policies, and object bytes.
It never connects to the hosted staging or production database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg2
import requests
from psycopg2 import sql
from psycopg2.extras import Json

EXPECTED_PROJECT_REF = "hfhrosthswcybccepmak"
ALLOWED_POLICY_COMMANDS = {"ALL", "SELECT", "INSERT", "UPDATE", "DELETE"}
ALLOWED_POLICY_MODES = {"PERMISSIVE", "RESTRICTIVE"}
REQUIRED_ARCHIVE_FILES = {
    "roles.sql", "schema.sql", "data.sql", "storage-buckets.json",
    "storage-objects.ndjson", "storage-policies.json", "app-table-counts.json",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Backup manifest timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc)


def safe_object_path(root: Path, bucket_id: str, object_name: str) -> Path:
    if not bucket_id or bucket_id in {".", ".."} or "/" in bucket_id or "\\" in bucket_id:
        raise ValueError("Invalid Storage bucket identifier in backup metadata.")
    if not object_name or object_name.startswith(("/", "\\")) or "\\" in object_name:
        raise ValueError("Invalid Storage object name in backup metadata.")
    parts = object_name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Unsafe path segment in Storage object metadata.")
    base = (root / bucket_id).resolve()
    target = (base / Path(*parts)).resolve()
    if base not in target.parents:
        raise ValueError("Storage object path escapes the restored bucket directory.")
    return target


def load_objects(path: Path) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid Storage object manifest line {line_number}.") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Storage object manifest line {line_number} is not an object.")
            objects.append(value)
    return objects


def db_connect(db_url: str):
    return psycopg2.connect(db_url)


def table_columns(cursor, schema: str, table: str) -> dict[str, str]:
    cursor.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def restore_buckets(conn, source_buckets: list[dict[str, Any]]) -> None:
    with conn.cursor() as cursor:
        columns = table_columns(cursor, "storage", "buckets")
    if not {"id", "name", "public"}.issubset(columns):
        raise RuntimeError("Local Storage buckets table is missing required columns.")

    # A bucket owner FK cannot be faithfully restored without Auth user rows.
    for bucket in source_buckets:
        if bucket.get("owner") or bucket.get("owner_id"):
            raise RuntimeError(
                "Source Storage bucket has a user owner, but Auth data is not present "
                "in the staging backup. Refusing to lose ownership metadata."
            )

    for source in source_buckets:
        selected = {
            key: value
            for key, value in source.items()
            if key in columns and key not in {"owner", "owner_id"}
        }
        if not {"id", "name", "public"}.issubset(selected):
            raise RuntimeError("Source Storage bucket metadata is incomplete.")
        names = list(selected)
        values = []
        for name in names:
            value = selected[name]
            if columns[name] in {"json", "jsonb"}:
                value = Json(value)
            values.append(value)
        insert = sql.SQL("INSERT INTO storage.buckets ({}) VALUES ({})").format(
            sql.SQL(", ").join(map(sql.Identifier, names)),
            sql.SQL(", ").join(sql.Placeholder() for _ in names),
        )
        update_names = [name for name in names if name != "id"]
        if update_names:
            update = sql.SQL(" ON CONFLICT (id) DO UPDATE SET {}").format(
                sql.SQL(", ").join(
                    sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(name), sql.Identifier(name))
                    for name in update_names
                )
            )
        else:
            update = sql.SQL(" ON CONFLICT (id) DO NOTHING")
        with conn.cursor() as cursor:
            cursor.execute(insert + update, values)
    conn.commit()


def restore_storage_policies(conn, policies: list[dict[str, Any]]) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'storage'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}

    for policy in policies:
        schema = policy.get("schemaname")
        table = policy.get("tablename")
        policy_name = policy.get("policyname")
        command = str(policy.get("cmd", "")).upper()
        mode = str(policy.get("permissive", "PERMISSIVE")).upper()
        if schema != "storage" or table not in existing_tables:
            raise RuntimeError("Backup contains a Storage policy for an unavailable target table.")
        if not isinstance(policy_name, str) or not policy_name or len(policy_name) > 255:
            raise RuntimeError("Invalid Storage policy name in backup metadata.")
        if command not in ALLOWED_POLICY_COMMANDS or mode not in ALLOWED_POLICY_MODES:
            raise RuntimeError("Unsupported Storage policy command or mode.")

        roles = policy.get("roles", [])
        if isinstance(roles, str):
            roles = [r.strip() for r in roles.strip("{}").split(",") if r.strip()]
        if not isinstance(roles, list) or not roles or any(not isinstance(r, str) for r in roles):
            raise RuntimeError("Invalid Storage policy role list.")
        role_sql = [
            sql.SQL("PUBLIC") if role.lower() == "public" else sql.Identifier(role)
            for role in roles
        ]

        qual = policy.get("qual")
        with_check = policy.get("with_check")
        for expression in (qual, with_check):
            if expression is not None and (
                not isinstance(expression, str)
                or ";" in expression
                or "--" in expression
                or "/*" in expression
                or "*/" in expression
            ):
                raise RuntimeError("Storage policy contains an unsupported SQL expression.")

        statement = sql.SQL(
            "DROP POLICY IF EXISTS {name} ON storage.{table}; "
            "CREATE POLICY {name} ON storage.{table} AS {mode} "
            "FOR {command} TO {roles}"
        ).format(
            name=sql.Identifier(policy_name),
            table=sql.Identifier(table),
            mode=sql.SQL(mode),
            command=sql.SQL(command),
            roles=sql.SQL(", ").join(role_sql),
        )
        if qual is not None:
            statement += sql.SQL(" USING ({})").format(sql.SQL(qual))
        if with_check is not None:
            statement += sql.SQL(" WITH CHECK ({})").format(sql.SQL(with_check))
        with conn.cursor() as cursor:
            cursor.execute(statement)
    conn.commit()


def upload_and_verify_objects(
    session: requests.Session,
    api_url: str,
    service_role_key: str,
    plain_storage_root: Path,
    objects: list[dict[str, Any]],
) -> tuple[int, int]:
    base_headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "x-upsert": "true",
    }
    uploaded = 0
    verified_bytes = 0

    for item in objects:
        bucket = item.get("bucket_id")
        name = item.get("name")
        if not isinstance(bucket, str) or not isinstance(name, str):
            raise RuntimeError("Storage object metadata is missing bucket_id or name.")
        source_path = safe_object_path(plain_storage_root, bucket, name)
        if not source_path.is_file():
            raise RuntimeError("An object listed in the backup is missing from the decrypted copy.")
        expected_metadata = item.get("metadata") or {}
        if not isinstance(expected_metadata, dict):
            raise RuntimeError("Storage object metadata is malformed.")
        expected_size = expected_metadata.get("size")
        if expected_size is not None and int(expected_size) != source_path.stat().st_size:
            raise RuntimeError("Storage object size differs from its source-time metadata.")

        content_type = expected_metadata.get("mimetype") or "application/octet-stream"
        object_url = f"{api_url.rstrip('/')}/storage/v1/object/{quote(bucket, safe='')}/{quote(name, safe='/')}"
        headers = {**base_headers, "Content-Type": str(content_type)}
        with source_path.open("rb") as handle:
            response = session.post(object_url, headers=headers, data=handle, timeout=(15, 600))
        if response.status_code not in {200, 201}:
            raise RuntimeError(f"Local Storage upload failed with HTTP {response.status_code}.")

        source_hash = hashlib.sha256()
        source_size = 0
        with source_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                source_hash.update(chunk)
                source_size += len(chunk)

        download = session.get(
            object_url,
            headers={k: v for k, v in base_headers.items() if k != "x-upsert"},
            stream=True,
            timeout=(15, 600),
        )
        if download.status_code != 200:
            raise RuntimeError(
                f"Local Storage verification download failed with HTTP {download.status_code}."
            )
        restored_hash = hashlib.sha256()
        restored_size = 0
        for chunk in download.iter_content(chunk_size=1024 * 1024):
            if chunk:
                restored_hash.update(chunk)
                restored_size += len(chunk)
        download.close()

        if source_size != restored_size or source_hash.digest() != restored_hash.digest():
            raise RuntimeError("Restored Storage object bytes do not match the decrypted backup.")
        uploaded += 1
        verified_bytes += restored_size

    return uploaded, verified_bytes


def smoke_test_local_auth(
    session: requests.Session, api_url: str, anon_key: str, service_key: str, db_url: str
) -> None:
    email = f"restore-smoke-{uuid.uuid4().hex}@example.invalid"
    password = secrets.token_urlsafe(32)
    admin_headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    anon_headers = {"apikey": anon_key, "Authorization": f"Bearer {anon_key}"}
    user_id = None
    try:
        create = session.post(
            f"{api_url.rstrip('/')}/auth/v1/admin/users",
            headers=admin_headers,
            json={"email": email, "password": password, "email_confirm": True},
            timeout=30,
        )
        if create.status_code not in {200, 201}:
            raise RuntimeError(f"Local Auth test-user creation failed with HTTP {create.status_code}.")
        user_id = create.json().get("id")
        if not user_id:
            raise RuntimeError("Local Auth did not return the synthetic test-user ID.")
        login = session.post(
            f"{api_url.rstrip('/')}/auth/v1/token?grant_type=password",
            headers=anon_headers,
            json={"email": email, "password": password},
            timeout=30,
        )
        if login.status_code != 200 or login.json().get("user", {}).get("id") != user_id:
            raise RuntimeError("Local Auth synthetic-user login test failed.")
    finally:
        if user_id:
            deleted = session.delete(
                f"{api_url.rstrip('/')}/auth/v1/admin/users/{quote(str(user_id), safe='')}",
                headers=admin_headers,
                timeout=30,
            )
            if deleted.status_code not in {200, 204}:
                raise RuntimeError("Could not remove the local synthetic Auth test user.")
    with db_connect(db_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM auth.users")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("The local Auth smoke test left user data behind.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-dir", required=True, type=Path)
    parser.add_argument("--plain-storage-dir", required=True, type=Path)
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--anon-key", required=True)
    parser.add_argument("--service-role-key", required=True)
    parser.add_argument("--evidence-out", required=True, type=Path)
    args = parser.parse_args()

    missing = sorted(
        name for name in REQUIRED_ARCHIVE_FILES if not (args.recovery_dir / name).is_file()
    )
    if missing:
        raise RuntimeError(
            f"Decrypted recovery archive is missing required files: {', '.join(missing)}"
        )

    manifest = json.loads(
        (args.recovery_dir / "backup-manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("project_ref") != EXPECTED_PROJECT_REF:
        raise RuntimeError("Backup manifest is not for the fixed Shoir-IE staging project.")
    if manifest.get("auth_data_exported") is not False or manifest.get("auth_non_migration_rows") != 0:
        raise RuntimeError("Backup manifest does not prove the zero-row Auth guard passed.")
    if manifest.get("storage_bucket_count") is None or manifest.get("storage_object_metadata_count") is None:
        raise RuntimeError("Backup manifest is missing Storage inventory counts.")

    started_at = utc_now()
    backup_at = parse_utc(manifest["created_at_utc"])
    rpo_seconds = max(0.0, (started_at - backup_at).total_seconds())
    source_buckets = json.loads(
        (args.recovery_dir / "storage-buckets.json").read_text(encoding="utf-8")
    )
    source_policies = json.loads(
        (args.recovery_dir / "storage-policies.json").read_text(encoding="utf-8")
    )
    source_objects = load_objects(args.recovery_dir / "storage-objects.ndjson")
    source_table_counts = json.loads(
        (args.recovery_dir / "app-table-counts.json").read_text(encoding="utf-8")
    )
    if not isinstance(source_buckets, list) or not isinstance(source_policies, list):
        raise RuntimeError("Storage metadata exports must be JSON arrays.")
    if len(source_buckets) != int(manifest["storage_bucket_count"]):
        raise RuntimeError("Storage bucket metadata count does not match the backup manifest.")
    if len(source_objects) != int(manifest["storage_object_metadata_count"]):
        raise RuntimeError("Storage object metadata count does not match the backup manifest.")
    if not isinstance(source_table_counts, dict) or not source_table_counts:
        raise RuntimeError("Application table row-count manifest is empty or invalid.")

    # Only a local DB connection is supplied by the workflow. No remote project
    # URL or service credential for the hosted staging/production projects is accepted.
    with db_connect(args.db_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_setting('server_version_num')")
            database_name, server_version_num = cursor.fetchone()
            if database_name != "postgres":
                raise RuntimeError("Restore target is not the disposable local postgres database.")
            if int(server_version_num) < 170000:
                raise RuntimeError("Restore target PostgreSQL major version is older than source PostgreSQL 17.")
        restore_buckets(conn, source_buckets)
        restore_storage_policies(conn, source_policies)

        for qualified_name, expected_count in source_table_counts.items():
            if not isinstance(qualified_name, str) or qualified_name.count(".") != 1:
                raise RuntimeError("Invalid application table key in backup manifest.")
            schema_name, table_name = qualified_name.split(".", 1)
            if schema_name not in {"public", "shoir_internal"}:
                raise RuntimeError("Backup row-count manifest references an unexpected schema.")
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT count(*) FROM {}.{}").format(
                        sql.Identifier(schema_name), sql.Identifier(table_name)
                    )
                )
                actual_count = cursor.fetchone()[0]
            if actual_count != int(expected_count):
                raise RuntimeError(f"Restored row count mismatch for {qualified_name}.")

        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM storage.buckets")
            restored_bucket_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'storage'")
            restored_policy_count = cursor.fetchone()[0]
        if restored_bucket_count != len(source_buckets):
            raise RuntimeError("Restored Storage bucket count does not match source.")
        if restored_policy_count != len(source_policies):
            raise RuntimeError("Restored Storage policy count does not match source.")

    session = requests.Session()
    uploaded_count, verified_bytes = upload_and_verify_objects(
        session, args.api_url, args.service_role_key, args.plain_storage_dir, source_objects
    )
    if uploaded_count != len(source_objects):
        raise RuntimeError("Not every source Storage object was restored.")

    with db_connect(args.db_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM storage.objects")
            restored_object_count = cursor.fetchone()[0]
            if restored_object_count != len(source_objects):
                raise RuntimeError("Restored Storage object metadata count does not match source.")
            cursor.execute("SELECT count(*) FROM auth.users")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("Backup restore unexpectedly populated Auth users despite zero-row guard.")

    smoke_test_local_auth(session, args.api_url, args.anon_key, args.service_role_key, args.db_url)

    finished_at = utc_now()
    evidence = {
        "result": "PASS",
        "target": "ephemeral-local-supabase",
        "source_project_ref": EXPECTED_PROJECT_REF,
        "database_name": "postgres",
        "postgres_major_version": 17,
        "application_table_count": len(source_table_counts),
        "storage_bucket_count": restored_bucket_count,
        "storage_policy_count": restored_policy_count,
        "storage_object_count": restored_object_count,
        "storage_objects_uploaded_and_sha256_verified": uploaded_count,
        "storage_object_bytes_sha256_verified": verified_bytes,
        "auth_data_exported": False,
        "auth_non_migration_source_rows": 0,
        "local_auth_synthetic_login": "PASS",
        "local_auth_test_user_removed": True,
        "backup_created_at_utc": backup_at.isoformat(),
        "restore_started_at_utc": started_at.isoformat(),
        "restore_completed_at_utc": finished_at.isoformat(),
        "rpo_seconds": round(rpo_seconds, 3),
        "rto_seconds": round((finished_at - started_at).total_seconds(), 3),
    }
    args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_out.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RESTORE REHEARSAL FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
