# Automatic IShowSpeed preview

The operator has requested an IShowSpeed test without source, niche, timestamp,
format, caption, subtitle, or approval choices. This change adds a private local
preview recipe to the supported `clipping` app.

1. Add an empty-input run endpoint and preset. The recipe selects the highest
   view count among the official videos checked on October 8, 2026: `I Met
   Cristiano Ronaldo`, https://www.youtube.com/watch?v=Uv1PyE8J38w. The snapshot
   records 347,628,460 views; it is not a live ranking of the entire channel.
2. Queue real-media preview jobs immediately, then transcribe with the installed
   English model, select a transcript window, render vertical subtitles, check
   the resulting MP4, and finish at a downloadable local preview. A preview is
   separate from campaign, publication, submission, and reward processing.
3. Persist bounded download retries with backoff and resume saved checkpoints.
   Network restrictions remain in force. Never substitute synthetic footage or
   invent subtitles when acquiring the actual source fails.
4. Expose a prominent preset button without a form. Display the selected source,
   progress, retry time, finished preview and failures.
5. Verify empty-input API dispatch, no approval handoffs for previews, preserved
   campaign approval gates, cancellation, kill switch, idempotency, persisted
   retry timing, native FFmpeg output, and the UI interactions. Run a real
   IShowSpeed job and report the observed outcome.

No credentials or new provider API keys are needed for the public source. This
does not establish permission to publish the footage or submit it to a reward
campaign. Daily campaign selection and live publishing are outside this test.
