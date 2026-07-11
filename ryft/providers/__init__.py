"""AI provider layer.

Public surface: the `AIProvider` interface (`base`), the `ProviderRegistry`
(`registry`), and `build_registry` (`factory`) which turns config into a live
registry. Concrete backends (ollama, openai_compatible, anthropic, google) are
imported lazily by the factory — importing this package never opens a socket.
"""

from __future__ import annotations

from .base import (
    AIProvider, CAP_CHAT, CAP_EMBED, CAP_REASONING, CAP_STREAM, CAP_TOOLS,
    ChatResult, Message, ProviderError, ProviderHealth, ROLE_AGENT, ROLE_ANALYZE,
    ROLE_CHAT, ROLE_COMMIT, ROLE_EMBED, ROLE_REVIEW, StreamChunk, Usage,
)
from .registry import ProviderRegistry, Resolved

__all__ = [
    "AIProvider", "CAP_CHAT", "CAP_EMBED", "CAP_REASONING", "CAP_STREAM", "CAP_TOOLS",
    "ChatResult", "Message", "ProviderError", "ProviderHealth",
    "ROLE_AGENT", "ROLE_ANALYZE", "ROLE_CHAT", "ROLE_COMMIT", "ROLE_EMBED", "ROLE_REVIEW",
    "StreamChunk", "Usage", "ProviderRegistry", "Resolved", "build_registry",
]


def build_registry(*args, **kwargs):  # re-exported lazily to keep import cheap
    from .factory import build_registry as _build
    return _build(*args, **kwargs)
