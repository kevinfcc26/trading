from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..entities import AggregatedSignal


@dataclass
class RiskDecision:
    approved: bool
    volume: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""


class IRiskManager(ABC):
    @abstractmethod
    async def evaluate(
        self,
        signal: AggregatedSignal,
        current_price: float,
        account_balance: float,
        open_positions_count: int,
    ) -> RiskDecision: ...
