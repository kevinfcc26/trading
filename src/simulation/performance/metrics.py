"""Performance metrics for backtesting: Sharpe, Sortino, MaxDrawdown, WinRate."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from trading.domain.entities import Trade


@dataclass
class PerformanceMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    avg_trade_duration_hours: float = 0.0
    initial_balance: float = 10_000.0
    final_balance: float = 10_000.0
    return_pct: float = 0.0

    @classmethod
    def from_trades(
        cls,
        trades: list[Trade],
        equity_curve: list[tuple[datetime, float]],
        initial_balance: float = 10_000.0,
    ) -> "PerformanceMetrics":
        closed = [t for t in trades if t.realized_pnl is not None]

        if not closed and not equity_curve:
            return cls(initial_balance=initial_balance, final_balance=initial_balance)

        if not closed:
            # Compute equity curve metrics only
            max_dd = 0.0
            max_dd_pct = 0.0
            if equity_curve:
                peak = equity_curve[0][1]
                for _, eq in equity_curve:
                    if eq > peak:
                        peak = eq
                    dd = peak - eq
                    dd_pct = dd / peak if peak > 0 else 0.0
                    max_dd = max(max_dd, dd)
                    max_dd_pct = max(max_dd_pct, dd_pct)
            final_balance = equity_curve[-1][1] if equity_curve else initial_balance
            return_pct = (final_balance - initial_balance) / initial_balance if initial_balance > 0 else 0.0
            return cls(
                initial_balance=initial_balance,
                final_balance=final_balance,
                return_pct=return_pct,
                max_drawdown=max_dd,
                max_drawdown_pct=max_dd_pct,
            )

        wins = [t for t in closed if (t.net_pnl or 0) > 0]
        losses = [t for t in closed if (t.net_pnl or 0) <= 0]

        total_pnl = sum(t.net_pnl or 0 for t in closed)
        win_amounts = [t.net_pnl or 0 for t in wins]
        loss_amounts = [abs(t.net_pnl or 0) for t in losses]

        gross_profit = sum(w for w in win_amounts)
        gross_loss = sum(l for l in loss_amounts)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Duration
        from datetime import timezone as _tz

        def _to_utc(dt):
            if dt.tzinfo is None:
                return dt.replace(tzinfo=_tz.utc)
            return dt

        durations = []
        for t in closed:
            if t.opened_at and t.closed_at:
                durations.append(
                    (_to_utc(t.closed_at) - _to_utc(t.opened_at)).total_seconds() / 3600
                )

        # Sharpe & Sortino from equity curve returns
        sharpe = 0.0
        sortino = 0.0
        if len(equity_curve) > 1:
            returns = []
            for i in range(1, len(equity_curve)):
                prev = equity_curve[i - 1][1]
                curr = equity_curve[i][1]
                if prev > 0:
                    returns.append((curr - prev) / prev)

            if returns:
                mean_r = sum(returns) / len(returns)
                variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
                std_r = math.sqrt(variance)
                sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0

                downside = [r for r in returns if r < 0]
                if downside:
                    down_var = sum(r ** 2 for r in downside) / len(downside)
                    down_std = math.sqrt(down_var)
                    sortino = (mean_r / down_std * math.sqrt(252)) if down_std > 0 else 0.0

        # Max drawdown from equity curve
        max_dd = 0.0
        max_dd_pct = 0.0
        if equity_curve:
            peak = equity_curve[0][1]
            for _, eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = peak - eq
                dd_pct = dd / peak if peak > 0 else 0.0
                max_dd = max(max_dd, dd)
                max_dd_pct = max(max_dd_pct, dd_pct)

        final_balance = equity_curve[-1][1] if equity_curve else initial_balance
        return_pct = (final_balance - initial_balance) / initial_balance if initial_balance > 0 else 0.0

        return cls(
            total_trades=len(closed),
            winning_trades=len(wins),
            losing_trades=len(losses),
            total_pnl=total_pnl,
            win_rate=len(wins) / len(closed) if closed else 0.0,
            avg_win=sum(win_amounts) / len(wins) if wins else 0.0,
            avg_loss=sum(loss_amounts) / len(losses) if losses else 0.0,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            avg_trade_duration_hours=sum(durations) / len(durations) if durations else 0.0,
            initial_balance=initial_balance,
            final_balance=final_balance,
            return_pct=return_pct,
        )
