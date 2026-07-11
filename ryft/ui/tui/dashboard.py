"""Dashboard renderable — the glanceable home screen.

Composes the design-system components into one Rich renderable that the TUI
feeds through `render.to_fragments`. Pure function of `ctx` + the command list:
no PTK, no event loop, easy to test. Stays information-dense but calm — KPI
strip up top, then git / providers / activity / commands panels below.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from ... import git as gitsys
from ..components import badge, empty_state, header_line, kpi, panel, stat_bar, table
from ..theme.palette import C


def build_dashboard(ctx, commands: list) -> object:
    branch = gitsys.current_branch(ctx.root)
    changes = gitsys.changed_files(ctx.root)
    commits_n = len(gitsys.recent_commits(ctx.root, n=50)) if gitsys.is_installed() else 0
    health = ctx.providers.health()
    healthy = sum(1 for h in health.values() if h.available)
    symbols_n = ctx.knowledge.symbol_count() if ctx.knowledge is not None else 0
    svc_state = ctx.services.state() if ctx.services is not None else {}

    # ── title ──
    title = Text()
    title.append("◆ RYFT", style=f"bold {C['primary']}")
    title.append(f"   {ctx.config.project.name}", style=f"bold {C['text']}")
    title.append(f"   on {branch}", style=C["dim"])
    title.append(" " * 4)
    dot = C["success"] if healthy else C["danger"]
    title.append("● ", style=dot)
    title.append(f"{healthy}/{len(health)} providers", style=C["dim"])

    # ── KPI strip ──
    kpis = Text()
    kpis.append("  ")
    kpis.append_text(kpi(str(len(changes)), "changes", C["amber"]))
    kpis.append("    ")
    kpis.append_text(kpi(str(commits_n), "commits", C["info"]))
    kpis.append("    ")
    kpis.append_text(kpi(str(symbols_n), "symbols", C["cyan"]))
    kpis.append("    ")
    kpis.append_text(kpi(str(len(commands)), "commands", C["primary"]))
    kpis.append("    ")
    kpis.append_text(kpi(str(len(svc_state)), "services", C["teal"]))

    # ── git panel ──
    if changes:
        rows = [
            [(c.path, C["text"]), (c.status, _status_color(c.status))]
            for c in changes[:8]
        ]
        git_body = table([("file", C["dim"]), ("status", C["dim"])], rows)
    else:
        git_body = empty_state("working tree clean")

    # ── providers panel ──
    prov_rows = []
    for name, h in sorted(health.items()):
        col = C["success"] if h.available else C["danger"]
        prov_rows.append([
            (name, C["text"]),
            ("online" if h.available else "offline", col),
            (h.detail or "", C["faint"]),
        ])
    prov_body = table(
        [("provider", C["dim"]), ("state", C["dim"]), ("detail", C["dim"])], prov_rows
    ) if prov_rows else empty_state("no providers")

    # ── activity panel ──
    acts = ctx.activity.recent(8)
    if acts:
        act_body = Group(*[
            Text(f"  {a.time_str}  ", style=C["faint"]) + Text(a.message, style=_level_color(a.level))
            for a in acts
        ])
    else:
        act_body = empty_state("no activity yet")

    # ── commands panel ──
    cmd_rows = [
        [(f"/{c.name}", C["primary"]), (c.description, C["dim"])]
        for c in commands[:12]
    ]
    cmd_body = table([("command", C["dim"]), ("description", C["dim"])], cmd_rows) if cmd_rows else empty_state("no commands")

    panels = Group(
        title,
        Text(""),
        kpis,
        Text(""),
        panel("git", git_body),
        Text(""),
        panel("providers", prov_body),
        Text(""),
        panel("activity", act_body),
        Text(""),
        panel("commands", cmd_body),
        Text(""),
        Text("  : or Ctrl+P command palette   ·   r refresh   ·   ? help   ·   q quit",
             style=C["faint"]),
    )
    return panels


def _status_color(status: str) -> str:
    return {
        "A": C["success"], "?": C["cyan"], "D": C["danger"],
        "M": C["amber"], "R": C["primary"],
    }.get(status, C["dim"])


def _level_color(level: str) -> str:
    return {
        "info": C["text"], "success": C["success"], "warn": C["warn"], "error": C["danger"],
    }.get(level, C["text"])
