# Ngrok for the Instagram development callback

The user's installed executable was found in the WinGet Ngrok.Ngrok package
directory. It reports version 3.3.1. Its saved account configuration passes
`ngrok config check`; an authentication-token value is present without being
printed. The current agent session's PATH has not picked up this installation.

The agent's inherited proxy refuses outbound connections. A provider
preflight now reports this as `proxy_connection_refused` before attempting a
tunnel or changing callback configuration. The user ran the launcher in a
normal terminal and reached ngrok, which returned `ERR_NGROK_121`. That error
identifies an agent version below the account's permitted minimum; it does
not establish invalid Instagram credentials.
Source: [ngrok ERR_NGROK_121](https://ngrok.com/docs/errors/err_ngrok_121).

The launcher now responds to that version error by copying the executable
into the project's ignored `.workflow-tests/ngrok-runtime` directory, running
`ngrok update` there and retrying authentication once. Ngrok verifies the
update's cryptographic signature. The installed WinGet executable is left
untouched, and a failed update restores the previous local executable.
Repeated version rejection stops after the retry rather than looping.
Source: [ngrok update command](https://ngrok.com/docs/gateway/agent/cli).

The final launcher starts a separate authentication service on loopback port
8001 using the terminal's environment. The existing clipping worker can keep
running on port 8000. A temporary version-2 named tunnel merges with the saved
ngrok configuration, preserves the public Host header, disables local request
inspection and requires generated Basic Auth credentials. The credentials
stay in a temporary local file, whose path is displayed; its contents are
not printed. The authentication service exposes account routes, not clipping
job routes. Owned processes and temporary credentials are cleaned up on exit.
Source: [ngrok version-2 configuration](https://ngrok.com/docs/gateway/agent/config/v2).

Only after a real HTTPS endpoint is returned does the launcher save its
exact callback in `.env.local`. It checks that the authorization URL and
Secure browser state cookie use that HTTPS callback before displaying
`callback_ready` and opening the authentication page. The user must save
the same callback in Meta's Instagram login settings, then authorize the
account through that page. The shared clipping database stores the verified
access pair, so the worker can read it without restarting. Posting stays
disabled.

Focused tests cover executable-copy isolation, update rollback, redacted
errors and the single retry, alongside HTTPS callback and account tests.
Native HTTP verification used a synthetic provider and confirmed Secure
cookie forwarding, exact authorization/exchange callback matching and
credential persistence. These checks do not establish Meta redirect
registration or successful real Instagram consent. A later normal-terminal
run reached the automatic update step and then returned `network_unavailable`.
Reading the resulting project executable established that the update
succeeded: it reports **3.39.11**. The final launcher resolves that cache path
and uses it. Native checks also confirmed the saved ngrok configuration is
valid for this version.

The previous generic network message was ambiguous because the ngrok log
classifier could produce the same reason as the Instagram preflight. This
reporting error is corrected: ngrok cloud transport failures have a distinct
reason and stage, and Instagram preflight failures identify the host and
safe DNS/TLS/timeout/refusal category. A read-only `-Diagnose` launcher mode
checks both provider hosts, executable paths and configuration validity. It
does not start authorization, change the callback or print any token. The
normal terminal's diagnostic output is still needed to identify the actual
cause of the user's new failure.

Ngrok provides the incoming callback route. The setup process still needs
outbound token-exchange access, and the clipping worker separately needs
outbound access to download source footage.
