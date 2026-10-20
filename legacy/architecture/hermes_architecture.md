# Hermes Architecture

**Based on:** `research/content_rewards.md`, `research/social_api_matrix.md`, `architecture/*.md`

---

## 6.1 System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        HERMES ORCHESTRATOR                       │
│  (Campaign discovery, state machine, cron, skills, MCP, agents) │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  SKILLS       │    │  MCP SERVERS  │    │  CUSTOM TOOLS │
│  (CLI/API)    │    │  (External)   │    │  (Binary)     │
└───────────────┘    └───────────────┘    └───────────────┘
```

---

## 6.2 Hermes Skills (Local Orchestration)

| Skill | Purpose | Wraps | Interface |
|-------|---------|-------|-----------|
| **campaign_research** | Discover & analyze campaigns | CR platform (browser/API) | `discover() → Campaign[]`, `analyze(campaign_id) → CampaignModel` |
| **campaign_parser** | Parse requirements → structured object | NLP + rules | `parse(campaign) → ComplianceRules` |
| **content_strategy** | Select source, plan clips | Transcript + campaign rules | `plan(source, campaign) → ClipPlan[]` |
| **video_processing** | Download, transcribe, edit, QA | yt-dlp, whisper, ffmpeg | `process(source, plan) → ReadyClip[]` |
| **compliance** | Automated gates | FFmpeg + Python rules | `check(clip, campaign) → QAReport` |
| **social_publishing** | Upload, publish, get URL | Platform APIs (5) | `publish(ready_clip) → PublishResult` |
| **submission** | Submit URL to CR | CR platform (browser/API) | `submit(campaign, url) → SubmissionResult` |
| **analytics** | Sync views/engagement | Platform APIs (read-only) | `sync(submission) → AnalyticsSnapshot` |
| **payout_tracking** | Check validation, payouts | CR platform + Whop | `check_payout(submission) → PayoutStatus` |
| **recovery** | Retry, restart, dead-letter | Internal DB + external checks | `recover() → RecoveredJob[]` |

---

## 6.3 MCP Servers (External Tools)

| MCP Server | Purpose | When to Use |
|------------|---------|-------------|
| **GitHub** | Code changes, PRs, issues | Deploying skill updates, version control |
| **Filesystem** | Read/write local files | Config, logs, artifacts |
| **SQLite/PostgreSQL** | Database operations | State machine, audit logs |
| **Browser (Playwright)** | CR platform automation (no API) | Campaign discovery, submission, payout check |
| **Docker** | Run FFmpeg/whisper containers | Isolated video processing |

---

## 6.4 Custom Tools (Binary/Deterministic)

| Tool | Purpose | Why Not Skill/MCP |
|------|---------|-------------------|
| **FFmpeg wrapper** | Video transcoding, QA probes | Binary, needs GPU/CPU, streaming I/O |
| **faster-whisper** | Transcription | ML model, GPU acceleration |
| **yt-dlp** | Video download | Complex CLI, frequent updates |
| **SHA-256 hasher** | File deduplication | Deterministic, high-throughput |

---

## 6.5 Cron Jobs (Scheduled Workflows)

| Cron | Schedule | Workflow | Purpose |
|------|----------|----------|---------|
| **campaign_discovery** | Every 4 hours | WORKFLOW A | Find new campaigns |
| **submission_status** | Every 15 min | WORKFLOW I | Check approval/rejection |
| **analytics_sync** | Every 6 hours | WORKFLOW J | Sync views for tracking |
| **token_health** | Every 1 hour | — | Refresh expiring tokens |
| **payout_check** | Every 12 hours | WORKFLOW K | Check validation → payout |
| **failed_job_recovery** | Every 15 min | WORKFLOW L | Retry failed jobs |
| **compliance_audit** | Daily | — | Scan for policy violations |

---

## 6.6 Agent Roles (Hermes Multi-Agent)

| Agent | Role | Trigger | Output |
|-------|------|---------|--------|
| **Researcher** | Campaign discovery, platform changes | Cron + manual | New campaigns, API updates |
| **Planner** | Campaign analysis, clip strategy | Campaign → ELIGIBLE | ClipPlan[], ComplianceRules |
| **Builder** | Video processing, editing | ClipPlan → READY | ReadyClip[] |
| **QA** | Compliance gates | ReadyClip → QA_PASSED/FAILED | QAReport |
| **Publisher** | Upload + publish to platforms | QA_PASSED → PUBLISHED | PublishResult (URL, platform ID) |
| **Analytics** | View/engagement sync | Cron + post-publish | AnalyticsSnapshot |
| **Fixer** | Error recovery, retries | Failed jobs → RECOVERED | RecoveredJob[] |

**Message Bus:** Hermes `MessageBus` (SQLite-backed) for inter-agent communication.

---

## 6.7 Data Flow (Hermes as Orchestrator)

```
CRON: campaign_discovery (4h)
    ↓
Researcher: discover() → Campaign[] (NEW)
    ↓
Planner: analyze() → CampaignModel (ANALYZED → ELIGIBLE)
    ↓
Planner: plan() → ClipPlan[] (ASSET_READY)
    ↓
Builder: process() → ReadyClip[] (CLIP_CREATED → QA_PASSED)
    ↓
QA: check() → QAReport (QA_PASSED / QA_FAILED)
    ↓
Publisher: publish() → PublishResult (PUBLISHED → URL_CAPTURED)
    ↓
Submission: submit() → SubmissionResult (SUBMITTED)
    ↓
CRON: submission_status (15m) → BRAND_REVIEW → APPROVED/REJECTED
    ↓
CRON: analytics_sync (6h) → TRACKING → VALIDATING
    ↓
CRON: payout_check (12h) → PAID / CLAWBACK
```

---

## 6.8 Skill Implementation Pattern

```python
# skills/campaign_research/skill.py
class CampaignResearchSkill:
    def __init__(self, db: Session, browser: BrowserMCP):
        self.db = db
        self.browser = browser
    
    def discover(self) -> List[Campaign]:
        # 1. Browser: navigate to CR Discover page
        # 2. Extract campaign cards (public + application)
        # 3. For each: create Campaign record (DISCOVERED)
        # 4. Return new campaigns
    
    def analyze(self, campaign_id: str) -> CampaignModel:
        # 1. Browser: open campaign detail
        # 2. Extract: requirements, rules, budget, platforms, deadlines
        # 3. Parse → CampaignModel (structured)
        # 4. Update Campaign status → ANALYZED
        # 5. Eligibility check → ELIGIBLE or CLOSED

# skills/video_processing/skill.py
class VideoProcessingSkill:
    def __init__(self, ffmpeg: FFmpegTool, whisper: WhisperTool, ytdlp: YtDlpTool):
        self.ffmpeg = ffmpeg
        self.whisper = whisper
        self.ytdlp = ytdlp
    
    def process(self, source: SourceMedia, plan: ClipPlan) -> List[ReadyClip]:
        # 1. Download (if URL) → SourceMedia.local_path
        # 2. Transcribe → Transcript
        # 3. Segment + score → ClipCandidate[]
        # 4. Select per platform → ClipPlan[]
        # 5. Edit each variant → Clip[]
        # 6. Caption per platform → Caption[]
        # 7. QA gates → QAReport
        # 8. Export ready → ReadyClip[]
```

---

## 6.9 Configuration (config.yaml)

```yaml
hermes:
  skills:
    - campaign_research
    - campaign_parser
    - content_strategy
    - video_processing
    - compliance
    - social_publishing
    - submission
    - analytics
    - payout_tracking
    - recovery
  
  cron:
    campaign_discovery: "0 */4 * * *"
    submission_status: "*/15 * * * *"
    analytics_sync: "0 */6 * * *"
    token_health: "0 * * * *"
    payout_check: "0 */12 * * *"
    failed_job_recovery: "*/15 * * * *"
  
  mcp:
    github: true
    filesystem: true
    sqlite: true
    browser: true
    docker: true
  
  limits:
    concurrent_edits: 2
    max_retry_attempts: 3
    token_refresh_threshold_hours: 2
    analytics_sync_window_days: 30
  
  human_gates:
    clip_selection_review_threshold: 500  # $ per clip
    caption_review_verticals: [CRYPTO, FINANCE, SUPPLEMENTS, GAMBLING, POLITICAL]
    pre_publish_review_threshold: 500
```

---

## 6.10 Directory Structure

```
project/
├── research/
│   ├── content_rewards.md
│   ├── social_api_matrix.md
│   └── cost_matrix.md
├── architecture/
│   ├── campaign_model.md
│   ├── content_pipeline.md
│   ├── compliance_engine.md
│   ├── state_machine.md
│   ├── hermes_architecture.md
│   ├── database.md
│   ├── security.md
│   └── final_plan.md
├── workflows/
│   ├── A_discover.md
│   ├── B_analyze.md
│   ├── C_source.md
│   ├── D_generate.md
│   ├── E_qa.md
│   ├── F_publish.md
│   ├── G_capture_url.md
│   ├── H_submit.md
│   ├── I_track_approval.md
│   ├── J_track_views.md
│   ├── K_track_payout.md
│   └── L_recover.md
├── skills/
│   ├── campaign_research/
│   ├── campaign_parser/
│   ├── content_strategy/
│   ├── video_processing/
│   ├── compliance/
│   ├── social_publishing/
│   ├── submission/
│   ├── analytics/
│   ├── payout_tracking/
│   └── recovery/
├── scripts/
│   ├── ffmpeg_wrapper.py
│   ├── whisper_transcribe.py
│   ├── ytdlp_download.py
│   └── hasher.py
├── db/
│   ├── models.py
│   ├── migrations/
│   └── seed.py
└── config.yaml
```

---

*End of Phase 6. Next: Phase 7 — Workflow Design.*