# Discovery fix plan and record

This records what was changed after the findings in
[DISCOVERY_AUDIT.md](DISCOVERY_AUDIT.md), and how each change was verified.
The goal is a search that can fail without lying about why, and that an
operator can inspect before it changes an order.

## Changes

| Finding | Fix | Where |
|---|---|---|
| 1. One query per niche | Query families plus niche templates, generated deterministically and expanded progressively | `clipping/discovery/queries.py` |
| 2. No provider fallback | Ordered provider chain; a provider failure is recorded and the next provider still runs | `clipping/discovery/providers.py`, `clipping/discovery/engine.py` |
| 3. No reasons for a zero-result run | Every rejection is counted by reason and reported with the run | `clipping/discovery/eligibility.py`, `clipping/discovery/models.py` |
| 4. One eligibility rule set | `strict` → `medium` → `relaxed` tiers; the first tier that yields enough candidates wins and is named in the result | `clipping/discovery/eligibility.py` |
| 5. One ranking proxy | Six documented signals with renormalized weights, missing evidence excluded and coverage reported | `clipping/discovery/scoring.py` |
| 6. Silent discarding of old videos | Old videos are rejected by a counted reason instead of disappearing | `clipping/discovery/eligibility.py` |
| 7. Indistinguishable provider errors | Stable provider error codes and run-level codes | `clipping/discovery/providers.py`, `clipping/discovery/engine.py` |
| 8. Discovery could not be inspected | `content-reward discover` and `content-reward discovery-health` commands | `clipping/cli.py` |

## Supporting work

- **Normalized records.** `SourceCandidate` is the single shape every provider
  result becomes, so the eligibility engine, the scorer and the clip pipeline
  never need to know which provider found a video. `clipping/discovery/models.py`
- **Bounded cache.** `DiscoveryCache` reuses a search result for three hours,
  keyed by query, provider, region, language and a hash of the active rules.
  A changed rule never reuses a stale result. `clipping/discovery/cache.py`
- **Health and history.** `ProviderHealth` reorders the chain across runs;
  `SourceHistory` records considered sources, the blacklist, the whitelist
  boost and per-query performance. `clipping/discovery/health.py`,
  `clipping/discovery/history.py`
- **Pipeline bridge.** `clipping/discovery/pipeline.py` converts candidates
  into the source records the clip pipeline already consumes, and broadens the
  search over several niches.
- **Order integration.** `Controller.discover_supplement()` runs the wider
  search only when the recorded scan has no usable source, keeps the original
  failure visible, and saves `discovery_supplement` in the order.
  `clipping/orchestrator.py`; disable it per order with
  `--no-discovery-fallback`.
- **Configuration.** A validated `discovery` section in `app/core/config.py`
  and `config/default.yaml`, so an invalid rule set fails at load time rather
  than during a run.
- **CLI.** `content-reward discover` and `content-reward discovery-health`,
  with `--dry-run` and `--debug` for the discover command. `clipping/cli.py`

## Rules kept

- Discovery never downloads media. Only metadata and the public captions the
  clip pipeline fetches later are in scope.
- A provider failure never ends a run. A zero-result run always states its
  reasons.
- Publishing stays disabled. Discovery reads public metadata only and never
  contacts a social account.
- The saved research run and the saved order remain authoritative. The wider
  search only adds candidates; it never overwrites a saved order.

## Verification

- `tests/clipping/test_discovery.py` — 18 focused tests covering the fallback
  chain, structured errors, deduplication across providers, tier relaxation,
  rejection counts, unknown transcript status, cache reuse and expiry, the
  public provider parser, the no-media-download rule, the pipeline record
  shape, the CLI output and the order integration. All providers in that file
  are synthetic; the suite never contacts YouTube.
- `python tests/clipping/run_tests.py tests -q` — the supported suite.
- `ruff check` on the changed files.

## Known limits

- The score is a ranking of observed public metadata, not a prediction of
  future views. `views_per_hour` is a lifetime average.
- Replay data is still optional; a selection made without it is editorial.
- Transcript availability stays `UNKNOWN` until the captions are fetched, and
  unknown is never a rejection.
- The provider chain inherits this process's proxy, TLS and permission limits.
