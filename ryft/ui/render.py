"""On-theme Rich renderables for the v2 UI.

These return Rich objects (not full-screen pagers) so they can be composed
into the TUI body *or* printed by one-shot commands. Colors come from
``ui.theme.palette.C`` (the design tokens) — this is the single visual
language shared by the dashboard, palette, and diff/commit/review viewers.

The diff/AI parsing logic is ported from the v1 renderer; the styling now
flows exclusively from the v2 design tokens so the whole app re-themes from
one place.
"""

from __future__ import annotations

import os
import re
from rich.console import Group
from rich.padding import Padding
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

from .theme.palette import C

_HUNK_RE = re.compile(r"^@@[^@]*@@")


# ── Diff ──────────────────────────────────────────────────────────────────────

def build_diff(file: str, diff_text: str, width: int = 120) -> "object":
    """GitHub-style diff as a Rich renderable (header + colored hunk lines)."""
    ext = os.path.splitext(file)[1].lower()
    file_headers: list[str] = []
    hunks: list[dict] = []
    current: dict | None = None
    old_no = new_no = 0

    for raw in diff_text.splitlines():
        if raw.startswith(("diff ", "index ", "--- ", "+++ ")):
            file_headers.append(raw)
            continue
        m = _HUNK_RE.match(raw)
        if m:
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
            current["lines"].append({"kind": "+", "text": raw[1:], "lo": None, "ln": new_no})
            new_no += 1
        elif raw.startswith("-"):
            current["lines"].append({"kind": "-", "text": raw[1:], "lo": old_no, "ln": None})
            old_no += 1
        else:
            text = raw[1:] if raw.startswith(" ") else raw
            current["lines"].append({"kind": " ", "text": text, "lo": old_no, "ln": new_no})
            old_no += 1
            new_no += 1

    parts: list = []
    hdr = Text(no_wrap=True)
    hdr.append("  ", style=C["dim"])
    hdr.append(file, style=f"bold {C['info']}")
    n_add = sum(1 for h in hunks for l in h["lines"] if l["kind"] == "+")
    n_del = sum(1 for h in hunks for l in h["lines"] if l["kind"] == "-")
    hdr.append(f"    +{n_add} ", style=C["success"])
    hdr.append(f"−{n_del}", style=C["danger"])
    parts.append(hdr)
    parts.append(Text(""))

    if not hunks:
        parts.append(Text("  (no diff content)", style=C["dim"]))
    else:
        for hunk in hunks:
            hh = Text(no_wrap=True)
            hh.append("  ", style=C["dim"])
            hh.append(hunk["header"], style=C["diff_hunk"])
            parts.append(hh)
            for line in hunk["lines"]:
                parts.append(_diff_line(line, ext, width))
            parts.append(Text(""))

    return Group(*parts)


def _diff_line(line: dict, ext: str, width: int) -> Text:
    kind = line["kind"]
    if kind == "+":
        bg, gutter, txt = C["diff_add"], C["success"], "#a6f3a6"
        gi, lo, ln = "+", "    ", f"{line['ln']:>4}" if line["ln"] is not None else "    "
    elif kind == "-":
        bg, gutter, txt = C["diff_del"], C["danger"], "#ffb3ad"
        gi, lo, ln = "−", f"{line['lo']:>4}" if line["lo"] is not None else "    ", "    "
    else:
        bg, gutter, txt = C["bg_base"], C["faint"], C["text"]
        lo = f"{line['lo']:>4}" if line["lo"] is not None else "    "
        ln = f"{line['ln']:>4}" if line["ln"] is not None else "    "

    t = Text(no_wrap=True)
    t.append(f" {lo} {ln} ", style=f"{C['faint']} on {bg}")
    t.append(f"{gutter} ", style=f"bold {gutter} on {bg}")
    if kind == " " and ext in (".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".json", ".yaml", ".yml", ".toml", ".sh"):
        lex = ext.lstrip(".").replace("tsx", "typescript").replace("jsx", "javascript")
        try:
            buf = Syntax(line["text"], lex, theme="github-dark", background_color="default", line_numbers=False)
            t.append_text(buf)
            return t
        except Exception:  # noqa: BLE001 - fall back to plain colored text
            pass
    t.append(line["text"], style=f"{txt} on {bg}")
    return t


# ── AI output ───────────────────────────────────────────────────────────────────

def build_ai_output(text: str, title: str = "Analysis") -> "object":
    sections = {"summary", "changes", "risks", "issues", "suggestions",
                "quality", "commit message"}
    parts: list = [Rule(title, style=C["dim"]), Text("")]
    for line in text.splitlines():
        s = line.strip()
        key = s.lower().rstrip(":")
        if key in sections:
            h = Text()
            h.append(f"  {s.upper()}", style=f"bold {C['teal']}")
            parts.append(Text(""))
            parts.append(h)
        elif s.startswith(("- ", "* ", "• ")):
            b = Text(f"      • {s[2:]}", style=C["text"])
            parts.append(b)
        elif s:
            parts.append(Text(f"    {s}", style=C["text"]))
    parts.append(Text(""))
    return Group(*parts)


# ── Misc text / code / files ─────────────────────────────────────────────────────

def build_text(title: str, text: str) -> "object":
    parts = [Rule(title.lower(), style=C["dim"]), Text("")]
    for ln in text.splitlines():
        parts.append(Text(f"  {ln}", style=C["text"]))
    parts.append(Text(""))
    return Group(*parts)


def build_code(title: str, code: str, lexer: str) -> "object":
    return Group(
        Rule(title.lower(), style=C["dim"]),
        Text(""),
        Padding(Syntax(code, lexer, theme="github-dark", background_color="default"), (0, 2)),
        Text(""),
    )


def build_git_changes(changes) -> "object":
    from ..git import FileChange  # noqa: F401 - type hint only

    if not changes:
        return Text("  working tree clean", style=C["success"])
    from .components import table
    rows = []
    meta = {
        "A": (C["success"], "added"), "?": (C["info"], "new"),
        "D": (C["danger"], "deleted"), "M": (C["amber"], "modified"),
        "R": (C["primary"], "renamed"),
    }
    for c in changes:
        color, label = meta.get(c.status, (C["dim"], c.status))
        rows.append([(f"{label:<10}", color), (c.path, C["text"])])
    return table([("status", C["dim"]), ("path", C["dim"])], rows)


def build_doctor(checks: list) -> "object":
    from .components import table

    style = {
        "ok": (C["success"], "✓"), "warn": (C["warn"], "!"), "fail": (C["danger"], "✗"),
    }
    rows = []
    for c in checks:
        color, icon = style.get(c.status, (C["dim"], "·"))
        detail = c.detail or ""
        why = f" — {c.why}" if getattr(c, "why", "") else ""
        rows.append([
            (f"{icon} {c.name}", color),
            (f"{detail}{why}", C["dim"]),
        ])
    return table([("check", C["dim"]), ("detail", C["dim"])], rows)
