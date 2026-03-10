from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from .signal import Direction


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
    volume: float                  # lots
    order_type: OrderType = OrderType.MARKET
    stop_loss: float | None = None
    take_profit: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    signal_id: UUID | None = None
    broker_order_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: UUID = field(default_factory=uuid4)
