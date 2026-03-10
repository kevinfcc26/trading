# Gotchas, Traps & Known Edge Cases

## pandas_ta Column Name Gotcha

**Problem:** `bbands` appends columns with a double `_2.0` suffix — not a single one.

```python
# WRONG — will raise KeyError
df["BBU_20_2.0"]

# CORRECT
df["BBU_20_2.0_2.0"]   # upper band
df["BBL_20_2.0_2.0"]   # lower band
df["BBM_20_2.0_2.0"]   # middle band
```

This is because `pandas_ta` encodes both `length=20` and `std=2.0` in the column name,
resulting in `BBU_{length}_{std}_{std}`.

**Where it matters:** `src/learning/infrastructure/feature_engineering.py` line 65.

---

## FEATURE_NAMES / Model Artifact Sync

**Problem:** If `FEATURE_NAMES` is changed without retraining, `MLStrategy` will produce wrong predictions
(feature vector shape or column order mismatch) — XGBoost may not raise an error, just give garbage output.

**Rule:** Whenever you add/rename/remove a feature:
1. Update `FEATURE_NAMES` in `feature_engineering.py`
2. Run `poetry run python -m brocker ingest ...` or retrain with new data
3. Re-register the artifact in `ModelRegistry`

---

## MT5 ImportError on Linux / CI

**Problem:** Any `import MetaTrader5` at module level will fail in Docker or CI (Linux).

**Rule:** Always use the lazy import pattern inside method bodies. See `patterns.md`.

**Watch out for:** Tests that accidentally import an MT5-dependent module at the top level.
Wrap with `pytest.importorskip("MetaTrader5")` if a test genuinely requires it.

---

## KillSwitch State is In-Memory

**Problem:** `KillSwitch` holds its engaged state in a Python object attribute.
Restarting the process resets it. In multi-pod deployments, only the pod that engaged it
knows about it.

**Mitigation (single process):** Works correctly — the process won't accept new trades.
**Mitigation (multi-pod):** Must persist state to Redis or PostgreSQL before Kubernetes deployment.
This is a known TODO for Phase 13.

---

## SignalAggregator Weights Must Sum to 1.0

```python
# This will raise ValueError at construction time:
SignalAggregator(weight_ta=0.30, weight_ml=0.35, weight_claude=0.40)  # sum = 1.05
```

Validated in `__init__` with a `1e-6` tolerance. Always verify weights sum to exactly 1.0.

---

## asyncio_mode = "auto" in pytest

`pyproject.toml` sets `asyncio_mode = "auto"`, meaning **all** `async def` test functions
are treated as asyncio tests automatically.
You do NOT need `@pytest.mark.asyncio` explicitly — but it is included by convention for clarity.
Do NOT use `asyncio.run()` inside test functions; pytest-asyncio handles the event loop.

---

## Legacy `src/domain/`, `src/application/`, `src/infrastructure/` Directories

These directories still exist for backward compatibility with pre-v2 code.
**Do not** import from them in new bounded context code.
**Do not** add new files there.
3 test files in `tests/unit/domain/` reference these and have pre-existing failures — leave them alone.

---

## PYTHONPATH Must Include `src/`

All bounded context imports use top-level package names (`from market.domain.entities import Candle`).
This only works if `src/` is in `sys.path`.

Configured in:
- `pyproject.toml` → `[tool.pytest.ini_options] pythonpath = ["src"]`
- `Dockerfile` → `ENV PYTHONPATH=/app/src`
- Manual runs: `PYTHONPATH=src poetry run python ...`

---

## PaperBrokerAdapter Initial Balance

When building the container for backtests, `PaperBrokerAdapter(initial_balance=10_000.0)`.
The `BacktestConfig.initial_balance` must match this value for accurate drawdown calculations.
If they diverge, the risk pipeline will compute sizes against a different balance than the paper broker tracks.

---

## Alembic Migration Order Matters

Migrations must run in order: `0001` then `0002`.
`alembic upgrade head` handles this automatically.
Do NOT skip `0001` — `0002` adds foreign-key-dependent tables.

---

## `research/` Import Isolation

If `research/` code accidentally imports from `strategy/infrastructure/` or `learning/infrastructure/`,
it will couple the sandbox to production code — defeating the purpose of isolation.
Enforce this with a Grep check before merging:

```bash
grep -r "from strategy.infrastructure\|from learning.infrastructure\|from execution.infrastructure" src/research/
# Should return no results
```

---

## ClaudeStrategy JSON Parsing

Claude's response is expected to be valid JSON with keys `direction`, `confidence`, `reasoning`.
If the model returns free text (e.g., due to a changed prompt), parsing will fail.
The strategy should catch `json.JSONDecodeError` and return a `HOLD` signal with low confidence
rather than crashing the pipeline.

---

## BacktestEngine Warmup Period

`BacktestConfig.warmup_candles = 50` — the engine skips signal generation for the first 50 bars.
This ensures TA indicators (EMA50, MACD) have enough data to produce valid values.
If you reduce this value, expect `NaN` in TA features and `InsufficientDataError` from strategies.

---

## Candle Boundary — Exactly On The Boundary Returns Next+1

`next_candle_open(H1, datetime(2025,1,7, 2,0,0))` returns `03:00`, not `02:00`.
When the clock lands exactly on a boundary, the current candle just opened —
the system treats that as "nothing to evaluate yet" and waits for the *next* open.
This prevents a zero-second wait that would cause an infinite tight loop.

## Weekend Recap Fires Once Per Window

`LearningWorker._recap_done_for_weekend` is a boolean flag reset when the market reopens.
If you restart the worker mid-weekend, the recap fires again (once per process lifetime per
weekend window). This is intentional — a restart means a fresh process with no memory of
having recapped.

## Docker Compose `brocker` Service vs `backtest` Profile

The default `docker compose up` starts the `brocker` service with `command: ["serve"]` (API mode).
The `backtest` service is behind the `--profile backtest` flag and runs once then exits.
Do not confuse the two — they share the same image but different entry commands.
