"""Smoke tests for the Shoir-IE production application surface."""

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


def test_required_workflow_exists():
    workflow = Path(".github/workflows/shoir-validation.yml")
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")
    assert "compileall" in text
    assert "pytest -q tests" in text
