# Shoir-IE — Requested Scope Completion and Gap Register

**Review date:** 2026-11-04  
**Repository baseline:** `MSJ1708/shoir-ie`  
**Reviewed staging baseline:** `staging-e2e-20261019` @ `f00da78a01e2ecf07fe263ddf570cbc1e075ac31`  
**Production:** out of scope; no production changes  
**Purpose:** account for every major capability group in the user's 22-section implementation specification and identify what is not implemented, only partially implemented, or not yet verified.

> This is an evidence register, not a claim of completion. A source file, module name, registry entry, route, chart, passing global test or draft pull request is not by itself proof of a fully usable feature. Where a full feature-specific hosted workflow has not been evidenced, the status is deliberately conservative.

## 1. Status rules

Use the exact canonical status vocabulary:

- `NOT_STARTED` — no implementation was identified in the inspected staging source for the stated requirement.
- `IN_PROGRESS` — partial foundation exists; essential behavior, integration or persistence is incomplete.
- `IMPLEMENTED_NOT_TESTED` — implementation is identifiable, but relevant tests have not been run.
- `IMPLEMENTED_NEEDS_VALIDATION` — implementation and some regression coverage exist, but relevant independent, integration, negative or hosted acceptance is still open.
- `TESTED` — feature-specific tests pass; this does not imply hosted staging acceptance.
- `STAGING_VERIFIED` — the exact hosted staging build passed the feature's acceptance workflow and evidence is retained.
- `EXTERNAL_CONFIGURATION_REQUIRED` — provider/customer/host credentials or setup are required.
- `BLOCKED_EXTERNAL` — an external prerequisite currently prevents the next acceptance step.
- `FAILED` — a mandatory test/acceptance requirement failed.
- `DEPRECATED` — intentionally retired.

No feature in this register is promoted to `STAGING_VERIFIED` without exact-build authenticated hosted evidence.

## 2. Verified current product baseline

The staging repository contains a Streamlit application, an Industrial Engineering Workbench and Command Center, a 96-module subscription inventory, a 100-tool registry/readiness matrix, Excel Intelligence code, Digital Thread code, an AI Copilot orchestrator, an enterprise layer, an Edge persistence service, engineering modules and an automated test suite.

The 100-tool matrix currently has 100 unique canonical IDs and no duplicate IDs. Its source counts are:

| Source-matrix status | Count | Interpretation |
|---|---:|---|
| `IMPLEMENTED_NEEDS_VALIDATION` | 87 | mapped code exists; tool-specific acceptance is incomplete |
| `FOUNDATION_ONLY` | 11 | not a complete usable capability |
| `EXTERNAL_CONFIGURATION_REQUIRED` | 2 | external setup/testing required |
| **Total** | **100** | not 100 completed or verified tools |

The exact per-tool inventory remains `SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`. Excel Intelligence is a distinct Workbench Data capability and is not a 97th subscription module.

## 3. Original eleven implementation areas

| Requested capability | Current status | What is already present | What is still required for full completion |
|---|---|---|---|
| 1. Manufacturing and Capacity Optimisation | `IMPLEMENTED_NEEDS_VALIDATION` | Capacity recovery/target-engine methods and tests | Independent reference fixtures for takt, cycle/lead time, practical capacity, bottlenecks, line balance with precedence, multi-product mix, changeovers, shifts, WIP, OEE and production scheduling; complete import-to-decision hosted journey. |
| 2. Supply Chain and Inventory Intelligence | `IMPLEMENTED_NEEDS_VALIDATION` | Forecasting and inventory policy methods/tests; historical `plan_inventory_policy(...)` behavior must remain compatible | Time-aware backtesting, baseline comparisons, stochastic and variable lead-time cases, safety-stock/service-factor references, ABC/XYZ, MOQ, expiry, procurement/supplier performance and network-planning workflow. |
| 3. Predictive Maintenance and Reliability | `IN_PROGRESS` | Reliability/maintenance foundations and T044 catalogue mapping | Full asset/failure history workflows; verified MTBF, MTTR, availability, reliability and Weibull fixtures; leak-free predictive evaluation; model calibration/monitoring; complete maintenance action lifecycle. |
| 4. Quality Engineering | `IMPLEMENTED_NEEDS_VALIDATION` | Statistical/quality methods and regression tests | Independent SPC rules, Cp/Cpk versus Pp/Ppk, MSA/Gauge R&R, DOE, sampling and hypothesis tests; persistent nonconformance/CAPA lifecycle and method assumptions. |
| 5. Facility Layout and Material Flow | `IMPLEMENTED_NEEDS_VALIDATION` | Existing `shoir_facility_layout.py` and tests | Hosted editable layout flow, SLP/relationship chart, distance/handling-cost reference fixtures, geometry correctness, alternative layouts, heatmaps, persistence and exports. Accurate 2D takes priority over 3D. |
| 6. Project Controls and Cost Intelligence | `IMPLEMENTED_NEEDS_VALIDATION` | Enterprise operations/value evidence foundations and tests | Verified WBS/CPM/PERT/critical path, resource allocation, baselines, EVM (PV/EV/AC/SV/CV), forecast and consistent cost allocations; complete portfolio/benefit verification. |
| 7. Workforce and Operations Scheduling | `IMPLEMENTED_NEEDS_VALIDATION` | Scheduling/industrial engineering method foundations | Feasible shift and staff scheduling with skills, availability, rest/work-hour rules, labour cost, hard/soft constraints, unfilled-role reporting and conflict explanation. |
| 8. Energy and Resource Efficiency | `IN_PROGRESS` | Shared performance/sustainability foundations | Governed measured baselines, tariff/emissions factor source and effective dates, energy/water/waste intensity, verified unit conversions, scenario comparison and measured-versus-estimated savings. |
| 9. Industrial Decision Intelligence and Simulation | `IMPLEMENTED_NEEDS_VALIDATION` | Simulation, experiment, resilience and optimization modules/tests | Calibration/validation, time/queue assumptions, reproducible Monte Carlo, discrete-event model validation where offered, sensitivity, multi-criteria decision analysis, solver-state accuracy and hosted evidence. |
| 10. Excel Intelligence | `IMPLEMENTED_NEEDS_VALIDATION` | Workbench Data route, in-app ingestion/runtime/studio, OOXML fidelity scanning, safe export, local-only Office.js planner, approval evidence | Full Stage 1 acceptance remains open; installable Office host deployment, desktop/web compatibility, separate scoped add-in identity, authenticated workbook transfer, transfer consent and cross-tenant security are not complete. See section 6. |
| 11. Industrial Engineering Copilot | `IMPLEMENTED_NEEDS_VALIDATION` | Deterministic intent/analysis engine, orchestration, typed tool registry, approval-gate foundations | Broader specialist tool coverage, evidence-linked cross-workspace execution, permission/approval tests, prompt-injection evaluation, durable execution replay/evaluation, tenant-scoped memory controls and hosted acceptance. A configured external LLM is not established by the inspected staging status. |

## 4. Additional advanced industrial capabilities

| Requested capability | Current status | Remaining implementation/acceptance |
|---|---|---|
| Engineering Recommendation Engine | `IN_PROGRESS` | Complete authorised cross-workspace data joins, transparent ranking, evidence links, hypothesis-vs-causation labels, missing-evidence detection, human review, implementation and measured outcome verification. |
| Industrial Engineering Project Lifecycle | `IN_PROGRESS` | Complete IDENTIFY–MEASURE–ANALYSE–DESIGN–SIMULATE–OPTIMISE–APPROVE–IMPLEMENT–VERIFY–SUSTAIN state machine, ownership, baselines, approvals, tasks, verification and lessons learned. |
| Advanced Operations Research Centre | `IMPLEMENTED_NEEDS_VALIDATION` | Shared optimization engines exist; LP/MILP/CP/nonlinear/network/transport/assignment/scheduling/facility-location/multiobjective formulations each need independent fixtures, solver/version and feasibility/optimality reporting and reproducibility. |
| Process Mining | `IN_PROGRESS` | Event-log case/activity/time/resource validation, process discovery, conformance checking, variants, loops, waiting/bottleneck and deviation analysis are not evidenced as a complete accepted workflow. |
| Industrial Digital Twin | `IN_PROGRESS` | Structural/scenario foundations exist. Level 2 data connections, Level 3 validated analytic links, Level 4 calibrated simulation and Level 5 approved operational monitoring are not established for a customer site. |
| Real-Time Industrial Monitoring | `EXTERNAL_CONFIGURATION_REQUIRED` | Monitoring tables/rules and telemetry methods exist; actual approved source feeds, data freshness, alert delivery, failure/recovery and customer network access must be configured and tested. |
| Logistics and Transportation Optimisation | `IN_PROGRESS` | Network/resilience foundation exists; complete VRP, delivery time windows, fleet/warehouse routing and independent distance/cost/capacity validations are not established. |
| Industrial Risk and Safety Engineering | `IN_PROGRESS` | Risk/FMEA foundations exist; configurable risk methods, bow-tie, hazard/control effectiveness, action closure and qualified review required. No automated declaration of safety. |
| Industrial Cost and Profitability Intelligence | `IN_PROGRESS` | Some economics/value-evidence methods exist; one governed cost model, allocation rules, double-counting controls, cost source dates and full cross-workspace comparison remain. |
| Engineering Knowledge Centre | `IN_PROGRESS` | Knowledge storage/search and Copilot context foundations exist; document approval/version/owner/classification, source-linked retrieval and tenant access acceptance remain. |
| 3D Factory Visualisation | `IN_PROGRESS` | Accurate editable 2D layout is the first requirement; no accepted geometry/coordinate-backed 3D model pipeline was established. |
| Executive Industrial Performance Centre | `IMPLEMENTED_NEEDS_VALIDATION` | Dashboard/control-tower foundations exist; governed KPI drill-down, role-bound source records, cross-department hosted acceptance and freshness disclosure remain. |
| Continuous Improvement Management | `IN_PROGRESS` | Evidence/value and enterprise workflow foundations exist; verified baseline → proposal → approval → tasks → measured effect → sustainment needs complete integration. |
| Advanced Excel Intelligence | `IMPLEMENTED_NEEDS_VALIDATION` | Workbook profiling, formula inventory, dependency/fidelity detection, version/evidence exports exist in part; full compatibility and formula/model conversion are not established. |
| Advanced Copilot | `IMPLEMENTED_NEEDS_VALIDATION` | Deterministic orchestration and approval foundations exist; specialist breadth, evaluation, external LLM configuration, prompt-injection robustness, scoped memory and replay remain. |

## 5. Additional operational workspaces

| Requested capability | Current status | Remaining implementation/acceptance |
|---|---|---|
| 6.1 Engineering Change and Configuration Management | `IN_PROGRESS` | Controlled revisioned specifications/BOM/parameters/instructions, impact analysis, approval/effective dates and supersession/rollback across linked assets/models/projects. |
| 6.2 Shutdown, Turnaround and Outage Management | `IN_PROGRESS` | Full shutdown scope/work packages, critical path, contractor/resources, material/permit readiness, costs, restart readiness and post-shutdown review. |
| 6.3 Product, Batch and Material Traceability | `IN_PROGRESS` | Batch/lot/serial genealogy, supplier-to-product history, inspection/quality/production links, affected-batch/recall analysis and evidence export. |
| 6.4 Laboratory and Testing Management | `IN_PROGRESS` | Sample chain, test plans/results, equipment calibration, review/approval, nonconformance links and reports; no accreditation claim. |
| 6.5 Procurement and Contract Intelligence | `IN_PROGRESS` | Quote/bid/total-cost comparison, supplier risk/performance, milestones, approval and human-reviewed extraction of contract terms. |
| 6.6 Frontline Work Instructions and Competency | `IN_PROGRESS` | Controlled revisions, skills/qualification matrix, expiry tracking, sign-offs, training records and work assignment gating. |
| 6.7 Environmental and Compliance Management | `IN_PROGRESS` | Governed waste/water/emissions factors and dates, permits/obligations, incident/actions and jurisdiction-specific professional review. |
| 6.8 Spare Parts Criticality and Lifecycle | `IN_PROGRESS` | Equipment-to-spare registry, criticality, obsolescence, repair/replace, lead-time and shutdown readiness integration. |
| 6.9 Mining Operations Intelligence | `IN_PROGRESS` | Shared module foundations exist, but ore/haulage/stockpile/reconciliation/energy-water per tonne require validated domain workflows and evidence. |
| 6.10 Operational Resilience and Business Continuity | `IMPLEMENTED_NEEDS_VALIDATION` | Resilience scenario foundations/tests exist; supplier/equipment/resource dependency maps, recovery assumptions, action tracking and tested scenarios remain. |

## 6. Excel Intelligence — precise status

The in-app Workbench Data capability and the Office.js add-in are different deliverables.

### In-app workbook capability

`IMPLEMENTED_NEEDS_VALIDATION` — source implementation includes:
- Workbook/multi-sheet import and data profiling.
- Data-quality and field intelligence.
- Formula inventory as inert evidence (not formula recalculation).
- OOXML fidelity checks for macros, external links, tables, charts, named ranges, pivots, hidden/merged cells, filters, validation and formatting metadata.
- Safe data-focused XLSX/evidence ZIP export and CSV formula-injection guards.
- Original source workbook is not overwritten.

Remaining:
- Exact hosted staging route/entitlement acceptance.
- End-to-end original-file preservation and round-trip verification on current deployed app.
- Full formula dependency graph / external reference resolution / calculation compatibility.
- Faithful preservation of source layout, macros, formulas, pivots, charts, validation and conditional formatting is not supported by the governed data-focused export.
- Complete workbook-to-Shoir-IE model conversion and independent reference tests.

### Office.js add-in

`EXTERNAL_CONFIGURATION_REQUIRED` / `IMPLEMENTED_NEEDS_VALIDATION`:
- A real task-pane scaffold and local deterministic planner exist.
- Local inspection, explicit approval and creation of a separate results worksheet are implemented in source.
- Its operation allow-list is intentionally limited (copy selection, trim text constants, SUM/AVERAGE summaries and column chart).

Still missing:
1. Actual hosted HTTPS task-pane and icon assets.
2. Replacement of `YOUR-SHOIR-IE-HOST` manifest placeholders.
3. Sideload/installation tests for supported Excel desktop and web clients.
4. Host compatibility tests, especially compressed OOXML export.
5. Dedicated Office add-in sign-in.
6. Short-lived, revocable Excel-scoped token exchange.
7. Authenticated workbook upload/transfer API with user consent, tenant boundary, rate limits, audit and retention.
8. Server-side workbook processing invoked from the add-in.
9. Secure, tested user/tenant isolation and deletion workflows for transferred files.

The current add-in is LOCAL_ONLY and does not upload workbooks. The browser workspace token must not be reused as an Office add-in token. The add-in is not deployment-ready or certified for Excel clients.

## 7. Copilot and AI governance — precise status

| Requirement | Current status | Remaining work |
|---|---|---|
| Natural-language classification and module recommendation | `IMPLEMENTED_NEEDS_VALIDATION` | Improve coverage, ambiguous intent handling and evaluation data. |
| Engineering analysis on supplied tabular data | `IMPLEMENTED_NEEDS_VALIDATION` | Expand specialist method coverage and independent evaluation. |
| Typed tool registry and approval metadata | `IMPLEMENTED_NEEDS_VALIDATION` | Bind every tool to real runtime actions and backend authorization; registry metadata alone is not an executable tool. |
| Nine specialist engineers | `IN_PROGRESS` | Verify each specialist's actual methods, evidence, scope and tool calls; no generic persona should be represented as a completed specialist. |
| Cross-workspace investigation | `IN_PROGRESS` | Authenticated retrieval, common dataset/KPI/asset IDs and evidence-linked reasoning. |
| Evidence-linked recommendations | `IN_PROGRESS` | Cite immutable calculation/data/run references and current freshness. |
| Prompt-injection defence | `IMPLEMENTED_NEEDS_VALIDATION` | Evaluate malicious workbook/document/external content and tool-output instruction handling. |
| Scoped AI memory | `IN_PROGRESS` | Inspect/correct/delete/disable flows, tenant and project scoping, consent, retention and isolation tests. |
| External generative model | `EXTERNAL_CONFIGURATION_REQUIRED` | No configured LLM is established in the inspected Excel status; provider, key, privacy, fallback, observability and evaluation are needed. |
| Replay and evaluation | `IN_PROGRESS` | Deterministic run records, replayable input versions, tool-level evaluations, feedback and failure recovery. |
| Consequential actions | `IMPLEMENTED_NEEDS_VALIDATION` | Prove backend permission and approval denial/acceptance paths for every write tool. |

## 8. Shared operational and enterprise platform

| Requested shared capability | Current status | Remaining implementation/acceptance |
|---|---|---|
| 7.1 Unified Asset and Equipment Registry | `IN_PROGRESS` | Stable rename-safe identity across module sources; hierarchy, ownership, specs, work/maintenance, quality, energy, spare parts and document links. |
| 7.2 Industrial Master Data Management | `IN_PROGRESS` | Authoritative IDs/units/reference records, duplicate conflict resolution, approval and source-aware mappings. |
| 7.3 KPI Governance | `IN_PROGRESS` | Versioned definitions/formulas/units/targets/owners/effective dates and approvals; consistent use across modules. |
| 7.4 Production Execution and Work Orders | `IN_PROGRESS` | Real work-order lifecycle, release/assignment, actual production/downtime/scrap and auditable completion. Do not claim full MES. |
| 7.5 Nonconformance, CAPA and Deviation | `IN_PROGRESS` | T039 is foundation-only; full persistent workflow, 8D, containment, root cause, corrective action, verification and effectiveness. |
| 7.6 Enterprise Portfolio and Benefits | `IN_PROGRESS` | Project portfolio, approved baseline, planned vs measured benefit, owner/resources/cost/milestones/risk and verification. |
| 7.7 Global Search | `IN_PROGRESS` | Complete authorised index and backend-enforced filtering for assets, docs, projects, workbooks, decisions and evidence. |
| 7.8 Notifications Centre | `IN_PROGRESS` | Persisted notification events, read/unread/preferences, delivery status, retries and alert deduplication. |
| 7.9 Shared Workflow Engine | `IN_PROGRESS` | Consistent status transitions, approver policies, rejection, escalation, comments and immutable audit across domains. |
| 7.10 Version History | `IN_PROGRESS` | Immutable versions/diffs/restore for models, projects, workbooks, KPIs, specs and documents. |
| 7.11 Import/Export Centre | `IMPLEMENTED_NEEDS_VALIDATION` | Unified job ledger, validation/errors/retries, permissions, history, provenance and download tests. |
| 7.12 Customer Administration | `IMPLEMENTED_NEEDS_VALIDATION` | Full organisation/site/team/invitation/role/account lifecycle and hosted cross-tenant tests. |
| 7.13 API and Webhook Management | `IN_PROGRESS` | Versioned API runtime, scoped credentials, rotation/revocation, event delivery, retries and public-facing abuse controls. |
| 7.14 Integration Health Centre | `IMPLEMENTED_NEEDS_VALIDATION` | Real customer source tests, freshness and redacted error/retry histories. |
| 7.15 Report Scheduling | `IN_PROGRESS` | Durable scheduler, recipient authorization, recurrence, delivery ledger, retries and cancellation. |
| 7.16 Help and Onboarding | `IMPLEMENTED_NEEDS_VALIDATION` | Complete guided journeys, contextual tutorials, troubleshooting, accessibility and verified module documentation. |

## 9. Engineering calculations and evidence standard

`IMPLEMENTED_NEEDS_VALIDATION` in part; not yet one fully proven common contract.

Still required across every critical calculation:
- Immutable input/dataset version references and source file/connector provenance.
- Formula/algorithm and version, input/output units and conversions.
- Dimensional validation, precision and rounding.
- Assumptions, constraints, warnings and errors.
- User/organisation/workspace and execution timestamp.
- Reproducibility metadata, random seed and solver version where relevant.
- Approval linkage for consequential actions.
- Independent known-answer fixtures, invalid/boundary/extreme/unit-conversion cases.
- A downstream stale-result signal when an input/version changes.

Optimisation must distinguish feasible, optimal, infeasible, unbounded, timeout and failed; heuristics cannot claim proven optimality. Simulations must disclose calibration, random seed, model/version, assumptions and uncertainty. Recommendations must separate measured from estimated, simulated and forecast impact.

## 10. Data architecture, Digital Thread and governance

| Requirement | Current status | Remaining work |
|---|---|---|
| Organisation/site/facility/area/asset/process/product/material/dataset relationships | `IMPLEMENTED_NEEDS_VALIDATION` | Full canonical hierarchy, all module mappings and hosted permissions. |
| Rename-independent canonical IDs | `IN_PROGRESS` | A source-key/legacy-ID improvement is in draft PR #229; CI and hosted acceptance are not complete. Some current source keys still include display/value text and therefore are not inherently stable. |
| Dataset lineage / downstream runs | `IN_PROGRESS` | T020 full immutable lineage, parent/child versions, transformation/event records and invalidation. |
| Tenant isolation | `IMPLEMENTED_NEEDS_VALIDATION` | Current authenticated cross-tenant database/file/search/export/AI denial test matrix remains incomplete. |
| Data retention/export/deletion | `IN_PROGRESS` | Complete user/organisation policy, server enforcement, evidence and restore/deletion tests. |
| Migration safety | `IMPLEMENTED_NEEDS_VALIDATION` | Repository/staging ledger reconciliation and full clean Postgres replay. |
| Internal-schema RLS | `TESTED` pending full regression confirmation | Staging migration enabled RLS on 12 private internal tables without policies; all 12 verified enabled, no FORCE, no policies, zero rows. Service operations and future least-privilege roles still need regression/policy design. |
| Backup/recovery | `BLOCKED_EXTERNAL` | Backup configuration and isolated restore rehearsal with measured RPO/RTO evidence. |

## 11. Security, identity and governance

| Requirement | Current status | Remaining work |
|---|---|---|
| Login/session/logout and revocation | `IMPLEMENTED_NEEDS_VALIDATION` | Fresh hosted authenticated session lifecycle and denial matrix. |
| RBAC and entitlements | `IMPLEMENTED_NEEDS_VALIDATION` | Full backend action/tenant/tier matrix for all routes, exports, jobs and AI tools. |
| MFA | `EXTERNAL_CONFIGURATION_REQUIRED` | Provider/policy/configuration and real staging challenge verification. |
| SSO/OIDC | `EXTERNAL_CONFIGURATION_REQUIRED` | Draft T098 work exists, but provider-backed sign-in/claims/revocation/audit are not accepted. |
| Protected administrator | `TESTED` for read-only staging aggregate invariant | Exactly one match and one active Enterprise Admin observed. Never use it as a test identity; recheck after reviewed account migrations only. |
| File security | `IMPLEMENTED_NEEDS_VALIDATION` | Cross-tenant storage, signed URL, upload resource-exhaustion, content and export denial tests. |
| SSRF/integration security | `IMPLEMENTED_NEEDS_VALIDATION` | Validate every actual transport path (DNS/IP pinning, redirect rejection, TLS, host/port allowlist, timeouts, rate limits). |
| AI security | `IMPLEMENTED_NEEDS_VALIDATION` | Prompt-injection, data exfiltration, tool escalation, cross-tenant retrieval and write-gate negative suite. |
| Audit history | `IN_PROGRESS` | Append-only, server-verified actor/event records and role-scoped review; user-editable workspace history is not enterprise audit evidence. |

## 12. Integrations and industrial connectivity

`EXTERNAL_CONFIGURATION_REQUIRED` for live customer connectors.

The repository includes read-only ERP adapter contracts, resource maps and security validation, but the ERP module explicitly states it contains no HTTP implementation or provider token handling. It cannot be described as a live SAP/Oracle connection.

Still required:
- Approved per-customer host/port and network allowlist.
- Server-side secret reference resolution.
- Provider-specific OAuth/certificate/auth and TLS implementation.
- DNS/IP/rebinding and redirect protection.
- Real customer endpoint and read-only credential.
- Resource discovery, mappings and sample validation.
- Import/sync with data provenance and freshness.
- Error/retry/rate limit/revoke tests.
- Real SAP S/4HANA, ECC, Oracle Fusion or EBS customer acceptance.
- MES/CMMS/EAM/IoT/plant feed adapters as approved by each customer.

No network call is to be made at application import time and no write access to a customer's ERP/MES/OT system is included without separate approval.

## 13. User experience, accessibility and localisation

| Requirement | Current status | Remaining work |
|---|---|---|
| Existing Streamlit visual identity/navigation | `IMPLEMENTED_NEEDS_VALIDATION` | Regression and hosted rendering at current build. |
| Responsive layout | `IMPLEMENTED_NEEDS_VALIDATION` | Full route-level desktop/tablet/mobile overflow and clipping checks. |
| Arabic/RTL | `IN_PROGRESS` | End-to-end localized navigation, forms, mixed text, numbers, charts, dialogs and exports. |
| Accessibility | `IN_PROGRESS` | Keyboard, screen reader, labels, contrast, focus and accessible chart/error tests. |
| Industrial data display | `IMPLEMENTED_NEEDS_VALIDATION` | Every chart/table must expose units, source, range, freshness, missing data and assumptions. |
| Loading/error/empty states | `IMPLEMENTED_NEEDS_VALIDATION` | Full route-by-route and async-failure acceptance. |

## 14. Subscription, entitlement and commercial readiness

| Requirement | Current status | Remaining work |
|---|---|---|
| Six package/add-on model and 96-module catalogue | `IMPLEMENTED_NEEDS_VALIDATION` | Complete all tier/add-on/user/storage/usage and cross-organisation enforcement tests. |
| Research Pack add-on separation | `IMPLEMENTED_NEEDS_VALIDATION` | Verify add-on activation/removal and tier precedence on the hosted app. |
| Upgrade/downgrade/expiry | `IMPLEMENTED_NEEDS_VALIDATION` | Full billing/entitlement lifecycle and denial evidence. |
| Pricing/subscription terms/refunds | `IMPLEMENTED_NEEDS_VALIDATION` | Qualified legal review and exact live customer journey. |
| Privacy/terms/consent/deletion | `IMPLEMENTED_NEEDS_VALIDATION` | Saudi legal and PDPL review, data flow, processor, residency, retention and deletion approval. |
| Billing/customer communication/support/incident process | `IN_PROGRESS` | Operational owner, support contacts, incident runbook, SLA limits and customer communications. |
| Certifications/endorsements | `NOT_STARTED` unless separate external evidence exists | No Aramco/SABIC/Ma'aden endorsement or enterprise certification may be claimed without evidence. |

## 15. Performance, reliability and operations

| Requirement | Current status | Remaining work |
|---|---|---|
| Database query/index review | `IMPLEMENTED_NEEDS_VALIDATION` | Production-scale workload profiling is not established; do not load-test production under staging-only authority. |
| Large workbook and dataset limits | `IMPLEMENTED_NEEDS_VALIDATION` | Realistic memory/CPU/concurrency tests and explicit limits across all routes. |
| Background jobs | `IMPLEMENTED_NEEDS_VALIDATION` | Durable queue lifecycle, cancellation, idempotency, retries, worker crash recovery and duplicate-side-effect tests. |
| Logs/errors/metrics/alerts | `IN_PROGRESS` | Central operational observability with secret redaction and actionable alert routing. |
| Backup configuration | `BLOCKED_EXTERNAL` | Operator confirms provider backups, retention and storage strategy. |
| Restore rehearsal | `BLOCKED_EXTERNAL` | Restore database and files in isolated staging; measure RPO/RTO; retain sign-off. |
| Disaster recovery documentation | `IN_PROGRESS` | Document runbooks and validate restoration, failure recovery and communications. |
| Availability/SLAs | `NOT_STARTED` for a customer commitment | Do not promise uptime or recovery objectives until measured and approved. |

## 16. Testing and acceptance journeys still required

The latest general staging CI run on 2026-11-03 passed its automated test job, but hosted smoke and authenticated release gate were skipped. It does not replace the prompt's full workflows.

| Journey from request | Current status | Required proof |
|---|---|---|
| A Manufacturing | `IMPLEMENTED_NEEDS_VALIDATION` | Import → capacity → bottleneck → simulation → comparison → report. |
| B Inventory | `IMPLEMENTED_NEEDS_VALIDATION` | Import demand/inventory → classification/policy → scenarios → recommendation/export. |
| C Maintenance | `IN_PROGRESS` | Asset/failure import → reliability → review/action → track. |
| D Quality | `IMPLEMENTED_NEEDS_VALIDATION` | Measurements → control/capability → nonconformance → corrective action. |
| E Facility Layout | `IMPLEMENTED_NEEDS_VALIDATION` | Layout/flows → distance/cost → alternatives → approval. |
| F Project Controls | `IMPLEMENTED_NEEDS_VALIDATION` | WBS → dependencies/baseline → actuals/EVM → report. |
| G Excel Intelligence | `IMPLEMENTED_NEEDS_VALIDATION` | Upload → fidelity/formula review → approved changes → export/reopen/compare. |
| H Copilot | `IMPLEMENTED_NEEDS_VALIDATION` | Context → approved typed tool → reference calculation → evidence/limits → approval. |
| I Cross-workspace recommendation | `IN_PROGRESS` | Real authorised source linkage → opportunity → evidence → approved project → measured result. |
| J Enterprise administration | `IMPLEMENTED_NEEDS_VALIDATION` | Disposable organisation/users/roles/tier/exports/audit and all denial cases. |
| K Integration health | `EXTERNAL_CONFIGURATION_REQUIRED` | Real test connector, safe sample read, freshness, simulated failure and recovery. |

Negative tests still needed across all relevant domains: missing/invalid inputs, units, extreme values, duplicate/large/malformed files, unsupported formulas, permission escalation, expired sessions, stale data, failed network/database calls, infeasible solver, incomplete logs and concurrent changes.

## 17. Implementation deliverables status

| Requested deliverable | Status |
|---|---|
| Master readiness audit | `IMPLEMENTED_NEEDS_VALIDATION` — draft PR #228 |
| Complete feature-completion matrix | `IMPLEMENTED_NEEDS_VALIDATION` — detailed CSV plus consolidated matrix |
| Architecture/data flow | `IMPLEMENTED_NEEDS_VALIDATION` — draft documentation |
| Workspace/module docs | `IN_PROGRESS` — full per-module technical/use docs remain |
| Calculation methodology library | `IN_PROGRESS` — critical methods still need independent fixtures |
| Data provenance docs | `IN_PROGRESS` |
| Security review | `IMPLEMENTED_NEEDS_VALIDATION` — draft review and staging RLS step |
| Tenant isolation evidence | `IN_PROGRESS` |
| Integration guide | `IMPLEMENTED_NEEDS_VALIDATION` — adapter architecture exists, live connector acceptance does not |
| AI Copilot tool/security guide | `IN_PROGRESS` |
| Excel compatibility guide | `IMPLEMENTED_NEEDS_VALIDATION` — documented limitations, hosted acceptance incomplete |
| Migration docs | `IN_PROGRESS` — ledger/source reconciliation outstanding |
| Backup/restore evidence | `BLOCKED_EXTERNAL` |
| Test report | `IMPLEMENTED_NEEDS_VALIDATION` — current feature PR workflows still being resolved |
| Staging acceptance report | `IMPLEMENTED_NEEDS_VALIDATION` — hosted authenticated gate not run on current candidate |
| Limitations/dependency registers | `IMPLEMENTED_NEEDS_VALIDATION` |
| Release decision | `NO-GO` |
| Rollback instructions | `IN_PROGRESS` — migration-specific procedure and recovery drill still required |
| User onboarding/operating manual | `IN_PROGRESS` |

## 18. Immediate engineering priorities

1. Close the Digital Thread identity regression failure; keep PR #229 draft until exact-head CI and review pass.
2. Close the staging RLS migration filename/history mismatch; keep PR #230 draft until versioned migration replay and service-path regression pass.
3. Verify the post-RLS Edge/server-role operations and private-schema access contract.
4. Reconcile the actual staging migration ledger and tracked source without replaying historical data-changing migrations.
5. Complete authenticated hosted staging acceptance using disposable E2E users and exact current build marker.
6. Complete the RLS/tenant isolation matrix for database, file, search, export and AI tool paths.
7. Complete dataset immutability/lineage (T020), Undo/Redo recovery (T006), CAPA (T039) and the other 8 foundation-only tools.
8. Complete calculation reference tests and each end-to-end journey.
9. Complete Excel Stage 1 and the genuine Office host/identity/transfer requirements.
10. Complete Copilot tool coverage, security evaluation and role/approval tests.
11. Complete externally configured integrations, identity, backup/recovery and legal review.
12. Only then re-evaluate BETA removal and release gates.

## 19. Explicit completion rule

A capability remains incomplete until all relevant conditions are met: code, UI, backend, persistence, integration with shared services, role and entitlement enforcement, provenance, error handling, documentation, independent tests, negative tests and exact-build staging acceptance.

Never translate `FOUNDATION_ONLY` into a complete feature. Never claim the whole Shoir-IE mission is finished because every requested item has a row, a page, or a registry entry.

**Current overall decision: NO-GO.** The objective is full implementation, but the current evidence does not justify a claim that every item is complete or bug-free.
