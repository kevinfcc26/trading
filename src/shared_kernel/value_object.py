"""ValueObject — base for immutable, structurally-equal domain value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueObject:
    """Value objects have no identity — equality is structural (all fields)."""
