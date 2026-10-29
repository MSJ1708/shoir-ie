import {
  createRemoteJWKSet,
  type JWTPayload,
  jwtVerify,
} from "npm:jose@6.2.13";

export const MAX_OIDC_ID_TOKEN_CHARS = 16_384;
const MAX_ID_TOKEN_AGE_SECONDS = 10 * 60;
const CLOCK_TOLERANCE_SECONDS = 5;

export interface OidcVerifierConfig {
  enabled: boolean;
  ready: boolean;
  issuer: string;
  clientId: string;
  jwksUrl: string;
  requireMfa: boolean;
  allowedMfaAmr: string[];
  allowedMfaAcr: string[];
}

export interface VerifiedOidcIdentity {
  issuer: string;
  subject: string;
  email: string;
  mfaVerified: boolean;
}

export class OidcVerificationError extends Error {
  readonly code: string;
  constructor(code: string) {
    super("The identity-provider response could not be verified.");
    this.name = "OidcVerificationError";
    this.code = code;
  }
}

function parseCsv(value: string | undefined, fallback: string[]): string[] {
  const values = (value || "").split(",").map((part) => part.trim()).filter(
    Boolean,
  );
  return [
    ...new Set(
      (values.length ? values : fallback).map((part) => part.toLowerCase()),
    ),
  ];
}

function httpsPublicDnsUrl(raw: string | undefined, label: string): URL | null {
  if (!raw?.trim()) return null;
  let url: URL;
  try {
    url = new URL(raw.trim());
  } catch {
    throw new Error(label + " must be a valid HTTPS URL.");
  }
  const host = url.hostname.toLowerCase();
  if (
    url.protocol !== "https:" ||
    url.username !== "" ||
    url.password !== "" ||
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    host.startsWith("[") ||
    /^\d{1,3}(?:\.\d{1,3}){3}$/.test(host)
  ) {
    throw new Error(
      label + " must use a public HTTPS DNS host without credentials.",
    );
  }
  return url;
}

export function readOidcVerifierConfig(
  getEnv: (name: string) => string | undefined = (name) => Deno.env.get(name),
): OidcVerifierConfig {
  const enabled =
    (getEnv("SHOIR_OIDC_ENABLED") || "").trim().toLowerCase() === "true";
  const issuer = (getEnv("SHOIR_OIDC_ISSUER") || "").trim();
  const clientId = (getEnv("SHOIR_OIDC_CLIENT_ID") || "").trim();
  const jwksUrl = (getEnv("SHOIR_OIDC_JWKS_URL") || "").trim();
  const requireMfa =
    (getEnv("SHOIR_OIDC_REQUIRE_MFA") || "").trim().toLowerCase() === "true";
  const allowedMfaAmr = parseCsv(getEnv("SHOIR_OIDC_MFA_AMR_VALUES"), ["mfa"]);
  const allowedMfaAcr = parseCsv(getEnv("SHOIR_OIDC_MFA_ACR_VALUES"), []);

  if (!enabled) {
    return {
      enabled: false,
      ready: false,
      issuer: "",
      clientId: "",
      jwksUrl: "",
      requireMfa,
      allowedMfaAmr,
      allowedMfaAcr,
    };
  }

  if (!issuer || !clientId || !jwksUrl) {
    return {
      enabled: true,
      ready: false,
      issuer: "",
      clientId: "",
      jwksUrl: "",
      requireMfa,
      allowedMfaAmr,
      allowedMfaAcr,
    };
  }

  const issuerUrl = httpsPublicDnsUrl(issuer, "OIDC issuer");
  const jwksEndpoint = httpsPublicDnsUrl(jwksUrl, "OIDC JWKS endpoint");
  if (
    !issuerUrl || !jwksEndpoint || issuerUrl.hostname !== jwksEndpoint.hostname
  ) {
    throw new Error(
      "OIDC issuer and JWKS endpoint must use the same approved HTTPS host.",
    );
  }

  return {
    enabled: true,
    ready: true,
    issuer,
    clientId,
    jwksUrl: jwksEndpoint.href,
    requireMfa,
    allowedMfaAmr,
    allowedMfaAcr,
  };
}

function isVerifiedEmail(value: unknown): value is string {
  return typeof value === "string" &&
    value.trim().length <= 320 &&
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export function identityFromVerifiedClaims(
  payload: JWTPayload,
  config: OidcVerifierConfig,
): VerifiedOidcIdentity {
  const subject = typeof payload.sub === "string" ? payload.sub.trim() : "";
  const email = typeof payload.email === "string"
    ? payload.email.trim().toLowerCase()
    : "";
  if (!subject || subject.length > 512) {
    throw new OidcVerificationError("invalid_subject");
  }
  if (!isVerifiedEmail(email) || payload.email_verified !== true) {
    throw new OidcVerificationError("unverified_email");
  }

  const amr = Array.isArray(payload.amr)
    ? payload.amr.filter((value): value is string => typeof value === "string")
      .map((value) => value.toLowerCase())
    : [];
  const acr = typeof payload.acr === "string" ? payload.acr.toLowerCase() : "";
  const mfaVerified =
    amr.some((value) => config.allowedMfaAmr.includes(value)) ||
    (acr !== "" && config.allowedMfaAcr.includes(acr));
  if (config.requireMfa && !mfaVerified) {
    throw new OidcVerificationError("mfa_claim_missing");
  }

  return { issuer: config.issuer, subject, email, mfaVerified };
}

let cachedJwksUrl = "";
let cachedJwks: ReturnType<typeof createRemoteJWKSet> | null = null;

export async function verifyOidcIdToken(
  idToken: string,
  config: OidcVerifierConfig,
  keyResolver?: ReturnType<typeof createRemoteJWKSet>,
): Promise<VerifiedOidcIdentity> {
  if (!config.enabled || !config.ready) {
    throw new OidcVerificationError("oidc_not_configured");
  }
  if (
    typeof idToken !== "string" ||
    idToken.length < 32 ||
    idToken.length > MAX_OIDC_ID_TOKEN_CHARS ||
    idToken.split(".").length !== 3
  ) {
    throw new OidcVerificationError("invalid_token_shape");
  }

  let resolver = keyResolver;
  if (!resolver) {
    if (!cachedJwks || cachedJwksUrl !== config.jwksUrl) {
      cachedJwks = createRemoteJWKSet(new URL(config.jwksUrl), {
        timeoutDuration: 5_000,
        cooldownDuration: 30_000,
        cacheMaxAge: 10 * 60_000,
      });
      cachedJwksUrl = config.jwksUrl;
    }
    resolver = cachedJwks;
  }

  let payload: JWTPayload;
  try {
    const verified = await jwtVerify(idToken, resolver, {
      issuer: config.issuer,
      audience: config.clientId,
      algorithms: ["RS256", "ES256"],
      clockTolerance: CLOCK_TOLERANCE_SECONDS,
      maxTokenAge: MAX_ID_TOKEN_AGE_SECONDS,
      requiredClaims: [
        "iss",
        "sub",
        "aud",
        "exp",
        "iat",
        "email",
        "email_verified",
      ],
    });
    payload = verified.payload;
  } catch {
    throw new OidcVerificationError("signature_or_standard_claims_invalid");
  }

  return identityFromVerifiedClaims(payload, config);
}

export async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}

export function escapePostgrestLikeLiteral(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/%/g, "\\%").replace(/_/g, "\\_");
}
