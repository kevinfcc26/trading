# Brocker v2 — AI Context

This file is the source of truth for AI assistants working on this project.

---

## Project Summary

**Brocker** is an institutional-grade Forex quantitative trading platform written in Python.
It uses a hybrid AI signal pipeline (TA + XGBoost + Claude) inside a DDD + Hexagonal +
Event-Driven architecture, with a full backtesting engine, knowledge ingestion pipeline,
and RL training environment.

---

## Architecture Overview

```
Clean/Hexagonal + DDD Bounded Contexts + Event Bus

shared_kernel/         ← primitives (DomainEvent, Entity, ValueObject, exceptions)
events/                ← EventBus (InMemoryEventBus for MVP, Redis stub for prod)
  └── trading_events.py  ← 12 domain events
market/                ← Market Data BC (Candle, CandleSeries, MarketState, MT5Feed)
trading/               ← Order/Position/Trade/Portfolio BC
strategy/              ← Signal generation BC (StrategyPort Protocol, SignalAggregator)
risk/                  ← Risk management BC (RiskPipeline, KillSwitch, PositionSizer)
execution/             ← Broker BC (BrokerPort Protocol, MT5Adapter, PaperBroker, IBKR stub)
simulation/            ← Backtest engine (BacktestEngine, SimulatedClock, PerformanceMetrics)
learning/              ← Knowledge ingestion BC (DocumentLoader → Claude → KnowledgeStore)
research/              ← ISOLATED research sandbox (no infra imports)
entrypoints/           ← CLI (trade/backtest/ingest/serve/kill-switch), API, workers
```

**Dependency rule**: domain ← application ← infrastructure. Never import infra from domain.

---

## New Folder Structure (v2)

```
brocker/
├── pyproject.toml          # Poetry (python>=3.12, package-mode=false)
├── poetry.lock
├── .env / .env.example
├── Dockerfile              # python:3.12-slim, Poetry, no MT5 on Linux
├── docker-compose.yml      # PostgreSQL + Redis + pgAdmin + brocker service
├── alembic/
│   └── versions/
│       ├── 0001_initial_schema.py    # signals, trades, positions
│       └── 0002_learning_schema.py   # knowledge_items, model_versions, experiments
├── docs/
│   ├── ai_context.md
│   └── knowledge/          # watched by LearningWorker for auto-ingestion
├── models/                 # ML artifacts, model registry, knowledge.jsonl
└── src/
    ├── shared_kernel/      # DomainEvent, Entity, ValueObject, exceptions
    ├── events/             # trading_events.py + bus/ (InMemoryBus, RedisBus)
    ├── market/             # domain/{entities,value_objects,ports} + infrastructure/mt5_feed
    ├── trading/            # domain/{entities,value_objects,ports,services} + application + infrastructure
    ├── strategy/           # domain/{entities,ports,services} + application + infrastructure/{ta,ml,claude}_strategy
    ├── risk/               # domain/{entities,value_objects,ports,services/{kill_switch,pipeline,position_sizer}} + application + infrastructure
    ├── execution/          # domain/ports.py (BrokerPort Protocol) + infrastructure/{mt5,paper,ibkr}
    ├── simulation/         # engine/{backtest_engine,clock} + market/market_simulator + performance/{metrics,report}
    ├── learning/           # domain + application + infrastructure/{document_loader,semantic_parser,concept_extractor,knowledge_store,model_registry,rl_environment}
    ├── research/           # ISOLATED: experiments/tracker + indicators/template + sandbox/
    └── entrypoints/
        ├── cli/{main,container}.py    # Typer CLI: trade/backtest/ingest/serve/kill-switch
        ├── api/{health,main,routes/}  # FastAPI
        └── workers/{trading,learning}_worker.py
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Architecture | DDD Bounded Contexts | Clear domain ownership, explicit boundaries |
| Ports | `Protocol` (not ABC) | Structural typing — no inheritance required |
| Event bus | `InMemoryEventBus` → `RedisEventBus` | Async pub/sub, swap for multi-process |
| Risk | Chain-of-responsibility `RiskPipeline` | KillSwitch → DrawdownCheck → MaxPositions → Sizing |
| Backtest | Event-driven `BacktestEngine` | SL/TP simulation, slippage, spread, commission |
| Knowledge | PDF → Claude (SemanticParser) → Claude (ConceptExtractor) → JSONL | Full knowledge pipeline |
| RL | `TradingEnv(gymnasium.Env)` | Discrete(3) action space (SELL/HOLD/BUY) |
| Package manager | Poetry 2.2 | Isolated venv, deterministic locks |
| MT5 | Optional dependency, Windows only | Lazy import inside methods |

---

## Signal Pipeline (unchanged core logic)

```
Candles → TAStrategy (TA=0.25) → MLStrategy (ML=0.35) → ClaudeStrategy (Claude=0.40)
       → SignalAggregator → AggregatedSignal
         Claude VETO: if Claude confidence > 0.70 in opposite direction → overrides
         Min threshold: 0.60
       → RiskPipeline (KillSwitch → DrawdownCheck → MaxPositions → SizeCalc)
       → BrokerPort.submit_order()
```

---

## Event Flow

```
MarketDataReceived
  → GenerateSignalUseCase → SignalGenerated
  → EvaluateRiskUseCase → RiskApproved | RiskRejected
  → MT5Adapter/PaperBroker → OrderFilled
  → OpenTradeUseCase → PositionOpened
  [on close] → TradeCompleted
  [on daily loss] → KillSwitchActivated
```

---

## CLI Commands

```bash
# Isolated Poetry environment
poetry run python -m brocker trade --symbol EURUSD --timeframe H1 --dry-run
poetry run python -m brocker backtest --symbol EURUSD --timeframe H1 --candles 1000
poetry run python -m brocker ingest docs/my_trading_book.pdf
poetry run python -m brocker serve --host 0.0.0.0 --port 8000
poetry run python -m brocker kill-switch --reason "Manual stop"

# Run tests
poetry run pytest tests/unit/risk/ tests/unit/strategy/ tests/unit/simulation/ -v

# Docker
docker compose up db redis -d    # start infra only
alembic upgrade head             # apply migrations
docker compose up                # full stack
```

---

## Environment

- **Python**: 3.12 (required by pandas-ta >=3.12)
- **Package manager**: Poetry 2.2 (`poetry install --with dev`)
- **Docker**: python:3.12-slim + Redis 7 + PostgreSQL 16
- **PYTHONPATH**: `src/` (configured in pyproject.toml pytest + Dockerfile ENV)

---

## Key Files

| File | Purpose |
|---|---|
| `src/shared_kernel/exceptions.py` | All domain exceptions (RiskViolation, KillSwitchActive) |
| `src/events/trading_events.py` | All 12 domain events |
| `src/events/bus/in_memory_bus.py` | Async in-memory pub/sub (MVP) |
| `src/strategy/domain/services.py` | SignalAggregator (migrated + preserved) |
| `src/risk/domain/services/pipeline.py` | RiskPipeline (chain of validators) |
| `src/risk/domain/services/kill_switch.py` | KillSwitch service |
| `src/execution/domain/ports.py` | BrokerPort Protocol |
| `src/simulation/engine/backtest_engine.py` | Core backtest engine |
| `src/learning/infrastructure/semantic_parser.py` | Claude document parser |
| `src/learning/infrastructure/rl_environment.py` | TradingEnv (gymnasium) |
| `src/entrypoints/cli/container.py` | Composition root |
| `alembic/versions/0002_learning_schema.py` | DB migration for learning tables |

---

## Implementation Status (v2)

| Phase | Description | Status |
|---|---|---|
| 1 | Shared Kernel + Event System | ✅ Done |
| 2 | Market bounded context | ✅ Done |
| 3 | Trading bounded context | ✅ Done |
| 4 | Strategy bounded context | ✅ Done |
| 5 | Risk bounded context (pipeline + kill switch) | ✅ Done |
| 6 | Execution bounded context (MT5 + Paper + IBKR stub) | ✅ Done |
| 7 | Simulation engine (backtest + metrics + report) | ✅ Done |
| 8 | Learning bounded context (ingest + RL env + registry) | ✅ Done |
| 9 | Research environment (isolated sandbox) | ✅ Done |
| 10 | Entrypoints + workers + tests + DB migration | ✅ Done |
| 11 | ML model training (XGBoost) | ✅ Done |
| 12 | RL agent training (PyTorch + gymnasium) | 🔲 Pending |
| 13 | Kubernetes manifests | 🔲 Pending |
| 14 | CI/CD pipeline (GitHub Actions) | 🔲 Pending |

---

## Notes for AI Assistants

- **MT5 import**: always lazy (`import MetaTrader5 as mt5` inside methods) — Windows only
- **BrokerPort**: `Protocol` (structural) — never import ABCs from domain
- **Event bus**: `InMemoryEventBus` in dev/test, wire `RedisEventBus` for multi-process prod
- **PYTHONPATH**: must include `src/` for all bounded context imports to resolve
- **KillSwitch**: in-memory for single process; for multi-pod → persist to PostgreSQL/Redis
- **SignalAggregator**: lives in `strategy/domain/services.py` (migrated from legacy `domain/services/`)
- **Legacy code**: `src/domain/`, `src/application/`, `src/infrastructure/` still present for backward compat
- **Poetry**: use `poetry run pytest ...` and `poetry install --with dev`
- **DB migrations**: 0001 (existing) + 0002 (knowledge tables); `alembic upgrade head`
