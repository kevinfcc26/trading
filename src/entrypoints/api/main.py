"""FastAPI application — health checks + API routes."""
from __future__ import annotations

from fastapi import FastAPI

from entrypoints.api.health import app as health_app
from entrypoints.api.routes.portfolio import router as portfolio_router
from entrypoints.api.routes.signals import router as signals_router

app = FastAPI(title="Brocker API", version="2.0.0")

# Mount health endpoints
app.include_router(health_app.router if hasattr(health_app, "router") else health_app.routes[0])

# Mount API routes
app.include_router(signals_router)
app.include_router(portfolio_router)


@app.get("/")
async def root() -> dict:
    return {"name": "Brocker", "version": "2.0.0", "status": "running"}
