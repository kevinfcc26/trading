"""DomainEvent — base class for all domain events."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DomainEvent:
    """Immutable base for every domain event.

    Subclasses add domain-specific fields as frozen dataclass fields.
    """
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_type(self) -> str:
        return self.__class__.__name__
