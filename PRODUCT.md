# Content Reward product

Content Reward prepares high-quality, campaign-eligible short clips for local
review. Its core runtime is clipping/, with shared SQLite/config infrastructure
in app/, campaign rules in campaigns/, safe publication preparation in publishing/,
and measured feedback in analytics/. See README.md for the supported commands.

The optimization objective is useful eligible content, low manual effort,
reliable/resumable processing and measured outcomes per unit of time. Clip count
is a configurable production target rather than permission to weaken quality.

Production prepares 20 colorized/fit clips by default and supports larger fresh
batches and exact saved-order resume. General studio/fit defaults and historical
orders are preserved. Final files remain in clips/. Public captions/replay are
inspected first; only selected media sections are acquired. Unknown source,
selection, transcription or reward facts must never be invented.

Publishing is disabled. Local manual export and simulated mocks exist, with
campaign validation and content-bound idempotency. Real platform posts require
future explicit authorization and verified official integration. Credentials
remain local and are entered through existing hidden terminal prompts.

Performance is imported/manual evidence, not automatically verified platform
analytics. Feedback uses latest observations from enough independent clips,
with bounded changes and visible sample counts. Experiments record a source
moment, variant settings and observed outcomes without causal claims.

The baseline and exact implementation plan are docs/AUDIT.md and
docs/REFACTOR_PLAN.md. The complete requirements are PRD.md. Archived applications
are retained under legacy/ and must not be confused with the supported runtime.
