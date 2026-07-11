"""Anthropic (Claude) provider.

Uses the Messages API directly (not the OpenAI shim) because Anthropic keeps
`system` as a top-level field and streams `content_block_delta` events rather
than OpenAI-style `delta.content`. Embeddings are not exposed by the public API,
so this provider advertises only chat + stream.
"""

from __future__ import annotations

import json
import os

from ._async import run_thread, stream_lines
from ._http import post_json, post_stream
from .base import CAP_CHAT, CAP_STREAM, Message, ProviderHealth, Usage

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-0"


class AnthropicProvider:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        api_key_env: str = "ANTHROPIC_API_KEY",
    ) -> None:
        self.name = "anthropic"
        self.api_key = api_key or os.environ.get(api_key_env)
        self.api_key_env = api_key_env
        self.default_model = model

    # ── interface ────────────────────────────────────────────────────────

    def capabilities(self) -> set[str]:
        return {CAP_CHAT, CAP_STREAM}

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": API_VERSION,
        }

    def health(self) -> ProviderHealth:
        from time import monotonic

        if not self.api_key:
            return ProviderHealth(available=False, detail="no API key configured")
        try:
            start = monotonic()
            post_json(
                API_URL, {"model": self.default_model, "max_tokens": 1,
                          "messages": [{"role": "user", "content": "hi"}]},
                headers=self._headers(), timeout=15, retries=0,
            )
            return ProviderHealth(available=True, latency_ms=(monotonic() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(available=False, detail=str(exc))

    async def chat(self, messages, model: str = "", **opts) -> "object":
        from .base import ChatResult

        model = model or self.default_model
        system, payload_msgs = _split_system(messages)
        payload = {
            "model": model,
            "max_tokens": int(opts.get("max_tokens", 1024)),
            "messages": payload_msgs,
            "temperature": float(opts.get("temperature", 0.2)),
        }
        if system:
            payload["system"] = system
        data = await run_thread(
            post_json, API_URL, payload,
            headers=self._headers(), timeout=int(opts.get("timeout", 120)), retries=1,
        )
        text = "".join(b.get("text", "") for b in data.get("content", []))
        usage = data.get("usage", {})
        return ChatResult(
            text=text, model=data.get("model", model),
            usage=Usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                        usage.get("input_tokens", 0) + usage.get("output_tokens", 0)),
            finish_reason=data.get("stop_reason"),
        )

    async def stream(self, messages, model: str = "", **opts):
        from .base import StreamChunk

        model = model or self.default_model
        system, payload_msgs = _split_system(messages)
        payload = {
            "model": model,
            "max_tokens": int(opts.get("max_tokens", 1024)),
            "messages": payload_msgs,
            "stream": True,
            "temperature": float(opts.get("temperature", 0.2)),
        }
        if system:
            payload["system"] = system
        async for raw in stream_lines(
            post_stream, API_URL, payload,
            headers=self._headers(), timeout=int(opts.get("timeout", 180)),
        ):
            raw = raw.strip()
            if not raw.startswith("data:"):
                continue
            event = raw[len("data:"):].strip()
            if event == "[DONE]":
                break
            try:
                obj = json.loads(event)
            except json.JSONDecodeError:
                continue
            etype = obj.get("type")
            if etype == "content_block_delta":
                delta = obj.get("delta", {}).get("text")
                if delta:
                    yield StreamChunk(delta=delta)
            elif etype == "message_stop":
                yield StreamChunk(delta="", finish_reason="stop")


def _split_system(messages: list[Message]) -> tuple[str, list[dict]]:
    system_parts: list[str] = []
    payload: list[dict] = []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
        else:
            payload.append({"role": m.role, "content": m.content})
    return "\n\n".join(system_parts), payload
