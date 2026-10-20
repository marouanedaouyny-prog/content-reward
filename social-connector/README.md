# Social Media Auto-Publishing Connector

A self-hosted social media publishing service that connects to official platform APIs.

## Quick Start

```bash
cd social-connector
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run
python -m app.main
```

## Architecture

```
social-connector/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration
│   ├── api/                 # REST API endpoints
│   │   ├── auth.py          # OAuth flows
│   │   ├── accounts.py      # Account management
│   │   ├── posts.py         # Publishing API
│   │   ├── jobs.py          # Job status
│   │   └── webhooks.py      # Platform webhooks
│   ├── auth/                # OAuth utilities
│   │   ├── oauth.py         # OAuth flows
│   │   ├── pkce.py          # PKCE support
│   │   └── crypto.py        # Encryption
│   ├── core/
│   │   ├── models.py        # Database models
│   │   ├── schemas.py       # Pydantic schemas
│   │   ├── events.py        # Event system
│   │   └── errors.py        # Error taxonomy
│   ├── providers/           # Platform adapters
│   │   ├── base.py          # Base provider interface
│   │   ├── registry.py      # Provider registry
│   │   ├── linkedin/        # LinkedIn adapter
│   │   ├── facebook/        # Facebook adapter
│   │   ├── instagram/       # Instagram adapter
│   │   ├── tiktok/          # TikTok adapter
│   │   ├── youtube/         # YouTube adapter
│   │   └── x/               # X adapter
│   ├── services/            # Business logic
│   │   ├── connection_service.py
│   │   ├── publish_service.py
│   │   ├── media_service.py
│   │   └── retry_service.py
│   ├── workers/             # Background workers
│   │   ├── scheduler.py     # APScheduler
│   │   └── publisher.py     # Publish worker
│   └── db/
│       ├── session.py       # Database session
│       └── migrations/      # Alembic migrations
├── data/                    # SQLite + media storage
├── tests/                   # Unit/integration tests
├── scripts/                 # CLI scripts
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Provider Interface

Each platform implements the `SocialProvider` abstract base class:

```python
class SocialProvider(ABC):
    id: str
    
    async def get_authorization_url(self, state: str, code_challenge: str | None = None) -> str
    async def exchange_code(self, code: str, redirect_uri: str) -> dict
    async def refresh_token(self, connection: dict) -> dict
    async def get_accounts(self, connection: dict) -> list[dict]
    async def validate_post(self, account: dict, post: dict) -> dict
    async def publish(self, account: dict, post: dict) -> dict
    async def get_status(self, account: dict, external_post_id: str) -> dict
    async def delete(self, account: dict, external_post_id: str) -> dict
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/providers` | List available providers |
| GET | `/v1/connect/{provider}` | Start OAuth flow |
| GET | `/v1/callback/{provider}` | OAuth callback |
| GET | `/v1/accounts` | List connected accounts |
| POST | `/v1/posts` | Create publish job |
| GET | `/v1/posts` | List posts |
| GET | `/v1/posts/{id}` | Get post details |
| POST | `/v1/posts/{id}/cancel` | Cancel queued post |
| GET | `/v1/jobs/{id}` | Get job status |
| POST | `/v1/webhooks/{provider}` | Platform webhooks |

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start development server
python -m app.main

# Run tests
pytest tests/
```

## Configuration

Key environment variables in `.env`:

```env
# App
APP_ENV=development
APP_SECRET=your-secret-key
DATABASE_URL=sqlite:///./data/app.db
MEDIA_DIR=./data/media

# Encryption
ENCRYPTION_KEY=your-32-byte-key

# LinkedIn
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_REDIRECT_URI=http://localhost:8000/v1/callback/linkedin

# Facebook/Instagram
FACEBOOK_APP_ID=...
FACEBOOK_APP_SECRET=...
FACEBOOK_REDIRECT_URI=http://localhost:8000/v1/callback/facebook

# TikTok
TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
TIKTOK_REDIRECT_URI=http://localhost:8000/v1/callback/tiktok

# YouTube
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REDIRECT_URI=http://localhost:8000/v1/callback/youtube

# X (Twitter)
X_CLIENT_ID=...
X_CLIENT_SECRET=...
X_REDIRECT_URI=http://localhost:8000/v1/callback/x
```

## Integration with Empire OS

The connector receives jobs from n8n/Empire OS via REST API:

```bash
# From n8n/Empire OS
curl -X POST http://localhost:8000/v1/posts \
  -H "Authorization: Bearer <api-key>" \
  -d '{
    "text": "Hello world",
    "media": [{"url": "https://example.com/video.mp4", "type": "video"}],
    "targets": [
      {"provider": "linkedin", "account_id": "acc_1"},
      {"provider": "tiktok", "account_id": "acc_2"}
    ]
  }'
```

## Security

- Tokens encrypted at rest with Fernet (AES-256)
- OAuth state + PKCE for authorization
- Never logs tokens
- API key authentication
- Webhook signature verification
- Rate limiting on public endpoints

## License

MIT