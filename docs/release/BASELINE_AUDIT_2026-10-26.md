# Shoir-IE baseline audit — 26 October 2026

**Captured at:** 2026-10-26T12:16:21Z  
**Method:** Read-only GitHub, workflow, Supabase schema/migration/function, advisor and aggregate account-invariant inspection.  
**Candidate baseline:** main 267be8889c310d90141c047d8aadd42c942423fb; staging-e2e-20261019 8b36e3737705867019b9cf29e603cfc37e7911e6.  
**Decision:** NO-GO. Keep BETA visible. Production unchanged.

## Repository and source control

| Item | Result | Status |
|---|---|---|
| Repository | MSJ1708/shoir-ie, public, default branch main | VERIFIED PASS |
| main head | 267be8889c310d90141c047d8aadd42c942423fb | VERIFIED PASS |
| staging head | 8b36e3737705867019b9cf29e603cfc37e7911e6 | VERIFIED PASS |
| Main branch protection API field | protected=false | FAIL |
| Visible repository rulesets | Empty array | FAIL |
| Detailed protection endpoint | 403 Resource not accessible by integration | BLOCKED |
| Open pull requests | 18; all were drafts in the captured response | VERIFIED PASS |
| Review submissions on #196 and #197 | None returned | BLOCKED |

An authorized repository administrator must configure and verify PR requirements, at least one independent approval, stale-review dismissal, conversation resolution, exact mandatory check names, and force-push/deletion/direct-push restrictions. The connected integration could not update branch protection or read its detailed configuration.

## CI and hosted authenticated gate

- Staging validation run 40273588613 passed on SHA 8b36e3737705867019b9cf29e603cfc37e7911e6.
- Authenticated release-gate run 40273588637 on that exact staging SHA was SKIPPED.
- PR #196 validation run 40303682913 on SHA 7c0219385fe33bcb68b963b23dfac9a9c0fb886c reported the test job successful, but live-deployment-smoke was SKIPPED.
- The latest actual manual authenticated gate found was run 39613907604 on older SHA 3c91c83db17724f415e7fb92d83ed338d9eb5a9a; it FAILED. Backend lifecycle/isolation passed and all 96 module routes passed, but the module matrix reported two logout-settlement failures for Enterprise Plus and Research Pack. The separate browser shell/Excel/logout step passed. This older run is diagnostic only, not evidence for the current candidate.
- A redacted artifact named shoir-ie-authenticated-release-evidence exists for the failed old run. It is stale and does not prove release acceptance.
- The GitHub connector is GET-only for workflow inspection, lacks workflow-dispatch write access, and cannot inspect Actions secret values. No dummy marker commit was pushed to force a workflow.

## Supabase baseline

| Environment | Project ref | Status | Region / DB |
|---|---|---|---|
| Staging | hfhrosthswcybccepmak | ACTIVE_HEALTHY | eu-central-1, PostgreSQL 17.11.0.003 |
| Production | gcsamrdaeraxieaagsta | ACTIVE_HEALTHY | eu-central-1, PostgreSQL 17.6.1.166 |

| Item | Staging | Production |
|---|---|---|
| shoir-persistence | Active v9; SHA-256 0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e | Active v8; SHA-256 410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d |
| shoir_referrals table | Present | Absent |
| Terms/refund acceptance columns | Present on subscription requests | Absent |
| Beta/legal/referral migration records | Present | Absent |
| shoir_* table count | 12 | 11 |

Staging migration records include 20261021130000_shoir_beta_legal_referrals and 20261022110000_enforce_beta_legal_acceptance. The refund-policy migration history uses version 20261025164602 with name 20261023130000_refresh_refund_policy_acceptance_version, whereas the canonical file is named with version 20261023130000. Reconcile the ledger/name mismatch against actual SQL, DDL and logs before planning production changes. Never rerun an applied migration blindly.

The staging security advisor reports INFO for public.shoir_referrals: RLS enabled but no policies. The read-only grants inventory returned no explicit grants to anon, authenticated or PUBLIC for the inspected shoir_* tables, suggesting this table is server-only. No policy/grant changes were made; confirm this intent in review.

## Master-administrator invariant

Aggregate-only read-only queries returned exactly one Enterprise Admin row and exactly one exact invariant match in each database: role Enterprise Admin, tier Enterprise Plus Tier ($399), active=true, expiry 2099-01-01T00:00:00Z. No username or identity field was queried. No master-account login/testing or mutation occurred.

## Canonical 100-tool matrix

Path: docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv, main blob SHA d1d5cb14c4b2e78ece1d8d78a19b26329761025a.

- 100 data rows, 100 unique IDs and 100 unique canonical names; no duplicates.
- 98 IMPLEMENTED_NEEDS_VALIDATION.
- 2 EXTERNAL_CONFIGURATION_REQUIRED: T096 and T098.
- 0 VERIFIED_WORKING.
- Tier counts: Starter 26, Mid-Tier Pro 25, Professional 24, Enterprise 15, Enterprise Plus 4, Research Pack 6.

Statuses were not upgraded because the current evidence does not support it.

## Hosted app and next steps

The staging source includes staging_app.py and a staging E2E guard that requires the intended staging project, HTTPS function path, hostname-only app-host variable and publishable/anon key, and rejects the production Streamlit hostname. This verifies source safeguards, not Streamlit Cloud settings or the running app revision. Connected tools could not verify the exact hosted staging URL, selected branch, entry point, configured secrets/variables, banner or deployed commit. Verify through Streamlit Cloud and a fresh browser session.

Immediate owners:
1. Repository administrator: protect main and provide saved-settings evidence.
2. GitHub Actions administrator: confirm the required staging-only secrets/variables and synthetic shoir-e2e-* fixtures, then dispatch the current authenticated gate.
3. Streamlit Cloud owner: confirm staging URL, repo/branch/entry point, staging secrets separation, banner and deployed SHA.
4. Supabase release owner: reconcile migration history and prepare reviewed, backward-compatible production change plan.
5. Integration and identity owners: configure real T096 endpoint and T098 provider, or keep them blocked.
6. QA/tool owners: validate modules against independent reference fixtures, permissions, persistence, exports and hosted evidence.
7. Saudi legal/privacy counsel, business and tax/payment owners: review entity, notices, PDPL/data transfers, payments/refunds/referrals/invoicing and claims.
8. Operations and release owners: verify backup restoration, monitoring, incident response, rollback and record explicit GO before release.

No production schema/function/app, user account, tier, payment, subscription, branch-protection or BETA setting was changed during this audit.