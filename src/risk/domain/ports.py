"""Risk domain ports (Protocols)."""
from __future__ import annotations

from typing import Protocol

from strategy.domain.entities import AggregatedSignal

from .entities import RiskAssessment, RiskPolicy


class RiskPort(Protocol):
    """Protocol for risk evaluation components."""

    async def evaluate(
        self,
        signal: AggregatedSignal,
        current_price: float,
        account_balance: float,
        open_positions_count: int,
        policy: RiskPolicy,
    ) -> RiskAssessment: ...
