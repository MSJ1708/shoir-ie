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
 * Browser origins are bound to the Supabase project, not shared between
 * staging and production. Keep these exact origins aligned with the
 * corresponding Streamlit deployment. The Python server-to-server caller
 * normally sends no Origin header; it remains subject to action authentication.
 */
const BROWSER_ORIGINS_BY_PROJECT: Readonly<
  Record<string, ReadonlySet<string>>
> = {
  hfhrosthswcybccepmak: new Set([
    "https://shoirieverified.streamlit.app",
    "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
    "http://127.0.0.1:8501",
    "http://localhost:8501",
  ]),
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

/** Missing Origin is allowed only for non-browser server-to-server clients. */
export function isAllowedBrowserOrigin(
  origin: string | null,
  projectUrl: string,
): boolean {
  if (origin === null) return true;
  const projectRef = supabaseProjectRef(projectUrl);
  if (!projectRef) return false;
  return BROWSER_ORIGINS_BY_PROJECT[projectRef]?.has(origin) ?? false;
}

/**
 * Return project-bound CORS headers. Never emit wildcard or cross-environment
 * origins; the request handler rejects non-allowlisted Origin values first.
 */
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

/**
 * Existing account codes may be normalized for ordinary users, but the
 * reserved administrator is never mutated as a side effect of login or
 * referral-summary reads. Any repair of its metadata is a reviewed operation.
 */
export function shouldAutoAssignReferralCode(
  usernameLc: string,
  referralCode: string,
): boolean {
  if (usernameLc.trim().toLowerCase() === "sho") return false;
  return !referralCode || referralCode.startsWith("AFF-");
}

/**
 * Validate the reserved master-administrator invariant without mutating the
 * account. Any discrepancy must fail closed and be corrected through a reviewed
 * operational procedure rather than as a side effect of login.
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

/**
 * Return only safe subscription fields after the caller's opaque workspace
 * session has already been revalidated by getSession().
 */
export function sessionEntitlementFields(
  account: Record<string, unknown>,
): {
  username: string;
  tier: string;
  active: true;
  expires_at: string;
} {
  const username = typeof account.username === "string"
    ? account.username.trim()
    : "";
  const tier = typeof account.tier === "string" ? account.tier.trim() : "";
  const expiresAt = typeof account.subscription_expires_at === "string"
    ? account.subscription_expires_at.trim()
    : "";
  const expiryTime = Date.parse(expiresAt);

  if (
    !username ||
    !tier ||
    account.active !== true ||
    !expiresAt ||
    !Number.isFinite(expiryTime) ||
    expiryTime <= Date.now()
  ) {
    throw new PublicRequestError(
      "Subscription entitlement could not be verified.",
      403,
    );
  }

  return {
    username,
    tier,
    active: true,
    expires_at: expiresAt,
  };
}

/**
 * Match the application's package normalization rules at the API boundary.
 * Research Pack is an add-on access state, not the Enterprise Plus tier.
 */
export function normalizePlatformTier(value: unknown): string {
  const tier = String(value || "Starter").trim().toLowerCase();
  if (tier.includes("research")) return "Research Pack";
  if (
    tier.includes("enterprise plus") || tier.includes("industrial enterprise")
  ) {
    return "Enterprise Plus";
  }
  if (tier.includes("enterprise")) return "Enterprise";
  if (tier.includes("professional")) return "Professional";
  if (tier.includes("pro")) return "Mid-Tier Pro";
  return "Starter";
}

export function platformTierAllows(
  currentValue: unknown,
  requiredValue: string,
): boolean {
  const current = normalizePlatformTier(currentValue);
  const required = normalizePlatformTier(requiredValue);
  const order = [
    "Starter",
    "Mid-Tier Pro",
    "Professional",
    "Enterprise",
    "Enterprise Plus",
  ];
  if (current === "Research Pack") {
    return [
      "Starter",
      "Mid-Tier Pro",
      "Professional",
      "Enterprise",
      "Research Pack",
    ].includes(required);
  }
  if (required === "Research Pack") return current === "Research Pack";
  return order.indexOf(current) >= order.indexOf(required);
}

export interface CsvShape {
  rowCount: number;
  columnCount: number;
  headers: string[];
}

/**
 * Inspect an already size-bounded UTF-8 CSV without materializing a DataFrame.
 * Counts logical records (quoted newlines are not row separators) and rejects
 * malformed quoting, duplicate/blank headers and invalid UTF-8.
 */
export function inspectCsvShape(bytes: Uint8Array): CsvShape {
  let source: string;
  try {
    source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new PublicRequestError("Dataset CSV must be valid UTF-8.", 400);
  }
  if (source.startsWith("\uFEFF")) source = source.slice(1);
  if (!source.length) {
    throw new PublicRequestError("Dataset CSV is empty.", 400);
  }

  const headers: string[] = [];
  let field = "";
  let fieldHasContent = false;
  let inQuotes = false;
  let firstRecord = true;
  let rowCount = 0;
  let recordHasContent = false;
  let columnCount = 0;

  const finishHeader = () => {
    headers.push(field);
    if (headers.some((header) => !header.trim())) {
      throw new PublicRequestError(
        "Dataset CSV contains a blank column header.",
        400,
      );
    }
    if (new Set(headers).size !== headers.length) {
      throw new PublicRequestError(
        "Dataset CSV contains duplicate column headers.",
        400,
      );
    }
    columnCount = headers.length;
    firstRecord = false;
  };

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (inQuotes) {
      if (character === '"') {
        if (source[index + 1] === '"') {
          if (firstRecord) field += '"';
          index += 1;
        } else {
          inQuotes = false;
        }
      } else if (firstRecord) {
        field += character;
      }
      fieldHasContent = true;
      recordHasContent = true;
      continue;
    }

    if (character === '"') {
      if (fieldHasContent) {
        throw new PublicRequestError(
          "Dataset CSV contains an invalid quote.",
          400,
        );
      }
      inQuotes = true;
      fieldHasContent = true;
      recordHasContent = true;
      continue;
    }
    if (character === ",") {
      if (firstRecord) headers.push(field);
      field = "";
      fieldHasContent = false;
      recordHasContent = true;
      continue;
    }
    if (character === "\n" || character === "\r") {
      if (firstRecord) {
        finishHeader();
      } else if (recordHasContent) {
        rowCount += 1;
      }
      field = "";
      fieldHasContent = false;
      recordHasContent = false;
      if (character === "\r" && source[index + 1] === "\n") {
        index += 1;
      }
      continue;
    }
    if (firstRecord) field += character;
    fieldHasContent = true;
    recordHasContent = true;
  }

  if (inQuotes) {
    throw new PublicRequestError(
      "Dataset CSV contains an unterminated quoted field.",
      400,
    );
  }
  if (firstRecord) {
    finishHeader();
  } else if (recordHasContent) {
    rowCount += 1;
  }

  if (columnCount < 1) {
    throw new PublicRequestError(
      "Dataset CSV must contain at least one column.",
      400,
    );
  }
  return { rowCount, columnCount, headers };
}

/** Only POST may dispatch API actions; OPTIONS is handled by the HTTP boundary. */
export function isAllowedApiMethod(method: string): boolean {
  return method.toUpperCase() === "POST";
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
  if (message === "Administrator account requires manual security review.") {
    return { status: 503, message };
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
