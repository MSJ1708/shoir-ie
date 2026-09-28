from pathlib import Path

import pandas as pd

from shoir_universal_platform_kernel import (
    GROUPED_160_VIEWS,
    PROVENANCE_STATES,
    WORKFLOW_STEPS,
    cached_profile,
    dataset_hash,
    domain_engine_metadata,
    paginate_dataframe,
    readiness_snapshot,
)


def test_universal_workflow_contract_is_complete():
    assert WORKFLOW_STEPS == (
        "DATA", "VALIDATE", "MODEL", "RUN", "VISUALIZE",
        "COMPARE", "EXPLAIN", "DECIDE", "EXPORT", "VERIFY",
    )


def test_grouped_160_navigation_has_four_workspaces():
    assert tuple(GROUPED_160_VIEWS) == ("Work", "Intelligence", "Governance", "Platform")
    assert sum(len(v) for v in GROUPED_160_VIEWS.values()) == 10


def test_160_renderer_uses_grouped_navigation():
    source = Path("shoir_160.py").read_text(encoding="utf-8")
    assert "Compact navigation: four grouped workspaces" in source
    assert 'tabs=st.tabs(["⚡ Command Center"' not in source


def test_provenance_contract_is_explicit():
    assert PROVENANCE_STATES == ("LIVE", "IMPORTED", "SIMULATED", "DEMO")


def test_profile_is_deterministic_and_cached():
    df = pd.DataFrame({"Asset": ["A", "B", "B"], "Qty": [10, None, 10]})
    first = cached_profile(df)
    second = cached_profile(df)
    assert first["fingerprint"] == second["fingerprint"] == dataset_hash(df)
    assert first["rows"] == 3
    assert first["missing_pct"] > 0
    assert first["duplicate_pct"] > 0


def test_pagination_is_bounded():
    df = pd.DataFrame({"x": range(605)})
    page, number, total = paginate_dataframe(df, page=3, page_size=250)
    assert number == 3
    assert total == 3
    assert len(page) == 105


def test_engine_contract_declares_common_lifecycle():
    meta = domain_engine_metadata("Fleet Routing")
    assert meta["lifecycle"] == list(WORKFLOW_STEPS)
    assert meta["provenance_required"] is True
    assert meta["reproducibility_required"] is True


def test_readiness_empty_dataset_is_safe():
    snap = readiness_snapshot(pd.DataFrame())
    assert snap["rows"] == 0
    assert snap["score"] == 0.0
    assert snap["warnings"]


def test_hash_is_sha256_length():
    df = pd.DataFrame({"x": [1, 2, 3]})
    digest = dataset_hash(df)
    assert len(digest) == 64
    int(digest, 16)
