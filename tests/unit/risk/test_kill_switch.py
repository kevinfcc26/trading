"""Tests for KillSwitch service."""
import pytest
from shared_kernel.exceptions import KillSwitchActive
from risk.domain.services.kill_switch import KillSwitch


def test_kill_switch_starts_disengaged():
    ks = KillSwitch()
    assert not ks.is_engaged
    assert ks.reason == ""


def test_kill_switch_engage():
    ks = KillSwitch()
    ks.engage("Daily drawdown exceeded")
    assert ks.is_engaged
    assert "Daily drawdown" in ks.reason


def test_kill_switch_check_raises_when_engaged():
    ks = KillSwitch()
    ks.engage("test reason")
    with pytest.raises(KillSwitchActive):
        ks.check()


def test_kill_switch_check_passes_when_disengaged():
    ks = KillSwitch()
    ks.check()  # should not raise


def test_kill_switch_reset():
    ks = KillSwitch()
    ks.engage("test")
    assert ks.is_engaged
    ks.reset()
    assert not ks.is_engaged
    ks.check()  # should not raise after reset


def test_engage_twice_stays_engaged():
    ks = KillSwitch()
    ks.engage("first reason")
    ks.engage("second reason")  # should not overwrite
    assert "first reason" in ks.reason
