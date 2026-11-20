#!/usr/bin/env python3
"""Create and verify SHA-256 manifests for locally exported Storage object bytes.

This utility never connects to Supabase, reads credentials, encrypts data, or
creates a backup by itself. An authorized operator must first export object
bytes using an approved backup process into an isolated local directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_READ_CHUNK_BYTES = 1024 * 1024


class ManifestError(ValueError):
    """A manifest or local Storage export failed strict validation."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _relative_object_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ManifestError("Storage object path must be a non-empty string of at most 1024 characters.")
    if "\\" in value or value.startswith("/"):
        raise ManifestError("Storage object paths must be relative POSIX paths without backslashes.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ManifestError("Storage object path contains an unsafe or empty path segment.")
    if path.as_posix() != value:
        raise ManifestError("Storage object path is not in canonical POSIX form.")
    return value


def _root_directory(value: str | Path) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise ManifestError("Storage export root must not be a symbolic link.")
    try:
        root = raw.resolve(strict=True)
    except OSError as exc:
        raise ManifestError("Storage export root does not exist or cannot be resolved.") from exc
    if not root.is_dir():
        raise ManifestError("Storage export root must be a directory.")
    return root


def _manifest_destination(value: str | Path, root: Path) -> Path:
    raw = Path(value).expanduser()
    if raw.exists() and raw.is_symlink():
        raise ManifestError("Manifest destination must not be a symbolic link.")
    destination = raw.resolve(strict=False)
    try:
        destination.relative_to(root)
    except ValueError:
        return destination
    raise ManifestError("Manifest file must be stored outside the Storage object export directory.")


def _iter_files(root: Path) -> Iterable[tuple[str, Path]]:
    observed_paths: set[str] = set()
    casefold_paths: set[str] = set()
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        safe_directories: list[str] = []
        for directory in directories:
            candidate = current_path / directory
            if candidate.is_symlink():
                raise ManifestError(f"Storage export contains a symbolic-link directory: {candidate.relative_to(root)}")
            if not candidate.is_dir():
                raise ManifestError(f"Storage export contains a non-directory entry: {candidate.relative_to(root)}")
            safe_directories.append(directory)
        directories[:] = safe_directories

        for filename in filenames:
            candidate = current_path / filename
            relative = candidate.relative_to(root).as_posix()
            safe_path = _relative_object_path(relative)
            if candidate.is_symlink():
                raise ManifestError(f"Storage export contains a symbolic-link object: {safe_path}")
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                raise ManifestError(f"Cannot inspect Storage object: {safe_path}") from exc
            if not stat.S_ISREG(mode):
                raise ManifestError(f"Storage export contains a non-regular object: {safe_path}")
            if safe_path in observed_paths or safe_path.casefold() in casefold_paths:
                raise ManifestError(f"Storage export contains a duplicate or case-colliding path: {safe_path}")
            observed_paths.add(safe_path)
            casefold_paths.add(safe_path.casefold())
            yield safe_path, candidate


def _hash_regular_file(path: Path, relative: str) -> tuple[int, str]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ManifestError(f"Cannot safely open Storage object: {relative}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ManifestError(f"Storage object is not a regular file: {relative}")
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while True:
                block = stream.read(_READ_CHUNK_BYTES)
                if not block:
                    break
                total += len(block)
                digest.update(block)
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or total != after.st_size
        ):
            raise ManifestError(f"Storage object changed while it was being hashed: {relative}")
        try:
            current = path.lstat()
        except OSError as exc:
            raise ManifestError(f"Storage object disappeared while it was being hashed: {relative}") from exc
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or current.st_dev != after.st_dev
            or current.st_ino != after.st_ino
        ):
            raise ManifestError(f"Storage object path changed while it was being hashed: {relative}")
        return total, digest.hexdigest()
    finally:
        os.close(descriptor)


def _manifest_body(objects: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "hash_algorithm": "sha256",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "object_count": len(objects),
        "total_bytes": sum(item["size_bytes"] for item in objects),
        "objects": objects,
    }


def create_manifest(root: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    export_root = _root_directory(root)
    destination = _manifest_destination(manifest_path, export_root)
    objects: list[dict[str, Any]] = []
    for relative, path in sorted(_iter_files(export_root), key=lambda item: item[0]):
        size, digest = _hash_regular_file(path, relative)
        objects.append({
            "path": relative,
            "size_bytes": size,
            "sha256": digest,
        })

    body = _manifest_body(objects)
    manifest = {**body, "manifest_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.is_symlink():
        raise ManifestError("Manifest destination must not be a symbolic link.")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=destination.name + ".",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(_canonical_json(manifest) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    return {
        "status": "MANIFEST_CREATED",
        "manifest_path": str(destination),
        "object_count": manifest["object_count"],
        "total_bytes": manifest["total_bytes"],
        "manifest_sha256": manifest["manifest_sha256"],
        "warning": "A checksum manifest detects accidental changes; it is not encryption, a digital signature, or proof of backup authenticity.",
    }


def _load_manifest(manifest_path: str | Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = Path(manifest_path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ManifestError("Manifest must be an existing regular file, not a symbolic link.")
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError("Manifest is unreadable or is not valid UTF-8 JSON.") from exc
    if not isinstance(document, dict):
        raise ManifestError("Manifest root must be a JSON object.")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("Manifest schema version is unsupported.")
    if document.get("hash_algorithm") != "sha256":
        raise ManifestError("Manifest hash algorithm must be sha256.")
    timestamp = document.get("created_at_utc")
    if not isinstance(timestamp, str):
        raise ManifestError("Manifest timestamp is missing.")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestError("Manifest timestamp must be ISO 8601.") from exc
    if parsed_timestamp.tzinfo is None:
        raise ManifestError("Manifest timestamp must include a UTC offset.")

    raw_objects = document.get("objects")
    if not isinstance(raw_objects, list):
        raise ManifestError("Manifest objects must be a JSON list.")
    by_path: dict[str, dict[str, Any]] = {}
    casefold_paths: set[str] = set()
    for item in raw_objects:
        if not isinstance(item, dict):
            raise ManifestError("Each manifest object must be a JSON object.")
        object_path = _relative_object_path(item.get("path"))
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ManifestError(f"Manifest size is invalid for object: {object_path}")
        if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest):
            raise ManifestError(f"Manifest SHA-256 is invalid for object: {object_path}")
        if object_path in by_path or object_path.casefold() in casefold_paths:
            raise ManifestError(f"Manifest contains a duplicate or case-colliding path: {object_path}")
        by_path[object_path] = {"path": object_path, "size_bytes": size, "sha256": digest}
        casefold_paths.add(object_path.casefold())

    if document.get("object_count") != len(by_path):
        raise ManifestError("Manifest object_count does not match its object list.")
    if document.get("total_bytes") != sum(item["size_bytes"] for item in by_path.values()):
        raise ManifestError("Manifest total_bytes does not match its object list.")
    manifest_hash = document.get("manifest_sha256")
    body = {key: value for key, value in document.items() if key != "manifest_sha256"}
    expected_hash = hashlib.sha256(_canonical_json(body)).hexdigest()
    if not isinstance(manifest_hash, str) or not _HASH_RE.fullmatch(manifest_hash) or manifest_hash != expected_hash:
        raise ManifestError("Manifest integrity hash does not match its contents.")
    return document, by_path


def verify_manifest(root: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    export_root = _root_directory(root)
    manifest, expected = _load_manifest(manifest_path)
    actual: dict[str, dict[str, Any]] = {}
    for relative, path in _iter_files(export_root):
        size, digest = _hash_regular_file(path, relative)
        actual[relative] = {"path": relative, "size_bytes": size, "sha256": digest}

    expected_paths = set(expected)
    actual_paths = set(actual)
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    changed = sorted(
        path for path in expected_paths & actual_paths
        if expected[path]["size_bytes"] != actual[path]["size_bytes"]
        or expected[path]["sha256"] != actual[path]["sha256"]
    )
    ok = not missing and not extra and not changed
    return {
        "status": "RESTORE_BYTES_VERIFIED" if ok else "RESTORE_BYTES_MISMATCH",
        "verified": ok,
        "expected_object_count": len(expected),
        "actual_object_count": len(actual),
        "expected_total_bytes": manifest["total_bytes"],
        "actual_total_bytes": sum(item["size_bytes"] for item in actual.values()),
        "missing_paths": missing,
        "extra_paths": extra,
        "changed_paths": changed,
        "manifest_sha256": manifest["manifest_sha256"],
        "warning": "Byte verification does not establish database consistency, encryption, access isolation, backup authenticity, or measured RPO/RTO.",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="Create a SHA-256 manifest for an exported Storage directory.")
    create.add_argument("--root", required=True, help="Local root directory containing exported Storage object bytes.")
    create.add_argument("--manifest", required=True, help="Manifest JSON path outside the export root.")
    verify = subparsers.add_parser("verify", help="Compare restored Storage bytes to an existing manifest.")
    verify.add_argument("--root", required=True, help="Local root directory containing restored Storage object bytes.")
    verify.add_argument("--manifest", required=True, help="Previously created manifest JSON path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = (
            create_manifest(args.root, args.manifest)
            if args.command == "create"
            else verify_manifest(args.root, args.manifest)
        )
    except ManifestError as exc:
        print(json.dumps({"status": "BLOCKED_INVALID_INPUT", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.command == "verify" and not result["verified"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
