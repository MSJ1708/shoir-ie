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
- Bounded metadata validation and server-side advisory transaction lock for concurrent writes.
- Staging UI path uses the authenticated session and does not query local SQLite for the dataset catalogue.

## Staging migration

The migration `20261104191500_shoir_atomic_dataset_version_registry.sql` was applied to staging project `hfhrosthswcybccepmak` through the authorised staging database tool. The source migration is tracked in this branch.

## Important limits

- The registry stores dataset metadata, hashes, schema and transformation descriptions; it does **not** archive the raw uploaded file bytes.
- A dataset remains in the current Streamlit session unless an approved durable file-storage path is separately configured and implemented.
- Downstream model and run records are not yet automatically invalidated or linked to every dataset version.
- This migration has not yet passed the full clean-database replay workflow and hosted authenticated staging acceptance.
- No production schema, Edge Function, secrets, or customer data were changed.

## Required acceptance

1. Clean local migration replay includes the new migration.
2. Deno format, type and Edge security tests pass on the exact PR head.
3. Unit tests verify same fingerprint is idempotent and changed fingerprint increments version.
4. Concurrent requests do not create duplicate versions or skip version numbers.
5. Cross-workspace and cross-user access is denied.
6. A hosted disposable-account workflow registers two versions and reads both back after a fresh session.
7. Raw file storage and model/run lineage are separately implemented and tested before claiming complete dataset lifecycle management.
