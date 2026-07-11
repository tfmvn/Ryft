"""Design tokens — the single source of visual truth.

Constants only, no logic. Mirrors `docs/DESIGN_SYSTEM.md`. Colors are GitHub-dark
derived, with a violet primary (#ae80ff) chosen to read as "AI" without the
Nerd-Font dependency the rest of the UI avoids. Both Rich hex strings (for
content rendering) and prompt_toolkit style fragments (for chrome) are derived
from here so the whole UI can be re-themed from one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Spacing scale — 4px base unit. Everything in the UI multiplies this.
UNIT = 4
SPACE = {
    "xs": 1 * UNIT,   # 4
    "sm": 2 * UNIT,   # 8
    "md": 3 * UNIT,   # 12
    "lg": 4 * UNIT,   # 16
    "xl": 6 * UNIT,   # 24
}

# Corner radius
RADIUS = 4

# Typography
MONO = "monospace"


@dataclass
class Palette:
    # Backgrounds (darkest -> lightest)
    bg_base: str = "#0d1117"
    bg_sunken: str = "#010409"
    bg_panel: str = "#161b22"
    bg_elevated: str = "#1c2128"
    bg_hover: str = "#21262d"

    # Borders
    border: str = "#30363d"
    border_strong: str = "#484f58"

    # Text
    text: str = "#e6edf3"
    text_dim: str = "#8b949e"
    text_faint: str = "#6e7681"

    # Primary (violet)
    primary: str = "#ae80ff"
    primary_dim: str = "#7c5cc4"

    # Semantic
    success: str = "#3fb950"
    warn: str = "#d29922"
    danger: str = "#f85149"
    info: str = "#58a6ff"

    # Accents
    cyan: str = "#39c5cf"
    teal: str = "#2dd4bf"
    mint: str = "#56d364"
    amber: str = "#e3b341"
    coral: str = "#ff7b72"

    # Diff
    diff_add: str = "#3fb950"
    diff_del: str = "#f85149"
    diff_ctx: str = "#8b949e"
    diff_hunk: str = "#39c5cf"

    # Prompt Toolkit class -> color (chrome styles live in palette.py)
    pt: dict = field(default_factory=dict)


# One shared instance; re-theme by mutating attributes before building styles.
THEME = Palette()
