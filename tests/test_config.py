"""Tests for the config facade (ryft.config) and the v2 loader/schema."""

from pathlib import Path

import pytest

import ryft.config as config_mod
from ryft.core.config.schema import IgnoreConfig

REPO = Path(__file__).resolve().parents[1]


def test_find_root_resolves_repo() -> None:
    root = config_mod.find_root(REPO)
    assert root is not None
    assert root == REPO
    assert (root / "pyproject.toml").exists()


def test_load_config_returns_populated_config() -> None:
    root = config_mod.find_root(REPO)
    cfg = config_mod.load_config(root)
    assert cfg is not None
    assert cfg.root is not None
    assert cfg.providers is not None
    assert cfg.providers.roles is not None

    assert cfg.ollama is not None


@pytest.mark.parametrize(
    "path,extra,expected",
    [
        ("sub/__pycache__/x.py", (), True),
        ("docs/progress.md", (), False),
        (".ryft/knowledge.db", (), True),
        ("secret/x.py", ("secret",), True),
        ("ryft/ai.py", (), True),
    ],
)
def test_is_ignored_list_patterns(path: str, extra: tuple, expected: bool) -> None:
    assert config_mod.is_ignored(REPO / path, REPO, list(extra)) is expected


def test_is_ignored_accepts_ignoreconfig() -> None:
    ic = IgnoreConfig(patterns=["secret"])
    assert config_mod.is_ignored(REPO / "secret" / "x.py", REPO, ic) is True
    assert config_mod.is_ignored(REPO / "docs" / "progress.md", REPO, ic) is False


def test_is_ignored_accepts_none() -> None:
    assert config_mod.is_ignored(REPO / "docs" / "progress.md", REPO, None) is False


def test_set_model_updates_provider_roles() -> None:
    cfg = config_mod.load_config(config_mod.find_root(REPO))
    config_mod.set_model(cfg, "llama3:latest")
    assert cfg.providers.roles.commit == "ollama:llama3:latest"
    assert cfg.ollama.commit_model == "llama3:latest"
