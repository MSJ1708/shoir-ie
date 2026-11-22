# @shoir-ie/persistence-sdk (beta)

This is a small typed client for the existing **session-scoped** Shoir-IE persistence Edge Function. It is a repository package, not yet published to npm or exposed through a customer-facing gateway.

## Supported operations

- List platform records with server-enforced workspace scope and bounded pagination.
- Save a platform record with server-enforced session, workspace and record-type checks.
- Load personal or explicitly selected organization workspace state.

## Configuration

Use the staging Edge Function URL and Supabase publishable key. Pass the current user's Shoir-IE session token from the application's secure session store. The publishable key is public configuration, not a service-role key. Never ship a service-role/secret key to a browser or SDK consumer.

```js
import { ShoirIEClient } from "@shoir-ie/persistence-sdk";

const client = new ShoirIEClient({
  edgeUrl: process.env.SHOIR_EDGE_URL,
  publishableKey: process.env.SHOIR_PUBLISHABLE_KEY,
  username: session.username,
  sessionToken: session.token
});

const page = await client.listPlatformRecords({ recordType: "decision", limit: 50 });
```

The SDK does not store, refresh, print or automatically retry the session token. It refuses non-HTTPS URLs, non-Supabase hosts, endpoint paths other than the exact persistence function, redirects, oversized request payloads and invalid pagination inputs. Each request uses a bounded timeout (15 seconds by default; configurable from 1 to 30 seconds), and response bodies are capped at 2 MiB while streamed. Browser callers must also be covered by the Edge Function's server-side CORS origin allowlist.

## Deliberate release boundary

This SDK does not create API keys, authenticate service-to-service consumers, publish an API hostname, provide public OpenAPI compatibility guarantees, implement per-tenant API quotas, or execute inert plugin manifests. It must not be used as a public commercial API until T097's hosted gateway, identity, rate limits, audit, external-client and independent-security acceptance is complete.

## Local tests

`npm test` uses Node's built-in test runner and mocked fetch responses. These tests do not call a hosted endpoint.
