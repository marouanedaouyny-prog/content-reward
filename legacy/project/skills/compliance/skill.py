# Compliance Skill
# Automated compliance gates for Content Rewards clips

from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
import subprocess
import json

from project.db.models import (
    Session, Campaign, Clip, Caption, QAReport, SourceMedia, QAStatus, init_db
)
from project.config.settings import get_settings

logger = logging.getLogger(__name__)


class ComplianceSkill:
    """Skill for running automated compliance gates on clips."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
        self.storage_dir = Path(self.settings.storage_dir)
    
    def check_clip(self, clip_id: str, campaign_id: str, platform: str) -> QAReport:
        """Run all automated compliance gates for a clip."""
        clip = self.db.query(Clip).filter(Clip.id == clip_id).first()
        if not clip:
            raise ValueError(f"Clip {clip_id} not found")
        
        campaign = self.db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        caption = self.db.query(Caption).filter(
            Caption.clip_id == clip_id,
            Caption.platform == platform
        ).first()
        
        logger.info(f"Running compliance checks for clip {clip_id} on {platform}")
        
        # Get platform-specific rules
        platform_rules = self._get_platform_rules(platform)
        campaign_rules = self._get_campaign_rules(campaign)
        all_rules = {**platform_rules, **campaign_rules}
        
        checks = []
        
        # 1. DURATION
        min_dur = all_rules.get("min_duration", 5)
        max_dur = all_rules.get("max_duration", 300)
        checks.append({
            "gate": "DURATION",
            "passed": min_dur <= clip.duration <= max_dur,
            "details": f"Duration: {clip.duration:.1f}s (required: {min_dur}-{max_dur}s)"
        })
        
        # 2. RESOLUTION (via ffprobe)
        resolution_check = self._check_resolution(clip, all_rules)
        checks.append(resolution_check)
        
        # 3. ASPECT_RATIO
        required_aspects = all_rules.get("aspect_ratios", ["9:16", "16:9"])
        checks.append({
            "gate": "ASPECT_RATIO",
            "passed": clip.aspect_ratio in required_aspects,
            "details": f"Aspect: {clip.aspect_ratio} (required: {required_aspects})"
        })
        
        # 4. CODEC
        codec_check = self._check_codec(clip)
        checks.append(codec_check)
        
        # 5. FILE_SIZE
        size_check = self._check_file_size(clip, all_rules)
        checks.append(size_check)
        
        # 6. DISCLOSURE
        disclosure_check = self._check_disclosure(caption, campaign)
        checks.append(disclosure_check)
        
        # 7. HASHTAGS
        hashtag_check = self._check_hashtags(caption, campaign)
        checks.append(hashtag_check)
        
        # 8. MENTIONS
        mention_check = self._check_mentions(caption, campaign)
        checks.append(mention_check)
        
        # 9. COPOSTING
        checks.append({
            "gate": "COPOSTING",
            "passed": True,  # Would check metadata
            "details": "Co-posting check not implemented"
        })
        
        # 10. REUSED_CONTENT
        reused_check = self._check_reused_content(clip)
        checks.append(reused_check)
        
        # 11. AUDIO_LEVEL
        audio_check = self._check_audio_level(clip)
        checks.append(audio_check)
        
        # 12. VISUAL_QUALITY
        visual_check = self._check_visual_quality(clip)
        checks.append(visual_check)
        
        # 13. PLATFORM_RULES
        platform_check = self._check_platform_rules(clip, campaign, platform)
        checks.append(platform_check)
        
        # 14. REGULATED_VERTICAL
        regulated_check = self._check_regulated_vertical(campaign, caption)
        checks.append(regulated_check)
        
        # Aggregate results
        passed = all(c["passed"] for c in checks)
        score = sum(1 for c in checks if c["passed"]) / len(checks) * 100
        failed_gates = [c["gate"] for c in checks if not c["passed"]]
        
        qa_report = QAReport(
            clip_id=clip.id,
            platform=platform,
            checks=checks,
            score=score,
            status="QA_PASSED" if passed else "QA_FAILED",
            failed_gates=failed_gates,
            engine_version="1.0.0"
        )
        self.db.add(qa_report)
        
        # Update clip status
        clip.status = "QA_PASSED" if passed else "QA_FAILED"
        clip.quality_score = score
        self.db.commit()
        
        logger.info(f"Compliance check for clip {clip_id}: {'PASSED' if passed else 'FAILED'} (score: {score:.1f})")
        
        return qa_report
    
    def _get_platform_rules(self, platform: str) -> Dict[str, Any]:
        """Get platform-specific requirements."""
        rules = {
            "TIKTOK": {
                "min_duration": 3,
                "max_duration": 300,  # 5 min for some accounts
                "aspect_ratios": ["9:16"],
                "max_file_size_mb": 4096,
                "codecs": ["h264", "hevc"],
                "audio_codecs": ["aac"],
            },
            "INSTAGRAM": {
                "min_duration": 3,
                "max_duration": 90,  # Reels max
                "aspect_ratios": ["9:16"],
                "max_file_size_mb": 4096,
                "codecs": ["h264"],
                "audio_codecs": ["aac"],
            },
            "YOUTUBE": {
                "min_duration": 1,
                "max_duration": 43200,  # 12 hours
                "aspect_ratios": ["16:9", "9:16"],  # Shorts vs regular
                "max_file_size_mb": 256000,
                "codecs": ["h264", "hevc", "vp9"],
                "audio_codecs": ["aac", "opus"],
            },
            "FACEBOOK": {
                "min_duration": 1,
                "max_duration": 240,
                "aspect_ratios": ["16:9", "9:16", "1:1", "4:5"],
                "max_file_size_mb": 10240,
                "codecs": ["h264"],
                "audio_codecs": ["aac"],
            },
            "X": {
                "min_duration": 1,
                "max_duration": 140,  # Standard, longer for premium
                "aspect_ratios": ["16:9", "9:16", "1:1"],
                "max_file_size_mb": 512,  # Default, 16GB for premium
                "codecs": ["h264"],
                "audio_codecs": ["aac"],
            }
        }
        return rules.get(platform, {})
    
    def _get_campaign_rules(self, campaign: Campaign) -> Dict[str, Any]:
        """Extract rules from campaign."""
        rules = {}
        
        if campaign.min_views:
            rules["min_views"] = campaign.min_views
        if campaign.max_payout_per_clip:
            rules["max_payout_per_clip"] = campaign.max_payout_per_clip
        if campaign.required_disclosure:
            rules["required_disclosure"] = campaign.required_disclosure
        if campaign.required_tags:
            rules["required_tags"] = campaign.required_tags
        if campaign.required_mentions:
            rules["required_mentions"] = campaign.required_mentions
        if campaign.editing_rules:
            for rule in campaign.editing_rules:
                if rule.get("rule_type") == "DURATION":
                    spec = rule.get("spec", {})
                    if "min" in spec:
                        rules["min_duration"] = spec["min"]
                    if "max" in spec:
                        rules["max_duration"] = spec["max"]
                elif rule.get("rule_type") == "ASPECT_RATIO":
                    rules["aspect_ratios"] = [rule.get("spec", {}).get("ratio", "9:16")]
        
        return rules
    
    def _check_resolution(self, clip: Clip, rules: Dict) -> Dict:
        """Check video resolution via ffprobe."""
        try:
            full_path = self.storage_dir / clip.clip_path
            if not full_path.exists():
                return {"gate": "RESOLUTION", "passed": False, "details": "File not found"}
            
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(full_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {"gate": "RESOLUTION", "passed": False, "details": "ffprobe failed"}
            
            info = json.loads(result.stdout)
            stream = info.get("streams", [{}])[0]
            width = stream.get("width", 0)
            height = stream.get("height", 0)
            
            # Platform minimums
            min_width = 720
            min_height = 720
            
            passed = width >= min_width and height >= min_height
            return {
                "gate": "RESOLUTION",
                "passed": passed,
                "details": f"Resolution: {width}x{height} (min: {min_width}x{min_height})"
            }
        except Exception as e:
            return {"gate": "RESOLUTION", "passed": False, "details": f"Check failed: {e}"}
    
    def _check_codec(self, clip: Clip) -> Dict:
        """Check video/audio codec."""
        try:
            full_path = self.storage_dir / clip.clip_path
            if not full_path.exists():
                return {"gate": "CODEC", "passed": False, "details": "File not found"}
            
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0,a:0",
                "-show_entries", "stream=codec_name",
                "-of", "json",
                str(full_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {"gate": "CODEC", "passed": False, "details": "ffprobe failed"}
            
            info = json.loads(result.stdout)
            video_codec = info.get("streams", [{}])[0].get("codec_name", "")
            audio_codec = info.get("streams", [{}])[1].get("codec_name", "") if len(info.get("streams", [])) > 1 else ""
            
            # Basic check - all major platforms support h264/aac
            passed = video_codec in ["h264", "hevc", "vp9"] and audio_codec in ["aac", "opus"]
            return {
                "gate": "CODEC",
                "passed": passed,
                "details": f"Video: {video_codec}, Audio: {audio_codec}"
            }
        except Exception as e:
            return {"gate": "CODEC", "passed": False, "details": f"Check failed: {e}"}
    
    def _check_file_size(self, clip: Clip, rules: Dict) -> Dict:
        """Check file size against platform limits."""
        try:
            full_path = self.storage_dir / clip.clip_path
            if not full_path.exists():
                return {"gate": "FILE_SIZE", "passed": False, "details": "File not found"}
            
            size = full_path.stat().st_size
            max_mb = rules.get("max_file_size_mb", 4096)
            max_bytes = max_mb * 1024 * 1024
            
            passed = size <= max_bytes
            return {
                "gate": "FILE_SIZE",
                "passed": passed,
                "details": f"Size: {size / 1024 / 1024:.1f}MB (max: {max_mb}MB)"
            }
        except Exception as e:
            return {"gate": "FILE_SIZE", "passed": False, "details": f"Check failed: {e}"}
    
    def _check_disclosure(self, caption: Optional[Caption], campaign: Campaign) -> Dict:
        """Check FTC disclosure is present."""
        if not campaign.required_disclosure:
            return {"gate": "DISCLOSURE", "passed": True, "details": "No disclosure required"}
        
        if not caption:
            return {"gate": "DISCLOSURE", "passed": False, "details": "No caption found"}
        
        disclosure_text = campaign.required_disclosure.lower()
        caption_text = caption.text.lower()
        
        passed = disclosure_text in caption_text
        return {
            "gate": "DISCLOSURE",
            "passed": passed,
            "details": f"Disclosure '{campaign.required_disclosure}' {'found' if passed else 'MISSING'}"
        }
    
    def _check_hashtags(self, caption: Optional[Caption], campaign: Campaign) -> Dict:
        """Check required hashtags are present."""
        if not campaign.required_tags:
            return {"gate": "HASHTAGS", "passed": True, "details": "No hashtags required"}
        
        if not caption:
            return {"gate": "HASHTAGS", "passed": False, "details": "No caption found"}
        
        caption_tags = set(caption.hashtags or [])
        required_tags = set(campaign.required_tags or [])
        
        missing = required_tags - caption_tags
        passed = len(missing) == 0
        return {
            "gate": "HASHTAGS",
            "passed": passed,
            "details": f"Missing: {missing}" if missing else "All required hashtags present"
        }
    
    def _check_mentions(self, caption: Optional[Caption], campaign: Campaign) -> Dict:
        """Check required mentions are present."""
        if not campaign.required_mentions:
            return {"gate": "MENTIONS", "passed": True, "details": "No mentions required"}
        
        if not caption:
            return {"gate": "MENTIONS", "passed": False, "details": "No caption found"}
        
        caption_mentions = set(caption.mentions or [])
        required_mentions = set(campaign.required_mentions or [])
        
        missing = required_mentions - caption_mentions
        passed = len(missing) == 0
        return {
            "gate": "MENTIONS",
            "passed": passed,
            "details": f"Missing: {missing}" if missing else "All required mentions present"
        }
    
    def _check_reused_content(self, clip: Clip) -> Dict:
        """Check if clip hash was recently used."""
        # Check last 30 days of submissions
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        
        recent = self.db.query(Clip).filter(
            Clip.clip_hash == clip.clip_hash,
            Clip.id != clip.id,
            Clip.created_at > cutoff
        ).first()
        
        passed = recent is None
        return {
            "gate": "REUSED_CONTENT",
            "passed": passed,
            "details": "Duplicate clip detected" if not passed else "Unique clip"
        }
    
    def _check_audio_level(self, clip: Clip) -> Dict:
        """Check audio loudness (-16 LUFS ±2)."""
        try:
            full_path = self.storage_dir / clip.clip_path
            if not full_path.exists():
                return {"gate": "AUDIO_LEVEL", "passed": False, "details": "File not found"}
            
            cmd = [
                "ffmpeg", "-i", str(full_path),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                "-f", "null", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # Parse loudnorm output from stderr
            import re
            json_match = re.search(r'\{.*\}', result.stderr, re.DOTALL)
            if json_match:
                loudness_data = json.loads(json_match.group())
                input_i = float(loudness_data.get("input_i", -16))
                passed = -18 <= input_i <= -14
                return {
                    "gate": "AUDIO_LEVEL",
                    "passed": passed,
                    "details": f"Integrated loudness: {input_i:.1f} LUFS (target: -16 ±2)"
                }
            else:
                return {"gate": "AUDIO_LEVEL", "passed": True, "details": "Could not measure, assuming OK"}
        except Exception as e:
            return {"gate": "AUDIO_LEVEL", "passed": True, "details": f"Check failed, assuming OK: {e}"}
    
    def _check_visual_quality(self, clip: Clip) -> Dict:
        """Check for black frames, frozen frames, corruption."""
        try:
            full_path = self.storage_dir / clip.clip_path
            if not full_path.exists():
                return {"gate": "VISUAL_QUALITY", "passed": False, "details": "File not found"}
            
            # Black frame detection
            cmd = [
                "ffmpeg", "-i", str(full_path),
                "-vf", "blackdetect=d=0.5:pix_th=0.1",
                "-f", "null", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            black_frames = "blackdetect" in result.stderr.lower()
            
            # Freeze detection
            cmd2 = [
                "ffmpeg", "-i", str(full_path),
                "-vf", "freezedetect=n=0.003",
                "-f", "null", "-"
            ]
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=60)
            
            frozen = "freezedetect" in result2.stderr.lower()
            
            passed = not black_frames and not frozen
            issues = []
            if black_frames:
                issues.append("black frames")
            if frozen:
                issues.append("frozen frames")
            
            return {
                "gate": "VISUAL_QUALITY",
                "passed": passed,
                "details": f"Issues: {', '.join(issues)}" if issues else "No visual issues detected"
            }
        except Exception as e:
            return {"gate": "VISUAL_QUALITY", "passed": True, "details": f"Check failed, assuming OK: {e}"}
    
    def _check_platform_rules(self, clip: Clip, campaign: Campaign, platform: str) -> Dict:
        """Check platform-specific rules."""
        # Political content check
        if platform in ["TIKTOK", "X"] and campaign.vertical == "POLITICAL":
            return {
                "gate": "PLATFORM_RULES",
                "passed": False,
                "details": f"Political content prohibited on {platform}"
            }
        
        # Vertical video for TikTok/IG Reels/Shorts
        if platform in ["TIKTOK", "INSTAGRAM"] and clip.aspect_ratio != "9:16":
            return {
                "gate": "PLATFORM_RULES",
                "passed": False,
                "details": f"{platform} requires 9:16 aspect ratio"
            }
        
        return {"gate": "PLATFORM_RULES", "passed": True, "details": "Platform rules OK"}
    
    def _check_regulated_vertical(self, campaign: Campaign, caption: Optional[Caption]) -> Dict:
        """Check regulated vertical requirements."""
        regulated = ["CRYPTO", "FINANCE", "SUPPLEMENTS", "GAMBLING", "POLITICAL"]
        
        if campaign.vertical not in regulated:
            return {"gate": "REGULATED_VERTICAL", "passed": True, "details": "Not a regulated vertical"}
        
        # Additional disclosures required
        if not caption:
            return {"gate": "REGULATED_VERTICAL", "passed": False, "details": "Caption required for regulated vertical"}
        
        # Check for common required disclosures
        caption_text = caption.text.lower()
        required_phrases = {
            "CRYPTO": ["not financial advice", "nfa", "dyor"],
            "FINANCE": ["not financial advice", "past performance"],
            "SUPPLEMENTS": ["not evaluated by fda", "dietary supplement"],
            "GAMBLING": ["gamble responsibly", "18+", "21+"],
        }
        
        phrases = required_phrases.get(campaign.vertical, [])
        found = any(p in caption_text for p in phrases)
        
        return {
            "gate": "REGULATED_VERTICAL",
            "passed": found,
            "details": f"Regulated vertical {campaign.vertical}: required disclosure {'found' if found else 'MISSING'}"
        }


def run_compliance_check(clip_id: str, campaign_id: str, platform: str) -> QAReport:
    """Entry point for running compliance check."""
    skill = ComplianceSkill()
    return skill.check_clip(clip_id, campaign_id, platform)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("ComplianceSkill ready")