# Architecture Reference

## Bounded Context Map

```
shared_kernel/          ← primitives only — no business logic
  ├── DomainEvent       (frozen dataclass, immutable)
  ├── Entity            (has UUID identity)
  ├── ValueObject       (frozen dataclass, structural equality)
  └── exceptions.py     (DomainException hierarchy)

events/
  ├── trading_events.py ← 12 domain events (all frozen dataclasses)
  └── bus/
      ├── InMemoryEventBus   ← dev/test (single process)
      └── RedisEventBus      ← prod (multi-process, stub only)

market/                 ← Market Data BC
  ├── domain/
  │   ├── entities: Candle, CandleSeries, MarketState
  │   ├── value_objects: Timeframe, Price, OHLCV
  │   └── ports: MarketFeedPort (Protocol)
  └── infrastructure/
      └── mt5_feed.py   ← MT5MarketFeed (lazy MT5 import)

trading/                ← Order/Trade/Position BC
  ├── domain/
  │   ├── entities: Order, Position, Trade, Portfolio
  │   ├── value_objects: Money, Volume, OrderType
  │   ├── services: calculate_pnl()
  │   └── ports: PortfolioRepository (Protocol)
  ├── application/      ← use cases: OpenTradeUseCase, etc.
  └── infrastructure/
      └── sqlalchemy repos

strategy/               ← Signal Generation BC
  ├── domain/
  │   ├── entities: Signal, AggregatedSignal, Direction, SignalSource
  │   ├── ports: StrategyPort (Protocol)
  │   └── services: SignalAggregator (weighted vote + Claude veto)
  ├── application/      ← GenerateSignalUseCase
  └── infrastructure/
      ├── ta_strategy.py      (pandas_ta indicators)
      ├── ml_strategy.py      (XGBoost inference)
      └── claude_strategy.py  (Anthropic SDK)

risk/                   ← Risk Management BC
  ├── domain/
  │   ├── entities: RiskAssessment, RiskPolicy
  │   ├── value_objects: DrawdownLimit, PositionLimit
  │   └── services/
  │       ├── pipeline.py       (chain-of-responsibility)
  │       ├── kill_switch.py    (in-memory flag)
  │       └── position_sizer.py (ATR-based sizing)
  └── application/      ← EvaluateRiskUseCase

execution/              ← Broker BC
  ├── domain/
  │   └── ports.py      ← BrokerPort (Protocol — never ABC)
  └── infrastructure/
      ├── mt5/adapter.py         (live trading)
      ├── paper/adapter.py       (dry-run / backtest)
      └── ibkr/adapter.py        (stub — not implemented)

simulation/             ← Backtest BC
  ├── engine/
  │   ├── backtest_engine.py    (event-driven replay)
  │   └── clock.py              (SimulatedClock)
  ├── market/
  │   └── market_simulator.py
  └── performance/
      ├── metrics.py            (PerformanceMetrics)
      └── report.py             (BacktestReport)

learning/               ← Knowledge + ML BC
  ├── domain/           (KnowledgeItem, ModelVersion, TradingConcept)
  ├── application/      (IngestDocumentUseCase, TrainModelUseCase)
  └── infrastructure/
      ├── document_loader.py    (PDF → text)
      ├── semantic_parser.py    (Claude: text → structured chunks)
      ├── concept_extractor.py  (Claude: chunks → trading concepts)
      ├── knowledge_store.py    (FileKnowledgeStore → knowledge.jsonl)
      ├── model_registry.py     (ModelRegistry → models/)
      ├── feature_engineering.py (FeatureEngineer + FEATURE_NAMES)
      ├── xgboost_trainer.py    (XGBoostTrainer)
      └── rl_environment.py     (TradingEnv — gymnasium.Env)

research/               ← ISOLATED sandbox
  ├── experiments/tracker.py
  ├── indicators/template.py
  └── sandbox/          (free experimentation — no imports from other BCs' infra)

entrypoints/
  ├── cli/
  │   ├── main.py       (Typer commands: trade/backtest/ingest/serve/kill-switch)
  │   └── container.py  (composition root — build_container())
  ├── api/
  │   ├── main.py       (FastAPI app)
  │   └── routes/       (health, trading routes)
  └── workers/
      ├── trading_worker.py
      └── learning_worker.py
```

---

## Dependency Rule (Strictly Enforced)

```
domain  ←  application  ←  infrastructure  ←  entrypoints
```

- `domain/` imports ONLY from `shared_kernel/` and other domain layers.
- `application/` imports domain + `events/`.
- `infrastructure/` imports application + domain + external libs.
- `entrypoints/` imports infrastructure (composition root only).
- **NEVER import infrastructure from domain or application.**

---

## Signal Pipeline (detailed)

```
MarketDataReceived event
  └─ GenerateSignalUseCase
       ├─ TAStrategy.generate(candles)    → Signal(weight=0.25)
       ├─ MLStrategy.generate(candles)    → Signal(weight=0.35)   [optional]
       └─ ClaudeStrategy.generate(candles)→ Signal(weight=0.40)
            └─ SignalAggregator.aggregate(ta, ml, claude)
                 ├─ Weighted score = Σ(direction_score × weight)
                 ├─ Claude VETO: if claude.confidence ≥ 0.70
                 │               AND claude opposes consensus → override
                 └─ If final_confidence < 0.60 → HOLD
  └─ SignalGenerated event
  └─ EvaluateRiskUseCase
       └─ RiskPipeline.evaluate(signal, price, balance, ...)
            ├─ Stage 1: KillSwitch.check()
            ├─ Stage 2: HOLD signal → reject
            ├─ Stage 3: DailyDrawdown ≥ max → engage KillSwitch + reject
            ├─ Stage 4: open_positions ≥ max → reject
            ├─ Stage 5: total_exposure ≥ max → reject
            ├─ Stage 6: current_price ≤ 0 → reject
            └─ Stage 7: PositionSizer(ATR) → volume, SL, TP
  └─ RiskApproved / RiskRejected event
  └─ BrokerPort.submit_order(order)
  └─ OrderFilled event → OpenTradeUseCase → PositionOpened event
```

---

## Event Flow

```
MarketDataReceived
  → SignalGenerated
  → RiskApproved | RiskRejected
  → OrderSubmitted
  → OrderFilled | OrderCancelled | OrderRejected
  → PositionOpened
  → PositionClosed
  → TradeCompleted
  [on daily loss limit] → KillSwitchActivated
```

All events are frozen dataclasses inheriting from `DomainEvent`.
`InMemoryEventBus`: async pub/sub, single process (MVP).
`RedisEventBus`: swap for multi-pod deployments.

---

## Composition Root

`src/entrypoints/cli/container.py` → `build_container(settings, model_path, dry_run)`

This is the **only** place where all bounded contexts are wired together.
All other code receives dependencies via constructor injection (no global state).

---

## Database Schema

Two Alembic migrations:
- `0001_initial_schema.py` — `signals`, `trades`, `positions` tables
- `0002_learning_schema.py` — `knowledge_items`, `model_versions`, `experiments` tables

ORM: SQLAlchemy 2 async (`asyncpg` driver).
Repos implement `Protocol` interfaces — domain never imports SQLAlchemy.
