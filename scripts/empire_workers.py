#!/usr/bin/env python3
"""
Automation Empire OS — Lead Generation & Product Research Workers
$0 constraint: local scrapers, Ollama embeddings, free APIs only
"""

import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass

from scripts.worker_base import BaseWorker, WorkerResult, WorkerRegistry
from backend.app.core.config import get_settings
from backend.app.core.db import init_db, Job, JobStatus

logger = logging.getLogger(__name__)


class LeadSourceDiscoveryWorker(BaseWorker):
    """Discover lead sources from free/public sources"""

    def __init__(self):
        super().__init__("lead_source_discovery")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        source_type = payload.get("source_type", "web")
        criteria = payload.get("search_criteria", {})
        max_results = payload.get("max_results", 50)

        leads = []

        if source_type == "web":
            leads = self._discover_web(criteria, max_results)
        elif source_type == "social_media":
            leads = self._discover_social(criteria, max_results)
        elif source_type == "directory":
            leads = self._discover_directories(criteria, max_results)

        # Score and deduplicate
        scored = self._score_leads(leads, criteria)
        deduped = self._deduplicate(scored)

        return WorkerResult(
            success=True,
            output={"leads": deduped[:max_results]},
            metrics={"discovered": len(leads), "scored": len(scored), "deduped": len(deduped)}
        )

    def _discover_web(self, criteria: Dict, max_results: int) -> List[Dict]:
        """Discover from web search - placeholder for actual scraping"""
        industry = criteria.get("industry", "")
        location = criteria.get("location", "")
        logger.info(f"Discovering leads: industry={industry}, location={location}")
        # Would integrate with free search APIs, RSS feeds, etc.
        return []

    def _discover_social(self, criteria: Dict, max_results: int) -> List[Dict]:
        """Discover from social media - placeholder"""
        logger.info("Discovering leads from social media")
        return []

    def _discover_directories(self, criteria: Dict, max_results: int) -> List[Dict]:
        """Discover from business directories - placeholder"""
        logger.info("Discovering leads from directories")
        return []

    def _score_leads(self, leads: List[Dict], criteria: Dict) -> List[Dict]:
        """Score leads based on relevance"""
        for lead in leads:
            score = 50  # base
            if criteria.get("industry") and criteria["industry"].lower() in lead.get("industry", "").lower():
                score += 20
            if criteria.get("location") and criteria["location"].lower() in lead.get("location", "").lower():
                score += 15
            if lead.get("contact_email"):
                score += 10
            if lead.get("company_website"):
                score += 5
            lead["score"] = min(100, score)
        return sorted(leads, key=lambda x: x["score"], reverse=True)

    def _deduplicate(self, leads: List[Dict]) -> List[Dict]:
        """Deduplicate by company+contact fingerprint"""
        seen = set()
        unique = []
        for lead in leads:
            fp = hashlib.md5(f"{lead.get('company_name','')}{lead.get('contact_email','')}".encode()).hexdigest()
            if fp not in seen:
                seen.add(fp)
                lead["fingerprint"] = fp
                unique.append(lead)
        return unique


class LeadExportWorker(BaseWorker):
    """Export leads to CSV/JSON/SQLite"""

    def __init__(self):
        super().__init__("lead_export")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        leads = payload.get("leads", [])
        export_format = payload.get("export_format", "csv")

        if not leads:
            return WorkerResult(success=False, error_code="NO_LEADS", error_message="No leads to export")

        exports_dir = Path(self.settings.storage_dir) / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leads_{timestamp}.{export_format}"
        filepath = exports_dir / filename

        if export_format == "csv":
            self._export_csv(leads, filepath)
        elif export_format == "json":
            self._export_json(leads, filepath)
        elif export_format == "sqlite":
            self._export_sqlite(leads, filepath)

        return WorkerResult(
            success=True,
            output={"export_path": str(filepath), "count": len(leads), "format": export_format},
            metrics={"exported": len(leads)},
            artifacts=[str(filepath)]
        )

    def _export_csv(self, leads: List[Dict], filepath: Path):
        import csv
        if not leads:
            return
        fieldnames = list(leads[0].keys())
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)

    def _export_json(self, leads: List[Dict], filepath: Path):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(leads, f, indent=2, default=str)

    def _export_sqlite(self, leads: List[Dict], filepath: Path):
        import sqlite3
        conn = sqlite3.connect(filepath)
        if leads:
            # Create table dynamically
            cols = ", ".join([f'"{k}" TEXT' for k in leads[0].keys()])
            conn.execute(f"CREATE TABLE leads ({cols})")
            placeholders = ", ".join(["?" for _ in leads[0]])
            for lead in leads:
                conn.execute(f"INSERT INTO leads VALUES ({placeholders})", list(lead.values()))
        conn.commit()
        conn.close()


class ProductScanWorker(BaseWorker):
    """Scan products from marketplaces/trends"""

    def __init__(self):
        super().__init__("product_scan")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        scan_type = payload.get("scan_type", "marketplace")
        target_sites = payload.get("target_sites", [])
        categories = payload.get("categories", [])
        max_products = payload.get("max_products", 100)
        include_trends = payload.get("include_trends", True)

        products = []

        if scan_type == "marketplace":
            products = self._scan_marketplaces(target_sites, categories, max_products)
        elif scan_type == "competitor":
            products = self._scan_competitors(target_sites, categories, max_products)
        elif scan_type == "trend":
            products = self._scan_trends(categories, max_products)

        # Add trend detection if requested
        if include_trends:
            products = self._detect_trends(products)

        return WorkerResult(
            success=True,
            output={"products": products},
            metrics={"scanned": len(products), "scan_type": scan_type}
        )

    def _scan_marketplaces(self, sites: List[str], categories: List[str], max_products: int) -> List[Dict]:
        """Scan marketplace sites - placeholder"""
        logger.info(f"Scanning marketplaces: {sites}, categories: {categories}")
        return []

    def _scan_competitors(self, sites: List[str], categories: List[str], max_products: int) -> List[Dict]:
        """Scan competitor sites - placeholder"""
        logger.info(f"Scanning competitors: {sites}")
        return []

    def _scan_trends(self, categories: List[str], max_products: int) -> List[Dict]:
        """Scan for trending products - placeholder"""
        logger.info(f"Scanning trends for: {categories}")
        return []

    def _detect_trends(self, products: List[Dict]) -> List[Dict]:
        """Detect trends in product data - placeholder for ML analysis"""
        for p in products:
            p["trend_score"] = 0.5
            p["price_momentum"] = "stable"
        return products


class ProductReportWorker(BaseWorker):
    """Generate product research reports"""

    def __init__(self):
        super().__init__("product_report")
        self.settings = get_settings()

    def execute(self, payload: Dict[str, Any]) -> WorkerResult:
        products = payload.get("products", [])
        report_format = payload.get("report_format", "markdown")

        if not products:
            return WorkerResult(success=False, error_code="NO_PRODUCTS", error_message="No products to report on")

        reports_dir = Path(self.settings.storage_dir) / "exports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"product_report_{timestamp}.{report_format}"
        filepath = reports_dir / filename

        if report_format == "markdown":
            self._generate_markdown(products, filepath)
        elif report_format == "json":
            self._generate_json(products, filepath)

        return WorkerResult(
            success=True,
            output={"report_path": str(filepath), "products_analyzed": len(products)},
            metrics={"products": len(products)},
            artifacts=[str(filepath)]
        )

    def _generate_markdown(self, products: List[Dict], filepath: Path):
        lines = [
            f"# Product Research Report",
            f"Generated: {datetime.now().isoformat()}",
            f"Products Analyzed: {len(products)}",
            "",
            "| Product | Category | Price | Trend Score | Opportunity |",
            "|---------|----------|-------|-------------|-------------|"
        ]
        for p in products[:50]:
            lines.append(f"| {p.get('name','N/A')[:30]} | {p.get('category','N/A')} | ${p.get('price',0):.2f} | {p.get('trend_score',0):.2f} | {p.get('opportunity_score','N/A')} |")

        filepath.write_text("\n".join(lines), encoding="utf-8")

    def _generate_json(self, products: List[Dict], filepath: Path):
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_products": len(products),
            "products": products
        }
        filepath.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


# Register workers
WorkerRegistry.register(LeadSourceDiscoveryWorker())
WorkerRegistry.register(LeadExportWorker())
WorkerRegistry.register(ProductScanWorker())
WorkerRegistry.register(ProductReportWorker())