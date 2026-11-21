"""Versioned, validated extension registry for Shoir-IE.

A plugin is executable only when a server-side Python handler is explicitly
registered. Metadata-only entries never appear as runnable operations. This
registry is a local SDK contract; it is not itself a publicly hosted REST API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from typing import Any, Callable, Mapping, Sequence


_ALLOWED_SCHEMA_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


@dataclass(frozen=True)
class PluginSpec:
    name: str
    category: str
    version: str = "1.0.0"
    enabled: bool = True
    description: str = ""
    api_version: str = "v1"
    required_scopes: tuple[str, ...] = ()
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    max_payload_bytes: int = 65536


_REGISTRY: dict[str, PluginSpec] = {}
_HANDLERS: dict[str, Callable[..., Any]] = {}


def _validate_schema(schema: Mapping[str, Any], value: Any, path: str = "$") -> None:
    """Validate the intentionally small JSON Schema subset supported by the SDK."""
    if not isinstance(schema, Mapping):
        raise ValueError(f"Plugin schema at {path} must be an object.")
    expected_type = schema.get("type")
    if expected_type is not None:
        if expected_type not in _ALLOWED_SCHEMA_TYPES:
            raise ValueError(f"Plugin schema at {path} uses an unsupported type.")
        valid = {
            "object": lambda v: isinstance(v, Mapping),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
        }[expected_type](value)
        if not valid:
            raise ValueError(f"{path} must be of type {expected_type}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of the configured enum values.")
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if not isinstance(required, list) or not isinstance(properties, Mapping):
            raise ValueError(f"Plugin object schema at {path} has an invalid required/properties declaration.")
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"{path} is missing required properties: {', '.join(map(str, missing))}.")
        if schema.get("additionalProperties", True) is False:
            unknown = [key for key in value if key not in properties]
            if unknown:
                raise ValueError(f"{path} contains unsupported properties: {', '.join(map(str, unknown))}.")
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema(child_schema, value[key], f"{path}.{key}")
    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if minimum is not None and len(value) < int(minimum):
            raise ValueError(f"{path} must contain at least {int(minimum)} items.")
        if maximum is not None and len(value) > int(maximum):
            raise ValueError(f"{path} must contain no more than {int(maximum)} items.")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                _validate_schema(item_schema, item, f"{path}[{index}]")
    if isinstance(value, str):
        if schema.get("minLength") is not None and len(value) < int(schema["minLength"]):
            raise ValueError(f"{path} is shorter than the configured minimum length.")
        if schema.get("maxLength") is not None and len(value) > int(schema["maxLength"]):
            raise ValueError(f"{path} exceeds the configured maximum length.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if schema.get("minimum") is not None and value < float(schema["minimum"]):
            raise ValueError(f"{path} is below the configured minimum.")
        if schema.get("maximum") is not None and value > float(schema["maximum"]):
            raise ValueError(f"{path} exceeds the configured maximum.")


def validate_plugin_payload(spec: PluginSpec, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Plugin input must be a JSON object.")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Plugin input must contain JSON-safe values only.") from exc
    if len(encoded) > spec.max_payload_bytes:
        raise ValueError(f"Plugin input exceeds the {spec.max_payload_bytes}-byte payload limit.")
    if spec.input_schema:
        _validate_schema(spec.input_schema, payload)
    return dict(payload)


def _validate_schema_definition(schema: Mapping[str, Any], path: str = "$") -> None:
    if not isinstance(schema, Mapping):
        raise ValueError(f"Plugin schema at {path} must be an object.")
    expected_type = schema.get("type")
    if expected_type is not None and expected_type not in _ALLOWED_SCHEMA_TYPES:
        raise ValueError(f"Plugin schema at {path} uses an unsupported type.")
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ValueError(f"Plugin schema properties at {path} must be an object.")
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise ValueError(f"Plugin schema required at {path} must be a string list.")
    enum = schema.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum):
        raise ValueError(f"Plugin schema enum at {path} must be a non-empty list.")
    if schema.get("items") is not None:
        _validate_schema_definition(schema["items"], path + "[]")
    for key, child in properties.items():
        _validate_schema_definition(child, path + "." + str(key))


def register_plugin(spec: PluginSpec, handler: Callable[..., Any] | None = None) -> None:
    if not isinstance(spec, PluginSpec):
        raise TypeError("Register a PluginSpec instance.")
    if not spec.name.strip():
        raise ValueError("Plugin name is required.")
    if not spec.category.strip():
        raise ValueError("Plugin category is required.")
    if spec.api_version != "v1":
        raise ValueError("Only the v1 local plugin contract is currently supported.")
    if isinstance(spec.max_payload_bytes, bool) or not 1 <= int(spec.max_payload_bytes) <= 1_048_576:
        raise ValueError("Plugin max_payload_bytes must be between 1 and 1,048,576.")
    if not isinstance(spec.required_scopes, tuple) or any(
        not isinstance(scope, str) or not scope.strip() for scope in spec.required_scopes
    ):
        raise ValueError("Plugin required_scopes must be a tuple of non-empty scope names.")
    if spec.input_schema:
        _validate_schema_definition(spec.input_schema)
    if spec.output_schema:
        _validate_schema_definition(spec.output_schema)
    _REGISTRY[spec.name] = spec
    if handler is None:
        _HANDLERS.pop(spec.name, None)
    else:
        if not callable(handler):
            raise TypeError("Plugin handler must be callable.")
        _HANDLERS[spec.name] = handler


def list_plugins() -> list[PluginSpec]:
    return sorted(_REGISTRY.values(), key=lambda item: (item.category.casefold(), item.name.casefold()))


def get_plugin(name: str) -> PluginSpec | None:
    return _REGISTRY.get(name)


def plugin_manifest() -> list[dict[str, Any]]:
    """Return a public-safe manifest; handler internals and secrets are never exposed."""
    return [
        {
            "name": spec.name,
            "category": spec.category,
            "version": spec.version,
            "api_version": spec.api_version,
            "enabled": spec.enabled,
            "description": spec.description,
            "required_scopes": list(spec.required_scopes),
            "input_schema": dict(spec.input_schema),
            "output_schema": dict(spec.output_schema),
            "max_payload_bytes": spec.max_payload_bytes,
            "execution_status": "EXECUTABLE" if spec.name in _HANDLERS else "METADATA_ONLY",
        }
        for spec in list_plugins()
    ]


def _require_scopes(spec: PluginSpec, scopes: Sequence[str]) -> None:
    supplied = {str(scope).strip() for scope in scopes if str(scope).strip()}
    missing = sorted(set(spec.required_scopes) - supplied)
    if missing:
        raise PermissionError("Plugin execution requires scopes: " + ", ".join(missing))


def execute_plugin(name: str, *args: Any, scopes: Sequence[str] = (), **kwargs: Any) -> Any:
    spec = _REGISTRY.get(name)
    handler = _HANDLERS.get(name)
    if spec is None:
        raise KeyError(f"Unknown plugin: {name}")
    if not spec.enabled:
        raise RuntimeError(f"Plugin is disabled: {name}")
    if handler is None:
        raise RuntimeError(f"Plugin is metadata-only until an adapter is installed: {name}")
    _require_scopes(spec, scopes)
    if kwargs and spec.input_schema:
        validated = validate_plugin_payload(spec, kwargs)
        result = handler(*args, **validated)
    else:
        result = handler(*args, **kwargs)
    if spec.output_schema:
        _validate_schema(spec.output_schema, result, "$.output")
    return result


def execute_plugin_payload(
    name: str,
    payload: Mapping[str, Any],
    *,
    scopes: Sequence[str] = (),
) -> Any:
    """Execute a versioned JSON-object plugin with schema, payload and scope checks."""
    spec = _REGISTRY.get(name)
    handler = _HANDLERS.get(name)
    if spec is None:
        raise KeyError(f"Unknown plugin: {name}")
    if not spec.enabled:
        raise RuntimeError(f"Plugin is disabled: {name}")
    if handler is None:
        raise RuntimeError(f"Plugin is metadata-only until an adapter is installed: {name}")
    _require_scopes(spec, scopes)
    validated = validate_plugin_payload(spec, payload)
    result = handler(validated)
    if spec.output_schema:
        _validate_schema(spec.output_schema, result, "$.output")
    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError("Plugin output must be JSON-safe.") from exc
    return result


for _spec in [
    PluginSpec(
        "REST connector adapter",
        "Connectivity",
        description="Metadata contract for REST integrations; requires a separately configured endpoint and credentials.",
    ),
    PluginSpec(
        "MQTT connector adapter",
        "Connectivity",
        description="Metadata contract for MQTT integrations; requires a separately configured broker and credentials.",
    ),
    PluginSpec(
        "OPC-UA connector adapter",
        "Connectivity",
        description="Metadata contract for OPC-UA integrations; requires a separately configured endpoint and certificate trust.",
    ),
    PluginSpec(
        "ERP adapter",
        "Enterprise",
        description="Metadata contract for ERP integrations; does not connect to SAP/Oracle without external configuration.",
    ),
]:
    register_plugin(_spec)
