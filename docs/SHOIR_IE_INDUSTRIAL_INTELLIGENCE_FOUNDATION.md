# Shoir-IE Industrial Intelligence Foundation

## Status and operating boundary

This document describes the shared Industrial Intelligence foundation implemented in shoir_industrial_intelligence.py and integrated under the existing Enterprise Industrial Operating System Workbench entry. It does not introduce a second application, navigation tree, subscription plan, or live OT/ERP connector.

The foundation is additive. Existing Shoir-IE pages, tool IDs, workbook tabs, subscriptions, Resource Intelligence, Industrial Control Center, Command Center, Inspector drawer and navigation remain authoritative.

This is a software foundation for deterministic, evidence-bounded workflows. Passing synthetic acceptance tests does not establish plant-specific engineering validity, customer readiness, Saudi legal/privacy compliance, an active external connector, or production readiness.

Production remains NO-GO; application status remains BETA. Work is staged through draft PR #232 only. No production schema, data or infrastructure is modified by this feature.

## Architecture

Existing Shoir-IE Workbench / Industrial Operating System
- Six connected tool suites
- Sixteen deterministic tool engines
- Shared records, evidence and provenance
- Industrial Digital Thread entity and edge links
- Operational event and investigation records
- Decisions, approvals, actions and verification
- Model versions and independent review
- Benefits records and independent review
- Risk/barrier screening
- Evidence retrieval context for the existing Copilot
- Existing workspace persistence and organization membership controls

## Persistence and authorization

The service uses the existing workspace_persistence path. For a selected organization workspace, it reuses shoir_active_organization_workspace, organization/workspace IDs, the authenticated session token, Edge Function membership validation and optimistic revision handling. Shared state must not fall back to per-user SQLite if the managed organization service is unavailable.

The service checks signed-in identity, the existing Enterprise tier gate and the active workspace role. Read, write and approval are separate operations. Organization roles are resolved by the existing server-backed organization service: Owner, Admin, Engineer, Approver and Viewer. Viewers are read-only. Approvals and independent verification are restricted to authorized roles, and a creator cannot approve or verify their own record.

These checks are implemented as service-level guards and covered by deterministic tests. Hosted end-to-end organization membership/RLS verification remains a separate release gate.

## Provenance

Supported provenance labels:
- LIVE
- IMPORTED
- MANUAL
- SYNTHETIC
- SIMULATED
- MOCK
- STALE

LIVE, IMPORTED and STALE records require a source reference. LIVE and STALE records also require a timezone-aware source timestamp. A label is not proof that a connection is live or data is accurate. Each record preserves a payload hash, creation identity/time, source reference and provenance limitations.

Original measurement inputs are not silently changed by Data Trust. Process event elapsed time is not automatically relabelled as waiting time. Suspected genealogy or cause-effect relationships are not treated as confirmed. Modeled values are not reported as realized benefits.

## Six suites and 16 tool engines

The catalogue and search aliases are maintained in TOOL_CATALOG. Each specialist capability has a stable II-001 through II-016 identifier, separate from the existing T001 through T100 registry; both namespaces are tested for uniqueness and non-overlap. Tool analysis is available through analyze_tool(tool_id_or_code, payload). Results include status, calculation timestamp, core version, input hash and limitations.

| Suite | Tool | Deterministic foundation |
|---|---|---|
| Operations Intelligence | Industrial Operations Mission Control | Transparent severity/urgency/impact triage; root cause remains unconfirmed |
| Operations Intelligence | Industrial Process Mining and Hidden Inefficiency Intelligence | Event-log variants, directly-follows transitions, elapsed time, explicit wait field, repeated-activity candidates and sequence deviations |
| Operations Intelligence | Intelligent Shift Handover and Operational Learning | Carry open issues, owner and acknowledgement state forward |
| Engineering Intelligence | Engineering Change Impact Twin | Directed dependency traversal and review register |
| Engineering Intelligence | Industrial Data Trust and Measurement Reconciliation Engine | Same-meter conflict and unit checks, explicit balance residuals, original-value retention |
| Engineering Intelligence | Industrial Experimentation and Process Improvement Laboratory | Full two-level factorial design and first-order least-squares fit |
| Maintenance and Project Intelligence | Asset Reliability Mission Board | Transparent history/criticality heuristic and supplied production dependencies |
| Maintenance and Project Intelligence | Shutdown and Turnaround Intelligence Optimizer | Deterministic precedence/skill/resource schedule with permit, inspection, SIMOPS and safety-hold gates |
| Maintenance and Project Intelligence | New Factory Commissioning and Production Ramp-up Intelligence | Required-check and evidence readiness gate |
| Production and Quality Intelligence | Production Yield and Process Variability Intelligence | First-pass, final yield, rework, scrap and unaccounted-unit calculation |
| Production and Quality Intelligence | Product and Batch Genealogy Intelligence | Confirmed forward/backward lot graph traversal; suspected links excluded |
| Supply Chain and Procurement Intelligence | Technical Procurement and Supplier Engineering Assurance | Requirement-to-offer compliance, deviation and evidence coverage |
| Supply Chain and Procurement Intelligence | Critical Spare Parts and Multi-Site Inventory Intelligence | Compatibility, source minimum and destination stock constraints |
| Energy and Enterprise Assurance | Industrial Energy Flexibility and Peak-Demand Optimizer | Period-window/capacity-constrained least-cost flexible-load placement |
| Energy and Enterprise Assurance | Industrial OT Asset and Configuration Assurance | Passive baseline-versus-observed configuration record diff |
| Energy and Enterprise Assurance | Industrial Benchmarking and Improvement Radar | KPI comparability by metric, units, period and denominator |

### Calculation boundaries

1. Mission Control returns a triage heuristic, not a formal safety risk score.
2. Process Mining measures event timestamps and only counts waiting minutes when the source explicitly supplies explicit_wait_minutes; elapsed time is not assumed to be queue time.
3. Engineering Change traverses only supplied dependency edges; absent edges are not inferred.
4. Turnaround checks supplied dependencies, skills, resources, permits, inspections, SIMOPS state and safety holds. Site calendars, rest rules, weather, crane envelopes and permit authority are not inferred. It cannot authorize work.
5. Data Trust flags supplied measurement conflicts and balance residuals. It does not estimate calibration uncertainty or automatically reconcile/overwrite values.
6. Asset Reliability is a transparent heuristic. It does not return an exact failure date or remaining useful life.
7. Yield assumes supplied quantities use the same product/batch boundary and unit.
8. Commissioning only reports readiness for authorized review; it does not grant formal acceptance.
9. Experimentation first-order fitting omits curvature/interactions in the fitted model. A generated design does not establish causality.
10. Procurement classifies claims against supplied requirement IDs and evidence IDs. An unsupported compliant claim remains unverified.
11. Energy Flexibility uses supplied tariffs, time windows and capacities; it does not dispatch equipment.
12. Spare Parts returns eligibility/rejection only; it does not move stock.
13. OT Assurance is passive evidence comparison; it performs no active scan, connection or controller modification.
14. Genealogy traverses only CONFIRMED edges. Suspected relationships remain separate.
15. Shift Handover carries unresolved records; repeated wording is not root-cause proof.
16. Benchmarking suppresses comparison when metric, units, period or denominator are incompatible.

## Shared services

The shared service module currently provides:
- Cause-and-effect investigation records with observations, candidate relationships, supporting references and counter-evidence.
- Risk/barrier screening records with owner and evidence fields; no formal safety approval is issued.
- Entity and relationship persistence integrated with shoir_digital_thread.py.
- Decision/action records, approval records and independent outcome verification.
- Actual benefit records that start unverified; only a different authorized reviewer can add an independent review with evidence.
- Immutable model-version registration with definition hash, assumptions and expected-versus-actual test comparisons; a different authorized reviewer is required to validate.
- Operational event records and event timeline state.
- Evidence retrieval context for the existing Copilot; record IDs are citations, not a generated AI conclusion.
- Analysis handoff to the existing Industrial Workbook. The service preserves existing workbook sheets, initializes the nine standard engineering tabs only for a new workbook, adds a provenance/hash-labelled result sheet, and persists through the active managed workspace.

The Copilot context service retrieves only records available in the current authorized workspace. It does not invent records, assert a root cause, approve an engineering change, or execute a plant action.

## Digital Thread

The shared Digital Thread vocabulary now includes:

Organization → Facility → ProductionLine → Process → Asset / Equipment → Instrument

It also covers Product, Batch, Material, Supplier, Order, WorkOrder, WorkPackage, Workforce, Document, Dataset, Event, Quality, Maintenance, Energy, Cost, KPI, Model, Experiment, Scenario, Decision, Action, Approval, Evidence, Risk, Control, Project and Outcome.

The new service creates stable node identities for saved industrial records and directed edges only between existing entities. CONFIRMED edges require at least one evidence reference; SUSPECTED and PROPOSED remain distinct statuses. Graph links are scoped to the active personal or organization workspace.

Existing canonical graph tables and the general Digital Thread remain in place. This feature does not migrate existing customers' rows into a new graph database.

## Industry templates

Five configurable starting templates are provided:
- Oil, Gas and Petrochemicals
- Mining and Minerals
- Steel, Aluminium and Metals
- Food and Manufacturing
- Water and Utilities

Templates provide suggested tools, starter KPIs and configuration warnings. They do not remove tools or change subscription entitlements.

## Acceptance tests

tests/test_shoir_industrial_intelligence.py contains deterministic coverage for:
- Catalogue cardinality, six suites, eight shared service definitions and five industry templates.
- All 16 independent analysis engines.
- Mission Control triage and root-cause boundary.
- Process event timeline, explicit waits, repeated activities and conformance.
- Engineering-change direct/downstream dependencies.
- Turnaround feasible/infeasible scheduling.
- Data conflict detection and original preservation.
- Asset priority ranking.
- Yield reconciliation.
- Commissioning fail-closed readiness.
- Reproducible experiment design.
- Supplier compliance/deviation classification.
- Energy scheduling constraints.
- Spare-part minimum-stock guard.
- Passive OT configuration difference detection.
- Confirmed genealogy traversal.
- Shift handover acknowledgement.
- Benchmark comparability.
- Input/provenance validation.
- Workspace persistence failure behavior.
- Personal workspace separation and organization viewer restriction.
- Evidence-backed Digital Thread relationships.
- Action independent approval and verification.
- Actual model test comparison and independent model review.
- Benefit independent review.
- Cause-effect uncertainty and Copilot evidence citation context.

Recommended commands:
- pytest -q tests/test_shoir_industrial_intelligence.py
- pytest -q tests/test_shoir_digital_thread.py
- python -m compileall -q .

The tests use synthetic fixtures and mocked managed persistence. Passing them is evidence of deterministic engine and service behavior only. It does not replace staging browser journeys, live Supabase RLS/Edge Function verification, real customer data reconciliation, OT security approval, independent engineering review, Arabic/RTL testing or the full production release checklist.

## Known further verification work

Before any new-tool status can be changed to VERIFIED:
1. Run the full exact-head CI suite and fix every failure.
2. Exercise all 16 routes through authenticated browser sessions.
3. Exercise organization-scoped persistence through the real staging Edge Function with disposable Owner/Admin/Engineer/Approver/Viewer accounts.
4. Prove cross-organization read/write/approval denial with distinct organizations.
5. Test page refresh, logout/login, reload and revision-conflict flows.
6. Test exports and workbook linkage for each relevant tool.
7. Test Arabic/RTL and 1440/768/390-pixel responsive layouts.
8. Complete independent engineering review of calculations and plant-specific constraints.
9. Keep external integration states blocked until approved endpoints, credentials, certificates, tests and customer authorization exist.
10. Preserve BETA and production NO-GO until existing release gates are independently satisfied.
