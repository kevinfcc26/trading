"""CLI entrypoint — Typer app with trade, backtest, ingest, serve commands."""
from __future__ import annotations

import asyncio
import logging
import signal as signal_module
import sys
from pathlib import Path

import typer
import uvicorn

from config.settings import get_settings
from market.domain.value_objects import Timeframe

app = typer.Typer(name="brocker", help="Forex AI Quantitative Trading Platform")
_shutdown_event = asyncio.Event()


def _handle_sigterm(*_) -> None:
    logging.getLogger(__name__).info("SIGTERM received — shutting down gracefully")
    _shutdown_event.set()


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command()
def trade(
    symbol: str = typer.Option(None, help="Trading symbol (e.g. EURUSD)"),
    timeframe: str = typer.Option(None, help="Timeframe (M1/M5/M15/H1/H4/D1)"),
    dry_run: bool = typer.Option(True, help="Simulate orders without executing"),
    model_path: str = typer.Option("models/model.joblib", help="Path to ML model"),
):
    """Run the automated event-driven trading loop."""
    asyncio.run(_trade(symbol, timeframe, dry_run, model_path))


@app.command()
def backtest(
    symbol: str = typer.Option("EURUSD", help="Symbol to backtest"),
    timeframe: str = typer.Option("H1", help="Timeframe"),
    candles: int = typer.Option(1000, help="Number of historical candles"),
    model_path: str = typer.Option("models/model.joblib", help="Path to ML model"),
    initial_balance: float = typer.Option(10_000.0, help="Starting balance"),
):
    """Run a full event-driven backtest with slippage, spread, and SL/TP simulation."""
    asyncio.run(_backtest(symbol, timeframe, candles, model_path, initial_balance))


@app.command()
def ingest(
    file: str = typer.Argument(..., help="Path to PDF/TXT/EPUB document to ingest"),
):
    """Ingest a trading document into the knowledge base."""
    asyncio.run(_ingest(file))


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="API host"),
    port: int = typer.Option(8000, help="API port"),
):
    """Start the health check and API server."""
    from entrypoints.api.health import app as health_app
    uvicorn.run(health_app, host=host, port=port, log_level="info")


@app.command()
def kill_switch(
    reason: str = typer.Option("Manual kill switch activation", help="Reason for activation"),
):
    """Manually activate the kill switch to halt all trading."""
    asyncio.run(_kill_switch(reason))


# ── Async implementations ──────────────────────────────────────────────────────

async def _trade(symbol_opt, timeframe_str, dry_run, model_path):
    settings = get_settings()
    _setup_logging(settings)
    signal_module.signal(signal_module.SIGTERM, _handle_sigterm)

    symbol = symbol_opt or settings.default_symbol
    tf = Timeframe(timeframe_str or settings.default_timeframe)

    from entrypoints.workers.trading_worker import TradingWorker
    worker = TradingWorker(settings, symbol, tf, dry_run=dry_run, model_path=model_path)
    await worker.run()


async def _backtest(symbol, timeframe_str, candle_count, model_path, initial_balance):
    settings = get_settings()
    _setup_logging(settings)
    tf = Timeframe(timeframe_str)

    from entrypoints.cli.container import build_container
    from simulation.engine.backtest_engine import BacktestConfig, BacktestEngine

    typer.echo(f"Running backtest: {symbol} {tf.value} ({candle_count} candles)...")

    container = build_container(settings, model_path, dry_run=False)
    await container.broker.connect()

    try:
        candles = await container.broker.get_candles(symbol, tf, count=candle_count)
    finally:
        await container.broker.disconnect()

    config = BacktestConfig(
        symbol=symbol,
        timeframe=tf,
        initial_balance=initial_balance,
    )

    engine = BacktestEngine(
        config=config,
        ta_strategy=container.ta_strategy,
        ml_strategy=container.ml_strategy,
        claude_strategy=container.claude_strategy,
        aggregator=container.aggregator,
    )

    report = await engine.run(candles)
    report.print_summary()


async def _ingest(file_path: str):
    settings = get_settings()
    _setup_logging(settings)

    from entrypoints.cli.container import build_container
    from learning.application.use_cases import IngestDocumentUseCase

    typer.echo(f"Ingesting: {file_path}")
    container = build_container(settings)

    use_case = IngestDocumentUseCase(
        loader=container.document_loader,
        parser=container.semantic_parser,
        extractor=container.concept_extractor,
        knowledge_base=container.knowledge_store,
    )

    items = await use_case.execute(file_path)
    typer.echo(f"Ingested {len(items)} knowledge items from {Path(file_path).name}")
    for item in items[:5]:
        typer.echo(f"  [{item.knowledge_type.value}] {item.title}")
    if len(items) > 5:
        typer.echo(f"  ... and {len(items) - 5} more")


async def _kill_switch(reason: str):
    settings = get_settings()
    container_module = __import__("entrypoints.cli.container", fromlist=["build_container"])
    container = container_module.build_container(settings)
    container.kill_switch.engage(reason)
    typer.echo(f"Kill switch activated: {reason}")


def _setup_logging(settings) -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
