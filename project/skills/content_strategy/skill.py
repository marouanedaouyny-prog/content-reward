# Content Strategy Skill
# Selects source content and plans clips based on campaign rules

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging

from project.db.models import (
    Session, Campaign, SourceMedia, Transcript, Clip, ClipPlan, init_db
)
from project.config.settings import get_settings

logger = logging.getLogger(__name__)


class ContentStrategySkill:
    """Skill for planning clips from source content based on campaign rules."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
    
    def plan(self, campaign_id: str) -> List[Dict[str, Any]]:
        """Generate clip plans for a campaign based on source media and rules."""
        campaign = self.db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        # Get downloaded source media
        sources = self.db.query(SourceMedia).filter(
            SourceMedia.campaign_id == campaign_id,
            SourceMedia.status == "DOWNLOADED"
        ).all()
        
        if not sources:
            logger.warning(f"No downloaded sources for campaign {campaign_id}")
            return []
        
        plans = []
        
        for source in sources:
            # Get transcript
            transcript = self.db.query(Transcript).filter(
                Transcript.source_media_id == source.id
            ).first()
            
            if not transcript:
                logger.warning(f"No transcript for source {source.id}")
                continue
            
            # Generate clip plans from this source
            source_plans = self._plan_from_source(campaign, source, transcript)
            plans.extend(source_plans)
        
        # Store plans
        for plan in plans:
            existing = self.db.query(ClipPlan).filter(
                ClipPlan.campaign_id == campaign_id,
                ClipPlan.source_media_id == plan["source_media_id"],
                ClipPlan.start_sec == plan["start_sec"],
                ClipPlan.end_sec == plan["end_sec"]
            ).first()
            
            if not existing:
                clip_plan = ClipPlan(
                    campaign_id=campaign_id,
                    source_media_id=plan["source_media_id"],
                    start_sec=plan["start_sec"],
                    end_sec=plan["end_sec"],
                    duration=plan["duration"],
                    target_platforms=plan["target_platforms"],
                    aspect_ratio=plan["aspect_ratio"],
                    strategy=plan["strategy"],
                    transcript_segment=plan["transcript_segment"]
                )
                self.db.add(clip_plan)
        
        self.db.commit()
        
        logger.info(f"Generated {len(plans)} clip plans for campaign {campaign.external_campaign_id}")
        return plans
    
    def _plan_from_source(self, campaign: Campaign, source: SourceMedia, 
                          transcript: Transcript) -> List[Dict[str, Any]]:
        """Generate clip plans from a single source."""
        plans = []
        
        # Parse campaign rules
        rules = self._parse_campaign_rules(campaign)
        
        # Get segments from transcript
        segments = transcript.segments or []
        
        if not segments:
            # Fallback: create fixed windows
            return self._create_fixed_windows(campaign, source)
        
        # Score each segment
        scored_segments = []
        for segment in segments:
            score = self._score_segment(segment, rules)
            scored_segments.append((segment, score))
        
        # Sort by score
        scored_segments.sort(key=lambda x: x[1], reverse=True)
        
        # Select top segments per platform
        target_platforms = campaign.platforms or ["TIKTOK", "INSTAGRAM", "YOUTUBE"]
        
        for platform in target_platforms:
            aspect_ratio = "9:16" if platform in ["TIKTOK", "INSTAGRAM"] else "16:9"
            max_duration = rules.get(f"max_duration_{platform}", rules.get("max_duration", 60))
            min_duration = rules.get("min_duration", 5)
            
            # Select best segment that fits duration
            for segment, score in scored_segments:
                seg_duration = segment.get("end", 0) - segment.get("start", 0)
                if min_duration <= seg_duration <= max_duration:
                    plans.append({
                        "campaign_id": campaign.id,
                        "source_media_id": source.id,
                        "start_sec": segment.get("start", 0),
                        "end_sec": segment.get("end", seg_duration),
                        "duration": seg_duration,
                        "target_platforms": [platform],
                        "aspect_ratio": aspect_ratio,
                        "strategy": "TOPIC_COMPLETE",
                        "transcript_segment": segment
                    })
                    break
        
        # If no segments fit, create fixed windows
        if not plans:
            plans = self._create_fixed_windows(campaign, source)
        
        return plans
    
    def _parse_campaign_rules(self, campaign: Campaign) -> Dict[str, Any]:
        """Extract rules from campaign."""
        rules = {}
        
        if campaign.min_views:
            rules["min_views"] = campaign.min_views
        if campaign.max_payout_per_clip:
            rules["max_payout_per_clip"] = campaign.max_payout_per_clip
        if campaign.editing_rules:
            for rule in campaign.editing_rules:
                if rule.get("rule_type") == "DURATION":
                    spec = rule.get("spec", {})
                    if "min" in spec:
                        rules["min_duration"] = spec["min"]
                    if "max" in spec:
                        rules["max_duration"] = spec["max"]
                elif rule.get("rule_type") == "ASPECT_RATIO":
                    rules["aspect_ratio"] = rule.get("spec", {}).get("ratio", "9:16")
        
        return rules
    
    def _score_segment(self, segment: Dict, rules: Dict) -> float:
        """Score a transcript segment for clip potential."""
        score = 0.5  # Base score
        
        text = segment.get("text", "").lower()
        
        # Hook keywords (first 3 seconds critical)
        hook_keywords = ["wait", "stop", "secret", "hack", "trick", "best", "worst", 
                        "never", "always", "why", "how", "what if", "imagine"]
        if any(kw in text for kw in hook_keywords):
            score += 0.2
        
        # Emotional keywords
        emotion_keywords = ["love", "hate", "amazing", "incredible", "shocking",
                           "unbelievable", "mind blown", "game changer"]
        if any(kw in text for kw in emotion_keywords):
            score += 0.15
        
        # Action keywords
        action_keywords = ["try this", "do this", "watch this", "link in bio",
                          "follow for more", "comment below"]
        if any(kw in text for kw in action_keywords):
            score += 0.1
        
        # Completeness (ends with period)
        if text.strip().endswith("."):
            score += 0.05
        
        return min(score, 1.0)
    
    def _create_fixed_windows(self, campaign: Campaign, source: SourceMedia) -> List[Dict[str, Any]]:
        """Create fixed-duration clip windows as fallback."""
        plans = []
        duration = source.duration or 60
        target_platforms = campaign.platforms or ["TIKTOK", "INSTAGRAM", "YOUTUBE"]
        
        # Create 30-second windows with 15-second overlap
        window_size = 30
        overlap = 15
        
        for platform in target_platforms:
            aspect_ratio = "9:16" if platform in ["TIKTOK", "INSTAGRAM"] else "16:9"
            
            start = 0
            clip_index = 0
            while start + window_size <= duration:
                plans.append({
                    "campaign_id": campaign.id,
                    "source_media_id": source.id,
                    "start_sec": start,
                    "end_sec": start + window_size,
                    "duration": window_size,
                    "target_platforms": [platform],
                    "aspect_ratio": aspect_ratio,
                    "strategy": "FIXED_WINDOW",
                    "transcript_segment": {"start": start, "end": start + window_size}
                })
                start += window_size - overlap
                clip_index += 1
        
        return plans


def generate_clip_plans(campaign_id: str) -> List[Dict[str, Any]]:
    """Entry point for generating clip plans."""
    skill = ContentStrategySkill()
    return skill.plan(campaign_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("ContentStrategySkill ready")