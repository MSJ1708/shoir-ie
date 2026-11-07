/** Production v9 CORS allowlist and reserved-administrator invariant. */

export const MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024;
export const MAX_WORKSPACE_STATE_BYTES = 8 * 1024 * 1024;

export class PublicRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "PublicRequestError";
    this.status = status;
  }
}

/** Read a bounded JSON object; count the streamed bytes independently of Content-Length. */
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
          // Cancellation is best effort; the oversized body is already rejected.
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
      // The runtime may already have released a cancelled stream.
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

/** Validate workspace state and its byte count before a row is replaced. */
export function normalizeWorkspaceStateJson(
  value: unknown,
  maxBytes = MAX_WORKSPACE_STATE_BYTES,
): string {
  let serialized: string;
  if (typeof value === "string") {
    serialized = value.trim() ? value : "{}";
  } else if (value === undefined || value === null) {
    serialized = "{}";
  } else {
    try {
      const encoded = JSON.stringify(value);
      if (typeof encoded !== "string") {
        throw new PublicRequestError(
          "Workspace state must be JSON serializable.",
          400,
        );
      }
      serialized = encoded;
    } catch (error) {
      if (error instanceof PublicRequestError) throw error;
      throw new PublicRequestError(
        "Workspace state must be JSON serializable.",
        400,
      );
    }
  }
  if (new TextEncoder().encode(serialized).byteLength > maxBytes) {
    throw new PublicRequestError(
      "Workspace state exceeds the allowed size limit.",
      413,
    );
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(serialized);
  } catch {
    throw new PublicRequestError("Workspace state must be valid JSON.", 400);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new PublicRequestError("Workspace state must be a JSON object.", 400);
  }
  return serialized;
}
const BROWSER_ORIGINS_BY_PROJECT: Readonly<
  Record<string, ReadonlySet<string>>
> = {
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

/** Only POST may dispatch API actions; OPTIONS is handled by the HTTP boundary. */
export function isAllowedApiMethod(method: string): boolean {
  return method.toUpperCase() === "POST";
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
