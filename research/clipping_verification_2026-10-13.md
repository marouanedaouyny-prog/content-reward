# Clipping-only verification

The user deferred Instagram setup and requested testing of the clipping
section. No Instagram setup, token import or posting was performed during
this verification. No production code changes were required.

The clipping suite passed **137 tests** in 39.56 seconds. Instagram account,
OAuth, tunnel and token tests were excluded from this run:

    python tests/clipping/run_tests.py tests/clipping --ignore=tests/clipping/test_instagram.py --ignore=tests/clipping/test_instagram_oauth.py --ignore=tests/clipping/test_instagram_tunnel.py --ignore=tests/clipping/test_instagram_token.py -q --tb=short

Coverage includes intake validation, uploads, queue transitions, review gates,
automatic clip planning, subtitle timing, caption grouping, rendering, source
retry/resume, interruption/process cleanup and JavaScript interaction checks.
The UI interaction checks use a simulated DOM; they are not real-browser
visual verification.

A separate native Python 3.11 HTTP check exercised the running workspace on
127.0.0.1:8000. It extracted a short input from an existing local project
video and uploaded it through the actual multipart endpoint. The local input
was used to avoid the agent's blocked source-download network. The initial
automatic transcription attempt returned no detected speech and correctly
paused the job at `awaiting_transcript`. Authored captions clearly labeled as
test text were supplied through the SRT handoff, and the same saved job
resumed to a completed private preview. These captions are not a transcript
of the original audio. This run did not establish speech recognition accuracy.

Automatic clip selection chose a 14-second window for the requested
12-second target, ending at the supplied cue boundary. The exported MP4
passed every application quality check: **1080×1920**, **H.264**, **AAC**,
expected selected duration and nonempty output. MP4, SRT, transcript and
preparation-package downloads worked. The package remained `not_submitted`.
A complete FFmpeg decode of both exported video and audio passed. A sampled
caption frame was inspected and showed readable two-line text inside the
portrait frame; this is a sample-frame check, not a full crop/content review.

A second five-second practice job verified rejection of the wrong review
step, campaign approval, rendering with three authored SRT cues, clip
approval and completion. A separate pending test job was cancelled
successfully. Completed states were read back from the live API. Health
responses during processing took at most 0.281 seconds in this run. No real
publication or reward submission was recorded.

The real local-video test job is
`0bea5321-4d33-4647-a536-21c2d342f5a5`. The practice job is
`73a22ee6-a295-47b6-9303-77195fc4f1f7`.
The [test clip](http://127.0.0.1:8000/api/v1/jobs/0bea5321-4d33-4647-a536-21c2d342f5a5/artifacts/clip)
is available from the running workspace. Native evidence is saved locally
in `.workflow-tests/clipping-native-verification-2026-10-13.json`; its video,
subtitle and frame paths are recorded there.

The live Playwright test could not start: Windows returned `WinError 5`
while creating the process communication pipe. No existing Chrome profile
was accessed, and browser layout or playback behavior was not verified.
Fresh online source acquisition also remains unverified from this restricted
network environment. The tested upload/SRT/export path works independently
of an Instagram connection.
