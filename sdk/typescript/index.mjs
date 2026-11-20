const API_VERSION = "v1";
const MAX_REQUEST_BYTES = 1024 * 1024;
const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 15_000;
const API_PATH = "/functions/v1/shoir-persistence";

function requiredText(value, field, maximum = 4096) {
  if (typeof value !== "string" || !value.trim() || value.length > maximum ||
      /[\x00-\x1f\x7f]/.test(value)) {
    throw new TypeError(field + " is missing or invalid.");
  }
  return value.trim();
}

function validateEndpoint(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new TypeError("edgeUrl must be a valid HTTPS Supabase function URL.");
  }
  const match = /^([a-z0-9]{20})\.supabase\.co$/i.exec(url.hostname);
  if (url.protocol !== "https:" || !match || url.pathname !== API_PATH ||
      url.username || url.password || url.search || url.hash || url.port) {
    throw new TypeError("edgeUrl must be the exact HTTPS Supabase shoir-persistence function endpoint.");
  }
  return url.toString();
}

function finiteInteger(value, field, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new TypeError(field + " must be an integer between " + minimum + " and " + maximum + ".");
  }
  return value;
}

async function readBoundedJsonResponse(response) {
  const contentLength = response.headers?.get?.("content-length");
  if (contentLength !== null && contentLength !== undefined && String(contentLength).trim()) {
    if (!/^[0-9]+$/.test(String(contentLength).trim())) {
      throw new TypeError("The Shoir-IE API returned an invalid response length.");
    }
    if (Number(contentLength) > MAX_RESPONSE_BYTES) {
      throw new RangeError("The Shoir-IE API response exceeds the 2 MiB SDK limit.");
    }
  }

  const reader = response.body?.getReader?.();
  if (reader) {
    const chunks = [];
    let total = 0;
    try {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        if (!(part.value instanceof Uint8Array)) {
          throw new TypeError("The Shoir-IE API returned an invalid response stream.");
        }
        total += part.value.byteLength;
        if (total > MAX_RESPONSE_BYTES) {
          try { await reader.cancel(); } catch { /* Preserve the size bound. */ }
          throw new RangeError("The Shoir-IE API response exceeds the 2 MiB SDK limit.");
        }
        chunks.push(part.value);
      }
    } catch (error) {
      try { await reader.cancel(); } catch { /* Preserve the original failure. */ }
      throw error;
    }
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    try {
      return JSON.parse(text);
    } catch {
      throw new TypeError("The Shoir-IE API returned malformed JSON.");
    }
  }

  if (typeof response.text === "function") {
    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) {
      throw new RangeError("The Shoir-IE API response exceeds the 2 MiB SDK limit.");
    }
    try {
      return JSON.parse(text);
    } catch {
      throw new TypeError("The Shoir-IE API returned malformed JSON.");
    }
  }

  // Compatibility for test doubles and fetch-compatible runtimes without a
  // readable stream. Standard browser and Node fetch responses use streaming.
  if (typeof response.json === "function") {
    const data = await response.json();
    let serialized;
    try {
      serialized = JSON.stringify(data);
    } catch {
      throw new TypeError("The Shoir-IE API returned an invalid JSON value.");
    }
    if (new TextEncoder().encode(serialized ?? "").byteLength > MAX_RESPONSE_BYTES) {
      throw new RangeError("The Shoir-IE API response exceeds the 2 MiB SDK limit.");
    }
    return data;
  }
  throw new TypeError("The Shoir-IE API returned no readable response body.");
}

export class ShoirIEApiError extends Error {
  constructor(message, status, code = "API_ERROR") {
    super(message);
    this.name = "ShoirIEApiError";
    this.status = status;
    this.code = code;
  }
}

/** Session-scoped beta client. The user session token is never logged or persisted by this SDK. */
export class ShoirIEClient {
  constructor({ edgeUrl, publishableKey, username, sessionToken, timeoutMs = DEFAULT_TIMEOUT_MS, fetchImpl = globalThis.fetch }) {
    this.edgeUrl = validateEndpoint(requiredText(edgeUrl, "edgeUrl", 2048));
    this.publishableKey = requiredText(publishableKey, "publishableKey", 1024);
    this.username = requiredText(username, "username", 120);
    this.sessionToken = requiredText(sessionToken, "sessionToken", 4096);
    this.timeoutMs = finiteInteger(timeoutMs, "timeoutMs", 1_000, 30_000);
    if (typeof fetchImpl !== "function") {
      throw new TypeError("fetchImpl must be a fetch-compatible function.");
    }
    this.fetchImpl = fetchImpl;
  }

  async _call(action, parameters = {}) {
    const body = {
      ...parameters,
      api_version: API_VERSION,
      action,
      username: this.username,
      token: this.sessionToken
    };
    let serialized;
    try {
      serialized = JSON.stringify(body);
    } catch {
      throw new TypeError("Request payload must be JSON serializable.");
    }
    if (new TextEncoder().encode(serialized).byteLength > MAX_REQUEST_BYTES) {
      throw new RangeError("Request payload exceeds the 1 MiB SDK limit.");
    }
    let response;
    try {
      response = await this.fetchImpl(this.edgeUrl, {
        method: "POST",
        redirect: "error",
        cache: "no-store",
        credentials: "omit",
        headers: {
          "apikey": this.publishableKey,
          "Authorization": "Bearer " + this.publishableKey,
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        body: serialized,
        signal: AbortSignal.timeout(this.timeoutMs)
      });
    } catch (error) {
      if (error?.name === "TimeoutError" || error?.name === "AbortError") {
        throw new ShoirIEApiError("The Shoir-IE API request timed out.", 0, "TIMEOUT");
      }
      throw new ShoirIEApiError("The Shoir-IE API request failed before a response was received.", 0, "TRANSPORT_ERROR");
    }
    let data;
    try {
      data = await readBoundedJsonResponse(response);
    } catch (error) {
      if (error instanceof RangeError) {
        throw new ShoirIEApiError("The Shoir-IE API response exceeds the SDK size limit.", response.status, "RESPONSE_TOO_LARGE");
      }
      throw new ShoirIEApiError("The Shoir-IE API returned an invalid JSON response.", response.status, "INVALID_RESPONSE");
    }
    if (!response.ok || !data || typeof data !== "object" || data.error) {
      const message = typeof data?.error === "string" ? data.error.slice(0, 240) : "The Shoir-IE API rejected the request.";
      throw new ShoirIEApiError(message, response.status, "API_ERROR");
    }
    return data;
  }

  async listPlatformRecords({ recordType, entityKey, limit = 100, offset = 0, organizationId, organizationWorkspaceId } = {}) {
    const pageSize = finiteInteger(limit, "limit", 1, 200);
    const pageOffset = finiteInteger(offset, "offset", 0, 100000);
    const parameters = { limit: pageSize, offset: pageOffset };
    if (recordType !== undefined) parameters.record_type = requiredText(recordType, "recordType", 80);
    if (entityKey !== undefined) parameters.entity_key = requiredText(entityKey, "entityKey", 240);
    if (organizationId !== undefined) parameters.organization_id = requiredText(organizationId, "organizationId", 120);
    if (organizationWorkspaceId !== undefined) parameters.organization_workspace_id = requiredText(organizationWorkspaceId, "organizationWorkspaceId", 120);
    if (Boolean(parameters.organization_id) !== Boolean(parameters.organization_workspace_id)) {
      throw new TypeError("organizationId and organizationWorkspaceId must be supplied together.");
    }
    return this._call("platform_record_list", parameters);
  }

  async savePlatformRecord({ recordType, entityKey, payload, organizationId, organizationWorkspaceId } = {}) {
    const parameters = {
      record_type: requiredText(recordType, "recordType", 80),
      entity_key: requiredText(entityKey, "entityKey", 240),
      payload
    };
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new TypeError("payload must be a JSON object.");
    }
    if (organizationId !== undefined) parameters.organization_id = requiredText(organizationId, "organizationId", 120);
    if (organizationWorkspaceId !== undefined) parameters.organization_workspace_id = requiredText(organizationWorkspaceId, "organizationWorkspaceId", 120);
    if (Boolean(parameters.organization_id) !== Boolean(parameters.organization_workspace_id)) {
      throw new TypeError("organizationId and organizationWorkspaceId must be supplied together.");
    }
    return this._call("platform_record_save", parameters);
  }

  async loadWorkspace({ workspace = "default", organizationId, organizationWorkspaceId } = {}) {
    const parameters = { workspace: requiredText(workspace, "workspace", 120) };
    if (organizationId !== undefined) parameters.organization_id = requiredText(organizationId, "organizationId", 120);
    if (organizationWorkspaceId !== undefined) parameters.organization_workspace_id = requiredText(organizationWorkspaceId, "organizationWorkspaceId", 120);
    if (Boolean(parameters.organization_id) !== Boolean(parameters.organization_workspace_id)) {
      throw new TypeError("organizationId and organizationWorkspaceId must be supplied together.");
    }
    return this._call("workspace_load", parameters);
  }
}

export const SHOIR_IE_API_VERSION = API_VERSION;
