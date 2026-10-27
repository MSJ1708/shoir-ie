# Shoir-IE 100-tool integration report

**Branch:** `feature/data-lineage-recovery-20261027` (candidate PR #208)  
**Scope:** code-grounded 100-target Workbench additions, automated authorization coverage, and persistence Edge Function hardening; no production deployment  
**Current release status:** implementation tranche in progress; NO-GO until current CI, authenticated browser, persistence, integration and release checks pass

## Current Workbench integration addendum — 27 October 2026

The current candidate adds focused, bounded workflows for T006 recovery, T020 dataset lineage, a limited T039 CAPA/8D register, the T044 RCM review register and T046 single-task RNLE screening. These methods are explicitly marked `IMPLEMENTED_NEEDS_VALIDATION` in both runtime registry and implementation matrix. The matrix is synchronized with the runtime registry in this candidate.

Matrix status counts after the 27 October integration: 98 IMPLEMENTED_NEEDS_VALIDATION, 0 FOUNDATION_ONLY, 2 EXTERNAL_CONFIGURATION_REQUIRED. These are implementation classifications, not verified-pass counts. These are implementation classifications, **not a pass rate** and not a count of tools verified in production. T006 undo/redo does not reverse external side effects; T020 does not independently authenticate source signatures or invalidate every consumer; T039 is not a complete CAPA lifecycle; T044 leaves decisions pending human review; T046 is a single-task screen with stated applicability/limits. Hosted persistence, cross-workspace/re-login behavior, independent method review and final integrated staging acceptance remain release gates.

## UI and architecture preserved

The implementation uses the existing `pages/Industrial_Engineering_Workbench.py` target directory and form patterns. No 100-page navigation redesign was introduced. Focused methods use stable target IDs, the existing authenticated-user check, `require_tool_access`, the existing result renderer and existing workspace-save helper. The target registry and the matrix continue to distinguish a mapped or implemented method from a fully verified capability.

## Focused execution methods

The original focused tranche was continued with four additional methods (T036, T037, T051 and T072). This integration also carries the separately tested T062 solver diagnostics, T071 discrete-event simulation and T087 reproducibility ZIP into the same branch. The combined Workbench contains 64 distinct stable target IDs with focused runner branches, including the four trust/help/support actions added in this tranche; each remains pending authenticated end-to-end verification. Other existing module workflows may cover additional targets, but they are not counted as focused runners unless wired to the stable target ID and its execution gate. The implementation matrix links every target to its minimum tier, contracts, evidence tests and remaining limitations.

### Lean, manufacturing, quality and economics

| ID | Method | Scope and explicit limitation |
|---|---|---|
| T024 | Production Line Balancer | Precedence-feasible topological/greedy station packing; heuristic, not globally optimal. |
| T025 | Bottleneck and Constraint Analyzer | User-entered capacities vs demand; screening result, not causal proof. |
| T027 | Value Stream Mapping Studio | First-pass lead-time estimate from WIP/flow, cycle time, uptime and changeover per batch; not a calibrated simulation. |
| T038 | FMEA Manager | RPN = severity × occurrence × detection; high severity separately surfaced; rating/risk bands need human review. |
| T070 | Queuing and Service-System Analyzer | Stable single-server M/M/1 model only; assumes Poisson arrivals/exponential service. |
| T082 | Industrial Costing and Variance Analyzer | Direct-material price/usage/total variance, with reconciliation. |
| T083 | Evidence-Based ROI Tracker | Cost-reduction and ROI arithmetic; always requires human evidence verification and never self-certifies savings. |
| T043 | Preventive Maintenance Planner | Interval due dates, overdue state and labor estimate; not a resource/downtime optimizer. |
| T047 | Job Safety and Hazard Register | Severity × likelihood screen with residual scores; not a certified or legally sufficient safety assessment. |
| T054 | Material Requirements Planner | One-level BOM netting, lot multiples and lead-time release indices; no recursive BOM explosion. |
| T084 | Engineering Project Portfolio Scorer | Direction-aware min-max normalization with user-defined weights; weight sensitivity not implemented. |
| T034 | Acceptance Sampling Planner | Single-sample binomial attributes plan and stated risk probabilities; not sampling-standard certification. |

### Data, reliability, supply chain and energy

| ID | Method | Scope and explicit limitation |
|---|---|---|
| T017 | Data Join and Merge Studio | Explicit join keys, duplicate-key policy, row limits and matched/unmatched cardinality diagnostics. |
| T018 | Time-Series Data Processor | UTC normalization, gap/duplicate diagnostics and optional numeric resampling; DST and large-volume cases require more verification. |
| T019 | Synthetic Industrial Data Generator | Reproducible seeded data with row-level `SYNTHETIC` provenance; never plant observations. |
| T076 | Process Mining Analyzer | Event-log variants, directly-follows transitions and case durations; not full conformance checking or causal analysis. |
| T079 | Water and Waste Efficiency Analyzer | Per-process input/output/waste balance; totals omitted when periods differ and unit incompatibility rejected. |
| T041 | Weibull Reliability Analyzer | Two-parameter MLE fit for at least five positive uncensored failure times; censored data and confidence intervals are not implemented. |
| T045 | Spare Parts and Criticality Planner | Reorder point and exposure screening from demand, lead time, safety stock and criticality; not multi-echelon optimization. |
| T050 | Safety Incident Trend Analyzer | Rates normalized to stated period-specific exposure hours; trends do not prove causation. |
| T059 | Warehouse Slotting and Picking Optimizer | Greedy nearest compatible slot assignment with capacity checks and unassigned-item reporting; not globally optimal. |
| T063 | Assignment and Scheduling Optimizer | Minimum-cost one-to-one Hungarian assignment; no calendars, skill constraints, precedence or multi-period scheduling. |
| T077 | Energy Performance Optimizer | Compare baseline/alternative energy intensity, cost and emissions from scenario inputs; no plant control or guaranteed savings. |

The methods use user-entered values and explicitly marked illustrative examples. A calculated number does not prove data accuracy or operational suitability.

### Additional statistical, forecasting and simulation methods

This follow-on branch adds four stable-ID runners to the existing Workbench target directory without creating new top-level navigation:

| ID | Implemented baseline | Scope / limitation |
|---|---|---|
| T036 | Linear regression and one-way ANOVA | One numeric predictor for ordinary least squares, or an independent-groups one-way ANOVA. Includes residual/group summaries, ANOVA table and supported inference; does not include multivariable modeling, causal conclusions or post-hoc pairwise tests. |
| T037 | Welch independent-samples t-test | Two-sided test, Welch degrees of freedom and confidence interval for the mean difference. Other test families, paired designs and multiplicity correction are not included. The minimum tier remains Research Pack. |
| T051 | Chronological demand baseline comparison | Compares naive-last-value, training-mean and trailing moving-average baselines on a chronological holdout; the lowest-MAE baseline provides a simple forecast. It does not provide trend/seasonality models or prediction intervals. |
| T072 | Seeded Monte Carlo net-value simulation | Supports declared independent benefit/cost inputs with normal, uniform, triangular or constant distributions. Reports quantiles, probability of negative net value, component correlation and a running-mean view. Correlations between inputs and cash-flow timing are not modeled; the result is not verified ROI. |

The four methods use explicit execution-time require_tool_access checks, the existing authenticated-user guard, saved input snapshots and the shared result renderer. Deterministic golden/boundary tests and Workbench AppTest coverage were added. Those tests must still pass on the exact final commit before the new methods can be considered validated. The implementation status for all four remains IMPLEMENTED_NEEDS_VALIDATION; authenticated save/reload, export and browser acceptance remain open.


### Solver diagnostics, discrete-event simulation and reproducibility export

This integration adds three executable tools to the existing Workbench, without changing primary navigation:

| ID | Method | Scope / limitation |
|---|---|---|
| T062 | Constraint and Solver Diagnostics | LP/MILP execution with actual solver status and independent bound, integrality and constraint residual checks. It does not create an irreducible infeasible subsystem or prove that the supplied formulation reflects the real operation. |
| T071 | Discrete-Event Simulation | Event-driven first-come-first-served serial process with finite servers, explicit deterministic/exponential assumptions, seeded replications and warm-up job exclusion. It is not a calibrated digital twin or arbitrary-routes simulator. |
| T087 | Reproducibility Pack Generator | Creates a ZIP with result/configuration metadata, SHA-256 manifests and optional redacted inputs/tables. Detailed payloads are opt-in; users must review the bundle before sharing. |

Golden/boundary tests and Workbench AppTests cover deterministic simulation results, seeded repeatability, optimal/infeasible/unbounded/integer solver cases, and ZIP structure/hash/redaction. The tools remain `IMPLEMENTED_NEEDS_VALIDATION` until the exact current head passes automated tests and authenticated persistence/export/browser acceptance.


### Network flow and facility-location optimization

| ID | Method | Scope / limitation |
|---|---|---|
| T069 | Network Flow and Location Optimization | A capacitated single-period facility-location MILP minimizes fixed site-opening costs plus per-unit shipment costs. It requires all customer demand to be met and independently audits the solver objective, facility capacities, route capacities and customer balances. It does not model multi-period inventory, intermediate transshipment or uncertainty. |

Independent tests use a hand-calculated four-route example (expected total cost 21 units), an infeasible route-capacity case, and invalid/duplicate-route inputs. The method is marked `IMPLEMENTED_NEEDS_VALIDATION` pending current CI and authenticated staging acceptance.


### Student Learning and Practice Mode

T089 now has a Starter-accessible practice path inside the existing Workbench. The fixed exercise set covers takt time, OEE, EOQ, Cp and NPV; each numerical answer is checked with a declared tolerance, then the learner sees the reference answer, formula and worked solution. Question prompts do not reveal the answer key before the learner submits. Examples are synthetic educational exercises, not plant observations. Golden-answer, wrong-answer and invalid-input tests plus a Workbench AppTest were added. The tool remains `IMPLEMENTED_NEEDS_VALIDATION` until current CI, authenticated UI and persistence checks pass.


### Guided Study Wizard

T002 is now an executable Starter workflow planner in the existing Workbench. It supports capacity/bottleneck, facility-layout, quality/capability, inventory, maintenance/reliability and sustainability goals; cross-references each planned step to the canonical tool registry; lists declared required fields; distinguishes tier-restricted and foundation-only steps; and suggests a next ready step without running or inventing downstream results. Tests cover missing inputs, current tier restrictions, completed-session steps and invalid goals. It remains `IMPLEMENTED_NEEDS_VALIDATION` pending current CI and authenticated persistence/browser checks.


### Trust center, contextual help and safe support bundle

Four previously foundation-only target tools now have focused Workbench actions while retaining the current navigation:

| ID | Implemented behavior | Explicit boundary |
|---|---|---|
| T007 | Redacts common credentials, emails, IP addresses and credential-bearing URLs from user-supplied diagnostic text; omits traceback frames/source lines; classifies common access, persistence, import/export, calculation and rate-limit symptoms with next checks. | It does not ingest server logs or prove the cause of a live failure. Redaction is heuristic and must not be treated as a guarantee that arbitrary text contains no sensitive data. |
| T009 | Checks registry ID completeness/duplicates/unknown statuses and summarizes all declared tool readiness statuses, with an optional filtered list. | This is a registry status report, not live runtime health, CI telemetry, or authenticated browser proof. |
| T010 | Searches canonical tool metadata and returns each matching tool's minimum tier, purpose, inputs, outputs, status and known limitations. | Guidance is registry-derived; full reviewed lessons, citations and verified deep links are not yet integrated. |
| T100 | Generates a uniquely referenced JSON bundle containing a redacted summary, severity, component, registry status counts and recovery checks. The Workbench exposes a download control. | The bundle is explicitly `PREPARED_NOT_SENT`. No ticketing backend, incident lifecycle or automatic transmission exists. Raw submitted diagnostics are not included in the persisted input snapshot. |

The focused actions use the existing authenticated actor check, `require_tool_access` gate and workspace-result helper. New deterministic tests cover redaction, traceback removal, status-registry integrity, searchable help, support-bundle non-delivery and the Workbench controls. Current-commit CI execution, authenticated browser acceptance, durable save/reload and workspace-isolation evidence remain required before these capabilities can be called verified.

### Equipment anomaly monitoring and freshness

T048 now has an Enterprise-gated path within the existing Workbench. It uses a global median/MAD point-anomaly screen with an explicit zero-MAD fallback, and independently reports freshness (`FRESH`, `STALE`, or `FUTURE_TIMESTAMP`). Invalid timestamps/non-finite values are rejected; out-of-order and duplicate timestamps are surfaced as warnings. The method is **not** a predictive-maintenance model, root-cause analyzer or live sensor integration. Unit and Workbench AppTest cases have been added; the status remains `IMPLEMENTED_NEEDS_VALIDATION` until CI and authenticated staging checks pass.

## Calculation safety and regression protection

Independent golden/boundary tests were added for the new methods, along with three Workbench Streamlit AppTest groups that invoke the forms and check structured results. Key controls include:

- Line-balance precedence and cycle-time validation; explicit infeasibility for oversized tasks.
- Capacity and flow comparisons with same-unit/time-period contracts.
- FMEA and hazard high-severity visibility beyond aggregate scores.
- Queue stability check for M/M/1.
- Direct-material variance reconciliation.
- ROI status always remains `REQUIRES_HUMAN_VERIFICATION`.
- Reject invalid timestamps rather than silently dropping rows; show duplicate join keys and output caps.
- Synthetic datasets are seed-reproducible and row-labelled.
- Acceptance sampling exposes the binomial acceptance probabilities rather than treating a result as a standard-certified plan.
- Flow totals are never combined across different reporting periods.
- Weibull fit explicitly excludes right/left/interval-censored data and does not claim confidence intervals.
- Spare-parts, warehouse, assignment and energy results clearly state which constraints are not included.

A shared output-rendering issue found when displaying a list of missing ROI evidence items was corrected: scalar diagnostic lists are rendered as lists, not passed into `pandas.json_normalize`. A VSM golden test was also corrected to use the formula `1 / 107 × 100 = 0.9346%`.

## Current target-registry status

The registry and matrix contain 100 target IDs, T001–T100. Current classification snapshot:

| Status | Count |
|---|---:|
| `VERIFIED_WORKING` | 0 |
| `IMPLEMENTED_NEEDS_VALIDATION` | 87 |
| `FOUNDATION_ONLY` | 11 |
| `EXTERNAL_CONFIGURATION_REQUIRED` | 2 |
| `MISSING` | 0 |
| `BLOCKED` | 0 |

These are evidence classifications, not a quality score. `IMPLEMENTED_NEEDS_VALIDATION` means a real implementation/first-pass method is mapped but mandatory verification remains incomplete. `FOUNDATION_ONLY` means the specialist promised behavior remains incomplete. Zero missing catalogue mappings does **not** mean all 100 tools are complete.

## Security review and threat model

A repository-level threat model is maintained at [docs/SHOIR_SECURITY_THREAT_MODEL.md](./SHOIR_SECURITY_THREAT_MODEL.md). It records the main assets and trust boundaries, observed controls, evidence limits and release blockers. This is a source review, not a penetration-test report or security certification.

Changes made in this candidate branch:
- The persistence Edge Function now reads JSON through a bounded stream (12 MiB maximum), rejects malformed/non-object bodies, validates workspace state as an object with an 8 MiB serialized limit, and validates before upsert so malformed or oversized state does not replace the last valid saved state.
- Unexpected persistence exceptions are mapped to a generic server error rather than returning raw database/storage/provider messages. Known public auth, subscription, rate-limit and payment-proof validation errors retain controlled statuses/messages.
- Added Deno regression tests for bounded input, malformed JSON, workspace-state limits, status mapping and internal error redaction.
- The Edge Function workflow now runs formatting, type-checking and Deno tests for this helper, and is configured to run for this stacked integration PR.
- Added a Python release-gate test covering registry/matrix identity, all 100 target IDs, all six package states, direct authorization allows/denies, unknown-target fail-closed behavior, and Research Pack versus Enterprise Plus separation.
- Enabled security-quality, platform and engine-regression workflows for pull requests targeting the current 100-tool integration base, in addition to main.

Residual security limitations are material:
- The repository currently reports main branch protection disabled with required status checks off. The available connected GitHub action could read this state but could not change branch protection; repository settings/admin action is still required.
- Cross-user/cross-workspace denial has not been proven against two disposable authenticated staging accounts and the deployed Supabase project. RLS policy source review is not a substitute for that runtime test.
- Full review of every SQL execution path, import/export format, Copilot entry point, connector URL, API/plugin action and browser rendering sink is not complete. The workflow secret-pattern guard only scans three application entry files; dependency/security jobs must be checked on the exact release head.
- No authenticated hosted browser run, staging import-to-export-to-decision run, renewal-only/account revocation walkthrough, production deployment parity check, or independent penetration test is evidenced by this branch.
- Request and workspace limits are intentional safety bounds; large workspace payloads above these limits will be rejected without replacing the prior saved state. Verify representative production workspace sizes in staging before deployment.

## Verification / release gates

### Canonical 100-target accounting
The matrix and runtime registry were reconciled: both contain exactly 100 unique IDs (T001–T100) with matching canonical name, minimum tier and implementation status. The classification remains 0 VERIFIED_WORKING, 87 IMPLEMENTED_NEEDS_VALIDATION, 11 FOUNDATION_ONLY, 2 EXTERNAL_CONFIGURATION_REQUIRED, 0 MISSING, and 0 BLOCKED. This means all targets are accounted for, not that all are operational.

The newly added test tests/test_shoir_100_tool_tier_truth_table.py is intended to make this cross-check and the six-package authorization truth table part of automated regression coverage. It exercises the canonical authorization helper, not every legacy route or external API callsite; route/API/Copilot/export-level enforcement still requires dedicated authenticated acceptance.

### CI evidence must match the candidate SHA
Earlier failures were diagnosed and the underlying assertion/selection issues corrected:
- On earlier PR #187 head 20ed6d39bcbfbbaec6c08f2241136293058ba97a, the validation suite reported one failure and 792 passes: Streamlit AppTest passed a formatted display label back to a selectbox and the formatter applied twice.
- The test now selects the stable underlying ID T021, and the reproducibility-pack assertion now inspects Streamlit download_button elements rather than the ordinary button collection; the actual Workbench uses the expected ZIP download control.
- The Deno Edge Function checks (format, type-check and security tests) passed on predecessor commit 72091c5f4543ffaca82d870d927bd578bd8c4962 ([workflow run](https://github.com/MSJ1708/shoir-ie/actions/runs/40201706751)). This is historical evidence for that exact revision, not proof that a later head has passed.

The latest branch changes also expanded workflow triggers and added the six-package target regression test. Earlier workflow conclusions must not be reused as proof for a later head. Confirm the latest commit SHA and conclusions for all of these workflows before making a merge decision: [Shoir-IE validation](https://github.com/MSJ1708/shoir-ie/actions/workflows/shoir-validation.yml), [security and quality](https://github.com/MSJ1708/shoir-ie/actions/workflows/security-quality.yml), [platform tests](https://github.com/MSJ1708/shoir-ie/actions/workflows/platform-tests.yml), [engine regression](https://github.com/MSJ1708/shoir-ie/actions/workflows/engine-regression.yml), and [Edge Function verification](https://github.com/MSJ1708/shoir-ie/actions/workflows/edge-function-check.yml).

The validation workflow's hosted live-deployment-smoke job is skipped on this stacked feature PR by its current condition; its local browser smoke is not authenticated application acceptance and cannot establish deployed-commit parity.

### Mandatory gates still open
Before this may be considered for merge or deployment, the exact final head must pass all applicable workflows and then complete the following in isolated staging:
- Authenticated browser walkthroughs for each advertised operational target, including correct action/output/error handling and tier-denial tests.
- Direct route/action/API/plugin/Copilot/export authorization checks, including all restricted tiers and unmapped-target fail-closed behavior.
- Save/reload/re-login, interrupted-save recovery and two-user cross-workspace isolation checks.
- Valid multi-sheet workbook import, validation, mapping, deterministic engineering calculation, scenario comparison, decision save, export generation, reopen and expected-value verification; invalid input must preserve the previous valid state.
- Facility Layout, Excel cleaning, Industrial Workbook, integration diagnostics, executive report exports, workspace/RBAC and security/governance walkthroughs.
- Staging database/RLS policy tests, migration and Edge Function dependency parity, dependency-scan review, and verification that no unresolved critical/high security finding remains.
- Confirmed deployment parity for the SHA being released. No production deployment was performed by this work.

## Release position

**DRAFT / NO-GO.** This integration tranche preserves the current UX and adds executable calculation-backed tools, but it does not complete all 100 targets or certify workforce/production readiness. Do not merge or make commercial readiness claims until the remaining foundation-only capabilities and the mandatory release checks are completed.


### Additional bounded target engines — 27 October 2026

The same candidate now adds focused first-pass engine/Workbench wiring and golden/boundary tests for T060 minimum-cost single-commodity network flow, T074 affine digital-twin output-fit diagnostics, T080 deterministic capacity-shock/backlog scenarios, T094 freshness-aware KPI threshold evaluation, T097 read-only plugin-manifest validation, and T099 workspace-scoped retention/restore-evidence preflight. These targets are classified **IMPLEMENTED_NEEDS_VALIDATION** because bounded executable workflows now exist. T097 does not register or invoke plugins; T099 does not export, delete, create backups or restore data; T094 does not persist or send alerts; T074 does not identify physics-based parameters or connect to live telemetry; and T060/T080 use deterministic user-supplied assumptions. No target is marked VERIFIED_WORKING. Full CI, authenticated tier/direct-action checks, hosted persistence/tenant testing and independent domain/security review remain required.
