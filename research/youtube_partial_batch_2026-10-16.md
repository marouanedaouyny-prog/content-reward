# Four highlights using partial downloads

The October 16 request changes new controller invocations to four clips from
one freshly searched long video. Three clips are accepted when only three
distinct usable windows fit. All deliveries go into the project `clips/` folder.
Instagram and publishing remain deferred.

## Implementation

- `clipping/sections.py` fetches only safe source metadata and public English
  JSON3 captions with `--skip-download`. It normalizes overlapping public cues,
  joins unfinished fragments and ranks the whole textual transcript, with replay
  data when available. The final subtitles come from actual local Whisper ASR
  on each selected small media section, not from invented word timings.
- Batch suggestions have a strict three-second gap and no overlapping source
  intervals. Four is the target; fewer than three rejects that candidate.
- Only selected windows plus three seconds of context on each side are requested
  using `--download-sections` and FFmpeg. Seekable HTTPS formats are required.
  There is no full-video/full-audio fallback. Wrong section durations, missing
  streams and oversized outputs fail validation. Keyframe/index/network overhead
  may transfer additional bytes; live network transfer savings are unverified.
- `clipping/batch.py` retains per-clip jobs, small source sections and ASR
  checkpoints. A temporary connection failure resumes the same source and does
  not render completed clips again. Finished batches recheck their original
  exports before presenting a ready result; failed checks invalidate old result
  manifests. Verified MP4/SRT/ASS files and separate post captions are copied
  into a flat delivery folder with order/source/clip names.
- `studio` captions keep sentence case with short white phrases, selective
  cyan content-word emphasis and original word timing. Existing palettes remain
  configurable; the user has not approved any permanent visual standard.
- Native CLI execution exposed duplicate module exception classes under
  `python -m`. The entry point now uses the canonical controller module so
  typed setup/connection errors receive their intended statuses. A subprocess
  regression test covers that exact failure.

## Verification

- Clipping regression suite: **215 passed, 1 deselected**, 51.25 seconds.
  Instagram test files and the Instagram UI case were excluded.
- Ruff passes for the controller, new section/batch modules and new tests.
- Installed yt-dlp argument parsing confirms subtitle-only extraction is not
  simulated and section requests enable FFmpeg and forced cut keyframes.
  Its installed FFmpeg downloader inserts input `-ss` and bounded `-t` for
  section starts/ends.
- Three actual 39.041016-second H.264/AAC exports were rendered from the
  previously verified real source, with full-image framing and the studio,
  pro and colorized styles. All mechanical checks passed, including full decode,
  source/clip hashes, captions, dimensions and audible audio (RMS -18.43 dB).
  Studio opening/middle/ending frames were visually inspected. These are
  previous-source samples, not outputs of the new search order. Word-for-word
  ASR accuracy and subjective caption taste remain unverified.
- Sample proof:
  `.workflow-tests/orchestrator-native-e2973a8114934db6aee394b5f9658a4c/media/batch-caption-review/verification.json`.
  Earlier recorded deliverable files had disappeared; the cached real source
  and transcript remained, allowing the explicitly labeled samples to be rebuilt.

## Fresh order status

New order `482a4a57-919d-4c69-938c-60c918255323` saved four partial-download
clips, `studio` captions, Selenium in `C:\Python314\python.exe`, full-image
framing and the shared `clips/` delivery folder. Its native start and corrected
resume reported `setup_required`, reason `browser_session_not_created`, before
discovery. No fresh source was selected and no new batch clip was created.

The user's normal terminal must resume that exact saved order to exercise the
live search, source captions and partial YouTube download. This tool session
cannot start Chrome; inherited proxy and TLS settings are preserved.

```powershell
.\run-youtube-clipping.cmd --resume 482a4a57-919d-4c69-938c-60c918255323
```

Official reference: [yt-dlp download options](https://github.com/yt-dlp/yt-dlp#download-options).

## Continuation: browser fallback and saved resume

The browser startup diagnostic identified a profile-directory creation failure.
A temporary inherited-permission profile removed that first failure but Chrome
then crashed before creating DevToolsActivePort. No experimental browser or
profile-permission changes were retained, and no browser sandbox/proxy controls
were disabled.

Batch discovery now falls back to the existing public/API discovery path for
specific Chrome/Selenium startup failures. It saves `discovery_provider=public`
in the same order, resets an incompatible pre-selection discovery scan, and
uses that runtime provider during resume preflight. Proxy-configuration errors
remain explicit and do not trigger fallback. Existing selected moments and
completed clip jobs keep their chosen source.

Native resume exercised the fallback, then reported
`youtube_connection_unavailable`. A later resume started directly with public
discovery, without another Chrome attempt, and reached the same connection
blocker in about 2.6 seconds. The fresh order is still at **0 of 4 clips**.
The three files in `clips/` remain labeled previous-source caption samples.

The final clipping regression suite passed **218 tests, 1 deselected**, in
51.45 seconds. Ruff passed for the changed batch module and tests. New tests
cover same-order fallback, saved public-provider preflight on resume and
preserving non-fallback setup errors.

`resume-youtube-clipping.cmd` lets the user double-click to resume the latest
saved order in their normal terminal. This does not start a replacement order.
