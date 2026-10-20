# TikTok connection setup

Updated: 2026-10-08.

The user selected TikTok as the first social account to prepare. TikTok application credentials have been saved in the local `.env` under `TIKTOK_CLIENT_KEY` and `TIKTOK_CLIENT_SECRET`. This file is excluded by the repository's `.gitignore` and this connector's `.dockerignore`. Credential values are intentionally absent from this document.

Saving application credentials does not authorize a TikTok user account. No authorization request, token exchange, upload, or publication has been performed. Credential validity and enabled permissions have not been verified with TikTok.

## Information needed next

1. The target TikTok public username/profile link.
2. The developer app's status: Sandbox, under review, or approved/Live. For Sandbox, confirm the target account has been added as a test user if required by that environment.
3. Enabled products and approved scopes: Login Kit, Display API, and/or Content Posting API. Account login uses `user.info.basic`; listing videos needs `video.list`; uploading for the owner to review/post needs `video.upload`; Direct Post needs `video.publish` and the applicable approval.
4. The exact registered Login Kit redirect URI. For the web flow, TikTok requires a static absolute HTTPS URI registered in its developer portal. No callback address has been guessed or written to the local configuration.

Share these non-secret settings to continue. Account consent will happen through TikTok's official authorization page, rather than by giving the application a TikTok password.

## Implementation still required

The existing connector cannot yet safely complete account authorization. Before attempting a real connection:

- Pass TikTok credentials into provider initialization; current initialization only supplies LinkedIn configuration.
- Persist expiring, single-use OAuth state bound to the requesting user and redirect URI, validate it on callback, and use the retained redirect URI during token exchange.
- Use the authorization parameters required by the selected web/desktop flow, including correct scope formatting and PKCE handling where applicable.
- Enable TLS certificate verification for provider requests.
- Repair the encryption helper's import order and configure appropriate application/token encryption secrets before retaining user access or refresh tokens.
- Align the deployment callback with the registered HTTPS URL and give the connector an endpoint distinct from the clipping API. The current compose file hardcodes an HTTP localhost callback and conflicts on host port 8000.
- Validate rejected, expired, reused, and mismatched OAuth callbacks before testing successful account consent.

The working `clipping/` app still uses operator publication and submission confirmations; it has no live TikTok connection adapter yet.

## Publishing choice

Use manual publishing while account setup is pending. If the application has the approved `video.upload` permission and the owner authorizes it, TikTok's inbox upload flow lets the owner finish editing and posting in TikTok. An uploaded draft must remain distinct from a published post in workflow status.

Direct Post has separate restrictions: unaudited clients are limited to private posting, and TikTok's guidelines exclude an internal utility built only to upload to accounts owned or managed by its developer/team. A client key and secret alone do not establish permission for automatic public posting.

## Official references

- [TikTok Login Kit for web: redirect URI, state, scopes, and user consent](https://developers.tiktok.com/docs/en/login-kit-web/)
- [TikTok Content Posting API: upload for owner review and posting](https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content/)
- [TikTok Direct Post guidelines and audit restrictions](https://developers.tiktok.com/docs/en/content-sharing-guidelines)

If replacing these credentials, update the local `.env` directly. Keep future client secrets, access tokens, and refresh tokens out of chat, source files, screenshots, and documentation.
