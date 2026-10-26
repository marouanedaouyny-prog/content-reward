# Configuration

`pyproject.toml` is the supported dependency source. Requirements files are
compatibility entry points; old pins live under `legacy/`. Install `.[dev]` for
tests/lint and `.[transcription]` for local Whisper. No paid service is required.

Settings precedence: `config/default.yaml`, the development/production profile,
optional `CONTENT_REWARD_CONFIG` YAML, then recognized environment overrides.
Unknown fields, wrong types, nonfinite values, invalid bounds and unsupported
publishing enablement fail with a redacted CONFIG_ERROR. Do not put secrets in YAML.
Existing saved orders keep their recorded rendering/count/campaign settings.

`whisper.model` selects a model name or local model folder; `WHISPER_MODEL` takes
precedence through the settings loader. Cache lookup resolves that selected model.
An unrelated cached tiny model cannot override a configured larger model. The
default remains `tiny.en`; an English-only choice uses a multilingual `small`
model for non-English or automatic-language input. Model downloads still require
network access. Optional segment and word confidence diagnostics in transcript
JSON are evidence for review, not proof that the speech was transcribed correctly.

| Setting | Purpose |
|---|---|
| `clips.target_count` | Positive production target, default 20 |
| `clips.min_duration/max_duration/target_duration` | Candidate bounds and preferred length |
| `captions.style`, `production.caption_style` | General studio vs approved colorized production choice |
| `video.framing` | Full-image fit by default; saved crop remains supported |
| `selection.weights`, `selection.editorial` | Normalized evidence weights and all editorial coefficients |
| `source_filter.*` | Cheap source metadata score, coverage floor, long-form duration and freshness bounds |
| `selection.minimum_score` | Strict production minimum based on available evidence |
| `dedup.*` | Source overlap, transcript/embedding similarity and repeated quote length |
| `quality.*` | Speech density/gaps, FPS, silence, black, duration and caption bounds |
| `worker.concurrency/render_concurrency` | 1-4 API workers/render slots; conservative default 1 |
| `worker.download_concurrency` | Download admission slots, default 1 |
| `worker.cpu_threads/memory_limit_mb` | Encoder threads and FFmpeg allocation budget; not hard RSS isolation |
| `video.encoder_profile` | `fast`, `balanced` (default; preserves current preset/CRF), or `max_quality` encoder tradeoff |
| `worker.maximum_attempts/retry_base_seconds` | Finite retry budget and exponential base delay |
| `whisper.model/device` | Selected model name or local model folder and CPU/CUDA/auto choice; GPU remains hardware dependent |
| `feedback.minimum_samples/maximum_adjustment` | Independent sample minimum and bounded ranking adjustment |
| `publishing.enabled` | Must remain false; uploads are not implemented/authorized |
| `posting.timezone/default_windows` | IANA timezone and cold-start windows; measured account slots replace fallback only after `minimum_history_samples` |
| `posting.max_per_day/minimum_gap_minutes` | Per-platform local review-queue frequency limits |
| `posting.same_source_hours/same_topic_hours` | Prevents near-term repetition in the prepared queue |

Environment overrides: `CLIPPING_STORAGE`, `CLIPPING_DATABASE`, `CLIPPING_OUTPUT`,
`CLIPPING_TARGET_COUNT`, `CLIPPING_CPU_THREADS`, `CLIPPING_MAXIMUM_ATTEMPTS`,
`WHISPER_MODEL`, `WHISPER_DEVICE`. `CONTENT_REWARD_PROFILE` chooses development or
production. Credentials such as `YOUTUBE_API_KEY` and `INSTAGRAM_*` remain separate
local environment values used by existing discovery/authentication modules.
The configuration loader does not copy credentials into settings or logs.

`POST /api/v1/queue` stores a local `READY` or `SCHEDULED` review item;
`GET /api/v1/queue` lists it, and `GET /api/v1/posting-time/{platform}` provides a
sample-supported recommendation. These routes do not start a publisher or make
network account calls. Historical timing uses only observations linked to a
publication record with explicit external-publication evidence; otherwise the
configured local-time windows are returned as a fallback.

`POST /metrics` accepts optional `hashtags`, `cta_used` and
`measurement_context` when recording manual/imported outcomes. Existing rows keep
unknown fields unknown. `GET /metrics` remains a descriptive report with UTC
daily, weekly and monthly aggregates and field-specific sample counts.

Learned recommendations require an explicit comparable context:

```json
{
  "account_id": "my-youtube-channel",
  "reporting_window_hours": 24,
  "view_definition": "engaged_views",
  "definition_version": "export-v1"
}
```

These are non-secret measurement labels, not account credentials. Supply the
same context on the imported observation and the order that should learn from
it. A complete context needs an account, a positive finite reporting window and
a known view definition (`play_starts`, `engaged_views`, `qualified_views` or
`platform_reported`). Keep different definitions and reporting windows separate;
the optional version is also part of the comparison identity. Old observations
without context remain descriptive and cannot supply learned recommendations.

Save the context as a small local JSON file (at most 8 KB), then use:

```powershell
.\.venv\Scripts\content-reward.exe run --new --niche Business --learning-context learning-context.json
```

API orders accept the same object in `POST /orders` as `measurement_context`.
An order freezes its learning cutoff at creation. Resume preserves that context;
omit the flag to keep it, or supply an identical file. A changed context requires
a separate new order. No performance observations are created by starting a run.

`POST /hashtags/suggest` accepts `measurement_context` and optional `niche`.
`GET /growth-insights` accepts the context fields as query parameters, plus
`platform`, `niche` and a timezone-aware `as_of`. Missing context produces
`insufficient_data` with reason `learning_context_required`, and unqualified
mixed platform/niche histories cannot produce a global recommendation. Complete
scopes still require the independent sample minimum. Copies and materially
overlapping source windows count once; missing follower outcomes are not zeros.
`average_view_percentage` and `audience_watch_ratio` can record rewatching above
100% or 1, respectively, and are never substituted for completion or retention.

Schema migrations 9 and 10 add nullable measurement fields and an experiment
scope with the historical `single_moment` default. Existing databases receive
a consistent SQLite backup before pending migrations. Content-block experiments
are opt-in through `analytics.experiments.create_experiment(...,
scope='content_blocks')`. Register identical variant settings across distinct
persisted moments with `add_variant`; `compare_variants` includes only blocks
covered by every variant and requires enough known, positive-view paired samples
for each outcome. It exposes missing variants and paired-block counts. Replicas
of one moment cannot establish independent support, and observed differences
are not evidence of causal uplift.

The model resolver prefers a compatible already-cached model; `WHISPER_MODEL`
explicitly selects a model/path. English-only `tiny.en` requires English mode;
other languages/auto use a compatible multilingual cache or configured fallback.
No model download happens in smoke tests. GPU activation does not install CUDA.

Final exports remain in `clips/` for compatibility. Runtime data lives under
`storage/clipping`; jobs, orders, sections, models, review frames and generated
transcripts retain their historical locations. The domain DB is
`storage/clipping/content-reward.db`; the existing API job DB default remains
`data/clipping.db`. Ignored local data and credentials were not relocated.

Use `--storage` for CLI order workspaces. `CLIPPING_DATABASE` independently controls
the standalone API/worker job DB. Avoid pointing either at an archived application's
DB. Container defaults bind only `127.0.0.1:8000`; the default Compose stack now
runs clipping. Compatibility wrappers preserve older explicit orders and styles.
