"""Provider registry: holds constructed providers, assigns them to roles, and
negotiates capability at runtime.

Roles (commit/analyze/review/chat/embed/agent) are mapped to
"provider:model" strings in config. The registry resolves each to a real
provider instance + model, verifies the provider actually supports the needed
capability, and falls back gracefully when it doesn't (e.g. no embedding
provider → semantic search becomes grep).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .base import (
    ALL_ROLES, AIProvider, CAP_EMBED, CAP_STREAM, ProviderHealth,
    ROLE_AGENT, ROLE_ANALYZE, ROLE_CHAT, ROLE_COMMIT, ROLE_EMBED, ROLE_REVIEW,
)

logger = logging.getLogger(__name__)


@dataclass
class Resolved:
    provider: Any
    model: str


class ProviderRegistry:
    """Owns provider instances and resolves roles → (provider, model)."""

    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}
        # role -> "provider_name" and role -> "model" (from config)
        self._role_provider: dict[str, str] = {}
        self._role_model: dict[str, str] = {}

    # ── registration ──────────────────────────────────────────────────────

    def register(self, provider: AIProvider) -> None:
        self._providers[provider.name] = provider
        logger.debug("Registered provider %s (caps=%s)", provider.name, sorted(provider.capabilities()))

    def set_role(self, role: str, assignment: str) -> None:
        """assignment is "provider:model" or just "provider"."""
        if ":" in assignment:
            name, model = assignment.split(":", 1)
        else:
            name, model = assignment, ""
        self._role_provider[role] = name.strip()
        self._role_model[role] = model.strip()

    def configure_roles(self, roles: dict[str, str]) -> None:
        for role, assignment in roles.items():
            if role in ALL_ROLES:
                self.set_role(role, assignment)

    # ── resolution ────────────────────────────────────────────────────────

    def resolve(self, role: str) -> Resolved | None:
        name = self._role_provider.get(role)
        if not name or name not in self._providers:
            return None
        provider = self._providers[name]
        model = self._role_model.get(role) or ""
        return Resolved(provider=provider, model=model)

    def provider(self, name: str) -> AIProvider | None:
        return self._providers.get(name)

    def list(self) -> list[AIProvider]:
        return list(self._providers.values())

    # ── capability negotiation ────────────────────────────────────────────

    def can(self, role: str, capability: str) -> bool:
        resolved = self.resolve(role)
        if resolved is None:
            return False
        return capability in resolved.provider.capabilities()

    def embed_provider(self) -> Resolved | None:
        """The provider responsible for embeddings (role=embed)."""
        return self.resolve(ROLE_EMBED)

    def health(self) -> dict[str, ProviderHealth]:
        out: dict[str, ProviderHealth] = {}
        for name, provider in self._providers.items():
            try:
                out[name] = provider.health()
            except Exception as exc:  # noqa: BLE001 - health must never raise
                out[name] = ProviderHealth(available=False, detail=str(exc))
        return out

    # Convenience capability queries used by commands.
    def supports_stream(self, role: str) -> bool:
        return self.can(role, CAP_STREAM)

    def supports_embed(self) -> bool:
        return self.can(ROLE_EMBED, CAP_EMBED)
