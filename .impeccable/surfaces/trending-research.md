# Trending research section

Mode: Operate. Target: clipping/workspace.html, clipping/trends.js.
An extension of the existing clipping workspace, requested 2026-10-10.

## Direction contract

THESIS: Show an agent's actual search evidence and next action together, so the
creator can move from a recent source to a clip without choosing a niche.

OWN-WORLD: Inherit white work surfaces, forest-green actions, blue source
context, native controls, readable type and flat list rows from DESIGN.md.

STORY: The creator sees which six niches were searched, when results were
observed, why a source ranks highly, and whether the agent is waiting or paused.
One action prepares the best eligible private preview; source handoff preserves
the existing campaign brief, permissions and disclosure.

FIRST VIEWPORT: Preserve Preview and its primary automatic action. A native
Trending research anchor leads to a full-width section after Clip Studio:
heading and actions, schedule/status, then ranked source rows and failures.

FORM: Local section extension, not a new visual world or concept tournament.
Signature interaction: carry measured research into the Source step or queue a
private preview. Missing metrics and failed searches remain explicit.

FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance.

## Implemented surface

The direction contract above was recorded before implementation and remains
unchanged. The native Trending research anchor opens `#trending-research`, a
full-width white section after Clip Studio and before guided campaign setup.
Its heading is "Find your next source". Search recent videos and Pause/Resume
research agent sit beside the explanation, stacking below it at 800px. The
source-blue inset reports provider, status and the actual next scan or retry.
The best eligible preview action, flat source rows, per-niche errors and native
selection-method disclosure follow. Existing padding, controls, focus, type and
reduced-motion behavior apply. DESIGN.md and the sidecar need no new primitives
or component previews and remain unchanged.

The independent background worker saves research reports and niche checkpoints
in SQLite. It searches Gaming, AI & technology, Business, Fitness, Sport, and
Culture & comedy, using the official YouTube API when configured or bounded
public searches otherwise. Completed scans schedule the next scan six hours
later while the app runs. Temporary connection failures retain results and
schedule persisted backoff; workspace Pause, agent Pause and shutdown are
respected. The interface refreshes every five seconds and preserves unchanged
source rows.

Each row shows the real creator, niche coverage, observed views, publication
date and observation time. Missing metrics display Unknown or Not recorded.
Views/hour since upload is explicitly a lifetime average. Growth between
observations is computed only with a comparable saved report at least fifteen
minutes earlier. Search coverage is incomplete and these signals do not predict
virality. Private-preview eligibility requires a recent recorded source with
known views, date and a duration of 1–120 minutes; stale scans require refresh.

Use source in campaign reveals and focuses Source, replaces competing file
inputs and preserves rules, permission notes and an existing caption/disclosure.
An empty caption can receive the source title. Preview actions queue an eligible
private job and select it in Preview without publishing or submitting. Remote
text is placed with `createElement` and `textContent`; validated YouTube IDs
produce canonical source links. No raster asset was added, so raster provenance
is not applicable.

## Finish disposition

Source and interaction checks support the implementation; the fresh finish
review returned **recapture** because 1440px, 390px and 320px browser captures
remain absent after Windows Chrome IPC error 5. No visual approval is claimed.
The evidence, live connection limit and preserved-system integrity are recorded
in `.impeccable/review/trending-design-evidence.md`.
