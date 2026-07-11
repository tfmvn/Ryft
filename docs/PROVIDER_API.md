# Ryft — Provider API

AI providers live behind one interface in `ryft/providers/`. A provider
declares its **capabilities**; the registry picks the right provider for each
**role** at runtime. Users can swap providers per role without touching code.

---

## The interface

```python
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol

@dataclass
class Message:
    role: str            # "system" | "user" | "assistant"
    content: str
    name: str | None = None

@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

@dataclass
class ChatResult:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None

@dataclass
class StreamChunk:
    delta: str
    finish_reason: str | None = None

@dataclass
class ProviderHealth:
    available: bool
    latency_ms: float | None = None
    detail: str | None = None

class AIProvider(Protocol):
    name: str
    def capabilities(self) -> set[str]: ...        # {"chat","stream","embed","reasoning","tools"}
    async def chat(self, messages: list[Message], **opts) -> ChatResult: ...
    async def stream(self, messages: list[Message], **opts) -> AsyncIterator[StreamChunk]: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    def health(self) -> ProviderHealth: ...
```

`opts` is provider-specific and passed through: `temperature`, `max_tokens`,
`top_p`, `thinking` (Anthropic), `seed`, etc. Providers ignore keys they
don't understand.

---

## Capabilities

A provider advertises what it can do. The registry uses this to fail fast with
a clear message instead of a network error.

| Capability | Used by |
| --- | --- |
| `chat` | every role |
| `stream` | live commit/review UI |
| `embed` | semantic search |
| `reasoning` | architecture/planning agents |
| `tools` | multi-agent workflows (future) |

---

## Built-in providers

| Class | Backend | Capabilities |
| --- | --- | --- |
| `OllamaProvider` | local Ollama `/api` | chat, stream, embed |
| `OpenAICompatibleProvider` | any `/v1` endpoint | chat, stream, embed |
| `AnthropicProvider` | Messages API | chat, stream, reasoning |
| `GoogleProvider` | Gemini | chat, stream |

The OpenAI-compatible base covers the bulk of the market — point it at any
`/v1` endpoint (OpenAI, LM Studio, Together, OpenRouter, Groq, Fireworks,
DeepInfra, NVIDIA NIM, …). `LM Studio` is wired up out of the box via this
base, targeting `http://localhost:1234/v1`. To add another OpenAI-compatible
backend, set its `[providers.<name>]` section with `api_key_env` and `base_url`
in config; the factory builds an `OpenAICompatibleProvider` for it.

---

## Roles

A *role* is a task; a *provider:model* assignment fulfills it. Config maps
roles → assignments:

```toml
[providers]
commit  = "ollama:qwen3:0.6b"
analyze = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
review  = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
chat    = "anthropic:claude-opus-4-8"
embed   = "openai:text-embedding-3-small"
agent   = "anthropic:claude-opus-4-8"
```

Roles: `commit`, `analyze`, `review`, `chat`, `embed`, `agent`.

---

## Writing a provider plugin

Implement `AIProvider` and register it via entry point
(`ryft.providers = mymod:MyProvider`) or drop it in
`~/.config/ryft/plugins`. The loader calls `capabilities()` and `health()`
once at discovery; `chat`/`stream`/`embed` only when a role selects it.

```python
from ryft.providers.base import AIProvider, Message, ChatResult, ProviderHealth

class MyProvider:
    name = "mycloud"
    def capabilities(self): return {"chat", "stream"}
    def health(self) -> ProviderHealth:
        ...
    async def chat(self, messages, **opts) -> ChatResult:
        ...
```

Conventions:

- **Never block the UI.** `chat`/`stream`/`embed` are async; the calling
  command awaits them inside a worker.
- **Retry with backoff** on transient 5xx/429; surface a typed error for auth.
- **Respect `opts`**; don't invent required fields.
- **Graceful degradation:** if `embed` is unavailable, semantic search falls
  back to grep automatically.
