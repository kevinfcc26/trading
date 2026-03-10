"""Learning domain services — knowledge translation."""
from __future__ import annotations

from .entities import KnowledgeItem, KnowledgeType


class KnowledgeTranslator:
    """Translates KnowledgeItems into strategy configuration hints.

    This is a lightweight mapping layer — not a full ML inference.
    Claude performs the deep extraction; this class applies the results.
    """

    def extract_risk_rules(self, items: list[KnowledgeItem]) -> dict:
        """Return risk parameter adjustments derived from knowledge items."""
        adjustments: dict = {}

        for item in items:
            if item.knowledge_type == KnowledgeType.RISK_CONCEPT:
                # Simple keyword-based extraction (can be expanded)
                content_lower = item.content.lower()

                if "never risk more than 1%" in content_lower:
                    adjustments["risk_per_trade"] = min(adjustments.get("risk_per_trade", 0.01), 0.01)

                if "2:1 risk reward" in content_lower or "2:1 r:r" in content_lower:
                    adjustments["rr_ratio"] = max(adjustments.get("rr_ratio", 2.0), 2.0)

                if "trend following" in content_lower:
                    adjustments["use_trend_filter"] = True

        return adjustments
