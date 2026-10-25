# Shoir-IE 100-tool integration report

**Branch:** `feat/shoir-100-tools-integration-20261025`  
**Scope:** code-grounded additions to the existing Shoir-IE Workbench  
**Current release status:** implementation tranche in progress; NO-GO until current CI, authenticated browser, persistence, integration and release checks pass

## UI and architecture preserved

The implementation uses the existing `pages/Industrial_Engineering_Workbench.py` target directory and form patterns. No 100-page navigation redesign was introduced. Focused methods use stable target IDs, the existing authenticated-user check, `require_tool_access`, the existing result renderer and existing workspace-save helper. The target registry and the matrix continue to distinguish a mapped or implemented method from a fully verified capability.

## Focused execution methods

The original focused tranche was continued with four additional methods (T036, T037, T051 and T072). This integration also carries the separately tested T062 solver diagnostics, T071 discrete-event simulation and T087 reproducibility ZIP into the same branch. The combined Workbench contains 55 distinct stable target IDs with focused runner branches; each remains pending authenticated end-to-end verification. Other existing module workflows may cover additional targets, but they are not counted as focused runners unless wired to the stable target ID and its execution gate. The implementation matrix links every target to its minimum tier, contracts, evidence tests and remaining limitations.

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
| `IMPLEMENTED_NEEDS_VALIDATION` | 79 |
| `FOUNDATION_ONLY` | 19 |
| `EXTERNAL_CONFIGURATION_REQUIRED` | 2 |
| `MISSING` | 0 |
| `BLOCKED` | 0 |

These are evidence classifications, not a quality score. `IMPLEMENTED_NEEDS_VALIDATION` means a real implementation/first-pass method is mapped but mandatory verification remains incomplete. `FOUNDATION_ONLY` means the specialist promised behavior remains incomplete. Zero missing catalogue mappings does **not** mean all 100 tools are complete.

## Verification / release gates

A previous run on an earlier code revision reported 705 passed, 2 failed and 2 skipped, and a later branch note reported 740 passed and 2 skipped before the most recent methods were integrated. Those results do not certify the current branch head.

Run GitHub Actions for validation, tests, engine regression, security/quality and platform tests on the updated branch head. A passing conclusion must be confirmed against the exact resulting SHA. The authenticated browser acceptance matrix remains unverified, including direct-route/API/Copilot/export tier enforcement, save/reload/re-login, cross-workspace isolation, real workbook-to-decision flow and configured live integrations.

Before merging, run all workflows on the exact final commit, fix every regression, complete authenticated browser and persistence/export checks, review deployment parity, and keep the PR in draft/NO-GO until mandatory acceptance is evidenced.

## Release position

**DRAFT / NO-GO.** This integration tranche preserves the current UX and adds executable calculation-backed tools, but it does not complete all 100 targets or certify workforce/production readiness. Do not merge or make commercial readiness claims until the remaining foundation-only capabilities and the mandatory release checks are completed.
