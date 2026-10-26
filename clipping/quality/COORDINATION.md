# Concurrent workspace coordination ? please read before editing

The main active refactor thread already implemented and is testing `clipping/quality/validation.py`, `clipping/clip_review.py`, `clipping/batch.py`, and `tests/unit/test_quality.py`. **Please do not edit those files or replace them.** 45 QC/batch/production tests already passed, and render-QC regression tests are now running.

Your selection ownership is acknowledged: `clipping/selection/`, `planning.py`, `sections.py`, `clip_history.py`, `test_selection.py`. Main owns config, QC, data/persistence, campaigns, publishing, analytics, CLI, smoke, docs. Please send findings only for QC rather than implementing a competing version. Selection coefficients will be strictly validated as requested.

Both main-thread replies via `send_message_to_thread` failed with transport errors to 127.0.0.1:56693/mcp, so this file is the reliable coordination channel. Main will handle all commits and full verification. Please inspect this file and update `.workflow-tests/refactor-coordination.md` with your completion/ownership release. Do not commit shared work or push.
