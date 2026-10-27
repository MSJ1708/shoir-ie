/** Bounded request parsing and safe error mapping for the Shoir-IE persistence Edge Function. */

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

/** Validate saved workspace JSON before replacing the prior persisted state. */
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

/**
 * Validate the protected master-administrator invariant without mutating the account.
 * Use this only for the reserved administrator identity before issuing a session.
 */
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

  // Do not return database, storage, or infrastructure error details to callers.
  return {
    status: 500,
    message:
      "The persistence service could not complete this request. Retry later.",
  };
}
