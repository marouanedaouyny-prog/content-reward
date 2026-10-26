# Growth and performance optimization plan

This plan maps the October 20 growth PRD onto the current local-first runtime.
The work is incremental: keep public captions and bounded downloads first,
preserve current Windows launchers, use evidence-backed scores, and keep social
publishing disabled. “Schedule” means a local prepared queue for review; it does
not authorize network posting.

| Order | Files / area | Problem to solve | Proposed change | Risk | Expected benefit | Acceptance evidence |
|---|---|---|---|---|---|---|
| 1 | `docs/DEPENDENCY_AUDIT.md`, `docs/PERFORMANCE_AUDIT.md`, this plan | Dependency and runtime costs were not consolidated | Maintain explicit dependency decisions and instrumentable bottlenecks before optimization | Static audit can mistake a possible bottleneck for a measured one | Avoid unnecessary installs and ungrounded speed claims | Review against `pyproject.toml`, current call paths and measured logs |
| 2 | `growth/source.py`, `app/core/config.py`, `config/default.yaml`, `clipping/batch.py` | Candidate sources were deeply inspected in provider order | Apply weighted metadata-only source ranking before fetching captions; reject only with configured evidence coverage | Lifetime velocity and keyword overlap are weak proxies and must stay labeled | Avoid caption work on well-supported weak candidates | Tests cover weighted inputs, sparse evidence, below-threshold rejection and batch order; score basis remains explicit |
| 3 | `growth/hook.py`, `growth/retention.py`, `growth/quality.py`, `growth/scorer.py`, `clipping/planning.py` | Heuristics need consistent evidence/missing-signal handling and explainable final ranking | Keep configured weighted scoring; add only source-supported signals and strict completeness/quality gates | Editorial estimates may be mistaken for audience prediction | Better prioritization without fabricated metrics | Synthetic ranking regressions; transcript evidence and missing fields shown in result; no unmeasured prediction called “viral” |
| 4 | `clipping/captions.py`, `clipping/caption_styles.py`, `clipping/framing.py`, `clipping/silence.py`, `clipping/clip_review.py` | Caption cleanup, safe-zone, framing and silence behavior need export-level checks | Preserve studio/fit defaults; keep optional cuts conservative; strengthen generated-video QC and human review evidence | Automatic crop/cut can damage meaning or visual quality | More readable, complete prepared clips | Synthetic media decode/QC plus review of actual exports before delivery |
| 5 | `clipping/hashtags.py`, `clipping/description.py`, campaign/package metadata | Hashtag/caption features need persistent performance memory and less repetition | Validate relevant tags, persist tag usage/performance where observations exist, keep CTA optional and content-grounded | Sparse history can overfit; generated copy can overstate claims | More relevant review packages | Unit tests for topic relevance, count limits, deduplication, unknown history and no unsupported claims |
| 6 | New `growth/timing.py`, scheduling repository, `app/api/routes.py`, CLI | No account-history recommendation and content-spacing queue contract | Recommend slots from timezone-aware observations with explicit cold-start fallback; add persisted READY/SCHEDULED queue and same-source/topic spacing; provide local review/status actions only | Timezone/DST bugs or accidental implication of a real post | Reviewable cadence and account-specific timing once real observations exist | Tests across timezone/DST, minimum gaps, per-day caps, restart persistence; publishing stays disabled |
| 7 | `analytics/models.py`, `analytics/collectors.py`, `analytics/reports.py`, UI/API reporting | Performance observations need profile visits/follower conversion and honest report coverage | Add validated profile-visit/follower metrics, followers per 1,000 views, daily/weekly/monthly aggregates and sample counts | Imported values can be mistaken as verified API collection | Optimize toward conversion rather than views alone | Tests for zero/missing views, aggregation, latest-per-clip/platform behavior and provenance |
| 8 | `growth/experiments.py`, `analytics/feedback.py`, `app/repositories/store.py` | Existing feedback is narrow and experiments need controlled assignment/results | Add reproducible variant assignment changing one or two dimensions, independent-clip minimums, bounded smoothing and persisted outcome linkage | Confounding and small samples | A cautious, auditable feedback loop | Deterministic assignment tests; no update below configured sample/view thresholds; report limitations |
| 9 | `clipping/sections.py`, `app/repositories/cache.py`, `clipping/media.py`, `analytics/reports.py` | Exact cache keys did not reuse a larger containing section or expose reuse rate | Implement verified containing-section lookup and local A/V trim; persist exact/contained hit, miss, reused bytes and expose measured cache efficiency | Container/codec timestamp or audio sync errors; telemetry starts from migration 6 | Avoid repeat network acquisition for contained windows; end-to-end time saved remains unmeasured | Synthetic integration fixture proves trimmed A/V range, hash validation and no network call; API/report tests cover instrumented counters, but production samples remain empty until real runs |
| 10 | `clipping/pipeline/resources.py`, config, `clipping/media.py` | Static resource caps lack workload measurements and adaptive modes | Add FAST/BALANCED/MAX_QUALITY profiles and a compute budget policy only after per-stage time/resource metrics exist | More modes increase configuration and quality variance | Predictable throughput/resource tradeoffs | Configuration contract tests and benchmark comparison on the same synthetic corpus |
| 11 | API/workspace/reporting | Growth dashboard metrics do not yet include best measured patterns | Add honest reports for best/worst measured clips, follower conversion, duration, hooks, hashtags, CTA and posting slots with sample counts | UI can overstate weak correlations | Faster operator review | API/UI tests show sample bases and an “insufficient data” state |
| 12 | Tests and release docs | End-to-end behavior must preserve bounded downloads and disabled publishing | Extend offline synthetic integration coverage, audit package contents and document limits | Network fixtures could accidentally contact platforms | Regression confidence across the supported pipeline | Full configured tests, Ruff, smoke, wheel/import check, secret scan and no outbound social activity |

## Implementation status (October 21, 2026)

- **Implemented:** items 1–9 and 11. The local queue and timing recommendation
  remain review-only; hashtag suggestions use explicitly observed platform tags
  and require three clips before a tag affects history scores.
- **Implemented:** item 7. Profile visits, follower conversion, observation
  provenance, UTC daily/weekly/monthly aggregates and field-specific sample
  counts are validated and reported.
- **Implemented:** item 11. The workspace shows best/lowest clips, duration,
  detected-hook, observed hashtag and CTA patterns, period summaries and
  posting-time recommendations with sample counts and fallback basis.
- **Implemented and verified:** item 12. The configured suite passes (610 passed,
  1 skipped); Ruff, `git diff --check`, runtime smoke, wheel build/content audit,
  target-directory install/import check and credential-pattern scan pass. The
  wheel excludes `legacy/` and `tests/` and includes the workspace and default
  configuration. The import check used the available system dependency set; a
  fully isolated dependency installation was not performed.
- **Partial:** item 10. Explicit `fast`, `balanced` and `max_quality` H.264
  profiles preserve `balanced` as the default, and a repeated synthetic encoder
  benchmark reports time, size and PSNR. Per-stage resource telemetry, 1080x1920
  representative media, memory peaks and an adaptive budget manager remain open.

## Non-goals and hard constraints

- Do not install all libraries from the PRD. See [dependency audit](DEPENDENCY_AUDIT.md).
- Do not claim speed, retention, virality, best posting time or follower uplift
  without measured observations and sample sizes.
- Do not full-download long sources; do not weaken bounded download validation.
- Do not turn local prepared posts or a queue into a public upload. Publishing,
  posting, following, commenting and other account activity remain disabled.
- Preserve the approved `studio`/`fit` defaults for standard clips and the
  explicitly selected colorized production launcher behavior.
