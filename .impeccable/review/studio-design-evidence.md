# Studio design evidence

Recorded on 2026-10-10 from the final source and the completed verification
handoff. This is source and interaction evidence; no screenshot or real-browser
visual approval is claimed.

## Scope and authority

The user requested `$impeccable` to add a section, colors and 3D design and to
upgrade the form, and delegated routine decisions. The approved result extends
the incumbent green Operate workspace. It adds Clip Studio and a guided optional
Campaign → Source → Clip form. Durable additions are merged into DESIGN.md and
the schemaVersion 2 sidecar, preserving the previous palette, type, radius and
spacing primitives. PRODUCT.md remains unchanged.

Source checked: `clipping/workspace.html`, `clipping/studio.js`,
`clipping/research.js`, and the static page/Studio route in `clipping/app.py`.
Documentation written: `DESIGN.md`, `.impeccable/design.json`,
`.impeccable/surfaces/clipping-workspace.md`, and this file. This handoff did not
edit application code or rerun the browser or detector.

## Implemented design

- Eight new semantic tokens describe clay Studio, blue Source and pale gold
  caption/Campaign contexts. Their normative values live in DESIGN.md
  frontmatter and match the CSS custom properties.
- The CSS3D model uses a video plane, forward caption plane and separate rotated
  edge face. It is explicitly labeled as a layout model and directs operators
  to Preview for actual output. Neutral offset shadows are confined to the
  model's two planes; panels remain flat.
- Vertical, square and landscape choices update the local model. Angle control
  and Front view are explicit interactions. Use format in campaign applies the
  format to the existing form while preserving source, caption and permissions.
  No new dependency, network request or animation loop is introduced.
- Reduced-motion preference shows the model flat, removes transitions and
  transforms, disables angle control and exposes explanatory text.
- Guided Next/Back navigation preserves the original 26 input contracts and
  defaults. Native validity, source count and campaign duration checks run across
  all steps before posting; a failing step opens and its control receives focus.
  Research and alternative-cut handoffs reveal Clip and preserve source and
  disclosure data. The automatic preview still posts `{}` independently of this
  optional form.

## Verification received

| Check | Final result |
| --- | --- |
| Focused clipping test suite | 72 tests passed in 52.72 seconds |
| Node UI interaction checks | Four final checks passed in 1.25 seconds |
| HTML structure | Balanced structure and unique IDs |
| Legacy field preservation | All 26 input attributes and defaults preserved |
| JavaScript syntax | `studio.js`, `research.js` and extracted workspace inline script passed `node --check` |
| Native HTTP | `/`, `/studio.js` and `/research.js` returned 200 |
| Documentation integrity | Frontmatter and JSON parse; previous primitives and sidecar entries preserved; all eight new colors match source; ten unique component previews |

Application results were supplied by the implementation handoff. The final UI
command was `python -m pytest tests/clipping/test_research_ui.py -q -p
no:cacheprovider --disable-warnings -o asyncio_default_fixture_loop_scope=function
--tb=short`. It executes `research_ui_check.cjs`, `automation_ui_check.cjs`,
`research_brief_ui_check.cjs` and `studio_ui_check.cjs` in `tests/clipping/`.
The extracted inline syntax target is
`.workflow-tests/studio-workspace-inline.js`. The documenter checked the
corresponding shipped patterns and documentation integrity without broadening
application verification. Final source corrections refresh the model after
sample subtitle loading and suggested-caption application; subtitle guidance
points to the Source step.

Calculated contrast is recorded in `studio-contrast.json`:

| Foreground/background role | Ratio |
| --- | --- |
| Studio copy on Studio tint | 7.99:1 |
| Model label on video face | 5.51:1 |
| Source settings | 7.02:1 |
| Caption settings | 6.18:1 |
| Selected format | 9.39:1 |

These are calculated color pairs, not measurements from browser screenshots.

## Detector disposition

`studio-detector-notes.md` records one scan before palette documentation. The
new palette advisories describe the intentional approved additions now recorded
in the design system. Two source warnings were corrected before the final
handoff: colored shadows became neutral, and the stripe became a separate
rotated edge face representing thickness. No second detector pass is claimed.
Unrelated pre-existing palette/type advisories remain outside scope and were
neither repaired nor promoted into new rules.

## Visual limit and preservation evidence

Required 1440px desktop, 390px mobile and 320px narrow captures are absent.
`capture-status.json` records that Chrome exited before DevToolsActivePort;
Windows denied Crashpad CreateFile and Mojo IPC with error 5. No browser security
settings were disabled. Finish disposition remains recapture without visual
approval. No additional capture attempt was made in this documentation pass.

Before records exist at `.workflow-tests/studio-before-DESIGN.md`,
`.workflow-tests/studio-before-design.json` and
`.workflow-tests/studio-before-workspace.html`. The implementation comparison is
`.workflow-tests/studio-design.diff`. Existing system decisions are retained;
old shadow-free wording is narrowed only for the authorized Studio model.
