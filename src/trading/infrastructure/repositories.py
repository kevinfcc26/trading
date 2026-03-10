"""SQLAlchemy implementations of TradeRepository and PositionRepository."""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading.domain.entities import Direction, Order, Position, Trade

# Re-use existing ORM models from the legacy persistence module
from infrastructure.persistence.models import PositionModel, TradeModel


def _trade_to_model(t: Trade) -> TradeModel:
    return TradeModel(
        id=t.id,
        instrument=t.instrument_symbol,
        side=t.side.value,
        volume=t.volume,
        entry_price=t.entry_price,
        exit_price=t.exit_price,
        stop_loss=t.stop_loss,
        take_profit=t.take_profit,
        realized_pnl=t.realized_pnl,
        commission=t.commission,
        swap=t.swap,
        signal_id=t.signal_id,
        broker_position_id=t.broker_position_id,
        opened_at=t.opened_at,
        closed_at=t.closed_at,
    )


def _model_to_trade(m: TradeModel) -> Trade:
    return Trade(
        id=m.id,
        instrument_symbol=m.instrument,
        side=Direction(m.side),
        volume=m.volume,
        entry_price=m.entry_price,
        exit_price=m.exit_price,
        stop_loss=m.stop_loss,
        take_profit=m.take_profit,
        realized_pnl=m.realized_pnl,
        commission=m.commission,
        swap=m.swap,
        signal_id=m.signal_id,
        broker_position_id=m.broker_position_id or "",
        opened_at=m.opened_at,
        closed_at=m.closed_at,
    )


class SQLTradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, trade: Trade) -> None:
        model = _trade_to_model(trade)
        await self._session.merge(model)
        await self._session.commit()

    async def get_by_id(self, trade_id: UUID) -> Trade | None:
        result = await self._session.execute(
            select(TradeModel).where(TradeModel.id == trade_id)
        )
        m = result.scalar_one_or_none()
        return _model_to_trade(m) if m else None

    async def get_open_trades(self, symbol: str | None = None) -> list[Trade]:
        stmt = select(TradeModel).where(TradeModel.exit_price.is_(None))
        if symbol:
            stmt = stmt.where(TradeModel.instrument == symbol)
        result = await self._session.execute(stmt)
        return [_model_to_trade(m) for m in result.scalars()]


def _position_to_model(p: Position) -> PositionModel:
    return PositionModel(
        id=p.id,
        broker_position_id=p.broker_position_id,
        instrument=p.instrument_symbol,
        side=p.side.value,
        volume=p.volume,
        entry_price=p.entry_price,
        stop_loss=p.stop_loss,
        take_profit=p.take_profit,
        signal_id=p.signal_id,
        opened_at=p.opened_at,
        is_open=p.is_open,
    )


def _model_to_position(m: PositionModel) -> Position:
    return Position(
        id=m.id,
        broker_position_id=m.broker_position_id,
        instrument_symbol=m.instrument,
        side=Direction(m.side),
        volume=m.volume,
        entry_price=m.entry_price,
        stop_loss=m.stop_loss,
        take_profit=m.take_profit,
        signal_id=m.signal_id,
        opened_at=m.opened_at,
        is_open=m.is_open,
    )


class SQLPositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, position: Position) -> None:
        model = _position_to_model(position)
        await self._session.merge(model)
        await self._session.commit()

    async def get_open_positions(self, symbol: str | None = None) -> list[Position]:
        stmt = select(PositionModel).where(PositionModel.is_open.is_(True))
        if symbol:
            stmt = stmt.where(PositionModel.instrument == symbol)
        result = await self._session.execute(stmt)
        return [_model_to_position(m) for m in result.scalars()]

    async def close_position(self, position_id: UUID) -> None:
        result = await self._session.execute(
            select(PositionModel).where(PositionModel.id == position_id)
        )
        m = result.scalar_one_or_none()
        if m:
            m.is_open = False
            await self._session.commit()
