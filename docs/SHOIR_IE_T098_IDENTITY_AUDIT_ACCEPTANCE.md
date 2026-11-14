# Shoir-IE T098 Identity and Audit Acceptance

Assessment date: 2026-11-08. Status: **provider-backed OIDC/MFA remains unconfigured; independent acceptance is outstanding**.

## Current repository / pull request state

PR #223 ([provider-backed OIDC and append-only security audit](https://github.com/MSJ1708/shoir-ie/pull/223)) remains open and draft. Last inspected head: `86cf0102f47c9a6e33269f7019a259158144453d`.

The proposal contains optional OIDC login, server-side JWT validation, exact verified-email mapping, optional MFA-claim enforcement and server-only audit insertion. The repository and PR description do not establish that a real identity provider tenant is configured.

No verified issuer, audience/client ID, client secret, cookie secret, JWKS endpoint/key rotation, verified-email behavior or MFA claim has been supplied for staging. A setting, mock JWT or database flag is not evidence of SSO/MFA connectivity.

## Required before acceptance

1. Review PR #223 as a separate security-sensitive change and reconcile it with the current PR #232 release candidate; do not merge the divergent branch wholesale.
2. Configure a staging-only IdP application and redirect URLs. Store client/cookie secrets in the approved server-side secret store.
3. Verify signature, allowed algorithm, issuer, audience, key rotation/JWKS cache, state, nonce, PKCE where applicable, clock skew, expiry, replay rejection and exact account/email mapping.
4. Confirm the provider supplies an actually verified email claim and an MFA-authentication claim with the required assurance level. Do not infer MFA from a local account flag.
5. Exercise success, invalid signature, wrong issuer/audience, missing/unverified email, unknown/ambiguous account, expired token, replay, inactive account, session revocation and provider outage using disposable staging identities.
6. Verify audit writes are server-side and append-only, attribute the real actor, fail closed when a mandatory audit write fails, and enforce retention/access/export controls.
7. Attach exact-SHA CI, SQL replay, hosted success/failure evidence, sanitized audit rows and independent security review.

No OIDC provider acceptance, MFA assurance, or complete enterprise identity coverage is claimed. T098 remains **EXTERNAL_CONFIGURATION_REQUIRED** until a real staging IdP and its security tests pass.

## Workbench route added — 2026-11-08

The existing Workbench now exposes a focused T098 configuration-readiness check using server-side configuration names and status flags only. It explicitly reports `sso_active=false`, `mfa_active=false` and untested provider evidence; it does not start login, activate MFA, or display secret values. A Workbench AppTest exercises the route. Real IdP configuration and browser acceptance remain outstanding.

