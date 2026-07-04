"""Help / status / activity / exit commands + the dispatch entry points.

``dispatch`` and ``dispatch_argv`` live here because they're the glue
between the registry and the REPL/CLI; they resolve a name to a
``CommandSpec`` and invoke its handler with the same try/except guard the
old single-file ``commands.py`` used.
"""
from __future__ import annotations

import logging

from .. import ui
from .registry import all_commands, command

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@command("help", "Show available commands.", usage=["/help"])
def cmd_help(ctx, args: list[str]) -> None:
    # COMMANDS is read at call time so the table is always fully
    # registered, regardless of which handler module imported first.
    COMMANDS = all_commands()
    if args:
        name = args[0].lstrip("/")
        spec = COMMANDS.get(name)
        if spec is None:
            ui.error(f"No such command: /{name}")
            return
        ui.render_help_command(spec)
    else:
        ui.render_help_index(COMMANDS)


@command("status", "Show project status.", usage=["/status"])
def cmd_status(ctx, args: list[str]) -> None:
    ui.render_dashboard(ctx)


@command("activity", "Show the activity feed.", usage=["/activity"])
def cmd_activity(ctx, args: list[str]) -> None:
    ui.render_activity_full(ctx)


@command("exit", "Exit Ryft.", usage=["/exit"], aliases=("quit",))
def cmd_exit(ctx, args: list[str]) -> None:
    if ctx.sync and ctx.sync.is_running:
        ctx.sync.stop()
    ctx.running = False


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _execute(ctx, name: str, args: list[str], label: str) -> None:
    spec = all_commands().get(name)
    if spec is None:
        ui.error(f"Unknown command: {label}. Try /help.")
        return
    try:
        spec.handler(ctx, args)
    except Exception as exc:
        # Command handlers are a plugin-style registry covering ~25
        # unrelated features — this top-level catch-all is the last line
        # of defense against a handler bug taking down the whole REPL, so
        # it stays broad by design, but the failure is now logged (with a
        # traceback) instead of only ever surfacing as a one-line message
        # to the user.
        logger.exception("Command %s failed", label)
        ui.error(f"{label} failed: {exc}")


def dispatch(ctx, raw: str) -> None:
    """Dispatch a single typed REPL line, e.g. '/commit' or '/diff foo.py'."""
    raw = raw.strip()
    if not raw: return
    if not raw.startswith("/"):
        ui.warn("Ryft only understands slash commands. Try /help.")
        return
    parts = raw[1:].split()
    if not parts: return
    name, args = parts[0].lower(), parts[1:]
    _execute(ctx, name, args, f"/{name}")


def dispatch_argv(ctx, argv: list[str]) -> None:
    """Dispatch a command from already-split argv, e.g. `ryft diff foo.py`
    from the shell. Unlike dispatch(), this never re-joins/re-splits the
    arguments, so a value containing spaces (a quoted filename, a commit
    message, ...) survives intact."""
    if not argv: return
    name, args = argv[0].lower(), argv[1:]
    _execute(ctx, name, args, name)
