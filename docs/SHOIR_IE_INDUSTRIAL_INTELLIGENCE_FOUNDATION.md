# Shoir-IE Industrial Intelligence Foundation

## Delivery status

**Code status: IMPLEMENTED AS A SHARED FOUNDATION — VALIDATION PENDING.**

The branch contains the shared service layer, all 16 deterministic analysis engines, six Workbench suites, eight cross-tool capability services, workspace-scoped Digital Thread integration, governed decision/action workflows, evidence-aware Copilot context, workbook handoff, exports, industry templates and acceptance-test definitions.

This is not yet a declaration that every route, calculation, tenant policy or browser flow has passed CI or staging. GitHub Actions for the current head must finish, and the live staging organization/role/persistence matrix must be independently exercised before the new capabilities can be labelled VERIFIED.

Application status remains **BETA**. Production remains **NO-GO**. Do not merge, deploy, migrate production data or change production infrastructure as part of this work.

## Repository and integration

- Repository: MSJ1708/shoir-ie
- Working branch: feat/shoir-ie-release-hardening-20261105
- Pull request: #232 (kept draft while implementation and verification continue)
- Main implementation: shoir_industrial_intelligence.py
- Existing suite integration: Industrial Operating System Workbench route and existing Workbench dispatcher
- Main AI integration: app.py get_copilot_response
- Existing Digital Thread: shoir_digital_thread.py
- Existing persistence: workspace_persistence.py and the authenticated organization-workspace Edge Function path
- Acceptance tests: tests/test_shoir_industrial_intelligence.py
- Shared foundation documentation: docs/SHOIR_IE_INDUSTRIAL_INTELLIGENCE_FOUNDATION.md

No new production migration or production data change is part of this implementation.

## Preserved platform contracts

The suite is additive and does not replace the existing application, its pages or its navigation. The existing top-level navigation, Workbench, Industrial Control Center, Command Center, Inspector, workbook tabs, login, subscription catalog, resource-intelligence capability, and specialist T001–T100 registry remain the authoritative platform surfaces.

The sixteen new specialist capabilities use their own non-overlapping codes:

\`II-001\` through \`II-016\`.

The existing T001–T100 inventory is not renumbered or expanded by this suite. Search includes exact names, codes, IDs and aliases. The Workbench only deep-links after a non-empty query matches a real registered tool; an empty search does not auto-open a tool.

The suite uses the existing \`Industrial Operating System\` module entitlement (Enterprise minimum) through the existing tier policy. It does not create a new subscription plan or modify plan pricing. The server-side service independently checks the existing Enterprise capability, authenticated actor, active organization membership, workspace role and operation. Organization read is restricted to Owner/Admin/Engineer/Approver/Viewer; writes to Owner/Admin/Engineer/Approver; approvals to Owner/Admin/Approver. A Viewer cannot write or approve.

## Architecture

Existing Shoir-IE app and Workbench
- Industrial Operating System
  - Six Industrial Intelligence suites
  - II-001 ... II-016 deterministic engines
  - Shared records, evidence and provenance
  - Existing Industrial Workbook handoff
  - Existing Digital Thread node/edge graph
  - Operational event timeline
  - Cause/effect investigation records
  - Risk and barrier screening / independent review
  - Decision proposals / independent review
  - Action approval / implementation / verification
  - Model versions / validation
  - Actual benefits / independent review
  - Evidence retrieval context for existing AI Copilot
  - workspace_persistence
    - Personal workspace persistence
    - Organization workspace Edge Function
      - Existing membership and revision checks

All new records are stored through the existing workspace persistence path. Shared organization writes require an authenticated organization workspace and the managed persistence service. If the managed shared persistence service is unavailable, a team write fails rather than falling back to an unrelated personal SQLite workspace.

Every record and graph edge carries organization/workspace scope. Lists are filtered against the current active workspace. A workspace save serializes only that active workspace's records; it does not copy another tenant's rows into the active tenant payload. The existing workspace loader is responsible for restoring the corresponding workspace snapshot when users switch context.

## Provenance and evidence contract

Supported provenance values are:

- \`LIVE\`
- \`IMPORTED\`
- \`MANUAL\`
- \`SYNTHETIC\`
- \`SIMULATED\`
- \`MOCK\`
- \`STALE\`

\`LIVE\`, \`IMPORTED\` and \`STALE\` require a source reference. \`LIVE\` and \`STALE\` also require a timezone-aware source timestamp. These labels record the supplied origin; they do not independently prove source health, accuracy or connector activity.

Records preserve their payload hash, creator, created timestamp, workspace scope, provenance, source reference, source timestamp and validation limitations. Original measurements are not overwritten by reconciliation. Any reconciliation or model output must remain distinguishable from the original observation.

Registered evidence means an evidence record ID or source reference already exists in the same active workspace. Confirmed Digital Thread links, action verification, decision reviews, model validation, cause/effect reviews, barrier reviews and benefit verification require registered workspace evidence. An arbitrary typed string is not sufficient.

## Six suites and sixteen engines

| Code | Suite | Tool | Implemented deterministic foundation |
|---|---|---|---|
| II-001 | Operations Intelligence | Industrial Operations Mission Control | Evidence-bounded event triage; transparent priority heuristic; no automatic root-cause claim |
| II-002 | Operations Intelligence | Industrial Process Mining and Hidden Inefficiency Intelligence | Event-log chronology, variants, directly-follows transitions, explicit wait minutes, repeated-activity candidates and conformance |
| II-003 | Engineering Intelligence | Engineering Change Impact Twin | Directed dependency traversal and change-impact review register |
| II-004 | Maintenance and Project Intelligence | Shutdown and Turnaround Intelligence Optimizer | Deterministic precedence/skill/resource schedule, one resource availability clock across skills, permit/inspection/SIMOPS/safety gates |
| II-005 | Engineering Intelligence | Industrial Data Trust and Measurement Reconciliation Engine | Measurement conflicts, unit-group checks, balance residuals and optional non-destructive residual-to-selected-stream proposals |
| II-006 | Maintenance and Project Intelligence | Asset Reliability Mission Board | Transparent criticality/history heuristic and supplied production dependencies |
| II-007 | Production and Quality Intelligence | Production Yield and Process Variability Intelligence | First-pass yield, recovered rework, final yield, scrap and count reconciliation |
| II-008 | Maintenance and Project Intelligence | New Factory Commissioning and Production Ramp-up Intelligence | Fail-closed required-check/evidence readiness gate |
| II-009 | Engineering Intelligence | Industrial Experimentation and Process Improvement Laboratory | Reproducible two-level factorial design and first-order least-squares fit |
| II-010 | Supply Chain and Procurement Intelligence | Technical Procurement and Supplier Engineering Assurance | Requirement-to-offer compliance, deviation and evidence coverage |
| II-011 | Energy and Enterprise Assurance | Industrial Energy Flexibility and Peak-Demand Optimizer | Deterministic tariff-ordered greedy placement within declared windows and capacities; global cost optimality is not guaranteed |
| II-012 | Supply Chain and Procurement Intelligence | Critical Spare Parts and Multi-Site Inventory Intelligence | Compatibility, source minimum stock and destination inventory constraints |
| II-013 | Energy and Enterprise Assurance | Industrial OT Asset and Configuration Assurance | Passive approved-baseline versus observed-configuration comparison |
| II-014 | Production and Quality Intelligence | Product and Batch Genealogy Intelligence | Forward/backward confirmed-lot traversal; suspected links remain separate |
| II-015 | Operations Intelligence | Intelligent Shift Handover and Operational Learning | Persistent organization-scoped handover records with separate incoming acknowledgement; acknowledgement does not close an issue |
| II-016 | Energy and Enterprise Assurance | Industrial Benchmarking and Improvement Radar | Comparability checks across metric, units, period and denominator |

### Calculation and operational boundaries

1. Mission Control provides a triage heuristic, not a formal safety risk score or confirmed root cause.
2. Process Mining treats elapsed event time as elapsed time; it counts waiting only when an explicit source field provides it.
3. Engineering Change reports only supplied dependency edges. Missing dependencies are not guessed.
4. Turnaround scheduling uses supplied task, resource, skill and constraint data. It does not infer site calendars, labor agreements, weather, lifting constraints, permit authority or all SIMOPS rules; it does not authorize work.
5. Data Trust flags supplied conflicts and balance residuals. It can create an explicitly targeted residual-assignment proposal, but that proposal is not applied, is not verified, and leaves original readings unchanged. It does not invent calibration uncertainty.
6. Asset Reliability does not produce a guaranteed failure date or remaining useful life.
7. Yield calculations require consistent product/batch boundaries and units.
8. Commissioning status is readiness for authorized review, not statutory or formal system acceptance.
9. DOE results are bounded by the supplied design and fitted model; first-order fit does not establish causality or omitted interactions.
10. Procurement Assurance only evaluates claims and evidence IDs supplied by the user; missing substantiation remains unverified.
11. Energy Flexibility uses supplied tariffs/windows/capacities and a deterministic tariff-ordered greedy allocator. Feasibility is checked, but a globally minimum-cost schedule is not guaranteed; the tool does not dispatch plant equipment.
12. Spare Parts reports eligibility or rejection; it does not execute a stock transfer.
13. OT Assurance is a passive records comparison. No active discovery, scan, PLC/DCS/SCADA connection or configuration write is performed.
14. Genealogy traverses only relationships explicitly marked CONFIRMED and does not turn suspected links into genealogy facts.
15. Shift Handover carries unresolved issues in a persistent organization-scoped record. A separately authenticated incoming shift owner can acknowledge each issue, but acknowledgement is not issue closure; similar issue text does not establish common cause.
16. Benchmarking suppresses misleading comparisons when required definitions, units, periods or denominators are incompatible.

## Tool delivery status matrix

The following is the code-delivery status on this candidate branch. All sixteen tools have an executable deterministic analysis engine and are registered under the existing Workbench. This status is not a statement that their plant/browser workflows have passed staging.

| Code | Tool | Current status |
|---|---|---|
| II-001 | Industrial Operations Mission Control | IMPLEMENTED — VALIDATION PENDING |
| II-002 | Industrial Process Mining and Hidden Inefficiency Intelligence | IMPLEMENTED — VALIDATION PENDING |
| II-003 | Engineering Change Impact Twin | IMPLEMENTED — VALIDATION PENDING |
| II-004 | Shutdown and Turnaround Intelligence Optimizer | IMPLEMENTED — VALIDATION PENDING |
| II-005 | Industrial Data Trust and Measurement Reconciliation Engine | IMPLEMENTED — VALIDATION PENDING |
| II-006 | Asset Reliability Mission Board | IMPLEMENTED — VALIDATION PENDING |
| II-007 | Production Yield and Process Variability Intelligence | IMPLEMENTED — VALIDATION PENDING |
| II-008 | New Factory Commissioning and Production Ramp-up Intelligence | IMPLEMENTED — VALIDATION PENDING |
| II-009 | Industrial Experimentation and Process Improvement Laboratory | IMPLEMENTED — VALIDATION PENDING |
| II-010 | Technical Procurement and Supplier Engineering Assurance | IMPLEMENTED — VALIDATION PENDING |
| II-011 | Industrial Energy Flexibility and Peak-Demand Optimizer | IMPLEMENTED — VALIDATION PENDING |
| II-012 | Critical Spare Parts and Multi-Site Inventory Intelligence | IMPLEMENTED — VALIDATION PENDING |
| II-013 | Industrial OT Asset and Configuration Assurance | IMPLEMENTED — VALIDATION PENDING |
| II-014 | Product and Batch Genealogy Intelligence | IMPLEMENTED — VALIDATION PENDING |
| II-015 | Intelligent Shift Handover and Operational Learning | IMPLEMENTED — VALIDATION PENDING |
| II-016 | Industrial Benchmarking and Improvement Radar | IMPLEMENTED — VALIDATION PENDING |

## Eight shared intelligence capabilities

| Capability | Foundation implementation | Important boundary |
|---|---|---|
| A. Industrial Cause-and-Effect Intelligence | Investigation records, observations, candidate relationships, supporting and contradicting evidence, independent review record | A candidate can be SUSPECTED or SUPPORTED; only an independent evidence-backed review can confirm/reject that candidate |
| B. Industrial Risk and Barrier Assurance | Risk screen, barrier owners, evidence references, independent barrier-effectiveness review and audit trail | Not formal safety/process-safety approval; a user-entered EFFECTIVE status cannot reduce the reviewed screen |
| C. Engineering Knowledge Graph | Existing Digital Thread node/edge graph, full entity vocabulary, scoped relationships and evidence requirements | No separate graph database; relationships only connect registered active-workspace entities |
| D. Industrial Decision and Action Management | Decision proposal with options/recommendation/rationale/evidence, independent APPROVED/REJECTED review, assigned actions, approval, implementation and verification | Decision author/action creator cannot independently approve or verify their own record; action closure follows independent verification |
| E. Industrial Investment and Benefits Realization | Baseline/actual/delta record with source evidence, separate independent review and audit trail | Actual record is unverified until separately reviewed; no automatic realized-savings/ROI claim |
| F. Engineering Model Validation and Registry | Immutable model/version identity, contract hash over definition/assumptions/tests, actual-versus-expected checks and independent review | All test cases must pass and a different authorized reviewer must provide registered evidence |
| G. Operational Event Intelligence | Provenance-bearing event record, source timestamp, entity reference, workspace scope and timeline list | No claim of live telemetry unless a configured source has supplied the record |
| H. Industrial Knowledge Copilot | Workspace-scoped evidence retrieval, record citations, linked Digital Thread context and connection to existing AI Copilot | Evidence is bounded/redacted before provider prompt use; retrieved records are not an automatic causal answer and Copilot cannot approve/execute actions |

## Industrial Digital Thread

The new shared services use the existing canonical Digital Thread type vocabulary:

Organization → Facility → ProductionLine → Process → Asset / Equipment → Instrument

The same vocabulary covers Product, Batch, Material, Supplier, Order, WorkOrder, WorkPackage, Workforce, Document, Dataset, Event, Quality, Maintenance, Energy, Cost, KPI, Model, Experiment, Scenario, Decision, Action, Approval, Evidence, Risk, Control, Project and Outcome.

New entities receive stable scoped thread identities. The thread namespace includes organization/personal identity and workspace, avoiding a global collision of the same user-supplied asset ID across tenants. Edges connect only entities registered in the active workspace. CONFIRMED edges require at least one registered evidence record/source reference; SUSPECTED and PROPOSED remain separate. Snapshot retrieval filters graph nodes to the active workspace's registered records/entities/actions/models and includes only edges whose endpoints are both visible.

The suite can connect:
- industrial entities and evidence records;
- records to events and actions;
- actions through approval, implementation and independent verification;
- model versions to registration and reviewer-validation state;
- risk/barrier screens and their independent reviews;
- decision proposals and their independent review records;
- outcome records and independent benefit review;
- relevant record nodes and linked Digital Thread edges in Copilot evidence context.

The existing Digital Thread graph remains the canonical UI/data structure. This feature does not introduce an unrelated graph database.

## Existing application integrations

- The existing Industrial Operating System Workbench route composes the established Operating System page and the Industrial Intelligence Suite.
- The Workbench dispatcher routes the existing module entry to that screen instead of the generic data exchange fallback.
- The Workbench search recognizes specialist names/aliases/IDs and deep-links to the selected tool; empty search is inert.
- Tool result export includes a provenance-bearing JSON package and calls the existing shared Excel/PDF/PowerPoint exporter when available.
- A user can send a tool result into the existing Industrial Workbook. Existing sheets are preserved; a new workbook initializes the established nine tabs; the result becomes a new named sheet with input, result, provenance, source, hashes and a NOT_VERIFIED status.
- The existing Industrial Control Tower has a permission-checked read-only panel for current-workspace events, open actions and risk screens.
- The existing AI Copilot retrieves current-workspace evidence for Enterprise-authorized users. Payloads are bounded and credential-like keys are redacted; the prompt instructs the model to cite record IDs, distinguish evidence provenance and not treat a relationship as proof of causation.
- Existing T001–T100 registry entries and their IDs remain unchanged. The suite uses II-001–II-016 identifiers separately.

## Industry templates

Five configurable workspace starting templates exist:

- Oil, Gas and Petrochemicals
- Mining and Minerals
- Steel, Aluminium and Metals
- Food and Manufacturing
- Water and Utilities

Each provides focus tools, starter KPIs and an explicit industry warning. Templates do not remove tools or modify subscription entitlements.

## Acceptance test inventory

\`tests/test_shoir_industrial_intelligence.py\` currently defines **56 tests**. It includes coverage for:

- 16-tool catalogue cardinality, stable II-001–II-016 IDs and exact/alias search.
- All 16 deterministic analysis engines and their expected synthetic acceptance cases.
- Entity vocabulary parity with the existing Digital Thread.
- Event triage and evidence boundaries.
- Process mining elapsed time, explicit waits, rework/repeated activities and conformance.
- Engineering Change dependency traversal.
- Turnaround feasible/infeasible schedules and global resource non-overlap across multiple skills.
- Measurement conflicts, original-value retention, explicit reconciliation proposals and rejection of negative proposed values.
- Asset priority and dependency outputs.
- Yield arithmetic and reconciliation.
- Commissioning fail-closed readiness.
- Reproducible experiment design.
- Supplier claim compliance and missing evidence.
- Energy capacity/window constraints and an explicit assertion that greedy allocation carries no global optimality guarantee.
- Spare-part compatibility and source minimum stock.
- Passive OT configuration differences.
- Confirmed genealogy traversal.
- Shift handover persistence, incoming-role acknowledgement, duplicate-ack rejection and the rule that acknowledgement does not close the issue.
- Benchmark comparability.
- Provenance/source metadata validation.
- Persistence failure behaviour.
- Personal/organization scope and Viewer restrictions.
- Server entitlement derives from authenticated session tier, not caller-supplied tier argument.
- Organization-switch isolation and no cross-tenant payload copying.
- Evidence-backed Digital Thread relationship creation.
- Event → entity → action → approval → implementation → independent verification.
- Action state transition enforcement and closure after verification.
- Decision proposal/option validation and independent review.
- Risk/barrier independent review.
- Actual benefit independent review.
- Model expected-versus-actual tests and evidence-backed independent validation.
- Cause/effect candidate and independent review.
- Copilot evidence citations, redaction, Digital Thread links and cross-organization denial.
- Workbook sheet handoff and preservation of standard/existing tabs.
- Workbench routing and empty-search behavior.
- Existing Copilot evidence-context integration.

The existing Digital Thread test file contains its separate regression tests. These acceptance definitions are committed, but **they are not a passing test report until the exact-head CI runner finishes successfully**.

## Verification still required

Before marking these features VERIFIED:

1. Run and pass all PR checks on the exact branch head; fix all new failures and classify historical failures.
2. Exercise all 16 real Workbench tool launches using authenticated browser sessions.
3. Test Owner, Admin, Engineer, Approver and Viewer using disposable staging users.
4. Prove read/write/approval denial across two distinct staging organizations using the actual Edge Function/RLS path.
5. Verify reload, logout/login, workspace switch, optimistic revision conflict and managed persistence on staging.
6. Exercise workbook handoff and JSON/Excel/PDF/PowerPoint export in the deployed UI.
7. Verify the real Copilot provider path with a disposable test workspace and confirm only authorized, redacted evidence is sent.
8. Perform responsive browser tests at 1440, 768 and 390 pixels, and Arabic/RTL tests.
9. Independently review all engineering calculations and plant-specific operating/safety constraints.
10. Keep SAP/Oracle/REST/OT integrations BLOCKED until actual endpoints, credentials, certificates, allowlists, customer authorization and security tests exist.
11. Complete all existing Shoir-IE release gates independently. Production remains NO-GO and BETA remains in force until those are satisfied.

## Current delivery labels

Use these labels precisely:

- IMPLEMENTED — VALIDATION PENDING: code and tests are committed on the candidate branch, but CI/browser/staging evidence is incomplete.
- VALIDATED IN CI: exact-head required checks have finished successfully.
- VALIDATED IN STAGING: authenticated staging journeys, real managed persistence and tenant/RBAC matrix have passed with disposable accounts.
- INDEPENDENTLY VERIFIED: an independent reviewer has inspected the required engineering/security evidence.
- PRODUCTION READY: all existing production release gates are independently satisfied and cutover is explicitly authorized.

No tool or shared capability should be labelled VERIFIED merely because its name exists in the Workbench or its test has been authored.
