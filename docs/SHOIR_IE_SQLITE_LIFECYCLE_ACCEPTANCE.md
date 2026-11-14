# Shoir-IE SQLite Lifecycle Acceptance

Assessment date: 2026-11-14. Candidate baseline: `d1a289106f7a4b29f9240156c9776d74a3bc88a3`. Status: **extended local regression coverage authored; full runtime acceptance still pending**.

## Implemented connection wrapper

`shoir_sqlite.py` defines `ClosingSQLiteConnection`. Its context manager delegates to sqlite3's standard commit/rollback behavior and closes the underlying connection at block exit. `sqlite_connect` selects this factory by default. The finalizer is defensive only; normal callers must use a context manager or explicit `close()`.

## Authored tests (not yet accepted as passing)

`tests/test_sqlite_connection_lifecycle.py` currently contains eight tests:

1. Context-manager commit and deterministic close.
2. Exception rollback and deterministic close, with explicit `BEGIN` so transactional DDL is actually tested.
3. Idempotent explicit close.
4. Abandoned connection finalizer and ResourceWarning check.
5. Nested savepoint rollback preserving the outer transaction.
6. Concurrent writer lock/busy-timeout failure followed by successful retry.
7. WAL checkpoint, reopen, persisted data and `PRAGMA quick_check`.
8. Repeatable fresh Industrial Platform schema initialization and expected lineage columns.

These tests were added to the candidate; they have not yet completed a passing exact-head CI run. Do not treat authored tests as a pass.

## Remaining acceptance

- Audit every direct `sqlite3.connect` call and classify it as scoped context-managed, long-lived returned handle, test-only, or external library. Replace scoped calls only after confirming imports and caller semantics; add explicit `try/finally` closure to long-lived handles where appropriate.
- Review `shoir_workspace_rbac.py`, `shoir_shadowshift.py`, `shoir_value_evidence.py`, `workspace_persistence.py`, `shoir_160.py`, `industrial_operating_system.py`, `shoir_commercial.py`, `industrial_platform.py`, `shoir_adoption_engine.py`, `durable_account_store.py`, `industrial_platform_excellence.py`, `shoir_enterprise_ops.py`, `shoir_industrial_workbook.py`, `shoir_enterprise_services.py`, `shoir_facility_layout.py`, `shoir_digital_thread.py`, `shoir_venture_studio.py`, `shoir_resilience_suite.py`, `shoir_unified_product.py`, and `industrial_experience.py`. This is an initial search-hit inventory, not a complete exhaustive count.
- Exercise each local database's create/upgrade path from a clean file and from the prior supported schema.
- Exercise Streamlit reruns, session changes, app shutdown/restart and file-handle reuse on the actual runtime.
- Run the full test suite with `ResourceWarning` treated as an error, and attach the exact SHA plus JUnit/test artifacts.
- Run an extended concurrent-write test on disposable copies of the relevant databases and inspect WAL/SHM files after close/reopen.

## Acceptance rule

Close this gate only after the full exact-head CI is green with no unapproved skips, the caller inventory is complete, and the application lifecycle test proves repeated use/restart without leaked handles, database-lock failures or schema regression. Do not label the SQLite layer production-ready on the basis of the wrapper tests alone.
