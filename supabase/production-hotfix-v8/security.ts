/** Minimal security helpers for an exact-schema production v8 hotfix. */
// This candidate is specifically for production. Do not permit staging or local
// development browser origins to call the production API.
const ALLOWED_BROWSER_ORIGINS = new Set<string>([
  "https://shoir-ie-app.streamlit.app",
]);

/** Browser origins must match exactly; missing Origin remains available for server-to-server calls. */
export function isAllowedBrowserOrigin(origin: string | null): boolean {
  return origin === null || ALLOWED_BROWSER_ORIGINS.has(origin);
}

/** No wildcard CORS is emitted. Unapproved origins are rejected before response paths reach this helper. */
export function corsHeadersForOrigin(origin: string | null): Headers {
  const headers = new Headers({
    "Content-Type": "application/json",
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  });
  if (origin !== null && ALLOWED_BROWSER_ORIGINS.has(origin)) {
    headers.set("Access-Control-Allow-Origin", origin);
  }
  return headers;
}

/** Read-only invariant check for the reserved administrator; never repairs the row. */
export function hasCanonicalMasterAdminInvariant(
  account: Record<string, unknown>,
): boolean {
  const expectedExpiry = Date.parse("2099-01-01T00:00:00Z");
  const actualExpiry = typeof account.subscription_expires_at === "string"
    ? Date.parse(account.subscription_expires_at)
    : Number.NaN;
  return account.username_lc === "sho" &&
    account.role === "Enterprise Admin" &&
    account.tier === "Enterprise Plus Tier ($399)" &&
    account.active === true &&
    Number.isFinite(actualExpiry) &&
    actualExpiry === expectedExpiry;
}
