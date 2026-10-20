# Content Rewards Workflow

## Overview
Automate operational work around legitimate content campaigns while preserving platform rules and human review. This workflow handles the full lifecycle of content reward campaigns from discovery to earnings tracking.

## Campaign Discovery
- Scan for campaign opportunities from supported sources
- Extract requirements from URLs, HTML, PDFs, or manual paste
- Parse campaign structure with field confidence scores

## Requirements Extraction
- Input: URL, HTML, PDF, or manual paste
- Output: Structured requirements with confidence per field
- Unknown fields are explicitly tracked

## Clip Pipeline
1. Source download (yt-dlp, FFmpeg)
2. Hash and inspect media
3. Transcribe audio (faster-whisper / Whisper)
4. Segment and rank candidate windows
5. Crop to 9:16 aspect ratio
6. Add captions and overlays
7. Loudness check and render
8. Visual QC and export

## Quality Checks (Automatic)
- Resolution, aspect ratio, codec, duration
- Audio presence, silent section detection
- Black-frame detection, file integrity
- Watermark detection where feasible

## Publishing
- Official platform APIs only (TikTok, YouTube, Instagram, Facebook, X)
- Each adapter exposes: publish(), get_status(), get_metrics()
- Never automate through undocumented endpoints

## Human Gates (Required by Default)
- Campaign acceptance
- Rights approval
- Final clip approval
- Publish approval
- Submission approval

## Compliance (Blocked)
- Fake views, likes, followers, comments
- Engagement manipulation
- Copyright-unapproved content
- Spam bursts

## Cost
- $0 hard cap - all processing local
- Local models via Ollama
- Free tools: yt-dlp, FFmpeg, OpenCV, Pillow
- No paid APIs or hosting

## State Persistence
- SQLite database for campaigns, clips, earnings
- Artifact hashes (SHA-256) for deduplication
- Audit log for all state transitions

## Testing
- Unit tests: parsers, scorers, state transitions, retry policy, idempotency
- Integration tests: DB, n8n webhook, Python worker, artifact pipeline
- Failure tests: network down, 429, file missing, DB locked, worker crash