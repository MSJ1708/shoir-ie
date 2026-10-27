# Shoir-IE Release Decision — 2026-10-27

**Decision: HOLD / NO-GO for production and paid commercial access.**

**Decision scope:** this review fixes and checks identified export, migration-test, backend deployment, and Streamlit security problems. It does not authorize production deployment, production Edge Function deployment, or production database migration.

## 1. Candidate source and CI evidence

| Area | Candidate/evidence | Current interpretation |
|---|---|---|
| PDF/PowerPoint pagination | PR #202, head `a4ef02b087f4d4da376a8dca3537544b899f5212`; [PR CI 40472138727](https://github.com/MSJ1708/shoir-ie/actions/runs/40472138727); [push CI 40472133548](https://github.com/MSJ1708/shoir-ie/actions/runs/40472133548) | Both exact-head checks passed. |
| Rendered export evidence | [Artifact 12719906502](https://github.com/MSJ1708/shoir-ie/actions/runs/40472138727/artifacts/12719906502) | Synthetic PDF inspected on all 3 pages: 67 ordered rows preserved. All 8 PowerPoint-rendered slides inspected; 67 ordered rows preserved across 7 table slides plus cover. No obvious clipping or content overflow in this artifact. |
| Local browser smoke | [Artifact 12719591615](https://github.com/MSJ1708/shoir-ie/actions/runs/40472138727/artifacts/12719591615) | Public unauthenticated Streamlit entry screen passed desktop/mobile smoke. Authenticated module routes were not run; `live-deployment-smoke` was skipped. |
| Safe referral migration | PR #205, current draft candidate head `c2b41109c26fff438e0d58c69e1e71f4ded5fef6`; [transaction integration 40474339364](https://github.com/MSJ1708/shoir-ie/actions/runs/40474339364) | PostgreSQL transaction/migration contract passed on this head. General exact-head validation was still running at the last check; recheck before any approval. |
| Admin/backend and Streamlit configuration | PR #204, current draft candidate head `30886577f826a50376cd49a8503a5334c5fb0f59` | Adds read-only administrator invariant/fail-closed handling, explicit CORS/XSRF and trusted-host allowlists, and tests that require Streamlit 1.61+ for `allowedHosts`. The current exact-head CI run was pending at the last check. Earlier source-only checks on the backend commit passed; they do not replace a fresh deployed staging test. |

PRs #202, #204, #205, and #201 remain drafts. Do not merge these candidates solely on the basis of this report.

## 2. Backend deployment parity

- Staging Supabase project: `hfhrosthswcybccepmak`.
- The reviewed PR #204 backend source was deployed to **staging only** as Edge Function v10, read-back SHA-256 `5605d40e61feac6d010e7e1097565a7090bdf3325c862cc09de32af650b5a232`.
- Read-back verified that the reserved `sho` administrator invariant is checked before a session is issued, drift returns a generic manual-review response, and the login-time tier auto-repair is absent. A preceding read-only query verified the stored role, tier, active flag and UTC expiry invariants.
- Production Supabase project: `gcsamrdaeraxieaagsta`; its `shoir-persistence` function remains at v8/hash `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`. Production function and database were not changed.
- The Streamlit CORS/XSRF/trusted-host configuration is committed in PR #204 but has **not** been deployed to the hosted Streamlit app. The latest run must pass before staging deployment of this configuration, followed by a smoke test against the actual staging hostname.

## 3. Migration safety and database parity

The historical migration `20261021130000_shoir_beta_legal_referrals.sql` contains updates to existing `shoir_accounts.affiliate_code` and `updated_at` fields. It has been applied in staging. **Do not replay this historical migration against production.**

Read-only aggregate preflight on 2026-10-27 found:
- Staging: 9 account rows, 1 blank referral code, 0 duplicate nonblank normalized referral-code groups.
- Production: 5 account rows, 5 blank referral codes, 0 duplicate nonblank normalized referral-code groups.

No individual account codes, credentials, or account row contents were selected for this aggregate check. Counts are time-specific and must be repeated on an isolated production-shaped copy immediately before any future migration.

The PR #205 additive candidate adds the policy-acceptance columns, server-only referral table, and a separate partial unique index on `LOWER(BTRIM(affiliate_code))` for populated codes. It does not rewrite existing codes/timestamps and uses a different index name from the historical index to avoid `IF NOT EXISTS` silently retaining the old expression. Its isolated PostgreSQL test seeds synthetic existing values, checks exact preservation, and verifies duplicate codes are rejected.

Important remaining migration risks:
- Staging ledger contains `20261021130000`, `20261022110000`, and recorded version `20261025164602` for the refund-policy-v2 guard; repository migration filename is `20261023130000_refresh_refund_policy_acceptance_version.sql`.
- Production ledger stops at `20261019140600` and lacks the later legal/referral schema.
- These ledgers must be reconciled using a reviewed migration manifest, not by blindly rerunning or recording migration filenames.
- A disposable local PostgreSQL test is useful, but a production-shaped isolated rehearsal, verified restore, before/after row comparisons, RLS/grant/constraint verification, and recovery drill are still required.
- No staging or production database migration was run in this review.

## 4. Authenticated staging and module acceptance

The latest authenticated release gate located during this review is historical: run [40369188234](https://github.com/MSJ1708/shoir-ie/actions/runs/40369188234) passed on staging branch SHA `9e3899d6f5147584cf27585d946fa7b5d18d92d5`. It predates the v10 staging Edge Function deployment and is **not** proof of the current deployment.

A fresh authenticated gate has not been run against the current staging application/backend pair. Required cases remain:
- staging build marker and host verification before any credentials are entered;
- login, invalid/inactive account, logout, token reuse rejection/session revocation;
- role/tier/expired-subscription permissions and privileged-operation denial;
- cross-workspace load/save denial, save/relogin restore and data isolation;
- all 96 module routes in authorized account tiers;
- current terms/policy acceptance and registration/referral flows;
- PDF, PPTX and XLSX generation, row/value preservation, import/export round trips, chart/provenance and relevant calculation correctness.

The current CI's `live-deployment-smoke` job is skipped. A fresh authenticated staging run must use disposable `shoir-e2e-*` identities and synthetic data against the exact integrated staging candidate. Do not use the protected master administrator or production/customer accounts.

## 5. Branch protection

GitHub's branch records report both `main` and `staging-e2e-20261019` as protected. The connected GitHub integration returned 403 when reading full branch-protection settings; the readable rulesets list was empty. Required status-check names, strictness, administrator enforcement and dismissal settings therefore remain unverified. A repository administrator with appropriate permissions must confirm and document these settings before release.

## 6. Commercial and Saudi legal readiness

The current Terms, Privacy, Refund, Cookie, and commercial checklist documents exist, but they are drafts and explicitly leave commercial clearance open. Before paid access, the operator must provide the accurate legal name, official business address and applicable registration details; final plan currency/total price/tax/period/renewal/cancellation/refund disclosures; a verified data inventory and retention/deletion procedures; processor/subprocessor and hosting-region mapping; cross-border transfer assessment; incident/data-subject-request procedures; SBOM/third-party license and branding review; and support/contact ownership.

Official sources to review with qualified counsel:
- SDAIA's current [laws and regulations index](https://sdaia.gov.sa/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx) lists the PDPL, implementing regulations, and rules on personal-data transfer outside the Kingdom.
- The official [Saudi E-Commerce Law translation](https://misa.gov.sa/app/uploads/2025/07/E-Commerce-Law.pdf) addresses electronic advertising, service-provider disclosures and consumer contract cancellation, subject to its statutory terms and exceptions.

No independent human security reviewer or Saudi-qualified lawyer approval is recorded on PR #204/#205 in the evidence checked. This document is not a legal opinion or independent certification.

## 7. Conditions to change HOLD to GO

All items below are mandatory and must refer to the same exact integrated candidate:
1. Exact-head PR and push CI pass on PRs #202, #204 and #205, including the final PostgreSQL preservation/index test and Streamlit security-config regression test.
2. Obtain and record independent human security review of the current deployed Edge Function/config and independent database/migration review.
3. Deploy the reviewed Streamlit config to staging only through the approved process; verify the actual hosted version, CORS origins and allowed hosts.
4. Run and pass the complete authenticated staging release gate, including exports, permissions and workspace isolation, on the exact integrated candidate.
5. Complete the production-shaped isolated migration rehearsal, verified backup/restore and approved migration-ledger reconciliation plan that explicitly excludes the historical destructive migration.
6. Verify the actual required branch checks/protection enforcement with repository-admin access.
7. Record Saudi-qualified counsel's review and the operator's approved commercial details/data protection controls.
8. Obtain explicit written release-owner approval tied to the exact candidate SHA and a coordinated production rollout/rollback plan.

## Final decision

**HOLD / NO-GO.** The identified PDF pagination failure is fixed and exact-head PR/push checks passed for the inspected export commit. The backend security mismatch was corrected on staging only. Migration checks were strengthened to cover existing-value preservation and normalized uniqueness. These are meaningful fixes, not a production clearance.

No production deployment, production Edge Function update, production database migration, production setting change, paid-access activation, or PR merge was performed as part of this review.
