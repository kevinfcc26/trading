# Brocker v2 — Claude Code Instructions

> This file is loaded automatically on every session.
> Read `docs/ai_context.md` for the full project context.

---

## Project Summary

**Brocker** is an institutional-grade Forex quant trading platform.
Stack: Python 3.12 · Poetry 2.2 · DDD Bounded Contexts · Hexagonal Architecture · Event-Driven.
AI pipeline: Technical Analysis (0.25) + XGBoost (0.35) + Claude (0.40) with veto.

---

## Non-Negotiable Rules

1. **Never import infrastructure from domain.** Dependency rule: `domain ← application ← infrastructure`.
2. **Never use ABC for ports.** Always use `typing.Protocol` (structural typing).
3. **Never import MetaTrader5 at module level.** Always lazy: `import MetaTrader5 as mt5` inside the method body.
4. **PYTHONPATH must include `src/`.** All bounded context imports are relative to `src/`.
5. **`research/` is an isolated sandbox.** No imports from any other bounded context's infrastructure layer.
6. **Every new phase starts with a spec in `docs/specs/phase-NN-title.md`** (copy `TEMPLATE.md`). Status must progress: DRAFT → APPROVED → IMPLEMENTING → DONE.
7. **Never modify `FEATURE_NAMES` in `src/learning/infrastructure/feature_engineering.py` without also updating `ml_strategy.py`** — it is the single source of truth for feature column order.
8. **`pandas_ta` bbands column names have a double `_2.0` suffix:** `BBU_20_2.0_2.0` / `BBL_20_2.0_2.0`.
9. **Domain events are frozen dataclasses.** Never add mutable fields or methods with side effects.
10. **All new domain exceptions must subclass `DomainException`** from `shared_kernel/exceptions.py`.

---

## Before You Start Any Task

1. Read `docs/ai_context.md` — it is the canonical source of truth.
2. Check `docs/specs/` for any IMPLEMENTING spec related to the task.
3. Run `poetry run pytest tests/unit/ -v` to confirm baseline is green (57 tests).

---

## Running the Project

```bash
# Install
poetry install --with dev          # standard
poetry install --with dev --extras mt5  # Windows + MT5

# Infrastructure
docker compose up db redis -d
alembic upgrade head

# CLI
poetry run python -m brocker trade --symbol EURUSD --timeframe H1 --dry-run
poetry run python -m brocker backtest --symbol EURUSD --timeframe H1 --candles 1000
poetry run python -m brocker ingest docs/knowledge/book.pdf
poetry run python -m brocker serve

# Tests (unit only, no infra required)
poetry run pytest tests/unit/ -v
```

---

## Detailed Reference Files

| File | Contents |
|------|----------|
| `.claude/architecture.md` | Bounded context map, dependency rules, event flow |
| `.claude/patterns.md` | Code patterns, conventions, anti-patterns |
| `.claude/testing.md` | Testing strategy, fixtures, mocking conventions |
| `.claude/decisions.md` | Architecture Decision Records (ADRs) |
| `.claude/gotchas.md` | Known traps, bugs, and edge cases |
| `.claude/workflow.md` | SDD process, phase lifecycle, done checklist |
