"""Strategy domain ports (Protocols)."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from market.domain.entities import CandleSeries

from .entities import AggregatedSignal, Signal


class StrategyPort(Protocol):
    """Protocol for individual strategy signal generators.

    Concrete implementations: TAStrategy, MLStrategy, ClaudeStrategy.
    Any class that implements generate() structurally satisfies this Protocol.
    """

    async def generate(self, candles: CandleSeries, **kwargs) -> Signal: ...


class SignalRepository(Protocol):
    async def save(self, signal: AggregatedSignal) -> AggregatedSignal: ...
    async def get_by_id(self, signal_id: UUID) -> AggregatedSignal | None: ...
