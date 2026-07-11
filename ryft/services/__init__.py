"""Background services: workers that keep Ryft live without blocking the UI.

`Service`/`PollingService` are the base; `GitMonitor` and `IndexerService` are
the built-ins; `ServiceManager` owns them and the shared `AICache`.
"""

from __future__ import annotations

from .ai_cache import AICache
from .base import PollingService, Service
from .git_monitor import GitMonitor
from .indexer import IndexerService
from .manager import ServiceManager

__all__ = [
    "AICache", "PollingService", "Service", "GitMonitor", "IndexerService",
    "ServiceManager",
]
