# Production Compatibility Manifest — 2026-10-28

**Status: HOLD / NOT AUTHORIZED FOR PRODUCTION EXECUTION**

This manifest records the fresh read-only comparison used for release planning. It does not authorize production DDL, migration-ledger repair, function deployment, or customer-account mutation.

## Target identity

| Item | Production | Staging |
|---|---|---|
| Supabase project ref | `gcsamrdaeraxieaagsta` | `hfhrosthswcybccepmak` |
| Project status | ACTIVE_HEALTHY | ACTIVE_HEALTHY |
| Region | `eu-central-1` | `eu-central-1` |
| Persistence function | v9 | v11 |
| Deployed source SHA-256 | `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740` | `a0252769822fd7834c6af67fcf69259ec9bbefce7041ac3a5a36d8d6a9a90397` |
| Migration ledger entries | 14 | 17 |

## Required schema comparison

Fresh catalog/aggregate-only queries on 2026-10-28, without selecting account row contents:

| Check | Production | Staging |
|---|---:|---:|
| Account rows | 5 | 9 |
| Populated `affiliate_code` rows | 0 | 8 |
| Blank/null `affiliate_code` rows | 5 | 1 |
| Excess rows in duplicate populated-code groups | 0 | 0 |
| `public.shoir_referrals` | Missing | Present |
| Current legal-acceptance columns on `shoir_subscription_requests` (6 expected) | 0 | 6 |
| Referral-table RLS | Not applicable | Enabled |
| Referral-table RLS policies | Not applicable | 0 |
| `anon` / `authenticated` table grants on referrals | Not applicable | 0 |

Production has the account/request core tables and service-role grants. The staging catalog additionally has referral-related indexes and the `shoir_require_legal_acceptance_before_approval` trigger on subscription requests. The deployed staging v11 handler uses the legal-acceptance fields and referral table that are absent in production; deploying v11 directly to production is incompatible.

## Migration history hazard

Production's recorded ledger currently ends at `20261019140600`. Repository migration source also contains these three later historical files that are not recorded in production's ledger:

- `20261021130000_shoir_beta_legal_referrals.sql`
- `20261022110000_enforce_beta_legal_acceptance.sql`
- `20261023130000_refresh_refund_policy_acceptance_version.sql`

The first historical migration updates `affiliate_code` and `updated_at` for blank/legacy codes and rewrites duplicates. With the current observed production aggregate, its predicate would match the five existing account rows because all five codes are blank. The count is time-specific; re-check immediately before any approved rollout.

**Forbidden until independent review:** normal `supabase db push` against production with this unresolved history. It could execute the historical rewriting migration before reaching the additive safe replacement.

## Intended replacement source

- `20261026110000_safe_beta_legal_referrals.sql` adds the six acceptance columns and server-only referral table without rewriting account codes or timestamps. Its partial unique index applies to populated normalized codes and aborts transactionally on a duplicate.
- `20261027120000_enforce_current_beta_legal_acceptance.sql` installs the current approval guard for Terms `2026-10-21-beta-v1`, Privacy `2026-10-21-v1`, Refund v2 `2026-10-23-v2`, Cookie `2026-10-21-v1`, and non-null `accepted_at`.

The source candidate and synthetic PostgreSQL preservation tests have passed their reported CI suites on the PR #218 candidate. That proves neither the actual production schema state nor recoverability of a production backup.

## Required execution package before production change

1. Re-read the production and staging ledgers, schema, indexes, constraints, trigger bodies, RLS, grants, Edge Function metadata/hash, and app/deployment revisions immediately before a release.
2. Freeze the exact application commit, Edge Function source/hash, SQL files and intended order in a reviewed compatibility manifest.
3. Create/identify an approved backup or point-in-time recovery reference and test restoration to an isolated environment.
4. Build an isolated production-shaped copy from the approved recovery point. Do not copy customer data into general-purpose artifacts. Record baseline and post-migration counts plus a protected digest over the existing account identifiers, `affiliate_code`, and `updated_at` values so preservation can be proven without publishing row-level values.
5. Rehearse the precise migration-ledger reconciliation on that isolated copy. The reviewed procedure must prevent the three legacy files above from executing and must apply only their reviewed safe replacements. Never blindly mark any migration applied; document why each ledger entry is reconciled and prove the resulting schema and trigger are equivalent to the intended current contract.
6. Verify duplicate-abort behavior, missing-column/trigger behavior, transaction rollback, failure handling, forward recovery, grants, RLS, indexes, trigger definition and application/function compatibility.
7. Have an independent database/security reviewer sign the evidence and have the release owner authorize the exact commit, schema/function hashes, ordered changes, maintenance window, rollback/forward-recovery plan and stop criteria.
8. Only then execute the explicitly approved sequence. Re-read the actual production schema/function hashes afterward and run non-destructive post-deployment probes.

## Proposed order (subject to the tested rehearsal)

1. Validate the backup/PITR point and restore evidence.
2. Apply the independently reviewed additive schema/guard replacements using the reviewed migration reconciliation procedure. The procedure must ensure the three legacy scripts are not replayed.
3. Verify the resulting production columns/table/index/trigger/RLS/grants and ledger against this manifest.
4. Deploy the function build compatible with that exact schema and explicitly approved source hash. Do not deploy staging v11 before the schema contract is satisfied.
5. Run safe production post-deployment probes for approved and rejected CORS origins, login/session lifecycle, protected-admin invariant (read-only, no test login as `sho`), referrals/legal approval guard and service health.
6. Monitor against documented success and recovery criteria.

## Abort criteria

Abort and remain HOLD if any manifest/ledger difference is unexplained; any existing account identifier, referral code, or `updated_at` changes unexpectedly; a duplicate/constraint issue occurs; restoration/recovery is unproven; any current policy version is absent; the app/function/schema compatibility contract fails; required checks/reviews are incomplete; or explicit release-owner authorization is missing.

## Current operational disposition

- Earlier staging CORS/preflight and public-shell browser checks passed on an older deployed baseline. The latest release-evidence PR #211 head is a newer candidate whose exact-head staging/authenticated jobs are queued; do not carry older pass status forward or call the latest candidate accepted.
- Staging function v11 source has exact-origin CORS and protected-admin fail-closed behavior.
- Current production inventory re-read on 2026-10-28 reports `shoir-persistence` v9, source hash `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740`. The active source includes `Access-Control-Allow-Methods: POST, OPTIONS`, but still emits `Access-Control-Allow-Origin: *`; exact-origin enforcement and `Vary: Origin` remain unresolved. Do not infer security readiness from the method-header correction.
- Production release remains **HOLD / NO-GO**. This manifest is preparation, not production authorization.


## Live production CORS diagnostic — October 28, 2026

A GitHub-hosted runner made non-mutating `OPTIONS` requests directly to the actual production endpoint:

`https://gcsamrdaeraxieaagsta.supabase.co/functions/v1/shoir-persistence`

| Probe | HTTP status | `Access-Control-Allow-Origin` | Result |
|---|---:|---|---|
| Approved origin: `https://shoir-ie-app.streamlit.app` | 200 | `*` | FAIL |
| Unapproved origin: `https://unapproved-origin.example` | 200 | `*` | FAIL |
| Origin omitted | 200 | `*` | FAIL |

The recorded GitHub-runner probe showed HTTP 200 with `Access-Control-Allow-Origin: *` for the approved origin, an unapproved origin, and no Origin header. That is a time-stamped live failure. The current management-API source reread still shows wildcard CORS despite now advertising `POST, OPTIONS`; therefore the security blocker remains open. Repeat the direct live HTTP probe after any separately authorized production change. Evidence artifact `shoir-ie-production-cors-diagnostic` was created by PR #211's staging-targeted release check; its JSON report records `overall: FAIL` and `release_gate: false`. The historical staging probe passed on the previously deployed baseline. The latest exact-head staging probe is still pending; it must be rerun after the reviewed candidate is deployed to staging.

This diagnostic used only HTTP OPTIONS requests. No credentials, account content, or production data were sent, and it made no production mutation. The failure is not closed until an exact production-compatible security source is reviewed, the deployment prerequisites in this manifest are met, the authorized change is deployed, and the same direct production probe passes.
