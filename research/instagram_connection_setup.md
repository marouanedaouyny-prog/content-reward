# Instagram connection setup

Implemented 2026-10-10 in the supported clipping runtime. The user provided an
Instagram token and numeric identifier, authorized saving them locally, then
asked to continue. Secret values are confined to ignored `.env.local` and
server-side requests; this document contains no token.

The new connection is a read-only Instagram Login check, independent of the
unfinished legacy connector. It uses the fixed graph.instagram.com host, bearer
authentication, verified TLS, a bounded response and timeout, and refuses
redirects. Identity must match the configured account. Unknown permission
lookup never establishes publishing access. No publishing endpoint is enabled.

Meta's first-party [Instagram API Postman collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
documents Instagram Login for professional accounts, bearer authorization and
the `instagram_business_basic` and `instagram_business_content_publish` scopes.
The separate Facebook Login section uses a different host and account/Page
setup; it is not the connection path implemented here.

Direct Meta reference pages could not be opened during research. Profile and
permission calls still require live provider validation. If the permission
probe is refused, the application records profile_verified with unknown
publishing access rather than assuming the token permits posting. No token
expiry or automatic refresh has been established.

The actual saved setup returned network_unavailable under the configured proxy
on 2026-10-10. This does not establish that the token is invalid or valid. After
outbound access is restored, verify identity and scopes, then design publishing
around reviewed campaign rights, reviewed clips and accessible video hosting.

Tests use synthetic tokens and provider responses to exercise secret redaction,
identity mismatch, cached-status invalidation, permission handling, expired
tokens, network errors, fixed-host transport, origin rejection and UI states.
Those fixtures do not prove the real token's permissions or identity.

## Continuation on 2026-10-12

The latest local configuration contains Instagram app credentials and the local
callback URI, with no saved authorized account token. Unfinished OAuth helper
methods were present, but their routes and browser controls were missing.
Their explicit SQLite transactions also lacked commits, so login states were
rolled back before a callback could consume them.

The continuation adds connection-start and callback routes, Connect/Reconnect
controls, callback feedback, committed ten-minute browser-bound login states,
single-use state consumption, strict profile validation and atomic credential
replacement. A newly authorized token/account pair takes precedence over old
manual credentials. Callbacks never return provider secrets, and their query
strings are removed before application access logging. Failed authorization
preserves the previous saved account. Posting remains disabled.

Native Python 3.11 HTTP checks returned 200 for the workspace, script, status
and health routes. The real local app also passed a connection-start and
declined-callback check without contacting Instagram. The configured callback
matches the running workspace at `http://127.0.0.1:8000/`. This confirms local
configuration shape, not the validity of the Meta app or its registration.

The targeted Instagram and UI suite returned **34 passed**. New checks exercise
credential replacement, expired/missing/replayed browser state, denied consent,
failed token exchanges, malformed profiles and redirect URIs, origin rejection,
HTTPS cookie flags, secret redaction, callback log sanitization and UI recovery.
The Windows test runner uses a unique fixture directory that inherits workspace
ACLs because pytest's 0700 folders exclude this sandbox identity.

The final full clipping run returned **119 passed, 1 failed** in 36.04 seconds.
The existing `test_source_deadline_stops_downloader_children` fails because
Windows refuses `taskkill /T /F` with exit code 1 and `Access denied`; its child
process survives. This was reproduced independently and is not a passing
cleanup check. Media termination code was unchanged in this continuation.
Docker Compose configuration validation completed successfully.

The subsequent continuation fixed the process-cleanup failure with owned
Windows job objects and a launcher gate. The full clipping suite then returned
**126 passed**. The installed Python 3.11 environment also proved cleanup after
abrupt supervisor exit. See the [cleanup record](windows_process_cleanup_2026-10-12.md)
for the implementation, sources and verification. The earlier 119/1 result above
is the historical pre-fix result; Instagram authorization remains unverified.

Outbound provider probing still fails with a network error. Chrome launch is
also refused (`spawn EPERM`), so browser screenshots and live account identity,
permissions and token exchange remain unverified. Meta's business-login and
token reference pages could not be retrieved (429/inaccessible), and the
Postman page rendered only its shell. The provider behavior therefore still
needs validation with a real authorized account; the local callback URL has not
been confirmed as acceptable to Meta. Automatic token refresh is not implemented.

## Expiry continuation

The account connection now saves provider-reported token expiry, clears cached
verification for known expired credentials, prevents expired provider checks,
shows expiry/reconnect feedback, and reports failed callback account checks
accurately. Missing and manual lifetimes remain unknown. Targeted checks returned
**47 passed**, and the full clipping suite returned **139 passed**. Native Python
3.11 fixture and HTTP checks passed. Provider renewal remains pending current
Meta contract validation; no real account is authorized. See the
[expiry implementation record](instagram_expiry_2026-10-12.md).

## Verification consistency continuation

A slow account check no longer returns or saves the previous account after
credentials or the configured API version change. The final comparison and save
share a SQLite transaction, and current lifetime metadata is used in the response.
The full clipping suite returned **144 passed**, with **52 passed** in the targeted
Instagram/browser-script suite. Native Python 3.11 concurrent reconnect and
restart checks also passed with a synthetic provider. See the
[verification race record](instagram_verification_race_2026-10-12.md). Live
authorization and provider renewal remain unverified.
