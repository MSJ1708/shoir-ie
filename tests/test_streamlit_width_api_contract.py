"""Guard the main Workbench against deprecated Streamlit width parameters."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_industrial_workbench_uses_current_width_api():
    source = (ROOT / "pages" / "Industrial_Engineering_Workbench.py").read_text(
        encoding="utf-8"
    )
    assert "use_container_width=" not in source
    assert 'width="stretch"' in source
    assert 'width="content"' in source
