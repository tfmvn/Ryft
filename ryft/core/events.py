"""A tiny, thread-safe typed event bus.

Workers and commands communicate through events, never by calling each other
directly. The dashboard subscribes and re-renders on change; services publish
state transitions. This decouples producers from consumers so the UI never
polls and slow work never blocks the paint.

Handlers must be fast (set a flag, enqueue a render). Long work belongs in a
service, not in an event handler.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

Handler = Callable[["Event"], None]


@dataclass
class Event:
    """A named event with an arbitrary payload dict."""

    type: str
    data: dict = field(default_factory=dict)
    at: float = field(default_factory=lambda: __import__("time").time())


# ── Typed event constructors (so publishers/subscribers agree on shape) ──

def git_state_changed(**data: object) -> Event:
    return Event("git.state.changed", dict(data))

def index_progress(**data: object) -> Event:
    return Event("index.progress", dict(data))

def index_ready(**data: object) -> Event:
    return Event("index.ready", dict(data))

def ai_cache_hit(**data: object) -> Event:
    return Event("ai.cache.hit", dict(data))

def provider_health_changed(**data: object) -> Event:
    return Event("provider.health.changed", dict(data))

def activity_logged(**data: object) -> Event:
    return Event("activity.logged", dict(data))


def plugin_loaded(**data: object) -> Event:
    return Event("plugin.loaded", dict(data))

def service_state_changed(**data: object) -> Event:
    return Event("service.state.changed", dict(data))


class EventBus:
    """Pub/sub with topic subscription and synchronous, fast dispatch."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            self._subs.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            handlers = self._subs.get(event_type)
            if handlers and handler in handlers:
                handlers.remove(handler)

    def emit(self, event: Event) -> None:
        """Deliver to exact-type subscribers and to wildcard ("*") subscribers."""
        with self._lock:
            exact = list(self._subs.get(event.type, ()))
            wild = list(self._subs.get("*", ()))
        for handler in exact + wild:
            try:
                handler(event)
            except Exception:  # a bad subscriber must never break the emitter
                logger.exception("Event handler for %s failed", event.type)

    def clear(self) -> None:
        with self._lock:
            self._subs.clear()
