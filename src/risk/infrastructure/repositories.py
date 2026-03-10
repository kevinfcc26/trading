"""Risk infrastructure — in-memory repositories (PostgreSQL persistence is a TODO)."""
from __future__ import annotations

from datetime import date, datetime

from risk.domain.entities import DrawdownRecord, RiskPolicy


class InMemoryRiskPolicyRepository:
    """Holds a single global RiskPolicy in memory.

    TODO: persist to PostgreSQL so policy changes survive restarts.
    """

    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self._policy = policy or RiskPolicy()

    def get(self) -> RiskPolicy:
        return self._policy

    def update(self, policy: RiskPolicy) -> None:
        self._policy = policy


class InMemoryDrawdownTracker:
    """Tracks daily drawdown in memory.

    Resets automatically at midnight. Replace with PostgreSQL for production.
    """

    def __init__(self) -> None:
        self._records: dict[date, DrawdownRecord] = {}
        self._current_date: date = datetime.utcnow().date()

    def record(self, balance: float, start_balance: float | None = None) -> DrawdownRecord:
        today = datetime.utcnow().date()

        if today != self._current_date or today not in self._records:
            self._current_date = today
            self._records[today] = DrawdownRecord(
                date=datetime.utcnow(),
                start_balance=start_balance or balance,
                current_balance=balance,
            )
        else:
            record = self._records[today]
            record.current_balance = balance

        return self._records[today]

    def get_today(self) -> DrawdownRecord | None:
        today = datetime.utcnow().date()
        return self._records.get(today)

    def daily_drawdown_pct(self) -> float:
        record = self.get_today()
        if record is None:
            return 0.0
        return record.drawdown_pct
