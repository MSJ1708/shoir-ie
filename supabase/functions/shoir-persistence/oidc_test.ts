import {
  createLocalJWKSet,
  exportJWK,
  generateKeyPair,
  SignJWT,
} from "npm:jose@6.2.13";
import {
  identityFromVerifiedClaims,
  MAX_OIDC_ID_TOKEN_CHARS,
  OidcVerificationError,
  readOidcVerifierConfig,
  verifyOidcIdToken,
  type OidcVerifierConfig,
} from "./oidc.ts";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

async function expectOidcError(
  action: () => unknown | Promise<unknown>,
  code: string,
): Promise<void> {
  try {
    await action();
  } catch (error) {
    assert(error instanceof OidcVerificationError, "Expected OidcVerificationError.");
    assert(error.code === code, `Expected ${code}, received ${error.code}.`);
    return;
  }
  throw new Error("Expected OIDC validation to reject the input.");
}

const ISSUER = "https://idp.example.invalid";
const CLIENT_ID = "shoir-test-client";
const JWKS_URL = "https://idp.example.invalid/.well-known/jwks.json";

const config: OidcVerifierConfig = {
  enabled: true,
  ready: true,
  issuer: ISSUER,
  clientId: CLIENT_ID,
  jwksUrl: JWKS_URL,
  requireMfa: false,
  allowedMfaAmr: ["mfa"],
  allowedMfaAcr: [],
};

const { privateKey, publicKey } = await generateKeyPair("RS256");
const publicJwk = await exportJWK(publicKey);
publicJwk.kid = "oidc-test-key";
publicJwk.alg = "RS256";
publicJwk.use = "sig";
const localJwks = createLocalJWKSet({ keys: [publicJwk] });

async function token(
  overrides: Record<string, unknown> = {},
  opts: { issuer?: string; audience?: string; expiresIn?: string; alg?: string } = {},
): Promise<string> {
  const body = {
    email: "approved-user@example.invalid",
    email_verified: true,
    amr: ["pwd", "mfa"],
    ...overrides,
  };
  const alg = opts.alg || "RS256";
  const builder = new SignJWT(body)
    .setProtectedHeader({ alg, kid: "oidc-test-key" })
    .setIssuer(opts.issuer || ISSUER)
    .setAudience(opts.audience || CLIENT_ID)
    .setSubject("subject-synthetic-001")
    .setIssuedAt()
    .setExpirationTime(opts.expiresIn || "5m");
  return await builder.sign(privateKey);
}

Deno.test("OIDC configuration is disabled or incomplete by default", () => {
  const disabled = readOidcVerifierConfig(() => undefined);
  assert(!disabled.enabled && !disabled.ready, "OIDC must stay disabled without explicit configuration.");

  const partial = readOidcVerifierConfig((name) => ({
    SHOIR_OIDC_ENABLED: "true",
    SHOIR_OIDC_ISSUER: ISSUER,
  }[name]));
  assert(partial.enabled && !partial.ready, "Partial OIDC configuration must not enable authentication.");
  assert(partial.issuer === "" && partial.clientId === "", "Partial OIDC must not expose usable configuration.");
});

Deno.test("OIDC configuration requires HTTPS DNS endpoints and same configured host", () => {
  const values: Record<string, string> = {
    SHOIR_OIDC_ENABLED: "true",
    SHOIR_OIDC_ISSUER: ISSUER,
    SHOIR_OIDC_CLIENT_ID: CLIENT_ID,
    SHOIR_OIDC_JWKS_URL: JWKS_URL,
    SHOIR_OIDC_REQUIRE_MFA: "false",
  };
  const valid = readOidcVerifierConfig((name) => values[name]);
  assert(valid.ready, "Complete HTTPS OIDC config should be ready.");
  assert(valid.issuer === ISSUER && valid.clientId === CLIENT_ID, "OIDC configuration values differ.");

  values.SHOIR_OIDC_ISSUER = "http://idp.example.invalid";
  let rejectedHttp = false;
  try {
    readOidcVerifierConfig((name) => values[name]);
  } catch {
    rejectedHttp = true;
  }
  assert(rejectedHttp, "OIDC issuer must reject plaintext HTTP.");

  values.SHOIR_OIDC_ISSUER = ISSUER;
  values.SHOIR_OIDC_JWKS_URL = "https://keys.example.invalid/jwks.json";
  let rejectedCrossHost = false;
  try {
    readOidcVerifierConfig((name) => values[name]);
  } catch {
    rejectedCrossHost = true;
  }
  assert(rejectedCrossHost, "OIDC issuer/JWKS host mismatch must be rejected.");
});

Deno.test("OIDC ID token verifies signature, issuer, audience, and verified email", async () => {
  const idToken = await token();
  const identity = await verifyOidcIdToken(
    idToken,
    config,
    localJwks as never,
  );
  assert(identity.issuer === ISSUER, "Verified issuer was not returned.");
  assert(identity.subject === "subject-synthetic-001", "Verified subject was not returned.");
  assert(identity.email === "approved-user@example.invalid", "Verified email was not normalized.");
  assert(identity.mfaVerified, "MFA claim should be recognized.");

  await expectOidcError(
    async async async () => verifyOidcIdToken(
      await token({}, { issuer: "https://attacker.example.invalid" }),
      config,
      localJwks as never,
    ),
    "signature_or_standard_claims_invalid",
  );

  await expectOidcError(
    async async async () => verifyOidcIdToken(
      await token({}, { audience: "different-client" }),
      config,
      localJwks as never,
    ),
    "signature_or_standard_claims_invalid",
  );
});

Deno.test("OIDC rejects expired, overlong, unverified-email, and missing-MFA tokens", async () => {
  await expectOidcError(
    async () => await verifyOidcIdToken(
      await token({}, { expiresIn: "-1s" }),
      config,
      localJwks as never,
    ),
    "signature_or_standard_claims_invalid",
  );

  await expectOidcError(
    () => verifyOidcIdToken("x".repeat(MAX_OIDC_ID_TOKEN_CHARS + 1), config, localJwks as never),
    "invalid_token_shape",
  );

  await expectOidcError(
    async async async () => verifyOidcIdToken(
      await token({ email_verified: false }),
      config,
      localJwks as never,
    ),
    "unverified_email",
  );

  const mfaConfig = { ...config, requireMfa: true, allowedMfaAmr: ["mfa"], allowedMfaAcr: [] };
  await expectOidcError(
    async async async () => verifyOidcIdToken(
      await token({ amr: ["pwd"] }),
      mfaConfig,
      localJwks as never,
    ),
    "mfa_claim_missing",
  );
});

Deno.test("unverified claims cannot be accepted by the claim mapper", () => {
  const claims = {
    iss: ISSUER,
    sub: "synthetic-subject",
    aud: CLIENT_ID,
    exp: Math.floor(Date.now() / 1000) + 300,
    iat: Math.floor(Date.now() / 1000),
    email: "user@example.invalid",
    email_verified: false,
    amr: [],
  };
  try {
    identityFromVerifiedClaims(claims, config);
    throw new Error("Expected unverified email rejection.");
  } catch (error) {
    assert(error instanceof OidcVerificationError, "Expected OIDC claim rejection.");
    assert(error.code === "unverified_email", "Wrong error for an unverified email.");
  }
});
