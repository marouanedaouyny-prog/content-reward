# Instagram verification during credential replacement

A provider check could finish after reconnecting another account and return the
previous account as verified. It could also overwrite a newer saved check. The
same problem affected manual token removal/replacement and API-version changes;
the code recomputed its fingerprint after the request instead of remembering
which configuration it had checked. Expiry metadata updated during a check could
also be stale in its response.

Verification now reads its starting credentials and lifetime from one SQLite
snapshot and captures the configuration fingerprint before network requests.
After the provider returns, a short write transaction compares the current
credentials and API version before saving. A changed configuration returns its
current status without saving the previous result. The comparison and write
share the transaction, including when another connection instance completes
OAuth. Network requests run outside database transactions. Unchanged credentials
use the current expiry metadata, including the existing expiry boundary check.
Status reads use one snapshot for credentials, expiry and cached verification.

Five new regressions failed before the fix: token replacement, token removal,
API-version changes, a slow previous account check finishing after another
account was authorized and verified, and changed expiry for the same token.
After the fix, the targeted Instagram/browser-script suite returned **52 passed**
in 3.22 seconds. The full clipping suite returned **144 passed** in 43.31 seconds:

```powershell
python tests/clipping/run_tests.py tests/clipping -q --tb=short
```

The installed Python **3.11.15** runtime independently reproduced concurrent
reconnection with a synthetic provider and confirmed that the new verification
survives reconstruction of the connection object. Both tokens were absent from
public output and posting remained disabled. Its repeatable smoke script is
`.workflow-tests/instagram-race-native-smoke.py`; the evidence record is
`.workflow-tests/instagram-race-verification-2026-10-12.json`.

These checks exercise local credential consistency. They do not validate real
Meta authorization, permissions or token renewal. The local configuration still
contains app credentials without an authorized account token. Provider access
remains unavailable and automatic renewal remains unimplemented.
