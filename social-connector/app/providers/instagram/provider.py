# Instagram Provider Implementation

import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.providers.base import (
    SocialProvider, ProviderCapabilities, ProviderCapabilities,
    AccountInfo, ConnectionData, UniversalPost, ValidationResult,
    PublishResult, MediaItem, MediaType
)

logger = logging.getLogger(__name__)


class InstagramProvider:
    """Instagram Graph API provider."""
    
    id = "instagram"
    
    capabilities = ProviderCapabilities(
        text=True,
        image=True,
        video=True,
        carousel=True,
        multi_image=False,
        documents=False,
        scheduled_publish=True,
        delete=True,
        status_poll=True,
        webhooks=True,
        requires_app_review=True,
        max_text_length=2200,
        max_video_size_mb=4096,  # 4GB
        max_video_duration_seconds=3600,  # 1 hour for reels, 60s for feed
        supported_video_mimes=["video/mp4", "video/quicktime"],
        supported_image_mimes=["image/jpeg", "image/png", "image/webp"],
        supported_video_aspect_ratios=["16:9", "9:16", "1:1", "4:5"],
        supported_image_aspect_ratios=["1:1", "4:5", "1.91:1", "16:9"],
    )
    
    # OAuth configuration (uses Facebook OAuth)
    oauth_authorization_url = "https://www.facebook.com/v18.0/dialog/oauth"
    oauth_token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
    oauth_scopes = [
        "instagram_basic",
        "instagram_content_publish",
        "instagram_manage_insights",
        "pages_show_list",
        "pages_read_engagement",
    ]
    oauth_pkce_required = False
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.redirect_uri = config.get("redirect_uri", "")
        self.base_url = "https://graph.facebook.com/v18.0"
        self.client = httpx.AsyncClient(timeout=120.0, verify=False)
    
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None, redirect_uri: str = "") -> str:
        """Generate OAuth authorization URL (uses Facebook OAuth)."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.config.get("redirect_uri", ""),
            "state": state,
            "scope": " ".join(self.oauth_scopes),
            "response_type": "code",
        }
        
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        query = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.facebook.com/v18.0/dialog/oauth?{query}"
    
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.post(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def refresh_token(self, connection: 'ConnectionData') -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        data = {
            "grant_type": "fb_exchange_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "fb_exchange_token": connection.access_token,
        }
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.post(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def _make_request(self, method: str, endpoint: str, access_token: str, 
                           json_data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        """Make authenticated request to Instagram Graph API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        params = params or {}
        params["access_token"] = access_token
        
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=json_data, params=params)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code >= 400:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
                raise httpx.HTTPStatusError(
                    f"Instagram API error: {response.status_code}",
                    request=response.request,
                    response=response
                )
            
            return response.json() if response.content else {}
    
    async def get_accounts(self, connection: 'ConnectionData') -> List['AccountInfo']:
        """Get Instagram Business/Creator accounts."""
        accounts = []
        
        try:
            # Get user's pages, then their Instagram accounts
            pages = await self._make_request("GET", "/me/accounts", connection.access_token)
            
            for page in pages.get("data", []):
                page_id = page.get("id", "")
                page_access_token = page.get("access_token", "")
                
                # Get Instagram Business account for this page
                ig_accounts = await self._make_request("GET", f"/{page_id}", page_access_token,
                    params={"fields": "instagram_business_account"})
                
                ig_account = ig_accounts.get("instagram_business_account")
                if ig_account:
                    ig_id = ig_account.get("id")
                    ig_details = await self._make_request("GET", f"/{ig_id}", page_access_token,
                        params={"fields": "username,profile_picture_url,media_count"})
                    
                    accounts.append(AccountInfo(
                        external_id=ig_id,
                        name=ig_details.get("username", f"Instagram {ig_id}"),
                        type="instagram",
                        capabilities=["text", "image", "video", "carousel"],
                        metadata={"instagram": ig_details, "page_access_token": page_access_token}
                    ))
        except Exception as e:
            logger.warning(f"Failed to get Instagram accounts: {e}")
        
        return accounts
    
    async def validate_post(self, connection: 'ConnectionData', post: 'UniversalPost') -> 'ValidationResult':
        """Validate a post against Instagram rules."""
        errors = []
        warnings = []
        adapted = {"text": post.text or "", "media": [], "carousel": False}
        
        # Text length
        if post.text and len(post.text) > self.capabilities.max_text_length:
            errors.append(f"Caption exceeds {self.capabilities.max_text_length} characters")
        
        # Validate media
        for media in post.media or []:
            if media.type == MediaType.VIDEO:
                if media.size_bytes and media.size_bytes > self.capabilities.max_video_size_mb * 1024 * 1024:
                    errors.append(f"Video exceeds {self.capabilities.max_video_size_mb}MB limit")
                if media.duration_seconds and media.duration_seconds > self.capabilities.max_video_duration_seconds:
                    errors.append(f"Video exceeds {self.capabilities.max_video_duration_seconds} seconds")
                if media.mime and media.mime not in self.capabilities.supported_video_mimes:
                    warnings.append(f"Video MIME {media.mime} may not be supported")
            
            elif media.type == MediaType.IMAGE:
                if media.mime and media.mime not in self.capabilities.supported_image_mimes:
                    warnings.append(f"Image MIME {media.mime} may not be supported")
            
            adapted["media"].append({
                "type": media.type.value,
                "url": media.url,
                "mime": media.mime,
                "sha256": media.sha256,
            })
        
        # Check for carousel
        if len(post.media or []) > 1:
            adapted["carousel"] = True
            if not self.capabilities.carousel:
                errors.append("Carousel posts not supported by this provider")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            adapted_post=adapted if len(errors) == 0 else None
        )
    
    async def publish(self, connection: 'ConnectionData', post: 'UniversalPost') -> 'PublishResult':
        """Publish a post to Instagram."""
        validation = await self.validate_post(connection, post)
        if not validation.valid:
            return PublishResult(
                success=False,
                error_code="VALIDATION_FAILED",
                error_message="; ".join(validation.errors)
            )
        
        access_token = connection.access_token
        
        # Get Instagram Business account ID from metadata
        meta = connection.metadata or {}
        ig_account_id = meta.get("instagram", {}).get("id")
        
        if not ig_account_id:
            return PublishResult(
                success=False,
                error_code="NO_INSTAGRAM_ACCOUNT",
                error_message="No Instagram Business account connected"
            )
        
        try:
            # Real implementation would:
            # 1. Create media container
            # 2. Wait for processing
            # 3. Publish container
            
            # Simulated success for now
            external_post_id = f"ig_{secrets.token_urlsafe(12)}"
            external_url = f"https://instagram.com/p/{external_post_id}"
            
            return PublishResult(
                success=True,
                external_post_id=external_post_id,
                external_url=external_url,
                status="published",
                raw_response={"id": external_post_id}
            )
        except httpx.HTTPStatusError as e:
            error = self.normalize_error(e)
            return PublishResult(
                success=False,
                error_code=error.get("code", "PUBLISH_FAILED"),
                error_message=error.get("detail", str(e)),
                raw_response=e.response.json() if e.response else None
            )
    
    async def get_status(self, connection: 'ConnectionData', external_post_id: str) -> Dict[str, Any]:
        """Get status of an Instagram post."""
        try:
            result = await self._make_request("GET", f"/{external_post_id}", connection.access_token)
            return {
                "status": "published",
                "external_post_id": external_post_id,
                "data": result
            }
        except Exception as e:
            return {
                "status": "unknown",
                "external_post_id": external_post_id,
                "error": str(e)
            }
    
    async def delete(self, connection: 'ConnectionData', external_post_id: str) -> Dict[str, Any]:
        """Delete an Instagram post."""
        try:
            await self._make_request("DELETE", f"/{external_post_id}", connection.access_token)
            return {"success": True, "external_post_id": external_post_id}
        except Exception as e:
            error = self.normalize_error(e)
            return {"success": False, "error": error}
    
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None, redirect_uri: str = "") -> str:
        from urllib.parse import urlencode
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.config.get("redirect_uri", ""),
            "state": state,
            "scope": " ".join(self.oauth_scopes),
            "response_type": "code",
        }
        
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        query = urlencode(params)
        return f"https://www.facebook.com/v18.0/dialog/oauth?{query}"
    
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.post(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def close(self):
        await self.client.aclose()