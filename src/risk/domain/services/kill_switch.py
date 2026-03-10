"""KillSwitch — stateful service that halts all new trading when triggered."""
from __future__ import annotations

import logging

from shared_kernel.exceptions import KillSwitchActive

logger = logging.getLogger(__name__)


class KillSwitch:
    """Stateful guard that prevents new trades when engaged.

    Can be engaged manually (e.g. via CLI) or automatically by the
    DailyDrawdownCheck validator when the daily loss limit is breached.

    Thread-safe for single-process use. For multi-process setups,
    persist the engaged state to PostgreSQL or Redis.
    """

    def __init__(self) -> None:
        self._engaged: bool = False
        self._reason: str = ""

    @property
    def is_engaged(self) -> bool:
        return self._engaged

    @property
    def reason(self) -> str:
        return self._reason

    def engage(self, reason: str) -> None:
        if not self._engaged:
            self._engaged = True
            self._reason = reason
            logger.critical("KILL SWITCH ENGAGED: %s", reason)

    def reset(self) -> None:
        self._engaged = False
        self._reason = ""
        logger.warning("Kill switch reset — trading resumed")

    def check(self) -> None:
        """Raise KillSwitchActive if the switch is engaged."""
        if self._engaged:
            raise KillSwitchActive(f"Kill switch is active: {self._reason}")
