/** Production v9 CORS allowlist and reserved-administrator invariant. */

const BROWSER_ORIGINS_BY_PROJECT: Readonly<Record<string, ReadonlySet<string>>> = {
  gcsamrdaeraxieaagsta: new Set([
    "https://shoir-ie-app.streamlit.app",
  ]),
};

function supabaseProjectRef(projectUrl: string): string | null {
  try {
    const parsed = new URL(projectUrl);
    if (
      parsed.protocol !== "https:" || parsed.port !== "" ||
      parsed.username !== "" || parsed.password !== "" ||
      parsed.pathname !== "/" || parsed.search !== "" || parsed.hash !== ""
    ) {
      return null;
    }
    const match = parsed.hostname.match(/^([a-z0-9-]+)\.supabase\.co$/i);
    return match ? match[1].toLowerCase() : null;
  } catch {
    return null;
  }
}

/** Missing Origin is reserved for server-to-server clients, which still need session auth. */
export function isAllowedBrowserOrigin(
  origin: string | null,
  projectUrl: string,
): boolean {
  if (origin === null) return true;
  const ref = supabaseProjectRef(projectUrl);
  if (!ref) return false;
  return BROWSER_ORIGINS_BY_PROJECT[ref]?.has(origin) ?? false;
}

/** Never use wildcard CORS. Unknown projects/origins receive no ACAO header. */
export function corsHeadersForOrigin(
  origin: string | null,
  projectUrl: string,
): Headers {
  const headers = new Headers({
    "Content-Type": "application/json",
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, apikey, content-type, x-retry-count, traceparent, tracestate, baggage",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  });
  if (origin !== null && isAllowedBrowserOrigin(origin, projectUrl)) {
    headers.set("Access-Control-Allow-Origin", origin);
  }
  return headers;
}

/** Check the immutable reserved account record; this function has no write path. */
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
