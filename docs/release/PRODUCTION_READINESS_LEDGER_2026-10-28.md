# Shoir-IE Production Readiness Ledger — 2026-10-28

**Decision: NO-GO / HOLD.** This is the live evidence ledger for the release-recovery work. It does not authorize production DDL, migration-ledger repair, Edge Function deployment, changes to production records, paid launch, or removal of the global BETA label.

**Assessment source:** read-only GitHub and Supabase Management API inspection on 2026-10-28, plus GitHub Actions evidence linked below. Statuses are intentionally conservative. A skipped job, a source-level test, a candidate PR, or a successful staging check is not a production pass.

**Evidence freshness rule:** GitHub PR #211 receives documentation/workflow-only commits during this recovery. Previously linked runs for head `429c8e074018f4cd61384280329b295f2807aa92` describe that prior head only and must not be treated as checks on a later SHA. For final acceptance, compare every workflow run's `head_sha` to the current PR head in GitHub. The workflow changes below are intended to make non-mutating public staging/production probes run on the dedicated `docs/live-release-recheck-20261027` branch push and the authenticated gate run only when that branch receives a commit with the explicit marker. No production deployment is triggered by these workflow changes.

## 1. Exact baseline

| Surface | Verified state | Evidence / interpretation |
|---|---|---|
| Repository | `MSJ1708/shoir-ie`, default branch `main` | [Repository](https://github.com/MSJ1708/shoir-ie) |
| Main | `2ef44057f84162389d39998e922b505dcfe4d3e9` | Branch API; current main branch head |
| Staging | `0558c23d59a3f0b79558a8d3407869d0238aceaf` | Branch API; current hosted-staging base, not PR #215's candidate |
| Production database | `gcsamrdaeraxieaagsta`, PostgreSQL 17.6.1.166, `eu-central-1` | Supabase project read; status ACTIVE_HEALTHY |
| Staging database | `hfhrosthswcybccepmak`, PostgreSQL 17.11.0.003, `eu-central-1` | Supabase project read; status ACTIVE_HEALTHY |
| Production persistence | `shoir-persistence` v9; SHA-256 `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740` | Direct Management API read of deployed function metadata and source |
| Staging persistence | `shoir-persistence` v11; SHA-256 `a0252769822fd7834c6af67fcf69259ec9bbefce7041ac3a5a36d8d6a9a90397` | Direct Management API read; not production-compatible until schema migration is separately reconciled |
| Production migration ledger | 14 entries; ends at `20261019140600` | Supabase migration history |
| Staging migration ledger | 17 entries | Includes three later legal/referral-related records absent from production |

## 2. Candidate and CI evidence

These are separate candidate branches. Their passing tests do not combine into a single releasable artifact and none has an independent approval recorded yet.

| PR | Exact head | Current check evidence | Current disposition |
|---|---|---|---|
| [#211 live release recheck](https://github.com/MSJ1708/shoir-ie/pull/211) | Prior fully checked head: `429c8e074018f4cd61384280329b295f2807aa92`; subsequent evidence/workflow commits supersede it. | Prior-head [authenticated release gate](https://github.com/MSJ1708/shoir-ie/actions/runs/40700565452) PASS; prior-head [validation](https://github.com/MSJ1708/shoir-ie/actions/runs/40700565581) PASS; prior-head exact checks and hosted staging acceptance PASS. These results do **not** transfer to newer commits. | Draft. On prior head, production public-shell smoke and authenticated gate checks were skipped/not run as applicable; production CORS diagnostic recorded FAIL. Confirm new runs on current PR head after workflow-trigger corrections. |
| [#220 production persistence security candidate](https://github.com/MSJ1708/shoir-ie/pull/220) | `a21bc158a11fe1119989371df726084ff81d7cc4` | [Tests](https://github.com/MSJ1708/shoir-ie/actions/runs/40739795836), [security/quality](https://github.com/MSJ1708/shoir-ie/actions/runs/40739795297), [platform](https://github.com/MSJ1708/shoir-ie/actions/runs/40739795015), [Edge Function verification](https://github.com/MSJ1708/shoir-ie/actions/runs/40739794997), [engine regression](https://github.com/MSJ1708/shoir-ie/actions/runs/40739795092), and [validation](https://github.com/MSJ1708/shoir-ie/actions/runs/40739795289) PASS. | Draft; no independent review; not deployed. Candidate README records the exact active v9 source hash as its source baseline. |
| [#218 safe legal/referral migration](https://github.com/MSJ1708/shoir-ie/pull/218) | `78012547a585ddb0ec063eb2b8d7dbfa4a6d6028` | [Tests](https://github.com/MSJ1708/shoir-ie/actions/runs/40740983351), [platform](https://github.com/MSJ1708/shoir-ie/actions/runs/40740983417), [security/quality](https://github.com/MSJ1708/shoir-ie/actions/runs/40740983757), [engine](https://github.com/MSJ1708/shoir-ie/actions/runs/40740983596), [validation](https://github.com/MSJ1708/shoir-ie/actions/runs/40740983432), and [subscription integration](https://github.com/MSJ1708/shoir-ie/actions/runs/40740983423) PASS. | Draft; no independent database/security review; no production migration. Source/test success is not a production-shaped restore rehearsal. |
| [#217 PDF/PPTX completeness](https://github.com/MSJ1708/shoir-ie/pull/217) | `7c0ddde187c36c53e591c3742a5d770b1b0703f9` | Exact-head validation, platform, engine, test and security/quality checks PASS. [Validation run](https://github.com/MSJ1708/shoir-ie/actions/runs/40505702284). Its synthetic export evidence reports 3 PDF pages and 11 PPTX slides, retaining all 67 row markers; artifact hashes are recorded in the PR thread. | Open and not independently reviewed; synthetic artifact validation only. No production deployment. |
| [#216 main security consolidation](https://github.com/MSJ1708/shoir-ie/pull/216) | `21a8d786485c11a415df1158d851bc43f9705c24` | See current branch checks before review/merge. | Draft, no independent review. #214/#213 overlap is documented as consolidated into #216; do not merge duplicates separately. |
| [#215 clean 100-tool staging candidate](https://github.com/MSJ1708/shoir-ie/pull/215) | `701c5ee0c167df35539bfba70ac751b45dd0e5df` | [Engine regression](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170787), [platform](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170856), [validation](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170743), and [security/quality](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170729) PASS. | Draft, not deployed to the hosted staging candidate. Its feature and module calculations still need exact-candidate acceptance. |

## 3. Authoritative blocker ledger

| Gate | Status | Verified cause / evidence | Exact remaining action |
|---|---|---|---|
| Live production CORS | **FAIL** | Active production v9 source still sets `Access-Control-Allow-Origin: *`; the `POST, OPTIONS` methods header is present, but source has no exact-origin denial or `Vary: Origin`. The GitHub-runner diagnostic in [run 40700565581](https://github.com/MSJ1708/shoir-ie/actions/runs/40700565581) recorded wildcard responses for approved, unapproved, and missing-origin probes. | Run a fresh non-mutating runner probe against the current endpoint; review #220; require written approval; deploy only the exact approved v9-compatible artifact; re-probe all origins and methods post-deployment. Local execution from this environment could not resolve the Supabase hostname, so local curl is not represented as a pass. |
| Request size, JSON validation and error redaction | **CANDIDATE PASS / PRODUCTION FAIL** | Deployed v9 source uses `req.json()` without an observed bounded streamed-body parser or equivalent 12 MiB bound. #220 includes bounded parsing, safe public errors and security tests; its exact-head checks pass. | Independent source review, then authorized deployment followed by non-mutating malformed/oversized/error probes. |
| Protected administrator stored invariant | **PASS — current data only** | Read-only aggregate query found exactly one active Enterprise Admin and confirmed the `sho` row matches username, role `Enterprise Admin`, tier `Enterprise Plus Tier ($399)`, active=true and expiry `2099-01-01T00:00:00Z`. No row was changed and no login was attempted. | Preserve the invariant; review #220. Never test with or modify the reserved administrator. |
| Protected administrator runtime behavior | **FAIL in deployed source** | Production v9 login code updates the reserved administrator's tier and `updated_at` when it observes a tier mismatch, instead of enforcing a read-only invariant. The stored row currently matches, but this code path remains unsafe. | Deploy the reviewed fail-closed candidate only after approval; verify drift handling through isolated unit tests and disposable identities, never by corrupting or logging in as `sho`. |
| Production/staging schema compatibility | **FAIL / HOLD** | Production is missing `public.shoir_referrals` and all 6 legal-acceptance columns on `shoir_subscription_requests`; staging has the table and all 6 columns. Production has 5 accounts with blank/null `affiliate_code` values. | Finalize a source/schema compatibility manifest and rehearse the exact reviewed sequence on an isolated production-shaped database. Do not deploy staging v11 to production. |
| Migration safety and ledger reconciliation | **BLOCKED** | Production ledger ends at `20261019140600`. Later historical migrations `20261021130000`, `20261022110000`, and `20261023130000` are not recorded in production; the first historical migration rewrites blank/legacy referral codes and `updated_at`. #218's safe replacements and synthetic preservation tests pass CI, but the live production ledger must not be advanced blindly. | Independent DB/security review; isolated proof that the legacy files cannot replay; confirm every ledger repair is supported by a schema/data equivalence comparison; save before/after protected digests and transaction rollback evidence. Never run normal production `supabase db push` while this remains unresolved. |
| Backup, PITR and actual restore | **BLOCKED / PLAN GAP** | Current Supabase organization plan reports `free`. Supabase's current plan docs say automatic backups and PITR are not included on Free; production backup availability and an isolated restore have not been proven. See [Supabase pricing](https://supabase.com/pricing) and [database-backup docs](https://supabase.com/docs/guides/platform/backups). | The owner must approve a costed plan change or establish an independently managed off-site backup path, then produce an actual isolated restore rehearsal with restore point, timings, row/schema checks, RPO/RTO and Edge Function/config recovery evidence. No production restore. |
| Hosted authenticated staging baseline | **PASS for the baseline only** | PR #211 exact-head authenticated gate run 40700565452 passed dedicated-account preflight, candidate build, authenticated Edge API lifecycle/workspace isolation, 96/96 route/default-state renders, and browser shell/Excel/logout. Its staging-live-acceptance job in run 40700565581 passed. | Repeat on the integrated #215 feature candidate after that exact candidate is deployed to staging. A baseline gate is not proof of new module behavior. |
| Hosted live-deployment smoke | **NOT RUN for the final candidate** | `live-deployment-smoke` was skipped in the current PR validation path. A skipped result is not a pass. | Run the release-specific smoke against the deployed exact candidate; retain URLs, timestamp, source hash, browser/network output and sanitized artifacts. Production smoke only after authorization. |
| Authentication throttling and inactive-account denial | **NOT YET ACCEPTED for final candidate** | Current PR #211 authenticated gate covers lifecycle and isolation, but no exact current-candidate acceptance evidence was found here proving both throttling and inactive-account denial against the hosted deployed candidate. | Add/execute disposable-account hosted checks for rate limiting, inactive account, expired session, role and tenant boundary denials; retain actual outputs. |
| Application persistence and RBAC | **PARTIAL** | Baseline authenticated lifecycle/workspace isolation passed; #215 contains additional stable-ID and actor/owner enforcement changes but has not been deployed to the hosted staging candidate. | Deploy #215 through protected staging workflow after required review/checks; run two-user cross-workspace and six-tier/direct-route authorization tests and save evidence. |
| PDF/PPTX/XLSX export correctness | **PARTIAL / CANDIDATE PASS** | #217 exact-head CI and synthetic PDF/PPTX rendering succeeded; its PR records 67-row completeness and visual review of all PDF pages/slides. XLSX injection tests are included and CI passed. | Independent review; run export acceptance from the final integrated candidate, verify source calculations, inspect exact final artifacts and save hashes. |
| Main branch ruleset | **PASS — configured** | Active ruleset “Protect main — release gates” requires PR, 1 approval, dismisses stale approvals, requires conversation resolution, blocks deletion and force-push, enforces strict status checks `test`, `edge-function`, `engine-regression`, `security-quality`. | Preserve; do not bypass. Obtain independent approval before merge. |
| Staging branch ruleset | **PARTIAL / ACTION REQUIRED** | Active staging ruleset requires a PR, 1 approval, stale-review dismissal, conversation resolution, blocked deletion/force-push and strict status checks, but currently requires only `test`; Edge Function, engine regression and security/quality checks are not required by the ruleset. | Repository administrator must update and verify required contexts for the release candidate, keeping release-only live checks separate from ordinary PR checks if their trigger conditions differ. |
| Independent reviews | **BLOCKED** | GitHub review API returned no submitted reviews for #211, #217, #218, #220 or #216 at this assessment. | Obtain independent security review for #220/#216 and independent DB/migration review for #218; resolve their comments and rerun affected checks. The agent must not approve its own PR. |
| T096 Integration Management Center | **EXTERNAL CONFIGURATION REQUIRED** | 100-tool inventory currently classifies T096 as external-configuration-required; no approved non-production endpoint/credential-backed test evidence is recorded. A generic REST framework is not proof of SAP/Oracle integration. | Supply an approved non-production HTTPS endpoint, host allowlist and read-only test credential; test redirects/SSRF/TLS, response bounds, schema validation and redaction. Otherwise keep it explicitly unavailable in launch scope and remove unsupported ERP claims. |
| T098 Identity and Audit Center | **EXTERNAL CONFIGURATION REQUIRED** | Inventory classifies T098 as external-configuration-required; no provider-backed OIDC/MFA evidence is recorded for the final candidate. | Supply the selected OIDC/MFA provider's staging configuration and disposable test identities; prove token/session/role mapping and durable audit event outcomes. Otherwise exclude from launch scope and remove unsupported OIDC/MFA/audit claims. |
| 100-tool matrix | **NOT VALIDATED** | Last candidate classification is 98 `IMPLEMENTED_NEEDS_VALIDATION`, 2 `EXTERNAL_CONFIGURATION_REQUIRED`, 0 `VERIFIED_WORKING`. These are readiness classifications, not a pass rate; #215's CI passing does not validate all 100 behaviors. | Attach reproducible inputs, expected/observed outputs, negative-path and access-control tests for each tool; update status only on actual acceptance. |
| Saudi legal/privacy/commercial readiness | **EXTERNAL REVIEW REQUIRED** | Legal/privacy, PDPL data map and pilot/support draft documents exist, but no qualified Saudi legal/privacy approval or verified company identity/contact details were produced by this assessment. | Provide factual legal-entity/contact details; obtain qualified Saudi review of PDPL/e-commerce, consent, retention/deletion, subprocessors, cross-border processing, refunds, pricing and referral wording; fix findings before paid launch. |
| Production release authorization | **NOT AUTHORIZED** | No explicit release-owner approval naming the exact source hashes, migration order, recovery evidence and maintenance window is recorded. | Request written approval only after every prerequisite is closed. Do not merge to main or deploy production as a side effect. |
| Post-deployment verification and rollback | **NOT RUN** | No authorized production release is complete. | After approval and deployment, verify deployed source hash, live CORS, disposable-account login/persistence/RBAC, legal guard, logs, admin invariants and rollback readiness. Stop and recover on any unexplained change. |
| Global BETA removal | **HOLD** | Production acceptance, recovery, review, legal/commercial sign-off and release authorization remain unresolved. | Keep the global BETA label. Remove it only after all mandatory gates have evidence and the hosted production customer journey is verified; retain feature-specific limitation notices. |

## 4. Release decision and sequencing

**Current decision: NO-GO.** No production migration, function deployment, production-account mutation, paid launch, or global BETA removal is authorized.

Safe sequence:

1. Refresh the production CORS probe and confirm the current endpoint/source hash on a GitHub-hosted runner.
2. Obtain independent security review for #220/#216; resolve any findings against the exact source hash.
3. Obtain a suitable backup/recovery capability under an owner-approved plan, and perform an isolated restore rehearsal.
4. Obtain independent database review of #218 and rehearse its migration-ledger reconciliation against a production-shaped isolated copy.
5. Correct the staging ruleset using repository-admin access and retain the exact saved configuration.
6. Deploy the integrated candidate to protected staging; rerun hosted authenticated acceptance, calculations, RBAC, login-throttle/inactive-account denial and all exports against that exact deployed candidate.
7. Validate all in-scope tool requirements and either provider-test T096/T098 or remove them and their unsupported claims from launch scope.
8. Complete qualified Saudi legal/privacy/commercial review and factual company disclosures.
9. Freeze an exact release candidate, rerun its required CI, compile the migration/function hashes and recovery evidence into a release authorization request, and wait for explicit written approval.
10. Deploy only the approved candidate, repeat live production probes and smoke tests, then consider global BETA removal.

### Stop conditions

Stop and remain HOLD if the function/schema hashes change unexpectedly; any migration would replay a historical rewriting script; recovery cannot be demonstrated; any protected-admin data changes; a required check is skipped or missing; a security/migration reviewer has not approved; T096/T098 claims exceed proven integration; legal facts are missing; or explicit production release authorization is absent.

## 5. Recovery update — 2026-10-28, 19:42 UTC

This section supersedes older candidate-head/check-status notes above where they differ. It does not change the release decision.

### Exact candidate heads and fresh CI

| Candidate | Current head | Fresh checks at the recorded head | Interpretation |
|---|---|---|---|
| [#216 main-based security/consolidation candidate](https://github.com/MSJ1708/shoir-ie/pull/216) | `67e43987ac99cba34564ff9ab2043550dd915820` | [Tests](https://github.com/MSJ1708/shoir-ie/actions/runs/40756561498), [validation](https://github.com/MSJ1708/shoir-ie/actions/runs/40756561606), [security/quality](https://github.com/MSJ1708/shoir-ie/actions/runs/40756561610), [Edge Function](https://github.com/MSJ1708/shoir-ie/actions/runs/40756561473), [engine](https://github.com/MSJ1708/shoir-ie/actions/runs/40756561519), [platform](https://github.com/MSJ1708/shoir-ie/actions/runs/40756561593), and push validation [40756556601](https://github.com/MSJ1708/shoir-ie/actions/runs/40756556601) were queued when refreshed. | **NOT YET PASS.** Earlier head `96f58dab4545758cf2d4f8b53a216bdea1a39053` ran 984 tests: 982 passed, 2 failed. One failure revealed the engine method is decorated with an async wrapper; the regression test was corrected to execute it via `asyncio.run`. The other attempted to JSON-serialize a pandas DataFrame instead of the sanitized `profile_records`; the assertion was corrected to inspect those serializable records. Both fixes are in the newer head, which must be rerun. The missing SimPy dependency was added to `requirements.txt` before that run. |
| [#215 staging integration/mobile candidate](https://github.com/MSJ1708/shoir-ie/pull/215) | `7e20633385cad96a59703ace23ddfedb0213c0fd` | [Validation](https://github.com/MSJ1708/shoir-ie/actions/runs/40756104792), [engine](https://github.com/MSJ1708/shoir-ie/actions/runs/40756104739), [platform](https://github.com/MSJ1708/shoir-ie/actions/runs/40756104791), and [security/quality](https://github.com/MSJ1708/shoir-ie/actions/runs/40756105091) were still in progress/queued at this refresh. The hosted staging job is no longer absent from the candidate workflow. | Hosted staging CORS/preflight **PASS**; the public browser smoke **FAIL** on the currently deployed staging app, as detailed below. Local candidate tests are not complete yet. |

### Live staging failure — do not waive

The current staging-targeted hosted run [40756104792](https://github.com/MSJ1708/shoir-ie/actions/runs/40756104792) uploaded artifact [`shoir-ie-staging-live-acceptance` #12846835741](https://github.com/MSJ1708/shoir-ie/actions/runs/40756104792). It directly probed `https://shoirieverified.streamlit.app/` and found:
- Approved/rejected-origin CORS and preflight assertions passed against the deployed staging Edge Function.
- Desktop public tabs and their expected fields passed.
- At 390px mobile width, the deployed tab list measured `scrollWidth=384` vs `clientWidth=358`; browser scroll position was 26px and “Explore the Modules” rendered clipped to “Explore the M…”.
- The report contains no uncaught JavaScript errors and no page-level horizontal overflow, but the tab-row clipping is a functional visual defect and the smoke correctly fails it.
- Authenticated module checks were explicitly `NOT RUN` because no authorized disposable-account credentials were supplied to CI.

PR #215 contains the candidate CSS to stack and wrap only the keyed public auth tabs, plus the stronger mobile geometry test. The hosted staging app does **not** yet run this PR’s source SHA, so the live failure cannot be called fixed until an independently reviewed candidate is deployed through the protected staging path and a fresh hosted screenshot/geometry run passes. The workflow job was initially malformed due to a bad indentation on commit `619a730bc1ba01ddb8c3af37dbf9b49083c053c6`; indentation was corrected in current head `7e20633385cad96a59703ace23ddfedb0213c0fd`. The temporary YAML error is not treated as a passing run.

### Additional security implementation now present in #216 candidate (not deployed)

The draft security candidate now includes these fail-closed changes, all still subject to fresh exact-head tests and independent review:

- The legacy Industrial Connectivity Hub’s direct URL probe and query against a shared application SQLite database have been removed. The UI states that profiles are metadata and no network request is made there.
- The legacy REST/SQL/MQTT/OPC-UA probes and sample-reader path return `EXTERNAL_TEST_DISABLED` instead of contacting user-entered URLs, arbitrary PostgreSQL/SQLite targets, MQTT brokers, or OPC-UA endpoints without the dedicated T096 safeguards.
- The old connector schedule UI no longer creates/runs live sync jobs, and pre-existing cached sample data is cleared from the user session instead of being rendered after the unsafe reader is disabled.
- `EnterpriseConnectorStub` no longer returns invented warehouse/demand values or logs an unperformed ERP write as successful; both operations fail closed with `NotImplementedError`.
- T096 configuration inspection now distinguishes the generic HTTPS REST adapter from unimplemented vendor/protocol adapters. Configuration presence is not labelled `CONNECTED`; SAP/Oracle/WMS/MES/ERP, SQL/MQTT/OPC-UA are explicitly `PROVIDER_ADAPTER_NOT_IMPLEMENTED` until provider-specific code and acceptance evidence exist.
- User-facing connector copy was changed to distinguish “profile/readiness” from live ERP connectivity. OIDC/MFA and durable audit still have no provider-backed T098 evidence.

No production function or database was changed. The currently deployed production CORS failure remains independent of these candidate changes.

### Saudi legal/privacy review reference pack

Use official sources as inputs for qualified counsel, not as a substitute for legal approval:
- [Saudi E-Commerce Law, official Bureau of Experts entry](https://laws.boe.gov.sa/BoeLaws/Laws/SearchDetails/?Id=360de590-0286-4fa5-a243-aa9100c31979&Query=+).
- [Saudi E-Commerce Law text published by MISA](https://misa.gov.sa/app/uploads/2025/07/E-Commerce-Law.pdf).
- [SDAIA Personal Data Protection Law](https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPL/).
- [SDAIA Regulation on Personal Data Transfer Outside the Kingdom](https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/RegulationonPersonalDataTransferOutsidetheKingdom/).
- [SDAIA guidance for controllers and processors](https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPLCP/).

The paid-launch blocker is unchanged: company legal identity/contact facts are not yet verified in the customer-facing policy pack, hosting/subprocessor/data-location and cross-border transfer facts need to be documented, and a qualified Saudi legal/privacy review is not recorded. Do not infer legal clearance from these references or this code review.

### Decision remains NO-GO

Production CORS, production/schema compatibility, safe migration-ledger reconciliation, backup/PITR plus actual restore rehearsal, hosted authenticated acceptance, staging mobile candidate deployment/verification, complete 100-tool evidence, T096/T098 provider setup or launch-scope exclusion, independent reviews, staging ruleset completion, legal/privacy/commercial review, release-owner authorization, post-deployment smoke, and global BETA removal remain unresolved. Preserve all stop conditions above.

