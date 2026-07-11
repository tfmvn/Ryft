"""Shared async shims so provider backends never block the event loop.

Provider network calls are synchronous (urllib). These helpers run them in a
worker thread and, for streaming, re-yield lines as they arrive.
"""

from __future__ import annotations

import asyncio
import queue


async def run_thread(fn, *args, **kwargs):
    """Run a blocking function in a worker thread, returning its result."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def stream_lines(fn, *args, **kwargs):
    """Drive a blocking line/object generator in a worker thread and re-yield
    each produced item immediately. Exceptions raised inside the generator are
    re-raised on the consumer side."""
    q: "queue.Queue[object]" = queue.Queue()
    sentinel = object()

    def _produce() -> None:
        try:
            for item in fn(*args, **kwargs):
                q.put(item)
        except Exception as exc:  # surface to consumer
            q.put(exc)
        finally:
            q.put(sentinel)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _produce)
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is sentinel:
            break
        if isinstance(item, Exception):
            raise item
        yield item
