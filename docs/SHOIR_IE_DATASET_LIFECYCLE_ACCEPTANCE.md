# Shoir-IE Dataset Lifecycle Acceptance

Assessment date: 2026-11-06. Status: **partially implemented in staging; full lifecycle not accepted**.

Staging has migrations `20261104192112_shoir_atomic_dataset_version_registry` and `20261104192857_shoir_private_dataset_file_storage_and_linkage`; Edge Function is v13. The design/source notes describe workspace-scoped immutable version records, current pointer, content/schema/transformation fingerprints, signed private object handling, server-side validation, historical selection and quality charts. The current candidate additionally forwards organization-workspace scope through dataset upload/list/download, returns current-head/version-fingerprint metadata, and links registered dataset versions to Industrial Intelligence evidence nodes with `INPUT_TO` edges. A version transition persists a lineage event and current Dataset node even when no older analysis depends on the dataset; older dependent records are marked stale without rewriting historical payloads. These candidate changes still require exact-head CI and hosted staging acceptance.

Documented gaps:
- registry path stores normalized CSV; raw original XLSX remains separate Excel Intelligence responsibility;
- resumable/TUS uploads not implemented (single-request 50 MiB limit);
- reference-aware orphan cleanup absent;
- downstream invalidation now has candidate source code for Industrial Intelligence records and canonical Digital Thread dataset-version nodes; exact-head CI and hosted acceptance are pending. Legacy module outputs outside that record contract, hosted identity continuity and full managed lineage are not yet proven;
- clean migration replay and authenticated hosted E2E not accepted;
- organisation ownership is unavailable because the organisation migration is not deployed.

Complete by testing two-version register/retrieve after fresh login, real object SHA-256, signed-link permissions, schema fingerprint and row/column checks, workbook round-trip separately, retention/deletion, safe orphan cleanup and stale dependent outputs. Use authenticated disposable accounts and record exact deployed commit/function version. Do not claim the full Import→Decide→Export chain until downstream lineage and exports pass.
