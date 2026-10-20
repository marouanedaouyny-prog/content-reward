# Clip research and YouTube planning implementation

The user wants daily Content Rewards clips across niches, with a section to choose YouTube footage and suggest promising moments. Implement this in the supported local `clipping/` runtime. The target Hugging Face repository currently returns 401; its documented fields are historical metadata, without footage, transcripts, retention, follower counts or reward terms.

## Contract and scope

- A local CSV/JSONL sample importer accepts at most 25 MB / 100,000 records. Preserve video IDs as strings, reject malformed rows, deduplicate IDs, and report missing/invalid records. Return aggregate topic/month/language/country/duration cohorts with support counts and share/save rates. Suppress recommendations from undersized groups. Label fixture data synthetic and uploads operator supplied.
- A YouTube source checker accepts a single canonical HTTPS video URL and returns selected public metadata through yt-dlp. Do not search arbitrarily, accept cookies, or download media during this check.
- A transcript planner scores whole subtitle windows using explainable editorial heuristics. Scores are not trained models or probabilities of virality. Return up to three diverse editable cuts, captions derived from the operator's source, and reasons.
- Automatic planning runs after saved campaign/rights approval and transcription. Its selected cut and alternatives are checkpointed. Existing clip review, publication, submission and reward handoffs remain in force.
- Add controls to the existing workspace for a YouTube source check, local research sample, synthetic demo, automatic planning and applying a suggested cut. Render imported text using textContent.
- No bulk dataset downloads, external publication, payment forecasts, or automatic campaign eligibility claims. Real footage still needs authorization and usable subtitles/transcription. Commercial permission for the specific dataset remains unverified.

## Ordered increments and checks

1. Write failing tests for metadata validation/deduplication, zero-view handling, supported cohorts, topic matching and synthetic provenance. Implement `clipping/research.py` and run its tests.
2. Write failing tests for transcript boundary selection, sparse/invalid inputs, YouTube URL validation, and gate-preserving workflow integration. Implement `clipping/planning.py` and narrowly extend `media.py` / `workflow.py`.
3. Write API tests for source checks, research upload/demo, planner and foreign-origin rejection. Add the API models/routes and `clipping/research.js` controls to the workspace.
4. Run the complete focused clipping suite, JavaScript syntax checks, and an isolated HTTP practice run producing an MP4 and saved suggestions. Try a real browser only if the environment permits it. Document verified behavior and remaining data/footage access limits.

No Git repository is present, so changes are left in the workspace without commits. See [dataset research](tiktok_videos_4b_research_2026-10-08.md) for primary sources and [yt-dlp options](https://github.com/yt-dlp/yt-dlp#usage-and-options) for public source metadata extraction.
