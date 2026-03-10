"""InMemoryEventBus — async in-process pub/sub (MVP implementation)."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable, Type

from shared_kernel.domain_event import DomainEvent

logger = logging.getLogger(__name__)


class InMemoryEventBus:
    """Async in-process event bus.

    All handlers for a given event type are called concurrently via
    asyncio.gather so that a slow handler does not block others.
    """

    def __init__(self) -> None:
        self._handlers: dict[Type[DomainEvent], list[Callable]] = defaultdict(list)

    def subscribe(
        self,
        event_type: Type[DomainEvent],
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> None:
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed %s to %s", handler.__qualname__, event_type.__name__)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            logger.debug("No handlers for %s", event.event_type)
            return

        logger.debug("Publishing %s to %d handler(s)", event.event_type, len(handlers))
        results = await asyncio.gather(
            *[h(event) for h in handlers],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error("Event handler error for %s: %s", event.event_type, result)
