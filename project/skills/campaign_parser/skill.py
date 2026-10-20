# Campaign Parser Skill
# Parses campaign details into structured requirements

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import json

from project.db.models import (
    Session, Campaign, CampaignRequirement, init_db
)
from project.config.settings import get_settings

logger = logging.getLogger(__name__)


class CampaignParserSkill:
    """Skill for parsing campaign details into structured requirements."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
    
    def parse(self, campaign_id: str) -> Dict[str, Any]:
        """Parse campaign into structured CampaignModel."""
        campaign = self.db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        logger.info(f"Parsing campaign {campaign.external_campaign_id}")
        
        # Extract structured requirements
        requirements = self._extract_requirements(campaign)
        
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
        
        campaign.status = "ANALYZED"
        campaign.analyzed_at = datetime.now(timezone.utc)
        if eligible:
            campaign.status = "ELIGIBLE"
            campaign.eligible_at = datetime.now(timezone.utc)
        else:
            campaign.status = "CLOSED"
            campaign.closed_at = datetime.now(timezone.utc)
        
        self.db.commit()
        
        return {
            "campaign_id": campaign.id,
            "external_campaign_id": campaign.external_campaign_id,
            "requirements_parsed": len(requirements),
            "eligible": eligible,
            "requirements": requirements
        }
    
    def _extract_requirements(self, campaign: Campaign) -> List[Dict[str, Any]]:
        """Extract all requirements from campaign data."""
        reqs = []
        
        # Platform requirements
        if campaign.platforms:
            reqs.append({
                "field_name": "platforms",
                "field_value": campaign.platforms,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        # Duration requirements
        if campaign.editing_rules:
            for rule in campaign.editing_rules:
                if rule.get("rule_type") == "DURATION":
                    spec = rule.get("spec", {})
                    reqs.append({
                        "field_name": "duration",
                        "field_value": spec,
                        "confidence": "HIGH",
                        "source": "structured"
                    })
                elif rule.get("rule_type") == "ASPECT_RATIO":
                    reqs.append({
                        "field_name": "aspect_ratio",
                        "field_value": rule.get("spec", {}),
                        "confidence": "HIGH",
                        "source": "structured"
                    })
        
        # Tags and mentions
        if campaign.required_tags:
            reqs.append({
                "field_name": "required_tags",
                "field_value": campaign.required_tags,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        if campaign.required_mentions:
            reqs.append({
                "field_name": "required_mentions",
                "field_value": campaign.required_mentions,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        # Disclosure
        if campaign.required_disclosure:
            reqs.append({
                "field_name": "required_disclosure",
                "field_value": campaign.required_disclosure,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        # Budget and payout
        if campaign.rate_cpm:
            reqs.append({
                "field_name": "rate_cpm",
                "field_value": campaign.rate_cpm,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        if campaign.rate_per_post:
            reqs.append({
                "field_name": "rate_per_post",
                "field_value": campaign.rate_per_post,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        if campaign.min_views:
            reqs.append({
                "field_name": "min_views",
                "field_value": campaign.min_views,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        if campaign.max_payout_per_clip:
            reqs.append({
                "field_name": "max_payout_per_clip",
                "field_value": campaign.max_payout_per_clip,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        # Pre-post review
        reqs.append({
            "field_name": "pre_post_review_enabled",
            "field_value": campaign.pre_post_review_enabled,
            "confidence": "HIGH",
            "source": "structured"
        })
        
        # Co-posting and repost limits
        reqs.append({
            "field_name": "co_posting_allowed",
            "field_value": campaign.co_posting_allowed,
            "confidence": "HIGH",
            "source": "structured"
        })
        
        reqs.append({
            "field_name": "repost_limit",
            "field_value": campaign.repost_limit,
            "confidence": "HIGH",
            "source": "structured"
        })
        
        # Vertical
        if campaign.vertical:
            reqs.append({
                "field_name": "vertical",
                "field_value": campaign.vertical,
                "confidence": "HIGH",
                "source": "structured"
            })
        
        # Parse description for additional rules
        if campaign.description:
            desc_reqs = self._extract_from_description(campaign.description)
            reqs.extend(desc_reqs)
        
        return reqs
    
    def _extract_from_description(self, description: str) -> List[Dict[str, Any]]:
        """Extract structured requirements from description text."""
        reqs = []
        desc_lower = description.lower()
        
        # Hook requirement
        if any(kw in desc_lower for kw in ["hook", "grab attention", "first 3 seconds", "opening"]):
            reqs.append({
                "field_name": "hook_required",
                "field_value": "Strong hook required in first 3 seconds",
                "confidence": "MEDIUM",
                "source": "description"
            })
        
        # CTA requirement
        if any(kw in desc_lower for kw in ["call to action", "cta", "call-to-action", "link in bio", "follow"]):
            reqs.append({
                "field_name": "cta_required",
                "field_value": "Call to action required",
                "confidence": "MEDIUM",
                "source": "description"
            })
        
        # Branding requirement
        if any(kw in desc_lower for kw in ["logo", "branding", "watermark", "brand visible"]):
            reqs.append({
                "field_name": "branding_required",
                "field_value": "Brand logo/watermark required",
                "confidence": "MEDIUM",
                "source": "description"
            })
        
        # Audio requirement
        if any(kw in desc_lower for kw in ["audio", "sound", "music", "voiceover", "narration"]):
            reqs.append({
                "field_name": "audio_required",
                "field_value": "Audio/music required",
                "confidence": "MEDIUM",
                "source": "description"
            })
        
        # Specific format requirements
        if "vertical" in desc_lower and "horizontal" not in desc_lower:
            reqs.append({
                "field_name": "format_preference",
                "field_value": "vertical_preferred",
                "confidence": "MEDIUM",
                "source": "description"
            })
        elif "horizontal" in desc_lower and "vertical" not in desc_lower:
            reqs.append({
                "field_name": "format_preference",
                "field_value": "horizontal_preferred",
                "confidence": "MEDIUM",
                "source": "description"
            })
        
        return reqs
    
    def _check_eligibility(self, campaign: Campaign) -> bool:
        """Check if campaign is eligible for automation."""
        # Budget check
        if campaign.budget_remaining <= 0:
            logger.warning(f"Campaign {campaign.external_campaign_id}: budget exhausted")
            return False
        
        # Deadline check
        if campaign.deadline and campaign.deadline < datetime.now(timezone.utc):
            logger.warning(f"Campaign {campaign.external_campaign_id}: deadline passed")
            return False
        
        # Platform support check
        supported = {"TIKTOK", "INSTAGRAM", "YOUTUBE", "FACEBOOK", "X"}
        campaign_platforms = set(campaign.platforms) if campaign.platforms else set()
        if not campaign_platforms.issubset(supported):
            logger.warning(f"Campaign {campaign.external_campaign_id}: unsupported platforms")
            return False
        
        # Vertical restrictions
        restricted_verticals = {"POLITICAL", "ADULT", "ILLEGAL"}
        if campaign.vertical and campaign.vertical in restricted_verticals:
            logger.warning(f"Campaign {campaign.external_campaign_id}: restricted vertical")
            return False
        
        # Pre-post review check - can still automate but needs human gate
        # Not a blocker, just adds human checkpoint
        
        return True


def parse_campaign(campaign_id: str) -> Dict[str, Any]:
    """Entry point for parsing a campaign."""
    skill = CampaignParserSkill()
    return skill.parse(campaign_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("CampaignParserSkill ready")