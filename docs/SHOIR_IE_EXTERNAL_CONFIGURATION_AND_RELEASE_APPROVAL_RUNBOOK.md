# Shoir-IE External Configuration, Operational Acceptance and Release Approval Runbook

**Scope:** hand-off from repository engineering to owner-controlled staging configuration and then to production release review.  
**Current release status:** BETA / NO-GO. This document is a procedure, not a deployment or legal approval.  
**Current integration target:** PR #232, branch `feat/shoir-ie-release-hardening-20261105`, base `staging-e2e-20261019`.

## 0. Non-negotiable safety rules

1. Use only the dedicated staging Supabase project `hfhrosthswcybccepmak` and a separate staging Streamlit app. The production Supabase project is `gcsamrdaeraxieaagsta`; never use it for these tests.
2. Never use the protected Enterprise Admin account `sho`, any customer account, customer data, real payment reference, or production credential for testing.
3. Use the seven dedicated `shoir-e2e-*` identities only for automated staging tests. Never create these users with direct SQL; use the repository's registration/approval provisioner.
4. Do not put DB passwords, service-role/secret keys, IdP client secrets, user passwords, bearer tokens or private test credentials in Git, issues, PR comments, workflow inputs, workbooks or chat.
5. Never put a Supabase service-role/secret key in GitHub Actions. The authenticated release gate accepts the staging publishable/anon key only.
6. No staging migration/function deployment until exact-head CI has passed, an independent review has approved the latest push, review threads are resolved, and the staging backup/rollback readiness is documented.
7. No production migration, Edge deployment, Streamlit release, PR merge or customer rollout until staging acceptance, independent technical/security/privacy reviews, recovery evidence and explicit owner authorization are complete.
8. A queued, skipped, authored, mocked or older-SHA test is not a pass. Preserve the source SHA, run URL, artifact and reviewer for every accepted gate.

## 1. Confirm the repository candidate and CI

1. Open [PR #232](https://github.com/MSJ1708/shoir-ie/pull/232). Confirm it is still the intended draft PR from `feat/shoir-ie-release-hardening-20261105` into `staging-e2e-20261019`.
2. Copy the exact HEAD SHA from the PR page. Do not use a SHA from an earlier runbook or an earlier chat.
3. In Actions, inspect all eight required staging contexts for that exact SHA:
   - `test`
   - `edge-function`
   - `engine-regression`
   - `security-quality`
   - `clean-postgres-migration-replay`
   - `postgres-transaction-contract`
   - `production-v9-security-backport`
   - `excel-intelligence`
4. Open each run and inspect job steps, JUnit/log artifacts, skipped tests, warnings and export-render evidence. All eight must pass on the same exact head. A full validation run with `live-deployment-smoke` skipped is not authenticated staging acceptance.
5. Require one independent reviewer, approval of the latest push and resolution of every review thread. The PR must remain draft until the independent reviewer and release owner agree that the staging prerequisites are met.

**Important:** the new candidate migration `20261120115000_shoir_dataset_storage_lifecycle_leases.sql` and matching Edge source are candidate-only until a separately approved staging deployment. No PR merge is implied by a green CI run.

## 2. Prepare the dedicated staging Streamlit app

Create/use a separate Streamlit Cloud app for staging, and configure its own Manage app → Settings → Secrets. The app must deploy the candidate branch so that the shell shows both:

- `STAGING TEST ENVIRONMENT`
- `SHOIR-IE SHELL VERSION: 3.2`

Use only the staging project URL and staging publishable key. The repository's staging secrets contract is:

```toml
[shoir]
environment = "staging"
supabase_url = "https://hfhrosthswcybccepmak.supabase.co"
publishable_key = "PASTE_THE_STAGING_PUBLISHABLE_KEY_HERE"
```

Replace the placeholder only in Streamlit's secret editor. The equivalent environment names documented by the app are `SHOIR_ENVIRONMENT=staging`, `SHOIR_SUPABASE_EDGE_URL` and `SHOIR_SUPABASE_PUBLISHABLE_KEY`.

Do not configure any direct database DSN in the staging Streamlit app. The app refuses direct fallback DSNs including `database.url`, `postgresql.url`, `supabase.url`, `SHOIR_DATABASE_URL`, `SUPABASE_DB_URL` and `DATABASE_URL`. A leftover production DSN must not bypass the staging Edge Function.

Verify the app's exact public HTTPS hostname and that its Edge URL belongs to `hfhrosthswcybccepmak`. Do not use the production Streamlit hostname `https://shoir-ie-app.streamlit.app/`.

## 3. Provision or recover the seven disposable E2E accounts

The authenticated release workflow needs seven unique identities, all prefixed with `shoir-e2e-`:

| Identity | Required state | Purpose |
|---|---|---|
| Active | Enabled, non-admin, Enterprise Plus by default | Login, workspace save/reload/re-login and session revocation |
| Second | Enabled, non-admin, different account | Cross-owner workspace denial |
| Starter | Enabled, non-admin, Starter | Tier and admin endpoint denial |
| Expired | Enabled, non-admin, expiry in the past | Renewal-only login and renewal restrictions |
| Module | Enabled, non-admin, Enterprise Plus | Module route/default-state matrix |
| Research module | Enabled, non-admin, Research Pack add-on | Research-only route matrix |
| Inactive | Disabled non-admin, future expiry | Inactive login denial |

Use the repository lifecycle helper from a trusted computer only:

```bash
python scripts/provision_staging_e2e_accounts.py
```

The helper is hard-pinned to the staging project, rejects production, asks for the staging publishable key, staging service-role/server secret, and staging administrator password through hidden prompts, and requires the exact confirmation phrase it prints. It uses normal registration and approval actions; the references are synthetic no-charge staging fixtures. It writes a private, git-ignored `.staging-e2e-credentials.json` file with restricted permissions and a secret-name mapping. Copy the generated username/password pairs into the corresponding GitHub Actions secrets below, keep the file private during the operation, and securely delete it once the secrets are confirmed.

If the identities already exist, do not blindly provision again. Inspect the provisioner's state file and staging registration queue. If passwords do not match Actions secrets, use the documented recovery helper `scripts/recover_staging_e2e_credentials.py` (or the PowerShell wrapper on Windows) to reset only the seven disposable identities. It is pinned to staging and does not create/delete accounts or modify `sho`.

## 4. Configure GitHub Actions secrets and variables

In GitHub repository Settings → Secrets and variables → Actions, create the following **repository Actions secrets**:

| Secret | Value |
|---|---|
| `SHOIR_E2E_EDGE_URL` | Full URL of staging `shoir-persistence` Edge Function |
| `SHOIR_E2E_PUBLISHABLE_KEY` | Staging Supabase publishable key (or supported legacy anon key); never service-role |
| `SHOIR_E2E_APP_URL` | Dedicated staging Streamlit HTTPS URL |
| `SHOIR_E2E_ACTIVE_USERNAME` / `SHOIR_E2E_ACTIVE_PASSWORD` | Disposable Active account credentials |
| `SHOIR_E2E_SECOND_USERNAME` / `SHOIR_E2E_SECOND_PASSWORD` | Disposable Second account credentials |
| `SHOIR_E2E_STARTER_USERNAME` / `SHOIR_E2E_STARTER_PASSWORD` | Disposable Starter account credentials |
| `SHOIR_E2E_EXPIRED_USERNAME` / `SHOIR_E2E_EXPIRED_PASSWORD` | Disposable Expired account credentials |
| `SHOIR_E2E_MODULE_USERNAME` / `SHOIR_E2E_MODULE_PASSWORD` | Disposable Enterprise Plus Module account credentials |
| `SHOIR_E2E_RESEARCH_MODULE_USERNAME` / `SHOIR_E2E_RESEARCH_MODULE_PASSWORD` | Disposable Research Pack account credentials |
| `SHOIR_E2E_INACTIVE_USERNAME` / `SHOIR_E2E_INACTIVE_PASSWORD` | Disposable Inactive account credentials |

Create these **Actions variables**:

| Variable | Value |
|---|---|
| `SHOIR_E2E_EXPECTED_STAGING_APP_HOST` | Exact app hostname only (no scheme, path or trailing route) |
| `SHOIR_E2E_ACTIVE_EXPECTED_TIER` | Optional; set only if the Active account should differ from default `Enterprise Plus Tier ($399)` |
| `SHOIR_E2E_VERIFY_LOGIN_THROTTLE` | Optional; set `true` only for a deliberately planned synthetic-IP throttle test |

Do not add the service-role key, DB password or any OIDC client secret to Actions for this gate. Its preflight validates the staging target and the presence of the variables before browser navigation.

## 5. Configure T098 OIDC and provider-backed MFA

T098 implementation is already part of PR #232. It is not provider-verified until a real non-production identity-provider client and hosted test exist.

### 5.1 Identity-provider setup

Choose an organization-approved OIDC identity provider. Create a **non-production staging application/client**. Configure:
- exact redirect URI equal to the staging app's `https://YOUR-STAGING-APP.streamlit.app/oauth2callback`;
- exact logout/callback host;
- openid/email/profile scopes required by the implementation;
- verified-email claim enabled;
- a provider-backed MFA policy, and document the actual `amr` and/or `acr` claim emitted by successful MFA;
- no account creation or account promotion through OIDC.

Do not assume every provider emits `amr=mfa`. Confirm claims from a staging test token using the provider's approved inspection tools; never paste the token into chat or commit it.

### 5.2 Staging Streamlit OIDC secrets

In the staging Streamlit app's app secrets manager, configure the following placeholders with the values supplied by the selected provider and secret manager:

```toml
[auth]
redirect_uri = "https://YOUR-STAGING-APP.streamlit.app/oauth2callback"
cookie_secret = "GENERATE_AND_STORE_A_STRONG_RANDOM_SECRET"
expose_tokens = "id"

[auth.enterprise]
client_id = "STAGING_IDP_CLIENT_ID"
client_secret = "STAGING_IDP_CLIENT_SECRET"
server_metadata_url = "https://YOUR-IDP-ISSUER/.well-known/openid-configuration"
```

The application uses the provider name `enterprise` and calls `st.login("enterprise")`. It requires the supported Streamlit OIDC API and exposed `st.user.tokens["id"]`. The repository pins the supported range to `streamlit>=1.61,<2`.

### 5.3 Staging Supabase Edge Function secrets

In the staging Supabase project only, configure these Edge Function secrets via the Supabase secret manager:

```text
SHOIR_OIDC_ENABLED=true
SHOIR_OIDC_ISSUER=https://YOUR-IDP-ISSUER
SHOIR_OIDC_CLIENT_ID=THE_SAME_CLIENT_ID_AS_STREAMLIT
SHOIR_OIDC_JWKS_URL=https://YOUR-IDP-ISSUER/.well-known/jwks.json
SHOIR_OIDC_REQUIRE_MFA=true
SHOIR_OIDC_MFA_AMR_VALUES=PROVIDER_VERIFIED_MFA_AMR
SHOIR_OIDC_MFA_ACR_VALUES=PROVIDER_VERIFIED_MFA_ACR
```

The exact issuer and JWKS endpoint must be HTTPS DNS names on the same hostname and meet the Edge Function's public-DNS restrictions. Issuer, client ID/audience and token claims must match exactly. Configure only the claim values actually proven by the provider. Do not enable mandatory MFA until this mapping has been verified.

### 5.4 Apply the OIDC audit store only to staging

Migration `20261118170000_shoir_oidc_audit_events.sql` is part of the candidate, not yet a live configuration proof. Apply it only in a reviewed staging deployment window after backup/rollback readiness and clean exact-head migration replay. Deploy the exact matching Edge Function only after the same release review. Never apply this migration to production as part of the staging exercise.

### 5.5 Required OIDC acceptance

Using one disposable existing Shoir-IE account with a provider-controlled synthetic email, verify:
- successful login and mapping to exactly one existing active Shoir-IE account;
- wrong issuer/audience, invalid signature, expiry, unverified email, missing/inactive/duplicate mapping are denied;
- token replay is denied;
- required MFA succeeds only with provider-backed claims and fails without them;
- pre-verification throttling does not use browser-supplied email;
- audit events store hashes/fingerprints, not raw token/subject;
- normal browser roles cannot read or mutate the audit table;
- audit-write outage fails closed and leaves no usable newly issued session;
- logout revokes the Shoir-IE session and then closes the IdP session.

Keep T098 unverified until the run evidence and independent security review are attached.

## 6. Configure and accept T096 — first real ERP/provider

T096 is not made live by entering a URL. Select exactly one provider product/edition and an authorized read-only staging resource first. The current repository has a secure generic HTTPS GET-only REST path and product/resource contracts for SAP S/4HANA Public/Private, SAP ECC, Oracle Fusion ERP/SCM and Oracle EBS, but vendor-specific authentication/pagination transports still require a provider-specific implementation and review.

Before a live test:
1. Obtain a written staging-sandbox authorization and select the exact product, API version, resource, tenant and read-only scope.
2. Implement/review the provider-specific OAuth/token and pagination adapter behind the existing GET-only contract. Do not add write verbs.
3. Store the credential only in the staging server secret manager; configure an exact endpoint hostname/port allowlist and only the precise approved private CIDR if the approved architecture requires it.
4. Confirm TLS verification, DNS/IP pinning, redirects denied, bounded timeout/response/page/rate limits, no import-time network activity and redacted errors.
5. Use synthetic or approved non-personal records and test success, 401/403, expiry/revocation, schema drift, pagination, duplicate IDs, units/currency mapping and lineage.
6. Attach exact source SHA, redacted profile, provider/API version, test report and provider owner sign-off.

Do not mark a generic REST mock, configuration inspection or product catalogue row as a verified SAP/Oracle integration.

## 7. Configure and accept T097 — hosted API/SDK

T097 is currently a local plugin registry/contract-inspection foundation, not a public hosted API or published SDK. Before claiming delivery, the owner must select the first use case/provider and authorize an external staging consumer. Then:
1. provision an approved API hostname, DNS, TLS and gateway/runtime;
2. approve an OpenAPI contract with stable errors/versioning;
3. implement tenant-bound OAuth/OIDC or service identity, narrow scopes, expiry/revocation/key rotation, request/time/size limits, rate limits, idempotency and replay controls;
4. implement the actual reviewed handler for the chosen resource (metadata-only plugins remain non-executable);
5. publish a versioned SDK to a private/test channel and install it from an external test client;
6. test missing/expired/wrong-audience credentials, scope denial, cross-tenant denial, rate limiting, pagination, idempotency, audit/redaction and SDK compatibility;
7. collect endpoint/TLS, OpenAPI checksum, redacted requests/responses, SDK checksum/client output and independent security review.

The provider and public API design choice may trigger additional repository implementation after the first external integration is selected. Do not represent T097 as a configuration-only task.

## 8. Configure and accept T099 — backup and disaster recovery

A workspace JSON export is not a database backup, PITR guarantee or Storage object backup. In Supabase Dashboard, inspect the actual plan and project settings; do not infer backup capability from plan labels.

For staging:
1. record the configured database backup/PITR schedule, recovery window and retention;
2. define and approve RPO and RTO;
3. establish an encrypted off-project database backup/export in a separate failure domain, with access controls and key custody/rotation;
4. separately back up all required Supabase Storage object bytes (database backups do not include Storage API file bodies); produce a path/size/SHA-256 manifest;
5. inventory Edge secrets, IdP credentials, DNS/TLS and Streamlit configuration in the approved secret manager;
6. provision an isolated disposable restore target that has no production write path or production provider connection;
7. restore database and Storage bytes, check migration/schema/grants/RLS/RPC, object checksums and tenant isolation;
8. connect a disposable staging app and test login, entitlements, workspace, dataset versioning, Digital Thread and exports;
9. measure actual RPO/RTO, partial-restore/failure rollback and obtain independent infrastructure/security reviewer sign-off.

Never test recovery by deleting, pausing, resetting or overwriting production.

## 9. Staging deployment and authenticated operational acceptance

Only after sections 1–8 prerequisites that apply to the selected features have independent review and staging recovery readiness:
1. confirm exact candidate SHA, eight CI checks green and PR #232 independent approval/thread resolution;
2. confirm the actual staging migration ledger and pending migrations with the authorized DB operator (the connected database-history query can fail independently of project health);
3. apply the approved staging migrations in timestamp order, including `20261120115000` and the OIDC audit migration only if OIDC is being accepted;
4. deploy the matching persistence Edge source to staging and record function version/hash;
5. recheck RLS, table grants, RPC grants, Security/Health/Performance Advisors and Storage bucket policy;
6. confirm staging banner, candidate build marker and E2E secrets;
7. run GitHub Actions → **Authenticated release gate**, selecting branch `feat/shoir-ie-release-hardening-20261105` (the workflow code must come from the candidate branch; target URLs/keys must remain staging-only);
8. download `shoir-ie-authenticated-release-evidence` and review exact SHA, browser diagnostics and all role/tier/session/workspace cases;
9. complete the T020 owner/admin lease acceptance: preview first, use only synthetic 48-hour-old orphan objects, test finalizer/sweeper/reference-writer lease conflicts, expiry and token-matched release, dual-ledger no-reference, intent/completion events, generic platform-record rejection of cross-workspace T020 paths, the 50-delete cap and cross-workspace denial. Do not run deletion until this operator rehearsal is explicitly approved;
10. complete data import → validate → calculate → simulate → optimize → decide → compare → export → reopen/verify journeys, including fresh login and tenant isolation; verify workbook/XLSX, PDF and PPTX artifacts; visually inspect authenticated desktop 1440px, tablet 768px and mobile 390px, including Arabic/RTL where supported;
11. retain redacted evidence and have qualified reviewers sign the tool-specific calculations, Industrial Engineering methods, security and export results.

No module or tool moves to `VERIFIED_WORKING` on the basis of source presence, an AppTest route, or synthetic examples alone.

## 10. Independent review and production release approval

### Required release reviewers

Record independent named approvals (not self-certification) for:
- Industrial Engineering method/calculation validity and operational fitness;
- security, identity, tenant isolation, Edge/RLS/RPC/storage policies and vulnerability findings;
- infrastructure, database migration, backup/restore and measured RPO/RTO;
- Saudi privacy/legal compliance, actual operator identity, processor/subprocessor contracts, hosting/cross-border transfers, lawful basis, retention, data-subject requests, incident process, support and refund obligations;
- product owner release acceptance and explicit production authorization.

### GitHub branch protection

Both `main` and `staging-e2e-20261019` currently have active repository rulesets requiring PR workflow and at least one independent approval, latest-push approval and resolved review threads, with no bypass actors. Staging requires eight CI contexts. Main currently requires only `test`, `edge-function`, `engine-regression` and `security-quality`; before a production PR, add/verify `clean-postgres-migration-replay`, `postgres-transaction-contract`, `production-v9-security-backport`, and `excel-intelligence` as required contexts. The connected GitHub integration can inspect rulesets but cannot edit repository administration settings; a repository administrator must make and verify that change.

### Staging-to-production path

1. Complete and independently sign off all staging evidence. Keep PR #232 draft until all staging acceptance criteria are satisfied.
2. Obtain the required independent approval on the latest PR #232 push, resolve every review thread, and have the release owner explicitly authorize the staging merge. Merge only after required branch checks pass.
3. Create a separate production release PR from the accepted staging release to `main`. Do not merge PR #232 directly into `main`.
4. Strengthen and verify the main ruleset before production review. Require all production-critical CI contexts, an independent reviewer, latest-push approval and resolved threads; test that deliberately failing required checks block merge.
5. Reconcile production's historical migration ledger and schema carefully; do not blindly replay or rewrite account/legal/referral migrations. Produce a reviewed production-specific migration plan, exact Edge Function compatibility plan, deployment ordering and tested rollback.
6. Verify production backup/PITR and independent Storage-object backup/restore first. Schedule a production change window; capture before-state versions/hashes and smoke/rollback criteria.
7. Present the exact production source SHA, migration plan, function version/hash, review sign-offs, security/privacy/legal approvals, recovery metrics, customer communications/support readiness and rollback procedure for explicit release-owner authorization.
8. Only after that explicit authorization may an administrator execute production changes. Recheck function health, CORS/origin behavior, auth, subscription and legal acceptance schema, RLS/grants/RPCs, workspace persistence and critical journeys. Attach post-deploy evidence and monitor the agreed rollback window.

No production work is authorized by this runbook. A green staging run does not automatically authorize a production deployment or customer sale.

## 11. Final completion checklist and evidence bundle

The release owner should be able to locate, for one exact candidate SHA:
- all eight green CI runs and their artifacts (JUnit, migration replay, Deno tests, dependency/secret scan, Excel checks and visual/export renders);
- independent review/approval and resolved PR threads;
- applied staging migration list, RLS/grant/RPC/advisor report and deployed Edge version/hash;
- authenticated disposable-account release gate evidence and 3-viewport browser traces/screenshots;
- T020 lifecycle lease and Storage audit rehearsal evidence;
- per-tool reference calculations, boundary/units/provenance/persistence/tenant/export acceptance and qualified Industrial Engineering sign-off;
- provider-backed T096, externally consumed T097, OIDC/MFA T098 and full database+Storage T099 acceptance evidence;
- Saudi legal/privacy and commercial-operator approvals;
- separate main branch protections, production PR approval, approved deployment/rollback record and production post-deploy verification.

Until every mandatory item has evidence, the final decision remains **BETA / NO-GO**. Preserve all failures/skips as blockers and do not advertise measured savings, ROI, live integrations, disaster-recovery readiness or legal clearance without the underlying evidence.
