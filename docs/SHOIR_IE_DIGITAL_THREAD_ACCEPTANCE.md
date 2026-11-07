# Shoir-IE Digital Thread Acceptance

Assessment date: 2026-11-06. Status: **canonical identity foundation present; managed lineage acceptance pending**.

The repository includes `shoir_digital_thread.py`, canonical identity/relationship tests and draft changes in PR #229/#232. Managed platform persistence supports workspace-scoped record types. This is not proof of hosted save/reload/re-login or organisation-scoped Digital Thread.

Outstanding:
- PR #229 review/integration and overlap review with #231/#232;
- managed persistence across a fresh session;
- entity rename, stable identity, legacy aliases, duplicate/ambiguous rejection and edge history on hosted storage;
- dataset→model→run→scenario→decision→outcome lineage with exact version references;
- stale-output marking/invalidation when dataset versions change;
- tenant/org scope (not yet deployed);
- privacy-conscious aggregate workforce data;
- clear separation between editable event history and immutable audit evidence.

Complete by integrating canonical IDs with managed storage, running create/rename/reload/re-login, relationship-preservation and ambiguity tests, then change dataset version and prove dependents become stale while historical evidence remains intact. Test cross-workspace/org denial with multiple disposable users. Attach exact SHA and artifacts.
