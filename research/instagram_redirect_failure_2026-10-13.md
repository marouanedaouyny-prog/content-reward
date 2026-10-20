# Instagram rejects the configured callback URL

The user reported the provider error:

    Invalid request: Request parameters are invalid: Invalid redirect_uri

The running workspace's connection endpoint was inspected with credentials,
authorization state and full authorization URLs omitted from output. It
returned HTTP 200 and sent this exact callback:

    http://127.0.0.1:8000/api/v1/clipping/accounts/instagram/callback

The authorization endpoint is `https://www.instagram.com/oauth/authorize`.
The request includes a client ID, random state, state cookie and the current
Instagram business basic/content publishing scopes. The rejection occurs at
the provider before a successful callback, so no account token was obtained.

The local `oauth_ready()` check validates credential and callback syntax. It
does not establish that Meta has registered or accepts that callback. A fully
registered OAuth callback must match the request value exactly; this includes
the scheme, host, port, path and any trailing slash.
Source: [OAuth 2.0 redirect matching](https://www.rfc-editor.org/rfc/rfc6749#section-3.1.2.3).

Meta's Instagram business-login documentation returned a login-required page
or an access error during this investigation. Its current acceptance of an
HTTP loopback callback could not be established. An existing Chrome session
could not be connected through the installed agent-browser CLI. No Meta
dashboard settings were read or changed.

The exact URL saved under the app's Instagram **Valid OAuth Redirect URIs**
has been requested from the user. The remaining diagnosis is whether the
requested URL is absent, different, or disallowed under that provider setup.
An HTTPS callback requires a working HTTPS route; changing a URL string alone
would not establish the callback or its browser state cookie.

Eight focused OAuth request, callback and redirect tests passed:

    python tests/clipping/run_tests.py tests/clipping/test_instagram_oauth.py -k 'connect_binds or callback_saves or redirect' -q --tb=short

These tests check local behavior and mocked exchanges. They do not prove
provider registration, a successful real Instagram login or account access.

Saved live request evidence:
`.workflow-tests/instagram-redirect-diagnostic-2026-10-13.json`.

No callback configuration was guessed, no account token was displayed,
and no live-authorization success is claimed.
