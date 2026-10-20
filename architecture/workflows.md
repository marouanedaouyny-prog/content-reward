# Workflow Designs

**Based on:** All previous phases. Each workflow is a discrete, idempotent unit.

---

## WORKFLOW A: Discover New Campaigns

| Field | Spec |
|-------|------|
| **Trigger** | Cron: `0 */4 * * *` (every 4 hours) |
| **Inputs** | None (discovers from CR platform) |
| **Steps** | 1. Browser: Navigate to `https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/discover`<br>2. Extract campaign cards (public + application-only)<br>3. For each: fetch detail page → extract basics<br>4. Create `Campaign` records with `status=DISCOVERED`<br>5. Deduplicate by `external_campaign_id` |
| **Tools** | Browser MCP (Playwright), CR platform (no public API) |
| **API Calls** | Page navigation, DOM extraction |
| **Outputs** | `Campaign[]` (new, status=DISCOVERED) |
| **State Transitions** | — → DISCOVERED |
| **Retries** | 3x on browser error |
| **Timeout** | 300s |
| **Logs** | Campaigns discovered, duplicates skipped, errors |
| **Alerts** | If 0 campaigns found 2x consecutive (platform change?) |
| **Human Checkpoint** | None (discovery is read-only) |

---

## WORKFLOW B: Analyze Campaign Requirements

| Field | Spec |
|-------|------|
| **Trigger** | Campaign status = DISCOVERED (event-driven) |
| **Inputs** | `campaign_id` |
| **Steps** | 1. Load Campaign (DISCOVERED)<br>2. Browser: Open campaign detail page<br>3. Extract: full description, requirements list, rules, budget, platforms, deadlines, vertical<br>4. Parse → `CampaignModel` (structured JSON)<br>5. Eligibility check: budget > 0, platforms supported, deadline > now, vertical allowed<br>6. Update Campaign: `status=ANALYZED` → `ELIGIBLE` or `CLOSED` |
| **Tools** | Browser MCP, Campaign Parser Skill |
| **API Calls** | Page navigation, DOM extraction |
| **Outputs** | `CampaignModel` (parsed), Campaign status updated |
| **State Transitions** | DISCOVERED → ANALYZED → ELIGIBLE / CLOSED |
| **Retries** | 3x on browser error |
| **Timeout** | 180s |
| **Logs** | Parsed requirements, eligibility result, close reason |
| **Alerts** | If CLOSED: reason logged for review |
| **Human Checkpoint** | None (parsing is deterministic) |

---

## WORKFLOW C: Select Source Content

| Field | Spec |
|-------|------|
| **Trigger** | Campaign status = ELIGIBLE + creator joins (manual or auto) |
| **Inputs** | `campaign_id`, `creator_id` |
| **Steps** | 1. Load `CampaignModel` + `Campaign.editing_rules`<br>2. Identify source content: campaign-provided assets OR creator's library<br>3. For each source URL: create `SourceMedia` record (status=PENDING)<br>4. Queue download jobs (WORKFLOW D prerequisite) |
| **Tools** | Content Strategy Skill |
| **API Calls** | None (local decision) |
| **Outputs** | `SourceMedia[]` (PENDING), Download jobs queued |
| **State Transitions** | ELIGIBLE → ASSET_READY (when downloads complete) |
| **Retries** | N/A |
| **Timeout** | 60s |
| **Logs** | Sources identified, media records created |
| **Alerts** | If no usable source content |
| **Human Checkpoint** | Optional: `SOURCE_SELECTION_REVIEW` for high-value campaigns |

---

## WORKFLOW D: Generate Clips

| Field | Spec |
|-------|------|
| **Trigger** | `SourceMedia` status = DOWNLOADED (event-driven) |
| **Inputs** | `source_media_id`, `campaign_id` |
| **Steps** | 1. Transcribe source (`faster-whisper`) → `Transcript`<br>2. Segment detection + scoring → `ClipCandidate[]`<br>3. Per-platform selection (strategy-aware) → `ClipPlan[]`<br>4. For each plan: edit variant (FFmpeg) → `Clip` + file<br>5. Generate captions per platform → `Caption[]`<br>6. Package metadata → `PublishPackage[]`<br>7. Run Compliance QA gates → `QAReport`<br>8. If PASSED: export → `ReadyClip[]`; if FAILED: `QA_FAILED` |
| **Tools** | Video Processing Skill (yt-dlp, whisper, ffmpeg), Compliance Skill |
| **API Calls** | None (all local) |
| **Outputs** | `ReadyClip[]` (per platform) OR `QAReport` (FAILED) |
| **State Transitions** | SOURCE_READY → CLIP_CREATED → QA_PASSED / QA_FAILED |
| **Retries** | Edit: 2x (simpler filters); Transcribe: 2x (smaller model) |
| **Timeout** | 600s per clip variant |
| **Logs** | Transcript, segments, edit params, QA check results |
| **Alerts** | QA_FAILED: log failed gates, clip rejected |
| **Human Checkpoint** | Optional: `CLIP_SELECTION_REVIEW`, `CAPTION_REVIEW` |

---

## WORKFLOW E: Run Compliance QA

| Field | Spec |
|-------|------|
| **Trigger** | Clip generated (part of Workflow D) |
| **Inputs** | `clip_id`, `campaign_id`, `platform`, `caption` |
| **Steps** | 1. Load `ComplianceRules` for campaign + platform<br>2. Run 14 automated gates (duration, resolution, aspect, codec, size, disclosure, hashtags, mentions, co-posting, reused, audio, visual, platform rules, vertical)<br>3. Aggregate → `QAReport` (score 0-100)<br>4. Update Clip: `status=QA_PASSED` or `QA_FAILED` |
| **Tools** | Compliance Skill (FFmpeg + Python) |
| **API Calls** | None (all local) |
| **Outputs** | `QAReport` (pass/fail per gate, score) |
| **State Transitions** | CLIP_CREATED → QA_PASSED / QA_FAILED |
| **Retries** | N/A (deterministic) |
| **Timeout** | 120s |
| **Logs** | Every gate result with input/output |
| **Alerts** | QA_FAILED: specific gate failures |
| **Human Checkpoint** | None (automated gates only) |

---

## WORKFLOW F: Publish to Supported Social Platform

| Field | Spec |
|-------|------|
| **Trigger** | `Clip` status = QA_PASSED (event-driven) |
| **Inputs** | `clip_id`, `platform`, `social_account_id` |
| **Steps** | 1. Load `ReadyClip` + `SocialAccount` (tokens)<br>2. Check token health → refresh if needed<br>3. Upload media (resumable/chunked per platform)<br>4. Publish (poll status until `PUBLISHED` or `FAILED`)<br>5. Capture `post_url` + `platform_post_id`<br>6. Create `SocialPost` record: `status=PUBLISHED`, `post_url`, `platform_post_id`<br>7. Update Clip: `status=PUBLISHED` |
| **Tools** | Social Publishing Skill (5 platform APIs) |
| **API Calls** | OAuth refresh, media upload (chunked), publish, status poll |
| **Outputs** | `PublishResult` (success, post_url, platform_post_id, error) |
| **State Transitions** | QA_PASSED → PUBLISHED / PUBLISH_FAILED |
| **Retries** | 3x (upload/publish), exponential backoff |
| **Timeout** | 300s |
| **Logs** | Upload progress, publish response, post URL |
| **Alerts** | PUBLISH_FAILED: error code, platform, account |
| **Human Checkpoint** | **Required** for: first publish to new account, high-value clips (>$500), regulated verticals |

---

## WORKFLOW G: Capture Published URL

| Field | Spec |
|-------|------|
| **Trigger** | `SocialPost` status = PUBLISHED (event-driven) |
| **Inputs** | `social_post_id` |
| **Steps** | 1. Verify `post_url` accessible (HEAD request)<br>2. Extract `platform_post_id` from URL if not captured<br>3. Update `Submission` record: `clip_url`, `clip_id_platform`, `status=URL_CAPTURED`<br>4. Queue submission job (WORKFLOW H) |
| **Tools** | HTTP client |
| **API Calls** | HEAD `post_url` |
| **Outputs** | Submission record updated, ready for submit |
| **State Transitions** | PUBLISHED → URL_CAPTURED |
| **Retries** | 3x on HEAD failure |
| **Timeout** | 30s |
| **Logs** | URL verified, platform ID extracted |
| **Alerts** | URL inaccessible after publish (platform issue) |
| **Human Checkpoint** | None |

---

## WORKFLOW H: Submit URL to Content Rewards

| Field | Spec |
|-------|------|
| **Trigger** | `Submission` status = URL_CAPTURED (event-driven) |
| **Inputs** | `submission_id` |
| **Steps** | 1. Load Submission + Campaign + Clip + SocialPost<br>2. Browser: Navigate to CR campaign submission page<br>3. Submit `clip_url` (or Draft if Pre-post Review)<br>4. Capture `submission_id_platform` + `submitted_at`<br>5. Update Submission: `status=SUBMITTED` |
| **Tools** | Submission Skill (Browser MCP - CR has no public API) |
| **API Calls** | Browser automation on CR platform |
| **Outputs** | Submission record: `status=SUBMITTED`, `submitted_at` |
| **State Transitions** | URL_CAPTURED → SUBMITTED |
| **Retries** | 3x on browser error |
| **Timeout** | 180s |
| **Logs** | Submission response, CR platform submission ID |
| **Alerts** | SUBMISSION_FAILED: browser error, platform change |
| **Human Checkpoint** | **Required** if Pre-post Review: Brand must approve Draft first |

---

## WORKFLOW I: Track Approval/Rejection

| Field | Spec |
|-------|------|
| **Trigger** | Cron: `*/15 * * * *` (every 15 min) |
| **Inputs** | Submissions with `status IN (SUBMITTED, BOT_TRIAGE, FLAGGED, BRAND_REVIEW)` |
| **Steps** | 1. For each pending submission: Browser → CR platform → check status<br>2. Parse status: `SUBMITTED`, `BOT_TRIAGE`, `FLAGGED`, `BRAND_REVIEW`, `APPROVED`, `REJECTED`<br>3. If `APPROVED`: capture `approved_at`, `bot_score` → `VALIDATING`<br>4. If `REJECTED`: capture `rejected_at`, `rejection_reason` → terminal<br>5. If `FLAGGED`: log flag, notify human for appeal (10 biz days) |
| **Tools** | Browser MCP (CR platform) |
| **API Calls** | Browser automation |
| **Outputs** | Submission status updated, `approved_at`/`rejected_at` captured |
| **State Transitions** | SUBMITTED → BOT_TRIAGE → FLAGGED/BRAND_REVIEW → APPROVED/REJECTED |
| **Retries** | 3x on browser error |
| **Timeout** | 120s per batch |
| **Logs** | Status changes, bot scores, rejection reasons |
| **Alerts** | APPROVED: start validation tracking; REJECTED: log reason; FLAGGED: human appeal needed |
| **Human Checkpoint** | FLAGGED → appeal decision (CR Support) |

---

## WORKFLOW J: Track Views and Expected Earnings

| Field | Spec |
|-------|------|
| **Trigger** | Cron: `0 */6 * * *` (every 6 hours) + post-approval event |
| **Inputs** | Submissions with `status IN (VALIDATING, TRACKING)` |
| **Steps** | 1. For each tracking submission: get `platform`, `platform_post_id`, `social_account_id`<br>2. Call platform analytics API (read-only OAuth):<br>   - TikTok: **MANUAL_CHECKPOINT** (no API) → creator screenshot<br>   - Instagram: `GET /insights` (FB Login + perms)<br>   - Facebook: `GET /video_insights`<br>   - YouTube: `videos.list?part=statistics` (real-time) + Analytics API (detailed)<br>   - X: `GET /2/tweets` with `public_metrics` + non-public (if ≤30 days)<br>3. Store `AnalyticsSnapshot` with verified views<br>4. For CPM: calculate `expected_payout = floor(verified_views/1000) * rate_cpm` clamped to [min, max]<br>5. For Per-post: check min-view requirement in monitoring period |
| **Tools** | Analytics Skill (5 platform APIs), MANUAL_CHECKPOINT for TikTok |
| **API Calls** | Platform analytics endpoints (read-only) |
| **Outputs** | `AnalyticsSnapshot[]`, updated `expected_payout` |
| **State Transitions** | VALIDATING → TRACKING (ongoing) |
| **Retries** | 3x per platform (rate limits handled) |
| **Timeout** | 300s per batch |
| **Logs** | Views per platform, expected payout, min-view status |
| **Alerts** | CPM: approaching max_payout; Per-post: min views not met |
| **Human Checkpoint** | TikTok: creator must upload screenshot |

---

## WORKFLOW K: Track Validation and Payout

| Field | Spec |
|-------|------|
| **Trigger** | Cron: `0 */12 * * *` (every 12 hours) |
| **Inputs** | Submissions with `status IN (VALIDATING, TRACKING)` + validation window logic |
| **Steps** | 1. For each submission: check validation window end:<br>   - CPM: `approved_at + 10 days`<br>   - Per-post: `approved_at + monitoring_period`<br>   - Retainer: `cycle_end`<br>2. If window ended: query CR platform for payout status<br>3. If `PAID`: capture `payout_settled_at`, `payout_amount` → `PAID`<br>4. If `CLAWBACK`: capture reason → `CLAWBACK`<br>5. If still `VALIDATING`: continue tracking |
| **Tools** | Payout Tracking Skill (Browser MCP for CR + Whop) |
| **API Calls** | Browser automation (CR), Whop API for withdrawal status |
| **Outputs** | Submission status updated, payout recorded |
| **State Transitions** | VALIDATING/TRACKING → PAID / CLAWBACK |
| **Retries** | 5x (longer window) |
| **Timeout** | 300s |
| **Logs** | Validation window end, payout status, amount |
| **Alerts** | PAID: notify creator; CLAWBACK: escalate human |
| **Human Checkpoint** | CLAWBACK: human review required |

---

## WORKFLOW L: Recover Failed Jobs

| Field | Spec |
|-------|------|
| **Trigger** | Cron: `*/15 * * * *` (every 15 min) |
| **Inputs** | `Job` records with `status=FAILED` AND `retryable=true` AND `attempt < max_attempts` AND `next_run_at <= now()` |
| **Steps** | 1. Query failed jobs<br>2. For each: check idempotency key in external system if possible<br>   - PUBLISH: check platform post exists<br>   - SUBMIT: check CR submission exists<br>   - UPLOAD: check media exists<br>3. If external success: mark SUCCEEDED, update submission state<br>4. Else: increment attempt, reset to QUEUED, schedule retry with backoff<br>5. If max attempts reached: `DEAD_LETTER` → alert human |
| **Tools** | Recovery Skill (DB + external checks) |
| **API Calls** | Platform APIs (read), CR platform (browser) |
| **Outputs** | Jobs re-queued or dead-lettered |
| **State Transitions** | FAILED → QUEUED (retry) / DEAD_LETTER |
| **Retries** | Per job config (3-5) |
| **Timeout** | 120s |
| **Logs** | Recovery attempts, external verification results |
| **Alerts** | DEAD_LETTER: human intervention required |
| **Human Checkpoint** | DEAD_LETTER only |

---

## Workflow Dependency Graph

```
A (Discover) → B (Analyze) → C (Source) → D (Generate) → E (QA)
                                                            ↓
F (Publish) ← G (Capture URL) ← H (Submit) ← I (Track Approval)
                                                            ↓
                                              J (Track Views) → K (Track Payout)
                                                            ↓
                                                    L (Recover) [runs independently on all]
```

---

*End of Phase 7. Next: Phase 8 — Database Schema.*