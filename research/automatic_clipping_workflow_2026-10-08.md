# Automatic source-to-clips workflow research

Researched October 8, 2026 against first-party documentation. Scope: the automatic IShowSpeed local test and the constraints on extending it to Content Rewards. This report records research, not a successful media download or a connected social account.

## Recommended operator experience

An empty-input **Run IShowSpeed test** action can select the source, acquire the real media, transcribe it locally, choose a complete speech window, create timed subtitles, render a vertical MP4, run technical checks, and expose the finished local preview. Persist every stage and bounded retry time so the operator does not choose timestamps, subtitles, format, or a caption. Display the actual source and processing state; acquisition failure must never produce invented footage or a synthetic result labeled IShowSpeed.

For daily reward work, extend source selection to an eligible campaign's approved assets. Automatic preparation and automatic public posting are different capabilities. The current test needs no platform credential; future publication needs the account owner's authorization and the platform's required controls. A source's popularity does not establish rights, campaign eligibility, clip quality, or expected earnings.

## Source selection and ranking

The selected public upload is **I Met Cristiano Ronaldo**, video ID `Uv1PyE8J38w`, published June 17, 2023 by the verified IShowSpeed account. The YouTube search result inspected on this date reports **347,628,460 views**. Direct page retrieval subsequently failed, so this is a dated metadata snapshot rather than a fresh media inspection. Label it **highest-viewed among checked official videos**, not proven highest across the entire channel. [Official upload](https://www.youtube.com/watch?v=Uv1PyE8J38w).

For later automatic refreshes, YouTube Data API `search.list` supports a channel filter, video-only results and descending `viewCount`. Google warns that non-relevance ordering can produce incomplete results; channel-filtered searches also have a 500-video limitation in the documented configuration. A bounded query is a ranking of retrieved candidates, not a completeness proof. Store candidate provenance, observation time and selection basis. [YouTube search API](https://developers.google.com/youtube/v3/docs/search/list).

## Acquisition and local transcription

yt-dlp provides JSON metadata with download suppression, playlist controls, socket timeouts and separate HTTP, extractor, fragment and file-access retry settings. HTTP and fragment retry defaults are 10; changing only HTTP retries leaves the fragment default intact. Use finite retries and an application-level deadline. Missing fragments should fail acquisition when the workflow requires a complete source. `--download-sections` accepts explicit time ranges and requires FFmpeg; use it only after a source window has been determined. Source metadata alone is not downloaded media. [Official yt-dlp options](https://github.com/yt-dlp/yt-dlp/blob/master/README.md).

Suggested preview acquisition controls:

```text
--ignore-config --no-playlist --socket-timeout 10
--retries 1 --extractor-retries 1 --fragment-retries 1
--abort-on-unavailable-fragments
```

Keep job-level backoff persisted outside the downloader. Check source existence, actual duration and decoded streams before accepting the checkpoint. A network restriction is a visible retry/failure state, not a reason to disable transport verification or silently change footage.

faster-whisper supports CPU `int8`, timestamped segments and optional word timestamps. Its segment iterator must be consumed for inference to run. VAD filters non-speech; model names trigger Hugging Face downloads, while a converted local directory can load locally. The existing English preview can use the cached English model without asking the operator for SRT. Transcription does not perform visual event detection, speaker tracking or viral prediction. Reject absent speech or invalid timed segments instead of inventing dialogue. FFmpeg is still required by this project's rendering stage even though faster-whisper decodes audio through bundled PyAV libraries. [faster-whisper README](https://github.com/SYSTRAN/faster-whisper).

The constructor exposes `local_files_only=True` to avoid model acquisition during a job. Its source identifies English-only models and reports their supported language as English. Pin a complete cached model and make missing-model readiness visible before queuing work. [faster-whisper model loader](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py).

## TikTok publication constraints

Direct Post requires an enabled product, approval of `video.publish`, authorization of that scope by the target user, and that user's access token/open ID. A developer client key and secret alone are insufficient. Unaudited clients' posts are private; public visibility requires the separate API-client audit. [Direct Post setup](https://developers.tiktok.com/docs/en/content-posting-api-get-started).

TikTok requires current creator information, a preview, editable preset captions, express upload consent, manually selected privacy without a default, and interactions disabled by default. Unaudited clients are limited to private accounts and `SELF_ONLY`. Its intended-use rules reject copying arbitrary other-platform content and a private utility limited to the operator's accounts. Therefore a zero-choice **local preview** is compatible with this product direction; promising zero-choice TikTok publication through this API would conflict with its documented publishing experience. [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines).

The web Login Kit requires a registered static HTTPS redirect URI, a unique anti-forgery state retained across authorization, callback state validation and secure token management. Do not assign unsolicited callbacks to a default user. [Web Login Kit](https://developers.tiktok.com/docs/en/login-kit-web).

Provider-specific PKCE matters: TikTok's **desktop** documentation requires a retained verifier and specifies a **hex-encoded SHA-256** challenge. Do not implement generic base64url PKCE for TikTok without checking the configured client type; the web guide inspected here does not list that desktop parameter set. [Desktop Login Kit](https://developers.tiktok.com/docs/en/login-kit-desktop).

## Current Content Rewards and Whop handoff

The current creator flow is discover/join a campaign, post to its required platform, and submit the public link within the documented deadline. Some campaigns require applying. The current FAQ says the brand or manager reviews every submission. A local MP4 is not a published post or an approved submission. [Current creator FAQ](https://contentrewards.com/creators).

V2 adds optional **pre-post review**: creators upload the raw draft, receive approval/rejection/change requests, and revise before publication. Its organization and campaign permissions are distinct from the former experience-level model. Keep draft approval separate from the later published submission and reward state. [V2 release](https://contentrewards.com/articles/v2-is-here).

The October 4, 2026 terms distinguish new campaigns from legacy Whop-hosted campaigns. Brand-provided assets grant a campaign-limited license; third-party rights, including music, must be cleared. Earnings depend on approval, verified views, the campaign model and validation. No views or earnings are guaranteed. Public IShowSpeed footage is not automatically an approved asset for a paid campaign. [Current creator terms](https://contentrewards.com/terms).

Do not assume automatic approval: current organization terms say a submission remains pending until reviewed. The older Whop article describes automatic approval after 48 hours; that older behavior must not be transferred to the current product. [Current organization terms](https://contentrewards.com/brands-terms), [older Whop setup article](https://whop.com/blog/set-up-content-rewards/).

No documented, authenticated **creator Content Rewards submission endpoint** was verified in this research. Whop's general developer documentation is not proof of such an endpoint. Preserve a real submission link/package handoff until a provider-supported integration contract is verified; do not invent `/content-rewards/submissions` or treat general payment/bounty APIs as equivalent. This is a research limitation, not a claim that no private API exists. [Whop documentation index](https://docs.whop.com/llms.txt).

## Implementation corrections identified

Observed in `clipping/media.py` while the parent implementation was in progress:

- Set fragment retries explicitly alongside HTTP/extractor retries and reject unavailable fragments. Preserve the existing application deadline.
- Ensure subprocess timeout/cancellation terminates any downloader-launched FFmpeg process, not only its direct parent.
- Keep the cached English ASR selection automatic for this preset; consume its segments, validate timestamps and fail honestly on absent speech.
- Persist retry attempts/backoff and distinguish exhausted acquisition from completed rendering. User-facing status must say **local preview**, never published or submitted without an actual verified handoff.
- Keep daily eligible-campaign selection as an explicit next capability if this change ships only the IShowSpeed preset. A fixed dated source proves the no-form test, not autonomous discovery across every niche.

No credentials were read, OAuth exchange attempted, accounts accessed, messages sent, content published or reward submissions made during this research.
