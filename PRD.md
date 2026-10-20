# Content Reward — Hardening and Project Reorganization

This is the canonical, deduplicated specification supplied by the user. The
implementation order and detailed file changes are in `docs/REFACTOR_PLAN.md`;
the factual pre-change baseline is in `docs/AUDIT.md`.

## Product goal

Turn the experimental repository into a production-oriented Content Rewards
system: discover → understand → select → validate → partially download →
transcribe → render → review → prepare publication → measure → learn → improve.
Optimize eligible clip quality, low manual effort, reliability, and measurable
reward per unit of time/compute, rather than output count alone. A numeric
quality target is aspirational; verification must describe concrete evidence.

## Non-negotiable compatibility and security

- Make `clipping/` the obvious supported runtime. Analyze imports before moves;
  preserve useful legacy code under `legacy/` and document deletion criteria.
- Preserve working behavior, Windows support, existing orders, source intervals,
  local credentials and media. Never migrate user data by moving whole folders.
- General captions remain studio/fit. The approved production launcher uses
  colorized/fit, defaults to 20 clips, accepts larger targets, searches freshly
  for new orders, and reports genuine shortfalls without duplication.
- Inspect public captions/replay first and download selected ranges only. No
  full-source media/audio fallback. No fabricated intelligence or viral claims.
- Publishing remains disabled. Build mock/manual-export adapters first; official
  integrations must not claim success without verified access and a real post.
  No credential bypasses, cookies/passwords/tokens in chat, or outbound posting.
- Prefer local/free tools; paid services can only be optional. Keep secrets out
  of Git/YAML/logs, use safe subprocess arguments, validate URLs and paths, bind
  the API locally, sanitize filenames and redact errors.

## Architecture and repository ownership

Separate API/core/models/repositories/workers from clipping discovery,
selection, download, transcription, captions, rendering, quality and pipeline.
Keep publishing, campaigns and analytics as independent modules. Introduce
folders when they create useful ownership; do not force a tree at the expense
of working imports. Pipeline orchestration calls focused modules, not modules
that secretly control the entire workflow. Dashboard work is secondary.

## Selection, candidates and duplication

Generate candidates using transcript topics/transitions, replay peaks,
question/answer boundaries, chapters, keyword triggers and measured high-energy
speech when available. Source engagement can inform ranking, not invent moment
boundaries. Merge/refine overlaps, deduplicate, rank. Score from traceable hook,
semantic/educational value, completeness, standalone context, surprise/emotion
when supported, source velocity/popularity/engagement, speech density, silence,
duration and intro/outro/ad penalties. Keep normalized weights in config. Missing
replay, embeddings or audio energy remain unknown, never fake values.

Deduplication considers source IDs, timestamp overlap, transcript similarity,
repeated quotes and optional supplied semantic embeddings. Thresholds are
configurable, including example overlap .65, transcript .85 and semantic .88.
Exclude previously used intervals and repeated takeaways across runs.

## Quality validation

Pre-render: complete beginning/thought/answer, duration range, enough speech,
limited silence, no obvious ads/intros/outros, no duplication, campaign rules.
Post-render: nonempty sensible file size, decodable video/audio, expected
resolution/aspect/duration/FPS, captions present/timed/readable/within bounds,
no excessive black frames or silence. Return structured passed/score/checks
and actionable failures. Preserve the distinction between automated checks and
human review of speech accuracy, visual framing and editorial quality.

## Campaigns and publishing

Campaign fields: stable ID, platform/title/creator, structured rules, minimum
views, duration bounds, allowed platforms, required hashtags, prohibited content,
payout model, deadline, source requirements and status. Parse rules conservatively;
unsupported prose must request manual structured review rather than infer safety.
Validate source → clip → metadata → destination; return eligible/violations/warnings.
Failed validation always blocks publication. Do not depend on unstable Whop scraping.

Publisher interface: `publish(clip, metadata)` behind platform adapters and a
manager. Start mock and manual export, preserve real external IDs/URLs when
available. Lifecycle: READY, PUBLISHING, PUBLISHED, PUBLISH_FAILED, SUBMITTED,
APPROVED, REJECTED, PAID. Manual export must not invent PUBLISHED. Publishing
must be idempotent and refuse changed artifacts or invalid campaigns.

## Data, state and reliability

SQLite is the source of truth, with versioned additive migrations and stable IDs
for orders, sources, candidate moments, clips, campaigns, publications, performance
metrics, rewards, pipeline events and experiments. JSON remains an export/debug
format and a supported historical import path. Existing data must survive migrations.

Explicit state machine: CREATED, DISCOVERING, SOURCES_FOUND, ANALYZING,
CANDIDATES_READY, DOWNLOADING, TRANSCRIBING, RENDERING, VERIFYING, READY,
PUBLISHING, PUBLISHED, SUBMITTED, COMPLETED, FAILED; add documented recovery
states as needed. Log every transition and reject invalid transitions clearly.
Resume reuses only existing hash-verified artifacts and starts at the failed
step, without redoing a valid download or transcript.

Normalized errors expose code/retryable/stage. Categories: NETWORK_ERROR,
SOURCE_UNAVAILABLE, DOWNLOAD_ERROR, TRANSCRIPTION_ERROR, RENDER_ERROR,
VALIDATION_ERROR, PUBLISH_ERROR, RATE_LIMIT, AUTH_ERROR, CONFIG_ERROR.
Use finite exponential backoff for retryable errors only. Never infinite retry.
Structured logs include timestamp, level, order_id, clip_id, stage, event,
duration_ms, error_code and message; redact secrets and untrusted provider text.

## Configuration, cache, storage and resources

Central validated `config/default.yaml`, development and production overlays;
environment secrets in local `.env`. Defaults preserve approved saved settings.
Expose clip counts/durations, captions/framing/resolution, scoring/dedup/QC,
worker/render/download concurrency, CPU threads, Whisper model/device and memory
limits. Remain safe on ordinary consumer hardware.

Standard storage areas: orders/sources/transcripts/renders/temp/logs/cache.
Deterministic keys for metadata/transcripts/sections/search/replay; avoid repeated
expensive work and verify cached artifacts. Keep approved final `clips/` delivery
compatible; support explicit export folders rather than silently moving old clips.

## Performance, experiments and feedback

Store per clip/platform: views, likes, comments, shares, saves, average watch
time, completion, retention, followers, campaign acceptance/rejection/reason,
reward amount and collection time/provenance. Unknown metrics stay unknown.
Start with validated imported/manual observations and deterministic rules.
Historical evidence gradually adjusts future ranking with bounded changes and
minimum sample counts. Do not build complex ML prematurely.

Variants link experiment_id, source_moment_id, variant, settings and performance.
Compare actual measured outcomes with sample counts, not causal claims from
tiny samples. Track generated clips/day, render and publish success rates,
pipeline duration, campaign acceptance, views/clip and reward by clip/source/
niche/hour; report denominators and missing values honestly.

## Interfaces, dependencies and tests

Use `pyproject.toml` as dependency source, with explicit optional dev,
transcription/GPU and publishing needs; no duplicate incompatible core pins.
Canonical CLI: content-reward run/resume/status/worker/api, clips list,
campaigns list, validate, reports and smoke. Keep Windows wrappers thin and
existing `python -m clipping` flags compatible.

Typed FastAPI routes: health; orders create/list/detail/resume; clips list/detail;
campaigns list/validate; metrics. Retain existing routes for compatibility.
Dashboard eventually shows active orders/stages/clips/errors/posts/views/rewards,
but do not redesign it before the architecture stabilizes.

Unit tests: scoring/dedup, rule parsing/validation, transitions, safe paths,
configuration, QC and resume. Integration: metadata → candidate → fake bounded
download/transcript → real synthetic render → QC, without large real downloads.
Smoke: FFmpeg/ffprobe, dependencies, DB, writable storage, config, Whisper,
local API startup and worker startup. Missing optional tools are explicit.

## Required execution order and definition of done

1. Audit whole repository; write `docs/AUDIT.md` and exact-file `docs/REFACTOR_PLAN.md`.
2. Isolate legacy safely; run tests after significant moves.
3. Centralize config, state, errors, logging and verified resume.
4. Improve candidate generation/scoring/dedup and pre/post QC.
5. Add migrations, normalized repositories/models and DB ownership.
6. Implement structured campaigns/rules/eligibility gates.
7. Implement publishing architecture with safe mock/manual export.
8. Implement observation collection, statistics, experiments and feedback.
9. Complete business tests, offline integration, CLI/API and smoke coverage.
10. Rewrite README/PRODUCT and architecture/pipeline/config/troubleshooting/legacy docs.

Work automatically without approval except genuinely destructive data/secret
operations. Prefer focused commits, tests after each significant change, configured
lint/type checks, and smoke. Do not rewrite working behavior for aesthetics or
claim platform publishing/metrics work before verified. Completion requires one
clear architecture, isolated legacy, working/resumable pipeline, centralized
scoring/config, real QC and logging, normalized migrated data, campaign gates,
manual publishing, performance/feedback foundations, meaningful passing tests,
Windows-compatible commands, accurate docs and no exposed secrets.
