# Shoir-IE production cutover readiness — 2026-11-05

**Decision: NO-GO for production schema/function/application rollout.**  
**Production Supabase control-plane status: ACTIVE_HEALTHY.** This does not mean the current application stack is release-ready.

## 1. Verified production snapshot (read-only)

Project: `gcsamrdaeraxieaagsta` (`shoir-ie-production`), region `eu-central-1`, PostgreSQL `17.6.1.166`.

Aggregate database checks:
- 5 account rows, 41 session rows, 4 subscription-request rows and 3 workspace-state rows.
- The protected Enterprise Admin aggregate invariant matches exactly one account. No admin row was read or changed.
- `shoir_subscription_requests` is missing all six required current legal-acceptance columns: `terms_accepted`, `terms_version`, `privacy_policy_version`, `refund_policy_version`, `cookie_policy_version`, `accepted_at`.
- `public.shoir_referrals` does not exist.
- The 12 tables in `shoir_internal` exist, but 0/12 currently have row-level security enabled. Read-only privilege checks found no schema USAGE or table DML grants for `anon`, `authenticated` or `service_role`; do not assume the production Edge Function can access this schema.
- Production has a private `subscription-payment-proofs` Storage bucket (512 KiB limit; PNG/JPEG/PDF MIME allow-list). The existing `storage.objects` policy denies browser roles access to that bucket. No `shoir-industrial-datasets` bucket currently exists.
- The candidate dataset-storage migration drops and recreates the existing payment-proof policy with an additional dataset-bucket exclusion. Verify the exact resulting policy expression and prove payment-proof upload/download behavior remains unchanged before rollout.
- Production migration history ends at `20261019140600` (`atomic_subscription_request_decisions`).
- Production `shoir-persistence` is active at version 9 (source hash recorded in the release evidence); staging currently runs version 13.
- Supabase production Security Advisor returned no lints. Performance Advisor reports 18 informational unused-index notices. These indexes are not to be dropped based only on an unused-index observation.

Production already contains accounts, sessions, subscription requests and workspace state. Any migration must be additive, preserve existing account codes/timestamps and workspace/session data, and avoid broad rewrites or resets.

## 2. Explicit historical migration hazard

Do **not** replay `20261021130000_shoir_beta_legal_referrals.sql` on production. It rewrites affiliate codes and `updated_at` values for blank or legacy-looking codes and rewrites case-insensitive duplicates. That historical behavior is not accepted for this production cutover.

The safer candidate is `20261105101231_safe_beta_legal_referrals_20261105.sql`. It adds the six legal-acceptance columns, creates the referral table and a trimmed/case-normalized partial unique index without updating existing account codes, timestamps or referral rows. This candidate still requires a production backup, schema/constraint/duplicate preflight, reviewed migration manifest and rollback plan before execution.

## 3. Candidate migration order — not yet approved or executed

1. **Backup and preflight:** verify a recoverable backup/PITR point and complete a restore rehearsal; capture migration history, schema, object owners, grants, RLS/policies, storage buckets/policies, exact row counts of the 12 internal tables, normalized affiliate-code duplicate/blank counts and all function dependencies. Confirm the protected-admin aggregate remains exactly one.
2. **Legal/referral structure:** apply the reviewed safe additive referral/legal migration only after the above preflight. Never replay the historical data-rewriting migration.
3. **Legal approval guard:** install the latest Refund Policy v2 trigger/function definition from `20261025164602_refresh_refund_policy_acceptance_version.sql` after the six columns exist. Existing requests with no recorded acknowledgement must not be silently treated as accepted; the current approval path should require a fresh acknowledgement.
4. **Private internal schema:** review each of the 12 production internal tables, their row contents, owners, grants, direct server callers and role bypass posture. Only then consider `20261104183132_enable_shoir_internal_rls_20261104.sql` and explicit deny policies from `20261105111832_explicit_deny_policies_for_private_rls_advisories.sql`. Do not apply a blanket allow policy. Do not assume staging's empty-table preflight is evidence about production.
5. **Managed record/dataset RPCs:** verify production table definitions, unique constraints, grants and function ownership before applying `20261104184453` and `20261104192112`. Run the atomicity, idempotency, concurrency and cross-account denial suite against a clean production-like clone first.
6. **Private dataset storage:** review existing `storage.objects` policies and current payment-proof restrictions before considering `20261104192857`. Verify bucket privacy, MIME/size constraints, object ownership, signed URL expiry, rollback and orphan behavior. Do not replace or broaden storage policies without an explicit compatibility review.
7. **Edge Function:** deploy the exact reviewed Edge Function revision to production only after all database prerequisites pass. Verify its deployed source hash/version, secret presence (never reveal secret values), JWT/session validation, restrictive CORS preflight, RPC grants and storage integration.
8. **Streamlit app:** deploy the reviewed application commit only after the production database/function compatibility gate passes. Verify the actual hosted host is serving that commit; an active database or successful local smoke test is not proof of application deployment.

This is a cutover sequence for review. It is not an instruction to run any migration immediately.

## 4. Mandatory gates before any production GO

- Exact-head CI green: Python regression suite with strict deprecation/future/resource warnings, Deno formatting/type/security tests, transaction integration, Excel Intelligence, PDF/PPTX generation and rendering, and desktop/mobile browser smoke evidence.
- Clean-database migration replay plus production-like clone validation; no unexplained migration ledger drift.
- Production backup and point-in-time restore rehearsal, verified recovery point and tested rollback plan.
- Authenticated hosted acceptance using disposable staging identities only: registration/legal acknowledgement, login/session/logout/revocation, entitlement/tier access, account/workspace restore, cross-account denial, dataset upload/catalogue/version/history/download/integrity and real graph rendering.
- Production-compatible API/schema/Edge Function exact-source verification and restrictive CORS probe from allowed and disallowed origins.
- Protected-admin invariant preserved; never use the protected administrator as a test account.
- Saudi legal/commercial/privacy/refund readiness reviewed by the responsible owner before paid-customer activation.

## 5. Known product limitations that block claims of full Enterprise integration

- The managed record API currently proves account + workspace isolation, not organisation-membership tenancy or cross-user corporate sharing.
- Organisation IDs, membership roles, invitations, role enforcement on every route/export/file/job/Copilot path and the two-user/third-user hosted acceptance are not complete.
- Dataset lifecycle still lacks resumable upload/recovery, reference-aware orphan cleanup, automatic downstream model/run invalidation, full dataset-to-calculation lineage and hosted authenticated acceptance.
- Original workbook preservation remains in the separate Excel Intelligence path.
- T096 ERP/Integration and T098 external identity/MFA are configuration-dependent; they must not be represented as connected until an authorised external endpoint/provider is configured and tested.

## 6. Evidence and safety boundary

The production project was found active and healthy at the Supabase control plane. The SQL queries in this review were read-only aggregates/schema checks. No production migration, account/session mutation, Edge Function deployment, secret change, storage policy change, billing operation or Streamlit production deployment was performed.

The staging branch and its draft PR remain separate from production. Keep the global BETA status until the mandatory gates above have passed with retained evidence.
