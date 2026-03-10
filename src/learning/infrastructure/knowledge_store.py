"""KnowledgeStore — PostgreSQL repository for KnowledgeItems.

Uses a simple JSON-based approach until Alembic migration 0002 adds
the knowledge_items table. Falls back to in-memory for tests.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

from learning.domain.entities import KnowledgeItem, KnowledgeType

logger = logging.getLogger(__name__)


class FileKnowledgeStore:
    """Simple file-based KnowledgeItem store (JSONL format).

    Used for MVP and testing. Replace with SQLKnowledgeStore
    once migration 0002 is applied.
    """

    def __init__(self, store_path: str | Path = "models/knowledge.jsonl") -> None:
        self._path = Path(store_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _serialize(self, item: KnowledgeItem) -> str:
        return json.dumps(
            {
                "id": str(item.id),
                "knowledge_type": item.knowledge_type.value,
                "title": item.title,
                "content": item.content,
                "source_document": item.source_document,
                "source_section": item.source_section,
                "confidence": item.confidence,
                "tags": item.tags,
                "created_at": item.created_at.isoformat(),
            }
        )

    async def save(self, item: KnowledgeItem) -> KnowledgeItem:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(self._serialize(item) + "\n")
        logger.debug("Saved KnowledgeItem: %s", item.title)
        return item

    async def get_all(self, knowledge_type: str | None = None) -> list[KnowledgeItem]:
        if not self._path.exists():
            return []

        items = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    from datetime import datetime
                    item = KnowledgeItem(
                        knowledge_type=KnowledgeType(d["knowledge_type"]),
                        title=d["title"],
                        content=d["content"],
                        source_document=d.get("source_document", ""),
                        source_section=d.get("source_section", ""),
                        confidence=d.get("confidence", 1.0),
                        tags=d.get("tags", []),
                        created_at=datetime.fromisoformat(d["created_at"]),
                    )
                    if knowledge_type is None or item.knowledge_type.value == knowledge_type:
                        items.append(item)
                except Exception as e:
                    logger.warning("Skipping corrupt knowledge record: %s", e)

        return items

    async def get_by_id(self, item_id: UUID) -> KnowledgeItem | None:
        items = await self.get_all()
        for item in items:
            if item.id == item_id:
                return item
        return None
