# Campaign Research Skill
# Discovers and analyzes campaigns from Content Rewards platform

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import json

from project.db.models import Session, Campaign, CampaignRequirement, init_db
from project.config.settings import get_settings

logger = logging.getLogger(__name__)


class CampaignResearchSkill:
    """Skill for discovering and analyzing Content Rewards campaigns."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
    
    def discover(self) -> List[Dict[str, Any]]:
        """
        Discover new campaigns from Content Rewards platform.
        Uses browser automation since CR has no public API.
        """
        logger.info("Discovering campaigns from Content Rewards...")
        
        # For now, return mock data structure
        # In production: use Playwright MCP to scrape CR Discover page
        campaigns = self._mock_discover()
        
        # Store new campaigns
        stored = []
        for camp_data in campaigns:
            existing = self.db.query(Campaign).filter(
                Campaign.external_campaign_id == camp_data["external_campaign_id"]
            ).first()
            
            if not existing:
                new_camp = Campaign(**camp_data)
                self.db.add(new_camp)
                stored.append(camp_data["external_campaign_id"])
        
        self.db.commit()
        logger.info(f"Discovered {len(campaigns)} campaigns, stored {len(stored)} new")
        return stored
    
    def analyze(self, campaign_id: str) -> Dict[str, Any]:
        """
        Analyze a campaign's requirements and structure.
        Returns structured CampaignModel.
        """
        campaign = self.db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        logger.info(f"Analyzing campaign {campaign.external_campaign_id}")
        
        # Parse requirements from campaign data
        requirements = self._parse_requirements(campaign)
        
        # Store parsed requirements
        for req in requirements:
            existing = self.db.query(CampaignRequirement).filter(
                CampaignRequirement.campaign_id == campaign.id,
                CampaignRequirement.field_name == req["field_name"]
            ).first()
            if not existing:
                self.db.add(CampaignRequirement(
                    campaign_id=campaign.id,
                    field_name=req["field_name"],
                    field_value=req["field_value"],
                    confidence=req["confidence"],
                    source=req["source"]
                ))
        
        # Eligibility check
        eligible = self._check_eligibility(campaign)
        
        campaign.status = "ELIGIBLE" if eligible else "CLOSED"
        campaign.analyzed_at = datetime.now(timezone.utc)
        if eligible:
            campaign.eligible_at = datetime.now(timezone.utc)
        else:
            campaign.closed_at = datetime.now(timezone.utc)
        
        self.db.commit()
        
        return {
            "campaign_id": campaign.id,
            "external_campaign_id": campaign.external_campaign_id,
            "requirements_parsed": len(requirements),
            "eligible": eligible,
            "requirements": requirements
        }
    
    def _mock_discover(self) -> List[Dict[str, Any]]:
        """Mock campaign discovery for development."""
        return [
            {
                "external_campaign_id": "cr_campaign_001",
                "campaign_type": "CPM",
                "title": "Tech Product Launch - Mobile App",
                "description": "Create engaging clips for new mobile app launch. Must show app interface and mention key features.",
                "brand_id": "brand_tech_001",
                "brand_name": "TechCorp",
                "platforms": ["TIKTOK", "INSTAGRAM", "YOUTUBE"],
                "required_tags": ["#TechLaunch", "#MobileApp"],
                "required_mentions": ["@TechCorp"],
                "required_disclosure": "Sponsored by TechCorp",
                "source_content": [{"type": "VIDEO_URL", "url": "https://example.com/source.mp4", "usage_rights": "campaign_assets"}],
                "editing_rules": [
                    {"rule_type": "DURATION", "spec": {"min": 15, "max": 60}, "mandatory": True},
                    {"rule_type": "ASPECT_RATIO", "spec": {"ratio": "9:16"}, "mandatory": True}
                ],
                "min_views": 1000,
                "max_payout_per_clip": 500.0,
                "budget_total": 10000.0,
                "budget_remaining": 10000.0,
                "budget_reserved": 0.0,
                "rate_cpm": 5.0,
                "pre_post_review_enabled": False,
                "submission_method": "URL",
                "co_posting_allowed": False,
                "repost_limit": 5,
                "deadline": None,
                "vertical": "TECH",
                "discovered_at": datetime.now(timezone.utc)
            }
        ]
    
    def _parse_requirements(self, campaign: Campaign) -> List[Dict[str, Any]]:
        """Parse campaign requirements into structured format."""
        reqs = []
        
        # Structured fields
        structured_fields = [
            ("platforms", campaign.platforms, "HIGH", "structured"),
            ("min_views", campaign.min_views, "HIGH", "structured"),
            ("max_payout_per_clip", campaign.max_payout_per_clip, "HIGH", "structured"),
            ("required_tags", campaign.required_tags, "MEDIUM", "structured"),
            ("required_mentions", campaign.required_mentions, "MEDIUM", "structured"),
            ("required_disclosure", campaign.required_disclosure, "HIGH", "structured"),
            ("editing_rules", campaign.editing_rules, "HIGH", "structured"),
        ]
        
        for name, value, conf, src in structured_fields:
            if value:
                reqs.append({
                    "field_name": name,
                    "field_value": value,
                    "confidence": conf,
                    "source": src
                })
        
        # Parse description for additional rules (simplified)
        if campaign.description:
            desc_reqs = self._extract_from_description(campaign.description)
            reqs.extend(desc_reqs)
        
        return reqs
    
    def _extract_from_description(self, description: str) -> List[Dict[str, Any]]:
        """Extract structured requirements from description text."""
        # Simplified keyword extraction
        reqs = []
        desc_lower = description.lower()
        
        keywords = {
            "hook": ("HOOK_REQUIRED", "Must have strong hook in first 3 seconds"),
            "cta": ("CTA_REQUIRED", "Must include call-to-action"),
            "logo": ("BRANDING_REQUIRED", "Must show brand logo"),
            "sound": ("AUDIO_REQUIRED", "Must have audio/music"),
        }
        
        for keyword, (field_name, field_value) in keywords.items():
            if keyword in desc_lower:
                reqs.append({
                    "field_name": field_name,
                    "field_value": field_value,
                    "confidence": "MEDIUM",
                    "source": "description"
                })
        
        return reqs
    
    def _check_eligibility(self, campaign: Campaign) -> bool:
        """Check if campaign is eligible for automation."""
        if campaign.budget_remaining <= 0:
            logger.warning(f"Campaign {campaign.external_campaign_id}: budget exhausted")
            return False
        
        if campaign.deadline and campaign.deadline < datetime.now(timezone.utc):
            logger.warning(f"Campaign {campaign.external_campaign_id}: deadline passed")
            return False
        
        # Check if platforms are supported
        supported = {"TIKTOK", "INSTAGRAM", "YOUTUBE", "FACEBOOK", "X"}
        campaign_platforms = set(campaign.platforms) if campaign.platforms else set()
        if not campaign_platforms.issubset(supported):
            logger.warning(f"Campaign {campaign.external_campaign_id}: unsupported platforms")
            return False
        
        # Check vertical restrictions
        restricted_verticals = {"POLITICAL", "ADULT", "ILLEGAL"}
        if campaign.vertical and campaign.vertical in restricted_verticals:
            logger.warning(f"Campaign {campaign.external_campaign_id}: restricted vertical")
            return False
        
        return True


# Skill entry point
def discover_campaigns() -> List[str]:
    """Entry point for cron job."""
    skill = CampaignResearchSkill()
    return skill.discover()


def analyze_campaign(campaign_id: str) -> Dict[str, Any]:
    """Entry point for campaign analysis."""
    skill = CampaignResearchSkill()
    return skill.analyze(campaign_id)


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    result = discover_campaigns()
    print(f"Discovered: {result}")