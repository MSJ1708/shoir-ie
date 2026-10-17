# Shoir-IE Module Workspace: Customization and Analysis Guide

## What stays the same

The main navigation and module identities are unchanged. Subscription gates continue to control access to modules. A custom display name is a workspace label only; it does not rename the internal module ID, grant another tier, change a calculation, or alter imported source fields.

The repository currently reconciles 89 distinct module names across its tier menus and catalogue. The Research Pack is a separate package with 85 unique cumulative module entries; its access does not imply Enterprise Plus entitlement.

## Personalize a module

1. Open a module and expand **Personalize this module** in the shared Module Studio.
2. Choose a working name and optionally identify the project, plant/site/department, owner/team, tags and working assumptions.
3. Choose your baseline and scenario labels, a primary numeric KPI, the target rule and tolerance, the summary statistic, its unit and a default chart.
4. Use **Display labels and units** to make table headers readable for your team. These labels affect presentation only; the original column names remain intact for formulas, import mappings and integrations.
5. Save the profile. It is stored per account and per module, and is included in the workspace evidence exports.

A module profile can be configured before importing a dataset. If an input table changes, choices tied to columns that no longer exist are ignored or reset instead of leaving the visualization controls in an invalid state.

## KPI targets

Supported target rules are **At least**, **At most**, and **Near target**. The selected metric can be summarized by mean, median, sum, minimum, maximum or latest value. Tolerance is applied in the KPI's own unit.

A displayed target result means that the selected data table satisfies or does not satisfy the configured rule. It is a calculated comparison—not independent verification of plant performance, cost savings, compliance or a guaranteed business outcome.

## Charts, analysis and exports

The shared visualization studio uses the current available module/workspace tables. Choose a chart and axes that suit the data; the saved preferred chart supplies a default, not a restriction. The workspace can include interactive Plotly charts and table summaries.

For modules with a named module playbook, the playbook shows the intended method, useful input fields and an interpretation guardrail. Run it against the selected result dataset after checking that the columns, units and assumptions match the project. The calculation result is recorded against that dataset's signature; if the inputs change, the UI asks for a new run rather than presenting the old output as current.

Excel and evidence ZIP exports include the profile and, when the source signature still matches, the module-specific analysis table and its metric summary. Keep the source dataset, units, assumption notes and external evidence with the exported bundle when using it in engineering reviews.

## Interpreting the named fallback playbooks

These analyses are intentionally transparent first-pass methods. They help prepare an engineering review but do not replace a module's validated specialist model where one exists.

| Playbook family | What it calculates or checks | Important limit |
|---|---|---|
| Quality | Specification-range checks and defect-rate indicators when the matching fields are supplied | Not a certified capability study; sampling design and assumptions still matter |
| Maintenance | Relative index from available condition indicators in the selected rows | Not a calibrated failure probability, diagnosis or validated predictive model |
| Inventory | Days of cover and an indicative reorder point from on-hand, demand, lead-time and safety-stock inputs | Units and demand/lead-time horizons must align |
| Logistics | Capacity-use percentages and transport-cost estimates from supplied demand/capacity and distance/cost columns | Not a route optimizer, safety validation or live quote |
| Facility | Weighted flow-distance and listed area totals | Not a complete Systematic Layout Planning solution or a measured savings claim |
| Production | Good-unit yield and scrap-rate measures when planned/good/scrap counts exist | Validate the production period and unit definitions |
| Sustainability | Estimated tCO2e from quantities and emission factors, or deltas between supplied baseline and scenario emissions | Quantity units and factor units/boundaries must match; estimates are not audited ESG disclosures |
| Economics | Annual net benefit, simple payback and simple annual return from supplied investment assumptions | Simple payback is not discounted NPV or a guarantee of realized savings |
| Scheduling | Work-content totals and resource load from processing and setup times | Not a constraint-validated finite-capacity schedule |
| Research | Approximate normal confidence intervals for supplied effect estimates and standard errors, or descriptive input summaries | Not a substitute for selecting and running the correct formal test/model |
| Literature and documents | Metadata/record completeness for citation matrices, sections and review fields | Completeness does not validate citations, LaTeX compilation or scientific claims |
| Formalization and proof | Completeness of claims, assumptions and proof/test-status records | A status field is not a machine-checked proof unless a proof backend actually ran successfully |
| Connectivity and integration | Recorded connector status, latency and success-rate summaries | Example or imported rows do not prove a connector is live now |
| Provenance and security | Artifact metadata completeness | A hash field alone is not a verified signature, immutable ledger or zero-knowledge guarantee |
| Optimization and simulation | Input readiness and demand/capacity or scenario screens | Does not imply quantum execution or a completed discrete-event/robust simulation |

## Sample data and operational use

When no compatible project data exists, the generic workspace may start with illustrative sample rows so users can see the expected schema. Replace them with approved, source-dated data before using the result to guide operations. Confirm data completeness, units, baseline definitions, applicable constraints, data permissions and subject-matter assumptions.

Do not describe modelled exposure, sample-data deltas or a readiness score as verified savings. Verify the result with actual post-deployment observations and retain the source references and approval record.

## QA scope

Repository checks exercise Python compilation, regression tests, tier/catalogue consistency, playbook calculations, profile isolation/persistence and result/export wiring. These checks do not prove that every module has been visually tested in an authenticated live Streamlit session. Before workforce rollout, use representative accounts from each tier to open the module, import a real but approved dataset, run the primary action, inspect charts, export and reopen the evidence, and verify persistence and access restrictions.
