# Shoir-IE Resilience Workspaces

The resilience suite adds six specialist workspaces to the industrial platform catalogue:

| Workspace | Tier | Main workflow |
|---|---|---|
| Autonomous Global Supply Chain & Resilient Logistics Network | Enterprise | Editable supplier/demand tables, transportation LP, explicit shortages, route allocation, capacity utilization, risk/carbon weights and Monte Carlo stress testing |
| Zero-Waste Closed-Loop Mega-Factory (Industrial Symbiosis Engine) | Enterprise | Editable material/heat/water streams, recovery-efficiency controls, circularity metrics, residual streams, Sankey and bar charts, and configurable gross-value assumptions |
| Real-Time Urban Mobility & Smart Infrastructure Grid | Enterprise | Synthetic corridor/junction editor, mode share, demand shock, road/transit capacity, delay and emissions proxies |
| Fully Automated Emergency Response & Humanitarian Disaster Logistics System | Enterprise | Relief-depot capacity, prioritized relief demand, response-time and risk weights, visible shortages and uncertainty trials |
| Autonomous Kinetic-Digital Twin (AKDT) for Industrial Logistics Resilience | Enterprise Plus | Synthetic asset telemetry, transparent heuristic health/risk index, edge-buffering scenario, alternate capacity and industrial supply allocation |
| L-SIMS — Local Capability & Dynamic Industrial Readiness Simulator | Enterprise | Aggregated domestic industrial spare-part families, supplier qualification confidence, monthly manufacturing/repair capacity, local-content proxy and part-family capability gaps |

## Shared capabilities

- User-editable data tables and repeatable scenario controls.
- Charts for allocation/flow, utilization, gaps, trends and stress-test distributions.
- CSV and JSON exports, plus owner- and module-scoped saved run snapshots with SHA-256 input hashes.
- Integration with Shoir-IE's module personalization profile, including display alias, project/site/team, KPI target, chart preference, numeric precision and notes.
- Shared subscription gating and catalogue discoverability.
- Clear distinction between model output and verified operational evidence.

## Modeling notes and limitations

The starter datasets are synthetic. The transportation model uses scipy.optimize.linprog with capacity limits, demand-balance equalities and explicit shortage variables. It optimizes a configurable weighted objective based on user-entered direct cost, lead days, risk and carbon-intensity proxies. A shortage remains visible rather than being mislabeled as delivered service.

The closed-loop workspace calculates candidate reuse subject to capture efficiency and demand, with separate heat and water estimates. The urban mobility model uses aggregated corridor data and simple capacity-sensitive proxies. AKDT asset health is a transparent heuristic—not a trained remaining-useful-life model—and its edge/cloud control is conceptual. L-SIMS only compares aggregate domestic manufacturing and repair capability for generic industrial spare-part families.

No new workspace is a live autonomous control system. None is connected by default to ports, carriers, PLCs, live traffic sensors, emergency dispatch, machinery or external telemetry. No modeled savings, service level, circularity, local content or readiness outcome is represented as verified fact. Validate input ownership, data freshness, units, assumptions, feasibility, safety and governance before operational use.

For real deployment, connector setup, access control, data contracts, cybersecurity, human approval, exception handling and integration/field acceptance remain separate engineering deliverables.
