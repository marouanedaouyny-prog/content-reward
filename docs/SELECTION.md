# Candidate selection and duplicate evidence

`clipping.planning.suggest_cuts` preserves timed transcript boundaries and ranks
windows using `config/default.yaml` selection weights. `selection.editorial`
owns every existing hook/topic/gap/duration coefficient. Explicit caller settings
override defaults; saved orders keep their recorded render settings.

Each suggestion records its `strategies`, `transcript_features`, `quality`, and
`selection` report. Candidate start anchors merge question/answer openings,
keywords, sentence boundaries, chapter starts and observed replay peaks. The
general transcript-boundary strategy remains a fallback for sources without
these metadata. Supplied, explicitly observed timed energy or engagement
annotations can add anchors; none are inferred from view counts. Identical cue
anchors merge before window construction. Completed sentence endings remain a
priority. Strict production selection rejects incomplete/contextual/advertising
windows, enforces `selection.minimum_score`, and keeps nonoverlapping moments.

`selection.signals` contains each configured weight, observed normalized value,
normalization basis and weighted contribution. Missing signals have `null`
values. The final score divides available weighted evidence by its available
weight; `evidence_coverage` makes missing evidence visible. Zero available weight
produces zero score. The score is an editorial ranking, not a prediction.

The semantic field is the documented transcript heuristic, not an embedding or
LLM judgment. Hook, standalone and completeness fields use observable transcript
features. Replay intensity is duration-weighted within the selected window;
footage outside that window never contributes. View counts and lifetime
views/hour are descriptive observations. Velocity stays unscored without a
comparable normalization reference. Likes/comments contribute only when both
counts and positive views are known. Emotion, controversy, surprise, novelty and
speaker energy are not invented when captions provide no measurements. Actual
audio/editorial judgment remains necessary.

`clipping.selection.dedup.compare_moments` returns duplicate reasons and measured
similarities. Same-source overlap uses intersection divided by the shorter
window, so a contained interval cannot escape detection. Configured transcript
similarity uses word counts plus shared word sequences. A configured consecutive
quote length catches repeated quotes across sources. Optional embedding cosine
similarity requires nonzero finite vectors of equal size and identical model
identifiers; absent, invalid or incompatible vectors remain unknown. No embedding
service or model is required or downloaded. Unicode apostrophes and case are
normalized. Source selection also retains its content-word diversity check,
using the same configured transcript threshold. Historical exclusions apply to
reserved intervals and excerpts; target counts never justify filling duplicates.

Regression commands:

```powershell
python -m pytest tests/unit/test_selection.py tests/clipping/test_planning.py tests/clipping/test_sections.py -q
python -m pytest tests/clipping/test_production.py tests/clipping/test_batch.py -q
python -m ruff check clipping/selection clipping/planning.py clipping/sections.py clipping/clip_history.py tests/unit/test_selection.py
```
