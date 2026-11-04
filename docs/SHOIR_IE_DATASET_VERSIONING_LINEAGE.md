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
