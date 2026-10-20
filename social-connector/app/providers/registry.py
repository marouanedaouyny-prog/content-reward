# Social Connector - Provider Registry

from typing import Dict, List, Optional, Any
from app.providers.base import ProviderRegistry, ProviderKind, SocialProvider, ProviderCapabilities

from app.providers.linkedin.provider import LinkedInProvider
from app.providers.facebook.provider import FacebookProvider
from app.providers.instagram.provider import InstagramProvider
from app.providers.tiktok.provider import TikTokProvider
from app.providers.youtube.provider import YouTubeProvider


def initialize_providers(config: Dict[str, Any] = None) -> 'ProviderRegistry':
    """Initialize and return the provider registry with all configured providers."""
    registry = ProviderRegistry()
    
    # Register LinkedIn provider
    registry.register(LinkedInProvider(config.get("linkedin", {}) if config else {}))
    
    # Register Facebook provider
    registry.register(FacebookProvider(config.get("facebook", {}) if config else {}))
    
    # Register Instagram provider
    registry.register(InstagramProvider(config.get("instagram", {}) if config else {}))
    
    # Register TikTok provider
    registry.register(TikTokProvider(config.get("tiktok", {}) if config else {}))
    
    # Register YouTube provider
    registry.register(YouTubeProvider(config.get("youtube", {}) if config else {}))
    
    return registry


def get_available_providers(registry: 'ProviderRegistry') -> List[Dict]:
    """Get list of available providers with their capabilities."""
    providers = []
    for provider in registry.list():
        caps = provider.capabilities
        providers.append({
            "id": provider.id,
            "name": provider.id.capitalize(),
            "capabilities": {
                "text": caps.text,
                "image": caps.image,
                "video": caps.video,
                "carousel": caps.carousel,
                "multi_image": caps.multi_image,
                "documents": caps.documents,
                "scheduled_publish": caps.scheduled_publish,
                "delete": caps.delete,
                "status_poll": caps.status_poll,
                "webhooks": caps.webhooks,
                "requires_app_review": caps.requires_app_review,
            }
        })
    return providers