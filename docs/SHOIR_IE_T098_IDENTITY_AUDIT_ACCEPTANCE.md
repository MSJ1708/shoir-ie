# Shoir-IE T098 Identity and Audit Acceptance

Assessment date: 2026-11-06. Status: **draft implementation; provider not configured**.

PR #223, [T098 provider-backed OIDC and append-only security audit](https://github.com/MSJ1708/shoir-ie/pull/223), remains draft. Its description records optional OIDC login, server JWT validation, exact verified-email mapping, optional MFA-claim enforcement and server-only audit insertion. It explicitly states no real provider tenant, issuer, client ID/secret, cookie secret, JWKS configuration, verified-email behavior or MFA claim has been supplied.

Required: exact-head Deno and SQL replay results; independent review of signature/issuer/audience/algorithm/JWKS rotation/state/nonce/replay/session rollback; staging IdP config; live success/failure/expired/replay/inactive/ambiguous identity/MFA tests; append-only audit insert/read/retention and actor-attribution acceptance.

Complete by reviewing PR #223, configuring a staging-only provider, verifying exact issuer/audience/key rotation/claims, enforcing actual MFA at the provider, running disposable-account hosted tests, proving audit failure fails closed, testing revocation and account deactivation, then attaching exact-SHA evidence. A UI setting or database flag is not proof of OIDC/MFA connectivity.
