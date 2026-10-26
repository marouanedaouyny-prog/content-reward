# Content Reward implementation plan

Baseline: `6fd405d`. Execute on `refactor/content-reward-hardening` in the PRD's
phase order. User has authorized automatic execution; no additional plan approval
is required. Preserve all local data and credential files. No external publishing.

## Design decisions

Keep the established `clipping` import surface and tested media implementation.
Add focused packages for new selection, quality, and pipeline behavior; do not
rename `captions.py` into a directory just to imitate a suggested tree. A small
`app/core` and `app/repositories` layer provides shared configuration, migrations,
and state; `clipping.app` remains the actual FastAPI entry point. Campaigns,
publication, and analytics depend on shared models/repositories, never on legacy.
One SQLite domain store owns orders/events/campaigns/publications/performance;
existing job databases remain compatible and are migrated additively. Manifest
JSON is a recovery/import and human-readable export, not the final state owner.

## Ordered increments and exact new/modified files

Each row is a logical increment; split the row further when tests expose coupling.
For every behavior change: failing test, implementation, affected tests, smoke,
lint when configured, then a focused commit. Run the full suite after major moves
and at completion. Never install a paid dependency or download a real video to test.

| Phase | File | Proposed change and acceptance |
|---|---|---|
| 1 | `docs/AUDIT.md` | Factual baseline, risks, dependencies and evidence |
| 1 | `docs/REFACTOR_PLAN.md` | This plan and exhaustive move manifest below |
| 1 | `PRD.md` | Canonical deduplicated requirements and preserved workflow constraints |
| 1 | `tasks/plan.md`, `tasks/todo.md` | Link plan and track verified phase completion; archive old task notes |
| 2 | `legacy/**` | Tracked-file moves listed below; retain legacy-relative imports/paths |
| 2 | `docs/LEGACY.md`, `legacy/README.md` | Execution context, dependencies, preserved local files, deletion criteria |
| 2 | `pyproject.toml`, `requirements.txt`, `requirements-clipping.txt`, `requirements-transcription.txt` | Single supported dependency source with optional transcription/dev groups and explicit supported test roots |
| 2 | `Dockerfile.clipping`, `docker-compose.yml`, `.dockerignore`, `.gitignore` | Default container points to clipping; exclude credentials and outputs |
| 3 | `config/default.yaml`, `config/development.yaml`, `config/production.yaml`, `.env.example` | Central non-secret defaults and validated overrides; retain studio vs production colorized settings |
| 3 | `app/__init__.py`, `app/core/__init__.py`, `app/core/config.py` | Strict typed settings, environment overrides, finite ranges, resource limits |
| 3 | `app/core/errors.py`, `app/core/logging.py`, `app/core/state.py` | Normalized retryable errors, secret redaction, required JSON event fields, valid transition graph |
| 3 | `clipping/workflow.py`, `clipping/orchestrator.py`, `clipping/autorun.py` | Wire finite retries, config defaults, structured events and durable transition history |
| 3 | `clipping/pipeline/__init__.py`, `clipping/pipeline/checkpoints.py` | Verify paths/hashes, invalidate dependent checkpoints and reuse valid work |
| 4 | `clipping/selection/__init__.py`, `clipping/selection/scoring.py`, `clipping/selection/dedup.py` | Configured scoring with per-signal evidence and missing-signal reporting; optional supplied embeddings, overlap/text/quote gates |
| 4 | `clipping/planning.py`, `clipping/sections.py`, `clipping/clip_history.py` | Integrate scoring/dedup with existing transcript/replay/QA generation; preserve editorial provenance |
| 4 | `clipping/quality/__init__.py`, `clipping/quality/validation.py`, `clipping/clip_review.py`, `clipping/media.py` | Pre-render complete-thought/ads/speech/duration checks; post-render decode/audio/FPS/black/silence/subtitle/file-size gates; bounded remote downloads |
| 5 | `app/repositories/__init__.py`, `app/repositories/database.py`, `app/repositories/store.py` | Versioned transactional SQLite migrations, normalized domain records and repositories |
| 5 | `app/repositories/cache.py`, `clipping/sections.py`, `clipping/trends.py` | Deterministic TTL cache for source captions/replay, bounded sections and same-run search recovery; hashes verify cached media, while new orders still search fresh |
| 5 | `app/models/__init__.py`, `app/models/domain.py` | Validated stable-ID domain records, artifact references and performance models |
| 5 | `clipping/orchestrator.py`, `clipping/batch.py`, `clipping/production.py` | Persist orders/sources/candidates/clips/artifacts; import old manifests once, export JSON from DB state |
| 5 | `clipping/autorun.py`, `clipping/clip_history.py` | Read latest order and historical reservations from DB after one-time historical manifest import; JSON exports never override committed state |
| 6 | `campaigns/__init__.py`, `campaigns/models.py`, `campaigns/rules.py`, `campaigns/validation.py` | Structured/manual rules, conservative parser warnings, source/clip/metadata/platform eligibility with failure gates |
| 6 | `clipping/workflow.py`, `clipping/batch.py` | Apply campaign checks before work and preserve preview-only authorization status |
| 7 | `publishing/__init__.py`, `publishing/base.py`, `publishing/manager.py`, `publishing/manual.py`, `publishing/mock.py` | Idempotent manual export and explicitly simulated mock; persisted statuses, hashes, IDs/URLs; validation required, network publication disabled |
| 7 | `publishing/youtube/__init__.py`, `publishing/instagram/__init__.py`, `publishing/tiktok/__init__.py` | Explicit unavailable official-adapter boundaries, never fabricated uploads |
| 8 | `analytics/__init__.py`, `analytics/models.py`, `analytics/collectors.py`, `analytics/feedback.py`, `analytics/reports.py` | Validated imported observations, reward provenance, bounded sample-supported score adjustment, experiments/variant comparison and business metrics |
| 8 | `clipping/selection/scoring.py`, `clipping/production.py` | Use persisted feedback only where supported; record source moment/settings features |
| 9 | `clipping/cli.py`, `clipping/__main__.py`, `scripts/smoke_test.py`, `scripts/__init__.py` | Canonical CLI plus old API flags, run/resume/status/worker/api/list/validate/report/smoke; offline runtime probes |
| 9 | `tests/unit/test_config.py`, `tests/unit/test_state_errors.py`, `tests/unit/test_selection.py`, `tests/unit/test_quality.py`, `tests/unit/test_store.py`, `tests/unit/test_campaigns.py`, `tests/unit/test_publishing.py`, `tests/unit/test_analytics.py`, `tests/unit/test_checkpoints.py`, `tests/unit/test_cli.py` | Business behavior and invalid input regressions |
| 9 | `tests/integration/test_pipeline.py`, `tests/integration/test_domain_api.py` | Synthetic render/QC, resume, manual-export and observation persistence without network |
| 3–4 | `tests/clipping/test_download_resilience.py`, `tests/clipping/test_trends.py`, `tests/clipping/test_clip_review.py` | Update explicitly superseded infinite-retry expectations and add stronger QC regressions; retain saved backoff and restart behavior |
| 9 | `app/api/__init__.py`, `app/api/routes.py`, `clipping/app.py` | Typed compatible domain routes; no dashboard redesign |
| 10 | `README.md`, `PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/PIPELINE.md`, `docs/CONFIGURATION.md`, `docs/TROUBLESHOOTING.md`, `AGENTS.md` | Current commands, runtime ownership, evidence, limitations and preserved operator preferences |

## Verification checkpoints

1. Audit baseline: inspect tracked files/imports, run 406-test clipping suite.
2. Isolation: all existing clipping tests pass; legacy remains importable in its
   own execution root when its optional historical dependencies are installed.
3. Config/state: invalid overrides and transitions fail; retry limit terminates;
   damaged artifacts invalidate only necessary stages; logs redact secrets.
4. Selection/QC: known stronger fixtures rank higher for documented reasons;
   duplicate/advertising/incomplete windows fail; synthetic exports decode.
5. Data: migrations repeat safely, preserve old tables/records and enforce FKs;
   concurrency/idempotency and DB-over-manifest ownership are covered.
6. Campaign/publishing: violations block export/publication; manual export
   never claims a real upload; same key cannot publish changed content.
7. Analytics: unknown observations stay unknown; real samples influence ranking
   gradually; variant summaries expose sample counts and unmeasured metrics.
8. Final: supported tests, lint/type checks, smoke, CLI commands, container context,
   secret scan and documented remaining external integration limits.

## Final implementation evidence

The phase checklist in `tasks/todo.md` records completion. Final supported-suite,
Ruff, smoke and isolated-wheel results are recorded in `docs/AUDIT.md`. The wheel
was imported from an external working directory and its API/worker smoke checks
passed. Build and smoke fixtures were confined to ignored `.workflow-tests/` and
temporary directories. The supported workflow did not publish or access social
accounts.

## Risks and mitigations

- Do not move whole on-disk directories: ignored `.env`, DBs, caches, sessions,
  and media may be present. Move tracked files individually and retain local data.
- Keep SQLite backups/import exports; additive migrations run in transactions.
- Import historical manifests under the existing per-order lock, mark each import
  transactionally, and never overwrite an existing DB order from JSON. Use SQLite
  backup API for any existing DB snapshot, not raw copies of live WAL files.
- Legacy startup instructions must explicitly address original data/env paths;
  relocating code must not silently select a blank database or lose encryption keys.
- Independent caption agreement is conditional on source-reference cues; absent
  evidence remains unverified and must be visible in QC results.
- No invented semantic/emotion/audio-energy evidence. Optional embeddings are
  evaluated only when supplied; missing signals are explicit.
- Concurrency stays conservative (one render and transcription job by default).
- Do not expose unauthenticated API over the network or enable publishing.

## Exhaustive tracked-file move manifest

Generated below from the audited Git inventory before implementation. All other
tracked files remain in place unless explicitly listed in the increments above.

| Existing tracked file | Destination |
|---|---|
| `Dockerfile.api` | `legacy/Dockerfile.api` |
| `Dockerfile.frontend` | `legacy/Dockerfile.frontend` |
| `PRD(1).md` | `legacy/PRD(1).md` |
| `architecture/campaign_model.md` | `legacy/architecture/campaign_model.md` |
| `architecture/compliance_engine.md` | `legacy/architecture/compliance_engine.md` |
| `architecture/content_pipeline.md` | `legacy/architecture/content_pipeline.md` |
| `architecture/cost_matrix.md` | `legacy/architecture/cost_matrix.md` |
| `architecture/database.md` | `legacy/architecture/database.md` |
| `architecture/final_plan.md` | `legacy/architecture/final_plan.md` |
| `architecture/hermes_architecture.md` | `legacy/architecture/hermes_architecture.md` |
| `architecture/security.md` | `legacy/architecture/security.md` |
| `architecture/state_machine.md` | `legacy/architecture/state_machine.md` |
| `architecture/workflows.md` | `legacy/architecture/workflows.md` |
| `backend/app/core/config.py` | `legacy/backend/app/core/config.py` |
| `backend/app/core/db.py` | `legacy/backend/app/core/db.py` |
| `backend/app/main.py` | `legacy/backend/app/main.py` |
| `docker-compose.yml` | `legacy/docker-compose.yml` |
| `frontend/app/globals.css` | `legacy/frontend/app/globals.css` |
| `frontend/app/layout.tsx` | `legacy/frontend/app/layout.tsx` |
| `frontend/app/page.tsx` | `legacy/frontend/app/page.tsx` |
| `frontend/next.config.js` | `legacy/frontend/next.config.js` |
| `frontend/package.json` | `legacy/frontend/package.json` |
| `n8n/workflows/clipping.json` | `legacy/n8n/workflows/clipping.json` |
| `n8n/workflows/content_rewards.json` | `legacy/n8n/workflows/content_rewards.json` |
| `n8n/workflows/lead_generation.json` | `legacy/n8n/workflows/lead_generation.json` |
| `n8n/workflows/product_research.json` | `legacy/n8n/workflows/product_research.json` |
| `prd(2).md` | `legacy/prd(2).md` |
| `project/.env.example` | `legacy/project/.env.example` |
| `project/config/settings.py` | `legacy/project/config/settings.py` |
| `project/db/crypto.py` | `legacy/project/db/crypto.py` |
| `project/db/models.py` | `legacy/project/db/models.py` |
| `project/main.py` | `legacy/project/main.py` |
| `project/requirements.txt` | `legacy/project/requirements.txt` |
| `project/scripts/init_db.py` | `legacy/project/scripts/init_db.py` |
| `project/skills/analytics/skill.py` | `legacy/project/skills/analytics/skill.py` |
| `project/skills/campaign_parser/skill.py` | `legacy/project/skills/campaign_parser/skill.py` |
| `project/skills/campaign_research/skill.py` | `legacy/project/skills/campaign_research/skill.py` |
| `project/skills/compliance/skill.py` | `legacy/project/skills/compliance/skill.py` |
| `project/skills/content_strategy/skill.py` | `legacy/project/skills/content_strategy/skill.py` |
| `project/skills/payout_tracking/skill.py` | `legacy/project/skills/payout_tracking/skill.py` |
| `project/skills/recovery/skill.py` | `legacy/project/skills/recovery/skill.py` |
| `project/skills/social_publishing/skill.py` | `legacy/project/skills/social_publishing/skill.py` |
| `project/skills/submission/skill.py` | `legacy/project/skills/submission/skill.py` |
| `project/skills/video_processing/skill.py` | `legacy/project/skills/video_processing/skill.py` |
| `requirements.txt` | `legacy/requirements.txt` |
| `scripts/__init__.py` | `legacy/scripts/__init__.py` |
| `scripts/agent_base.py` | `legacy/scripts/agent_base.py` |
| `scripts/agent_manager.py` | `legacy/scripts/agent_manager.py` |
| `scripts/agent_runner.py` | `legacy/scripts/agent_runner.py` |
| `scripts/agents.py` | `legacy/scripts/agents.py` |
| `scripts/ai_router.py` | `legacy/scripts/ai_router.py` |
| `scripts/content_rewards_workers.py` | `legacy/scripts/content_rewards_workers.py` |
| `scripts/empire_coordinator.py` | `legacy/scripts/empire_coordinator.py` |
| `scripts/empire_workers.py` | `legacy/scripts/empire_workers.py` |
| `scripts/main.py` | `legacy/scripts/main.py` |
| `scripts/orchestrator.py` | `legacy/scripts/orchestrator.py` |
| `scripts/real_pipeline.py` | `legacy/scripts/real_pipeline.py` |
| `scripts/worker_base.py` | `legacy/scripts/worker_base.py` |
| `social-connector/.dockerignore` | `legacy/social-connector/.dockerignore` |
| `social-connector/.env.example` | `legacy/social-connector/.env.example` |
| `social-connector/Dockerfile` | `legacy/social-connector/Dockerfile` |
| `social-connector/README.md` | `legacy/social-connector/README.md` |
| `social-connector/TIKTOK_SETUP.md` | `legacy/social-connector/TIKTOK_SETUP.md` |
| `social-connector/app/auth/crypto.py` | `legacy/social-connector/app/auth/crypto.py` |
| `social-connector/app/config.py` | `legacy/social-connector/app/config.py` |
| `social-connector/app/core/models.py` | `legacy/social-connector/app/core/models.py` |
| `social-connector/app/db/session.py` | `legacy/social-connector/app/db/session.py` |
| `social-connector/app/main.py` | `legacy/social-connector/app/main.py` |
| `social-connector/app/providers/base.py` | `legacy/social-connector/app/providers/base.py` |
| `social-connector/app/providers/facebook/provider.py` | `legacy/social-connector/app/providers/facebook/provider.py` |
| `social-connector/app/providers/instagram/provider.py` | `legacy/social-connector/app/providers/instagram/provider.py` |
| `social-connector/app/providers/linkedin/provider.py` | `legacy/social-connector/app/providers/linkedin/provider.py` |
| `social-connector/app/providers/registry.py` | `legacy/social-connector/app/providers/registry.py` |
| `social-connector/app/providers/tiktok/provider.py` | `legacy/social-connector/app/providers/tiktok/provider.py` |
| `social-connector/app/providers/youtube/provider.py` | `legacy/social-connector/app/providers/youtube/provider.py` |
| `social-connector/docker-compose.yml` | `legacy/social-connector/docker-compose.yml` |
| `social-connector/empire_integration.py` | `legacy/social-connector/empire_integration.py` |
| `social-connector/requirements.txt` | `legacy/social-connector/requirements.txt` |
| `str.txt` | `legacy/str.txt` |
| `tests/integration/test_workers.py` | `legacy/tests/integration/test_workers.py` |
| `tests/unit/test_core.py` | `legacy/tests/unit/test_core.py` |
| `workflows/content_rewards/README.md` | `legacy/workflows/content_rewards/README.md` |
| `workflows/content_rewards/inputs_schema.json` | `legacy/workflows/content_rewards/inputs_schema.json` |
| `workflows/content_rewards/outputs_schema.json` | `legacy/workflows/content_rewards/outputs_schema.json` |
| `workflows/content_rewards/workflow.yaml` | `legacy/workflows/content_rewards/workflow.yaml` |
| `workflows/lead_generation/README.md` | `legacy/workflows/lead_generation/README.md` |
| `workflows/lead_generation/inputs_schema.json` | `legacy/workflows/lead_generation/inputs_schema.json` |
| `workflows/lead_generation/outputs_schema.json` | `legacy/workflows/lead_generation/outputs_schema.json` |
| `workflows/lead_generation/workflow.yaml` | `legacy/workflows/lead_generation/workflow.yaml` |
| `workflows/product_research/README.md` | `legacy/workflows/product_research/README.md` |
| `workflows/product_research/inputs_schema.json` | `legacy/workflows/product_research/inputs_schema.json` |
| `workflows/product_research/workflow.yaml` | `legacy/workflows/product_research/workflow.yaml` |
