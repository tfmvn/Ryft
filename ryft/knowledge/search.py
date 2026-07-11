"""Search over the knowledge store.

Two modes, composed by callers:

* **Lexical** — `LIKE` over symbol names/signatures/docs and commit subjects.
  Instant, works with no AI provider. This is what powers `:search` in the TUI.
* **Semantic** — embed the query with the `embed` role and rank stored symbol
  embeddings by cosine similarity. Requires an embedding provider; falls back to
  lexical when none is configured.
"""

from __future__ import annotations

from .store import KnowledgeStore, Symbol


def lexical_symbols(store: KnowledgeStore, query: str, limit: int = 20) -> list[Symbol]:
    return store.search_symbols(query, limit)


def lexical_commits(store: KnowledgeStore, query: str, limit: int = 10) -> list[dict]:
    like = f"%{query.lower()}%"
    rows = store._conn.execute(  # noqa: SLF001
        "SELECT hash, author, date, subject FROM commits"
        " WHERE LOWER(subject) LIKE ? OR LOWER(author) LIKE ?"
        " ORDER BY date DESC LIMIT ?",
        (like, like, limit),
    ).fetchall()
    return [dict(r) for r in rows]


async def semantic_symbols(ctx, store: KnowledgeStore, query: str, k: int = 10) -> list[tuple[str, str, float]]:
    """Rank symbols by semantic similarity to `query`.

    Returns [(ref, kind, score)]; `ref` is "file:symbol". Falls back to an empty
    list when no embedding provider is configured or embedding fails.
    """
    provider, model = ctx.provider_for("embed")
    if provider is None or not hasattr(provider, "embed"):
        return []
    try:
        vectors = await provider.embed([query], model=model)
    except Exception:  # noqa: BLE001
        return []
    if not vectors:
        return []
    return store.similar(vectors[0], k=k, model=model)


async def explain_symbol(ctx, store: KnowledgeStore, ref: str) -> str | None:
    """Produce a short natural-language description of a symbol using the
    `analyze` role. Returns None when no chat provider is available."""
    provider, model = ctx.provider_for("analyze")
    if provider is None or not hasattr(provider, "chat"):
        return None
    sym = _symbol_by_ref(store, ref)
    if sym is None:
        return None
    prompt = (
        f"Explain the {sym.kind} `{sym.name}` defined in {sym.file} "
        f"(lines {sym.line}-{sym.end_line}).\n\nSignature: {sym.signature}\n"
        f"Docstring:\n{sym.doc}\n\nGive a concise (2-3 sentence) explanation."
    )
    try:
        result = await provider.chat([{"role": "user", "content": prompt}], model=model)
    except Exception:  # noqa: BLE001
        return None
    return getattr(result, "text", None)


def _symbol_by_ref(store: KnowledgeStore, ref: str) -> Symbol | None:
    file, _, name = ref.partition(":")
    for s in store.symbols_for_file(file):
        if s.name == name:
            return s
    return None
