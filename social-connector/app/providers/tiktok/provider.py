# TikTok Provider Implementation

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


class TikTokProvider:
    """TikTok Content Posting API provider."""
    
    id = "tiktok"
    
    capabilities = ProviderCapabilities(
        text=True,
        image=False,
        video=True,
        carousel=False,
        multi_image=False,
        documents=False,
        scheduled_publish=False,
        delete=False,
        status_poll=True,
        webhooks=True,
        requires_app_review=True,
        max_text_length=2200,
        max_video_size_mb=1024,  # 1GB
        max_video_duration_seconds=3600,  # 1 hour
        supported_video_mimes=["video/mp4", "video/quicktime"],
        supported_image_mimes=[],
        supported_video_aspect_ratios=["9:16", "16:9", "1:1"],
        supported_image_aspect_ratios=[],
    )
    
    # OAuth configuration
    oauth_authorization_url = "https://www.tiktok.com/v2/auth/authorize/"
    oauth_token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    oauth_scopes = [
        "video.upload",
        "video.list",
        "user.info.basic",
        "video.publish",
    ]
    oauth_pkce_required = True
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.client_key = config.get("client_key", "")
        self.client_secret = config.get("client_secret", "")
        self.redirect_uri = config.get("redirect_uri", "")
        self.base_url = "https://open.tiktokapis.com/v2"
        self.client = httpx.AsyncClient(timeout=120.0, verify=False)
    
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None, redirect_uri: str = "") -> str:
        from urllib.parse import urlencode
        
        params = {
            "client_key": self.client_key,
            "redirect_uri": redirect_uri or self.config.get("redirect_uri", ""),
            "state": state,
            "scope": " ".join(self.oauth_scopes),
            "response_type": "code",
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
            "client_key": self.client_key,
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
            "client_key": self.client_key,
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
        """Make authenticated request to TikTok API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=json_data, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code >= 400:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
                raise httpx.HTTPStatusError(
                    f"TikTok API error: {response.status_code}",
                    request=response.request,
                    response=response
                )
            
            return response.json() if response.content else {}
    
    async def get_accounts(self, connection: 'ConnectionData') -> List['AccountInfo']:
        """Get TikTok creator info."""
        accounts = []
        
        try:
            user_info = await self._make_request("GET", "/user/info/", connection.access_token)
            
            user_data = user_info.get("data", {}).get("user", {})
            accounts.append(AccountInfo(
                external_id=user_data.get("open_id", ""),
                name=user_data.get("display_name", ""),
                type="creator",
                capabilities=["text", "video"],
                metadata={"user": user_data}
            ))
        except Exception as e:
            logger.warning(f"Failed to get TikTok account: {e}")
        
        return accounts
    
    async def validate_post(self, connection: 'ConnectionData', post: 'UniversalPost') -> 'ValidationResult':
        """Validate a post against TikTok rules."""
        errors = []
        warnings = []
        adapted = {"text": post.text or "", "media": []}
        
        # Text length
        if post.text and len(post.text) > self.capabilities.max_text_length:
            errors.append(f"Caption exceeds {self.capabilities.max_text_length} characters")
        
        # Validate media - TikTok only supports video
        video_count = 0
        for media in post.media or []:
            if media.type == MediaType.VIDEO:
                video_count += 1
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
            errors.append("TikTok requires at least one video")
        elif video_count > 1:
            errors.append("TikTok only supports single video posts")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            adapted_post=adapted if len(errors) == 0 else None
        )
    
    async def _upload_video(self, access_token: str, video_url: str) -> Optional[str]:
        """Upload video to TikTok using upload API."""
        try:
            # Step 1: Create upload URL
            create_upload = await self._make_request("POST", "/video/upload/", access_token, 
                json_data={"media_type": "video", "chunk_size": 10485760})
            
            upload_url = create_upload.get("data", {}).get("upload_url")
            video_id = create_upload.get("data", {}).get("video_id")
            
            if not upload_url or not video_id:
                logger.error(f"Failed to create upload URL: {create_upload}")
                return None
            
            # Download video
            async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
                video_resp = await client.get(video_url, timeout=120.0)
                video_resp.raise_for_status()
                video_data = video_resp.content
            
            # Upload video in chunks (simplified - single chunk for now)
            async with httpx.AsyncClient(timeout=300.0, verify=False) as client:
                upload_resp = await client.put(
                    upload_url,
                    content=video_data,
                    headers={"Content-Type": "video/mp4"}
                )
                upload_resp.raise_for_status()
            
            return video_id
            
        except Exception as e:
            logger.error(f"Video upload failed: {e}")
            return None
    
    async def publish(self, connection: 'ConnectionData', post: 'UniversalPost') -> 'PublishResult':
        """Publish a video to TikTok."""
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
                error_message="TikTok requires a video"
            )
        
        try:
            # Upload video
            video_id = await self._upload_video(connection.access_token, video_media.url)
            if not video_id:
                return PublishResult(
                    success=False,
                    error_code="UPLOAD_FAILED",
                    error_message="Failed to upload video"
                )
            
            # Create post
            post_data = {
                "post_info": {
                    "title": post.text or "",
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_stitch": False,
                    "disable_comment": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_id": video_id,
                }
            }
            
            result = await self._make_request("POST", "/video/publish/", connection.access_token, 
                json_data=post_data)
            
            external_post_id = result.get("data", {}).get("publish_id", "")
            external_url = f"https://www.tiktok.com/@user/video/{external_post_id}"
            
            return PublishResult(
                success=True,
                external_post_id=external_post_id,
                external_url=external_url,
                status="published",
                raw_response=result
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
        """Get status of a TikTok post."""
        try:
            result = await self._make_request("GET", f"/video/query/", connection.access_token,
                params={"filters": {"video_ids": [external_post_id]}})
            
            videos = result.get("data", {}).get("videos", [])
            if videos:
                video = videos[0]
                status = video.get("status", "unknown")
                return {
                    "status": status,
                    "external_post_id": external_post_id,
                    "data": video
                }
            return {"status": "not_found", "external_post_id": external_post_id}
        except Exception as e:
            return {"status": "unknown", "external_post_id": external_post_id, "error": str(e)}
    
    async def delete(self, connection: 'ConnectionData', external_post_id: str) -> Dict[str, Any]:
        """Delete a TikTok post (not supported)."""
        return {"success": False, "error": "TikTok does not support post deletion via API"}
    
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None, redirect_uri: str = "") -> str:
        from urllib.parse import urlencode
        
        params = {
            "client_key": self.client_key,
            "redirect_uri": redirect_uri or self.config.get("redirect_uri", ""),
            "state": state,
            "scope": " ".join(self.oauth_scopes),
            "response_type": "code",
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
            "client_key": self.client_key,
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
    
    async def close(self):
        await self.client.aclose()