# Automation Empire OS — PRD

**Version:** 1.0
**Date:** 2026-09-27
**Budget:** $0 hard cap
**Owner:** Solo operator
**Build style:** Vibe coding + AI coding agents + deterministic workers
**Primary goal:** Build a local-first automation operating system that can run many independent revenue workflows from one control plane.

---

## 0. Executive Definition

Build one modular system, not 50 disconnected scripts.

The system discovers opportunities → analyzes them → executes workflows → verifies results → records state → tracks revenue → learns from results → creates new jobs.

Initial vertical:

```text
Content Rewards automation
```

Future verticals:

```text
lead generation
web scraping
affiliate research
SEO/content
product research
job monitoring
competitor monitoring
ecommerce operations
freelance operations
micro-SaaS operations
```

Hard budget rule:

```text
Monthly cash spend must remain $0.
```

No architecture may depend on a paid API, paid hosting, paid DB, paid proxy, paid automation platform, paid model, or paid storage service to function.

Free cloud services are optional accelerators, never hard dependencies.

Local software is the default.

---

# 1. Product Vision

## 1.1 Problem

Automation projects usually become:

```text
script
→ another script
→ cron
→ random JSON files
→ duplicated credentials
→ broken retries
→ no state
→ no observability
→ impossible maintenance
```

This project replaces that structure with one reusable operating layer.

## 1.2 Vision

```text
              EMPIRE OS
                  |
        +---------+---------+
        |         |         |
     DISCOVER   BUILD    DISTRIBUTE
        |         |         |
     signals   workers   channels
        |         |         |
        +---------+---------+
                  |
              ANALYTICS
                  |
              REVENUE
                  |
              REINVEST
                  |
          NEW AUTOMATIONS
```

## 1.3 Core principle

Use code for deterministic work.

Use AI for:

```text
classification
planning
research synthesis
text generation
vision interpretation
anomaly analysis
workflow proposal
```

Never make an LLM the source of truth for state, money, IDs, permissions, retries, or irreversible actions.

---

# 2. Goals

## 2.1 Primary goals

1. Run many automation workflows from one control panel.
2. Share infrastructure across workflows.
3. Keep all important state persistent.
4. Run core stack locally at $0.
5. Allow optional free cloud deployment.
6. Make every workflow independently testable.
7. Add workflows without redesigning core infrastructure.
8. Support human approval for risky actions.
9. Track execution cost even when cost is $0.
10. Track revenue by workflow.
11. Resume after crash/restart.
12. Prevent duplicate actions.
13. Make AI models swappable.
14. Allow vibe coding agents to work from explicit specs/tests.

## 2.2 Non-goals for v1

- Fully autonomous money movement.
- Artificial views, likes, followers, comments, or engagement.
- Circumventing platform restrictions.
- Private undocumented API dependency.
- CAPTCHA bypass systems.
- Proxy farms.
- Credential harvesting.
- Large-scale scraping that violates target-site rules.
- Paid infrastructure.
- Multi-tenant SaaS billing.
- Complex distributed Kubernetes deployment.

---

# 3. $0 Constraint

## 3.1 Hard rule

```text
PAID_SERVICE = BLOCKED
```

Every dependency must have one of:

```text
local + free/open source
OR
free tier with no required payment
OR
manual fallback
```

If free quota is exhausted:

```text
pause job
→ save state
→ switch local provider
→ retry later
```

Never automatically activate billing.

## 3.2 Cost ledger

Every execution records:

```text
provider
model
requests
input tokens
output tokens
audio seconds
compute time
storage bytes
estimated_cost
billing_status
```

For a local job:

```text
estimated_cost = 0
```

For a free-tier job:

```text
estimated_cost = 0
```

But quota usage must still be tracked.

---

# 4. Free Stack

Current design is based on tools that can run locally or have a current free option. Limits can change, so the project must not hard-code assumptions about external quotas.

## 4.1 Core runtime

```text
OS: Windows 11 + WSL2 Ubuntu
Docker Desktop
Python 3.12+
Node.js 22+
Git
FFmpeg
SQLite
```

## 4.2 Workflow engine

Primary:

```text
n8n self-hosted locally
```

n8n provides workflow automation and can be self-hosted with npm or Docker. citeturn113192search0

Do not make n8n the only execution layer.

Use:

```text
n8n → orchestration
Python → heavy processing
DB → state
```

## 4.3 Local AI

Primary:

```text
Ollama
```

Ollama runs open models locally; local models remain free and local execution does not send prompts off-machine. citeturn633031view3

Use model adapters so any local model can be swapped without changing application logic.

Example model roles:

```text
small model → classification
coding model → code generation
larger model → planning / synthesis
vision model → image/video frame analysis
embedding model → semantic search
```

Do not hard-code one model name as a system requirement.

## 4.4 Optional free AI APIs

### OpenRouter

Use only as fallback.

OpenRouter currently lists free models with $0 prompt pricing and a free plan with 25+ free models; current free-plan API access shows a 50 requests/day rate limit. citeturn774483search1turn774483search5

Policy:

```text
local model first
→ free external model second
→ paid model never automatically selected
```

### Gemini API

Use as optional fallback where the current Google free tier allows it. Google currently lists free-tier Gemini models and free-of-charge input/output pricing for those tiers; exact availability/limits vary by model and account. citeturn391953search3

### Groq

Use as optional fallback for fast inference. Groq currently provides a Free plan with model-specific rate limits; exact limits must be read from current account/API response headers. citeturn391953search0

The router must detect `429 Too Many Requests` and back off. citeturn391953search0

## 4.5 Database

Primary v1:

```text
SQLite
```

Why:

```text
zero cost
local
zero ops
persistent
portable
fast enough for solo MVP
```

Migration target:

```text
PostgreSQL
```

Use SQLAlchemy/SQLModel so migration is possible later.

Do not add hosted Postgres solely for v1.

## 4.6 Frontend

```text
Next.js / React / TypeScript
```

Local dev server:

```text
localhost
```

Optional remote static hosting can use Cloudflare Pages/Workers free resources. Current Cloudflare Workers Free includes 100,000 requests/day, with specific CPU/memory/subrequest limits. citeturn774483search3turn774483search7

Remote frontend is optional.

## 4.7 Public access

Preferred:

```text
local only
```

When remote access is needed:

```text
Cloudflare Tunnel
```

Never expose raw n8n or worker ports directly to the internet.

## 4.8 Code hosting

```text
GitHub Free
```

GitHub Actions:

```text
public repo → standard GitHub-hosted runner usage is free
private repo → Free plan includes monthly quota
self-hosted runners → no GitHub Actions runner charge
```

Current GitHub Free includes 2,000 Actions minutes/month for GitHub Free accounts; public repository standard runners are free. citeturn774483search6

For strict $0:

```text
local runner
or
public repo CI where appropriate
```

Secrets never go into public repos.

## 4.9 Optional free cloud backend

Render may be used only for prototypes/remote tests.

Current Render Free Web Services spin down after 15 minutes idle and free Postgres expires after 30 days. Free filesystems are ephemeral. Render explicitly says Free instances are not for production. citeturn774483search0

Therefore:

```text
Render free ≠ core production dependency
```

---

# 5. Architecture

## 5.1 System

```text
                         +----------------+
                         |   DASHBOARD    |
                         +-------+--------+
                                 |
                                 v
                    +------------+------------+
                    |      CONTROL API       |
                    +------------+------------+
                                 |
             +-------------------+-------------------+
             |                   |                   |
             v                   v                   v
       +-----------+       +-----------+       +-----------+
       | ORCHESTR. |       | AI ROUTER |       |  POLICY   |
       +-----+-----+       +-----+-----+       +-----+-----+
             |                   |                   |
             +-------------------+-------------------+
                                 |
                                 v
                         +-------+-------+
                         |     QUEUE     |
                         +-------+-------+
                                 |
                 +---------------+---------------+
                 |               |               |
                 v               v               v
             Python         Scrapers         Media
             Workers         Workers         Workers
                 |               |               |
                 +---------------+---------------+
                                 |
                                 v
                           +-----+-----+
                           |    DB     |
                           +-----+-----+
                                 |
                                 v
                           +-----+-----+
                           | ANALYTICS |
                           +-----------+
```

## 5.2 Components

### Control API

Responsibilities:

```text
CRUD workflows
CRUD jobs
approvals
settings
health
metrics
cost ledger
retries
kill switches
```

### Orchestrator

Responsibilities:

```text
trigger jobs
load workflow definition
validate prerequisites
enqueue tasks
track state
handle dependency graph
schedule retries
stop unsafe actions
```

### Queue

v1:

```text
DB-backed job queue
```

Do not add Redis until DB queue becomes bottleneck.

### Worker

Every worker accepts:

```text
job_id
workflow_id
payload
attempt
idempotency_key
```

Returns:

```text
status
output
error_code
retryable
metrics
artifacts
```

### AI Router

Interface:

```python
class ModelProvider(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse: ...
```

Providers:

```text
OllamaProvider
OpenRouterProvider
GeminiProvider
GroqProvider
MockProvider
```

Router policy:

```text
local available?
→ use local

local failed?
→ try configured free provider

quota exceeded?
→ next provider

all unavailable?
→ queue job

never paid
```

---

# 6. Core Modules

## 6.1 Registry

Stores all workflows.

Workflow schema:

```json
{
  "id": "content_rewards",
  "name": "Content Rewards",
  "version": "1.0.0",
  "enabled": true,
  "risk_level": "medium",
  "entrypoints": ["manual", "schedule"],
  "required_credentials": [],
  "steps": [],
  "outputs": []
}
```

## 6.2 Scheduler

Supports:

```text
cron
interval
manual
webhook
DB event
file event
```

Every schedule must be pausable.

## 6.3 Queue

Job states:

```text
QUEUED
RUNNING
WAITING
RETRYING
SUCCEEDED
FAILED
CANCELLED
BLOCKED
```

## 6.4 State Manager

State must survive:

```text
crash
restart
AI context loss
browser restart
network failure
worker restart
```

Use DB, never prompt context, as persistent state.

## 6.5 Artifact Manager

Artifact types:

```text
video
image
audio
text
JSON
CSV
PDF
HTML
screenshot
log
```

Local filesystem structure:

```text
storage/
  raw/
  processed/
  output/
  temp/
  exports/
```

Each artifact has hash:

```text
sha256
```

Deduplicate identical files.

## 6.6 Secrets

Secrets only in:

```text
.env.local
OS environment
n8n credential store
GitHub Actions secrets
```

Never:

```text
source code
logs
DB plaintext fields
frontend bundle
Git history
```

## 6.7 Notification layer

v1:

```text
terminal
browser dashboard
local webhook
email only if free SMTP/provider is available
```

No paid notification dependency.

---

# 7. Workflow Contract

Each workflow must include:

```text
README.md
workflow.yaml
inputs schema
outputs schema
permissions
risk level
timeouts
retry policy
idempotency strategy
manual approval rules
unit tests
integration tests
```

Example:

```yaml
id: content_rewards
version: 1.0.0
risk_level: medium
permissions:
  - browser
  - filesystem
  - social_publish
retries:
  max_attempts: 3
  backoff_seconds: [30, 120, 600]
approval:
  publish: required
  submit: required
```

---

# 8. Empire Workflow Library

## 8.1 Content Rewards

```text
campaign discovery
→ requirements extraction
→ eligibility check
→ source collection
→ clip plan
→ clip generation
→ quality check
→ human approval
→ social publishing
→ submission
→ views tracking
→ earnings tracking
```

Current Content Rewards architecture must be treated separately from generic Whop API infrastructure. New Content Rewards campaigns/submissions run through the Content Rewards web app, while Whop API documentation exposes broader capabilities such as payments, payouts, identity, apps, stats, partners, and webhooks. Do not assume undocumented Content Rewards CRUD endpoints exist.

## 8.2 Lead Generation

```text
source discovery
→ search/filter
→ data extraction
→ normalization
→ duplicate detection
→ enrichment if legally/technically permitted
→ scoring
→ export
```

Outputs:

```text
CSV
SQLite
CRM-compatible JSON
```

## 8.3 Product Research

```text
source scan
→ product extraction
→ trend detection
→ price normalization
→ competitor comparison
→ opportunity score
→ report
```

## 8.4 SEO Engine

```text
keyword/source discovery
→ clustering
→ SERP/manual source collection
→ content plan
→ draft
→ fact checks
→ publish queue
```

## 8.5 Job Monitor

```text
job-source monitor
→ parse
→ dedupe
→ skill match
→ priority score
→ alert
```

## 8.6 Competitor Monitor

```text
target list
→ snapshot
→ diff
→ classify change
→ alert
→ archive
```

---

# 9. Content Rewards Module

## 9.1 Purpose

Automate operational work around legitimate content campaigns while preserving platform rules and human review.

## 9.2 Campaign object

```json
{
  "campaign_id": "",
  "source": "content_rewards",
  "title": "",
  "type": "cpm|per_post|retainer",
  "platforms": [],
  "niches": [],
  "budget_total": 0,
  "budget_remaining": 0,
  "rate": 0,
  "max_payout": 0,
  "min_views": 0,
  "application_required": false,
  "preapproval_required": false,
  "required_tags": [],
  "required_mentions": [],
  "duration_min": 0,
  "duration_max": 0,
  "source_material": [],
  "rights_notes": "",
  "deadline": null,
  "status": "unknown",
  "raw_source_url": ""
}
```

## 9.3 Campaign parser

Input:

```text
URL
HTML
manual paste
screenshot
PDF
```

Output:

```text
structured requirements
confidence per field
unknown fields
source citation
```

Never guess missing requirements.

Field confidence:

```text
HIGH
MEDIUM
LOW
UNKNOWN
```

## 9.4 Campaign scoring

Scoring is a prioritization tool, not a payout guarantee.

Features:

```text
platform fit
niche fit
payout model
minimum views
max payout
remaining budget
content difficulty
editing time
source availability
rights clarity
deadline
account eligibility
```

Example score:

```text
score =
  platform_fit
+ niche_fit
+ payout_fit
+ source_fit
+ time_fit
- risk_penalty
- uncertainty_penalty
```

All weights configurable.

## 9.5 Clip pipeline

```text
source
→ download
→ hash
→ inspect
→ transcribe
→ segment
→ detect hooks
→ rank candidate windows
→ crop 9:16
→ captions
→ overlays
→ loudness check
→ render
→ visual QC
→ export
```

Local tools:

```text
yt-dlp
FFmpeg
OpenCV
Pillow
faster-whisper / Whisper
Python
```

No paid video API required.

## 9.6 Quality checks

Automatic:

```text
resolution
aspect ratio
codec
duration
audio presence
silent section detection
subtitle overflow
black-frame detection
file integrity
watermark detection where feasible
```

Optional AI:

```text
hook clarity
topic match
caption correctness
visual quality
```

## 9.7 Publishing

Official platform APIs only where available and permitted.

Never automate through undocumented endpoints as core logic.

Publishing adapters:

```text
TikTokPublisher
YouTubePublisher
InstagramPublisher
FacebookPublisher
XPublisher
```

Each adapter exposes:

```python
publish(draft) -> PublishResult
get_status(post_id) -> PostStatus
get_metrics(post_id) -> Metrics
```

## 9.8 Human gates

Required by default for v1:

```text
campaign acceptance
rights approval
final clip approval
publish approval
submission approval
```

Later, each gate can have configurable automation policy.

## 9.9 Compliance

The workflow must block:

```text
fake views
fake likes
fake followers
fake comments
engagement manipulation
copyright-unapproved content
spam bursts
```

The system must not claim platform approval merely because an API request succeeded.

---

# 10. Database Schema

## 10.1 Core tables

```text
workflows
workflow_versions
jobs
job_attempts
job_events
approvals
credentials_metadata
artifacts
providers
provider_usage
notifications
errors
system_settings
```

## 10.2 Business tables

```text
campaigns
campaign_requirements
source_media
clips
clip_versions
published_posts
submissions
metrics_snapshots
earnings
payouts
leads
products
jobs_market
competitors
```

## 10.3 Required fields

All major records should contain:

```text
id
created_at
updated_at
status
version
source
metadata_json
```

## 10.4 Audit log

Every state transition:

```text
who
when
what
old_state
new_state
reason
job_id
request_id
```

For automated actor:

```text
actor = system
```

---

# 11. API

## 11.1 Internal API

Base:

```text
/api/v1
```

Endpoints:

```text
GET    /health
GET    /workflows
POST   /workflows/{id}/run
GET    /jobs
GET    /jobs/{id}
POST   /jobs/{id}/retry
POST   /jobs/{id}/cancel
POST   /jobs/{id}/approve
POST   /jobs/{id}/reject
GET    /campaigns
GET    /campaigns/{id}
POST   /campaigns/import
GET    /clips
POST   /clips/generate
POST   /clips/{id}/approve
POST   /publishing/jobs
GET    /published-posts
GET    /earnings
GET    /providers/health
GET    /system/cost
POST   /system/pause
POST   /system/resume
POST   /system/kill-switch
```

## 11.2 Idempotency

All side-effect endpoints must support:

```text
Idempotency-Key
```

The key is persisted before execution.

Duplicate request:

```text
same key
→ return original result
```

Never duplicate a publish/payment/submission because of retry.

---

# 12. Event Bus

Event format:

```json
{
  "event_id": "uuid",
  "event_type": "job.succeeded",
  "timestamp": "ISO-8601",
  "workflow_id": "",
  "job_id": "",
  "payload": {},
  "trace_id": ""
}
```

Core events:

```text
workflow.started
workflow.paused
job.created
job.started
job.waiting
job.retrying
job.succeeded
job.failed
approval.requested
approval.granted
approval.rejected
artifact.created
campaign.discovered
campaign.qualified
clip.created
clip.approved
post.published
submission.created
metrics.updated
earnings.updated
payout.updated
provider.rate_limited
provider.failed
system.kill_switch
```

---

# 13. Error System

Errors must be classified.

```text
AUTH
RATE_LIMIT
NETWORK
INVALID_INPUT
PARSER
MEDIA
PERMISSION
POLICY
CAPTCHA
DUPLICATE
TIMEOUT
RESOURCE
UNKNOWN
```

Each error gets:

```text
retryable
severity
recovery_action
```

Example:

```json
{
  "code": "RATE_LIMIT",
  "retryable": true,
  "recovery": "backoff",
  "severity": "warning"
}
```

Recovery engine:

```text
RATE_LIMIT → exponential backoff
NETWORK → retry
AUTH → refresh token/manual reauth
DUPLICATE → stop
POLICY → block/manual review
INVALID_INPUT → fail fast
UNKNOWN → quarantine + alert
```

---

# 14. AI Agent Structure

## 14.1 Controller Agent

Role:

```text
select next system action
```

Must not directly perform side effects.

## 14.2 Research Agent

```text
discover
extract
summarize
cite
```

## 14.3 Analyst Agent

```text
classify
score
compare
find anomalies
```

## 14.4 Builder Agent

```text
write code
write tests
fix bugs
refactor
```

## 14.5 Content Agent

```text
hook
caption
title
description
CTA
```

## 14.6 QA Agent

```text
validate output
check requirements
check policy rules
find defects
```

## 14.7 Finance Agent

Read-only in v1.

```text
revenue aggregation
cost aggregation
payout reconciliation
```

No autonomous money movement.

---

# 15. AI Agent Protocol

Agents cannot directly edit production state without tools.

Every agent returns:

```json
{
  "decision": "",
  "reason": "",
  "evidence": [],
  "assumptions": [],
  "unknowns": [],
  "actions": [],
  "confidence": 0
}
```

State classes:

```text
FACT
ASSUMPTION
HYPOTHESIS
UNKNOWN
```

Never merge these categories.

---

# 16. Vibe Coding Protocol

## 16.1 AI coding rule

Never ask coding agent:

```text
build whole empire
```

Instead:

```text
inspect repo
→ read PRD
→ identify one module
→ write tests
→ implement module
→ run tests
→ inspect failures
→ fix
→ report changed files
```

## 16.2 Project instructions

Create:

```text
AGENTS.md
CLAUDE.md
GEMINI.md
opencode.md
```

They must point to one source of truth:

```text
PRD.md
```

## 16.3 Agent constraints

AI coding agents must:

```text
not delete files without reason
not replace architecture silently
not add paid dependencies
not expose secrets
not skip tests
not invent APIs
not use undocumented APIs without explicit flag
not bypass policy controls
```

## 16.4 Definition of done

A module is done only when:

```text
code exists
+ tests pass
+ error paths handled
+ logs exist
+ state persisted
+ retry behavior tested
+ docs updated
+ no paid dependency added
```

---

# 17. Dashboard

## 17.1 Main views

```text
Overview
Workflows
Jobs
Campaigns
Content
Publishing
Revenue
Providers
Errors
Logs
System
```

## 17.2 Overview cards

```text
running jobs
failed jobs
queued jobs
active workflows
published posts
views
revenue
provider quota
storage
```

## 17.3 Job inspector

Show:

```text
job ID
workflow
state
attempts
input
output
logs
artifacts
errors
trace ID
```

## 17.4 Kill switch

Global:

```text
STOP ALL
```

Workflow-specific:

```text
PAUSE WORKFLOW
```

Action-specific:

```text
DISABLE PUBLISH
DISABLE SCRAPE
DISABLE SUBMIT
```

Kill switch must persist in DB.

---

# 18. Security

## 18.1 Principles

```text
least privilege
local first
secret isolation
audit everything
manual gates for risky actions
```

## 18.2 Browser automation

Use:

```text
Playwright
Selenium
```

Only where no supported API exists and automation is permitted.

Browser sessions:

```text
encrypted/persistent local profile
```

Never log cookies or session tokens.

## 18.3 n8n security

Self-hosted n8n must have:

```text
auth
HTTPS when exposed
strong encryption key
protected webhooks
regular updates
restricted network access
```

n8n provides a security audit command/API that checks credentials, DB, filesystem, nodes, instance settings, and webhook security. citeturn113192search3

---

# 19. Observability

Minimum:

```text
structured JSON logs
trace_id
job_id
workflow_id
provider
duration_ms
status
error_code
```

Metrics:

```text
jobs_total
jobs_success
jobs_failed
job_duration
retry_count
provider_calls
provider_429
artifacts_created
storage_bytes
revenue_total
estimated_cost_total
```

Local log storage:

```text
SQLite + rotating files
```

---

# 20. Backup

Because local-first means local failure is real.

Daily:

```text
SQLite backup
config backup
workflow export
```

Artifact backup:

```text
important outputs only
```

Backup target:

```text
external drive
Git repository for non-secret config
```

Never commit:

```text
DB credentials
OAuth tokens
API keys
session cookies
private media
```

---

# 21. Testing

## 21.1 Unit

Test:

```text
parsers
scorers
state transitions
retry policy
idempotency
provider routing
file validation
```

## 21.2 Integration

Test:

```text
DB
n8n webhook
Python worker
AI adapter
artifact pipeline
social API adapters
```

## 21.3 Failure tests

Simulate:

```text
network down
429
401
file missing
corrupt video
DB locked
worker crash
duplicate request
expired OAuth token
```

## 21.4 Golden fixtures

Store fixed input/output examples:

```text
fixtures/
  campaigns/
  videos/
  captions/
  api_responses/
```

AI output must not be tested only by exact text.

Use structural assertions.

---

# 22. Development Phases

## Phase 0 — Foundation

Deliver:

```text
repo
Docker setup
Python environment
Node environment
SQLite
FastAPI
Next.js
n8n
Ollama integration
logging
config
```

Acceptance:

```text
one command starts core stack locally
```

## Phase 1 — Orchestrator

Deliver:

```text
workflow registry
job queue
scheduler
state machine
retry engine
idempotency
kill switch
```

Acceptance:

```text
sample workflow survives worker restart
```

## Phase 2 — AI Router

Deliver:

```text
Ollama provider
optional OpenRouter provider
optional Gemini provider
optional Groq provider
quota detection
fallback
cost ledger
```

Acceptance:

```text
disable provider
→ router selects next provider
```

## Phase 3 — Dashboard

Deliver:

```text
overview
jobs
workflow controls
logs
providers
```

Acceptance:

```text
operator can control system without CLI
```

## Phase 4 — Content Rewards

Deliver:

```text
campaign import
requirements parser
campaign DB
qualification
source media
clip pipeline
QC
human approval
publishing adapters
submission tracker
views tracker
earnings tracker
```

Acceptance:

```text
one legitimate campaign
→ one valid approved workflow
→ complete audit trail
```

## Phase 5 — Empire Modules

Add one workflow at a time:

```text
lead generation
product research
job monitor
SEO
competitor monitoring
affiliate research
```

Each module must reuse core infrastructure.

## Phase 6 — Optimization

Only after real usage:

```text
PostgreSQL
Redis
remote workers
object storage
parallel execution
advanced scheduling
```

Never add complexity before bottleneck exists.

---

# 23. Local Dev Commands

Expected bootstrap pattern:

```bash
# clone
 git clone <repo>
 cd automation-empire-os

# Python
python -m venv .venv

# Windows
.venv\\Scripts\\activate

# WSL/Linux
source .venv/bin/activate

pip install -r requirements.txt

# frontend
npm install

# n8n via Docker
 docker compose up -d

# start API
uvicorn backend.app:app --reload

# start frontend
npm run dev
```

Exact package versions should be pinned during implementation.

---

# 24. Environment Variables

```env
APP_ENV=development
APP_SECRET=
DATABASE_URL=sqlite:///./data/empire.db
STORAGE_DIR=./storage
LOG_DIR=./logs

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=

OPENROUTER_API_KEY=
OPENROUTER_MODEL=

GEMINI_API_KEY=
GEMINI_MODEL=

GROQ_API_KEY=
GROQ_MODEL=

WHOP_API_KEY=
WHOP_APP_ID=
WHOP_CLIENT_ID=
WHOP_CLIENT_SECRET=

TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=
TIKTOK_REDIRECT_URI=

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=

META_APP_ID=
META_APP_SECRET=
META_REDIRECT_URI=
```

Empty provider credentials must disable provider cleanly.

No startup failure because optional provider is absent.

---

# 25. Provider Abstraction

All external providers implement a shared adapter pattern.

```python
class Provider:
    name: str

    def health(self) -> ProviderHealth:
        ...

    def execute(self, request: ProviderRequest) -> ProviderResponse:
        ...

    def estimate_cost(self, request: ProviderRequest) -> float:
        ...
```

Provider registry:

```text
ollama
openrouter
 gemini
 groq
whop
tiktok
youtube
instagram
```

The application never calls provider SDKs directly from business logic.

---

# 26. Whop Integration

Use Whop for supported business/platform capabilities.

Whop currently exposes payments, payouts, identity, accounts, apps, ads, stats, partners and webhooks through its developer platform. Whop also supports apps running inside Whop and provides TypeScript, Python and Ruby SDKs. citeturn633031view1

Integration rules:

```text
server-side API key only
OAuth where user authorization is required
webhooks for supported events
sandbox before real money
```

Do not assume Content Rewards resources exist in the public Whop API unless current documentation explicitly exposes them.

---

# 27. Free-Tier Protection

## 27.1 Quota manager

Every external provider has:

```text
requests_today
requests_minute
tokens_today
tokens_minute
last_error
reset_time
```

If provider returns rate limit:

```text
record headers
calculate retry_at
pause
fallback
```

## 27.2 Billing lock

No provider configuration may contain payment activation logic.

System setting:

```text
ALLOW_PAID_SERVICES=false
```

This must be hard-false in v1 code paths.

## 27.3 Cloud lock

Optional cloud deployment is disabled by default.

```text
DEPLOY_MODE=LOCAL
```

---

# 28. Revenue Layer

Every workflow has revenue attribution.

```text
workflow_id
campaign_id
source
revenue_gross
fees
revenue_net
currency
status
date
```

Revenue states:

```text
EXPECTED
PENDING
APPROVED
SETTLED
WITHDRAWN
DISPUTED
CANCELLED
```

Do not count expected revenue as cash.

Dashboard must separate:

```text
projected
pending
settled
withdrawn
```

---

# 29. Opportunity Engine

Purpose:

```text
find new automation opportunities
```

Inputs:

```text
marketplaces
job boards
social trends
public datasets
RSS
GitHub repositories
product launches
user-provided ideas
```

Pipeline:

```text
collect
→ normalize
→ dedupe
→ classify
→ score
→ store
→ alert
```

Opportunity schema:

```text
problem
customer
repetition
frequency
pain
existing tools
monetization route
automation difficulty
legal risk
cost
confidence
```

---

# 30. Empire Expansion Loop

```text
discover problem
→ build tiny automation
→ run locally
→ measure time saved/revenue
→ improve
→ package
→ reuse core modules
→ launch next automation
```

Each new automation must answer:

```text
What input?
What output?
What repetitive work removed?
What API/site/tool used?
What state persisted?
What can fail?
What is human-controlled?
What revenue path exists?
```

---

# 31. Workflow Marketplace Inside Empire OS

Future internal library:

```text
Workflow Cards
```

Each card:

```text
name
version
purpose
inputs
outputs
requirements
risk
runtime
estimated cost
status
last successful run
revenue
```

Install workflow:

```text
enable
→ configure credentials
→ dry run
→ test
→ activate
```

---

# 32. Dry Run Mode

Every workflow supports:

```text
DRY_RUN=true
```

Dry run:

```text
reads data
parses
plans
renders previews
writes simulated actions
```

But does not:

```text
publish
submit
send money
send destructive requests
```

Example:

```json
{
  "mode": "dry_run",
  "planned_action": "publish",
  "target": "tiktok",
  "payload_hash": "..."
}
```

---

# 33. Human Approval Engine

Approval object:

```text
approval_id
job_id
action
risk
preview
evidence
requested_at
expires_at
approved_by
approved_at
reason
```

Rules:

```text
low risk → auto
medium risk → configurable
high risk → manual
money movement → manual v1
external publishing → manual v1
```

---

# 34. Browser Automation Safety

When browser automation is used:

```text
DOM locators > image clicking
explicit waits > sleeps
state verification after action
screenshot on failure
session reuse where permitted
rate limits respected
```

Never:

```text
blind infinite loops
rapid retries
credential extraction
anti-bot bypass
```

---

# 35. File Layout

```text
automation-empire-os/
├── PRD.md
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── opencode.md
├── docker-compose.yml
├── .env.example
├── .gitignore
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── providers/
│   │   ├── workers/
│   │   ├── workflows/
│   │   └── main.py
│   └── tests/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── tests/
│
├── workflows/
│   ├── content_rewards/
│   ├── lead_generation/
│   ├── product_research/
│   ├── seo/
│   ├── job_monitor/
│   └── competitor_monitor/
│
├── n8n/
│   ├── workflows/
│   └── exports/
│
├── scripts/
├── fixtures/
├── migrations/
├── storage/
├── logs/
└── docs/
```

---

# 36. First MVP Workflow

Build this before everything else:

```text
MANUAL TRIGGER
→ create test job
→ Ollama classify input
→ store result
→ create artifact
→ emit event
→ dashboard displays job
→ mark success
```

Then:

```text
schedule
→ queue
→ worker
→ AI
→ artifact
→ dashboard
```

Then Content Rewards.

This proves architecture before adding complexity.

---

# 37. Content Rewards MVP Workflow

```text
1. User adds campaign URL
2. Parser collects available content
3. Extract requirements
4. Mark unknown fields
5. User approves campaign
6. Source media imported
7. Transcript generated locally
8. Candidate clips generated
9. Automatic QC
10. User reviews
11. Approved clip enters publish queue
12. Official social API publishes where configured
13. Public URL stored
14. User completes/approves CR submission where current official interface requires it
15. Metrics snapshots scheduled
16. Earnings state updated
17. Dashboard shows lifecycle
```

Success condition:

```text
full state trace from campaign → clip → post → submission → earnings
```

---

# 38. Acceptance Criteria

## Core

- System starts locally.
- No paid service required.
- No provider key required for local-only operation.
- DB survives restart.
- Jobs survive restart.
- Failed jobs can retry.
- Duplicate jobs cannot create duplicate side effects.
- Kill switch stops side effects.
- Logs identify job/workflow/trace.

## AI

- Ollama works without internet after model installation.
- Provider adapter can be swapped.
- External provider quota failure does not crash system.
- No paid provider is selected automatically.

## Workflow

- New workflow can be registered without rewriting orchestrator.
- Workflow has explicit input/output schema.
- Workflow has tests.

## Content

- Video output passes technical QC.
- Human approval gate works.
- Publish result is stored.
- Submission state is stored.
- Metrics snapshots are stored.
- Revenue state is separated from projected revenue.

---

# 39. Performance Targets

v1 target is reliability, not scale.

```text
API response p95 < 500ms for local CRUD
job state persistence < 100ms typical
zero duplicate side effects in tested retry scenarios
worker restart recovery < 1 manual action
```

Media jobs are excluded from API latency target.

---

# 40. Failure Philosophy

Never hide failure.

Bad:

```text
catch exception
→ continue
```

Good:

```text
failure
→ classify
→ persist
→ decide recovery
→ retry/fallback/block
→ alert
```

Every unknown failure becomes visible.

---

# 41. Upgrade Path

Only upgrade infrastructure when evidence requires it.

```text
SQLite
→ PostgreSQL
```

when:

```text
concurrency
or
DB contention
or
remote multi-worker requirement
```

```text
DB queue
→ Redis
```

when queue throughput becomes bottleneck.

```text
local worker
→ remote worker
```

when 24/7 execution becomes necessary.

```text
local storage
→ object storage
```

when storage size becomes operational problem.

Never upgrade because architecture diagrams look cooler.

---

# 42. Security Acceptance Tests

- Secrets absent from Git.
- Logs do not reveal tokens.
- Frontend bundle contains no private keys.
- Kill switch blocks external side effects.
- Browser sessions cannot be exported through logs.
- API routes require auth when exposed remotely.
- Webhooks validate signatures where provider supports signing.
- Idempotency prevents duplicate side effects.

---

# 43. Operational Runbook

## Start

```text
Docker
→ n8n
→ API
→ workers
→ frontend
```

## Stop

```text
pause workflows
→ finish/stop workers
→ backup DB
→ stop services
```

## Crash

```text
restart core
→ load jobs from DB
→ recover RUNNING jobs as UNKNOWN
→ retry only retryable jobs
```

## Provider outage

```text
mark provider unhealthy
→ fallback
→ queue if no fallback
```

## Disk nearly full

```text
pause media jobs
→ cleanup temp
→ archive old artifacts
→ resume
```

---

# 44. Build Order for Vibe Coding

Strict order:

```text
01 repo skeleton
02 config
03 DB
04 migrations
05 models
06 state machine
07 queue
08 orchestrator
09 worker
10 logging
11 idempotency
12 provider interface
13 Ollama adapter
14 dashboard
15 n8n integration
16 artifact manager
17 media engine
18 content rewards parser
19 content rewards clip engine
20 publishing adapters
21 submission tracker
22 analytics
23 revenue
24 additional workflows
```

Do not jump from step 1 to step 24.

---

# 45. AI Coding Prompt Contract

Every coding agent should receive:

```text
READ PRD.md FIRST.

TASK:
<one bounded task>

RULES:
- $0 architecture only.
- No paid dependency.
- No undocumented API invention.
- Preserve existing architecture.
- Inspect before editing.
- Write/update tests.
- Run tests.
- Handle failure paths.
- Persist state.
- Keep secrets out of code.
- Do not refactor unrelated code.

OUTPUT:
1. changed files
2. implementation summary
3. tests run
4. failures
5. unresolved assumptions
```

---

# 46. Definition of Empire

Empire does not mean one huge autonomous agent.

Empire means:

```text
shared infrastructure
+
independent workflows
+
shared state
+
reusable workers
+
reusable providers
+
reusable AI router
+
central observability
+
central revenue tracking
```

Adding workflow #20 should require:

```text
new workflow package
new config
new tests
```

Not:

```text
rewrite core system
```

---

# 47. Final Product State

Target:

```text
                    EMPIRE OS
                        |
        +---------------+---------------+
        |               |               |
     Discovery       Execution       Revenue
        |               |               |
      signals         jobs          analytics
        |               |               |
        +---------------+---------------+
                        |
                  AI MODEL ROUTER
                        |
             +----------+----------+
             |          |          |
           Ollama    Free APIs   Manual
             |
             v
          Workers
             |
     +-------+-------+-------+
     |       |       |       |
   Content  Leads  SEO    Research
     |       |       |       |
     +-------+-------+-------+
             |
          DATABASE
             |
         DASHBOARD
```

Absolute constraint:

```text
$0
local-first
modular
persistent
observable
recoverable
human-controlled
```

That is v1 architecture.
