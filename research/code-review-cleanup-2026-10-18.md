# Clipping code review and cleanup

Reviewed the current clipping controller, batch/download flow, caption renderer
and shared defaults against `AGENTS.md`, `tasks/plan.md` and the studio roadmap.
The requested Standards and Spec reviews ran independently in parallel.

This directory has no Git repository or resolvable comparison commit, and no
issue-tracker configuration. A comparison point was requested. Cleanup used a
filesystem snapshot of the current files instead of claiming a historical Git
diff review. The [before/after patch](code-cleanup-2026-10-18.patch) records the
actual changes; the snapshot is under
`.workflow-tests/code-cleanup-1edb06ecd97e4863b90a0fd23671ba73/`.

## Standards

No hard documented-standard violations were found. Three heuristic findings
were resolved:

1. **Duplicated style definitions.** Shared choices in `clipping/template.py`
   now serve controller validation, CLI arguments, workflow intake and ASS
   validation. CLI ordering is preserved; classic still uses the SRT renderer.
2. **Duplicated tokenization.** `sections._content_words` centralizes the
   repeated expression while preserving ordered title keywords and set-based
   transcript signatures.
3. **Ambiguous coordinates.** Caption variables distinguish word/event times
   from character spans, avoiding names that obscure or shadow the source start.

The final independent Standards review found all three resolved and no new
blocking concern. The existing export-verification wrapper remains a useful
test seam. No speculative framework, dependency or broad module rewrite was
introduced.

## Spec

Two resume defects were verified and fixed:

1. **P2: stale legacy result manifest after failed verification.** Requirement:
   "Export verification checks the actual file" (`tasks/plan.md`, criterion 3).
   `Controller.finish` previously cleared the in-memory result while leaving
   `order/result.json` advertising an export that failed rechecking. It now
   removes that manifest before verification and recreates it only after success.
   The legacy failed-recheck test now also asserts removal of the result file.
2. **P2: invalid cached section prevents recovery.** Requirement: "A saved order
   resumes after a connection failure or interruption" (`tasks/plan.md`,
   criterion 2). Unreadable or truncated cached sections were repeatedly reused
   and rejected. They are now validated before reuse; an invalid checkpoint is
   removed and only its original bounded range is requested again. Valid cached
   sections remain reusable; newly invalid or full-length responses are rejected.
   Real FFmpeg/ffprobe regression cases verify unreadable and short media,
   bounded reacquisition and subsequent cache reuse.

The final independent Spec review confirmed both fixes and no new risk within
the changed code. Studio/fit defaults, saved per-clip styles, idempotent payload
normalization, bounded download arguments and preview-only publishing are kept.

## Verification

- Baseline targeted checks: 35 passed before production edits.
- Regression demonstration: 3 failures before fixes, each at the intended bug.
- Resume/section/batch checks after fixes: 35 passed.
- Expanded targeted checks after cleanup: 45 passed.
- Before/after comparison: 36 ASS outputs identical across three styles and
  multiple windows/transcript fixtures; two complete moment plans identical.
- Ruff `E4,E7,E9,F` checks passed for all changed Python files and tests.
- Broader non-Instagram clipping regression: **230 passed, 1 deselected** in
  76.16 seconds. Command:

  ```powershell
  python tests/clipping/run_tests.py tests/clipping --ignore=tests/clipping/test_instagram.py --ignore=tests/clipping/test_instagram_oauth.py --ignore=tests/clipping/test_instagram_tunnel.py --ignore=tests/clipping/test_instagram_token.py -k 'not instagram' -q --tb=short
  ```

Live source connectivity and subjective export quality are separate
from this local code review; no live order or social credentials were changed.

Standards: 3 heuristic findings fixed (strongest: duplicated style choices),
0 hard violations. Spec: 2 P2 resume findings fixed, 0 unresolved in scope.
