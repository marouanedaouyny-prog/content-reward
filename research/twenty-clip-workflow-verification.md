# Twenty-clip workflow verification — October 18, 2026

`make-20-clips.cmd` starts a new public-discovery order with 20 requested clips,
up to 20 moments per source, approved colorized captions and full-image fit
framing. `--clips 40` changes the target; `--resume latest` preserves the saved
order. The generic four-clip studio launcher and historical orders keep their
settings. Publishing remains disabled.

Production uses strict transcript/replay selection, prior-order interval and
text exclusions, bounded media windows, per-source checkpoints and source/window
cache identities. Source-access refusals can move to another source; transient
failures save progress. Poor caption windows are replaced, with a maximum of
three caption failures per source. Insufficient sources retain partial exports
and report the shortfall instead of duplicating clips.

## Verification

- Full non-Instagram clipping suite: **311 passed** in 176.72 seconds.
- Final focused planning, sections, caption coverage, production and export
  review suite after the last selection changes: **130 passed** in 76.15 seconds.
- Ruff E4/E7/E9/F checks passed for changed Python modules and tests.
- Actual CMD launcher: help exited 0; invalid zero count exited 2 without
  pretending that an order or clip index had been created.
- [The real-media audit](../.workflow-tests/twenty-local-ba999acddf9a4aebafd4c48688aebffe/audit.json)
  exited 0 after **20 unique MP4s, jobs and bounded acquisitions**. It used
  existing cached footage, real local Whisper, FFmpeg and the shared verifier.
  No new full-source download occurred. It deliberately interrupted after nine
  exports, resumed without changing them, and then resumed the completed order
  with transcription, rendering and acquisition forbidden. All rechecks passed.
- Actual exports were 15.17–46.96 seconds at 1080×1920, H.264/AAC. Minimum
  expected-speech caption coverage was 78.14%; minimum source-token recall was
  79.45%. Three five-second audio comparisons with the original cached source
  had correlations above 0.999. Actual frames from clips 1, 9, 10, 13, 15 and 20
  were inspected: source faces remain visible and captions use at most two lines.
- The approved `clips/50-Cent-Colorized.mp4` remains unchanged, SHA-256
  `615f000724dace84851f8f5dd30c11f2bb7e9f3ebee0fa33c5f81ab20233571d`.

## Bugs found through real media

Supplying full spoken text as a Whisper prompt caused missing speech and
repeated hallucinations. The earlier six-export test was stopped and recorded
as negative evidence. Production now uses unprompted ASR and independently
checks caption timing coverage and source-text agreement before saving a
transcript and again at final export review. Matching a faulty ASR transcript
and SRT is insufficient.

Review of the initial 20 selections found acknowledgements, an outro,
unanswered host setups and a channel subscription promotion. Added regression
tests reject those detected cases while retaining complete question/answer
windows and ordinary discussion of subscriptions. The updated selector still
finds 20 candidates in the cached Dana transcript at targets 15 and 35, and
the cached 50 Cent public captions at target 35. Those are metadata checks,
not fresh-source acquisition or human approval of every selection.

The real 20-export fixture retained its earlier preallocated windows. It proves
processing and recovery; its editorial flags remain unresolved and its files
stay in the private test directory. They are not a new user batch.

## Live-source limit and user entry point

A real production attempt saved order
`b1ab89fa-c4ad-4585-99d0-5b1fcd971ddd` with
`connection_unavailable / youtube_connection_unavailable`, before discovery,
with zero clips. No proxy, TLS or browser restriction was bypassed. Resume
that order from the normal PowerShell terminal, where source access previously
worked:

```powershell
Set-Location -LiteralPath 'C:\Users\hp\Desktop\New folder\content rewerad'
.\make-20-clips.cmd --resume b1ab89fa-c4ad-4585-99d0-5b1fcd971ddd
```

For another new run, use `.\make-20-clips.cmd`. Completed batches write
`clips/LATEST-CLIPS.txt`; shortfalls write an order-specific partial index.
Caption agreement is a gross-error check, not perfect ASR or semantic review.
Selection is editorial when replay data is absent. Available eligible sources,
access and resources remain finite; virality and follower growth are not
guaranteed. [Machine-readable evidence](twenty-clip-workflow-verification.json)
records the counts, limits and saved order.
