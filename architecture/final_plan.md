# Final System Plan — Content Rewards Automation

**Consolidates:** Phases 0-10. This is the single source of truth for implementation.

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HERMES ORCHESTRATOR                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │  Skills     │ │  MCP        │ │  Custom     │ │  Cron       │            │
│  │  (10)       │ │  (5)        │ │  Tools (4)  │ │  (7)        │            │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│  PLATFORM     │           │  PLATFORM     │           │  PLATFORM     │
│  APIs (5)     │           │  CR (Browser) │           │  Whop         │
│  TikTok       │           │  Discover     │           │  Withdrawal   │
│  Instagram    │           │  Submit       │           │               │
│  Facebook     │           │  Approval     │           │               │
│  YouTube      │           │  Payout       │           │               │
│  X            │           │               │           │               │
└───────────────┘           └───────────────┘           └───────────────┘
```

---

## 2. Component Graph

```
HERMES
├── Skills (local orchestration)
│   ├── campaign_research          → CR Discover (browser)
│   ├── campaign_parser            → Structured CampaignModel
│   ├── content_strategy           → ClipPlan[] per platform
│   ├── video_processing           → yt-dlp + whisper + ffmpeg
│   ├── compliance                 → 14 automated gates
│   ├── social_publishing          → 5 platform APIs (OAuth)
│   ├── submission                 → CR Submit (browser)
│   ├── analytics                  → 5 platform APIs (read-only)
│   ├── payout_tracking            → CR + Whop (browser)
│   └── recovery                   → Job queue + external verification
├── MCP Servers (external tools)
│   ├── github                     → Code deployment
│   ├── filesystem                 → Config, artifacts
│   ├── sqlite                     → State, audit
│   ├── browser (playwright)       → CR automation
│   └── docker                     → Isolated processing
├── Custom Tools (binary/deterministic)
│   ├── ffmpeg_wrapper.py          → Transcode, QA probes
│   ├── whisper_transcribe.py      → Transcription
│   ├── ytdlp_download.py          → Video download
│   └── hasher.py                  → SHA-256 deduplication
└── Cron Jobs (scheduled workflows)
    ├── campaign_discovery (4h)    → WORKFLOW A
    ├── submission_status (15m)    → WORKFLOW I
    ├── analytics_sync (6h)        → WORKFLOW J
    ├── token_health (1h)          → Token refresh
    ├── payout_check (12h)         → WORKFLOW K
    ├── failed_job_recovery (15m)  → WORKFLOW L
    └── compliance_audit (daily)   → Policy scan
```

---

## 3. Data Flow (End-to-End)

```
CRON A (4h): Discover
    │
    ▼
Campaign DISCOVERED
    │
    ▼
WORKFLOW B: Analyze → CampaignModel (ANALYZED → ELIGIBLE/CLOSED)
    │
    ▼
WORKFLOW C: Source → SourceMedia[] (ASSET_READY)
    │
    ▼
WORKFLOW D: Generate → Clip[] + Caption[] (CLIP_CREATED)
    │
    ▼
WORKFLOW E: QA → QAReport (QA_PASSED / QA_FAILED)
    │
    ▼
WORKFLOW F: Publish → SocialPost[] (PUBLISHED / PUBLISH_FAILED)
    │
    ▼
WORKFLOW G: Capture URL → Submission (URL_CAPTURED)
    │
    ▼
WORKFLOW H: Submit → Submission (SUBMITTED)
    │
    ▼
CRON I (15m): Track Approval → APPROVED/REJECTED/FLAGGED
    │
    ▼
CRON J (6h): Analytics Sync → AnalyticsSnapshot[] (TRACKING)
    │
    ▼
CRON K (12h): Payout Check → PAID / CLAWBACK
    │
    ▼
CRON L (15m): Recovery → Retry / Dead Letter
```

---

## 4. State Machine (Submission)

```text
DRAFT → SUBMITTED → BOT_TRIAGE → (FLAGGED → human) → BRAND_REVIEW
                                                        ↓
                                               APPROVED → VALIDATING → TRACKING
                                                        ↓                    ↓
                                                   PAID ◄────────────── CLAWBACK
                                                        ↓
                                                     REJECTED (terminal)
```

**Idempotency Keys on Every External Call:**
| Action | Key Format |
|--------|------------|
| Upload | `upload:{clip_hash}:{platform}` |
| Publish | `publish:{clip_id}:{platform}:{account_id}` |
| Submit | `submit:{campaign_id}:{creator_id}:{clip_url_hash}` |
| Analytics | `analytics:{submission_id}:{platform}:{date}` |
| Payout | `payout:{submission_id}:{validation_window_end}` |

---

## 5. Social Connector Architecture

| Platform | Upload | Publish | Post URL | Analytics | Verdict |
|----------|--------|---------|----------|-----------|---------|
| **TikTok** | ✅ Resumable | ✅ Direct/Inbox | ✅ share_url | 🔴 MANUAL | Automate publish; manual views |
| **Instagram** | ✅ Container | ✅ media_publish | ✅ permalink | ⚠️ FB Login only | Full auto with FB Login |
| **Facebook** | ✅ Resumable | ✅ Video API | ✅ permalink_url | ✅ video_insights | **Fully automatable** |
| **YouTube** | ✅ Resumable | ✅ videos.insert | ✅ watch?v={id} | ✅ Data + Analytics API | **Fully automatable** |
| **X** | ✅ Chunked | ✅ tweets.create | ✅ status URL | ⚠️ Public ✅, Private 30d | Automate; sync daily |

**OAuth Flows:** All 5 use OAuth 2.0 + PKCE (recommended). Tokens encrypted at rest (Fernet), auto-refreshed 2hr before expiry.

---

## 6. Content Pipeline

```
SOURCE URL
    ↓ (yt-dlp + hash)
SourceMedia
    ↓ (faster-whisper)
Transcript
    ↓ (segment + score)
ClipCandidate[]
    ↓ (per-platform select)
ClipPlan[]
    ↓ (FFmpeg: trim, crop, captions, branding, normalize)
Clip[] (5 variants)
    ↓ (LLM caption + required tags/mentions/disclosure)
Caption[]
    ↓ (14 automated gates)
QAReport
    ↓ (export)
ReadyClip[] → PUBLISH QUEUE
```

**All local, $0 cost. No paid APIs.**

---

## 7. Compliance Layer

**14 Automated Gates (every clip, every platform):**
1. DURATION 2. RESOLUTION 3. ASPECT_RATIO 4. CODEC 5. FILE_SIZE
6. DISCLOSURE (FTC) 7. HASHTAGS 8. MENTIONS 9. COPOSTING
10. REUSED_CONTENT 11. AUDIO_LEVEL 12. VISUAL_QUALITY
13. PLATFORM_RULES 14. REGULATED_VERTICAL/POLITICAL

**Human Gates (configurable):**
- CLIP_SELECTION_REVIEW (>$500/clip)
- CAPTION_REVIEW (regulated verticals)
- PRE_PUBLISH_REVIEW (>$500, first publish to account)

**NEVER Automated (Terms §12.2):**
- Bot views, view farms, click farms, engagement pods, artificial inflation

---

## 8. Error Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Upload failed | Job FAILED | Retry 3x (30s, 120s, 600s) |
| Publish failed | Job FAILED | Retry 3x; alert human if PPA/2FA |
| Submit failed | Job FAILED | Retry 3x; then MANUAL_CHECKPOINT |
| Token expired | Pre-check / 401 | Auto-refresh; alert if revoked |
| Bot flagged | State=FLAGGED | Human appeal (10 biz days) |
| Validation failed | CR payout check | Log, reverse reserved budget |
| Dead letter | Max retries | Human intervention |

**Restart Safety:** All jobs use idempotency keys. On restart: query `jobs` for non-terminal states → verify externally → resume or re-queue.

---

## 9. Cron Jobs

| Job | Schedule | Workflow | Critical |
|-----|----------|----------|----------|
| campaign_discovery | `0 */4 * * *` | A | New campaigns |
| submission_status | `*/15 * * * *` | I | Approval tracking |
| analytics_sync | `0 */6 * * *` | J | View verification |
| token_health | `0 * * * *` | — | Prevent auth failures |
| payout_check | `0 */12 * * *` | K | Revenue realization |
| failed_job_recovery | `*/15 * * * *` | L | Self-healing |
| compliance_audit | `0 2 * * *` | — | Policy enforcement |

---

## 10. MCP Integrations

| MCP | Purpose |
|-----|---------|
| GitHub | Deploy skill updates, version control |
| Filesystem | Read/write config, logs, artifacts |
| SQLite | State machine, audit logs, job queue |
| Browser (Playwright) | CR platform automation (no API) |
| Docker | Isolated FFmpeg/whisper containers |

---

## 11. Hermes Skills (10)

| Skill | Wraps | Entry Point |
|-------|-------|-------------|
| campaign_research | CR Discover (browser) | `discover() → Campaign[]` |
| campaign_parser | NLP + rules | `parse(campaign) → CampaignModel` |
| content_strategy | Transcript + rules | `plan(source, campaign) → ClipPlan[]` |
| video_processing | yt-dlp, whisper, ffmpeg | `process(source, plan) → ReadyClip[]` |
| compliance | FFmpeg + Python rules | `check(clip, campaign) → QAReport` |
| social_publishing | 5 platform APIs | `publish(ready_clip) → PublishResult` |
| submission | CR Submit (browser) | `submit(campaign, url) → SubmissionResult` |
| analytics | 5 platform APIs (read) | `sync(submission) → AnalyticsSnapshot` |
| payout_tracking | CR + Whop (browser) | `check_payout(submission) → PayoutStatus` |
| recovery | Job queue + external | `recover() → RecoveredJob[]` |

---

## 12. Required Manual Checkpoints

| Checkpoint | When | Who |
|------------|------|-----|
| **TikTok Analytics** | Every CPM submission | Creator (screenshot) |
| **First Publish to Account** | New social_account_id | Operator |
| **High-Value Clip (>$500)** | Before publish | Operator |
| **Regulated Vertical Caption** | Crypto/Finance/Supplements/Gambling/Political | Compliance |
| **Pre-post Review (Draft)** | Campaign enables | Brand moderator |
| **FLAGGED Appeal** | Bot Score ≥ threshold | CR Support |
| **DEAD_LETTER Job** | Max retries exceeded | Operator |

---

## 13. Security Model

- **OAuth tokens:** Fernet encrypted at rest, auto-refreshed, revocable
- **Secrets:** `.env` only (gitignored), never in logs/DB
- **Scopes:** Least privilege (read-only for analytics, write only for publish)
- **Audit log:** Every sensitive action (redacted tokens)
- **Account isolation:** Per-creator, per-platform
- **Sanctions screening:** OFAC SDN at onboarding
- **Data retention:** YouTube ≤30 days (auto-purge), Analytics 2yr, Payouts 7yr

---

## 14. Cost Model

| Category | MVP | Scale |
|----------|-----|-------|
| Infrastructure | $0 (local) | $0-50/mo |
| Platform APIs | $0 (free tiers) | $0-100/mo |
| LLM Inference | $0 (NVIDIA/OpenRouter free) | $0 |
| CR Platform Fees | 0-10% revenue | 0-10% revenue |
| **Automation Overhead** | **$0** | **$0-150/mo** |

---

## 15. MVP Scope (Phase 1)

**Must Have:**
- [ ] Campaign discovery (browser) → DISCOVERED
- [ ] Campaign parser → CampaignModel (ELIGIBLE)
- [ ] Source download (yt-dlp) → SourceMedia
- [ ] Transcribe (faster-whisper) → Transcript
- [ ] Segment + ClipPlan (vertical 9:16) → ClipPlan[]
- [ ] Edit (FFmpeg) → Clip variants (TT, IG, YT, X)
- [ ] Caption (template + required tags) → Caption[]
- [ ] QA (14 gates) → QA_PASSED
- [ ] Publish (TikTok + Instagram + YouTube) → SocialPost
- [ ] Submit URL (browser) → SUBMITTED
- [ ] Track approval (cron) → APPROVED/REJECTED
- [ ] Analytics sync (YT, FB, IG, X) → AnalyticsSnapshot
- [ ] TikTok manual checkpoint → MANUAL
- [ ] Payout check (cron) → PAID
- [ ] State machine + idempotency + audit logs
- [ ] Token encryption + auto-refresh
- [ ] Recovery cron

**Nice to Have (Phase 2):**
- [ ] Facebook publishing
- [ ] Retainer campaign support
- [ ] Pre-post Review (Draft) flow
- [ ] Multi-creator support
- [ ] Web dashboard (Hermes dashboard)
- [ ] Telegram/Discord notifications

**Phase 3:**
- [ ] X (Twitter) publishing
- [ ] Advanced clip strategies (ML-based)
- [ ] Batch campaign processing
- [ ] Whop withdrawal automation
- [ ] Multi-language support

---

## 16. Blockers & Required Credentials

### Blockers (Must Resolve Before Implementation)
1. **Content Rewards API:** No public API → requires browser automation (Playwright)
2. **TikTok Analytics:** No official API → MANUAL_CHECKPOINT required
3. **Instagram Insights:** Requires FB Login + Business Verification + App Review (weeks)
4. **YouTube Quota:** 100 uploads/day limit → audit needed for scale
5. **X API Free Tier:** 500 posts/mo → upgrade needed for volume

### Required Credentials (Before Launch)
```env
# Platform OAuth
TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=
INSTAGRAM_CLIENT_ID=          # via FB Login
INSTAGRAM_CLIENT_SECRET=
FACEBOOK_CLIENT_ID=
FACEBOOK_CLIENT_SECRET=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
X_CLIENT_ID=
X_CLIENT_SECRET=

# Content Rewards (browser automation)
CR_EMAIL=
CR_PASSWORD=

# Whop (payouts)
WHOP_API_KEY=

# Security
TOKEN_ENCRYPTION_PASSWORD=    # 32+ chars
TOKEN_ENCRYPTION_SALT=        # unique per deploy
API_KEY=                      # Hermes auth

# LLM (free tiers)
NVIDIA_API_KEY=
OPENROUTER_API_KEY=
```

### Platform App Setup Required
| Platform | Steps | Timeline |
|----------|-------|----------|
| **TikTok** | Create app → Content Posting API → Audit for public | 1-2 weeks |
| **Instagram** | FB App → Business Verification → App Review (Advanced) | 2-4 weeks |
| **Facebook** | Same as IG | Included |
| **YouTube** | Google Cloud → YouTube Data API v3 → OAuth verification | 1-2 weeks |
| **X** | Developer Portal → Project + App → Basic tier ($100/mo if needed) | 1 week |

---

## 17. Implementation Order

```
Week 1-2: Foundation
  ├── Database schema (SQLite + migrations)
  ├── Token encryption + OAuth flows (5 platforms)
  ├── Job queue + idempotency framework
  └── Audit logging

Week 3-4: Content Pipeline
  ├── yt-dlp download + hash deduplication
  ├── faster-whisper transcription
  ├── Segment detection + ClipPlan
  ├── FFmpeg editing (5 variants)
  ├── Caption generation (template)
  └── QA gates (14 checks)

Week 5-6: Publishing & Submission
  ├── Social Publishing Skill (5 platforms)
  ├── Browser automation for CR Submit
  ├── State machine implementation
  └── Idempotency on all external calls

Week 7-8: Tracking & Recovery
  ├── Analytics sync (4 auto + 1 manual)
  ├── Approval tracking cron
  ├── Payout tracking cron
  ├── Failed job recovery cron
  └── Compliance audit cron

Week 9-10: Polish & Deploy
  ├── Hermes skills packaging
  ├── Config.yaml + cron registration
  ├── End-to-end test (dry-run)
  ├── Security audit
  └── Documentation
```

---

## 18. Success Criteria (MVP)

- [ ] Discover → Publish → Submit → Approve → Payout works for 1 campaign
- [ ] Zero duplicate publishes/submissions on restart
- [ ] All 14 QA gates pass on test clips
- [ ] Token auto-refresh works for all 5 platforms
- [ ] TikTok manual checkpoint documented and tested
- [ ] Audit log captures every sensitive action
- [ ] Cost: $0 automation overhead
- [ ] Recovery cron handles 3 failure types

---

*This plan is complete. All research evidence cited in `research/`. All architecture decisions documented in `architecture/`. All workflows specified in `workflows/`. Ready for implementation.*