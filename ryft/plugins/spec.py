"""Plugin contracts.

A plugin is any object that exposes `meta` (a `PluginMeta`) and a `register`
method taking a `PluginAPI`. We use a Protocol (not a base class) so plugins
needn't subclass anything — a plain module with `meta` + `register` qualifies.
`Plugin` is offered as an opt-in convenience base for authors who want defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .api import PluginAPI


@dataclass
class PluginMeta:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""


@runtime_checkable
class RyftPlugin(Protocol):
    meta: PluginMeta

    def register(self, api: "PluginAPI") -> None: ...


class Plugin:
    """Convenience base: set `meta` then implement `register`."""

    meta: PluginMeta

    def register(self, api: "PluginAPI") -> None:  # pragma: no cover - override
        raise NotImplementedError
