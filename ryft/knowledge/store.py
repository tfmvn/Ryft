"""Knowledge store — the project's persistent memory, backed by SQLite.

Lives at `.ryft/knowledge.db` (or a path you pass). Stores *symbols* (functions,
classes, methods) extracted by the indexer, *commits* captured from git, and
optional *embeddings* for semantic search. The schema is versioned and migrated
on open, so the store is safe to reopen across Ryft versions.

No heavy dependencies — just `sqlite3`. Vectors are stored as JSON blobs and
compared in Python (fine for the thousands-of-symbol scale of a normal repo);
a vector index can replace this later without changing the interface.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1


@dataclass
class Symbol:
    name: str
    kind: str            # function | class | method | constant
    file: str
    line: int
    end_line: int
    signature: str
    doc: str
    hash: str


class KnowledgeStore:
    def __init__(self, db_path: Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    # ── schema ────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS symbols ("
            " id INTEGER PRIMARY KEY, file TEXT, name TEXT, kind TEXT,"
            " line INTEGER, end_line INTEGER, signature TEXT, doc TEXT, hash TEXT)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file)")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS files ("
            " path TEXT PRIMARY KEY, hash TEXT, indexed_at REAL)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS commits ("
            " hash TEXT PRIMARY KEY, author TEXT, date TEXT, subject TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS embeddings ("
            " id INTEGER PRIMARY KEY, kind TEXT, ref TEXT, model TEXT,"
            " vector TEXT)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_embed_ref ON embeddings(kind, ref)")
        cur.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._conn.commit()

    # ── symbols ───────────────────────────────────────────────────────────

    def upsert_symbols(self, file: str, symbols: list[Symbol]) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM symbols WHERE file = ?", (file,))
        cur.executemany(
            "INSERT INTO symbols (file, name, kind, line, end_line, signature, doc, hash)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (s.file, s.name, s.kind, s.line, s.end_line, s.signature, s.doc, s.hash)
                for s in symbols
            ],
        )
        self._conn.commit()

    def remove_file(self, file: str) -> None:
        self._conn.execute("DELETE FROM symbols WHERE file = ?", (file,))
        self._conn.execute("DELETE FROM files WHERE path = ?", (file,))
        self._conn.commit()

    def symbols_for_file(self, file: str) -> list[Symbol]:
        rows = self._conn.execute(
            "SELECT * FROM symbols WHERE file = ? ORDER BY line", (file,)
        ).fetchall()
        return [_row_to_symbol(r) for r in rows]

    def search_symbols(self, term: str, limit: int = 20) -> list[Symbol]:
        like = f"%{term.lower()}%"
        rows = self._conn.execute(
            "SELECT * FROM symbols"
            " WHERE LOWER(name) LIKE ? OR LOWER(signature) LIKE ? OR LOWER(doc) LIKE ?"
            " ORDER BY (LOWER(name) LIKE ?) DESC, line LIMIT ?",
            (like, like, like, f"{term.lower()}%", limit),
        ).fetchall()
        return [_row_to_symbol(r) for r in rows]

    def all_symbols(self) -> list[Symbol]:
        return [_row_to_symbol(r) for r in self._conn.execute("SELECT * FROM symbols").fetchall()]

    def symbol_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]

    def file_hash(self, path: str) -> str | None:
        row = self._conn.execute(
            "SELECT hash FROM files WHERE path = ?", (path,)
        ).fetchone()
        return row["hash"] if row else None

    def mark_indexed(self, path: str, hash_: str) -> None:
        self._conn.execute(
            "INSERT INTO files (path, hash, indexed_at) VALUES (?, ?, ?)"
            " ON CONFLICT(path) DO UPDATE SET hash=excluded.hash, indexed_at=excluded.indexed_at",
            (path, hash_, time.time()),
        )
        self._conn.commit()

    # ── commits ───────────────────────────────────────────────────────────

    def add_commits(self, commits: list[dict]) -> None:
        self._conn.executemany(
            "INSERT OR IGNORE INTO commits (hash, author, date, subject) VALUES (?, ?, ?, ?)",
            [(c["hash"], c["author"], c["date"], c["subject"]) for c in commits],
        )
        self._conn.commit()

    def recent_commits(self, n: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT hash, author, date, subject FROM commits ORDER BY date DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── embeddings ────────────────────────────────────────────────────────

    def store_embedding(self, kind: str, ref: str, model: str, vector: list[float]) -> None:
        self._conn.execute(
            "INSERT INTO embeddings (kind, ref, model, vector) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET vector=excluded.vector, model=excluded.model",
            (kind, ref, model, json.dumps(vector)),
        )
        self._conn.commit()

    def similar(self, vector: list[float], k: int = 10, model: str | None = None) -> list[tuple[str, str, float]]:
        """Return up to k (ref, kind, score) rows most similar to `vector`."""
        query = "SELECT ref, kind, vector FROM embeddings"
        params: list = []
        if model:
            query += " WHERE model = ?"
            params.append(model)
        rows = self._conn.execute(query, params).fetchall()
        scored = []
        for r in rows:
            try:
                v = json.loads(r["vector"])
            except (json.JSONDecodeError, TypeError):
                continue
            scored.append((r["ref"], r["kind"], _cosine(vector, v)))
        scored.sort(key=lambda t: t[2], reverse=True)
        return scored[:k]

    # ── lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "KnowledgeStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _row_to_symbol(r: sqlite3.Row) -> Symbol:
    return Symbol(
        name=r["name"], kind=r["kind"], file=r["file"], line=r["line"],
        end_line=r["end_line"], signature=r["signature"], doc=r["doc"], hash=r["hash"],
    )


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
