from benchmark_harness import benchmark_quality
from plugin_registry import execute_plugin, list_plugins

def test_benchmark_harness():
    out=benchmark_quality(1000)
    assert out["rows"] == 1000
    assert out["duration_ms"] >= 0
    assert out["quality_score"] >= 0

def test_plugin_registry_is_explicit_and_safe():
    names={p.name for p in list_plugins()}
    assert "REST connector adapter" in names
    try:
        execute_plugin("REST connector adapter")
    except RuntimeError as exc:
        assert "metadata-only" in str(exc)
    else:
        raise AssertionError("Metadata-only plugin unexpectedly executed")
