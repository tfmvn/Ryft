"""Plugin manager — discovery and loading.

Two discovery channels, both optional and failure-isolated:

1. **Entry points** in the `ryft.plugins` group (pip-installed plugins).
2. **Directory scan** of `~/.config/ryft/plugins` and `<project>/.ryft/plugins`
   (local, no-packaging plugins), plus `RYFT_PLUGIN_PATH` (colon-separated).

Each discovered module/object must expose `meta` (a `PluginMeta`) and a
`register(api)` method. The manager builds a `PluginAPI` per plugin, calls
`register`, then drains the collected commands/providers/services/panels. A bad
plugin never breaks the others — it's logged and skipped.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

from ..core.events import plugin_loaded
from .api import PluginAPI
from .spec import PluginMeta

logger = logging.getLogger(__name__)

ENTRY_GROUP = "ryft.plugins"


class PluginManager:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.plugins: list[PluginMeta] = []
        self.commands: list = []
        self.providers: list = []     # (name, provider)
        self.services: list = []      # factory(ctx) -> Service
        self.panels: list = []

    # ── discovery ────────────────────────────────────────────────────────

    def discover(self) -> list[object]:
        found: list[object] = []
        found += self._from_entry_points()
        for module in self._from_directories():
            found.append(module)
        return found

    def _from_entry_points(self) -> list[object]:
        out: list[object] = []
        try:
            eps = importlib.metadata.entry_points(group=ENTRY_GROUP)
        except Exception:  # noqa: BLE001 - older Pythons / missing group
            return out
        for ep in eps:
            try:
                out.append(ep.load())
            except Exception:  # noqa: BLE001 - a broken plugin must not crash boot
                logger.exception("Failed to load plugin entry point %s", ep.name)
        return out

    def _from_directories(self) -> list[object]:
        out: list[object] = []
        dirs: list[Path] = []
        env = os.environ.get("RYFT_PLUGIN_PATH")
        if env:
            dirs += [Path(p) for p in env.split(":") if p]
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        dirs.append(base / "ryft" / "plugins")
        dirs.append(self.ctx.root / ".ryft" / "plugins")
        for d in dirs:
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.py")):
                if f.name == "__init__.py":
                    continue
                mod = self._load_file(f)
                if mod is not None:
                    out.append(mod)
        return out

    def _load_file(self, path: Path) -> object | None:
        try:
            spec = importlib.util.spec_from_file_location(f"_ryft_plugin_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
        except Exception:  # noqa: BLE001
            logger.exception("Failed to import plugin %s", path)
            return None

    # ── loading ────────────────────────────────────────────────────────────

    def load_all(self) -> None:
        for plugin in self.discover():
            self._load_one(plugin)

    def _load_one(self, plugin: object) -> None:
        meta = getattr(plugin, "meta", None)
        if not isinstance(meta, PluginMeta):
            logger.warning("Skipping plugin %r: missing valid `meta`", plugin)
            return
        api = PluginAPI(self.ctx, meta)
        try:
            plugin.register(api)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            logger.exception("Plugin %s register() failed", meta.name)
            return
        self.plugins.append(meta)
        self.commands += api._commands
        self.providers += api._providers
        self.services += api._services
        self.panels += api._panels

        # ── Register drained items into the live runtime ──────────────────
        # This is the step the old manager missed: collected commands,
        # providers, and services were stored but never connected to the
        # registries commands and the TUI actually read. Without it a plugin
        # could "load" and do nothing.
        from ..commands import REGISTRY  # local import avoids a load-time cycle

        for spec in api._commands:
            REGISTRY[spec.name] = spec

        for name, provider in api._providers:
            try:
                self.ctx.providers.register(provider)
                roles = getattr(provider, "roles", None)
                if isinstance(roles, dict):
                    self.ctx.providers.configure_roles(roles)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to register provider %s from plugin %s", name, meta.name)

        for factory in api._services:
            try:
                svc = factory(self.ctx)
                if self.ctx.services is not None:
                    self.ctx.services.register(svc)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to build service from plugin %s", meta.name)

        self.ctx.events.emit(plugin_loaded(name=meta.name, version=meta.version))
        self.ctx.activity.add(f"plugin loaded: {meta.name}", "success")

    def shutdown(self) -> None:
        self.plugins.clear()
        self.commands.clear()
        self.providers.clear()
        self.services.clear()
        self.panels.clear()
