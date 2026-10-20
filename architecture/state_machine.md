# State Machine Architecture

**Based on:** `research/content_rewards.md` (Submission lifecycle, Approval, Validation, Payout)

---

## 5.1 Core States (Campaign)

```text
DISCOVERED
    ↓ (analyze)
ANALYZED
    ↓ (eligibility check)
ELIGIBLE
    ↓ (campaign accepted / assets ready)
ACTIVE
    ↓ (budget exhausted / deadline / closed)
CLOSED
```

**Transitions:**
| From | To | Trigger | Condition |
|------|-----|---------|-----------|
| DISCOVERED | ANALYZED | Campaign parser completes | Requirements extracted |
| ANALYZED | ELIGIBLE | Eligibility check passes | Budget > 0, platforms match, deadline > now |
| ANALYZED | CLOSED | Eligibility fails | Budget exhausted, deadline passed, platforms unsupported |
| ELIGIBLE | ACTIVE | Creator joins / first submission | At least 1 submission |
| ACTIVE | CLOSED | Budget exhausted / deadline | `budget_remaining ≤ 0` OR `now > deadline` |

---

## 5.2 Core States (Submission)

```text
DRAFT (optional, pre-post review)
    ↓
SUBMITTED
    ↓ (auto, immediate)
BOT_TRIAGE
    ├── score < threshold → BRAND_REVIEW
    └── score ≥ threshold → FLAGGED → (human review) → BRAND_REVIEW
            ↓
    BRAND_REVIEW (moderator action)
    ├── APPROVED → VALIDATING
    └── REJECTED → terminal
            ↓
    VALIDATING (CR verifies views)
    ├── PAID (settled)
    ├── CLAWBACK (fraud upheld)
    └── REJECTED (validation failed)
```

**Full State Enum:**
```python
class SubmissionStatus(str, Enum):
    # Pre-submission
    DRAFT = "draft"
    
    # Submission flow
    SUBMITTED = "submitted"
    BOT_TRIAGE = "bot_triage"
    FLAGGED = "flagged"
    BRAND_REVIEW = "brand_review"
    
    # Terminal outcomes
    APPROVED = "approved"
    REJECTED = "rejected"
    
    # Post-approval
    VALIDATING = "validating"
    PAID = "paid"
    CLAWBACK = "clawback"
    
    # Error states
    UPLOAD_FAILED = "upload_failed"
    PUBLISH_FAILED = "publish_failed"
    SUBMISSION_FAILED = "submission_failed"
    TOKEN_EXPIRED = "token_expired"
    CAMPAIGN_CLOSED = "campaign_closed"
    FRAUD_FLAGGED = "fraud_flagged"
```

---

## 5.3 State Definitions

| State | Entry Condition | Exit Condition | Persistence | Retry Policy |
|-------|-----------------|----------------|-------------|--------------|
| **DRAFT** | Pre-post review enabled + creator uploads raw video | Brand approves/rejects draft | `submission.draft_url`, `draft_id_platform` | N/A |
| **SUBMITTED** | Creator submits public URL (or draft approved) | Bot Score computed | `submission.clip_url`, `clip_id_platform`, `submitted_at` | Auto-retry on platform error (3x) |
| **BOT_TRIAGE** | Submission received | Score < threshold → BRAND_REVIEW; Score ≥ threshold → FLAGGED | `bot_score`, `bot_score_flagged` | N/A (CR system) |
| **FLAGGED** | Bot Score ≥ threshold | Human review completes | `flagged_at`, `flag_reason` | Human appeal (10 biz days) |
| **BRAND_REVIEW** | Bot triage passed OR flag resolved | Brand moderator clicks Approve/Reject | `brand_reviewer_id`, `review_started_at` | 7-day auto-approval (legacy) |
| **APPROVED** | Brand clicks Approve | Validation window starts | `approved_at` | N/A |
| **REJECTED** | Brand clicks Reject | Terminal (unless appealed) | `rejected_at`, `rejection_reason` | Creator can appeal to CR Support |
| **VALIDATING** | Approved | Views verified + validation window ends | `validation_start`, `validation_end`, `verified_views` | CR system |
| **PAID** | Validation passed + payout settled | Terminal | `payout_settled_at`, `payout_amount` | N/A |
| **CLAWBACK** | Fraud upheld post-settlement | Terminal | `clawback_at`, `clawback_amount`, `clawback_reason` | N/A |

---

## 5.4 Failure States & Recovery Actions

| Failure State | Trigger | Recovery Action | Max Retries | Idempotency Key |
|---------------|---------|-----------------|-------------|-----------------|
| **UPLOAD_FAILED** | Media upload API error | Exponential backoff retry | 3 | `upload:{clip_hash}:{platform}:{attempt}` |
| **PUBLISH_FAILED** | Publish API error / PPA missing / 2FA | Alert human; retry after fix | 3 | `publish:{clip_id}:{platform}:{account_id}:{attempt}` |
| **SUBMISSION_FAILED** | CR platform submit error | Retry; if persistent → MANUAL_CHECKPOINT | 3 | `submit:{campaign_id}:{creator_id}:{clip_url_hash}:{attempt}` |
| **TOKEN_EXPIRED** | OAuth refresh failed / revoked | Pause submissions; alert human to re-auth | N/A | `token_refresh:{account_id}` |
| **CAMPAIGN_CLOSED** | Budget exhausted / deadline | Stop new submissions; finish in-flight | N/A | N/A |
| **FRAUD_FLAGGED** | Bot Score upheld on appeal | Escalate human; permanent ban risk | N/A | N/A |

---

## 5.5 Persistence Requirements

Every state transition must be recorded:

```sql
-- State history (append-only)
CREATE TABLE submission_state_history (
    id UUID PRIMARY KEY,
    submission_id UUID NOT NULL,
    from_state VARCHAR(50),
    to_state VARCHAR(50) NOT NULL,
    trigger VARCHAR(100),           -- "bot_triage", "brand_approve", "retry", "human_action"
    actor VARCHAR(50),              -- "system", "brand_moderator", "creator", "cr_support"
    metadata JSONB,                 -- scores, reasons, error codes
    created_at TIMESTAMP DEFAULT NOW()
);

-- Current state (denormalized for queries)
CREATE TABLE submissions (
    id UUID PRIMARY KEY,
    campaign_id UUID NOT NULL,
    creator_id UUID NOT NULL,
    status VARCHAR(50) NOT NULL,
    current_state_since TIMESTAMP NOT NULL,
    retry_count INT DEFAULT 0,
    idempotency_key VARCHAR(255) UNIQUE,
    -- ... other fields
);
```

**Idempotency Rules:**
1. Every external action (upload, publish, submit, analytics sync, payout check) uses a deterministic key
2. Keys stored in `jobs` table with unique constraint
3. On restart: query `jobs` for `status IN (QUEUED, RUNNING)` → resume from last known state
4. **Never** duplicate: upload, publish, submit, or payout check

---

## 5.6 Retry Policies by Action

| Action | Backoff | Max Attempts | Timeout | Dead Letter |
|--------|---------|--------------|---------|-------------|
| Media Upload | 30s, 120s, 600s | 3 | 300s | MANUAL_CHECKPOINT |
| Video Publish | 30s, 120s, 600s | 3 | 300s | MANUAL_CHECKPOINT |
| URL Submit | 60s, 300s, 1800s | 3 | 3600s | MANUAL_CHECKPOINT |
| Analytics Sync | 300s, 1800s, 3600s | 3 | 86400s | Skip (catch up next run) |
| Token Refresh | 60s, 300s | 3 | 600s | Alert human |
| Payout Check | 3600s, 21600s | 5 | 86400s | Alert human |

---

## 5.7 Recovery Procedures

### Restart Recovery
```python
def recover_on_startup():
    # 1. Find incomplete jobs
    stuck_jobs = db.query(Job).filter(
        Job.status.in_([QUEUED, RUNNING, WAITING, RETRYING])
    ).all()
    
    for job in stuck_jobs:
        # 2. Check idempotency key in external system if possible
        if job.type == "PUBLISH":
            external_status = check_platform_post(job.idempotency_key)
            if external_status == "PUBLISHED":
                job.status = SUCCEEDED
                update_submission_state(job.submission_id, "PUBLISHED")
            else:
                job.status = QUEUED  # retry
        
        elif job.type == "SUBMIT":
            external_status = check_cr_submission(job.idempotency_key)
            if external_status in ["SUBMITTED", "APPROVED", "REJECTED"]:
                job.status = SUCCEEDED
                update_submission_state(job.submission_id, external_status)
            else:
                job.status = QUEUED
        
        # 3. Re-queue with incremented attempt
        job.attempt += 1
        job.status = QUEUED
        job.next_run_at = now()
        db.commit()
```

### Failed Job Recovery (Cron)
```python
# Runs every 15 minutes
def recover_failed_jobs():
    failed_jobs = db.query(Job).filter(
        Job.status == FAILED,
        Job.retryable == True,
        Job.attempt < Job.max_attempts
    ).all()
    
    for job in failed_jobs:
        if job.next_run_at <= now():
            job.status = QUEUED
            job.error_code = None
            job.error_message = None
            db.commit()
```

---

## 5.8 Human Checkpoints (State-Gated)

| State Transition | Human Required | Who | Timeout |
|------------------|----------------|-----|---------|
| DRAFT → SUBMITTED | If Pre-post Review | Brand moderator | 7 days |
| BRAND_REVIEW → APPROVED/REJECTED | Always | Brand moderator | 7 days (legacy auto-approve) |
| FLAGGED → BRAND_REVIEW | Appeal decision | CR Support | 10 biz days |
| REJECTED → (appeal) | Creator initiates | CR Support | 10 biz days |
| High-value clip publish | Configurable (>$500) | Operator | 1 hour |
| Regulated vertical caption | Always | Compliance officer | 1 hour |

---

*End of Phase 5. Next: Phase 6 — Hermes Architecture.*