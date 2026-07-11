"""AppContext — the wiring bag handed to subsystems and commands.

It is NOT a god object: it holds references to the long-lived subsystems and a
little shared mutable state (`running`, `ui`), but contains no business logic.
Subsystems are attached by `lifecycle.build_context`; ones not yet constructed
(default `None`) are filled in as their layers come online.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..providers.registry import ProviderRegistry
from .config.schema import Config
from .events import EventBus
from .models import ActivityFeed, SyncStatus


@dataclass
class AppContext:
    root: Path
    config: Config
    events: EventBus
    providers: ProviderRegistry
    activity: ActivityFeed = field(default_factory=ActivityFeed)

    # Attached once their layers exist (knowledge store, services manager,
    # plugins manager). Typed loosely on purpose — they are not part of core.
    knowledge: Any | None = None
    services: Any | None = None
    plugins: Any | None = None

    # UI back-reference, set when the TUI starts; lets commands emit UI events
    # without importing prompt_toolkit at module load.
    ui: Any | None = None

    # Legacy compatibility fields — optional so one-shot commands that never
    # construct an AI client or sync watcher stay clean.
    ai: Any | None = None
    sync: Any | None = None
    sync_status: SyncStatus = field(default_factory=SyncStatus)
    console: Any = None

    running: bool = True

    def provider_for(self, role: str):
        """Convenience resolver: (provider, model) for a role, or (None, '')."""
        resolved = self.providers.resolve(role)
        if resolved is None:
            return None, ""
        return resolved.provider, resolved.model
