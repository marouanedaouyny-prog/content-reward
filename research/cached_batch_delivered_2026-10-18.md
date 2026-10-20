# Four new clips from the user-approved cached interview

Order: `67f69696-94b1-4649-b2cf-725647f88100`.

The fresh source connection was rechecked and remained unavailable. Web search
found recent alternatives, but their media could not be acquired here. The
user explicitly chose **"Use the cached interview for four new clips"** on
October 18. This amended the source constraint for this order; it does not
replace fresh search for future orders.

The cached source is the real Dana White / The Diary Of A CEO interview
`Q-DFC0AnbY4`, 5,291.479 seconds long. Existing source and word-timed ASR data
were verified before selecting four new, separate takeaways. Only small local
source windows were extracted; no new full-video download was made. None of
these windows overlaps the earlier 756.51–795.53-second caption preview.

| New clip | Style | Actual duration | Original-source window |
| --- | --- | --- | --- |
| Protect your people | studio, cyan emphasis | 48.833 s | 1465.15–1513.95 |
| A plan needs action | pro, gold emphasis | 42.542 s | 2931.08–2973.62 |
| The cost of never trying | colorized, lime word tracking | 19.833 s | 4327.26–4347.07 |
| What success feels like | classic, plain white | 21.249 s | 2978.60–2999.83 |

Each is a 1080 × 1920 H.264/AAC MP4 using the full original image over a
blurred background. Speech remains original. All four MP4s, SRT files, three
ASS files and separate post captions are in the flat `clips/` folder. The four
MP4s have distinct checksums and differ from the previous preview.

## Actual export review

The controller completed all four jobs. Each final export passed source and
clip checksum, dimensions, codecs, duration, caption text/timing, two-line
caption limits, full decode and audible-audio checks. Five frames from each
actual export were inspected for opening, ending, shot changes, framing and
readability; additional actual frames verified cyan/gold/lime emphasis and
corrected captions. The source image stays visible across speaker changes.

Review caught and corrected ASR errors including "bargain" and "vision board",
the GPS phrase and a context-specific "No". The earlier unrelated "you know"
interjection was preserved. "Vision board" now appears together as a readable
phrase. Two endpoints were shortened by 0.09 seconds to exclude fragments of
the following sentence. Existing word timing units were retained rather than
inventing individual word timestamps.

Decoded audio was compared against the corresponding original source windows.
Normalized waveform correlations were 0.999304, 0.999431, 0.999443 and 0.999421,
with no detected alignment offset. This supports preservation of the source
audio; it does not establish perfect ASR word accuracy.

Selections are editorial. No replay ranking or future virality is claimed.
Prepared files still require the user's review before any social publishing;
no account publication or submission was performed.

## Artifacts

- [All four clips and captions](../clips/67f69696-four-clips.zip).
- [Combined post captions](../clips/67f69696-post-captions.txt).
- Final controller result: `storage/clipping/orders/67f69696-94b1-4649-b2cf-725647f88100/result.json`.
- Source provenance and authorization: `cache-reuse.json` in that order folder.
- Caption revisions: `caption-corrections.json` and `caption-revisions/`.
- Mechanical/audio evidence: `final-audit.json`; delivery hashes and ZIP audit:
  `delivery-audit.json`.
- Actual export frames: `review-01/` through `review-04/`, and
  `contact-sheet-final.jpg`.

The ZIP's CRC check passed, and each archived MP4 checksum matches its delivered
file. The bundle contains exactly four MP4s, their spoken subtitles, post
captions and source attribution. All media and metadata belong to this order.
