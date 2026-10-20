# YouTube clipping orchestrator

The requested controller is implemented in `clipping/orchestrator.py`, with
Windows entry point `run-youtube-clipping.cmd`. It uses the existing research
and media workers, rather than the legacy orchestration stack.

## Behavior

- An ordinary invocation creates a new order and fresh source search.
- `--resume latest` or `--resume <uuid>` continues its saved research/job.
- Each order has an isolated workflow DB and OS lock; media/model storage is shared.
- Temporary connections receive bounded exponential retries. A refused source
  can fall back to another ranked candidate, up to three source candidates.
- Completed downloads and speech transcripts remain checkpoints. Exclusive
  resume recovers processing/research left running after a process crash.
- Setup, connection, transcription, source-access, interruption and export
  failures have explicit statuses. Provider exception text is redacted at the
  controller boundary. Proxy and TLS settings are preserved.
- Captions are configurable. Optional full-image framing retains speakers over
  a blurred background. Five actual output frames accompany the result.
- Export review checks source/clip hashes, H.264/AAC, dimensions, duration,
  subtitle content/timing, short blocks, full decode and audible audio.
- Result metadata and `post-caption.txt` accompany the MP4. Source headline and
  creator credit are used when available. No posting or Instagram connection occurs.

Selection now considers useful title-topic terms, independent openings and
completed answers. Common pronouns/auxiliary verbs are excluded from title
matching; filler and promotions are penalized. Replay data takes precedence when
available. Editorial scores remain heuristics, not verified popularity forecasts.

## Verification

- Clipping regression suite: **203 passed, 1 deselected**, 71.33 seconds.
  Instagram Python test files were excluded; the deselected case is Instagram UI.
- Focused controller suite after the final retry-counter fix: **14 passed**.
- Ruff passed for the new controller/review modules and their test files.
  A broader lint run still reports style warnings in existing modules.
- Native Python CLI help and saved-status commands executed successfully.
- Cached real-source check rendered an 8-second 1080×1920 H.264/AAC export with
  colored captions and full-image framing. Full decode and audio checks passed;
  audio RMS was −18.27 dB. Sample frames showed the full speaker and readable captions.
  Evidence: `.workflow-tests/orchestrator-native-e2973a8114934db6aee394b5f9658a4c/`.
- The final verifier also checked the existing real 39-second export, including
  its source hash, subtitle text/timing and complete decode. Audio RMS −18.43 dB;
  no black-frame markers. Evidence: `.workflow-tests/orchestrator-real-export-review/`.
- A cached-transcript planning check selected the central working-from-home
  passage at 756.51 seconds, instead of a generic conversational opening.
  This check was not a fresh YouTube order.

## Fresh native execution

Selenium order `90a197ab-4df8-4597-bf05-5f9c0c1ed353` stopped at browser setup.
Chrome raised `SessionNotCreatedException` in this tool session. The browser
helper now distinguishes this condition from connection and permission failures.

A separate fresh public-search order,
`e0dfa827-af54-4892-9166-fa9f42a87d2e`, encountered the tool session's unavailable
YouTube connection. Its bounded retries and persisted state were exercised.
After adding fast connection preflight, resuming the same order reported
`connection_unavailable` at `source_connectivity` in about 5.6 seconds, retaining
the same research run. No source job or new clip was fabricated.

Resume this saved order in the user's normal project terminal:

```powershell
.\run-youtube-clipping.cmd --resume latest
```

The normal terminal previously completed live YouTube discovery and download,
but a fresh complete run of this new controller there is still unverified.
`ready_for_review` reports mechanical export success. Framing, meaning, caption
taste, ASR accuracy and whether a passage is actually famous still need review.

Official implementation reference:
[FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html).
