"""AIStrategyFactory — builds the correct AI reasoning layer from settings.

Supported providers (set AI_PROVIDER in .env):
  "claude"  — Anthropic Claude API (requires credits)
  "ollama"  — Local Ollama server (free, requires ollama running)
  "none"    — No LLM; AI slot always returns the TA signal as-is

Adding a new provider:
  1. Create src/strategy/infrastructure/<name>_strategy.py
  2. Add an elif branch in build_ai_strategy()
  3. Add any needed settings to config/settings.py
"""
from __future__ import annotations

import logging

from config.settings import Settings
from market.domain.entities import CandleSeries
from strategy.domain.entities import Direction, Signal, SignalSource

logger = logging.getLogger(__name__)


class NullAIStrategy:
    """No-op AI layer — passes through the TA signal unchanged.

    Used when AI_PROVIDER=none. The weight assigned to this slot
    effectively boosts TA in the aggregator.
    """

    async def generate(self, candles: CandleSeries, **kwargs) -> Signal:
        ta_signal: Signal | None = kwargs.get("ta_signal")
        if ta_signal is not None:
            return ta_signal
        return Signal(
            instrument_symbol=candles.instrument_symbol,
            timeframe=candles.timeframe,
            direction=Direction.HOLD,
            confidence=0.0,
            source=SignalSource.NONE,
            reasoning="AI provider disabled",
        )


def build_ai_strategy(settings: Settings):
    """Return the configured AI strategy instance.

    Returns one of: ClaudeStrategy | OllamaStrategy | NullAIStrategy
    """
    provider = settings.ai_provider.lower().strip()

    if provider == "claude":
        from strategy.infrastructure.claude_strategy import ClaudeStrategy
        logger.info("AI provider: Claude (%s)", "claude-sonnet-4-6")
        return ClaudeStrategy(api_key=settings.anthropic_api_key.get_secret_value())

    if provider == "ollama":
        from strategy.infrastructure.ollama_strategy import OllamaStrategy
        logger.info(
            "AI provider: Ollama (model=%s url=%s)",
            settings.ollama_model, settings.ollama_url,
        )
        return OllamaStrategy(model=settings.ollama_model, base_url=settings.ollama_url)

    if provider == "none":
        logger.info("AI provider: None (TA signal passthrough)")
        return NullAIStrategy()

    logger.warning("Unknown AI_PROVIDER=%r — falling back to none", provider)
    return NullAIStrategy()
