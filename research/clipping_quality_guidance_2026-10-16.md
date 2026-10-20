# Better YouTube clipping: primary-source guidance

Researched 2026-10-16. The user selected `clips/caption-preview-studio.mp4`
as the visual reference. This note addresses choosing stronger moments; it does
not establish that the planner already implements every suggestion, or that a
fresh search or export succeeded.

## What the sources support

- **Open immediately with something understandable and worth watching.** An
  official YouTube interview with its Shorts product lead and creator Jenny
  Hoyos emphasizes immediate hooks and concise mini-stories. The one-second
  advice is a creator's approach, not a documented algorithmic threshold or
  performance guarantee. [YouTube Shorts deep dive](https://blog.youtube/creator-and-artist-stories/youtube-shorts-deep-dive/)
- **Review replay spikes in context.** YouTube says retention spikes can reflect
  rewatching or sharing, including replay caused by unclear content. Its
  guidance also recommends bringing compelling later moments forward. This
  supports inspecting a candidate and its context; it does not prove that the
  largest spike makes the best standalone clip. Public replay metadata must
  not be described as the source owner's private Analytics retention report.
  [Audience-retention guidance](https://support.google.com/youtube/answer/9314415?hl=en)
- **Compare relevance, age, duration and observed popularity.** The official
  search API provides publication filters, view-count ordering and a `long`
  duration filter meaning more than 20 minutes. It warns that ordering combined
  with date filters can yield incomplete results. Search more than one relevant
  query and record the candidates actually observed; do not claim exhaustive
  coverage. [Search API reference](https://developers.google.com/youtube/data/reference/rest/v3/search/list?hl=en)
- **Keep source observations auditable.** The video resource documents
  publication time, duration, view count and caption availability. Preserve
  their observation timestamp and provenance. Caption availability is only
  an initial signal: it does not establish that a usable timed transcript has
  actually been retrieved. [Video resource reference](https://developers.google.com/youtube/data/reference/rest/v3/videos)
- **Popularity is not a promise of future clip performance.** YouTube describes
  recommendations as depending on audience relevance, performance and viewer
  satisfaction. Search results are not simply the most-viewed videos. A source
  view count or an internal editorial score is not a virality probability.
  [YouTube performance FAQ](https://support.google.com/youtube/answer/141805?hl=en)
- **Bounded downloads are a supported tool feature.** yt-dlp documents
  `--download-sections` time ranges and its FFmpeg dependency. This supports
  downloading selected windows after transcript planning, with no full-source
  or full-audio fallback. [yt-dlp download options](https://github.com/yt-dlp/yt-dlp#download-options)

## Project editorial rules inferred from that guidance

These are local selection heuristics, not official YouTube ranking rules.

1. For each proposed clip, write one sentence stating its point and payoff.
   Reject a window that needs unseen context to explain its subject, claim or
   answer. Start at a complete thought; finish the answer or story beat.
2. Inspect the opening aloud and in the actual export. Favor a concrete claim,
   surprising result, clear problem or question that the same clip answers.
   Reject filler, promotion and generic questions without a payoff.
3. For a batch of three or four, require different takeaways as well as
   non-overlapping windows. Compare normalized transcript text and meaningful
   topic terms to flag repeated material; inspect flagged pairs before keeping
   both. Different timestamps alone do not make different clips.
4. Use replay data to propose candidates, then check speech and context. If
   replay data is absent, retain an explicit `editorial` selection label. Never
   substitute source-wide views for evidence about a specific moment.
5. Preserve a per-clip review record: source URL and time range, opening,
   takeaway, ending, replay availability, selection rationale and review
   outcome. Validate speech, framing and the approved studio captions on the
   rendered file before delivering it from `clips/`.

No source examined supports guaranteed virality, magic caption colors, a
universal ideal clip duration, or a fixed score that predicts future views.
