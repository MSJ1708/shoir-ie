# T098 — OIDC and durable audit configuration

**Status: IMPLEMENTATION CANDIDATE / NOT PROVIDER-VERIFIED.** This document describes the configuration required for an isolated non-production test. It does not claim an identity provider is connected, MFA is enabled, or production is approved.

## Design and fail-closed behavior

The optional sign-in method is integrated into the existing Shoir-IE sign-in screen and does not replace password login. It is hidden behind Streamlit OIDC configuration readiness. After the provider redirect, a user must explicitly choose **Verify identity and open Shoir-IE**; the UI never authorizes a user from the displayed email. It sends the exposed ID token server-side to the persistence Edge Function. The Edge Function independently validates the JWT signature, issuer, audience, algorithm, token age/expiry, subject and verified email, then requires exactly one pre-existing active Shoir-IE account with that exact verified email. OIDC does not create or promote accounts.

The Edge Function can require provider-backed MFA claims. If MFA is required but the token does not contain a configured acceptable `amr` or `acr` claim, sign-in is denied. A configuration flag by itself does not prove MFA. The ID token is never written to logs; the append-only audit stores a SHA-256 token fingerprint and subject fingerprint, not raw tokens or raw subjects. The token fingerprint's unique constraint provides one-time exchange semantics: a previously exchanged ID token cannot create another Shoir-IE session. A failed audit write fails authentication closed and attempts to revoke any just-created session.

Audit records are stored in `public.shoir_security_audit_events`. The proposed migration enables RLS, denies all direct privileges to `PUBLIC`, `anon` and `authenticated`, and grants the service role only INSERT plus the minimum sequence USAGE needed to allocate an ID. It does not grant normal API roles SELECT/UPDATE/DELETE. Apply this migration to **staging only** after review and migration replay; never apply it to production without a separate explicit approval.

## Required Streamlit secrets

Configure these values in Streamlit Cloud's **app secrets manager**, not in Git or `.streamlit/config.toml`. For a named provider, Streamlit's shared settings and the provider's keys must be in secrets:

```toml
[auth]
redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
cookie_secret = "REPLACE_WITH_A_STRONG_RANDOM_SECRET_FROM_SECRET_MANAGER"
expose_tokens = "id"

[auth.enterprise]
client_id = "VALUE_FROM_IDP_APP_REGISTRATION"
client_secret = "STORE_IN_STREAMLIT_SECRETS_ONLY"
server_metadata_url = "https://YOUR-IDP-ISSUER/.well-known/openid-configuration"
```

Replace each placeholder using the approved identity provider. Do not commit actual credentials. Register the exact hosted callback URL as a redirect URI in the identity provider and permit only the intended Shoir-IE host. A local-development callback is not a hosted callback.

The code uses the named provider key `enterprise`, so it calls `st.login("enterprise")`. Streamlit must support its OIDC user API and the exposed `st.user.tokens["id"]` entry. The current repository requirement is `streamlit>=1.61,<2`.

## Required staging Edge Function secrets

Configure these secrets in the **staging Supabase project only** (`hfhrosthswcybccepmak`) after a provider is chosen:

```text
SHOIR_OIDC_ENABLED=true
SHOIR_OIDC_ISSUER=https://YOUR-IDP-ISSUER
SHOIR_OIDC_CLIENT_ID=THE_SAME_CLIENT_ID_AS_STREAMLIT
SHOIR_OIDC_JWKS_URL=https://YOUR-IDP-ISSUER/.well-known/jwks.json
SHOIR_OIDC_REQUIRE_MFA=true
SHOIR_OIDC_MFA_AMR_VALUES=mfa
SHOIR_OIDC_MFA_ACR_VALUES=OPTIONAL_PROVIDER_SPECIFIC_MFA_ACR
```

The Edge Function currently requires an HTTPS DNS issuer and JWKS URL on the same hostname, and rejects IP literals, localhost and private/local-style hostnames. Use the provider's documented issuer and JWKS URL only after confirming that they satisfy this restriction; do not weaken URL validation to make an arbitrary endpoint work. The issuer and client ID must exactly match the token's `iss` and `aud`. Use provider documentation to select valid `amr`/`acr` values; do not assume every provider emits `amr=mfa`. Do not enable `SHOIR_OIDC_REQUIRE_MFA=true` until the real provider's MFA policy and token claims have been verified, and do not claim MFA merely because the flag is set.

## Test sequence for the provider owner

1. Choose an identity provider (for example, an organization-managed OIDC issuer) and create a non-production client with exact callback URL, email scope and verified-email claim enabled.
2. Configure only the staging Streamlit secrets and staging Edge Function secrets. Never copy provider credentials to the repo or production.
3. Apply `20261028190000_shoir_oidc_audit_events.sql` to a disposable local Postgres instance and the approved staging project only after the migration-review gate passes.
4. Run the new Deno OIDC test suite and full migration history replay on the exact branch SHA.
5. Register a **disposable existing Shoir-IE account** with a synthetic, provider-controlled email; do not use the protected administrator, a customer identity, or a real account.
6. Verify valid login, wrong issuer/audience, tampered signature, expired token, unverified email, inactive/unmapped/duplicate-email account, MFA missing when required, throttling, duplicate token exchange, and audit-store outage. Confirm failure paths do not return an application token.
7. Verify through authorized database inspection that each success/denial event is recorded, raw tokens and subjects are absent, normal roles cannot read audit records, and a failed audit write does not leave a usable session.
8. Verify logout first revokes the Shoir-IE session and then ends the Streamlit OIDC session.
9. Save redacted logs and exact artifact hashes. Obtain an independent security review before closing T098.

## Open dependencies

- A specific approved identity provider and its tenant/client registration.
- Streamlit secrets for callback URL, random cookie secret, client ID and client secret.
- Staging Supabase Edge Function secret values for issuer, audience/client ID and JWKS URL.
- Provider evidence for the expected verified-email and MFA claims.
- Staging migration approval and successful exact-head migration rehearsal.
- Disposable non-production test account and a completed hosted browser run.
- Independent security review.

Until every item above is complete, T098 remains `EXTERNAL_CONFIGURATION_REQUIRED` / `IMPLEMENTED_NEEDS_VALIDATION` as appropriate. This branch is a draft candidate, not a verified integration.
