# Shoir-IE 100-Tool Implementation Matrix — Evidence Report

**Prepared:** 2026-10-23  
**Baseline audited:** `main` at `3a73ada0be2ea5e85903b9c8937f8a9387ee061d`  
**Implementation branch:** `feat/100-tool-library-20261023` (changes not merged or deployed by this report)

## Purpose and confidence

This report accompanies `SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`. It uses the six exact statuses required by the master prompt. A mapped route or catalog entry is not treated as proof that the target specialist method works. No target is marked `VERIFIED_WORKING`: the authenticated 100-tool browser matrix, persistence/re-login tests, and full import-analysis-scenario-export journeys have not run for this revision.

## Status definitions

- `VERIFIED_WORKING`: all applicable automated and authenticated end-to-end acceptance checks passed on the exact tested revision.
- `IMPLEMENTED_NEEDS_VALIDATION`: real deterministic implementation or a relevant existing engine is present, but mandatory end-to-end evidence is incomplete.
- `FOUNDATION_ONLY`: a related route, generic platform foundation, partial method, or broad proxy exists; promised specialist behavior is not complete/proven.
- `MISSING`: no adequate dedicated implementation was identified in the current pass.
- `EXTERNAL_CONFIGURATION_REQUIRED`: code or a related route exists, but authorized endpoints/credentials/deployment/live checks are required.
- `BLOCKED`: validation is stopped by a documented environment limitation.

## What is being added in this changeset

The new single-entry **Engineering Tool Library** is designed to fit inside the existing module shell rather than adding 100 navigation items. It groups capability cards by the ten workbenches from the prompt and uses stable IDs T001–T100. The new workbench adds executable deterministic paths for T011, T013, T014, T016, T019, T021, T022, T023, T026, T032, T042, T055, T072, T078, and T081. Those actions are still `IMPLEMENTED_NEEDS_VALIDATION` until CI and authenticated acceptance checks are reviewed.

The current library keeps the prior imported dataset in session state when a new upload is malformed, provides a cleaning preview with in-session undo, labels generated datasets as synthetic, and shows formula/method/assumption details beside numeric outputs. This additive workflow does not replace the existing workbook or specialized module implementations.

## Current gap classification

- **Reusable existing capability:** existing module routes are cross-referenced in the CSV (including Excel import/workbook, existing search/project/persistence, IE/quality, MILP/facility, planning/inventory/routing, simulation, research, export, and enterprise routes).
- **New deterministic behavior in this change:** 15 explicit tool IDs listed above; source code and golden tests are included, but end-to-end proof remains pending.
- **Foundation/partial targets:** marked `FOUNDATION_ONLY`; related names or broad platform areas exist, but the target acceptance behavior needs a specialist implementation or evidence.
- **Missing targets:** a small set of targets without an adequate route/engine is marked `MISSING` instead of being shown as usable.
- **External configuration:** integration/identity capabilities that cannot honestly be proven without authorized non-production configuration are marked `EXTERNAL_CONFIGURATION_REQUIRED`.

## Entitlement model

Minimum tiers are taken from the prompt's target table. Each tool has a stable ID independent of display text. `tool_access_allowed()` fails closed for unknown IDs and delegates the Research Pack/ordinary-tier inheritance rule to the existing shared tier policy. The product's existing tier model remains unchanged: Research Pack inherits through Enterprise plus Research Pack tools, but not Enterprise Plus; Enterprise Plus does not itself grant Research Pack-only tools. Existing legacy-route enforcement remains an independent path and requires the existing matrix tests plus the new 100-ID truth-table tests.

## Verification still required before release

1. Review the pull-request CI results on this exact branch/commit.
2. Run the authenticated browser matrix for each tool and tier, including direct routes/actions and denied routes.
3. Execute five end-to-end workflows from the master prompt with disposable fixtures/accounts.
4. Reopen/parse XLSX, PDF, PPTX, and ZIP outputs from existing export paths.
5. Run the staging integration/access gate only after authorized test credentials and matching schema/Edge Function are available.
6. Recompute the matrix evidence column after each verified test run; change a status to `VERIFIED_WORKING` only when the definition above is met.

**Release recommendation: NO-GO for a production/paid launch until the outstanding gates pass.** This changeset is a focused implementation increment, not a claim that all 100 specialist targets are complete.
