# Social Connector Configuration
# $0 constraint: all optional providers disabled by default
# Local-first: everything works without external keys

from pydantic import Field, validator
from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    # Environment
    app_env: str = Field(default="development", env="APP_ENV")
    app_secret: str = Field(default="change-this-to-a-random-secret", env="APP_SECRET")
    
    # Database
    database_url: str = Field(default="sqlite:///./data/app.db", env="DATABASE_URL")
    
    # Storage
    media_dir: str = Field(default="./data/media", env="MEDIA_DIR")
    log_dir: str = Field(default="./logs", env="LOG_DIR")
    
    # Encryption (required - for token encryption)
    encryption_key: str = Field(default="", env="ENCRYPTION_KEY")
    
    # API Security
    api_key: str = Field(default="", env="API_KEY")
    
    # LinkedIn
    linkedin_client_id: Optional[str] = Field(default=None, env="LINKEDIN_CLIENT_ID")
    linkedin_client_secret: Optional[str] = Field(default=None, env="LINKEDIN_CLIENT_SECRET")
    linkedin_redirect_uri: Optional[str] = Field(default=None, env="LINKEDIN_REDIRECT_URI")
    
    # Facebook
    facebook_app_id: Optional[str] = Field(default=None, env="FACEBOOK_APP_ID")
    facebook_app_secret: Optional[str] = Field(default=None, env="FACEBOOK_APP_SECRET")
    facebook_redirect_uri: Optional[str] = Field(default=None, env="FACEBOOK_REDIRECT_URI")
    
    # Instagram
    instagram_client_id: Optional[str] = Field(default=None, env="INSTAGRAM_CLIENT_ID")
    instagram_client_secret: Optional[str] = Field(default=None, env="INSTAGRAM_CLIENT_SECRET")
    instagram_redirect_uri: Optional[str] = Field(default=None, env="INSTAGRAM_REDIRECT_URI")
    
    # TikTok
    tiktok_client_key: Optional[str] = Field(default=None, env="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: Optional[str] = Field(default=None, env="TIKTOK_CLIENT_SECRET")
    tiktok_redirect_uri: Optional[str] = Field(default=None, env="TIKTOK_REDIRECT_URI")
    
    # YouTube
    youtube_client_id: Optional[str] = Field(default=None, env="YOUTUBE_CLIENT_ID")
    youtube_client_secret: Optional[str] = Field(default=None, env="YOUTUBE_CLIENT_SECRET")
    youtube_redirect_uri: Optional[str] = Field(default=None, env="YOUTUBE_REDIRECT_URI")
    
    # X (Twitter)
    x_client_id: Optional[str] = Field(default=None, env="X_CLIENT_ID")
    x_client_secret: Optional[str] = Field(default=None, env="X_CLIENT_SECRET")
    x_redirect_uri: Optional[str] = Field(default=None, env="X_REDIRECT_URI")
    
    # System
    base_url: str = Field(default="http://localhost:8000", env="BASE_URL")
    front_url: str = Field(default="http://localhost:3000", env="FRONT_URL")
    
    # Encryption
    encryption_key: str = Field(default="", env="ENCRYPTION_KEY")
    
    # Scheduler
    scheduler_enabled: bool = Field(default=True, env="SCHEDULER_ENABLED")
    worker_concurrency: int = Field(default=2, env="WORKER_CONCURRENCY")
    
    # $0 constraint enforcement
    allow_paid_services: bool = Field(default=False, env="ALLOW_PAID_SERVICES")
    deploy_mode: str = Field(default="local", env="DEPLOY_MODE")
    
    @validator("allow_paid_services")
    def enforce_no_paid(cls, v):
        """Hard-false in v1 code paths — never allow paid services."""
        if v is True:
            raise ValueError("ALLOW_PAID_SERVICES must be false in v1")
        return v
    
    @validator("deploy_mode")
    def enforce_local_first(cls, v):
        """Local deployment by default."""
        if v not in ("local", "render", "cloudflare"):
            raise ValueError("deploy_mode must be local|render|cloudflare")
        return v
    
    class Config:
        case_insensitive = True
        env_file = ".env"


# Singleton instance
_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings