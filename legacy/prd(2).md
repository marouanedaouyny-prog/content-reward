# PRD — Social Media Auto-Publishing Connector

**Status:** Draft
**Research date:** 2026-09-29
**Primary goal:** Build self-hosted social-media connectors that receive content from n8n/API/CLI and publish through official platform APIs.
**Cost target:** $0 for local development + self-hosting on existing hardware.

---

## 1. Product

Build one small service that abstracts social-platform APIs behind one unified interface:

```text
n8n / CLI / REST / automation
        |
        v
+-------------------------+
| Social Connector API    |
| auth / media / publish  |
| status / retry / logs   |
+------------+------------+
             |
      +------+------+------+------+------+------+ 
      |      |      |      |      |      |
     X   LinkedIn  Meta  TikTok YouTube Threads ...
```

Core idea:

```text
Connect account once
→ store encrypted refresh/access credentials
→ accept post job
→ validate per-platform rules
→ upload media
→ publish
→ poll/receive status
→ persist external post ID + URL
→ retry transient failures
```

No scraping. No browser-cookie automation in core. Use official APIs wherever platform exposes publishing APIs.

---

## 2. Why build this

Existing OSS projects show proven patterns:

### Postiz
GitHub: https://github.com/gitroomhq/postiz-app

Postiz is a large AGPL-3.0 self-hosted social scheduling system. Its current repository describes API/webhook automation, custom integrations, provider modification, and many platform providers. The repo currently shows ~35k stars and thousands of commits. The latest release observed during research is v2.24.0, released 2026-09-22. citeturn344715search1turn344715search6

Useful architecture to study:

- provider-per-platform model
- OAuth connection flow
- unified integration identifiers
- public API for integrations/posts
- media upload abstraction
- status/retry workflow
- provider-specific validation

Postiz docs show a consistent OAuth callback shape:

```text
{FRONTEND_URL}/integrations/social/{provider}
```

They also expose separate provider configuration and a documented "create provider" workflow. citeturn147565search1turn206874search0

Important license point: Postiz source is AGPL-3.0. Treat its code as reference unless project licensing/compliance requirements explicitly allow using/forking it. citeturn147565search7

### Mixpost
GitHub: https://github.com/inovector/mixpost
GitHub app: https://github.com/inovector/MixpostApp

Mixpost is self-hosted social-management software. The standalone Lite repository provides scheduling, publishing and management without monthly subscription fees. Current GitHub release listing shows v2.6.0 as latest observed release. citeturn344715search8turn344715search9

Useful for studying:

- account/channel model
- scheduled content model
- provider abstraction
- Laravel implementation patterns

### Socioboard
GitHub: https://github.com/socioboard/Socioboard-5.0

Open-source social-management platform with a centralized API and plugin/extensibility model. GitHub currently shows ~1.5k stars. citeturn908997search0turn908997search4

Useful for studying:

- centralized social API
- multi-account handling
- extensible integrations

### Nango
GitHub: https://github.com/NangoHQ/nango

Nango is open-source integration infrastructure focused on OAuth, credentials, token refresh, API integrations, retries, rate limiting and multi-tenant connections. GitHub currently describes 1,000+ APIs. Nango uses an Elastic License, so review licensing before embedding it in a commercial product. citeturn908997search2turn908997search7

Use Nango only when auth/integration maintenance becomes larger than writing small platform adapters directly.

---

## 3. MVP scope

### Platforms

Build these first:

1. LinkedIn
2. Facebook Pages
3. Instagram Business/Creator
4. TikTok
5. YouTube
6. X

Second wave:

- Threads
- Reddit
- Pinterest
- Bluesky
- Mastodon
- Telegram
- Discord

Do not start with 15+ platforms. Build provider interface first, then add adapters one by one.

---

## 4. Platform reality

Every platform has different OAuth scopes, account types, media rules, approval states, quotas and post semantics. Connector MUST expose platform capabilities instead of pretending every provider behaves identically.

### TikTok
TikTok Content Posting API currently supports direct photo/video posting. Direct Post requires an app, Content Posting API, Direct Post configuration, user authorization and approval for `video.publish`. TikTok states that unaudited clients have content restricted to private viewing until audit/compliance approval. TikTok also documents a publish-status endpoint and a 6-requests-per-minute limit per user access token for relevant posting calls. citeturn925021search0turn925021search1

Design implication:

```text
publish() may return PROCESSING
→ save publish_id
→ poll status
→ map final status
```

### YouTube
YouTube uses `videos.insert` for uploads. Google documents OAuth scopes including `https://www.googleapis.com/auth/youtube.upload`. Google also states that uploads from unverified API projects created after 2020-07-28 are restricted to private viewing until the project passes audit. citeturn925021search3

Design implication:

```text
upload != guaranteed PUBLIC
```

Store requested visibility and actual resulting visibility/status.

### LinkedIn
LinkedIn's current Posts API supports organic text, image, video, document, article, multi-image and poll posts, with permissions such as `w_member_social` and organization permissions. LinkedIn also requires versioned API headers and notes that older Marketing API versions are being sunset. citeturn830343search0turn830343search3

Design implication:

```text
LinkedIn adapter MUST keep API version in config
```

### Meta
Facebook Pages and Instagram should be implemented as separate providers over Meta's APIs because account discovery, permissions and media flows differ. Postiz's current provider documentation explicitly separates Facebook and Instagram provider configuration, and Instagram Business via Facebook shares Meta app credentials with Facebook Page integration. citeturn147565search1

Before release, verify current Meta developer permissions/app-review requirements against Meta's official documentation.

### X
Implement OAuth-based user connection and provider-specific post/media operations. Do not hard-code assumptions from older Twitter API versions; provider version/endpoints must be configurable and covered by integration tests.

---

## 5. Functional requirements

### FR-1 Account connection

User can:

```text
GET /connect/{provider}
→ OAuth authorization
→ callback
→ exchange code
→ fetch account identity
→ encrypt credentials
→ save connection
```

Support:

- OAuth 2 Authorization Code
- PKCE where provider supports/requires it
- refresh token flow
- token expiry tracking
- reconnect
- disconnect
- connection health check

Never ask user to paste access tokens into normal UI.

### FR-2 Account discovery

After OAuth, provider adapter resolves usable publishing targets:

```json
{
  "provider": "linkedin",
  "accounts": [
    {
      "external_id": "...",
      "name": "...",
      "type": "profile",
      "capabilities": ["text", "image", "video"]
    }
  ]
}
```

### FR-3 Unified publish API

```http
POST /v1/posts
```

Request:

```json
{
  "idempotency_key": "job-123",
  "text": "Hello world",
  "media": [
    {
      "url": "https://example.com/video.mp4",
      "type": "video"
    }
  ],
  "targets": [
    {
      "provider": "linkedin",
      "account_id": "acc_1"
    },
    {
      "provider": "tiktok",
      "account_id": "acc_2"
    }
  ],
  "publish_at": null
}
```

Response:

```json
{
  "job_id": "job_123",
  "status": "queued",
  "targets": [
    {
      "provider": "linkedin",
      "status": "queued"
    }
  ]
}
```

### FR-4 Per-platform adaptation

Universal content MUST be transformed by adapter:

```text
UniversalPost
      ↓
Provider.validate()
      ↓
Provider.prepare_media()
      ↓
Provider.publish()
      ↓
Provider.fetch_status()
```

Examples:

```text
caption length
media MIME
aspect ratio
file size
thread splitting
visibility
hashtags/mentions
provider-specific metadata
```

No provider-specific logic in generic scheduler.

### FR-5 Scheduling

Support:

```text
publish now
publish at UTC timestamp
retry failed job
cancel queued job
```

MVP scheduler:

- SQLite
- one worker process
- APScheduler or DB-backed polling loop
- UTC internally
- timezone conversion only at API/UI edge

Avoid Redis/Celery in MVP.

### FR-6 Status

Normalize provider states:

```text
queued
uploading
processing
published
failed
cancelled
needs_reauth
needs_review
```

Store provider-specific raw response separately for debugging.

### FR-7 Idempotency

Same `idempotency_key` MUST NOT create duplicate posts.

DB constraint:

```text
unique(user_id, idempotency_key, target_account_id)
```

Adapter should also support provider-side duplicate checks where practical.

### FR-8 Retry

Retry only transient failures:

```text
429
408
502
503
504
network timeout
provider processing timeout
```

Do not blindly retry:

```text
invalid OAuth
invalid media
permission denied
account disabled
unsupported content
expired/invalid refresh token after refresh attempt
```

Backoff:

```text
30s → 2m → 5m → 15m → 1h
```

Add jitter.

### FR-9 Webhooks

Provide:

```http
POST /v1/webhooks/{provider}
```

Use provider signatures where available.

Webhook flow:

```text
provider event
→ verify signature
→ map event
→ update DB
→ emit internal event
```

### FR-10 n8n integration

Primary automation path:

```text
n8n
  → HTTP Request
  → POST /v1/posts
  → connector
  → social platform
```

Also expose:

```http
GET  /v1/accounts
GET  /v1/providers
GET  /v1/posts/{id}
POST /v1/posts/{id}/cancel
GET  /v1/jobs/{id}
```

Later:

```text
native n8n node
```

---

## 6. Connector interface

Python interface:

```python
from abc import ABC, abstractmethod

class SocialProvider(ABC):
    id: str

    @abstractmethod
    def get_authorization_url(self, state: str, code_challenge: str | None = None) -> str:
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        ...

    @abstractmethod
    async def refresh_token(self, connection: dict) -> dict:
        ...

    @abstractmethod
    async def get_accounts(self, connection: dict) -> list[dict]:
        ...

    @abstractmethod
    async def validate_post(self, account: dict, post: dict) -> dict:
        ...

    @abstractmethod
    async def publish(self, account: dict, post: dict) -> dict:
        ...

    @abstractmethod
    async def get_status(self, account: dict, external_post_id: str) -> dict:
        ...

    @abstractmethod
    async def delete(self, account: dict, external_post_id: str) -> dict:
        ...
```

Provider-specific helper classes:

```text
OAuthClient
HttpClient
MediaUploader
RateLimiter
ErrorMapper
```

Each adapter MUST be isolated:

```text
providers/
├── base.py
├── linkedin/
│   ├── provider.py
│   ├── oauth.py
│   ├── media.py
│   ├── schemas.py
│   └── errors.py
├── tiktok/
├── youtube/
├── facebook/
├── instagram/
└── x/
```

---

## 7. System architecture

```text
                    +------------------+
                    | n8n / REST / CLI |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    | FastAPI Gateway  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
       +-------------+               +-------------+
       | Auth/Conn   |               | Post Engine |
       +------+------+               +------+------+ 
              |                             |
              v                             v
       +-------------+               +-------------+
       | Credential  |               | Scheduler   |
       | Vault       |               | + Worker    |
       +------+------+               +------+------+ 
              |                             |
              +--------------+--------------+
                             |
                             v
                    +------------------+
                    | Provider Manager |
                    +--+--+--+--+--+---+
                       |  |  |  |  |  |
                       v  v  v  v  v  v
                      X LI FB IG TT YT

Persistence:
SQLite → MVP
PostgreSQL → later multi-user production
Local filesystem → MVP media
S3/R2-compatible storage → later
```

---

## 8. Zero-cost stack

### Backend

```text
Python 3.12+
FastAPI
Pydantic
httpx
SQLAlchemy
Alembic
APScheduler
cryptography
PyJWT only where needed
pytest
respx
```

### Frontend

MVP can avoid frontend completely.

Use:

```text
FastAPI Swagger/OpenAPI
```

Add Next.js dashboard later.

### Storage

MVP:

```text
SQLite
./data/app.db
./data/media/
```

Credentials:

```text
encrypted in DB
master key from environment
```

### Dev

```text
Docker Compose
GitHub Actions
Python venv
ngrok/Cloudflare Tunnel or equivalent for OAuth dev callbacks where compatible
```

Do not assume any third-party free-host tier is permanent. Self-hosting on existing machine keeps software spend at $0.

---

## 9. Database model

### users

```text
id
email
created_at
```

### social_connections

```text
id
user_id
provider
external_account_id
external_account_type
account_name
access_token_encrypted
refresh_token_encrypted
token_expires_at
scopes_json
metadata_json
status
created_at
updated_at
```

### posts

```text
id
user_id
idempotency_key
text
publish_at
status
created_at
updated_at
```

### post_targets

```text
id
post_id
connection_id
provider
external_post_id
external_url
status
error_code
error_message
raw_response_json
attempt_count
next_retry_at
published_at
```

### media

```text
id
post_id
local_path
source_url
mime_type
size_bytes
sha256
created_at
```

### job_events

```text
id
post_target_id
event_type
payload_json
created_at
```

---

## 10. Security

Hard rules:

```text
Never log access tokens
Never log refresh tokens
Never return tokens from API responses
Encrypt tokens at rest
Hash API keys
Validate redirect_uri against allowlist
Use OAuth state
Use PKCE where supported
Verify webhook signatures
Limit webhook body size
Rate-limit public API
```

API auth:

```text
Authorization: Bearer <connector_api_key>
```

API keys stored hashed; only plaintext shown once at creation.

For local single-user mode, optional static API key is acceptable.

---

## 11. Publishing state machine

```text
CREATED
  ↓
QUEUED
  ↓
VALIDATING
  ↓
UPLOADING
  ↓
PROCESSING
  ↓
PUBLISHED
```

Failure branches:

```text
VALIDATING → FAILED
UPLOADING  → RETRY / FAILED
PROCESSING → POLL / RETRY / FAILED
ANY        → NEEDS_REAUTH
ANY        → CANCELLED
```

Never mark provider job `published` merely because HTTP request returned 200/201 when provider exposes an async publish-status flow.

---

## 12. Media pipeline

Input:

```text
URL
local file
multipart upload
```

Normalize:

```text
download
→ MIME detect
→ size check
→ SHA-256
→ optional ffprobe
→ provider validation
→ provider upload
```

Never re-encode media unless adapter requires it.

Media object should contain:

```text
mime
width
height
duration
size
sha256
```

Use FFmpeg only for provider-specific conversion or validation.

---

## 13. Provider capability contract

Each provider exposes:

```json
{
  "text": true,
  "image": true,
  "video": true,
  "carousel": false,
  "multi_image": false,
  "documents": false,
  "scheduled_publish": true,
  "delete": false,
  "status_poll": true,
  "webhooks": false,
  "requires_app_review": true
}
```

UI/API validation reads capabilities instead of hard-coding provider names.

---

## 14. Error taxonomy

Normalize errors:

```text
AUTH_INVALID
AUTH_EXPIRED
AUTH_REFRESH_FAILED
PERMISSION_DENIED
ACCOUNT_NOT_FOUND
MEDIA_INVALID
MEDIA_TOO_LARGE
MEDIA_UNSUPPORTED
RATE_LIMITED
PROVIDER_UNAVAILABLE
PROVIDER_REJECTED
DUPLICATE
PROCESSING_TIMEOUT
UNKNOWN
```

Response example:

```json
{
  "code": "RATE_LIMITED",
  "retryable": true,
  "retry_after": 120,
  "provider": "tiktok"
}
```

Keep raw provider response in DB for debugging, but redact secrets.

---

## 15. API design

### Provider list

```http
GET /v1/providers
```

### Start OAuth

```http
GET /v1/connect/{provider}
```

### OAuth callback

```http
GET /v1/callback/{provider}
```

### Accounts

```http
GET /v1/accounts
DELETE /v1/accounts/{id}
POST /v1/accounts/{id}/reconnect
```

### Posts

```http
POST   /v1/posts
GET    /v1/posts
GET    /v1/posts/{id}
DELETE /v1/posts/{id}
POST   /v1/posts/{id}/cancel
```

### Jobs

```http
GET /v1/jobs/{id}
```

### Webhooks

```http
POST /v1/webhooks/{provider}
```

---

## 16. n8n workflow examples

### Auto-publish generated video

```text
Trigger
→ Generate content
→ FFmpeg / local file
→ POST /v1/posts
→ Wait / poll job
→ IF published
   → save URL
→ ELSE
   → route error
```

### Multi-platform cross-post

```json
{
  "text": "New video",
  "media": [
    {"url": "https://host/video.mp4", "type": "video"}
  ],
  "targets": [
    {"provider": "youtube", "account_id": "yt_1"},
    {"provider": "tiktok", "account_id": "tt_1"},
    {"provider": "linkedin", "account_id": "li_1"}
  ]
}
```

One automation → multiple adapters.

---

## 17. CLI

Optional but useful:

```bash
social-connect providers
social-connect auth linkedin
social-connect accounts
social-connect publish ./video.mp4 --text "hello"
social-connect job job_123
social-connect logs job_123
```

CLI calls same REST API. No duplicate business logic.

---

## 18. Project structure

```text
social-connector/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── accounts.py
│   │   ├── posts.py
│   │   ├── jobs.py
│   │   └── webhooks.py
│   ├── auth/
│   │   ├── oauth.py
│   │   ├── pkce.py
│   │   └── crypto.py
│   ├── core/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── events.py
│   │   └── errors.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── linkedin/
│   │   ├── facebook/
│   │   ├── instagram/
│   │   ├── tiktok/
│   │   ├── youtube/
│   │   └── x/
│   ├── services/
│   │   ├── connection_service.py
│   │   ├── publish_service.py
│   │   ├── media_service.py
│   │   └── retry_service.py
│   ├── workers/
│   │   ├── scheduler.py
│   │   └── publisher.py
│   └── db/
│       ├── session.py
│       └── migrations/
├── tests/
│   ├── unit/
│   ├── contract/
│   └── integration/
├── scripts/
├── data/
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── README.md
└── PRD.md
```

---

## 19. Implementation phases

### Phase 0 — research

- freeze provider API versions
- create developer apps
- document scopes
- document approval/audit requirements
- test OAuth manually
- test one text post + one image/video post

Exit condition:

```text
Every MVP provider has confirmed official publish path.
```

### Phase 1 — core engine

Build:

- FastAPI
- SQLite
- API key auth
- OAuth state + PKCE
- encryption
- provider registry
- generic post/job models
- idempotency
- retry engine

No platform yet.

### Phase 2 — LinkedIn

Implement:

```text
OAuth
account discovery
text
image
video
status
errors
```

### Phase 3 — Meta

Implement separately:

```text
Facebook Page
Instagram Business/Creator
```

Reuse Meta OAuth infrastructure where appropriate, but keep publish adapters separate.

### Phase 4 — TikTok

Implement:

```text
creator info
video direct post
photo direct post
publish status
approval-state handling
```

TikTok-specific compliance must be explicit in code/docs. citeturn925021search0turn925021search5

### Phase 5 — YouTube

Implement:

```text
OAuth
channel discovery
video upload
metadata
visibility
upload status
```

### Phase 6 — X

Implement:

```text
OAuth
text
media
post ID
URL
error/rate-limit mapping
```

### Phase 7 — scheduler + n8n hardening

Add:

- scheduled posts
- dead-letter state
- structured logs
- webhook events
- n8n examples
- API docs
- Docker deployment

---

## 20. Testing strategy

### Unit tests

Test each adapter with mocked HTTP.

```text
OAuth URL
code exchange
refresh
account discovery
validation
media upload
publish
status
error mapping
```

### Contract tests

Given same universal post:

```text
provider A → valid request
provider B → transformed request
provider C → rejected before network call
```

### Integration tests

Use real developer accounts only in explicit integration-test environment.

Never commit credentials.

### Failure tests

Must simulate:

```text
401
403
404
409
429
500
502
503
network timeout
expired token
invalid media
async provider processing
```

---

## 21. Observability

Structured JSON logs:

```json
{
  "event": "publish_finished",
  "job_id": "job_123",
  "provider": "youtube",
  "status": "published",
  "duration_ms": 12000
}
```

Metrics:

```text
publish_total
publish_success_total
publish_failed_total
publish_retry_total
provider_http_429_total
oauth_refresh_total
```

No token values in logs.

---

## 22. Acceptance criteria

MVP is complete when:

```text
1. User can connect LinkedIn with OAuth.
2. User can discover publishing account.
3. API accepts one universal post schema.
4. Adapter publishes text post.
5. Adapter returns external ID/URL.
6. Scheduled job publishes without manual intervention.
7. Failed transient request retries automatically.
8. Permanent provider error becomes FAILED with normalized code.
9. Duplicate idempotency key does not create duplicate post.
10. Token refresh works without reconnect when provider supports refresh.
11. n8n can create/poll jobs through REST.
12. Secrets never appear in logs or API responses.
```

Then repeat same acceptance suite provider-by-provider.

---

## 23. Important architecture rule

Do NOT make one giant `social.py` containing all platforms.

Do this:

```text
Generic engine
    |
Provider interface
    |
Small isolated adapters
```

Reason:

```text
Provider API changes
→ update one adapter
→ scheduler/core stays stable
```

---

## 24. Recommended build path for this project

Start from Postiz's architecture ideas, not from copying its whole application.

Target:

```text
FastAPI
+ SQLite
+ official APIs
+ provider registry
+ encrypted OAuth connections
+ scheduler
+ n8n REST API
```

Keep first release small:

```text
LinkedIn + Facebook Pages + Instagram + TikTok + YouTube + X
```

After stable publishing, add more providers.

The main reusable asset is not platform code. It is the normalized connector contract:

```text
connect
→ validate
→ upload
→ publish
→ track
→ retry
→ report
```

---

## 25. Research sources

- Postiz GitHub: https://github.com/gitroomhq/postiz-app citeturn344715search1
- Postiz releases: https://github.com/gitroomhq/postiz-app/releases citeturn344715search6
- Postiz provider docs: https://github.com/gitroomhq/postiz-docs/blob/main/self-host/providers/overview.mdx citeturn147565search1
- Postiz public integrations controller: https://github.com/gitroomhq/postiz-app/blob/main/apps/backend/src/public-api/routes/v1/public.integrations.controller.ts citeturn147565search6
- Mixpost GitHub: https://github.com/inovector/MixpostApp citeturn344715search8
- Mixpost releases: https://github.com/inovector/mixpost/releases citeturn344715search9
- Socioboard GitHub: https://github.com/socioboard/Socioboard-5.0 citeturn908997search0
- Nango GitHub: https://github.com/NangoHQ/nango citeturn908997search2
- TikTok Content Posting API: https://developers.tiktok.com/docs/en/content-posting-api-get-started citeturn925021search0
- TikTok Direct Post reference: https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post citeturn925021search1
- YouTube `videos.insert`: https://developers.google.com/youtube/v3/docs/videos/insert citeturn925021search3
- LinkedIn Posts API: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api citeturn830343search0
