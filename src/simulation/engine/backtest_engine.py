"""BacktestEngine — event-driven historical replay engine.

Flow per bar:
  1. Advance SimulatedClock to candle.time
  2. Update PaperBrokerAdapter price
  3. Check open positions for SL/TP hits
  4. Publish MarketDataReceived
  5. Run GenerateSignalUseCase on accumulated candles
  6. Run EvaluateRiskUseCase
  7. If approved → submit order to PaperBrokerAdapter
  8. Accumulate trade records for PerformanceAnalyzer
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from events.bus.in_memory_bus import InMemoryEventBus
from events.trading_events import MarketDataReceived
from execution.infrastructure.paper.adapter import PaperBrokerAdapter
from market.domain.entities import Candle, CandleSeries
from market.domain.value_objects import Timeframe
from risk.domain.entities import RiskPolicy
from risk.domain.services.kill_switch import KillSwitch
from risk.domain.services.pipeline import RiskPipeline
from simulation.engine.clock import SimulatedClock
from simulation.performance.metrics import PerformanceMetrics
from simulation.performance.report import BacktestReport
from strategy.domain.entities import Direction
from strategy.domain.services import SignalAggregator
from strategy.infrastructure.ta_strategy import TAStrategy
from trading.domain.entities import Order, OrderType, Position, Trade
from trading.domain.services import calculate_pnl

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    symbol: str
    timeframe: Timeframe
    initial_balance: float = 10_000.0
    spread_pips: float = 0.0002
    commission_per_lot: float = 7.0
    slippage_pips: float = 0.0001
    warmup_candles: int = 50        # minimum candles before first signal
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)


class BacktestEngine:
    """Replays historical candles and runs the full trading pipeline."""

    def __init__(
        self,
        config: BacktestConfig,
        ta_strategy: TAStrategy,
        ml_strategy,           # MLStrategy (optional — may be None)
        claude_strategy,       # ClaudeStrategy (optional — may be None)
        aggregator: SignalAggregator,
    ) -> None:
        self._config = config
        self._ta = ta_strategy
        self._ml = ml_strategy
        self._claude = claude_strategy
        self._aggregator = aggregator
        self._clock = SimulatedClock()
        self._bus = InMemoryEventBus()
        self._broker = PaperBrokerAdapter(
            initial_balance=config.initial_balance,
            spread_pips=config.spread_pips,
            commission_per_lot=config.commission_per_lot,
            slippage_pips=config.slippage_pips,
        )
        self._kill_switch = KillSwitch()
        self._pipeline = RiskPipeline(self._kill_switch, config.risk_policy)
        self._completed_trades: list[Trade] = []
        self._equity_curve: list[tuple[datetime, float]] = []

    async def run(self, candles: CandleSeries) -> BacktestReport:
        """Run the backtest over the given candle series."""
        await self._broker.connect()
        all_candles = candles.candles

        for i, candle in enumerate(all_candles):
            if i < self._config.warmup_candles:
                continue

            # Advance clock and price
            self._clock.advance(candle.time)
            self._broker.set_current_price(candle.close)

            # Check SL/TP on open positions
            await self._check_stops(candle)

            # Build rolling candle series for strategy
            window = CandleSeries(
                instrument_symbol=candles.instrument_symbol,
                timeframe=candles.timeframe,
                candles=all_candles[: i + 1],
            )

            # Publish market data event
            await self._bus.publish(
                MarketDataReceived(
                    symbol=candles.instrument_symbol,
                    timeframe=candles.timeframe.value,
                    close=candle.close,
                    candle_time=candle.time,
                )
            )

            # Generate signal
            ta_signal = await self._ta.generate(window)

            # ML and Claude are optional
            if self._ml is not None:
                try:
                    ml_signal = await self._ml.generate(window)
                except Exception:
                    ml_signal = ta_signal   # fallback
            else:
                ml_signal = ta_signal

            if self._claude is not None:
                try:
                    claude_signal = await self._claude.generate(
                        window, ta_signal=ta_signal, ml_signal=ml_signal
                    )
                except Exception:
                    claude_signal = ta_signal
            else:
                claude_signal = ta_signal

            aggregated = self._aggregator.aggregate(ta_signal, ml_signal, claude_signal)

            # Skip HOLD
            if aggregated.direction == Direction.HOLD:
                self._equity_curve.append((candle.time, self._broker._balance))
                continue

            # Risk evaluation
            open_positions = await self._broker.fetch_positions()
            balance = await self._broker.get_balance()

            assessment = await self._pipeline.evaluate(
                signal=aggregated,
                current_price=candle.close,
                account_balance=balance,
                open_positions_count=len(open_positions),
            )

            if not assessment.approved:
                logger.debug("Risk rejected: %s", assessment.reason)
                self._equity_curve.append((candle.time, self._broker._balance))
                continue

            # Submit order to paper broker
            order = Order(
                instrument_symbol=candles.instrument_symbol,
                direction=aggregated.direction,
                volume=assessment.volume,
                order_type=OrderType.MARKET,
                stop_loss=assessment.stop_loss,
                take_profit=assessment.take_profit,
                signal_id=aggregated.id,
            )
            await self._broker.submit_order(order)

            self._equity_curve.append((candle.time, self._broker._balance))

        # Close remaining open positions at last price
        open_positions = await self._broker.fetch_positions()
        for pos in open_positions:
            await self._broker.close_position(pos)

        return self._build_report(candles)

    async def _check_stops(self, candle: Candle) -> None:
        """Close positions that have hit SL or TP on this candle."""
        open_positions = await self._broker.fetch_positions()
        for pos in open_positions:
            hit_sl = hit_tp = False

            if pos.stop_loss is not None:
                if pos.side == Direction.BUY and candle.low <= pos.stop_loss:
                    hit_sl = True
                elif pos.side == Direction.SELL and candle.high >= pos.stop_loss:
                    hit_sl = True

            if pos.take_profit is not None:
                if pos.side == Direction.BUY and candle.high >= pos.take_profit:
                    hit_tp = True
                elif pos.side == Direction.SELL and candle.low <= pos.take_profit:
                    hit_tp = True

            if hit_sl or hit_tp:
                close_price = (pos.stop_loss if hit_sl else pos.take_profit) or candle.close
                self._broker.set_current_price(close_price)
                await self._broker.close_position(pos)

                pnl = calculate_pnl(pos.side, pos.entry_price, close_price, pos.volume)
                trade = Trade(
                    instrument_symbol=pos.instrument_symbol,
                    side=pos.side,
                    volume=pos.volume,
                    entry_price=pos.entry_price,
                    exit_price=close_price,
                    stop_loss=pos.stop_loss,
                    take_profit=pos.take_profit,
                    realized_pnl=pnl,
                    opened_at=pos.opened_at,
                    closed_at=self._clock.now(),
                )
                self._completed_trades.append(trade)
                logger.debug(
                    "SL/TP hit: %s PnL=%.2f %s",
                    pos.instrument_symbol,
                    pnl,
                    "SL" if hit_sl else "TP",
                )

    def _build_report(self, candles: CandleSeries) -> BacktestReport:
        metrics = PerformanceMetrics.from_trades(
            trades=self._completed_trades,
            equity_curve=self._equity_curve,
            initial_balance=self._config.initial_balance,
        )
        return BacktestReport(
            symbol=self._config.symbol,
            timeframe=self._config.timeframe,
            total_candles=len(candles),
            trades=self._completed_trades,
            metrics=metrics,
            equity_curve=self._equity_curve,
        )
