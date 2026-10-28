# Shoir-IE — PDPL Provider/Data Map and Operator-Facts Register

**Prepared:** 27 October 2026  
**Purpose:** Give the operator, privacy professional, and Saudi-qualified counsel a fact-based starting point for the PDPL and cross-border-transfer review.  
**Status:** **DRAFT — NOT A COMPLIANCE CERTIFICATE OR LEGAL OPINION.** Unknown provider settings and business facts are explicitly left open. Never treat a presumed provider, region, legal basis, retention period, approval, or contract as verified.

## 1. Executive result

The repository contains versioned Terms, Privacy, Refund, and Cookie notices. The current staging app/source and consent guard use the same policy identifiers: Terms `2026-10-21-beta-v1`, Privacy `2026-10-21-v1`, Refund `2026-10-23-v2`, Cookie `2026-10-21-v1`. This is evidence of identifier consistency only.

Live project metadata returned the following database facts:

| Environment | Supabase project ref | Database status / version | Project region reported |
|---|---|---|---|
| Production | `gcsamrdaeraxieaagsta` | ACTIVE_HEALTHY / PostgreSQL 17.6.1.166 | `eu-central-1` |
| Staging | `hfhrosthswcybccepmak` | ACTIVE_HEALTHY / PostgreSQL 17.11.0.003 | `eu-central-1` |

The project-region identifier is direct metadata. It does **not** establish the location of Streamlit hosting, object storage, logs, backups, support/email services, or AI processing. Because `eu-central-1` is not a Saudi region identifier, counsel and the operator must treat processing of Saudi data subjects' personal data in these database projects as a potential transfer outside the Kingdom and document the applicable legal assessment and safeguards before approving such processing.

**Important production mismatch:** production does not currently have the staging beta legal/referral schema (the six current legal-acceptance fields and `public.shoir_referrals` are absent), and production persistence Edge Function v8 has not been updated to the reviewed staging consent enforcement. Current staging policy IDs must not be read as proof that production enforces them. The migration and function rollout remains blocked pending reviewed, tested, explicitly approved deployment.

## 2. Inventory of data categories and purposes

This first-pass inventory is derived from the repository's published Privacy Policy and application/source structure. Engineering must reconcile each row against the current deployed build and all actual provider settings before sign-off.

| Data category | Examples presently described or implied by the source | Stated/intended purpose | Known system touchpoints | Open verification |
|---|---|---|---|---|
| Account identifiers and access | Username, email, salted password hash, account state, role/tier/expiry, session and recovery metadata | Registration, authentication, access control, recovery and support | Streamlit application; Supabase account/database functions; source also references local `enterprise_full_workspace.db` | Confirm exact source of truth, host filesystem persistence, cache lifetime, who can access each copy, and deletion/synchronization behavior |
| Industrial/workspace content | Uploaded spreadsheets, workbook tabs, process/asset/material/order/workforce/quality/maintenance data, scenario inputs/outputs, saved decisions and exports | User-requested engineering workflows, calculations, simulation, optimization, reports, collaboration and persistence | App upload/processing paths; Supabase workspace persistence; possible local database/cache; downloadable exports | Enumerate tables, object buckets, caches, temporary files, logs and backups; classify whether customers may submit employee or other personal data and confidential industrial data |
| Subscription and payment review | Selected plan, payment status, transaction/reference number and optional payment evidence, as stated in the Privacy Policy | Manual payment verification, entitlements, dispute and support handling | App subscription flow; database persistence; displayed manual STC Pay QR/payment instructions | Confirm exactly what is stored, whether any receipt/image is uploaded, storage location/access/retention, real payment-account owner, provider terms, refunds and reconciliation controls |
| Referral attribution | Submitted referral code/status and account association | Attribution and abuse prevention | Application/database referral logic; staging-only referrals table until reviewed production rollout | Confirm complete fields and access rules after migration, retention and whether any reward is ever offered; current Terms say no reward is currently offered or guaranteed |
| Security, audit and operational telemetry | Session, audit, support, error diagnostics, login throttling, operational logs | Secure operation, investigation, service support and compliance | Application, Supabase functions/database, hosting and CI logs | Inventory payload fields, log destinations, administrative access, retention/rotation, redaction and whether personal data appears in job artifacts |
| AI/Copilot content | Prompt and relevant context when AI is enabled and the user requests it | Produce requested AI-assisted explanations or suggestions | Privacy notice describes Anthropic when AI Copilot is used; actual deployed secret/config, provider account, endpoint, region and retention settings were not confirmed in this check | Confirm whether enabled per environment; list data sent, provider/subprocessors, region, contractual terms, retention/training controls and user notice/consent requirements |
| Email/support communications | Account recovery, service messages, support and privacy requests | Account lifecycle, notices, support and user-rights handling | Email provider is described as configured per deployment; actual provider and account were not verified | Name the provider, region/subprocessors, DPA/contract, sender identity, support mailbox owner, access and retention |
| CI/release evidence | Build/test output, code metadata, synthetic test artifact and security SBOM artifacts if generation succeeds | Engineering assurance, traceability and release evidence | GitHub repository/Actions and artifacts | Verify workflow permissions, artifact retention, log redaction, repository access, SBOM job result, and whether any artifact ever contains non-synthetic data |

### Collection minimization and prohibited test data

The existing beta notices direct users not to submit credentials from other services, card credentials, one-time codes, government identifiers, sensitive personal data, confidential trade secrets, export-controlled material, or another person's information without authorization and approved deployment. Keep this as a beta safeguard, but do not treat it as a substitute for assessing the lawfulness and protection of any data the operator actually processes.

Use synthetic data for testing and release acceptance. Do not use real customer records or the reserved administrator to demonstrate tenant isolation, persistence, entitlement, or deletion behavior.

## 3. Provider and transfer register

| Provider / service | Evidence available today | Region/contract status | Required operator evidence |
|---|---|---|---|
| Streamlit-hosted application | Production and staging app URLs are documented in release records; both URLs were inaccessible through the browser tool used for this audit, so hosted runtime acceptance was not checked | Hosting region, subprocessors, logs, backups, contract/DPA and retention not verified | Export current hosting settings/terms and region, runtime version/commit, logs/backup region/retention, DPA/subprocessors and available tenant controls |
| Supabase database/functions | Live production and staging metadata checked; both database projects report `eu-central-1` | Region is known for the projects; object storage/backups, service access, subprocessors, DPA, retention and support-access location need confirmation | Provider contract/DPA, actual storage/bucket region, backup/PITR region and retention, access list, deletion semantics and subprocessors |
| Anthropic / AI provider | Named in Privacy Policy as a provider when Copilot is used | Whether AI is enabled in the deployed app, account/entity, endpoint, region, DPA and retention/training settings not verified | Export non-secret configuration metadata and provider terms/DPA/region; verify the exact request payload; disable AI for non-approved data until signed off |
| Email provider | Privacy Policy says the provider is configured per deployment | Name, region, data sent, retention and contract not verified | Name the provider and sending account, provider terms/DPA, region, logs, retention and data fields |
| STC Pay / manual payment route | Policy states payment is via a separate displayed STC Pay QR/manual review rather than integrated card checkout | Actual merchant/account owner, transaction details stored, account eligibility, provider terms and region not verified | Confirm merchant identity, transaction reconciliation, receipt/invoice and refund workflow, customer-visible terms and applicable tax obligations |
| GitHub / Actions | Repository and CI artifacts are used for code and release evidence | Access roster, artifact retention and enterprise terms not audited | Verify repository team access, workflow token permissions, secret access boundaries, artifact retention, log redaction and SBOM output retention |

Do not write credentials, API keys, tokens, private connection strings or customer identifiers into this register. Record the names of settings/secrets only, their owner and whether configured, never the values.

## 4. Processing-purpose and lawful-basis record

The current Privacy Policy explicitly says the basis depends on the purpose and has not yet been documented for each specific operation. The operator must complete the following register with counsel; do not assume consent is automatically the correct basis for every processing activity.

| Processing purpose | Candidate basis to be assessed by counsel | Required determination/evidence |
|---|---|---|
| Create and operate an account / authenticate a requested user | Service/contract necessity or other lawful basis, as applicable | Identify controller, account fields, retention, service necessity, user notice and access controls |
| Deliver requested analysis, simulations, workbooks, reports and saved workspaces | Service/contract necessity or other lawful basis, as applicable | Data flow by feature, data minimization, storage duration, local cache/temp file behavior and customer instructions |
| Manual subscription/payment review and refunds | Contract and/or legal obligation, as applicable | Exact data collected, merchant identity, transaction records, retention and tax/accounting requirements |
| Security, anti-abuse, audit and incident investigation | Legitimate or other legally available basis as determined by counsel | Log field inventory, balancing/necessity assessment where relevant, retention and role-based access |
| Referral attribution | Contract/legitimate interest/consent or other basis as counsel determines; no assumed reward | Confirm purpose and eligibility, user disclosure, minimal attribution fields, anti-abuse controls and retention |
| Support, complaint and privacy requests | Requested service and/or legal obligation, as applicable | Verification procedure, contact ownership, case record access, response tracking and retention |
| AI Copilot request processing | Depends on the user's requested feature, the applicable provider relationship and transfer assessment | Confirm active provider and payload; determine notice/choice, lawful basis, minimization, provider terms and transfer safeguards |

The Saudi PDPL framework includes requirements around purpose specification and documentation, minimizing data, not retaining personal data longer than needed (subject to applicable exceptions), accuracy, security, accountability and individual rights. Use the official SDAIA controller/processor guidance and the law/regulations themselves for counsel's analysis rather than treating this table as a concluded legal basis.

## 5. Required operating procedures

### Individual requests

The published Privacy Policy directs access, readable-copy, correction/updating and destruction requests to `shoirtheagent@gmail.com` and says identity may need to be verified. Before launch, a named owner must prove that mailbox is controlled and monitored, and rehearse the entire workflow across:
1. request intake and identity verification;
2. locating records in application/database, object storage, workspace states, support/email, logs, AI/provider systems and backups;
3. access/export, correction or deletion where required and legally permitted;
4. documenting exceptions, completion and response;
5. confirming that caches, replicas and scheduled backups follow the approved retention/deletion rule.

The source notice does not promise a single automatic deletion schedule for every database, backup, cache, log and provider. The operator must decide and publish actual retention periods only after mapping the relevant systems; do not invent durations.

### Security incident and personal-data breach

Assign an accountable incident lead and privacy/legal escalation contact. The official SDAIA Implementing Regulation, Article 24, describes notification to the competent authority within **72 hours of awareness** for a personal-data breach that may harm the data or subject or conflict with their rights/interests, and notification to affected subjects without undue delay where applicable. The exact threshold, required content, any additional sector rules and operational steps must be confirmed by counsel for the actual incident and business.

Required preparation:
- on-call/incident owner and escalation channel;
- timestamped detection, containment, evidence preservation and risk assessment;
- list of potentially affected categories/subjects and affected systems;
- legally reviewed notification templates and evidence capture;
- ability to notify competent authority/affected subjects within the applicable timeframes;
- recovery and corrective-action record, with credentials/secrets excluded from public logs.

### Retention and disposal

Create an approved retention schedule by record class (account, authentication/security logs, workspaces/uploads, exports/temp files, payment/transaction records, referrals, support, AI logs, backups, CI artifacts). For each class record: purpose, system, region, retention period, deletion trigger, exceptions/legal hold, deletion owner and verification method. Implement only after the operator and counsel confirm the periods and any legal retention requirements.

### Cross-border assessment

For each external provider, document:
- controller/processor/subprocessor roles and contractual obligations;
- data categories, purpose, volume, data-subject geography and storage/processing region;
- whether transfer/disclosure outside the Kingdom occurs, and the appropriate legal route and safeguards;
- minimization and why each transferred category is necessary;
- risk assessment where required by the applicable transfer rules;
- contract clauses, transfer safeguards, onward transfers, deletion and breach assistance;
- risk mitigation and the decision/approval by the responsible privacy professional and counsel.

Do not describe the system as PDPL-compliant until this analysis and all applicable steps are completed and evidenced.

## 6. Official sources for qualified review

Use the current version of the official materials, and confirm the law, regulations, guidance and effective amendments at the time of launch:

- SDAIA, **Guide to the Saudi Personal Data Protection Law for Controllers and Processors**: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPLCP/
- SDAIA, **Implementing Regulation and Regulation on Personal Data Transfer outside the Kingdom**: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPL2
- SDAIA, **Regulation on Personal Data Transfer Outside the Kingdom**: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/RegulationonPersonalDataTransferOutsidetheKingdom
- SDAIA, **Personal Data Breach Notification service**: https://dgp.sdaia.gov.sa/wps/portal/pdp/services/personaldatabreachnotification
- SDAIA, **Standard Contractual Clauses for Personal Data Transfer**: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/StandardContractualClauses
- Saudi Authority for Intellectual Property, software/application copyright registration information: https://www.saip.gov.sa/en/services/copyrights/copyr1
- Saudi E-Commerce Law (official English translation link currently recorded by this repository): https://misa.gov.sa/app/uploads/2025/07/E-Commerce-Law.pdf
- ZATCA VAT registration information: https://zatca.gov.sa/en/eServices/Pages/eServices-002.aspx

The SDAIA controller/processor guidance is guidance rather than a substitute for the binding law and regulations. A qualified Saudi legal/privacy reviewer should confirm applicability and the current official versions.

## 7. Explicit open items — require real operator or professional input

| Open item | Why automation cannot close it | Evidence required |
|---|---|---|
| Legal operator/controller identity, address, registration and actual contracting party | Not reliably discoverable from source code or assumed from a contact mailbox | Exact legal name, CR/registration details where applicable, official address, authorized representative and approval to publish |
| Provider/processing map | Some provider settings, contracts, storage regions and subprocessors are external to accessible source metadata | Provider dashboard exports/settings, terms/DPA, regions, subprocessors and retention information |
| Lawful basis, privacy notice and transfer safeguards | Requires factual purpose mapping and qualified legal judgment | Signed processing-purpose/legal-basis matrix, data-transfer assessment and applicable contract/safeguard decision |
| Retention and rights-request operations | Actual periods, legal holds, and staffing/ownership are business/legal decisions | Approved schedule, owner, completed request simulation and deletion evidence |
| Breach response ownership | Requires named and reachable humans and a staffed escalation route | Named incident lead, privacy contact, on-call schedule, rehearsed tabletop and legally reviewed templates |
| Paid terms, manual payments, invoices/tax, refunds and referral rules | Merchant identity, prices, tax status and commercial choices are external facts | Approved terms and price matrix, actual provider/merchant confirmation, refund/cancellation workflow, tax/accounting opinion |
| Production legal-consent enforcement | Current production schema/function are behind staging and rollout is approval-gated | Independent review, safe forward migration/restore rehearsal, authorized coordinated deployment, exact-SHA postflight evidence |
| Final PDPL/legal sign-off | Only a qualified reviewer can approve legal conclusions | Dated written sign-off against the exact deployed system and actual operator/provider facts |

**Current decision:** legal/privacy and commercial gates remain **BLOCKED**. This register reduces discovery work, but does not close these gates or authorize sensitive-data processing or paid access.
