# Payout Tracking Skill
# Tracks validation windows and payouts from Content Rewards

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging
import asyncio

from project.db.models import (
    Session, Submission, Payout, PayoutStatus, SubmissionStatus, Campaign, init_db
)
from project.config.settings import get_settings

logger = logging.getLogger(__name__)


class PayoutTrackingSkill:
    """Skill for tracking validation windows and payouts."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
    
    def check_payouts(self) -> Dict[str, int]:
        """Check validation windows and update payout statuses."""
        results = {"checked": 0, "paid": 0, "clawback": 0, "still_validating": 0}
        
        # Get submissions in VALIDATING or TRACKING state
        submissions = self.db.query(Submission).filter(
            Submission.status.in_([SubmissionStatus.VALIDATING, SubmissionStatus.TRACKING])
        ).all()
        
        for submission in submissions:
            try:
                result = self._check_submission_payout(submission)
                results["checked"] += 1
                
                if result == "PAID":
                    results["paid"] += 1
                elif result == "CLAWBACK":
                    results["clawback"] += 1
                else:
                    results["still_validating"] += 1
                    
            except Exception as e:
                logger.error(f"Failed to check payout for submission {submission.id}: {e}")
        
        return results
    
    def _check_submission_payout(self, submission: Submission) -> str:
        """Check if a submission's validation window has ended and payout is ready."""
        if submission.status == SubmissionStatus.VALIDATING:
            # Check if validation window has ended
            if submission.validation_end and submission.validation_end <= datetime.now(timezone.utc):
                # Window ended - check if CR has paid out
                # In production: query CR platform or wait for webhook
                # For now: simulate payout
                return self._process_payout(submission)
            else:
                # Still in validation window
                if submission.status != SubmissionStatus.TRACKING:
                    submission.status = SubmissionStatus.TRACKING
                    self.db.commit()
                return "TRACKING"
        
        elif submission.status == SubmissionStatus.TRACKING:
            # Check if validation window ended
            if submission.validation_end and submission.validation_end <= datetime.now(timezone.utc):
                return self._process_payout(submission)
            return "TRACKING"
        
        return "UNKNOWN"
    
    def _process_payout(self, submission: Submission) -> str:
        """Process payout after validation window."""
        # Calculate expected payout based on campaign type
        campaign = self.db.query(Campaign).filter(Campaign.id == submission.campaign_id).first()
        if not campaign:
            logger.error(f"Campaign {submission.campaign_id} not found for submission {submission.id}")
            return "ERROR"
        
        payout_amount = self._calculate_payout(submission, campaign)
        
        if payout_amount > 0:
            # Create payout record
            payout = Payout(
                submission_id=submission.id,
                campaign_id=submission.campaign_id,
                creator_id=submission.creator_id,
                amount=payout_amount,
                fee_amount=payout_amount * 0.10,  # 10% CR fee (simplified)
                fee_percentage=10.0,
                net_amount=payout_amount * 0.90,
                status=PayoutStatus.SETTLED,
                settled_at=datetime.now(timezone.utc),
                idempotency_key=f"payout:{submission.id}:{submission.validation_end.isoformat()}"
            )
            self.db.add(payout)
            
            # Update submission
            submission.status = SubmissionStatus.PAID
            submission.payout_status = PayoutStatus.SETTLED
            submission.payout_amount = payout_amount
            submission.payout_settled_at = datetime.now(timezone.utc)
            
            self.db.commit()
            logger.info(f"Payout processed for submission {submission.id}: ${payout_amount:.2f}")
            return "PAID"
        else:
            # No payout due (e.g., min views not met)
            submission.status = SubmissionStatus.REJECTED
            submission.rejection_reason = "Validation failed: minimum requirements not met"
            self.db.commit()
            logger.info(f"No payout for submission {submission.id}: requirements not met")
            return "REJECTED"
    
    def _calculate_payout(self, submission: Submission, campaign: Campaign) -> float:
        """Calculate payout based on campaign type and verified views."""
        if campaign.campaign_type.value == "CPM":
            # CPM: per 1000 verified views
            rate = campaign.rate_cpm or 0
            payout = (submission.verified_views / 1000) * rate
            
            # Apply min/max per clip
            if campaign.max_payout_per_clip:
                payout = min(payout, campaign.max_payout_per_clip)
            
            # Min payout check (if campaign has min_views threshold)
            if campaign.min_views and submission.verified_views < campaign.min_views:
                return 0.0
            
            return round(payout, 2)
        
        elif campaign.campaign_type.value == "PER_POST":
            # Flat rate per approved post
            rate = campaign.rate_per_post or 0
            
            # Check min views if specified
            if campaign.min_views and submission.verified_views < campaign.min_views:
                return 0.0
            
            return round(rate, 2)
        
        elif campaign.campaign_type.value == "RETAINER":
            # Per cycle - handled differently
            rate = campaign.rate_retainer_cycle or 0
            return round(rate, 2)
        
        return 0.0
    
    def check_clawbacks(self) -> int:
        """Check for clawbacks (fraud flags upheld after payout)."""
        # In production: query CR for fraud flags on paid submissions
        # For now: placeholder
        clawback_count = 0
        
        paid_submissions = self.db.query(Submission).filter(
            Submission.status == SubmissionStatus.PAID
        ).all()
        
        for submission in paid_submissions:
            # Check if fraud flag was upheld post-payout
            # This would come from CR platform
            pass
        
        return clawback_count
    
    def get_whop_withdrawal_status(self, payout_id: str) -> Optional[str]:
        """Check Whop withdrawal status for a payout."""
        payout = self.db.query(Payout).filter(Payout.id == payout_id).first()
        if not payout:
            return None
        
        # In production: call Whop API
        # For now: return mock status
        return "PENDING"


def check_payouts() -> Dict[str, int]:
    """Entry point for cron job."""
    skill = PayoutTrackingSkill()
    return skill.check_payouts()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = check_payouts()
    print(f"Payout check results: {result}")