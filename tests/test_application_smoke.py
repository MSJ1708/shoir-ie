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
