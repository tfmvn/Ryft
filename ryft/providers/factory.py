"""Provider factory: turns configuration into a live `ProviderRegistry`.

Two sources feed the registry:

1. **Typed backends** from `ProvidersConfig` — `ollama`, `openai`, `anthropic`,
   `google` — each constructed only when enabled and (for keyed backends)
   configured.
2. **Built-in OpenAI-compatible vendors** — Together, OpenRouter, Groq,
   Fireworks, DeepInfra, NVIDIA NIM, and LM Studio — registered automatically
   when their API key is present (LM Studio is local, so always registered).

Every one of these REST providers shares `OpenAICompatibleProvider`; only the
`base_url` / key env / default model differ, so there is no per-vendor code.
"""

from __future__ import annotations

import os

from .anthropic import AnthropicProvider
from .base import ALL_ROLES, AIProvider
from .google import GoogleProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider
from .registry import ProviderRegistry

# name -> (base_url, api_key_env, default_model)
_OAI_VENDORS: dict[str, tuple[str, str, str]] = {
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY", "mistralai/Mixtral-8x7B-Instruct-v0.1"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "openai/gpt-4o-mini"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
    "deepinfra": ("https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY", "meta-llama/Llama-3.3-70B-Instruct"),
    "nvidia_nim": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", "meta/llama-3.3-70b-instruct"),
}


def build_registry(providers_config, ollama_config, openai_config, anthropic_config, google_config) -> ProviderRegistry:
    """Construct and role-configure the provider registry.

    Parameters are the relevant sub-configs from `Config` (kept explicit to
    avoid a hard dependency on the full config object shape here).
    """
    reg = ProviderRegistry()

    if getattr(ollama_config, "enabled", False):
        reg.register(OllamaProvider(
            host=getattr(ollama_config, "host", None) or "http://localhost:11434",
            models=getattr(ollama_config, "models", None) or None,
        ))

    if getattr(openai_config, "enabled", False):
        reg.register(_openai_from_config(openai_config))

    if getattr(anthropic_config, "enabled", False):
        reg.register(AnthropicProvider(
            api_key=getattr(anthropic_config, "api_key", None),
            model=getattr(anthropic_config, "model", None) or "claude-sonnet-4-0",
        ))

    if getattr(google_config, "enabled", False):
        reg.register(GoogleProvider(
            api_key=getattr(google_config, "api_key", None),
            model=getattr(google_config, "model", None) or "gemini-1.5-flash",
        ))

    # Auto-register OpenAI-compatible vendors that have credentials present.
    for name, (base_url, env, default_model) in _OAI_VENDORS.items():
        if os.environ.get(env):
            reg.register(OpenAICompatibleProvider(
                name, base_url, api_key_env=env, default_model=default_model,
            ))

    # LM Studio is local — always available for discovery.
    reg.register(OpenAICompatibleProvider(
        "lm_studio", "http://localhost:1234/v1", api_key=None, default_model="",
    ))

    # Apply role assignments from config (role -> "provider:model").
    roles = getattr(providers_config, "roles", None)
    if roles is not None:
        reg.configure_roles({r: getattr(roles, r) for r in ALL_ROLES if getattr(roles, r, None)})

    return reg


def _openai_from_config(cfg) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        "openai",
        base_url=getattr(cfg, "base_url", None) or "https://api.openai.com/v1",
        api_key=getattr(cfg, "api_key", None),
        api_key_env="OPENAI_API_KEY",
        default_model=getattr(cfg, "default_model", None) or "gpt-4o-mini",
    )
