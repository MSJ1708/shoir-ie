# Referral migration reconciliation plan

**Status: HOLD — review and isolated rehearsal required. This is not production authorization.**

## Problem

The staging-applied migration `20261021130000_shoir_beta_legal_referrals.sql` changes existing `shoir_accounts.affiliate_code` and `updated_at` values for blank/legacy/duplicate codes. It has already been applied in staging. Do not rerun it there, attempt an unplanned rollback, or assume its original values can be reconstructed.

## Safe replacement

`supabase/migrations/20261026110000_safe_beta_legal_referrals.sql` is an additive replacement candidate. It adds legal-acceptance columns, the server-only referral table and lookup indexes without rewriting existing account identifiers or timestamps. It intentionally does not enforce global affiliate-code uniqueness until duplicate inventory and remediation are separately approved.

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
