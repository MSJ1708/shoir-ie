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

/** Check that exactly one active Enterprise Admin exists and is the canonical reserved administrator. */
export function hasExactlyOneCanonicalMasterAdmin(
  activeEnterpriseAdmins: unknown,
): boolean {
  return Array.isArray(activeEnterpriseAdmins) &&
    activeEnterpriseAdmins.length === 1 &&
    hasCanonicalMasterAdminInvariant(
      activeEnterpriseAdmins[0] as Record<string, unknown>,
    );
}

export const MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024;

export class PublicRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "PublicRequestError";
    this.status = status;
  }
}

/**
 * Read a bounded JSON object. Content-Length is an early rejection hint only;
 * the stream is independently counted because that header is untrusted.
 */
export async function readBoundedJsonObject(
  request: Request,
  maxBytes = MAX_REQUEST_BODY_BYTES,
): Promise<Record<string, unknown>> {
  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null) {
    if (!/^\d+$/.test(declaredLength)) {
      throw new PublicRequestError("Invalid Content-Length header.", 400);
    }
    if (Number(declaredLength) > maxBytes) {
      throw new PublicRequestError(
        "Request body exceeds the allowed size limit.",
        413,
      );
    }
  }

  const reader = request.body?.getReader();
  if (!reader) {
    throw new PublicRequestError("A JSON request body is required.", 400);
  }

  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      totalBytes += value.byteLength;
      if (totalBytes > maxBytes) {
        try {
          await reader.cancel("Request body size limit exceeded.");
        } catch {
          // Cancellation is best effort; never continue buffering the request.
        }
        throw new PublicRequestError(
          "Request body exceeds the allowed size limit.",
          413,
        );
      }
      chunks.push(value);
    }
  } catch (error) {
    if (error instanceof PublicRequestError) throw error;
    throw new PublicRequestError("Request body could not be read.", 400);
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // A reader can already be released by a runtime after cancellation.
    }
  }

  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(bytes),
    );
  } catch {
    throw new PublicRequestError("Request body must be valid UTF-8 JSON.", 400);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new PublicRequestError("Request body must be a JSON object.", 400);
  }
  return parsed as Record<string, unknown>;
}
