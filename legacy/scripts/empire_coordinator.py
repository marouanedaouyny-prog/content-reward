#!/usr/bin/env python3
"""
Automation Empire OS — Enhanced Empire Coordinator
Runs real campaigns end-to-end with agents passing actual data.
"""

import logging
import time
import threading
import signal
import sys
import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.getcwd())

from scripts.agent_base import get_agent_registry, AgentRegistry, AgentMessage
from scripts.worker_base import WorkerRegistry
from scripts.agents import register_all_agents
from scripts.orchestrator import get_orchestrator, Orchestrator
from scripts.real_pipeline import get_pipeline, RealPipeline, PipelineData
# Import worker modules to register workers
import scripts.content_rewards_workers
import scripts.empire_workers
from backend.app.core.config import get_settings
from backend.app.core.db import init_db, Job, JobStatus, SystemSettings, Campaign, Clip, PublishedPost, Earnings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EmpireStats:
    """Empire-wide statistics."""
    total_jobs: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0
    total_campaigns: int = 0
    total_clips: int = 0
    total_posts: int = 0
    total_earnings: float = 0.0
    active_agents: int = 0
    uptime_seconds: float = 0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    campaigns_completed: int = 0
    pipelines_run: int = 0


class EmpireCoordinator:
    """
    Main coordinator for the Automation Empire OS.
    Runs autonomous cycles with REAL data flow between agents.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.running = False
        self.cycle_interval = self.config.get("cycle_interval", 300)
        self.max_concurrent_jobs = self.config.get("max_concurrent_jobs", 10)
        self.dry_run = self.config.get("dry_run", False)
        self.max_campaigns_per_cycle = self.config.get("max_campaigns_per_cycle", 3)
        
        # Components
        self.orchestrator: Optional[Orchestrator] = None
        self.agent_registry: Optional[AgentRegistry] = None
        self.pipeline: Optional[RealPipeline] = None
        self.stats = EmpireStats()
        
        # Control
        self.cycle_thread: Optional[threading.Thread] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()
        
        # Campaign queue for agents to work on
        self.campaign_queue: List[Dict] = []
        self.active_pipelines: Dict[str, PipelineData] = {}
    
    def initialize(self):
        """Initialize all empire components."""
        logger.info("Initializing Automation Empire OS with REAL pipeline...")
        
        # Initialize database
        settings = get_settings()
        init_db(settings.database_url)
        
        # Initialize pipeline
        self.pipeline = get_pipeline()
        
        # Initialize orchestrator
        self.orchestrator = get_orchestrator()
        
        # Register workflows from YAML
        from scripts.orchestrator import WorkflowLoader
        workflows = WorkflowLoader.load_all(Path("workflows"))
        for wf in workflows.values():
            self.orchestrator.register_workflow(wf)
        
        logger.info(f"Registered workflows: {list(workflows.keys())}")
        
        # Initialize agent registry
        self.agent_registry = get_agent_registry()
        register_all_agents()
        
        logger.info(f"Registered agents: {self.agent_registry.list()}")
        
        # Start all agents
        self.agent_registry.start_all()
        
        # Start orchestrator scheduler
        self.orchestrator.start_scheduler()
        
        # Load initial campaign queue
        self._load_campaign_queue()
        
        self.stats.start_time = datetime.now(timezone.utc)
        logger.info("Empire OS initialized successfully with REAL data pipeline")
    
    def _load_campaign_queue(self):
        """Load campaigns that need processing."""
        settings = get_settings()
        session = init_db(settings.database_url)
        
        # Get campaigns that are qualified but not yet processed
        campaigns = session.query(Campaign).filter(
            Campaign.status.in_(["discovered", "qualified"])
        ).limit(self.max_campaigns_per_cycle).all()
        
        for campaign in campaigns:
            # Handle platforms field - could be list or JSON string
            platforms = campaign.platforms
            if isinstance(platforms, str):
                platforms = json.loads(platforms or '["tiktok", "youtube"]')
            
            self.campaign_queue.append({
                "campaign_id": campaign.campaign_id,
                "title": campaign.title,
                "platforms": platforms,
                "budget_total": campaign.budget_total,
                "min_views": campaign.min_views,
                "source_urls": [],  # Would come from campaign metadata
                "clip_plan": {"aspect_ratio": "9:16", "duration_seconds": 60},
                "publish_config": {
                    "platforms": ["tiktok"],
                    "caption": f"Campaign content #{campaign.campaign_id[:8]}",
                    "tags": ["viral", "trending", "contentrewards"]
                }
            })
        
        logger.info(f"Loaded {len(self.campaign_queue)} campaigns into queue")
    
    def run_cycle(self):
        """Run one autonomous empire cycle with REAL work."""
        cycle_start = time.time()
        logger.info("=== Starting Empire Cycle (REAL) ===")
        
        try:
            # Phase 1: DISCOVER - Researcher finds/imports new opportunities
            self._phase_discover()
            
            # Phase 2: PROCESS - Run real pipelines on queued campaigns
            self._phase_process_campaigns()
            
            # Phase 3: BUILD - Ensure workers/workflows exist
            self._phase_build()
            
            # Phase 4: EXECUTE - Run queued jobs
            self._phase_execute()
            
            # Phase 5: QA - Quality check on generated clips
            self._phase_qa()
            
            # Phase 6: PUBLISH - Distribute content
            self._phase_publish()
            
            # Phase 7: ANALYZE - Track revenue/performance
            self._phase_analyze()
            
            # Phase 8: FIX - Handle errors and recovery
            self._phase_fix()
            
            # Update stats
            self._update_stats()
            
            cycle_time = time.time() - cycle_start
            logger.info(f"=== Empire Cycle Complete ({cycle_time:.1f}s) ===")
            self._log_stats()
            
        except Exception as e:
            logger.error(f"Empire cycle error: {e}", exc_info=True)
    
    def _phase_discover(self):
        """Phase 1: Discover new opportunities - Researcher agent."""
        logger.info("Phase 1: DISCOVER (Researcher)")
        
        researcher = self.agent_registry.get("researcher")
        if not researcher:
            return
        
        # Check capacity
        settings = get_settings()
        session = init_db(settings.database_url)
        pending_jobs = session.query(Job).filter(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])).count()
        
        if pending_jobs < self.max_concurrent_jobs:
            # Researcher discovers new campaigns
            result = researcher.execute_task(type('Task', (), {
                'task_type': 'discover_campaigns',
                'payload': {'source_type': 'manual', 'manual_paste': 'New campaign from researcher agent'}
            })())
            logger.info(f"Researcher discovered: {result}")
            
            # Reload queue after discovery
            self._load_campaign_queue()
        
        # Periodic trend analysis
        if self._should_run_periodic("trend_analysis", 21600):
            result = researcher.execute_task(type('Task', (), {
                'task_type': 'analyze_trends',
                'payload': {'platforms': ['tiktok', 'youtube'], 'max_products': 20}
            })())
            logger.info(f"Trend analysis: {result}")
    
    def _phase_process_campaigns(self):
        """Phase 2: Process campaigns through REAL pipeline."""
        logger.info(f"Phase 2: PROCESS - Running pipelines on {len(self.campaign_queue)} campaigns")
        
        # Process campaigns in queue
        for campaign_data in self.campaign_queue[:self.max_campaigns_per_cycle]:
            if self.shutdown_event.is_set():
                break
            
            logger.info(f"Processing campaign: {campaign_data['campaign_id']}")
            
            # Run the REAL pipeline
            result = self.pipeline.run_campaign_pipeline(campaign_data)
            
            if result.get("success"):
                self.stats.campaigns_completed += 1
                self.stats.pipelines_run += 1
                
                # Update campaign status
                self._update_campaign_status(campaign_data["campaign_id"], "completed")
                
                logger.info(f"Pipeline completed: {result['pipeline_data']}")
            else:
                logger.warning(f"Pipeline failed: {result.get('error')}")
                self._update_campaign_status(campaign_data["campaign_id"], "failed")
            
            # Remove from queue
            self.campaign_queue.remove(campaign_data)
    
    def _phase_build(self):
        """Phase 3: Ensure all workers and workflows are ready."""
        logger.info("Phase 3: BUILD (Builder)")
        
        builder = self.agent_registry.get("builder")
        if not builder:
            return
        
        workers = WorkerRegistry.list()
        logger.info(f"Available workers: {workers}")
        
        required_workers = {
            "content_rewards": ["campaign_discovery", "campaign_parser", "source_download", "clip_generator", "quality_check"],
            "lead_generation": ["lead_source_discovery", "lead_export"],
            "product_research": ["product_scan", "product_report"],
        }
        
        for wf_id, required in required_workers.items():
            for worker_name in required:
                if worker_name not in workers:
                    logger.warning(f"Missing worker {worker_name} for workflow {wf_id}")
    
    def _phase_execute(self):
        """Phase 4: Execute queued jobs via orchestrator."""
        logger.info("Phase 4: EXECUTE")
        
        settings = get_settings()
        session = init_db(settings.database_url)
        
        queued_jobs = session.query(Job).filter(Job.status == JobStatus.QUEUED).limit(self.max_concurrent_jobs).all()
        
        for job in queued_jobs:
            if self.shutdown_event.is_set():
                break
            
            logger.info(f"Executing job {job.id} ({job.workflow_id})")
            result = self.orchestrator.execute_job(job.id)
            
            if result.success:
                self.stats.successful_jobs += 1
                logger.info(f"Job {job.id} succeeded")
            else:
                self.stats.failed_jobs += 1
                logger.warning(f"Job {job.id} failed: {result.error_code} - {result.error_message}")
            
            self.stats.total_jobs += 1
            time.sleep(1)
    
    def _phase_qa(self):
        """Phase 5: Quality assurance on generated clips."""
        logger.info("Phase 5: QA (QA Agent)")
        
        qa = self.agent_registry.get("qa")
        if not qa:
            return
        
        settings = get_settings()
        session = init_db(settings.database_url)
        
        clips = session.query(Clip).filter(Clip.status == "generated").limit(10).all()
        
        for clip in clips:
            result = qa.execute_task(type('Task', (), {
                'task_type': 'check_quality',
                'payload': {'clip_id': clip.id}
            })())
            logger.info(f"QC for clip {clip.id}: {result.get('success', 'unknown')}")
    
    def _phase_publish(self):
        """Phase 6: Publish approved clips to platforms."""
        logger.info("Phase 6: PUBLISH (Publisher Agent)")
        
        publisher = self.agent_registry.get("publisher")
        if not publisher:
            return
        
        settings = get_settings()
        session = init_db(settings.database_url)
        
        clips = session.query(Clip).filter(Clip.status == "qc_passed").limit(5).all()
        
        for clip in clips:
            result = publisher.execute_task(type('Task', (), {
                'task_type': 'publish_clip',
                'payload': {
                    'clip_id': clip.id,
                    'platform': 'tiktok',
                    'caption': f"Campaign content #{clip.campaign_id[:8]}",
                    'tags': ['viral', 'trending', 'contentrewards']
                }
            })())
            logger.info(f"Published clip {clip.id}: {result}")
            
            # Update clip status
            clip.status = "published"
            session.commit()
    
    def _phase_analyze(self):
        """Phase 7: Analyze performance and revenue."""
        logger.info("Phase 7: ANALYZE (Analytics Agent)")
        
        analytics = self.agent_registry.get("analytics")
        if not analytics:
            return
        
        # Track revenue
        result = analytics.execute_task(type('Task', (), {
            'task_type': 'track_revenue',
            'payload': {}
        })())
        logger.info(f"Revenue tracking: ${result.get('total_revenue', 0):.2f}")
        
        # Analyze performance
        if self._should_run_periodic("performance_analysis", 86400):
            result = analytics.execute_task(type('Task', (), {
                'task_type': 'analyze_performance',
                'payload': {}
            })())
            logger.info(f"Performance analysis: {result}")
        
        # Generate report
        if self._should_run_periodic("weekly_report", 604800):
            result = analytics.execute_task(type('Task', (), {
                'task_type': 'generate_report',
                'payload': {'report_type': 'summary', 'period': 'weekly'}
            })())
            logger.info(f"Weekly report generated")
    
    def _phase_fix(self):
        """Phase 8: Fix errors and recover system."""
        logger.info("Phase 8: FIX (Fixer Agent)")
        
        fixer = self.agent_registry.get("fixer")
        if not fixer:
            return
        
        # Retry failed jobs
        result = fixer.execute_task(type('Task', (), {
            'task_type': 'retry_failed_jobs',
            'payload': {'max_retries': 3}
        })())
        logger.info(f"Retry failed jobs: {result}")
        
        # System health check
        result = fixer.execute_task(type('Task', (), {
            'task_type': 'system_recovery',
            'payload': {'action': 'check'}
        })())
        logger.info(f"System health: {result}")
        
        # Check for stuck jobs
        result = fixer.execute_task(type('Task', (), {
            'task_type': 'resolve_deadlock',
            'payload': {}
        })())
        logger.info(f"Deadlock check: {result}")
    
    def _should_run_periodic(self, task_name: str, interval_seconds: int) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.stats.start_time).total_seconds()
        return int(elapsed) % interval_seconds < self.cycle_interval
    
    def _update_campaign_status(self, campaign_id: str, status: str):
        """Update campaign status in database."""
        settings = get_settings()
        session = init_db(settings.database_url)
        campaign = session.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
        if campaign:
            campaign.status = status
            session.commit()
    
    def _update_stats(self):
        """Update empire statistics."""
        settings = get_settings()
        session = init_db(settings.database_url)
        
        self.stats.total_jobs = session.query(Job).count()
        self.stats.successful_jobs = session.query(Job).filter(Job.status == JobStatus.SUCCEEDED).count()
        self.stats.failed_jobs = session.query(Job).filter(Job.status == JobStatus.FAILED).count()
        self.stats.total_campaigns = session.query(Campaign).count()
        self.stats.total_clips = session.query(Clip).count()
        self.stats.total_posts = session.query(PublishedPost).count()
        self.stats.total_earnings = sum(e.amount for e in session.query(Earnings).all())
        self.stats.active_agents = len([a for a in self.agent_registry.get_all().values() if a.status.value == "running"])
        self.stats.uptime_seconds = (datetime.now(timezone.utc) - self.stats.start_time).total_seconds()
    
    def _log_stats(self):
        """Log current empire statistics."""
        logger.info(f"""
╔══════════════════════════════════════════════════════════════╗
║                  EMPIRE OS STATUS                            ║
╠══════════════════════════════════════════════════════════════╣
║ Uptime:          {self.stats.uptime_seconds/3600:.1f} hours                        ║
║ Active Agents:   {self.stats.active_agents}                                    ║
║ Total Jobs:      {self.stats.total_jobs}                                     ║
║  ✓ Succeeded:    {self.stats.successful_jobs}                                     ║
║  ✗ Failed:       {self.stats.failed_jobs}                                     ║
║ Campaigns:       {self.stats.total_campaigns}                                     ║
║ Campaigns Done:  {self.stats.campaigns_completed}                                     ║
║ Pipelines Run:   {self.stats.pipelines_run}                                     ║
║ Clips Generated: {self.stats.total_clips}                                     ║
║ Posts Published: {self.stats.total_posts}                                     ║
║ Total Earnings:  ${self.stats.total_earnings:.2f}                                ║
╚══════════════════════════════════════════════════════════════╝
        """)
    
    def start(self):
        """Start the autonomous empire."""
        if self.running:
            logger.warning("Empire already running")
            return
        
        self.initialize()
        self.running = True
        self.shutdown_event.clear()
        
        self.cycle_thread = threading.Thread(target=self._run_cycles, daemon=True)
        self.cycle_thread.start()
        
        self.monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Empire OS started - running autonomously with REAL pipelines")
    
    def _run_cycles(self):
        while not self.shutdown_event.is_set():
            self.run_cycle()
            self.shutdown_event.wait(self.cycle_interval)
    
    def _monitor(self):
        while not self.shutdown_event.is_set():
            time.sleep(60)
            
            if self.shutdown_event.is_set():
                break
            
            # Check kill switch
            settings = get_settings()
            session = init_db(settings.database_url)
            kill_switch = session.query(SystemSettings).filter(SystemSettings.key == "kill_switch").first()
            
            if kill_switch:
                import json
                if json.loads(kill_switch.value_json).get("enabled", False):
                    logger.warning("Kill switch activated - pausing empire")
                    self.shutdown_event.wait(60)
                    continue
            
            # Check agent health
            for name, agent in self.agent_registry.get_all().items():
                if agent.status.value == "failed":
                    logger.error(f"Agent {name} failed - restarting")
                    agent.start()
    
    def stop(self):
        logger.info("Stopping Empire OS...")
        self.running = False
        self.shutdown_event.set()
        
        if self.cycle_thread:
            self.cycle_thread.join(timeout=10)
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        
        if self.agent_registry:
            self.agent_registry.stop_all()
        
        if self.orchestrator:
            self.orchestrator.stop_scheduler()
        
        logger.info("Empire OS stopped")


# Global coordinator instance
_coordinator: Optional[EmpireCoordinator] = None


def get_coordinator() -> EmpireCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = EmpireCoordinator()
    return _coordinator


def run_empire(config: Dict[str, Any] = None):
    coordinator = EmpireCoordinator(config)
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        coordinator.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        coordinator.start()
        while coordinator.running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        coordinator.stop()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Automation Empire OS - Autonomous Coordinator with REAL Pipeline")
    parser.add_argument("--cycle-interval", type=int, default=300, help="Cycle interval in seconds")
    parser.add_argument("--max-jobs", type=int, default=10, help="Max concurrent jobs")
    parser.add_argument("--max-campaigns", type=int, default=3, help="Max campaigns per cycle")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    
    args = parser.parse_args()
    
    config = {
        "cycle_interval": args.cycle_interval,
        "max_concurrent_jobs": args.max_jobs,
        "max_campaigns_per_cycle": args.max_campaigns,
        "dry_run": args.dry_run,
    }
    
    coordinator = EmpireCoordinator(config)
    coordinator.initialize()
    
    if args.once:
        coordinator.run_cycle()
    else:
        run_empire(config)