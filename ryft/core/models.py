"""Shared data shapes used across Ryft.

Kept intentionally dependency-free so every layer (commands, ui, services,
plugins) can import from here without pulling in heavy machinery.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ActivityEvent:
    message: str
    level: str = "info"  # info | success | warn | error
    at: float = field(default_factory=time.time)

    @property
    def time_str(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.at))


@dataclass
class SyncStatus:
    """Live state of the background sync watcher, consumed by the TUI."""

    current_file: str | None = None
    current_stage: str | None = None
    last_file: str | None = None
    last_commit_message: str | None = None
    last_push_time: float | None = None
    commits_this_session: int = 0
    busy: bool = False


@dataclass
class CommandSpec:
    """Metadata for one registered command (REPL, palette, and CLI)."""

    name: str
    handler: Callable[["AppContext", list[str]], None]
    description: str
    group: str = "general"
    usage: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


class ActivityFeed:
    """In-memory ring buffer of recent events, newest last.

    The ONLY place events get recorded. Commands and services call `.add()`;
    the UI calls `.recent()`/`.all()` to render. No raw logging elsewhere.
    """

    def __init__(self, max_events: int = 200) -> None:
        self._events: deque[ActivityEvent] = deque(maxlen=max_events)

    def add(self, message: str, level: str = "info") -> ActivityEvent:
        event = ActivityEvent(message=message, level=level)
        self._events.append(event)
        return event

    def recent(self, n: int = 8) -> list[ActivityEvent]:
        return list(self._events)[-n:]

    def all(self) -> list[ActivityEvent]:
        return list(self._events)


# Avoid a hard import cycle with context.py at type-check time only.
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    from .context import AppContext  # noqa: E402
