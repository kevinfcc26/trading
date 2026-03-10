from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from .signal import Direction


@dataclass
class Position:
    instrument_symbol: str
    side: Direction
    volume: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    signal_id: UUID | None = None
    broker_position_id: str = ""
    opened_at: datetime = field(default_factory=datetime.utcnow)
    is_open: bool = True
    id: UUID = field(default_factory=uuid4)

    def unrealized_pnl(self, current_price: float, contract_size: float = 100_000.0) -> float:
        multiplier = 1.0 if self.side == Direction.BUY else -1.0
        return multiplier * (current_price - self.entry_price) * self.volume * contract_size
