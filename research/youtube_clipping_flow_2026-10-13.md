# YouTube discovery to one captioned highlight

The previous delivered video verified rendering with authored fixture subtitles.
It did not establish successful YouTube discovery, a famous source moment, or
speech-caption accuracy on a real YouTube video.

## Implemented flow

Run `./start-youtube-clipping.ps1` from the project in normal PowerShell, then open
`http://127.0.0.1:8000/`. The main action is **Search long videos & make one clip**.
Instagram is not needed for this private preview.

- `clipping/trends.py`: scans six niches, keeps dates/counts unknown unless obtained
  from YouTube, ranks by observed growth or lifetime-average views/hour, and selects
  one recorded source longer than 20 minutes and up to two hours from the last
  14 days. Official API search uses `videoDuration=long`; public search checks up
  to eight metadata candidates per niche and rejects short sources for preview.
- `clipping/trends_api.py`: accepts `auto_preview=true` on the scan request. The
  persistent agent queues exactly one ranked preview after discovery. It preserves
  intent added during an active search, replaces stale connection retries, and
  recovers the scan-to-job handoff after a restart without duplicate jobs.
- `clipping/media.py`: saves bounded numeric replay bins through yt-dlp's
  `after_move` output, without persisting a full metadata dump with signed URLs.
  It explicitly enables an available Deno or Node runtime. Speech transcription
  and burned-in word-aligned subtitles use the downloaded source audio.
- `clipping/planning.py`: prioritizes YouTube replay peaks within transcript
  windows when valid non-flat replay data exists. Missing replay data remains
  explicitly labeled editorial selection. Suggestions do not create extra videos.
- `clipping/workspace.html` and `clipping/trends.js`: connect the main action to
  discovery, hand off the chosen job, show progress, display the transcript-derived
  post caption and subtitle origin, and retain source-view statistics for review.
- `start-youtube-clipping.ps1` and `clipping/__main__.py`: start a fresh worker,
  refuse an occupied port, and preserve inherited network settings. The launcher
  checks the JavaScript runtime and installs the companion version required by
  the existing yt-dlp metadata when absent or mismatched. It supports this
  project's uv environment, which has no pip module installed.

Replay intensity compares moments within a video; source-view ranking compares
the bounded search sample. Neither establishes that a newly exported clip will
go viral. A missing source or transcript never produces substitute demo footage
or authored sample subtitles.

## Fresh verification

**153 clipping tests passed; one Instagram UI test was deselected.** The four
Instagram-specific Python test modules were excluded at the user's request.

```powershell
python tests/clipping/run_tests.py tests/clipping --ignore=tests/clipping/test_instagram.py --ignore=tests/clipping/test_instagram_oauth.py --ignore=tests/clipping/test_instagram_tunnel.py --ignore=tests/clipping/test_instagram_token.py -k 'not instagram' -q --tb=short
```

The final full run completed in 69.63 seconds. An earlier concurrent run hit an
existing half-second child-start timing assertion; the isolated process-cleanup
test and the final full run both passed. The native startup check also exposed
and verified a fix for console encoding when Python output is redirected on
Windows. PowerShell launcher parsing completed with zero errors, its companion
requirement resolved to `yt-dlp-ejs==0.8.0`, and uv's installer flags were checked.

The actual Python 3.11 server served the new main action, returned healthy status,
queued the automatic discovery intent, reused its running scan on the API, and
recorded the refused YouTube connection while creating zero jobs or fake clips.
Evidence: [native server verification](../.workflow-tests/youtube-flow-90566481e82d49b88c576c8662421bdc/verification.json).

## Remaining live verification

This tool environment still cannot reach YouTube through its inherited proxy.
The old worker was stopped and port 8000 was checked free for the normal-terminal
launcher. Downloading a live source, fetching its actual replay data, installing
the missing solver online, checking spoken-caption accuracy and real-browser
playback remain unverified. UI interaction checks use a JavaScript DOM harness;
they are not browser playback evidence. Source acquisition keeps the existing
500 MB limit; automatic transcription keeps the existing 30-minute deadline and
genuine-SRT handoff if speech recognition cannot finish.

## Primary implementation references

- [YouTube search duration and ordering](https://developers.google.com/youtube/v3/docs/search/list)
- [yt-dlp YouTube replay extraction](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py)
- [yt-dlp output and simulation options](https://github.com/yt-dlp/yt-dlp#verbosity-and-simulation-options)
- [yt-dlp JavaScript runtime and matching companion setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
