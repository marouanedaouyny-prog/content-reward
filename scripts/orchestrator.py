#!/usr/bin/env python3
"""
Automation Empire OS — Orchestrator
Coordinates workflows, manages job queue, handles scheduling
$0 constraint: local SQLite queue, n8n for orchestration
"""

import json
import uuid
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
import schedule

from scripts.worker_base import BaseWorker, WorkerResult, WorkerRegistry
from backend.app.core.config import get_settings
from backend.app.core.db import (
    init_db, Job, JobStatus, WorkflowVersion, JobAttempt, SystemSettings
)

logger = logging.getLogger(__name__)


@dataclass
class WorkflowDefinition:
    """Loaded workflow definition from YAML"""
    id: str
    version: str
    name: str
    risk_level: str
    permissions: List[str]
    retries: Dict[str, Any]
    approval: Dict[str, Any]
    timeouts: Dict[str, int]
    idempotency_strategy: Dict[str, Any]
    manual_approval_rules: List[Dict]
    cost_tracking: Dict[str, Any]
    steps: List[Dict] = field(default_factory=list)

    def retry_config_dict(self) -> Dict[str, Any]:
        """Get retry config as dict"""
        if self.retries:
            return self.retries
        return {"max_attempts": 3, "backoff_seconds": [30, 120, 600]}

    def approval_rules_dict(self) -> Dict[str, Any]:
        """Get approval rules as dict"""
        if self.approval:
            return self.approval
        return {}


class WorkflowLoader:
    """Load workflow definitions from YAML files"""

    @staticmethod
    def load_from_file(filepath: Path) -> Optional[WorkflowDefinition]:
        import yaml
        try:
            with open(filepath, "r") as f:
                data = yaml.safe_load(f)
            return WorkflowDefinition(**data)
        except Exception as e:
            logger.error(f"Failed to load workflow from {filepath}: {e}")
            return None

    @staticmethod
    def load_all(workflows_dir: Path) -> Dict[str, WorkflowDefinition]:
        workflows = {}
        for wf_dir in workflows_dir.iterdir():
            if wf_dir.is_dir():
                yaml_file = wf_dir / "workflow.yaml"
                if yaml_file.exists():
                    wf = WorkflowLoader.load_from_file(yaml_file)
                    if wf:
                        workflows[wf.id] = wf
        return workflows


class Orchestrator:
    """
    Core orchestrator - manages workflow execution, job queue, scheduling
    """

    def __init__(self):
        self.settings = get_settings()
        self.session = init_db(self.settings.database_url)
        self.workflows = WorkflowLoader.load_all(Path("workflows"))
        self.running = False
        self.worker_map = self._build_worker_map()

    def _build_worker_map(self) -> Dict[str, BaseWorker]:
        """Map workflow step names to worker instances"""
        return {name: worker for name, worker in WorkerRegistry._workers.items()}

    def register_workflow(self, workflow: WorkflowDefinition):
        """Register or update workflow in registry"""
        self.workflows[workflow.id] = workflow

        # Persist to DB
        existing = self.session.query(WorkflowVersion).filter(
            WorkflowVersion.id == workflow.id
        ).first()
        if existing:
            existing.version = workflow.version
            existing.name = workflow.name
            existing.risk_level = workflow.risk_level
            existing.permissions = json.dumps(workflow.permissions)
            existing.retry_config = json.dumps(workflow.retries)
            existing.approval_rules = json.dumps(workflow.approval)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            existing = WorkflowVersion(
                id=workflow.id,
                version=workflow.version,
                name=workflow.name,
                risk_level=workflow.risk_level,
                permissions=json.dumps(workflow.permissions),
                retry_config=json.dumps(workflow.retries),
                approval_rules=json.dumps(workflow.approval)
            )
            self.session.add(existing)
        self.session.commit()

    def create_job(self, workflow_id: str, payload: Dict[str, Any],
                   idempotency_key: Optional[str] = None,
                   risk_level: Optional[str] = None) -> Job:
        """Create a new job for a workflow"""
        wf = self.workflows.get(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        job = Job(
            workflow_id=workflow_id,
            payload=json.dumps(payload),
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            risk_level=risk_level or wf.risk_level,
            status=JobStatus.QUEUED,
            attempt=1
        )
        self.session.add(job)
        self.session.commit()
        return job

    def execute_job(self, job_id: str) -> WorkerResult:
        """Execute a single job through its workflow steps"""
        job = self.session.query(Job).filter(Job.id == job_id).first()
        if not job:
            return WorkerResult(success=False, error_code="JOB_NOT_FOUND", error_message=f"Job {job_id} not found")

        wf = self.workflows.get(job.workflow_id)
        if not wf:
            return WorkerResult(success=False, error_code="WORKFLOW_NOT_FOUND", error_message=f"Workflow {job.workflow_id} not found")

        # Check kill switch
        kill_switch = self.session.query(SystemSettings).filter(SystemSettings.key == "kill_switch").first()
        if kill_switch and json.loads(kill_switch.value_json).get("enabled", False):
            job.status = JobStatus.BLOCKED
            job.error_code = "KILL_SWITCH"
            job.error_message = "Global kill switch enabled"
            self.session.commit()
            return WorkerResult(success=False, error_code="KILL_SWITCH", error_message="Global kill switch enabled")

        # Check workflow-specific kill switch
        wf_kill = self.session.query(SystemSettings).filter(SystemSettings.key == f"kill_switch_{job.workflow_id}").first()
        if wf_kill and json.loads(wf_kill.value_json).get("enabled", False):
            job.status = JobStatus.BLOCKED
            job.error_code = "WORKFLOW_KILL_SWITCH"
            job.error_message = f"Workflow {job.workflow_id} kill switch enabled"
            self.session.commit()
            return WorkerResult(success=False, error_code="WORKFLOW_KILL_SWITCH", error_message=f"Workflow kill switch enabled")

        job.status = JobStatus.RUNNING
        self.session.commit()

        # Execute workflow steps sequentially
        payload = json.loads(job.payload) if job.payload else {}
        step_results = {}

        for step in wf.steps:
            step_name = step.get("worker")
            step_payload = {**payload, **step.get("payload", {}), "step_results": step_results}

            worker = self.worker_map.get(step_name)
            if not worker:
                return WorkerResult(
                    success=False,
                    error_code="WORKER_NOT_FOUND",
                    error_message=f"Worker {step_name} not registered"
                )

            # Check if step requires approval
            if self._requires_approval(step_name, wf, step_results):
                job.status = JobStatus.WAITING
                job.error_code = "APPROVAL_REQUIRED"
                job.error_message = f"Step {step_name} requires human approval"
                self.session.commit()
                return WorkerResult(
                    success=False,
                    error_code="APPROVAL_REQUIRED",
                    error_message=f"Step {step_name} requires human approval",
                    retryable=False
                )

            # Execute step
            # For campaign_parser, pass the campaign_id from previous step's results
            if step_name == "campaign_parser" and "campaign_discovery" in step_results:
                discovery_output = step_results["campaign_discovery"]
                campaigns_stored = discovery_output.get("campaigns_stored", [])
                if campaigns_stored:
                    step_payload["campaign_id"] = campaigns_stored[0]
            
            # For source_download, pass campaign_id from campaign_discovery output
            if step_name == "source_download":
                if "campaign_discovery" in step_results:
                    discovery_output = step_results["campaign_discovery"]
                    campaigns_stored = discovery_output.get("campaigns_stored", [])
                    if campaigns_stored:
                        step_payload["campaign_id"] = campaigns_stored[0]
                # Also pass source_urls from original payload if available
                if "source_urls" in payload:
                    step_payload["source_urls"] = payload["source_urls"]
            
            # For clip_generator, pass source_media_ids from source_download output
            if step_name == "clip_generator" and "source_download" in step_results:
                download_output = step_results["source_download"]
                downloaded = download_output.get("downloaded", [])
                if downloaded:
                    # Pass the first downloaded source media ID
                    step_payload["source_media_id"] = downloaded[0].get("source_media_id")
            
            # For quality_check, pass clip_id from clip_generator output
            if step_name == "quality_check" and "clip_generator" in step_results:
                clip_output = step_results["clip_generator"]
                clip_id = clip_output.get("clip_id")
                if clip_id:
                    step_payload["clip_id"] = clip_id
            
            # For publish, pass clip_id from clip_generator output
            if step_name == "publish" and "clip_generator" in step_results:
                clip_output = step_results["clip_generator"]
                clip_id = clip_output.get("clip_id")
                if clip_id:
                    step_payload["clip_id"] = clip_id
            
            result = worker.run(
                job_id=job.id,
                workflow_id=job.workflow_id,
                payload=step_payload,
                attempt=job.attempt,
                idempotency_key=f"{job.idempotency_key}_{step_name}"
            )

            step_results[step_name] = result.output if result.success else {}

            if not result.success:
                # Handle retry logic
                retry_config = wf.retry_config_dict()
                max_attempts = retry_config.get("max_attempts", 3)
                if job.attempt < max_attempts:
                    job.status = JobStatus.RETRYING
                    job.attempt += 1
                    self.session.commit()
                    # Schedule retry with backoff
                    backoff = retry_config.get("backoff_seconds", [30, 120, 600])
                    delay = backoff[min(job.attempt - 2, len(backoff) - 1)]
                    logger.info(f"Scheduling retry for job {job_id} in {delay}s (attempt {job.attempt})")
                    time.sleep(delay)
                    return self.execute_job(job_id)  # Recursive retry
                else:
                    job.status = JobStatus.FAILED
                    self.session.commit()
                    return result

        # All steps succeeded
        job.status = JobStatus.SUCCEEDED
        job.output = json.dumps(step_results)
        self.session.commit()

        return WorkerResult(success=True, output=step_results)

    def _requires_approval(self, step_name: str, wf: WorkflowDefinition, step_results: Dict) -> bool:
        """Check if step requires human approval based on rules"""
        for rule in wf.manual_approval_rules:
            if rule.get("action") == step_name:
                condition = rule.get("condition", "always_required")
                if condition == "always_required":
                    return True
                # Could evaluate other conditions based on step_results
        return False

    def approve_job(self, job_id: str, step_name: str, approved: bool, approver: str = "human") -> bool:
        """Handle human approval for a waiting job"""
        job = self.session.query(Job).filter(Job.id == job_id).first()
        if not job or job.status != JobStatus.WAITING:
            return False

        if approved:
            job.status = JobStatus.QUEUED  # Will be picked up by executor
            self.session.commit()
            return True
        else:
            job.status = JobStatus.CANCELLED
            job.error_code = "APPROVAL_REJECTED"
            job.error_message = f"Step {step_name} rejected by {approver}"
            self.session.commit()
            return True

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get job status and details"""
        job = self.session.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        return {
            "id": job.id,
            "workflow_id": job.workflow_id,
            "status": job.status.value,
            "attempt": job.attempt,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "output": json.loads(job.output) if job.output else None,
            "metrics": json.loads(job.metrics) if job.metrics else None
        }

    def list_jobs(self, status: Optional[JobStatus] = None, limit: int = 50) -> List[Dict]:
        """List jobs with optional status filter"""
        query = self.session.query(Job).order_by(Job.created_at.desc())
        if status:
            query = query.filter(Job.status == status)
        jobs = query.limit(limit).all()
        return [self.get_job_status(j.id) for j in jobs]

    def start_scheduler(self):
        """Start the background scheduler for cron jobs"""
        self.running = True
        self._load_schedules()
        scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("Scheduler started")

    def stop_scheduler(self):
        """Stop the background scheduler"""
        self.running = False
        schedule.clear()
        logger.info("Scheduler stopped")

    def _load_schedules(self):
        """Load cron schedules from workflow definitions"""
        for wf in self.workflows.values():
            # Check for schedule in workflow metadata (would be in YAML)
            # For now, register from known schedules
            if wf.id == "content_rewards":
                schedule.every().day.at("06:00").do(self._schedule_workflow, wf.id)
            elif wf.id == "lead_generation":
                schedule.every().monday.at("08:00").do(self._schedule_workflow, wf.id)
            elif wf.id == "product_research":
                schedule.every().sunday.at("09:00").do(self._schedule_workflow, wf.id)

    def _schedule_workflow(self, workflow_id: str):
        """Create and queue a scheduled job"""
        try:
            idempotency_key = f"scheduled_{workflow_id}_{datetime.now().strftime('%Y%m%d')}"
            job = self.create_job(workflow_id, {"scheduled": True}, idempotency_key=idempotency_key)
            logger.info(f"Scheduled job created: {job.id} for workflow {workflow_id}")
        except Exception as e:
            logger.error(f"Failed to schedule workflow {workflow_id}: {e}")

    def _run_scheduler(self):
        """Background scheduler loop"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute


# Global orchestrator instance
_orchestrator = None

def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator