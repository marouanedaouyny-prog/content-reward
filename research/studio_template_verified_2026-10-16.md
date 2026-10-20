# Approved studio template: implementation and verification

The user explicitly selected `clips/caption-preview-studio.mp4` as the default
visual template. The exact reproduction instructions and agent workflow are
saved in [the roadmap](studio_template_roadmap.md) and linked from root AGENTS.md.
The approved video's numeric appearance settings were preserved.

## Changes

- Shared `studio` caption and `fit` framing defaults are in `clipping/template.py`.
  Controller configuration, CLI settings, request validation and implicit media
  rendering use them. Explicit style choices remain supported. Default resolution
  does not insert fields into historical normalized requests or alter their hashes.
- Matching vertical exports record `render_template=studio-v1`. Batch result
  records retain framing, selection-quality flags and transcript-diversity notes.
- The two older lime/gold palette samples and their subtitle/post-caption files
  were moved to `storage/clipping/style-samples/previous-palettes/`. Source and
  destination paths were verified within the workspace before moving files.
  `clips/` keeps the approved preview and will receive new finished batches.
- Planner changes penalize filler prefixes, referential questions without a
  named source topic, and gaps between transcript cues. Promotion checks now
  recognize first-order discounts and spoken `.com slash` offers, as well as
  explicit sponsor/promo wording. Batch selection excludes detected promotions.
- Batch planning considers up to 20 separate windows and filters near-duplicate
  normalized transcripts before accepting three or four. Similarity thresholds
  and scores are editorial heuristics; semantic takeaway diversity, physical
  silence, complete context and ASR accuracy still need actual-clip review.

## Evidence

- **226 passed, 1 deselected**, 91.21 seconds: the full clipping regression suite
  excluding Instagram test files and the Instagram UI case.
- Ruff passed for the shared defaults, controller/batch/section modules and new
  test files. Undefined-name/syntax checks also passed across all changed Python
  modules and tests. This is not a claim that all legacy style warnings are fixed.
- A native FFmpeg render with omitted settings matched an explicit studio/fit
  render: identical SRT, identical ASS and identical decoded video frame hashes.
  This used a short synthetic test fixture solely for verification; it was not
  delivered as user content or a fresh source result.
- Regression cases cover filler-led versus direct openings, long cue gaps,
  discounts without the word "sponsor", referential questions, an advertisement
  with a high replay peak and repeated takeaways at separate source timestamps.
- A check against the cached real transcript exposed a coffee promotion that
  matched business/home keywords. The expanded promotion check removed it from
  the batch. The cached check used controlled topic terms and is explicitly
  labeled `fresh_search_result=false` in
  `.workflow-tests/studio-template-selection-review.json`.

Primary-source research is saved in
[the guidance note](clipping_quality_guidance_2026-10-16.md). It cites official
YouTube guidance and tool documentation, separating those sources from local
editorial rules. No score or palette guarantees virality.

The live saved order `482a4a57-919d-4c69-938c-60c918255323` remains at zero new
clips with `youtube_connection_unavailable`. Its studio/fit settings already
match the approved defaults. No new video search or batch export was claimed
as successful in this template-update task.
