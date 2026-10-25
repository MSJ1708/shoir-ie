# Shoir-IE 100-tool integration report

**Branch:** `agent/shoir-100-rnle-ergonomics-20261025` (stacked on `agent/shoir-100-release-gates-20261025`)  
**Scope:** code-grounded additions to the existing Shoir-IE Workbench  
**Current release status:** implementation tranche in progress; NO-GO until current CI, authenticated browser, persistence, integration and release checks pass

## UI and architecture preserved

The implementation uses the existing `pages/Industrial_Engineering_Workbench.py` target directory and form patterns. No 100-page navigation redesign was introduced. Focused methods use stable target IDs, the existing authenticated-user check, `require_tool_access`, the existing result renderer and existing workspace-save helper. The target registry and the matrix continue to distinguish a mapped or implemented method from a fully verified capability.

## Focused execution methods

The original focused tranche was continued with four additional methods (T036, T037, T051 and T072). This integration also carries the separately tested T062 solver diagnostics, T071 discrete-event simulation and T087 reproducibility ZIP into the same branch. The combined Workbench contains 65 distinct stable target IDs with focused runner branches after adding T046, including the trust/help/support actions; each remains pending authenticated end-to-end verification. Other existing module workflows may cover additional targets, but they are not counted as focused runners unless wired to the stable target ID and its execution gate. The implementation matrix links every target to its minimum tier, contracts, evidence tests and remaining limitations.

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


### CAPA and 8D register review (T039)

T039 is wired into the existing Workbench and has a deterministic record-review engine in `shoir_target_engines.py`. It validates CAPA IDs and status values, checks the D1–D8 completeness fields, flags overdue actions, and requires relevant implementation/closure evidence for records marked closed. It distinguishes a missing-field/due-date review from proof that a root cause is correct, a corrective action is effective, or an 8D system complies with a standard.

The UI's editable JSON list and as-of date feed the method through the normal authenticated focused-tool execution gate and shared result/input snapshot helper. Unit fixtures and a Streamlit AppTest cover incomplete/overdue records, closed-record evidence and visible synthetic provenance. T039 is now classified `IMPLEMENTED_NEEDS_VALIDATION`, rather than `FOUNDATION_ONLY`, because a real execution path and method exist. Durable save/reload/re-login, attachment handling, explicit approval/status-transition audit history and authenticated workspace-isolation tests remain unresolved. It must not be described as a complete electronic CAPA lifecycle until these are implemented and verified.

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

### Ergonomics: Revised NIOSH Lifting Equation (T046)

T046 now has an execution path in the existing Workbench using `shoir_ergonomics.py`, not a generic ergonomic risk score. It calculates the single-task Revised NIOSH Lifting Equation (RNLE) for an explicitly confirmed two-handed standing lifting task: endpoint horizontal/vertical/asymmetry multipliers, distance multiplier, Table 5 frequency multiplier (linear interpolation between table rows), independently classified origin/destination coupling multipliers from Table 7, the lower endpoint recommended weight limit (RWL), and lifting index (`LI = load / RWL`).

The calculation uses the NIOSH 23 kg load constant and documents the method/source, formulas, entered-data provenance, assumptions and warnings. Table 5 and Table 7 use the vertical category boundary of 30 inches (76.2 cm); this was explicitly tested after review of the official NIOSH manual. Origin and destination coupling quality are separate inputs. For frequencies below 0.1 lift/minute, the method requires the usual <=1 hour duration category or a qualified confirmation rather than silently applying an inconsistent duration category. The code rejects invalid/non-finite measurements and zero frequency multipliers, and requires the user to confirm that the task is within scope before it runs. Official method reference: [NIOSH Applications Manual 94-110, revised September 2021](https://www.cdc.gov/niosh/docs/94-110/).

The supported calculation is deliberately limited: it is not a multiple-task RNLE assessment, it does not cover every lifting situation, and an LI or RWL alone does not certify a task or establish medical/safety suitability. Qualified review and accurate field measurements are still required. Golden, interpolation, coupling and boundary fixtures plus a Workbench AppTest have been added. T046 remains `IMPLEMENTED_NEEDS_VALIDATION`; hosted authenticated browser, tier-denial, durable persistence/re-login, cross-workspace isolation and Arabic/RTL checks have not been completed.

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
| `IMPLEMENTED_NEEDS_VALIDATION` | 89 |
| `FOUNDATION_ONLY` | 9 |
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
