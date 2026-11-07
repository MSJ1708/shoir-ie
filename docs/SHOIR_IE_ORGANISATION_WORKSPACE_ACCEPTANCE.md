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

1. `20261107120637_shoir_organization_workspaces.sql` — organization, membership, invitation, workspace and append-only audit tables, RLS, server-only grants, and scoped RPCs. The filename now matches the migration version already recorded in staging; its SQL was preserved.
2. `shoir_team_workspaces.py` — an existing-module renderer for organization selection, create/join, workspace create/archive, membership list/role change/removal, invitation create/accept/revoke, owner transfer, audit read and explicit owner-confirmed organization closure.
3. `app.py` — routes the existing Team Workspaces & RBAC module into that renderer without adding duplicate navigation.
4. `durable_account_store.py` — allowlists organization actions through the session-authenticated Edge client and requires explicit staging environment configuration.
5. `20261107150000_shoir_organization_close.sql` — owner-only close operation. It revokes pending invitations, archives workspaces, removes active memberships, closes the team organization and appends an audit event. It does not delete audit history or account/personal-workspace data.
6. `20261107153000_shoir_organization_member_suspend_restore.sql` — owner/admin-scoped member suspension and restoration. Admins cannot suspend, restore or change other Admin accounts; restoring an inactive account is denied; both operations append immutable audit events.
6. `supabase/functions/shoir-persistence/index.ts` — adds the session-authenticated `org_close_session` action.
7. Regression tests cover migration source/grants, client allowlisting, production fail-closed behavior, authentication gating, owner/viewer UI surfaces, confirmed close, member suspend/restore UI and client actions, and the authenticated organization lifecycle contract.

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

1. Complete all current branch CI runs, including clean PostgreSQL replay, migration inventory, Edge type/security verification, Python regression and UI tests.
2. Apply `20261107150000_shoir_organization_close.sql` to staging only after the clean replay and security review pass.
3. Deploy the repository's exact persistence Edge Function source to staging as a new version, retaining the existing custom session-authentication design. Record the deployed source hash and version.
4. Run the authenticated release gate manually against the verified staging app and staging Edge endpoint with the dedicated disposable credentials already configured in GitHub Actions. Do not use `sho`, production identities or customer data.
5. Verify that cleanup closes both disposable organizations and that no invitation, active workspace, membership or open test session is left behind. Retain immutable audit records as designed.
6. Run hosted suspend/restore acceptance, add expired-invitation acceptance, and verify role-specific access to platform records, datasets, files, jobs, exports, Copilot and Digital Thread.
7. Capture the actual staging app URL, Edge Function version and SHA, migration ledger, authenticated run URL, test report and screenshots.
8. Have the authorized owner review the evidence. Keep PR #232 open and draft until approval; do not merge, deploy production, remove BETA or change the protected administrator.

Until these steps are complete, Team Workspaces & RBAC is **implemented in the release branch but not verified for hosted commercial use**. Do not advertise it as production-ready enterprise collaboration.
