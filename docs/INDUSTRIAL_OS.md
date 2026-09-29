# Shoir-IE Industrial Engineering Operating System

Shoir-IE now exposes an integrated operating layer around the specialist engineering modules.

## Shared lifecycle

Every module can participate in:

**DATA → VALIDATE → MAP → MODEL → RUN → VISUALIZE → COMPARE → EXPLAIN → DECIDE → EXPORT → VERIFY**

The integration is additive. Specialist calculation engines remain the owners of domain mathematics; the operating layer adds shared project context, provenance, evidence, scenarios, uncertainty, visualization intelligence, verification, and reporting.

## Core objects

- Project
- Dataset
- Digital Thread entity
- Model
- Experiment
- Scenario
- Run / Job
- KPI
- Decision
- Outcome
- Evidence / Reproducibility manifest

## Capability maturity

The operating layer separates:

- Verified
- Implemented
- Foundation
- Integration-ready

Legacy catalogue entries marked Operational are surfaced as Implemented in the maturity view. This is a presentation/governance mapping; it does not claim a live external connector or deployment that has not been configured and verified.

## Decision-grade workflow

The OS surface provides Project Workspace, Scenario Laboratory, Data Intelligence, Problem Solver/Copilot, Visualization Intelligence, Forecast Operations, Digital Thread, Control Tower, Alerts, Decision & Evidence, Experiment/Uncertainty, Verification/Replay, Story/ROI, Presentation/Reports, Run Center, Self-Diagnostics, Capability Maturity, Connector Framework, Formula/KPI Registry, Security/Collaboration, Experience/Localization, and Benchmarking.

## Data and evidence

The layer fingerprints active datasets, records provenance state (LIVE, IMPORTED, SIMULATED, DEMO), persists governed artifacts through the existing enterprise artifact layer, and can generate reproducibility/evidence manifests containing dataset metadata, assumptions, parameters, run context, environment information, and result fingerprints.

## Truthfulness

Unconfigured enterprise integrations remain explicitly integration-ready. Missing operational telemetry is displayed as unavailable rather than fabricated. ROI values are expected to be based on measured baselines and verified outcomes.

## Validation

The feature layer is covered by tests/test_shoir_industrial_os.py and runs inside the repository's normal GitHub Actions regression/validation workflows.