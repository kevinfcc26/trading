"""Risk domain value objects."""
from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.value_object import ValueObject


@dataclass(frozen=True)
class Drawdown(ValueObject):
    """Current drawdown as a fraction of peak equity."""
    value: float  # 0.05 = 5% drawdown

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"Drawdown cannot be negative: {self.value}")

    @property
    def as_percentage(self) -> float:
        return self.value * 100


@dataclass(frozen=True)
class RiskAmount(ValueObject):
    """Maximum risk in account currency for a single trade."""
    amount: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"RiskAmount cannot be negative: {self.amount}")
