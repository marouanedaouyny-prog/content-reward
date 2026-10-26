# Evidence-based quality improvement

User objective: improve the entire project, production reliability, trend and
moment selection, learning from measured outcomes, and mistakes in past clips.
The October 22 clarification adds a niche library and one local folder per niche.
An unconditional 10/10 rating and guaranteed virality are not verifiable outcomes.
Completion requires the evidence below, not only passing implementation tests.

## Current findings

- The initial audit found 31 historical normalized clips, zero performance
  observations, zero experiments and zero publications. Saved counts are
  historical records. After recovery and a stricter per-cue caption review,
  22 historical exports remain available with niche copies (11 sports, 11 culture
  and comedy). Nine flagged exports are withheld. Copies are not extra clips.
- The current fresh order `242f2d89` now has an immutable caption revision of
  its AI discussion. The user confirmed "AI is here to stay" and "twenty
  Elvises"; corrected word intervals retain the existing local alignment.
  The revision passed independent timed-cue, displayed-caption, full decode
  and audio checks. Three actual review frames were inspected. Remaining speech
  still requires human review. The original job and artifacts are retained.
- Publisher Intro/Sponsor chapter ranges now exclude overlapping candidates,
  including on resume and recovery. Topic/discovery conflicts are flagged for
  niche review; explicit per-clip decisions can classify a sports-channel AI
  discussion as AI & technology. Per-cue caption recall/order checks now use
  the same conservative thresholds as the whole-window gate.
- Order `79cc9a45` has four caption-boundary failures under the new independent
  checks, and five moments fail current standalone/editorial checks. These sets
  overlap. Historical all-green review records are not a current approval.
- The later order `2e6e3f85` has 11 retained completed jobs and nine source-access
  skips. Earlier chat statements saying zero completed clips are superseded by
  current DB and filesystem evidence.

See [caption audit](../research/caption_quality_audit_2026-10-22.md) and
[selection retrospective](../research/2026-10-22-selection-retrospective.md).

## Acceptance and remaining work

| Area | Required outcome | Current evidence / remaining work |
|---|---|---|
| Reliability | Bounded acquisition, accurate failures, finite retries, durable progress | Safe HTTP/network/TLS/tooling diagnostics and FFmpeg cutoff regressions added; partial preflight preservation and artifact integrity checks implemented. Full combined verification pending. |
| Niche library | Streams, sports, business, education and other supported niches have local folders and a usable section | New routing, CLI/API, workspace filter and availability counts; ambiguous discovery labels go to niche review. New runs organize; historical saved paths/settings remain. Browser and production fixture evidence added. |
| Selection | Eligible standalone moments ranked before greedy suppression; no repeated takeaways or filler | Configured growth ranking and supported feedback now run before pruning. Historical context/setup/unanswered-question cases are regressions. Need a larger held-out, editorially labeled corpus and actual export review. |
| Captions | Independent timed cues catch omissions, insertions, wrong order and boundary fragments | New precision/order/local timing/displayed-SRT checks and optional ASR confidence diagnostics. Configured model honored. Proper-name and audio truth still need review; noisy public cues alone cannot prove them. |
| Learning | Comparable account/window/view definitions, niche/platform cohorts, independent metric samples and bounded updates | Nullable measurement metadata, context-qualified reports, creation-time learning cutoff and paired content-block experiments implemented. Copies/materially overlapping windows count once; no actual observations, real uplift or calibration evidence exist. Import owned post observations before live validation. |
| Past exports | Recover retained artifacts, correct flagged mistakes, recheck actual exports and provide an accurate index | 22 historical MP4/SRT/ASS/post-caption groups remain available after stricter local cue review. Index: `clips/RECOVERED-CLIPS.txt`; structured hashes/provenance: `.json`. Nine flagged clips remain withheld. New local revisions preserve the original job and logical count; names, speech truth and complete editorial review remain open. |
| Performance | Representative measured render/ASR time and memory with a quality budget | Dense selection fixture median wall time fell from 5.583 to 2.347 s with identical outputs. One 40.08-second 1080x1920 retained section rendered in 189.591 s plus 12.285 s external review; encoder peak working set 476.74 MiB. Small.en inference on a retained 56.16-second section took 60.817 s and still needed corrections. Broader workload and total pipeline resource measurements remain open. |
| Interface | Accessible, responsive, honest empty/error/partial states | Niche library desktop/mobile browser and DOM checks added. Wider workspace usability/a11y review remains open. |
| Security and release | Data/credential preservation, disabled publishing, clean package and current checks | Preserve local data and existing worktree. Configured tests, Ruff, smoke and packaging/security audit need final evidence after this work is stable. |

## Library usage

Open the workspace's **Niche library** section, `GET /niche-library`, or run:

```powershell
.\.venv\Scripts\content-reward.exe library
```

New canonical runs/API orders store the niche routing preference. Files remain
under the selected `clips/` delivery root in `sports/`, `streams/`, `business/`,
`education/`, `gaming/`, `ai-technology/`, `fitness/`, `comedy/` or `unclassified/`.
Existing saved orders retain their original flat delivery paths; explicit
`recover ORDER_ID --restore --organize` adds niche copies without changing those
records. Routing combines recorded discovery labels with narrow literal topic
checks and explicit editorial decisions; it is not a verified semantic classifier. Library status
separates missing/empty/changed artifacts from available recorded files; presence
and hashes still do not establish editorial or speech accuracy.

## Verification recorded on October 22–23

- Last completed full configured run: **933 passed, 2 skipped** in 1,191.10s.
  The previously failing launcher-startup timing, niche-count and synthetic-render
  wait assumptions were corrected without removing termination, fresh-discovery,
  duplicate, decode, quality or artifact checks. The combined run includes the
  recovery/context/experiment, chapter, niche and immutable-revision changes.
  An October 23 real recovery exposed a Windows CRLF post-caption mismatch.
  Recovery now reconstructs the saved caption's newline variants and requires
  the recorded hash. All 50 recovery/revision tests pass, including LF/CRLF and
  different-text rejection; the final full-suite run includes this fix.
- Ruff passes. Runtime smoke passes with installed FFmpeg 9.0.1, including the
  shared bounded-section compatibility predicate, isolated DB/worker and API.
- Niche library DOM and real Chrome desktop/mobile checks pass, including
  empty/error/filter/changed/missing file states and literal XSS payload text.
- Real offline tiny.en inference preserved confidence diagnostics for six
  segments and all 99 words of a retained bounded section. This establishes
  diagnostic persistence, not speech correctness or audience performance.
- The link-redirection regression is skipped when this Windows account cannot
  create symbolic links; containment checks exist but need a link-capable
  environment for that integration case.
- Installed-environment dependency validation with `uv pip check` passed for
  50 packages. The production DB's read-only quick check and foreign-key check
  passed, with all historical clips preserved and no observations or publications added.
- The offline wheel contains 107 Python files matching the checkout and no
  legacy/data/media packages. Its isolated worker/database/API smoke check passed
  outside the checkout. One initial API startup timed out under concurrent work;
  the subsequent package and installed-entry-point probes passed.

The overall objective is not achieved. Historical correction, broader
performance/evaluation evidence and the remaining production clips are open. The recovered
index labels old-source provenance explicitly and does not replace the current
order's `LATEST-CLIPS.txt`.

## Research basis

YouTube describes recommendations as personalized and based on multiple signals,
including viewer satisfaction. Its analytics definitions distinguish views,
engaged views, watch duration and retention. Editorial transcript scores are
therefore selection hypotheses; measure outcomes using comparable cohorts and
record metric definitions before claiming improvement.

- [YouTube recommendation explanation](https://support.google.com/youtube/answer/16089387)
- [YouTube analytics report definitions](https://developers.google.com/youtube/analytics/channel_reports)
- [FFmpeg partial-section seeking issue](https://github.com/yt-dlp/yt-dlp/issues/16546)
