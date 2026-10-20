# Twenty-clip workflow implementation plan

> Execute in verified increments using the available executing-plans,
> incremental-implementation and test-driven-development instructions. Assign
> source-selection work separately from orchestration when agents are available.

**Goal:** A repeatable Windows launcher makes 20 distinct colorized vertical
clips per invocation, supports other positive counts, and resumes interrupted
orders without regenerating completed clips or downloading full sources.

**Architecture:** Keep historical single-source orders compatible. Extend the
existing controller with a production mode for counts above four. It processes
freshly discovered eligible sources until the requested number of verified
exports exists. The new launcher allows up to 20 useful moments per source;
the generic controller retains its four-moment per-source default.
Reuse the existing bounded downloader, local Whisper, renderer and verifier.

**Stack:** Python, SQLite job checkpoints, yt-dlp, Selenium/public discovery,
faster-whisper, FFmpeg, Windows CMD launchers, pytest.

## Constraints and acceptance evidence

- The new launcher defaults to 20, `colorized`, `fit`, 1080x1920 and original audio.
- Repeat runs start fresh searches; resume retains that order and settings.
- Count accepts any positive integer; source availability and computer resources
  remain finite. “Unlimited” means repeatable/configurable, not guaranteed views.
- Eligible recorded sources remain over 20 minutes, at most two hours, and within
  14 days. Missing metadata/captions tries another candidate.
- Rank actual transcript/replay moments; reject greetings, advertisements,
  incomplete answers and near duplicates in production mode. Label editorial
  selections when replay evidence is absent. Never claim guaranteed virality.
- Only selected windows plus three-second context may be acquired. No complete
  video/audio fallback, proxy bypass, credential collection or publishing.
- Persist each source, chosen interval, job and export; interrupted runs reuse
  completed work. Permanent source-access refusals can try another source;
  transient connectivity failures save and exit after the configured retry budget.
- Exclude source intervals and repeated takeaways reserved by prior orders.
- Deliver exactly the requested count before declaring the order ready. If
  sources run out, retain verified partial exports and report the shortfall.
- Keep all outputs in `clips/`, with an index and separate post captions.
- Verify orchestration with 20, larger counts, interruption, inaccessible sources,
  prior-run exclusions and manifest integrity. Verify the actual renderer on real
  media separately. Simulated acquisition is not evidence of a live YouTube run.
- No Git repository is present: keep a narrow code backup/diff, do not initialize
  Git or invent commits. Existing approved clips remain intact.

## 1. Selection and captions

Files: `clipping/planning.py`, `clipping/sections.py`,
`tests/clipping/test_planning.py`, `tests/clipping/test_sections.py`.

Interfaces:

```python
suggest_cuts(..., limit=3, min_gap=None, excluded_windows=None,
             require_standalone=False)
select_moments(source, count, target, *, strict=False, excluded=())
post_caption(excerpt)  # complete short text; no mid-sentence truncation
```

- [x] Add failing tests for dialogue-marker normalization, greetings/promotions,
  incomplete endings and excluded historical windows.
- [x] Allow one through 20 requested moments per source. Strict selection may
  return fewer useful moments and raises when there are none; preserve the
  historical three-of-four behavior outside strict selection.
- [x] Filter unsafe candidates before the top-pool limit, preserving replay and
  editorial evidence. Reject near-duplicate text as well as overlapping windows.
- [x] Generate a complete short post caption instead of truncating the first cue.
- [x] Run `python tests/clipping/run_tests.py tests/clipping/test_planning.py tests/clipping/test_sections.py -q --tb=short`.

- [x] Add regression coverage for the additional acknowledgement, outro and
  unanswered-setup windows discovered during actual twenty-export review.

## 2. Production orchestration and history

Files: new `clipping/production.py`, new `clipping/clip_history.py`,
`clipping/batch.py`, `clipping/orchestrator.py`, new
`tests/clipping/test_production.py`, `tests/clipping/test_batch.py`.

- [x] Add regression tests using the real controller/SQLite engine with bounded
  fixture acquisition, covering these behaviors:

```python
assert len(controller.run(connection_attempts=1)['result']['clips']) == 20
assert len({clip['job_id'] for clip in controller.state['result']['clips']}) == 20
assert controller.state['result']['full_video_downloaded'] is False
```

- [x] Add `clips_per_source=4` to saved configuration and CLI; validate positive
  target counts and a per-source count from one through 20.
- [x] Dispatch targets above four to `execute_production(controller, attempts,
  delay)`. Persist each entry's source, moment and metadata path so resume does
  not depend on the last source assigned to the controller.
- [x] Reuse batch job/render/delivery functions with per-entry source selection
  and idempotency keys that distinguish replacement source windows.
- [x] Serialize production orders with an OS lock. Read prior order reservations
  and exclude overlap or repeated takeaways on each source. Ignore the current
  order when reading history, so its own checkpoints can resume.
- [x] Continue across source-specific caption/section access refusals. Save on
  transient failures. Recheck completed outputs before presenting a ready result.
- [x] Report `insufficient_sources` with completed/requested counts when the fresh
  eligible pool cannot fill the target. Never duplicate clips to fill the count.
- [x] Write final manifests and a simple clip/post-caption index only when the
  exact requested number passes export verification.
- [x] Run production, batch, section and controller regressions together.

## 3. Repeatable caption quality and Windows entry point

Files: `clipping/media.py`, `clipping/_transcribe.py`,
`clipping/workflow.py`, associated transcription tests, new `make-20-clips.cmd`,
`clipping/README.md`, `AGENTS.md`.

- [x] Attach bounded timed source cues for independent caption coverage and
  text-agreement checks. Keep normal ASR unprompted: an actual media test showed
  that supplying full spoken text as a prompt can omit speech or cause loops.
  Reject poor windows and try replacements with a bounded per-source budget.
- [x] Test prompt validation/forwarding without introducing a new provider or
  changing historical requests that omit it.
- [x] Add a normal-terminal launcher equivalent to:

```powershell
.\.venv\Scripts\python.exe -m clipping.orchestrator --clips 20 --per-source 20 --caption-style colorized --framing fit --provider public
```

- [x] Support `make-20-clips.cmd --resume latest` and `--clips 40`. Print exact
  resume commands and open the delivery folder after a successful interactive run.
- [x] Document fresh-source, review, connection-recovery and no-virality-guarantee
  behavior. Record the newly approved colorized production workflow without
  altering historical job settings or the older studio template.

## 4. Completion audit

- [x] Run the appropriate full clipping suite and Ruff E4/E7/E9/F checks.
  Full non-Instagram suite: 311 passed. Final focused suite after additional
  source-selection fixes: 130 passed. Final Ruff check passed.
- [x] Execute the 20-output integration path, including an interruption/resume,
  with actual FFmpeg verification or independently verified real-media exports.
- [x] Attempt the normal production entry point in this environment; distinguish
  source connectivity failure from code failure and retain an exact saved order.
- [x] Inspect the output count, unique source/window identities, subtitle styles,
  manifests/indexes and compatibility with already completed orders.
- [x] Record evidence and unresolved live-network limits. Do not call simulated
  acquisition a completed fresh-source YouTube production run.


Final evidence: `research/twenty-clip-workflow-verification.md` and its JSON
record. Real cached-media run: twenty unique exports, both resume checks passed,
terminal exit 0. The fresh-source order remains network-blocked in this tool
process; this is not presented as a completed live YouTube batch.
