# LinkedIn Provider Implementation

import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from app.providers.base import (
    SocialProvider, ProviderCapabilities, ProviderCapabilities,
    AccountInfo, ConnectionData, UniversalPost, ValidationResult,
    PublishResult, MediaItem, MediaType
)

logger = logging.getLogger(__name__)


class LinkedInProvider:
    """LinkedIn Posts API provider."""
    
    id = "linkedin"
    
    capabilities = ProviderCapabilities(
        text=True,
        image=True,
        video=True,
        carousel=False,
        multi_image=False,
        documents=True,
        scheduled_publish=True,
        delete=False,
        status_poll=True,
        webhooks=False,
        requires_app_review=True,
        max_text_length=3000,
        max_video_size_mb=5120,  # 5GB
        max_video_duration_seconds=600,  # 10 minutes
        supported_video_mimes=["video/mp4", "video/quicktime"],
        supported_image_mimes=["image/jpeg", "image/png", "image/webp"],
        supported_video_aspect_ratios=["16:9", "9:16", "1:1", "4:5"],
        supported_image_aspect_ratios=["1:1", "4:5", "1.91:1", "16:9"],
    )
    
    # OAuth configuration
    oauth_authorization_url = "https://www.linkedin.com/oauth/v2/authorization"
    oauth_token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    oauth_scopes = [
        "r_liteprofile",
        "r_emailaddress",
        "w_member_social",
        "rw_organization_admin",  # for organization posts
    ]
    oauth_pkce_required = False  # LinkedIn doesn't require PKCE but supports it
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.redirect_uri = config.get("redirect_uri", "")
        self.base_url = "https://api.linkedin.com/v2"
        self.upload_url = "https://api.linkedin.com/v2"
        self.client = httpx.AsyncClient(timeout=120.0, verify=False)
    
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None, redirect_uri: str = "") -> str:
        """Generate LinkedIn OAuth authorization URL."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.config.get("redirect_uri", ""),
            "state": state,
            "scope": " ".join(self.oauth_scopes),
        }
        
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        query = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.oauth_authorization_url}?{query}"
    
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
                self.oauth_token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def refresh_token(self, connection: 'ConnectionData') -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        # LinkedIn doesn't provide refresh tokens in standard OAuth
        # Tokens are long-lived (60 days), need re-auth
        raise NotImplementedError("LinkedIn doesn't support refresh tokens. Re-auth required.")
    
    async def _make_request(self, method: str, endpoint: str, access_token: str, 
                           json_data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        """Make authenticated request to LinkedIn API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=json_data)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code >= 400:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
                raise httpx.HTTPStatusError(
                    f"LinkedIn API error: {response.status_code}",
                    request=response.request,
                    response=response
                )
            
            return response.json() if response.content else {}
    
    async def get_accounts(self, connection: 'ConnectionData') -> List['AccountInfo']:
        """Get LinkedIn accounts (profiles and organizations)."""
        accounts = []
        
        # Get user profile
        try:
            profile = await self._make_request("GET", "/me", connection.access_token)
            
            accounts.append(AccountInfo(
                external_id=profile.get("id", ""),
                name=profile.get("localizedFirstName", "") + " " + profile.get("localizedLastName", ""),
                type="profile",
                capabilities=["text", "image", "video", "document"],
                metadata={"profile": profile}
            ))
        except Exception as e:
            logger.warning(f"Failed to get LinkedIn profile: {e}")
        
        # Get organizations where user is admin
        try:
            orgs = await self._make_request("GET", "/organizationAcls", connection.access_token, 
                                           params={"q": "roleAssignee", "state": "APPROVED"})
            
            for org in orgs.get("elements", []):
                org_urn = org.get("organization", "")
                org_id = org_urn.split(":")[-1] if org_urn else ""
                
                if org_id:
                    org_details = await self._make_request("GET", f"/organizations/{org_id}", connection.access_token)
                    accounts.append(AccountInfo(
                        external_id=f"urn:li:organization:{org_id}",
                        name=org_details.get("localizedName", f"Organization {org_id}"),
                        type="organization",
                        capabilities=["text", "image", "video", "document"],
                        metadata={"organization": org_details}
                    ))
        except Exception as e:
            logger.warning(f"Failed to get LinkedIn organizations: {e}")
        
        return accounts
    
    async def validate_post(self, connection: 'ConnectionData', post: 'UniversalPost') -> 'ValidationResult':
        """Validate a post against LinkedIn rules."""
        errors = []
        warnings = []
        adapted = {"text": post.text or "", "media": []}
        
        # Text length
        if post.text and len(post.text) > self.capabilities.max_text_length:
            errors.append(f"Text exceeds {self.capabilities.max_text_length} characters")
        
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
        
        # Check targets
        for target in post.targets or []:
            if target.provider != "linkedin":
                errors.append(f"Target provider {target.provider} not supported by LinkedIn adapter")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            adapted_post=adapted if len(errors) == 0 else None
        )
    
    async def _upload_media(self, access_token: str, media_url: str, media_type: MediaType) -> Dict:
        """Upload media to LinkedIn using binary upload."""
        # Download media first
        async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
            media_resp = await client.get(media_url, timeout=60.0)
            media_resp.raise_for_status()
            media_data = media_resp.content
        
        # Register upload
        register_data = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"] if media_type == MediaType.VIDEO 
                          else ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": f"urn:li:person:{await self._get_person_urn(access_token)}",
                "serviceRelationships": [{
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent"
                }]
            }
        }
        
        upload_resp = await self._make_request("POST", "/assets?action=registerUpload", access_token, json_data=register_data)
        upload_info = upload_resp.get("value", {})
        
        # Upload to the provided upload URL
        upload_url = upload_info.get("uploadMechanism", {}).get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}).get("uploadUrl")
        upload_headers = upload_info.get("uploadMechanism", {}).get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}).get("headers", {})
        
        if not upload_url:
            raise ValueError("Failed to get upload URL from LinkedIn")
        
        # Upload the file
        async with httpx.AsyncClient(timeout=300.0, verify=False) as client:
            upload_resp = await client.post(
                upload_url,
                content=media_data,
                headers=upload_headers
            )
            upload_resp.raise_for_status()
        
        return {"asset": upload_info.get("asset"), "media_urn": upload_info.get("asset")}
    
    async def _get_person_urn(self, access_token: str) -> str:
        """Get the person URN for the authenticated user."""
        profile = await self._make_request("GET", "/me", access_token)
        return profile.get("id", "")
    
    async def publish(self, connection: 'ConnectionData', post: 'UniversalPost') -> 'PublishResult':
        """Publish a post to LinkedIn."""
        # Validate first
        validation = await self.validate_post(connection, post)
        if not validation.valid:
            return PublishResult(
                success=False,
                error_code="VALIDATION_FAILED",
                error_message="; ".join(validation.errors)
            )
        
        access_token = connection.access_token
        
        # Handle media upload
        media_urns = []
        for media in post.media or []:
            if media.type in (MediaType.IMAGE, MediaType.VIDEO):
                try:
                    result = await self._upload_media(connection.access_token, media.url, media.type)
                    if result.get("media_urn"):
                        media_urns.append(result["media_urn"])
                except Exception as e:
                    logger.warning(f"Failed to upload media: {e}")
        
        # Build post content
        author_urn = f"urn:li:person:{await self._get_person_urn(connection.access_token)}"
        
        post_data = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": post.text or ""},
                    "shareMediaCategory": "NONE" if not media_urns else ("VIDEO" if any(m.type == MediaType.VIDEO for m in post.media) else "IMAGE")
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
        
        # Add media if present
        if media_urns:
            post_data["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                {
                    "status": "READY",
                    "description": {"text": post.text or ""},
                    "media": urn,
                    "title": {"text": "Content"},
                }
                for urn in media_urns
            ]
        
        try:
            result = await self._make_request("POST", "/ugcPosts", connection.access_token, json_data=post_data)
            
            external_post_id = result.get("id", "")
            external_url = f"https://www.linkedin.com/feed/update/{external_post_id}"
            
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
        """Get status of a LinkedIn post."""
        try:
            result = await self._make_request("GET", f"/ugcPosts/{external_post_id}", connection.access_token)
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
        """Delete a LinkedIn post."""
        try:
            await self._make_request("DELETE", f"/ugcPosts/{external_post_id}", connection.access_token)
            return {"success": True, "external_post_id": external_post_id}
        except Exception as e:
            error = self.normalize_error(e)
            return {"success": False, "error": error}
    
    async def get_authorization_url(self, state: str, code_challenge: Optional[str] = None, redirect_uri: str = "") -> str:
        """Generate LinkedIn OAuth authorization URL."""
        from urllib.parse import urlencode
        
        params = {
            "response_type": "code",
            "client_id": self.config.get("client_id", ""),
            "redirect_uri": redirect_uri or self.config.get("redirect_uri", ""),
            "state": state,
            "scope": " ".join([
                "r_liteprofile",
                "r_emailaddress",
                "w_member_social",
            ]),
        }
        
        # LinkedIn doesn't use PKCE standard way, but we can add it
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        query = urlencode(params)
        return f"https://www.linkedin.com/oauth/v2/authorization?{query}"
    
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.config.get("client_id", ""),
            "client_secret": self.config.get("client_secret", ""),
        }
        
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            return response.json()
    
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for access token (async wrapper)."""
        return await self.exchange_code(code, redirect_uri)
    
    async def get_authorization_url(self, state: str, code_challenge: str = None, redirect_uri: str = "") -> str:
        return await self.get_authorization_url(state, code_challenge, redirect_uri)
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()