# Trending research design evidence

Recorded 2026-10-10 from shipped source and the completed implementation
verification handoff. This record provides source and interaction evidence;
it does not provide screenshots or real-browser visual approval.

## Scope and implemented behavior

The user requested faster downloads, recovery from temporary failures and an
automatic viral/trending research agent with its own section. This extends the
existing Operate workspace. The section reuses white panels, source-blue status
context, green actions, existing controls and flat list rows. No new global
design token, component preview or raster asset is introduced.

Source checked: `clipping/workspace.html`, `clipping/trends.js`,
`clipping/trends.py` and the worker/static-route integration in `clipping/app.py`.
Context checked: PRODUCT.md, DESIGN.md, `.impeccable/design.json`,
`research/clipping_speed_trends_plan.md` and
`research/trending-tools-assessment.md`. The documentation reference was
`C:/Users/hp/.agents/skills/impeccable/reference/document.md`.

The native Trending research anchor leads to a full-width section after Studio
and before guided campaign setup. A separate background worker persists
six-niche reports and schedules scans every six hours while the app runs.
The section exposes provider, scan/retry timing, actual source metrics, unknowns
and search failures. Lifetime-average views/hour is distinguished from growth
between saved observations; neither is a viral forecast. Remote text is rendered
with DOM creation and textContent. Source handoff preserves campaign rules,
permission notes and an existing caption/disclosure. Research previews remain
private and select their job in Preview without publication or submission.

Download options now cap source selection at 1080p, enable four fragment
connections and resume partials. Persisted temporary-failure backoff preserves
successful work; Pause, cancellation and shutdown remain effective. A speed
increase has not been benchmarked. The final live handoff reports the saved
IShowSpeed job resumed at source_ingest after its first temporary failure.
It also reports research retry_scheduled with zero sources, six network failures
and an actual next attempt. The configured proxy remains a connection limit;
no acquired IShowSpeed footage or invented trend result is claimed.

## Verification received

| Check | Final result |
| --- | --- |
| Full clipping suite | 91 passed in 49.58 seconds |
| Node UI checks through `tests/clipping/test_research_ui.py` | All five passed, including trending handoff, text rendering, preview and retry states |
| Native HTTP | `/`, `/trends.js`, `/api/v1/clipping/trends` and `/health` returned 200 |
| HTML | Unique IDs and heading references valid |
| JavaScript | Syntax checks passed |

The final suite includes actual running-subprocess interruption, queued work
retained on shutdown and startup of the independent research worker. These
application results were supplied by the implementation handoff. The
documenter checked shipped behavior and documentation integrity without rerunning
the application suite, browser or detector.

## Detector and finish disposition

`trending-detector-notes.md` records one detector pass and six inherited
advisories: existing colors #101818, #cfe7db, #fff5df and #d5b47a, plus existing
32px/22px type. There was no new finding and no second pass. This pre-existing
drift is recorded without repair or promotion into new system rules.

The fresh finish review returned **recapture** solely for the missing 1440px,
390px and 320px screenshots. `capture-status.json` records Chrome exiting before
DevToolsActivePort after Windows rejected Crashpad/Mojo IPC with error 5.
No new browser attempt was made in this documentation pass. Source, HTTP and
Node checks supplement inspection; they do not establish visual approval.

## Documentation integrity

Only `.impeccable/surfaces/clipping-workspace.md`,
`.impeccable/surfaces/trending-research.md` and this file were written by this
handoff. The six pre-implementation direction blocks remain unchanged.
DESIGN.md frontmatter and the schemaVersion 2 sidecar parse successfully;
both global files remain byte-for-byte unchanged from the handoff start:

- DESIGN.md SHA-256: `d0b48bdf24eb5c44b78e2895acfc9fe3380d349faafd9c6891cfa927ed98a8f9`.
- `.impeccable/design.json` SHA-256: `bf865b1fd8a5dd53a01ccca3bda6d65635e90d629e7d74bedd12165761e3bf85`.

The global document's surface examples still describe the prior navigation
and Studio-to-campaign order. The updated surface briefs own the new section
composition; that existing prose was preserved under the ordinary-extension
boundary. No global extraction, refresh or broader design change was needed.
