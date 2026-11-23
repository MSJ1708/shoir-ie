# Workflow Automation Agent — Staging Assurance

This integration adds a staging-only, read-only evidence run.

## Target and controls

- Repository: `MSJ1708/shoir-ie`
- Branch: `staging-e2e-20261019`
- Trigger: push to that branch or manual dispatch while that branch is selected
- GitHub permissions: Contents, Actions and Pull Requests read-only
- Agent checkout token: separate fine-grained read-only secret `WORKFLOW_AGENT_READ_TOKEN`
- Evidence: JSON artifacts retained for 14 days

The job cannot write to the Shoir-IE repository, merge a pull request, deploy Streamlit, change branch rules, write to Supabase, access production secrets or run migrations.

## One-time secret setup

Create a fine-grained GitHub token for `MSJ1708/shoir-release-assurance-agent` only. Grant Metadata read and Contents read. Add it to Shoir-IE repository Actions secrets as `WORKFLOW_AGENT_READ_TOKEN`. Do not put the token in code, workflow text, issues or chat.

## Running it

Push the integration PR to `staging-e2e-20261019` only after review/approval requirements are satisfied. Then open Actions → Workflow Agent Staging Assurance and inspect the uploaded evidence artifact.

This first stage verifies the private agent can load, start and read Shoir-IE's staging repository/Actions metadata. It is not a 96-module functional E2E, RBAC acceptance, backup/restore rehearsal, OIDC/MFA verification or production release approval. Shoir-IE remains BETA / production NO-GO until those gates have independent evidence.
