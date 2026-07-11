"""Icon glyphs and the icon-colour heuristic used by the activity log."""
from __future__ import annotations

from .colors import AMBER, CORAL, CYAN, MINT, TEXT_DIM, TEAL, VIOLET

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
