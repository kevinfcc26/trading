"""Trading domain entities — Order, Position, Trade, Portfolio."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    instrument_symbol: str
    direction: Direction
    volume: float                      # lots
    order_type: OrderType = OrderType.MARKET
    stop_loss: float | None = None
    take_profit: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    signal_id: UUID | None = None
    broker_order_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: UUID = field(default_factory=uuid4)

    def fill(self, broker_order_id: str) -> None:
        self.broker_order_id = broker_order_id
        self.status = OrderStatus.FILLED

    def cancel(self) -> None:
        self.status = OrderStatus.CANCELLED

    def reject(self) -> None:
        self.status = OrderStatus.REJECTED


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

    def close(self) -> None:
        self.is_open = False


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

    @property
    def is_closed(self) -> bool:
        return self.exit_price is not None


@dataclass
class Portfolio:
    """Aggregate view of all open positions and account state."""
    balance: float
    equity: float
    open_positions: list[Position] = field(default_factory=list)
    currency: str = "USD"

    @property
    def open_positions_count(self) -> int:
        return len(self.open_positions)

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(
            p.unrealized_pnl(p.entry_price)  # use entry as placeholder if no current price
            for p in self.open_positions
        )
