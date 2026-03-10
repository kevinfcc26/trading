"""Trading domain value objects."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from shared_kernel.value_object import ValueObject


@dataclass(frozen=True)
class Money(ValueObject):
    amount: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", self.currency.upper())

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.amount - other.amount, self.currency)

    def __float__(self) -> float:
        return self.amount


@dataclass(frozen=True)
class Quantity(ValueObject):
    """Position size in lots."""
    lots: float

    def __post_init__(self) -> None:
        if self.lots < 0:
            raise ValueError(f"Quantity cannot be negative: {self.lots}")


@dataclass(frozen=True)
class RiskAmount(ValueObject):
    """Maximum risk in account currency for a single trade."""
    amount: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"RiskAmount cannot be negative: {self.amount}")
