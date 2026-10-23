# Shoir-IE 100-Tool Implementation Audit — Phase 1

**Reviewed source baseline:** `3a73ada0be2ea5e85903b9c8937f8a9387ee061d` (main, 2026-10-21)  
**Implementation branch:** `audit/shoir-100-tools-20261023`  
**Purpose:** establish a conservative 100-target crosswalk and enforceable stable-ID/tier contract while preserving the existing shell and workbench.

## What this audit establishes

The existing repository has meaningful reusable engines and surfaces: the central `shoir_tier_capabilities.py` policy, `industrial_platform.py`, `industrial_platform_excellence.py`, the Excel runtime/studio, the Industrial Engineering Workbench, the dedicated facility-layout renderer, capacity-recovery calculations, workbook formulas, workspace persistence, and enterprise connector/decision services. These are reused as candidate mappings; the 100-tool catalog is not treated as proof that all 100 target acceptance criteria are already satisfied.

The source audit uses the required status vocabulary. `VERIFIED_WORKING` is intentionally not assigned solely from source inspection. Existing route mappings are `IMPLEMENTED_NEEDS_VALIDATION` only where a concrete related renderer or deterministic method is visible; generalized workflow/playbook surfaces remain `FOUNDATION_ONLY`. `MISSING` means no adequate specialist source was identified in the targeted search for that capability. External configuration statuses do not imply an active live connection.

## Baseline status counts

- `EXTERNAL_CONFIGURATION_REQUIRED`: **2**
- `FOUNDATION_ONLY`: **51**
- `IMPLEMENTED_NEEDS_VALIDATION`: **47**
- `MISSING`: **0**

These are static-source classifications, **not** authenticated-browser passes and not a workforce-readiness score. All 100 browser statuses remain `UNVERIFIED` in the matrix; no rows are labelled `VERIFIED_WORKING` from source presence alone.

## Layout and module integration rule

Do not add 100 top-level navigation items. Keep existing Home, Workbench, Data, Analyze, Simulate, Optimize, Operations, Decisions, Research and Knowledge navigation. The target directory is a collapsed discovery panel inside the existing Workbench, with grouped workbenches, search/filtering, minimum tier and readiness. A tool is launchable only through an actual mapped runtime route; this directory must never turn a foundation-only target into an executable tool or bypass that route's native authorization.

## Tier rule

The registry delegates target decisions to `shoir_tier_capabilities.tier_allows`. The five ordinary plans are cumulative in order. `Research Pack` is a separate add-on: it inherits through Enterprise and Research Pack-only features, never Enterprise Plus. Enterprise Plus never grants Research Pack-only access. Unknown target IDs fail closed. The target registry check is not yet a substitute for execution-time wiring in each legacy module/action/export path; that work remains explicitly tracked rather than claimed completed.

## P0 and implementation gaps

1. Bind each target ID to the real renderer/action; make unmapped targets visibly non-executable and ensure runtime execution, Copilot, direct routes, APIs and exports check the central policy.
2. Close the known workbook, facility-layout, export, persistence/recovery, integration diagnostic and authenticated tier gates with dedicated staging accounts.
3. Three initially missing targets now have bounded deterministic engines and focused fixtures: T066 cutting/bin packing, T075 forecast error threshold monitoring, and T085 sample size for a specific two-sample t-test. Broader specialist fixtures are still required; validate units, invalid/boundary inputs and solver states.
4. Complete all 100 authenticated browser walkthroughs, including empty/malformed data, save/reload/re-login, export parsing, direct-route denial and narrow/RTL views.
5. Add CI gates for manifest completeness, tier drift, route/render mapping, calculation fixtures, exports and the browser matrix.

## Verification limits

Three focused methods have now been added in `shoir_target_engines.py`; this does not mean they are yet wired into the Workbench action flow. The code-writing environment could inspect and edit the connected GitHub repository but could not clone it locally from this execution environment. The repository's checked-in GitHub Actions workflow is therefore the source of executable test evidence for this branch; the hosted Streamlit app cannot be considered authenticated-browser-verified without authorized disposable test accounts and the matching secrets-backed workflow. Do not deploy or merge based on this phase report alone.
