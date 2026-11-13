# Industrial Resource Intelligence & Resilience — implementation evidence

Assessment date: 2026-11-13  
Repository: `MSJ1708/shoir-ie`  
Working branch: `feat/shoir-ie-release-hardening-20261105`  
Parent release PR: [#232 — draft, staging target](https://github.com/MSJ1708/shoir-ie/pull/232)  
Release decision: **BETA / NO-GO. No production deployment or migration is authorized.**

## 1. Current implementation boundary

The new capability is registered inside Shoir-IE's existing module catalogue, Workbench module matrix, Enterprise entitlement policy and Explorer module catalogue. It does not add a separate application, a new top-level navigation section, or a 101st canonical entry to the existing 100-tool target registry.

The module label is **Industrial Resource Intelligence**. Its product heading is **Industrial Resource Intelligence & Resilience System**; its engineering concept is the **Industrial Exchange Intelligence Twin (IEIT)**.

The first vertical slice is an explicit-input engineering workspace with deterministic calculation functions. It is not the complete multi-company industrial network product described in the master implementation prompt. The implementation deliberately avoids claiming live supplier availability, live ERP/LIMS/SCADA connectivity, physical infrastructure, legal compliance, verified savings, insurance underwriting, or autonomous operational authority.

## 2. Repository changes in this feature slice

| File | Change |
|---|---|
| `shoir_resource_intelligence.py` | New deterministic engineering services for passport validation, resource balance/loss screening, compatibility, constrained resource allocation, supply-disruption scenarios, dependency propagation, safety gating, value calculation, exploratory quality forecasting, historical delivery reliability, cascade ranking, bottleneck/infrastructure/intensity screening and CSV-row validation. |
| `shoir_resource_intelligence_ui.py` | New Streamlit workspace rendered inside the existing Workbench. Includes facility profile, shared secure CSV/XLS/XLSX import, resource passports, balance screening, compatibility, demand/route entry, LP optimizer, disruption and dependency screens, safety gate, value calculation, history screening, cascade ranking, bottleneck/infrastructure screens and JSON evidence export. |
| `industrial_platform_excellence.py` | Adds the module to the existing Workbench module matrix at Enterprise. |
| `shoir_tier_capabilities.py` | Adds an explicit Enterprise module entitlement. Existing plan definitions and the 100-tool catalogue are unchanged. |
| `industrial_platform.py` | Adds the module to `PLATFORM_CATALOG` and routes direct module calls to the dedicated renderer rather than a generic placeholder. |
| `pages/Industrial_Engineering_Workbench.py` | Adds the route and search aliases to the existing sidebar module search. Keeps the existing selector and native tier check. |
| `app.py` | The Explore Modules catalogue receives the shared catalogue entry and an Enterprise-gated Workbench launch action. Direct module dispatch uses the dedicated renderer. |
| `tests/test_shoir_resource_intelligence.py` | Adds deterministic engineering tests and a Workbench AppTest for IEIT alias discovery, launch and Starter-tier denial. |
| `docs/INDUSTRIAL_RESOURCE_INTELLIGENCE_STATUS.md` | This status and acceptance-boundary record. |

No Supabase migration, Edge Function, external credential, customer record, subscription price, protected administrator, staging database or production resource was changed for this feature.

## 3. Capability completion matrix

The labels below follow the master prompt's completion vocabulary. **PARTIALLY_IMPLEMENTED** means a real foundation exists but the full requested capability is not complete. **BLOCKED_EXTERNAL_DEPENDENCY** identifies capabilities that need a real customer / infrastructure / regulated-provider input before they can be completed or validated.

| Master prompt capability | Current status | Implemented foundation | Remaining work / reason it is not complete |
|---|---|---|---|
| 1. Industrial Resource Passport | PARTIALLY_IMPLEMENTED | Facility-linked record; owner, English/Arabic descriptions, source process/equipment, type, quantity/unit, numeric quality, temperature/pressure, availability window, seasonal notes, storage/transport requirements, treatment/safety notes, source/lab/certificate references, certificate-valid-until text, measurement timestamp and provenance. | Certificate expiry verification, controlled bilingual vocabulary, attachments, versioned history and tenant-scoped persistence remain incomplete. |
| 2. Resource Exchange Discovery | PARTIALLY_IMPLEMENTED | Explicitly entered demand and exchange-route candidates; no supplier availability is inferred. | No live marketplace, participant directory, confidential matching, treatment/logistics provider or customer opt-in network exists. |
| 3. Cross-Company Process Compatibility Twin | PARTIALLY_IMPLEMENTED | Deterministic type/unit and buyer quality-limit screen; supports numeric quality, temperature and pressure limits; explicit lab/engineering hold statuses. | Full composition chemistry, thermodynamics, phase behavior, contamination interaction, equipment envelope, secondary waste and qualified process models remain absent. |
| 4. Plant Resource Loss and Recovery | PARTIALLY_IMPLEMENTED | Same-unit input/output balance and suspected-discrepancy alert; never calls a discrepancy a confirmed loss. | Multi-stream source mapping, root-cause evidence, recovery project workflow, measured implementation results and persistent action ownership remain incomplete. |
| 5. Multi-Resource Process Integration | PARTIALLY_IMPLEMENTED | Same-boundary energy balance; waste-heat source/sink temperature-approach screen; single-contaminant water-reuse LP with explicit source, sink, connection, flow and blended-concentration constraints. | No multi-contaminant water pinch, heat-exchanger network synthesis, steam pressure optimization, exergy, treatment/energy co-optimization or cross-utility optimization. Actual exchanger duty, treatment performance and reuse safety require qualified engineering design. |
| 6. Resource Quality Forecasting | PARTIALLY_IMPLEMENTED | Time-aware exploratory linear trend, chronological holdout MAE and approximate residual band when at least 20 valid observations are provided. | No validated plant model, multivariate process inputs, seasonality, model monitoring or qualified backtesting acceptance. |
| 7. Supply Reliability Predictor | PARTIALLY_IMPLEMENTED | Historical in-full-and-quality pass rate and standard error from explicit delivery periods. | It explicitly does not predict future reliability; no verified supplier history, schedule integration or outage model is connected. |
| 8. Exchange Reliability Engine | PARTIALLY_IMPLEMENTED | Supplier quantity shock, relaxed allocation with explicit shortage, and downstream graph traversal. | No integrated time-dependent quality/supply forecasts, complete physical dependency model, recovery alternatives or network-wide validation. |
| 9. Resource Substitution Intelligence | PARTIALLY_IMPLEMENTED | The compatibility screening service can be reused to screen a proposed substitute. | No substitution catalogue, product/process consequence model, safety case or qualified approval workflow exists. |
| 10. Multi-Company Resource Optimizer | PARTIALLY_IMPLEMENTED | Single-period LP transportation allocation with supply caps, demand satisfaction, and explicitly entered route capacities and resource/transport/treatment costs; missing capacity or cost inputs are rejected rather than defaulted. Type/unit/quality screening and independent reconciliation are included. | No MILP, multi-period production/maintenance scheduling, storage, infrastructure constraints, uncertainty sets, multi-objective solve or cross-company network. Conditional treatment routes are not optimizer-eligible. |
| 11. Resource Cascade Optimizer | PARTIALLY_IMPLEMENTED | Deterministic prevention-first ranking of entered opportunity actions. | No quantity-conserving cascade network, overlapping opportunity prevention or marginal-value route optimizer. |
| 12. Resource Bottleneck Detector | PARTIALLY_IMPLEMENTED | Deterministic smallest-capacity screen over entered capacity constraints with exact-unit checks and shortfall. | No process-network constraint graph, binding-constraint optimization, equipment operating windows or time-dependent capacity model. |
| 13. Contingency and Resilience Simulator | PARTIALLY_IMPLEMENTED | Single-supplier fractional supply shock and shortage re-optimization; recovery time stays unset without evidence. | No time-stepped multi-event discrete simulation, quality failure/treatment failure models, storage depletion schedule or validated recovery playbook. |
| 14. Infrastructure Co-Optimization | PARTIALLY_IMPLEMENTED | Preliminary route screen requires user-asserted connection confirmation, route distance, capacity, demand and access/permit/engineering reference fields; it never returns operational authorization. | No GIS/route survey, hydraulic design, pressure/flow model, physical access verification, CAPEX/OPEX optimization, permit validation or construction approval. Real route/permit evidence remains an external dependency. |
| 15. Physical Feasibility and Safety Gate | PARTIALLY_IMPLEMENTED | Critical failure forces REJECTED; laboratory and engineering/safety/environmental references are required for evidence-recorded state; no operational authorization is returned. | No Saudi or international regulatory rule library, material incompatibility database, permit-source/version register or independently qualified approval. |
| 16. Industrial Exchange Assurance | PARTIALLY_IMPLEMENTED | Structured supplier/buyer agreement drafts with quantity tolerance, quality limits, schedule, certificate requirement, treatment/testing responsibilities, shortage/rejection procedures and four approval-reference fields; delivery assessments compare quantities, quality and certificate validity and retain deviations/evidence references. | Approval references are not signatures; no legally reviewed contract, participant authentication, cross-organization approvals, immutable audit lifecycle, automatic contractual remedy or operational release exists. Delivery status always requires human acceptance and carries no contractual effect. |
| 17. Industrial Proof of Value | PARTIALLY_IMPLEMENTED | Supplier, buyer and transfer-neutral network formulas. Internal sale revenue is excluded from network value to avoid double-counting. | No customer baseline/counterfactual records, volume normalization, actual delivery reconciliation, emissions factors or independent verification evidence. |
| 18. Resource Quality Digital Memory | PARTIALLY_IMPLEMENTED | Passport additions/imports append workspace revision snapshots with actor/time fields, content SHA-256, parent revision hash and a verifier; history is included in the explicit per-user workspace save and JSON export. | The workspace is editable and can be rewritten/deleted; hashes do not provide immutable storage, an independent timestamp authority, certified chain of custody, laboratory integration or managed entity lineage. |
| 19. Confidential Industrial Intelligence Network | BLOCKED_EXTERNAL_DEPENDENCY | Module requires authenticated user and Enterprise entitlement; current save action explicitly refuses to write resource data into an active organization-shared workspace. | No resource-specific organization tenant schema, attribute-based disclosure, approved cross-company matching or authorized company participant network exists. |
| 20. Exchange Failure Risk Intelligence | PARTIALLY_IMPLEMENTED | Explicit supplier shock and shortage exposure in a one-period allocation. | No replacement-provider database, contract exposure model, validated recovery-time distribution, insured risk or financial guarantee. |
| 21. Emergency Resource Network | BLOCKED_EXTERNAL_DEPENDENCY | No fictitious resource inventory or emergency capacity is shown. | Requires qualified participant registration, current availability, quality certificates, transport availability, permits and emergency coordination agreement. |
| 22. Industrial Cluster Twin | NOT_IMPLEMENTED | User-entered dependency graph can show downstream node reachability. | No geographic cluster asset registry, geospatial routes, verified infrastructure, participant data sharing or time-aware cluster twin. |
| Production and maintenance-aware optimizer | NOT_IMPLEMENTED | — | The current LP is a single-period flow allocation; no production/MRO calendar or asset availability constraints are included. |
| Uncertainty-aware optimization | NOT_IMPLEMENTED | Forecast intervals are displayed separately; they are not used in an optimizer. | Needs data-backed uncertainty distributions/scenarios, robust/stochastic formulations and validation. |
| Investment prioritization | NOT_IMPLEMENTED | — | Needs approved cost/benefit inputs, engineering feasibility, safety, risk, portfolio constraints and reproducible financial metric policy. |
| Performance persistence monitor | PARTIALLY_IMPLEMENTED | Production-normalized usage-intensity comparison between baseline and reporting period; output is explicitly not independently verified. | No continuous monitoring, operating-condition adjustment, degradation detection, persistence alerts, project implementation record or verified savings lifecycle. |
| Engineering knowledge/model assurance | PARTIALLY_IMPLEMENTED | Calculation methods are deterministic, inspectable and covered by tests; limits and assumptions are returned in outputs. | No versioned standards library, calculation-method approval register, qualified references or full model registry integration. |

## 4. Engineering method boundaries

### Resource passport

The passport stores owner and source process/equipment text, English/Arabic descriptions, availability/seasonal notes, storage and transport requirements, laboratory and certificate references, and certificate-valid-until text. A reference is not a certificate authenticity or expiry verification.

### Resource memory and revision history

When a passport is manually created or imported, the UI appends a workspace revision containing the passport snapshot, recorded actor/time, content SHA-256 and parent revision hash. The Resource Memory tab recomputes the content and event hashes and checks revision continuity. This can reveal accidental or partial edits to the currently saved data, but it is not immutable: a workspace editor can rewrite or delete the complete history, and no external timestamp authority or independent custodian is used. It is not a certified chain-of-custody record.

### Resource balance

The balance compares same-period input and accounted output in the same user-entered unit. It reports a discrepancy outside tolerance as **suspected**, never as a confirmed leak. Meter accuracy, boundary completeness, time alignment, inventory change and unmeasured streams must be investigated separately.

### Energy balance and waste heat

The energy balance compares same-boundary input against useful output, entered waste heat and other output in kWh. A residual outside tolerance is an unreconciled discrepancy, not proof of a specific energy loss. The waste-heat screen checks only whether the entered source temperature exceeds the sink temperature plus the minimum approach. A positive screen can estimate gross thermal energy from user-entered heat rate and operating hours, but it is not an exchanger design, recovered-energy measurement, efficiency estimate or verified savings calculation.

### Water reuse

The current water reuse LP covers one named dissolved-contaminant concentration only. It maximizes flow across entered source/sink connections while enforcing source supply, sink demand, connection capacity and a blended concentration limit. Physical connections require an explicit user confirmation plus an evidence-reference field, but that evidence is not independently checked. The model does not represent additional contaminants, microbial hazards, treatment units, secondary waste, process-specific chemistry, storage/time schedules or permit requirements; it is not a water-pinch study or permission to reuse water.

### Compatibility

The current screen requires exact resource-type and unit agreement. It does not perform hidden unit conversions. Numeric properties are compared with explicit buyer minimum/maximum bounds. Missing essential measurements return INSUFFICIENT_DATA. A treatment record can be shown as COMPATIBLE_SUBJECT_TO_TREATMENT only when residual values and an entered evidence reference/approver are supplied; the output explicitly says that this assertion is not independently verified. The LP optimizer rejects this conditional status until a separate qualification step exists.

### Network allocation

The LP is single-period and deterministic. It allocates only through routes that pass the current raw-resource compatibility screen. Supply limits, demand equality and explicitly entered route capacities are enforced; transport and treatment costs must also be entered explicitly, including deliberate zero values. No missing route capacity or cost is silently defaulted. A solver result is independently reconciled. Infeasible inputs return INFEASIBLE. It is not a multi-period MILP and does not model actual pipelines, production schedules, tank constraints, pressure, permits or contract commitments.

### Forecasting and reliability

Quality forecasting requires a minimum history and includes a chronological holdout error, but remains an exploratory linear trend with an approximate residual interval. Historical supply reliability is an empirical pass rate only. Neither output claims future probability or an operational service-level guarantee.

### Bottlenecks and infrastructure

The bottleneck screen identifies the smallest entered capacity after enforcing exact unit agreement. It does not infer an unentered capacity. The infrastructure screen requires a user-confirmed physical connection and records distance, capacity and evidence references; any positive result is only preliminary, user-asserted and not operational authorization.

### Exchange assurance

Agreement records are drafts only. The module records supplier/buyer, resource, quantity and tolerance, quality limits, schedule, certificates, treatment/testing responsibilities, shortage/rejection procedures and engineering/safety/environmental/commercial reference fields. Recording all four references does not sign a contract. Delivery assessments compare actual quantity, entered quality values, certificate reference and expiry date, and delivery evidence. They flag shortages, excess, missing quality, out-of-specification results and missing/expired certificates. Each result requires human acceptance and explicitly returns no contractual effect or operational authorization.

### Safety and value

A safety result with all reference fields supplied means only that references were entered. The code does not inspect their issuer, validity, content or independence. Critical failure is non-overridable. All value results preserve the selected FORECAST / ESTIMATED / MEASURED evidence label; an API request to mark a result independently verified is downgraded to measured-pending-evidence. Network value excludes internal sale revenue to avoid counting the same intercompany payment as new network value.

## 5. Persistence and confidentiality boundary

The first module version saves its state through the existing Shoir-IE per-user workspace service only when the user explicitly clicks **Save workspace data**. The UI distinguishes a managed per-user workspace from a local fallback. If an organization-shared workspace context is active, the module refuses the save rather than silently putting its resource records into an unreviewed shared data scope.

This is not proof of authenticated hosted save/re-login recovery for this module. It is also not a cross-company industrial network. No organization-level resource passport or resource exchange row is written to Supabase by this feature slice, and no database migration was added.

## 6. Entitlement and discovery boundary

- Workbench module: `Industrial Resource Intelligence`.
- Minimum tier: `Enterprise`.
- Shared `PLATFORM_CATALOG` and Workbench module matrix registration are present.
- The existing 100-tool registry keeps its stable T001–T100 IDs; this module is not misrepresented as T101.
- Workbench search aliases include: Industrial Resource Intelligence, Industrial Resource Intelligence & Resilience, Industrial Resource Exchange, Industrial Exchange Intelligence Twin, IEIT, Industrial Symbiosis, Resource Efficiency, Resource Recovery, Waste Heat Recovery, Water Reuse, Industrial Resource Optimization, Industrial Resource Resilience, Resource Matching, Industrial Network Optimization and Industrial Cluster Intelligence.
- Explore Modules receives the platform catalogue entry and an Enterprise-disabled launch control; the launch routes into the existing Workbench.
- Renderer-level and UI-level Enterprise checks are present. Existing Starter accounts do not gain access through search or a direct renderer call.

## 7. New tests and exact-head validation

The new test file `tests/test_shoir_resource_intelligence.py` includes coverage for:

- Passport field, provenance, timestamp, bilingual-description and numeric validation.
- Rejection of user-entered `LIVE` provenance; only a separately verified connector may use it.
- Shared Shoir-IE OOXML preflight, package path/expansion checks and bounded workbook upload for Excel import.
- Complete supplier interruption reports full unmet demand with no resource allocation.
- Invalid/non-finite/zero/negative resource quantities.
- Balance reconciliation and unconfirmed suspected-loss classification.
- Over-reconciliation discrepancy detection.
- Resource type/unit mismatch and missing quality data.
- Out-of-window quality and temperature/pressure bounds.
- Treatment evidence remaining user-asserted and not automatically executable by the optimizer.
- Explicit laboratory and engineering review statuses.
- LP solution, objective cost, infeasible shared supply and route quality rejection.
- Supplier disruption shortage and unset recovery time.
- Non-overridable critical safety failure and missing approval references.
- Transfer-neutral network financial value and non-self-certification of independent verification.
- Exchange agreement draft approval-reference states and delivery quantity/quality/certificate evidence checks.
- Passport revision hash-chain creation, continuity verification, tamper detection and refusal to extend a broken chain.
- Downstream dependency graph traversal without causality claims.
- Insufficient-data and time-aware exploratory forecast behavior.
- Historical delivery pass rate without a future probability.
- Prevention-first cascade ordering.
- Unit-consistent capacity bottleneck, preliminary route evidence and production-normalized intensity checks.
- Same-boundary energy reconciliation and waste-heat temperature-approach screening.
- One-contaminant water reuse LP with blended-quality, unit and connection checks.
- Exchange agreement draft approval-reference, delivery quantity, quality and certificate checks.
- Source-row preservation in import validation.
- Workbench IEIT search/launch and Starter-tier denial.
- Explore catalogue and Enterprise policy registration.

**Exact-head CI is the acceptance gate.** The commit checks must complete on the final branch head, not an earlier SHA. A queued or in-progress workflow is not a pass. Hosted authenticated browser acceptance, multi-company access denial, data reload after logout/login, Arabic/RTL and the 1440/768/390 viewport checks remain separate acceptance evidence.

## 8. External evidence still required

To complete the full prompt, the next phase requires real, authorized evidence for: industrial facility/process/equipment models; lab test certificates and quality limits; production and maintenance schedules; treatment residual performance; supplier/demand time profiles; logistics routes and transport cost; physical network/infrastructure design and permits; customer-approved operating constraints; environmental calculation factors and reporting boundaries; legal review of Saudi and target-market obligations; independently reviewed engineering and safety approvals; and a verified organization-scoped confidential data-sharing architecture.

No external participant, live integration, real exchange, achieved resource saving, environmental impact, ROI, certification or regulatory compliance is claimed in this implementation report.

## 9. Release recommendation

**Development/staging feature branch only — PARTIALLY_IMPLEMENTED.** Keep PR #232 in draft, retain BETA, and preserve the existing global **NO-GO** decision. Do not merge to staging, deploy the Edge Function, apply any database migration, deploy Streamlit to production, or modify production data as part of this feature work.
