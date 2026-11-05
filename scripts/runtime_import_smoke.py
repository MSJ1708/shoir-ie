"""Execute app.py's top-level import/bootstrap preamble without running the UI.

Streamlit can render a redacted ImportError when one of the application's imports
fails. Compile-only checks miss missing modules and missing imported attributes.
This smoke test executes everything before the first top-level function/class, so
CI reports the real Python exception while avoiding the interactive UI lifecycle.
"""
from __future__ import annotations

import logging
import ast
import sys
import traceback
from pathlib import Path


class _BareStreamlitContextNoticeFilter(logging.Filter):
    """Hide only Streamlit's expected no-runtime notices in this import-only smoke."""

    _expected = (
        "missing ScriptRunContext",
        "Session state does not function when running a script without",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(notice in message for notice in self._expected)


# This smoke intentionally executes app.py outside a Streamlit runtime. These
# two messages describe the test harness, not application runtime failures.
# Keep all other warning/error logging visible.
_bare_context_filter = _BareStreamlitContextNoticeFilter()
for _logger_name in (
    "streamlit.runtime.scriptrunner_utils.script_run_context",
    "streamlit.runtime.state.session_state_proxy",
):
    logging.getLogger(_logger_name).addFilter(_bare_context_filter)


def main() -> int:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(app_path))

    # The app's import preamble includes guarded compatibility imports. Preserve
    # those try/except blocks as-written; stop before any UI or application logic.
    boundary = next(
        (
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ),
        len(tree.body),
    )
    preamble = ast.Module(body=tree.body[:boundary], type_ignores=[])
    ast.fix_missing_locations(preamble)

    namespace = {
        "__name__": "__shoir_runtime_import_smoke__",
        "__file__": str(app_path),
    }
    try:
        exec(compile(preamble, str(app_path), "exec"), namespace)
    except BaseException:
        print(
            f"Runtime import smoke failed while executing app.py's first "
            f"{boundary} top-level statements.",
            file=sys.stderr,
        )
        traceback.print_exc()
        return 1

    print(
        "Runtime import smoke passed: app.py's top-level imports and guarded "
        f"compatibility imports executed ({boundary} statements)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
