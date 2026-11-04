# Shoir-IE External Dependency Register

**Snapshot:** 2026-11-04  
**Rule:** a configuration item is complete only after an actual authorised test and retained evidence.

| Dependency | Needed for | Current evidence | Exact next action |
|---|---|---|---|
| Dedicated staging Streamlit app | Authenticated hosted release gate | `staging_app.py` exists; hosted target hostname not verified | Staging app owner confirms exact URL/hostname, branch deployment and staging banner. |
| Staging Streamlit secrets | Safe app-to-staging Edge connection | Source guard requires staging environment, Edge URL and publishable key; secret values were not read | Confirm secret names and exact staging project target inside Streamlit staging settings; never send secret values in chat or commit them. |
| GitHub Actions staging E2E secrets | Backend/browser acceptance | Workflow requires dedicated URLs, publishable key and seven disposable account credential pairs | Repository administrator configures only `shoir-e2e-*` test identities and expected staging host/variables according to `AUTHENTICATED_RELEASE_GATE.md`. |
| OIDC identity provider / MFA | Enterprise Identity and Audit (T098) | Provider setup is classified EXTERNAL_CONFIGURATION_REQUIRED | Customer/security owner supplies approved issuer, client, redirect URLs, signing/claim policy and a staging test tenant; complete login, revocation and audit tests. |
| SAP / Oracle / ERP endpoints | Real connector operation (T096) | Connector architecture/source exists; no customer endpoint or successful customer connection proven here | Obtain written customer authorisation, endpoint, least-privilege read-only credential, network/TLS allowlist, sample data and staging acceptance. |
| Microsoft Excel host deployment | Genuine Office add-in | Manifest and taskpane/planner source exist; manifest placeholders remain and Office desktop/web host tests are absent | Configure verified HTTPS static host and icon assets, replace placeholders, sideload/test supported Office hosts, validate auth and permissions. |
| Excel-to-Shoir-IE transfer | Upload workbook from Office task pane | Current add-in planner is local-only; no authenticated workbook-transfer API or Excel-scoped token flow is established | Design a separate short-lived, revocable Excel-scoped token and consented, audited, tenant-bound upload API before enabling transfer. Never reuse the broad browser workspace token. |
| Customer industrial data feeds | Real monitoring/twin levels | Internal connector/monitoring foundations exist; no live data feed is established | Customer configures approved read-only source, network permissions, schema mapping, freshness limits and fail/restore tests. |
| Legal and privacy review | Saudi/customer commercial readiness | Terms, privacy, refund and legal risk documents exist; review clearance remains open | Obtain accurate operator/business identity, hosting/subprocessor/data-location map, retention/deletion/incident processes and qualified Saudi legal review. |
| Backup and restore | Operational readiness | Backup settings and successful restore evidence were not established in this review | Authorised operator supplies backup configuration and conducts isolated restore rehearsal with measured RPO/RTO. |
| Branch protection verification | Controlled release | GitHub reports main and staging branches protected; required-check configuration was not established here | Repository administrator verifies required status checks, strictness, bypass/admin enforcement and dismissal rules. |

Do not mistake a connector adapter, manifest, endpoint field or configuration screen for a successful external integration. Mark each connection NOT CONNECTED until a real authorised test succeeds.
