"""TradingWorker — professional multi-timeframe trading loop.

Signal pipeline per candle:
  1. Fetch D1/H4/H1 candles (MultiTimeframeAnalyzer)
  2. Detect S/R levels (SRDetector)
  3. TAStrategy with MTF bias filter
  4. MLStrategy (H1 features)
  5. AI strategy with professional prompt (MTF + S/R context)
  6. SignalAggregator.aggregate_professional() — confluence-based
  7. Persist AggregatedSignal to DB
  8. RiskPipeline with structural S/R stop
  9. Submit order if approved
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
from strategy.domain.sr_detector import SRDetector
from strategy.infrastructure.ai_strategy_factory import build_ai_strategy
from strategy.infrastructure.ml_strategy import MLStrategy
from strategy.infrastructure.multi_timeframe_analyzer import MultiTimeframeAnalyzer
from strategy.infrastructure.ta_strategy import TAStrategy
from trading.domain.entities import Order, OrderType

logger = logging.getLogger(__name__)

_MARKET_CLOSED_POLL_SECONDS = 3600.0


class TradingWorker:
    """Candle-aligned, schedule-aware professional trading loop."""

    def __init__(
        self,
        settings: Settings,
        symbol: str,
        timeframe: Timeframe,
        dry_run: bool = True,
        model_path: str = "models/model.joblib",
        atr_multiplier: float = 2.0,
        rr_ratio: float = 2.0,
    ) -> None:
        self._settings = settings
        self._symbol = symbol
        self._timeframe = timeframe
        self._dry_run = dry_run
        self._model_path = model_path
        self._atr_multiplier = atr_multiplier
        self._rr_ratio = rr_ratio
        self._shutdown = asyncio.Event()
        self._bus = InMemoryEventBus()

    def _build_components(self):
        s = self._settings

        if self._dry_run:
            broker = PaperBrokerAdapter(initial_balance=s.initial_balance)
        else:
            conn = MT5ConnectionManager(
                login=s.mt5_login,
                password=s.mt5_password.get_secret_value(),
                server=s.mt5_server,
            )
            broker = MT5Adapter(conn)

        ta = TAStrategy()

        ml = None
        try:
            ml = MLStrategy(self._model_path)
        except Exception:
            logger.warning("ML model not found — using TA-only mode")

        ai = build_ai_strategy(s)
        mtf_analyzer = MultiTimeframeAnalyzer(broker)
        sr_detector = SRDetector(
            swing_window=s.sr_swing_window,
            max_levels=s.sr_max_levels,
            rr_min=s.sr_min_rr_ratio,
        )

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
            atr_multiplier=self._atr_multiplier,
            rr_ratio=self._rr_ratio,
        )
        ks = KillSwitch()
        pipeline = RiskPipeline(ks, policy)

        return broker, ta, ml, ai, mtf_analyzer, sr_detector, aggregator, pipeline

    async def run(self) -> None:
        broker, ta, ml, ai, mtf_analyzer, sr_detector, aggregator, pipeline = (
            self._build_components()
        )
        await broker.connect()
        logger.info(
            "TradingWorker started: %s %s dry_run=%s  ATR×%.1f  R:R=%.1f",
            self._symbol, self._timeframe.value, self._dry_run,
            self._atr_multiplier, self._rr_ratio,
        )

        try:
            while not self._shutdown.is_set():
                now = datetime.now(timezone.utc)

                if not is_forex_open(now):
                    wait_secs = seconds_until_market_open(now)
                    logger.info(
                        "Market closed. Reopens in %.0fh %.0fm — sleeping.",
                        wait_secs // 3600, (wait_secs % 3600) // 60,
                    )
                    sleep_secs = min(wait_secs, _MARKET_CLOSED_POLL_SECONDS)
                    try:
                        await asyncio.wait_for(self._shutdown.wait(), timeout=sleep_secs)
                    except asyncio.TimeoutError:
                        pass
                    continue

                wait_secs = seconds_until_next_candle(self._timeframe, now)
                next_open = next_candle_open(self._timeframe, now)
                logger.debug(
                    "Waiting %.0fs for next %s candle at %s",
                    wait_secs, self._timeframe.value,
                    next_open.strftime("%H:%M:%S UTC"),
                )
                try:
                    await asyncio.wait_for(self._shutdown.wait(), timeout=wait_secs)
                    break
                except asyncio.TimeoutError:
                    pass

                if self._shutdown.is_set():
                    break

                logger.info(
                    "New %s candle — evaluating [%s]",
                    self._timeframe.value,
                    next_open.strftime("%Y-%m-%d %H:%M UTC"),
                )
                try:
                    await self._iteration(
                        broker, ta, ml, ai, mtf_analyzer, sr_detector, aggregator, pipeline
                    )
                except Exception as exc:
                    logger.error("Trading loop error: %s", exc, exc_info=True)

        finally:
            await self._log_summary(broker)
            await broker.disconnect()
            logger.info("TradingWorker stopped")

    async def _iteration(
        self, broker, ta, ml, ai, mtf_analyzer, sr_detector, aggregator, pipeline
    ) -> None:
        import datetime as _dt

        s = self._settings

        # 1. Fetch entry-TF candles for event publishing + TA/ML
        candles = await broker.get_candles(self._symbol, self._timeframe, count=200)
        current_price = candles.candles[-1].close if candles.candles else 0.0

        await self._bus.publish(
            MarketDataReceived(
                symbol=self._symbol,
                timeframe=self._timeframe.value,
                close=current_price,
                candle_time=candles.candles[-1].time if candles.candles else _dt.datetime.utcnow(),
            )
        )

        # 2. Multi-timeframe analysis
        mtf_context = None
        if s.mtf_enabled:
            try:
                mtf_context = await mtf_analyzer.analyze(self._symbol, self._timeframe)
                logger.info(
                    "MTF: bias=%s alignment=%.0f%% (D1=%s H4=%s)",
                    mtf_context.dominant_bias.value,
                    mtf_context.trend_alignment * 100,
                    mtf_context.d1.trend.value,
                    mtf_context.h4.trend.value,
                )
            except Exception as exc:
                logger.warning("MTF analysis failed: %s", exc)

        # 3. S/R detection (use H4 candles for meaningful swing levels)
        sr_context = None
        try:
            h4_candles = await broker.get_candles(self._symbol, Timeframe.H4, count=200)
            sr_context = sr_detector.detect(h4_candles, current_price)
            logger.info(
                "S/R: sup=%s res=%s at_sup=%s at_res=%s rr_viable=%s",
                f"{sr_context.nearest_support.price:.5f}" if sr_context.nearest_support else "none",
                f"{sr_context.nearest_resistance.price:.5f}" if sr_context.nearest_resistance else "none",
                sr_context.at_support,
                sr_context.at_resistance,
                sr_context.rr_viable,
            )
        except Exception as exc:
            logger.warning("S/R detection failed: %s", exc)

        # 4. TA signal (with MTF bias filter)
        ta_signal = await ta.generate(candles, mtf_context=mtf_context)

        # 5. ML signal
        ml_signal = await ml.generate(candles) if ml else ta_signal

        # 6. AI signal (professional prompt with full context)
        ai_signal = await ai.generate(
            candles,
            ta_signal=ta_signal,
            ml_signal=ml_signal,
            mtf_context=mtf_context,
            sr_context=sr_context,
        )

        logger.info(
            "TA=%s(%.2f) ML=%s(%.2f) AI=%s(%.2f)",
            ta_signal.direction.value, ta_signal.confidence,
            ml_signal.direction.value, ml_signal.confidence,
            ai_signal.direction.value, ai_signal.confidence,
        )

        # 7. Professional confluence-based aggregation
        if s.use_professional_aggregator:
            aggregated = aggregator.aggregate_professional(
                ta_signal, ml_signal, ai_signal,
                mtf_context=mtf_context,
                sr_context=sr_context,
            )
        else:
            aggregated = aggregator.aggregate(ta_signal, ml_signal, ai_signal)

        logger.info(
            "→ %s conf=%.2f%s",
            aggregated.direction.value,
            aggregated.confidence,
            f" [{aggregated.override_reason}]" if aggregated.override_reason else "",
        )

        # 8. Persist signal to DB
        if s.signal_persistence_enabled:
            try:
                from infrastructure.persistence.session import get_session_factory
                from strategy.infrastructure.signal_repository import SQLSignalRepository

                session_factory = get_session_factory()
                async with session_factory() as session:
                    repo = SQLSignalRepository(session)
                    await repo.save(aggregated)
                    logger.debug("Signal persisted: %s", aggregated.id)
            except Exception as exc:
                logger.warning("Signal persistence failed: %s", exc)

        # 9. Risk evaluation
        if hasattr(broker, "set_current_price") and candles.candles:
            broker.set_current_price(current_price)

        balance = await broker.get_account_balance()
        positions = await broker.get_open_positions(self._symbol)

        assessment = await pipeline.evaluate(
            signal=aggregated,
            current_price=current_price,
            account_balance=balance,
            open_positions_count=len(positions),
        )

        if not assessment.approved:
            logger.info("Risk rejected: %s", assessment.reason)
            return

        # 10. Submit order
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
        logger.info(
            "Order submitted: %s vol=%.2f SL=%.5f TP=%.5f",
            order.direction.value, order.volume,
            order.stop_loss or 0, order.take_profit or 0,
        )

        # Persist trade to DB
        await self._persist_trade(order, current_price)

        # Log running balance after each order
        new_balance = await broker.get_account_balance()
        open_pos = await broker.get_open_positions(self._symbol)
        logger.info(
            "Balance: %.2f | Open positions: %d",
            new_balance, len(open_pos),
        )

    async def _persist_trade(self, order: Order, price: float) -> None:
        try:
            from datetime import datetime, timezone
            from infrastructure.persistence.models import TradeModel
            from infrastructure.persistence.session import get_session_factory

            session_factory = get_session_factory()
            async with session_factory() as session:
                trade = TradeModel(
                    instrument=order.instrument_symbol,
                    side=order.direction.value,
                    volume=order.volume,
                    entry_price=price,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    signal_id=order.signal_id,
                    broker_position_id=order.broker_order_id or "",
                    opened_at=datetime.now(timezone.utc),
                )
                session.add(trade)
                await session.commit()
                logger.debug("Trade persisted to DB: %s %s", order.direction.value, order.instrument_symbol)
        except Exception as exc:
            logger.warning("Trade persistence failed: %s", exc)

    async def _log_summary(self, broker) -> None:
        try:
            balance = await broker.get_account_balance()
            positions = await broker.get_open_positions(self._symbol)
            initial = self._settings.initial_balance
            pnl = balance - initial
            pnl_pct = (pnl / initial) * 100
            logger.info(
                "=== SESSION SUMMARY ===  Balance: %.2f  PnL: %+.2f (%+.1f%%)  Open positions: %d",
                balance, pnl, pnl_pct, len(positions),
            )
        except Exception:
            pass

    def stop(self) -> None:
        self._shutdown.set()
