import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  inspectCsvShape,
  isAllowedApiMethod,
  isAllowedBrowserOrigin,
  MAX_REQUEST_BODY_BYTES,
  MAX_WORKSPACE_STATE_BYTES,
  normalizePlatformTier,
  normalizeWorkspaceStateJson,
  platformTierAllows,
  publicErrorFor,
  PublicRequestError,
  readBoundedJsonObject,
  sessionEntitlementFields,
} from "./security.ts";

Deno.test("only POST may dispatch persistence API actions", () => {
  assert(isAllowedApiMethod("POST"), "POST must be accepted.");
  assert(
    isAllowedApiMethod("post"),
    "HTTP method comparison must be case-insensitive.",
  );
  for (const method of ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"]) {
    assert(
      !isAllowedApiMethod(method),
      `${method} must not dispatch API actions.`,
    );
  }
});

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

Deno.test("session entitlement returns only safe live account fields", () => {
  const result = sessionEntitlementFields({
    username: "synthetic-enterprise-user",
    tier: "Enterprise Tier",
    active: true,
    subscription_expires_at: "2099-01-01T00:00:00Z",
    password_hash: "must-not-leak",
    email: "private@example.invalid",
    affiliate_code: "private-code",
  });

  assert(result.username === "synthetic-enterprise-user", "Username missing.");
  assert(result.tier === "Enterprise Tier", "Tier missing.");
  assert(result.active === true, "Active state missing.");
  assert(
    result.expires_at === "2099-01-01T00:00:00Z",
    "Subscription expiry missing.",
  );
  assert(
    !("password_hash" in result) && !("email" in result) &&
      !("affiliate_code" in result),
    "Private account fields must never be returned.",
  );
});

Deno.test("session entitlement fails closed on incomplete, inactive or expired account data", () => {
  const canonical = {
    username: "synthetic-enterprise-user",
    tier: "Enterprise Tier",
    active: true,
    subscription_expires_at: "2099-01-01T00:00:00Z",
  };
  const invalid = [
    { ...canonical, username: "" },
    { ...canonical, tier: "" },
    { ...canonical, active: false },
    { ...canonical, subscription_expires_at: "" },
    { ...canonical, subscription_expires_at: "not-a-date" },
    { ...canonical, subscription_expires_at: "2000-01-01T00:00:00Z" },
  ];

  for (const account of invalid) {
    try {
      sessionEntitlementFields(account);
    } catch (error) {
      assert(
        error instanceof PublicRequestError,
        "Expected a public request error.",
      );
      assert(error.status === 403, "Invalid entitlements must be denied.");
      continue;
    }
    throw new Error("Invalid account entitlement should not be accepted.");
  }
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

Deno.test("dataset API package gate follows the canonical tier hierarchy", () => {
  const allowed = [
    "Enterprise Tier",
    "Enterprise Plus Tier ($399)",
    "Research Pack",
  ];
  assert(
    normalizePlatformTier("Research Pack Add-on") === "Research Pack",
    "Research Pack should be recognized as a separate add-on state.",
  );
  assert(
    normalizePlatformTier("Enterprise Plus Tier ($399)") === "Enterprise Plus",
    "Enterprise Plus should keep its own tier identity.",
  );
  const denied = [
    "Starter Tier",
    "Mid-Tier Pro",
    "Pro Tier",
    "Professional Tier",
    "",
    undefined,
  ];
  for (const tier of allowed) {
    assert(
      platformTierAllows(tier, "Enterprise"),
      "Enterprise dataset capability should be allowed for " + String(tier),
    );
  }
  for (const tier of denied) {
    assert(
      !platformTierAllows(tier, "Enterprise"),
      "Enterprise dataset capability must be denied for " + String(tier),
    );
  }
  assert(
    !platformTierAllows("Enterprise Plus Tier ($399)", "Research Pack"),
    "Enterprise Plus must not be treated as the Research Pack add-on.",
  );
  assert(
    platformTierAllows("Research Pack", "Enterprise"),
    "Research Pack should retain its inherited base capabilities.",
  );
});

Deno.test("CSV shape inspection counts quoted logical records and handles CRLF", () => {
  const input = new TextEncoder().encode(
    "asset_id,description,value\r\n" +
      'A-1,"line one, with comma",10\r\n' +
      'A-2,"line one\nline two",20\r\n' +
      'A-3,"escaped ""quote""",30\r\n',
  );
  const shape = inspectCsvShape(input);
  assert(shape.rowCount === 3, "Quoted newlines must not create extra rows.");
  assert(shape.columnCount === 3, "CSV column count is incorrect.");
  assert(
    shape.headers.join("|") === "asset_id|description|value",
    "CSV headers were not parsed correctly.",
  );
});

Deno.test("CSV shape inspection rejects duplicate, blank and malformed headers", () => {
  const invalid = [
    "asset_id,asset_id\nA-1,A-2\n",
    "asset_id, \nA-1,A-2\n",
    'asset_id,description\nA-1,"unterminated\n',
    'asset_id,description\nA-1,unquoted"quote\n',
  ];
  for (const csv of invalid) {
    try {
      inspectCsvShape(new TextEncoder().encode(csv));
    } catch (error) {
      assert(
        error instanceof PublicRequestError,
        "Expected a public CSV validation error.",
      );
      assert(
        error.status === 400,
        "Malformed CSV must be rejected as client input.",
      );
      continue;
    }
    throw new Error("Malformed CSV should not be accepted.");
  }
});

Deno.test("CORS origins are isolated by the exact Supabase project", () => {
  const stagingUrl = "https://hfhrosthswcybccepmak.supabase.co";
  const productionUrl = "https://gcsamrdaeraxieaagsta.supabase.co";
  const productionOrigin = "https://shoir-ie-app.streamlit.app";
  const stagingOrigin = "https://shoirieverified.streamlit.app";
  const alternateStagingOrigin =
    "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app";
  const localOrigin = "http://localhost:8501";

  assert(
    isAllowedBrowserOrigin(productionOrigin, productionUrl),
    "Production app origin should be allowed by production.",
  );
  assert(
    !isAllowedBrowserOrigin(stagingOrigin, productionUrl),
    "Staging origin must not be allowed by production.",
  );
  assert(
    !isAllowedBrowserOrigin(alternateStagingOrigin, productionUrl),
    "Alternate staging origin must not be allowed by production.",
  );
  assert(
    isAllowedBrowserOrigin(stagingOrigin, stagingUrl),
    "Staging app origin should be allowed by staging.",
  );
  assert(
    isAllowedBrowserOrigin(alternateStagingOrigin, stagingUrl),
    "Configured alternate staging origin should be allowed by staging.",
  );
  assert(
    isAllowedBrowserOrigin(localOrigin, stagingUrl),
    "Local development origin should be allowed only by staging.",
  );
  assert(
    !isAllowedBrowserOrigin(productionOrigin, stagingUrl),
    "Production origin must not be allowed by staging.",
  );
  assert(
    !isAllowedBrowserOrigin("https://attacker.example", stagingUrl),
    "Unknown browser origin must be rejected.",
  );
  assert(
    !isAllowedBrowserOrigin(
      "https://shoir-ie-app.streamlit.app.evil.test",
      productionUrl,
    ),
    "Lookalike production host must be rejected.",
  );
  assert(
    !isAllowedBrowserOrigin(
      productionOrigin,
      "https://unknown.supabase.co",
    ),
    "Unknown Supabase project must fail closed.",
  );
  assert(
    isAllowedBrowserOrigin(null, productionUrl),
    "Origin-less server-to-server call should remain possible.",
  );

  const productionHeaders = corsHeadersForOrigin(
    productionOrigin,
    productionUrl,
  );
  assert(
    productionHeaders.get("Access-Control-Allow-Origin") === productionOrigin,
    "Production CORS header must echo only the production origin.",
  );
  const allowedHeaders = productionHeaders.get(
    "Access-Control-Allow-Headers",
  ) || "";
  const expectedHeaders = [
    "authorization",
    "x-client-info",
    "apikey",
    "content-type",
    "x-retry-count",
    "traceparent",
    "tracestate",
    "baggage",
  ];
  for (const header of expectedHeaders) {
    assert(
      allowedHeaders.toLowerCase().includes(header),
      `CORS preflight must allow the supported Supabase client header: ${header}`,
    );
  }
  const deniedHeaders = corsHeadersForOrigin(stagingOrigin, productionUrl);
  assert(
    deniedHeaders.get("Access-Control-Allow-Origin") === null,
    "Denied origin must not receive Access-Control-Allow-Origin.",
  );
});
