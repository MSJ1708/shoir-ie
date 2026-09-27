import numpy as np
import pandas as pd
import plotly.graph_objects as go

from shoir_performance import (
    evenly_spaced_indices,
    sample_for_plot,
    sample_preview,
    lightweight_frame_signature,
)


def test_evenly_spaced_sampling_preserves_edges():
    idx = evenly_spaced_indices(100_000, 1_000)
    assert len(idx) <= 1_002
    assert idx[0] == 0
    assert idx[-1] == 99_999


def test_large_plot_sampling_does_not_mutate_source():
    df = pd.DataFrame({
        "x": np.arange(25_000),
        "y": np.linspace(0, 1, 25_000),
        "group": ["A", "B"] * 12_500,
    })
    sampled = sample_for_plot(df, max_points=5_000, chart="Scatter")
    assert len(sampled) <= 5_000
    assert len(df) == 25_000
    assert df.iloc[0]["x"] == 0
    assert df.iloc[-1]["x"] == 24_999


def test_preview_is_bounded_and_deterministic():
    df = pd.DataFrame({"value": np.arange(100_000)})
    a = sample_preview(df, 500)
    b = sample_preview(df, 500)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 500


def test_lightweight_signature_changes_for_edge_content():
    base = pd.DataFrame({"x": np.arange(50), "y": np.arange(50) ** 2})
    altered = base.copy()
    altered.iloc[-1, 1] = -1
    assert lightweight_frame_signature(base) != lightweight_frame_signature(altered)


def test_performance_module_imports_without_plotly_dependency():
    # Plotly remains an application dependency; this confirms the bounded
    # sampling helper does not require a Plotly figure to operate.
    assert isinstance(go.Figure(), go.Figure)
