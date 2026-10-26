# Legal, privacy and commercial readiness checklist — 26 October 2026

**Scope:** Engineering preparation and issue spotting only. This is not legal, tax, accounting or regulatory advice, and it is not a legal certification. No professional approval is claimed.

## Known facts and unresolved details

The two Supabase projects are located in eu-central-1. The legal entity that will sell the service, registration details, business address, VAT status, contracting identity, privacy contact, payment provider, customer mix, revenue/supply facts, retention policy, subprocessors and data-flow inventory were not established by this audit. Do not invent them. Staging contains newer legal/referral acceptance schema than production. Existing users must not be backdated or silently recorded as accepting new terms. Related pull requests and policy text are drafts, not approval.

## Current official reference points

- SDAIA PDPL knowledge center / controller and processor guidance: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPLCP/
- SDAIA Personal Data Transfer Regulation: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPL2/
- SDAIA PDPL knowledge center: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/
- ZATCA VAT rules: https://zatca.gov.sa/en/RulesRegulations/Taxes/Pages/VAT.aspx
- ZATCA e-invoicing updates: https://zatca.gov.sa/en/MediaCenter/News/Pages/Wave25-E-invoicing.aspx

Official SDAIA guidance addresses processing of personal data relating to individuals in the Kingdom and a regulatory framework for relevant transfers outside the Kingdom. Counsel must map the actual data, purpose, entities, recipients, legal basis, transfer mechanism, safeguards and risk assessment. Hosting in a specific region alone does not decide compliance. Tax/invoicing applicability similarly depends on actual entity, taxable supplies, customer locations and current ZATCA rules/waves.

## Required reviews

| Area | Required decision/evidence | Accountable owner |
|---|---|---|
| Contracting identity | Legal entity, jurisdiction, registration, address, authorized signatory and seller of record | Business owner + Saudi counsel |
| Beta/terms of service | Scope, acceptable use, support, suspension/termination and liability language reviewed | Saudi counsel + product |
| Industrial calculation disclaimer | Outputs are decision support; validate input quality, units, assumptions, standards and site safety before operational use | Engineering + counsel |
| Privacy notice | Data categories, purposes/legal basis, retention, rights, disclosures, privacy contact and security | Privacy owner + counsel |
| Controller/processor | Determine roles of operator, customer and providers; processor terms where applicable | Counsel + business owner |
| Cross-border data | Data-flow map, recipient/subprocessor, transfer condition, safeguards, minimization and risk assessment | Counsel + security |
| Customer industrial data | Confidentiality, data ownership/use restrictions, encryption, least privilege, isolation, export/deletion and retention | Security + engineering |
| Incident response | Named owner, triage, evidence preservation and legally applicable notification duties | Security/ops + counsel |
| Cookies/analytics | Determine actual services and applicable notice/consent requirements | Counsel + product |
| Copyright/IP/open-source | Ownership/assignment, third-party assets, license/attribution inventory | Business owner + counsel |
| Refund/cancellation/renewal | Eligibility, process, timing, access revocation and dispute route match actual implementation | Counsel + payment owner |
| Referrals | Eligibility, attribution, reward triggers, expiry, self-referral/abuse rules, disclosures and tax/accounting | Counsel + commercial |
| Payment/invoicing | Provider eligibility, server verification, signature and idempotency, receipts/invoices, refund/reversal handling | Payment owner + accountant |
| VAT/e-invoicing | Applicability and phase/requirements based on legal entity, taxable status/supplies and current rules | Qualified Saudi tax/accounting professional |
| Enterprise contracts | Confidentiality, support levels, availability promises, responsibilities, exit/data export | Counsel + sales |
| Marketing/case studies | Permission and substantiation; distinguish synthetic demonstrations from real customer outcomes | Business owner + counsel |
| Agreement acceptance | Version ID, affirmative action, timestamp, account association, server enforcement and appropriate audit | Engineering + counsel |
| Support contact | Verified customer support and escalation route | Operations |

Engineering can prepare versioned agreement content, server-side acceptance enforcement, audit evidence, data export/deletion and subscription state transitions. It must not fabricate consent or pre-accept revised documents for existing accounts.

## Commercial controls to prove before paid access

- Plan names, prices, renewal/expiry, entitlements and revocation match the implemented backend.
- Checkout/payment is not advertised as operational unless provider-backed server verification, signatures/idempotency, error recovery, refund and cancellation tests pass.
- Refund policy and acceptance version match the deployed function/schema.
- Referral attribution/rewards and anti-abuse controls have documented approved rules and actual tests.
- Support, escalation and incident response are staffed and discoverable.
- Marketing, testimonials, ROI and savings claims are substantiated and clearly distinguish modeled forecasts from actual measured outcomes.
- Legal identity, privacy contact and tax/accounting decisions are documented before launch.

**Status:** legal/privacy/commercial gate BLOCKED until responsible business ownership, qualified review, PDPL/data-transfer assessment, tax/payment determination and matching engineering evidence are complete. BETA remains enabled.