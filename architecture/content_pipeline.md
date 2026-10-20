# Content Pipeline Architecture

**Inputs:** Source video (URL or local) → **Outputs:** Compliant, platform-ready clips with metadata

---

## 3.1 Pipeline Stages (Deterministic I/O)

```
SOURCE ACQUISITION
        ↓
TRANSCRIPTION & ANALYSIS
        ↓
SEGMENT DETECTION & SCORING
        ↓
CLIP SELECTION (strategy-aware)
        ↓
EDITING (FFmpeg + filters)
        ↓
CAPTION GENERATION
        ↓
METADATA ENRICHMENT
        ↓
COMPLIANCE QA (automated gates)
        ↓
EXPORT (per-platform variants)
```

---

## 3.2 Stage Specifications

### Stage 1: SOURCE ACQUISITION
| Field | Spec |
|-------|------|
| **Input** | `source_url` (YouTube, Dailymotion, local path), `campaign_id` |
| **Tool** | `yt-dlp` (YouTube/Dailymotion), `ffmpeg` (local) |
| **Output** | `SourceMedia` record: `id, campaign_id, source_url, title, file_hash, media_type, duration, resolution, downloaded_at, status, local_path` |
| **Idempotency** | `file_hash` (SHA-256) → deduplicate |
| **Failure** | `DOWNLOAD_FAILED` → retry 3x, then `MANUAL_CHECKPOINT` |
| **Cost** | FREE (local) |

### Stage 2: TRANSCRIPTION & ANALYSIS
| Field | Spec |
|-------|------|
| **Input** | `SourceMedia.local_path`, `campaign_id` |
| **Tool** | `faster-whisper` (local, FREE) or `whisper.cpp` |
| **Output** | `Transcript` record: `source_media_id, full_text, segments[{start, end, text, confidence}], language, model_used` |
| **Idempotency** | `source_media_id + model_version` |
| **Failure** | `TRANSCRIPTION_FAILED` → fallback model, then `MANUAL_CHECKPOINT` |
| **Cost** | FREE (local GPU/CPU) |

### Stage 3: SEGMENT DETECTION & SCORING
| Field | Spec |
|-------|------|
| **Input** | `Transcript`, `Campaign.editing_rules`, `campaign_type` |
| **Logic** | Score segments by: hook strength (first 3s), topic relevance (keyword match), completeness (sentence boundaries), duration fit, visual change density (scene detection via `ffmpeg select=gt(scene,0.3)`) |
| **Output** | `ClipCandidate[]`: `{source_media_id, start_sec, end_sec, duration, aspect_ratio_candidates, score, reasoning, transcript_segment}` |
| **Idempotency** | `transcript_id + rules_hash + model_version` |
| **Failure** | `SEGMENT_FAILED` → use fallback heuristic (fixed windows) |
| **Cost** | FREE (local) |

### Stage 4: CLIP SELECTION
| Field | Spec |
|-------|------|
| **Input** | `ClipCandidate[]`, `Campaign` (platforms, aspect_ratio requirements, min/max duration) |
| **Strategy** | Per-platform selection: vertical (9:16) for TikTok/IG Reels/Shorts, horizontal (16:9) for YouTube/X. Multi-variant from same source. |
| **Output** | `ClipPlan[]`: `{clip_id, source_media_id, start_sec, end_sec, duration, target_platforms[], aspect_ratio, strategy: "HOOK_FIRST|TOPIC_COMPLETE|VISUAL_PEAK"}` |
| **Idempotency** | `campaign_id + candidates_hash + strategy_version` |
| **Human Gate** | Optional: `CLIP_SELECTION_REVIEW` (configurable) |

### Stage 5: EDITING
| Field | Spec |
|-------|------|
| **Input** | `ClipPlan`, `SourceMedia.local_path` |
| **Tool** | `ffmpeg` (FREE, local) |
| **Operations** | Trim, crop/rescale (aspect_ratio), burn captions, add branding watermark, normalize audio (-16 LUFS), encode H.264 High Profile / AAC |
| **Per-Platform Variants** | Generate variants in parallel: TikTok (9:16, ≤60s), IG Reels (9:16, ≤90s), YT Shorts (9:16, ≤60s), YT Standard (16:9), X (16:9 or 9:16) |
| **Output** | `Clip` record: `id, campaign_id, source_media_id, clip_path, clip_hash, aspect_ratio, duration, status, variant_of` |
| **Idempotency** | `clip_hash` (SHA-256 of output file) → deduplicate |
| **Failure** | `EDIT_FAILED` → retry with simpler filter graph, then `MANUAL_CHECKPOINT` |

### Stage 6: CAPTION GENERATION
| Field | Spec |
|-------|------|
| **Input** | `ClipPlan`, `Campaign` (required_tags, required_mentions, required_disclosure), `Transcript` segment |
| **Logic** | 1. Extract key phrases from transcript segment<br>2. Inject required tags/mentions<br>3. Prepend required disclosure (FTC)<br>4. Truncate to platform limit (TT: 2200, IG: 2200, YT: 5000, X: 280) |
| **Output** | `Caption` record: `clip_id, platform, text, hashtags[], mentions[], disclosure_included: true, char_count` |
| **Idempotency** | `clip_id + campaign_requirements_hash + template_version` |
| **Human Gate** | Optional: `CAPTION_REVIEW` |

### Stage 7: METADATA ENRICHMENT
| Field | Spec |
|-------|------|
| **Input** | `Clip`, `Caption[]`, `Campaign` |
| **Output** | `PublishPackage` per platform: `{clip_id, platform, video_path, caption, tags, mentions, disclosure, privacy_status, scheduled_at, idempotency_key}` |
| **Idempotency** | `clip_id + platform + metadata_hash` |

### Stage 8: COMPLIANCE QA (Automated Gates)
| Gate | Check | Tool | Pass/Fail | Action on Fail |
|------|-------|------|-----------|----------------|
| **Duration** | Within platform min/max | `ffprobe` | ✅/❌ | `QC_FAILED:DURATION` |
| **Resolution** | ≥720p (TT/IG/YT), ≥1080p (YT Standard) | `ffprobe` | ✅/❌ | `QC_FAILED:RESOLUTION` |
| **Aspect Ratio** | Matches platform requirement | `ffprobe` | ✅/❌ | `QC_FAILED:ASPECT` |
| **Codec** | H.264/AAC (all platforms) | `ffprobe` | ✅/❌ | `QC_FAILED:CODEC` |
| **File Size** | Within platform limit | `os.path.getsize` | ✅/❌ | `QC_FAILED:SIZE` |
| **Disclosure** | Required text present at start of caption | String match | ✅/❌ | `QC_FAILED:DISCLOSURE` |
| **Hashtags** | Required tags present | Set containment | ✅/❌ | `QC_FAILED:HASHTAGS` |
| **Mentions** | Required mentions present | Set containment | ✅/❌ | `QC_FAILED:MENTIONS` |
| **Co-posting** | Not a co-post (single account) | Metadata check | ✅/❌ | `QC_FAILED:COPOST` |
| **Reused Content** | `clip_hash` not in recent submissions | DB lookup | ✅/❌ | `QC_FAILED:REUSED` |
| **Audio Level** | -16 LUFS ±2 | `ffmpeg -af loudnorm` | ✅/❌ | `QC_FAILED:AUDIO` |
| **Visual Quality** | No black frames, frozen frames, corruption | `ffmpeg blackdetect, freezedetect` | ✅/❌ | `QC_FAILED:VISUAL` |

**Output:** `QAReport`: `{clip_id, platform, passed: bool, checks[], score: 0-100, status: QA_PASSED|QA_FAILED}`

### Stage 9: EXPORT
| Field | Spec |
|-------|------|
| **Input** | `QAReport` (only PASSED), `PublishPackage[]` |
| **Output** | `ReadyClip` per platform: `{clip_id, platform, video_path, caption, metadata, idempotency_key, qa_score}` |
| **Storage** | `storage/ready/{campaign_id}/{clip_id}_{platform}.mp4` |

---

## 3.3 Data Flow Summary

```
Campaign
    ↓ (discover)
Source URL
    ↓ (download + hash)
SourceMedia (DB)
    ↓ (transcribe)
Transcript (DB)
    ↓ (segment + score)
ClipCandidate[] (memory)
    ↓ (select per platform)
ClipPlan[] (memory)
    ↓ (edit per variant)
Clip[] (DB + files)
    ↓ (caption per platform)
Caption[] (DB)
    ↓ (package metadata)
PublishPackage[] (memory)
    ↓ (QA gates)
QAReport (DB)
    ↓ (export ready)
ReadyClip[] → PUBLISH QUEUE
```

---

## 3.4 Error Handling & Recovery

| Stage | Retry Policy | Fallback | Human Escalation |
|-------|--------------|----------|------------------|
| Download | 3x exponential backoff | Alternate source URL | MANUAL_CHECKPOINT |
| Transcribe | 2x (smaller model) | Skip transcription (use time-based segments) | MANUAL_CHECKPOINT |
| Segment | 1x (heuristic fallback) | Fixed 15s/30s/60s windows | N/A (always produces output) |
| Edit | 2x (simpler filters) | Skip variant | MANUAL_CHECKPOINT |
| Caption | 1x (template only) | Minimal caption (disclosure only) | CAPTION_REVIEW gate |
| QA | N/A (deterministic) | N/A | QA_FAILED → clip rejected |

---

## 3.5 Cost Model (All Local/FREE)

| Component | Tool | Cost |
|-----------|------|------|
| Download | yt-dlp | FREE |
| Transcribe | faster-whisper (CPU/GPU) | FREE |
| Segment/Score | Python (local) | FREE |
| Edit | FFmpeg | FREE |
| Caption | Python (local) | FREE |
| QA | FFmpeg + Python | FREE |
| Storage | Local disk | FREE |

**No paid APIs required for content pipeline.**

---

## 3.6 Parallelization

- **Per-campaign:** Sequential (state machine)
- **Per-clip:** Parallel variants (TikTok, IG, YT, X)
- **Per-source:** Multiple clip candidates in parallel

**Concurrency limit:** Configurable (default: 2 concurrent edits to manage GPU/CPU)

---

*End of Phase 3. Next: Phase 4 — Compliance Engine.*