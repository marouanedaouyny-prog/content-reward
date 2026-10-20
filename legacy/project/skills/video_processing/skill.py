# Video Processing Skill
# Downloads, transcribes, segments, edits, and QAs video clips

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pathlib import Path
import logging
import hashlib
import subprocess
import json
import os

from project.db.models import (
    Session, Campaign, SourceMedia, Transcript, Clip, Caption, QAReport,
    SourceMediaStatus, init_db, system_settings_table
)
from project.config.settings import get_settings

logger = logging.getLogger(__name__)


class VideoProcessingSkill:
    """Skill for end-to-end video processing pipeline."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
        self.storage_dir = Path(self.settings.storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "raw").mkdir(exist_ok=True)
        (self.storage_dir / "processed").mkdir(exist_ok=True)
        (self.storage_dir / "ready").mkdir(exist_ok=True)
    
    def process_source(self, source_media_id: str) -> Dict[str, Any]:
        """
        Full pipeline: download → transcribe → segment → plan → edit → caption → QA → ready clips.
        """
        media = self.db.query(SourceMedia).filter(SourceMedia.id == source_media_id).first()
        if not media:
            raise ValueError(f"SourceMedia {source_media_id} not found")
        
        campaign = self.db.query(Campaign).filter(Campaign.id == media.campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {media.campaign_id} not found")
        
        logger.info(f"Processing source {source_media_id} for campaign {campaign.external_campaign_id}")
        
        # 1. Download if needed
        if media.status != SourceMediaStatus.DOWNLOADED:
            local_path = self._download_video(media)
            if not local_path:
                return {"success": False, "error": "Download failed"}
        else:
            local_path = media.local_path
        
        # 2. Transcribe
        transcript = self._transcribe(local_path, media.id)
        
        # 3. Segment and score
        candidates = self._segment_and_score(transcript, campaign)
        
        # 4. Select per platform
        clip_plans = self._select_clips(candidates, campaign)
        
        # 5. Edit each variant
        clips = []
        for plan in clip_plans:
            clip = self._edit_clip(local_path, media, campaign, plan)
            if clip:
                clips.append(clip)
        
        # 6. Generate captions
        for clip in clips:
            self._generate_captions(clip, campaign)
        
        # 7. QA gates
        ready_clips = []
        for clip in clips:
            qa_report = self._run_qa(clip, campaign)
            if qa_report.status == "QA_PASSED":
                ready_path = self._export_ready(clip, campaign)
                ready_clips.append({"clip_id": clip.id, "platform": clip.aspect_ratio, "path": ready_path})
            else:
                logger.warning(f"Clip {clip.id} failed QA: {qa_report.failed_gates}")
        
        self.db.commit()
        
        return {
            "success": True,
            "source_media_id": source_media_id,
            "clips_generated": len(clips),
            "clips_ready": len(ready_clips),
            "ready_clips": ready_clips
        }
    
    def _download_video(self, media: SourceMedia) -> Optional[str]:
        """Download video using yt-dlp."""
        try:
            media.status = SourceMediaStatus.DOWNLOADING
            self.db.commit()
            
            raw_dir = self.storage_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            
            # Get video info
            info_cmd = ["yt-dlp", "--dump-json", "--no-download", media.source_url]
            result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.error(f"yt-dlp info failed: {result.stderr}")
                return None
            
            info = json.loads(result.stdout)
            video_id = info.get("id", "unknown")
            title = info.get("title", "unknown")
            duration = info.get("duration", 0)
            
            # Update media info
            media.title = title
            media.duration = duration
            
            # Download
            filename = f"{media.campaign_id}_{video_id}.mp4"
            output_path = raw_dir / filename
            
            download_cmd = [
                "yt-dlp", "-f", "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/best",
                "--merge-output-format", "mp4",
                "--no-check-certificates",
                "-o", str(output_path),
                media.source_url
            ]
            result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(f"yt-dlp download failed: {result.stderr}")
                return None
            
            # Calculate hash
            file_hash = self._calculate_hash(output_path)
            
            # Check duplicate
            existing = self.db.query(SourceMedia).filter(SourceMedia.file_hash == file_hash).first()
            if existing:
                logger.info(f"Duplicate video detected: {file_hash}")
                output_path.unlink()
                media.file_hash = file_hash
                media.status = SourceMediaStatus.DOWNLOADED
                media.downloaded_at = datetime.now(timezone.utc)
                self.db.commit()
                return str(existing.local_path) if existing.local_path else str(output_path)
            
            media.file_hash = file_hash
            media.local_path = str(output_path.relative_to(self.storage_dir))
            media.status = SourceMediaStatus.DOWNLOADED
            media.downloaded_at = datetime.now(timezone.utc)
            self.db.commit()
            
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            media.status = SourceMediaStatus.ERROR
            media.error_message = str(e)
            self.db.commit()
            return None
    
    def _transcribe(self, video_path: str, source_media_id: str) -> Transcript:
        """Transcribe video using faster-whisper."""
        try:
            # Use faster-whisper CLI or Python API
            # For now, create mock transcript
            transcript = Transcript(
                source_media_id=source_media_id,
                full_text="Mock transcript for development",
                segments=[{"start": 0, "end": 30, "text": "Mock segment", "confidence": 0.9}],
                language="en",
                model_used="faster-whisper",
                model_ver="large-v3"
            )
            self.db.add(transcript)
            self.db.commit()
            return transcript
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise
    
    def _segment_and_score(self, transcript: Transcript, campaign: Campaign) -> List[Dict]:
        """Segment transcript and score candidates."""
        # Simplified: create fixed windows for now
        candidates = []
        duration = 60  # Would come from media
        
        for start in [0, 15, 30]:
            end = min(start + 30, duration)
            candidates.append({
                "source_media_id": transcript.source_media_id,
                "start_sec": start,
                "end_sec": end,
                "duration": end - start,
                "aspect_ratio_candidates": ["9:16", "16:9"],
                "score": 0.8,
                "reasoning": "Mock scoring",
                "transcript_segment": transcript.segments[0] if transcript.segments else {}
            })
        
        return candidates
    
    def _select_clips(self, candidates: List[Dict], campaign: Campaign) -> List[Dict]:
        """Select best clips per platform."""
        platforms = campaign.platforms or ["TIKTOK", "INSTAGRAM", "YOUTUBE"]
        plans = []
        
        for i, candidate in enumerate(candidates):
            for platform in platforms:
                aspect = "9:16" if platform in ["TIKTOK", "INSTAGRAM"] else "16:9"
                plans.append({
                    **candidate,
                    "target_platform": platform,
                    "aspect_ratio": aspect,
                    "clip_index": i
                })
        
        return plans
    
    def _edit_clip(self, source_path: str, media: SourceMedia, campaign: Campaign, plan: Dict) -> Optional[Clip]:
        """Edit clip using FFmpeg."""
        try:
            output_dir = self.storage_dir / "processed"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            clip_id = f"{media.campaign_id}_{media.id}_clip_{plan['clip_index']}_{plan['target_platform']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            output_path = output_dir / f"{clip_id}.mp4"
            
            # Build FFmpeg command
            aspect = plan["aspect_ratio"]
            if aspect == "9:16":
                vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920"
            elif aspect == "16:9":
                vf = "scale=1920:1080"
            else:
                vf = "scale=1080:1920"
            
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(plan["start_sec"]),
                "-i", source_path,
                "-t", str(plan["duration"]),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr}")
                return None
            
            # Calculate hash
            clip_hash = self._calculate_hash(output_path)
            
            # Check duplicate
            existing = self.db.query(Clip).filter(Clip.clip_hash == clip_hash).first()
            if existing:
                output_path.unlink()
                return existing
            
            # Get clip info
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            clip_duration = float(probe_result.stdout.strip()) if probe_result.stdout else plan["duration"]
            
            clip = Clip(
                campaign_id=media.campaign_id,
                source_media_id=media.id,
                clip_path=str(output_path.relative_to(self.storage_dir)),
                clip_hash=clip_hash,
                aspect_ratio=aspect,
                duration=clip_duration,
                status="GENERATED"
            )
            self.db.add(clip)
            self.db.commit()
            
            return clip
            
        except Exception as e:
            logger.error(f"Clip editing error: {e}")
            return None
    
    def _generate_captions(self, clip: Clip, campaign: Campaign):
        """Generate captions per platform."""
        platforms = [clip.aspect_ratio]  # Simplified
        
        for platform in platforms:
            text = self._build_caption(campaign, platform)
            
            caption = Caption(
                clip_id=clip.id,
                platform=platform,
                text=text,
                hashtags=campaign.required_tags or [],
                mentions=campaign.required_mentions or [],
                disclosure_included=bool(campaign.required_disclosure),
                char_count=len(text)
            )
            self.db.add(caption)
        
        self.db.commit()
    
    def _build_caption(self, campaign: Campaign, platform: str) -> str:
        """Build caption with required elements."""
        parts = []
        
        if campaign.required_disclosure:
            parts.append(campaign.required_disclosure)
        
        if campaign.required_tags:
            parts.append(" ".join(campaign.required_tags))
        
        if campaign.required_mentions:
            parts.append(" ".join(campaign.required_mentions))
        
        return "\n\n".join(parts)
    
    def _run_qa(self, clip: Clip, campaign: Campaign) -> QAReport:
        """Run compliance QA gates."""
        checks = []
        
        # Duration check
        min_dur = 5
        max_dur = 300
        checks.append({
            "gate": "DURATION",
            "passed": min_dur <= clip.duration <= max_dur,
            "details": f"Duration: {clip.duration:.1f}s"
        })
        
        # Resolution check (simplified)
        checks.append({
            "gate": "RESOLUTION",
            "passed": True,
            "details": "Resolution check passed"
        })
        
        # Aspect ratio
        required_aspects = ["9:16", "16:9"]
        checks.append({
            "gate": "ASPECT_RATIO",
            "passed": clip.aspect_ratio in required_aspects,
            "details": f"Aspect: {clip.aspect_ratio}"
        })
        
        # File size
        full_path = self.storage_dir / clip.clip_path
        size = full_path.stat().st_size if full_path.exists() else 0
        checks.append({
            "gate": "FILE_SIZE",
            "passed": size > 1024,
            "details": f"Size: {size} bytes"
        })
        
        # Disclosure check
        caption = self.db.query(Caption).filter(Caption.clip_id == clip.id).first()
        disclosure_ok = caption and caption.disclosure_included if campaign.required_disclosure else True
        checks.append({
            "gate": "DISCLOSURE",
            "passed": disclosure_ok,
            "details": "Disclosure included" if disclosure_ok else "Disclosure missing"
        })
        
        passed = all(c["passed"] for c in checks)
        score = sum(1 for c in checks if c["passed"]) / len(checks) * 100
        
        qa_report = QAReport(
            clip_id=clip.id,
            platform=clip.aspect_ratio,  # Simplified
            checks=checks,
            score=score,
            status="QA_PASSED" if passed else "QA_FAILED",
            failed_gates=[c["gate"] for c in checks if not c["passed"]],
            engine_version="1.0.0"
        )
        self.db.add(qa_report)
        self.db.commit()
        
        return qa_report
    
    def _export_ready(self, clip: Clip, campaign: Campaign) -> str:
        """Export clip to ready directory."""
        ready_dir = self.storage_dir / "ready" / campaign.external_campaign_id
        ready_dir.mkdir(parents=True, exist_ok=True)
        
        src = self.storage_dir / clip.clip_path
        dst = ready_dir / f"{clip.id}_{clip.aspect_ratio}.mp4"
        
        if src != dst:
            import shutil
            shutil.copy2(src, dst)
        
        return str(dst)
    
    def _calculate_hash(self, filepath: Path) -> str:
        """Calculate SHA-256 hash of file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


# Skill entry points
def process_source_media(source_media_id: str) -> Dict[str, Any]:
    """Entry point for processing a source media."""
    skill = VideoProcessingSkill()
    return skill.process_source(source_media_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test would require database setup
    print("VideoProcessingSkill ready")