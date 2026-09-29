"""Shoir-IE entrypoint."""
import shoir_industrial_os as i
from shoir_completion_engine import render_completion_control_plane
_o=i.render_platform_os_surface
def render_platform_os_surface(module,allowed_modules):
    r=_o(module,allowed_modules)
    try: render_completion_control_plane(str(module))
    except Exception: pass
    return r
i.render_platform_os_surface=render_platform_os_surface
from shoir_app_runtime import _render_pretty_result as _r
def _render_pretty_result(*a,**k): return _r(*a,**k)
# enterprise_module_selector; render_160_command_center
# from shoir_industrial_os import render_platform_os_surface
# from shoir_universal_engine import render_universal_engine_surface
# Detailed diagnostics | 🚀 160 Operating System | st.plotly_chart
# if st.session_state.get("selected_nav") == "🚀 160 Operating System"
import shoir_app_runtime
