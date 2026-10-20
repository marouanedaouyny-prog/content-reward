# Agent roadmap: approved studio clips

## October 18 production override

The user subsequently approved `clips/50-Cent-Colorized.mp4` and requested a
repeatable 20-clip workflow. `make-20-clips.cmd` explicitly uses `colorized`
captions with lime emphasis and the same `fit` full-image framing. It allows
up to 20 distinct useful moments per source and additional sources as needed.
This newer choice overrides the studio appearance/count for that launcher;
the generic four-clip launcher and saved older orders retain their settings.
The selection, bounded-download, actual-export review and honest provenance
requirements below still apply. The approved sample establishes appearance,
not guaranteed virality or approval of automatically selected future moments.

## Original studio reference

The user approved **`clips/caption-preview-studio.mp4`** on October 16, 2026.
Use this file as the visual reference for all future clipping work. Approval
concerns the appearance; it does not certify the old sample's transcription,
opening, source selection or popularity. The sample is earlier footage.

## Exact visual template: studio-v1

- 1080 × 1920 vertical MP4, original source speech and audio.
- `caption_style=studio`, `framing_mode=fit`. Shared defaults are in
  `clipping/template.py`; appearance is implemented in `caption_styles.py` and
  `media.py`. Other entry points must use the shared defaults when omitted.
- Fit the entire source image in the center. Fill the vertical canvas with a
  scaled/cropped copy of that source, blurred with `boxblur=24:2` and darkened
  with `brightness=-0.12`. Keep the full speaker visible across shot changes.
- Arial bold, 68 px at 1080 × 1920, sentence case, white `#FFFFFF`.
  Selective cyan `#55DDF6` emphasis follows actual word timing. Highlight at
  most one content word per short phrase; preserve the reference's restrained
  emphasis instead of adding bouncing text, animated zooms or all-word karaoke.
- Bottom-center subtitles; horizontal margins 97 px (9%), bottom margin 346 px
  (18%), dark outline thickness 3 and shadow 2. Keep text outside the source
  face area and away from screen edges.
- Short phrases, at most two lines; word-timed grouping normally caps at six
  words, 32 characters and three seconds, and breaks at speech gaps. Never
  invent word timestamps. Review punctuation, transcription and line breaks.
- H.264, CRF 23, fast preset, AAC 128 kb/s, MP4 fast-start. No added voiceover,
  background music, stickers, logos or color-palette changes without a request.
- Keep spoken subtitles in SRT/ASS and the separate post caption in its own
  `-caption.txt`. Do not substitute a post headline for spoken subtitles.

## Repeatable workflow

1. **Identify the order.** A new clipping request starts a fresh source search.
   A restyle keeps its source/window/transcript. Resume an interrupted order
   rather than creating another one. Default to four clips; accept three strong
   distinct moments instead of manufacturing a fourth weak or duplicate one.
2. **Compare real long-video candidates.** Use the configured discovery path,
   including Selenium when available and the tested public fallback when Chrome
   cannot start. Compare topic relevance, publication date, duration and observed
   views/growth. Current eligibility is recorded sources over 20 minutes and up
   to two hours, published within 14 days. Record the actual sample and dates;
   neither a source-wide view count nor views/hour proves a moment is famous.
3. **Read before downloading.** Fetch safe metadata, public English captions
   and replay bins. Inspect the actual transcript across the long source. Rank
   candidate windows by a concrete immediate opening, clear point, complete
   payoff, source relevance and available replay evidence. Read surrounding
   context to catch missing referents, punchlines and unfinished answers.
4. **Choose different takeaways.** Check more candidates than the final count.
   Avoid generic filler, promotional passages, long dead pauses and openings
   that depend on unseen context. Preserve complete thoughts. Require separate
   source intervals and inspect normalized transcript overlap so one repeated
   idea cannot fill several batch slots. Write an opening/point/ending rationale
   for each selected clip. Automated similarity checks are only a first pass.
5. **Request only selected media.** Download each chosen range with three
   seconds of context on both sides, using bounded section downloads. Never
   fall back to downloading the full video or full audio. If captions or partial
   source access are unusable, try another eligible source or report the limit.
6. **Transcribe and render.** Run local ASR on each small section for actual
   speech and word timing. Apply studio-v1 without changing its approved look.
   Map the original-source timestamps to the local section correctly. Preserve
   checkpoints for source sections, transcripts, jobs and verified exports.
7. **Review the actual MP4.** Check opening and payoff, ending, shot changes,
   speaker visibility, original audio, caption words, word timing and readable
   line breaks. Confirm full decode, format, duration, hashes and audible audio.
   Saved frames support inspection; they do not prove semantic or ASR accuracy.
   Fix visible problems before presenting an export as finished.
8. **Deliver one folder.** Put verified MP4s, SRT/ASS and post captions into
   `clips/` with order/source/clip filenames. Give the current order's actual
   outputs concisely. Label editorial selections when replay data is absent.
   Never pass off the approved old preview as a new search result. Keep Instagram
   and publishing deferred until requested.

## Evidence and limits

The implementation penalizes filler-led openings, referential questions and
speech gaps, selects a larger pool, excludes detected promotional passages,
and excludes near-duplicate normalized transcripts in a batch.
These are project editorial heuristics. They do not establish semantic topic
diversity, private retention access, guaranteed virality or perfect ASR.
Speech coverage and gap estimates use transcript cue intervals, not direct
audio-silence measurements; pauses inside a cue still need actual-clip review.
Replay spikes can reflect confusing passages as well as useful rewatching.

See [primary-source research](clipping_quality_guidance_2026-10-16.md) for the
official YouTube and yt-dlp references. The approved preview and the native
default-vs-explicit render check establish appearance, not fresh source access.
