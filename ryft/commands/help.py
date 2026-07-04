"""Shell-level commands: /help, /activity, /exit, /quit."""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import REGISTRY, register

if TYPE_CHECKING:
    from ..models import AppContext


@register(
    "help",
    description="Show all commands, or details for one command",
    usage=["/help", "/help <command>"],
)
def cmd_help(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    if args:
        spec = REGISTRY.get(args[0].lstrip("/"))
        if spec is None:
            ui.error(f"Unknown command: {args[0]}")
            return
        ui.render_help_command(spec)
        return
    ui.render_help_index(REGISTRY)


@register("activity", description="Show the full activity log")
def cmd_activity(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    ui.render_activity_full(ctx)


@register("exit", description="Exit the Ryft shell", aliases=["quit"])
def cmd_exit(ctx: "AppContext", args: list[str]) -> None:
    ctx.running = False
