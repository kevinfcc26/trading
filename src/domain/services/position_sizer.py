"""
Fixed-fractional position sizing: risk_per_trade % of balance per trade.
"""

from ..entities import Direction


def calculate_position_size(
    account_balance: float,
    risk_per_trade: float,       # e.g. 0.01 for 1%
    entry_price: float,
    stop_loss_price: float,
    contract_size: float = 100_000.0,
    min_lot: float = 0.01,
    lot_step: float = 0.01,
) -> float:
    """Return position size in lots, rounded to lot_step."""
    risk_amount = account_balance * risk_per_trade
    pip_risk = abs(entry_price - stop_loss_price)

    if pip_risk == 0:
        return min_lot

    raw_lots = risk_amount / (pip_risk * contract_size)
    # Round to lot_step
    lots = max(min_lot, round(raw_lots / lot_step) * lot_step)
    return lots


def default_stop_loss(
    direction: Direction,
    entry_price: float,
    atr: float,
    atr_multiplier: float = 2.0,
) -> float:
    """ATR-based stop loss."""
    offset = atr * atr_multiplier
    if direction == Direction.BUY:
        return entry_price - offset
    return entry_price + offset


def default_take_profit(
    direction: Direction,
    entry_price: float,
    stop_loss: float,
    rr_ratio: float = 2.0,
) -> float:
    """Risk-reward ratio based take profit."""
    risk = abs(entry_price - stop_loss)
    if direction == Direction.BUY:
        return entry_price + risk * rr_ratio
    return entry_price - risk * rr_ratio
