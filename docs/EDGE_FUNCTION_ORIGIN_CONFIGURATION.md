# Edge Function Browser-Origin Configuration

**Security rule:** Production and staging must use different origin allowlists. Never configure both the production and staging application hosts in the production project's `SHOIR_ALLOWED_BROWSER_ORIGINS`.

## Default behavior

The shared `shoir-persistence` handler reads `SHOIR_ALLOWED_BROWSER_ORIGINS` for each request. If this variable is unset, the code defaults to the production origin only:

`https://shoir-ie-app.streamlit.app`

A project configuration must contain exactly one canonical HTTPS origin, without a path, query string, fragment or credentials. The source accepts only the two currently verified hosts above; any other host fails closed. A combined production-and-staging list is rejected. If the variable is set but empty or invalid, the parser fails closed: browser origins are not accepted. An absent Origin remains available for server-to-server requests and receives no `Access-Control-Allow-Origin` header; the API action still authenticates and authorizes the caller.

## Per-project configuration

| Project | Value |
|---|---|
| Production `gcsamrdaeraxieaagsta` | Leave `SHOIR_ALLOWED_BROWSER_ORIGINS` unset (production-only default), or set exactly `https://shoir-ie-app.streamlit.app`. |
| Staging `hfhrosthswcybccepmak` | Set exactly `https://shoirieverified.streamlit.app` before deploying this shared source to staging. The current deployed staging v11 is unchanged by this source PR. |

The staging origin above is grounded in the current archived GitHub-runner browser acceptance artifact. The historical host `shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app` is deliberately not allowed because its use was not established by that acceptance evidence. Re-verify the active staging host before changing its allowlist.

Do not run a secrets command as a substitute for approved change control. When staging is next explicitly authorized for deployment of this shared source, set the staging value using the project's supported Supabase secret/configuration mechanism, then immediately rerun real staging preflight and hosted shell/browser acceptance.

## Response requirements

- Allowed Origin: echo that exact origin; include `Vary: Origin`, `Access-Control-Allow-Methods: POST, OPTIONS`, and the reviewed headers.
- Unapproved Origin: reject before action dispatch and do not emit `Access-Control-Allow-Origin`.
- Approved OPTIONS: HTTP 204 with no response body.
- Unsupported method: HTTP 405.
- Origin-free service-to-service call: no fabricated ACAO; all endpoint authentication/authorization still applies.
- No wildcard `Access-Control-Allow-Origin: *`.

Unit/source tests only establish implementation contracts. Live CORS is not passed until a networked runner probes the deployed target after an explicitly authorized deployment.
