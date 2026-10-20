#!/usr/bin/env python3
"""
Automation Empire OS — Base Worker Class
$0 constraint: local-first, no paid dependencies
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone
import json
import uuid
import logging
import traceback
from pathlib import Path

# Local imports
from backend.app.core.config import get_settings
from backend.app.core.db import init_db, Job, JobStatus, JobAttempt, WorkflowVersion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    """Standardized worker output"""
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = True
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)


class BaseWorker(ABC):
    """
    Base class for all Empire OS workers.
    Every worker accepts: job_id, workflow_id, payload, attempt, idempotency_key
    Returns: WorkerResult with status, output, error, metrics, artifacts
    """

    def __init__(self, worker_name: str):
        self.worker_name = worker_name
        self.settings = get_settings()
        self.session = init_db(self.settings.database_url)

    @abstractmethod
    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        """Execute the worker's main logic. Must be implemented by subclass."""
        pass

    def run(self, job_id: str, workflow_id: str, payload: Dict[str, Any],
            attempt: int = 1, idempotency_key: Optional[str] = None) -> WorkerResult:
        """
        Main entry point - handles job lifecycle, retries, idempotency, logging.
        """
        # Idempotency check
        if idempotency_key:
            existing = self.session.query(Job).filter(
                Job.idempotency_key == idempotency_key
            ).first()
            if existing and existing.status == JobStatus.SUCCEEDED:
                logger.info(f"[{self.worker_name}] Idempotency hit for {idempotency_key}, returning cached result")
                return WorkerResult(
                    success=True,
                    output=json.loads(existing.output) if existing.output else {},
                    metrics={"cached": True}
                )

        # Update job status to RUNNING
        job = self.session.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.RUNNING
            job.attempt = attempt
            self.session.commit()

        # Record attempt start - check if already exists
        existing_attempt = self.session.query(JobAttempt).filter(
            JobAttempt.job_id == job_id,
            JobAttempt.attempt_number == attempt
        ).first()
        
        if existing_attempt:
            attempt_record = existing_attempt
            attempt_record.status = JobStatus.RUNNING
            attempt_record.started_at = datetime.now(timezone.utc)
            attempt_record.error_code = None
            attempt_record.error_message = None
        else:
            attempt_record = JobAttempt(
                job_id=job_id,
                attempt_number=attempt,
                status=JobStatus.RUNNING,
                started_at=datetime.now(timezone.utc)
            )
            self.session.add(attempt_record)
        self.session.commit()

        start_time = datetime.now(timezone.utc)

        try:
            logger.info(f"[{self.worker_name}] Starting job {job_id} (attempt {attempt})")
            result = self.execute(payload)

            # Record attempt completion
            execution_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            attempt_record.status = JobStatus.SUCCEEDED if result.success else JobStatus.FAILED
            attempt_record.output = json.dumps(result.output)
            attempt_record.error_code = result.error_code
            attempt_record.error_message = result.error_message
            attempt_record.execution_time_ms = execution_ms
            attempt_record.completed_at = datetime.now(timezone.utc)

            # Update job
            if job:
                job.status = JobStatus.SUCCEEDED if result.success else JobStatus.FAILED
                job.output = json.dumps(result.output)
                job.error_code = result.error_code
                job.error_message = result.error_message
                job.metrics = json.dumps(result.metrics)
                job.artifacts = json.dumps(result.artifacts)
                job.retryable = result.retryable
                job.touch()

            self.session.commit()

            if result.success:
                logger.info(f"[{self.worker_name}] Job {job_id} succeeded in {execution_ms}ms")
            else:
                logger.warning(f"[{self.worker_name}] Job {job_id} failed: {result.error_code} - {result.error_message}")

            return result

        except Exception as e:
            execution_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            error_msg = f"{type(e).__name__}: {str(e)}"
            trace = traceback.format_exc()

            attempt_record.status = JobStatus.FAILED
            attempt_record.error_code = "WORKER_EXCEPTION"
            attempt_record.error_message = error_msg
            attempt_record.execution_time_ms = execution_ms
            attempt_record.completed_at = datetime.now(timezone.utc)

            if job:
                job.status = JobStatus.FAILED
                job.error_code = "WORKER_EXCEPTION"
                job.error_message = error_msg
                job.retryable = True

            self.session.commit()
            logger.error(f"[{self.worker_name}] Job {job_id} exception: {error_msg}\n{trace}")

            return WorkerResult(
                success=False,
                error_code="WORKER_EXCEPTION",
                error_message=error_msg,
                retryable=True
            )


class WorkerRegistry:
    """Registry of all available workers"""

    _workers: Dict[str, BaseWorker] = {}

    @classmethod
    def register(cls, worker: BaseWorker):
        cls._workers[worker.worker_name] = worker

    @classmethod
    def get(cls, name: str) -> Optional[BaseWorker]:
        return cls._workers.get(name)

    @classmethod
    def list(cls) -> List[str]:
        return list(cls._workers.keys())