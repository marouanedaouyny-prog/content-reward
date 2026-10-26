# Performance audit

Initial audit: 2026-10-20; local selection measurement added 2026-10-22.
The encoder and transcript fixtures below measure narrow paths. Representative
pipeline throughput and peak resource measurements remain open.

## Current pipeline and cost controls

| Area | Current path / evidence | Cost or weakness | Safe next measurement |
|---|---|---|---|
| Discovery | `clipping/trends.py` invokes configured public search providers; per-run results use `CacheRepository` | Provider latency, rate limiting and result quality vary; every fresh order intentionally starts fresh discovery | Log provider, elapsed time, result count, cache hit/miss and failure class per research run |
| Metadata and transcript | `clipping/sections.py:inspect_source` requests metadata and public captions before media; transcript/replay is cached with TTL | Caption language/provider fallback may repeat extractor work after unusable captions; no transcript means source rejection instead of full download | Count metadata/caption requests and rejection reasons by source without recording signed URLs or credentials |
| Candidate scoring | `clipping/planning.py` builds a capped candidate pool and `clipping/sections.py:select_moments` refills after exclusions | Repeated pool generation and pairwise dedup can grow with candidate count; no labeled benchmark establishes scoring quality | Record candidates entering each prune stage and stage duration; evaluate ranking against reviewed examples |
| Partial download | `clipping/sections.py:download_section` uses yt-dlp `--download-sections`, validates bounds and caches verified files | Network transfer and keyframe seeking dominate; each selected moment may require its own remote acquisition | Record requested seconds, downloaded bytes, actual duration, cache outcome and elapsed time per section |
| Section reuse | `app/repositories/cache.py` verifies expiry, byte size and SHA-256; `clipping/sections.py` can trim a verified containing section locally and validate its A/V range; access outcomes and reused bytes are persisted and reported | Local re-encoding consumes CPU; production cache hit rate and net time saved are not yet available | Use the measured counters after actual orders run; benchmark trimmed reuse against a bounded redownload on the same synthetic corpus |
| Transcription | `clipping/media.py:transcribe` starts isolated `_transcribe.py`; faster-whisper uses local model/VAD when installed | Model load/inference and CPU/RAM dominate; process isolation repeats interpreter/model initialization per section | Record model/device, section duration, elapsed time, failure/timeout and memory where available; compare captions-first hit paths |
| Silence and reframing | `clipping/media.py` calls `clipping/silence.py` and `clipping/framing.py` only when enabled/reliable | Decode/sample scans add CPU; reliability threshold and fallback need benchmarked review clips | Count sampled frames and processing time; compare automatic framing with fit on a fixed reviewed sample |
| Render | `clipping/media.py` runs FFmpeg for each final clip; `clipping/pipeline/resources.py` bounds render concurrency and CPU threads | Encoding is likely the dominant local compute stage; current resource limits are concurrency controls, not a hard memory cap | Record render wall time, output bytes, resolution/FPS/codec and configured thread count per clip |
| QC | `clipping/clip_review.py` decodes exported media and checks audio/video/captions | Full decode is intentionally expensive but catches corruption; avoid weakening it without equivalent evidence | Measure QC duration separately and retain strict decode as the production gate |
| Persistence and resume | SQLite repositories persist order/stage/event data and artifact hashes; retry resumes checkpoints | Some intermediate state remains in compatibility job DBs/JSON exports, so cross-store joins cost complexity | Instrument database query/write time and count re-used versus invalidated checkpoints |
| Metrics and feedback | `analytics/collectors.py`, `analytics/reports.py`, `analytics/feedback.py` use imported/manual observations | No automatic platform collection is established; small samples must not be treated as predictive | Track observation sample count, distinct clips, metric coverage and feedback support status |

## Full-media and repeated-work audit

- Supported batch source acquisition calls the bounded section downloader; the
  implementation validates the selected range and has no full-video fallback.
- Public captions are requested before media sections. When they are unusable,
  the source is rejected; the pipeline does not fetch a full source as a rescue.
- Same-run search, transcript/replay, and exact section assets have cache paths.
  Cache verification checks expiry and file integrity. A larger cached range can
  now satisfy a contained request via local A/V trim and strict range validation.
  Exact/containing hits, misses and reused bytes are instrumented; production
  samples and end-to-end savings still need to be observed.
- Transcription is isolated and serialized by the resource gate. Reusing an
  already cached transcript avoids it; repeated model startup for distinct
  sections is a measurable optimization opportunity, not yet proven a bottleneck.
- No benchmark in this audit establishes whole-pipeline CPU/RAM peaks, provider request savings,
  clips/hour, bytes/clip or end-to-end latency. Add instrumentation before
  claiming improvement.

## Selection payoff scan measurement

The standalone payoff check previously rescanned a long transcript prefix even
though its final-sentence rule cannot cross sentence punctuation. Restricting
that regex scan to the relevant suffix preserves the selection policy.
Differential checks covered 3,078 Unicode/punctuation/cue-boundary cases and
compared complete planner output on the following deterministic fixtures:

| Fixture | Cues | Median wall time before / after | Median CPU before / after | Complete output |
|---|---:|---:|---:|---|
| Dense distinct speech | 240 | 5.583 / 2.347 s | 3.375 / 1.719 s | Identical, 19 candidates |
| Repeated speech | 120 | 1.222 / 1.226 s | 0.805 / 0.734 s | Identical, 1 candidate |

Each variant ran twice in alternating order on Python 3.11.15 on this Windows
host, with no downloads or renders. Other verification work was running, so
wall time is subject to contention. The dense fixture's observed median wall
time decreased by 58%; the repeated fixture's wall time was effectively
unchanged. This is neither an end-to-end speedup nor a quality/uplift result.
Raw local timing/profile evidence is in
`.workflow-tests/selection-payoff-before-after-2026-10-22.json`; the dense fixture
SHA-256 is `08491e13d5c9d3a481fc4314bdf83639ef2d921502ad397adf9ecb392d28a1d6`.

## Risks

- Lower resolution, shorter QC, looser candidate scoring or fewer retries could
  improve apparent speed while reducing deliverable quality or resilience.
- Increasing concurrency can multiply model and FFmpeg memory use. Keep current
  conservative defaults until representative resource measurements justify a
  bounded change.
- Any benchmark must use deterministic synthetic media or a locally authorized
  fixture, and must not publish, contact social accounts, or download a full
  public source.

## Encoder profile smoke benchmark

`scripts/benchmark_encoder_profiles.py` compares the configured H.264 preset/CRF
pairs on a lossless FFV1 `testsrc2` fixture. It rotates profile order across three
repeats and reports median encode time, realtime factor, output bytes and PSNR.
On this Windows host, a 1-second 320x568 30-FPS sample with one thread measured:

| Profile | Preset / CRF | Median encode | Median output | Median PSNR |
|---|---|---:|---:|---:|
| fast | ultrafast / 25 | 93.7 ms | 203,324 bytes | 29.9258 dB |
| balanced | fast / 23 | 287.2 ms | 81,488 bytes | 29.8088 dB |
| max_quality | slow / 20 | 451.1 ms | 102,733 bytes | 29.8840 dB |

This low-resolution, video-only sample is a script and configuration check, not
representative 1080x1920 evidence or a perceptual-quality test. It does not measure
filtering, captions, audio, QC, memory or end-to-end pipeline time; keep `balanced`
as the default and choose profiles explicitly until representative local media is
benchmarked.

## Retained-section render and review probe

On October 22, one retained 40.08-second source window was rendered through the
actual pipeline with the approved colorized/fit composition, 1080x1920 at 30 FPS,
balanced encoding (`fast`, CRF 23), two CPU threads and FFmpeg 9.0.1. The source
section and cached transcript were hash-verified; no source was downloaded and
the probe created no production clip or publication.

| Measurement | Observed value |
|---|---:|
| Render wall time, including its embedded validation | 189.591 s |
| Separate full export review, including five review frames | 12.285 s |
| Directly monitored FFmpeg encoder CPU time | 273.344 s |
| FFmpeg encoder peak Windows working set | 476.74 MiB |
| Export size | 9,414,338 bytes |

The same output passed full decode, audible-audio/black/silence checks,
1080x1920 H.264/AAC verification and independent source/displayed-caption gates.
These mechanical checks do not establish speech truth or editorial quality.
The initial benchmark call omitted the saved local plan at review time; that
harness omission was corrected and the completed render was reused for review.
Render and review were therefore measured in separate invocations.

The sampler covered the Python process and directly launched tools. It did not
monitor descendants launched through interruption helpers, so the table reports
the encoder's own CPU/working-set counters rather than claiming total CPU or
peak memory for the full pipeline. Working set includes shareable pages. This
single fixture is not an end-to-end throughput estimate, an ASR benchmark,
a representative corpus, or a before/after optimization result. Keep current
conservative resource settings until broader measurements justify a change.
Compact evidence is in
[the retained-section probe](../research/2026-10-22-render-resource-probe.json).
