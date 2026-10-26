# Staging and production schema/function parity — 26 October 2026

**Captured at:** 2026-10-26T12:16:21Z. Read-only inventory only. No migration or Edge Function was deployed. Production parity is incomplete; do not deploy.

## Project identities

| Environment | Project ref | Status | Region / database |
|---|---|---|---|
| Staging | hfhrosthswcybccepmak | ACTIVE_HEALTHY | eu-central-1, PostgreSQL 17.11.0.003 |
| Production | gcsamrdaeraxieaagsta | ACTIVE_HEALTHY | eu-central-1, PostgreSQL 17.6.1.166 |

## Edge Function inventory

| Field | Staging | Production |
|---|---|---|
| Function | shoir-persistence | shoir-persistence |
| Status / version | ACTIVE / 9 | ACTIVE / 8 |
| Bundle SHA-256 | 0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e | 410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d |
| Source inventory | Includes index.ts and security.ts; supports referral session and legal/refund-policy contract | Older index.ts bundle; no security.ts file reported; referral/legal/refund-policy contract absent |

Staging source/version inventory is VERIFIED PASS as a deployment fact, not as full runtime acceptance. Version equality is not a valid deployment criterion on its own.

## Migration reconciliation

| Migration / contract | Staging | Production | Status |
|---|---|---|---|
| 20261019124815_server_side_login_rate_limits.sql | Applied | Applied | APPLIED in both; do not rerun |
| 20261019140600_atomic_subscription_request_decisions.sql | Applied | Applied | APPLIED in both; do not rerun |
| 20261021130000_shoir_beta_legal_referrals.sql | Applied | No record | PENDING in production |
| 20261022110000_enforce_beta_legal_acceptance.sql | Applied | No record | PENDING in production |
| 20261023130000_refresh_refund_policy_acceptance_version.sql | Ledger version 20261025164602 with that filename as name | No record | CONFLICTING ledger version/name association |

The unusual refund-policy entry must be reconciled against the canonical file, migration SQL, actual DDL and operation logs. Do not rewrite migration history or rerun it blindly.

## Directly observed schema differences

| Feature | Staging | Production |
|---|---|---|
| public.shoir_referrals | Present | Absent |
| terms_accepted | Present | Absent |
| terms_version / privacy_policy_version / refund_policy_version / cookie_policy_version / accepted_at | Present | Absent |
| Legal acceptance trigger | Reported present in prior read-only inspection | Absent |
| shoir_* table count | 12 | 11 |

Before preparing any production migration, inspect exact canonical SQL, triggers, constraints, indexes, grants and function dependencies. Assess the impact on existing users and pending subscription requests without extracting identifiers.

## RLS and grants

All inventoried public shoir_* tables reported RLS enabled. Policy/grant inventory showed server-only policies and no explicit anon/authenticated/PUBLIC grants for inspected shoir_* tables. Staging security advisor returned INFO that public.shoir_referrals has RLS enabled but no policies. This appears consistent with a server-only table given the grants inventory; confirm with owner and keep the advisor finding documented. No policy or grant was changed. Never add broad client access just to eliminate the advisor warning.

## Master-admin invariant

Aggregate-only read-only checks showed exactly one Enterprise Admin record and one exact match in each environment: tier Enterprise Plus Tier ($399), active=true, expiry 2099-01-01T00:00:00Z. No identity fields were queried, and no account was tested or changed.

## Reconciliation checklist

- [x] Confirm project refs and project health.
- [x] Capture migration ledgers.
- [x] Compare relevant table, column and table-count differences.
- [x] Inspect Edge Function version, bundle hashes and source presence.
- [x] Inspect RLS/policy/grant inventory and security advisor.
- [ ] Reconcile refund-policy migration history version/name discrepancy.
- [ ] Compare all actual trigger, constraint, index, function and grant definitions.
- [ ] Verify backup recovery point and test restoration in an isolated environment.
- [ ] Review migration/function deployment order and compatibility.
- [ ] Run staging legal acceptance, session, subscription and negative access tests.
- [ ] Obtain independent technical review and explicit production authorization.
- [ ] Verify production after authorized deployment with post-deploy smoke and aggregate invariant check.

**Status:** production parity FAIL. No production change was made.