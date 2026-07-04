"""Project-facing commands: /config, /init, /root, /tree, /files."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import register
from .. import config as config_mod
from ..utils import discover_files, human_path

if TYPE_CHECKING:
    from ..models import AppContext


@register(
    "config",
    description="Show or (re)write the project's .src.py configuration",
    usage=["/config", "/config init"],
)
def cmd_config(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    if args and args[0].lower() == "init":
        path = config_mod.init_config(cfg.root, cfg.project.name)
        ctx.config = config_mod.load_config(cfg.root)
        ui.success(f"Configuration written to {path}")
        return

    status, detail = config_mod.validate_config(cfg.root)
    lines = [
        f"project        {cfg.project.name}",
        f"root           {cfg.root}",
        f"config file    {cfg.path or '(none — using defaults)'}",
        f"config status  {status}" + (f" — {detail}" if detail else ""),
        "",
        f"ollama         {'enabled' if cfg.ollama.enabled else 'disabled'}  ·  "
        f"commit={cfg.ollama.commit_model}",
        f"git            {cfg.git.remote}/{cfg.git.branch}",
        f"sync           {'enabled' if cfg.sync.enabled else 'disabled'}  ·  "
        f"debounce={cfg.sync.debounce_seconds}s",
        f"formatter      {'enabled' if cfg.formatter.enabled else 'disabled'}",
    ]
    ui.render_text("config", "\n".join(lines))


@register(
    "init",
    description="Set up Ryft in this project (runs onboarding)",
    usage=["/init"],
)
def cmd_init(ctx: "AppContext", args: list[str]) -> None:
    from .. import onboarding, ui

    cfg, created = onboarding.run_onboarding(ctx.config.root)
    ctx.config = cfg
    if created:
        ui.render_completion_screen(cfg.project.name)


@register("root", description="Show the resolved project root")
def cmd_root(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    ui.info(str(ctx.config.root))


@register("tree", description="Show a directory tree of tracked, non-ignored files")
def cmd_tree(ctx: "AppContext", args: list[str]) -> None:
    from rich.tree import Tree
    from .. import ui

    cfg = ctx.config
    paths = discover_files(cfg.root, cfg.ignore)
    root_label = f"[bold]{cfg.root.name}[/bold]"
    tree = Tree(root_label)
    nodes: dict[tuple[str, ...], Tree] = {(): tree}

    for p in paths:
        rel_parts = Path(human_path(p, cfg.root)).parts
        for depth in range(1, len(rel_parts) + 1):
            key = tuple(rel_parts[:depth])
            if key in nodes:
                continue
            label = rel_parts[depth - 1]
            parent = nodes[tuple(rel_parts[: depth - 1])]
            nodes[key] = parent.add(label)

    ui.render_tree(tree)


@register("files", description="List tracked, non-ignored files")
def cmd_files(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    paths = discover_files(cfg.root, cfg.ignore)
    ui.render_files([human_path(p, cfg.root) for p in paths])
