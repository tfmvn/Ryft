"""RyftApp REPL shell and render_dashboard.

``commands`` is imported lazily (inside ``RyftApp.run()``) rather than at
module level to break the ``ui ↔ commands`` circular dependency that
existed in the old single-file layout.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import clear

from rich.rule import Rule
from rich.text import Text

from .. import git
from .colors import PTK_STYLE, TEXT_DIM, TEXT_GHOST, TEXT_HI, TEXT_MID, VIOLET, VIOLET_DIM, AMBER, CORAL, MINT, CYAN, _rule, _sp, console
from .icons import _I
from .activity import log_activity

if TYPE_CHECKING:
    from ..models import AppContext

logger = logging.getLogger(__name__)


def render_dashboard(ctx: "AppContext") -> None:
    cfg     = ctx.config
    is_repo = git.is_repo(cfg.root)
    n       = len(git.changed_files(cfg.root)) if is_repo else 0
    ai_ok   = ctx.ai.is_available()
    sync_on = ctx.sync and ctx.sync.is_running

    _rule("status", VIOLET_DIM)
    _sp()

    def _row(icon, label, val, vc):
        row = Text()
        row.append(f"  {icon}  ", style=TEXT_DIM)
        row.append(f"{label:<14}", style=TEXT_DIM)
        row.append(val, style=vc)
        console.print(row)

    _row(_I["git"],    "git",     git.current_branch(cfg.root) if is_repo else "—", CYAN)
    _row(_I["spark"],  "changes", f"{n} modified" if n else "clean", AMBER if n else MINT)
    _row(_I["model"],  "ollama",  "online"  if ai_ok  else "offline", MINT if ai_ok  else CORAL)
    _row(_I["sync"],   "sync",    "running" if sync_on else "stopped", MINT if sync_on else TEXT_DIM)
    _sp()


class RyftApp:
    def __init__(self, ctx: "AppContext", first_run: bool = False) -> None:
        self.ctx = ctx
        self.first_run = first_run
        # The bottom toolbar re-renders on every 0.5s UI tick (see
        # _refresh_loop below) and calls is_repo/current_branch/
        # changed_files every time; without this cache that's 3 fresh
        # `git` subprocesses spawned twice a second just sitting idle at
        # the prompt. invalidate() is called after every dispatched
        # command so the toolbar reflects state changes immediately.
        self._status_cache = git.StatusCache(ctx.config.root)

    def _completer(self) -> NestedCompleter:
        cfg   = self.ctx.config
        cache = self._status_cache
        files = ({c.path: None for c in cache.changed_files()}
                 if cache.is_repo() else {})
        return NestedCompleter.from_nested_dict({
            "/help": None, "/status": None, "/activity": None,
            "/init": None,
            "/watch": None,
            "/sync":    {"start": None, "stop": None, "status": None},
            "/format":  {".": None, "changed": None},
            "/analyze": None,
            "/review":  files or None,
            "/message": files or None,
            "/model":   {"list": None, "current": None},
            "/git":     {"status": None, "diff": None, "log": None,
                         "push": None, "pull": None, "commit": None},
            "/commit": None, "/push": None, "/pull": None,
            "/diff":   files or None,
            "/log": None, "/doctor": None,
            "/config":  {"init": None},
            "/tree": None, "/files": None, "/root": None,
            "/exit": None, "/quit": None,
        })

    def _toolbar(self) -> FormattedText:
        cfg      = self.ctx.config
        cache    = self._status_cache
        is_repo  = cache.is_repo()
        sync_on  = self.ctx.sync and self.ctx.sync.is_running
        branch   = cache.current_branch() if is_repo else "—"
        model    = cfg.ollama.model.split(":")[0]
        sep      = ("class:bottom-toolbar.sep", "  │  ")
        sstatus  = self.ctx.sync_status

        parts: list = [
            ("class:bottom-toolbar", "  "),
            ("class:bottom-toolbar.accent", f"{_I['branch']} "),
            ("class:bottom-toolbar.value", branch),
            sep,
        ]

        if not sync_on:
            n = len(cache.changed_files()) if is_repo else 0
            git_lbl = f"{n} modified" if n else "clean"
            parts += [
                ("class:bottom-toolbar.accent", "⬡ "),
                ("class:bottom-toolbar.value", model),
                sep,
                ("class:bottom-toolbar.accent", f"{_I['sync']} "),
                ("class:bottom-toolbar.value", "off"),
                sep,
                ("class:bottom-toolbar.accent", "◻ "),
                ("class:bottom-toolbar.value", git_lbl),
                ("class:bottom-toolbar", "  "),
            ]
            return FormattedText(parts)

        if sstatus.busy and sstatus.current_file:
            stage = sstatus.current_stage or ""
            if stage == "pushed":
                parts += [
                    ("class:bottom-toolbar.accent", f"{_I['sync']} "),
                    ("class:bottom-toolbar.value", sstatus.current_file),
                    sep,
                    ("class:bottom-toolbar.value", "pushed "),
                    ("class:bottom-toolbar.accent", "✓"),
                    ("class:bottom-toolbar", "  "),
                ]
                return FormattedText(parts)

            stage_idx = {"format": 0, "message": 1, "commit": 2, "push": 3}.get(stage, 0)
            n_stages  = 4
            width     = 8
            filled    = round((stage_idx + 1) / n_stages * width)
            bar       = "█" * filled + "░" * (width - filled)
            parts += [
                ("class:bottom-toolbar.accent", f"{_I['sync']} "),
                ("class:bottom-toolbar.value", sstatus.current_file),
                sep,
                ("class:bottom-toolbar.value", f"[{bar}]"),
                sep,
                ("class:bottom-toolbar.value", stage),
                ("class:bottom-toolbar", "  "),
            ]
            return FormattedText(parts)

        # idle, sync on
        push_lbl = time.strftime("%H:%M", time.localtime(sstatus.last_push_time)) \
            if sstatus.last_push_time else "—"
        parts += [
            ("class:bottom-toolbar.accent", f"{_I['sync']} "),
            ("class:bottom-toolbar.value", "watching"),
            sep,
            ("class:bottom-toolbar.accent", f"{_I['check']} "),
            ("class:bottom-toolbar.value", f"{sstatus.commits_this_session} commits"),
            sep,
            ("class:bottom-toolbar.accent", f"{_I['push']} "),
            ("class:bottom-toolbar.value", push_lbl),
            ("class:bottom-toolbar", "  "),
        ]
        return FormattedText(parts)

    def _splash(self) -> None:
        clear()
        cfg     = self.ctx.config
        cache   = self._status_cache
        is_repo = cache.is_repo()
        n       = len(cache.changed_files()) if is_repo else 0
        ai_ok   = self.ctx.ai.is_available()
        branch  = cache.current_branch() if is_repo else "—"

        console.print()
        wm = Text()
        wm.append("  ryft", style=f"bold {VIOLET}")
        wm.append(f"  {cfg.project.name}", style=f"bold {TEXT_HI}")
        wm.append(f"  ·  {cfg.root}", style=TEXT_DIM)
        console.print(wm)
        console.print()

        def _stat(icon, label, val, vc):
            row = Text()
            row.append(f"  {icon}  ", style=TEXT_DIM)
            row.append(f"{label:<10}", style=TEXT_DIM)
            row.append(val, style=vc)
            console.print(row)

        _stat(_I["branch"],  "branch",   branch, CYAN)
        _stat(_I["spark"],   "changes",  f"{n} modified" if n else "clean",
              AMBER if n else MINT)
        _stat(_I["model"],   "ollama",   "online" if ai_ok else "offline",
              MINT if ai_ok else CORAL)

        console.print()
        console.print(Rule(style=TEXT_GHOST))
        console.print(f"  [{TEXT_DIM}]type[/]  [{VIOLET}]/help[/]  [{TEXT_DIM}]for available commands[/]")
        console.print()

    def run(self) -> None:
        # Lazy import of commands — breaks the ui ↔ commands cycle.
        # commands.dispatch is only called here, never at module level.
        from .. import commands as commands_mod
        from .activity import render_completion_screen

        if self.first_run:
            render_completion_screen(self.ctx.config.project.name)
        else:
            self._splash()
        while self.ctx.running:
            session = PromptSession(
                completer=self._completer(),
                bottom_toolbar=self._toolbar,
                style=PTK_STYLE,
                complete_while_typing=True,
            )
            stop_refresh = threading.Event()

            def _refresh_loop():
                while not stop_refresh.wait(0.5):
                    try:
                        session.app.invalidate()
                    except Exception:
                        # Purely cosmetic: a failed UI invalidation during
                        # a teardown race shouldn't crash the refresh
                        # thread, but it's still worth a trace if it ever
                        # happens repeatedly.
                        logger.debug("Toolbar refresh invalidate failed", exc_info=True)

            refresher = threading.Thread(target=_refresh_loop, daemon=True)
            refresher.start()
            try:
                raw = session.prompt(
                    FormattedText([("class:prompt", "  ❯ ")])
                ).strip()
                if not raw:
                    continue
                console.print()
                try:
                    commands_mod.dispatch(self.ctx, raw)
                except Exception as exc:
                    logger.exception("Command dispatch failed for input: %r", raw)
                    log_activity(self.ctx, f"Command failed: {exc}", "error")
                finally:
                    # Any command may have changed branch/commit state
                    # (or, for /watch and /sync, changed whether sync is
                    # running) — force the next toolbar render to read
                    # fresh values instead of serving a stale cache entry.
                    self._status_cache.invalidate()
                console.print()
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            finally:
                stop_refresh.set()
