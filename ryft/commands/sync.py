"""Sync & watch commands."""
from __future__ import annotations

from .. import git, recovery, ui
from .registry import command


@command(
    "watch",
    "Watch this folder and auto-commit.",
    usage=["/watch", "ryft watch"],
)
def cmd_watch(ctx, args: list[str]) -> None:
    """Foreground sync: watch this folder and auto-commit on save until
    interrupted. This is what `ryft watch` runs from the shell."""
    cfg = ctx.config
    if not git.is_repo(cfg.root) and not recovery.ensure_git_repo(cfg.root):
        ui.warn("Watch needs a git repository. Run '/doctor fix' when you're ready.")
        return

    msg = ctx.sync.start()
    if not ctx.sync.is_running:
        ui.error(msg)
        return
    ui.success(f"Watching {cfg.root} — press Ctrl+C to stop.")
    try:
        while ctx.sync.is_running:
            import time as _time
            _time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        ui.warn(ctx.sync.stop())


@command("sync", "Start/stop sync.", usage=["/sync start|stop"])
def cmd_sync(ctx, args: list[str]) -> None:
    sub = args[0] if args else "status"
    if sub == "start":
        cfg = ctx.config
        if not git.is_repo(cfg.root) and not recovery.ensure_git_repo(cfg.root):
            ui.warn("Sync needs a git repository. Run '/doctor fix' when you're ready.")
            return
        if cfg.sync.debounce_seconds < 10:
            ui.warn(f"debounce_seconds={cfg.sync.debounce_seconds} is very low — may generate many commits.")
        msg = ctx.sync.start()
        (ui.success if ctx.sync.is_running else ui.warn)(msg)
    elif sub == "stop":
        ui.warn(ctx.sync.stop())
    elif sub == "status":
        state = "running" if ctx.sync.is_running else "stopped"
        ui.info(f"Sync is {state} (debounce {ctx.config.sync.debounce_seconds}s, push={ctx.config.sync.push})")
    else:
        ui.error("Usage: /sync start|stop|status")
