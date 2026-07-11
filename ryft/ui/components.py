"""Reusable Rich renderables — the component library.

Pure functions returning Rich objects, so they are trivial to unit-test and
compose into panels/dashboards. No prompt_toolkit, no application state. Color
comes from `ui.theme.palette.C` (hex strings), keeping us on the design tokens.
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .theme.palette import C


def panel(title: str, body: RenderableType, *, border: str = C["border"], subtitle: str | None = None) -> Panel:
    return Panel(
        body,
        title=f"[bold {C['primary']}]{title}[/]",
        border_style=border,
        subtitle=subtitle,
        padding=(0, 1),
        highlight=False,
    )


def kpi(value: str, label: str, accent: str = C["primary"]) -> Text:
    t = Text()
    t.append(value + "\n", style=f"bold {accent}")
    t.append(label, style=C["dim"])
    return t


def stat_bar(pairs: list[tuple[str, str, str]]) -> Text:
    """`pairs` = [(label, value, color), ...] rendered as `label value │ …`."""
    t = Text()
    for i, (label, value, color) in enumerate(pairs):
        if i:
            t.append("  │  ", style=C["faint"])
        t.append(label + " ", style=C["dim"])
        t.append(value, style=color)
    return t


def bar(value: float, maximum: float = 100.0, width: int = 16, color: str = C["primary"]) -> Text:
    ratio = max(0.0, min(1.0, value / maximum)) if maximum else 0.0
    filled = int(round(ratio * width))
    t = Text()
    t.append("█" * filled, style=color)
    t.append("░" * (width - filled), style=C["border"])
    return t


def pill(text: str, color: str = C["primary"]) -> Text:
    return Text(f" {text} ", style=f"bold {color} on {C['bg_sunken']}")


def badge(text: str, color: str = C["dim"]) -> Text:
    b = Text()
    b.append("●", style=color)
    b.append(" " + text, style=C["text"])
    return b


def table(headers: list[tuple[str, str]], rows: list[list[tuple[str, str]]], *, padding: int = 1) -> Table:
    """`headers` = [(text, color)]; `rows` = list of [(text, color)] cells."""
    t = Table(show_header=True, header_style="bold", box=None, padding=(0, padding), expand=True)
    for text, color in headers:
        t.add_column(f"[{color}]{text}[/]", justify="left")
    for row in rows:
        t.add_row(*[Text(cell, style=style) for cell, style in row])
    return t


def empty_state(message: str) -> Align:
    return Align.center(Text(message, style=C["dim"]))


def header_line(left: str, right: str = "") -> Text:
    t = Text()
    t.append(left, style=f"bold {C['primary']}")
    if right:
        t.append("  " + right, style=C["dim"])
    return t
