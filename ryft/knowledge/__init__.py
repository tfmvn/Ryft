"""Project knowledge layer: store + indexer + search.

The indexer populates the store from source files and git; search queries it
lexically and (when an embedding provider is configured) semantically.
"""

from __future__ import annotations

from .indexer import Indexer
from .search import (
    explain_symbol, lexical_commits, lexical_symbols, semantic_symbols,
)
from .store import KnowledgeStore, Symbol

__all__ = [
    "Indexer", "KnowledgeStore", "Symbol", "lexical_symbols", "lexical_commits",
    "semantic_symbols", "explain_symbol",
]
