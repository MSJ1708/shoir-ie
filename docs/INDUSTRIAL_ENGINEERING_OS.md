# Shoir-IE Industrial Engineering Operating System

## Purpose

Shoir-IE remains a single industrial decision platform rather than a collection of disconnected calculators. The integration layer connects the existing domain engines through one lifecycle:

**Observe → Understand → Diagnose → Model → Experiment → Optimize → Decide → Execute → Verify → Learn**

The new layer is intentionally thin. Existing specialist engines remain the authority for calculations, Digital Twin, forecasting, optimization, research, enterprise security, persistence, and other domain capabilities.

## Universal module contract

A module participates in the shared contract:

**Input → Validate → Normalize → Analyze → Visualize → Explain → Compare → Simulate/Optimize → Export → Persist → Trace → Verify**

A module is not considered visualization-complete merely because a chart can be hard-coded for a known dataset. The universal visualization layer now discovers the active module table, attempts the industrial chart suite, and falls back to a truthful data-completeness view when no specialized chart applies.

Audits disable unrelated global-state fallback so a module cannot pass by visualizing another module's data.

## Shared engineering surfaces

The Industrial Engineering Operating System surface provides:

- deterministic problem-to-method routing
- resource-family evidence mapping for people, machines, materials, time, space, energy, cost and carbon
- scenario trade-off comparison relative to an explicit baseline
- mixed-objective Pareto flags without hiding trade-offs
- expected-vs-actual verification with explicit tolerance
- canonical Digital Thread entity mapping
- industry profiles and persona-oriented views
- an IE method library with coverage and authority metadata
- a controlled industrial event contract
- visualization-contract audit access

## Workbook integration

The Industrial Workbook is still the editable artifact and now also supports:

- named engineering variables
- additional shared engineering functions
- industrial pivot query steps
- median and standard-deviation grouping
- safe conditional-formatting previews
- expanded IE starter templates
- persistent variable metadata
- labeled workbook versions
- version restore by ID while retaining the legacy two-argument API
- scenario branching
- existing comments and workspace history

The formula evaluator remains AST-based and allow-listed. New functions are delegated to the existing adoption engine while legacy formulas stay available for compatibility.

## Decision and learning loop

Analysis does not imply execution. The existing Decision Center, Implementation Tracker, Digital Thread, enterprise audit ledger and memory systems remain the governed authorities.

Verification is explicitly represented as:

**Expected → Intervention → Measurement → Actual → Variance → Verified Outcome**

The platform can therefore preserve the distinction between measured results, assumptions, predictions and post-implementation outcomes.

## Extension path

The architecture leaves specialist method implementation in the existing domain engines and uses the method library as the common routing and discovery layer. Future plugins can register additional methods, templates, connectors or simulations without creating a second orchestration kernel.

## Validation

CI should compile and run the complete repository test suite for `feat/**` branches. The platform validation workflow also performs AST parsing of the application and required integration modules.


## Production Bottleneck & Capacity Recovery Study

The Industrial Operating System includes a first end-to-end capacity-recovery workflow backed by the separate, testable `shoir_capacity_recovery.py` service. It is intentionally a deterministic screening model, not a discrete-event simulation or calibrated digital twin.

### Workflow

1. Review the clearly labelled synthetic station table or optionally import a CSV / first-sheet XLSX (10 MiB and 1,000-row limits).
2. Map five baseline fields: station, cycle time in seconds/unit, available time in minutes/shift, availability percentage, and parallel resource count.
3. Edit the recovery scenario explicitly. Scenario cycle times, availability and resource counts default to baseline when data is imported; improvements are never silently inserted.
4. Enter good-unit demand and overall first-pass yield. Results recalculate from current inputs, showing station capacity, binding station(s), baseline/scenario line capacity, shortfall/surplus, and comparison chart.
5. Inspect the calculation version, assumptions, source reference, and input hash; export station results, comparison summary, assumptions, data lineage, and the chart via the existing export service.
6. Save an owner-scoped study snapshot with normalized inputs, results, decision/rationale, calculation version, and SHA-256 identifiers. Later record a source-referenced actual-output measure and compare it with the saved scenario estimate using an explicit tolerance.
7. Optionally calculate a scenario value sensitivity using user-supplied operating shifts/year, per-unit contribution/avoided cost, and implementation cost.

### Calculation contract and boundaries

Per station:

`Capacity = AvailableTimeMinutes × 60 × ParallelResources ÷ CycleTimeSeconds × AvailabilityFraction`

The serial-line screening estimate is the minimum station capacity. The entered overall first-pass yield is applied once to that line capacity. Demand shortfall is `max(0, demand − estimated good capacity)`; surplus is `max(0, estimated good capacity − demand)`.

Units, limits and invalid values are checked before calculation. The model rejects missing/non-numeric/non-finite values, non-positive cycle time, invalid percentages, fractional or non-positive resource counts, duplicate station names, and oversized inputs. The present version does not model product mix, setups, blocking/starvation, buffers, rework flows, stochastic time variation or finite schedules. The binding station is a calculated constraint, not proof of root cause.

### Evidence semantics

- A calculated capacity estimate is not actual production and is not a guarantee.
- The saved input/result hashes identify a payload; they do not authenticate the originating workbook or prove that measurements are correct.
- Actual outcomes require a measurement period and a source reference. A source reference is recorded for traceability but is not independently authenticated.
- A tolerance comparison is arithmetic only. It does not establish causality, operator safety, or an independently verified saving.
- Financial sensitivity is labelled as a scenario estimate. Financial benefits become realized only after an appropriate customer-specific baseline and post-change measurement and implementation costs are assessed.

### Persistence and access

The study and outcome APIs use parameterized SQLite statements, require a non-empty owner, and filter reads by owner and study identifier. The production database path follows the existing workspace default; tests inject a temporary database to verify isolated persistence. Existing database migration is additive. This does not replace a full multi-tenant authorization review of every application route.
