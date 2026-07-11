"""Derived styles from tokens: prompt_toolkit Style + Rich color helpers.

`ptk_style()` returns the chrome styling for the Application (status bar, focus
rings, palette). `rich()` returns a hex string for a token name so content
rendered through Rich stays on-palette. Keeping both here means a theme change
in `tokens.py` propagates everywhere.
"""

from __future__ import annotations

from prompt_toolkit.styles import Style

from .tokens import THEME


def ptk_style() -> Style:
    p = THEME
    return Style.from_dict({
        "statusbar": f"bg:{p.bg_panel} {p.text}",
        "statusbar.key": f"{p.primary} bold",
        "statusbar.dim": p.text_dim,
        "separator": p.border,
        "frame": f"{p.border}",
        "frame.border": f"{p.border}",
        "title": f"{p.primary} bold",
        "section": f"{p.cyan} bold",
        "kpi.value": f"{p.text} bold",
        "kpi.label": p.text_dim,
        "good": p.success,
        "warn": p.warn,
        "bad": p.danger,
        "accent": p.primary,
        "dim": p.text_dim,
        "faint": p.text_faint,
        "palette": f"bg:{p.bg_elevated} {p.text}",
        "palette.title": f"{p.primary} bold",
        "palette.item": p.text,
        "palette.item.selected": f"bg:{p.primary} {p.bg_base} bold",
        "palette.item.key": f"{p.primary}",
        "palette.prompt": f"{p.primary} bold",
        "help": f"bg:{p.bg_panel} {p.text}",
        "help.title": f"{p.primary} bold",
        "dialog": f"bg:{p.bg_elevated} {p.text}",
        "dialog.border": f"{p.primary}",
        "dialog.title": f"{p.primary} bold",
    })


def rich(name: str) -> str:
    """Return the hex color for token `name` as a Rich color string."""
    return getattr(THEME, name, THEME.text)


# Common Rich color aliases used across panels.
C = {
    "bg": THEME.bg_panel,
    "bg_base": THEME.bg_base,
    "text": THEME.text,
    "dim": THEME.text_dim,
    "faint": THEME.text_faint,
    "primary": THEME.primary,
    "cyan": THEME.cyan,
    "teal": THEME.teal,
    "mint": THEME.mint,
    "amber": THEME.amber,
    "coral": THEME.coral,
    "success": THEME.success,
    "warn": THEME.warn,
    "danger": THEME.danger,
    "info": THEME.info,
    "border": THEME.border,
    "diff_add": THEME.diff_add,
    "diff_del": THEME.diff_del,
    "diff_ctx": THEME.diff_ctx,
    "diff_hunk": THEME.diff_hunk,
}
