from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from .signal import Direction


@dataclass
class Trade:
    instrument_symbol: str
    side: Direction
    volume: float
    entry_price: float
    exit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    realized_pnl: float | None = None
    commission: float = 0.0
    swap: float = 0.0
    signal_id: UUID | None = None
    broker_position_id: str = ""
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: UUID = field(default_factory=uuid4)

    @property
    def net_pnl(self) -> float | None:
        if self.realized_pnl is None:
            return None
        return self.realized_pnl - self.commission - self.swap
