# Configuration Loader
# Loads settings from .env file and environment variables

from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional, List
import os


class Settings(BaseSettings):
    """Application settings loaded from .env and environment."""
    
    # App
    app_env: str = Field(default="development", alias="APP_ENV")
    app_secret: str = Field(default="", alias="APP_SECRET")
    database_url: str = Field(default="sqlite:///./data/empire.db", alias="DATABASE_URL")
    
    # Token Encryption
    token_encryption_password: str = Field(default="", alias="TOKEN_ENCRYPTION_PASSWORD")
    token_encryption_salt: str = Field(default="", alias="TOKEN_ENCRYPTION_SALT")
    
    # API Key
    api_key: str = Field(default="", alias="API_KEY")
    
    # LinkedIn
    linkedin_client_id: str = Field(default="", alias="LINKEDIN_CLIENT_ID")
    linkedin_client_secret: str = Field(default="", alias="LINKEDIN_CLIENT_SECRET")
    linkedin_redirect_uri: str = Field(default="http://localhost:8000/v1/callback/linkedin", alias="LINKEDIN_REDIRECT_URI")
    
    # Facebook/Instagram
    facebook_client_id: str = Field(default="", alias="FACEBOOK_CLIENT_ID")
    facebook_client_secret: str = Field(default="", alias="FACEBOOK_CLIENT_SECRET")
    facebook_redirect_uri: str = Field(default="http://localhost:8000/v1/callback/facebook", alias="FACEBOOK_REDIRECT_URI")
    
    # TikTok
    tiktok_client_key: str = Field(default="", alias="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: str = Field(default="", alias="TIKTOK_CLIENT_SECRET")
    tiktok_redirect_uri: str = Field(default="http://localhost:8000/v1/callback/tiktok", alias="TIKTOK_REDIRECT_URI")
    
    # YouTube
    youtube_client_id: str = Field(default="", alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str = Field(default="", alias="YOUTUBE_CLIENT_SECRET")
    youtube_redirect_uri: str = Field(default="http://localhost:8000/v1/callback/youtube", alias="YOUTUBE_REDIRECT_URI")
    
    # X (Twitter)
    x_client_id: str = Field(default="", alias="X_CLIENT_ID")
    x_client_secret: str = Field(default="", alias="X_CLIENT_SECRET")
    x_redirect_uri: str = Field(default="http://localhost:8000/v1/callback/x", alias="X_REDIRECT_URI")
    
    # Content Rewards
    cr_email: str = Field(default="", alias="CR_EMAIL")
    cr_password: str = Field(default="", alias="CR_PASSWORD")
    
    # Whop
    whop_api_key: str = Field(default="", alias="WHOP_API_KEY")
    
    # LLM APIs
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    
    # Social Connector URL
    social_connector_url: str = Field(default="http://localhost:8000", alias="SOCIAL_CONNECTOR_URL")
    
    # Feature flags
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    
    # Storage
    storage_dir: str = Field(default="./storage", alias="STORAGE_DIR")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings from environment."""
    global _settings
    _settings = Settings()
    return _settings