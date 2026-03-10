"""GET /portfolio — current open positions."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/")
async def get_portfolio() -> dict:
    """Return current open positions.

    Full implementation requires a PositionRepository or live broker query.
    """
    return {"positions": [], "note": "Connect PositionRepository for live data"}
