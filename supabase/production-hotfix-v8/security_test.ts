import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  isAllowedBrowserOrigin,
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
