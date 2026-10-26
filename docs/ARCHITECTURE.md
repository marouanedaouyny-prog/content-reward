# Supported architecture

`clipping/` owns the running system. `clipping.app:app` mounts the existing
workspace and compatible routes plus typed domain routes from `app/api/routes.py`.
The CLI dispatches to the same autorunner, controller and job engine. There is no
second production backend, n8n dependency, or Next.js dependency.

An optional [PHP social SDK companion](SOCIAL_PHP.md) is called by
`clipping/social_bridge.py` over local JSON stdin/stdout. It currently supports
TikTok OAuth and read-only identity checks. It has no HTTP listener or publishing
route, does not persist credentials, and does not change clipping order state.
PHP dependencies are locked separately in `integrations/social-php/composer.lock`.

## Ownership

| Module | Owns | Does not establish |
|---|---|---|
| `clipping/trends`, `youtube_browser`, `growth/source.py` | Public source discovery, observed metadata and cheap pre-transcript ranking | Moment popularity or reposting rights |
| `clipping/discovery` | Resilient source discovery: query families, provider chain, tiered eligibility, explainable ranking, bounded cache and provider health | A prediction of future views, or a download of source media |
| `clipping/planning`, `selection/`, `sections` | Cue-based candidates, evidence scores, dedup, bounded downloads | Guaranteed virality or unavailable private analytics |
| `clipping/media`, `_transcribe`, `captions`, `caption_styles` | Local speech timing, FFmpeg, approved visual styles | Perfect ASR or editorial review |
| `clipping/quality`, `clip_review` | Pre-render gates, strict decode, audio/FPS/black/silence/subtitle checks | Artistic approval or independent speech truth without source cues |
| `app/core` | Strict settings, normalized errors, state contracts, redacted structured logging | External authorization |
| `app/repositories` | Transactional migrations, authoritative orders and normalized records | That JSON exports can overwrite DB state |
| `campaigns/` | Structured rules and source/content/metadata/destination eligibility | Complete interpretation of arbitrary prose |
| `publishing/` | Idempotent local packages and explicitly simulated mocks | A real platform upload |
| `analytics/` | Imported observations, experiments, reports, bounded feedback | Automatic verified collection or causal uplift |
| `growth/timing.py`, `posting_queue` | Timezone-aware local review schedule, account-evidence timing recommendations and spacing checks | A publisher, account connection or public post |

## Persistence and compatibility

`storage/clipping/content-reward.db` owns production orders and normalized sources,
candidate moments, clips, campaigns, publications, performance observations,
rewards, local posting-queue entries, cache-access observations, events, experiments and variant relationships. Migrations are versioned
and preserve existing records; the experiment migration permits multiple independent clips per variant. Every write uses parameter binding, explicit transactions and
foreign keys. Existing DB snapshots use SQLite's backup API so live WAL data is
included. Existing job/trend/OAuth tables are preserved in their existing DBs.

Order state and revision are read in one SELECT. Updates compare revisions and
fail clearly on a stale writer. An existing DB record always wins over historical
JSON. Import obtains an order lock, validates identity/size, and marks the import
in the same transaction. Invalid manifests are recorded as import warnings;
busy ones wait for a later import. They are never discarded or silently replaced.
Missing JSON exports do not prevent DB-backed resume or historical reservations.

`ClippingWorkflow` still owns its compatible SQLite job records and review gates.
New state transitions are checked against its explicit graph and logged within
the update transaction. Controller stages project its existing resumable workflow;
they do not replace the separate job approval lifecycle.

`CacheRepository` stores bounded JSON source metadata/transcripts/replay records,
per-run search responses, and bounded section file references in SQLite. Search
keys include the research-run ID to preserve fresh discovery for each new order.
File references are reused only while their expiry, size, and SHA-256 still match.
For bounded media sections, a valid cached window may also satisfy a smaller
contained request; the requested range is locally trimmed and re-probed before
reuse. Invalid trims fall back to the exact bounded remote request.

The posting queue accepts reviewed local clips and stores READY/SCHEDULED records.
Posting-time recommendations use a weekday/hour bucket only after the configured
number of actual performance samples; otherwise they select a configured
cold-start window in the account timezone. Only publication records with explicit
network-attempt evidence count as account history.

## Execution and resources

The API can start 1-4 queue consumers, each with its own workflow object and
lease heartbeat. SQLite claims prevent duplicate jobs. Process-local admission
gates bound rendering, downloads, and transcription; transcription stays serialized
to contain model memory. FFmpeg threads and allocation size are configurable.
Allocation limits are not a hard RSS/container limit. Windows process-tree
ownership and cancellation remain in `windows_process.py`.

Selection uses configured editorial coefficients and normalized available
signals. Each score records weights, evidence and missing signals. Observed
completion can adjust matching duration/question/caption patterns only after a
minimum number of distinct clips; snapshots of the same clip do not inflate
sample counts. See [selection details](SELECTION.md).

Source prefiltering scores metadata before caption retrieval and rejects only
when evidence coverage clears its configured floor. Hashtag candidates come
from supplied niche/topic evidence plus related discovery terms, with recent-use
freshness and account history exposed per tag. Experiment comparisons permit at
most two dimensions, group replicated clips by variant, and suppress outcome
averages until each variant reaches its configured minimum independent clips.

Discovery searches through a fixed provider chain (`youtube_api`, `yt_dlp`,
`selenium`, `public_search`). A provider only searches: it returns broad public
metadata and never decides whether a video is usable. A provider failure is
reported with a stable code and the chain continues, so one broken provider
never ends a search. Query families give each niche several phrasings, and
eligibility is evaluated as `strict`, `medium` then `relaxed` tiers; the tier
that produced the sources is named in the result and every rejection is
counted by reason. Ranking uses six documented public signals with the
available evidence renormalized and the coverage reported. Repeated searches
reuse a bounded cached result keyed by query, provider, region, language and a
hash of the active rules. Discovery never downloads media and never contacts a
social account. `content-reward discover` and `content-reward discovery-health`
expose the candidate pool, the diagnostics and the provider health without
starting a clip. See [DISCOVERY_AUDIT.md](DISCOVERY_AUDIT.md) and
[PROVIDERS.md](PROVIDERS.md).

The existing browser workspace is preserved. Dashboard redesign is deferred.
Archived systems and original environment/data paths are documented in
[LEGACY.md](LEGACY.md).

## Implementation references

Transaction behavior follows the [Python SQLite documentation](https://docs.python.org/3/library/sqlite3.html).
Strict domain validation follows [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/).
Dependency metadata follows the [Python packaging guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).
