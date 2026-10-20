# YouTube clipping orchestrator

User request: one runnable controller performs the standing search-to-clip
workflow and handles connection exceptions without losing progress.

## Acceptance criteria

1. One command creates a fresh order, searches real long-video candidates,
   selects an eligible source, transcribes it, chooses a source moment and
   renders one vertical clip with configurable colored captions.
2. A saved order resumes after a connection failure or interruption without
   duplicating completed downloads/transcripts. Retry budgets are bounded;
   setup problems, missing speech and temporary connections have distinct
   statuses. No old clip is reported as a new search result.
3. Export verification checks the actual file, subtitle coverage and timing,
   full decode and audio. Source/selection evidence and review frames accompany
   the result. Automated checks are distinguished from subjective human review.

## Implementation

- Reuse `TrendResearchAgent`, `ClippingWorkflow` and existing media functions.
- Store each order's manifest and isolated workflow database in
  `storage/clipping/orders/<uuid>`. Share the existing media/model storage.
- Hold an OS file lock for each running order. Write JSON state atomically.
- Make dependency checks local; browser readiness runs only when discovery is
  needed. Preserve inherited proxies. Redact provider exceptions.
- Use bounded exponential connection retries with `--resume latest` and
  explicit connection/setup/transcript/quality/interruption exit statuses.
- Improve moment scoring for topic relevance, independent openings and complete
  payoffs; retain the explicit replay-versus-editorial distinction.
- Add optional source-preserving framing for exports where portrait cropping
  would cut speakers; keep existing workflow defaults compatible.
- Add native Python CLI and Windows one-command launcher; no Instagram setup,
  publication, external service integration or new cloud dependency.

## Verification

Focused failure/restart/idempotency tests, then the clipping test suite. Exercise
the native controller against the actual environment and report its true status.
Verify media review with a clearly labeled cached-source check if live search
is unavailable. A cached-source check is never delivered as a fresh order.
# Current order: four highlights without downloading the full video

The user now wants one visible `clips/` folder and a fresh search that produces
three or four distinct highlights from the same popular long video, with revised
colored captions. This explicit batch request overrides the usual single clip.

1. Copy previously delivered exports into `clips/`, labeled as previous clips.
2. Fetch public source metadata and English subtitles only. Rank complete,
   independent transcript windows with replay evidence when available. Select
   four non-overlapping moments (three is acceptable); never pad with duplicates.
3. Download only the chosen time ranges with yt-dlp and FFmpeg. Require a
   bounded section duration and never fall back to a full media download.
4. Transcribe each small section for actual speech and word timing, render 9:16
   with revised selective colored emphasis, and run the existing export checks.
5. Save checkpointed batch results and copy verified MP4s and post captions into
   the same flat `clips/` folder. Resume preserves the source and finished clips.
6. Verify caption parsing, distinct selection, range commands, offset handling,
   resume/failure behavior and actual local rendering. Attempt the fresh live
   order and report any real connection blocker without substituting old clips.

Use the existing order controller, discovery, media processing and verifier.
Keep historical saved single-clip orders resumable. Missing usable subtitles
must produce an explicit source failure and try another ranked source; it must
not cause a full-video or full-audio download. Preserve proxy/TLS settings and
redact provider exception details.

# Approved studio template and better selections

The user explicitly approved `clips/caption-preview-studio.mp4`. Preserve its
appearance and use studio captions plus full-image blurred-background framing
as the defaults across controller, API preview and media rendering. Centralize
the defaults without rewriting historical job fingerprints. Keep explicit
alternative styles available only when requested.

Document the exact reference settings and the repeatable agent workflow in
AGENTS.md and a linked roadmap. Archive the two old alternative-style samples
inside workspace storage; they are the same footage, not distinct highlights.

Ground selection improvements in the official-source research note. Penalize
filler-led introductions and long speech gaps, expose the reasons, and avoid
near-duplicate takeaways across a batch in addition to overlapping time windows.
Keep the original speech and completed thoughts. Verify real default rendering
against the explicit approved template and run relevant regression checks.

# October 17 goal: fresh clips with different subtitle styles

Start a fresh source search and produce the normal three/four distinct partial-
download highlights, rotating studio/pro/colorized/classic styles for this order.
Keep studio/fit as the permanent defaults and preserve review-only publishing.
Add an explicit saved per-batch style sequence, use each clip's actual saved
style during processing/delivery/resume, test it, then execute the fresh order.
The required deliverable remains new real-source MP4s and post captions; tests,
old previews and a saved blocked order alone do not complete this goal.

