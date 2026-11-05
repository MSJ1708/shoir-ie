# Staging migration reconciliation — 2026-11-05

**Environment:** staging Supabase project `hfhrosthswcybccepmak` only  
**Production:** not modified by these staging migrations  
**Applied migrations reviewed:** `20261105101231` and `20261105111832`

## Referral migration preflight and change

Read-only checks immediately before the `20261105101231_safe_beta_legal_referrals_20261105` migration showed:

- 9 account rows in staging.
- 1 blank affiliate code, excluded by the partial unique index.
- 0 duplicate nonblank codes after `LOWER(BTRIM(affiliate_code))` normalization.
- `public.shoir_referrals` already existed with the expected columns, constraints and sequence.
- The existing normalized index was `LOWER(affiliate_code)`; the stricter trimmed-normalized index was absent.
- The referral table had RLS enabled and no public/authenticated access; service-role access was present.

The staging migration replayed reviewed additive SQL from `20261026110000_safe_beta_legal_referrals.sql`. It uses `IF NOT EXISTS`, reasserts server-only permissions, and creates the partial unique index on `LOWER(BTRIM(affiliate_code))`. It contains no `UPDATE` of `shoir_accounts`, no account-code rewrite, and no timestamp rewrite. The historical data-rewriting migration `20261021130000` was not replayed.

## Explicit browser-role deny policies

The staging migration ledger records the explicit deny-policy migration as version `20261105111832`. Read-only inspection of `pg_policies` confirmed all 13 expected policies exist: one on `public.shoir_referrals` and 12 on the private `shoir_internal` tables. Each policy is scoped to `anon` and `authenticated`, applies to `ALL`, and has both `USING (false)` and `WITH CHECK (false)`. No broad browser-role access is granted.

The repository migration filename and clean-replay inventory are aligned to the applied staging version `20261105111832`; the policy SQL is unchanged.

## Postflight

Read-only verification confirmed:

- `idx_shoir_accounts_affiliate_code_trimmed_unique` exists.
- Referral row count remains 0.
- Blank affiliate code count remains 1.
- Staging migration ledger records `20261105101231` and `20261105111832`.
- Supabase Security Advisor currently returns no linter findings for staging.
- Supabase Performance Advisor reports 18 informational unused-index findings. These have not been dropped: absence of observed use is not enough evidence to safely remove an index.

## Release limits

This reconciles the reviewed referral and browser-role deny-policy migrations in staging only. It does not resolve the production migration gap. Production still requires a separately reviewed migration plan, backup/restore evidence and production-compatible acceptance before any schema or Edge Function deployment. In particular, production is missing the six current legal-acceptance columns and its `shoir-persistence` Edge Function is version 9 while staging is version 13.

No production schema, function, secrets, billing, account or customer data were changed.
