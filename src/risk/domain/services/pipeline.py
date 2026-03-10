"""RiskPipeline — chain-of-responsibility pattern for risk validation.

Pipeline stages (in order):
  1. KillSwitchCheck      — abort if kill switch is engaged
  2. DailyDrawdownCheck   — abort if daily loss limit breached
  3. MaxPositionsCheck    — abort if max open positions reached
  4. PortfolioExposureCheck — abort if total exposure too large
  5. PositionSizeCalculator — compute volume, SL, TP

Any stage may raise RiskViolation to short-circuit the chain.
On success, returns a RiskAssessment with approved=True.
"""
from __future__ import annotations

import logging

from shared_kernel.exceptions import KillSwitchActive, RiskViolation
from strategy.domain.entities import AggregatedSignal, Direction

from ..entities import RiskAssessment, RiskPolicy
from .kill_switch import KillSwitch
from .position_sizer import (
    calculate_position_size,
    default_stop_loss,
    default_take_profit,
)

logger = logging.getLogger(__name__)

_DEFAULT_ATR = 0.0020


class RiskPipeline:
    """Evaluate a signal through the full risk chain."""

    def __init__(
        self,
        kill_switch: KillSwitch,
        policy: RiskPolicy | None = None,
    ) -> None:
        self._ks = kill_switch
        self._policy = policy or RiskPolicy()

    async def evaluate(
        self,
        signal: AggregatedSignal,
        current_price: float,
        account_balance: float,
        open_positions_count: int,
        daily_drawdown_pct: float = 0.0,
        total_exposure_pct: float = 0.0,
        policy: RiskPolicy | None = None,
    ) -> RiskAssessment:
        p = policy or self._policy

        # Stage 1: Kill switch
        try:
            self._ks.check()
        except KillSwitchActive as exc:
            return RiskAssessment(approved=False, reason=str(exc), signal_id=signal.id)

        # Stage 2: HOLD signal — no trade
        if signal.direction == Direction.HOLD:
            return RiskAssessment(
                approved=False,
                reason="Signal direction is HOLD",
                signal_id=signal.id,
            )

        # Stage 3: Daily drawdown
        if daily_drawdown_pct >= p.max_daily_drawdown:
            reason = (
                f"Daily drawdown {daily_drawdown_pct:.1%} exceeds limit {p.max_daily_drawdown:.1%}"
            )
            self._ks.engage(reason)
            return RiskAssessment(approved=False, reason=reason, signal_id=signal.id)

        # Stage 4: Max positions
        if open_positions_count >= p.max_open_positions:
            return RiskAssessment(
                approved=False,
                reason=f"Max open positions reached ({p.max_open_positions})",
                signal_id=signal.id,
            )

        # Stage 5: Portfolio exposure
        if total_exposure_pct >= p.max_portfolio_exposure:
            return RiskAssessment(
                approved=False,
                reason=f"Portfolio exposure {total_exposure_pct:.1%} exceeds limit {p.max_portfolio_exposure:.1%}",
                signal_id=signal.id,
            )

        # Stage 6: Current price validation
        if current_price <= 0.0:
            return RiskAssessment(
                approved=False,
                reason="Invalid current price (≤ 0)",
                signal_id=signal.id,
            )

        # Stage 7: Position sizing
        atr = _DEFAULT_ATR
        for comp in signal.component_signals:
            if "atr_14" in comp.context:
                atr = float(comp.context["atr_14"])
                break

        sl = default_stop_loss(signal.direction, current_price, atr, p.atr_multiplier)
        tp = default_take_profit(signal.direction, current_price, sl, p.rr_ratio)
        volume = calculate_position_size(account_balance, p.risk_per_trade, current_price, sl)

        logger.info(
            "Risk approved: entry=%.5f SL=%.5f TP=%.5f vol=%.2f",
            current_price, sl, tp, volume,
        )

        return RiskAssessment(
            approved=True,
            volume=volume,
            stop_loss=sl,
            take_profit=tp,
            reason="All risk checks passed",
            signal_id=signal.id,
        )
