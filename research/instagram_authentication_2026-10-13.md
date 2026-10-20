# Instagram HTTPS authentication setup

The user reported `Invalid redirect_uri` and installed ngrok. The local
authorization request previously used an HTTP loopback callback. A reachable
HTTPS callback and matching provider registration were still required. Exact
registered callback matching is specified in [OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749#section-3.1.2.3).

The setup tool now runs from `start-instagram-tunnel.ps1` in a normal terminal,
checks provider connectivity and starts a separate authentication service on
loopback port 8001. This lets token exchange use the normal terminal's network
environment while the clipping worker continues running. Generated Basic
Auth credentials protect the incoming tunnel; the service exposes account
routes without clipping job controls. Its temporary credentials are local
and removed on exit. Callback request logging is disabled and OAuth codes
are redacted by the shared account router.

The launcher waits for a real ngrok HTTPS endpoint, updates the local callback
configuration while preserving other configuration bytes, then confirms the
authorization URL and Secure browser state cookie. The user saves the exact
callback in Meta's Instagram login settings and connects through the displayed
authentication page. Successful code exchange saves the token and account ID
together in the shared database and verifies the account. Posting stays disabled.

The user's first normal-terminal run reached ngrok but returned
`ERR_NGROK_121`, meaning the agent version was below the account's minimum.
The installed executable reported 3.3.1. The launcher now handles this by
copying ngrok into the project, running its signed update there and retrying
once. It restores a previous local copy if the update fails and reuses the
updated copy on future launches. Provider errors and updater output are not
printed verbatim. Sources: [ngrok's version error](https://ngrok.com/docs/errors/err_ngrok_121),
[update command](https://ngrok.com/docs/gateway/agent/cli).

Verification on 2026-10-13:

- The complete clipping suite passed: **203 tests** in 53.13 seconds.
- The focused Instagram suites passed: **66 tests**. They cover update
  isolation and rollback, the single retry, credential redaction, callback
  matching, state cookies, account verification and saved credential reuse.
- The final PowerShell launcher parsed with zero syntax errors.
- A native Python 3.11 Uvicorn HTTP smoke check with a synthetic provider
  confirmed HTTPS forwarding, Secure cookie creation, exact authorization and
  exchange callback matching, persistence across account recreation and no
  exposed clipping job routes. It also rejected a foreign browser origin.

Commands:

    python tests/clipping/run_tests.py tests/clipping -q --tb=short
    python tests/clipping/run_tests.py tests/clipping/test_instagram_tunnel.py tests/clipping/test_instagram_oauth.py tests/clipping/test_instagram.py -q --tb=short

Native verification evidence is in
`.workflow-tests/instagram-auth-native-verification-2026-10-13.json`. Current
setup status is in `.workflow-tests/instagram-authentication-last-run.json`.
Both are local ignored artifacts. Account status should be inspected with
GET, without triggering a new provider verification from the restricted
worker environment.

The agent's proxy still refuses outbound Instagram connections. The user
must rerun the revised launcher in their normal terminal to establish the
live update, tunnel, provider registration and consent. Passing local tests
does not establish live account authorization. Source downloads separately
require network access from the clipping worker. Browser visual verification
was unavailable because the existing Chrome session could not be connected.
