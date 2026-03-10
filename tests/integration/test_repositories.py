"""
Integration tests — require a real PostgreSQL instance.
Run with: docker compose up db -d && pytest tests/integration/
"""
import os
import pytest
import pytest_asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from domain.entities import AggregatedSignal, Direction, Signal, SignalSource, Trade
from domain.value_objects import Timeframe
from infrastructure.persistence.models import Base
from infrastructure.persistence.signal_repository import SignalRepository
from infrastructure.persistence.trade_repository import TradeRepository

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://brocker:brocker@localhost:5432/brocker",
)

pytestmark = pytest.mark.skipif(
    not os.getenv("INTEGRATION_TESTS"),
    reason="Set INTEGRATION_TESTS=1 to run integration tests",
)


@pytest_asyncio.fixture(scope="module")
async def engine():
    e = create_async_engine(DATABASE_URL, echo=False)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await e.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_save_and_retrieve_signal(session):
    repo = SignalRepository(session)
    signal = AggregatedSignal(
        instrument_symbol="EURUSD",
        timeframe=Timeframe.H1,
        direction=Direction.BUY,
        confidence=0.72,
        source=SignalSource.AGGREGATED,
        reasoning="RSI oversold, EMA trend up",
        component_signals=[],
    )
    saved = await repo.save(signal)
    assert saved.id == signal.id

    fetched = await repo.get_by_id(signal.id)
    assert fetched is not None
    assert fetched.direction == Direction.BUY
    assert fetched.confidence == pytest.approx(0.72)


@pytest.mark.asyncio
async def test_save_and_retrieve_trade(session):
    repo = TradeRepository(session)
    trade = Trade(
        instrument_symbol="EURUSD",
        side=Direction.BUY,
        volume=0.10,
        entry_price=1.09500,
        stop_loss=1.09300,
        take_profit=1.09900,
        opened_at=datetime.now(timezone.utc),
    )
    saved = await repo.save(trade)
    assert saved.id == trade.id

    fetched = await repo.get_by_id(trade.id)
    assert fetched is not None
    assert fetched.entry_price == pytest.approx(1.09500)


@pytest.mark.asyncio
async def test_get_open_trades(session):
    repo = TradeRepository(session)
    t1 = Trade(
        instrument_symbol="EURUSD",
        side=Direction.BUY,
        volume=0.10,
        entry_price=1.09500,
        opened_at=datetime.now(timezone.utc),
    )
    t2 = Trade(
        instrument_symbol="GBPUSD",
        side=Direction.SELL,
        volume=0.05,
        entry_price=1.25000,
        opened_at=datetime.now(timezone.utc),
    )
    await repo.save(t1)
    await repo.save(t2)

    open_trades = await repo.get_open_trades()
    symbols = {t.instrument_symbol for t in open_trades}
    assert "EURUSD" in symbols
    assert "GBPUSD" in symbols
