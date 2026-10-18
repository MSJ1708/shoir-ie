# Shoir-IE: Module Rendering & Workforce-Readiness Audit

**Repository:** [MSJ1708/shoir-ie](https://github.com/MSJ1708/shoir-ie)  
**Audit snapshot:** 18 October 2026  
**Audit type:** Static source/catalogue review plus engineering acceptance plan; not a claim that all browser tests passed.

## Executive status

- The repository has 96 distinct catalogue labels after de-duplication. The legacy catalogue has 56 entries and the platform catalogue has 42; two labels repeat across those lists: Research AI and Production Bottleneck & Capacity Recovery Study. The actual distinct inventory is therefore 96, not 88–92.
- A confirmed shared export argument-order bug was fixed and merged in [commit eba42bb](https://github.com/MSJ1708/shoir-ie/commit/eba42bbd34d925b2b48f44fec894bae08e1d90ba). Legacy module renderers could send a tier and username into figure parameters, causing export entitlement to fall back to Starter or chart/export paths to behave incorrectly. The fix normalizes these call styles and adds regression tests.
- Five GitHub Actions workflows for that fix were recorded as successful: engine regression, security/quality, application tests, platform tests and the repository validation workflow. Passing code/test workflows does not certify every Streamlit module's visual rendering.
- The hosted Streamlit page could not be inspected in the available browser path during this audit. Every module in this document is therefore marked as source-reviewed, not browser-certified. Actual screenshots, interaction checks and downloaded-file validation remain required.
- High-priority areas for live verification include Excel cleaning upload-to-download, Facility Layout department/From-To/SLP rendering, Enterprise Integration & Collaboration recovery diagnostics, persistence/restart, tier enforcement, shared exports and the capacity study's observed-versus-simulated distinctions.

Priority meanings: **P0** = trust, security, persistence, import/export or navigation blocker; **P1** = major engineering workflow/reliability requirement; **P2** = advanced enhancement/specialized assurance. Priorities are recommendations, not a statement that the module has a confirmed defect.

## Cross-cutting rendering and reliability gates

1. **Route and heading:** open every module from category navigation and global search/deep-link where supported. Confirm correct title, category, controls and non-blank content.
2. **Empty and populated states:** test without uploaded data, with valid data, missing fields and malformed data. Upload must remain optional unless the module genuinely requires data.
3. **State and navigation:** edit values, run, change a parameter, switch away/back, reset and reload. There must be no NameError, duplicate widget/key exception, stale result or unrelated module fallback.
4. **Charts:** verify labels, axes, units, legend, responsive layout and empty-state handling. Tables must remain usable if a chart cannot render.
5. **Calculations:** use an independent golden fixture for each primary domain method; check units, bounds, missing values, solver status and agreement between KPI, table and chart.
6. **Downloads:** open every offered XLSX/PDF/PPTX/ZIP with a parser; check content, non-empty payload, charts where promised, MIME/file name, assumptions and lineage.
7. **Entitlements:** test menu, direct route, search, Copilot, API and export paths. Server-side authorization must deny restricted actions without mutating data.
8. **Persistence/recovery:** save, reload and restore; simulate database/connector outage and failed write. Fail safely without destroying prior work.
9. **Data status:** label LIVE / IMPORTED / SYNTHETIC / STALE / OFFLINE and preserve source timestamp, assumptions and evidence classification in every export.
10. **Responsive/accessibility:** test desktop and narrow viewport, Unicode/long labels, Arabic/RTL, currency/date display, keyboard focus and table alternatives.
11. **CI/browser suite:** compilation and unit tests do not prove browser layout. CI should eventually emit a result per module and store screenshots/logs for failures.
12. **Single registry:** move stable ID, canonical name, aliases, tier, category, renderer, expected inputs/outputs, sub-tools and smoke-test ID into one authoritative manifest; fail CI on missing renderer/test or unintended duplicate aliases.

## Module-by-module improvement register

**Distinct modules:** 96 · **P0:** 10 · **P1:** 56 · **P2:** 30

### Core Platform, Data and Facilities

#### 1. MILP Solvers

- **Priority:** P1
- **Improve:** Guided variables/objective/constraints builder with unit, bounds and solver-status explanation.
- **Sub-tools / capability gaps to add or deepen:** Add infeasibility/conflict hints, shadow prices, sensitivity, saved models; test optimal/infeasible/unbounded and independently recompute objective.

#### 2. Inventory Playback

- **Priority:** P1
- **Improve:** Link time-phased demand, supply, lead time and stock position to replenishment decisions.
- **Sub-tools / capability gaps to add or deepen:** Add safety stock/reorder points, ABC/XYZ, stockout timeline, service and cost comparison; test zero/intermittent demand and inventory conservation.

#### 3. Core IE Tools

- **Priority:** P1
- **Improve:** Connect common formulas through shared validated inputs, units and visible assumptions.
- **Sub-tools / capability gaps to add or deepen:** Add takt, cycle time, capacity, OEE, Little's Law and line balance; test golden hand calculations and zero/mixed-unit cases.

#### 4. Subscriptions

- **Priority:** P0
- **Improve:** Make displayed plan match server-enforced entitlements and subscription/trial state.
- **Sub-tools / capability gaps to add or deepen:** Add invoice history, renewal/expiry, payment failures and entitlement preview; test tier boundaries, expired accounts and direct-route denial.

#### 5. Persistence

- **Priority:** P0
- **Improve:** Expose backend health, last save, migrations and recoverable workspace status.
- **Sub-tools / capability gaps to add or deepen:** Add snapshot/restore, backups, retry and conflict handling; edit/reload/restart and simulate DB outage without losing old data.

#### 6. Venture Studio

- **Priority:** P1
- **Improve:** Connect customer discovery, hypotheses, pilots, ROI and investor claims to sourced evidence.
- **Sub-tools / capability gaps to add or deepen:** Add interview log, pilot stage gates, baseline/post metrics, evidence vault and gated investor room; test incomplete pilots and unsupported ROI claims.

#### 7. Facility Layout & Warehousing

- **Priority:** P0
- **Improve:** Complete department-to-From/To-to-SLP-to-block-layout workflow and trace distances/cost.
- **Sub-tools / capability gaps to add or deepen:** Add department editor, relationship weights, flow heatmap, layout alternatives and handling-cost comparison; test blank departments, missing flows and exports.

#### 8. Enterprise Integration & Collaboration

- **Priority:** P0
- **Improve:** Make connector and collaboration success/failure states actionable instead of generic recovery only.
- **Sub-tools / capability gaps to add or deepen:** Add connection profiles, field mapping, test/sync/retry log, comments and conflict handling; test bad credentials, offline endpoints and permission denial.


### Supply Chain, Production and Shop-Floor

#### 9. Carbon Accounting

- **Priority:** P1
- **Improve:** Version reporting boundary, scope, units, activity source and emissions factors for every result.
- **Sub-tools / capability gaps to add or deepen:** Add Scope 1/2/3 ledger, factor source/date, uncertainty and baseline waterfall; reproduce CO2e totals independently and test missing factors.

#### 10. IoT Digital Twin

- **Priority:** P1
- **Improve:** Clearly distinguish live, imported, synthetic, stale and offline telemetry.
- **Sub-tools / capability gaps to add or deepen:** Add protocol health, replay, schema/unit mapping, gap/outlier alerts and buffer status; test stale, duplicate and out-of-order readings.

#### 11. MEIO Matrix

- **Priority:** P1
- **Improve:** Model multi-echelon stock and lead-time propagation across suppliers, hubs, sites and demand.
- **Sub-tools / capability gaps to add or deepen:** Add echelon targets, fill-rate heatmap, shortages, holding/shortage costs and sensitivity; test capacity loss and stock conservation.

#### 12. Slotting & Gantt

- **Priority:** P2
- **Improve:** Connect slot recommendations to item velocity, dimensions, compatibility and schedule constraints.
- **Sub-tools / capability gaps to add or deepen:** Add ABC pick frequency, capacity zones, editable timeline and replenishment windows; test duplicate slots, over-capacity and narrow layout.

#### 13. Fleet Routing

- **Priority:** P1
- **Improve:** Include vehicle capacity, depots, shifts, time windows and service durations in route feasibility.
- **Sub-tools / capability gaps to add or deepen:** Add route map, utilization, missed windows, unserved stops, emissions/cost breakdown; test infeasible, unreachable and single-stop routes.

#### 14. Warehouse Heatmap

- **Priority:** P2
- **Improve:** Link zones to occupancy, pick frequency, replenishment and congestion with a usable legend.
- **Sub-tools / capability gaps to add or deepen:** Add layer selector, threshold editor, aisle coordinates and pick-path overlay; test empty zones, equal values and missing coordinates.

#### 15. Supplier Risk Matrix

- **Priority:** P1
- **Improve:** Expose risk-score components, weights, evidence dates, owners and change history.
- **Sub-tools / capability gaps to add or deepen:** Add supplier concentration, mitigations, alternate sourcing and trend charts; test missing scores and weights so missing evidence never means zero risk.

#### 16. Scenarios

- **Priority:** P1
- **Improve:** Persist reproducible baselines and alternatives with assumptions, owner, timestamp and model/data versions.
- **Sub-tools / capability gaps to add or deepen:** Add branching, parameter diffs, KPI comparisons and restore; verify changed inputs invalidate prior results until rerun.

#### 17. AGV Fleet Dispatcher

- **Priority:** P1
- **Improve:** Respect battery, charging, vehicle availability, blocked paths and station capacity.
- **Sub-tools / capability gaps to add or deepen:** Add task queue, fleet map, battery scheduler, congestion alerts and replay; test depleted battery, duplicate tasks and no-AGV states.

#### 18. Geospatial Network Designer

- **Priority:** P2
- **Improve:** Validate coordinate systems and compare facilities/territories on demand, capacity and travel time.
- **Sub-tools / capability gaps to add or deepen:** Add candidate scoring, distance/time matrix, territory assignment and map fallback; test invalid coordinates, duplicate locations and missing map tiles.

#### 19. Production Planning & Control (PPC)

- **Priority:** P1
- **Improve:** Link demand, BOM/material availability and work-center capacity into time-phased orders.
- **Sub-tools / capability gaps to add or deepen:** Add MRP exception list, load chart, order priorities, late-order drilldown and planned-vs-actual; test shortages, overloaded centers and dates.

#### 20. Production Bottleneck & Capacity Recovery Study

- **Priority:** P0
- **Improve:** Keep calculated OEE separate from simulated recovery and treat lowest OEE only as a candidate constraint.
- **Sub-tools / capability gaps to add or deepen:** Add throughput/WIP/queue/routing evidence, recovery waterfall and scenario comparison; test independent OEE values, zero output, warning and Excel hash.

#### 21. Lean Manufacturing & Shop Floor Operations

- **Priority:** P1
- **Improve:** Connect observed work elements, waste and corrective actions to measured before/after changes.
- **Sub-tools / capability gaps to add or deepen:** Add value-stream map, takt/cycle comparison, spaghetti diagram, kaizen log and standard work; never claim savings before post-change measurements.

#### 22. Quality Control, Six Sigma & Reliability

- **Priority:** P1
- **Improve:** Guide method choice and disclose sample size, measurement quality and assumptions.
- **Sub-tools / capability gaps to add or deepen:** Add SPC chart family, Cp/Cpk, Gage R&R, DOE/ANOVA, Pareto/FMEA and Weibull; validate reference fixtures and small-sample warnings.


### Operations, Automation and Industrial Analytics

#### 23. Engineering Economics & Finance

- **Priority:** P1
- **Improve:** Make cash-flow timing, discount, inflation, lifetime, tax and residual-value assumptions explicit.
- **Sub-tools / capability gaps to add or deepen:** Add NPV/IRR/payback, cash-flow timeline, tornado and break-even; test independent financial examples and undefined IRR.

#### 24. AI Copilot

- **Priority:** P1
- **Improve:** Separate suggestions, proposed plans, executed steps and verified outputs with source traceability.
- **Sub-tools / capability gaps to add or deepen:** Add dry-run, routing confidence, step progress, approval, cancel/retry and runtime budget; test ambiguous prompts, no data and tool failures.

#### 25. FastAPI Gateway

- **Priority:** P1
- **Improve:** Expose deployment and API health and enforce auth/scopes, rate limits and schemas server-side.
- **Sub-tools / capability gaps to add or deepen:** Add OpenAPI, key lifecycle, readiness probe, redacted request logs and idempotency; test unauthorized calls, invalid payload and throttling.

#### 26. Monte Carlo Sim

- **Priority:** P1
- **Improve:** Make distributions, correlation assumptions, seed and convergence visible.
- **Sub-tools / capability gaps to add or deepen:** Add distribution-fit, percentile fan chart, convergence trace and run seed export; same seeds must reproduce output and invalid distributions must fail safely.

#### 27. Sensitivity Analysis

- **Priority:** P1
- **Improve:** Separate one-at-a-time and global/correlated sensitivity with units and a clear baseline.
- **Sub-tools / capability gaps to add or deepen:** Add tornado, break-even finder, response surface and ranked drivers; test constant inputs, correlations and agreement with result tables.

#### 28. Webhook Alerts

- **Priority:** P1
- **Improve:** Make message delivery observable and prevent duplicated or unbounded retries.
- **Sub-tools / capability gaps to add or deepen:** Add test-send, signed payload, idempotency, retry/dead-letter and secret rotation; test timeout and 4xx/5xx with no duplicate alert.

#### 29. Agentic Workflows

- **Priority:** P1
- **Improve:** Type every action, enforce permissions, require approval for writes and bound time/cost.
- **Sub-tools / capability gaps to add or deepen:** Add workflow graph, dry-run, checkpoints, retry/rollback and audit steps; test cycle, timeout and partial failure without downstream writes.

#### 30. Control Tower

- **Priority:** P1
- **Improve:** Show source, freshness, threshold, owner and drilldown on every KPI/risk card.
- **Sub-tools / capability gaps to add or deepen:** Add incident timeline, acknowledgements, shift/facility filters and trends; test missing feeds and ensure null data is not shown as healthy zero.

#### 31. Cryptographic Ledger

- **Priority:** P1
- **Improve:** Document proof scope and canonicalize entries so integrity is not confused with engineering truth.
- **Sub-tools / capability gaps to add or deepen:** Add verification, signature/key version, rotation and tamper diff; delete/reorder/change records and ensure verification fails visibly.

#### 32. Predictive Maintenance Hub

- **Priority:** P1
- **Improve:** Separate heuristic scores from calibrated predictions, with horizon and false-positive/negative evidence.
- **Sub-tools / capability gaps to add or deepen:** Add asset ranking, sensor quality, threshold tuning, remaining-life interval and work-order feedback; test drift, missing sensors and time leakage.

#### 33. Human Factors & Ergonomics (NIOSH)

- **Priority:** P2
- **Improve:** Expose task/job assumptions and choose the suitable ergonomic method for the exposure.
- **Sub-tools / capability gaps to add or deepen:** Add applicable NIOSH lifting, RULA/REBA, exposure duration and reassessment; test units and invalid variables with method scope explained.

#### 34. Digital Twin & Discrete-Event Simulation

- **Priority:** P1
- **Improve:** Support editable route/queue/resource models, warm-up, replications and calibration.
- **Sub-tools / capability gaps to add or deepen:** Add process editor, WIP/utilization dashboard, confidence intervals and experiments; test flow conservation, overload and seed reproducibility.

#### 35. Green IE & Sustainability

- **Priority:** P2
- **Improve:** Link resource/waste flows to boundaries and source-backed factors across alternatives.
- **Sub-tools / capability gaps to add or deepen:** Add Sankey, circularity decomposition, recovery scenarios and uncertainty; check mass/energy balance and label assumptions versus measurements.

#### 36. Research AI

- **Priority:** P1
- **Improve:** Ground responses in uploaded sources or verified references and expose missing-source warnings.
- **Sub-tools / capability gaps to add or deepen:** Add document ingestion, citations, claim-to-source table and reproducible protocol; test conflicting sources and unsupported citations.


### Research, Formal Methods and Advanced Computation

#### 37. Evidence Degradation & Decision-Readiness Lab

- **Priority:** P2
- **Improve:** Score freshness, provenance, reproducibility and contradictions using visible rules.
- **Sub-tools / capability gaps to add or deepen:** Add evidence timeline, score decomposition, contradiction links and refresh tasks; test stale/conflicting evidence and preserve source immutability.

#### 38. Statistical Hypothesis Testing

- **Priority:** P1
- **Improve:** Report effect sizes, confidence intervals and assumption diagnostics beside p-values.
- **Sub-tools / capability gaps to add or deepen:** Add test chooser, power/sample size, variance checks and multiple-comparison correction; validate golden data and small-sample cases.

#### 39. LaTeX Document Formatter

- **Priority:** P2
- **Improve:** Keep source intact and show compiler errors with useful locations and build status.
- **Sub-tools / capability gaps to add or deepen:** Add templates, bibliography checks, PDF preview and source bundle; test missing packages, broken citations and Arabic/Unicode.

#### 40. Literature & Citation Matrix

- **Priority:** P2
- **Improve:** Track query date, deduplicated papers, screening decisions and extraction confidence.
- **Sub-tools / capability gaps to add or deepen:** Add DOI resolver, inclusion workflow, study-quality tags and BibTeX/RIS/CSV exports; never fabricate missing citation metadata.

#### 41. Advanced Regression Analysis

- **Priority:** P1
- **Improve:** Pair coefficients with residuals, cross-validation, intervals and leakage/multicollinearity checks.
- **Sub-tools / capability gaps to add or deepen:** Add QQ/residual plots, VIF, time-aware splits and robust/regularized models; test constant columns, missing predictors and small samples.

#### 42. Live Reproducible Paper Canvas

- **Priority:** P2
- **Improve:** Bind text, figures, data and formulas to immutable run/version IDs.
- **Sub-tools / capability gaps to add or deepen:** Add notebook cells, figure registry, bibliography, environment manifest and version diff; repeat builds and compare artifact hashes.

#### 43. Paper-to-Simulation Auto-Engine

- **Priority:** P2
- **Improve:** Separate paper-extracted values from inferred parameters and request approval before running.
- **Sub-tools / capability gaps to add or deepen:** Add page-cited parameter table, unit normalization, calibration and paper-vs-model comparison; inferred values must be flagged and confirmed.

#### 44. Automated Theory-to-Code Formalizer

- **Priority:** P2
- **Improve:** Require types, domains, units, assumptions and invariants before code generation.
- **Sub-tools / capability gaps to add or deepen:** Add equation editor, dimensional analysis, sandbox and test vectors; reject under-specified or dimensionally inconsistent expressions.

#### 45. Automated Code-to-Formal-Proof Verifier

- **Priority:** P2
- **Improve:** Distinguish proved, disproved, unknown and timeout with supported-language limits.
- **Sub-tools / capability gaps to add or deepen:** Add proof obligations, counterexample, proof trace and assumption ledger; unsupported constructs must never return proved.

#### 46. Adversarially Stressed Synthetic Industrial Twins

- **Priority:** P2
- **Improve:** Keep synthetic provenance and shock severity visible; compare to baseline and invariants.
- **Sub-tools / capability gaps to add or deepen:** Add shock coverage, invariant monitor and stress-vs-baseline graph; test extremes and seeds, never label synthetic readings as live.

#### 47. Adversarial AI Peer-Review Swarm

- **Priority:** P2
- **Improve:** Require reviews to cite claims/methods and separate fact checks from reviewer opinion.
- **Sub-tools / capability gaps to add or deepen:** Add reviewer roles, claim evidence map, severity/confidence and response tracker; human adjudication required for conflicting critiques.

#### 48. Adversarial Chaos & Shock Injector

- **Priority:** P2
- **Improve:** Keep disruptions sandboxed with blast-radius preview and guaranteed stop/reset controls.
- **Sub-tools / capability gaps to add or deepen:** Add scenario library, seed, rollback and recovery checklist; verify no external writes without explicit approval.

#### 49. Autonomous Parametric Surrogate Swarm

- **Priority:** P2
- **Improve:** Show training domain, validation error and extrapolation risk before a surrogate supports a decision.
- **Sub-tools / capability gaps to add or deepen:** Add ensemble comparison, active learning, uncertainty bands and domain coverage; test out-of-domain inputs against held-out truth.

#### 50. Real-Time Quantum-Classical Hybrid Optimization Router

- **Priority:** P2
- **Improve:** Show actual solver/backend, support limits and fallback behavior; do not imply quantum execution without evidence.
- **Sub-tools / capability gaps to add or deepen:** Add backend capability table, classical baseline and runtime/cost compare; simulate unavailable backend and verify fallback label.

#### 51. Decentralized Cryptographic Reproducibility Vault

- **Priority:** P2
- **Improve:** Sign manifests for code/data/environment/output and state exactly what each proof demonstrates.
- **Sub-tools / capability gaps to add or deepen:** Add key identity/rotation, verifier and revocation; independently tamper with each artifact and identify the changed component.

#### 52. 🔌 Edge-Connected IoT Digital Twin Bridge

- **Priority:** P2
- **Improve:** Separate sample runner from deployed connector and expose setup and credential failures.
- **Sub-tools / capability gaps to add or deepen:** Add protocol wizard, secret/certificate rotation, schema mapping, offline buffer and replay; test offline broker and stale credentials.

#### 53. 🔌 Universal Cross-Domain Mathematical Isomorphism Engine (UCMIE)

- **Priority:** P2
- **Improve:** Require a mapping contract for variables, dimensions, constraints and proof obligations before claiming equivalence.
- **Sub-tools / capability gaps to add or deepen:** Add ontology mapping, unit validation, confidence and counterexamples; inconsistent models must return equivalence not established.

#### 54. 🔄 Autonomous Epistemic Cross-Disciplinary Falsification Matrix (AE-FRESM)

- **Priority:** P2
- **Improve:** Pre-register hypotheses and tie attempts to methods, evidence and counterexamples.
- **Sub-tools / capability gaps to add or deepen:** Add falsification matrix, preregistration, assumption sensitivity and contradiction queue; preserve inconclusive/rejected results.

#### 55. Autonomous Cognitive Operations & Zero-Knowledge Mesh (ACO-ZKMS)

- **Priority:** P2
- **Improve:** Specify identity, least privilege, trust boundaries and cryptographic proof scope.
- **Sub-tools / capability gaps to add or deepen:** Add policy simulation, signed identities, key lifecycle and threat-model checklist; test revoked identity and cross-workspace denial.

#### 56. ⚡ ACO-ZKMS Master Engine

- **Priority:** P2
- **Improve:** Represent orchestration as a controlled graph with fail-closed gates and auditable completion.
- **Sub-tools / capability gaps to add or deepen:** Add approval gates, health checks, rollback and signed execution record; test cyclic plans and unavailable sub-agents.


### Platform, Governance, Digital Thread and Enterprise Modules

#### 57. Excel Data Cleaning & Import

- **Priority:** P0
- **Improve:** Preserve raw sheets and provide before/after preview, detected headers, cleaning audit and working output download.
- **Sub-tools / capability gaps to add or deepen:** Add merged/multi-row header repair, type/date normalization, duplicate policy and data dictionary; test multi-sheet valid/corrupt/large files and open downloads.

#### 58. Industrial Workbook

- **Priority:** P0
- **Improve:** Complete the Inputs/Data/Calculations/KPIs/Simulation/Optimization/Scenarios/Decisions/Dashboard flow.
- **Sub-tools / capability gaps to add or deepen:** Add formula dependency trace, safe recalc, named ranges, undo/redo and workbook health; test formulas, sheet switching and export round-trip.

#### 59. Industrial Operating System

- **Priority:** P1
- **Improve:** Lead with source freshness, actionable risks and working links to the underlying KPI/module.
- **Sub-tools / capability gaps to add or deepen:** Add model health, action register, scenario compare and outcome verification; missing data must not appear as verified zero or savings.

#### 60. Global Project & Digital Thread

- **Priority:** P1
- **Improve:** Connect datasets, assets, models, experiments, decisions and outcomes in a searchable relationship graph.
- **Sub-tools / capability gaps to add or deepen:** Add lineage/impact analysis, orphan detection, owner/version timeline and graph export; test broken links and workspace isolation.

#### 61. Engineering Validation Center

- **Priority:** P1
- **Improve:** Use reusable domain rules, named units and cross-field checks with repair preview.
- **Sub-tools / capability gaps to add or deepen:** Add schema contracts, formula integrity, rule severity and downloadable reports; test valid/invalid fixtures and no-upload empty state.

#### 62. Industrial Data Model & Digital Thread

- **Priority:** P1
- **Improve:** Define canonical entities, relationship cardinality and schema versions with referential integrity.
- **Sub-tools / capability gaps to add or deepen:** Add schema registry, lineage browser, orphan/duplicate report and change impact; test duplicate IDs, dangling links and persistence.

#### 63. Advanced Planning & Scheduling

- **Priority:** P1
- **Improve:** Schedule finite machine/labor capacity, setup, material, shifts, maintenance and due dates.
- **Sub-tools / capability gaps to add or deepen:** Add interactive Gantt, sequencing, lateness, freeze horizon and rescheduling; verify no overbooked resource or unavailable material.

#### 64. Quality Engineering & Reliability

- **Priority:** P1
- **Improve:** Unify quality/reliability methods with sample adequacy and explicit assumptions.
- **Sub-tools / capability gaps to add or deepen:** Add SPC, capability, Gage R&R, DOE/ANOVA, FMEA and Weibull; use golden fixtures for each method and edge case.

#### 65. Capital Investment & Engineering Economics

- **Priority:** P1
- **Improve:** Expose full cash-flow/lifecycle assumptions and keep uncertainty visible.
- **Sub-tools / capability gaps to add or deepen:** Add NPV/IRR/payback, annual cash flow, tax/inflation settings, break-even and sensitivity; cross-check independently calculated cases.

#### 66. Workforce Engineering

- **Priority:** P1
- **Improve:** Join task standards, takt/demand, skills, shifts, overtime and ergonomic limits.
- **Sub-tools / capability gaps to add or deepen:** Add line balance, staffing calculator, skills matrix and workload warnings; test skill mismatch, absenteeism and impossible takt.

#### 67. Industrial Sustainability & LCA

- **Priority:** P2
- **Improve:** Version lifecycle boundaries and factors across materials, energy, water and emissions.
- **Sub-tools / capability gaps to add or deepen:** Add impact categories, uncertainty, stage-level factors and baseline compare; flag missing stages and reproduce visible totals.

#### 68. Benchmarking & Engineering Standards

- **Priority:** P2
- **Improve:** Require benchmark source/date/geography/unit and relevant peer group before comparison.
- **Sub-tools / capability gaps to add or deepen:** Add source registry, unit normalization, target history and percentile view; block stale or incompatible comparisons.

#### 69. Manufacturing Execution System

- **Priority:** P1
- **Improve:** Separate sandbox from real MES write; reconcile order, event, downtime, scrap and genealogy status.
- **Sub-tools / capability gaps to add or deepen:** Add dispatch/confirmation, WIP, traceability, quality release and sync reconciliation; test duplicates and missing acknowledgements.

#### 70. Industrial Simulation Lab

- **Priority:** P1
- **Improve:** Add process editing, input distributions, warm-up, replications and calibration before scenario comparison.
- **Sub-tools / capability gaps to add or deepen:** Add method selector, process map, output analysis and experiment matrix; verify seed reproducibility and baseline calibration.

#### 71. 3D Factory Designer

- **Priority:** P2
- **Improve:** Tie scale and geometry to equipment/aisle dimensions, travel paths and a saved facility version.
- **Sub-tools / capability gaps to add or deepen:** Add snapping, collision/clearance, coordinate import and layout alternatives; test overlap, missing coordinates and viewport resizing.

#### 72. Industrial Connectivity Hub

- **Priority:** P1
- **Improve:** Make configure/validate/map/test/sync/monitor/disconnect an explicit connector lifecycle.
- **Sub-tools / capability gaps to add or deepen:** Add REST/SQL/MQTT/OPC-UA profiles, least-privilege scope, retries and dead-letter; test timeout/auth/schema drift without secret leakage.

#### 73. Multi-Objective Optimization

- **Priority:** P1
- **Improve:** Make Pareto feasibility, normalization, units and dominance explanations visible.
- **Sub-tools / capability gaps to add or deepen:** Add Pareto frontier, epsilon/weight options and trade-off table; compare plotted points with result rows on reference problems.

#### 74. Robust & Resilient Optimization

- **Priority:** P1
- **Improve:** Expose uncertainty sets and compare nominal, worst-case and risk-aware solution quality.
- **Sub-tools / capability gaps to add or deepen:** Add disruptions, chance constraints where supported, CVaR and recovery profile; test infeasible scenarios and clearly show solver status.

#### 75. Engineering Model Registry

- **Priority:** P1
- **Improve:** Version immutable model/input/environment/result manifests with owner, approval and lineage.
- **Sub-tools / capability gaps to add or deepen:** Add version diff, promotion gates, dependency versions, replay and rollback; modify an input and verify hash mismatch is detected.

#### 76. Experiment Lab

- **Priority:** P1
- **Improve:** Make factors, baseline, seed, replicates and model/data version first-class.
- **Sub-tools / capability gaps to add or deepen:** Add scenario matrix, batch run, confidence intervals, KPI deltas and history; verify repeatability and stored input hash.

#### 77. Experiment Engine

- **Priority:** P1
- **Improve:** Expose DOE design choice, randomization, factors/levels, sample-size and effect assumptions.
- **Sub-tools / capability gaps to add or deepen:** Add factorial/fractional design, response surface, bootstrap and ANOVA/effect plots; validate generated runs against references.

#### 78. Industrial Control Center

- **Priority:** P1
- **Improve:** Give every risk card source, freshness, threshold, owner and working drilldown.
- **Sub-tools / capability gaps to add or deepen:** Add incident timeline, acknowledgement, facility/shift filters, KPI trend and action register; test missing-feed and threshold cases.

#### 79. ShadowShift — Micro-Loss & Recovery Intelligence

- **Priority:** P1
- **Improve:** Keep observed interruption/recovery separate from extrapolated exposure and verified benefit.
- **Sub-tools / capability gaps to add or deepen:** Add micro-loss Pareto, observation coverage, evidence-gap ranking, experiment register and hashed export; test small samples and duplicated events.

#### 80. Engineering Decision Center

- **Priority:** P1
- **Improve:** Record alternatives, assumptions, uncertainty, owner, approval and outcome measure for each decision.
- **Sub-tools / capability gaps to add or deepen:** Add decision cards, approval history, reversibility, follow-up and actual-vs-expected verification; test unauthorized approvals.

#### 81. Industrial Data Platform

- **Priority:** P1
- **Improve:** Make ingestion, schema, validation, version and freshness reusable across module workflows.
- **Sub-tools / capability gaps to add or deepen:** Add dataset catalog, contracts, lineage, incremental sync and quarantine; test oversized/corrupt files and schema drift.

#### 82. Advanced Engineering Copilot

- **Priority:** P1
- **Improve:** Show method choice, provenance, permissions, cost/time bounds and per-step execution truth.
- **Sub-tools / capability gaps to add or deepen:** Add dry run, route confidence, resume/cancel, retry and approval queue; test unavailable tools and partial execution.

#### 83. Live Industrial Digital Twin

- **Priority:** P1
- **Improve:** Show live/simulated status, sync lag, asset match confidence and sensor freshness.
- **Sub-tools / capability gaps to add or deepen:** Add event timeline, stale-state/drift, asset-process map and playback; test disconnect/time skew and don't imply control where none exists.

#### 84. Advanced ML Demand Forecasting

- **Priority:** P1
- **Improve:** Use rolling backtests, seasonality, external regressors and intervals alongside point forecast.
- **Sub-tools / capability gaps to add or deepen:** Add naive baseline, model leaderboard, residual diagnostics and drift; test sparse history, missing regressors and leakage.

#### 85. Scenario Versioning & Comparison

- **Priority:** P1
- **Improve:** Show differences in inputs, formula, constraints and data source with baseline restore.
- **Sub-tools / capability gaps to add or deepen:** Add version branches, parameter diffs, KPI deltas and ownership; test save/change/compare/restore and stale-result invalidation.

#### 86. Team Workspaces & RBAC

- **Priority:** P0
- **Improve:** Enforce workspace/tenant isolation server-side for datasets, artifacts, runs and exports.
- **Sub-tools / capability gaps to add or deepen:** Add per-action role matrix, invites/deprovision, ownership transfer and audit; test cross-workspace access and direct-route bypass.

#### 87. Executive Report Center

- **Priority:** P0
- **Improve:** Validate that exported files are non-empty, readable and consistent with on-screen results.
- **Sub-tools / capability gaps to add or deepen:** Add branded templates, chart selection, uncertainty/limitations page and export history; parse XLSX/PDF/PPTX and test pagination/empty charts.

#### 88. Predictive Maintenance Digital Twin

- **Priority:** P1
- **Improve:** Tie asset state and maintenance history to a versioned, calibrated risk model and horizon.
- **Sub-tools / capability gaps to add or deepen:** Add sensor mapping, remaining-life interval, work-order scenario and model drift; test gaps, unseen assets and time-separated validation.

#### 89. Localization & Multi-Currency

- **Priority:** P1
- **Improve:** Keep ISO codes, rate source/date, original amount and conversion assumptions.
- **Sub-tools / capability gaps to add or deepen:** Add locked-rate scenario, local number/date format, SAR and Arabic/RTL QA; test missing rates, reversed rates and timezone boundaries.

#### 90. Enterprise Security & Governance

- **Priority:** P0
- **Improve:** Show actual configured identity/MFA/retention/isolation state, not feature placeholders.
- **Sub-tools / capability gaps to add or deepen:** Add SSO/OIDC/MFA/SCIM status, policy editor, audit export and retention workflow; test expiry, unauthorized export and role bypass.

#### 91. Autonomous Global Supply Chain & Resilient Logistics Network

- **Priority:** P1
- **Improve:** Model supplier tiers, capacities, lead-time variation, disruptions and explicit shortage penalty.
- **Sub-tools / capability gaps to add or deepen:** Add supplier-outage scenarios, Monte Carlo service, alternate sourcing, carbon/cost trade-off; reconcile flow and mark synthetic data.

#### 92. Zero-Waste Closed-Loop Mega-Factory (Industrial Symbiosis Engine)

- **Priority:** P2
- **Improve:** Respect captured supply, reuse demand and quality/capacity limits across material/water/heat flows.
- **Sub-tools / capability gaps to add or deepen:** Add process Sankey, recovery yield, residual waste and cost/carbon marginal view; test balances and never assume 100% circularity.

#### 93. Real-Time Urban Mobility & Smart Infrastructure Grid

- **Priority:** P2
- **Improve:** Distinguish synthetic junction data from live feeds and show network timestamps/calibration.
- **Sub-tools / capability gaps to add or deepen:** Add road/transit map, peak scenarios, capacity, delay and emissions proxies; test disconnected graph and label proxy metrics.

#### 94. Fully Automated Emergency Response & Humanitarian Disaster Logistics System

- **Priority:** P1
- **Improve:** Expose demand urgency, equity, stock and vehicle capacity constraints; keep human coordination authoritative.
- **Sub-tools / capability gaps to add or deepen:** Add allocation policy, depot outages, last-mile routing, unmet-demand map and approval log; test inadequate supply without hiding shortage.

#### 95. Autonomous Kinetic-Digital Twin (AKDT) for Industrial Logistics Resilience

- **Priority:** P2
- **Improve:** Expose sandbox/live boundary, telemetry confidence, edge buffering and recovery assumptions.
- **Sub-tools / capability gaps to add or deepen:** Add synthetic replay, state timeline, buffer overflow and baseline/recovery comparison; test offline buffers and duplicate/mismatched events.

#### 96. L-SIMS — Local Capability & Dynamic Industrial Readiness Simulator

- **Priority:** P2
- **Improve:** Model local capability by part family, demand, qualified capacity, lead time and confidence.
- **Sub-tools / capability gaps to add or deepen:** Add capability gap map, supplier/repair directory and qualification milestones; distinguish observed from estimated/unqualified capacity.

## Findings requiring closure evidence

| ID | Priority | Finding | Closure evidence |
|---|---|---|---|
| R-01 | Fixed in main | Export-bar argument order could cause old module calls to pass tier/username as figures and drop entitlement context. | Merged fix and regression coverage: [commit eba42bb](https://github.com/MSJ1708/shoir-ie/commit/eba42bbd34d925b2b48f44fec894bae08e1d90ba). |
| R-02 | P0 verification | Enterprise Integration & Collaboration has a recoverable exception path whose diagnostic may be hidden in an expander. | Exercise success, missing config, rejected credentials and offline timeout; show an actionable message while preserving navigation. |
| R-03 | P0 verification | A Facility Layout SLP heatmap compatibility fix exists, but department, From/To, relationship matrix and heatmap need a connected UI regression. | Screenshot and validate all four on populated and empty data, and open the export. |
| R-04 | P0 verification | Excel data preparation must be verified from upload through cleaned workbook and audit download. | Downloaded XLSX/ZIP opens; expected sheets/audit are present and original data can be recovered. |
| R-05 | P0 verification | Source contains dedicated routes and a generic fallback studio; a populated fallback screen is not by itself proof of domain-specific engineering behavior. | Each module needs a named domain acceptance test; fallback-only behavior must be transparent to users. |
| R-06 | P1 verification | Module labels/tier metadata are spread across legacy and platform catalogues and tier helpers. | Add registry parity tests for stable IDs, aliases, category/tier and render-target mapping. |
| R-07 | P1 verification | Startup depends on a large application file and multiple service layers. | Cold-start with a test database/minimum secrets; optional service failures should result in explicit degraded mode. |
| R-08 | P1 verification | Chart and file-export failures are independent of calculation correctness. | Parse generated files and compare their content with the on-screen result for each export-enabled module. |
| R-09 | P1 verification | Capacity recovery correctly labels simulated recovery and treats the lowest OEE as a candidate signal, not proof of a bottleneck. | Keep caveats; require throughput/WIP/queue/routing evidence to confirm a constraint. |
| R-10 | P1 verification | Source dispatch presence cannot confirm successful visible rendering or primary-action behavior. | Run a browser smoke loop with per-module screenshots, errors, interaction and download checks. |

## Workforce-readiness release gate

Do not mark a module **PASS** until its record has: module ID/tier/commit/environment; startup and render result; empty-state result; primary calculation fixture and expected values; screenshot of its key chart; save/reload outcome; access-control outcome; parsed download artifacts where offered; and an invalid-input/error-recovery result.

### Recommended implementation sequence

1. Close the P0 tests for Excel Data Cleaning & Import, Industrial Workbook, Facility Layout & Warehousing, Enterprise Integration & Collaboration, Persistence, Subscription entitlements, Team Workspaces & RBAC, Executive Report Center and Enterprise Security & Governance.
2. Run a browser smoke loop across all 96 distinct module labels and classify each **PASS / FAIL / PARTIAL / NOT TESTED**. Never infer visual success from code presence alone.
3. Fix each confirmed failure with a regression test and screenshot/log evidence, plus an independent calculation check where relevant.
4. Consolidate module identity, navigation, entitlement, Copilot routing and test coverage into one registry.
5. Deliver P1 workflow depth and P2 specialized tools only after calculation, rendering, persistence and evidence labels meet acceptance criteria.
