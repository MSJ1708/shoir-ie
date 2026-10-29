import {
  corsHeadersForOrigin,
  isAllowedBrowserOrigin,
  MAX_REQUEST_BODY_BYTES,
  parseAllowedBrowserOrigins,
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

Deno.test("CORS allowlists are isolated per deployment environment", () => {
  const productionOrigins = parseAllowedBrowserOrigins(undefined);
  const productionOrigin = "https://shoir-ie-app.streamlit.app";
  const stagingOrigin = "https://shoirieverified.streamlit.app";

  assert(
    isAllowedBrowserOrigin(productionOrigin, productionOrigins),
    "Production origin must be allowed by the safe default.",
  );
  assert(
    !isAllowedBrowserOrigin(stagingOrigin, productionOrigins),
    "Staging origin must not be allowed against the production default.",
  );
  assert(
    corsHeadersForOrigin(productionOrigin, productionOrigins)
      .get("Access-Control-Allow-Origin") === productionOrigin,
    "Production origin must be echoed exactly.",
  );

  const stagingOrigins = parseAllowedBrowserOrigins(stagingOrigin);
  assert(
    isAllowedBrowserOrigin(stagingOrigin, stagingOrigins),
    "Configured staging origin must be allowed in staging.",
  );
  assert(
    !isAllowedBrowserOrigin(productionOrigin, stagingOrigins),
    "Staging allowlist must not include the production host.",
  );
  assert(
    corsHeadersForOrigin(stagingOrigin, stagingOrigins)
      .get("Access-Control-Allow-Origin") === stagingOrigin,
    "Staging origin must be echoed exactly only when configured.",
  );

  for (const origin of [
    "https://unapproved-origin.example",
    "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
    "http://localhost:8501",
    "null",
  ]) {
    assert(
      !isAllowedBrowserOrigin(origin, productionOrigins),
      `Expected origin to be denied by production: ${origin}`,
    );
    assert(
      !corsHeadersForOrigin(origin, productionOrigins)
        .has("Access-Control-Allow-Origin"),
      "Unapproved production origins must not get ACAO.",
    );
    assert(
      !isAllowedBrowserOrigin(origin, stagingOrigins),
      `Expected origin to be denied by staging: ${origin}`,
    );
    assert(
      !corsHeadersForOrigin(origin, stagingOrigins)
        .has("Access-Control-Allow-Origin"),
      "Unapproved staging origins must not get ACAO.",
    );
  }

  for (const malformed of [
    "http://shoir-ie-app.streamlit.app",
    "https://shoir-ie-app.streamlit.app/path",
    "https://user:password@example.com",
    "",
    "https://good.example,",
    "https://unverified-domain.example",
  ]) {
    assert(
      parseAllowedBrowserOrigins(malformed).size === 0,
      "Invalid configured origins must fail closed.",
    );
  }

  assert(
    isAllowedBrowserOrigin(null, productionOrigins),
    "Origin-free server calls must remain possible.",
  );
  assert(
    !corsHeadersForOrigin(null, productionOrigins)
      .has("Access-Control-Allow-Origin"),
    "Origin-free responses must not fabricate a browser origin.",
  );
});
