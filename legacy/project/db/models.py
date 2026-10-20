# Database Models
# SQLModel-based models for SQLite, with migration support
# $0: uses only stdlib + SQLModel (no paid hosting required)

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Column, Relationship, create_engine, Session, select
from sqlalchemy import Enum as SQLEnum, JSON, Text, Table, Column, String, JSON as SA_JSON, DateTime, Integer, MetaData
import json
import uuid
import enum


# --- Core audit fields -------------------------------------------------------

class TimeStampedMixin:
    """Mixin for created_at, updated_at, and version tracking."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = Field(default=1)
    
    def touch(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)


# Base model for all tables
class BaseModel(SQLModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)


# --- Enums -------------------------------------------------------------------

class CampaignType(str, enum.Enum):
    CPM = "CPM"
    PER_POST = "PER_POST"
    RETAINER = "RETAINER"


class CampaignStatus(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    ANALYZED = "ANALYZED"
    ELIGIBLE = "ELIGIBLE"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    EXHAUSTED = "EXHAUSTED"


class SubmissionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    BOT_TRIAGE = "BOT_TRIAGE"
    FLAGGED = "FLAGGED"
    BRAND_REVIEW = "BRAND_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    VALIDATING = "VALIDATING"
    TRACKING = "TRACKING"
    PAID = "PAID"
    CLAWBACK = "CLAWBACK"
    UPLOAD_FAILED = "UPLOAD_FAILED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    SUBMISSION_FAILED = "SUBMISSION_FAILED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    CAMPAIGN_CLOSED = "CAMPAIGN_CLOSED"
    FRAUD_FLAGGED = "FRAUD_FLAGGED"


class SocialPlatform(str, enum.Enum):
    TIKTOK = "TIKTOK"
    INSTAGRAM = "INSTAGRAM"
    FACEBOOK = "FACEBOOK"
    YOUTUBE = "YOUTUBE"
    X = "X"


class SocialAccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    ERROR = "ERROR"


class SocialPostStatus(str, enum.Enum):
    PENDING = "PENDING"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DELETED = "DELETED"


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class JobType(str, enum.Enum):
    UPLOAD = "UPLOAD"
    PUBLISH = "PUBLISH"
    SUBMIT = "SUBMIT"
    ANALYTICS_SYNC = "ANALYTICS_SYNC"
    TOKEN_REFRESH = "TOKEN_REFRESH"
    PAYOUT_CHECK = "PAYOUT_CHECK"
    DOWNLOAD = "DOWNLOAD"
    TRANSCRIBE = "TRANSCRIBE"
    EDIT = "EDIT"
    QA = "QA"


class PayoutStatus(str, enum.Enum):
    PENDING = "PENDING"
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    WITHDRAWN = "WITHDRAWN"
    CLAWBACK = "CLAWBACK"
    FAILED = "FAILED"


class QAStatus(str, enum.Enum):
    QA_PASSED = "QA_PASSED"
    QA_FAILED = "QA_FAILED"


class SourceMediaStatus(str, enum.Enum):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    PROCESSED = "PROCESSED"
    ERROR = "ERROR"


# --- Campaigns ---------------------------------------------------------------

class Campaign(BaseModel, TimeStampedMixin, table=True):
    """Campaign — content reward campaign model."""
    __tablename__ = "campaigns"
    
    external_campaign_id: str = Field(index=True, unique=True)
    campaign_type: CampaignType = Field(sa_column=Column(SQLEnum(CampaignType), index=True))
    title: str = Field(default="")
    description: str = Field(default="", sa_column=Column(Text))
    brand_id: str = Field(default="", index=True)
    brand_name: str = Field(default="")
    status: CampaignStatus = Field(default=CampaignStatus.DISCOVERED, sa_column=Column(SQLEnum(CampaignStatus), index=True))
    platforms: List[str] = Field(default=[], sa_column=Column(JSON))
    required_tags: List[str] = Field(default=[], sa_column=Column(JSON))
    required_mentions: List[str] = Field(default=[], sa_column=Column(JSON))
    required_disclosure: str = Field(default="")
    source_content: List[Dict] = Field(default=[], sa_column=Column(JSON))
    editing_rules: List[Dict] = Field(default=[], sa_column=Column(JSON))
    min_views: Optional[int] = Field(default=None)
    max_payout_per_clip: Optional[float] = Field(default=None)
    budget_total: float = Field(default=0.0)
    budget_remaining: float = Field(default=0.0)
    budget_reserved: float = Field(default=0.0)
    rate_cpm: Optional[float] = Field(default=None)
    rate_per_post: Optional[float] = Field(default=None)
    rate_retainer_cycle: Optional[float] = Field(default=None)
    pre_post_review_enabled: bool = Field(default=False)
    submission_method: str = Field(default="URL")  # "URL" or "DRAFT_THEN_URL"
    co_posting_allowed: bool = Field(default=False)
    repost_limit: int = Field(default=5)
    deadline: Optional[datetime] = Field(default=None)
    vertical: Optional[str] = Field(default=None)
    discovered_at: Optional[datetime] = Field(default=None)
    analyzed_at: Optional[datetime] = Field(default=None)
    eligible_at: Optional[datetime] = Field(default=None)
    closed_at: Optional[datetime] = Field(default=None)


class CampaignRequirement(BaseModel, TimeStampedMixin, table=True):
    """CampaignRequirement — individual requirement within a campaign."""
    __tablename__ = "campaign_requirements"
    
    campaign_id: str = Field(foreign_key="campaigns.id", index=True)
    field_name: str = Field(index=True)
    field_value: Dict = Field(sa_column=Column(JSON))
    confidence: str = Field(default="LOW")  # "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN"
    source: str = Field(default="parser")


# --- Source Media ------------------------------------------------------------

class SourceMedia(BaseModel, TimeStampedMixin, table=True):
    """SourceMedia — raw media extracted for a campaign."""
    __tablename__ = "source_media"
    
    campaign_id: str = Field(foreign_key="campaigns.id", index=True)
    source_url: str = Field(default="")
    title: str = Field(default="")
    file_hash: str = Field(index=True, unique=True)  # SHA-256
    media_type: str = Field(default="video")
    duration: Optional[float] = Field(default=None)
    resolution: Optional[str] = Field(default=None)
    downloaded_at: Optional[datetime] = Field(default=None)
    status: SourceMediaStatus = Field(default=SourceMediaStatus.PENDING, sa_column=Column(SQLEnum(SourceMediaStatus), index=True))
    local_path: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)


# --- Transcripts -------------------------------------------------------------

class Transcript(BaseModel, TimeStampedMixin, table=True):
    """Transcript of source media."""
    __tablename__ = "transcripts"
    
    source_media_id: str = Field(foreign_key="source_media.id", index=True)
    full_text: str = Field(sa_column=Column(Text))
    segments: List[Dict] = Field(default=[], sa_column=Column(JSON))
    language: Optional[str] = Field(default=None)
    model_used: Optional[str] = Field(default=None)
    model_ver: Optional[str] = Field(default=None)


# --- Clips -------------------------------------------------------------------

class Clip(BaseModel, TimeStampedMixin, table=True):
    """Clip — generated video clip from a campaign source."""
    __tablename__ = "clips"
    
    campaign_id: str = Field(foreign_key="campaigns.id", index=True)
    source_media_id: Optional[str] = Field(default=None, foreign_key="source_media.id", index=True)
    clip_path: str
    clip_hash: str = Field(index=True, unique=True)  # SHA-256 of output file
    aspect_ratio: str = Field(default="16:9")
    duration: float = Field(default=0.0)
    title: str = Field(default="")
    captions: Optional[Dict] = Field(default=None, sa_column=Column(JSON))
    quality_score: float = Field(default=0.0)
    status: str = Field(default="GENERATED")  # GENERATED, QA_PASSED, QA_FAILED, PUBLISHED, REJECTED
    variant_of: Optional[str] = Field(default=None, foreign_key="clips.id", index=True)


# --- Captions ----------------------------------------------------------------

class ClipPlan(BaseModel, TimeStampedMixin, table=True):
    """ClipPlan — planned clip from source media."""
    __tablename__ = "clip_plans"
    
    campaign_id: str = Field(foreign_key="campaigns.id", index=True)
    source_media_id: str = Field(foreign_key="source_media.id", index=True)
    start_sec: float = Field(default=0.0)
    end_sec: float = Field(default=0.0)
    duration: float = Field(default=0.0)
    target_platforms: List[str] = Field(default=[], sa_column=Column(JSON))
    aspect_ratio: str = Field(default="9:16")
    strategy: str = Field(default="FIXED_WINDOW")
    transcript_segment: Dict = Field(default={}, sa_column=Column(JSON))


class Caption(BaseModel, TimeStampedMixin, table=True):
    """Caption per platform for a clip."""
    __tablename__ = "captions"
    
    clip_id: str = Field(foreign_key="clips.id", index=True)
    platform: SocialPlatform = Field(sa_column=Column(SQLEnum(SocialPlatform), index=True))
    text: str = Field(sa_column=Column(Text))
    hashtags: List[str] = Field(default=[], sa_column=Column(JSON))
    mentions: List[str] = Field(default=[], sa_column=Column(JSON))
    disclosure_included: bool = Field(default=False)
    char_count: int = Field(default=0)


# --- Social Accounts ---------------------------------------------------------

class SocialAccount(BaseModel, TimeStampedMixin, table=True):
    """SocialAccount — connected OAuth account for a creator."""
    __tablename__ = "social_accounts"
    
    creator_id: str = Field(index=True)
    platform: SocialPlatform = Field(sa_column=Column(SQLEnum(SocialPlatform), index=True))
    external_id: str = Field(index=True)  # platform user/page ID
    username: Optional[str] = Field(default=None)
    display_name: Optional[str] = Field(default=None)
    account_type: Optional[str] = Field(default=None)  # PERSONAL, BUSINESS, CREATOR, PAGE
    access_token_encrypted: str
    refresh_token_encrypted: Optional[str] = Field(default=None)
    token_expires_at: Optional[datetime] = Field(default=None, index=True)
    scopes: List[str] = Field(default=[], sa_column=Column(JSON))
    meta_data: Dict = Field(default={}, sa_column=Column(JSON))
    status: SocialAccountStatus = Field(default=SocialAccountStatus.ACTIVE, sa_column=Column(SQLEnum(SocialAccountStatus), index=True))
    connected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = Field(default=None)


# --- Social Posts ------------------------------------------------------------

class SocialPost(BaseModel, TimeStampedMixin, table=True):
    """SocialPost — a post that was published to a social platform."""
    __tablename__ = "social_posts"
    
    clip_id: str = Field(foreign_key="clips.id", index=True)
    campaign_id: str = Field(foreign_key="campaigns.id", index=True)
    social_account_id: str = Field(foreign_key="social_accounts.id", index=True)
    platform: SocialPlatform = Field(sa_column=Column(SQLEnum(SocialPlatform), index=True))
    post_url: str
    platform_post_id: str = Field(index=True)
    status: SocialPostStatus = Field(default=SocialPostStatus.PENDING, sa_column=Column(SQLEnum(SocialPostStatus), index=True))
    published_at: Optional[datetime] = Field(default=None)
    error_code: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    idempotency_key: str = Field(unique=True, index=True)


# --- Submissions -------------------------------------------------------------

class Submission(BaseModel, TimeStampedMixin, table=True):
    """Submission — formal submission to Content Rewards."""
    __tablename__ = "submissions"
    
    campaign_id: str = Field(foreign_key="campaigns.id", index=True)
    creator_id: str = Field(index=True)
    clip_id: str = Field(foreign_key="clips.id", index=True)
    social_post_id: Optional[str] = Field(default=None, foreign_key="social_posts.id", index=True)
    platform: SocialPlatform = Field(sa_column=Column(SQLEnum(SocialPlatform), index=True))
    clip_url: str
    clip_id_platform: Optional[str] = Field(default=None)
    draft_url: Optional[str] = Field(default=None)
    draft_id_platform: Optional[str] = Field(default=None)
    status: SubmissionStatus = Field(default=SubmissionStatus.DRAFT, sa_column=Column(SQLEnum(SubmissionStatus), index=True))
    bot_score: Optional[int] = Field(default=None, ge=0, le=100)
    bot_score_flagged: bool = Field(default=False)
    brand_reviewer_id: Optional[str] = Field(default=None)
    approved_at: Optional[datetime] = Field(default=None)
    rejected_at: Optional[datetime] = Field(default=None)
    rejection_reason: Optional[str] = Field(default=None)
    validation_start: Optional[datetime] = Field(default=None)
    validation_end: Optional[datetime] = Field(default=None)
    verified_views: int = Field(default=0)
    expected_payout: float = Field(default=0.0)
    payout_status: PayoutStatus = Field(default=PayoutStatus.PENDING, sa_column=Column(SQLEnum(PayoutStatus), index=True))
    payout_amount: Optional[float] = Field(default=None)
    payout_settled_at: Optional[datetime] = Field(default=None)
    submitted_at: Optional[datetime] = Field(default=None)
    idempotency_key: str = Field(unique=True, index=True)


class SubmissionStateHistory(BaseModel, TimeStampedMixin, table=True):
    """SubmissionStateHistory — append-only audit of state transitions."""
    __tablename__ = "submission_state_history"
    
    submission_id: str = Field(foreign_key="submissions.id", index=True)
    from_state: Optional[str] = Field(default=None)
    to_state: str = Field(index=True)
    trigger: str = Field(default="")
    actor: str = Field(default="system")  # "system", "brand_moderator", "creator", "cr_support", "operator"
    meta_data: Dict = Field(default={}, sa_column=Column(JSON))


# --- Analytics Snapshots -----------------------------------------------------

class AnalyticsSnapshot(BaseModel, TimeStampedMixin, table=True):
    """AnalyticsSnapshot — periodic snapshots of post metrics."""
    __tablename__ = "analytics_snapshots"
    
    submission_id: str = Field(foreign_key="submissions.id", index=True)
    social_post_id: Optional[str] = Field(default=None, foreign_key="social_posts.id", index=True)
    platform: SocialPlatform = Field(sa_column=Column(SQLEnum(SocialPlatform), index=True))
    snapshot_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    data_source: str = Field(default="API")  # "API", "MANUAL", "SCREENSHOT"
    views: int = Field(default=0)
    likes: int = Field(default=0)
    comments: int = Field(default=0)
    shares: int = Field(default=0)
    reach: Optional[int] = Field(default=None)
    impressions: Optional[int] = Field(default=None)
    video_views_3s: Optional[int] = Field(default=None)
    video_views_complete: Optional[int] = Field(default=None)
    avg_watch_time: Optional[float] = Field(default=None)
    raw_data: Dict = Field(default={}, sa_column=Column(JSON))


# --- Payouts -----------------------------------------------------------------

class Payout(BaseModel, TimeStampedMixin, table=True):
    """Payout — tracked earnings per submission."""
    __tablename__ = "payouts"
    
    submission_id: str = Field(foreign_key="submissions.id", index=True)
    campaign_id: str = Field(foreign_key="campaigns.id", index=True)
    creator_id: str = Field(index=True)
    amount: float = Field(default=0.0)
    currency: str = Field(default="USD")
    fee_amount: float = Field(default=0.0)
    fee_percentage: float = Field(default=0.0)
    net_amount: float = Field(default=0.0)
    status: PayoutStatus = Field(default=PayoutStatus.PENDING, sa_column=Column(SQLEnum(PayoutStatus), index=True))
    whop_withdrawal_id: Optional[str] = Field(default=None)
    whop_status: Optional[str] = Field(default=None)
    settled_at: Optional[datetime] = Field(default=None)
    withdrawn_at: Optional[datetime] = Field(default=None)
    clawback_at: Optional[datetime] = Field(default=None)
    clawback_reason: Optional[str] = Field(default=None)
    idempotency_key: str = Field(unique=True, index=True)


# --- Jobs (Async Task Queue) -------------------------------------------------

class Job(BaseModel, TimeStampedMixin, table=True):
    """Job — async task queue for external operations."""
    __tablename__ = "jobs"
    
    workflow_id: str = Field(index=True)
    type: JobType = Field(sa_column=Column(SQLEnum(JobType), index=True))
    status: JobStatus = Field(default=JobStatus.QUEUED, sa_column=Column(SQLEnum(JobStatus), index=True))
    payload: Dict = Field(default={}, sa_column=Column(JSON))
    attempt: int = Field(default=1)
    max_attempts: int = Field(default=3)
    idempotency_key: str = Field(unique=True, index=True)
    error_code: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    output: Dict = Field(default={}, sa_column=Column(JSON))
    retryable: bool = Field(default=True)
    next_run_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)


# --- QA Reports --------------------------------------------------------------

class QAReport(BaseModel, TimeStampedMixin, table=True):
    """QAReport — compliance check results for a clip."""
    __tablename__ = "qa_reports"
    
    clip_id: str = Field(foreign_key="clips.id", index=True)
    platform: SocialPlatform = Field(sa_column=Column(SQLEnum(SocialPlatform), index=True))
    checks: List[Dict] = Field(default=[], sa_column=Column(JSON))
    score: float = Field(default=0.0)
    status: QAStatus = Field(sa_column=Column(SQLEnum(QAStatus), index=True))
    failed_gates: List[str] = Field(default=[], sa_column=Column(JSON))
    engine_version: str = Field(default="1.0.0")


# --- Audit Logs --------------------------------------------------------------

class AuditLog(BaseModel, TimeStampedMixin, table=True):
    """AuditLog — security audit trail."""
    __tablename__ = "audit_logs"
    
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    action: str = Field(index=True)
    actor_type: str = Field(default="system")  # "system", "creator", "brand", "cr_support", "operator"
    actor_id: Optional[str] = Field(default=None)
    input: Dict = Field(default={}, sa_column=Column(JSON))
    output: Dict = Field(default={}, sa_column=Column(JSON))
    meta_data: Dict = Field(default={}, sa_column=Column(JSON))


# --- System Settings ---------------------------------------------------------
# Use plain SQLAlchemy Table completely separate from SQLModel to avoid SQLModel id conflicts

# Create separate metadata for system_settings to avoid SQLModel's automatic id field
_system_settings_metadata = MetaData()

system_settings_table = Table(
    "system_settings",
    _system_settings_metadata,
    Column("key", String, primary_key=True),
    Column("value_json", SA_JSON, nullable=False),
    Column("updated_by", String, default="system"),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column("updated_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Column("version", Integer, default=1),
)


def seed_default_settings(session: Session):
    """Insert default system settings if not present."""
    for key, value in DEFAULT_SETTINGS.items():
        existing = session.exec(
            select(system_settings_table).where(system_settings_table.c.key == key)
        ).first()
        if not existing:
            session.execute(
                system_settings_table.insert().values(
                    key=key,
                    value_json=value,
                    updated_by="system"
                )
            )
    session.commit()


# --- Engine: create DB and tables --------------------------------------------

def init_db(database_url: str = "sqlite:///./data/empire.db") -> Session:
    """Initialize SQLite database and create all tables."""
    engine = create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False},  # needed for multi-threaded access
    )
    SQLModel.metadata.create_all(engine)
    # Create system_settings table using separate metadata
    _system_settings_metadata.create_all(engine)
    return Session(engine)


def get_engine(database_url: str = "sqlite:///./data/empire.db"):
    """Get engine for direct use."""
    return create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )


# --- Health check ------------------------------------------------------------

def check_db_health(session: Session) -> Dict[str, Any]:
    """Check database connectivity and return health status."""
    try:
        session.exec(select(Campaign).limit(1))
        return {"status": "healthy", "details": "SQLite connection OK"}
    except Exception as e:
        return {"status": "unhealthy", "details": str(e)}


# --- Default settings seed ---------------------------------------------------

DEFAULT_SETTINGS = {
    "compliance.engine_version": "1.0.0",
    "limits.concurrent_edits": 2,
    "limits.max_retry_attempts": 3,
    "human_gates.clip_selection_review_threshold": 500,
    "human_gates.caption_review_verticals": ["CRYPTO", "FINANCE", "SUPPLEMENTS", "GAMBLING", "POLITICAL"],
    "human_gates.pre_publish_review_threshold": 500,
    "token_refresh_threshold_hours": 2,
    "analytics_sync_window_days": 30,
    "retry.backoff_seconds": [30, 120, 600],
    "platform.tiktok.unaudited_user_limit": 5,
    "platform.instagram.posts_per_day_limit": 25,
    "platform.youtube.quota_units_per_day": 10000,
    "platform.x.posts_per_month_free": 500,
}