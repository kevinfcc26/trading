"""
DefaultRiskManager — fixed-fractional sizing with ATR-based SL/TP.
"""
import logging

from domain.entities import AggregatedSignal, Direction
from domain.ports import IDataProvider, IRiskManager, RiskDecision
from domain.services import calculate_position_size, default_stop_loss, default_take_profit

logger = logging.getLogger(__name__)

_DEFAULT_ATR = 0.0020  # fallback if no ATR in context


class DefaultRiskManager(IRiskManager):
    def __init__(
        self,
        risk_per_trade: float = 0.01,
        max_open_positions: int = 3,
        data_provider: IDataProvider | None = None,
        rr_ratio: float = 2.0,
        atr_multiplier: float = 1.5,
    ) -> None:
        self._risk = risk_per_trade
        self._max_positions = max_open_positions
        self._data = data_provider
        self._rr_ratio = rr_ratio
        self._atr_multiplier = atr_multiplier

    async def evaluate(
        self,
        signal: AggregatedSignal,
        current_price: float,
        account_balance: float,
        open_positions_count: int,
    ) -> RiskDecision:
        if open_positions_count >= self._max_positions:
            return RiskDecision(
                approved=False,
                reason=f"Max open positions reached ({self._max_positions})",
            )

        if signal.direction == Direction.HOLD:
            return RiskDecision(approved=False, reason="Signal is HOLD")

        # Get current price if not provided
        if current_price == 0.0 and self._data:
            current_price = await self._data.get_current_price(signal.instrument_symbol)

        if current_price == 0.0:
            return RiskDecision(approved=False, reason="Could not determine current price")

        # Extract ATR from TA context
        atr = _DEFAULT_ATR
        for comp in signal.component_signals:
            if "atr_14" in comp.context:
                atr = float(comp.context["atr_14"])
                break

        sl = default_stop_loss(signal.direction, current_price, atr, self._atr_multiplier)
        tp = default_take_profit(signal.direction, current_price, sl, self._rr_ratio)
        volume = calculate_position_size(account_balance, self._risk, current_price, sl)

        logger.info(
            "Risk: entry=%.5f SL=%.5f TP=%.5f volume=%.2f",
            current_price,
            sl,
            tp,
            volume,
        )

        return RiskDecision(
            approved=True,
            volume=volume,
            stop_loss=sl,
            take_profit=tp,
        )
