"""The AI provider interface and shared value types.

One interface (`AIProvider`), many backends. A provider *declares*
capabilities; the registry negotiates which provider fulfills each role.
Backend clients use `urllib` (no heavy HTTP dependency) and run their network
calls in a worker thread via `asyncio.to_thread`, so they never block the UI
thread. Errors are normalized into `ProviderError` with a `.kind`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
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


class ProviderError(Exception):
    def __init__(self, message: str, *, kind: str = "unknown", status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind          # auth | rate_limit | timeout | unavailable | unknown
        self.status = status


class AIProvider(Protocol):
    """A backend that can answer chat/embed requests.

    Implementations must be safe to construct without network access. Network
    calls happen only in `chat`/`stream`/`embed`.
    """

    name: str

    def capabilities(self) -> set[str]:
        """Return a subset of {"chat","stream","embed","reasoning","tools"}."""
        ...

    def health(self) -> ProviderHealth:
        """Cheap, synchronous availability check (e.g. a ping)."""
        ...

    async def chat(self, messages: list[Message], **opts: object) -> ChatResult:
        ...

    async def stream(self, messages: list[Message], **opts: object) -> AsyncIterator[StreamChunk]:
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...


# Capability vocabulary — single source of truth.
CAP_CHAT = "chat"
CAP_STREAM = "stream"
CAP_EMBED = "embed"
CAP_REASONING = "reasoning"
CAP_TOOLS = "tools"

ROLE_COMMIT = "commit"
ROLE_ANALYZE = "analyze"
ROLE_REVIEW = "review"
ROLE_CHAT = "chat"
ROLE_EMBED = "embed"
ROLE_AGENT = "agent"

ALL_ROLES = {ROLE_COMMIT, ROLE_ANALYZE, ROLE_REVIEW, ROLE_CHAT, ROLE_EMBED, ROLE_AGENT}
