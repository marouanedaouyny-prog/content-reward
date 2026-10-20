# Recovery Skill
# Handles failed job recovery, retries, and dead letter processing

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging

from project.db.models import (
    Session, Job, JobStatus, JobType, Submission, SubmissionStatus, 
    SocialPost, SocialPostStatus, Clip, init_db
)
from project.config.settings import get_settings

logger = logging.getLogger(__name__)


class RecoverySkill:
    """Skill for recovering failed jobs and handling retries."""
    
    def __init__(self, db_session: Session = None):
        self.db = db_session or init_db()
        self.settings = get_settings()
    
    def recover_failed_jobs(self) -> Dict[str, int]:
        """Recover failed jobs that are eligible for retry."""
        results = {"requeued": 0, "dead_lettered": 0, "verified_external": 0}
        
        # Get failed jobs that are retryable and haven't exceeded max attempts
        failed_jobs = self.db.query(Job).filter(
            Job.status == JobStatus.FAILED,
            Job.retryable == True,
            Job.attempt < Job.max_attempts,
            Job.next_run_at <= datetime.now(timezone.utc)
        ).all()
        
        for job in failed_jobs:
            try:
                result = self._recover_job(job)
                if result == "REQUEUED":
                    results["requeued"] += 1
                elif result == "DEAD_LETTER":
                    results["dead_lettered"] += 1
                elif result == "VERIFIED_EXTERNAL":
                    results["verified_external"] += 1
            except Exception as e:
                logger.error(f"Failed to recover job {job.id}: {e}")
        
        return results
    
    def _recover_job(self, job: Job) -> str:
        """Attempt to recover a single failed job."""
        # First, check if the external action actually succeeded
        external_status = self._check_external_status(job)
        
        if external_status == "SUCCEEDED":
            # External action succeeded - mark job as succeeded
            job.status = JobStatus.SUCCEEDED
            job.completed_at = datetime.now(timezone.utc)
            job.error_code = None
            job.error_message = None
            self._update_related_state(job)
            self.db.commit()
            logger.info(f"Job {job.id} verified as succeeded externally")
            return "VERIFIED_EXTERNAL"
        
        elif external_status == "FAILED":
            # External action confirmed failed - retry
            return self._requeue_job(job)
        
        else:
            # Unknown status - requeue for retry
            return self._requeue_job(job)
    
    def _check_external_status(self, job: Job) -> str:
        """Check the actual status of the external operation."""
        if job.type == JobType.PUBLISH:
            return self._check_publish_status(job)
        elif job.type == JobType.SUBMIT:
            return self._check_submit_status(job)
        elif job.type == JobType.UPLOAD:
            return self._check_upload_status(job)
        elif job.type == JobType.ANALYTICS_SYNC:
            return self._check_analytics_status(job)
        elif job.type == JobType.TOKEN_REFRESH:
            return self._check_token_status(job)
        elif job.type == JobType.PAYOUT_CHECK:
            return self._check_payout_status(job)
        
        return "UNKNOWN"
    
    def _check_publish_status(self, job: Job) -> str:
        """Check if a publish actually succeeded by querying the platform."""
        idempotency_key = job.idempotency_key
        # Parse: publish:{platform}:{clip_id}:{account_id}:{timestamp}
        parts = idempotency_key.split(":")
        if len(parts) >= 4:
            platform = parts[1]
            clip_id = parts[2]
            account_id = parts[3]
            
            # Check if SocialPost exists with this platform_post_id
            post = self.db.query(SocialPost).filter(
                SocialPost.clip_id == clip_id,
                SocialPost.social_account_id == account_id,
                SocialPost.platform == platform.upper()
            ).first()
            
            if post and post.status == SocialPostStatus.PUBLISHED:
                return "SUCCEEDED"
        
        return "UNKNOWN"
    
    def _check_submit_status(self, job: Job) -> str:
        """Check if a submission to CR succeeded."""
        idempotency_key = job.idempotency_key
        # Parse: submit:{campaign_id}:{creator_id}:{clip_url_hash}
        
        # Check if Submission exists
        submission = self.db.query(Submission).filter(
            Submission.idempotency_key == idempotency_key
        ).first()
        
        if submission and submission.status in [
            SubmissionStatus.SUBMITTED, SubmissionStatus.BOT_TRIAGE,
            SubmissionStatus.FLAGGED, SubmissionStatus.BRAND_REVIEW,
            SubmissionStatus.APPROVED, SubmissionStatus.VALIDATING,
            SubmissionStatus.TRACKING, SubmissionStatus.PAID
        ]:
            return "SUCCEEDED"
        
        return "UNKNOWN"
    
    def _check_upload_status(self, job: Job) -> str:
        """Check if media upload succeeded."""
        # Would check platform-specific media ID
        return "UNKNOWN"
    
    def _check_analytics_status(self, job: Job) -> str:
        """Check if analytics sync succeeded."""
        # Check if AnalyticsSnapshot was created
        # Simplified for now
        return "UNKNOWN"
    
    def _check_token_status(self, job: Job) -> str:
        """Check if token refresh succeeded."""
        # Would verify new token works
        return "UNKNOWN"
    
    def _check_payout_status(self, job: Job) -> str:
        """Check if payout check succeeded."""
        return "UNKNOWN"
    
    def _requeue_job(self, job: Job) -> str:
        """Requeue a job for retry with exponential backoff."""
        job.attempt += 1
        job.status = JobStatus.QUEUED
        job.error_code = None
        job.error_message = None
        
        # Exponential backoff
        backoff_seconds = self._get_backoff(job.attempt)
        job.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
        
        self.db.commit()
        logger.info(f"Job {job.id} requeued for attempt {job.attempt}, next run in {backoff_seconds}s")
        return "REQUEUED"
    
    def _get_backoff(self, attempt: int) -> int:
        """Calculate exponential backoff."""
        base = 30  # seconds
        max_backoff = 3600  # 1 hour
        backoff = base * (2 ** (attempt - 1))
        return min(backoff, max_backoff)
    
    def _update_related_state(self, job: Job):
        """Update related entity states based on job completion."""
        if job.type == JobType.PUBLISH:
            # Update Clip status to PUBLISHED
            # Extract clip_id from idempotency_key
            pass
        elif job.type == JobType.SUBMIT:
            # Update Submission state
            pass
    
    def dead_letter_jobs(self) -> int:
        """Move jobs that exceeded max attempts to dead letter."""
        dead_lettered = 0
        
        dead_jobs = self.db.query(Job).filter(
            Job.status == JobStatus.FAILED,
            Job.retryable == True,
            Job.attempt >= Job.max_attempts
        ).all()
        
        for job in dead_jobs:
            job.status = JobStatus.CANCELLED
            job.error_code = "MAX_ATTEMPTS_EXCEEDED"
            job.error_message = f"Job failed after {job.max_attempts} attempts"
            self.db.commit()
            dead_lettered += 1
            logger.warning(f"Job {job.id} moved to dead letter after {job.attempt} attempts")
        
        return dead_lettered
    
    def restart_stuck_jobs(self, timeout_minutes: int = 30) -> int:
        """Restart jobs stuck in RUNNING state."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        restarted = 0
        
        stuck_jobs = self.db.query(Job).filter(
            Job.status == JobStatus.RUNNING,
            Job.started_at < cutoff
        ).all()
        
        for job in stuck_jobs:
            job.status = JobStatus.QUEUED
            job.started_at = None
            job.attempt += 1
            job.next_run_at = datetime.now(timezone.utc)
            self.db.commit()
            restarted += 1
            logger.warning(f"Job {job.id} restarted after being stuck in RUNNING for >{timeout_minutes}min")
        
        return restarted


def recover_jobs() -> Dict[str, int]:
    """Entry point for cron job."""
    skill = RecoverySkill()
    results = skill.recover_failed_jobs()
    results["dead_lettered"] += skill.dead_letter_jobs()
    results["restarted"] = skill.restart_stuck_jobs()
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = recover_jobs()
    print(f"Recovery results: {result}")