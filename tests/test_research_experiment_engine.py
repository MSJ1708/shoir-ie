import numpy as np

from research_experiment_engine import (
    CONFLICT_MIX_WEIGHT,
    CONFLICT_SIGNAL_BIAS,
    apply_evidence_conflict,
)


def test_zero_conflict_preserves_evidence():
    latent = np.array([100.0, 120.0, 140.0])
    evidence = np.array([98.0, 121.0, 141.0])
    rng = np.random.default_rng(2026)

    out, mask = apply_evidence_conflict(latent, evidence, 0, rng)

    assert not mask.any()
    assert np.array_equal(out, evidence)


def test_conflict_changes_finite_observations_and_is_counterbalanced():
    latent = np.full(4000, 120.0)
    evidence = latent.copy()
    rng = np.random.default_rng(2026)

    out, mask = apply_evidence_conflict(latent, evidence, 10, rng)

    assert 250 <= int(mask.sum()) <= 550
    changed = np.flatnonzero(~np.isclose(out, evidence, rtol=0, atol=1e-12))
    assert len(changed) > 0
    assert set(changed.tolist()).issubset(set(np.flatnonzero(mask).tolist()))

    shifts = out[changed] - evidence[changed]
    assert np.any(shifts < 0)
    assert np.any(shifts > 0)

    # At baseline evidence==latent demand, the 50/50 blend with a
    # +/-20% contradictory signal yields a +/-10% net shift.
    assert np.isclose(np.abs(shifts), 120.0 * CONFLICT_SIGNAL_BIAS * CONFLICT_MIX_WEIGHT).all()


def test_conflict_assignment_is_reproducible():
    latent = np.full(1000, 120.0)
    evidence = latent.copy()

    out1, mask1 = apply_evidence_conflict(latent, evidence, 10, np.random.default_rng(2026))
    out2, mask2 = apply_evidence_conflict(latent, evidence, 10, np.random.default_rng(2026))

    assert np.array_equal(mask1, mask2)
    assert np.array_equal(out1, out2)
