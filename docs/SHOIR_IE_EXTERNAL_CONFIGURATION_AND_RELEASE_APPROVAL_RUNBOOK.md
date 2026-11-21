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

[supabase]
edge_url = "https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence"
publishable_key = "PASTE_THE_STAGING_PUBLISHABLE_KEY_HERE"
```

Replace the placeholder only in Streamlit's secret editor. The app reads `[shoir].environment`, `[supabase].edge_url` and `[supabase].publishable_key`. The equivalent environment names are `SHOIR_ENVIRONMENT=staging`, `SHOIR_SUPABASE_EDGE_URL` and `SHOIR_SUPABASE_PUBLISHABLE_KEY`. The Edge URL must be the full `/functions/v1/shoir-persistence` endpoint, not only the project root.

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

If the identities already exist, do not blindly provision again. Inspect the provisioner's state file and staging registration queue. If passwords do not match Actions secrets, use the documented Python recovery helper `scripts/recover_staging_e2e_credentials.py` to reset only the seven disposable identities. Run it from PowerShell on Windows with Python and GitHub CLI installed; there is no separate `.ps1` wrapper. It is pinned to staging and does not create/delete accounts or modify `sho`.

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

Do not add the service-role key, DB password or any OIDC client secret to Actions for this gate. Its preflight validates the staging target and the presence of the variables before browser navigation. The full validation workflow's hosted browser smoke now uses this exact variable as its sole target; it never falls back to the production Streamlit hostname. If it is missing or malformed, the job fails immediately with a configuration diagnostic rather than silently skipping or probing production.

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

The Workbench T098 readiness inspector reads these nested Streamlit `[auth]` settings and reports whether their syntax/configuration is present without exposing values. It cannot inspect the separate Supabase Edge Function secret manager; its result explicitly labels Edge verifier configuration as `NOT_INSPECTABLE_FROM_STREAMLIT`. A “Streamlit configuration ready” result is not evidence that the Edge secrets exist, that the provider accepted authentication, that MFA claims are correct, or that the audit migration is deployed.

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

T096 is not made live by entering a URL. Select exactly one provider product/edition and an authorized read-only staging resource first.

**Repository implementation now present:** the release candidate has a server-side OAuth 2.0 client-credentials transport for SAP S/4HANA Cloud Public/Private OData reads. It uses an opaque server-side credential reference, bounded access-token caching, exact HTTPS host allowlisting, DNS/IP pinning, TLS verification, redirects denied, bounded response sizes/timeouts, and sanitized failures. The existing T096 Workbench has an explicit provider-read action. It accepts only a connection ID and logical resource key; connection profiles, field mappings, credential values and host allowlists remain in server-side Streamlit configuration. It verifies the active Shoir-IE session using the staging Edge Function and, for a shared organization workspace, checks the Owner/Admin `manage` permission in the Edge/database path before making a provider request. The Workbench returns only status, record counts, mapping version and digest; it does not display or persist raw provider records.

**Oracle correction from current official documentation:** the normal Oracle Fusion Applications REST platform (for example, `/fscmRestApi/...`) does not accept the generic Client Credentials grant. Oracle documents Client Credentials only for Spectra services. Fusion Applications non-interactive access requires a provider-configured JWT user-assertion flow (with a separately signed client assertion) or another supported flow. Shoir-IE does not yet implement that Oracle JWT assertion exchange, so the candidate's Oracle Fusion ERP/SCM transport now fails closed before resolving credentials or making an HTTP request. Do not enter a client secret and expect a standard Fusion Applications REST read to work.

The only currently implemented client-credentials provider-read transport is SAP S/4HANA Cloud Public/Private. Oracle Fusion ERP/SCM remain specification/configuration work until the provider-specific JWT user-assertion and client-assertion exchange is implemented and independently reviewed. **SAP ECC and Oracle E-Business Suite are also deliberately refused** until their distinct legacy adapters are implemented and reviewed. No live provider acceptance or scheduled integration is claimed.

### 6.1 Select and authorize the first provider

1. Obtain written authorization from the ERP tenant owner for a non-production sandbox, exact API version, read-only resource/scope, pagination contract and synthetic/non-personal test records.
2. For the current transport, select SAP S/4HANA Cloud Public/Private only. Select Oracle Fusion ERP/SCM only after a separate reviewed JWT user-assertion adapter is committed. Do not configure SAP ECC or Oracle EBS as a cloud-product substitute.
3. Confirm the exact service root, token issuer URL and approved DNS hostnames/ports with the vendor/tenant owner. Do not guess public hostnames or use production ERP endpoints.

### 6.2 Configure server-side staging settings

Configure these **root-level Streamlit staging secrets** in the dedicated staging app only. They are read by the Streamlit server and are never returned to the browser or written to a workbook.

```toml
# Illustrative shape only. Replace every placeholder in Streamlit's secret editor.
# Do not commit real values or paste credentials into chat or Actions.
SHOIR_ERP_CONNECTIONS_JSON = '''
{
  "sap-plant-read": {
    "connection": {
      "product_id": "SAP_S4HANA_CLOUD_PUBLIC",
      "workspace_id": "EXACT_ACTIVE_WORKSPACE_ID",
      "tenant_ref": "OPAQUE_NON_SECRET_TENANT_REFERENCE",
      "base_url": "https://APPROVED-ERP-HOST/APPROVED-SERVICE-ROOT",
      "credential_ref": "vault://shoir/staging/sap-plant-read",
      "enabled": true,
      "read_only": true
    },
    "bindings": {
      "production_orders": {
        "source_path": "APPROVED_ODATA_SERVICE/APPROVED_PRODUCTION_ORDER_RESOURCE",
        "records_path": "value",
        "entity_type": "Order",
        "id_path": "ProductionOrder",
        "field_map": {"order_number": "ProductionOrder"},
        "required_fields": ["order_number"],
        "mapping_version": "1",
        "max_records": 1000,
        "max_pages": 10
      }
    }
  }
}
'''
SHOIR_ERP_CREDENTIALS_JSON = '''
{
  "vault://shoir/staging/sap-plant-read": {
    "token_url": "https://APPROVED-IDP-HOST/APPROVED-TOKEN-PATH",
    "client_id": "STAGING-OAUTH-CLIENT-ID",
    "client_secret": "STAGING-OAUTH-CLIENT-SECRET",
    "scope": "APPROVED_READ_ONLY_SCOPE"
  }
}
'''
SHOIR_ERP_ALLOWED_HOSTS = "APPROVED-ERP-HOST;APPROVED-IDP-HOST"
SHOIR_ERP_APPROVED_PRIVATE_CIDRS = ""
SHOIR_ERP_TIMEOUT_SECONDS = "8"
```

The example is a schema template, not a working vendor endpoint or OAuth scope. Create a separate connection entry and credential reference for each approved provider/resource. `workspace_id` must exactly match the active personal or organization workspace the operator is using. Only include exact host[:port] values required by the endpoint and token issuer. Leave the private CIDR setting empty unless the network/security owner has approved specific private ranges. The timeout must be between 0.5 and 10 seconds.

Never place these secrets in GitHub Actions, repository files, the public API SDK, client-side JSON inputs or chat. The Workbench input contains only the opaque `connection_id` and `resource_key`.

### 6.3 Hosted acceptance

1. Verify configuration inspection makes no DNS/HTTP call; verify the explicit action is unavailable outside the staging environment.
2. Test a successful read and negative cases: missing/expired session, inactive account, insufficient tier, wrong workspace, non-Owner/Admin shared workspace, disabled/write-enabled connection, unknown credential reference, unapproved hostname, DNS/private-IP policy violation, invalid token, 401/403, 429, redirect, oversized/malformed response and expired token.
3. Validate provider pagination, source IDs, duplicate/conflicting IDs, field maps, required fields, units/currency, timezone and source timestamps against synthetic/approved records.
4. Confirm the Workbench exposes no token/secret or raw provider records, and no provider data is persisted by the configuration-check action.
5. If actual import is later required, design it as a separate reviewed workflow with explicit consent, dataset lineage, retention and deletion semantics. This T096 verification action is not an importer or continuous sync.
6. Attach exact source SHA, redacted connection/resource profile, vendor/API version, logs, test outputs, DNS/TLS evidence and provider owner/security sign-off.

Do not mark a generic REST mock, configuration inspection, synthetic transport test or product catalogue row as a verified SAP/Oracle integration. T096 remains `EXTERNAL_CONFIGURATION_REQUIRED` until an actual authorized provider sandbox test and independent review pass.

## 7. Configure and accept T097 — hosted API/SDK

The repository now includes an initial typed JavaScript/TypeScript beta client under `sdk/typescript`, a v1 OpenAPI contract draft and a backward-compatible Edge API version guard. It supports three existing session-authenticated actions: platform record list, platform record save and workspace load. The package is not published and is not a public customer API. It reuses the existing Shoir-IE session and Supabase publishable key; it does not issue API keys or create a service-to-service identity.

Before claiming delivery, the owner must select the first use case and authorize an external staging consumer. Then:
1. provision an approved API hostname, DNS, TLS and hosted gateway/runtime;
2. review the OpenAPI v1 contract against the hosted implementation and establish stable error/versioning and compatibility policy;
3. implement tenant-bound OAuth/OIDC or service identity, narrow scopes, expiry/revocation/key rotation, request/time/size limits, per-tenant rate limits, idempotency and replay controls;
4. implement the actual reviewed handler for the chosen external resource (metadata-only plugin manifests remain non-executable);
5. publish the SDK to an approved private/test package channel and install/consume it from an external test client;
6. test missing/expired/wrong-audience credentials, scope denial, cross-tenant denial, rate limiting, pagination, idempotency, audit/redaction and SDK compatibility;
7. collect endpoint/TLS, OpenAPI checksum, redacted requests/responses, SDK checksum/client output and independent security review.

Do not represent the repository beta SDK or existing persistence Edge Function as a published public API. T097 remains `EXTERNAL_CONFIGURATION_REQUIRED` until hosted gateway, identities, quotas, external client use and independent review are accepted.

## 8. Configure and accept T099 — backup and disaster recovery

A workspace JSON export is not a database backup, PITR guarantee or Storage object backup. In Supabase Dashboard, inspect the actual plan and project settings; do not infer backup capability from plan labels.

For staging:
1. record the configured database backup/PITR schedule, recovery window and retention;
2. define and approve RPO and RTO;
3. establish an encrypted off-project database backup/export in a separate failure domain, with access controls and key custody/rotation;
4. separately back up all required Supabase Storage object bytes (database backups do not include Storage API file bodies); produce a path/size/SHA-256 manifest using the repository helper after the authorized export completes:
   ```bash
   python scripts/shoir_storage_recovery_manifest.py create --root ./protected-storage-export --manifest ./protected-recovery-evidence/storage-manifest.json
   python scripts/shoir_storage_recovery_manifest.py verify --root ./isolated-restored-storage --manifest ./protected-recovery-evidence/storage-manifest.json
   ```
   The helper hashes local files only; it does not export Supabase objects, encrypt the backup, sign the manifest or validate database consistency. Keep export and manifest outside Git and public artifacts.
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
3. apply the approved staging migrations in timestamp order, including `20261120115000` and `20261120130000` plus the OIDC audit migration only if OIDC is being accepted;
4. deploy the matching persistence Edge source to staging and record function version/hash;
5. recheck RLS, table grants, RPC grants, Security/Health/Performance Advisors and Storage bucket policy;
6. confirm staging banner, candidate build marker and E2E secrets;
7. run GitHub Actions → **Authenticated release gate**, selecting branch `feat/shoir-ie-release-hardening-20261105` (the workflow code must come from the candidate branch; target URLs/keys must remain staging-only);
8. download `shoir-ie-authenticated-release-evidence` and review exact SHA, browser diagnostics and all role/tier/session/workspace cases;
9. complete the T020 owner/admin lease acceptance: preview first, use only synthetic 48-hour-old orphan objects, test finalizer/sweeper/reference-writer lease conflicts, renewal by the active token, stale-token renewal/commit rejection, transaction-fenced dataset/generic-record metadata writes, expiry and token-matched release, dual-ledger no-reference, intent/completion events, generic platform-record rejection of cross-workspace T020 paths, the 50-delete cap and cross-workspace denial. Do not run deletion until this operator rehearsal is explicitly approved;
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

Both `main` and `staging-e2e-20261019` have active repository rulesets requiring PR workflow and at least one independent approval, latest-push approval and resolved review threads, with no bypass actors. Staging requires eight CI contexts. Main currently requires only `test`, `edge-function`, `engine-regression` and `security-quality`; it is not production-strength until `clean-postgres-migration-replay`, `postgres-transaction-contract`, `production-v9-security-backport`, and `excel-intelligence` are also required.

A repository administrator can apply the additive, idempotent change from an administrator-authenticated computer with GitHub CLI installed:

```bash
gh auth status
python scripts/strengthen_main_ruleset.py
python scripts/strengthen_main_ruleset.py --apply
```

The first invocation is dry-run only. The second requires repository Administration:write access, reads the current main ruleset, refuses to proceed if its branch target, active enforcement, no-bypass, strict checks or independent-review protections have drifted, adds only the four missing contexts, and verifies the returned ruleset. Do not paste a PAT or secret into chat, files, Actions variables or command-line arguments. Afterward, open GitHub Settings → Rules → Protect main — release gates and confirm all eight contexts, one independent review, latest-push approval, resolved threads and no bypass actors. The connected GitHub integration can inspect rulesets but cannot apply this admin-only change itself.

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
