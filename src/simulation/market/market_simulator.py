"""MarketSimulator — models realistic fill conditions for backtesting."""
from __future__ import annotations

from dataclasses import dataclass

from trading.domain.entities import Direction


@dataclass
class FillModel:
    """Parameters for the fill simulation."""
    spread_pips: float = 0.0002
    slippage_pips: float = 0.0001
    commission_per_lot: float = 7.0
    contract_size: float = 100_000.0


class MarketSimulator:
    """Applies realistic slippage, spread, and commission to simulated fills."""

    def __init__(self, model: FillModel | None = None) -> None:
        self._model = model or FillModel()

    def fill_price(self, mid_price: float, direction: Direction) -> float:
        """Compute the actual fill price given direction."""
        half_spread = self._model.spread_pips / 2
        slippage = self._model.slippage_pips

        if direction == Direction.BUY:
            return mid_price + half_spread + slippage
        return mid_price - half_spread - slippage

    def commission(self, volume_lots: float) -> float:
        return self._model.commission_per_lot * volume_lots

    def gross_pnl(
        self,
        direction: Direction,
        entry_price: float,
        exit_price: float,
        volume_lots: float,
    ) -> float:
        multiplier = 1.0 if direction == Direction.BUY else -1.0
        return multiplier * (exit_price - entry_price) * volume_lots * self._model.contract_size

    def net_pnl(
        self,
        direction: Direction,
        entry_price: float,
        exit_price: float,
        volume_lots: float,
    ) -> float:
        return self.gross_pnl(direction, entry_price, exit_price, volume_lots) - self.commission(volume_lots)
