# Sentence endings in automatic clip selection

The planner selected the nearest target duration before scoring its window.
That discarded a nearby sentence ending even when it fitted the campaign's
duration limits. A high-scoring question without a sentence ending could also
outrank an available finished sentence.

Each starting subtitle now prefers a sentence-ending cue among its valid end
options, then chooses the nearest target within those options. Finished endings
also take precedence when ranking the resulting windows. Quoted dialogue is
recognized when punctuation precedes closing quotes or brackets, including
common CJK punctuation. Minimum/maximum duration and source boundaries remain
hard limits. If no ending fits, the planner retains a bounded fallback with an
explicit context-review reason.

The public suggestion structure and persisted job identity are unchanged.
Punctuation is an editorial heuristic; it does not prove complete factual
context, an accurate transcript or likely engagement. Actual source review
still determines whether the chosen moment works.

Before the fix, six new regressions failed; the new hard-duration-limit check
already passed. After the fix, the planning/automation suite returned **32
passed** in 8.85 seconds. The full clipping suite returned **161 passed** in
42.82 seconds:

    python tests/clipping/run_tests.py tests/clipping -q --tb=short

The installed Python **3.11.15** runtime independently completed preparation and
rendering on a 35-second source visibly labeled SYNTHETIC TEST FOOTAGE, with
authored sample subtitles. For a target of 30 seconds and limits of 20–35
seconds, the selected cut extended to 34 seconds and retained its final
sentence. The actual MP4 passed 1080x1920, H.264, AAC, duration and file checks.
The plan survived reload, the final SRT cue ran from 30 to 34 seconds, and the
32-second extracted frame visibly showed the ending caption. No publication or
submission record was created.

Repeatable verification is .workflow-tests/sentence-planner-native-smoke.py.
Its record is
.workflow-tests/sentence-planner-native-verification-2026-10-13.json.
This is test-fixture evidence. The requested IShowSpeed job still has no acquired
source or clip, and outbound YouTube access remains refused. The fixture was
not substituted into that job.
