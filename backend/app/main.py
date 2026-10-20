#!/usr/bin/env python3
"""
Automation Empire OS — FastAPI Main Application
$0 constraint: local-first, optional free-tier fallbacks only
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import logging
import json

from backend.app.core.config import get_settings
from backend.app.core.db import (
    init_db, Job, JobStatus, WorkflowVersion, SystemSettings,
    Campaign, Clip, PublishedPost, Earnings, Provider
)
from scripts.orchestrator import get_orchestrator, Orchestrator
from scripts.worker_base import WorkerRegistry
import uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

orchestrator: Optional[Orchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    settings = get_settings()
    # Initialize DB
    init_db(settings.database_url)
    # Initialize orchestrator
    orchestrator = get_orchestrator()
    # Register workflows from YAML
    from scripts.orchestrator import WorkflowLoader
    workflows = WorkflowLoader.load_all(Path("workflows"))
    for wf in workflows.values():
        orchestrator.register_workflow(wf)
    # Start scheduler
    orchestrator.start_scheduler()
    logger.info("Empire OS started")
    yield
    # Shutdown
    orchestrator.stop_scheduler()
    logger.info("Empire OS stopped")


app = FastAPI(
    title="Automation Empire OS",
    description="Local-first automation operating system",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class JobCreate(BaseModel):
    workflow_id: str
    payload: Dict[str, Any] = {}
    idempotency_key: Optional[str] = None
    risk_level: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    attempt: int
    created_at: str
    updated_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None


class ApprovalRequest(BaseModel):
    step_name: str
    approved: bool
    approver: str = "human"


# Dependency
def get_orch() -> Orchestrator:
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orchestrator


# Health
@app.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "healthy",
        "version": "1.0.0",
        "deploy_mode": settings.deploy_mode,
        "ollama_url": settings.ollama_base_url,
        "workers_registered": WorkerRegistry.list()
    }


# Workflows
@app.get("/api/v1/workflows")
async def list_workflows(orch: Orchestrator = Depends(get_orch)):
    return {
        "workflows": [
            {
                "id": wf.id,
                "version": wf.version,
                "name": wf.name,
                "risk_level": wf.risk_level,
                "enabled": True
            }
            for wf in orch.workflows.values()
        ]
    }


@app.get("/api/v1/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, orch: Orchestrator = Depends(get_orch)):
    wf = orch.workflows.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "id": wf.id,
        "version": wf.version,
        "name": wf.name,
        "risk_level": wf.risk_level,
        "permissions": wf.permissions,
        "retries": wf.retries,
        "approval": wf.approval,
        "timeouts": wf.timeouts,
        "steps": wf.steps
    }


@app.post("/api/v1/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, job_data: JobCreate, orch: Orchestrator = Depends(get_orch)):
    wf = orch.workflows.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    job = orch.create_job(
        workflow_id=workflow_id,
        payload=job_data.payload,
        idempotency_key=job_data.idempotency_key,
        risk_level=job_data.risk_level
    )

    # Execute synchronously for now (could be async with background tasks)
    result = orch.execute_job(job.id)

    return {
        "job_id": job.id,
        "success": result.success,
        "output": result.output,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "metrics": result.metrics
    }


# Jobs
@app.get("/api/v1/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = 50, orch: Orchestrator = Depends(get_orch)):
    job_status = JobStatus(status) if status else None
    jobs = orch.list_jobs(status=job_status, limit=limit)
    return {"jobs": jobs}


@app.get("/api/v1/jobs/{job_id}")
async def get_job(job_id: str, orch: Orchestrator = Depends(get_orch)):
    job = orch.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/v1/jobs/{job_id}/retry")
async def retry_job(job_id: str, orch: Orchestrator = Depends(get_orch)):
    job = orch.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Reset job to queued
    session = init_db(get_settings().database_url)
    db_job = session.query(Job).filter(Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")
    db_job.status = JobStatus.QUEUED
    db_job.attempt += 1
    db_job.error_code = None
    db_job.error_message = None
    session.commit()
    result = orch.execute_job(job_id)
    return {"job_id": job_id, "success": result.success, "output": result.output}


@app.post("/api/v1/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, orch: Orchestrator = Depends(get_orch)):
    session = init_db(get_settings().database_url)
    db_job = session.query(Job).filter(Job.id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")
    db_job.status = JobStatus.CANCELLED
    session.commit()
    return {"job_id": job_id, "status": "cancelled"}


@app.post("/api/v1/jobs/{job_id}/approve")
async def approve_job(job_id: str, approval: ApprovalRequest, orch: Orchestrator = Depends(get_orch)):
    success = orch.approve_job(job_id, approval.step_name, approval.approved, approval.approver)
    if not success:
        raise HTTPException(status_code=400, detail="Job not in waiting state or approval failed")
    return {"job_id": job_id, "approved": approval.approved}


@app.post("/api/v1/jobs/{job_id}/reject")
async def reject_job(job_id: str, approval: ApprovalRequest, orch: Orchestrator = Depends(get_orch)):
    success = orch.approve_job(job_id, approval.step_name, False, approval.approver)
    if not success:
        raise HTTPException(status_code=400, detail="Job not in waiting state")
    return {"job_id": job_id, "rejected": True}


# Campaigns
@app.get("/api/v1/campaigns")
async def list_campaigns(status: Optional[str] = None, limit: int = 50):
    settings = get_settings()
    session = init_db(settings.database_url)
    query = session.query(Campaign)
    if status:
        query = query.filter(Campaign.status == status)
    campaigns = query.order_by(Campaign.created_at.desc()).limit(limit).all()
    return {
        "campaigns": [
            {
                "id": c.id,
                "campaign_id": c.campaign_id,
                "title": c.title,
                "type": c.type,
                "platforms": json.loads(c.platforms) if c.platforms else [],
                "budget_total": c.budget_total,
                "budget_remaining": c.budget_remaining,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in campaigns
        ]
    }


@app.get("/api/v1/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    settings = get_settings()
    session = init_db(settings.database_url)
    campaign = session.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "id": campaign.id,
        "campaign_id": campaign.campaign_id,
        "title": campaign.title,
        "type": campaign.type,
        "platforms": json.loads(campaign.platforms) if campaign.platforms else [],
        "niches": json.loads(campaign.niches) if campaign.niches else [],
        "budget_total": campaign.budget_total,
        "budget_remaining": campaign.budget_remaining,
        "rate": campaign.rate,
        "max_payout": campaign.max_payout,
        "min_views": campaign.min_views,
        "status": campaign.status,
        "metadata_json": json.loads(campaign.metadata_json) if campaign.metadata_json else None
    }


@app.post("/api/v1/campaigns/import")
async def import_campaign(campaign_data: Dict[str, Any]):
    settings = get_settings()
    session = init_db(settings.database_url)

    campaign = Campaign(
        campaign_id=campaign_data.get("campaign_id", f"camp_{uuid.uuid4().hex[:12]}"),
        source=campaign_data.get("source", "manual"),
        title=campaign_data.get("title", ""),
        type=campaign_data.get("type", "cpm"),
        platforms=json.dumps(campaign_data.get("platforms", [])),
        niches=json.dumps(campaign_data.get("niches", [])),
        budget_total=campaign_data.get("budget_total", 0),
        budget_remaining=campaign_data.get("budget_remaining", 0),
        rate=campaign_data.get("rate", 0),
        max_payout=campaign_data.get("max_payout", 0),
        min_views=campaign_data.get("min_views", 0),
        required_tags=json.dumps(campaign_data.get("required_tags", [])),
        required_mentions=json.dumps(campaign_data.get("required_mentions", [])),
        deadline=campaign_data.get("deadline"),
        status="discovered",
        raw_source_url=campaign_data.get("raw_source_url", ""),
        metadata_json=json.dumps(campaign_data.get("metadata", {}))
    )
    session.add(campaign)
    session.commit()
    return {"campaign_id": campaign.campaign_id, "status": "imported"}


# Clips
@app.get("/api/v1/clips")
async def list_clips(campaign_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50):
    settings = get_settings()
    session = init_db(settings.database_url)
    query = session.query(Clip)
    if campaign_id:
        query = query.filter(Clip.campaign_id == campaign_id)
    if status:
        query = query.filter(Clip.status == status)
    clips = query.order_by(Clip.created_at.desc()).limit(limit).all()
    return {
        "clips": [
            {
                "id": c.id,
                "campaign_id": c.campaign_id,
                "clip_path": c.clip_path,
                "aspect_ratio": c.aspect_ratio,
                "duration": c.duration,
                "quality_score": c.quality_score,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in clips
        ]
    }


@app.post("/api/v1/clips/generate")
async def generate_clip(request: Request):
    data = await request.json()
    settings = get_settings()
    session = init_db(settings.database_url)

    source_media_id = data.get("source_media_id")
    clip_plan = data.get("clip_plan", {})

    # Create job for clip generation
    orch = get_orchestrator()
    job = orch.create_job("content_rewards", {
        "step": "clip_generator",
        "source_media_id": source_media_id,
        "clip_plan": clip_plan
    })

    result = orch.execute_job(job.id)
    return {"job_id": job.id, "success": result.success, "output": result.output}


# Published Posts
@app.get("/api/v1/published-posts")
async def list_published_posts(campaign_id: Optional[str] = None, platform: Optional[str] = None, limit: int = 50):
    settings = get_settings()
    session = init_db(settings.database_url)
    query = session.query(PublishedPost)
    if campaign_id:
        query = query.filter(PublishedPost.campaign_id == campaign_id)
    if platform:
        query = query.filter(PublishedPost.platform == platform)
    posts = query.order_by(PublishedPost.created_at.desc()).limit(limit).all()
    return {
        "posts": [
            {
                "id": p.id,
                "campaign_id": p.campaign_id,
                "platform": p.platform,
                "post_id": p.post_id,
                "status": p.status,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "view_count": p.view_count,
                "earnings": p.earnings
            }
            for p in posts
        ]
    }


# Earnings
@app.get("/api/v1/earnings")
async def get_earnings(campaign_id: Optional[str] = None):
    settings = get_settings()
    session = init_db(settings.database_url)
    query = session.query(Earnings)
    if campaign_id:
        query = query.filter(Earnings.campaign_id == campaign_id)
    earnings = query.order_by(Earnings.recorded_at.desc()).all()
    total = sum(e.amount for e in earnings)
    return {
        "total_earnings": total,
        "currency": "USD",
        "breakdown": [
            {
                "campaign_id": e.campaign_id,
                "amount": e.amount,
                "source": e.source,
                "status": e.status,
                "recorded_at": e.recorded_at.isoformat() if e.recorded_at else None
            }
            for e in earnings
        ]
    }


# Providers
@app.get("/api/v1/providers/health")
async def providers_health():
    settings = get_settings()
    session = init_db(settings.database_url)
    providers = session.query(Provider).all()
    return {
        "providers": [
            {
                "name": p.name,
                "kind": p.kind,
                "health": p.health,
                "requests_today": p.requests_today,
                "tokens_today": p.tokens_today,
                "can_use": p.can_use()
            }
            for p in providers
        ]
    }


# System
@app.get("/api/v1/system/cost")
async def system_cost():
    settings = get_settings()
    session = init_db(settings.database_url)
    # Aggregate costs from jobs
    jobs = session.query(Job).all()
    total_cost = sum(j.estimated_cost for j in jobs)
    return {
        "total_estimated_cost": total_cost,
        "currency": "USD",
        "jobs_count": len(jobs),
        "paid_services_allowed": settings.allow_paid_services
    }


@app.post("/api/v1/system/pause")
async def pause_system():
    settings = get_settings()
    session = init_db(settings.database_url)
    setting = session.query(SystemSettings).filter(SystemSettings.key == "kill_switch").first()
    if not setting:
        setting = SystemSettings(key="kill_switch", value_json=json.dumps({"enabled": True}))
        session.add(setting)
    else:
        setting.value_json = json.dumps({"enabled": True})
    session.commit()
    return {"status": "paused", "kill_switch": True}


@app.post("/api/v1/system/resume")
async def resume_system():
    settings = get_settings()
    session = init_db(settings.database_url)
    setting = session.query(SystemSettings).filter(SystemSettings.key == "kill_switch").first()
    if setting:
        setting.value_json = json.dumps({"enabled": False})
    session.commit()
    return {"status": "resumed", "kill_switch": False}


@app.post("/api/v1/system/kill-switch")
async def kill_switch(workflow_id: Optional[str] = None):
    settings = get_settings()
    session = init_db(settings.database_url)
    key = f"kill_switch_{workflow_id}" if workflow_id else "kill_switch"
    setting = session.query(SystemSettings).filter(SystemSettings.key == key).first()
    if not setting:
        setting = SystemSettings(key=key, value_json=json.dumps({"enabled": True}))
        session.add(setting)
    else:
        setting.value_json = json.dumps({"enabled": True})
    session.commit()
    return {"status": "kill_switch_enabled", "workflow_id": workflow_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)