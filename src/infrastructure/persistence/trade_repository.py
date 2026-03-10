from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities import Direction, Trade
from domain.ports import ITradeRepository

from .models import TradeModel


def _to_domain(m: TradeModel) -> Trade:
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
        created_at=m.created_at,
    )


def _to_model(t: Trade) -> TradeModel:
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


class TradeRepository(ITradeRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, trade: Trade) -> Trade:
        model = _to_model(trade)
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _to_domain(model)

    async def get_by_id(self, trade_id: UUID) -> Trade | None:
        result = await self._session.execute(
            select(TradeModel).where(TradeModel.id == trade_id)
        )
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def get_open_trades(self, symbol: str | None = None) -> list[Trade]:
        stmt = select(TradeModel).where(TradeModel.closed_at.is_(None))
        if symbol:
            stmt = stmt.where(TradeModel.instrument == symbol)
        result = await self._session.execute(stmt)
        return [_to_domain(m) for m in result.scalars().all()]

    async def update(self, trade: Trade) -> Trade:
        model = await self._session.get(TradeModel, trade.id)
        if model is None:
            raise ValueError(f"Trade {trade.id} not found")
        model.exit_price = trade.exit_price
        model.realized_pnl = trade.realized_pnl
        model.commission = trade.commission
        model.swap = trade.swap
        model.closed_at = trade.closed_at
        await self._session.commit()
        await self._session.refresh(model)
        return _to_domain(model)
