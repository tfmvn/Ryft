"""Application bootstrap and teardown.

`build_context` assembles the long-lived subsystems into an `AppContext`. It is
the only place that decides *how* the runtime is wired; everything else just
reads from the context. Knowledge / services / plugins layers attach later via
the `attach_*` helpers (or directly by setting `ctx.knowledge` etc.), which keeps
this module from hard-importing layers that may not exist yet.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config.loader import load_config
from .context import AppContext
from .events import EventBus

logger = logging.getLogger(__name__)


def build_context(root: Path | None = None, *, start_services: bool = False) -> AppContext:
    """Resolve the project root, load config, and wire core subsystems + the
    AI provider registry. Returns a ready-to-use `AppContext`.

    Background *services* are constructed but only started when
    ``start_services=True`` (the TUI), so one-shot CLI commands never spawn
    worker threads they don't need.
    """
    from ..knowledge.store import KnowledgeStore
    from ..plugins.manager import PluginManager
    from ..providers import build_registry
    from ..services.manager import ServiceManager

    resolved = root or Path.cwd()
    cfg = load_config(resolved)
    events = EventBus()
    reg = build_registry(
        cfg.providers, cfg.providers.ollama, cfg.providers.openai,
        cfg.providers.anthropic, cfg.providers.google,
    )
    ctx = AppContext(root=cfg.root, config=cfg, events=events, providers=reg)

    # Knowledge store (SQLite). Indexing is lazy — commands that need it call
    # ctx.knowledge via the indexer; the service re-indexes in the background.
    ctx.knowledge = KnowledgeStore(ctx.root / ".ryft" / "knowledge.db")

    # Plugins: discover, load, and register into the live registries.
    plugins = PluginManager(ctx)
    plugins.load_all()
    ctx.plugins = plugins

    # Services: constructed (and wired through the event bus) but idle until
    # the caller starts them.
    ctx.services = ServiceManager(ctx)

    # Sync controller: the /watch and /sync commands drive it. Constructed here
    # (cheap — no threads/observers until .start()) so `ctx.sync` is always live.
    from ..sync import SyncController

    ctx.sync = SyncController(ctx)

    if start_services:
        ctx.services.start_all()

    return ctx


def attach_knowledge(ctx: AppContext, store) -> None:
    ctx.knowledge = store


def attach_services(ctx: AppContext, manager) -> None:
    ctx.services = manager


def attach_plugins(ctx: AppContext, manager) -> None:
    ctx.plugins = manager


def shutdown(ctx: AppContext) -> None:
    """Stop background services and signal the UI to stop. Idempotent."""
    ctx.running = False
    if ctx.services is not None:
        try:
            ctx.services.stop_all()
        except Exception as exc:  # noqa: BLE001 - teardown must not raise
            logger.warning("Error stopping services: %s", exc)
    if ctx.plugins is not None:
        try:
            ctx.plugins.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error shutting down plugins: %s", exc)
