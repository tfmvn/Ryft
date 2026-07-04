"""watch/sync commands -- thin wrappers around `SyncController`
(ryft/sync.py). All the actual debouncing/watchdog/commit-pipeline work
already lives there; these handlers just start/stop it and report state.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import register

if TYPE_CHECKING:
    from ..models import AppContext


@register(
    "watch",
    description="Watch this folder and auto-commit on save",
    usage=["/watch"],
)
def cmd_watch(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    if not ctx.sync.is_running:
        msg = ctx.sync.start()
        (ui.success if ctx.sync.is_running else ui.warn)(msg)
        if not ctx.sync.is_running:
            return

    ui.info("Watching for changes — press Ctrl+C to stop.")
    try:
        while ctx.sync.is_running:
            import time
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if ctx.sync.is_running:
            ui.info(ctx.sync.stop())


@register(
    "sync",
    description="Control background sync: start / stop / status",
    usage=["/sync start", "/sync stop", "/sync status"],
)
def cmd_sync(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    sub = args[0].lower() if args else "status"

    if sub == "start":
        msg = ctx.sync.start()
        (ui.success if ctx.sync.is_running else ui.warn)(msg)
    elif sub == "stop":
        ui.info(ctx.sync.stop())
    elif sub == "status":
        ui.info("running" if ctx.sync.is_running else "stopped")
    else:
        ui.error(f"Unknown /sync subcommand: {sub}  (use start/stop/status)")
