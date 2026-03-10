from ..entities import Direction, Trade


def calculate_pnl(
    side: Direction,
    entry_price: float,
    exit_price: float,
    volume: float,
    contract_size: float = 100_000.0,
) -> float:
    multiplier = 1.0 if side == Direction.BUY else -1.0
    return multiplier * (exit_price - entry_price) * volume * contract_size


def summarize_trades(trades: list[Trade]) -> dict:
    closed = [t for t in trades if t.realized_pnl is not None]
    wins = [t for t in closed if (t.net_pnl or 0) > 0]
    losses = [t for t in closed if (t.net_pnl or 0) <= 0]
    total_pnl = sum(t.net_pnl or 0 for t in closed)
    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(closed) if closed else 0.0,
        "total_pnl": total_pnl,
        "avg_win": sum(t.net_pnl or 0 for t in wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(t.net_pnl or 0 for t in losses) / len(losses) if losses else 0.0,
    }
