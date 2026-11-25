#!/usr/bin/env python3
"""Restore a Shoir-IE staging backup into an ephemeral local Supabase stack.

This utility is intentionally limited to a disposable local target. It restores
application schemas/data, bucket metadata, Storage policies, and object bytes.
It never connects to the hosted staging or production database.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

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
    "database-contract.json", "migration-history.json",
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


def validate_local_target_urls(db_url: str, api_url: str) -> None:
    parsed_db = urlparse(db_url)
    if (
        parsed_db.scheme not in {"postgres", "postgresql"}
        or parsed_db.hostname not in {"127.0.0.1", "localhost"}
        or parsed_db.port != 54322
        or parsed_db.path.rstrip("/") != "/postgres"
    ):
        raise RuntimeError("Refusing any database target other than the disposable local Supabase PostgreSQL listener.")
    parsed_api = urlparse(api_url)
    if (
        parsed_api.scheme != "http"
        or parsed_api.hostname not in {"127.0.0.1", "localhost"}
        or parsed_api.port != 54321
    ):
        raise RuntimeError("Refusing any API target other than the disposable local Supabase API listener.")


def db_connect(db_url: str):
    return psycopg2.connect(db_url)


def database_contract(conn) -> dict[str, int]:
    queries = {
        "rls_table_count": """
            SELECT count(*) FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('public', 'shoir_internal')
              AND c.relkind = 'r' AND c.relrowsecurity
        """,
        "policy_count": "SELECT count(*) FROM pg_policies WHERE schemaname IN ('public', 'shoir_internal')",
        "constraint_count": """
            SELECT count(*) FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname IN ('public', 'shoir_internal')
        """,
        "function_count": """
            SELECT count(*) FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname IN ('public', 'shoir_internal') AND p.prokind IN ('f', 'p')
        """,
        "table_grant_count": """
            SELECT count(*) FROM information_schema.role_table_grants
            WHERE table_schema IN ('public', 'shoir_internal')
        """,
        "routine_grant_count": """
            SELECT count(*) FROM information_schema.routine_privileges
            WHERE specific_schema IN ('public', 'shoir_internal')
        """,
    }
    values: dict[str, int] = {}
    with conn.cursor() as cursor:
        for key, query in queries.items():
            cursor.execute(query)
            values[key] = int(cursor.fetchone()[0])
    return values


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


def normalize_bucket_config(row: dict[str, Any]) -> dict[str, Any]:
    allowed = row.get("allowed_mime_types")
    if allowed is not None and not isinstance(allowed, list):
        raise RuntimeError("Storage bucket allowed_mime_types is malformed.")
    limit = row.get("file_size_limit")
    return {
        "id": str(row.get("id", "")),
        "name": str(row.get("name", "")),
        "public": bool(row.get("public", False)),
        "file_size_limit": None if limit is None else int(limit),
        "allowed_mime_types": None if allowed is None else sorted(str(item) for item in allowed),
    }


def validate_storage_object_inventory(
    source_objects: list[dict[str, Any]],
    restored_rows: list[tuple[str, str, Any]],
) -> None:
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for item in source_objects:
        bucket = item.get("bucket_id")
        name = item.get("name")
        metadata = item.get("metadata") or {}
        if not isinstance(bucket, str) or not isinstance(name, str) or not isinstance(metadata, dict):
            raise RuntimeError("Source Storage object inventory contains malformed metadata.")
        key = (bucket, name)
        if key in expected:
            raise RuntimeError("Source Storage object inventory contains duplicate object keys.")
        expected[key] = metadata

    restored: dict[tuple[str, str], Any] = {}
    for bucket, name, metadata in restored_rows:
        key = (str(bucket), str(name))
        if key in restored:
            raise RuntimeError("Restored Storage object inventory contains duplicate object keys.")
        restored[key] = metadata if isinstance(metadata, dict) else {}

    missing = sorted(set(expected) - set(restored))
    extra = sorted(set(restored) - set(expected))
    if missing or extra:
        raise RuntimeError(
            f"Restored Storage object key set differs from source (missing={missing}, extra={extra})."
        )

    for key, source_metadata in expected.items():
        target_metadata = restored[key]
        for field in ("size", "mimetype", "cacheControl"):
            expected_value = source_metadata.get(field)
            if expected_value is None:
                continue
            actual_value = target_metadata.get(field)
            if field == "size":
                expected_value = int(expected_value)
                actual_value = None if actual_value is None else int(actual_value)
            else:
                expected_value = str(expected_value)
                actual_value = None if actual_value is None else str(actual_value)
            if actual_value != expected_value:
                raise RuntimeError(
                    f"Restored Storage object {key[0]}/{key[1]} metadata mismatch for {field}."
                )


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

        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP POLICY IF EXISTS {} ON storage.{}").format(
                    sql.Identifier(policy_name), sql.Identifier(table)
                )
            )
            statement = sql.SQL(
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
        cache_control = expected_metadata.get("cacheControl")
        if cache_control is not None:
            headers["Cache-Control"] = str(cache_control)
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


def smoke_test_shoir_identity(
    session: requests.Session,
    api_url: str,
    anon_key: str,
    service_key: str,
    db_url: str,
) -> None:
    """Exercise the real Shoir-IE persistence login/session/workspace path locally."""
    username_lc = f"restore-{uuid.uuid4().hex[:16]}"
    username = username_lc
    password = secrets.token_urlsafe(32)
    salt_hex = secrets.token_hex(16)
    password_hash = salt_hex + "$" + hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        200_000,
        dklen=32,
    ).hex()
    throttle_hash = hmac.new(
        service_key.encode("utf-8"),
        ("user:" + username_lc).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    marker = {"restore_rehearsal": "passed", "probe_id": uuid.uuid4().hex}
    endpoint = f"{api_url.rstrip('/')}/functions/v1/shoir-persistence"
    headers = {"apikey": anon_key, "Content-Type": "application/json"}
    token: str | None = None

    with db_connect(db_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.shoir_accounts
                    (username, username_lc, password_hash, role, tier, email,
                     created_at, subscription_expires_at, active, updated_at)
                VALUES (%s, %s, %s, 'User', 'Enterprise Tier ($199)', %s,
                        now(), '2099-01-01T00:00:00Z', true, now())
                """,
                (username, username_lc, password_hash, f"{username_lc}@example.invalid"),
            )
        conn.commit()

    def call(action: str, **extra: Any) -> tuple[requests.Response, dict[str, Any]]:
        response = session.post(
            endpoint,
            headers=headers,
            json={"action": action, "username": username, **extra},
            timeout=(10, 60),
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Shoir-IE local persistence action {action} returned non-JSON HTTP {response.status_code}."
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Shoir-IE local persistence action {action} returned an invalid response.")
        return response, payload

    try:
        login_response, login = call("login", password=password)
        if login_response.status_code != 200 or login.get("ok") is not True:
            raise RuntimeError("Shoir-IE custom account login failed in local restore rehearsal.")
        token_value = login.get("token")
        if not isinstance(token_value, str) or len(token_value) < 32:
            raise RuntimeError("Shoir-IE custom login did not return a valid session token.")
        token = token_value

        entitlement_response, entitlement = call("session_entitlement", token=token)
        if (
            entitlement_response.status_code != 200
            or entitlement.get("ok") is not True
            or entitlement.get("username") != username
            or entitlement.get("active") is not True
        ):
            raise RuntimeError("Shoir-IE local session entitlement validation failed.")

        save_response, saved = call("workspace_save", token=token, state_json=marker)
        if save_response.status_code != 200 or saved.get("ok") is not True:
            raise RuntimeError("Shoir-IE local workspace save failed.")

        load_response, loaded = call("workspace_load", token=token)
        restored_state = loaded.get("state_json")
        if isinstance(restored_state, str):
            try:
                restored_state = json.loads(restored_state)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Shoir-IE local workspace state was not valid JSON.") from exc
        if (
            load_response.status_code != 200
            or loaded.get("ok") is not True
            or restored_state != marker
        ):
            raise RuntimeError("Shoir-IE local workspace load did not return the saved probe state.")

        logout_response, logout = call("logout", token=token)
        if logout_response.status_code != 200 or logout.get("ok") is not True or logout.get("revoked") is not True:
            raise RuntimeError("Shoir-IE local logout did not revoke the synthetic session.")

        stale_response, stale = call("workspace_load", token=token)
        if stale_response.status_code != 401 or stale.get("error") != "Unauthorized session.":
            raise RuntimeError("Shoir-IE local session remained usable after logout.")
    finally:
        # Remove only this random synthetic account from the disposable local DB.
        with db_connect(db_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM public.shoir_sessions WHERE username_lc = %s", (username_lc,))
                cursor.execute("DELETE FROM public.shoir_workspace_states WHERE username_lc = %s", (username_lc,))
                cursor.execute("DELETE FROM public.shoir_login_throttle WHERE key_hash = %s", (throttle_hash,))
                cursor.execute("DELETE FROM public.shoir_pending_credentials WHERE username_lc = %s", (username_lc,))
                cursor.execute("DELETE FROM public.shoir_accounts WHERE username_lc = %s", (username_lc,))
            conn.commit()

        with db_connect(db_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      (SELECT count(*) FROM public.shoir_accounts WHERE username_lc = %s),
                      (SELECT count(*) FROM public.shoir_sessions WHERE username_lc = %s),
                      (SELECT count(*) FROM public.shoir_workspace_states WHERE username_lc = %s),
                      (SELECT count(*) FROM public.shoir_pending_credentials WHERE username_lc = %s),
                      (SELECT count(*) FROM public.shoir_login_throttle WHERE key_hash = %s)
                    """,
                    (username_lc, username_lc, username_lc, username_lc, throttle_hash),
                )
                remaining = cursor.fetchone()
        if any(remaining):
            raise RuntimeError("Shoir-IE local smoke-test account left synthetic rows after cleanup.")


def validate_migration_history(
    history: list[dict[str, Any]], migration_dir: Path, expected_count: int
) -> dict[str, Any]:
    if not isinstance(history, list) or len(history) != expected_count:
        raise RuntimeError("Source migration ledger count does not match its database contract.")
    history_by_version: dict[str, str] = {}
    for row in history:
        if not isinstance(row, dict):
            raise RuntimeError("Source migration ledger contains a malformed row.")
        version = row.get("version")
        name = row.get("name")
        if (
            not isinstance(version, str)
            or not re.fullmatch(r"\d{14}", version)
            or not isinstance(name, str)
            or not name
            or "/" in name
            or "\\" in name
        ):
            raise RuntimeError("Source migration ledger contains an invalid version or name.")
        if version in history_by_version:
            raise RuntimeError(f"Duplicate source migration version: {version}.")
        history_by_version[version] = name

    repository_by_version: dict[str, str] = {}
    if not migration_dir.is_dir():
        raise RuntimeError("Checked-out Supabase migration directory is missing.")
    for path in migration_dir.glob("*.sql"):
        match = re.fullmatch(r"(\d{14})_(.+)\.sql", path.name)
        if not match:
            raise RuntimeError(f"Unrecognized SQL migration filename: {path.name}.")
        version, name = match.groups()
        if version in repository_by_version:
            raise RuntimeError(f"Duplicate repository migration version: {version}.")
        repository_by_version[version] = name

    missing = sorted(set(history_by_version) - set(repository_by_version))
    extra = sorted(set(repository_by_version) - set(history_by_version))
    mismatched = sorted(
        version
        for version in set(history_by_version) & set(repository_by_version)
        if history_by_version[version] != repository_by_version[version]
    )
    if missing or extra or mismatched:
        raise RuntimeError(
            "Migration history does not exactly match checked-out migration files "
            f"(missing={missing}, extra={extra}, name_mismatch={mismatched})."
        )
    return {
        "migration_history_count": len(history_by_version),
        "repository_migration_file_count": len(repository_by_version),
        "migration_history_matches_repository": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-dir", required=True, type=Path)
    parser.add_argument("--migration-dir", required=True, type=Path)
    parser.add_argument("--plain-storage-dir", required=True, type=Path)
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--anon-key", required=True)
    parser.add_argument("--service-role-key", required=True)
    parser.add_argument("--evidence-out", required=True, type=Path)
    args = parser.parse_args()

    validate_local_target_urls(args.db_url, args.api_url)

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

    restore_started_raw = os.environ.get("SHOIR_RESTORE_STARTED_AT_UTC")
    if not restore_started_raw:
        raise RuntimeError("Restore start timestamp is missing; refusing to report an incomplete RTO.")
    started_at = parse_utc(restore_started_raw)
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
    source_database_contract = json.loads(
        (args.recovery_dir / "database-contract.json").read_text(encoding="utf-8")
    )
    source_migration_history = json.loads(
        (args.recovery_dir / "migration-history.json").read_text(encoding="utf-8")
    )
    if not isinstance(source_buckets, list) or not isinstance(source_policies, list):
        raise RuntimeError("Storage metadata exports must be JSON arrays.")
    if len(source_buckets) != int(manifest["storage_bucket_count"]):
        raise RuntimeError("Storage bucket metadata count does not match the backup manifest.")
    if len(source_objects) != int(manifest["storage_object_metadata_count"]):
        raise RuntimeError("Storage object metadata count does not match the backup manifest.")
    if not isinstance(source_table_counts, dict) or not source_table_counts:
        raise RuntimeError("Application table row-count manifest is empty or invalid.")
    expected_contract_keys = {
        "rls_table_count", "policy_count", "constraint_count",
        "function_count", "table_grant_count", "routine_grant_count",
        "source_migration_count",
    }
    if not isinstance(source_database_contract, dict) or not expected_contract_keys.issubset(source_database_contract):
        raise RuntimeError("Database restore contract is incomplete.")
    migration_validation = validate_migration_history(
        source_migration_history,
        args.migration_dir,
        int(source_database_contract["source_migration_count"]),
    )
    if int(manifest.get("migration_history_count", -1)) != migration_validation["migration_history_count"]:
        raise RuntimeError("Backup manifest migration count does not match encrypted migration ledger.")
    if int(manifest.get("source_migration_count", -1)) != int(source_database_contract["source_migration_count"]):
        raise RuntimeError("Backup manifest migration count differs from the source database contract.")

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

        restored_contract = database_contract(conn)
        for key in (
            "rls_table_count", "policy_count", "constraint_count",
            "function_count", "table_grant_count", "routine_grant_count",
        ):
            if restored_contract[key] != int(source_database_contract[key]):
                raise RuntimeError(
                    f"Restored database contract mismatch for {key}: "
                    f"source={source_database_contract[key]}, restored={restored_contract[key]}."
                )

        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM storage.buckets")
            restored_bucket_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'storage'")
            restored_policy_count = cursor.fetchone()[0]
        if restored_bucket_count != len(source_buckets):
            raise RuntimeError("Restored Storage bucket count does not match source.")
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, public, file_size_limit, allowed_mime_types FROM storage.buckets"
            )
            restored_bucket_rows = [
                {
                    "id": row[0],
                    "name": row[1],
                    "public": row[2],
                    "file_size_limit": row[3],
                    "allowed_mime_types": row[4],
                }
                for row in cursor.fetchall()
            ]
        expected_bucket_config = {
            row["id"]: normalize_bucket_config(row) for row in source_buckets
        }
        restored_bucket_config = {
            row["id"]: normalize_bucket_config(row) for row in restored_bucket_rows
        }
        if restored_bucket_config != expected_bucket_config:
            raise RuntimeError("Restored Storage bucket privacy, size limit, or MIME allowlist differs from source.")
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
            cursor.execute("SELECT bucket_id, name, metadata FROM storage.objects")
            restored_object_rows = cursor.fetchall()
            validate_storage_object_inventory(source_objects, restored_object_rows)
            cursor.execute("SELECT count(*) FROM auth.users")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("Backup restore unexpectedly populated Auth users despite zero-row guard.")

    smoke_test_local_auth(session, args.api_url, args.anon_key, args.service_role_key, args.db_url)
    smoke_test_shoir_identity(
        session, args.api_url, args.anon_key, args.service_role_key, args.db_url
    )

    finished_at = utc_now()
    evidence = {
        "result": "PASS",
        "target": "ephemeral-local-supabase",
        "source_project_ref": EXPECTED_PROJECT_REF,
        "database_name": "postgres",
        "postgres_major_version": 17,
        "application_table_count": len(source_table_counts),
        "database_contract": restored_contract,
        "source_migration_count": int(source_database_contract["source_migration_count"]),
        **migration_validation,
        "storage_bucket_count": restored_bucket_count,
        "storage_policy_count": restored_policy_count,
        "storage_object_count": restored_object_count,
        "storage_objects_uploaded_and_sha256_verified": uploaded_count,
        "storage_object_bytes_sha256_verified": verified_bytes,
        "auth_data_exported": False,
        "auth_non_migration_source_rows": 0,
        "local_supabase_auth_synthetic_login": "PASS",
        "local_supabase_auth_test_user_removed": True,
        "shoir_custom_account_login": "PASS",
        "shoir_session_entitlement": "PASS",
        "shoir_workspace_save_load": "PASS",
        "shoir_logout_revocation": "PASS",
        "shoir_synthetic_account_and_session_cleanup": "PASS",
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
