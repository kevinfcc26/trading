"""Market domain value objects."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from shared_kernel.value_object import ValueObject


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @property
    def minutes(self) -> int:
        mapping = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}
        return mapping[self.value]


@dataclass(frozen=True)
class Price(ValueObject):
    value: float

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"Price cannot be negative: {self.value}")

    def __float__(self) -> float:
        return self.value


@dataclass(frozen=True)
class Spread(ValueObject):
    """Bid-ask spread in price units."""
    value: float

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"Spread cannot be negative: {self.value}")


@dataclass(frozen=True)
class Volatility(ValueObject):
    """ATR-based volatility measure."""
    atr: float
    period: int = 14
