"""EventBus Protocol and EventHandler type alias."""
from __future__ import annotations

from typing import Awaitable, Callable, Protocol, Type, TypeVar

from shared_kernel.domain_event import DomainEvent

E = TypeVar("E", bound=DomainEvent)

# An event handler is an async callable that receives a single event
EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventBus(Protocol):
    """Protocol for event bus implementations.

    Concrete implementations: InMemoryEventBus, RedisEventBus.
    Usage:
        bus.subscribe(SignalGenerated, my_handler)
        await bus.publish(SignalGenerated(...))
    """

    def subscribe(self, event_type: Type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        """Register *handler* to be called when *event_type* events are published."""
        ...

    async def publish(self, event: DomainEvent) -> None:
        """Publish *event* to all subscribers registered for its type."""
        ...
