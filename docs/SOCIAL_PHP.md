# PHP social SDK companion

Python remains the clipping runtime. An optional local PHP subprocess hosts the
TikTok SDK; JSON travels through stdin/stdout without an HTTP server. This is an
OAuth/identity integration, not a publishing adapter. No clips are uploaded.

## Installed and reproducible

On 2026-10-25, installed locally on Windows x64:

- PHP 8.4.27 NTS in `.tools/php/`, with curl, OpenSSL, mbstring, fileinfo and zip.
- Composer 2.10.3 in `.tools/composer.phar`.
- `jstolpe/tiktok-api-php-sdk` 1.0.5 under `integrations/social-php/vendor/`.

The PHP archive, certificate bundle and Composer download are checked against
published SHA256 checksums before first use. The installer accepts checksum
responses returned as bytes by Windows PowerShell. Downloads are kept inside the
project; there are no global PATH changes. Composer plugins/scripts are disabled.
Commit `composer.json` and `composer.lock`; binaries and `vendor/` are ignored.
The SDK is deliberately pinned pending review of future releases. Composer's
strict validator warns about this exact version constraint; the manifest is valid.

From the project root:

```powershell
powershell -NoProfile -File scripts/setup-social-php.ps1
.venv/Scripts/content-reward.exe social status
# Equivalent offline status:
.venv/Scripts/python.exe -m clipping.social_bridge
```

`social status` loads the real PHP SDK, reports versions, and reports
`publishing_enabled: false` and `account_verified: false`. It makes no network
requests and reads no account credentials. Missing PHP/SDK returns an unavailable
status without affecting clipping. The Windows setup requires the Microsoft
Visual C++ x64 runtime; it was already available on this machine.

This companion is installed from a source checkout, not bundled in Python wheels.
For a separately installed Python package, set `CONTENT_REWARD_PHP` to the full
PHP executable path and `CONTENT_REWARD_PHP_BRIDGE` to the installed `bridge.php`
path. On other operating systems, provide a compatible PHP CLI and install the
locked Composer dependencies manually; the PowerShell installer is Windows-only.

## Python interface

```python
from clipping.social_bridge import SocialBridge

bridge = SocialBridge()
status = bridge.health()  # offline

# Build a login URL offline, using the exact callback registered for your app.
login = bridge.start_login(client_key, registered_redirect_uri)
# The application must open login.url and receive the callback locally.
tokens = bridge.complete_login(login, callback_url, client_secret)
identity = bridge.profile(tokens['access_token'])
# Later, explicitly renew and securely replace the old tokens:
renewed = bridge.refresh(client_key, client_secret, tokens['refresh_token'])
```

The variables in this example must come from local input/secure storage. Do not
paste secrets, callback URLs containing codes, or tokens into chat or logs. The
bridge returns sensitive token dictionaries to Python in memory and does not save
them. The calling application owns secure persistence, expiry scheduling and
replacement of refreshed tokens. No browser, callback listener, credential UI,
or persisted account connection is automatically created by this library.

`start_login` generates random state. `complete_login` requires the exact callback
target, validates state, enforces a ten-minute lifetime and consumes the attempt
once. A failed network exchange requires a new login attempt. Desktop loopback
callbacks require a port and use TikTok's documented SHA256 hex PKCE challenge;
web callbacks require HTTPS. Only `user.info.basic` is requested. The SDK creates
the authorization URL, token grant parameters and profile request. Our subclasses
replace its transport to prevent SDK debug objects from exposing configuration.

The PHP boundary allows only health, authorization URL, token exchange, refresh
and read-only basic profile requests. It rejects upload, publish, inbox drafts and
arbitrary requests. Transport uses fixed TikTok HTTPS endpoints, verified TLS,
no redirects, 10-second connection / 25-second total deadlines, a 1 MiB response
limit and bearer headers for profile tokens. OAuth uses form encoding. Python
passes credentials over stdin, never command arguments, with a 35-second process
deadline. Errors contain fixed codes, never remote response bodies or stderr.

Account access remains **unverified**. Before real TikTok login, rotate the secret
previously shared in chat, confirm the app's Sandbox/live status, enable Login Kit
and basic user permission, and register the appropriate exact callback. No existing
TikTok credentials were loaded or used during installation or tests. App keys alone
are not user access tokens. Public publishing needs a separate authorized feature,
TikTok permissions/review and user approval; installing an SDK does not provide it.

## Other SDKs researched

| Platform | Candidate | Recommendation for this project |
| --- | --- | --- |
| YouTube | [`google/apiclient`](https://github.com/googleapis/google-api-php-client), with `google/apiclient-services` / `Google\Service\YouTube` | Official Google-supported PHP client, in maintenance mode. Suitable for a future YouTube adapter. Pin service versions when adding it. |
| Instagram | [`facebook/php-business-sdk`](https://github.com/facebook/facebook-php-business-sdk) | Official Meta Marketing API SDK. Its [`IGUser`](https://github.com/facebook/facebook-php-business-sdk/blob/main/src/FacebookAds/Object/IGUser.php) includes media and publishing endpoints. Evaluate the selected Instagram auth flow before adopting it. |
| Instagram | [`jstolpe/instagram-graph-api-php-sdk`](https://github.com/jstolpe/instagram-graph-api-php-sdk) | Community SDK from the TikTok SDK author. Its [request class](https://github.com/jstolpe/instagram-graph-api-php-sdk/blob/master/src/Instagram/Request/Request.php) targets `graph.facebook.com` and Facebook authorization. It is not a direct replacement for this project's `graph.instagram.com` connector. |
| Facebook/Instagram legacy | [`facebook/graph-sdk`](https://github.com/facebookarchive/php-graph-sdk) | Repository archived in January 2022; do not add it for a new integration. |

These YouTube/Instagram packages were researched, not installed or connected.
Keep the existing Instagram hidden token prompt and connector. The SDK assessment
above is based on primary repository documentation/source; Meta's Instagram Login
documentation returned HTTP 429 during this review, so compatibility with that
flow was not assumed. Separate platform credentials and identity verification
remain necessary.

Sources: [TikTok PHP SDK](https://github.com/jstolpe/tiktok-api-php-sdk),
[TikTok desktop login](https://developers.tiktok.com/docs/en/login-kit-desktop),
[TikTok token lifecycle](https://developers.tiktok.com/docs/en/oauth-user-access-token-management),
[TikTok basic profile](https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info),
[PHP Windows installation](https://www.php.net/manual/en/install.windows.manual.php),
[Composer downloads](https://getcomposer.org/download/).

## Verification

```powershell
.venv/Scripts/python.exe tests/clipping/run_tests.py tests/unit/test_social_bridge.py -q
.tools/php/php.exe tests/php/social_bridge_test.php
.venv/Scripts/python.exe -m ruff check .
.tools/php/php.exe .tools/composer.phar audit --working-dir=integrations/social-php
.venv/Scripts/python.exe tests/clipping/run_tests.py tests -q
.venv/Scripts/content-reward.exe smoke
```

Bridge integration tests launch the real PHP executable and SDK. PHP tests replace
only HTTP delivery with synthetic responses, inspecting actual SDK requests.
They do not contact social accounts. The PHP integration tests skip if the optional
runtime/dependencies are absent; install them to run the complete bridge checks.

Verified on this checkout, 2026-10-25: full suite **954 passed, 2 skipped**;
all 21 bridge tests passed; Ruff and project smoke passed; both PHP source files
passed syntax checks; Composer platform requirements passed and its audit reported
no known security advisories. The setup script also completed a second run using
the existing runtime and lock file. These results establish offline integration,
not successful live OAuth or account access.
