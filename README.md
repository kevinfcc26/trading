# Brocker v2

**Institutional-grade Forex quantitative trading platform** built in Python.

Combines a hybrid AI signal pipeline (Technical Analysis + XGBoost + Claude) inside a
DDD + Hexagonal + Event-Driven architecture, with a full backtesting engine, knowledge
ingestion pipeline, and Reinforcement Learning training environment.

---

## Features

- **Hybrid AI signal pipeline** — weighted combination of TA indicators, XGBoost ML, and Claude LLM reasoning with veto capability
- **Domain-Driven Design** — clearly bounded contexts (market, trading, strategy, risk, execution, simulation, learning)
- **Hexagonal architecture** — `Protocol`-based ports; swap adapters without touching domain logic
- **Event-driven core** — `InMemoryEventBus` for dev/test, `RedisEventBus` for multi-process production
- **Full backtesting engine** — SL/TP simulation, slippage, spread, commission, performance metrics
- **Knowledge ingestion** — PDF → Claude semantic parsing → concept extraction → JSONL knowledge store
- **RL environment** — `gymnasium`-compatible `TradingEnv` (SELL/HOLD/BUY action space)
- **Multi-broker support** — MetaTrader 5 (Windows), Paper broker, IBKR stub
- **Risk pipeline** — chain-of-responsibility: KillSwitch → DrawdownCheck → MaxPositions → PositionSizer
- **CLI + REST API** — Typer CLI and FastAPI health/routes entrypoints

---

## Signal Pipeline

```
Candles
  → TAStrategy     (weight 0.25)
  → MLStrategy     (weight 0.35)
  → ClaudeStrategy (weight 0.40)
  → SignalAggregator
       └─ Claude VETO: if Claude confidence > 0.70 in opposite direction → override
       └─ Min aggregated threshold: 0.60
  → RiskPipeline (KillSwitch → DrawdownCheck → MaxPositions → SizeCalc)
  → BrokerPort.submit_order()
```

---

## Architecture

```
shared_kernel/      ← DomainEvent, Entity, ValueObject, exceptions
events/             ← trading_events.py (12 events) + InMemoryBus / RedisBus
market/             ← Candle, CandleSeries, MarketState, MT5MarketFeed
trading/            ← Order, Position, Trade, Portfolio + SQLAlchemy repos
strategy/           ← StrategyPort Protocol, SignalAggregator, TAStrategy, MLStrategy, ClaudeStrategy
risk/               ← RiskPipeline, KillSwitch, PositionSizer
execution/          ← BrokerPort Protocol, MT5Adapter, PaperBrokerAdapter, IBKRAdapter stub
simulation/         ← BacktestEngine, SimulatedClock, MarketSimulator, PerformanceMetrics
learning/           ← DocumentLoader, SemanticParser, ConceptExtractor, KnowledgeStore,
                       ModelRegistry, TradingEnv (RL), FeatureEngineer, XGBoostTrainer
research/           ← ISOLATED sandbox — no infrastructure imports allowed
entrypoints/        ← CLI (Typer), API (FastAPI), workers (TradingWorker, LearningWorker)
```

**Dependency rule**: `domain ← application ← infrastructure`. Domain layers never import infrastructure.

---

## Requirements

| Requirement      | Version       |
|------------------|---------------|
| Python           | 3.12.x        |
| Poetry           | 2.2+          |
| PostgreSQL       | 16 (via Docker) |
| Redis            | 7 (via Docker) |
| MetaTrader 5     | Windows only (optional) |

---

## Quick Start

### 1. Install dependencies

```bash
poetry install --with dev
```

For MetaTrader 5 support (Windows only):

```bash
poetry install --with dev --extras mt5
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY, DB_URL, REDIS_URL, etc.
```

### 3. Start infrastructure

```bash
docker compose up db redis -d
```

### 4. Apply database migrations

```bash
alembic upgrade head
```

### 5. Run the platform

```bash
# Live trading (dry run)
poetry run python -m brocker trade --symbol EURUSD --timeframe H1 --dry-run

# Backtest
poetry run python -m brocker backtest --symbol EURUSD --timeframe H1 --candles 1000

# Ingest a trading book / PDF
poetry run python -m brocker ingest docs/knowledge/my_book.pdf

# Start REST API
poetry run python -m brocker serve --host 0.0.0.0 --port 8000

# Trigger kill switch
poetry run python -m brocker kill-switch --reason "Manual stop"
```

---

## Docker (full stack)

```bash
# Full stack (API + DB + Redis + pgAdmin)
docker compose up

# Run a one-off backtest
docker compose --profile backtest run backtest

# pgAdmin UI
open http://localhost:5050   # admin@brocker.local / admin
```

---

## Running Tests

```bash
# Unit tests only (fast, no infra required)
poetry run pytest tests/unit/ -v

# Risk + strategy + simulation suites
poetry run pytest tests/unit/risk/ tests/unit/strategy/ tests/unit/simulation/ -v

# All tests (requires running DB/Redis for integration)
poetry run pytest -v
```

---

## Project Structure

```
brocker/
├── pyproject.toml              # Poetry config (python 3.12, package-mode=false)
├── docker-compose.yml          # PostgreSQL 16 + Redis 7 + pgAdmin + brocker service
├── Dockerfile                  # python:3.12-slim, Poetry, no MT5 on Linux
├── alembic/
│   └── versions/
│       ├── 0001_initial_schema.py     # signals, trades, positions
│       └── 0002_learning_schema.py    # knowledge_items, model_versions, experiments
├── docs/
│   ├── ai_context.md           # AI assistant context (source of truth)
│   ├── specs/                  # SDD phase specs (TEMPLATE.md + per-phase)
│   └── knowledge/              # Drop PDFs here — LearningWorker auto-ingests
├── models/                     # ML artifacts, XGBoost models, knowledge.jsonl
├── src/
│   ├── shared_kernel/
│   ├── events/
│   ├── market/
│   ├── trading/
│   ├── strategy/
│   ├── risk/
│   ├── execution/
│   ├── simulation/
│   ├── learning/
│   ├── research/
│   └── entrypoints/
│       ├── cli/                # main.py + container.py (composition root)
│       ├── api/                # FastAPI health + routes
│       └── workers/            # TradingWorker, LearningWorker
└── tests/
    ├── unit/                   # Fast, in-process unit tests
    └── integration/            # Tests requiring DB/Redis
```

---

## Implementation Status

| Phase | Description                                    | Status       |
|-------|------------------------------------------------|--------------|
| 1     | Shared Kernel + Event System                   | ✅ Done      |
| 2     | Market bounded context                         | ✅ Done      |
| 3     | Trading bounded context                        | ✅ Done      |
| 4     | Strategy bounded context                       | ✅ Done      |
| 5     | Risk bounded context (pipeline + kill switch)  | ✅ Done      |
| 6     | Execution bounded context (MT5 + Paper + IBKR) | ✅ Done      |
| 7     | Simulation engine (backtest + metrics)         | ✅ Done      |
| 8     | Learning bounded context (ingest + RL + registry) | ✅ Done   |
| 9     | Research environment (isolated sandbox)        | ✅ Done      |
| 10    | Entrypoints + workers + DB migrations          | ✅ Done      |
| 11    | ML model training (XGBoost)                    | ✅ Done      |
| 12    | RL agent training (PyTorch + gymnasium)        | 🔲 Pending   |
| 13    | Kubernetes manifests                           | 🔲 Pending   |
| 14    | CI/CD pipeline (GitHub Actions)                | 🔲 Pending   |

---

## Key Technologies

| Layer           | Technology                               |
|-----------------|------------------------------------------|
| Language        | Python 3.12                              |
| AI / LLM        | Anthropic Claude (`anthropic` SDK)       |
| ML              | XGBoost 2, scikit-learn                  |
| RL Environment  | `gymnasium`                              |
| Technical Analysis | `pandas-ta`                           |
| Database        | PostgreSQL 16 + SQLAlchemy 2 (async)     |
| Migrations      | Alembic                                  |
| Event bus       | In-memory (dev) / Redis 7 (prod)         |
| CLI             | Typer                                    |
| API             | FastAPI + Uvicorn                        |
| Config          | Pydantic Settings                        |
| Logging         | structlog                                |
| Broker          | MetaTrader 5 (Windows), Paper, IBKR stub |
| PDF ingestion   | pypdf                                    |
| Packaging       | Poetry 2.2                               |

---

## Notes

- **MT5 import** is always lazy (`import MetaTrader5 as mt5` inside methods) — Windows only, optional dependency.
- **`PYTHONPATH`** must include `src/` for bounded context imports to resolve. Configured automatically in `pyproject.toml` (pytest) and `Dockerfile`.
- **KillSwitch** is in-memory for single process. For multi-pod deployments, persist state to PostgreSQL or Redis.
- **`BrokerPort`** uses Python `Protocol` (structural typing) — no ABC inheritance needed to satisfy the interface.
- Drop PDF files into `docs/knowledge/` and the `LearningWorker` will auto-ingest them via Claude.
