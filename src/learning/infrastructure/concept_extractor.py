"""ConceptExtractor — uses Claude to extract KnowledgeItems from document sections."""
from __future__ import annotations

import json
import logging

import anthropic

from learning.domain.entities import KnowledgeItem, KnowledgeType

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are an expert at extracting actionable trading knowledge from text.

Given a document section, extract 1-5 distinct knowledge items.
Each item must be a self-contained principle, rule, or concept.

Respond with a JSON array. Each element must have:
{
  "type": "PRINCIPLE" | "RULE" | "RISK_CONCEPT" | "INDICATOR" | "PATTERN",
  "title": "<short descriptive title>",
  "content": "<full knowledge item text, 50-200 words>",
  "tags": ["<tag1>", "<tag2>"],
  "confidence": <float 0.0-1.0>
}

Rules:
- Only extract knowledge that is specific and actionable
- Skip vague or subjective statements
- Tags should be lowercase: e.g. ["trend", "risk", "rsi", "position-sizing"]
- Confidence = how clearly stated this knowledge is in the source text
"""


class ConceptExtractor:
    """Extracts structured KnowledgeItems from parsed document sections."""

    def __init__(self, api_key: str, model: str = _MODEL) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def extract(self, section: dict, source_document: str = "") -> list[KnowledgeItem]:
        """Extract knowledge items from a single parsed section."""
        section_title = section.get("section", "")
        section_content = section.get("content", "")

        if not section_content:
            return []

        prompt = f"""Section: {section_title}

{section_content}

Extract knowledge items from the above section."""

        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()

            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            items_data = json.loads(raw)
            items = []
            for d in items_data:
                try:
                    items.append(
                        KnowledgeItem(
                            knowledge_type=KnowledgeType(d["type"]),
                            title=d["title"],
                            content=d["content"],
                            source_document=source_document,
                            source_section=section_title,
                            confidence=float(d.get("confidence", 1.0)),
                            tags=d.get("tags", []),
                        )
                    )
                except (KeyError, ValueError) as e:
                    logger.warning("Skipping malformed knowledge item: %s", e)

            logger.info(
                "Extracted %d items from section '%s'", len(items), section_title
            )
            return items

        except Exception as exc:
            logger.error("ConceptExtractor failed for section '%s': %s", section_title, exc)
            return []

    def extract_all(self, sections: list[dict], source_document: str = "") -> list[KnowledgeItem]:
        """Extract knowledge items from all sections."""
        all_items = []
        for section in sections:
            items = self.extract(section, source_document)
            all_items.extend(items)
        return all_items
