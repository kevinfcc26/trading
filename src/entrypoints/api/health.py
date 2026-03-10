"""
FastAPI health endpoints for Kubernetes liveness/readiness probes.
GET /healthz  → 200 if app is running
GET /readyz   → 200 if DB + broker connections are healthy
"""
import logging

from fastapi import FastAPI, Response

logger = logging.getLogger(__name__)

app = FastAPI(title="Brocker Health API", docs_url=None, redoc_url=None)

_broker = None
_db_session_factory = None


def configure(broker, session_factory) -> None:
    """Called from composition root to inject dependencies."""
    global _broker, _db_session_factory
    _broker = broker
    _db_session_factory = session_factory


@app.get("/healthz")
async def liveness():
    return {"status": "ok"}


@app.get("/readyz")
async def readiness(response: Response):
    checks = {}

    # DB check
    try:
        if _db_session_factory:
            async with _db_session_factory() as session:
                await session.execute(__import__("sqlalchemy").text("SELECT 1"))
            checks["db"] = "ok"
        else:
            checks["db"] = "not configured"
    except Exception as exc:
        logger.error("DB readiness check failed: %s", exc)
        checks["db"] = f"error: {exc}"
        response.status_code = 503

    # Broker check
    try:
        if _broker:
            connected = await _broker.is_connected()
            checks["broker"] = "ok" if connected else "disconnected"
            if not connected:
                response.status_code = 503
        else:
            checks["broker"] = "not configured"
    except Exception as exc:
        logger.error("Broker readiness check failed: %s", exc)
        checks["broker"] = f"error: {exc}"
        response.status_code = 503

    return {"status": "ok" if response.status_code != 503 else "degraded", "checks": checks}
