#!/usr/bin/env python3
"""
Automation Empire OS — Content Rewards Workers
$0 constraint: yt-dlp, FFmpeg, faster-whisper, OpenCV, Pillow, Ollama
"""

import os
import re
import json
import hashlib
import subprocess
import tempfile
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

# Local imports
from scripts.worker_base import BaseWorker, WorkerResult, WorkerRegistry
from backend.app.core.config import get_settings
from backend.app.core.db import (
    init_db, Campaign, CampaignRequirement, SourceMedia, Clip, Job, JobStatus, PublishedPost
)

logger = logging.getLogger(__name__)


class CampaignDiscoveryWorker(BaseWorker):
    """Discover content reward campaigns from various sources"""

    def __init__(self):
        super().__init__("campaign_discovery")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        source_type = payload.get("source_type", "manual")
        source_url = payload.get("source_url")
        html_content = payload.get("html_content")
        manual_paste = payload.get("manual_paste")

        campaigns = []

        if source_type == "url" and source_url:
            campaigns = self._discover_from_url(source_url)
        elif source_type == "html" and html_content:
            campaigns = self._discover_from_html(html_content)
        elif source_type == "manual" and manual_paste:
            campaigns = self._discover_from_manual(manual_paste)

        # Store campaigns in DB
        stored = []
        for camp in campaigns:
            existing = self.session.query(Campaign).filter(
                Campaign.campaign_id == camp["campaign_id"]
            ).first()
            if not existing:
                new_camp = Campaign(**camp)
                self.session.add(new_camp)
            # Always add to stored so downstream steps get the campaign_id
            stored.append(camp["campaign_id"])

        self.session.commit()

        return WorkerResult(
            success=True,
            output={"campaigns_discovered": len(campaigns), "campaigns_stored": stored},
            metrics={"discovered": len(campaigns), "stored": len(stored)}
        )

    def _discover_from_url(self, url: str) -> List[Dict]:
        """Placeholder - would use Playwright/requests to scrape"""
        logger.info(f"Discovering campaigns from URL: {url}")
        return []

    def _discover_from_html(self, html: str) -> List[Dict]:
        """Placeholder - parse HTML for campaign data"""
        logger.info("Discovering campaigns from HTML")
        return []

    def _discover_from_manual(self, text: str) -> List[Dict]:
        """Parse manually pasted campaign details"""
        logger.info("Discovering campaigns from manual input")
        # Basic extraction from text
        camp_id = hashlib.md5(text.encode()).hexdigest()[:12]
        return [{
            "campaign_id": camp_id,
            "source": "manual",
            "title": text[:100],
            "type": "cpm",
            "platforms": ["tiktok", "youtube", "instagram"],
            "budget_total": 1000.0,
            "budget_remaining": 1000.0,
            "rate": 5.0,
            "max_payout": 500.0,
            "min_views": 1000,
            "status": "discovered",
            "raw_source_url": "",
            "metadata_json": json.dumps({"source_text": text[:500]})
        }]


class CampaignParserWorker(BaseWorker):
    """Parse campaign requirements from source material"""

    def __init__(self):
        super().__init__("campaign_parser")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        campaign_id = payload.get("campaign_id")
        if not campaign_id:
            return WorkerResult(success=False, error_code="MISSING_CAMPAIGN_ID", error_message="campaign_id required")

        campaign = self.session.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
        if not campaign:
            return WorkerResult(success=False, error_code="CAMPAIGN_NOT_FOUND", error_message=f"Campaign {campaign_id} not found")

        # Parse requirements (placeholder - would use Ollama for AI parsing)
        requirements = self._extract_requirements(campaign)

        for req in requirements:
            existing = self.session.query(CampaignRequirement).filter(
                CampaignRequirement.campaign_id == campaign.id,
                CampaignRequirement.field_name == req["field_name"]
            ).first()
            if not existing:
                self.session.add(CampaignRequirement(
                    campaign_id=campaign.id,
                    field_name=req["field_name"],
                    field_value=req["field_value"],
                    confidence=req["confidence"],
                    source=req["source"]
                ))

        campaign.status = "qualified"
        self.session.commit()

        return WorkerResult(
            success=True,
            output={"campaign_id": campaign_id, "requirements_parsed": len(requirements)},
            metrics={"requirements": len(requirements)}
        )

    def _extract_requirements(self, campaign: Campaign) -> List[Dict]:
        """Extract structured requirements - placeholder for AI parsing"""
        reqs = []
        # Basic known fields - handle both string and list
        platforms = campaign.platforms
        if isinstance(platforms, str):
            platforms = json.loads(platforms or '["tiktok"]')
        
        required_tags = campaign.required_tags
        if isinstance(required_tags, str):
            required_tags = json.loads(required_tags or "[]")
            
        required_mentions = campaign.required_mentions
        if isinstance(required_mentions, str):
            required_mentions = json.loads(required_mentions or "[]")
        
        fields = [
            ("platforms", platforms, "HIGH", "parser"),
            ("min_views", str(campaign.min_views), "HIGH", "parser"),
            ("max_payout", str(campaign.max_payout), "HIGH", "parser"),
            ("required_tags", required_tags, "MEDIUM", "parser"),
            ("required_mentions", required_mentions, "MEDIUM", "parser"),
        ]
        for name, value, conf, src in fields:
            reqs.append({
                "field_name": name,
                "field_value": json.dumps(value) if isinstance(value, list) else str(value),
                "confidence": conf,
                "source": src
            })
        return reqs


class SourceDownloadWorker(BaseWorker):
    """Download source media (video) for campaigns"""

    def __init__(self):
        super().__init__("source_download")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        campaign_id = payload.get("campaign_id")
        source_urls = payload.get("source_urls", [])

        if not campaign_id:
            return WorkerResult(success=False, error_code="MISSING_CAMPAIGN_ID", error_message="campaign_id required")

        campaign = self.session.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
        if not campaign:
            return WorkerResult(success=False, error_code="CAMPAIGN_NOT_FOUND", error_message=f"Campaign {campaign_id} not found")

        # In dry run mode, just create mock source media entries
        if self.settings.dry_run:
            logger.info(f"DRY RUN: Would download videos for campaign {campaign_id}")
            downloaded = []
            for i, url in enumerate(source_urls):
                mock_source = SourceMedia(
                    campaign_id=campaign.id,
                    source_url=url,
                    title=f"Mock video {i+1} from {url}",
                    file_hash=f"mock_hash_{uuid.uuid4().hex[:16]}",
                    media_type="video",
                    duration=60.0,
                    downloaded_at=datetime.now(timezone.utc),
                    status="downloaded"
                )
                self.session.add(mock_source)
                self.session.flush()
                downloaded.append({"source_media_id": mock_source.id, "path": f"mock/video_{i+1}.mp4", "hash": mock_source.file_hash, "duration": 60.0})
            self.session.commit()
            
            return WorkerResult(
                success=True,
                output={"campaign_id": campaign_id, "downloaded": downloaded},
                metrics={"total_urls": len(source_urls) if source_urls else 1, "successful": len(downloaded)},
                error_code=None,
                error_message=None
            )

        # Use default test URL if none provided
        if not source_urls:
            source_urls = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]

        downloaded = []
        for url in source_urls:
            result = self._download_video(url, campaign.id)
            if result:
                downloaded.append(result)

        self.session.commit()

        return WorkerResult(
            success=len(downloaded) > 0,
            output={"campaign_id": campaign_id, "downloaded": downloaded},
            metrics={"total_urls": len(source_urls), "successful": len(downloaded)},
            error_code="PARTIAL_DOWNLOAD" if len(downloaded) < len(source_urls) else None,
            error_message=f"Downloaded {len(downloaded)}/{len(source_urls)}" if len(downloaded) < len(source_urls) else None
        )

    def _download_video(self, url: str, campaign_db_id: str) -> Optional[Dict]:
        """Download video using yt-dlp"""
        try:
            # Create storage path
            storage_dir = Path(self.settings.storage_dir) / "raw"
            storage_dir.mkdir(parents=True, exist_ok=True)

            # Get video info first
            info_cmd = ["yt-dlp", "--dump-json", "--no-download", url]
            result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.error(f"yt-dlp info failed: {result.stderr}")
                return None

            info = json.loads(result.stdout)
            video_id = info.get("id", "unknown")
            title = info.get("title", "unknown")
            duration = info.get("duration", 0)

            # Generate output filename - always use .mp4 since we force merge
            filename = f"{campaign_db_id}_{video_id}.mp4"
            output_path = storage_dir / filename

            # Download with yt-dlp
            download_cmd = [
                "yt-dlp", "-f", "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/best",
                "--merge-output-format", "mp4",
                "--no-check-certificates",
                "-o", str(output_path),
                url
            ]
            result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(f"yt-dlp download failed: {result.stderr}")
                return None

            # Use the actual output path (may have been renamed by merge)
            actual_path = output_path
            if not actual_path.exists():
                # Try with different extensions
                for ext in ['.mp4', '.webm', '.mkv']:
                    test_path = output_path.with_suffix(ext)
                    if test_path.exists():
                        actual_path = test_path
                        break
            
            if not actual_path.exists():
                logger.error(f"Downloaded file not found at {output_path}")
                return None

            # Calculate hash
            file_hash = self._calculate_hash(actual_path)

            # Check for duplicates
            existing = self.session.query(SourceMedia).filter(SourceMedia.file_hash == file_hash).first()
            if existing:
                logger.info(f"Duplicate video detected: {file_hash}")
                output_path.unlink()  # Remove duplicate file
                return {"source_media_id": existing.id, "duplicate": True}

            # Store in DB
            media = SourceMedia(
                campaign_id=campaign_db_id,
                source_url=url,
                title=title,
                file_hash=file_hash,
                media_type="video",
                duration=duration,
                downloaded_at=datetime.now(timezone.utc),
                status="downloaded"
            )
            self.session.add(media)
            self.session.flush()

            return {"source_media_id": media.id, "path": str(output_path), "hash": file_hash, "duration": duration}

        except subprocess.TimeoutExpired:
            logger.error(f"Download timeout for {url}")
            return None
        except Exception as e:
            logger.error(f"Download error for {url}: {e}")
            return None

    def _calculate_hash(self, filepath: Path) -> str:
        """Calculate SHA-256 hash of file"""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


class ClipGeneratorWorker(BaseWorker):
    """Generate clips from source media using FFmpeg"""

    def __init__(self):
        super().__init__("clip_generator")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        source_media_id = payload.get("source_media_id")
        clip_plan = payload.get("clip_plan", {})  # {start, end, aspect_ratio, etc.}

        if not source_media_id:
            return WorkerResult(success=False, error_code="MISSING_SOURCE_MEDIA", error_message="source_media_id required")

        media = self.session.query(SourceMedia).filter(SourceMedia.id == source_media_id).first()
        if not media:
            return WorkerResult(success=False, error_code="SOURCE_NOT_FOUND", error_message=f"Source media {source_media_id} not found")

        # Find source file
        storage_dir = Path(self.settings.storage_dir) / "raw"
        source_files = list(storage_dir.glob(f"{media.campaign_id}_{media.id.split('_')[-1]}.*"))
        if not source_files:
            # Fallback: search by hash
            source_files = list(storage_dir.rglob("*"))
            source_files = [f for f in source_files if self._calculate_hash(f) == media.file_hash]

        if not source_files:
            return WorkerResult(success=False, error_code="SOURCE_FILE_MISSING", error_message="Source file not found in storage")

        source_path = source_files[0]

        # Generate clip
        clip_result = self._generate_clip(source_path, media, clip_plan)

        if clip_result:
            media.status = "processed"
            self.session.commit()

            return WorkerResult(
                success=True,
                output={"clip_id": clip_result["clip_id"], "clip_path": clip_result["clip_path"]},
                metrics=clip_result["metrics"],
                artifacts=[clip_result["clip_path"]]
            )

        return WorkerResult(success=False, error_code="CLIP_GENERATION_FAILED", error_message="Failed to generate clip")

    def _generate_clip(self, source_path: Path, media: SourceMedia, clip_plan: Dict) -> Optional[Dict]:
        """Generate clip using FFmpeg"""
        try:
            output_dir = Path(self.settings.storage_dir) / "processed"
            output_dir.mkdir(parents=True, exist_ok=True)

            clip_id = f"{media.campaign_id}_{media.id}_clip_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            output_path = output_dir / f"{clip_id}.mp4"

            # Default clip plan
            start = clip_plan.get("start_seconds", 0)
            duration = clip_plan.get("duration_seconds", min(60, media.duration or 60))
            aspect_ratio = clip_plan.get("aspect_ratio", "9:16")

            # Build FFmpeg command
            if aspect_ratio == "9:16":
                # Vertical crop for TikTok/Reels/Shorts
                vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920"
            elif aspect_ratio == "16:9":
                vf = "scale=1920:1080"
            else:
                vf = "scale=1080:1920"

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", str(source_path),
                "-t", str(duration),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr}")
                return None

            # Calculate clip hash
            clip_hash = self._calculate_hash(output_path)

            # Check duplicate
            existing = self.session.query(Clip).filter(Clip.clip_hash == clip_hash).first()
            if existing:
                output_path.unlink()
                return {"clip_id": existing.id, "clip_path": str(output_path), "duplicate": True, "metrics": {}}

            # Get clip info
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            clip_duration = float(probe_result.stdout.strip()) if probe_result.stdout else duration

            # Store in DB
            clip = Clip(
                campaign_id=media.campaign_id,
                source_media_id=media.id,
                clip_path=str(output_path.relative_to(self.settings.storage_dir)),
                clip_hash=clip_hash,
                aspect_ratio=aspect_ratio,
                duration=clip_duration,
                status="generated"
            )
            self.session.add(clip)
            self.session.flush()

            return {
                "clip_id": clip.id,
                "clip_path": str(output_path.relative_to(self.settings.storage_dir)),
                "metrics": {"duration": clip_duration, "aspect_ratio": aspect_ratio}
            }

        except Exception as e:
            logger.error(f"Clip generation error: {e}")
            return None

    def _calculate_hash(self, filepath: Path) -> str:
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


class QualityCheckWorker(BaseWorker):
    """Automated quality checks for generated clips"""

    def __init__(self):
        super().__init__("quality_check")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        clip_id = payload.get("clip_id")
        if not clip_id:
            return WorkerResult(success=False, error_code="MISSING_CLIP_ID", error_message="clip_id required")

        clip = self.session.query(Clip).filter(Clip.id == clip_id).first()
        if not clip:
            return WorkerResult(success=False, error_code="CLIP_NOT_FOUND", error_message=f"Clip {clip_id} not found")

        # Run quality checks
        checks = self._run_quality_checks(clip)

        passed = all(c["passed"] for c in checks)
        clip.quality_score = sum(1 for c in checks if c["passed"]) / len(checks) * 100
        clip.status = "qc_passed" if passed else "qc_failed"

        self.session.commit()

        return WorkerResult(
            success=passed,
            output={"clip_id": clip_id, "checks": checks, "score": clip.quality_score},
            metrics={"checks_passed": sum(1 for c in checks if c["passed"]), "total_checks": len(checks), "score": clip.quality_score},
            error_code="QC_FAILED" if not passed else None,
            error_message=f"Quality checks failed: {[c['name'] for c in checks if not c['passed']]}" if not passed else None
        )

    def _run_quality_checks(self, clip: Clip) -> List[Dict]:
        """Run automated quality checks"""
        checks = []

        # 1. File exists
        full_path = Path(self.settings.storage_dir) / clip.clip_path
        checks.append({
            "name": "file_exists",
            "passed": full_path.exists(),
            "details": f"Path: {full_path}"
        })

        if not full_path.exists():
            return checks

        # 2. File size > 0
        size = full_path.stat().st_size
        checks.append({
            "name": "file_size",
            "passed": size > 1024,  # > 1KB
            "details": f"Size: {size} bytes"
        })

        # 3. Duration check
        checks.append({
            "name": "duration",
            "passed": 5 <= clip.duration <= 300,  # 5s - 5min
            "details": f"Duration: {clip.duration:.1f}s"
        })

        # 4. Aspect ratio
        checks.append({
            "name": "aspect_ratio",
            "passed": clip.aspect_ratio in ["9:16", "16:9", "1:1"],
            "details": f"Aspect: {clip.aspect_ratio}"
        })

        # 5. FFprobe validation
        try:
            probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,codec_name", "-of", "json", str(full_path)]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                info = json.loads(result.stdout)
                stream = info.get("streams", [{}])[0]
                width = stream.get("width", 0)
                height = stream.get("height", 0)
                codec = stream.get("codec_name", "")

                checks.append({
                    "name": "video_stream",
                    "passed": width > 0 and height > 0,
                    "details": f"{width}x{height} {codec}"
                })

                checks.append({
                    "name": "resolution_min",
                    "passed": width >= 720 and height >= 720,
                    "details": f"Min 720p: {width}x{height}"
                })

                checks.append({
                    "name": "codec_h264",
                    "passed": codec in ["h264", "libx264"],
                    "details": f"Codec: {codec}"
                })
            else:
                checks.append({"name": "video_stream", "passed": False, "details": "ffprobe failed"})
        except Exception as e:
            checks.append({"name": "video_stream", "passed": False, "details": str(e)})

        return checks


class SocialConnectorPublishWorker(BaseWorker):
    """Publish clips to multiple social platforms via Social Connector API"""

    def __init__(self):
        super().__init__("social_connector_publish")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        clip_id = payload.get("clip_id")
        platforms = payload.get("platforms", ["tiktok"])
        caption = payload.get("caption", "")
        schedule = payload.get("schedule", "immediate")

        if not clip_id:
            return WorkerResult(success=False, error_code="MISSING_CLIP_ID", error_message="clip_id required")

        clip = self.session.query(Clip).filter(Clip.id == clip_id).first()
        if not clip:
            return WorkerResult(success=False, error_code="CLIP_NOT_FOUND", error_message=f"Clip {clip_id} not found")

        if clip.status != "qc_passed":
            return WorkerResult(success=False, error_code="CLIP_NOT_READY", error_message=f"Clip {clip_id} has not passed QC")

        # In dry run mode, just simulate publishing to all platforms
        if self.settings.dry_run:
            logger.info(f"DRY RUN: Would publish clip {clip_id} to platforms: {platforms}")
            
            published_posts = []
            for platform in platforms:
                post = PublishedPost(
                    clip_id=clip.id,
                    campaign_id=clip.campaign_id,
                    platform=platform,
                    post_id=f"dryrun_{platform}_{uuid.uuid4().hex[:12]}",
                    status="published",
                    published_at=datetime.now(timezone.utc),
                    metrics=json.dumps({"caption": caption, "platform": platform}),
                    view_count=0,
                    earnings=0.0
                )
                self.session.add(post)
                published_posts.append({
                    "platform": platform,
                    "post_id": post.post_id,
                    "status": "published"
                })
            
            clip.status = "published"
            self.session.commit()
            
            return WorkerResult(
                success=True,
                output={"clip_id": clip_id, "published": published_posts, "dry_run": True},
                metrics={"published": True, "platforms": len(platforms), "dry_run": True}
            )

        # Real publishing via Social Connector API
        import asyncio
        import httpx
        
        results = asyncio.run(self._publish_via_social_connector(clip, platforms, caption, schedule))
        
        # Store results
        published_count = 0
        for result in results:
            post = PublishedPost(
                clip_id=clip.id,
                campaign_id=clip.campaign_id,
                platform=result.provider,
                post_id=result.external_post_id or f"published_{uuid.uuid4().hex[:12]}",
                status="published" if result.success else "failed",
                published_at=datetime.now(timezone.utc),
                metrics=json.dumps({
                    "caption": caption,
                    "platform": result.provider,
                    "external_url": result.external_url,
                    "error": result.error
                }),
                view_count=0,
                earnings=0.0
            )
            self.session.add(post)
            if result.success:
                published_count += 1
        
        clip.status = "published" if published_count > 0 else "publish_failed"
        self.session.commit()
        
        return WorkerResult(
            success=published_count > 0,
            output={
                "clip_id": clip_id, 
                "published": [
                    {
                        "platform": r.provider,
                        "success": r.success,
                        "external_post_id": r.external_post_id,
                        "external_url": r.external_url,
                        "error": r.error
                    }
                    for r in results
                ]
            },
            metrics={"total_platforms": len(platforms), "published": published_count},
            error_code="PARTIAL_PUBLISH" if published_count < len(platforms) and published_count > 0 else None,
            error_message=f"Published to {published_count}/{len(platforms)} platforms" if published_count < len(platforms) else None
        )

    async def _publish_via_social_connector(self, clip: Clip, platforms: List[str], caption: str, schedule: str) -> List:
        """Publish clip via Social Connector API"""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "social-connector"))
        from empire_integration import SocialConnectorClient, SocialPost, PublishResult
        
        # Get clip file path
        clip_path = Path(self.settings.storage_dir) / clip.clip_path
        if not clip_path.exists():
            logger.error(f"Clip file not found: {clip_path}")
            return [PublishResult(
                provider=p, account_id="", success=False, error="Clip file not found"
            ) for p in platforms]
        
        # For real implementation, upload clip to accessible URL
        # For now, use local file path as URL (would need a file server in production)
        media_url = f"file://{clip_path.absolute()}"
        
        client = SocialConnectorClient()
        try:
            # Get connected accounts for target platforms
            accounts = await client.get_accounts()
            
            targets = []
            for platform in platforms:
                platform_accounts = [a for a in accounts if a["provider"] == platform]
                if platform_accounts:
                    for acc in platform_accounts:
                        targets.append({"provider": platform, "account_id": acc["id"]})
                else:
                    logger.warning(f"No connected account for {platform}")
            
            if not targets:
                return [PublishResult(
                    provider=p, account_id="", success=False, error="No connected account"
                ) for p in platforms]
            
            # Create post
            post = SocialPost(
                text=caption,
                media=[{
                    "type": "video",
                    "url": media_url,
                    "mime": "video/mp4",
                    "sha256": clip.clip_hash
                }],
                targets=targets,
                idempotency_key=f"{clip.campaign_id}_{clip.id}_social"
            )
            
            created = await client.create_post(post)
            
            # Poll for results
            post_id = created.get("id")
            if post_id:
                results = await client._wait_for_publish(post_id, targets)
                return results
            
            return [PublishResult(
                provider=p, account_id="", success=False, error="Post creation failed"
            ) for p in platforms]
            
        finally:
            await client.close()


class PublishWorker(BaseWorker):
    """Publish clips to social platforms"""

    def __init__(self):
        super().__init__("publish")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        clip_id = payload.get("clip_id")
        platform = payload.get("platform", "tiktok")
        caption = payload.get("caption", "")
        tags = payload.get("tags", [])

        if not clip_id:
            return WorkerResult(success=False, error_code="MISSING_CLIP_ID", error_message="clip_id required")

        clip = self.session.query(Clip).filter(Clip.id == clip_id).first()
        if not clip:
            return WorkerResult(success=False, error_code="CLIP_NOT_FOUND", error_message=f"Clip {clip_id} not found")

        if clip.status != "qc_passed":
            return WorkerResult(success=False, error_code="CLIP_NOT_READY", error_message=f"Clip {clip_id} has not passed QC")

        # In dry run mode, just simulate publishing
        if self.settings.dry_run:
            logger.info(f"DRY RUN: Would publish clip {clip_id} to {platform}")
            
            # Create published post record
            post = PublishedPost(
                clip_id=clip.id,
                campaign_id=clip.campaign_id,
                platform=platform,
                post_id=f"dryrun_{uuid.uuid4().hex[:12]}",
                status="published",
                published_at=datetime.now(timezone.utc),
                metrics=json.dumps({"caption": caption, "tags": tags}),
                view_count=0,
                earnings=0.0
            )
            self.session.add(post)
            self.session.commit()
            
            return WorkerResult(
                success=True,
                output={"post_id": post.post_id, "clip_id": clip_id, "platform": platform, "dry_run": True},
                metrics={"published": True, "dry_run": True}
            )

        # Real publishing would integrate with platform APIs here
        # For now, simulate success
        post = PublishedPost(
            clip_id=clip.id,
            campaign_id=clip.campaign_id,
            platform=platform,
            post_id=f"published_{uuid.uuid4().hex[:12]}",
            status="published",
            published_at=datetime.now(timezone.utc),
            metrics=json.dumps({"caption": caption, "tags": tags}),
            view_count=0,
            earnings=0.0
        )
        self.session.add(post)
        
        # Update clip status
        clip.status = "published"
        self.session.commit()
        
        return WorkerResult(
            success=True,
            output={"post_id": post.post_id, "clip_id": clip_id, "platform": platform},
            metrics={"published": True}
        )


# Register all workers
WorkerRegistry.register(CampaignDiscoveryWorker())
WorkerRegistry.register(CampaignParserWorker())
WorkerRegistry.register(SourceDownloadWorker())
WorkerRegistry.register(ClipGeneratorWorker())
WorkerRegistry.register(QualityCheckWorker())
WorkerRegistry.register(SocialConnectorPublishWorker())
WorkerRegistry.register(PublishWorker())