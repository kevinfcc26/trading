# Architecture Decision Records (ADRs)

## ADR-001 — Protocol over ABC for Ports

**Status:** Accepted

**Context:** Need a port abstraction for brokers, market feeds, and repositories.

**Decision:** Use `typing.Protocol` (structural typing) instead of `abc.ABC`.

**Consequences:**
- Adapters satisfy a port without inheriting from it — zero coupling.
- Easier to mock: any object with matching methods satisfies the protocol at runtime.
- Type checkers (mypy, pyright) verify conformance statically.
- Trade-off: no runtime `isinstance(x, BrokerPort)` check — use `Protocol` with `runtime_checkable` if needed.

**Location:** `src/execution/domain/ports.py`, `src/market/domain/ports.py`

---

## ADR-002 — Lazy MT5 Import

**Status:** Accepted

**Context:** `MetaTrader5` is a Windows-only, optional dependency. Importing it at module level
would crash on Linux (Docker) and on any Windows machine without the package installed.

**Decision:** Import `MetaTrader5 as mt5` inside each method body that requires it.

**Consequences:**
- Platform-agnostic module loading.
- Slight overhead of repeated import lookup (mitigated by Python's import cache — no actual re-import).
- All code paths that call MT5 must handle `ImportError` or `ModuleNotFoundError` gracefully.

**Location:** `src/execution/infrastructure/mt5/adapter.py`, `src/market/infrastructure/mt5_feed.py`

---

## ADR-003 — InMemoryEventBus for MVP, RedisEventBus for Prod

**Status:** Accepted

**Context:** Event-driven architecture requires a pub/sub mechanism. Redis adds operational complexity.

**Decision:** Ship `InMemoryEventBus` for dev/test/single-process deployments.
`RedisEventBus` is stubbed and wired when `REDIS_URL` is configured in prod.

**Consequences:**
- Zero infra dependencies for running unit tests.
- Single-process pub/sub is synchronous within the event loop.
- Multi-process (multi-pod Kubernetes) requires switching to `RedisEventBus`.
- `KillSwitch` state is in-memory — for multi-pod, persist it to Redis/PostgreSQL.

**Location:** `src/events/bus/`

---

## ADR-004 — Weighted Signal Aggregation with Claude Veto

**Status:** Accepted

**Context:** Three strategy signals (TA, ML, Claude) must be combined into one actionable signal.

**Decision:** Weighted sum (TA=0.25, ML=0.35, Claude=0.40) with a Claude override veto.
If Claude's confidence ≥ 0.70 and it opposes the consensus → Claude wins unconditionally.
If aggregated confidence < 0.60 → HOLD.

**Rationale:**
- Claude carries the highest weight: it can incorporate reasoning about macro context.
- The veto prevents ML/TA from overriding a high-conviction Claude judgment.
- A 0.60 threshold filters noise and prevents low-confidence trades.

**Weights are configurable** via `.env` (`WEIGHT_TA`, `WEIGHT_ML`, `WEIGHT_CLAUDE`).

**Location:** `src/strategy/domain/services.py` — `SignalAggregator`

---

## ADR-005 — RiskPipeline as Chain-of-Responsibility

**Status:** Accepted

**Context:** Multiple independent risk checks must be evaluated before any trade.

**Decision:** Ordered pipeline stages. Each stage either rejects (returns `RiskAssessment(approved=False)`)
or passes to the next. Final stage computes position size.

**Stage order:**
1. KillSwitch (hardest block — engaged by drawdown or manual trigger)
2. HOLD signal passthrough
3. Daily drawdown limit
4. Max open positions
5. Portfolio exposure limit
6. Price validity
7. Position sizing (ATR-based: SL = ATR × multiplier, TP = SL × R:R ratio)

**Consequences:**
- Easy to add/remove stages without touching other checks.
- Early rejection is cheap — most trades are rejected at stage 1 or 3.
- Adding a new check requires only inserting a new block in `pipeline.py`.

**Location:** `src/risk/domain/services/pipeline.py`

---

## ADR-006 — FEATURE_NAMES as Single Source of Truth

**Status:** Accepted

**Context:** XGBoost model and inference code must use identical feature columns in the same order.
A mismatch causes silent wrong predictions.

**Decision:** `FEATURE_NAMES: list[str]` defined once in `feature_engineering.py`.
Both `FeatureEngineer.build_feature_matrix()` and `MLStrategy` import this list directly.

**Consequences:**
- Changing features requires: (1) update `FEATURE_NAMES`, (2) retrain model, (3) redeploy artifact.
- Model artifact and `FEATURE_NAMES` version must always match — track via `ModelRegistry`.

**Location:** `src/learning/infrastructure/feature_engineering.py`

---

## ADR-007 — Event-Driven BacktestEngine

**Status:** Accepted

**Context:** Backtesting must realistically simulate the live trading loop.

**Decision:** `BacktestEngine` replays candles using the same `GenerateSignalUseCase` and
`EvaluateRiskUseCase` as live trading, driven by a `SimulatedClock`.
`PaperBrokerAdapter` handles SL/TP simulation, slippage, spread, and commission.

**Consequences:**
- Backtest logic and live logic share the same code path — less drift.
- Backtests are slower than vectorized approaches but more realistic.
- No look-ahead bias: each bar only sees candles up to that point.
- `warmup_candles=50` ensures TA indicators are initialized before first signal.

**Location:** `src/simulation/engine/backtest_engine.py`

---

## ADR-008 — Knowledge Ingestion via Claude (Two-Pass)

**Status:** Accepted

**Context:** Trading books and PDFs contain unstructured knowledge that should inform Claude's signals.

**Decision:** Two-pass Claude pipeline:
1. `SemanticParser`: PDF text → structured semantic chunks (context-aware sections)
2. `ConceptExtractor`: chunks → explicit trading concepts (entry/exit rules, indicators, patterns)
Both outputs are stored in `knowledge.jsonl` via `FileKnowledgeStore`.

**Consequences:**
- Knowledge is persisted and re-usable across restarts.
- Claude's `ClaudeStrategy` can optionally load relevant concepts at signal generation time.
- Cost: 2 Claude API calls per document ingestion pass.

**Location:** `src/learning/infrastructure/`

---

## ADR-009 — Composition Root in CLI Container

**Status:** Accepted

**Context:** All bounded contexts need to be wired together exactly once, at startup.

**Decision:** `src/entrypoints/cli/container.py` → `build_container(settings, model_path, dry_run)`
is the **only** place that instantiates and connects all services.
All other code receives dependencies via constructor injection.

**Consequences:**
- No global singletons or service locators in domain/application code.
- Easy to swap adapters (e.g., `PaperBrokerAdapter` vs `MT5Adapter`) by changing one line in container.
- Testability: tests build their own minimal containers or mock dependencies directly.

**Location:** `src/entrypoints/cli/container.py`

---

## ADR-011 — Candle-Open Alignment + Weekend Learning Mode

**Status:** Accepted

**Context:** The original `TradingWorker` polled every `loop_interval_seconds` (default 60s),
which could fire mid-candle — acting on an incomplete bar and wasting Claude API calls.
Forex also closes Friday 22:00 UTC → Sunday 22:00 UTC; polling during that window is useless.

**Decision:**

**Candle-open alignment** — `TradingWorker` sleeps until the exact UTC boundary of the
next bar open (`next_candle_open(timeframe, now)`), then executes one iteration on the
freshly-closed complete candle. No mid-candle signal generation.

**Weekend guard** — `TradingWorker` detects `is_forex_open() == False` and skips all
iterations. It sleeps in 1-hour chunks until `seconds_until_market_open()` drops to 0,
logging the expected reopen time.

**Weekend learning mode** — `LearningWorker` activates once per weekend closure:
- Check interval drops from 60 min → 30 min
- `_weekend_recap()` fires once: logs knowledge store count, latest model accuracy
- Phase 12 hook: XGBoost retraining + RL episode evaluation will run here

**New domain utility:** `src/market/domain/market_schedule.py`
- `is_forex_open(dt)` / `is_weekend(dt)` — market state
- `next_candle_open(timeframe, dt)` — next bar boundary
- `seconds_until_next_candle(timeframe, dt)` — wait duration
- `seconds_until_market_open(dt)` — weekend sleep duration

**Consequences:**
- Signal quality improves: always acts on closed, confirmed candles.
- API cost reduced: no duplicate Claude calls mid-candle.
- Transparent logging: operator can see exactly when next candle and next session are.
- LearningWorker uses weekend downtime productively.

**Tests:** 22 unit tests in `tests/unit/market/test_market_schedule.py` — all passing.

---

## ADR-010 — SDD (Spec-Driven Development) Workflow

**Status:** Accepted

**Context:** Large architectural changes need upfront agreement on scope, API signatures, and tests
before implementation begins.

**Decision:** Every phase (feature group) begins with a spec in `docs/specs/phase-NN-title.md`.
Status lifecycle: DRAFT → APPROVED → IMPLEMENTING → DONE.
The spec defines: goal, scope, domain concepts, acceptance criteria (AC), file list, API signatures,
test plan, risks, and a done checklist.

**Consequences:**
- Implementation must match spec signatures exactly; signature changes require spec update first.
- ACs map 1-to-1 to tests — tests reference AC numbers in docstrings.
- `docs/ai_context.md` is updated when a phase reaches DONE.

**Location:** `docs/specs/TEMPLATE.md`
