"""ProfessionalPromptBuilder — structured professional trader brief for LLM."""
from __future__ import annotations

from datetime import datetime, timezone

from market.domain.entities import CandleSeries
from strategy.domain.entities import Direction, Signal
from strategy.domain.value_objects import MultiTimeframeContext, SRContext

_SESSIONS = [
    (0, 7,   "Sydney/Tokyo",              "low",     "avoid — low liquidity"),
    (7, 9,   "Tokyo/London Overlap",       "medium",  "moderate — watch for reversals"),
    (8, 12,  "London Session",             "high",    "strong trends, good for breakouts"),
    (12, 17, "London/New York Overlap",    "highest", "best — tightest spreads, strongest moves"),
    (17, 21, "New York Session",           "medium",  "decent — fading London trends"),
    (21, 24, "New York Close",             "low",     "avoid — positions closing, erratic"),
]


def _get_session(hour_utc: int) -> tuple[str, str, str]:
    for start, end, name, quality, advice in _SESSIONS:
        if start <= hour_utc < end:
            return name, quality, advice
    return "Off-hours", "very low", "avoid — very low liquidity"


class ProfessionalPromptBuilder:
    """Builds the structured professional trader brief for LLMs."""

    def build(
        self,
        candles: CandleSeries,
        ta_signal: Signal,
        ml_signal: Signal,
        mtf_context: MultiTimeframeContext | None = None,
        sr_context: SRContext | None = None,
    ) -> str:
        now = datetime.now(tz=timezone.utc)
        session_name, session_quality, session_advice = _get_session(now.hour)
        current_price = candles.candles[-1].close if candles.candles else 0.0

        sections = []

        # Section 1 — Multi-timeframe
        if mtf_context:
            sections.append(self._format_mtf(mtf_context))

        # Section 2 — S/R levels
        if sr_context:
            sections.append(self._format_sr(sr_context, current_price))

        # Section 3 — Recent candles
        sections.append(self._format_candles(candles))

        # Section 4 — Technical signals
        sections.append(self._format_ta(ta_signal))

        # Section 5 — ML signal
        sections.append(self._format_ml(ml_signal))

        # Section 6 — Session
        sections.append(
            f"## Session & Timing\n"
            f"UTC Hour: {now.hour:02d}:00 | Session: {session_name} "
            f"(liquidity={session_quality})\n"
            f"Advice: {session_advice}"
        )

        # Section 7 — Decision framework
        bias = mtf_context.dominant_bias if mtf_context else Direction.HOLD
        sections.append(self._format_decision(sr_context, bias, current_price))

        return "\n\n".join(sections)

    def _format_mtf(self, ctx: MultiTimeframeContext) -> str:
        def tf_line(a) -> str:
            arrow = {"BUY": "↑", "SELL": "↓", "HOLD": "→"}.get(a.trend.value, "→")
            return (
                f"  {a.timeframe.value:4s}: {arrow} {a.trend.value:4s}  "
                f"strength={a.trend_strength:.2f}  "
                f"EMA20={a.ema_fast:.5f}  EMA50={a.ema_slow:.5f}"
            )

        alignment_pct = int(ctx.trend_alignment * 100)
        return (
            f"## Multi-Timeframe Structure\n"
            f"{tf_line(ctx.d1)}  (D1 — macro trend)\n"
            f"{tf_line(ctx.h4)}  (H4 — swing structure)\n"
            f"{tf_line(ctx.h1)}  (H1 — entry momentum)\n"
            f"Alignment: {alignment_pct}%  |  Dominant bias: {ctx.dominant_bias.value}\n"
            f"{'⚠ Timeframes DISAGREE — higher bar for entry.' if alignment_pct < 67 else '✓ Timeframes aligned — bias is clear.'}"
        )

    def _format_sr(self, sr: SRContext, current_price: float) -> str:
        lines = [f"## Key Support/Resistance Levels\nCurrent price: {current_price:.5f}"]

        resistances = sorted(
            [lv for lv in sr.levels if lv.price > current_price], key=lambda x: x.price
        )
        supports = sorted(
            [lv for lv in sr.levels if lv.price <= current_price],
            key=lambda x: x.price,
            reverse=True,
        )

        if resistances:
            lines.append("RESISTANCE:")
            for i, lv in enumerate(resistances[:3], 1):
                pips = (lv.price - current_price) * 10000
                lines.append(
                    f"  R{i}: {lv.price:.5f}  strength={lv.strength:.2f}  "
                    f"touches={lv.touch_count}  ({pips:.1f} pips away)"
                )

        if supports:
            lines.append("SUPPORT:")
            for i, lv in enumerate(supports[:3], 1):
                pips = (current_price - lv.price) * 10000
                lines.append(
                    f"  S{i}: {lv.price:.5f}  strength={lv.strength:.2f}  "
                    f"touches={lv.touch_count}  ({pips:.1f} pips away)"
                )

        at_level = []
        if sr.at_support:
            at_level.append("AT SUPPORT")
        if sr.at_resistance:
            at_level.append("AT RESISTANCE")
        status = " + ".join(at_level) if at_level else "between levels"
        lines.append(f"Price is: {status}  |  R:R viable (>=2:1): {'YES' if sr.rr_viable else 'NO'}")

        return "\n".join(lines)

    def _format_candles(self, candles: CandleSeries) -> str:
        recent = candles.candles[-5:] if candles.candles else []
        rows = "\n".join(
            f"  [{c.time.strftime('%Y-%m-%d %H:%M')}] "
            f"O={c.open:.5f} H={c.high:.5f} L={c.low:.5f} C={c.close:.5f} V={c.volume:.0f}"
            for c in recent
        )
        return f"## Recent Candles ({candles.instrument_symbol} {candles.timeframe.value})\n{rows}"

    def _format_ta(self, ta_signal: Signal) -> str:
        ctx = ta_signal.context
        lines = [
            f"## Technical Analysis Signal (H1)",
            f"Direction: {ta_signal.direction.value}  |  Confidence: {ta_signal.confidence:.2f}",
            f"RSI(14): {ctx.get('rsi', 'n/a')}",
            f"EMA20={ctx.get('ema_fast', 'n/a')}  EMA50={ctx.get('ema_slow', 'n/a')}",
            f"MACD={ctx.get('macd', 'n/a')}  Signal={ctx.get('macd_signal', 'n/a')}",
            f"BB Upper={ctx.get('bb_upper', 'n/a')}  BB Lower={ctx.get('bb_lower', 'n/a')}",
        ]
        return "\n".join(lines)

    def _format_ml(self, ml_signal: Signal) -> str:
        ctx = ml_signal.context
        return (
            f"## ML Signal (XGBoost)\n"
            f"Direction: {ml_signal.direction.value}  |  Confidence: {ml_signal.confidence:.2f}\n"
            f"Probabilities: SELL={ctx.get('proba_sell', 0):.2f}  "
            f"HOLD={ctx.get('proba_hold', 0):.2f}  "
            f"BUY={ctx.get('proba_buy', 0):.2f}"
        )

    def _format_decision(
        self, sr: SRContext | None, bias: Direction, current_price: float
    ) -> str:
        rr_note = ""
        if sr and sr.nearest_support and sr.nearest_resistance:
            risk_pips = (current_price - sr.nearest_support.price) * 10000
            reward_pips = (sr.nearest_resistance.price - current_price) * 10000
            rr_note = (
                f"\nR:R Analysis: risk={risk_pips:.1f}pips to S1  "
                f"reward={reward_pips:.1f}pips to R1  "
                f"ratio={reward_pips/risk_pips:.2f}:1"
                if risk_pips > 0 else ""
            )

        bias_warning = (
            f"\n⚠ Dominant bias is {bias.value}. "
            "Trades against this bias require confluence score >= 4/5."
            if bias != Direction.HOLD else ""
        )

        return (
            f"## Your Decision as a Professional FX Trader{bias_warning}{rr_note}\n\n"
            f"DECISION FRAMEWORK (follow this order):\n"
            f"1. BIAS: Does the trade align with D1 macro trend ({bias.value})?\n"
            f"2. LEVEL: Is price at or very near a key S/R level? "
            f"{'YES — valid setup location.' if (sr and (sr.at_support or sr.at_resistance)) else 'NO — price is mid-range. Prefer HOLD.'}\n"
            f"3. R:R: Is minimum 2:1 risk/reward achievable? "
            f"{'YES.' if (sr and sr.rr_viable) else 'NO — insufficient R:R. Strong preference for HOLD.'}\n"
            f"4. CONFLUENCE: Count factors that agree (D1 bias, H4 structure, H1 momentum, price at level, session quality).\n"
            f"   Minimum 3/5 required. If < 3: HOLD.\n"
            f"5. CONVICTION: A confident HOLD beats a forced trade.\n\n"
            f"Respond ONLY with valid JSON (no markdown):\n"
            f'{{\n'
            f'  "direction": "BUY" | "SELL" | "HOLD",\n'
            f'  "confidence": <float 0.0-1.0>,\n'
            f'  "reasoning": "<2-3 sentences: setup quality, key risks, why>",\n'
            f'  "stop_loss_note": "<structural level to use as stop>",\n'
            f'  "invalidation": "<what would invalidate this setup>"\n'
            f'}}'
        )
