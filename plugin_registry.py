"""Small, dependency-free extension registry used by Shoir-IE.

Plugins are metadata-only until an explicit adapter is registered. This avoids
fake integrations while giving the platform a stable extension contract.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any

@dataclass(frozen=True)
class PluginSpec:
    name: str
    category: str
    version: str = "1.0.0"
    enabled: bool = True
    description: str = ""

_REGISTRY: dict[str, PluginSpec] = {}
_HANDLERS: dict[str, Callable[..., Any]] = {}

def register_plugin(spec: PluginSpec, handler: Callable[..., Any] | None = None) -> None:
    if not spec.name.strip():
        raise ValueError("Plugin name is required.")
    _REGISTRY[spec.name] = spec
    if handler is not None:
        _HANDLERS[spec.name] = handler

def list_plugins() -> list[PluginSpec]:
    return list(_REGISTRY.values())

def get_plugin(name: str) -> PluginSpec | None:
    return _REGISTRY.get(name)

def execute_plugin(name: str, *args: Any, **kwargs: Any) -> Any:
    spec = _REGISTRY.get(name)
    handler = _HANDLERS.get(name)
    if spec is None:
        raise KeyError(f"Unknown plugin: {name}")
    if not spec.enabled:
        raise RuntimeError(f"Plugin is disabled: {name}")
    if handler is None:
        raise RuntimeError(f"Plugin is metadata-only until an adapter is installed: {name}")
    return handler(*args, **kwargs)

for _spec in [
    PluginSpec("REST connector adapter","Connectivity",description="Metadata contract for REST integrations."),
    PluginSpec("MQTT connector adapter","Connectivity",description="Metadata contract for MQTT integrations."),
    PluginSpec("OPC-UA connector adapter","Connectivity",description="Metadata contract for OPC-UA integrations."),
    PluginSpec("ERP adapter","Enterprise",description="Metadata contract for ERP integrations."),
]:
    register_plugin(_spec)
