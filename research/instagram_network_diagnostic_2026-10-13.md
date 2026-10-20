# Verified paths and ambiguous network failure

The user ran the revised launcher in a normal PowerShell terminal. It reached
`updating_agent`, then stopped with `network_unavailable`, and asked whether
the executable path had been verified.

The exact selected executable is the project-local
`.workflow-tests/ngrok-runtime/ngrok.exe`. It exists and reports ngrok
**3.39.11**, establishing that the previous update from 3.3.1 succeeded. A
native invocation through the actual PowerShell launcher also confirmed the
Python path is `.venv/Scripts/python.exe` and the saved ngrok configuration
at the normal LocalAppData location validates with this version. The paths
are resolved before launching. No credential contents were printed.

The reported network reason did not establish which connection failed:
both the provider preflight and ngrok log classifier previously produced
`network_unavailable` with an Instagram-specific message. The latter was a
confirmed error in the diagnostic wording. The launcher now distinguishes
`ngrok_network_unavailable` at stage `ngrok_startup` from provider failures at
stage `instagram_preflight`. Provider failures identify only the fixed host,
safe transport category and optional HTTP status. Raw errors remain hidden.

`start-instagram-tunnel.ps1 -Diagnose` now verifies executable paths, version,
ngrok configuration and both Instagram hosts without starting a tunnel or
authorization. It saves output in a separate ignored diagnostic file,
preserving the real authentication attempt's status record. It preserves
normal proxy use and TLS verification. It does not change provider settings,
the callback configuration or credentials.

Native execution of this diagnostic command in the agent environment passed
the local checks and identified `proxy_connection_refused` for both provider
hosts. This is the agent's known restricted proxy; it does not establish the
cause of the user's normal-terminal failure. The user was asked for that
terminal's safe diagnostic JSON. If both hosts are reachable, rerunning
normal setup will identify a ngrok connection failure by stage.

The user subsequently ran the diagnostic mode in their normal terminal and
provided its safe JSON. It confirmed ngrok **3.39.11**, both executable paths,
a valid saved ngrok configuration and `proxy_configured: false`. Both
`api.instagram.com` and `graph.instagram.com` were reachable. The earlier
generic network failure's origin remains unconfirmed; the user's terminal
has no current Instagram transport failure in this diagnostic result. The
next required observation is a real setup run, which can now report the
connection stage accurately or return the live HTTPS callback for provider
registration. No tunnel or authorization was performed by the diagnostic.

Verification: the seven new diagnostic regression cases failed before the
change and passed afterward. The focused Instagram suites passed **73
tests**, and the complete clipping suite passed **210 tests** in 49.78
seconds. The PowerShell launcher parsed with zero syntax errors and its
native diagnostic mode exited successfully. Real Instagram authorization
remains unverified.

The updated executable's command format was compared with its own CLI help
and [ngrok's official CLI reference](https://ngrok.com/docs/gateway/agent/cli).
