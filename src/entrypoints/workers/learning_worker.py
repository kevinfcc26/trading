"""LearningWorker — background worker for knowledge ingestion and model monitoring.

Weekend learning mode:
    When the Forex market is closed (Fri 22:00 → Sun 22:00 UTC) the worker
    switches to an enhanced learning schedule:
      - Document check interval drops from 1 hour → 30 minutes
      - A weekly recap is logged once per weekend window:
          * Time since last model training
          * Number of knowledge items in store
          * Placeholder hook for XGBoost retraining and RL episode runs (Phase 12)
    This ensures the system uses market downtime to absorb new knowledge and
    prepare better models for the next trading week.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from market.domain.market_schedule import is_weekend

logger = logging.getLogger(__name__)

_WEEKDAY_INTERVAL = 3600    # 1 hour during trading week
_WEEKEND_INTERVAL = 1800    # 30 minutes during weekend learning window


class LearningWorker:
    """Periodically ingests new documents and runs a weekend learning recap.

    Usage: run as a background asyncio task alongside TradingWorker.
    """

    def __init__(
        self,
        watch_directory: str | Path = "docs/knowledge",
        anthropic_api_key: str = "",
        check_interval_seconds: int = _WEEKDAY_INTERVAL,
    ) -> None:
        self._watch_dir = Path(watch_directory)
        self._api_key = anthropic_api_key
        self._base_interval = check_interval_seconds
        self._shutdown = asyncio.Event()
        self._ingested: set[str] = set()
        self._recap_done_for_weekend: bool = False  # fire recap once per weekend window

    async def run(self) -> None:
        self._watch_dir.mkdir(parents=True, exist_ok=True)
        logger.info("LearningWorker started, watching: %s", self._watch_dir)

        while not self._shutdown.is_set():
            now = datetime.now(timezone.utc)
            in_weekend = is_weekend(now)

            # ── Weekend recap (once per closure window) ───────────────────
            if in_weekend and not self._recap_done_for_weekend:
                await self._weekend_recap()
                self._recap_done_for_weekend = True
            elif not in_weekend:
                self._recap_done_for_weekend = False  # reset for next weekend

            # ── Document ingestion ────────────────────────────────────────
            try:
                await self._check_new_documents()
            except Exception as exc:
                logger.error("LearningWorker error: %s", exc, exc_info=True)

            # ── Adaptive sleep interval ───────────────────────────────────
            interval = _WEEKEND_INTERVAL if in_weekend else self._base_interval
            if in_weekend:
                logger.debug(
                    "Weekend learning mode — next check in %dm", interval // 60
                )
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

        logger.info("LearningWorker stopped")

    async def _check_new_documents(self) -> None:
        from learning.application.use_cases import IngestDocumentUseCase
        from learning.infrastructure.concept_extractor import ConceptExtractor
        from learning.infrastructure.document_loader import DocumentLoader
        from learning.infrastructure.knowledge_store import FileKnowledgeStore
        from learning.infrastructure.semantic_parser import SemanticParser

        supported_exts = {".pdf", ".txt", ".md", ".epub"}
        new_files = [
            p for p in self._watch_dir.iterdir()
            if p.suffix.lower() in supported_exts and p.name not in self._ingested
        ]

        if not new_files:
            return

        logger.info("Found %d new document(s) to ingest", len(new_files))

        loader = DocumentLoader()
        parser = SemanticParser(api_key=self._api_key)
        extractor = ConceptExtractor(api_key=self._api_key)
        kb = FileKnowledgeStore()
        use_case = IngestDocumentUseCase(loader, parser, extractor, kb)

        for file_path in new_files:
            try:
                items = await use_case.execute(file_path)
                self._ingested.add(file_path.name)
                logger.info("Ingested %d items from %s", len(items), file_path.name)
            except Exception as exc:
                logger.error("Failed to ingest %s: %s", file_path.name, exc)

    async def _weekend_recap(self) -> None:
        """Run once at the start of each weekend closure window.

        Logs a performance and knowledge summary.
        Phase 12 hook: XGBoost retraining and RL episode evaluation will run here.
        """
        now = datetime.now(timezone.utc)
        logger.info(
            "═══ Weekend Learning Mode activated (%s) ═══",
            now.strftime("%A %Y-%m-%d %H:%M UTC"),
        )

        # Knowledge store summary
        try:
            from learning.infrastructure.knowledge_store import FileKnowledgeStore
            kb = FileKnowledgeStore()
            all_items = await kb.get_all()
            logger.info("Knowledge store: %d concepts accumulated", len(all_items))
        except Exception as exc:
            logger.warning("Could not read knowledge store: %s", exc)

        # Model registry summary
        try:
            from learning.infrastructure.model_registry import ModelRegistry
            registry = ModelRegistry()
            versions = registry.list_versions()
            if versions:
                latest = versions[-1]
                logger.info(
                    "Latest model: %s (accuracy=%.4f)",
                    latest.version,
                    latest.metrics.get("accuracy", 0.0),
                )
            else:
                logger.info("No trained model found — consider running 'brocker ingest' + training")
        except Exception as exc:
            logger.warning("Could not read model registry: %s", exc)

        logger.info(
            "Weekend agenda: ingest new documents every %dm "
            "→ Phase 12 will add XGBoost retraining + RL episode here",
            _WEEKEND_INTERVAL // 60,
        )

    def stop(self) -> None:
        self._shutdown.set()
