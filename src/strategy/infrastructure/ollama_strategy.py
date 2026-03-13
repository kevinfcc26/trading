"""OllamaStrategy — local LLM reasoning layer via Ollama REST API."""
from __future__ import annotations

import json
import logging

import httpx

from market.domain.entities import CandleSeries
from strategy.domain.entities import Direction, Signal, SignalSource

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "llama3.2"
_DEFAULT_URL = "http://localhost:11434"
_TIMEOUT = 180.0

_SYSTEM_PROMPT = """You are an FX trading signal classifier. Analyze the provided market data and output a directional signal.

Respond ONLY with valid JSON — no markdown, no text outside JSON:
{
  "direction": "BUY" | "SELL" | "HOLD",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<1-2 sentences>",
  "stop_loss_note": "<nearest structural level against the trade>",
  "invalidation": "<what price action invalidates this setup>"
}

Decision rules:
- BUY: D1/H4 trend is bullish AND price near support OR TA/ML signals align bullish.
- SELL: D1/H4 trend is bearish AND price near resistance OR TA/ML signals align bearish.
- HOLD: signals conflict, no clear structure, or inside tight consolidation.
- Use HOLD sparingly — only when direction is genuinely unclear.
- Confidence reflects how strongly the evidence supports the direction (0.5=uncertain, 0.9=very clear).
"""


class OllamaStrategy:
    """Uses a local Ollama LLM as the professional reasoning layer."""

    def __init__(self, model: str = _DEFAULT_MODEL, base_url: str = _DEFAULT_URL) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def generate(self, candles: CandleSeries, **kwargs) -> Signal:
        ta_signal: Signal | None = kwargs.get("ta_signal")
        ml_signal: Signal | None = kwargs.get("ml_signal")
        mtf_context = kwargs.get("mtf_context")
        sr_context = kwargs.get("sr_context")

        if ta_signal is None or ml_signal is None:
            return self._hold(candles, "No TA/ML context provided")

        if mtf_context is not None:
            from strategy.infrastructure.professional_prompt_builder import ProfessionalPromptBuilder
            prompt = ProfessionalPromptBuilder().build(
                candles, ta_signal, ml_signal, mtf_context, sr_context
            )
        else:
            prompt = _build_simple_prompt(candles, ta_signal, ml_signal)

        try:
            result = await self._call_ollama(prompt)
        except Exception as exc:
            logger.error("Ollama API failed: %s", exc)
            return self._hold(candles, f"Ollama error: {exc}")

        context = {}
        if result.get("stop_loss_note"):
            context["stop_loss_note"] = result["stop_loss_note"]
        if result.get("invalidation"):
            context["invalidation"] = result["invalidation"]

        return Signal(
            instrument_symbol=candles.instrument_symbol,
            timeframe=candles.timeframe,
            direction=result["direction"],
            confidence=result["confidence"],
            source=SignalSource.OLLAMA,
            reasoning=result["reasoning"],
            context=context,
        )

    async def _call_ollama(self, prompt: str) -> dict:
        payload = {
            "model": self._model,
            "prompt": f"{_SYSTEM_PROMPT}\n\n{prompt}",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 400},
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{self._base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "")
            logger.debug("Ollama raw response: %s", raw[:300])
            return _parse_response(raw)

    def _hold(self, candles: CandleSeries, reason: str) -> Signal:
        return Signal(
            instrument_symbol=candles.instrument_symbol,
            timeframe=candles.timeframe,
            direction=Direction.HOLD,
            confidence=0.0,
            source=SignalSource.OLLAMA,
            reasoning=reason,
        )


def _build_simple_prompt(candles: CandleSeries, ta_signal: Signal, ml_signal: Signal) -> str:
    recent = candles.candles[-5:] if candles.candles else []
    candles_str = "\n".join(
        f"  [{c.time.strftime('%Y-%m-%d %H:%M')}] O={c.open:.5f} H={c.high:.5f} "
        f"L={c.low:.5f} C={c.close:.5f} V={c.volume:.0f}"
        for c in recent
    )
    ta_ctx = json.dumps(
        {k: round(v, 6) if isinstance(v, float) and v == v else 0.0
         for k, v in ta_signal.context.items()}, indent=2)
    ml_ctx = json.dumps(
        {k: round(v, 6) if isinstance(v, float) and v == v else 0.0
         for k, v in ml_signal.context.items()}, indent=2)

    return f"""# {candles.instrument_symbol} {candles.timeframe.value}

Candles:
{candles_str}

TA: {ta_signal.direction.value} conf={ta_signal.confidence:.2f}
{ta_ctx}

ML: {ml_signal.direction.value} conf={ml_signal.confidence:.2f}
{ml_ctx}

Evaluate and respond with JSON only."""


def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        raw = raw[start:end]

    data = json.loads(raw)
    direction = Direction(data["direction"].upper())
    confidence = float(data["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"Invalid confidence: {confidence}")

    return {
        "direction": direction,
        "confidence": confidence,
        "reasoning": str(data.get("reasoning", "")),
        "stop_loss_note": str(data.get("stop_loss_note", "")),
        "invalidation": str(data.get("invalidation", "")),
    }
