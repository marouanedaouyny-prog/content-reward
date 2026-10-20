# Orchestrator tasks

- [x] Implement saved orders, resume, locking and structured error handling.
- [x] Connect discovery, source selection and the existing clipping worker.
- [x] Add selection improvements and actual export verification.
- [x] Add Windows launcher and usage documentation.
- [x] Run failure/recovery tests and the clipping regression suite.
- [x] Execute a fresh native order and report the real result or saved blocker.
# Current batch order

- [x] Create the visible `clips/` folder. Earlier delivered files are missing at
  their recorded paths; do not substitute unrelated demo/test exports.
- [x] Add caption-first source inspection and bounded partial downloads.
- [x] Add distinct batch planning, checkpoints, resume and flat delivery.
- [x] Add the revised caption style and verify actual rendered output.
- [x] Update workflow documentation and run focused/regression checks.
- [x] Start fresh order `482a4a57-919d-4c69-938c-60c918255323` and report the
  actual `browser_session_not_created` blocker. No fresh batch clips exist yet.
- [ ] Complete that fresh order in a working normal-terminal browser session,
  review its actual exports and deliver three or four new clips.

- [x] Add tested same-order public discovery fallback when Chrome cannot start,
  preserve its runtime choice on resume, and provide a double-click resume file.
  Native resume reached the fallback but then reported
  `youtube_connection_unavailable`; the fresh batch remains at zero clips.

Previous exports were recreated from the cached real source in `clips/`, with
explicit previous/preview filenames. They do not satisfy the fresh batch.

# Approved studio template

- [x] Apply the approved studio/fit defaults consistently to all entry points.
- [x] Record exact settings and a reusable agent roadmap; archive old palette samples.
- [x] Research primary-source guidance for better hooks and clip selection.
- [x] Improve filler/gap handling, context flags, promotion checks and near-duplicate batch filtering.
- [x] Verify actual default output and regression checks (226 passed); live order
  remains at zero clips with `youtube_connection_unavailable`.

# October 17 varied-style order

- [x] Save a per-order caption style sequence and use each clip's saved style
  for rendering, delivery filenames, metadata and resume. Default stays studio.
- [x] Add `start-varied-clips.cmd` for four distinct highlights with studio,
  pro, colorized and classic subtitles.
- [x] Verify focused style/resume checks (25 passed), Ruff, and the clipping
  regression suite excluding Instagram checks (228 passed, 1 deselected).
- [x] Start fresh order `67f69696-94b1-4649-b2cf-725647f88100`. Selenium could
  not start; the public fallback reported `youtube_connection_unavailable`.
- [x] Complete the amended order after the user's October 18 approval to reuse
  the cached Dana White interview. Four distinct new studio/pro/colorized/classic
  clips, spoken subtitle files and post captions are verified in `clips/`.
  Their windows exclude the earlier preview. The checked ZIP is
  `clips/67f69696-four-clips.zip`; selection is editorial, not replay-verified.

Social setup remains separate: the user will enter each platform's credentials
locally, step by step. Instagram's local status is `not_configured`; its hidden
prompt is `connect-instagram-token.ps1`. Publishing remains disabled.

