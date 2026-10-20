#!/usr/bin/env python3
"""
Automation Empire OS — Integration Tests
$0 constraint: pytest, local services only
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./test_empire.db"
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["ALLOW_PAID_SERVICES"] = "false"

from backend.app.core.db import init_db, Job, JobStatus, Campaign, SourceMedia, Clip
from scripts.content_rewards_workers import (
    CampaignDiscoveryWorker, CampaignParserWorker,
    SourceDownloadWorker, ClipGeneratorWorker, QualityCheckWorker
)
from scripts.empire_workers import (
    LeadSourceDiscoveryWorker, LeadExportWorker,
    ProductScanWorker, ProductReportWorker
)


@pytest.fixture(scope="session", autouse=True)
def cleanup():
    yield
    for f in ["./test_empire.db", "./test_storage"]:
        if os.path.exists(f):
            if os.path.isfile(f):
                os.remove(f)
            else:
                import shutil
                shutil.rmtree(f)


class TestContentRewardsWorkers:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = init_db("sqlite:///./test_empire.db")

    def test_campaign_discovery_manual(self):
        worker = CampaignDiscoveryWorker()
        result = worker.execute({
            "source_type": "manual",
            "manual_paste": "Test campaign for tech products, $5 CPM, 1000 min views"
        })
        assert result.success is True
        assert "campaigns_discovered" in result.output

    def test_campaign_parser(self):
        # First create a campaign
        campaign = Campaign(
            campaign_id="test_camp_123",
            title="Test Campaign",
            type="cpm",
            platforms=json.dumps(["tiktok"]),
            min_views=1000,
            max_payout=500,
            status="discovered"
        )
        self.session.add(campaign)
        self.session.commit()

        worker = CampaignParserWorker()
        result = worker.execute({"campaign_id": "test_camp_123"})
        assert result.success is True
        assert result.output.get("requirements_parsed", 0) > 0


class TestEmpireWorkers:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = init_db("sqlite:///./test_empire.db")

    def test_lead_discovery(self):
        worker = LeadSourceDiscoveryWorker()
        result = worker.execute({
            "source_type": "web",
            "search_criteria": {"industry": "technology", "location": "san francisco"},
            "max_results": 10
        })
        # Should succeed even with empty results (placeholder implementation)
        assert result.success is True

    def test_lead_export_csv(self):
        worker = LeadExportWorker()
        test_leads = [
            {"id": "1", "company_name": "Test Co", "contact_email": "test@test.com", "score": 80}
        ]
        result = worker.execute({"leads": test_leads, "export_format": "csv"})
        assert result.success is True
        assert "export_path" in result.output
        assert result.output["export_path"].endswith(".csv")

    def test_product_scan(self):
        worker = ProductScanWorker()
        result = worker.execute({
            "scan_type": "marketplace",
            "categories": ["electronics"],
            "max_products": 50
        })
        assert result.success is True

    def test_product_report(self):
        worker = ProductReportWorker()
        test_products = [
            {"name": "Test Product", "category": "electronics", "price": 99.99, "trend_score": 0.8}
        ]
        result = worker.execute({"products": test_products, "report_format": "markdown"})
        assert result.success is True
        assert "report_path" in result.output
        assert result.output["report_path"].endswith(".md")


class TestDatabaseIntegration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = init_db("sqlite:///./test_empire.db")

    def test_campaign_to_clip_pipeline(self):
        # Create campaign
        campaign = Campaign(
            campaign_id="pipeline_test",
            title="Pipeline Test",
            type="cpm",
            platforms=json.dumps(["tiktok"]),
            budget_total=1000,
            status="discovered"
        )
        self.session.add(campaign)
        self.session.commit()

        # Create source media
        media = SourceMedia(
            campaign_id=campaign.id,
            source_url="https://example.com/video.mp4",
            title="Test Video",
            file_hash="abc123",
            media_type="video",
            duration=120,
            status="downloaded"
        )
        self.session.add(media)
        self.session.commit()

        # Create clip
        clip = Clip(
            campaign_id=campaign.id,
            source_media_id=media.id,
            clip_path="processed/test_clip.mp4",
            clip_hash="def456",
            aspect_ratio="9:16",
            duration=30,
            status="generated"
        )
        self.session.add(clip)
        self.session.commit()

        # Verify relationships
        assert clip.campaign_id == campaign.id
        assert clip.source_media_id == media.id

        retrieved_campaign = self.session.query(Campaign).filter(Campaign.campaign_id == "pipeline_test").first()
        assert retrieved_campaign is not None


class TestOrchestratorIntegration:
    def test_orchestrator_workflow_registration(self):
        import scripts.orchestrator
        scripts.orchestrator._orchestrator = None

        from scripts.orchestrator import Orchestrator, WorkflowDefinition

        orch = Orchestrator()

        # Register a test workflow
        wf = WorkflowDefinition(
            id="integration_test",
            version="1.0.0",
            name="Integration Test",
            risk_level="low",
            permissions=["filesystem"],
            retries={"max_attempts": 2},
            approval={},
            timeouts={"step_timeout_seconds": 60},
            idempotency_strategy={"key_prefix": "test"},
            manual_approval_rules=[],
            cost_tracking={"estimated_cost": 0}
        )
        orch.register_workflow(wf)

        assert "integration_test" in orch.workflows

        # Create job
        job = orch.create_job("integration_test", {"test": "data"})
        assert job.workflow_id == "integration_test"

        orch.stop_scheduler()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])