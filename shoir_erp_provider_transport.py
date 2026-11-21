"""Provider-aware, read-only SAP S/4HANA and Oracle Fusion transport.

Secrets are resolved server-side from an opaque credential reference. SAP uses
its configured OAuth 2.0 client-credentials flow; Oracle Fusion Applications uses
signed JWT User Assertion plus client assertion. Requests use pinned HTTPS GET,
strict same-origin pagination, bounded response sizes and no automatic retries.
This module does not create provider tenants, credentials, network routes or live acceptance.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import shoir_erp_connectors as erp
from shoir_rest_connector import (
    ConnectorFailure,
    _PinnedHTTPSConnection,
    _resolve_pinned_ip,
)


_MAX_TOKEN_BYTES = 64 * 1024
_MAX_JSON_BYTES = 2 * 1024 * 1024
_MAX_TIMEOUT_SECONDS = 10.0
_ALLOWED_EXPIRY_SECONDS = 24 * 60 * 60


class ERPProviderTransportError(RuntimeError):
    """Sanitized provider transport failure; never includes URLs or secret values."""


@dataclass(frozen=True)
class OAuthClientCredentials:
    token_url: str
    client_id: str
    client_secret: str
    scope: str = ""


@dataclass(frozen=True)
class OracleJWTAssertionCredentials:
    token_url: str
    identity_domain_url: str
    client_id: str
    assertion_issuer: str
    client_assertion_subject: str
    user_subject: str
    signing_key_id: str
    signing_private_key_pem: str
    scope: str
    private_key: Any


class PinnedHTTPSJsonClient:
    """Small HTTP client that pins each TLS connection to a vetted DNS result."""

    def __init__(
        self,
        allowed_hosts: set[tuple[str, int]],
        *,
        approved_private_networks: tuple[Any, ...] = (),
        timeout_seconds: float = 8.0,
        max_response_bytes: int = _MAX_JSON_BYTES,
        resolver: Callable[..., Any] | None = None,
    ) -> None:
        if not 0.5 <= float(timeout_seconds) <= _MAX_TIMEOUT_SECONDS:
            raise ValueError("timeout_seconds must be between 0.5 and 10.")
        if not 1 <= int(max_response_bytes) <= _MAX_JSON_BYTES:
            raise ValueError("max_response_bytes is outside the supported bound.")
        self.allowed_hosts = set(allowed_hosts)
        self.approved_private_networks = tuple(approved_private_networks)
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)
        self.resolver = resolver

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
        max_response_bytes: int | None = None,
    ) -> tuple[int, str, bytes]:
        method = str(method or "").upper()
        if method not in {"GET", "POST"}:
            raise ERPProviderTransportError("The provider transport permits GET data reads and OAuth token POST only.")
        if body is not None and len(body) > 16 * 1024:
            raise ERPProviderTransportError("The provider request body exceeds its size limit.")
        requested_limit = self.max_response_bytes if max_response_bytes is None else max_response_bytes
        if (
            isinstance(requested_limit, bool)
            or not isinstance(requested_limit, int)
            or not 1 <= requested_limit <= self.max_response_bytes
        ):
            raise ERPProviderTransportError("The provider response size limit is invalid.")
        limit = requested_limit
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
            port = parsed.port or 443
        except (ValueError, UnicodeError) as exc:
            raise ERPProviderTransportError("The provider URL is invalid.") from exc
        if (
            parsed.scheme.lower() != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.fragment
            or len(url) > 4096
            or (host, port) not in self.allowed_hosts
            or not 1 <= port <= 65535
        ):
            raise ERPProviderTransportError("The provider URL is not an approved HTTPS destination.")
        path = parsed.path or "/"
        if not path.startswith("/") or chr(92) in path or any(ord(c) < 32 for c in path):
            raise ERPProviderTransportError("The provider URL path is invalid.")
        try:
            pinned_ip = _resolve_pinned_ip(
                host,
                port,
                self.approved_private_networks,
                resolver=self.resolver,
            )
        except ConnectorFailure as exc:
            raise ERPProviderTransportError("The provider destination failed the network-address policy.") from exc
        target = path + (("?" + parsed.query) if parsed.query else "")
        connection = _PinnedHTTPSConnection(
            host=host,
            port=port,
            pinned_ip=pinned_ip,
            timeout=self.timeout_seconds,
        )
        try:
            request_headers = {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "User-Agent": "Shoir-IE-ERP-ReadOnly/1.0",
                **dict(headers),
            }
            connection.request(method, target, body=body, headers=request_headers)
            response = connection.getresponse()
            status = int(response.status)
            content_type = str(response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
            length_header = response.getheader("Content-Length")
            if length_header:
                if not str(length_header).isdigit() or int(length_header) > limit:
                    raise ERPProviderTransportError("The provider response exceeds the configured size limit.")
            payload = response.read(limit + 1)
            if len(payload) > limit:
                raise ERPProviderTransportError("The provider response exceeds the configured size limit.")
            return status, content_type, payload
        except ERPProviderTransportError:
            raise
        except Exception as exc:
            # Do not surface the underlying exception: it can contain a URL,
            # bearer token, authorization header or provider response fragment.
            raise ERPProviderTransportError("The provider request failed; inspect approved redacted server diagnostics.") from exc
        finally:
            connection.close()


class _OAuthTokenCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[str, float]] = {}

    def get_or_create(
        self,
        cache_key: str,
        create: Callable[[], tuple[str, int]],
    ) -> str:
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(cache_key)
            if cached and cached[1] > now:
                return cached[0]
            token, expires_in = create()
            if not token or not 1 <= expires_in <= _ALLOWED_EXPIRY_SECONDS:
                raise ERPProviderTransportError("The identity provider returned an invalid access-token lifetime.")
            safety_margin = min(60.0, max(1.0, expires_in * 0.1))
            self._entries[cache_key] = (token, now + max(1.0, expires_in - safety_margin))
            return token


class OAuth2ClientCredentialsTransport:
    """Common OAuth2 and bounded HTTPS transport used by supported cloud adapters."""

    provider: str

    def __init__(
        self,
        *,
        allowed_hosts: set[tuple[str, int]],
        credential_resolver: Callable[[str], Mapping[str, Any]],
        approved_private_networks: tuple[Any, ...] = (),
        timeout_seconds: float = 8.0,
        resolver: Callable[..., Any] | None = None,
        http_client: PinnedHTTPSJsonClient | None = None,
    ) -> None:
        self.allowed_hosts = set(allowed_hosts)
        self.credential_resolver = credential_resolver
        self.http = http_client or PinnedHTTPSJsonClient(
            allowed_hosts,
            approved_private_networks=approved_private_networks,
            timeout_seconds=timeout_seconds,
            resolver=resolver,
        )
        self._tokens = _OAuthTokenCache()

    @staticmethod
    def _safe_secret(value: Any, field: str, maximum: int = 4096) -> str:
        text = str(value or "").strip()
        if not text or len(text) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in text):
            raise ERPProviderTransportError(f"The server-side {field} setting is missing or invalid.")
        return text

    def _credentials(self, connection: erp.ERPConnectionProfile) -> OAuthClientCredentials:
        try:
            raw = self.credential_resolver(connection.credential_ref)
        except Exception as exc:
            raise ERPProviderTransportError("The server-side credential reference could not be resolved.") from exc
        if not isinstance(raw, Mapping):
            raise ERPProviderTransportError("The server-side credential reference has an invalid contract.")
        token_url = self._safe_secret(raw.get("token_url"), "OAuth token URL", 2048)
        client_id = self._safe_secret(raw.get("client_id"), "OAuth client ID")
        client_secret = self._safe_secret(raw.get("client_secret"), "OAuth client secret")
        scope = str(raw.get("scope") or "").strip()
        if len(scope) > 1024 or any(ord(char) < 32 or ord(char) == 127 for char in scope):
            raise ERPProviderTransportError("The server-side OAuth scope is invalid.")
        try:
            parsed = urlsplit(token_url)
            host = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
            port = parsed.port or 443
        except (ValueError, UnicodeError) as exc:
            raise ERPProviderTransportError("The OAuth token URL is invalid.") from exc
        if (
            parsed.scheme.lower() != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (host, port) not in self.allowed_hosts
        ):
            raise ERPProviderTransportError("The OAuth token URL is not an approved HTTPS destination.")
        return OAuthClientCredentials(token_url, client_id, client_secret, scope)

    def _access_token(
        self,
        connection: erp.ERPConnectionProfile,
        credentials: OAuthClientCredentials,
    ) -> str:
        # Include a one-way fingerprint of the secret so rotation cannot reuse
        # a token cached under the previous credential. Never persist or log it.
        secret_fingerprint = hashlib.sha256(credentials.client_secret.encode("utf-8")).hexdigest()
        cache_key = hashlib.sha256(
            (
                connection.credential_ref + "|" + connection.product_id + "|"
                + credentials.token_url + "|" + credentials.client_id + "|"
                + credentials.scope + "|" + secret_fingerprint
            ).encode("utf-8")
        ).hexdigest()

        def create() -> tuple[str, int]:
            basic = base64.b64encode(
                (credentials.client_id + ":" + credentials.client_secret).encode("utf-8")
            ).decode("ascii")
            form = {"grant_type": "client_credentials"}
            if credentials.scope:
                form["scope"] = credentials.scope
            status, content_type, raw = self.http.request(
                "POST",
                credentials.token_url,
                headers={
                    "Authorization": "Basic " + basic,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body=urlencode(form).encode("ascii"),
                max_response_bytes=_MAX_TOKEN_BYTES,
            )
            if 300 <= status < 400:
                raise ERPProviderTransportError("OAuth redirects are blocked.")
            if status in {401, 403}:
                raise ERPProviderTransportError("The OAuth provider rejected the configured client credentials.")
            if status != 200 or "json" not in content_type:
                raise ERPProviderTransportError("The OAuth provider did not return a valid token response.")
            try:
                data = json.loads(raw.decode("utf-8"))
                token = self._safe_secret(data.get("access_token"), "OAuth access token", 8192)
                token_type = str(data.get("token_type") or "Bearer").strip().casefold()
                expires_raw = data.get("expires_in")
                expires_float = float(expires_raw)
                if not math.isfinite(expires_float) or not expires_float.is_integer():
                    raise ValueError("expires_in is invalid")
                expires_in = int(expires_float)
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
                raise ERPProviderTransportError("The OAuth token response is malformed.") from exc
            if token_type != "bearer":
                raise ERPProviderTransportError("The OAuth provider returned an unsupported token type.")
            return token, expires_in

        return self._tokens.get_or_create(cache_key, create)

    @staticmethod
    def _resource_url(connection: erp.ERPConnectionProfile, source_path: str) -> str:
        try:
            path = erp._validate_relative_path(source_path, "source path")
        except Exception as exc:
            raise ERPProviderTransportError("The configured provider resource path is invalid.") from exc
        base = urlsplit(connection.base_url)
        if (
            base.scheme.lower() != "https"
            or not base.hostname
            or base.username
            or base.password
            or base.query
            or base.fragment
        ):
            raise ERPProviderTransportError("The configured provider base URL is invalid.")
        return connection.base_url.rstrip("/") + "/" + path.lstrip("/")

    def _validate_page_url(self, next_url: str, original_url: str) -> str:
        resolved = urljoin(original_url, next_url)
        parsed = urlsplit(resolved)
        original = urlsplit(original_url)
        try:
            host = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
            port = parsed.port or 443
        except (ValueError, UnicodeError) as exc:
            raise ERPProviderTransportError("The provider pagination link is invalid.") from exc
        original_host = (original.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
        original_port = original.port or 443
        if (
            parsed.scheme.lower() != "https"
            or host != original_host
            or port != original_port
            or parsed.username
            or parsed.password
            or parsed.fragment
            or (host, port) not in self.allowed_hosts
            or parsed.path != original.path
            or len(resolved) > 4096
        ):
            raise ERPProviderTransportError("The provider pagination link left the approved resource origin or path.")
        return resolved

    def _get(self, url: str, token: str) -> tuple[dict[str, Any], str]:
        status, content_type, raw = self.http.request(
            "GET",
            url,
            headers={"Authorization": "Bearer " + token},
            max_response_bytes=_MAX_JSON_BYTES,
        )
        if 300 <= status < 400:
            raise ERPProviderTransportError("Provider redirects are blocked.")
        if status in {401, 407}:
            raise ERPProviderTransportError("The provider rejected the OAuth access token.")
        if status == 403:
            raise ERPProviderTransportError("The provider denied this read-only resource scope.")
        if status == 429:
            raise ERPProviderTransportError("The provider rate limit was reached; no retry was attempted.")
        if not 200 <= status < 300 or "json" not in content_type:
            raise ERPProviderTransportError("The provider did not return a successful JSON response.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ERPProviderTransportError("The provider returned malformed JSON.") from exc
        if not isinstance(payload, dict):
            raise ERPProviderTransportError("The provider response must be a JSON object.")
        return payload, url

    def get_json(
        self,
        connection: erp.ERPConnectionProfile,
        relative_path: str,
        *,
        page_token: str | None,
        page_size: int,
    ) -> erp.TransportPage:
        if connection.product_id not in self.supported_products:
            raise ERPProviderTransportError("This provider transport does not support the selected ERP product.")
        if not connection.enabled or not connection.read_only:
            raise ERPProviderTransportError("Only explicitly enabled read-only ERP connections are accepted.")
        credentials = self._credentials(connection)
        token = self._access_token(connection, credentials)
        initial_url = self._resource_url(connection, relative_path)
        current_url = initial_url
        if page_token:
            current_url = self._page_url_from_token(page_token, initial_url, page_size)
        else:
            current_url = self._initial_page_url(initial_url, page_size)
        payload, _ = self._get(current_url, token)
        return self._page(payload, current_url, initial_url, page_size)

    def _page_url_from_token(self, token: str, initial_url: str, page_size: int) -> str:
        raise NotImplementedError

    def _initial_page_url(self, initial_url: str, page_size: int) -> str:
        raise NotImplementedError

    def _page(
        self,
        payload: dict[str, Any],
        current_url: str,
        initial_url: str,
        page_size: int,
    ) -> erp.TransportPage:
        raise NotImplementedError


class SAPODataOAuthTransport(OAuth2ClientCredentialsTransport):
    """SAP S/4HANA Cloud OData V2/V4 read transport."""

    provider = "SAP"
    supported_products = frozenset({"SAP_S4HANA_CLOUD_PUBLIC", "SAP_S4HANA_CLOUD_PRIVATE"})

    def _initial_page_url(self, initial_url: str, page_size: int) -> str:
        parts = urlsplit(initial_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["$top"] = str(page_size)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))

    def _page_url_from_token(self, token: str, initial_url: str, page_size: int) -> str:
        if len(token) > 4096 or any(ord(char) < 32 for char in token):
            raise ERPProviderTransportError("The SAP OData page token is invalid.")
        return self._validate_page_url(token, initial_url)

    def _page(self, payload: dict[str, Any], current_url: str, initial_url: str, page_size: int) -> erp.TransportPage:
        next_link = payload.get("@odata.nextLink") or payload.get("odata.nextLink")
        legacy = payload.get("d")
        if not next_link and isinstance(legacy, dict):
            next_link = legacy.get("__next")
        next_token = self._validate_page_url(str(next_link), initial_url) if next_link else None
        return erp.TransportPage(payload, next_token)


class OracleFusionOAuthTransport(OAuth2ClientCredentialsTransport):
    """Oracle Fusion Applications REST reads using the JWT User Assertion grant.

    This 2-legged flow sends both a signed user assertion (authorization grant)
    and a signed client assertion (client authentication). The private signing
    key is resolved only on the server and never leaves the process.
    """

    provider = "ORACLE"
    supported_products = frozenset({"ORACLE_FUSION_ERP", "ORACLE_FUSION_SCM"})
    USER_ASSERTION_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
    CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
    ASSERTION_TTL_SECONDS = 300

    def _credentials(self, connection: erp.ERPConnectionProfile) -> OracleJWTAssertionCredentials:
        try:
            raw = self.credential_resolver(connection.credential_ref)
        except Exception as exc:
            raise ERPProviderTransportError("The server-side Oracle credential reference could not be resolved.") from exc
        if not isinstance(raw, Mapping):
            raise ERPProviderTransportError("The server-side Oracle credential reference has an invalid contract.")

        token_url = self._safe_secret(raw.get("token_url"), "Oracle OAuth token URL", 2048)
        identity_domain_url = self._safe_secret(raw.get("identity_domain_url"), "Oracle identity-domain URL", 2048)
        client_id = self._safe_secret(raw.get("client_id"), "Oracle OAuth client ID", 512)
        assertion_issuer = self._safe_secret(raw.get("assertion_issuer"), "Oracle JWT assertion issuer", 512)
        client_assertion_subject = self._safe_secret(raw.get("client_assertion_subject"), "Oracle JWT client assertion subject", 512)
        user_subject = self._safe_secret(raw.get("user_subject"), "Oracle user assertion subject", 512)
        signing_key_id = self._safe_secret(raw.get("signing_key_id"), "Oracle JWT signing key ID", 200)
        scope = self._safe_secret(raw.get("scope"), "Oracle OAuth scope", 1024)
        private_key_pem = raw.get("signing_private_key_pem")
        if (
            not isinstance(private_key_pem, str)
            or not 100 <= len(private_key_pem) <= 16384
            or not private_key_pem.startswith("-----BEGIN ")
            or "PRIVATE KEY-----" not in private_key_pem[:100]
            or chr(0) in private_key_pem
        ):
            raise ERPProviderTransportError("The server-side Oracle RSA private-key PEM is missing or invalid.")

        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa

            private_key = serialization.load_pem_private_key(
                private_key_pem.encode("utf-8"),
                password=None,
            )
        except Exception as exc:
            raise ERPProviderTransportError("The Oracle assertion signing key could not be loaded.") from exc
        if not isinstance(private_key, rsa.RSAPrivateKey) or private_key.key_size < 2048:
            raise ERPProviderTransportError("Oracle JWT assertions require an RSA private key of at least 2048 bits.")

        try:
            token = urlsplit(token_url)
            token_host = (token.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
            token_port = token.port or 443
            audience = urlsplit(identity_domain_url)
            audience_host = (audience.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
            audience_port = audience.port or 443
        except (ValueError, UnicodeError) as exc:
            raise ERPProviderTransportError("The Oracle identity-domain or token URL is invalid.") from exc

        if (
            token.scheme.lower() != "https"
            or not token_host
            or token.username
            or token.password
            or token.query
            or token.fragment
            or token.path.rstrip("/") != "/oauth2/v1/token"
            or (token_host, token_port) not in self.allowed_hosts
            or not 1 <= token_port <= 65535
        ):
            raise ERPProviderTransportError("The Oracle OAuth token URL is not an approved HTTPS /oauth2/v1/token endpoint.")
        if (
            audience.scheme.lower() != "https"
            or not audience_host
            or audience.username
            or audience.password
            or audience.query
            or audience.fragment
            or audience.path not in ("", "/")
            or audience_host != token_host
            or audience_port != token_port
        ):
            raise ERPProviderTransportError("The Oracle JWT audience must be the same HTTPS identity-domain origin as the token endpoint.")

        return OracleJWTAssertionCredentials(
            token_url=token_url,
            identity_domain_url=identity_domain_url.rstrip("/") + "/",
            client_id=client_id,
            assertion_issuer=assertion_issuer,
            client_assertion_subject=client_assertion_subject,
            user_subject=user_subject,
            signing_key_id=signing_key_id,
            signing_private_key_pem=private_key_pem,
            scope=scope,
            private_key=private_key,
        )

    @staticmethod
    def _b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @classmethod
    def _signed_assertion(
        cls,
        credentials: OracleJWTAssertionCredentials,
        *,
        subject: str,
        now: int,
    ) -> str:
        import uuid
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        header = {
            "alg": "RS256",
            "kid": credentials.signing_key_id,
            "typ": "JWT",
        }
        claims = {
            "iss": credentials.assertion_issuer,
            "sub": subject,
            "aud": [credentials.identity_domain_url],
            "iat": now,
            "exp": now + cls.ASSERTION_TTL_SECONDS,
            "jti": uuid.uuid4().hex,
        }
        encoded_header = cls._b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        encoded_claims = cls._b64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signing_input = encoded_header + "." + encoded_claims
        signature = credentials.private_key.sign(
            signing_input.encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return signing_input + "." + cls._b64url(signature)

    def _access_token(
        self,
        connection: erp.ERPConnectionProfile,
        credentials: OracleJWTAssertionCredentials,
    ) -> str:
        key_fingerprint = hashlib.sha256(
            credentials.signing_private_key_pem.encode("utf-8")
        ).hexdigest()
        cache_key = hashlib.sha256(
            (
                connection.credential_ref + "|" + connection.product_id + "|"
                + credentials.token_url + "|" + credentials.identity_domain_url + "|"
                + credentials.client_id + "|" + credentials.assertion_issuer + "|"
                + credentials.client_assertion_subject + "|" + credentials.user_subject + "|"
                + credentials.signing_key_id + "|" + credentials.scope + "|" + key_fingerprint
            ).encode("utf-8")
        ).hexdigest()

        def create() -> tuple[str, int]:
            now = int(time.time())
            client_assertion = self._signed_assertion(
                credentials,
                subject=credentials.client_assertion_subject,
                now=now,
            )
            user_assertion = self._signed_assertion(
                credentials,
                subject=credentials.user_subject,
                now=now,
            )
            form = {
                "grant_type": self.USER_ASSERTION_GRANT,
                "assertion": user_assertion,
                "scope": credentials.scope,
                "client_assertion_type": self.CLIENT_ASSERTION_TYPE,
                "client_assertion": client_assertion,
                "client_id": credentials.client_id,
            }
            status, content_type, raw = self.http.request(
                "POST",
                credentials.token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                body=urlencode(form).encode("ascii"),
                max_response_bytes=_MAX_TOKEN_BYTES,
            )
            if 300 <= status < 400:
                raise ERPProviderTransportError("Oracle OAuth redirects are blocked.")
            if status in {401, 403}:
                raise ERPProviderTransportError("Oracle Identity Domain rejected the configured JWT assertions or scope.")
            if status != 200 or "json" not in content_type:
                raise ERPProviderTransportError("Oracle Identity Domain did not return a valid JWT-grant token response.")
            try:
                data = json.loads(raw.decode("utf-8"))
                token = self._safe_secret(data.get("access_token"), "Oracle OAuth access token", 8192)
                token_type = str(data.get("token_type") or "Bearer").strip().casefold()
                expires_raw = data.get("expires_in")
                expires_float = float(expires_raw)
                if not math.isfinite(expires_float) or not expires_float.is_integer():
                    raise ValueError("expires_in is invalid")
                expires_in = int(expires_float)
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
                raise ERPProviderTransportError("Oracle OAuth token response is malformed.") from exc
            if token_type != "bearer":
                raise ERPProviderTransportError("Oracle Identity Domain returned an unsupported token type.")
            return token, expires_in

        return self._tokens.get_or_create(cache_key, create)

    def _initial_page_url(self, initial_url: str, page_size: int) -> str:
        parts = urlsplit(initial_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["limit"] = str(page_size)
        query["offset"] = "0"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))

    def _page_url_from_token(self, token: str, initial_url: str, page_size: int) -> str:
        if token.startswith("offset:"):
            raw = token[7:]
            if not raw.isdigit() or len(raw) > 12:
                raise ERPProviderTransportError("The Oracle offset page token is invalid.")
            parts = urlsplit(initial_url)
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query["limit"] = str(page_size)
            query["offset"] = str(int(raw))
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
        if len(token) > 4096:
            raise ERPProviderTransportError("The Oracle next-page link is too long.")
        return self._validate_page_url(token, initial_url)

    def _page(self, payload: dict[str, Any], current_url: str, initial_url: str, page_size: int) -> erp.TransportPage:
        links = payload.get("links")
        next_link = None
        if isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and str(link.get("rel") or "").casefold() == "next":
                    next_link = link.get("href")
                    break
        if next_link:
            return erp.TransportPage(payload, self._validate_page_url(str(next_link), initial_url))
        if payload.get("hasMore") is True:
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                raise ERPProviderTransportError("Oracle reported more pages without a non-empty items page.")
            query = dict(parse_qsl(urlsplit(current_url).query, keep_blank_values=True))
            try:
                offset = int(query.get("offset", "0"))
            except (TypeError, ValueError) as exc:
                raise ERPProviderTransportError("The Oracle response offset is invalid.") from exc
            return erp.TransportPage(payload, "offset:" + str(offset + len(items)))
        return erp.TransportPage(payload, None)

def transport_for(
    product_id: str,
    *,
    allowed_hosts: set[tuple[str, int]],
    credential_resolver: Callable[[str], Mapping[str, Any]],
    approved_private_networks: tuple[Any, ...] = (),
    timeout_seconds: float = 8.0,
    resolver: Callable[..., Any] | None = None,
    http_client: PinnedHTTPSJsonClient | None = None,
) -> OAuth2ClientCredentialsTransport:
    """Return only a supported cloud-product transport; legacy products fail closed."""
    key = str(product_id or "").strip().upper()
    common = {
        "allowed_hosts": allowed_hosts,
        "credential_resolver": credential_resolver,
        "approved_private_networks": approved_private_networks,
        "timeout_seconds": timeout_seconds,
        "resolver": resolver,
        "http_client": http_client,
    }
    if key in SAPODataOAuthTransport.supported_products:
        return SAPODataOAuthTransport(**common)
    if key in OracleFusionOAuthTransport.supported_products:
        return OracleFusionOAuthTransport(**common)
    raise ERPProviderTransportError(
        "Provider transport is not implemented for this product; SAP ECC and Oracle EBS need separately reviewed legacy auth adapters."
    )


def read_provider_resource(
    connection: erp.ERPConnectionProfile,
    binding: erp.ERPResourceBinding,
    *,
    actor_id: str,
    active_workspace_id: str,
    allowed_hosts: set[tuple[str, int]],
    authorize: Callable[[str, str, str, str], bool] | None,
    credential_resolver: Callable[[str], Mapping[str, Any]],
    approved_private_networks: tuple[Any, ...] = (),
    timeout_seconds: float = 8.0,
    resolver: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Perform one explicitly authorized, read-only resource read and canonicalize it."""
    transport = transport_for(
        connection.product_id,
        allowed_hosts=allowed_hosts,
        credential_resolver=credential_resolver,
        approved_private_networks=approved_private_networks,
        timeout_seconds=timeout_seconds,
        resolver=resolver,
    )
    return erp.adapter_for(connection.product_id).read_resource(
        connection,
        binding,
        transport,
        actor_id=actor_id,
        active_workspace_id=active_workspace_id,
        allowed_hosts=allowed_hosts,
        authorize=authorize,
    )
