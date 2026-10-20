# Cost Plan & Dependency Classification

**Based on:** All previous phases. Target: $0 marginal cost for automation layer.

---

## 10.1 Dependency Classification

| Dependency | Category | Cost | Notes |
|------------|----------|------|-------|
| **Hermes Agent** | Core | FREE | Open source (Nous Research) |
| **Python 3.11+** | Runtime | FREE | Standard library |
| **SQLite** | Database | FREE | Embedded |
| **FFmpeg** | Video processing | FREE | Binary, local |
| **faster-whisper** | Transcription | FREE | Local ML (CPU/GPU) |
| **yt-dlp** | Video download | FREE | CLI, local |
| **OpenCV** | Scene detection | FREE | Python package |
| **Pillow** | Image processing | FREE | Python package |
| **httpx** | HTTP client | FREE | Python package |
| **pydantic** | Validation | FREE | Python package |
| **sqlmodel/SQLAlchemy** | ORM | FREE | Python package |
| **cryptography** | Token encryption | FREE | Python package |
| **APScheduler** | Cron | FREE | Python package |
| **Playwright** | Browser automation | FREE | Python package |
| **TikTok API** | Platform | FREE WITH LIMITS | Unaudited: 5 users/24hr, private only; Audited: requires review |
| **Instagram Graph API** | Platform | FREE WITH LIMITS | Requires Business Verification + App Review for Advanced Access |
| **Facebook Graph API** | Platform | FREE WITH LIMITS | Requires Business Verification + App Review |
| **YouTube Data API v3** | Platform | FREE WITH LIMITS | 10,000 quota units/day; upload bucket 100/day; audit for increase |
| **YouTube Analytics API** | Platform | FREE WITH LIMITS | Separate quota; 48-72hr latency |
| **X API v2** | Platform | FREE WITH LIMITS | Free tier: 500 posts/mo, 20min/8GB video; Basic $100/mo for 10k posts |
| **Whop API** | Payments | FREE | Payment processor (Whop takes % on withdrawals) |
| **Content Rewards Platform** | Business | REVENUE SHARE | CR takes 10% (CPM) or 0-10% (Per-post/Retainer) |
| **NVIDIA API (Nemotron)** | LLM | FREE TIER | `nvidia/nemotron-3-ultra-550b-a55b` free tier available |
| **OpenRouter** | LLM | FREE TIER | Some models free (e.g., `meta-llama/llama-3.1-8b-instruct:free`) |
| **Ollama** | Local LLM | FREE | Local inference (requires GPU RAM) |
| **Groq** | LLM | FREE TIER | Fast inference, generous free tier |

---

## 10.2 Infrastructure Costs (Local-First)

| Resource | Spec | Monthly Cost |
|----------|------|--------------|
| **Compute** | Local machine (CPU + GPU) | $0 (owned) |
| **Storage** | Local SSD (1TB for clips) | $0 (owned) |
| **Network** | Home/office internet | $0 (existing) |
| **GPU** | RTX 3080/4080 for whisper/ffmpeg | $0 (owned) |
| **Backup** | External drive / cloud sync | ~$5-10 (optional) |

**Total infrastructure: $0/month (using existing hardware)**

---

## 10.3 API Costs (Per Campaign Estimates)

### Scenario: 10 clips/campaign, 5 platforms each = 50 publishes

| Platform | API Calls per Clip | Cost |
|----------|-------------------|------|
| **TikTok** | Upload init + publish + status poll (3) + video list (1) | Free (within unaudited limits) |
| **Instagram** | Media container + publish + insights (3) | Free (with Advanced Access) |
| **Facebook** | Video upload + publish + insights (3) | Free |
| **YouTube** | Resumable upload (1) + statistics (1) + Analytics (1) | Free (quota: ~3 units/clip) |
| **X** | Media upload (3 chunks) + tweet create + metrics (2) | Free tier (500 posts/mo) |

**Total API cost: $0** (all within free tiers for moderate volume)

---

## 10.4 LLM Costs (Campaign Analysis, Caption Generation)

| Task | Model | Estimated Tokens | Cost |
|------|-------|------------------|------|
| Campaign parsing | Nemotron 3 Ultra (NVIDIA free) | ~2k input, ~1k output | $0 |
| Clip strategy | Nemotron 3 Ultra | ~3k input, ~2k output | $0 |
| Caption generation | Llama 3.1 8B (OpenRouter free) | ~1k input, ~500 output | $0 |
| Compliance rules | Local (deterministic) | N/A | $0 |

**Total LLM cost: $0** (using free tiers)

---

## 10.5 Revenue Model (Creator Side)

| Campaign Type | CR Fee | Whop Withdrawal | Net to Creator |
|---------------|--------|-----------------|----------------|
| **CPM** | 10% flat | Free to Whop balance | 90% of verified views payout |
| **Per-post <$5k** | 10% | Free | 90% of flat rate |
| **Per-post ≥$5k (Premium)** | 0% | Free | 100% of flat rate |
| **Retainer <$5k** | 10% | Free | 90% of cycle rate |
| **Retainer ≥$5k (Premium)** | 0% | Free | 100% of cycle rate |

**Whop withdrawal:** ~3-5 business days (or instant for Whop fee)

---

## 10.6 Cost per Clip (Automation Layer Only)

| Component | Cost |
|-----------|------|
| Download (yt-dlp) | $0 |
| Transcribe (faster-whisper, 60s video) | $0 (local GPU ~10s) |
| Segment/Score | $0 (local CPU ~1s) |
| Edit (FFmpeg, 5 variants) | $0 (local GPU ~30s) |
| Caption (LLM) | $0 (free tier) |
| QA (14 gates) | $0 (local FFmpeg ~5s) |
| Upload (5 platforms) | $0 (API free tier) |
| Publish (5 platforms) | $0 (API free tier) |
| Submit (browser) | $0 (local) |
| Analytics sync | $0 (API free tier) |
| **Total per clip** | **$0** |

---

## 10.7 Scaling Thresholds (When Costs Appear)

| Threshold | Platform | Action |
|-----------|----------|--------|
| >5 unaudited TikTok users/24hr | TikTok | Submit for audit |
| >100 TikTok posts/day/account | TikTok | Audit required |
| >25 IG posts/24hr/account | Instagram | Rate limit hit |
| >10,000 YouTube quota units/day | YouTube | Request quota increase (audit) |
| >500 posts/mo on X | X | Upgrade to Basic ($100/mo) |
| >5 concurrent FFmpeg jobs | Local | Queue or add GPU |

---

## 10.8 Optional Paid Upgrades (Not Required for MVP)

| Upgrade | Cost | Benefit |
|---------|------|---------|
| **X API Basic** | $100/mo | 10,000 posts/mo, higher video limits |
| **YouTube Quota Increase** | Free (audit) | Higher upload/search limits |
| **TikTok Audit** | Free (review) | Public posts, higher limits |
| **IG/FB Advanced Access** | Free (review) | Insights, publishing |
| **Cloud GPU (RunPod/Vast)** | $0.50-2/hr | Faster transcription/encoding |
| **Managed DB (Neon/Supabase)** | Free tier → $25/mo | PostgreSQL, backups, scaling |

---

## 10.9 Cost Summary

| Category | MVP Cost | Scale Cost |
|----------|----------|------------|
| Infrastructure | $0 | $0-50/mo |
| Platform APIs | $0 | $0-100/mo |
| LLM Inference | $0 | $0 |
| CR Platform Fees | 0-10% of revenue | 0-10% of revenue |
| Whop Withdrawal | Free | Free |
| **Total Automation Overhead** | **$0** | **$0-150/mo** |

**The automation layer itself costs $0 to run. Revenue shares only apply when creators earn.**

---

## 10.10 Budget Allocation (If Scaling)

| Priority | Budget | Use |
|----------|--------|-----|
| 1 | $0 | Local hardware (existing) |
| 2 | $0 | Free API tiers |
| 3 | $50/mo | Cloud GPU for batch processing (optional) |
| 4 | $100/mo | X API Basic (if >500 posts/mo) |
| 5 | $25/mo | Managed PostgreSQL (if multi-user) |

---

*End of Phase 10. Next: Phase 11 — Final System Plan.*