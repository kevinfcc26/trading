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
    timeframe: str = typer.Option(None, help="Timeframe — drives model path and MTF config (default: DEFAULT_TIMEFRAME from .env)"),
    dry_run: bool = typer.Option(False, "--dry-run/--live", help="--dry-run: simulate only | --live: real orders"),
):
    """Run the automated event-driven trading loop."""
    asyncio.run(_trade(symbol, timeframe, dry_run))


@app.command()
def backtest(
    symbol: str = typer.Option("EURUSD", help="Symbol to backtest"),
    timeframe: str = typer.Option(None, help="Timeframe — drives model path and MTF config (default: DEFAULT_TIMEFRAME from .env)"),
    candles: int = typer.Option(1000, help="Number of historical candles"),
    initial_balance: float = typer.Option(None, help="Starting balance (default: INITIAL_BALANCE from .env)"),
    use_ai: bool = typer.Option(False, "--use-ai/--no-ai", help="Enable AI layer (Ollama/Claude) — slower but more realistic"),
):
    """Run a full event-driven backtest. Timeframe auto-selects model and thresholds."""
    asyncio.run(_backtest(symbol, timeframe, candles, initial_balance, use_ai))


@app.command()
def train(
    symbol: str = typer.Option("EURUSD", help="Symbol to fetch training candles for"),
    timeframe: str = typer.Option(None, help="Timeframe — drives model path and label threshold (default: DEFAULT_TIMEFRAME from .env)"),
    candles: int = typer.Option(5000, help="Number of historical candles to train on"),
    val_split: float = typer.Option(0.2, help="Fraction of data to use for validation"),
    horizon: int = typer.Option(5, help="Forward-return horizon (bars) for label generation"),
):
    """Train XGBoost model. Timeframe auto-selects model path and label threshold."""
    asyncio.run(_train(symbol, timeframe, candles, val_split, horizon))


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
    from entrypoints.api.main import app as api_app
    uvicorn.run(api_app, host=host, port=port, log_level="info")


@app.command()
def kill_switch(
    reason: str = typer.Option("Manual kill switch activation", help="Reason for activation"),
):
    """Manually activate the kill switch to halt all trading."""
    asyncio.run(_kill_switch(reason))


# ── Timeframe helpers ──────────────────────────────────────────────────────────

# Auto-configuration by timeframe — single source of truth
_TF_MODEL_PATH: dict[str, str] = {
    "M1":  "models/model_m1.joblib",
    "M5":  "models/model_m5.joblib",
    "M15": "models/model_m15.joblib",
    "H1":  "models/model_h1.joblib",
    "H4":  "models/model_h4.joblib",
    "D1":  "models/model_d1.joblib",
}

_TF_LABEL_THRESHOLD: dict[str, float] = {
    "M1":  0.0003,
    "M5":  0.0005,
    "M15": 0.0008,
    "H1":  0.0015,
    "H4":  0.0030,
    "D1":  0.0060,
}

# ATR multiplier for stop loss — wider on higher TFs to absorb natural noise
_TF_ATR_MULTIPLIER: dict[str, float] = {
    "M1":  1.0,
    "M5":  1.2,
    "M15": 1.5,
    "H1":  2.0,
    "H4":  2.5,
    "D1":  3.0,
}

# Risk:Reward ratio for take profit — higher TFs justify holding longer
_TF_RR_RATIO: dict[str, float] = {
    "M1":  1.2,
    "M5":  1.5,
    "M15": 1.5,
    "H1":  2.0,
    "H4":  2.5,
    "D1":  3.0,
}


def _model_path_for(tf: Timeframe) -> str:
    return _TF_MODEL_PATH.get(tf.value, "models/model.joblib")


def _threshold_for(tf: Timeframe) -> float:
    return _TF_LABEL_THRESHOLD.get(tf.value, 0.0015)


def _atr_multiplier_for(tf: Timeframe) -> float:
    return _TF_ATR_MULTIPLIER.get(tf.value, 2.0)


def _rr_ratio_for(tf: Timeframe) -> float:
    return _TF_RR_RATIO.get(tf.value, 2.0)


# ── Async implementations ──────────────────────────────────────────────────────

async def _trade(symbol_opt, timeframe_str, dry_run):
    settings = get_settings()
    _setup_logging(settings)
    signal_module.signal(signal_module.SIGTERM, _handle_sigterm)

    symbol = symbol_opt or settings.default_symbol
    tf = Timeframe(timeframe_str or settings.default_timeframe)
    model_path = _model_path_for(tf)

    from entrypoints.workers.trading_worker import TradingWorker
    worker = TradingWorker(
        settings, symbol, tf, dry_run=dry_run, model_path=model_path,
        atr_multiplier=_atr_multiplier_for(tf),
        rr_ratio=_rr_ratio_for(tf),
    )
    await worker.run()


async def _backtest(symbol, timeframe_str, candle_count, initial_balance, use_ai=False):
    settings = get_settings()
    _setup_logging(settings)
    tf = Timeframe(timeframe_str or settings.default_timeframe)
    model_path = _model_path_for(tf)

    from entrypoints.cli.container import build_container
    from market.domain.value_objects import Timeframe as TF
    from simulation.engine.backtest_engine import BacktestConfig, BacktestEngine
    from strategy.domain.sr_detector import SRDetector

    typer.echo(f"Running backtest: {symbol} {tf.value} ({candle_count} candles)  model={model_path}")

    container = build_container(settings, model_path, dry_run=False)
    await container.broker.connect()

    try:
        candles = await container.broker.get_candles(symbol, tf, count=candle_count)
        # Pre-fetch higher timeframes for MTF context (no lookahead — sliced per bar)
        d1_candles = await container.broker.get_candles(symbol, TF.D1, count=500)
        h4_candles = await container.broker.get_candles(symbol, TF.H4, count=1000)
        typer.echo(f"  MTF data: D1={len(d1_candles)} bars, H4={len(h4_candles)} bars")
    finally:
        await container.broker.disconnect()

    sr_detector = SRDetector(
        swing_window=settings.sr_swing_window,
        max_levels=settings.sr_max_levels,
        rr_min=settings.sr_min_rr_ratio,
    )

    balance = initial_balance if initial_balance is not None else settings.initial_balance
    typer.echo(f"  Initial balance: ${balance:,.2f}")

    engine = BacktestEngine(
        config=BacktestConfig(
            symbol=symbol,
            timeframe=tf,
            initial_balance=balance,
            atr_multiplier=_atr_multiplier_for(tf),
            rr_ratio=_rr_ratio_for(tf),
        ),
        ta_strategy=container.ta_strategy,
        ml_strategy=container.ml_strategy,
        claude_strategy=container.claude_strategy if use_ai else None,
        aggregator=container.aggregator,
        sr_detector=sr_detector,
    )

    report = await engine.run(candles, d1_candles=d1_candles, h4_candles=h4_candles)
    report.print_summary()


async def _train(symbol, timeframe_str, candle_count, val_split, horizon):
    import joblib
    import numpy as np
    from pathlib import Path as _Path

    settings = get_settings()
    _setup_logging(settings)
    tf = Timeframe(timeframe_str or settings.default_timeframe)
    model_path = _model_path_for(tf)
    threshold = _threshold_for(tf)

    from entrypoints.cli.container import build_container
    from learning.infrastructure.feature_engineering import FeatureEngineer
    from learning.infrastructure.model_registry import ModelRegistry
    from learning.infrastructure.xgboost_trainer import XGBoostTrainer

    typer.echo(f"Fetching {candle_count} {tf.value} candles for {symbol}  threshold={threshold}  model={model_path}")

    container = build_container(settings, dry_run=False)
    await container.broker.connect()
    try:
        series = await container.broker.get_candles(symbol, tf, count=candle_count)
    finally:
        await container.broker.disconnect()

    typer.echo(f"Got {len(series)} candles — building features and labels...")

    df = series.to_dataframe().reset_index()
    engineer = FeatureEngineer()
    X = engineer.build_feature_matrix(df)
    y = engineer.generate_labels(df.loc[X.index], horizon=horizon, threshold=threshold)

    # Align X and y (label generation drops last `horizon` rows)
    common = X.index.intersection(y.index)
    X, y = X.loc[common], y.loc[common]

    # Label distribution diagnostic
    counts = y.value_counts().sort_index()
    total = len(y)
    typer.echo(
        f"  Labels: SELL={counts.get(0,0)} ({counts.get(0,0)/total:.0%})  "
        f"HOLD={counts.get(1,0)} ({counts.get(1,0)/total:.0%})  "
        f"BUY={counts.get(2,0)} ({counts.get(2,0)/total:.0%})  "
        f"total={total}"
    )

    split = int(len(X) * (1 - val_split))
    X_train, X_val = X.iloc[:split].values, X.iloc[split:].values
    y_train, y_val = y.iloc[:split].values, y.iloc[split:].values

    typer.echo(f"Training on {len(X_train)} bars, validating on {len(X_val)} bars...")

    trainer = XGBoostTrainer()
    metrics = trainer.train(X_train, y_train, X_val, y_val)

    typer.echo(
        f"Accuracy={metrics['accuracy']:.4f}  "
        f"LogLoss={metrics['log_loss']:.4f}  "
        f"F1(BUY)={metrics['f1_buy']:.4f}  "
        f"F1(SELL)={metrics['f1_sell']:.4f}"
    )

    # Save to the path MLStrategy expects
    out = _Path(model_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(trainer.model, out)
    typer.echo(f"Model saved: {out}")

    # Also register in ModelRegistry for versioning
    from datetime import datetime
    version_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    registry = ModelRegistry()
    trainer.save(registry, version_str, metrics)
    typer.echo(f"Registered as version {version_str}")


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
