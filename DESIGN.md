---
name: Clipping workspace
description: A restrained green workspace for preparing and reviewing subtitled video.
colors:
  accent: "#176753"
  accent-hover: "#124f41"
  accent-active: "#0d4134"
  ink: "#172526"
  muted: "#59696a"
  line: "#d9e0df"
  field-border: "#b8c6c3"
  surface: "#ffffff"
  canvas: "#f5f7f5"
  tint: "#eaf4ef"
  secondary-active: "#dcece4"
  selected-surface: "#f0f7f3"
  progress-complete: "#8bb39f"
  focus: "#a56f16"
  error: "#9a3725"
  studio-tint: "#fce9df"
  studio-ink: "#74331f"
  studio-face: "#f6ba8c"
  studio-side: "#c47547"
  source-tint: "#e7efff"
  source-ink: "#254ba0"
  caption-tint: "#fff2ce"
  caption-ink: "#765417"
typography:
  display:
    fontFamily: "Georgia, serif"
    fontSize: "36px"
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  title:
    fontFamily: "system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.6
  body:
    fontFamily: "system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.6
  button:
    fontFamily: "system-ui"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: "normal"
  small:
    fontFamily: "system-ui, sans-serif"
    fontSize: "12px"
    lineHeight: 1.6
rounded:
  control: "3px"
  inset: "8px"
  panel: "12px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-primary-active:
    backgroundColor: "{colors.accent-active}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.accent}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.tint}"
  button-secondary-active:
    backgroundColor: "{colors.secondary-active}"
    textColor: "{colors.accent}"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "12px"
    width: "100%"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "24px"
  status-chip:
    backgroundColor: "{colors.tint}"
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
    padding: "4px 9px"
  selected-run:
    backgroundColor: "{colors.selected-surface}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  progress-current:
    textColor: "{colors.accent}"
    padding: "8px 0 0"
  campaign-disclosure:
    textColor: "{colors.ink}"
    padding: "8px 0"
  studio-panel:
    backgroundColor: "{colors.studio-tint}"
    textColor: "{colors.studio-ink}"
    rounded: "{rounded.panel}"
    padding: "24px"
  studio-video-plane:
    backgroundColor: "{colors.studio-face}"
    textColor: "{colors.studio-ink}"
    rounded: "{rounded.panel}"
    padding: "20px"
  studio-caption-plane:
    backgroundColor: "{colors.caption-tint}"
    textColor: "{colors.caption-ink}"
    rounded: "{rounded.inset}"
    padding: "12px"
  studio-format-selected:
    backgroundColor: "{colors.studio-ink}"
    textColor: "{colors.surface}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  source-settings:
    backgroundColor: "{colors.source-tint}"
    textColor: "{colors.source-ink}"
    rounded: "{rounded.control}"
    padding: "12px 16px"
  campaign-settings:
    backgroundColor: "{colors.caption-tint}"
    textColor: "{colors.caption-ink}"
    rounded: "{rounded.control}"
    padding: "12px 16px"
  clip-settings:
    backgroundColor: "{colors.studio-tint}"
    textColor: "{colors.studio-ink}"
    rounded: "{rounded.control}"
    padding: "12px 16px"
---

# Design System: Clipping workspace

## Overview

**Creative North Star: "The Quiet Workbench"**

A pale canvas, white work surfaces and restrained forest green make the interface feel calm and practical. The serif page title provides a small editorial signature; familiar system type carries the operational detail. Borders and changes in surface tone establish hierarchy without decorative imagery.

The system supports sustained reading and clear states. Short labels, roomy controls and readable paragraphs keep dense workflow information approachable. Green identifies actions and selected progress; explicit text carries the meaning of each processing state.

The approved extension adds warm clay to Clip Studio, blue to source settings and pale gold to caption and campaign requirements. These colors identify editing context while green continues to carry workflow actions. A controlled CSS3D layout model shows video and caption planes; the surrounding work surfaces retain their flat treatment.

This record was extracted from `clipping/workspace.html`. Real-browser capture is unavailable because Chrome IPC is rejected in this environment. These are code-backed decisions; visual recapture and finish review remain pending.

**Key Characteristics:**
- Restrained green actions on a pale canvas.
- Georgia page title with system type for operational content.
- Flat white panels, thin borders and tonal state changes.
- Scoped clay, blue and gold editing contexts; depth confined to the Clip Studio layout model.
- Compact labels, readable paragraphs and visible keyboard focus.
- Responsive stacking and reduced-motion support.

## Colors

The palette combines deep green controls with warm, near-white working surfaces. Frontmatter values are normative; the sidecar's generated tonal ramps are panel previews, not additional implemented colors.

### Primary

- **Forest Green** (`accent`): primary controls, links, active progress and status text.
- **Deep Forest** (`accent-hover`) and **Pressed Forest** (`accent-active`): primary button interaction states.
- **Soft Green** (`tint`): secondary hover, recent-run interaction and status backgrounds.
- **Pressed Soft Green** (`secondary-active`): secondary button active background.
- **Selected Paper** (`selected-surface`): selected recent-run background.
- **Completed Green** (`progress-complete`): the border of completed workflow steps.

### Secondary

- **Clay Paper** (`studio-tint`) and **Clay Ink** (`studio-ink`): Clip Studio background, readable copy, current Clip step and selected format controls.
- **Clay Face** (`studio-face`) and **Clay Edge** (`studio-side`): the model's video plane, Studio border and separately rotated edge face. The edge conveys model thickness.
- **Source Paper** (`source-tint`) and **Source Blue** (`source-ink`): the Source legend and current Source step.

### Tertiary

- **Caption Paper** (`caption-tint`) and **Caption Ink** (`caption-ink`): the caption plane, Campaign legend and current Campaign step.

### Neutral

- **Ink** (`ink`): body text and completed step labels.
- **Muted Ink** (`muted`): supporting text, pending steps and metadata.
- **Paper** (`surface`): panel and field backgrounds; text on filled primary controls.
- **Pale Canvas** (`canvas`): the surrounding page and empty preview inset.
- **Quiet Line** (`line`): panel strokes and section dividers.
- **Field Line** (`field-border`): input, select and textarea strokes.

### Functional states

- **Amber Focus** (`focus`): keyboard focus outlines across controls, links and disclosures.
- **Brick Error** (`error`): failure text, accompanied by readable messages.

**The Green State Rule.** Use green for actions and selected or completed progress, while keeping processing state meaning explicit in text.

**The Editing Context Rule.** Reuse these paired tones for their named editing contexts; keep action, processing and completion meaning explicit.

## Typography

**Display Font:** Georgia with a serif fallback.
**Body Font:** system-ui with a sans-serif fallback.

**Character:** The page title supplies a restrained editorial accent. Operational headings, controls and detail use familiar system type for clear scanning.

### Hierarchy

- **Display:** the normal-weight page title; its mobile size is (32px) below the first layout breakpoint.
- **Headline:** panel headings; their narrow-screen size is (22px).
- **Title:** run titles and supporting subsection headings.
- **Body:** workflow explanation and detail, with paragraphs limited to (70ch).
- **Label:** field labels and compact interface descriptions. Progress text uses the same size with current-step weight (650).
- **Button:** medium-weight action labels, with normal line height.
- **Small:** source metadata, footer and table information. Source facts use tabular numerals.

Headings balance their wrapping. Long brief and error text can wrap anywhere instead of forcing horizontal page overflow.

**The Content First Type Rule.** Keep the serif signature on the page title and use the operational type scale for task information.

## Layout

The current workspace uses a centered container with a maximum width of (1240px), desktop horizontal padding of (32px), and native section links below the header. The main work area pairs a sidebar of up to (320px) with the remaining preview space, separated by (24px). The tinted automatic action panel sits above recent runs in the sidebar; the larger white preview panel spans both rows and contains its own numbered progress list. Panels have (24px) internal padding.

Clip Studio follows the work area as a full-width clay panel. Two equal columns pair its copy and controls with the layout model, separated by (48px), reducing to (24px) at the first breakpoint. Controls have a maximum width of (400px). The model scene is (420px) high, uses perspective of (900px), and keeps the frame within (70%) of its column. Format choices set vertical, square or landscape proportions.

The collapsed campaign setup panel follows Studio at full width. With the guided script active, it shows one fieldset at a time beneath three equal-width step controls; paired fields retain their two-column layout. The source markup preserves the two-column fieldset fallback and its (32px) gap. The two workflow-map inputs also span the available width and meet in a tinted planning/rendering area. A small inline SVG connects the inputs geometrically; the explanatory text and ordered lists carry its meaning.

At (800px) and below, the work area stacks in automatic action, preview, then history order. Header and main horizontal padding become (24px), the page title reduces, and fallback campaign fieldsets become one column. At (600px) and below, Studio and the workflow map become one column; the map hides its SVG connector. The Studio scene becomes (380px) high and the frame may use (85%) of its column. Progress retains five columns with a minimum width of (112px) per step and scrolls horizontally, with proximity scroll snapping. At (480px) and below, horizontal padding becomes (16px), panels use (20px) padding, paired form fields become one column, and campaign action buttons stack at full width. Studio format and campaign step controls use smaller padding and label-sized text. Download links wrap and tables scroll within their own wrapper.

Media fills the preview width, uses contained fitting and is capped at (520px) height. A dark inset with explanatory text occupies empty preview space with a minimum height of (280px), reducing to (240px) on narrow screens. It uses the existing media background rather than a fabricated video frame. Repeated gaps and margins retain the incumbent spacing scale.

## Elevation & Depth

Work surfaces remain flat: white panels, a pale page, tinted states and thin borders provide separation. Button interaction changes color without translating or scaling the element. Clip Studio's layout model is the approved local exception. The video plane rotates with a separate edge face; its caption plane sits forward by (32px). Neutral offset shadows show the separation of these planes only.

### Shadow Vocabulary

- **Model video plane** (`0 18px 32px rgba(0,0,0,.14)`): local separation inside the CSS3D layout model.
- **Model caption plane** (`0 12px 20px rgba(0,0,0,.12)`): local separation of the forward caption plane.

The controlled angle changes the model with a (180ms) `cubic-bezier(.16,1,.3,1)` transition. There is no animation loop. Reduced-motion preference removes transitions and transforms, disables the angle control and describes the flat view.

**The Flat Surface Rule.** Establish work-surface hierarchy through borders and tone; confine shadows and three-dimensional transforms to the Clip Studio layout model.

## Shapes

Controls, status chips and recent-run buttons use the compact control radius. Preview insets and alerts use the intermediate radius; main panels use the broad panel radius. Borders are generally (1px); workflow step rules are (2px). The shapes stay restrained and rectangular.

Keyboard focus uses an amber outline of (3px), offset by (3px), on buttons, links, disclosures and fields. Keep that treatment outside the component border.

## Components

### Buttons

Clear, compact controls with the shared control radius and medium-weight labels. Primary buttons pair the accent fill with white text; secondary buttons pair a white surface with accent text and border. Shared padding is in frontmatter. Minimum control height is (44px); the full-width automatic action is (48px).

Primary hover and active states deepen the fill. Secondary hover and active states use pale green tones with accent text. Disabled controls use opacity (.65) and a waiting cursor. Color and border transitions last (160ms) with `ease-out`; reduced-motion preference removes them.

### Inputs / Fields

White fields with muted green-gray strokes, the control radius and inherited body typography. Field padding follows the updated component contract. Labels sit above the field with a (6px) gap; placeholders use muted ink at full opacity. Textareas have a minimum height of (82px) and resize vertically. Checkboxes use accent color and a (16px) square. Fields keep accent caret color and the shared focus outline. The guided form uses native validity checks and readable error text, reveals the invalid step and focuses its control before submission.

### Chips

Status labels combine soft green fill and accent text with the compact control radius. Failed states use error text on the existing pale warning background; paused, cancelled and retry-waiting states use ink on the pale canvas. Every label describes the actual state in words. These are not interactive filter controls.

### Cards / Containers

Main work panels use white surfaces, a quiet border and the panel radius. The automatic action panel and joined map output use the existing soft green tint. Actual media and empty preview insets share the incumbent dark media background and intermediate radius. Empty preview text uses soft green and is limited to (36ch); it distinguishes failure, cancellation, pause, required subtitles and automatic retry. These local media treatments do not introduce a new palette token. Internal spacing follows the responsive layout rules; panel surfaces remain flat, including the clay Studio panel surrounding its model.

### Navigation

Native anchor links lead to Preview, Clip studio, Workflow map and Campaign setup. They use compact medium-weight text with a minimum target height of (44px), muted ink at rest, and accent color with an underline on hover. The campaign link opens its disclosure at Campaign. Narrow-screen navigation uses the label size.

The preview contains a five-step ordered progress list. Each step has a two-digit number set with tabular numerals and a top rule: pending uses quiet line and muted text, current uses accent with weight (650), and completed uses completed green with ink text. The active step exposes `aria-current="step"`. Responsive scrolling follows Layout.

The campaign disclosure spans the workspace width and uses ink summary text at the title size with weight (600), native expandable behavior and the shared focus treatment. The error details disclosure preserves the actual run error below a short explanation. Campaign creation returns the operator to the preview; choosing an alternative cut opens campaign setup without bypassing review. Programmatic handoff scrolling respects reduced-motion preference.

### Clip Studio layout model

A clay video plane and pale gold caption plane provide a clear layout diagram, with a separate rotated edge representing thickness. The model is explicitly labeled as a layout model; actual footage remains in Preview. Vertical (9:16), square (1:1) and landscape (16:9) format controls expose selection with `aria-pressed`. A range control inspects angles from (-30°) to (30°), starting at (-18°); Front view returns the angle to (0°). Reduced-motion preference displays the model flat.

Choosing a Studio format updates the local model. Use format in campaign explicitly applies it to the existing format field and reveals Clip settings, preserving the source, caption and permissions. The caption plane reflects the form's caption or an explicit placement label. The model uses CSS and local JavaScript, with no new dependencies, network requests or generated imagery.

### Guided campaign setup

Campaign, Source and Clip form a three-step ordered sequence. Current-step controls expose `aria-current="step"`, with gold, blue and clay tones matching their fieldset legends. Back preserves entered data. Moving forward validates preceding steps; final submission validates all steps, including hidden ones, before posting. An invalid step is opened and its failing control receives focus. Native input contracts remain intact. Source validation requires exactly one source outside practice mode, and campaign duration limits constrain desired clip length.

The bottom action row remains visible with a sticky white surface. A concise task summary carries the current practice/campaign mode, platform, desired length and format, while preserving the review requirement. Research and alternative-cut actions reveal Clip settings and preserve the existing source and disclosure fields. The automatic preview action remains independent of this form.

### Recent runs

Recent-run selectors are stacked text buttons with a wrapping title and smaller muted metadata. Selection changes the border to accent and the fill to selected paper, and exposes `aria-pressed`. Hover and active use soft green while preserving ink text. Text aligns left and the list uses the smallest shared gap. History sits beneath the automatic action on desktop and after the preview when stacked. The list has a maximum height of (360px), internal scroll and room around focus outlines. Unchanged polling preserves the existing controls instead of rebuilding them.

## Do's and Don'ts

### Do:

- **Do** preserve the green action palette, pale canvas and white work surfaces.
- **Do** use the shared control, inset and panel radius roles.
- **Do** pair state color with a readable label and visible keyboard focus.
- **Do** let controls, downloads and long text wrap within the available width.
- **Do** keep color transitions brief and respect reduced-motion preference.
- **Do** use the approved editing tones for Studio, Source and Campaign contexts.
- **Do** label the model as a layout diagram and apply its format to campaign settings explicitly.
- **Do** reveal and focus the invalid step before the guided form can submit.

### Don't:

- **Don't** substitute decorative imagery for unavailable video output.
- **Don't** carry the Studio model's shadows or transforms into the flat panel system.
- **Don't** use selected or completed styling as evidence of publication, payment or successful rendering.
