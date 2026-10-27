# Shoir-IE Paid-Pilot Readiness Gate

**Historical snapshot:** 26 October 2026; see the 27 October candidate update below  
**Decision:** **NO-GO** for paid-pilot activation and general availability on current evidence.  
**Scope:** readiness checklist and owner runbook; not legal, tax, privacy or security advice.

This document records evidence and required actions. It does not certify Saudi legal compliance, security, commercial registration, calculation accuracy, or production readiness. The operator identity, deployment/provider facts and qualified reviews must be supplied by the real accountable owner.

## Current candidate update — 27 October 2026

This section supersedes conflicting historical candidate/status statements later in this document. It is **not** a production release approval.

- Current staging baseline reviewed: `staging-e2e-20261019` at `76419a9842f88292f94d706ca9b20bab63c45550`.
- Exact-commit CI validation passed: [run 40480842355](https://github.com/MSJ1708/shoir-ie/actions/runs/40480842355).
- Authenticated staging release gate passed using disposable `shoir-e2e-*` accounts only: [run 40480842338](https://github.com/MSJ1708/shoir-ie/actions/runs/40480842338). The run explicitly avoided the reserved master administrator.
- This evidence covers the pre-#207/#208 staging candidate. The SAP/Oracle foundation and the focused recovery/lineage/RCM/RNLE candidates are not included in this SHA and require their own exact-head checks plus a fresh gate after integration.
- Production is still **HOLD / NO-GO**: production Edge Function remains v8 while staging is v10; production and staging migration histories differ. No production function deployment or migration was performed.
- Branch protection is enabled, but the connected review API could not verify the exact required-check policy; a repository owner must confirm it in GitHub settings.
- The successful staging gate does not establish legal clearance, independent formula validation, PDPL compliance, database recovery readiness, or authorization for paid access.


## Latest live service recheck — 27 October 2026, 10:40 UTC

**Decision remains HOLD / NO-GO.** This dated recheck is read-only operational evidence. It does not approve production changes, legal text, paid access or a deployment.

### Exact candidate and tests

- Current staging branch head observed in the GitHub comparison: `0558c23d59a3f0b79558a8d3407869d0238aceaf`.
- PR #208 head: `5f0215d4d2ac0cde925bbd59e020810216e45598`. It is 31 commits ahead of the merge base and 2 commits behind staging; the merge base is `76419a9842f88292f94d706ca9b20bab63c45550`. Do not treat the PR-head test as final integrated-candidate acceptance.
- Exact-head validation run [40487656400](https://github.com/MSJ1708/shoir-ie/actions/runs/40487656400) was **queued** at recheck. The `test` job was queued and `live-deployment-smoke` was **skipped**. No final pass is claimed.
- The 100-row tool matrix reports **98 IMPLEMENTED_NEEDS_VALIDATION, 2 EXTERNAL_CONFIGURATION_REQUIRED, 0 VERIFIED_WORKING**. These are implementation states, not a production verification rate.
- Staging and main have diverged. Do not merge the staging line into main as a shortcut; reconcile source history deliberately after current-candidate validation.

### Read-only Supabase state

Project refs are identifiers only; no credentials were read.

| Check | Production | Staging |
|---|---|---|
| Project | `gcsamrdaeraxieaagsta` | `hfhrosthswcybccepmak` |
| Database | PostgreSQL 17.6.1.166 | PostgreSQL 17.11.0.003 |
| `shoir-persistence` | v8, SHA-256 `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d` | v10, SHA-256 `5605d40e61feac6d010e7e1097565a7090bdf3325c862cc09de32af650b5a232` |
| Canonical-admin protection in deployed function source | Missing; login still contains a tier/`updated_at` auto-repair update | Present; invalid protected-admin state fails closed and is not auto-repaired |
| Migration history | Through `20261019140600_atomic_subscription_request_decisions` | Includes the same history plus three additional migration records |

A read-only query found the reserved account invariant currently matches in both projects: role `Enterprise Admin`, tier `Enterprise Plus Tier ($399)`, active `true`, expiry `2099-01-01 00:00:00 UTC`. No administrator login or account mutation was performed. The matching row does **not** make production's auto-repair code safe; the deployed production function remains older than staging.

Staging has the legacy `20261021130000_shoir_beta_legal_referrals` migration, `20261022110000_enforce_beta_legal_acceptance`, and a policy refresh recorded as `20261025164602` with name `20261023130000_refresh_refund_policy_acceptance_version`. Production lacks the legal-acceptance columns and `public.shoir_referrals` table. The earlier referral migration is documented as rewriting existing affiliate codes and timestamps. **Do not replay it in production. Do not deploy staging function v10 directly to production while schema/function compatibility is unresolved.** First approve a migration/function manifest, perform isolated preservation and restore rehearsal, and verify the actual deployed source.

The staging `public.shoir_referrals` table has RLS enabled and no policies. Read-only privilege checks showed `anon` and `authenticated` have no table privileges while `service_role` has the required server-only CRUD privileges. The Supabase security advisor flags the missing policy as informational; retain the server-only model and independently verify the grants rather than adding broad client policies just to silence the advisory. Production's security advisor returned no security lints in this snapshot; this is not a security certification. Performance advisors returned informational unused-index findings (16 production, 19 staging), which should be reviewed, not blindly deleted.

### Eight closeout gates

1. Refresh/reconcile PR #208 against current staging, then obtain a successful exact-head full validation result.
2. Run a fresh authenticated staging release gate on that exact integrated candidate using disposable `shoir-e2e-*` accounts; ensure mandatory probes fail closed and hosted smoke is not skipped.
3. Verify save/reload/re-login, revoked-session behavior, six-package entitlement boundaries, direct-route/action denial and two-user cross-workspace isolation on the hosted candidate.
4. Round-trip synthetic XLSX, PDF, PPTX and ZIP artifacts; open/parse all outputs and inspect every PDF page and PowerPoint continuation slide, units, formulas, labels, assumptions, warnings and provenance.
5. Configure and verify required reviews and named status checks for `main` and `staging-e2e-20261019`. The latest documented 26 October branch-settings snapshot said the required-check contexts were empty (and staging enforcement was off); re-check the actual current settings before calling this complete.
6. Approve a production-compatible Edge Function/migration plan, preserve the canonical administrator without login-time mutation, reconcile the migration ledger and prove forward/rollback compatibility in an isolated production-shaped rehearsal.
7. Produce successful backup/restore and rollback evidence for the exact release candidate; verify the Streamlit deployment branch, commit, entry point and secret/configuration presence without disclosing values.
8. Obtain qualified Saudi legal/privacy review of the actual operator identity, commercial registration, PDPL/data flows and retention/transfers, customer notices, calculation limitations, refund/cancellation, copyright/IP and commercial terms. Populate the accountable owner's facts and obtain explicit release-owner approval before enabling paid access.

## PR recommendation disposition ledger — 27 October 2026

This ledger separates current implementation candidates from superseded drafts. It is not merge authorization and does not replace reviewing the actual patch, exact-head checks or deployment evidence.

### Active integration/release PRs

| PR | Recommendation and disposition | Required action |
|---|---|---|
| #208 | Current focused Workbench integration: T006/T020/T037/T039/T044/T046 and additional bounded methods. Matrix is 98 IMPLEMENTED_NEEDS_VALIDATION, 2 EXTERNAL_CONFIGURATION_REQUIRED, 0 VERIFIED_WORKING. | Refresh against the latest staging base (the head was 2 commits behind when checked); pass exact-head CI, then rerun the authenticated release gate and hosted tests on the integrated SHA. |
| #211 | This recheck and rollback-manifest update. | Keep draft until documentation/validation checks pass and the dated live evidence has independent review. |
| #212 | Unique mobile auth-tab wrapping and tab geometry checks selectively ported from #184. | Pass exact-head tests and run desktop plus 390px mobile hosted smoke; smoke was skipped in the workflow state last queried. |
| #213 | Main-based source fix to make protected administrator login read-only and fail closed on invariant drift. | Pass Python/Deno tests and review; do not deploy until production schema/function parity, rollback and release approval are separately satisfied. |
| #214 | Main-based Streamlit CORS/XSRF and known-host allowlist hardening, with config regression tests. | Pass exact-head tests and verify the actual hosted domains/configuration; source change alone does not update the live app. |
| #199 | Historical live-state/parity snapshot on main; its findings were the basis of the newer, dated #211 recheck. | Preserve for history; do not treat it as current evidence or merge an old snapshot into staging. |
| #191 | Older main-based T006 recovery, T020 lineage and T039 registry draft. | These areas are now represented in the newer #208 staging candidate. Do not merge the stale stack independently; compare only for uncovered changes after #208 validation. |
| #189 | Earlier staging release-candidate verification branch. | Superseded by the newer candidate; run acceptance on the final integrated SHA rather than reuse old results. |
| #188 | Older stacked RNLE/T046 implementation. | T046 is present in #208; do not merge this stale branch without a target-level audit proving unique code. |
| #184 | T044 RCM plus mobile smoke/landing fixes on an older stacked base. | T044 work overlaps #208. The distinct mobile tab/geometry tests have been ported to #212; keep the old stack out of the merge path. |
| #182 | Nine focused methods on the old `audit/shoir-100-tools-20261023` base. | Compare T015/T033/T036/T037/T049/T052/T058/T062/T071 against the current target registry and tests. Cherry-pick only unique, reviewed methods. |
| #181 / #180 | Earlier waves of 100-tool methods on older main-based branches. | Audit target-by-target against merged method libraries and #208's runtime registry; do not wholesale merge shared Workbench/registry files. |
| #179 | Earlier unit-converter and fail-closed readiness foundation. | Verify whether any recommendation is still uncovered in the current implementation before selectively porting; preserve the canonical tier-gate tests. |
| #178 / #175 / #174 / #173 / #172 | Earlier competing grouped-tool-library/registry/runner stacks. | Treat as superseded candidates pending a file/target comparison with merged #183/#193 and current #208. Do not merge the old stacks as-is. |
| #170 | Main-based legal notice, consent and referral draft. | Do not merge or publish unchanged. Align it with the safer migration path, actual product behavior, migration history, and qualified Saudi legal/privacy review. Referral attribution is not a promised reward/discount program. |

### Previously integrated recommendations — still subject to release gates

| PR | Integrated scope | Remaining boundary |
|---|---|---|
| #200 | Authenticated release-gate logic now fails closed when mandatory probes are skipped/unknown. | The current integrated candidate still needs a fresh gate; skipped live smoke is not a pass. |
| #202 | PDF/PPTX pagination/readability correction. | Inspect the exact-candidate generated PDF pages and every PPTX slide, including continuation pages, with parseable artifacts attached. |
| #203 | XLSX formula/URL injection safeguards. | Re-test all relevant export paths with hostile synthetic strings and parse the produced workbook. |
| #205 | Non-destructive additive referral/legal schema path and rehearsal plan was added to the staging line. | The migration has not been authorized/applied to production; historical staging migration rewrote data and must not be replayed in production. |
| #206 | Admin invariant, Streamlit security settings and regression tests are integrated in staging; deployed staging function is v10. | Production still serves v8 and its login handler still auto-repairs the reserved admin. PR #213 carries the source-level correction to a main-based branch; no production deploy has occurred. |
| #207 | Read-only SAP/Oracle adapter and product/IT specification integrated in staging. | Specification-only; no provider transport, credentials, customer tenant, live sync or writes. Do not market the connectors as connected. |
| #210 | Paid-readiness, PDPL inventory, pilot acceptance, rollback and legal-review templates integrated in staging. | Documentation is not verification. Counsel/privacy review, actual operator facts and all acceptance evidence remain outstanding. |

The open-stack history is deliberately not being merged wholesale. The reviewed base is heavily diverged: the last comparison found staging and main differ by 106 versus 412 commits from their merge base. Every integration must use a clean base and preserve exact-head CI and scope boundaries.

**Release recommendation: NO-GO for paid launch or production deployment on the evidence available at this recheck.**

## 1. Technical launch gate

| Requirement | Status | Evidence / action to close |
|---|---|---|
| Main CI at exact current main SHA | PARTIAL | At the initial audit SHA 72e498d892b9eb088d34be940fc1f6d97b482c1a (now superseded by the 26 Oct recheck), test, engine regression, transaction contract, Edge Function verification and security-quality passed. Hosted public smoke failed. See [validation run 40273481812](https://github.com/MSJ1708/shoir-ie/actions/runs/40273481812). |
| Production deployment/source parity | FAIL / BLOCKED | Public app reports missing durable_account_store.edge_referral_summary; current source contains this function. Verify Streamlit branch/commit/entry point and deployed source, then prepare a version-compatible bundle and rollback plan. No production action was performed. |
| Staging branch validation | PARTIAL | Branch staging-e2e-20261019 at 8b36e3737705867019b9cf29e603cfc37e7911e6 passed validation [run 40273588613](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588613). Authenticated release gate [run 40273588637](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588637) and hosted smoke were skipped. |
| Branch protection | FAIL | GitHub says main is unprotected; rulesets empty; required contexts empty. Repository admin must enable required reviews, status checks and conversation resolution. Reread the resulting settings afterward. |
| Registry and matrix | PASS for structural row count only | The current matrix has 100 tool rows: 98 IMPLEMENTED_NEEDS_VALIDATION, 0 FOUNDATION_ONLY, 2 EXTERNAL_CONFIGURATION_REQUIRED, 0 VERIFIED_WORKING. These are not all production-ready. |
| Authenticated tier/route/direct-action checks | NOT RUN for final candidate | Run the dedicated authenticated release gate with only disposable shoir-e2e-* accounts. Cover all six packages, unknown tier/tool, expired/revoked session, Copilot, exports, direct route/action and mutations. Do not use the master administrator account. |
| Tenant/RLS/RPC checks | NOT ESTABLISHED for final candidate | Use two distinct test users/workspaces; prove server/database denial for cross-tenant read, list, update, insert, delete, export and direct-object reference. Capture redacted artifacts. |
| Save/reload/re-login | NOT ESTABLISHED for final candidate | Confirm writes and confirmed status on the actual staging service; verify reload after new login; test write failure, stale policy and revoked session. |
| Import/export | NOT ESTABLISHED for final candidate | Round-trip real synthetic XLSX, PDF, PPTX and ZIP artifacts; open/parse them and inspect formulas/units, metadata, labels, assumptions, warnings, provenance, file names and empty/malformed/oversized inputs. |
| Browser and RTL | PARTIAL | Main public shell smoke fails; staging hosted smoke skipped. Run authenticated browser checks on desktop and mobile, plus Arabic/RTL only if publicly claimed. |

### Safe test identity requirements

The current authenticated gate checks dedicated test-account configuration, expects the test identities to begin with shoir-e2e-, and validates the configured staging host before using credentials. Keep test secrets in GitHub Actions secrets/variables. Never print secret values or dump environment values. Do not copy production credentials into staging. Keep synthetic datasets labeled in results and exports.

## 2. Paid-pilot scope and calculation validation

A paid-pilot offer must name the exact tool IDs included. The current source matrix marks zero tools VERIFIED_WORKING; therefore there is no evidence-backed paid-pilot subset established by the current matrix.

Before any tool is marketed as operational, attach a per-tool acceptance row with:

- stable ID/name and minimum tier (Research Pack remains a distinct add-on, not included automatically with Enterprise Plus);
- complete input schema, required units, validation, equation/method and assumptions;
- independent reference/known case, expected values and tolerance;
- boundary, invalid, missing, non-finite and unit-conversion tests;
- execution-time entitlement tests for UI and direct action;
- persistence, export and provenance test evidence;
- limitations, uncertainty and required human review;
- exact candidate SHA, CI/browser run, artifact location and named reviewer role.

Do not market heuristic results as globally optimal, initial risk screens as certified assessments, a simulation as a forecast guarantee, AI output as professional sign-off, or estimated ROI as verified savings. Safety, ergonomics, maintenance, quality, workforce and consequential industrial decisions require the appropriate qualified human review. No fictional case study, synthetic dataset, projected saving or example customer result may be presented as actual evidence.

## 3. Saudi operator and business facts

**Status: BLOCKED — real operator identity and qualified review required.**

The accountable owner must supply and verify the actual person/entity that will contract, own the software, issue invoices, receive payments and act as privacy controller/operator. These are factual inputs, not blanks to publish:

| Fact to verify | Required evidence | Status |
|---|---|---|
| Legal name / legal form | Actual identity and formation/registration records | BLOCKED |
| Commercial registration and permitted activity | Current official record / advice about suitable activity | BLOCKED |
| Official address and contact route | Verified national/business address and support contact | BLOCKED |
| Contracting, invoice and payment entities | Matching legal name, invoices and payment account ownership | BLOCKED |
| Tax/Zakat/VAT status | Qualified Saudi tax advice based on entity, supplies, customer geography and turnover | BLOCKED |
| Product / trade name | Search and document relevant brand/trademark risks; obtain counsel advice | BLOCKED |
| Customer geography and language | Owner-approved target markets, language promises and support coverage | BLOCKED |

The Saudi Ministry of Commerce describes establishment registration through the Saudi Business Center and indicates that establishment details include business activities, approved address and e-commerce information where applicable: https://mc.gov.sa/en/eservices/Pages/ServiceDetails.aspx?sID=38 and https://mc.gov.sa/en/Pages/Start-your-project.aspx. This is reference material for a qualified adviser, not a conclusion that a specific Shoir-IE registration type is correct.

ZATCA's VAT registration page says its individual registration service targets individuals whose annual revenues exceed SAR 375,000 and describes optional registration between SAR 187,500 and SAR 375,000: https://www.zatca.gov.sa/en/eServices/Pages/eservices-002.aspx. The threshold and obligation must be assessed for the actual operator, taxable supplies, residence and other relevant facts; do not hardcode a tax status from the product price alone.

## 4. Terms, privacy notice and customer-facing claims

**Status: Versioned policy source files exist on current main, but qualified Saudi legal review and factual alignment remain BLOCKED.**

Current main contains versioned `docs/TERMS_AND_CONDITIONS.md` (2026-10-21-beta-v1), `docs/PRIVACY_POLICY.md` (2026-10-21-v1), `docs/REFUND_POLICY.md` (2026-10-23-v2), `docs/COOKIE_POLICY.md` (2026-10-21-v1), `docs/LEGAL_RISK_REGISTER.md`, and `docs/THIRD_PARTY_LICENSE_REVIEW.md`; the README links to the policy documents. Their presence in Git does not prove that the current live app displays the same versions or constitute qualified legal approval. The operator's full legal identity, official address and applicable registration details remain incomplete. `docs/COMMERCIAL_LAUNCH_CHECKLIST.md` is absent from current main; it is on open draft PR #170 and a review-only copy is preserved in this audit PR under [docs/release/legal-drafts](https://github.com/MSJ1708/shoir-ie/tree/agent/pr-integration-release-audit-20261026/docs/release/legal-drafts).

PR #170 is 47 commits ahead / 334 behind current main. Direct file comparison found much of its policy/consent/referral implementation already matches main, while the PR branch remains on refund-policy v1 and does not contain main's v2 acceptance migration/tests. Do not merge that stale stack wholesale. Its code differences and any remaining unique checklist material must be reconciled on a current-main-based branch after review. Current policies and internal legal drafts are review materials, not approval or launch clearance. The main legal risk register explicitly says Shoir-IE is not legally cleared for commercial production. Before paid use:

A separate internal-review bundle is prepared in this audit PR under [docs/release/legal-drafts](https://github.com/MSJ1708/shoir-ie/tree/agent/pr-integration-release-audit-20261026/docs/release/legal-drafts): terms, privacy, refund/cancellation, cookie and launch checklist copies carry explicit “not for customer use/publication” headers; calculation/decision-support disclaimer and attribution-only referral rules are additional drafts. [The release gate](https://github.com/MSJ1708/shoir-ie/blob/agent/pr-integration-release-audit-20261026/docs/release/PAID_READINESS_GATE.md) and [privacy data inventory template](https://github.com/MSJ1708/shoir-ie/blob/agent/pr-integration-release-audit-20261026/docs/release/PDPL_DATA_INVENTORY_TEMPLATE.md) are operational review aids only. None of these drafts is legally approved or placed in public app policy paths.

- Have qualified Saudi counsel review Terms of Service / beta or paid-pilot agreement, privacy notice, refund/cancellation, subscription and renewal, complaints, acceptable use, confidentiality, data ownership, warranty/liability language and governing law against the real operator and service behavior.
- Ensure the UI names the current policy version; record acceptance (actor, timestamp and exact version) server-side; fail closed if it cannot be recorded or the required version is stale.
- Distinguish attribution-only referrals from rewards. No discount, commission, free month or reward should be promised or activated without separate approved rules and a tested implementation. Preserve current manual-payment handling unless an explicitly approved change is made.
- Ensure plan names, tier scope, price, currency, interval, renewal, expiry, manual payment, failed payments, refund/cancellation and support terms match the actual service. Do not activate a live payment system from this audit.
- Ensure customer marketing claims describe only verified tool IDs and explicitly label demo/synthetic results and all unverified savings.

## 5. PDPL data map and operational privacy controls

**Status: BLOCKED — hosting/provider facts and operations evidence are incomplete.**

The current legal risk register says the actual provider and region inventory, transfer path, retention/deletion coverage, data-subject workflow and incident process are not fully evidenced. Build and confirm the factual data map for:

- registration/account/profile, workspace users/roles, support messages and consent records;
- uploaded Excel/workbooks, raw/cleaned datasets, industrial/customer data, input values, calculation results, scenarios and exports;
- logs, audit/diagnostic bundles, analytics and telemetry;
- AI/Copilot prompts, responses, any model/provider and data sent to it;
- email and support vendors, payment transaction identifiers, payment-proof attachments, referrals;
- primary database, object/file storage, caches, local files, backups, subprocessors and vendor support paths.

For each flow record: precise fields, purpose, legal basis, actual system/provider, storage country/region, roles, recipients/processors, retention period, deletion behavior in primary storage/logs/backups/provider, access/correction/deletion request path, transfer safeguards, incident escalation and responsible owner. Never state that a provider is hosted in Saudi Arabia or transfers are compliant without checking actual service configuration and contract.

Official Saudi reference points:
- SDAIA PDPL knowledge center, including the law, implementing regulation, transfer regulation and current guidance: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/
- SDAIA guide for controllers and processors: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPLCP/
- SDAIA transfer regulation and related official materials: https://sdaia.gov.sa/ar/SDAIA/about/Documents/General%20Rules%20for%20the%20Transfer%20of%20Personal%20Data%20outside%20the%20Geographical%20Borders%20of%20the%20Kingdom.pdf

These sources are starting points for counsel/privacy review, not a claim of compliance.

## 6. IP, dependencies and assets

**Status: INCOMPLETE / BLOCKED.**

The repository's existing Third-Party Licence Review explicitly remains incomplete. Before commercial release:

- Generate an SBOM for the exact release candidate; record tool/version, lockfiles, direct and transitive dependencies, vulnerabilities and accepted/fixed findings.
- Review licenses and source/ownership for dependencies, images, fonts, icons, datasets, demo data, examples, copied snippets and any generated/third-party assets.
- Review repository history and contributor/contractor assignments for code ownership and permission; investigate and rotate any actual secret that may have been committed.
- Run relevant trademark/name searches and retain result evidence; obtain professional advice on name ownership and protection.
- Publish an appropriate third-party notices file where required. A proprietary root LICENSE does not replace third-party obligations.

SAIP publishes a software/application copyright registration service and related copyright guidance: https://www.saip.gov.sa/en/services/copyrights/copyr1 and https://www.saip.gov.sa/en/services/copyrights. Registration availability is not proof that every ownership/license issue has been cleared.

## 7. Billing, manual payment, invoices and referrals

**Status: NOT READY; real provider and legal/tax facts missing.**

- Preserve the current STC Pay QR/manual-payment workflow unless an explicitly approved change is specified. Do not imply that payment is automatically reconciled if approval is manual.
- Confirm the contracting operator and payment account holder, provider eligibility/terms, accepted currency/payment types, settlement, transaction reference, invoice issuer and refund/chargeback process.
- Before production billing, test sandbox transitions: pending, success, failure, duplicate/delayed webhook, invalid signature, refund, chargeback, cancellation, plan change, expiry and renewal. Provider-reported authoritative server state must control access; no client redirect/local flag can grant paid access.
- Verify the actual invoicing and tax requirements with a qualified Saudi tax adviser. Do not invent a VAT registration number or tax status.
- Keep referral attribution separate from reward logic; test self-referral, duplicate attribution and status authorization. Leave any rewards inactive until separate written terms, owner approval, technical tests and legal review exist.

No real payment, payment-provider configuration or live billing action was performed by this audit.

## 8. Support, monitoring, recovery and launch operations

**Status: NOT ESTABLISHED for a paid customer environment.**

Before a paid pilot, name accountable roles (not invented individual names) and document:

- customer onboarding, supported browser/device/language matrix and accurate feature table;
- support contact, complaints and billing escalation, privacy-request handler and response target;
- account/plan/expiry/consent troubleshooting and admin audit workflow;
- incident severity, alert route, on-call owner, data-breach triage, customer notifications and regulator escalation where required;
- backup schedule, evidence of successful restore, recovery time objectives, rollback commands/steps and maintenance communication;
- release manifest listing exact app commit, DB migration files, Edge versions, required configuration names/presence, approvals and pre/postflight checks.

The authenticated workflow being skipped is not evidence of support readiness or recoverability. All incident and restore procedures must be exercised in a safe non-production environment.

## 9. Production deployment change control

**Status: NOT AUTHORIZED. No production mutation was performed.**

Do not deploy merely because a PR or staging test passes. Before an owner-authorized production release:

1. identify exact source commit, entry point, DB project reference, migration history and Edge Function deployed versions;
2. reconcile compatibility between old/new app, schema, RPCs, Edge Function and legal-consent enforcement, using backward-compatible expand/contract steps where appropriate;
3. prove backup and restore on a safe target, and define partial-deployment recovery;
4. run the approved non-destructive preflight and exact-candidate staging release gate;
5. collect accountable-owner approval, then run postflight and verify live smoke, registration/consent, account status, isolation, save/reload and export behavior;
6. record the exact deployed SHA and a reviewed rollback plan.

The current production public smoke failure is a blocker to diagnose. Do not work around it by weakening smoke assertions or deploying the code without parity review.

## 10. Final gate status

| Launch gate | Decision |
|---|---|
| Exact current main source/CI | PARTIAL — hosted smoke failure |
| Authenticated staging | NOT RUN / SKIPPED |
| Branch protection | FAIL |
| 100 operational tools | FAIL — zero verified in matrix |
| Paid pilot tool subset independently validated | NOT ESTABLISHED |
| Tenant isolation/persistence/export for exact final candidate | NOT ESTABLISHED |
| Production parity and rollback | FAIL / BLOCKED |
| Operator identity/registration and Saudi counsel | BLOCKED |
| PDPL provider map/transfer/retention/deletion | BLOCKED |
| IP/SBOM/license/brand review | INCOMPLETE |
| Billing/tax/invoice/refund/support | NOT READY |

**Final decision: NO-GO.** Reassess only after the exact limited pilot scope passes calculation/reference, authorization, persistence, export and authenticated staging acceptance and its applicable legal, privacy, provider, payment, support and recovery gates have closed.

## Live deployment evidence added 26 October 2026

A read-only Supabase management/API inspection verified that the production database project is `gcsamrdaeraxieaagsta` and staging is `hfhrosthswcybccepmak`; both report region `eu-central-1`. This is only the database region, not a full vendor/data-transfer assessment.

Production reports 14 migrations and ends at `20261019140600_atomic_subscription_request_decisions`. Staging reports 17 migrations and additionally includes legal/referral and consent-policy records (`20261021130000_shoir_beta_legal_referrals`, `20261022110000_enforce_beta_legal_acceptance`, and applied version `20261025164602` named `20261023130000_refresh_refund_policy_acceptance_version`). Schema/policy parity remains **FAIL / BLOCKED** until the version/name discrepancy is reconciled and a reviewed rollout is approved.

Both `shoir-persistence` Edge Functions report ACTIVE version 8 and `verify_jwt=false`, but deployed source SHA-256 differs: production `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`; staging `b25d2c22d33baa4daef2b63d27375dcdfac57bb58cfc5e577882882436a0d0d0`. The production deployed `index.ts` returned by the management API lacks referral-handling code present in staging and current repository source. The app's exact Streamlit deployment branch/entry point and config cannot be verified from the available connection. **Do not hot-deploy**; reconcile app/schema/Edge as one bundle with backup, restore proof, authorized change window, postflight and rollback.

Read-only grant/policy queries found staging `public.shoir_referrals` has RLS enabled, no row policy and no direct table grants to `anon` or `authenticated`; grants are shown for `postgres` and `service_role`. This may be correct for a server-only table, but only if every caller uses reviewed, authenticated server logic. `shoir_accounts` and `shoir_workspace_states` have deny-all RLS policies for `anon`/`authenticated` and no direct grants to those roles. These metadata checks do not prove complete endpoint, object-ownership, entitlement, session-expiry, or tenant-isolation security.

A fresh read of the current CI records confirms the public main smoke still fails on the recorded main SHA, staging's unauthenticated smoke is skipped, and the staging authenticated release-gate job is skipped. Skipped checks remain **NOT RUN**. The live parity evidence and required actions are detailed in [PR Integration Audit](PR_INTEGRATION_AUDIT.md).

No production migration, Edge Function deployment, Streamlit deployment, account operation, or billing operation was performed. Decision remains **NO-GO**.



## Current baseline recheck — 26 October 2026

This recheck supersedes older SHA/count claims elsewhere in the historical capture.

- Current `main`: `267be8889c310d90141c047d8aadd42c942423fb`.
- Exact-main automated checks: validation [40291784799](https://github.com/MSJ1708/shoir-ie/actions/runs/40291784799), engine regression [40291784823](https://github.com/MSJ1708/shoir-ie/actions/runs/40291784823), and security/quality [40291784836](https://github.com/MSJ1708/shoir-ie/actions/runs/40291784836) passed.
- The merged PR #193 commit had a failed hosted desktop/mobile smoke in [40290645125](https://github.com/MSJ1708/shoir-ie/actions/runs/40290645125). The current main automated validation run is not proof that the deployed hosted app is aligned.
- Staging validation passed at `8b36e3737705867019b9cf29e603cfc37e7911e6`, but authenticated release gate [40273588637](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588637) was skipped.
- Current matrix: 100 rows = 98 `IMPLEMENTED_NEEDS_VALIDATION`, 2 `EXTERNAL_CONFIGURATION_REQUIRED`, and 0 `VERIFIED_WORKING`.
- T096 draft implementation is in [PR #195](https://github.com/MSJ1708/shoir-ie/pull/195); no real staging endpoint/result has been verified. T098 has no verified enterprise OIDC flow, provider-backed MFA evidence or durable audit persistence evidence.
- Branch protection could not be read by the active integration (403). An authorized repository administrator must inspect the actual saved rules.
- The root [Commercial Launch Checklist](../COMMERCIAL_LAUNCH_CHECKLIST.md) is the gate-by-gate source of truth.

Decision remains **NO-GO**. Do not remove the public BETA label or activate paid general availability.
