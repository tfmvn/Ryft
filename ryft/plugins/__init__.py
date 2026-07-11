"""Plugin system.

`spec` defines what a plugin is; `api` is the facade handed to plugins; `manager`
discovers and loads them from entry points and plugin directories.
"""

from __future__ import annotations

from .api import PluginAPI
from .manager import PluginManager
from .spec import PluginMeta, Plugin, RyftPlugin

__all__ = ["PluginAPI", "PluginManager", "PluginMeta", "Plugin", "RyftPlugin"]
