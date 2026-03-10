"""Risk application use cases."""
from __future__ import annotations

import logging

from events.bus.event_bus import EventBus
from events.trading_events import KillSwitchActivated, RiskApproved, RiskRejected
from market.domain.ports import MarketDataPort
from risk.domain.entities import RiskAssessment, RiskPolicy
from risk.domain.services.kill_switch import KillSwitch
from risk.domain.services.pipeline import RiskPipeline
from strategy.domain.entities import AggregatedSignal

logger = logging.getLogger(__name__)


class EvaluateRiskUseCase:
    """Run the full RiskPipeline and publish the result as a domain event."""

    def __init__(
        self,
        pipeline: RiskPipeline,
        event_bus: EventBus,
        data_provider: MarketDataPort | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._bus = event_bus
        self._data = data_provider

    async def execute(
        self,
        signal: AggregatedSignal,
        account_balance: float,
        open_positions_count: int,
        current_price: float = 0.0,
        daily_drawdown_pct: float = 0.0,
        total_exposure_pct: float = 0.0,
    ) -> RiskAssessment:
        if current_price <= 0.0 and self._data:
            current_price = await self._data.get_current_price(signal.instrument_symbol)

        assessment = await self._pipeline.evaluate(
            signal=signal,
            current_price=current_price,
            account_balance=account_balance,
            open_positions_count=open_positions_count,
            daily_drawdown_pct=daily_drawdown_pct,
            total_exposure_pct=total_exposure_pct,
        )

        if assessment.approved:
            await self._bus.publish(
                RiskApproved(
                    signal_id=signal.id,
                    symbol=signal.instrument_symbol,
                    direction=signal.direction.value,
                    volume=assessment.volume,
                    stop_loss=assessment.stop_loss or 0.0,
                    take_profit=assessment.take_profit or 0.0,
                    entry_price=current_price,
                )
            )
        else:
            await self._bus.publish(
                RiskRejected(
                    signal_id=signal.id,
                    symbol=signal.instrument_symbol,
                    direction=signal.direction.value,
                    reason=assessment.reason,
                )
            )

        return assessment


class ActivateKillSwitchUseCase:
    """Manually engage the kill switch."""

    def __init__(self, kill_switch: KillSwitch, event_bus: EventBus) -> None:
        self._ks = kill_switch
        self._bus = event_bus

    async def execute(self, reason: str) -> None:
        self._ks.engage(reason)
        await self._bus.publish(KillSwitchActivated(reason=reason))
        logger.critical("Kill switch activated via use case: %s", reason)
