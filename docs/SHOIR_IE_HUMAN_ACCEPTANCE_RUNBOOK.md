# Shoir-IE Human Acceptance and Release Runbook

**Purpose:** Complete the remaining human-only, account-backed and hosted acceptance steps after the repository-side work in PR #232.  
**Last inspected candidate:** `d1a289106f7a4b29f9240156c9776d74a3bc88a3` (this document is being added on top of that candidate; always use the SHA displayed by PR #232 after this commit).  
**Current disposition:** **BETA / NO-GO**. This runbook does not authorize production deployment.

## Safety rules — read before starting

- Work only on the dedicated staging Supabase project `hfhrosthswcybccepmak` and dedicated staging Streamlit app.
- Never test with production users, customer datasets, production payment references or the protected Enterprise Admin account `sho`.
- Do not restore over the existing staging project. Recovery rehearsal must use an isolated disposable project/branch.
- Do not paste Supabase secret/service-role keys, DB passwords, IdP secrets, user passwords or session tokens into chat, PR comments, source files or workflow inputs.
- Never use the Supabase service-role/secret key as the GitHub Actions publishable key. The authenticated test workflow requires the staging publishable/anon key only.
- Do not run SQL directly to fake migration history or to create E2E users. Use the repository's migration and test-account lifecycle scripts.
- A test is accepted only when the exact candidate SHA has a completed passing result and its evidence artifact is retained. Queued, skipped, authored or locally inferred tests are not passes.
- Do not mark a capability LIVE, connected, optimal, legally cleared or workforce-ready unless the corresponding provider/evidence supports that claim.

## A. What repository-side work is already included

The candidate currently includes:
- PR CI concurrency and branch-trigger changes to prevent duplicate feature push/PR validation.
- A Data Trust correction that preserves the submitted measurement snapshot separately from normalized analysis rows.
- An Energy Flexibility regression correction that accepts a valid fallback period and rejects only genuinely infeasible schedules.
- Eight authored SQLite lifecycle tests, including savepoints, writer locking, WAL checkpoint/reopen and fresh schema initialization.
- Security workflow de-duplication and targeted Platform Tests. The main validation workflow remains the owner of the full Python test suite.
- A corrected SQLite lifecycle acceptance record and this human acceptance runbook.

These changes are committed work, **not a completed passing CI result**. The latest exact-head CI must still run.

## B. Exact-head CI and stale queue cleanup

1. Open [PR #232](https://github.com/MSJ1708/shoir-ie/pull/232).
2. Confirm its head SHA in the PR header. Use the newest SHA shown there; do not use a prior SHA from this document.
3. Open the PR's **Checks** tab. Wait for all relevant checks on that exact SHA:
   - `test` — full regression suite, compile/import/runtime and export checks in the Shoir-IE validation workflow.
   - `security-quality` — dependency/security checks.
   - `edge-function` — Edge Function format, type and security tests.
   - `engine-regression` — targeted engine tests.
   - `clean-postgres-migration-replay` — clean migration replay when migrations change.
   - `postgres-transaction-contract` — subscription transaction contract when relevant migrations change.
   - `production-v9-security-backport` — compatibility tests when its backport files change.
   - `excel-intelligence` — Excel Intelligence tests when its files change.
4. A job is acceptable only when it shows **completed / success** on the current SHA. Do not treat `skipped`, `cancelled`, `queued`, `pending` or older-head passes as success.
5. Open [GitHub Actions](https://github.com/MSJ1708/shoir-ie/actions). Filter by branch `feat/shoir-ie-release-hardening-20261105` and status `queued`. Cancel only stale runs whose displayed head SHA is not the current PR head. Do not cancel the nine current-head checks. The repository had a large historical queue at inspection; new concurrency does not retroactively remove every pre-existing run.
6. If a current-head job fails, open that job, read the failing test name and logs, fix the defect in the candidate, commit the correction, and wait for checks on the new SHA. Never edit a test merely to make a correct but inconvenient result pass.
7. When every relevant exact-head check has passed, confirm there are no skipped required checks and no unapproved skips in the JUnit artifact.

## C. Correct staging branch protection

Open [Repository Rulesets](https://github.com/MSJ1708/shoir-ie/settings/rules).

1. Open **Protect staging — acceptance gates**.
2. Under pull request rules, set **required approving reviews = 1**.
3. Keep dismissal of stale approvals enabled; keep review-thread resolution required; keep deletion and non-fast-forward protections enabled.
4. Under required status checks, enable strict/up-to-date checks and add the current GitHub Actions check contexts. For this candidate, use the exact contexts visible in the PR's Checks tab. At minimum, align staging with the four checks already required by main: `test`, `edge-function`, `engine-regression`, `security-quality`. Also require the migration replay, subscription transaction, Excel and v9 compatibility contexts whenever the corresponding files in this PR are changed and the checks are present.
5. Keep bypass actors empty. Do not add the repository owner, an automation account or an app as a bypass actor.
6. Save the ruleset and reopen it to verify the saved values.
7. Open [main protection](https://github.com/MSJ1708/shoir-ie/rules/26065188) and confirm its existing one-review/four-check/no-bypass settings remain in force.
8. Return to PR #232. Request one **independent reviewer** with write access. The PR author must not approve their own work. The reviewer must examine the full diff and approve after the latest push; resolve every review conversation.
9. Keep PR #232 as draft until exact-head checks pass and the reviewer is ready. Then use **Ready for review**. Do not merge merely because the draft flag was removed.

## D. Prove backup and recovery before staging mutation

Open the [staging Supabase project](https://supabase.com/dashboard/project/hfhrosthswcybccepmak).

1. In the dashboard, open **Database → Backups**. Record the available backup timestamp, backup type, retention and whether PITR is enabled. Capture a redacted screenshot or export that proves the backup is available.
2. Open the PITR section if enabled. Record the earliest/latest recovery point and configured retention. Do not assume that a plan automatically means PITR is enabled.
3. Open **Storage → Buckets**. Inventory each bucket and object count. Database backups do not contain the Storage object bodies; create an independent object-byte backup in a separate controlled location and generate a manifest with object path, size and SHA-256.
4. Record the Edge Function names/versions and the approved non-secret configuration that must be recreated. Back up configuration/secrets through the organization's approved secret manager; never put secret values in the evidence bundle.
5. Agree the recovery point objective (RPO) and recovery time objective (RTO) with the responsible business/operator. Record the approved target before the rehearsal.
6. Use the Supabase restore-to-new-project procedure or an approved isolated restore environment. Do **not** select the live staging project as the restore destination. Check the displayed cost and region before creating a new project; stop if the cost or data location is not approved.
7. Restore the database into that isolated project. Restore Storage object bytes separately. Reconfigure only the staging/test Edge Function, auth settings and app secrets needed for the rehearsal. Do not connect production integrations.
8. Verify table counts, schema/migration versions, RLS, grants, RPC permissions, representative records, Storage object checksums, login, workspace read/write, dataset lineage, Digital Thread and exports.
9. Measure actual elapsed restoration time and the data-loss interval. Record measured RPO/RTO and compare them to the approved targets.
10. Keep the restore logs, screenshots, object manifest/checksums and independent reviewer acceptance together. If any critical object, tenant boundary or permission is missing, the backup gate remains NOT ACCEPTED.

Reference: [Supabase Database Backups](https://supabase.com/docs/guides/platform/backups). Supabase documents that Storage object bytes are separate from database backups.

## E. Prepare the isolated staging Streamlit app

Open [Streamlit Community Cloud](https://share.streamlit.io/).

1. Create or open the dedicated staging app for repository `MSJ1708/shoir-ie`, branch `staging-e2e-20261019`, entrypoint `app.py`.
2. Do not reuse the production app at `https://shoir-ie-app.streamlit.app/`.
3. In **Manage app → Settings → Secrets**, add the staging-only configuration below, replacing the publishable-key placeholder in the Streamlit secret editor only:
   ```toml
   [shoir]
   environment = "staging"

   [supabase]
   edge_url = "https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence"
   publishable_key = "USE_THE_STAGING_PUBLISHABLE_KEY_HERE"
   ```
4. Save and allow the app to restart. Open the app and verify the sign-in screen visibly displays **STAGING TEST ENVIRONMENT** before entering credentials.
5. If the banner is missing, the app is not the correct staging target, or the Edge URL is wrong, stop. Do not enter any test credentials.

## F. Provision the seven disposable authenticated test identities

The authenticated release workflow requires seven different test identities. It will refuse usernames that do not start with `shoir-e2e-`.

Required identities:
- `shoir-e2e-active` — active, non-admin, Enterprise Plus by default.
- `shoir-e2e-second` — distinct active non-admin.
- `shoir-e2e-starter` — Starter.
- `shoir-e2e-expired` — expired subscription / renewal-only.
- `shoir-e2e-module` — separate Enterprise Plus module traversal identity.
- `shoir-e2e-research` — Research Pack add-on.
- `shoir-e2e-inactive` — disabled account with otherwise valid credentials.

1. Use a trusted workstation or an approved GitHub Codespaces environment. The repository provisioning script is not intended to run inside this chat.
2. Check that the approved staging project is active and that the staging-only Streamlit app is configured.
3. If the staging administrator identity does not exist, follow the guarded one-time procedure in `docs/AUTHENTICATED_RELEASE_GATE.md`. Do not overwrite an existing `sho` account; never use `sho` for test activity.
4. From the repository root run:
   ```bash
   python scripts/provision_staging_e2e_accounts.py
   ```
5. The script prompts for the staging publishable key, staging service-role/secret key and staging administrator password. Enter them only into the hidden local prompts. It is hard-pinned to the staging project and uses the normal registration/approval workflow.
6. The script writes `.staging-e2e-credentials.json` locally with restricted file permissions. Keep it private. If the run stops part-way, inspect its recorded account states and the staging admin queue before retrying; do not rerun blindly or create duplicate users.
7. Verify the account tiers/states with the script's output. Do not use real people/customer emails or real payment references.

## G. Configure GitHub Actions staging secrets and variables

Open [Repository Actions secrets and variables](https://github.com/MSJ1708/shoir-ie/settings/secrets/actions).

Under **Secrets**, add these names from the local provisioning file and staging app configuration. Values must never be posted to the PR or chat.

- `SHOIR_E2E_EDGE_URL`
- `SHOIR_E2E_PUBLISHABLE_KEY`
- `SHOIR_E2E_APP_URL`
- `SHOIR_E2E_ACTIVE_USERNAME`, `SHOIR_E2E_ACTIVE_PASSWORD`
- `SHOIR_E2E_SECOND_USERNAME`, `SHOIR_E2E_SECOND_PASSWORD`
- `SHOIR_E2E_STARTER_USERNAME`, `SHOIR_E2E_STARTER_PASSWORD`
- `SHOIR_E2E_EXPIRED_USERNAME`, `SHOIR_E2E_EXPIRED_PASSWORD`
- `SHOIR_E2E_MODULE_USERNAME`, `SHOIR_E2E_MODULE_PASSWORD`
- `SHOIR_E2E_RESEARCH_MODULE_USERNAME`, `SHOIR_E2E_RESEARCH_MODULE_PASSWORD`
- `SHOIR_E2E_INACTIVE_USERNAME`, `SHOIR_E2E_INACTIVE_PASSWORD`

Under **Variables**, add:
- `SHOIR_E2E_EXPECTED_STAGING_APP_HOST` — hostname only, without scheme/path.
- `SHOIR_E2E_ACTIVE_EXPECTED_TIER` — set to `Enterprise Plus Tier ($399)` if using the default active account tier.
- `SHOIR_E2E_VERIFY_LOGIN_THROTTLE` — enable only when the configured staging throttle test is ready to run.

Do not add the Supabase service-role/secret key, database password, staging admin password or any production key to GitHub Actions. The E2E workflow does not need them.

After confirming that all secrets/variables exist and the staging app displays the banner, securely delete the local credential JSON when it is no longer needed. Keep the account credentials in the approved password manager according to the test-account retention policy.

## H. Apply the three pending staging migrations and deploy the matching Edge Function

**Do this only after Sections B, C and D are accepted, the PR has one independent approval, exact-head CI is green, and PR #232 has been merged into staging.** Do not run these commands on main/production.

Use the repository checkout at the approved staging candidate. Authenticate with the Supabase CLI using a staging-scoped operator credential. Link only to:
`hfhrosthswcybccepmak`.

First inspect remote migration history and preview the changes:
```bash
supabase migration list --remote
supabase db push --dry-run --remote
```

The preview must show only the three intended outstanding organization migrations:
- `20261107150000_shoir_organization_close.sql`
- `20261107153000_shoir_organization_member_suspend_restore.sql`
- `20261107160000_shoir_organization_workspace_state.sql`

If the dry-run lists any unexpected migration, seed data or a different target, stop and reconcile migration history. Do not run `db reset`, `migration repair`, or direct DDL to make the counts look right.

After the dry-run matches exactly and the recovery evidence has been approved:
```bash
supabase db push --remote
```

Then deploy only the persistence function to staging:
```bash
supabase functions deploy shoir-persistence --remote=hfhrosthswcybccepmak --use-api --no-verify-jwt
```

The explicit `--no-verify-jwt` preserves the existing staging function's configured platform-JWT behavior. The function relies on its application-level session-token validation, which must remain covered by the security tests and authenticated E2E workflow. Do not use the flag for other functions or environments without reviewing their authentication design.

After deployment:
1. Confirm Supabase migration history includes the three expected versions and no unexpected ones.
2. Confirm `shoir-persistence` is ACTIVE and its deployed source/hash corresponds to the reviewed candidate.
3. Run the Supabase Security and Health advisors; both must remain free of lints.
4. Re-run the Performance advisor. The six organization foreign-key findings should be gone after the final organization index migration. Review any other findings rather than blindly dropping indexes.
5. Confirm the organization audit table cannot be updated/deleted by application roles and that service-role access is narrowly scoped.

Supabase references: [CLI db push and dry-run](https://supabase.com/docs/reference/cli/supabase-db-push), [Deploy Edge Functions](https://supabase.com/docs/guides/functions/deploy).

## I. Run authenticated staging acceptance

After migrations/function deployment and after all Actions secrets/variables are configured:

1. Open [GitHub Actions](https://github.com/MSJ1708/shoir-ie/actions).
2. Select **Authenticated release gate**.
3. Select **Run workflow**.
4. Select branch `staging-e2e-20261019`.
5. Start the workflow once. Do not repeatedly click Run while it is in progress.
6. Open the run and wait for all jobs. Download the `shoir-ie-authenticated-release-evidence` artifact.
7. Require every mandatory case to show PASS. Any FAIL is a defect; any BLOCKED/SKIP/missing required case means the gate is not accepted.
8. Verify that the workflow restored the active test workspace and revoked temporary sessions. Review the artifact for restore warnings.
9. Confirm that disposable organizations/workspaces created by the workflow were closed/cleaned up while their audit records were preserved.
10. The 96-module rendering matrix proves route/render access for that matrix; it does **not** prove all 100 tool calculations, engineering correctness or real supplier/ERP integrations. Those need the separate tool acceptance below.

## J. Complete engineering acceptance for all tools

For every row in `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`:
1. Run a known-good reference case with independently calculated expected results and units.
2. Run boundary cases, missing/invalid input, negative/non-finite values, conflicting data, empty datasets and oversized inputs where applicable.
3. Confirm provenance is visible and accurate (LIVE/IMPORTED/MANUAL/SYNTHETIC/SIMULATED/MOCK/STALE).
4. Confirm the correct tier/role can run, read, save, export and approve; unauthorized roles and cross-tenant users are denied.
5. Save, reload in a fresh session, export and reopen the exported artifact. Check hashes and source lineage.
6. Verify warnings/limitations are accurate. A heuristic cannot be advertised as a proven root cause, global optimum, RUL date, safety approval or live connector.
7. Record tool ID, exact input fixture, expected result, actual result, test SHA, reviewer and evidence artifact.
8. Set a matrix entry to VERIFIED_WORKING only after all relevant cases pass and an independent engineering reviewer signs it off.

Repeat this for all 16 Industrial Intelligence tools, the eight shared capabilities and Industrial Resource Intelligence. Do not use synthetic fixtures to claim live telemetry, external suppliers or plant control.

## K. Complete Excel add-in runtime acceptance

The candidate contains local Office.js scaffolding; its manifest has not been accepted in a real Excel host. Before calling it an add-in ready for workforce use:
1. Choose an approved HTTPS host for `taskpane.html`, `taskpane.js`, `planner.js` and icons. It must serve the exact assets with valid TLS and the required Office host headers/CORS behavior.
2. Replace every `YOUR-SHOIR-IE-HOST` placeholder with the verified staging host. Do not claim deployment from a manifest template.
3. Validate the manifest XML and Office requirement set.
4. Sideload into Excel for the web and each supported desktop host. Confirm task pane launch, read-only and write operations, 10,000-cell/8 MiB limits, error handling and source workbook preservation.
5. Test a workbook round-trip and compare formulas, styles, names, tables, sheets, metadata and recalculation behavior. Reopen the original and confirm it was not silently altered.
6. Test Arabic/RTL and tier/access rejection. Retain screenshots and test workbooks as evidence.

## L. Complete external integration, API and identity gates

- **T096 ERP/Integration Management:** obtain a customer/vendor sandbox, a read-only test account, provider docs and approval to connect. Configure the exact hostname allowlist and authentication method. Run the full 22-row ERP acceptance matrix, TLS/SSRF/DNS/rebinding/redirect/timeout/size/error-redaction tests. No write scopes.
- **T097 API/SDK:** decide the externally supported tenant and auth model, publish an API contract, rate limits, scopes, idempotency, pagination and SDKs. Test with an independent external client; local plugin registry code is not a hosted public API.
- **T098 Identity/Audit:** configure a real OIDC issuer/client, audience, JWKS and verified email; enable MFA at the provider; validate logout/session revocation and append-only audit history. Do not mark MFA implemented from a configuration placeholder or a user-entered boolean.
- **T099 Backup/Recovery:** complete Sections D and H plus the full evidence bundle in `docs/SHOIR_IE_T099_BACKUP_RECOVERY_ACCEPTANCE.md`.

## M. Saudi privacy, legal, licensing and operational clearance

1. Have qualified Saudi privacy/legal counsel review the actual operator identity, registration/address, PDPL roles/lawful basis, privacy notice, data processing inventory, processors/subprocessors, cross-border hosting/transfers, retention/deletion, data-subject requests, breach reporting and incident procedures.
2. Verify customer-facing terms, refund/support channels, payment flows, commercial claims and the product's legal identity.
3. Generate and review a complete SPDX or CycloneDX SBOM, including transitive Python/JS packages, solver binaries, fonts, images, sample data and licenses. Record attribution and asset ownership. Obtain any necessary trademark/IP advice.
4. Document monitoring, support ownership, escalation, backup cadence, security incident handling, account recovery, change management and rollback.
5. Do not self-certify legal clearance. Keep the product BETA until the qualified reviewer supplies written acceptance.

## N. Final release gate

1. Recheck all exact-head CI on the final staging candidate.
2. Verify staging ruleset still enforces one independent approval, required checks, thread resolution, strict status checks, no force push/deletion and no bypass.
3. Verify backup/recovery and authenticated staging acceptance are accepted with artifacts.
4. Verify the 100-tool matrix, 16-tool suite, eight shared services, Excel add-in and external dependencies have evidence, not merely code.
5. Verify privacy/legal, licensing/SBOM and independent engineering/security reviews are signed.
6. Only then consider a separate PR from accepted staging to main. Main requires its own independent approval and four required checks.
7. Production migrations/deployment require a separate explicit authorization and a production backup/recovery plan. This runbook grants neither.

**Stop condition:** Any unexpected migration, missing backup, wrong app banner/host, non-`shoir-e2e-` test identity, cross-tenant access, failed required check, unresolved review thread, skipped acceptance case, or mismatch in deployed function/source means STOP and keep BETA / NO-GO.

---

## Candidate update — 2026-11-16: remaining canonical Workbench routes

The candidate now includes a dedicated source dispatch module for the nine IDs that were previously navigation-only: T001, T003, T008, T053, T057, T064, T088, T090 and T093.

- Each target is routed by canonical ID in the existing Workbench inspector.
- Each render and submit path calls the canonical tier gate. Execution also requires the existing authenticated actor callback.
- Result/input saves use the existing per-user workspace persistence helper; no second persistence implementation was introduced.
- The new focused test module covers all nine target engines plus guest denial, invalid DAGs, routing matrix completeness, scheduling material constraints and roster conflicts.
- The static execution audit is updated to expect 100 dedicated dispatch IDs and zero mapped-only IDs. This measures source wiring only, not acceptance.

Important boundaries:
- T001 reads authenticated session metadata, not a live operational/tenant-wide dashboard.
- T003 searches permitted canonical tool metadata and current-session result labels only.
- T008 discloses missing formula/unit/assumption/limit metadata and redacts secret-like fields; it does not infer missing engineering assumptions.
- T053 is a priority/earliest-due-date list heuristic, not a global job-shop optimizer.
- T057 is a skill/availability roster heuristic, not legal or fatigue-rule certification.
- T064 is a nearest-feasible-stop heuristic using a user-supplied matrix, not a live road/traffic route optimizer.
- T088 checks DOI/URL syntax only; citations and claims remain unverified.
- T090 formats supplied report content; it does not rerun or certify results.
- T093 validates and orders a typed DAG plan only; it does not execute downstream tools.

Required before any of these IDs may become VERIFIED_WORKING: exact-head CI on the latest candidate SHA; authenticated browser walkthrough; package/role denial tests; managed save, fresh-session reload and tenant isolation evidence; export inspection where applicable; and independent engineering/research review. Do not promote any matrix status based on authored tests or a source-route audit alone.

No staging migration, Edge Function deployment, production write, account mutation, credential read or merge is authorized by this code change. Retain PR #232 as draft, keep BETA, and keep production NO-GO.
