# Social Publishing Skill
# Publishes clips to social platforms via official APIs

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pathlib import Path
import logging
import asyncio
import httpx
import json

from project.db.models import (
    Session, Campaign, Clip, SocialAccount, SocialPost, SocialPostStatus, SocialPlatform, init_db
)
from project.config.settings import get_settings
from project.db.crypto import get_token_encryption

logger = logging.getLogger(__name__)


class SocialPublishingSkill:
    """Skill for publishing clips to social platforms."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
        self.encryption = get_token_encryption()
        self.storage_dir = Path(self.settings.storage_dir)
        self.client = httpx.AsyncClient(timeout=120.0)
    
    async def publish_clip(self, clip_id: str, platform: str, account_id: str) -> Dict[str, Any]:
        """Publish a clip to a specific platform using the specified account."""
        clip = self.db.query(Clip).filter(Clip.id == clip_id).first()
        if not clip:
            return {"success": False, "error": f"Clip {clip_id} not found"}
        
        account = self.db.query(SocialAccount).filter(SocialAccount.id == account_id).first()
        if not account:
            return {"success": False, "error": f"Account {account_id} not found"}
        
        if account.platform.value != platform:
            return {"success": False, "error": f"Account platform mismatch: {account.platform.value} != {platform}"}
        
        # Check token health
        access_token = await self._get_valid_token(account)
        if not access_token:
            return {"success": False, "error": "Failed to get valid access token"}
        
        # Get caption
        caption = self.db.query(Caption).filter(
            Caption.clip_id == clip_id,
            Caption.platform == platform
        ).first()
        
        caption_text = caption.text if caption else ""
        
        # Get video file
        video_path = self.storage_dir / clip.clip_path
        if not video_path.exists():
            return {"success": False, "error": f"Video file not found: {video_path}"}
        
        # Dispatch to platform-specific publisher
        platform_method = getattr(self, f"_publish_{platform.lower()}", None)
        if not platform_method:
            return {"success": False, "error": f"No publisher for platform: {platform}"}
        
        try:
            result = await platform_method(clip, account, access_token, caption_text, video_path)
            return result
        except Exception as e:
            logger.error(f"Publish error for {platform}: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_valid_token(self, account: SocialAccount) -> Optional[str]:
        """Get valid access token, refreshing if needed."""
        if account.token_expires_at and account.token_expires_at < datetime.now(timezone.utc):
            return await self._refresh_token(account)
        
        return self.encryption.decrypt(account.access_token_encrypted)
    
    async def _refresh_token(self, account: SocialAccount) -> Optional[str]:
        """Refresh OAuth token based on platform."""
        refresh_token = self.encryption.decrypt(account.refresh_token_encrypted) if account.refresh_token_encrypted else None
        if not refresh_token:
            return None
        
        token_data = None
        
        if account.platform == SocialPlatform.TIKTOK:
            token_data = await self._refresh_tiktok(refresh_token)
        elif account.platform == SocialPlatform.INSTAGRAM:
            token_data = await self._refresh_instagram(refresh_token)
        elif account.platform == SocialPlatform.FACEBOOK:
            token_data = await self._refresh_facebook(refresh_token)
        elif account.platform == SocialPlatform.YOUTUBE:
            token_data = await self._refresh_youtube(refresh_token)
        elif account.platform == SocialPlatform.X:
            token_data = await self._refresh_x(refresh_token)
        
        if token_data:
            account.access_token_encrypted = self.encryption.encrypt(token_data["access_token"])
            if token_data.get("refresh_token"):
                account.refresh_token_encrypted = self.encryption.encrypt(token_data["refresh_token"])
            account.token_expires_at = token_data["expires_at"]
            self.db.commit()
            return token_data["access_token"]
        
        return None
    
    # Token refresh methods
    async def _refresh_tiktok(self, refresh_token: str) -> Optional[Dict]:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_key": self.settings.tiktok_client_key,
            "client_secret": self.settings.tiktok_client_secret,
        }
        response = await self.client.post("https://open.tiktokapis.com/v2/oauth/token/", data=data)
        if response.status_code == 200:
            data = response.json()
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 7200))
            }
        return None
    
    async def _refresh_instagram(self, refresh_token: str) -> Optional[Dict]:
        # Instagram uses Facebook's token refresh
        return await self._refresh_facebook(refresh_token)
    
    async def _refresh_facebook(self, refresh_token: str) -> Optional[Dict]:
        data = {
            "grant_type": "fb_exchange_token",
            "client_id": self.settings.facebook_client_id,
            "client_secret": self.settings.facebook_client_secret,
            "fb_exchange_token": refresh_token,
        }
        response = await self.client.post("https://graph.facebook.com/v18.0/oauth/access_token", data=data)
        if response.status_code == 200:
            data = response.json()
            return {
                "access_token": data["access_token"],
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 5184000))
            }
        return None
    
    async def _refresh_youtube(self, refresh_token: str) -> Optional[Dict]:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.settings.youtube_client_id,
            "client_secret": self.settings.youtube_client_secret,
        }
        response = await self.client.post("https://oauth2.googleapis.com/token", data=data)
        if response.status_code == 200:
            data = response.json()
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
            }
        return None
    
    async def _refresh_x(self, refresh_token: str) -> Optional[Dict]:
        import base64
        credentials = base64.b64encode(f"{self.settings.x_client_id}:{self.settings.x_client_secret}".encode()).decode()
        headers = {"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        response = await self.client.post("https://api.x.com/2/oauth2/token", data=data, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 7200))
            }
        return None
    
    # Platform-specific publishers
    async def _publish_tiktok(self, clip: Clip, account: SocialAccount, token: str, caption: str, video_path: Path) -> Dict:
        """Publish to TikTok using Direct Post API."""
        # 1. Initialize upload
        init_response = await self.client.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "post_info": {
                    "title": caption[:2200],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_stitch": False,
                    "disable_comment": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_path.stat().st_size,
                    "chunk_size": 10485760,  # 10MB chunks
                }
            }
        )
        
        if init_response.status_code != 200:
            return {"success": False, "error": f"Upload init failed: {init_response.text}"}
        
        init_data = init_response.json()["data"]
        upload_url = init_data["upload_url"]
        video_id = init_data["video_id"]
        
        # 2. Upload video in chunks
        chunk_size = 10485760
        with open(video_path, "rb") as f:
            chunk_index = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                
                upload_response = await self.client.put(
                    upload_url,
                    content=chunk,
                    headers={"Content-Type": "video/mp4", "Content-Range": f"bytes {chunk_index*chunk_size}-{(chunk_index+1)*chunk_size-1}/{video_path.stat().st_size}"}
                )
                
                if upload_response.status_code not in [200, 201]:
                    return {"success": False, "error": f"Chunk upload failed: {upload_response.text}"}
                
                chunk_index += 1
        
        # 3. Finalize and publish
        publish_response = await self.client.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "post_info": {
                    "title": caption[:2200],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_id": video_id,
                }
            }
        )
        
        if publish_response.status_code != 200:
            return {"success": False, "error": f"Publish failed: {publish_response.text}"}
        
        publish_data = publish_response.json()["data"]
        post_id = publish_data["publish_id"]
        post_url = f"https://www.tiktok.com/@{account.username}/video/{post_id}"
        
        # Save social post record
        social_post = SocialPost(
            clip_id=clip.id,
            campaign_id=clip.campaign_id,
            social_account_id=account.id,
            platform=SocialPlatform.TIKTOK,
            post_url=post_url,
            platform_post_id=post_id,
            status=SocialPostStatus.PUBLISHED,
            published_at=datetime.now(timezone.utc),
            idempotency_key=f"publish:tiktok:{clip.id}:{account.id}:{datetime.now().timestamp()}"
        )
        self.db.add(social_post)
        self.db.commit()
        
        return {"success": True, "post_id": post_id, "post_url": post_url}
    
    async def _publish_instagram(self, clip: Clip, account: SocialAccount, token: str, caption: str, video_path: Path) -> Dict:
        """Publish to Instagram Reels via Graph API."""
        # 1. Create media container
        container_response = await self.client.post(
            f"https://graph.facebook.com/v18.0/{account.external_id}/media",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "media_type": "REELS",
                "video_url": f"file://{video_path.absolute()}",  # For demo; production needs public URL
                "caption": caption[:2200],
                "share_to_feed": "true",
            }
        )
        
        if container_response.status_code != 200:
            return {"success": False, "error": f"Container creation failed: {container_response.text}"}
        
        container_id = container_response.json()["id"]
        
        # 2. Poll container status
        for _ in range(30):
            status_response = await self.client.get(
                f"https://graph.facebook.com/v18.0/{container_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"fields": "status_code"}
            )
            if status_response.status_code == 200:
                status = status_response.json().get("status_code")
                if status == "FINISHED":
                    break
                elif status == "ERROR":
                    return {"success": False, "error": "Container processing failed"}
            await asyncio.sleep(2)
        
        # 3. Publish
        publish_response = await self.client.post(
            f"https://graph.facebook.com/v18.0/{account.external_id}/media_publish",
            headers={"Authorization": f"Bearer {token}"},
            data={"creation_id": container_id}
        )
        
        if publish_response.status_code != 200:
            return {"success": False, "error": f"Publish failed: {publish_response.text}"}
        
        publish_data = publish_response.json()
        post_id = publish_data["id"]
        
        # Get permalink
        permalink_response = await self.client.get(
            f"https://graph.facebook.com/v18.0/{post_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "permalink"}
        )
        post_url = permalink_response.json().get("permalink", f"https://instagram.com/p/{post_id}")
        
        social_post = SocialPost(
            clip_id=clip.id,
            campaign_id=clip.campaign_id,
            social_account_id=account.id,
            platform=SocialPlatform.INSTAGRAM,
            post_url=post_url,
            platform_post_id=post_id,
            status=SocialPostStatus.PUBLISHED,
            published_at=datetime.now(timezone.utc),
            idempotency_key=f"publish:instagram:{clip.id}:{account.id}:{datetime.now().timestamp()}"
        )
        self.db.add(social_post)
        self.db.commit()
        
        return {"success": True, "post_id": post_id, "post_url": post_url}
    
    async def _publish_facebook(self, clip: Clip, account: SocialAccount, token: str, caption: str, video_path: Path) -> Dict:
        """Publish to Facebook Page via Graph API."""
        # Similar to Instagram but for Pages
        # Use /{page_id}/videos endpoint
        publish_response = await self.client.post(
            f"https://graph-video.facebook.com/v18.0/{account.external_id}/videos",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "description": caption[:63206],
                "file_url": f"file://{video_path.absolute()}",  # Production needs public URL
            }
        )
        
        if publish_response.status_code != 200:
            return {"success": False, "error": f"Publish failed: {publish_response.text}"}
        
        publish_data = publish_response.json()
        post_id = publish_data["id"]
        post_url = f"https://facebook.com/{post_id}"
        
        social_post = SocialPost(
            clip_id=clip.id,
            campaign_id=clip.campaign_id,
            social_account_id=account.id,
            platform=SocialPlatform.FACEBOOK,
            post_url=post_url,
            platform_post_id=post_id,
            status=SocialPostStatus.PUBLISHED,
            published_at=datetime.now(timezone.utc),
            idempotency_key=f"publish:facebook:{clip.id}:{account.id}:{datetime.now().timestamp()}"
        )
        self.db.add(social_post)
        self.db.commit()
        
        return {"success": True, "post_id": post_id, "post_url": post_url}
    
    async def _publish_youtube(self, clip: Clip, account: SocialAccount, token: str, caption: str, video_path: Path) -> Dict:
        """Publish to YouTube via Data API v3 (resumable upload)."""
        # 1. Initiate resumable upload
        init_response = await self.client.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(video_path.stat().st_size),
            },
            json={
                "snippet": {
                    "title": caption[:100],
                    "description": caption,
                    "categoryId": "22",  # People & Blogs
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                }
            }
        )
        
        if init_response.status_code != 200:
            return {"success": False, "error": f"Upload init failed: {init_response.text}"}
        
        upload_url = init_response.headers.get("Location")
        if not upload_url:
            return {"success": False, "error": "No upload URL in response"}
        
        # 2. Upload video in chunks (256KB multiples)
        chunk_size = 262144  # 256KB
        total_size = video_path.stat().st_size
        
        with open(video_path, "rb") as f:
            bytes_sent = 0
            while bytes_sent < total_size:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                
                end_byte = bytes_sent + len(chunk) - 1
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {bytes_sent}-{end_byte}/{total_size}",
                    "Content-Length": str(len(chunk)),
                }
                
                upload_response = await self.client.put(upload_url, content=chunk, headers=headers)
                
                if upload_response.status_code not in [200, 201, 308]:
                    return {"success": False, "error": f"Chunk upload failed: {upload_response.text}"}
                
                bytes_sent += len(chunk)
                
                # Check for final response
                if upload_response.status_code in [200, 201]:
                    final_data = upload_response.json()
                    break
        
        video_id = final_data["id"]
        post_url = f"https://www.youtube.com/watch?v={video_id}"
        
        social_post = SocialPost(
            clip_id=clip.id,
            campaign_id=clip.campaign_id,
            social_account_id=account.id,
            platform=SocialPlatform.YOUTUBE,
            post_url=post_url,
            platform_post_id=video_id,
            status=SocialPostStatus.PUBLISHED,
            published_at=datetime.now(timezone.utc),
            idempotency_key=f"publish:youtube:{clip.id}:{account.id}:{datetime.now().timestamp()}"
        )
        self.db.add(social_post)
        self.db.commit()
        
        return {"success": True, "post_id": video_id, "post_url": post_url}
    
    async def _publish_x(self, clip: Clip, account: SocialAccount, token: str, caption: str, video_path: Path) -> Dict:
        """Publish to X (Twitter) via API v2."""
        # 1. Upload media (chunked)
        # INIT
        init_response = await self.client.post(
            "https://api.x.com/2/media/upload",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "command": "INIT",
                "media_type": "video/mp4",
                "total_bytes": str(video_path.stat().st_size),
                "media_category": "tweet_video",
            }
        )
        
        if init_response.status_code != 200:
            return {"success": False, "error": f"Media init failed: {init_response.text}"}
        
        media_id = init_response.json()["data"]["id"]
        
        # 2. APPEND chunks
        chunk_size = 5242880  # 5MB
        with open(video_path, "rb") as f:
            segment_index = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                
                append_response = await self.client.post(
                    "https://api.x.com/2/media/upload",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"media": chunk},
                    data={
                        "command": "APPEND",
                        "media_id": media_id,
                        "segment_index": str(segment_index),
                    }
                )
                
                if append_response.status_code != 200:
                    return {"success": False, "error": f"Append failed: {append_response.text}"}
                
                segment_index += 1
        
        # 3. FINALIZE
        finalize_response = await self.client.post(
            "https://api.x.com/2/media/upload",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"command": "FINALIZE", "media_id": media_id}
        )
        
        if finalize_response.status_code != 200:
            return {"success": False, "error": f"Finalize failed: {finalize_response.text}"}
        
        # 4. Poll processing status
        for _ in range(30):
            status_response = await self.client.get(
                "https://api.x.com/2/media/upload",
                headers={"Authorization": f"Bearer {token}"},
                params={"command": "STATUS", "media_id": media_id}
            )
            if status_response.status_code == 200:
                status = status_response.json()
                if status.get("processing_info", {}).get("state") == "succeeded":
                    break
                elif status.get("processing_info", {}).get("state") == "failed":
                    return {"success": False, "error": "Video processing failed"}
            await asyncio.sleep(2)
        
        # 5. Create tweet
        tweet_response = await self.client.post(
            "https://api.x.com/2/tweets",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"text": caption[:280], "media": {"media_ids": [media_id]}}
        )
        
        if tweet_response.status_code != 200:
            return {"success": False, "error": f"Tweet failed: {tweet_response.text}"}
        
        tweet_data = tweet_response.json()["data"]
        tweet_id = tweet_data["id"]
        post_url = f"https://x.com/{account.username}/status/{tweet_id}"
        
        social_post = SocialPost(
            clip_id=clip.id,
            campaign_id=clip.campaign_id,
            social_account_id=account.id,
            platform=SocialPlatform.X,
            post_url=post_url,
            platform_post_id=tweet_id,
            status=SocialPostStatus.PUBLISHED,
            published_at=datetime.now(timezone.utc),
            idempotency_key=f"publish:x:{clip.id}:{account.id}:{datetime.now().timestamp()}"
        )
        self.db.add(social_post)
        self.db.commit()
        
        return {"success": True, "post_id": tweet_id, "post_url": post_url}


async def publish_clip(clip_id: str, platform: str, account_id: str) -> Dict[str, Any]:
    """Entry point for publishing a clip."""
    skill = SocialPublishingSkill()
    return await skill.publish_clip(clip_id, platform, account_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("SocialPublishingSkill ready")