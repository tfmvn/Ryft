"""Google (Gemini) provider.

Uses the generative language v1beta API. Chat/stream go through
`models/{model}:generateContent` / `:streamGenerateContent?alt=sse`; embeddings
through `models/{model}:embedContent`. `system` is a top-level
`systemInstruction`. Capabilities: chat, stream, embed.
"""

from __future__ import annotations

import json
import os

from ._async import run_thread, stream_lines
from ._http import post_json, post_stream
from .base import CAP_CHAT, CAP_EMBED, CAP_STREAM, Message, ProviderHealth, Usage

BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-1.5-flash"


class GoogleProvider:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        api_key_env: str = "GOOGLE_API_KEY",
    ) -> None:
        self.name = "google"
        self.api_key = api_key or os.environ.get(api_key_env)
        self.api_key_env = api_key_env
        self.default_model = model

    # ── interface ────────────────────────────────────────────────────────

    def capabilities(self) -> set[str]:
        return {CAP_CHAT, CAP_EMBED, CAP_STREAM}

    def _url(self, suffix: str) -> str:
        key = self.api_key or ""
        return f"{BASE}/{suffix}?key={key}"

    def health(self) -> ProviderHealth:
        from time import monotonic

        if not self.api_key:
            return ProviderHealth(available=False, detail="no API key configured")
        try:
            start = monotonic()
            post_json(
                self._url(f"models/{self.default_model}:generateContent"),
                {"contents": [{"role": "user", "parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 1}},
                timeout=15, retries=0,
            )
            return ProviderHealth(available=True, latency_ms=(monotonic() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(available=False, detail=str(exc))

    def _body(self, messages, **opts) -> dict:
        system_parts, contents = [], []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m.content}]})
        body = {"contents": contents}
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        gen = {"temperature": float(opts.get("temperature", 0.2))}
        if opts.get("max_tokens"):
            gen["maxOutputTokens"] = int(opts["max_tokens"])
        body["generationConfig"] = gen
        return body

    async def chat(self, messages, model: str = "", **opts) -> "object":
        from .base import ChatResult

        model = model or self.default_model
        data = await run_thread(
            post_json, self._url(f"models/{model}:generateContent"), self._body(messages, **opts),
            timeout=int(opts.get("timeout", 120)), retries=1,
        )
        text = _text_from(data)
        um = data.get("usageMetadata", {})
        pt, ct = um.get("promptTokenCount", 0), um.get("candidatesTokenCount", 0)
        return ChatResult(text=text, model=model, usage=Usage(pt, ct, pt + ct),
                          finish_reason=_finish(data))

    async def stream(self, messages, model: str = "", **opts):
        from .base import StreamChunk

        model = model or self.default_model
        async for raw in stream_lines(
            post_stream, self._url(f"models/{model}:streamGenerateContent?alt=sse"),
            self._body(messages, **opts), timeout=int(opts.get("timeout", 180)),
        ):
            raw = raw.strip()
            if not raw.startswith("data:"):
                continue
            payload = raw[len("data:"):].strip()
            if payload in ("[DONE]", ""):
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            text = _text_from(obj)
            if text:
                yield StreamChunk(delta=text)
            fr = _finish(obj)
            if fr:
                yield StreamChunk(delta="", finish_reason=fr)

    async def embed(self, texts: list[str], model: str = "", **opts) -> list[list[float]]:
        model = model or "text-embedding-004"
        out: list[list[float]] = []
        for text in texts:
            data = await run_thread(
                post_json, self._url(f"models/{model}:embedContent"),
                {"content": {"parts": [{"text": text}]}}, timeout=int(opts.get("timeout", 60)), retries=1,
            )
            vals = data.get("embedding", {}).get("values")
            if vals:
                out.append(vals)
        return out


def _text_from(data: dict) -> str:
    parts = []
    for cand in data.get("candidates", []):
        for p in cand.get("content", {}).get("parts", []):
            parts.append(p.get("text", ""))
    return "".join(parts)


def _finish(data: dict) -> str | None:
    for cand in data.get("candidates", []):
        fr = cand.get("finishReason")
        if fr and fr != "MAX_TOKENS":
            return "stop"
        if fr == "MAX_TOKENS":
            return "length"
    return None
