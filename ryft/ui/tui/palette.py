"""Command palette renderable.

Given the command list, the current query, and the highlighted row, produce the
palette panel. Filtering is a simple case-insensitive substring over name,
description, and aliases — fast enough for thousands of commands and trivially
correct. Keyboard navigation/selection is handled by the app shell; this module
is pure rendering.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from ..components import empty_state, header_line, panel, table
from ..theme.palette import C


def filter_commands(commands: list, query: str) -> list:
    q = query.strip().lower()
    if not q:
        return list(commands)
    out = []
    for c in commands:
        hay = " ".join([c.name, c.description, *getattr(c, "aliases", [])]).lower()
        if q in hay:
            out.append(c)
    return out


def build_palette(commands: list, query: str, selected: int) -> object:
    matches = filter_commands(commands, query)
    head = header_line("command palette", f"{len(matches)} matches")
    if not matches:
        body = empty_state("no matching commands")
    else:
        rows = []
        for i, c in enumerate(matches):
            sel = i == selected
            marker = "▶ " if sel else "  "
            name = marker + "/" + c.name
            rows.append([
                (name, C["primary"] if sel else C["text"]),
                (c.description, C["dim"] if not sel else C["text"]),
            ])
        body = table([("command", C["dim"]), ("description", C["dim"])], rows)
    hint = Text("  ↑↓ navigate   ·   enter run   ·   esc cancel", style=C["faint"])
    return panel("palette", Group(head, Text(""), body, Text(""), hint))
