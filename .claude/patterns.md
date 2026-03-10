# Code Patterns & Conventions

## Module-Level Boilerplate

Every module starts with:
```python
"""One-line description — more detail if needed."""
from __future__ import annotations
```

`from __future__ import annotations` is mandatory — enables forward references and
deferred evaluation of type hints throughout the codebase.

---

## DomainEvent Pattern

```python
# src/events/trading_events.py
from dataclasses import dataclass, field
from shared_kernel.domain_event import DomainEvent

@dataclass(frozen=True)
class SomethingHappened(DomainEvent):
    """Fired when something happens."""
    symbol: str = ""
    value: float = 0.0
    # All fields must have defaults (DomainEvent base adds event_id + occurred_at)
    # Only serialisable types: str, float, int, UUID, datetime
    # NO mutable containers (list, dict) — use tuple if needed
```

---

## ValueObject Pattern

```python
from dataclasses import dataclass
from shared_kernel.value_object import ValueObject

@dataclass(frozen=True)
class Price(ValueObject):
    value: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError(f"Price must be positive, got {self.value}")
```

---

## Entity Pattern

```python
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from shared_kernel.entity import Entity

@dataclass
class Order(Entity):  # NOT frozen — entities have mutable state
    id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    # ...
```

---

## Port (Protocol) Pattern

```python
# domain/ports.py
from typing import Protocol

class SomePort(Protocol):
    """Never inherit from this — structural typing only."""

    async def do_something(self, param: SomeType) -> Result: ...
    async def get_state(self) -> StateType: ...
```

Adapter in `infrastructure/` satisfies the protocol without inheriting:
```python
class ConcreteAdapter:  # NO "implements SomePort"
    async def do_something(self, param: SomeType) -> Result:
        ...
    async def get_state(self) -> StateType:
        ...
```

---

## Use Case Pattern

```python
# application/use_cases.py
class GenerateSignalUseCase:
    def __init__(
        self,
        ta_strategy: TAStrategy,
        ml_strategy: MLStrategy | None,
        claude_strategy: ClaudeStrategy,
        aggregator: SignalAggregator,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._ta = ta_strategy
        self._ml = ml_strategy
        self._claude = claude_strategy
        self._aggregator = aggregator
        self._bus = event_bus

    async def execute(self, candles: CandleSeries) -> AggregatedSignal:
        ...
        await self._bus.publish(SignalGenerated(...))
        return signal
```

All dependencies injected via constructor. No global state, no singletons outside container.

---

## MT5 Lazy Import Pattern

```python
# infrastructure/mt5/adapter.py
class MT5Adapter:
    async def connect(self) -> None:
        import MetaTrader5 as mt5  # ← inside method body, every time
        if not mt5.initialize(...):
            raise BrokerConnectionError("MT5 init failed")

    async def submit_order(self, order: Order) -> Order:
        import MetaTrader5 as mt5  # ← repeat in every method that needs it
        ...
```

**Never** `import MetaTrader5` at the module level — it only exists on Windows with MT5 installed.

---

## Risk Pipeline Extension Pattern

To add a new risk check, insert a new stage in `RiskPipeline.evaluate()`:

```python
# Stage N: My new check
if some_condition:
    return RiskAssessment(
        approved=False,
        reason="Clear human-readable reason",
        signal_id=signal.id,
    )
```

Stages short-circuit: first rejection stops the chain. Always return `RiskAssessment`,
never raise inside `evaluate()` (except re-raising `KillSwitchActive` for stage 1).

---

## Strategy (StrategyPort) Pattern

```python
# infrastructure/my_strategy.py
from strategy.domain.entities import Signal, Direction, SignalSource
from market.domain.entities import CandleSeries

class MyStrategy:  # satisfies StrategyPort structurally
    async def generate(self, candles: CandleSeries) -> Signal:
        # Must always return a Signal — never raise for normal conditions
        # Use Direction.HOLD + low confidence for "no signal"
        return Signal(
            instrument_symbol=candles.symbol,
            timeframe=candles.timeframe,
            direction=Direction.HOLD,
            confidence=0.0,
            source=SignalSource.TA,  # or ML / CLAUDE
        )
```

---

## Exception Hierarchy

```
Exception
└── DomainException          (shared_kernel/exceptions.py)
    ├── RiskViolation         — risk pipeline rule broken
    ├── KillSwitchActive      — kill switch engaged
    ├── InsufficientDataError — not enough candles
    ├── BrokerConnectionError — broker unreachable
    └── ModelNotFoundError    — ML artifact missing
```

Always raise the most specific `DomainException` subclass.
Never raise bare `Exception` or `ValueError` from domain code.

---

## Logging Convention

```python
import logging
logger = logging.getLogger(__name__)

# Use structured log calls with % formatting (not f-strings — lazy evaluation)
logger.info("Risk approved: entry=%.5f SL=%.5f TP=%.5f vol=%.2f", entry, sl, tp, vol)
logger.warning("Kill switch engaged: %s", reason)
logger.error("Broker connection failed: %s", exc)
```

For structured production logging, `structlog` is configured project-wide.

---

## Settings / Config Pattern

```python
# config/settings.py
from pydantic_settings import BaseSettings
from pydantic import SecretStr

class Settings(BaseSettings):
    anthropic_api_key: SecretStr
    mt5_login: int = 0
    mt5_password: SecretStr = SecretStr("")
    weight_ta: float = 0.25
    weight_ml: float = 0.35
    weight_claude: float = 0.40
    # ...

    model_config = SettingsConfigDict(env_file=".env")
```

Always access secrets with `.get_secret_value()` — never log them.

---

## async/await Convention

All I/O-bound operations are `async`:
- Broker operations (`BrokerPort` methods)
- Event bus (`publish`, `subscribe`)
- Use cases (`execute`)
- DB repositories

CPU-bound operations (TA indicators, XGBoost inference) are synchronous.
Wrap with `asyncio.to_thread()` only if blocking the event loop becomes a measured problem.

---

## pandas_ta Column Names

```python
# Correct column names after pandas_ta appends:
"RSI_14"            # RSI
"EMA_20"            # EMA(20)
"EMA_50"            # EMA(50)
"MACD_12_26_9"      # MACD line
"MACDs_12_26_9"     # MACD signal line
"MACDh_12_26_9"     # MACD histogram
"BBU_20_2.0_2.0"    # Bollinger upper  ← double _2.0 suffix
"BBL_20_2.0_2.0"    # Bollinger lower  ← double _2.0 suffix
"BBM_20_2.0_2.0"    # Bollinger middle
"ATRr_14"           # ATR (ratio mode)
```

---

## Feature Engineering Convention

`FEATURE_NAMES` in `src/learning/infrastructure/feature_engineering.py` is the **single
source of truth** for the XGBoost feature vector column order.

```python
FEATURE_NAMES: list[str] = [
    "rsi_14", "ema_diff", "macd", "macd_signal", "bb_width", "close", "volume"
]
```

`ml_strategy.py` imports this list directly.
If you add/remove/rename features: update `FEATURE_NAMES` first, then retrain the model.
The model artifact and `FEATURE_NAMES` must always be in sync.

---

## Research Sandbox Rules

`src/research/` is an **isolated** sandbox:
- May import from `shared_kernel/` (domain primitives only)
- May import standard library and third-party packages
- **Must NOT** import from `market/`, `trading/`, `strategy/`, `risk/`,
  `execution/`, `simulation/`, `learning/`, `entrypoints/`, `events/bus/`

This prevents research experiments from accidentally coupling to production infrastructure.
