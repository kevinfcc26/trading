"""All domain events for the trading platform.

Events are the primary integration mechanism between bounded contexts.
They are immutable (frozen dataclasses) and carry only serialisable data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from shared_kernel.domain_event import DomainEvent


@dataclass(frozen=True)
class MarketDataReceived(DomainEvent):
    """Fired when a new candle / market data tick is available."""
    symbol: str = ""
    timeframe: str = ""
    close: float = 0.0
    candle_time: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class SignalGenerated(DomainEvent):
    """Fired after the strategy pipeline produces an aggregated signal."""
    signal_id: UUID = field(default_factory=UUID)
    symbol: str = ""
    timeframe: str = ""
    direction: str = ""       # "BUY" | "SELL" | "HOLD"
    confidence: float = 0.0
    source: str = "AGGREGATED"
    reasoning: str = ""
    override_reason: str = ""


@dataclass(frozen=True)
class RiskApproved(DomainEvent):
    """Fired when the risk pipeline approves a signal for execution."""
    signal_id: UUID = field(default_factory=UUID)
    symbol: str = ""
    direction: str = ""
    volume: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    entry_price: float = 0.0


@dataclass(frozen=True)
class RiskRejected(DomainEvent):
    """Fired when the risk pipeline rejects a signal."""
    signal_id: UUID = field(default_factory=UUID)
    symbol: str = ""
    direction: str = ""
    reason: str = ""


@dataclass(frozen=True)
class OrderSubmitted(DomainEvent):
    """Fired when an order is sent to the broker."""
    order_id: UUID = field(default_factory=UUID)
    signal_id: UUID = field(default_factory=UUID)
    symbol: str = ""
    direction: str = ""
    volume: float = 0.0


@dataclass(frozen=True)
class OrderFilled(DomainEvent):
    """Fired when the broker confirms an order is filled."""
    order_id: UUID = field(default_factory=UUID)
    broker_order_id: str = ""
    symbol: str = ""
    direction: str = ""
    volume: float = 0.0
    fill_price: float = 0.0


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """Fired when an order is cancelled."""
    order_id: UUID = field(default_factory=UUID)
    reason: str = ""


@dataclass(frozen=True)
class OrderRejected(DomainEvent):
    """Fired when the broker rejects an order."""
    order_id: UUID = field(default_factory=UUID)
    reason: str = ""


@dataclass(frozen=True)
class PositionOpened(DomainEvent):
    """Fired when a new position is confirmed open."""
    position_id: UUID = field(default_factory=UUID)
    symbol: str = ""
    direction: str = ""
    volume: float = 0.0
    entry_price: float = 0.0


@dataclass(frozen=True)
class PositionClosed(DomainEvent):
    """Fired when a position is closed."""
    position_id: UUID = field(default_factory=UUID)
    symbol: str = ""
    exit_price: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class TradeCompleted(DomainEvent):
    """Fired when a full trade lifecycle (open → close) is complete."""
    trade_id: UUID = field(default_factory=UUID)
    symbol: str = ""
    direction: str = ""
    volume: float = 0.0
    entry_price: float = 0.0
    exit_price: float = 0.0
    realized_pnl: float = 0.0
    commission: float = 0.0
    swap: float = 0.0


@dataclass(frozen=True)
class KillSwitchActivated(DomainEvent):
    """Fired when the kill switch is engaged."""
    reason: str = ""
    drawdown_pct: float = 0.0
