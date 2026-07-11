"""Configuration: schema (plain dataclasses) + loaders.

Importing this package is instant and dependency-free.
"""

from __future__ import annotations

from .loader import (
    DEFAULT_TOML, find_root, init_config, load_config, validate_config,
)
from .schema import (
    AnthropicBackendConfig, Config, FormatterConfig, GitConfig, GithubConfig,
    GoogleBackendConfig, IgnoreConfig, OllamaBackendConfig, OpenAIBackendConfig,
    ProjectConfig, ProviderRoleConfig, ProvidersConfig, ServicesConfig,
    SyncConfig, ThemeConfig,
)

__all__ = [
    "DEFAULT_TOML", "find_root", "init_config", "load_config", "validate_config",
    "AnthropicBackendConfig", "Config", "FormatterConfig", "GitConfig",
    "GithubConfig", "GoogleBackendConfig", "IgnoreConfig", "OllamaBackendConfig",
    "OpenAIBackendConfig", "ProjectConfig", "ProviderRoleConfig",
    "ProvidersConfig", "ServicesConfig", "SyncConfig", "ThemeConfig",
]
