"""Thin Shoir-IE Streamlit entrypoint.

The executable application runtime lives in shoir_app_runtime. These imports
preserve the historical public integration surface while keeping the entrypoint
small and testable.
"""
from shoir_industrial_os import render_platform_os_surface
from shoir_universal_engine import postflight_contract, render_universal_engine_surface
from shoir_app_runtime import _render_pretty_result as _runtime_render_pretty_result

# Historical application integration symbols.
enterprise_module_selector = None
render_160_command_center = None


def _render_pretty_result(*args, **kwargs):
    return _runtime_render_pretty_result(*args, **kwargs)


# The runtime contains the detailed diagnostics, Plotly surfaces and 160 route.
import shoir_app_runtime  # noqa: F401
