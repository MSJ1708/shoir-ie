# ShadowShift — Micro-Loss & Recovery Intelligence

ShadowShift is an Enterprise-tier Shoir-IE workspace for recording operational interruptions, separating recovery-to-stable-work time, investigating evidence gaps, registering small experiments, and exporting a traceable study.

## Existing Shoir-IE capabilities it extends

- Workforce Engineering: takt, staffing and line balance.
- Manufacturing Execution System: execution and downtime events.
- Experiment Engine / Experiment Lab: designed experiments and scenario comparisons.
- Engineering Decision Center: governed decisions.
- Value Evidence Engine: task-time baselines and financial value tracking.

The repository contained related capabilities, but not one unified micro-loss workspace linking interruption and recovery records to evidence strength, ranked next observations, a registered experiment and an evidence-hashed snapshot.

## Method and boundaries

- Interruption and recovery are recorded separately.
- Observed elapsed burden = sum(interruption minutes + recovery minutes).
- People-weighted labor minutes = sum((interruption + recovery) × people affected).
- Projected per-shift burden = observed burden ÷ observation-window minutes × nominal shift minutes.
- Annual gross labor exposure = projected people-weighted hours per shift × shifts per year × supplied loaded hourly labor cost.
- A downstream stress factor creates a separate scenario-only increment; it is excluded from the labor-cost calculation.
- Next-experiment priority is a transparent heuristic using burden, evidence gap, event count and estimated test effort.

Outputs are estimates, not savings or verified causal effects. Small or unrepresentative samples can mislead. Use matched tests, preserve limitations and replicate results before changing standard work.

## Data and privacy

Study, event, experiment and snapshot records are stored in enterprise_full_workspace.db. Reads and writes are scoped by authenticated owner and study ID. CSV/XLSX imports are normalized before saving. The module has no external AI service dependency.

## Tests

Run pytest tests/test_shoir_shadowshift.py. Tests cover calculations, normalization, no-data behavior, experiment ranking, persistence and account-level isolation.
