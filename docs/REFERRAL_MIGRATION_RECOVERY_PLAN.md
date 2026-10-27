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
