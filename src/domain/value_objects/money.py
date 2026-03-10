from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    @classmethod
    def of(cls, amount: float | str | Decimal, currency: str = "USD") -> "Money":
        return cls(amount=Decimal(str(amount)), currency=currency)

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Cannot subtract different currencies")
        return Money(self.amount - other.amount, self.currency)

    def __float__(self) -> float:
        return float(self.amount)

    def __repr__(self) -> str:
        return f"{self.currency} {self.amount:.2f}"
