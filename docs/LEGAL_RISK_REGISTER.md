# Shoir-IE Legal and Launch-Risk Register

**Review date:** 25 October 2026  
**Status: NOT LEGALLY CLEARED FOR COMMERCIAL PRODUCTION.** This is an engineering/source inventory, not legal advice, a compliance opinion, security certification, or proof of conformance with Saudi law.

## Release-blocking items

| Area | Current evidence | Required before paid commercial launch | Owner |
|---|---|---|---|
| Legal operator identity | Product name and contact email are present; legal entity identity/address not verified in this repository review | Publish accurate legal name, official address, applicable commercial registration and contact route; verify authority to offer the service | Operator / Saudi counsel |
| Saudi PDPL and privacy | Privacy notice describes potential processing by Streamlit, Supabase and Anthropic and notes that processing may occur outside the Kingdom of Saudi Arabia | Map actual personal data, purposes, lawful bases, recipients, processors, retention/deletion, rights workflow, incident response, and cross-border transfer arrangements; obtain review against current PDPL and implementing regulations | Privacy owner / counsel |
| Terms and consumer protection | Beta terms and refund notice exist | Counsel should verify mandatory consumer rights, applicable e-commerce requirements, disclosures, taxes, dispute process, governing-law language, and Arabic-language requirements for the actual offer | Saudi counsel |
| Copyright and licenses | Repository license and a source-level third-party review exist | Generate and review an exact dependency SBOM, license notices, bundled asset provenance, model/provider terms, and obligations of transitive dependencies for the release build | Engineering / counsel |
| Engineering claims | 100 target IDs are inventoried, but the candidate report currently classifies 0 as VERIFIED_WORKING | Independently validate each advertised tool, units, boundary cases, deterministic outputs, limitations, safety implications, and evidence provenance; remove unsupported savings or performance claims | Engineering lead |
| Security and isolation | Static review and automated checks exist; runtime tenant denial and route-level enforcement have not been fully evidenced | Complete authenticated cross-user/cross-workspace and tier-bypass tests, session revocation/expiry, upload/parser abuse, secret/log review and deployment parity | Security lead |
| Commercial operations | Payment review is manual; referrals are attribution only | Confirm pricing, tax, invoice/receipt, support, refund, cancellation, renewal, incident, data export/deletion, and complaint workflows | Operator |

## Referral statement
Referral codes record attribution only. No discount, free month, commission, cash payment or other reward is currently offered or guaranteed. Do not publish referral income, conversion, or benefit claims without verified underlying records.

## Beta engineering disclaimer
Shoir-IE is undergoing beta testing and active development. Calculations, AI responses, simulations, exports, integrations, saved data and permissions can fail or be incomplete. Users must independently validate source data, units, assumptions, constraints, calculations and results before use. Do not use outputs as the sole basis for safety-critical or legally regulated decisions.

## Evidence still missing
- A signed review by qualified Saudi legal counsel for the actual operator and commercial offer.
- Confirmed PDPL inventory, transfer/processor assessment and retention schedule for the deployed stack.
- Verified license and provenance inventory for the exact release artifact.
- Authenticated staging acceptance for all capabilities that will be advertised as operational.
- Independent security assessment and disposition of high/critical findings.
- Confirmed deployment parity between reviewed source SHA, staging and any intended release.

**Decision:** NO-GO for paid commercial release until each mandatory item is completed or explicitly accepted by an authorized accountable owner with documented rationale. Software tests alone cannot certify legal compliance.
