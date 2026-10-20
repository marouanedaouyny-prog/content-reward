# Analytics Skill
# Syncs views and engagement metrics from social platforms

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging
import asyncio
import httpx

from project.db.models import (
    Session, Submission, SocialPost, AnalyticsSnapshot, SocialPlatform, init_db
)
from project.config.settings import get_settings
from project.db.crypto import get_token_encryption

logger = logging.getLogger(__name__)


class AnalyticsSkill:
    """Skill for syncing analytics from social platforms."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
        self.encryption = get_token_encryption()
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def sync_submission(self, submission_id: str) -> List[AnalyticsSnapshot]:
        """Sync analytics for a single submission."""
        submission = self.db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise ValueError(f"Submission {submission_id} not found")
        
        social_post = self.db.query(SocialPost).filter(
            SocialPost.id == submission.social_post_id
        ).first()
        
        if not social_post:
            logger.warning(f"No social post for submission {submission_id}")
            return []
        
        account = self.db.query(SocialAccount).filter(
            SocialAccount.id == social_post.social_account_id
        ).first()
        
        if not account:
            logger.warning(f"No account for social post {social_post.id}")
            return []
        
        # Get valid token
        access_token = await self._get_valid_token(account)
        if not access_token:
            logger.warning(f"Failed to get token for account {account.id}")
            return []
        
        # Dispatch to platform-specific sync
        sync_method = getattr(self, f"_sync_{submission.platform.value.lower()}", None)
        if not sync_method:
            logger.warning(f"No analytics sync for platform: {submission.platform.value}")
            return []
        
        try:
            snapshot = await sync_method(social_post, account, access_token)
            return [snapshot] if snapshot else []
        except Exception as e:
            logger.error(f"Analytics sync error for {submission.platform.value}: {e}")
            return []
    
    async def _get_valid_token(self, account: 'SocialAccount') -> Optional[str]:
        """Get valid access token, refreshing if needed."""
        # Import here to avoid circular imports
        from project.db.models import SocialAccount
        
        if account.token_expires_at and account.token_expires_at < datetime.now(timezone.utc):
            # Would need to refresh - simplified for now
            pass
        
        return self.encryption.decrypt(account.access_token_encrypted)
    
    async def _sync_tiktok(self, social_post: SocialPost, account: 'SocialAccount', token: str) -> Optional[AnalyticsSnapshot]:
        """Sync TikTok analytics - MANUAL_CHECKPOINT required."""
        # TikTok has no official analytics API for video views
        # This is a MANUAL_CHECKPOINT - creator must provide screenshot
        logger.info(f"TikTok analytics for {social_post.platform_post_id}: MANUAL_CHECKPOINT required")
        
        # Create placeholder snapshot indicating manual verification needed
        snapshot = AnalyticsSnapshot(
            submission_id=social_post.id,  # This would need submission_id lookup
            social_post_id=social_post.id,
            platform=SocialPlatform.TIKTOK,
            snapshot_time=datetime.now(timezone.utc),
            data_source="MANUAL",
            views=0,
            likes=0,
            comments=0,
            shares=0,
            raw_data={"note": "TikTok requires manual screenshot verification"}
        )
        self.db.add(snapshot)
        self.db.commit()
        
        return snapshot
    
    async def _sync_instagram(self, social_post: SocialPost, account: 'SocialAccount', token: str) -> Optional[AnalyticsSnapshot]:
        """Sync Instagram Reels insights via Graph API."""
        try:
            # Get media insights
            response = await self.client.get(
                f"https://graph.facebook.com/v18.0/{social_post.platform_post_id}/insights",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "metric": "views,likes,comments,shares,reach,plays",
                    "period": "lifetime"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Instagram insights failed: {response.text}")
                return None
            
            data = response.json().get("data", [])
            metrics = {item["name"]: item["values"][0]["value"] for item in data}
            
            snapshot = AnalyticsSnapshot(
                social_post_id=social_post.id,
                platform=SocialPlatform.INSTAGRAM,
                snapshot_time=datetime.now(timezone.utc),
                data_source="API",
                views=metrics.get("views", 0),
                likes=metrics.get("likes", 0),
                comments=metrics.get("comments", 0),
                shares=metrics.get("shares", 0),
                reach=metrics.get("reach"),
                video_views_3s=metrics.get("video_views_3s"),
                raw_data=metrics
            )
            self.db.add(snapshot)
            self.db.commit()
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Instagram analytics sync failed: {e}")
            return None
    
    async def _sync_facebook(self, social_post: SocialPost, account: 'SocialAccount', token: str) -> Optional[AnalyticsSnapshot]:
        """Sync Facebook video insights via Graph API."""
        try:
            response = await self.client.get(
                f"https://graph.facebook.com/v18.0/{social_post.platform_post_id}/video_insights",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "metric": "total_video_views,total_video_views_unique,total_video_complete_views,total_video_10s_views,total_video_avg_time_watched,total_video_impressions"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Facebook insights failed: {response.text}")
                return None
            
            data = response.json().get("data", [])
            metrics = {item["name"]: item["values"][0]["value"] for item in data}
            
            snapshot = AnalyticsSnapshot(
                social_post_id=social_post.id,
                platform=SocialPlatform.FACEBOOK,
                snapshot_time=datetime.now(timezone.utc),
                data_source="API",
                views=metrics.get("total_video_views", 0),
                video_views_complete=metrics.get("total_video_complete_views"),
                avg_watch_time=metrics.get("total_video_avg_time_watched"),
                impressions=metrics.get("total_video_impressions"),
                raw_data=metrics
            )
            self.db.add(snapshot)
            self.db.commit()
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Facebook analytics sync failed: {e}")
            return None
    
    async def _sync_youtube(self, social_post: SocialPost, account: 'SocialAccount', token: str) -> Optional[AnalyticsSnapshot]:
        """Sync YouTube analytics via Data API (real-time) + Analytics API (detailed)."""
        try:
            # Real-time stats via Data API
            response = await self.client.get(
                "https://www.googleapis.com/youtube/v3/videos",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "part": "statistics",
                    "id": social_post.platform_post_id
                }
            )
            
            if response.status_code != 200:
                logger.error(f"YouTube Data API failed: {response.text}")
                return None
            
            items = response.json().get("items", [])
            if not items:
                return None
            
            stats = items[0].get("statistics", {})
            
            snapshot = AnalyticsSnapshot(
                social_post_id=social_post.id,
                platform=SocialPlatform.YOUTUBE,
                snapshot_time=datetime.now(timezone.utc),
                data_source="API",
                views=int(stats.get("viewCount", 0)),
                likes=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                raw_data=stats
            )
            self.db.add(snapshot)
            self.db.commit()
            
            return snapshot
            
        except Exception as e:
            logger.error(f"YouTube analytics sync failed: {e}")
            return None
    
    async def _sync_x(self, social_post: SocialPost, account: 'SocialAccount', token: str) -> Optional[AnalyticsSnapshot]:
        """Sync X (Twitter) metrics via API v2."""
        try:
            # Public metrics (always available)
            response = await self.client.get(
                f"https://api.x.com/2/tweets/{social_post.platform_post_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "tweet.fields": "public_metrics,non_public_metrics,organic_metrics,promoted_metrics"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"X metrics failed: {response.text}")
                return None
            
            data = response.json().get("data", {})
            public = data.get("public_metrics", {})
            non_public = data.get("non_public_metrics", {})
            organic = data.get("organic_metrics", {})
            promoted = data.get("promoted_metrics", {})
            
            # Combine metrics
            views = public.get("impression_count", 0)
            if "impression_count" in non_public:
                views = non_public["impression_count"]
            elif "impression_count" in organic:
                views = organic["impression_count"]
            
            snapshot = AnalyticsSnapshot(
                social_post_id=social_post.id,
                platform=SocialPlatform.X,
                snapshot_time=datetime.now(timezone.utc),
                data_source="API",
                views=views,
                likes=public.get("like_count", 0),
                comments=public.get("reply_count", 0),
                shares=public.get("retweet_count", 0),
                raw_data={
                    "public_metrics": public,
                    "non_public_metrics": non_public,
                    "organic_metrics": organic,
                    "promoted_metrics": promoted
                }
            )
            self.db.add(snapshot)
            self.db.commit()
            
            return snapshot
            
        except Exception as e:
            logger.error(f"X analytics sync failed: {e}")
            return None
    
    async def sync_all_pending(self, hours_back: int = 24) -> Dict[str, int]:
        """Sync analytics for all submissions in tracking state."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        submissions = self.db.query(Submission).filter(
            Submission.status.in_(["VALIDATING", "TRACKING"]),
            Submission.updated_at > cutoff
        ).all()
        
        results = {"synced": 0, "failed": 0, "manual_required": 0}
        
        for submission in submissions:
            try:
                snapshots = await self.sync_submission(submission.id)
                if snapshots:
                    # Check if any are manual
                    if any(s.data_source == "MANUAL" for s in snapshots):
                        results["manual_required"] += 1
                    else:
                        results["synced"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                logger.error(f"Failed to sync submission {submission.id}: {e}")
                results["failed"] += 1
        
        return results


async def sync_analytics(submission_id: str = None) -> List[AnalyticsSnapshot]:
    """Entry point for analytics sync."""
    skill = AnalyticsSkill()
    if submission_id:
        return await skill.sync_submission(submission_id)
    else:
        return await skill.sync_all_pending()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("AnalyticsSkill ready")