# Development Workflow

## SDD (Spec-Driven Development) Process

Every non-trivial change follows this lifecycle:

```
DRAFT → APPROVED → IMPLEMENTING → DONE
```

### Step 1: Create the Spec (DRAFT)

Copy `docs/specs/TEMPLATE.md` to `docs/specs/phase-NN-title.md`.
Fill in all 10 sections:

1. **Goal** — one paragraph, observable outcome
2. **Scope** — in/out of scope
3. **Domain Concepts** — new entities/value objects/services
4. **Acceptance Criteria** — numbered ACs, each maps to one test
5. **Files to Create or Modify** — exact paths, CREATE/MODIFY, notes
6. **API / Signatures** — Python signatures the implementation must match
7. **Test Plan** — test name → AC mapping
8. **Dependencies and Risks** — external deps, migration risks
9. **Implementation Notes** — algorithm choices, gotchas, ordering constraints
10. **Done Checklist** — verify before closing

### Step 2: Review & Approve (APPROVED)

Update status to `APPROVED` before writing any code.
If signatures need to change during implementation, **update the spec first**.

### Step 3: Implement (IMPLEMENTING)

- Follow file list in §5 exactly
- Implement to match signatures in §6 exactly
- Write tests that reference AC numbers in docstrings

### Step 4: Close (DONE)

All items in §10 Done Checklist must pass:

```
- [ ] All files listed in §5 created / modified
- [ ] All ACs verified by passing tests
- [ ] `poetry run pytest tests/unit/` fully green
- [ ] `docs/ai_context.md` updated (phase → ✅ Done)
- [ ] This spec status → DONE
```

---

## Current Phase Status

| Phase | Spec File | Status |
|-------|-----------|--------|
| 1–11 | (no individual spec files, predates SDD) | ✅ Done |
| 11 | `phase-11-xgboost-training.md` | ✅ Done |
| 12 | RL agent training (PyTorch + gymnasium) | 🔲 Pending |
| 13 | Kubernetes manifests | 🔲 Pending |
| 14 | CI/CD (GitHub Actions) | 🔲 Pending |

---

## Adding a New Bounded Context

1. Create `src/newcontext/` with the standard layout:
   ```
   newcontext/
   ├── __init__.py
   ├── domain/
   │   ├── __init__.py
   │   ├── entities.py
   │   ├── value_objects.py
   │   ├── ports.py         ← Protocol-based
   │   └── services.py
   ├── application/
   │   ├── __init__.py
   │   └── use_cases.py
   └── infrastructure/
       ├── __init__.py
       └── adapter.py
   ```
2. Add domain exceptions to `shared_kernel/exceptions.py` if needed.
3. Add new domain events to `events/trading_events.py` if needed.
4. Wire the new context in `entrypoints/cli/container.py`.
5. Add to the architecture map in `docs/ai_context.md` and `.claude/architecture.md`.
6. Write unit tests in `tests/unit/newcontext/`.

---

## Adding a New Domain Event

```python
# src/events/trading_events.py — append at the end
@dataclass(frozen=True)
class MyNewEvent(DomainEvent):
    """Fired when X happens."""
    symbol: str = ""
    value: float = 0.0
```

Rules:
- All fields must have default values (DomainEvent base already provides `event_id` + `occurred_at`)
- Only serialisable types: `str`, `float`, `int`, `UUID`, `datetime`, `bool`
- No mutable containers (`list`, `dict`) — use `tuple` if a collection is needed
- Update the event count comment at the top of `trading_events.py`

---

## Adding a New Risk Stage

Insert a new block in `src/risk/domain/services/pipeline.py` → `RiskPipeline.evaluate()`:

```python
# Stage N: My new check description
if my_condition:
    return RiskAssessment(
        approved=False,
        reason="Human-readable explanation of why this was rejected",
        signal_id=signal.id,
    )
```

- Always add between existing stages, not after stage 7 (position sizing)
- Update the module docstring stage list at the top of `pipeline.py`
- Write a test in `tests/unit/risk/test_pipeline.py` covering the new AC

---

## Adding a New CLI Command

```python
# src/entrypoints/cli/main.py
@app.command()
def my_command(
    symbol: str = typer.Option("EURUSD"),
    # ...
) -> None:
    """Short description shown in --help."""
    settings = Settings()
    container = build_container(settings, dry_run=True)
    # ... use container
```

---

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for ClaudeStrategy + knowledge ingestion |
| `DB_URL` | `postgresql+asyncpg://brocker:brocker@localhost/brocker` | PostgreSQL async URL |
| `DB_HOST` | `localhost` | Overridden to `db` inside Docker |
| `REDIS_URL` | `redis://localhost:6379/0` | For RedisEventBus (prod) |
| `MT5_LOGIN` | `0` | MT5 account login number |
| `MT5_PASSWORD` | — | MT5 account password |
| `MT5_SERVER` | — | MT5 broker server address |
| `WEIGHT_TA` | `0.25` | TAStrategy weight in aggregator |
| `WEIGHT_ML` | `0.35` | MLStrategy weight in aggregator |
| `WEIGHT_CLAUDE` | `0.40` | ClaudeStrategy weight in aggregator |
| `MIN_SIGNAL_THRESHOLD` | `0.60` | Minimum confidence to act |
| `CLAUDE_VETO_THRESHOLD` | `0.70` | Claude override confidence threshold |
| `RISK_PER_TRADE` | `0.01` | Fraction of balance risked per trade |
| `MAX_OPEN_POSITIONS` | `5` | Max simultaneous positions |

---

## Git Workflow

- Branch naming: `phase-NN/short-description` or `fix/issue-description`
- Commit format: imperative subject, 72 chars max, body explains *why* not *what*
- Always run `poetry run pytest tests/unit/ -v` before committing
- No force-pushing to `main`

---

## Before Closing Any Phase

```bash
# 1. All unit tests green
poetry run pytest tests/unit/ -v

# 2. No research isolation leaks
grep -r "from strategy.infrastructure\|from learning.infrastructure" src/research/

# 3. No MT5 module-level imports
grep -rn "^import MetaTrader5\|^from MetaTrader5" src/

# 4. Weights sum to 1.0 (verify in .env or settings default)
python -c "print(0.25 + 0.35 + 0.40)"  # must be 1.0

# 5. Update docs/ai_context.md phase table
# 6. Update spec status → DONE
```
