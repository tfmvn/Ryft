"""Automatic command registration.

Each handler module decorates its functions with ``@command(...)``, which
populates the module-level ``_COMMANDS`` registry. Importing a handler
module (as ``ryft/commands/__init__.py`` does) is enough to register every
command in it — there is no central hand-written ``COMMANDS`` dict to keep
in sync.

Aliases (e.g. ``quit`` → ``exit``) are declared inline on the decorator so
they live next to the handler they mirror.
"""
from __future__ import annotations

from typing import Callable

from ..models import CommandSpec

# name -> CommandSpec (one spec per name; aliases share the same spec object)
_COMMANDS: dict[str, CommandSpec] = {}


def command(
    name: str,
    description: str,
    *,
    usage: list[str] | None = None,
    examples: list[str] | None = None,
    aliases: tuple[str, ...] = (),
) -> Callable:
    """Register *func* as the handler for *name*.

    Replaces the hand-written ``COMMANDS = {...}`` literal from the old
    single-file ``commands.py``. Aliases point additional names at the same
    ``CommandSpec`` (matching the old ``COMMANDS["quit"] = COMMANDS["exit"]``).
    """
    def deco(func):
        spec = CommandSpec(name, func, description, usage or [], examples or [])
        _COMMANDS[name] = spec
        for alias in aliases:
            _COMMANDS[alias] = spec
        return func

    return deco


def all_commands() -> dict[str, CommandSpec]:
    """Snapshot of the registry. Returned by reference — callers read it at
    call time (see ``cmd_help``) so they always see the fully-registered
    table regardless of import order."""
    return _COMMANDS
