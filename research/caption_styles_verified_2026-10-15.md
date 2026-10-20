# Colored and professional captions

Restyled the real 39-second Dana White preview in job
`90f2f31f-89f6-48b7-a8be-6e111c49883f` from the saved original source and
transcript. This avoids burning a second subtitle layer over the previous clip.

Two variants are saved under the job's `captions-2026-10-15` directory:

- `colorized/clip.mp4`: bold uppercase white captions, current spoken word in lime.
- `pro/clip.mp4`: smaller bold white captions, important topic words in gold.

Each directory includes plain SRT and editable styled ASS files. The completed
job now points to the professional version and retains both in
`output.caption_variants`. Previous video files are retained. The local app was
stopped during verification; final delivery uses direct local file links.

The optional job payload field `caption_style` accepts `classic`, `colorized`
or `pro`. Omitting it preserves the existing classic behavior. The colorized
style uses saved word timings, holds the caption layout steady during color
changes, and does not invent word timing for segment-only subtitles. Transcript
control characters cannot inject ASS positioning or formatting commands.

Verification:

- 177 clipping tests passed, one Instagram UI test deselected; Instagram Python
  test files excluded because authentication remains deferred.
- Both actual exports are 39.041 seconds, 1080×1920 H.264/AAC.
- Both files decoded completely through FFmpeg with exit code zero.
- Encoded audio packet hashes exactly match the original reviewed preview.
- SRT bytes exactly match the original reviewed subtitles; speech and timing
  were not rewritten by styling.
- Five actual frames from each output inspected at 1, 3, 5.6, 15 and 35.5 seconds.
  Lime active words and gold emphasis render correctly, with readable captions
  below the speaker's face where the speaker is visible. Framing is unchanged.

Evidence: `.workflow-tests/caption-style-review-2026-10-15/`.
Render script: `.workflow-tests/style_reviewed_captions.py`.

Implementation references: [ASS override tags](https://aegisub.org/docs/latest/ass_tags/)
and [FFmpeg subtitles filter](https://ffmpeg.org/ffmpeg-filters.html#subtitles-1).
