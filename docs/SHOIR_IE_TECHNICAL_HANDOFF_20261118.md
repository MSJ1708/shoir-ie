# Shoir-IE technical hand-off — 2026-11-18

**Purpose:** Record what has actually been implemented and verified on the repository side, what the latest CI did, and what remains for the staging operator. This is a technical hand-off, not production release approval.

## Repository candidate

- Repository: MSJ1708/shoir-ie
- PR: [#232 — Release hardening and staging security acceptance](https://github.com/MSJ1708/shoir-ie/pull/232)
- Branch: feat/shoir-ie-release-hardening-20261105
- Previous inspected head: b43571cacdfa791d1417ca73ee10e572028f61f2
- Target branch: staging-e2e-20261019
- PR state at inspection: open and draft.
- This commit adds CI execution changes and this hand-off. Re-read the PR header for the exact current SHA and use only checks attached to that SHA.

## CI evidence on the previous exact head

| Check | Result |
|---|---|
| Engine Regression | 521 passed, 0 failed |
| Edge Function security tests | 14 passed, 0 failed |
| Clean PostgreSQL 17 migration replay | 2 passed on disposable local PostgreSQL |
| PostgreSQL transaction contract | Success |
| Production-v9 security backport | 5 passed, 0 failed |
| Excel Intelligence | 38 Python tests and 9 Node planner tests passed |
| Security/quality dependency audit | No known vulnerabilities found |

Run links: [Engine Regression](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726907), [Edge Function](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726898), [migration replay](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726989), [transaction contract](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726919), [v9 security backport](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726914), [Excel Intelligence](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726920), [security/quality](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726900).

## Full validation: not passed

[Full validation run #43929726913](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726913) was cancelled at the 120-minute GitHub Actions job limit. The pytest progress reached approximately 40%. Three failure markers were visible in the output before cancellation (two near 20%, one near 25%), but the process was terminated before it could print failing test names, tracebacks, totals or JUnit XML. The artifact upload confirmed that no JUnit file existed. Therefore:

- the full test suite is **not passed**;
- the exact failing tests and final pass/fail/skip totals are **unknown**;
- those three visible failure markers must be diagnosed on a completed run; do not assume they are fixed by component workflow successes.

Independent steps after the cancellation did complete: Deno formatting/type checks and active Edge security tests; production-v9 format/type/security checks; direct dependency audit; credential-pattern scan; synthetic PDF/PPTX render step; application import smoke (57 top-level statements); and local Playwright smoke for desktop, tablet and mobile public-entry pages. The in-workflow PostgreSQL service/Node steps were skipped due their default success condition. The separate checks above are valid component evidence but do not replace the full run.

## Technical CI improvement added in this revision

The full-validation workflow now:

1. Installs pytest-xdist and pytest-timeout in CI only (not in production app requirements).
2. Runs the broad test set with four workers and --dist=loadfile, keeping test modules within one worker process.
3. Runs the two PostgreSQL integration modules serially after the parallel suite. Both interact with one disposable PostgreSQL service and create cluster-wide roles and temporary databases, so they are intentionally not parallelized against each other.
4. Uses a 10-minute per-test timeout and verbose test output so one stalled test yields a named failure/traceback rather than occupying the entire runner window.
5. Stores parallel and PostgreSQL JUnit output separately and uploads both reports.
6. Runs the PostgreSQL service check and Node/Excel checks with explicit always() conditions after successful compilation, so a regression failure does not silently suppress independent technical checks.
7. Raises the job ceiling to 180 minutes as a guardrail, not as a substitute for test-level timeouts.
8. Upgrades actions/setup-node to v7 and Node 24; GitHub Actions removed the Node 20 action runtime on 23 September 2026. The Excel workflow is updated consistently.

**Important:** these are CI workflow changes. The new exact-head run must still complete; any timeout or failed test must be investigated and fixed. No test may be skipped merely to obtain green CI.

## Live environment parity (read-only observations)

| Item | Staging | Production |
|---|---:|---:|
| Supabase project ref | hfhrosthswcybccepmak | gcsamrdaeraxieaagsta |
| PostgreSQL | 17.11 | 17.6 |
| Applied migration versions | 24 through 20261107120637 | 14 through 20261019140600 |
| shoir-persistence | v14 | v10 |
| Organization tables | 5 | 0 |
| Legal-acceptance columns | 6 | 0 |
| shoir_internal RLS | Enabled on 12 tables | Disabled on 12 tables |

Security advisors were empty in the last observation for both projects. Earlier grant inspection found no direct anon or authenticated grants on production shoir_internal; the RLS parity gap is still a defence-in-depth issue and needs an approved least-privilege review. These were read-only observations; no staging or production schema or function changes were performed.

## Migration and production safeguards

- Staging currently has the base organization migration 20261107120637; three additional organization migrations remain in candidate source: 20261107150000, 20261107153000, 20261107160000.
- Candidate also tracks the additive legal/referral migration 20261026110000; staging already has equivalent safe SQL recorded as 20261105101231. The differing version identifiers must be explicitly reconciled. Do not run supabase db push blindly or fake migration history.
- **Never replay** 20261021130000_shoir_beta_legal_referrals.sql on production as written. It updates affiliate codes and updated_at for rows matching its predicates. The additive replacement 20261026110000_safe_beta_legal_referrals.sql preserves those values, but production migration order must be tested because the 20261022110000 legal-acceptance trigger depends on the columns created by the safe replacement.
- Before the later production promotion, test the migration ordering and history reconciliation on a disposable PostgreSQL 17 database shaped like production. Prove existing affiliate codes and timestamps remain unchanged, including the protected administrator record. Never use a production migration repair or ad hoc history edit to make counts match.
- Staging deployed Edge Function v14 is also behind the current candidate index.ts; the candidate includes organization close, member suspension/restoration and shared workspace-state routes. It must be deployed to staging only after an accepted backup/restore point, exact-head CI and independent approval.

## 100-tool / capability status

The canonical matrix remains:

- 100 canonical tool IDs with dedicated Workbench dispatch paths in source;
- 96 IMPLEMENTED_NEEDS_VALIDATION;
- 4 EXTERNAL_CONFIGURATION_REQUIRED (T096–T099);
- 0 VERIFIED_WORKING.

The 16 Industrial Intelligence engines and eight shared capabilities have source and automated test coverage, but hosted authenticated acceptance and independent engineering review remain outstanding. T094's automated regression coverage passed in the Engine Regression run; its durable hosted alerts and notifications still require staging acceptance. A route, unit test or synthetic example is not proof that a tool is verified for plant decisions.

### External gates for your staging week

- **T096 — ERP:** the generic connector source is not a provider-complete SAP/Oracle implementation. Choose the exact product/edition and permitted read-only sandbox/auth contract; implement and test provider-specific transport, pagination, tenant/resource mapping, TLS and SSRF boundaries.
- **T097 — API/SDK:** provision an approved external API host/gateway and test identity/scopes, rate limits, audit, TLS/DNS and a client outside the repository. Local plugin metadata is not a hosted API.
- **T098 — OIDC/MFA/audit:** PR #223 is separate and draft, not included in PR #232. Its proposal has a security finding: caller-controlled email_hint is used as a throttle key before ID-token validation, allowing targeted throttling. It also has an out-of-order migration version. Fix/review/rebase that work before configuring a real staging IdP; do not merge the PR wholesale.
- **T099 — backup/recovery:** verify Supabase backup/PITR and retention, separately back up Storage object bytes and secrets/configuration, restore into an isolated project, measure RPO/RTO, and obtain independent review. A workspace JSON export is not a database disaster-recovery plan.

## Staging acceptance hand-off

Use the existing [Human Acceptance Runbook](SHOIR_IE_HUMAN_ACCEPTANCE_RUNBOOK.md) and [Authenticated Release Gate](AUTHENTICATED_RELEASE_GATE.md). The workflow requires seven dedicated staging-only identities with usernames beginning shoir-e2e-, a dedicated staging Streamlit hostname/banner, the staging Edge URL and publishable key, and the listed GitHub Actions secrets/variables. Never provide service-role keys to Actions; never use customer identities or the protected Enterprise Admin account. Run the authenticated workflow manually on staging-e2e-20261019 after its preflight is satisfied.

For every tool ID, record a reference fixture and independently checked result, boundaries, role/tier denial, provenance, save/reload/re-login, tenant isolation and export evidence as applicable. The 96-module rendering matrix is not proof that all 100 tool calculations are correct. Retain failures and skipped cases as blockers; do not upgrade matrix status until a qualified reviewer signs the evidence.

## Branch protection and eventual production release

Both main and staging-e2e-20261019 rulesets were observed active, with PR-required changes, one independent approval, approval of the latest push, review-thread resolution, strict/up-to-date checks, no bypass actors, and deletion/non-fast-forward protection. The staging ruleset requires eight contexts. The main ruleset currently requires only test, edge-function, engine-regression and security-quality; before a production PR, add/verify the migration replay, transaction contract and production-v9 compatibility contexts, and include Excel if it is designated production-critical. The connected GitHub tools do not expose ruleset-write operations.

Production must remain untouched until the staging release is accepted, backup/recovery is evidenced, a separate PR into main passes the main ruleset with independent review, and the production-specific migration/function/app rollout has a tested rollback plan and explicit authorization.

## Actions completed / not performed in this technical pass

Completed on the repository candidate: CI execution/diagnostic improvements, Node action/runtime upgrade, and this current technical hand-off. All resulting checks are pending on the new commit until GitHub Actions finishes.

Not performed: no staging or production migration, Edge deployment, production application deployment, PR merge, customer/account change, or use of the protected administrator. Keep Shoir-IE **BETA / NO-GO** until all remaining evidence exists.


## Full-suite failure diagnosis and remediation — 2026-11-18

The exact-head full run on `8f671ed83f4fc05dcae558b5a7d751b3b64db151` completed its 1,413-test report and found 14 failures, 0 errors and 0 skips in the parallel suite. The serial PostgreSQL suite passed 3/3. The failures were:

- Ten Streamlit AppTest timeouts across `test_shoir_resource_intelligence.py`, `test_shoir_100_tool_workbench.py` and `test_shoir_tool_trust_center_workbench.py`. The tests launch full Workbench pages backed by the same local SQLite stores. Running those three modules concurrently on separate xdist workers caused contention and exceeded the AppTest's 45–60 second script-run limits; one long nine-tool end-to-end UI test also exceeded the global 600-second timeout.
- Two stale error-message regex expectations in `test_final_integration.py`; the current implementation intentionally reports the more precise text “dataset lineage is stale or unverified” and “source dataset version is no longer current”. The assertions have been aligned to the implemented safety messages.
- One SQLite ResourceWarning caused by the test itself using `with sqlite3.connect(...)`, whose context manager commits/rolls back but does not close the connection. The test now uses `contextlib.closing` for both connections.
- One workflow-contract test expected the old literal `pytest -q tests` after the CI command had been deliberately replaced with xdist and separate serial suites. The contract now asserts the new parallel/serial workflow and report artifacts.

### Remediation added

The three Streamlit-heavy modules are removed from the parallel xdist suite and are now run in a dedicated serial AppTest step with a 30-minute per-test diagnostic ceiling. The nine-canonical-tool UI route test has the same explicit timeout marker so its full route/entitlement matrix is not killed at ten minutes. PostgreSQL integration remains its own serial step. Both parallel and serial reports remain uploaded as separate JUnit XML files. This preserves all test cases; none is skipped or weakened.

The updated exact-head CI must still run and pass before this remediation is considered complete.


---

## Superseding handoff update — 2026-11-20

This addendum supersedes any older handoff text above that describes standalone PR #223 as the T098 integration target. The T098 OIDC implementation was selectively forward-ported into PR #232; PR #223 is closed/superseded and must not be merged. The current detailed T098 status and provider checklist are in `docs/SHOIR_IE_T098_IDENTITY_AUDIT_ACCEPTANCE.md` and `docs/T098_OIDC_AUDIT_CONFIGURATION.md`.

### Current repository engineering candidate

- Active PR: [#232 — Release hardening and staging security acceptance](https://github.com/MSJ1708/shoir-ie/pull/232).
- Branch: `feat/shoir-ie-release-hardening-20261105`.
- Current head at this handoff refresh: `ace18eadb47aca2ff193c4ee55706d6041e97580`.
- Target: `staging-e2e-20261019`.
- PR remains open and draft. It is a candidate for staging review, not a release approval.
- The canonical tool readiness matrix remains 96 `IMPLEMENTED_NEEDS_VALIDATION`, four `EXTERNAL_CONFIGURATION_REQUIRED` (T096–T099), zero `VERIFIED_WORKING`.

### T020 — coordinated Storage lifecycle lease

Repository work now adds migration `20261120115000_shoir_dataset_storage_lifecycle_leases.sql` and matching Edge Function integration:

- Private RLS-enabled workspace/dataset lease table; no direct table privileges to anon, authenticated or service_role.
- Pinned-search-path SECURITY DEFINER acquire/release RPCs executable only by service_role.
- Lease acquisition is atomic on workspace/dataset, limited to 30–600 seconds, and reclaims expired leases. Release is token-matched so a stale operation cannot release a newer holder's lease.
- Dataset finalization holds a 300-second lease across temporary object verification, content-addressed object creation/reuse, atomic metadata registration and temporary cleanup.
- T020 cleanup acquires the same lease before checking both metadata ledgers, writing kind-specific deletion intent, removing an eligible old temporary or immutable orphan object and writing completion evidence.
- Preview remains default; deletion requires explicit confirmation. The 48-hour newest-timestamp rule, workspace path validation, Owner/Admin manage permission, fail-closed reference checks, 500-object/200-directory scan bound, 100-reference-check limit and 50-deletion limit remain.

The current candidate contains PostgreSQL replay tests for lease table RLS/grants, RPC grants, competing acquisition, stale-token release denial, correct/idempotent release, invalid TTL rejection and expiry reclamation, plus static Edge ordering and T020 UI/operator contracts.

### Exact-head CI and deployment boundary

The eight required workflow runs were created for head `ace18eadb47aca2ff193c4ee55706d6041e97580` at the time of this refresh:

- Full Shoir-IE validation — run [44731941242](https://github.com/MSJ1708/shoir-ie/actions/runs/44731941242).
- Engine Regression — run [44731941029](https://github.com/MSJ1708/shoir-ie/actions/runs/44731941029).
- Edge Function verification — run [44731941206](https://github.com/MSJ1708/shoir-ie/actions/runs/44731941206).
- Production v9 compatibility — run [44731941017](https://github.com/MSJ1708/shoir-ie/actions/runs/44731941017).
- Security and quality — run [44731941046](https://github.com/MSJ1708/shoir-ie/actions/runs/44731941046).
- Clean PostgreSQL migration replay — run [44731941092](https://github.com/MSJ1708/shoir-ie/actions/runs/44731941092).
- Excel Intelligence — run [44731941109](https://github.com/MSJ1708/shoir-ie/actions/runs/44731941109).
- Subscription transaction integration — run [44731941048](https://github.com/MSJ1708/shoir-ie/actions/runs/44731941048).

At initial inspection, the focused workflows were starting/in progress and the two large suites were pending. Do not infer passes from queued/running states; inspect final job steps and artifacts for this exact SHA. If any subsequent commit is pushed, repeat the complete checks on that newer exact head.

Read-only Supabase project inspection still reports staging Edge v14 and production Edge v10. The connected database migration-history call failed authentication, so the current deployed migration ledger must be confirmed through the authorized operator path before a migration decision. Neither the new migration nor matching Edge source has been deployed to staging or production.

### Work still required before any staging deployment

1. Obtain a green exact-head CI result with inspected JUnit, PostgreSQL replay and Deno logs; resolve all failures, skips and warnings.
2. Obtain independent code/security review and one required approval on the latest push; resolve every review thread.
3. Confirm a staging backup and tested rollback/restore path, including Storage object bytes; the database-only backup is insufficient.
4. Apply reviewed migrations to staging in timestamp order and deploy the matching Edge Function source only in a separately approved staging window. Recheck RLS/grants, RPCs, advisors and deployed function hash/version.
5. Run authenticated disposable-account staging acceptance for T020 lease conflict/expiry/release, TUS upload interruption/resume, hash/shape validation, historical download, temporary/immutable orphan preview/deletion, Owner/Admin permissions, cross-workspace denial and audit events.

The T020 cleanup remains manual; no scheduler or service identity has been configured. Do not operate it on production.

### External configuration and final acceptance

T096–T099 still require real provider/identity/infrastructure configuration and acceptance. The exact configurations and evidence lists remain in the T096, T097, T098 and T099 acceptance documents. After those are configured, run the authenticated release gate and full browser/module/workbook/export journey with disposable staging identities. Independent Industrial Engineering, security, infrastructure and Saudi privacy/legal review is still required.

**Release position is unchanged: PR #232 remains draft; Shoir-IE remains BETA; production remains NO-GO.** No staging/prod migration, Edge deployment, secret change, Streamlit deploy, merge, customer/account mutation or protected-administrator use is claimed by this repository pass.
