import {
  corsHeadersForOrigin,
  isAllowedBrowserOrigin,
  MAX_REQUEST_BODY_BYTES,
  MAX_WORKSPACE_STATE_BYTES,
  normalizeWorkspaceStateJson,
  publicErrorFor,
  PublicRequestError,
  readBoundedJsonObject,
  shouldAutoAssignReferralCode,
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

Deno.test("referral code assignment never mutates the reserved or any Enterprise Admin account", () => {
  const protectedRows = [
    {
      username_lc: "sho",
      role: "Enterprise Admin",
      affiliate_code: null,
    },
    {
      username_lc: "sho",
      role: "Enterprise Admin",
      affiliate_code: "AFF-LEGACY-15",
    },
    {
      username_lc: "other-admin",
      role: " enterprise admin ",
      affiliate_code: "",
    },
    {
      username: " SHO ",
      role: "User",
      affiliate_code: "",
    },
  ];
  for (const account of protectedRows) {
    assert(
      !shouldAutoAssignReferralCode(account),
      "Protected administrators must never receive an automatic code rewrite.",
    );
  }
  assert(
    shouldAutoAssignReferralCode({
      username_lc: "ordinary-user",
      role: "User",
      affiliate_code: "",
    }),
    "An ordinary account with no code may receive one.",
  );
  assert(
    shouldAutoAssignReferralCode({
      username_lc: "ordinary-user",
      role: "User",
      affiliate_code: "AFF-LEGACY-15",
    }),
    "An ordinary account may replace a retired legacy code on explicit summary action.",
  );
  assert(
    !shouldAutoAssignReferralCode({
      username_lc: "ordinary-user",
      role: "User",
      affiliate_code: "SHR-ABCDE12345",
    }),
    "An ordinary account with a current code must keep it.",
  );
});


Deno.test("CORS allowlist returns exact origin headers for only the approved app hosts", () => {
  const approvedOrigins = [
    "https://shoir-ie-app.streamlit.app",
    "https://shoirieverified.streamlit.app",
  ];
  for (const origin of approvedOrigins) {
    assert(
      isAllowedBrowserOrigin(origin),
      `Expected approved origin to be allowed: ${origin}`,
    );
    const headers = corsHeadersForOrigin(origin);
    assert(
      headers.get("Access-Control-Allow-Origin") === origin,
      "Approved origin must be echoed exactly, never wildcarded.",
    );
    assert(
      headers.get("Access-Control-Allow-Methods") === "POST, OPTIONS",
      "CORS methods must be limited to POST and OPTIONS.",
    );
    assert(
      headers.get("Vary") === "Origin",
      "Origin-specific responses must declare Vary: Origin.",
    );
  }

  for (const origin of [
    "https://unapproved-origin.example",
    "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
    "http://localhost:8501",
    "null",
  ]) {
    assert(
      !isAllowedBrowserOrigin(origin),
      `Expected origin to be denied: ${origin}`,
    );
    assert(
      !corsHeadersForOrigin(origin).has("Access-Control-Allow-Origin"),
      "Unapproved origins must never receive Access-Control-Allow-Origin.",
    );
  }

  assert(
    isAllowedBrowserOrigin(null),
    "Origin-free server-to-server calls must remain possible.",
  );
  assert(
    !corsHeadersForOrigin(null).has("Access-Control-Allow-Origin"),
    "Origin-free responses must not fabricate a browser origin.",
  );
});
