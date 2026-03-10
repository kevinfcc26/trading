# Phase XX — [Title]

**Status:** DRAFT | APPROVED | IMPLEMENTING | DONE

---

## 1. Goal

_One paragraph: what problem does this phase solve, and what observable outcome marks it complete?_

---

## 2. Scope

**In scope:**
- …

**Out of scope:**
- …

---

## 3. Domain Concepts

| Concept | Definition |
|---------|-----------|
| … | … |

---

## 4. Acceptance Criteria

Each AC maps 1-to-1 to a test. ACs are numbered; tests reference them in docstrings.

- **AC-1** …
- **AC-2** …
- **AC-N** …

---

## 5. Files to Create or Modify

| # | File | Action | Notes |
|---|------|--------|-------|
| 1 | `src/…` | CREATE | … |
| 2 | `src/…` | MODIFY | … |
| 3 | `tests/…` | CREATE | … |

---

## 6. API / Signatures

The contract. Code must match these signatures exactly; if they change, update this spec first.

```python
# src/…/module.py

class SomeClass:
    def some_method(self, param: Type) -> ReturnType: ...
```

---

## 7. Test Plan

| Test name | Covers AC | Notes |
|-----------|-----------|-------|
| `test_something` | AC-1 | … |

---

## 8. Dependencies and Risks

| Item | Type | Mitigation |
|------|------|-----------|
| … | Dependency / Risk | … |

---

## 9. Implementation Notes

_Guidance for the implementer: algorithm choices, gotchas, edge cases, ordering constraints._

---

## 10. Done Checklist

- [ ] All files listed in §5 created / modified
- [ ] All ACs verified by passing tests
- [ ] `poetry run pytest tests/unit/` fully green
- [ ] `docs/ai_context.md` updated (phase → ✅ Done)
- [ ] This spec status → DONE
