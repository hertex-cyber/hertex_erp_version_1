"""Lightweight in-process event bus.

Modules publish domain events (e.g. ``invoice.posted``); listeners subscribe without
importing each other, mirroring the Celery/Redis event bus described in the technical
plan. Celery tasks can replace the in-process fan-out without changing publishers.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("hertex.events")

Handler = Callable[[dict[str, Any]], Awaitable[None]]

_handlers: dict[str, list[Handler]] = defaultdict(list)


def subscribe(event_name: str) -> Callable[[Handler], Handler]:
    def decorator(handler: Handler) -> Handler:
        _handlers[event_name].append(handler)
        return handler

    return decorator


async def publish(
    event_name: str, payload: dict[str, Any], correlation_id: str | None = None
) -> None:
    if correlation_id:
        payload.setdefault("correlation_id", correlation_id)
    logger.info(
        "event.published",
        extra={"event": event_name, "correlation_id": correlation_id},
    )
    handlers = list(_handlers.get(event_name, []))
    if not handlers:
        return
    results = await asyncio.gather(
        *(handler(payload) for handler in handlers), return_exceptions=True
    )
    for result in results:
        if isinstance(result, Exception):
            logger.exception("event.handler_failed", exc_info=result, extra={"event": event_name})
