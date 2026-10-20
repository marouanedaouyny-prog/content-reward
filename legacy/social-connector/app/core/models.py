# Social Connector - Database Models

from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Boolean, ForeignKey, 
    Enum as SQLEnum, Index, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from typing import Optional

Base = declarative_base()


class PostStatus(str, Enum):
    """Post status states."""
    CREATED = "created"
    QUEUED = "queued"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_REAUTH = "needs_reauth"
    NEEDS_REVIEW = "needs_review"


class ConnectionStatus(str, Enum):
    """Social connection status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ERROR = "error"


class User(Base):
    """User table."""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    api_key_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    connections = relationship("SocialConnection", back_populates="user", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")


class SocialConnection(Base):
    """Social media connection (OAuth tokens + account info)."""
    __tablename__ = "social_connections"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    
    # Provider info
    provider = Column(String(50), nullable=False, index=True)  # linkedin, facebook, instagram, tiktok, youtube, x
    external_account_id = Column(String(255), nullable=False, index=True)
    external_account_type = Column(String(50), nullable=True)  # profile, page, channel, etc.
    account_name = Column(String(255), nullable=False)
    
    # Encrypted tokens
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Scopes and metadata
    scopes_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    
    # Status
    status = Column(
        SQLEnum(ConnectionStatus), 
        default=ConnectionStatus.ACTIVE, 
        nullable=False, 
        index=True
    )
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_refreshed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="connections")
    post_targets = relationship("PostTarget", back_populates="connection", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "external_account_id", name="uq_user_provider_account"),
        Index("ix_connection_user_provider", "user_id", "provider"),
    )


class Post(Base):
    """Post - a universal post that can be published to multiple targets."""
    __tablename__ = "posts"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    
    # Content
    text = Column(Text, nullable=True)
    media_json = Column(JSON, nullable=True)  # [{"url": "...", "type": "video/image", "mime": "...", "sha256": "..."}]
    
    # Scheduling
    publish_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Status
    status = Column(
        SQLEnum(PostStatus),
        default=PostStatus.CREATED,
        nullable=False,
        index=True
    )
    
    # Idempotency
    idempotency_key = Column(String(255), nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="posts")
    targets = relationship("PostTarget", back_populates="post", cascade="all, delete-orphan")
    media = relationship("Media", back_populates="post", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_post_idempotency"),
    )


class PostTarget(Base):
    """PostTarget - a post published to a specific social account."""
    __tablename__ = "post_targets"
    
    id = Column(String(36), primary_key=True)
    post_id = Column(String(36), ForeignKey("posts.id"), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("social_connections.id"), nullable=False, index=True)
    
    provider = Column(String(50), nullable=False, index=True)
    external_post_id = Column(String(255), nullable=True, index=True)
    external_url = Column(Text, nullable=True)
    
    status = Column(
        SQLEnum(PostStatus),
        default=PostStatus.QUEUED,
        nullable=False,
        index=True
    )
    
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    raw_response_json = Column(JSON, nullable=True)
    
    attempt_count = Column(Integer, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    post = relationship("Post", back_populates="targets")
    connection = relationship("SocialConnection", back_populates="post_targets")
    job_events = relationship("JobEvent", back_populates="target", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint("post_id", "connection_id", name="uq_post_connection"),
    )


class Media(Base):
    """Media file attached to a post."""
    __tablename__ = "media"
    
    id = Column(String(36), primary_key=True)
    post_id = Column(String(36), ForeignKey("posts.id"), nullable=False, index=True)
    
    local_path = Column(String(512), nullable=True)
    source_url = Column(Text, nullable=True)
    mime_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    post = relationship("Post", back_populates="media")
    
    __table_args__ = (
        Index("ix_media_post_sha256", "post_id", "sha256"),
    )


class JobEvent(Base):
    """Job event log for debugging and observability."""
    __tablename__ = "job_events"
    
    id = Column(String(36), primary_key=True)
    target_id = Column(String(36), ForeignKey("post_targets.id"), nullable=False, index=True)
    
    event_type = Column(String(50), nullable=False, index=True)  # queued, uploading, processing, published, failed, retry, cancelled
    payload_json = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    target = relationship("PostTarget", back_populates="job_events")