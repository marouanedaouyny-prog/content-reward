# Real YouTube clip verified

The user launched `start-youtube-clipping.cmd` in their normal terminal. The
running app on port 8000 successfully used Selenium discovery, downloaded a
long source, transcribed its speech, and rendered a real captioned preview.
Instagram remains deferred.

- Research run: `0e12d1b9-b8b8-48de-a65d-e5378680c529`, completed.
- Provider: `selenium_browser`; six niches searched, five eligible sources found.
- Selected source: `Q-DFC0AnbY4`, Dana White interview, The Diary Of A CEO.
- Saved source snapshot: 2,579,966 views; duration 5,291 seconds.
- Preview job: `90f2f31f-89f6-48b7-a8be-6e111c49883f`, completed.
- Source speech transcript: `faster_whisper:en`, 1,101 segments with word timing.
- YouTube supplied no replay heatmap. No most-replayed or viral claim is verified.

## Review and fixes

The original automatic preview began with "You know what I mean?". Some ASR
words had zero duration; the caption builder treated an entire affected sentence
as one cue, which produced a six-line block covering the speaker's face.

The caption builder now keeps zero-duration words with a timed neighbor, retains
the transcript text, and excludes words outside the cut before grouping. Regression
tests cover readable blocks and text preservation. The planner no longer rewards
generic conversational filler as an opening question. Portrait captions use a
smaller font and lower placement.

The delivered cut was selected through editorial review: source 12:36.51–13:15.53,
keeping the working-from-home claim and its explanation together. This editorial
revision is explicitly labeled `editorial_review`; it is not an automatic
heatmap-based result. Original files remain available in the job directory.

Delivered files are under:
`storage/clipping/jobs/90f2f31f-89f6-48b7-a8be-6e111c49883f/reviewed/`.
The completed job's clip, subtitle, caption and package paths now refer to this
reviewed version. The existing running app serves it without a restart. Python
code fixes take effect in its worker after the next normal launcher restart.

Post caption:
> Can you build a successful business from home? Dana White’s take. #Business #Entrepreneurship #DanaWhite

## Verification

- 169 clipping tests passed; one Instagram UI test deselected; Instagram Python
  test files excluded because authentication is outside the current request.
- Real output: 39.041 seconds, 1080×1920, H.264 video, AAC stereo audio.
- Full FFmpeg decode succeeded; no detected black intervals of 0.25 seconds or longer.
- Audio mean level −18.4 dB, peak −1.6 dB; output is not silent.
- Five actual output frames inspected at 1, 8, 18, 30 and 38 seconds; sampled
  captions are readable and avoid covering the speaker's face.
- Live artifact endpoint returned HTTP 206 for a byte range, `video/mp4`, with
  a valid MP4 header. API reports the reviewed paths and caption.
- No claim of browser playback or word-for-word subtitle accuracy: browser review
  tools are unavailable, and the speech transcript is automatic ASR.

Review script: `.workflow-tests/review_one_youtube_clip.py`. Frame evidence and
the original output snapshot: `.workflow-tests/real-clip-review-90f2f31f/`.
