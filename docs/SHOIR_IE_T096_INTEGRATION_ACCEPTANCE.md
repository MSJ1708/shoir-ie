# Shoir-IE T096 Integration Management Centre Acceptance

Assessment date: 2026-11-06. Status: **foundation only / external configuration required**.

`shoir_erp_connectors.py` defines explicit SAP S/4HANA Public/Private, SAP ECC, Oracle Fusion ERP, Oracle Fusion SCM and Oracle EBS product profiles; a read-only GET transport protocol; and canonical mapping contracts. Its own module documentation states there is no HTTP implementation or token handling and requires injected server-side authorization/transport. The 22-row `docs/integrations/ERP_ACCEPTANCE_MATRIX.csv` was marked NOT RUN in the inspected source.

Missing: provider auth/OAuth and secret resolution; production HTTP transport with TLS/DNS/IP pinning/allowlists/redirect rejection/timeouts/size and rate bounds; durable connector UI/health registry; hosted acceptance; SAP and Oracle sandbox credentials.

Complete in order: (1) keep connector state unconfigured until verified; (2) add controlled-server security tests for SSRF, DNS rebinding, redirects, TLS and response limits; (3) implement server-side provider-aware secret resolution and GET-only transport; (4) wire the existing Integration Management Centre; (5) obtain exact product sandbox and least-privilege read-only credentials; (6) execute live auth, expiry/revocation, rate-limit and schema-drift tests; (7) prove sanitization and lineage; (8) attach evidence per exact supported product. Mocks do not count as live SAP/Oracle acceptance.
