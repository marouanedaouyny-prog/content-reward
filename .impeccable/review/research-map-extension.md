# Research map extension evidence

Recorded: 2026-10-09. Scope: an ordinary extension of the existing green Operate
workspace. This note records source evidence; it does not establish visual
verification or authorize a design-system change.

## Sources and boundary

Compared the finished [workspace](../../clipping/workspace.html) and
[research controls](../../clipping/research.js) with [PRODUCT.md](../../PRODUCT.md),
[DESIGN.md](../../DESIGN.md), the [design sidecar](../design.json), the
[surface brief](../surfaces/clipping-workspace.md), and the existing
[research guide](../../clipping/RESEARCH_GUIDE.md). Applied the shipped
Impeccable documenter role and `reference/document.md` scan instructions.

Only this evidence note is written. The incumbent design system, product brief,
surface brief, implementation and research guide are preserved.

## Implemented extension

- `#workflow-map` uses a named section, headings and ordered lists to explain
  the two inputs: optional TikTok metadata and actual source video/subtitles.
  Text separates planning, local rendering and later campaign handoffs.
- `renderWorkflowMap(job)` reads the selected job's saved `source_path`,
  `transcript_path`, `selected_clip_plan` and `clip_path`. It distinguishes
  pending, running, failed and available checkpoints. A completed job label
  alone does not manufacture a ready preview. The map reflects saved output
  fields; it is not an independent media-quality check.
- Live status text names the selected run and identifies synthetic practice.
  `#open-research` is a native secondary button. `openResearch()` expands both
  optional disclosures and focuses the local sample input. The automatic
  preview continues to use its saved defaults.
- `renderReport(report)` presents one planning brief with topic, desired length,
  supporting-post count, context, reason and limitations. Imported text uses
  `textContent`. Synthetic demonstrations are explicitly labeled and receive
  no brief-apply action.
- `applyBrief(brief)` fills topic keywords and desired length and enables
  transcript planning. Campaign bounds constrain the length within the existing
  1–180-second intake range. Negative minimums, invalid bounds and explicit
  language mismatches stop the action before changing settings. The source,
  format, language, caption/disclosure and permissions remain the supplied
  values; applying a brief neither creates nor approves a job.

These behaviors support PRODUCT.md's delegated choices, honest progress and
separation of private previews from publication and reward. Historical metadata
is labeled as research evidence, not a prediction or proof of earnings.

## Incumbent system comparison

The extension reuses existing section surfaces, heading/body styles, compact
state text, borders and secondary controls. New map/brief rules introduce no
new literal color or font-size values. The map uses the existing spacing rhythm
and a local two-column composition that stacks at 600px; this is a surface
layout rule, not a replacement of the shared 800px/480px responsive system.

DESIGN.md and `.impeccable/design.json` remain unchanged. Forest green actions,
pale canvas, Georgia page title, system operational typography, flat panels and
visible focus retain their existing authority. No new brand, assets or visual
world has been committed.

## Verification and finish disposition

Implementation verification supplied by the coordinator: the full focused
clipping suite passed 71 tests; native HTTP checks returned 200 for the workspace,
research script and demo report; shipped Node checks covered campaign bounds,
demo exclusion, source/disclosure preservation and failed/complete checkpoints.
Both scripts passed syntax checks and HTML IDs were unique. After the final
negative-minimum guard, all three UI interaction tests and `research.js` syntax
passed on the final files.

This documentation pass checks source consistency, note links and preservation
of existing files. It does not rerun the suite, detector or browser capture.

Pre-existing detector advisories are preserved without repair or canonization:
`#cfe7db`, `#a5bab1`, `#fff5df`, `#d5b47a`, `#101818`, and responsive sizes `32px`
and `22px` are missing from the machine-readable token ramp. The responsive sizes
already appear in DESIGN.md prose. These advisories do not establish a new
system change and are outside this extension's documentation boundary.

Finish disposition remains **recapture**. Desktop (1440px), mobile (390px) and
narrow (320px) captures are missing because Windows Chrome IPC denies launch.
Source and interaction checks supplement visual inspection; they do not provide
visual approval. This extension establishes no live dataset import, real source
download, publication, paid reward or promised performance outcome.
