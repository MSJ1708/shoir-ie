> **DRAFT FOR QUALIFIED SAUDI COUNSEL / PRIVACY REVIEW — NOT FOR CUSTOMER USE OR PUBLICATION.**

> **Review status update — 27 October 2026:** This remains an unapproved working draft. Do not publish, activate paid access, represent compliance, or rely on it as legal advice. The accountable operator must supply the true legal identity/address/registration, actual prices and tax treatment, support contact, data flows/retention/hosting/transfer facts, and working refund/cancellation process. Qualified Saudi counsel and a privacy reviewer must approve the text against actual deployed behavior before customer use. The successful staging gate is not legal clearance.

>
> Copied from open draft PR #170 for review preparation. This is not legal advice or a compliance finding. The actual operator identity, official address and registration, service provider/hosting regions, purposes/legal bases, data flows, support contact, pricing, billing/refund operations and applicable obligations must be verified by the accountable owner and qualified professionals. Do not publish until facts are confirmed, counsel approves, and the deployed product behavior matches this document.

# Shoir-IE Pre-Commercial Launch Checklist

**Release decision: HOLD — not cleared for paid commercial production.**

This checklist turns the open risks into items that can be closed with named owners and evidence. The staging app and authenticated release gate are technically verified, but that does not clear the production deployment or establish compliance under Saudi law.

## Gate 1 — Identify the operator and publish accurate commercial details

Owner: founder/operator, with Saudi counsel.

- [ ] Confirm whether the provider is an individual or a registered legal entity. Record the exact legal name, official business address, and commercial-registration or other public-register details where applicable. Do not make these up.
- [ ] Confirm the customer-support and complaints contact route and ensure someone actually monitors it.
- [ ] Confirm whether the advertised plans are priced in USD or SAR, the total payable price, applicable VAT/taxes/fees, subscription period, activation date/length, expiry/renewal rules, and cancellation/refund process.
- [ ] Make the website, registration UI, payment instructions, invoice/receipt, Terms and Refund Policy agree. Keep STC Pay QR/manual verification; do not imply card checkout or automatic activation.
- [ ] Obtain legal review of e-commerce disclosures and advertising claims. The Saudi E-Commerce Law addresses provider identity/address/contact, registration information, service characteristics, total price including charges/taxes, payment arrangements and itemized invoices. See the official English translation: https://misa.gov.sa/app/uploads/2025/07/E-Commerce-Law.pdf

**Evidence to close:** approved identity details, approved price/term matrix, screenshots of the storefront/payment steps, and a dated Saudi-law review memo.

## Gate 2 — Finish the Saudi PDPL data inventory and operating procedures

Owner: data controller/operator and technical maintainer; Saudi privacy counsel to confirm legal basis and required controls.

- [ ] List every personal-data category and source: account usernames/email, password hashes and pending registration metadata, payment references/receipts, support emails, sessions/audit/security logs, referrals, workspace uploads/exports, AI prompts/context, telemetry, backups and caches.
- [ ] For each category, record purpose, lawful basis, minimum necessary fields, access roles, recipients/processors, storage region, retention period, deletion method, and the system owner. Do not assume consent is always the correct lawful basis; document the basis purpose by purpose.
- [ ] Confirm all live providers and configuration (Streamlit, Supabase, email, AI/Copilot and analytics, if enabled), their contracts/subprocessors, hosting locations, access controls, logs/backups, and whether data may be accessed or transferred outside Saudi Arabia.
- [ ] Have counsel verify any required transfer safeguards and whether a privacy impact assessment, data protection officer/contact, processing-activity record, or additional notice is required for the actual use case.
- [ ] Implement and test requests for access, readable copy, correction/update, destruction where legally available, and consent withdrawal where relevant. Set realistic response ownership and deadlines.
- [ ] Set and test retention/deletion rules for primary records, uploaded payment proofs, local caches, logs, support records and backups. Define incident escalation and assess whether/when notifications are required.
- [ ] Obtain explicit approval before accepting sensitive personal, confidential, regulated or live industrial data. Until then, keep beta use to synthetic or non-sensitive test data.

The official SDAIA guidance describes the Saudi PDPL framework, lawful basis and data-subject rights; separate rules apply to transfers outside the Kingdom. Start with https://sdaia.gov.sa/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx and https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPLCP/

**Evidence to close:** approved data map, provider/region matrix, transfer assessment and safeguards, retention schedule, request-handling test, incident playbook, and counsel approval.

## Gate 3 — Prove the marketed calculation features

Owner: independent industrial-engineering reviewer and software maintainer.

- [ ] Create a formula inventory for every marketed module: inputs, outputs, units, formula/source, assumptions, validity range, solver/model version and known limitations.
- [ ] For each supported calculation, add reference-result tests from an independent source; boundary/extreme tests; invalid/missing/zero input tests; dimensional/unit checks; rounding/tolerance checks; and regression fixtures.
- [ ] For optimization/simulation, test feasible, infeasible, unbounded, timeout and solver-error outcomes. Do not present a failed/unknown solver status as a valid optimum.
- [ ] Test spreadsheet import mapping, formulas, data types, time zones, duplicated rows, missing values, and export/round-trip integrity. Never silently imply imported data was validated when it was not.
- [ ] Label measured, user-provided, simulated, AI-generated and illustrative results separately. Ensure demos and sample plants are clearly fictional/synthetic.
- [ ] Remove any universal savings promise. A savings claim needs baseline, post-deployment measurement, implementation cost, dates, source evidence, and an accountable reviewer.
- [ ] Have a qualified reviewer sign off each marketed module before calling its calculations verified. Keep evidence, test version and review date in the release record.

**Evidence to close:** formula-to-test matrix, reference datasets, signed engineering review, solver regression report, and substantiated proof for each public ROI claim.

## Gate 4 — Clear copyright, dependencies, branding and ownership

Owner: software maintainer/founder; IP counsel if needed.

- [ ] Generate an SPDX or CycloneDX SBOM from the exact deployed build, including pinned direct and transitive dependencies, JavaScript/TypeScript imports and solver/runtime components.
- [ ] Review each package licence and required notices for the deployed use/distribution model. Retain the notices and scan report with the release.
- [ ] Create an asset register for fonts, icons, images, logos, sample files, datasets, charts, screenshots, marketing copy and copied snippets. Record owner, source, licence/permission and attribution obligations.
- [ ] Verify copyright assignments/permissions for all contributors and contractors; scan repository history for material copied without a licence and for exposed secrets that need rotation.
- [ ] Search relevant Saudi and international trademark registers for Shoir-IE and logo conflicts. Do not assume copyright or the repository LICENSE clears the trademark.
- [ ] Consider SAIP software/application copyright registration as a documentation step; it does not cure third-party infringement. See https://www.saip.gov.sa/en/services/copyrights/copyr1

**Evidence to close:** SBOM, machine-readable licence report, signed-off asset register, contributor/assignment records and documented name/logo search.

## Gate 5 — Verify production rollout and operations

Owner: platform maintainer and operator.

**Current status at 26 October 2026: OPEN — the current release candidate has not passed authenticated hosted acceptance or production parity.** The checkmarked items below are historical evidence from an earlier setup/test revision, not a PASS for the current `main` or release candidate.

- [x] **Historical staging schema evidence:** an earlier setup recorded the legal-version fields, server-only referral table and approval trigger. A fresh read-only comparison now confirms these legal/referral migrations are applied to staging, but not to production.
- [x] **Historical staging function evidence:** an earlier run recorded `shoir-persistence` version 8. Both current production and staging report version 8, but their deployed source SHA-256 hashes differ, so version-number equality is not source parity.
- [x] **Historical authenticated gate:** run [39861471413](https://github.com/MSJ1708/shoir-ie/actions/runs/39861471413) passed an earlier staging candidate. It does **not** verify the current candidate SHA. Current staging validation [40273588613](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588613) passed its test job but skipped hosted smoke; current authenticated release-gate run [40273588637](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588637) was **SKIPPED / NOT RUN**.
- [x] **Historical production transaction evidence:** earlier project records report the atomic registration/approval flow was tested with synthetic data. The current production migration inventory confirms `20261019140600_atomic_subscription_request_decisions` is applied, but the later legal/referral and refund-v2 migrations are absent from production's applied migration history. The historical test is not a substitute for current deployment parity or a new approved migration.
- [ ] **BLOCKED — release owner:** verify the actual Streamlit branch, commit, entry point, and configuration presence. The current hosted main smoke [40273481812](https://github.com/MSJ1708/shoir-ie/actions/runs/40273481812) fails at desktop/mobile hosted entry-screen rendering.
- [ ] Plan production rollout as a coordinated maintenance-window change: reviewed app SHA + missing database migrations + compatible Edge Function source. Do not roll out one component alone.
- [ ] Before any production deployment, snapshot/back up and prove recovery, record exact commit/migration/function hashes, rehearse rollback, and define handling for in-flight pending registrations.
- [ ] After authorized deployment, verify consent capture and stale-policy rejection, manual approval/decline, renewal, referral attribution, private receipt permissions, tenant isolation, and refund/complaint route using disposable accounts and synthetic fixtures only.
- [ ] Do not enable paid commercial access until technical, calculation-validation, operator/legal, privacy, tax/payment, support and recovery gates are independently closed.

## Sign-off record

| Gate | Reviewer / owner | Evidence link or location | Date | Status |
|---|---|---|---|---|
| Operator/commercial disclosures | To be assigned | Not yet provided | — | OPEN |
| PDPL/privacy and data transfers | To be assigned | Not yet provided | — | OPEN |
| Calculation verification | Qualified IE reviewer needed | Not yet provided | — | OPEN |
| Copyright/SBOM/branding | To be assigned | Not yet provided | — | OPEN |
| Production deployment | Platform maintainer | Staging evidence available; production rollout pending | — | OPEN |
| Saudi-law approval | Saudi-qualified lawyer | Not yet provided | — | OPEN |

## Important references

- Saudi E-Commerce Law (official English translation): https://misa.gov.sa/app/uploads/2025/07/E-Commerce-Law.pdf
- SDAIA legal/regulatory hub for PDPL and cross-border transfer rules: https://sdaia.gov.sa/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx
- SDAIA Guide to Saudi PDPL for controllers/processors: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPLCP/
- SAIP software/application copyright service: https://www.saip.gov.sa/en/services/copyrights/copyr1
- ZATCA VAT registration information: https://zatca.gov.sa/en/eServices/Pages/eServices-002.aspx

**This checklist is project guidance, not a legal opinion. Only a qualified reviewer can close the Saudi-law sign-off; only the operator can confirm its identity, registrations, actual providers and commercial choices.**