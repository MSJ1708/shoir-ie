"""Deterministic research-experiment primitives for Shoir-IE.

The evidence-conflict factor is defined as the probability that an otherwise
finite evidence observation is blended 50/50 with a contradictory signal that
is 20% above or below latent demand. The sign is counterbalanced by row index
so the treatment does not introduce a systematic upward or downward bias.
"""
from __future__ import annotations

import numpy as np

CONFLICT_SIGNAL_BIAS = 0.20
CONFLICT_MIX_WEIGHT = 0.50


def apply_evidence_conflict(
    latent_demand: np.ndarray,
    evidence: np.ndarray,
    conflict_pct: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply a controlled, balanced contradictory-evidence treatment.

    Parameters
    ----------
    latent_demand:
        Ground-truth demand used by the simulator.
    evidence:
        Current evidence after freshness/uncertainty/missingness processing.
    conflict_pct:
        Percentage of observations receiving a conflicting signal.
    rng:
        Experiment RNG. Only the conflict assignment consumes random draws;
        the contradictory direction is deterministic and counterbalanced.

    Returns
    -------
    evidence_with_conflict, conflict_mask
    """
    latent = np.asarray(latent_demand, dtype=float)
    out = np.asarray(evidence, dtype=float).copy()

    if latent.shape != out.shape:
        raise ValueError("latent_demand and evidence must have the same shape.")
    if not 0.0 <= float(conflict_pct) <= 100.0:
        raise ValueError("conflict_pct must be between 0 and 100.")

    mask = rng.random(out.size) < (float(conflict_pct) / 100.0)
    finite_conflict = mask & np.isfinite(out)

    if np.any(finite_conflict):
        direction = np.where(np.arange(out.size) % 2 == 0, -1.0, 1.0)
        contradictory_signal = latent * (1.0 + direction * CONFLICT_SIGNAL_BIAS)
        out[finite_conflict] = (
            (1.0 - CONFLICT_MIX_WEIGHT) * out[finite_conflict]
            + CONFLICT_MIX_WEIGHT * contradictory_signal[finite_conflict]
        )

    return out, mask
