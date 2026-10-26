# Discovery audit

Scope: how a clipping order finds a long source video, what can go wrong, and
what the supported runtime guarantees today. Audit baseline: the supported
`clipping/` runtime on branch `refactor/content-reward-hardening`. No private
media, credentials or saved orders were modified.

## The path that existed before this work

An order reached discovery through `clipping/trends.py`:

1. `TrendResearchAgent.consume_once()` looped over the six configured niches.
2. For each niche it called `trends.discover(niche)` once.
3. `trends.discover()` picked **one** provider from the environment:
   `CLIPPING_SELENIUM_PROVIDER=selenium` used `clipping/youtube_browser.py`,
   a set `YOUTUBE_API_KEY` used the official search API, and everything else
   used a bounded `yt-dlp` flat search with one metadata lookup per candidate.
4. `trends.candidate()` converted the records into pipeline source records and
   `TrendResearchAgent._rank()` sorted them by observed popularity proxies.

Everything the order learned about *why* a source was or was not usable came
from that one code path.

## Findings

| # | Finding | Evidence | Impact |
|---|---|---|---|
| 1 | One literal query per niche decided the whole search | `trends.discover()` used `niche['query']` only | A narrow phrasing that returns nothing ended the scan for that niche, even when other phrasings of the same niche had strong long videos |
| 2 | No provider fallback inside a scan | The provider was chosen once, before the search | A Selenium/browser failure or an API quota error failed the niche; the public search path was never tried in the same run |
| 3 | A zero-result run had no reasons | `trends.candidate()` returned `None` for unusable records without recording why | `no_eligible_sources` was reported without saying whether the cause was duration, views, age, a live stream or missing metadata |
| 4 | One rule set decided eligibility | A single 14-day freshness window and one duration band | A rich candidate pool collapsed to zero matches with no relaxation step |
| 5 | Ranking used one proxy | `views_per_hour_since_upload` | Slow-growing but strong videos and fast-growing weak ones were indistinguishable; no relevance, freshness or engagement signal was used |
| 6 | Old videos were silently discarded | `trends.candidate()` returned `None` for anything published more than 14 days ago | A popular long interview outside the window vanished from the results with no record |
| 7 | A provider error was indistinguishable from "no results" | `trends.discover()` raised `ValueError` for several different failures | An operator could not tell a rate limit from a broken install from an empty result set |
| 8 | Discovery could not be inspected before it changed an order | No command exposed the candidate pool | Every search change had to be judged from a finished order |

## What the supported runtime does now

`clipping/discovery/` is a separate, inspectable discovery engine. The old
single-query scan still exists and still owns the saved research run, but the
order now has a second, wider search that runs only when the first one finds
nothing usable.

- **Query families.** `QueryGenerator` produces several phrasings per niche
  (`podcast`, `interview`, `livestream`, `debate`, `reaction`, `discussion`,
  `story`, `full episode`) plus the niche's own preferred templates.
- **Provider chain.** `youtube_api` → `yt_dlp` → `selenium` → `public_search`.
  Every provider only searches; a failure of one never ends the run.
- **Structured failures.** Providers report `PROVIDER_FAILED`,
  `PROVIDER_TIMEOUT`, `PROVIDER_INVALID_METADATA`, `PROVIDER_UNAVAILABLE`,
  `CHROME_NOT_FOUND`, `PAGE_LOAD_TIMEOUT`, `SEARCH_LAYOUT_CHANGED`,
  `BROWSER_START_FAILED` or `DRIVER_START_FAILED`. A run where no provider
  answered returns `ALL_PROVIDERS_FAILED` with the providers and queries that
  were attempted.
- **Progressive eligibility.** `strict` → `medium` → `relaxed` tiers are
  evaluated in order and the first tier that produces enough candidates wins.
  The tier that produced the sources is reported, and every rejection is
  counted by reason (`duration`, `duration_unknown`, `views`, `views_unknown`,
  `age`, `age_unknown`, `live`, `blacklisted`, `score`).
- **Explainable ranking.** `SourceScorer` combines velocity, relevance,
  engagement, freshness, channel quality and transcript availability. Missing
  evidence is excluded and renormalized, and the coverage is reported beside
  the score.
- **Bounded cache.** Repeated searches reuse a cached result for three hours,
  keyed by query, provider, region, language and a hash of the active rules, so
  a changed rule never reuses a stale result.
- **Order integration.** `Controller.discover_supplement()` runs the wider
  search when the recorded scan has no usable source, keeps the original
  failure, and records `discovery_supplement` in the saved order.

## Commands

```bash
content-reward discover --niche Business --mode balanced --dry-run
content-reward discovery-health --history
```

`discover` prints the candidate pool, the tier that produced it, the provider
outcomes and the diagnostics. It never starts a clip and never publishes.

## Limits that are still true

- The engine does not measure recent growth. `views_per_hour` is a lifetime
  average, and the score is a ranking of observed public metadata, not a
  prediction of future views.
- Replay data, when present, still comes from the public replay sample. A
  selection made without replay evidence is editorial and is labelled as such.
- Transcript availability is `UNKNOWN` until the captions are fetched. Unknown
  is never a rejection and carries a neutral signal.
- Discovery never downloads media. Only metadata and the public captions the
  clip pipeline fetches later are in scope here.
- The provider chain inherits this process's proxy, TLS and permission limits.
  A blocked network fails the provider and is reported as such.
- One discovery run is bounded by `total_timeout_seconds` (90 by default). A
  provider that hangs is reported as a timeout instead of blocking the order.

## Verification

`tests/clipping/test_discovery.py` covers the fallback chain, the structured
errors, deduplication across providers, tier relaxation, the rejection counts,
the cache reuse and expiry, the public provider parser, the "no media
download" rule, the pipeline record shape, the CLI output and the order
integration. Every provider in that file is synthetic; the suite never contacts
YouTube.
