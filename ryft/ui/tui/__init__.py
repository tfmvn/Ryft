"""Full-screen TUI: application shell, dashboard, command palette."""

from __future__ import annotations

from .app import RyftTUI
from .dashboard import build_dashboard
from .palette import build_palette, filter_commands
from .render import to_fragments

__all__ = ["RyftTUI", "build_dashboard", "build_palette", "filter_commands", "to_fragments"]
