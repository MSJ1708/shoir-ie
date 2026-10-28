# Production change authorization request — Shoir-IE

**State: PREPARATION ONLY — NOT APPROVED. Do not execute production changes from this document.**

> **Candidate snapshot note — 2026-10-28 20:16 UTC:** PR #220 advanced after this packet was first drafted. Its current candidate head is `7b852037ac4d28f43365da81443463d8a287ded7` (draft, exact-head checks queued/not verified); current helper blob SHA-1 is `40b1d1de3e87b4ed3e3e86062824ae84cae825e6`. The original `79feaae...` source/head and `c079ce...` helper blob values below are historical preparation-time identifiers, not current release identifiers. This packet is **not approval-ready** until all relevant checks and independent review pass, then the deterministic deployment artifact is built from the exact approved SHA and its actual SHA-256 is recorded.

Prepared on 2026-10-28. This packet separates the production persistence-function security hotfix from the legal/referral schema migration. They are two distinct changes and require independent scope, preconditions and explicit release-owner approval.

## A. Production persistence-function security hotfix

### Exact target and candidate

- Repository: `MSJ1708/shoir-ie`
- Production Supabase project: `gcsamrdaeraxieaagsta`
- Function: `shoir-persistence`
- Currently observed production version: **v9**
- Currently observed production source SHA-256: `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740`
- Candidate PR: [#220](https://github.com/MSJ1708/shoir-ie/pull/220)
- Candidate source commit recorded at preparation time: `79feaae04bbb05e104c4b399840668788ebfaf18`
- Candidate source path: `supabase/production-hotfix-v8/index.ts`
- GitHub file-blob SHA (not a SHA-256 artifact digest): `b194c5d695bb6776d5f2688e288ae17da85bf68c`
- Security helper path: `supabase/production-hotfix-v8/security.ts`
- Security helper GitHub file-blob SHA (not a SHA-256 artifact digest): `c079ce704b9ba2f2ff28f0899184d78624d20cd9`
- **Deterministic deployment-bundle SHA-256: NOT GENERATED.** A deployment artifact must be built from the reviewed exact commit, hashed, and pinned before release approval.
- PR #220 is a **draft**. Exact-head CI was queued or not yet observed as complete at the time of preparation. No independent approval is recorded.

### Proposed change scope

The proposed function-only hotfix is based on the currently deployed production-v9 source, not staging v11. It changes browser CORS to use only the approved origin `https://shoir-ie-app.streamlit.app`; returns approved-origin OPTIONS preflight with exact method/header policy and `Vary: Origin`; rejects unapproved origins; restricts API actions to POST; handles unsupported methods with 405; applies a 12 MiB streamed UTF-8 JSON-object bound; maps internal errors to safe public responses; rechecks the protected-administrator invariant for privileged sessions; and prevents subscription approvals from modifying the reserved administrator or any Enterprise Admin.

This function candidate does **not** include the legal/referral migration and is designed not to depend on the six currently missing legal-acceptance columns or `public.shoir_referrals`.

### Preconditions that must all pass before approval

1. Independent security review of the complete PR diff against production v9.
2. Fresh exact-head Deno formatting, type-checking and tests, Python contract tests, security/quality tests and relevant regression suites all pass. No skipped mandatory test counts as pass.
3. A fresh read-only check records the active production version/hash immediately before the approved change window.
4. An approved rollback/recovery point and a documented function rollback procedure are verified. If the database plan does not supply an adequate restore point, the owner must approve a suitable recovery alternative before approving the function release.
5. Build the deterministic deployment bundle from the exact reviewed source commit; record both source and bundle SHA-256 hashes in the release record. No artifact hash may be inferred from a GitHub blob SHA.
6. Release owner signs and authorizes this *function-only* change explicitly, naming the target project and change window.

### Ordered execution if subsequently authorized

1. Verify that the actual active production function version and source hash still match the pre-change record. Abort on drift.
2. Verify the approval record names this exact function candidate, build hash, target and recovery plan.
3. Deploy only the pinned production-v9-compatible function bundle. Do not deploy staging v11 and do not run a database migration as part of this function-only action.
4. Read back the deployed version and source/bundle digest. Abort if the observed version or source does not match.
5. Run non-mutating browser-preflight HTTP probes for: approved origin, unapproved origin, origin omitted, required methods, required headers, error response headers and `Vary: Origin`. Approved origin must receive exact ACAO; unapproved origin must receive 403 and no ACAO; origin-free preflight must not receive ACAO. Do not send an arbitrary state-changing POST.
6. Run safe authenticated smoke tests using disposable/approved test accounts only. Verify login/logout, persistence and RBAC. Never sign in as `sho` or mutate that account.
7. Review function/application logs for unexpected errors or data exposure; verify the single active canonical admin remains unchanged through read-only aggregate inspection.
8. Stop and begin the approved rollback/recovery procedure if the function source, CORS behavior, session handling, persistence, RBAC or invariant checks fail.

### Impact, downtime and rollback notes

- Expected change: edge-function code only; no database DDL or intended customer-row mutation in this action.
- Downtime: **not measured; do not promise zero downtime**. Record the actual deployment duration and any observed disruption.
- Rollback: restore the immediately preceding, recorded production-v9 function artifact through the supported Supabase deployment control after the stop criteria are met. The prior source must be retrievable and its hash verified before approval.
- Responsible approvers: independent security reviewer and the authorized production release owner. Names are not filled in because no independent approval/authorization is recorded.
- Current observed blocker: the pre-change live CORS probe returned HTTP 200 with `Access-Control-Allow-Origin: *` for approved, unapproved and origin-free OPTIONS requests. This is a real failure, not proof that the candidate is ready to deploy.

## B. Separate legal/referral database migration

**This migration is not included in the function-only action above and is not approved by this document.**

### Candidate source

- Candidate PR: [#218](https://github.com/MSJ1708/shoir-ie/pull/218)
- Candidate commit at preparation time: `89b760611ba67028b5d9d2bc4286642fd641c6f9`
- Migration: `supabase/migrations/20261026110000_safe_beta_legal_referrals.sql`
- GitHub file-blob SHA (not a SHA-256 artifact digest): `5c3f489698d610878c61ca9626f72f4d3d8702e0`
- PR #218 is a **draft**. The most recent migration rehearsal for this narrowed privilege revision is pending; earlier success on an older revision is not evidence for this exact head.
- Expected changes: add the six missing legal-acceptance fields to `public.shoir_subscription_requests`; create/refine `public.shoir_referrals`, its constraints and indexes; enforce the reviewed legal-consent trigger/policy version; preserve existing account identifiers, `affiliate_code` and `updated_at`; and grant only the approved table CRUD plus sequence USAGE/SELECT to `service_role`, with no browser-role permissions.
- Current production migration ledger ends at `20261019140600`. Historical files `20261021130000_shoir_beta_legal_referrals.sql`, `20261022110000_enforce_beta_legal_acceptance.sql`, and `20261023130000_refresh_refund_policy_acceptance_version.sql` must not be blindly replayed; earlier migration code can rewrite `affiliate_code` and `updated_at`.

### Preconditions

1. Fresh exact-head CI plus PostgreSQL migration replay on the exact candidate.
2. Reviewed, production-shaped isolated migration rehearsal using synthetic data and an exact, approved schema/migration history; before/after identifiers, codes and timestamps must be compared.
3. Reconciliation procedure must explain each production-ledger difference and prevent unreviewed historical files from running. Do not mark any migration applied merely to unblock `db push`.
4. Actual backup/PITR availability, retention/checkpoint and successful isolated restore evidence are mandatory. No qualifying production restore rehearsal has been performed.
5. Independent database/security review signs the migration source, resulting schema/grants/RLS, preservation comparison, transaction/abort behavior and recovery plan.
6. Release owner explicitly approves the exact migration file/hash, ledger reconciliation, target project and execution window in a separate approval.

### Proposed order if subsequently authorized

1. Confirm the source backup/checkpoint and successfully restore it into isolated infrastructure; validate login, account boundaries, subscription/legal persistence and function compatibility with synthetic accounts.
2. Reconcile the exact production ledger using the independently reviewed procedure; abort if any legacy migration would run unexpectedly.
3. Execute only the approved forward migration sequence and verify schema, RLS/grants, constraints, trigger policy version and protected-row digests. Do not use `supabase db push` as a substitute for reviewed reconciliation.
4. Verify no unintended rows changed and all legal-consent tests pass. Stop on any unexplained difference.
5. Use the exact post-migration schema manifest to approve the compatible function build; staging v11 must not be deployed simply because it is newer.
6. Record final ledger/schema diffs, hashes, logs and recovery decision.

### Current recovery blocker

The available project/plan/tool evidence does not establish an adequate production backup/PITR restore point or an actual isolated restore rehearsal. Do not perform the migration until a qualifying recovery capability is made available and independently verified. Do not upgrade the plan or incur a paid service cost without separate owner authorization.

## C. Required release-owner decision record

This is a **request for a future explicit decision**, not authorization to execute.

The release owner must record for each action separately:

- [ ] Approve function-only hotfix `shoir-persistence` for production project `gcsamrdaeraxieaagsta`.
- [ ] Approve database migration/reconciliation as a separate action after restore and independent review.
- [ ] Exact reviewed source commit(s), migration file hash(es) and deterministic artifact SHA-256 hash(es).
- [ ] Independent review identity and approval reference.
- [ ] Backup/restore evidence, checkpoint ID, observed RPO/RTO and named recovery operator.
- [ ] All passing/failing/pending gates and the exact-head CI/artifact links.
- [ ] Approved change window, impact statement, stop criteria and rollback/forward-recovery decision-maker.
- [ ] Explicit written authorization timestamp and owner identity/role.

**Current decision: NO-GO / HOLD.** Missing exact-candidate test results, artifact SHA-256, independent security/database approvals and actual restore evidence prevent this request from being approval-ready. Production deployment, production DDL, production row changes, production paid-launch enablement and BETA removal remain unauthorized.
