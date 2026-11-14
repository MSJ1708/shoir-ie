# Staging migration reconciliation — 2026-11-05

**Environment:** staging Supabase project `hfhrosthswcybccepmak` only  
**Production:** not modified by this migration  
**Applied migration:** `20261105101231_safe_beta_legal_referrals_20261105`

## Preflight

Read-only checks immediately before applying the migration showed:

- 9 account rows in staging.
- 1 blank affiliate code, which is excluded by the partial unique index.
- 0 duplicate nonblank codes after `LOWER(BTRIM(affiliate_code))` normalization.
- `public.shoir_referrals` already existed with the expected columns, constraints and sequence.
- The existing normalized index was `LOWER(affiliate_code)`; the stricter trimmed-normalized index was absent.
- The referral table had RLS enabled and no public/authenticated access; service-role access was present.

## Change

The staging migration replayed the reviewed additive SQL from `20261026110000_safe_beta_legal_referrals.sql`. It uses `IF NOT EXISTS`, reasserts server-only permissions, and creates the partial unique index on `LOWER(BTRIM(affiliate_code))`.

It contains no `UPDATE` of `shoir_accounts`, no account-code rewrite, and no timestamp rewrite. The historical data-rewriting migration `20261021130000` was not replayed.

## Postflight

Read-only verification confirmed:

- `idx_shoir_accounts_affiliate_code_trimmed_unique` exists.
- Referral row count remains 0.
- Blank affiliate code count remains 1.
- Staging migration ledger records version `20261105101231`.
- Supabase advisor findings remain at the same 13 informational deny-by-default RLS notices and 18 informational unused-index notices; no new advisor finding was introduced by this migration.

## Release limits

This reconciles the safe referral migration in staging only. It does not resolve the remaining production migration gap. Production still requires a separately reviewed migration plan, backup/restore evidence and authenticated production-compatible acceptance before any schema or function deployment.

## Repository-to-ledger timestamp reconciliation — 2026-11-07

A fresh comparison of the staging migration ledger with the candidate's tracked SQL found a timestamp mismatch for the revised Refund Policy v2 guard:

- Staging records version `20261025164602`, name `20261023130000_refresh_refund_policy_acceptance_version`.
- The recorded SQL statement was fetched read-only from the staging migration ledger and compared with the repository file. The executable SQL matched exactly.
- The candidate migration source has therefore been renamed to `20261025164602_20261023130000_refresh_refund_policy_acceptance_version.sql`, and the local migration inventory, clean-replay version list and policy-version test now use the recorded version.
- The safe referral replacement SQL in `20261026110000_safe_beta_legal_referrals.sql` is equivalent to the idempotent safe SQL already recorded on staging under `20261105101231`. The earlier version remains tracked for clean-history replay; it is not an unreviewed data rewrite.
- After the timestamp alignment, the remaining local-only migration versions against the current staging ledger are `20261026110000` and the three organization migrations `20261107150000`, `20261107153000` and `20261107160000`. The latter three remain blocked on exact-head CI and backup/rollback readiness.

This is source/ledger alignment, not a migration repair or live schema change. No migration ledger rows were manually inserted, deleted or rewritten. Before any staging deployment, rerun the complete clean PostgreSQL replay, compare the local/remote migration list again, verify the idempotent replacement behavior, and use the authorized migration runner. Do not use `migration repair` merely to hide a mismatch.
