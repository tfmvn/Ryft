"""/format -- run the formatter pipeline over the whole project, just the
changed files, or one explicit path.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import register
from .. import formatter, git
from ..utils import discover_files, human_path

if TYPE_CHECKING:
    from ..models import AppContext


@register(
    "format",
    description="Format files (whole project, changed files, or one path)",
    usage=["/format", "/format .", "/format changed", "/format <path>"],
    examples=["/format changed", "/format src/app.py"],
)
def cmd_format(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    target = args[0] if args else "changed"

    if target in (".", "all"):
        paths = discover_files(cfg.root, cfg.ignore)
    elif target == "changed":
        paths = [cfg.root / c.path for c in git.changed_files(cfg.root)]
    else:
        p = Path(target)
        paths = [p if p.is_absolute() else cfg.root / p]

    paths = [p for p in paths if p.exists()]
    if not paths:
        ui.info("Nothing to format.")
        return

    changed = formatter.format_paths(
        paths,
        max_blank_lines=cfg.formatter.max_blank_lines,
        remove_comments=cfg.formatter.remove_comments,
    )

    if not changed:
        ui.success(f"Checked {len(paths)} file(s) — nothing to format.")
        return

    for p in changed:
        ui.log_activity(ctx, f"Formatted {human_path(p, cfg.root)}", "info")
    ui.success(f"Formatted {len(changed)} of {len(paths)} file(s).")
