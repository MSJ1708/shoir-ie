<div align="center">

# ⚡ Shoir-IE

### Deep-Tech Industrial Engineering & Operations Research Platform

**52 modules · 4 tiers · manual-verified subscriptions · a dedicated Research Pack for academic work**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-Proprietary-8b5cf6?style=flat-square)](#license)
[![Status](https://img.shields.io/badge/Status-Active%20Development-2dd4bf?style=flat-square)](#roadmap)

[Overview](#overview) · [Screenshots](#screenshots) · [Modules & Tiers](#modules--tiers) · [Research Pack](#research-pack) · [Architecture](#architecture) · [Security](#security) · [Getting Started](#getting-started) · [Roadmap](#roadmap)

</div>

---

## Overview

Shoir-IE is a single, connected workspace for industrial engineering and operations-research work — network and inventory optimization, facility layout, quality and reliability, simulation, and a dedicated **Research Pack** for people who need to defend their results to a reviewer, not just present them to a manager.

The problem it solves: IE and OR work is usually scattered across a spreadsheet for EOQ, a separate app for routing, a Six Sigma add-in, a capex spreadsheet, and a stats package for the paper — with nothing connected and nothing reproducible. Shoir-IE puts all of it behind one login, working off one shared, always-current dataset.

| | |
|---|---|
| 🏭 **For operations teams** | Network design, inventory, routing, quality, and production planning in one workspace |
| 🎓 **For researchers** | A Research Pack purpose-built for reproducibility, adversarial peer review, and paper-to-simulation workflows |
| 🔐 **Manually verified accounts** | Every subscription is reviewed by an administrator against real payment proof before activation — no account is ever auto-created |
| 🇸🇦 **Built for the region** | STC Pay integration and Saudi PDPL / E-Commerce Law–aware policies from day one |

---

## Screenshots

> Add real screenshots here before publishing — placeholders below show where they go. A short GIF of the "Explore the Modules" tab, the dashboard, and the Admin Panel review screen make the strongest first impression.

<div align="center">

| Landing & Registration | Dashboard | Admin Review |
|:---:|:---:|:---:|
| `docs/images/landing.png` | `docs/images/dashboard.png` | `docs/images/admin-panel.png` |

</div>

```markdown
![Landing page](docs/images/landing.png)
![Dashboard](docs/images/dashboard.png)
![Admin review screen](docs/images/admin-panel.png)
```

---

## Modules & Tiers

Every tier is **cumulative** — Mid-Tier Pro includes everything in Starter, Enterprise includes everything in Mid-Tier Pro, and so on.

<div align="center">
<img src="docs/images/module_tier_chart.png" alt="Cumulative modules by tier: Starter 7, Mid-Tier Pro 21, Enterprise 33, Research Pack 52" width="720">
</div>

| Tier | Price | Adds | Total modules | Built for |
|---|---|---|---|---|
| **Starter** | $29 | 7 core modules | 7 | Individual analysts replacing spreadsheet-based decisions with solved, optimal answers |
| **Mid-Tier Pro** | $79 | +14 modules | 21 | Teams running day-to-day operations — routing, scheduling, quality, finance |
| **Enterprise** | $199 | +12 modules | 33 | Organizations that need automation, simulation-under-uncertainty, and a natural-language copilot |
| **Research Pack** | +$30 add-on | +19 modules | 52 | Researchers who need reproducibility, adversarial review, and a paper-to-simulation pipeline |

Full documentation for all 52 modules — what each one does, when to use it, and a worked example — is built directly into the app: open the login page and click the **🧭 Explore the Modules** tab. It's not marketing copy; every example maps to a real, running feature.

**A sample of what's inside:**

- **MILP Solvers** — exact optimal warehouse-and-customer network design in seconds, not a week of spreadsheet trial-and-error
- **Monte Carlo Sim** — 10,000-scenario demand simulation instead of one misleadingly-precise point estimate
- **Human Factors & Ergonomics (NIOSH)** — real NIOSH lifting-equation scoring for manual material handling tasks
- **AI Copilot** — ask in plain language ("optimize the network", "check my tier") and get an answer grounded in your real workspace data, not a canned script

---

## Research Pack

The Research Pack is Shoir-IE's sharpest differentiator: a genuinely research-grade layer most industrial-engineering software doesn't attempt — statistics, reproducibility, adversarial review, and a full paper-to-simulation pipeline.

<div align="center">
<img src="docs/images/research_pack_chart.png" alt="Research Pack's 19 modules broken down by category: Advanced Computation Infrastructure 7, Research Authoring 5, Paper-to-Simulation Pipeline 4, Peer Review and Stress-Testing 3" width="640">
</div>

**Why it exists:** there's a real gap between "I have a model" and "I have a submittable, defensible, reproducible result." The Research Pack is built to close exactly that gap:

- **Statistical Hypothesis Testing** → run a proper t-test/ANOVA/chi-square with real statistics, ready to cite, instead of a claimed result
- **Paper-to-Simulation Auto-Engine** → point it at a published model and get a runnable simulation of it, turning a week of re-implementation into a starting point
- **Adversarial AI Peer-Review Swarm** → get your methodology critiqued before a real reviewer does, catching weak claims before submission instead of after rejection
- **Decentralized Cryptographic Reproducibility Vault** → cryptographically prove your published results came from the exact code and data you say they did, months or years later

---

## Architecture

### Registration → Verification → Access

Every account is manually verified against real payment proof before activation — the platform never auto-creates a paid account.

```mermaid
flowchart TD
    A[User registers<br/>picks a tier, submits payment proof] --> B[Request queued<br/>waits for admin review]
    B --> C{Admin reviews<br/>verifies proof in Admin Panel}
    C -->|Approve| D[Account created<br/>at the purchased tier]
    C -->|Decline| E[Request closed<br/>no account, logged]
    D --> F[User signs in<br/>modules unlocked for that tier]
```

### System overview

```mermaid
flowchart LR
    UI[Streamlit UI<br/>52 modules] --> Auth[Auth & Session State<br/>salted PBKDF2 hashing]
    Auth --> DB[(SQLite<br/>enterprise_full_workspace.db)]
    UI --> Solvers[Optimization Engines<br/>PuLP · SciPy · NumPy]
    UI --> Maps[Geospatial Layer<br/>Folium · Plotly]
    UI --> Copilot[AI Copilot]
    Copilot -. optional .-> LLM[Anthropic Claude API]
```

---

## Security

- **Salted, hashed passwords** — PBKDF2-HMAC-SHA256, 200,000 iterations. Nothing is ever stored in plain text, including the admin account.
- **Database-backed login rate limiting** — 5 failed attempts locks a username out for 10 minutes; can't be bypassed by opening a new tab.
- **Input validation at the point of entry** — usernames and emails are format-checked at registration, closing a stored-XSS gap at the source rather than patching every place a name is later displayed.
- **Secrets kept out of source** — admin credentials and email/API keys read from `st.secrets`, never hardcoded.
- **Full audit trail** — every admin action (approve, decline, manual code generation) is logged with a timestamp and actor.
- **Role-gated admin panel** — the pending-request review screen, user list, and audit log are reachable only by the authenticated admin account, nowhere else in the app.

## Compliance

Privacy Policy, Terms & Conditions, Cookie Policy, and Refund Policy are built directly into the registration flow, with a real consent checkbox — not an afterthought page nobody reads. Drafted specifically around what this app actually collects (reviewed against Saudi PDPL and E-Commerce Law considerations, given STC Pay as the payment method).

---

## Getting Started

### Prerequisites
- Python 3.10+
- pip

### Installation

```bash
git clone <your-repo-url>
cd shoir-ie
pip install -r requirements.txt
```

### Configuration

Create `.streamlit/secrets.toml`:

```toml
[email]
sender_email = "your-notification-email@gmail.com"
app_password = "your-app-password"

[admin]
password = "set-a-strong-admin-password-here"

# Optional — connects the AI Copilot to a real language model.
# Without this, the Copilot still works using real workspace data,
# just without open-ended natural-language reasoning.
[anthropic]
api_key = "your-anthropic-api-key"
```

### Run

```bash
streamlit run app.py
```

Sign in with the admin account configured above to reach the Admin Panel and start approving registrations.

> ⚠️ **Before deploying publicly:** this app currently stores its database and uploaded payment proofs on local disk. Streamlit Community Cloud does not guarantee persistence of local files — a redeploy or restart can wipe all accounts, including the admin account. Migrate to a hosted database (e.g. Supabase or Neon Postgres) before relying on a public deployment.

---

## Tech Stack

| Layer | Technology |
|---|---|
| App framework | Streamlit |
| Optimization | PuLP (MILP), SciPy, NumPy |
| Data | Pandas, SQLite |
| Visualization | Plotly, Folium |
| AI Copilot | Rule-based by default; optional Anthropic Claude API |
| Auth | Salted PBKDF2 password hashing, database-backed rate limiting |

---

## Roadmap

Honest, in priority order:

- [ ] **Migrate off local SQLite** to a hosted Postgres database — required before any public deployment
- [ ] **Public demo / auto-approved trial tier** — so evaluators can try the platform without waiting on manual approval
- [ ] Guided first-run onboarding for new accounts
- [ ] Consistent CSV/PDF export with charts across all 52 modules
- [ ] Automated test coverage and CI
- [ ] Modularize the codebase out of a single file

---

## License

Proprietary — © 2026 Shoir-IE. All rights reserved.

## Contact

**shoirtheagent@gmail.com**
