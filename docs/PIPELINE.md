# Clipping and review pipeline

1. Resume an unfinished production order or create a fresh discovery order.
2. Compare eligible public long sources by actual metadata, then apply the
   configured cheap source pre-filter before transcript work; unknown counts,
   dates and signals remain unknown. Sparse metadata alone cannot reject a source.
   A new order performs fresh discovery.
3. Fetch public captions and usable replay data before acquiring media. Candidate
   anchors combine transcript boundaries, QA openings, topic words, chapters,
   replay peaks, and explicitly supplied measured annotations where available.
4. Rank explainable candidates, apply bounded supported feedback, reject repeated
   intervals/quotes/transcripts, and enforce complete thoughts and source context.
5. If a campaign is selected, validate its source, duration, metadata and destination
   before acquisition. Add required hashtags to the separate post caption.
6. Download only selected bounded ranges, with context padding. A source failure
   never triggers full-video/full-audio fallback. Local legacy footage can be reused.
7. Transcribe locally, compare independent timed source cues when available, and
   reject gross coverage failures. Source cue agreement is not ASR self-consistency.
8. Render using saved style/framing, then strict decode/QC. Full-image fit and the
   approved studio/colorized appearances are preserved. The encoder profile changes
   only the FFmpeg preset/CRF; `balanced` keeps the previous output settings.
9. Verify output/subtitle hashes, stream formats, dimensions, duration, FPS, audio,
   black/silence detection and caption bounds. Save review frames. Human review
   remains required for meaning, speaker framing, caption taste and speech accuracy.
10. Save normalized clip records and MP4/SRT/ASS/post captions into `clips/`.
    Manual preparation can create an idempotent review package after campaign
    validation; it creates no public post.
11. Import actual performance observations, record experiments, report measured
    business metrics, and use enough independent evidence to adjust future ranking.
12. Prepare optional post descriptions and hashtags, request a timezone-aware
    posting recommendation, and add the reviewed clip to the local READY/SCHEDULED
    queue. The queue applies per-platform daily, gap, source and topic spacing.
    It has no execution path to upload or publish.

## Resume and retries

Each worker stage checkpoints paths and hashes. A changed/missing source invalidates
dependent transcription/planning/render outputs; a damaged transcript preserves a
valid source; missing or changed subtitle sidecars invalidate rendering. Campaign
approval survives artifact repair; changed clip approval is cleared.

Temporary failures use finite exponential backoff with saved due times. Restart
does not bypass backoff. Exhaustion becomes a failed saved job requiring explicit
resume/repair. Invalid configuration, access/authorization failures and validation
failures do not retry indefinitely. Cancellation and kill switch interrupt owned
media processes. `already_running` is observed rather than duplicated.

Search results, source-caption metadata/replay JSON, bounded sections and transcript
checkpoints are reused within their saved context. Deterministic source/window IDs
and hashes protect reuse. The SQLite cache uses deterministic identity keys, bounded
payloads, expiry, and content hashes for section files. Search results are scoped to
one research-run ID, so resuming that run can recover a just-fetched result while a
new order still performs fresh discovery. Fresh discovery and historical interval
exclusions take precedence over maximizing cache hits. JSON is an export/import
surface; SQLite is authoritative for order state and reservations.

## Measured business metrics

The generated-per-day metric divides saved clips by the inclusive calendar span
from the first saved clip through the latest saved clip. Average pipeline duration
sums recorded controller-run durations per order before averaging orders. Render
success rate is based on explicit render-stage start/success/failure events; an
interrupted attempt without a recorded success remains a failure in the measured
rate. Reward/hour stays unknown until imported
reward evidence can be joined to corresponding clip-level timing. Platform metrics
remain imported/manual observations, not verified API collection.
Follower conversion reports use only latest observations with known positive views
and known follower gains. Overall rates are view-weighted; missing follower or view
values stay out of the denominator. Profile visits remain null until observed.
Optional `hashtags` and `cta_used` fields attach explicitly supplied post details to
each manual/imported observation. Historical rows without those fields stay unknown.
The workspace hashtag suggestion form uses platform-specific history only after
three measured clips, shrinks tag rates toward that platform's baseline, and marks
the result for review. Associations are not causal and submitted tags are not
independently verified as public posts. No report or suggestion triggers publishing.

The growth report also shows descriptive duration, detected-hook, hashtag-group and
CTA associations only when each group reaches the three-clip minimum. Posting-time
recommendations use confirmed publication evidence when enough account observations
exist; otherwise the interface labels the configured time-window fallback.

## Evidence and statuses

READY means local artifact/preparation readiness, never PUBLISHED. Manual platform
confirmation in historical job flows records operator evidence; it is not an API
upload. Official adapters remain unavailable. The publication status vocabulary
also reserves PUBLISHING/PUBLISHED/PUBLISH_FAILED/SUBMITTED/APPROVED/REJECTED/PAID
for future verified integrations. Unknown performance/rewards remain null.
