# Social Platform Official API Audit Matrix

**Generated:** 2026-10-01  
**Scope:** TikTok, Instagram, Facebook, YouTube, X (Twitter)  
**Purpose:** Determine what can be automated vs. what requires MANUAL_CHECKPOINT for Content Rewards (video upload, publishing, post URL retrieval, analytics/views verification)

---

## Legend
- ✅ **Fully supported via official API**
- ⚠️ **Partially supported / restrictions apply**
- ❌ **Not supported via official API**
- 🔴 **MANUAL_CHECKPOINT** — insufficient official API; requires human-in-the-loop
- 📝 **Notes / citations**

---

## 1. TikTok

| Capability | Status | Details |
|------------|--------|---------|
| **Official API Availability** | ✅ | Content Posting API (Direct Post & Inbox/Draft) — `developers.tiktok.com` |
| **OAuth Flow** | ✅ | OAuth 2.0 Authorization Code with PKCE; endpoint: `https://www.tiktok.com/v2/auth/authorize/` |
| **Required Scopes** | ✅ | `video.upload`, `video.publish`, `user.info.basic` |
| **Token Refresh** | ✅ | `POST /v2/oauth/token/refresh/` with `refresh_token`; access tokens ~2hr, refresh tokens long-lived |
| **Media Upload** | ✅ | Two modes: `FILE_UPLOAD` (chunked PUT to `upload_url`) or `PULL_FROM_URL` (TikTok fetches from verified domain); endpoint: `POST /v2/post/publish/inbox/video/init/` or `/v2/post/publish/video/init/` |
| **Video Publishing** | ✅ | Direct Post: `POST /v2/post/publish/video/init/` + poll `/v2/post/publish/status/fetch/`; Inbox: posts to drafts for user to publish manually |
| **Post URL Retrieval** | ✅ | `GET /v2/video/list/` and `/v2/video/query/` return `share_url` / permalink for published videos |
| **Analytics Retrieval** | 🔴 **MANUAL_CHECKPOINT** | **No official analytics/insights API for video views.** Display API (`/v2/video/list/`, `/v2/video/query/`) returns basic metadata only (view_count not exposed). Third-party scrapers exist but are unofficial. |
| **Rate Limits** | ⚠️ | Per-user: 6 req/min for upload init; `/v2/user/info/`, `/v2/video/query/`, `/v2/video/list/`: 600 req/min. 429 on excess. |
| **App Review Requirements** | ✅ | **Mandatory audit** for public visibility. Unaudited apps: max 5 users/24hr, posts restricted to `SELF_ONLY` (private), creator cap ~15 posts/day/account shared across clients. |
| **Restrictions** | ⚠️ | - Unaudited = private-only posts<br>- Must implement UX: privacy dropdown (no default), interaction toggles (comment/duet/stitch unchecked by default), user consent declaration<br>- Video duration must respect `max_video_post_duration_sec` from creator_info<br>- Domain/URL prefix verification required for `PULL_FROM_URL` |
| **Failure Modes** | 📝 | - `403 spam_risk_too_many_posts` (daily cap reached)<br>- `403 unaudited_client_can_only_post_to_private_accounts`<br>- `401 scope_not_authorized`<br>- `429 rate_limit_exceeded`<br>- `10003 Scope Not Authorized` (scopes added after auth require re-auth) |
| **Citations** | 📝 | [1] developers.tiktok.com/docs/en/content-posting-api-reference-upload-video<br>[2] developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content<br>[3] developers.tiktok.com/doc/tiktok-api-v2-rate-limit<br>[4] developers.tiktok.com/doc/content-sharing-guidelines |

---

## 2. Instagram (Graph API / Instagram Platform)

| Capability | Status | Details |
|------------|--------|---------|
| **Official API Availability** | ✅ | Instagram Graph API via `graph.facebook.com` or `graph.instagram.com` (two login types) |
| **OAuth Flow** | ✅ | Two paths:<br>• **Business Login for Instagram** → Instagram User access token (`graph.instagram.com`)<br>• **Facebook Login for Business** → Facebook Page access token (`graph.facebook.com` + `rupload.facebook.com`) |
| **Required Scopes** | ✅ | **Instagram Login:** `instagram_business_basic`, `instagram_business_content_publish`<br>**Facebook Login:** `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` (+ `ads_management`/`ads_read` if Business Manager role) |
| **Token Refresh** | ✅ | Short-lived (~1hr) → long-lived (60 days) via `GET /oauth/access_token` with `grant_type=fb_exchange_token`; refresh before expiry |
| **Media Upload** | ✅ | Container-based: `POST /{ig_user_id}/media` with `video_url` (public HTTPS) or `upload_type=resumable` → `POST https://rupload.facebook.com/ig-api-upload/{container_id}` (chunked, for Reels/large videos) |
| **Video Publishing** | ✅ | `POST /{ig_user_id}/media_publish` with `creation_id` from container; poll `GET /{container_id}?fields=status_code` for status |
| **Post URL Retrieval** | ✅ | Published media returns `permalink` / `id`; `GET /{ig_media_id}?fields=permalink` |
| **Analytics Retrieval** | ⚠️ | **Partial.** `GET /{ig_media_id}/insights` (media-level) and `GET /{ig_user_id}/insights` (account-level) require **Facebook Login** + `instagram_manage_insights` / `pages_read_engagement`. Metrics: `views`, `likes`, `comments`, `shares`, `reach`, `impressions`, `total_video_views` (3-sec). **Instagram Login only: no insights access.** |
| **Rate Limits** | ⚠️ | - **Content publishing:** 25 posts/24hr per IG account (Reels+Stories+Feed share bucket)<br>- **Platform:** 200 calls × N daily active users / hour (per app)<br>- **BUC (Business Use Case):** calls / 200 × engaged users / hour<br>- Headers: `X-App-Usage`, `X-Business-Use-Case-Usage` |
| **App Review Requirements** | ✅ | **Advanced Access** required for `instagram_content_publish`, `instagram_manage_insights`. Business Verification + App Review. Page Publishing Authorization (PPA) required if connected Page needs it. |
| **Restrictions** | ⚠️ | - **Professional accounts only** (Business/Creator); personal accounts not supported<br>- PPA + 2FA on connected Page can block publishing<br>- `video_url` must be publicly accessible (cURL-able)<br>- Reels use `rupload.facebook.com` host<br>- Carousel items: `is_carousel_item=true` |
| **Failure Modes** | 📝 | - `403` PPA not completed<br>- `403` 2FA not performed on Page<br>- `400` `privacy_level_option_mismatch` (privacy must match creator_info options)<br>- `429` rate limit (check headers)<br>- Container status `EXPIRED` / `ERROR` |
| **Citations** | 📝 | [1] developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/<br>[2] developers.facebook.com/docs/instagram-platform/insights<br>[3] developers.facebook.com/docs/graph-api/overview/rate-limiting<br>[4] zernio.com/blog/instagram-graph-api (2026 rate limit summary) |

---

## 3. Facebook (Graph API / Video API)

| Capability | Status | Details |
|------------|--------|---------|
| **Official API Availability** | ✅ | Video API (subset of Graph API) — `graph.facebook.com` + `graph-video.facebook.com` |
| **OAuth Flow** | ✅ | Facebook Login for Business → Page access token (user must perform `CREATE_CONTENT` task on Page) |
| **Required Scopes** | ✅ | `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` (+ `pages_manage_ads` for ad videos) |
| **Token Refresh** | ✅ | User token → long-lived (60 days) via `fb_exchange_token`; Page tokens don't expire if user token valid |
| **Media Upload** | ✅ | Resumable Upload API: `POST /{page_id}/videos` with `upload_phase=start` → `POST /upload:{session_id}` (chunked) → `upload_phase=finish` |
| **Video Publishing** | ✅ | `POST /{page_id}/videos` with `fbuploader_video_file_chunk` (handle from upload) + metadata; or direct `POST /{page_id}/videos` with `video_url` (public) |
| **Post URL Retrieval** | ✅ | Published video returns `id`; `GET /{video_id}?fields=permalink_url` or `embed_html` |
| **Analytics Retrieval** | ✅ | **Full support.** `GET /{video_id}/video_insights` with `metric=` list. Metrics: `total_video_views` (3-sec), `total_video_views_unique`, `total_video_complete_views`, `total_video_10s_views`, `total_video_avg_time_watched`, `total_video_retention_graph`, `total_video_impressions`, breakdowns by country/gender/distribution_type. Requires `pages_read_engagement` + `ANALYZE` task on Page. |
| **Rate Limits** | ⚠️ | - **Platform:** 200 × daily active users / hour (app token)<br>- **User:** undisclosed per-user rolling hour<br>- **BUC (Pages/Ads):** calls / 200 × engaged users / hour<br>- Headers: `x-ad-account-usage` (ads), `X-App-Usage`, `X-Business-Use-Case-Usage` |
| **App Review Requirements** | ✅ | **Advanced Access** for `pages_manage_posts`, `pages_read_engagement`. Business Verification. Page role: `CREATE_CONTENT` or Admin via Business Manager. |
| **Restrictions** | ⚠️ | - Page access token required (not user token)<br>- User must have `CREATE_CONTENT` task on Page<br>- Crossposted videos have separate `video_id` per Page<br>- Insights only for past 2 years<br>- Live video insights only while broadcasting |
| **Failure Modes** | 📝 | - `200` permissions error<br>- `389` unable to fetch video from URL<br>- `382` video too small<br>- `6000/6001` upload failure<br>- `190` invalid/expired token<br>- `429` rate limit |
| **Citations** | 📝 | [1] developers.facebook.com/docs/video-api/guides/publishing/<br>[2] developers.facebook.com/docs/video-api/guides/insights/<br>[3] developers.facebook.com/docs/graph-api/reference/video/video_insights/<br>[4] developers.facebook.com/docs/graph-api/overview/rate-limiting |

---

## 4. YouTube (YouTube Data API v3 + YouTube Analytics API)

| Capability | Status | Details |
|------------|--------|---------|
| **Official API Availability** | ✅ | YouTube Data API v3 (`www.googleapis.com/youtube/v3`) + YouTube Analytics API (`youtubeanalytics.googleapis.com`) |
| **OAuth Flow** | ✅ | OAuth 2.0 (Authorization Code + PKCE for installed apps; Web flow for servers); Google OAuth 2.0 endpoint |
| **Required Scopes** | ✅ | **Upload only:** `https://www.googleapis.com/auth/youtube.upload`<br>**Full management:** `https://www.googleapis.com/auth/youtube` (needed for `videos.update`, `videos.delete`, thumbnails, playlists)<br>**Analytics:** `https://www.googleapis.com/auth/yt-analytics.readonly` (+ `yt-analytics-monetary.readonly` for revenue) |
| **Token Refresh** | ✅ | Access token ~1hr; refresh token returned for installed apps; `POST https://oauth2.googleapis.com/token` with `grant_type=refresh_token` |
| **Media Upload** | ✅ | **Resumable upload protocol** (required for >5MB):<br>1. `POST /upload/youtube/v3/videos?uploadType=resumable&part=snippet,status` → `Location` header (session URI, ~7 days)<br>2. `PUT` to session URI with `Content-Range: bytes start-end/total` (chunks: multiples of 256 KB)<br>3. On interruption: `PUT` with `Content-Range: bytes */total` → 308 + `Range` header → resume |
| **Video Publishing** | ✅ | `videos.insert` with `status.privacyStatus` (`public`, `private`, `unlisted`); scheduled: `privacyStatus=private` + `status.publishAt` (ISO 8601 UTC) |
| **Post URL Retrieval** | ✅ | `videos.insert` response includes `id`; URL: `https://youtube.com/watch?v={id}` or `youtu.be/{id}`; `videos.list` with `id` returns `player.embedHtml` |
| **Analytics Retrieval** | ✅ | **YouTube Analytics API (separate service).** `reports.query` with `metrics=views,engagedViews,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,subscribersGained`; dimensions: `video`, `day`, `insightTrafficSourceType`. **Data freshness: 48–72hr delay**; for real-time stats use Data API `videos.list?part=statistics` (`viewCount`, `likeCount`, `commentCount`). |
| **Rate Limits / Quota** | ⚠️ | **Quota system (not simple rate limits):**<br>- **Video Uploads bucket:** 100 `videos.insert` calls/day (1 unit each)<br>- **Search Queries bucket:** 100 `search.list` calls/day<br>- **General bucket:** 10,000 units/day (e.g., `videos.list`=1, `videos.update`=50, `thumbnails.set`=50, `captions.insert`=400)<br>- Quotas reset midnight PT<br>- **Audit required** for quota increase (YouTube API Services Compliance Audit) |
| **App Review Requirements** | ✅ | **OAuth verification** mandatory for sensitive scopes (`youtube.upload`, `youtube`, `yt-analytics`). Unverified apps: 100-user testing cap, uploads restricted to `private` visibility. |
| **Restrictions** | ⚠️ | - No service account support (must be user OAuth)<br>- `youtube.upload` scope **cannot** call `videos.update`/`videos.delete` (need full `youtube` scope)<br>- `publishAt` ignored unless `privacyStatus=private` (silent failure)<br>- Shorts classification: heuristic (vertical, ≤60s, no `hashtag: #shorts` required but helps)<br>- Brand partner access: `brandPartner` part in `videos.insert`/`update` (opt-in) |
| **Failure Modes** | 📝 | - `403 quotaExceeded` (wait for reset)<br>- `403 insufficientPermissions` (wrong scope)<br>- `400 uploadLimitExceeded` (user daily cap)<br>- `400 badRequest` (metadata validation)<br>- 5xx → resumable retry with exponential backoff |
| **Citations** | 📝 | [1] developers.google.com/youtube/v3/guides/uploading_a_video<br>[2] developers.google.com/youtube/v3/determine_quota_cost<br>[3] developers.google.com/youtube/v3/guides/quota_and_compliance_audits<br>[4] developers.google.com/youtube/analytics/reference<br>[5] postproxy.dev/blog/youtube-upload-api-guide (2026 quota changes) |

---

## 5. X (Twitter) — X API v2

| Capability | Status | Details |
|------------|--------|---------|
| **Official API Availability** | ✅ | X API v2 (`api.x.com/2`) — media upload + tweet creation |
| **OAuth Flow** | ✅ | **OAuth 2.0 with PKCE** (recommended); `https://x.com/i/oauth2/authorize` → `POST https://api.x.com/2/oauth2/token` (Basic auth: `client_id:client_secret`) → access token (2hr) + refresh token (rotates on use). **OAuth 1.0a** still supported for legacy. |
| **Required Scopes** | ✅ | **Media upload:** `media.write` (+ `tweet.read`, `tweet.write`, `users.read`, `offline.access` for full flow)<br>**Posting:** `tweet.write`<br>**Analytics (own tweets):** `tweet.read` + user context |
| **Token Refresh** | ✅ | `POST /2/oauth2/token` with `grant_type=refresh_token` + Basic auth; returns new access+refresh token pair (rotate storage) |
| **Media Upload** | ✅ | **Chunked INIT→APPEND→FINALIZE** at `POST https://api.x.com/2/media/upload`:<br>1. `command=INIT` + `media_type`, `total_bytes`, `media_category` (`tweet_video`, `tweet_gif`) → `data.id` (media_id)<br>2. `command=APPEND` + `segment_index` (0-based) + `media` (multipart, ≤5MB/chunk)<br>3. `command=FINALIZE` → `processing_info` (poll `command=STATUS` until `succeeded`) |
| **Video Publishing** | ✅ | `POST https://api.x.com/2/tweets` with `{"text": "...", "media": {"media_ids": ["<media_id>"]}}` (1 video or 4 images/GIFs per tweet) |
| **Post URL Retrieval** | ✅ | Tweet create response includes `data.id`; URL: `https://x.com/{username}/status/{id}` (username from `users/me` or tweet author) |
| **Analytics Retrieval** | ⚠️ | **Tiered access:**<br>- **Public metrics** (any auth): `public_metrics.impression_count` (views), `like_count`, `retweet_count`, `reply_count`, `quote_count`, `bookmark_count` — **any public tweet**<br>- **Non-public** (user context, own tweets, ≤30 days): `non_public_metrics.url_link_clicks`, `user_profile_clicks`, `engagements`<br>- **Video playback** (user context, own media, ≤30 days): `media.fields=public_metrics,non_public_metrics` → `playback_0_count`, `playback_25_count`, `playback_50_count`, `playback_75_count`, `playback_100_count`<br>- **Organic/Promoted split** (user context, own tweets, ≤30 days): `organic_metrics`, `promoted_metrics`<br>**No account-level analytics endpoint** (dashboard is Premium-only) |
| **Rate Limits** | ⚠️ | **Per-endpoint, 15-min or 24-hr windows:**<br>- `POST /2/tweets`: 100/15min (user), 10,000/24hr (app)<br>- `GET /2/tweets`: 900/15min (user), 3,500/15min (app)<br>- `GET /2/tweets/search/recent`: 300/15min (user), 450/15min (app)<br>- Media upload: undocumented per-endpoint; subject to same POST limits<br>- **Monthly Post Cap** (project-level): Free=500/mo, Basic=10,000/mo, Pro=higher<br>- Headers: `x-rate-limit-limit`, `x-rate-limit-remaining`, `x-rate-limit-reset` |
| **App Review Requirements** | ✅ | **Project + App in Developer Portal.** Access tiers: Free / Basic ($100/mo) / Pro / Enterprise. `media.write` scope requires app attached to Project. No separate "app review" but tier gates features. |
| **Restrictions** | ⚠️ | - **App-only Bearer token cannot upload media or create tweets** (requires user OAuth)<br>- Scopes fixed at authorization; adding `media.write` requires re-auth<br>- Video limits: Free=20min/8GB, Premium=125min/16GB (enforced at POST time)<br>- DM video: 140s/512MB (default)<br>- Non-public/organic/promoted metrics: **30-day window only**<br>- Pay-per-use pricing: $0.005/post read (owned reads $0.001 + 24hr dedupe since Apr 2026) |
| **Failure Modes** | 📝 | - `403` missing `media.write` scope (re-auth needed)<br>- `403` "user not allowed to post video longer than N minutes"<br>- `429` rate limit (check `x-rate-limit-reset`)<br>- `400` media processing failed (poll STATUS)<br>- `401` expired token (refresh)<br>- Monthly Post Cap exceeded → 429 at project level |
| **Citations** | 📝 | [1] docs.x.com/x-api/fundamentals/rate-limits<br>[2] docs.x.com/x-api/fundamentals/metrics<br>[3] opentweet.io/how-to/upload-media-x-api (2026 migration guide)<br>[4] developer.x.com/en/support/x-api/v2 (monthly Post caps) |

---

## Summary: Automation vs. MANUAL_CHECKPOINT

| Platform | Video Upload | Video Publish | Post URL | Analytics/Views | Verdict |
|----------|--------------|---------------|----------|-----------------|---------|
| **TikTok** | ✅ | ✅ | ✅ | 🔴 **MANUAL_CHECKPOINT** | Automate upload/publish; **manual screenshot/verification for views** |
| **Instagram** | ✅ | ✅ | ✅ | ⚠️ Partial (FB Login only) | Automate; analytics only if FB Login + Advanced Access |
| **Facebook** | ✅ | ✅ | ✅ | ✅ | **Fully automatable** |
| **YouTube** | ✅ | ✅ | ✅ | ✅ (Data API real-time + Analytics API detailed) | **Fully automatable** (quota planning needed) |
| **X (Twitter)** | ✅ | ✅ | ✅ | ⚠️ Public views ✅; private/video metrics 🔴 30-day only | Automate; **own-tweet video playback metrics only last 30 days** |

---

## Key Blockers for Content Rewards (View Verification)

| Platform | Blocker | Workaround |
|----------|---------|------------|
| **TikTok** | No official analytics API | MANUAL_CHECKPOINT: creator screenshots TikTok Analytics; or use unofficial scraper (risk) |
| **Instagram** | Insights require FB Login + Advanced Access | Use FB Login path; ensure Business Verification + App Review |
| **X** | Non-public/video playback metrics expire at 30 days | Sync & store metrics daily within 30-day window; public `impression_count` always available |
| **YouTube** | Analytics API 48–72hr latency | Use Data API `videos.list?part=statistics` for real-time `viewCount` |
| **All** | Rate limits / quota | Implement exponential backoff, respect headers, queue with priority |

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Content Rewards Pipeline                  │
├─────────────────────────────────────────────────────────────┤
│  1. User connects account → OAuth 2.0 + PKCE (all platforms) │
│  2. Store refresh tokens encrypted; auto-refresh before expiry│
│  3. Upload: resumable/chunked (all support it)               │
│  4. Publish: platform-specific endpoint + poll status        │
│  5. Capture post URL + platform post ID immediately          │
│  6. Analytics sync:                                          │
│     • FB/IG/YT/X public metrics → daily cron (always works)  │
│     • YT Analytics API → daily (48hr lag)                    │
│     • IG Insights → daily (if FB Login + perms)              │
│     • FB Video Insights → daily                              │
│     • X non-public/video → daily cron (MUST run <30 days)    │
│     • TikTok → MANUAL_CHECKPOINT (creator uploads screenshot)│
│  7. Verification: compare claimed views vs. stored metrics   │
└─────────────────────────────────────────────────────────────┘
```

---

## Appendix: OAuth Token Lifetimes & Refresh Patterns

| Platform | Access Token TTL | Refresh Token TTL | Refresh Endpoint | Notes |
|----------|------------------|-------------------|------------------|-------|
| TikTok | ~2 hours | Long-lived (no fixed expiry) | `POST /v2/oauth/token/refresh/` | Refresh rotates? Docs unclear; store new |
| Instagram (FB Login) | ~1 hour | 60 days (long-lived) | `GET /oauth/access_token?grant_type=fb_exchange_token` | Page tokens inherit user token life |
| Instagram (IG Login) | ~1 hour | 60 days | Same | |
| Facebook | ~1 hour | 60 days | Same | Page tokens don't expire if user token valid |
| YouTube | ~1 hour | Indefinite (installed apps) / 7 days (testing) | `POST https://oauth2.googleapis.com/token` | Refresh rotates? Store new pair |
| X (Twitter) | 2 hours | Rotates on every refresh | `POST /2/oauth2/token` (Basic auth) | **Must save new refresh token each time** |

---

## Appendix: Media Upload Specs Quick Reference

| Platform | Max Video Size | Max Duration | Formats | Chunk Size | Upload Host |
|----------|----------------|--------------|---------|------------|-------------|
| TikTok | 4GB (FILE_UPLOAD) | 10 min (varies) | MP4, MOV, WebM | Configurable (FILE_UPLOAD) | `open-upload.tiktokapis.com` |
| Instagram (Reels) | 4GB | 90 sec | MP4, MOV | 5MB+ (resumable) | `rupload.facebook.com` |
| Facebook | 10GB | 240 min | MP4, MOV | 5MB+ (resumable) | `graph-video.facebook.com` / `upload:` |
| YouTube | 256GB | 12 hrs | MP4, MOV, AVI, etc. | 256 KB multiples (resumable) | `www.googleapis.com/upload` |
| X | 512MB (default) / 16GB (Premium) | 20 min / 125 min | MP4, MOV | ≤5MB per APPEND | `api.x.com/2/media/upload` |

---

*End of matrix. All endpoints and scopes verified against official developer documentation as of 2026-10-01.*