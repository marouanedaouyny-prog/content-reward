# Dependency audit

Audit date: 2026-10-20. This is a repository and installed-environment audit,
not a guarantee that every upstream release or platform combination was tested.
No package was installed for this audit. Runtime requirements come from
`pyproject.toml`; the optional transcription and development groups stay optional.

| Dependency | Class | Purpose / current alternative | Benefit and cost | License / Windows evidence | Decision |
|---|---|---|---|---|---|
| Python standard library (`sqlite3`, `subprocess`, `threading`, `hashlib`) | REQUIRED | Persistence, bounded process execution, resource gates, hashing | No extra install; synchronous operations need explicit timeouts and process ownership | Python runtime is declared as >=3.11; Windows paths/processes are covered by project tests | Keep |
| FastAPI | REQUIRED | Local API; no current alternative | Typed routes and test client; API server remains an installed runtime dependency | Pinned in `pyproject.toml`; license metadata was absent in installed wheel, so confirm SPDX before redistribution | Keep |
| Uvicorn | REQUIRED | Serves FastAPI; no current alternative | Local server; adds runtime dependency | Pinned; installed distribution did not expose a license classifier | Keep |
| Pydantic v2 | REQUIRED | Request/domain/config validation | Prevents permissive configuration and payload handling; adds validation dependency | Pinned; installed distribution did not expose a license classifier | Keep |
| python-multipart | REQUIRED | FastAPI multipart endpoints | Needed only by upload routes; keep while supported routes require it | Pinned; installed distribution did not expose a license classifier | Keep; verify whether route surface can remove it |
| yt-dlp[default] | REQUIRED | Public metadata, captions, search and bounded section download | One provider covers current public-source flow; upstream changes can affect extractors | Pinned; project wraps it with finite timeouts and retries; license should be confirmed from upstream metadata before redistribution | Keep; never enable full-video fallback |
| PyYAML | REQUIRED | Non-secret YAML defaults/profiles | Small config parser; schema validation remains Pydantic's responsibility | Installed metadata reports MIT | Keep |
| tzdata | REQUIRED | IANA timezone database fallback for `zoneinfo`, required on Windows hosts without system zone files | Small pure-Python-data wheel; enables configured timezone and daylight-saving rules cross-platform | PyPI identifies Apache-2.0; current project pin is `2026.5` | Keep; this is required by timezone-aware scheduling |
| opencv-python-headless | REQUIRED | Optional local face/speaker framing helpers | Enables existing CV path without GUI packages; native wheel size and CPU cost | Installed metadata reports Apache-2.0; installed on this Windows environment | Keep until measured removal/optionalization is safe |
| FFmpeg / ffprobe | REQUIRED external executable | Trim, encode, probe, subtitles and media QC | Broad media support; subprocess and encode time dominate rendering | Not a Python package; project checks executable availability and owns child processes on Windows | Keep external and report missing tools clearly |
| faster-whisper | OPTIONAL (`transcription`) | Local section transcription; no equivalent within core without a speech engine | Accurate timed words without uploading media; model download, RAM and CPU/GPU cost | Optional pin; installed metadata reports MIT; native CTranslate2/PyAV support still depends on chosen wheel/device | Keep optional; use public captions first |
| requests | OPTIONAL (`transcription`) | Used by existing transcription setup/runtime support | Small HTTP helper; duplicates other HTTP stacks if introduced into core | Optional range; installed metadata reports Apache-2.0 | Keep only with transcription extra |
| pytest / pytest-asyncio | DEV | Automated tests | Test coverage; no production runtime cost | Dev pins; pytest reports MIT and pytest-asyncio Apache-2.0 | Keep dev-only |
| httpx | DEV | API integration tests | ASGI test client; no separate production need | Dev pin; installed metadata reports BSD-3-Clause | Keep dev-only |
| Ruff | DEV | Linting | Fast static checks; no runtime cost | Dev pin; installed metadata did not include a license classifier | Keep dev-only |
| httpx async client | OPTIONAL / NOT ADOPTED | Would centralize new outbound HTTP calls; existing network media flow uses yt-dlp and bounded standard-library/provider requests | Pooling/async are useful only if a measured multi-request path needs them; would duplicate clients today | No project runtime dependency or Windows test evidence | Do not add until a concrete concurrent network path is measured |
| Tenacity | OPTIONAL / NOT ADOPTED | Retry library; current `app.core.errors.retry_delay` and persisted stage retry state already provide finite policy | Avoids hand-written retry duplication only if converted consistently; adds dependency and may obscure persisted attempts | No project dependency or Windows evidence | Do not add; consolidate on current retry policy |
| Pydantic Settings | OPTIONAL / NOT ADOPTED | Environment configuration; current `app.core.config` validates YAML and explicit env overrides | Could reduce custom env parsing but duplicates Pydantic/config merge behavior | No project dependency or Windows evidence | Reconsider only if config sources grow |
| Typer / Rich | OPTIONAL / NOT ADOPTED | CLI presentation; current argparse CLI and text output work in wrappers | Richer UX but not needed for canonical commands and creates more dependencies | No project dependency or Windows evidence | Keep argparse until UX requirements justify change |
| SQLAlchemy / Alembic | OPTIONAL / REJECTED FOR CURRENT SCOPE | ORM and migrations; current repository uses explicit SQLite SQL, transactions and versioned migrations | ORM adds abstraction and dependency cost without multi-database need | No project dependency or Windows evidence | Keep SQLite repository layer; reassess only for a real migration need |
| APScheduler | OPTIONAL / NOT ADOPTED | In-process schedule triggers; current persisted workers and retry scheduling own jobs | Could simplify calendar triggers but does not make publishing authorized or reliable across restarts by itself | No project dependency or Windows evidence | Defer; use persisted local queue and manual review |
| Silero VAD | OPTIONAL / NOT ADOPTED | Speech-region detection; faster-whisper currently supplies VAD filtering and project QC measures speech/silence | Potentially lower transcription cost; adds model/runtime complexity | No project dependency or Windows evidence | Benchmark against current VAD before adoption |
| PySceneDetect | OPTIONAL / NOT ADOPTED | Scene-change signal | Could help visual candidate/reframing cues; no current measured need | No project dependency or Windows evidence | Defer until candidate quality can be compared on a labeled sample |
| MediaPipe / Ultralytics YOLO | OPTIONAL / NOT ADOPTED | Face/person detection and tracking | May improve framing where the current OpenCV face path is unreliable; substantial native/model cost | No project dependency or Windows evidence established here | Do not add without a Windows compatibility and crop-quality benchmark |
| sentence-transformers / FAISS | OPTIONAL / NOT ADOPTED | Semantic deduplication and retrieval | Can improve semantic similarity at larger scale; model download and memory cost | No project dependency or Windows evidence | Current lexical/overlap dedup is sufficient for current local scale; evaluate on labeled duplicate pairs first |
| structlog | OPTIONAL / NOT ADOPTED | Structured logging | Could offer richer processors; current JSON event logger already emits redacted structured fields | No project dependency or Windows evidence | Do not add unless logger gaps are demonstrated |
| KeyBERT / YAKE / spaCy / librosa / Redis / Dramatiq / RQ / PostgreSQL | OPTIONAL / NOT ADOPTED | Keywords, entities, audio analysis, distributed cache/jobs/database | Each adds an operational or model cost; current local SQLite and deterministic extraction are simpler | No project dependency or Windows evidence established here | Defer until measured data volume or accuracy requires them |

## Findings and follow-up

- The installed Windows environment matches the declared core pins inspected in
  `pyproject.toml`; that is evidence of this environment only, not every Windows
  Python version or GPU configuration.
- Installed metadata for several projects omitted a license field/classifier.
  Resolve that against each upstream distribution's license before making a
  redistribution claim; this audit deliberately does not infer licenses.
- Suggested libraries in the PRD are not automatic requirements. No dependency
  should be added without an isolated Windows install check, license review, and
  measurable benefit against the current implementation.
- Re-run this audit when changing `pyproject.toml`, supported Python versions,
  native media dependencies, or packaging.
