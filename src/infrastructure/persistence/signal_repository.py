from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities import AggregatedSignal, Direction, Signal, SignalSource
from domain.ports import ISignalRepository
from domain.value_objects import Timeframe

from .models import SignalModel


def _to_domain(m: SignalModel) -> AggregatedSignal:
    return AggregatedSignal(
        id=m.id,
        instrument_symbol=m.instrument,
        timeframe=Timeframe(m.timeframe),
        direction=Direction(m.direction),
        confidence=m.confidence,
        source=SignalSource(m.source),
        context={
            "ta": m.ta_context or {},
            "ml": m.ml_context or {},
        },
        reasoning=m.reasoning or "",
        override_reason=m.override_reason or "",
        created_at=m.created_at,
    )


def _to_model(s: AggregatedSignal) -> SignalModel:
    ta_ctx = {}
    ml_ctx = {}
    components_data = []

    for c in s.component_signals:
        if c.source == SignalSource.TA:
            ta_ctx = c.context
        elif c.source == SignalSource.ML:
            ml_ctx = c.context
        components_data.append(
            {
                "source": c.source.value,
                "direction": c.direction.value,
                "confidence": c.confidence,
            }
        )

    return SignalModel(
        id=s.id,
        instrument=s.instrument_symbol,
        timeframe=s.timeframe.value,
        direction=s.direction.value,
        confidence=s.confidence,
        source=s.source.value,
        ta_context=ta_ctx,
        ml_context=ml_ctx,
        reasoning=s.reasoning,
        component_signals=components_data,
        override_reason=s.override_reason,
        created_at=s.created_at,
    )


class SignalRepository(ISignalRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, signal: AggregatedSignal) -> AggregatedSignal:
        model = _to_model(signal)
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _to_domain(model)

    async def get_by_id(self, signal_id: UUID) -> AggregatedSignal | None:
        result = await self._session.execute(
            select(SignalModel).where(SignalModel.id == signal_id)
        )
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None
