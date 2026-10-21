# Shoir-IE Legal and Launch-Risk Register

**Review date:** October 21, 2026  
**Review type:** Targeted repository/source review of public legal notices, registration, referral claims and selected persistence code.  
**Overall status:** **NOT LEGALLY CLEARED FOR COMMERCIAL PRODUCTION.** This document is not legal advice, a compliance certificate, a full security assessment or a formula-by-formula engineering audit. A Saudi-qualified lawyer and appropriately skilled technical reviewers should confirm unresolved items.

## Beta terms and user notices

Current branch drafts are versioned in:
- [Terms and Conditions](TERMS_AND_CONDITIONS.md) — version 2026-10-21-beta-v1
- [Privacy Policy](PRIVACY_POLICY.md) — version 2026-10-21-v1
- [Refund Policy](REFUND_POLICY.md) — version 2026-10-21-v1
- [Cookie Policy](COOKIE_POLICY.md) — version 2026-10-21-v1

The public app displays a beta warning; the terms explain that calculations, AI responses, simulations, reports, integrations and stored work may be incomplete or wrong; the output disclaimers require independent verification; and the limitation-of-liability wording expressly preserves legal rights that cannot be excluded. The current referral copy no longer promises a 15% discount or displays invented referral counts. Rewards are inactive unless separate program rules are published.

**Important:** these changes are on branch legal-beta-referral-readiness-2026-10-21. They do not change the live website until reviewed, merged and correctly deployed. User-facing notices must remain consistent with the code and actual deployment.

## Findings and required actions

| Priority | Finding | Status and required evidence to close |
|---|---|---|
| **P0** | Public operator identity is incomplete in the in-app terms/privacy notice. The operating legal name, official address and applicable commercial registration details have not been confirmed in the repository. | **Open.** Confirm the actual operator/entity, business registration and contact/address details; publish the required details before a paid commercial launch. Do not invent legal-entity details. |
| **P0** | The production Supabase Edge Function/schema may not match the source and migrations in the repository. The repository's docs/RELEASE_READINESS_REPORT_2026-10-19.md records production migration/function drift and missing registration/atomic-decision database functions at the time of that report. | **Open / release blocker.** Review and reconcile current production migration history, deployed Edge Function version and schema before deployment. Apply only a reviewed, environment-matched migration/function bundle, then complete registration, acceptance, approval, decline, renewal and workspace-isolation E2E tests on staging. Never deploy this branch blindly to production. |
| **P0** | Consent/version recording and referral attribution require the new SQL migration and matching Edge Function code. | **Implemented in this branch, deployment not verified.** Run CI/static tests; apply migration and Edge source to staging together; verify that an unauthorised user cannot read referral counts, new registration cannot bypass current acceptance, invalid/self-referral codes are rejected, and referral states change only on admin decisions. |
| **P0** | The current platform contains industrial calculations, optimization, simulations, ML predictions, AI Copilot outputs and potential cost/savings examples. This review did not independently validate every formula, unit, algorithm, module, solver status or report. | **Open.** Require module-level reference calculations, unit/boundary tests, invalid-input tests, solver-status checks, regression fixtures, review by a qualified industrial engineer, provenance labels, and validated-versus-simulated UI states. Do not claim verified savings without recorded baseline, post-change measurements and evidence. |
| **P0** | Privacy disclosures must reflect actual data handling, including the configured cloud, account/storage, email and AI providers. The previous notice made absolute claims about no third-party sharing and a simple retention process that were not safe to promise. | **Draft updated in branch; factual deployment inventory open.** Verify enabled providers, regions, data types, logs, backups, telemetry, AI prompts, subprocessors, access permissions, contracts and cross-border transfer safeguards. Align the policy with the actual configuration. |
| **P0** | End-to-end retention/deletion periods and data-subject request handling have not been evidenced for every database, backup, cache, local file, log and third-party provider. | **Open.** Create a personal-data inventory and retention schedule; specify deletion method and exceptions; implement and test requests for access, correction, readable copy and destruction; define incident/breach handling and responsible contact. |
| **P1** | Third-party code and asset copyright/licence status has not been fully inventoried. The proprietary LICENSE is not a substitute for package and asset licences. | **Open.** Complete [Third-Party Licence Review](THIRD_PARTY_LICENSE_REVIEW.md), generate an SBOM, scan transitive dependencies and JavaScript/TypeScript imports, and record provenance/permissions for all images, fonts, icons, datasets, sample content and marketing assets. |
| **P1** | The platform name/logo has not been shown as cleared by a trademark search. | **Open.** Search relevant Saudi and international registers for similar marks; document ownership and brand permission. Ask Saudi counsel whether/how to apply for applicable trademark protection. |
| **P1** | Subscription prices, currency, billing period, tier contents, payment approval, refund handling, taxes and any required e-commerce disclosures must be accurate for the operator and target markets. | **Open.** Ensure displayed price, currency, term, renewal/expiry, refund/cancellation approach, provider details, complaint route and tax treatment are accurate before payment; test every purchase/approval/refund support path. Keep STC Pay QR/manual review unless a future payment-system change is expressly approved. |
| **P1** | Tax registration and invoicing status is not known from this repository review. | **Open.** Ask a Saudi tax adviser to assess the operator's facts, taxable supplies, customer location and cross-border position. ZATCA says mandatory VAT registration generally applies to resident taxable persons whose taxable supplies exceed SAR 375,000 in relevant 12-month tests, with separate rules and exceptions; do not treat gross app subscription receipts as the only test. |
| **P1** | A disclaimer cannot lawfully eliminate all liability or statutory consumer rights. | **Mitigated in draft, legal review open.** Obtain Saudi-law review of enforceability, consumer/business user differences, warranty exclusions, liability caps, complaint process, refund rules and governing-law clause. |
| **P1** | Referral attribution is not the same as a reward programme, and abusive or unsolicited referral marketing can create separate risks. | **Draft implementation only.** Keep rewards inactive until separate terms specify eligibility, qualification, caps, expiry, reversals, tax, abuse and marketing rules. Verify consent and data-minimisation for referrals before production. |
| **P1** | Repository history, contributor/contractor rights and any third-party code copied into the project have not been forensically reviewed. | **Open.** Verify assignments/permissions and scan history for incompatible copied material and exposed secrets. Rotate any secret that may have been committed, including historical secrets. |
| **P2** | The beta has not been independently security-certified or penetration-tested, and successful source tests alone do not prove tenant isolation or hosted behaviour. | **Open.** Complete authenticated browser E2E, cross-account isolation, access-control, upload/export, dependency, secrets and incident-response checks; commission an independent security review before handling live industrial/confidential data. |

## Suggested pre-commercial release gate

1. Legal owner, registered operator details, prices/currency/tax, terms, privacy, refund and complaint channels reviewed by Saudi counsel/adviser.
2. PDPL data inventory, processing basis, provider locations, contract/transfer review, retention schedule and data-request workflow verified.
3. Current Edge Function and database migrations reconciled against production; staging E2E and CI pass for all registration and account paths.
4. Formula/model validation and evidence provenance completed for marketed modules; all example data and savings claims labeled and supported.
5. SBOM, dependency licence scan, asset provenance and trademark search completed.
6. Only then consider paid commercial release; retain dated evidence and rollback/recovery plan.

## Official reference points

- [SDAIA: PDPL Article 4 — information to data subjects before/when personal data is collected](https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPL2/%21ut/p/z0/04_Sj9CPykssy0xPLMnMz0vMAfIjo8ziPR1dzTwMgw2MDMOcTA3MjH39TE29jY0MQsz1g1Pz9L30o_ArAppiVOTr7JuuH1WQWJKhm5mXlq8fEeAS4GOkX5DtHg4A45XaIQ%21%21/).
- [SDAIA: data-subject rights](https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPL/%21ut/p/z0/04_Sj9CPykssy0xPLMnMz0vMAfIjo8ziPR1dzTwMgw2MDMOcTA3MjH39TE29jY0MQsz1g1Pz9L30o_ArAppiVOTr7JuuH1WQWJKhm5mXlq8fEeAS4KNfkO0eDgDZXeBe/).
- [SDAIA: rules for transfers of personal data outside Saudi Arabia](https://sdaia.gov.sa/ar/SDAIA/about/Documents/General%20Rules%20for%20the%20Transfer%20of%20Personal%20Data%20outside%20the%20Geographical%20Borders%20of%20the%20Kingdom.pdf).
- [SAIP: copyright registration for computer software and applications](https://www.saip.gov.sa/en/services/copyrights/copyr1).
- [ZATCA: VAT registration for individuals](https://zatca.gov.sa/en/eServices/Pages/eServices-002.aspx).

This register records implementation tasks and risk areas. It does not assert that Shoir-IE is compliant with each cited law or that a legal claim is impossible.
