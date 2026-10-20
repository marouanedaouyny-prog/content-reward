# Content Rewards clipping workspace

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is a creator starting social accounts with zero followers who
wants to post clips daily across promising niches. They have explicitly delegated
source, niche, timestamp, format and subtitle choices to the workflow. Their
current requested test is an IShowSpeed video with a high view count.

## Product Purpose

Turn a source video into a subtitled short with as little operator input as
possible. For the current test, success is an automatically prepared local
IShowSpeed preview, with visible progress and an honest failure state.

## Operating Context

The supported entry point is the local `clipping` FastAPI application with a
static browser workspace, SQLite persistence and a background queue consumer.
This workflow replaces n8n for the clipping task. The project also contains
older backend, frontend and connector applications with unresolved review
findings; they are not the supported entry point for this work.

## Capabilities and Constraints

- Jobs save processing checkpoints, approval decisions and artifacts.
- Downloads resume partials, cap source selection at 1080p and use four fragment
  connections. Temporary source failures continue with saved backoff; operator
  pause, cancellation and subprocess deadlines remain effective.
- A separate persistent research agent searches six niches every six hours while
  the app runs, using public YouTube search or optional official API credentials.
  It records actual source metrics and can queue a private preview from its best
  eligible result. These popularity signals do not predict viral outcomes.
- FFmpeg renders video and subtitles; yt-dlp acquires public sources;
  faster-whisper can transcribe locally. English transcription is installed.
- Automatic inference runs in an owned process with Pause/cancellation controls
  and a finite deadline. Empty or unavailable speech recognition requests timed
  subtitles while preserving the prepared source.
- The automatic test selects a saved official IShowSpeed source snapshot and
  uses transcript heuristics to choose a window. It is not a virality model.
- This environment currently refuses outbound downloader connections through
  its configured proxy. Actual IShowSpeed footage has not been acquired.
- Private previews and reward campaigns have different completion states.
  A preview does not establish campaign eligibility or permission to repost.
- Campaign publication and reward submission require real platform access and
  recorded authorization. TikTok app credentials alone are not an authorized
  social account. Those capabilities remain outside the private video test.
- The account section can start Instagram browser authorization and verify saved
  credentials. The app configuration is present, but no authorized account token
  is currently saved. Actual identity and permissions remain unverified because
  outbound access is refused. Posting stays disabled after a successful check.
- Provider-reported OAuth expiry is saved and displayed. Expired credentials
  cannot retain cached verification or be used for another account check.
  Missing/manual lifetime data stays unknown. Provider renewal remains pending
  live validation.
- The referenced TikTok metadata dataset is currently inaccessible and has not
  been imported. Synthetic demonstrations must stay visibly identified.

## Evidence on Hand

The source-check record is `.workflow-tests/ishowspeed-source-test.json`.
Local practice exports are in `storage/clipping/demos/`. Tests are in
`tests/clipping/`; research notes are in `research/`. There are no verified
earnings, promised view counts or successful IShowSpeed renders to advertise.

## Product Principles

1. Delegate routine choices instead of presenting configuration at every step.
2. Show the current task, actual progress and the next automatic action.
3. Preserve successful work across retries and restarts.
4. Clearly distinguish a private preview, a published post and a paid reward.
5. Use measured outcomes; never imply guaranteed virality or income.

## Open Decisions

Hosting, campaign membership, source permissions for publication and production
social account authorization have not been established. Future niche and daily
campaign automation should use those actual constraints rather than inventing
an eligible campaign.
