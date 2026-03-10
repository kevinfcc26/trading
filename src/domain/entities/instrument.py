from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str          # e.g. "EURUSD"
    digits: int = 5      # decimal places for price
    contract_size: float = 100_000.0
    currency_profit: str = "USD"

    def __str__(self) -> str:
        return self.symbol
