"""GET /signals — recent signal history."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/")
async def list_signals(limit: int = 10) -> dict:
    """Return the most recent N signals.

    Full implementation requires a SignalRepository connected to PostgreSQL.
    """
    return {"signals": [], "limit": limit, "note": "Connect SignalRepository for live data"}
