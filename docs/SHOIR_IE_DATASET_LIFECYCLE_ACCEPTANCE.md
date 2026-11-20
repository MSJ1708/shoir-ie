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


## Candidate update — 2026-11-20: resumable upload and registration cleanup

The release-hardening candidate now includes `shoir_supabase_tus.py` and routes managed normalized-CSV uploads through Supabase Storage's TUS endpoint on the direct project storage hostname. It uses the required 6 MiB chunk size, a signed upload token, bounded retries, HEAD-based offset reconciliation after uncertain PATCH responses, strict upload-location host validation, and disabled redirects. The existing 50 MiB cap remains.

The resumable upload URL is retained only in the active server-side Streamlit session, bound to the user/workspace/dataset/content hash/organization scope, with a 23-hour local expiry. The server can resume the same upload on a rerun or transient connection loss while that session remains available. This is **not** cross-device or guaranteed process-restart persistence; an expired or unavailable upload capability starts a fresh upload.

Dataset finalization now keeps the temporary upload until the atomic metadata RPC succeeds. If that RPC reports failure after a new content-addressed object was created, deletion is attempted only after both the managed-record and event ledgers are successfully queried and confirm no reference exists. An error in either reference query fails closed and retains the object. A pre-existing or concurrent object is never removed by this failure path. After a successful registration, temporary-object removal is best-effort and returned as `temporary_cleanup_pending` rather than falsely reporting the registration as failed.

Regression coverage is added in `tests/test_shoir_supabase_tus.py` and `tests/test_shoir_dataset_storage_cleanup_contract.py`. These are candidate source/test additions until the exact final SHA completes all required CI.

**Still not implemented:** a scheduled, reference-aware sweep for pre-existing/aged orphan objects and abandoned temporary uploads. This must enumerate candidate objects, check all metadata references and tenant/workspace boundaries, retain objects whenever the metadata check fails, and produce a deletion audit. Do not delete objects based on age alone. Hosted staging upload/resume/download, fresh-login, cross-workspace, object-retention and original-workbook round-trip acceptance remain open.


## Candidate update — 2026-11-20: bounded operator sweep for abandoned temporary uploads

The current candidate adds a session-authenticated T020 storage-maintenance action and a separate operator control in the existing Industrial Engineering Workbench:

- The action resolves the current personal workspace from the authenticated actor or resolves a shared organization workspace with database-enforced `manage` permission (Owner/Admin only).
- Preview is the default. Deletion requires a separate explicit `confirm_delete=true` request and a Workbench confirmation checkbox.
- Only exact T020 temporary-upload paths under the selected workspace can be deleted. Other workspaces, buckets, traversal paths, original XLSX files and immutable content-addressed dataset files are excluded.
- A temporary object must have valid Storage timestamps and remain untouched for at least 48 hours. The newest of created, updated and last-accessed timestamps controls eligibility; missing, malformed or future timestamps are retained.
- Both the managed-record and event ledgers must successfully confirm no reference to the exact temporary storage key. Any reference-query error retains the object.
- A deletion-intent event is written before Storage removal; a separate deletion-confirmed event follows successful removal.
- The scan is bounded to 500 objects/200 directories, 100 reference checks and 50 deletions per invocation. Operators can repeat preview/deletion to process remaining entries.
- No automatic schedule is created. Scheduling this authenticated operation remains an external operational configuration.

**Immutable content-addressed orphan objects are intentionally retained by this sweep.** Deleting one can race a concurrent dataset version-finalize request between its object read and metadata transaction. A safe immutable-object sweep needs an atomic lease/coordination protocol shared with dataset registration; age plus two reference reads alone is insufficient. This remains repository engineering work, not an external provider credential task.

These source changes require exact-head Deno, Python, full regression and authenticated owner/member staging acceptance before an Edge deployment. Keep BETA / production NO-GO.
