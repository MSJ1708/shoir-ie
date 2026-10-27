> **DRAFT FOR OWNER AND QUALIFIED SAUDI COUNSEL REVIEW — NOT FOR CUSTOMER USE OR PUBLICATION.**  

> **Review status update — 27 October 2026:** This remains an unapproved working draft. Do not publish, activate paid access, represent compliance, or rely on it as legal advice. The accountable operator must supply the true legal identity/address/registration, actual prices and tax treatment, support contact, data flows/retention/hosting/transfer facts, and working refund/cancellation process. Qualified Saudi counsel and a privacy reviewer must approve the text against actual deployed behavior before customer use. The successful staging gate is not legal clearance.

> This draft describes attribution-only behavior. It does not authorize a reward, discount, commission, payment or marketing claim.

# Shoir-IE referral attribution — draft rules

## 1. Current intent

A referral code may be used to record how a registration or enquiry was referred. Attribution is a measurement/recordkeeping feature only. A code does not itself create a discount, commission, credit, free period, reward, payment entitlement or guarantee of acceptance.

## 2. No reward unless separately activated

No referral reward is offered by these draft rules. Do not show a reward rate, promised value, referral earnings or invented referral counts. A reward program must not be activated until the actual operator approves its economics and eligibility, qualified counsel approves program terms and advertising, and the implementation is independently tested.

## 3. Attribution requirements

Attribution must be recorded and read using authorized server-side operations. Do not trust client-side display state for attribution counts or eligibility. The product should reject malformed/unknown codes according to the actual policy and return a neutral, non-sensitive message. The referral owner must not gain access to another person's account details, payment evidence, workspace data or private registration details.

## 4. Abuse and duplicate handling

The implementation should define and test self-referral denial, repeated submissions, duplicate code attribution, case normalization, unknown/inactive codes, concurrent registration, account deletion, corrections and audit events. A failed server write must not be displayed as a successful attribution. Logs should avoid unnecessary personal data and never contain passwords, tokens or payment secrets.

## 5. Privacy and retention

Referral attribution may constitute personal data when linked to a user or account. The operator must record its actual purpose, data fields, source, legal basis, access roles, recipients, retention period, correction/deletion process and any cross-border processing in the privacy data map. Publish only wording that matches actual server/database behavior.

## 6. Customer-facing wording (draft)

“Referral codes may be used to record the source of a registration or enquiry. Unless Shoir-IE publishes separate terms for an approved promotion, a referral code does not provide a discount, commission, credit, free period or other reward.”

## 7. Acceptance evidence required

Before release, provide tests for code creation and validation, correct attribution to an eligible owner, unknown/inactive codes, self-referral, duplicate/concurrent attribution, unauthorized summary/read attempts, failed server write, account deletion/retention behavior, and policy text/version display. Confirm that every displayed count derives from authorized real data and that no reward is implied if none exists.

**Status:** ATTRIBUTION-ONLY DRAFT / NO REWARDS AUTHORIZED / NOT LEGALLY APPROVED.
