"""Tests for PaperBrokerAdapter."""
import pytest
from trading.domain.entities import Direction, Order, OrderStatus, OrderType
from execution.infrastructure.paper.adapter import PaperBrokerAdapter


@pytest.mark.asyncio
async def test_paper_broker_connects():
    broker = PaperBrokerAdapter(initial_balance=10_000.0)
    await broker.connect()
    assert await broker.is_connected()


@pytest.mark.asyncio
async def test_paper_broker_submit_order():
    broker = PaperBrokerAdapter(initial_balance=10_000.0)
    await broker.connect()
    broker.set_current_price(1.10000)

    order = Order(
        instrument_symbol="EURUSD",
        direction=Direction.BUY,
        volume=0.01,
        order_type=OrderType.MARKET,
    )
    filled = await broker.submit_order(order)

    assert filled.status == OrderStatus.FILLED
    assert filled.broker_order_id is not None


@pytest.mark.asyncio
async def test_paper_broker_get_positions():
    broker = PaperBrokerAdapter(initial_balance=10_000.0)
    await broker.connect()
    broker.set_current_price(1.10000)

    order = Order(
        instrument_symbol="EURUSD",
        direction=Direction.BUY,
        volume=0.01,
        order_type=OrderType.MARKET,
    )
    await broker.submit_order(order)

    positions = await broker.fetch_positions("EURUSD")
    assert len(positions) == 1
    assert positions[0].is_open


@pytest.mark.asyncio
async def test_paper_broker_close_position_updates_balance():
    broker = PaperBrokerAdapter(initial_balance=10_000.0)
    await broker.connect()
    broker.set_current_price(1.10000)

    order = Order(
        instrument_symbol="EURUSD",
        direction=Direction.BUY,
        volume=0.01,
        order_type=OrderType.MARKET,
    )
    await broker.submit_order(order)

    positions = await broker.fetch_positions()
    assert len(positions) == 1

    # Price moves up — close at profit
    broker.set_current_price(1.11000)
    closed = await broker.close_position(positions[0])

    assert not closed.is_open
    final_balance = await broker.get_balance()
    assert final_balance != 10_000.0  # balance changed after PnL
