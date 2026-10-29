# Production Release Authorization Request — Draft for Owner Review

**State: NOT READY TO SUBMIT FOR APPROVAL. Production remains HOLD / NO-GO.**

This document identifies the production action that will eventually require written authorization. It does not request immediate execution, does not authorize any operation, and must not be interpreted as a GO decision.

## 1. Target and current deployed baseline

- Repository: `MSJ1708/shoir-ie`
- Production application: `https://shoir-ie-app.streamlit.app/`
- Production Supabase project: `gcsamrdaeraxieaagsta` (`shoir-ie-production`, eu-central-1, PG17)
- Function: `shoir-persistence`
- Verified deployed version: **v9**
- Verified deployed source SHA-256: `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740`
- Expected approved browser origin: `https://shoir-ie-app.streamlit.app`
- Current live CORS behavior: **FAIL** — non-mutating preflight diagnostics returned HTTP 200 and `Access-Control-Allow-Origin: *` for approved, unapproved, and origin-free requests.
- Current production schema: legal acceptance fields and `public.shoir_referrals` are absent.
- Current protected-admin invariant: exactly one active canonical administrator was verified with an aggregate-only read-only query. No admin login/test or account mutation occurred.

## 2. Candidate commits and artifact status

| Component | Candidate | What it covers | Current limitation |
|---|---|---|---|
| Production-v9 security hotfix | [PR #220](https://github.com/MSJ1708/shoir-ie/pull/220), head `2ab663663fe910f395b881869bc006183ed7bdfb` | Exact-origin CORS, 204 OPTIONS, POST-only action handling, bounded JSON, safe errors, protected-admin fail-closed checks. Main required source/security test checks passed on that head. | Hosted smoke is skipped; independent review is absent; no production deployment. This candidate preserves the v9 action/schema contract and **does not add the missing registration/legal/referral capabilities**. It is not by itself the complete production release bundle. |
| Safe legal/referral schema path | [PR #218](https://github.com/MSJ1708/shoir-ie/pull/218), recorded head `89b760611ba67028b5d9d2bc4286642fd641c6f9` | Additive legal-acceptance fields, server-only referral attribution, approval guard; old code/timestamps are not rewritten by the safe migration. Disposable PostgreSQL replay/transaction checks passed on the recorded candidate. | Production migration ledger reconciliation, production-shaped rehearsal, backup/PITR and restore evidence, coordinated function sequencing and review remain open. |
| Protected referral summary guard | [PR #226](https://github.com/MSJ1708/shoir-ie/pull/226), head `96aa69156d84043140f3c36a6c543e839a860934` | Prevents referral-code auto-assignment from modifying the reserved `sho` account or any Enterprise Admin. | Exact-head checks were in progress at last observation; no independent review. |

**No final deployable bundle hash exists yet. Do not approve or deploy the components independently as a full release.** The final request must name the exact reviewed bundle, exact migration files/order and hashes, exact CI head, and review approvals after they are available.

## 3. Production database changes proposed for later review

The current candidate plan is limited to the safe additive migrations in PR #218:

- `20261026110000_safe_beta_legal_referrals.sql`
- `20261027120000_enforce_current_beta_legal_acceptance.sql`

These filenames must not simply be handed to normal `supabase db push`. The history reconciliation and applied-version mapping must first be reviewed and rehearsed. The staging ledger contains an entry at version `20261025164602` named `20261023130000_refresh_refund_policy_acceptance_version`, while repository source naming uses the `20261023130000` timestamp. The old `20261021130000_shoir_beta_legal_referrals.sql` writes `affiliate_code` and `updated_at` on blank/legacy rows; all five current production account rows match its blank-code predicate. Do not replay it against production.

Current aggregate counts: 4 production subscription requests, 0 pending new-registration requests, and 5 blank/null affiliate codes; staging has 8 subscription requests, 0 pending new-registration requests, and 1 blank/null affiliate code. No request/account identifiers or referral codes were selected.

## 4. Required prerequisites before owner approval can be requested

- [ ] All exact-head CI and security checks pass for the final combined source.
- [ ] Independent security review explicitly covers CORS, request bounds, authentication/authorization, protected-admin behavior, registration/consent, referral handling, and the full migration diff.
- [ ] The main and staging rule sets are enforced as intended, all required contexts are unique and passing, and an independent review is approved.
- [ ] Disposable-account staging acceptance covers registration with current policy versions, missing/stale consent denial, login/logout, throttle behavior, inactive-account denial, tiers/RBAC, workspace persistence/isolation, referral behavior, exports and error responses.
- [ ] A production-shaped isolated rehearsal proves exact ledger reconciliation, schema compatibility, legal approval trigger behavior, preservation of every existing `affiliate_code` and `updated_at`, and forward/rollback recovery.
- [ ] An authoritative backup/PITR reference and an isolated successful restore result are recorded; owner, recovery operators, abort criteria and communication plan are named.
- [ ] Saudi legal/privacy/commercial approval is documented separately from technical test results.
- [ ] The final deployable function bundle and migration artifacts are versioned and SHA-256 checksummed; no live source hash drift exists.

## 5. Execution sequence if all prerequisites pass and written authorization is given

1. Re-read production function version/hash, migration ledger, schema fingerprint and protected-admin aggregate invariant immediately before the window.
2. Verify the named backup/PITR restore point and capture pre-change aggregate schema/account/referral-preservation checks.
3. Apply only the reviewed, reconciled schema migrations in the exact approved order using the approved migration procedure; do not replay the historical rewriting migration.
4. Verify migration-ledger versions and schema. Confirm every existing `affiliate_code` and `updated_at` remains unchanged, and the exact one-admin invariant still passes.
5. Deploy only the final reviewed Edge Function bundle that combines exact-origin CORS and protected-admin hardening with the legal-acceptance-aware registration/referral actions compatible with the new schema.
6. Re-read the deployed function version/source hash and run real non-mutating CORS/preflight checks for approved and unapproved origins, errors and unsupported methods.
7. Run staging-approved production smoke with disposable non-admin identities only, if authorized by policy: registration/legal acceptance, login/logout, inactive/expiry and throttling denials, workspace persistence, role enforcement, and safe non-mutating verification. Never use the protected administrator as a test account.
8. Verify export artifacts, schema and ledger, capture redacted evidence, and obtain a separate dated release-owner GO decision only if every mandatory gate passes.

## 6. Recovery and impact controls

**Recovery plan is not yet proven and is a blocker.** Before approval, the owner and operators must finalize and test a procedure that addresses both function rollback and additive schema forward-recovery. Blindly redeploying the current v9 bundle would restore the wildcard-CORS defect and missing registration action, so it must not be treated as an acceptable default rollback without explicit risk assessment. The plan must specify when to abort, whether to keep registration unavailable, how to roll forward safely, and who can make that decision.

Expected impact includes rejecting unapproved browser origins, bounded payload failures, and enforcing current legal-policy acceptance before new registrations can be approved. A mismatched code/schema sequence could break registration or approval; the approved sequence must keep them coordinated. No downtime claim is made.

## 7. Requested authorization fields (leave unsigned until complete)

- Release owner / approver: **Not yet recorded**
- Written approval timestamp / ticket: **Not yet recorded**
- Exact function bundle SHA-256: **Not yet available**
- Exact migration artifact hashes and reconciled versions: **Not yet final**
- Approved change window: **Not yet recorded**
- Backup/PITR and verified restore evidence: **Not yet available**
- Named recovery owner and tested procedure: **Not yet approved**
- Final CI / independent security review: **Pending**
- Decision: **HOLD — DO NOT DEPLOY**


## Recheck — shared-handler origin configuration (29 October 2026)

PR #226 now builds the shared current-main handler with a project-specific origin allowlist. With `SHOIR_ALLOWED_BROWSER_ORIGINS` unset, it defaults to the production origin only. A future authorized staging deployment of that shared source must set the variable to exactly `https://shoirieverified.streamlit.app` first. The currently deployed staging v11 function has not been changed. Production must not include the staging host in its allowlist.

This candidate is still source-only and its latest exact-head workflows are queued/in progress; its live smoke is skipped. The candidate is not the final bundle because the deployed production v9 function lacks the current registration action and legal/referral schema. **Authorization fields remain unsigned, and the release decision remains HOLD — DO NOT DEPLOY.**


## Exact-head status recheck — 29 October 2026

Latest inspected PR heads: #226 `dbc6cf8d7e2e1f632169e9c953416849b9e6f674` and #224 `a1a4cb25c2cd6936845689bca7af6b9096e5c470` still had CI queued at recheck. PR #218 `17ded0dff27fa26737d2f7820978809d017c7b2a` had its disposable PostgreSQL replay and transaction-contract tests passed, with security-quality in progress and additional jobs queued. These are source/rehearsal statuses, not production acceptance. PR #220 remains a partial v9 security candidate and does not contain the current registration action or schema. The authorization prerequisites remain incomplete; this request remains **unsigned / NOT READY / HOLD — DO NOT DEPLOY**.


## Latest ledger documentation status

The ledger PR advanced to commit `c0908c057506317251ccbe1b31b16ed783d4e337`; checks for that documentation-only head were queued at the latest recheck. The underlying authorization prerequisites have not changed. No approval signature or production change window is recorded. **HOLD — DO NOT DEPLOY.**


## Final code-head check — 29 October 2026

Latest CORS candidate #226 head: `9fd31cf87b7b1c7bc6c08c5ce95bd7abb7b6a1eb`; required test, Edge Function, security-quality and engine-regression checks were queued. Latest required-check/authenticated-gate candidate #224 head: `a1a4cb25c2cd6936845689bca7af6b9096e5c470`; its test and gate checks were queued. The full handler is now project-bound for CORS but remains undeployed. The current authorization request still lacks final artifact hashes, verified backup/restore evidence, independent review, and written owner approval. **HOLD — DO NOT DEPLOY.**
