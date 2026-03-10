"""
ExecuteOrderUseCase — translates an AggregatedSignal into a broker order.
"""
import logging
from datetime import datetime, timezone

from domain.entities import AggregatedSignal, Direction, Order, OrderType, Trade
from domain.ports import IBroker, IRiskManager, ITradeRepository

logger = logging.getLogger(__name__)


class ExecuteOrderUseCase:
    def __init__(
        self,
        broker: IBroker,
        risk_manager: IRiskManager,
        trade_repository: ITradeRepository,
        dry_run: bool = True,
    ) -> None:
        self._broker = broker
        self._risk = risk_manager
        self._repo = trade_repository
        self._dry_run = dry_run

    async def execute(self, signal: AggregatedSignal) -> Trade | None:
        if signal.direction == Direction.HOLD:
            logger.info("Signal is HOLD — no order placed")
            return None

        # 1. Risk evaluation
        current_price = 0.0
        try:
            from domain.ports import IDataProvider  # avoid circular at module level
        except ImportError:
            pass

        balance = await self._broker.get_account_balance()
        open_positions = await self._broker.get_open_positions(signal.instrument_symbol)
        open_count = len(open_positions)

        risk_decision = await self._risk.evaluate(
            signal,
            current_price=0.0,  # RiskManager will fetch via broker if needed
            account_balance=balance,
            open_positions_count=open_count,
        )

        if not risk_decision.approved:
            logger.info("Risk manager rejected trade: %s", risk_decision.reason)
            return None

        # 2. Build order
        order = Order(
            instrument_symbol=signal.instrument_symbol,
            direction=signal.direction,
            volume=risk_decision.volume,
            order_type=OrderType.MARKET,
            stop_loss=risk_decision.stop_loss,
            take_profit=risk_decision.take_profit,
            signal_id=signal.id,
        )

        if self._dry_run:
            logger.info("[DRY RUN] Would submit: %s", order)
            trade = Trade(
                instrument_symbol=signal.instrument_symbol,
                side=signal.direction,
                volume=risk_decision.volume,
                entry_price=0.0,
                stop_loss=risk_decision.stop_loss,
                take_profit=risk_decision.take_profit,
                signal_id=signal.id,
                opened_at=datetime.now(timezone.utc),
                broker_position_id="DRY_RUN",
            )
        else:
            # 3. Submit to broker
            filled_order = await self._broker.submit_order(order)
            trade = Trade(
                instrument_symbol=signal.instrument_symbol,
                side=signal.direction,
                volume=filled_order.volume,
                entry_price=0.0,  # actual fill price fetched from position
                stop_loss=risk_decision.stop_loss,
                take_profit=risk_decision.take_profit,
                signal_id=signal.id,
                broker_position_id=filled_order.broker_order_id or "",
                opened_at=datetime.now(timezone.utc),
            )

        # 4. Persist trade
        saved = await self._repo.save(trade)
        logger.info("Trade persisted: %s", saved.id)
        return saved
