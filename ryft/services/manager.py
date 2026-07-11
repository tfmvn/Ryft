"""Service manager — owns the background workers.

Builds the configured services, wires them together through the event bus (git
changes trigger a re-index), and starts/stops them as a unit. Also owns the
shared `AICache`. The manager is attached to `ctx.services` by the lifecycle so
commands and the UI can read worker state.
"""

from __future__ import annotations

from ..core.events import service_state_changed
from .ai_cache import AICache
from .base import Service
from .git_monitor import GitMonitor
from .indexer import IndexerService


class ServiceManager:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.services: dict[str, Service] = {}
        self.cache = AICache()
        self._wire()

    def _wire(self) -> None:
        cfg = self.ctx.config.services
        if cfg.git_monitor:
            self.register(GitMonitor(self.ctx))
        if cfg.indexer:
            self.register(IndexerService(self.ctx))

        # Git changes -> prompt re-index without waiting for the next poll.
        git = self.services.get("git_monitor")
        idx = self.services.get("indexer")
        if git is not None and idx is not None:
            self.ctx.events.subscribe(
                "git.state.changed", lambda _e: idx.reindex_now()
            )

    def register(self, svc: Service) -> None:
        self.services[svc.name] = svc

    def start_all(self) -> None:
        for svc in self.services.values():
            svc.start()
            self.ctx.events.emit(service_state_changed(name=svc.name, running=True))

    def stop_all(self) -> None:
        for svc in self.services.values():
            svc.stop()
            self.ctx.events.emit(service_state_changed(name=svc.name, running=False))

    def state(self) -> dict[str, bool]:
        return {name: svc.running for name, svc in self.services.items()}

    def get(self, name: str) -> Service | None:
        return self.services.get(name)
