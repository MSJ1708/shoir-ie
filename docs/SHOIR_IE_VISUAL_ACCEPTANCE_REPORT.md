# Shoir-IE Visual Acceptance Report

Assessment date: 2026-11-20. Status: **local public-entry viewport smoke is implemented; full authenticated visual acceptance remains NOT ACCEPTED / NOT VERIFIED**.

## What repository CI can verify

The full validation workflow contains a local Streamlit + Chromium/Playwright smoke run. It starts the exact checked-out application locally with no account credentials and checks three viewport sizes:

| Viewport | Size |
|---|---:|
| Desktop | 1440 × 1000 |
| Tablet | 768 × 1024 |
| Mobile | 390 × 844 |

At each viewport it waits for stable application readiness, detects known startup/runtime error markers, records uncaught browser and console errors, checks horizontal overflow, and exercises the public sign-in, subscription/registration and module-explorer tabs. It captures screenshots of those public surfaces and a deeper module-explorer section. The generated `shoir-ie-local-runtime-smoke` artifact contains the public-entry screenshots and redacted JSON results when that stage completes.

The validation workflow separately generates synthetic PDF/PPTX evidence, renders each PowerPoint slide to PDF/PNG, and uploads report-export artifacts. These are file-generation/rendering checks, not proof that every authenticated report in every module is visually correct.

The feature-PR `live-deployment-smoke` job is skipped by its workflow event/branch condition. That does not invalidate the local smoke test, but it is not a hosted staging test. The local smoke test intentionally does not sign in, register accounts, submit forms or mutate production data.

## What is not yet evidenced

The complete authenticated 25-screen inventory has not been inspected across the three viewports. In particular, the following remain staging acceptance tasks:

- Arabic/RTL layouts, navigation, field alignment and bidirectional text at all three viewport sizes.
- Authenticated shell, Workbench tabs, Inspector, Industrial Control Center and each major module's empty, error and populated states.
- Team Workspaces and all role/tier variants, including suspended/removed users and cross-organization denial.
- Dataset catalogue/history, upload progress, lease conflicts, Digital Thread graph and relationship details.
- Copilot approval gates, KPI alert tables, subscription/account states, Security/Trust Center and Executive Report Center.
- Every critical Plotly figure's labels, units, axes, legends, hover text, accessibility and clipping.
- Authenticated XLSX/PDF/PPTX export, actual browser downloads, open/reopen and content correctness.

## Required staging visual acceptance

1. Confirm staging banner and exact deployed candidate SHA before entering any test credentials.
2. Use only the dedicated disposable `shoir-e2e-*` accounts; never use `sho`, production identities or customer data.
3. Capture screenshots and browser traces for the authenticated 25-screen inventory at 1440px, 768px and 390px, including Arabic/RTL where supported.
4. Inspect every critical chart, table, modal, drawer, tab, form and download; verify keyboard focus, readable labels, units, empty/error states and no clipping/overflow.
5. Exercise the full import → validate → model → run → visualize → compare → explain → decide → export → reopen/verify workflow.
6. Attach redacted screenshots, traces, viewport metadata, the exact source SHA and defect fixes to the staging acceptance evidence.
7. Obtain independent product, engineering and accessibility/visual review. Preserve the existing Shoir-IE design and navigation.

A screenshot file existing is not proof that the screen is correct. Do not mark the visual gate passed until the complete authenticated evidence bundle has been reviewed on the exact staging candidate.
