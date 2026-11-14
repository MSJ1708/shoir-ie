# Shoir-IE SQLite Lifecycle Acceptance

Assessment date: 2026-11-06. Evidence baseline: `bd76f8450c20e18aa74d9b70d0945e735aa2b804`. Status: **implemented wrapper; full acceptance pending**.

`shoir_sqlite.py` defines `ClosingSQLiteConnection`: context-manager exit delegates to sqlite3 commit/rollback behavior and closes the underlying connection in `finally`; a defensive finalizer closes abandoned handles. `sqlite_connect` uses this subclass as its factory. The enterprise integration module uses the shared closing connection.

Current tests cover commit/close, exception rollback/close, repeatable explicit close and abandoned-connection ResourceWarning. The previous rollback test was invalid because it used DDL without explicit BEGIN. It now explicitly begins the transaction. The correction must pass the current full CI before F-002 is closed.

Still needed:
- nested/savepoint behavior;
- concurrent writes, busy timeout and locking;
- WAL checkpoint/file lifecycle;
- fresh schema and upgrade compatibility for each local DB;
- repeated Streamlit reruns/restarts;
- direct `sqlite3.connect` repository-wide inventory with caller lifecycle classified;
- complete warning-free application run.

Complete by running the lifecycle test file, all persistence/enterprise callers, adding missing concurrency/nested/WAL cases, auditing direct sqlite connections and then running the full suite with ResourceWarning as error. Attach exact SHA and artifacts before marking accepted.
