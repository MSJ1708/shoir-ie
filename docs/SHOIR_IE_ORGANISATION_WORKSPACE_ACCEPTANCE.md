# Shoir-IE Organisation and Workspace Acceptance

Assessment date: 2026-11-06. Status: **not end-to-end implemented; release blocker**.

The source migration `20261106120000_shoir_organization_workspaces.sql` defines five org tables, membership roles, hashed single-use invitations, org/workspace RPCs, owner transfer, audit events, RLS and service-role-only grants. However, live staging query found **zero** of these tables; the migration is not in the staging ledger. The deployed staging persistence Edge Function v13 contains no organisation, membership or invitation actions. The production v9 function also contains no such actions.

`shoir_workspace_rbac.py` remains a local SQLite workspace-membership flow and is not the organisation model in the SQL migration. Source-level migration tests do not prove multi-account acceptance.

Required work:
1. Review migration SQL, SECURITY DEFINER ownership/search_path, actor authority, grant boundaries, uniqueness/concurrency and rollback.
2. Replay all migrations on clean PostgreSQL 17.
3. Apply the organisation migration to staging only after review and backup.
4. Add Edge actions that derive actor from validated session and call narrowly scoped service-role RPCs.
5. Wire the existing Team Workspaces/RBAC UI; avoid duplicate navigation.
6. Support org creation, member roles, invite create/revoke/expire/accept, member removal, owner transfer, workspace create/archive and org audit.
7. Add three disposable users (two in one org, one in another); test all five roles, replay/expiry, escalation, removal, ownership transfer, cross-org denial and preserved personal workspaces.
8. Re-test record, dataset, file, job, export, Copilot and Digital Thread access after membership removal.
9. Record exact deployed SHA, migration and Edge Function version plus screenshots/logs.

Do not claim enterprise team collaboration until the hosted flow passes.
