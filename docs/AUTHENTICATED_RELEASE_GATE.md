# Authenticated release gate

This workflow is an **on-demand production integration check**. It is deliberately not triggered by ordinary pushes or pull requests because it contacts the configured Edge Function, creates temporary server sessions and performs a small save/restore probe against a dedicated test account.

## Safety requirements

Every account used by this workflow must be a disposable test identity whose username starts with `shoir-e2e-`. The runner refuses other usernames. Never use the master administrator, a paying customer, or an account with real workspace data.

Provision these distinct accounts in the selected test environment before running the workflow:

| Test identity | Required state | Purpose |
|---|---|---|
| Active | Enabled, non-admin, Enterprise Plus by default | Login, workspace round-trip, session revocation and cross-owner denial |
| Second | Enabled, non-admin, distinct from Active | Prove a valid session cannot read or overwrite another account's workspace |
| Starter | Enabled, non-admin, Starter tier | Confirm tier returned by the authoritative auth service and deny administrator API access |
| Expired | Enabled, non-admin, subscription expiry in the past | Confirm renewal-only login, deny workspace read/write, and reject renewal submission without a payment reference |
| Inactive (optional) | Disabled test account with otherwise valid credentials | Confirm inactive login does not issue a session |

The Active test workspace should be a small JSON object and contain no real customer or business data. During the round-trip probe, the script records its prior serialized state, writes a unique temporary marker, logs in again to read that marker, and restores the original state before revoking test sessions. A workspace that is not a JSON object or exceeds 1 MB is not overwritten. Review the JSON evidence artifact for any `FAIL` result or restore warning.

## GitHub Actions configuration

Add these as **GitHub Actions secrets** under repository Settings → Secrets and variables → Actions → Secrets:

- `SHOIR_E2E_EDGE_URL` — the configured `shoir-persistence` Edge Function endpoint for the target environment.
- `SHOIR_E2E_PUBLISHABLE_KEY` — the publishable key for that same environment. Do **not** provide a service-role key.
- `SHOIR_E2E_ACTIVE_USERNAME`, `SHOIR_E2E_ACTIVE_PASSWORD`
- `SHOIR_E2E_SECOND_USERNAME`, `SHOIR_E2E_SECOND_PASSWORD`
- `SHOIR_E2E_STARTER_USERNAME`, `SHOIR_E2E_STARTER_PASSWORD`
- `SHOIR_E2E_EXPIRED_USERNAME`, `SHOIR_E2E_EXPIRED_PASSWORD`\n- `SHOIR_E2E_MODULE_USERNAME`, `SHOIR_E2E_MODULE_PASSWORD` — a distinct Enterprise Plus test account used only for route/default-state module traversal.\n- `SHOIR_E2E_RESEARCH_MODULE_USERNAME`, `SHOIR_E2E_RESEARCH_MODULE_PASSWORD` — a distinct Research Pack add-on test account for the modules unavailable to the base-tier matrix.

Optional inactive-account verification uses `SHOIR_E2E_INACTIVE_USERNAME` and `SHOIR_E2E_INACTIVE_PASSWORD` together. Set the Actions **variable** `SHOIR_E2E_ACTIVE_EXPECTED_TIER` if the Active test account should be a tier other than `Enterprise Plus Tier ($399)`. The browser test defaults to `https://shoir-ie-app.streamlit.app/`; override that with secret `SHOIR_E2E_APP_URL` only when testing an approved staging deployment.

Do not put passwords or tokens in workflow inputs, source files, issues, pull requests, or chat messages. Reports deliberately omit usernames, passwords, tokens, workspace payloads, and response bodies.

## Running and evidence

1. Confirm the configured Edge Function and Streamlit deployment contain the revisions being tested.
2. Open GitHub Actions → **Authenticated release gate** → **Run workflow** on `main`.
3. Review the run summary and download `shoir-ie-authenticated-release-evidence`.
4. Record the run URL, commit SHA, timestamp, target environment, and each case's result in `docs/RELEASE_VERIFICATION_MATRIX.md`. Treat any failed cleanup or workspace restore as a release blocker.

The gate checks active/invalid-password/expired authentication, dedicated-account tier metadata, server-side non-admin denial, owner-bound workspace access, workspace save/re-login/restore, renewal-only restrictions and reference validation, server logout revocation, and an authenticated browser route to the Excel module. It also runs `scripts/authenticated_module_matrix.py` against the 96-name `docs/MODULE_TIER_INVENTORY.csv`: Enterprise Plus routes are exercised using a dedicated Enterprise Plus test account, and Research Pack-only entries are exercised using a distinct Research Pack test account. The script records per-module route/default-state rendering outcomes and fails closed on missing inventory entries, blank content, fatal renderer markers, or horizontal overflow. The Edge login path consumes server-side buckets: 8 attempts per username per 10 minutes and, when the trusted Cloudflare client-IP header is present, 30 attempts per IP per 10 minutes. A successful login clears that user's bucket; the IP bucket expires naturally after the window. The throttle table and RPC are restricted to service_role, and login fails closed with 503 if the throttle RPC is unavailable. Apply migration `20261019123300_server_side_login_rate_limits.sql` before deploying the Edge Function revision that calls it. For an intentional live limiter test, set the Actions variable `SHOIR_E2E_VERIFY_LOGIN_THROTTLE=true`; it generates nine invalid attempts against a random synthetic username (never a real account). This consumes nine attempts from the ephemeral runner's IP bucket, so do not run the optional probe repeatedly inside one 10-minute window.

## Explicit limits

This gate does not approve or decline renewal requests, change any subscription, run a penetration test, restore a database backup, or verify every one of the 96 modules' calculations and file-export round-trips. Those require separate test-environment workflows and evidence. A successful run improves release confidence, but must not be described as an independent security certification.


## Module-rendering matrix

The module-rendering matrix validates authenticated route selection and safe default/empty-state rendering for every source inventory entry. It is not calculation correctness proof, valid-input result proof, import/export round-trip proof, direct service authorization proof, tenant-isolation proof, or production readiness evidence; those remain separate acceptance cases. The account usernames must be unique `shoir-e2e-*` identities and must never be the master administrator or a customer. Module-matrix workspaces are disposable and must contain no industrial/customer data.
