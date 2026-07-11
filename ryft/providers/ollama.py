"""Ollama provider — local models with no API key.

Capabilities: chat, stream, embed. Some models (e.g. `llama3.2`) also support
reasoning-style prompting but we expose only what is verifiable: chat/stream
via /api/chat and embeddings via /api/embed. `health()` is the cheap
`/api/tags` ping. Multi-line model tags are passed straight through.
"""

from __future__ import annotations

import json

from ._async import run_thread, stream_lines
from ._http import get_json, post_json, post_stream
from .base import (
    CAP_CHAT,
    CAP_EMBED,
    CAP_STREAM,
    Message,
    ProviderHealth,
    Usage,
)

DEFAULT_HOST = "http://localhost:11434"


class OllamaProvider:
    def __init__(self, host: str = DEFAULT_HOST, models: list[str] | None = None) -> None:
        self.host = host.rstrip("/")
        self.name = "ollama"
        self._models = models or []

    # ── interface ────────────────────────────────────────────────────────

    def capabilities(self) -> set[str]:
        return {CAP_CHAT, CAP_STREAM, CAP_EMBED}

    def health(self) -> ProviderHealth:
        from time import monotonic

        start = monotonic()
        try:
            get_json(f"{self.host}/api/tags", timeout=3)
            return ProviderHealth(available=True, latency_ms=(monotonic() - start) * 1000)
        except ProviderError as exc:
            return ProviderHealth(available=False, detail=str(exc))

    async def chat(self, messages, model: str = "", **opts) -> "object":
        from .base import ChatResult

        payload = {"model": model, "messages": _to_ollama(messages), "stream": False}
        data = await run_thread(post_json, f"{self.host}/api/chat", payload, timeout=int(opts.get("timeout", 120)))
        content = data.get("message", {}).get("content", "")
        prompt = data.get("prompt_eval_count", 0)
        comp = data.get("eval_count", 0)
        return ChatResult(text=content, model=model, usage=Usage(prompt, comp, prompt + comp))

    async def stream(self, messages, model: str = "", **opts):
        from .base import StreamChunk

        payload = {"model": model, "messages": _to_ollama(messages), "stream": True}
        async for line in stream_lines(post_stream, f"{self.host}/api/chat", payload, timeout=int(opts.get("timeout", 180))):
            line = line.strip()
            if not line or not line.startswith("data:") and not line.startswith("{"):
                continue
            if line.startswith("data:"):
                line = line[len("data:"):].strip()
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            delta = obj.get("message", {}).get("content", "")
            if delta:
                yield StreamChunk(delta=delta, finish_reason=obj.get("done") and "stop" or None)

    async def embed(self, texts: list[str], model: str = "", **opts) -> list[list[float]]:
        payload = {"model": model, "input": texts}
        data = await run_thread(post_json, f"{self.host}/api/embed", payload, timeout=int(opts.get("timeout", 60)))
        return data.get("embeddings", [])


def _to_ollama(messages: list[Message]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]
