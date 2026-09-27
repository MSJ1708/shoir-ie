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
