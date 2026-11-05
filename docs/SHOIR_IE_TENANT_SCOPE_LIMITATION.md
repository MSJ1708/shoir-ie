# Shoir-IE tenant and organisation-scope limitation

**Environment reviewed:** authorised staging project `hfhrosthswcybccepmak`  
**Review date:** 2026-11-05  
**Status:** `IN_PROGRESS` — account/workspace isolation exists for the managed platform API; verified organisation-level tenancy and team sharing are not implemented.

## 1. Evidence checked

Read-only staging schema queries found:

- `public.shoir_workspace_states` is keyed by `username_lc` and stores one `state_json` document per account.
- `public.shoir_platform_records` and `public.shoir_platform_events` are keyed by `workspace_key`.
- The current Edge helper derives `workspace_key` from the authenticated lowercase username plus the supplied workspace label. The caller's username is first checked against the opaque session.
- The application schema search across `public` and `shoir_internal` returned no authoritative organisation, tenant, organisation-membership, workspace-membership or invitation tables.
- `public.shoir_accounts` contains username, role, tier, email and account state fields, but no organisation ID or email-verification field.
- The managed platform tables have RLS enabled. Staging checks report no direct SELECT grants for `anon` or `authenticated`; the Edge service role has the required server-side access.

## 2. What the current scope does and does not provide

**Provided:** an authenticated account can read and write records in its own derived workspace scope. A second account using the same visible workspace label receives a different workspace key because the username participates in the key. This prevents accidental cross-account sharing through this API.

**Not provided:** two employees in the same company cannot yet be shown to share one authoritative organisation workspace through a server-verified membership relationship. The collaboration record type currently persists inside the account-derived workspace and therefore must not be described as an organisation-wide collaboration service.

This is not a verified enterprise tenant model. Do not mark customer administration, team workspaces, shared collaboration, organisation-level audit, or cross-user project permissions as `STAGING_VERIFIED` on this evidence.

## 3. Required implementation before enterprise team sharing

1. Add organisation identity records with immutable organisation IDs, status, owner and creation metadata.
2. Add organisation memberships with an explicit role, status, inviter, accepted timestamp, suspension/removal history and unique membership constraints.
3. Add invitation records using high-entropy single-use tokens stored only as hashes, expiry, target identity, inviter and revocation state. Invitation acceptance must require a live account session and exact target identity.
4. Make the server resolve the active organisation and workspace from the authenticated session plus verified membership. Never trust an arbitrary client-supplied organisation ID or role.
5. Derive shared workspace keys from the verified organisation ID and workspace ID, not from a display name or the current username.
6. Preserve the existing personal-workspace path. Use additive migrations and a reviewed backfill that creates personal-organisation ownership for existing accounts without exposing their existing records to other users.
7. Enforce the membership role on every read, write, list, export, file, job, notification, report and Copilot/tool path. UI hiding is not authorization.
8. Provide server-verified organisation audit events for membership changes, access reviews, invitations, role changes and consequential engineering approvals.
9. Add end-to-end disposable-account tests for owner/admin/engineer/approver/viewer roles, invitation acceptance/expiry/revocation, cross-organisation record/file denial, role escalation, membership removal and personal-workspace preservation.
10. Add hosted acceptance using at least two separate disposable accounts in one test organisation and a third account in another organisation. Prove the first two can see only records permitted by membership/role and the third cannot enumerate, download, export or infer the other's data.

## 4. External and operational requirements

- Decide the supported invitation delivery route. Email delivery requires a configured provider and sender-domain verification; until then, an invitation link may be manually transferred to the exact invited account, but must remain single-use, short-lived and target-bound.
- Agree role names and permission policy with the product owner before granting write/approval powers.
- Organisation-level identity and membership require a controlled migration, backup and rollback plan, tested only in staging.
- Any legal/customer-specific access model must be reviewed against the relevant contracts and privacy obligations.

## 5. Release impact

This is a mandatory blocker for claims of enterprise-wide tenant sharing, team collaboration, organisation-level customer administration and company-wide Digital Thread. It does not invalidate the narrower account-scoped dataset and record API, provided those capabilities remain described accurately.

**Current release decision for enterprise organisation sharing: NO-GO.** The account-scoped record service must not be relabelled as an organisation tenant service until the membership model and cross-account acceptance suite pass.
