# Database Schema

**Based on:** All previous phases. SQLite for local, PostgreSQL for production.

---

## 8.1 Core Tables

```sql
-- Campaigns
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_campaign_id VARCHAR(255) UNIQUE NOT NULL,
    campaign_type VARCHAR(20) NOT NULL CHECK (campaign_type IN ('CPM', 'PER_POST', 'RETAINER')),
    title VARCHAR(500),
    description TEXT,
    brand_id VARCHAR(255),
    brand_name VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED' CHECK (status IN ('DISCOVERED', 'ANALYZED', 'ELIGIBLE', 'ACTIVE', 'CLOSED', 'EXHAUSTED')),
    platforms JSONB NOT NULL DEFAULT '[]',
    required_tags JSONB NOT NULL DEFAULT '[]',
    required_mentions JSONB NOT NULL DEFAULT '[]',
    required_disclosure TEXT,
    source_content JSONB NOT NULL DEFAULT '[]',
    editing_rules JSONB NOT NULL DEFAULT '[]',
    min_views INT,
    max_payout_per_clip DECIMAL(12,2),
    budget_total DECIMAL(12,2) NOT NULL DEFAULT 0,
    budget_remaining DECIMAL(12,2) NOT NULL DEFAULT 0,
    budget_reserved DECIMAL(12,2) NOT NULL DEFAULT 0,
    rate_cpm DECIMAL(10,4),
    rate_per_post DECIMAL(12,2),
    rate_retainer_cycle DECIMAL(12,2),
    pre_post_review_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    submission_method VARCHAR(20) NOT NULL DEFAULT 'URL' CHECK (submission_method IN ('URL', 'DRAFT_THEN_URL')),
    co_posting_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    repost_limit INT NOT NULL DEFAULT 5,
    deadline TIMESTAMP WITH TIME ZONE,
    vertical VARCHAR(50),
    discovered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    analyzed_at TIMESTAMP WITH TIME ZONE,
    eligible_at TIMESTAMP WITH TIME ZONE,
    closed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_campaigns_external ON campaigns(external_campaign_id);
CREATE INDEX idx_campaigns_deadline ON campaigns(deadline);

-- Campaign Requirements (parsed, structured)
CREATE TABLE campaign_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    field_name VARCHAR(100) NOT NULL,
    field_value JSONB NOT NULL,
    confidence VARCHAR(10) NOT NULL DEFAULT 'LOW' CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN')),
    source VARCHAR(50) NOT NULL DEFAULT 'parser',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_campaign_req_campaign ON campaign_requirements(campaign_id);

-- Source Media
CREATE TABLE source_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    source_url TEXT,
    title VARCHAR(500),
    file_hash VARCHAR(64) NOT NULL,  -- SHA-256
    media_type VARCHAR(20) NOT NULL DEFAULT 'video',
    duration DECIMAL(8,2),
    resolution VARCHAR(20),
    downloaded_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'DOWNLOADING', 'DOWNLOADED', 'PROCESSED', 'ERROR')),
    local_path TEXT,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_source_media_hash ON source_media(file_hash);
CREATE INDEX idx_source_media_campaign ON source_media(campaign_id);
CREATE INDEX idx_source_media_status ON source_media(status);

-- Transcripts
CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_media_id UUID NOT NULL REFERENCES source_media(id) ON DELETE CASCADE,
    full_text TEXT NOT NULL,
    segments JSONB NOT NULL DEFAULT '[]',
    language VARCHAR(10),
    model_used VARCHAR(50),
    model_version VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transcripts_source ON transcripts(source_media_id);

-- Clips
CREATE TABLE clips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    source_media_id UUID REFERENCES source_media(id) ON DELETE SET NULL,
    clip_path TEXT NOT NULL,
    clip_hash VARCHAR(64) NOT NULL,  -- SHA-256 of output file
    aspect_ratio VARCHAR(10) NOT NULL,
    duration DECIMAL(8,2) NOT NULL,
    title VARCHAR(500),
    captions JSONB,
    quality_score DECIMAL(5,2),
    status VARCHAR(30) NOT NULL DEFAULT 'GENERATED' CHECK (status IN ('GENERATED', 'QA_PASSED', 'QA_FAILED', 'PUBLISHED', 'REJECTED')),
    variant_of UUID REFERENCES clips(id),  -- for multi-platform variants
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_clips_hash ON clips(clip_hash);
CREATE INDEX idx_clips_campaign ON clips(campaign_id);
CREATE INDEX idx_clips_status ON clips(status);
CREATE INDEX idx_clips_variant ON clips(variant_of);

-- Captions
CREATE TABLE captions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,
    text TEXT NOT NULL,
    hashtags JSONB NOT NULL DEFAULT '[]',
    mentions JSONB NOT NULL DEFAULT '[]',
    disclosure_included BOOLEAN NOT NULL DEFAULT FALSE,
    char_count INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_captions_clip ON captions(clip_id);
CREATE UNIQUE INDEX idx_captions_clip_platform ON captions(clip_id, platform);

-- Social Accounts (connected OAuth accounts)
CREATE TABLE social_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL,  -- references creator in auth system
    platform VARCHAR(20) NOT NULL CHECK (platform IN ('TIKTOK', 'INSTAGRAM', 'FACEBOOK', 'YOUTUBE', 'X')),
    external_id VARCHAR(255) NOT NULL,  -- platform user/page ID
    username VARCHAR(255),
    display_name VARCHAR(255),
    account_type VARCHAR(30),  -- PERSONAL, BUSINESS, CREATOR, PAGE
    access_token_encrypted TEXT NOT NULL,
    refresh_token_encrypted TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    scopes JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED', 'ERROR')),
    connected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_social_accounts_creator_platform_ext ON social_accounts(creator_id, platform, external_id);
CREATE INDEX idx_social_accounts_status ON social_accounts(status);
CREATE INDEX idx_social_accounts_token_expires ON social_accounts(token_expires_at);

-- Social Posts (published clips)
CREATE TABLE social_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    social_account_id UUID NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,
    post_url TEXT NOT NULL,
    platform_post_id VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PUBLISHING', 'PUBLISHED', 'FAILED', 'DELETED')),
    published_at TIMESTAMP WITH TIME ZONE,
    error_code VARCHAR(50),
    error_message TEXT,
    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_social_posts_clip ON social_posts(clip_id);
CREATE INDEX idx_social_posts_campaign ON social_posts(campaign_id);
CREATE INDEX idx_social_posts_status ON social_posts(status);
CREATE INDEX idx_social_posts_platform_post ON social_posts(platform, platform_post_id);

-- Submissions (to Content Rewards)
CREATE TABLE submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    creator_id UUID NOT NULL,
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    social_post_id UUID REFERENCES social_posts(id) ON DELETE SET NULL,
    platform VARCHAR(20) NOT NULL,
    clip_url TEXT NOT NULL,
    clip_id_platform VARCHAR(255),
    draft_url TEXT,
    draft_id_platform VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'SUBMITTED', 'BOT_TRIAGE', 'FLAGGED', 'BRAND_REVIEW', 'APPROVED', 'REJECTED', 'VALIDATING', 'TRACKING', 'PAID', 'CLAWBACK', 'UPLOAD_FAILED', 'PUBLISH_FAILED', 'SUBMISSION_FAILED', 'TOKEN_EXPIRED', 'CAMPAIGN_CLOSED', 'FRAUD_FLAGGED')),
    bot_score INT CHECK (bot_score >= 0 AND bot_score <= 100),
    bot_score_flagged BOOLEAN NOT NULL DEFAULT FALSE,
    brand_reviewer_id VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejected_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    validation_start TIMESTAMP WITH TIME ZONE,
    validation_end TIMESTAMP WITH TIME ZONE,
    verified_views BIGINT NOT NULL DEFAULT 0,
    expected_payout DECIMAL(12,2) NOT NULL DEFAULT 0,
    payout_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (payout_status IN ('PENDING', 'RESERVED', 'SETTLED', 'CLAWBACK')),
    payout_amount DECIMAL(12,2),
    payout_settled_at TIMESTAMP WITH TIME ZONE,
    submitted_at TIMESTAMP WITH TIME ZONE,
    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_submissions_campaign ON submissions(campaign_id);
CREATE INDEX idx_submissions_creator ON submissions(creator_id);
CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_submissions_clip ON submissions(clip_id);
CREATE INDEX idx_submissions_idempotency ON submissions(idempotency_key);
CREATE INDEX idx_submissions_validation_end ON submissions(validation_end);

-- Submission State History (append-only audit)
CREATE TABLE submission_state_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    from_state VARCHAR(50),
    to_state VARCHAR(50) NOT NULL,
    trigger VARCHAR(100),
    actor VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_submission_history_submission ON submission_state_history(submission_id);
CREATE INDEX idx_submission_history_created ON submission_state_history(created_at);

-- Analytics Snapshots
CREATE TABLE analytics_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    social_post_id UUID REFERENCES social_posts(id) ON DELETE SET NULL,
    platform VARCHAR(20) NOT NULL,
    snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    data_source VARCHAR(30) NOT NULL,  -- 'API', 'MANUAL', 'SCREENSHOT'
    views BIGINT NOT NULL DEFAULT 0,
    likes BIGINT NOT NULL DEFAULT 0,
    comments BIGINT NOT NULL DEFAULT 0,
    shares BIGINT NOT NULL DEFAULT 0,
    reach BIGINT,
    impressions BIGINT,
    video_views_3s BIGINT,
    video_views_complete BIGINT,
    avg_watch_time DECIMAL(8,2),
    raw_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analytics_submission ON analytics_snapshots(submission_id);
CREATE INDEX idx_analytics_snapshot_time ON analytics_snapshots(snapshot_time);
CREATE INDEX idx_analytics_platform ON analytics_snapshots(platform);

-- Payouts
CREATE TABLE payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    creator_id UUID NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    fee_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    fee_percentage DECIMAL(5,2) NOT NULL DEFAULT 0,
    net_amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'RESERVED', 'SETTLED', 'WITHDRAWN', 'CLAWBACK', 'FAILED')),
    whop_withdrawal_id VARCHAR(255),
    whop_status VARCHAR(50),
    settled_at TIMESTAMP WITH TIME ZONE,
    withdrawn_at TIMESTAMP WITH TIME ZONE,
    clawback_at TIMESTAMP WITH TIME ZONE,
    clawback_reason TEXT,
    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_payouts_submission ON payouts(submission_id);
CREATE INDEX idx_payouts_campaign ON payouts(campaign_id);
CREATE INDEX idx_payouts_creator ON payouts(creator_id);
CREATE INDEX idx_payouts_status ON payouts(status);
CREATE INDEX idx_payouts_idempotency ON payouts(idempotency_key);

-- Jobs (async task queue)
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'UPLOAD', 'PUBLISH', 'SUBMIT', 'ANALYTICS_SYNC', 'TOKEN_REFRESH', 'PAYOUT_CHECK'
    status VARCHAR(20) NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'RUNNING', 'WAITING', 'RETRYING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'BLOCKED')),
    payload JSONB,
    attempt INT NOT NULL DEFAULT 1,
    max_attempts INT NOT NULL DEFAULT 3,
    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
    error_code VARCHAR(50),
    error_message TEXT,
    output JSONB,
    retryable BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_next_run ON jobs(next_run_at);
CREATE INDEX idx_jobs_idempotency ON jobs(idempotency_key);
CREATE INDEX idx_jobs_workflow ON jobs(workflow_id);

-- QA Reports
CREATE TABLE qa_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,
    checks JSONB NOT NULL DEFAULT '[]',
    score DECIMAL(5,2) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('QA_PASSED', 'QA_FAILED')),
    failed_gates JSONB NOT NULL DEFAULT '[]',
    engine_version VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_qa_clip ON qa_reports(clip_id);
CREATE INDEX idx_qa_status ON qa_reports(status);

-- Audit Logs
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    actor_type VARCHAR(30) NOT NULL,  -- 'system', 'creator', 'brand', 'cr_support', 'operator'
    actor_id VARCHAR(255),
    input JSONB,
    output JSONB,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
CREATE INDEX idx_audit_actor ON audit_logs(actor_type, actor_id);

-- System Settings
CREATE TABLE system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value_json JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(100) NOT NULL DEFAULT 'system'
);
```

---

## 8.2 Idempotency Keys (Critical)

| Table | Idempotency Key Format | Purpose |
|-------|------------------------|---------|
| `jobs` | `{type}:{entity_id}:{platform}:{attempt}` | Prevent duplicate external calls |
| `social_posts` | `publish:{clip_id}:{platform}:{account_id}` | Prevent duplicate publishes |
| `submissions` | `submit:{campaign_id}:{creator_id}:{clip_url_hash}` | Prevent duplicate submissions |
| `payouts` | `payout:{submission_id}:{validation_window_end}` | Prevent duplicate payout checks |
| `analytics_snapshots` | `analytics:{submission_id}:{platform}:{date}` | Prevent duplicate snapshots |

---

## 8.3 Migration Strategy

```python
# Alembic migration example
def upgrade():
    # 1. Create all tables (above)
    # 2. Add foreign keys
    # 3. Create indexes
    # 4. Insert default system_settings
    op.execute("""
        INSERT INTO system_settings (key, value_json, updated_by) VALUES
        ('compliance.engine_version', '"1.0.0"', 'system'),
        ('limits.concurrent_edits', '2', 'system'),
        ('limits.max_retry_attempts', '3', 'system'),
        ('human_gates.clip_selection_review_threshold', '500', 'system'),
        ('human_gates.caption_review_verticals', '["CRYPTO", "FINANCE", "SUPPLEMENTS", "GAMBLING", "POLITICAL"]', 'system')
    """)

def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('qa_reports')
    op.drop_table('jobs')
    op.drop_table('payouts')
    op.drop_table('analytics_snapshots')
    op.drop_table('submission_state_history')
    op.drop_table('submissions')
    op.drop_table('social_posts')
    op.drop_table('social_accounts')
    op.drop_table('captions')
    op.drop_table('clips')
    op.drop_table('transcripts')
    op.drop_table('source_media')
    op.drop_table('campaign_requirements')
    op.drop_table('campaigns')
    op.drop_table('system_settings')
```

---

## 8.4 Entity Relationship Summary

```
Campaign 1──∞ CampaignRequirement
Campaign 1──∞ SourceMedia
Campaign 1──∞ Clip
Campaign 1──∞ Submission
Campaign 1──∞ Payout

SourceMedia 1──1 Transcript
SourceMedia 1──∞ Clip

Clip 1──∞ Caption (per platform)
Clip 1──∞ SocialPost (per platform)
Clip 1──1 QAReport (per platform)
Clip ∞──1 SourceMedia

SocialAccount 1──∞ SocialPost
SocialAccount 1──∞ Submission

Submission 1──1 SocialPost
Submission 1──∞ AnalyticsSnapshot
Submission 1──1 Payout
Submission 1──∞ SubmissionStateHistory

Creator ∞──∞ SocialAccount
Creator ∞──∞ Submission
Creator ∞──∞ Payout
```

---

*End of Phase 8. Next: Phase 9 — Security.*