# Content Reward

Local-first Content Rewards clipping and review. The supported runtime is
`clipping/`; shared infrastructure lives in `app/`. Historical applications are
isolated in `legacy/` and are not imported by the current application.

The production workflow finds eligible long YouTube sources, reads public
captions and available replay evidence, selects distinct moments, downloads
only their bounded ranges, transcribes locally, renders vertical clips, checks
quality, and prepares files for review. Campaign rules and measured feedback
can guide selection. **Network publishing is disabled.**

## Quick start on Windows

Python 3.11+, FFmpeg 9.0+ with ffprobe, and the free `uv` package manager are required.

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[transcription,dev]"
.\.venv\Scripts\content-reward.exe smoke
.\.venv\Scripts\content-reward.exe api
```

Open <http://127.0.0.1:8000/> for the existing local workspace. To install without
uv, use `python -m venv .venv` followed by that environment's
`python -m pip install -e ".[transcription,dev]"`. FFmpeg must be on PATH.
`setup-transcription.ps1` can prepare the supported English model. The smoke
check imports Whisper but does not download a model; `/health` reports cached
model readiness. Real discovery requires working public YouTube access.

## Canonical commands

```powershell
.\.venv\Scripts\content-reward.exe run --target 20
.\.venv\Scripts\content-reward.exe run --new --target 40
.\.venv\Scripts\content-reward.exe resume
.\.venv\Scripts\content-reward.exe status
.\.venv\Scripts\content-reward.exe clips list
.\.venv\Scripts\content-reward.exe library
.\.venv\Scripts\content-reward.exe campaigns list
.\.venv\Scripts\content-reward.exe campaigns import campaign.json
.\.venv\Scripts\content-reward.exe metrics import performance.json
.\.venv\Scripts\content-reward.exe metrics report
.\.venv\Scripts\content-reward.exe worker --once
```

`python -m clipping run|resume|status|worker|api` provides the same commands.
`python -m clipping` without a command still starts the compatible local API.
`run` resumes the latest unfinished production order; `--new` explicitly starts
fresh discovery. `resume` preserves the saved count, source reservations, render
settings, and campaign. A configurable larger target never justifies duplicate
or weak clips: genuine insufficient-source results retain partial progress.

Use `--storage PATH` to select a separate workspace. The default is
`storage/clipping`. Finished files and post captions remain in the approved
single `clips/` root; new canonical runs organize exports into niche subfolders.
Use the workspace's **Niche library** section or `content-reward library` to browse
sports, streams, business, education, gaming, AI/technology, fitness and comedy.
Ambiguous sources appear under **Needs niche review**. Saved historical orders
retain their delivery paths. The library distinguishes missing, empty and changed
files from available exports; recorded processing status remains historical.
Read `clips/LATEST-CLIPS.txt` for the current completed batch.
Production uses **colorized/fit** captions and framing; general and historical
studio orders retain **studio/fit**. The approved visual template is preserved.

## Review and campaign eligibility

Import a structured campaign, then add `--campaign CAMPAIGN_ID` to a new run.
Rules check source restrictions, duration, forbidden terms, hashtags, destination
and deadline. Prose extraction always requires a structured-rule review.

```powershell
.\.venv\Scripts\content-reward.exe validate CLIP_ID
.\.venv\Scripts\content-reward.exe prepare CLIP_ID --campaign CAMPAIGN_ID --platform youtube --caption "Useful point #Example" --key review-001
```

`prepare` validates the campaign, clip hash, reviewed rules and recorded rights,
then exports a local review package. Its status is READY, with no public post ID
or URL. Official YouTube/Instagram/TikTok adapters deliberately report unavailable
access. Instagram identity verification does not authorize publishing.

## Configuration and architecture

Non-secret defaults are in `config/default.yaml`, with development/production
overlays and optional `CONTENT_REWARD_CONFIG`. `.env.example` documents environment
settings and blank credential names. Enter credentials locally using the existing
hidden prompts; never put them in committed YAML. Saved orders keep their settings.

```text
clipping/       discovery, selection, bounded media, captions, rendering and QC
app/            typed domain API, config/state/errors, SQLite migrations/repositories
campaigns/      structured rules, conservative parser and eligibility checks
publishing/     validated manual export, simulated mock, unavailable official adapters
analytics/      imported observations, experiments, reports and bounded feedback
config/         validated non-secret defaults and profiles
scripts/        smoke and supported maintenance commands
tests/          offline unit/integration tests and existing clipping regressions
docs/           audit, plan, architecture, pipeline, configuration and troubleshooting
legacy/         preserved experimental systems and their historical dependency pins
```

Orders are authoritative in `storage/clipping/content-reward.db`. Existing job
DBs remain compatible. Historical manifests are imported under their order locks
without overwriting existing DB records. JSON manifests are recovery/debug
exports. Additive migrations keep existing tables and create SQLite-consistent
pre-migration backups. Resume verifies artifact paths and hashes, including
subtitle sidecars, before reusing completed work.

## Verification

```powershell
.\.venv\Scripts\python.exe tests/clipping/run_tests.py tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\content-reward.exe smoke
```

Tests use fixtures/mocks, synthetic FFmpeg media, deliberate render failures and
corrupt-media regressions. They do not download large real videos or contact
social accounts. Historical legacy tests are intentionally excluded.

## Current limits

Editorial scores are traceable heuristics, not predictions of virality. Missing
replay, semantic embeddings, emotion, or audio-energy evidence stays unknown.
Machine QC cannot establish perfect speech accuracy or editorial/visual quality;
review the exported clips. Performance data currently comes from validated manual
or exported observations. Feedback needs multiple independent clips and is bounded;
small variant samples do not establish causation. No automatic campaign scraping,
verified official publishing, guaranteed reward, or hard process-wide memory cap
is claimed. CPU/concurrency limits and FFmpeg allocation limits are configurable.
Metric reports use the calendar span from the first to latest saved clip and
record render attempts explicitly. Reward/hour remains unknown until an order has
both imported clip rewards and recorded run duration.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [pipeline](docs/PIPELINE.md)
- [Configuration](docs/CONFIGURATION.md) and [troubleshooting](docs/TROUBLESHOOTING.md)
- [Legacy retention](docs/LEGACY.md) and [selection evidence](docs/SELECTION.md)
- [Baseline audit](docs/AUDIT.md), [implementation plan](docs/REFACTOR_PLAN.md), [PRD](PRD.md)
- [Detailed clipping guide](clipping/README.md) and [approved template](research/studio_template_roadmap.md)
