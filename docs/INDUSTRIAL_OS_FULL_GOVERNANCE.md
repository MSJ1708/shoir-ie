# Shoir-IE Industrial OS — Full Governance

This branch establishes the Industrial OS governance layer as an executable cross-module contract around the existing specialist engineering engines.

## Universal module contract

Every selected module is wrapped at the common runtime boundary by:

`DATA → VALIDATE → MAP → MODEL → RUN → VISUALIZE → COMPARE → EXPLAIN → DECIDE → EXPORT → VERIFY`

The contract is persisted as a `module_contract` record with:
- machine-readable manifest fields
- manifest completeness
- validation gate state
- per-stage status and evidence
- KPI lineage IDs
- verification outcome
- workspace and actor
- completion percentage

A module with its own input UI is explicitly recorded as `MODULE_MANAGED` rather than being falsely labelled imported data.

## Capability evidence

Capability state is conservative:
- `Verified` requires a complete manifest, a completed module contract, and a persisted PASS verification record.
- `Implemented` means the capability exists but still needs capability-specific verification evidence.
- `Foundation` means supporting infrastructure is present but the capability itself is not complete.
- `Integration-ready` means configuration/deployment is required before a live claim is valid.

## Replay

Replay records capture callable path, parameters, dataset fingerprint, expected result fingerprint, Python/numpy/pandas versions and optional seed. Replays refuse an input fingerprint mismatch and report PASS/DRIFT when a result fingerprint can be compared.

## Distributed execution

`shoir_worker.py` provides a separate worker process for callable jobs stored in the Postgres queue. The runtime can continue to use the local executor for development/offline use.

Example:

`python -m shoir_worker --workspace default`

## Engineering analysis services

The governed core includes:
- full and fractional factorial DOE
- central-composite and Box-Behnken designs
- transparent quadratic response surfaces
- replication planning
- Monte Carlo, bootstrap and sensitivity analysis
- forecast model comparison, backtesting, MAPE, prediction intervals, decomposition and drift monitoring
- dimensional unit derivation and secure formula evaluation
- scenario constraint analysis with best/worst and driver tables
- KPI evidence lineage
- decision memory
- alert → investigation → simulation → decision chaining
- benchmark provenance/versioning
- accessibility/localization configuration
- Executive / Engineering / Audit / Research evidence-pack manifests

## Persistence posture

PostgreSQL/Supabase is authoritative whenever a trusted database URL is configured. SQLite remains the compatibility/offline fallback. The platform-owned repository tables are `shoir_platform_records`, `shoir_platform_events`, and `shoir_platform_jobs`.

Live SAP, Oracle, MES, WMS, MQTT, OPC-UA, REST and SFTP behavior remains configuration-dependent: the code supplies connector implementations and health/fetch contracts, while a production connection requires real endpoint credentials and network access.

## Validation

The repository adds deep regression coverage for the governance kernel and an AST guard against silent `except Exception: pass` handlers. CI remains the final gate before merging.
