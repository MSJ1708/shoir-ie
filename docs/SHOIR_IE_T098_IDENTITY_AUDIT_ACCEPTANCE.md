# Shoir-IE T098 Identity and Audit Acceptance

Assessment date: 2026-11-20. Status: **repository implementation present in PR #232; real-provider configuration and hosted acceptance remain outstanding**.

## Current implementation and integration target

PR #232 (`feat/shoir-ie-release-hardening-20261105`) is the single staging release-hardening candidate. It contains the current T098 implementation. The former standalone PR #223 was superseded/closed after its reviewed implementation was selectively forward-ported; **do not merge PR #223**.

The implementation is integrated into the existing login page and keeps password sign-in available. OIDC is offered only when the Streamlit authentication configuration is ready and requires an explicit user action to verify identity and open Shoir-IE. The browser-side email is display-only; it is not used as an authorization or rate-limit identity.

The server-side persistence Edge Function independently verifies the ID token using pinned `jose`:
- permits RS256 and ES256 only;
- checks the exact configured issuer and client ID/audience;
- validates signature using the configured HTTPS JWKS endpoint, token expiry and maximum age;
- requires an email claim with provider-verified status;
- resolves the verified email to exactly one pre-existing Shoir-IE account whose `active` field is exactly `true`;
- never creates, promotes or upserts a Shoir-IE account through OIDC;
- can require MFA using configured provider `amr` and/or `acr` values, and denies when the required claim is absent;
- rate-limits pre-verification requests by trusted edge IP and uses the identity only after token verification;
- rejects replay of a previously exchanged ID token using a unique token fingerprint.

On success, the Edge Function issues the normal Shoir-IE session only after verification and account mapping. Audit events store SHA-256 token/subject fingerprints, not raw ID tokens or raw subjects. Audit persistence is fail-closed; if a mandatory write fails after session creation, the handler attempts to revoke that session. Logout revokes the Shoir-IE session and then ends the Streamlit identity-provider session.

The migration `supabase/migrations/20261118170000_shoir_oidc_audit_events.sql` creates the protected security-audit store with RLS enabled, direct privileges revoked from normal API roles, and service-role insertion only. It has **not** been applied to staging or production.

## Automated repository evidence

Current source and contract coverage includes:
- `shoir_oidc_auth.py` and the existing `app.py` login integration;
- `supabase/functions/shoir-persistence/oidc.ts`, `oidc_test.ts`, and the persistence Edge Function action;
- `tests/test_shoir_oidc_auth.py` and `tests/test_t098_oidc_integration_contract.py`;
- migration privilege/append-only assertions and Edge security tests;
- `docs/T098_OIDC_AUDIT_CONFIGURATION.md`, the staging-only configuration and test runbook.

These are implementation and automated-test artifacts, not evidence of a real identity provider connection. A mocked/local key test does not prove provider availability, key rotation, provider MFA policy, or hosted callback behavior.

## External configuration still required

The accountable owner must choose the organization-approved OIDC provider and create a **non-production staging client**. Configure:
1. Streamlit secrets: exact hosted callback URL, a strong random cookie secret, exposed ID token, provider client ID/client secret and provider metadata URL.
2. Staging Supabase Edge Function secrets: enable flag, exact issuer, matching client ID/audience, public JWKS URL and the provider-specific MFA `amr`/`acr` values.
3. Provider policy: verified-email claim enabled, authorized callback/logout URLs, and a documented MFA assurance policy that produces the configured claim.
4. Staging database: approved application of the audit migration after backup/recovery readiness, review and clean migration replay; then deploy the matching Edge Function source through the normal release process.

Secret values must remain in the deployment secret manager. Never commit them to the repository, place them in a workbook, or paste them into chat. The real issuer and JWKS URL must satisfy the code's HTTPS/public-DNS/same-host restrictions; do not weaken those restrictions to fit an unsupported provider endpoint.

## Required hosted acceptance (disposable identities only)

Use a disposable existing Shoir-IE account with synthetic/provider-controlled email. Do not use the protected Enterprise Admin account or customer identities.

Verify a valid sign-in and sign-out, then negative cases: wrong issuer/audience, invalid signature, expired or old token, unverified email, no matching account, duplicate matching accounts, inactive account, missing required MFA claim, replayed token, trusted-IP and verified-identity throttling, and audit-store outage. Verify the audit row contains only hashes/fingerprints and safe metadata; ensure normal roles cannot read, mutate or delete it; and prove a failed audit write cannot leave a usable Shoir-IE session. Test JWKS rotation/key rollover with the actual provider and confirm session revocation/logout behavior.

Capture the exact app/Edge SHA, provider/API metadata, redacted logs, audit-policy inspection, screenshots and test results. Obtain independent security review and resolve all review comments.

## Acceptance decision

T098 remains **`EXTERNAL_CONFIGURATION_REQUIRED` / NOT VERIFIED** until the real provider is configured, the staging audit migration and matching Edge code are deployed through approved gates, the full hosted positive/negative matrix passes, evidence is retained, and an independent reviewer accepts it.

No provider tenant, client secret, cookie secret, MFA claim mapping, staging migration, Edge deployment or hosted OIDC browser acceptance was performed in this repository-only work. Keep PR #232 draft, Shoir-IE BETA, and production NO-GO.
