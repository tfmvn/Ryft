"""v2 system commands: /providers, /plugins, /github, /cloud, /dashboard,
/graph, /timeline.

Read-only introspection over the running context — providers, plugins, the
commit graph, and the live dashboard. These make the new architecture visible
from both the TUI palette and one-shot ``ryft <cmd>``.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.text import Text

from . import register
from .. import git
from ..ui.theme.palette import C

if TYPE_CHECKING:
    from ..models import AppContext

_console = Console()

_ROLE_ORDER = ("commit", "analyze", "review", "chat", "embed", "agent")


@register("providers", description="Show configured AI providers, roles, and health")
def cmd_providers(ctx: "AppContext", args: list[str]) -> None:
    health = ctx.providers.health()
    lines: list[Text] = [Text("providers", style=f"bold {C['primary']}"), Text("")]
    if not health:
        lines.append(Text("  no providers configured", style=C["dim"]))
    for name, h in sorted(health.items()):
        col = C["success"] if h.available else C["danger"]
        lines.append(
            Text(f"  {name:<14} ", style=C["text"])
            + Text("online" if h.available else "offline", style=col)
            + Text(f"  {h.detail or ''}", style=C["dim"])
        )
    lines += [Text(""), Text("roles", style=f"bold {C['primary']}")]
    roles = ctx.config.providers.roles
    for role in _ROLE_ORDER:
        lines.append(
            Text(f"  {role:<10} -> {getattr(roles, role)}", style=C["dim"])
        )
    _console.print(Group(*lines))


@register("plugins", description="List loaded plugins")
def cmd_plugins(ctx: "AppContext", args: list[str]) -> None:
    plugins = ctx.plugins.plugins if ctx.plugins is not None else []
    lines: list[Text] = [Text("plugins", style=f"bold {C['primary']}"), Text("")]
    if not plugins:
        lines.append(Text("  no plugins loaded", style=C["dim"]))
    for p in plugins:
        lines.append(
            Text(f"  {p.name:<16} ", style=C["text"])
            + Text(f"v{p.version}", style=C["dim"])
            + Text(f"  {p.description}", style=C["dim"])
        )
    _console.print(Group(*lines))


@register("github", description="GitHub status / open PRs (needs GITHUB_TOKEN)")
def cmd_github(ctx: "AppContext", args: list[str]) -> None:
    token_env = getattr(ctx.config.github, "token_env", "GITHUB_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        _console.print(
            Text(
                f"github: no token in ${token_env}. Set it to list open PRs/issues.",
                style=C["warn"],
            )
        )
        return
    remote = git.remote_url(ctx.config.root) or ""
    owner_repo = _owner_repo(remote)
    if not owner_repo:
        _console.print(Text(f"github: could not parse repo from remote '{remote}'", style=C["warn"]))
        return
    url = f"https://api.github.com/repos/{owner_repo}/pulls?state=open&per_page=20"
    try:
        import json
        import urllib.request

        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            prs = json.load(resp)
    except Exception as exc:  # network/parse failure — stay honest, don't crash
        _console.print(Text(f"github: could not fetch PRs: {exc}", style=C["warn"]))
        return
    lines = [
        Text(f"github · {owner_repo}", style=f"bold {C['primary']}"),
        Text(""),
    ]
    if not prs:
        lines.append(Text("  no open pull requests", style=C["dim"]))
    for pr in prs:
        lines.append(
            Text(f"  #{pr['number']} ", style=C["cyan"])
            + Text(pr["title"], style=C["text"])
        )
    _console.print(Group(*lines))


@register("cloud", description="Show cloud / agent-capable providers")
def cmd_cloud(ctx: "AppContext", args: list[str]) -> None:
    lines: list[Text] = [Text("cloud / agents", style=f"bold {C['primary']}"), Text("")]
    any_agent = False
    for p in ctx.providers.list():
        caps = p.capabilities()
        if "tools" in caps or "reasoning" in caps or ctx.providers.can("agent", "chat"):
            any_agent = True
            lines.append(
                Text(f"  {p.name:<14} ", style=C["text"])
                + Text("agent-capable", style=C["teal"])
                + Text(f"  caps={sorted(caps)}", style=C["dim"])
            )
    if not any_agent:
        lines.append(
            Text("  no agent-capable providers configured", style=C["dim"])
        )
    lines.append(
        Text("  (configure an agent role in [providers] to enable cloud agents)", style=C["faint"])
    )
    _console.print(Group(*lines))


@register("dashboard", description="Print the live dashboard (one-shot)")
def cmd_dashboard(ctx: "AppContext", args: list[str]) -> None:
    from ..commands import REGISTRY
    from ..ui.tui.dashboard import build_dashboard

    _console.print(build_dashboard(ctx, list(REGISTRY.values())))


@register("graph", description="Show the commit graph", usage=["/graph", "/graph <n>"])
def cmd_graph(ctx: "AppContext", args: list[str]) -> None:
    n = 20
    if args and args[0].isdigit():
        n = int(args[0])
    text = git.graph(ctx.config.root, n)
    _console.print(Text(text or "(no commits yet)", style=C["dim"]))


@register(
    "timeline",
    description="Recent commits as a timeline",
    usage=["/timeline", "/timeline <n>"],
)
def cmd_timeline(ctx: "AppContext", args: list[str]) -> None:
    n = 20
    if args and args[0].isdigit():
        n = int(args[0])
    commits = git.recent_commits(ctx.config.root, n)
    lines: list[Text] = [Text("timeline", style=f"bold {C['primary']}"), Text("")]
    for c in commits:
        lines.append(
            Text(f"  {c['date']:<12} ", style=C["dim"])
            + Text(c["hash"], style=C["cyan"])
            + Text(f"  {c['subject']}", style=C["text"])
        )
    _console.print(Group(*lines))


@register("sessions", description="Show the live activity feed and runtime state")
def cmd_sessions(ctx: "AppContext", args: list[str]) -> None:
    lines: list[Text] = [Text("sessions", style=f"bold {C['primary']}"), Text("")]
    events = ctx.activity.all()
    if not events:
        lines.append(Text("  no activity recorded this session", style=C["dim"]))
    for e in events[-20:]:
        lines.append(
            Text(f"  {e.time_str}  ", style=C["faint"])
            + Text(e.message, style=C["text"])
        )
    online = sum(1 for h in ctx.providers.health().values() if h.available)
    running = len(ctx.services.state()) if ctx.services is not None else 0
    loaded = len(ctx.plugins.plugins) if ctx.plugins is not None else 0
    lines += [
        Text(""),
        Text(
            f"  providers online: {online}   services: {running}   "
            f"plugins: {loaded}",
            style=C["dim"],
        ),
    ]
    _console.print(Group(*lines))


def _owner_repo(remote: str) -> str | None:
    """Extract ``owner/repo`` from a git remote URL (https or ssh)."""
    remote = remote.strip()
    if remote.endswith(".git"):
        remote = remote[:-4]
    if remote.startswith("git@"):
        # git@github.com:owner/repo
        rest = remote.split(":", 1)[-1]
    elif "://" in remote:
        rest = remote.split("://", 1)[-1]
        rest = rest.split("/", 1)[-1] if "/" in rest else rest
    else:
        return None
    if rest.count("/") >= 1:
        return "/".join(rest.split("/")[:2])
    return None
