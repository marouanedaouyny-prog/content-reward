# PRD — Growth Optimization, Quality, Hashtags & Posting Intelligence

This is the growth-system specification supplied by the user on October 20, 2026.
The implementation order is in section 58; general hardening requirements remain
in the root `PRD.md` and `docs/REFACTOR_PLAN.md`. Publishing stays disabled
(see `AGENTS.md`): "publish" below means preparing/scheduling a publication
package, never a real platform upload.

## 1. Project Goal

Upgrade `content-reward` from a clip-generation system into a growth-optimization system.

Primary goal:

```text
Generate fewer but stronger clips
→ better retention
→ better reach
→ more profile visits
→ more followers
```

Main optimization target:

```text
followers_gained_per_1000_views
```

Secondary targets:

```text
completion_rate
average_watch_time
shares
saves
comments
profile_visits
engagement_rate
```

Do NOT optimize only for views.

---

## 2. Core Product Principle

Current system:

```text
Find good moment
→ render clip
```

Target system:

```text
Find strong source
→ find high-growth moment
→ improve hook
→ improve edit
→ generate captions
→ generate hashtags
→ choose posting time
→ publish
→ measure performance
→ learn
→ improve next clips
```

---

## 3. Main Weaknesses To Fix

Current weaknesses:

```text
weak hook detection
weak retention prediction
generic captions
generic hashtags
no posting-time intelligence
no follower-conversion tracking
no post-performance learning
limited quality scoring
limited A/B testing
limited niche adaptation
```

Codex must improve these areas without breaking current clipping pipeline.

---

## 4. Growth Score

Create a centralized `GrowthScorer`.

Example:

```python
growth_score =
    hook_strength * 0.22 +
    retention_potential * 0.18 +
    shareability * 0.14 +
    standalone_clarity * 0.12 +
    emotional_intensity * 0.10 +
    novelty * 0.08 +
    niche_relevance * 0.06 +
    follow_potential * 0.10
```

Weights must be configurable.

Example:

```yaml
growth_scoring:
  hook_strength: 0.22
  retention_potential: 0.18
  shareability: 0.14
  standalone_clarity: 0.12
  emotional_intensity: 0.10
  novelty: 0.08
  niche_relevance: 0.06
  follow_potential: 0.10
```

---

## 5. Hook Quality

The first 1–3 seconds are critical.

Create hook analysis.

Score:

```text
surprise
curiosity
conflict
bold statement
strong question
clear promise
unexpected fact
emotional line
authority statement
```

Weak hooks:

```text
"So basically..."
"Today we are going to..."
"Let me explain..."
"As I was saying..."
```

Strong hooks:

```text
"This mistake cost him millions."
"Nobody tells you this about..."
"This is why most people fail..."
"He thought he was winning until..."
```

Do NOT fabricate claims.

Only generate hooks supported by source content.

---

## 6. Hook Reframing

If source starts weakly:

```text
original clip
↓
identify strongest sentence
↓
move strongest sentence earlier when context permits
```

Do not change factual meaning.

Possible edit:

```text
strong statement first
→ quick context
→ payoff
```

---

## 7. Clip Duration Optimization

System must evaluate clip duration dynamically.

Default ranges:

```yaml
duration:
  min_seconds: 18
  preferred_min: 24
  preferred_max: 42
  max_seconds: 60
```

Do not force every clip to same length.

Choose duration based on:

```text
idea completeness
speech speed
payoff timing
platform
historical performance
```

---

## 8. Retention Prediction

Create `RetentionScorer`.

Signals:

```text
strong first sentence
low silence
fast information density
sentence continuity
clear payoff
speaker energy
visual activity
caption density
clip length
number of topic changes
```

Penalties:

```text
slow intro
long pauses
repetition
unnecessary setup
dead air
weak ending
mid-sentence start
mid-answer ending
```

---

## 9. Silence Removal

Automatically detect silence.

Default:

```yaml
silence:
  threshold_db: -35
  min_duration_ms: 450
  aggressive_cut: false
```

Remove unnecessary pauses.

Do NOT make speech unnatural.

Keep micro-pauses where needed.

---

## 10. Filler Word Cleanup

Optional feature:

Detect:

```text
uh
um
you know
basically
like
kind of
sort of
```

Only remove when cut is visually/audio safe.

Never make jump cuts excessive.

---

## 11. Visual Quality

Target format:

```text
1080x1920
9:16
```

Minimum quality checks:

```text
no black borders
face visible
subject not cropped incorrectly
captions inside safe zone
minimum bitrate
stable FPS
audio synchronized
```

---

## 12. Smart Reframing

Improve framing.

Use:

```text
face detection
speaker detection
active speaker tracking
center-of-interest detection
```

Modes:

```text
fit
crop
speaker-focus
split-screen
```

Default:

```text
speaker-focus if reliable
otherwise fit
```

Never crop important visual information.

---

## 13. Face Tracking

If video contains people:

```text
detect faces
→ track face
→ follow dominant speaker
→ smooth crop movement
```

Avoid shaky camera movement.

Use temporal smoothing.

---

## 14. Captions

Captions must improve readability and retention.

Requirements:

```text
large font
high contrast
2–5 words per visual line
safe-zone positioning
word-level timing when available
highlight active word
no overflow
```

---

## 15. Caption Styles

Support configurable styles:

```text
studio
colorized
minimal
karaoke
bold
```

Example:

```yaml
captions:
  style: colorized
  words_per_line: 4
  max_lines: 2
  highlight_active_word: true
```

---

## 16. Caption Intelligence

Do NOT use raw transcript blindly.

Clean:

```text
punctuation
capitalization
filler repetitions
broken sentences
ASR mistakes
```

Preserve meaning.

Do not rewrite content into different claims.

---

## 17. Emphasis Detection

Highlight words related to:

```text
numbers
money
strong emotions
names
surprise
conflict
results
important verbs
```

Example:

```text
"He made $50,000 in 7 days"
```

Highlight:

```text
$50,000
7 days
```

---

## 18. Title / Overlay Text

Generate optional top overlay.

Examples:

```text
"This Changed Everything"
"Biggest Mistake"
"Why He Failed"
"Nobody Expected This"
```

Rules:

```text
max 6 words
must match clip
must not mislead
must not duplicate subtitles
```

---

## 19. Description Generator

Create post caption generator.

Structure:

```text
Hook
↓
short context
↓
optional CTA
```

Example pattern:

```text
Most people miss this part.

[short context]

Follow for more clips like this.
```

Do not spam CTA on every post.

---

## 20. CTA Strategy

Create multiple CTA categories.

```text
follow
comment
save
share
profile
none
```

System should learn which CTA performs best.

Examples:

```text
Follow for more breakdowns.
Save this for later.
Would you agree?
Part 2 on profile.
```

Never use fake scarcity or misleading statements.

---

## 21. Hashtag Engine

Create `HashtagGenerator`.

Do NOT output random generic hashtags.

Use 3 layers:

```text
1. niche hashtags
2. topic-specific hashtags
3. broader discovery hashtags
```

Example:

```text
#podcast
#entrepreneurship
#business
#startup
#mindset
```

Avoid:

```text
#fyp
#viral
#trending
```

as default-only strategy.

They may be included if data shows value, but not relied upon.

---

## 22. Hashtag Count

Config:

```yaml
hashtags:
  min: 3
  preferred: 5
  max: 8
```

Platform-specific limits must be configurable.

---

## 23. Hashtag Ranking

Score hashtags using:

```text
topic relevance
niche relevance
competition
historical account performance
platform
recent post performance
```

Example:

```python
hashtag_score =
    relevance * 0.45 +
    account_history * 0.25 +
    discoverability * 0.20 +
    freshness * 0.10
```

---

## 24. Hashtag Deduplication

Avoid repetitive identical sets.

Bad:

```text
post 1 → same 5 hashtags
post 2 → same 5 hashtags
post 3 → same 5 hashtags
```

Use controlled variation.

---

## 25. Hashtag Memory

Store:

```text
hashtag
platform
uses
average_views
average_completion_rate
average_follows
last_used
```

Use history to improve future hashtag selection.

---

## 26. Posting Time Intelligence

Create `PostingTimeOptimizer`.

Initial version:

Use platform + timezone + account history.

Store:

```text
weekday
hour
views
watch_time
followers_gained
engagement
```

Calculate best slots.

---

## 27. Initial Posting Windows

Before account-specific data exists, use configurable default time windows.

Do not hardcode universal claims.

Example:

```yaml
posting:
  timezone: Africa/Casablanca

  default_windows:
    - "12:00-14:00"
    - "18:00-22:00"
```

These are fallback windows only.

Historical account performance must eventually override them.

---

## 28. Posting Frequency

Create frequency rules.

Example:

```yaml
posting:
  max_posts_per_day: 3
  minimum_gap_minutes: 180
```

Do not publish 20 clips immediately.

Queue them.

---

## 29. Content Queue

Add scheduling queue.

Statuses:

```text
READY
SCHEDULED
PUBLISHING
PUBLISHED
FAILED
```

Fields:

```text
clip_id
platform
scheduled_at
caption
hashtags
CTA
account_id
```

---

## 30. Avoid Cannibalization

Do not post very similar clips close together.

Rules:

```text
same source
same speaker
same topic
same hook style
```

Add spacing.

Example:

```yaml
content_spacing:
  same_source_hours: 8
  same_topic_hours: 6
```

---

## 31. Platform-Specific Optimization

Different platforms require different settings.

Create:

```text
platform_profiles/
├── tiktok.yaml
├── youtube_shorts.yaml
└── instagram_reels.yaml
```

Each profile can control:

```text
duration
caption style
hashtags
description length
CTA style
posting windows
```

---

## 32. Niche Profiles

Create niche configs:

```text
podcast
business
gaming
sports
motivation
technology
stream
comedy
```

Example:

```yaml
niche: podcast

preferred_duration:
  min: 25
  max: 45

signals:
  strong_opinion: high
  educational_value: high
  emotional_intensity: medium
```

---

## 33. Source Selection

Improve source scoring.

Rank long videos by:

```text
views/hour
upload freshness
channel authority
engagement
topic relevance
replay data
duration
transcript availability
```

Example:

```python
source_score =
    velocity * 0.30 +
    relevance * 0.25 +
    engagement * 0.15 +
    freshness * 0.15 +
    replay_signal * 0.10 +
    transcript_quality * 0.05
```

---

## 34. Long Video Strategy

For long videos:

```text
do not download full file
```

Workflow:

```text
get metadata
→ get transcript
→ analyze candidate moments
→ select top 3–4
→ download only timestamp windows
```

Example:

```text
2h podcast

selected:
00:18:40–00:19:12
00:44:30–00:45:10
01:20:15–01:20:50
01:46:05–01:46:42
```

Only these ranges should be downloaded.

---

## 35. Candidate Count

Config:

```yaml
selection:
  candidate_count: 20
  final_clip_count: 4
```

Pipeline:

```text
20 candidates
→ score
→ deduplicate
→ quality filter
→ final 4
```

---

## 36. Follower Conversion Tracking

Track:

```text
views
profile_visits
followers_gained
```

Calculate:

```text
follow_conversion_rate =
followers_gained / views
```

Primary metric:

```text
followers_per_1000_views =
followers_gained / views * 1000
```

---

## 37. Example

Clip A:

```text
100,000 views
200 follows
```

Result:

```text
2 followers / 1000 views
```

Clip B:

```text
20,000 views
500 follows
```

Result:

```text
25 followers / 1000 views
```

System must prefer patterns similar to Clip B.

---

## 38. Performance Database

Store per post:

```text
clip_id
source_id
platform
posted_at
duration
hook_type
caption_style
hashtags
CTA
views
likes
comments
shares
saves
watch_time
completion_rate
profile_visits
followers_gained
```

---

## 39. Learning Loop

Target:

```text
Publish
↓
wait for metrics
↓
collect metrics
↓
calculate quality
↓
associate result with features
↓
update scoring preferences
↓
future clips improve
```

---

## 40. Start Rule-Based

Do NOT add complicated ML initially.

Start with:

```text
weighted averages
historical averages
Bayesian smoothing
simple ranking
```

Only add ML when enough performance data exists.

---

## 41. Exploration vs Exploitation

Do not always choose same style.

Use:

```text
80% proven patterns
20% experiments
```

Config:

```yaml
optimization:
  exploitation_ratio: 0.8
  exploration_ratio: 0.2
```

---

## 42. A/B Testing

Generate controlled variants.

Possible variables:

```text
hook
caption style
overlay title
clip duration
CTA
hashtags
posting time
```

Only change 1–2 variables per experiment.

---

## 43. Experiment Example

```text
Same clip

A:
25 sec
colorized captions
no CTA

B:
34 sec
colorized captions
Follow CTA
```

Compare:

```text
completion rate
followers/1000 views
shares
```

---

## 44. Quality Score

Create final quality score:

```python
quality_score =
    video_quality * 0.15 +
    audio_quality * 0.15 +
    subtitle_quality * 0.15 +
    hook_score * 0.20 +
    retention_score * 0.20 +
    completeness * 0.15
```

Minimum production threshold:

```yaml
quality:
  minimum_score: 0.75
```

Reject clips below threshold.

---

## 45. Audio Quality

Validate:

```text
voice audible
no clipping
no extreme volume
no audio/video desync
```

Normalize loudness.

Suggested target:

```text
around -14 to -16 LUFS
```

Make configurable.

---

## 46. Video Quality

Check:

```text
resolution
bitrate
FPS
frame corruption
black frames
frozen frames
```

---

## 47. Subtitle Quality

Check:

```text
timing
overflow
spelling
word alignment
safe-zone
line length
```

---

## 48. Content Completeness

Clip must:

```text
start with understandable context
contain one complete idea
finish with payoff
```

Reject clips that end prematurely.

---

## 49. Viral Signals

Candidate moment should detect:

```text
shock
conflict
strong opinion
unexpected answer
money
mistakes
success/failure
story climax
controversial statement
clear lesson
specific numbers
```

Do not artificially manufacture them.

---

## 50. Topic Continuity

Do not cut:

```text
setup
```

from:

```text
payoff
```

If clip requires 5 extra seconds for comprehension, include them.

---

## 51. Metadata Generation

For each final clip create:

```json
{
  "title": "",
  "description": "",
  "hashtags": [],
  "CTA": "",
  "hook_type": "",
  "topic": "",
  "predicted_growth_score": 0.0,
  "recommended_post_time": ""
}
```

---

## 52. Human-Readable Manifest

Create:

```text
output/manifests/<clip-id>.json
```

Include:

```text
source
timestamps
scores
hashtags
caption
posting time
render settings
```

---

## 53. Dashboard Additions

Dashboard should show:

```text
best clips
worst clips
followers/1000 views
best posting hour
best hashtag groups
best duration
best caption style
best niche
best hook type
```

---

## 54. Analytics Reports

Generate reports:

```text
daily
weekly
monthly
```

Example:

```text
Top-performing hook:
controversial opinion

Best duration:
28–36 sec

Best posting window:
19:00–21:00

Best CTA:
no CTA

Best hashtag group:
business + entrepreneurship + startup
```

---

## 55. Weak Pattern Detection

System should identify:

```text
low retention patterns
bad hashtags
bad posting slots
bad clip lengths
low-follow topics
```

Automatically reduce future priority.

---

## 56. Minimum Data Thresholds

Avoid learning from insufficient data.

Example:

```yaml
learning:
  minimum_posts_per_pattern: 5
  minimum_views_per_post: 500
```

Do not overreact to one viral or failed clip.

---

## 57. Cold Start

When account has no data:

Use:

```text
general heuristics
niche config
platform config
source signals
```

Then transition toward account-specific behavior.

---

## 58. Optimization Priority

Codex must implement in this order.

### Phase 1

```text
quality scoring
hook scoring
retention scoring
```

### Phase 2

```text
caption improvements
visual framing
silence cleanup
```

### Phase 3

```text
hashtag engine
description generator
CTA generator
```

### Phase 4

```text
posting scheduler
posting-time optimizer
content spacing
```

### Phase 5

```text
performance metrics
followers/1000 views
historical analytics
```

### Phase 6

```text
feedback loop
experiments
adaptive scoring
```

---

## 59. Codex Rules

Do NOT:

```text
invent fake analytics
hardcode "best posting time" globally
use random hashtags
optimize only for views
generate misleading hooks
spam CTAs
destroy current working clipping flow
```

---

## 60. Preserve Current Pipeline

Existing workflow must remain functional:

```text
discovery
→ selection
→ partial download
→ transcription
→ captions
→ render
→ QC
```

Enhancements must be modular.

---

## 61. New Modules

Recommended:

```text
growth/
├── hook.py
├── retention.py
├── quality.py
├── hashtags.py
├── metadata.py
├── timing.py
├── experiments.py
└── optimizer.py
```

---

## 62. Suggested Interfaces

```python
class HookScorer:
    def score(self, candidate):
        ...

class RetentionScorer:
    def score(self, candidate):
        ...

class HashtagGenerator:
    def generate(self, context):
        ...

class PostingTimeOptimizer:
    def recommend(self, platform, history):
        ...

class GrowthOptimizer:
    def rank(self, candidates):
        ...
```

---

## 63. Configuration

Add:

```yaml
growth:
  optimize_for: followers_per_1000_views

  candidate_count: 20
  final_clip_count: 4

  duration:
    min: 18
    preferred_min: 24
    preferred_max: 42
    max: 60

  hashtags:
    min: 3
    preferred: 5
    max: 8

  posting:
    max_per_day: 3
    minimum_gap_minutes: 180

  quality:
    minimum_score: 0.75

  experiments:
    enabled: true
    exploration_ratio: 0.20
```

---

## 64. Tests

Add tests for:

```text
hook scoring
retention scoring
quality scoring
hashtag generation
hashtag deduplication
posting-time calculations
content spacing
follower conversion
experiment assignment
adaptive weights
```

---

## 65. Definition Of Done

Feature complete when system can:

```text
find long video
→ identify top candidate moments
→ select best 3–4
→ download only those sections
→ improve edit quality
→ generate subtitles
→ generate post caption
→ generate relevant hashtags
→ recommend publishing time
→ schedule clips
→ track performance
→ calculate followers/1000 views
→ learn from historical posts
→ improve next batch
```

---

## 66. Final Objective

Do NOT build:

```text
automatic clip factory
```

Build:

```text
automatic audience-growth engine
```

Optimization target:

```text
maximum follower growth
with
minimum manual work
while maintaining high content quality
```
