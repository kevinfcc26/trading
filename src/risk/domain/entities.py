"""Risk domain entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class RiskPolicy:
    """Configuration for risk rules applied to a symbol or globally."""
    max_open_positions: int = 3
    risk_per_trade: float = 0.01          # fraction of balance
    max_daily_drawdown: float = 0.05      # 5% daily loss kills trading
    max_portfolio_exposure: float = 0.06  # max total exposure
    rr_ratio: float = 2.0
    atr_multiplier: float = 1.5
    id: UUID = field(default_factory=uuid4)


@dataclass
class RiskAssessment:
    """Result of running the RiskPipeline on a signal."""
    approved: bool
    volume: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""
    signal_id: UUID | None = None
    evaluated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DrawdownRecord:
    """Daily PnL snapshot for drawdown tracking."""
    date: datetime
    start_balance: float
    current_balance: float
    id: UUID = field(default_factory=uuid4)

    @property
    def drawdown_pct(self) -> float:
        if self.start_balance == 0:
            return 0.0
        return (self.start_balance - self.current_balance) / self.start_balance
