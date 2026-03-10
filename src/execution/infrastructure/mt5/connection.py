"""MT5ConnectionManager — lifecycle management for the MT5 terminal."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MT5ConnectionManager:
    def __init__(self, login: int, password: str, server: str) -> None:
        self._login = login
        self._password = password
        self._server = server
        self._connected = False

    async def connect(self) -> None:
        import MetaTrader5 as mt5  # type: ignore[import]

        if not mt5.initialize():
            raise ConnectionError(f"MT5 initialize() failed: {mt5.last_error()}")
        if not mt5.login(self._login, password=self._password, server=self._server):
            raise ConnectionError(f"MT5 login failed: {mt5.last_error()}")

        self._connected = True
        info = mt5.terminal_info()
        logger.info("MT5 connected: %s", info.name if info else "unknown")

    async def disconnect(self) -> None:
        import MetaTrader5 as mt5  # type: ignore[import]

        mt5.shutdown()
        self._connected = False
        logger.info("MT5 disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected
