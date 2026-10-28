/** Minimal security helpers for the production-v9-compatible security candidate. */
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


/** A subscription approval must never mutate the reserved administrator account. */
export function isProtectedAdministratorTarget(
  request: Record<string, unknown>,
  existingAccount: Record<string, unknown> | null | undefined,
  pendingCredential: Record<string, unknown> | null | undefined,
): boolean {
  return request.username_lc === "sho" ||
    existingAccount?.username_lc === "sho" ||
    existingAccount?.role === "Enterprise Admin" ||
    pendingCredential?.username_lc === "sho";
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

export function publicErrorFor(
  error: unknown,
): { status: number; message: string } {
  if (error instanceof PublicRequestError) {
    return { status: error.status, message: error.message };
  }

  const message = error instanceof Error ? error.message : "";
  if (message === "Unauthorized session.") {
    return { status: 401, message: "Unauthorized session." };
  }
  if (message === "Session scope does not permit this action.") {
    return { status: 403, message };
  }
  if (message === "Account is inactive.") {
    return { status: 403, message };
  }
  if (message === "Admin authorization failed.") {
    return { status: 403, message };
  }
  if (message === "SUBSCRIPTION_EXPIRED") {
    return { status: 403, message: "SUBSCRIPTION_EXPIRED" };
  }
  if (
    message === "Authentication protection is temporarily unavailable." ||
    message ===
      "Registration request could not be confirmed by the persistence service."
  ) {
    return { status: 503, message };
  }

  const inputErrors = new Set([
    "Payment proof is empty or exceeds the 512 KiB limit.",
    "Payment proof is not valid base64 data.",
    "Payment proof exceeds the 512 KiB limit.",
    "Payment proof data or content type is invalid.",
    "Payment proof must be PNG, JPG, JPEG or PDF.",
    "Payment proof content does not match its declared file type.",
  ]);
  if (inputErrors.has(message)) return { status: 400, message };

  return {
    status: 500,
    message:
      "The persistence service could not complete this request. Retry later.",
  };
}
