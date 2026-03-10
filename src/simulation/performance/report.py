"""BacktestReport — structured result of a completed backtest run."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from market.domain.value_objects import Timeframe
from simulation.performance.metrics import PerformanceMetrics
from trading.domain.entities import Trade


@dataclass
class BacktestReport:
    symbol: str
    timeframe: Timeframe
    total_candles: int
    trades: list[Trade] = field(default_factory=list)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)

    def summary(self) -> dict:
        m = self.metrics
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "total_candles": self.total_candles,
            "total_trades": m.total_trades,
            "win_rate": f"{m.win_rate:.1%}",
            "profit_factor": f"{m.profit_factor:.2f}",
            "total_pnl": f"{m.total_pnl:.2f}",
            "max_drawdown": f"{m.max_drawdown_pct:.1%}",
            "sharpe_ratio": f"{m.sharpe_ratio:.2f}",
            "sortino_ratio": f"{m.sortino_ratio:.2f}",
            "return_pct": f"{m.return_pct:.1%}",
            "initial_balance": f"{m.initial_balance:.2f}",
            "final_balance": f"{m.final_balance:.2f}",
        }

    def print_summary(self) -> None:
        print(f"\n=== Backtest Report: {self.symbol} {self.timeframe.value} ===")
        for k, v in self.summary().items():
            print(f"  {k}: {v}")
