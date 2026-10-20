# Automation Empire OS — Database Models
# SQLModel-based models for SQLite, with migration support
# $0: uses only stdlib + SQLModel (no paid hosting required)

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Column, Relationship, create_engine, Session, select
from sqlalchemy import Enum as SQLEnum, JSON
import json
import uuid
import enum


# --- Core audit fields -------------------------------------------------------

class TimeStampedModel(SQLModel):
    """Base model with created_at, updated_at, and version tracking."""
    id: Optional[str] = Field(default_factory=lambda str: str(uuid.uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = Field(default=1, sa_column=Column(default=1))

    def touch(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)


# --- Provider model --------------------------------------------------------

class Provider(SQLModel, table=True):
    """Provider registry — tracks available AI/External providers."""
    __tablename__ = "provider"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True, unique=True)
    kind: str  # "ollama", "openrouter", "gemini", "groq", etc.
    health: str = Field(default="unknown")  # "healthy", "unhealthy", "rate_limited"
    config_json: Optional[str] = Field(default=None)  # serialized config
    requests_today: int = Field(default=0)
    tokens_today: int = Field(default=0)
    reset_time: Optional[datetime] = Field(default=None)
    last_check: Optional[datetime] = Field(default=None)

    def is_healthy(self) -> bool:
        return self.health == "healthy"

    def can_use(self) -> bool:
        return self.is_healthy() and self.requests_today < 1000  # simple guard


# --- Job state machine -----------------------------------------------------

class JobStatus(str, enum.Enum):
    """Job execution states."""
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"

    # Allow SQL comparison
    pass


class Job(SQLModel, table=True):
    """Job — individual execution unit within a workflow."""
    __tablename__ = "job"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workflow_id: str = Field(index=True, foreign_key="workflow_version.id")
    workflow_version_id: Optional[str] = Field(default=None, foreign_key="workflow_version.id")
    payload: Optional[str] = Field(default=None, sa_column=Column(JSON))  # serialized job payload
    status: JobStatus = Field(
        default=JobStatus.QUEUED,
        sa_column=Column(SQLEnum(JobStatus), index=True)
    )
    attempt: int = Field(default=1)
    idempotency_key: Optional[str] = Field(default=None, unique=True, index=True)
    error_code: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    output: Optional[str] = Field(default=None, sa_column=Column(JSON))
    metrics: Optional[str] = Field(default=None, sa_column=Column(JSON))  # serialized metrics
    retryable: bool = Field(default=True)
    risk_level: str = Field(default="medium")
    estimated_cost: float = Field(default=0.0)
    billing_status: str = Field(default="free_tier_or_local")
    artifacts: Optional[str] = Field(default=None, sa_column=Column(JSON))  # serialized artifact references
    trace_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_terminal(self) -> bool:
        return self.status in (
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.BLOCKED,
        )

    def is_retryable(self) -> bool:
        return self.retryable and not self.is_terminal()

    def touch(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)


class JobAttempt(SQLModel, table=True):
    """JobAttempt — tracks each attempt of a job for audit/debug purposes."""
    __tablename__ = "job_attempt"
    job_id: str = Field(foreign_key="job.id", primary_key=True)
    attempt_number: int = Field(primary_key=True)
    status: JobStatus = Field(
        sa_column=Column(SQLEnum(JobStatus), index=True)
    )
    output: Optional[str] = Field(default=None, sa_column=Column(JSON))
    error_code: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    execution_time_ms: Optional[int] = Field(default=None)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)


# --- Workflow registry -----------------------------------------------------

class WorkflowVersion(SQLModel, table=True):
    """WorkflowVersion — registered workflow definitions."""
    __tablename__ = "workflow_version"
    id: str = Field(primary_key=True)  # e.g. "content_rewards"
    version: str = Field(default="1.0.0")
    name: str = Field(default="Unnamed workflow")
    description: Optional[str] = Field(default=None)
    enabled: bool = Field(default=True)
    risk_level: str = Field(default="medium")
    permissions: Optional[str] = Field(default=None, sa_column=Column(JSON))
    retry_config: Optional[str] = Field(default=None, sa_column=Column(JSON))
    approval_rules: Optional[str] = Field(default=None, sa_column=Column(JSON))
    cost_tracking: Optional[str] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def retry_config_dict(self) -> Dict[str, Any]:
        if self.retry_config:
            return json.loads(self.retry_config)
        return {"max_attempts": 3, "backoff_seconds": [30, 120, 600]}

    def approval_rules_dict(self) -> Dict[str, Any]:
        if self.approval_rules:
            return json.loads(self.approval_rules)
        return {}


# --- Campaigns (Content Rewards specific) ---------------------------------

class Campaign(SQLModel, table=True):
    """Campaign — content reward campaign model."""
    __tablename__ = "campaign"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    campaign_id: str = Field(index=True, unique=True)  # external ID if applicable
    source: str = Field(default="content_rewards")  # "content_rewards" | "lead_gen" | etc.
    title: str = Field(default="")
    type: str = Field(default="cpm")  # "cpm" | "per_post" | "retainer"
    platforms: Optional[str] = Field(default=None, sa_column=Column(JSON))  # serialized
    niches: Optional[str] = Field(default=None, sa_column=Column(JSON))
    budget_total: float = Field(default=0.0)
    budget_remaining: float = Field(default=0.0)
    rate: float = Field(default=0.0)  # payout rate
    max_payout: float = Field(default=0.0)
    min_views: int = Field(default=0)
    application_required: bool = Field(default=False)
    preapproval_required: bool = Field(default=False)
    required_tags: Optional[str] = Field(default=None, sa_column=Column(JSON))
    required_mentions: Optional[str] = Field(default=None, sa_column=Column(JSON))
    duration_min: int = Field(default=0)
    duration_max: int = Field(default=0)
    source_material: Optional[str] = Field(default=None, sa_column=Column(JSON))
    rights_notes: str = Field(default="")
    deadline: Optional[datetime] = Field(default=None)
    status: str = Field(default="unknown", index=True)  # "unknown" | "qualified" | "approved" | etc.
    raw_source_url: str = Field(default="")
    metadata_json: Optional[str] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CampaignRequirement(SQLModel, table=True):
    """CampaignRequirement — individual requirement within a campaign."""
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id")
    field_name: str = Field(index=True)
    field_value: str = Field(index=True)
    confidence: str = Field(default="LOW")  # "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN"
    source: str = Field(default="parser")  # where this came from


class SourceMedia(SQLModel, table=True):
    """SourceMedia — raw media extracted for a campaign."""
    __tablename__ = "source_media"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id")
    source_url: str = Field(index=True)
    title: str = Field(default="")
    file_hash: str = Field(index=True, unique=True)  # SHA-256
    media_type: str = Field(default="")  # "video" | "image" | "audio" | "text"
    duration: Optional[float] = Field(default=None)
    resolution: Optional[str] = Field(default=None)
    downloaded_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="pending")  # "pending" | "downloaded" | "processed" | "error"


class Clip(SQLModel, table=True):
    """Clip — generated video clip from a campaign source."""
    __tablename__ = "clip"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id")
    source_media_id: Optional[str] = Field(default=None, foreign_key="source_media.id")
    clip_path: str = Field(index=True)  # relative path in storage/
    clip_hash: str = Field(index=True, unique=True)  # SHA-256 of clip
    aspect_ratio: str = Field(default="16:9")
    duration: float = Field(default=0.0)
    title: str = Field(default="")
    captions: Optional[str] = Field(default=None, sa_column=Column(JSON))
    quality_score: float = Field(default=0.0)
    status: str = Field(default="generated")  # "generated" | "qc_passed" | "approved" | "rejected"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PublishedPost(SQLModel, table=True):
    """PublishedPost — a post that was published to a social platform."""
    __tablename__ = "published_post"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    clip_id: Optional[str] = Field(default=None, foreign_key="clip.id")
    campaign_id: str = Field(foreign_key="campaign.id")
    platform: str = Field(index=True)  # "tiktok" | "youtube" | "instagram" | "facebook" | "x"
    post_id: str = Field(index=True)  # external post ID from platform
    status: str = Field(default="pending")  # "pending" | "published" | "failed"
    published_at: Optional[datetime] = Field(default=None)
    metrics: Optional[str] = Field(default=None, sa_column=Column(JSON))  # serialized
    view_count: int = Field(default=0)
    earnings: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Submission(SQLModel, table=True):
    """Submission — formal submission to a platform or partner."""
    __tablename__ = "submission"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id")
    status: str = Field(default="pending")  # "pending" | "approved" | "rejected" | "submitted"
    submitted_at: Optional[datetime] = Field(default=None)
    approval_id: Optional[str] = Field(default=None)  # removed foreign key to approvals table
    metadata_json: Optional[str] = Field(default=None, sa_column=Column(JSON))


# --- Artifacts ------------------------------------------------------------

class Artifact(SQLModel, table=True):
    """Artifact — tracked output file (video, image, audio, text, JSON, CSV, etc.)."""
    __tablename__ = "artifact"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    key: str = Field(index=True, unique=True)  # e.g. "clip_abc123" or "report_xyz"
    kind: str = Field(default="")  # "video" | "image" | "audio" | "text" | "json" | "csv"
    path: str = Field(index=True)  # relative path under storage/
    sha256: str = Field(index=True, unique=True)
    size_bytes: int = Field(default=0)
    related_id: Optional[str] = Field(default=None)  # references clip_id, job_id, etc.
    related_type: Optional[str] = Field(default=None)  # "clip" | "job" | "campaign"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Metrics snapshots -----------------------------------------------------

class MetricsSnapshot(SQLModel, table=True):
    """MetricsSnapshot — periodic snapshots of campaign/post metrics."""
    __tablename__ = "metrics_snapshot"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    campaign_id: Optional[str] = Field(default=None, foreign_key="campaign.id")
    published_post_id: Optional[str] = Field(default=None, foreign_key="published_post.id")
    snapshot_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: str = Field(sa_column=Column(JSON))  # serialized metrics
    source: str = Field(default="")  # e.g. "tiktok_api" | "youtube_analytics" | "manual"


# --- Earnings --------------------------------------------------------------

class Earnings(SQLModel, table=True):
    """Earnings — tracked earnings per campaign/post."""
    __tablename__ = "earnings"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    campaign_id: Optional[str] = Field(default=None, foreign_key="campaign.id")
    published_post_id: Optional[str] = Field(default=None, foreign_key="published_post.id")
    amount: float = Field(default=0.0)
    currency: str = Field(default="USD")
    source: str = Field(default="")  # e.g. "tiktok_payout" | "youtube_adSense"
    transaction_id: Optional[str] = Field(default=None, unique=True)
    status: str = Field(default="pending")  # "pending" | "settled" | "withdrawn" | "disputed"
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Errors ----------------------------------------------------------------

class ErrorLog(SQLModel, table=True):
    """ErrorLog — tracked errors for observability."""
    __tablename__ = "error_log"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    error_code: str = Field(index=True)  # e.g. "RATE_LIMIT" | "NETWORK" | "PARSER" | etc.
    severity: str = Field(default="warning")  # "info" | "warning" | "error" | "critical"
    job_id: Optional[str] = Field(default=None, foreign_key="job.id")
    workflow_id: Optional[str] = Field(default=None, foreign_key="workflow_version.id")
    message: str = Field(index=True)
    traceback: Optional[str] = Field(default=None, sa_column=Column(JSON))
    context_json: Optional[str] = Field(default=None, sa_column=Column(JSON))  # serialized context
    recovered: bool = Field(default=False)
    recovered_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- System settings -------------------------------------------------------

class SystemSettings(SQLModel, table=True):
    """SystemSettings — global system configuration stored in DB."""
    key: str = Field(primary_key=True)
    value_json: str = Field(sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: str = Field(default="system")


# --- Engine: create DB and tables -----------------------------------------

def init_db(database_url: str = "sqlite:///./data/empire.db") -> Session:
    """Initialize SQLite database and create all tables."""
    engine = create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False},  # needed for multi-threaded access
    )
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(engine)
    return Session(engine)


# --- Engine: health check ---------------------------------------------------

def check_db_health(session: Session) -> Dict[str, Any]:
    """Check database connectivity and return health status."""
    try:
        session.exec(select(Provider).limit(1))
        return {"status": "healthy", "details": "SQLite connection OK"}
    except Exception as e:
        return {"status": "unhealthy", "details": str(e)}