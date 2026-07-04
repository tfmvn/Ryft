"""Activity log, TaskSpinner, onboarding screens, and render_activity_full."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.console import Group
from rich.markup import escape
from rich.text import Text

from prompt_toolkit.shortcuts import clear  # type: ignore[import]

from .colors import CORAL, MINT, TEXT_DIM, TEXT_GHOST, TEXT_MID, TEXT_HI, VIOLET, VIOLET_DIM, _rule, _sp, console
from .icons import _I, _icon_color
from .pager import _pager
from .prompt import info

if TYPE_CHECKING:
    from ..models import AppContext


# ═══════════════════════════════════════════════════════════════════════════════
# Activity log
# ═══════════════════════════════════════════════════════════════════════════════

def log_activity(ctx: "AppContext", msg: str, level: str = "info") -> None:
    ctx.activity.add(msg, level)
    icon, color = _icon_color(msg, level)
    line = Text()
    line.append(f"  {time.strftime('%H:%M')}  ", style=TEXT_DIM)
    line.append(f"{icon}  ", style=color)
    line.append(msg, style=TEXT_MID)
    console.print(line)


class TaskSpinner:
    """Single-task spinner — dots + violet accent, pip-style step logging."""

    def __init__(self, ctx: "AppContext", initial_msg: str) -> None:
        from rich.text import Text
        self.ctx      = ctx
        self._msg     = initial_msg
        self._running = False
        self._st      = console.status(
            Text(f"  {initial_msg}", style=VIOLET),
            spinner="dots",
            spinner_style=VIOLET,
        )
        self._st.start()
        self._running = True

    def start(self, msg: str) -> None:
        from rich.text import Text
        self._msg = msg
        self._st.update(Text(f"  {msg}", style=VIOLET))
        if not self._running:
            self._st.start()
            self._running = True

    def step(self, msg: str) -> None:
        """Mark current step done, log it, keep spinner alive for next step."""
        self._st.stop()
        self._running = False
        log_activity(self.ctx, msg, "success")
        self._st.start()
        self._running = True

    def fail(self, msg: str) -> None:
        if self._running:
            self._st.stop()
            self._running = False
        log_activity(self.ctx, msg, "error")

    def stop(self) -> None:
        if self._running:
            try:
                self._st.stop()
            except Exception:
                pass
            self._running = False

    def __enter__(self) -> "TaskSpinner":
        return self

    def __exit__(self, *_) -> None:
        self.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# First-run onboarding
# ═══════════════════════════════════════════════════════════════════════════════

def render_onboarding_welcome() -> None:
    clear()
    console.print()
    wm = Text()
    wm.append("  Welcome to ", style=TEXT_HI)
    wm.append("Ryft", style=f"bold {VIOLET}")
    wm.append(".", style=TEXT_HI)
    console.print(wm)
    console.print()
    console.print(f"  [{TEXT_DIM}]No configuration was found in this folder.[/]")
    console.print()


class OnboardingProgress:
    """Sequential checklist used during first-run setup:

        ✓ Project detected
        ✓ Creating configuration
        ✓ Validating

        Done.
    """

    def __init__(self) -> None:
        from rich.text import Text
        self._st = console.status(Text("  Getting started…", style=VIOLET),
                                   spinner="dots", spinner_style=VIOLET)
        self._started = False

    def __enter__(self) -> "OnboardingProgress":
        self._st.start()
        self._started = True
        return self

    def step(self, label: str) -> None:
        self._st.stop()
        console.print(f"  [{MINT}]{_I['check']}[/]  [{TEXT_MID}]{escape(label)}[/]")
        self._st.start()

    def fail(self, label: str) -> None:
        self._st.stop()
        self._started = False
        console.print(f"  [{CORAL}]{_I['cross']}[/]  [{TEXT_MID}]{escape(label)}[/]")

    def __exit__(self, *_) -> None:
        if self._started:
            self._st.stop()


def render_onboarding_done() -> None:
    console.print()
    console.print(f"  [{MINT}]Done.[/]")
    console.print()


def render_completion_screen(project_name: str) -> None:
    """Friendly guidance screen shown right after onboarding finishes."""
    from rich.rule import Rule
    console.print(Rule(style=TEXT_GHOST))
    console.print()
    ready = Text()
    ready.append("  You're ready", style=f"bold {TEXT_HI}")
    ready.append(f"  ·  {project_name}", style=TEXT_DIM)
    console.print(ready)
    console.print()
    console.print(f"  [{TEXT_DIM}]Try one of these:[/]")
    console.print()

    suggestions = [
        ("ryft watch",  "start watching this folder and auto-commit changes"),
        ("ryft commit", "commit your current changes with an AI message"),
        ("ryft review", "get an AI code review of what changed"),
        ("ryft doctor", "check that everything is set up correctly"),
    ]
    for cmd, desc in suggestions:
        row = Text()
        row.append(f"    {cmd:<14}", style=f"bold {VIOLET}")
        row.append(desc, style=TEXT_DIM)
        console.print(row)

    console.print()
    console.print(f"  [{TEXT_DIM}]Type[/]  [{VIOLET}]/help[/]  [{TEXT_DIM}]anytime.[/]")
    console.print()
    console.print(Rule(style=TEXT_GHOST))
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
# Activity
# ═══════════════════════════════════════════════════════════════════════════════

def render_activity_full(ctx: "AppContext") -> None:
    from rich.rule import Rule
    events = ctx.activity.all()
    if not events:
        _rule("activity", VIOLET_DIM)
        _sp()
        info("No activity recorded yet.")
        return

    parts: list = [Rule(f"[{VIOLET_DIM}]activity[/{VIOLET_DIM}]", style=TEXT_GHOST), Text("")]
    prev_date = None
    for e in events:
        date_str = time.strftime("%Y-%m-%d", time.localtime(e.at))
        if date_str != prev_date:
            prev_date = date_str
            parts.append(Text(""))
            parts.append(Text(f"  {date_str}", style=TEXT_DIM))
        icon, color = _icon_color(e.message, e.level)
        row = Text()
        row.append(f"  {e.time_str}  ", style=TEXT_DIM)
        row.append(f"{icon}  ", style=color)
        row.append(e.message, style=TEXT_MID)
        parts.append(row)

    parts.append(Text(""))
    _pager("activity", Group(*parts))
