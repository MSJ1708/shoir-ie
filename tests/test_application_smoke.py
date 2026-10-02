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
    assert "Detailed diagnostics" in source
    assert "st.plotly_chart" in source


def test_streamlit_application_starts_without_runtime_exception():
    """Exercise the actual Streamlit script, not only imports and source checks."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30)
    at.run(timeout=30)
    assert not at.exception, "\n".join(str(e.value) for e in at.exception)



def test_160_operating_system_route_is_wired():
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert '"🚀 160 Operating System"' in app_source
    assert "render_160_command_center" in app_source
    assert 'if st.session_state.get("selected_nav") == "🚀 160 Operating System"' in app_source


def test_module_explorer_is_outcome_led_and_keeps_external_context():
    source = Path("app.py").read_text(encoding="utf-8")
    required = [
        "Explore the Modules",
        "What it helps you do",
        "Where it helps",
        "Illustrative example",
        "Why this is becoming a bigger industrial buying priority",
        "https://www.nist.gov/publications/2026-roadmap-artificial-intelligence-and-machine-learning-smart-manufacturing",
        "https://www.weforum.org/press/2026/06/new-global-lighthouse-sites-demonstrate-how-ai-is-rewiring-manufacturing-and-supply-chains/",
        "https://www.unilever.com/news/news-search/2026/unilever-x-accenture-partnership-scales-digital-twins/",
        "https://press.siemens.com/global/en/pressrelease/siemens-unveils-technologies-accelerate-industrial-ai-revolution-ces-2026",
        "https://www.reuters.com/world/china/global-economy-asian-factory-activity-expands-thanks-global-ai-boom-2026-10-01/",
    ]
    for marker in required:
        assert marker in source, f"Module explorer is missing required customer-facing element: {marker}"
