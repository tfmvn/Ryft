"""Tests for the provider registry (ryft.providers) and the Ollama client."""

from pathlib import Path

import pytest

import ryft.config as config_mod
from ryft.providers import build_registry

REPO = Path(__file__).resolve().parents[1]


def _registry():
    cfg = config_mod.load_config(config_mod.find_root(REPO))
    return build_registry(
        cfg.providers,
        cfg.providers.ollama,
        cfg.providers.openai,
        cfg.providers.anthropic,
        cfg.providers.google,
    )


def test_registry_builds_and_lists() -> None:
    reg = _registry()
    providers = reg.list()
    assert providers
    names = {p.name for p in providers}
    assert "ollama" in names


def test_registry_health_is_dict() -> None:
    reg = _registry()
    health = reg.health()
    assert isinstance(health, dict)
    assert "ollama" in health


def test_ollama_reports_chat_capability() -> None:

    from ryft.providers.ollama import CAP_CHAT

    reg = _registry()
    ollama = reg.provider("ollama")
    assert ollama is not None
    assert CAP_CHAT in ollama.capabilities()


def test_registry_can_and_supports_embed() -> None:
    reg = _registry()

    assert isinstance(reg.can("commit", "chat"), bool)
    assert isinstance(reg.supports_embed(), bool)
