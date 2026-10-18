"""Regression tests for shared module export-bar argument compatibility."""

from industrial_platform import _normalize_render_export_args


def test_legacy_positional_tier_and_username_are_normalized():
    figures, tier, username = _normalize_render_export_args(
        "Enterprise", "test_engineer", "unknown"
    )

    assert figures == ()
    assert tier == "Enterprise"
    assert username == "test_engineer"


def test_legacy_positional_tier_with_keyword_username_is_normalized():
    figures, tier, username = _normalize_render_export_args(
        "Enterprise Plus", None, "test_engineer"
    )

    assert figures == ()
    assert tier == "Enterprise Plus"
    assert username == "test_engineer"


def test_explicit_figures_and_tier_are_preserved():
    original_figures = [("KPI comparison", object())]

    figures, tier, username = _normalize_render_export_args(
        original_figures, "Enterprise", "test_engineer"
    )

    assert figures is original_figures
    assert tier == "Enterprise"
    assert username == "test_engineer"


def test_omitted_tier_defaults_to_starter():
    figures, tier, username = _normalize_render_export_args(
        (), None, "test_engineer"
    )

    assert figures == ()
    assert tier == "Starter"
    assert username == "test_engineer"
