import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  isAllowedBrowserOrigin,
  shouldAutoAssignReferralCode,
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
    subscription_expires_at: "2099-01-01T00:00:00.000Z",
  });
  assert(
    hasCanonicalMasterAdminInvariant(canonical),
    "The canonical reserved administrator should pass the invariant.",
  );

  const invalidCases: Array<Record<string, unknown>> = [
    { ...canonical, username_lc: "not-sho" },
    { ...canonical, role: "Enterprise User" },
    { ...canonical, tier: "Enterprise Tier" },
    { ...canonical, active: false },
    { ...canonical, subscription_expires_at: "2098-12-31T23:59:59.000Z" },
    { ...canonical, subscription_expires_at: null },
  ];
  for (const account of invalidCases) {
    assert(
      !hasCanonicalMasterAdminInvariant(account),
      "Administrator invariant drift must be rejected.",
    );
  }
  assert(
    canonical.tier === "Enterprise Plus Tier ($399)" &&
      canonical.subscription_expires_at === "2099-01-01T00:00:00.000Z",
    "The invariant checker must not mutate its input.",
  );
});

Deno.test("persistence CORS allows only exact configured browser origins", () => {
  const origins = [
    "https://shoir-ie-app.streamlit.app",
    "https://shoirieverified.streamlit.app",
    "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
    "http://127.0.0.1:8501",
    "http://localhost:8501",
  ];
  for (const origin of origins) {
    assert(isAllowedBrowserOrigin(origin), `Expected allowlisted origin: ${origin}`);
    const headers = corsHeadersForOrigin(origin);
    assert(
      headers.get("Access-Control-Allow-Origin") === origin,
      "CORS must reflect the exact allowlisted origin, not a wildcard.",
    );
    assert(
      headers.get("Access-Control-Allow-Methods") === "POST, OPTIONS",
      "Preflight must name only supported browser request methods.",
    );
    assert(
      headers.get("Vary") === "Origin",
      "Origin-specific headers must be cache-safe.",
    );
  }

  assert(
    isAllowedBrowserOrigin(null),
    "Server-to-server requests without an Origin header must remain supported.",
  );
  assert(
    !corsHeadersForOrigin(null).has("Access-Control-Allow-Origin"),
    "Requests without an Origin must not receive a fabricated CORS origin.",
  );

  const rejected = [
    "https://attacker.invalid",
    "https://shoir-ie-app.streamlit.app.attacker.invalid",
    "null",
  ];
  for (const origin of rejected) {
    assert(
      !isAllowedBrowserOrigin(origin),
      `Unexpected browser origin accepted: ${origin}`,
    );
    assert(
      !corsHeadersForOrigin(origin).has("Access-Control-Allow-Origin"),
      "Rejected origins must never receive an allow-origin header.",
    );
  }
});


Deno.test("reserved administrator referral metadata is never auto-assigned", () => {
  assert(
    !shouldAutoAssignReferralCode("sho", ""),
    "A blank reserved-admin referral code must not trigger a write.",
  );
  assert(
    !shouldAutoAssignReferralCode("sho", "AFF-LEGACY"),
    "A legacy reserved-admin referral code must not trigger a rewrite.",
  );
  assert(
    !shouldAutoAssignReferralCode("SHO", ""),
    "The reserved-admin guard must be case-insensitive.",
  );
  assert(
    shouldAutoAssignReferralCode("ordinary-user", ""),
    "An ordinary account without a referral code may receive a code.",
  );
  assert(
    shouldAutoAssignReferralCode("ordinary-user", "AFF-LEGACY"),
    "An ordinary account's legacy code may be normalized.",
  );
  assert(
    !shouldAutoAssignReferralCode("ordinary-user", "SHR-CURRENT"),
    "An ordinary account's existing canonical code must be preserved.",
  );
});
