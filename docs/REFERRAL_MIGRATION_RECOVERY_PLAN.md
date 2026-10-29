# Referral migration reconciliation plan

**Status: HOLD — review and isolated rehearsal required. This is not production authorization.**

## Problem

The staging-applied migration `20261021130000_shoir_beta_legal_referrals.sql` changes existing `shoir_accounts.affiliate_code` and `updated_at` values for blank/legacy/duplicate codes. It has already been applied in staging. Do not rerun it there, attempt an unplanned rollback, or assume its original values can be reconstructed.

## Read-only preflight — October 27, 2026

Aggregate-only queries found no duplicate **nonblank** referral-code groups in either live project at the time checked. Staging reported 9 accounts, 1 blank code, and 0 duplicate nonblank groups. Production reported 5 accounts, 5 blank codes, and 0 duplicate nonblank groups. No individual referral codes, account identifiers, password hashes, or other account-row contents were selected for this check.

This is a time-bounded preflight, not a permanent guarantee. Repeat the same duplicate check against an isolated production-shaped copy immediately before any approved migration. If any duplicate exists, abort rather than rewriting account data to force uniqueness.

## Safe replacement

`supabase/migrations/20261026110000_safe_beta_legal_referrals.sql` is an additive replacement candidate. It adds legal-acceptance columns, the server-only referral table, and a case-insensitive **partial unique index for populated referral codes**. It excludes null/blank legacy rows and does not rewrite any existing account identifier or timestamp. Index creation must fail transactionally if duplicate populated codes have appeared; it must not attempt to repair them.

## Required reconciliation before production

1. Freeze and export the production migration ledger and staging migration ledger; record exact schema/function hashes and a secure backup/PITR point.
2. On a restored, isolated production-shaped copy, run read-only preflight queries for existing columns, referral table/sequence, null/blank/duplicate affiliate codes, legal-acceptance rows, triggers, grants and RLS.
3. Compare the replacement DDL with the exact live schema and repository baseline. Do not infer migration history from filenames alone.
4. Create a reviewed migration manifest. It must explicitly prevent the legacy data-rewriting migration from executing against production. If the migration runner requires the old version to be marked as applied, only use a separately reviewed, documented ledger-reconciliation procedure after verifying the existing schema; never blindly insert/update migration history.
5. Apply the replacement to the isolated copy and verify before/after row counts, every existing `affiliate_code` and `updated_at` value, constraints, grants, RLS, triggers and application compatibility.
6. Test failure/abort behavior, forward recovery and restore the isolated copy from backup. Record expected row counts, hashes, operator, approvals and timings.
7. Staging already has the earlier migration applied. Do not apply this replacement as a substitute for it on staging without a separate compatibility migration plan. First reconcile the staging ledger and verify schema parity; do not rewrite account identifiers to make environments look identical.
8. Production changes require a separate explicit release authorization and maintenance window. No production DDL is authorized by this document.

## Abort criteria

Abort if any existing account identifier/timestamp changes unexpectedly, schema/ledger state differs from the manifest, an unknown duplicate/constraint issue appears, backup/restore cannot be verified, application/function versions are incompatible, or required reviewer/owner approval is missing.

## Post-deployment checks if later authorized

- Verify columns/table/indexes, grants, RLS, trigger/function definitions and migration ledger.
- Verify referral codes are attribution only; no rewards/discounts are activated by schema existence.
- Verify legal acceptance version checks and approval guard behavior using synthetic accounts.
- Verify account and timestamp preservation against the pre-migration snapshot.
- Attach sanitized evidence and hashes to the release record.


## Fresh read-only compatibility recheck — October 28, 2026

Aggregate-only queries were rerun against the live production and staging databases. No usernames, account identifiers, referral-code values, password hashes, or row-level account data were selected.

| Check | Production | Staging |
|---|---:|---:|
| Account rows | 5 | 9 |
| Populated referral codes | 0 | 8 |
| Blank/null referral codes | 5 | 1 |
| Duplicate populated-code excess | 0 | 0 |
| `public.shoir_referrals` exists | No | Yes |
| Current legal-acceptance columns present (6 expected) | 0 | 6 |
| Referral-table RLS enabled | Not applicable (table absent) | Yes |
| Referral-table RLS policies | Not applicable | 0 |
| Browser role grants on referral table (`anon` / `authenticated`) | Not applicable | 0 |

Function inventory after staging-only deployment:

- Production `shoir-persistence`: version **9**, deployed source hash `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740`. Current source includes `Access-Control-Allow-Methods: POST, OPTIONS` but still emits wildcard `Access-Control-Allow-Origin: *`; the CORS release blocker remains open.
- Staging `shoir-persistence`: version **11**, deployed source hash `a0252769822fd7834c6af67fcf69259ec9bbefce7041ac3a5a36d8d6a9a90397`; source was deployed from security candidate commit `21a8d786485c11a415df1158d851bc43f9705c24`.

The staging function was verified to no longer emit wildcard CORS and no longer auto-repair the reserved administrator during login. Production remains unchanged and still has the older handler. The live staging HTTP CORS/preflight probe now passes via GitHub Actions; hosted public-shell and authenticated tests are recorded separately and must complete successfully before they can count as release evidence.

### Compatibility decision

The present mismatch is real: deploying the staging v11 handler to production before schema rollout is not approved. Production has neither the legal-acceptance columns nor the referral table used by this handler. Normal migration execution is also unsafe until the unrecorded legacy migration path is reconciled because the historical `20261021130000_shoir_beta_legal_referrals.sql` includes data-rewriting updates.

Do not execute production DDL on the basis of this recheck alone. Required next steps remain: exact migration manifest and schema diff; isolated production-shaped rehearsal; account-identifier/code/timestamp preservation proof; backup/PITR and restore/forward-recovery verification; independent database/security review; and explicit release-owner approval. The query results are time-bound and must be repeated immediately before any approved production migration.


## Explicit migration-ledger reconciliation runbook (prepared only; NOT executed)

**This runbook is for an approved change window only. It does not authorize production use.** The current production catalog has none of the six legal fields and no referrals table, while production's migration ledger ends at `20261019140600`. The safe replacement migrations are later in order than the three unsafe historical files. The exact sequence below must first pass on an isolated restore of a production-shaped copy.

### Required isolated rehearsal sequence

1. Restore a fresh isolated copy from an approved pre-change recovery point. Record project/database identity and ensure the runner cannot target either hosted project.
2. Capture aggregate counts and a protected digest of the existing `username_lc`, `affiliate_code` and `updated_at` set. Never export row content into public artifacts.
3. Compare the isolated target's migration list with the tracked repository migrations and the expected production ledger. Stop if any difference is unexplained.
4. Confirm that the historical SQL files would rewrite blank referral codes and timestamps if executed. Treat these timestamps as superseded for this rollout and **do not execute their historical SQL**:
   - `20261021130000_shoir_beta_legal_referrals.sql`
   - `20261022110000_enforce_beta_legal_acceptance.sql`
   - `20261023130000_refresh_refund_policy_acceptance_version.sql`
5. In the isolated copy only, use the supported Supabase migration-history repair operation to record these three reviewed historical timestamps as reconciled, without executing their old SQL. This changes migration metadata only; it neither creates the missing columns/table nor validates the schema. Do this only after the compatibility manifest explicitly maps the three skipped historical timestamps to the safe replacement migrations below. If the mapping is not independently approved, stop.
6. Recheck the migration list and run a migration dry-run. The output must show **only** `20261026110000_safe_beta_legal_referrals.sql` and `20261027120000_enforce_current_beta_legal_acceptance.sql` as pending. If any historical file is scheduled, a safe file is absent, or any extra migration is listed, abort before applying SQL.
7. Only in the isolated copy, apply the rehearsed migration set and verify schema, triggers, grants/RLS, current policy versions, transaction behavior, and exact preservation of every synthetic `affiliate_code` and `updated_at` value. Test abort/forward-recovery and restore again from the original checkpoint.
8. Record actual CLI output, schema hashes, row-preservation proof, restore identity/timing, and reviewer sign-off. Repeat read-only production preflight immediately before any separately authorized production change.

### Repair-operation recovery guard

The history repair is a separate metadata mutation and is not atomic with the subsequent schema push. If the repair succeeds but the dry-run fails before DDL executes, restore the original history entries in the isolated rehearsal using the reviewed reverse-repair operation, then investigate. If any DDL has executed or the post-repair schema is ambiguous, do not automatically reverse ledger rows; stop and use the rehearsed recovery procedure.

**Production remains HOLD.** The runbook has not been run against production or any hosted database. Production execution requires an exact function/schema candidate, a verified backup/PITR restore rehearsal, independent database/security review, and written release-owner authorization. The staging migration history and schema differ; do not run this production-specific repair procedure against staging.
