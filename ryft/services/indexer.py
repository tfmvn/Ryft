"""Indexer service.

Runs the structural knowledge index on an interval and on demand (e.g. right
after the git monitor reports a change, so the symbol graph stays fresh without
waiting for the next poll). Embeddings are refreshed separately and lazily by
the semantic-search path, not on this tight loop.
"""

from __future__ import annotations

from ..knowledge import Indexer
from .base import PollingService


class IndexerService(PollingService):
    name = "indexer"
    interval = 30.0

    def __init__(self, ctx, indexer: Indexer | None = None) -> None:
        super().__init__()
        self.ctx = ctx
        self.indexer = indexer or Indexer(ctx)

    def tick(self) -> None:
        """Periodic incremental re-index."""
        self.indexer.index(full=False)

    def reindex_now(self) -> int:
        """Force an incremental index immediately (used after git changes)."""
        return self.indexer.index(full=False)

    def reindex_full(self) -> int:
        return self.indexer.index(full=True)
