#!/usr/bin/env python3
"""
Automation Empire OS — Real Data Pipeline
Enables agents to pass real data and complete full campaigns.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
import uuid

from scripts.agent_base import AgentTask
from scripts.orchestrator import get_orchestrator
from backend.app.core.config import get_settings
from backend.app.core.db import (
    init_db, Campaign, CampaignRequirement, SourceMedia, Clip, 
    PublishedPost, Earnings, Job, JobStatus
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineData:
    """Data passed between agents in a pipeline."""
    campaign_id: Optional[str] = None
    campaign_db_id: Optional[str] = None
    source_media_ids: List[str] = field(default_factory=list)
    clip_ids: List[str] = field(default_factory=list)
    published_post_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class RealPipeline:
    """Executes a complete campaign pipeline with real data."""
    
    def __init__(self):
        self.settings = get_settings()
        self.orchestrator = get_orchestrator()
        self.session = init_db(self.settings.database_url)
    
    def run_campaign_pipeline(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run complete pipeline: Discover → Parse → Download → Generate Clips → QC → Publish → Track
        """
        pipeline_data = PipelineData()
        results = {}
        
        try:
            # Step 1: Create/Import Campaign
            logger.info("Step 1: Creating campaign")
            campaign_result = self._create_campaign(campaign_data)
            pipeline_data.campaign_id = campaign_result.get("campaign_id")
            pipeline_data.campaign_db_id = campaign_result.get("db_id")
            results["campaign"] = campaign_result
            
            if not pipeline_data.campaign_db_id:
                return {"success": False, "error": "Failed to create campaign", "results": results}
            
            # Step 2: Parse Campaign Requirements
            logger.info("Step 2: Parsing campaign requirements")
            parse_result = self._parse_campaign(pipeline_data.campaign_id)
            results["parse"] = parse_result
            
            # Step 3: Download Source Media
            logger.info("Step 3: Downloading source media")
            download_result = self._download_sources(pipeline_data.campaign_db_id, campaign_data.get("source_urls", []))
            pipeline_data.source_media_ids = download_result.get("source_media_ids", [])
            results["download"] = download_result
            
            # Step 4: Generate Clips
            logger.info("Step 4: Generating clips")
            clip_result = self._generate_clips(pipeline_data.source_media_ids, campaign_data.get("clip_plan", {}))
            pipeline_data.clip_ids = clip_result.get("clip_ids", [])
            results["clips"] = clip_result
            
            # Step 5: Quality Check
            logger.info("Step 5: Quality checking clips")
            qc_result = self._quality_check(pipeline_data.clip_ids)
            results["qc"] = qc_result
            
            # Step 6: Publish (if not dry run)
            if not self.settings.dry_run:
                logger.info("Step 6: Publishing clips")
                publish_result = self._publish_clips(pipeline_data.clip_ids, campaign_data.get("publish_config", {}))
                pipeline_data.published_post_ids = publish_result.get("post_ids", [])
                results["publish"] = publish_result
            else:
                logger.info("Step 6: Skipping publish (dry run mode)")
                results["publish"] = {"skipped": True, "reason": "dry_run"}
            
            # Step 7: Track Earnings (placeholder for now)
            logger.info("Step 7: Tracking earnings")
            earnings_result = self._track_earnings(pipeline_data.published_post_ids)
            results["earnings"] = earnings_result
            
            return {
                "success": True,
                "pipeline_data": {
                    "campaign_id": pipeline_data.campaign_id,
                    "campaign_db_id": pipeline_data.campaign_db_id,
                    "source_media_count": len(pipeline_data.source_media_ids),
                    "clips_generated": len(pipeline_data.clip_ids),
                    "posts_published": len(pipeline_data.published_post_ids),
                },
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            return {"success": False, "error": str(e), "results": results}
    
    def _create_campaign(self, data: Dict) -> Dict:
        """Create or import a campaign."""
        campaign_id = data.get("campaign_id", f"camp_{uuid.uuid4().hex[:12]}")
        
        # Check if exists
        existing = self.session.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
        if existing:
            return {"campaign_id": existing.campaign_id, "db_id": existing.id, "status": "exists"}
        
        campaign = Campaign(
            campaign_id=campaign_id,
            source=data.get("source", "manual"),
            title=data.get("title", "Untitled Campaign"),
            type=data.get("type", "cpm"),
            platforms=json.dumps(data.get("platforms", ["tiktok", "youtube", "instagram"])),
            niches=json.dumps(data.get("niches", [])),
            budget_total=data.get("budget_total", 1000.0),
            budget_remaining=data.get("budget_remaining", 1000.0),
            rate=data.get("rate", 5.0),
            max_payout=data.get("max_payout", 500.0),
            min_views=data.get("min_views", 1000),
            required_tags=json.dumps(data.get("required_tags", [])),
            required_mentions=json.dumps(data.get("required_mentions", [])),
            deadline=data.get("deadline"),
            status="qualified",
            raw_source_url=data.get("raw_source_url", ""),
            metadata_json=json.dumps(data.get("metadata", {}))
        )
        
        self.session.add(campaign)
        self.session.commit()
        
        return {"campaign_id": campaign.campaign_id, "db_id": campaign.id, "status": "created"}
    
    def _parse_campaign(self, campaign_id: str) -> Dict:
        """Parse campaign requirements using the campaign_parser worker."""
        job = self.orchestrator.create_job("content_rewards", {
            "step": "campaign_parser",
            "campaign_id": campaign_id
        })
        
        result = self.orchestrator.execute_job(job.id)
        return {"job_id": job.id, "success": result.success, "output": result.output}
    
    def _download_sources(self, campaign_db_id: str, source_urls: List[str]) -> Dict:
        """Download source videos using source_download worker."""
        if not source_urls:
            # Use placeholder for testing
            source_urls = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]  # Test URL
        
        job = self.orchestrator.create_job("content_rewards", {
            "step": "source_download",
            "campaign_id": campaign_db_id,
            "source_urls": source_urls
        })
        
        result = self.orchestrator.execute_job(job.id)
        
        # Extract source media IDs from result
        source_media_ids = []
        if result.success and result.output:
            downloaded = result.output.get("downloaded", [])
            for item in downloaded:
                if isinstance(item, dict) and "source_media_id" in item:
                    source_media_ids.append(item["source_media_id"])
        
        return {"job_id": job.id, "success": result.success, "output": result.output, "source_media_ids": source_media_ids}
    
    def _generate_clips(self, source_media_ids: List[str], clip_plan: Dict) -> Dict:
        """Generate clips from source media using clip_generator worker."""
        clip_ids = []
        
        for source_media_id in source_media_ids:
            job = self.orchestrator.create_job("content_rewards", {
                "step": "clip_generator",
                "source_media_id": source_media_id,
                "clip_plan": clip_plan
            })
            
            result = self.orchestrator.execute_job(job.id)
            
            if result.success and result.output:
                clip_id = result.output.get("clip_id")
                if clip_id:
                    clip_ids.append(clip_id)
        
        return {"clip_ids": clip_ids, "count": len(clip_ids)}
    
    def _quality_check(self, clip_ids: List[str]) -> Dict:
        """Run quality checks on clips."""
        passed = []
        failed = []
        
        for clip_id in clip_ids:
            job = self.orchestrator.create_job("content_rewards", {
                "step": "quality_check",
                "clip_id": clip_id
            })
            
            result = self.orchestrator.execute_job(job.id)
            
            if result.success:
                passed.append(clip_id)
            else:
                failed.append(clip_id)
        
        return {"passed": passed, "failed": failed, "total": len(clip_ids)}
    
    def _publish_clips(self, clip_ids: List[str], publish_config: Dict) -> Dict:
        """Publish clips to platforms."""
        post_ids = []
        platforms = publish_config.get("platforms", ["tiktok"])
        
        for clip_id in clip_ids:
            for platform in platforms:
                job = self.orchestrator.create_job("content_rewards", {
                    "step": "publish",
                    "clip_id": clip_id,
                    "platform": platform,
                    "caption": publish_config.get("caption", ""),
                    "tags": publish_config.get("tags", [])
                })
                
                result = self.orchestrator.execute_job(job.id)
                
                if result.success and result.output:
                    post_id = result.output.get("post_id")
                    if post_id:
                        post_ids.append(post_id)
        
        return {"post_ids": post_ids, "count": len(post_ids)}
    
    def _track_earnings(self, post_ids: List[str]) -> Dict:
        """Track earnings from published posts."""
        # Placeholder - would integrate with platform APIs
        return {"tracked": len(post_ids), "total_estimated": 0.0}


# Global pipeline instance
_pipeline = None

def get_pipeline() -> RealPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RealPipeline()
    return _pipeline