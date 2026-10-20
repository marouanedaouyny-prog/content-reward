# Project audit — 2026-10-06

## Verdict

The separate `clipping/` application is a usable local clipping workflow, but the repository is not a finished, fully automated Content Rewards system. It can prepare media, import timed subtitles or use the installed English transcription runtime, render clips, save reviews, and record operator confirmations. Account connections, external publication, Content Rewards submission, analytics, and payment reconciliation still require work.

The working entry point is described in [clipping/README.md](../clipping/README.md). Its Python queue replaces n8n for this deployment. The legacy backend, Next.js frontend, project skills, and social connector remain separate implementations with serious unresolved defects. Adding credentials alone will not complete them.

This audit inspected the current snapshot and ran focused checks. There is no `.git` baseline, so findings cannot be attributed to a particular change. Production code was not modified, and no real accounts, posts, submissions, or payments were accessed.

## Required fixes

P1 findings block reliable live use of the affected legacy component. P2 findings affect normal operation or data integrity. The two P2 findings in the current clipping runtime were reproduced using an isolated database and an approval-hash fixture; the publication check did not upload a video.

### [P1] Repair OAuth and transport security before connecting accounts

In [social-connector/app/main.py](../social-connector/app/main.py), lines 289–295 generate state and a verifier without retaining them. Line 292 replaces the computed challenge with an unrelated random string. The callback never validates state, line 344 uses an undefined `redirect_uri`, and lines 347–351 assign connections to a default user. Configuration at lines 275–281 passes only LinkedIn credentials although other providers are initialized.

Provider clients and [empire_integration.py](../social-connector/empire_integration.py), line 52, disable TLS verification. The encryption helper also references `timedelta` in an annotation before importing it: [crypto.py](../social-connector/app/auth/crypto.py), lines 111 and 135, which prevents import under the configured Python 3.11 runtime.

Retain a short-lived, single-use state record bound to the requesting user, provider, redirect URI, and PKCE verifier. Validate and consume it during the callback, pass every provider's configured credentials, repair imports, and enable certificate verification. Real account connection should wait for these fixes and negative callback tests.

### [P1] Make legacy approval decisions resumable and bind the correct publishing worker

[workflow.yaml](../workflows/content_rewards/workflow.yaml), line 29, gates `publish`, but line 68 invokes `social_connector_publish`. [orchestrator.py](../scripts/orchestrator.py), lines 286–294, compares these names literally. The configured publishing worker bypasses that gate.

Lines 302–305 only change an approved job to queued; they do not save approval evidence or the execution checkpoint. Running again starts at the beginning and reaches the same unconditional gate. Lines 243–248 also forward a generated clip ID only to `publish`, leaving the actual configured publisher without it.

Repair the worker contract and persist approved artifacts, captions, target accounts, and step checkpoints. These are defects in the legacy orchestrator; the separate clipping runtime already persists its local review stages.

### [P1] Stop reporting simulated external actions as successful

[YouTube provider](../social-connector/app/providers/youtube/provider.py), line 232, and [Facebook provider](../social-connector/app/providers/facebook/provider.py), line 247, contain simulated publication success. They do not establish a real upload or a real public post.

[Submission skill](../project/skills/submission/skill.py), lines 61–85, inserts a local `SUBMITTED` record while its external submission call is commented out. Draft approval is hardcoded true at line 91, and the external submission method ends in `pass` at line 101.

[Payout tracking](../project/skills/payout_tracking/skill.py), lines 54–58, simulates payout after a time window. Lines 94–104 mark the payout settled and the submission paid without payment confirmation.

Keep practice outcomes explicitly labeled. Require actual provider responses, submission receipts, approval decisions, and payment evidence for live statuses. The new clipping application records these as operator confirmations; it does not independently verify them.

### [P1] Repair the legacy frontend and container wiring

[frontend/next.config.js](../frontend/next.config.js), lines 1–3, contains TypeScript syntax in a JavaScript configuration. The normal ECMAScript parser rejects it, and [Dockerfile.frontend](../Dockerfile.frontend), line 1, configures Node 20. Local Node 24's `--check` accepted the file, so that check alone is insufficient. The rewrite at configuration line 9 also points to `localhost:8000`, which addresses the frontend container rather than the API container in Docker.

[Dockerfile.api](../Dockerfile.api), lines 6–18, neither installs yt-dlp nor copies the sibling connector integration client. The root requirements file only comments that yt-dlp is installed. [Connector client](../social-connector/empire_integration.py), line 49, defaults to the Empire API's `localhost:8000`, and both legacy compose stacks bind host port 8000. The root Ollama service supplies a shell command without overriding its executable entrypoint.

Use valid JavaScript configuration, service DNS names, distinct host ports, complete image dependencies, and an explicit model initialization arrangement. The dedicated clipping compose file is separate and passes configuration validation; its container runtime remains unverified.

### [P1] Repair legacy execution dispatch and queue consumption

[orchestrator.py](../scripts/orchestrator.py), lines 180–186, executes every workflow step regardless of the caller's requested step, and lets YAML defaults overwrite supplied inputs. Its kill-switch guard at lines 159–166 reads the database setting without honoring the configured environment flag. Scheduled callbacks at lines 365–370 insert jobs, but the legacy API starts no queue consumer.

[backend/app/main.py](../backend/app/main.py), lines 152–165, calls blocking workflow execution directly from an async request handler. Downloads, FFmpeg, and retry sleeps can prevent polling and control requests from being served.

Prefer consolidating callers onto one durable execution engine. Otherwise add explicit step dispatch, caller-first input merging, a queue consumer, execution outside the ASGI event loop, and consistent environment controls.

### [P2] Isolate incompatible databases and legacy sessions

[backend/app/core/db.py](../backend/app/core/db.py), lines 197–203 and 331, and [project/db/models.py](../project/db/models.py), lines 190–203 and 493, use incompatible `source_media` schemas with the same default `data/empire.db` database. Their campaign foreign keys also differ. Creating tables does not migrate an existing incompatible schema.

[orchestrator.py](../scripts/orchestrator.py), line 91, retains a live session shared across execution paths. Share an engine/session factory and open a session per request or execution instead. Separate or consolidate the legacy schemas with migrations. The clipping runtime already uses its own `data/clipping.db` and per-operation connections.

### [P2] Add pagination and retrieval controls to the clipping workspace

[clipping/workflow.py](../clipping/workflow.py), lines 172–176, returns the newest 50 jobs by default and caps requests at 100, without an offset or cursor. [workspace.html](../clipping/workspace.html), line 148, always requests the default list and provides no paging or job-ID lookup.

Reproduction: created 51 isolated jobs. The default list contained 50; the oldest job remained in the database but was absent from the list. An older waiting job therefore becomes inaccessible through the workspace even though it remains retrievable by ID through the API. Add cursor pagination and a way to retrieve older active jobs.

### [P2] Require a post identifier in publication URLs

[clipping/workflow.py](../clipping/workflow.py), lines 279–283, checks for path substrings such as `/watch` or `/shorts/` without requiring an actual post identifier.

Reproduction: `https://www.youtube.com/watch` was accepted and advanced an isolated prepared job to `awaiting_submission`, despite containing no video ID. Validate the platform-specific path and query identifier before saving. Continue labeling operator confirmation separately from any future provider verification.

## Features still missing from the clipping workflow

| Area | Present | Still needed for the intended automation |
| --- | --- | --- |
| Whop / Content Rewards access | Manual campaign intake, rights notes, rules, and confirmation references | An authorized integration or supported import for real campaigns and decisions. Verify the access actually available to the user's account; a generic Whop API key does not establish creator submission access. |
| Social accounts and publishing | Manual publication with a recorded URL | Correct OAuth, account selection, refresh/revocation, one real publishing adapter, upload processing checks, and actual post IDs. |
| Clip selection and framing | Operator chooses start/duration; fixed center crop | Highlight suggestions, context review, speaker framing, and editable crop positions if automatic clip selection is required. |
| Captions | SRT import/demo and installed English `tiny.en` runtime | An actual spoken-footage accuracy check. The multilingual `small` model is not downloaded; select English to use the installed English model. |
| Campaign compliance | Required rules/rights notes, duration limits, human reviews | Structured checks for each campaign's applicable requirements, captions/disclosures, allowed material, and draft approval evidence. Media integrity checks do not establish eligibility. |
| Submission and deadlines | Operator receipt recording and a saved deadline | Verified submission evidence and deadline reminders. Confirm any available supported submission interface before automating it. |
| Analytics and rewards | Operator decision/payment history | Real view observations, campaign eligibility decisions, and reconciliation against actual payment evidence. |
| Deployment and operations | Local single-process worker, checkpoints, retries, kill switch | A real browser check, reproducible container run, dependency lock, backups/restore, migrations, and CI. Authentication and deployment controls are needed before expanding beyond the documented local operator use. |

## Verification results

Checks performed for this audit:

| Check | Result |
| --- | --- |
| Focused clipping suite | **27 passed**, 41 warnings, 12.75 seconds. |
| Installed `.venv` dependency compatibility | **37 packages compatible**. This is a dependency consistency check, not a vulnerability audit. |
| Full `tests/` collection | **Blocked by two collection errors**: legacy integration and unit tests cannot import `sqlmodel`. |
| Dedicated clipping compose configuration | **Passed** `docker compose -f docker-compose.clipping.yml config --quiet`. |
| Docker daemon access | Denied on the Docker Desktop named pipe; build and container execution were not verified. |
| Legacy frontend configuration | Normal ES-module parsing fails at `import type`; no complete frontend build was run. |
| New clipping pagination and URL checks | Both defects above reproduced against isolated data. |
| Existing localhost service | Port 8000 was not responding during the audit. This indicates the service was not available then, not a reproduced application failure. |

Commands used for the main checks:

```powershell
python -m pytest tests/clipping -q -p no:cacheprovider --disable-warnings -o asyncio_default_fixture_loop_scope=function
uv pip check --python .venv/Scripts/python.exe --cache-dir .uv-cache
python -m pytest tests --collect-only -q -p no:cacheprovider --disable-warnings -o asyncio_default_fixture_loop_scope=function
docker compose -f docker-compose.clipping.yml config --quiet
```

Earlier native model checks established CPU loading, decoder inference, and speech activity detection on silent input. They did not establish spoken-word accuracy. Browser launch was denied in earlier validation, so visual/mobile interaction remains unverified. No live publishing or reward reconciliation was tested. This is a prioritized audit, not a claim that every earlier review comment was re-tested or that all remaining defects have been found.

## Completion order

1. Keep `clipping/` as the supported entry point and repair its pagination and publication URL validation. Keep legacy success claims out of the active workflow.
2. Run an authorized real source through English transcription or a reviewed SRT, rendering, and both approval stages. Inspect spoken captions, framing, and the actual browser experience.
3. Repair account connection security and implement one real social provider compatible with the user's account and the provider's current requirements. Verify failures and a real post before adding other providers.
4. Add supported campaign imports, submission evidence, deadline reminders, analytics, and payment reconciliation. Preserve manual handoffs where an authorized external interface has not been established.
5. Resolve or retire duplicated legacy paths, isolate/migrate databases, make the relevant full test suite runnable, and verify a container deployment plus backup/restore before expanding use.

To use the installed English transcription environment locally:

```powershell
.\.venv\Scripts\python.exe -m clipping
```

Open `http://127.0.0.1:8000/` and select English. Publication, Content Rewards submission, and reward confirmation remain operator actions in this version.
