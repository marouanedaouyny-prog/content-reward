# Content Rewards clipping workflow

This is the working local entry point for clipping. It prepares a real video, persists review decisions, and guides you through publication, campaign submission, and reward tracking. Its built-in Python engine handles job intake, queuing, checkpoints, and approval resumption without n8n. It has its own database and queue consumer, so it does not depend on the unfinished legacy orchestrator or social connector.

The user's standing workflow and caption preferences are saved in
[AGENTS.md](../AGENTS.md): identify the current order, search YouTube, choose
strong standalone moments, render three or four highlights, add approved studio
captions, review the export, and deliver that order's result.

## Run one complete clipping order

### Run it from chat

Tell the assistant **"run the clipping workflow"**. The saved project
instructions tell it to execute **`run-clipping-auto.cmd`** directly using its
tools. You do not need to enter the launch command yourself. It resumes the
latest unfinished production batch or starts a fresh 20-clip colorized/fit
batch when the previous one is finished. An already-running batch is detected
without launching a duplicate.

The runner requires no keypresses and does not open Explorer. It prints progress
and a final JSON summary containing the order ID, actual output paths and saved
manifest/event-log paths. Run `run-clipping-auto.cmd --status` to inspect saved
progress. `--new` explicitly starts another batch; `--new --clips 40` changes
its target. Resume preserves settings; changing an unfinished order's options
requires a separate `--new` order. `--resume ORDER_ID` selects an exact order.

The assistant's direct equivalent is:

```powershell
.\.venv\Scripts\python.exe -m clipping.autorun
```

This runs when requested in chat or launched locally. It inherits its process's
network access and reports connection failures with a saved resume command.
It cannot remove restrictions on the tool session's YouTube access. The manual
launcher below remains available for running in your normal terminal.

### Make 20 colorized clips per run

Double-click **`make-20-clips.cmd`**, or run this from the project folder in your
normal PowerShell terminal:

```powershell
.\make-20-clips.cmd
```

This repeatable workflow starts a fresh search, ranks real transcript moments
and available replay signals, and prepares **20 distinct clips** with the lime
colorized captions approved in `clips/50-Cent-Colorized.mp4`. It keeps the full
source picture over a blurred background, original speech and 1080x1920 output.
It can take up to 20 strong moments from a long source and uses additional
eligible sources when needed. The last verified search contained only two
eligible videos, so the launcher does not restrict a run to four clips per video.
No full-video or full-audio fallback is allowed.

Every successful run writes its MP4s, subtitles and separate post captions into
**`clips/`** and opens that folder. Read **`clips/LATEST-CLIPS.txt`** for the exact
new filenames. Historical exports remain available. Each run also has its own
`<order>-CLIPS.txt` index and result JSON, avoiding confusion with previous clips.

```powershell
.\make-20-clips.cmd --resume latest
.\make-20-clips.cmd --status
.\make-20-clips.cmd --clips 40
.\make-20-clips.cmd --niche "Business"
```

There is no fixed total-clip quota in this workflow: rerun it for another fresh
batch or choose another positive count. Available sources, download access,
disk space and rendering time remain finite. Resume retains its original count,
styles, source windows and completed jobs. It verifies existing exports instead
of downloading or rendering them again. If a run has too few distinct eligible
moments, it saves reviewed partial exports with an explicit shortfall and can
search again on resume. It never duplicates a previous clip to reach the count.

Prior order windows and near-duplicate transcript passages are excluded.
Detected greetings, introductions, ads, context-dependent openings and unfinished
answers are rejected in this larger-run mode. Captions use actual local ASR word
timings; source-caption coverage and text agreement are checked to catch gross
omissions and repeated hallucinations. Full spoken transcripts are not supplied
as Whisper prompts: a real-media regression showed that they can suppress ASR
speech. Poor ASR windows are replaced rather than counted as finished clips.
These checks do not establish perfect transcription or semantic quality.

The Windows launcher uses the public discovery path that worked for your latest
clip. `--provider selenium` remains available. Connection failures retain the
order and use bounded retries. Run in your normal terminal; this tool session
may have different network/browser restrictions.

The workflow ranks for useful hooks and complete payoffs. It cannot guarantee
virality or follower growth. Exports are prepared **for review**; social login,
uploading and publishing remain separate. The generic controller below retains
its historical four-clip studio default; the new launcher supplies the requested
20/colorized settings explicitly.

The current social-account preference is **Instagram, YouTube and TikTok,
with posts prepared for review**. The user will connect credentials locally,
one account at a time, starting with the existing Instagram hidden-token
launcher. Publishing remains disabled. The Instagram connector does not
establish YouTube or TikTok access; verify each account separately before
claiming it is connected. A main niche and public profile targets are still
needed for account-specific post preparation.

The current controller defaults to **four distinct highlights from one newly
discovered popular long video**, using partial downloads and the new `studio`
captions. All finished exports appear together in the project **`clips/`** folder.
Earlier exports and caption previews are labeled separately from new batches.

From the project folder in a normal Windows terminal:

```powershell
.\run-youtube-clipping.cmd
```

This controller checks the local tools and source connectivity, searches all
six niches, compares eligible long sources and reads public English captions
plus available replay data. It selects four separate moments (three if only
three distinct windows fit), then downloads only those windows with three
seconds of context on each side. Local Whisper transcribes each small section
for actual spoken subtitles and word timing. The controller renders vertical
clips, verifies each export and prints its path and separate post caption.
It operates without Instagram login or publishing.

No full-video or full-audio fallback is allowed in this mode. Missing usable
public captions tries another ranked source, up to three candidates. Bounded
time-range acquisition uses yt-dlp's
[documented section downloads](https://github.com/yt-dlp/yt-dlp#download-options)
and FFmpeg over seekable HTTPS formats. Nearby keyframes, stream indexes and
protocol overhead can require extra bytes; exact network transfer savings have
not been benchmarked. A section with an unexpected duration is rejected.

Every ordinary invocation starts a **new order and fresh search**. To continue
saved work after a connection failure, interruption or repaired setup:

```powershell
.\run-youtube-clipping.cmd --resume latest
```

You can also double-click `resume-youtube-clipping.cmd` to continue the latest
saved order. If Chrome/Selenium cannot start, the batch controller falls back
to public discovery in the same order and records that choice for resume.
The fallback uses the existing public/API discovery path, preserves proxies
and TLS, and never enables full-video downloads. A provider switch starts a
fresh discovery scan; completed source selection and clip checkpoints remain
on their chosen source. Other setup errors retain their original error status.

You can replace `latest` with the exact order ID printed by the controller.
Completed sections, transcripts and clips remain checkpoints. A resume reuses that
order; it does not create a replacement search or silently deliver an old clip.
Use `--status` to read the latest saved order without running its workers.

Optional settings for a new order:

```powershell
.\run-youtube-clipping.cmd --clips 4 --caption-style studio --duration 35
.\run-youtube-clipping.cmd --clips 3 --niche "Business"
.\run-youtube-clipping.cmd --clips 1 --caption-style colorized
.\run-youtube-clipping.cmd --caption-style pro --framing crop
.\run-youtube-clipping.cmd --provider public
```

For an explicitly requested batch with a different subtitle look on each clip:

```powershell
.\run-youtube-clipping.cmd --clips 4 --caption-styles studio pro colorized classic
```

Or double-click `start-varied-clips.cmd` for a new order. The selected style
sequence is saved and rotates across distinct highlights from the same source;
resume retains each job's style. Style names appear in mixed-batch delivery
filenames and result metadata. Use `resume-youtube-clipping.cmd` to continue a
saved batch. This option does not change the approved studio/fit defaults.

Defaults are Selenium discovery, all niches, four clips with a 35-second target,
`studio` captions and `fit` framing. Studio keeps natural sentence case and white
text, with selective cyan emphasis timed to actual words. It avoids bouncing
and highlights one content word per short phrase. The existing `colorized` and
`pro` samples remain available. Fit keeps the full source image over a
blurred background, preserving speakers during wide shots. Crop uses the
existing portrait crop. Each clip still needs a content/timing review; the
user has approved `clips/caption-preview-studio.mp4` as the default appearance.
Exact settings and the repeatable agent workflow are recorded in
[the studio roadmap](../research/studio_template_roadmap.md). If Selenium is installed in another
Python, supply `--browser-python "C:\Python314\python.exe"`. This runtime path
can also be corrected while resuming.

The controller allows three connection attempts per connected stage per invocation,
with 5- and 10-second waits, then exits with the order saved. Configure that
budget with `--connection-attempts` and `--retry-delay`. Source-specific access
refusals try the next ranked candidate, up to three sources. Setup errors,
TLS verification failures, missing speech and failed export checks have distinct
statuses. The controller preserves inherited proxies and TLS verification.

| Exit code | Meaning |
| --- | --- |
| 0 | Export ready for review, or an informational command completed |
| 75 | Connection unavailable; resume the saved order later |
| 2 | Setup, source, transcription or export review needs attention |
| 3 | Another controller owns this order |
| 130 | Interrupted; checkpoints retained |

`ready_for_review` means the actual export passed checksum, dimension, duration,
subtitle-content/timing, full-decode and audible-audio checks. Five actual frames
are saved for visual review. Framing, source context, caption taste and
word-for-word ASR accuracy still need review. Replay-based selection is identified
when available; otherwise selection is explicitly editorial. The planner uses
source-title relevance, independent openings and completed answers, and penalizes
filler and promotional language. These scores do not establish guaranteed virality.

State, progress events, review frames, source-caption metadata, small downloaded
sections and `result.json` are under `storage/clipping/orders/<order-id>/`.
MP4, SRT, ASS, separate post captions and the batch manifest are copied into
the single flat `clips/` delivery folder. Filenames include the order and source
IDs so previous clips cannot be confused with a new batch. Each order has an isolated workflow
database and an OS lock; media and models use the existing shared storage.
Open the printed MP4 path for this controller's result. The native entry point
for other scripts is `.venv/Scripts/python.exe -m clipping.orchestrator`.

## Search long YouTube videos and make one captioned clip

From the project folder in a normal PowerShell terminal:

```powershell
.\start-youtube-clipping.ps1
```

Open **http://127.0.0.1:8000/**. Startup searches six niches for videos published
within 14 days, longer than 20 minutes and up to two hours, ranks eligible sources
by observed growth or views/hour since upload, and queues exactly one preview.
The main **Search long videos & make one clip** button starts the same flow.
Source dates, durations and view counts are shown in **YouTube long-video search**.
Public search needs no API token; an existing `YOUTUBE_API_KEY` enables official
API discovery. The supported `ytsearch8:` mode obtains a bounded relevance sample;
publication dates from inspected metadata enforce the 14-day eligibility window.
The installed downloader does not support the old `ytsearchdate8:` command.
Searches inspect missing metadata before eligibility. This ranks the sampled
sources, not all YouTube. Invalid commands fail with setup guidance; only detected
connection failures, rate limits and timeouts enter automatic retry.

For the Selenium installation in system Python 3.14, run:

```powershell
.\start-youtube-clipping.ps1 -Selenium -BrowserPython "C:\Python314\python.exe"
```

Double-clicking `start-youtube-clipping.cmd` also selects Selenium. Browser search
runs in the Python that has Selenium installed; transcription and rendering stay
in the project Python 3.11 environment. The launcher first checks that an isolated
Chrome session can start and reach YouTube. Selenium Manager obtains its matching
driver and keeps its cache in `.workflow-tests/selenium-cache`.

The browser reads public search/watch metadata for at most eight source videos
per niche. Exact view counts, source duration and publication dates are retained;
missing or abbreviated metrics remain unknown. Only public metadata is passed to
the existing ranked-source selection and one-clip workflow. No personal Chrome
profile, account cookies or signed media URLs are returned. Browser and driver
downloads preserve inherited proxy settings. Switching search providers starts
a fresh scan rather than reusing findings from the old provider.

The downloader saves only numeric replay-heatmap bins alongside the source.
The planner prioritizes replay peaks within transcript boundaries when available.
Missing, malformed or flat replay data falls back to explicitly labeled editorial
selection. No method guarantees that a new clip will go viral. Only the selected
window is rendered; alternative suggestions are metadata, not additional videos.

Subtitles come from local Whisper transcription of the actual source audio.
Its word timestamps drive short captions burned into the vertical MP4, and SRT
is also downloadable. When source metadata is available, the post caption uses
its headline and creator credit; otherwise it uses the selected transcript opening.
It appears in the preview and package. Source or transcription failure is shown
as a waiting/error state; no demo footage or sample captions are substituted.
Instagram is unnecessary for this private local preview.

Caption rendering defaults to the approved `studio` style and `fit` framing
when settings are omitted, including API/manual previews. It accepts optional
`payload.caption_style`: `classic` uses plain white captions, `colorized` uses
bold uppercase captions with the current word highlighted in lime, and `pro`
uses gold keyword emphasis. Styled options export editable `subtitles.ass`
alongside the plain SRT. Colors follow source word timing where available;
segment-only transcripts are not assigned invented word timings. Existing
requests with explicit settings retain those choices. Default resolution does
not rewrite saved request fingerprints. The shared defaults are in `template.py`.

Batch planning now checks up to 20 non-overlapping candidates before choosing
three or four. It penalizes filler-led openings and long speech gaps, excludes
detected promotional passages, and filters near-duplicate normalized transcripts
even at different replay peaks. Speech coverage, gap flags and selection reasons
are retained for review. Distinct semantic takeaways and complete context still
require editorial review; the scores are not predictions of future views.
See [the primary-source research](../research/clipping_quality_guidance_2026-10-16.md).

The launcher checks the installed JavaScript runtime and installs the matching
`yt-dlp-ejs` companion in the project environment if missing. The installed Node.js
24 runtime is explicitly enabled for YouTube challenge solving, following the
[official yt-dlp setup guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

The launcher starts a fresh worker so it uses the normal terminal's network
environment. It refuses to reuse an occupied port: stop the existing workspace
with Ctrl+C, or use `-Port 8002`. It does not alter proxy settings. This agent's
YouTube connection remains refused in this tool session. On October 14, the
user's normal launcher successfully discovered and downloaded a real long
source and produced a spoken-caption preview. See the
[real-source verification record](../research/youtube_real_clip_verified_2026-10-14.md).
Word-for-word ASR accuracy and real-browser playback still need review.

Implementation references: [YouTube long-video search parameters](https://developers.google.com/youtube/v3/docs/search/list),
[yt-dlp replay extraction](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_video.py),
and [yt-dlp output options](https://github.com/yt-dlp/yt-dlp#verbosity-and-simulation-options).

## Saved IShowSpeed test

On Windows, double-click `start-ishowspeed.cmd`. PowerShell users can run
`./start-ishowspeed.ps1`, or run:

```powershell
.venv/Scripts/python.exe -m clipping --ishowspeed
```

Startup automatically queues the saved IShowSpeed preview. Open
**http://127.0.0.1:8000/** to see its progress; no source, niche, timestamp,
format, caption or subtitle selections are required. This preset is separate
from the main long-video discovery button. The equivalent API is
`POST /api/v1/clipping/automations/ishowspeed/runs` with no body or `{}`.

If this workspace is already running on the selected local port, the launcher
reuses it and starts/opens the saved preview instead of starting a second
server. It checks the API identity before sending the run request.

The preset selects **I Met Cristiano Ronaldo** from three official uploads
checked on October 8, 2026. Its view count is a dated search snapshot, not a
live ranking of the entire channel. It downloads actual footage, transcribes
with the installed English model, selects a transcript window near 30 seconds,
renders a subtitled 9:16 MP4, and completes as a **local preview**. MP4, SRT and
preview details are available in the workspace. Campaign and clip approvals
are not required for this private test; the campaign workflow keeps its gates.

Temporary source failures retry after 60, 300 and 900 seconds, then every 30
minutes until acquisition succeeds or you pause/cancel. This applies to private
previews and approved campaign jobs. Retry times, approvals, partial downloads
and completed checkpoints survive restart. Permanent errors remain failed with
an explicit retry action. No synthetic footage or invented subtitles replace a
failed source. `DRY_RUN=true` rejects this real-video preset.

Downloads use four parallel DASH/native-HLS fragment connections, explicit
partial-file resume and a 1080p source cap. Each attempt has finite HTTP and
fragment retries, a 20-second socket timeout and a 30-minute total deadline.
Complete sources are reused after a checkpoint interruption; video-only format
files are excluded. Sources remain limited to 500 MB. These controls reduce
avoidable work, but actual throughput depends on the connection and protocol;
no live download speed benchmark has been possible in this environment.

Automatic transcription runs in an owned process, so Pause, cancellation and
shutdown can interrupt model loading and inference. Each attempt has a 30-minute
deadline. An empty speech result, inference failure or timeout requests timed
SRT subtitles while retaining the prepared source. Partial or invalid automatic
transcripts are not saved as completed checkpoints.

Automatic transcription preserves verified word timestamps. Rendering groups
those words into short phrases, ends captions at their aligned speech times,
and excludes words outside the selected clip. Phrases normally use one or two
lines; a single long token can exceed that layout budget. Imported SRT cues,
older transcripts, and segments containing zero-duration word alignments keep
their original segment timing instead of receiving guessed word timing.

This environment's proxy currently refuses YouTube connections. The automatic
run therefore waits/retries acquisition rather than producing an IShowSpeed
clip. Real-browser visual verification also remains unavailable because Chrome
cannot create its Windows IPC channels here. Native rendering on a labeled
fixture and script/API checks are separate evidence. See the
[workflow research](../research/automatic_clipping_workflow_2026-10-08.md).

The preset does not publish, submit rewards, discover eligible campaigns across
niches, or schedule daily campaigns. Those require actual permissions and
provider-supported interfaces; a successful private preview is a distinct
result.

For a reward campaign, start with authorized source footage and copy the
campaign's actual requirements. Campaign selection, source permissions, crop
quality, factual context, and account eligibility require your review.

## Start locally

Use Python 3.11 or newer. Install FFmpeg with its `ffprobe` executable and put both on PATH. Run these commands from the project root:

```powershell
python -m pip install -r requirements-clipping.txt
python -m clipping
```

Open **http://127.0.0.1:8000/**. If the legacy API is running on port 8000, stop it or run `python -m clipping --port 8001` and open that port instead. This single process starts both the browser workspace and its background worker.

Click **Try a five-second practice clip**, approve the campaign review, wait for preparation, watch the generated video, and approve the clip. Practice mode creates harmless synthetic footage and subtitles, then completes without publishing or submitting anything.

For automatic transcription of real footage on Windows, run the setup command:

```powershell
.\setup-transcription.ps1
.\.venv\Scripts\python.exe -m clipping
```

This installs dependencies in the project's Python 3.11 environment and prepares `tiny.en` on CPU. **Select English** as the spoken language to use that model. Start the app with the `.venv` executable above so it uses the installed libraries. To prepare a multilingual model for French, Arabic, and automatic language detection, run `.\setup-transcription.ps1 -Model small`. Model downloads need internet access and disk space.

The app prefers a complete local `models/small` folder, then local `models/tiny.en` for explicitly selected English. An explicit `WHISPER_MODEL` takes precedence. Without a usable model, the job asks for a timed SRT transcript. Import a `.srt` file or paste its text during intake or after that pause; preparation resumes from the saved source.

For a subtitle mockup, open **Use your own timed subtitles** and click **Load five-second subtitle demo** while practice mode is checked. Create and approve that practice job to render the three sample captions. The [sample SRT](examples/practice.srt) is demonstration text for the generated practice video, rather than recognition of its tone audio. Source URLs use yt-dlp; uploading authorized footage is the most direct path.

## Use a real campaign

The workspace now includes a **YouTube source checker**, local metadata cohort reports, and optional transcript-based cut suggestions across niches. Enable the automatic planning option to select and render a window after campaign approval, or apply a suggested SRT window manually. Suggestions are explainable editorial heuristics, not forecasts of virality. See the [research and planning guide](RESEARCH_GUIDE.md) for inputs, the data model, demonstrations and verification limits.

1. Join an eligible campaign and review its terms. Copy its title, page URL, platform, requirements, duration limits, and source authorization into the workspace. Select **current** or **legacy** according to the campaign. Record its actual reward rate if known.
2. Disable practice mode. Upload an authorized source video (up to 500 MB) or provide its HTTPS source URL. Choose a start time, length, and aspect ratio. Add the required caption and any supplied SRT transcript.
3. Approve the campaign and rights task. The background worker acquires the source, transcribes it or waits for SRT, cuts and crops the selected window, burns subtitles, and checks the exported video.
4. Watch the complete clip. Check the crop, transcription, context, tags, disclosures, and campaign rules. If draft review is required, obtain brand approval and record its reference before approving the clip. Downloads include MP4, SRT, and a preparation package.
5. Publish the approved clip using your eligible platform account. After it is public and processing has finished, record its URL and actual publication time in the workspace.
6. Submit that public URL in the actual Content Rewards campaign. Record the submission ID or confirmation reference and actual submission time. The current creator guide specifies submission within 30 minutes of posting; the workspace displays that deadline. Legacy campaigns use their own terms. [Current creator guide](https://contentrewards.com/creators).
7. Record brand decisions and payment receipts as they arrive. Payments require an actual amount received. These records are operator confirmations; the app does not independently verify views, platform approvals, or payments.

`completed` means a local preview/practice run finished or the operator recorded a real submission. It does not mean the brand approved or paid it. The preparation package also does not constitute a submission. There is no automatic social posting or Content Rewards submission in this runtime: the documented research did not establish an available public creator submission API. See [research](../research/whop_clipping_research.md) for the evidence and platform constraints.

## Trending research agent

Open **Trending research** in the workspace. A separate background agent starts
automatically and searches gaming, AI/technology, business, fitness, sport, and
culture/comedy. It saves reports in the clipping database and refreshes every
six hours while the application runs. Connection failures retry with saved,
increasing delays; successful niche results are retained. **Pause research
agent** controls its schedule independently of video jobs. The global processing
pause also stops research.

Without credentials the agent uses bounded yt-dlp public searches, with at most
two metadata inspections per niche when publication dates are missing. An
optional `YOUTUBE_API_KEY` enables the official YouTube Data API: recent niche
searches followed by video statistics. No credential is required to use the
public-search adapter. Search failures are shown rather than replaced by demo
results. The official API may have access or quota restrictions.

Each result records its source, observation time, publication time, duration,
views and niche. Ranking uses measured growth when two comparable snapshots
exist, otherwise views/hour since upload, which is a lifetime average. Unknown
metrics stay unknown. These signals are editorial research, not viral forecasts
or evidence of campaign eligibility. Results older than 14 days and active or
upcoming livestreams are excluded when their dates/status are available.

**Prepare the best research preview** queues the highest-ranked eligible source
without niche, timing or format choices. A preview needs a known recent upload
date, view count and a recorded 1–120 minute video. It prepares a private local
clip and does not publish or submit rewards. **Use source in campaign** copies
the URL into Source, clears conflicting uploads, and preserves your existing
campaign rules, permission notes and caption. Record real permission before
approving campaign processing. Review speech, framing and factual context.

API: `GET /api/v1/clipping/trends`, `POST /api/v1/clipping/trends/runs` with `{}`,
`POST /api/v1/clipping/trends/schedule` with `{"enabled": false}` or `true`, and
`POST /api/v1/clipping/trends/runs/{id}/preview` with `{}` to select the best
source or `{"candidate_id":"VIDEO_ID"}` for a saved candidate.

Research and video workers run while the app is open. Closing the server or
shutting down the computer stops them; saved jobs resume when it restarts. The
Docker service uses `restart: unless-stopped` for process failures while Docker
is running. No workflow setting can fix a blocked network connection.

See the [tool assessment](../research/trending-tools-assessment.md) for Laya,
GEO, MiroFish and the official discovery/download sources. These tools are not
installed or required by this workflow.

## Saved state and controls

The **Instagram account** section offers **Connect Instagram** and **Verify
Instagram access**. Connect opens Instagram's consent screen and returns to the
account section after the server exchanges the authorization code, confirms the
profile and checks permissions. This connects an account; posting stays disabled.

For browser authorization, configure `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`
and `INSTAGRAM_REDIRECT_URI` in the project-root `.env.local` or environment.
Use the Instagram Login app credentials and a redirect URI accepted and
registered by Meta. The local app supports
`http://127.0.0.1:8000/api/v1/clipping/accounts/instagram/callback`; acceptance by
Meta has not been verified here. Open the workspace using exactly the same
scheme, host and port as the registered callback so its browser cookie returns.

Successful authorization saves the token and account ID together in the local
clipping database. This saved pair takes precedence over older manual tokens.

To connect your own account without a tunnel or local OAuth callback,
generate an **Instagram user access token** in Meta's app dashboard for the
Instagram API with Instagram Login. The account must be a professional
Business or Creator account. Meta documents app-dashboard token generation
in its [Instagram API collection](https://www.postman.com/meta/workspace/instagram/documentation/23987686-9386f468-7714-490f-9bfc-9442db5c8f00).
Run `./connect-instagram-token.ps1` from the project root in a normal PowerShell
terminal and paste the token into its hidden prompt. No ngrok installation,
callback registration or account-ID entry is needed for this route.

The command checks the profile before replacing saved credentials, derives
the account ID and saves the pair together in the shared clipping database.
It then checks identity and permissions using the normal terminal's network
environment. The running workspace reads that saved access without a
restart. The command prints `authorized` after identity verification;
permission lookup failures may leave publishing permission unknown. Posting
remains disabled. Tokens are never printed, accepted as command-line
arguments or exposed through the workspace. Redirected input is rejected
rather than allowing a prompt that echoes the token. Existing expiry data
is retained when reimporting the same saved pair; a new token without known
lifetime data has unknown expiry.

For an HTTPS development callback, run `./start-instagram-tunnel.ps1` in a
normal PowerShell terminal from the project root. It uses the saved ngrok
account configuration and finds the executable in the project cache, on PATH
or in the WinGet installation. If ngrok rejects an old agent with
`ERR_NGROK_121`, it copies that executable into `.workflow-tests/ngrok-runtime`,
runs ngrok's signed update there and retries once. Future runs use that copy.
See [ngrok's update command](https://ngrok.com/docs/gateway/agent/cli) and
[version-2 tunnel configuration](https://ngrok.com/docs/gateway/agent/config/v2).

The launcher checks outbound Instagram connectivity, starts an isolated
authentication service on 127.0.0.1:8001 and creates a Basic Auth protected
HTTPS tunnel to it. It preserves the public Host header, disables local
request inspection and generates temporary tunnel credentials in a local
file. The terminal displays that file's path. The authentication service
does not expose clipping job routes; the regular workspace can keep running.

Keep the terminal open. Once a real HTTPS endpoint is available, the launcher
saves its exact callback as `INSTAGRAM_REDIRECT_URI`, checks the authorization
request and Secure state cookie, and prints `callback_ready`. Save that exact
callback in Meta's Instagram login **Valid OAuth Redirect URIs**. Open the
displayed authentication page, use its local tunnel credentials and select
**Connect Instagram**. The callback must return to that same HTTPS host.
Successful authorization and account verification save the access pair in
the shared local database and print `authorized`. Posting remains disabled.
The temporary tunnel credentials and server are removed when setup exits.

Local checks do not establish Meta registration or user consent. Ngrok
supplies the incoming HTTPS route; token exchange requires outbound access
from the terminal running setup, and source downloads require outbound access
from the clipping worker. A refused proxy is reported separately from invalid
account credentials.
If setup fails, run `./start-instagram-tunnel.ps1 -Diagnose` in the same terminal.
This checks the resolved ngrok and Python paths, executable version, ngrok
configuration validity and connectivity to both Instagram hosts without
starting a tunnel or login. Its JSON includes safe DNS, TLS, timeout or
connection-refusal categories, with no credentials or raw provider errors.
The diagnostic result is saved separately in
`.workflow-tests/instagram-network-diagnostic-last-run.json`. Normal setup
failures now include the connection stage; ngrok cloud failures are reported
as `ngrok_network_unavailable`, separately from Instagram preflight failures.

Without a saved OAuth pair, the app reads `INSTAGRAM_ACCESS_TOKEN` and
`INSTAGRAM_ACCOUNT_ID` from the environment, then `.env.local`. These local files
and the database are ignored by Git and are never served by the workspace.

**Verify Instagram access** makes bounded, read-only HTTPS requests to
`graph.instagram.com` using server-side bearer authentication. It checks the
token's account identity against the configured ID and probes granted
permissions. If permission lookup is unavailable, publishing access remains
unknown. Network failures, invalid tokens and account mismatches have distinct
status messages. Provider errors are sanitized, redirects are refused, and API
responses do not expose the token. The last checked status is stored in the
clipping database with a credential fingerprint; changing credentials invalidates
that saved result. A previous successful check is not a guarantee of future
token validity.

OAuth token lifetimes are saved when the provider returns a positive integer
`expires_in`. The account section shows the resulting expiry date. Missing
lifetime data and manually configured tokens retain **unknown expiry**; the app
does not assume a fixed lifetime. Expired credentials clear cached identity and
permission claims, skip further provider checks, and offer **Reconnect
Instagram**. Expiry is checked again after network verification so an account
cannot return a current verified state if its token expired during that check.
An unsuccessful account check after OAuth now returns its actual failure state
instead of a connection-success message. Automatic renewal remains pending
validation of Meta's current provider contract.

Endpoints are `GET /api/v1/clipping/accounts/instagram`,
`POST /api/v1/clipping/accounts/instagram/verify` and
`POST /api/v1/clipping/accounts/instagram/connect`; POST requests use `{}`.
The callback is `GET /api/v1/clipping/accounts/instagram/callback`.
Authorization states expire after ten minutes, are bound to an HttpOnly browser
cookie, and can only be used once. Callback query strings are removed from
application access logs, and callback responses disable referrer forwarding.
Verification and token exchange run
outside the ASGI event loop. There is no Instagram publish endpoint in this
runtime; successful identity/permission checks keep posting disabled. The
legacy connector's Facebook Login implementation is not used by this check.

On 2026-10-12, Instagram app configuration was present, but no authorized account
token was saved. Native HTTP connection-start and declined-callback checks
passed without a provider request. Outbound access was refused, so actual
authorization, account identity, permissions and token expiry remain unverified.

For Docker, pass the credentials without baking them into the image:
`docker compose --env-file .env.local -f docker-compose.clipping.yml up --build -d`.
An optional `INSTAGRAM_GRAPH_VERSION` environment variable can pin a supported
API version (format `vNUMBER.NUMBER`); otherwise the app's default API version
is used. App credentials and redirect URI are also read from `.env.local`.

Jobs start at `awaiting_campaign_approval`, then move through preparation, clip review, publication, and submission. Preparation runs outside the ASGI event loop, and the app starts its own queue consumer. Each database operation opens a separate SQLite connection.

Approved stages and completed preparation checkpoints survive restart. A worker heartbeat keeps its processing lease current; a running job abandoned for five minutes is requeued on startup or during maintenance. Use a single application process/worker for this local deployment. Failed jobs retain their error and checkpoints and offer **Retry saved job**. Creating the same normalized request reuses the existing job; an explicit idempotency key cannot be reused with different input. To make a fresh variant, change its clip plan/caption or supply a new explicit key.

Approvals bind to the reviewed input and rendered clip hash. A modified clip cannot be approved or confirmed as the published artifact. **Pause processing** stops new jobs and interrupts active downloader/FFmpeg processes and their children. Windows uses an owned job object and a launcher gate, so child cleanup does not require `taskkill`. A refused job assignment prevents the media executable from starting and reports a process-management error. Cancellation preserves the cancelled state; application shutdown requeues interrupted work for restart. Local model inference may still finish its current operation before the next checkpoint. The app cannot remove an external post or undo a submission.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `CLIPPING_DATABASE` | `data/clipping.db` | Separate clipping database; leave legacy `empire.db` isolated |
| `CLIPPING_STORAGE` | `storage/clipping` | Sources, transcripts, clips, and downloaded models |
| `WHISPER_MODEL` | Local model for the selected language, otherwise `small` | Optional faster-whisper model name or local folder override |
| `DRY_RUN` | `false` | When true, forces practice mode for newly created jobs |
| `KILL_SWITCH` | `false` | When true, blocks processing and publication/submission confirmations |
| `CLIPPING_AUTOMATION` | unset | Set to `ishowspeed` to queue/open the automatic local preview on startup |
| `CLIPPING_TREND_AGENT` | `true` | Start the independent research worker; `false` disables that worker at startup |
| `YOUTUBE_API_KEY` | unset | Optional official YouTube discovery credentials; otherwise use public search |
| `TREND_REGION` | `US` | YouTube API region context |
| `TREND_LANGUAGE` | `en` | API language hint and research preview's spoken-language default |

The database kill switch persists independently of the environment switch. A true environment switch remains effective even if the workspace toggle is cleared. This app is a local operator workspace without user authentication; the supplied commands and Compose file bind it to localhost.

## Docker

The dedicated Compose file includes FFmpeg, yt-dlp, optional local transcription, and this runtime:

```powershell
docker compose -f docker-compose.clipping.yml up --build -d
```

This Compose file runs only `clipping-api`; n8n is not part of the clipping deployment. The original Compose stack and historical n8n workflow files remain available for the legacy applications.

## Direct automation

Use `POST http://127.0.0.1:8000/api/v1/clipping/jobs` as the direct HTTP intake for a script, webhook sender, or another local application. It returns a saved job awaiting campaign approval. Review tasks appear in the workspace, and approval clicks resume preparation automatically. Use `GET /api/v1/jobs/{id}` to poll status. No separate orchestration service, workflow import, or activation is required.

This replaces n8n's role in this clipping workflow. It is a fixed clipping workflow rather than a general visual workflow editor. Campaign and clip review remain required, and external publishing/submission remain operator tasks.

## API example

Send this JSON directly to `POST /api/v1/clipping/jobs`:

```json
{
  "workflow_id": "content_rewards",
  "idempotency_key": "practice-software-clip-001",
  "payload": {
    "campaign": {
      "title": "Practice software clip",
      "url": "https://contentrewards.com/discover",
      "platform": "youtube",
      "experience": "current",
      "rights_notes": "Synthetic practice footage generated locally.",
      "rules": "A vertical practice clip with sample subtitles."
    },
    "dry_run": true,
    "caption": "Practice footage",
    "clip_plan": {
      "start_seconds": 0,
      "duration_seconds": 5,
      "aspect_ratio": "9:16"
    }
  }
}
```

For a real job, set `dry_run` false and supply exactly one `source_url` or `source_path`. `POST /api/v1/clipping/uploads` accepts a multipart `file` and returns the relative `source_path`. All relative paths must stay within workflow storage.

Read a job with `GET /api/v1/jobs/{id}`. Approve its current waiting step with `POST /api/v1/jobs/{id}/approve`:

```json
{
  "step_name": "campaign_review",
  "fingerprint": "copy approval_fingerprint from the current job",
  "approved": true
}
```

Clip review uses `step_name: "clip_review"` and its current fingerprint, with `brand_draft_reference` if required. `/transcript`, `/publication`, `/submission`, `/reward`, `/cancel`, and `/retry` expose the corresponding workspace actions. Read their schemas at **http://127.0.0.1:8000/docs**. Publication and submission timestamps require an explicit timezone.

## Validation and remaining limits

After adding word timing and shorter caption phrases, the full clipping suite
returned **183 passed** on 2026-10-13. Native Python 3.11 rendered a labeled
synthetic 1080x1920 test into five caption phrases with authored word timings.
Extracted frames showed readable two-line captions. This checks timing and
layout, while speech recognition accuracy on the actual source remains
unverified. See the [word-caption record](../research/word_captions_2026-10-13.md).

After correcting automatic sentence-ending selection, the full clipping suite
returned **161 passed** on 2026-10-13. The planning/automation suite returned
**32 passed**. Native Python 3.11 rendered a labeled synthetic test from a
30-second target to a valid 34-second sentence ending, retained its subtitle,
and preserved the plan after reload. Actual IShowSpeed acquisition remains
blocked. See the [sentence-selection record](../research/sentence_cut_selection_2026-10-13.md).

After adding controlled inference and empty-speech recovery, the full clipping
suite returned **154 passed** on 2026-10-12. The focused transcription/automation/
process suite returned **30 passed**. Native Python 3.11 interrupted a transcription
attempt in **0.53 seconds** without writing a partial checkpoint. The audible
local excerpt returned no speech with VAD, so caption accuracy remains unverified.
See the [controlled transcription record](../research/controlled_transcription_2026-10-12.md).

After fixing verification during credential replacement, the full clipping
suite returned **144 passed** on 2026-10-12. The targeted Instagram/browser-script
suite returned **52 passed**. Installed Python 3.11 independently passed a
concurrent reconnect and restart-persistence check with a synthetic provider.
See the [verification race record](../research/instagram_verification_race_2026-10-12.md).

After adding expiry/reconnection handling, the full clipping suite returned
**139 passed** on 2026-10-12. The targeted Instagram and browser-script checks
returned **47 passed**, and installed Python 3.11 fixture/HTTP checks passed.
These checks verify local lifecycle handling; actual authorization and automatic
provider renewal remain unverified. See the
[expiry record](../research/instagram_expiry_2026-10-12.md).

On 2026-10-12, the Instagram/browser interaction suite returned **34 passed**.
The initial full run returned **119 passed, 1 failed** because Windows refused
`taskkill`. After replacing that cleanup path with owned Windows job objects,
the full clipping suite returned **126 passed**, including deadline, Pause and
detached-child cleanup. The installed Python 3.11 environment also proved
cleanup after abrupt supervisor exit. See the
[process cleanup record](../research/windows_process_cleanup_2026-10-12.md).
The restarted Python 3.11 HTTP worker also exported and completed a new
five-second synthetic practice clip, verified as 1080x1920 H.264/AAC with no
publication or submission record.
Native HTTP OAuth start and declined-callback checks passed without a provider
request, and Docker Compose configuration validates. Actual Instagram login
and real-browser screenshots remain unverified because provider connections and
Chrome launch are refused. See the [connection record](../research/instagram_connection_setup.md).

On 2026-10-10, all 91 focused clipping tests passed, including resumable download
policy, continued retries beyond four attempts, preserved campaign approvals,
actual subprocess interruption, shutdown recovery, research persistence and
growth observations, independent worker startup, origin restrictions, private
preview selection and five UI interaction checks. Native HTTP routes returned
200 in the installed Python 3.11 app. Live research reported six connection
failures and scheduled another scan with zero verified sources; the saved
IShowSpeed preview was resumed with the continuing retry policy. Real download
throughput and live source discovery remain unverified because outbound access
is blocked. Visual review still needs browser screenshots.

Run the focused tests from the project root. On this Windows sandbox, use the
runner below so fixture directories inherit workspace access permissions:

```powershell
python tests/clipping/run_tests.py tests/clipping -q
```

The focused checks exercise actual FFmpeg/ffprobe rendering, dimensions and audio, saved approvals, restart recovery, idempotency, kill switches, cancellation, failures, input validation, real source/SRT preparation, and operator handoffs. Media tests skip if FFmpeg is absent; install it to exercise those checks.

On 2026-10-04, all 24 focused tests passed with FFmpeg available, including a direct API job rendered and resumed by the built-in worker without an external orchestrator. The native launcher is also covered. A running HTTP workflow produced and downloaded a 1080x1920 H.264/AAC video, persisted both reviews, and completed a practice job without publication or submission records. Health requests continued responding during rendering (maximum observed response time: 0.056 seconds in that run).

On 2026-10-05, PyPI and Hugging Face connections were refused. Installation nevertheless succeeded offline using cached wheels, with their existing RECORD hashes checked when recovering extracted wheels. The Windows environment uses faster-whisper 1.0.3, CTranslate2 4.8.2, PyAV 12.3.0, ONNX Runtime 1.30.0, and the remaining runtime dependencies. All 37 installed packages passed dependency compatibility checks. A complete cached [English `tiny.en` model](https://huggingface.co/Systran/faster-whisper-tiny.en) was copied into `storage/clipping/models/tiny.en` and loaded on CPU. Decoder inference and speech activity detection completed on a silent test input; this verifies the native runtime, rather than spoken-word accuracy. The larger multilingual `small` model was unavailable in the cache and has not been downloaded. Sample subtitles stay labeled as practice data.

All 27 focused tests passed after the subtitle changes. The running app in the installed environment reported English model readiness and rendered a five-second, three-caption practice video with preserved SRT timings. That job is named **Subtitle demo - three timed captions** in the workspace.

Compose configuration validated, but Docker's daemon was inaccessible and browser launch was denied by the environment. Those runtime checks remain unverified. Speech recognition accuracy on actual campaign footage still needs review; the model check and subtitle demo do not establish caption accuracy for that footage.

The earlier review findings in the legacy backend, frontend, project skills, OAuth connector, and legacy workflows remain separate work. Full legacy test collection is still blocked by missing SQLModel. This clipping entry point is a usable local workflow, not a claim that the entire repository is production ready. Caption quality, speaker framing, campaign compliance, and earning eligibility still require human review; checks here cover media integrity and the workflow's state transitions.
