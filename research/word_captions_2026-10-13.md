# Short captions with preserved word timing

Automatic transcription previously discarded the model's word timings.
Rendering used the entire segment text for its full duration, which could fill
too much of a vertical video or include words outside the actual cut.

The installed faster-whisper 1.0.3 API supports word timestamps through
the transcription option and segment word records. The implementation uses
that version's documented start, end and word values.
Source: [official versioned documentation](https://github.com/SYSTRAN/faster-whisper/tree/v1.0.3#word-level-timestamps).

The worker now retains optional word metadata alongside the existing segment
text and timing. Validation rejects malformed, non-finite, unordered or
out-of-source word times, empty word text, and words that do not reproduce the
segment text. Word boundaries may differ slightly from parent segment
boundaries; source bounds still apply. Rendering validates saved transcripts
again before writing captions.

Aligned words overlapping the selected clip are grouped into short phrases
with at most six word entries, a 32-character budget, and up to two intended
16-character lines. Groups split before long pauses or when adding a word
would exceed three seconds. A single long word or long individual alignment
can exceed those budgets because the renderer preserves its supplied timing
and text. Raw word spacing is retained for languages that do not use spaces.
The available interval of a boundary word is clamped to the clip and rebased.

Imported SRT, older transcripts without word metadata, and segments containing
any zero-duration word alignment keep their original segment cues. No word
times are fabricated for those cases. This fallback can retain a longer cue.

## Verification

Transcription tests first returned 11 failures and one pass for the new word
requirements; after implementation, all 25 transcription tests passed. Caption
tests first returned six failures and two passes on the original rendering.
Two additional checks cover boundary words and alignment outside the parent
segment. The final clipping suite returned **183 passed in 41.36 seconds**:

    python tests/clipping/run_tests.py tests/clipping -q --tb=short

A real local-model diagnostic produced nine segments and 54 aligned words,
including two zero-duration alignments. The new metadata validation accepted
them. This diagnostic disabled VAD only for inspection; product transcription
still uses VAD. Neither recognition accuracy nor campaign suitability was
established by the diagnostic.

Native Python 3.11 ran the complete private preparation workflow against
labeled synthetic footage, tone audio and authored word timings. The rendered
12-second H.264/AAC MP4 passed the dimensions, duration, codec and file checks
at 1080x1920. Five caption phrases preserved the complete authored text and
original first/last word times; word metadata survived database reload.
No publication or reward submission occurred.

The first extracted frame revealed an extra automatic line wrap despite two
SRT lines. Reducing the phrase and line budgets fixed the inspected layout.
The final first-caption and longest-caption frames showed readable two-line
captions without clipping. This was native video verification; browser
verification remains unavailable in this environment.

Evidence lives in:

- `.workflow-tests/word-captions-native-verification-2026-10-13.json`
- `.workflow-tests/word-captions-verification-2026-10-13.json`
- `.workflow-tests/caption-runtime-verification-2026-10-13.json`
- `.workflow-tests/word-captions-native-smoke.py`

## Remaining work

Actual IShowSpeed acquisition still lacks a source checkpoint. The last
connection investigation found the configured proxy refusing connections;
caption improvements do not resolve that access failure. Recognition,
speaker context, cropping and subtitle accuracy need review on the actual
footage once it becomes available.
