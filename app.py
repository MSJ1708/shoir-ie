"""Shoir-IE Streamlit entrypoint.

The application runtime is intentionally kept outside this launcher so the
entrypoint remains stable, testable and easy for deployment tooling to invoke.
"""
import shoir_app_runtime  # noqa: F401
