"""Ryft Terminal UI — v3.

Palette: dark github-style base, violet primary, cyan secondary,
teal for AI, mint/amber/coral for status. GitHub-accurate diff colours.

Key improvements over v2:
  • Real scrollable pager with viewport, scroll position, line numbers
  • GitHub-accurate diff renderer: green tint on additions, red tint on
    deletions, hunk headers in purple, token-level syntax on context lines
  • commands.py dispatch bug fixed: ui.warn/error accept optional ctx
  • Spinner guard against double-start
  • render_text / render_log sent to pager when > terminal height
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from io import StringIO
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import clear
from prompt_toolkit.styles import Style as PTKStyle

from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.prompt import Confirm
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

from . import git, commands

if TYPE_CHECKING:
    from .models import AppContext

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Palette
# ═══════════════════════════════════════════════════════════════════════════════

BG_BASE     = "#0d1117"
BG_RAISED   = "#161b22"
BG_OVERLAY  = "#1a1f28"

# diff backgrounds (rich bg colors)
DIFF_ADD_BG  = "#0d2a16"   # dark green wash
DIFF_DEL_BG  = "#2a0d0d"   # dark red wash
DIFF_HUNK_BG = "#1a1830"   # dark purple wash

VIOLET      = "#ae80ff"
VIOLET_DIM  = "#7b5cb8"
CYAN        = "#79c0ff"
MINT        = "#56d364"
AMBER       = "#e3b341"
CORAL       = "#ff7b72"
TEAL        = "#39d3c3"
PINK        = "#f778ba"

TEXT_HI     = "#f0f6fc"
TEXT_MID    = "#c9d1d9"
TEXT_DIM    = "#6e7681"
TEXT_GHOST  = "#3d444d"

# ── Rich theme ────────────────────────────────────────────────────────────────

_THEME = Theme({
    "success": MINT,  "warning": AMBER, "error": CORAL,
    "accent":  VIOLET, "cyan": CYAN,    "teal": TEAL,
    "dim":     TEXT_DIM, "ghost": TEXT_GHOST,
})

console = Console(theme=_THEME, highlight=False)

def _term_width() -> int:
    return console.width or 100

# ── PTK Style ─────────────────────────────────────────────────────────────────

PTK_STYLE = PTKStyle.from_dict({
    "bottom-toolbar":        f"bg:{BG_RAISED} {TEXT_DIM}",
    "bottom-toolbar.accent": f"bg:{BG_RAISED} bold {VIOLET}",
    "bottom-toolbar.value":  f"bg:{BG_RAISED} {TEXT_MID}",
    "bottom-toolbar.sep":    f"bg:{BG_RAISED} {TEXT_GHOST}",
    "prompt":                f"bold {VIOLET}",
    # Completion menu
    "completion-menu.completion":            f"bg:{BG_OVERLAY} {TEXT_MID}",
    "completion-menu.completion.current":    f"bg:{VIOLET_DIM} {TEXT_HI} bold",
    "completion-menu.meta.completion":       f"bg:{BG_RAISED} {TEXT_DIM}",
    "completion-menu.meta.completion.current": f"bg:{VIOLET_DIM} {TEXT_DIM}",
    "scrollbar.background": f"bg:{BG_RAISED}",
    "scrollbar.button":     f"bg:{VIOLET_DIM}",
})

# ── Icons ─────────────────────────────────────────────────────────────────────

_I = {
    "dot":     "·",   "arrow":   "›",   "bullet":  "▸",
    "check":   "✓",   "cross":   "✗",   "warn":    "⚑",
    "commit":  "●",   "push":    "↑",   "pull":    "↓",
    "format":  "◈",   "analyze": "◉",   "sync":    "⟳",
    "model":   "⬡",   "file":    "◻",   "folder":  "◼",
    "git":     "⬢",   "branch":  "⬢",   "star":    "★",
    "spark":   "◆",   "add":     "+",   "del":     "−",
    "hunk":    "⌗",   "ctx":     " ",
}

def _icon_color(msg: str, level: str) -> tuple[str, str]:
    ml = msg.lower()
    if level == "error":   return _I["cross"],   CORAL
    if level == "warn":    return _I["warn"],     AMBER
    if "commit"  in ml:   return _I["commit"],   MINT
    if "push"    in ml:   return _I["push"],      VIOLET
    if "pull"    in ml:   return _I["pull"],      VIOLET
    if "format"  in ml:   return _I["format"],    CYAN
    if "sync"    in ml:   return _I["sync"],      CYAN
    if "analyz"  in ml or "review" in ml: return _I["analyze"], TEAL
    if level == "success": return _I["check"],    MINT
    return _I["dot"], TEXT_DIM


# ═══════════════════════════════════════════════════════════════════════════════
# Scrollable pager — real viewport with keyboard nav
# ═══════════════════════════════════════════════════════════════════════════════

def _render_to_lines(renderable, width: int) -> list[str]:
    """Render a Rich renderable to a list of ANSI-coloured strings, one per line."""
    buf = StringIO()
    c = Console(file=buf, force_terminal=True, width=width, theme=_THEME, highlight=False)
    c.print(renderable)
    raw = buf.getvalue()
    # Split on newlines but keep the ANSI codes per line
    return raw.split("\n")


def _pager(title: str, renderable, *, width: int | None = None) -> None:
    """
    Full-screen scrollable pager.
    Keys: ↑/k  ↓/j  PgUp/u  PgDn/d  g(top)  G(bottom)  q/ESC(quit)
    """
    render_w = (width or _term_width()) - 2
    all_lines = _render_to_lines(renderable, render_w)

    state = {"top": 0}

    def _make_header() -> FormattedText:
        pct = int(state["top"] / max(1, len(all_lines)) * 100)
        return FormattedText([
            ("bg:" + BG_OVERLAY + " bold " + VIOLET, f"  {title}  "),
            ("bg:" + BG_OVERLAY + " " + TEXT_DIM,
             f"  ↑↓/jk · PgUp/d · PgDn/u · g/G top/bot · q quit"
             f"  [{pct}%]  "),
        ])

    def _make_body(rows: int) -> ANSI:
        visible = all_lines[state["top"]: state["top"] + rows]
        # pad to fill screen so background is consistent
        while len(visible) < rows:
            visible.append("")
        return ANSI("\n".join(visible))

    header_ctrl = FormattedTextControl(lambda: _make_header())
    header_win  = Window(height=1, content=header_ctrl, style="bg:" + BG_OVERLAY)

    body_ctrl = FormattedTextControl(lambda: _make_body(body_win.render_info.window_height if body_win.render_info else 40))
    body_win  = Window(content=body_ctrl, wrap_lines=False, always_hide_cursor=True)

    kb = KeyBindings()

    def _scroll(delta: int) -> None:
        rows = body_win.render_info.window_height if body_win.render_info else 40
        max_top = max(0, len(all_lines) - rows)
        state["top"] = max(0, min(state["top"] + delta, max_top))

    @kb.add("q")
    @kb.add("escape")
    def _quit(e): e.app.exit()

    @kb.add("up")
    @kb.add("k")
    def _up(e):   _scroll(-1)

    @kb.add("down")
    @kb.add("j")
    def _dn(e):   _scroll(1)

    @kb.add("pageup")
    @kb.add("u")
    def _pgup(e):
        rows = body_win.render_info.window_height if body_win.render_info else 40
        _scroll(-(rows - 2))

    @kb.add("pagedown")
    @kb.add("d")
    def _pgdn(e):
        rows = body_win.render_info.window_height if body_win.render_info else 40
        _scroll(rows - 2)

    @kb.add("g")
    def _top(e):  state["top"] = 0

    @kb.add("G")
    def _bot(e):
        rows = body_win.render_info.window_height if body_win.render_info else 40
        state["top"] = max(0, len(all_lines) - rows)

    app = Application(
        layout=Layout(HSplit([header_win, body_win])),
        key_bindings=kb,
        full_screen=True,
        style=PTK_STYLE,
        mouse_support=True,
    )
    with patch_stdout():
        app.run()


# ═══════════════════════════════════════════════════════════════════════════════
# GitHub-style diff renderer
# ═══════════════════════════════════════════════════════════════════════════════

_HUNK_RE = re.compile(r"^@@[^@]*@@")

def _parse_diff_hunks(diff_text: str) -> list[dict]:
    """
    Parse a unified diff into a list of hunk dicts:
      { "header": str, "lines": [{"kind": "+"/"-"/"@"/" ", "text": str, "lno_old": int|None, "lno_new": int|None}] }
    Also returns file header lines separately.
    """
    file_headers: list[str] = []
    hunks: list[dict] = []
    current: dict | None = None
    old_no = new_no = 0

    for raw in diff_text.splitlines():
        if raw.startswith("diff ") or raw.startswith("index ") or raw.startswith("--- ") or raw.startswith("+++ "):
            file_headers.append(raw)
            continue

        m = _HUNK_RE.match(raw)
        if m:
            # Parse @@ -a,b +c,d @@
            nums = re.findall(r"[-+]\d+", raw)
            old_no = abs(int(nums[0])) if nums else 1
            new_no = abs(int(nums[1])) if len(nums) > 1 else 1
            current = {"header": raw, "lines": []}
            hunks.append(current)
            continue

        if current is None:
            file_headers.append(raw)
            continue

        if raw.startswith("+"):
            current["lines"].append({"kind": "+", "text": raw[1:], "lno_old": None, "lno_new": new_no})
            new_no += 1
        elif raw.startswith("-"):
            current["lines"].append({"kind": "-", "text": raw[1:], "lno_old": old_no, "lno_new": None})
            old_no += 1
        else:
            # context line — may start with " " or be empty
            text = raw[1:] if raw.startswith(" ") else raw
            current["lines"].append({"kind": " ", "text": text, "lno_old": old_no, "lno_new": new_no})
            old_no += 1
            new_no += 1

    return file_headers, hunks


def _diff_line_text(line: dict, width: int, ext: str) -> Text:
    """
    Render one diff line as a Rich Text with:
      • Full-width tinted background
      • Line numbers (old + new columns)
      • Gutter icon
      • Syntax-highlighted code on context lines; plain coloured on +/-
    """
    kind    = line["kind"]
    src     = line["text"]
    lno_old = line["lno_old"]
    lno_new = line["lno_new"]

    # colours by kind
    if kind == "+":
        bg, gutter_color, text_color = DIFF_ADD_BG,  MINT,     "#aaffaa"
        gutter_icon = "+"
        lno_str_l = "    "
        lno_str_r = f"{lno_new:>4}" if lno_new is not None else "    "
    elif kind == "-":
        bg, gutter_color, text_color = DIFF_DEL_BG,  CORAL,    "#ffaaaa"
        gutter_icon = "−"
        lno_str_l = f"{lno_old:>4}" if lno_old is not None else "    "
        lno_str_r = "    "
    else:
        bg, gutter_color, text_color = BG_BASE,      TEXT_GHOST, TEXT_MID
        gutter_icon = " "
        lno_str_l = f"{lno_old:>4}" if lno_old is not None else "    "
        lno_str_r = f"{lno_new:>4}" if lno_new is not None else "    "

    t = Text(no_wrap=True, end="\n")
    t.append(f" {lno_str_l} {lno_str_r} ", style=f"{TEXT_GHOST} on {bg}")
    t.append(f"{gutter_icon} ", style=f"bold {gutter_color} on {bg}")

    # Inline syntax highlight context lines using Rich Syntax, extract spans
    # For +/- lines just use coloured plain text (matches GitHub behaviour)
    if kind == " " and ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".json",
                                ".yaml", ".yml", ".toml", ".sh", ".bash",
                                ".c", ".cpp", ".h", ".go", ".rs", ".java"):
        # Render one line of syntax via Rich, extract ANSI, append raw
        _lbuf = StringIO()
        _lcon = Console(file=_lbuf, force_terminal=True, width=width, highlight=False,
                        theme=_THEME)
        lex = ext.lstrip(".")
        if lex in ("jsx", "tsx"): lex = "javascript"
        _lcon.print(Syntax(src, lex, theme="github-dark", background_color="default",
                           line_numbers=False), end="")
        ansi_src = _lbuf.getvalue().rstrip("\n")
        t.append_text(Text.from_ansi(ansi_src))
    else:
        t.append(src, style=f"{text_color} on {bg}")

    return t


def _render_diff_pager(file: str, diff_text: str) -> None:
    """Build a GitHub-style diff view and send to the scrollable pager."""
    ext = os.path.splitext(file)[1].lower()
    w   = _term_width()
    file_headers, hunks = _parse_diff_hunks(diff_text)

    parts: list = []

    # ── File header bar ───────────────────────────────────────────────────────
    hdr = Text(no_wrap=True)
    hdr.append(f"  {_I['file']}  ", style=TEXT_DIM)
    hdr.append(file, style=f"bold {CYAN}")
    n_add = sum(1 for h in hunks for l in h["lines"] if l["kind"] == "+")
    n_del = sum(1 for h in hunks for l in h["lines"] if l["kind"] == "-")
    hdr.append(f"   +{n_add}", style=MINT)
    hdr.append(f"  −{n_del}", style=CORAL)
    parts.append(hdr)
    parts.append(Text(""))

    if not hunks:
        parts.append(Text("  (no diff content)", style=TEXT_DIM))
    else:
        for hunk in hunks:
            # hunk header line
            hh = Text(no_wrap=True)
            hh.append(f"  {_I['hunk']} ", style=f"bold {VIOLET_DIM}")
            # extract just the @@ ... @@ portion and the trailing context
            hh.append(hunk["header"], style=VIOLET_DIM)
            parts.append(hh)

            for line in hunk["lines"]:
                parts.append(_diff_line_text(line, w, ext))

            parts.append(Text(""))

    _pager(f"diff  ·  {file}", Group(*parts))


# ═══════════════════════════════════════════════════════════════════════════════
# Section helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _rule(label: str = "", color: str = TEXT_GHOST) -> None:
    if label:
        console.print(Rule(f"[{color}]{label}[/{color}]", style=TEXT_GHOST))
    else:
        console.print(Rule(style=TEXT_GHOST))

def _sp() -> None:
    console.print()


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
# RyftApp — REPL shell
# ═══════════════════════════════════════════════════════════════════════════════

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

        _stat(_I["branch"],  "branch",   branch,
              CYAN)
        _stat(_I["spark"],   "changes",  f"{n} modified" if n else "clean",
              AMBER if n else MINT)
        _stat(_I["model"],   "ollama",   "online" if ai_ok else "offline",
              MINT if ai_ok else CORAL)

        console.print()
        console.print(Rule(style=TEXT_GHOST))
        console.print(f"  [{TEXT_DIM}]type[/]  [{VIOLET}]/help[/]  [{TEXT_DIM}]for available commands[/]")
        console.print()

    def run(self) -> None:
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
                _sp()
                try:
                    commands.dispatch(self.ctx, raw)
                except Exception as exc:
                    logger.exception("Command dispatch failed for input: %r", raw)
                    log_activity(self.ctx, f"Command failed: {exc}", "error")
                finally:
                    # Any command may have changed branch/commit state
                    # (or, for /watch and /sync, changed whether sync is
                    # running) — force the next toolbar render to read
                    # fresh values instead of serving a stale cache entry.
                    self._status_cache.invalidate()
                _sp()
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            finally:
                stop_refresh.set()


# ═══════════════════════════════════════════════════════════════════════════════
# Activity log & spinner
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
                # Cosmetic terminal cleanup — never worth surfacing to
                # the user, but logged so a genuinely broken terminal
                # session leaves a trace somewhere.
                logger.debug("Spinner stop failed", exc_info=True)
            self._running = False

    def __enter__(self) -> "TaskSpinner":
        return self

    def __exit__(self, *_) -> None:
        self.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Stage labels & colours used by the live commit tree
# ─────────────────────────────────────────────────────────────────────────────

_STAGES = ["target", "format", "message", "commit"]
_STAGE_LABEL = {
    "target":  "target",
    "format":  "format",
    "message": "message",
    "commit":  "commit",
}

# Per-state glyph + colour for each file row
_FILE_STATE_STYLE = {
    "waiting":  (f"[{TEXT_GHOST}]○[/{TEXT_GHOST}]",   TEXT_GHOST),
    "active":   (f"[bold {VIOLET}]◉[/bold {VIOLET}]", VIOLET),
    "done":     (f"[{MINT}]●[/{MINT}]",               MINT),
    "error":    (f"[{CORAL}]✗[/{CORAL}]",             CORAL),
}

# Stage pill colours: inactive / active / done / error
_PILL_INACTIVE = f"{TEXT_GHOST} on {BG_OVERLAY}"
_PILL_ACTIVE   = f"bold {BG_BASE} on {VIOLET}"
_PILL_DONE     = f"{BG_BASE} on {MINT}"
_PILL_ERROR    = f"{BG_BASE} on {CORAL}"


def _stage_pill(label: str, state: str) -> Text:
    """Return a styled pill Text for one stage."""
    t = Text(no_wrap=True)
    if state == "inactive":
        t.append(f" {label} ", style=_PILL_INACTIVE)
    elif state == "active":
        t.append(f" {label} ", style=_PILL_ACTIVE)
    elif state == "done":
        t.append(f" {label} ", style=_PILL_DONE)
    else:  # error
        t.append(f" {label} ", style=_PILL_ERROR)
    return t


def _build_file_row(
    fname: str,
    file_state: str,          # waiting / active / done / error
    stage_states: dict,       # {stage_name: "inactive"|"active"|"done"|"error"}
    commit_msg: str,
    is_last: bool,
) -> Text:
    """
    Render one file row:
      ◉ src/foo.py   [ target ]›[ format ]›[ message ]›[ commit ]   chore: update foo.py
    """
    glyph, glyph_color = _FILE_STATE_STYLE[file_state][:2], _FILE_STATE_STYLE[file_state][1]
    glyph_markup = _FILE_STATE_STYLE[file_state][0]

    row = Text(no_wrap=True)

    # tree connector
    connector = "└─" if is_last else "├─"
    row.append(f"  {connector} ", style=TEXT_GHOST)

    # state glyph (already markup — append raw)
    row.append_text(Text.from_markup(glyph_markup))
    row.append("  ", style="")

    # filename — dim dir part, bright basename
    parts = fname.rsplit("/", 1)
    if len(parts) == 2:
        row.append(parts[0] + "/", style=TEXT_DIM)
        row.append(parts[1], style=f"bold {TEXT_HI}" if file_state == "active" else TEXT_MID)
    else:
        row.append(fname, style=f"bold {TEXT_HI}" if file_state == "active" else TEXT_MID)

    row.append("   ", style="")

    # stage pills separated by thin arrows
    for i, stage in enumerate(_STAGES):
        st = stage_states.get(stage, "inactive")
        row.append_text(_stage_pill(_STAGE_LABEL[stage], st))
        if i < len(_STAGES) - 1:
            row.append(" › ", style=TEXT_GHOST)

    # commit message (appears once commit stage is done)
    if commit_msg and stage_states.get("commit") in ("done", "error"):
        row.append("   ", style="")
        row.append(commit_msg, style=TEXT_DIM)

    return row


class LiveCommitView:
    """
    Renders a live-updating commit tree using Rich Live.

    Layout:
      commit  ·  3 files
      ├─ ◉  src/foo.py   [ target ]›[ format ]›[ message ]›[ commit ]
      ├─ ○  src/bar.py   [ target ]›[ format ]›[ message ]›[ commit ]
      └─ ○  src/baz.py   [ target ]›[ format ]›[ message ]›[ commit ]

      ▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒  1 / 3   0:00:04
    """

    def __init__(self, ctx: "AppContext", files: list[str]) -> None:
        from rich.live import Live
        from rich.progress import (
            BarColumn, Progress, SpinnerColumn,
            TaskProgressColumn, TimeElapsedColumn, TextColumn,
        )

        self.ctx    = ctx
        self.files  = files
        self._total = len(files)
        self._done  = 0

        # per-file state
        self._file_state: dict[str, str]        = {f: "waiting" for f in files}
        self._stage_states: dict[str, dict]     = {
            f: {s: "inactive" for s in _STAGES} for f in files
        }
        self._messages: dict[str, str]          = {f: "" for f in files}
        self._start = time.time()

        # overall progress bar (shown below the tree)
        self._progress = Progress(
            SpinnerColumn(spinner_name="dots", style=VIOLET),
            BarColumn(
                bar_width=32,
                style=f"on {BG_OVERLAY}",
                complete_style=VIOLET,
                finished_style=MINT,
                pulse_style=VIOLET_DIM,
            ),
            TaskProgressColumn(style=f"bold {TEXT_MID}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        self._bar_task = self._progress.add_task("commit", total=self._total)

        self._live = Live(
            self._render(),
            console=console,
            refresh_per_second=12,
            transient=False,
        )

    # ── internal render ───────────────────────────────────────────────────────

    def _render(self):
        from rich.console import Group as RGroup
        elapsed = time.time() - self._start
        done    = self._done

        header = Text(no_wrap=True)
        header.append(f"\n  commit", style=f"bold {VIOLET}")
        header.append(f"  ·  {self._total} file{'s' if self._total != 1 else ''}",
                      style=TEXT_DIM)
        header.append(f"  ·  {done}/{self._total} done", style=TEXT_GHOST)

        rows = [header, Text("")]
        for i, fname in enumerate(self.files):
            is_last = i == len(self.files) - 1
            row = _build_file_row(
                fname,
                self._file_state[fname],
                self._stage_states[fname],
                self._messages[fname],
                is_last,
            )
            rows.append(row)

        rows.append(Text(""))
        rows.append(self._progress)
        rows.append(Text(""))
        return RGroup(*rows)

    # ── public API called by commands.py ──────────────────────────────────────

    def __enter__(self) -> "LiveCommitView":
        self._live.start()
        return self

    def set_stage(self, fname: str, stage: str, state: str) -> None:
        """Set one stage of one file to inactive/active/done/error."""
        self._stage_states[fname][stage] = state
        if state == "active":
            self._file_state[fname] = "active"
        self._live.update(self._render())

    def set_file_state(self, fname: str, state: str, message: str = "") -> None:
        self._file_state[fname] = state
        if message:
            self._messages[fname] = message
        if state in ("done", "error"):
            self._done += 1
            self._progress.update(self._bar_task, advance=1)
        self._live.update(self._render())

    def __exit__(self, *_) -> None:
        self._live.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Live push view
# ─────────────────────────────────────────────────────────────────────────────

_PUSH_STAGES = ["pack", "delta", "write", "push"]

class LivePushView:
    """
    Simulated-but-honest push progress.
    Real git push gives no granular progress over HTTPS, so we show
    animated fake stages that complete as one real call resolves.

    Layout:
      push  ·  origin/main

      [ pack ]›[ delta ]›[ write ]›[ push ]

      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒▒▒  3 / 4   0:00:01
    """

    def __init__(self, ctx: "AppContext", remote: str, branch: str) -> None:
        from rich.live import Live
        from rich.progress import (
            BarColumn, Progress, SpinnerColumn,
            TaskProgressColumn, TimeElapsedColumn,
        )

        self.ctx     = ctx
        self.remote  = remote
        self.branch  = branch
        self._stages = {s: "inactive" for s in _PUSH_STAGES}
        self._status = ""
        self._start  = time.time()

        self._progress = Progress(
            SpinnerColumn(spinner_name="dots", style=VIOLET),
            BarColumn(
                bar_width=32,
                style=f"on {BG_OVERLAY}",
                complete_style=VIOLET,
                finished_style=MINT,
                pulse_style=VIOLET_DIM,
            ),
            TaskProgressColumn(style=f"bold {TEXT_MID}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        self._bar_task = self._progress.add_task("push", total=len(_PUSH_STAGES))

        self._live = Live(
            self._render(),
            console=console,
            refresh_per_second=12,
            transient=False,
        )

    def _render(self):
        from rich.console import Group as RGroup

        header = Text(no_wrap=True)
        header.append(f"\n  push", style=f"bold {VIOLET}")
        header.append(f"  ·  {self.remote}/{self.branch}", style=TEXT_DIM)
        if self._status:
            header.append(f"  ·  {self._status}", style=TEXT_GHOST)

        pills = Text(no_wrap=True)
        pills.append("  ")
        for i, stage in enumerate(_PUSH_STAGES):
            st = self._stages[stage]
            pills.append_text(_stage_pill(stage, st))
            if i < len(_PUSH_STAGES) - 1:
                pills.append(" › ", style=TEXT_GHOST)

        return RGroup(header, Text(""), pills, Text(""), self._progress, Text(""))

    def __enter__(self) -> "LivePushView":
        self._live.start()
        return self

    def set_stage(self, stage: str, state: str, status: str = "") -> None:
        self._stages[stage] = state
        if status:
            self._status = status
        if state in ("done", "error"):
            self._progress.update(self._bar_task, advance=1)
        self._live.update(self._render())

    def finish(self, ok: bool, msg: str = "") -> None:
        self._status = msg
        final = "done" if ok else "error"
        for s in _PUSH_STAGES:
            if self._stages[s] != "done":
                self._stages[s] = final
        self._live.update(self._render())

    def __exit__(self, *_) -> None:
        self._live.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# One-line outputs  (ctx is accepted but ignored — fixes commands.py dispatch bug)
# ═══════════════════════════════════════════════════════════════════════════════

def info(msg: str,    _ctx=None) -> None: console.print(f"  [{TEXT_DIM}]{_I['arrow']}[/]  [{TEXT_MID}]{escape(msg)}[/]")
def success(msg: str, _ctx=None) -> None: console.print(f"  [{MINT}]{_I['check']}[/]  [{TEXT_MID}]{escape(msg)}[/]")
def warn(msg: str,    _ctx=None) -> None: console.print(f"  [{AMBER}]{_I['warn']}[/]  [{TEXT_MID}]{escape(msg)}[/]")
def error(msg: str,   _ctx=None) -> None: console.print(f"  [{CORAL}]{_I['cross']}[/]  [{TEXT_MID}]{escape(msg)}[/]")


def confirm(question: str, default: bool = True) -> bool:
    """Styled Y/n prompt used by onboarding and auto-recovery flows."""
    _sp()
    for line in question.splitlines():
        console.print(f"  [{TEXT_HI}]{escape(line)}[/]" if line.strip() else "")
    try:
        return Confirm.ask(f"  [{VIOLET}]?[/]", default=default, console=console)
    except (EOFError, KeyboardInterrupt):
        return False


def run_model_pull(model: str) -> bool:
    """Run `ollama pull <model>` with a live status line, returning success."""
    from . import ai as ai_mod

    state = {"line": ""}
    with console.status(Text(f"  Downloading {model}…", style=VIOLET),
                         spinner="dots", spinner_style=VIOLET) as st:
        def _on_line(line: str) -> None:
            clean = line.strip()
            if clean:
                state["line"] = clean
                st.update(Text(f"  {model}  ·  {clean}", style=VIOLET))

        ok = ai_mod.pull_model_cli(model, on_line=_on_line)

    if ok:
        success(f"{model} downloaded")
    else:
        error(f"{model} download failed" + (f" — {state['line']}" if state["line"] else ""))
    return ok


# ═══════════════════════════════════════════════════════════════════════════════
# Diff views
# ═══════════════════════════════════════════════════════════════════════════════

def render_diff_summary(stats: list[tuple[str, int, int]]) -> None:
    """Bar-chart summary of changed files."""
    _rule("diff summary", VIOLET_DIM)
    _sp()

    if not stats:
        info("Working tree is clean.")
        return

    max_a = max((a for _, a, _ in stats), default=1) or 1
    max_d = max((d for _, _, d in stats), default=1) or 1
    bar_w = 20

    for fname, adds, dels in stats:
        a_bar = round(adds / max_a * bar_w)
        d_bar = round(dels / max_d * bar_w)
        row   = Text(no_wrap=True)
        row.append(f"  {fname:<44}", style=TEXT_MID)
        row.append(f" +{adds:<4}", style=MINT)
        row.append("█" * a_bar,  style=f"{MINT} on {DIFF_ADD_BG}")
        row.append("█" * d_bar,  style=f"{CORAL} on {DIFF_DEL_BG}")
        row.append(f"−{dels}",   style=CORAL)
        console.print(row)

    _sp()
    console.print(f"  [{TEXT_DIM}]tip · /diff <file>  to browse line changes[/]")
    _sp()


def render_file_diff(file: str, diff_text: str) -> None:
    """GitHub-style diff sent to scrollable pager."""
    _render_diff_pager(file, diff_text)


# ═══════════════════════════════════════════════════════════════════════════════
# AI output
# ═══════════════════════════════════════════════════════════════════════════════

def render_ai_output(text: str, title: str = "Analysis") -> None:
    SECTIONS = {"summary", "changes", "risks", "issues",
                "suggestions", "quality", "commit message"}
    parts: list = [Rule(f"[{TEAL}]{title}[/{TEAL}]", style=TEXT_GHOST), Text("")]

    for line in text.splitlines():
        s   = line.strip()
        key = s.lower().rstrip(":")
        if key in SECTIONS:
            parts.append(Text(""))
            h = Text()
            h.append(f"  {_I['spark']} ", style=TEAL)
            h.append(s.upper(), style=f"bold {TEAL}")
            parts.append(h)
        elif s.startswith(("- ", "* ", "• ")):
            b = Text()
            b.append(f"      {_I['bullet']} ", style=VIOLET_DIM)
            b.append(s[2:], style=TEXT_MID)
            parts.append(b)
        elif s:
            parts.append(Text(f"    {s}", style=TEXT_MID))

    parts.append(Text(""))
    _pager(title, Group(*parts))


# ═══════════════════════════════════════════════════════════════════════════════
# Activity
# ═══════════════════════════════════════════════════════════════════════════════

def render_activity_full(ctx: "AppContext") -> None:
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


# ═══════════════════════════════════════════════════════════════════════════════
# Misc
# ═══════════════════════════════════════════════════════════════════════════════

def render_text(title: str, text: str) -> None:
    """Render plain text — sent to pager if long."""
    lines = text.splitlines()
    term_h = os.get_terminal_size().lines if os.isatty(1) else 40
    parts = [Rule(f"[{VIOLET_DIM}]{title.lower()}[/{VIOLET_DIM}]", style=TEXT_GHOST), Text("")]
    for ln in lines:
        parts.append(Text(f"  {ln}", style=TEXT_MID))
    parts.append(Text(""))
    if len(lines) > term_h - 4:
        _pager(title.lower(), Group(*parts))
    else:
        for p in parts:
            console.print(p)


def render_code(title: str, code: str, lexer: str) -> None:
    _rule(title.lower(), VIOLET_DIM)
    _sp()
    console.print(Padding(
        Syntax(code, lexer, theme="github-dark", background_color="default"),
        (0, 2),
    ))
    _sp()


def render_tree(tree: Tree) -> None:
    _sp()
    console.print(Padding(tree, (0, 2)))
    _sp()


def render_files(files: list[str]) -> None:
    _rule("tracked files", VIOLET_DIM)
    _sp()
    for f in files:
        row = Text()
        row.append(f"  {_I['file']}  ", style=TEXT_DIM)
        row.append(f, style=TEXT_MID)
        console.print(row)
    _sp()


# ═══════════════════════════════════════════════════════════════════════════════
# Git status
# ═══════════════════════════════════════════════════════════════════════════════

_STATUS_META = {
    "A": (MINT,      "added"),
    "?": (CYAN,      "new"),
    "D": (CORAL,     "deleted"),
    "M": (AMBER,     "modified"),
    "R": (VIOLET,    "renamed"),
}

def render_git_changes(changes) -> None:
    if not changes:
        success("Working tree is clean.")
        return
    _rule(f"changes  ·  {len(changes)} file(s)", VIOLET_DIM)
    _sp()
    for c in changes:
        color, label = _STATUS_META.get(c.status, (TEXT_DIM, c.status))
        row = Text()
        row.append(f"  {label:<12}", style=color)
        row.append(c.path, style=TEXT_MID)
        console.print(row)
    _sp()


# ═══════════════════════════════════════════════════════════════════════════════
# Doctor / models / dashboard
# ═══════════════════════════════════════════════════════════════════════════════

_DOCTOR_STYLE = {
    "ok":   (_I["check"], MINT),
    "warn": (_I["warn"],  AMBER),
    "fail": (_I["cross"], CORAL),
}

def render_doctor(checks: list) -> None:
    """Render a list of `doctor.DoctorCheck`. Each non-ok check gets its
    explanation and fix hint printed underneath, indented."""
    _rule("system health", VIOLET_DIM)
    _sp()
    for c in checks:
        icon, color = _DOCTOR_STYLE.get(c.status, (_I["dot"], TEXT_DIM))
        row = Text()
        row.append(f"  {icon}  ", style=color)
        row.append(f"{c.name:<22}", style=TEXT_HI if c.status == "ok" else TEXT_MID)
        row.append(c.detail, style=TEXT_DIM)
        console.print(row)
        if c.status != "ok" and c.why:
            console.print(Text(f"       {c.why}", style=TEXT_DIM))
        if c.status != "ok" and c.fix_hint:
            fix_row = Text()
            fix_row.append("       fix: ", style=VIOLET_DIM)
            fix_row.append(c.fix_hint, style=TEXT_MID)
            console.print(fix_row)
        if c.status != "ok" and (c.why or c.fix_hint):
            console.print()

    ok = sum(1 for c in checks if c.status == "ok")
    warn = sum(1 for c in checks if c.status == "warn")
    fail = sum(1 for c in checks if c.status == "fail")
    summary = Text()
    summary.append("  summary  ", style=TEXT_DIM)
    summary.append(f"{ok} ok", style=MINT)
    summary.append("  ·  ", style=TEXT_GHOST)
    summary.append(f"{warn} warning{'s' if warn != 1 else ''}", style=AMBER if warn else TEXT_GHOST)
    summary.append("  ·  ", style=TEXT_GHOST)
    summary.append(f"{fail} failure{'s' if fail != 1 else ''}", style=CORAL if fail else TEXT_GHOST)
    console.print(summary)
    _sp()


def render_models(models: list[str], current: str, installed: list[str]) -> None:
    _rule("ollama models", VIOLET_DIM)
    _sp()
    for m in models:
        is_cur = m == current
        is_ins = m in installed
        if is_cur:
            icon, ic, nc = _I["star"],  VIOLET,     TEXT_HI
        elif is_ins:
            icon, ic, nc = _I["check"], MINT,        TEXT_MID
        else:
            icon, ic, nc = _I["dot"],   TEXT_GHOST,  TEXT_DIM
        row = Text()
        row.append(f"  {icon}  ", style=ic)
        row.append(m, style=nc)
        if is_cur:    row.append("  ← active",       style=VIOLET_DIM)
        elif not is_ins: row.append("  not installed", style=TEXT_GHOST)
        console.print(row)
    _sp()


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


# ═══════════════════════════════════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════════════════════════════════

_CMD_GROUPS: dict[str, list[str]] = {
    "git"     : ["commit", "push", "pull", "diff", "log", "git"],
    "ai"      : ["analyze", "review", "message", "model"],
    "sync"    : ["watch", "sync", "format"],
    "project" : ["init", "status", "doctor", "config", "tree", "files", "root"],
    "shell"   : ["help", "activity", "exit"],
}

def render_help_index(commands_dict: dict) -> None:
    _rule("commands", VIOLET_DIM)
    for group, names in _CMD_GROUPS.items():
        _sp()
        console.print(f"  [{TEXT_DIM}]{group}[/]")
        for name in names:
            spec = commands_dict.get(name)
            if spec is None:
                continue
            row = Text()
            row.append(f"    /{name:<16}", style=f"bold {VIOLET}")
            row.append(spec.description, style=TEXT_MID)
            console.print(row)
    _sp()


def render_help_command(spec) -> None:
    _sp()
    console.print(Text(f"  /{spec.name}", style=f"bold {VIOLET}"))
    _sp()
    console.print(f"  [{TEXT_MID}]{escape(spec.description)}[/]")
    if spec.usage:
        _sp()
        console.print(f"  [{TEXT_DIM}]usage[/]")
        for u in spec.usage:
            console.print(f"    [{TEXT_DIM}]{escape(u)}[/]")
    if spec.examples:
        _sp()
        console.print(f"  [{TEXT_DIM}]examples[/]")
        for ex in spec.examples:
            console.print(f"    [{CYAN}]{escape(ex)}[/]")
    _sp()