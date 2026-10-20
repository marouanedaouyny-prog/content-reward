# Direct Instagram token connection without a tunnel

The user requested another authentication method after ngrok setup failures.
The project already accepted Instagram user tokens through local
configuration. A secure local connector now provides a simpler route for
the user's own account, using a token generated in Meta's app dashboard.
Meta's official [Instagram API collection](https://www.postman.com/meta/workspace/instagram/documentation/23987686-9386f468-7714-490f-9bfc-9442db5c8f00)
documents dashboard token generation and the Instagram Login API for
Business and Creator accounts. No token lifetime or specific dashboard
breadcrumb was assumed.

Run the new launcher in a normal PowerShell terminal:

    ./connect-instagram-token.ps1

The native Python CLI hides token entry, refuses redirected input and does
not accept a token in command-line arguments. Unknown arguments are
reported without repeating their values. The token is used only for bounded
read-only provider calls. The connector confirms the profile before saving
credentials, derives the account ID and saves the access pair together in
the existing local database. The shared account verifier checks identity
and permissions and saves its redacted status for the running workspace.
No tunnel, registered local callback or app-secret exchange is used.

Initial invalid-token, network and malformed-profile failures preserve the
previous saved access pair. A second verification failure after a successful
profile check can leave the new pair saved with an unverified error status;
the CLI does not claim successful authorization in that case. Reimporting
the same saved pair retains its expiry metadata. A different imported token
has unknown expiry unless the project already has its lifetime information.
No token refresh or posting functionality was added.

Six new regression cases failed before implementation and then passed. The
focused direct-token, account and OAuth suites passed 52 tests. The complete
clipping suite passed **216 tests** in 45.03 seconds. Native Python
3.11 verification with a synthetic provider confirmed the CLI success path,
derived identity, credential persistence after account recreation, hidden
credential output, rejection of redirected input and redaction of mistaken
token arguments. Its temporary database was isolated from the real account
database, and its emit function was captured so it did not overwrite the
real authentication status. The PowerShell launcher parsed successfully.
Native evidence is saved locally in
`.workflow-tests/instagram-token-native-verification-2026-10-13.json`.

The user's normal terminal previously confirmed both Instagram hosts were
reachable, with no configured proxy. The agent's own environment still has
a refused proxy. The user must generate the real token and enter it locally;
synthetic verification does not establish live account access. Real success
prints `authorized` with `method: direct_token` in the canonical local
authentication status record. Posting remains disabled.
