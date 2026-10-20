# content-reward

Local automation workspace for content preparation and workflow experiments.

## Working clipping entry point

For the automatic **IShowSpeed test**, double-click **`start-ishowspeed.cmd`**
on Windows, or run **`.\start-ishowspeed.ps1`**. It
opens a saved workflow with source selection, English subtitles, automatic
cut planning, vertical rendering and download retries; no intake choices or
preview approval clicks are required. Open **http://127.0.0.1:8000/** to see the
result or its actual connection state. This prepares a private local preview,
not a published post. See the [automatic test setup](clipping/README.md).

The supported workspace includes YouTube source inspection, optional transcript-based cut planning, and local metadata research across niches. Read the [clip research and data guide](clipping/RESEARCH_GUIDE.md) for how the data works and what has been verified. The demo is synthetic; the tool does not predict viral outcomes or automatically publish.

It also includes a persistent **Trending research** agent that scans six niches,
saves observed source metrics, and can queue the best eligible private preview.
Downloads resume partial files, cap source quality at 1080p and use four parallel
fragment connections. Temporary failures keep retrying with saved backoff;
Pause and cancellation remain effective. See the [setup guide](clipping/README.md#trending-research-agent).

The supervised Content Rewards clipping workflow has its own browser workspace, background worker, saved approvals, real FFmpeg exports, and direct HTTP job intake. Its built-in engine runs the workflow without n8n. Start here for the clipping niche:

```powershell
python -m pip install -r requirements-clipping.txt
python -m clipping
```

Open **http://127.0.0.1:8000/** and click **Try a five-second practice clip**. FFmpeg and ffprobe must be available on PATH. For real campaigns, the workspace prepares clips and guides operator publication, submission, and reward confirmation. See the [clipping setup guide](clipping/README.md) for Docker, optional transcription, and direct API automation.

Automatic English subtitles are installed in the project's `.venv`, with a local `tiny.en` model. Run **`.\.venv\Scripts\python.exe -m clipping`** to use those libraries, and select **English** in the workspace. `.\setup-transcription.ps1` checks that setup; use `-Model small` to download the multilingual model when internet access is available. The workspace also imports SRT files and includes a five-second subtitle demo.

The legacy applications below still have unresolved review findings. Use `docker-compose.clipping.yml` for this clipping entry point; the original Compose stack is not the validated setup for it.

## Legacy application setup

### Prerequisites
- Docker Desktop
- Python 3.11+
- Node.js 20+
- FFmpeg
- yt-dlp

### One-Command Start (Docker)

```bash
# Clone and enter
git clone <repo>
cd automation-empire-os

# Start all services
docker compose up -d

# Services:
# - Ollama (local LLM): http://localhost:11434
# - n8n (orchestration): http://localhost:5678 (admin/changeme)
# - Empire API: http://localhost:8000
# - Empire Frontend: http://localhost:3000
```

### Local Development

```bash
# Python environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -r requirements.txt

# Install yt-dlp
pip install yt-dlp

# Start Ollama (separate terminal)
ollama serve
ollama pull llama3.2

# Start n8n (separate terminal)
n8n start

# Start API
python -m uvicorn backend.app.main:app --reload --port 8000

# Start Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    EMPIRE OS                                 │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ DISCOVER │  │  BUILD   │  │ DISTRIB. │  │ ANALYTICS│    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │             │             │             │           │
│       └─────────────┼─────────────┼─────────────┘           │
│                     ▼             ▼                         │
│              ┌──────────┐  ┌──────────┐                     │
│              │ORCHESTR. │  │ AI ROUTER│                     │
│              └────┬─────┘  └────┬─────┘                     │
│                   │             │                           │
│                   └──────┬──────┘                           │
│                          ▼                                  │
│                    ┌──────────┐                             │
│                    │  QUEUE   │  (SQLite-backed)            │
│                    └────┬─────┘                             │
│                         │                                   │
│         ┌───────────────┼───────────────┐                   │
│         ▼               ▼               ▼                   │
│    ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│    │ PYTHON   │   │ SCRAPER  │   │  MEDIA   │             │
│    │ WORKERS  │   │ WORKERS  │   │ WORKERS  │             │
│    └────┬─────┘   └────┬─────┘   └────┬─────┘             │
│         │              │              │                     │
│         └──────────────┼──────────────┘                     │
│                        ▼                                    │
│                  ┌──────────┐                               │
│                  │   DB     │  (SQLite → Postgres)          │
│                  └────┬─────┘                               │
│                       │                                     │
│                       ▼                                     │
│                  ┌──────────┐                               │
│                  │ANALYTICS │                               │
│                  └──────────┘                               │
└─────────────────────────────────────────────────────────────┘
```

## Workflows

| Workflow | Schedule | Description |
|----------|----------|-------------|
| `content_rewards` | Daily 6AM UTC | Campaign discovery → clip generation → publishing → tracking |
| `lead_generation` | Weekly Mon 8AM | Source discovery → extraction → scoring → export |
| `product_research` | Weekly Sun 9AM | Market scan → trend detection → opportunity scoring → report |

## $0 Constraint

- **Local-first**: Everything runs on your machine
- **No paid APIs required**: Ollama for AI, SQLite for DB, n8n for orchestration
- **Optional free tiers**: OpenRouter, Gemini, Groq as fallbacks (disabled by default)
- **Hard rule**: `ALLOW_PAID_SERVICES=false` enforced in code

## Project Structure

```
├── backend/                 # FastAPI application
│   └── app/
│       ├── core/           # Config, DB models
│       └── main.py         # API endpoints
├── scripts/                # Python workers
│   ├── worker_base.py      # Base worker class
│   ├── content_rewards_workers.py
│   ├── empire_workers.py   # Lead gen, product research
│   └── orchestrator.py     # Workflow orchestration
├── workflows/              # Workflow definitions (YAML + schemas)
│   ├── content_rewards/
│   ├── lead_generation/
│   └── product_research/
├── n8n/workflows/          # n8n workflow JSON imports
├── frontend/               # Next.js dashboard
├── tests/
│   ├── unit/
│   └── integration/
├── storage/                # Artifact filesystem
│   ├── raw/
│   ├── processed/
│   ├── output/
│   └── exports/
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health |
| GET | `/api/v1/workflows` | List workflows |
| POST | `/api/v1/workflows/{id}/run` | Execute workflow |
| GET | `/api/v1/jobs` | List jobs |
| GET | `/api/v1/jobs/{id}` | Job status |
| POST | `/api/v1/jobs/{id}/approve` | Human approval |
| GET | `/api/v1/campaigns` | List campaigns |
| POST | `/api/v1/campaigns/import` | Import campaign |
| GET | `/api/v1/clips` | List clips |
| GET | `/api/v1/published-posts` | List published posts |
| GET | `/api/v1/earnings` | Earnings summary |
| GET | `/api/v1/providers/health` | Provider status |
| GET | `/api/v1/system/cost` | Cost tracking |
| POST | `/api/v1/system/kill-switch` | Emergency stop |

## Workers

All workers inherit from `BaseWorker` and implement `execute(payload) -> WorkerResult`:

### Content Rewards
- `campaign_discovery` - Find campaigns from URLs/HTML/manual
- `campaign_parser` - Extract structured requirements
- `source_download` - Download videos via yt-dlp
- `clip_generator` - Generate clips via FFmpeg (9:16, 16:9, 1:1)
- `quality_check` - Automated QC (resolution, codec, duration, aspect)

### Lead Generation
- `lead_source_discovery` - Web/social/directory sources
- `lead_export` - CSV/JSON/SQLite export

### Product Research
- `product_scan` - Marketplace/competitor/trend scanning
- `product_report` - Markdown/JSON reports

## Configuration

Environment variables (`.env.local`):
```env
APP_ENV=development
APP_SECRET=your-random-secret
DATABASE_URL=sqlite:///./data/empire.db
STORAGE_DIR=./storage
LOG_DIR=./logs

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=llama3.2

# Optional free-tier fallbacks (disabled by default)
OPENROUTER_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=

# Platform credentials
WHOP_API_KEY=
TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=

N8N_BASE_URL=http://localhost:5678
N8N_API_KEY=

KILL_SWITCH=false
DRY_RUN=false
ALLOW_PAID_SERVICES=false
DEPLOY_MODE=local
```

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# All tests
pytest -v
```

## Adding New Workflows

1. Create directory: `workflows/new_workflow/`
2. Add `workflow.yaml` (see existing examples)
3. Add `inputs_schema.json` and `outputs_schema.json`
4. Add `README.md`
5. Create workers in `scripts/`
6. Register workers in `WorkerRegistry`
7. Add n8n workflow in `n8n/workflows/`
8. Import n8n workflow via UI or API

## License

MIT - Build your empire.
