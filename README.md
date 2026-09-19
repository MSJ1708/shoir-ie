<div align="center">

# ⚡ Shoir-IE

### <strong>Industrial Engineering Command Center & Decision Intelligence Platform</strong>

One connected workspace for industrial engineering, operations research, optimization, simulation, quality, reliability, sustainability, economics, digital-twin foundations, process intelligence, AI-assisted workflows, and executive reporting.

[![CI](https://github.com/MSJ1708/shoir-ie/actions/workflows/shoir-validation.yml/badge.svg)](https://github.com/MSJ1708/shoir-ie/actions/workflows/shoir-validation.yml)
[![Framework](https://img.shields.io/badge/Framework-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Proprietary-111827)](#license)
[![Status](https://img.shields.io/badge/Status-Active%20Development-0F766E)](#project-status)

<strong>Problem → Data → Engineering → Scenario → Decision → Verification → Report</strong>

</div>

---

## 🏭 Why Shoir-IE exists

Industrial engineering is full of mature mathematics, methods, and software.

The problem is often the **workflow around the mathematics**.

A planner may clean data in Excel, test a network in one tool, calculate inventory in another, analyze quality somewhere else, model capital investment in another workbook, prepare charts manually, and then rebuild the entire story in a presentation.

Shoir-IE is built around a different premise:

> **The industrial problem, its data, its engineering method, its scenarios, its evidence, its decision, and its reporting should live in one connected workspace.**

The platform is designed to turn fragmented engineering work into a repeatable decision workflow.

---

# ⚡ The transformation

### Traditional workflow

~~~text
Excel / CSV
    ↓
Manual cleanup
    ↓
Separate engineering tools
    ↓
Manual scenario copies
    ↓
Manual charts
    ↓
Manual report writing
    ↓
Decision
~~~

### Shoir-IE workflow

~~~mermaid
flowchart LR
    A[Industrial Data] --> B[Validation & Cleaning]
    B --> C[Shared Industrial Model]
    C --> D[Engineering Methods]
    D --> E[Optimization / Simulation / Analytics]
    E --> F[Scenario & Sensitivity]
    F --> G[Decision Center]
    G --> H[Verification]
    H --> I[Executive / Technical Export]
    H -. feedback .-> C
~~~

The important innovation is not simply having more calculations.

It is **connecting the work that surrounds the calculations**.

---

# 🚀 What Shoir-IE brings together

| Engineering domain | Representative capabilities |
|---|---|
| Operations Research | MILP, transportation, assignment, facility location, robust optimization, multi-objective optimization |
| Supply Chain | Inventory playback, MEIO, safety-stock workflows, supplier risk, fleet routing, network design |
| Production | PPC, planning, scheduling, lean operations, manufacturing-execution foundations |
| Quality | SPC, capability, Six Sigma, Gage R&R, DOE, ANOVA, FMEA/PFMEA |
| Reliability | Weibull analysis, failure workflows, predictive-maintenance foundations |
| Simulation | Monte Carlo, discrete-event simulation, experiment management, scenario analysis |
| Facilities | Facility layout, warehousing, travel analysis, 3D factory foundations |
| Workforce | Staffing, takt, standard time, balance, ergonomics and human-factors workflows |
| Economics | NPV, IRR, payback, CAPEX/OPEX and sensitivity analysis |
| Sustainability | Carbon accounting, energy, waste, LCA and green-engineering workflows |
| Digital Thread | Products, customers, suppliers, facilities, machines, people, materials, routes and orders |
| Connectivity | Integration foundations, data ingestion and digital-twin connectivity concepts |
| Decision Intelligence | Scenario versioning, comparisons, model health, decision verification and experiments |
| AI | Copilot, module recommendations and agentic workflow foundations |
| Research | Statistics, regression, paper-to-simulation, reproducibility and adversarial review concepts |
| Reporting | Excel workbooks, executive packages, charts and evidence-oriented exports |

---

# 💡 Why this can be a game-changer

The strongest value proposition is not “another industrial engineering calculator.”

It is:

> **A unified environment that reduces the repeated work between industrial engineering tools.**

## 1. Less re-entry

When information is repeatedly copied between workbooks, models, reports and presentations, engineering time is consumed by transfer work.

A shared workflow makes it possible to reuse validated information across downstream analyses.

~~~text
Validated Data
    ├── Inventory
    ├── Production
    ├── Simulation
    ├── Quality
    ├── Economics
    ├── Sustainability
    └── Reporting
~~~

That can reduce duplicate preparation and reduce the opportunity for inconsistent versions of the same number.

## 2. Faster scenario exploration

Industrial decisions are rarely single-answer problems.

They are usually:

- What happens if demand rises?
- What happens if capacity is constrained?
- What happens if a supplier is disrupted?
- What happens if a machine is unavailable?
- What happens if service becomes more important than cost?
- What happens if we invest in automation?

Shoir-IE is designed to make those questions part of the normal engineering workflow.

## 3. Lower analysis overhead

A large amount of engineering effort happens after the core calculation:

**cleaning → formatting → copying → charting → documentation → reporting → review**

Automating and connecting more of that chain creates more time for engineering judgment and improvement work.

## 4. Better traceability

A decision becomes much more useful when the evidence behind it can be traced.

~~~text
Decision
  ↓
Scenario
  ↓
Inputs
  ↓
Method
  ↓
Constraints / Assumptions
  ↓
Result
  ↓
Export
  ↓
Actual Outcome
  ↓
Verification
~~~

That closed loop is central to Shoir-IE.

## 5. System-level cost thinking

Industrial cost is interconnected.

A decision can reduce labor while increasing inventory.

A decision can reduce inventory while increasing transport.

A decision can reduce operating cost while increasing risk.

A decision can increase utilization while increasing quality or maintenance exposure.

Shoir-IE therefore brings together:

<strong>Cost · Service · Capacity · Inventory · Quality · Risk · Workforce · Carbon · Energy</strong>

instead of assuming that one local metric tells the whole story.

---

# 📈 How the value can be measured

Shoir-IE is intended to make efficiency improvements measurable rather than relying on generic marketing percentages.

| Value area | Recommended baseline | Possible post-deployment measurement |
|---|---|---|
| Data preparation | Analyst hours/study | Analyst hours/study |
| Scenario work | Scenarios/month | Scenarios/month |
| Reporting | Hours/report | Hours/report |
| Rework | Corrections/study | Corrections/study |
| Planning | Planning-cycle duration | Planning-cycle duration |
| Inventory | Average inventory and service | Average inventory and service |
| Logistics | Distance / transport cost | Distance / transport cost |
| Quality | FPY / scrap / capability | FPY / scrap / capability |
| Energy | kWh/unit | kWh/unit |
| Carbon | tCO₂e/unit | tCO₂e/unit |
| Decision quality | Predicted vs actual | Prediction error after implementation |

<strong>Important:</strong> actual savings depend on the organization's baseline process, data quality, solver/model complexity, automation coverage, integrations, deployment environment, and adoption. Shoir-IE does not claim a universal savings percentage.

---

# 🧠 Industrial Operating System

The Industrial Operating System is the platform's decision-intelligence layer.

It is designed to turn individual analytical modules into a coherent engineering workflow.

### 📊 KPI Studio
Formula-driven KPI calculation with guarded expression evaluation and target comparison.

### 📚 Engineering Methods Library
Searchable methods, equations, inputs, use cases, and limitations.

### ⚖️ Compare Anything
Compare scenarios and analytical tables using absolute and relative change.

### 🌿 Scenario Git
Preserve scenario versions, lineage, assumptions, and comparison history.

### 🔎 Process Mining
Analyze event logs, variants, transitions, cycle times, and conformance.

### 🧠 Model & Data Health
Monitor feature-distribution drift and surface potential model/data issues.

### ✅ Decision Verification
Compare predicted outcomes with actual outcomes after implementation.

### 🛠️ DMAIC / A3
Translate analysis into structured continuous-improvement work.

### 🧩 Industrial Templates
Start common engineering studies from reusable structures.

### 🩺 Platform Diagnostics
Check runtime, database, and dependency readiness.

The design philosophy is:

> **Results first. Evidence second. Technical internals when needed.**

---

# 🤖 Copilot AI

The Copilot is intended to be the natural-language entry point into the industrial platform.

Instead of requiring users to remember which screen contains which capability, the user can describe the engineering problem.

Examples:

> “Compare these two supply-chain scenarios.”

> “Which engineering method should I use for this study?”

> “Check whether this process is drifting.”

> “Verify the forecast against actual performance.”

> “Prepare the executive output.”

The Copilot's recommendation layer is connected to the platform capability catalogue so new capabilities can be surfaced through natural-language requests.

The design principle is grounded assistance:

- use actual workspace information where available
- identify the appropriate module
- expose assumptions and limitations
- avoid inventing unavailable plant data
- preserve user approval before consequential actions

---

# 🏗️ Architecture

~~~mermaid
flowchart TB
    U[Engineer / Planner / Manager / Researcher] --> UI[Shoir-IE Interface]

    UI --> NAV[Workspace & Module Layer]
    UI --> IOS[Industrial Operating System]
    UI --> COP[Copilot & Recommendations]

    NAV --> MODEL[Industrial Platform Services]
    IOS --> MODEL
    COP --> MODEL

    MODEL --> DATA[Shared Data & Persistence]
    MODEL --> OPT[Optimization]
    MODEL --> SIM[Simulation]
    MODEL --> ML[Analytics / ML]
    MODEL --> QUAL[Quality & Reliability]
    MODEL --> ECO[Engineering Economics]
    MODEL --> SUST[Sustainability]
    MODEL --> CONN[Connectivity Foundations]

    OPT --> DEC[Decision Center]
    SIM --> DEC
    ML --> DEC
    QUAL --> DEC
    ECO --> DEC
    SUST --> DEC
    CONN --> DEC

    DEC --> VER[Verification & Governance]
    VER --> REP[Excel / Executive / Technical Exports]
    VER -. feedback .-> DATA
~~~

---

# 🧩 Capability tiers

The application uses cumulative feature tiers.

| Tier | Focus |
|---|---|
| <strong>Starter</strong> | Core IE, optimization, inventory, facility/warehouse analysis, persistence, data cleaning and validation |
| <strong>Pro</strong> | Supply chain, carbon, IoT foundations, MEIO, fleet, supplier risk, scenarios, PPC, lean, quality, economics and the Industrial Data Model |
| <strong>Professional</strong> | APS, advanced quality/reliability, capital investment, workforce engineering, sustainability/LCA, benchmarking, scenario versioning and localization |
| <strong>Enterprise</strong> | AI Copilot, Monte Carlo, sensitivity, alerts, agentic workflows, control-tower capabilities, predictive maintenance, human factors, digital twins, MES foundations, industrial simulation, 3D factory, connectivity, robust/multi-objective optimization, registry, experiments, decision center and executive reporting |
| <strong>Enterprise Plus</strong> | Industrial Data Platform, Advanced Engineering Copilot, live-digital-twin capabilities, enterprise security/governance and predictive-maintenance digital-twin capabilities |
| <strong>Research Pack</strong> | Statistical analysis, research authoring, paper-to-simulation, reproducibility, formalization, adversarial review and advanced research experimentation |

The application currently contains a broad cumulative feature catalogue; availability depends on the user's configured tier.

---

# 🔬 Research & advanced engineering

Shoir-IE extends beyond day-to-day IE workflows into research-oriented engineering.

The research chain is designed around:

~~~text
Research Question
      ↓
Model
      ↓
Data
      ↓
Experiment
      ↓
Analysis
      ↓
Stress Test
      ↓
Reproducibility
      ↓
Publication
~~~

Representative capabilities include:

- statistical hypothesis testing
- advanced regression
- literature/citation support
- paper-to-simulation workflows
- theory-to-code formalization
- adversarial review concepts
- reproducible research workflows
- formal-verification concepts
- synthetic industrial twins
- advanced optimization-routing concepts

These capabilities are intended to support inspection, stress testing and reproducibility rather than simply generating presentation output.

---

# 📊 Results-first experience

Shoir-IE is being shaped around a consistent presentation rule:

~~~text
Engineering Result
       ↓
KPI / Chart
       ↓
Readable Table
       ↓
Interpretation
       ↓
Assumptions
       ↓
Download
       ↓
Technical Details
~~~

The goal is that a normal user sees the engineering result first.

Advanced users can still access the mathematics, diagnostics, generated source, assumptions, and other technical material when needed.

---

# 📤 Exports

The platform includes export-oriented workflows so analysis can leave the application as a reusable business artifact.

Representative outputs include:

- formatted Excel workbooks
- multi-sheet executive packages
- charts embedded in supported workbooks
- scenario comparison tables
- quality/reliability outputs
- simulation outputs
- decision verification records
- technical evidence tables

The objective is to prevent a common failure mode:

> analysis is completed successfully, but the engineer still has to spend another hour rebuilding the result for the manager.

---

# ✅ Quality assurance

Shoir-IE includes automated GitHub Actions validation.

The current validation chain includes:

~~~text
Dependency installation
        ↓
Full Python-tree compilation
        ↓
Complete pytest suite
        ↓
Application-module parsing
        ↓
Module-surface regression checks
        ↓
Real Streamlit application startup test
~~~

The repository's latest validated main release completed the validation workflow successfully.

The test suite covers core areas including:

- Industrial Platform services
- Platform Excellence services
- Industrial Operating System services
- Excel/data-cleaning workflows
- application smoke checks
- module wiring
- Streamlit startup behavior

This is intentionally stronger than checking that individual Python files merely compile.

---

# 🧪 Validation philosophy

A production-oriented engineering platform should fail loudly during development and explain issues cleanly to users.

Shoir-IE therefore emphasizes:

**Input validation**

Check missing fields, invalid ranges, malformed structures, and unsuitable data before analysis.

**Model validation**

Surface feasibility, assumptions, uncertainty, stability, and reproducibility concerns.

**Result validation**

Make the result explicit instead of returning opaque solver or pandas errors.

**Decision verification**

Compare predictions to actual outcomes after implementation.

**Regression protection**

Add tests when a production defect is discovered.

---

# 🔐 Security & governance

The application contains security and governance mechanisms including:

- salted password hashing
- database-backed login-attempt controls
- role/tier-gated functionality
- audit-trail infrastructure
- secret-based configuration for supported integrations
- structured workspace persistence
- guarded formula evaluation
- scenario lineage/versioning
- decision-verification persistence
- platform diagnostics

For public or enterprise deployment, additional environment-specific hardening should be configured, including hosted database persistence, secret rotation, backups, access controls, monitoring, network policy, and connector security.

---

# 🛠️ Getting started

## Requirements

- Python 3.10+
- pip
- a supported Streamlit environment

## Install

~~~bash
git clone https://github.com/MSJ1708/shoir-ie.git
cd shoir-ie
python -m pip install -r requirements.txt
~~~

## Run

~~~bash
streamlit run app.py
~~~

## Configuration

Deployment secrets should be supplied through Streamlit secrets or the deployment environment.

Example structure:

~~~toml
[email]
sender_email = "your-notification-email"
app_password = "your-app-password"

[admin]
password = "your-strong-admin-password"

[anthropic]
api_key = "your-api-key"
~~~

Do not commit real passwords, API keys, payment credentials, or other secrets to the repository.

---

# 📁 Repository structure

~~~text
shoir-ie/
│
├── app.py
├── industrial_platform.py
├── industrial_platform_excellence.py
├── industrial_operating_system.py
├── shoir_upgrade.py
│
├── aegis_opt.py
├── aegis_sim.py
├── enterprise_engine.py
├── database.py
│
├── pages/
│   ├── Industrial_Engineering_Workbench.py
│   └── Industrial_Platform_Command_Center.py
│
├── tests/
│   ├── test_application_smoke.py
│   ├── test_industrial_operating_system.py
│   ├── test_industrial_platform.py
│   ├── test_platform_excellence.py
│   └── test_shoir_upgrade.py
│
├── docs/
│   └── images/
│
└── .github/
    └── workflows/
~~~

---

# 🏆 Competition & presentation story

A compelling Shoir-IE demonstration should show **one problem moving through the entire platform**.

### Example challenge

**Demand is rising, supply is constrained, and management wants a defensible decision.**

### Demonstration

**1. Load the data**  
Import the operational dataset.

**2. Validate it**  
Show data-quality and assumption checks.

**3. Build the engineering model**  
Use the shared industrial representation.

**4. Optimize**  
Run the relevant planning, network, inventory, routing, or production engine.

**5. Stress-test**  
Introduce demand, capacity, lead-time, or supplier uncertainty.

**6. Compare scenarios**  
Show how cost, service, capacity, risk, and sustainability change.

**7. Explain**  
Show the drivers, assumptions, limitations, and evidence.

**8. Verify**  
Record the decision and later compare predicted versus actual performance.

**9. Export**  
Produce an executive-ready package.

This makes the platform demonstrable as an end-to-end engineering system rather than a collection of disconnected screens.

---

# 🌍 Long-term vision

Shoir-IE is designed to evolve toward a continuously learning industrial decision loop:

~~~text
DATA
  ↓
DIGITAL THREAD
  ↓
ENGINEERING METHODS
  ↓
OPTIMIZATION + SIMULATION + AI
  ↓
DECISION
  ↓
EXECUTION
  ↓
MEASUREMENT
  ↓
VERIFICATION
  ↓
LEARNING
  ↺
~~~

The long-term opportunity is a platform where the system can help users not only answer:

<strong>“What should we do?”</strong>

but also:

<strong>“Why does the model say that?”</strong>

<strong>“What happens under uncertainty?”</strong>

<strong>“What did we actually implement?”</strong>

<strong>“Did reality match the prediction?”</strong>

That feedback loop is the heart of Shoir-IE's industrial decision-intelligence vision.

---

# 🗺️ Roadmap

The highest-priority next steps are focused on depth, reliability and real-world deployment:

- [ ] Broader end-to-end browser interaction testing
- [ ] Deeper cross-module digital-thread propagation
- [ ] Hosted PostgreSQL persistence for production deployments
- [ ] More extensive ERP/MES/SCADA connector testing
- [ ] Stronger APS ↔ MES ↔ Quality feedback loops
- [ ] Deeper digital-twin calibration and live-data synchronization
- [ ] Expanded model registry and experiment lineage
- [ ] More comprehensive executive reporting
- [ ] Guided onboarding and study templates
- [ ] Production observability and deployment hardening
- [ ] Larger real-world benchmark and case-study library

---

# 📜 License

<strong>Proprietary — © 2026 Shoir-IE. All rights reserved.</strong>

See [LICENSE](LICENSE).

---

# 📬 Contact

<strong>Shoir-IE</strong><br>
Email: <strong>shoirtheagent@gmail.com</strong>

---

<div align="center">

### ⚡ Shoir-IE

<strong>From fragmented industrial analysis to connected engineering decisions.</strong>

</div>
