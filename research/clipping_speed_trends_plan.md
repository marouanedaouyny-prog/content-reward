# Download resilience and trend discovery

Requested 2026-10-10: faster acquisition, continued operation after temporary
failures, and an automatic viral/trending research agent with its own section.

1. Cap source selection at 1080p; enable four DASH/HLS fragment connections,
   explicit partial-file resume, bounded downloader retries and a realistic
   per-attempt deadline. Reuse complete source artifacts after interruption.
2. Persist recurring backoff for temporary failures on both preview and approved
   campaign jobs. Keep permanent failures visible; preserve checkpoints and
   approvals. Stop child processes on Pause, cancellation or shutdown.
3. Add an independent, persistent trend agent. Search recent YouTube uploads
   across six niches. Prefer the official API when YOUTUBE_API_KEY is configured;
   otherwise use bounded yt-dlp public searches. Save evidence, timestamps,
   transparent ranking and failure states; refresh automatically while the app
   runs. Never fabricate live results or guarantee virality.
4. Extend the existing workspace with a readable research queue/results section,
   last/next scan state and actions to carry a source into the campaign form or
   prepare a private preview. Publication approvals remain in effect.
5. Verify meaningful download/retry/cancellation, discovery/persistence/ranking,
   API and UI interactions, then document operating limits and researched tools.

No Git baseline exists. The supported application is clipping/, not the older
backend/Next.js/social connector. External downloader access remains subject to
the configured network restrictions; changing options cannot restore connectivity.
