# Authenticated release gate

This workflow is an **on-demand non-production staging integration check**. It is deliberately not triggered by ordinary pushes or pull requests because it contacts the configured Edge Function, creates temporary server sessions and performs a small save/restore probe against a dedicated test account. It is fail-closed: the Edge API target must be the approved staging Supabase project (hfhrosthswcybccepmak), and the browser target must match the explicitly configured staging Streamlit hostname. The known production Supabase project and public production Streamlit host are rejected.

## Safety requirements

Every account used by this workflow must be a disposable test identity whose username starts with `shoir-e2e-`. The runner refuses other usernames. Never use the master administrator, a paying customer, or an account with real workspace data.

Provision these distinct accounts in the approved staging environment through the supported account registration/approval lifecycle before running the workflow. Do not insert account rows directly with SQL or reuse production identities:

| Test identity | Required state | Purpose |
|---|---|---|
| Active | Enabled, non-admin, Enterprise Plus by default | Login, workspace round-trip, session revocation and cross-owner denial |
| Second | Enabled, non-admin, distinct from Active | Prove a valid session cannot read or overwrite another account's workspace |
| Starter | Enabled, non-admin, Starter tier | Confirm tier returned by the authoritative auth service and deny administrator API access |
| Expired | Enabled, non-admin, subscription expiry in the past | Confirm renewal-only login, deny workspace read/write, and reject renewal submission without a payment reference |
| Inactive (optional) | Disabled test account with otherwise valid credentials | Confirm inactive login does not issue a session |

The Active test workspace should be a small JSON object and contain no real customer or business data. During the round-trip probe, the script records its prior serialized state, writes a unique temporary marker, logs in again to read that marker, and restores the original state before revoking test sessions. A workspace that is not a JSON object or exceeds 1 MB is not overwritten. Review the JSON evidence artifact for any `FAIL` result or restore warning.

## Staging Streamlit configuration — required before any login test

Create a separate Streamlit Cloud app for staging, then set these **app secrets** in that staging app's Manage app → Settings → Secrets panel. Use the staging publishable key from the staging Supabase dashboard, not the production key.

```toml
[shoir]
environment = "staging"

[supabase]
edge_url = "https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence"
publishable_key = "PASTE_THE_STAGING_PUBLISHABLE_KEY_HERE"
```

The placeholder above is documentation only; replace it in Streamlit's secret editor and never commit the key to Git. The equivalent environment variables are `SHOIR_ENVIRONMENT=staging`, `SHOIR_SUPABASE_EDGE_URL`, and `SHOIR_SUPABASE_PUBLISHABLE_KEY`.

In staging mode the app validates the exact staging Edge host and refuses to start if the staging URL/key are missing or point elsewhere. It also refuses direct database DSNs (`database.url`, `postgresql.url`, `supabase.url`, `SHOIR_DATABASE_URL`, `SUPABASE_DB_URL`, or `DATABASE_URL`) so a leftover production database connection cannot silently bypass the staging Edge Function. The sign-in page must display **STAGING TEST ENVIRONMENT**. The authenticated browser and module-matrix tests check this banner *before entering any username or password*, so they abort without submitting credentials if the staging marker is missing.

## One-time staging administrator bootstrap

The historical administrator seed migration is intentionally a no-op. If the isolated staging project does not yet have an administrator, use the one-time helper in `scripts/bootstrap_staging_admin.py` from a trusted computer:

```bash
python scripts/bootstrap_staging_admin.py
```

The helper is hard-pinned to staging project `hfhrosthswcybccepmak` and refuses to overwrite an existing `sho` identity. It prompts without echoing for a staging-only Supabase server secret/service-role key and a unique password of at least 16 characters, then requires typing an explicit staging confirmation phrase. It never prints or saves either secret. The key is used locally for a single verified bootstrap and must not be committed, pasted into chat, or added to GitHub Actions.

If the helper says the `sho` identity already exists, stop and use the approved administrator-recovery procedure rather than rerunning bootstrap. Keep the staging admin password in a password manager because the E2E provisioner below requires it. Never use the admin password as a test-account password.

## Provision the six disposable E2E identities

After the staging app configuration and staging administrator are ready, run this from the repository root on a trusted computer:

```bash
python scripts/provision_staging_e2e_accounts.py
```

The helper is hard-pinned to the staging project, rejects the known production project, asks for the staging publishable key, the staging service-role/secret key, and the staging administrator password via hidden prompts, and requires a confirmation phrase. It checks that all six planned usernames are unused before making changes. It creates each test account via `register_request` and approves it via the normal admin approval action. The transaction references are explicitly synthetic **no-charge staging fixtures**; no payment service is contacted.

Only the intentionally expired test fixture's `subscription_expires_at` is updated after approval, using the staging server key, so the expired-login/renewal-only path can be verified. The helper verifies all five active accounts' tier/login results and the expired account's renewal-only result, then revokes verification sessions. It does not use production, does not overwrite matching identities, and does not print keys, passwords, session tokens, or API response bodies.

The script writes six random test passwords to `.staging-e2e-credentials.json` in the repository root, with file permissions restricted to the current user; the filename is git-ignored. Review the `github_actions_secret_map` in this file to copy each username/password into the matching Actions secrets. Keep the file private until all secrets are set, then securely delete it. If provisioning stops part-way, the file records each account status; inspect the staging admin queue and that file before retrying. **Do not rerun to create duplicate accounts.**

## GitHub Actions configuration

Add these as **GitHub Actions secrets** under repository Settings → Secrets and variables → Actions → Secrets:

- `SHOIR_E2E_EDGE_URL` — the configured `shoir-persistence` Edge Function endpoint for the target environment.
- `SHOIR_E2E_PUBLISHABLE_KEY` — the publishable key for the approved staging environment. Do **not** provide a service-role key.
- `SHOIR_E2E_APP_URL` — the full HTTPS URL of the dedicated staging Streamlit app (not `https://shoir-ie-app.streamlit.app/`).
- `SHOIR_E2E_ACTIVE_USERNAME`, `SHOIR_E2E_ACTIVE_PASSWORD`
- `SHOIR_E2E_SECOND_USERNAME`, `SHOIR_E2E_SECOND_PASSWORD`
- `SHOIR_E2E_STARTER_USERNAME`, `SHOIR_E2E_STARTER_PASSWORD`
- `SHOIR_E2E_EXPIRED_USERNAME`, `SHOIR_E2E_EXPIRED_PASSWORD`
- `SHOIR_E2E_MODULE_USERNAME`, `SHOIR_E2E_MODULE_PASSWORD` — a distinct Enterprise Plus test account used only for route/default-state module traversal.
- `SHOIR_E2E_RESEARCH_MODULE_USERNAME`, `SHOIR_E2E_RESEARCH_MODULE_PASSWORD` — a distinct Research Pack add-on test account for the modules unavailable to the base-tier matrix.

Add this as a GitHub Actions **variable** under Settings → Secrets and variables → Actions → Variables:

- `SHOIR_E2E_EXPECTED_STAGING_APP_HOST` — the exact hostname of the staging Streamlit app, for example `your-staging-app.streamlit.app` (hostname only; no scheme or path).

Optional inactive-account verification uses `SHOIR_E2E_INACTIVE_USERNAME` and `SHOIR_E2E_INACTIVE_PASSWORD` together. Set the Actions **variable** `SHOIR_E2E_ACTIVE_EXPECTED_TIER` if the Active test account should be a tier other than `Enterprise Plus Tier ($399)`. There is intentionally no default application URL: missing or mismatched staging configuration stops the tests before browser navigation.

Do not put passwords or tokens in workflow inputs, source files, issues, pull requests, or chat messages. Reports deliberately omit usernames, passwords, tokens, workspace payloads, and response bodies.

## Running and evidence

1. Confirm a dedicated staging Streamlit deployment exists and that its own app secrets point to staging Supabase project `hfhrosthswcybccepmak` (not production). Confirm the Edge Function endpoint and publishable key refer to that same project. Changing the approved staging project requires an explicit reviewed code change.
2. Confirm the configured Edge Function and Streamlit deployment contain the revisions being tested.
3. Open GitHub Actions → **Authenticated release gate** → **Run workflow**, then select the branch containing the release-candidate commit. For this unmerged PR, select `staging-e2e-20261019` (PR #165). Do not select `main` until these changes have landed there: `workflow_dispatch` runs the workflow code from the selected branch, so choosing `main` would test the older base revision instead of this candidate.
4. Review the run summary and download `shoir-ie-authenticated-release-evidence`.
5. Record the run URL, commit SHA, timestamp, target environment, and each case's result in `docs/RELEASE_VERIFICATION_MATRIX.md`. Treat any failed cleanup or workspace restore as a release blocker.

The gate checks active/invalid-password/expired authentication, dedicated-account tier metadata, server-side non-admin denial, owner-bound workspace access, workspace save/re-login/restore, renewal-only restrictions and reference validation, server logout revocation, and an authenticated browser route to the Excel module. It also runs `scripts/authenticated_module_matrix.py` against the 96-name `docs/MODULE_TIER_INVENTORY.csv`: Enterprise Plus routes are exercised using a dedicated Enterprise Plus test account, and Research Pack-only entries are exercised using a distinct Research Pack test account. The script records per-module route/default-state rendering outcomes and fails closed on missing inventory entries, blank content, fatal renderer markers, or horizontal overflow. The Edge login path consumes server-side buckets: 8 attempts per username per 10 minutes and, when the trusted Cloudflare client-IP header is present, 30 attempts per IP per 10 minutes. A successful login clears that user's bucket; the IP bucket expires naturally after the window. The throttle table and RPC are restricted to service_role, and login fails closed with 503 if the throttle RPC is unavailable. Production already records the login-throttle SQL under version `20261019124815`. The production and staging ledger statements have matching fingerprints; the tracked source filename now reflects the production version. This does not imply the separate atomic subscription-decision migration or its Edge Function dependency is present in production. For an intentional live limiter test, set the Actions variable `SHOIR_E2E_VERIFY_LOGIN_THROTTLE=true`; it generates nine invalid attempts against a random synthetic username (never a real account). This consumes nine attempts from the ephemeral runner's IP bucket, so do not run the optional probe repeatedly inside one 10-minute window.

## Explicit limits

This gate does not approve or decline renewal requests, change any subscription, run a penetration test, restore a database backup, or verify every one of the 96 modules' calculations and file-export round-trips. Those require separate test-environment workflows and evidence. A successful run improves release confidence, but must not be described as an independent security certification.


## Module-rendering matrix

The module-rendering matrix validates authenticated route selection and safe default/empty-state rendering for every source inventory entry. It is not calculation correctness proof, valid-input result proof, import/export round-trip proof, direct service authorization proof, tenant-isolation proof, or production readiness evidence; those remain separate acceptance cases. The account usernames must be unique `shoir-e2e-*` identities and must never be the master administrator or a customer. Module-matrix workspaces are disposable and must contain no industrial/customer data.
