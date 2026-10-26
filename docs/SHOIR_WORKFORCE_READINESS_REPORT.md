# Shoir-IE Workforce Readiness Report

**Report date:** 2026-10-26  
**Repository:** [MSJ1708/shoir-ie](https://github.com/MSJ1708/shoir-ie)  
**Candidate branch:** `feat/shoir-100-t006-recovery-20261026`  
**Current decision:** **NO-GO for production/workforce rollout; continue isolated staging and review.**

## Executive assessment

Shoir-IE has an existing industrial-engineering application shell, reusable engineering modules and a grouped 100-target Workbench. The candidate branch improves tool accounting and adds focused deterministic methods. This evidence does **not** establish that all 100 target capabilities are complete, that all advertised modules pass browser acceptance, or that the product is ready for unsupervised plant decisions.

The user experience remains inside the existing Workbench; this tranche does not add 100 top-level navigation destinations or replace the established application shell.

## Current target status inventory

The canonical `shoir_tool_registry.py` and `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv` are aligned at the time of this report:

| Registry status | Count | Meaning |
|---|---:|---|
| `IMPLEMENTED_NEEDS_VALIDATION` | 91 | A mapped/executable implementation or meaningful foundation exists; complete acceptance is not proven |
| `FOUNDATION_ONLY` | 7 | Foundational work remains before the target should be represented as operational |
| `EXTERNAL_CONFIGURATION_REQUIRED` | 2 | Live configuration/provider setup and testing is required |
| `VERIFIED_WORKING` | 0 | No target has completed all applicable hosted acceptance requirements |
| **Total** | **100** | Stable IDs T001–T100 accounted for |

These are implementation classifications, **not** a 91% operational-success score. Every target still requires acceptance evidence appropriate to its claim.

## Implemented tranche findings

### T006 — Undo, Redo, and Recovery

A bounded JSON snapshot-history method and Workbench flow were added for explicit checkpoint, undo, redo and revision restore. Validation tests cover the basic state transitions, history bounds, non-JSON input, oversize snapshots and invalid revisions. The Workbench AppTest checks the user flow and preservation of the last successful output after a failed checkpoint.

**Scope limitation:** it is not a universal undo manager. It does not automatically intercept other modules' edits or roll back external system side effects. Hosted persistence through save/reload/re-login and cross-workspace isolation are not yet proven.

### T039 — CAPA and 8D Manager

The existing method, gated Workbench form, result table, calculation fixtures and Workbench AppTest were audited and its catalog mapping corrected. It evaluates record completeness, dates, overdue states, evidence references and closed-record evidence.

**Scope limitation:** it is not yet a complete CAPA lifecycle ledger. Durable record CRUD, immutable/versioned status events, auditable approval events, access-controlled attachment storage and two-user isolation remain open.

## Mandatory workforce-readiness gates

A module must not be labelled `PASS` until its evidence record identifies module/tool ID, minimum tier, exact commit and environment; startup/render outcome; useful empty state; a deterministic input fixture and independently expected output; visual evidence for key charts where applicable; save/reload/re-login outcome; authorization and denial outcome; parsed export artifact where offered; and invalid-input/error-recovery behavior.

Required acceptance work remains:

1. **Six-package entitlements:** Starter, Mid-Tier Pro, Professional, Enterprise, Enterprise Plus and Research Pack. Verify positive and negative access at real module, route, direct action, Copilot, API/plugin and export boundaries. Research Pack must not grant Enterprise Plus, and Enterprise Plus must not grant Research Pack-only capabilities.
2. **Workbook to decision:** import a multi-sheet fixture; validate, map and clean; preserve version/lineage; run a deterministic method; compare scenarios; save a decision; produce actual exports; reopen and inspect output content. Invalid imports must preserve prior valid data.
3. **Facility Layout/SLP:** create/edit departments; validate From-To flows and missing data; produce relationship analysis and candidate layouts; recalculate distance/handling costs; compare alternatives; save/reload and export.
4. **Persistence and tenancy:** save, refresh, reload and re-login with separate disposable test users; prove unauthorized reads and writes are denied across workspaces without mutation. Local SQLite fallback is not evidence of hosted durable persistence.
5. **Enterprise integration:** distinguish configured, connected, offline, failed and metadata-only adapters. Test adapter contracts for success, auth failure, timeout, schema mismatch and retry. Mocks are not live integrations.
6. **Exports:** create and reopen supported PDF/XLSX/PPTX/ZIP outputs; inspect structure and content, formulas/charts when claimed, filenames/MIME types, data sources, assumptions and subscription enforcement.
7. **Quality, safety and reliability:** independently check statistical assumptions, reliability inputs and safety/ergonomics limitations. Outputs require qualified human review when appropriate and must not imply regulatory certification.
8. **Interface accessibility:** check compact layouts, keyboard focus, readable statuses and Arabic/RTL behavior where supported.

## Verification state and evidence

The candidate runs these automated workflows: [validation](https://github.com/MSJ1708/shoir-ie/actions/workflows/shoir-validation.yml), [platform tests](https://github.com/MSJ1708/shoir-ie/actions/workflows/platform-tests.yml), [engine regression](https://github.com/MSJ1708/shoir-ie/actions/workflows/engine-regression.yml), [security/quality](https://github.com/MSJ1708/shoir-ie/actions/workflows/security-quality.yml), and [Edge Function verification](https://github.com/MSJ1708/shoir-ie/actions/workflows/edge-function-check.yml).

At the last inspected exact-code revision `bd1de654970e87be5c8ca75e1929350e69dd1e1b`, Engine Regression completed successfully. Platform tests, main validation tests and security/quality were still in progress at that snapshot; the hosted live-deployment-smoke check was skipped on the stacked feature pull request. Subsequent registry/report-only commits advanced the branch head, so **latest-head CI must be inspected again before a merge decision**. This environment did not execute the Python test suite locally and did not perform an authenticated hosted browser walkthrough.

Historical workflows listed in `docs/SHOIR_100_TOOL_IMPLEMENTATION_AUDIT.md` refer to older commits. They must not be represented as proof for the current candidate.

## Risk register

| Risk | Severity | Required mitigation |
|---|---|---|
| No target currently classified as fully verified | Critical for a “100 working tools” claim | Complete authenticated acceptance matrix and attach evidence per target |
| `main` branch protection was reported disabled at baseline | High | Repository owner enables required reviews/status checks and confirms settings |
| Hosted authenticated persistence / cross-workspace isolation unproven | Critical for enterprise/customer data | Test using disposable staging users and deployed RLS/backend configuration |
| Hosted smoke was skipped; earlier public smoke returned sleeping-app page | High for public release | Restore through owner/provider controls and re-run hosted smoke on the exact release SHA |
| T006 only manages snapshots explicitly entered into the tool | Medium/high functional gap | Keep scope clearly labelled; build a transaction-aware application undo contract before making a broader claim |
| T039 lacks a fully auditable lifecycle/attachment store | High for compliance workflows | Add durable CRUD/versioning, server-side approval events, and access-controlled attachment references |
| Two targets need provider/enterprise configuration | High for claims about integrations/identity | Configure only authorized staging endpoints; show `NOT CONNECTED` until tested |
| No final legal/commercial clearance evidenced | High before paid access | Complete Saudi-law legal identity, privacy, terms, calculation disclaimer and marketing claim review separately |

## Workforce release rule

Do not authorize production use for safety-critical, quality-release, maintenance-critical, staffing or investment decisions solely from a generated score or modelled KPI. Identify source data, assumptions, warnings and model status; require accountable engineering/management review; distinguish simulated or estimated value from measured and independently verified outcomes.

**Conclusion: NO-GO for workforce/production rollout.** Continue implementation and isolated staging. A status label or green CI workflow alone is not sufficient to change this decision.
