"""Entity — base class for domain entities with identity."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class Entity:
    """Entities are identified by their UUID.

    Two entities with the same id are considered equal regardless of
    other field values (identity equality, not structural equality).
    """
    id: UUID = field(default_factory=uuid4)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
