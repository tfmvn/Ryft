"""Core runtime: models, events, context, and bootstrap.

Tier 0 of the architecture. Imports nothing from Ryft's higher layers at module
load time, so it is safe to import first from any entry point.
"""

from __future__ import annotations

from .config import load_config
from .context import AppContext
from .events import Event, EventBus
from .lifecycle import attach_knowledge, attach_plugins, attach_services, build_context, shutdown
from .models import ActivityEvent, ActivityFeed, CommandSpec, SyncStatus

__all__ = [
    "load_config", "AppContext", "Event", "EventBus", "build_context", "shutdown",
    "attach_knowledge", "attach_services", "attach_plugins",
    "ActivityEvent", "ActivityFeed", "CommandSpec", "SyncStatus",
]
