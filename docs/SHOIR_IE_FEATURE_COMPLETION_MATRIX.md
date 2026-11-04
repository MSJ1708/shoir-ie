# Shoir-IE Feature Completion Matrix

**Snapshot:** 2026-11-04  
**Source of truth for detailed 100-tool rows:** [SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv](SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv)  
**Status vocabulary:** use the exact statuses below for new reporting. Do not silently translate legacy matrix values into stronger claims.

## Status definitions

- `NOT_STARTED`: no implementation found after the scoped audit.
- `IN_PROGRESS`: a partial implementation or foundation exists; required functionality is incomplete.
- `IMPLEMENTED_NOT_TESTED`: implementation evidence exists but no relevant test has been run.
- `IMPLEMENTED_NEEDS_VALIDATION`: code and/or automated tests exist, but end-to-end, hosted or independent engineering validation remains open.
- `TESTED`: the applicable feature-specific test criteria passed; this does not imply hosted verification.
- `STAGING_VERIFIED`: exact feature workflow passed on the identified hosted staging build with retained evidence.
- `EXTERNAL_CONFIGURATION_REQUIRED`: repository implementation depends on credentials, host setup, provider or customer configuration not established by source alone.
- `BLOCKED_EXTERNAL`: an external prerequisite currently prevents the next acceptance step.
- `FAILED`: a required test or acceptance criterion failed.
- `DEPRECATED`: the feature has intentionally been retired.

## Canonical 100-tool inventory

The current source matrix contains 100 unique IDs (T001–T100) with no duplicate IDs. Existing IDs must remain unchanged.

| Legacy status in source matrix | Normalised status for this review | Count | Interpretation |
|---|---|---:|---|
| IMPLEMENTED_NEEDS_VALIDATION | IMPLEMENTED_NEEDS_VALIDATION | 87 | Source implementation is mapped; tool-level authenticated persistence, browser and evidence acceptance remain open. |
| FOUNDATION_ONLY | IN_PROGRESS | 11 | Partial foundation only; do not expose or describe the full capability as complete. |
| EXTERNAL_CONFIGURATION_REQUIRED | EXTERNAL_CONFIGURATION_REQUIRED | 2 | Provider/customer setup and hosted tests required. |
| **Total** |  | **100** | No claim that 100 tools are staging verified. |

### Foundation-only entries

| ID | Canonical tool | Status | Main gap retained from source inventory |
|---|---|---|---|
| T006 | Undo, Redo, and Recovery | IN_PROGRESS | No complete cross-module undo/redo contract. |
| T020 | Dataset Versioning and Lineage | IN_PROGRESS | Immutable versions, downstream invalidation and durable lineage require verification. |
| T039 | CAPA and 8D Manager | IN_PROGRESS | Verify all disciplines, approvals, attachments and auditable transitions. |
| T044 | Reliability-Centered Maintenance Assistant | IN_PROGRESS | Do not claim certified RCM; specialist logic and independent review remain necessary. |
| T046 | Ergonomics Assessment Toolkit | IN_PROGRESS | Verify methods, required inputs and scoring tables against independent fixtures. |
| T060 | Supply Chain Network Planner | IN_PROGRESS | Validate network formulations and independent flow/cost cases. |
| T074 | Digital Twin Calibration Studio | IN_PROGRESS | No validated calibration pipeline or configured live plant source established. |
| T080 | Industrial Disruption Simulator | IN_PROGRESS | No calibrated industrial disruption engine established; retain SYNTHETIC/LIVE labels. |
| T094 | KPI Dashboard and Alert Center | IN_PROGRESS | Source aggregation, threshold persistence, access scoping and duplicate-alert tests remain. |
| T097 | API, SDK, and Plugin Toolkit | IN_PROGRESS | Verify executable interfaces and permissions; metadata-only plugins are not runnable tools. |
| T099 | Data Governance and Recovery Center | IN_PROGRESS | Restore/delete workflows need isolated staging, tenant-scope tests and recovery proof. |

### External configuration entries

| ID | Canonical tool | Status | External prerequisite |
|---|---|---|---|
| T096 | Integration Management Center | EXTERNAL_CONFIGURATION_REQUIRED | Approved endpoints, credentials, permissions, network access and staging connection tests. |
| T098 | Enterprise Identity and Audit Center | EXTERNAL_CONFIGURATION_REQUIRED | Approved OIDC/identity provider setup, MFA policy and authenticated security/audit acceptance. |

## Original nine engineering workspaces and two shared capabilities

The statuses below are deliberately conservative workspace-level assessments. They reflect the current source/test inventory and the absence of current authenticated hosted acceptance; they do not certify every calculation or sub-feature.

| Area | Status | Source/test evidence found | Acceptance still required |
|---|---|---|---|
| 1. Manufacturing & Capacity Optimisation | IMPLEMENTED_NEEDS_VALIDATION | `shoir_capacity_recovery.py`, `shoir_target_engines.py`; `test_shoir_capacity_recovery.py`, `test_shoir_target_engines.py` | Reference cases for takt, capacity, line balance, precedence, product mix and throughput; authenticated scenario workflow. |
| 2. Supply Chain & Inventory Intelligence | IMPLEMENTED_NEEDS_VALIDATION | `shoir_target_engines.py`, `shoir_forecasting.py`; `test_shoir_target_engines.py`, `test_shoir_forecasting.py` | Time-aware forecast splits, baseline comparison, stochastic assumptions, lead-time cases and hosted import/export. |
| 3. Predictive Maintenance & Reliability | IN_PROGRESS | Reliability/maintenance foundations and RCM catalogue entry T044; related engineering tests exist | Independent MTBF/MTTR/availability/Weibull fixtures, leakage-safe model evaluation and specialist RCM review. |
| 4. Quality Engineering | IMPLEMENTED_NEEDS_VALIDATION | `industrial_experience.py`, target-engine methods; `test_industrial_quality_recovery.py`, `test_shoir_target_engines.py` | Reference cases for SPC, capability/performance distinction, MSA, sampling assumptions and CAPA workflow. |
| 5. Facility Layout & Material Flow | IMPLEMENTED_NEEDS_VALIDATION | `shoir_facility_layout.py`; `test_facility_layout.py` | Hosted From-To/layout workflow, geometry-distance consistency, alternative comparison and export verification. |
| 6. Project Controls & Cost Intelligence | IMPLEMENTED_NEEDS_VALIDATION | `shoir_enterprise_ops.py`, `shoir_value_evidence.py`; `test_shoir_enterprise_ops.py`, `test_shoir_value_evidence` coverage where present | WBS/dependency/schedule and EVM reference fixtures, cost allocation and verified benefit lifecycle. |
| 7. Workforce & Operations Scheduling | IMPLEMENTED_NEEDS_VALIDATION | Industrial experience/target-engine foundations; `test_industrial_experience.py`, `test_shoir_target_engines.py` | Hard/soft constraint, skill/rest/coverage feasibility and infeasibility explanation tests. |
| 8. Energy & Resource Efficiency | IN_PROGRESS | Shared target-engine and enterprise performance foundations; no specific end-to-end acceptance evidenced in this review | Source/effective dates for tariffs and emissions factors, measured-versus-estimated benefits and independent intensity tests. |
| 9. Decision Intelligence & Simulation | IMPLEMENTED_NEEDS_VALIDATION | `aegis_sim.py`, `shoir_experiment_engine.py`, `shoir_resilience_suite.py`; related regression tests | Reproducibility, calibration, solver-state classification and evidence-linked scenario acceptance. |
| 10. Excel Intelligence (shared capability) | IMPLEMENTED_NEEDS_VALIDATION | `shoir_excel_runtime.py`, `shoir_excel_studio.py`, Workbench Data route; Excel implementation docs/tests | Full Stage 1 remains open; Office host compatibility, hosted route and import/export round trips remain unverified. |
| 11. Industrial Engineering Copilot (shared capability) | IMPLEMENTED_NEEDS_VALIDATION | `shoir_copilot_orchestrator.py`, `shoir_tool_registry.py`, `test_shoir_copilot_orchestrator.py` | Exact staging browser flow, tool permission/approval tests, prompt-injection evaluation and evidence replay. Current in-app engine is deterministic; external generative-model use is not configured. |

## Additional capability groups

| Capability group | Status | Evidence and current limitation |
|---|---|---|
| Digital Thread / canonical identity | IN_PROGRESS | `shoir_digital_thread.py` exists; current derived ID includes node display name and is not rename-safe. |
| Cross-workspace recommendation and benefits | IN_PROGRESS | Value-evidence and enterprise services exist; full linked measure-to-verify workflow remains unproven. |
| Operations Research | IMPLEMENTED_NEEDS_VALIDATION | Optimization modules/tests exist; verify formulations, solver versions, feasibility, optimality gaps and reproduced runs. |
| Process Mining | IN_PROGRESS | No complete event-log discovery/conformance acceptance was established in this source review. |
| Digital Twin | IN_PROGRESS | Structural/scenario foundations exist; calibrated live operational twin is not established. |
| Real-time monitoring | EXTERNAL_CONFIGURATION_REQUIRED | Monitoring tables and rules exist; real feed, freshness and alert delivery need approved source configuration. |
| Logistics / routing | IN_PROGRESS | Network/resilience foundations exist; complete routing and independently verified route-cost workflow is not established. |
| Risk and safety engineering | IN_PROGRESS | FMEA/risk-related foundations exist; no automated declaration of operational safety is permitted. |
| Engineering knowledge centre | IN_PROGRESS | Knowledge service foundations exist; source approval, versioning, access and citation acceptance remain. |
| 3D factory visualisation | IN_PROGRESS | Accurate 3D model pipeline was not established; prioritise validated 2D layouts. |
| Executive performance / KPI governance | IMPLEMENTED_NEEDS_VALIDATION | Existing dashboard and KPI foundations require governed definitions, source links and role-tested drill-down. |
| Change, shutdown, traceability, laboratory, procurement, competency and spare parts | IN_PROGRESS | Shared enterprise service foundations exist; each domain workflow must be audited and accepted before it is presented as complete. |
| Customer administration, API/webhooks, notifications and report scheduling | IN_PROGRESS | Enterprise service foundations are present; live role/tenant, delivery, revocation and hosted acceptance remain open. |

## Rules for maintaining this matrix

1. Keep T001–T100 canonical IDs and the 96-module subscription catalogue intact.
2. Do not allocate new IDs until the complete repository and existing registries are searched.
3. Attach source path, backend/table, UI route, entitlement, test and retained evidence for each feature row.
4. Do not promote an item to TESTED because the global pytest suite passed; require relevant feature-specific tests.
5. Do not promote an item to STAGING_VERIFIED without exact-build authenticated hosted evidence.
6. Keep the detailed source CSV as the canonical 100-tool row inventory; this document is the consolidated readiness view, not a duplicate replacement.
