"""Explicit read-only ERP resource adapters and canonical data mapping.

This module deliberately contains no HTTP implementation and no token handling.
It accepts only an injected read-only GET transport plus a server-side authorization
callback. Product-specific authentication/transport and live tenant acceptance are
separate milestones; this module must not be presented as a live connection.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit


CANONICAL_ENTITY_TYPES = frozenset(
    {
        "Dataset", "Asset", "Process", "Product", "Material", "Order",
        "Workforce", "Quality", "Maintenance", "Energy", "Cost", "Scenario",
        "KPI", "Model", "Experiment", "Decision", "Outcome",
    }
)

SENSITIVE_FIELD_PATTERN = re.compile(
    r"(?:email|e-mail|phone|mobile|birth|dateofbirth|\bdob\b|national.?id|"
    r"passport|street|postal.?address|home.?address|full.?name|first.?name|"
    r"last.?name|personal.?name|employee.?name|person.?name|username|"
    r"employee.?id|person.?id|user.?id|nationality|passport.?number)",
    re.IGNORECASE,
)

PRODUCT_DESCRIPTORS: dict[str, dict[str, str]] = {
    "SAP_S4HANA_CLOUD_PUBLIC": {
        "provider": "SAP",
        "label": "SAP S/4HANA Cloud Public Edition",
        "api_catalog": "https://api.sap.com/",
    },
    "SAP_S4HANA_CLOUD_PRIVATE": {
        "provider": "SAP",
        "label": "SAP S/4HANA Cloud Private Edition / customer-managed S/4HANA",
        "api_catalog": "https://api.sap.com/package/S4HANAOPAPI/odata",
    },
    "SAP_ECC": {
        "provider": "SAP",
        "label": "SAP ECC (separate legacy product profile)",
        "api_catalog": "https://api.sap.com/",
    },
    "ORACLE_FUSION_ERP": {
        "provider": "ORACLE",
        "label": "Oracle Fusion Cloud ERP / Financials",
        "api_catalog": "https://docs.oracle.com/en/cloud/saas/financials/26d/api.html",
    },
    "ORACLE_FUSION_SCM": {
        "provider": "ORACLE",
        "label": "Oracle Fusion Cloud SCM / Manufacturing",
        "api_catalog": "https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/api.html",
    },
    "ORACLE_EBS": {
        "provider": "ORACLE",
        "label": "Oracle E-Business Suite (separate legacy product profile)",
        "api_catalog": "https://docs.oracle.com/cd/E26401_01/doc.122/e20923/T291171T509750.htm",
    },
}

# This is a capability catalogue, not a promise that an API/resource is exposed
# in every product or tenant. Every item requires an explicit tenant resource map.
RESOURCE_ENTITY_OPTIONS: dict[str, tuple[str, ...]] = {
    "plant_master": ("Asset", "Process"),
    "work_center_master": ("Asset", "Process"),
    "product_master": ("Product",),
    "material_master": ("Material",),
    "bill_of_materials": ("Material", "Product"),
    "production_orders": ("Order",),
    "production_operations": ("Process", "Order"),
    "production_confirmations": ("Order", "Process"),
    "quality_results": ("Quality",),
    "inventory_balances": ("Material",),
    "material_movements": ("Material",),
    "maintenance_orders": ("Maintenance",),
    "procurement_orders": ("Order", "Material"),
    "cost_records": ("Cost",),
}


class ERPConnectorError(Exception):
    """Sanitized connector error with a stable public error code."""

    def __init__(self, code: str, remediation: str):
        super().__init__(remediation)
        self.code = code
        self.remediation = remediation


@dataclass(frozen=True)
class ERPConnectionProfile:
    product_id: str
    workspace_id: str
    connection_id: str
    tenant_ref: str
    base_url: str
    credential_ref: str
    enabled: bool = False
    read_only: bool = True


@dataclass(frozen=True)
class ERPResourceBinding:
    resource_key: str
    source_path: str
    records_path: str
    entity_type: str
    id_path: str
    field_map: Mapping[str, str]
    required_fields: tuple[str, ...] = ()
    units: Mapping[str, str] = field(default_factory=dict)
    currency_path: str = ""
    source_timestamp_path: str = ""
    source_timezone: str = ""
    mapping_version: str = "1"
    max_records: int = 5000
    max_pages: int = 20


@dataclass(frozen=True)
class TransportPage:
    payload: Any
    next_page_token: str | None = None


class ReadOnlyERPTransport(Protocol):
    """Transport implemented by a provider-aware, policy-enforcing server component.

    This protocol exposes GET only. A production implementation must resolve the
    credential reference server-side and enforce TLS, host allowlists, DNS/IP
    pinning, redirect rejection, timeouts, response-size limits, provider-specific
    auth, rate limits and secret redaction.
    """

    def get_json(
        self,
        connection: ERPConnectionProfile,
        relative_path: str,
        *,
        page_token: str | None,
        page_size: int,
    ) -> TransportPage:
        ...


def _safe_text(value: Any, field_name: str, *, max_length: int = 200) -> str:
    value = str(value or "").strip()
    if not value or len(value) > max_length or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ERPConnectorError("CONFIGURATION_INVALID", f"{field_name} is missing or invalid.")
    return value


def _normalize_host(host: str) -> str:
    try:
        return host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ERPConnectorError("CONFIGURATION_INVALID", "The approved hostname is invalid.") from exc


def _host_port_from_allowlist(value: str) -> tuple[str, int]:
    try:
        parsed = urlsplit("//" + value.strip())
        host = _normalize_host(parsed.hostname or "")
        port = parsed.port if parsed.port is not None else 443
    except (ValueError, ERPConnectorError) as exc:
        raise ERPConnectorError("CONFIGURATION_INVALID", "The hostname allowlist contains an invalid host or port.") from exc
    if not host or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ERPConnectorError("CONFIGURATION_INVALID", "Allowlist entries must be exact hostnames[:port], without URL paths or credentials.")
    if not 1 <= port <= 65535:
        raise ERPConnectorError("CONFIGURATION_INVALID", "An approved port is outside the valid range.")
    return host, port


def _validate_connection(
    connection: ERPConnectionProfile,
    allowed_hosts: set[tuple[str, int]],
) -> tuple[str, int, str]:
    descriptor = PRODUCT_DESCRIPTORS.get(connection.product_id)
    if descriptor is None:
        raise ERPConnectorError("PRODUCT_UNSUPPORTED", "Choose a product ID listed in the supported-products specification.")
    if not connection.enabled:
        raise ERPConnectorError("CONNECTION_DISABLED", "An administrator must enable the reviewed connection before any read is attempted.")
    if not connection.read_only:
        raise ERPConnectorError("READ_ONLY_REQUIRED", "The ERP MVP is read-only; write-enabled connection profiles are refused.")
    if not _safe_text(connection.workspace_id, "workspace reference") or not _safe_text(connection.connection_id, "connection reference"):
        raise ERPConnectorError("CONFIGURATION_INVALID", "A workspace and connection reference are required.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", connection.tenant_ref):
        raise ERPConnectorError("CONFIGURATION_INVALID", "Use an opaque, non-secret tenant reference.")
    if not re.fullmatch(r"(?:env:[A-Z][A-Z0-9_]{2,150}|(?:secret|vault)://[A-Za-z0-9._:/-]{1,400})", connection.credential_ref):
        raise ERPConnectorError("CREDENTIAL_REFERENCE_INVALID", "Use an opaque server-side env:, secret:// or vault:// credential reference; never provide a credential value.")
    try:
        parsed = urlsplit(connection.base_url)
        port = parsed.port if parsed.port is not None else 443
        hostname = _normalize_host(parsed.hostname or "")
    except (ValueError, ERPConnectorError) as exc:
        raise ERPConnectorError("CONFIGURATION_INVALID", "The endpoint hostname or port is invalid.") from exc
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not 1 <= port <= 65535
    ):
        raise ERPConnectorError("CONFIGURATION_INVALID", "The endpoint must be HTTPS with no embedded credentials, query or fragment.")
    path = parsed.path or ""
    if path and (
        not re.fullmatch(r"[A-Za-z0-9._~/-]+", path)
        or "//" in path
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        raise ERPConnectorError("CONFIGURATION_INVALID", "The endpoint path contains unsupported or traversal syntax.")
    if (hostname, port) not in allowed_hosts:
        raise ERPConnectorError("DESTINATION_BLOCKED", "The endpoint does not exactly match the server-side approved hostname and port.")
    return hostname, port, path.rstrip("/")


def _validate_relative_path(path: str, field_name: str) -> str:
    text = str(path or "").strip()
    if (
        not text
        or len(text) > 512
        or text.startswith(("/", "\\"))
        or not re.fullmatch(r"[A-Za-z0-9._~/-]+", text)
        or "//" in text
        or any(part in {".", ".."} for part in text.split("/"))
    ):
        raise ERPConnectorError("RESOURCE_PATH_INVALID", f"{field_name} must be a configured relative API path without query or traversal segments.")
    return text


def _validate_json_path(path: str, field_name: str, *, allow_root: bool = False) -> str:
    text = str(path or "").strip()
    if allow_root and not text:
        return ""
    parts = text.split(".") if text else []
    if not parts or len(text) > 256 or any(
        not re.fullmatch(r"[A-Za-z0-9_@:$-]{1,100}", part) or part in {".", ".."}
        for part in parts
    ):
        raise ERPConnectorError("MAPPING_INVALID", f"{field_name} must be an explicit dot-separated JSON object path.")
    return text


def _extract_path(value: Any, path: str) -> Any:
    if not path:
        return value
    current = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _safe_json_value(value: Any) -> bool:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
        return not isinstance(value, (dict, list))
    except (TypeError, ValueError, OverflowError):
        return False


def _validate_binding(binding: ERPResourceBinding) -> None:
    allowed_entities = RESOURCE_ENTITY_OPTIONS.get(binding.resource_key)
    if allowed_entities is None:
        raise ERPConnectorError("RESOURCE_UNSUPPORTED", "This logical resource is not in the approved MVP capability catalogue.")
    if binding.entity_type not in CANONICAL_ENTITY_TYPES or binding.entity_type not in allowed_entities:
        raise ERPConnectorError("MAPPING_INVALID", "The resource entity type is not valid for this logical capability.")
    _validate_relative_path(binding.source_path, "source path")
    _validate_json_path(binding.records_path, "records path", allow_root=True)
    _validate_json_path(binding.id_path, "source ID path")
    if SENSITIVE_FIELD_PATTERN.search(binding.id_path):
        raise ERPConnectorError(
            "PERSONAL_DATA_FIELD_BLOCKED",
            "A personal identifier cannot be used as the default source key; choose a non-personal business key or obtain a separate privacy-approved design.",
        )
    if not binding.field_map or len(binding.field_map) > 100:
        raise ERPConnectorError("MAPPING_INVALID", "An explicit field map with 1 to 100 fields is required.")
    for canonical_field, source_path in binding.field_map.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", str(canonical_field)):
            raise ERPConnectorError("MAPPING_INVALID", "Canonical field names must use lower_snake_case.")
        if SENSITIVE_FIELD_PATTERN.search(str(canonical_field)) or SENSITIVE_FIELD_PATTERN.search(str(source_path)):
            raise ERPConnectorError("PERSONAL_DATA_FIELD_BLOCKED", "Personal or identifying fields require a separate privacy-approved mapping and are not accepted by this default adapter.")
        _validate_json_path(str(source_path), f"source field map for {canonical_field}")
    if any(field_name not in binding.field_map for field_name in binding.required_fields):
        raise ERPConnectorError("MAPPING_INVALID", "Every required canonical field must exist in field_map.")
    if any(field_name not in binding.field_map for field_name in binding.units):
        raise ERPConnectorError("MAPPING_INVALID", "Units may only be assigned to explicitly mapped fields.")
    if binding.currency_path:
        _validate_json_path(binding.currency_path, "currency path")
    if binding.source_timestamp_path:
        _validate_json_path(binding.source_timestamp_path, "source timestamp path")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,49}", binding.mapping_version):
        raise ERPConnectorError("MAPPING_INVALID", "A valid mapping version is required.")
    if not 1 <= binding.max_records <= 5000 or not 1 <= binding.max_pages <= 100:
        raise ERPConnectorError("LIMIT_INVALID", "The mapping must use 1-5000 records and 1-100 pages per read.")


def _utc_iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def _canonical_record(
    source_record: Mapping[str, Any],
    connection: ERPConnectionProfile,
    binding: ERPResourceBinding,
    imported_at: str,
) -> dict[str, Any] | None:
    source_id = _extract_path(source_record, binding.id_path)
    if source_id is None or isinstance(source_id, (dict, list)) or not str(source_id).strip():
        return None
    fields: dict[str, Any] = {}
    for canonical_field, source_path in binding.field_map.items():
        value = _extract_path(source_record, source_path)
        if value is None:
            continue
        if not _safe_json_value(value):
            raise ERPConnectorError("MAPPING_INVALID", "A mapped field contains an unsupported or non-finite value.")
        fields[canonical_field] = value
    if any(field_name not in fields for field_name in binding.required_fields):
        return None
    currency = None
    if binding.currency_path:
        raw_currency = _extract_path(source_record, binding.currency_path)
        if raw_currency is not None:
            if not isinstance(raw_currency, str) or not re.fullmatch(r"[A-Z]{3}", raw_currency.strip()):
                return None
            currency = raw_currency.strip()
    source_timestamp = None
    if binding.source_timestamp_path:
        raw_timestamp = _extract_path(source_record, binding.source_timestamp_path)
        source_timestamp = _utc_iso(raw_timestamp)
        if raw_timestamp is not None and source_timestamp is None:
            return None
    raw_key = f"{connection.connection_id}|{binding.resource_key}|{source_id}"
    source_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return {
        "entity_type": binding.entity_type,
        "entity_key": f"{binding.entity_type[:3].upper()}-{source_hash[:20].upper()}",
        "fields": fields,
        "lineage": {
            "source_provider": PRODUCT_DESCRIPTORS[connection.product_id]["provider"],
            "source_product": connection.product_id,
            "connection_ref": connection.connection_id,
            "tenant_ref": connection.tenant_ref,
            "workspace_ref": connection.workspace_id,
            "resource_key": binding.resource_key,
            "source_object_hash": source_hash,
            "source_timestamp_utc": source_timestamp,
            "read_at_utc": imported_at,
            "mapping_version": binding.mapping_version,
            "units": {key: value for key, value in binding.units.items() if key in fields},
            "currency": currency,
            "source_timezone": binding.source_timezone or "UNSPECIFIED",
            "validation_status": "VALIDATED",
        },
    }


class ERPReadOnlyAdapter:
    """Provider/product-bound read-only response mapper. No write methods exist."""

    product_id: str

    def read_resource(
        self,
        connection: ERPConnectionProfile,
        binding: ERPResourceBinding,
        transport: ReadOnlyERPTransport,
        *,
        actor_id: str,
        active_workspace_id: str,
        allowed_hosts: set[tuple[str, int]],
        authorize: Callable[[str, str, str, str], bool] | None,
        page_size: int = 250,
    ) -> dict[str, Any]:
        if authorize is None or not callable(authorize):
            raise ERPConnectorError("AUTHORIZATION_REQUIRED", "A server-side authorization check is required before an ERP read.")
        if not _safe_text(actor_id, "actor reference"):
            raise ERPConnectorError("AUTHORIZATION_REQUIRED", "An authenticated actor reference is required.")
        if active_workspace_id != connection.workspace_id:
            raise ERPConnectorError("WORKSPACE_DENIED", "The connection belongs to a different workspace.")
        try:
            authorized = authorize(actor_id, connection.workspace_id, connection.connection_id, binding.resource_key)
        except Exception as exc:
            raise ERPConnectorError(
                "AUTHORIZATION_CHECK_FAILED",
                "Authorization could not be verified; no ERP request was sent. Check the approved access-control service.",
            ) from exc
        if authorized is not True:
            raise ERPConnectorError("ACCESS_DENIED", "The current actor is not authorized for this connection and resource.")
        if connection.product_id != self.product_id:
            raise ERPConnectorError("PRODUCT_MISMATCH", "The selected adapter does not match the connection product.")
        _, _, base_path = _validate_connection(connection, allowed_hosts)
        _validate_binding(binding)
        if not 1 <= page_size <= 1000:
            raise ERPConnectorError("LIMIT_INVALID", "Page size must be between 1 and 1000.")
        if base_path:
            # The transport owns URL construction, but this guard catches accidental
            # absolute-path configuration before a request can be attempted.
            base_path = base_path.rstrip("/")
        if not connection.enabled:
            raise ERPConnectorError("CONNECTION_DISABLED", "The connection is not enabled.")
        imported_at = datetime.now(timezone.utc).isoformat()
        records: list[dict[str, Any]] = []
        seen_tokens: set[str] = set()
        seen_records: dict[str, str] = {}
        conflicting_keys: set[str] = set()
        duplicates = 0
        conflicts = 0
        rejected = 0
        token: str | None = None
        truncated = False
        pages_read = 0
        for page_number in range(binding.max_pages):
            try:
                page = transport.get_json(connection, binding.source_path, page_token=token, page_size=page_size)
            except ERPConnectorError:
                raise
            except Exception as exc:
                # Never include the raw transport exception; it may contain URLs,
                # headers, tokens or customer response fragments.
                raise ERPConnectorError("TRANSPORT_FAILURE", "The provider read failed; inspect approved redacted server-side diagnostics.") from exc
            if not isinstance(page, TransportPage):
                raise ERPConnectorError(
                    "INVALID_TRANSPORT_RESPONSE",
                    "The connector transport returned an invalid page contract; no result was accepted.",
                )
            pages_read += 1
            collection = _extract_path(page.payload, binding.records_path)
            if not isinstance(collection, list):
                raise ERPConnectorError("INVALID_RESPONSE_SCHEMA", "The provider response did not contain the configured record collection.")
            if len(collection) > page_size:
                raise ERPConnectorError("INVALID_RESPONSE_SCHEMA", "The provider returned more records than the configured page bound.")
            for source_record in collection:
                if not isinstance(source_record, Mapping):
                    rejected += 1
                    continue
                try:
                    record = _canonical_record(source_record, connection, binding, imported_at)
                except ERPConnectorError:
                    rejected += 1
                    continue
                if record is None:
                    rejected += 1
                    continue
                key = record["entity_key"]
                digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
                if key in conflicting_keys:
                    conflicts += 1
                    continue
                if key in seen_records:
                    if seen_records[key] == digest:
                        duplicates += 1
                        continue
                    conflicts += 1
                    conflicting_keys.add(key)
                    records = [item for item in records if item["entity_key"] != key]
                    seen_records.pop(key, None)
                    continue
                if len(records) >= binding.max_records:
                    truncated = True
                    break
                seen_records[key] = digest
                records.append(record)
            if truncated:
                break
            next_token = page.next_page_token
            if next_token is None or next_token == "":
                token = None
                break
            if not isinstance(next_token, str) or len(next_token) > 2048 or any(ord(c) < 32 for c in next_token):
                raise ERPConnectorError("INVALID_PAGINATION", "The provider returned an invalid page token.")
            if next_token in seen_tokens or next_token == token:
                raise ERPConnectorError("PAGINATION_LOOP", "The provider repeated a pagination token; the read was stopped.")
            seen_tokens.add(next_token)
            token = next_token
            if page_number == binding.max_pages - 1:
                truncated = True
        else:
            truncated = True
        status = "READ_COMPLETED"
        if not records and not rejected and not duplicates and not conflicts and not truncated:
            status = "EMPTY_DATASET"
        elif rejected or conflicts or truncated:
            status = "PARTIAL_READ"
        digest_input = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return {
            "tool_id": "T096",
            "product_id": self.product_id,
            "resource_key": binding.resource_key,
            "status": status,
            "read_only": True,
            "pages_read": pages_read,
            "record_count": len(records),
            "rejected_record_count": rejected,
            "duplicate_record_count": duplicates,
            "conflicting_duplicate_count": conflicts,
            "truncated": truncated,
            "read_at_utc": imported_at,
            "mapping_version": binding.mapping_version,
            "records_sha256": hashlib.sha256(digest_input.encode("utf-8")).hexdigest(),
            "records": records,
            "warning": "This is a mapped read result, not proof of durable persistence or ongoing synchronization.",
        }


class SAPS4HANACloudPublicAdapter(ERPReadOnlyAdapter):
    product_id = "SAP_S4HANA_CLOUD_PUBLIC"


class SAPS4HANACloudPrivateAdapter(ERPReadOnlyAdapter):
    product_id = "SAP_S4HANA_CLOUD_PRIVATE"


class SAPECCAdapter(ERPReadOnlyAdapter):
    product_id = "SAP_ECC"


class OracleFusionERPAdapter(ERPReadOnlyAdapter):
    product_id = "ORACLE_FUSION_ERP"


class OracleFusionSCMAdapter(ERPReadOnlyAdapter):
    product_id = "ORACLE_FUSION_SCM"


class OracleEBSAdapter(ERPReadOnlyAdapter):
    product_id = "ORACLE_EBS"


_ADAPTER_CLASSES: dict[str, type[ERPReadOnlyAdapter]] = {
    "SAP_S4HANA_CLOUD_PUBLIC": SAPS4HANACloudPublicAdapter,
    "SAP_S4HANA_CLOUD_PRIVATE": SAPS4HANACloudPrivateAdapter,
    "SAP_ECC": SAPECCAdapter,
    "ORACLE_FUSION_ERP": OracleFusionERPAdapter,
    "ORACLE_FUSION_SCM": OracleFusionSCMAdapter,
    "ORACLE_EBS": OracleEBSAdapter,
}


def adapter_for(product_id: str) -> ERPReadOnlyAdapter:
    """Return an explicit product adapter; unsupported products fail closed."""
    adapter_class = _ADAPTER_CLASSES.get(str(product_id or "").strip().upper())
    if adapter_class is None:
        raise ERPConnectorError("PRODUCT_UNSUPPORTED", "No adapter is registered for this exact product ID.")
    return adapter_class()


def product_catalog() -> list[dict[str, str]]:
    """Return non-secret product metadata. This is catalogue information, not live status."""
    return [
        {"product_id": key, "provider": item["provider"], "label": item["label"], "api_catalog": item["api_catalog"], "status": "SPECIFICATION_ONLY_UNCONFIGURED"}
        for key, item in PRODUCT_DESCRIPTORS.items()
    ]
