from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from ..value_objects import Timeframe


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalSource(str, Enum):
    TA = "TA"
    ML = "ML"
    CLAUDE = "CLAUDE"
    AGGREGATED = "AGGREGATED"


@dataclass
class Signal:
    instrument_symbol: str
    timeframe: Timeframe
    direction: Direction
    confidence: float          # 0.0 – 1.0
    source: SignalSource
    context: dict = field(default_factory=dict)
    reasoning: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0,1], got {self.confidence}")


@dataclass
class AggregatedSignal(Signal):
    component_signals: list[Signal] = field(default_factory=list)
    override_reason: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.source = SignalSource.AGGREGATED
