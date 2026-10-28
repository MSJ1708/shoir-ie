import {
  hasCanonicalMasterAdminInvariant,
  MAX_REQUEST_BODY_BYTES,
  MAX_WORKSPACE_STATE_BYTES,
  normalizeWorkspaceStateJson,
  publicErrorFor,
  PublicRequestError,
  readBoundedJsonObject,
} from "./security.ts";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

async function expectPublicError(
  action: () => unknown | Promise<unknown>,
  expectedStatus: number,
  expectedText: string,
): Promise<void> {
  try {
    await action();
  } catch (error) {
    assert(error instanceof PublicRequestError, "Expected PublicRequestError.");
    assert(
      error.status === expectedStatus,
      `Expected status ${expectedStatus}, got ${error.status}.`,
    );
    assert(
      error.message.includes(expectedText),
      `Expected message to include "${expectedText}".`,
    );
    return;
  }
  throw new Error("Expected the action to reject.");
}

Deno.test("bounded JSON parser accepts a normal object", async () => {
  const request = new Request("https://example.invalid", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ action: "workspace_load", username: "test-user" }),
  });
  const parsed = await readBoundedJsonObject(request);
  assert(parsed.action === "workspace_load", "Action was not parsed.");
  assert(parsed.username === "test-user", "Username was not parsed.");
});

Deno.test("bounded JSON parser rejects invalid JSON and non-object JSON", async () => {
  const invalid = new Request("https://example.invalid", {
    method: "POST",
    body: "{not-json",
  });
  await expectPublicError(
    () => readBoundedJsonObject(invalid),
    400,
    "valid UTF-8 JSON",
  );

  const array = new Request("https://example.invalid", {
    method: "POST",
    body: "[]",
  });
  await expectPublicError(
    () => readBoundedJsonObject(array),
    400,
    "JSON object",
  );
});

Deno.test("bounded JSON parser enforces the actual streamed byte limit", async () => {
  const payload = JSON.stringify({ data: "x".repeat(128) });
  const request = new Request("https://example.invalid", {
    method: "POST",
    body: payload,
  });
  await expectPublicError(
    () => readBoundedJsonObject(request, 32),
    413,
    "size limit",
  );
  assert(
    MAX_REQUEST_BODY_BYTES > payload.length,
    "Default limit should allow this small fixture.",
  );
});

Deno.test("workspace JSON accepts objects and keeps a missing state recoverable", () => {
  const source = '{"project":"synthetic","revision":2}';
  assert(
    normalizeWorkspaceStateJson(source) === source,
    "Serialized object should be preserved.",
  );
  assert(
    normalizeWorkspaceStateJson(undefined) === "{}",
    "Missing state should normalize to an empty object.",
  );
  assert(
    normalizeWorkspaceStateJson({ project: "synthetic" }) ===
      '{"project":"synthetic"}',
    "Object input should serialize.",
  );
});

Deno.test("workspace JSON rejects malformed, non-object, and oversized state before replacement", async () => {
  await expectPublicError(
    () => normalizeWorkspaceStateJson("{broken"),
    400,
    "valid JSON",
  );
  await expectPublicError(
    () => normalizeWorkspaceStateJson("[1,2]"),
    400,
    "JSON object",
  );
  await expectPublicError(
    () => normalizeWorkspaceStateJson('{"value":"123456"}', 8),
    413,
    "size limit",
  );
  assert(
    MAX_WORKSPACE_STATE_BYTES > 8,
    "Default workspace limit should exceed the small test limit.",
  );
});

Deno.test("public error mapping does not expose internal infrastructure details", () => {
  const internal = publicErrorFor(
    new Error("postgres host=secret.internal password=do-not-leak"),
  );
  assert(
    internal.status === 500,
    "Unknown internal failures should remain server errors.",
  );
  assert(
    !internal.message.includes("secret.internal"),
    "Internal host leaked in response.",
  );
  assert(
    !internal.message.includes("do-not-leak"),
    "Internal secret leaked in response.",
  );

  const unauthorized = publicErrorFor(new Error("Unauthorized session."));
  assert(
    unauthorized.status === 401,
    "Unauthorized sessions should be 401.",
  );
  assert(
    unauthorized.message === "Unauthorized session.",
    "Expected stable public auth message.",
  );

  const invalidProof = publicErrorFor(
    new Error("Payment proof exceeds the 512 KiB limit."),
  );
  assert(
    invalidProof.status === 400,
    "Invalid proof should be a client error.",
  );
});

Deno.test("protected administrator invariant is read-only and fails closed on drift", () => {
  const canonical = Object.freeze({
    username_lc: "sho",
    role: "Enterprise Admin",
    tier: "Enterprise Plus Tier ($399)",
    active: true,
    subscription_expires_at: "2099-01-01T00:00:00+00:00",
  });
  assert(
    hasCanonicalMasterAdminInvariant(canonical),
    "Canonical protected administrator state should be accepted.",
  );
  assert(
    canonical.tier === "Enterprise Plus Tier ($399)",
    "The invariant check must not mutate the account.",
  );

  const invalidRows = [
    { ...canonical, role: "User" },
    { ...canonical, tier: "Professional Tier ($129)" },
    { ...canonical, active: false },
    { ...canonical, subscription_expires_at: "2030-01-01T00:00:00Z" },
    { ...canonical, username_lc: "another-user" },
  ];
  for (const row of invalidRows) {
    assert(
      !hasCanonicalMasterAdminInvariant(row),
      "Invariant drift must be detected and rejected.",
    );
  }
});
