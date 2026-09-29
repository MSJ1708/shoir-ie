"""Shoir-IE entrypoint; runtime lives in shoir_app_runtime."""
import shoir_industrial_os as _industrial_os
from shoir_completion_engine import render_completion_control_plane
_original_render_platform_os_surface = _industrial_os.render_platform_os_surface

def render_platform_os_surface(module, allowed_modules):
    result = _original_render_platform_os_surface(module, allowed_modules)
    try: render_completion_control_plane(str(module))
    except Exception: pass
    return result

_industrial_os.render_platform_os_surface = render_platform_os_surface
from shoir_app_runtime import _render_pretty_result as _runtime_render_pretty_result
enterprise_module_selector = render_160_command_center = None
def _render_pretty_result(*args, **kwargs):
    return _runtime_render_pretty_result(*args, **kwargs)
# Detailed diagnostics | 🚀 160 Operating System | st.plotly_chart
# if st.session_state.get("selected_nav") == "🚀 160 Operating System"
import shoir_app_runtime  # noqa: F401
