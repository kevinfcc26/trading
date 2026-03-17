"""Unit tests for domain entity validation."""
import pytest

from domain.entities import Direction, Signal, SignalSource, Trade
from domain.value_objects import Timeframe, Price, Money
from decimal import Decimal


class TestSignal:
    def test_invalid_confidence_raises(self):
        with pytest.raises(ValueError):
            Signal(
                instrument_symbol="EURUSD",
                timeframe=Timeframe.H1,
                direction=Direction.BUY,
                confidence=1.5,
                source=SignalSource.TA,
            )

    def test_valid_signal_created(self):
        s = Signal(
            instrument_symbol="EURUSD",
            timeframe=Timeframe.H1,
            direction=Direction.BUY,
            confidence=0.75,
            source=SignalSource.TA,
        )
        assert s.direction == Direction.BUY
        assert s.confidence == 0.75


class TestPrice:
    def test_positive_price(self):
        p = Price.of("1.12345")
        assert float(p) == pytest.approx(1.12345)

    def test_zero_price_raises(self):
        with pytest.raises(ValueError):
            Price.of(0)

    def test_negative_price_raises(self):
        with pytest.raises(ValueError):
            Price.of(-1.0)

    def test_pips(self):
        p1 = Price.of("1.10000")
        p2 = Price.of("1.10010")
        # digits=5 → factor=10^5; 0.00010 × 100_000 = 10 pipettes
        assert p1.pips_to(p2) == pytest.approx(Decimal("10.0"), abs=0.01)


class TestMoney:
    def test_add_same_currency(self):
        a = Money.of(100)
        b = Money.of(50)
        assert float(a + b) == 150.0

    def test_add_different_currency_raises(self):
        a = Money.of(100, "USD")
        b = Money.of(50, "EUR")
        with pytest.raises(ValueError):
            _ = a + b


class TestTrade:
    def test_net_pnl_calculation(self):
        t = Trade(
            instrument_symbol="EURUSD",
            side=Direction.BUY,
            volume=0.1,
            entry_price=1.10000,
            realized_pnl=100.0,
            commission=5.0,
            swap=2.0,
        )
        assert t.net_pnl == pytest.approx(93.0)

    def test_net_pnl_none_when_no_realized(self):
        t = Trade(
            instrument_symbol="EURUSD",
            side=Direction.BUY,
            volume=0.1,
            entry_price=1.10000,
        )
        assert t.net_pnl is None
