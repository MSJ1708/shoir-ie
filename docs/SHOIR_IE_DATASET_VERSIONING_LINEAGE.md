# Shoir-IE Dataset Versioning and Lineage — staging implementation notes

## Status

`IMPLEMENTED_NEEDS_VALIDATION` on branch `feat/managed-platform-record-api-20261104`. This is not a claim of hosted staging acceptance.

## Implemented in this branch

- Stable logical dataset ID based on dataset name and source identity, not file byte length.
- Deterministic CSV content hash.
- Schema metadata with column dtype and nullable signal.
- Version fingerprint covering dataset ID, content hash, schema and transformation log.
- Authenticated Edge action `dataset_version_register`.
- Session validation before registration.
- Atomic PostgreSQL function `shoir_platform_register_dataset_version`.
- Immutable version records in `shoir_platform_records` with record type `dataset_version`.
- Current dataset pointer in `shoir_platform_records` with record type `dataset`.
- Dataset version registration event in `shoir_platform_events`.
- Idempotent return for the same current fingerprint.
- New version number when content, schema or transformation fingerprint changes.
- Bounded metadata validation, server-side fingerprint recomputation from dataset ID/content hash/schema/transformations, and server-side advisory transaction lock for concurrent writes.
- The Workbench Data Platform route shows a persistent dataset catalogue, historical version selector, and integrity-checked shared-workspace loading.
- Dataset quality profiles render a missingness chart and up to three numeric distributions with explicit axis labels and descriptive-only interpretation notes.
- The route is guarded by the stable T020 entitlement at render time; the Edge API independently enforces Enterprise access on dataset upload, registration, listing and download actions.
- The current record key is account/workspace scoped, not organisation-membership scoped; see `SHOIR_IE_TENANT_SCOPE_LIMITATION.md`.
- The route caches the last processed upload fingerprint to prevent repeating a same-file upload on Streamlit reruns.
- Staging UI path uses the authenticated session and does not query local SQLite for the dataset catalogue.
- Authenticated signed download URLs are issued only after checking the workspace-scoped dataset head record.
- Downloads are SHA-256-verified client-side before CSV parsing; the server also parses the normalized CSV structure and rejects mismatched row counts, column counts, duplicate/blank headers or schema keys before version metadata is committed.
- The original platform catalog requires Enterprise for this workspace; the T020 registry, Streamlit route and Edge API now enforce that same Enterprise package.

## Staging migration

The migration `20261104192112_shoir_atomic_dataset_version_registry.sql` was applied to staging project `hfhrosthswcybccepmak` through the authorised staging database tool. The source migration is tracked in this branch.

## Important limits

- The staging upload path now stores the normalized CSV artifact in the private `shoir-industrial-datasets` bucket, using a signed upload URL, a temporary object path, server-side SHA-256 verification, and a content-addressed final object key.
- The raw original XLSX workbook is not preserved by this particular dataset registry path; the normalized tabular CSV representation is stored. Excel Intelligence separately preserves source workbooks through its own workflow.
- Uploads currently use a bounded single-request signed upload (50 MiB maximum); resumable/TUS upload and progress recovery are not yet implemented.
- A verified content-addressed object can be left orphaned if the subsequent metadata transaction fails. A scheduled, reference-aware orphan cleanup process is not yet implemented; do not delete objects by age alone.
- Downstream model and run records are not yet automatically invalidated or linked to every dataset version.
- This migration has not yet passed the full clean-database replay workflow and hosted authenticated staging acceptance.
- No production schema, Edge Function, secrets, or customer data were changed.

## Required acceptance

1. Clean local migration replay includes the new migration.
2. Deno format, type and Edge security tests pass on the exact PR head.
3. Unit tests verify same fingerprint is idempotent and changed fingerprint increments version.
4. Concurrent requests do not create duplicate versions or skip version numbers.
5. Cross-workspace and cross-user access is denied.
6. A hosted disposable-account workflow registers two versions, loads a version after a fresh session, and verifies private object access.
7. Hosted disposable-account acceptance verifies signed upload, server-side byte hashing, private object retrieval after a fresh session, and no cross-workspace access.
8. Raw original-workbook retention, resumable uploads, reference-aware orphan cleanup, and model/run downstream invalidation/lineage are separately implemented and tested before claiming complete dataset lifecycle management.


---

## Candidate lineage hardening update — 2026-11-15

The candidate's Industrial Intelligence lineage path has since been extended:

- Dataset-version references propagate automatically from registered evidence into newly created Industrial Intelligence records.
- The Industrial Intelligence model registry and action ledger carry dataset-version dependency metadata from their model-test/action evidence.
- A new dataset version invalidates dependent Industrial Intelligence records, models and actions in the active workspace; preserves the historical payload/model definition/action; marks corresponding Digital Thread nodes stale; and records affected IDs in the lineage event.
- Managed workspace save is attempted once for the affected lists; in-memory state and graph state are restored if the save is not confirmed.
- Stale model validation, action approval, decision review, benefit verification, risk/barrier review, cause/effect review and shift-handover acknowledgement are blocked.
- T094 future-dated KPI readings are explicitly classified and excluded from alert generation.

Focused regression tests were added for dependency propagation, repeat invalidation idempotence, model/action/decision/benefit/risk/cause-effect/handover stale guards, save rollback and T094 future timestamps. The 74 Industrial Intelligence test functions and 130 Resource Intelligence test functions currently present are test-source counts only. Exact-head CI is still pending; no passing result is inferred from test source.

### Still outside this coverage

The managed invalidation routine currently covers the Industrial Intelligence `records`, `models` and `actions` workspace stores. Legacy local SQLite stores in `industrial_platform.py`—including `platform_models`, `platform_scenarios`, `platform_experiments` and `platform_decisions`—are not yet automatically invalidated or blocked by this routine. Full model/run/scenario/decision/outcome lineage across those legacy routes remains incomplete.

Hosted fresh-session/re-login, cross-organization isolation, signed-object access, original XLSX retention, resumable upload, reference-aware orphan cleanup, backup/recovery, browser/export acceptance and independent engineering review remain separate gates.


## Further stale-consumer update — 2026-11-15

The candidate now also invalidates the duplicate Industrial Intelligence `events` ledger in the same workspace save as `records`, `models` and `actions`. The rollback regression test checks the event mirror is restored when the managed save is rejected. Copilot evidence retrieval excludes stale dataset-derived records from citations and reports `excluded_stale_evidence_count`.

Two focused regression tests were added for event-mirror invalidation and stale-evidence exclusion in Copilot. The current Industrial Intelligence test-source count is 76 before the most recent test additions; test-source counts are not passing CI results. Exact-head validation remains pending.


## Legacy SQLite lineage integration update — 2026-11-15

The candidate now adds a separate additive dataset-version registry for the legacy local Industrial Platform path:

- `platform_dataset_versions` stores immutable local metadata versions by dataset ID, version number, SHA-256 content hash, version fingerprint, schema, transformations, row/column counts, actor and timestamp.
- `platform_datasets` tracks the current version and fingerprint. Re-registering identical content does not create another version; a changed content/schema/transformation fingerprint advances the version.
- Legacy model, experiment, scenario and platform-decision rows now have dependency, freshness and stale-marker columns. New saves resolve caller-declared dataset references against the registered immutable history; unresolved references are recorded as `UNVERIFIED_REFERENCE`, not `CURRENT`.
- A version advance invalidates dependent rows in `platform_models`, `platform_experiments`, `platform_scenarios`, `platform_decisions`, the mirrored `experience_decisions`, and existing `experience_decision_outcomes`. Historical model parameters, scenario inputs/KPIs, experiment payloads, decision metrics and outcome payloads are retained.
- New model/scenario/experiment/decision saves reject stale source references. Standalone Experience decision approval/implementation/verification transitions and outcome insertion reject both `STALE` and `UNVERIFIED_REFERENCE` lineage.
- The Experience decision/outcome tables receive additive schema migration columns; older rows default to `NOT_LINKED` unless actual dependency evidence is present.
- The local SQLite dataset path is explicitly disabled unless `APP_ENVIRONMENT` is `local`, `development` or `test`. A production deployment without managed dataset configuration fails closed and does not create a local SQLite substitute.
- Regression tests cover local immutable versioning, unchanged-content idempotence, invalidation of legacy artifact types, decision mirror/outcome invalidation, unverified-source approval denial, old-schema migration/backfill and production fallback denial.

### Limits that remain

This local registry stores dataset version metadata and hashes, not the original workbook or raw file bytes. It is not a substitute for the managed staging Storage implementation. Historical artifacts without verifiable dataset references remain `NOT_LINKED`; the system deliberately does not infer their dependencies after the fact. The new local registry does not establish managed hosted dataset upload/download, Storage object retention, resumable upload, orphan cleanup, fresh-session continuity or cross-organization acceptance. Exact-head CI and independent engineering review are still required before this code is accepted.


## Initial-import Digital Thread and unresolved-lineage fail-closed update — 2026-11-15

- The first verified dataset registration now creates a canonical Dataset-version node immediately, even when no analysis record depends on it yet. The node stores dataset ID, version, content hash, version fingerprint, source name, registration time and current-version verification state.
- The initial Dataset node is saved through the authenticated workspace persistence path. A failed save records `shoir_dataset_thread_sync_status=SAVE_FAILED`, sets the workspace lineage block and prevents new dataset-dependent record creation.
- If a dataset-version invalidation save fails, the active workspace remains lineage-blocked. Model validation, action approval/status transitions, decision review, benefit verification, risk/barrier review, cause/effect review and shift-handover acknowledgement now also refuse to proceed while that block is set.
- Copilot returns `DATASET_LINEAGE_UNRESOLVED` and no citations while the workspace lineage block is active. Stale or unresolved data cannot be silently presented as current evidence.
- The local immutable metadata registry now supports a content reversion lifecycle A → B → A as versions 1 → 2 → 3. The earlier content-hash uniqueness index is removed by an additive, history-preserving SQLite table rebuild when encountered.
- Regression tests cover first-import Dataset Thread persistence, failed initial graph save, unresolved-lineage approval/Copilot blocking, A → B → A versioning and old-table uniqueness migration.

CI for the latest candidate head remains pending. These are source changes and authored tests, not hosted acceptance evidence.


## Retry-safe activation and atomic current-head persistence — 2026-11-15

A final ordering review found that the newly active dataset dependency and Thread save status needed to be part of the same persisted snapshot as the Thread node/event. The candidate now:

- Sets the active dataset dependency and enables lineage tracking before calling the idempotent invalidation/persistence routine.
- Re-runs idempotent invalidation on every authenticated Enterprise activation, including when the same immutable dataset version is reopened after a fresh login. This retries a previously failed lineage save instead of trusting a session-local flag.
- Persisting the current Dataset node, active dataset dependency, workspace-wide lineage status and lineage event is one managed workspace save. A confirmed save clears the block; a failed save restores artifact/graph changes and sets `SAVE_FAILED` plus the workspace block.
- Reuses one lineage event for each dataset ID/version and unions the prior affected artifact IDs into the event payload on subsequent activation. This preserves the audit trail without creating duplicate events or erasing the original affected-ID list.
- The fresh-session retry regression test verifies that reopening the same version after a deliberately failed save clears the block only after a successful persistence call, and that the saved snapshot includes the active dependency, current node ID and unblocked state.

The latest candidate also includes a Workbench AppTest asserting that a future-dated T094 KPI observation is visible as `FUTURE_TIMESTAMP` but opens no alert. T094 unit and UI tests are both authored; exact-head CI remains pending.
