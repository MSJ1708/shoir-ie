import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";
import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  isAllowedBrowserOrigin,
} from "./security.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);
const ITERATIONS = 200_000;
const PAYMENT_PROOF_BUCKET = "subscription-payment-proofs";
const MAX_PAYMENT_PROOF_BYTES = 512 * 1024;

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
  const encoded = String(body.proof_base64 || "");
  if (!encoded) return null;
  const contentType = String(body.proof_content_type || "").toLowerCase();
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
    headers: corsHeadersForOrigin(origin),
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
  if (
    requiredScope === "workspace" &&
    !(row.username_lc === "sho" && row.role === "Enterprise Admin") &&
    isExpired(row.subscription_expires_at)
  ) throw new Error("SUBSCRIPTION_EXPIRED");
  return row;
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

Deno.serve(async (req) => {
  const origin = req.headers.get("origin");
  if (!isAllowedBrowserOrigin(origin)) {
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
      headers: corsHeadersForOrigin(origin),
    });
  }
  try {
    const body = await req.json();
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
      // Never mutate the reserved administrator while logging in.
      // Drift is a controlled operational incident; fail closed without revealing
      // row details and correct it only through a reviewed administrative procedure.
      const isProtectedMasterAdmin = row.username_lc === "sho";
      if (
        isProtectedMasterAdmin &&
        !hasCanonicalMasterAdminInvariant(row as Record<string, unknown>)
      ) {
        return sendResponse({
          error: "The protected administrator configuration requires manual review.",
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

    if (action === "logout") {
      const token = String(body.token || "").trim();
      const usernameLc = String(body.username || "").trim().toLowerCase();
      if (!token || !usernameLc) return sendResponse({ ok: true, revoked: false });
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

    if (action === "workspace_load") {
      await getSession(String(body.token), String(body.username));
      const { data, error } = await supabase.from("shoir_workspace_states")
        .select("state_json,updated_at").eq(
          "username_lc",
          String(body.username).trim().toLowerCase(),
        ).maybeSingle();
      if (error) throw error;
      return sendResponse({
        ok: true,
        state_json: data?.state_json || null,
        updated_at: data?.updated_at || null,
      });
    }
    if (action === "workspace_save") {
      await getSession(String(body.token), String(body.username));
      const { error } = await supabase.from("shoir_workspace_states").upsert({
        username_lc: String(body.username).trim().toLowerCase(),
        state_json: String(body.state_json || "{}"),
        updated_at: new Date().toISOString(),
      }, { onConflict: "username_lc" });
      if (error) throw error;
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
        return sendResponse({ error: "Invalid private payment proof path." }, 400);
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
      const existing = await getAccount(request.username);
      const { data: pendingCred } = await supabase.from(
        "shoir_pending_credentials",
      ).select("*").eq("username_lc", request.username_lc).maybeSingle();
      const now = new Date().toISOString();
      const expiry = request.request_type === "Renewal" && existing
        ? expiry30(existing.subscription_expires_at)
        : expiry30();
      const passwordHash = existing?.password_hash ||
        pendingCred?.password_hash;
      if (!passwordHash) {
        return sendResponse({
          error: "Pending registration credentials are missing.",
        }, 500);
      }
      const payload = {
        username: request.username,
        username_lc: request.username_lc,
        password_hash: passwordHash,
        role: existing?.role || "User",
        tier: request.tier || existing?.tier || "Starter Tier ($29)",
        email: request.email || existing?.email || "",
        created_at: existing?.created_at || now,
        subscription_expires_at: expiry,
        linkedin: existing?.linkedin || null,
        github: existing?.github || null,
        about_me: existing?.about_me || null,
        affiliate_code: existing?.affiliate_code || null,
        active: true,
        updated_at: now,
      };
      const { error: accountErr } = await supabase.from("shoir_accounts")
        .upsert(payload, { onConflict: "username" });
      if (accountErr) throw accountErr;
      await supabase.from("shoir_subscription_requests").update({
        status: "Approved",
        approved_at: now,
        updated_at: now,
      }).eq("id", request.id);
      return sendResponse({
        ok: true,
        username: request.username,
        expires_at: expiry,
        tier: payload.tier,
        email: payload.email,
        request_id: request.id,
      });
    }

    if (action === "admin_decline_session") {
      await adminSession(String(body.username), String(body.token));
      const id = Number(body.request_id);
      const { error } = await supabase.from("shoir_subscription_requests")
        .update({ status: "Declined", updated_at: new Date().toISOString() })
        .eq("id", id);
      if (error) throw error;
      return sendResponse({ ok: true });
    }

    return sendResponse({ error: "Unknown action." }, 400);
  } catch (err: unknown) {
    return sendResponse(
      { error: err instanceof Error ? err.message : String(err) },
      500,
    );
  }
});
