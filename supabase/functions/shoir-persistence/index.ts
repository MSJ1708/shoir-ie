import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";
import {
  corsHeadersForOrigin,
  hasCanonicalMasterAdminInvariant,
  isAllowedBrowserOrigin,
  normalizeWorkspaceStateJson,
  publicErrorFor,
  readBoundedJsonObject,
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
      if (!referralCode || referralCode.startsWith("AFF-")) {
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
          return sendResponse({ error: "Self-referrals are not allowed." }, 400);
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
        return sendResponse({ error: "Select a valid subscription tier." }, 400);
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
      // Validate before upsert so malformed/oversized state never replaces the last valid save.
      const workspaceState = normalizeWorkspaceStateJson(body.state_json);
      const { error } = await supabase.from("shoir_workspace_states").upsert({
        username_lc: String(body.username).trim().toLowerCase(),
        state_json: workspaceState,
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
