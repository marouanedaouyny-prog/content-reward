# Campaign Model — Content Rewards Automation System

**Based on:** `research/content_rewards.md` (official Terms Sep 24, 2026)

---

## 1.1 Campaign Types

| Field | CPM | Per-post | Retainer |
|-------|-----|----------|----------|
| **Mechanics** | Paid per 1,000 verified views | Flat amount per approved clip | Cycle-based subscription |
| **Min Budget** | $1,000 | $1,000 | $1,000 |
| **Per-clip Min/Max** | Brand sets both | Min-view requirement optional | Per-cycle deliverable amount |
| **View Accrual** | Continues post-approval while funded | Stops at approval | N/A (work-for-hire) |
| **Payout Timing** | ~10 days after approval (7d earn + 3d hold) | Shortly after approval | After each Cycle ends |
| **Budget Draw** | Incremental (verified views) | Reserved at approval | Per-cycle |

---

## 1.2 Campaign Structured Object

```json
{
  "campaign_id": "string (UUID)",
  "external_campaign_id": "string (CR platform ID)",
  "campaign_type": "CPM|PER_POST|RETAINER",
  "title": "string",
  "description": "string",
  "brand_id": "string",
  "brand_name": "string",
  "status": "DISCOVERED|ANALYZED|ELIGIBLE|ACTIVE|CLOSED|EXHAUSTED",
  "platforms": ["TIKTOK", "INSTAGRAM", "YOUTUBE", "X", "FACEBOOK"],
  "required_tags": ["string"],
  "required_mentions": ["string"],
  "required_disclosure": "string (FTC template)",
  "source_content": [
    {
      "type": "VIDEO_URL|ASSET_LIBRARY",
      "url": "string",
      "usage_rights": "string"
    }
  ],
  "editing_rules": [
    {
      "rule_type": "DURATION|ASPECT_RATIO|BRANDING|AUDIO|CUTS",
      "spec": "object",
      "mandatory": true
    }
  ],
  "min_views": "integer|null",
  "max_payout_per_clip": "number|null",
  "budget_total": "number",
  "budget_remaining": "number",
  "budget_reserved": "number",
  "rate_cpm": "number|null",
  "rate_per_post": "number|null",
  "rate_retainer_cycle": "number|null",
  "pre_post_review_enabled": false,
  "submission_method": "URL|DRAFT_THEN_URL",
  "co_posting_allowed": false,
  "repost_limit": 5,
  "deadline": "ISO8601|null",
  "discovered_at": "ISO8601",
  "analyzed_at": "ISO8601|null",
  "eligible_at": "ISO8601|null",
  "closed_at": "ISO8601|null"
}
```

---

## 1.3 Input/Action/Deliverable per Type

### CPM
| Phase | Input | Creator Action | Deliverable | Publish Requirement | Submit Requirement | Approval State | Analytics | Payout Calculation | Validation Period | Failure Conditions |
|-------|-------|----------------|-------------|---------------------|-------------------|----------------|-----------|-------------------|-------------------|-------------------|
| **Post** | Campaign brief, source assets | Create clip per rules, post on required platform(s) | Public clip URL | Must be on campaign-specified platform(s); public account | Submit public URL (or Draft if Pre-post Review) | BOT_SCORE_TRIAGE → BRAND_REVIEW → APPROVED/REJECTED | CR fetches views via platform APIs (read-only OAuth) | `floor(verified_views / 1000) * rate_cpm`, clamped to [min, max] per clip | 7-day earn window + 3-day hold (~10 days) | Views < min, fraud flag, brand rejection, campaign budget exhausted |

### Per-post
| Phase | Input | Creator Action | Deliverable | Publish Requirement | Submit Requirement | Approval State | Analytics | Payout Calculation | Validation Period | Failure Conditions |
|-------|-------|----------------|-------------|---------------------|-------------------|----------------|-----------|-------------------|-------------------|-------------------|
| **Post** | Campaign brief, source assets | Create clip per rules, post on required platform(s) | Public clip URL | Must be on campaign-specified platform(s); public account | Submit public URL (or Draft if Pre-post Review) | BOT_SCORE_TRIAGE → BRAND_REVIEW → APPROVED/REJECTED | CR fetches views; min-view check in monitoring period | `rate_per_post` (flat), reserved at approval | Shortly after approval | Min views not met in monitoring period (payout returns to budget), fraud flag, brand rejection |

### Retainer
| Phase | Input | Creator Action | Deliverable | Publish Requirement | Submit Requirement | Approval State | Analytics | Payout Calculation | Validation Period | Failure Conditions |
|-------|-------|----------------|-------------|---------------------|-------------------|----------------|-----------|-------------------|-------------------|-------------------|
| **Cycle** | Campaign brief, cycle spec, source assets | Produce deliverables per cycle spec (work-for-hire) | Clip(s) per cycle | Per campaign spec | Submit URL(s) per cycle | BOT_SCORE_TRIAGE → BRAND_REVIEW → APPROVED/REJECTED | Per-cycle reporting | `rate_retainer_cycle` per completed cycle | After each Cycle ends | Deliverables not met, fraud flag, brand rejection |

---

## 1.4 Common Fields for All Submissions

```json
{
  "submission_id": "string (UUID)",
  "campaign_id": "string",
  "creator_id": "string",
  "platform": "TIKTOK|INSTAGRAM|YOUTUBE|X|FACEBOOK",
  "social_account_id": "string (linked account UUID)",
  "clip_url": "string (public permalink)",
  "clip_id_platform": "string (platform post ID)",
  "draft_url": "string|null (if Pre-post Review)",
  "draft_id_platform": "string|null",
  "status": "DRAFT|SUBMITTED|BOT_TRIAGE|BRAND_REVIEW|APPROVED|REJECTED|FLAGGED|VALIDATING|PAID|CLAWBACK",
  "bot_score": "integer 0-100|null",
  "bot_score_flagged": "boolean",
  "brand_reviewer_id": "string|null",
  "approved_at": "ISO8601|null",
  "rejected_at": "ISO8601|null",
  "rejection_reason": "string|null",
  "validation_start": "ISO8601|null",
  "validation_end": "ISO8601|null",
  "verified_views": "integer",
  "expected_payout": "number",
  "payout_status": "PENDING|RESERVED|SETTLED|CLAWBACK",
  "payout_amount": "number",
  "payout_settled_at": "ISO8601|null",
  "submitted_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

---

## 1.5 State Transitions (Submission)

```text
DRAFT (if pre-post review)
    ↓
SUBMITTED
    ↓
BOT_TRIAGE (auto)
    ├── score < threshold → BRAND_REVIEW
    └── score ≥ threshold → FLAGGED → human review → BRAND_REVIEW or REJECTED
            ↓
    BRAND_REVIEW (moderator)
    ├── APPROVED → VALIDATING
    └── REJECTED → terminal
            ↓
    VALIDATING (CR verifies views)
    ├── PAID (settled to Platform balance)
    └── FRAUD_FLAGGED → REJECTED/CLAWBACK
```

---

## 1.6 Failure States & Recovery

| Failure State | Trigger | Recovery Action | Idempotency Key |
|---------------|---------|-----------------|-----------------|
| **UPLOAD_FAILED** | Platform API error | Retry with exponential backoff (max 3) | `clip_id:upload:{attempt}` |
| **PUBLISH_FAILED** | Platform API error / PPA missing / 2FA | Alert human; retry after fix | `clip_id:publish:{attempt}` |
| **SUBMISSION_FAILED** | CR platform error | Retry; if persistent → MANUAL_CHECKPOINT | `submission_id:{attempt}` |
| **BOT_FLAGGED** | Score ≥ threshold | Auto-pause; human appeal (10 biz days) | N/A (state-based) |
| **REJECTED** | Brand rejection | Log reason; no auto-retry (human decision) | N/A |
| **VALIDATION_FAILED** | Views < min / fraud upheld | Reverse reserved budget; notify | N/A |
| **TOKEN_EXPIRED** | OAuth refresh failed | Alert human to re-auth; pause submissions | `account_id:token_refresh` |
| **CAMPAIGN_CLOSED** | Budget exhausted / deadline | Stop new submissions; finish in-flight | N/A |
| **FRAUD_FLAGGED** | Bot Score upheld | Permanent ban risk; escalate human | N/A |

---

## 1.7 Idempotency Keys (Critical)

Every external action must use a deterministic idempotency key:

| Action | Key Format | Stored Where |
|--------|------------|--------------|
| Upload media | `upload:{clip_hash}:{platform}` | DB `jobs` |
| Publish | `publish:{clip_id}:{platform}:{account_id}` | DB `jobs` |
| Submit URL | `submit:{campaign_id}:{creator_id}:{clip_url_hash}` | DB `submissions` |
| Analytics sync | `analytics:{submission_id}:{platform}:{date}` | DB `analytics_snapshots` |
| Payout check | `payout:{submission_id}:{validation_window_end}` | DB `payouts` |

**Rule:** Restarting Hermes must NOT duplicate posts, submissions, or payouts. All keys persisted in DB with unique constraints.

---

*End of Phase 1. Next: Phase 3 — Content Pipeline Architecture.*