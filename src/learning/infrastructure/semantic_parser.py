"""SemanticParser — uses Claude to break a document into structured sections."""
from __future__ import annotations

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are an expert at analyzing trading and finance documents.
Your task is to break a document into structured sections, identifying the key topic of each.

Respond with a JSON array. Each element must have:
{
  "section": "<section title>",
  "content": "<full text of the section>",
  "topic": "principles|risk|indicators|patterns|psychology|strategy|general"
}

Rules:
- Extract only sections relevant to trading, investing, or risk management
- Skip table of contents, bibliography, index, and boilerplate
- Maximum 20 sections per document
- Each content field should be self-contained (50-500 words)
"""


class SemanticParser:
    """Sends raw document text to Claude and receives structured sections."""

    def __init__(self, api_key: str, model: str = _MODEL) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def parse(self, raw_text: str, document_name: str = "") -> list[dict]:
        """Parse raw document text into structured sections."""
        # Truncate to avoid token limits (approx 50k chars = ~12k tokens)
        max_chars = 50_000
        truncated = raw_text[:max_chars]
        if len(raw_text) > max_chars:
            logger.warning("Document truncated to %d chars for parsing: %s", max_chars, document_name)

        prompt = f"""Document: {document_name}

--- DOCUMENT TEXT ---
{truncated}
--- END DOCUMENT ---

Parse the above document into structured sections."""

        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()

            # Strip markdown code fences
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            sections = json.loads(raw)
            logger.info("Parsed %d sections from %s", len(sections), document_name)
            return sections
        except Exception as exc:
            logger.error("SemanticParser failed for %s: %s", document_name, exc)
            return []
