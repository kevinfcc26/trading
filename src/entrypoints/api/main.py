"""FastAPI application — health checks + API routes."""
from __future__ import annotations

from fastapi import FastAPI, Response
from entrypoints.api.routes.portfolio import router as portfolio_router
from entrypoints.api.routes.signals import router as signals_router

app = FastAPI(title="Brocker API", version="2.0.0")

app.include_router(signals_router)
app.include_router(portfolio_router)


@app.get("/")
async def root() -> dict:
    return {"name": "Brocker", "version": "2.0.0", "status": "running"}


@app.get("/healthz")
async def liveness() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readiness(response: Response) -> dict:
    return {"status": "ok"}
