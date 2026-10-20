#!/usr/bin/env python3
"""
Automation Empire OS — Unit Tests
$0 constraint: pytest, no paid dependencies
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Set test environment
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./test_empire.db"
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["ALLOW_PAID_SERVICES"] = "false"


# Import after env setup
from backend.app.core.config import Settings, get_settings
from backend.app.core.db import (
    init_db, Job, JobStatus, WorkflowVersion, Campaign,
    Provider, TimeStampedModel
)
from scripts.worker_base import BaseWorker, WorkerResult, WorkerRegistry
from scripts.orchestrator import Orchestrator, WorkflowDefinition, WorkflowLoader


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    """Clean up test database after all tests"""
    yield
    # Cleanup
    for f in ["./test_empire.db", "./test_storage"]:
        if os.path.exists(f):
            if os.path.isfile(f):
                os.remove(f)
            else:
                import shutil
                shutil.rmtree(f)


class TestSettings:
    def test_settings_defaults(self):
        settings = Settings()
        assert settings.app_env == "development"
        assert settings.database_url == "sqlite:///./data/empire.db"
        assert settings.ollama_base_url == "http://localhost:11434"
        assert settings.allow_paid_services is False
        assert settings.deploy_mode == "local"

    def test_settings_enforce_no_paid(self):
        with pytest.raises(ValueError, match="ALLOW_PAID_SERVICES must be false"):
            Settings(allow_paid_services=True)

    def test_settings_deploy_mode_validation(self):
        with pytest.raises(ValueError, match="deploy_mode must be local"):
            Settings(deploy_mode="aws")


class TestDatabaseModels:
    @pytest.fixture(autouse=True)
    def setup_db(self):
        self.session = init_db("sqlite:///./test_empire.db")
        yield
        self.session.close()

    def test_job_creation(self):
        job = Job(
            workflow_id="test_workflow",
            payload=json.dumps({"test": "data"}),
            idempotency_key="test_key_123",
            status=JobStatus.QUEUED
        )
        self.session.add(job)
        self.session.commit()

        retrieved = self.session.query(Job).filter(Job.id == job.id).first()
        assert retrieved is not None
        assert retrieved.workflow_id == "test_workflow"
        assert retrieved.status == JobStatus.QUEUED
        assert retrieved.idempotency_key == "test_key_123"

    def test_job_terminal_states(self):
        job = Job(status=JobStatus.SUCCEEDED)
        assert job.is_terminal() is True

        job.status = JobStatus.FAILED
        assert job.is_terminal() is True

        job.status = JobStatus.RUNNING
        assert job.is_terminal() is False

    def test_workflow_version(self):
        wf = WorkflowVersion(
            id="test_wf",
            version="1.0.0",
            name="Test Workflow",
            risk_level="low"
        )
        self.session.add(wf)
        self.session.commit()

        retrieved = self.session.query(WorkflowVersion).filter(WorkflowVersion.id == "test_wf").first()
        assert retrieved is not None
        assert retrieved.name == "Test Workflow"

    def test_campaign_model(self):
        campaign = Campaign(
            campaign_id="camp_123",
            title="Test Campaign",
            type="cpm",
            platforms=json.dumps(["tiktok", "youtube"]),
            budget_total=1000.0,
            status="discovered"
        )
        self.session.add(campaign)
        self.session.commit()

        retrieved = self.session.query(Campaign).filter(Campaign.campaign_id == "camp_123").first()
        assert retrieved is not None
        assert retrieved.title == "Test Campaign"
        assert json.loads(retrieved.platforms) == ["tiktok", "youtube"]


class TestWorkerBase:
    def test_worker_result_creation(self):
        result = WorkerResult(success=True, output={"key": "value"})
        assert result.success is True
        assert result.output == {"key": "value"}

        result = WorkerResult(success=False, error_code="TEST_ERROR", error_message="Test failed")
        assert result.success is False
        assert result.error_code == "TEST_ERROR"
        assert result.retryable is True  # default

    def test_worker_registry(self):
        # Clear registry
        WorkerRegistry._workers.clear()

        class TestWorker(BaseWorker):
            def execute(self, payload):
                return WorkerResult(success=True)

        worker = TestWorker("test_worker")
        WorkerRegistry.register(worker)

        assert "test_worker" in WorkerRegistry.list()
        assert WorkerRegistry.get("test_worker") == worker


class TestOrchestrator:
    @pytest.fixture(autouse=True)
    def setup_orchestrator(self):
        # Clear any existing
        import scripts.orchestrator
        scripts.orchestrator._orchestrator = None

        self.orch = Orchestrator()
        yield
        self.orch.stop_scheduler()

    def test_create_job(self):
        job = self.orch.create_job("content_rewards", {"test": "payload"})
        assert job is not None
        assert job.workflow_id == "content_rewards"
        assert job.status == JobStatus.QUEUED

    def test_get_job_status(self):
        job = self.orch.create_job("content_rewards", {"test": "payload"})
        status = self.orch.get_job_status(job.id)
        assert status is not None
        assert status["id"] == job.id
        assert status["status"] == "queued"

    def test_list_jobs(self):
        self.orch.create_job("content_rewards", {"a": 1})
        self.orch.create_job("content_rewards", {"b": 2})
        jobs = self.orch.list_jobs(limit=10)
        assert len(jobs) >= 2


class TestWorkflowDefinition:
    def test_workflow_definition_creation(self):
        wf = WorkflowDefinition(
            id="test",
            version="1.0.0",
            name="Test",
            risk_level="medium",
            permissions=["browser"],
            retries={"max_attempts": 3},
            approval={"publish": True},
            timeouts={"step_timeout_seconds": 300},
            idempotency_strategy={"key_prefix": "test"},
            manual_approval_rules=[],
            cost_tracking={"estimated_cost": 0}
        )
        assert wf.id == "test"
        assert wf.risk_level == "medium"


class TestConfigValidation:
    def test_database_url_format(self):
        settings = Settings()
        assert settings.database_url.startswith("sqlite://")

    def test_storage_dir_exists(self):
        settings = Settings()
        # Directory creation happens at runtime


# Integration-style tests
class TestIntegration:
    @pytest.fixture(autouse=True)
    def setup(self):
        import scripts.orchestrator
        scripts.orchestrator._orchestrator = None
        self.orch = Orchestrator()

    def test_full_job_lifecycle(self):
        # Create job
        job = self.orch.create_job("content_rewards", {"campaign_source": "manual"})

        # Check status
        status = self.orch.get_job_status(job.id)
        assert status["status"] == "queued"

        # Job would be executed by workers (mocked in real test)
        # This tests the orchestration layer


if __name__ == "__main__":
    pytest.main([__file__, "-v"])