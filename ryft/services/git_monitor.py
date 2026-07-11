"""Git state monitor.

Polls git for branch / working-tree changes and publishes `git_state_changed`
events when something moves. The dashboard subscribes and re-renders; the
indexer service subscribes and re-indexes incrementally. We fingerprint the
state so we emit only on real change, not every poll.
"""

from __future__ import annotations

from .. import git as gitsys
from ..core.events import git_state_changed
from .base import PollingService


class GitMonitor(PollingService):
    name = "git_monitor"
    interval = 3.0

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self._fp = None

    def tick(self) -> None:
        branch = gitsys.current_branch(self.ctx.root)
        changes = gitsys.changed_files(self.ctx.root)
        fp = (branch, tuple(sorted((c.path, c.status) for c in changes)))
        if fp == self._fp:
            return
        self._fp = fp
        self.ctx.events.emit(git_state_changed(
            branch=branch, changed=[c.path for c in changes], count=len(changes),
        ))
