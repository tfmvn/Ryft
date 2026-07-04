"""GitHub-style diff renderer, live commit/push views, and all render_*
functions.

Dependencies: colors, icons, pager, prompt. No upward dependency on
``commands`` or handler modules.
"""
from __future__ import annotations

import os
import re
import time
from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

from .colors import (
    BG_BASE, BG_OVERLAY, DIFF_ADD_BG, DIFF_DEL_BG,
    VIOLET, VIOLET_DIM, CYAN, MINT, AMBER, CORAL, TEAL,
    TEXT_HI, TEXT_MID, TEXT_DIM, TEXT_GHOST,
    _THEME, _rule, _sp, _term_width, console,
)
from .icons import _I, _icon_color
from .pager import _pager
from .prompt import info, success

if TYPE_CHECKING:
    from .dashboard import RyftApp

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
# Stage labels & colours used by the live commit tree
# ═══════════════════════════════════════════════════════════════════════════════

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

    def __init__(self, ctx, files: list[str]) -> None:
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

    # ── public API ────────────────────────────────────────────────────────────

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

    def __init__(self, ctx, remote: str, branch: str) -> None:
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


def render_tree(tree) -> None:
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
# Doctor / models
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
