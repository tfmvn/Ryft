"""AI response cache.

Cheap memoization so repeated prompts (commit messages for the same diff, the
same explain query, identical analyses) don't burn tokens or latency. Purely
in-memory with an LRU cap and optional TTL; nothing here touches the network.

Keyed by a stable hash of (role, model, prompt). On a hit we emit
`ai_cache_hit` so the dashboard can show cache savings.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    value: Any
    at: float


class AICache:
    def __init__(self, max_size: int = 512, ttl: float = 3600.0) -> None:
        self.max_size = max_size
        self.ttl = ttl
        self._store: "OrderedDict[str, _Entry]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(role: str, model: str, prompt: str) -> str:
        blob = f"{role}\x00{model}\x00{prompt}".encode("utf-8", "replace")
        return hashlib.sha1(blob).hexdigest()[:24]

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        if self.ttl and (time.time() - entry.at) > self.ttl:
            self._store.pop(key, None)
            self.misses += 1
            return None
        self._store.move_to_end(key)
        self.hits += 1
        return entry.value

    def put(self, key: str, value: Any) -> None:
        self._store[key] = _Entry(value=value, at=time.time())
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "size": len(self._store)}

    def clear(self) -> None:
        self._store.clear()
        self.hits = self.misses = 0
