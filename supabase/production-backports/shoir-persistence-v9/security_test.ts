import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  isAllowedApiMethod,
  isAllowedBrowserOrigin,
  normalizeWorkspaceStateJson,
  PublicRequestError,
  readBoundedJsonObject,
} from "./security.ts";

Deno.test("production v9 dispatches API actions only for POST", () => {
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

Deno.test("production v9 CORS allows only the exact production app origin", () => {
  const projectUrl = "https://gcsamrdaeraxieaagsta.supabase.co";
  const allowed = "https://shoir-ie-app.streamlit.app";
  assert(
    isAllowedBrowserOrigin(allowed, projectUrl),
    "Production app must be allowed.",
  );
  assert(
    isAllowedBrowserOrigin(null, projectUrl),
    "Server-to-server callers must remain possible.",
  );
  for (
    const origin of [
      "https://shoirieverified.streamlit.app",
      "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
      "https://attacker.example",
      "https://shoir-ie-app.streamlit.app.evil.test",
      "http://shoir-ie-app.streamlit.app",
    ]
  ) {
    assert(
      !isAllowedBrowserOrigin(origin, projectUrl),
      `Unexpected allowed origin: ${origin}`,
    );
  }
  assert(
    !isAllowedBrowserOrigin(allowed, "https://unknown.supabase.co"),
    "Unknown Supabase project must fail closed.",
  );
  const headers = corsHeadersForOrigin(allowed, projectUrl);
  assert(
    headers.get("Access-Control-Allow-Origin") === allowed,
    "Allowed origin must be echoed exactly.",
  );
  assert(headers.get("Vary") === "Origin", "Vary: Origin is required.");
  const denied = corsHeadersForOrigin("https://attacker.example", projectUrl);
  assert(
    denied.get("Access-Control-Allow-Origin") === null,
    "Denied origins must not get ACAO.",
  );
  assert(
    !headers.get("Access-Control-Allow-Headers")?.includes("*"),
    "Wildcard request-header policy is not allowed.",
  );
});

Deno.test("reserved administrator invariant is exact and side-effect free", () => {
  const canonical = Object.freeze({
    username_lc: "sho",
    role: "Enterprise Admin",
    tier: "Enterprise Plus Tier ($399)",
    active: true,
    subscription_expires_at: "2099-01-01T00:00:00Z",
  });
  assert(
    hasCanonicalMasterAdminInvariant(canonical),
    "Canonical admin must pass.",
  );
  assert(
    canonical.tier === "Enterprise Plus Tier ($399)",
    "Invariant check must not mutate the account.",
  );
  assert(
    !hasCanonicalMasterAdminInvariant({ ...canonical, tier: "Enterprise" }),
    "Tier drift must fail closed.",
  );
  assert(
    !hasCanonicalMasterAdminInvariant({ ...canonical, active: false }),
    "Inactive admin must fail closed.",
  );
  assert(
    !hasCanonicalMasterAdminInvariant({ ...canonical, role: "User" }),
    "Role drift must fail closed.",
  );
  assert(
    !hasCanonicalMasterAdminInvariant({
      ...canonical,
      subscription_expires_at: "2098-01-01T00:00:00Z",
    }),
    "Expiry drift must fail closed.",
  );
});

Deno.test("production v9 rejects malformed, oversized and non-object request bodies", async () => {
  const normal = await readBoundedJsonObject(
    new Request("https://example.test", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "health", value: 1 }),
    }),
  );
  assert(normal.action === "health", "Normal JSON objects must parse.");

  for (const body of ["{", "null", "[]", '"string"', "1"]) {
    let caught: unknown;
    try {
      await readBoundedJsonObject(
        new Request("https://example.test", { method: "POST", body }),
      );
    } catch (error) {
      caught = error;
    }
    assert(
      caught instanceof PublicRequestError,
      "Invalid JSON shape must be rejected.",
    );
    assert(caught.status === 400, "Invalid JSON shape must return HTTP 400.");
  }

  let lengthError: unknown;
  try {
    await readBoundedJsonObject(
      new Request("https://example.test", {
        method: "POST",
        headers: { "content-length": "200" },
        body: '{"ok":true}',
      }),
      32,
    );
  } catch (error) {
    lengthError = error;
  }
  assert(
    lengthError instanceof PublicRequestError,
    "Oversized declared length must be rejected.",
  );
  assert(
    lengthError.status === 413,
    "Oversized declared length must return HTTP 413.",
  );

  let streamedError: unknown;
  try {
    await readBoundedJsonObject(
      new Request("https://example.test", {
        method: "POST",
        body: JSON.stringify({ data: "x".repeat(200) }),
      }),
      32,
    );
  } catch (error) {
    streamedError = error;
  }
  assert(
    streamedError instanceof PublicRequestError,
    "Actual stream bytes must be bounded.",
  );
  assert(
    streamedError.status === 413,
    "Oversized stream must return HTTP 413.",
  );
});

Deno.test("production v9 validates workspace JSON before persistence replacement", () => {
  assert(
    normalizeWorkspaceStateJson({ selected: "Dashboard" }) ===
      '{"selected":"Dashboard"}',
    "Object workspace state must normalize.",
  );
  assert(
    normalizeWorkspaceStateJson(null) === "{}",
    "Missing workspace state must remain recoverable.",
  );

  for (const value of ["{", "null", "[]", 5]) {
    let caught: unknown;
    try {
      normalizeWorkspaceStateJson(value);
    } catch (error) {
      caught = error;
    }
    assert(
      caught instanceof PublicRequestError,
      "Invalid workspace state must be rejected.",
    );
    assert(
      caught.status === 400,
      "Invalid workspace state must return HTTP 400.",
    );
  }

  let oversized: unknown;
  try {
    normalizeWorkspaceStateJson({ data: "x".repeat(128) }, 64);
  } catch (error) {
    oversized = error;
  }
  assert(
    oversized instanceof PublicRequestError,
    "Oversized workspace state must be rejected.",
  );
  assert(
    oversized.status === 413,
    "Oversized workspace state must return HTTP 413.",
  );
});
