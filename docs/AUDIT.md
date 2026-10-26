# Content Reward current-state audit

Audit baseline: commit `6fd405d`, 252 tracked files. Inspected tracked inventory,
Python imports and definitions, launchers, container setup, dependency files,
active SQLite schema (read-only), test entry points, and runtime implementation.
No private media, credentials, or historical orders were modified during audit.

## Active application and dependency graph

`clipping/` is the supported runtime. It has **no Python imports from** `backend/`,
`project/`, or the old `scripts/`. `clipping.app` serves the workspace and API,
starts a media queue consumer and optional trend consumer, and uses
`ClippingWorkflow` for durable jobs. `clipping.autorun` calls `Controller`, which
dispatches partial batches to `batch` or larger batches to `production`.
`sections` obtains public captions before acquiring bounded source windows.
`media` owns FFmpeg, transcript inference, and rendering. `windows_process`
owns Windows process-tree cleanup. `planning`, `captions`, `caption_styles`,
`caption_review`, and `clip_review` implement selection and quality checks.
`research` and `trends` perform metadata analysis and discovery. Instagram
authentication is separate from media production; it does not authorize posting.

Entry points: `python -m clipping` (local API), `python -m clipping.autorun`
(resume latest unfinished production order or start a new 20-clip run),
`python -m clipping.orchestrator` (explicit order), and the Windows wrappers.
Production defaults are colorized/fit; the general visual template is studio/fit.
Saved orders retain their settings. Final exports live in `clips/`.

## Legacy components

| Component | Current purpose/dependency | Disposition |
|---|---|---|
| `backend/` | SQLModel Empire API used by old workers | Isolate intact |
| `frontend/` | Next.js dashboard for Empire API | Isolate with its API |
| `scripts/` except `verify_twenty_clips_local.py` | Empire agents, workers, scheduler, AI router | Isolate with backend |
| `workflows/`, `n8n/` | Old orchestration definitions | Isolate, retain relative names |
| `social-connector/` | Separate multi-platform service; not used by clipping | Move tracked code only; leave credentials/data in place |
| `project/` | Another campaign/skills/SQLModel application | Isolate intact |
| `architecture/`, old PRDs, `str.txt` | Historical designs/notes | Preserve under legacy |
| `tests/unit`, `tests/integration` | Import old backend and scripts | Move with their implementation |

The old scripts import one another through `scripts.*` and `backend.*` and use
relative workflow paths. Retaining a self-contained `legacy/` execution root
preserves these relationships without making them production dependencies.
Legacy code is **not certified production-ready**. No deletion is justified by
the absence of imports from clipping alone.

## Duplicate responsibilities and dead/overridden code

Three generations implement campaigns, media, persistence, publication, and
analytics. The old `scripts/ai_router.py` defines `BaseProvider` and
`GroqProvider` twice; later definitions shadow earlier ones. Historical discovery
snapshots in `clipping/automation.py` are labeled snapshots, not live rankings.
No general dead-code deletion is planned: dynamic worker registries and optional
integration imports make purely static reachability insufficient evidence.

## Persistence and resume

The active database currently has `clipping_job`, `clipping_setting`, and
`clipping_trend_run`. Jobs store request/output JSON inside transactional SQLite
rows. Approvals use fingerprints; reward updates use write transactions.
Controller orders instead use `orders/<uuid>/order.json`, `latest.json`, and
`events.jsonl`; production uses per-order workflow databases. There are no
versioned migrations for a normalized shared domain store.

Media stages skip work based on checkpoint keys. Source and export hashes are
recorded, but `_prepare` does not verify every checkpoint before skipping its
stage. A missing or altered transcript can therefore be reused until a later
failure. Order manifests and DB state require an explicit ownership/migration
policy; existing data must never be silently replaced.

## Selection and quality

Existing selection already considers completed sentences, question/answer
context, transcript topic words, filler, ads, introductions, gaps, duration, and
real replay heatmaps. It rejects overlapping windows and repeated word/shingle
signatures across saved orders. These are editorial heuristics, not validated
virality predictions. Weights and similarity cutoffs are scattered. Embedding
similarity and measured speaker energy are not implemented; missing evidence
must remain unknown. Arbitrary emotion/novelty scores would be misleading.

`clip_review.verify_export` checks streams, dimensions, hashes, timing, source
speech agreement, full decoding, audible audio, and writes review frames. It
checks independent source-speech agreement only when `source_reference` timed
cues exist; otherwise matching subtitles to their own ASR cannot establish
speech completeness. It counts black-frame markers but does not reject them. It has no explicit FPS or
subtitle-width checks. Visual/editorial review remains necessary; mechanical QC
must not be presented as a complete artistic or transcription review.

## Reliability and security findings

1. **High: unbounded retries.** `workflow.consume_once` persists
   `maximum_attempts: null` and retries temporary download failures forever.
   The outer order controller has bounded retries, so the policies disagree.
2. **High: stale checkpoints.** Recorded artifacts must be checked for existence,
   containment, and content hash before resume skips their producing step.
3. **Medium: incomplete QC enforcement.** Black detection is collected without a
   rejection gate; FPS and sensible file size also need structured checks.
4. **Medium: error/log leakage.** Several workflow failures persist `str(exc)`;
   the API worker uses exception tracebacks. Legacy providers log response text.
   Normalize public failures and redact credential-bearing values centrally.
5. **Medium: legacy download path.** `media.ingest` still supports full remote
   source acquisition for older workflows; new production uses sections. New
   remote intake must consistently use bounded ranges, never full-source fallback.
6. **Medium: fragmented dependency setup.** Root requirements describe the old
   application, clipping has a separate range-based set, transcription another.
   The global interpreter and `.venv` differ. During audit the global interpreter
   lacks `faster-whisper` and `sqlmodel`; this is not evidence that the local
   transcription interpreter lacks its installed model.

Positive controls: local-only API bind and Docker port, browser-origin checks,
storage containment, non-shell subprocess argument lists, process-tree cleanup,
credential-free public discovery output, OAuth state validation, and ignored
environment/credential/export directories. No committed secret was found in the
initial repository scan; a scan is not proof against every possible secret.

## Tests and tooling

The existing clipping suite passed **406 tests** before this task. A fresh
baseline also passed: **406 tests in 148.63 seconds**. Tests include synthetic FFmpeg renders,
API/worker integration, checkpoint resume, source boundaries, captions, Windows
cleanup, OAuth, and discovery mocks. The older root-wide test collection fails
without `sqlmodel`, so it must be explicitly separated from supported tests.
No root pyproject, lint/type policy, normalized domain tests, or smoke command
exists yet. Existing source includes historical trailing whitespace; blanket
formatting is outside this refactor.

## Configuration and delivery constraints

Configuration is split among environment variables, controller dataclass
defaults, template constants, wrappers, and scattered weights. Keep historical
saved settings authoritative. Central configuration must validate unknown keys,
ranges, finite numeric values, and resource limits. Secrets remain local.
Preserve `clips/` as the default user delivery directory under the standing
workflow; optional export destinations may coexist. Publishing stays disabled;
manual export must record readiness without claiming a public post exists.

## Final verification

The final supported run used the required Windows environment command:
`.venv/Scripts/python.exe tests/clipping/run_tests.py tests -q` — **552 passed,
1 skipped**. Repository-configured lint passed with
`.venv/Scripts/python.exe -m ruff check .`. The offline in-repository smoke
passed configuration, FFmpeg/ffprobe, dependencies, Whisper availability,
temporary storage, isolated SQLite, worker, and loopback API checks.

The built wheel was installed into an isolated target and imported with the
repository absent from the working directory. Its CLI smoke, including API
startup and worker probe, passed. The wheel check caught and fixed omission of
the `growth` runtime package in setuptools discovery. `git diff --check` passed.
A final pattern scan found no AWS, Google API, GitHub, or private-key-shaped
secrets in the supported tree; ignored local data and `legacy/` were excluded.

Analytics regressions cover multi-platform reward aggregation per clip, malformed
reward validation, pending campaign decisions, render attempts, calendar-span clip
rates, order-linked reward/hour, and manual-preparation vs actual-publication
separation. The report keeps metrics unknown when their evidence is absent.

Official platform publishing and automatic performance collection remain
unimplemented and disabled. The system does not claim public uploads, verified
platform metrics, guaranteed rewards, or causal experiment results. Manual export
is local review preparation only.
