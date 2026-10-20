# Empire OS Social Connector Integration

"""
Integration module that connects the Empire OS orchestrator/workers
with the Social Connector API for automated multi-platform publishing.
"""

import httpx
import logging
import json
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
import sys

# Add Empire OS scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

logger = logging.getLogger(__name__)


@dataclass
class SocialPost:
    """Post to be published across social platforms."""
    text: str
    media: List[Dict[str, Any]]  # [{"type": "video", "url": "...", "mime": "video/mp4"}]
    targets: List[Dict[str, str]]  # [{"provider": "linkedin", "account_id": "..."}]
    publish_at: Optional[datetime] = None
    idempotency_key: Optional[str] = None


@dataclass
class PublishResult:
    """Result of publishing to a single platform."""
    provider: str
    account_id: str
    success: bool
    external_post_id: Optional[str] = None
    external_url: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


class SocialConnectorClient:
    """Client for communicating with Social Connector API."""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "test-key"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=120.0, verify=False)
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def get_providers(self) -> List[Dict]:
        """Get available providers."""
        response = await self.client.get(f"{self.base_url}/v1/providers", headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    async def get_accounts(self) -> List[Dict]:
        """Get connected accounts."""
        response = await self.client.get(f"{self.base_url}/v1/accounts", headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    async def create_post(self, post: SocialPost) -> Dict:
        """Create a post in Social Connector."""
        payload = {
            "text": post.text,
            "media": post.media,
            "targets": post.targets,
            "idempotency_key": post.idempotency_key
        }
        if post.publish_at:
            payload["publish_at"] = post.publish_at.isoformat()
        
        response = await self.client.post(
            f"{self.base_url}/v1/posts",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def get_post_status(self, post_id: str) -> Dict:
        """Get post status."""
        response = await self.client.get(
            f"{self.base_url}/v1/posts/{post_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    async def list_posts(self, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """List posts."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        
        response = await self.client.get(
            f"{self.base_url}/v1/posts",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def publish_campaign_clips(self, 
                                     campaign_id: str,
                                     clips: List[Dict],
                                     caption: str,
                                     targets: List[Dict],
                                     publish_at: Optional[datetime] = None) -> List[PublishResult]:
        """
        Publish campaign clips to social platforms.
        
        Args:
            campaign_id: Empire OS campaign ID
            clips: List of clip info with local file paths or URLs
            caption: Post caption/text
            targets: List of target platforms/accounts
            publish_at: Optional scheduled time
            
        Returns:
            List of publish results per platform
        """
        results = []
        
        for clip in clips:
            # Create post for each clip
            media = []
            if clip.get("local_path"):
                # In production, upload to storage and get public URL
                # For now, assume clips are accessible via local server or pre-uploaded
                media.append({
                    "type": "video" if clip.get("type") == "video" else "image",
                    "url": clip.get("url", clip.get("local_path")),
                    "mime": clip.get("mime", "video/mp4"),
                    "sha256": clip.get("sha256", "")
                })
            
            post = SocialPost(
                text=caption,
                media=media,
                targets=targets,
                publish_at=publish_at,
                idempotency_key=f"{campaign_id}_{clip.get('id', 'clip')}"
            )
            
            try:
                created = await self.create_post(post)
                post_id = created.get("id")
                
                # Wait for processing (poll)
                if post_id:
                    result = await self._wait_for_publish(post_id, targets)
                    results.extend(result)
            except Exception as e:
                logger.error(f"Failed to create post for clip {clip.get('id')}: {e}")
                for target in targets:
                    results.append(PublishResult(
                        provider=target.get("provider"),
                        account_id=target.get("account_id"),
                        success=False,
                        error=str(e)
                    ))
        
        return results
    
    async def _wait_for_publish(self, post_id: str, targets: List[Dict], 
                                max_wait: int = 300) -> List[PublishResult]:
        """Poll post status until published or failed."""
        results = []
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < max_wait:
            try:
                status = await self.get_post_status(post_id)
                post_status = status.get("status", "")
                
                if post_status in ["published", "failed"]:
                    # Extract results per target
                    for target in targets:
                        # In real implementation, parse per-target status
                        results.append(PublishResult(
                            provider=target.get("provider"),
                            account_id=target.get("account_id"),
                            success=post_status == "published",
                            external_post_id=status.get("external_post_id"),
                            external_url=status.get("external_url"),
                            error=status.get("error") if post_status == "failed" else None,
                            raw_response=status
                        ))
                    break
                
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error polling post {post_id}: {e}")
                await asyncio.sleep(5)
        
        return results
    
    async def close(self):
        await self.client.aclose()


class EmpireSocialPublisher:
    """
    High-level publisher that integrates Empire OS campaign flow
    with Social Connector for automated multi-platform publishing.
    """
    
    def __init__(self, social_connector_url: str = "http://localhost:8000", 
                 api_key: str = "test-key"):
        self.client = SocialConnectorClient(social_connector_url, api_key)
        self.default_targets = []  # Configured per campaign
    
    async def publish_campaign(self, campaign: Dict, clips: List[Dict]) -> Dict[str, Any]:
        """
        Publish a completed campaign to all configured platforms.
        
        Args:
            campaign: Campaign dict with id, caption, targets, schedule
            clips: List of processed clips ready for publishing
            
        Returns:
            Summary of publishing results
        """
        campaign_id = campaign.get("id", "unknown")
        caption = campaign.get("caption", "")
        targets = campaign.get("targets", self.default_targets)
        publish_at = campaign.get("publish_at")
        
        if not targets:
            # Default: publish to all connected accounts
            accounts = await self.client.get_accounts()
            targets = [
                {"provider": acc["provider"], "account_id": acc["id"]}
                for acc in accounts
            ]
        
        logger.info(f"Publishing campaign {campaign_id} to {len(targets)} targets")
        
        results = await self.client.publish_campaign_clips(
            campaign_id=campaign_id,
            clips=clips,
            caption=caption,
            targets=targets,
            publish_at=publish_at
        )
        
        # Summarize
        by_provider = {}
        for r in results:
            if r.provider not in by_provider:
                by_provider[r.provider] = {"success": 0, "failed": 0, "details": []}
            if r.success:
                by_provider[r.provider]["success"] += 1
            else:
                by_provider[r.provider]["failed"] += 1
            by_provider[r.provider]["details"].append(asdict(r))
        
        return {
            "campaign_id": campaign_id,
            "total_clips": len(clips),
            "total_targets": len(targets),
            "results": by_provider,
            "timestamp": datetime.now().isoformat()
        }
    
    async def close(self):
        await self.client.close()


async def test_integration():
    """Test the integration with Social Connector."""
    publisher = EmpireSocialPublisher()
    
    try:
        # Test getting providers
        providers = await publisher.client.get_providers()
        print(f"Available providers: {[p['id'] for p in providers]}")
        
        # Test getting accounts
        accounts = await publisher.client.get_accounts()
        print(f"Connected accounts: {accounts}")
        
        # Test creating a post
        test_post = SocialPost(
            text="Test post from Empire OS integration",
            media=[],
            targets=[{"provider": "linkedin", "account_id": "test"}],
            idempotency_key="test-empire-123"
        )
        
        created = await publisher.client.create_post(test_post)
        print(f"Created post: {created}")
        
        print("Integration test passed!")
        
    finally:
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(test_integration())