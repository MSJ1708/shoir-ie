"""Safe, explicit, read-only REST connector verification for Shoir-IE.

No network operation occurs at import time. The only network entry point is
verify_readonly_rest_connector(), which must be called from an authorized,
explicitly submitted T096 action. This adapter supports HTTPS + Bearer token
only; vendor-specific protocols/authentication belong in separately reviewed
adapters.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit


_MAX_ENDPOINT_LENGTH = 2048
_MAX_RESPONSE_BYTES = 1_048_576
_MAX_TIMEOUT_SECONDS = 10.0
_DEFAULT_TIMEOUT_SECONDS = 5.0
_MAX_DNS_ADDRESSES = 16
_SENSITIVE_KEY = re.compile(
    r"(secret|token|password|authorization|credential|api[_-]?key|"
    r"access[_-]?key|email|phone|mobile|ssn|national[_-]?id|"
    r"personal[_-]?data|refresh)",
    re.IGNORECASE,
)
_BLOCKED_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("fd00:ec2::254"),
}
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "fe80::/10",
        "ff00::/8",
    )
)


class ConnectorFailure(Exception):
    """Controlled connector failure with a safe, user-facing status."""

    def __init__(self, status: str, remediation: str):
        super().__init__(status)
        self.status = status
        self.remediation = remediation


def _config_value(name: str) -> str:
    value = os.environ.get(name, "")
    if value and value.strip():
        return value.strip()
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        return str(value or "").strip()
    except Exception:
        return ""


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _profile_env_names(profile: Mapping[str, Any]) -> tuple[str, str, str]:
    name = str(profile.get("name") or "REST connector").strip()[:150]
    endpoint_env = str(profile.get("endpoint_env") or "").strip()
    credential_env = str(profile.get("credential_env") or "").strip()
    endpoint_match = re.fullmatch(r"(SHOIR_CONNECTOR_[A-Z0-9_]+)_ENDPOINT", endpoint_env)
    if not endpoint_match:
        raise ConnectorFailure(
            "CONFIGURATION_INVALID",
            "Use a server-side SHOIR_CONNECTOR_<NAME>_ENDPOINT setting for the approved HTTPS endpoint.",
        )
    prefix = endpoint_match.group(1)
    if credential_env != prefix + "_TOKEN":
        raise ConnectorFailure(
            "CONFIGURATION_INVALID",
            "This REST adapter supports a Bearer token stored as the matching SHOIR_CONNECTOR_<NAME>_TOKEN secret only.",
        )
    return name, prefix, credential_env


def _parse_allowlisted_hosts(raw: str) -> set[tuple[str, int]]:
    values = [part for part in re.split(r"[,\s]+", raw.strip()) if part]
    if not values:
        raise ConnectorFailure(
            "CONFIGURATION_INVALID",
            "Set SHOIR_CONNECTOR_ALLOWED_HOSTS to an explicit comma-separated hostname[:port] allowlist.",
        )
    result: set[tuple[str, int]] = set()
    for value in values:
        if "*" in value or "/" in value or "@" in value:
            raise ConnectorFailure(
                "CONFIGURATION_INVALID",
                "The connector host allowlist must contain exact hostnames or IP addresses, not wildcards or URLs.",
            )
        try:
            parsed = urlsplit("//" + value)
            host = (parsed.hostname or "").rstrip(".").lower()
            port = parsed.port if parsed.port is not None else 443
        except ValueError as exc:
            raise ConnectorFailure(
                "CONFIGURATION_INVALID", "The connector host allowlist contains an invalid host or port."
            ) from exc
        if not host or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ConnectorFailure(
                "CONFIGURATION_INVALID",
                "Each connector allowlist entry must be an exact hostname[:port] without a path or credentials.",
            )
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ConnectorFailure(
                "CONFIGURATION_INVALID", "A connector allowlist hostname is not valid IDNA."
            ) from exc
        if not 1 <= port <= 65535:
            raise ConnectorFailure("CONFIGURATION_INVALID", "An allowlisted connector port is invalid.")
        result.add((host, port))
    return result


def _parse_approved_private_cidrs(raw: str) -> tuple[Any, ...]:
    networks = []
    for item in [part for part in re.split(r"[,\s]+", raw.strip()) if part]:
        try:
            network = ipaddress.ip_network(item, strict=True)
        except ValueError as exc:
            raise ConnectorFailure(
                "CONFIGURATION_INVALID",
                "SHOIR_CONNECTOR_APPROVED_PRIVATE_CIDRS contains an invalid CIDR network.",
            ) from exc
        if not network.is_private or network.is_loopback or network.is_link_local or network.is_multicast or network.is_reserved:
            raise ConnectorFailure(
                "CONFIGURATION_INVALID",
                "Only explicitly approved private industrial-network CIDRs may be listed; loopback, link-local, multicast and reserved ranges are prohibited.",
            )
        if any(network.version == blocked.version and network.overlaps(blocked) for blocked in _BLOCKED_NETWORKS):
            raise ConnectorFailure(
                "CONFIGURATION_INVALID",
                "The approved private CIDR overlaps a prohibited network range.",
            )
        if any(ip in network for ip in _BLOCKED_IPS if ip.version == network.version):
            raise ConnectorFailure(
                "CONFIGURATION_INVALID",
                "The approved private CIDR includes a prohibited cloud-metadata address.",
            )
        networks.append(network)
    return tuple(networks)


def _ip_permitted(address: Any, approved_private_networks: tuple[Any, ...]) -> bool:
    if address in _BLOCKED_IPS:
        return False
    if (
        address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
    ):
        return False
    if address.is_global:
        return True
    if address.is_private:
        return any(
            network.version == address.version and address in network
            for network in approved_private_networks
        )
    return False


def _resolve_pinned_ip(
    host: str,
    port: int,
    approved_private_networks: tuple[Any, ...],
    resolver: Callable[..., Any] | None = None,
) -> str:
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        lookup = resolver or socket.getaddrinfo
        try:
            records = lookup(host, port, type=socket.SOCK_STREAM)
        except (OSError, socket.gaierror, TimeoutError) as exc:
            raise ConnectorFailure(
                "CONNECTION_FAILED",
                "The approved connector hostname could not be resolved. Verify DNS and the deployment's network policy.",
            ) from exc
        addresses = []
        for record in records:
            try:
                addr = ipaddress.ip_address(record[4][0].split("%", 1)[0])
            except (ValueError, IndexError, TypeError):
                continue
            if addr not in addresses:
                addresses.append(addr)
    if not addresses or len(addresses) > _MAX_DNS_ADDRESSES:
        raise ConnectorFailure(
            "DESTINATION_BLOCKED",
            "The connector hostname resolved to no usable addresses or too many addresses.",
        )
    if any(not _ip_permitted(address, approved_private_networks) for address in addresses):
        raise ConnectorFailure(
            "DESTINATION_BLOCKED",
            "The connector hostname resolves to a prohibited or unapproved network address. Review the exact host allowlist and private-network policy.",
        )
    # Connect to this validated address directly. TLS SNI and certificate
    # verification still use the original hostname, preventing DNS re-resolution
    # between validation and the socket connection.
    return str(addresses[0])


def _validated_path(raw: str, field: str) -> str:
    path = raw.strip()
    if (
        not path
        or len(path) > 256
        or path.startswith("/")
        or path.startswith("\\")
        or not re.fullmatch(r"[A-Za-z0-9._~/-]+", path)
        or "//" in path
        or any(segment in {".", ".."} for segment in path.split("/"))
    ):
        raise ConnectorFailure(
            "CONFIGURATION_INVALID",
            f"{field} must be a short, relative path configured by the connector administrator without query strings or traversal segments.",
        )
    return path


def _safe_endpoint(raw: str, allowed_hosts: set[tuple[str, int]]) -> tuple[Any, str, int, str]:
    if not raw or len(raw) > _MAX_ENDPOINT_LENGTH:
        raise ConnectorFailure(
            "CONFIGURATION_INVALID", "The approved connector endpoint is missing or exceeds the URL length limit."
        )
    try:
        parsed = urlsplit(raw)
        port = parsed.port or 443
        host = (parsed.hostname or "").rstrip(".").lower()
    except ValueError as exc:
        raise ConnectorFailure(
            "CONFIGURATION_INVALID", "The approved connector endpoint has an invalid hostname or port."
        ) from exc
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not 1 <= port <= 65535
    ):
        raise ConnectorFailure(
            "CONFIGURATION_INVALID",
            "The REST connector requires an HTTPS endpoint with no embedded credentials, query string or fragment.",
        )
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ConnectorFailure(
            "CONFIGURATION_INVALID", "The connector endpoint hostname is not valid IDNA."
        ) from exc
    if (host, port) not in allowed_hosts:
        raise ConnectorFailure(
            "DESTINATION_BLOCKED",
            "The connector endpoint does not exactly match an administrator-approved hostname and port.",
        )
    base_path = parsed.path or ""
    if base_path and (
        not re.fullmatch(r"[A-Za-z0-9._~/-]+", base_path)
        or "//" in base_path
        or any(segment in {".", ".."} for segment in base_path.split("/"))
    ):
        raise ConnectorFailure(
            "CONFIGURATION_INVALID", "The connector base path contains unsupported or traversal syntax."
        )
    return parsed, host, port, base_path.rstrip("/")


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to the already validated IP, with hostname TLS verification."""

    def __init__(self, host: str, port: int, pinned_ip: str, timeout: float):
        super().__init__(host=host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _get_response(
    host: str,
    port: int,
    pinned_ip: str,
    base_path: str,
    relative_path: str,
    token: str,
    timeout: float,
) -> tuple[int, str, bytes]:
    target_path = (base_path + "/" + relative_path).replace("//", "/")
    connection = _PinnedHTTPSConnection(host, port, pinned_ip, timeout)
    try:
        connection.request(
            "GET",
            target_path,
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer " + token,
                "Connection": "close",
                "User-Agent": "Shoir-IE-Integration-Check/1.0",
            },
        )
        response = connection.getresponse()
        status = response.status
        content_type = str(response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
        content_length = response.getheader("Content-Length")
        if content_length:
            if not content_length.isdigit():
                raise ConnectorFailure("MALFORMED_RESPONSE", "The connector returned an invalid content length.")
            if int(content_length) > _MAX_RESPONSE_BYTES:
                raise ConnectorFailure(
                    "RESPONSE_TOO_LARGE", "The connector response exceeds the 1 MiB limit."
                )
        body = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ConnectorFailure(
                "RESPONSE_TOO_LARGE", "The connector response exceeds the 1 MiB limit."
            )
        return status, content_type, body
    except ConnectorFailure:
        raise
    except (socket.timeout, TimeoutError) as exc:
        raise ConnectorFailure(
            "CONNECTION_FAILED_TIMEOUT", "The connector timed out. Check endpoint health and the configured network path."
        ) from exc
    except ssl.SSLError as exc:
        raise ConnectorFailure(
            "TLS_VERIFICATION_FAILED", "TLS certificate verification failed; do not disable certificate verification."
        ) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise ConnectorFailure(
            "CONNECTION_FAILED", "The connector request failed. Check DNS, egress policy, endpoint health and credentials."
        ) from exc
    finally:
        connection.close()


def _redacted_preview(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        result = {}
        for key, child in list(value.items())[:40]:
            key_text = str(key)[:100]
            result[key_text] = "[REDACTED]" if _SENSITIVE_KEY.search(key_text) else _redacted_preview(child, depth=depth + 1)
        return result
    if isinstance(value, list):
        return [_redacted_preview(item, depth=depth + 1) for item in value[:3]]
    if isinstance(value, str):
        return value[:200] + ("…" if len(value) > 200 else "")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "[UNSUPPORTED_VALUE]"


def verify_readonly_rest_connector(
    profile: Mapping[str, Any],
    *,
    include_sample_data: bool = False,
    config_reader: Callable[[str], str] | None = None,
    resolver: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Explicitly verify one approved HTTPS REST connector using GET-only requests.

    Endpoint, token and resource paths are read only from the approved server-side
    environment/Streamlit secret store. Redirects are never followed, TLS
    verification remains enabled, DNS results are validated and one permitted IP
    is pinned for the actual TLS connection.
    """
    now = _timestamp()
    name = str(profile.get("name") or "REST connector").strip()[:150]
    network_attempted = False
    try:
        protocol = str(profile.get("protocol") or "").strip().upper()
        if protocol != "REST":
            raise ConnectorFailure(
                "CONFIGURATION_INVALID",
                "The generic adapter supports REST/HTTPS only; use a separately reviewed provider-specific adapter for other protocols.",
            )
        name, prefix, credential_env = _profile_env_names(profile)
        read_config = config_reader or _config_value
        enabled = read_config(prefix + "_ENABLED").strip().lower() in {"true", "1", "yes", "enabled"}
        if not enabled:
            return {
                "tool_id": "T096",
                "profile_name": name,
                "status": "DISABLED_OR_REVOKED",
                "attempted": False,
                "verified_at": now,
                "connection_verified": False,
                "data_retrieval_verified": False,
                "error_code": "CONNECTOR_DISABLED",
                "remediation": "An authorized deployment administrator must explicitly enable this connector after reviewing its destination, scope and least-privilege token.",
            }
        endpoint = read_config(prefix + "_ENDPOINT")
        token = read_config(credential_env)
        if not endpoint or not token:
            raise ConnectorFailure(
                "NOT_CONFIGURED",
                "Set the approved endpoint and Bearer-token secret in the server-side secret store. Never enter a token in the Workbench JSON editor.",
            )
        if len(token) > 4096 or any(ord(character) < 32 or ord(character) == 127 for character in token):
            raise ConnectorFailure(
                "CONFIGURATION_INVALID",
                "The configured Bearer token exceeds the safe size limit or contains prohibited control characters; rotate it in the approved secret store.",
            )
        health_path = _validated_path(read_config(prefix + "_HEALTH_PATH"), "health path")
        read_path = _validated_path(read_config(prefix + "_READ_PATH"), "read path")
        allowed_hosts = _parse_allowlisted_hosts(read_config("SHOIR_CONNECTOR_ALLOWED_HOSTS"))
        private_networks = _parse_approved_private_cidrs(read_config("SHOIR_CONNECTOR_APPROVED_PRIVATE_CIDRS"))
        timeout_raw = read_config("SHOIR_CONNECTOR_TIMEOUT_SECONDS")
        try:
            timeout = float(timeout_raw) if timeout_raw else _DEFAULT_TIMEOUT_SECONDS
        except (TypeError, ValueError, OverflowError) as exc:
            raise ConnectorFailure(
                "CONFIGURATION_INVALID", "SHOIR_CONNECTOR_TIMEOUT_SECONDS must be a number between 0.5 and 10."
            ) from exc
        if not 0.5 <= timeout <= _MAX_TIMEOUT_SECONDS:
            raise ConnectorFailure(
                "CONFIGURATION_INVALID", "SHOIR_CONNECTOR_TIMEOUT_SECONDS must be between 0.5 and 10."
            )
        parsed, host, port, base_path = _safe_endpoint(endpoint, allowed_hosts)
        network_attempted = True  # DNS resolution is part of the explicit operator-triggered attempt.
        pinned_ip = _resolve_pinned_ip(host, port, private_networks, resolver=resolver)

        health_status, _health_type, _health_body = _get_response(
            host, port, pinned_ip, base_path, health_path, token, timeout
        )
        if 300 <= health_status < 400:
            raise ConnectorFailure(
                "REDIRECT_BLOCKED", "The health endpoint returned a redirect; redirects are blocked to prevent trust-boundary changes."
            )
        if health_status in {401, 407}:
            raise ConnectorFailure(
                "AUTHENTICATION_REJECTED", "The connector rejected authentication. Rotate/check the scoped token through the authorized administrator."
            )
        if health_status == 403:
            raise ConnectorFailure(
                "AUTHORIZATION_REJECTED", "The connector denied the requested health operation. Check least-privilege service permissions."
            )
        if health_status == 429:
            raise ConnectorFailure(
                "RATE_LIMITED", "The connector rate limit was reached. Wait for the provider's retry window; no automatic retry was attempted."
            )
        if not 200 <= health_status < 300:
            raise ConnectorFailure(
                "CONNECTION_FAILED", f"The health endpoint returned HTTP {health_status}; inspect provider health without exposing response bodies."
            )

        read_status, content_type, body = _get_response(
            host, port, pinned_ip, base_path, read_path, token, timeout
        )
        if 300 <= read_status < 400:
            raise ConnectorFailure(
                "REDIRECT_BLOCKED", "The read endpoint returned a redirect; it was not followed."
            )
        if read_status in {401, 407}:
            raise ConnectorFailure(
                "AUTHENTICATION_REJECTED", "The connector rejected authentication on data retrieval. Check or revoke the scoped token."
            )
        if read_status == 403:
            raise ConnectorFailure(
                "AUTHORIZATION_REJECTED", "The connector denied the read operation. Grant only the approved read scope if appropriate."
            )
        if read_status == 429:
            raise ConnectorFailure(
                "RATE_LIMITED", "The connector rate limit was reached. No automatic retry was attempted."
            )
        if not 200 <= read_status < 300:
            raise ConnectorFailure(
                "DATA_RETRIEVAL_FAILED", f"The read endpoint returned HTTP {read_status}; verify the configured read-only resource."
            )
        if "json" not in content_type:
            raise ConnectorFailure(
                "MALFORMED_RESPONSE", "The read endpoint must return a JSON content type."
            )
        try:
            sample = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorFailure(
                "MALFORMED_RESPONSE", "The read endpoint returned invalid UTF-8 JSON."
            ) from exc
        if not isinstance(sample, (dict, list)):
            raise ConnectorFailure(
                "MALFORMED_RESPONSE", "The read endpoint must return a JSON object or list."
            )
        keys = list(sample.keys())[:100] if isinstance(sample, dict) else (
            list(sample[0].keys())[:100] if sample and isinstance(sample[0], dict) else []
        )
        record_count = len(sample) if isinstance(sample, list) else None
        result = {
            "tool_id": "T096",
            "profile_name": name,
            "status": "DATA_RETRIEVAL_VERIFIED",
            "attempted": True,
            "verified_at": now,
            "connection_verified": True,
            "health_http_status": health_status,
            "data_retrieval_verified": True,
            "read_http_status": read_status,
            "response_content_type": content_type,
            "response_bytes": len(body),
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "response_shape": "list" if isinstance(sample, list) else "object",
            "record_count": record_count,
            "sample_keys": keys,
            "sample_preview": _redacted_preview(sample) if include_sample_data else None,
            "warning": "This verifies only the configured HTTPS health/read paths and the returned sample response. It does not prove vendor-wide integration, write access, data quality, or ongoing availability.",
        }
        return result
    except ConnectorFailure as exc:
        return {
            "tool_id": "T096",
            "profile_name": name,
            "status": exc.status,
            "attempted": network_attempted,
            "verified_at": now,
            "connection_verified": False,
            "data_retrieval_verified": False,
            "error_code": exc.status,
            "remediation": exc.remediation,
        }
    except Exception as exc:
        # Do not return exception messages, URLs, response bodies or header values.
        # The class name is low-sensitivity diagnostic context and is not a secret.
        return {
            "tool_id": "T096",
            "profile_name": name,
            "status": "CONNECTION_FAILED",
            "attempted": network_attempted,
            "verified_at": now,
            "connection_verified": False,
            "data_retrieval_verified": False,
            "error_code": type(exc).__name__[:80],
            "remediation": "The connector operation failed unexpectedly. Check protected deployment diagnostics and connector configuration; do not disable TLS verification or broaden network access.",
        }
