from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Price:
    value: Decimal
    digits: int = 5  # pip precision

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError(f"Price must be positive, got {self.value}")

    @classmethod
    def of(cls, value: float | str | Decimal, digits: int = 5) -> "Price":
        return cls(value=Decimal(str(value)), digits=digits)

    def __add__(self, other: "Price") -> "Price":
        return Price(self.value + other.value, self.digits)

    def __sub__(self, other: "Price") -> "Price":
        return Price(self.value - other.value, self.digits)

    def pips_to(self, other: "Price") -> Decimal:
        factor = Decimal(10) ** self.digits
        return (other.value - self.value) * factor

    def __float__(self) -> float:
        return float(self.value)
