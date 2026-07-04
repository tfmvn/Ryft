"""Config, tree, files, root commands."""
from __future__ import annotations

from pathlib import Path

from rich.tree import Tree  # type: ignore[import]

from .. import config as config_mod, ui
from ..config import DEFAULT_IGNORE
from ..utils import discover_files, human_path
from .registry import command


@command("config", "Show config.", usage=["/config", "/config init"])
def cmd_config(ctx, args: list[str]) -> None:
    cfg = ctx.config
    if args and args[0] == "init":
        path = config_mod.init_config(cfg.root, cfg.project.name)
        cfg.path = path
        ui.success(f"Initialized configuration at {path}")
        return
    if cfg.path and cfg.path.exists():
        ui.render_code(f"Configuration ({cfg.path.name})", cfg.path.read_text(encoding="utf-8"), "python")
    else:
        ui.warn("No .src.py file found. Using defaults. Run '/config init' to create one.")


@command("tree", "Show project tree.", usage=["/tree"])
def cmd_tree(ctx, args: list[str]) -> None:
    cfg = ctx.config
    root_node = Tree(f"[bold]{cfg.root.name}[/bold]")

    def add(node: Tree, path: Path, depth: int) -> None:
        if depth > 3: return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError: return
        for entry in entries:
            if entry.name in DEFAULT_IGNORE or entry.name in cfg.ignore or entry.name.startswith("."):
                continue
            if entry.is_dir():
                branch = node.add(f"[bold cyan]{entry.name}/[/bold cyan]")
                add(branch, entry, depth + 1)
            else:
                node.add(entry.name)

    add(root_node, cfg.root, 0)
    ui.render_tree(root_node)


@command("files", "List tracked files.", usage=["/files"])
def cmd_files(ctx, args: list[str]) -> None:
    cfg = ctx.config
    files = discover_files(cfg.root, cfg.ignore)
    ui.render_files([human_path(f, cfg.root) for f in files])


@command("root", "Show project root.", usage=["/root"])
def cmd_root(ctx, args: list[str]) -> None:
    ui.info(str(ctx.config.root))
