# Design upgrade evidence

Recorded: 2026-10-10. The user requested `$impeccable i want upgrade that design`
and delegated routine choices. This upgrade preserves the existing green Operate
identity; it does not establish a new visual world or generated imagery.

## Source and documentation scope

Compared final [workspace HTML](../../clipping/workspace.html) and
[research controls](../../clipping/research.js) with [PRODUCT.md](../../PRODUCT.md),
[DESIGN.md](../../DESIGN.md), the [sidecar](../design.json), and the
[surface brief](../surfaces/clipping-workspace.md). The
[before snapshot](../../.workflow-tests/design-upgrade-before.html) and
[refreshed diff](../../.workflow-tests/design-upgrade.diff) record the change.

Updated DESIGN.md layout/component prose, three affected component contracts,
six existing sidecar component examples, the recorded 600px breakpoint and the
surface composition brief. Palette, typography, spacing and radius primitives,
the named world/rules and sidecar schemaVersion 2 remain unchanged. No code or
product-document edits belong to this documentation pass.

## Final source behavior

- A sidebar of up to 320px groups the automatic action with recent runs; a larger
  preview panel contains numbered progress and the actual video or empty state.
  Native anchors navigate the workspace. Optional campaign setup occupies a
  separate panel with two fieldsets; its disclosure remains collapsed initially.
- At 800px the automatic action, preview and history stack. At 600px the map
  stacks and progress scrolls horizontally. At 480px paired fields and campaign
  buttons stack. The SVG only connects map inputs geometrically and is hidden
  from assistive technology; explanatory text retains the complete meaning.
- Empty previews distinguish failed, cancelled, paused, subtitle-needed and
  automatic-retry states. A short run explanation leads to a native disclosure
  containing the actual error. Saved output fields continue to determine preview
  readiness; a ready label is not publication, payment or a media-quality check.
- Recent selectors expose `aria-pressed`; unchanged poll results preserve their
  existing controls. Navigation and alternative-cut actions open setup. Creating
  a campaign task returns to the preview. New and research scroll handoffs use
  immediate scrolling when reduced motion is requested.
- Field padding is now 12px, progress-step padding is 8px 0 0, and the campaign
  summary uses ink, existing 18px type and 8px 0 padding. Those intentional
  component changes are reflected without changing the shared primitive scales.

## Verification and limits

The coordinator reports the focused clipping suite passed 71 tests before the
final empty-state and reduced-motion corrections. All three UI interaction tests
were rechecked on the final files, including reduced-motion expectations. Both
JavaScript syntax checks, balanced/unique HTML structure and final native HTTP
checks passed. The integrity check confirms all 26 relocated form-field
contracts/defaults are equivalent at attribute level. This documentation pass
verifies schema, token preservation, snippet syntax, links and source-file
preservation; it does not rerun implementation tests or the detector.

The [calculated contrast record](upgrade-contrast.json) reports body 14.68:1,
muted text 5.75:1, primary controls 6.77:1, empty-preview text 16.03:1,
failed-status text 6.58:1 and tinted-panel copy 5.11:1. These calculations do not
replace rendered inspection.

Pre-existing token advisories remain uncorrected: `#cfe7db`, `#a5bab1`, `#fff5df`,
`#d5b47a`, `#101818`, and responsive sizes 32px/22px are outside the recorded
primitive ramp. The upgraded empty preview reuses the existing media literal
`#101818`; its code sample records that local use without promoting it into a
new palette token. No unrelated advisory was repaired or canonized.

Disposition remains **recapture**. Captures at 1440px, 390px and 320px are absent;
the fresh browser attempt was blocked by Windows Crashpad/Mojo IPC error 5.
No new detector or browser attempt was made for this documentation pass. The
upgrade has no visual finish approval and establishes no live dataset import,
source acquisition, publication, reward payment or promised performance outcome.
