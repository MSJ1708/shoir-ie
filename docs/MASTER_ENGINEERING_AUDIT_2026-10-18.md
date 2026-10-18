# Shoir-IE Master Engineering Audit — 18 October 2026

## Executive status

**Status: partial implementation; full production-readiness gate remains open.**

This document records an evidence-based repository baseline and two focused fixes from the audit. It deliberately does not equate a green CI run or a module renderer existing with end-to-end production readiness. Facility Layout import integrity and workbook processor failure visibility have regression coverage. At code-and-test commit `25facfe5b6f921e9da300397f04af46f126b67ba`, the complete suite passed **384 tests**, and validation, engine-regression, platform-tests, and security-quality workflows passed. A later documentation-only commit `836ffffdde3d117d104c942a23d1f2b7df908f45` triggered another workflow round that was still running when this report update was authored. Broader live connector, browser-rendering, production-persistence and authorization checks remain unverified unless expressly marked below.

## 1. Repository baseline

| Item | Evidence / result |
|---|---|
| Repository | [MSJ1708/shoir-ie](https://github.com/MSJ1708/shoir-ie) |
| Default branch | \`main\` |
| Baseline HEAD before audit changes | \`705dad3c3ac293697adb47a4ffc1fc36656c6787\` |
| Audit branch | \`audit/master-engineering-hardening-2026-10-18\` |
| Application entry point | \`app.py\` (modular Streamlit application; entry point is large, so broad changes should remain focused) |
| Existing target implementations | \`shoir_facility_layout.py\`, \`shoir_enterprise_integration.py\`, \`shoir_capacity_recovery.py\`, \`shoir_excel_studio.py\`, \`shoir_industrial_workbook.py\`, \`workspace_persistence.py\`, \`industrial_platform.py\`, and enterprise/security support modules |
| Existing regression assets | Focused tests already exist for facility layout, capacity recovery, workbook formulas/persistence, Excel cleaning/import, workspace persistence, exports, tier/catalog integrity, application shell, and enterprise services. |
| Dependency configuration | \`requirements.txt\`; current repository pins PuLP and pytest ranges and declares Streamlit, pandas, openpyxl, xlsxwriter, ReportLab, python-pptx, Plotly, and other application dependencies. |
| Baseline security-quality workflow | [Run 39135650924 — success](https://github.com/MSJ1708/shoir-ie/actions/runs/39135650924) |
| Baseline engine-regression workflow | [Run 39135650936 — success](https://github.com/MSJ1708/shoir-ie/actions/runs/39135650936) |
| Baseline validation workflow | [Run 39135650977 — success](https://github.com/MSJ1708/shoir-ie/actions/runs/39135650977) |

The three results above belong to the unmodified baseline commit. The audited head 408ebd3e6e60edfd1c78094c53ad084ad5b2bedb also passed the principal workflows listed in Section 6. This is CI evidence only and does not establish live browser or production-infrastructure readiness.

### Relevant open pull requests inspected

- [PR #123 — Harden capacity recovery evidence and import/export safety](https://github.com/MSJ1708/shoir-ie/pull/123): open when inspected. It covers capacity-result provenance, stale-result invalidation, CSV size limits, duplicate input columns and spreadsheet formula-injection protection. Its unmerged changes must not be described as part of \`main\`; this audit branch avoids duplicating its capacity-recovery edits.
- [PR #116 — Add regression coverage for resilience workspaces](https://github.com/MSJ1708/shoir-ie/pull/116): open when inspected; it adds regression coverage for six resilience workspaces.

The main branch already contains prior facility-layout SLP compatibility work, module-catalog/navigation hardening, capacity-recovery implementation/tests, and shared export argument compatibility. Those existing implementations/tests were retained.

## 2. Baseline issue register

| Issue ID | Module | File / function | Reproduction / evidence | Root cause | Severity | Existing fix / PR | Required remediation | Regression test | Status |
|---|---|---|---|---|---|---|---|---|---|
| FAC-IMP-001 | Facility Layout & Warehousing | \`shoir_facility_layout.py::_import_data\` | Import a flow containing a non-numeric/negative measurement, unsupported SLP code, duplicate directed edge or endpoint absent from the department registry. | The previous import path coerced numeric parse failures, filtered rows with empty endpoints instead of reporting data loss, truncated relationship values, and wrote departments before all flow records were validated. | High — engineering data integrity | No equivalent complete fix found on baseline; PR #123 is related to a different capacity-recovery import path. | Validate every row and cross-reference before persistence; reject ambiguous headers and invalid values; perform all accepted writes in one transaction. | Six new tests in \`tests/test_facility_layout.py\`. | Implemented; all six targeted tests passed as part of 384-test suite at code commit `25facfe5b6f921e9da300397f04af46f126b67ba`. |
| FAC-IMP-002 | Facility Layout & Warehousing | \`_import_data\`, \`_flow_matrix\`, \`_slp_frame\` | Import two records for the same directed edge, or an edge that conflicts with an existing flow ID. | No complete import-time endpoint/duplicate-edge validation in the old import routine. | High | Baseline tests already cover SLP matrix alignment, route direction, alternate paths and pandas-compatible heatmap conversion. | Preserve opposite-direction flows but reject duplicate same-direction edges and invalid references. | Directionality, duplicate-edge, unknown-endpoint and repeated-import tests added. | Implemented; targeted directionality and duplicate-edge cases passed in the 384-test suite at code commit `25facfe5b6f921e9da300397f04af46f126b67ba`. |
| CAP-BASE-001 | Production Bottleneck & Capacity Recovery Study | \`shoir_capacity_recovery.py\` | Existing tests compare reference metrics, reject invalid inputs, test zero-output behavior and inspect evidence hashes. | Baseline implementation has focused calculation validation. A separate open PR proposes additional result-hash and import-size hardening. | High | [PR #123](https://github.com/MSJ1708/shoir-ie/pull/123) | Review the pending PR and its checks before treating its improvements as released. Verify independent calculations and exact current-scenario provenance. | Existing \`tests/test_shoir_capacity_recovery.py\`; PR-specific regression tests are not part of this audit commit unless merged. | Partially covered on baseline; not re-audited end-to-end here. |
| ENT-BASE-001 | Enterprise Integration & Collaboration | \`shoir_enterprise_integration.py\` plus enterprise services | Current test suite validates some connector profile rules and registry/workspace round trips. No connector credentials or plant endpoints were supplied for this audit. | Static configuration and mocked/unit tests cannot establish that an external system is reachable or that its authentication succeeds. | High | Existing connector validation and release-hardening tests | Test each available adapter contract with mocks; live-test only configured, authorized services; report timeout/authentication/unsupported states separately. | Existing tests include malformed endpoint validation and registry persistence. | Partially covered; live connector verification blocked by unavailable credentials/endpoints. |
| IMP-ERR-001 | Enterprise Integration & Collaboration; Facility Layout & Warehousing | `shoir_enterprise_integration.py::_import_dataset`; `shoir_facility_layout.py::_file_to_frames` | Force `process_uploaded_workbook` to raise while importing a supported CSV, or return no usable worksheets. | Catch-all handlers suppressed processor defects and silently fell back to raw parsing; empty processor results also fell through without an explicit diagnostic. | High — data quality and diagnosability | No equivalent fix found on baseline; separate from PR #123 capacity-recovery safeguards. | Propagate processor failures; allow fallback only when `shoir_excel_studio` itself is absent; raise an actionable error for empty output. | Five checks in `tests/test_workbook_import_failure_visibility.py`. | Implemented; all five processor-visibility checks passed as part of the 384-test suite at code commit `25facfe5b6f921e9da300397f04af46f126b67ba`. |
| XLS-BASE-001 | Excel Data Cleaning & Import | \`shoir_excel_studio.py\`, \`shoir_excel_runtime.py\` | Existing tests exercise workbook cleaning/export artifacts, CSV parsing, identifier preservation, formula-injection-safe output, quality metadata and failed-upload stale-download cleanup. | Unit fixtures do not prove hosted upload/download behavior, resource limits at the deployment boundary, or all supported spreadsheet variants. | High | Existing \`tests/test_excel_studio.py\` and \`tests/test_release_hardening.py\`; PR #123 adds separate CSV/capacity safeguards. | Run target-format matrix with actual generated artifacts, failed replacements, size boundaries and browser downloads. | Existing suite plus five cross-module workbook-processor visibility tests in `tests/test_workbook_import_failure_visibility.py`. | Partially covered; hosted browser path not verified. |
| WBK-BASE-001 | Industrial Workbook | \`shoir_industrial_workbook.py\` | Existing tests cover supported formula arithmetic, cross-sheet references, circular formulas, audit errors, query pipelines, saved versions, variables, comments and workspace-scoped persistence. | Formula coverage is intentionally a supported subset; those tests do not prove full Excel compatibility or preservation of every workbook feature. | High | Existing \`tests/test_industrial_workbook.py\` | Verify representative XLSX round trips; keep unsupported functions explicit; test formula, cached value and exported-value consistency. | Existing workbook tests; broader fixture-based round-trip coverage still needed. | Partially covered; full round-trip/UI/export compatibility not established by this audit. |
| RBAC-BASE-001 | Team Workspaces & RBAC | \`workspace_persistence.py\` and protected data/service boundaries | Existing persistence tests cover per-user state separation and safe exclusion of transient/secret-like keys. Some enterprise-layer tests check user/workspace-scoped records. | State-persistence isolation tests are not equivalent to negative authorization tests for every read/write/export/API route. | Critical | Existing \`tests/test_workspace_persistence.py\`, enterprise-layer tests and release-hardening tests | Enumerate protected resource operations; test cross-user and cross-workspace reads, writes, exports, direct calls, tier enforcement and logout/account switching. | Existing tests are a starting point, not complete authorization evidence. | Not fully verified; live durable-backend enforcement and exhaustive negative authorization matrix remain open. |
| RPT-BASE-001 | Executive Report Center | \`industrial_platform.py::export_pdf\`, \`export_pptx\` and report helpers | Existing release-hardening tests generate PDF/PPTX payloads and reopen PowerPoint artifacts; Excel report tests reopen generated workbooks. | Artifact smoke tests do not prove all report templates, long content, multi-page page breaks, cross-format consistency, Arabic/RTL rendering or browser download behavior. | High | Existing \`tests/test_release_hardening.py\` | Compare a single run across PDF/PPTX/XLSX and test page/slide boundaries, Arabic glyphs, source IDs, rounding and assumptions. | Existing artifact tests; full parity suite still required. | Partially covered; complete report-center gate not established. |
| SEC-BASE-001 | Enterprise Security & Governance | \`.github/workflows/security-quality.yml\`, auth/RBAC/persistence/configuration | Baseline security-quality workflow succeeded and includes a hard-coded-secret pattern guard. | A secret-pattern scan and green workflow are limited controls; they do not establish encryption, SSO/MFA, backup/restore, complete access enforcement or certification. | Critical | Baseline security workflow passed | Verify each claimed control at the enforcement point with negative tests and deployment/configuration evidence. Avoid production tests without authorization. | Existing security-quality workflow and module tests; comprehensive control-by-control test suite remains open. | Partially verified; no compliance/certification claim is made. |

## 3. Changes implemented on the audit branch

### Facility Layout import integrity

The Facility Layout import path now:

- Supports normalized department and From/To header aliases, rejecting ambiguous duplicate columns.
- Skips genuinely empty spreadsheet rows while rejecting incomplete non-empty records.
- Validates required IDs and names, duplicate IDs/names, coordinate bounds, positive/finite numeric values where applicable, non-negative loads and distances, and supported SLP values \`A/E/I/O/U/X\`.
- Rejects self-links, unknown department endpoints, duplicate flow IDs, duplicate directed edges, and collisions with existing IDs/edges. The reverse direction remains a distinct edge.
- Validates existing-workspace conflicts before writing, then persists department and flow rows in a single SQLite transaction. A rejected import cannot leave only the department half of a workbook applied.
- Retains the existing additive/upsert import behavior for compatible imports; it does not delete unrelated registered departments or flows.

Regression cases added:

1. Valid imported From/To data round-trips while preserving the distinction between \(A \rightarrow B\) and \(B \rightarrow A\).
2. Negative load values reject the whole import without partial writes.
3. Unknown endpoints reject the whole import without partial writes.
4. Duplicate department IDs and unsupported SLP relationship codes reject the import.
5. Duplicate directed edges reject the import.
6. Re-importing the same flow IDs is idempotent and does not create duplicate rows.

### Shared workbook processor failure visibility

Both `shoir_enterprise_integration.py::_import_dataset` and `shoir_facility_layout.py::_file_to_frames` previously caught every exception raised by `process_uploaded_workbook` and silently tried raw parsing instead. They now fall back only when the processor module itself is absent; processor errors propagate to the existing actionable UI error boundary, and a processor result with no non-empty worksheets raises a clear `ValueError`.

Five checks in `tests/test_workbook_import_failure_visibility.py` verify that processor exceptions remain visible in both import surfaces, empty processor output is reported as an error, and valid cleaned frames are returned as independent copies with the supplied digest preserved. They passed as part of the 384-test suite on code/test commit `25facfe5b6f921e9da300397f04af46f126b67ba`.

The six Facility Layout tests and five additional processor-visibility checks passed within **384 tests in 14.47 seconds** in [Shoir-IE tests run 39137634006](https://github.com/MSJ1708/shoir-ie/actions/runs/39137634006) on code/test commit `25facfe5b6f921e9da300397f04af46f126b67ba`. The same code revision passed [Engine Regression run 39137634227](https://github.com/MSJ1708/shoir-ie/actions/runs/39137634227), [validation run 39137633970](https://github.com/MSJ1708/shoir-ie/actions/runs/39137633970), [Platform Tests run 39137634011](https://github.com/MSJ1708/shoir-ie/actions/runs/39137634011), and [Security and Quality run 39137633949](https://github.com/MSJ1708/shoir-ie/actions/runs/39137633949). Documentation-only audit commit `836ffffdde3d117d104c942a23d1f2b7df908f45` subsequently triggered fresh checks tracked separately.

## 4. Eight-module verification matrix

A module status describes the evidence actually obtained, not whether a renderer or Python file exists.

| Module | Initial findings / existing evidence | Fixes in this change set | Unit tests | Integration tests | Rendering tests | Security tests | Export tests | Final status at audit start |
|---|---|---|---|---|---|---|---|---|
| Facility Layout & Warehousing | Existing tests cover From/To matrix, new departments in SLP, route direction, alternate paths and pandas heatmap mapping. Import validation had an integrity gap. | Validate imports before atomic persistence; six regression cases; surface workbook processor errors rather than falling back silently. | Six facility cases passed in the 384-test suite at code commit 25facfe. | Import/database cases added; full live persistence lifecycle not run. | Existing UI has charts/forms/tabs, but browser rendering is not verified here. | Workspace scoping is present in query keys; exhaustive cross-workspace route tests not run here. | Existing workbook/CSV export functions present; generated artifacts not re-opened by a new facility export test. | **Partial — targeted import fixes passed CI; module-wide completion gates open.** |
| Enterprise Integration & Collaboration | Existing tests cover connector-profile validation, enterprise registry behavior and workspace round trips; import handler previously hid processor errors. | Propagate cleaning-engine failures; actionable empty-result error; five processor-visibility regression checks shared with Facility Layout. | Existing tests plus new regression cases; 384-test suite passed at code commit 25facfe. | Mocked/live adapter and retry/idempotency matrix not comprehensively executed. | No browser check. | Secret masking and server-side permissions not fully audited for every adapter operation. | Export workflow not connector-specific; cross-format checks remain open. | **Partial — import failure diagnostics improved; live endpoint checks blocked without credentials/endpoints.** |
| Production Bottleneck & Capacity Recovery Study | Existing calculation and evidence tests cover invalid input, independent reference metrics and bounded simulated recovery. PR #123 contains overlapping follow-up hardening. | No overlapping capacity code changed in this branch. | Existing capacity-recovery suite plus complete 384-test suite passed at code commit 25facfe. | End-to-end upload → scenario → export not live-tested. | Hosted chart/result panels not browser-tested. | Untrusted CSV boundary and evidence claims require review of PR #123 and current deployment. | Study XLSX generation exists; exported/current-scenario parity not completely revalidated in this audit. | **Partial — preserve and review open PR #123; not declared complete.** |
| Excel Data Cleaning & Import | Existing tests reopen workbook output and cover transformations, metadata, CSV dialect and safe literal text. | Shared-data import callers no longer swallow cleaning-processor exceptions; output with no usable worksheets returns an actionable error. | Existing tests plus five cross-module processor-visibility checks; 384-test suite passed at code commit 25facfe. | Hosted upload failure and successful replacement scenarios not executed in a live browser. | No browser check. | Upload resource boundaries and untrusted workbook handling require broader deployment verification. | Several XLSX artifacts are re-opened by tests; complete target-format matrix not run here. | **Partial — diagnostics strengthened; no live download verification.** |
| Industrial Workbook | Existing tests cover formula evaluation, cycles, errors, scenarios, versions, variables, comments and persistence. | No workbook engine change in this patch. | Existing unit tests. | Broad import/save/reload with representative real-world files not run as a single E2E test here. | No browser check. | Formula safety tests exist; workbook-level threat model and all supported-file cases remain open. | Full Excel-feature preservation and round-trip parity are not claimed. | **Partial — supported formula subset only; compatibility gate open.** |
| Team Workspaces & RBAC | Per-user local-state isolation tests and enterprise workspace scoping exist. | No authorization-boundary change in this patch. | Existing persistence tests. | Durable hosted backend and account-switch lifecycle not exercised here. | No browser check. | Exhaustive direct-call, export, role/tier and cross-workspace negative tests not run. | Permission-gated exports not comprehensively verified. | **Not fully verified — authorization coverage is a release blocker until tested.** |
| Executive Report Center | Existing PDF/PPTX/XLSX helper tests validate selected artifact generation and reopening. | No report renderer change in this patch. | Existing artifact tests. | Same-run parity comparison across all formats not comprehensively run. | No browser download or visual overflow test. | Sensitive-data logging and report authorization need full path audit. | Multi-page, long-label, Arabic/RTL, missing-chart and identical-KPI checks remain open. | **Partial — selected artifacts tested; report-center completion gates open.** |
| Enterprise Security & Governance | Baseline security-quality CI passed; secret-pattern scanner is present. Existing permission/persistence tests cover parts of the surface. | No global security-control changes in this focused patch. | Existing security and negative-input tests. | Production DB, identity provider, backups, TLS and external services not exercised. | Not applicable to control existence; UI badges are not accepted as proof. | No destructive penetration test; enforcement-point matrix is incomplete. | Export authorization/escaping require comprehensive path coverage. | **Partially verified — no certification or production-security claim.** |

## 5. Application-wide verification matrix

| Area | Evidence available | Result | Evidence still required |
|---|---|---|---|
| Python syntax / import compilation | The audited head's validation run completed compile and required-module parse steps successfully. | **Pass at commit 408ebd3e6e60edfd1c78094c53ad084ad5b2bedb.** | Re-run automatically after further changes. |
| Primary navigation and module catalog | Existing catalog/category, tier-integrity, application-shell and smoke tests are present. | **Partially covered by existing automated tests**. | Authenticated browser navigation across every category, tab, modal, search route and narrow/desktop layout. |
| Optional workbook/data startup | Modular application has existing no-upload paths and smoke tests, but live startup under every missing dependency/configuration is not run in this task. | **Not fully verified**. | Hosted startup with no upload, invalid upload, missing database and returning/new sessions. |
| Persistence and recovery | Local SQLite workspace tests cover round trips and selected isolation semantics. | **Unit-level evidence only**. | Hosted durable database outage/recovery, restart persistence, concurrent writes and account switch. |
| Tier / role access | Catalog parity/tier tests exist. | **Partially covered**. | Negative direct access tests for protected calls and exports; distinction between tier entitlement and user authorization. |
| Facility and shared-import integrity | Atomic validation and processor error-visibility regression tests have been added. | **Implemented; 384-test suite passed at code commit 25facfe; hosted upload/download verification remains open.** | Latest documentation-head CI and hosted upload/download verification. |
| Excel cleaning/import | Existing artifact and parser tests plus new import error-visibility checks. | **Partially covered; 384-test suite passed at code commit 25facfe.** | All supported extensions, file-size limits and browser download validation. |
| Industrial workbook | Formula/query/persistence regression tests exist. | **Partially covered**. | Validated round-trip fixtures and declared compatibility matrix. |
| PDF / PowerPoint / Excel report integrity | Selected artifact builders are tested in \`test_release_hardening.py\`. | **Partially covered**. | Cross-format data parity, visual inspection, Arabic/RTL, long report boundaries and missing-chart paths. |
| Connector availability | Endpoint validation tests exist, but credentials and plant endpoints were not supplied. | **Blocked for live verification**. | Authorized configuration plus successful connector-specific tests. |
| Security control enforcement | Baseline security workflow passed; checks include a heuristic credential-pattern scan. | **Limited automated verification**. | Control-by-control negative tests, deployment configuration review, TLS/backup evidence, identity provider evidence and full access-boundary audit. |
| Hosted Streamlit browser | No authenticated interactive browser session was available through the repository workflow. | **Not performed**. | Authorized browser session and test accounts for desktop/mobile smoke tests. |
| Production deployment | Repository CI is observable; no deployment changes or production database mutations were performed. | **Not verified in this task**. | Post-PR hosted smoke test and deployment-specific configuration evidence. |

## 6. CI, scope and limitations

- Never interpret “pending” or “blocked” as “passed.” Five principal workflows passed on code/test commit `25facfe5b6f921e9da300397f04af46f126b67ba` with 384 tests. A documentation-only commit `836ffffdde3d117d104c942a23d1f2b7df908f45` followed; its latest-head workflow round was in progress at the time of this report update.
- The repository cannot be cloned into the task container because outbound GitHub DNS/network access is unavailable. Changes were made through the authenticated GitHub integration and must be validated by GitHub Actions.
- No production database records, credentials or deployment settings were modified.
- No destructive penetration test was run.
- No live SAP, Oracle, MES, ERP, SQL, REST, MQTT or OPC-UA system was claimed as connected.
- No investor-facing savings, downtime, yield or ROI claims were independently measured or re-certified.
- The audit does not claim full Excel compatibility, SSO/MFA, encryption, backups, certification or general production readiness solely because related functions or settings exist.
- The main branch's existing tests and current-green baseline workflows are useful evidence, but they do not replace complete browser testing and enforcement-point security tests.

## 7. Pull request acceptance checklist

- [x] Record main branch HEAD and inspect open PRs.
- [x] Establish baseline CI state.
- [x] Create a feature branch from the observed main HEAD.
- [x] Fix the identified Facility Layout import integrity issue.
- [x] Surface workbook processor failures instead of silently falling back in Facility Layout and Enterprise Integration imports; add regression tests.
- [x] Add regression tests for the fix.
- [x] Keep capacity-recovery edits separate from overlapping open PR #123.
- [x] Complete CI for processor-error hardening at code/test commit `25facfe`; all five principal workflows passed with 384 tests.
- [ ] Confirm fresh CI on the latest documentation-only head.
- [x] Record completed workflow outcomes and links in this report.
- [x] Open a non-merged PR to main (PR #126).
- [ ] Perform an authorized hosted browser/deployment verification.
- [ ] Complete remaining module and security matrices before declaring the full definition of done satisfied.
