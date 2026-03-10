"""RedisEventBus — Redis Streams-backed event bus (production stub).

This is a stub implementation. Full implementation requires:
- redis.asyncio client
- JSON serialisation of DomainEvent subclasses
- Consumer groups for at-least-once delivery
- Dead-letter queue for failed handlers
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Type

from shared_kernel.domain_event import DomainEvent

logger = logging.getLogger(__name__)


class RedisEventBus:
    """Production event bus backed by Redis Streams.

    Not yet implemented — falls back gracefully with a warning.
    Replace the InMemoryEventBus with this class in the composition
    root when you are ready for multi-process event delivery.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        logger.warning("RedisEventBus is not yet implemented; no events will be delivered.")

    def subscribe(
        self,
        event_type: Type[DomainEvent],
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> None:
        logger.warning("RedisEventBus.subscribe() is a no-op (stub).")

    async def publish(self, event: DomainEvent) -> None:
        logger.warning("RedisEventBus.publish() is a no-op (stub): %s", event.event_type)
