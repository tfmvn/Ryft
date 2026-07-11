"""Palette: dark github-style base, violet primary, cyan secondary,
teal for AI, mint/amber/coral for status. GitHub-accurate diff colours.

This is the lowest layer of the ``ui`` package — nothing else in ``ui``
depends on the handler modules or on ``commands``, so importing
``ryft.ui`` never triggers a circular import.
"""
from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

from prompt_toolkit.styles import Style as PTKStyle  # type: ignore[import]

# ═══════════════════════════════════════════════════════════════════════════════
# Backgrounds
# ═══════════════════════════════════════════════════════════════════════════════

BG_BASE     = "#0d1117"
BG_RAISED   = "#161b22"
BG_OVERLAY  = "#1a1f28"

# diff backgrounds (rich bg colors)
DIFF_ADD_BG  = "#0d2a16"   # dark green wash
DIFF_DEL_BG  = "#2a0d0d"   # dark red wash
DIFF_HUNK_BG = "#1a1830"   # dark purple wash

# ═══════════════════════════════════════════════════════════════════════════════
# Accent / status colours
# ═══════════════════════════════════════════════════════════════════════════════

VIOLET      = "#ae80ff"
VIOLET_DIM  = "#7b5cb8"
CYAN        = "#79c0ff"
MINT        = "#56d364"
AMBER       = "#e3b341"
CORAL       = "#ff7b72"
TEAL        = "#39d3c3"
PINK        = "#f778ba"

# ═══════════════════════════════════════════════════════════════════════════════
# Text colours
# ═══════════════════════════════════════════════════════════════════════════════

TEXT_HI     = "#f0f6fc"
TEXT_MID    = "#c9d1d9"
TEXT_DIM    = "#6e7681"
TEXT_GHOST  = "#3d444d"

# ═══════════════════════════════════════════════════════════════════════════════
# Rich console & theme
# ═══════════════════════════════════════════════════════════════════════════════

_THEME = Theme({
    "success": MINT,  "warning": AMBER, "error": CORAL,
    "accent":  VIOLET, "cyan": CYAN,    "teal": TEAL,
    "dim":     TEXT_DIM, "ghost": TEXT_GHOST,
})

console = Console(theme=_THEME, highlight=False)


def _term_width() -> int:
    return console.width or 100

# ═══════════════════════════════════════════════════════════════════════════════
# PTK style
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# Section helpers
# ═══════════════════════════════════════════════════════════════════════════════

from rich.rule import Rule  # noqa: E402 — needs console above


def _rule(label: str = "", color: str = TEXT_GHOST) -> None:
    if label:
        console.print(Rule(f"[{color}]{label}[/{color}]", style=TEXT_GHOST))
    else:
        console.print(Rule(style=TEXT_GHOST))


def _sp() -> None:
    console.print()
