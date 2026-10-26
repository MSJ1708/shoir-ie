# Shoir-IE data inventory and privacy operations template

**Status:** TEMPLATE / FACTUAL CONFIGURATION NOT VERIFIED / REQUIRES QUALIFIED REVIEW.  
Do not mark a provider, region, legal basis, retention period or transfer as compliant before verifying actual contracts and runtime configuration.

## Data-flow inventory

Complete one row per actual data flow. Known categories below are prompts for verification, not claims that every system is enabled.

| Data flow / category | Fields and sensitivity | Purpose | Source | Actual service/provider | Region/country | Access role | Recipients/processors | Proposed retention | Deletion path incl. backup/logs | Transfer path / safeguards | Legal basis / notice version | Status / evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Registration / identity | Username, email and any profile fields actually collected | Account creation/authentication/support | User | NOT VERIFIED | NOT VERIFIED | Authorized account service | NOT VERIFIED | NOT SET | NOT VERIFIED | NOT VERIFIED | COUNSEL TO CONFIRM | BLOCKED |
| Password/authentication/session | Password handling, salted hash, session/token identifiers; never store raw passwords in this inventory | Authentication and session security | User / auth service | NOT VERIFIED | NOT VERIFIED | Auth service / limited operators | NOT VERIFIED | NOT SET | NOT VERIFIED | NOT VERIFIED | COUNSEL TO CONFIRM | BLOCKED |
| Subscription/manual payment | Plan, status, transaction reference, optional proof file if enabled | Subscription request and manual reconciliation | User / operator | NOT VERIFIED | NOT VERIFIED | Authorized billing/admin roles | Payment provider and bank only as actually used | NOT SET | NOT VERIFIED | NOT VERIFIED | COUNSEL / ACCOUNTANT TO CONFIRM | BLOCKED |
| Workspaces and industrial data | Uploaded workbooks, raw/clean tables, columns, formulas, industrial/customer data | User-requested engineering workflows | User / import connector | NOT VERIFIED | NOT VERIFIED | Workspace members and authorized service roles | NOT VERIFIED | NOT SET | NOT VERIFIED | NOT VERIFIED | CONTRACT / PRIVACY REVIEW REQUIRED | BLOCKED |
| Calculations and decisions | Inputs, outputs, assumptions, scenarios, provenance, approvals | Analysis, simulation, optimization, reporting | User/tool | NOT VERIFIED | NOT VERIFIED | Workspace roles | NOT VERIFIED | NOT SET | NOT VERIFIED | NOT VERIFIED | CONTRACT / PRIVACY REVIEW REQUIRED | BLOCKED |
| Logs, audit and diagnostics | Session events, errors, support bundle fields, audit events | Security, support, reliability | App/service | NOT VERIFIED | NOT VERIFIED | Limited support/security roles | Hosting/monitoring providers if enabled | NOT SET | NOT VERIFIED | NOT VERIFIED | COUNSEL TO CONFIRM | BLOCKED |
| AI/Copilot | Prompt, relevant context, response and any attached data actually transmitted | User-requested AI assistance | User/workspace | Model/provider NOT VERIFIED | NOT VERIFIED | User and authorized service | Provider/subprocessors NOT VERIFIED | NOT SET | NOT VERIFIED | NOT VERIFIED | COUNSEL TO CONFIRM | BLOCKED |
| Email/support | Contact details, complaint/ticket content, attachments | Support and complaint handling | User/operator | NOT VERIFIED | NOT VERIFIED | Support role | Email/helpdesk providers if enabled | NOT SET | NOT VERIFIED | NOT VERIFIED | COUNSEL TO CONFIRM | BLOCKED |
| Referral attribution | Referral code, attributed owner/account linkage and timestamps if enabled | Attribution only unless a separate program is authorized | Registration flow | NOT VERIFIED | NOT VERIFIED | Restricted referral/admin paths | NOT VERIFIED | NOT SET | NOT VERIFIED | NOT VERIFIED | COUNSEL TO CONFIRM | BLOCKED |
| Exports/files | XLSX/PDF/PPTX/ZIP contents, filenames, provenance and any embedded data | User-requested downloads/sharing | App/workspace | NOT VERIFIED | NOT VERIFIED | User/workspace roles | User-chosen recipients; storage providers if any | NOT SET | NOT VERIFIED | NOT VERIFIED | CONTRACT / PRIVACY REVIEW REQUIRED | BLOCKED |
| Backups/caches | Copies of any categories above, including local ephemeral files | Recovery and operation | Systems | NOT VERIFIED | NOT VERIFIED | Restricted operator roles | Hosting/database vendors | NOT SET | NOT VERIFIED | NOT VERIFIED | COUNSEL TO CONFIRM | BLOCKED |

## Operational procedures to define and test

- Data-subject requests: intake channel, identity verification, owner, response timeline, access/correction/deletion/export capabilities, exceptions, audit record.
- Incident/breach: detection, severity/risk assessment, evidence preservation, response owner, counsel/privacy escalation, regulator/data-subject notification decision and applicable deadline.
- Retention/deletion: deletion request across primary DB, object/file storage, logs, analytics, vendor systems, backups and derived exports; define exceptions and evidence.
- Cross-border transfers: actual source/destination/provider, access paths, subcontractors, transfer purpose and safeguards reviewed by qualified counsel.
- Processor/vendor inventory: signed terms, subprocessor changes, support access, data location and return/deletion commitments.
- Data minimization: prohibit unnecessary personal data in industrial datasets, diagnostic bundles, prompts and shared exports; never include passwords/tokens.
- Security: enforce authorization server-side and review RLS/RPC/Edge access; the UI hiding an item is not an access-control test.

## Review sources

Use the current official SDAIA PDPL Knowledge Center, implementing regulation, personal-data transfer regulation and Controller/Processor guidance, plus qualified Saudi privacy/legal review. The actual hosting/vendor facts must be verified; this template does not establish a transfer or compliance conclusion.

**Owner:** NOT NAMED  
**Last verified against actual deployment/configuration:** NOT VERIFIED  
**Qualified review:** NOT RECEIVED  
**Status:** BLOCKED
