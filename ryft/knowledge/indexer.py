"""Knowledge indexer — walks the repo and populates the `KnowledgeStore`.

Two responsibilities, both incremental:

1. **Symbols**: discover source files (via `commons.fs.discover_files`), extract
   symbols, and upsert only files whose content hash changed. Deleted files are
   pruned. Emits `index_progress` / `index_ready` events for the dashboard.
2. **Commits**: capture recent git history into the store so timeline/search can
   use it without shelling out each render.

Embeddings (semantic search) are a separate async step — `Indexer.embed_all` —
so the cheap structural index stays synchronous and fast on huge repos.
"""

from __future__ import annotations

from pathlib import Path

from .. import fs as fsys
from .. import git as gitsys
from ..core.events import index_progress, index_ready
from . import symbols
from .store import KnowledgeStore


class Indexer:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.store = KnowledgeStore(ctx.root / ".ryft" / "knowledge.db")

    # ── structural index ─────────────────────────────────────────────────

    def index(self, full: bool = False) -> int:
        """Index symbols + commits. Returns the number of files (re)indexed."""
        files = fsys.discover_files(
            self.ctx.root, list(self.ctx.config.ignore.patterns) or [],
        )
        indexed_rel: set[str] = set()
        indexed = 0
        total = len(files)

        for i, path in enumerate(files, start=1):
            try:
                result = symbols.extract(path, self.ctx.root)
            except Exception:  # noqa: BLE001 - a bad file must not abort indexing
                continue
            rel = self._rel(path)
            indexed_rel.add(rel)
            if full or self.store.file_hash(rel) != result.hash:
                self.store.upsert_symbols(rel, result.symbols)
                self.store.mark_indexed(rel, result.hash)
                indexed += 1
            if i % 50 == 0 and self.ctx.events is not None:
                self.ctx.events.emit(index_progress(processed=i, total=total))

        # prune files that no longer exist (compare against indexed rel paths)
        for row in self.store._conn.execute("SELECT path FROM files").fetchall():  # noqa: SLF001
            if row["path"] not in indexed_rel:
                self.store.remove_file(row["path"])

        # git history
        try:
            self.store.add_commits(gitsys.recent_commits(self.ctx.root, n=200))
        except Exception:  # noqa: BLE001
            pass

        if self.ctx.events is not None:
            self.ctx.events.emit(index_ready(indexed=indexed, total=total))
        return indexed

    # ── embeddings (semantic) ────────────────────────────────────────────

    async def embed_all(self, batch: int = 32) -> int:
        """Compute and store embeddings for symbols without one yet.

        Uses the `embed` provider role. Returns the number of symbols embedded.
        Skipped silently when no embedding provider is configured.
        """
        provider, model = self.ctx.provider_for("embed")
        if provider is None or not hasattr(provider, "embed"):
            return 0
        all_syms = self.store.all_symbols()
        # Skip already-embedded refs.
        done = {
            r["ref"]
            for r in self.store._conn.execute(  # noqa: SLF001
                "SELECT ref FROM embeddings WHERE kind='symbol'"
            ).fetchall()
        }
        pending = [s for s in all_syms if f"{s.file}:{s.name}" not in done]
        embedded = 0
        for i in range(0, len(pending), batch):
            chunk = pending[i : i + batch]
            texts = [f"{s.name}\n{s.signature}\n{s.doc}"[:2000] for s in chunk]
            try:
                vectors = await provider.embed(texts, model=model)
            except Exception:  # noqa: BLE001 - embedding failures are non-fatal
                break
            for sym, vec in zip(chunk, vectors):
                self.store.store_embedding("symbol", f"{sym.file}:{sym.name}", model, vec)
                embedded += 1
        return embedded

    # ── helpers ──────────────────────────────────────────────────────────

    def _rel(self, path: Path) -> str:
        return fsys.human_path(path, self.root())

    def root(self) -> Path:
        return self.ctx.root

    def close(self) -> None:
        self.store.close()
