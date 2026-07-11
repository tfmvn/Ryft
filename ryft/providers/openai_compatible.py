"""OpenAI-compatible provider base.

One implementation serves every backend that exposes the OpenAI chat/embeddings
surface: OpenAI, Together, OpenRouter, Groq, Fireworks, DeepInfra, NVIDIA NIM,
and any LM Studio / OpenAI-compatible local server. They differ only in
`base_url`, auth header, and key environment variable — captured by the
`OpenAICompatibleProvider` parameters so there is no per-vendor copy/paste.

Streaming follows the OpenAI SSE format: `data: {json}` chunks terminated by
`data: [DONE]`.
"""

from __future__ import annotations

import json
import os

from ._async import run_thread, stream_lines
from ._http import post_json, post_stream
from .base import (
    CAP_CHAT,
    CAP_EMBED,
    CAP_STREAM,
    Message,
    ProviderHealth,
    Usage,
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        auth_scheme: str = "Bearer",
        models: list[str] | None = None,
        default_model: str | "",
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get(api_key_env)
        self.api_key_env = api_key_env
        self.auth_scheme = auth_scheme
        self._models = models or []
        self.default_model = default_model

    # ── interface ────────────────────────────────────────────────────────

    def capabilities(self) -> set[str]:
        return {CAP_CHAT, CAP_STREAM, CAP_EMBED}

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"{self.auth_scheme} {self.api_key}"}
        return {}

    def health(self) -> ProviderHealth:
        from time import monotonic

        if not self.api_key:
            return ProviderHealth(available=False, detail="no API key configured")
        if self.default_model:
            return self._model_health(self.default_model)
        # Probe without a model: just confirm auth by hitting models list.
        try:
            from ._http import get_json

            start = monotonic()
            get_json(f"{self.base_url}/models", headers=self._headers(), timeout=5)
            return ProviderHealth(available=True, latency_ms=(monotonic() - start) * 1000)
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return ProviderHealth(available=False, detail=str(exc))

    def _model_health(self, model: str) -> ProviderHealth:
        from time import monotonic

        try:
            start = monotonic()
            post_json(
                f"{self.base_url}/chat/completions",
                {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                headers=self._headers(),
                timeout=15,
                retries=0,
            )
            return ProviderHealth(available=True, latency_ms=(monotonic() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(available=False, detail=str(exc))

    async def chat(self, messages, model: str = "", **opts) -> "object":
        from .base import ChatResult

        model = model or self.default_model
        payload = {
            "model": model,
            "messages": _to_oai(messages),
            "stream": False,
            "temperature": float(opts.get("temperature", 0.2)),
        }
        if opts.get("max_tokens"):
            payload["max_tokens"] = int(opts["max_tokens"])
        data = await run_thread(
            post_json, f"{self.base_url}/chat/completions", payload,
            headers=self._headers(), timeout=int(opts.get("timeout", 120)), retries=1,
        )
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResult(
            text=choice["message"]["content"],
            model=data.get("model", model),
            usage=Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), usage.get("total_tokens", 0)),
            finish_reason=choice.get("finish_reason"),
        )

    async def stream(self, messages, model: str = "", **opts):
        from .base import StreamChunk

        model = model or self.default_model
        payload = {
            "model": model,
            "messages": _to_oai(messages),
            "stream": True,
            "temperature": float(opts.get("temperature", 0.2)),
        }
        if opts.get("max_tokens"):
            payload["max_tokens"] = int(opts["max_tokens"])
        async for raw in stream_lines(
            post_stream, f"{self.base_url}/chat/completions", payload,
            headers=self._headers(), timeout=int(opts.get("timeout", 180)),
        ):
            raw = raw.strip()
            if not raw.startswith("data:"):
                continue
            data = raw[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = obj["choices"][0].get("delta", {}).get("content")
            if delta:
                fr = obj["choices"][0].get("finish_reason")
                yield StreamChunk(delta=delta, finish_reason=fr)
            elif obj["choices"][0].get("finish_reason"):
                yield StreamChunk(delta="", finish_reason=obj["choices"][0]["finish_reason"])

    async def embed(self, texts: list[str], model: str = "", **opts) -> list[list[float]]:
        model = model or self.default_model
        payload = {"model": model, "input": texts}
        data = await run_thread(
            post_json, f"{self.base_url}/embeddings", payload,
            headers=self._headers(), timeout=int(opts.get("timeout", 60)), retries=1,
        )
        # OpenAI returns ordered embeddings; some clones return {"embedding":...}
        items = data.get("data") or []
        if items and "embedding" in items[0]:
            return [it["embedding"] for it in items]
        return data.get("embeddings", [])


def _to_oai(messages: list[Message]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]
