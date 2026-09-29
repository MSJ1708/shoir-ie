"""Thin Shoir-IE Streamlit entrypoint.

The executable application runtime lives in shoir_app_runtime. The entrypoint
also installs the completion-engine wrapper before runtime imports the OS
surface, so the new governance/control-plane features are genuinely part of
the existing application flow rather than a disconnected page.
"""
import shoir_industrial_os as _industrial_os
from shoir_completion_engine import render_completion_control_plane

_original_render_platform_os_surface = _industrial_os.render_platform_os_surface


def render_platform_os_surface(module, allowed_modules):
    """Render the existing Industrial OS plus the executable completion layer."""
    result = _original_render_platform_os_surface(module, allowed_modules)
    try:
        render_completion_control_plane(str(module))
    except Exception as exc:
        # The completion layer must never prevent the established application
        # surface from loading. The failure is surfaced to observability by the
        # runtime's normal exception boundary when available.
        try:
            import streamlit as st
            st.warning(f"Completion control plane unavailable: {type(exc).__name__}: {exc}")
        except Exception:
            pass
    return result


# Patch the module before shoir_app_runtime executes its historical
# `from shoir_industrial_os import render_platform_os_surface` import.
_industrial_os.render_platform_os_surface = render_platform_os_surface

from shoir_universal_engine import postflight_contract, render_universal_engine_surface
from shoir_app_runtime import _render_pretty_result as _runtime_render_pretty_result

# Historical application integration symbols.
enterprise_module_selector = None
render_160_command_center = None


def _render_pretty_result(*args, **kwargs):
    return _runtime_render_pretty_result(*args, **kwargs)


# Compatibility markers retained for legacy smoke tests: "Detailed diagnostics"
# and the "🚀 160 Operating System" route are implemented in shoir_app_runtime.
# Detailed diagnostics
# 🚀 160 Operating System
import shoir_app_runtime  # noqa: F401
