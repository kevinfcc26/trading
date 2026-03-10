"""
ClaudeAdapter — calls the Anthropic API and parses the JSON response into a Signal.
Uses tenacity for retry on transient errors.
"""
import json
import logging

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from domain.entities import CandleSeries, Direction, Signal, SignalSource
from domain.ports import ISignalGenerator

from .prompt_builder import ClaudePromptBuilder

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"


class ClaudeAdapter(ISignalGenerator):
    def __init__(self, api_key: str, model: str = _MODEL) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._prompt_builder = ClaudePromptBuilder()

    async def generate(
        self,
        candles: CandleSeries,
        ta_signal: Signal | None = None,
        ml_signal: Signal | None = None,
    ) -> Signal:
        """
        Override: accepts optional ta_signal and ml_signal to inject context.
        Falls back to HOLD if API fails after retries.
        """
        if ta_signal is None or ml_signal is None:
            return Signal(
                instrument_symbol=candles.instrument_symbol,
                timeframe=candles.timeframe,
                direction=Direction.HOLD,
                confidence=0.0,
                source=SignalSource.CLAUDE,
                reasoning="No TA/ML context provided",
            )

        prompt = self._prompt_builder.build(candles, ta_signal, ml_signal)

        try:
            result = await self._call_api(prompt)
        except Exception as exc:
            logger.error("Claude API failed: %s", exc)
            return Signal(
                instrument_symbol=candles.instrument_symbol,
                timeframe=candles.timeframe,
                direction=Direction.HOLD,
                confidence=0.0,
                source=SignalSource.CLAUDE,
                reasoning=f"API error: {exc}",
            )

        return Signal(
            instrument_symbol=candles.instrument_symbol,
            timeframe=candles.timeframe,
            direction=result["direction"],
            confidence=result["confidence"],
            source=SignalSource.CLAUDE,
            reasoning=result["reasoning"],
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_api(self, user_prompt: str) -> dict:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=ClaudePromptBuilder.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)

        direction = Direction(data["direction"].upper())
        confidence = float(data["confidence"])
        reasoning = str(data.get("reasoning", ""))

        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Invalid confidence: {confidence}")

        return {"direction": direction, "confidence": confidence, "reasoning": reasoning}
