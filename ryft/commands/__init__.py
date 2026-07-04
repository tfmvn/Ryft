"""Command registry + dispatch.

This package replaces the old single-file ``ryft/commands.py`` and its
long if/elif chain. Every command is a small, self-registering handler:

    from . import register

    @register("doctor", description="Run health checks")
    def cmd_doctor(ctx, args):
        ...

Submodules call ``register(...)`` at import time (a decorator, same
pattern as ``ryft.lang``'s formatter registry); this file's only job is
to import every submodule for that side effect and expose
``dispatch``/``dispatch_argv`` to the rest of the app.

Layout (mirrors ``ryft/ui``'s split):
  commit.py  -> commit, push, pull, diff, log, status, git
  sync.py    -> watch, sync
  doctor.py  -> doctor
  config.py  -> config, init, root, tree, files
  format.py  -> format
  ai.py      -> analyze, review, message, model
  help.py    -> help, activity, exit, quit

``ui`` is imported lazily inside handlers where needed (mirroring the
lazy ``commands`` import in ``ui/dashboard.py``) to avoid re-creating the
``ui <-> commands`` circular dependency the old single-file layout had.
"""
from __future__ import annotations

import shlex
from typing import Callable, TYPE_CHECKING

from ..models import CommandSpec

if TYPE_CHECKING:
    from ..models import AppContext

__all__ = ["register", "REGISTRY", "dispatch", "dispatch_argv"]

# name -> CommandSpec. Populated by every submodule's @register calls
# below, in whatever order they happen to import in — dict identity
# means later imports never invalidate earlier registrations.
REGISTRY: dict[str, CommandSpec] = {}

# alias -> canonical name (e.g. "quit" -> "exit")
_ALIASES: dict[str, str] = {}


def register(
    name: str,
    *,
    description: str,
    usage: list[str] | None = None,
    examples: list[str] | None = None,
    aliases: list[str] | None = None,
) -> Callable[[Callable], Callable]:
    """Decorator: register a handler ``fn(ctx, args)`` as the command
    ``/name``. Returns the function unchanged so it stays plainly
    callable (and testable) on its own."""

    def _decorator(fn: Callable) -> Callable:
        REGISTRY[name] = CommandSpec(
            name=name,
            handler=fn,
            description=description,
            usage=usage or [],
            examples=examples or [],
        )
        for alias in aliases or []:
            _ALIASES[alias] = name
        return fn

    return _decorator


def _resolve(name: str) -> CommandSpec | None:
    name = name.lower()
    if name in REGISTRY:
        return REGISTRY[name]
    return REGISTRY.get(_ALIASES.get(name, ""))


def _run(ctx: "AppContext", name: str, args: list[str], *, unknown_hint: str) -> None:
    from .. import ui

    spec = _resolve(name)
    if spec is None:
        ui.error(f"Unknown command: {name}  ({unknown_hint})")
        return
    spec.handler(ctx, args)


def dispatch(ctx: "AppContext", raw: str) -> None:
    """Dispatch one REPL line, e.g. ``/commit foo.py`` or ``help``.

    A leading ``/`` is optional and stripped if present; arguments are
    split shell-style so quoted filenames survive.
    """
    from .. import ui

    raw = raw.strip()
    if not raw:
        return
    if raw.startswith("/"):
        raw = raw[1:]
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        ui.error(f"Could not parse command: {exc}")
        return
    if not parts:
        return
    name, args = parts[0], parts[1:]
    _run(ctx, name, args, unknown_hint="try /help")


def dispatch_argv(ctx: "AppContext", argv: list[str]) -> None:
    """Dispatch one non-interactive CLI invocation, e.g.
    ``ryft doctor fix`` -> argv == ["doctor", "fix"]."""
    if not argv:
        return
    name, args = argv[0], argv[1:]
    _run(ctx, name, args, unknown_hint="try 'ryft --help'")


# ── Side-effect imports: each module below calls register() for the ────────
# commands it owns. Order doesn't matter — see REGISTRY docstring above.
from . import commit, sync, doctor, config, format, ai, help  # noqa: E402,F401
