# Submission Skill
# Submits clip URLs to Content Rewards platform

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from project.db.models import (
    Session, Submission, SocialPost, SubmissionStatus, Campaign, Clip, init_db
)
from project.config.settings import get_settings

logger = logging.getLogger(__name__)


class SubmissionSkill:
    """Skill for submitting clips to Content Rewards platform."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
    
    def submit(self, campaign_id: str, clip_id: str, platform: str, 
               creator_id: str) -> Dict[str, Any]:
        """Submit a published clip URL to Content Rewards."""
        campaign = self.db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            return {"success": False, "error": f"Campaign {campaign_id} not found"}
        
        clip = self.db.query(Clip).filter(Clip.id == clip_id).first()
        if not clip:
            return {"success": False, "error": f"Clip {clip_id} not found"}
        
        # Get published social post
        social_post = self.db.query(SocialPost).filter(
            SocialPost.clip_id == clip_id,
            SocialPost.platform == platform,
            SocialPost.status == "PUBLISHED"
        ).first()
        
        if not social_post:
            return {"success": False, "error": f"No published post found for clip {clip_id} on {platform}"}
        
        # Check if pre-post review is required
        if campaign.pre_post_review_enabled:
            # Would need draft approval first
            if not self._check_draft_approved(campaign_id, clip_id):
                return {"success": False, "error": "Pre-post review required but draft not approved"}
        
        # Create submission record
        idempotency_key = f"submit:{campaign_id}:{creator_id}:{hash(social_post.post_url)}"
        
        existing = self.db.query(Submission).filter(
            Submission.idempotency_key == idempotency_key
        ).first()
        
        if existing:
            logger.info(f"Submission already exists for {idempotency_key}")
            return {"success": True, "submission_id": existing.id, "status": existing.status.value}
        
        submission = Submission(
            campaign_id=campaign_id,
            creator_id=creator_id,
            clip_id=clip_id,
            social_post_id=social_post.id,
            platform=platform,
            clip_url=social_post.post_url,
            clip_id_platform=social_post.platform_post_id,
            status=SubmissionStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key
        )
        self.db.add(submission)
        self.db.commit()
        
        logger.info(f"Submitted clip {clip_id} to campaign {campaign.external_campaign_id} on {platform}")
        
        # In production: browser automation to submit on CR platform
        # self._submit_to_cr_platform(submission)
        
        return {
            "success": True,
            "submission_id": submission.id,
            "status": "SUBMITTED",
            "clip_url": social_post.post_url
        }
    
    def _check_draft_approved(self, campaign_id: str, clip_id: str) -> bool:
        """Check if draft was approved for pre-post review."""
        # In production: query CR platform for draft approval status
        return True  # Simplified for now
    
    def _submit_to_cr_platform(self, submission: Submission):
        """Browser automation to submit on CR platform."""
        # Would use Playwright MCP to:
        # 1. Login to CR
        # 2. Navigate to campaign
        # 3. Click "Submit Video"
        # 4. Paste URL
        # 5. Submit
        pass


def submit_clip(campaign_id: str, clip_id: str, platform: str, creator_id: str) -> Dict[str, Any]:
    """Entry point for submitting a clip."""
    skill = SubmissionSkill()
    return skill.submit(campaign_id, clip_id, platform, creator_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("SubmissionSkill ready")