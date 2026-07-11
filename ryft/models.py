"""Canonical shared data shapes for Ryft (v2).

This module is a thin re-export hub. The single sources of truth live in
``ryft.core``:

  * ``ryft.core.config.schema`` — ``Config`` and all sub-configs
  * ``ryft.core.context``       — ``AppContext`` (the wiring bag)
  * ``ryft.core.models``        — ``ActivityEvent``, ``SyncStatus``,
    ``CommandSpec``, ``ActivityFeed``

Legacy import paths (``from ryft.models import Config`` / ``AppContext`` /
``ActivityEvent`` …) keep resolving here after the v2 consolidation, so no
caller had to change. New code should import from ``ryft.core.*`` directly.
"""

from __future__ import annotations

from .core.config.schema import (  # noqa: F401
    Config,
    FormatterConfig,
    GitConfig,
    GithubConfig,
    IgnoreConfig,
    OllamaBackendConfig,
    OllamaConfig,
    ProviderRoleConfig,
    ProvidersConfig,
    ProjectConfig,
    ServicesConfig,
    SyncConfig,
    ThemeConfig,
)
from .core.context import AppContext  # noqa: F401
from .core.models import (  # noqa: F401
    ActivityEvent,
    ActivityFeed,
    CommandSpec,
    SyncStatus,
)

__all__ = [
    "Config", "FormatterConfig", "GitConfig", "GithubConfig", "IgnoreConfig",
    "OllamaBackendConfig", "OllamaConfig", "ProviderRoleConfig",
    "ProvidersConfig", "ProjectConfig", "ServicesConfig", "SyncConfig",
    "ThemeConfig", "AppContext", "ActivityEvent", "ActivityFeed",
    "CommandSpec", "SyncStatus",
]
