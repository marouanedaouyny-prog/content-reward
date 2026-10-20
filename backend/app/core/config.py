# Automation Empire OS — Configuration
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
    database_url: str = Field(default="sqlite:///./data/empire.db", env="DATABASE_URL")

    # Storage
    storage_dir: str = Field(default="./storage", env="STORAGE_DIR")
    log_dir: str = Field(default="./logs", env="LOG_DIR")

    # Local AI (required — runs entirely off-machine)
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_default_model: str = Field(default="llama3.2", env="OLLAMA_DEFAULT_MODEL")

    # Cloud AI Providers with FREE tiers
    # OpenRouter (has free models)
    openrouter_api_key: Optional[str] = Field(default=None, env="OPENROUTER_API_KEY")
    openrouter_model: Optional[str] = Field(default="meta-llama/llama-3.1-8b-instruct:free", env="OPENROUTER_MODEL")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", env="OPENROUTER_BASE_URL")

    # Groq (free tier: 30 req/min, 6000 tokens/min, very fast)
    groq_api_key: Optional[str] = Field(default=None, env="GROQ_API_KEY")
    groq_model: Optional[str] = Field(default="llama-3.1-8b-instant", env="GROQ_MODEL")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", env="GROQ_BASE_URL")

    # NVIDIA (free tier - using working model)
    nvidia_api_key: Optional[str] = Field(default=None, env="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", env="NVIDIA_BASE_URL")
    nvidia_model: Optional[str] = Field(default="nvidia/nemotron-3-ultra-550b-a55b", env="NVIDIA_MODEL")

    # Gemini (free tier: 1500 req/day)
    gemini_api_key: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    gemini_model: Optional[str] = Field(default="gemini-1.5-flash", env="GEMINI_MODEL")
    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta/openai/", env="GEMINI_BASE_URL")

    # Content platform credentials (optional)
    whop_api_key: Optional[str] = Field(default=None, env="WHOP_API_KEY")
    whapp_app_id: Optional[str] = Field(default=None, env="WHOP_APP_ID")
    whop_client_id: Optional[str] = Field(default=None, env="WHOP_CLIENT_ID")
    whop_client_secret: Optional[str] = Field(default=None, env="WHOP_CLIENT_SECRET")

    tiktok_client_key: Optional[str] = Field(default=None, env="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: Optional[str] = Field(default=None, env="TIKTOK_CLIENT_SECRET")
    tiktok_redirect_uri: Optional[str] = Field(default=None, env="TIKTOK_REDIRECT_URI")

    # n8n
    n8n_base_url: str = Field(default="http://localhost:5678", env="N8N_BASE_URL")
    n8n_api_key: Optional[str] = Field(default=None, env="N8N_API_KEY")

    # System
    kill_switch: bool = Field(default=False, env="KILL_SWITCH")
    dry_run: bool = Field(default=False, env="DRY_RUN")

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


# Singleton instance
_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings