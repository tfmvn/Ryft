"""PluginAPI — the surface a plugin is handed at registration time.

This is the *only* thing a plugin should touch of Ryft's internals. It exposes
a read-only view of the context plus registration methods; the manager drains
the collected items after `register()` returns. Plugins never reach into the
registry, store, or UI directly — they go through here, which keeps the boundary
auditable and safe to evolve.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..core.context import AppContext
    from ..core.models import CommandSpec
    from ..services.base import Service


class PluginAPI:
    def __init__(self, ctx: "AppContext", meta) -> None:
        self.ctx = ctx
        self.meta = meta
        self._commands: list = []
        self._providers: list = []
        self._services: list = []
        self._panels: list = []

    # ── registration (called by the plugin's register()) ─────────────────

    def register_command(self, spec: "CommandSpec") -> None:
        self._commands.append(spec)

    def register_provider(self, name: str, provider) -> None:
        self._providers.append((name, provider))

    def register_service(self, factory: "Callable[[AppContext], Service]") -> None:
        self._services.append(factory)

    def register_panel(self, panel) -> None:
        self._panels.append(panel)

    # ── read-only access ─────────────────────────────────────────────────

    def log(self, message: str) -> None:
        self.ctx.activity.add(f"[plugin:{self.meta.name}] {message}", "info")
