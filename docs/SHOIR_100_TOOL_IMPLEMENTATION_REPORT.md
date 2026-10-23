# Shoir-IE 100-Tool Implementation Report

## Purpose and evidence boundary

This report accompanies `SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv` and the canonical registry `shoir_100_tool_registry.py`. The work was started from the audited `main` baseline commit `3a73ada0be2ea5e85903b9c8937f8a9387ee061d` on an isolated review branch. No production branch, database, account, billing, Edge Function or deployment was changed.

The catalog contains exactly 100 target IDs, T001–T100. The status field describes the source crosswalk and known implementation state; it does not replace route-level or browser evidence. No tool is marked `VERIFIED_WORKING`. All 100 browser checks are `UNVERIFIED` at this stage.

## Current matrix status

| Status | Count |
|---|---:|
| `EXTERNAL_CONFIGURATION_REQUIRED` | 5 |
| `FOUNDATION_ONLY` | 45 |
| `IMPLEMENTED_NEEDS_VALIDATION` | 47 |
| `MISSING` | 3 |
| **Total** | **100** |

Six deterministic quick methods are directly executable inside the existing Core IE Tools screen: T013 Data Quality Profiler, T016 Unit and Currency Converter (currency uses an explicitly supplied rate/source/date), T019 Synthetic Industrial Data Generator, T021 Time Study and Standard Time, T022 Work Sampling Analyzer, and T023 Takt Time and Capacity Calculator. The corresponding functions have golden/validation tests in `tests/test_shoir_100_tool_workbench.py`. These six are **implemented but still need browser/workflow verification**, so they are not marked verified.

The other entries are connected to a related existing workspace only where the source crosswalk provides a route. Selecting “Open related workspace” still goes through the existing shell and subscription policy. A related route is not proof that every specialist acceptance criterion is complete. Foundation-only and missing entries remain visibly identified; `run_tool_calculation` raises `ToolNotImplementedError` rather than fabricating a result for a target without a declared engine.

## Layout and navigation impact

The new library is a collapsible expander inside the existing `Core IE Tools` page. The existing app shell, navigation, current EOQ/OEE tabs, and current route identities are preserved. No 100-item top-level navigation expansion was added. The catalog includes ten workbench groups and a search/filter view.

## Entitlements

Both `shoir_tier_capabilities.tier_allows/available_modules` and `industrial_platform.tier_allows` now use a strict recognized-tier check for authorization. Unmapped module names and unknown/empty tier labels fail closed in `available_modules`; canonical registry execution checks a stable T-ID before dispatch. Existing ordinary tier inheritance is retained. Research Pack inherits through Enterprise and its own features but never grants Enterprise Plus; Enterprise Plus does not grant Research Pack-only capability.

## Verification status

- Registry shape and tier truth-table tests have been added for all 100 IDs across Starter, Mid-Tier Pro, Professional, Enterprise, Enterprise Plus and Research Pack.
- Golden/validation tests cover staged dataset profiling, physical and user-supplied currency conversion, repeatable synthetic data, time-study formula, Wilson work-sampling interval, takt/capacity, and entitlement denial.
- Existing route-specific test suites remain in force. Full hosted authenticated browser matrix, save/reload/re-login, all route-specific specialist golden fixtures and XLSX/PDF/PPTX/ZIP round trips still require execution on the resulting branch/revision.
- Live connector, SSO/MFA, and identity-provider outcomes are not inferred from a catalog or mocked adapter. Configured external endpoints/credentials must be tested in authorized staging before marking their rows connected.
- The GitHub Actions run on the exact final branch HEAD must be recorded after the last code update; this report does not claim a pass before that run finishes.

## Remaining P0 / release decision

**NO-GO for a full 100-tool production claim.** The main source-level framework and six deterministic engines are now in place, and tier fail-open cases have regression tests, but this change does not complete all 100 specialist methods or authenticated browser checks. The next acceptance gate is the branch CI result, followed by the full authenticated module matrix on a disposable tier account set, complete import/export round trips, and focused facility-layout/workbook/persistence checks. Do not merge or deploy on the strength of this report alone.

## Status definitions

- `VERIFIED_WORKING`: automated and applicable authenticated end-to-end checks passed on the named revision.
- `IMPLEMENTED_NEEDS_VALIDATION`: an implementation/helper or closely corresponding route exists, but required validation is incomplete.
- `FOUNDATION_ONLY`: a related workspace or partial foundation exists; the specialist target is not yet proven complete.
- `MISSING`: no adequate specialist route/engine was identified in this crosswalk.
- `EXTERNAL_CONFIGURATION_REQUIRED`: a required authorized endpoint/provider/credential/deployment must be configured and verified.
- `BLOCKED`: work is prevented by a documented external or environment limitation.
