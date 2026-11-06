import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  isAllowedBrowserOrigin,
} from "./security.ts";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

Deno.test("production v9 CORS allows only the exact production app origin", () => {
  const projectUrl = "https://gcsamrdaeraxieaagsta.supabase.co";
  const allowed = "https://shoir-ie-app.streamlit.app";
  assert(isAllowedBrowserOrigin(allowed, projectUrl), "Production app must be allowed.");
  assert(isAllowedBrowserOrigin(null, projectUrl), "Server-to-server callers must remain possible.");
  for (const origin of [
    "https://shoirieverified.streamlit.app",
    "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
    "https://attacker.example",
    "https://shoir-ie-app.streamlit.app.evil.test",
    "http://shoir-ie-app.streamlit.app",
  ]) {
    assert(!isAllowedBrowserOrigin(origin, projectUrl), `Unexpected allowed origin: ${origin}`);
  }
  assert(!isAllowedBrowserOrigin(allowed, "https://unknown.supabase.co"),
    "Unknown Supabase project must fail closed.");
  const headers = corsHeadersForOrigin(allowed, projectUrl);
  assert(headers.get("Access-Control-Allow-Origin") === allowed,
    "Allowed origin must be echoed exactly.");
  assert(headers.get("Vary") === "Origin", "Vary: Origin is required.");
  const denied = corsHeadersForOrigin("https://attacker.example", projectUrl);
  assert(denied.get("Access-Control-Allow-Origin") === null,
    "Denied origins must not get ACAO.");
  assert(!headers.get("Access-Control-Allow-Headers")?.includes("*"),
    "Wildcard request-header policy is not allowed.");
});

Deno.test("reserved administrator invariant is exact and side-effect free", () => {
  const canonical = Object.freeze({
    username_lc: "sho",
    role: "Enterprise Admin",
    tier: "Enterprise Plus Tier ($399)",
    active: true,
    subscription_expires_at: "2099-01-01T00:00:00Z",
  });
  assert(hasCanonicalMasterAdminInvariant(canonical), "Canonical admin must pass.");
  assert(canonical.tier === "Enterprise Plus Tier ($399)",
    "Invariant check must not mutate the account.");
  assert(!hasCanonicalMasterAdminInvariant({...canonical, tier: "Enterprise"}),
    "Tier drift must fail closed.");
  assert(!hasCanonicalMasterAdminInvariant({...canonical, active: false}),
    "Inactive admin must fail closed.");
  assert(!hasCanonicalMasterAdminInvariant({...canonical, role: "User"}),
    "Role drift must fail closed.");
  assert(!hasCanonicalMasterAdminInvariant({...canonical, subscription_expires_at: "2098-01-01T00:00:00Z"}),
    "Expiry drift must fail closed.");
});
