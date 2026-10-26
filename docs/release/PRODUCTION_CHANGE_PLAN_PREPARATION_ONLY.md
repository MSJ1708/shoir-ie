# Shoir-IE Production Change Plan — Preparation Only

**State: PREPARATION ONLY — NOT APPROVED FOR EXECUTION.** Production must remain unchanged until the release owner, database owner and security reviewer have approved an exact, reviewed plan. This document is not an instruction to run a migration or deploy an Edge Function now.

## 1. Verified starting facts

- Production project reference reported and confirmed through the connected Supabase project listing: `gcsamrdaeraxieaagsta`.
- Production `shoir-persistence`: deployed version 8; source SHA-256 metadata `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`.
- Staging `shoir-persistence`: deployed version 9; source SHA-256 metadata `0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e`.
- Production has no `shoir_referrals` table, zero of the six expected legal acceptance columns on `shoir_subscription_requests`, and no matching legal acceptance approval trigger. Staging has all three.
- Aggregate-only query: production 5 accounts, one exact master-admin invariant match, all five accounts match the current referral migration rewrite predicate; staging 8 accounts, one invariant match, zero rewrite-predicate matches. No identifiers were selected and no rows were changed.
- Current source contains `20261021130000_shoir_beta_legal_referrals.sql`, which updates `affiliate_code` and `updated_at` for missing/blank/legacy values before creating referral objects. Running it verbatim would update all five currently existing production account rows.
- Staging migration history includes legal/referral migrations; production migration history currently ends at `20261019140600_atomic_subscription_request_decisions`. The staging refund-policy acceptance migration is recorded under ledger version `20261025164602` while the checked-in filename is prefixed `20261023130000`.
- Current main/staging source trees diverge substantially, and the authoritative Streamlit deployment branch/entry point/runtime SHA is not independently established in this audit.

## 2. Mandatory preconditions — stop if any item is missing

1. Release owner records the exact approved application SHA, migration files/versions, Edge Function source hashes and planned production window.
2. DBA independently confirms the target project identity in Supabase Dashboard. Stop if the project ref or environment does not match the approved change record.
3. Backup/PITR settings, backup age/retention and point-in-time recovery window are verified. Complete a restore rehearsal in an isolated environment and save redacted evidence plus integrity-query results.
4. A second database reviewer inspects the final SQL, execution order, grants, RLS, triggers, data-impact predicates and migration history.
5. The original referral rewrite is not scheduled to run against production. The responsible DBA must select and document a controlled migration-history strategy that avoids silently applying its row-rewriting behavior. Do not blindly mark a migration applied, edit applied history, rename a migration or rerun SQL merely to make versions agree.
6. A safe forward migration plan is tested against a staging clone representing production's five-account schema/state, not only against the already-upgraded staging database. It must leave existing account values and timestamps unchanged unless a separately approved backfill is expressly authorized.
7. The exact runtime application/entry point and compatibility requirements are verified. Do not assume the production app tracks `main`, staging, or a particular Streamlit app without checking the platform settings and observed runtime.
8. Dedicated disposable smoke-test accounts and a monitoring owner are ready. Do not use or mutate the master administrator.
9. All mandatory staging gate checks pass, including the login throttle and inactive-account denial probes. Skips are not passes.
10. Written production approval identifies the change owner, operator, recovery owner, start/end window and abort authority.

## 3. Migration design and review sequence

### A. Resolve migration history before execution

- Reconcile every migration version/name against actual applied migration history and the current DDL. Record the precise reason for the refund-policy version/name discrepancy.
- Resolve how the pending `20261021130000_shoir_beta_legal_referrals.sql` will be prevented from rewriting existing rows while preserving the already-applied staging schema and history. The production execution plan must not simply run the current file unchanged.
- The preferred functional outcome is additive schema creation and safe referral behavior for new accounts. Any backfill for existing accounts is a distinct business/data decision and must have a written predicate, a before/after aggregate, an idempotence strategy and explicit approval.
- Keep legal version strings exactly synchronized across published notices, application payload validation, Edge Function validation and the database approval guard. The current versions in source are terms `2026-10-21-beta-v1`, privacy `2026-10-21-v1`, refund `2026-10-23-v2` and cookie `2026-10-21-v1`; counsel must first approve the actual text/version.

### B. Provisional dependency order for rehearsal only

The order below is a planning hypothesis. The DBA and reviewer must confirm it against final migration/Edge Function/app source before it becomes executable.

1. **Preflight snapshot:** confirm project reference; capture migration ledger, schema, grants, RLS, triggers and safe aggregate baselines; verify backup/restore readiness.
2. **Data-preserving schema expansion:** apply only the independently reviewed schema change that does not rewrite existing account records and that creates the required legal acceptance/referral objects in a transaction where supported.
3. **Schema postchecks:** verify exact columns, constraints, trigger, RLS, indexes and grants; verify account counts, codes and timestamps are unchanged except for any separately approved and documented change.
4. **Compatible Edge Function:** deploy the reviewed function source only after its schema preconditions pass. Confirm actual deployed version/source SHA, request/response contracts and JWT/custom-session boundary. Do not infer success from a deployment CLI result alone.
5. **Reviewed application revision:** deploy only the approved app revision after confirming it matches the active function contract. The order must be changed if final compatibility testing reveals the app and function require a backward-compatible expand/contract transition.
6. **Post-deployment acceptance:** use approved synthetic account(s), not the master administrator, to test login/logout/session rejection, legal acceptance recording, inactive-account denial, throttling, subscription request flow, referral handling, role/entitlement denial, workspace isolation, persistence and report exports.
7. **Operational observation:** inspect redacted logs/alerts and health/error metrics for an owner-approved observation window; re-run all required invariant and aggregate checks.

## 4. Preconditions, postconditions and abort criteria

**Preconditions:** approved exact SHAs and files; independent SQL/security review; verified backup and successful restore rehearsal; verified runtime target; approved change window; current authenticated staging gate all required checks pass; no unresolved production migration-history ambiguity.

**Postconditions:** the runtime app SHA and app URL/entry point match approval; deployed Edge Function source/version matches the plan; actual schema and migration ledger match the approved result; legal consent is persisted and the database approval guard rejects missing/stale consent; referral configuration is secure; exact master-admin invariant remains one; authentication/entitlement/isolation/persistence/export tests pass; monitoring/alerts are normal.

**Abort before writes:** any target identity mismatch, unknown migration/checksum, failed backup/restore proof, source/runtime SHA mismatch, missing reviewer/approval, unapproved row-changing predicate, unexpected row count, failing mandatory staging check or untested rollback/recovery assumption.

**Abort during change:** any unexpected affected-row count, schema/constraint/grant/RLS difference, failed function contract, authentication or consent regression, admin invariant deviation, cross-workspace access, sensitive log output, or sustained service/error alert outside the approved threshold. Stop subsequent steps and invoke the named recovery owner; do not improvise additional SQL.

## 5. Recovery limits

- Additive schema changes and legal-acceptance triggers should not be rolled back by dropping columns/tables or bypassing mandatory consent. Prefer a reviewed forward fix unless the approved recovery plan proves rollback safe.
- Do not automatically revert to the currently observed production Edge Function version 8: it lacks the legal acceptance and referral-summary handlers present in the version-9 source. A rollback candidate must be demonstrated compatible with the post-change schema and the app, and must not silently disable a mandatory legal guard.
- Any account-level changes require an approved before-image/restore plan. The current referral migration's effect on existing codes/timestamps has not been approved.
- If restoring a database is required, use the documented backup/PITR procedure in the approved change window and validate integrity before reopening service.

## 6. Current authorization status

**Not authorized. No production writes performed by this review.** Backup/PITR availability, restoration rehearsal, independent migration review, final ordered deployment, production smoke tests and production release approval remain BLOCKED / NOT RUN until the named owners supply evidence. BETA stays visible.
