# Shoir-IE — Saudi privacy, commercial and legal launch readiness

**Assessment date:** 2026-11-21  
**Status:** **NOT LEGALLY CLEARED — keep BETA and do not start paid customer marketing or production onboarding until the operator-specific legal, privacy, tax and service terms have been reviewed.**  
**Purpose:** evidence-led launch checklist for the owner and qualified Saudi legal/privacy/tax advisers. This document is not a legal opinion, regulatory filing, licence, certification or substitute for the controlling Arabic legal texts.

## 1. What this review establishes

Shoir-IE is a business software/service intended for use by organisations and individual users. Its deployment can involve account names, email addresses, authentication/session data, workspace activity, support requests, subscription records, uploaded workbooks and customer industrial datasets. Whether a particular dataset is personal data depends on whether a person can be identified directly or indirectly; pseudonymous data is still not automatically anonymous. The PDPL applies to covered processing in the Kingdom and can also apply to personal data of people residing in the Kingdom processed from outside it. SDAIA's controller/processor guide is explanatory guidance, not binding law.

The repository already contains Beta Terms, Privacy, Refund and Cookie notices and a technical privacy readiness document. Their presence is not proof that the actual operator, legal basis, processing map, cloud/data locations, processor contracts, deletion practice, rights handling, incident response or commercial refund treatment has been accepted.

The following is therefore an owner-controlled legal workstream, not something that code changes alone can close.

## 2. Establish the actual seller / service operator first

Before selling or advertising paid access, confirm with Saudi counsel and the Ministry of Commerce / Saudi Business Center which legal form and activity registration applies to the actual seller (sole establishment, company, or other permitted status). Do not publish guessed legal identity details or a personal address as a business address.

Record and verify:
- legal name and legal form of the contracting service provider;
- active Commercial Registration (where required), registration number, registered activities and business address;
- authorised signatory / operator and business contact details;
- official support, complaints, billing and cancellation contact channels;
- ownership/control of the Shoir-IE name, domain, code, logos and customer-facing materials;
- whether any regulated activity, professional licence, government/customer-sector approval or procurement registration applies to the chosen sales model.

The Commercial Register Law states that every merchant must register, subject to categories the Ministry may exempt under the Regulations. The official English translation notes that the Arabic text governs. The E-Commerce Law also requires a merchant to register its e-shop in the Commercial Register. Counsel must confirm how these provisions apply to the actual seller and whether any relevant exemption or separate service rule applies.

## 3. PDPL: required privacy programme

### 3.1 Determine controller and processor roles

Create a signed role map for each processing activity:
- Shoir-IE's own account, billing, support, security and product analytics;
- customer administrator/member accounts and workspace data;
- customer uploads, Excel workbooks, industrial datasets, decision records and exports;
- identity provider, hosting provider, database, email, analytics, payment and support providers;
- integrations to SAP/Oracle or customer-controlled systems.

For each flow, identify who determines the purpose and means, who acts only on documented customer instructions, which party is controller / processor / subprocessor, and the applicable contract. Do not assume Shoir-IE is always only a processor: its own user-account, billing and security purposes may be separate controller activities.

### 3.2 Keep a written Record of Processing Activities (RoPA)

For every relevant purpose, record at minimum: data-subject and personal-data categories, purpose, lawful basis, collection source, mandatory/optional fields, recipients/processors, hosting and transfer locations, retention periods, security controls, access roles, deletion method and the owner accountable for each flow. Keep it accurate and updated.

The Implementing Regulation requires controllers to maintain written, accurate processing records while processing continues and for five years after processing ends, with defined minimum content including purposes, data categories, data-subject categories, retention, recipients, transfers and security measures.

### 3.3 Privacy notice and lawful bases

Before collection, make a Saudi PDPL-compliant privacy notice available and provide the required information at or before collection. It must be tailored to the real service and explain the controller identity/contact, purposes, data categories, legal basis, collection method, retention, recipients/processors, any outside-Kingdom transfer, data-subject rights and the method for exercising them. State which fields are mandatory or optional and the consequence of not providing mandatory data. Do not use one blanket consent for unrelated purposes.

For each purpose, document a valid lawful basis under the Law. Do not assume consent is the only basis or that “legitimate interest” is generally available: SDAIA's guidance explains that the PDPL restricts use of the legitimate-interest basis. Where consent is used, make it specific, provable and withdrawable; provide a usable withdrawal channel. Sensitive data requires additional assessment and safeguards; explicit consent is required where consent is the chosen basis for sensitive-data processing, and sensitive data must not be processed for direct marketing.

### 3.4 Data-subject rights and service process

Create a monitored request channel and tested internal workflow for:
- information about collection and processing;
- access and a readable copy of the person's data;
- correction, completion and updating;
- destruction where the legal conditions apply;
- withdrawal of consent where consent is the basis.

Verify the requester, log each request, protect other people's data and confidential customer information, and record the decision. The Implementing Regulation generally requires a response within 30 days; an additional period of up to 30 days may be used only in the specified circumstances and with advance notice and reasons. The process must work across database records, uploaded objects, exports, caches, logs, email/support systems, subprocessors and backups, subject to lawful retention exceptions.

### 3.5 Security, breach response and impact assessments

Adopt an incident process with named 24/7 escalation owners, evidence preservation, containment, customer communications and regulator notification decision-making. Where the PDPL Implementing Regulation's threshold is met, the controller must notify the competent authority within 72 hours of becoming aware of the breach; it also provides for notifying affected data subjects without undue delay when the stated harm/rights threshold is met. Record the decision and supporting evidence even where a report is not required.

Perform and document a privacy impact assessment when required by the Implementing Regulation, including relevant sensitive-data, linked-dataset, large-scale/repetitive processing or other specified high-risk cases. Reassess after major changes to data, integrations, identity or hosting.

### 3.6 National Register and DPO applicability

Do not assume every small business has the same SDAIA registration/DPO requirement. Apply the current SDAIA Rules Governing the National Register to the actual controller: mandatory registration applies to specified categories, including a controller whose main activity is based on personal-data processing, a controller processing sensitive data, and certain individuals processing personal data beyond personal/family use. Confirm whether Shoir-IE's actual service activity and the operator's role meet a trigger; retain the registration certificate or written legal determination.

A DPO is required in the cases specified in Article 32 of the Implementing Regulation, including a controller whose primary activities require regular and systematic monitoring of data subjects or whose core activities are based on processing sensitive personal data, and certain public entities processing at large scale. Have counsel document the applicability assessment and appoint a qualified DPO where required.

## 4. Hosting and international data transfers

Prepare a current data-flow and subprocessor inventory showing the actual region/country for Streamlit hosting, Supabase database, Supabase Storage, Edge Functions, identity provider, email, analytics, payment and support. A provider's marketing statement or the location of its head office is not evidence of the location where each dataset and backup is processed.

For each transfer or remote access outside the Kingdom:
- identify personal-data categories, recipient, country, purpose and whether the recipient is a controller or processor;
- determine the applicable PDPL transfer condition and whether the transfer is necessary and limited to the minimum required;
- assess the destination's level of protection and the applicable transfer safeguards / approved mechanisms;
- execute appropriate processor / transfer agreements and verify onward-transfer and deletion terms;
- document the decision, risk assessment and monitoring.

Do not represent that data is stored only in Saudi Arabia unless the actual production plan, region, backups, logs, support access and subprocessors prove this. SDAIA's transfer regulation and guidance control this assessment. NCA Cloud Cybersecurity Controls (CCC-2:2024) were updated to reflect data-localisation changes; applicability depends on the actual entity/customer/sector and cloud role and must be assessed, not assumed.

## 5. E-Commerce, subscription and customer terms

The E-Commerce Law requires service-provider identity/contact information and, where applicable, commercial registration information to be disclosed in the e-shop. Before contract conclusion, provide clear contract terms and service characteristics, total price including charges and taxes, payment arrangements, and relevant warranty information; provide the required itemised invoice after contract conclusion. Electronic advertisements are part of the contract and must not contain false or misleading claims.

Have Saudi counsel classify Shoir-IE's SaaS/subscription offer and approve:
- Terms of Service / SaaS agreement and order/renewal process;
- precise subscription tiers, trial/Beta status, usage limits, taxes, billing date, renewal, cancellation and suspension terms;
- refunds, service failures, downtime, delivery/performance commitments and complaint escalation;
- customer acceptable-use / data ownership / confidentiality / IP rights;
- customer data processing agreement, security schedule and subprocessors list;
- SLA, support hours, incident notification, service credits and liability terms (as applicable);
- product feature, AI, prediction, live-integration, performance and savings/ROI claims.

Important classification point: the E-Commerce Law contains a seven-day cancellation provision with specified exceptions, including used software and online downloadable software, plus a separate delay/refund provision. It is not safe to assume the downloadable-software exception automatically covers a hosted SaaS subscription. Counsel must classify the actual product and contract and align the refund notice, payment workflow and in-app behavior. Never publish a broad “no refunds” statement without legal review.

## 6. Tax, billing and invoicing

Obtain tax advice for the operator's legal form, source of revenue and customer locations. ZATCA states that resident persons with taxable supplies above SAR 375,000 in the relevant 12-month test are generally subject to mandatory VAT registration, and voluntary registration may be available above SAR 187,500, subject to the applicable rules. Do not treat subscription revenue as exempt or decide registration solely from total cash receipts; the taxable-supply tests and non-resident cases need review. Confirm whether ZATCA e-invoicing requirements apply to the seller and how invoices, credit notes, tax IDs and retention will be handled.

## 7. Marketing and claims gate

Do not remove Beta branding, claim legal approval/certification, claim live SAP/Oracle integrations, claim predictive maintenance is live, claim plant-proven results, advertise measured savings/ROI, or claim enterprise/Aramco/SABIC readiness until the exact claim is substantiated and approved. E-Commerce advertisements can form part of the contract and the Law prohibits false or misleading claims. Publish only feature descriptions and results supported by the actual deployed version and documented evidence.

Before marketing, approve:
- final product name, trademark/domain and logo rights;
- truthful plan/feature comparison and exclusions;
- documented benchmark methodology and customer permission for any case study;
- disclaimers for heuristic, simulated, synthetic, advisory and unverified outputs;
- privacy/cookie/marketing consent behavior and unsubscribe/opt-out handling;
- sales proposal, order form, invoice and customer-support process.

## 8. Required legal evidence before the Beta label is removed

Attach a dated, signed evidence bundle:
1. Operator identity, legal form, active registration/activity and authorised signatory.
2. Saudi counsel's written entity, software-service, e-commerce, consumer, IP and contract classification.
3. PDPL applicability / controller-processor role assessment; National Register decision/registration; DPO decision/appointment.
4. RoPA, data-flow map, privacy notice, cookie/analytics notice and lawful-basis/consent register.
5. Cross-border transfer and hosting/subprocessor assessment, contracts and safeguards.
6. Data-subject request playbook and test evidence; retention/deletion schedule and tested evidence across database, Storage, logs, exports and backup lifecycle.
7. Breach response plan, 72-hour escalation clock, customer/regulator notification templates and incident contacts.
8. Required privacy impact assessments and security-control evidence.
9. Approved Terms of Service, subscription/order/renewal/cancellation/refund, customer DPA, SLA and support/complaints channel.
10. Tax/VAT/e-invoicing determination and approved invoice/credit-note process.
11. Marketing approval: trademark/IP clearance, substantiated feature/benefit statements and customer reference permissions.
12. Named Saudi privacy/legal and product/release-owner sign-offs.

## 9. Official references checked (2026-11-21)

- [SDAIA — Personal Data Protection Law and official guidance hub](https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPL/)
- [SDAIA — Implementing Regulation of the PDPL (PDF)](https://dgp.sdaia.gov.sa/wps/wcm/connect/2a9a4744-a2ae-444f-bad2-6dacde843637/The%2Bimpelementing%2Bregulation%2Bof%2Bthe%2Bpersonal%2Bdata%2Bprotection%2Blaw.pdf?MOD=AJPERES)
- [SDAIA — Regulation on Personal Data Transfer outside the Kingdom](https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPL2/)
- [SDAIA — Rules Governing the National Register of Controllers (PDF)](https://dgp.sdaia.gov.sa/wps/wcm/connect/2b9c4e29-a7a0-4334-9a3a-2b8610483e4e/The%2BRules%2BGoverning%2Bthe%2BNational%2BRegister%2Bof%2BControllers%2BWithin%2Bthe%2BKingdom.pdf?MOD=AJPERES)
- [SDAIA — Private-entity registration requirements](https://dgp.sdaia.gov.sa/wps/portal/pdp/Registration/private/)
- [SDAIA — Personal Data Breach Notification service](https://dgp.sdaia.gov.sa/wps/portal/pdp/services/personaldatabreachnotification/)
- [Ministry of Investment / Bureau of Experts official translation — E-Commerce Law (PDF)](https://misa.gov.sa/app/uploads/2025/07/E-Commerce-Law.pdf)
- [Ministry of Investment / Bureau of Experts official translation — Commercial Register Law (PDF)](https://misa.gov.sa/app/uploads/2025/07/Commercial-Register-Law.pdf) (the Arabic text governs)
- [Ministry of Commerce — Commercial registration service](https://mc.gov.sa/en/ESERVICES/pages/ServiceDetails.aspx?sID=38)
- [ZATCA — VAT registration for individuals](https://www.zatca.gov.sa/en/eServices/Pages/eservices-002.aspx)
- [National Cybersecurity Authority — Cloud Cybersecurity Controls](https://nca.gov.sa/en/regulatory-documents/controls-list/ccc/)

**Decision:** Saudi legal/privacy/commercial clearance is **NOT COMPLETE**. These references help structure the review but do not establish that the operator is registered, the processing is compliant, taxes are handled, or the consumer contract is lawful. Keep BETA and do not begin paid commercial launch until the actual entity, data flows, production locations and customer contract have been reviewed and signed off by qualified Saudi advisers.
