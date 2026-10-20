# One clip from another video, with colorized captions

Order: `f64b1233-9eaa-4040-a875-ac74b8c030bf`.

**Delivered after the user's normal-terminal run:**
`clips/f64b1233-2v99_8xJoqA-01.mp4`, 42 seconds, colorized captions.
The connection-failure notes below describe the earlier tool-session attempts.
They no longer describe this order's completion status.

The user requested one new clip from a different video, using the existing
`colorized` caption style. This order uses lime word highlights, fit framing,
9:16 output, original audio and a 35-second target. It excludes the previous
Dana White source, `Q-DFC0AnbY4`. Studio remains the default for other orders.
Publishing is disabled.

## Fresh source research

Public pages were checked on October 18. These are preliminary candidates;
their counts are index snapshots, not live measurements, and their public
YouTube captions and media have not been acquired.

| Candidate | Indexed date | Length | Observed views | Source |
| --- | --- | --- | --- | --- |
| Eric Weinstein interview about secret alien programs (`IkhmdTqSvJw`) | Needs live confirmation | 1:52:58 | 2.3 million | [SubSub](https://open.subsub.io/channels/thediaryofaceo/view/content) |
| All-In: Martin Shkreli interview (`yZR8QW4qQmM`) | October 12, 2026 | 25:17 | 116,138 in the index's October 13 snapshot | [Trari](https://trari.com/en/c/allin/) |
| All-In: Is Claude Conscious? (`TBLHdXABwAg`) | October 10, 2026 | 1:33:15 | 474,742 in the same snapshot | [Trari](https://trari.com/en/c/allin/) |

No best moment has been claimed. Source selection must inspect the actual
transcript and available replay data. If replay data is unavailable, label the
selection editorial. Download only the selected range plus bounded context.

## Earlier tool-session attempts

- Public YouTube connectivity failed with a refused connection.
- The project's caption-first inspection of `IkhmdTqSvJw` returned
  `SourceUnavailable`; no source video was downloaded.
- Selenium returned `browser_session_not_created`.
- The installed Chrome automation tool found no running browser connection;
  its browser startup also encountered access-denied errors.
- The new controller run saved `connection_unavailable` at
  `source_connectivity`, reason `youtube_connection_unavailable`.
- At this stage no new MP4 or finished-result manifest existed. Earlier Dana
  clips and unrelated test media did not fulfill it.

The controller supports an explicit single clip through the existing
partial-download pipeline. Two regression tests failed before the change;
the batch, section and controller suites then passed all 37 tests. Ruff's
E4/E7/E9/F checks passed. This verifies controller behavior, not a new export.

The user resumed the exact order from their normal terminal:

```powershell
.\run-youtube-clipping.cmd --resume f64b1233-9eaa-4040-a875-ac74b8c030bf
```

## Successful acquisition and final review

The fresh discovery selected FLAGRANT's October 14 interview, **50 Cent on
Diddy's Life In Prison, Eminem, & Street Fighter Reaction**, source
`2v99_8xJoqA`. At acquisition it recorded 2,426,971 views and a 7,013-second
runtime. The downloaded source section is only 46.922 seconds; no new full
video was downloaded. The previous Dana White source was excluded.

The automatic choice was a greeting and guest introduction. Editorial review
trimmed the greeting and retained the comic career setup, Mets pitch joke,
Instagram punchline, guest identification and response. The final source window
is 1.78–43.78 seconds. This is an **introduction roast**, not a verified
most-replayed or most-famous moment. Later interview moments were inspected in
the public transcript; acquiring a later window still failed in the tool
session. This limitation must not be hidden by calling the introduction the
best moment in the whole interview.

The captions were corrected against the public source transcript, including
“made a fortune,” “Mets,” “Balrog” and “50 Cent Jackson.” The character spelling
was checked against the [official film cast](https://www.streetfightermovie.com/synopsis/).
Retained word timings were preserved. Proper names and the closing introduction
were regrouped for readability. The separate post caption was rewritten rather
than leaving the automatically truncated source text.

Final checks: H.264/AAC at 1080×1920, 42.000292 seconds, full decode, matching
source/export hashes, audible audio, matching subtitle text/timings and captions
limited to two lines. Seven actual export frames were inspected, including the
opening, ending, wide shot and corrected names. Source/export audio correlation
was 0.999147 over 672,000 mono samples. This does not establish perfect ASR
accuracy or exhaustive frame-by-frame review.

The MP4 is 16,237,650 bytes; SHA-256:
`615f000724dace84851f8f5dd30c11f2bb7e9f3ebee0fa33c5f81ab20233571d`.
The isolated order's `final-audit.json`, `caption-corrections.json` and
`caption-revisions/` retain the review evidence and original export. Publishing
remains disabled.
