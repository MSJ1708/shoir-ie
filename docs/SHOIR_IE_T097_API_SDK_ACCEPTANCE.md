# T097 — API, SDK, and Plugin Toolkit Acceptance

**Acceptance status:** `EXTERNAL_CONFIGURATION_REQUIRED`  
**Release status:** **NOT ACCEPTED / NOT VERIFIED**  
**Scope:** Staging-first acceptance. This record does not authorize a public production API or third-party customer access.

## 1. Implemented boundary (do not overstate)

The current repository contains a local server-side plugin registry and Workbench contract inspector. It validates plugin metadata, JSON input/output schemas, declared scopes and payload bounds. Metadata-only entries remain non-executable until a reviewed handler is installed.

This is **not** evidence of a hosted public REST API, an externally consumable SDK, production identity, tenant-isolated API keys, or a live connector. The local registry and its tests are foundations only.

## 2. External prerequisites

- An approved API hostname, DNS ownership, valid TLS certificate and hosted gateway/runtime.
- A defined API versioning policy and published OpenAPI specification with stable request, response and error schemas.
- An approved identity design (OIDC/OAuth2 or equivalent service identity), issuer/audience validation, narrowly scoped credentials, tenant binding, expiry, revocation and key rotation.
- Secret storage for provider credentials. Secrets must never be committed, returned to the browser, or written into diagnostic artifacts.
- Per-tenant rate limits, request/body/time bounds, idempotency and replay controls, audit logging, redaction, monitoring and incident handling.
- A reviewed provider/connector handler and a staging sandbox containing synthetic data.
- A versioned SDK package (at minimum the supported client language selected for the first external integration), installation instructions, typed examples, compatibility policy and changelog.

No external endpoint or provider credential is assumed to exist. Select one concrete provider/use case before claiming a connector is integrated.

## 3. Required acceptance cases

| Area | Required evidence |
|---|---|
| Authentication | Missing, malformed, expired, revoked and wrong-audience credentials are denied; authorized credentials succeed. |
| Authorization | Missing/insufficient scope returns 403; tenant A cannot read or mutate tenant B resources. |
| Transport | TLS is enforced; redirects, unsafe hosts and disallowed protocols are rejected; request size and timeout limits hold. |
| Contracts | OpenAPI schema validates; required/optional/null/unknown fields, malformed JSON and schema-version changes have deterministic responses. |
| Rate limiting | Per-tenant and per-key limits return documented 429 responses and safe retry hints. |
| Idempotency | Replayed requests cannot duplicate non-idempotent actions; keys are scoped and expire as documented. |
| Pagination | Stable ordering, cursor validation, terminal pages and maximum page size are tested. |
| SDK | Install from the published package, authenticate, call the staging endpoint, parse typed responses and handle documented errors. |
| Audit/security | Actor, tenant, action, outcome and correlation ID are captured; credentials and sensitive payloads are redacted. |
| Lifecycle | Key issue/rotation/revoke, API deprecation and version compatibility are tested. |

## 4. Evidence bundle

Attach:
1. Exact source commit SHA and deployed staging build/version.
2. API hostname/TLS validation and staging environment identity.
3. OpenAPI document checksum and contract-test report.
4. Redacted request/response examples for success and each negative case.
5. Cross-tenant isolation, scope-denial, rate-limit and idempotency test outputs.
6. SDK package version, checksum, installation log and successful sample-client output.
7. Redacted audit evidence and reviewer sign-off from an independent API/security reviewer.

Never attach raw access tokens, secrets, customer data or production keys.

## 5. Pass/fail rule

T097 may move to `VERIFIED_WORKING` only when all required cases pass against a real hosted **staging** endpoint using disposable tenants and synthetic data, the SDK is consumed by an external test client, and independent security review is recorded.

A passing local registry unit test or metadata-only Workbench screen does not satisfy this gate. Until all evidence exists, retain `EXTERNAL_CONFIGURATION_REQUIRED` and block any claim that a public API/SDK is available.

## 6. Safe execution order

1. Choose the first provider/resource and obtain authorization for a staging sandbox.
2. Provision the staging hostname, TLS, identity issuer/client, scopes and secrets.
3. Publish and review the versioned OpenAPI contract.
4. Implement the authenticated tenant-scoped gateway and reviewed provider handler.
5. Build and publish a versioned SDK to a private/test package channel.
6. Run the complete positive/negative contract and tenant-isolation matrix.
7. Collect redacted evidence and independent security approval.
8. Only then propose production configuration through a separately reviewed release.

**No production endpoint, customer credential, or live customer data is required or permitted for this acceptance test.**
