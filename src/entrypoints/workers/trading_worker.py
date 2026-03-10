"""TradingWorker — event-driven async trading loop.

Architecture:
    MarketDataReceived → GenerateSignalUseCase → SignalGenerated
    SignalGenerated → EvaluateRiskUseCase → RiskApproved | RiskRejected
    RiskApproved → ExecutionUseCase → OrderFilled
    OrderFilled → OpenTradeUseCase → PositionOpened

Scheduling rules:
    1. Candle-open alignment: each iteration fires only at the open of a new bar.
       The worker sleeps exactly until the next candle boundary, then acts on the
       freshly-closed (complete) candle. Mid-candle polling is avoided entirely.
    2. Weekend guard: Forex closes Friday 22:00 UTC and reopens Sunday 22:00 UTC.
       During that window the worker skips all iterations and sleeps until the
       next session open, logging the expected reopen time.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from config.settings import Settings
from events.bus.in_memory_bus import InMemoryEventBus
from events.trading_events import MarketDataReceived
from execution.infrastructure.mt5.adapter import MT5Adapter
from execution.infrastructure.mt5.connection import MT5ConnectionManager
from execution.infrastructure.paper.adapter import PaperBrokerAdapter
from market.domain.market_schedule import (
    is_forex_open,
    next_candle_open,
    seconds_until_market_open,
    seconds_until_next_candle,
)
from market.domain.value_objects import Timeframe
from risk.domain.entities import RiskPolicy
from risk.domain.services.kill_switch import KillSwitch
from risk.domain.services.pipeline import RiskPipeline
from strategy.domain.services import SignalAggregator
from strategy.infrastructure.claude_strategy import ClaudeStrategy
from strategy.infrastructure.ml_strategy import MLStrategy
from strategy.infrastructure.ta_strategy import TAStrategy
from trading.domain.entities import Order, OrderType

logger = logging.getLogger(__name__)

# Maximum time to sleep while waiting for market open (re-check every hour)
_MARKET_CLOSED_POLL_SECONDS = 3600.0


class TradingWorker:
    """Runs the candle-aligned, schedule-aware trading loop."""

    def __init__(
        self,
        settings: Settings,
        symbol: str,
        timeframe: Timeframe,
        dry_run: bool = True,
        model_path: str = "models/model.joblib",
    ) -> None:
        self._settings = settings
        self._symbol = symbol
        self._timeframe = timeframe
        self._dry_run = dry_run
        self._model_path = model_path
        self._shutdown = asyncio.Event()
        self._bus = InMemoryEventBus()

    def _build_components(self):
        s = self._settings

        if self._dry_run:
            broker = PaperBrokerAdapter(initial_balance=10_000.0)
        else:
            conn = MT5ConnectionManager(
                login=s.mt5_login,
                password=s.mt5_password.get_secret_value(),
                server=s.mt5_server,
            )
            broker = MT5Adapter(conn)

        ta = TAStrategy()
        try:
            ml = MLStrategy(self._model_path)
        except Exception:
            logger.warning("ML model not found — using TA-only mode")
            ml = None

        claude = ClaudeStrategy(api_key=s.anthropic_api_key.get_secret_value())

        aggregator = SignalAggregator(
            weight_ta=s.weight_ta,
            weight_ml=s.weight_ml,
            weight_claude=s.weight_claude,
            min_threshold=s.min_signal_threshold,
            claude_veto_threshold=s.claude_veto_threshold,
        )

        policy = RiskPolicy(
            risk_per_trade=s.risk_per_trade,
            max_open_positions=s.max_open_positions,
        )
        ks = KillSwitch()
        pipeline = RiskPipeline(ks, policy)

        return broker, ta, ml, claude, aggregator, pipeline

    async def run(self) -> None:
        broker, ta, ml, claude, aggregator, pipeline = self._build_components()
        await broker.connect()
        logger.info(
            "TradingWorker started: %s %s dry_run=%s",
            self._symbol, self._timeframe.value, self._dry_run,
        )

        try:
            while not self._shutdown.is_set():
                now = datetime.now(timezone.utc)

                # ── Weekend / market-closed guard ──────────────────────────
                if not is_forex_open(now):
                    wait_secs = seconds_until_market_open(now)
                    reopen_at = next_candle_open(self._timeframe, now)  # rough next-bar ref
                    logger.info(
                        "Market closed (weekend). Forex reopens in %.0fh %.0fm — sleeping.",
                        wait_secs // 3600,
                        (wait_secs % 3600) // 60,
                    )
                    sleep_secs = min(wait_secs, _MARKET_CLOSED_POLL_SECONDS)
                    try:
                        await asyncio.wait_for(self._shutdown.wait(), timeout=sleep_secs)
                    except asyncio.TimeoutError:
                        pass
                    continue  # re-check after sleep

                # ── Candle-open alignment ──────────────────────────────────
                # Sleep until the next bar opens, then act on the just-closed candle.
                wait_secs = seconds_until_next_candle(self._timeframe, now)
                next_open = next_candle_open(self._timeframe, now)
                logger.debug(
                    "Waiting %.0fs for next %s candle open at %s",
                    wait_secs, self._timeframe.value,
                    next_open.strftime("%H:%M:%S UTC"),
                )
                try:
                    await asyncio.wait_for(self._shutdown.wait(), timeout=wait_secs)
                    break  # shutdown was set during the wait
                except asyncio.TimeoutError:
                    pass

                if self._shutdown.is_set():
                    break

                # ── Trading iteration ──────────────────────────────────────
                candle_time = next_open.strftime("%Y-%m-%d %H:%M UTC")
                logger.info("New %s candle open — evaluating signal [%s]",
                            self._timeframe.value, candle_time)
                try:
                    await self._iteration(broker, ta, ml, claude, aggregator, pipeline)
                except Exception as exc:
                    logger.error("Trading loop error: %s", exc, exc_info=True)

        finally:
            await broker.disconnect()
            logger.info("TradingWorker stopped")

    async def _iteration(self, broker, ta, ml, claude, aggregator, pipeline) -> None:
        import datetime as _dt

        candles = await broker.get_candles(self._symbol, self._timeframe, count=200)

        await self._bus.publish(
            MarketDataReceived(
                symbol=self._symbol,
                timeframe=self._timeframe.value,
                close=candles.candles[-1].close if candles.candles else 0.0,
                candle_time=candles.candles[-1].time if candles.candles else _dt.datetime.utcnow(),
            )
        )

        ta_signal = await ta.generate(candles)
        ml_signal = await ml.generate(candles) if ml else ta_signal
        claude_signal = await claude.generate(candles, ta_signal=ta_signal, ml_signal=ml_signal)
        aggregated = aggregator.aggregate(ta_signal, ml_signal, claude_signal)

        logger.info(
            "Signal: %s conf=%.2f%s",
            aggregated.direction.value,
            aggregated.confidence,
            f" [VETO: {aggregated.override_reason}]" if aggregated.override_reason else "",
        )

        balance = await broker.get_account_balance()
        positions = await broker.get_open_positions(self._symbol)

        if hasattr(broker, "set_current_price") and candles.candles:
            broker.set_current_price(candles.candles[-1].close)

        current_price = candles.candles[-1].close if candles.candles else 0.0
        assessment = await pipeline.evaluate(
            signal=aggregated,
            current_price=current_price,
            account_balance=balance,
            open_positions_count=len(positions),
        )

        if not assessment.approved:
            logger.info("Risk rejected: %s", assessment.reason)
            return

        order = Order(
            instrument_symbol=self._symbol,
            direction=aggregated.direction,
            volume=assessment.volume,
            order_type=OrderType.MARKET,
            stop_loss=assessment.stop_loss,
            take_profit=assessment.take_profit,
            signal_id=aggregated.id,
        )
        await broker.submit_order(order)
        logger.info("Order submitted: %s vol=%.2f", order.direction.value, order.volume)

    def stop(self) -> None:
        self._shutdown.set()
