# Discovery providers

The discovery engine searches through a fixed chain. Each provider only
**searches**: it returns broad public metadata and never decides whether a
video is usable. Filtering, ranking and tier relaxation belong to the
eligibility engine.

## The chain

| Order | Provider | Requires | Notes |
|---|---|---|---|
| 1 | `youtube_api` | `YOUTUBE_API_KEY` | Official search API. Ordered by view count, region and language aware. Skipped when no key is set. |
| 2 | `yt_dlp` | `yt-dlp` on PATH | Bounded `ytsearchN:` flat search plus one metadata lookup per candidate. Never downloads media. |
| 3 | `selenium` | A Selenium-capable Python in `CLIPPING_SELENIUM_PYTHON` and a working Chrome | Fallback only. Runs `clipping/youtube_browser.py`. Chrome is never required for discovery. |
| 4 | `public_search` | Nothing beyond outbound HTTPS | Last resort. Reads the public results page. No key, no browser, no download. |

A provider that fails is reported and the chain continues. The order of the
chain is not changed by failures within one run; `ProviderHealth` reorders
providers across runs so a provider that failed recently is tried later.

## Failure codes

| Code | Meaning | Typical repair |
|---|---|---|
| `PROVIDER_FAILED` | The provider ran and did not return usable results | Check the install and the network path |
| `PROVIDER_TIMEOUT` | The provider did not answer within the timeout | Raise `provider_timeout_seconds` or repair the connection |
| `PROVIDER_INVALID_METADATA` | The provider answered with unreadable metadata | Report it; the page layout may have changed |
| `PROVIDER_UNAVAILABLE` | The provider could not be reached | Repair proxy, TLS or DNS |
| `INVALID_QUERY` | The query was empty or not a string | Internal error; report it |
| `CHROME_NOT_FOUND` | No Selenium-capable Python is configured | Set `CLIPPING_SELENIUM_PYTHON` or use the public path |
| `PAGE_LOAD_TIMEOUT` | The browser search timed out | Repair the browser session |
| `SEARCH_LAYOUT_CHANGED` | The browser or page returned an unreadable shape | Report it; the public layout changed |
| `BROWSER_START_FAILED` | The browser could not reach YouTube | Repair Chrome access |
| `DRIVER_START_FAILED` | The browser could not start | Repair the Chrome/driver install |

Run-level codes: `ALL_PROVIDERS_FAILED` (no provider answered) and
`NO_SUITABLE_SOURCES` (providers answered, but no candidate passed any tier).

## Configuration

`config/default.yaml`, section `discovery`:

```yaml
discovery:
  mode: balanced              # fast | balanced | deep
  providers:
    youtube_api: true
    yt_dlp: true
    selenium: true
    public_search: true
  queries_per_niche: 8
  results_per_query: 20
  target_sources: 5
  minimum_sources: 2
  max_parallel_queries: 3
  provider_timeout_seconds: 20
  total_timeout_seconds: 90
  cache_ttl_hours: 3
  language: en
  region: US
  whitelist_boost: 0.10
  freshness_window_days: 14
  secondary_lookup_limit: 5
  families: [podcast, interview, livestream, debate, reaction, discussion, story, full episode]
  eligibility:
    strict:  {min_duration_minutes: 45, min_views: 100000, max_age_days: 7,  min_score: 0.70, require_views: true,  require_age: true}
    medium:  {min_duration_minutes: 30, min_views: 25000,  max_age_days: 30, min_score: 0.55, require_views: true,  require_age: false}
    relaxed: {min_duration_minutes: 20, min_views: 5000,   max_age_days: 90, min_score: 0.45, require_views: false, require_age: false}
```

Setting a provider to `false` removes it from the chain. `fast` uses only
`yt_dlp` with three queries; `deep` allows eight metadata lookups per run.

## Health and history

```bash
content-reward discovery-health
content-reward discovery-health --history
```

The report contains the observed provider health, the cache statistics and,
with `--history`, the sources this project considered before, the blacklist and
the per-query performance. Provider health is observed in the running process:
a provider that never ran is *unknown*, not *failed*.

## Rules

- Discovery never downloads media. Providers use flat search or page reads.
- Discovery never contacts a social account and never publishes.
- A provider failure never ends a run, and a zero-result run always states its
  reasons.
- Credentials are never echoed into a report. An API key is read from the
  environment and is not part of any saved record.
