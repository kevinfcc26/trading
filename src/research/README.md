# Research Module — Isolation Rules

This module is **ISOLATED** from production code.

## Allowed imports
- `shared_kernel.*`
- `market.domain.*`
- `strategy.domain.*`
- `trading.domain.*`
- `risk.domain.*`
- Standard library
- Third-party data science libs: numpy, pandas, matplotlib, scikit-learn, scipy

## Prohibited imports
- `infrastructure.*` (no SQLAlchemy, no MT5, no anthropic)
- `execution.*`
- `learning.infrastructure.*`
- `entrypoints.*`
- `events.bus.*` (no live event publishing)

## Purpose
- Prototype new indicators
- Test signal generation logic
- Run statistical analysis on historical data
- Develop and validate new strategies before promoting to `strategy/`

## Notebook usage
Put Jupyter notebooks in `research/sandbox/`. They should NOT be committed
with output (use `nbstripout` or similar).

## Promoting research to production
1. Write unit tests under `tests/unit/strategy/`
2. Implement the strategy in `strategy/infrastructure/`
3. Wire it in `entrypoints/cli/container.py`
