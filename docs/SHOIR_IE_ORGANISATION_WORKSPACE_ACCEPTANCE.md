# Shoir-IE Organisation and Workspace Acceptance

Assessment date: 2026-11-07. Status: **PARTIALLY IMPLEMENTED; hosted acceptance and release remain blocked**.

## Verified staging baseline

The authorized staging Supabase project is `hfhrosthswcybccepmak`. The first organization/workspace migration is recorded as applied in staging at version `20261107120637`. The five organization tables exist with RLS enabled. The last read-only count query returned:

| Table | Rows at last inspection |
|---|---:|
| `shoir_organizations` | 9 |
| `shoir_organization_memberships` | 9 |
| `shoir_organization_invitations` | 0 |
| `shoir_organization_workspaces` | 0 |
| `shoir_organization_audit_events` | 0 |

Those nine organizations/memberships are the personal-organization backfill; they are not evidence of team collaboration acceptance.

The deployed staging `shoir-persistence` function was version 14 at the last inspection. Its `index.ts` and `security.ts` matched the then-current branch sources, and the implementation validates opaque session tokens, expiry, account state, username binding, scope and subscription state before organization actions. The Edge Function has `verify_jwt=false`; the application-level session authentication is therefore a critical security boundary and must continue to be verified end-to-end. The repository now contains a further owner-only organization-close action, but that change has **not** yet been deployed to staging.

Production has not been changed. The production persistence function was version 9 at read-only inspection and retains the older wildcard CORS implementation; this remains a production release blocker and is intentionally outside this task's deployment scope.

## Repository implementation now present

The release-hardening branch adds or updates:

1. `20261107120637_shoir_organization_workspaces.sql` — organization, membership, invitation, workspace and append-only audit tables, RLS, server-only grants, and scoped RPCs. The filename matches the version already recorded in staging; its SQL was preserved.
2. `shoir_team_workspaces.py` — an existing-module renderer for organization selection, create/join, workspace create/archive, membership list/role change/removal/suspend/restore, invitation create/accept/revoke, owner transfer, audit read and owner-confirmed organization closure.
3. `app.py` and `industrial_platform.py` — preserve the established Team Workspaces membership editor/export surface and add the organization-backed UI as a separate staging-only tab. The legacy `shoir_workspace_rbac.py` editor stores compatibility membership metadata in the application-local SQLite database; a visible notice now states that these rows do not grant or revoke access to organization workspaces, shared workbook data, files or APIs.
4. `durable_account_store.py` — allowlists organization actions through the session-authenticated Edge client and requires explicit staging environment configuration.
5. `20261107150000_shoir_organization_close.sql` — owner-only close operation. It revokes pending invitations, archives workspaces, removes active memberships, closes the team organization and appends an audit event. It does not delete audit history or account/personal-workspace data.
6. `20261107153000_shoir_organization_member_suspend_restore.sql` — owner/admin-scoped member suspension and restoration. Admins cannot suspend, restore or change other Admin accounts; restoring an inactive account is denied; both operations append immutable audit events.
7. `supabase/functions/shoir-persistence/index.ts` — session-authenticated organization management and workspace data actions. Shared persistence is used only when both organization and organization-workspace IDs are explicitly supplied; personal workspace behavior remains unchanged.
8. `20261107160000_shoir_organization_workspace_state.sql` — shared workspace state keyed by workspace key, an 8 MiB JSON-object limit matching the Edge request contract, RLS, no direct table grants (including `service_role`), and only two narrowly scoped service-role RPC grants. Read/write RPCs validate role and active workspace in the transaction, require optimistic revision tokens, append revision metadata audit events (not workbook contents), and block stale writes. The migration also revokes `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES` and `TRIGGER` on organization audit history from `service_role` while preserving its `SELECT`/`INSERT` use. It adds covering indexes for the six organization foreign keys reported by the staging performance advisor plus the new state updater FK.
9. `workspace_persistence.py` and `durable_account_store.py` — the existing workbook state saver/loader now uses the shared organization state only for an explicitly active team workspace. Scope changes clear the prior loaded values; access is revalidated each app rerun; stale revision conflicts pause autosave until an explicit confirmed reload; personal SQLite fallback is forbidden for team scope. Team management widget values are excluded from durable state.
10. Regression tests cover migration source/grants/indexes, Edge routing, client allowlisting, production fail-closed behavior, state scope switching, personal/shared separation, unsaved-key cleanup, stale revision handling, authentication gating, UI management actions and the authenticated organization lifecycle contract. The isolated clean-PostgreSQL migration replay also exercises Owner/Viewer/Engineer shared-state reads/writes, revision conflicts, append-only audit metadata, no direct service-role shared-state table privileges, no audit-table truncation/control privileges and the two RPC grants.

The per-user Digital Thread/domain manifest is deliberately not written for shared workspace saves until that artifact manifest itself is organization-aware. Dataset/file/job/export sharing is therefore not claimed complete.

The Team Workspaces renderer is deliberately staging-only until hosted acceptance passes. Backend RPC authorization remains authoritative; hiding a control in Streamlit is not treated as security enforcement.

## Authenticated acceptance prepared but not yet executed

`scripts/authenticated_release_gate.py` now contains a two-organization acceptance sequence using only the existing disposable `shoir-e2e-*` active Enterprise, second-user and Starter test identities. It is designed to test:

- Owner creates two team organizations and a workspace.
- Owner invites the second disposable account as Viewer.
- Invitee accepts; replay is denied.
- Viewer can read but cannot create a workspace.
- The invitee is denied access to the second organization.
- Owner promotes the invitee to Admin; Admin can create a workspace and invite a third disposable user, but cannot self-promote.
- Owner changes the member to Engineer and Approver; those roles cannot create workspaces.
- Owner suspends the member; the member's still-valid session is denied organization access. Owner restores the active account; organization access works again.
- Owner removes the member; subsequent organization access is denied.
- Owner creates and revokes a second-organization invitation; the revoked token cannot be accepted.
- A `finally` cleanup closes only the two organizations created by that run, preserving audit history, before test sessions are revoked.

The authenticated workflow currently requires an explicit manual `workflow_dispatch` or its existing one-shot push opt-in on `staging-e2e-20261019`. The GitHub Actions connection available to this task does not expose a workflow-dispatch operation. Therefore the real hosted gate has **not** been run. No credentials are printed or requested in this document.

## Remaining acceptance blockers

1. Complete all eight required CI workflows on the exact final candidate SHA and inspect JUnit, migration replay, Edge, security, Excel and browser/export artifacts.
2. Obtain one independent review of the latest PR push and resolve every review thread before a staging merge is considered.
3. Reconcile the actual staging migration ledger with an authorized database operator; the repository connection's database-history authentication failure is not evidence that migrations are absent.
4. Document and verify a recoverable staging backup/rollback point for both PostgreSQL data and Storage object bytes before any deployment.
5. Apply only reviewed, actually missing staging migrations in timestamp order. Do not replay a migration already recorded as applied.
6. Deploy the exact matching candidate persistence Edge Function source to staging, then record function version/hash and recheck RLS, direct grants, RPC grants, bucket policies and Supabase advisors.
7. Verify the staging banner/build marker and configure the seven dedicated disposable E2E identities and required GitHub Actions secrets/variables.
8. Run the authenticated release gate against the exact staging app and Edge endpoint. Verify Owner/second-user/Starter/Expired/Module/Research/Inactive login, tier and session expectations.
9. Complete organization lifecycle tests: Owner/Viewer/Engineer/Approver/Admin boundaries, Admin cannot promote or alter Owner, invitation expiry/revocation, suspend/restore, removal, archive/close and cross-organization denial. Confirm test cleanup leaves no active test session or open disposable organization while retaining immutable audit records.
10. Run a two-member shared-workspace round trip: Owner creates shared state, Viewer read succeeds/write fails, Engineer updates a new revision, stale revision conflicts, and suspension/removal denies further access.
11. Verify artifact ownership separately for datasets, Storage files, jobs, exports, reports and Digital Thread links. The shared workspace state table does not make every artifact organization-owned.
12. Verify Digital Thread identity/rename/alias/edge continuity, dataset-version invalidation and cross-workspace denial across a fresh logout/re-login.
13. Capture authenticated screenshots/traces at 1440px, 768px and 390px including Arabic/RTL where supported; inspect navigation, workbench, charts, drawers, forms, errors and downloads.
14. Attach the exact-SHA migration ledger, Edge version/hash, authenticated gate result, redacted test reports, screenshots and reviewer sign-offs. Keep PR #232 draft until the owner and independent reviewers explicitly accept the staging evidence.

Until every item is complete, Team Workspaces & RBAC remains **implemented in the release branch but not verified for hosted commercial use**. Do not advertise it as production-ready enterprise collaboration.
