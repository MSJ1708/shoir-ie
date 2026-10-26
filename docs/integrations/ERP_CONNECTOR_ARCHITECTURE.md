# ERP Connector Architecture and Security Contract

**State: design plus isolated mapping-engine foundation.** The adapter module added in this branch maps explicitly configured provider responses to canonical records using an injected read-only transport. This branch does not implement a vendor OAuth login flow, a production HTTP transport, scheduled synchronization, durable checkpoints or a connected UI state. Those are later milestones and must remain visibly unconfigured until implemented and live-tested.

## Placement in the product

Extend the existing T096 Integration Management Center / Enterprise Integration & Collaboration workflow. Do not add a second connector registry or new top-level navigation.

Conceptual flow:

Customer IT product/API selection → server-side connection profile → provider-specific auth provider → hardened GET-only transport → provider adapter → explicit response contract → canonical field map and validation → workspace-scoped staging/persistence → Industrial Workbook and Digital Thread → analysis/simulation/optimization → traceable decision/export.

No module may create an ERP write operation through this integration MVP.

## Product adapters

Use exact product IDs; never select auth or API behavior from a broad "SAP" or "Oracle" label alone.

- SAP S/4HANA Cloud Public Edition
- SAP S/4HANA Cloud Private Edition/customer-managed S/4HANA
- SAP ECC
- Oracle Fusion Cloud ERP/Financials
- Oracle Fusion Cloud SCM/Manufacturing
- Oracle E-Business Suite

The implementation may share strictly read-only parsing/mapping primitives. Product-specific API selection, auth flows, pagination, response shapes, rate limits and data semantics remain explicit to the product profile and customer tenant. Oracle EBS must never share an assumed Fusion endpoint or grant. SAP ECC must never be presented as S/4HANA support.

## Credential and tenant contract

Connection metadata contains an opaque secret reference, not secret material. Credentials may only be resolved inside an approved server-side credential/authentication component. Do not pass raw tokens into Streamlit state, browser storage, user-editable JSON, database rows, audit payloads, exports or error text.

The connection profile must be associated with an immutable connection reference, a workspace, a tenant alias, an exact product ID and a server-authorized owner/admin scope. Authorization must be checked on each operation using the actor, workspace, connection and logical resource. A caller-supplied connection ID is never proof of access.

The mapping-engine boundary requires a server-side authorization callback and exact hostname/port allowlist. A future HTTP transport must preserve TLS validation, reject redirects, resolve and validate all destination addresses, pin a permitted address to prevent DNS rebinding, block metadata/loopback/link-local/multicast/reserved destinations, use bounded timeouts and response sizes, and avoid untrusted proxies. On-premise connectivity must use a customer-approved integration gateway or private connectivity pattern; do not open unrestricted public ingress.

## Canonical Digital Thread mapping

Integrate with Shoir-IE's existing vocabulary from shoir_digital_thread.py:

Dataset → Asset → Process → Product → Material → Order → Workforce → Quality → Maintenance → Energy → Cost → Scenario → KPI → Model → Experiment → Decision → Outcome.

A provider response is not a canonical model by itself. Every resource binding must configure:
- an exact provider-relative resource path;
- the response collection path for that API version (not guessed as `value`, `items` or any other default);
- one canonical entity type;
- the source primary-key path;
- an explicit allowlisted field map;
- required canonical fields, mapping version and any units/currency/timezone metadata;
- optional source-updated timestamp path.

Only explicitly mapped values are emitted; unselected source fields are discarded. Missing required fields, conflicting duplicates, unparseable collection shapes and unsupported values must not be silently treated as valid records. Do not infer unit conversions, currency, calendar, plant identity or timezone. Preserve units and source timestamps as metadata; perform a conversion only under a separate explicit, tested mapping rule.

Workforce-related APIs require a separate data-minimization/privacy decision. Prefer aggregate counts and measures. Do not map employee/person names, personal identifiers, contact details, addresses, birth data or other unnecessary personal data.

## Lineage

Every mapped record must carry:
- source provider and exact product profile;
- opaque connection and tenant references;
- logical resource and source object hash (not raw identifier by default);
- source timestamp if present and valid;
- import/read timestamp in UTC;
- mapping version;
- explicitly stated units, currency and source timezone;
- validation state.

Lineage is evidence of origin, not proof that the source data is correct, current or complete. Every display and export should retain the difference between source time and read/import time.

## Read and synchronization reliability

The transport contract is GET-only. Use provider-approved page tokens/links but never follow arbitrary absolute next-page URLs without reapplying the same destination policy. Bound page size, total pages, total records and response size. Reject repeating page tokens. Apply idempotent keys per connection/resource/source record. Identical duplicates may be counted and collapsed; conflicting duplicate data must be flagged and excluded pending review.

Only retry provider-documented transient failures with bounded backoff and rate-limit compliance. Do not retry permanent authentication, permission, tenant or schema failures indefinitely. Cancellation/revocation must stop future reads. A future durable sync implementation must atomically persist the imported records with its checkpoint; a partial import must not advance the checkpoint beyond records successfully committed. The current mapping-engine foundation does not claim to provide durable sync.

## Connection status semantics

- Not configured — required product profile or server-side prerequisites are absent.
- Configuration required — details recorded, but validation is incomplete.
- Test pending — an authorized operator has requested a test and it is not complete.
- Connected — read-only — live health and an approved read succeeded.
- Validated for capability — each listed resource has its own successful live read and negative-test evidence.
- Sync active — durable, bounded synchronization is implemented and its last run is healthy.
- Paused/revoked — explicit administrative state.
- Failed — action required — last test or read failed with a sanitized diagnostic.

Never infer Connected from a saved URL, token reference, mock response, health endpoint alone or connector-registry entry.

## Threat model and controls

| Threat | Required control |
|---|---|
| SSRF / metadata access / DNS rebinding | Exact allowlist, DNS validation and pinned HTTPS transport; redirect rejection; no arbitrary private-network allow |
| Cross-workspace connection or cache reuse | Server-side RBAC and workspace binding on every read; workspace key included in cache/persistence scope |
| Credential leakage | Secret reference only; provider-side token acquisition/refresh; redaction in logs, previews and errors |
| Overprivileged ERP access | Customer-defined least-privilege read role, exact resource scopes, no write method |
| Mass export or personal data exposure | Capability and row-level authorization, field allowlist, minimization, bounded results, approved export |
| Pagination or API abuse | Page/record/response/timeout limits, bounded retry, rate-limit handling and cancellation |
| Schema drift / wrong units | Contract validation, mapping version, explicit units/currency/timezone, quarantine on required-field failure |
| Misleading freshness | Separate source timestamp and read timestamp; never claim sync when no successful provider read exists |
| Provider compromise or malformed payload | JSON/type validation, no dynamic code/plugin execution, no raw payload rendering |
| Duplicate or partial import | Stable idempotency keys, conflict reporting, atomic persistence/checkpoint in the later sync layer |

## Definition of completion

The module scaffold and deterministic mapper do not equal live support. Completion requires production-grade provider-specific auth and transport, UI wiring in the existing T096 module, durable workspace-scoped persistence, full automated security tests, an approved staging tenant per supported product and successful live positive/negative acceptance. Keep each product and capability status separate until that evidence exists.
