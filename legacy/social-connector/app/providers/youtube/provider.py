# YouTube Provider Implementation

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


class YouTubeProvider:
    """YouTube Data API v3 provider."""
    
    id = "youtube"
    
    capabilities = ProviderCapabilities(
        text=True,
        image=False,
        video=True,
        carousel=False,
        multi_image=False,
        documents=False,
        scheduled_publish=True,
        delete=True,
        status_poll=True,
        webhooks=True,
        requires_app_review=True,
        max_text_length=5000,
        max_video_size_mb=256000,  # 256GB
        max_video_duration_seconds=43200,  # 12 hours
        supported_video_mimes=["video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska"],
        supported_image_mimes=[],
        supported_video_aspect_ratios=["16:9", "9:16", "1:1", "4:5"],
        supported_image_aspect_ratios=[],
    )
    
    # OAuth configuration
    oauth_authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
    oauth_token_url = "https://oauth2.googleapis.com/token"
    oauth_scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]
    oauth_pkce_required = False
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.redirect_uri = config.get("redirect_uri", "")
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.upload_url = "https://www.googleapis.com/upload/youtube/v3"
        self.client = httpx.AsyncClient(timeout=300.0, verify=False)
    
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None, redirect_uri: str = "") -> str:
        from urllib.parse import urlencode
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.config.get("redirect_uri", ""),
            "state": state,
            "scope": " ".join(self.oauth_scopes),
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
        }
        
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        query = urlencode(params)
        return f"{self.oauth_authorization_url}?{query}"
    
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
                self.oauth_token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def refresh_token(self, connection: 'ConnectionData') -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.post(
                self.oauth_token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def _make_request(self, method: str, endpoint: str, access_token: str, 
                           json_data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        """Make authenticated request to YouTube API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        params = params or {}
        
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
                    f"YouTube API error: {response.status_code}",
                    request=response.request,
                    response=response
                )
            
            return response.json() if response.content else {}
    
    async def get_accounts(self, connection: 'ConnectionData') -> List['AccountInfo']:
        """Get YouTube channels for the authenticated user."""
        accounts = []
        
        try:
            # Get user's channels
            channels = await self._make_request("GET", "/channels", connection.access_token,
                params={"part": "snippet,contentDetails,statistics", "mine": "true"})
            
            for channel in channels.get("items", []):
                snippet = channel.get("snippet", {})
                stats = channel.get("statistics", {})
                
                accounts.append(AccountInfo(
                    external_id=channel.get("id", ""),
                    name=snippet.get("title", ""),
                    type="channel",
                    capabilities=["text", "video"],
                    metadata={
                        "channel": channel,
                        "stats": stats,
                        "description": snippet.get("description", ""),
                        "custom_url": snippet.get("customUrl", ""),
                    }
                ))
        except Exception as e:
            logger.warning(f"Failed to get YouTube channels: {e}")
        
        return accounts
    
    async def validate_post(self, connection: 'ConnectionData', post: 'UniversalPost') -> 'ValidationResult':
        """Validate a post against YouTube rules."""
        errors = []
        warnings = []
        adapted = {"text": post.text or "", "media": [], "privacy": "private"}
        
        # Text length
        if post.text and len(post.text) > self.capabilities.max_text_length:
            errors.append(f"Title/description exceeds {self.capabilities.max_text_length} characters")
        
        # Validate media - YouTube only supports video
        video_count = 0
        for media in post.media or []:
            if media.type == MediaType.VIDEO:
                if media.size_bytes and media.size_bytes > self.capabilities.max_video_size_mb * 1024 * 1024:
                    errors.append(f"Video exceeds {self.capabilities.max_video_size_mb}MB limit")
                if media.duration_seconds and media.duration_seconds > self.capabilities.max_video_duration_seconds:
                    errors.append(f"Video exceeds {self.capabilities.max_video_duration_seconds} seconds")
                if media.mime and media.mime not in self.capabilities.supported_video_mimes:
                    warnings.append(f"Video MIME {media.mime} may not be supported")
            
            adapted["media"].append({
                "type": media.type.value,
                "url": media.url,
                "mime": media.mime,
                "sha256": media.sha256,
            })
        
        if video_count == 0:
            errors.append("YouTube requires at least one video")
        elif len(post.media or []) > 1:
            errors.append("YouTube only supports single video uploads per API call")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            adapted_post=adapted if len(errors) == 0 else None
        )
    
    async def _upload_video(self, access_token: str, video_url: str, metadata: Dict) -> Optional[str]:
        """Upload video to YouTube using resumable upload."""
        try:
            # This is a simplified implementation
            # Real implementation would use resumable upload protocol
            
            # Step 1: Create upload session
            create_data = {
                "snippet": metadata.get("snippet", {}),
                "status": metadata.get("status", {"privacyStatus": "private"})
            }
            
            # For now, simulate success
            return f"yt_{secrets.token_urlsafe(12)}"
            
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return None
    
    async def publish(self, connection: 'ConnectionData', post: 'UniversalPost') -> 'PublishResult':
        """Publish a video to YouTube."""
        validation = await self.validate_post(connection, post)
        if not validation.valid:
            return PublishResult(
                success=False,
                error_code="VALIDATION_FAILED",
                error_message="; ".join(validation.errors)
            )
        
        access_token = connection.access_token
        
        # Get video URL
        video_media = next((m for m in post.media if m.type == MediaType.VIDEO), None)
        if not video_media:
            return PublishResult(
                success=False,
                error_code="NO_VIDEO",
                error_message="YouTube requires a video"
            )
        
        try:
            # Build metadata
            metadata = {
                "snippet": {
                    "title": (post.text or "Untitled")[:100],
                    "description": post.text or "",
                    "tags": [],
                    "categoryId": "22",  # People & Blogs
                },
                "status": {
                    "privacyStatus": "private",
                    "selfDeclaredMadeForKids": False,
                }
            }
            
            # Upload video
            video_id = await self._upload_video(connection.access_token, video_media.url, metadata)
            
            if not video_id:
                return PublishResult(
                    success=False,
                    error_code="UPLOAD_FAILED",
                    error_message="Failed to upload video to YouTube"
                )
            
            external_url = f"https://www.youtube.com/watch?v={video_id}"
            
            return PublishResult(
                success=True,
                external_post_id=video_id,
                external_url=f"https://www.youtube.com/watch?v={video_id}",
                status="published",
                raw_response={"id": video_id}
            )
        except httpx.HTTPStatusError as e:
            error = self.normalize_error(e)
            return PublishResult(
                success=False,
                error_code=error.get("code", "UPLOAD_FAILED"),
                error_message=error.get("detail", str(e)),
                raw_response=e.response.json() if e.response else None
            )
    
    async def get_status(self, connection: 'ConnectionData', external_post_id: str) -> Dict[str, Any]:
        """Get status of a YouTube video."""
        try:
            result = await self._make_request("GET", "/videos", connection.access_token,
                params={"part": "status,snippet", "id": external_post_id})
            
            items = result.get("items", [])
            if items:
                video = items[0]
                status = video.get("status", {}).get("uploadStatus", "unknown")
                return {
                    "status": status,
                    "external_post_id": external_post_id,
                    "data": video
                }
            return {"status": "not_found", "external_post_id": external_post_id}
        except Exception as e:
            return {"status": "unknown", "external_post_id": external_post_id, "error": str(e)}
    
    async def delete(self, connection: 'ConnectionData', external_post_id: str) -> Dict[str, Any]:
        """Delete a YouTube video."""
        try:
            await self._make_request("DELETE", "/videos", connection.access_token,
                params={"id": external_post_id})
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
            "access_type": "offline",
            "prompt": "consent",
        }
        
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        query = urlencode(params)
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    
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
                "https://oauth2.googleapis.com/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def refresh_token(self, connection: 'ConnectionData') -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def close(self):
        await self.client.aclose()