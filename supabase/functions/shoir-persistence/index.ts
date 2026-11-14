import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";
import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  inspectCsvShape,
  isAllowedApiMethod,
  isAllowedBrowserOrigin,
  normalizeWorkspaceStateJson,
  platformTierAllows,
  publicErrorFor,
  readBoundedJsonObject,
  sessionEntitlementFields,
  shouldAutoAssignReferralCode,
} from "./security.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);
const ITERATIONS = 200_000;
const PAYMENT_PROOF_BUCKET = "subscription-payment-proofs";
const MAX_PAYMENT_PROOF_BYTES = 512 * 1024;
const TERMS_VERSION = "2026-10-21-beta-v1";
const PRIVACY_POLICY_VERSION = "2026-10-21-v1";
const REFUND_POLICY_VERSION = "2026-10-23-v2";
const COOKIE_POLICY_VERSION = "2026-10-21-v1";
// Keep these values aligned with the public notices and the matching SQL migration.

async function ensurePaymentProofBucket() {
  const { data, error } = await supabase.storage.getBucket(
    PAYMENT_PROOF_BUCKET,
  );
  if (!error && data) {
    if ((data as { public?: boolean }).public === true) {
      throw new Error("Payment proof storage bucket must remain private.");
    }
    return;
  }
  const { error: createError } = await supabase.storage.createBucket(
    PAYMENT_PROOF_BUCKET,
    {
      public: false,
      fileSizeLimit: "512KB",
      allowedMimeTypes: ["image/png", "image/jpeg", "application/pdf"],
    },
  );
  if (createError) {
    const { data: retry, error: retryError } = await supabase.storage.getBucket(
      PAYMENT_PROOF_BUCKET,
    );
    if (
      retryError || !retry || (retry as { public?: boolean }).public === true
    ) throw createError;
  }
}

function decodePaymentProof(base64Value: string) {
  const compact = base64Value.replace(/^data:[^;]+;base64,/i, "").replace(
    /\s+/g,
    "",
  );
  if (
    !compact || compact.length > Math.ceil(MAX_PAYMENT_PROOF_BYTES * 4 / 3) + 8
  ) {
    throw new Error("Payment proof is empty or exceeds the 512 KiB limit.");
  }
  let binary: string;
  try {
    binary = atob(compact);
  } catch {
    throw new Error("Payment proof is not valid base64 data.");
  }
  if (binary.length > MAX_PAYMENT_PROOF_BYTES) {
    throw new Error("Payment proof exceeds the 512 KiB limit.");
  }
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function storePaymentProof(
  body: Record<string, unknown>,
): Promise<string | null> {
  const encoded = String(body.proof_base64 || "").trim();
  const rawContentType = String(body.proof_content_type || "").trim()
    .toLowerCase();
  if (!encoded && !rawContentType) return null;
  if (!encoded || !rawContentType) {
    throw new Error("Payment proof data or content type is invalid.");
  }
  const contentType = rawContentType;
  const extensionByType: Record<string, string> = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "application/pdf": "pdf",
  };
  const extension = extensionByType[contentType];
  if (!extension) {
    throw new Error("Payment proof must be PNG, JPG, JPEG or PDF.");
  }
  const bytes = decodePaymentProof(encoded);
  const validSignature = contentType === "application/pdf"
    ? new TextDecoder().decode(bytes.slice(0, 5)) === "%PDF-"
    : contentType === "image/png"
    ? bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 &&
      bytes[2] === 0x4e && bytes[3] === 0x47 &&
      bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a &&
      bytes[7] === 0x0a
    : bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 &&
      bytes[2] === 0xff;
  if (!validSignature) {
    throw new Error(
      "Payment proof content does not match its declared file type.",
    );
  }
  await ensurePaymentProofBucket();
  const objectPath = `renewals/${crypto.randomUUID()}.${extension}`;
  const { error } = await supabase.storage.from(PAYMENT_PROOF_BUCKET).upload(
    objectPath,
    bytes,
    {
      contentType,
      cacheControl: "300",
      upsert: false,
    },
  );
  if (error) throw error;
  return `storage://${PAYMENT_PROOF_BUCKET}/${objectPath}`;
}

function response(
  data: unknown,
  status = 200,
  origin: string | null = null,
) {
  return new Response(JSON.stringify(data), {
    status,
    headers: corsHeadersForOrigin(origin, SUPABASE_URL),
  });
}
function hexToBytes(hex: string) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}
function bytesToHex(bytes: ArrayBuffer | Uint8Array) {
  const u = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  return Array.from(u).map((b) => b.toString(16).padStart(2, "0")).join("");
}
async function pbkdf2(password: string, saltHex: string) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      hash: "SHA-256",
      salt: hexToBytes(saltHex),
      iterations: ITERATIONS,
    },
    key,
    256,
  );
  return bytesToHex(bits);
}
async function hashPassword(password: string) {
  const salt = new Uint8Array(16);
  crypto.getRandomValues(salt);
  const s = bytesToHex(salt);
  return s + "$" + await pbkdf2(password, s);
}
async function verifyPassword(stored: string, password: string) {
  if (!stored || !password || !stored.includes("$")) return false;
  const [salt, expected] = stored.split("$", 2);
  const actual = await pbkdf2(password, salt);
  if (actual.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < actual.length; i++) {
    diff |= actual.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return diff === 0;
}
function isExpired(v: string | null) {
  return !!v && new Date(v).getTime() <= Date.now();
}
function expiry30(base?: string | null) {
  const now = Date.now();
  const current = base ? new Date(base).getTime() : 0;
  return new Date(Math.max(now, current || 0) + 30 * 24 * 60 * 60 * 1000)
    .toISOString();
}
async function getAccount(username: string) {
  const { data, error } = await supabase.from("shoir_accounts").select("*").eq(
    "username_lc",
    username.trim().toLowerCase(),
  ).maybeSingle();
  if (error) throw error;
  return data;
}
async function createSession(
  usernameLc: string,
  scope: "workspace" | "renewal" = "workspace",
  ttlMs = 30 * 24 * 60 * 60 * 1000,
) {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  const token = bytesToHex(b);
  const h = bytesToHex(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)),
  );
  const { error } = await supabase.from("shoir_sessions").insert({
    token_hash: h,
    username_lc: usernameLc,
    scope,
    expires_at: new Date(Date.now() + ttlMs).toISOString(),
  });
  if (error) throw error;
  return token;
}
async function getSession(
  token: string,
  username?: string,
  requiredScope: "workspace" | "renewal" | "either" = "workspace",
) {
  const h = bytesToHex(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)),
  );
  const { data, error } = await supabase.from("shoir_sessions").select(
    "username_lc,expires_at,scope",
  ).eq("token_hash", h).maybeSingle();
  if (error || !data || isExpired(data.expires_at)) {
    throw new Error("Unauthorized session.");
  }
  if (username && data.username_lc !== username.trim().toLowerCase()) {
    throw new Error("Unauthorized session.");
  }
  const scope = data.scope || "workspace";
  if (requiredScope !== "either" && scope !== requiredScope) {
    throw new Error("Session scope does not permit this action.");
  }
  const row = await getAccount(data.username_lc);
  if (!row || row.active === false) throw new Error("Account is inactive.");
  // Re-check the immutable reserved-administrator invariant for every
  // already-issued session, not only at the moment of login.
  if (
    row.username_lc === "sho" &&
    !hasCanonicalMasterAdminInvariant(row)
  ) {
    throw new Error("Administrator account requires manual security review.");
  }
  if (
    requiredScope === "workspace" &&
    !(row.username_lc === "sho" && row.role === "Enterprise Admin") &&
    isExpired(row.subscription_expires_at)
  ) throw new Error("SUBSCRIPTION_EXPIRED");
  return row;
}
function datasetEntitlementDenied(row: Record<string, unknown>): boolean {
  return !platformTierAllows(row.tier, "Professional");
}

function datasetEntitlementDenial(
  row: Record<string, unknown>,
): {
  error: string;
  required_tier: string;
  current_tier: string;
} | null {
  if (!datasetEntitlementDenied(row)) return null;
  return {
    error: "FEATURE_REQUIRES_PROFESSIONAL",
    required_tier: "Professional",
    current_tier: String(row.tier || "Starter"),
  };
}

async function datasetEntitlementDenialForRequest(
  row: Record<string, unknown>,
  body: Record<string, unknown>,
): Promise<
  {
    error: string;
    required_tier: string;
    current_tier: string;
  } | null
> {
  const organizationId = String(body.organization_id || "").trim();
  const workspaceId = String(body.organization_workspace_id || "").trim();
  if (organizationId || workspaceId) {
    if (!organizationId || !workspaceId) {
      return {
        error: "ORGANIZATION_WORKSPACE_ACCESS_DENIED",
        required_tier: "Active Enterprise organization membership",
        current_tier: String(row.tier || "Starter"),
      };
    }
    try {
      await organizationForActor(String(row.username_lc || ""), organizationId);
      return null;
    } catch {
      return {
        error: "ORGANIZATION_WORKSPACE_ACCESS_DENIED",
        required_tier: "Active Enterprise organization membership",
        current_tier: String(row.tier || "Starter"),
      };
    }
  }
  return datasetEntitlementDenial(row);
}

async function adminSession(username: string, token: string) {
  const row = await getSession(token, username);
  if (row.username_lc !== "sho" || row.role !== "Enterprise Admin") {
    throw new Error("Admin authorization failed.");
  }
  return row;
}

async function loginThrottleKey(raw: string) {
  const hmacKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(SERVICE_ROLE_KEY),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "HMAC",
    hmacKey,
    new TextEncoder().encode(raw),
  );
  return bytesToHex(signature);
}
async function checkLoginThrottle(
  keyHash: string,
  maxAttempts: number,
  mode: "attempt" | "clear",
) {
  const { data, error } = await supabase.rpc("shoir_check_login_throttle", {
    p_key_hash: keyHash,
    p_mode: mode,
    p_max_attempts: maxAttempts,
    p_window_seconds: 600,
    p_block_seconds: 600,
  });
  if (error) {
    throw new Error("Authentication protection is temporarily unavailable.");
  }
  const result = data as { blocked?: boolean } | null;
  return Boolean(result?.blocked);
}
async function loginThrottleBuckets(usernameLc: string, req: Request) {
  const keys: Array<
    { key_hash: string; max_attempts: number; reset_on_success: boolean }
  > = [
    {
      key_hash: await loginThrottleKey("user:" + usernameLc),
      max_attempts: 8,
      reset_on_success: true,
    },
  ];
  // Trust only the reverse-proxy-populated Cloudflare IP header; never accept a
  // client-controlled X-Forwarded-For value as the source of an IP limit.
  const clientIp = String(req.headers.get("cf-connecting-ip") || "").trim();
  if (clientIp && clientIp.length <= 128) {
    keys.push({
      key_hash: await loginThrottleKey("ip:" + clientIp),
      max_attempts: 30,
      reset_on_success: false,
    });
  }
  return keys;
}

const PLATFORM_RECORD_TYPES = new Set([
  "asset",
  "dataset",
  "dataset_version",
  "process",
  "product",
  "material",
  "calculation",
  "kpi",
  "scenario",
  "recommendation",
  "decision",
  "project",
  "action",
  "document",
  "workbook",
  "model",
  "quality",
  "maintenance",
  "energy",
  "cost",
  "traceability",
  "risk",
  "workflow",
  "artifact",
  "canonical_entity",
  "canonical_relationship",
  "canonical_event",
  "twin_asset",
  "twin_snapshot",
  "twin_scenario",
  "connector_health",
  "job",
  "knowledge_document",
  "monitoring_event",
  "report_provenance",
  "security_policy",
  "connector_run",
  "connector_schedule",
  "collaboration_item",
  "monitoring_rule",
  "cost_baseline",
  "kpi_definition",
  "project_record",
  "work_order",
  "change_request",
  "risk_record",
  "traceability_record",
  "laboratory_sample",
  "procurement_record",
  "spare_part",
  "shutdown_package",
  "competency_record",
]);
const PLATFORM_SECRET_KEY =
  /(?:password|passwd|token|secret|api.?key|authorization|cookie|credential|private.?key|national.?id|passport|e.?mail|phone|mobile|birth|\bdob\b|street|postal.?address|home.?address|full.?name|first.?name|last.?name|username|employee.?id|person.?id)/i;
function validatePlatformPayload(
  value: unknown,
  depth = 0,
): Record<string, unknown> {
  if (
    !value || typeof value !== "object" || Array.isArray(value) || depth > 8
  ) {
    throw new Error("Platform payload must be a bounded JSON object.");
  }
  const encoded = JSON.stringify(value);
  if (new TextEncoder().encode(encoded).byteLength > 256 * 1024) {
    throw new Error("Platform payload exceeds the 256 KiB limit.");
  }
  const walk = (item: unknown, level: number): void => {
    if (level > 8) throw new Error("Platform payload nesting is too deep.");
    if (Array.isArray(item)) {
      if (item.length > 5000) {
        throw new Error("Platform payload contains too many items.");
      }
      for (const child of item) walk(child, level + 1);
    } else if (item && typeof item === "object") {
      for (
        const [key, child] of Object.entries(item as Record<string, unknown>)
      ) {
        if (PLATFORM_SECRET_KEY.test(key)) {
          throw new Error(
            "Credential or sensitive identifier fields are not accepted in platform records.",
          );
        }
        walk(child, level + 1);
      }
    } else if (typeof item === "number" && !Number.isFinite(item)) {
      throw new Error("Platform payload contains a non-finite number.");
    }
  };
  walk(value, depth);
  return value as Record<string, unknown>;
}
function stablePlatformJson(value: unknown): string {
  if (Array.isArray(value)) {
    return "[" + value.map(stablePlatformJson).join(",") + "]";
  }
  if (value && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return "{" + Object.keys(object).sort().map((key) =>
      JSON.stringify(key) + ":" + stablePlatformJson(object[key])
    ).join(",") + "}";
  }
  return JSON.stringify(value);
}
async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return bytesToHex(digest);
}

async function sha256Bytes(value: Uint8Array): Promise<string> {
  const bytes = new Uint8Array(value.byteLength);
  bytes.set(value);
  const digest = await crypto.subtle.digest(
    "SHA-256",
    bytes.buffer as ArrayBuffer,
  );
  return bytesToHex(digest);
}
async function platformWorkspaceKey(
  username: string,
  workspace: string,
): Promise<string> {
  const user = username.trim().toLowerCase();
  const scope = workspace.trim().toLowerCase();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$/.test(scope)) {
    throw new Error("Workspace identifier is invalid.");
  }
  return (await sha256Hex(user + "::" + scope)).slice(0, 32);
}

const ORGANIZATION_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function validatedOrganizationId(value: unknown): string {
  const id = String(value || "").trim();
  if (!ORGANIZATION_ID_PATTERN.test(id)) {
    throw new Error("Organization identifier is invalid.");
  }
  return id;
}

function requireOrganizationTier(row: Record<string, unknown>): void {
  if (!platformTierAllows(row.tier, "Enterprise")) {
    throw new Error(
      "Organization workspaces require an active Enterprise subscription.",
    );
  }
  if (
    row.active !== true ||
    isExpired(
      typeof row.subscription_expires_at === "string"
        ? row.subscription_expires_at
        : null,
    )
  ) {
    throw new Error(
      "The organization owner subscription is inactive or expired.",
    );
  }
}

async function organizationForActor(
  actor: string,
  organizationIdValue: unknown,
  requireManage = false,
): Promise<{ organization: Record<string, unknown>; role: string }> {
  const organizationId = validatedOrganizationId(organizationIdValue);
  const { data: organization, error: organizationError } = await supabase
    .from("shoir_organizations")
    .select("organization_id,display_name,org_type,owner_username_lc,status")
    .eq("organization_id", organizationId)
    .maybeSingle();
  if (organizationError) throw organizationError;
  if (!organization || organization.status !== "active") {
    throw new Error("Active organization was not found.");
  }
  const { data: membership, error: membershipError } = await supabase
    .from("shoir_organization_memberships")
    .select("role,status")
    .eq("organization_id", organizationId)
    .eq("username_lc", actor)
    .maybeSingle();
  if (membershipError) throw membershipError;
  if (!membership || membership.status !== "active") {
    throw new Error("Active organization membership is required.");
  }
  const role = String(membership.role || "");
  if (requireManage && !["owner", "admin"].includes(role)) {
    throw new Error("Organization management permission is required.");
  }
  if (organization.org_type === "team") {
    const owner = await getAccount(
      String(organization.owner_username_lc || ""),
    );
    if (!owner) throw new Error("Organization owner account was not found.");
    requireOrganizationTier(owner as Record<string, unknown>);
  }
  return { organization: organization as Record<string, unknown>, role };
}

async function resolveManagedWorkspaceKey(
  row: Record<string, unknown>,
  body: Record<string, unknown>,
  permission: "read" | "write" | "approve" | "manage",
): Promise<string> {
  const organizationId = String(body.organization_id || "").trim();
  const workspaceId = String(body.organization_workspace_id || "").trim();
  if (!organizationId && !workspaceId) {
    return await platformWorkspaceKey(
      String(row.username_lc || ""),
      String(body.workspace || "default"),
    );
  }
  if (!organizationId || !workspaceId) {
    throw new Error(
      "Both organization_id and organization_workspace_id are required.",
    );
  }
  const organization = await organizationForActor(
    String(row.username_lc || ""),
    organizationId,
  );
  if (!ORGANIZATION_ID_PATTERN.test(workspaceId)) {
    throw new Error("Organization workspace identifier is invalid.");
  }
  const { data, error } = await supabase.rpc("shoir_org_resolve_workspace", {
    p_actor: String(row.username_lc || ""),
    p_organization_id: organizationId,
    p_workspace_id: workspaceId,
    p_permission: permission,
  });
  if (error) throw new Error("Organization workspace access was denied.");
  const resolved = Array.isArray(data) ? data[0] : data;
  const key = String(resolved?.workspace_key || "");
  if (!/^[0-9a-f]{32}$/.test(key)) {
    throw new Error("Organization workspace could not be resolved.");
  }
  return key;
}

Deno.serve(async (req) => {
  const origin = req.headers.get("origin");
  if (!isAllowedBrowserOrigin(origin, SUPABASE_URL)) {
    return new Response(JSON.stringify({ error: "Origin not allowed." }), {
      status: 403,
      headers: {
        "Content-Type": "application/json",
        "Vary": "Origin",
      },
    });
  }
  const sendResponse = (data: unknown, status = 200) =>
    response(data, status, origin);
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: corsHeadersForOrigin(origin, SUPABASE_URL),
    });
  }
  if (!isAllowedApiMethod(req.method)) {
    return sendResponse({ error: "Method not allowed." }, 405);
  }
  try {
    const body = await readBoundedJsonObject(req);
    const action = String(body.action || "");

    if (action === "login") {
      const username = String(body.username || "").trim(),
        password = String(body.password || "");
      const usernameLc = username.toLowerCase();
      let throttleBuckets: Array<
        { key_hash: string; max_attempts: number; reset_on_success: boolean }
      >;
      let blocked = false;
      try {
        throttleBuckets = await loginThrottleBuckets(usernameLc, req);
        for (const bucket of throttleBuckets) {
          if (
            await checkLoginThrottle(
              bucket.key_hash,
              bucket.max_attempts,
              "attempt",
            )
          ) blocked = true;
        }
      } catch {
        return sendResponse({
          error:
            "Authentication protection is temporarily unavailable. Please retry shortly.",
        }, 503);
      }
      if (blocked) {
        return sendResponse({
          error: "Too many sign-in attempts. Please wait and try again.",
        }, 429);
      }
      const row = await getAccount(username);
      if (
        !row || row.active === false ||
        !await verifyPassword(row.password_hash, password)
      ) {
        return sendResponse({ error: "Invalid username or password." }, 401);
      }
      try {
        for (const bucket of throttleBuckets) {
          if (bucket.reset_on_success) {
            await checkLoginThrottle(
              bucket.key_hash,
              bucket.max_attempts,
              "clear",
            );
          }
        }
      } catch {
        return sendResponse({
          error:
            "Authentication protection is temporarily unavailable. Please retry shortly.",
        }, 503);
      }
      // Never silently rewrite the reserved administrator on login. Any drift
      // is an operational incident that must be corrected deliberately.
      const isProtectedMasterAdmin = row.username_lc === "sho";
      if (
        isProtectedMasterAdmin &&
        !hasCanonicalMasterAdminInvariant(row as Record<string, unknown>)
      ) {
        return sendResponse({
          error:
            "The protected administrator configuration requires manual review.",
        }, 503);
      }
      const isMasterAdmin = isProtectedMasterAdmin;
      const effectiveTier = row.tier;
      if (!isMasterAdmin && isExpired(row.subscription_expires_at)) {
        const token = await createSession(
          row.username_lc,
          "renewal",
          60 * 60 * 1000,
        );
        return sendResponse({
          error: "SUBSCRIPTION_EXPIRED",
          token,
          username: row.username,
          tier: effectiveTier,
          email: row.email,
          expires_at: row.subscription_expires_at,
          renewal_only: true,
        }, 403);
      }
      const token = await createSession(row.username_lc);
      return sendResponse({
        ok: true,
        token,
        username: row.username,
        role: row.role,
        tier: effectiveTier,
        email: row.email,
        expires_at: row.subscription_expires_at,
      });
    }

    if (action === "referral_summary_session") {
      const username = String(body.username || "").trim();
      const row = await getSession(String(body.token || ""), username);
      let referralCode = String(row.affiliate_code || "").trim().toUpperCase();
      if (shouldAutoAssignReferralCode(row.username_lc, referralCode)) {
        let assigned = false;
        for (let attempt = 0; attempt < 6 && !assigned; attempt++) {
          const candidate = "SHR-" +
            crypto.randomUUID().replace(/-/g, "").slice(0, 10).toUpperCase();
          const { data: existing, error: lookupError } = await supabase
            .from("shoir_accounts").select("username_lc").ilike(
              "affiliate_code",
              candidate,
            ).maybeSingle();
          if (lookupError) throw lookupError;
          if (existing) continue;
          const { data: changed, error: updateError } = await supabase
            .from("shoir_accounts")
            .update({
              affiliate_code: candidate,
              updated_at: new Date().toISOString(),
            })
            .eq("username_lc", row.username_lc)
            .select("affiliate_code").maybeSingle();
          if (updateError) {
            if (String(updateError.code || "") === "23505") continue;
            throw updateError;
          }
          if (changed?.affiliate_code) {
            referralCode = String(changed.affiliate_code);
            assigned = true;
          }
        }
        if (!assigned) {
          throw new Error(
            "A unique referral code could not be assigned. Please retry.",
          );
        }
      }
      const { data: referrals, error: referralError } = await supabase
        .from("shoir_referrals").select("status").eq(
          "referrer_username_lc",
          row.username_lc,
        );
      if (referralError) throw referralError;
      const counts = {
        pending_count: 0,
        qualified_count: 0,
        declined_count: 0,
      };
      for (const referral of referrals || []) {
        if (referral.status === "Pending") counts.pending_count++;
        else if (referral.status === "Qualified") counts.qualified_count++;
        else if (referral.status === "Declined") counts.declined_count++;
      }
      return sendResponse({ ok: true, referral_code: referralCode, ...counts });
    }

    if (action === "session_entitlement") {
      // Revalidate a current Shoir-IE workspace session against the live session
      // and account rows. Return only the caller's own entitlement fields.
      const username = String(body.username || "").trim();
      const row = await getSession(
        String(body.token || ""),
        username,
        "workspace",
      );
      const entitlement = sessionEntitlementFields(
        row as Record<string, unknown>,
      );
      return sendResponse({ ok: true, ...entitlement });
    }

    if (action === "account_exists") {
      // Do not expose account or registration status through a public username
      // probe. The serialized registration transaction enforces duplicates and
      // returns the same generic conflict response to every caller.
      return sendResponse({ exists: false });
    }

    if (action === "register_request") {
      const username = String(body.username || "").trim();
      const usernameLc = username.toLowerCase();
      const password = String(body.password || "");
      const email = String(body.email || "").trim();
      const tier = String(body.tier || "Starter Tier ($29)").trim();
      const paymentMethod = String(body.payment_method || "").trim();
      const transactionId = String(body.transaction_id || "").trim();
      const referralCode = String(body.referral_code || "").trim()
        .toUpperCase();
      if (
        body.terms_accepted !== true ||
        String(body.terms_version || "") !== TERMS_VERSION ||
        String(body.privacy_policy_version || "") !== PRIVACY_POLICY_VERSION ||
        String(body.refund_policy_version || "") !== REFUND_POLICY_VERSION ||
        String(body.cookie_policy_version || "") !== COOKIE_POLICY_VERSION
      ) {
        return sendResponse({
          error:
            "Please accept the current beta terms and acknowledge the current policy notices before registering.",
        }, 400);
      }
      if (referralCode && !/^[A-Z0-9-]{3,32}$/.test(referralCode)) {
        return sendResponse({
          error:
            "Referral codes may contain only letters, numbers and hyphens.",
        }, 400);
      }
      let referrerUsernameLc: string | null = null;
      if (referralCode) {
        const { data: referrer, error: referrerError } = await supabase
          .from("shoir_accounts").select("username_lc,active")
          .ilike("affiliate_code", referralCode).maybeSingle();
        if (referrerError) throw referrerError;
        if (!referrer || referrer.active === false) {
          return sendResponse({
            error: "Referral code was not found or is inactive.",
          }, 400);
        }
        if (String(referrer.username_lc).toLowerCase() === usernameLc) {
          return sendResponse(
            { error: "Self-referrals are not allowed." },
            400,
          );
        }
        referrerUsernameLc = String(referrer.username_lc).toLowerCase();
        const { data: priorReferral, error: priorReferralError } =
          await supabase
            .from("shoir_referrals").select("id").eq(
              "referred_username_lc",
              usernameLc,
            ).maybeSingle();
        if (priorReferralError) throw priorReferralError;
        if (priorReferral) {
          return sendResponse({
            error: "This account already has referral attribution recorded.",
          }, 409);
        }
      }
      const allowedTiers = new Set([
        "Starter Tier ($29)",
        "Mid-Tier Pro ($79)",
        "Professional Tier ($129)",
        "Enterprise Tier ($199)",
        "Enterprise Plus Tier ($399)",
        "Research Pack ($30 add-on)",
      ]);

      if (!/^[A-Za-z0-9._-]{3,32}$/.test(username)) {
        return sendResponse({
          error:
            "Username must be 3-32 letters, numbers, periods, underscores or hyphens.",
        }, 400);
      }
      if (password.length < 8 || password.length > 128) {
        return sendResponse({
          error: "Password must be between 8 and 128 characters.",
        }, 400);
      }
      const emailParts = email.split("@");
      if (
        email.length > 254 ||
        emailParts.length !== 2 ||
        !emailParts[0] ||
        !emailParts[1] ||
        !emailParts[1].includes(".") ||
        emailParts[1].startsWith(".") ||
        emailParts[1].endsWith(".") ||
        email.includes(" ") || email.includes("\t") || email.includes("\n") ||
        email.includes("\r")
      ) {
        return sendResponse({ error: "Enter a valid email address." }, 400);
      }
      if (!allowedTiers.has(tier)) {
        return sendResponse(
          { error: "Select a valid subscription tier." },
          400,
        );
      }
      if (paymentMethod !== "STC Pay (QR)") {
        return sendResponse(
          { error: "Unsupported registration payment method." },
          400,
        );
      }
      if (transactionId.length > 128) {
        return sendResponse({
          error: "Payment reference must be 128 characters or fewer.",
        }, 400);
      }

      let proofPath: string | null = null;
      try {
        proofPath = await storePaymentProof(body);
      } catch (err) {
        return sendResponse({
          error: err instanceof Error
            ? err.message
            : "Payment proof could not be validated.",
        }, 400);
      }
      if (!transactionId && !proofPath) {
        return sendResponse({
          error:
            "Provide a payment reference or upload payment proof before submitting registration.",
        }, 400);
      }

      const { data, error } = await supabase.rpc(
        "shoir_create_registration_request",
        {
          p_username: username,
          p_username_lc: usernameLc,
          p_password_hash: await hashPassword(password),
          p_email: email,
          p_tier: tier,
          p_payment_method: paymentMethod,
          p_transaction_id: transactionId || null,
          p_screenshot_path: proofPath,
        },
      );
      if (error) {
        if (proofPath) {
          const objectPath = proofPath.replace(
            `storage://${PAYMENT_PROOF_BUCKET}/`,
            "",
          );
          await supabase.storage.from(PAYMENT_PROOF_BUCKET).remove([
            objectPath,
          ]);
        }
        if (error.code === "P0002") {
          return sendResponse({
            error:
              "Registration request could not be submitted. Sign in if you have an account or contact support.",
          }, 409);
        }
        if (error.code === "22023") {
          return sendResponse({ error: error.message }, 400);
        }
        throw error;
      }
      const result = data as {
        ok?: boolean;
        request_id?: number;
        status?: string;
      } | null;
      if (!result?.ok || !result.request_id) {
        if (proofPath) {
          const objectPath = proofPath.replace(
            `storage://${PAYMENT_PROOF_BUCKET}/`,
            "",
          );
          await supabase.storage.from(PAYMENT_PROOF_BUCKET).remove([
            objectPath,
          ]);
        }
        throw new Error(
          "Registration request could not be confirmed by the persistence service.",
        );
      }
      const acceptedAt = new Date().toISOString();
      let legalAcceptanceRecorded = false;
      let referralAttributed = false;
      let referralWarning: string | undefined;
      const { data: consentRow, error: consentError } = await supabase
        .from("shoir_subscription_requests")
        .update({
          terms_accepted: true,
          terms_version: TERMS_VERSION,
          privacy_policy_version: PRIVACY_POLICY_VERSION,
          refund_policy_version: REFUND_POLICY_VERSION,
          cookie_policy_version: COOKIE_POLICY_VERSION,
          accepted_at: acceptedAt,
          updated_at: acceptedAt,
        })
        .eq("id", result.request_id)
        .eq("username_lc", usernameLc)
        .eq("status", "Pending")
        .select("id").maybeSingle();
      if (consentError || !consentRow?.id) {
        console.error(
          "Unable to persist registration policy acknowledgement.",
          consentError?.code || "missing-row",
        );
        // Fail closed: leave no approvable request with missing consent. This is
        // also protected by a database trigger for every approval path.
        const { error: closeRequestError } = await supabase
          .from("shoir_subscription_requests")
          .update({ status: "Declined", updated_at: acceptedAt })
          .eq("id", result.request_id)
          .eq("username_lc", usernameLc)
          .eq("status", "Pending");
        if (closeRequestError) {
          console.error(
            "Unable to close request after consent persistence failure.",
            closeRequestError.code || "unknown",
          );
        }
        if (proofPath) {
          const objectPath = proofPath.replace(
            `storage://${PAYMENT_PROOF_BUCKET}/`,
            "",
          );
          const { error: cleanupProofError } = await supabase.storage
            .from(PAYMENT_PROOF_BUCKET).remove([objectPath]);
          if (cleanupProofError) {
            console.error(
              "Unable to remove unneeded payment proof.",
              "storage-error",
            );
          }
        }
        return sendResponse({
          error:
            "The registration was not accepted because its legal-acceptance record could not be saved. No subscription was activated. Refresh and retry, or contact support if the issue continues.",
        }, 500);
      }
      legalAcceptanceRecorded = true;
      if (referrerUsernameLc && legalAcceptanceRecorded) {
        const { error: attributionError } = await supabase.from(
          "shoir_referrals",
        ).insert({
          referrer_username_lc: referrerUsernameLc,
          referred_username_lc: usernameLc,
          referral_code: referralCode,
          status: "Pending",
        });
        if (attributionError) {
          referralWarning =
            "Registration was received, but the server could not confirm referral attribution. No reward or discount is implied.";
          console.error(
            "Unable to persist beta referral attribution.",
            attributionError.code || "unknown",
          );
        } else {
          referralAttributed = true;
        }
      } else if (referrerUsernameLc) {
        referralWarning =
          "Registration was received, but the legal-acceptance record could not be confirmed. Referral attribution was not recorded.";
      }
      return sendResponse({
        ok: true,
        request_id: result.request_id,
        status: result.status || "Pending",
        proof_uploaded: !!proofPath,
        legal_acceptance_recorded: legalAcceptanceRecorded,
        referral_attributed: referralAttributed,
        referral_warning: referralWarning,
      });
    }

    if (action === "logout") {
      const token = String(body.token || "").trim();
      const usernameLc = String(body.username || "").trim().toLowerCase();
      if (!token || !usernameLc) {
        return sendResponse({ ok: true, revoked: false });
      }
      const tokenHash = bytesToHex(
        await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)),
      );
      // Revocation is idempotent and account-scoped. Never store or log the bearer token.
      const { data, error } = await supabase.from("shoir_sessions").delete()
        .eq("token_hash", tokenHash).eq("username_lc", usernameLc).select(
          "token_hash",
        );
      if (error) throw error;
      return sendResponse({ ok: true, revoked: !!(data && data.length) });
    }

    if (action === "org_list_session") {
      const username = String(body.username || "").trim();
      const actor = await getSession(
        String(body.token || ""),
        username,
        "workspace",
      );
      const { data, error } = await supabase.from(
        "shoir_organization_memberships",
      )
        .select("organization_id,role,status,joined_at")
        .eq("username_lc", actor.username_lc)
        .eq("status", "active")
        .order("created_at", { ascending: true });
      if (error) throw error;
      const memberships = data || [];
      const organizationIds = memberships.map((item) => item.organization_id);
      if (!organizationIds.length) {
        return sendResponse({ ok: true, organizations: [] });
      }
      const { data: organizations, error: organizationError } = await supabase
        .from("shoir_organizations")
        .select(
          "organization_id,display_name,org_type,owner_username_lc,status",
        )
        .in("organization_id", organizationIds)
        .eq("status", "active")
        .order("display_name", { ascending: true });
      if (organizationError) throw organizationError;
      const byId = new Map((organizations || []).map((item) => [
        item.organization_id,
        item,
      ]));
      const result = memberships.flatMap((membership) => {
        const organization = byId.get(membership.organization_id);
        if (!organization) return [];
        return [{
          organization_id: organization.organization_id,
          display_name: organization.display_name,
          org_type: organization.org_type,
          owner_username_lc: organization.owner_username_lc,
          role: membership.role,
          joined_at: membership.joined_at,
        }];
      });
      return sendResponse({ ok: true, organizations: result });
    }

    if (action === "org_create_session") {
      const username = String(body.username || "").trim();
      const actor = await getSession(
        String(body.token || ""),
        username,
        "workspace",
      );
      requireOrganizationTier(actor as Record<string, unknown>);
      const displayName = String(body.display_name || "").trim();
      if (displayName.length < 2 || displayName.length > 120) {
        return sendResponse({
          error: "Organization name must contain 2 to 120 characters.",
        }, 400);
      }
      const { data, error } = await supabase.rpc("shoir_org_create", {
        p_actor: actor.username_lc,
        p_display_name: displayName,
      });
      if (error) throw error;
      return sendResponse({
        ok: true,
        organization: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_workspace_list_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
      );
      const { data, error } = await supabase.from(
        "shoir_organization_workspaces",
      )
        .select(
          "workspace_id,display_name,name_key,status,created_at,updated_at",
        )
        .eq("organization_id", String(membership.organization.organization_id))
        .eq("status", "active")
        .order("display_name", { ascending: true });
      if (error) throw error;
      return sendResponse({
        ok: true,
        role: membership.role,
        workspaces: data || [],
      });
    }

    if (action === "org_member_list_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
      );
      const { data, error } = await supabase.from(
        "shoir_organization_memberships",
      )
        .select("username_lc,role,status,joined_at,created_at,updated_at")
        .eq("organization_id", String(membership.organization.organization_id))
        .eq("status", "active")
        .order("role", { ascending: true })
        .order("username_lc", { ascending: true });
      if (error) throw error;
      return sendResponse({
        ok: true,
        role: membership.role,
        members: data || [],
      });
    }

    if (action === "org_invitation_create_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      if (membership.organization.org_type !== "team") {
        return sendResponse({
          error: "Invitations are available only for team organizations.",
        }, 403);
      }
      const target = String(body.target_username_lc || "").trim().toLowerCase();
      const role = String(body.role || "viewer").trim().toLowerCase();
      if (
        !target || target.length > 128 || !/^[a-z0-9][a-z0-9._-]*$/.test(target)
      ) {
        return sendResponse({ error: "Invitation username is invalid." }, 400);
      }
      if (!["admin", "engineer", "approver", "viewer"].includes(role)) {
        return sendResponse({ error: "Invitation role is invalid." }, 400);
      }
      const lifetimeDays = Number(body.lifetime_days ?? 7);
      if (
        !Number.isInteger(lifetimeDays) || lifetimeDays < 1 || lifetimeDays > 30
      ) {
        return sendResponse({
          error: "Invitation lifetime must be between 1 and 30 days.",
        }, 400);
      }
      const tokenBytes = new Uint8Array(32);
      crypto.getRandomValues(tokenBytes);
      const invitationToken = bytesToHex(tokenBytes);
      const tokenHash = await sha256Hex(invitationToken);
      const expiresAt = new Date(
        Date.now() + lifetimeDays * 24 * 60 * 60 * 1000,
      ).toISOString();
      const { data, error } = await supabase.rpc(
        "shoir_org_invitation_create",
        {
          p_actor: actor.username_lc,
          p_organization_id: String(membership.organization.organization_id),
          p_target_username_lc: target,
          p_role: role,
          p_token_hash: tokenHash,
          p_expires_at: expiresAt,
        },
      );
      if (error) throw error;
      return sendResponse({
        ok: true,
        invitation: Array.isArray(data) ? data[0] : data,
        invitation_token: invitationToken,
        token_notice:
          "Copy this token now. It is stored only as a SHA-256 hash and cannot be retrieved again.",
      });
    }

    if (action === "org_invitation_accept_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const invitationToken = String(body.invitation_token || "").trim()
        .toLowerCase();
      if (!/^[0-9a-f]{64}$/.test(invitationToken)) {
        return sendResponse({ error: "Invitation token is invalid." }, 400);
      }
      const { data, error } = await supabase.rpc(
        "shoir_org_invitation_accept",
        {
          p_actor: actor.username_lc,
          p_token_hash: await sha256Hex(invitationToken),
        },
      );
      if (error) throw error;
      return sendResponse({
        ok: true,
        membership: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_invitation_list_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const { data, error } = await supabase.from(
        "shoir_organization_invitations",
      )
        .select(
          "invitation_id,target_username_lc,role,created_by_username_lc,expires_at,used_at,revoked_at,accepted_by_username_lc,created_at",
        )
        .eq("organization_id", String(membership.organization.organization_id))
        .order("created_at", { ascending: false })
        .limit(100);
      if (error) throw error;
      return sendResponse({ ok: true, invitations: data || [] });
    }

    if (action === "org_invitation_revoke_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const invitationId = validatedOrganizationId(body.invitation_id);
      const { data, error } = await supabase.rpc(
        "shoir_org_invitation_revoke",
        {
          p_actor: actor.username_lc,
          p_organization_id: String(membership.organization.organization_id),
          p_invitation_id: invitationId,
        },
      );
      if (error) throw error;
      return sendResponse({
        ok: true,
        result: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_member_role_set_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const target = String(body.target_username_lc || "").trim().toLowerCase();
      const newRole = String(body.role || "").trim().toLowerCase();
      if (!target || target.length > 128) {
        return sendResponse({ error: "Member username is invalid." }, 400);
      }
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const { data, error } = await supabase.rpc("shoir_org_member_role_set", {
        p_actor: actor.username_lc,
        p_organization_id: String(membership.organization.organization_id),
        p_target_username_lc: target,
        p_role: newRole,
      });
      if (error) throw error;
      return sendResponse({
        ok: true,
        result: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_member_remove_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const target = String(body.target_username_lc || "").trim().toLowerCase();
      if (!target || target.length > 128) {
        return sendResponse({ error: "Member username is invalid." }, 400);
      }
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const { data, error } = await supabase.rpc("shoir_org_member_remove", {
        p_actor: actor.username_lc,
        p_organization_id: String(membership.organization.organization_id),
        p_target_username_lc: target,
      });
      if (error) throw error;
      return sendResponse({
        ok: true,
        result: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_member_suspend_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const target = String(body.target_username_lc || "").trim().toLowerCase();
      if (!target || target.length > 128) {
        return sendResponse({ error: "Member username is invalid." }, 400);
      }
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const { data, error } = await supabase.rpc("shoir_org_member_suspend", {
        p_actor: actor.username_lc,
        p_organization_id: String(membership.organization.organization_id),
        p_target_username_lc: target,
      });
      if (error) throw error;
      return sendResponse({
        ok: true,
        result: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_member_restore_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const target = String(body.target_username_lc || "").trim().toLowerCase();
      if (!target || target.length > 128) {
        return sendResponse({ error: "Member username is invalid." }, 400);
      }
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const { data, error } = await supabase.rpc("shoir_org_member_restore", {
        p_actor: actor.username_lc,
        p_organization_id: String(membership.organization.organization_id),
        p_target_username_lc: target,
      });
      if (error) throw error;
      return sendResponse({
        ok: true,
        result: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_owner_transfer_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const target = String(body.target_username_lc || "").trim().toLowerCase();
      if (!target || target.length > 128) {
        return sendResponse({ error: "New owner username is invalid." }, 400);
      }
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
      );
      const { data, error } = await supabase.rpc("shoir_org_owner_transfer", {
        p_actor: actor.username_lc,
        p_organization_id: String(membership.organization.organization_id),
        p_target_username_lc: target,
      });
      if (error) throw error;
      return sendResponse({
        ok: true,
        result: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_close_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
      );
      if (membership.role !== "owner") {
        return sendResponse({
          error: "Only the organization owner may close the organization.",
        }, 403);
      }
      const { data, error } = await supabase.rpc("shoir_org_close", {
        p_actor: actor.username_lc,
        p_organization_id: String(membership.organization.organization_id),
      });
      if (error) throw error;
      return sendResponse({
        ok: true,
        result: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_workspace_create_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const displayName = String(body.display_name || "").trim();
      if (!displayName || displayName.length > 120) {
        return sendResponse({
          error: "Workspace name must contain 1 to 120 characters.",
        }, 400);
      }
      const { data, error } = await supabase.rpc("shoir_org_workspace_create", {
        p_actor: actor.username_lc,
        p_organization_id: String(membership.organization.organization_id),
        p_display_name: displayName,
      });
      if (error) throw error;
      return sendResponse({
        ok: true,
        workspace: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_workspace_archive_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const workspaceId = validatedOrganizationId(
        body.organization_workspace_id,
      );
      const { data, error } = await supabase.rpc(
        "shoir_org_workspace_archive",
        {
          p_actor: actor.username_lc,
          p_organization_id: String(membership.organization.organization_id),
          p_workspace_id: workspaceId,
        },
      );
      if (error) throw error;
      return sendResponse({
        ok: true,
        result: Array.isArray(data) ? data[0] : data,
      });
    }

    if (action === "org_audit_list_session") {
      const actor = await getSession(
        String(body.token || ""),
        String(body.username || ""),
        "workspace",
      );
      const membership = await organizationForActor(
        actor.username_lc,
        body.organization_id,
        true,
      );
      const limit = Number(body.limit ?? 100);
      if (!Number.isInteger(limit) || limit < 1 || limit > 200) {
        return sendResponse({
          error: "Audit event page size must be between 1 and 200.",
        }, 400);
      }
      const { data, error } = await supabase.from(
        "shoir_organization_audit_events",
      )
        .select(
          "event_id,actor_username_lc,subject_username_lc,event_type,payload_json,created_at",
        )
        .eq("organization_id", String(membership.organization.organization_id))
        .order("created_at", { ascending: false })
        .limit(limit);
      if (error) throw error;
      return sendResponse({ ok: true, events: data || [] });
    }

    if (action === "dataset_download_url") {
      const username = String(body.username || "").trim();
      const row = await getSession(
        String(body.token || ""),
        username,
        "workspace",
      );
      const entitlementResponse = await datasetEntitlementDenialForRequest(
        row as unknown as Record<string, unknown>,
        body,
      );
      if (entitlementResponse) return sendResponse(entitlementResponse, 403);
      const workspaceKey = await resolveManagedWorkspaceKey(
        row as Record<string, unknown>,
        body,
        "read",
      );
      const datasetId = String(body.dataset_id || "").trim();
      const requestedVersion = body.version == null || body.version === ""
        ? null
        : Number(body.version);
      if (
        !/^DS-[A-F0-9]{12,32}$/.test(datasetId) ||
        (requestedVersion !== null &&
          (!Number.isSafeInteger(requestedVersion) || requestedVersion < 1))
      ) {
        return sendResponse(
          { error: "Dataset identifier or version is invalid." },
          400,
        );
      }
      const recordType = requestedVersion === null
        ? "dataset"
        : "dataset_version";
      const entityKey = requestedVersion === null
        ? datasetId
        : datasetId + ":v" + requestedVersion;
      const { data: record, error } = await supabase
        .from("shoir_platform_records")
        .select("payload_json")
        .eq("workspace_key", workspaceKey)
        .eq("record_type", recordType)
        .eq("entity_key", entityKey)
        .maybeSingle();
      if (error) throw error;
      if (!record?.payload_json) {
        return sendResponse(
          { error: "Dataset version was not found in this workspace." },
          404,
        );
      }
      const payload = record.payload_json as Record<string, unknown>;
      const storageKey = String(payload.storage_key || "");
      const expectedPrefix = workspaceKey + "/" + datasetId + "/";
      if (
        !storageKey.startsWith(expectedPrefix) ||
        !/^[0-9a-f]{64}\.csv$/.test(storageKey.slice(expectedPrefix.length))
      ) {
        return sendResponse(
          { error: "Dataset storage reference is invalid." },
          409,
        );
      }
      const { data, error: signError } = await supabase.storage
        .from("shoir-industrial-datasets")
        .createSignedUrl(storageKey, 300, { download: true });
      if (signError) throw signError;
      if (!data?.signedUrl) {
        throw new Error(
          "Storage provider did not return a signed download URL.",
        );
      }
      return sendResponse({
        ok: true,
        download_url: data.signedUrl,
        data_hash: String(payload.data_hash || ""),
        version: Number(payload.version || requestedVersion || 1),
        row_count: Number(payload.row_count || 0),
        column_count: Number(payload.column_count || 0),
        version_record_id: String(payload.version_record_id || ""),
        registered_at: String(payload.registered_at || ""),
      });
    }

    if (action === "dataset_upload_create") {
      const username = String(body.username || "").trim();
      const row = await getSession(
        String(body.token || ""),
        username,
        "workspace",
      );
      const entitlementResponse = await datasetEntitlementDenialForRequest(
        row as unknown as Record<string, unknown>,
        body,
      );
      if (entitlementResponse) return sendResponse(entitlementResponse, 403);
      const workspaceKey = await resolveManagedWorkspaceKey(
        row as Record<string, unknown>,
        body,
        "write",
      );
      const datasetId = String(body.dataset_id || "").trim();
      const dataHash = String(body.data_hash || "").toLowerCase();
      if (
        !/^DS-[A-F0-9]{12,32}$/.test(datasetId) ||
        !/^[0-9a-f]{64}$/.test(dataHash)
      ) {
        return sendResponse(
          { error: "Dataset upload identity is invalid." },
          400,
        );
      }
      const uploadPath = "tmp/" + workspaceKey + "/" + datasetId + "/" +
        crypto.randomUUID().replace(/-/g, "") + ".csv";
      const { data, error } = await supabase.storage
        .from("shoir-industrial-datasets")
        .createSignedUploadUrl(uploadPath, { upsert: false });
      if (error) throw error;
      if (!data?.signedUrl || !data?.token) {
        throw new Error(
          "Storage provider did not return a signed upload URL.",
        );
      }
      return sendResponse({
        ok: true,
        upload_url: data.signedUrl,
        upload_token: data.token,
        upload_path: uploadPath,
        max_bytes: 52428800,
      });
    }

    if (action === "dataset_version_finalize") {
      const username = String(body.username || "").trim();
      const row = await getSession(
        String(body.token || ""),
        username,
        "workspace",
      );
      const entitlementResponse = await datasetEntitlementDenialForRequest(
        row as unknown as Record<string, unknown>,
        body,
      );
      if (entitlementResponse) return sendResponse(entitlementResponse, 403);
      const workspaceKey = await resolveManagedWorkspaceKey(
        row as Record<string, unknown>,
        body,
        "write",
      );
      const datasetId = String(body.dataset_id || "").trim();
      const uploadPath = String(body.upload_path || "").trim();
      const name = String(body.name || "").trim();
      const sourceName = String(body.source_name || "").trim();
      const dataHash = String(body.data_hash || "").toLowerCase();
      const fingerprint = String(body.version_fingerprint || "").toLowerCase();
      const rowCount = Number(body.row_count);
      const columnCount = Number(body.column_count);
      const schema = body.schema;
      const transformations = body.transformations || [];
      if (
        !/^DS-[A-F0-9]{12,32}$/.test(datasetId) ||
        !uploadPath.startsWith("tmp/" + workspaceKey + "/" + datasetId + "/") ||
        uploadPath.includes("..") ||
        uploadPath.length > 240 ||
        !name ||
        name.length > 200 ||
        sourceName.length > 500 ||
        !/^[0-9a-f]{64}$/.test(dataHash) ||
        !/^[0-9a-f]{64}$/.test(fingerprint) ||
        !Number.isSafeInteger(rowCount) ||
        rowCount < 0 ||
        rowCount > 100000000 ||
        !Number.isSafeInteger(columnCount) ||
        columnCount < 0 ||
        columnCount > 5000 ||
        !schema ||
        typeof schema !== "object" ||
        Array.isArray(schema) ||
        new TextEncoder().encode(JSON.stringify(schema)).byteLength > 65536 ||
        !Array.isArray(transformations) ||
        transformations.length > 50 ||
        new TextEncoder().encode(JSON.stringify(transformations)).byteLength >
          16384
      ) {
        return sendResponse(
          { error: "Dataset version metadata is invalid." },
          400,
        );
      }
      const expectedFingerprint = await sha256Hex(
        stablePlatformJson({
          dataset_id: datasetId,
          data_hash: dataHash,
          schema,
          transformations,
        }),
      );
      if (expectedFingerprint !== fingerprint) {
        return sendResponse(
          {
            error:
              "Dataset version fingerprint does not match the submitted metadata.",
          },
          422,
        );
      }
      const { data: uploaded, error: downloadError } = await supabase.storage
        .from("shoir-industrial-datasets")
        .download(uploadPath);
      if (downloadError || !uploaded) {
        throw downloadError ||
          new Error("Uploaded dataset file is missing.");
      }
      if (uploaded.size > 52428800) {
        await supabase.storage
          .from("shoir-industrial-datasets")
          .remove([uploadPath]);
        return sendResponse(
          { error: "Dataset file exceeds the 50 MiB storage limit." },
          413,
        );
      }
      const bytes = new Uint8Array(await uploaded.arrayBuffer());
      const digest = await sha256Bytes(bytes);
      if (digest !== dataHash) {
        await supabase.storage
          .from("shoir-industrial-datasets")
          .remove([uploadPath]);
        return sendResponse(
          {
            error:
              "Uploaded dataset content hash does not match the registered data hash.",
          },
          422,
        );
      }
      let csvShape;
      try {
        csvShape = inspectCsvShape(bytes);
      } catch (shapeError) {
        await supabase.storage
          .from("shoir-industrial-datasets")
          .remove([uploadPath]);
        throw shapeError;
      }
      const schemaColumns = Object.keys(schema as Record<string, unknown>);
      if (
        csvShape.rowCount !== rowCount ||
        csvShape.columnCount !== columnCount ||
        schemaColumns.length !== csvShape.columnCount ||
        csvShape.headers.some((header) => !schemaColumns.includes(header))
      ) {
        await supabase.storage
          .from("shoir-industrial-datasets")
          .remove([uploadPath]);
        return sendResponse(
          {
            error:
              "Dataset row count, column count or schema does not match the uploaded CSV.",
          },
          422,
        );
      }
      const storageKey = workspaceKey + "/" + datasetId + "/" + dataHash +
        ".csv";
      const bucket = supabase.storage.from("shoir-industrial-datasets");
      const { data: existingFile, error: existingError } = await bucket
        .download(storageKey);
      if (!existingError && existingFile) {
        const existingBytes = new Uint8Array(
          await existingFile.arrayBuffer(),
        );
        const existingHash = await sha256Bytes(existingBytes);
        if (existingHash !== dataHash) {
          await bucket.remove([uploadPath]);
          throw new Error(
            "Existing immutable dataset object does not match its content hash.",
          );
        }
      } else {
        const uploadBlob = new Blob(
          [bytes.slice().buffer as ArrayBuffer],
          { type: "text/csv" },
        );
        const { error: storeError } = await bucket.upload(
          storageKey,
          uploadBlob,
          { contentType: "text/csv", upsert: false },
        );
        if (storeError) {
          const { data: racedFile, error: racedError } = await bucket
            .download(storageKey);
          if (racedError || !racedFile) throw storeError;
          const racedBytes = new Uint8Array(await racedFile.arrayBuffer());
          const racedHash = await sha256Bytes(racedBytes);
          if (racedHash !== dataHash) {
            throw new Error(
              "Concurrent immutable dataset upload has a different content hash.",
            );
          }
        }
      }
      const { error: removeError } = await bucket.remove([uploadPath]);
      if (removeError) throw removeError;
      const versionRecordId = "SPR-" +
        crypto.randomUUID().replace(/-/g, "").slice(0, 24).toUpperCase();
      const headRecordId = "SPR-" +
        crypto.randomUUID().replace(/-/g, "").slice(0, 24).toUpperCase();
      const eventId = "SPE-" +
        crypto.randomUUID().replace(/-/g, "").slice(0, 24).toUpperCase();
      const { data, error } = await supabase.rpc(
        "shoir_platform_register_dataset_version_with_storage",
        {
          p_workspace_key: workspaceKey,
          p_dataset_id: datasetId,
          p_name: name,
          p_source_name: sourceName,
          p_data_hash: dataHash,
          p_version_fingerprint: fingerprint,
          p_row_count: rowCount,
          p_column_count: columnCount,
          p_schema_json: schema,
          p_transformations_json: transformations,
          p_actor: row.username_lc,
          p_version_record_id: versionRecordId,
          p_head_record_id: headRecordId,
          p_event_id: eventId,
          p_storage_key: storageKey,
        },
      );
      if (error) throw error;
      const registration = Array.isArray(data) ? data[0] : data;
      return sendResponse({ ok: true, registration });
    }

    if (action === "dataset_version_register") {
      const username = String(body.username || "").trim();
      const row = await getSession(
        String(body.token || ""),
        username,
        "workspace",
      );
      const entitlementResponse = await datasetEntitlementDenialForRequest(
        row as unknown as Record<string, unknown>,
        body,
      );
      if (entitlementResponse) return sendResponse(entitlementResponse, 403);
      const workspaceKey = await resolveManagedWorkspaceKey(
        row as Record<string, unknown>,
        body,
        "write",
      );
      const datasetId = String(body.dataset_id || "").trim();
      const name = String(body.name || "").trim();
      const sourceName = String(body.source_name || "").trim();
      const dataHash = String(body.data_hash || "").toLowerCase();
      const fingerprint = String(body.version_fingerprint || "").toLowerCase();
      const rowCount = Number(body.row_count);
      const columnCount = Number(body.column_count);
      const schema = body.schema;
      const transformations = body.transformations || [];
      if (
        !/^DS-[A-F0-9]{12,32}$/.test(datasetId) ||
        !name || name.length > 200 || sourceName.length > 500 ||
        !/^[0-9a-f]{64}$/.test(dataHash) ||
        !/^[0-9a-f]{64}$/.test(fingerprint) ||
        !Number.isSafeInteger(rowCount) || rowCount < 0 ||
        rowCount > 100000000 ||
        !Number.isSafeInteger(columnCount) || columnCount < 0 ||
        columnCount > 5000 ||
        !schema || typeof schema !== "object" || Array.isArray(schema) ||
        new TextEncoder().encode(JSON.stringify(schema)).byteLength > 65536 ||
        !Array.isArray(transformations) || transformations.length > 50 ||
        new TextEncoder().encode(JSON.stringify(transformations)).byteLength >
          16384
      ) {
        return sendResponse(
          { error: "Dataset version metadata is invalid." },
          400,
        );
      }
      const versionRecordId = "SPR-" +
        crypto.randomUUID().replace(/-/g, "").slice(0, 24).toUpperCase();
      const headRecordId = "SPR-" +
        crypto.randomUUID().replace(/-/g, "").slice(0, 24).toUpperCase();
      const eventId = "SPE-" +
        crypto.randomUUID().replace(/-/g, "").slice(0, 24).toUpperCase();
      const { data, error } = await supabase.rpc(
        "shoir_platform_register_dataset_version",
        {
          p_workspace_key: workspaceKey,
          p_dataset_id: datasetId,
          p_name: name,
          p_source_name: sourceName,
          p_data_hash: dataHash,
          p_version_fingerprint: fingerprint,
          p_row_count: rowCount,
          p_column_count: columnCount,
          p_schema_json: schema,
          p_transformations_json: transformations,
          p_actor: row.username_lc,
          p_version_record_id: versionRecordId,
          p_head_record_id: headRecordId,
          p_event_id: eventId,
        },
      );
      if (error) throw error;
      const registration = Array.isArray(data) ? data[0] : data;
      return sendResponse({ ok: true, registration });
    }

    if (action === "platform_record_save") {
      const username = String(body.username || "").trim();
      const token = String(body.token || "");
      const row = await getSession(token, username, "workspace");
      const recordType = String(body.record_type || "").trim().toLowerCase();
      if (recordType === "dataset" || recordType === "dataset_version") {
        const entitlementResponse = await datasetEntitlementDenialForRequest(
          row as unknown as Record<string, unknown>,
          body,
        );
        if (entitlementResponse) return sendResponse(entitlementResponse, 403);
      }
      const entityKey = String(body.entity_key || "").trim();
      if (!PLATFORM_RECORD_TYPES.has(recordType)) {
        return sendResponse(
          { error: "Platform record type is not supported." },
          400,
        );
      }
      if (
        !entityKey || entityKey.length > 240 ||
        /[\\x00-\\x1f\\x7f]/.test(entityKey)
      ) {
        return sendResponse({ error: "Platform entity key is invalid." }, 400);
      }
      const payload = validatePlatformPayload(body.payload);
      const canonical = stablePlatformJson(payload);
      const contentHash = await sha256Hex(canonical);
      const workspaceKey = await resolveManagedWorkspaceKey(
        row as Record<string, unknown>,
        body,
        "write",
      );
      const recordId = "SPR-" +
        crypto.randomUUID().replace(/-/g, "").slice(0, 24).toUpperCase();
      const eventId = "SPE-" +
        crypto.randomUUID().replace(/-/g, "").slice(0, 24).toUpperCase();
      const { data, error } = await supabase.rpc(
        "shoir_platform_upsert_record",
        {
          p_record_id: recordId,
          p_workspace_key: workspaceKey,
          p_record_type: recordType,
          p_entity_key: entityKey,
          p_payload: payload,
          p_content_hash: contentHash,
          p_actor: row.username_lc,
          p_event_id: eventId,
        },
      );
      if (error) throw error;
      const saved = Array.isArray(data) ? data[0] : data;
      return sendResponse({ ok: true, record: saved });
    }
    if (action === "platform_record_list") {
      const username = String(body.username || "").trim();
      const row = await getSession(
        String(body.token || ""),
        username,
        "workspace",
      );
      const workspaceKey = await resolveManagedWorkspaceKey(
        row as Record<string, unknown>,
        body,
        "read",
      );
      const recordType = String(body.record_type || "").trim().toLowerCase();
      if (recordType && !PLATFORM_RECORD_TYPES.has(recordType)) {
        return sendResponse(
          { error: "Platform record type is not supported." },
          400,
        );
      }
      if (recordType === "dataset" || recordType === "dataset_version") {
        const entitlementResponse = await datasetEntitlementDenialForRequest(
          row as unknown as Record<string, unknown>,
          body,
        );
        if (entitlementResponse) return sendResponse(entitlementResponse, 403);
      }
      const entityKey = String(body.entity_key || "").trim();
      if (entityKey.length > 240 || /[\\x00-\\x1f\\x7f]/.test(entityKey)) {
        return sendResponse({ error: "Platform entity key is invalid." }, 400);
      }
      const requestedLimit = Number(body.limit || 100);
      const requestedOffset = Number(body.offset || 0);
      if (
        !Number.isInteger(requestedLimit) || requestedLimit < 1 ||
        requestedLimit > 200
      ) {
        return sendResponse({
          error: "Platform record page size must be between 1 and 200.",
        }, 400);
      }
      if (
        !Number.isSafeInteger(requestedOffset) || requestedOffset < 0 ||
        requestedOffset > 100000
      ) {
        return sendResponse(
          { error: "Platform record offset is invalid." },
          400,
        );
      }
      let query = supabase.from("shoir_platform_records")
        .select(
          "record_id,record_type,entity_key,payload_json,content_hash,version,created_at,updated_at",
        )
        .eq("workspace_key", workspaceKey)
        .order("updated_at", { ascending: false })
        .order("record_id", { ascending: true })
        .range(requestedOffset, requestedOffset + requestedLimit);
      if (recordType) query = query.eq("record_type", recordType);
      if (entityKey) query = query.eq("entity_key", entityKey);
      const { data, error } = await query;
      if (error) throw error;
      const page = data || [];
      const hasMore = page.length > requestedLimit;
      const records = hasMore ? page.slice(0, requestedLimit) : page;
      return sendResponse({
        ok: true,
        records,
        has_more: hasMore,
        next_offset: requestedOffset + records.length,
      });
    }

    if (action === "workspace_load") {
      const actor = await getSession(
        String(body.token),
        String(body.username),
        "workspace",
      );
      const organizationId = String(body.organization_id || "").trim();
      const organizationWorkspaceId = String(
        body.organization_workspace_id || "",
      ).trim();
      if (organizationId || organizationWorkspaceId) {
        if (!organizationId || !organizationWorkspaceId) {
          return sendResponse({
            error:
              "Both organization_id and organization_workspace_id are required.",
          }, 400);
        }
        const { data, error } = await supabase.rpc(
          "shoir_org_workspace_state_load",
          {
            p_actor: actor.username_lc,
            p_organization_id: organizationId,
            p_workspace_id: organizationWorkspaceId,
          },
        );
        if (error) throw error;
        const state = Array.isArray(data) ? data[0] : data;
        return sendResponse({
          ok: true,
          state_json: typeof state?.state_json === "string"
            ? state.state_json
            : null,
          revision: Number.isSafeInteger(Number(state?.revision))
            ? Number(state.revision)
            : 0,
          updated_at: state?.updated_at || null,
        });
      }
      const { data, error } = await supabase.from("shoir_workspace_states")
        .select("state_json,updated_at").eq(
          "username_lc",
          actor.username_lc,
        ).maybeSingle();
      if (error) throw error;
      return sendResponse({
        ok: true,
        state_json: data?.state_json || null,
        updated_at: data?.updated_at || null,
      });
    }
    if (action === "workspace_save") {
      const actor = await getSession(
        String(body.token),
        String(body.username),
        "workspace",
      );
      // Validate before upsert so malformed/oversized state never replaces the last valid save.
      const workspaceState = normalizeWorkspaceStateJson(body.state_json);
      const organizationId = String(body.organization_id || "").trim();
      const organizationWorkspaceId = String(
        body.organization_workspace_id || "",
      ).trim();
      if (organizationId || organizationWorkspaceId) {
        if (!organizationId || !organizationWorkspaceId) {
          return sendResponse({
            error:
              "Both organization_id and organization_workspace_id are required.",
          }, 400);
        }
        const rawRevision = body.expected_revision;
        if (rawRevision === undefined || rawRevision === null) {
          return sendResponse(
            { error: "Workspace revision is required." },
            400,
          );
        }
        const parsedRevision = Number(rawRevision);
        if (!Number.isSafeInteger(parsedRevision) || parsedRevision < 0) {
          return sendResponse(
            { error: "Workspace revision is invalid." },
            400,
          );
        }
        const expectedRevision: number = parsedRevision;
        const { data, error } = await supabase.rpc(
          "shoir_org_workspace_state_save",
          {
            p_actor: actor.username_lc,
            p_organization_id: organizationId,
            p_workspace_id: organizationWorkspaceId,
            p_state_json: workspaceState,
            p_expected_revision: expectedRevision,
          },
        );
        if (error?.code === "40001") {
          return sendResponse({
            error: "SHARED_WORKSPACE_REVISION_CONFLICT",
          }, 409);
        }
        if (error) throw error;
        const saved = Array.isArray(data) ? data[0] : data;
        return sendResponse({
          ok: true,
          revision: Number(saved?.revision || 0),
          updated_at: saved?.updated_at || null,
        });
      }
      const { error } = await supabase.from("shoir_workspace_states").upsert({
        username_lc: actor.username_lc,
        state_json: workspaceState,
        updated_at: new Date().toISOString(),
      }, { onConflict: "username_lc" });
      if (error) throw error;
      return sendResponse({ ok: true });
    }
    if (action === "workspace_access_check") {
      const actor = await getSession(
        String(body.token),
        String(body.username),
        "workspace",
      );
      const organizationId = String(body.organization_id || "").trim();
      const organizationWorkspaceId = String(
        body.organization_workspace_id || "",
      ).trim();
      if (!organizationId || !organizationWorkspaceId) {
        return sendResponse({
          error:
            "Both organization_id and organization_workspace_id are required.",
        }, 400);
      }
      await resolveManagedWorkspaceKey(
        actor as Record<string, unknown>,
        body,
        "read",
      );
      return sendResponse({ ok: true });
    }
    if (action === "renew_request") {
      const row = await getSession(
        String(body.token),
        String(body.username),
        "either",
      );
      if (row.username_lc === "sho" && row.role === "Enterprise Admin") {
        return sendResponse({
          error:
            "Administrator subscription is not eligible for customer renewal.",
        }, 403);
      }
      const transactionId = String(body.transaction_id || "").trim();
      if (!transactionId) {
        return sendResponse({
          error:
            "A transaction/payment reference is required for renewal review.",
        }, 400);
      }
      const proofPath = await storePaymentProof(body);
      const pending = await supabase.from("shoir_subscription_requests").insert(
        {
          username: row.username,
          username_lc: row.username_lc,
          email: row.email,
          tier: body.tier || row.tier,
          request_type: "Renewal",
          payment_method: body.payment_method || "",
          transaction_id: transactionId,
          screenshot_path: proofPath,
          status: "Pending",
        },
      ).select("id").single();
      if (pending.error) {
        if (proofPath) {
          const objectPath = proofPath.replace(
            `storage://${PAYMENT_PROOF_BUCKET}/`,
            "",
          );
          await supabase.storage.from(PAYMENT_PROOF_BUCKET).remove([
            objectPath,
          ]);
        }
        throw pending.error;
      }
      return sendResponse({
        ok: true,
        request_id: pending.data.id,
        proof_uploaded: !!proofPath,
      });
    }
    if (action === "admin_payment_proof_url_session") {
      await adminSession(String(body.username), String(body.token));
      const storedPath = String(body.screenshot_path || "");
      const prefix = `storage://${PAYMENT_PROOF_BUCKET}/`;
      if (!storedPath.startsWith(prefix)) {
        return sendResponse(
          { error: "Invalid private payment proof reference." },
          400,
        );
      }
      const objectPath = storedPath.slice(prefix.length);
      if (!objectPath.startsWith("renewals/") || objectPath.includes("..")) {
        return sendResponse(
          { error: "Invalid private payment proof path." },
          400,
        );
      }
      const { data, error } = await supabase.storage.from(PAYMENT_PROOF_BUCKET)
        .createSignedUrl(objectPath, 300);
      if (error) throw error;
      return sendResponse({
        ok: true,
        signed_url: data.signedUrl,
        expires_in: 300,
      });
    }
    if (action === "admin_list_requests_session") {
      await adminSession(String(body.username), String(body.token));
      const { data, error } = await supabase.from("shoir_subscription_requests")
        .select("*").eq("status", "Pending").order("requested_at", {
          ascending: true,
        });
      if (error) throw error;
      return sendResponse({ ok: true, requests: data || [] });
    }

    if (
      action === "admin_approve_session" ||
      action === "admin_approve_latest_session" ||
      action === "admin_approve_target_session"
    ) {
      await adminSession(String(body.username), String(body.token));
      let query = supabase.from("shoir_subscription_requests").select("*").eq(
        "status",
        "Pending",
      );
      if (action === "admin_approve_session") {
        query = query.eq("id", Number(body.request_id));
      } else if (action === "admin_approve_target_session") {
        query = query.eq(
          "username_lc",
          String(body.target_username || "").trim().toLowerCase(),
        ).eq("request_type", String(body.request_type || "New"));
      }
      query = query.order("requested_at", { ascending: false }).limit(1);
      const { data, error } = await query;
      if (error) throw error;
      const request = data?.[0];
      if (!request) return sendResponse({ error: "Request not found." }, 404);
      if (
        request.request_type === "New" &&
        (
          request.terms_accepted !== true ||
          request.terms_version !== TERMS_VERSION ||
          request.privacy_policy_version !== PRIVACY_POLICY_VERSION ||
          request.refund_policy_version !== REFUND_POLICY_VERSION ||
          request.cookie_policy_version !== COOKIE_POLICY_VERSION ||
          !request.accepted_at
        )
      ) {
        return sendResponse({
          error:
            "This registration has no confirmed current beta-terms and policy acknowledgement. Do not approve it; have the user resubmit.",
        }, 409);
      }
      const { data: decision, error: decisionError } = await supabase.rpc(
        "shoir_finalize_subscription_request",
        { p_request_id: request.id, p_decision: "Approved" },
      );
      if (decisionError) {
        if (decisionError.code === "P0002") {
          return sendResponse(
            { error: "Pending request not found or already processed." },
            409,
          );
        }
        throw decisionError;
      }
      let referralStatusUpdated = true;
      if (request.request_type === "New") {
        const { error: referralStatusError } = await supabase
          .from("shoir_referrals")
          .update({
            status: "Qualified",
            qualified_at: new Date().toISOString(),
          })
          .eq("referred_username_lc", request.username_lc)
          .eq("status", "Pending");
        if (referralStatusError) {
          referralStatusUpdated = false;
          console.error(
            "Approved account, but referral qualification update failed.",
            referralStatusError.code || "unknown",
          );
        }
      }
      const decisionBody = decision && typeof decision === "object"
        ? decision as Record<string, unknown>
        : { ok: true, request_id: request.id };
      return sendResponse({
        ...decisionBody,
        referral_status_updated: referralStatusUpdated,
      });
    }

    if (action === "admin_decline_session") {
      await adminSession(String(body.username), String(body.token));
      const id = Number(body.request_id);
      if (!Number.isSafeInteger(id) || id <= 0) {
        return sendResponse({ error: "Invalid request identifier." }, 400);
      }
      const { data: declinedRequest, error: declinedRequestError } =
        await supabase
          .from("shoir_subscription_requests").select(
            "username_lc,request_type",
          )
          .eq("id", id).eq("status", "Pending").maybeSingle();
      if (declinedRequestError) throw declinedRequestError;
      if (!declinedRequest) {
        return sendResponse({
          error: "Pending request not found or already processed.",
        }, 404);
      }
      const { data: decision, error: decisionError } = await supabase.rpc(
        "shoir_finalize_subscription_request",
        { p_request_id: id, p_decision: "Declined" },
      );
      if (decisionError) {
        if (decisionError.code === "P0002") {
          return sendResponse(
            { error: "Pending request not found or already processed." },
            404,
          );
        }
        throw decisionError;
      }
      let referralStatusUpdated = true;
      if (declinedRequest.request_type === "New") {
        const { error: referralStatusError } = await supabase
          .from("shoir_referrals")
          .update({ status: "Declined" })
          .eq("referred_username_lc", declinedRequest.username_lc)
          .eq("status", "Pending");
        if (referralStatusError) {
          referralStatusUpdated = false;
          console.error(
            "Declined request, but referral status update failed.",
            referralStatusError.code || "unknown",
          );
        }
      }
      const decisionBody = decision && typeof decision === "object"
        ? decision as Record<string, unknown>
        : { ok: true, request_id: id };
      return sendResponse({
        ...decisionBody,
        referral_status_updated: referralStatusUpdated,
      });
    }

    return sendResponse({ error: "Unknown action." }, 400);
  } catch (err: unknown) {
    const failure = publicErrorFor(err);
    return sendResponse({ error: failure.message }, failure.status);
  }
});
