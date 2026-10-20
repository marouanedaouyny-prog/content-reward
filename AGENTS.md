# Project instructions: YouTube clipping

## User's standing workflow

The user wants the complete workflow: search for popular long YouTube videos,
find strong standalone moments and make three or four distinct finished clips.
The user explicitly approved `clips/caption-preview-studio.mp4` as the visual
template on October 16. **Use `studio` captions and `fit` framing by default for
all clips.** Keep its natural-case white text, selective cyan word emphasis and
full source image over a blurred background. Do not return to the previous lime
or white/gold styles unless the user explicitly requests them.

On October 18 the user approved `clips/50-Cent-Colorized.mp4` and requested a
repeatable workflow producing **20 clips per run**, with configurable larger
counts and repeated fresh runs. For this production workflow use
`make-20-clips.cmd`: `colorized` lime captions, `fit` framing, and up to 20 strong
moments per source, moving to other fresh eligible sources when needed.
This explicit production choice overrides the older count/style defaults for
that launcher. Historical saved orders retain their original settings.
The approved sample establishes the caption look; larger runs should still
reject detected introductions and ads and find independent useful moments.

### Chat-triggered runs

When the user says "run it", "start the clipping workflow", or equivalent in
this project's clipping context, execute the workflow directly with the tools:

```powershell
.\.venv\Scripts\python.exe -m clipping.autorun
```

`run-clipping-auto.cmd` is the equivalent noninteractive Windows launcher.
It automatically resumes the latest unfinished production order, preserves its
saved settings, and starts a fresh 20-clip colorized/fit order after completion.
Use `--new` only for an explicit fresh batch and `--status` to inspect progress.
An active order returns `already_running`; monitor that order instead of
starting a duplicate. Read its manifest/result to provide the actual clips and
post captions. This entry point requires no keypress or Explorer window.
Use the existing bounded retries and checkpoints. Report actual network limits;
the launcher inherits this process's proxy, TLS and permission restrictions.

Read [the agent roadmap](research/studio_template_roadmap.md) before creating or
restyling clips. It records the exact template settings and review requirements.

Follow these steps for every new YouTube clipping order:

1. **Identify the current order.** Check its niche, source constraints and latest
   job state. A new order starts a fresh search. An explicit request to restyle
   an existing clip reuses that clip's source and transcript.
2. **Search YouTube.** Use the project's discovery flow, including Selenium
   where configured. Compare real long-video candidates using their topic,
   duration, publication date and observed popularity. Follow any user-specified
   search constraints; otherwise use the project's current eligibility rules.
3. **Find the best moment inside the source.** Inspect its actual transcript and
   available replay data. Prefer a strong opening, a clear point or payoff, and
   enough context for the clip to stand alone. Preserve completed thoughts.
   Generic filler questions and the first arbitrary 30 seconds are weak choices.
   Source view counts alone do not identify its best moment. When replay data is
   missing, label the selection as editorial; do not claim it is verified as the
   most replayed or most famous moment.
4. **Make a finished batch.** Default to four distinct highlights from the same
   source; three is acceptable when only three strong windows fit. Render each
   in vertical 9:16 with the approved `studio-v1` template unless the user asks
   otherwise. Preserve original speech and full-image framing so speakers stay
   visible through shot changes. Different timestamps alone do not establish
   different takeaways; check transcript similarity as well as overlap.
5. **Add professional colored captions.** Use the actual source speech, short
   readable phrases, at most two lines, consistent typography, selective color
   emphasis and appropriate word timing. Keep subtitles clear of faces and
   screen edges. Review transcription errors, line breaks and distracting
   effects. Keep the post caption separate from the spoken on-video subtitles.
6. **Review the actual export.** Check the opening, ending, shot changes, audio,
   caption readability and synchronization. Verify that the MP4 decodes and that
   the delivered file belongs to the current order. Correct visible problems
   before presenting it as finished.
7. **Deliver the result.** Provide the new finished clips and their post captions
   concisely. Repeated links to a previous clip do not complete a new order.
   State any material selection or verification limit accurately.

For every new order, produce **three or four distinct clips
from one freshly discovered long video**, with the approved `studio` caption
style. Fetch public captions and replay metadata first, select non-overlapping
moments, then download only their bounded time ranges. Never fall back to
downloading the full source or its full audio. If public captions are unusable,
try another eligible source and report the limit accurately. New controller
invocations default to four partial-download clips; historical saved single-clip
orders preserve their original settings. Finished clips and their post captions
go into the single project `clips/` folder. Label previous-source samples clearly;
they do not count toward the fresh batch.

The newer 20-clip production workflow follows the user's requested count instead
of the legacy three/four count. It may use several sources; every new invocation
still starts fresh discovery. Exclude previous source intervals and repeated
takeaways, save partial work on failures, and do not weaken quality or duplicate
clips to fill the target. Report an insufficient-source shortfall accurately.
Captions with gross omissions or repeated hallucinations must not pass just
because the SRT matches its own faulty ASR. Compare against timed source cues.

Clipping runs independently of social authentication. The user now wants to
connect **Instagram, YouTube and TikTok step by step**, starting with Instagram,
and **prepare posts for review**. Keep publishing disabled; no upload, posting,
following, commenting or outbound account activity is authorized by this choice.
Use the approved studio template for prepared posts. Account-specific content
should use the user's chosen niche; that niche and the public profile targets
have not yet been supplied.

Prepared posts from the newer production launcher use its explicitly approved
colorized style; publishing remains disabled.

The user will enter credentials locally. For Instagram, use the existing
`connect-instagram-token.ps1` hidden prompt in a normal PowerShell terminal;
never ask for tokens, passwords or cookies in chat. Confirm actual account
identity/access before describing a connection as verified. Treat credentials
for each platform separately. YouTube/TikTok authentication is not established
by the existing Instagram connector or by a public profile URL.

## Project entry points

For the October 18 varied-style order `67f69696-94b1-4649-b2cf-725647f88100`,
the user explicitly approved using the cached Dana White interview to create
four new distinct clips. This order may reuse that source and transcript;
label the cached-source provenance and editorial selection accurately. Exclude
the earlier preview's window. The next new order still starts a fresh search.

- Complete order controller: `run-youtube-clipping.cmd`; use `--resume latest`
  after connection failure and `--status` to inspect saved state.
- Chat-triggered/noninteractive runner: `run-clipping-auto.cmd`, implemented in
  `clipping/autorun.py`; automatically resume or start a new production batch.
- Repeatable 20-clip workflow: `make-20-clips.cmd`; `--clips 40` chooses another
  positive target, `--resume latest` preserves the saved production order. Find
  the newest completed files and post captions in `clips/LATEST-CLIPS.txt`.
- Double-click resume: `resume-youtube-clipping.cmd`. Batch discovery can fall
  back to the public provider if Chrome cannot start, preserving the saved order.
- Explicit varied-style order: `start-varied-clips.cmd` or `--caption-styles
  studio pro colorized classic`. This rotates styles across new clips for that
  order, keeping studio/fit as the permanent defaults. The user requested a fresh
  varied-style search on October 17; older previews do not complete that order.
- Workflow, runtime setup and API notes: `clipping/README.md`.
- Normal-terminal Selenium launcher: `start-youtube-clipping.cmd`.
- Caption grouping and styles: `clipping/captions.py` and `clipping/caption_styles.py`.
- Approved shared defaults: `clipping/template.py`; agent reproduction roadmap:
  `research/studio_template_roadmap.md`.
- Source-window selection: `clipping/planning.py`.
- Real-source and caption verification records: `research/`.

These instructions record user preferences. They do not establish that every
step or visual-quality check is already automated in the current implementation.
