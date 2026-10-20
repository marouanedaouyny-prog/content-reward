# Instagram token expiry and recovery

OAuth login previously discarded the token response's lifetime. An expired
credential could continue to show a saved verified account, and the callback
reported connection success even when its final account check failed.

The connection now records issue and expiry timestamps alongside the saved
OAuth token/account pair when a positive integer `expires_in` is supplied. The
issue timestamp starts before the exchange request, so transport latency cannot
extend the recorded lifetime. Booleans, nonpositive numbers, nonfinite values,
strings and overflowing durations are rejected without replacing the previous
saved credentials. If lifetime data is omitted, expiry remains unknown. Manual
credentials and older saved records also retain unknown expiry.

The public status exposes only `token_expires_at` and a three-state
`token_expired` value: false for a known future expiry, true for a known elapsed
expiry, and null when the lifetime is unknown. Tokens stay server-side. Known
expired credentials clear cached identity/permission claims and are not sent to
the provider. Lifetime is rechecked after network verification to catch expiry
while a request is in flight. The UI shows the date and reconnect action;
callbacks report unsuccessful final account checks rather than success.

The duration interpretation follows OAuth's definition of `expires_in` as
seconds from token response generation. Unknown expiry is deliberately retained
when the provider omits it. See [RFC 6749 section 5.1](https://www.rfc-editor.org/rfc/rfc6749#section-5.1).

Meta's current renewal references remain inaccessible: the
[refresh reference](https://developers.facebook.com/docs/instagram-platform/reference/refresh_access_token)
returned 429 and its alternate documentation path could not be fetched. No
provider-specific renewal request or background renewal task was added. Live
account authorization and renewal still require provider validation; this local
expiry implementation does not establish a real account's token lifetime.

The new expiry and callback regressions were observed failing before the fix.
The targeted Instagram/backend/browser-script suite returned **47 passed** in
2.95 seconds. The installed Python 3.11 environment independently persisted a
synthetic reported lifetime, cleared cached verification at its expiry boundary,
and rejected a subsequent provider check using the expired credential.

The final full clipping suite returned **139 passed** in 44.96 seconds. The
restarted native HTTP app returned 200 for its workspace, script, account status
and health routes; the expiry element and new status fields are served. The
actual saved account remains unauthorized, with unknown expiry and posting
disabled. No real provider token, token lifetime or renewal was verified.
