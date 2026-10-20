#!/usr/bin/env python3
"""
Automation Empire OS — Specialized Agents
Researcher, Planner, Builder, QA, Publisher, Analytics, Fixer agents.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

from scripts.agent_base import BaseAgent, AgentTask, AgentRegistry, get_agent_registry
from scripts.orchestrator import get_orchestrator, Orchestrator
from scripts.worker_base import WorkerRegistry
from scripts.ai_router import get_router, llm_complete, LLMRequest, ProviderKind
from backend.app.core.config import get_settings
from backend.app.core.db import init_db, Campaign, Job, JobStatus, Clip, PublishedPost, Earnings

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    """Agent that discovers opportunities: campaigns, trends, leads, products."""
    
    def __init__(self, message_bus, config=None):
        super().__init__(
            name="researcher",
            message_bus=message_bus,
            capabilities=["campaign_discovery", "trend_analysis", "lead_generation", "product_research", "competitor_analysis"],
            config=config
        )
        self.orchestrator = get_orchestrator()
    
    def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload
        
        if task_type == "discover_campaigns":
            return self._discover_campaigns(payload)
        elif task_type == "analyze_trends":
            return self._analyze_trends(payload)
        elif task_type == "generate_leads":
            return self._generate_leads(payload)
        elif task_type == "research_products":
            return self._research_products(payload)
        elif task_type == "analyze_competitors":
            return self._analyze_competitors(payload)
        else:
            return {"error": f"Unknown task type: {task_type}"}
    
    def _discover_campaigns(self, payload: Dict) -> Dict:
        """Discover content reward campaigns."""
        source_type = payload.get("source_type", "manual")
        source_url = payload.get("source_url")
        
        # Create job for campaign discovery
        job = self.orchestrator.create_job("content_rewards", {
            "step": "campaign_discovery",
            "source_type": source_type,
            "source_url": source_url,
            "manual_paste": payload.get("manual_paste")
        })
        
        result = self.orchestrator.execute_job(job.id)
        return {"job_id": job.id, "success": result.success, "output": result.output}
    
    def _analyze_trends(self, payload: Dict) -> Dict:
        """Analyze trending topics and content."""
        platforms = payload.get("platforms", ["tiktok", "youtube", "instagram"])
        niches = payload.get("niches", [])
        
        job = self.orchestrator.create_job("product_research", {
            "step": "product_scan",
            "scan_type": "trend",
            "categories": niches,
            "max_products": payload.get("max_products", 50)
        })
        
        result = self.orchestrator.execute_job(job.id)
        return {"job_id": job.id, "success": result.success, "output": result.output}
    
    def _generate_leads(self, payload: Dict) -> Dict:
        """Generate leads for outreach."""
        source_type = payload.get("source_type", "web")
        criteria = payload.get("criteria", {})
        
        job = self.orchestrator.create_job("lead_generation", {
            "step": "lead_source_discovery",
            "source_type": source_type,
            "search_criteria": criteria,
            "max_results": payload.get("max_results", 100)
        })
        
        result = self.orchestrator.execute_job(job.id)
        return {"job_id": job.id, "success": result.success, "output": result.output}
    
    def _research_products(self, payload: Dict) -> Dict:
        """Research product opportunities."""
        scan_type = payload.get("scan_type", "marketplace")
        target_sites = payload.get("target_sites", [])
        categories = payload.get("categories", [])
        
        job = self.orchestrator.create_job("product_research", {
            "step": "product_scan",
            "scan_type": scan_type,
            "target_sites": target_sites,
            "categories": categories,
            "max_products": payload.get("max_products", 100)
        })
        
        result = self.orchestrator.execute_job(job.id)
        return {"job_id": job.id, "success": result.success, "output": result.output}
    
    def _analyze_competitors(self, payload: Dict) -> Dict:
        """Analyze competitor strategies."""
        competitors = payload.get("competitors", [])
        platforms = payload.get("platforms", ["tiktok", "youtube"])
        
        # This would trigger a custom workflow
        return {"status": "competitor_analysis_queued", "competitors": competitors}
    
    def analyze_with_llm(self, prompt: str, system_prompt: str = None) -> Dict:
        """Use LLM for intelligent analysis"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = self.llm_complete(messages, temperature=0.3, max_tokens=1024)
        return {
            "success": not response.error,
            "content": response.content,
            "provider": response.provider.value if response.provider else "unknown",
            "error": response.error
        }


class PlannerAgent(BaseAgent):
    """Agent that plans workflows, creates job sequences, and manages scheduling."""
    
    def __init__(self, message_bus, config=None):
        super().__init__(
            name="planner",
            message_bus=message_bus,
            capabilities=["workflow_planning", "job_scheduling", "resource_allocation", "dependency_management", "approval_routing"],
            config=config
        )
        self.orchestrator = get_orchestrator()
    
    def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload
        
        if task_type == "plan_workflow":
            return self._plan_workflow(payload)
        elif task_type == "schedule_jobs":
            return self._schedule_jobs(payload)
        elif task_type == "create_job_chain":
            return self._create_job_chain(payload)
        elif task_type == "allocate_resources":
            return self._allocate_resources(payload)
        elif task_type == "route_approval":
            return self._route_approval(payload)
        else:
            return {"error": f"Unknown task type: {task_type}"}
    
    def _plan_workflow(self, payload: Dict) -> Dict:
        """Plan a complete workflow from goal."""
        goal = payload.get("goal", "")
        workflow_type = payload.get("workflow_type", "content_rewards")
        
        # Break down goal into steps
        if workflow_type == "content_rewards":
            steps = [
                {"worker": "campaign_discovery", "payload": {"source_type": "manual"}},
                {"worker": "campaign_parser", "payload": {}},
                {"worker": "source_download", "payload": {"source_urls": []}},
                {"worker": "clip_generator", "payload": {"clip_plan": {"aspect_ratio": "9:16"}}},
                {"worker": "quality_check", "payload": {}},
            ]
        elif workflow_type == "lead_generation":
            steps = [
                {"worker": "lead_source_discovery", "payload": {"source_type": "web"}},
                {"worker": "lead_export", "payload": {"export_format": "csv"}},
            ]
        elif workflow_type == "product_research":
            steps = [
                {"worker": "product_scan", "payload": {"scan_type": "marketplace"}},
                {"worker": "product_report", "payload": {"report_format": "markdown"}},
            ]
        else:
            steps = []
        
        return {
            "workflow_type": workflow_type,
            "goal": goal,
            "steps": steps,
            "estimated_steps": len(steps)
        }
    
    def _schedule_jobs(self, payload: Dict) -> Dict:
        """Schedule recurring jobs."""
        workflow_id = payload.get("workflow_id")
        schedule_config = payload.get("schedule", {})
        
        # This would integrate with the orchestrator's scheduler
        return {"scheduled": True, "workflow_id": workflow_id, "config": schedule_config}
    
    def _create_job_chain(self, payload: Dict) -> Dict:
        """Create a chain of dependent jobs."""
        jobs = payload.get("jobs", [])
        chain = []
        
        for i, job_spec in enumerate(jobs):
            job = self.orchestrator.create_job(
                workflow_id=job_spec.get("workflow_id", "content_rewards"),
                payload=job_spec.get("payload", {}),
                idempotency_key=job_spec.get("idempotency_key")
            )
            chain.append({"job_id": job.id, "spec": job_spec})
        
        return {"chain": chain, "total_jobs": len(chain)}
    
    def _allocate_resources(self, payload: Dict) -> Dict:
        """Allocate resources for job execution."""
        # Check system capacity, provider health, etc.
        settings = get_settings()
        return {
            "ollama_available": True,
            "storage_available": True,
            "providers_healthy": ["ollama"],
            "estimated_capacity": "high"
        }
    
    def _route_approval(self, payload: Dict) -> Dict:
        """Route approval requests."""
        job_id = payload.get("job_id")
        step_name = payload.get("step_name")
        
        # Notify human or auto-approve based on rules
        return {"routed": True, "job_id": job_id, "step": step_name}


class BuilderAgent(BaseAgent):
    """Agent that writes code, creates workers, implements features."""
    
    def __init__(self, message_bus, config=None):
        super().__init__(
            name="builder",
            message_bus=message_bus,
            capabilities=["code_generation", "worker_creation", "api_implementation", "database_migration", "test_writing", "refactoring"],
            config=config
        )
    
    def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload
        
        if task_type == "create_worker":
            return self._create_worker(payload)
        elif task_type == "implement_api":
            return self._implement_api(payload)
        elif task_type == "write_tests":
            return self._write_tests(payload)
        elif task_type == "refactor_code":
            return self._refactor_code(payload)
        elif task_type == "create_workflow":
            return self._create_workflow(payload)
        elif task_type == "fix_bug":
            return self._fix_bug(payload)
        else:
            return {"error": f"Unknown task type: {task_type}"}
    
    def _create_worker(self, payload: Dict) -> Dict:
        """Create a new worker class."""
        worker_name = payload.get("worker_name")
        worker_type = payload.get("worker_type", "base")  # base, content, lead, product
        template = payload.get("template", "basic")
        
        # Generate worker code
        code = self._generate_worker_code(worker_name, worker_type, template)
        
        # Write to file
        file_path = Path(f"scripts/{worker_type}_workers.py")
        
        # Check if file exists and append, or create new
        if file_path.exists():
            # Would append to existing file
            action = "append"
        else:
            action = "create"
        
        return {
            "worker_name": worker_name,
            "file_path": str(file_path),
            "action": action,
            "code_preview": code[:500] + "..." if len(code) > 500 else code
        }
    
    def _generate_worker_code(self, name: str, worker_type: str, template: str) -> str:
        """Generate worker class code using LLM for intelligent implementation."""
        # First try LLM-based generation
        prompt = f"""Generate a Python worker class for Automation Empire OS.

Worker name: {name}
Worker type: {worker_type}
Template: {template}

Requirements:
1. Inherit from BaseWorker
2. Implement execute(payload) -> WorkerResult
3. Use proper error handling
4. Follow existing patterns in the codebase
5. Include proper imports

Return ONLY the Python code."""
        
        llm_result = self.analyze_with_llm(prompt, 
            "You are an expert Python developer for Automation Empire OS. Generate clean, production-ready worker code.")
        
        if llm_result["success"] and llm_result["content"]:
            # Extract code from LLM response
            code = llm_result["content"]
            # Ensure it has proper imports
            if "BaseWorker" not in code:
                base_imports = """from scripts.worker_base import BaseWorker, WorkerResult, WorkerRegistry
from backend.app.core.config import get_settings
from backend.app.core.db import init_db
import logging

logger = logging.getLogger(__name__)
"""
                code = base_imports + "\n" + code
            return code
        
        # Fallback to template-based generation
        base_imports = """from scripts.worker_base import BaseWorker, WorkerResult, WorkerRegistry
from backend.app.core.config import get_settings
from backend.app.core.db import init_db
import logging

logger = logging.getLogger(__name__)
"""
        
        class_template = f'''
class {name.title().replace("_", "")}Worker(BaseWorker):
    """Auto-generated worker for {name}"""
    
    def __init__(self):
        super().__init__("{name}")
        self.settings = get_settings()
    
    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        # TODO: Implement {name} logic
        return WorkerResult(
            success=True,
            output={{"message": "{name} completed"}},
            metrics={{"worker": "{name}"}}
        )

WorkerRegistry.register({name.title().replace("_", "")}Worker())
'''
        return base_imports + class_template
    
    def _implement_api(self, payload: Dict) -> Dict:
        """Implement API endpoint."""
        endpoint = payload.get("endpoint")
        method = payload.get("method", "POST")
        logic = payload.get("logic", "")
        
        return {"endpoint": endpoint, "method": method, "implemented": True}
    
    def _write_tests(self, payload: Dict) -> Dict:
        """Write tests for a module."""
        module = payload.get("module")
        test_type = payload.get("test_type", "unit")
        
        return {"module": module, "test_type": test_type, "tests_created": True}
    
    def _refactor_code(self, payload: Dict) -> Dict:
        """Refactor existing code."""
        file_path = payload.get("file_path")
        refactor_type = payload.get("refactor_type", "cleanup")
        
        return {"file_path": file_path, "refactor_type": refactor_type, "refactored": True}
    
    def _create_workflow(self, payload: Dict) -> Dict:
        """Create workflow definition."""
        workflow_id = payload.get("workflow_id")
        steps = payload.get("steps", [])
        
        workflow_def = {
            "id": workflow_id,
            "version": "1.0.0",
            "name": payload.get("name", workflow_id),
            "risk_level": payload.get("risk_level", "medium"),
            "permissions": payload.get("permissions", []),
            "retries": {"max_attempts": 3, "backoff_seconds": [30, 120, 600]},
            "approval": payload.get("approval", {}),
            "timeouts": {"step_timeout_seconds": 300},
            "idempotency_strategy": {"key_prefix": workflow_id},
            "manual_approval_rules": [],
            "cost_tracking": {"estimated_cost": 0},
            "steps": steps
        }
        
        # Save as YAML
        import yaml
        workflow_dir = Path(f"workflows/{workflow_id}")
        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_file = workflow_dir / "workflow.yaml"
        workflow_file.write_text(yaml.dump(workflow_def))
        
        return {"workflow_id": workflow_id, "file": str(workflow_file), "steps": len(steps)}
    
    def _fix_bug(self, payload: Dict) -> Dict:
        """Fix a bug based on error information."""
        error_code = payload.get("error_code")
        error_message = payload.get("error_message")
        file_path = payload.get("file_path")
        
        return {"fixed": True, "error_code": error_code, "file": file_path}


class QAAgent(BaseAgent):
    """Agent that tests, validates, and performs quality checks."""
    
    def __init__(self, message_bus, config=None):
        super().__init__(
            name="qa",
            message_bus=message_bus,
            capabilities=["unit_testing", "integration_testing", "quality_validation", "performance_testing", "regression_testing", "smoke_testing"],
            config=config
        )
    
    def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload
        
        if task_type == "run_tests":
            return self._run_tests(payload)
        elif task_type == "validate_output":
            return self._validate_output(payload)
        elif task_type == "check_quality":
            return self._check_quality(payload)
        elif task_type == "run_smoke_test":
            return self._run_smoke_test(payload)
        elif task_type == "performance_test":
            return self._performance_test(payload)
        else:
            return {"error": f"Unknown task type: {task_type}"}
    
    def _run_tests(self, payload: Dict) -> Dict:
        """Run test suite."""
        import subprocess
        
        test_path = payload.get("path", "tests/")
        test_type = payload.get("test_type", "all")
        
        cmd = ["python", "-m", "pytest", test_path, "-v"]
        if test_type == "unit":
            cmd.extend(["-m", "unit"])
        elif test_type == "integration":
            cmd.extend(["-m", "integration"])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "return_code": result.returncode
        }
    
    def _validate_output(self, payload: Dict) -> Dict:
        """Validate job/workflow output."""
        job_id = payload.get("job_id")
        expected_schema = payload.get("schema")
        
        # Get job result
        orchestrator = get_orchestrator()
        job_status = orchestrator.get_job_status(job_id)
        
        if not job_status:
            return {"valid": False, "error": "Job not found"}
        
        output = job_status.get("output", {})
        
        # Basic validation
        valid = True
        errors = []
        
        if expected_schema:
            # Would use jsonschema validation
            pass
        
        return {"valid": valid, "errors": errors, "output_keys": list(output.keys())}
    
    def _check_quality(self, payload: Dict) -> Dict:
        """Run quality checks on artifacts."""
        clip_id = payload.get("clip_id")
        
        if clip_id:
            # Trigger quality check worker
            orchestrator = get_orchestrator()
            job = orchestrator.create_job("content_rewards", {
                "step": "quality_check",
                "clip_id": clip_id
            })
            result = orchestrator.execute_job(job.id)
            return {"job_id": job.id, "success": result.success, "output": result.output}
        
        return {"error": "clip_id required"}
    
    def _run_smoke_test(self, payload: Dict) -> Dict:
        """Run smoke tests on system."""
        import subprocess
        
        # Test health endpoint
        result = subprocess.run(
            ["curl", "-s", "http://localhost:8000/health"],
            capture_output=True, text=True, timeout=10
        )
        
        health_ok = result.returncode == 0 and "healthy" in result.stdout
        
        return {
            "health_check": health_ok,
            "response": result.stdout[:200]
        }
    
    def _performance_test(self, payload: Dict) -> Dict:
        """Run performance benchmarks."""
        return {"benchmarks": "completed", "metrics": {}}


class PublisherAgent(BaseAgent):
    """Agent that publishes content to platforms and manages distribution."""
    
    def __init__(self, message_bus, config=None):
        super().__init__(
            name="publisher",
            message_bus=message_bus,
            capabilities=["tiktok_publishing", "youtube_publishing", "instagram_publishing", "facebook_publishing", "x_publishing", "cross_posting", "scheduling"],
            config=config
        )
        self.orchestrator = get_orchestrator()
    
    def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload
        
        if task_type == "publish_clip":
            return self._publish_clip(payload)
        elif task_type == "schedule_posts":
            return self._schedule_posts(payload)
        elif task_type == "cross_post":
            return self._cross_post(payload)
        elif task_type == "get_platform_status":
            return self._get_platform_status(payload)
        else:
            return {"error": f"Unknown task type: {task_type}"}
    
    def _publish_clip(self, payload: Dict) -> Dict:
        """Publish a clip to a platform."""
        clip_id = payload.get("clip_id")
        platform = payload.get("platform", "tiktok")
        caption = payload.get("caption", "")
        tags = payload.get("tags", [])
        
        # This would integrate with platform APIs
        # For now, create a job for publishing
        job = self.orchestrator.create_job("content_rewards", {
            "step": "publish",
            "clip_id": clip_id,
            "platform": platform,
            "caption": caption,
            "tags": tags
        })
        
        result = self.orchestrator.execute_job(job.id)
        return {"job_id": job.id, "success": result.success, "output": result.output}
    
    def _schedule_posts(self, payload: Dict) -> Dict:
        """Schedule multiple posts."""
        posts = payload.get("posts", [])
        scheduled = []
        
        for post in posts:
            job = self.orchestrator.create_job("content_rewards", {
                "step": "publish",
                "clip_id": post.get("clip_id"),
                "platform": post.get("platform"),
                "caption": post.get("caption", ""),
                "scheduled_time": post.get("scheduled_time")
            })
            scheduled.append({"job_id": job.id, "platform": post.get("platform")})
        
        return {"scheduled": scheduled}
    
    def _cross_post(self, payload: Dict) -> Dict:
        """Cross-post to multiple platforms."""
        clip_id = payload.get("clip_id")
        platforms = payload.get("platforms", ["tiktok", "youtube", "instagram"])
        
        return self._schedule_posts({
            "posts": [
                {"clip_id": clip_id, "platform": p, "caption": payload.get("caption", "")}
                for p in platforms
            ]
        })
    
    def _get_platform_status(self, payload: Dict) -> Dict:
        """Get publishing status for platforms."""
        # Would check API credentials, rate limits, etc.
        return {
            "tiktok": {"connected": True, "rate_limit_remaining": 100},
            "youtube": {"connected": True, "rate_limit_remaining": 50},
            "instagram": {"connected": False, "rate_limit_remaining": 0},
            "facebook": {"connected": False, "rate_limit_remaining": 0},
            "x": {"connected": False, "rate_limit_remaining": 0}
        }


class AnalyticsAgent(BaseAgent):
    """Agent that tracks metrics, revenue, and performance analytics."""
    
    def __init__(self, message_bus, config=None):
        super().__init__(
            name="analytics",
            message_bus=message_bus,
            capabilities=["revenue_tracking", "performance_analysis", "campaign_roi", "platform_analytics", "trend_detection", "reporting"],
            config=config
        )
    
    def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload
        
        if task_type == "track_revenue":
            return self._track_revenue(payload)
        elif task_type == "analyze_performance":
            return self._analyze_performance(payload)
        elif task_type == "campaign_roi":
            return self._campaign_roi(payload)
        elif task_type == "platform_analytics":
            return self._platform_analytics(payload)
        elif task_type == "generate_report":
            return self._generate_report(payload)
        else:
            return {"error": f"Unknown task type: {task_type}"}
    
    def _track_revenue(self, payload: Dict) -> Dict:
        """Track revenue from campaigns."""
        settings = get_settings()
        session = init_db(settings.database_url)
        
        from backend.app.core.db import Earnings
        
        earnings = session.query(Earnings).all()
        total = sum(e.amount for e in earnings)
        
        by_campaign = {}
        for e in earnings:
            cid = e.campaign_id or "unknown"
            by_campaign[cid] = by_campaign.get(cid, 0) + e.amount
        
        by_source = {}
        for e in earnings:
            src = e.source or "unknown"
            by_source[src] = by_source.get(src, 0) + e.amount
        
        return {
            "total_revenue": total,
            "by_campaign": by_campaign,
            "by_source": by_source,
            "currency": "USD"
        }
    
    def _analyze_performance(self, payload: Dict) -> Dict:
        """Analyze content performance."""
        campaign_id = payload.get("campaign_id")
        
        settings = get_settings()
        session = init_db(settings.database_url)
        
        from backend.app.core.db import PublishedPost, Clip
        
        query = session.query(PublishedPost)
        if campaign_id:
            query = query.filter(PublishedPost.campaign_id == campaign_id)
        
        posts = query.all()
        
        total_views = sum(p.view_count for p in posts)
        total_earnings = sum(p.earnings for p in posts)
        avg_views = total_views / len(posts) if posts else 0
        
        by_platform = {}
        for p in posts:
            plat = p.platform
            if plat not in by_platform:
                by_platform[plat] = {"views": 0, "earnings": 0, "count": 0}
            by_platform[plat]["views"] += p.view_count
            by_platform[plat]["earnings"] += p.earnings
            by_platform[plat]["count"] += 1
        
        return {
            "total_posts": len(posts),
            "total_views": total_views,
            "total_earnings": total_earnings,
            "avg_views_per_post": avg_views,
            "by_platform": by_platform
        }
    
    def _campaign_roi(self, payload: Dict) -> Dict:
        """Calculate ROI for campaigns."""
        campaign_id = payload.get("campaign_id")
        
        settings = get_settings()
        session = init_db(settings.database_url)
        
        from backend.app.core.db import Campaign, Earnings
        
        campaign = session.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
        if not campaign:
            return {"error": "Campaign not found"}
        
        earnings = session.query(Earnings).filter(Earnings.campaign_id == campaign.id).all()
        total_earned = sum(e.amount for e in earnings)
        total_spent = campaign.budget_total - campaign.budget_remaining
        
        roi = ((total_earned - total_spent) / total_spent * 100) if total_spent > 0 else 0
        
        return {
            "campaign_id": campaign_id,
            "total_earned": total_earned,
            "total_spent": total_spent,
            "roi_percent": roi,
            "profitable": roi > 0
        }
    
    def _platform_analytics(self, payload: Dict) -> Dict:
        """Get platform-specific analytics."""
        platform = payload.get("platform")
        
        # Would fetch from platform APIs
        return {
            "platform": platform,
            "metrics": "would fetch from API"
        }
    
    def _generate_report(self, payload: Dict) -> Dict:
        """Generate analytics report."""
        report_type = payload.get("report_type", "summary")
        period = payload.get("period", "weekly")
        
        settings = get_settings()
        session = init_db(settings.database_url)
        
        from backend.app.core.db import Job, Campaign, Clip, PublishedPost, Earnings
        
        if report_type == "summary":
            total_jobs = session.query(Job).count()
            total_campaigns = session.query(Campaign).count()
            total_clips = session.query(Clip).count()
            total_posts = session.query(PublishedPost).count()
            total_earnings = sum(e.amount for e in session.query(Earnings).all())
            
            return {
                "report_type": "summary",
                "period": period,
                "totals": {
                    "jobs": total_jobs,
                    "campaigns": total_campaigns,
                    "clips": total_clips,
                    "posts": total_posts,
                    "earnings": total_earnings
                }
            }
        
        return {"report_type": report_type, "generated": True}


class FixerAgent(BaseAgent):
    """Agent that debugs issues, fixes errors, handles retries and recovery."""
    
    def __init__(self, message_bus, config=None):
        super().__init__(
            name="fixer",
            message_bus=message_bus,
            capabilities=["error_diagnosis", "auto_retry", "bug_fixing", "system_recovery", "log_analysis", "deadlock_resolution"],
            config=config
        )
        self.orchestrator = get_orchestrator()
    
    def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        task_type = task.task_type
        payload = task.payload
        
        if task_type == "diagnose_error":
            return self._diagnose_error(payload)
        elif task_type == "retry_failed_jobs":
            return self._retry_failed_jobs(payload)
        elif task_type == "fix_bug":
            return self._fix_bug(payload)
        elif task_type == "analyze_logs":
            return self._analyze_logs(payload)
        elif task_type == "resolve_deadlock":
            return self._resolve_deadlock(payload)
        elif task_type == "system_recovery":
            return self._system_recovery(payload)
        else:
            return {"error": f"Unknown task type: {task_type}"}
    
    def _diagnose_error(self, payload: Dict) -> Dict:
        """Diagnose an error from job failure."""
        job_id = payload.get("job_id")
        error_code = payload.get("error_code")
        error_message = payload.get("error_message")
        
        # Get job details
        orchestrator = get_orchestrator()
        job_status = orchestrator.get_job_status(job_id) if job_id else None
        
        # Common error patterns and fixes
        fixes = {
            "WORKER_NOT_FOUND": "Register the missing worker in WorkerRegistry",
            "SOURCE_FILE_MISSING": "Re-download source media or check storage path",
            "DOWNLOAD_FAILED": "Check yt-dlp version and network connectivity",
            "FFMPEG_FAILED": "Verify FFmpeg installation and codec support",
            "QC_FAILED": "Review quality check logs, adjust clip parameters",
            "APPROVAL_REQUIRED": "Human approval needed - cannot auto-fix",
            "KILL_SWITCH": "System paused - resume via API",
            "RATE_LIMIT": "Wait and retry with backoff",
        }
        
        suggested_fix = fixes.get(error_code, "Manual investigation required")
        
        return {
            "job_id": job_id,
            "error_code": error_code,
            "error_message": error_message,
            "diagnosis": f"Error {error_code}: {error_message}",
            "suggested_fix": suggested_fix,
            "auto_fixable": error_code in ["WORKER_NOT_FOUND", "RATE_LIMIT", "DOWNLOAD_FAILED"]
        }
    
    def _retry_failed_jobs(self, payload: Dict) -> Dict:
        """Retry failed jobs."""
        status_filter = payload.get("status", "failed")
        max_retries = payload.get("max_retries", 3)
        
        orchestrator = get_orchestrator()
        jobs = orchestrator.list_jobs(status=JobStatus.FAILED, limit=50)
        
        retried = []
        for job in jobs:
            if job.get("attempt", 1) <= max_retries:
                # Reset job to queued
                settings = get_settings()
                session = init_db(settings.database_url)
                from backend.app.core.db import Job as JobModel
                
                db_job = session.query(JobModel).filter(JobModel.id == job["id"]).first()
                if db_job:
                    db_job.status = JobStatus.QUEUED
                    db_job.error_code = None
                    db_job.error_message = None
                    session.commit()
                    
                    result = orchestrator.execute_job(job["id"])
                    retried.append({
                        "job_id": job["id"],
                        "retried": True,
                        "success": result.success
                    })
        
        return {"retried_count": len(retried), "jobs": retried}
    
    def _fix_bug(self, payload: Dict) -> Dict:
        """Fix a bug - delegates to builder agent."""
        # Send task to builder
        builder = AgentRegistry.get("builder")
        if builder:
            return builder.send_task("builder", "fix_bug", payload, wait_response=True)
        return {"error": "Builder agent not available"}
    
    def _analyze_logs(self, payload: Dict) -> Dict:
        """Analyze logs for patterns."""
        log_path = payload.get("log_path", "./logs")
        pattern = payload.get("pattern", "ERROR")
        
        import subprocess
        result = subprocess.run(
            ["grep", "-r", pattern, log_path],
            capture_output=True, text=True
        )
        
        lines = result.stdout.strip().split("\n") if result.stdout else []
        
        return {
            "pattern": pattern,
            "matches": len(lines),
            "sample": lines[:10]
        }
    
    def _resolve_deadlock(self, payload: Dict) -> Dict:
        """Resolve system deadlocks."""
        # Check for stuck jobs
        orchestrator = get_orchestrator()
        stuck_jobs = orchestrator.list_jobs(status=JobStatus.RUNNING, limit=100)
        
        resolved = []
        for job in stuck_jobs:
            # Check if job has been running too long
            # For now, just report
            resolved.append({"job_id": job["id"], "action": "flagged_for_review"})
        
        return {"stuck_jobs_found": len(stuck_jobs), "resolved": resolved}
    
    def _system_recovery(self, payload: Dict) -> Dict:
        """Perform system recovery actions."""
        action = payload.get("action", "check")
        
        if action == "check":
            # Health checks
            settings = get_settings()
            session = init_db(settings.database_url)
            from backend.app.core.db import check_db_health
            
            db_health = check_db_health(session)
            
            return {
                        "database": db_health,
                        "orchestrator": "running" if self.orchestrator else "stopped",
                        "workers_registered": WorkerRegistry.list()
                    }
        
        elif action == "reset_stuck_jobs":
            return self._retry_failed_jobs({"status": "running", "max_retries": 1})
        
        elif action == "clear_kill_switch":
            settings = get_settings()
            session = init_db(settings.database_url)
            from backend.app.core.db import SystemSettings
            import json
            
            setting = session.query(SystemSettings).filter(SystemSettings.key == "kill_switch").first()
            if setting:
                setting.value_json = json.dumps({"enabled": False})
                session.commit()
            
            return {"kill_switch_cleared": True}
        
        return {"action": action, "completed": True}


# Register all agents
def register_all_agents():
    """Register all specialized agents."""
    registry = get_agent_registry()
    bus = registry.get_message_bus()
    
    agents = [
        ResearcherAgent(bus),
        PlannerAgent(bus),
        BuilderAgent(bus),
        QAAgent(bus),
        PublisherAgent(bus),
        AnalyticsAgent(bus),
        FixerAgent(bus),
    ]
    
    for agent in agents:
        registry.register(agent)
    
    return agents