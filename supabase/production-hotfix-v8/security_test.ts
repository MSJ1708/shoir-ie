import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  hasExactlyOneCanonicalMasterAdmin,
  isAllowedBrowserOrigin,
  MAX_REQUEST_BODY_BYTES,
  PublicRequestError,
  readBoundedJsonObject,
} from "./security.ts";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

Deno.test("v8 hotfix CORS uses exact approved origins and never a wildcard", () => {
  const origin = "https://shoir-ie-app.streamlit.app";
  assert(
    isAllowedBrowserOrigin(origin),
    "production app origin must be allowed exactly",
  );
  const headers = corsHeadersForOrigin(origin);
  assert(
    headers.get("Access-Control-Allow-Origin") === origin,
    "approved origin must be reflected exactly",
  );
  assert(
    headers.get("Access-Control-Allow-Origin") !== "*",
    "wildcard CORS is forbidden",
  );
  assert(
    headers.get("Access-Control-Allow-Methods") === "POST, OPTIONS",
    "method allowlist is required",
  );
  assert(
    headers.get("Vary") === "Origin",
    "cache variation by origin is required",
  );
});

Deno.test("v8 hotfix rejects an unapproved origin and emits no allow-origin header", () => {
  const rejectedOrigins = [
    "https://unapproved-origin.example",
    "https://shoirieverified.streamlit.app",
    "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
    "http://localhost:8501",
  ];
  for (const origin of rejectedOrigins) {
    assert(
      !isAllowedBrowserOrigin(origin),
      `unapproved browser origin ${origin} must be rejected before handling`,
    );
    assert(
      !corsHeadersForOrigin(origin).has("Access-Control-Allow-Origin"),
      `unapproved origin ${origin} must not receive ACAO`,
    );
  }
});

Deno.test("v8 hotfix keeps origin-free server-to-server calls possible without ACAO", () => {
  assert(
    isAllowedBrowserOrigin(null),
    "origin-free server-to-server calls remain allowed",
  );
  assert(
    !corsHeadersForOrigin(null).has("Access-Control-Allow-Origin"),
    "no origin must not receive fabricated ACAO",
  );
});

Deno.test("v8 hotfix accepts the exact reserved administrator invariant read-only", () => {
  const canonical = {
    username_lc: "sho",
    role: "Enterprise Admin",
    tier: "Enterprise Plus Tier ($399)",
    active: true,
    subscription_expires_at: "2099-01-01T00:00:00Z",
  };
  assert(
    hasCanonicalMasterAdminInvariant(canonical),
    "canonical reserved admin must pass",
  );
  const variants = [
    { ...canonical, username_lc: "other" },
    { ...canonical, role: "User" },
    { ...canonical, tier: "Enterprise Tier ($199)" },
    { ...canonical, active: false },
    { ...canonical, subscription_expires_at: "2099-01-02T00:00:00Z" },
  ];
  for (const variant of variants) {
    assert(
      !hasCanonicalMasterAdminInvariant(variant),
      "every changed invariant must fail closed",
    );
  }
  assert(
    canonical.tier === "Enterprise Plus Tier ($399)",
    "check must not mutate the supplied account object",
  );
});

Deno.test("reserved administrator list requires exactly one canonical active admin", () => {
  const canonical = {
    username_lc: "sho",
    role: "Enterprise Admin",
    tier: "Enterprise Plus Tier ($399)",
    active: true,
    subscription_expires_at: "2099-01-01T00:00:00Z",
  };
  assert(
    hasExactlyOneCanonicalMasterAdmin([canonical]),
    "one canonical active administrator must pass",
  );
  assert(
    !hasExactlyOneCanonicalMasterAdmin([]),
    "missing active administrator must fail closed",
  );
  assert(
    !hasExactlyOneCanonicalMasterAdmin([canonical, canonical]),
    "multiple active administrators must fail closed",
  );
  assert(
    !hasExactlyOneCanonicalMasterAdmin([{ ...canonical, username_lc: "other" }]),
    "a different administrator identity must fail closed",
  );
  assert(
    !hasExactlyOneCanonicalMasterAdmin([{ ...canonical, active: false }]),
    "inactive reserved administrator must fail closed",
  );
});

async function expectPublicRequestError(
  action: () => unknown | Promise<unknown>,
  expectedStatus: number,
  expectedText: string,
): Promise<void> {
  try {
    await action();
  } catch (error) {
    assert(error instanceof PublicRequestError, "Expected PublicRequestError.");
    assert(error.status === expectedStatus, `Expected status ${expectedStatus}, got ${error.status}.`);
    assert(error.message.includes(expectedText), `Expected message to include "${expectedText}".`);
    return;
  }
  throw new Error("Expected the action to reject.");
}

Deno.test("bounded parser accepts a normal object", async () => {
  const request = new Request("https://example.invalid", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ action: "login", username: "synthetic-user" }),
  });
  const parsed = await readBoundedJsonObject(request);
  assert(parsed.action === "login", "Action was not parsed.");
  assert(parsed.username === "synthetic-user", "Username was not parsed.");
});

Deno.test("bounded parser rejects invalid JSON and non-object JSON", async () => {
  const invalid = new Request("https://example.invalid", {
    method: "POST",
    body: "{not-json",
  });
  await expectPublicRequestError(
    () => readBoundedJsonObject(invalid),
    400,
    "valid UTF-8 JSON",
  );

  const array = new Request("https://example.invalid", {
    method: "POST",
    body: "[]",
  });
  await expectPublicRequestError(
    () => readBoundedJsonObject(array),
    400,
    "JSON object",
  );
});

Deno.test("bounded parser enforces actual streamed body byte limit", async () => {
  const request = new Request("https://example.invalid", {
    method: "POST",
    body: JSON.stringify({ data: "x".repeat(128) }),
  });
  await expectPublicRequestError(
    () => readBoundedJsonObject(request, 32),
    413,
    "size limit",
  );
  assert(MAX_REQUEST_BODY_BYTES > 128, "Default request limit should allow the fixture.");
});
