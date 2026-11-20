import test from "node:test";
import assert from "node:assert/strict";
import { ShoirIEApiError, ShoirIEClient, SHOIR_IE_API_VERSION } from "../index.mjs";

const edgeUrl = "https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence";
const base = { edgeUrl, publishableKey: "public-publishable-key", username: "shoir-e2e-active", sessionToken: "opaque-test-session-token" };

test("client validates the exact HTTPS Supabase function endpoint", () => {
  assert.throws(() => new ShoirIEClient({ ...base, edgeUrl: "http://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence" }), /exact HTTPS/);
  assert.throws(() => new ShoirIEClient({ ...base, edgeUrl: "https://attacker.example.test/functions/v1/shoir-persistence" }), /exact HTTPS/);
  assert.throws(() => new ShoirIEClient({ ...base, edgeUrl: edgeUrl + "?token=leak" }), /exact HTTPS/);
});

test("list sends API v1, project headers and bounded pagination", async () => {
  let call;
  const client = new ShoirIEClient({ ...base, fetchImpl: async (url, options) => {
    call = { url, options };
    return { ok: true, status: 200, json: async () => ({ ok: true, records: [], has_more: false, next_offset: 0 }) };
  }});
  const result = await client.listPlatformRecords({ recordType: "decision", limit: 25, offset: 50 });
  assert.equal(result.ok, true);
  assert.equal(call.url, edgeUrl);
  assert.equal(call.options.method, "POST");
  assert.equal(call.options.redirect, "error");
  assert.equal(call.options.credentials, "omit");
  assert.equal(call.options.headers.apikey, base.publishableKey);
  assert.equal(call.options.headers.Authorization, "Bearer " + base.publishableKey);
  const body = JSON.parse(call.options.body);
  assert.equal(body.api_version, "v1");
  assert.equal(body.action, "platform_record_list");
  assert.equal(body.record_type, "decision");
  assert.equal(body.offset, 50);
  assert.equal(body.token, base.sessionToken);
  assert.equal(SHOIR_IE_API_VERSION, "v1");
});

test("invalid pagination and partial organization scope fail before network", async () => {
  let calls = 0;
  const client = new ShoirIEClient({ ...base, fetchImpl: async () => { calls += 1; throw new Error("unexpected"); }});
  await assert.rejects(() => client.listPlatformRecords({ limit: 201 }), /between 1 and 200/);
  await assert.rejects(() => client.listPlatformRecords({ organizationId: "org-only" }), /must be supplied together/);
  assert.equal(calls, 0);
});

test("save validates a JSON object and sends a bounded payload", async () => {
  let body;
  const client = new ShoirIEClient({ ...base, fetchImpl: async (_url, options) => {
    body = JSON.parse(options.body);
    return { ok: true, status: 200, json: async () => ({ ok: true, record: { entity_key: "DEC-1" } }) };
  }});
  const saved = await client.savePlatformRecord({ recordType: "decision", entityKey: "DEC-1", payload: { status: "Draft" } });
  assert.equal(saved.record.entity_key, "DEC-1");
  assert.equal(body.action, "platform_record_save");
  assert.deepEqual(body.payload, { status: "Draft" });
  await assert.rejects(() => client.savePlatformRecord({ recordType: "decision", entityKey: "DEC-2", payload: [] }), /JSON object/);
});

test("API errors are surfaced without serializing request credentials", async () => {
  const client = new ShoirIEClient({ ...base, fetchImpl: async () => ({ ok: false, status: 403, json: async () => ({ error: "Access denied." }) }) });
  await assert.rejects(() => client.loadWorkspace(), (error) =>
    error instanceof ShoirIEApiError && error.status === 403 && error.message === "Access denied." && !error.message.includes(base.sessionToken)
  );
});

test("oversized payloads are rejected before fetch", async () => {
  let calls = 0;
  const client = new ShoirIEClient({ ...base, fetchImpl: async () => { calls += 1; return {}; }});
  const large = { data: "x".repeat(1024 * 1024) };
  await assert.rejects(() => client.savePlatformRecord({ recordType: "decision", entityKey: "D-1", payload: large }), /1 MiB/);
  assert.equal(calls, 0);
});
