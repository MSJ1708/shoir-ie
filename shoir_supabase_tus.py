"""Small, bounded Supabase Storage TUS client for signed private uploads.

The caller creates the signed upload token through the authenticated Edge
Function. This module never receives a service-role key and never follows
redirects, which prevents signed upload capabilities leaking to another host.
"""
from __future__ import annotations

import base64
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests


TUS_VERSION = "1.0.0"
TUS_CHUNK_BYTES = 6 * 1024 * 1024
MAX_DATASET_UPLOAD_BYTES = 50 * 1024 * 1024
_RETRY_DELAYS_SECONDS = (0.0, 0.25, 0.5, 1.0, 2.0)
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class TusUploadExpiredError(RuntimeError):
    """The resumable upload resource has expired or no longer exists."""


def _metadata_value(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _safe_upload_path(value: str) -> str:
    path = str(value or "").strip()
    parts = path.split("/")
    if (
        not path
        or path.startswith("/")
        or len(path) > 240
        or any(part in {"", ".", ".."} for part in parts)
        or "\\" in path
        or any(ord(char) < 32 for char in path)
    ):
        raise ValueError("Dataset upload object path is invalid.")
    return path


def _upload_endpoint(project_ref: str) -> str:
    ref = str(project_ref or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]{20}", ref):
        raise ValueError("Supabase project reference is invalid.")
    return f"https://{ref}.storage.supabase.co/storage/v1/upload/resumable"


def _validate_upload_location(location: str, endpoint: str, project_ref: str) -> str:
    resolved = urljoin(endpoint.rstrip("/") + "/", str(location or "").strip())
    try:
        parsed = urlsplit(resolved)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("Storage returned an invalid resumable upload location.") from exc
    expected_host = f"{project_ref}.storage.supabase.co"
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname != expected_host
        or port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not parsed.path.startswith("/storage/v1/upload/resumable/")
    ):
        raise RuntimeError("Storage returned an untrusted resumable upload location.")
    return resolved


def _header_int(headers: Any, name: str, default: int | None = None) -> int | None:
    raw = headers.get(name) if hasattr(headers, "get") else None
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Storage returned an invalid {name} header.") from exc
    if value < 0:
        raise RuntimeError(f"Storage returned an invalid {name} header.")
    return value


def _head_upload_offset(
    http: Any,
    upload_url: str,
    expected_length: int,
) -> int:
    try:
        response = http.head(
            upload_url,
            headers={"Tus-Resumable": TUS_VERSION, "Cache-Control": "no-store"},
            timeout=(10, 30),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            "Unable to confirm resumable upload progress; retry the same file to resume."
        ) from exc
    if response.status_code in {404, 410}:
        raise TusUploadExpiredError("The resumable upload has expired; start a new upload.")
    if response.status_code != 200:
        raise RuntimeError(
            f"Storage could not confirm resumable upload progress ({response.status_code})."
        )
    remote_length = _header_int(response.headers, "Upload-Length")
    if remote_length is not None and remote_length != expected_length:
        raise RuntimeError("Storage resumable upload length does not match the selected file.")
    offset = _header_int(response.headers, "Upload-Offset")
    if offset is None or offset > expected_length:
        raise RuntimeError("Storage returned an invalid resumable upload offset.")
    return offset


def upload_signed_tus(
    *,
    project_ref: str,
    bucket_name: str,
    object_name: str,
    content_type: str,
    signed_upload_token: str,
    file_bytes: bytes,
    resume_url: str = "",
    on_upload_url: Callable[[str], None] | None = None,
    http_session: Any | None = None,
) -> str:
    """Create or resume a signed TUS upload and return its opaque upload URL.

    Progress is reconciled with HEAD after uncertain PATCH responses, so a
    retried chunk is never blindly sent from a stale byte offset.
    """
    ref = str(project_ref or "").strip().lower()
    endpoint = _upload_endpoint(ref)
    bucket = str(bucket_name or "").strip()
    object_path = _safe_upload_path(object_name)
    media_type = str(content_type or "").strip()
    token = str(signed_upload_token or "").strip()
    if not bucket or len(bucket) > 100 or not media_type or len(media_type) > 120:
        raise ValueError("Dataset upload metadata is invalid.")
    if not isinstance(file_bytes, bytes) or not file_bytes or len(file_bytes) > MAX_DATASET_UPLOAD_BYTES:
        raise ValueError("Dataset upload must be between 1 byte and 50 MiB.")
    if not resume_url and not re.fullmatch(r"[A-Za-z0-9._~-]{16,4096}", token):
        raise ValueError("A valid signed upload token is required.")
    http = http_session or requests.Session()
    owns_session = http_session is None
    try:
        upload_url = ""
        if resume_url:
            upload_url = _validate_upload_location(resume_url, endpoint, ref)
        else:
            metadata = ",".join(
                (
                    "bucketName " + _metadata_value(bucket),
                    "objectName " + _metadata_value(object_path),
                    "contentType " + _metadata_value(media_type),
                )
            )
            headers = {
                "Tus-Resumable": TUS_VERSION,
                "Upload-Length": str(len(file_bytes)),
                "Upload-Metadata": metadata,
                "x-signature": token,
                "x-upsert": "false",
            }
            try:
                created = http.post(
                    endpoint,
                    headers=headers,
                    timeout=(10, 30),
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                raise RuntimeError(
                    "Unable to create a resumable storage upload; retry the same file."
                ) from exc
            if created.status_code != 201:
                raise RuntimeError(
                    f"Storage rejected resumable upload creation ({created.status_code})."
                )
            upload_url = _validate_upload_location(
                str(created.headers.get("Location") or ""),
                endpoint,
                ref,
            )
            if on_upload_url is not None:
                on_upload_url(upload_url)

        offset = _head_upload_offset(http, upload_url, len(file_bytes))
        while offset < len(file_bytes):
            chunk = file_bytes[offset : offset + TUS_CHUNK_BYTES]
            next_offset = offset + len(chunk)
            advanced = False
            for attempt, delay in enumerate(_RETRY_DELAYS_SECONDS):
                if delay:
                    time.sleep(delay)
                response = None
                try:
                    response = http.patch(
                        upload_url,
                        data=chunk,
                        headers={
                            "Tus-Resumable": TUS_VERSION,
                            "Upload-Offset": str(offset),
                            "Content-Type": "application/offset+octet-stream",
                        },
                        timeout=(10, 90),
                        allow_redirects=False,
                    )
                except requests.RequestException:
                    # The server may have accepted some or all of the chunk.
                    # HEAD below determines the authoritative remote byte offset.
                    response = None

                if response is not None and response.status_code not in {204} | _RETRYABLE_STATUS_CODES:
                    raise RuntimeError(
                        f"Storage rejected a resumable upload chunk ({response.status_code})."
                    )

                if response is not None and response.status_code == 204:
                    reported = _header_int(response.headers, "Upload-Offset")
                    remote_offset = (
                        reported if reported is not None
                        else _head_upload_offset(http, upload_url, len(file_bytes))
                    )
                else:
                    remote_offset = _head_upload_offset(http, upload_url, len(file_bytes))

                if remote_offset < offset or remote_offset > next_offset:
                    raise RuntimeError(
                        "Storage resumable upload offset changed outside the submitted chunk."
                    )
                if remote_offset > offset:
                    offset = remote_offset
                    advanced = True
                    break
                # No bytes were accepted. Retry this same chunk from the
                # confirmed offset; never assume a failed PATCH was atomic.
            if not advanced:
                raise RuntimeError(
                    "Resumable dataset upload did not advance after bounded retries; retry the same file to resume."
                )
        return upload_url
    finally:
        if owns_session:
            try:
                http.close()
            except Exception:
                pass
