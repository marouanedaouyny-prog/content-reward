# Caption quality audit, 2026-10-22

Scope: inspect authoritative SQLite order `79cc9a45-cf13-4248-9789-28e9b90ff6c7`,
its 20 saved job transcripts/SRT files, public source cues, stored review records,
and the caption generation/review code. No source download, account access,
publication or media modification was performed for this audit.

## Current artifact evidence

The authoritative order is `ready_for_review` / `finished`, with 20 stored batch
results. At audit time **all 20 delivery MP4 paths and all 20 delivery SRT paths
were absent**. The per-job SRT and transcript files under `storage/clipping/jobs/`
remain, as do bounded source sections and review frames. A completed database
record does not prove that its delivery files are currently available. This audit
therefore does not certify the old final MP4 files or their current accessibility.

The stored export reviews passed all checks and recorded mechanical scores of
100, while also setting `human_review_required=true` and
`speech_accuracy=not_verified`. Those qualifications matter: the saved SRTs
contain material recognition errors.

## Examples from saved subtitles

| Clip | Job ID | Actual saved SRT evidence | Independent comparison / limit |
|---|---|---|---|
| 1 | `022aea99-8dee-419c-b6e6-1655aa1236f6` | `Eric Tenhart`, `all Trafford`, `FC -20`, final `This` | The title spells `Erik ten Hag`; public cues say `Old Trafford` but also contain their own name errors. The final `This` is an ASR word timed 36.80–37.16 against a selected end of 36.88. |
| 11 | `de9a5ac5-a918-4834-8fc4-98744badb908` | Final `I'm` after the complete news-conference point | Word 39.50–39.84, local selected end 39.559. It belongs to the following context, rather than the supplied source cue. |
| 13 | `eb07f83c-4215-44d9-83a7-38647e86d8d2` | `Tim Hagg, sanctioned the savings of the last year, Martinez` and `my interesting neighbours` | Public cues instead say `Tinhag sanctioned the signings of Malasia Martinez` and `Manchester United`; the public names are noisy too. Old token recall was 0.760563, which did not establish speech accuracy. |
| 17 | `14723bff-ea0f-4c1d-99b6-1f7a3d5ee944` | Leading `right`; final `Part` | The leading word is 2.68–3.02 against local start 3.00. It leaves only 20 ms in the selected interval. The trailing fragment still needs human/audio review; coarse public cues cannot prove its exact boundary. |
| 18 | `f50e7fa4-3b63-453c-b957-f49f1d047bc1` | Leading `me.`, `Muzzy`, `middles`, `raspid`, final `What` | Source cues say `was he`, `Middlesbrough`, `Rashford`, and omit the leading/trailing context. `me` is 2.70–3.04 against start 3.00; `What` is 23.88–24.32 against end 24.119. |
| 19 | `26cf1ce2-1cad-40b9-a5b9-f57b655354a6` | `Zoron Londani`, `favorite ability` | Public captions say `Zoron Mandani` and `favorability`; the title supplies only `Zohran`. Neither ASR output establishes the correct full name. |
| 20 | `c3a0a39d-3f14-4187-a243-e4ca045efbbb` | Repeated `Mom Donnie`, including inside an attributed quotation | Public captions use several inconsistent variants (`Manny`, `Mdani`). These require evidence-based correction or rejection, rather than replacing one recognizer's guess with another. |

Review frame `review-18/review-3.jpg` shows the approved full-image/blurred-background
layout with lime emphasis, and visibly displays `SAME LIKE DOING THIS CHARLIE,`.
A screenshot demonstrates appearance; it does not establish that the caption
matches the source audio.

## Reproduced weaknesses and fixes

`caption_review.assess_captions` originally checked bag-of-words recall below
0.45, source speech overlap below 0.35, and one repeated four-word-loop pattern.
Executable regressions demonstrated that it accepted:

- Only six of eleven source words stretched over the whole source cue.
- All source words plus thirteen unrelated inserted words.
- All source words in reverse order.
- Two correct source sentences exchanged between their timed cues.
- An entirely omitted middle source cue while the other cues matched.
- Words substantially truncated by a clip boundary.

The gate now reports source token precision, ordered token recall and per-cue
local agreement. Conservative source-cue checks tolerate 0.75 seconds of boundary
jitter and avoid making a local judgment from fewer than six reference words.
Substantial crossing words at clip edges produce explicit review failures. The
gate still labels speech accuracy unverified and names the limits of noisy
public captions; its thresholds are editorial safeguards rather than a trained
speech-accuracy metric.

A second reproduced bypass involved zero-duration ASR words: the old speech
assessment correctly excluded them from timed speech evidence, but the display
grouper retained their text by merging it with a neighboring timed word. A saved
SRT could therefore include unsupported text that was never assessed. Export
review now assesses the actual displayed SRT against independently supplied cues
in addition to assessing the original ASR. Silence-removal mappings are applied
to both displayed and independent source cues.

Disfluency-only segments also previously produced empty caption blocks; they
are now omitted from display. This does not alter source speech or the approved
caption style.

Reassessing the 20 saved ASR transcripts with the new boundary gate rejects
clips **1, 11, 17 and 18**. The other 16 pass these structural agreement gates;
that result does not certify their proper names or meanings. The saved delivery
files were not rebuilt and historical review records were not rewritten.

## Production follow-up and remaining limits

- Production should recover or reject a candidate after a new caption failure;
  merely pausing forever at `TranscriptRequired` does not improve clip delivery.
- Generic small batches must attach independent source cues just as production
  entries do; absent cues should remain explicit in review evidence.
- Fixed after this audit: `media.whisper_model_location` now honors the effective
  `settings.whisper.model` before unrelated cached models, including YAML overlays,
  explicit local paths and the higher-precedence `WHISPER_MODEL` environment value.
  An English-only selection still uses a compatible multilingual fallback for
  non-English/automatic language mode. The default remains the installed `tiny.en`.
- All audited job payloads had no transcription hint. A short, bounded entity
  context from trustworthy metadata may help recognition; a full copied speech
  prompt previously caused omissions and must not be reintroduced.
- Fixed after this audit: the transcription worker preserves finite/range-checked
  segment `avg_logprob`, `no_speech_prob`, `compression_ratio` and word `probability`.
  Saved transcript JSON includes an `asr_confidence` availability/provenance summary
  and explicit limitations. Confidence can support targeted review, but cannot
  prove a name or quotation is correct. Invalid optional worker diagnostics are
  omitted; invalid diagnostics in a received transcript cannot be checkpointed.
- Subtitle scores based only on format, size and timing must remain clearly
  identified as mechanical evidence, with human speech review still required.

## Verification

The new bypass regressions were observed failing before their fixes. Focused
coverage, caption display, export review, transcription and silence tests passed:
**81 passed**. Ruff checks for the changed caption modules and tests passed.
The parent task remains responsible for full configured-suite and smoke checks.

The follow-up model/confidence regression run passed **110 tests** across
transcription, captions, export review, config and checkpoint modules. Ruff and
diff checks passed. A real inference on one existing bounded section, using the
already-installed `tiny.en` with model-hub offline settings enabled, preserved
all three segment diagnostics for six segments and word probabilities for all
99 words. This verifies metadata persistence with the installed recognizer; it
does not verify the speech transcription. Its local evidence is
`.workflow-tests/asr-confidence-probe.json`.
