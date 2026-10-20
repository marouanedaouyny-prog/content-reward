# Social Connector - Provider Base Interface

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import asyncio


class ProviderKind(str, Enum):
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    X = "x"
    OLLAMA = "ollama"  # For local LLM fallback


class PostStatus(str, Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_REAUTH = "needs_reauth"
    NEEDS_REVIEW = "needs_review"


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"


@dataclass
class MediaItem:
    """Universal media item."""
    url: str
    type: MediaType
    mime: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[int] = None


@dataclass
class PostTargetConfig:
    """Target configuration for a post."""
    provider: str
    account_id: str
    # Provider-specific overrides
    visibility: Optional[str] = None  # public, private, unlisted, connections_only, etc.
    scheduled_at: Optional[str] = None  # ISO datetime


@dataclass
class UniversalPost:
    """Universal post that can be adapted to any platform."""
    text: Optional[str] = None
    media: List[MediaItem] = None
    targets: List[PostTargetConfig] = None
    idempotency_key: Optional[str] = None
    publish_at: Optional[str] = None  # ISO datetime
    
    def __post_init__(self):
        if self.media is None:
            self.media = []
        if self.targets is None:
            self.targets = []


@dataclass
class ProviderCapabilities:
    """What a provider supports."""
    text: bool = True
    image: bool = False
    video: bool = False
    carousel: bool = False
    multi_image: bool = False
    documents: bool = False
    scheduled_publish: bool = True
    delete: bool = False
    status_poll: bool = True
    webhooks: bool = False
    requires_app_review: bool = True
    max_text_length: Optional[int] = None
    max_video_size_mb: Optional[int] = None
    max_video_duration_seconds: Optional[int] = None
    supported_video_mimes: List[str] = None
    supported_image_mimes: List[str] = None
    supported_video_aspect_ratios: List[str] = None
    supported_image_aspect_ratios: List[str] = None
    
    def __post_init__(self):
        if self.supported_video_mimes is None:
            self.supported_video_mimes = ["video/mp4", "video/quicktime"]
        if self.supported_image_mimes is None:
            self.supported_image_mimes = ["image/jpeg", "image/png", "image/webp"]
        if self.supported_video_aspect_ratios is None:
            self.supported_video_aspect_ratios = ["16:9", "9:16", "1:1", "4:5"]
        if self.supported_image_aspect_ratios is None:
            self.supported_image_aspect_ratios = ["1:1", "4:5", "1.91:1", "16:9"]


@dataclass
class ValidationResult:
    """Result of post validation."""
    valid: bool
    errors: List[str] = None
    warnings: List[str] = None
    adapted_post: Optional[Dict[str, Any]] = None  # Provider-specific adapted post
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


@dataclass
class PublishResult:
    """Result of a publish operation."""
    success: bool
    external_post_id: Optional[str] = None
    external_url: Optional[str] = None
    status: str = "published"  # published, processing, failed
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = None
    # For async processing
    publish_id: Optional[str] = None  # Provider's publish ID for status polling
    
    def __post_init__(self):
        if self.success:
            self.status = self.status or "published"
        else:
            self.status = self.status or "failed"


@dataclass
class AccountInfo:
    """Account information from provider."""
    external_id: str
    name: str
    type: str  # profile, page, channel, etc.
    capabilities: List[str]  # text, image, video, etc.
    metadata: Optional[Dict] = None


@dataclass
class ConnectionData:
    """Stored connection data (with decrypted tokens)."""
    provider: str
    external_account_id: str
    external_account_type: str
    account_name: str
    access_token: str
    refresh_token: Optional[str] = None
    token_expires_at: Optional[str] = None
    scopes: Optional[List[str]] = None
    metadata: Optional[Dict] = None


class SocialProvider(ABC):
    """
    Abstract base class for all social media providers.
    Each platform implements this interface.
    """
    
    # Provider identifier
    id: str = ""
    
    # Capabilities - override in subclass
    capabilities: 'ProviderCapabilities' = ProviderCapabilities()
    
    # OAuth configuration
    oauth_authorization_url: str = ""
    oauth_token_url: str = ""
    oauth_scopes: List[str] = []
    oauth_pkce_required: bool = True
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
    
    @abstractmethod
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None, redirect_uri: str = "") -> str:
        """
        Generate OAuth authorization URL.
        Returns the URL to redirect the user to for authorization.
        """
        pass
    
    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        Returns token data: {access_token, refresh_token, expires_in, scope, ...}
        """
        pass
    
    @abstractmethod
    async def refresh_token(self, connection: ConnectionData) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.
        Returns new token data.
        """
        pass
    
    @abstractmethod
    async def get_accounts(self, connection: ConnectionData) -> List[AccountInfo]:
        """
        Discover available publishing accounts for this connection.
        """
        pass
    
    @abstractmethod
    async def validate_post(self, account: ConnectionData, post: UniversalPost) -> ValidationResult:
        """
        Validate a post against platform rules.
        Returns ValidationResult with any errors/warnings and adapted post.
        """
        pass
    
    @abstractmethod
    async def publish(self, account: ConnectionData, post: UniversalPost) -> PublishResult:
        """
        Publish a post to the platform.
        Returns PublishResult with external_post_id and URL.
        For async platforms, returns PublishResult with publish_id for polling.
        """
        pass
    
    @abstractmethod
    async def get_status(self, account: ConnectionData, external_post_id: str) -> Dict[str, Any]:
        """
        Get the current status of a published post.
        Returns normalized status and metadata.
        """
        pass
    
    @abstractmethod
    async def delete(self, account: ConnectionData, external_post_id: str) -> Dict[str, Any]:
        """
        Delete a published post.
        Returns result with success status.
        """
        pass
    
    def get_capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities."""
        return self.capabilities
    
    def get_oauth_scopes(self) -> List[str]:
        """Get required OAuth scopes."""
        return self.oauth_scopes
    
    def supports_media_type(self, media_type: str) -> bool:
        """Check if provider supports a media type."""
        if media_type == "image":
            return self.capabilities.image
        elif media_type == "video":
            return self.capabilities.video
        elif media_type == "carousel":
            return self.capabilities.carousel
        elif media_type == "document":
            return self.capabilities.documents
        return False
    
    def normalize_error(self, error: Exception, response: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Normalize provider error to standard error taxonomy.
        Override in subclass for provider-specific error mapping.
        """
        error_str = str(error).lower()
        
        if "401" in error_str or "unauthorized" in error_str or "invalid token" in error_str:
            return {"code": "AUTH_INVALID", "retryable": False}
        if "403" in error_str or "forbidden" in error_str or "permission denied" in error_str:
            return {"code": "PERMISSION_DENIED", "retryable": False}
        if "404" in error_str or "not found" in error_str:
            return {"code": "ACCOUNT_NOT_FOUND", "retryable": False}
        if "429" in error_str or "rate limit" in error_str:
            return {"code": "RATE_LIMITED", "retryable": True, "retry_after": 120}
        if "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str:
            return {"code": "PROVIDER_UNAVAILABLE", "retryable": True, "retry_after": 30}
        if "timeout" in error_str:
            return {"code": "PROCESSING_TIMEOUT", "retryable": True}
        if "expired" in error_str or "token expired" in error_str:
            return {"code": "AUTH_EXPIRED", "retryable": True}
        
        return {"code": "UNKNOWN", "retryable": False, "detail": str(error)}


# Provider Registry
class ProviderRegistry:
    """Registry of all available providers."""
    
    def __init__(self):
        self._providers: Dict[str, SocialProvider] = {}
    
    def register(self, provider: SocialProvider):
        """Register a provider."""
        if not provider.id:
            raise ValueError("Provider must have an id")
        self._providers[provider.id] = provider
    
    def get(self, provider_id: str) -> Optional[SocialProvider]:
        """Get a provider by ID."""
        return self._providers.get(provider_id)
    
    def list(self) -> List[SocialProvider]:
        """List all registered providers."""
        return list(self._providers.values())
    
    def get_capabilities(self, provider_id: str) -> Optional['ProviderCapabilities']:
        """Get capabilities for a provider."""
        provider = self.get(provider_id)
        if provider:
            return provider.get_capabilities()
        return None
    
    def get_all_capabilities(self) -> Dict[str, 'ProviderCapabilities']:
        """Get capabilities for all providers."""
        return {p.id: p.get_capabilities() for p in self._providers.values()}


# Global registry instance
_provider_registry = None


def get_provider_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = ProviderRegistry()
    return _provider_registry