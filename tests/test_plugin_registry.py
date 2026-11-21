from __future__ import annotations

import pytest

from plugin_registry import (
    PluginSpec,
    execute_plugin_payload,
    get_plugin,
    plugin_manifest,
    register_plugin,
)


def test_plugin_payload_enforces_versioned_input_schema_and_scopes():
    spec = PluginSpec(
        name="test.capacity-check",
        category="tests",
        api_version="v1",
        required_scopes=("workspaces:read",),
        input_schema={
            "type": "object",
            "required": ["capacity", "demand"],
            "additionalProperties": False,
            "properties": {
                "capacity": {"type": "number", "minimum": 0},
                "demand": {"type": "number", "minimum": 0},
            },
        },
        output_schema={
            "type": "object",
            "required": ["gap", "status"],
            "additionalProperties": False,
            "properties": {
                "gap": {"type": "number"},
                "status": {"type": "string", "enum": ["SURPLUS", "SHORTAGE", "BALANCED"]},
            },
        },
    )

    def handler(payload):
        gap = payload["capacity"] - payload["demand"]
        return {
            "gap": gap,
            "status": "SURPLUS" if gap > 0 else "SHORTAGE" if gap < 0 else "BALANCED",
        }

    register_plugin(spec, handler)
    result = execute_plugin_payload(
        spec.name,
        {"capacity": 120, "demand": 100},
        scopes=("workspaces:read",),
    )
    assert result == {"gap": 20, "status": "SURPLUS"}


def test_plugin_payload_rejects_missing_scope_schema_errors_and_extra_fields():
    spec = PluginSpec(
        name="test.scoped-plugin",
        category="tests",
        required_scopes=("datasets:read",),
        input_schema={
            "type": "object",
            "required": ["dataset_id"],
            "additionalProperties": False,
            "properties": {"dataset_id": {"type": "string", "minLength": 1}},
        },
    )
    register_plugin(spec, lambda payload: {"ok": True})
    with pytest.raises(PermissionError, match="datasets:read"):
        execute_plugin_payload(spec.name, {"dataset_id": "DS-1"})
    with pytest.raises(ValueError, match="missing required"):
        execute_plugin_payload(spec.name, {}, scopes=("datasets:read",))
    with pytest.raises(ValueError, match="unsupported properties"):
        execute_plugin_payload(
            spec.name,
            {"dataset_id": "DS-1", "owner": "other"},
            scopes=("datasets:read",),
        )


def test_plugin_manifest_distinguishes_metadata_only_from_executable():
    metadata = PluginSpec(
        name="test.metadata-only",
        category="tests",
        description="No installed adapter.",
    )
    register_plugin(metadata)
    rows = {item["name"]: item for item in plugin_manifest()}
    assert rows[metadata.name]["execution_status"] == "METADATA_ONLY"
    assert rows["REST connector adapter"]["execution_status"] == "METADATA_ONLY"
    assert get_plugin(metadata.name) == metadata


def test_plugin_disabled_and_invalid_schema_or_payload_are_rejected():
    disabled = PluginSpec(
        name="test.disabled",
        category="tests",
        enabled=False,
    )
    register_plugin(disabled, lambda payload: payload)
    with pytest.raises(RuntimeError, match="disabled"):
        execute_plugin_payload(disabled.name, {})

    with pytest.raises(ValueError, match="unsupported type"):
        register_plugin(PluginSpec(
            name="test.invalid-schema",
            category="tests",
            input_schema={"type": "function"},
        ))

    bounded = PluginSpec(
        name="test.bounded",
        category="tests",
        max_payload_bytes=12,
        input_schema={"type": "object"},
    )
    register_plugin(bounded, lambda payload: {"ok": True})
    with pytest.raises(ValueError, match="payload limit"):
        execute_plugin_payload(bounded.name, {"message": "this is too long"})
