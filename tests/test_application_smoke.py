"""Production smoke tests for the Shoir-IE application surface."""

from pathlib import Path
import ast

REQUIRED_MODULES = (
    "app.py",
    "industrial_platform.py",
    "industrial_platform_excellence.py",
    "industrial_operating_system.py",
    "shoir_upgrade.py",
)


def test_required_modules_parse():
    for filename in REQUIRED_MODULES:
        path = Path(filename)
        assert path.exists(), f"Missing required application module: {filename}"
        ast.parse(path.read_text(encoding="utf-8"), filename=filename)


def test_validation_workflow_covers_compile_and_tests():
    workflow = Path(".github/workflows/shoir-validation.yml").read_text(encoding="utf-8")
    assert "compileall" in workflow
    assert "pytest -q tests" in workflow


def test_platform_catalog_has_render_path():
    """Every catalog module must be wired to an application rendering path."""
    from industrial_platform import PLATFORM_CATALOG
    platform_source = Path("industrial_platform.py").read_text(encoding="utf-8")
    app_source = Path("app.py").read_text(encoding="utf-8")
    for item in PLATFORM_CATALOG:
        name = str(item.get("name", "")).strip()
        assert name, "Catalog contains a module without a name"
        assert (f'"{name}"' in platform_source) or (f'"{name}"' in app_source), (
            f"Catalog module is not wired into the application: {name}"
        )


def test_polished_results_surface_is_wired():
    """Guard against regressions to raw implementation-style result output."""
    source = Path("app.py").read_text(encoding="utf-8")
    assert "def _render_pretty_result" in source
    assert "enterprise_module_selector" in source
    assert "Technical Details" in source
    assert "st.plotly_chart" in source
