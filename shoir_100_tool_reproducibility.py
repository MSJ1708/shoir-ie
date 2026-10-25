"""Secret-aware, metadata-only reproducibility archive builder for Research Pack target T087."""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Mapping


_SECRET_KEY = re.compile(r"(password|passwd|secret|token|api.?key|credential|connection.?string|authorization|cookie|email|phone|address|private.?key|service.?role)", re.I)
_SAFE_PACKAGES = ("numpy", "pandas", "scipy", "pulp", "streamlit", "plotly")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _safe_scalar_mapping(value: Mapping[str, Any], label: str, *, maximum: int = 100) -> dict[str, Any]:
    if len(value) > maximum:
        raise ValueError(f"{label} is limited to {maximum} key/value entries.")
    safe = {}
    for key, item in value.items():
        name = str(key).strip()
        if not name:
            raise ValueError(f"{label} contains an empty key.")
        if _SECRET_KEY.search(name):
            raise ValueError(f"{label} contains a key that looks sensitive ('{name}'); remove it before packaging.")
        if item is None or isinstance(item, (str, bool, int)):
            safe[name] = item
        elif isinstance(item, float):
            if item != item or item in (float("inf"), float("-inf")):
                raise ValueError(f"{label} contains a non-finite numeric value for '{name}'.")
            safe[name] = item
        else:
            raise ValueError(f"{label} values must be scalar text/numeric/boolean/null values; raw tables and files are not embedded.")
    return safe


def build_reproducibility_pack(
    *,
    project_name: str,
    app_version: str,
    git_commit: str,
    dataset_fingerprint: str,
    method_name: str,
    method_version: str,
    parameters: Mapping[str, Any],
    output_summary: Mapping[str, Any],
    random_seed: int | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create a valid ZIP with a manifest, allowed environment metadata, methods, outputs and SHA-256 ledger."""
    project = str(project_name or "").strip()
    app_ver = str(app_version or "").strip()
    commit = str(git_commit or "").strip()
    fingerprint = str(dataset_fingerprint or "").strip().lower()
    method = str(method_name or "").strip()
    method_ver = str(method_version or "").strip()
    if not all((project, app_ver, commit, method, method_ver)):
        raise ValueError("Project, app version, commit/ref, method name and method version are required.")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("Dataset fingerprint must be a 64-character SHA-256 hex digest.")
    if random_seed is not None and (not isinstance(random_seed, int) or isinstance(random_seed, bool) or random_seed < 0):
        raise ValueError("Random seed must be a non-negative integer or blank.")
    if created_at:
        try:
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("created_at must be an ISO-8601 timestamp.") from exc
        if created.tzinfo is None:
            raise ValueError("created_at must include a timezone.")
        created_utc = created.astimezone(timezone.utc).isoformat()
    else:
        created_utc = datetime.now(timezone.utc).isoformat()

    params = _safe_scalar_mapping(parameters, "parameters")
    outputs = _safe_scalar_mapping(output_summary, "output_summary")
    environment = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {},
        "package_version_scope": "allowlisted package versions only; no environment variables or credentials included",
    }
    for package in _SAFE_PACKAGES:
        try:
            environment["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            environment["packages"][package] = None

    manifest = {
        "artifact_type": "shoir-ie-reproducibility-metadata-pack",
        "format_version": "1.0",
        "created_at_utc": created_utc,
        "project_name": project,
        "app_version": app_ver,
        "git_commit_or_ref": commit,
        "dataset_fingerprint_sha256": fingerprint,
        "method": {"name": method, "version": method_ver},
        "random_seed": random_seed,
        "input_scope": "metadata-only; source dataset cells and original workbook are not embedded",
        "parameter_keys": sorted(params),
        "output_keys": sorted(outputs),
    }
    methods_markdown = (
        "# Reproducibility notes\n\n"
        f"- Project: {project}\n- Application version: {app_ver}\n- Git commit/ref: {commit}\n"
        f"- Method: {method} ({method_ver})\n- Dataset SHA-256: {fingerprint}\n"
        f"- Random seed: {random_seed if random_seed is not None else 'not supplied'}\n\n"
        "## Reproduction limits\n\n"
        "- The original dataset is intentionally not included; obtain it through its authorized source workflow and compare its fingerprint.\n"
        "- Environment versions are descriptive and may not reproduce operating-system, solver, random-number or hardware behavior exactly.\n"
        "- The archive does not authenticate the user-entered metadata or independently verify the method/output.\n"
        "- Values in outputs.json are user-supplied summary scalars; they are not independently recomputed by this pack builder.\n"
    ).encode("utf-8")

    members = {
        "manifest.json": _json_bytes(manifest),
        "environment.json": _json_bytes(environment),
        "parameters.json": _json_bytes(params),
        "outputs.json": _json_bytes(outputs),
        "method_and_limitations.md": methods_markdown,
    }
    checksum_text = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(members.items())
    ).encode("utf-8")
    members["checksums.sha256"] = checksum_text

    buffer = BytesIO()
    try:
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, content in sorted(members.items()):
                archive.writestr(name, content)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise RuntimeError("Reproducibility ZIP could not be created.") from exc
    archive_bytes = buffer.getvalue()
    if not archive_bytes or not zipfile.is_zipfile(BytesIO(archive_bytes)):
        raise RuntimeError("Reproducibility ZIP validation failed.")
    # Re-open and validate member payload hashes before returning the artifact.
    with zipfile.ZipFile(BytesIO(archive_bytes), "r") as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"Generated ZIP failed CRC validation at {bad_member}.")
        for name, content in members.items():
            if archive.read(name) != content:
                raise RuntimeError(f"Generated ZIP content mismatch for {name}.")

    return {
        "tool_id": "T087",
        "status": "PACKAGE_BUILT",
        "method": "Metadata-only reproducibility archive with SHA-256 member checksums",
        "manifest": manifest,
        "environment": environment,
        "member_names": sorted(members),
        "member_count": len(members),
        "zip_size_bytes": len(archive_bytes),
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "archive_base64": base64.b64encode(archive_bytes).decode("ascii"),
        "raw_dataset_included": False,
        "secret_key_screen_applied": True,
        "warnings": [
            "The archive is metadata-only; it does not contain the source dataset or guarantee full computational reproducibility.",
            "User-supplied summaries and references are not authenticated or independently verified.",
            "Review the archive content and sensitivity before external sharing.",
        ],
        "metrics": {
            "member_count": len(members),
            "zip_size_bytes": len(archive_bytes),
            "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
            "raw_dataset_included": False,
        },
    }
